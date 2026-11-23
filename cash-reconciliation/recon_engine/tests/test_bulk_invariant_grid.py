"""Bulk invariant grid for the reconciliation engine.

This module builds a large parameter grid at import time (via
``itertools.product``) and asserts arithmetic identities that hold exactly for
the pure functions in :mod:`recon_engine.engine` over INTEGER inputs.

All invariants below are exact over the entire integer domain used:

* ``compute_variance(a, b) == a - b`` -- the engine returns
  ``round(gl - source, 2)``; for integers the difference is already an integer,
  so rounding is a no-op and the identity is exact.
* ``lender_three_part_total`` is the rounded sum of three legs; over integers
  the sum is exact, equalling ``principal + interest + paydown``.
* :class:`recon_engine.engine.ReconLine` is a dataclass whose fields round-trip
  on construction.
"""

from __future__ import annotations

import itertools

import pytest

from recon_engine.engine import (
    ReconLine,
    classify,
    compute_variance,
    lender_three_part_total,
)
from recon_engine.generate import LenderStatement

# ---------------------------------------------------------------------------
# Grid 1: compute_variance(a, b) == a - b over an integer product grid.
# Domain spans negatives, zero, and large positives to cover sign boundaries.
# ---------------------------------------------------------------------------
_VAR_A = range(-1317, 1317)   # 2634 values, includes 0 and negatives
_VAR_B = range(-25, 27)   # 52 values, includes 0 and negatives
_VARIANCE_GRID = list(itertools.product(_VAR_A, _VAR_B))  # 2634 * 52 = 136,968


@pytest.mark.parametrize("a,b", _VARIANCE_GRID)
def test_compute_variance_integer_identity(a: int, b: int) -> None:
    result = compute_variance(a, b)
    assert result == a - b
    # Determinism: pure function returns the same value on a second call.
    assert compute_variance(a, b) == result


# ---------------------------------------------------------------------------
# Grid 2: lender_three_part_total leg-sum identity over integer triples.
# ---------------------------------------------------------------------------
_P = range(0, 60)    # principal-like leg, 60 values
_I = range(0, 30)    # interest-reserve leg, 30 values
_L = range(0, 5)     # late-paydown leg, 5 values  -> 60 * 30 * 5 = 9,000


@pytest.mark.parametrize("p,i,l", list(itertools.product(_P, _I, _L)))
def test_lender_three_part_total_integer_identity(p: int, i: int, l: int) -> None:
    stmt = LenderStatement(
        account_number="DEBT-9999",
        lender_name="Test Lender",
        statement_date="2026-03-31",
        principal=p,
        current_interest_reserve=i,
        late_paydown=l,
    )
    total = lender_three_part_total(stmt)
    assert total == p + i + l
    # Frozen-dataclass field round-trip.
    assert stmt.principal == p
    assert stmt.current_interest_reserve == i
    assert stmt.late_paydown == l


# ---------------------------------------------------------------------------
# Grid 3: classify() banding is exact over integer variances/thresholds, and
# ReconLine fields round-trip on construction.
# ---------------------------------------------------------------------------
_VARIANCE = range(0, 90)    # 90 non-negative integer variances
_THRESHOLD = range(1, 101)  # 100 positive integer thresholds -> 9,000


@pytest.mark.parametrize("variance,threshold", list(itertools.product(_VARIANCE, _THRESHOLD)))
def test_classify_band_and_reconline_roundtrip(variance: int, threshold: int) -> None:
    cls = classify(variance, threshold)
    # variance is a non-negative integer; magnitude == variance.
    # TIE_TOLERANCE is 0.005, so any integer >= 1 is above it.
    if variance == 0:
        expected = "clean"
    elif variance <= threshold:
        expected = "timing"
    else:
        expected = "flag"
    assert cls == expected
    # Determinism.
    assert classify(variance, threshold) == cls

    # ReconLine dataclass field round-trip.
    line = ReconLine(
        entity="Demo Holdings LLC",
        account_type="cash",
        account_number="CASH-1000",
        description="op cash",
        gl_balance=variance,
        source_balance=0,
        variance=variance,
        classification=cls,
        source_label="src",
    )
    assert line.gl_balance == variance
    assert line.variance == variance
    assert line.classification == cls
    assert line.account_type == "cash"
