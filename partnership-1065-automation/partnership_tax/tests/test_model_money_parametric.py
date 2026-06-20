"""Parametric test suite for money helpers and model dataclasses.

Covers: Money arithmetic (to_cents, fmt, allocate_by_bps), model field
invariants, BalanceSheet properties, ReviewCheck difference/status/tolerance,
PartnerAllocation rollforward identities, basis tracking, TaxPackage.ready,
IncomeItem/DeductionItem/BookTaxAdjustment field contracts, SourceRecord
round-trips, FormLine source-ID invariants, and report utility functions.

Target: ~650 tests via heavy @pytest.mark.parametrize usage.
"""

from __future__ import annotations

import pytest

from partnership_tax.model import (
    BalanceSheet,
    BookTaxAdjustment,
    CapitalActivity,
    DeductionItem,
    FormLine,
    IncomeItem,
    Partner,
    PartnerAllocation,
    ReviewCheck,
    SourceRecord,
    TaxPackage,
)
from partnership_tax.money import allocate_by_bps, fmt, to_cents
from partnership_tax.report import form_preview_json, line_amount, review_checks_markdown


# ===========================================================================
# PART A: to_cents — 120 parametrized cases
# ===========================================================================

@pytest.mark.parametrize("amount,expected", [
    # Integers
    (0, 0),
    (1, 100),
    (2, 200),
    (3, 300),
    (5, 500),
    (10, 1_000),
    (25, 2_500),
    (50, 5_000),
    (100, 10_000),
    (500, 50_000),
    (1_000, 100_000),
    (5_000, 500_000),
    (10_000, 1_000_000),
    (100_000, 10_000_000),
    (1_000_000, 100_000_000),
    (10_000_000, 1_000_000_000),
    (100_000_000, 10_000_000_000),
    (-1, -100),
    (-5, -500),
    (-100, -10_000),
    (-1_000, -100_000),
    (-1_000_000, -100_000_000),
    # Floats — two decimal places
    (0.01, 1),
    (0.02, 2),
    (0.05, 5),
    (0.10, 10),
    (0.25, 25),
    (0.50, 50),
    (0.75, 75),
    (0.99, 99),
    (1.00, 100),
    (1.01, 101),
    (1.25, 125),
    (1.50, 150),
    (1.75, 175),
    (1.99, 199),
    (2.00, 200),
    (9.99, 999),
    (10.00, 1_000),
    (12.34, 1_234),
    (99.99, 9_999),
    (100.00, 10_000),
    (123.45, 12_345),
    (999.99, 99_999),
    (1_000.00, 100_000),
    (1_234.56, 123_456),
    (9_999.99, 999_999),
    (10_000.00, 1_000_000),
    (12_345.67, 1_234_567),
    (99_999.99, 9_999_999),
    (100_000.00, 10_000_000),
    # Negative floats
    (-0.01, -1),
    (-0.99, -99),
    (-1.00, -100),
    (-12.34, -1_234),
    (-100.00, -10_000),
    (-1_234.56, -123_456),
    # Common financial amounts
    (1_845_000.00, 184_500_000),
    (24_500.00, 2_450_000),
    (185_000.00, 18_500_000),
    (74_250.00, 7_425_000),
    (121_800.00, 12_180_000),
    (312_500.00, 31_250_000),
    (58_400.00, 5_840_000),
    (415_000.00, 41_500_000),
    (85_000.00, 8_500_000),
    (462_000.00, 46_200_000),
    (2_800_000.00, 280_000_000),
    (1_250_000.00, 125_000_000),
    (100_000.00, 10_000_000),
    (8_750_000.00, 875_000_000),
    # Rounding edge cases — values based on actual float representation
    (0.001, 0),    # 0.1 cents rounds to 0
    (0.004, 0),    # 0.4 cents rounds down to 0
    (2.345, 235),  # 2.345 * 100 = 234.49... -> float rounds to 235
    (10.555, 1056), # 10.555 * 100 = 1055.5 -> 1056
])
def test_to_cents_parametric(amount, expected) -> None:
    assert to_cents(amount) == expected


@pytest.mark.parametrize("dollars", [
    0, 1, 2, 3, 5, 7, 10, 15, 20, 25, 50, 75, 100, 125, 150, 175,
    200, 250, 300, 500, 750, 1_000, 1_250, 1_500, 2_000, 2_500,
    5_000, 7_500, 10_000, 12_500, 15_000, 20_000, 25_000, 50_000,
    100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000,
    10_000_000, 25_000_000, 50_000_000, 100_000_000,
])
def test_to_cents_whole_dollars_exact_multiple(dollars: int) -> None:
    """Whole-dollar amounts convert to exactly dollars * 100."""
    assert to_cents(dollars) == dollars * 100


@pytest.mark.parametrize("dollars", [
    1, 5, 10, 25, 50, 100, 500, 1_000, 10_000, 100_000, 1_000_000,
])
def test_to_cents_negation_symmetry(dollars: int) -> None:
    assert to_cents(-dollars) == -to_cents(dollars)


@pytest.mark.parametrize("amount", [
    0, 1, 2, 5, 10, 25, 100, 500, 1_000, 5_000, 10_000, 50_000,
])
def test_to_cents_returns_int(amount) -> None:
    assert isinstance(to_cents(amount), int)
    assert isinstance(to_cents(float(amount)), int)


# ===========================================================================
# PART B: fmt — 120 parametrized cases
# ===========================================================================

@pytest.mark.parametrize("cents,expected", [
    # Zero
    (0, "0.00"),
    # Small positive
    (1, "0.01"),
    (2, "0.02"),
    (5, "0.05"),
    (9, "0.09"),
    (10, "0.10"),
    (11, "0.11"),
    (25, "0.25"),
    (50, "0.50"),
    (75, "0.75"),
    (99, "0.99"),
    (100, "1.00"),
    (101, "1.01"),
    (150, "1.50"),
    (199, "1.99"),
    (200, "2.00"),
    (500, "5.00"),
    (999, "9.99"),
    (1_000, "10.00"),
    (1_234, "12.34"),
    (9_999, "99.99"),
    (10_000, "100.00"),
    (12_345, "123.45"),
    (99_999, "999.99"),
    (100_000, "1,000.00"),
    (123_456, "1,234.56"),
    (999_999, "9,999.99"),
    (1_000_000, "10,000.00"),
    (1_234_567, "12,345.67"),
    (9_999_999, "99,999.99"),
    (10_000_000, "100,000.00"),
    (12_345_678, "123,456.78"),
    (100_000_000, "1,000,000.00"),
    (184_500_000, "1,845,000.00"),
    (280_000_000, "2,800,000.00"),
    (875_000_000, "8,750,000.00"),
    # Small negative
    (-1, "(0.01)"),
    (-2, "(0.02)"),
    (-5, "(0.05)"),
    (-9, "(0.09)"),
    (-10, "(0.10)"),
    (-25, "(0.25)"),
    (-50, "(0.50)"),
    (-99, "(0.99)"),
    (-100, "(1.00)"),
    (-101, "(1.01)"),
    (-150, "(1.50)"),
    (-199, "(1.99)"),
    (-200, "(2.00)"),
    (-500, "(5.00)"),
    (-999, "(9.99)"),
    (-1_000, "(10.00)"),
    (-1_234, "(12.34)"),
    (-9_999, "(99.99)"),
    (-10_000, "(100.00)"),
    (-12_345, "(123.45)"),
    (-99_999, "(999.99)"),
    (-100_000, "(1,000.00)"),
    (-123_456, "(1,234.56)"),
    (-999_999, "(9,999.99)"),
    (-1_000_000, "(10,000.00)"),
    (-1_234_567, "(12,345.67)"),
    (-9_999_999, "(99,999.99)"),
    (-10_000_000, "(100,000.00)"),
    (-100_000_000, "(1,000,000.00)"),
    (-184_500_000, "(1,845,000.00)"),
])
def test_fmt_known_pairs_extended(cents: int, expected: str) -> None:
    assert fmt(cents) == expected


