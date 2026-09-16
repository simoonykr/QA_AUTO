"""Independent page discovery and non-executable, evidence-backed scenario drafts."""
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.errors import DomainError
from app.db.models import AuditEvent, Environment, OutboxEvent, OutboxStatus, PageDiscovery, PageScenario

router = APIRouter(tags=["page-first"])


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environmentId: UUID
    startUrl: str = Field(min_length=1, max_length=2048)
    includeInternalLinks: bool = False
    maxDepth: int = Field(default=0, ge=0, le=2)
    maxPages: int = Field(default=1, ge=1, le=5)
    maxAiCalls: Literal[0] = 0


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maxAiCalls: Literal[0] = 0


class EvidenceStep(BaseModel):
    id: str
    action: Literal["assert"] = "assert"
    targetDescription: str
    selector: str
    assertion: dict
    source: Literal["PAGE_DISCOVERY"] = "PAGE_DISCOVERY"
    evidence: dict


class ScenarioResponse(BaseModel):
    scenarioId: UUID
    discoveryId: UUID
    revision: int = 1
    status: Literal["REVIEW_REQUIRED", "READY"] = "REVIEW_REQUIRED"
    purpose: str
    pages: list[dict]
    steps: list[EvidenceStep]
    automationStatus: str = "MANUAL_REVIEW_REQUIRED"
    warnings: list[dict]
    executable: bool = False
    aiUsage: dict
    comparisons: list[dict] = Field(default_factory=list)
    scenarioCandidates: list[dict] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)
    selectedCandidateIds: list[str] = Field(default_factory=list)
    extractedTestCase: dict | None = None
    versionId: str | None = None
    environmentId: str | None = None


def allowed_url(url: str, domains: list[str]) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme in {"http", "https"} and parsed.hostname in domains
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def allowed_resource_url(url: str, domains: list[str]) -> bool:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        return (parsed.scheme in {"http", "https"} and not parsed.username and not parsed.password
                and any(host == domain or host.endswith(f".{domain}") for domain in domains))
    except ValueError:
        return False


def internal_page_url(base_url: str, href: str, domains: list[str]) -> str | None:
    """Resolve a crawl candidate without widening the navigation allowlist."""
    try:
        parsed = urlsplit(urljoin(base_url, href))
        if re.search(r"(?:^|[-_/])(logout|log-out|signout|sign-out|delete|remove|checkout|payment|purchase|unsubscribe)(?:[-_/]|$)", parsed.path, re.I):
            return None
        normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))
        return normalized if not parsed.query and not parsed.fragment and allowed_url(normalized, domains) else None
    except ValueError:
        return None


def safe_text(value: str) -> str:
    value = value[:160]
    if re.search(r"@|\b(?:token|secret|password|bearer)\b|\d{3}[- ]?\d{3,4}[- ]?\d{4}", value, re.I):
        return ""
    return value


def scenario_payload(discovery: PageDiscovery) -> dict:
    result = discovery.result or {}
    candidates = result.get("scenarioCandidates") or build_scenario_candidates(
        result.get("areas", []), result.get("interactions", []), result.get("stateChanges", []))
    steps = []
    for element in result.get("elements", []):
        if not (element.get("matchCount") == 1 and element.get("visible") and element.get("selector")):
            continue
        steps.append({"id": f"step-{len(steps) + 1}", "action": "assert",
            "targetDescription": element.get("name") or element["elementId"],
            "selector": element["selector"], "assertion": {"type": "element", "operator": "visible", "expected": True},
            "source": "PAGE_DISCOVERY", "evidence": {"elementId": element["elementId"],
            "fingerprint": result["fingerprint"], "url": result["pages"][0]["url"], "observed": "visible"}})
    return {"scenarioId": str(uuid4()), "discoveryId": str(discovery.id), "revision": 1,
        "status": "REVIEW_REQUIRED", "purpose": "탐색 페이지의 검증된 요소 표시 확인",
        "pages": result.get("pages", []), "steps": steps[:50],
        "scenarioCandidates": candidates, "coverage": coverage_summary(candidates),
        "comparisons": [{"id": f"comparison-{index + 1}", "result": "PAGE_ONLY",
            "text": step["targetDescription"], "draft": step["targetDescription"],
            "decision": "PENDING", "stepId": step["id"], "source": "PAGE_DISCOVERY",
            "evidence": "실제 표시된 페이지 요소"} for index, step in enumerate(steps[:50])],
        "automationStatus": "MANUAL_REVIEW_REQUIRED", "executable": False,
        "warnings": [{"code": "SCENARIO_REVIEW_REQUIRED", "message": "페이지 표시 확인 초안입니다. 검토 선택 저장 후 승인해 주세요. TC 비교는 선택 사항입니다."}],
        "aiUsage": {"source": "RULE_BASED", "callCount": 0, "inputTokens": 0, "outputTokens": 0, "costUsd": "0"}}


