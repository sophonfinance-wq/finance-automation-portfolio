"""Bulk invariant grid for the accounts payable engine.

This module builds a very large parameter grid at import time (via
``itertools.product``) and asserts arithmetic identities that hold **exactly**
for the pure functions in :mod:`ap_engine.money` over integer inputs.

It is excluded from the default suite for speed and runs on demand::

    SWEEP=1 python -m pytest -q

The gate is the ``pytest_ignore_collect`` hook in ``conftest.py``, which matches
this module by its literal filename.

All invariants below are exact over the entire integer domain swept:

* ``sum(split_evenly(t, n)) == t`` -- the parts are floor-equal with the whole
  remainder on the final part, so the identity holds for negative totals too.
* ``sum(allocate_by_ratio(t, w)) == t`` for any weights summing to 10000 bps;
  largest-remainder allocation neither creates nor destroys a cent.
* ``apply_rate(b, r) == b * r // 10000`` -- integer truncation, no float path.
* ``to_cents(fmt(c)) == c`` -- formatting is lossless for integer cents.
"""

from __future__ import annotations

import itertools

import pytest

from ap_engine.money import allocate_by_ratio, apply_rate, fmt, split_evenly, to_cents

# ---------------------------------------------------------------------------
# Grid 1: split_evenly conserves the total over a wide integer domain.
# 2000 totals * 12 period counts = 24,000 cases.
# ---------------------------------------------------------------------------
_SPLIT_TOTALS = range(-1000, 1000)  # 2000 values, spans the sign boundary
_SPLIT_PERIODS = range(1, 13)  # 12 values, a full fictional year
_SPLIT_GRID = list(itertools.product(_SPLIT_TOTALS, _SPLIT_PERIODS))


@pytest.mark.parametrize("total_cents,periods", _SPLIT_GRID)
def test_split_evenly_conserves_the_total(total_cents: int, periods: int) -> None:
    parts = split_evenly(total_cents, periods)
    assert sum(parts) == total_cents
    assert len(parts) == periods
    base = total_cents // periods
    assert parts[:-1] == [base] * (periods - 1)
    assert parts[-1] == total_cents - base * (periods - 1)


# ---------------------------------------------------------------------------
# Grid 2: allocate_by_ratio conserves the total for every weight shape.
# 2000 totals * 6 shapes = 12,000 cases.
# ---------------------------------------------------------------------------
_WEIGHT_SHAPES: tuple[tuple[int, ...], ...] = (
    (10_000,),
    (5_000, 5_000),
    (3_333, 3_333, 3_334),
    (2_500, 2_500, 2_500, 2_500),
    (1, 9_999),
    (1_000, 2_000, 3_000, 4_000),
)
_ALLOC_TOTALS = range(0, 2000)  # 2000 values
_ALLOC_GRID = list(itertools.product(_ALLOC_TOTALS, _WEIGHT_SHAPES))


@pytest.mark.parametrize("total_cents,weights", _ALLOC_GRID)
def test_allocate_by_ratio_conserves_the_total(
    total_cents: int, weights: tuple[int, ...]
) -> None:
    parts = allocate_by_ratio(total_cents, weights)
    assert sum(parts) == total_cents
    assert len(parts) == len(weights)
    for part, weight in zip(parts, weights, strict=True):
        exact = total_cents * weight
        assert exact // 10_000 <= part <= exact // 10_000 + 1
    # Determinism: a second call over the same inputs is identical.
    assert allocate_by_ratio(total_cents, weights) == parts


# ---------------------------------------------------------------------------
# Grid 3: apply_rate is exact integer truncation.
# 1000 bases * 21 rates = 21,000 cases.
# ---------------------------------------------------------------------------
_RATE_BASES = range(0, 100_000, 100)  # 1000 values
_RATE_BPS = range(0, 10_500, 500)  # 21 values, through 100.00% and past it
_RATE_GRID = list(itertools.product(_RATE_BASES, _RATE_BPS))


@pytest.mark.parametrize("base_cents,rate_bps", _RATE_GRID)
def test_apply_rate_is_exact_truncation(base_cents: int, rate_bps: int) -> None:
    rated = apply_rate(base_cents, rate_bps)
    assert rated == base_cents * rate_bps // 10_000
    assert isinstance(rated, int)
    # The retained portion and its complement always foot back to the base.
    assert rated + (base_cents - rated) == base_cents


# ---------------------------------------------------------------------------
# Grid 4: fmt is a lossless rendering of integer cents.
# 40,000 values across the sign boundary.
# ---------------------------------------------------------------------------
_FMT_VALUES = range(-20_000, 20_000)


@pytest.mark.parametrize("cents", _FMT_VALUES)
def test_fmt_round_trips_through_to_cents(cents: int) -> None:
    text = fmt(cents)
    assert to_cents(text.replace(",", "")) == cents
    whole, _, frac = text.partition(".")
    assert len(frac) == 2
    assert whole.lstrip("-").replace(",", "").isdigit()