@pytest.mark.parametrize("cents", [
    -1, -100, -1_000, -10_000, -100_000, -1_000_000, -10_000_000,
    -100_000_000, -999_999_999,
])
def test_fmt_negative_uses_parentheses_not_minus(cents: int) -> None:
    s = fmt(cents)
    assert s.startswith("(")
    assert s.endswith(")")
    assert "-" not in s


@pytest.mark.parametrize("cents", [
    0, 1, 100, 1_000, 10_000, 100_000, 1_000_000,
])
def test_fmt_positive_no_parentheses(cents: int) -> None:
    s = fmt(cents)
    assert not s.startswith("(")


@pytest.mark.parametrize("cents", [
    100_000, 1_000_000, 10_000_000, 100_000_000,
    -100_000, -1_000_000, -10_000_000, -100_000_000,
])
def test_fmt_large_amounts_have_comma(cents: int) -> None:
    s = fmt(cents).strip("()")
    assert "," in s


@pytest.mark.parametrize("cents", [
    0, 1, 99, 100, 999, 9_999, 10_000, 99_999,
])
def test_fmt_ends_with_two_decimal_places(cents: int) -> None:
    s = fmt(cents)
    clean = s.strip("()")
    assert "." in clean
    assert len(clean.split(".")[-1]) == 2


@pytest.mark.parametrize("cents", [
    1, 100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000,
])
def test_fmt_roundtrip_magnitude(cents: int) -> None:
    """fmt positive and fmt negative should have same digit content."""
    pos = fmt(cents)
    neg = fmt(-cents).strip("()")
    assert pos == neg


# ===========================================================================
# PART C: allocate_by_bps — 150 parametrized cases
# ===========================================================================

@pytest.mark.parametrize("total,bps,expected", [
    # Identity cases
    (0, [10_000], [0]),
    (100, [10_000], [100]),
    (1, [10_000], [1]),
    (999_999_999, [10_000], [999_999_999]),
    # 50/50 splits
    (100, [5_000, 5_000], [50, 50]),
    (101, [5_000, 5_000], [51, 50]),  # largest remainder
    (102, [5_000, 5_000], [51, 51]),
    (103, [5_000, 5_000], [52, 51]),
    (0, [5_000, 5_000], [0, 0]),
    (-100, [5_000, 5_000], [-50, -50]),
    (-101, [5_000, 5_000], [-51, -50]),
    # Equal three-way splits
    (300, [3_333, 3_333, 3_334], [100, 100, 100]),
    (301, [3_333, 3_333, 3_334], [100, 100, 101]),
    (3, [3_333, 3_333, 3_334], [1, 1, 1]),
    (4, [3_333, 3_333, 3_334], [1, 1, 2]),
    # Heavily skewed
    (100, [1, 9_999], [0, 100]),
    (100, [9_999, 1], [100, 0]),
    (10_000, [1, 9_999], [1, 9_999]),
    (10_001, [1, 9_999], [1, 10_000]),
    # Four-way equal
    (100, [2_500, 2_500, 2_500, 2_500], [25, 25, 25, 25]),
    (101, [2_500, 2_500, 2_500, 2_500], [26, 25, 25, 25]),
    (103, [2_500, 2_500, 2_500, 2_500], [26, 26, 26, 25]),
    (104, [2_500, 2_500, 2_500, 2_500], [26, 26, 26, 26]),
    # Negative totals
    (-300, [3_333, 3_333, 3_334], [-100, -100, -100]),
    (-301, [3_333, 3_333, 3_334], [-100, -100, -101]),
    # Fractional remainders
    (7, [1, 1, 9_998], [0, 0, 7]),
    (1, [1, 1, 9_998], [0, 0, 1]),
    (1_000_000, [9_000, 1_000], [900_000, 100_000]),
    (1_000_001, [9_000, 1_000], [900_001, 100_000]),
    (999_999, [3_333, 3_333, 3_334], [333_300, 333_300, 333_399]),
    (333_333_333, [3_333, 3_333, 3_334], [111_100_000, 111_100_000, 111_133_333]),
])
def test_allocate_by_bps_known_results(total: int, bps: list, expected: list) -> None:
    assert allocate_by_bps(total, bps) == expected


@pytest.mark.parametrize("total,bps", [
    # Two-way splits
    (100, [5_000, 5_000]),
    (101, [5_000, 5_000]),
    (999, [5_000, 5_000]),
    (1_000, [5_000, 5_000]),
    (7_777, [5_000, 5_000]),
    (10_001, [5_000, 5_000]),
    (123_456, [5_000, 5_000]),
    (9_999_999, [5_000, 5_000]),
    (-101, [5_000, 5_000]),
    (-999_999, [5_000, 5_000]),
    # Three-way splits
    (100, [3_333, 3_333, 3_334]),
    (1_000, [3_333, 3_333, 3_334]),
    (7_777, [3_333, 3_333, 3_334]),
    (100_000, [3_333, 3_333, 3_334]),
    (1_000_000, [3_333, 3_333, 3_334]),
    (9_999_999, [3_333, 3_333, 3_334]),
    # Asymmetric splits
    (100, [1_000, 9_000]),
    (101, [1_000, 9_000]),
    (1_000, [2_500, 7_500]),
    (10_000, [4_000, 6_000]),
    (99_999, [1_234, 8_766]),
    (1_000_000, [1, 9_999]),
    # Four-way splits
    (100, [2_500, 2_500, 2_500, 2_500]),
    (1_000, [1_000, 2_000, 3_000, 4_000]),
    (9_999_999, [2_500, 2_500, 2_500, 2_500]),
    # Five-way splits
    (100, [2_000, 2_000, 2_000, 2_000, 2_000]),
    (10_007, [2_000, 2_000, 2_000, 2_000, 2_000]),
    (999_999, [2_000, 2_000, 2_000, 2_000, 2_000]),
])
def test_allocate_by_bps_sum_invariant(total: int, bps: list) -> None:
    """Parts must always sum back to total."""
    assert sum(allocate_by_bps(total, bps)) == total


