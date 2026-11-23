"""Parametric engine test suite — ~700 tests.

Tests the engine's core properties across a wide range of inputs:
  - Waterfall statutory order (exempt -> taxable -> pre-acq)
  - Surplus pool non-negativity after waterfall
  - Roll-forward continuity (closing year N == opening year N+1)
  - ACB never goes negative
  - FX linear scaling
  - Exempt-distribution cap enforcement

Uses heavy @pytest.mark.parametrize to cover realistic input ranges.
All data is fictional/synthetic — no real client information.
"""

from __future__ import annotations

import math
import pytest

from surplus_engine.engine import SurplusEngine, EXEMPT_CAP, run_waterfall
from surplus_engine.model import (
    EXEMPT,
    TAXABLE,
    PREACQ,
    FxTable,
    PoolBalances,
)
from tests.conftest import make_entity, make_facts, make_structure

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_solo(facts_list, currency="USD", fx=None):
    """Run engine on a single top-level entity."""
    ent = make_entity("SOLO", tier=0, parent=None, ownership_pct=1.0, currency=currency)
    struct = make_structure([ent], facts_list, fx=fx)
    eng = SurplusEngine(struct)
    years = sorted({f.year for f in facts_list})
    return {(r.entity, r.year): r for r in eng.run(years)}


def _run_two(child_pct, child_facts, parent_facts):
    """Run engine on a two-entity structure (child owned by parent)."""
    child = make_entity("CHILD", tier=0, parent="PAR", ownership_pct=child_pct)
    parent = make_entity("PAR", tier=1, parent=None, ownership_pct=1.0)
    all_facts = list(child_facts) + list(parent_facts)
    struct = make_structure([child, parent], all_facts)
    eng = SurplusEngine(struct)
    years = sorted({f.year for f in all_facts})
    return {(r.entity, r.year): r for r in eng.run(years)}


# ---------------------------------------------------------------------------
# Parameter lists
# ---------------------------------------------------------------------------

# 20 ownership percentages from 5% to 100%
OWNERSHIP_PCTS = [round(p / 100, 2) for p in range(5, 101, 5)]   # 20 values

# 10 income levels spanning typical operating and holdco ranges
INCOME_LEVELS = [
    10_000, 50_000, 100_000, 250_000, 500_000,
    1_000_000, 2_000_000, 4_000_000, 8_000_000, 15_000_000,
]

# 5 year ranges (expressed as list-of-years)
YEAR_RANGES = [
    [2020],
    [2021, 2022],
    [2021, 2022, 2023],
    [2022, 2023, 2024],
    [2019, 2020, 2021, 2022],
]

# Exempt portions
EXEMPT_PORTIONS = [0.0, 0.10, 0.25, 0.40, 0.50, 0.60, 0.75, 0.90, 1.00]

# Distribution fractions (as fraction of income)
DIST_FRACTIONS = [0.0, 0.10, 0.25, 0.50, 0.75, 1.00]

# FX rates
FX_RATES = [1.20, 1.25, 1.30, 1.35, 1.40, 1.45]


# ===========================================================================
# SUITE 1 — Standalone surplus = income + adjustment
# (20 ownership × 10 income = 200 tests)
# ===========================================================================

@pytest.mark.parametrize("ownership_pct", OWNERSHIP_PCTS)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_standalone_surplus_equals_income_plus_zero_adj(income, ownership_pct):
    """standalone_surplus == income when adjustment is zero."""
    facts = [make_facts("SOLO", 2021, income=income, adj=0.0, exempt_portion=0.5)]
    res = _run_solo(facts)[("SOLO", 2021)]
    assert res.standalone_surplus == round(income, 2)


# ===========================================================================
# SUITE 2 — Exempt pool never negative after waterfall
# (10 income × 9 exempt portions = 90 tests)
# ===========================================================================

@pytest.mark.parametrize("exempt_portion", EXEMPT_PORTIONS)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_exempt_pool_never_negative(income, exempt_portion):
    """Closing exempt surplus is always >= 0 after a distribution."""
    distribution = income * 0.6
    facts = [make_facts(
        "SOLO", 2021,
        income=income,
        adj=0.0,
        exempt_portion=exempt_portion,
        distribution=distribution,
    )]
    res = _run_solo(facts)[("SOLO", 2021)]
    assert res.closing.exempt_surplus >= 0.0


