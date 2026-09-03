import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.db.models import Environment, TestCaseVersion


SUPPORTED_ACTIONS = {"navigate", "fill", "click", "assert"}


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
        if action in {"fill", "click", "assert"} and step.get("resolutionStatus") in {"UNRESOLVED", "RESOLVING", "AMBIGUOUS", "NOT_FOUND", "STALE"}:
            raise ExecutionPlanError(
                "SELECTOR_RESOLUTION_REQUIRED", "페이지 분석으로 화면 요소를 확정해야 합니다.",
                step_no=step_no, step_id=step["id"], missing_fields=["selector"],
            )
        if action == "navigate":
            step["url"] = step["url"] or environment.base_url
            _validate_target_url(step["url"], environment.allowed_domains, step_no)
        elif action == "fill":
            _require(step, ["selector"], step_no)
            if not step.get("value") and not step.get("secretRef"):
                raise ExecutionPlanError("STEP_PARAMETER_MISSING", "fill 단계에 value 또는 secretRef가 필요합니다.", step_no=step_no, step_id=step["id"], missing_fields=["value", "secretRef"])
        elif action == "click":
            _require(step, ["selector"], step_no)
        elif action == "assert":
            assertion_type = step.get("assertionType") or ("url" if step.get("url") and not step.get("selector") else "text")
            step["assertionType"] = assertion_type
            required = ["url", "operator", "expected"] if assertion_type == "url" else ["selector", "operator", "expected"]
            _require(step, required, step_no)
            if assertion_type == "url":
                _validate_target_url(step["url"], environment.allowed_domains, step_no, step["id"])
        normalized.append(step)

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
            "url": (source.get("url") or environment.base_url) if action == "navigate" else source.get("url"),
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


def _validate_target_url(url: str, allowed_domains: list[str], step_no: int, step_id: str | None = None) -> None:
    host = urlparse(url).hostname
    if not host or host not in allowed_domains:
        raise ExecutionPlanError("TARGET_URL_NOT_ALLOWED", "허용되지 않은 테스트 대상 주소입니다.", step_no=step_no, step_id=step_id)
