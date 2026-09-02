import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.db.models import Environment, TestCaseVersion


SUPPORTED_ACTIONS = {"navigate", "fill", "click", "assert"}


class ExecutionPlanError(Exception):
    def __init__(self, code: str, message: str, *, step_no: int | None = None):
        self.code = code
        self.message = message
        self.step_no = step_no


@dataclass(frozen=True)
class ValidatedExecutionPlan:
    version_id: str
    status: str
    revision: int
    plan_hash: str
    source: str
    environment: dict[str, str]
    steps: list[dict[str, Any]]

    @property
    def public_steps(self) -> list[dict[str, Any]]:
        return [
            {**step, "value": "***" if step.get("value") else None}
            for step in self.steps
        ]


def validate_execution_plan(version: TestCaseVersion, environment: Environment) -> ValidatedExecutionPlan:
    spec = version.structured_spec or {}
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
            "timeoutMs": int(source.get("timeoutMs") or 10_000),
        }
        if action == "navigate":
            step["url"] = step["url"] or environment.base_url
            _validate_target_url(step["url"], environment.allowed_domains, step_no)
        elif action == "fill":
            _require(step, "selector", step_no)
            if not step.get("value") and not step.get("secretRef"):
                raise ExecutionPlanError("STEP_PARAMETER_MISSING", "fill 단계에 value 또는 secretRef가 필요합니다.", step_no=step_no)
        elif action == "click":
            _require(step, "selector", step_no)
        elif action == "assert":
            for field in ("selector", "operator", "expected"):
                _require(step, field, step_no)
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
            "timeoutMs": int(source.get("timeoutMs") or 10_000),
        })
    return preview


def _require(step: dict[str, Any], field: str, step_no: int) -> None:
    if step.get(field) is None or step.get(field) == "":
        raise ExecutionPlanError("STEP_PARAMETER_MISSING", f"{step['action']} 단계에 {field} 값이 필요합니다.", step_no=step_no)


def _validate_target_url(url: str, allowed_domains: list[str], step_no: int) -> None:
    host = urlparse(url).hostname
    if not host or host not in allowed_domains:
        raise ExecutionPlanError("TARGET_URL_NOT_ALLOWED", "허용되지 않은 테스트 대상 주소입니다.", step_no=step_no)
