"""Traffic split uniformity test.

Validates that the hashing algorithm produces < 0.5% deviation
when splitting 100K users across bucket space.
"""
import collections

from scipy.stats import chisquare

from splitlab.splitter import get_bucket, get_variant
from splitlab.models import SDKConfig, LayerConfig, ExperimentConfig, GroupConfig


def test_bucket_uniformity_100k():
    """Chi-square test: 100K users across 10000 buckets."""
    salt = "test_uniformity_salt_abc123"
    n_users = 100_000
    n_buckets = 10_000
    bucket_counts = [0] * n_buckets

    for i in range(n_users):
        user_id = f"user_{i}"
        bucket = get_bucket(user_id, salt)
        assert 0 <= bucket < n_buckets
        bucket_counts[bucket] += 1

    expected = n_users / n_buckets  # 10
    stat, p_value = chisquare(bucket_counts)

    # p > 0.01 means we cannot reject uniformity hypothesis
    assert p_value > 0.01, f"Distribution not uniform: chi2={stat:.1f}, p={p_value:.4f}"


def test_max_deviation_below_half_percent():
    """Max deviation from expected count should be < 0.5% of total users."""
    salt = "deviation_test_salt_xyz"
    n_users = 100_000
    n_buckets = 10_000
    bucket_counts = [0] * n_buckets

    for i in range(n_users):
        bucket = get_bucket(f"user_{i}", salt)
        bucket_counts[bucket] += 1

    expected = n_users / n_buckets
    max_deviation = max(abs(c - expected) for c in bucket_counts) / n_users
    assert max_deviation < 0.005, f"Max deviation {max_deviation:.4f} exceeds 0.5%"


def test_group_split_50_50():
    """Verify 50/50 split produces ~50% in each group for 100K users."""
    config = SDKConfig(
        layers=[LayerConfig(
            id="layer1",
            name="test_layer",
            salt="group_split_salt",
            experiments=[ExperimentConfig(
                id="exp1",
                key="test_exp",
                status="running",
                bucket_start=0,
                bucket_end=9999,
                groups=[
                    GroupConfig(id="g1", name="control", traffic_percentage=50),
                    GroupConfig(id="g2", name="treatment", traffic_percentage=50),
                ],
                whitelist={},
            )],
        )],
        version="1",
    )

    counts = collections.Counter()
    n_users = 100_000
    for i in range(n_users):
        variant = get_variant(f"user_{i}", "test_exp", config)
        counts[variant] += 1

    control_pct = counts["control"] / n_users
    treatment_pct = counts["treatment"] / n_users

    # Each should be ~50%, with deviation < 0.5%
    assert abs(control_pct - 0.5) < 0.005, f"Control: {control_pct:.4f}"
    assert abs(treatment_pct - 0.5) < 0.005, f"Treatment: {treatment_pct:.4f}"


def test_mutual_exclusion_within_layer():
    """Users should only appear in one experiment within a layer."""
    config = SDKConfig(
        layers=[LayerConfig(
            id="layer1",
            name="test_layer",
            salt="exclusion_salt",
            experiments=[
                ExperimentConfig(
                    id="exp1", key="exp_a", status="running",
                    bucket_start=0, bucket_end=4999,
                    groups=[GroupConfig(id="g1", name="a_group", traffic_percentage=100)],
                    whitelist={},
                ),
                ExperimentConfig(
                    id="exp2", key="exp_b", status="running",
                    bucket_start=5000, bucket_end=9999,
                    groups=[GroupConfig(id="g2", name="b_group", traffic_percentage=100)],
                    whitelist={},
                ),
            ],
        )],
        version="1",
    )

    for i in range(100_000):
        user_id = f"user_{i}"
        a = get_variant(user_id, "exp_a", config)
        b = get_variant(user_id, "exp_b", config)
        # User must be in at most one experiment
        assert not (a is not None and b is not None), f"User {user_id} in both experiments"


def test_layer_independence():
    """Same user can be in experiments in different layers (different salts)."""
    config = SDKConfig(
        layers=[
            LayerConfig(
                id="layer1", name="layer_a", salt="salt_layer_1",
                experiments=[ExperimentConfig(
                    id="exp1", key="exp_in_layer1", status="running",
                    bucket_start=0, bucket_end=9999,
                    groups=[GroupConfig(id="g1", name="group1", traffic_percentage=100)],
                    whitelist={},
                )],
            ),
            LayerConfig(
                id="layer2", name="layer_b", salt="salt_layer_2",
                experiments=[ExperimentConfig(
                    id="exp2", key="exp_in_layer2", status="running",
                    bucket_start=0, bucket_end=9999,
                    groups=[GroupConfig(id="g2", name="group2", traffic_percentage=100)],
                    whitelist={},
                )],
            ),
        ],
        version="1",
    )

    both_count = 0
    n_users = 10_000
    for i in range(n_users):
        user_id = f"user_{i}"
        v1 = get_variant(user_id, "exp_in_layer1", config)
        v2 = get_variant(user_id, "exp_in_layer2", config)
        if v1 and v2:
            both_count += 1

    # All users should be in both (full traffic in both layers)
    assert both_count == n_users


def test_whitelist_override():
    """Whitelisted user should always get the specified group."""
    config = SDKConfig(
        layers=[LayerConfig(
            id="layer1", name="test", salt="wl_salt",
            experiments=[ExperimentConfig(
                id="exp1", key="wl_exp", status="running",
                bucket_start=0, bucket_end=9999,
                groups=[
                    GroupConfig(id="g1", name="control", traffic_percentage=50),
                    GroupConfig(id="g2", name="treatment", traffic_percentage=50),
                ],
                whitelist={"vip_user": "treatment"},
            )],
        )],
        version="1",
    )

    variant = get_variant("vip_user", "wl_exp", config)
    assert variant == "treatment"
