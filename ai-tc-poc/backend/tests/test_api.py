from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile
from fastapi.testclient import TestClient
import pytest

from app.core.database import get_session
from app.core.config import Settings, get_settings
from app.db.models import Base
from app.main import app
from app.modules.executions.repository import ExecutionRuleError, SqlExecutionRepository
from app.modules.test_cases.repository import SqlTestCaseRepository, TestCaseVersionRuleError as VersionRuleError
from app.modules.test_cases.execution_plan import ExecutionPlanError, validate_execution_plan
from app.modules.auth.service import validate_demo_auth_config
from app.schemas.executions import CreateExecutionRequest, ExecutionDetailsResponse, ExecutionResponse
from app.schemas.test_cases import TestCaseSummary
from app.schemas.resources import EnvironmentSummary, TestAccountSummary
from app.workers.playwright_worker import WorkerExecutionError, _assert_allowed_url, _assert_plan_snapshot, _parse_viewport
from app.workers.step_executor import StepDefinitionError, execute_step


async def fake_session():
    yield object()


class FakeTestCaseRepository:
    versions: dict[str, str] = {}

    def __init__(self, *_args):
        pass

    async def list(self):
        return [TestCaseSummary(id="TC-142", title="회원가입", group="Authentication", status="READY", passRate=96, lastExecutedAt="12분 전")]

    async def save_structured(self, _body, result):
        self.versions[result.versionId] = "REVIEW_REQUIRED"
        return result

    async def approve(self, version_id):
        key = str(version_id)
        if key not in self.versions:
            from app.modules.test_cases.repository import TestCaseVersionRuleError
            raise TestCaseVersionRuleError("TC_VERSION_NOT_FOUND", "테스트 케이스 버전을 찾을 수 없습니다.")
        self.versions[key] = "READY"
        return {"versionId": key, "status": "READY"}

    async def execution_plan(self, version_id, environment_id=None):
        return {
            "versionId": str(version_id), "status": "READY", "revision": 1,
            "planHash": "a" * 64,
            "environment": {"id": str(environment_id or UUID('00000000-0000-0000-0000-000000000301')), "name": "Staging", "baseUrl": "http://demo-target"},
            "steps": [{"stepNo": 1, "id": "step-1", "title": "페이지 진입", "action": "navigate", "url": "http://demo-target", "timeoutMs": 10000}],
            "warnings": [], "executable": True, "source": "RULE_BASED",
        }

    async def patch_step(self, version_id, step_id, body, environment_id=None):
        plan = await self.execution_plan(version_id, environment_id)
        plan["revision"] = 2
        plan["planHash"] = "b" * 64
        plan["steps"][0].update(body.model_dump(exclude_unset=True))
        return plan


class FakeExecutionRepository:
    ids: dict[str, ExecutionResponse] = {}

    def __init__(self, *_args):
        pass

    async def create(self, body, idempotency_key):
        if idempotency_key not in self.ids:
            self.ids[idempotency_key] = ExecutionResponse(
                id="00000000-0000-0000-0000-000000000701", status="QUEUED",
                testCaseVersionId=body.testCaseVersionId, queuedAt=datetime.now(UTC),
            )
        return self.ids[idempotency_key]

    async def get(self, execution_id):
        return next((item for item in self.ids.values() if item.id == str(execution_id)), None)

    async def details(self, execution_id):
        item = await self.get(execution_id)
        if not item:
            return None
        return ExecutionDetailsResponse(
            execution=item,
            result={"status": item.status, "stepCount": 1},
            steps=[{
                "id": "00000000-0000-0000-0000-000000000801",
                "stepNo": 1,
                "status": "PASS",
                "action": {"type": "navigate"},
            }],
            artifacts=[],
        )

    async def artifact(self, execution_id, artifact_id):
        if str(artifact_id) != "00000000-0000-0000-0000-000000000901":
            return None
        return SimpleNamespace(
            id=artifact_id,
            object_key=f"executions/{execution_id}/steps/1/failure.png",
            sha256="a" * 64,
        )

    async def request_cancel(self, execution_id):
        item = await self.get(execution_id)
        if item and item.status in {"QUEUED", "PROVISIONING", "RUNNING", "WAITING_APPROVAL"}:
            return item.model_copy(update={"status": "CANCEL_REQUESTED"})
        return None

    async def retry(self, execution_id, idempotency_key):
        item = await self.get(execution_id)
        if not item:
            return None
        if item.status not in {"PASS", "FAIL", "BLOCKED", "NEEDS_REVIEW", "CANCELLED", "SYSTEM_ERROR"}:
            raise ValueError
        retried = item.model_copy(update={
            "id": "00000000-0000-0000-0000-000000000702",
            "status": "QUEUED",
            "parentExecutionId": item.id,
        })
        self.ids[idempotency_key] = retried
        return retried

    @staticmethod
    def _response(item):
        return item


