"""Integer-cent money primitives: exact splits, ratio allocation, formatting."""

from __future__ import annotations

import pytest

from partnership_engine.money import (
    allocate_by_ratio,
    fmt,
    split_evenly,
    to_cents,
    total,
)


def test_to_cents_rounds_half_away_from_zero():
    assert to_cents(1200.00) == 120000
    assert to_cents("1200.005") == 120001
    assert to_cents(-50.005) == -5001


def test_split_evenly_sums_exactly_and_remainder_on_last():
    parts = split_evenly(100, 3)
    assert sum(parts) == 100
    assert parts == [33, 33, 34]


def test_split_evenly_rejects_zero_periods():
    with pytest.raises(ValueError):
        split_evenly(100, 0)


def test_allocate_by_ratio_sums_to_total():
    parts = allocate_by_ratio(10_001, [5000, 5000])
    assert sum(parts) == 10_001
    assert parts == [5000, 5001] or parts == [5001, 5000]


def test_allocate_by_ratio_handles_negative_total():
    # A book loss allocated 50/50 must still sum exactly to the (negative) total.
    parts = allocate_by_ratio(-10_001, [5000, 5000])
    assert sum(parts) == -10_001


def test_allocate_by_ratio_rejects_bad_weights():
    with pytest.raises(ValueError):
        allocate_by_ratio(100, [6000, 5000])  # 110%


def test_fmt_uses_parentheses_for_negatives():
    assert fmt(120000) == "1,200.00"
    assert fmt(-5000) == "(50.00)"
    assert fmt(0) == "0.00"


def test_total_sums_iterable():
    assert total([100, 200, 300]) == 600
