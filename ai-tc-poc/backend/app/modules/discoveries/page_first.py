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
                        "message": f"최대 {max_pages}페이지·깊이 {max_depth}를 탐색했습니다. 시나리오 근거는 시작 페이지 요소로 제한되며 클릭 전후 상태·iframe·AI 기능 추론은 아직 수행하지 않습니다."})
                    item.result = {"pages": pages, "elements": root_elements,
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
    return hashlib.sha256(json.dumps({"url": url, "elements": elements}, sort_keys=True).encode()).hexdigest()


async def collect_elements(page):
    nodes = page.locator('[data-testid],h1,h2,h3,button,a[href],input,select,textarea,[role]')
    elements = []
    for index in range(min(await nodes.count(), 200)):
        node = nodes.nth(index)
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
            if role not in {"button", "link", "heading", "textbox", "combobox", "checkbox", "radio"}:
                continue
            if not name or name != raw_name or '"' in name or "\\" in name:
                continue
            selector = f'role={role}[name="{name}"]'
            locator = page.get_by_role(role, name=name, exact=True)
        if await locator.count() != 1:
            continue
        elements.append({"elementId": f"element-{index + 1}", "selector": selector,
            "name": name, "matchCount": 1, "visible": await locator.is_visible(), "enabled": await locator.is_enabled()})
        if len(elements) >= 50:
            break
    return elements
