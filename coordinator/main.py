"""
SplitLab Coordinator Service

Runs independently from the gateway (backend). Monitors backend health via
heartbeat. When a backend instance goes down:
1. Purges stale config cache shards from Redis
2. Rebuilds config cache from PostgreSQL
3. Publishes recovery event so SDK clients re-fetch

This ensures repair is never blocked by gateway unavailability.
"""
import asyncio
import logging
import time
import signal
import sys
from datetime import datetime, timezone

import asyncpg
import os
import redis.asyncio as redis
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("coordinator")

HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "5"))
HEARTBEAT_TIMEOUT = int(os.environ.get("HEARTBEAT_TIMEOUT", "15"))
REPAIR_COOLDOWN = int(os.environ.get("REPAIR_COOLDOWN", "10"))

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://splitlab:splitlab@postgres:5432/splitlab")


class Coordinator:
    def __init__(self):
        self._redis: redis.Redis | None = None
        self._db_pool: asyncpg.Pool | None = None
        self._running = True
        self._last_heartbeat: float = 0
        self._backend_alive = False
        self._last_repair: float = 0

    async def start(self):
        logger.info("Coordinator starting...")
        self._redis = redis.from_url(REDIS_URL, decode_responses=True)
        self._db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

        await self._register_self()
        logger.info("Coordinator running. Monitoring backend heartbeat.")

        await asyncio.gather(
            self._heartbeat_loop(),
            self._watchdog_loop(),
        )

    async def stop(self):
        self._running = False
        if self._redis:
            await self._redis.aclose()
        if self._db_pool:
            await self._db_pool.close()
        logger.info("Coordinator stopped.")

    async def _register_self(self):
        await self._redis.set("coordinator:alive", "1", ex=30)

    async def _heartbeat_loop(self):
        """Periodically check backend health endpoint."""
        async with httpx.AsyncClient(timeout=5) as client:
            while self._running:
                try:
                    resp = await client.get(f"{BACKEND_URL}/health")
                    if resp.status_code == 200:
                        self._last_heartbeat = time.time()
                        if not self._backend_alive:
                            logger.info("Backend is UP. Triggering recovery cleanup.")
                            await self._on_backend_recovered()
                        self._backend_alive = True
                        await self._redis.set("backend:heartbeat", str(self._last_heartbeat), ex=HEARTBEAT_TIMEOUT * 2)
                    else:
                        logger.warning(f"Backend health check failed: HTTP {resp.status_code}")
                except Exception as e:
                    logger.warning(f"Backend unreachable: {e}")

                await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _watchdog_loop(self):
        """Detect heartbeat timeout and trigger repair."""
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await self._redis.set("coordinator:alive", "1", ex=30)

            if self._last_heartbeat == 0:
                continue

            elapsed = time.time() - self._last_heartbeat
            if elapsed > HEARTBEAT_TIMEOUT and self._backend_alive:
                logger.error(f"Backend heartbeat TIMEOUT ({elapsed:.1f}s). Triggering shard repair.")
                self._backend_alive = False
                await self._on_backend_down()

    async def _on_backend_down(self):
        """Repair callback: backend is confirmed down."""
        now = time.time()
        if now - self._last_repair < REPAIR_COOLDOWN:
            logger.info("Repair cooldown active, skipping.")
            return
        self._last_repair = now

        await self._purge_stale_shards()
        await self._rebuild_config_cache()
        await self._publish_recovery_event("backend_down")

    async def _on_backend_recovered(self):
        """Called when backend comes back online after being down."""
        await self._purge_stale_shards()
        await self._rebuild_config_cache()
        await self._publish_recovery_event("backend_recovered")

    async def _purge_stale_shards(self):
        """Remove all stale config cache and shard markers from Redis."""
        logger.info("Purging stale shards from Redis...")
        keys_to_delete = []

        async for key in self._redis.scan_iter("sdk:config*"):
            keys_to_delete.append(key)
        async for key in self._redis.scan_iter("shard:*"):
            keys_to_delete.append(key)
        async for key in self._redis.scan_iter("backend:instance:*"):
            keys_to_delete.append(key)

        if keys_to_delete:
            await self._redis.delete(*keys_to_delete)
            logger.info(f"Purged {len(keys_to_delete)} stale keys: {keys_to_delete}")
        else:
            logger.info("No stale shards found.")

    async def _rebuild_config_cache(self):
        """Rebuild SDK config cache directly from PostgreSQL."""
        logger.info("Rebuilding config cache from database...")
        try:
            async with self._db_pool.acquire() as conn:
                layers = await conn.fetch("""
                    SELECT id, name, salt FROM experiment_layers
                """)

                layer_configs = []
                for layer in layers:
                    experiments = await conn.fetch("""
                        SELECT id, key, status, bucket_start, bucket_end,
                               rollout_steps, current_step_index
                        FROM experiments
                        WHERE layer_id = $1 AND status IN ('running', 'full_rollout')
                    """, layer["id"])

                    exp_configs = []
                    for exp in experiments:
                        groups = await conn.fetch("""
                            SELECT id, name, traffic_percentage, config_json
                            FROM experiment_groups WHERE experiment_id = $1
                        """, exp["id"])

                        whitelists = await conn.fetch("""
                            SELECT w.user_id, g.name as group_name
                            FROM whitelists w JOIN experiment_groups g ON w.group_id = g.id
                            WHERE w.experiment_id = $1
                        """, exp["id"])

                        effective_groups = self._compute_effective_traffic(
                            exp["rollout_steps"], exp["current_step_index"], groups
                        )

                        import json
                        exp_configs.append({
                            "id": str(exp["id"]),
                            "key": exp["key"],
                            "status": exp["status"],
                            "bucket_start": exp["bucket_start"],
                            "bucket_end": exp["bucket_end"],
                            "groups": [
                                {
                                    "id": str(g["id"]),
                                    "name": g["name"],
                                    "traffic_percentage": pct,
                                    "config_json": json.loads(g["config_json"]) if g["config_json"] else None,
                                }
                                for g, pct in effective_groups
                            ],
                            "whitelist": {w["user_id"]: w["group_name"] for w in whitelists},
                        })

                    layer_configs.append({
                        "id": str(layer["id"]),
                        "name": layer["name"],
                        "salt": layer["salt"],
                        "experiments": exp_configs,
                    })

                import json
                import hashlib
                config = json.dumps({"layers": layer_configs, "version": "1"})
                etag = hashlib.md5(config.encode()).hexdigest()

                await self._redis.set("sdk:config", config, ex=300)
                await self._redis.set("sdk:config:etag", etag, ex=300)
                logger.info(f"Config cache rebuilt. {len(layer_configs)} layers, etag={etag[:8]}...")

        except Exception as e:
            logger.error(f"Failed to rebuild config cache: {e}")

    def _compute_effective_traffic(self, rollout_steps, current_step_index, groups):
        """Compute effective traffic percentages accounting for gradual rollout."""
        if current_step_index is None or not rollout_steps:
            return [(g, g["traffic_percentage"]) for g in groups]

        import json as _json
        steps = rollout_steps if isinstance(rollout_steps, list) else _json.loads(rollout_steps)
        step = steps[current_step_index]
        target_pct = step["traffic_percentage"]

        control_group = next((g for g in groups if g["name"] == "control"), None)
        if control_group is None:
            control_group = groups[0]

        treatment_groups = [g for g in groups if g["id"] != control_group["id"]]

        if not treatment_groups:
            return [(g, g["traffic_percentage"]) for g in groups]

        original_treatment_total = sum(g["traffic_percentage"] for g in treatment_groups)

        result = []
        treatment_allocated = 0
        for i, tg in enumerate(treatment_groups):
            if original_treatment_total > 0:
                share = tg["traffic_percentage"] / original_treatment_total
            else:
                share = 1.0 / len(treatment_groups)

            if i == len(treatment_groups) - 1:
                allocated = target_pct - treatment_allocated
            else:
                allocated = round(target_pct * share)
            treatment_allocated += allocated
            result.append((tg, allocated))

        control_pct = 100 - target_pct
        return [(control_group, control_pct)] + result

    async def _publish_recovery_event(self, event_type: str):
        """Publish recovery event to Redis pub/sub so SDK clients know to re-fetch."""
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        import json
        await self._redis.publish("splitlab:events", json.dumps(event))
        logger.info(f"Published recovery event: {event_type}")


async def main():
    coordinator = Coordinator()

    def shutdown(signum, frame):
        logger.info("Shutdown signal received.")
        coordinator._running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        await coordinator.start()
    finally:
        await coordinator.stop()


if __name__ == "__main__":
    asyncio.run(main())