class FakeResourceRepository:
    def __init__(self, *_args):
        pass

    async def environments(self):
        return [EnvironmentSummary(
            id="00000000-0000-0000-0000-000000000301",
            name="Staging",
            baseUrl="http://demo-target",
            allowedDomains=["demo-target"],
            defaultViewport="1440x900",
        )]

    async def test_accounts(self):
        return [TestAccountSummary(
            id="00000000-0000-0000-0000-000000000601",
            name="qa-runner-01",
            status="AVAILABLE",
        )]


@pytest.fixture(autouse=True)
def isolate_database(monkeypatch):
    app.dependency_overrides[get_session] = fake_session
    monkeypatch.setattr("app.modules.test_cases.router.SqlTestCaseRepository", FakeTestCaseRepository)
    monkeypatch.setattr("app.modules.executions.router.SqlExecutionRepository", FakeExecutionRepository)
    monkeypatch.setattr("app.modules.resources.router.SqlResourceRepository", FakeResourceRepository)
    FakeExecutionRepository.ids.clear()
    FakeTestCaseRepository.versions.clear()
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]


def test_demo_auth_protects_api_and_uses_http_only_cookie() -> None:
    settings = get_settings()
    settings.demo_auth_enabled = True
    settings.demo_auth_username = "demo-user"
    settings.demo_auth_password = "demo-password"
    settings.demo_session_secret = "test-session-secret-that-is-longer-than-32-characters"
    try:
        unauthorized = client.get("/api/v1/test-cases")
        rejected = client.post("/api/v1/auth/login", json={
            "username": "demo-user", "password": "wrong-password",
        })
        logged_in = client.post("/api/v1/auth/login", json={
            "username": "demo-user", "password": "demo-password",
        })
        me = client.get("/api/v1/auth/me")
        authorized = client.get("/api/v1/test-cases")
        logged_out = client.post("/api/v1/auth/logout")
        after_logout = client.get("/api/v1/test-cases")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["code"] == "AUTH_REQUIRED"
        assert rejected.status_code == 401
        assert logged_in.status_code == 200
        assert "HttpOnly" in logged_in.headers["set-cookie"]
        assert "SameSite=lax" in logged_in.headers["set-cookie"]
        assert me.json()["approvalStatus"] == "APPROVED"
        assert authorized.status_code == 200
        assert logged_out.status_code == 204
        assert after_logout.status_code == 401
    finally:
        settings.demo_auth_enabled = False
        settings.demo_auth_username = ""
        settings.demo_auth_password = ""
        settings.demo_session_secret = ""
        client.cookies.clear()


def test_demo_auth_rejects_insecure_cross_site_cookie() -> None:
    settings = get_settings().model_copy(update={
        "demo_auth_enabled": True,
        "demo_auth_username": "demo-user",
        "demo_auth_password": "demo-password",
        "demo_session_secret": "test-session-secret-that-is-longer-than-32-characters",
        "demo_cookie_secure": False,
        "demo_cookie_samesite": "none",
    })
    with pytest.raises(RuntimeError, match="DEMO_COOKIE_SECURE"):
        validate_demo_auth_config(settings)