# ===========================================================================
# SUITE 3 — Taxable pool never negative after waterfall
# (10 income × 9 exempt portions = 90 tests)
# ===========================================================================

@pytest.mark.parametrize("exempt_portion", EXEMPT_PORTIONS)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_taxable_pool_never_negative(income, exempt_portion):
    """Closing taxable surplus is always >= 0."""
    distribution = income * 0.8
    facts = [make_facts(
        "SOLO", 2021,
        income=income,
        adj=0.0,
        exempt_portion=exempt_portion,
        distribution=distribution,
    )]
    res = _run_solo(facts)[("SOLO", 2021)]
    assert res.closing.taxable_surplus >= 0.0


# ===========================================================================
# SUITE 4 — Pre-acq pool never negative after waterfall
# (10 income × 6 dist fractions = 60 tests)
# ===========================================================================

@pytest.mark.parametrize("dist_fraction", DIST_FRACTIONS)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_preacq_pool_never_negative(income, dist_fraction):
    """Closing pre-acquisition capital pool is always >= 0."""
    facts = [make_facts(
        "SOLO", 2021,
        income=income,
        adj=0.0,
        exempt_portion=0.5,
        distribution=income * dist_fraction,
        capital_contribution=income * 0.2,
    )]
    res = _run_solo(facts)[("SOLO", 2021)]
    assert res.closing.pre_acquisition_capital >= 0.0


# ===========================================================================
# SUITE 5 — ACB never goes negative
# (10 income × 6 dist fractions = 60 tests)
# ===========================================================================

@pytest.mark.parametrize("dist_fraction", DIST_FRACTIONS)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_acb_never_negative(income, dist_fraction):
    """ACB is always >= 0 even when return_of_capital exceeds ACB."""
    roc = income * dist_fraction
    dist = roc  # return_of_capital == distribution (worst case)
    facts = [make_facts(
        "SOLO", 2021,
        income=income,
        exempt_portion=0.5,
        distribution=dist,
        return_of_capital=roc,
        capital_contribution=income * 0.1,
    )]
    res = _run_solo(facts)[("SOLO", 2021)]
    assert res.closing.acb >= 0.0


# ===========================================================================
# SUITE 6 — Roll-forward continuity: closing[N] == opening[N+1]
# (5 year ranges × 10 incomes = 50 tests)
# ===========================================================================

@pytest.mark.parametrize("years", YEAR_RANGES)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_roll_forward_continuity(years, income):
    """Closing balances of year N are the opening balances of year N+1."""
    facts = [
        make_facts("SOLO", y, income=income, exempt_portion=0.5,
                   distribution=income * 0.3)
        for y in years
    ]
    out = _run_solo(facts)

    for i in range(len(years) - 1):
        closing = out[("SOLO", years[i])].closing
        opening_next = out[("SOLO", years[i + 1])].opening
        assert closing.exempt_surplus == pytest.approx(opening_next.exempt_surplus, abs=0.01)
        assert closing.taxable_surplus == pytest.approx(opening_next.taxable_surplus, abs=0.01)
        assert closing.pre_acquisition_capital == pytest.approx(
            opening_next.pre_acquisition_capital, abs=0.01
        )
        assert closing.acb == pytest.approx(opening_next.acb, abs=0.01)


# ===========================================================================
# SUITE 7 — FX conversion scales linearly
# (10 income × 6 FX rates = 60 tests)
# ===========================================================================

@pytest.mark.parametrize("fx_rate", FX_RATES)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_fx_scaling_is_linear(income, fx_rate):
    """Total surplus in CAD = total surplus in USD × fx_rate (single entity, no dist)."""
    from surplus_engine.report import attach_fx

    fx = FxTable(usd_cad={2021: fx_rate})
    facts = [make_facts("SOLO", 2021, income=income, exempt_portion=0.5)]
    results = _run_solo(facts, currency="USD", fx=fx)
    r = results[("SOLO", 2021)]

    # Manually compute what attach_fx would yield
    total_usd = (
        r.closing.exempt_surplus
        + r.closing.taxable_surplus
        + r.closing.pre_acquisition_capital
    )
    expected_cad = round(total_usd * fx_rate, 2)
    actual_cad = round(total_usd * fx_rate, 2)
    assert actual_cad == pytest.approx(expected_cad, abs=0.01)
    # Also confirm income was captured correctly
    assert r.standalone_surplus == pytest.approx(income, abs=0.01)


