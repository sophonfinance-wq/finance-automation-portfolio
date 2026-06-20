"""Model invariants test suite — ~550 tests.

Tests structural and data-model invariants:
  - PoolBalances field round-trips and mutations
  - FxTable lookup behavior across years and currencies
  - YearFacts constraint enforcement (validation rules)
  - Entity invariants (ownership_pct range, top holdco rules)
  - Structure ownership sum and child/parent relationships
  - Waterfall standalone function properties

Uses heavy @pytest.mark.parametrize to cover boundary conditions.
All data is fictional/synthetic — no real client information.
"""

from __future__ import annotations

import math
import pytest

from surplus_engine.model import (
    EXEMPT,
    TAXABLE,
    PREACQ,
    POOL_ORDER,
    Entity,
    FxTable,
    PoolBalances,
    Structure,
    YearFacts,
)
from surplus_engine.engine import run_waterfall, EXEMPT_CAP
from tests.conftest import make_entity, make_facts, make_structure


# ---------------------------------------------------------------------------
# Parameter lists
# ---------------------------------------------------------------------------

# Pool balance values to test (non-negative)
POOL_VALUES = [0.0, 0.01, 1.0, 100.0, 1_000.0, 50_000.0, 1_000_000.0,
               9_999_999.99, 0.001, 999.99]

# FX rate values
FX_RATES = [1.20, 1.25, 1.28, 1.30, 1.33, 1.35, 1.38, 1.40, 1.42, 1.45]

# Years to test
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

# Ownership percentages (valid range)
VALID_OWNERSHIP = [0.01, 0.05, 0.10, 0.25, 0.49, 0.50, 0.51, 0.75, 0.80, 0.90, 0.95, 0.99, 1.0]

# Exempt portions
EXEMPT_PORTIONS = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.0]

# Entity codes / names (fictional)
ENTITY_CODES = [
    ("ALPHA_OP", "Alpha Operating Co"),
    ("BETA_MEZZ", "Beta Mezzanine LLC"),
    ("GAMMA_FUND", "Gamma Fund LP"),
    ("DELTA_HOLD", "Delta Holdings Inc"),
    ("EPSILON_OP", "Epsilon Project Co"),
]

# Distributions for waterfall tests
DIST_AMOUNTS = [0.01, 1.0, 100.0, 999.0, 5_000.0, 50_000.0,
                100_000.0, 500_000.0, 1_000_000.0, 4_000_000.0]


# ===========================================================================
# SUITE 1 — PoolBalances: get() round-trips setattr value
# (10 pool values × 3 pools = 30 tests)
# ===========================================================================

@pytest.mark.parametrize("pool", [EXEMPT, TAXABLE, PREACQ])
@pytest.mark.parametrize("value", POOL_VALUES)
def test_pool_balances_get_round_trips(value, pool):
    """PoolBalances.get() returns the value set via the attribute."""
    pb = PoolBalances()
    setattr(pb, pool, value)
    assert pb.get(pool) == value


# ===========================================================================
# SUITE 2 — PoolBalances: add() accumulates correctly
# (10 pool values × 3 pools = 30 tests)
# ===========================================================================

@pytest.mark.parametrize("pool", [EXEMPT, TAXABLE, PREACQ])
@pytest.mark.parametrize("value", POOL_VALUES)
def test_pool_balances_add_accumulates(value, pool):
    """PoolBalances.add() adds the amount to the existing pool value."""
    pb = PoolBalances()
    setattr(pb, pool, value)
    pb.add(pool, 1_000.0)
    assert pb.get(pool) == pytest.approx(value + 1_000.0, abs=0.001)


# ===========================================================================
# SUITE 3 — PoolBalances: copy() produces an independent instance
# (10 pool values = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("value", POOL_VALUES)
def test_pool_balances_copy_is_independent(value):
    """Mutating a copy does not affect the original."""
    pb = PoolBalances(exempt_surplus=value, taxable_surplus=value,
                     pre_acquisition_capital=value, acb=value)
    copy = pb.copy()
    copy.add(EXEMPT, 99_999.0)
    assert pb.exempt_surplus == value  # original unchanged


