"""Curated invariant grid for the tax-surplus engine (1,500 cases).

A bounded, CI-gating slice of the SWEEP-gated ``test_bulk_invariant_grid.py``.
Every case runs the real ``run_waterfall`` and ``PoolBalances`` code and asserts
invariants that are mathematically certain over the integer input domain:

* the waterfall never draws more than the distribution or more than the pools
  hold, and every emitted step is strictly positive and correctly tagged;
* the exempt draw never exceeds the statutory exempt cap;
* ``PoolBalances`` field access via ``get`` mirrors the attributes and ``add``
  shifts a pool by exactly the given integer amount.
"""

import itertools

import pytest

from surplus_engine.model import (
    EXEMPT,
    PREACQ,
    TAXABLE,
    PoolBalances,
)
from surplus_engine.engine import (
    EXEMPT_CAP,
    run_waterfall,
)

# 30 distributions x 50 pool balances = 1,500.
_DIST = range(0, 30)
_POOL = range(0, 50)
_GRID = list(itertools.product(_DIST, _POOL))


@pytest.mark.parametrize("dist,pool", _GRID)
def test_waterfall_and_pool_invariants(dist: int, pool: int) -> None:
    opening = PoolBalances(
        exempt_surplus=pool,
        taxable_surplus=pool,
        pre_acquisition_capital=pool,
        acb=0,
    )
    steps, cap_amount, cap_binding = run_waterfall(dist, opening, EXEMPT_CAP)

    total_drawn = sum(s.amount for s in steps)
    # Never draw more than the distribution, nor more than the pools hold.
    assert total_drawn <= dist + 1e-9
    assert total_drawn <= 3 * pool + 1e-9
    # Every emitted step is strictly positive and tagged to a real pool.
    for s in steps:
        assert s.amount > 0
        assert s.pool in (EXEMPT, TAXABLE, PREACQ)
    # Exempt cap is the exact fraction of the distribution, and is respected.
    assert cap_amount == pytest.approx(round(dist * EXEMPT_CAP, 2))
    exempt_drawn = sum(s.amount for s in steps if s.pool == EXEMPT)
    assert exempt_drawn <= cap_amount + 1e-9
    assert cap_binding in (True, False)

    # PoolBalances get() mirrors attributes; add() shifts by an exact amount.
    # Use a fresh instance so the waterfall's draw-down cannot affect it.
    pb = PoolBalances(
        exempt_surplus=pool,
        taxable_surplus=pool,
        pre_acquisition_capital=pool,
        acb=0,
    )
    assert pb.get(EXEMPT) == pool
    assert pb.get(TAXABLE) == pool
    assert pb.get(PREACQ) == pool
    pb.add(EXEMPT, 7)
    assert pb.get(EXEMPT) == pool + 7
