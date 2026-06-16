"""Unit tests: variance, materiality classification, and the 3-part debt formula."""

from __future__ import annotations

import pytest

from recon_engine.engine import (
    TIE_TOLERANCE,
    classify,
    compute_variance,
    lender_three_part_total,
)
from recon_engine.generate import LenderStatement


# --- variance ----------------------------------------------------------------
def test_compute_variance_positive() -> None:
    assert compute_variance(100.0, 90.0) == 10.0


def test_compute_variance_negative_when_gl_below_source() -> None:
    assert compute_variance(90.0, 100.0) == -10.0


def test_compute_variance_exact_tie() -> None:
    assert compute_variance(482_150.22, 482_150.22) == 0.0


def test_compute_variance_rounds_to_cents() -> None:
    # classic float case: 1.1 - 1.0 is 0.10000000000000009 and must round to 0.10
    assert compute_variance(1.1, 1.0) == 0.10
    # sub-cent residue is dropped to the nearest cent
    assert compute_variance(100.004, 0.0) == 100.0


# --- materiality classification thresholds -----------------------------------
@pytest.mark.parametrize(
    ("variance", "expected"),
    [
        (0.0, "clean"),
        (TIE_TOLERANCE, "clean"),       # at tie tolerance -> still clean
        (0.01, "timing"),               # tiny non-zero -> timing
        (49.99, "timing"),
        (50.0, "timing"),               # exactly at threshold -> immaterial
        (-50.0, "timing"),              # sign-independent
        (50.01, "flag"),                # just over threshold -> flag
        (5000.0, "flag"),
        (-5000.0, "flag"),
    ],
)
def test_classify_thresholds(variance: float, expected: str) -> None:
    assert classify(variance, threshold=50.0) == expected


def test_classify_respects_custom_threshold() -> None:
    # With a tighter $10 threshold, $25 becomes a flag instead of timing.
    assert classify(25.0, threshold=10.0) == "flag"
    assert classify(25.0, threshold=50.0) == "timing"


# --- 3-part debt formula -----------------------------------------------------
def _lender(principal: float, interest: float, paydown: float) -> LenderStatement:
    return LenderStatement(
        account_number="DEBT-9999",
        lender_name="Test Lender",
        statement_date="2026-03-31",
        principal=principal,
        current_interest_reserve=interest,
        late_paydown=paydown,
    )


def test_three_part_formula_sums_all_legs() -> None:
    assert lender_three_part_total(_lender(1_000_000, 5_000, 7_500)) == 1_012_500.0


def test_three_part_formula_optional_paydown_zero() -> None:
    assert lender_three_part_total(_lender(1_250_000, 0.0, 0.0)) == 1_250_000.0


def test_three_part_formula_rounds_to_cents() -> None:
    assert lender_three_part_total(_lender(100.10, 0.20, 0.05)) == 100.35