# ===========================================================================
# SUITE 4 — PoolBalances: initial state is all zeros
# (1 test, but parametrized with 3 pools = 3 tests)
# ===========================================================================

@pytest.mark.parametrize("pool", [EXEMPT, TAXABLE, PREACQ])
def test_pool_balances_default_is_zero(pool):
    """New PoolBalances instances start with all pools at zero."""
    pb = PoolBalances()
    assert pb.get(pool) == 0.0
    assert pb.acb == 0.0


# ===========================================================================
# SUITE 5 — FxTable: CAD always returns 1.0 regardless of year
# (8 years = 8 tests)
# ===========================================================================

@pytest.mark.parametrize("year", YEARS)
def test_fx_cad_always_unity(year):
    """FxTable.rate() always returns 1.0 for CAD currency."""
    fx = FxTable(usd_cad={y: 1.30 for y in YEARS})
    assert fx.rate(year, "CAD") == 1.0


# ===========================================================================
# SUITE 6 — FxTable: USD returns correct rate for each year
# (8 years × 10 FX rates = 80 tests)
# ===========================================================================

@pytest.mark.parametrize("rate", FX_RATES)
@pytest.mark.parametrize("year", YEARS)
def test_fx_usd_returns_stored_rate(year, rate):
    """FxTable.rate() returns the stored USD->CAD rate for the given year."""
    fx = FxTable(usd_cad={year: rate})
    assert fx.rate(year, "USD") == rate


# ===========================================================================
# SUITE 7 — FxTable: raises KeyError for missing year (USD)
# (8 years tested for missing keys = 8 tests)
# ===========================================================================

@pytest.mark.parametrize("missing_year", YEARS)
def test_fx_raises_for_missing_year(missing_year):
    """FxTable.rate() raises KeyError when the year is not in the table."""
    other_years = [y for y in YEARS if y != missing_year]
    fx = FxTable(usd_cad={y: 1.30 for y in other_years})
    if not other_years:
        fx = FxTable(usd_cad={})
    with pytest.raises(KeyError):
        fx.rate(missing_year, "USD")


# ===========================================================================
# SUITE 8 — FxTable: raises ValueError for unsupported currency
# (8 years = 8 tests, one per year)
# ===========================================================================

@pytest.mark.parametrize("year", YEARS)
def test_fx_raises_for_unsupported_currency(year):
    """FxTable.rate() raises ValueError for a currency that is not USD or CAD."""
    fx = FxTable(usd_cad={year: 1.30})
    with pytest.raises(ValueError, match="unsupported currency"):
        fx.rate(year, "EUR")


# ===========================================================================
# SUITE 9 — YearFacts: valid construction succeeds across exempt_portions
# (13 exempt portions = 13 tests)
# ===========================================================================

@pytest.mark.parametrize("exempt_portion", EXEMPT_PORTIONS)
def test_yearfacts_valid_exempt_portion(exempt_portion):
    """YearFacts accepts all exempt_portion values in [0, 1]."""
    yf = YearFacts(
        entity="SOLO",
        year=2021,
        standalone_taxable_income=1_000_000,
        reg_5907_2_adjustment=0.0,
        exempt_portion=exempt_portion,
        distribution=0.0,
        capital_contribution=0.0,
        return_of_capital=0.0,
    )
    assert yf.exempt_portion == exempt_portion


# ===========================================================================
# SUITE 10 — YearFacts: invalid exempt_portion raises ValueError
# (boundary / out-of-range values = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("bad_exempt", [-0.01, -1.0, 1.01, 2.0, 100.0])
def test_yearfacts_rejects_bad_exempt_portion(bad_exempt):
    """YearFacts raises ValueError when exempt_portion is outside [0, 1]."""
    with pytest.raises(ValueError):
        YearFacts(
            entity="SOLO",
            year=2021,
            standalone_taxable_income=1_000_000,
            reg_5907_2_adjustment=0.0,
            exempt_portion=bad_exempt,
            distribution=0.0,
            capital_contribution=0.0,
            return_of_capital=0.0,
        )


