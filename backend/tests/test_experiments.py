import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_create_layer(client, layer_data):
    resp = await client.post("/api/v1/layers", json=layer_data)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == layer_data["name"]
    assert "salt" in data
    assert len(data["salt"]) == 32


@pytest.mark.asyncio
async def test_list_layers(client, layer_data):
    await client.post("/api/v1/layers", json=layer_data)
    resp = await client.get("/api/v1/layers")
    assert resp.status_code == 200
    layers = resp.json()
    assert len(layers) >= 1


@pytest.mark.asyncio
async def test_get_layer_not_found(client):
    resp = await client.get("/api/v1/layers/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    layer_id = layer_resp.json()["id"]

    experiment_data["layer_id"] = layer_id
    resp = await client.post("/api/v1/experiments", json=experiment_data)
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == experiment_data["key"]
    assert data["status"] == "draft"
    assert len(data["groups"]) == 2


@pytest.mark.asyncio
async def test_list_experiments(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    await client.post("/api/v1/experiments", json=experiment_data)

    resp = await client.get("/api/v1/experiments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/experiments/{exp_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == exp_id


@pytest.mark.asyncio
async def test_update_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    resp = await client.put(f"/api/v1/experiments/{exp_id}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_experiment(client, layer_data, experiment_data):
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/experiments/{exp_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/experiments/{exp_id}")
    assert get_resp.json()["status"] == "archived"