def test_demo_auth_requires_secure_cookie_outside_local_environment() -> None:
    settings = get_settings().model_copy(update={
        "app_env": "production",
        "demo_auth_enabled": True,
        "demo_auth_username": "demo-user",
        "demo_auth_password": "demo-password",
        "demo_session_secret": "test-session-secret-that-is-longer-than-32-characters",
        "demo_cookie_secure": False,
    })
    with pytest.raises(RuntimeError, match="outside local"):
        validate_demo_auth_config(settings)


def test_list_test_cases_matches_frontend_contract() -> None:
    response = client.get("/api/v1/test-cases")
    assert response.status_code == 200
    first = response.json()[0]
    assert {"id", "title", "group", "status", "passRate", "lastExecutedAt"} <= first.keys()


def test_structure_test_case() -> None:
    response = client.post("/api/v1/test-case-versions/current/structure", json={
        "title": "회원가입", "rawText": "회원가입하고 안전한 비밀번호를 입력한 뒤 대시보드를 확인한다.",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 0.68
    assert body["steps"][0]["note"] in "회원가입하고 안전한 비밀번호를 입력한 뒤 대시보드를 확인한다."
    assert body["assertions"][0]["expected"] in "회원가입하고 안전한 비밀번호를 입력한 뒤 대시보드를 확인한다."
    assert body["aiUsage"]["source"] == "RULE_BASED"
    assert body["aiUsage"]["callCount"] == 0
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["versionId"] != "00000000-0000-0000-0000-000000000501"

    approved = client.post(f'/api/v1/test-case-versions/{body["versionId"]}/approve')
    assert approved.status_code == 200
    assert approved.json() == {"versionId": body["versionId"], "status": "READY"}


def test_each_structure_creates_a_unique_review_version_and_unknown_approval_is_hidden() -> None:
    payload = {"title": "고유 버전", "rawText": "페이지에 접속하고 결과가 보이는지 확인한다."}
    first = client.post("/api/v1/test-case-versions/current/structure", json=payload)
    second = client.post("/api/v1/test-case-versions/current/structure", json=payload)
    unknown = client.post("/api/v1/test-case-versions/ffffffff-ffff-ffff-ffff-ffffffffffff/approve")
    assert first.json()["versionId"] != second.json()["versionId"]
    assert first.json()["status"] == second.json()["status"] == "REVIEW_REQUIRED"
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "TC_VERSION_NOT_FOUND"


def test_execution_plan_endpoint_returns_server_validated_contract() -> None:
    response = client.get(
        "/api/v1/test-case-versions/00000000-0000-0000-0000-000000000501/execution-plan",
        params={"environmentId": "00000000-0000-0000-0000-000000000301"},
    )
    assert response.status_code == 200
    assert response.json()["executable"] is True
    assert response.json()["steps"][0]["stepNo"] == 1
    assert response.json()["planHash"] == "a" * 64


def test_patch_review_step_returns_recalculated_plan() -> None:
    response = client.patch(
        "/api/v1/test-case-versions/00000000-0000-0000-0000-000000000501/steps/step-1",
        params={"environmentId": "00000000-0000-0000-0000-000000000301"},
        json={"url": "http://demo-target", "operator": "contains", "expected": "demo-target", "assertionType": "url"},
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert response.json()["planHash"] == "b" * 64


def test_structure_rejects_9613_character_multi_tc_import_for_review() -> None:
    rows = ["TC ID | 제목 | 단계"] + [
        f"TC-{index:03d} | KakaoGames 테스트 {index} | 실행 후 결과 확인"
        for index in range(1, 103)
    ]
    raw_text = "\n".join(rows)
    raw_text += "가" * (9_613 - len(raw_text))
    assert len(raw_text) == 9_613

    response = client.post("/api/v1/test-case-versions/current/structure", json={
        "title": "KakaoGames 102건",
        "rawText": raw_text,
    })

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "MULTIPLE_TEST_CASES_REVIEW_REQUIRED"
    assert body["retryable"] is False
    assert body["details"] == {
        "reviewStatus": "REVIEW_REQUIRED",
        "detectedTestCaseCount": 102,
        "rawTextLength": 9_613,
        "aiCallCount": 0,
    }


def test_import_txt_test_case() -> None:
    response = client.post(
        "/api/v1/test-cases/import",
        files={"file": ("login.txt", "로그인 페이지 접속\n아이디와 비밀번호 입력\n대시보드 확인".encode(), "text/plain")},
    )
    assert response.status_code == 200
    assert response.json() == {
        "fileName": "login.txt",
        "format": "txt",
        "title": "login",
        "rawText": "로그인 페이지 접속\n아이디와 비밀번호 입력\n대시보드 확인",
        "warnings": [],
    }


def test_import_docx_test_case() -> None:
    document = BytesIO()
    with ZipFile(document, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>상품을 장바구니에 담는다.</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>결제 버튼을 확인한다.</w:t></w:r></w:p></w:body></w:document>",
        )
    response = client.post(
        "/api/v1/test-cases/import",
        files={"file": ("checkout.docx", document.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 200
    assert response.json()["rawText"] == "상품을 장바구니에 담는다.\n결제 버튼을 확인한다."


def test_import_xlsx_test_case() -> None:
    workbook = BytesIO()
    with ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="TC" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            '<row><c t="inlineStr"><is><t>단계</t></is></c><c t="inlineStr"><is><t>기대결과</t></is></c></row>'
            '<row><c t="inlineStr"><is><t>로그인</t></is></c><c t="inlineStr"><is><t>대시보드 노출</t></is></c></row>'
            '</sheetData></worksheet>',
        )
    response = client.post(
        "/api/v1/test-cases/import",
        files={"file": ("login.xlsx", workbook.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    assert response.json()["rawText"] == "단계 | 기대결과\n로그인 | 대시보드 노출"


def test_import_xlsx_excludes_report_metadata_before_tc_table() -> None:
    workbook = BytesIO()
    rows = [
        ["Pass", "12"], ["Build Version", "2026.09"], ["담당자", "QA"],
        ["TC ID", "Test Steps", "Expected Result"],
        ["TC-001", "로그인 버튼 클릭", "대시보드 노출"],
        ["TC-002", "로그아웃 버튼 클릭", "로그인 화면 노출"],
    ]
    row_xml = "".join(
        "<row>" + "".join(f'<c t="inlineStr"><is><t>{cell}</t></is></c>' for cell in row) + "</row>"
        for row in rows
    )
    with ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            f'{row_xml}</sheetData></worksheet>',
        )
    response = client.post(
        "/api/v1/test-cases/import",
        files={"file": ("report.xlsx", workbook.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Pass" not in body["rawText"]
    assert "Build Version" not in body["rawText"]
    assert "Expected Result" in body["rawText"]
    assert "대시보드 노출" in body["rawText"]
    assert body["warnings"] == ["XLSX_METADATA_ROWS_EXCLUDED:3", "XLSX_TEST_CASES_DETECTED:2"]


def test_import_rejects_unsupported_or_large_file() -> None:
    unsupported = client.post("/api/v1/test-cases/import", files={"file": ("case.pdf", b"pdf", "application/pdf")})
    too_large = client.post("/api/v1/test-cases/import", files={"file": ("case.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")})
    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    assert too_large.status_code == 413
    assert too_large.json()["code"] == "FILE_TOO_LARGE"


def test_execution_resources_hide_secrets_and_expose_policy() -> None:
    environments = client.get("/api/v1/environments")
    accounts = client.get("/api/v1/test-accounts")
    policy = client.get("/api/v1/execution-policies/current")
    assert environments.status_code == accounts.status_code == policy.status_code == 200
    assert environments.json()[0]["defaultViewport"] == "1440x900"
    assert accounts.json()[0] == {
        "id": "00000000-0000-0000-0000-000000000601",
        "name": "qa-runner-01",
        "status": "AVAILABLE",
    }
    assert "secretRef" not in accounts.json()[0]
    assert policy.json()["supportedBrowsers"] == ["Chromium"]
    assert policy.json()["maxAiCalls"] == 0


def test_ai_settings_fail_closed_without_api_key() -> None:
    missing_key = Settings(
        ai_enabled=True,
        ai_max_calls_per_run=1,
        ai_daily_budget_usd="1",
        openai_api_key="",
    )
    configured = Settings(
        ai_enabled=True,
        ai_max_calls_per_run=1,
        ai_daily_budget_usd="1",
        openai_api_key="test-key-not-used",
    )
    assert missing_key.ai_ready is False
    assert configured.ai_ready is True
    assert "test-key-not-used" not in repr(configured)


def test_execution_requires_idempotency_key() -> None:
    payload = {
        "testCaseVersionId": "00000000-0000-0000-0000-000000000501", "environmentId": "00000000-0000-0000-0000-000000000301",
        "browser": "Chromium", "accountId": "00000000-0000-0000-0000-000000000601", "viewport": "1440x900", "locale": "ko-KR",
        "limits": {"timeoutMinutes": 15, "maxAiCalls": 20, "retryCount": 2}, "requireRiskApproval": True,
    }
    response = client.post("/api/v1/executions", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_execution_idempotency() -> None:
    payload = {
        "testCaseVersionId": "00000000-0000-0000-0000-000000000501", "environmentId": "00000000-0000-0000-0000-000000000301",
        "browser": "Chromium", "accountId": "00000000-0000-0000-0000-000000000601", "viewport": "1440x900", "locale": "ko-KR",
        "limits": {"timeoutMinutes": 15, "maxAiCalls": 20, "retryCount": 2}, "requireRiskApproval": True,
    }
    headers = {"Idempotency-Key": "test-execution-1"}
    first = client.post("/api/v1/executions", json=payload, headers=headers)
    second = client.post("/api/v1/executions", json=payload, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]


def test_execution_get_and_cancel() -> None:
    execution = ExecutionResponse(
        id="00000000-0000-0000-0000-000000000701", status="RUNNING",
        testCaseVersionId="00000000-0000-0000-0000-000000000501", queuedAt=datetime.now(UTC),
    )
    FakeExecutionRepository.ids["existing"] = execution
    fetched = client.get(f"/api/v1/executions/{execution.id}")
    cancelled = client.post(f"/api/v1/executions/{execution.id}/cancel")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "RUNNING"
    assert cancelled.status_code == 202
    assert cancelled.json()["execution"]["status"] == "CANCEL_REQUESTED"


def test_execution_details_exposes_steps_and_artifacts() -> None:
    execution = ExecutionResponse(
        id="00000000-0000-0000-0000-000000000701", status="PASS",
        testCaseVersionId="00000000-0000-0000-0000-000000000501", queuedAt=datetime.now(UTC),
    )
    FakeExecutionRepository.ids["details"] = execution
    response = client.get(f"/api/v1/executions/{execution.id}/details")
    assert response.status_code == 200
    assert response.json()["result"]["stepCount"] == 1
    assert response.json()["steps"][0]["action"]["type"] == "navigate"


def test_execution_events_close_after_terminal_status() -> None:
    execution = ExecutionResponse(
        id="00000000-0000-0000-0000-000000000701", status="PASS",
        testCaseVersionId="00000000-0000-0000-0000-000000000501", queuedAt=datetime.now(UTC),
    )
    FakeExecutionRepository.ids["events"] = execution
    response = client.get(f"/api/v1/executions/{execution.id}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: execution.updated" in response.text
    assert "event: execution.completed" in response.text


def test_execution_artifact_download(monkeypatch) -> None:
    execution = ExecutionResponse(
        id="00000000-0000-0000-0000-000000000701", status="FAIL",
        testCaseVersionId="00000000-0000-0000-0000-000000000501", queuedAt=datetime.now(UTC),
    )
    FakeExecutionRepository.ids["artifact"] = execution

    async def fake_get(_self, _object_key):
        return b"png-content"

    monkeypatch.setattr("app.modules.executions.router.ArtifactStore.get", fake_get)
    response = client.get(
        f"/api/v1/executions/{execution.id}/artifacts/00000000-0000-0000-0000-000000000901"
    )
    assert response.status_code == 200
    assert response.content == b"png-content"
    assert response.headers["etag"] == "a" * 64


def test_execution_retry_requires_terminal_state() -> None:
    execution = ExecutionResponse(
        id="00000000-0000-0000-0000-000000000701", status="RUNNING",
        testCaseVersionId="00000000-0000-0000-0000-000000000501", queuedAt=datetime.now(UTC),
    )
    FakeExecutionRepository.ids["existing"] = execution
    response = client.post(
        f"/api/v1/executions/{execution.id}/retry",
        headers={"Idempotency-Key": "retry-1"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "EXECUTION_STATE_CONFLICT"


def test_validation_error_uses_standard_envelope() -> None:
    response = client.get("/api/v1/executions/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["requestId"]


def test_invalid_request_id_is_replaced_with_uuid() -> None:
    response = client.get("/health", headers={"X-Request-ID": "not-a-uuid"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "not-a-uuid"


def test_execution_request_digest_is_stable() -> None:
    payload = CreateExecutionRequest.model_validate({
        "testCaseVersionId": "00000000-0000-0000-0000-000000000501",
        "environmentId": "00000000-0000-0000-0000-000000000301",
        "browser": "Chromium",
        "accountId": "00000000-0000-0000-0000-000000000601",
        "viewport": "1440x900",
        "locale": "ko-KR",
        "limits": {"timeoutMinutes": 15, "maxAiCalls": 20, "retryCount": 2},
        "requireRiskApproval": True,
    })
    assert SqlExecutionRepository._request_digest(payload) == SqlExecutionRepository._request_digest(payload.model_copy())
    assert len(SqlExecutionRepository._request_digest(payload)) == 64


def test_required_database_models_are_registered() -> None:
    assert len(Base.metadata.tables) == 15


def test_execution_resource_ids_require_real_uuids() -> None:
    with pytest.raises(ExecutionRuleError):
        SqlExecutionRepository._resolve_id("tcv-new-v1")


class CaptureScalarSession:
    def __init__(self):
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return None


@pytest.mark.asyncio
async def test_version_approval_query_enforces_organization_and_project_scope() -> None:
    session = CaptureScalarSession()
    repository = SqlTestCaseRepository(
        session,
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000201"),
    )
    with pytest.raises(VersionRuleError, match="찾을 수 없습니다"):
        await repository.approve(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    query = str(session.statements[0])
    assert "test_case_versions.organization_id" in query
    assert "test_cases.organization_id" in query
    assert "test_cases.project_id" in query


@pytest.mark.asyncio
async def test_execution_version_query_enforces_organization_and_project_scope() -> None:
    session = CaptureScalarSession()
    repository = SqlExecutionRepository(
        session,
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000201"),
        UUID("00000000-0000-0000-0000-000000000101"),
        UUID("00000000-0000-0000-0000-000000000999"),
    )
    with pytest.raises(ExecutionRuleError, match="찾을 수 없습니다"):
        await repository._validate_resources(
            UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            UUID("00000000-0000-0000-0000-000000000301"),
            None,
        )
    query = str(session.statements[0])
    assert "test_case_versions.organization_id" in query
    assert "test_cases.organization_id" in query
    assert "test_cases.project_id" in query


def test_worker_parses_viewport_and_blocks_unknown_domains() -> None:
    assert _parse_viewport("1440x900") == {"width": 1440, "height": 900}
    _assert_allowed_url("http://demo-target", ["demo-target"])
    with pytest.raises(WorkerExecutionError, match="허용되지 않은"):
        _assert_allowed_url("https://example.com", ["demo-target"])


def _plan_version(steps):
    return SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000501"),
        status="READY",
        structured_spec={"steps": steps, "planRevision": 2, "source": "RULE_BASED"},
    )


def _plan_environment():
    return SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000301"),
        name="Staging", base_url="http://demo-target", allowed_domains=["demo-target"],
    )


def test_execution_plan_validates_parameters_hash_and_masks_values() -> None:
    plan = validate_execution_plan(_plan_version([
        {"id": "step-1", "title": "진입", "action": "navigate"},
        {"id": "step-2", "title": "입력", "action": "fill", "selector": "#email", "value": "private", "timeoutMs": 5000},
        {"id": "step-3", "title": "클릭", "action": "click", "selector": "#submit"},
        {"id": "step-4", "title": "확인", "action": "assert", "selector": "#welcome", "operator": "contains", "expected": "환영"},
    ]), _plan_environment())
    assert plan.revision == 2
    assert len(plan.plan_hash) == 64
    assert plan.steps[0]["url"] == "http://demo-target"
    assert plan.public_steps[1]["value"] == "***"
    assert plan.steps[1]["value"] == "private"


def test_url_assertion_does_not_require_selector() -> None:
    plan = validate_execution_plan(_plan_version([
        {"id": "url-check", "title": "URL 확인", "action": "assert", "assertionType": "url", "url": "http://demo-target/dashboard", "operator": "contains", "expected": "/dashboard"},
    ]), _plan_environment())
    assert plan.steps[0]["selector"] is None
    assert plan.steps[0]["assertionType"] == "url"


def test_text_assertion_error_includes_step_and_missing_field() -> None:
    with pytest.raises(ExecutionPlanError) as raised:
        validate_execution_plan(_plan_version([
            {"id": "result-check", "title": "결과 확인", "action": "assert", "assertionType": "text", "operator": "contains", "expected": "완료"},
        ]), _plan_environment())
    assert raised.value.step_no == 1
    assert raised.value.step_id == "result-check"
    assert raised.value.missing_fields == ["selector"]


@pytest.mark.parametrize(("step","code"), [
    ({"id": "step-1", "title": "입력", "action": "fill", "selector": "#email"}, "STEP_PARAMETER_MISSING"),
    ({"id": "step-1", "title": "대기", "action": "wait"}, "UNSUPPORTED_ACTION"),
    ({"id": "step-1", "title": "외부", "action": "navigate", "url": "https://example.com"}, "TARGET_URL_NOT_ALLOWED"),
])
def test_execution_plan_rejects_invalid_steps(step, code) -> None:
    with pytest.raises(ExecutionPlanError) as raised:
        validate_execution_plan(_plan_version([step]), _plan_environment())
    assert raised.value.code == code
    assert raised.value.step_no == 1


def test_worker_blocks_changed_execution_plan_snapshot() -> None:
    plan = validate_execution_plan(_plan_version([
        {"id": "step-1", "title": "진입", "action": "navigate"},
    ]), _plan_environment())
    execution = SimpleNamespace(settings={"executionPlan": {
        "hash": "changed", "revision": plan.revision, "stepCount": 1,
        "environmentId": plan.environment["id"],
    }})
    with pytest.raises(WorkerExecutionError) as raised:
        _assert_plan_snapshot(execution, plan)
    assert raised.value.code == "EXECUTION_PLAN_INVALID"


class FakeResponse:
    status = 200


class FakeLocator:
    def __init__(self):
        self.filled = None
        self.clicked = False

    async def fill(self, value, **_kwargs):
        self.filled = value

    async def click(self, **_kwargs):
        self.clicked = True


class FakePage:
    def __init__(self):
        self.url = None
        self.locators = {}

    async def goto(self, url, **_kwargs):
        self.url = url
        return FakeResponse()

    def locator(self, selector):
        return self.locators.setdefault(selector, FakeLocator())


@pytest.mark.asyncio
async def test_step_executor_runs_navigate_fill_and_click() -> None:
    page = FakePage()
    await execute_step(page, {"action": "navigate"}, "http://demo-target")
    fill = await execute_step(page, {"action": "fill", "selector": "#email", "value": "qa@example.test"}, "http://demo-target")
    await execute_step(page, {"action": "click", "selector": "#submit"}, "http://demo-target")
    assert page.url == "http://demo-target"
    assert page.locators["#email"].filled == "qa@example.test"
    assert page.locators["#submit"].clicked is True
    assert fill.action["value"] == "***"


@pytest.mark.asyncio
async def test_step_executor_rejects_incomplete_or_unknown_steps() -> None:
    page = FakePage()
    with pytest.raises(StepDefinitionError, match="selector"):
        await execute_step(page, {"action": "fill", "value": "secret"}, "http://demo-target")
    with pytest.raises(StepDefinitionError, match="지원하지 않는 action"):
        await execute_step(page, {"action": "upload", "selector": "#file"}, "http://demo-target")
