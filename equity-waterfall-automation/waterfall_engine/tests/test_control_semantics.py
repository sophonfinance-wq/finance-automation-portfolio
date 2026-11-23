"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one basis point or one month either side
of the line. A control that fires a cent early is as wrong as one that never
fires, and only a boundary test can tell the two apart.

The re-derivation cases carry the most weight. A figure equal to the recompute to
the cent must pass and a cent off must fail; a covenant maturing exactly at the
edge of its window is inside it and a month past the edge is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from waterfall_engine.engine import (
    SEVERITY,
    check_cap_contribution_recomputes,
    check_cap_rollforward_zeroes,
    check_cov_ltc_within_max,
    check_cov_maturity_window,
    check_dil_recompute,
    check_dist_no_leakage,
    check_dist_within_available,
    check_hurdle_boundary_recomputes,
    check_loan_repaid_before_distribution,
    check_mbr_commitment_honored,
    check_pref_accrual_recomputes,
    check_promo_carry_recomputes,
    check_promo_split_ratios_valid,
    check_ret_multiple_recomputes,
    check_ret_preferred_ties,
    check_ret_profit_split_ties,
    check_syn_capital_call_ratio,
    check_syn_report_due,
    check_wf_pari_passu_split,
    check_wf_tier_allocation_recomputes,
)
from waterfall_engine.generate import (
    AS_OF_PERIOD,
    DEVELOPER_ID,
    INVESTOR_ID,
    PROJECTS,
    SPONSORS,
    baseline,
)
from waterfall_engine.model import (
    DOC_CAPITAL_LEDGER,
    DOC_DEAL_TERMS,
    DOC_DILUTION_WORKSHEET,
    DOC_LOAN_COVENANT,
    DOC_MEMBER_REGISTER,
    DOC_RETURNS_SUMMARY,
    DOC_WATERFALL_SCHEDULE,
    TIER_PREF,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(SPONSORS[0], PROJECTS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _ledger_row(payload: dict, member_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_CAPITAL_LEDGER)["accounts"]
        if r["member_id"] == member_id
    )


def _returns_row(payload: dict, member_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_RETURNS_SUMMARY)["members"]
        if r["member_id"] == member_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# pref_accrual_recomputes -- exact to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_pref_accrual_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _ledger_row(payload, INVESTOR_ID)["investment_return_account_cents"] += delta
    assert bool(_fired(check_pref_accrual_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_contribution_account_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _ledger_row(payload, DEVELOPER_ID)["contribution_account_cents"] += delta
    assert bool(_fired(check_cap_contribution_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_capital_account_rolls_to_zero(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _ledger_row(payload, INVESTOR_ID)["ending_contribution_account_cents"] += delta
    assert bool(_fired(check_cap_rollforward_zeroes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# wf_ -- allocation and pari passu
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tier_allocation_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_WATERFALL_SCHEDULE)["entries"][0]["amount_cents"] += delta
    assert bool(_fired(check_wf_tier_allocation_recomputes(_ctx(payload)))) is should_fail


def test_pari_passu_split_must_match_the_balances() -> None:
    payload = _payload()
    assert not _fired(check_wf_pari_passu_split(_ctx(payload)))
    entries = _doc(payload, DOC_WATERFALL_SCHEDULE)["entries"]
    inv_a = next(e for e in entries if e["tier"] == TIER_PREF and e["member_id"] == INVESTOR_ID)
    dev_a = next(e for e in entries if e["tier"] == TIER_PREF and e["member_id"] == DEVELOPER_ID)
    inv_a["amount_cents"] += 1
    dev_a["amount_cents"] -= 1
    assert _fired(check_wf_pari_passu_split(_ctx(payload)))


# --------------------------------------------------------------------------- #
# hurdle_boundary_recomputes -- the promote boundary is solved from contributions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_hurdle_target_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_WATERFALL_SCHEDULE)["hurdle_target_cents"] += delta
    assert bool(_fired(check_hurdle_boundary_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# promo_ -- the splits sum, and the carry re-derives
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "dev_bps, should_fail", [(5000, False), (5001, True), (4999, True)]
)
def test_promote_split_must_sum_to_100(dev_bps: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_DEAL_TERMS)["tier_d_developer_bps"] = dev_bps
    assert bool(_fired(check_promo_split_ratios_valid(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_promote_carry_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_WATERFALL_SCHEDULE)["promote_split_cents"] += delta
    assert bool(_fired(check_promo_carry_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# loan_repaid_before_distribution -- repayment ties, net proceeds tie
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_loan_repayment_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_LOAN_COVENANT)["member_loan_repayment_cents"] += delta
    assert bool(_fired(check_loan_repaid_before_distribution(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# dil_recompute -- diluted interest ties by its own method
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_dilution_interest_to_the_bp(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_DILUTION_WORKSHEET)["diluted_interest_bps"] += delta
    assert bool(_fired(check_dil_recompute(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# dist_ -- no leakage, within available
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_no_leakage_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_WATERFALL_SCHEDULE)["total_distributed_cents"] += delta
    assert bool(_fired(check_dist_no_leakage(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True)])
def test_distribution_within_available_at_the_edge(delta: int, should_fail: bool) -> None:
    """Distributing exactly the available proceeds passes; a cent more fails."""
    payload = _payload()
    schedule = _doc(payload, DOC_WATERFALL_SCHEDULE)
    schedule["total_distributed_cents"] = schedule["proceeds_after_loans_cents"] + delta
    assert bool(_fired(check_dist_within_available(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ret_ -- the realized-returns summary ties the waterfall
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_equity_multiple_to_the_bp(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _returns_row(payload, INVESTOR_ID)["equity_multiple_bps"] += delta
    assert bool(_fired(check_ret_multiple_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_preferred_return_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _returns_row(payload, INVESTOR_ID)["preferred_return_cents"] += delta
    assert bool(_fired(check_ret_preferred_ties(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_profit_split_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _returns_row(payload, DEVELOPER_ID)["profit_split_cents"] += delta
    assert bool(_fired(check_ret_profit_split_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# mbr_commitment_honored -- funded at the ceiling passes, a cent over fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (-1, True)])
def test_commitment_ceiling_at_the_cent(delta: int, should_fail: bool) -> None:
    """The investor funded 9,000,000; a commitment set to that passes, a cent
    below fails."""
    payload = _payload()
    member = next(
        m for m in _doc(payload, DOC_MEMBER_REGISTER)["members"]
        if m["member_id"] == INVESTOR_ID
    )
    funded = sum(c["amount_cents"] for c in member["contributions"])
    member["commitment_cents"] = funded + delta
    assert bool(_fired(check_mbr_commitment_honored(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cov_ltc_within_max -- the ratio sits at or below the cap
# --------------------------------------------------------------------------- #
def test_ltc_within_max_at_the_edge() -> None:
    payload = _payload()
    loan = _doc(payload, DOC_LOAN_COVENANT)
    # Set the senior loan to exactly the cap, then a dollar over.
    loan["senior_loan_cents"] = loan["total_cost_cents"] * loan["max_ltc_bps"] // 10000
    assert not _fired(check_cov_ltc_within_max(_ctx(payload)))
    # One full basis point of cost over the cap crosses the integer LTC threshold.
    loan["senior_loan_cents"] += loan["total_cost_cents"] // 10000 + 1
    assert _fired(check_cov_ltc_within_max(_ctx(payload)))


# --------------------------------------------------------------------------- #
# syn_capital_call_ratio -- the draw is the fixed ratio
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_syndicate_draw_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_LOAN_COVENANT)["syndicate_draw_cents"] += delta
    assert bool(_fired(check_syn_capital_call_ratio(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cov_maturity_window -- the window closes at exactly lead_periods out (FLAG)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset, should_flag",
    [(6, True), (7, False), (1, True), (0, False)],
)
def test_maturity_window_edge(offset: int, should_flag: bool) -> None:
    """A financing maturing exactly ``lead`` months out is inside the window; a
    month past it, or already matured, is not."""
    payload = _payload()
    _doc(payload, DOC_LOAN_COVENANT)["maturity_period"] = AS_OF_PERIOD + offset
    fired = _fired(check_cov_maturity_window(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# syn_report_due -- the window closes at exactly lead_periods out (FLAG)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset, should_flag",
    [(3, True), (4, False), (1, True), (0, False)],
)
def test_report_due_window_edge(offset: int, should_flag: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_LOAN_COVENANT)["report_due_period"] = AS_OF_PERIOD + offset
    fired = _fired(check_syn_report_due(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "mbr_unique_ids": Status.FAIL,
    "mbr_role_valid": Status.FAIL,
    "mbr_roles_complete": Status.FAIL,
    "mbr_commitment_honored": Status.FAIL,
    "pref_rate_valid": Status.FAIL,
    "pref_accrual_recomputes": Status.FAIL,
    "cap_contribution_recomputes": Status.FAIL,
    "cap_rollforward_zeroes": Status.FAIL,
    "wf_tier_order_valid": Status.FAIL,
    "wf_pari_passu_split": Status.FAIL,
    "wf_tier_allocation_recomputes": Status.FAIL,
    "hurdle_rate_valid": Status.FAIL,
    "hurdle_boundary_recomputes": Status.FAIL,
    "promo_split_ratios_valid": Status.FAIL,
    "promo_carry_recomputes": Status.FAIL,
    "loan_rate_valid": Status.FAIL,
    "loan_repaid_before_distribution": Status.FAIL,
    "dil_method_valid": Status.FAIL,
    "dil_penalty_multiplier": Status.FAIL,
    "dil_recompute": Status.FAIL,
    "dist_no_leakage": Status.FAIL,
    "dist_within_available": Status.FAIL,
    "ret_multiple_recomputes": Status.FAIL,
    "ret_preferred_ties": Status.FAIL,
    "ret_profit_split_ties": Status.FAIL,
    "cov_maturity_window": Status.FLAG,
    "cov_ltc_within_max": Status.FAIL,
    "syn_capital_call_ratio": Status.FAIL,
    "syn_report_due": Status.FLAG,
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
        "set", "mbr", "pref", "cap", "wf", "hurdle", "promo",
        "loan", "dil", "dist", "ret", "cov", "syn",
    }
