from fastapi import APIRouter
from app.schemas.test_cases import StructureRequest, StructuredStep, StructuredTestCase, TestCaseSummary


router = APIRouter(prefix="/test-cases", tags=["test-cases"])
version_router = APIRouter(prefix="/test-case-versions", tags=["test-cases"])


@router.get("", response_model=list[TestCaseSummary])
async def list_test_cases() -> list[TestCaseSummary]:
    # Repository wiring replaces this seed in the next slice.
    return [
        TestCaseSummary(id="TC-142", title="신규 사용자 이메일 회원가입", group="Authentication", status="READY", passRate=96, lastExecutedAt="12분 전"),
        TestCaseSummary(id="TC-138", title="상품 검색 및 가격 필터 적용", group="Search", status="READY", passRate=89, lastExecutedAt="어제"),
        TestCaseSummary(id="TC-131", title="장바구니 수량 변경 후 합계 검증", group="Checkout", status="REVIEW_REQUIRED", passRate=72, lastExecutedAt="2일 전"),
        TestCaseSummary(id="TC-127", title="만료된 세션에서 로그인 화면 이동", group="Authentication", status="READY", passRate=100, lastExecutedAt="4일 전"),
    ]


@version_router.post("/current/structure", response_model=StructuredTestCase)
async def structure_test_case(body: StructureRequest) -> StructuredTestCase:
    # Deterministic placeholder keeps the API contract stable until AI Gateway integration.
    return StructuredTestCase(
        versionId="tcv-new-v1", title=body.title,
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
