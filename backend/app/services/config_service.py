import hashlib

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Experiment, ExperimentLayer
from app.schemas.sdk_config import SDKConfigResponse, LayerConfig, ExperimentConfig, GroupConfig
from app.services.traffic_math import compute_effective_traffic


async def build_sdk_config(db: AsyncSession) -> SDKConfigResponse:
    result = await db.execute(
        select(ExperimentLayer)
        .options(
            selectinload(ExperimentLayer.experiments)
            .selectinload(Experiment.groups),
            selectinload(ExperimentLayer.experiments)
            .selectinload(Experiment.whitelists),
        )
    )
    layers = result.scalars().all()

    layer_configs = []
    for layer in layers:
        experiments = []
        for exp in layer.experiments:
            if exp.status not in ("running", "full_rollout"):
                continue
            whitelist_map = {}
            for wl in exp.whitelists:
                group = next((g for g in exp.groups if g.id == wl.group_id), None)
                if group:
                    whitelist_map[wl.user_id] = group.name

            effective = compute_effective_traffic(
                exp.rollout_steps, exp.current_step_index, exp.groups
            )

            experiments.append(ExperimentConfig(
                id=str(exp.id),
                key=exp.key,
                status=exp.status,
                bucket_start=exp.bucket_start,
                bucket_end=exp.bucket_end,
                groups=[
                    GroupConfig(
                        id=str(g.id),
                        name=g.name,
                        traffic_percentage=pct,
                        config_json=g.config_json,
                    )
                    for g, pct in effective
                ],
                whitelist=whitelist_map,
            ))

        layer_configs.append(LayerConfig(
            id=str(layer.id),
            name=layer.name,
            salt=layer.salt,
            experiments=experiments,
        ))

    config = SDKConfigResponse(layers=layer_configs, version="1")
    return config


def compute_etag(config_json: str) -> str:
    return hashlib.md5(config_json.encode()).hexdigest()


async def get_cached_config(redis_client: redis.Redis, db: AsyncSession) -> tuple[str, str]:
    cached = await redis_client.get("sdk:config")
    etag = await redis_client.get("sdk:config:etag")

    if cached and etag:
        return cached, etag

    config = await build_sdk_config(db)
    config_json = config.model_dump_json()
    etag = compute_etag(config_json)

    await redis_client.set("sdk:config", config_json, ex=300)
    await redis_client.set("sdk:config:etag", etag, ex=300)

    return config_json, etag


async def invalidate_config_cache(redis_client: redis.Redis):
    await redis_client.delete("sdk:config", "sdk:config:etag")
