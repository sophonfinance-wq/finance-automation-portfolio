"""Tests for the Autonomous Close Loop.

These prove the substrate (the injected drift really trips the sentinel), the
loop's behaviour (it resyncs each drifted category to the authoritative
re-derivation and posts autonomously), the boundary of autonomy (a tampered
locked period is quarantined; a broken opening halts the post), that it never
invents a number (the settled register equals a clean engine run), and that the
whole thing is deterministic.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from close_engine.engine import CloseEngine
from close_engine.faults import inject_unbalanced_opening
from close_engine.generate import generate_dataset
from close_engine.loop import (
    AUTO_POSTED,
    HALTED,
    PARTIAL,
    _category_lines,
    _differing_categories,
    autonomous_close_loop,
    demo_setup,
    verdict_exit_code,
)
from close_engine.loop_report import render_html_document, render_markdown
from close_engine.sentinel import run_sentinel

PERIOD, SEED = "2026-03", 2026


# --------------------------------------------------------------------------- #
# Substrate.
# --------------------------------------------------------------------------- #
def test_demo_drift_trips_the_sentinel():
    dataset, posted, locked, faults = demo_setup(PERIOD, SEED)
    report = run_sentinel(dataset, posted, locked=locked)
    assert not report.clean
    controls = {f.control_id for f in report.findings}
    for expected in ("C2", "C3", "C8", "C9", "C10"):
        assert expected in controls, f"{expected} did not fire"


def test_clean_close_reconciles_untouched():
    dataset = generate_dataset(PERIOD, seed=SEED)
    posted = CloseEngine(dataset).run()
    baseline = run_sentinel(dataset, posted)
    assert not baseline.findings  # clean baseline: zero findings


# --------------------------------------------------------------------------- #
# Loop behaviour.
# --------------------------------------------------------------------------- #
def test_loop_auto_posts_partial_and_quarantines_locked_period():
    dataset, posted, locked, faults = demo_setup(PERIOD, SEED)
    journal = autonomous_close_loop(dataset, posted, locked=locked)
    assert journal.verdict == PARTIAL
    assert journal.posted
    # Exactly the four drifted categories are resynced, in engine order.
    assert list(journal.categories_resynced) == [
        "prepaid_amortization",
        "mgmt_fee_accrual",
        "note_interest",
        "gna_allocation",
    ]
    # The tampered locked period is held, not acted on.
    assert len(journal.quarantined) == 1
    assert journal.quarantined[0].control_id == "C10"
    assert not journal.halted_on
    # Criticals strictly decrease to just the quarantined one.
    assert journal.turns[-1].criticals_after == 1


def test_loop_never_invents_numbers():
    """After the loop, every category equals a clean engine re-derivation."""
    dataset, posted, locked, faults = demo_setup(PERIOD, SEED)
    autonomous_close_loop(dataset, posted, locked=locked)
    authoritative = CloseEngine(dataset).run()
    assert not _differing_categories(posted, authoritative)
    # And there is nothing left for the loop to do (idempotent).
    again = autonomous_close_loop(dataset, posted, locked=locked)
    assert not again.turns


def test_clean_close_auto_posts_in_zero_turns():
    dataset = generate_dataset(PERIOD, seed=SEED)
    posted = CloseEngine(dataset).run()
    journal = autonomous_close_loop(dataset, posted)
    assert journal.verdict == AUTO_POSTED
    assert not journal.turns
    assert journal.total_adjustments == 0


# --------------------------------------------------------------------------- #
# The boundary of autonomy.
# --------------------------------------------------------------------------- #
def test_broken_opening_halts_rather_than_fabricates():
    dataset = generate_dataset(PERIOD, seed=SEED)
    corrupted, _desc = inject_unbalanced_opening(dataset)
    posted = CloseEngine(corrupted).run()
    journal = autonomous_close_loop(corrupted, posted)
    assert journal.verdict == HALTED
    assert any(b.control_id == "C1" for b in journal.halted_on)
    assert verdict_exit_code(journal.verdict) == 1


def test_budget_exhaustion_halts():
    dataset, posted, locked, faults = demo_setup(PERIOD, SEED)
    journal = autonomous_close_loop(dataset, posted, locked=locked, budget=1)
    assert journal.verdict == HALTED
    assert len(journal.turns) == 1
    assert verdict_exit_code(journal.verdict) == 1


def test_verdict_exit_codes():
    assert verdict_exit_code(AUTO_POSTED) == 0
    assert verdict_exit_code(PARTIAL) == 0
    assert verdict_exit_code(HALTED) == 1


# --------------------------------------------------------------------------- #
# Determinism + rendering.
# --------------------------------------------------------------------------- #
def test_loop_is_deterministic():
    d1, p1, l1, f1 = demo_setup(PERIOD, SEED)
    d2, p2, l2, f2 = demo_setup(PERIOD, SEED)
    j1 = replace(autonomous_close_loop(d1, p1, locked=l1), faults=f1)
    j2 = replace(autonomous_close_loop(d2, p2, locked=l2), faults=f2)
    assert render_markdown(j1) == render_markdown(j2)
    assert render_html_document(j1) == render_html_document(j2)


def test_reports_render():
    dataset, posted, locked, faults = demo_setup(PERIOD, SEED)
    journal = replace(autonomous_close_loop(dataset, posted, locked=locked), faults=faults)
    md = render_markdown(journal)
    assert "AUTO-POSTED (PARTIAL)" in md
    assert "Turn 1" in md and "Turn 4" in md
    assert "QUARANTINE" in md and "C10" in md
    html = render_html_document(journal)
    assert html.startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html.lower()


def test_cli_smoke(tmp_path):
    from close_engine.loop import main

    rc = main(["--demo", "--out", str(tmp_path)])
    assert rc == 0
    tracked_output = Path(__file__).resolve().parents[2] / "output"
    for name in ("autonomous_close_loop.md", "autonomous_close_loop.html"):
        assert (tmp_path / name).read_text("utf-8") == (
            tracked_output / name
        ).read_text("utf-8"), f"stale tracked output: {name}"

    rc_halt = main(["--demo", "--budget", "1"])
    assert rc_halt == 1
