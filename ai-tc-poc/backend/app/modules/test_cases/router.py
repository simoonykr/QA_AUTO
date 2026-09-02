from uuid import UUID
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import DomainError
from app.modules.test_cases.repository import SqlTestCaseRepository, TestCaseVersionRuleError
from app.modules.test_cases.execution_plan import ExecutionPlanError
from app.schemas.test_cases import ExecutionPlanResponse, ImportedTestCase, StructureRequest, StructuredTestCase, TestCaseSummary, TestCaseVersionApproval, TestCaseVersionStepPatch
from app.modules.test_cases.importer import MAX_UPLOAD_BYTES, import_test_case
from app.modules.ai.service import StructureService


router = APIRouter(prefix="/test-cases", tags=["test-cases"])
version_router = APIRouter(prefix="/test-case-versions", tags=["test-cases"])


@router.get("", response_model=list[TestCaseSummary])
async def list_test_cases(session: AsyncSession = Depends(get_session)) -> list[TestCaseSummary]:
    repository = SqlTestCaseRepository(session, UUID(get_settings().default_organization_id))
    return await repository.list()


@router.post("/import", response_model=ImportedTestCase)
async def import_test_case_file(file: UploadFile = File(...)) -> ImportedTestCase:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    return import_test_case(file.filename or "upload", data)


@version_router.post("/current/structure", response_model=StructuredTestCase)
async def structure_test_case(body: StructureRequest, request: Request, session: AsyncSession = Depends(get_session)) -> StructuredTestCase:
    settings = get_settings()
    version_id = uuid4()
    structured = await StructureService(session, settings).structure(body, version_id)
    repository = SqlTestCaseRepository(
        session, UUID(settings.default_organization_id), UUID(settings.default_project_id),
        UUID(settings.default_user_id), UUID(request.state.request_id),
    )
    try:
        return await repository.save_structured(body, structured)
    except TestCaseVersionRuleError as exc:
        raise DomainError(exc.code, exc.message, 404) from None


@version_router.post("/{version_id}/approve", response_model=TestCaseVersionApproval)
async def approve_test_case_version(version_id: UUID, request: Request, session: AsyncSession = Depends(get_session)) -> TestCaseVersionApproval:
    settings = get_settings()
    repository = SqlTestCaseRepository(
        session, UUID(settings.default_organization_id), UUID(settings.default_project_id),
        UUID(settings.default_user_id), UUID(request.state.request_id),
    )
    try:
        return await repository.approve(version_id)
    except TestCaseVersionRuleError as exc:
        status_code = 409 if exc.code == "TC_VERSION_NOT_REVIEWABLE" else 404
        raise DomainError(exc.code, exc.message, status_code) from None
    except ExecutionPlanError as exc:
        raise DomainError(
            exc.code, exc.message, 422, retryable=False,
            details={"stepNo": exc.step_no, "stepId": exc.step_id, "missingFields": exc.missing_fields},
        ) from None


@version_router.patch("/{version_id}/steps/{step_id}", response_model=ExecutionPlanResponse)
async def patch_test_case_version_step(
    version_id: UUID,
    step_id: str,
    body: TestCaseVersionStepPatch,
    request: Request,
    environment_id: UUID | None = Query(default=None, alias="environmentId"),
    session: AsyncSession = Depends(get_session),
) -> ExecutionPlanResponse:
    settings = get_settings()
    repository = SqlTestCaseRepository(
        session, UUID(settings.default_organization_id), UUID(settings.default_project_id),
        UUID(settings.default_user_id), UUID(request.state.request_id),
    )
    try:
        return await repository.patch_step(version_id, step_id, body, environment_id)
    except TestCaseVersionRuleError as exc:
        status_code = 409 if exc.code == "TC_VERSION_NOT_REVIEWABLE" else (422 if exc.code == "TC_STEP_PATCH_EMPTY" else 404)
        raise DomainError(exc.code, exc.message, status_code) from None


@version_router.get("/{version_id}/execution-plan", response_model=ExecutionPlanResponse)
async def get_test_case_execution_plan(
    version_id: UUID,
    request: Request,
    environment_id: UUID | None = Query(default=None, alias="environmentId"),
    session: AsyncSession = Depends(get_session),
) -> ExecutionPlanResponse:
    settings = get_settings()
    repository = SqlTestCaseRepository(
        session, UUID(settings.default_organization_id), UUID(settings.default_project_id),
        UUID(settings.default_user_id), UUID(request.state.request_id),
    )
    try:
        return await repository.execution_plan(version_id, environment_id)
    except TestCaseVersionRuleError as exc:
        raise DomainError(exc.code, exc.message, 404) from None
