import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


class TestAttributeUpload:
    async def test_upload_valid_attributes(self, client):
        payload = {
            "users": [
                {
                    "user_id": "user_001",
                    "attributes": {"country": "CN", "device": "mobile", "plan": "premium"}
                }
            ]
        }
        resp = await client.post("/api/v1/sdk/attributes", json=payload)
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 3

    async def test_upload_multiple_users(self, client):
        payload = {
            "users": [
                {"user_id": "user_001", "attributes": {"country": "CN"}},
                {"user_id": "user_002", "attributes": {"country": "US", "device": "desktop"}},
            ]
        }
        resp = await client.post("/api/v1/sdk/attributes", json=payload)
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 3

    async def test_invalid_key_format_rejected(self, client):
        payload = {
            "users": [
                {"user_id": "user_001", "attributes": {"INVALID_KEY": "value"}}
            ]
        }
        resp = await client.post("/api/v1/sdk/attributes", json=payload)
        assert resp.status_code == 422

    async def test_key_with_numbers_rejected(self, client):
        payload = {
            "users": [
                {"user_id": "user_001", "attributes": {"key123": "value"}}
            ]
        }
        resp = await client.post("/api/v1/sdk/attributes", json=payload)
        assert resp.status_code == 422

    async def test_value_too_long_rejected(self, client):
        payload = {
            "users": [
                {"user_id": "user_001", "attributes": {"country": "x" * 257}}
            ]
        }
        resp = await client.post("/api/v1/sdk/attributes", json=payload)
        assert resp.status_code == 422

    async def test_too_many_attributes_rejected(self, client):
        attrs = {f"key{'_' * i}a": "val" for i in range(21)}
        payload = {
            "users": [
                {"user_id": "user_001", "attributes": attrs}
            ]
        }
        resp = await client.post("/api/v1/sdk/attributes", json=payload)
        assert resp.status_code == 422

    async def test_upsert_overwrites_value(self, client):
        payload1 = {"users": [{"user_id": "user_001", "attributes": {"country": "CN"}}]}
        resp1 = await client.post("/api/v1/sdk/attributes", json=payload1)
        assert resp1.status_code == 200

        payload2 = {"users": [{"user_id": "user_001", "attributes": {"country": "US"}}]}
        resp2 = await client.post("/api/v1/sdk/attributes", json=payload2)
        assert resp2.status_code == 200
        assert resp2.json()["accepted"] == 1


class TestSDKConfigIncludesTargetingRules:
    async def test_config_includes_targeting_rules(self, client, layer_data, experiment_data):
        layer_resp = await client.post("/api/v1/layers", json=layer_data)
        layer_id = layer_resp.json()["id"]

        targeting_rules = {
            "operator": "AND",
            "rules": [
                {"key": "country", "op": "in", "values": ["CN", "US"]},
                {"key": "device", "op": "eq", "value": "mobile"},
            ]
        }
        experiment_data["layer_id"] = layer_id
        experiment_data["targeting_rules"] = targeting_rules
        experiment_data["stratification_dimensions"] = ["country", "device"]

        exp_resp = await client.post("/api/v1/experiments", json=experiment_data)
        assert exp_resp.status_code == 201
        exp_id = exp_resp.json()["id"]

        await client.post(f"/api/v1/experiments/{exp_id}/start")

        config_resp = await client.get("/api/v1/sdk/config")
        assert config_resp.status_code == 200
        config = config_resp.json()

        exp_config = config["layers"][0]["experiments"][0]
        assert exp_config["targeting_rules"] == targeting_rules
        assert exp_config["stratification_dimensions"] == ["country", "device"]

    async def test_config_without_targeting_rules(self, client, layer_data, experiment_data):
        layer_resp = await client.post("/api/v1/layers", json=layer_data)
        layer_id = layer_resp.json()["id"]

        experiment_data["layer_id"] = layer_id

        exp_resp = await client.post("/api/v1/experiments", json=experiment_data)
        assert exp_resp.status_code == 201
        exp_id = exp_resp.json()["id"]

        await client.post(f"/api/v1/experiments/{exp_id}/start")

        config_resp = await client.get("/api/v1/sdk/config")
        assert config_resp.status_code == 200
        config = config_resp.json()

        exp_config = config["layers"][0]["experiments"][0]
        assert exp_config["targeting_rules"] is None
        assert exp_config["stratification_dimensions"] is None
