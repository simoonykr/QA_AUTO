from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Execution, ExecutionStatus, OutboxEvent, OutboxStatus
from app.schemas.executions import CreateExecutionRequest, ExecutionResponse


class SqlExecutionRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID, project_id: UUID):
        self.session = session
        self.organization_id = organization_id
        self.project_id = project_id

    async def create(self, body: CreateExecutionRequest, idempotency_key: str) -> ExecutionResponse:
        existing = await self._find(idempotency_key)
        if existing:
            return self._response(existing)

        execution = Execution(
            organization_id=self.organization_id,
            project_id=self.project_id,
            test_case_version_id=UUID(body.testCaseVersionId),
            environment_id=UUID(body.environmentId),
            account_id=UUID(body.accountId) if body.accountId else None,
            idempotency_key=idempotency_key,
            status=ExecutionStatus.QUEUED,
            settings=body.model_dump(mode="json"),
        )
        self.session.add(execution)
        await self.session.flush()
        self.session.add(self._queued_event(execution))
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
        return await self.session.scalar(select(Execution).where(
            Execution.id == execution_id,
            Execution.organization_id == self.organization_id,
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
            status=ExecutionStatus.QUEUED,
            attempt=source.attempt + 1,
            settings=source.settings,
            parent_execution_id=source.id,
        )
        self.session.add(execution)
        await self.session.flush()
        self.session.add(self._queued_event(execution))
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

    @staticmethod
    def _response(execution: Execution) -> ExecutionResponse:
        return ExecutionResponse(
            id=str(execution.id), status=execution.status.value,
            testCaseVersionId=str(execution.test_case_version_id), queuedAt=execution.queued_at,
            startedAt=execution.started_at, endedAt=execution.ended_at,
            parentExecutionId=str(execution.parent_execution_id) if execution.parent_execution_id else None,
        )
