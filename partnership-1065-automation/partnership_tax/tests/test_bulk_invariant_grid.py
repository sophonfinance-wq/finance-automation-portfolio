"""Bulk invariant grid for the partnership 1065 automation engine.

The grids below are generated at import via ``itertools.product`` so the file
stays tiny while exercising tens of thousands of parameter points.  Every
assertion is an exact-arithmetic invariant of the real source code:

* ``allocate_by_bps`` preserves the exact signed total for any bps split.
* ``to_cents(int_dollars) == int_dollars * 100`` (exact integer round-trip).
* Frozen dataclass fields read back exactly as constructed (round-trip).
"""

from __future__ import annotations

import itertools

import pytest

from partnership_tax.money import allocate_by_bps, to_cents
from partnership_tax.model import IncomeItem

# ---------------------------------------------------------------------------
# Grid 1: allocate_by_bps sum-preservation (signed totals x two-way bps split).
# total in [-96, 96)  -> 192 values ; split index in [1, 100) -> 99 values.
# 192 * 99 = 19,008 cases.
# ---------------------------------------------------------------------------
_TOTALS = range(-96, 96)
_SPLITS = range(1, 100)
_ALLOC_GRID = list(itertools.product(_TOTALS, _SPLITS))


@pytest.mark.parametrize("total_cents,split", _ALLOC_GRID)
def test_allocate_preserves_total(total_cents: int, split: int) -> None:
    # Two-way basis-point split summing to 10_000 bps.
    bps = [split * 100, 10_000 - split * 100]
    parts = allocate_by_bps(total_cents, bps)
    assert sum(parts) == total_cents


# ---------------------------------------------------------------------------
# Grid 2: to_cents exact integer round-trip.
# int dollars in [-3000, 3000) -> 6000 values.
# ---------------------------------------------------------------------------
_DOLLARS = range(-3000, 3000)


@pytest.mark.parametrize("dollars", _DOLLARS)
def test_to_cents_integer_roundtrip(dollars: int) -> None:
    assert to_cents(dollars) == dollars * 100


# ---------------------------------------------------------------------------
# Grid 3: IncomeItem frozen-dataclass field round-trip.
# amount in [-20, 20) -> 40 values ; source suffix in [0, 60) -> 60 values.
# 40 * 60 = 2,400 cases.
# ---------------------------------------------------------------------------
_AMOUNTS = range(-20, 20)
_SUFFIXES = range(0, 60)
_ITEM_GRID = list(itertools.product(_AMOUNTS, _SUFFIXES))


@pytest.mark.parametrize("amount,suffix", _ITEM_GRID)
def test_income_item_roundtrip(amount: int, suffix: int) -> None:
    label = f"item-{suffix}"
    source_id = f"SRC-{suffix}"
    item = IncomeItem(label=label, amount_cents=amount, source_id=source_id)
    assert item.label == label
    assert item.amount_cents == amount
    assert item.source_id == source_id
