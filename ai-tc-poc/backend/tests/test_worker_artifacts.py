from uuid import uuid4

import pytest

from app.workers import playwright_worker
from app.workers.artifacts import StoredArtifact


@pytest.mark.asyncio
async def test_capture_screenshot_persists_success_artifact(monkeypatch) -> None:
    execution_id = uuid4()
    step_run_id = uuid4()
    recorded = {}

    class Page:
        async def screenshot(self, *, full_page):
            assert full_page is False
            return b"success-png"

    class Store:
        async def put_png(self, object_key, content):
            assert content == b"success-png"
            return StoredArtifact(object_key=object_key, sha256="a" * 64, size_bytes=len(content))

    async def record_artifact(actual_execution_id, actual_step_run_id, stored, artifact_type):
        recorded.update(
            execution_id=actual_execution_id,
            step_run_id=actual_step_run_id,
            stored=stored,
            artifact_type=artifact_type,
        )

    monkeypatch.setattr(playwright_worker, "ArtifactStore", Store)
    monkeypatch.setattr(playwright_worker, "_record_artifact", record_artifact)

    await playwright_worker._capture_screenshot(
        Page(),
        execution_id,
        2,
        step_run_id,
        artifact_type="SUCCESS_SCREENSHOT",
        filename="success.png",
        full_page=False,
    )

    assert recorded["execution_id"] == execution_id
    assert recorded["step_run_id"] == step_run_id
    assert recorded["stored"].object_key == f"executions/{execution_id}/steps/2/success.png"
    assert recorded["artifact_type"] == "SUCCESS_SCREENSHOT"
