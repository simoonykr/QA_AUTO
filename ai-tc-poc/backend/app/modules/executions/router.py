from uuid import UUID
from io import BytesIO
from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import DomainError
from app.modules.executions.repository import ExecutionRuleError, SqlExecutionRepository
from app.modules.executions.events import execution_event_stream
from app.modules.test_cases.execution_plan import ExecutionPlanError
from app.schemas.executions import CreateExecutionRequest, ExecutionActionResponse, ExecutionDetailsResponse, ExecutionResponse
from app.workers.artifacts import ArtifactStore


router = APIRouter(prefix="/executions", tags=["executions"])


def repository_for(session: AsyncSession, request: Request) -> SqlExecutionRepository:
    settings = get_settings()
    return SqlExecutionRepository(
        session,
        UUID(settings.default_organization_id),
        UUID(settings.default_project_id),
        UUID(settings.default_user_id),
        UUID(request.state.request_id),
    )


@router.post("", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_execution(body: CreateExecutionRequest, request: Request, idempotency_key: str | None = Header(default=None), session: AsyncSession = Depends(get_session)) -> ExecutionResponse:
    if not idempotency_key:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key 헤더가 필요합니다.")
    try:
        return await repository_for(session, request).create(body, idempotency_key)
    except ExecutionRuleError as exc:
        status_code = 409 if exc.code in {"IDEMPOTENCY_CONFLICT", "TC_NOT_READY"} else 404 if exc.code.endswith("_NOT_FOUND") else 400
        raise DomainError(exc.code, exc.message, status_code) from None
    except ExecutionPlanError as exc:
        raise DomainError(
            exc.code, exc.message, 422, retryable=False,
            details={"stepNo": exc.step_no} if exc.step_no else {},
        ) from None


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: UUID, request: Request, session: AsyncSession = Depends(get_session)) -> ExecutionResponse:
    repository = repository_for(session, request)
    execution = await repository.get(execution_id)
    if not execution:
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)
    return repository._response(execution)


@router.get("/{execution_id}/details", response_model=ExecutionDetailsResponse)
async def get_execution_details(execution_id: UUID, request: Request, session: AsyncSession = Depends(get_session)) -> ExecutionDetailsResponse:
    details = await repository_for(session, request).details(execution_id)
    if not details:
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)
    return details


@router.get("/{execution_id}/events")
async def stream_execution_events(execution_id: UUID, request: Request, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
    repository = repository_for(session, request)
    if not await repository.get(execution_id):
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)

    async def load_details() -> ExecutionDetailsResponse | None:
        return await repository.details(execution_id)

    return StreamingResponse(
        execution_event_stream(request, load_details),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{execution_id}/artifacts/{artifact_id}")
async def download_execution_artifact(execution_id: UUID, artifact_id: UUID, request: Request, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
    artifact = await repository_for(session, request).artifact(execution_id, artifact_id)
    if not artifact:
        raise DomainError("ARTIFACT_NOT_FOUND", "실행 증적을 찾을 수 없습니다.", 404)
    try:
        content = await ArtifactStore().get(artifact.object_key)
    except Exception:
        raise DomainError("ARTIFACT_STORAGE_ERROR", "증적 저장소에서 파일을 읽을 수 없습니다.", 503, retryable=True) from None
    return StreamingResponse(
        BytesIO(content),
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="{artifact.id}.png"',
            "Content-Length": str(len(content)),
            "ETag": artifact.sha256,
        },
    )


@router.post("/{execution_id}/cancel", response_model=ExecutionActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def cancel_execution(execution_id: UUID, request: Request, session: AsyncSession = Depends(get_session)) -> ExecutionActionResponse:
    repository = repository_for(session, request)
    existing = await repository.get(execution_id)
    if not existing:
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)
    execution = await repository.request_cancel(execution_id)
    if not execution:
        raise DomainError("EXECUTION_STATE_CONFLICT", "현재 상태에서는 실행을 중단할 수 없습니다.", 409)
    return ExecutionActionResponse(execution=execution)


@router.post("/{execution_id}/retry", response_model=ExecutionActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_execution(execution_id: UUID, request: Request, idempotency_key: str | None = Header(default=None), session: AsyncSession = Depends(get_session)) -> ExecutionActionResponse:
    if not idempotency_key:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key 헤더가 필요합니다.")
    repository = repository_for(session, request)
    try:
        execution = await repository.retry(execution_id, idempotency_key)
    except ValueError:
        raise DomainError("EXECUTION_STATE_CONFLICT", "종료된 실행만 재시도할 수 있습니다.", 409) from None
    if not execution:
        raise DomainError("EXECUTION_NOT_FOUND", "실행 정보를 찾을 수 없습니다.", 404)
    return ExecutionActionResponse(execution=execution)