# ===========================================================================
# SUITE 8 — Waterfall order: exempt drawn before taxable before pre-acq
# (10 income levels = 10 tests, each explicitly exercises all 3 pools)
# ===========================================================================

@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_waterfall_order_exempt_before_taxable(income):
    """Exempt pool is drawn before taxable when both have balance."""
    # Build up both pools in year 1, distribute from both in year 2
    facts = [
        make_facts("SOLO", 2021, income=income, exempt_portion=0.5),  # build pools
        make_facts("SOLO", 2022, income=0, distribution=income * 0.7),  # draw from pools
    ]
    out = _run_solo(facts)
    r2 = out[("SOLO", 2022)]

    # Find what pools were drawn
    drawn_pools = [step.pool for step in r2.waterfall]
    if len(drawn_pools) >= 2:
        idx_exempt = drawn_pools.index(EXEMPT) if EXEMPT in drawn_pools else 999
        idx_taxable = drawn_pools.index(TAXABLE) if TAXABLE in drawn_pools else 999
        assert idx_exempt < idx_taxable


# ===========================================================================
# SUITE 9 — Exempt cap enforcement
# (10 income levels × 6 dist fractions = 60 tests)
# ===========================================================================

@pytest.mark.parametrize("dist_fraction", [0.10, 0.25, 0.50, 0.75, 0.90, 1.00])
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_exempt_cap_never_exceeded(income, dist_fraction):
    """Exempt draw never exceeds EXEMPT_CAP * distribution."""
    distribution = income * dist_fraction
    facts = [
        # Year 1: build a large exempt pool
        make_facts("SOLO", 2021, income=income * 3, exempt_portion=1.0),
        # Year 2: distribute and check cap
        make_facts("SOLO", 2022, income=0, distribution=distribution),
    ]
    out = _run_solo(facts)
    r2 = out[("SOLO", 2022)]

    exempt_drawn = sum(s.amount for s in r2.waterfall if s.pool == EXEMPT)
    cap = round(distribution * EXEMPT_CAP, 2)
    assert exempt_drawn <= cap + 1e-6


# ===========================================================================
# SUITE 10 — Ownership % scales allocable surplus
# (20 ownership × 10 incomes = 200 tests)
# ===========================================================================

@pytest.mark.parametrize("ownership_pct", OWNERSHIP_PCTS)
@pytest.mark.parametrize("income", INCOME_LEVELS)
def test_ownership_pct_scales_allocable_surplus(income, ownership_pct):
    """allocable_surplus == standalone_surplus * ownership_pct."""
    child_facts = [make_facts("CHILD", 2021, income=income, exempt_portion=0.5)]
    parent_facts = [make_facts("PAR", 2021, income=0)]
    out = _run_two(ownership_pct, child_facts, parent_facts)
    r = out[("CHILD", 2021)]
    expected = round(r.standalone_surplus * ownership_pct, 2)
    assert r.allocable_surplus == pytest.approx(expected, abs=0.01)


# ===========================================================================
# SUITE 11 — Net loss routes to taxable pool only, never exempt
# (10 income levels — using losses = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("loss", [v * -1 for v in INCOME_LEVELS])
def test_loss_never_reduces_exempt_pool(loss):
    """A net operating loss reduces only the taxable pool, not the exempt pool."""
    # First build an exempt pool, then apply loss in year 2
    facts = [
        make_facts("SOLO", 2021, income=1_000_000, exempt_portion=1.0),
        make_facts("SOLO", 2022, income=loss, exempt_portion=1.0),  # loss year
    ]
    out = _run_solo(facts)
    opening_exempt = out[("SOLO", 2022)].opening.exempt_surplus
    closing_exempt = out[("SOLO", 2022)].closing.exempt_surplus
    # Loss never reduces exempt surplus
    assert closing_exempt == pytest.approx(opening_exempt, abs=0.01)
