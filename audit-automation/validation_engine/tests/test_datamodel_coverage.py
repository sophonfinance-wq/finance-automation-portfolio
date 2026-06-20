"""Coverage for the engine data model: Finding, WorkbookReport, enums.

Pins down the value-level behavior of the dataclasses and enums that the rest of
the engine relies on (serialisation, verdict roll-up precedence, status tally).
"""

from __future__ import annotations

import json

import pytest

from validation_engine.engine import (
    Finding,
    Status,
    Verdict,
    WorkbookReport,
    overall_verdict,
)


# --------------------------------------------------------------------------- #
# Status / Verdict enums
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "member, expected",
    [
        (Status.PASS, "PASS"),
        (Status.FAIL, "FAIL"),
        (Status.FLAG, "FLAG"),
    ],
)
def test_status_value_matches_name(member, expected):
    """Each Status member's value equals its uppercase name."""
    assert member.value == expected


@pytest.mark.parametrize(
    "member, expected",
    [
        (Verdict.PASS, "PASS"),
        (Verdict.REVIEW, "REVIEW"),
        (Verdict.FAIL, "FAIL"),
    ],
)
def test_verdict_value_matches_name(member, expected):
    """Each Verdict member's value equals its expected string."""
    assert member.value == expected


def test_status_is_str_enum():
    """Status is a str-Enum, so members compare equal to their raw string."""
    assert Status.FAIL == "FAIL"
    assert Verdict.REVIEW == "REVIEW"


# --------------------------------------------------------------------------- #
# Finding
# --------------------------------------------------------------------------- #
def test_finding_to_dict_has_exact_keys_and_values():
    """to_dict serialises rule/status/location/message with status as its value."""
    f = Finding("expected_formula", Status.FAIL, "Summary!B2", "boom")
    assert f.to_dict() == {
        "rule": "expected_formula",
        "status": "FAIL",
        "location": "Summary!B2",
        "message": "boom",
    }


def test_finding_to_dict_round_trips_through_json():
    """A Finding's dict is JSON-serialisable and survives a round-trip."""
    f = Finding("json_tieout", Status.FLAG, "json:closing_surplus", "note")
    assert json.loads(json.dumps(f.to_dict())) == f.to_dict()


def test_finding_is_frozen():
    """Finding is a frozen dataclass — attributes cannot be reassigned."""
    f = Finding("r", Status.PASS, "-", "m")
    with pytest.raises(Exception):
        f.rule = "other"  # type: ignore[misc]


def test_finding_equality_and_hash():
    """Frozen Findings with identical fields are equal and hashable."""
    a = Finding("r", Status.PASS, "-", "m")
    b = Finding("r", Status.PASS, "-", "m")
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


# --------------------------------------------------------------------------- #
# WorkbookReport.verdict roll-up
# --------------------------------------------------------------------------- #
def test_empty_report_verdict_is_pass():
    """A report with no findings rolls up to PASS."""
    assert WorkbookReport("w").verdict is Verdict.PASS


def test_report_all_pass_is_pass():
    """Only PASS findings => verdict PASS."""
    r = WorkbookReport("w", [Finding("r", Status.PASS, "-", "ok")])
    assert r.verdict is Verdict.PASS


def test_report_flag_only_is_review():
    """A FLAG with no FAIL => verdict REVIEW."""
    r = WorkbookReport(
        "w",
        [Finding("r", Status.PASS, "-", "ok"), Finding("r", Status.FLAG, "-", "soft")],
    )
    assert r.verdict is Verdict.REVIEW


def test_report_any_fail_is_fail():
    """A single FAIL dominates even when FLAGs are present => verdict FAIL."""
    r = WorkbookReport(
        "w",
        [Finding("r", Status.FLAG, "-", "soft"), Finding("r", Status.FAIL, "-", "hard")],
    )
    assert r.verdict is Verdict.FAIL


