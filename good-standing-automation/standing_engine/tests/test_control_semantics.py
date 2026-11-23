"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The amount and date-gate cases carry the most weight. A franchise tax met to the
cent must pass and a cent short must fail; a report filed on the due date is not
the same as one filed the day after; a renewal at the very edge of the lead
window is inside it and a day past the edge is not.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from standing_engine.engine import (
    SEVERITY,
    check_agt_fee_current,
    check_agt_matches_sos,
    check_dis_cancellation_complete,
    check_fil_due_date_recomputes,
    check_fil_renewal_lead_time,
    check_fil_report_fee_paid,
    check_fil_report_filed_on_time,
    check_lic_current,
    check_rec_state_required,
    check_roll_report_counts_tie,
    check_roll_standing_recomputes,
    check_roll_watchlist_ties,
    check_sts_sos_active,
    check_tax_amount_meets,
    check_tax_due_date_recomputes,
    check_tax_paid_on_time,
)
from standing_engine.generate import AS_OF, PORTFOLIOS, RENEWAL_LEAD_DAYS, baseline
from standing_engine.model import (
    DOC_COMPLIANCE_REPORT,
    DOC_JURISDICTION_MATRIX,
    DOC_RENEWAL_WATCHLIST,
    DOC_STANDING_RECORD_REGISTER,
    DOC_STANDING_SUMMARY,
    ENTITY_LLC,
    STATE_MARRAN,
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


def _record(payload: dict, record_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_STANDING_RECORD_REGISTER)["records"]
        if r["record_id"] == record_id
    )


def _matrix_row(payload: dict, state: str, entity_type: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_JURISDICTION_MATRIX)["requirements"]
        if r["state"] == state and r["entity_type"] == entity_type
    )


