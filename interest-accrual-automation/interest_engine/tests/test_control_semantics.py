"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The accrual and gate cases carry the most weight. Interest re-derived to the cent
must pass and a cent off must fail; a period beginning on the maturity date is not
the same as one beginning the day before; a payment equal to the accrued interest
services it, and a cent more reduces principal.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from interest_engine.accrual import accrued_interest
from interest_engine.engine import (
    SEVERITY,
    check_acc_interest_rederives,
    check_gate_maturity_approaching,
    check_gate_maturity_stop,
    check_gate_no_prepayment,
    check_gate_rate_step,
    check_recip_income_expense_equal,
    check_recip_nr_np_equal,
    check_rf_ending_balance_rederives,
    check_rpt_note_settled_recomputes,
    check_rpt_report_count_ties,
    check_rpt_watchlist_ties,
    check_wf_final_settles_zero,
    check_wf_payment_within_balance,
    check_wf_subordination_order,
)
from interest_engine.generate import AS_OF, MATURITY_LEAD_DAYS, PORTFOLIOS, baseline
from interest_engine.model import (
    DOC_DEBT_SERVICE_REPORT,
    DOC_INTEREST_SUMMARY,
    DOC_MATURITY_WATCHLIST,
    DOC_NOTE_REGISTER,
    DOC_ROLLFORWARD,
    DOC_TRIAL_BALANCE,
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


def _note(payload: dict, note_id: str) -> dict:
    return next(
        n for n in _doc(payload, DOC_NOTE_REGISTER)["notes"] if n["note_id"] == note_id
    )


def _rows_of(payload: dict, note_id: str) -> list[dict]:
    rows = [r for r in _doc(payload, DOC_ROLLFORWARD)["rows"] if r["note_id"] == note_id]
    return sorted(rows, key=lambda r: (r["period_start"], r["period_end"]))


def _tb_row(payload: dict, account: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_TRIAL_BALANCE)["accounts"] if r["account"] == account
    )


def _summary_row(payload: dict, note_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_INTEREST_SUMMARY)["notes"] if r["note_id"] == note_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# acc_interest_rederives -- the accrual is met to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_accrual_rederives_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _rows_of(payload, "NR-1401")[0]
    row["accrued_cents"] = row["accrued_cents"] + delta
    assert bool(_fired(check_acc_interest_rederives(_ctx(payload)))) is should_fail


def test_accrual_matches_the_kernel() -> None:
    """The shipped accrual is exactly what the kernel produces from the terms."""
    payload = _payload()
    note = _note(payload, "NR-1401")
    row = _rows_of(payload, "NR-1401")[0]
    expected = accrued_interest(
        row["beginning_cents"], row["rate_bps"], row["days"], note["day_count_denom"]
    )
    assert row["accrued_cents"] == expected


