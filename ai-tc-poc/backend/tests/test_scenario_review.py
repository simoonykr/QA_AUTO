from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from app.core.errors import DomainError
from app.db.models import TestCaseVersion as Version
from app.modules.discoveries.page_first import (build_scenario_candidates, compare_candidate_coverage,
    coverage_summary, feature_inventory, safe_state_candidate, scenario_payload, page_fingerprint)
from app.modules.discoveries.review import (extract, compare, apply_selections, ReviewRequest, Selection,
    selected_steps, editable, approve, RevisionRequest)
from app.modules.test_cases.execution_plan import validate_execution_plan, ExecutionPlanError


def fixture_payload():
    element = {"elementId": "e1", "selector": '[data-testid="menu"]', "name": "메뉴", "matchCount": 1, "visible": True, "enabled": True}
    result = {"elements": [element], "pages": [{"url": "https://example.test", "fingerprint": "abc"}], "fingerprint": "abc"}
    discovery = NS(id=uuid4(), result=result, status="COMPLETED", ended_at=datetime.now(UTC), environment_id=uuid4())
    return scenario_payload(discovery), discovery


def test_extraction_filters_report_fields_without_ai():
    result = extract("KG-WEB-001\nResult: Not Test\nBTS ID: bug\nComment: x\nSource: y\n대상: 게임\n메뉴 클릭\n메뉴 표시 확인")
    assert result["target"] == "게임"
    assert result["actions"] == ["메뉴 클릭"]
    assert result["expectedResults"] == ["메뉴 표시 확인"]
    assert result["aiCallCount"] == 0


def test_comparison_does_not_invent_matches_for_actions():
    payload, _ = fixture_payload()
    rows = compare(payload, extract("메뉴 클릭\n다른 요구사항\n결제 완료"))
    assert [r["result"] for r in rows] == ["CONFLICT", "TC_ONLY", "NOT_AUTOMATABLE", "PAGE_ONLY"]
    assert all(r["decision"] == "PENDING" for r in rows)


def test_exact_visible_match_and_revision_conflict():
    payload, _ = fixture_payload()
    payload["comparisons"] = compare(payload, extract("메뉴 표시 확인"))
    assert payload["comparisons"][0]["result"] == "MATCHED"
    changed = apply_selections(payload, ReviewRequest(expectedRevision=1, selections=[Selection(comparisonId="comparison-1", decision="ADD")]))
    assert changed["revision"] == 2 and payload["revision"] == 1
    assert len(selected_steps(changed)) == 1
    with pytest.raises(DomainError) as e:
        editable(changed, 1)
    assert e.value.code == "SCENARIO_REVISION_CONFLICT"


@pytest.mark.parametrize("decision", ["ADD", "IGNORE"])
def test_unverified_add_cannot_be_enabled_by_wording_edit(decision):
    payload, _ = fixture_payload()
    payload["comparisons"] = compare(payload, extract("결제 완료"))
    with pytest.raises(DomainError) as e:
        apply_selections(payload, ReviewRequest(expectedRevision=1, selections=[Selection(
            comparisonId="comparison-1", decision=decision, draft="메뉴 표시 확인")]))
    assert e.value.code == "COMPARISON_EVIDENCE_REQUIRED"


def test_pending_and_empty_plan_block_approval():
    payload, _ = fixture_payload()
    payload["comparisons"] = compare(payload, extract("메뉴 표시 확인"))
    with pytest.raises(DomainError):
        selected_steps(payload)
    payload["comparisons"][0]["decision"] = "MANUAL"
    with pytest.raises(DomainError) as e:
        selected_steps(payload)
    assert e.value.code == "SCENARIO_EMPTY"


@pytest.mark.asyncio
async def test_approval_creates_ready_version_once_and_validates_environment():
    payload, discovery = fixture_payload()
    payload["comparisons"] = compare(payload, extract("메뉴 표시 확인"))
    payload = apply_selections(payload, ReviewRequest(expectedRevision=1, selections=[Selection(comparisonId="comparison-1", decision="ADD")]))
    item = NS(id=uuid4(), payload=payload, discovery_id=discovery.id, organization_id=uuid4(), project_id=uuid4())
    env = NS(id=discovery.environment_id, base_url="https://example.test", name="Staging", allowed_domains=["example.test"])

    class Session:
        def __init__(self):
            self.values = [item, discovery, env, item]
            self.added = []
        async def scalar(self, query):
            assert "organization_id" in str(query) and "project_id" in str(query)
            return self.values.pop(0)
        def add(self, value):
            self.added.append(value)
        async def commit(self):
            pass

    session = Session()
    request = NS(state=NS(request_id=str(uuid4())))
    result = await approve(item.id, RevisionRequest(expectedRevision=2), request, session)
    assert result["status"] == "READY" and result["executable"]
    again = await approve(item.id, RevisionRequest(expectedRevision=2), request, session)
    assert again["versionId"] == result["versionId"]
    versions = [v for v in session.added if isinstance(v, Version)]
    assert len(versions) == 1
    plan = validate_execution_plan(versions[0], env)
    assert [s["action"] for s in plan.steps] == ["navigate", "assert"]
    assert plan.revision == 2
    with pytest.raises(ExecutionPlanError):
        validate_execution_plan(versions[0], NS(id=uuid4()))
    with pytest.raises(DomainError):
        editable(item.payload, 2)


