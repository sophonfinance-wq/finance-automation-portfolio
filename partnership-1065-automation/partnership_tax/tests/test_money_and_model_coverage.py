"""Coverage tests for the money helpers and the dataclass model.

These pin down the integer-cent arithmetic that every other module relies on
(``to_cents``, ``fmt``, ``allocate_by_bps``) plus the small computed properties
on the model dataclasses (``BalanceSheet.total_assets_cents`` and
``ReviewCheck.difference_cents`` / ``ReviewCheck.status``). All expected values
were derived from the code's actual behaviour, including its float-rounding and
largest-remainder allocation quirks.
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


# ---------------------------------------------------------------------------
# to_cents — dollars -> integer cents (rounds via float)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "amount,expected",
    [
        (0, 0),
        (1, 100),
        (5, 500),
        (12.34, 1234),
        (12.345, 1234),   # 12.345 -> 1234.49.. rounds to 1234
        (12.344, 1234),
        (0.01, 1),
        (0.99, 99),
        (100.00, 10000),
        (-1, -100),
        (-12.34, -1234),
        (-0.01, -1),
        (1_845_000, 184_500_000),
        (1.5, 150),
        (2.5, 250),
    ],
)
def test_to_cents_known_pairs(amount, expected) -> None:
    assert to_cents(amount) == expected


def test_to_cents_returns_int_type() -> None:
    assert isinstance(to_cents(12.34), int)
    assert isinstance(to_cents(7), int)


@pytest.mark.parametrize("dollars", [0, 1, 25, 100, 999, 1_250_000])
def test_to_cents_whole_dollars_is_exactly_times_100(dollars) -> None:
    assert to_cents(dollars) == dollars * 100


def test_to_cents_negation_symmetry() -> None:
    # Whole-cent magnitudes negate cleanly (no half-cent rounding involved).
    for d in (12.34, 100.0, 7.77, 0.5):
        assert to_cents(-d) == -to_cents(d)


# ---------------------------------------------------------------------------
# fmt — cents -> accounting string
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cents,expected",
    [
        (0, "0.00"),
        (1, "0.01"),
        (99, "0.99"),
        (100, "1.00"),
        (123456, "1,234.56"),
        (100000000, "1,000,000.00"),
        (-1, "(0.01)"),
        (-100, "(1.00)"),
        (-123456, "(1,234.56)"),
        (-100000000, "(1,000,000.00)"),
    ],
)
def test_fmt_known_pairs(cents, expected) -> None:
    assert fmt(cents) == expected


def test_fmt_negative_is_parenthesised_not_minus() -> None:
    s = fmt(-5000)
    assert s.startswith("(") and s.endswith(")")
    assert "-" not in s


def test_fmt_zero_is_not_parenthesised() -> None:
    assert "(" not in fmt(0)


@pytest.mark.parametrize("cents", [1, 100, 250, 999, 123456, 5_000_000])
def test_fmt_thousands_separator_present_for_large(cents) -> None:
    # >= $1,000.00 should carry at least one comma.
    if cents >= 100000:
        assert "," in fmt(cents)


# ---------------------------------------------------------------------------
# allocate_by_bps — largest-remainder, total-preserving
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "total,bps,expected",
    [
        (100, [10000], [100]),
        (100, [5000, 5000], [50, 50]),
        (101, [5000, 5000], [51, 50]),          # odd penny -> first by remainder
        (-101, [5000, 5000], [-51, -50]),       # sign preserved
        (100, [3333, 3333, 3334], [33, 33, 34]),
        (0, [5000, 5000], [0, 0]),
        (7, [1, 1, 9998], [0, 0, 7]),
        (1000000, [9000, 1000], [900000, 100000]),
        (3, [3333, 3333, 3334], [1, 1, 1]),
    ],
)
def test_allocate_by_bps_known_pairs(total, bps, expected) -> None:
    assert allocate_by_bps(total, bps) == expected


@pytest.mark.parametrize(
    "total,bps",
    [
        (100, [5000, 5000]),
        (101, [5000, 5000]),
        (999983, [3333, 3333, 3334]),
        (-777, [2500, 2500, 5000]),
        (1, [1, 9999]),
        (123456789, [4000, 3500, 2500]),
    ],
)
def test_allocate_by_bps_sums_exactly_to_total(total, bps) -> None:
    """The defining invariant: parts always sum back to the original total."""
    assert sum(allocate_by_bps(total, bps)) == total


@pytest.mark.parametrize(
    "total,bps",
    [
        (101, [5000, 5000]),
        (777, [2500, 2500, 5000]),
        (1, [1, 9999]),
        (50, [3333, 3333, 3334]),
    ],
)
def test_allocate_by_bps_all_parts_share_sign_of_total(total, bps) -> None:
    parts = allocate_by_bps(total, bps)
    assert all(p >= 0 for p in parts)
    neg = allocate_by_bps(-total, bps)
    assert all(p <= 0 for p in neg)


def test_allocate_by_bps_negation_mirrors_positive() -> None:
    pos = allocate_by_bps(101, [3333, 3333, 3334])
    neg = allocate_by_bps(-101, [3333, 3333, 3334])
    assert neg == [-p for p in pos]


def test_allocate_by_bps_zero_total_is_all_zero() -> None:
    assert allocate_by_bps(0, [2500, 2500, 5000]) == [0, 0, 0]


def test_allocate_by_bps_largest_remainder_gets_the_penny() -> None:
    # total 100, weights 3333/3334/3333: raw remainders favour the 3334 bucket.
    assert allocate_by_bps(100, [3333, 3334, 3333]) == [33, 34, 33]


# ---------------------------------------------------------------------------
# BalanceSheet.total_assets_cents
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cash,rec,prop,expected",
    [
        (0, 0, 0, 0),
        (100, 200, 300, 600),
        (74_000_000, 9_000_000, 5_000_000, 88_000_000),
        (-100, 50, 50, 0),
    ],
)
def test_balance_sheet_total_assets(cash, rec, prop, expected) -> None:
    bs = BalanceSheet(
        cash_cents=cash, receivables_cents=rec,
        property_net_cents=prop, liabilities_cents=999,
    )
    assert bs.total_assets_cents == expected


def test_balance_sheet_excludes_liabilities_from_assets() -> None:
    bs = BalanceSheet(cash_cents=100, receivables_cents=0,
                      property_net_cents=0, liabilities_cents=500)
    assert bs.total_assets_cents == 100


# ---------------------------------------------------------------------------
# ReviewCheck — difference and status
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "expected,actual,diff",
    [
        (100, 100, 0),
        (100, 103, 3),
        (100, 98, -2),
        (0, -5, -5),
        (50, 75, 25),
    ],
)
def test_review_check_difference(expected, actual, diff) -> None:
    assert ReviewCheck("C", "d", expected, actual).difference_cents == diff


@pytest.mark.parametrize(
    "expected,actual,tol,status",
    [
        (100, 100, 0, "OK"),
        (100, 101, 0, "FAIL"),
        (100, 102, 2, "OK"),
        (100, 98, 2, "OK"),
        (100, 103, 2, "FAIL"),
        (100, 97, 2, "FAIL"),
    ],
)
def test_review_check_status_respects_tolerance(expected, actual, tol, status) -> None:
    chk = ReviewCheck("C", "d", expected, actual, tolerance_cents=tol)
    assert chk.status == status


def test_review_check_status_symmetric_around_tolerance() -> None:
    over = ReviewCheck("C", "d", 100, 105, tolerance_cents=5)
    under = ReviewCheck("C", "d", 100, 95, tolerance_cents=5)
    assert over.status == "OK"
    assert under.status == "OK"
    assert ReviewCheck("C", "d", 100, 106, tolerance_cents=5).status == "FAIL"


# ---------------------------------------------------------------------------
# Frozen dataclasses are immutable; defaults applied
# ---------------------------------------------------------------------------
def test_partner_is_frozen() -> None:
    p = Partner("GP", "Demo", "corp", 1, 1, 1)
    with pytest.raises(Exception):
        p.profit_bps = 99  # type: ignore[misc]


def test_deduction_item_defaults() -> None:
    d = DeductionItem("Repairs", 100, "TB-1")
    assert d.deductible_for_tax is True
    assert d.is_book_depreciation is False


def test_form_line_source_ids_is_tuple() -> None:
    fl = FormLine("Form 1065", "1c", "x", 100, ("A", "B"))
    assert isinstance(fl.source_ids, tuple)
    assert fl.source_ids == ("A", "B")


def test_taxpackage_ready_true_when_all_checks_ok() -> None:
    pkg = TaxPackage(
        source=None,  # type: ignore[arg-type]
        book_income_cents=0, ordinary_income_cents=0, total_income_cents=0,
        total_deductions_cents=0, tax_depreciation_cents=0,
        checks=[ReviewCheck("A", "d", 1, 1), ReviewCheck("B", "d", 2, 2)],
    )
    assert pkg.ready is True


def test_taxpackage_ready_false_when_any_check_fails() -> None:
    pkg = TaxPackage(
        source=None,  # type: ignore[arg-type]
        book_income_cents=0, ordinary_income_cents=0, total_income_cents=0,
        total_deductions_cents=0, tax_depreciation_cents=0,
        checks=[ReviewCheck("A", "d", 1, 1), ReviewCheck("B", "d", 2, 99)],
    )
    assert pkg.ready is False


def test_taxpackage_ready_true_with_no_checks() -> None:
    # all() of an empty iterable is True — vacuously ready.
    pkg = TaxPackage(
        source=None,  # type: ignore[arg-type]
        book_income_cents=0, ordinary_income_cents=0, total_income_cents=0,
        total_deductions_cents=0, tax_depreciation_cents=0,
    )
    assert pkg.ready is True


def test_capital_activity_and_income_item_are_frozen() -> None:
    ca = CapitalActivity("GP", 1, 2, 3)
    with pytest.raises(Exception):
        ca.contributions_cents = 9  # type: ignore[misc]
    ii = IncomeItem("Rent", 100, "TB-1")
    with pytest.raises(Exception):
        ii.amount_cents = 0  # type: ignore[misc]


def test_source_record_and_adjustment_round_trip_fields() -> None:
    rec = SourceRecord("S1", "Tab", "A1", "Label", 500, "note")
    assert (rec.source_id, rec.amount_cents) == ("S1", 500)
    adj = BookTaxAdjustment("M1-X", "desc", -250, "S1")
    assert adj.amount_cents == -250


def test_partner_allocation_holds_rollforward_fields() -> None:
    pa = PartnerAllocation("GP", "Demo", 10, 20, 30, 5, 55)
    assert pa.ending_capital_cents == 55
    assert pa.ordinary_income_cents == 10
