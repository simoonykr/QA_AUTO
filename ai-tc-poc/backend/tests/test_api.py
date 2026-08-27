from fastapi.testclient import TestClient
from app.main import app


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


def test_execution_requires_idempotency_key() -> None:
    payload = {
        "testCaseVersionId": "tcv-new-v1", "environmentId": "env-staging",
        "browser": "Chromium", "accountId": "qa-runner-01", "viewport": "1440x900", "locale": "ko-KR",
        "limits": {"timeoutMinutes": 15, "maxAiCalls": 20, "retryCount": 2}, "requireRiskApproval": True,
    }
    response = client.post("/api/v1/executions", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_execution_idempotency() -> None:
    payload = {
        "testCaseVersionId": "tcv-new-v1", "environmentId": "env-staging",
        "browser": "Chromium", "accountId": "qa-runner-01", "viewport": "1440x900", "locale": "ko-KR",
        "limits": {"timeoutMinutes": 15, "maxAiCalls": 20, "retryCount": 2}, "requireRiskApproval": True,
    }
    headers = {"Idempotency-Key": "test-execution-1"}
    first = client.post("/api/v1/executions", json=payload, headers=headers)
    second = client.post("/api/v1/executions", json=payload, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
