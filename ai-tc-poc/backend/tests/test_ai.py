from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.core.config import Settings
from app.core.errors import DomainError
from app.modules.ai.gateway import GatewayResult
from app.modules.ai.discovery import DiscoveryMappingService, PROMPT_VERSION
from app.modules.ai.service import StructureService, detect_test_case_count, rule_based_structure
from app.schemas.test_cases import StructureRequest


BODY = StructureRequest(title="로그인", rawText="로그인 화면에서 이메일 입력 후 환영 문구를 확인한다.")
AI_DATA = {
    "preconditions": ["테스트 계정이 준비되어 있다."],
    "steps": [{"id": "step-1", "title": "페이지 진입", "note": "로그인 폼 확인", "action": "navigate", "confidence": 0.9}],
    "assertions": [{"type": "text", "operator": "contains", "expected": "환영", "timeoutMs": 10000}],
    "assumptions": [],
    "confidence": 0.9,
}


class FakeSession:
    def __init__(self, scalars):
        self.scalars = list(scalars)
        self.added = []
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        return None

    async def scalar(self, *_args, **_kwargs):
        return self.scalars.pop(0)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


class FakeGateway:
    def __init__(self):
        self.calls = 0

    async def structure(self, *_args):
        self.calls += 1
        return GatewayResult(AI_DATA, 100, 50, "resp-test")


class FakeDiscoveryGateway:
    def __init__(self):
        self.calls = 0
        self.steps = None
        self.elements = None

    async def map_discovery(self, steps, elements):
        self.calls += 1
        self.steps, self.elements = steps, elements
        return GatewayResult({"mappings": [
            {"stepId": "step-1", "candidateIds": ["element-2", "invented-selector"]},
            {"stepId": "unknown-step", "candidateIds": ["element-1"]},
        ]}, 80, 20, "resp-discovery")


def ai_settings(**updates):
    return Settings(
        ai_enabled=True, ai_max_calls_per_run=1, ai_daily_budget_usd="1",
        openai_api_key="test-key-not-used", **updates,
    )


def test_disabled_ai_uses_rule_based_structure_without_tokens() -> None:
    result = rule_based_structure(BODY)
    assert result.aiUsage.source == "RULE_BASED"
    assert result.aiUsage.callCount == 0
    assert result.aiUsage.costUsd == "0.00000000"
    assert result.steps[0].note in BODY.rawText
    assert result.assertions[0].expected in BODY.rawText


def test_structure_request_preserves_full_9613_character_raw_text() -> None:
    raw_text = "가" * 9_613
    request = StructureRequest(title="KakaoGames", rawText=raw_text)
    assert len(request.rawText) == 9_613
    assert request.rawText == raw_text


def test_detects_multiple_test_cases_in_large_tabular_import() -> None:
    rows = ["TC ID | 제목 | 단계"] + [f"TC-{index:03d} | 테스트 {index} | 실행 후 결과 확인" for index in range(1, 103)]
    raw_text = "\n".join(rows)
    assert detect_test_case_count(raw_text) == 102


@pytest.mark.asyncio
async def test_multiple_test_cases_are_blocked_before_ai_call() -> None:
    body = StructureRequest(title="KakaoGames", rawText="\n".join(f"TC-{index:03d} | 테스트 {index}" for index in range(1, 103)))
    gateway = FakeGateway()
    with pytest.raises(DomainError) as raised:
        await StructureService(FakeSession([]), ai_settings(), gateway).structure(body)
    assert raised.value.code == "MULTIPLE_TEST_CASES_REVIEW_REQUIRED"
    assert raised.value.details["detectedTestCaseCount"] == 102
    assert raised.value.details["aiCallCount"] == 0
    assert gateway.calls == 0


