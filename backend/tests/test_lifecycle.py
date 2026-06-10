import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_start_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/experiments/{exp_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_cannot_start_running_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    await client.post(f"/api/v1/experiments/{exp_id}/start")
    resp = await client.post(f"/api/v1/experiments/{exp_id}/start")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pause_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    await client.post(f"/api/v1/experiments/{exp_id}/start")
    resp = await client.post(f"/api/v1/experiments/{exp_id}/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_cannot_pause_draft_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/experiments/{exp_id}/pause")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resume_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    await client.post(f"/api/v1/experiments/{exp_id}/start")
    await client.post(f"/api/v1/experiments/{exp_id}/pause")
    resp = await client.post(f"/api/v1/experiments/{exp_id}/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_rollout_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]
    group_id = create_resp.json()["groups"][1]["id"]

    await client.post(f"/api/v1/experiments/{exp_id}/start")
    resp = await client.post(f"/api/v1/experiments/{exp_id}/rollout?winner_group_id={group_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "full_rollout"
    assert resp.json()["winner_group_id"] == group_id


@pytest.mark.asyncio
async def test_full_lifecycle(client, layer_data, experiment_data):
    """End-to-end: draft → start → pause → resume → rollout."""
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]
    group_id = create_resp.json()["groups"][0]["id"]

    assert create_resp.json()["status"] == "draft"

    r = await client.post(f"/api/v1/experiments/{exp_id}/start")
    assert r.json()["status"] == "running"

    r = await client.post(f"/api/v1/experiments/{exp_id}/pause")
    assert r.json()["status"] == "paused"

    r = await client.post(f"/api/v1/experiments/{exp_id}/resume")
    assert r.json()["status"] == "running"

    r = await client.post(f"/api/v1/experiments/{exp_id}/rollout?winner_group_id={group_id}")
    assert r.json()["status"] == "full_rollout"