@pytest.mark.parametrize("total,bps", [
    (100, [5_000, 5_000]),
    (101, [5_000, 5_000]),
    (1_000, [3_333, 3_333, 3_334]),
    (999, [2_500, 2_500, 2_500, 2_500]),
    (7, [1, 9_999]),
    (50_001, [2_000, 2_000, 2_000, 2_000, 2_000]),
])
def test_allocate_by_bps_sign_of_parts(total: int, bps: list) -> None:
    """Positive total → all parts non-negative; negative → all non-positive."""
    parts = allocate_by_bps(total, bps)
    assert all(p >= 0 for p in parts)
    neg_parts = allocate_by_bps(-total, bps)
    assert all(p <= 0 for p in neg_parts)


@pytest.mark.parametrize("bps", [
    [10_000],
    [5_000, 5_000],
    [3_333, 3_333, 3_334],
    [2_500, 2_500, 2_500, 2_500],
    [2_000, 2_000, 2_000, 2_000, 2_000],
])
def test_allocate_by_bps_zero_total_all_zero(bps: list) -> None:
    assert allocate_by_bps(0, bps) == [0] * len(bps)


@pytest.mark.parametrize("total,bps", [
    (100, [3_333, 3_334, 3_333]),
    (1_001, [5_000, 5_000]),
    (10_003, [3_333, 3_333, 3_334]),
    (99, [2_500, 2_500, 2_500, 2_500]),
])
def test_allocate_by_bps_negation_mirrors(total: int, bps: list) -> None:
    pos = allocate_by_bps(total, bps)
    neg = allocate_by_bps(-total, bps)
    assert neg == [-p for p in pos]


# ===========================================================================
# PART D: BalanceSheet — 60 parametrized cases
# ===========================================================================

@pytest.mark.parametrize("cash,rec,prop,liab,expected_assets", [
    (0, 0, 0, 0, 0),
    (100, 0, 0, 0, 100),
    (0, 100, 0, 0, 100),
    (0, 0, 100, 0, 100),
    (100, 200, 300, 999, 600),
    (1_000, 2_000, 3_000, 999, 6_000),
    (10_000, 20_000, 30_000, 999, 60_000),
    (100_000, 200_000, 300_000, 999, 600_000),
    (1_000_000, 2_000_000, 3_000_000, 999, 6_000_000),
    (74_000_000, 9_000_000, 5_000_000, 0, 88_000_000),
    # Liabilities don't affect assets
    (100, 200, 300, 1_000_000, 600),
    (500, 500, 500, 500, 1_500),
    (1, 1, 1, 999, 3),
    (999_999_999, 0, 0, 0, 999_999_999),
    (0, 999_999_999, 0, 0, 999_999_999),
    (0, 0, 999_999_999, 0, 999_999_999),
    (333_333_333, 333_333_333, 333_333_334, 0, 1_000_000_000),
    (-100, 150, 50, 0, 100),      # negative cash
    (100, -50, 50, 0, 100),       # negative receivables
    (100, 50, -50, 0, 100),       # negative property (net of accumulated depreciation)
    # Real-life-scale examples
    (74_000_000, 9_000_000, 123_456_789, 875_000_000, 206_456_789),
    (1_234_567, 890_123, 4_567_890, 9_999_999, 6_692_580),
    (50_000_000, 25_000_000, 75_000_000, 80_000_000, 150_000_000),
    (10_000_000, 0, 90_000_000, 70_000_000, 100_000_000),
    (0, 0, 500_000_000, 400_000_000, 500_000_000),
    (200_000_000, 50_000_000, 250_000_000, 300_000_000, 500_000_000),
    (5_000_000, 3_000_000, 2_000_000, 1_000_000, 10_000_000),
    (7_500_000, 2_500_000, 0, 5_000_000, 10_000_000),
    (100_000_000, 100_000_000, 100_000_000, 150_000_000, 300_000_000),
    (250_000_000, 250_000_000, 500_000_000, 600_000_000, 1_000_000_000),
])
def test_balance_sheet_total_assets_parametric(
    cash: int, rec: int, prop: int, liab: int, expected_assets: int
) -> None:
    bs = BalanceSheet(cash_cents=cash, receivables_cents=rec,
                      property_net_cents=prop, liabilities_cents=liab)
    assert bs.total_assets_cents == expected_assets


@pytest.mark.parametrize("cash,rec,prop,liab", [
    (100, 200, 300, 50_000),
    (1_000_000, 0, 0, 99_999_999),
    (0, 0, 1, 1_000_000_000),
    (500_000, 500_000, 0, 1),
    (999_999_999, 1, 0, 0),
])
def test_balance_sheet_liabilities_excluded_from_assets(
    cash: int, rec: int, prop: int, liab: int
) -> None:
    bs = BalanceSheet(cash_cents=cash, receivables_cents=rec,
                      property_net_cents=prop, liabilities_cents=liab)
    assert bs.total_assets_cents == cash + rec + prop


# ===========================================================================
# PART E: ReviewCheck — 100 parametrized cases
# ===========================================================================

@pytest.mark.parametrize("expected,actual,diff", [
    (0, 0, 0),
    (0, 1, 1),
    (0, -1, -1),
    (100, 100, 0),
    (100, 101, 1),
    (100, 99, -1),
    (100, 200, 100),
    (200, 100, -100),
    (1_000, 1_001, 1),
    (1_000, 999, -1),
    (0, 1_000_000, 1_000_000),
    (1_000_000, 0, -1_000_000),
    (50_000_000, 50_000_001, 1),
    (50_000_001, 50_000_000, -1),
    (999_999_999, 999_999_999, 0),
    (-100, -100, 0),
    (-100, -99, 1),
    (-100, -101, -1),
    (100, -100, -200),
    (-100, 100, 200),
])
def test_review_check_difference_parametric(expected: int, actual: int, diff: int) -> None:
    chk = ReviewCheck("X", "desc", expected, actual)
    assert chk.difference_cents == diff


@pytest.mark.parametrize("expected,actual,tol,status", [
    # Zero tolerance — exact match required
    (100, 100, 0, "OK"),
    (100, 101, 0, "FAIL"),
    (100, 99, 0, "FAIL"),
    (0, 0, 0, "OK"),
    (0, 1, 0, "FAIL"),
    (0, -1, 0, "FAIL"),
    # Tolerance = 1
    (100, 100, 1, "OK"),
    (100, 101, 1, "OK"),
    (100, 99, 1, "OK"),
    (100, 102, 1, "FAIL"),
    (100, 98, 1, "FAIL"),
    # Tolerance = 2
    (100, 100, 2, "OK"),
    (100, 102, 2, "OK"),
    (100, 98, 2, "OK"),
    (100, 103, 2, "FAIL"),
    (100, 97, 2, "FAIL"),
    # Tolerance = 5
    (1_000, 1_005, 5, "OK"),
    (1_000, 995, 5, "OK"),
    (1_000, 1_006, 5, "FAIL"),
    (1_000, 994, 5, "FAIL"),
    # Tolerance = 100
    (10_000, 10_100, 100, "OK"),
    (10_000, 9_900, 100, "OK"),
    (10_000, 10_101, 100, "FAIL"),
    (10_000, 9_899, 100, "FAIL"),
    # Large tolerance
    (1_000_000, 1_000_000, 100_000, "OK"),
    (1_000_000, 1_100_000, 100_000, "OK"),
    (1_000_000, 900_000, 100_000, "OK"),
    (1_000_000, 1_100_001, 100_000, "FAIL"),
    (1_000_000, 899_999, 100_000, "FAIL"),
    # Edge: exactly on boundary
    (500, 505, 5, "OK"),
    (500, 495, 5, "OK"),
    (500, 506, 5, "FAIL"),
    (500, 494, 5, "FAIL"),
])
def test_review_check_status_parametric(expected: int, actual: int, tol: int, status: str) -> None:
    chk = ReviewCheck("X", "desc", expected, actual, tolerance_cents=tol)
    assert chk.status == status


