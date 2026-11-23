"""The published artifacts must have a stable shape and stay plain ASCII."""

from __future__ import annotations

import json

from ap_engine.engine import REGISTRY, RULE_FAMILIES, analyze_folder, overall_verdict
from ap_engine.model import DocumentReport, Finding, Status, Verdict
from ap_engine.report import (
    ENGINE_NAME,
    PART_NO,
    build_json_report,
    build_markdown_report,
    family_counts,
    total_counts,
    write_reports,
)

#: Words that must never reach a published artifact.
_FORBIDDEN = ("todo", "fixme", "tbd", "do not ship", "internal only")


def test_json_report_key_order_is_the_contract(corpus_dir) -> None:
    """Literal dict order is the published order; no sort_keys anywhere."""
    payload = build_json_report(analyze_folder(corpus_dir))
    assert list(payload) == [
        "tool",
        "engine",
        "part_no",
        "version",
        "generated_utc",
        "overall_verdict",
        "document_count",
        "counts",
        "family_counts",
        "registry",
        "reports",
    ]
    assert payload["tool"] == "ap_engine"
    assert payload["engine"] == ENGINE_NAME
    assert payload["part_no"] == PART_NO


def test_json_report_registry_matches_the_engine(corpus_dir) -> None:
    payload = build_json_report(analyze_folder(corpus_dir))
    assert payload["registry"] == [rule_id for rule_id, _ in REGISTRY]


def test_json_report_counts_reconcile_to_the_findings(corpus_dir) -> None:
    """The headline tally is a sum of the detail, not a separate number."""
    reports = analyze_folder(corpus_dir)
    payload = build_json_report(reports)
    detail = {"PASS": 0, "FAIL": 0, "FLAG": 0}
    for report in payload["reports"]:
        for finding in report["findings"]:
            detail[finding["status"]] += 1
    assert payload["counts"] == detail
    assert payload["document_count"] == len(reports)
    assert payload["overall_verdict"] == overall_verdict(reports).value


def test_family_counts_partition_the_findings(corpus_dir) -> None:
    """Every finding lands in exactly one family bucket."""
    reports = analyze_folder(corpus_dir)
    per_family = family_counts(reports)
    assert list(per_family) == list(RULE_FAMILIES)
    rolled = {"PASS": 0, "FAIL": 0, "FLAG": 0}
    for bucket in per_family.values():
        for status, count in bucket.items():
            rolled[status] += count
    assert rolled == total_counts(reports)


def test_finding_to_dict_shape() -> None:
    finding = Finding("gate_lien_waiver", Status.FAIL, "doc:X/y", "message text")
    assert finding.to_dict() == {
        "rule": "gate_lien_waiver",
        "status": "FAIL",
        "location": "doc:X/y",
        "message": "message text",
    }


def test_document_report_verdict_precedence() -> None:
    """FAIL beats FLAG beats PASS, and an empty report is PASS."""
    fail = Finding("r", Status.FAIL, "-", "m")
    flag = Finding("r", Status.FLAG, "-", "m")
    ok = Finding("r", Status.PASS, "-", "m")
    assert DocumentReport("d", []).verdict is Verdict.PASS
    assert DocumentReport("d", [ok]).verdict is Verdict.PASS
    assert DocumentReport("d", [ok, flag]).verdict is Verdict.REVIEW
    assert DocumentReport("d", [ok, flag, fail]).verdict is Verdict.FAIL
    assert DocumentReport("d", [fail]).verdict is Verdict.FAIL


def test_rules_fired_preserves_first_seen_order_without_duplicates() -> None:
    findings = [
        Finding("b", Status.FLAG, "-", "m"),
        Finding("a", Status.FAIL, "-", "m"),
        Finding("b", Status.FLAG, "-", "m"),
        Finding("c", Status.PASS, "-", "m"),
    ]
    assert DocumentReport("d", findings).rules_fired() == ["b", "a"]


def test_markdown_is_plain_ascii_and_has_no_leftover_notes(corpus_dir) -> None:
    text = build_markdown_report(analyze_folder(corpus_dir))
    assert all(ord(ch) < 128 for ch in text), "markdown must be plain ASCII"
    low = text.lower()
    for term in _FORBIDDEN:
        assert term not in low, term


def test_markdown_sections_and_tables(corpus_dir) -> None:
    reports = analyze_folder(corpus_dir)
    lines = build_markdown_report(reports).split("\n")
    assert lines[0] == f"# {ENGINE_NAME} Control Report ({PART_NO})"
    assert "## Control families" in lines
    assert "## Document sets" in lines
    assert "## Exceptions" in lines
    assert "## Registered controls" in lines
    # One row per registered control in the closing table.
    for rule_id, _ in REGISTRY:
        assert any(line.startswith(f"| {rule_id} |") for line in lines), rule_id
    # One section per analyzed document set.
    for report in reports:
        assert any(line.startswith(f"### {report.document} ") for line in lines)


def test_markdown_escapes_pipes_in_messages() -> None:
    finding = Finding("r", Status.FAIL, "-", "value a | value b")
    text = build_markdown_report([DocumentReport("d.json", [finding])])
    assert "value a \\| value b" in text


def test_markdown_reports_a_clean_set_without_an_empty_table() -> None:
    text = build_markdown_report([DocumentReport("clean.json", [])])
    assert "All controls held." in text
    assert "| Status | Control |" not in text


def test_write_reports_writes_only_what_is_asked(corpus_dir, tmp_path) -> None:
    reports = analyze_folder(corpus_dir)
    assert write_reports(reports) == []

    json_path = tmp_path / "ap_report.json"
    md_path = tmp_path / "ap_report.md"
    written = write_reports(reports, json_path=json_path, md_path=md_path)
    assert written == [json_path, md_path]

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["document_count"] == len(reports)
    assert md_path.read_text(encoding="utf-8").startswith("# ")
    # Two-space indent, the byte-stable serialisation contract.
    assert '\n  "tool": "ap_engine",' in json_path.read_text(encoding="utf-8")


def test_json_report_is_serialisable_and_ascii_safe(corpus_dir) -> None:
    payload = build_json_report(analyze_folder(corpus_dir))
    text = json.dumps(payload, indent=2)
    assert all(ord(ch) < 128 for ch in text)
    assert json.loads(text) == payload
