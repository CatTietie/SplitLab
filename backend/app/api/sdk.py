from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.event import EventBatch
from app.services.config_service import get_cached_config
from app.services.event_service import ingest_events

router = APIRouter(prefix="/api/v1/sdk", tags=["sdk"])


@router.get("/config")
async def get_sdk_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    config_json, etag = await get_cached_config(redis_client, db)

    client_etag = request.headers.get("If-None-Match")
    if client_etag and client_etag.strip('"') == etag:
        return Response(status_code=304)

    return Response(
        content=config_json,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.post("/events")
async def post_events(batch: EventBatch, db: AsyncSession = Depends(get_db)):
    count = await ingest_events(db, batch)
    return {"accepted": count}
