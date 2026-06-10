"""Full E2E lifecycle test.

Tests the complete experiment lifecycle:
create layer → create experiment → start → assign users → track events → get stats → pause → rollout
"""
import collections
from splitlab.splitter import get_bucket, get_variant
from splitlab.models import SDKConfig, LayerConfig, ExperimentConfig, GroupConfig


def test_full_lifecycle_simulation():
    """Simulate complete experiment lifecycle locally."""
    # 1. Setup: create layer + experiment config
    config = SDKConfig(
        layers=[LayerConfig(
            id="homepage_layer",
            name="homepage",
            salt="homepage_salt_v1",
            experiments=[ExperimentConfig(
                id="exp_cta",
                key="homepage_cta_test",
                status="running",
                bucket_start=0,
                bucket_end=9999,
                groups=[
                    GroupConfig(id="g_ctrl", name="control", traffic_percentage=50),
                    GroupConfig(id="g_treat", name="treatment", traffic_percentage=50),
                ],
                whitelist={"admin_user": "treatment"},
            )],
        )],
        version="1",
    )

    # 2. Assign 10K users and verify split
    assignments = collections.Counter()
    n_users = 10_000
    for i in range(n_users):
        variant = get_variant(f"user_{i}", "homepage_cta_test", config)
        assert variant in ("control", "treatment")
        assignments[variant] += 1

    # Verify ~50/50 split
    assert abs(assignments["control"] / n_users - 0.5) < 0.02

    # 3. Simulate conversions (treatment has 15% rate, control 10%)
    import random
    random.seed(42)
    events = {"control": {"total": 0, "converted": 0}, "treatment": {"total": 0, "converted": 0}}

    for i in range(n_users):
        variant = get_variant(f"user_{i}", "homepage_cta_test", config)
        events[variant]["total"] += 1
        rate = 0.10 if variant == "control" else 0.15
        if random.random() < rate:
            events[variant]["converted"] += 1

    # 4. Compute stats
    import math
    ctrl = events["control"]
    treat = events["treatment"]
    p_c = ctrl["converted"] / ctrl["total"]
    p_t = treat["converted"] / treat["total"]
    p_pool = (ctrl["converted"] + treat["converted"]) / (ctrl["total"] + treat["total"])
    se = math.sqrt(p_pool * (1 - p_pool) * (1/ctrl["total"] + 1/treat["total"]))
    z = (p_t - p_c) / se

    # Should detect significant difference with 10K users
    from scipy.stats import norm
    p_value = 2 * (1 - norm.cdf(abs(z)))
    assert p_value < 0.05, f"Expected significant result, got p={p_value:.4f}"

    # 5. Simulate pause — paused experiment returns None
    paused_config = SDKConfig(
        layers=[LayerConfig(
            id="homepage_layer",
            name="homepage",
            salt="homepage_salt_v1",
            experiments=[ExperimentConfig(
                id="exp_cta",
                key="homepage_cta_test",
                status="paused",
                bucket_start=0,
                bucket_end=9999,
                groups=[
                    GroupConfig(id="g_ctrl", name="control", traffic_percentage=50),
                    GroupConfig(id="g_treat", name="treatment", traffic_percentage=50),
                ],
                whitelist={},
            )],
        )],
        version="2",
    )
    assert get_variant("user_0", "homepage_cta_test", paused_config) is None

    # 6. Whitelist override still works in running state
    assert get_variant("admin_user", "homepage_cta_test", config) == "treatment"


def test_multi_layer_experiment():
    """Multiple experiments across layers work independently."""
    config = SDKConfig(
        layers=[
            LayerConfig(
                id="layer_ui", name="ui_tests", salt="ui_salt",
                experiments=[ExperimentConfig(
                    id="exp_btn", key="button_color", status="running",
                    bucket_start=0, bucket_end=4999,
                    groups=[
                        GroupConfig(id="g1", name="blue", traffic_percentage=50),
                        GroupConfig(id="g2", name="green", traffic_percentage=50),
                    ],
                    whitelist={},
                )],
            ),
            LayerConfig(
                id="layer_algo", name="algo_tests", salt="algo_salt",
                experiments=[ExperimentConfig(
                    id="exp_sort", key="sort_algorithm", status="running",
                    bucket_start=0, bucket_end=9999,
                    groups=[
                        GroupConfig(id="g3", name="default", traffic_percentage=50),
                        GroupConfig(id="g4", name="new_ranker", traffic_percentage=50),
                    ],
                    whitelist={},
                )],
            ),
        ],
        version="1",
    )

    # User can be in experiments from different layers simultaneously
    in_both = 0
    for i in range(10_000):
        user_id = f"user_{i}"
        btn = get_variant(user_id, "button_color", config)
        sort = get_variant(user_id, "sort_algorithm", config)
        if btn is not None and sort is not None:
            in_both += 1

    # button_color only covers 50% of traffic, sort covers 100%
    # So ~50% should be in both
    assert 4500 < in_both < 5500
