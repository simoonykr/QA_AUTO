import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, ROUND_UP
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError
from app.db.models import AiStructureCache, AiUsageLedger, AiUsageStatus
from app.modules.ai.gateway import OpenAIGateway
from app.schemas.test_cases import AiUsageSummary, StructureRequest, StructuredTestCase


VERSION_ID = "00000000-0000-0000-0000-000000000501"
ENDPOINT = "/api/v1/test-case-versions/current/structure"
_MONEY = Decimal("0.00000001")


class StructureService:
    def __init__(self, session: AsyncSession, settings: Settings, gateway: OpenAIGateway | None = None):
        self.session = session
        self.settings = settings
        self.gateway = gateway or OpenAIGateway(settings)

    async def structure(self, body: StructureRequest) -> StructuredTestCase:
        detected_count = detect_test_case_count(body.rawText)
        if detected_count > 1:
            raise DomainError(
                "MULTIPLE_TEST_CASES_REVIEW_REQUIRED",
                "여러 테스트 케이스가 포함되어 있어 TC별 분리 검토가 필요합니다.",
                422,
                retryable=False,
                details={
                    "reviewStatus": "REVIEW_REQUIRED",
                    "detectedTestCaseCount": detected_count,
                    "rawTextLength": len(body.rawText),
                    "aiCallCount": 0,
                },
            )
        if not self.settings.ai_ready:
            return rule_based_structure(body, self.settings.ai_daily_budget_usd)

        organization_id = UUID(self.settings.default_organization_id)
        request_hash = self._request_hash(body)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 918_273_645})
        cached = await self.session.scalar(select(AiStructureCache).where(
            AiStructureCache.organization_id == organization_id,
            AiStructureCache.request_hash == request_hash,
            AiStructureCache.model == self.settings.openai_model,
        ))
        spent = await self._daily_spent(organization_id)
        if cached:
            result = dict(cached.structured_result)
            result["aiUsage"] = self._usage("CACHE", 0, 0, Decimal("0"), spent)
            return StructuredTestCase.model_validate(result)

        reservation = self._maximum_cost(body)
        if spent + reservation > self.settings.ai_daily_budget_usd:
            raise DomainError(
                "AI_DAILY_BUDGET_EXCEEDED",
                "오늘의 AI 사용 예산을 초과하여 구조화를 실행하지 않았습니다.",
                429,
                retryable=False,
                details={"dailySpentUsd": money(spent), "dailyBudgetUsd": money(self.settings.ai_daily_budget_usd)},
            )

        ledger = AiUsageLedger(
            id=uuid4(), organization_id=organization_id, endpoint=ENDPOINT,
            request_hash=request_hash, model=self.settings.openai_model,
            status=AiUsageStatus.RESERVED, reserved_cost_usd=reservation, cost_usd=Decimal("0"),
        )
        self.session.add(ledger)
        await self.session.flush()
        try:
            gateway_result = await self.gateway.structure(body.title, body.rawText)
            cost = self._actual_cost(gateway_result.input_tokens, gateway_result.output_tokens)
            if cost > reservation:
                raise DomainError("AI_USAGE_LIMIT_ERROR", "AI 사용량이 예약 한도를 초과했습니다.", 502, retryable=False)
            structured = StructuredTestCase.model_validate({
                "versionId": VERSION_ID, "title": body.title, **gateway_result.data,
                "aiUsage": self._usage("AI", gateway_result.input_tokens, gateway_result.output_tokens, cost, spent + cost),
            })
            ledger.status = AiUsageStatus.COMPLETED
            ledger.input_tokens = gateway_result.input_tokens
            ledger.output_tokens = gateway_result.output_tokens
            ledger.cost_usd = cost
            ledger.upstream_request_id = gateway_result.request_id
            ledger.completed_at = datetime.now(UTC)
            cached_payload = structured.model_dump(exclude={"aiUsage"}, mode="json")
            self.session.add(AiStructureCache(
                id=uuid4(), organization_id=organization_id, request_hash=request_hash,
                model=self.settings.openai_model, structured_result=cached_payload,
            ))
            await self.session.commit()
            return structured
        except DomainError as exc:
            ledger.status = AiUsageStatus.FAILED
            ledger.error_code = exc.code
            ledger.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise
        except Exception as exc:
            ledger.status = AiUsageStatus.FAILED
            ledger.error_code = "AI_INTERNAL_ERROR"
            ledger.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise DomainError("AI_INTERNAL_ERROR", "AI 구조화 결과를 저장하지 못했습니다.", 500, retryable=True) from exc

    async def _daily_spent(self, organization_id: UUID) -> Decimal:
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        value = await self.session.scalar(select(func.coalesce(func.sum(AiUsageLedger.cost_usd), 0)).where(
            AiUsageLedger.organization_id == organization_id,
            AiUsageLedger.status == AiUsageStatus.COMPLETED,
            AiUsageLedger.created_at >= day_start,
        ))
        return Decimal(value or 0)

    def _request_hash(self, body: StructureRequest) -> str:
        normalized = json.dumps({
            "title": " ".join(body.title.split()),
            "rawText": "\n".join(line.strip() for line in body.rawText.strip().splitlines()),
            "model": self.settings.openai_model,
            "schema": 1,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _maximum_cost(self, body: StructureRequest) -> Decimal:
        # UTF-8 byte count is a conservative upper bound for text token count.
        input_upper_bound = len(body.title.encode()) + len(body.rawText.encode()) + 512
        return (
            Decimal(input_upper_bound) * self.settings.ai_input_cost_per_1m_usd / Decimal(1_000_000)
            + Decimal(self.settings.ai_max_output_tokens) * self.settings.ai_output_cost_per_1m_usd / Decimal(1_000_000)
        ).quantize(_MONEY, rounding=ROUND_UP)

    def _actual_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * self.settings.ai_input_cost_per_1m_usd / Decimal(1_000_000)
            + Decimal(output_tokens) * self.settings.ai_output_cost_per_1m_usd / Decimal(1_000_000)
        ).quantize(_MONEY, rounding=ROUND_UP)

    def _usage(self, source: str, input_tokens: int, output_tokens: int, cost: Decimal, spent: Decimal) -> AiUsageSummary:
        return AiUsageSummary(
            source=source, callCount=1 if source == "AI" else 0,
            inputTokens=input_tokens, outputTokens=output_tokens,
            costUsd=money(cost), dailySpentUsd=money(spent), dailyBudgetUsd=money(self.settings.ai_daily_budget_usd),
        )


def rule_based_structure(body: StructureRequest, budget: Decimal = Decimal("0")) -> StructuredTestCase:
    segments = _test_segments(body.rawText)
    steps = []
    assertions = []
    assumptions = []
    preconditions = []
    for index, segment in enumerate(segments[:20], start=1):
        action = _action_for(segment)
        if action == "assert":
            assertions.append({"type": "text", "operator": "contains", "expected": segment, "timeoutMs": 10_000})
        if any(keyword in segment.lower() for keyword in ("전제", "준비", "환경", "조건", "precondition")):
            preconditions.append(segment)
        steps.append({
            "id": f"step-{index}",
            "title": segment[:80],
            "note": segment,
            "action": action,
            "confidence": 0.7 if action != "assert" else 0.8,
        })
    if not assertions:
        expected = segments[-1]
        assertions.append({"type": "text", "operator": "contains", "expected": expected, "timeoutMs": 10_000})
        steps[-1]["action"] = "assert"
    if len(segments) > 20:
        assumptions.append(f"원문의 {len(segments)}개 항목 중 앞 20개만 구조화했습니다. 나머지 항목은 검토가 필요합니다.")
    return StructuredTestCase(
        versionId=VERSION_ID, title=body.title,
        preconditions=list(dict.fromkeys(preconditions)),
        steps=steps,
        assertions=assertions,
        assumptions=assumptions,
        confidence=0.68,
        aiUsage=AiUsageSummary(source="RULE_BASED", callCount=0, inputTokens=0, outputTokens=0, costUsd="0.00000000", dailySpentUsd="0.00000000", dailyBudgetUsd=money(budget)),
    )


def detect_test_case_count(raw_text: str) -> int:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    explicit_ids = set(re.findall(r"(?im)\b(?:TC|TEST[-_ ]?CASE)[-_ ]?\d{1,6}\b", raw_text))
    if len(explicit_ids) > 1:
        return len(explicit_ids)

    for index, line in enumerate(lines[:10]):
        cells = [cell.strip().lower() for cell in line.split("|")]
        header = " ".join(cells)
        if len(cells) > 1 and any(marker in header for marker in ("tc id", "tc no", "test case id", "테스트 케이스 id", "테스트케이스 id", "케이스 id")):
            data_rows = [candidate for candidate in lines[index + 1:] if "|" in candidate]
            if len(data_rows) > 1:
                return len(data_rows)

    # Large tabular imports are not safe to collapse into one executable TC.
    tabular_rows = sum(1 for line in lines if "|" in line)
    if len(raw_text) > 5_000 and (len(lines) >= 20 or tabular_rows >= 10):
        return max(tabular_rows, len(lines) - 1)
    return 1


def _test_segments(raw_text: str) -> list[str]:
    segments = [item.strip(" -\t") for item in re.split(r"(?:\r?\n)+|(?<=[.!?。])\s+", raw_text) if item.strip(" -\t")]
    return segments or [raw_text.strip()]


def _action_for(segment: str) -> str:
    lowered = segment.lower()
    if any(keyword in lowered for keyword in ("접속", "이동", "진입", "navigate", "open", "url")):
        return "navigate"
    if any(keyword in lowered for keyword in ("입력", "작성", "기입", "fill", "type")):
        return "fill"
    if any(keyword in lowered for keyword in ("클릭", "선택", "누르", "click", "tap")):
        return "click"
    return "assert"


def money(value: Decimal) -> str:
    return format(Decimal(value).quantize(_MONEY), ".8f")
