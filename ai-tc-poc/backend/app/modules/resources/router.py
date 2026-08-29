from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.modules.resources.repository import SqlResourceRepository
from app.schemas.resources import EnvironmentSummary, ExecutionPolicyResponse, TestAccountSummary


router = APIRouter(tags=["execution-resources"])


def repository_for(session: AsyncSession) -> SqlResourceRepository:
    settings = get_settings()
    return SqlResourceRepository(
        session,
        UUID(settings.default_organization_id),
        UUID(settings.default_project_id),
    )


@router.get("/environments", response_model=list[EnvironmentSummary])
async def list_environments(session: AsyncSession = Depends(get_session)) -> list[EnvironmentSummary]:
    return await repository_for(session).environments()


@router.get("/test-accounts", response_model=list[TestAccountSummary])
async def list_test_accounts(session: AsyncSession = Depends(get_session)) -> list[TestAccountSummary]:
    return await repository_for(session).test_accounts()


@router.get("/execution-policies/current", response_model=ExecutionPolicyResponse)
async def get_execution_policy() -> ExecutionPolicyResponse:
    return ExecutionPolicyResponse(
        allowedActions=["navigate", "click", "fill", "assert"],
        supportedBrowsers=["Chromium"],
        maxTimeoutMinutes=30,
        maxAiCalls=50,
        maxRetries=2,
        requireRiskApproval=True,
    )
