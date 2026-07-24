"""Extended curated invariant grid -- exact identities over the shared money kernel.

Every assertion below is an exact equality checked across a bounded integer-cent
domain, so it gates CI on every push rather than living behind ``SWEEP=1``. These
are the arithmetic identities every control in this engine ultimately reduces to:
a split that conserves its total, a ratio allocation that neither loses nor mints
a cent, and a rate applied as exact truncating integer math. They are swept over
the engine's own ``money`` module, which is the kernel each control shares.
"""
from __future__ import annotations

import itertools

import pytest

from upgrade_engine.money import allocate_by_ratio, apply_rate, split_evenly

# --------------------------------------------------------------------------- #
# Grid 1: split_evenly conserves the total exactly, for negative, zero and
# positive totals across one, two and three parts. 2,000 totals x 3 = 6,000.
# --------------------------------------------------------------------------- #
_SPLIT_GRID = list(itertools.product(range(-1000, 1000), range(1, 4)))


@pytest.mark.parametrize("total_cents,parts", _SPLIT_GRID)
def test_split_evenly_conserves_total(total_cents: int, parts: int) -> None:
    got = split_evenly(total_cents, parts)
    assert len(got) == parts
    assert sum(got) == total_cents
    # Every part but the last shares one floor value; no drift accumulates.
    if parts > 1:
        assert len(set(got[:-1])) == 1
        assert got[0] == total_cents // parts
    # Pure function: identical output on a second call.
    assert split_evenly(total_cents, parts) == got


# --------------------------------------------------------------------------- #
# Grid 2: allocate_by_ratio neither loses nor creates a cent when the weights
# sum to 10000 bps, however the remainder falls. 1,000 totals x 2 shapes = 2,000.
# --------------------------------------------------------------------------- #
_WEIGHT_SHAPES: tuple[tuple[int, ...], ...] = ((5000, 5000), (2500, 2500, 5000))
_ALLOC_GRID = list(itertools.product(range(0, 1000), _WEIGHT_SHAPES))


@pytest.mark.parametrize("total_cents,weights", _ALLOC_GRID)
def test_allocate_by_ratio_conserves_total(total_cents: int, weights: tuple[int, ...]) -> None:
    parts = allocate_by_ratio(total_cents, weights)
    assert len(parts) == len(weights)
    assert sum(parts) == total_cents
    # Deterministic largest-remainder placement.
    assert allocate_by_ratio(total_cents, weights) == parts


# --------------------------------------------------------------------------- #
# Grid 3: apply_rate is exact truncating integer math and never exceeds the base
# for a non-negative base at a rate of 0..95.00%. 100 bases x 20 rates = 2,000.
# --------------------------------------------------------------------------- #
_RATE_GRID = list(itertools.product(range(0, 100), range(0, 10000, 500)))


@pytest.mark.parametrize("base_cents,rate_bps", _RATE_GRID)
def test_apply_rate_is_exact_and_bounded(base_cents: int, rate_bps: int) -> None:
    got = apply_rate(base_cents, rate_bps)
    assert got == base_cents * rate_bps // 10000
    assert 0 <= got <= base_cents