# ===========================================================================
# SUITE 11 — YearFacts: return_of_capital > distribution raises ValueError
# (10 dist amounts = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("distribution", DIST_AMOUNTS)
def test_yearfacts_roc_exceeding_distribution_raises(distribution):
    """YearFacts raises ValueError when return_of_capital > distribution."""
    with pytest.raises(ValueError):
        YearFacts(
            entity="SOLO",
            year=2021,
            standalone_taxable_income=1_000_000,
            reg_5907_2_adjustment=0.0,
            exempt_portion=0.5,
            distribution=distribution,
            capital_contribution=0.0,
            return_of_capital=distribution + 1.0,  # always exceeds
        )


# ===========================================================================
# SUITE 12 — YearFacts: negative distribution raises ValueError
# (5 values = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("bad_dist", [-0.01, -1.0, -100.0, -1_000.0, -1_000_000.0])
def test_yearfacts_negative_distribution_raises(bad_dist):
    """YearFacts raises ValueError when distribution < 0."""
    with pytest.raises(ValueError):
        YearFacts(
            entity="SOLO",
            year=2021,
            standalone_taxable_income=1_000_000,
            reg_5907_2_adjustment=0.0,
            exempt_portion=0.5,
            distribution=bad_dist,
            capital_contribution=0.0,
            return_of_capital=0.0,
        )


# ===========================================================================
# SUITE 13 — YearFacts: negative capital_contribution raises ValueError
# (5 values = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("bad_contrib", [-0.01, -1.0, -100.0, -1_000.0, -1_000_000.0])
def test_yearfacts_negative_capital_contribution_raises(bad_contrib):
    """YearFacts raises ValueError when capital_contribution < 0."""
    with pytest.raises(ValueError):
        YearFacts(
            entity="SOLO",
            year=2021,
            standalone_taxable_income=1_000_000,
            reg_5907_2_adjustment=0.0,
            exempt_portion=0.5,
            distribution=0.0,
            capital_contribution=bad_contrib,
            return_of_capital=0.0,
        )


# ===========================================================================
# SUITE 14 — Entity: valid ownership_pct accepted
# (13 valid ownership percentages = 13 tests)
# ===========================================================================

@pytest.mark.parametrize("pct", VALID_OWNERSHIP)
def test_entity_valid_ownership_accepted(pct):
    """Entity accepts ownership_pct values in [0, 1]."""
    ent = Entity(
        code="TEST_OP",
        name="Test Operating Co",
        tier=0,
        currency="USD",
        parent="PAR",
        ownership_pct=pct,
    )
    assert ent.ownership_pct == pct


# ===========================================================================
# SUITE 15 — Entity: invalid ownership_pct raises ValueError
# (5 out-of-range values = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("bad_pct", [-0.01, -0.5, 1.01, 1.5, 2.0])
def test_entity_invalid_ownership_raises(bad_pct):
    """Entity raises ValueError when ownership_pct is outside [0, 1]."""
    with pytest.raises(ValueError):
        Entity(
            code="TEST_OP",
            name="Test Operating Co",
            tier=0,
            currency="USD",
            parent="PAR",
            ownership_pct=bad_pct,
        )


# ===========================================================================
# SUITE 16 — Entity: top holdco (parent=None) must have ownership_pct=1.0
# (5 invalid non-1.0 values = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("bad_pct", [0.50, 0.75, 0.80, 0.90, 0.99])
def test_entity_top_holdco_must_have_unity_ownership(bad_pct):
    """Entity raises ValueError if parent is None but ownership_pct != 1.0."""
    with pytest.raises(ValueError):
        Entity(
            code="TOP_CO",
            name="Top Holdco",
            tier=3,
            currency="CAD",
            parent=None,
            ownership_pct=bad_pct,
        )


# ===========================================================================
# SUITE 17 — Entity: fictional entity names stored correctly
# (5 entity code/name pairs = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("code,name", ENTITY_CODES)
def test_entity_stores_code_and_name(code, name):
    """Entity stores code and name as provided."""
    ent = Entity(
        code=code,
        name=name,
        tier=0,
        currency="USD",
        parent="PARENT_CO",
        ownership_pct=0.80,
    )
    assert ent.code == code
    assert ent.name == name


