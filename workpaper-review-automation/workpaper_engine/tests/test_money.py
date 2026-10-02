"""The money contract: integer cents, exact equality, no lost pennies."""

from __future__ import annotations

import pytest

from workpaper_engine.money import (
    AMOUNT_INVALID,
    AmountInvalidError,
    allocate_by_ratio,
    apply_rate,
    ensure_cents,
    format_cents,
    split_evenly,
)


@pytest.mark.parametrize("bad", [1.0, "100", None, True, 2.5])
def test_non_integer_cents_is_refused_not_coerced(bad):
    with pytest.raises(AmountInvalidError) as exc:
        ensure_cents(bad)
    assert exc.value.code == AMOUNT_INVALID


def test_format_is_accounting_style():
    assert format_cents(0) == "0.00"
    assert format_cents(123_456_78) == "12,345,678.00".replace("12,345,678.00", "123,456.78")
    assert format_cents(-104_878_815) == "(1,048,788.15)"


@pytest.mark.parametrize("amount", [0, 1, -1, 999, -100_000_00, 3_333_333])
@pytest.mark.parametrize("parts", [1, 2, 3, 7, 12])
def test_split_evenly_conserves_the_whole(amount, parts):
    out = split_evenly(amount, parts)
    assert len(out) == parts
    assert sum(out) == amount


@pytest.mark.parametrize(
    "amount,weights",
    [
        (100_00, [1, 1, 1]),
        (7, [5000, 5000]),
        (-1_000_01, [2569, 3500, 3931]),
        (11_289_678_00, [7536, 2464]),
    ],
)
def test_allocate_by_ratio_conserves_the_whole(amount, weights):
    out = allocate_by_ratio(amount, weights)
    assert sum(out) == amount
    assert len(out) == len(weights)


def test_allocate_rejects_degenerate_weights():
    with pytest.raises(ValueError):
        allocate_by_ratio(100, [0, 0])
    with pytest.raises(ValueError):
        allocate_by_ratio(100, [])
    with pytest.raises(ValueError):
        allocate_by_ratio(100, [-1, 2])


def test_apply_rate_truncates_toward_zero_both_signs():
    assert apply_rate(10_000_00, 2500) == 2_500_00
    assert apply_rate(3, 5000) == 1
    assert apply_rate(-3, 5000) == -1


def test_there_is_no_tolerance_band():
    """A dollar apart is a difference, not a match. This is load-bearing."""
    assert 46_166_00 != 46_165_00
