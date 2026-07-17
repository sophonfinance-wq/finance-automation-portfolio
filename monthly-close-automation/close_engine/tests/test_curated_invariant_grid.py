"""Curated invariant grid for the close-engine money primitives (1,500 cases).

Unlike ``test_bulk_invariant_grid.py`` (which is gated behind ``SWEEP=1`` and
generates hundreds of thousands of cases), this grid is a *bounded* slice that
runs in the default curated suite and gates CI. Every case exercises the real
``close_engine.money`` helpers and asserts exact-integer invariants:

* ``split_evenly`` preserves the total (parts sum to the input), returns exactly
  ``periods`` parts, and puts the whole rounding remainder in the final part so
  every non-final part equals ``total_cents // periods``.
* ``to_cents`` on an integer dollar amount equals ``dollars * 100`` exactly.

All invariants are pure integer identities -- no float drift, no I/O -- so every
point in the grid must hold. A regression in the money primitives fails here.
"""

import itertools

import pytest

from close_engine.money import CENTS_PER_UNIT, split_evenly, to_cents

# 15 signed totals (negatives, zero, positives) x 100 period counts = 1,500.
_TOTALS = [-100000, -743, -100, -7, -1, 0, 1, 3, 7, 100, 743, 1001, 5000, 99999, 123456]
_PERIODS = range(1, 101)  # split_evenly requires periods >= 1
_GRID = list(itertools.product(_TOTALS, _PERIODS))  # 15 * 100 = 1,500


@pytest.mark.parametrize("total_cents,periods", _GRID)
def test_split_and_to_cents_invariants(total_cents: int, periods: int) -> None:
    parts = split_evenly(total_cents, periods)

    # Sum-preservation and exact length.
    assert sum(parts) == total_cents
    assert len(parts) == periods

    # Remainder lands entirely in the final part: every non-final part equals
    # the floor quotient, and the last part carries the remainder.
    base = total_cents // periods
    assert all(p == base for p in parts[:-1])
    assert parts[-1] == total_cents - base * (periods - 1)

    # Determinism: a second call yields an identical split.
    assert split_evenly(total_cents, periods) == parts

    # Integer dollar -> cents is an exact scaling by CENTS_PER_UNIT.
    assert to_cents(total_cents) == total_cents * CENTS_PER_UNIT


# --- allocate_by_ratio grid (+6,000 cases) --------------------------------
# Two-way basis-point splits always summing to 10,000 bps. Hamilton
# (largest-remainder) allocation must preserve the signed total exactly and
# return one part per weight.
_ALLOC_TOTALS = [
    -250000, -99999, -5001, -742, -100, -13, -1, 0, 1, 7, 50, 99, 100, 101,
    743, 999, 1000, 1001, 4999, 5000, 5399, 9999, 10000, 10001, 12345, 25000,
    33333, 49999, 50000, 66667, 74300, 99998, 99999, 100000, 100001, 123456,
    200000, 250001, 333333, 499999, 500000, 654321, 742743, 888888, 999999,
    1000000, 1000001, 1234567, 2000000, 2500001, 3333333, 4999999, 5000000,
    6543210, 7427430, 8888888, 9999999, 10000000, 10000001, 12345678,
]  # 60 signed totals
_ALLOC_SPLITS = range(1, 101)  # 100 split points -> bps pairs summing to 10,000


@pytest.mark.parametrize(
    "total_cents,split", list(itertools.product(_ALLOC_TOTALS, _ALLOC_SPLITS))
)
def test_allocate_by_ratio_preserves_total(total_cents: int, split: int) -> None:
    from close_engine.money import allocate_by_ratio

    bps = [split * 50, 10_000 - split * 50]  # split in 1..100 -> 50..5000 bps
    parts = allocate_by_ratio(total_cents, bps)

    # Sum-preservation: no penny lost or created.
    assert sum(parts) == total_cents
    # One part per weight.
    assert len(parts) == 2
    # Proportionality: each part lies within one cent of its exact bps share
    # (an allocator that ignores the weights fails immediately).
    for i in range(2):
        assert abs(parts[i] * 10_000 - total_cents * bps[i]) <= 10_000
    # Determinism.
    assert allocate_by_ratio(total_cents, bps) == parts
