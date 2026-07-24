"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The limit, match, withholding and deposit-timing cases carry the most weight. A
limit met to the cent must pass and a cent over must fail; a match computed on
capped comp is right and one on uncapped comp is wrong; a deposit on the seventh
business day is timely and the eighth is late.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benefit_engine.engine import (
    SEVERITY,
    check_dol_remit_after_pay,
    check_dol_safe_harbor,
    check_lim_402g_deferral,
    check_lim_415c_additions,
    check_lim_deferral_watch,
    check_lim_fsa_cap,
    check_lim_hsa_tier,
    check_mat_comp_cap,
    check_mat_recomputes,
    check_rpt_exception_watchlist_ties,
    check_rpt_tie_status_recomputes,
    check_whh_not_over_max,
    check_whh_per_period_recomputes,
)
from benefit_engine.generate import (
    COMP_CAP_CENTS,
    DEFERRAL_WATCH_BAND_CENTS,
    EMPLOYERS,
    MATCH_RATE_BPS,
    P_401K,
    P_FSA_MED,
    P_HSA,
    P_MATCH,
    PERIODS_REMAINING,
    baseline,
)
from benefit_engine.model import (
    DOC_DEDUCTION_REGISTER,
    DOC_EMPLOYEE_REGISTER,
    DOC_RECONCILIATION_REPORT,
    DOC_REMITTANCE_SCHEDULE,
    Context,
    Status,
)
from benefit_engine.reconcile import capped_match, per_period_max


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(EMPLOYERS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _employee(payload: dict, employee_id: str) -> dict:
    return next(
        e for e in _doc(payload, DOC_EMPLOYEE_REGISTER)["employees"]
        if e["employee_id"] == employee_id
    )


def _deduction(payload: dict, employee_id: str, plan_code: str) -> dict:
    return next(
        d for d in _doc(payload, DOC_DEDUCTION_REGISTER)["deductions"]
        if d["employee_id"] == employee_id and d["plan_code"] == plan_code
    )


def _remittance(payload: dict, plan_code: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_REMITTANCE_SCHEDULE)["remittances"]
        if r["plan_code"] == plan_code
    )


