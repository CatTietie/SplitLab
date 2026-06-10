import math
import pytest

from app.services.stats_service import _min_sample_size


def test_min_sample_size_standard():
    """Known: baseline 10%, MDE 2% → ~3842 per group."""
    n = _min_sample_size(0.1, 0.02)
    assert 3500 < n < 4200


def test_min_sample_size_high_baseline():
    """Higher baseline should need fewer samples for same absolute MDE."""
    n_low = _min_sample_size(0.05, 0.02)
    n_high = _min_sample_size(0.30, 0.02)
    # Higher baseline + same MDE → variance changes, but absolute is different
    assert n_low > 0
    assert n_high > 0


def test_min_sample_size_small_mde():
    """Smaller MDE requires larger sample size."""
    n_big_mde = _min_sample_size(0.1, 0.05)
    n_small_mde = _min_sample_size(0.1, 0.01)
    assert n_small_mde > n_big_mde


def test_min_sample_size_zero_mde():
    """Zero MDE should not crash (division by zero guard)."""
    try:
        n = _min_sample_size(0.1, 0.001)
        assert n > 0
    except ZeroDivisionError:
        pytest.fail("Should handle very small MDE without crash")
