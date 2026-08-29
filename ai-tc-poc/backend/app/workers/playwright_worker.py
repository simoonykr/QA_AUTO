import asyncio
import json
import logging
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID, uuid4

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.db.models import Artifact, AuditEvent, Environment, Execution, ExecutionStatus, StepRun, TestCaseVersion
from app.workers.artifacts import ArtifactStore, StoredArtifact
from app.workers.step_executor import StepDefinitionError, execute_step


logger = logging.getLogger(__name__)
settings = get_settings()


class WorkerExecutionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _parse_viewport(value: str) -> dict[str, int]:
    try:
        width_text, height_text = value.lower().split("x", maxsplit=1)
        width, height = int(width_text), int(height_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise WorkerExecutionError("INVALID_VIEWPORT", "화면 크기 형식이 올바르지 않습니다.") from exc
    if not 320 <= width <= 7680 or not 320 <= height <= 4320:
        raise WorkerExecutionError("INVALID_VIEWPORT", "지원하지 않는 화면 크기입니다.")
    return {"width": width, "height": height}


def _assert_allowed_url(url: str, allowed_domains: list[str]) -> None:
    host = urlparse(url).hostname
    if not host or host not in allowed_domains:
        raise WorkerExecutionError("DOMAIN_NOT_ALLOWED", "허용되지 않은 테스트 대상 주소입니다.")


async def _claim_execution(execution_id: UUID) -> bool:
    async with SessionFactory() as session:
        result = await session.execute(
            update(Execution)
            .where(Execution.id == execution_id, Execution.status == ExecutionStatus.QUEUED)
            .values(status=ExecutionStatus.PROVISIONING)
            .returning(Execution.id)
        )
        claimed = result.scalar_one_or_none() is not None
        await session.commit()
        return claimed


async def _load_execution(execution_id: UUID) -> tuple[Execution, Environment, TestCaseVersion]:
    async with SessionFactory() as session:
        execution = await session.scalar(select(Execution).where(Execution.id == execution_id))
        if not execution:
            raise WorkerExecutionError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.")
        environment = await session.scalar(select(Environment).where(Environment.id == execution.environment_id))
        if not environment:
            raise WorkerExecutionError("ENVIRONMENT_NOT_FOUND", "실행 환경을 찾을 수 없습니다.")
        version = await session.scalar(select(TestCaseVersion).where(TestCaseVersion.id == execution.test_case_version_id))
        if not version:
            raise WorkerExecutionError("TC_VERSION_NOT_FOUND", "테스트 케이스 버전을 찾을 수 없습니다.")
        return execution, environment, version


async def _set_running(execution_id: UUID) -> bool:
    async with SessionFactory() as session:
        result = await session.execute(
            update(Execution)
            .where(Execution.id == execution_id, Execution.status == ExecutionStatus.PROVISIONING)
            .values(status=ExecutionStatus.RUNNING, started_at=datetime.now(UTC))
            .returning(Execution.id)
        )
        started = result.scalar_one_or_none() is not None
        await session.commit()
        return started


async def _is_cancel_requested(execution_id: UUID) -> bool:
    async with SessionFactory() as session:
        status = await session.scalar(select(Execution.status).where(Execution.id == execution_id))
        return status == ExecutionStatus.CANCEL_REQUESTED


async def _finish(
    execution_id: UUID,
    status: ExecutionStatus,
    *,
    error_code: str | None = None,
) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        execution = await session.scalar(select(Execution).where(Execution.id == execution_id))
        if not execution:
            return
        execution.status = status
        execution.ended_at = now
        execution.error_code = error_code
        step_count = await session.scalar(
            select(func.count()).select_from(StepRun).where(StepRun.execution_id == execution.id)
        )
        execution.result = {"status": status.value, "stepCount": step_count or 0, "errorCode": error_code}
        session.add(AuditEvent(
            organization_id=execution.organization_id,
            action=f"execution.{status.value.lower()}",
            resource_type="execution",
            resource_id=str(execution.id),
            request_id=uuid4(),
            metadata_json={"worker": settings.redis_worker_consumer, "errorCode": error_code},
        ))
        await session.commit()


async def _record_step(
    execution_id: UUID,
    step_no: int,
    *,
    status: str,
    action: dict,
    assertion: dict | None,
    started_at: datetime,
    error_code: str | None = None,
) -> UUID | None:
    async with SessionFactory() as session:
        execution = await session.scalar(select(Execution).where(Execution.id == execution_id))
        if not execution:
            return None
        step_run = StepRun(
            organization_id=execution.organization_id,
            execution_id=execution.id,
            step_no=step_no,
            attempt=execution.attempt,
            status=status,
            action=action,
            assertion=assertion,
            confidence=1 if status == "PASS" else 0,
            error_code=error_code,
            started_at=started_at,
            ended_at=datetime.now(UTC),
        )
        session.add(step_run)
        await session.commit()
        return step_run.id


async def _record_artifact(execution_id: UUID, step_run_id: UUID | None, stored: StoredArtifact) -> None:
    async with SessionFactory() as session:
        execution = await session.scalar(select(Execution).where(Execution.id == execution_id))
        if not execution:
            return
        session.add(Artifact(
            organization_id=execution.organization_id,
            execution_id=execution.id,
            step_run_id=step_run_id,
            artifact_type="FAILURE_SCREENSHOT",
            object_key=stored.object_key,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
        ))
        await session.commit()


async def execute(execution_id: UUID) -> None:
    if not await _claim_execution(execution_id):
        return

    execution, environment, version = await _load_execution(execution_id)
    current_action = {"type": "worker_start"}
    current_step_no = 0
    current_started_at = datetime.now(UTC)
    page = None
    try:
        if execution.settings.get("browser") != "Chromium":
            raise WorkerExecutionError("UNSUPPORTED_BROWSER", "현재 Worker는 Chromium 실행만 지원합니다.")
        _assert_allowed_url(environment.base_url, environment.allowed_domains)
        viewport = _parse_viewport(execution.settings.get("viewport", "1440x900"))
        locale = execution.settings.get("locale", "ko-KR")
        timeout_minutes = execution.settings.get("limits", {}).get("timeoutMinutes", 15)
        timeout_ms = min(max(int(timeout_minutes), 1), 30) * 60_000

        if not await _set_running(execution_id):
            await _finish(execution_id, ExecutionStatus.CANCELLED)
            return

        structured_spec = version.structured_spec or {}
        steps = structured_spec.get("steps") or [{"action": "navigate", "url": environment.base_url}]
        if not isinstance(steps, list):
            raise WorkerExecutionError("INVALID_TEST_SPEC", "구조화된 실행 단계 형식이 올바르지 않습니다.")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport=viewport, locale=locale)
                page = await context.new_page()
                for current_step_no, step in enumerate(steps, start=1):
                    if await _is_cancel_requested(execution_id):
                        await _finish(execution_id, ExecutionStatus.CANCELLED)
                        return
                    current_started_at = datetime.now(UTC)
                    current_action = {"type": step.get("action", "unknown"), "stepId": step.get("id")}
                    try:
                        result = await execute_step(page, step, environment.base_url)
                    except Exception:
                        await _capture_failure(page, execution_id, current_step_no, current_action, current_started_at)
                        raise
                    await _record_step(
                        execution_id,
                        current_step_no,
                        status="PASS",
                        action=result.action,
                        assertion=result.assertion,
                        started_at=current_started_at,
                    )
            finally:
                await browser.close()

        if await _is_cancel_requested(execution_id):
            await _finish(execution_id, ExecutionStatus.CANCELLED)
            return
        await _finish(execution_id, ExecutionStatus.PASS)
    except WorkerExecutionError as exc:
        await _finish(execution_id, ExecutionStatus.FAIL, error_code=exc.code)
    except StepDefinitionError:
        logger.exception("invalid test step", extra={"execution_id": str(execution_id), "step_no": current_step_no})
        await _finish(execution_id, ExecutionStatus.FAIL, error_code="INVALID_TEST_STEP")
    except AssertionError:
        await _finish(execution_id, ExecutionStatus.FAIL, error_code="ASSERTION_FAILED")
    except PlaywrightTimeoutError:
        await _finish(execution_id, ExecutionStatus.FAIL, error_code="STEP_TIMEOUT")
    except PlaywrightError:
        logger.exception("browser execution failed", extra={"execution_id": str(execution_id)})
        await _finish(execution_id, ExecutionStatus.FAIL, error_code="BROWSER_ERROR")
    except Exception:
        logger.exception("worker execution failed", extra={"execution_id": str(execution_id)})
        await _finish(execution_id, ExecutionStatus.SYSTEM_ERROR, error_code="WORKER_ERROR")


