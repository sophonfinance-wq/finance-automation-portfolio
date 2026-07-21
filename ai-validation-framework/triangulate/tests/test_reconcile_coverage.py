"""Coverage tests for reconciliation, severity breakdown and the HumanGate
(``triangulate.reconcile``).
"""

from __future__ import annotations

import pytest

from triangulate.model import AuthoritySource, Finding, Severity
from triangulate.reconcile import (
    HumanGate,
    VerdictStatus,
    reconcile,
    severity_breakdown,
)


def _f(code, ref, sev, auth=AuthoritySource.AI_ASSUMPTION, msg="m"):
    return Finding(code, ref, sev, msg, "raiser", authority=auth)


# --------------------------------------------------------------------------- #
# severity_breakdown                                                           #
# --------------------------------------------------------------------------- #
def test_breakdown_empty_has_all_four_buckets_zeroed():
    assert severity_breakdown([]) == {
        "Critical": 0, "High": 0, "Medium": 0, "Low": 0
    }


def test_breakdown_counts_each_severity():
    findings = [
        _f("A", "B1", Severity.LOW),
        _f("B", "B2", Severity.LOW),
        _f("C", "B3", Severity.HIGH),
        _f("D", "B4", Severity.CRITICAL),
    ]
    counts = severity_breakdown(findings)
    assert counts == {"Critical": 1, "High": 1, "Medium": 0, "Low": 2}


def test_breakdown_total_equals_input_length():
    findings = [_f("A", f"B{i}", Severity.MEDIUM) for i in range(7)]
    assert sum(severity_breakdown(findings).values()) == 7


# --------------------------------------------------------------------------- #
# reconcile: dedup, conflict resolution, ordering                             #
# --------------------------------------------------------------------------- #
def test_reconcile_empty_is_empty():
    assert reconcile([]) == []


def test_reconcile_dedupes_on_code_and_cell():
    a = _f("DUP", "B7", Severity.HIGH, AuthoritySource.AI_ASSUMPTION, "first")
    b = _f("DUP", "B7", Severity.HIGH, AuthoritySource.AI_ASSUMPTION, "second")
    ranked = reconcile([a, b])
    assert len(ranked) == 1


def test_reconcile_keeps_distinct_codes_on_same_cell():
    a = _f("X", "B7", Severity.HIGH)
    b = _f("Y", "B7", Severity.HIGH)
    assert len(reconcile([a, b])) == 2


def test_reconcile_keeps_distinct_cells_for_same_code():
    a = _f("X", "B1", Severity.HIGH)
    b = _f("X", "B2", Severity.HIGH)
    assert len(reconcile([a, b])) == 2


def test_higher_authority_wins_conflict():
    low = _f("DUP", "B7", Severity.HIGH, AuthoritySource.AI_ASSUMPTION, "low")
    high = _f("DUP", "B7", Severity.HIGH, AuthoritySource.SIGNED_PRIOR_YEAR, "high")
    # Order of input must not matter -- authority decides.
    assert reconcile([low, high])[0].message == "high"
    assert reconcile([high, low])[0].message == "high"


def test_severity_breaks_tie_when_authority_equal():
    lo = _f("DUP", "B7", Severity.LOW, AuthoritySource.AI_ASSUMPTION, "lo")
    hi = _f("DUP", "B7", Severity.HIGH, AuthoritySource.AI_ASSUMPTION, "hi")
    assert reconcile([lo, hi])[0].message == "hi"
    assert reconcile([hi, lo])[0].message == "hi"


def test_reconcile_sorts_most_severe_first():
    findings = [
        _f("A", "B1", Severity.LOW),
        _f("B", "B2", Severity.CRITICAL),
        _f("C", "B3", Severity.MEDIUM),
        _f("D", "B4", Severity.HIGH),
    ]
    ranked = reconcile(findings)
    assert [f.severity for f in ranked] == [
        Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW
    ]


def test_reconcile_secondary_sort_by_authority_then_cell():
    # Same severity: higher authority first; equal authority -> cell_ref asc.
    a = _f("A", "B9", Severity.HIGH, AuthoritySource.AI_ASSUMPTION)
    b = _f("B", "B1", Severity.HIGH, AuthoritySource.SIGNED_PRIOR_YEAR)
    c = _f("C", "B2", Severity.HIGH, AuthoritySource.AI_ASSUMPTION)
    ranked = reconcile([a, b, c])
    # b has highest authority -> first; then a & c (same authority) by cell_ref.
    assert [f.cell_ref for f in ranked] == ["B1", "B2", "B9"]


