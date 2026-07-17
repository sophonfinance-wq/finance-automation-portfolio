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