def _summary_row(payload: dict, entity_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_STANDING_SUMMARY)["entities"]
        if r["entity_id"] == entity_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# tax_amount_meets -- the franchise tax is met at the statutory amount, not a cent under
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_tax_amount_meets_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    required = _matrix_row(payload, STATE_MARRAN, ENTITY_LLC)["franchise_tax_cents"]
    _record(payload, "GS-1001")["franchise_tax_paid_cents"] = required + delta
    assert bool(_fired(check_tax_amount_meets(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_report_fee_meets_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    required = _matrix_row(payload, STATE_MARRAN, ENTITY_LLC)["report_fee_cents"]
    _record(payload, "GS-1001")["report_fee_paid_cents"] = required + delta
    assert bool(_fired(check_fil_report_fee_paid(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# fil_report_filed_on_time -- filed on the due date, not the day after
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(-1, False), (0, False), (1, True)])
def test_report_filed_on_the_due_date(offset: int, should_fail: bool) -> None:
    """A report filed exactly on the due date is on time; one day later is late."""
    payload = _payload()
    due = date.fromisoformat(_record(payload, "GS-1001")["report_due_date"])
    _record(payload, "GS-1001")["report_filed_date"] = (due + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_fil_report_filed_on_time(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# tax_paid_on_time -- paid on the due date, not the day after
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(-1, False), (0, False), (1, True)])
def test_franchise_paid_on_the_due_date(offset: int, should_fail: bool) -> None:
    payload = _payload()
    due = date.fromisoformat(_record(payload, "GS-1001")["franchise_tax_due_date"])
    _record(payload, "GS-1001")["franchise_tax_paid_date"] = (due + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_tax_paid_on_time(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# fil_renewal_lead_time -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset, should_flag", [(RENEWAL_LEAD_DAYS, True), (RENEWAL_LEAD_DAYS + 1, False)]
)
def test_renewal_window_edge(offset: int, should_flag: bool) -> None:
    """A next report due exactly ``lead_days`` out is inside the window; a day past
    it is not."""
    payload = _payload()
    _record(payload, "GS-1001")["next_report_due_date"] = (
        _as_of() + timedelta(days=offset)
    ).isoformat()
    fired = _fired(check_fil_renewal_lead_time(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_renewal_window_is_clean_far_out() -> None:
    """The baseline records' next report dates are well beyond the window."""
    assert not _fired(check_fil_renewal_lead_time(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# lic_current -- the licence must renew after the review date, not on it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(0, True), (1, False)])
def test_license_renews_after_the_review_date(offset: int, should_fail: bool) -> None:
    """A licence whose renewal date is exactly the review date is due, not current;
    one day later is current."""
    payload = _payload()
    _record(payload, "GS-1002")["license_due_date"] = (
        _as_of() + timedelta(days=offset)
    ).isoformat()
    assert bool(_fired(check_lic_current(_ctx(payload)))) is should_fail


def test_license_status_must_read_current() -> None:
    payload = _payload()
    assert not _fired(check_lic_current(_ctx(payload)))
    _record(payload, "GS-1002")["license_status"] = "lapsed"
    assert _fired(check_lic_current(_ctx(payload)))


# --------------------------------------------------------------------------- #
# fil_due_date_recomputes / tax_due_date_recomputes -- the stated date re-derives
# --------------------------------------------------------------------------- #
def test_report_due_date_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_fil_due_date_recomputes(_ctx(payload)))
    _record(payload, "GS-1001")["report_due_date"] = "2029-03-02"
    assert _fired(check_fil_due_date_recomputes(_ctx(payload)))


def test_franchise_due_date_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_tax_due_date_recomputes(_ctx(payload)))
    _record(payload, "GS-1001")["franchise_tax_due_date"] = "2029-06-02"
    assert _fired(check_tax_due_date_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# agt_ -- the agent of record is the contracted agent, with fee paid
# --------------------------------------------------------------------------- #
def test_agent_of_record_must_match_the_contract() -> None:
    payload = _payload()
    assert not _fired(check_agt_matches_sos(_ctx(payload)))
    _record(payload, "GS-1001")["sos_agent_name"] = "Some Other Agent Co"
    assert _fired(check_agt_matches_sos(_ctx(payload)))


def test_agent_fee_must_be_paid() -> None:
    payload = _payload()
    assert not _fired(check_agt_fee_current(_ctx(payload)))
    _record(payload, "GS-1001")["agent_fee_paid_date"] = ""
    assert _fired(check_agt_fee_current(_ctx(payload)))


# --------------------------------------------------------------------------- #
# sts_sos_active -- the internal Active status reconciles to the SOS status
# --------------------------------------------------------------------------- #
def test_active_entity_must_read_active_at_the_sos() -> None:
    payload = _payload()
    assert not _fired(check_sts_sos_active(_ctx(payload)))
    _record(payload, "GS-1001")["sos_status"] = "SUSPENDED"
    assert _fired(check_sts_sos_active(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rec_state_required -- a record for a state the entity never joined is stray
# --------------------------------------------------------------------------- #
def test_stray_state_record_is_flagged() -> None:
    payload = _payload()
    assert not _fired(check_rec_state_required(_ctx(payload)))
    _record(payload, "GS-1001")["state"] = "Tolvane"
    assert _fired(check_rec_state_required(_ctx(payload)))


# --------------------------------------------------------------------------- #
# dis_cancellation_complete -- every state a dissolved entity touched is cancelled
# --------------------------------------------------------------------------- #
def test_dissolved_entity_must_be_cancelled_everywhere() -> None:
    payload = _payload()
    assert not _fired(check_dis_cancellation_complete(_ctx(payload)))
    _record(payload, "GS-1007")["cancellation_filed"] = False
    assert _fired(check_dis_cancellation_complete(_ctx(payload)))


# --------------------------------------------------------------------------- #
# roll_ -- the rollup recomputes from the evidence, not the other way round
# --------------------------------------------------------------------------- #
def test_standing_flag_must_recompute() -> None:
    """A stated flag that contradicts the records fails; leaving it fails not."""
    payload = _payload()
    assert not _fired(check_roll_standing_recomputes(_ctx(payload)))
    _summary_row(payload, "ENT-101")["good_standing"] = False
    assert _fired(check_roll_standing_recomputes(_ctx(payload)))


def test_report_count_must_tie_the_summary() -> None:
    payload = _payload()
    assert not _fired(check_roll_report_counts_tie(_ctx(payload)))
    _doc(payload, DOC_COMPLIANCE_REPORT)["good_standing_count"] += 1
    assert _fired(check_roll_report_counts_tie(_ctx(payload)))


def test_watchlist_must_tie_the_evidence() -> None:
    payload = _payload()
    assert not _fired(check_roll_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_RENEWAL_WATCHLIST)["entries"].append(
        {
            "entity_id": "ENT-101",
            "state": STATE_MARRAN,
            "next_report_due_date": "2030-03-01",
            "days_remaining": 167,
        }
    )
    fired = _fired(check_roll_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "ent_unique_ids": Status.FAIL,
    "ent_type_valid": Status.FAIL,
    "ent_status_valid": Status.FAIL,
    "ent_jurisdictions_declared": Status.FAIL,
    "jur_matrix_defined": Status.FAIL,
    "jur_record_present": Status.FAIL,
    "rec_required_fields": Status.FAIL,
    "rec_file_number_unique": Status.FAIL,
    "rec_entity_exists": Status.FAIL,
    "rec_state_required": Status.FAIL,
    "fil_due_date_recomputes": Status.FAIL,
    "fil_report_filed_on_time": Status.FAIL,
    "fil_report_fee_paid": Status.FAIL,
    "fil_renewal_lead_time": Status.FLAG,
    "tax_amount_meets": Status.FAIL,
    "tax_due_date_recomputes": Status.FAIL,
    "tax_paid_on_time": Status.FAIL,
    "agt_matches_sos": Status.FAIL,
    "agt_fee_current": Status.FAIL,
    "sts_sos_active": Status.FAIL,
    "lic_current": Status.FAIL,
    "dis_cancellation_complete": Status.FAIL,
    "roll_standing_recomputes": Status.FAIL,
    "roll_report_counts_tie": Status.FAIL,
    "roll_watchlist_ties": Status.FLAG,
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
        "set", "ent", "jur", "rec", "fil", "tax", "agt", "sts", "lic", "dis", "roll"
    }
