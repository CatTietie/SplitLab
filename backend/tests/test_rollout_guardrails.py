import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.rollout_engine import check_guardrails


class FakeGroup:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class FakeExperiment:
    def __init__(self, guardrail_metrics, groups):
        self.guardrail_metrics = guardrail_metrics
        self.groups = groups


@pytest.fixture
def experiment_with_guardrails():
    return FakeExperiment(
        guardrail_metrics=[{"metric_name": "error_rate", "threshold": 0.05, "direction": "up"}],
        groups=[
            FakeGroup(uuid.uuid4(), "control"),
            FakeGroup(uuid.uuid4(), "treatment"),
        ],
    )


@pytest.fixture
def experiment_without_guardrails():
    return FakeExperiment(
        guardrail_metrics=None,
        groups=[
            FakeGroup(uuid.uuid4(), "control"),
            FakeGroup(uuid.uuid4(), "treatment"),
        ],
    )


async def test_no_guardrails_returns_ok(experiment_without_guardrails):
    with patch("app.services.rollout_engine._get_experiment", new_callable=AsyncMock, return_value=experiment_without_guardrails):
        result = await check_guardrails(AsyncMock(), AsyncMock(), uuid.uuid4())
    assert result == "ok"


async def test_guardrail_ok_when_below_threshold(experiment_with_guardrails):
    async def fake_stats(db, exp_id, group_id, metric_name):
        if group_id == experiment_with_guardrails.groups[0].id:
            return {"total_users": 100, "event_users": 5, "rate": 0.05}
        return {"total_users": 100, "event_users": 6, "rate": 0.06}

    with patch("app.services.rollout_engine._get_experiment", new_callable=AsyncMock, return_value=experiment_with_guardrails):
        with patch("app.services.rollout_engine._get_metric_stats", side_effect=fake_stats):
            with patch("app.services.rollout_engine.publish_event", new_callable=AsyncMock):
                result = await check_guardrails(AsyncMock(), AsyncMock(), uuid.uuid4())
    # degradation = 0.06 - 0.05 = 0.01 < threshold 0.05
    assert result == "ok"


async def test_guardrail_warn_when_above_threshold(experiment_with_guardrails):
    async def fake_stats(db, exp_id, group_id, metric_name):
        if group_id == experiment_with_guardrails.groups[0].id:
            return {"total_users": 100, "event_users": 5, "rate": 0.05}
        return {"total_users": 100, "event_users": 12, "rate": 0.12}

    with patch("app.services.rollout_engine._get_experiment", new_callable=AsyncMock, return_value=experiment_with_guardrails):
        with patch("app.services.rollout_engine._get_metric_stats", side_effect=fake_stats):
            with patch("app.services.rollout_engine.publish_event", new_callable=AsyncMock) as mock_publish:
                result = await check_guardrails(AsyncMock(), AsyncMock(), uuid.uuid4())
    # degradation = 0.12 - 0.05 = 0.07 > threshold 0.05 but < 2*0.05=0.10
    assert result == "warn"
    mock_publish.assert_called_once()
    call_args = mock_publish.call_args[0]
    assert call_args[1] == "rollout_guardrail_warning"
    assert call_args[2]["severity"] == "warning"


async def test_guardrail_rollback_when_above_2x_threshold(experiment_with_guardrails):
    async def fake_stats(db, exp_id, group_id, metric_name):
        if group_id == experiment_with_guardrails.groups[0].id:
            return {"total_users": 100, "event_users": 5, "rate": 0.05}
        return {"total_users": 100, "event_users": 18, "rate": 0.18}

    with patch("app.services.rollout_engine._get_experiment", new_callable=AsyncMock, return_value=experiment_with_guardrails):
        with patch("app.services.rollout_engine._get_metric_stats", side_effect=fake_stats):
            with patch("app.services.rollout_engine.publish_event", new_callable=AsyncMock) as mock_publish:
                result = await check_guardrails(AsyncMock(), AsyncMock(), uuid.uuid4())
    # degradation = 0.18 - 0.05 = 0.13 > 2*0.05=0.10
    assert result == "rollback"
    mock_publish.assert_called_once()
    call_args = mock_publish.call_args[0]
    assert call_args[2]["severity"] == "critical"


async def test_guardrail_skips_when_insufficient_users(experiment_with_guardrails):
    async def fake_stats(db, exp_id, group_id, metric_name):
        return {"total_users": 10, "event_users": 5, "rate": 0.50}

    with patch("app.services.rollout_engine._get_experiment", new_callable=AsyncMock, return_value=experiment_with_guardrails):
        with patch("app.services.rollout_engine._get_metric_stats", side_effect=fake_stats):
            result = await check_guardrails(AsyncMock(), AsyncMock(), uuid.uuid4())
    assert result == "ok"
