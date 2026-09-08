"""Independent page discovery and non-executable, evidence-backed scenario drafts."""
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
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
    maxPages: Literal[1] = 1
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
        "automationStatus": "MANUAL_REVIEW_REQUIRED", "executable": False,
        "warnings": [{"code": "SCENARIO_REVIEW_REQUIRED", "message": "페이지 표시 확인 초안입니다. TC 비교와 검토 선택 저장 후 승인해 주세요."}],
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
    item = PageDiscovery(id=uuid4(), organization_id=org, project_id=project,
        environment_id=environment.id, test_case_version_id=None, status="QUEUED",
        settings={"startUrl": body.startUrl, "maxPages": 1, "maxAiCalls": 0, "mode": "PAGE_FIRST"})
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
            "warnings": (item.result or {}).get("warnings", []), "aiUsage": {"source": "RULE_BASED", "callCount": 0}}


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
                        if req.method not in {"GET", "HEAD"} or not allowed_url(req.url, env.allowed_domains):
                            await route.abort()
                        else:
                            await route.continue_()

                    await context.route("**/*", guard)
                    page = await context.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    if not allowed_url(page.url, env.allowed_domains):
                        raise ValueError("redirect")
                    # Stable IDs only: no HTML, input values or arbitrary page text collected.
                    elements = await collect_elements(page)
                    fingerprint = page_fingerprint(page.url, elements)
                    item.result = {"pages": [{"url": page.url, "title": "", "fingerprint": fingerprint}],
                        "elements": elements, "fingerprint": fingerprint,
                        "warnings": [{"code": "LIMITED_READ_ONLY_DISCOVERY", "message": "1페이지의 안정적인 test ID 요소만 탐색합니다. 클릭·입력·iframe 내부 탐색은 수행하지 않습니다."}]}
                finally:
                    await browser.close()
            item.status = "COMPLETED"
        except Exception:
            item.status, item.error_code = "FAILED", "PAGE_SCAN_FAILED"
        item.ended_at = datetime.now(UTC)
        await session.commit()


def page_fingerprint(url, elements):
    return hashlib.sha256(json.dumps({"url": url, "elements": elements}, sort_keys=True).encode()).hexdigest()


async def collect_elements(page):
    nodes = page.locator('[data-testid]')
    elements = []
    for index in range(min(await nodes.count(), 100)):
        node = nodes.nth(index)
        test_id = await node.get_attribute("data-testid") or ""
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", test_id) or not safe_text(test_id):
            continue
        selector = f'[data-testid="{test_id}"]'
        if await page.locator(selector).count() != 1:
            continue
        elements.append({"elementId": f"element-{index + 1}", "selector": selector,
            "name": safe_text(await node.get_attribute("aria-label") or test_id),
            "matchCount": 1, "visible": await node.is_visible(), "enabled": await node.is_enabled()})
    return elements
