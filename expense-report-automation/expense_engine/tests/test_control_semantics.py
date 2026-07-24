"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one day or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The reconciliation and policy cases carry the most weight. A report that foots to
the statement total can still put a charge's penny on the wrong line; a charge one
cent over the limit is a control break and one cent under it is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_engine.engine import (
    SEVERITY,
    check_card_last4_valid,
    check_cod_disallowed_category,
    check_dup_no_duplicate_charge,
    check_pol_approver_distinct,
    check_pol_per_charge_limit,
    check_pol_submitted_within_window,
    check_rec_every_charge_reported,
    check_rec_report_total_ties,
    check_stmt_last4_matches_card,
)
from expense_engine.generate import PROGRAMMES, baseline
from expense_engine.model import (
    DOC_CARDHOLDER_REGISTER,
    DOC_EXPENSE_REPORT_REGISTER,
    DOC_POLICY,
    DOC_STATEMENT_REGISTER,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PROGRAMMES[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _cardholder(payload: dict, cid: str) -> dict:
    return next(
        c for c in _doc(payload, DOC_CARDHOLDER_REGISTER)["cardholders"]
        if c["cardholder_id"] == cid
    )


def _statement(payload: dict, statement_id: str) -> dict:
    return next(
        s for s in _doc(payload, DOC_STATEMENT_REGISTER)["statements"]
        if s["statement_id"] == statement_id
    )


def _report(payload: dict, report_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_EXPENSE_REPORT_REGISTER)["reports"]
        if r["report_id"] == report_id
    )


def _stmt_line(payload: dict, line_id: str) -> dict:
    for stmt in _doc(payload, DOC_STATEMENT_REGISTER)["statements"]:
        for line in stmt["lines"]:
            if line["line_id"] == line_id:
                return line
    raise KeyError(line_id)


def _report_line(payload: dict, statement_line_id: str) -> dict:
    for report in _doc(payload, DOC_EXPENSE_REPORT_REGISTER)["reports"]:
        for line in report["lines"]:
            if line["statement_line_id"] == statement_line_id:
                return line
    raise KeyError(statement_line_id)


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# pol_per_charge_limit -- one cent over the limit is a break, one under is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_per_charge_limit_is_a_hard_edge(delta: int, should_fail: bool) -> None:
    payload = _payload()
    limit = _doc(payload, DOC_POLICY)["per_charge_limit_cents"]
    _stmt_line(payload, "L-0101")["amount_cents"] = limit + delta
    assert bool(_fired(check_pol_per_charge_limit(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# pol_submitted_within_window -- the window is measured to the day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "submitted, should_flag",
    [("2029-10-14", False), ("2029-10-15", True)],
)
def test_submission_window_is_measured_to_the_day(submitted: str, should_flag: bool) -> None:
    """The statement is dated 2029-09-30; the window is 14 days.

    A report filed on day 14 is inside it; on day 15 it is late and flags.
    """
    payload = _payload()
    _report(payload, "EXP-2909-01")["submitted_date"] = submitted
    fired = _fired(check_pol_submitted_within_window(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# rec_every_charge_reported -- the report line ties its charge to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_each_charge_reconciles_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _report_line(payload, "L-0101")["amount_cents"] += delta
    assert bool(_fired(check_rec_every_charge_reported(_ctx(payload)))) is should_fail


def test_a_dropped_report_line_is_an_unreported_charge() -> None:
    """Removing the report line for a real charge fails the line-by-line control."""
    payload = _payload()
    report = _report(payload, "EXP-2909-01")
    report["lines"] = [ln for ln in report["lines"] if ln["statement_line_id"] != "L-0104"]
    assert _fired(check_rec_every_charge_reported(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rec_report_total_ties -- the whole report ties the whole statement
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_report_total_ties_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _report_line(payload, "L-0301")["amount_cents"] += delta
    assert bool(_fired(check_rec_report_total_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# card_last4_valid -- exactly four digits, nothing else
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "last4, should_fail",
    [("4417", False), ("441", True), ("44170", True), ("44A7", True), ("", True)],
)
def test_card_last4_must_be_four_digits(last4: str, should_fail: bool) -> None:
    payload = _payload()
    _cardholder(payload, "CH-01")["card_last4"] = last4
    # An empty string is absence, which card_required_fields owns, so it should
    # not itself produce a card_last4_valid finding.
    fired = _fired(check_card_last4_valid(_ctx(payload)))
    if last4 == "":
        assert not fired
    else:
        assert bool(fired) is should_fail


# --------------------------------------------------------------------------- #
# stmt_last4_matches_card -- the charge carries its own card's last four
# --------------------------------------------------------------------------- #
def test_a_mismatched_last_four_fails() -> None:
    payload = _payload()
    assert not _fired(check_stmt_last4_matches_card(_ctx(payload)))
    _stmt_line(payload, "L-0102")["last4"] = "0000"
    assert _fired(check_stmt_last4_matches_card(_ctx(payload)))


# --------------------------------------------------------------------------- #
# cod_disallowed_category -- a review flag, not a hard failure
# --------------------------------------------------------------------------- #
def test_a_disallowed_category_flags_for_review() -> None:
    payload = _payload()
    assert not _fired(check_cod_disallowed_category(_ctx(payload)))
    _stmt_line(payload, "L-0303")["category"] = "gambling"
    fired = _fired(check_cod_disallowed_category(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# pol_approver_distinct -- self-approval removes the second person
# --------------------------------------------------------------------------- #
def test_self_approval_fails() -> None:
    payload = _payload()
    assert not _fired(check_pol_approver_distinct(_ctx(payload)))
    report = _report(payload, "EXP-2909-03")
    report["approver"] = _cardholder(payload, "CH-03")["name"]
    assert _fired(check_pol_approver_distinct(_ctx(payload)))


# --------------------------------------------------------------------------- #
# dup_no_duplicate_charge -- same day, merchant, amount and card
# --------------------------------------------------------------------------- #
def test_a_duplicate_charge_is_caught() -> None:
    payload = _payload()
    assert not _fired(check_dup_no_duplicate_charge(_ctx(payload)))
    stmt = _statement(payload, "STMT-2909-01")
    dup = dict(next(ln for ln in stmt["lines"] if ln["line_id"] == "L-0101"))
    dup["line_id"] = "L-0105"
    stmt["lines"].append(dup)
    assert _fired(check_dup_no_duplicate_charge(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "card_required_fields": Status.FAIL,
    "card_id_unique": Status.FAIL,
    "card_last4_valid": Status.FAIL,
    "card_home_entity_known": Status.FAIL,
    "stmt_required_fields": Status.FAIL,
    "stmt_line_unique": Status.FAIL,
    "stmt_amounts_integer": Status.FAIL,
    "stmt_last4_matches_card": Status.FAIL,
    "rpt_required_fields": Status.FAIL,
    "rpt_receipt_on_file": Status.FAIL,
    "rpt_purpose_present": Status.FAIL,
    "rec_every_charge_reported": Status.FAIL,
    "rec_no_orphan_report_line": Status.FAIL,
    "rec_report_total_ties": Status.FAIL,
    "rec_gl_ties_reports": Status.FAIL,
    "cod_gl_valid": Status.FAIL,
    "cod_project_exists": Status.FAIL,
    "cod_disallowed_category": Status.FLAG,
    "pol_submitted_within_window": Status.FLAG,
    "pol_per_charge_limit": Status.FAIL,
    "pol_approver_distinct": Status.FAIL,
    "dup_no_duplicate_charge": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {
        "set", "card", "stmt", "rpt", "rec", "cod", "pol", "dup"
    }