def test_reconcile_is_idempotent():
    findings = [
        _f("A", "B1", Severity.LOW),
        _f("B", "B2", Severity.CRITICAL),
        _f("A", "B1", Severity.LOW),  # duplicate
    ]
    once = reconcile(findings)
    twice = reconcile(once)
    assert [f.to_dict() for f in once] == [f.to_dict() for f in twice]


def test_reconcile_does_not_mutate_input_list():
    findings = [_f("B", "B2", Severity.CRITICAL), _f("A", "B1", Severity.LOW)]
    snapshot = list(findings)
    reconcile(findings)
    assert findings == snapshot


# --------------------------------------------------------------------------- #
# HumanGate policy                                                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "severities, expected_status",
    [
        ([], VerdictStatus.PASS),
        ([Severity.LOW], VerdictStatus.PASS),
        ([Severity.MEDIUM], VerdictStatus.PASS),
        ([Severity.LOW, Severity.MEDIUM], VerdictStatus.PASS),
        ([Severity.HIGH], VerdictStatus.FLAG),
        ([Severity.HIGH, Severity.LOW], VerdictStatus.FLAG),
        ([Severity.CRITICAL], VerdictStatus.FAIL),
        ([Severity.CRITICAL, Severity.HIGH], VerdictStatus.FAIL),
        ([Severity.MEDIUM, Severity.CRITICAL], VerdictStatus.FAIL),
    ],
)
def test_human_gate_status_by_worst_severity(severities, expected_status):
    findings = [_f("X", f"B{i}", s) for i, s in enumerate(severities)]
    verdict = HumanGate().decide(findings)
    assert verdict.status is expected_status


def test_human_gate_pass_sets_passed_true():
    v = HumanGate().decide([_f("X", "B1", Severity.LOW)])
    assert v.passed is True
    assert v.status is VerdictStatus.PASS


def test_human_gate_non_pass_sets_passed_false_and_adds_note():
    v = HumanGate().decide([_f("X", "B1", Severity.CRITICAL)])
    assert v.passed is False
    # Non-pass verdicts carry the authority-hierarchy remediation note.
    assert any("authority" in n.lower() for n in v.notes)


def test_human_gate_pass_has_no_remediation_note():
    v = HumanGate().decide([])
    assert v.notes == []


def test_human_gate_max_severity_is_recorded():
    v = HumanGate().decide([
        _f("A", "B1", Severity.LOW),
        _f("B", "B2", Severity.HIGH),
    ])
    assert v.max_severity is Severity.HIGH


def test_human_gate_empty_max_severity_is_none():
    v = HumanGate().decide([])
    assert v.max_severity is None
    assert v.to_dict()["max_severity"] is None


def test_human_gate_custom_signer_is_recorded():
    gate = HumanGate(signer="Partner-In-Charge")
    v = gate.decide([])
    assert v.signed_off_by == "Partner-In-Charge"


def test_human_gate_rationale_mentions_count():
    v = HumanGate().decide([
        _f("A", "B1", Severity.CRITICAL),
        _f("B", "B2", Severity.CRITICAL),
    ])
    assert "2 Critical" in v.rationale


def test_human_gate_clean_rationale_when_no_findings():
    v = HumanGate().decide([])
    assert "Clean run" in v.rationale
    assert "eligible for human sign-off" in v.rationale


# --------------------------------------------------------------------------- #
# Verdict.to_dict                                                              #
# --------------------------------------------------------------------------- #
def test_verdict_to_dict_serialises_findings_and_status():
    findings = [_f("A", "B1", Severity.CRITICAL)]
    v = HumanGate().decide(findings)
    d = v.to_dict()
    assert d["status"] == "FAIL"
    assert d["max_severity"] == "Critical"
    assert isinstance(d["findings"], list)
    assert d["findings"][0]["code"] == "A"
    assert d["severity_counts"]["Critical"] == 1
    assert d["signed_off_by"] == "HumanGate(automated-policy)"
