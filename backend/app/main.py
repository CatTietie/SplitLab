import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import redis.asyncio as redis

from app.api import api_router
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


async def _rollout_timer_loop(app: FastAPI):
    from app.core.database import async_session
    from app.core.redis import redis_pool
    from app.services.rollout_timer import TIMER_ZSET_KEY, TIMER_LOCK_KEY, get_expired_timers, cancel_timer
    from app.services.rollout_engine import advance_step, rollback_step, check_guardrails

    while True:
        await asyncio.sleep(5)
        try:
            redis_client = redis.Redis(connection_pool=redis_pool)
            lock = redis_client.lock(TIMER_LOCK_KEY, timeout=10)
            if await lock.acquire(blocking=False):
                try:
                    import uuid
                    expired = await get_expired_timers(redis_client)
                    for exp_id_str in expired:
                        await cancel_timer(redis_client, uuid.UUID(exp_id_str))
                        try:
                            async with async_session() as db:
                                experiment_id = uuid.UUID(exp_id_str)
                                result = await check_guardrails(db, redis_client, experiment_id)
                                if result == "rollback":
                                    await rollback_step(db, redis_client, experiment_id, "guardrail_rollback")
                                else:
                                    await advance_step(db, redis_client, experiment_id, "auto_advance")
                        except Exception as e:
                            logger.error(f"Error processing timer for {exp_id_str}: {e}")
                finally:
                    try:
                        await lock.release()
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Timer loop error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_rollout_timer_loop(app))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="SplitLab", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/health")
    async def health_check(redis_client: redis.Redis = Depends(get_redis)):
        await redis_client.set("backend:heartbeat", str(datetime.now(timezone.utc).timestamp()), ex=30)
        return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/v1/events/stream")
    async def event_stream(request: Request, redis_client: redis.Redis = Depends(get_redis)):
        """SSE endpoint for real-time experiment events (config changes, recovery)."""
        async def generate():
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("splitlab:events")
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message["type"] == "message":
                        data = message["data"]
                        yield f"data: {data}\n\n"
                    else:
                        yield f": keepalive\n\n"
                    await asyncio.sleep(0.5)
            finally:
                await pubsub.unsubscribe("splitlab:events")
                await pubsub.aclose()

        return StreamingResponse(generate(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        })

    return app


app = create_app()
