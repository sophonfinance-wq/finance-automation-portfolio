"""Curated invariant grid for the partnership 1065 engine (1,500 cases).

A bounded, CI-gating slice of the SWEEP-gated ``test_bulk_invariant_grid.py``.
Every case exercises the real ``partnership_tax`` arithmetic and asserts exact
invariants over integer inputs:

* ``allocate_by_bps`` preserves the exact signed total for any two-way split;
* ``to_cents`` on an integer dollar amount equals ``dollars * 100``;
* ``IncomeItem`` frozen-dataclass fields round-trip on construction.
"""

from __future__ import annotations

import itertools

import pytest

from partnership_tax.money import allocate_by_bps, to_cents
from partnership_tax.model import IncomeItem

# 30 signed totals x 50 split points = 1,500.
_TOTALS = range(-15, 15)      # 30 values, includes negatives and zero
_SPLITS = range(1, 51)        # 50 values -> split*100 bps in [100, 5000]
_GRID = list(itertools.product(_TOTALS, _SPLITS))


@pytest.mark.parametrize("total_cents,split", _GRID)
def test_allocate_to_cents_and_item_roundtrip(total_cents: int, split: int) -> None:
    # Two-way basis-point split summing to 10,000 bps preserves the total exactly.
    bps = [split * 100, 10_000 - split * 100]
    parts = allocate_by_bps(total_cents, bps)
    assert sum(parts) == total_cents
    assert len(parts) == 2

    # Integer dollars -> cents is exact.
    assert to_cents(total_cents) == total_cents * 100

    # Frozen-dataclass field round-trip.
    item = IncomeItem(
        label=f"item-{split}",
        amount_cents=total_cents,
        source_id=f"SRC-{split}",
    )
    assert item.label == f"item-{split}"
    assert item.amount_cents == total_cents
    assert item.source_id == f"SRC-{split}"


# --- three-way allocation grid (+5,500 cases) ------------------------------
# Three-way basis-point splits summing to 10,000 bps must preserve the exact
# signed total, return one part per weight, and keep every part within one
# cent of its exact proportional share.
_TOTALS3 = [
    -12345678, -5000000, -999999, -742743, -123456, -99999, -50000, -12345,
    -5001, -1000, -743, -100, -27, -13, -7, -3, -1, 0, 1, 3, 7, 13, 27, 100,
    743, 1000, 5001, 9999, 12345, 33333, 50000, 99999, 123456, 250001, 333333,
    499999, 654321, 742743, 888888, 999999, 1000000, 1234567, 2500001, 3333333,
    4999999, 5000000, 6543210, 7427430, 8888888, 9999999, 10000000, 10000001,
    12345678, 20000001, 25000000,
]  # 55 signed totals spanning cents to eight figures
_SPLITS3 = range(1, 101)  # 100 split points


@pytest.mark.parametrize(
    "total_cents,split", list(itertools.product(_TOTALS3, _SPLITS3))
)
def test_allocate_three_way_preserves_total(total_cents: int, split: int) -> None:
    a = split * 30                      # 30..3000 bps
    b = split * 60                      # 60..6000 bps
    bps = [a, b, 10_000 - a - b]        # remainder keeps the sum at 10,000
    parts = allocate_by_bps(total_cents, bps)
    assert sum(parts) == total_cents
    assert len(parts) == 3
    # Proportionality: each part within one cent of its exact bps share
    # (a weight-ignoring allocator fails immediately).
    for i in range(3):
        assert abs(parts[i] * 10_000 - total_cents * bps[i]) <= 10_000
    # Determinism.
    assert allocate_by_bps(total_cents, bps) == parts
