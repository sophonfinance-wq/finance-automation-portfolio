"""Tests for the money primitives (exact integer-cent arithmetic)."""

from __future__ import annotations

import pytest

from close_engine import money


def test_to_cents_rounds_half_up() -> None:
    assert money.to_cents(1200.00) == 120000
    assert money.to_cents("12.005") == 1201  # half-up at the cent
    assert money.to_cents(0) == 0


def test_fmt_groups_and_signs() -> None:
    assert money.fmt(120000) == "1,200.00"
    assert money.fmt(-5000) == "-50.00"
    assert money.fmt(5) == "0.05"


def test_split_evenly_sums_to_total() -> None:
    parts = money.split_evenly(100000, 12)
    assert sum(parts) == 100000
    assert len(parts) == 12
    # First parts equal; the remainder lands on the last part.
    assert parts[0] == 8333
    assert parts[-1] == 100000 - 8333 * 11


def test_split_evenly_exact_division() -> None:
    parts = money.split_evenly(120000, 12)
    assert parts == [10000] * 12


def test_split_evenly_rejects_zero_periods() -> None:
    with pytest.raises(ValueError):
        money.split_evenly(100, 0)


def test_allocate_by_ratio_sums_to_total() -> None:
    # 100.00 split 40/35/25 -> exact 40.00 / 35.00 / 25.00
    parts = money.allocate_by_ratio(10000, [4000, 3500, 2500])
    assert parts == [4000, 3500, 2500]
    assert sum(parts) == 10000


def test_allocate_by_ratio_largest_remainder_no_penny_lost() -> None:
    # 100.00 split into three thirds: 33.34 / 33.33 / 33.33 (largest remainder)
    parts = money.allocate_by_ratio(10000, [3334, 3333, 3333])
    assert sum(parts) == 10000


def test_allocate_by_ratio_rejects_bad_weights() -> None:
    with pytest.raises(ValueError):
        money.allocate_by_ratio(10000, [5000, 4000])  # sums to 9000, not 10000
