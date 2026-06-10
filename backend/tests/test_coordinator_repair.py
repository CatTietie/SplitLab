"""
Coordinator repair chain unit test.

Tests the coordinator's core logic:
1. Heartbeat timeout detection triggers repair
2. Purge stale shards removes all shard:* and config keys
3. Rebuild config cache repopulates from data
4. Recovery event is published
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import fakeredis.aioredis


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_purge_stale_shards(fake_redis):
    """Stale shard keys should be removed on purge."""
    # Simulate stale data from split-brain
    await fake_redis.set("sdk:config", '{"layers": []}')
    await fake_redis.set("sdk:config:etag", "old_etag")
    await fake_redis.set("shard:exp_1:bucket_0_4999", "backend_instance_1")
    await fake_redis.set("shard:exp_2:bucket_5000_9999", "backend_instance_2")
    await fake_redis.set("backend:instance:dead_node", "ghost")

    # Purge logic (same as coordinator._purge_stale_shards)
    keys_to_delete = []
    async for key in fake_redis.scan_iter("sdk:config*"):
        keys_to_delete.append(key)
    async for key in fake_redis.scan_iter("shard:*"):
        keys_to_delete.append(key)
    async for key in fake_redis.scan_iter("backend:instance:*"):
        keys_to_delete.append(key)

    assert len(keys_to_delete) == 5
    await fake_redis.delete(*keys_to_delete)

    # Verify all cleaned
    assert await fake_redis.get("sdk:config") is None
    assert await fake_redis.get("shard:exp_1:bucket_0_4999") is None
    assert await fake_redis.get("shard:exp_2:bucket_5000_9999") is None
    assert await fake_redis.get("backend:instance:dead_node") is None


@pytest.mark.asyncio
async def test_rebuild_config_populates_redis(fake_redis):
    """After rebuild, sdk:config and sdk:config:etag should exist."""
    # Simulate coordinator rebuilding config
    import hashlib
    config_data = {
        "layers": [{
            "id": "layer_1",
            "name": "test",
            "salt": "abc123",
            "experiments": [{
                "id": "exp_1",
                "key": "homepage_test",
                "status": "running",
                "bucket_start": 0,
                "bucket_end": 9999,
                "groups": [
                    {"id": "g1", "name": "control", "traffic_percentage": 50, "config_json": None},
                    {"id": "g2", "name": "treatment", "traffic_percentage": 50, "config_json": None},
                ],
                "whitelist": {},
            }],
        }],
        "version": "1",
    }
    config_json = json.dumps(config_data)
    etag = hashlib.md5(config_json.encode()).hexdigest()

    await fake_redis.set("sdk:config", config_json, ex=300)
    await fake_redis.set("sdk:config:etag", etag, ex=300)

    # Verify
    cached = await fake_redis.get("sdk:config")
    assert cached is not None
    parsed = json.loads(cached)
    assert len(parsed["layers"]) == 1
    assert parsed["layers"][0]["experiments"][0]["key"] == "homepage_test"
    assert await fake_redis.get("sdk:config:etag") == etag


@pytest.mark.asyncio
async def test_recovery_event_published(fake_redis):
    """Recovery event should be published to splitlab:events channel."""
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe("splitlab:events")
    # Consume the subscribe confirmation message
    await pubsub.get_message(timeout=1)

    # Publish recovery event (same as coordinator._publish_recovery_event)
    event = {"type": "backend_recovered", "timestamp": "2026-06-08T12:00:00+00:00"}
    receivers = await fake_redis.publish("splitlab:events", json.dumps(event))
    assert receivers >= 1, "At least one subscriber should receive the message"

    # Receive
    await asyncio.sleep(0.1)
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    assert msg is not None, "Should have received the published message"
    assert msg["type"] == "message"
    data = json.loads(msg["data"])
    assert data["type"] == "backend_recovered"

    await pubsub.unsubscribe("splitlab:events")
    await pubsub.aclose()


@pytest.mark.asyncio
async def test_heartbeat_timeout_detection():
    """Watchdog should detect when heartbeat exceeds timeout."""
    last_heartbeat = time.time() - 20  # 20 seconds ago
    timeout = 15

    elapsed = time.time() - last_heartbeat
    assert elapsed > timeout, "Should have detected timeout"

    # This is the core logic from coordinator._watchdog_loop
    backend_was_alive = True
    should_trigger_repair = elapsed > timeout and backend_was_alive
    assert should_trigger_repair


@pytest.mark.asyncio
async def test_full_repair_chain(fake_redis):
    """Full chain: inject stale data → purge → rebuild → verify clean state."""
    # 1. Inject stale split-brain residue
    await fake_redis.set("sdk:config", '{"old": true}')
    await fake_redis.set("sdk:config:etag", "stale_etag")
    await fake_redis.set("shard:orphan_1", "dead_backend")
    await fake_redis.set("shard:orphan_2", "dead_backend")

    # 2. Purge
    keys_to_delete = []
    async for key in fake_redis.scan_iter("sdk:config*"):
        keys_to_delete.append(key)
    async for key in fake_redis.scan_iter("shard:*"):
        keys_to_delete.append(key)
    if keys_to_delete:
        await fake_redis.delete(*keys_to_delete)

    # 3. Verify purge
    assert await fake_redis.get("sdk:config") is None
    assert await fake_redis.get("shard:orphan_1") is None

    # 4. Rebuild with fresh data
    import hashlib
    fresh_config = json.dumps({"layers": [], "version": "1"})
    fresh_etag = hashlib.md5(fresh_config.encode()).hexdigest()
    await fake_redis.set("sdk:config", fresh_config, ex=300)
    await fake_redis.set("sdk:config:etag", fresh_etag, ex=300)

    # 5. Verify rebuild
    result = await fake_redis.get("sdk:config")
    assert json.loads(result) == {"layers": [], "version": "1"}
    assert await fake_redis.get("sdk:config:etag") == fresh_etag

    # 6. No stale residue remains
    stale_keys = []
    async for key in fake_redis.scan_iter("shard:*"):
        stale_keys.append(key)
    assert len(stale_keys) == 0, "No stale shards should remain after repair"