def _report_plan(payload: dict, plan_code: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_RECONCILIATION_REPORT)["plans"]
        if p["plan_code"] == plan_code
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# mat_recomputes -- the match is right to the cent, either side
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_match_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _deduction(payload, "EMP-01", P_MATCH)["amount_cents"] += delta
    assert bool(_fired(check_mat_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# mat_comp_cap -- an above-cap match may sit at the cap, not a cent over
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True)])
def test_match_cap_ceiling(delta: int, should_fail: bool) -> None:
    payload = _payload()
    ceiling = capped_match(COMP_CAP_CENTS, MATCH_RATE_BPS)
    _deduction(payload, "EMP-04", P_MATCH)["amount_cents"] = ceiling + delta
    assert bool(_fired(check_mat_comp_cap(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# lim_402g_deferral -- at the limit is fine, a cent over is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("over, should_fail", [(-1, False), (0, False), (1, True)])
def test_402g_at_the_limit(over: int, should_fail: bool) -> None:
    """EMP-01 (age 46) has a 402(g) limit of 23,500.00 and a 900.00 deferral this
    period, so a prior YTD of 22,600.00 lands the year-to-date exactly at the
    limit."""
    payload = _payload()
    this = _deduction(payload, "EMP-01", P_401K)["amount_cents"]
    limit = 2_350_000
    _employee(payload, "EMP-01")["prior_ytd"][P_401K] = limit - this + over
    assert bool(_fired(check_lim_402g_deferral(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# lim_hsa_tier -- family limit met exactly passes, a cent over fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("over, should_fail", [(0, False), (1, True)])
def test_hsa_tier_at_the_limit(over: int, should_fail: bool) -> None:
    payload = _payload()
    this = _deduction(payload, "EMP-05", P_HSA)["amount_cents"]
    limit = 855_000  # family, EMP-05 is under 55 so no catch-up
    _employee(payload, "EMP-05")["prior_ytd"][P_HSA] = limit - this + over
    assert bool(_fired(check_lim_hsa_tier(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# lim_fsa_cap -- election at the cap passes, a cent over fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("over, should_fail", [(0, False), (1, True)])
def test_fsa_at_the_cap(over: int, should_fail: bool) -> None:
    payload = _payload()
    this = _deduction(payload, "EMP-01", P_FSA_MED)["amount_cents"]
    cap = 330_000
    _employee(payload, "EMP-01")["prior_ytd"][P_FSA_MED] = cap - this + over
    assert bool(_fired(check_lim_fsa_cap(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# lim_415c_additions -- additions at the ceiling pass, a cent over fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("over, should_fail", [(0, False), (1, True)])
def test_415c_at_the_ceiling(over: int, should_fail: bool) -> None:
    """EMP-02 additions = deferral YTD + 6,000.00 match; a prior 401(k) YTD that
    puts additions exactly at the 70,000.00 limit passes, a cent more fails."""
    payload = _payload()
    this_def = _deduction(payload, "EMP-02", P_401K)["amount_cents"]
    match = _deduction(payload, "EMP-02", P_MATCH)["amount_cents"]
    limit = 7_000_000
    _employee(payload, "EMP-02")["prior_ytd"][P_401K] = limit - match - this_def + over
    assert bool(_fired(check_lim_415c_additions(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# lim_deferral_watch -- the FLAG band is [limit - band, limit], inclusive
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "ytd_target, should_flag",
    [
        (2_350_000 - DEFERRAL_WATCH_BAND_CENTS - 1, False),  # a cent below the band
        (2_350_000 - DEFERRAL_WATCH_BAND_CENTS, True),       # the near edge
        (2_350_000, True),                                    # exactly at the limit
        (2_350_000 + 1, False),                               # over: a breach, not a watch
    ],
)
def test_deferral_watch_band(ytd_target: int, should_flag: bool) -> None:
    payload = _payload()
    this = _deduction(payload, "EMP-01", P_401K)["amount_cents"]
    _employee(payload, "EMP-01")["prior_ytd"][P_401K] = ytd_target - this
    fired = _fired(check_lim_deferral_watch(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# whh_per_period_recomputes -- the level base is exact, either side fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_hsa_per_period_recomputes_exactly(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _deduction(payload, "EMP-05", P_HSA)["amount_cents"] += delta
    assert bool(_fired(check_whh_per_period_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# whh_not_over_max -- the true-up ceiling is inclusive, a cent over fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True)])
def test_hsa_not_over_max_ceiling(delta: int, should_fail: bool) -> None:
    payload = _payload()
    # EMP-05 room is 7,010.00 over 7 periods; the true-up piece is the ceiling.
    room = 855_000 - 24_000 - 130_000
    ceiling = per_period_max(room, PERIODS_REMAINING)
    _deduction(payload, "EMP-05", P_HSA)["amount_cents"] = ceiling + delta
    assert bool(_fired(check_whh_not_over_max(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# dol_safe_harbor -- the seventh business day is timely, the eighth is late
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "remit, should_fail",
    [("2031-09-09", False), ("2031-09-10", True)],
)
def test_deposit_on_the_safe_harbor_edge(remit: str, should_fail: bool) -> None:
    """Pay date is Friday 2031-08-29; 2031-09-09 is the seventh business day and
    2031-09-10 the eighth."""
    payload = _payload()
    _remittance(payload, P_401K)["remit_date"] = remit
    assert bool(_fired(check_dol_safe_harbor(_ctx(payload)))) is should_fail


def test_safe_harbor_ignores_employer_money() -> None:
    """The match is employer money and is not subject to the deposit safe harbor."""
    payload = _payload()
    _remittance(payload, P_MATCH)["remit_date"] = "2031-10-31"
    assert not _fired(check_dol_safe_harbor(_ctx(payload)))


# --------------------------------------------------------------------------- #
# dol_remit_after_pay -- on the pay date is fine, before it is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("remit, should_fail", [("2031-08-29", False), ("2031-08-28", True)])
def test_remit_not_before_pay(remit: str, should_fail: bool) -> None:
    payload = _payload()
    _remittance(payload, P_HSA)["remit_date"] = remit
    assert bool(_fired(check_dol_remit_after_pay(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence, not the other way round
# --------------------------------------------------------------------------- #
def test_tie_flag_must_recompute() -> None:
    """A stated tie flag that contradicts the legs fails; leaving it does not."""
    payload = _payload()
    assert not _fired(check_rpt_tie_status_recomputes(_ctx(payload)))
    _report_plan(payload, P_HSA)["tied"] = False
    assert _fired(check_rpt_tie_status_recomputes(_ctx(payload)))


def test_watchlist_must_tie_the_evidence() -> None:
    payload = _payload()
    assert not _fired(check_rpt_exception_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_RECONCILIATION_REPORT)["exceptions"].append(
        {"employee_id": "EMP-01", "plan_code": P_401K, "kind": "deferral_over"}
    )
    fired = _fired(check_rpt_exception_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "emp_unique_ids": Status.FAIL,
    "emp_entity_valid": Status.FAIL,
    "emp_fields_valid": Status.FAIL,
    "pln_unique_codes": Status.FAIL,
    "pln_type_valid": Status.FAIL,
    "ded_refs_valid": Status.FAIL,
    "ded_unique_pairs": Status.FAIL,
    "ded_matches_provider": Status.FAIL,
    "tie_provider_total": Status.FAIL,
    "tie_je_liability": Status.FAIL,
    "tie_cash_transfer": Status.FAIL,
    "ent_subtotal_recomputes": Status.FAIL,
    "ent_consolidated_ties": Status.FAIL,
    "mat_recomputes": Status.FAIL,
    "mat_comp_cap": Status.FAIL,
    "lim_402g_deferral": Status.FAIL,
    "lim_hsa_tier": Status.FAIL,
    "lim_fsa_cap": Status.FAIL,
    "lim_415c_additions": Status.FAIL,
    "lim_deferral_watch": Status.FLAG,
    "whh_per_period_recomputes": Status.FAIL,
    "whh_not_over_max": Status.FAIL,
    "dol_safe_harbor": Status.FAIL,
    "dol_remit_after_pay": Status.FAIL,
    "je_balances": Status.FAIL,
    "je_clearing_zeroes": Status.FAIL,
    "rpt_tie_status_recomputes": Status.FAIL,
    "rpt_exception_watchlist_ties": Status.FLAG,
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
        "set", "emp", "pln", "ded", "tie", "ent", "mat", "lim", "whh", "dol", "je", "rpt"
    }