def scope():
    settings = get_settings()
    return UUID(settings.default_organization_id), UUID(settings.default_project_id)


async def find_discovery(session, discovery_id):
    org, project = scope()
    item = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id,
        PageDiscovery.organization_id == org, PageDiscovery.project_id == project,
        PageDiscovery.test_case_version_id.is_(None)))
    if not item:
        raise DomainError("DISCOVERY_NOT_FOUND", "페이지 분석을 찾을 수 없습니다.", 404)
    return item


def audit(org, request, action, resource_id):
    return AuditEvent(organization_id=org, action=action, resource_type="page_first",
        resource_id=str(resource_id), request_id=UUID(request.state.request_id), metadata_json={})


@router.post("/page-discoveries", status_code=202)
async def start(body: StartRequest, request: Request, session: AsyncSession = Depends(get_session)):
    org, project = scope()
    environment = await session.scalar(select(Environment).where(Environment.id == body.environmentId,
        Environment.organization_id == org, Environment.project_id == project))
    if not environment:
        raise DomainError("ENVIRONMENT_NOT_FOUND", "실행 환경을 찾을 수 없습니다.", 404)
    if not allowed_url(body.startUrl, environment.allowed_domains):
        raise DomainError("TARGET_URL_NOT_ALLOWED", "허용 도메인의 인증정보·쿼리 없는 URL을 사용해 주세요.", 422)
    if (not body.includeInternalLinks and (body.maxPages != 1 or body.maxDepth != 0)) or (
        body.includeInternalLinks and body.maxDepth == 0
    ):
        raise DomainError("DISCOVERY_SCOPE_INVALID", "내부 페이지 탐색 여부와 깊이·페이지 수 범위를 확인해 주세요.", 422)
    item = PageDiscovery(id=uuid4(), organization_id=org, project_id=project,
        environment_id=environment.id, test_case_version_id=None, status="QUEUED",
        settings={"startUrl": body.startUrl, "includeInternalLinks": body.includeInternalLinks,
            "maxDepth": body.maxDepth, "maxPages": body.maxPages, "maxAiCalls": 0, "mode": "PAGE_FIRST"})
    session.add(item)
    session.add(OutboxEvent(organization_id=org, aggregate_type="page_discovery", aggregate_id=item.id,
        event_type="page_first.requested", payload={"discoveryId": str(item.id)}, status=OutboxStatus.PENDING,
        attempts=0, available_at=datetime.now(UTC)))
    session.add(audit(org, request, "page_first.requested", item.id))
    await session.commit()
    return {"discoveryId": str(item.id), "status": "QUEUED"}


