import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
def gradual_experiment_data(layer_data):
    return {
        "key": f"gradual_exp_{uuid.uuid4().hex[:8]}",
        "name": "Gradual Rollout Test",
        "description": "Test experiment with rollout steps",
        "bucket_start": 0,
        "bucket_end": 9999,
        "groups": [
            {"name": "control", "traffic_percentage": 50},
            {"name": "treatment", "traffic_percentage": 50},
        ],
        "rollout_steps": [
            {"traffic_percentage": 10, "hold_seconds": 60},
            {"traffic_percentage": 50, "hold_seconds": 120},
            {"traffic_percentage": 100, "hold_seconds": 0},
        ],
        "guardrail_metrics": [
            {"metric_name": "error_rate", "threshold": 0.05, "direction": "up"}
        ],
    }


async def _create_layer(client: AsyncClient, layer_data: dict) -> str:
    resp = await client.post("/api/v1/layers", json=layer_data)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_experiment(client: AsyncClient, layer_id: str, data: dict) -> dict:
    data["layer_id"] = layer_id
    resp = await client.post("/api/v1/experiments", json=data)
    assert resp.status_code == 201
    return resp.json()


async def test_start_with_rollout_steps_sets_step_zero(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)

    resp = await client.post(f"/api/v1/experiments/{exp['id']}/start")
    assert resp.status_code == 200
    started = resp.json()
    assert started["status"] == "running"
    assert started["current_step_index"] == 0
    assert started["rollout_steps"] is not None


async def test_advance_step_increments_index(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")

    resp = await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    assert resp.status_code == 200
    advanced = resp.json()
    assert advanced["current_step_index"] == 1


async def test_rollback_step_decrements_index(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})

    resp = await client.post(f"/api/v1/experiments/{exp['id']}/rollout-rollback")
    assert resp.status_code == 200
    rolled_back = resp.json()
    assert rolled_back["current_step_index"] == 0


async def test_cannot_rollback_below_zero(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")

    resp = await client.post(f"/api/v1/experiments/{exp['id']}/rollout-rollback")
    assert resp.status_code == 400


async def test_cannot_advance_past_last_step(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")
    # Advance to step 1
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    # Advance to step 2 (last)
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})

    # Try to advance past last step
    resp = await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    assert resp.status_code == 400


async def test_advance_after_rollback_requires_confirmation(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-rollback")

    # Try advance without confirmation
    resp = await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    assert resp.status_code == 409

    # Advance with confirmation
    resp = await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": True})
    assert resp.status_code == 200
    assert resp.json()["current_step_index"] == 1


async def test_start_without_rollout_steps_no_gradual_mode(client: AsyncClient, layer_data, experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, experiment_data)

    resp = await client.post(f"/api/v1/experiments/{exp['id']}/start")
    assert resp.status_code == 200
    started = resp.json()
    assert started["status"] == "running"
    assert started["current_step_index"] is None


async def test_not_in_gradual_mode_returns_400(client: AsyncClient, layer_data, experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")

    resp = await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})
    assert resp.status_code == 400


async def test_rollout_status_endpoint(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")

    resp = await client.get(f"/api/v1/experiments/{exp['id']}/rollout-status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["current_step_index"] == 0
    assert status["current_traffic_percentage"] == 10
    assert len(status["steps"]) == 3
    assert len(status["step_logs"]) >= 1


async def test_pause_and_resume_preserves_step(client: AsyncClient, layer_data, gradual_experiment_data):
    layer_id = await _create_layer(client, layer_data)
    exp = await _create_experiment(client, layer_id, gradual_experiment_data)
    await client.post(f"/api/v1/experiments/{exp['id']}/start")
    await client.post(f"/api/v1/experiments/{exp['id']}/rollout-advance", json={"confirmed": False})

    # Pause
    resp = await client.post(f"/api/v1/experiments/{exp['id']}/pause")
    assert resp.status_code == 200
    assert resp.json()["current_step_index"] == 1

    # Resume
    resp = await client.post(f"/api/v1/experiments/{exp['id']}/resume")
    assert resp.status_code == 200
    assert resp.json()["current_step_index"] == 1
