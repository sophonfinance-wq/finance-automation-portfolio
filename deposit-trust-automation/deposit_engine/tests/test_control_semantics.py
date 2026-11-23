"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one row or one status either side of
the line. A control that fires a cent early is as wrong as one that never fires,
and only a boundary test can tell the two apart.

The tie-out and split cases carry the most weight. A variance of a single cent
on any reconciliation leg must fail and zero must pass; a forfeiture split a
cent off the deposit is a split that created or destroyed money; a concession of
exactly zero is legitimate and a concession of one positive cent is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deposit_engine.engine import (
    SEVERITY,
    check_bnk_forfeiture_income_ties,
    check_bnk_upgrade_bank_ties,
    check_cxl_reversal_matches_sweep,
    check_cxl_split_sums,
    check_net_concession_sign,
    check_net_sale_recomputes,
    check_rpt_exception_flags_tie,
    check_rpt_total_variance_ties,
    check_seg_amount_splits,
    check_sts_valid_bucket,
    check_swp_need_to_post_not_swept,
    check_swp_posted_has_paydown,
    check_tie_agent_variance_zero,
    check_tie_loan_leg_zero,
)
from deposit_engine.generate import PORTFOLIOS, baseline
from deposit_engine.model import (
    DOC_DEPOSIT_LEDGER,
    DOC_ESCROW_STATEMENT,
    DOC_PAYDOWN_REGISTER,
    DOC_RECON_SUMMARY,
    DOC_TRUST_BALANCES,
    STATUS_BUCKETS,
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


def _deposit(payload: dict, deposit_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_DEPOSIT_LEDGER)["deposits"]
        if r["deposit_id"] == deposit_id
    )


def _agent_entry(payload: dict, unit_id: str) -> dict:
    return next(
        e for e in _doc(payload, DOC_ESCROW_STATEMENT)["entries"]
        if e["unit_id"] == unit_id
    )


def _movement(payload: dict, paydown_id: str) -> dict:
    return next(
        m for m in _doc(payload, DOC_PAYDOWN_REGISTER)["movements"]
        if m["paydown_id"] == paydown_id
    )


def _cancellation(payload: dict, cancellation_id: str) -> dict:
    return next(
        c for c in _doc(payload, "cancellation_register")["cancellations"]
        if c["cancellation_id"] == cancellation_id
    )


def _sales_row(payload: dict, unit_id: str) -> dict:
    return next(
        u for u in _doc(payload, "sales_matrix")["units"] if u["unit_id"] == unit_id
    )


