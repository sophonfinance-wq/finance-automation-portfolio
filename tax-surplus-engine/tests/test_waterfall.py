"""Waterfall ordering and exempt-cap enforcement."""

from __future__ import annotations

from surplus_engine.engine import EXEMPT_CAP, run_waterfall
from surplus_engine.model import EXEMPT, PREACQ, TAXABLE, PoolBalances


def test_waterfall_consumes_in_statutory_order():
    # Plenty in every pool; distribution small enough to be fully exempt-funded
    # if the cap allowed. Use a high cap so ordering (not cap) is exercised.
    opening = PoolBalances(exempt_surplus=1000, taxable_surplus=1000, pre_acquisition_capital=1000)
    steps, _, _ = run_waterfall(500, opening, exempt_cap_fraction=1.0)
    assert [s.pool for s in steps] == [EXEMPT]
    assert steps[0].amount == 500


def test_waterfall_spills_exempt_then_taxable_then_preacq():
    opening = PoolBalances(exempt_surplus=100, taxable_surplus=100, pre_acquisition_capital=100)
    # cap fraction 1.0 so exempt isn't the constraint; total 250 forces spill.
    steps, _, _ = run_waterfall(250, opening, exempt_cap_fraction=1.0)
    assert [s.pool for s in steps] == [EXEMPT, TAXABLE, PREACQ]
    assert steps[0].amount == 100   # exempt fully drawn
    assert steps[1].amount == 100   # taxable fully drawn
    assert steps[2].amount == 50    # remainder from pre-acq


def test_waterfall_never_overdraws_a_pool():
    opening = PoolBalances(exempt_surplus=30, taxable_surplus=20, pre_acquisition_capital=10)
    steps, _, _ = run_waterfall(1000, opening, exempt_cap_fraction=1.0)
    drawn = {s.pool: s.amount for s in steps}
    assert drawn[EXEMPT] == 30
    assert drawn[TAXABLE] == 20
    assert drawn[PREACQ] == 10
    # Total drawn cannot exceed what was available (60), even though 1000 asked.
    assert sum(s.amount for s in steps) == 60


def test_exempt_cap_limits_exempt_draw():
    # Lots of exempt surplus, but cap at 60% means at most 60 of a 100 dist
    # comes from exempt; the rest spills to taxable.
    opening = PoolBalances(exempt_surplus=1000, taxable_surplus=1000, pre_acquisition_capital=0)
    steps, cap_amount, binding = run_waterfall(100, opening, exempt_cap_fraction=0.60)
    drawn = {s.pool: s.amount for s in steps}
    assert cap_amount == 60.0
    assert binding is True
    assert drawn[EXEMPT] == 60.0
    assert drawn[TAXABLE] == 40.0


def test_exempt_cap_not_binding_when_exempt_balance_is_low():
    # Only 20 of exempt available, cap would allow 60 -> cap is NOT the binding
    # constraint; exempt draw limited by balance, not cap.
    opening = PoolBalances(exempt_surplus=20, taxable_surplus=1000, pre_acquisition_capital=0)
    steps, cap_amount, binding = run_waterfall(100, opening, exempt_cap_fraction=0.60)
    drawn = {s.pool: s.amount for s in steps}
    assert cap_amount == 60.0
    assert binding is False
    assert drawn[EXEMPT] == 20.0
    assert drawn[TAXABLE] == 80.0


def test_default_exempt_cap_value():
    assert EXEMPT_CAP == 0.60


def test_zero_distribution_produces_no_steps():
    opening = PoolBalances(exempt_surplus=100)
    steps, _, binding = run_waterfall(0, opening)
    assert steps == []
    assert binding is False
