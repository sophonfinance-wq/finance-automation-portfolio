"""Bulk invariant grid for the close-engine money primitives.

This module generates a large Cartesian product of integer inputs at import
time and exercises two bulletproof, exact-integer invariants of the money
helpers:

* ``split_evenly`` preserves the total (the parts sum to the input) and always
  returns exactly ``periods`` parts.
* ``to_cents`` on an integer dollar amount equals ``dollars * 100`` exactly.

Both invariants are pure integer identities -- no float drift, no I/O -- so
every point in the grid must hold. The grid is built with ``itertools.product``
so the file stays small while collecting tens of thousands of cases.
"""

import itertools

import pytest

from close_engine.money import CENTS_PER_UNIT, split_evenly, to_cents

# --- split_evenly grid -----------------------------------------------------
# totals span negative, zero, and positive cents; periods are always >= 1.
_TOTALS = range(-743, 744)      # 1487 values, includes 0 and negatives
_PERIODS = range(1, 101)        # 100 values, all >= 1 (split_evenly requires)
_SPLIT_GRID = list(itertools.product(_TOTALS, _PERIODS))  # 1487 * 100 = 148,700


@pytest.mark.parametrize("total_cents,periods", _SPLIT_GRID)
def test_split_evenly_preserves_total_and_length(total_cents, periods):
    parts = split_evenly(total_cents, periods)
    assert sum(parts) == total_cents
    assert len(parts) == periods


# --- to_cents integer round-trip grid --------------------------------------
# For integer dollar inputs, to_cents is exactly dollars * 100 (no rounding).
_DOLLARS = range(-3150, 3150)   # 6,300 integer dollar values, signed


@pytest.mark.parametrize("dollars", _DOLLARS)
def test_to_cents_integer_round_trip(dollars):
    assert to_cents(dollars) == dollars * CENTS_PER_UNIT
