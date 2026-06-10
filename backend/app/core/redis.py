import redis.asyncio as redis

from app.core.config import settings

redis_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> redis.Redis:
    client = redis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()
