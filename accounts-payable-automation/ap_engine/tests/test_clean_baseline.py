"""The clean baseline document set must satisfy every registered control.

A control engine that flags a clean run is worse than no engine: reviewers stop
reading it. These tests pin the false-positive surface, including the four
benign cases the design calls out explicitly.
"""

from __future__ import annotations

from ap_engine.engine import REGISTRY, analyze_document
from ap_engine.model import (
    DOC_COMMITMENT_REGISTER,
    DOC_INFORMATION_REPORTING,
    DOC_INVOICE_POSTING,
    DOC_TYPES,
    DOC_WORKFLOW_MATRIX,
    DocumentReport,
    Status,
    Verdict,
)


def _clean_path(corpus_dir):
    matches = sorted(corpus_dir.glob("clean__*.json"))
    assert len(matches) == 1, "the corpus must carry exactly one clean baseline"
    return matches[0]


def test_clean_baseline_verdict_is_pass(clean_report: DocumentReport) -> None:
    """No FAIL, no FLAG, verdict PASS."""
    counts = clean_report.counts()
    assert counts["FAIL"] == 0, clean_report.rules_fired()
    assert counts["FLAG"] == 0, clean_report.rules_fired()
    assert clean_report.verdict is Verdict.PASS
    assert clean_report.rules_fired() == []


def test_every_registered_control_reports_a_pass(clean_report: DocumentReport) -> None:
    """Each rule must actually run on the baseline, not silently no-op.

    A rule that returns ``[]`` because its document type is missing would look
    green while testing nothing; requiring a PASS finding per rule closes that.
    """
    passed = {f.rule for f in clean_report.findings if f.status is Status.PASS}
    registered = {rule_id for rule_id, _ in REGISTRY}
    assert passed == registered, registered - passed


def test_baseline_carries_every_document_type(corpus_dir) -> None:
    """The baseline exercises all five source artifact types."""
    import json

    data = json.loads(_clean_path(corpus_dir).read_text(encoding="utf-8"))
    present = [doc["doc_type"] for doc in data["documents"]]
    assert present == list(DOC_TYPES)


def test_benign_jobcost_notice_is_not_a_failure(corpus_dir) -> None:
    """A "job-cost entries not created" notice is informational, never a FAIL.

    This is the distinction the design flags as the most important one in the
    posting family: the baseline carries the notice and must still pass.
    """
    import json

    path = _clean_path(corpus_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    posting = next(d for d in data["documents"] if d["doc_type"] == DOC_INVOICE_POSTING)
    assert posting["notices"], "the baseline must carry a benign notice to test against"
    assert any("job-cost entries not created" in n for n in posting["notices"])
    assert posting["error_markers"] == []

    report = analyze_document(path)
    marker_findings = [f for f in report.findings if f.rule == "post_no_error_marker"]
    assert len(marker_findings) == 1
    assert marker_findings[0].status is Status.PASS
    assert "benign" in marker_findings[0].message


def test_ledger_only_invoices_do_not_trip_actually_posted(corpus_dir) -> None:
    """Zero job-cost entries is legitimate and must not fail the posted check."""
    import json

    path = _clean_path(corpus_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    posting = next(d for d in data["documents"] if d["doc_type"] == DOC_INVOICE_POSTING)
    assert posting["posted_counts"]["job_cost_entries"] < posting["posted_counts"]["invoices"]

    report = analyze_document(path)
    fired = [
        f
        for f in report.findings
        if f.rule == "post_actually_posted" and f.status is not Status.PASS
    ]
    assert fired == []


def test_inactive_job_without_a_workflow_is_not_a_failure(corpus_dir) -> None:
    """A closed job legitimately routes nowhere."""
    import json

    path = _clean_path(corpus_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    routing = next(d for d in data["documents"] if d["doc_type"] == DOC_WORKFLOW_MATRIX)
    inactive = [j for j in routing["jobs"] if not j["active"]]
    assert inactive and inactive[0]["workflows"] == []

    report = analyze_document(path)
    fired = [
        f
        for f in report.findings
        if f.rule == "route_every_job_mapped" and f.status is not Status.PASS
    ]
    assert fired == []


def test_below_threshold_vendor_needs_no_evaluation(corpus_dir) -> None:
    """The coverage control applies only above the reporting threshold."""
    import json

    path = _clean_path(corpus_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    register = next(
        d for d in data["documents"] if d["doc_type"] == DOC_INFORMATION_REPORTING
    )
    small = [v for v in register["vendors"] if not v["evaluated"]]
    assert small, "the baseline must carry an unevaluated small vendor"
    assert all(v["ytd_paid_cents"] < register["threshold_cents"] for v in small)

    report = analyze_document(path)
    fired = [
        f
        for f in report.findings
        if f.rule == "ir_threshold_coverage" and f.status is not Status.PASS
    ]
    assert fired == []


def test_single_line_purchase_order_is_not_a_lump_sum_failure(corpus_dir) -> None:
    """The lump-sum control applies to subcontracts, not purchase orders."""
    import json

    path = _clean_path(corpus_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    register = next(
        d for d in data["documents"] if d["doc_type"] == DOC_COMMITMENT_REGISTER
    )
    orders = [c for c in register["commitments"] if c["contract_type"] == "purchase_order"]
    assert orders and len(orders[0]["schedule_of_values"]) == 1

    report = analyze_document(path)
    fired = [
        f
        for f in report.findings
        if f.rule == "cmt_sov_not_lump_sum" and f.status is not Status.PASS
    ]
    assert fired == []


def test_baseline_amounts_are_all_integer_cents(corpus_dir) -> None:
    """No float survives anywhere in a generated document set."""
    import json

    data = json.loads(_clean_path(corpus_dir).read_text(encoding="utf-8"))
    floats: list[str] = []

    def walk(prefix: str, node: object) -> None:
        if isinstance(node, dict):
            for key in sorted(node):
                walk(f"{prefix}.{key}" if prefix else str(key), node[key])
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(f"{prefix}[{index}]", item)
        elif isinstance(node, float):
            floats.append(prefix)

    walk("", data)
    assert floats == []
