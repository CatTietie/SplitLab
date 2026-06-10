import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


ROLLOUT_STEPS_4 = [
    {"traffic_percentage": 5, "hold_seconds": 600},
    {"traffic_percentage": 20, "hold_seconds": 1800},
    {"traffic_percentage": 50, "hold_seconds": 3600},
    {"traffic_percentage": 100, "hold_seconds": 0},
]


@pytest.fixture
def acceptance_experiment_data():
    return {
        "key": f"accept_exp_{uuid.uuid4().hex[:8]}",
        "name": "Acceptance Test Experiment",
        "description": "4-step gradual rollout acceptance",
        "bucket_start": 0,
        "bucket_end": 9999,
        "groups": [
            {"name": "control", "traffic_percentage": 50},
            {"name": "treatment", "traffic_percentage": 50},
        ],
        "rollout_steps": ROLLOUT_STEPS_4,
        "guardrail_metrics": [
            {"metric_name": "error_rate", "threshold": 0.05, "direction": "up"}
        ],
    }


async def _create_layer(client: AsyncClient, layer_data: dict) -> str:
    resp = await client.post("/api/v1/layers", json=layer_data)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_and_start(client: AsyncClient, layer_data: dict, exp_data: dict) -> dict:
    layer_id = await _create_layer(client, layer_data)
    exp_data["layer_id"] = layer_id
    resp = await client.post("/api/v1/experiments", json=exp_data)
    assert resp.status_code == 201
    exp = resp.json()
    resp = await client.post(f"/api/v1/experiments/{exp['id']}/start")
    assert resp.status_code == 200
    return resp.json()


def _get_traffic_for_experiment(sdk_config: dict, experiment_key: str) -> dict[str, int]:
    for layer in sdk_config["layers"]:
        for exp in layer["experiments"]:
            if exp["key"] == experiment_key:
                return {g["name"]: g["traffic_percentage"] for g in exp["groups"]}
    return {}


async def test_4step_rollout_sdk_config_updates(client: AsyncClient, layer_data, acceptance_experiment_data):
    """Acceptance: 4-step rollout (5%->20%->50%->100%) updates SDK config at each step."""
    exp = await _create_and_start(client, layer_data, acceptance_experiment_data)
    exp_key = acceptance_experiment_data["key"]

    # Step 0: treatment=5%, control=95%
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 5
    assert traffic["control"] == 95

    # Advance to step 1: treatment=20%, control=80%
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 20
    assert traffic["control"] == 80

    # Advance to step 2: treatment=50%, control=50%
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 50
    assert traffic["control"] == 50

    # Advance to step 3: treatment=100%, control=0%
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 100
    assert traffic["control"] == 0


