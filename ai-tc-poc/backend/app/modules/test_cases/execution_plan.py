import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.db.models import Environment, TestCaseVersion


SUPPORTED_ACTIONS = {"navigate", "reload", "fill", "click", "select", "scroll", "assert", "wait"}


class ExecutionPlanError(Exception):
    def __init__(self, code: str, message: str, *, step_no: int | None = None, step_id: str | None = None, missing_fields: list[str] | None = None):
        self.code = code
        self.message = message
        self.step_no = step_no
        self.step_id = step_id
        self.missing_fields = missing_fields or []


@dataclass(frozen=True)
class ValidatedExecutionPlan:
    version_id: str
    status: str
    revision: int
    plan_hash: str
    source: str
    environment: dict[str, str]
    steps: list[dict[str, Any]]
    automation_status: str
    automation_reason: str

    @property
    def public_steps(self) -> list[dict[str, Any]]:
        return [
            {**step, "value": "***" if step.get("value") else None}
            for step in self.steps
        ]


def validate_execution_plan(version: TestCaseVersion, environment: Environment) -> ValidatedExecutionPlan:
    spec = version.structured_spec or {}
    page_first = spec.get("pageFirst")
    if page_first and (page_first.get("environmentId") != str(environment.id)
                       or page_first.get("revision") != spec.get("planRevision")):
        raise ExecutionPlanError("SCENARIO_SNAPSHOT_INVALID", "승인된 시나리오 환경·revision과 일치하지 않습니다.")
    if spec.get("automationStatus") == "UNSUPPORTED":
        raise ExecutionPlanError("AUTOMATION_UNSUPPORTED", str(spec.get("automationReason") or "자동 실행을 지원하지 않는 테스트입니다."))
    source_steps = spec.get("steps")
    if not isinstance(source_steps, list) or not source_steps:
        raise ExecutionPlanError("EXECUTION_PLAN_INVALID", "실행할 구조화 단계가 없습니다.")

    normalized: list[dict[str, Any]] = []
    for step_no, source in enumerate(source_steps, start=1):
        if not isinstance(source, dict):
            raise ExecutionPlanError("EXECUTION_PLAN_INVALID", "단계 형식이 올바르지 않습니다.", step_no=step_no)
        action = source.get("action")
        if action not in SUPPORTED_ACTIONS:
            raise ExecutionPlanError("UNSUPPORTED_ACTION", f"지원하지 않는 action입니다: {action}", step_no=step_no)
        if action == 'wait' and source.get('operator') != 'domcontentloaded':
            raise ExecutionPlanError('UNSUPPORTED_ACTION', '문서 로딩 완료 대기만 지원합니다.', step_no=step_no)
        step = {
            "stepNo": step_no,
            "id": str(source.get("id") or f"step-{step_no}"),
            "title": str(source.get("title") or f"단계 {step_no}"),
            "action": action,
            "url": source.get("url"),
            "selector": source.get("selector"),
            "value": source.get("value"),
            "secretRef": source.get("secretRef"),
            "operator": source.get("operator"),
            "expected": source.get("expected"),
            "assertionType": source.get("assertionType"),
            "timeoutMs": int(source.get("timeoutMs") or 10_000),
            "targetDescription": source.get("targetDescription"),
            "selectorHint": source.get("selectorHint") or {},
            "resolutionStatus": source.get("resolutionStatus"),
        }
        if action in {"fill", "click", "select", "scroll", "assert"} and step.get("resolutionStatus") in {"UNRESOLVED", "RESOLVING", "AMBIGUOUS", "NOT_FOUND", "STALE"}:
            raise ExecutionPlanError(
                "PAGE_ANALYSIS_REQUIRED", "페이지 분석으로 화면 요소를 확정해야 합니다.",
                step_no=step_no, step_id=step["id"], missing_fields=["selector"],
            )
        if action == "navigate":
            if not step["url"]:
                raise ExecutionPlanError("TARGET_URL_REQUIRED", "원문 대상 URL이 없는 이동 단계입니다. 대상 URL을 명시해 다시 분석해 주세요.", step_no=step_no)
            _validate_target_url(step["url"], environment.allowed_domains, step_no)
        elif action == "reload":
            pass
        elif action == "fill":
            _require_selector(step, step_no)
            if not step.get("value") and not step.get("secretRef"):
                raise ExecutionPlanError("STEP_PARAMETER_MISSING", "fill 단계에 value 또는 secretRef가 필요합니다.", step_no=step_no, step_id=step["id"], missing_fields=["value", "secretRef"])
        elif action == "click":
            _require_selector(step, step_no)
        elif action == "select":
            _require_selector(step, step_no)
            _require(step, ["value"], step_no)
        elif action == "scroll":
            if step.get("selector") is None:
                _require(step, ["value"], step_no)
        elif action == "assert":
            assertion_type = step.get("assertionType") or ("url" if step.get("url") and not step.get("selector") else "text")
            step["assertionType"] = assertion_type
            required = (["operator", "expected"] if assertion_type in {"url", "page_title"} else
                ["selector", "expected"] if assertion_type == "observed_state" else ["selector", "operator", "expected"])
            if "selector" in required:
                _require_selector(step, step_no)
                required = [field for field in required if field != "selector"]
            _require(step, required, step_no)
            if assertion_type in {"url", "page_title"} and _is_placeholder_expectation(step.get("expected")):
                raise ExecutionPlanError(
                    "ASSERTION_EXPECTED_REQUIRED", "URL·페이지 제목 검증에는 구체적인 기대값이 필요합니다.",
                    step_no=step_no, step_id=step["id"], missing_fields=["expected"],
                )
            if assertion_type == "observed_state" and not isinstance(step.get("expected"), dict):
                raise ExecutionPlanError("STEP_PARAMETER_INVALID", "observed_state expected는 객체여야 합니다.",
                    step_no=step_no, step_id=step["id"])
            if assertion_type == "url" and step.get("url"):
                _validate_target_url(step["url"], environment.allowed_domains, step_no, step["id"])
        normalized.append(step)

    normalized = _order_execution_steps(normalized)
    for step_no, step in enumerate(normalized, start=1):
        step["stepNo"] = step_no

    revision = int(spec.get("planRevision") or 1)
    canonical = json.dumps({
        "versionId": str(version.id),
        "revision": revision,
        "environmentId": str(environment.id),
        "baseUrl": environment.base_url,
        "steps": normalized,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return ValidatedExecutionPlan(
        version_id=str(version.id),
        status=version.status.value if hasattr(version.status, "value") else str(version.status),
        revision=revision,
        plan_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source=str(spec.get("source") or "RULE_BASED"),
        environment={"id": str(environment.id), "name": environment.name, "baseUrl": environment.base_url},
        steps=normalized,
        automation_status=str(spec.get("automationStatus") or "MANUAL_REVIEW_REQUIRED"),
        automation_reason=str(spec.get("automationReason") or "실행 가능성을 검토해야 합니다."),
    )


def preview_execution_steps(version: TestCaseVersion, environment: Environment) -> list[dict[str, Any]]:
    source_steps = (version.structured_spec or {}).get("steps") or []
    preview = []
    for step_no, source in enumerate(source_steps, start=1):
        if not isinstance(source, dict):
            continue
        action = str(source.get("action") or "unknown")
        preview.append({
            "stepNo": step_no,
            "id": str(source.get("id") or f"step-{step_no}"),
            "title": str(source.get("title") or f"단계 {step_no}"),
            "action": action,
            "url": source.get("url"),
            "selector": source.get("selector"),
            "value": "***" if source.get("value") else None,
            "secretRef": source.get("secretRef"),
            "operator": source.get("operator"),
            "expected": source.get("expected"),
            "assertionType": source.get("assertionType") or ("url" if action == "assert" and source.get("url") and not source.get("selector") else ("text" if action == "assert" else None)),
            "timeoutMs": int(source.get("timeoutMs") or 10_000),
            "targetDescription": source.get("targetDescription"),
            "selectorHint": source.get("selectorHint") or {},
            "resolutionStatus": source.get("resolutionStatus"),
        })
    return preview


def _require(step: dict[str, Any], fields: list[str], step_no: int) -> None:
    missing = [field for field in fields if step.get(field) is None or step.get(field) == ""]
    if missing:
        raise ExecutionPlanError(
            "STEP_PARAMETER_MISSING", f"{step['action']} 단계에 {', '.join(missing)} 값이 필요합니다.",
            step_no=step_no, step_id=step["id"], missing_fields=missing,
        )


def _require_selector(step: dict[str, Any], step_no: int) -> None:
    if not step.get("selector"):
        raise ExecutionPlanError(
            "SELECTOR_REQUIRED", "화면 요소 단계에 검증된 selector가 필요합니다.",
            step_no=step_no, step_id=step["id"], missing_fields=["selector"],
        )


def _is_placeholder_expectation(value: Any) -> bool:
    if not isinstance(value, str):
        return value is None
    normalized = re.sub(r"\s+", "", value).lower()
    return normalized in {"", "확인", "검증", "주소확인", "url확인", "제목확인", "탭제목확인"}


def _order_execution_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep stable order inside groups while enforcing page-first execution."""
    indexed = list(enumerate(steps))
    first_navigate = next((index for index, step in indexed if step.get("action") == "navigate"), None)

    def rank(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, step = item
        if first_navigate is not None and index == first_navigate:
            return (0, index)
        if step.get("action") == "reload":
            return (1, index)
        if step.get("action") == "wait":
            return (2, index)
        if step.get("action") == "assert" and step.get("assertionType") == "page_title":
            return (3, index)
        if step.get("action") == "assert" and step.get("assertionType") == "url":
            return (4, index)
        return (5, index)

    return [step for _, step in sorted(indexed, key=rank)]


def _validate_target_url(url: str, allowed_domains: list[str], step_no: int, step_id: str | None = None) -> None:
    host = urlparse(url).hostname
    if not host or host not in allowed_domains:
        raise ExecutionPlanError("TARGET_URL_NOT_ALLOWED", "허용되지 않은 테스트 대상 주소입니다.", step_no=step_no, step_id=step_id)
