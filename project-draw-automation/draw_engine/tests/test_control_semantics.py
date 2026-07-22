"""Targeted tests for the controls whose logic is worth pinning down directly.

The planted-defect corpus proves each control fires. These tests prove the
*boundaries* are where they should be -- that a rule passes right up to its limit
and fails one cent past it, and that the conservative choices really are
conservative.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from draw_engine.engine import analyze_document
from draw_engine.generate import baseline, d
from draw_engine.model import (
    DOC_COST_DETAIL,
    DOC_CYCLE_CALENDAR,
    DOC_DRAW_REQUEST,
    DOC_JC_RECONCILIATION,
    Status,
)


def _write(tmp_path: Path, pkg: dict[str, Any], name: str = "case") -> Path:
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(pkg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def _doc(pkg: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(x for x in pkg["documents"] if x["doc_type"] == doc_type)


def _line(pkg: dict[str, Any], code: str) -> dict[str, Any]:
    return next(l for l in _doc(pkg, DOC_DRAW_REQUEST)["lines"] if l["code"] == code)


def _fired(path: Path, rule: str) -> bool:
    return rule in analyze_document(path).rules_fired()


@pytest.fixture()
def pkg() -> dict[str, Any]:
    return copy.deepcopy(baseline("Alderpoint Terraces"))


# --------------------------------------------------------------------------- #
# The reconciliation identity is exact -- no tolerance band
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta", [1, -1, 100, -100])
def test_recon_identity_has_no_tolerance(
    pkg: dict[str, Any], tmp_path: Path, delta: int
) -> None:
    """One cent of drift is a failure. A control that tolerates a penny has not
    proved the draw ties."""
    _doc(pkg, DOC_JC_RECONCILIATION)["totals"][
        "costs_to_date_net_retention_cents"] += delta
    assert _fired(_write(tmp_path, pkg), "recon_draws_tie_costs")


def test_recon_identity_holds_at_zero(pkg: dict[str, Any], tmp_path: Path) -> None:
    assert not _fired(_write(tmp_path, pkg), "recon_draws_tie_costs")


# --------------------------------------------------------------------------- #
# Contingency ceiling: passes at the limit, fails one cent past it
# --------------------------------------------------------------------------- #
def test_contingency_passes_exactly_at_the_ceiling(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    """Hard progress is 40.00% of a 500,000 contingency == a 200,000 ceiling."""
    line = _line(pkg, "03-900")
    line["total_disbursed_to_date_cents"] = d(200_000)
    line["previous_applications_cents"] = (
        d(200_000) - line["request_this_period_cents"])
    line["remaining_funds_cents"] = line["revised_budget_cents"] - d(200_000)
    assert not _fired(_write(tmp_path, pkg), "cont_within_percent_complete")


def test_contingency_fails_one_cent_past_the_ceiling(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    line = _line(pkg, "03-900")
    line["total_disbursed_to_date_cents"] = d(200_000) + 1
    line["previous_applications_cents"] = (
        d(200_000) + 1 - line["request_this_period_cents"])
    line["remaining_funds_cents"] = line["revised_budget_cents"] - d(200_000) - 1
    assert _fired(_write(tmp_path, pkg), "cont_within_percent_complete")


def test_contingency_ceiling_excludes_itself_from_progress(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    """Drawing contingency must not raise the progress that authorises it.

    If the contingency line counted toward its own class's percent complete, a
    project could bootstrap entitlement: spend contingency, measure higher
    progress, become entitled to spend more. The denominator is deliberately the
    productive lines only.
    """
    before = _line(pkg, "03-900")["total_disbursed_to_date_cents"]
    # Push the contingency draw right to the ceiling; it must still pass, and
    # would *not* if its own spend inflated the measured progress.
    line = _line(pkg, "03-900")
    line["total_disbursed_to_date_cents"] = d(200_000)
    line["previous_applications_cents"] = d(200_000) - line["request_this_period_cents"]
    line["remaining_funds_cents"] = line["revised_budget_cents"] - d(200_000)
    assert not _fired(_write(tmp_path, pkg), "cont_within_percent_complete")
    assert before < d(200_000)  # the baseline really was below the ceiling


# --------------------------------------------------------------------------- #
# Cutoff boundaries
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("day,expected_fire", [("2027-04-01", False),
                                               ("2027-04-30", False),
                                               ("2027-03-31", True),
                                               ("2027-05-01", True)])
def test_period_boundaries_are_inclusive(
    pkg: dict[str, Any], tmp_path: Path, day: str, expected_fire: bool
) -> None:
    """The first and last day of the month are inside the period."""
    _doc(pkg, DOC_COST_DETAIL)["transactions"][0]["accounting_date"] = day
    assert _fired(_write(tmp_path, pkg), "cut_costs_inside_period") is expected_fire


@pytest.mark.parametrize("posted,expected_fire", [("2027-05-03", False),
                                                  ("2027-05-04", True)])
def test_posting_deadline_is_inclusive(
    pkg: dict[str, Any], tmp_path: Path, posted: str, expected_fire: bool
) -> None:
    """Posting *on* the deadline is in time; the day after is not."""
    _doc(pkg, DOC_COST_DETAIL)["transactions"][0]["posted_date"] = posted
    assert _fired(_write(tmp_path, pkg), "cut_posted_by_deadline") is expected_fire


@pytest.mark.parametrize("days,expected_fire", [(2, False), (3, True)])
def test_approval_sla_boundary(
    pkg: dict[str, Any], tmp_path: Path, days: int, expected_fire: bool
) -> None:
    txn = _doc(pkg, DOC_COST_DETAIL)["transactions"][0]
    txn["approval_notice_date"] = "2027-04-06"
    txn["approval_completed_date"] = f"2027-04-{6 + days:02d}"
    assert _fired(_write(tmp_path, pkg), "cut_approvals_within_sla") is expected_fire


# --------------------------------------------------------------------------- #
# Missing evidence is never a passing control
# --------------------------------------------------------------------------- #
def test_unreadable_posting_deadline_fails_rather_than_passes(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    """With no deadline, no cost can be *shown* to have met it.

    The tempting alternative -- skip the rule when the deadline is missing --
    would turn a missing control parameter into a clean bill of health.
    """
    _doc(pkg, DOC_CYCLE_CALENDAR)["posting_deadline"] = None
    assert _fired(_write(tmp_path, pkg), "cut_posted_by_deadline")


def test_missing_signature_fails(pkg: dict[str, Any], tmp_path: Path) -> None:
    _doc(pkg, DOC_DRAW_REQUEST)["signed_by"] = None
    assert _fired(_write(tmp_path, pkg), "doc_signed")


def test_signature_without_a_date_fails(pkg: dict[str, Any], tmp_path: Path) -> None:
    """An undated signature cannot be tied to the package it supposedly approves."""
    _doc(pkg, DOC_DRAW_REQUEST)["signature_date"] = None
    assert _fired(_write(tmp_path, pkg), "doc_signed")


# --------------------------------------------------------------------------- #
# Retention sign conventions
# --------------------------------------------------------------------------- #
def test_zero_retention_is_not_a_sign_violation(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    """Zero is neither withheld nor released; it must not trip the sign rule."""
    for cat in _doc(pkg, DOC_JC_RECONCILIATION)["categories"]:
        cat["retention_withheld_cents"] = 0
    # Totals must follow, or the footing rule fires instead of the sign rule.
    _doc(pkg, DOC_JC_RECONCILIATION)["totals"]["retention_withheld_cents"] = 0
    assert not _fired(_write(tmp_path, pkg), "recon_retention_sign")


def test_negative_release_is_rejected(pkg: dict[str, Any], tmp_path: Path) -> None:
    """A release moves value *into* the current period, so it is positive."""
    _doc(pkg, DOC_JC_RECONCILIATION)["categories"][0][
        "retention_billed_current_cents"] = d(-5_000)
    assert _fired(_write(tmp_path, pkg), "recon_retention_release_moved")


# --------------------------------------------------------------------------- #
# Follow-up only when actually late
# --------------------------------------------------------------------------- #
def test_no_followup_required_when_funded_on_time(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    """A package funded inside the window is never asked to evidence a chase."""
    cal = _doc(pkg, DOC_CYCLE_CALENDAR)
    assert cal["followup_logged"] is False
    assert not _fired(_write(tmp_path, pkg), "fund_overdue_followed_up")


def test_followup_required_when_unfunded(pkg: dict[str, Any], tmp_path: Path) -> None:
    _doc(pkg, DOC_CYCLE_CALENDAR)["funded"] = None
    assert _fired(_write(tmp_path, pkg), "fund_overdue_followed_up")


def test_logged_followup_satisfies_an_overdue_draw(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    cal = _doc(pkg, DOC_CYCLE_CALENDAR)
    cal["funded"] = None
    cal["followup_logged"] = True
    assert not _fired(_write(tmp_path, pkg), "fund_overdue_followed_up")


# --------------------------------------------------------------------------- #
# Accrual policy exemption
# --------------------------------------------------------------------------- #
def test_immaterial_accrual_is_exempt_when_payment_is_immediate(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    """The policy permits a small accrual for something that must be paid now."""
    assert not _fired(_write(tmp_path, pkg), "acc_only_material")


def test_immaterial_accrual_without_the_exemption_flags(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    for txn in _doc(pkg, DOC_COST_DETAIL)["transactions"]:
        if txn["is_accrual"]:
            txn["payment_required_immediately"] = False
    assert _fired(_write(tmp_path, pkg), "acc_only_material")


# --------------------------------------------------------------------------- #
# A category present in cost detail but absent from the form
# --------------------------------------------------------------------------- #
def test_orphan_cost_category_is_caught(
    pkg: dict[str, Any], tmp_path: Path
) -> None:
    """Cost billed under a code that appears on no form line is unbillable.

    Without this branch the tie-out would compare only the codes the form
    happens to mention, and an entire category of cost could be requested with
    nothing on the form to authorise it.
    """
    detail = _doc(pkg, DOC_COST_DETAIL)
    detail["transactions"].append({
        "txn_id": "T-9999", "code": "99-999", "cost_class": "hard",
        "amount_cents": d(5_000), "vendor": "Ghost Cost Co",
        "invoice_number": "INV-9999",
        "accounting_date": "2027-04-15", "posted_date": "2027-05-02",
        "approval_notice_date": "2027-04-15",
        "approval_completed_date": "2027-04-16",
        "is_accrual": False, "payment_required_immediately": False,
    })
    report = analyze_document(_write(tmp_path, pkg))
    messages = [
        f.message for f in report.findings
        if f.rule == "form_request_ties_cost_detail" and f.status is not Status.PASS
    ]
    assert any("99-999" in m and "no line" in m for m in messages), messages
