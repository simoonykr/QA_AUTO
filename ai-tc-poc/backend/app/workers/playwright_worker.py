import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse, urlunparse
from uuid import UUID, uuid4

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.db.models import Artifact, AuditEvent, Environment, Execution, ExecutionStatus, PageDiscovery, StepRun, TestCase, TestCaseVersion
from app.workers.artifacts import ArtifactStore, StoredArtifact
from app.workers.step_executor import StepDefinitionError, execute_step, selector_locator
from app.modules.test_cases.execution_plan import ExecutionPlanError, validate_execution_plan


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


def _assert_plan_snapshot(execution: Execution, plan) -> None:
    snapshot = execution.settings.get("executionPlan") or {}
    if (
        snapshot.get("hash") != plan.plan_hash
        or int(snapshot.get("revision") or 0) != plan.revision
        or int(snapshot.get("stepCount") or 0) != len(plan.steps)
        or snapshot.get("environmentId") != plan.environment["id"]
    ):
        raise WorkerExecutionError("EXECUTION_PLAN_INVALID", "실행 생성 이후 계획이 변경되어 Worker 실행을 차단했습니다.")


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
        environment = await session.scalar(select(Environment).where(
            Environment.id == execution.environment_id,
            Environment.organization_id == execution.organization_id,
            Environment.project_id == execution.project_id,
        ))
        if not environment:
            raise WorkerExecutionError("ENVIRONMENT_NOT_FOUND", "실행 환경을 찾을 수 없습니다.")
        version = await session.scalar(
            select(TestCaseVersion)
            .join(TestCase, TestCase.id == TestCaseVersion.test_case_id)
            .where(
                TestCaseVersion.id == execution.test_case_version_id,
                TestCaseVersion.organization_id == execution.organization_id,
                TestCase.organization_id == execution.organization_id,
                TestCase.project_id == execution.project_id,
            )
        )
        if not version:
            raise WorkerExecutionError("TC_VERSION_NOT_FOUND", "테스트 케이스 버전을 찾을 수 없습니다.")
        if version.status != "READY":
            raise WorkerExecutionError("TC_NOT_READY", "승인되지 않은 테스트 케이스는 실행할 수 없습니다.")
        if not version.structured_spec:
            raise WorkerExecutionError("INVALID_TEST_SPEC", "구조화된 실행 명세가 없습니다.")
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

        try:
            plan = validate_execution_plan(version, environment)
        except ExecutionPlanError as exc:
            raise WorkerExecutionError(exc.code, exc.message) from exc
        _assert_plan_snapshot(execution, plan)
        steps = plan.steps

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
                    current_action = {"type": step.get("action", "unknown"), "planStepId": step.get("id")}
                    try:
                        result = await execute_step(page, step, environment.base_url)
                    except Exception:
                        await _capture_failure(page, execution_id, current_step_no, current_action, current_started_at)
                        raise
                    await _record_step(
                        execution_id,
                        current_step_no,
                        status="PASS",
                        action={**result.action, "planStepId": step.get("id")},
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


def _safe_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _sanitize_discovery_text(value: object) -> str:
    text = str(value or "")[:160]
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "***@***", text, flags=re.IGNORECASE)
    return re.sub(r"(?<!\d)(?:01[016789][- ]?\d{3,4}[- ]?\d{4})(?!\d)", "***-****-****", text)


def _sanitize_discovery_elements(elements: list[dict]) -> list[dict]:
    safe = []
    for source in elements:
        item = {key: _sanitize_discovery_text(value) for key, value in source.items()}
        href = item.get("href", "")
        if href.lower().startswith(("mailto:", "tel:", "javascript:", "data:")) or "?" in href:
            item["href"] = ""
        elif "#" in href:
            item["href"] = href.split("#", 1)[0]
        safe.append(item)
    return safe


def _safe_discovery_url(base_url: str, href: str, allowed_domains: list[str]) -> str | None:
    candidate = urljoin(base_url, href)
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.hostname not in allowed_domains:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


