"""Surplus elevates UP a tier only on an actual distribution, at owner's %."""

from __future__ import annotations

from surplus_engine.engine import SurplusEngine
from tests.conftest import make_entity, make_facts, make_structure


def _run(structure, years):
    eng = SurplusEngine(structure)
    return {(r.entity, r.year): r for r in eng.run(years)}


def test_no_elevation_without_distribution():
    # Child earns big surplus but distributes nothing -> parent gets no elevation.
    child = make_entity("CHILD", tier=0, parent="PAR", ownership_pct=1.0)
    parent = make_entity("PAR", tier=1, parent=None, ownership_pct=1.0)
    facts = [
        make_facts("CHILD", 2021, income=1_000_000, exempt_portion=1.0),  # no distribution
        make_facts("PAR", 2021, income=0),
    ]
    struct = make_structure([child, parent], facts)
    out = _run(struct, [2021])
    assert out[("PAR", 2021)].elevated_exempt == 0.0
    assert out[("PAR", 2021)].elevated_taxable == 0.0
    assert out[("PAR", 2021)].closing.exempt_surplus == 0.0


def test_elevation_only_on_distribution_at_owner_pct():
    # Child 80%-owned; distributes 100 funded entirely from exempt (cap high
    # enough). Parent should receive 80% of the exempt draw as elevated exempt.
    child = make_entity("CHILD", tier=0, parent="PAR", ownership_pct=0.80)
    parent = make_entity("PAR", tier=1, parent=None, ownership_pct=1.0)
    facts = [
        # exempt_portion 0.8 funds BOTH pools (800k exempt, 200k taxable). With
        # the default cap 0.6 a 100k distribution draws 60k exempt (cap-limited),
        # then spills 40k into the (funded) taxable pool.
        make_facts("CHILD", 2021, income=1_000_000, exempt_portion=0.80,
                   distribution=100_000),
        make_facts("PAR", 2021, income=0),
    ]
    struct = make_structure([child, parent], facts)
    out = _run(struct, [2021])
    child_r = out[("CHILD", 2021)]
    par_r = out[("PAR", 2021)]

    # Child distribution: exempt pool huge, but cap 0.6 -> 60k exempt + 40k taxable.
    drawn = {s.pool: s.amount for s in child_r.waterfall}
    assert drawn["exempt_surplus"] == 60_000
    assert drawn["taxable_surplus"] == 40_000

    # Parent elevation = 80% of each drawn characterisation.
    assert par_r.elevated_exempt == 48_000     # 60k * 0.80
    assert par_r.elevated_taxable == 32_000     # 40k * 0.80
    assert par_r.closing.exempt_surplus == 48_000
    assert par_r.closing.taxable_surplus == 32_000


def test_multi_tier_elevation_chains_upward():
    # 3-tier chain, all 100%-owned, exempt cap raised to 1.0 so draws stay exempt.
    op = make_entity("OP", tier=0, parent="MEZZ", ownership_pct=1.0)
    mezz = make_entity("MEZZ", tier=1, parent="TOP", ownership_pct=1.0)
    top = make_entity("TOP", tier=2, parent=None, ownership_pct=1.0)
    facts = [
        make_facts("OP", 2021, income=1_000_000, exempt_portion=1.0, distribution=200_000),
        make_facts("MEZZ", 2021, income=0, exempt_portion=1.0, distribution=150_000),
        make_facts("TOP", 2021, income=0),
    ]
    struct = make_structure([op, mezz, top], facts)
    eng = SurplusEngine(struct, exempt_cap_fraction=1.0)  # keep everything exempt
    out = {(r.entity, r.year): r for r in eng.run([2021])}

    # OP distributes 200k exempt -> MEZZ receives 200k elevated exempt.
    assert out[("MEZZ", 2021)].elevated_exempt == 200_000
    # MEZZ then has 200k exempt and distributes 150k -> TOP receives 150k.
    assert out[("TOP", 2021)].elevated_exempt == 150_000
    # MEZZ closing exempt = 200k received - 150k distributed = 50k.
    assert out[("MEZZ", 2021)].closing.exempt_surplus == 50_000
    assert out[("TOP", 2021)].closing.exempt_surplus == 150_000
