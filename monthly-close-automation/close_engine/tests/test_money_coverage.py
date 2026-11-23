"""Additional coverage for the money primitives.

Exercises boundary/edge values, sign handling, the invariant that splits and
allocations conserve the total to the penny, idempotency of round-tripping
cents through :func:`fmt`, and the error paths. Values are derived from the
module's ACTUAL observed behavior (e.g. half-away-from-zero rounding on
negatives), not from an idealized spec.
"""

from __future__ import annotations

import pytest

from close_engine import money


# --------------------------------------------------------------------------- #
# to_cents — rounding boundaries and sign handling
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "dollars, expected_cents",
    [
        (0, 0),
        (0.0, 0),
        (1, 100),
        (1.00, 100),
        (12.34, 1234),
        ("12.34", 1234),
        (12.005, 1201),  # half-up at the cent boundary
        ("12.005", 1201),
        (0.004, 0),  # below the half boundary rounds down
        (0.005, 1),  # exactly half rounds up
        (-1.0, -100),
        (-12.34, -1234),
        (-0.005, -1),  # half-away-from-zero for negatives
        (-12.005, -1201),
        (1000000, 100000000),
    ],
)
def test_to_cents_boundaries(dollars, expected_cents) -> None:
    assert money.to_cents(dollars) == expected_cents


def test_to_cents_accepts_string_and_float_equivalently() -> None:
    assert money.to_cents("250.50") == money.to_cents(250.50)


# --------------------------------------------------------------------------- #
# fmt — formatting, grouping, sign, and the two-decimal invariant
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cents, expected",
    [
        (0, "0.00"),
        (5, "0.05"),
        (50, "0.50"),
        (99, "0.99"),
        (100, "1.00"),
        (120000, "1,200.00"),
        (-5000, "-50.00"),
        (-1, "-0.01"),
        (1, "0.01"),
        (1234567, "12,345.67"),
        (-1234567, "-12,345.67"),
        (100000000, "1,000,000.00"),
    ],
)
def test_fmt_values(cents, expected) -> None:
    assert money.fmt(cents) == expected


@pytest.mark.parametrize("cents", [0, 1, -1, 99, 100, 250050, -250050, 7])
def test_fmt_always_has_two_decimal_places(cents) -> None:
    text = money.fmt(cents)
    assert "." in text
    assert len(text.split(".")[-1]) == 2


@pytest.mark.parametrize("cents", [0, 1, 99, 100, 120000, 1234567, 5])
def test_fmt_round_trips_back_to_cents(cents) -> None:
    # Formatting cents to a dollar string and back through to_cents is a
    # lossless round trip for non-negative amounts.
    assert money.to_cents(money.fmt(cents).replace(",", "")) == cents


# --------------------------------------------------------------------------- #
# split_evenly — conservation, remainder placement, edge counts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "total, periods",
    [
        (100000, 12),
        (100000, 7),
        (1, 1),
        (1, 3),
        (0, 5),
        (10001, 3),
        (999999, 11),
        (7, 1),
        (-100, 3),
        (-100000, 12),
    ],
)
def test_split_evenly_conserves_total(total, periods) -> None:
    parts = money.split_evenly(total, periods)
    assert sum(parts) == total
    assert len(parts) == periods


def test_split_evenly_remainder_lands_on_last_part() -> None:
    parts = money.split_evenly(100, 3)
    assert parts == [33, 33, 34]
    # All but the last share the floor amount.
    assert parts[:-1] == [33, 33]


def test_split_evenly_single_period_returns_whole() -> None:
    assert money.split_evenly(12345, 1) == [12345]


def test_split_evenly_zero_total_is_all_zeros() -> None:
    assert money.split_evenly(0, 4) == [0, 0, 0, 0]


def test_split_evenly_negative_remainder_on_last() -> None:
    # Observed behavior: floor division on negatives pushes the remainder onto
    # the final element while still conserving the total.
    parts = money.split_evenly(-100, 3)
    assert parts == [-34, -34, -32]
    assert sum(parts) == -100


@pytest.mark.parametrize("periods", [0, -1, -5])
def test_split_evenly_rejects_non_positive_periods(periods) -> None:
    with pytest.raises(ValueError):
        money.split_evenly(100, periods)


# --------------------------------------------------------------------------- #
# allocate_by_ratio — Hamilton largest-remainder conservation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "total, weights",
    [
        (10000, [4000, 3500, 2500]),
        (10000, [3334, 3333, 3333]),
        (100, [3334, 3333, 3333]),
        (101, [10000]),
        (1, [5000, 5000]),
        (0, [5000, 5000]),
        (99999, [5000, 3000, 2000]),
        (777, [2500, 2500, 2500, 2500]),
        (10, [9999, 1]),
    ],
)
def test_allocate_by_ratio_conserves_total(total, weights) -> None:
    parts = money.allocate_by_ratio(total, weights)
    assert sum(parts) == total
    assert len(parts) == len(weights)


def test_allocate_by_ratio_exact_split_no_remainder() -> None:
    assert money.allocate_by_ratio(10000, [4000, 3500, 2500]) == [4000, 3500, 2500]


def test_allocate_by_ratio_zero_weight_gets_nothing() -> None:
    assert money.allocate_by_ratio(100, [0, 10000]) == [0, 100]


def test_allocate_by_ratio_largest_remainder_gets_extra_penny() -> None:
    # 1 cent split 50/50: a single penny goes to the first (tie broken by index).
    assert money.allocate_by_ratio(1, [5000, 5000]) == [1, 0]


@pytest.mark.parametrize(
    "weights",
    [
        [5000, 4000],  # 9000
        [5000, 5001],  # 10001
        [10000, 1],  # 10001
        [0, 0],  # 0
        [3333, 3333, 3333],  # 9999
    ],
)
def test_allocate_by_ratio_rejects_weights_not_summing_to_10000(weights) -> None:
    with pytest.raises(ValueError):
        money.allocate_by_ratio(10000, weights)


# --------------------------------------------------------------------------- #
# total
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "amounts, expected",
    [
        ([], 0),
        ([100], 100),
        ([100, 200, 300], 600),
        ([100, -100], 0),
        ([-1, -2, -3], -6),
        (range(1, 5), 10),
    ],
)
def test_total_sums_iterable(amounts, expected) -> None:
    assert money.total(amounts) == expected


def test_total_consumes_generator() -> None:
    assert money.total(x * 2 for x in (10, 20, 30)) == 120