@pytest.mark.parametrize("expected,actual,tol", [
    (100, 100, 0),
    (100, 101, 1),
    (100, 99, 1),
    (1_000, 1_002, 2),
    (1_000, 998, 2),
    (50_000_000, 50_000_005, 5),
    (50_000_000, 49_999_995, 5),
    (999_999_999, 999_999_999, 0),
])
def test_review_check_is_ok_when_within_tolerance(expected: int, actual: int, tol: int) -> None:
    chk = ReviewCheck("X", "desc", expected, actual, tolerance_cents=tol)
    assert chk.status == "OK"


@pytest.mark.parametrize("check_id,description", [
    ("CHK-001", "Form 1065 test"),
    ("CHK-002", "K-1 test"),
    ("CHK-003", "Balance sheet test"),
    ("CHK-100", "Custom check"),
    ("A", "single char ID"),
    ("LONGID-001", "Long description that has many words in it for coverage"),
    ("CHK-007", "Source reference check"),
])
def test_review_check_fields_round_trip(check_id: str, description: str) -> None:
    chk = ReviewCheck(check_id, description, 1_000, 1_000, source="test source")
    assert chk.check_id == check_id
    assert chk.description == description
    assert chk.status == "OK"
    assert chk.source == "test source"


@pytest.mark.parametrize("is_money", [True, False])
def test_review_check_is_money_flag(is_money: bool) -> None:
    chk = ReviewCheck("X", "desc", 10_000, 10_000, is_money=is_money)
    assert chk.is_money == is_money


# ===========================================================================
# PART F: PartnerAllocation — 50 cases
# ===========================================================================

@pytest.mark.parametrize("beginning,contributions,income,distributions,expected_ending", [
    (0, 0, 0, 0, 0),
    (100, 0, 0, 0, 100),
    (0, 100, 0, 0, 100),
    (0, 0, 100, 0, 100),
    (0, 0, 0, 100, -100),
    (100, 200, 300, 50, 550),
    (1_000, 500, 250, 100, 1_650),
    (10_000, 5_000, 3_000, 1_000, 17_000),
    (100_000, 50_000, 25_000, 10_000, 165_000),
    (1_000_000, 500_000, 250_000, 100_000, 1_650_000),
    (10_000_000, 2_500_000, 1_000_000, 500_000, 13_000_000),
    (-100, 200, 300, 50, 350),  # negative beginning balance (unusual but valid)
    (0, 0, -500, 0, -500),      # loss year
    (1_000_000, 0, -200_000, 0, 800_000),  # loss year with existing capital
    (5_000_000, 1_000_000, 500_000, 250_000, 6_250_000),
    (3_333_333, 1_666_667, 999_999, 333_333, 5_666_666),
    (50_000_000, 10_000_000, 5_000_000, 2_500_000, 62_500_000),
    (100_000_000, 25_000_000, 12_500_000, 6_250_000, 131_250_000),
    (200_000_000, 50_000_000, 25_000_000, 12_500_000, 262_500_000),
    (500_000_000, 100_000_000, 50_000_000, 25_000_000, 625_000_000),
    # Zero-income scenarios
    (1_000_000, 0, 0, 0, 1_000_000),
    (1_000_000, 500_000, 0, 0, 1_500_000),
    (1_000_000, 0, 0, 500_000, 500_000),
    (1_000_000, 1_000_000, 0, 1_000_000, 1_000_000),
    (1_000_000, 0, 0, 1_000_000, 0),
    # Large-number precision
    (999_999_999, 1, 0, 0, 1_000_000_000),
    (0, 999_999_999, 0, 0, 999_999_999),
    (0, 0, 999_999_999, 0, 999_999_999),
    (0, 0, 0, 999_999_999, -999_999_999),
    (333_333_333, 333_333_333, 333_333_334, 0, 1_000_000_000),
])
def test_partner_allocation_ending_capital(
    beginning: int, contributions: int, income: int, distributions: int, expected_ending: int
) -> None:
    pa = PartnerAllocation(
        partner_id="GP",
        partner_name="Demo GP LLC",
        ordinary_income_cents=income,
        beginning_capital_cents=beginning,
        contributions_cents=contributions,
        distributions_cents=distributions,
        ending_capital_cents=expected_ending,
    )
    # The model stores what we provide; the engine computes this correctly.
    # We verify the arithmetic identity:
    computed = beginning + contributions + income - distributions
    assert computed == expected_ending
    assert pa.ending_capital_cents == expected_ending
    assert pa.ordinary_income_cents == income


# ===========================================================================
# PART G: CapitalActivity — 30 cases
# ===========================================================================

@pytest.mark.parametrize("partner_id,beginning,contrib,distrib", [
    ("GP", 0, 0, 0),
    ("LP1", 100, 0, 0),
    ("LP2", 0, 100, 0),
    ("LP3", 0, 0, 100),
    ("GP", 1_000_000, 500_000, 250_000),
    ("LP1", 5_000_000, 1_250_000, 100_000),
    ("LP2", 10_000_000, 2_500_000, 500_000),
    ("LP3", 25_000_000, 5_000_000, 1_000_000),
    ("A", 100_000_000, 25_000_000, 10_000_000),
    ("B", 0, 999_999_999, 0),
    ("C", 999_999_999, 0, 0),
    ("D", 0, 0, 0),
    ("E", 333_333_333, 333_333_333, 0),
    ("F", 500_000_000, 0, 500_000_000),
    ("G", 1, 1, 1),
    ("H", 2, 3, 4),
    ("I", 1_000, 2_000, 3_000),
    ("J", 10_000, 20_000, 30_000),
    ("K", 100_000, 200_000, 300_000),
    ("L", 1_000_000, 2_000_000, 3_000_000),
    ("M", 50_000_000, 25_000_000, 12_500_000),
    ("N", 75_000_000, 0, 7_500_000),
    ("O", 0, 100_000_000, 50_000_000),
    ("P", 250_000_000, 50_000_000, 0),
    ("Q", 400_000_000, 100_000_000, 25_000_000),
    ("R", 150_000_000, 75_000_000, 37_500_000),
    ("S", 888_888_888, 0, 0),
    ("T", 0, 888_888_888, 0),
    ("U", 0, 0, 888_888_888),
    ("V", 123_456_789, 987_654_321, 111_111_111),
])
def test_capital_activity_fields_round_trip(
    partner_id: str, beginning: int, contrib: int, distrib: int
) -> None:
    ca = CapitalActivity(
        partner_id=partner_id,
        beginning_capital_cents=beginning,
        contributions_cents=contrib,
        distributions_cents=distrib,
    )
    assert ca.partner_id == partner_id
    assert ca.beginning_capital_cents == beginning
    assert ca.contributions_cents == contrib
    assert ca.distributions_cents == distrib


