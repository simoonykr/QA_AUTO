"""Opt-in real Chromium regression; synthetic HTML, no external requests or AI.

Run with RUN_BROWSER_TESTS=1 after `python -m playwright install chromium`.
This exercises browser components, not PostgreSQL/queue/artifact integration.
"""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from playwright.async_api import async_playwright

from app.modules.discoveries.page_first import collect_elements, page_fingerprint, scenario_payload
from app.modules.discoveries.review import ReviewRequest, Selection, apply_selections, selected_steps
from app.workers.playwright_worker import _verify_page_first_snapshot, WorkerExecutionError
from app.workers.step_executor import execute_step

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1", reason="opt-in real Chromium test")]


async def test_real_browser_collect_review_assert_and_detect_change():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(service_workers="block")
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            await page.set_content('''<button data-testid="menu" aria-label="Menu">Menu</button>
                <span data-testid="hidden" hidden>Hidden</span>
                <span data-testid="duplicate">One</span><span data-testid="duplicate">Two</span>
                <input data-testid="password" value="synthetic-only">
                <input data-testid="entry" value="synthetic-only">''')
            elements = await collect_elements(page)
            assert {e["name"] for e in elements} == {"Menu", "hidden", "entry"}
            assert "synthetic-only" not in str(elements)
            fingerprint = page_fingerprint(page.url, elements)
            result = {"elements": elements, "fingerprint": fingerprint,
                "pages": [{"url": page.url, "fingerprint": fingerprint}]}
            payload = scenario_payload(SimpleNamespace(id=uuid4(), result=result))
            assert len(payload["steps"]) == 2
            reviewed = apply_selections(payload, ReviewRequest(expectedRevision=1, selections=[
                Selection(comparisonId=row["id"], decision="ADD") for row in payload["comparisons"]]))
            await _verify_page_first_snapshot(page, {"fingerprint": fingerprint})
            for step in selected_steps(reviewed):
                outcome = await execute_step(page, {"action": "assert", "selector": step["selector"],
                    "assertionType": "element", "operator": "visible", "expected": "true"}, page.url)
                assert outcome.assertion["operator"] == "visible"
            await page.locator('[data-testid="menu"]').evaluate("node => node.hidden = true")
            with pytest.raises(WorkerExecutionError) as error:
                await _verify_page_first_snapshot(page, {"fingerprint": fingerprint})
            assert error.value.code == "DISCOVERY_STALE"
        finally:
            await browser.close()
