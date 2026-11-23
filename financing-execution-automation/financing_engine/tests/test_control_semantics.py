"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one count or one status either side of the
line. A control that fires a day early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The variance, overdue and period-end cases carry the most weight. A variance must
match its dates to the day; a milestone dated exactly on the report date is due,
not overdue; a report dated the day before period-end is not a period-end
snapshot.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from financing_engine.engine import (
    SEVERITY,
    check_base_original_immutable,
    check_date_overdue_flag,
    check_date_report_is_period_end,
    check_ord_current_nondecreasing,
    check_roll_prior_ties_current,
    check_rpt_active_count_ties,
    check_rpt_financing_total_ties,
    check_rpt_overdue_count_ties,
    check_var_gantt_month_recomputes,
    check_var_recomputes,
    recompute_financing_total,
)
from financing_engine.generate import ENTITIES, REPORT_DATE, baseline
from financing_engine.model import (
    DOC_FINANCING_REPORT,
    DOC_GANTT_SUMMARY,
    DOC_MILESTONE_SCHEDULE,
    DOC_PRIOR_SCHEDULE,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(ENTITIES[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _milestone(payload: dict, milestone_id: str) -> dict:
    return next(
        m for m in _doc(payload, DOC_MILESTONE_SCHEDULE)["milestones"]
        if m["milestone_id"] == milestone_id
    )


def _prior_row(payload: dict, milestone_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_PRIOR_SCHEDULE)["prior_milestones"]
        if r["milestone_id"] == milestone_id
    )


def _gantt_bar(payload: dict, workstream_id: str) -> dict:
    return next(
        b for b in _doc(payload, DOC_GANTT_SUMMARY)["bars"]
        if b["workstream_id"] == workstream_id
    )


def _report(payload: dict) -> dict:
    return _doc(payload, DOC_FINANCING_REPORT)


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _report_date() -> date:
    return date.fromisoformat(REPORT_DATE)


# --------------------------------------------------------------------------- #
# var_recomputes -- the variance matches its dates to the day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_variance_matches_its_dates(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _milestone(payload, "WS-01-M1")
    row["variance_days"] += delta
    assert bool(_fired(check_var_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# date_overdue_flag -- overdue on the day after, not on the report date
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_flag", [(-1, True), (0, False), (1, False)])
def test_overdue_gate_at_the_report_date(offset: int, should_flag: bool) -> None:
    """A milestone dated exactly on the report date is due, not overdue; a day
    earlier has slipped past it. The baseline flag is False, so a re-derived True
    is the mismatch the control raises."""
    payload = _payload()
    current = (_report_date() + timedelta(days=offset)).isoformat()
    _milestone(payload, "WS-01-M1")["current_date"] = current
    fired = _fired(check_date_overdue_flag(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_overdue_flag_is_clean_on_the_baseline() -> None:
    """Every baseline milestone is in the future and correctly flagged not-overdue."""
    assert not _fired(check_date_overdue_flag(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# date_report_is_period_end -- the report date is the last day of the month
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "report_date, should_fail",
    [("2029-06-30", False), ("2029-06-29", True), ("2029-07-01", True)],
)
def test_report_date_is_period_end(report_date: str, should_fail: bool) -> None:
    payload = _payload()
    payload["report_date"] = report_date
    assert bool(_fired(check_date_report_is_period_end(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# roll_prior_ties_current -- this Prior equals last Current, to the day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shift, should_fail", [(0, False), (1, True), (-1, True)])
def test_prior_ties_last_current(shift: int, should_fail: bool) -> None:
    payload = _payload()
    row = _prior_row(payload, "WS-02-M1")
    shifted = date.fromisoformat(row["current_date"]) + timedelta(days=shift)
    row["current_date"] = shifted.isoformat()
    assert bool(_fired(check_roll_prior_ties_current(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# base_original_immutable -- the frozen Original does not move
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shift, should_fail", [(0, False), (1, True), (-30, True)])
def test_original_baseline_is_frozen(shift: int, should_fail: bool) -> None:
    payload = _payload()
    row = _milestone(payload, "WS-02-M1")
    shifted = date.fromisoformat(row["original_date"]) + timedelta(days=shift)
    row["original_date"] = shifted.isoformat()
    assert bool(_fired(check_base_original_immutable(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ord_current_nondecreasing -- equal is allowed, backwards is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shift, should_fail", [(0, False), (1, False), (-40, True)])
def test_current_dates_do_not_run_backwards(shift: int, should_fail: bool) -> None:
    """Setting milestone 2 to its predecessor's date (or later) is fine; pulling it
    before the predecessor runs the schedule backwards."""
    payload = _payload()
    first = _milestone(payload, "WS-01-M1")
    second = _milestone(payload, "WS-01-M2")
    anchored = date.fromisoformat(first["current_date"]) + timedelta(days=shift)
    second["current_date"] = anchored.isoformat()
    assert bool(_fired(check_ord_current_nondecreasing(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# var_gantt_month_recomputes -- the bar sits in the closing month
# --------------------------------------------------------------------------- #
def test_gantt_month_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_var_gantt_month_recomputes(_ctx(payload)))
    bar = _gantt_bar(payload, "WS-01")
    bar["gantt_month"] = (bar["gantt_month"] % 12) + 1
    assert _fired(check_var_gantt_month_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the schedule, not the other way round
# --------------------------------------------------------------------------- #
def test_active_count_must_tie_the_register() -> None:
    payload = _payload()
    assert not _fired(check_rpt_active_count_ties(_ctx(payload)))
    _report(payload)["active_count"] += 1
    assert _fired(check_rpt_active_count_ties(_ctx(payload)))


def test_overdue_count_must_tie_the_schedule() -> None:
    payload = _payload()
    assert not _fired(check_rpt_overdue_count_ties(_ctx(payload)))
    _report(payload)["overdue_count"] += 1
    assert _fired(check_rpt_overdue_count_ties(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_financing_total_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    recomputed = recompute_financing_total(_ctx(payload))
    _report(payload)["total_financing_cents"] = recomputed + delta
    assert bool(_fired(check_rpt_financing_total_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "mem_workstream_ids_unique": Status.FAIL,
    "mem_workstream_type_valid": Status.FAIL,
    "mem_workstream_status_valid": Status.FAIL,
    "mem_milestone_workstream_exists": Status.FAIL,
    "mem_playbook_defined": Status.FAIL,
    "mem_playbook_complete": Status.FAIL,
    "mem_portfolio_present": Status.FAIL,
    "mem_workstream_in_tracker": Status.FAIL,
    "var_dates_wellformed": Status.FAIL,
    "var_recomputes": Status.FAIL,
    "var_gantt_month_recomputes": Status.FAIL,
    "roll_prior_ties_current": Status.FAIL,
    "base_original_immutable": Status.FAIL,
    "date_report_is_period_end": Status.FAIL,
    "date_overdue_flag": Status.FLAG,
    "ord_sequence_unique": Status.FAIL,
    "ord_current_nondecreasing": Status.FAIL,
    "rpt_active_count_ties": Status.FAIL,
    "rpt_overdue_count_ties": Status.FAIL,
    "rpt_financing_total_ties": Status.FAIL,
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
        "set", "mem", "var", "roll", "base", "date", "ord", "rpt"
    }
