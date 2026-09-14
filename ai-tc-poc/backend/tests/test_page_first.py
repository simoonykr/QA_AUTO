from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from app.core.errors import DomainError
from app.modules.discoveries.page_first import (
    StartRequest, ScenarioRequest, ScenarioResponse, allowed_resource_url, allowed_url, safe_text,
    scenario_payload, find_discovery, generate, internal_page_url, start,
)


@pytest.mark.parametrize("url", ["https://evil.test", "https://example.test?token=x",
    "https://user:pass@example.test", "file:///tmp/page", "https://example.test/#token"])
def test_disallowed_urls(url):
    assert not allowed_url(url, ["example.test"])


def test_allowed_page_url_and_no_ai():
    assert allowed_url("https://example.test/games", ["example.test"])
    with pytest.raises(ValidationError):
        ScenarioRequest(maxAiCalls=1)
    request = StartRequest(environmentId=uuid4(), startUrl="https://example.test",
        includeInternalLinks=True, maxPages=3, maxDepth=2)
    assert request.maxPages == 3 and request.maxDepth == 2
    with pytest.raises(ValidationError):
        StartRequest(environmentId=uuid4(), startUrl="https://example.test", maxPages=6)


def test_internal_page_candidates_stay_bounded_to_safe_navigation_urls():
    domains = ["example.test"]
    assert internal_page_url("https://example.test/games", "/policy", domains) == "https://example.test/policy"
    assert internal_page_url("https://example.test/games", "https://evil.test", domains) is None
    assert internal_page_url("https://example.test/games", "/search?q=secret", domains) is None
    assert internal_page_url("https://example.test/games", "#section", domains) is None
    assert internal_page_url("https://example.test/account", "/logout", domains) is None
    assert internal_page_url("https://example.test/cart", "/checkout/payment", domains) is None


@pytest.mark.asyncio
async def test_internal_scope_requires_explicit_link_crawl():
    class Session:
        async def scalar(self, statement):
            return SimpleNamespace(id=uuid4(), allowed_domains=["example.test"])

    body = StartRequest(environmentId=uuid4(), startUrl="https://example.test", maxPages=2)
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    with pytest.raises(DomainError) as error:
        await start(body, request, Session())
    assert error.value.code == "DISCOVERY_SCOPE_INVALID"


def test_static_resources_allow_subdomains_without_relaxing_navigation_contract():
    assert allowed_resource_url("https://cdn.assets.example.test/app.js?v=1", ["example.test"])
    assert allowed_resource_url("https://example.test/app.css?v=1", ["example.test"])
    assert allowed_resource_url("https://cdn.jsdelivr.net/npm/app.js", ["example.test", "cdn.jsdelivr.net"])
    assert not allowed_resource_url("https://example.test.evil.test/app.js", ["example.test"])
    assert not allowed_url("https://cdn.assets.example.test/", ["example.test"])


def test_sensitive_metadata_removed():
    for value in ["qa@example.test", "Bearer abc", "010-1234-5678", "password"]:
        assert safe_text(value) == ""


def test_scenario_uses_only_verified_visible_elements_and_stays_unapproved():
    discovery = SimpleNamespace(id=uuid4(), result={"fingerprint": "abc", "pages": [{"url": "https://example.test"}],
        "elements": [
            {"elementId": "e1", "selector": "#one", "matchCount": 1, "visible": True},
            {"elementId": "e2", "selector": "#two", "matchCount": 2, "visible": True},
            {"elementId": "e3", "selector": "#three", "matchCount": 1, "visible": False}]})
    result = ScenarioResponse.model_validate(scenario_payload(discovery))
    assert len(result.steps) == 1
    assert result.steps[0].evidence["elementId"] == "e1"
    assert result.executable is False
    assert result.status == "REVIEW_REQUIRED"
    assert result.aiUsage["callCount"] == 0


@pytest.mark.asyncio
async def test_discovery_lookup_is_scoped():
    class Session:
        async def scalar(self, statement):
            sql = str(statement)
            assert "organization_id" in sql and "project_id" in sql
            assert "test_case_version_id IS NULL" in sql
            return None
    with pytest.raises(DomainError) as error:
        await find_discovery(Session(), uuid4())
    assert error.value.code == "DISCOVERY_NOT_FOUND"


@pytest.mark.asyncio
async def test_incomplete_discovery_cannot_create_scenario():
    class Session:
        async def scalar(self, statement):
            return SimpleNamespace(status="SCANNING")
    with pytest.raises(DomainError) as error:
        await generate(uuid4(), ScenarioRequest(), None, Session())
    assert error.value.code == "DISCOVERY_NOT_READY"
