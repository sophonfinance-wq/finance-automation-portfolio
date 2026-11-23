"""Tests for the Reconciliation Assurance Loop.

Prove the substrate (injected drift genuinely deviates from the baseline), the
loop's behaviour (it converges account-by-account to the source of record and
preserves the scenario's genuine reconciling items), the materiality gate, and
determinism.
"""

from __future__ import annotations

from recon_engine import MATERIALITY_THRESHOLD
from recon_engine.engine import reconcile
from recon_engine.generate import DEFAULT_SEED, generate_dataset
from recon_engine.loop import (
    FAIL,
    FLAG,
    PASS,
    _outcomes,
    assurance_loop,
    demo_setup,
    deviations,
    render_markdown,
    verdict_exit_code,
)


def _baseline():
    return reconcile(generate_dataset(DEFAULT_SEED), threshold=MATERIALITY_THRESHOLD)


# --------------------------------------------------------------------------- #
# Substrate.
# --------------------------------------------------------------------------- #
def test_demo_drift_deviates_from_baseline():
    pristine, drifted, faults = demo_setup()
    assert len(faults) == 3
    devs = deviations(reconcile(drifted, threshold=MATERIALITY_THRESHOLD), _baseline())
    assert len(devs) == 3
    # The faults hit three distinct accounts, all clean in the baseline.
    base_clean = {
        ln.account_number
        for ln in _baseline().all_active_lines
        if ln.classification == "clean"
    }
    assert {d.account_number for d in devs} <= base_clean


def test_pristine_dataset_has_no_deviation():
    assert deviations(_baseline(), _baseline()) == []


# --------------------------------------------------------------------------- #
# Loop behaviour.
# --------------------------------------------------------------------------- #
def test_loop_converges_and_flags_material_drift():
    _pristine, drifted, faults = demo_setup()
    journal = assurance_loop(drifted, faults=faults)
    assert journal.converged
    assert journal.verdict == FLAG
    assert len(journal.turns) == 3
    assert journal.turns[-1].deviations_after == 0
    assert journal.total_correction > journal.materiality
    # Accounts resynced in deterministic (sorted) order.
    assert list(journal.accounts_resynced) == sorted(journal.accounts_resynced)


def test_loop_restores_fidelity_not_zero_variances():
    """Genuine reconciling items survive; only injected drift is corrected."""
    _pristine, drifted, faults = demo_setup()
    assurance_loop(drifted, faults=faults)
    settled = reconcile(drifted, threshold=MATERIALITY_THRESHOLD)
    assert _outcomes(settled) == _outcomes(_baseline())
    # The scenario's intentional flags are still flagged — not papered over.
    assert settled.summary_counts()["flag"] == _baseline().summary_counts()["flag"] > 0


def test_clean_dataset_passes_in_zero_turns():
    journal = assurance_loop(generate_dataset(DEFAULT_SEED))
    assert journal.verdict == PASS
    assert not journal.turns
    assert journal.total_adjustments == 0


def test_budget_exhaustion_fails():
    _pristine, drifted, faults = demo_setup()
    journal = assurance_loop(drifted, faults=faults, budget=1)
    assert not journal.converged
    assert journal.verdict == FAIL
    assert verdict_exit_code(journal.verdict) == 1


def test_verdict_exit_codes():
    assert verdict_exit_code(PASS) == 0
    assert verdict_exit_code(FLAG) == 0
    assert verdict_exit_code(FAIL) == 1


# --------------------------------------------------------------------------- #
# Determinism + rendering + CLI.
# --------------------------------------------------------------------------- #
def test_loop_is_deterministic():
    j1 = assurance_loop(demo_setup()[1], faults=demo_setup()[2])
    j2 = assurance_loop(demo_setup()[1], faults=demo_setup()[2])
    assert render_markdown(j1) == render_markdown(j2)


def test_markdown_report_contents():
    _pristine, drifted, faults = demo_setup()
    md = render_markdown(assurance_loop(drifted, faults=faults))
    assert "FLAG" in md
    assert "Turn 1" in md and "Turn 3" in md
    assert "Injected drift" in md


def test_cli_smoke(tmp_path):
    from recon_engine.loop import main

    rc = main(["--demo", "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "assurance_loop_report.md").exists()
    assert main(["--demo", "--budget", "1"]) == 1
    assert main([]) == 0  # clean run
