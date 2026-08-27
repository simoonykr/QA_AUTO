from datetime import UTC, datetime
from uuid import uuid4
from fastapi import APIRouter, Header, status
from app.core.errors import DomainError
from app.schemas.executions import CreateExecutionRequest, ExecutionResponse


router = APIRouter(prefix="/executions", tags=["executions"])
_idempotency_cache: dict[str, ExecutionResponse] = {}


@router.post("", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_execution(body: CreateExecutionRequest, idempotency_key: str | None = Header(default=None)) -> ExecutionResponse:
    if not idempotency_key:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key 헤더가 필요합니다.")
    if idempotency_key in _idempotency_cache:
        return _idempotency_cache[idempotency_key]
    execution = ExecutionResponse(id=f"EX-{str(uuid4())[:8]}", status="QUEUED", testCaseVersionId=body.testCaseVersionId, queuedAt=datetime.now(UTC))
    _idempotency_cache[idempotency_key] = execution
    return execution
