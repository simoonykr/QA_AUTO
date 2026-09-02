from uuid import UUID
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import DomainError
from app.modules.test_cases.repository import SqlTestCaseRepository, TestCaseVersionRuleError
from app.schemas.test_cases import ImportedTestCase, StructureRequest, StructuredTestCase, TestCaseSummary, TestCaseVersionApproval
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
