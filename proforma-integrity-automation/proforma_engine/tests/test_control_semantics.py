"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one day or one basis point either side
of the line. A control that fires a cent early is as wrong as one that never
fires, and only a boundary test can tell the two apart.

The tie-out and gate cases carry the most weight. A figure that re-derives to the
cent must pass and a cent off must fail; a reserve exactly at the interest it
funds is adequate and a cent under is not; a QPR filed on its due date is on time
and a day later is not; a profit swing exactly at the materiality band is inside
it and a cent past is flagged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proforma_engine.engine import (
    SEVERITY,
    check_cost_hard_soft_total,
    check_int_reserve_adequate,
    check_mgn_margin_on_cost,
    check_prof_net_profit_derivation,
    check_rpt_qpr_due_date_gate,
    check_var_materiality_flag,
    check_var_metric_delta,
    check_wfl_split_completeness,
)
from proforma_engine.generate import PORTFOLIOS, baseline
from proforma_engine.model import (
    DOC_FILING_REGISTER,
    DOC_PROFORMA_LEDGER,
    DOC_TIEOUT_SUMMARY,
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


def _ledger_row(payload: dict, project_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_PROFORMA_LEDGER)["projects"]
        if r["project_id"] == project_id
    )


def _summary_row(payload: dict, project_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_TIEOUT_SUMMARY)["projects"]
        if r["project_id"] == project_id
    )


def _qpr_filing(payload: dict, project_id: str) -> dict:
    return next(
        f for f in _doc(payload, DOC_FILING_REGISTER)["qpr_filings"]
        if f["project_id"] == project_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# cost_hard_soft_total -- ties to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_hard_soft_total_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _summary_row(payload, "PRJ-01")["total_project_cost_cents"] += delta
    assert bool(_fired(check_cost_hard_soft_total(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# prof_net_profit_derivation -- re-derives to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_net_profit_re_derives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _summary_row(payload, "PRJ-01")["net_profit_cents"] += delta
    assert bool(_fired(check_prof_net_profit_derivation(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# mgn_margin_on_cost -- one basis point off is off
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_margin_on_cost_re_derives_at_the_bp(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _summary_row(payload, "PRJ-01")["margin_on_cost_bps"] += delta
    assert bool(_fired(check_mgn_margin_on_cost(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# wfl_split_completeness -- the split must sum to the whole
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_split_must_sum_to_net(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _summary_row(payload, "PRJ-01")["investor_profit_cents"] += delta
    assert bool(_fired(check_wfl_split_completeness(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# int_reserve_adequate -- the reserve must cover the interest, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_reserve_covers_interest_at_the_cent(delta: int, should_fail: bool) -> None:
    """Reserve equal to the interest is adequate; a cent under is not; a cent over
    is fine."""
    payload = _payload()
    row = _ledger_row(payload, "PRJ-01")
    row["interest_reserve_cents"] = row["interest_cost_cents"] + delta
    assert bool(_fired(check_int_reserve_adequate(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# var_metric_delta -- a typed variance one cent off fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_variance_is_current_minus_prior(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _summary_row(payload, "PRJ-01")["variance"]["net_profit_cents"] += delta
    assert bool(_fired(check_var_metric_delta(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# var_materiality_flag -- the band closes at exactly the band amount
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("over, should_flag", [(0, False), (1, True)])
def test_materiality_band_edge(over: int, should_flag: bool) -> None:
    """A swing exactly at the band is inside it; a cent past it is flagged."""
    payload = _payload()
    band = payload["materiality_cents"]
    # Current net profit for PRJ-01 is fixed by its ledger; set prior so the swing
    # lands exactly at (or one cent past) the band.
    srow = _summary_row(payload, "PRJ-01")
    current_np = srow["net_profit_cents"]
    _ledger_row(payload, "PRJ-01")["prior"]["net_profit_cents"] = current_np - band - over
    fired = _fired(check_var_materiality_flag(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_materiality_is_clean_on_the_baseline() -> None:
    """The baseline swings are well inside the band and raise no flag."""
    assert not _fired(check_var_materiality_flag(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# rpt_qpr_due_date_gate -- filed on the due date is on time, a day later is late
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "filed, should_fail",
    [("2031-01-22", False), ("2031-01-21", False), ("2031-01-23", True)],
)
def test_qpr_due_date_gate(filed: str, should_fail: bool) -> None:
    """PRJ-01 is in Marran, whose QPR is due 2031-01-22."""
    payload = _payload()
    _qpr_filing(payload, "PRJ-01")["filed_date"] = filed
    assert bool(_fired(check_rpt_qpr_due_date_gate(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "src_sources_total_ties": Status.FAIL,
    "src_uses_total_ties": Status.FAIL,
    "src_source_use_balance": Status.FAIL,
    "cost_hard_soft_total": Status.FAIL,
    "cost_unlevered_ties_devbudget": Status.FAIL,
    "cost_contingency_rollup": Status.FAIL,
    "int_reserve_adequate": Status.FAIL,
    "int_equity_funded_before_construction": Status.FAIL,
    "prof_net_profit_derivation": Status.FAIL,
    "prof_unlevered_profit_derivation": Status.FAIL,
    "wfl_waterfall_ties_net": Status.FAIL,
    "wfl_budgeted_ties_net": Status.FAIL,
    "wfl_distributed_ties_net": Status.FAIL,
    "wfl_sponsor_share_derivation": Status.FAIL,
    "wfl_split_completeness": Status.FAIL,
    "mgn_margin_on_cost": Status.FAIL,
    "mgn_margin_on_revenue": Status.FAIL,
    "mgn_cost_per_nsf": Status.FAIL,
    "var_metric_delta": Status.FAIL,
    "var_schedule_days": Status.FAIL,
    "var_materiality_flag": Status.FLAG,
    "rpt_project_qpr_filed": Status.FAIL,
    "rpt_qpr_due_date_gate": Status.FAIL,
    "rpt_regional_deliverables_present": Status.FAIL,
    "rpt_cycle_count_ties": Status.FAIL,
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
        "set", "src", "cost", "int", "prof", "wfl", "mgn", "var", "rpt"
    }