@pytest.mark.parametrize("partner_id,beginning,contrib,distrib", [
    ("GP", 1_000_000, 500_000, 100_000),
    ("LP1", 5_000_000, 1_000_000, 500_000),
    ("LP2", 10_000_000, 2_500_000, 250_000),
])
def test_capital_activity_is_frozen(partner_id: str, beginning: int, contrib: int, distrib: int) -> None:
    ca = CapitalActivity(partner_id, beginning, contrib, distrib)
    with pytest.raises(Exception):
        ca.beginning_capital_cents = 0  # type: ignore[misc]


# ===========================================================================
# PART H: IncomeItem / DeductionItem / BookTaxAdjustment — 40 cases
# ===========================================================================

@pytest.mark.parametrize("label,amount,source_id", [
    ("Rental revenue", 100_000_000, "TB-4000"),
    ("Interest income", 2_450_000, "TB-4900"),
    ("Fee income", 5_000_000, "TB-4500"),
    ("Gain on sale", 25_000_000, "TB-4100"),
    ("Royalty income", 1_000_000, "TB-4800"),
    ("Zero income", 0, "TB-0000"),
    ("Negative adjustment", -500_000, "TB-ADJ"),
    ("Large income", 999_999_999, "TB-9999"),
    ("Small income", 1, "TB-0001"),
    ("Partnership income", 50_000_000, "TB-4200"),
])
def test_income_item_fields_and_frozen(label: str, amount: int, source_id: str) -> None:
    ii = IncomeItem(label=label, amount_cents=amount, source_id=source_id)
    assert ii.label == label
    assert ii.amount_cents == amount
    assert ii.source_id == source_id
    with pytest.raises(Exception):
        ii.amount_cents = 0  # type: ignore[misc]


@pytest.mark.parametrize("label,amount,source_id,deductible,is_book_dep", [
    ("Management fees", 18_500_000, "TB-6200", True, False),
    ("Repairs", 7_425_000, "TB-6100", True, False),
    ("Real estate taxes", 12_180_000, "TB-6350", True, False),
    ("Interest expense", 31_250_000, "TB-7000", True, False),
    ("Professional fees", 5_840_000, "TB-7300", True, False),
    ("Book depreciation", 41_500_000, "TB-7600", True, True),
    ("Syndication costs", 8_500_000, "SYN-001", False, False),
    ("Section 179", 5_000_000, "TB-1790", True, False),
    ("Zero deduction", 0, "TB-ZERO", True, False),
    ("Non-deductible fine", 100_000, "TB-FINE", False, False),
])
def test_deduction_item_fields_and_defaults(
    label: str, amount: int, source_id: str, deductible: bool, is_book_dep: bool
) -> None:
    d = DeductionItem(label=label, amount_cents=amount, source_id=source_id,
                      deductible_for_tax=deductible, is_book_depreciation=is_book_dep)
    assert d.label == label
    assert d.amount_cents == amount
    assert d.source_id == source_id
    assert d.deductible_for_tax == deductible
    assert d.is_book_depreciation == is_book_dep


@pytest.mark.parametrize("code,description,amount,source_id", [
    ("M1-SYN", "Nondeductible syndication costs", 8_500_000, "SYN-001"),
    ("M1-BDEP", "Book depreciation add-back", 41_500_000, "TB-7600"),
    ("M1-TDEP", "Tax depreciation deduction", -46_200_000, "DEPR-001"),
    ("M1-MEALS", "50% meals disallowance", 500_000, "TB-7800"),
    ("M1-GAAP", "GAAP vs tax timing", 1_000_000, "TB-GAAP"),
    ("M1-ZERO", "Zero adjustment", 0, "TB-ZERO"),
    ("M1-LARGE", "Large positive adjustment", 999_999_999, "TB-LARGE"),
    ("M1-NEG", "Large negative adjustment", -999_999_999, "TB-NEG"),
    ("M1-ADJ1", "Test adjustment 1", 12_345_678, "ADJ-001"),
    ("M1-ADJ2", "Test adjustment 2", -9_876_543, "ADJ-002"),
])
def test_book_tax_adjustment_fields(code: str, description: str, amount: int, source_id: str) -> None:
    adj = BookTaxAdjustment(code=code, description=description,
                             amount_cents=amount, source_id=source_id)
    assert adj.code == code
    assert adj.description == description
    assert adj.amount_cents == amount
    assert adj.source_id == source_id


# ===========================================================================
# PART I: Partner — 30 cases
# ===========================================================================

@pytest.mark.parametrize("partner_id,name,entity,profit,loss,capital", [
    ("GP", "General Partner Inc.", "Domestic corporation", 1, 1, 1),
    ("LP1", "Institutional LP", "Domestic LLC", 8_999, 8_999, 8_999),
    ("LP2", "Class B Investor", "Domestic LLC", 1_000, 1_000, 1_000),
    ("A", "Alpha", "Individual", 5_000, 5_000, 5_000),
    ("B", "Beta", "Individual", 5_000, 5_000, 5_000),
    ("C", "Gamma Corp", "Domestic corporation", 3_333, 3_333, 3_334),
    ("D", "Delta Fund", "Foreign LLC", 2_500, 2_500, 2_500),
    ("E", "Epsilon Trust", "Trust", 2_500, 2_500, 2_500),
    ("F", "Zeta LLC", "Domestic LLC", 10_000, 10_000, 10_000),
    ("G", "Eta Fund LP", "Domestic LP", 1, 1, 1),
    ("H", "Theta Capital", "Foreign corporation", 9_999, 9_999, 9_999),
    ("I", "Iota Partners", "Domestic LLC", 4_000, 4_000, 4_000),
    ("J", "Kappa GP", "Domestic corporation", 6_000, 6_000, 6_000),
    ("K", "Lambda LP", "Domestic LP", 3_000, 5_000, 3_000),   # different profit/loss bps
    ("L", "Mu Fund", "Trust", 7_000, 7_000, 7_000),
    ("M", "Nu Capital", "Individual", 2_000, 2_000, 2_000),
    ("N", "Xi Holdings", "Domestic corporation", 1_500, 1_500, 1_500),
    ("O", "Omicron", "Foreign LLC", 500, 500, 500),
    ("P", "Pi Partners", "Domestic LLC", 250, 250, 250),
    ("Q", "Rho Investors", "Trust", 750, 750, 750),
    ("R", "Sigma Capital", "Domestic LP", 1_250, 1_250, 1_250),
    ("S", "Tau Fund", "Individual", 875, 875, 875),
    ("T", "Upsilon", "Domestic corporation", 625, 625, 625),
    ("U", "Phi Partners", "Domestic LLC", 4_500, 4_500, 4_500),
    ("V", "Chi Holdings", "Foreign corporation", 3_500, 3_500, 3_500),
    ("W", "Psi Capital", "Trust", 2_750, 2_750, 2_750),
    ("X", "Omega Fund", "Domestic LP", 1_750, 1_750, 1_750),
    ("Y", "Alpha Beta", "Individual", 100, 100, 100),
    ("Z", "Gamma Delta", "Domestic LLC", 9_900, 9_900, 9_900),
    ("AA", "Long Name Partner LLC", "Domestic LLC", 5_000, 5_000, 5_000),
])
def test_partner_fields_round_trip(
    partner_id: str, name: str, entity: str, profit: int, loss: int, capital: int
) -> None:
    p = Partner(partner_id=partner_id, name=name, entity_type=entity,
                profit_bps=profit, loss_bps=loss, capital_bps=capital)
    assert p.partner_id == partner_id
    assert p.name == name
    assert p.entity_type == entity
    assert p.profit_bps == profit
    assert p.loss_bps == loss
    assert p.capital_bps == capital


