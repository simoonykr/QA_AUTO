import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, ROUND_UP
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError
from app.db.models import AiStructureCache, AiUsageLedger, AiUsageStatus
from app.modules.ai.gateway import OpenAIGateway
from app.modules.ai.service import money


ENDPOINT = "/internal/page-discoveries/map"
PROMPT_VERSION = "semantic-element-mapping-v1"
_MONEY = Decimal("0.00000001")


class DiscoveryMappingService:
    def __init__(self, session: AsyncSession, settings: Settings, gateway: OpenAIGateway | None = None):
        self.session = session
        self.settings = settings
        self.gateway = gateway or OpenAIGateway(settings)

    async def map(self, organization_id: UUID, steps: list[dict], elements: list[dict]) -> dict:
        if not self.settings.ai_ready:
            raise DomainError("AI_NOT_AVAILABLE", "AI 의미 매핑을 사용할 수 없습니다.", 409, retryable=False)
        safe_steps = [
            {
                "stepId": str(step.get("id") or ""),
                "action": str(step.get("action") or ""),
                "targetDescription": str(step.get("targetDescription") or step.get("title") or "")[:300],
                "selectorHint": step.get("selectorHint") or {},
            }
            for step in steps
        ]
        safe_elements = [
            {
                "elementId": str(element.get("elementId") or ""),
                "tag": element.get("tag") or "",
                "role": element.get("role") or "",
                "name": element.get("name") or "",
                "label": element.get("label") or "",
                "placeholder": element.get("placeholder") or "",
                "dataTestId": element.get("dataTestId") or "",
                "id": element.get("id") or "",
                "htmlName": element.get("htmlName") or "",
                "href": element.get("href") or "",
            }
            for element in elements[:500]
        ]
        request_hash = self._request_hash(safe_steps, safe_elements)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 918_273_646})
        cached = await self.session.scalar(select(AiStructureCache).where(
            AiStructureCache.organization_id == organization_id,
            AiStructureCache.request_hash == request_hash,
            AiStructureCache.model == self.settings.openai_model,
        ))
        spent = await self._daily_spent(organization_id)
        if cached:
            return {
                "mappings": (cached.structured_result or {}).get("mappings") or [],
                "model": self.settings.openai_model,
                "promptVersion": PROMPT_VERSION,
                "aiUsage": self._usage("CACHE", 0, 0, Decimal("0"), spent),
            }
        reservation = self._maximum_cost(safe_steps, safe_elements)
        if spent + reservation > self.settings.ai_daily_budget_usd:
            raise DomainError("AI_DAILY_BUDGET_EXCEEDED", "오늘의 AI 사용 예산을 초과했습니다.", 429, retryable=False)
        ledger = AiUsageLedger(
            id=uuid4(), organization_id=organization_id, endpoint=ENDPOINT, request_hash=request_hash,
            model=self.settings.openai_model, status=AiUsageStatus.RESERVED,
            reserved_cost_usd=reservation, cost_usd=Decimal("0"),
        )
        self.session.add(ledger)
        await self.session.flush()
        try:
            result = await self.gateway.map_discovery(safe_steps, safe_elements)
            cost = self._actual_cost(result.input_tokens, result.output_tokens)
            if cost > reservation:
                raise DomainError("AI_USAGE_LIMIT_ERROR", "AI 사용량이 예약 한도를 초과했습니다.", 502, retryable=False)
            allowed_steps = {step["stepId"] for step in safe_steps}
            allowed_elements = {element["elementId"] for element in safe_elements}
            mappings = []
            for mapping in result.data.get("mappings") or []:
                step_id = str(mapping.get("stepId") or "")
                if step_id not in allowed_steps:
                    continue
                candidate_ids = list(dict.fromkeys(
                    str(value) for value in mapping.get("candidateIds") or [] if str(value) in allowed_elements
                ))[:5]
                mappings.append({"stepId": step_id, "candidateIds": candidate_ids})
            ledger.status = AiUsageStatus.COMPLETED
            ledger.input_tokens, ledger.output_tokens, ledger.cost_usd = result.input_tokens, result.output_tokens, cost
            ledger.upstream_request_id, ledger.completed_at = result.request_id, datetime.now(UTC)
            self.session.add(AiStructureCache(
                id=uuid4(), organization_id=organization_id, request_hash=request_hash,
                model=self.settings.openai_model, structured_result={"mappings": mappings},
            ))
            await self.session.commit()
            return {
                "mappings": mappings, "model": self.settings.openai_model, "promptVersion": PROMPT_VERSION,
                "aiUsage": self._usage("AI", result.input_tokens, result.output_tokens, cost, spent + cost),
            }
        except Exception as exc:
            ledger.status = AiUsageStatus.FAILED
            ledger.error_code = exc.code if isinstance(exc, DomainError) else "AI_INTERNAL_ERROR"
            ledger.completed_at = datetime.now(UTC)
            await self.session.commit()
            if isinstance(exc, DomainError):
                raise
            raise DomainError("AI_INTERNAL_ERROR", "AI 의미 매핑 결과를 저장하지 못했습니다.", 500, retryable=True) from exc

    async def _daily_spent(self, organization_id: UUID) -> Decimal:
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        value = await self.session.scalar(select(func.coalesce(func.sum(AiUsageLedger.cost_usd), 0)).where(
            AiUsageLedger.organization_id == organization_id,
            AiUsageLedger.status == AiUsageStatus.COMPLETED,
            AiUsageLedger.created_at >= day_start,
        ))
        return Decimal(value or 0)

    def _request_hash(self, steps: list[dict], elements: list[dict]) -> str:
        normalized = json.dumps(
            {"steps": steps, "elements": elements, "model": self.settings.openai_model, "schema": PROMPT_VERSION},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _maximum_cost(self, steps: list[dict], elements: list[dict]) -> Decimal:
        input_upper_bound = len(json.dumps({"steps": steps, "elements": elements}, ensure_ascii=False).encode()) + 512
        return (
            Decimal(input_upper_bound) * self.settings.ai_input_cost_per_1m_usd / Decimal(1_000_000)
            + Decimal(self.settings.ai_max_output_tokens) * self.settings.ai_output_cost_per_1m_usd / Decimal(1_000_000)
        ).quantize(_MONEY, rounding=ROUND_UP)

    def _actual_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * self.settings.ai_input_cost_per_1m_usd / Decimal(1_000_000)
            + Decimal(output_tokens) * self.settings.ai_output_cost_per_1m_usd / Decimal(1_000_000)
        ).quantize(_MONEY, rounding=ROUND_UP)

    def _usage(self, source: str, input_tokens: int, output_tokens: int, cost: Decimal, spent: Decimal) -> dict:
        return {
            "source": source, "callCount": 1 if source == "AI" else 0,
            "inputTokens": input_tokens, "outputTokens": output_tokens,
            "costUsd": money(cost), "dailySpentUsd": money(spent),
            "dailyBudgetUsd": money(self.settings.ai_daily_budget_usd),
        }
