"""Per-entity-year engine behaviour (``surplus_engine.engine.SurplusEngine``).

Exercises the statutory mechanics on small, hand-built structures: capital
contributions touching both the pre-acq pool and ACB, the exempt-cap binding
flag propagating onto the result, multi-year deemed-gain timing, processing
order (bottom-up within a year, top-down in the returned list), quiet-year
fallback facts, and the custom exempt-cap fraction passed to the engine.
"""

from __future__ import annotations

import pytest

from surplus_engine.engine import EXEMPT_CAP, SurplusEngine
from surplus_engine.model import EXEMPT, PREACQ, TAXABLE
from tests.conftest import make_entity, make_facts, make_structure


def _run(structure, years, **kw):
    eng = SurplusEngine(structure, **kw)
    return {(r.entity, r.year): r for r in eng.run(years)}


# --------------------------------------------------------------------------- #
# Capital events
# --------------------------------------------------------------------------- #
def test_capital_contribution_raises_both_preacq_and_acb(single_entity_factory):
    facts = [make_facts("SOLO", 2021, income=0, capital_contribution=500_000)]
    struct = single_entity_factory(facts)
    r = _run(struct, [2021])[("SOLO", 2021)]
    assert r.closing.pre_acquisition_capital == 500_000
    assert r.closing.acb == 500_000


def test_capital_contribution_funds_preacq_used_by_waterfall(single_entity_factory):
    # No surplus, but a contribution seeds pre-acq capital; a distribution then
    # spills all the way to the pre-acq pool.
    facts = [
        make_facts("SOLO", 2021, income=0, capital_contribution=100_000,
                   distribution=40_000),
    ]
    struct = single_entity_factory(facts)
    r = _run(struct, [2021])[("SOLO", 2021)]
    drawn = {s.pool: s.amount for s in r.waterfall}
    assert drawn == {PREACQ: 40_000}
    assert r.closing.pre_acquisition_capital == 60_000


def test_return_of_capital_without_prior_acb_is_all_deemed_gain(single_entity_factory):
    # No contribution -> ACB is 0; the entire return of capital is a deemed gain.
    facts = [make_facts("SOLO", 2021, income=0, distribution=70_000,
                        return_of_capital=70_000)]
    struct = single_entity_factory(facts)
    r = _run(struct, [2021])[("SOLO", 2021)]
    assert r.closing.acb == 0.0
    assert r.deemed_gain_on_negative_acb == 70_000


def test_partial_return_of_capital_reduces_acb_without_deemed_gain(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, income=0, capital_contribution=200_000),
        make_facts("SOLO", 2022, income=0, distribution=50_000,
                   return_of_capital=50_000),
    ]
    out = _run(single_entity_factory(facts), [2021, 2022])
    assert out[("SOLO", 2022)].closing.acb == 150_000
    assert out[("SOLO", 2022)].deemed_gain_on_negative_acb == 0.0


# --------------------------------------------------------------------------- #
# Exempt-cap propagation onto the result record
# --------------------------------------------------------------------------- #
def test_exempt_cap_binding_flag_set_on_result(single_entity_factory):
    # Large exempt pool, default cap -> the cap binds and the flag is recorded.
    facts = [make_facts("SOLO", 2021, income=1_000_000, exempt_portion=1.0,
                        distribution=100_000)]
    struct = single_entity_factory(facts)
    r = _run(struct, [2021])[("SOLO", 2021)]
    assert r.exempt_cap_binding is True
    assert r.exempt_cap_amount == 60_000  # 60% of 100k


def test_exempt_cap_not_binding_when_exempt_balance_below_cap(single_entity_factory):
    # Exempt pool (1k) is smaller than the cap (6k of a 10k dist), so the cap is
    # NOT the binding constraint; the low exempt balance is. Remainder spills to
    # the funded taxable pool.
    facts = [make_facts("SOLO", 2021, income=10_000, exempt_portion=0.1,
                        distribution=10_000)]
    struct = single_entity_factory(facts)
    r = _run(struct, [2021])[("SOLO", 2021)]
    drawn = {s.pool: s.amount for s in r.waterfall}
    assert drawn[EXEMPT] == 1_000      # whole (small) exempt pool, < 6k cap
    assert drawn[TAXABLE] == 9_000
    assert r.exempt_cap_binding is False


def test_custom_exempt_cap_fraction_is_honoured(single_entity_factory):
    # exempt_portion 0.6 funds both pools so the cap-limited remainder can spill.
    facts = [make_facts("SOLO", 2021, income=1_000_000, exempt_portion=0.6,
                        distribution=100_000)]
    struct = single_entity_factory(facts)
    r = _run(struct, [2021], exempt_cap_fraction=0.25)[("SOLO", 2021)]
    drawn = {s.pool: s.amount for s in r.waterfall}
    assert r.exempt_cap_amount == 25_000
    assert drawn[EXEMPT] == 25_000
    assert drawn[TAXABLE] == 75_000


