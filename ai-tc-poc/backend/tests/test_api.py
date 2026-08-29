from datetime import UTC, datetime
from types import SimpleNamespace
from fastapi.testclient import TestClient
import pytest

from app.core.database import get_session
from app.db.models import Base
from app.main import app
from app.modules.executions.repository import SqlExecutionRepository
from app.schemas.executions import CreateExecutionRequest, ExecutionDetailsResponse, ExecutionResponse
from app.schemas.test_cases import TestCaseSummary
from app.schemas.resources import EnvironmentSummary, TestAccountSummary
from app.workers.playwright_worker import WorkerExecutionError, _assert_allowed_url, _parse_viewport
from app.workers.step_executor import StepDefinitionError, execute_step


async def fake_session():
    yield object()


class FakeTestCaseRepository:
    def __init__(self, *_args):
        pass

    async def list(self):
        return [TestCaseSummary(id="TC-142", title="회원가입", group="Authentication", status="READY", passRate=96, lastExecutedAt="12분 전")]


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
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]


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
    assert body["confidence"] == 0.94
    assert len(body["steps"]) == 4
    assert len(body["assertions"]) == 2


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
    assert len(Base.metadata.tables) == 13


def test_frontend_poc_aliases_resolve_to_seed_uuids() -> None:
    assert str(SqlExecutionRepository._resolve_id("tcv-new-v1")) == "00000000-0000-0000-0000-000000000501"
    assert str(SqlExecutionRepository._resolve_id("env-staging")) == "00000000-0000-0000-0000-000000000301"
    assert str(SqlExecutionRepository._resolve_id("qa-runner-01")) == "00000000-0000-0000-0000-000000000601"


def test_worker_parses_viewport_and_blocks_unknown_domains() -> None:
    assert _parse_viewport("1440x900") == {"width": 1440, "height": 900}
    _assert_allowed_url("http://demo-target", ["demo-target"])
    with pytest.raises(WorkerExecutionError, match="허용되지 않은"):
        _assert_allowed_url("https://example.com", ["demo-target"])


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
