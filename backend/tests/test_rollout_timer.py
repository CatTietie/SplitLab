import time
import uuid

import pytest
import fakeredis.aioredis

from app.services.rollout_timer import (
    schedule_timer, cancel_timer, get_expired_timers,
    save_remaining, pop_remaining, TIMER_ZSET_KEY,
)


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_schedule_and_expire_timer(redis_client):
    exp_id = uuid.uuid4()
    await schedule_timer(redis_client, exp_id, 0)

    expired = await get_expired_timers(redis_client)
    assert str(exp_id) in expired


async def test_schedule_future_timer_not_expired(redis_client):
    exp_id = uuid.uuid4()
    await schedule_timer(redis_client, exp_id, 3600)

    expired = await get_expired_timers(redis_client)
    assert str(exp_id) not in expired


async def test_cancel_timer_removes_from_zset(redis_client):
    exp_id = uuid.uuid4()
    await schedule_timer(redis_client, exp_id, 0)
    await cancel_timer(redis_client, exp_id)

    expired = await get_expired_timers(redis_client)
    assert str(exp_id) not in expired


async def test_multiple_timers_only_expired_returned(redis_client):
    exp_a = uuid.uuid4()
    exp_b = uuid.uuid4()
    await schedule_timer(redis_client, exp_a, 0)
    await schedule_timer(redis_client, exp_b, 3600)

    expired = await get_expired_timers(redis_client)
    assert str(exp_a) in expired
    assert str(exp_b) not in expired


async def test_save_and_pop_remaining(redis_client):
    exp_id = uuid.uuid4()
    await schedule_timer(redis_client, exp_id, 3600)

    await save_remaining(redis_client, exp_id)
    await cancel_timer(redis_client, exp_id)

    remaining = await pop_remaining(redis_client, exp_id)
    assert remaining is not None
    assert 3598 <= remaining <= 3600

    # Second pop returns None (consumed)
    assert await pop_remaining(redis_client, exp_id) is None


async def test_pop_remaining_without_save_returns_none(redis_client):
    exp_id = uuid.uuid4()
    assert await pop_remaining(redis_client, exp_id) is None