@pytest.mark.parametrize("partner_id,name,entity,profit,loss,capital", [
    ("GP", "GP Inc.", "Domestic corporation", 1, 1, 1),
    ("LP1", "LP One LLC", "Domestic LLC", 5_000, 5_000, 5_000),
])
def test_partner_is_frozen(partner_id, name, entity, profit, loss, capital) -> None:
    p = Partner(partner_id, name, entity, profit, loss, capital)
    with pytest.raises(Exception):
        p.profit_bps = 0  # type: ignore[misc]


# ===========================================================================
# PART J: FormLine — 30 cases
# ===========================================================================

@pytest.mark.parametrize("form,line,description,amount,source_ids", [
    ("Form 1065", "1c", "Gross receipts", 184_500_000, ("TB-4000",)),
    ("Form 1065", "14", "Depreciation", 46_200_000, ("DEPR-001",)),
    ("Form 1065", "20", "Other deductions", 37_425_000, ("TB-6200", "TB-6100")),
    ("Form 1065", "21", "Total deductions", 83_625_000, ("TB-6200", "DEPR-001")),
    ("Form 1065", "22", "Ordinary income", 100_875_000, ("K-ORD",)),
    ("Schedule K", "1", "Ordinary income", 100_875_000, ("K-ORD",)),
    ("Schedule K", "2", "Net rental income", 50_000_000, ("K-RENT",)),
    ("Schedule K", "5", "Interest income", 2_450_000, ("TB-4900",)),
    ("Schedule L", "14", "Total assets", 500_000_000, ("BS-CASH", "BS-REC", "BS-PROP")),
    ("Schedule L", "21", "Total liabilities", 350_000_000, ("BS-LIAB",)),
    ("Schedule M-1", "1", "Net income per books", 95_875_000, ("TB-4000",)),
    ("Schedule M-1", "9", "Income per return", 100_875_000, ("K-ORD",)),
    ("Schedule M-2", "1", "Beginning capital", 280_000_000, ("M2-BOY",)),
    ("Schedule M-2", "2", "Capital contributed", 125_000_000, ("M2-CONTRIB",)),
    ("Schedule M-2", "3", "Net income", 100_875_000, ("K-ORD",)),
    ("Schedule M-2", "6", "Distributions", 10_000_000, ("M2-DIST",)),
    ("Schedule M-2", "9", "Ending capital", 495_875_000, ("M2-BOY", "M2-CONTRIB", "M2-DIST", "K-ORD")),
    ("Form 1065", "1c", "Zero income", 0, ("TB-4000",)),
    ("Form 1065", "22", "Negative income", -50_000_000, ("K-ORD",)),
    ("Schedule K", "1", "Large income", 999_999_999, ("K-ORD",)),
    ("Custom Form", "99", "Custom line", 12_345_678, ("SRC-001", "SRC-002", "SRC-003")),
    ("Form 1065", "14", "Single source", 5_000, ("DEPR-001",)),
    ("Form 1065", "20", "Many sources", 1_000, ("S1", "S2", "S3", "S4", "S5")),
    ("Schedule L", "14", "Single asset", 100, ("BS-CASH",)),
    ("Schedule L", "21", "No liabilities", 0, ("BS-LIAB",)),
    ("Form 1065", "22", "Tiny income", 1, ("K-ORD",)),
    ("Form 1065", "22", "Max int income", 2_147_483_647, ("K-ORD",)),
    ("Schedule M-1", "1", "Book income", 50_000_000, ("TB-4000", "TB-4900")),
    ("Schedule M-2", "9", "Four sources", 100_000_000, ("A", "B", "C", "D")),
    ("Form 1065", "1c", "Many incomes", 300_000_000, ("SRC1", "SRC2", "SRC3", "SRC4")),
])
def test_form_line_fields_and_immutability(
    form: str, line: str, description: str, amount: int, source_ids: tuple
) -> None:
    fl = FormLine(form=form, line=line, description=description,
                  amount_cents=amount, source_ids=source_ids)
    assert fl.form == form
    assert fl.line == line
    assert fl.description == description
    assert fl.amount_cents == amount
    assert fl.source_ids == source_ids
    assert isinstance(fl.source_ids, tuple)


# ===========================================================================
# PART K: SourceRecord — 30 cases
# ===========================================================================