def test_fingerprint_changes_when_observed_state_changes():
    elements = [{"name": "menu", "visible": True}]
    original = page_fingerprint("https://example.test", elements)
    elements[0]["visible"] = False
    assert page_fingerprint("https://example.test", elements) != original


def test_semantic_metadata_does_not_invalidate_legacy_fingerprint():
    element = {"elementId": "e1", "selector": '[data-testid="menu"]', "name": "menu",
        "matchCount": 1, "visible": True, "enabled": True}
    original = page_fingerprint("https://example.test", [element])
    enriched = {**element, "role": "button", "areaKind": "navigation", "areaName": "Main",
        "interactable": True}
    assert page_fingerprint("https://example.test", [enriched]) == original
    areas, interactions = feature_inventory([enriched])
    assert areas == [{"id": "area-1", "kind": "navigation", "name": "Main", "elementIds": ["e1"]}]
    assert interactions[0]["selector"] == element["selector"]


def test_state_observation_rejects_forms_and_dangerous_controls():
    base = {"interactable": True, "role": "tab", "ariaSelected": "false", "insideForm": False}
    assert safe_state_candidate({**base, "name": "PC"})
    assert not safe_state_candidate({**base, "name": "Delete account"})
    assert not safe_state_candidate({**base, "name": "PC", "insideForm": True})
    assert not safe_state_candidate({**base, "name": "PC", "interactable": False})


def test_interaction_ids_reference_observed_elements():
    element = {"elementId": "element-7", "selector": '[data-testid="pc"]', "name": "PC",
        "matchCount": 1, "visible": True, "enabled": True, "interactable": True,
        "role": "tab", "areaKind": "main", "areaName": "Filters"}
    _, interactions = feature_inventory([element])
    assert interactions[0]["id"] == "interaction-1"
    assert interactions[0]["elementId"] == "element-7"


def test_observed_state_change_creates_deduplicated_function_candidate_and_coverage():
    areas = [{"id": "area-1", "kind": "main", "name": "전체게임 필터", "elementIds": ["element-7"]}]
    interactions = [{"id": "interaction-1", "areaId": "area-1", "elementId": "element-7",
        "kind": "button", "name": "#모바일", "selector": 'role=button[name="#모바일"]',
        "enabled": True, "risk": "READ_ONLY_CANDIDATE", "source": "PAGE_DISCOVERY"}]
    change = {"id": "state-change-1", "interactionId": "interaction-1",
        "before": {"url": "https://example.test", "ariaPressed": "false", "ariaSelected": None, "checked": None},
        "after": {"url": "https://example.test", "ariaPressed": "true", "ariaSelected": None, "checked": None},
        "source": "PLAYWRIGHT_OBSERVED"}
    candidates = build_scenario_candidates(areas, interactions, [change, change])
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["steps"][0] == {"action": "click", "interactionId": "interaction-1",
        "selector": 'role=button[name="#모바일"]'}
    assert candidate["steps"][1]["assertion"]["changedFields"] == ["ariaPressed"]
    assert candidate["evidence"] == {"elementIds": ["element-7"], "interactionIds": ["interaction-1"],
        "stateChangeIds": ["state-change-1"]}
    assert candidate["automationStatus"] == "MANUAL_REVIEW_REQUIRED"
    assert coverage_summary(candidates)["MISSING_IN_TC"] == 1

    partial = compare_candidate_coverage(candidates, {"actions": ["#모바일 클릭"], "expectedResults": []})
    assert partial[0]["coverage"] == "PARTIAL"
    covered = compare_candidate_coverage(candidates, {
        "actions": ["#모바일 클릭"], "expectedResults": ["모바일 필터 선택 후 게임 목록 변경 확인"]})
    assert covered[0]["coverage"] == "COVERED"


def test_unobserved_or_unknown_interaction_never_creates_candidate():
    assert build_scenario_candidates([], [], [{"interactionId": "missing", "source": "PLAYWRIGHT_OBSERVED"}]) == []
    assert build_scenario_candidates([], [{"id": "i1"}], [{"interactionId": "i1", "source": "AI"}]) == []


def test_empty_or_table_tc_is_rejected():
    for raw, code in [("Result: Not Test", "TC_EMPTY"), ("a | b", "TC_TABLE_REQUIRES_IMPORT")]:
        with pytest.raises(DomainError) as error:
            extract(raw)
        assert error.value.code == code


