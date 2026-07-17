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
