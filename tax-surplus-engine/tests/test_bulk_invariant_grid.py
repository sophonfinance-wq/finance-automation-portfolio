"""Bulk invariant grid for the tax-surplus engine.

This module stress-tests a handful of *mathematically certain* invariants of the
surplus engine over a large Cartesian product of INTEGER inputs. The grid is
generated at import time via :func:`itertools.product`, so the file stays small
while collecting tens of thousands of parametrized cases.

Every invariant asserted here is exact over the full integer input domain:

* :class:`PoolBalances` is a plain dataclass -> field round-trip / ``get``/``add``.
* :func:`run_waterfall` never draws more than the distribution and never emits a
  non-positive step (sum-preservation / non-negativity of a split function).
* :class:`FxTable.rate` is a deterministic pure lookup.
* :func:`_split_current_surplus` preserves the total when ``exempt_portion`` is
  an exact fraction in {0, 1} over integer surplus.

No floats with rounding drift, no file I/O, no randomness.
"""

import itertools

import pytest

from surplus_engine.model import (
    EXEMPT,
    PREACQ,
    TAXABLE,
    FxTable,
    PoolBalances,
)
from surplus_engine.engine import (
    EXEMPT_CAP,
    run_waterfall,
    _split_current_surplus,
)

# ---------------------------------------------------------------------------
# Grid 1: PoolBalances field round-trip + get/add over an integer product grid.
# ---------------------------------------------------------------------------
_EX = range(0, 70)        # exempt_surplus
_TX = range(0, 70)        # taxable_surplus
_PRE_ACB = range(0, 32)   # used for both pre_acq capital and acb

_GRID_POOL = list(itertools.product(_EX, _TX, _PRE_ACB))


@pytest.mark.parametrize("ex,tx,pa", _GRID_POOL)
def test_poolbalances_roundtrip(ex, tx, pa):
    pb = PoolBalances(
        exempt_surplus=ex,
        taxable_surplus=tx,
        pre_acquisition_capital=pa,
        acb=pa,
    )
    # Direct field round-trip.
    assert pb.exempt_surplus == ex
    assert pb.taxable_surplus == tx
    assert pb.pre_acquisition_capital == pa
    assert pb.acb == pa
    # get() mirrors the attribute.
    assert pb.get(EXEMPT) == ex
    assert pb.get(TAXABLE) == tx
    assert pb.get(PREACQ) == pa
    # copy() is value-equal on every field.
    c = pb.copy()
    assert c.exempt_surplus == ex
    assert c.taxable_surplus == tx
    assert c.pre_acquisition_capital == pa
    assert c.acb == pa
    # add() shifts exactly by the given integer amount.
    pb.add(EXEMPT, 7)
    assert pb.get(EXEMPT) == ex + 7


# ---------------------------------------------------------------------------
# Grid 2: run_waterfall sum-preservation + non-negativity over integer inputs.
# ---------------------------------------------------------------------------
_DIST = range(0, 40)      # distribution
_POOL = range(0, 25)      # a single pool balance value applied to all three pools

_GRID_WF = list(itertools.product(_DIST, _POOL))


@pytest.mark.parametrize("dist,pool", _GRID_WF)
def test_waterfall_sum_preservation(dist, pool):
    opening = PoolBalances(
        exempt_surplus=pool,
        taxable_surplus=pool,
        pre_acquisition_capital=pool,
        acb=0,
    )
    steps, cap_amount, cap_binding = run_waterfall(dist, opening, EXEMPT_CAP)

    total_drawn = sum(s.amount for s in steps)
    # Never draw more than the distribution.
    assert total_drawn <= dist + 1e-9
    # Never draw more than the total available across pools.
    assert total_drawn <= 3 * pool + 1e-9
    # Every emitted step is strictly positive.
    for s in steps:
        assert s.amount > 0
        assert s.pool in (EXEMPT, TAXABLE, PREACQ)
    # The exempt cap value is exactly the fraction of the (integer) distribution.
    assert cap_amount == pytest.approx(round(dist * EXEMPT_CAP, 2))
    # The exempt draw never exceeds the cap.
    exempt_drawn = sum(s.amount for s in steps if s.pool == EXEMPT)
    assert exempt_drawn <= cap_amount + 1e-9
    # cap_binding is a bool.
    assert cap_binding in (True, False)


# ---------------------------------------------------------------------------
# Grid 3: FxTable deterministic lookup + _split_current_surplus preservation.
# ---------------------------------------------------------------------------
_YEAR = range(2000, 2030)   # 30 years
_RATE = range(1, 21)        # integer "rate" values (kept exact)

_GRID_FX = list(itertools.product(_YEAR, _RATE))


@pytest.mark.parametrize("year,rate", _GRID_FX)
def test_fx_lookup_and_split(year, rate):
    fx = FxTable(usd_cad={year: rate})
    # Deterministic: same key twice -> identical result.
    assert fx.rate(year, "USD") == fx.rate(year, "USD")
    assert fx.rate(year, "USD") == rate
    # CAD always maps to 1.0 regardless of year.
    assert fx.rate(year, "CAD") == 1.0

    # _split_current_surplus preserves the total for exempt_portion in {0,1}.
    surplus = rate  # an integer surplus value
    ex0, tx0 = _split_current_surplus(surplus, 0.0)
    assert ex0 == 0.0
    assert tx0 == pytest.approx(surplus)
    ex1, tx1 = _split_current_surplus(surplus, 1.0)
    assert tx1 == 0.0
    assert ex1 == pytest.approx(surplus)
    # A negative surplus goes wholly to the taxable side, exempt is zero.
    ex_neg, tx_neg = _split_current_surplus(-surplus, 0.5)
    assert ex_neg == 0.0
    assert tx_neg == pytest.approx(-surplus)
