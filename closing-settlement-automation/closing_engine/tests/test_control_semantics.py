"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one day or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The re-derivation controls carry the most weight. A figure that recomputes to the
cent must pass and a cent off must fail; a threshold met exactly at the line is
inside it; a rate-derived fee is right only at its rate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from closing_engine.engine import (
    SEVERITY,
    check_cos_prepaid_commission_relief_cap,
    check_fee_broker_commission_variance,
    check_fee_concessions_within_assumption,
    check_fee_listing_sales_rederives,
    check_je_ar_plug_recomputes,
    check_je_balances,
    check_loan_ending_recomputes,
    check_loan_release_price_covered,
    check_rev_recognized_in_coe_month,
    check_rpt_closed_count_ties,
    check_rpt_net_to_seller_total_ties,
    check_rpt_unit_tied_recomputes,
    check_ss_net_to_seller_recompute,
)
from closing_engine.generate import DEVELOPERS, baseline
from closing_engine.model import (
    ACCOUNT_ACCOUNTS_RECEIVABLE,
    DOC_CLOSING_JE_REGISTER,
    DOC_CLOSING_REPORT,
    DOC_CLOSING_SUMMARY,
    DOC_COS_SCHEDULE,
    DOC_LOAN_RELEASE_REGISTER,
    DOC_PROFORMA_ASSUMPTIONS,
    DOC_REVENUE_SCHEDULE,
    DOC_SETTLEMENT_REGISTER,
    DOC_UNIT_REGISTER,
    Context,
    Status,
)
from closing_engine.money import apply_rate


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(DEVELOPERS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _row(payload: dict, doc_type: str, key: str, unit_id: str) -> dict:
    return next(r for r in _doc(payload, doc_type)[key] if r["unit_id"] == unit_id)


def _settlement(payload: dict, unit_id: str) -> dict:
    return _row(payload, DOC_SETTLEMENT_REGISTER, "settlements", unit_id)


def _je(payload: dict, unit_id: str) -> dict:
    return _row(payload, DOC_CLOSING_JE_REGISTER, "entries", unit_id)


def _loan(payload: dict, unit_id: str) -> dict:
    return _row(payload, DOC_LOAN_RELEASE_REGISTER, "releases", unit_id)


def _cos(payload: dict, unit_id: str) -> dict:
    return _row(payload, DOC_COS_SCHEDULE, "entries", unit_id)


def _revenue(payload: dict, unit_id: str) -> dict:
    return _row(payload, DOC_REVENUE_SCHEDULE, "entries", unit_id)


def _unit(payload: dict, unit_id: str) -> dict:
    return _row(payload, DOC_UNIT_REGISTER, "units", unit_id)


def _gross(payload: dict, unit_id: str) -> int:
    return int(_unit(payload, unit_id)["gross_sales_cents"])


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# ss_net_to_seller_recompute -- exact to the cent, either side
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_net_to_seller_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _settlement(payload, "U-101")["net_to_seller_cents"] += delta
    assert bool(_fired(check_ss_net_to_seller_recompute(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# fee_listing_sales_rederives -- right only at its rate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_listing_fee_is_right_only_at_its_rate(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _settlement(payload, "U-101")["listing_sales_fee_cents"] += delta
    assert bool(_fired(check_fee_listing_sales_rederives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# loan_release_price_covered -- the remittance covers the price, at the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_release_price_covered_at_the_cent(delta: int, should_fail: bool) -> None:
    """A remittance equal to the release price covers it; a cent short does not."""
    payload = _payload()
    loan = _loan(payload, "U-101")
    loan["release_price_cents"] = int(loan["bank_remittance_cents"]) + delta
    assert bool(_fired(check_loan_release_price_covered(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cos_prepaid_commission_relief_cap -- relieved equals MIN, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_prepaid_relief_equals_the_cap(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _cos(payload, "U-101")["prepaid_relieved_cents"] += delta
    assert bool(_fired(check_cos_prepaid_commission_relief_cap(_ctx(payload)))) is should_fail


def test_prepaid_relief_is_capped_at_the_prepaid_balance() -> None:
    """When earned exceeds the prepaid balance, relief is the prepaid balance."""
    payload = _payload()
    cos = _cos(payload, "U-101")
    prepaid = int(_unit(payload, "U-101")["prepaid_balance_cents"])
    # Baseline commission earned exceeds the prepaid balance, so relief == prepaid.
    assert cos["prepaid_relieved_cents"] == prepaid
    assert not _fired(check_cos_prepaid_commission_relief_cap(_ctx(payload)))


# --------------------------------------------------------------------------- #
# je_balances / je_ar_plug -- the entry foots and the plug is derived
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True), (-1, True)])
def test_entry_foots_only_when_balanced(delta: int, should_fail: bool) -> None:
    payload = _payload()
    for line in _je(payload, "U-101")["lines"]:
        if line["account"] == "Closing Costs":
            line["debit_cents"] += delta
    assert bool(_fired(check_je_balances(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True), (-1, True)])
def test_receivable_plug_recomputes(delta: int, should_fail: bool) -> None:
    payload = _payload()
    for line in _je(payload, "U-101")["lines"]:
        if line["account"] == ACCOUNT_ACCOUNTS_RECEIVABLE:
            line["debit_cents"] += delta
    assert bool(_fired(check_je_ar_plug_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# loan_ending_recomputes -- the roll-forward is exact
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_loan_ending_rolls_forward_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    loan = _loan(payload, "U-101")
    loan["ending_balance_cents"] += delta
    loan["lender_statement_ending_cents"] += delta  # keep the tie, isolate the roll
    assert bool(_fired(check_loan_ending_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rev_recognized_in_coe_month -- the close month, not a neighbour
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "month, should_fail",
    [("2029-01", False), ("2029-02", True), ("2028-12", True)],
)
def test_revenue_recognized_in_the_close_month(month: str, should_fail: bool) -> None:
    """U-101 closes 2029-01-15, so only 2029-01 is the correct recognition month."""
    payload = _payload()
    _revenue(payload, "U-101")["recognized_month"] = month
    assert bool(_fired(check_rev_recognized_in_coe_month(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# fee_broker_commission_variance -- a FLAG, off the proforma rate
# --------------------------------------------------------------------------- #
def test_broker_commission_variance_is_a_flag() -> None:
    payload = _payload()
    assert not _fired(check_fee_broker_commission_variance(_ctx(payload)))
    _settlement(payload, "U-101")["broker_commission_cents"] += 1
    fired = _fired(check_fee_broker_commission_variance(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# fee_concessions_within_assumption -- a FLAG, above the allowance
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("over, should_flag", [(0, False), (1, True)])
def test_concessions_flag_above_the_allowance(over: int, should_flag: bool) -> None:
    """Concessions at the allowance are clean; a cent above it flags."""
    payload = _payload()
    gross = _gross(payload, "U-101")
    allowance = apply_rate(gross, 50)
    _settlement(payload, "U-101")["concessions_cents"] = allowance + over
    fired = _fired(check_fee_concessions_within_assumption(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the units, not the other way round
# --------------------------------------------------------------------------- #
def test_tied_flag_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_rpt_unit_tied_recomputes(_ctx(payload)))
    next(r for r in _doc(payload, DOC_CLOSING_SUMMARY)["units"] if r["unit_id"] == "U-101")[
        "tied"
    ] = False
    assert _fired(check_rpt_unit_tied_recomputes(_ctx(payload)))


def test_closed_count_must_tie_the_register() -> None:
    payload = _payload()
    assert not _fired(check_rpt_closed_count_ties(_ctx(payload)))
    _doc(payload, DOC_CLOSING_REPORT)["closed_count"] += 1
    assert _fired(check_rpt_closed_count_ties(_ctx(payload)))


def test_net_to_seller_total_must_tie_the_settlements() -> None:
    payload = _payload()
    assert not _fired(check_rpt_net_to_seller_total_ties(_ctx(payload)))
    _doc(payload, DOC_CLOSING_REPORT)["total_net_to_seller_cents"] += 1
    assert _fired(check_rpt_net_to_seller_total_ties(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "unit_unique_ids": Status.FAIL,
    "unit_status_valid": Status.FAIL,
    "unit_required_fields": Status.FAIL,
    "unit_artifacts_complete": Status.FAIL,
    "je_unit_exists": Status.FAIL,
    "je_balances": Status.FAIL,
    "je_ar_plug_recomputes": Status.FAIL,
    "ss_total_charges_recompute": Status.FAIL,
    "ss_total_closing_costs_recompute": Status.FAIL,
    "ss_net_to_seller_recompute": Status.FAIL,
    "fee_listing_sales_rederives": Status.FAIL,
    "fee_warranty_reserve_rederives": Status.FAIL,
    "fee_broker_commission_variance": Status.FLAG,
    "fee_concessions_within_assumption": Status.FLAG,
    "rev_recognized_in_coe_month": Status.FAIL,
    "rev_deferred_upgrade_reversed": Status.FAIL,
    "loan_ending_recomputes": Status.FAIL,
    "loan_ties_lender_statement": Status.FAIL,
    "loan_release_price_covered": Status.FAIL,
    "cos_margin_recompute": Status.FAIL,
    "cos_prepaid_commission_relief_cap": Status.FAIL,
    "rpt_closed_count_ties": Status.FAIL,
    "rpt_net_to_seller_total_ties": Status.FAIL,
    "rpt_unit_tied_recomputes": Status.FAIL,
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
        "set", "unit", "je", "ss", "fee", "rev", "loan", "cos", "rpt"
    }
