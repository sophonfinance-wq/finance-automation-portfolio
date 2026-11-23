"""Tests for the Surplus Assurance Loop.

The loop is a bounded, human-gated remediation loop over the reconciliation
harness. These tests prove the substrate (injected drift really breaks the named
identities), the loop's behaviour (converges, and to the *authoritative* numbers
— it never invents figures), the verdict gate (PASS / FLAG / FAIL), and that the
whole thing is deterministic.
"""

from __future__ import annotations

from surplus_engine.engine import SurplusEngine
from surplus_engine.generate import generate_structure
from surplus_engine.loop import (
    DEMO_FAULTS,
    FAIL,
    FLAG,
    PASS,
    Fault,
    Mutation,
    apply_faults,
    assurance_loop,
    run_authoritative,
    verdict_exit_code,
)
from surplus_engine.loop_report import (
    render_html_document,
    render_markdown,
)
from surplus_engine.reconcile import reconcile

YEARS = [2021, 2022, 2023, 2024]


def _structure():
    return generate_structure(2021, 2024)


# --------------------------------------------------------------------------- #
# Substrate: the injected drift genuinely breaks the named controls.
# --------------------------------------------------------------------------- #
def test_clean_run_reconciles_with_no_drift():
    struct = _structure()
    journal = assurance_loop(struct, YEARS, faults=())
    assert journal.converged
    assert journal.verdict == PASS
    assert len(journal.turns) == 0
    assert journal.total_adjustments == 0
    assert len(journal.initial_breaks) == 0


def test_demo_faults_break_reconcile():
    struct = _structure()
    authoritative = run_authoritative(struct, YEARS)
    assert reconcile(authoritative, struct).ok  # clean baseline

    drifted = apply_faults(authoritative, DEMO_FAULTS)
    report = reconcile(drifted, struct)
    assert not report.ok
    names = {c.name for c in report.breaks}
    # Each demo fault's control must actually fire.
    assert "exempt_conservation" in names          # F1
    assert "elevation_exempt" in names             # F2
    assert "acb_conservation" in names             # F3


def test_each_demo_fault_individually_breaks_its_control():
    struct = _structure()
    authoritative = run_authoritative(struct, YEARS)
    for fault in DEMO_FAULTS:
        drifted = apply_faults(authoritative, (fault,))
        report = reconcile(drifted, struct)
        assert not report.ok, f"{fault.id} did not break any identity"


# --------------------------------------------------------------------------- #
# Loop behaviour.
# --------------------------------------------------------------------------- #
def test_loop_converges_and_flags_material_drift():
    struct = _structure()
    journal = assurance_loop(struct, YEARS, faults=DEMO_FAULTS)
    assert journal.converged
    assert journal.verdict == FLAG                 # material adjustments booked
    # One remediation turn per distinct contaminated fiscal year (2021, 2022, 2023).
    assert [t.year_settled for t in journal.turns] == [2021, 2022, 2023]
    # Breaks strictly decrease to zero.
    assert journal.turns[-1].breaks_after_count == 0
    assert journal.total_adjustment_cad > journal.materiality_cad


def test_settled_workpapers_match_engine_exactly():
    """The loop's corrections reproduce the engine's own closing balances."""
    struct = _structure()
    engine_results = SurplusEngine(struct).run(YEARS)
    engine_by_key = {(r.entity, r.year): r for r in engine_results}

    # Manually mirror the loop: drift, then settle every year.
    from surplus_engine.loop import _settle_year  # internal, but part of the contract

    authoritative = run_authoritative(struct, YEARS)
    auth_by_key = {(r.entity, r.year): r for r in authoritative}
    drifted = apply_faults(authoritative, DEMO_FAULTS)
    wp_by_key = {(r.entity, r.year): r for r in drifted}
    entities = list(struct.entities.keys())
    for year in YEARS:
        _settle_year(wp_by_key, auth_by_key, year, entities, struct)

    for key, eng in engine_by_key.items():
        wp = wp_by_key[key]
        assert round(wp.closing.exempt_surplus, 2) == round(eng.closing.exempt_surplus, 2)
        assert round(wp.closing.taxable_surplus, 2) == round(eng.closing.taxable_surplus, 2)
        assert round(wp.closing.pre_acquisition_capital, 2) == round(eng.closing.pre_acquisition_capital, 2)
        assert round(wp.closing.acb, 2) == round(eng.closing.acb, 2)
        assert round(wp.elevated_exempt, 2) == round(eng.elevated_exempt, 2)


def test_pass_on_immaterial_drift():
    struct = _structure()
    tiny = (
        Fault(
            id="TINY",
            title="sub-materiality rounding drift",
            entity="BIRCH_OP",
            year=2022,
            mutations=(Mutation("closing.exempt_surplus", "add", 50.00),),
            control="exempt_conservation",
        ),
    )
    journal = assurance_loop(struct, YEARS, faults=tiny)
    assert journal.converged
    assert journal.verdict == PASS
    assert 0 < journal.total_adjustment_cad <= journal.materiality_cad


def test_fail_on_budget_exhaustion():
    struct = _structure()
    journal = assurance_loop(struct, YEARS, faults=DEMO_FAULTS, budget=1)
    assert not journal.converged
    assert journal.verdict == FAIL
    assert verdict_exit_code(journal.verdict) == 1
    assert len(journal.turns) == 1


def test_verdict_exit_codes():
    assert verdict_exit_code(PASS) == 0
    assert verdict_exit_code(FLAG) == 0
    assert verdict_exit_code(FAIL) == 1


# --------------------------------------------------------------------------- #
# Determinism + rendering.
# --------------------------------------------------------------------------- #
def test_loop_is_deterministic():
    struct1 = _structure()
    struct2 = _structure()
    j1 = assurance_loop(struct1, YEARS, faults=DEMO_FAULTS)
    j2 = assurance_loop(struct2, YEARS, faults=DEMO_FAULTS)
    assert render_markdown(j1, struct1) == render_markdown(j2, struct2)
    assert render_html_document(j1, struct1) == render_html_document(j2, struct2)


def test_markdown_report_contains_verdict_and_turns():
    struct = _structure()
    journal = assurance_loop(struct, YEARS, faults=DEMO_FAULTS)
    md = render_markdown(journal, struct)
    assert "FLAG" in md
    assert "Turn 1" in md and "Turn 3" in md
    assert "Injected drift" in md
    assert "acb" in md.lower()


def test_html_document_is_self_contained():
    struct = _structure()
    journal = assurance_loop(struct, YEARS, faults=DEMO_FAULTS)
    html = render_html_document(journal, struct)
    assert html.startswith("<!doctype html>")
    assert "Surplus Assurance Loop" in html
    # No external resources — the strict-CSP / offline guarantee.
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html.lower()


def test_cli_smoke_demo_and_budget(capsys, tmp_path):
    from surplus_engine.loop import main

    # Demo converges -> FLAG -> exit 0, and writes both reports.
    rc = main(["--demo", "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "assurance_loop_report.md").exists()
    assert (tmp_path / "assurance_loop.html").exists()

    # Same drift, budget of 1 -> FAIL -> exit 1.
    rc_fail = main(["--demo", "--budget", "1"])
    assert rc_fail == 1