async def test_guardrail_auto_rollback_reverts_sdk_config(client: AsyncClient, layer_data, acceptance_experiment_data):
    """Acceptance: guardrail degradation > 2x threshold triggers rollback, SDK config reverts."""
    exp = await _create_and_start(client, layer_data, acceptance_experiment_data)
    exp_key = acceptance_experiment_data["key"]
    exp_id = exp["id"]

    # Advance to step 1 (20%)
    await client.post(f"/api/v1/experiments/{exp_id}/rollout-advance", json={"confirmed": False})
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 20

    # Inject events to trigger guardrail: control has low error_rate, treatment has high
    # Need 30+ users per group for guardrail to evaluate
    control_group_name = "control"
    treatment_group_name = "treatment"

    # Control: 50 users, 2 with error_rate event (4% rate)
    control_events = []
    for i in range(50):
        control_events.append({
            "experiment_key": exp_key,
            "group_name": control_group_name,
            "user_id": f"ctrl_user_{i}",
            "event_name": "exposure",
            "metadata": None,
            "event_time": datetime.now(timezone.utc).isoformat(),
        })
    for i in range(2):
        control_events.append({
            "experiment_key": exp_key,
            "group_name": control_group_name,
            "user_id": f"ctrl_user_{i}",
            "event_name": "error_rate",
            "metadata": None,
            "event_time": datetime.now(timezone.utc).isoformat(),
        })

    # Treatment: 50 users, 10 with error_rate event (20% rate)
    # degradation = 0.20 - 0.04 = 0.16 > 2*0.05 = 0.10 → triggers rollback
    treatment_events = []
    for i in range(50):
        treatment_events.append({
            "experiment_key": exp_key,
            "group_name": treatment_group_name,
            "user_id": f"treat_user_{i}",
            "event_name": "exposure",
            "metadata": None,
            "event_time": datetime.now(timezone.utc).isoformat(),
        })
    for i in range(10):
        treatment_events.append({
            "experiment_key": exp_key,
            "group_name": treatment_group_name,
            "user_id": f"treat_user_{i}",
            "event_name": "error_rate",
            "metadata": None,
            "event_time": datetime.now(timezone.utc).isoformat(),
        })

    await client.post("/api/v1/sdk/events", json={"events": control_events})
    await client.post("/api/v1/sdk/events", json={"events": treatment_events})

    # Simulate the timer loop: check guardrails then rollback
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.services.rollout_engine import check_guardrails, rollback_step

    # Use the test overrides to get db/redis
    from tests.conftest import TestingSessionLocal, _fake_redis

    async with TestingSessionLocal() as db:
        result = await check_guardrails(db, _fake_redis, uuid.UUID(exp_id))
        assert result == "rollback"
        await rollback_step(db, _fake_redis, uuid.UUID(exp_id), "guardrail_rollback")

    # Verify SDK config reverts to step 0 (5%)
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 5
    assert traffic["control"] == 95

    # Verify experiment state
    resp = await client.get(f"/api/v1/experiments/{exp_id}")
    assert resp.json()["current_step_index"] == 0


async def test_rollback_then_advance_confirmation_full_flow(client: AsyncClient, layer_data, acceptance_experiment_data):
    """Acceptance: rollback sets confirm flag, re-advance without confirm -> 409, with confirm -> 200."""
    exp = await _create_and_start(client, layer_data, acceptance_experiment_data)
    exp_id = exp["id"]
    exp_key = acceptance_experiment_data["key"]

    # Advance to step 1
    resp = await client.post(f"/api/v1/experiments/{exp_id}/rollout-advance", json={"confirmed": False})
    assert resp.status_code == 200
    assert resp.json()["current_step_index"] == 1

    # Rollback to step 0
    resp = await client.post(f"/api/v1/experiments/{exp_id}/rollout-rollback")
    assert resp.status_code == 200
    assert resp.json()["current_step_index"] == 0

    # Verify SDK config shows step 0 traffic
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 5

    # Try advance without confirmation -> 409
    resp = await client.post(f"/api/v1/experiments/{exp_id}/rollout-advance", json={"confirmed": False})
    assert resp.status_code == 409

    # Advance with confirmation -> 200
    resp = await client.post(f"/api/v1/experiments/{exp_id}/rollout-advance", json={"confirmed": True})
    assert resp.status_code == 200
    assert resp.json()["current_step_index"] == 1

    # Verify SDK config shows step 1 traffic
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), exp_key)
    assert traffic["treatment"] == 20
    assert traffic["control"] == 80


async def test_no_rollout_steps_sdk_config_static(client: AsyncClient, layer_data):
    """Acceptance: experiment without rollout_steps uses static traffic percentages."""
    plain_exp_data = {
        "key": f"plain_exp_{uuid.uuid4().hex[:8]}",
        "name": "No Rollout Experiment",
        "bucket_start": 0,
        "bucket_end": 9999,
        "groups": [
            {"name": "control", "traffic_percentage": 50},
            {"name": "treatment", "traffic_percentage": 50},
        ],
    }

    layer_id = await _create_layer(client, layer_data)
    plain_exp_data["layer_id"] = layer_id
    resp = await client.post("/api/v1/experiments", json=plain_exp_data)
    assert resp.status_code == 201
    exp = resp.json()

    # Start
    resp = await client.post(f"/api/v1/experiments/{exp['id']}/start")
    assert resp.status_code == 200
    assert resp.json()["current_step_index"] is None

    # Verify SDK config has original 50/50 split
    resp = await client.get("/api/v1/sdk/config")
    traffic = _get_traffic_for_experiment(resp.json(), plain_exp_data["key"])
    assert traffic["treatment"] == 50
    assert traffic["control"] == 50
