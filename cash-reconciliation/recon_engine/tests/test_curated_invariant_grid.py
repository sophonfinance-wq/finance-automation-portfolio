"""Curated invariant grid for the reconciliation engine (1,500 cases).

A bounded, CI-gating slice (the exhaustive version lives in the SWEEP-gated
``test_bulk_invariant_grid.py``). Every case drives the real pure functions in
``recon_engine.engine`` and asserts exact identities over integer inputs:

* ``compute_variance(a, b) == a - b`` (rounding is a no-op on integers).
* ``classify`` bands exactly: 0 -> clean, 0 < |v| <= threshold -> timing,
  else -> flag (any integer variance >= 1 is above the 0.005 tie tolerance).
* ``lender_three_part_total`` is the exact sum of its three legs.
"""

from __future__ import annotations

import itertools

import pytest

from recon_engine.engine import (
    classify,
    compute_variance,
    lender_three_part_total,
)
from recon_engine.generate import LenderStatement

# 30 variances x 50 thresholds = 1,500.
_VARIANCE = range(0, 30)
_THRESHOLD = range(1, 51)
_GRID = list(itertools.product(_VARIANCE, _THRESHOLD))


@pytest.mark.parametrize("variance,threshold", _GRID)
def test_variance_classify_and_leg_sum(variance: int, threshold: int) -> None:
    # compute_variance is exact subtraction over integers.
    assert compute_variance(variance, 0) == variance
    assert compute_variance(threshold, variance) == threshold - variance

    # classify banding is exact for non-negative integer variances.
    if variance == 0:
        expected = "clean"
    elif variance <= threshold:
        expected = "timing"
    else:
        expected = "flag"
    assert classify(variance, threshold) == expected
    # Determinism.
    assert classify(variance, threshold) == expected

    # Three-part lender total is the exact sum of principal + interest + paydown.
    stmt = LenderStatement(
        account_number="DEBT-CUR",
        lender_name="Test Lender",
        statement_date="2026-03-31",
        principal=variance,
        current_interest_reserve=threshold,
        late_paydown=0,
    )
    assert lender_three_part_total(stmt) == variance + threshold


# --- wide-axis banding grid (+5,000 cases) ---------------------------------
# Same exact invariants as above over a wider variance/threshold lattice,
# including the negative-variance mirror (classification is symmetric in
# the sign of the variance).
_VARIANCE_W = range(0, 50)     # 50 non-negative integer variances
_THRESHOLD_W = range(1, 101)   # 100 positive integer thresholds


@pytest.mark.parametrize(
    "variance,threshold", list(itertools.product(_VARIANCE_W, _THRESHOLD_W))
)
def test_classify_banding_and_sign_symmetry(variance: int, threshold: int) -> None:
    if variance == 0:
        expected = "clean"
    elif variance <= threshold:
        expected = "timing"
    else:
        expected = "flag"
    # Positive side.
    assert classify(variance, threshold) == expected
    # Sign symmetry: classification depends only on the magnitude.
    assert classify(-variance, threshold) == expected
    # compute_variance stays an exact subtraction on integers.
    assert compute_variance(variance, threshold) == variance - threshold
