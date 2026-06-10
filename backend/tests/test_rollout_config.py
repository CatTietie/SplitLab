import pytest

from app.services.traffic_math import compute_effective_traffic


class FakeGroup:
    def __init__(self, id, name, traffic_percentage):
        self.id = id
        self.name = name
        self.traffic_percentage = traffic_percentage


def test_no_rollout_returns_original():
    groups = [FakeGroup(1, "control", 50), FakeGroup(2, "treatment", 50)]
    result = compute_effective_traffic(None, None, groups)
    assert [(g.name, pct) for g, pct in result] == [("control", 50), ("treatment", 50)]


def test_step_zero_10_percent():
    groups = [FakeGroup(1, "control", 50), FakeGroup(2, "treatment", 50)]
    steps = [{"traffic_percentage": 10, "hold_seconds": 60}]
    result = compute_effective_traffic(steps, 0, groups)
    by_name = {g.name: pct for g, pct in result}
    assert by_name["treatment"] == 10
    assert by_name["control"] == 90


def test_step_100_percent():
    groups = [FakeGroup(1, "control", 50), FakeGroup(2, "treatment", 50)]
    steps = [{"traffic_percentage": 100, "hold_seconds": 0}]
    result = compute_effective_traffic(steps, 0, groups)
    by_name = {g.name: pct for g, pct in result}
    assert by_name["treatment"] == 100
    assert by_name["control"] == 0


def test_multi_group_proportional_scaling():
    groups = [
        FakeGroup(1, "control", 40),
        FakeGroup(2, "treatment_a", 40),
        FakeGroup(3, "treatment_b", 20),
    ]
    steps = [{"traffic_percentage": 30, "hold_seconds": 60}]
    result = compute_effective_traffic(steps, 0, groups)
    by_name = {g.name: pct for g, pct in result}
    assert by_name["control"] == 70
    # treatment_a had 40/60=2/3 of treatment, treatment_b had 20/60=1/3
    assert by_name["treatment_a"] == 20
    assert by_name["treatment_b"] == 10
    assert sum(pct for _, pct in result) == 100


def test_empty_rollout_steps_returns_original():
    groups = [FakeGroup(1, "control", 50), FakeGroup(2, "treatment", 50)]
    result = compute_effective_traffic([], None, groups)
    assert [(g.name, pct) for g, pct in result] == [("control", 50), ("treatment", 50)]


def test_single_treatment_50_percent():
    groups = [FakeGroup(1, "control", 50), FakeGroup(2, "treatment", 50)]
    steps = [
        {"traffic_percentage": 5, "hold_seconds": 60},
        {"traffic_percentage": 50, "hold_seconds": 120},
    ]
    result = compute_effective_traffic(steps, 1, groups)
    by_name = {g.name: pct for g, pct in result}
    assert by_name["treatment"] == 50
    assert by_name["control"] == 50
