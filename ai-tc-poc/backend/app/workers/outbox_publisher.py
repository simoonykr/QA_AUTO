import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.db.models import OutboxEvent, OutboxStatus


logger = logging.getLogger(__name__)
settings = get_settings()


async def publish_batch(redis: Redis) -> int:
    async with SessionFactory() as session:
        events = list((await session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING, OutboxEvent.available_at <= datetime.now(UTC))
            .order_by(OutboxEvent.created_at)
            .limit(settings.outbox_batch_size)
            .with_for_update(skip_locked=True)
        )).all())
        for event in events:
            try:
                await redis.xadd(settings.redis_execution_stream, {
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "aggregate_id": str(event.aggregate_id),
                    "organization_id": str(event.organization_id),
                    "payload": json.dumps(event.payload, ensure_ascii=False),
                })
                event.status = OutboxStatus.PUBLISHED
                event.published_at = datetime.now(UTC)
            except Exception:
                event.attempts += 1
                if event.attempts >= settings.outbox_max_attempts:
                    event.status = OutboxStatus.FAILED
                else:
                    event.available_at = datetime.now(UTC) + timedelta(seconds=min(60, 2 ** event.attempts))
                logger.exception("outbox event publish failed", extra={"event_id": str(event.id)})
        await session.commit()
        return len(events)


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            count = await publish_batch(redis)
            if count == 0:
                await asyncio.sleep(settings.outbox_poll_interval_seconds)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