def test_default_engine_uses_module_exempt_cap(single_entity_factory):
    facts = [make_facts("SOLO", 2021, income=1_000_000, exempt_portion=1.0,
                        distribution=100_000)]
    eng = SurplusEngine(single_entity_factory(facts))
    assert eng.exempt_cap_fraction == EXEMPT_CAP


# --------------------------------------------------------------------------- #
# Standalone surplus & allocable surplus
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "income,adj,expected",
    [
        (1_000_000, -50_000, 950_000),
        (1_000_000, 50_000, 1_050_000),
        (0, 0, 0.0),
        (-200_000, 100_000, -100_000),
    ],
)
def test_standalone_surplus_is_income_plus_adjustment(single_entity_factory, income, adj, expected):
    facts = [make_facts("SOLO", 2021, income=income, adj=adj, exempt_portion=1.0)]
    r = _run(single_entity_factory(facts), [2021])[("SOLO", 2021)]
    assert r.standalone_surplus == expected


@pytest.mark.parametrize("pct", [1.0, 0.9, 0.75, 0.5, 0.0])
def test_allocable_surplus_scales_by_ownership(pct):
    child = make_entity("CHILD", tier=0, parent="TOP", ownership_pct=pct)
    top = make_entity("TOP", tier=1, parent=None, ownership_pct=1.0)
    facts = [make_facts("CHILD", 2021, income=1_000_000, exempt_portion=1.0),
             make_facts("TOP", 2021, income=0)]
    out = _run(make_structure([child, top], facts), [2021])
    assert out[("CHILD", 2021)].allocable_surplus == pytest.approx(1_000_000 * pct)


# --------------------------------------------------------------------------- #
# Quiet-year fallback facts
# --------------------------------------------------------------------------- #
def test_year_without_facts_is_quiet(single_entity_factory):
    # Provide facts only for 2021; run 2021..2022. 2022 must be a no-op year.
    facts = [make_facts("SOLO", 2021, income=1_000_000, exempt_portion=1.0)]
    out = _run(single_entity_factory(facts), [2021, 2022])
    q = out[("SOLO", 2022)]
    assert q.standalone_surplus == 0.0
    assert q.distribution == 0.0
    assert q.waterfall == []
    # Surplus simply rolls forward unchanged.
    assert q.closing.exempt_surplus == 1_000_000


# --------------------------------------------------------------------------- #
# Processing / ordering
# --------------------------------------------------------------------------- #
def test_results_returned_top_down_by_tier():
    op = make_entity("OP", tier=0, parent="MEZZ", ownership_pct=1.0)
    mezz = make_entity("MEZZ", tier=1, parent="TOP", ownership_pct=1.0)
    top = make_entity("TOP", tier=2, parent=None, ownership_pct=1.0)
    facts = [make_facts("OP", 2021, income=100), make_facts("TOP", 2021, income=0)]
    struct = make_structure([op, mezz, top], facts, years=[2021])
    results = SurplusEngine(struct).run([2021])
    assert [r.entity for r in results] == ["TOP", "MEZZ", "OP"]


def test_run_processes_years_in_ascending_order(single_entity_factory):
    # Passing years out of order must still roll forward chronologically.
    facts = [
        make_facts("SOLO", 2021, income=0, capital_contribution=100_000),
        make_facts("SOLO", 2022, income=0, capital_contribution=50_000),
    ]
    out = _run(single_entity_factory(facts), [2022, 2021])
    # 2022 ACB must include 2021's contribution (roll-forward), proving order.
    assert out[("SOLO", 2021)].closing.acb == 100_000
    assert out[("SOLO", 2022)].closing.acb == 150_000


def test_distribution_without_pools_yields_no_draws(single_entity_factory):
    # Income is a loss, so no surplus; a positive distribution cannot draw.
    facts = [make_facts("SOLO", 2021, income=-100_000, exempt_portion=1.0,
                        distribution=10_000)]
    r = _run(single_entity_factory(facts), [2021])[("SOLO", 2021)]
    assert r.waterfall == []
    assert r.closing.taxable_surplus == 0.0


# --------------------------------------------------------------------------- #
# Loss roll-forward against prior taxable surplus
# --------------------------------------------------------------------------- #
def test_prior_taxable_surplus_absorbs_later_loss(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, income=1_000_000, exempt_portion=0.0),  # all taxable
        make_facts("SOLO", 2022, income=-300_000, exempt_portion=0.0),   # loss
    ]
    out = _run(single_entity_factory(facts), [2021, 2022])
    assert out[("SOLO", 2021)].closing.taxable_surplus == 1_000_000
    # Loss reduces the carried taxable pool but stays non-negative.
    assert out[("SOLO", 2022)].closing.taxable_surplus == 700_000


def test_loss_larger_than_pool_floors_at_zero(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, income=100_000, exempt_portion=0.0),
        make_facts("SOLO", 2022, income=-500_000, exempt_portion=0.0),
    ]
    out = _run(single_entity_factory(facts), [2021, 2022])
    assert out[("SOLO", 2022)].closing.taxable_surplus == 0.0
