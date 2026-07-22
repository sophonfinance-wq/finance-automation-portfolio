"""Integer-cent invariants. Money is exact here or the engine is worthless."""

from __future__ import annotations

import pytest

from ap_engine.money import (
    AMOUNT_INVALID,
    CENTS_PER_UNIT,
    AmountInvalidError,
    allocate_by_ratio,
    apply_rate,
    fmt,
    require_cents,
    split_evenly,
    to_cents,
)


# --------------------------------------------------------------------------- #
# to_cents / fmt
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "amount,expected",
    [
        (0, 0),
        (1, 100),
        (1200.00, 120_000),
        ("1200.00", 120_000),
        (0.005, 1),  # half-up on the cent boundary
        (-0.005, -1),  # symmetric away from zero
        (-1200.00, -120_000),
        (12.345, 1_235),
    ],
)
def test_to_cents_rounds_half_up(amount, expected: int) -> None:
    assert to_cents(amount) == expected
    assert isinstance(to_cents(amount), int)


@pytest.mark.parametrize(
    "cents,expected",
    [
        (0, "0.00"),
        (5, "0.05"),
        (120_000, "1,200.00"),
        (-5_000, "-50.00"),
        (-1, "-0.01"),
        (1_234_567_890, "12,345,678.90"),
    ],
)
def test_fmt_is_float_free_and_stable(cents: int, expected: str) -> None:
    assert fmt(cents) == expected


def test_fmt_round_trips_through_to_cents() -> None:
    for cents in range(-2_500, 2_500, 7):
        assert to_cents(fmt(cents).replace(",", "")) == cents


def test_cents_per_unit_is_the_atomic_scale() -> None:
    assert CENTS_PER_UNIT == 100
    assert to_cents(1) == CENTS_PER_UNIT


# --------------------------------------------------------------------------- #
# split_evenly
# --------------------------------------------------------------------------- #
def test_split_evenly_sums_back_to_the_whole() -> None:
    for total_cents in (0, 1, 99, 100, 1_000_003, -7):
        for periods in range(1, 13):
            parts = split_evenly(total_cents, periods)
            assert len(parts) == periods
            assert sum(parts) == total_cents
            assert all(isinstance(p, int) for p in parts)


def test_split_evenly_puts_the_remainder_on_the_last_part() -> None:
    parts = split_evenly(100, 3)
    assert parts == [33, 33, 34]
    assert parts[-1] != parts[0]
    # And the first parts are all identical, so drift cannot accumulate.
    assert len(set(parts[:-1])) == 1


def test_split_evenly_rejects_zero_periods() -> None:
    with pytest.raises(ValueError, match="periods must be >= 1"):
        split_evenly(100, 0)
    with pytest.raises(ValueError):
        split_evenly(100, -3)


# --------------------------------------------------------------------------- #
# allocate_by_ratio
# --------------------------------------------------------------------------- #
def test_allocate_by_ratio_requires_ten_thousand_bps() -> None:
    """Weights that do not sum to 100.00% raise rather than silently normalise."""
    with pytest.raises(ValueError) as excinfo:
        allocate_by_ratio(1_000, [5_000, 4_000])
    assert "10000 bps" in str(excinfo.value)
    assert "9000" in str(excinfo.value)

    with pytest.raises(ValueError):
        allocate_by_ratio(1_000, [5_000, 6_000])
    with pytest.raises(ValueError):
        allocate_by_ratio(1_000, [])


def test_allocate_by_ratio_creates_and_loses_no_penny() -> None:
    weights = [3_333, 3_333, 3_334]
    for total_cents in range(0, 500):
        parts = allocate_by_ratio(total_cents, weights)
        assert sum(parts) == total_cents
        assert len(parts) == len(weights)


def test_allocate_by_ratio_uses_largest_remainder() -> None:
    """The leftover cent lands on the largest fractional remainder, not the last."""
    parts = allocate_by_ratio(10, [3_333, 3_333, 3_334])
    assert sum(parts) == 10
    assert parts == [3, 3, 4]

    # One cent across the same weights lands on the largest weight, not the last
    # index by default; ties break on the lower index, which keeps it stable.
    parts = allocate_by_ratio(1, [3_333, 3_333, 3_334])
    assert parts == [0, 0, 1]
    assert allocate_by_ratio(1, [5_000, 5_000]) == [1, 0]


def test_allocate_by_ratio_handles_a_single_full_weight() -> None:
    assert allocate_by_ratio(12_345, [10_000]) == [12_345]


# --------------------------------------------------------------------------- #
# apply_rate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "base,bps,expected",
    [
        (100_000, 1_000, 10_000),  # 10.00% retention
        (100_000, 0, 0),
        (100_000, 10_000, 100_000),
        (99_999, 875, 8_749),  # truncating, never rounding up
        (1, 5_000, 0),
    ],
)
def test_apply_rate_truncates(base: int, bps: int, expected: int) -> None:
    assert apply_rate(base, bps) == expected
    assert isinstance(apply_rate(base, bps), int)


# --------------------------------------------------------------------------- #
# require_cents
# --------------------------------------------------------------------------- #
def test_require_cents_passes_integers_through() -> None:
    assert require_cents("doc/amount_cents", 0) == 0
    assert require_cents("doc/amount_cents", -12_345) == -12_345


@pytest.mark.parametrize("bad", [1234.56, "1234", None, [1], {"a": 1}, True, False])
def test_require_cents_rejects_non_integers(bad: object) -> None:
    """Floats, strings and booleans are refused rather than coerced."""
    with pytest.raises(AmountInvalidError) as excinfo:
        require_cents("POST-2026-0001/gl_recap.debit_cents", bad)
    error = excinfo.value
    assert error.code == AMOUNT_INVALID
    assert error.field == "POST-2026-0001/gl_recap.debit_cents"
    assert error.value is bad or error.value == bad
    assert AMOUNT_INVALID in str(error)
    assert repr(bad) in str(error)


def test_require_cents_unit_appears_in_the_message() -> None:
    with pytest.raises(AmountInvalidError, match="a whole count"):
        require_cents("POST-2026-0001/rejected.entries", 1.5, unit="a whole count")


def test_amount_invalid_error_is_a_value_error() -> None:
    """Callers that only catch ValueError still behave."""
    assert issubclass(AmountInvalidError, ValueError)