def _candidate_for_element(element: dict, candidate_id: str) -> dict | None:
    if element.get("dataTestId"):
        strategy, selector, confidence = "DATA_TESTID", f'[data-testid="{_safe_quote(element["dataTestId"])}"]', 1.0
    elif element.get("role") and element.get("name"):
        strategy, selector, confidence = "ROLE_NAME", f'role={element["role"]}[name="{_safe_quote(element["name"])}"]', 0.95
    elif element.get("label"):
        strategy, selector, confidence = "LABEL", f'label="{_safe_quote(element["label"])}"', 0.92
    elif element.get("placeholder"):
        strategy, selector, confidence = "PLACEHOLDER", f'placeholder="{_safe_quote(element["placeholder"])}"', 0.9
    elif element.get("id"):
        strategy, selector, confidence = "ID_NAME", f'#{_safe_quote(element["id"])}', 0.88
    elif element.get("htmlName"):
        strategy, selector, confidence = "ID_NAME", f'[name="{_safe_quote(element["htmlName"])}"]', 0.85
    elif element.get("href"):
        strategy, selector, confidence = "LINK_URL", f'a[href="{_safe_quote(element["href"])}"]', 0.82
    elif element.get("name"):
        strategy, selector, confidence = "VISIBLE_TEXT", f'text="{_safe_quote(element["name"])}"', 0.75
    else:
        return None
    return {"id": candidate_id, "strategy": strategy, "selector": selector, "matchCount": 0, "visible": False, "enabled": False, "confidence": confidence}