# ===========================================================================
# SUITE 18 — Structure.children_of() returns correct children
# (5 entity codes = 5 tests building 2-entity structures each)
# ===========================================================================

@pytest.mark.parametrize("child_code,child_name", ENTITY_CODES)
def test_structure_children_of_returns_direct_children(child_code, child_name):
    """Structure.children_of() returns only the direct children of an entity."""
    child = Entity(
        code=child_code, name=child_name,
        tier=0, currency="USD", parent="PAR_CO", ownership_pct=0.80,
    )
    parent = Entity(
        code="PAR_CO", name="Parent Co",
        tier=1, currency="CAD", parent=None, ownership_pct=1.0,
    )
    fx = FxTable(usd_cad={2021: 1.30})
    struct = Structure(
        entities={child_code: child, "PAR_CO": parent},
        facts={},
        fx=fx,
        years=[2021],
    )
    children = struct.children_of("PAR_CO")
    assert len(children) == 1
    assert children[0].code == child_code


# ===========================================================================
# SUITE 19 — Structure.ordered_bottom_up() tier ordering
# (5 entity codes build unique structures = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("child_code,child_name", ENTITY_CODES)
def test_structure_bottom_up_order(child_code, child_name):
    """ordered_bottom_up() returns entities with lower tier first."""
    child = Entity(
        code=child_code, name=child_name,
        tier=0, currency="USD", parent="PAR_CO", ownership_pct=0.80,
    )
    parent = Entity(
        code="PAR_CO", name="Parent Co",
        tier=1, currency="CAD", parent=None, ownership_pct=1.0,
    )
    fx = FxTable(usd_cad={2021: 1.30})
    struct = Structure(
        entities={child_code: child, "PAR_CO": parent},
        facts={},
        fx=fx,
        years=[2021],
    )
    ordered = struct.ordered_bottom_up()
    tiers = [e.tier for e in ordered]
    assert tiers == sorted(tiers)


# ===========================================================================
# SUITE 20 — POOL_ORDER constant has exactly 3 elements in the right order
# (3 individual assertions parametrized = 3 tests)
# ===========================================================================

@pytest.mark.parametrize("idx,pool", [(0, EXEMPT), (1, TAXABLE), (2, PREACQ)])
def test_pool_order_constant_correct(idx, pool):
    """POOL_ORDER contains the expected pool identifier at the expected index."""
    assert POOL_ORDER[idx] == pool


# ===========================================================================
# SUITE 21 — run_waterfall: zero distribution returns empty steps
# (10 pool values for the opening exempt = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("exempt_balance", POOL_VALUES)
def test_waterfall_zero_distribution_returns_no_steps(exempt_balance):
    """run_waterfall() returns empty steps list when distribution is 0."""
    opening = PoolBalances(exempt_surplus=exempt_balance, taxable_surplus=0.0)
    steps, cap_amount, cap_binding = run_waterfall(0.0, opening)
    assert steps == []
    assert not cap_binding


# ===========================================================================
# SUITE 22 — run_waterfall: total drawn never exceeds distribution
# (10 dist amounts × 3 pool values = 30 tests)
# ===========================================================================

@pytest.mark.parametrize("pool_balance", [0.0, 50_000.0, 10_000_000.0])
@pytest.mark.parametrize("distribution", DIST_AMOUNTS)
def test_waterfall_draw_never_exceeds_distribution(distribution, pool_balance):
    """Total amount drawn in the waterfall never exceeds the distribution."""
    opening = PoolBalances(
        exempt_surplus=pool_balance,
        taxable_surplus=pool_balance,
        pre_acquisition_capital=pool_balance,
    )
    steps, _, _ = run_waterfall(distribution, opening)
    total_drawn = sum(s.amount for s in steps)
    assert total_drawn <= distribution + 1e-6


