import hashlib
import json
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Artifact, AuditEvent, Environment, Execution, ExecutionStatus, OutboxEvent, OutboxStatus,
    StepRun, TestAccount, TestCase, TestCaseVersion,
)
from app.schemas.executions import (
    ArtifactResponse, CreateExecutionRequest, ExecutionDetailsResponse, ExecutionResponse, StepRunResponse,
)


POC_ID_ALIASES = {
    "tcv-new-v1": UUID("00000000-0000-0000-0000-000000000501"),
    "env-staging": UUID("00000000-0000-0000-0000-000000000301"),
    "qa-runner-01": UUID("00000000-0000-0000-0000-000000000601"),
}


class ExecutionRuleError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


class SqlExecutionRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID, project_id: UUID, actor_id: UUID, request_id: UUID):
        self.session = session
        self.organization_id = organization_id
        self.project_id = project_id
        self.actor_id = actor_id
        self.request_id = request_id

    async def create(self, body: CreateExecutionRequest, idempotency_key: str) -> ExecutionResponse:
        digest = self._request_digest(body)
        existing = await self._find(idempotency_key)
        if existing:
            if existing.request_digest != digest:
                raise ExecutionRuleError("IDEMPOTENCY_CONFLICT", "같은 Idempotency-Key에 다른 요청 내용이 사용되었습니다.")
            return self._response(existing)

        version_id = self._resolve_id(body.testCaseVersionId)
        environment_id = self._resolve_id(body.environmentId)
        account_id = self._resolve_id(body.accountId) if body.accountId else None
        await self._validate_resources(version_id, environment_id, account_id)

        execution = Execution(
            organization_id=self.organization_id,
            project_id=self.project_id,
            test_case_version_id=version_id,
            environment_id=environment_id,
            account_id=account_id,
            idempotency_key=idempotency_key,
            request_digest=digest,
            status=ExecutionStatus.QUEUED,
            settings=body.model_dump(mode="json"),
        )
        self.session.add(execution)
        await self.session.flush()
        self.session.add(self._queued_event(execution))
        self.session.add(self._audit("execution.created", execution.id, {"idempotencyKey": idempotency_key}))
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self._find(idempotency_key)
            if existing:
                return self._response(existing)
            raise
        await self.session.refresh(execution)
        return self._response(execution)

    async def get(self, execution_id: UUID) -> Execution | None:
        return await self.session.scalar(
            select(Execution)
            .where(
                Execution.id == execution_id,
                Execution.organization_id == self.organization_id,
            )
            .execution_options(populate_existing=True)
        )

    async def details(self, execution_id: UUID) -> ExecutionDetailsResponse | None:
        execution = await self.get(execution_id)
        if not execution:
            return None
        step_runs = (await self.session.scalars(
            select(StepRun)
            .where(StepRun.execution_id == execution.id)
            .order_by(StepRun.step_no, StepRun.attempt)
        )).all()
        artifacts = (await self.session.scalars(
            select(Artifact)
            .where(Artifact.execution_id == execution.id)
            .order_by(Artifact.created_at)
        )).all()
        return ExecutionDetailsResponse(
            execution=self._response(execution),
            result=execution.result,
            errorCode=execution.error_code,
            steps=[StepRunResponse(
                id=str(item.id), stepNo=item.step_no, status=item.status,
                action=item.action, assertion=item.assertion, errorCode=item.error_code,
                startedAt=item.started_at, endedAt=item.ended_at,
            ) for item in step_runs],
            artifacts=[ArtifactResponse(
                id=str(item.id), stepRunId=str(item.step_run_id) if item.step_run_id else None,
                type=item.artifact_type, objectKey=item.object_key, sha256=item.sha256,
                sizeBytes=item.size_bytes, createdAt=item.created_at,
            ) for item in artifacts],
        )

    async def artifact(self, execution_id: UUID, artifact_id: UUID) -> Artifact | None:
        return await self.session.scalar(select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.execution_id == execution_id,
            Artifact.organization_id == self.organization_id,
        ))

    async def request_cancel(self, execution_id: UUID) -> ExecutionResponse | None:
        cancellable = [
            ExecutionStatus.QUEUED, ExecutionStatus.PROVISIONING, ExecutionStatus.RUNNING,
            ExecutionStatus.WAITING_APPROVAL,
        ]
        result = await self.session.execute(
            update(Execution)
            .where(
                Execution.id == execution_id,
                Execution.organization_id == self.organization_id,
                Execution.status.in_(cancellable),
            )
            .values(status=ExecutionStatus.CANCEL_REQUESTED)
            .returning(Execution)
        )
        execution = result.scalar_one_or_none()
        if execution:
            self.session.add(self._audit("execution.cancel_requested", execution.id, {}))
            await self.session.commit()
            return self._response(execution)
        return None

    async def retry(self, execution_id: UUID, idempotency_key: str) -> ExecutionResponse | None:
        source = await self.get(execution_id)
        if not source:
            return None
        terminal = {
            ExecutionStatus.PASS, ExecutionStatus.FAIL, ExecutionStatus.BLOCKED,
            ExecutionStatus.NEEDS_REVIEW, ExecutionStatus.CANCELLED, ExecutionStatus.SYSTEM_ERROR,
        }
        if source.status not in terminal:
            raise ValueError("execution is not terminal")
        existing = await self._find(idempotency_key)
        if existing:
            return self._response(existing)
        execution = Execution(
            organization_id=self.organization_id,
            project_id=source.project_id,
            test_case_version_id=source.test_case_version_id,
            environment_id=source.environment_id,
            account_id=source.account_id,
            idempotency_key=idempotency_key,
            request_digest=source.request_digest,
            status=ExecutionStatus.QUEUED,
            attempt=source.attempt + 1,
            settings=source.settings,
            parent_execution_id=source.id,
        )
        self.session.add(execution)
        await self.session.flush()
        self.session.add(self._queued_event(execution))
        self.session.add(self._audit("execution.retried", execution.id, {"parentExecutionId": str(source.id)}))
        await self.session.commit()
        await self.session.refresh(execution)
        return self._response(execution)

    def _queued_event(self, execution: Execution) -> OutboxEvent:
        return OutboxEvent(
            organization_id=self.organization_id,
            aggregate_type="execution",
            aggregate_id=execution.id,
            event_type="execution.requested",
            payload={
                "schemaVersion": 1,
                "jobId": str(execution.id),
                "executionId": str(execution.id),
                "organizationId": str(self.organization_id),
                "attempt": execution.attempt,
                "requestedAt": execution.queued_at.isoformat() if execution.queued_at else None,
            },
            status=OutboxStatus.PENDING,
        )

    async def _find(self, idempotency_key: str) -> Execution | None:
        return await self.session.scalar(select(Execution).where(
            Execution.organization_id == self.organization_id,
            Execution.idempotency_key == idempotency_key,
        ))

    async def _validate_resources(self, version_id: UUID, environment_id: UUID, account_id: UUID | None) -> None:
        version = await self.session.scalar(
            select(TestCaseVersion)
            .join(TestCase, TestCase.id == TestCaseVersion.test_case_id)
            .where(
                TestCaseVersion.id == version_id,
                TestCaseVersion.organization_id == self.organization_id,
                TestCase.organization_id == self.organization_id,
                TestCase.project_id == self.project_id,
            )
        )
        if not version:
            raise ExecutionRuleError("TC_VERSION_NOT_FOUND", "테스트 케이스 버전을 찾을 수 없습니다.")
        if version.status != "READY":
            raise ExecutionRuleError("TC_NOT_READY", "승인되지 않은 테스트 케이스는 실행할 수 없습니다.")
        environment = await self.session.scalar(select(Environment).where(
            Environment.id == environment_id,
            Environment.organization_id == self.organization_id,
            Environment.project_id == self.project_id,
        ))
        if not environment:
            raise ExecutionRuleError("ENVIRONMENT_NOT_FOUND", "실행 환경을 찾을 수 없습니다.")
        if account_id:
            account = await self.session.scalar(select(TestAccount).where(
                TestAccount.id == account_id,
                TestAccount.organization_id == self.organization_id,
                TestAccount.project_id == self.project_id,
            ))
            if not account:
                raise ExecutionRuleError("TEST_ACCOUNT_NOT_FOUND", "테스트 계정을 찾을 수 없습니다.")
            if account.status != "AVAILABLE":
                raise ExecutionRuleError("TEST_ACCOUNT_UNAVAILABLE", "현재 사용할 수 없는 테스트 계정입니다.")

    def _audit(self, action: str, resource_id: UUID, metadata: dict) -> AuditEvent:
        return AuditEvent(
            organization_id=self.organization_id,
            actor_id=self.actor_id,
            action=action,
            resource_type="execution",
            resource_id=str(resource_id),
            request_id=self.request_id,
            metadata_json=metadata,
        )

    @staticmethod
    def _request_digest(body: CreateExecutionRequest) -> str:
        canonical = json.dumps(body.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _resolve_id(value: str) -> UUID:
        if value in POC_ID_ALIASES:
            return POC_ID_ALIASES[value]
        try:
            return UUID(value)
        except ValueError as exc:
            raise ExecutionRuleError("INVALID_RESOURCE_ID", "TC·환경·계정 ID 형식이 올바르지 않습니다.") from exc

    @staticmethod
    def _response(execution: Execution) -> ExecutionResponse:
        return ExecutionResponse(
            id=str(execution.id), status=execution.status.value,
            testCaseVersionId=str(execution.test_case_version_id), queuedAt=execution.queued_at,
            startedAt=execution.started_at, endedAt=execution.ended_at,
            parentExecutionId=str(execution.parent_execution_id) if execution.parent_execution_id else None,
        )
