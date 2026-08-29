import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import Request

from app.schemas.executions import ExecutionDetailsResponse


TERMINAL_STATUSES = {"PASS", "FAIL", "BLOCKED", "NEEDS_REVIEW", "CANCELLED", "SYSTEM_ERROR"}


def _event(name: str, data: dict[str, Any], event_id: int) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event_id}\nevent: {name}\ndata: {payload}\n\n"


async def execution_event_stream(
    request: Request,
    load_details: Callable[[], Awaitable[ExecutionDetailsResponse | None]],
    *,
    interval_seconds: float = 1.0,
) -> AsyncIterator[str]:
    previous: str | None = None
    event_id = 0
    while not await request.is_disconnected():
        details = await load_details()
        if details is None:
            event_id += 1
            yield _event("error", {"code": "EXECUTION_NOT_FOUND"}, event_id)
            return
        snapshot = details.model_dump(mode="json")
        signature = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if signature != previous:
            event_id += 1
            yield _event("execution.updated", snapshot, event_id)
            previous = signature
        if details.execution.status in TERMINAL_STATUSES:
            event_id += 1
            yield _event("execution.completed", snapshot, event_id)
            return
        await asyncio.sleep(interval_seconds)