async def _capture_failure(page, execution_id: UUID, step_no: int, action: dict, started_at: datetime) -> None:
    step_run_id = await _record_step(
        execution_id,
        step_no,
        status="FAIL",
        action=action,
        assertion=None,
        started_at=started_at,
        error_code="STEP_FAILED",
    )
    try:
        screenshot = await page.screenshot(full_page=True)
        object_key = f"executions/{execution_id}/steps/{step_no}/failure.png"
        stored = await ArtifactStore().put_png(object_key, screenshot)
        await _record_artifact(execution_id, step_run_id, stored)
    except Exception:
        logger.exception("failure screenshot upload failed", extra={"execution_id": str(execution_id), "step_no": step_no})


async def _ensure_consumer_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(
            settings.redis_execution_stream,
            settings.redis_worker_group,
            id="0",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await _ensure_consumer_group(redis)
    try:
        while True:
            messages = await redis.xreadgroup(
                groupname=settings.redis_worker_group,
                consumername=settings.redis_worker_consumer,
                streams={settings.redis_execution_stream: ">"},
                count=1,
                block=settings.worker_poll_block_ms,
            )
            for _stream, entries in messages:
                for message_id, fields in entries:
                    try:
                        if fields.get("event_type") == "execution.requested":
                            payload = json.loads(fields.get("payload", "{}"))
                            await execute(UUID(payload.get("executionId") or fields["aggregate_id"]))
                    except Exception:
                        logger.exception("execution message failed", extra={"message_id": message_id})
                    finally:
                        await redis.xack(settings.redis_execution_stream, settings.redis_worker_group, message_id)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