@pytest.mark.asyncio
async def test_structure_calls_gateway_once_and_records_usage() -> None:
    session = FakeSession([None, Decimal("0")])
    gateway = FakeGateway()
    result = await StructureService(session, ai_settings(), gateway).structure(BODY)
    assert gateway.calls == 1
    assert result.aiUsage.source == "AI"
    assert result.aiUsage.inputTokens == 100
    assert result.aiUsage.outputTokens == 50
    assert result.aiUsage.costUsd == "0.00004500"
    assert len(session.added) == 2
    assert session.commits == 1


@pytest.mark.asyncio
async def test_same_structure_uses_cache_without_gateway_call() -> None:
    cached = SimpleNamespace(structured_result={"versionId": "00000000-0000-0000-0000-000000000501", "title": BODY.title, **AI_DATA})
    session = FakeSession([cached, Decimal("0.25")])
    gateway = FakeGateway()
    result = await StructureService(session, ai_settings(), gateway).structure(BODY)
    assert gateway.calls == 0
    assert result.aiUsage.source == "CACHE"
    assert result.aiUsage.dailySpentUsd == "0.25000000"


@pytest.mark.asyncio
async def test_daily_budget_blocks_before_gateway_call() -> None:
    session = FakeSession([None, Decimal("1")])
    gateway = FakeGateway()
    with pytest.raises(DomainError, match="예산") as raised:
        await StructureService(session, ai_settings(), gateway).structure(BODY)
    assert raised.value.code == "AI_DAILY_BUDGET_EXCEEDED"
    assert gateway.calls == 0


@pytest.mark.asyncio
async def test_discovery_mapping_uses_only_server_owned_ids_and_records_usage() -> None:
    session = FakeSession([None, Decimal("0")])
    gateway = FakeDiscoveryGateway()
    result = await DiscoveryMappingService(session, ai_settings(), gateway).map(
        UUID("00000000-0000-0000-0000-000000000001"),
        [{"id": "step-1", "action": "click", "targetDescription": "PC 필터", "selectorHint": {"role": "button"}, "value": "secret"}],
        [
            {"elementId": "element-1", "role": "button", "name": "모바일"},
            {"elementId": "element-2", "role": "button", "name": "PC", "selector": "#must-not-leak"},
        ],
    )
    assert gateway.calls == 1
    assert gateway.steps == [{"stepId": "step-1", "action": "click", "targetDescription": "PC 필터", "selectorHint": {"role": "button"}}]
    assert gateway.elements[1]["elementId"] == "element-2"
    assert "selector" not in gateway.elements[1]
    assert result["mappings"] == [{"stepId": "step-1", "candidateIds": ["element-2"]}]
    assert result["promptVersion"] == PROMPT_VERSION
    assert result["aiUsage"]["source"] == "AI"
    assert result["aiUsage"]["callCount"] == 1
    assert session.commits == 1


@pytest.mark.asyncio
async def test_discovery_mapping_cache_keeps_openai_call_at_zero() -> None:
    cached = SimpleNamespace(structured_result={"mappings": [{"stepId": "step-1", "candidateIds": ["element-1"]}]})
    session = FakeSession([cached, Decimal("0.125")])
    gateway = FakeDiscoveryGateway()
    result = await DiscoveryMappingService(session, ai_settings(), gateway).map(
        UUID("00000000-0000-0000-0000-000000000001"),
        [{"id": "step-1", "action": "click", "targetDescription": "필터"}],
        [{"elementId": "element-1", "role": "button", "name": "필터"}],
    )
    assert gateway.calls == 0
    assert result["aiUsage"]["source"] == "CACHE"
    assert result["aiUsage"]["callCount"] == 0


@pytest.mark.asyncio
async def test_discovery_mapping_is_fail_closed_when_ai_is_disabled() -> None:
    gateway = FakeDiscoveryGateway()
    with pytest.raises(DomainError) as raised:
        await DiscoveryMappingService(FakeSession([]), Settings(), gateway).map(
            UUID("00000000-0000-0000-0000-000000000001"), [], []
        )
    assert raised.value.code == "AI_NOT_AVAILABLE"
    assert gateway.calls == 0