async def discover(discovery_id: UUID) -> None:
    async with SessionFactory() as session:
        discovery = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id).with_for_update())
        if not discovery or discovery.status != "QUEUED":
            return
        discovery.status, discovery.started_at = "PROVISIONING", datetime.now(UTC)
        await session.commit()
    try:
        async with SessionFactory() as session:
            discovery = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id))
            environment = await session.scalar(select(Environment).where(
                Environment.id == discovery.environment_id, Environment.organization_id == discovery.organization_id,
                Environment.project_id == discovery.project_id,
            ))
            version = await session.scalar(select(TestCaseVersion).where(
                TestCaseVersion.id == discovery.test_case_version_id, TestCaseVersion.organization_id == discovery.organization_id,
            ))
            if not environment or not version or version.status != "REVIEW_REQUIRED":
                raise WorkerExecutionError("DISCOVERY_RESOURCE_INVALID", "페이지 분석 대상 정보를 찾을 수 없습니다.")
            _assert_allowed_url(environment.base_url, environment.allowed_domains)
            discovery.status = "SCANNING"
            await session.commit()
            source_steps = (version.structured_spec or {}).get("steps") or []
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport={"width": 1440, "height": 900})
                page = await context.new_page()
                await page.goto(environment.base_url, wait_until="domcontentloaded", timeout=30_000)
                _assert_allowed_url(page.url, environment.allowed_domains)
                page_url = page.url
                title = await page.title()
                iframe_count = len(page.frames) - 1
                has_shadow_dom = await page.locator("*").evaluate_all("els => els.some(el => !!el.shadowRoot)")
                elements = await page.locator("button,a,input,select,textarea,[role]").evaluate_all("""els => els.slice(0, 500).map(el => ({
                  tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || ({BUTTON:'button',A:'link',INPUT:'textbox',SELECT:'combobox',TEXTAREA:'textbox'}[el.tagName] || ''),
                  name: (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim().slice(0, 160),
                  label: el.labels && el.labels[0] ? (el.labels[0].innerText || '').trim().slice(0,160) : '',
                  placeholder: el.getAttribute('placeholder') || '', dataTestId: el.getAttribute('data-testid') || '',
                  id: el.id || '', htmlName: el.getAttribute('name') || '', href: el.getAttribute('href') || ''
                }))""")
                elements = _sanitize_discovery_elements(elements)
                fingerprint = hashlib.sha256(json.dumps({"url": page_url, "title": title, "elements": elements}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                pages = [{"url": page_url, "title": title, "fingerprint": fingerprint,
                          "iframeCount": iframe_count, "hasShadowDom": has_shadow_dom}]
                max_pages = int((discovery.settings or {}).get("maxPages") or 1)
                hrefs = await page.locator("a[href]").evaluate_all("els => els.slice(0,100).map(el => el.getAttribute('href') || '')")
                page_urls = []
                for href in hrefs:
                    candidate_url = _safe_discovery_url(page_url, href, environment.allowed_domains)
                    if candidate_url and candidate_url not in {page_url, *page_urls}:
                        page_urls.append(candidate_url)
                    if len(page_urls) >= max_pages - 1:
                        break
                for candidate_url in page_urls:
                    await page.goto(candidate_url, wait_until="domcontentloaded", timeout=20_000)
                    _assert_allowed_url(page.url, environment.allowed_domains)
                    final_url = _safe_discovery_url(candidate_url, page.url, environment.allowed_domains) or candidate_url
                    candidate_title = await page.title()
                    candidate_signature = await page.locator("button,a,input,select,textarea,[role]").evaluate_all(
                        "els => els.slice(0,500).map(el => [el.tagName,el.getAttribute('role')||'',el.getAttribute('aria-label')||'',el.id||'',el.getAttribute('name')||''])"
                    )
                    candidate_fingerprint = hashlib.sha256(json.dumps({"url": final_url, "title": candidate_title, "elements": candidate_signature}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                    pages.append({"url": final_url, "title": candidate_title, "fingerprint": candidate_fingerprint,
                                  "iframeCount": len(page.frames) - 1,
                                  "hasShadowDom": await page.locator("*").evaluate_all("els => els.some(el => !!el.shadowRoot)")})
                await page.goto(page_url, wait_until="domcontentloaded", timeout=20_000)
                async with SessionFactory() as session:
                    current = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id).with_for_update())
                    current.status = "MAPPING"
                    await session.commit()
                step_results = []
                for step in source_steps:
                    if step.get("action") not in {"fill", "click", "assert"} or step.get("assertionType") == "url":
                        continue
                    description = str(step.get("targetDescription") or step.get("title") or "")
                    hints = step.get("selectorHint") or {}
                    terms = [str(value).strip().lower().lstrip("#") for value in [*hints.values(), description] if value]
                    matched = [element for element in elements if any(term and (term in str(element.get("name", "")).lower().lstrip("#") or str(element.get("name", "")).lower().lstrip("#") in term) for term in terms)]
                    candidates = []
                    for index, element in enumerate(matched[:5], start=1):
                        candidate = _candidate_for_element(element, f"candidate-{index}")
                        if not candidate:
                            continue
                        locator = selector_locator(page, candidate["selector"])
                        candidate["matchCount"] = await locator.count()
                        if candidate["matchCount"]:
                            candidate["visible"] = await locator.first.is_visible()
                            candidate["enabled"] = await locator.first.is_enabled()
                        candidates.append(candidate)
                    valid = [candidate for candidate in candidates if candidate["matchCount"] == 1 and candidate["visible"] and candidate["enabled"]]
                    status = "RESOLVED" if len(valid) == 1 else ("AMBIGUOUS" if len(valid) > 1 else "NOT_FOUND")
                    step_results.append({
                        "stepId": str(step.get("id")), "targetDescription": description, "resolutionStatus": status,
                        "selectedCandidateId": valid[0]["id"] if len(valid) == 1 else None, "candidates": candidates,
                    })
                async with SessionFactory() as session:
                    current = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id).with_for_update())
                    current.status = "VALIDATING"
                    await session.commit()
            finally:
                await browser.close()
        executable = all(item["resolutionStatus"] == "RESOLVED" for item in step_results)
        async with SessionFactory() as session:
            discovery = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id).with_for_update())
            previous = await session.scalar(
                select(PageDiscovery).where(
                    PageDiscovery.test_case_version_id == discovery.test_case_version_id,
                    PageDiscovery.environment_id == discovery.environment_id,
                    PageDiscovery.id != discovery.id,
                    PageDiscovery.status.in_(["COMPLETED", "NEEDS_REVIEW"]),
                ).order_by(PageDiscovery.ended_at.desc()).with_for_update()
            )
            if previous and (previous.result or {}).get("fingerprint") != fingerprint:
                previous_result = dict(previous.result or {})
                previous_result["steps"] = [{**step, "resolutionStatus": "STALE", "selectedCandidateId": None} for step in previous_result.get("steps") or []]
                previous_result["executable"] = False
                previous.result = previous_result
                previous.status = "NEEDS_REVIEW"
            discovery.status = "COMPLETED" if executable else "NEEDS_REVIEW"
            discovery.result = {
                "revision": int((version.structured_spec or {}).get("planRevision") or 1),
                "pages": pages,
                "steps": step_results, "warnings": [],
                "executable": executable, "fingerprint": fingerprint, "model": None,
                "promptVersion": "rule-based-v1", "aiUsage": {"source": "RULE_BASED", "callCount": 0},
            }
            discovery.ended_at = datetime.now(UTC)
            session.add(AuditEvent(
                organization_id=discovery.organization_id, action="page_discovery.completed", resource_type="page_discovery",
                resource_id=str(discovery.id), request_id=uuid4(), metadata_json={"status": discovery.status, "elementCount": len(elements)},
            ))
            await session.commit()
    except Exception as exc:
        logger.exception("page discovery failed", extra={"discovery_id": str(discovery_id)})
        async with SessionFactory() as session:
            item = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id).with_for_update())
            if item:
                item.status, item.error_code, item.ended_at = "FAILED", getattr(exc, "code", "DISCOVERY_FAILED"), datetime.now(UTC)
                await session.commit()


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
                        elif fields.get("event_type") == "page_discovery.requested":
                            payload = json.loads(fields.get("payload", "{}"))
                            await discover(UUID(payload.get("discoveryId") or fields["aggregate_id"]))
                    except Exception:
                        logger.exception("execution message failed", extra={"message_id": message_id})
                    finally:
                        await redis.xack(settings.redis_execution_stream, settings.redis_worker_group, message_id)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