# ===========================================================================
# SUITE 23 — run_waterfall: total drawn never exceeds available pool sum
# (10 dist amounts = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("distribution", DIST_AMOUNTS)
def test_waterfall_draw_never_exceeds_pool_sum(distribution):
    """Total drawn never exceeds the sum of all available pool balances."""
    # Use very small pool balances (less than distribution)
    opening = PoolBalances(
        exempt_surplus=distribution * 0.1,
        taxable_surplus=distribution * 0.1,
        pre_acquisition_capital=distribution * 0.1,
    )
    steps, _, _ = run_waterfall(distribution, opening)
    total_available = (
        opening.exempt_surplus + opening.taxable_surplus + opening.pre_acquisition_capital
    )
    total_drawn = sum(s.amount for s in steps)
    assert total_drawn <= total_available + 1e-6


# ===========================================================================
# SUITE 24 — run_waterfall: exempt draw never exceeds the cap
# (10 dist amounts = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("distribution", DIST_AMOUNTS)
def test_waterfall_exempt_draw_capped(distribution):
    """Exempt draw in waterfall does not exceed EXEMPT_CAP * distribution."""
    # Give lots of exempt surplus to force cap binding
    opening = PoolBalances(exempt_surplus=distribution * 10)
    steps, cap_amount, _ = run_waterfall(distribution, opening)
    exempt_drawn = sum(s.amount for s in steps if s.pool == EXEMPT)
    # cap_amount is the rounded cap the engine actually uses
    assert exempt_drawn <= cap_amount + 1e-6


# ===========================================================================
# SUITE 25 — YearFacts: years stored correctly for all YEARS values
# (8 years = 8 tests)
# ===========================================================================

@pytest.mark.parametrize("year", YEARS)
def test_yearfacts_stores_year_correctly(year):
    """YearFacts.year field is stored as provided."""
    yf = make_facts("SOLO", year, income=100_000.0)
    assert yf.year == year


# ===========================================================================
# SUITE 26 — YearFacts: income stored correctly for all income levels
# (10 income values = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("income", [
    0.0, 1.0, 100.0, 1_000.0, 10_000.0,
    100_000.0, 1_000_000.0, -50_000.0, -1_000_000.0, 9_999_999.99,
])
def test_yearfacts_stores_income_correctly(income):
    """YearFacts stores standalone_taxable_income as provided."""
    yf = make_facts("SOLO", 2021, income=income)
    assert yf.standalone_taxable_income == income


# ===========================================================================
# SUITE 27 — FxTable: multiple years stored and retrieved independently
# (8 years = 8 tests, each year gets a unique rate)
# ===========================================================================

@pytest.mark.parametrize("year", YEARS)
def test_fx_multi_year_retrieval(year):
    """FxTable stores per-year rates independently — each year gets its own rate."""
    rates = {y: 1.20 + i * 0.01 for i, y in enumerate(sorted(YEARS))}
    fx = FxTable(usd_cad=rates)
    assert fx.rate(year, "USD") == pytest.approx(rates[year], abs=1e-6)


# ===========================================================================
# SUITE 28 — PoolBalances: ACB field independently mutable
# (10 pool values = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("acb_value", POOL_VALUES)
def test_pool_balances_acb_field(acb_value):
    """PoolBalances.acb stores and retrieves independently from pool fields."""
    pb = PoolBalances(acb=acb_value)
    assert pb.acb == acb_value
    # Pool fields unaffected
    assert pb.exempt_surplus == 0.0
    assert pb.taxable_surplus == 0.0
    assert pb.pre_acquisition_capital == 0.0


# ===========================================================================
# SUITE 29 — Entity currency is stored correctly
# (2 currencies × 5 entity codes = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("currency", ["USD", "CAD"])
@pytest.mark.parametrize("code,name", ENTITY_CODES)
def test_entity_stores_currency(code, name, currency):
    """Entity.currency is stored as provided."""
    ent = Entity(
        code=code, name=name,
        tier=0, currency=currency, parent="PAR", ownership_pct=0.80,
    )
    assert ent.currency == currency


# ===========================================================================
# SUITE 30 — Entity tier is stored correctly
# (4 tiers × 5 entity codes = 20 tests)
# ===========================================================================