def _summary_unit(payload: dict, unit_id: str) -> dict:
    return next(
        u for u in _doc(payload, DOC_RECON_SUMMARY)["units"] if u["unit_id"] == unit_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# seg_amount_splits -- the identity holds to the cent, both directions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_segregation_identity_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _deposit(payload, "DEP-1001")["amount_cents"] += delta
    assert bool(_fired(check_seg_amount_splits(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# tie_agent_variance_zero -- zero is the only passing value
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_agent_variance_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _agent_entry(payload, "UNIT-105")["agent_deposit_cents"] += delta
    assert bool(_fired(check_tie_agent_variance_zero(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# tie_loan_leg_zero -- the loan leg nets to the swept earnest money exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_loan_leg_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _movement(payload, "PDN-2005")["principal_cents"] += delta
    assert bool(_fired(check_tie_loan_leg_zero(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# swp_ -- the sweep register against the ledger's own status column
# --------------------------------------------------------------------------- #
def test_swept_deposit_needs_exactly_one_paydown() -> None:
    """Zero rows and two rows both fail; the baseline's one row passes."""
    payload = _payload()
    assert not _fired(check_swp_posted_has_paydown(_ctx(payload)))
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    register["movements"].append(dict(_movement(payload, "PDN-2001"), paydown_id="PDN-2098"))
    assert _fired(check_swp_posted_has_paydown(_ctx(payload)))

    payload = _payload()
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    register["movements"] = [
        m for m in register["movements"] if m["paydown_id"] != "PDN-2001"
    ]
    assert _fired(check_swp_posted_has_paydown(_ctx(payload)))


def test_unswept_deposit_tolerates_no_paydown() -> None:
    payload = _payload()
    assert not _fired(check_swp_need_to_post_not_swept(_ctx(payload)))
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    register["movements"].append(
        {
            "paydown_id": "PDN-2097",
            "deposit_id": "DEP-1002",
            "unit_id": "UNIT-102",
            "payment_date": "2030-03-20",
            "kind": "paydown",
            "principal_cents": 1_500_000,
        }
    )
    assert _fired(check_swp_need_to_post_not_swept(_ctx(payload)))


# --------------------------------------------------------------------------- #
# cxl_ -- the forfeiture split accounts for every cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_forfeiture_split_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _cancellation(payload, "CXL-3001")["termination_fee_cents"] += delta
    assert bool(_fired(check_cxl_split_sums(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_reversal_matches_the_sweep_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _movement(payload, "PDN-2004")["principal_cents"] += delta
    assert bool(_fired(check_cxl_reversal_matches_sweep(_ctx(payload)))) is should_fail


def test_never_swept_cancellation_tolerates_no_reversal() -> None:
    """DEP-1007 cancelled before posting; a reversal for it is unwinding nothing."""
    payload = _payload()
    assert not _fired(check_cxl_reversal_matches_sweep(_ctx(payload)))
    register = _doc(payload, DOC_PAYDOWN_REGISTER)
    register["movements"].append(
        {
            "paydown_id": "PDN-2096",
            "deposit_id": "DEP-1007",
            "unit_id": "UNIT-106",
            "payment_date": "2030-03-21",
            "kind": "reversal",
            "principal_cents": 1_000_000,
        }
    )
    assert _fired(check_cxl_reversal_matches_sweep(_ctx(payload)))


# --------------------------------------------------------------------------- #
# sts_valid_bucket -- membership is exact
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", STATUS_BUCKETS)
def test_every_known_bucket_passes(status: str) -> None:
    payload = _payload()
    _deposit(payload, "DEP-1002")["status"] = status
    assert not _fired(check_sts_valid_bucket(_ctx(payload)))


@pytest.mark.parametrize("status", ["pending", "posted", "", "NEED_TO_POST"])
def test_unknown_bucket_fails(status: str) -> None:
    payload = _payload()
    _deposit(payload, "DEP-1002")["status"] = status
    assert _fired(check_sts_valid_bucket(_ctx(payload)))


# --------------------------------------------------------------------------- #
# bnk_ -- the trust balances tie to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_upgrade_bank_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_TRUST_BALANCES)["upgrade_bank_balance_cents"] += delta
    assert bool(_fired(check_bnk_upgrade_bank_ties(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_forfeiture_income_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_TRUST_BALANCES)["forfeiture_income_cents"] += delta
    assert bool(_fired(check_bnk_forfeiture_income_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# net_ -- concession netting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_net_sale_recomputes_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _sales_row(payload, "UNIT-105")["net_sale_cents"] += delta
    assert bool(_fired(check_net_sale_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("concession, should_fail", [(-1, False), (0, False), (1, True)])
def test_concession_sign_boundary(concession: int, should_fail: bool) -> None:
    """A zero concession is legitimate; one positive cent inflates revenue."""
    payload = _payload()
    row = _sales_row(payload, "UNIT-102")
    row["concession_cents"] = concession
    row["net_sale_cents"] = row["sales_price_cents"] + concession
    assert bool(_fired(check_net_concession_sign(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence, not the other way round
# --------------------------------------------------------------------------- #
def test_exception_flag_must_tie_the_variance() -> None:
    """A flag that contradicts the recomputed variance is a FLAG finding."""
    payload = _payload()
    assert not _fired(check_rpt_exception_flags_tie(_ctx(payload)))
    _summary_unit(payload, "UNIT-101")["exception_flag"] = True
    fired = _fired(check_rpt_exception_flags_tie(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_total_variance_foots_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_RECON_SUMMARY)["total_variance_cents"] += delta
    assert bool(_fired(check_rpt_total_variance_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "led_unique_ids": Status.FAIL,
    "led_required_fields": Status.FAIL,
    "seg_amount_splits": Status.FAIL,
    "seg_components_nonnegative": Status.FAIL,
    "tie_agent_variance_zero": Status.FAIL,
    "tie_agent_completeness": Status.FAIL,
    "tie_ledger_completeness": Status.FAIL,
    "tie_loan_leg_zero": Status.FAIL,
    "swp_posted_has_paydown": Status.FAIL,
    "swp_paydown_has_deposit": Status.FAIL,
    "swp_need_to_post_not_swept": Status.FAIL,
    "cxl_row_joins": Status.FAIL,
    "cxl_split_sums": Status.FAIL,
    "cxl_reversal_matches_sweep": Status.FAIL,
    "cxl_fee_account": Status.FAIL,
    "sts_valid_bucket": Status.FAIL,
    "sts_closed_excluded_from_agent": Status.FLAG,
    "bnk_upgrade_bank_ties": Status.FAIL,
    "bnk_forfeiture_income_ties": Status.FAIL,
    "net_sale_recomputes": Status.FAIL,
    "net_concession_sign": Status.FAIL,
    "net_concession_account": Status.FAIL,
    "rpt_unit_variance_recomputes": Status.FAIL,
    "rpt_exception_flags_tie": Status.FLAG,
    "rpt_total_variance_ties": Status.FAIL,
    "rpt_bucket_totals_tie": Status.FAIL,
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
        "set", "led", "seg", "tie", "swp", "cxl", "sts", "bnk", "net", "rpt",
    }