# --------------------------------------------------------------------------- #
# rf_ending_balance_rederives -- the roll-forward identity holds to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_ending_balance_rederives_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _rows_of(payload, "NR-1401")[0]
    row["ending_cents"] = row["ending_cents"] + delta
    assert bool(_fired(check_rf_ending_balance_rederives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# gate_maturity_stop -- accrual stops on the maturity date, not the day after
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(0, True), (1, False)])
def test_accrual_stops_on_maturity(offset: int, should_fail: bool) -> None:
    """A period beginning exactly on the maturity date must accrue nothing; a
    period beginning a day before it may still accrue."""
    payload = _payload()
    second = _rows_of(payload, "NR-1401")[1]
    start = date.fromisoformat(second["period_start"])
    _note(payload, "NR-1401")["maturity_date"] = (start + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_gate_maturity_stop(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# gate_maturity_approaching -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset, should_flag", [(MATURITY_LEAD_DAYS, True), (MATURITY_LEAD_DAYS + 1, False)]
)
def test_maturity_window_edge(offset: int, should_flag: bool) -> None:
    """A note maturing exactly ``lead_days`` out is inside the window; a day past
    it is not."""
    payload = _payload()
    _note(payload, "NR-1401")["maturity_date"] = (
        _as_of() + timedelta(days=offset)
    ).isoformat()
    fired = _fired(check_gate_maturity_approaching(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_maturity_window_is_clean_far_out() -> None:
    """The baseline notes mature well beyond the window and raise no flag."""
    assert not _fired(check_gate_maturity_approaching(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# gate_no_prepayment -- interest service passes, a cent of principal fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True)])
def test_prepayment_is_principal_not_interest(delta: int, should_fail: bool) -> None:
    """NR-1403 bars prepayment. A pre-maturity payment equal to accrued interest is
    fine; a cent above it reduces principal and trips the gate."""
    payload = _payload()
    row = _rows_of(payload, "NR-1403")[0]
    row["payment_cents"] = row["accrued_cents"] + delta
    assert bool(_fired(check_gate_no_prepayment(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# gate_rate_step -- the default rate steps in on the event date
# --------------------------------------------------------------------------- #
def test_rate_steps_on_the_event_date() -> None:
    """NR-1405's event of default is 2029-08-01. The period starting that day must
    carry the default rate; the period before it the stated rate."""
    payload = _payload()
    assert not _fired(check_gate_rate_step(_ctx(payload)))
    # A pre-event period wrongly carrying the default rate trips the gate.
    _rows_of(payload, "NR-1405")[0]["rate_bps"] = _note(payload, "NR-1405")["default_rate_bps"]
    assert _fired(check_gate_rate_step(_ctx(payload)))


def test_post_event_period_at_stated_rate_fails() -> None:
    payload = _payload()
    # The third period begins on the event date and must be at the default rate.
    on_event = _rows_of(payload, "NR-1405")[2]
    assert on_event["period_start"] == "2029-08-01"
    on_event["rate_bps"] = _note(payload, "NR-1405")["stated_rate_bps"]
    assert _fired(check_gate_rate_step(_ctx(payload)))


# --------------------------------------------------------------------------- #
# wf_payment_within_balance -- a payment at the balance passes, a cent over fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True)])
def test_payment_within_balance_edge(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _rows_of(payload, "NR-1401")[0]
    available = row["beginning_cents"] + row["advance_cents"] + row["accrued_cents"]
    row["payment_cents"] = available + delta
    assert bool(_fired(check_wf_payment_within_balance(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# wf_final_settles_zero -- a payoff note lands on exactly zero
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ending, should_fail", [(0, False), (1, True), (-1, True)])
def test_payoff_settles_to_zero(ending: int, should_fail: bool) -> None:
    payload = _payload()
    _rows_of(payload, "NR-1403")[-1]["ending_cents"] = ending
    assert bool(_fired(check_wf_final_settles_zero(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# wf_subordination_order -- the subordinate services interest but not principal
# --------------------------------------------------------------------------- #
def test_subordinate_may_service_interest_not_principal() -> None:
    payload = _payload()
    assert not _fired(check_wf_subordination_order(_ctx(payload)))
    row = _rows_of(payload, "NR-1405")[0]
    row["payment_cents"] = row["accrued_cents"] + 1
    assert _fired(check_wf_subordination_order(_ctx(payload)))


# --------------------------------------------------------------------------- #
# recip_ -- the two sides reconcile
# --------------------------------------------------------------------------- #
def test_receivable_must_equal_payable() -> None:
    payload = _payload()
    assert not _fired(check_recip_nr_np_equal(_ctx(payload)))
    _tb_row(payload, _note(payload, "NR-1401")["np_account"])["balance_cents"] += 1
    assert _fired(check_recip_nr_np_equal(_ctx(payload)))


def test_income_must_equal_expense() -> None:
    payload = _payload()
    assert not _fired(check_recip_income_expense_equal(_ctx(payload)))
    _tb_row(payload, _note(payload, "NR-1402")["income_account"])["balance_cents"] += 1
    assert _fired(check_recip_income_expense_equal(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence, not the other way round
# --------------------------------------------------------------------------- #
def test_settled_flag_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_rpt_note_settled_recomputes(_ctx(payload)))
    _summary_row(payload, "NR-1403")["settled"] = False
    assert _fired(check_rpt_note_settled_recomputes(_ctx(payload)))


def test_report_count_must_tie_the_summary() -> None:
    payload = _payload()
    assert not _fired(check_rpt_report_count_ties(_ctx(payload)))
    _doc(payload, DOC_DEBT_SERVICE_REPORT)["settled_count"] += 1
    assert _fired(check_rpt_report_count_ties(_ctx(payload)))


def test_watchlist_must_tie_the_evidence() -> None:
    payload = _payload()
    assert not _fired(check_rpt_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_MATURITY_WATCHLIST)["entries"].append(
        {"note_id": "NR-1402", "maturity_date": "2031-12-31", "days_remaining": 821}
    )
    fired = _fired(check_rpt_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "note_unique_ids": Status.FAIL,
    "note_required_fields": Status.FAIL,
    "note_terms_valid": Status.FAIL,
    "note_entities_distinct": Status.FAIL,
    "acc_row_fields_present": Status.FAIL,
    "acc_day_count_ties": Status.FAIL,
    "acc_interest_rederives": Status.FAIL,
    "rf_row_note_exists": Status.FAIL,
    "rf_ending_balance_rederives": Status.FAIL,
    "rf_continuity": Status.FAIL,
    "rf_opening_ties_principal": Status.FAIL,
    "gate_rate_step": Status.FAIL,
    "gate_maturity_stop": Status.FAIL,
    "gate_no_prepayment": Status.FAIL,
    "gate_maturity_approaching": Status.FLAG,
    "wf_payment_within_balance": Status.FAIL,
    "wf_final_settles_zero": Status.FAIL,
    "wf_subordination_order": Status.FAIL,
    "recip_nr_np_equal": Status.FAIL,
    "recip_income_expense_equal": Status.FAIL,
    "gl_journal_balances": Status.FAIL,
    "gl_journal_ties_accrual": Status.FAIL,
    "gl_note_on_tb": Status.FAIL,
    "gl_tb_complete": Status.FAIL,
    "rpt_note_settled_recomputes": Status.FAIL,
    "rpt_report_count_ties": Status.FAIL,
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
        "set", "note", "acc", "rf", "gate", "wf", "recip", "gl", "rpt"
    }
