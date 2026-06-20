"""The adversarial demo is the portfolio's load-bearing claim, so it is pinned.

`--demo-adversarial` injects ONE hallucinated figure into an otherwise-clean
workpaper. The pipeline must catch it deterministically (Reviewer *and*
independent Auditor), return FAIL, and exit non-zero. A clean workpaper must
still sign off. If any of that breaks, these tests break.
"""

from __future__ import annotations

from triangulate.cli import main
from triangulate.generate import make_adversarial_workpaper
from triangulate.orchestrator import TriangulateOrchestrator
from triangulate.reconcile import VerdictStatus
from triangulate.roles.preparer import AdversarialPreparer


def _run():
    return TriangulateOrchestrator(preparer=AdversarialPreparer()).run()


def test_injection_breaks_the_tie_out():
    wp = make_adversarial_workpaper()
    streams = wp.get("B2").value + wp.get("B3").value + wp.get("B4").value
    assert wp.get("B5").value != streams  # stated total no longer ties to its formula


def test_pipeline_returns_fail():
    verdict = _run().verdict
    assert verdict.status is VerdictStatus.FAIL
    assert verdict.severity_counts["Critical"] > 0


def test_injected_cell_flagged_by_both_reviewer_and_auditor():
    findings = _run().verdict.findings
    b5 = {(f.code, "Reviewer" in f.raised_by, "Audit" in f.raised_by)
          for f in findings if f.cell_ref == "B5" and "TIE_OUT" in f.code}
    codes = {c for c, _, _ in b5}
    assert "TIE_OUT_MISMATCH" in codes          # the Reviewer (LLM-style) catch
    assert "AUDIT_TIE_OUT_FAIL" in codes        # the deterministic Auditor catch
    # Caught independently — not one model's opinion of itself.
    assert any(is_rev for _, is_rev, _ in b5)
    assert any(is_aud for _, _, is_aud in b5)


def test_error_cascades_to_dependent_cells():
    # B5 feeds B7 and B8; the single bad figure poisons the whole chain.
    refs = {f.cell_ref for f in _run().verdict.findings if f.severity.name == "CRITICAL"}
    assert {"B5", "B7", "B8"} <= refs


def test_cli_demo_exits_nonzero():
    assert main(["--demo-adversarial", "--no-artifacts"]) == 1


def test_clean_workpaper_still_signs_off():
    assert main(["--sample", "clean", "--no-artifacts"]) == 0
