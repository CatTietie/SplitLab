import time
import uuid

import redis.asyncio as redis

TIMER_ZSET_KEY = "splitlab:rollout_timers"
TIMER_LOCK_KEY = "splitlab:rollout_timer_lock"
REMAINING_KEY_PREFIX = "splitlab:rollout_remaining:"


async def schedule_timer(redis_client: redis.Redis, experiment_id: uuid.UUID, hold_seconds: int):
    fire_at = time.time() + hold_seconds
    await redis_client.zadd(TIMER_ZSET_KEY, {str(experiment_id): fire_at})


async def cancel_timer(redis_client: redis.Redis, experiment_id: uuid.UUID):
    await redis_client.zrem(TIMER_ZSET_KEY, str(experiment_id))


async def get_expired_timers(redis_client: redis.Redis) -> list[str]:
    now = time.time()
    results = await redis_client.zrangebyscore(TIMER_ZSET_KEY, "-inf", now)
    return [r.decode() if isinstance(r, bytes) else r for r in results]


async def get_remaining_seconds(redis_client: redis.Redis, experiment_id: uuid.UUID) -> int | None:
    score = await redis_client.zscore(TIMER_ZSET_KEY, str(experiment_id))
    if score is None:
        return None
    remaining = score - time.time()
    return max(0, int(remaining))


async def save_remaining(redis_client: redis.Redis, experiment_id: uuid.UUID):
    remaining = await get_remaining_seconds(redis_client, experiment_id)
    if remaining is not None:
        key = f"{REMAINING_KEY_PREFIX}{experiment_id}"
        await redis_client.set(key, str(remaining), ex=86400)


async def pop_remaining(redis_client: redis.Redis, experiment_id: uuid.UUID) -> int | None:
    key = f"{REMAINING_KEY_PREFIX}{experiment_id}"
    val = await redis_client.get(key)
    if val is not None:
        await redis_client.delete(key)
        return int(val)
    return None
