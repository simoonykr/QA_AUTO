from uuid import UUID
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import DomainError
from app.modules.executions.repository import SqlExecutionRepository
from app.schemas.executions import CreateExecutionRequest, ExecutionActionResponse, ExecutionResponse


router = APIRouter(prefix="/executions", tags=["executions"])


def repository_for(session: AsyncSession) -> SqlExecutionRepository:
    settings = get_settings()
    return SqlExecutionRepository(session, UUID(settings.default_organization_id), UUID(settings.default_project_id))


@router.post("", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_execution(body: CreateExecutionRequest, idempotency_key: str | None = Header(default=None), session: AsyncSession = Depends(get_session)) -> ExecutionResponse:
    if not idempotency_key:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key 헤더가 필요합니다.")
    return await repository_for(session).create(body, idempotency_key)


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: UUID, session: AsyncSession = Depends(get_session)) -> ExecutionResponse:
    repository = repository_for(session)
    execution = await repository.get(execution_id)
    if not execution:
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)
    return repository._response(execution)


@router.post("/{execution_id}/cancel", response_model=ExecutionActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def cancel_execution(execution_id: UUID, session: AsyncSession = Depends(get_session)) -> ExecutionActionResponse:
    repository = repository_for(session)
    existing = await repository.get(execution_id)
    if not existing:
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)
    execution = await repository.request_cancel(execution_id)
    if not execution:
        raise DomainError("EXECUTION_STATE_CONFLICT", "현재 상태에서는 실행을 중단할 수 없습니다.", 409)
    return ExecutionActionResponse(execution=execution)


@router.post("/{execution_id}/retry", response_model=ExecutionActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_execution(execution_id: UUID, idempotency_key: str | None = Header(default=None), session: AsyncSession = Depends(get_session)) -> ExecutionActionResponse:
    if not idempotency_key:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key 헤더가 필요합니다.")
    repository = repository_for(session)
    try:
        execution = await repository.retry(execution_id, idempotency_key)
    except ValueError:
        raise DomainError("EXECUTION_STATE_CONFLICT", "종료된 실행만 재시도할 수 있습니다.", 409) from None
    if not execution:
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)
    return ExecutionActionResponse(execution=execution)