def test_page_only_scenario_requires_review_without_tc():
    payload, _ = fixture_payload()
    assert len(payload["comparisons"]) == len(payload["steps"]) == 1
    assert payload["comparisons"][0]["result"] == "PAGE_ONLY"
    with pytest.raises(DomainError) as error:
        selected_steps(payload)
    assert error.value.code == "SCENARIO_REVIEW_REQUIRED"
    reviewed = apply_selections(payload, ReviewRequest(expectedRevision=1,
        selections=[Selection(comparisonId="comparison-1", decision="ADD")]))
    assert selected_steps(reviewed) == payload["steps"]
    assert reviewed["revision"] == 2 and not reviewed["executable"]


def test_tc_comparison_replaces_initial_page_review():
    payload, _ = fixture_payload()
    payload = apply_selections(payload, ReviewRequest(expectedRevision=1,
        selections=[Selection(comparisonId="comparison-1", decision="ADD")]))
    rows = compare(payload, extract("메뉴 표시 확인"))
    assert len(rows) == 1 and rows[0]["result"] == "MATCHED"
    assert rows[0]["decision"] == "PENDING"


def test_http_compare_review_revision_and_response_contract(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app, settings
    from app.core.database import get_session
    payload, discovery = fixture_payload()
    item = NS(id=uuid4(), payload=payload, discovery_id=discovery.id,
        organization_id=uuid4(), project_id=uuid4())
    item.payload["scenarioId"] = str(item.id)
    class Session:
        commits = 0
        async def scalar(self, query):
            assert "organization_id" in str(query) and "project_id" in str(query)
            return item
        def add(self, event):
            assert event.metadata_json["snapshot"]["revision"] >= 2
        async def commit(self):
            self.commits += 1
    session = Session()
    async def dependency():
        yield session
    monkeypatch.setattr(settings, "demo_auth_enabled", False)
    monkeypatch.setitem(app.dependency_overrides, get_session, dependency)
    with TestClient(app) as client:
        path = f"/api/v1/page-scenarios/{item.id}"
        response = client.post(path + "/compare", json={"expectedRevision": 1, "rawText": "메뉴 표시 확인"})
        assert response.status_code == 200
        assert response.json()["revision"] == 2
        assert response.json()["comparisons"][0]["result"] == "MATCHED"
        assert response.json()["extractedTestCase"]["aiCallCount"] == 0
        request = {"expectedRevision": 2, "selections": [{"comparisonId": "comparison-1", "decision": "ADD"}]}
        saved = client.patch(path + "/review", json=request)
        assert saved.status_code == 200 and saved.json()["revision"] == 3
        assert saved.json()["executable"] is False
        stale = client.patch(path + "/review", json=request)
        assert stale.status_code == 409
        assert stale.json()["code"] == "SCENARIO_REVISION_CONFLICT"
        assert stale.json()["requestId"] == stale.headers["x-request-id"]
        assert stale.json()["retryable"] is False
        latest = client.get(path)
        assert latest.status_code == 200 and latest.json() == saved.json()
        assert session.commits == 2


def test_http_scenario_routes_require_authentication(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app, settings
    monkeypatch.setattr(settings, "demo_auth_enabled", True)
    with TestClient(app) as client:
        for method, path in [("post", "/test-cases/extract"),
            ("post", f"/page-scenarios/{uuid4()}/compare"),
            ("patch", f"/page-scenarios/{uuid4()}/review"),
            ("post", f"/page-scenarios/{uuid4()}/approve")]:
            response = getattr(client, method)("/api/v1" + path, json={})
            assert response.status_code == 401
            assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_worker_verifies_live_fingerprint_without_browser_or_network(monkeypatch):
    from app.modules.discoveries import page_first
    from app.workers.playwright_worker import _verify_page_first_snapshot, WorkerExecutionError
    elements = [{"visible": True}]
    async def collect(page):
        return elements
    monkeypatch.setattr(page_first, "collect_elements", collect)
    page = NS(url="https://example.test")
    snapshot = {"fingerprint": page_fingerprint(page.url, elements)}
    await _verify_page_first_snapshot(page, snapshot)
    elements[0]["visible"] = False
    with pytest.raises(WorkerExecutionError) as error:
        await _verify_page_first_snapshot(page, snapshot)
    assert error.value.code == "DISCOVERY_STALE"


@pytest.mark.asyncio
async def test_stale_discovery_cannot_be_approved():
    from datetime import timedelta
    payload, discovery = fixture_payload()
    payload["comparisons"] = compare(payload, extract("메뉴 표시 확인"))
    payload["comparisons"][0]["decision"] = "ADD"
    discovery.ended_at -= timedelta(minutes=31)
    item = NS(payload=payload, discovery_id=discovery.id, organization_id=uuid4(), project_id=uuid4())
    class Session:
        values = [item, discovery]
        async def scalar(self, query):
            return self.values.pop(0)
        async def commit(self):
            pytest.fail("stale discovery must not commit")
    with pytest.raises(DomainError) as error:
        await approve(uuid4(), RevisionRequest(expectedRevision=1), None, Session())
    assert error.value.code == "DISCOVERY_STALE"
