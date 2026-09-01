from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.errors import DomainError
from app.modules.ai.gateway import GatewayResult
from app.modules.ai.service import StructureService, deterministic_structure
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


def ai_settings(**updates):
    return Settings(
        ai_enabled=True, ai_max_calls_per_run=1, ai_daily_budget_usd="1",
        openai_api_key="test-key-not-used", **updates,
    )


def test_disabled_ai_uses_rule_based_structure_without_tokens() -> None:
    result = deterministic_structure(BODY)
    assert result.aiUsage.source == "RULE_BASED"
    assert result.aiUsage.callCount == 0
    assert result.aiUsage.costUsd == "0.00000000"


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
