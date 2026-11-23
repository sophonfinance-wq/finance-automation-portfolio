"""Tests for the Triangulate Review Loop.

Prove the boundary of autonomy the framework exists for: arithmetic drift is
re-derived and re-reviewed to PASS; judgment findings (AI assumptions,
hardcoded cells) are escalated, never manufactured. Each remediation is a new
workpaper version — the read-only guard is never touched.
"""

from __future__ import annotations

from triangulate.formula import evaluate
from triangulate.generate import (
    make_adversarial_workpaper,
    make_clean_workpaper,
    make_defective_workpaper,
)
from triangulate.loop import (
    AUTO_CLEARED,
    CLEAN,
    ESCALATED,
    render_markdown,
    review_loop,
    verdict_exit_code,
)


# --------------------------------------------------------------------------- #
# The headline behaviour: the adversarial injection self-clears.
# --------------------------------------------------------------------------- #
def test_adversarial_injection_auto_clears():
    journal = review_loop(make_adversarial_workpaper(), scenario="adversarial")
    assert journal.initial_verdict == "FAIL"
    assert journal.verdict == AUTO_CLEARED
    assert journal.final_pipeline_verdict == "PASS"
    # One arithmetic fix (B5) cascades to clear B7/B8 on re-review.
    assert len(journal.turns) == 1
    assert journal.turns[0].correction.cell_ref == "B5"
    assert verdict_exit_code(journal) == 0


def test_correction_is_the_formula_rederivation():
    """The loop never invents: the fix equals the cell's own formula value."""
    wp = make_adversarial_workpaper()
    values = {ref: c.value for ref, c in wp.cells.items() if c.value is not None}
    expected_b5 = round(evaluate(wp.cells["B5"].formula, values), 2)
    journal = review_loop(make_adversarial_workpaper(), scenario="adversarial")
    assert journal.turns[0].correction.to_value == expected_b5


def test_each_turn_is_a_new_version_original_untouched():
    wp = make_adversarial_workpaper()
    before = wp.digest()
    journal = review_loop(wp, scenario="adversarial")
    assert wp.digest() == before               # input never mutated
    digests = {t.version_digest for t in journal.turns}
    assert before[:12] not in digests          # every turn minted a new version


# --------------------------------------------------------------------------- #
# The boundary: judgment escalates.
# --------------------------------------------------------------------------- #
def test_defective_sample_escalates_judgment_findings():
    journal = review_loop(make_defective_workpaper(), scenario="defective")
    assert journal.verdict == ESCALATED
    assert journal.final_pipeline_verdict in ("FLAG", "FAIL")
    assert verdict_exit_code(journal) == 1
    # The residual fix packet contains the judgment finding types.
    residual = " ".join(journal.residual_findings)
    assert "HARDCODED_NO_FORMULA" in residual or "UNSUPPORTED_AI_ASSUMPTION" in residual
    # But the loop DID clear what arithmetic could prove.
    assert len(journal.turns) >= 1


def test_clean_workpaper_is_clean():
    journal = review_loop(make_clean_workpaper(), scenario="clean")
    assert journal.verdict == CLEAN
    assert not journal.turns
    assert verdict_exit_code(journal) == 0


def test_budget_zero_escalates_without_fixing():
    journal = review_loop(make_adversarial_workpaper(), scenario="adversarial", budget=0)
    assert journal.verdict == ESCALATED
    assert not journal.turns
    assert verdict_exit_code(journal) == 1


# --------------------------------------------------------------------------- #
# Determinism + rendering + CLI.
# --------------------------------------------------------------------------- #
def test_loop_is_deterministic():
    md1 = render_markdown(review_loop(make_adversarial_workpaper(), scenario="adversarial"))
    md2 = render_markdown(review_loop(make_adversarial_workpaper(), scenario="adversarial"))
    assert md1 == md2


def test_markdown_report_contents():
    md = render_markdown(review_loop(make_defective_workpaper(), scenario="defective"))
    assert "ESCALATED" in md
    assert "Fix packet — left for the human" in md
    assert "cannot" in md and "authority" in md


def test_cli_smoke(tmp_path):
    from triangulate.loop import main

    assert main(["--sample", "adversarial", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "review_loop_report.md").exists()
    assert main(["--sample", "defective"]) == 1
    assert main(["--sample", "clean"]) == 0
