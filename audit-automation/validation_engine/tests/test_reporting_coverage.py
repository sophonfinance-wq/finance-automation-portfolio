"""Coverage for the report builders (build_json_report / build_markdown_report).

These exercise the rendering layer directly with hand-built WorkbookReports so
the assertions do not depend on the generated corpus and can fail precisely if
the rendering regresses (escaping, table rows, all-pass shortcut, JSON shape).
"""

from __future__ import annotations

import json

from validation_engine.engine import (
    REGISTRY,
    Finding,
    Status,
    Verdict,
    WorkbookReport,
    build_json_report,
    build_markdown_report,
)


def _mixed_reports():
    return [
        WorkbookReport(
            "fail.xlsx",
            [Finding("expected_formula", Status.FAIL, "Surplus-Detail!B6", "bad")],
        ),
        WorkbookReport(
            "flag.xlsx",
            [Finding("forbidden_text", Status.FLAG, "Summary!D2", "todo note")],
        ),
        WorkbookReport(
            "pass.xlsx",
            [Finding("debit_credit_balance", Status.PASS, "-", "ties out")],
        ),
    ]


# --------------------------------------------------------------------------- #
# build_json_report
# --------------------------------------------------------------------------- #
def test_json_report_top_level_keys():
    """The JSON report carries every documented top-level key."""
    payload = build_json_report(_mixed_reports())
    assert {
        "tool",
        "version",
        "generated_utc",
        "overall_verdict",
        "workbook_count",
        "registry",
        "reports",
    } <= set(payload)


def test_json_report_workbook_count_and_registry():
    """workbook_count and registry reflect the inputs/engine registry."""
    reports = _mixed_reports()
    payload = build_json_report(reports)
    assert payload["workbook_count"] == len(reports)
    assert payload["registry"] == [rid for rid, _ in REGISTRY]
    assert payload["version"] == "1.0.0"


def test_json_report_overall_verdict_is_fail_with_a_fail():
    """A FAIL report drives overall_verdict to FAIL."""
    payload = build_json_report(_mixed_reports())
    assert payload["overall_verdict"] == Verdict.FAIL.value


def test_json_report_overall_verdict_review_when_only_flags():
    """Flag-only inputs => overall verdict REVIEW."""
    reports = [WorkbookReport("a", [Finding("r", Status.FLAG, "-", "m")])]
    assert build_json_report(reports)["overall_verdict"] == "REVIEW"


def test_json_report_round_trips_through_json():
    """The JSON report is serialisable and stable through a round-trip."""
    payload = build_json_report(_mixed_reports())
    assert json.loads(json.dumps(payload)) == payload


def test_json_report_generated_utc_is_iso_z():
    """generated_utc is an ISO-8601 UTC stamp ending in Z."""
    payload = build_json_report(_mixed_reports())
    stamp = payload["generated_utc"]
    assert stamp.endswith("Z") and "T" in stamp


def test_json_report_empty_input():
    """An empty run yields zero workbooks and overall PASS."""
    payload = build_json_report([])
    assert payload["workbook_count"] == 0
    assert payload["reports"] == []
    assert payload["overall_verdict"] == "PASS"


# --------------------------------------------------------------------------- #
# build_markdown_report
# --------------------------------------------------------------------------- #
def test_markdown_starts_with_title():
    """The markdown report begins with the report title."""
    md = build_markdown_report(_mixed_reports())
    assert md.startswith("# Validation Report")


def test_markdown_has_overall_verdict_line():
    """The overall verdict line is rendered."""
    md = build_markdown_report(_mixed_reports())
    assert "**Overall verdict:** FAIL" in md


def test_markdown_summary_table_header_present():
    """The per-workbook summary table header is present."""
    md = build_markdown_report(_mixed_reports())
    assert "| Workbook | Verdict | PASS | FAIL | FLAG |" in md


def test_markdown_has_section_per_workbook():
    """Each workbook gets its own ## section."""
    reports = _mixed_reports()
    md = build_markdown_report(reports)
    for r in reports:
        assert f"## {r.workbook}" in md


def test_markdown_all_pass_workbook_shows_shortcut():
    """A workbook with only PASS findings renders the 'All checks passed.' line."""
    md = build_markdown_report(
        [WorkbookReport("ok.xlsx", [Finding("r", Status.PASS, "-", "fine")])]
    )
    assert "All checks passed." in md


def test_markdown_escapes_pipe_in_message():
    """A pipe in a finding message is escaped so the table is not broken."""
    md = build_markdown_report(
        [WorkbookReport("w.xlsx", [Finding("r", Status.FAIL, "S!A1", "a|b|c")])]
    )
    assert "a\\|b\\|c" in md
    assert "a|b|c |" not in md  # unescaped form must not leak through


def test_markdown_actionable_table_lists_non_pass_only():
    """The per-workbook detail table lists FAIL/FLAG rows but not PASS rows."""
    md = build_markdown_report(
        [
            WorkbookReport(
                "w.xlsx",
                [
                    Finding("debit_credit_balance", Status.PASS, "-", "ties"),
                    Finding("expected_formula", Status.FAIL, "S!B6", "hardcoded"),
                ],
            )
        ]
    )
    assert "expected_formula" in md
    # The FAIL finding appears as a detail row; the PASS finding does not.
    assert "| FAIL | expected_formula |" in md
    assert "debit_credit_balance" not in md.split("## w.xlsx")[1]


def test_markdown_workbook_count_line():
    """The 'Workbooks validated' count reflects the inputs."""
    reports = _mixed_reports()
    md = build_markdown_report(reports)
    assert f"Workbooks validated: {len(reports)}" in md
