from uuid import UUID
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.modules.test_cases.repository import SqlTestCaseRepository
from app.schemas.test_cases import ImportedTestCase, StructureRequest, StructuredTestCase, TestCaseSummary
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
async def structure_test_case(body: StructureRequest, session: AsyncSession = Depends(get_session)) -> StructuredTestCase:
    return await StructureService(session, get_settings()).structure(body)