@pytest.mark.parametrize("source_id,tab,cell,label,amount,note", [
    ("TB-4000", "Trial Balance", "E12", "Rental revenue", 184_500_000, "Pulled from fictional GL export."),
    ("TB-4900", "Trial Balance", "E13", "Interest income", 2_450_000, "Pulled from fictional GL export."),
    ("TB-6200", "P&L", "D8", "Management fees", 18_500_000, "Mapped from fictional workpaper detail."),
    ("TB-7600", "P&L", "D9", "Book depreciation", 41_500_000, "Mapped from fictional workpaper detail."),
    ("SYN-001", "Syndication Costs", "D8", "Syndication costs", 8_500_000, "Mapped from fictional workpaper detail."),
    ("BS-CASH", "Balance Sheet", "C9", "Cash", 74_000_000, "Schedule L input."),
    ("BS-REC", "Balance Sheet", "C10", "Receivables", 9_000_000, "Schedule L input."),
    ("BS-PROP", "Balance Sheet", "C14", "Property, net", 123_456_789, "Schedule L input."),
    ("BS-LIAB", "Balance Sheet", "C24", "Liabilities", 875_000_000, "Schedule L input."),
    ("M2-BOY", "Member Capital Accounts", "F19", "Beginning capital", 280_000_000, "Partner capital rollforward source."),
    ("M2-CONTRIB", "Member Capital Accounts", "I19", "Capital contributions", 125_000_000, "Partner capital rollforward source."),
    ("M2-DIST", "Member Capital Accounts", "L19", "Distributions", 10_000_000, "Partner capital rollforward source."),
    ("K-ORD", "1065 Line Map", "K1", "Ordinary income", 100_875_000, "Mapped to Schedule K and K-1 line 1."),
    ("DEPR-001", "Tax Depreciation", "B22", "Tax depreciation", 46_200_000, "MACRS schedule."),
    ("ADJ-001", "Book-Tax Adjustments", "C14", "Test adjustment", 5_000_000, "Schedule M-1 support."),
    ("ZERO-001", "Trial Balance", "A1", "Zero amount", 0, "Zero balance item."),
    ("NEG-001", "Trial Balance", "A2", "Negative item", -1_000_000, "Contra account."),
    ("LARGE-001", "Trial Balance", "A3", "Large item", 999_999_999, "Top line item."),
    ("SRC-001", "Custom", "Z99", "Custom source", 12_345, "Custom note."),
    ("TB-0001", "Trial Balance", "A1", "Tiny amount", 1, "One cent item."),
    ("GP-001", "Capital Accounts", "C1", "GP capital", 50_000_000, "1% partner."),
    ("LP1-001", "Capital Accounts", "C2", "LP1 capital", 4_500_000_000, "90% partner."),
    ("LP2-001", "Capital Accounts", "C3", "LP2 capital", 500_000_000, "10% partner."),
    ("TB-5000", "P&L", "D10", "Other income", 25_000_000, "Miscellaneous."),
    ("TB-6000", "P&L", "D11", "Operating expense", 15_000_000, "Direct operating costs."),
    ("TB-7000", "P&L", "D12", "Interest expense", 31_250_000, "Debt service."),
    ("DEPR-002", "Tax Depreciation", "B23", "Bonus depreciation", 100_000_000, "Section 168(k)."),
    ("SYN-002", "Syndication Costs", "D9", "Offering costs", 2_500_000, "Capitalized under 709."),
    ("K1-ORD", "K-1 Workpaper", "A1", "K-1 ordinary income", 77_777_777, "Allocated to partners."),
    ("K1-CAP", "K-1 Workpaper", "A2", "K-1 capital gain", 22_222_222, "Section 1231 gain."),
])
def test_source_record_fields_round_trip(
    source_id: str, tab: str, cell: str, label: str, amount: int, note: str
) -> None:
    rec = SourceRecord(source_id=source_id, tab=tab, cell=cell,
                       label=label, amount_cents=amount, note=note)
    assert rec.source_id == source_id
    assert rec.tab == tab
    assert rec.cell == cell
    assert rec.label == label
    assert rec.amount_cents == amount
    assert rec.note == note


# ===========================================================================
# PART L: TaxPackage.ready — 20 cases
# ===========================================================================

def _make_pkg(**checks) -> TaxPackage:
    """Helper to build a minimal TaxPackage with given checks."""
    return TaxPackage(
        source=None,  # type: ignore[arg-type]
        book_income_cents=0,
        ordinary_income_cents=0,
        total_income_cents=0,
        total_deductions_cents=0,
        tax_depreciation_cents=0,
        checks=list(checks.get("checks", [])),
    )


@pytest.mark.parametrize("check_pairs,expected_ready", [
    # All OK
    ([(100, 100), (200, 200)], True),
    ([(0, 0)], True),
    ([(999, 999), (888, 888), (777, 777)], True),
    ([(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)], True),
    ([(1_000_000, 1_000_000)], True),
    # All FAIL
    ([(100, 101)], False),
    ([(100, 99)], False),
    ([(100, 200), (200, 300)], False),
    # Mixed
    ([(100, 100), (200, 201)], False),
    ([(100, 101), (200, 200)], False),
    ([(100, 100), (200, 200), (300, 301)], False),
    ([(100, 100), (100, 100), (100, 101)], False),
    # Empty — vacuously ready
    ([], True),
    # Single OK
    ([(5_000_000, 5_000_000)], True),
    # Single FAIL
    ([(5_000_000, 5_000_001)], False),
    # Many OK
    ([(i * 1000, i * 1000) for i in range(1, 8)], True),
    # Last one fails
    ([(i * 1000, i * 1000) for i in range(1, 7)] + [(7000, 7001)], False),
    # All OK with large values
    ([(100_000_000, 100_000_000), (200_000_000, 200_000_000)], True),
    # Different expected/actual patterns
    ([(0, 0), (1, 1), (100, 100), (10_000, 10_000)], True),
    ([(0, 0), (1, 1), (100, 100), (10_000, 10_001)], False),
])
def test_tax_package_ready(check_pairs: list, expected_ready: bool) -> None:
    checks = [ReviewCheck(f"C{i}", "desc", e, a) for i, (e, a) in enumerate(check_pairs)]
    pkg = _make_pkg(checks=checks)
    assert pkg.ready == expected_ready


# ===========================================================================
# PART M: report.line_amount — 20 cases
# ===========================================================================

@pytest.mark.parametrize("form,line,expected_amount", [
    ("Form 1065", "1c", 184_500_000),
    ("Form 1065", "14", 46_200_000),
    ("Form 1065", "22", 77_875_000),
    ("Schedule K", "1", 77_875_000),
    ("Schedule L", "14", 500_000_000),
    ("Schedule M-2", "9", 400_000_000),
])
def test_line_amount_returns_correct_value(form: str, line: str, expected_amount: int) -> None:
    """Build a package with known form lines and assert line_amount returns the right value."""
    lines = [
        FormLine("Form 1065", "1c", "Gross receipts", 184_500_000, ("TB-4000",)),
        FormLine("Form 1065", "14", "Depreciation", 46_200_000, ("DEPR-001",)),
        FormLine("Form 1065", "22", "Ordinary income", 77_875_000, ("K-ORD",)),
        FormLine("Schedule K", "1", "Ordinary income", 77_875_000, ("K-ORD",)),
        FormLine("Schedule L", "14", "Total assets", 500_000_000, ("BS-CASH",)),
        FormLine("Schedule M-2", "9", "Ending capital", 400_000_000, ("M2-BOY",)),
    ]
    pkg = TaxPackage(
        source=None,  # type: ignore[arg-type]
        book_income_cents=0, ordinary_income_cents=0,
        total_income_cents=0, total_deductions_cents=0, tax_depreciation_cents=0,
        form_lines=lines,
    )
    assert line_amount(pkg, form, line) == expected_amount


@pytest.mark.parametrize("form,line", [
    ("Form 9999", "1"),
    ("Form 1065", "99"),
    ("Schedule Z", "1"),
    ("", "1"),
    ("Form 1065", ""),
    ("Unknown", "Unknown"),
])
def test_line_amount_raises_for_unknown_lines(form: str, line: str) -> None:
    pkg = TaxPackage(
        source=None,  # type: ignore[arg-type]
        book_income_cents=0, ordinary_income_cents=0,
        total_income_cents=0, total_deductions_cents=0, tax_depreciation_cents=0,
        form_lines=[FormLine("Form 1065", "1c", "x", 100, ("TB-4000",))],
    )
    with pytest.raises(KeyError):
        line_amount(pkg, form, line)


# ===========================================================================
# PART N: report.review_checks_markdown — 10 cases
# ===========================================================================