@router.get("/page-discoveries/{discovery_id}")
async def get(discovery_id: UUID, session: AsyncSession = Depends(get_session)):
    item = await find_discovery(session, discovery_id)
    return {"discoveryId": str(item.id), "status": item.status, "errorCode": item.error_code,
            "pages": (item.result or {}).get("pages", []), "elements": (item.result or {}).get("elements", []),
            "areas": (item.result or {}).get("areas", []),
            "interactions": (item.result or {}).get("interactions", []),
            "stateChanges": (item.result or {}).get("stateChanges", []),
            "scenarioCandidates": (item.result or {}).get("scenarioCandidates", []),
            "coverage": (item.result or {}).get("coverage", coverage_summary([])),
            "warnings": (item.result or {}).get("warnings", []),
            "scope": {"includeInternalLinks": bool(item.settings.get("includeInternalLinks", False)),
                "maxDepth": int(item.settings.get("maxDepth", 0)), "maxPages": int(item.settings.get("maxPages", 1))},
            "aiUsage": {"source": "RULE_BASED", "callCount": 0}}


@router.post("/page-discoveries/{discovery_id}/scenarios", response_model=ScenarioResponse, status_code=201)
async def generate(discovery_id: UUID, body: ScenarioRequest, request: Request, session: AsyncSession = Depends(get_session)):
    discovery = await find_discovery(session, discovery_id)
    if discovery.status != "COMPLETED":
        raise DomainError("DISCOVERY_NOT_READY", "완료된 페이지 분석이 필요합니다.", 409)
    payload = scenario_payload(discovery)
    session.add(PageScenario(id=UUID(payload["scenarioId"]), organization_id=discovery.organization_id,
        project_id=discovery.project_id, discovery_id=discovery.id, payload=payload))
    session.add(audit(discovery.organization_id, request, "page_scenario.created", payload["scenarioId"]))
    await session.commit()
    return payload


