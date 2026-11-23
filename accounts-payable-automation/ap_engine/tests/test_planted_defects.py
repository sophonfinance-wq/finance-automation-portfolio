"""Every planted defect must trip its own control, and only its own control.

Three assertions per rule, parametrized over :data:`ap_engine.generate.DEFECTS`:

1. the rule fires on its own fixture,
2. at the severity the design table specifies (FAIL vs FLAG),
3. and nothing else fires on that fixture -- so a passing suite cannot be the
   result of one blunt rule shadowing another.

A fourth test proves the same rule stays silent on the clean baseline, which is
what makes assertion (1) evidence rather than coincidence.
"""

from __future__ import annotations

import pytest

from ap_engine.engine import SEVERITY
from ap_engine.generate import DEFECTS, Defect
from ap_engine.model import DocumentReport, Status, Verdict

_IDS = [d.rule for d in DEFECTS]


@pytest.mark.parametrize("defect", DEFECTS, ids=_IDS)
def test_defect_trips_its_own_rule(
    defect: Defect, reports: dict[str, DocumentReport]
) -> None:
    """The planted defect produces a non-PASS finding on its own rule."""
    report = reports[defect.key]
    fired = [
        f for f in report.findings if f.rule == defect.rule and f.status is not Status.PASS
    ]
    assert fired, (
        f"{defect.rule} did not fire on its own fixture ({defect.label}); "
        f"controls that fired instead: {report.rules_fired()}"
    )


@pytest.mark.parametrize("defect", DEFECTS, ids=_IDS)
def test_defect_fires_at_the_designed_severity(
    defect: Defect, reports: dict[str, DocumentReport]
) -> None:
    """The observed severity matches the design table for that rule."""
    report = reports[defect.key]
    observed = {
        f.status
        for f in report.findings
        if f.rule == defect.rule and f.status is not Status.PASS
    }
    assert observed == {SEVERITY[defect.rule]}, (
        f"{defect.rule} fired at {observed}, design table says {SEVERITY[defect.rule]}"
    )


@pytest.mark.parametrize("defect", DEFECTS, ids=_IDS)
def test_defect_trips_nothing_else(
    defect: Defect, reports: dict[str, DocumentReport]
) -> None:
    """Exactly one control fires per fixture -- no collateral findings."""
    report = reports[defect.key]
    assert report.rules_fired() == [defect.rule], (
        f"fixture for {defect.rule} ({defect.label}) also tripped "
        f"{[r for r in report.rules_fired() if r != defect.rule]}"
    )


@pytest.mark.parametrize("defect", DEFECTS, ids=_IDS)
def test_rule_is_silent_on_the_clean_baseline(
    defect: Defect, clean_report: DocumentReport
) -> None:
    """The same rule must not fire on the clean baseline."""
    fired = [
        f
        for f in clean_report.findings
        if f.rule == defect.rule and f.status is not Status.PASS
    ]
    assert fired == [], f"{defect.rule} fired on the clean baseline: {fired}"


@pytest.mark.parametrize("defect", DEFECTS, ids=_IDS)
def test_defect_verdict_matches_its_severity(
    defect: Defect, reports: dict[str, DocumentReport]
) -> None:
    """A FAIL rule rolls the set up to FAIL; a FLAG rule rolls it to REVIEW."""
    report = reports[defect.key]
    expected = Verdict.FAIL if SEVERITY[defect.rule] is Status.FAIL else Verdict.REVIEW
    assert report.verdict is expected


def test_blocking_marker_fails_but_benign_notice_does_not() -> None:
    """The benign/blocking distinction, tested directly on both branches.

    Two document sets differing only in where the text sits: an informational
    notice must pass, the same run carrying a blocking marker must fail.
    """
    import json
    import random
    import tempfile
    from pathlib import Path

    from ap_engine.engine import analyze_document
    from ap_engine.generate import build_document_set

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        benign = build_document_set("Demo Holdings LLC", 1, random.Random(1))
        posting = benign["documents"][0]
        posting["notices"] = [
            "job-cost entries not created for 2 ledger-only invoice(s)",
            "vendor remit-to address updated since the prior run",
        ]
        posting["error_markers"] = []
        benign_path = base / "benign.json"
        benign_path.write_text(json.dumps(benign, indent=2), encoding="utf-8")

        blocking = build_document_set("Demo Holdings LLC", 1, random.Random(1))
        blocking["documents"][0]["notices"] = [
            "job-cost entries not created for 2 ledger-only invoice(s)",
            "batch contention detected; the update was aborted",
        ]
        blocking_path = base / "blocking.json"
        blocking_path.write_text(json.dumps(blocking, indent=2), encoding="utf-8")

        benign_findings = [
            f
            for f in analyze_document(benign_path).findings
            if f.rule == "post_no_error_marker"
        ]
        blocking_findings = [
            f
            for f in analyze_document(blocking_path).findings
            if f.rule == "post_no_error_marker"
        ]

    assert [f.status for f in benign_findings] == [Status.PASS]
    assert [f.status for f in blocking_findings] == [Status.FAIL]
    assert "batch contention" in blocking_findings[0].message


def test_amount_invalid_is_reported_not_coerced() -> None:
    """A float amount produces an AMOUNT_INVALID finding, not a rounded number."""
    import json
    import random
    import tempfile
    from pathlib import Path

    from ap_engine.engine import analyze_document
    from ap_engine.generate import build_document_set
    from ap_engine.money import AMOUNT_INVALID

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad_amount.json"
        packet = build_document_set("Maple Fund LP", 2, random.Random(2))
        posting = packet["documents"][0]
        posting["gl_recap"]["debit_cents"] = 1234.56
        path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        report = analyze_document(path)

    fired = [f for f in report.findings if f.rule == "post_gl_balanced"]
    assert len(fired) == 1
    assert fired[0].status is Status.FAIL
    assert AMOUNT_INVALID in fired[0].message
    assert "1234.56" in fired[0].message