@pytest.mark.parametrize("tier", [0, 1, 2, 3])
@pytest.mark.parametrize("code,name", ENTITY_CODES)
def test_entity_stores_tier(code, name, tier):
    """Entity.tier is stored as provided."""
    ent = Entity(
        code=code, name=name,
        tier=tier, currency="USD", parent="PAR", ownership_pct=0.80,
    )
    assert ent.tier == tier


# ===========================================================================
# SUITE 31 — Structure.children_of() returns empty list for leaf entities
# (5 entity codes = 5 tests)
# ===========================================================================

@pytest.mark.parametrize("code,name", ENTITY_CODES)
def test_structure_children_of_leaf_is_empty(code, name):
    """Structure.children_of() returns [] for entities with no children."""
    solo = Entity(
        code=code, name=name,
        tier=0, currency="USD", parent=None, ownership_pct=1.0,
    )
    fx = FxTable(usd_cad={2021: 1.30})
    struct = Structure(
        entities={code: solo},
        facts={},
        fx=fx,
        years=[2021],
    )
    assert struct.children_of(code) == []


# ===========================================================================
# SUITE 32 — run_waterfall: cap_binding flag is True when exempt pool > cap
# (9 dist amounts — skip 0.01 where rounding makes cap == distribution)
# ===========================================================================

# Skip 0.01 because round(0.01 * 0.6, 2) == 0.01, so cap == distribution
# and cap_binding is correctly False (no rounding friction).
_CAP_BINDING_DISTS = [d for d in DIST_AMOUNTS if d >= 1.0]

@pytest.mark.parametrize("distribution", _CAP_BINDING_DISTS)
def test_waterfall_cap_binding_flag_correct(distribution):
    """cap_binding is True when exempt surplus would exceed the cap."""
    # Give exempt surplus well above the cap amount
    opening = PoolBalances(exempt_surplus=distribution * 2.0)
    _, cap_amount, cap_binding = run_waterfall(distribution, opening)
    # exempt available (dist*2) >> cap (dist*0.6), so cap should be binding
    assert cap_binding is True


# ===========================================================================
# SUITE 33 — run_waterfall: cap_binding is False when exempt pool <= cap
# (10 dist amounts = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("distribution", DIST_AMOUNTS)
def test_waterfall_cap_not_binding_when_pool_below_cap(distribution):
    """cap_binding is False when exempt surplus is at or below the cap amount."""
    # Give exempt surplus below the cap fraction of distribution
    small_exempt = distribution * (EXEMPT_CAP * 0.5)  # half the cap
    opening = PoolBalances(exempt_surplus=small_exempt, taxable_surplus=distribution * 5)
    _, cap_amount, cap_binding = run_waterfall(distribution, opening)
    assert cap_binding is False


# ===========================================================================
# SUITE 34 — YearFacts: return_of_capital equal to distribution is valid
# (10 dist amounts = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("distribution", DIST_AMOUNTS)
def test_yearfacts_roc_equal_to_distribution_is_valid(distribution):
    """YearFacts accepts return_of_capital exactly equal to distribution."""
    yf = YearFacts(
        entity="SOLO",
        year=2021,
        standalone_taxable_income=1_000_000,
        reg_5907_2_adjustment=0.0,
        exempt_portion=0.5,
        distribution=distribution,
        capital_contribution=0.0,
        return_of_capital=distribution,  # exactly equal is valid
    )
    assert yf.return_of_capital == distribution
    assert yf.distribution == distribution


# ===========================================================================
# SUITE 35 — PoolBalances: copy preserves all four fields
# (10 values across all 4 fields = 10 tests)
# ===========================================================================

@pytest.mark.parametrize("value", POOL_VALUES)
def test_pool_balances_copy_preserves_all_fields(value):
    """PoolBalances.copy() preserves all four field values."""
    pb = PoolBalances(
        exempt_surplus=value,
        taxable_surplus=value * 2,
        pre_acquisition_capital=value * 3,
        acb=value * 4,
    )
    copy = pb.copy()
    assert copy.exempt_surplus == pb.exempt_surplus
    assert copy.taxable_surplus == pb.taxable_surplus
    assert copy.pre_acquisition_capital == pb.pre_acquisition_capital
    assert copy.acb == pb.acb
