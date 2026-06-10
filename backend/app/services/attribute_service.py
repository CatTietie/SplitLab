import re

import redis.asyncio as redis
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.user_attribute import UserAttribute

ATTR_KEY_RE = re.compile(r"^[a-z_]+$")
ATTR_KEY_MAX = 64
ATTR_VALUE_MAX = 256
MAX_ATTRS_PER_USER = 20
REDIS_TTL = 3600


class AttributeValidationError(Exception):
    pass


def validate_attributes(attributes: dict[str, str]) -> None:
    if len(attributes) > MAX_ATTRS_PER_USER:
        raise AttributeValidationError(f"Maximum {MAX_ATTRS_PER_USER} attributes per user")
    for key, value in attributes.items():
        if len(key) > ATTR_KEY_MAX or not ATTR_KEY_RE.match(key):
            raise AttributeValidationError(f"Invalid attribute key: {key}")
        if len(value) > ATTR_VALUE_MAX:
            raise AttributeValidationError(f"Attribute value too long for key: {key}")


async def upsert_attributes(
    db: AsyncSession, redis_client: redis.Redis, user_id: str, attributes: dict[str, str]
) -> None:
    validate_attributes(attributes)

    existing_count = await db.scalar(
        select(func.count()).where(UserAttribute.user_id == user_id)
    )
    new_keys = set(attributes.keys())
    existing_keys_result = await db.execute(
        select(UserAttribute.attribute_key).where(
            UserAttribute.user_id == user_id,
            UserAttribute.attribute_key.in_(list(new_keys)),
        )
    )
    existing_keys = {row[0] for row in existing_keys_result.all()}
    net_new = len(new_keys - existing_keys)

    if (existing_count or 0) + net_new > MAX_ATTRS_PER_USER:
        raise AttributeValidationError(f"User would exceed {MAX_ATTRS_PER_USER} attributes limit")

    for key, value in attributes.items():
        stmt = pg_insert(UserAttribute).values(
            user_id=user_id, attribute_key=key, attribute_value=value
        ).on_conflict_do_update(
            constraint="uq_user_attr",
            set_={"attribute_value": value, "updated_at": func.now()}
        )
        await db.execute(stmt)
    await db.commit()

    redis_key = f"attr:{user_id}"
    await redis_client.hset(redis_key, mapping=attributes)
    await redis_client.expire(redis_key, REDIS_TTL)


async def get_attributes(
    redis_client: redis.Redis, db: AsyncSession, user_id: str
) -> dict[str, str]:
    redis_key = f"attr:{user_id}"
    cached = await redis_client.hgetall(redis_key)
    if cached:
        return cached

    result = await db.execute(
        select(UserAttribute).where(UserAttribute.user_id == user_id)
    )
    attrs = {row.attribute_key: row.attribute_value for row in result.scalars().all()}

    if attrs:
        await redis_client.hset(redis_key, mapping=attrs)
        await redis_client.expire(redis_key, REDIS_TTL)

    return attrs
