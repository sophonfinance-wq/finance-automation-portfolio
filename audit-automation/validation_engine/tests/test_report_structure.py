"""Report structure (JSON + markdown) and overall verdict must be well-formed."""

from __future__ import annotations

import json

from validation_engine.engine import (
    REGISTRY,
    Verdict,
    build_json_report,
    build_markdown_report,
    overall_verdict,
    validate_folder,
)


def test_json_report_shape(corpus_dir):
    """JSON report carries the expected top-level keys and per-finding fields."""
    reports = validate_folder(corpus_dir)
    payload = build_json_report(reports)

    for key in (
        "tool",
        "version",
        "generated_utc",
        "overall_verdict",
        "workbook_count",
        "registry",
        "reports",
    ):
        assert key in payload, f"missing top-level key: {key}"

    assert payload["tool"] == "validation_engine"
    assert payload["workbook_count"] == len(reports)
    assert payload["registry"] == [rule_id for rule_id, _ in REGISTRY]
    assert payload["overall_verdict"] in {v.value for v in Verdict}

    # Must round-trip through JSON unchanged.
    assert json.loads(json.dumps(payload)) == payload

    for rep in payload["reports"]:
        assert {"workbook", "verdict", "counts", "findings"} <= set(rep)
        assert set(rep["counts"]) == {"PASS", "FAIL", "FLAG"}
        for f in rep["findings"]:
            assert {"rule", "status", "location", "message"} == set(f)
            assert f["status"] in {"PASS", "FAIL", "FLAG"}


def test_markdown_report_shape(corpus_dir):
    """Markdown report has a title, verdict line, summary table, per-wb sections."""
    reports = validate_folder(corpus_dir)
    md = build_markdown_report(reports)

    assert md.startswith("# Validation Report")
    assert "**Overall verdict:**" in md
    assert "| Workbook | Verdict | PASS | FAIL | FLAG |" in md
    for rep in reports:
        assert f"## {rep.workbook}" in md


def test_overall_verdict_is_fail_for_mixed_corpus(corpus_dir):
    """The generated corpus contains FAIL defects, so overall must be FAIL."""
    reports = validate_folder(corpus_dir)
    assert overall_verdict(reports) is Verdict.FAIL


def test_registry_is_nonempty_and_unique():
    """Registry rule ids are unique and non-empty."""
    ids = [rule_id for rule_id, _ in REGISTRY]
    assert ids
    assert len(ids) == len(set(ids))
