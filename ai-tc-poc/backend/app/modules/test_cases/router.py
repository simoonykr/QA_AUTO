from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_session
from app.modules.test_cases.repository import SqlTestCaseRepository
from app.schemas.test_cases import StructureRequest, StructuredStep, StructuredTestCase, TestCaseSummary


router = APIRouter(prefix="/test-cases", tags=["test-cases"])
version_router = APIRouter(prefix="/test-case-versions", tags=["test-cases"])


@router.get("", response_model=list[TestCaseSummary])
async def list_test_cases(session: AsyncSession = Depends(get_session)) -> list[TestCaseSummary]:
    repository = SqlTestCaseRepository(session, UUID(get_settings().default_organization_id))
    return await repository.list()


@version_router.post("/current/structure", response_model=StructuredTestCase)
async def structure_test_case(body: StructureRequest) -> StructuredTestCase:
    # Deterministic placeholder keeps the API contract stable until AI Gateway integration.
    return StructuredTestCase(
        versionId="00000000-0000-0000-0000-000000000501", title=body.title,
        preconditions=["Staging 환경과 미사용 이메일 계정이 준비되어 있다."],
        steps=[
            StructuredStep(id="step-1", title="로그인 페이지 진입", note="URL과 로그인 폼을 확인합니다.", action="navigate"),
            StructuredStep(id="step-2", title="테스트 계정 입력", note="보안 저장소의 계정 별칭을 사용합니다.", action="fill"),
            StructuredStep(id="step-3", title="로그인 버튼 선택", note="접근성 후보를 탐색합니다.", action="click"),
            StructuredStep(id="step-4", title="대시보드 노출 검증", note="URL과 환영 문구를 확인합니다.", action="assert"),
        ],
        assertions=[
            {"type": "text", "operator": "contains", "expected": "환영", "timeoutMs": 10_000},
            {"type": "url", "operator": "matches", "expected": "/dashboard", "timeoutMs": 10_000},
        ],
        assumptions=["test_password 변수를 사용합니다."] if "안전한 비밀번호" in body.rawText else [], confidence=0.94,
    )
