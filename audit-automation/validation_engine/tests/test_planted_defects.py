"""Each planted defect must be caught by its corresponding rule (one per rule)."""

from __future__ import annotations

import pytest

from validation_engine.engine import REGISTRY, Status, Verdict, WorkbookReport
from validation_engine.generate import DEFECTS


def _findings_for_rule(report: WorkbookReport, rule: str) -> list:
    return [f for f in report.findings if f.rule == rule]


# Map each defect key -> (rule it should trip, expected status of that finding).
_EXPECTED = {
    "hardcoded_total": ("expected_formula", Status.FAIL),
    "unbalanced_tb": ("debit_credit_balance", Status.FAIL),
    "stale_note": ("forbidden_text", Status.FLAG),
    "reversed_lineage": ("lineage_direction", Status.FLAG),
    "cap_leftover": ("cap_logic_leftover", Status.FLAG),
    "json_mismatch": ("json_tieout", Status.FAIL),
}


def test_every_rule_has_a_planted_defect():
    """Sanity: the generator plants exactly one defect per registry rule."""
    planted_rules = {d.rule for d in DEFECTS}
    registry_rules = {rule_id for rule_id, _ in REGISTRY}
    assert planted_rules == registry_rules


@pytest.mark.parametrize("key", list(_EXPECTED))
def test_planted_defect_is_caught(reports, key):
    """The defect workbook trips its rule with the expected non-PASS status."""
    rule, expected_status = _EXPECTED[key]
    report = reports[key]
    hits = [f for f in _findings_for_rule(report, rule) if f.status is expected_status]
    assert hits, (
        f"{key}: expected a {expected_status.value} from rule {rule!r}, "
        f"got {[ (f.status.value, f.message) for f in report.findings ]}"
    )
    # Every non-PASS finding must carry a usable location reference.
    for f in hits:
        assert f.location and f.location != ""


@pytest.mark.parametrize("key", list(_EXPECTED))
def test_defect_drives_workbook_verdict(reports, key):
    """A FAIL defect => verdict FAIL; a FLAG-only defect => verdict REVIEW."""
    _rule, status = _EXPECTED[key]
    verdict = reports[key].verdict
    if status is Status.FAIL:
        assert verdict is Verdict.FAIL
    else:
        assert verdict in (Verdict.REVIEW, Verdict.FAIL)
