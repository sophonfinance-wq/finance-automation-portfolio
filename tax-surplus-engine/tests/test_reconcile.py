"""Reconciliation harness: identities pass on valid runs; tampering is detected."""

from __future__ import annotations

from surplus_engine.engine import SurplusEngine
from surplus_engine.generate import generate_structure
from surplus_engine.reconcile import reconcile
from tests.conftest import make_entity, make_facts, make_structure  # noqa: F401


def test_generated_structure_fully_reconciles():
    struct = generate_structure(2021, 2024)
    results = SurplusEngine(struct).run(struct.years)
    report = reconcile(results, struct)
    assert report.ok, [(c.name, c.entity, c.year, c.delta) for c in report.breaks]
    # A healthy battery ran across 4 entities x 4 years.
    assert len(report.checks) > 50


def test_identities_hold_on_multi_tier_with_elevation():
    child = make_entity("CHILD", tier=0, parent="PARENT", ownership_pct=0.80)
    parent = make_entity("PARENT", tier=1, parent=None, ownership_pct=1.0)
    facts = [
        make_facts("CHILD", 2021, income=1_000_000, exempt_portion=1.0),
        make_facts("CHILD", 2022, distribution=300_000),
        make_facts("PARENT", 2021, income=0.0),
    ]
    struct = make_structure([child, parent], facts, years=[2021, 2022])
    results = SurplusEngine(struct).run([2021, 2022])
    report = reconcile(results, struct)
    assert report.ok, [(c.name, c.entity, c.year, c.delta) for c in report.breaks]
    # Elevation actually occurred: the child drew exempt surplus, lifted at 80%.
    elev = next(
        c for c in report.checks
        if c.name == "elevation_exempt" and c.entity == "PARENT" and c.year == 2022
    )
    assert elev.expected > 0
    assert elev.passed


def test_acb_break_is_detected_when_balance_tampered():
    struct = generate_structure(2021, 2023)
    results = SurplusEngine(struct).run(struct.years)
    # Corrupt one closing ACB; the conservation identity must catch it.
    results[0].closing.acb += 12_345.0
    report = reconcile(results, struct)
    assert not report.ok
    assert "acb_conservation" in {c.name for c in report.breaks}


def test_exempt_break_is_detected_when_pool_tampered():
    struct = generate_structure(2021, 2023)
    results = SurplusEngine(struct).run(struct.years)
    target = next(r for r in results if r.closing.exempt_surplus > 0)
    target.closing.exempt_surplus += 9_999.0
    report = reconcile(results, struct)
    assert not report.ok
    assert "exempt_conservation" in {c.name for c in report.breaks}
