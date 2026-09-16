"""Deterministic TC comparison, optimistic review revisions and atomic approval."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import re
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import DomainError
from app.db.models import Environment, PageDiscovery, PageScenario, TestCase, TestCaseVersion
from app.modules.discoveries.page_first import (scope, audit, allowed_url, compare_candidate_coverage,
    coverage_summary, ScenarioResponse)
from app.modules.test_cases.execution_plan import validate_execution_plan

router = APIRouter(tags=["scenario-review"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractRequest(StrictRequest):
    rawText: str = Field(min_length=1, max_length=50000)


class RevisionRequest(StrictRequest):
    expectedRevision: int = Field(ge=1)


class CompareRequest(RevisionRequest):
    rawText: str = Field(min_length=1, max_length=50000)


class Selection(StrictRequest):
    comparisonId: str
    decision: Literal["PENDING", "ADD", "MANUAL", "EXCLUDE", "IGNORE"]
    draft: str | None = Field(default=None, min_length=1, max_length=2000)


class ReviewRequest(RevisionRequest):
    selections: list[Selection] = Field(min_length=1, max_length=200)


def extract(raw: str) -> dict:
    target, actions, expected = [], [], []
    for line in raw.splitlines():
        text = line.strip()
        if not text or re.match(r"^(?:TC ID|Result(?:\([^)]*\))?|BTS(?: ID)?|Comment|Source|Not Test)\s*(?:[:：|]|$)", text, re.I):
            continue
        if re.fullmatch(r"(?:[A-Z]+-)*(?:WEB-|TC-)?\d+", text):
            continue
        if "|" in text:
            raise DomainError("TC_TABLE_REQUIRES_IMPORT", "표는 파일 가져오기로 TC별 분리 후 전송해 주세요.", 422)
        if re.match(r"^(?:대상|target|url|전제조건|precondition)\s*[:：]", text, re.I):
            target.append(re.split(r"[:：]", text, maxsplit=1)[1].strip())
        elif re.search(r"클릭|입력|선택|접속|이동|\b(click|fill|navigate|press)\b", text, re.I):
            actions.append(text)
        else:
            expected.append(text)
    if not any(target + actions + expected):
        raise DomainError("TC_EMPTY", "비교할 TC 내용을 입력해 주세요.", 422)
    if len(actions) + len(expected) + len(target) > 200:
        raise DomainError("TC_TOO_MANY_ITEMS", "TC 요구사항은 200개 이하로 분리해 주세요.", 422)
    return {"target": "\n".join(target), "actions": actions, "expectedResults": expected,
            "source": "RULE_BASED", "aiCallCount": 0}


def compare(payload: dict, extracted: dict) -> list[dict]:
    rows, matched = [], set()
    clauses = ([extracted["target"]] if extracted["target"] else []) + extracted["actions"] + extracted["expectedResults"]
    for text in clauses:
        # Only exact visibility statements can count as verified matches.
        candidates = [s for s in payload["steps"] if s["targetDescription"] and s["targetDescription"] in text]
        step = candidates[0] if len(candidates) == 1 else None
        visible = step and text.strip() in {f'{step["targetDescription"]} 표시', f'{step["targetDescription"]} 표시 확인', f'{step["targetDescription"]} is visible'}
        unsupported = bool(re.search(r"삭제|결제|게시|업로드|자연스럽|보기 좋|디자인|\b(delete|payment|upload)\b", text, re.I))
        visible = visible and not unsupported
        status = "NOT_AUTOMATABLE" if unsupported else "MATCHED" if visible else "CONFLICT" if candidates else "TC_ONLY"
        if visible:
            matched.add(step["id"])
        rows.append({"id": f"comparison-{len(rows)+1}", "result": status, "text": text, "draft": text,
            "decision": "PENDING", "stepId": step["id"] if visible else None,
            "source": "TEST_CASE", "evidence": "페이지 표시 근거 일치" if visible else "업무 기대 결과는 자동 확정하지 않았습니다."})
    for step in payload["steps"]:
        if step["id"] not in matched:
            rows.append({"id": f"comparison-{len(rows)+1}", "result": "PAGE_ONLY", "text": step["targetDescription"],
                "draft": step["targetDescription"], "decision": "PENDING", "stepId": step["id"],
                "source": "PAGE_DISCOVERY", "evidence": "실제 표시된 페이지 요소"})
    if len(rows) > 200:
        raise DomainError("COMPARISON_TOO_LARGE", "비교 항목을 200개 이하로 줄여 주세요.", 422)
    return rows


async def scenario(session, scenario_id, lock=False):
    org, project = scope()
    query = select(PageScenario).where(PageScenario.id == scenario_id,
        PageScenario.organization_id == org, PageScenario.project_id == project)
    item = await session.scalar(query.with_for_update() if lock else query)
    if not item:
        raise DomainError("SCENARIO_NOT_FOUND", "시나리오를 찾을 수 없습니다.", 404)
    return item


def check_revision(payload, expected):
    if payload["revision"] != expected:
        raise DomainError("SCENARIO_REVISION_CONFLICT", "최신 시나리오를 다시 조회해 주세요.", 409)


def editable(payload, expected):
    check_revision(payload, expected)
    if payload["status"] == "READY":
        raise DomainError("SCENARIO_ALREADY_APPROVED", "승인 버전은 변경할 수 없습니다. 새 시나리오를 생성해 주세요.", 409)


def selected_steps(payload):
    rows = payload.get("comparisons")
    if not rows or any(r["decision"] == "PENDING" for r in rows):
        raise DomainError("SCENARIO_REVIEW_REQUIRED", "모든 비교 항목의 검토 선택을 저장해 주세요.", 422)
    ids = {r["stepId"] for r in rows if r["decision"] in {"ADD", "IGNORE"} and r.get("stepId")}
    steps = [s for s in payload["steps"] if s["id"] in ids]
    if not steps:
        raise DomainError("SCENARIO_EMPTY", "실행할 검증 단계가 없습니다.", 422)
    return steps


def apply_selections(payload, body):
    editable(payload, body.expectedRevision)
    result = deepcopy(payload)
    rows = {row["id"]: row for row in result.get("comparisons", [])}
    if len({s.comparisonId for s in body.selections}) != len(body.selections):
        raise DomainError("DUPLICATE_SELECTION", "중복된 비교 항목입니다.", 422)
    for selection in body.selections:
        row = rows.get(selection.comparisonId)
        if not row:
            raise DomainError("COMPARISON_NOT_FOUND", "비교 항목을 찾을 수 없습니다.", 404)
        if selection.decision in {"ADD", "IGNORE"} and row["result"] not in {"MATCHED", "PAGE_ONLY"}:
            raise DomainError("COMPARISON_EVIDENCE_REQUIRED", "근거 없는 항목은 추가·무시할 수 없습니다. 제외 또는 수동 검증을 선택해 주세요.", 422)
        row["decision"] = selection.decision
        if selection.draft is not None:
            row["draft"] = selection.draft
            row["source"] = "MANUAL"
            # Wording changes never change assertion semantics or resolve a conflict.
    result["revision"] += 1
    result["executable"] = False
    return result


async def persist(session, item, payload, request, action):
    event = audit(item.organization_id, request, action, item.id)
    event.metadata_json = {"revision": payload["revision"], "snapshot": deepcopy(payload)}
    session.add(event)
    item.payload = payload
    await session.commit()
    return payload


@router.post("/test-cases/extract")
async def extract_tc(body: ExtractRequest):
    return extract(body.rawText)


@router.post("/page-scenarios/{scenario_id}/compare", response_model=ScenarioResponse)
async def compare_tc(scenario_id: UUID, body: CompareRequest, request: Request, session: AsyncSession = Depends(get_session)):
    item = await scenario(session, scenario_id, True)
    editable(item.payload, body.expectedRevision)
    payload = deepcopy(item.payload)
    payload["extractedTestCase"] = extract(body.rawText)
    payload["comparisons"] = compare(payload, payload["extractedTestCase"])
    payload["scenarioCandidates"] = compare_candidate_coverage(
        payload.get("scenarioCandidates", []), payload["extractedTestCase"])
    payload["coverage"] = coverage_summary(payload["scenarioCandidates"])
    payload["revision"] += 1
    payload["executable"] = False
    payload["warnings"] = [{"code": "SCENARIO_REVIEW_REQUIRED", "message": "모든 비교 항목을 검토해 주세요."}]
    return await persist(session, item, payload, request, "page_scenario.compared")


@router.patch("/page-scenarios/{scenario_id}/review", response_model=ScenarioResponse)
async def review(scenario_id: UUID, body: ReviewRequest, request: Request, session: AsyncSession = Depends(get_session)):
    item = await scenario(session, scenario_id, True)
    return await persist(session, item, apply_selections(item.payload, body), request, "page_scenario.reviewed")


@router.post("/page-scenarios/{scenario_id}/approve", response_model=ScenarioResponse)
async def approve(scenario_id: UUID, body: RevisionRequest, request: Request, session: AsyncSession = Depends(get_session)):
    item = await scenario(session, scenario_id, True)
    payload = deepcopy(item.payload)
    check_revision(payload, body.expectedRevision)
    if payload["status"] == "READY":
        return payload
    steps = selected_steps(payload)
    discovery = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == item.discovery_id,
        PageDiscovery.organization_id == item.organization_id, PageDiscovery.project_id == item.project_id))
    if not discovery or discovery.status != "COMPLETED" or not discovery.ended_at or discovery.ended_at < datetime.now(UTC) - timedelta(minutes=30):
        raise DomainError("DISCOVERY_STALE", "최근 30분 이내 페이지 분석으로 다시 생성해 주세요.", 409)
    environment = await session.scalar(select(Environment).where(Environment.id == discovery.environment_id,
        Environment.organization_id == item.organization_id, Environment.project_id == item.project_id))
    result = discovery.result or {}
    url = result["pages"][0]["url"]
    if not environment or not allowed_url(url, environment.allowed_domains):
        raise DomainError("TARGET_URL_NOT_ALLOWED", "실행 환경 URL을 확인해 주세요.", 422)
    elements = {e["elementId"]: e for e in result["elements"]}
    for step in steps:
        evidence = step["evidence"]
        element = elements.get(evidence["elementId"])
        if not element or element["matchCount"] != 1 or not element["visible"] or element["selector"] != step["selector"] or evidence["fingerprint"] != result["fingerprint"]:
            raise DomainError("SCENARIO_EVIDENCE_INVALID", "페이지 근거를 다시 확인해 주세요.", 422)
    case_id, version_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    spec = {"source": "RULE_BASED", "planRevision": payload["revision"],
        "automationStatus": "PARTIALLY_AUTOMATABLE", "automationReason": "QA가 선택한 표시 assertion만 실행합니다. 제외·수동 항목은 실행하지 않습니다.",
        "pageFirst": {"scenarioId": str(item.id), "revision": payload["revision"], "environmentId": str(environment.id),
            "fingerprint": result["fingerprint"], "url": url, "elements": result["elements"]},
        "steps": [{"id": "navigate", "action": "navigate", "title": "분석 페이지 접속", "url": url}] + [
            {"id": s["id"], "action": "assert", "title": s["targetDescription"], "selector": s["selector"],
                "assertionType": "element", "operator": "visible", "expected": "true", "resolutionStatus": "RESOLVED"}
            for s in steps]}
    version = TestCaseVersion(id=version_id, organization_id=item.organization_id, test_case_id=case_id,
        version_no=1, raw_text=payload["purpose"], structured_spec=spec, status="READY", created_at=now)
    validate_execution_plan(version, environment)
    session.add(TestCase(id=case_id, organization_id=item.organization_id, project_id=item.project_id,
        display_id=f"SC-{case_id}", title=payload["purpose"], group_name="Page scenarios", created_at=now))
    session.add(version)
    payload.update(status="READY", executable=True, versionId=str(version_id), environmentId=str(environment.id),
        automationStatus="PARTIALLY_AUTOMATABLE", warnings=[{"code": "PARTIAL_SCOPE", "message": "선택한 표시 검증만 실행합니다. 수동·제외 항목은 실행 범위 밖입니다."}])
    return await persist(session, item, payload, request, "page_scenario.approved")
