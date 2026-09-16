from dataclasses import dataclass
import json
from typing import Any

from playwright.async_api import Page, expect
import re


class StepDefinitionError(Exception):
    pass


class StepAssertionError(AssertionError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class StepResult:
    action: dict[str, Any]
    assertion: dict[str, Any] | None = None


def _required(step: dict[str, Any], field: str) -> Any:
    value = step.get(field)
    if value is None or value == "":
        raise StepDefinitionError(f"{step.get('action', 'unknown')} 단계에 {field} 값이 필요합니다.")
    return value


async def wait_for_render(page: Page, timeout: int) -> None:
    await page.wait_for_load_state("load", timeout=timeout)
    await page.locator("body").wait_for(state="visible", timeout=timeout)
    await page.wait_for_timeout(750)


async def execute_step(page: Page, step: dict[str, Any], base_url: str) -> StepResult:
    action_type = _required(step, "action")
    timeout = int(step.get("timeoutMs", 10_000))
    if action_type == 'wait':
        if step.get('operator') != 'domcontentloaded':
            raise StepDefinitionError('문서 로딩 완료 대기만 지원합니다.')
        await wait_for_render(page, timeout)
        return StepResult(action={'type': 'wait', 'state': 'rendered'})

    if action_type == "navigate":
        url = step.get("url") or base_url
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if response and response.status >= 400:
            raise AssertionError(f"HTTP {response.status}")
        await wait_for_render(page, timeout)
        return StepResult(action={"type": "navigate", "url": url})

    if action_type == "assert" and (step.get("assertionType") == "url" or (step.get("url") and not step.get("selector"))):
        operator = step.get("operator", "contains")
        expected = str(_required(step, "expected"))
        if operator == "equals":
            await expect(page).to_have_url(expected, timeout=timeout)
        elif operator in {"contains", "matches"}:
            if expected not in page.url:
                raise AssertionError(f"URL does not contain expected value: {expected}")
        else:
            raise StepDefinitionError(f"지원하지 않는 URL assertion operator입니다: {operator}")
        assertion = {"type": "url", "operator": operator, "expected": expected}
        return StepResult(action={"type": "assert", "url": page.url}, assertion=assertion)

    if action_type == "assert" and step.get("assertionType") == "observed_state":
        from app.modules.discoveries.page_first import area_fingerprints, collect_elements, page_fingerprint
        selector = _required(step, "selector")
        expected = _required(step, "expected")
        if not isinstance(expected, dict):
            raise StepDefinitionError("observed_state expected는 객체여야 합니다.")
        locator = selector_locator(page, selector)
        if await locator.count() != 1:
            raise StepAssertionError("INTERACTION_TARGET_AMBIGUOUS", "관찰 대상 요소가 하나가 아닙니다.")
        elements = await collect_elements(page)
        actual = {"url": page.url, "ariaPressed": await locator.get_attribute("aria-pressed"),
            "ariaSelected": await locator.get_attribute("aria-selected"),
            "checked": await locator.is_checked() if await locator.get_attribute("type") in {"checkbox", "radio"} else None,
            "pageFingerprint": page_fingerprint(page.url, elements)}
        for field in ("url", "ariaPressed", "ariaSelected", "checked", "pageFingerprint"):
            if field in expected and actual[field] != expected[field]:
                raise StepAssertionError("EXPECTED_STATE_NOT_CHANGED", f"관찰 상태가 일치하지 않습니다: {field}")
        if "areas" in expected:
            current = area_fingerprints(elements)
            for area in expected["areas"]:
                key = json.dumps([area.get("kind"), area.get("name")], ensure_ascii=False, separators=(",", ":"))
                observed = current.get(key) or {}
                if (observed.get("itemCount") != area.get("afterItemCount")
                        or observed.get("fingerprint") != area.get("afterFingerprint")):
                    raise StepAssertionError("LIST_CHANGE_NOT_OBSERVED", "관찰된 영역 상태가 분석 결과와 일치하지 않습니다.")
        return StepResult(action={"type": "assert", "selector": selector},
            assertion={"type": "observed_state", "selector": selector, "expected": expected})

    selector = _required(step, "selector")
    locator = selector_locator(page, selector)
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
        assertion = {"type": step.get("assertionType") or "text", "selector": selector, "operator": operator, "expected": expected}
        return StepResult(action={"type": "assert", "selector": selector}, assertion=assertion)

    raise StepDefinitionError(f"지원하지 않는 action입니다: {action_type}")


def selector_locator(page: Page, selector: str):
    role_match = re.fullmatch(r'role=([^\[]+)\[name="(.*)"\]', selector)
    if role_match:
        return page.get_by_role(role_match.group(1), name=role_match.group(2), exact=True)
    text_match = re.fullmatch(r'text="(.*)"', selector)
    if text_match:
        return page.get_by_text(text_match.group(1), exact=True)
    label_match = re.fullmatch(r'label="(.*)"', selector)
    if label_match:
        return page.get_by_label(label_match.group(1), exact=True)
    placeholder_match = re.fullmatch(r'placeholder="(.*)"', selector)
    if placeholder_match:
        return page.get_by_placeholder(placeholder_match.group(1), exact=True)
    return page.locator(selector)