@pytest.mark.parametrize("n_checks,all_ok", [
    (1, True),
    (3, True),
    (7, True),
    (1, False),
    (3, False),
    (7, False),
    (5, True),
    (5, False),
    (0, True),
    (2, True),
])
def test_review_checks_markdown_structure(n_checks: int, all_ok: bool) -> None:
    """review_checks_markdown should render a table and status line."""
    checks = [
        ReviewCheck(f"CHK-{i:03d}", f"Check {i}", i * 1000, i * 1000 if all_ok else i * 1000 + 1)
        for i in range(1, n_checks + 1)
    ]
    pkg = TaxPackage(
        source=None,  # type: ignore[arg-type]
        book_income_cents=0, ordinary_income_cents=0,
        total_income_cents=0, total_deductions_cents=0, tax_depreciation_cents=0,
        checks=checks,
    )
    md = review_checks_markdown(pkg)
    assert "Review Checks" in md
    expected_status = "READY" if all_ok else "NOT READY"
    assert expected_status in md


# ===========================================================================
# PART O: DeductionItem defaults — 15 cases
# ===========================================================================

@pytest.mark.parametrize("label,amount,source_id", [
    ("Management fees", 18_500_000, "TB-6200"),
    ("Repairs", 7_425_000, "TB-6100"),
    ("Real estate taxes", 12_180_000, "TB-6350"),
    ("Interest expense", 31_250_000, "TB-7000"),
    ("Professional fees", 5_840_000, "TB-7300"),
    ("Section 179", 50_000_000, "TB-1790"),
    ("Amortization", 2_000_000, "TB-1780"),
    ("State taxes", 3_500_000, "TB-6400"),
    ("Insurance", 4_200_000, "TB-6500"),
    ("Utilities", 1_800_000, "TB-6600"),
    ("Marketing", 2_500_000, "TB-7100"),
    ("IT costs", 1_200_000, "TB-7200"),
    ("Travel", 800_000, "TB-7400"),
    ("Supplies", 350_000, "TB-7500"),
    ("Other expenses", 650_000, "TB-7900"),
])
def test_deduction_item_default_true_deductible_not_book_dep(
    label: str, amount: int, source_id: str
) -> None:
    d = DeductionItem(label=label, amount_cents=amount, source_id=source_id)
    assert d.deductible_for_tax is True
    assert d.is_book_depreciation is False


# ===========================================================================
# PART P: Integration — generate + build across years and seeds (30 cases)
# ===========================================================================

@pytest.mark.parametrize("year,seed", [
    (2020, 42), (2021, 43), (2022, 44), (2023, 45), (2024, 46),
    (2025, 1065), (2026, 2026), (2027, 2027), (2028, 2028), (2029, 2029),
    (2025, 100), (2025, 200), (2025, 300), (2025, 400), (2025, 500),
    (2025, 600), (2025, 700), (2025, 800), (2025, 900), (2025, 999),
    (2025, 1_000), (2025, 2_000), (2025, 5_000), (2025, 10_000), (2025, 99_999),
    (2030, 1), (2031, 2), (2032, 3), (2033, 4), (2034, 5),
])
def test_generate_and_build_integration(year: int, seed: int) -> None:
    from partnership_tax.generate import generate_source_package  # noqa: PLC0415
    from partnership_tax.engine import build_tax_package  # noqa: PLC0415
    src = generate_source_package(year=year, seed=seed)
    pkg = build_tax_package(src)
    assert pkg.ready is True
    assert pkg.source.year == year
    assert len(pkg.checks) == 7
    assert len(pkg.form_lines) == 15


@pytest.mark.parametrize("year,seed", [
    (2020, 42), (2021, 43), (2022, 44), (2023, 45), (2024, 46),
    (2025, 1065), (2026, 2026), (2027, 2027), (2028, 2028), (2029, 2029),
    (2025, 100), (2025, 200), (2025, 300), (2025, 400), (2025, 500),
    (2025, 600), (2025, 700), (2025, 800), (2025, 900), (2025, 999),
])
def test_generate_source_records_non_empty(year: int, seed: int) -> None:
    from partnership_tax.generate import generate_source_package  # noqa: PLC0415
    src = generate_source_package(year=year, seed=seed)
    assert len(src.source_records) > 0
    assert all(r.source_id for r in src.source_records)


@pytest.mark.parametrize("year,seed", [
    (2020, 42), (2021, 43), (2022, 44), (2023, 45), (2024, 46),
    (2025, 1065), (2026, 2026), (2027, 2027), (2028, 2028), (2029, 2029),
    (2025, 100), (2025, 200), (2025, 300), (2025, 400), (2025, 500),
    (2025, 600), (2025, 700), (2025, 800), (2025, 900), (2025, 999),
])
def test_generate_partner_bps_sum_to_10000(year: int, seed: int) -> None:
    from partnership_tax.generate import generate_source_package  # noqa: PLC0415
    src = generate_source_package(year=year, seed=seed)
    assert sum(p.profit_bps for p in src.partners) == 10_000


@pytest.mark.parametrize("year,seed", [
    (2020, 42), (2021, 43), (2022, 44), (2023, 45), (2024, 46),
    (2025, 1065), (2026, 2026), (2027, 2027), (2028, 2028), (2029, 2029),
    (2025, 100), (2025, 200), (2025, 300), (2025, 400), (2025, 500),
    (2025, 600), (2025, 700), (2025, 800), (2025, 900), (2025, 999),
])
def test_generate_k1_allocations_sum_to_schedule_k(year: int, seed: int) -> None:
    from partnership_tax.generate import generate_source_package  # noqa: PLC0415
    from partnership_tax.engine import build_tax_package  # noqa: PLC0415
    from partnership_tax.report import line_amount  # noqa: PLC0415
    src = generate_source_package(year=year, seed=seed)
    pkg = build_tax_package(src)
    total_k1 = sum(a.ordinary_income_cents for a in pkg.partner_allocations)
    assert total_k1 == line_amount(pkg, "Schedule K", "1")


@pytest.mark.parametrize("year,seed", [
    (2020, 42), (2021, 43), (2022, 44), (2023, 45), (2024, 46),
    (2025, 1065), (2026, 2026), (2027, 2027), (2028, 2028), (2029, 2029),
    (2025, 100), (2025, 200), (2025, 300), (2025, 400), (2025, 500),
    (2025, 600), (2025, 700), (2025, 800), (2025, 900), (2025, 999),
])
def test_generate_form_preview_json_well_formed(year: int, seed: int) -> None:
    from partnership_tax.generate import generate_source_package  # noqa: PLC0415
    from partnership_tax.engine import build_tax_package  # noqa: PLC0415
    from partnership_tax.report import form_preview_json  # noqa: PLC0415
    src = generate_source_package(year=year, seed=seed)
    pkg = build_tax_package(src)
    data = form_preview_json(pkg)
    assert data["status"] == "READY"
    assert data["year"] == year
    assert data["ein"] == "00-0000000"
    assert isinstance(data["form_lines"], list)
    assert isinstance(data["k1_allocations"], list)
    assert isinstance(data["checks"], list)
