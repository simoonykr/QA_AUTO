from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import DomainError
from app.modules.discoveries.repository import DiscoveryRepository, DiscoveryRuleError
from app.schemas.test_cases import DiscoveryApplyRequest, DiscoveryResponse, DiscoveryStartRequest, DiscoveryStartResponse, ExecutionPlanResponse

router = APIRouter(prefix="/test-case-versions", tags=["page-discovery"])


def _repository(session: AsyncSession, request: Request) -> DiscoveryRepository:
    settings = get_settings()
    return DiscoveryRepository(session, UUID(settings.default_organization_id), UUID(settings.default_project_id), UUID(settings.default_user_id), UUID(request.state.request_id))


def _raise(exc: DiscoveryRuleError) -> None:
    status = 404 if exc.code in {"TC_VERSION_NOT_FOUND", "ENVIRONMENT_NOT_FOUND", "DISCOVERY_NOT_FOUND"} else (422 if exc.code in {"AI_DISABLED", "DISCOVERY_SELECTION_REQUIRED"} else 409)
    raise DomainError(exc.code, exc.message, status, retryable=False) from None


@router.post("/{version_id}/discover", response_model=DiscoveryStartResponse, status_code=202)
async def start_discovery(version_id: UUID, body: DiscoveryStartRequest, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        return await _repository(session, request).start(version_id, body, get_settings().ai_ready)
    except DiscoveryRuleError as exc:
        _raise(exc)


@router.get("/{version_id}/discoveries/{discovery_id}", response_model=DiscoveryResponse)
async def get_discovery(version_id: UUID, discovery_id: UUID, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        return await _repository(session, request).get(version_id, discovery_id)
    except DiscoveryRuleError as exc:
        _raise(exc)


@router.post("/{version_id}/discoveries/{discovery_id}/apply", response_model=ExecutionPlanResponse)
async def apply_discovery(version_id: UUID, discovery_id: UUID, body: DiscoveryApplyRequest, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        return await _repository(session, request).apply(version_id, discovery_id, body)
    except DiscoveryRuleError as exc:
        _raise(exc)
