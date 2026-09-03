import json
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.errors import DomainError


@dataclass(frozen=True)
class GatewayResult:
    data: dict
    input_tokens: int
    output_tokens: int
    request_id: str | None


class OpenAIGateway:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def structure(self, title: str, raw_text: str) -> GatewayResult:
        key = self.settings.openai_api_key.get_secret_value() if self.settings.openai_api_key else ""
        payload = {
            "model": self.settings.openai_model,
            "store": False,
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "instructions": "Convert the Korean or English QA notes into one concise executable Playwright test-case structure. Provide url for navigate and selector/value/expected/operator only when the exact value is grounded in the source; otherwise use null and add an assumption that review is required. Never invent selectors, credentials, or secret values.",
            "input": f"Title: {title}\n\nQA notes:\n{raw_text}",
            "text": {"format": {"type": "json_schema", "name": "structured_test_case", "strict": True, "schema": _OUTPUT_SCHEMA}},
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.openai_timeout_seconds) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise DomainError("AI_TIMEOUT", "AI 구조화 요청 시간이 초과되었습니다.", 504, retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise DomainError("AI_UPSTREAM_ERROR", "AI 구조화 서비스를 호출하지 못했습니다.", 502, retryable=status >= 500, details={"upstreamStatus": status}) from exc
        except httpx.HTTPError as exc:
            raise DomainError("AI_UPSTREAM_ERROR", "AI 구조화 서비스에 연결하지 못했습니다.", 502, retryable=True) from exc

        body = response.json()
        try:
            text = next(
                content["text"]
                for item in body["output"] if item.get("type") == "message"
                for content in item.get("content", []) if content.get("type") == "output_text"
            )
            data = json.loads(text)
            usage = body["usage"]
            return GatewayResult(data, int(usage["input_tokens"]), int(usage["output_tokens"]), body.get("id"))
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DomainError("AI_RESPONSE_INVALID", "AI 구조화 응답을 검증하지 못했습니다.", 502, retryable=False) from exc

    async def map_discovery(self, steps: list[dict], elements: list[dict]) -> GatewayResult:
        """Map test intent to server-owned element IDs without allowing selector invention."""
        return await self._request_json(
            instructions=(
                "Match each QA step to zero or more page element IDs by meaning. "
                "Use only elementId values present in the input. Never create selectors, values, "
                "credentials, or actions. Return an empty candidateIds list when uncertain."
            ),
            input_data={"steps": steps, "elements": elements},
            schema_name="page_element_mapping",
            schema=_DISCOVERY_MAPPING_SCHEMA,
        )

    async def _request_json(self, *, instructions: str, input_data: dict, schema_name: str, schema: dict) -> GatewayResult:
        key = self.settings.openai_api_key.get_secret_value() if self.settings.openai_api_key else ""
        payload = {
            "model": self.settings.openai_model,
            "store": False,
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "instructions": instructions,
            "input": json.dumps(input_data, ensure_ascii=False, separators=(",", ":")),
            "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        }
        return await self._send(payload, key)

    async def _send(self, payload: dict, key: str) -> GatewayResult:
        try:
            async with httpx.AsyncClient(timeout=self.settings.openai_timeout_seconds) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise DomainError("AI_TIMEOUT", "AI 요청 시간이 초과되었습니다.", 504, retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise DomainError("AI_UPSTREAM_ERROR", "AI 서비스를 호출하지 못했습니다.", 502, retryable=status >= 500, details={"upstreamStatus": status}) from exc
        except httpx.HTTPError as exc:
            raise DomainError("AI_UPSTREAM_ERROR", "AI 서비스에 연결하지 못했습니다.", 502, retryable=True) from exc
        body = response.json()
        try:
            output_text = next(
                content["text"]
                for item in body["output"] if item.get("type") == "message"
                for content in item.get("content", []) if content.get("type") == "output_text"
            )
            usage = body["usage"]
            return GatewayResult(json.loads(output_text), int(usage["input_tokens"]), int(usage["output_tokens"]), body.get("id"))
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DomainError("AI_RESPONSE_INVALID", "AI 응답을 검증하지 못했습니다.", 502, retryable=False) from exc


_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "preconditions": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "id": {"type": "string"}, "title": {"type": "string"}, "note": {"type": "string"},
                "action": {"type": "string", "enum": ["navigate", "click", "fill", "select", "press", "scroll", "wait", "upload", "assert"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "url": {"type": ["string", "null"]}, "selector": {"type": ["string", "null"]},
                "value": {"type": ["string", "null"]}, "operator": {"type": ["string", "null"]},
                "expected": {"type": ["string", "null"]},
                "timeoutMs": {"type": ["integer", "null"], "minimum": 100, "maximum": 60000},
            }, "required": ["id", "title", "note", "action", "confidence", "url", "selector", "value", "operator", "expected", "timeoutMs"],
        }},
        "assertions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["url", "element", "text", "attribute", "count", "network", "visual_change"]},
                "operator": {"type": "string"}, "expected": {"type": "string"},
                "timeoutMs": {"type": "integer", "minimum": 100, "maximum": 60000},
            }, "required": ["type", "operator", "expected", "timeoutMs"],
        }},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["preconditions", "steps", "assertions", "assumptions", "confidence"],
}


_DISCOVERY_MAPPING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "stepId": {"type": "string"},
                    "candidateIds": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
                },
                "required": ["stepId", "candidateIds"],
            },
        }
    },
    "required": ["mappings"],
}
