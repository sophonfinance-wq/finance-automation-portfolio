"""Core engine rules: surplus build-up, ACB invariance, FX, ownership %."""

from __future__ import annotations

from surplus_engine.engine import SurplusEngine
from surplus_engine.model import FxTable
from tests.conftest import make_entity, make_facts, make_structure


def _run(structure, years):
    eng = SurplusEngine(structure)
    return {(r.entity, r.year): r for r in eng.run(years)}


def test_standalone_surplus_is_income_plus_adjustment(single_entity_factory):
    facts = [make_facts("SOLO", 2021, income=1_000_000, adj=-50_000, exempt_portion=1.0)]
    struct = single_entity_factory(facts)
    res = _run(struct, [2021])[("SOLO", 2021)]
    assert res.standalone_surplus == 950_000
    # Fully exempt portion -> all goes to exempt pool.
    assert res.current_exempt_addition == 950_000
    assert res.current_taxable_addition == 0.0
    assert res.closing.exempt_surplus == 950_000


def test_exempt_portion_splits_current_surplus(single_entity_factory):
    facts = [make_facts("SOLO", 2021, income=1_000_000, adj=0, exempt_portion=0.40)]
    struct = single_entity_factory(facts)
    res = _run(struct, [2021])[("SOLO", 2021)]
    assert res.current_exempt_addition == 400_000
    assert res.current_taxable_addition == 600_000


def test_acb_unaffected_by_operating_income(single_entity_factory):
    # Big income, big distribution, but NO capital events -> ACB must stay 0.
    facts = [
        make_facts("SOLO", 2021, income=5_000_000, adj=100_000, exempt_portion=0.5,
                   distribution=400_000),
    ]
    struct = single_entity_factory(facts)
    res = _run(struct, [2021])[("SOLO", 2021)]
    assert res.closing.acb == 0.0  # operating income/loss never touches ACB


def test_acb_moves_only_on_capital_events(single_entity_factory):
    # Year 1: contribution raises ACB. Year 2: return of capital lowers it.
    facts = [
        make_facts("SOLO", 2021, income=2_000_000, exempt_portion=1.0,
                   capital_contribution=300_000),
        make_facts("SOLO", 2022, income=2_000_000, exempt_portion=1.0,
                   distribution=120_000, return_of_capital=120_000),
    ]
    struct = single_entity_factory(facts)
    out = _run(struct, [2021, 2022])
    assert out[("SOLO", 2021)].closing.acb == 300_000   # +contribution
    assert out[("SOLO", 2022)].closing.acb == 180_000   # -return of capital


def test_acb_floored_at_zero(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, income=2_000_000, exempt_portion=1.0,
                   capital_contribution=100_000),
        # Return of capital larger than ACB -> floor at 0, not negative.
        make_facts("SOLO", 2022, income=2_000_000, exempt_portion=1.0,
                   distribution=500_000, return_of_capital=500_000),
    ]
    struct = single_entity_factory(facts)
    out = _run(struct, [2021, 2022])
    assert out[("SOLO", 2022)].closing.acb == 0.0


def test_deemed_gain_on_negative_acb(single_entity_factory):
    # A return of capital beyond ACB triggers an ITA 40(3)-style deemed gain to
    # the owner; ACB still floors at nil (never goes negative).
    facts = [
        make_facts("SOLO", 2021, income=2_000_000, exempt_portion=1.0,
                   capital_contribution=100_000),
        make_facts("SOLO", 2022, income=2_000_000, exempt_portion=1.0,
                   distribution=500_000, return_of_capital=500_000),
    ]
    struct = single_entity_factory(facts)
    out = _run(struct, [2021, 2022])
    assert out[("SOLO", 2022)].closing.acb == 0.0
    assert out[("SOLO", 2022)].deemed_gain_on_negative_acb == 400_000  # 500k - 100k
    # No over-distribution -> no deemed gain in the contribution year.
    assert out[("SOLO", 2021)].deemed_gain_on_negative_acb == 0.0


def test_fx_applied_at_summary(single_entity_factory):
    from surplus_engine.report import attach_fx

    fx = FxTable(usd_cad={2021: 1.40})
    facts = [make_facts("SOLO", 2021, income=1_000_000, exempt_portion=1.0)]
    struct = single_entity_factory(facts, currency="USD", fx=fx)
    eng = SurplusEngine(struct)
    results = eng.run([2021])
    attach_fx(results, struct)
    r = results[0]
    assert r.fx_rate_to_cad == 1.40
    total_cad = (
        r.closing.exempt_surplus + r.closing.taxable_surplus
        + r.closing.pre_acquisition_capital
    ) * r.fx_rate_to_cad
    assert total_cad == 1_000_000 * 1.40


def test_cad_entity_uses_unit_fx(single_entity_factory):
    from surplus_engine.report import attach_fx

    fx = FxTable(usd_cad={2021: 1.40})
    facts = [make_facts("SOLO", 2021, income=500_000, exempt_portion=1.0)]
    struct = single_entity_factory(facts, currency="CAD", fx=fx)
    eng = SurplusEngine(struct)
    results = eng.run([2021])
    attach_fx(results, struct)
    assert results[0].fx_rate_to_cad == 1.0  # already CAD


def test_ownership_pct_scales_allocable_surplus():
    # Two-tier: child 75%-owned by parent. Allocable surplus at child reflects %.
    child = make_entity("CHILD", tier=0, parent="PAR", ownership_pct=0.75)
    parent = make_entity("PAR", tier=1, parent=None, ownership_pct=1.0)
    facts = [
        make_facts("CHILD", 2021, income=1_000_000, exempt_portion=1.0),
        make_facts("PAR", 2021, income=0),
    ]
    struct = make_structure([child, parent], facts)
    out = _run(struct, [2021])
    # Allocable surplus = standalone_surplus * ownership_pct.
    assert out[("CHILD", 2021)].allocable_surplus == 750_000
    # But the child's own pool holds 100% of its own surplus (allocation to the
    # parent happens via elevation on distribution, tested separately).
    assert out[("CHILD", 2021)].closing.exempt_surplus == 1_000_000


def test_net_loss_does_not_create_negative_exempt(single_entity_factory):
    facts = [make_facts("SOLO", 2021, income=-200_000, exempt_portion=1.0)]
    struct = single_entity_factory(facts)
    res = _run(struct, [2021])[("SOLO", 2021)]
    # Loss routes to taxable pool, which is floored at zero -> no negatives.
    assert res.closing.exempt_surplus == 0.0
    assert res.closing.taxable_surplus == 0.0
