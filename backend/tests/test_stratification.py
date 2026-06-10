import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


class TestStratificationEndpoint:
    async def test_no_dimensions_returns_empty(self, client, layer_data, experiment_data):
        layer_resp = await client.post("/api/v1/layers", json=layer_data)
        layer_id = layer_resp.json()["id"]

        experiment_data["layer_id"] = layer_id
        exp_resp = await client.post("/api/v1/experiments", json=experiment_data)
        assert exp_resp.status_code == 201
        exp_id = exp_resp.json()["id"]

        resp = await client.get(f"/api/v1/experiments/{exp_id}/stratification")
        assert resp.status_code == 200
        assert resp.json() == {"dimensions": []}

    async def test_nonexistent_experiment_returns_404(self, client):
        import uuid
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/experiments/{fake_id}/stratification")
        assert resp.status_code == 404

    async def test_with_dimensions_and_events(self, client, layer_data, experiment_data):
        layer_resp = await client.post("/api/v1/layers", json=layer_data)
        layer_id = layer_resp.json()["id"]

        experiment_data["layer_id"] = layer_id
        experiment_data["stratification_dimensions"] = ["country"]
        exp_resp = await client.post("/api/v1/experiments", json=experiment_data)
        assert exp_resp.status_code == 201
        exp_id = exp_resp.json()["id"]

        await client.post(f"/api/v1/experiments/{exp_id}/start")

        config_resp = await client.get("/api/v1/sdk/config")
        config = config_resp.json()
        groups = config["layers"][0]["experiments"][0]["groups"]
        control_name = groups[0]["name"]

        attrs_payload = {
            "users": [
                {"user_id": f"user_{i}", "attributes": {"country": "CN" if i % 2 == 0 else "US"}}
                for i in range(10)
            ]
        }
        await client.post("/api/v1/sdk/attributes", json=attrs_payload)

        events_payload = {
            "events": [
                {
                    "experiment_key": experiment_data["key"],
                    "group_name": control_name,
                    "user_id": f"user_{i}",
                    "event_name": "page_view",
                    "event_time": "2026-06-10T10:00:00Z",
                }
                for i in range(10)
            ]
        }
        await client.post("/api/v1/sdk/events", json=events_payload)

        resp = await client.get(f"/api/v1/experiments/{exp_id}/stratification")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["dimensions"]) == 1
        assert data["dimensions"][0]["dimension"] == "country"