@router.get("/page-scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(scenario_id: UUID, session: AsyncSession = Depends(get_session)):
    org, project = scope()
    item = await session.scalar(select(PageScenario).where(PageScenario.id == scenario_id,
        PageScenario.organization_id == org, PageScenario.project_id == project))
    if not item:
        raise DomainError("SCENARIO_NOT_FOUND", "시나리오를 찾을 수 없습니다.", 404)
    return item.payload


async def scan(discovery_id: UUID):
    from app.core.database import SessionFactory
    from playwright.async_api import async_playwright
    async with SessionFactory() as session:
        item = await session.scalar(select(PageDiscovery).where(PageDiscovery.id == discovery_id).with_for_update())
        if not item or item.status != "QUEUED" or item.test_case_version_id is not None:
            return
        item.status, item.started_at = "SCANNING", datetime.now(UTC)
        await session.commit()
        try:
            env = await session.scalar(select(Environment).where(Environment.id == item.environment_id,
                Environment.organization_id == item.organization_id, Environment.project_id == item.project_id))
            url = item.settings["startUrl"]
            if not env or not allowed_url(url, env.allowed_domains):
                raise ValueError("disallowed")
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(service_workers="block")
                    context.set_default_timeout(1000)

                    async def guard(route):
                        req = route.request
                        resource_domains = [*env.allowed_domains, *getattr(env, "resource_domains", [])]
                        permitted = (allowed_url(req.url, env.allowed_domains) if req.is_navigation_request()
                                     else allowed_resource_url(req.url, resource_domains))
                        if req.method not in {"GET", "HEAD"} or not permitted:
                            await route.abort()
                        else:
                            await route.continue_()

                    await context.route("**/*", guard)
                    from app.workers.step_executor import wait_for_render
                    page = await context.new_page()
                    include_links = bool(item.settings.get("includeInternalLinks", False))
                    max_depth = int(item.settings.get("maxDepth", 0))
                    max_pages = int(item.settings.get("maxPages", 1))
                    queue = [(url, 0)]
                    visited: set[str] = set()
                    pages, root_elements, root_fingerprint, warnings = [], [], "", []
                    while queue and len(pages) < max_pages:
                        candidate, depth = queue.pop(0)
                        if candidate in visited:
                            continue
                        visited.add(candidate)
                        try:
                            await page.goto(candidate, wait_until="domcontentloaded", timeout=20000)
                            await wait_for_render(page, 10_000)
                            if not allowed_url(page.url, env.allowed_domains):
                                raise ValueError("redirect")
                            page_elements = await collect_elements(page)
                            page_fp = page_fingerprint(page.url, page_elements)
                            pages.append({"url": page.url, "title": safe_text(await page.title()),
                                "fingerprint": page_fp, "depth": depth, "elementCount": len(page_elements)})
                            if not root_fingerprint:
                                root_elements, root_fingerprint = page_elements, page_fp
                            if include_links and depth < max_depth:
                                hrefs = await page.locator("a[href]").evaluate_all(
                                    "nodes => nodes.map(node => node.getAttribute('href') || '')"
                                )
                                for href in hrefs:
                                    linked = internal_page_url(page.url, href, env.allowed_domains)
                                    if linked and linked not in visited and all(linked != queued for queued, _ in queue):
                                        queue.append((linked, depth + 1))
                        except Exception:
                            if not pages:
                                raise
                            warnings.append({"code": "PAGE_SKIPPED", "message": "연결된 내부 페이지 1개를 안전하게 분석하지 못해 제외했습니다."})
                    warnings.insert(0, {"code": "LIMITED_READ_ONLY_DISCOVERY",
                        "message": f"최대 {max_pages}페이지·깊이 {max_depth}를 탐색했습니다. 시작 페이지의 명시적 토글만 클릭 전후 상태를 관찰하며 일반 버튼·폼·위험 행동·iframe·AI 기능 추론은 수행하지 않습니다."})
                    root_areas, root_interactions = feature_inventory(root_elements)
                    await page.goto(pages[0]["url"], wait_until="domcontentloaded", timeout=20000)
                    await wait_for_render(page, 10_000)
                    state_changes = await observe_state_changes(page, root_elements, root_interactions)
                    scenario_candidates = build_scenario_candidates(root_areas, root_interactions, state_changes)
                    item.result = {"pages": pages, "elements": root_elements,
                        "areas": root_areas, "interactions": root_interactions,
                        "stateChanges": state_changes,
                        "scenarioCandidates": scenario_candidates,
                        "coverage": coverage_summary(scenario_candidates),
                        "fingerprint": root_fingerprint, "warnings": warnings}
                finally:
                    await browser.close()
            item.status = "COMPLETED"
        except Exception as exc:
            from app.modules.discoveries.target import discovery_error
            code, message = discovery_error(exc)
            item.status, item.error_code = "FAILED", code
            item.result = {"warnings": [{"code": code, "message": message}]}
        item.ended_at = datetime.now(UTC)
        await session.commit()


def page_fingerprint(url, elements):
    # Keep fingerprints compatible with discoveries created before semantic
    # inventory metadata was added.
    observed = [{key: element.get(key) for key in (
        "elementId", "selector", "name", "matchCount", "visible", "enabled"
    ) if key in element} for element in elements]
    return hashlib.sha256(json.dumps({"url": url, "elements": observed}, sort_keys=True).encode()).hexdigest()


def feature_inventory(elements: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group observed elements without clicking or inventing page semantics."""
    areas_by_key: dict[tuple[str, str], dict] = {}
    interactions = []
    for element in elements:
        kind = element.get("areaKind") or "content"
        name = element.get("areaName") or kind
        key = (kind, name)
        area = areas_by_key.get(key)
        if area is None:
            area = {"id": f"area-{len(areas_by_key) + 1}", "kind": kind,
                "name": name, "elementIds": []}
            areas_by_key[key] = area
        area["elementIds"].append(element["elementId"])
        if not element.get("interactable"):
            continue
        interactions.append({"id": f"interaction-{len(interactions) + 1}", "areaId": area["id"],
            "elementId": element["elementId"], "kind": element.get("role") or element.get("tag"),
            "name": element.get("name", ""), "selector": element.get("selector", ""),
            "enabled": bool(element.get("enabled")), "risk": "READ_ONLY_CANDIDATE",
            "source": "PAGE_DISCOVERY"})
    return list(areas_by_key.values()), interactions


COVERAGE_STATUSES = ("COVERED", "PARTIAL", "MISSING_IN_TC", "TC_ONLY", "NOT_AUTOMATABLE")


def coverage_summary(candidates: list[dict]) -> dict[str, int]:
    summary = {status: 0 for status in COVERAGE_STATUSES}
    for candidate in candidates:
        status = candidate.get("coverage")
        if status in summary:
            summary[status] += 1
    return summary


def build_scenario_candidates(areas: list[dict], interactions: list[dict], state_changes: list[dict]) -> list[dict]:
    """Create feature candidates only from Playwright-observed state transitions."""
    area_by_id = {area.get("id"): area for area in areas}
    interaction_by_id = {item.get("id"): item for item in interactions}
    candidates, seen = [], set()
    for change in state_changes:
        interaction = interaction_by_id.get(change.get("interactionId"))
        if not interaction or change.get("source") != "PLAYWRIGHT_OBSERVED":
            continue
        area = area_by_id.get(interaction.get("areaId")) or {}
        key = (interaction.get("areaId"), interaction.get("selector"))
        if key in seen:
            continue
        seen.add(key)
        after = change.get("after") or {}
        before = change.get("before") or {}
        changed = [field for field in ("url", "ariaPressed", "ariaSelected", "checked", "pageFingerprint")
            if before.get(field) != after.get(field)]
        changed_areas = change.get("changedAreas") or []
        if changed_areas:
            changed.append("areas")
        if not changed:
            continue
        stable = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:12]
        state_change_id = change.get("id") or f"state-change-{len(candidates) + 1}"
        name = interaction.get("name") or interaction.get("elementId")
        area_name = area.get("name") or area.get("kind") or "content"
        candidates.append({"id": f"candidate-{stable}", "areaId": interaction.get("areaId"),
            "areaName": area_name, "purpose": f"{name} 선택 시 {area_name} 상태 변경 확인",
            "preconditions": [f"{area_name} 영역과 {name} 컨트롤이 표시되고 활성화됨"],
            "steps": [
                {"action": "click", "interactionId": interaction["id"], "selector": interaction["selector"]},
                {"action": "assert", "assertion": {"type": "observed_state", "changedFields": changed,
                    "expected": {field: (changed_areas if field == "areas" else after.get(field)) for field in changed}}},
            ], "evidence": {"elementIds": [interaction["elementId"]],
                "interactionIds": [interaction["id"]], "stateChangeIds": [state_change_id]},
            "automationStatus": "AUTOMATABLE" if change.get("restored") else "MANUAL_REVIEW_REQUIRED",
            "confidence": 1 if change.get("restored") else 0.5,
            "coverage": "MISSING_IN_TC", "source": "RULE_BASED_OBSERVED"})
    return candidates


def compare_candidate_coverage(candidates: list[dict], extracted: dict) -> list[dict]:
    """Conservatively compare observed functions with extracted TC clauses."""
    actions = extracted.get("actions") or []
    expected = extracted.get("expectedResults") or []
    compared = []
    for candidate in candidates:
        result = dict(candidate)
        interaction_name = ""
        steps = candidate.get("steps") or []
        if steps:
            # Candidate purpose begins with the observed accessible name.
            interaction_name = candidate.get("purpose", "").split(" 선택 시 ", 1)[0]
        action_match = bool(interaction_name and any(
            interaction_name in clause and re.search(r"클릭|선택|click|press", clause, re.I) for clause in actions))
        expectation_match = bool(any(re.search(r"선택|활성|변경|필터|목록|selected|active|change|filter|list", clause, re.I)
            for clause in expected))
        result["coverage"] = "COVERED" if action_match and expectation_match else "PARTIAL" if action_match or expectation_match else "MISSING_IN_TC"
        compared.append(result)
    return compared


def safe_state_candidate(element: dict) -> bool:
    if (not element.get("interactable") or element.get("insideForm") or not element.get("visible")
            or not element.get("enabled") or element.get("matchCount") != 1):
        return False
    if re.search(r"logout|log out|signout|sign out|delete|remove|checkout|payment|purchase|unsubscribe|submit|save|send|download|탈퇴|삭제|결제|로그아웃|저장|전송|다운로드", element.get("name", ""), re.I):
        return False
    return element.get("role") in {"button", "checkbox", "radio", "tab"} or any(
        element.get(key) is not None for key in ("ariaPressed", "ariaSelected")
    )


def area_fingerprints(elements: list[dict]) -> dict[str, dict]:
    """Return bounded, value-free signatures for visible elements grouped by observed landmark."""
    grouped: dict[str, list[dict]] = {}
    labels: dict[str, tuple[str, str]] = {}
    for element in elements:
        if not element.get("visible"):
            continue
        kind = element.get("areaKind") or "content"
        name = element.get("areaName") or kind
        key = json.dumps([kind, name], ensure_ascii=False, separators=(",", ":"))
        labels[key] = (kind, name)
        grouped.setdefault(key, []).append({field: element.get(field) for field in (
            "selector", "name", "role", "enabled", "ariaPressed", "ariaSelected")})
    result = {}
    for key, values in grouped.items():
        kind, name = labels[key]
        canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        result[key] = {"kind": kind, "name": name, "itemCount": len(values),
            "fingerprint": hashlib.sha256(canonical.encode()).hexdigest()}
    return result


def changed_area_evidence(before: dict[str, dict], after: dict[str, dict]) -> list[dict]:
    changes = []
    for key in sorted(set(before) | set(after)):
        left, right = before.get(key), after.get(key)
        if left == right:
            continue
        source = right or left or {}
        changes.append({"kind": source.get("kind", "content"), "name": source.get("name", "content"),
            "beforeItemCount": (left or {}).get("itemCount", 0), "afterItemCount": (right or {}).get("itemCount", 0),
            "beforeFingerprint": (left or {}).get("fingerprint"),
            "afterFingerprint": (right or {}).get("fingerprint")})
    return changes[:10]


async def observe_state_changes(page, elements: list[dict], interactions: list[dict] | None = None) -> list[dict]:
    """Observe bounded safe controls and restore the starting page before the next click."""
    changes = []
    interaction_ids = {item["elementId"]: item["id"] for item in (interactions or [])}
    initial_url = page.url
    initial_fingerprint = page_fingerprint(initial_url, elements)
    for element in [item for item in elements if safe_state_candidate(item)][:10]:
        locator = page.locator(element["selector"]) if element["selector"].startswith("[") else page.get_by_role(
            element["role"], name=element["name"], exact=True)
        if await locator.count() != 1:
            continue
        try:
            before_elements = await collect_elements(page)
            before_areas = area_fingerprints(before_elements)
            before = {"url": page.url, "ariaPressed": await locator.get_attribute("aria-pressed"),
                "ariaSelected": await locator.get_attribute("aria-selected"), "checked": await locator.is_checked()
                if element.get("role") in {"checkbox", "radio"} else None,
                "pageFingerprint": page_fingerprint(page.url, before_elements)}
            await locator.click(timeout=1000)
            await page.wait_for_timeout(300)
            after_elements = await collect_elements(page)
            after_areas = area_fingerprints(after_elements)
            after = {"url": page.url, "ariaPressed": await locator.get_attribute("aria-pressed"),
                "ariaSelected": await locator.get_attribute("aria-selected"), "checked": await locator.is_checked()
                if element.get("role") in {"checkbox", "radio"} else None,
                "pageFingerprint": page_fingerprint(page.url, after_elements)}
        except Exception:
            continue
        area_changes = changed_area_evidence(before_areas, after_areas)
        restored = False
        try:
            if urlsplit(initial_url).scheme in {"http", "https"}:
                await page.goto(initial_url, wait_until="domcontentloaded", timeout=10_000)
                await page.wait_for_timeout(300)
                restored = page_fingerprint(page.url, await collect_elements(page)) == initial_fingerprint
            else:
                await locator.click(timeout=1000)
                await page.wait_for_timeout(150)
                restored = page_fingerprint(page.url, await collect_elements(page)) == initial_fingerprint
        except Exception:
            restored = False
        if before != after:
            changes.append({"id": f"state-change-{len(changes) + 1}",
                "interactionId": interaction_ids.get(element["elementId"], element["elementId"]),
                "selector": element["selector"],
                "before": before, "after": after, "changedAreas": area_changes,
                "restored": restored, "source": "PLAYWRIGHT_OBSERVED"})
        if not restored:
            break
    return changes


async def collect_elements(page):
    nodes = page.locator('[data-testid],h1,h2,h3,button,a[href],input,select,textarea,[role]')
    elements = []
    for index in range(min(await nodes.count(), 200)):
        node = nodes.nth(index)
        semantics = await node.evaluate("""element => {
            const tag = element.tagName.toLowerCase();
            const implicit = {a:'link',button:'button',h1:'heading',h2:'heading',h3:'heading',
                input:'textbox',select:'combobox',textarea:'textbox'}[tag] || '';
            const role = element.getAttribute('role') || implicit;
            const landmark = element.closest('header,nav,main,footer,section,form,[role="banner"],'
                + '[role="navigation"],[role="main"],[role="contentinfo"],[role="dialog"]');
            const landmarkTag = landmark?.tagName.toLowerCase() || 'content';
            const areaKind = landmark?.getAttribute('role') || landmarkTag;
            const heading = landmark?.querySelector('h1,h2,h3');
            const areaName = landmark?.getAttribute('aria-label') || heading?.innerText || areaKind;
            return {tag, role, areaKind, areaName: String(areaName || '').replace(/\\s+/g, ' ').trim(),
                insideForm: Boolean(element.closest('form')), ariaPressed: element.getAttribute('aria-pressed'),
                ariaSelected: element.getAttribute('aria-selected')};
        }""")
        test_id = await node.get_attribute("data-testid") or ""
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", test_id) and safe_text(test_id):
            selector = f'[data-testid="{test_id}"]'
            name = safe_text(await node.get_attribute("aria-label") or test_id)
            locator = page.locator(selector)
        else:
            metadata = await node.evaluate("""element => {
                const tag = element.tagName.toLowerCase();
                const implicit = {a:'link',button:'button',h1:'heading',h2:'heading',h3:'heading',
                    input:'textbox',select:'combobox',textarea:'textbox'}[tag] || '';
                const role = element.getAttribute('role') || implicit;
                const imageAlt = element.querySelector('img[alt]')?.getAttribute('alt') || '';
                const name = element.getAttribute('aria-label') || element.getAttribute('title') ||
                    element.getAttribute('placeholder') || element.innerText || imageAlt;
                return {role, name: String(name || '').replace(/\\s+/g, ' ').trim()};
            }""")
            role = metadata.get("role", "")
            raw_name = metadata.get("name", "")
            name = safe_text(raw_name)
            if role not in {"button", "link", "heading", "textbox", "combobox", "checkbox", "radio", "tab"}:
                continue
            if not name or name != raw_name or '"' in name or "\\" in name:
                continue
            selector = f'role={role}[name="{name}"]'
            locator = page.get_by_role(role, name=name, exact=True)
        if await locator.count() != 1:
            continue
        visible, enabled = await locator.is_visible(), await locator.is_enabled()
        role = semantics.get("role", "")
        elements.append({"elementId": f"element-{index + 1}", "selector": selector,
            "name": name, "matchCount": 1, "visible": visible, "enabled": enabled,
            "tag": semantics.get("tag", ""), "role": role,
            "areaKind": safe_text(semantics.get("areaKind", "")) or "content",
            "areaName": safe_text(semantics.get("areaName", "")) or "content",
            "insideForm": bool(semantics.get("insideForm")),
            "ariaPressed": semantics.get("ariaPressed"), "ariaSelected": semantics.get("ariaSelected"),
            "interactable": bool(visible and enabled and role in {
                "button", "link", "textbox", "combobox", "checkbox", "radio", "tab"})})
        if len(elements) >= 50:
            break
    return elements
