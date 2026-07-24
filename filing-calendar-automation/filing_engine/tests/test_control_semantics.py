"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a day early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The overdue, late-filing and due-date cases carry the most weight. A return filed
exactly on the deadline is on time and a day past it is late; an obligation
unfiled with its deadline on the review date is overdue and a day out is still
open; a due date met to the day re-derives and a day off does not.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from filing_engine.engine import (
    SEVERITY,
    check_cnt_final_not_recurring,
    check_due_extended_matches,
    check_due_original_matches,
    check_ext_applicable_overdue,
    check_ext_due_soon,
    check_ext_filed_on_time,
    check_ext_flag_valid,
    check_pay_fixed_amount,
    check_rpt_counts_tie,
    check_rpt_status_recomputes,
    check_rpt_watchlist_ties,
    check_wfl_actual_slippage,
    check_wfl_goal_monotonic,
)
from filing_engine.generate import AS_OF, DUE_LEAD_DAYS, PORTFOLIOS, baseline
from filing_engine.model import (
    DOC_DUE_WATCHLIST,
    DOC_OBLIGATION_REGISTER,
    DOC_PRIOR_YEAR_REGISTER,
    DOC_STATUS_SUMMARY,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _obligation(payload: dict, obligation_id: str) -> dict:
    return next(
        o for o in _doc(payload, DOC_OBLIGATION_REGISTER)["obligations"]
        if o["obligation_id"] == obligation_id
    )


def _summary_row(payload: dict, obligation_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_STATUS_SUMMARY)["obligations"]
        if r["obligation_id"] == obligation_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# ext_filed_on_time -- on or before the deadline, not a day past it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(-1, False), (0, False), (1, True)])
def test_filed_on_the_deadline(offset: int, should_fail: bool) -> None:
    """A return filed exactly on the applicable due date is on time; a day later
    is late. OB-1004's original due is 2028-09-15 and it filed no extension."""
    payload = _payload()
    due = date.fromisoformat(_obligation(payload, "OB-1004")["original_due"])
    _obligation(payload, "OB-1004")["return_filed"] = (due + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_ext_filed_on_time(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ext_applicable_overdue -- overdue on the review date, not the day after
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(0, True), (1, False)])
def test_overdue_on_the_review_date(offset: int, should_fail: bool) -> None:
    """An unfiled obligation whose deadline falls on ``as_of`` is overdue; one day
    out is still open."""
    payload = _payload()
    obligation = _obligation(payload, "OB-1004")
    obligation["return_filed"] = None
    obligation["original_due"] = (_as_of() + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_ext_applicable_overdue(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ext_due_soon -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset, should_flag", [(DUE_LEAD_DAYS, True), (DUE_LEAD_DAYS + 1, False)]
)
def test_due_window_edge(offset: int, should_flag: bool) -> None:
    """A deadline exactly ``lead_days`` out is inside the window; a day past it is
    not."""
    payload = _payload()
    obligation = _obligation(payload, "OB-1004")
    obligation["return_filed"] = None
    obligation["original_due"] = (_as_of() + timedelta(days=offset)).isoformat()
    fired = _fired(check_ext_due_soon(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_due_window_is_clean_far_out() -> None:
    """The baseline obligations fall due well beyond the window and raise no flag."""
    assert not _fired(check_ext_due_soon(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# pay_fixed_amount -- the fixed amount is met at the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_fixed_amount_at_the_cent(delta: int, should_fail: bool) -> None:
    """The statutory fixed amount is exact: a cent either way is wrong."""
    payload = _payload()
    _obligation(payload, "OB-1003")["amount_required_cents"] += delta
    assert bool(_fired(check_pay_fixed_amount(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# due_original_matches / due_extended_matches -- the date re-derives exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_original_due_re_derives(delta: int, should_fail: bool) -> None:
    payload = _payload()
    obligation = _obligation(payload, "OB-1004")
    derived = date.fromisoformat(obligation["original_due"])
    obligation["original_due"] = (derived + timedelta(days=delta)).isoformat()
    assert bool(_fired(check_due_original_matches(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_extended_due_re_derives(delta: int, should_fail: bool) -> None:
    payload = _payload()
    obligation = _obligation(payload, "OB-1001")
    derived = date.fromisoformat(obligation["extended_due"])
    obligation["extended_due"] = (derived + timedelta(days=delta)).isoformat()
    assert bool(_fired(check_due_extended_matches(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ext_flag_valid -- the extension flag and the extended date agree
# --------------------------------------------------------------------------- #
def test_extended_date_needs_the_flag() -> None:
    payload = _payload()
    assert not _fired(check_ext_flag_valid(_ctx(payload)))
    # An extended date on a row that filed no extension.
    _obligation(payload, "OB-1004")["extended_due"] = "2029-03-15"
    assert _fired(check_ext_flag_valid(_ctx(payload)))


def test_flag_needs_the_extended_date() -> None:
    payload = _payload()
    obligation = _obligation(payload, "OB-1004")
    obligation["extension_filed"] = True  # but no extended date
    assert _fired(check_ext_flag_valid(_ctx(payload)))


# --------------------------------------------------------------------------- #
# wfl_ -- the schedule runs in order and on track
# --------------------------------------------------------------------------- #
def test_goal_order_must_hold() -> None:
    payload = _payload()
    assert not _fired(check_wfl_goal_monotonic(_ctx(payload)))
    _obligation(payload, "OB-1001")["prep_goal"] = "2028-08-20"  # after review goal
    assert _fired(check_wfl_goal_monotonic(_ctx(payload)))


def test_actual_slippage_is_a_flag() -> None:
    payload = _payload()
    assert not _fired(check_wfl_actual_slippage(_ctx(payload)))
    _obligation(payload, "OB-1002")["review_actual"] = "2028-09-05"
    fired = _fired(check_wfl_actual_slippage(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# cnt_final_not_recurring -- a final entity carries no live obligation
# --------------------------------------------------------------------------- #
def test_final_entity_must_not_recur() -> None:
    payload = _payload()
    assert not _fired(check_cnt_final_not_recurring(_ctx(payload)))
    _doc(payload, DOC_PRIOR_YEAR_REGISTER)["final_entities"].append("ENT-101")
    assert _fired(check_cnt_final_not_recurring(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the register, not the other way round
# --------------------------------------------------------------------------- #
def test_status_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_rpt_status_recomputes(_ctx(payload)))
    _summary_row(payload, "OB-1001")["status"] = "filed"
    assert _fired(check_rpt_status_recomputes(_ctx(payload)))


def test_counts_must_tie_the_register() -> None:
    payload = _payload()
    assert not _fired(check_rpt_counts_tie(_ctx(payload)))
    _doc(payload, DOC_STATUS_SUMMARY)["overdue_count"] += 1
    assert _fired(check_rpt_counts_tie(_ctx(payload)))


def test_watchlist_must_tie_the_register() -> None:
    payload = _payload()
    assert not _fired(check_rpt_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_DUE_WATCHLIST)["entries"].append(
        {
            "obligation_id": "OB-1001",
            "entity_id": "ENT-101",
            "form": "FED-1065",
            "applicable_due": "2029-03-15",
            "days_remaining": 469,
        }
    )
    fired = _fired(check_rpt_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "due_year_end_valid": Status.FAIL,
    "due_table_defined": Status.FAIL,
    "due_original_matches": Status.FAIL,
    "due_extended_matches": Status.FAIL,
    "ext_flag_valid": Status.FAIL,
    "ext_applicable_overdue": Status.FAIL,
    "ext_filed_on_time": Status.FAIL,
    "ext_due_soon": Status.FLAG,
    "pay_fixed_amount": Status.FAIL,
    "evd_filed_has_evidence": Status.FAIL,
    "evd_extension_evidence": Status.FAIL,
    "evd_no_orphan_evidence": Status.FAIL,
    "ros_entity_has_row": Status.FAIL,
    "ros_row_entity_known": Status.FAIL,
    "ros_unique_obligation_ids": Status.FAIL,
    "wfl_goal_monotonic": Status.FAIL,
    "wfl_actual_slippage": Status.FLAG,
    "cnt_final_not_recurring": Status.FAIL,
    "rpt_status_recomputes": Status.FAIL,
    "rpt_counts_tie": Status.FAIL,
    "rpt_watchlist_ties": Status.FLAG,
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
        "set", "due", "ext", "pay", "evd", "ros", "wfl", "cnt", "rpt"
    }
