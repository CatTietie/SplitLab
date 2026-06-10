import json
from datetime import datetime, timezone

import redis.asyncio as redis


async def publish_event(redis_client: redis.Redis, event_type: str, payload: dict):
    event = {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.publish("splitlab:events", json.dumps(event))
