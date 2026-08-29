from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page, expect


class StepDefinitionError(Exception):
    pass


@dataclass(frozen=True)
class StepResult:
    action: dict[str, Any]
    assertion: dict[str, Any] | None = None


def _required(step: dict[str, Any], field: str) -> Any:
    value = step.get(field)
    if value is None or value == "":
        raise StepDefinitionError(f"{step.get('action', 'unknown')} 단계에 {field} 값이 필요합니다.")
    return value


async def execute_step(page: Page, step: dict[str, Any], base_url: str) -> StepResult:
    action_type = _required(step, "action")
    timeout = int(step.get("timeoutMs", 10_000))

    if action_type == "navigate":
        url = step.get("url") or base_url
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if response and response.status >= 400:
            raise AssertionError(f"HTTP {response.status}")
        return StepResult(action={"type": "navigate", "url": url})

    selector = _required(step, "selector")
    locator = page.locator(selector)
    if action_type == "fill":
        value = str(_required(step, "value"))
        await locator.fill(value, timeout=timeout)
        return StepResult(action={"type": "fill", "selector": selector, "value": "***"})
    if action_type == "click":
        await locator.click(timeout=timeout)
        return StepResult(action={"type": "click", "selector": selector})
    if action_type == "assert":
        operator = step.get("operator", "contains")
        expected = str(_required(step, "expected"))
        if operator == "equals":
            await expect(locator).to_have_text(expected, timeout=timeout)
        elif operator == "visible":
            await expect(locator).to_be_visible(timeout=timeout)
        elif operator == "contains":
            await expect(locator).to_contain_text(expected, timeout=timeout)
        else:
            raise StepDefinitionError(f"지원하지 않는 assertion operator입니다: {operator}")
        assertion = {"type": "text", "selector": selector, "operator": operator, "expected": expected}
        return StepResult(action={"type": "assert", "selector": selector}, assertion=assertion)

    raise StepDefinitionError(f"지원하지 않는 action입니다: {action_type}")
