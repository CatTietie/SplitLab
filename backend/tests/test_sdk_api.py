import pytest
import pytest_asyncio
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_sdk_config_endpoint(client, layer_data, experiment_data):
    """SDK config should return running experiments."""
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_id = create_resp.json()["id"]

    # Draft experiments should NOT appear in SDK config
    resp = await client.get("/api/v1/sdk/config")
    assert resp.status_code == 200
    config = resp.json()
    experiment_keys = [
        e["key"]
        for layer in config["layers"]
        for e in layer["experiments"]
    ]
    assert experiment_data["key"] not in experiment_keys

    # Start experiment — should now appear
    await client.post(f"/api/v1/experiments/{exp_id}/start")
    resp = await client.get("/api/v1/sdk/config")
    config = resp.json()
    experiment_keys = [
        e["key"]
        for layer in config["layers"]
        for e in layer["experiments"]
    ]
    assert experiment_data["key"] in experiment_keys


@pytest.mark.asyncio
async def test_sdk_config_etag(client, layer_data, experiment_data):
    """ETag should return 304 on unchanged config."""
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]

    resp1 = await client.get("/api/v1/sdk/config")
    etag = resp1.headers.get("etag")
    assert etag is not None

    resp2 = await client.get("/api/v1/sdk/config", headers={"If-None-Match": etag})
    assert resp2.status_code == 304


@pytest.mark.asyncio
async def test_event_ingestion(client, layer_data, experiment_data):
    """Events should be accepted for valid experiment/group."""
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_key = create_resp.json()["key"]

    events = {
        "events": [
            {
                "experiment_key": exp_key,
                "group_name": "control",
                "user_id": f"user_{i}",
                "event_name": "click",
                "metadata": None,
                "event_time": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(10)
        ]
    }

    resp = await client.post("/api/v1/sdk/events", json=events)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 10


@pytest.mark.asyncio
async def test_event_ingestion_invalid_experiment(client):
    """Events for nonexistent experiments should be silently dropped."""
    events = {
        "events": [
            {
                "experiment_key": "nonexistent_exp",
                "group_name": "control",
                "user_id": "user_1",
                "event_name": "click",
                "metadata": None,
                "event_time": datetime.now(timezone.utc).isoformat(),
            }
        ]
    }
    resp = await client.post("/api/v1/sdk/events", json=events)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 0


@pytest.mark.asyncio
async def test_event_batch_performance(client, layer_data, experiment_data):
    """Batch of 200 events should be ingested in a single request."""
    layer_resp = await client.post("/api/v1/layers", json=layer_data)
    experiment_data["layer_id"] = layer_resp.json()["id"]
    create_resp = await client.post("/api/v1/experiments", json=experiment_data)
    exp_key = create_resp.json()["key"]

    events = {
        "events": [
            {
                "experiment_key": exp_key,
                "group_name": "control" if i % 2 == 0 else "treatment",
                "user_id": f"user_{i}",
                "event_name": "purchase",
                "metadata": {"amount": i * 10},
                "event_time": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(200)
        ]
    }

    resp = await client.post("/api/v1/sdk/events", json=events)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 200
