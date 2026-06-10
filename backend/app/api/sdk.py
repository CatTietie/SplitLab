from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.event import EventBatch
from app.schemas.targeting import AttributeBatchRequest
from app.services.config_service import get_cached_config
from app.services.event_service import ingest_events
from app.services.attribute_service import upsert_attributes, AttributeValidationError

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


@router.post("/attributes")
async def upload_attributes(
    request: AttributeBatchRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    total = 0
    for user_upload in request.users:
        try:
            await upsert_attributes(db, redis_client, user_upload.user_id, user_upload.attributes)
            total += len(user_upload.attributes)
        except AttributeValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"accepted": total}