def test_fail_takes_precedence_over_flag_regardless_of_order():
    """FAIL precedence does not depend on finding order."""
    fail = Finding("r", Status.FAIL, "-", "hard")
    flag = Finding("r", Status.FLAG, "-", "soft")
    assert WorkbookReport("w", [fail, flag]).verdict is Verdict.FAIL
    assert WorkbookReport("w", [flag, fail]).verdict is Verdict.FAIL


# --------------------------------------------------------------------------- #
# WorkbookReport.counts
# --------------------------------------------------------------------------- #
def test_counts_zeroed_for_empty_report():
    """counts() always reports all three buckets, zeroed when empty."""
    assert WorkbookReport("w").counts() == {"PASS": 0, "FAIL": 0, "FLAG": 0}


def test_counts_tally_matches_findings():
    """counts() tallies each status bucket correctly."""
    findings = [
        Finding("r", Status.PASS, "-", "m"),
        Finding("r", Status.PASS, "-", "m"),
        Finding("r", Status.FAIL, "-", "m"),
        Finding("r", Status.FLAG, "-", "m"),
        Finding("r", Status.FLAG, "-", "m"),
        Finding("r", Status.FLAG, "-", "m"),
    ]
    assert WorkbookReport("w", findings).counts() == {"PASS": 2, "FAIL": 1, "FLAG": 3}


def test_counts_sum_equals_number_of_findings():
    """The three bucket counts sum to the total number of findings (invariant)."""
    findings = [
        Finding("r", Status.PASS, "-", "m"),
        Finding("r", Status.FAIL, "-", "m"),
        Finding("r", Status.FLAG, "-", "m"),
        Finding("r", Status.FLAG, "-", "m"),
    ]
    r = WorkbookReport("w", findings)
    assert sum(r.counts().values()) == len(findings)


# --------------------------------------------------------------------------- #
# WorkbookReport.to_dict
# --------------------------------------------------------------------------- #
def test_report_to_dict_shape_and_consistency():
    """to_dict exposes workbook/verdict/counts/findings consistently."""
    findings = [Finding("r", Status.FAIL, "S!A1", "m")]
    r = WorkbookReport("book.xlsx", findings)
    d = r.to_dict()
    assert d["workbook"] == "book.xlsx"
    assert d["verdict"] == "FAIL"
    assert d["counts"] == {"PASS": 0, "FAIL": 1, "FLAG": 0}
    assert d["findings"] == [findings[0].to_dict()]


def test_report_to_dict_round_trips_through_json():
    """The full report dict is JSON-serialisable and stable."""
    r = WorkbookReport(
        "book.xlsx",
        [Finding("r", Status.FLAG, "-", "m"), Finding("r", Status.PASS, "-", "ok")],
    )
    d = r.to_dict()
    assert json.loads(json.dumps(d)) == d


# --------------------------------------------------------------------------- #
# overall_verdict
# --------------------------------------------------------------------------- #
def test_overall_verdict_empty_is_pass():
    """No reports rolls up to PASS."""
    assert overall_verdict([]) is Verdict.PASS


def test_overall_verdict_all_pass():
    """All-PASS reports roll up to PASS."""
    reports = [WorkbookReport("a"), WorkbookReport("b")]
    assert overall_verdict(reports) is Verdict.PASS


def test_overall_verdict_review_when_only_flags():
    """A REVIEW report with no FAIL report rolls up to REVIEW."""
    reports = [
        WorkbookReport("a"),
        WorkbookReport("b", [Finding("r", Status.FLAG, "-", "m")]),
    ]
    assert overall_verdict(reports) is Verdict.REVIEW


def test_overall_verdict_fail_dominates():
    """Any FAIL report makes the whole run FAIL."""
    reports = [
        WorkbookReport("a", [Finding("r", Status.FLAG, "-", "m")]),
        WorkbookReport("b", [Finding("r", Status.FAIL, "-", "m")]),
    ]
    assert overall_verdict(reports) is Verdict.FAIL
