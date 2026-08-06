"""Money primitives: exactness, sign handling, and the penny-safe helpers."""

from __future__ import annotations

import pytest

from workpaper_engine.money import (
    AMOUNT_INVALID,
    BPS_FULL,
    AmountInvalidError,
    allocate_by_ratio,
    apply_rate,
    fmt,
    fmt_bps,
    percent_complete_bps,
    require_cents,
    split_evenly,
    to_cents,
    total,
)


# --------------------------------------------------------------------------- #
# require_cents
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [0, 1, -1, 100, -250_000, 2**40])
def test_require_cents_accepts_integers(value: int) -> None:
    assert require_cents("f", value) == value


@pytest.mark.parametrize("value", [1.0, 0.5, "100", None, [], {}, 12000000.5])
def test_require_cents_rejects_non_integers(value: object) -> None:
    with pytest.raises(AmountInvalidError) as exc:
        require_cents("field.path", value)
    assert exc.value.code == AMOUNT_INVALID
    assert "field.path" in str(exc.value)


@pytest.mark.parametrize("value", [True, False])
def test_require_cents_rejects_bool(value: bool) -> None:
    """``bool`` is an ``int`` subclass; a boolean amount is schema drift."""
    with pytest.raises(AmountInvalidError):
        require_cents("flag", value)


def test_require_cents_reports_the_unit_it_expected() -> None:
    with pytest.raises(AmountInvalidError) as exc:
        require_cents("split", 1.5, unit="integer basis points")
    assert "integer basis points" in str(exc.value)


# --------------------------------------------------------------------------- #
# to_cents / fmt
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "amount,expected",
    [
        (0, 0), (1, 100), ("1200.00", 120_000), (1200.00, 120_000),
        (0.01, 1), (-0.01, -1), ("0.005", 1), ("-0.005", -1),
        # 1.005 in binary float sits just below the half-cent boundary; routing
        # through Decimal's string form is what keeps this at 101 not 100.
        ("1.005", 101), (1.005, 101),
        ("-1200.50", -120_050),
    ],
)
def test_to_cents(amount: object, expected: int) -> None:
    assert to_cents(amount) == expected


@pytest.mark.parametrize(
    "cents,expected",
    [
        (0, "0.00"), (1, "0.01"), (100, "1.00"), (120_000, "1,200.00"),
        (-5_000, "-50.00"), (-1, "-0.01"), (645_288_889, "6,452,888.89"),
    ],
)
def test_fmt(cents: int, expected: str) -> None:
    assert fmt(cents) == expected


@pytest.mark.parametrize(
    "bps,expected",
    [(0, "0.00%"), (10000, "100.00%"), (3500, "35.00%"), (6500, "65.00%"),
     (-250, "-2.50%")],
)
def test_fmt_bps(bps: int, expected: str) -> None:
    assert fmt_bps(bps) == expected


# --------------------------------------------------------------------------- #
# split_evenly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "amount,parts", [(100, 3), (1, 3), (0, 5), (-100, 3), (999_999, 7), (10, 1)]
)
def test_split_evenly_sums_to_whole(amount: int, parts: int) -> None:
    pieces = split_evenly(amount, parts)
    assert len(pieces) == parts
    assert sum(pieces) == amount


def test_split_evenly_puts_remainder_last() -> None:
    assert split_evenly(100, 3) == [33, 33, 34]


def test_split_evenly_rejects_zero_parts() -> None:
    with pytest.raises(ValueError):
        split_evenly(100, 0)


# --------------------------------------------------------------------------- #
# allocate_by_ratio
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "amount,weights",
    [
        # The shipped sharing ratio is 35/65, so it is swept as itself.
        (100, [3500, 6500]), (100, [3333, 3333, 3334]), (1, [3500, 6500]),
        (0, [10000]), (999_999, [2500, 2500, 2500, 2500]),
        (-100, [3333, 3333, 3334]),
    ],
)
def test_allocate_by_ratio_sums_to_whole(amount: int, weights: list[int]) -> None:
    parts = allocate_by_ratio(amount, weights)
    assert len(parts) == len(weights)
    assert sum(parts) == amount


def test_allocate_by_ratio_rejects_bad_weights() -> None:
    with pytest.raises(ValueError, match="10000"):
        allocate_by_ratio(100, [3500, 6600])


def test_allocate_by_ratio_is_largest_remainder() -> None:
    """The extra penny goes to the largest fractional remainder, not the first."""
    assert allocate_by_ratio(10, [3333, 3333, 3334]) == [3, 3, 4]


def test_the_shipped_result_allocates_exactly() -> None:
    """The corpus result splits 35/65 with a remainder, and still sums back.

    This is the identity the members' capital accounts stand on: allocate an odd
    result and the two member columns must still sum to the figure the statement
    of operations reports, to the cent.
    """
    parts = allocate_by_ratio(52_488_889, [3500, 6500])
    assert parts == [18_371_111, 34_117_778]
    assert sum(parts) == 52_488_889


def test_taxable_result_allocates_exactly() -> None:
    """The same identity for the tax column, whose base differs by the adjustment."""
    parts = allocate_by_ratio(48_288_889, [3500, 6500])
    assert sum(parts) == 48_288_889
    assert parts == [16_901_111, 31_387_778]


# --------------------------------------------------------------------------- #
# apply_rate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "base,rate,expected",
    [(100_000, 1000, 10_000), (100_000, 0, 0), (0, 1000, 0),
     (999, 1000, 99), (100_000, BPS_FULL, 100_000)],
)
def test_apply_rate(base: int, rate: int, expected: int) -> None:
    assert apply_rate(base, rate) == expected


def test_apply_rate_truncates() -> None:
    """Truncation is the contract, so a derived figure compares with ==."""
    assert apply_rate(999, 1000) == 99  # not 100


# --------------------------------------------------------------------------- #
# percent_complete_bps
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "actual,budget,expected",
    [
        (400_000_000, 1_000_000_000, 4000),   # 40.00%
        (90_000_000, 130_000_000, 6923),      # 69.23%, floored
        (0, 100, 0),
        (100, 100, BPS_FULL),
        (200, 100, 20000),                    # over target reports over 100%
    ],
)
def test_percent_complete_bps(actual: int, budget: int, expected: int) -> None:
    assert percent_complete_bps(actual, budget) == expected


@pytest.mark.parametrize("budget", [0, -1, -100_000])
def test_percent_complete_bps_zero_or_negative_budget(budget: int) -> None:
    """No target means no ratio to report."""
    assert percent_complete_bps(500, budget) == 0


@pytest.mark.parametrize("actual", [0, -1, -100_000])
def test_percent_complete_bps_non_positive_actual(actual: int) -> None:
    """A net credit does not create a negative ratio."""
    assert percent_complete_bps(actual, 1_000) == 0


def test_percent_complete_floors_rather_than_rounds() -> None:
    """Flooring can only ever understate consumption, never overstate it."""
    assert percent_complete_bps(1, 3) == 3333  # not 3334


# --------------------------------------------------------------------------- #
# total
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "amounts,expected",
    [([], 0), ([1, 2, 3], 6), ([-1, 1], 0), ([100_000, -50_000], 50_000)],
)
def test_total(amounts: list[int], expected: int) -> None:
    assert total(amounts) == expected
