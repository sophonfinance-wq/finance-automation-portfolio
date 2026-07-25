"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent, one basis point or one month
either side of the line. A control that fires a cent early is as wrong as one
that never fires, and only a boundary test can tell the two apart.

The sizing and expiry cases carry the most weight. A loan sized to the cent at
the advance rate must pass and a cent over must fail; an all-in rate that takes
the floor by a single basis point must recompute to the floor; a term sheet live
on the pricing date is not the same as one expiring the day before; a term sheet
at the very edge of the lead window is inside it and a day past the edge is not.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from sizing_engine.engine import (
    SEVERITY,
    check_exp_termsheet_lead_time,
    check_exp_termsheet_not_expired,
    check_fee_amount_recomputes,
    check_rate_all_in_recomputes,
    check_rpt_commitment_total_ties,
    check_rpt_deal_count_ties,
    check_rpt_expiry_watchlist_ties,
    check_rpt_fee_total_ties,
    check_size_drawn_within_commitment,
    check_size_ltc_not_exceeded,
    check_size_maturity_reconciles,
)
from sizing_engine.generate import AS_OF, COMMITMENT_LEAD_DAYS, PORTFOLIOS, baseline
from sizing_engine.model import (
    DOC_DEAL_REGISTER,
    DOC_EXPIRY_WATCHLIST,
    DOC_FEE_SUMMARY,
    DOC_RATE_SUMMARY,
    DOC_TERM_SHEET_ROLLUP,
    Context,
    Status,
)
from sizing_engine.terms import ltc_cap_cents


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _deal(payload: dict, deal_id: str) -> dict:
    return next(
        d for d in _doc(payload, DOC_DEAL_REGISTER)["deals"] if d["deal_id"] == deal_id
    )


def _rate_row(payload: dict, deal_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_RATE_SUMMARY)["rates"] if r["deal_id"] == deal_id
    )


def _fee_amount_row(payload: dict, fee_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_FEE_SUMMARY)["amounts"] if r["fee_id"] == fee_id
    )


def _rollup(payload: dict) -> dict:
    return _doc(payload, DOC_TERM_SHEET_ROLLUP)


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# size_ltc_not_exceeded -- the loan is capped at the advance rate, not a cent over
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_ltc_cap_met_at_the_cent(delta: int, should_fail: bool) -> None:
    """DL-203 is sized exactly at its cap; a cent over is an over-advance."""
    payload = _payload()
    deal = _deal(payload, "DL-203")
    cap = ltc_cap_cents(deal["cost_basis_cents"], deal["max_ltc_bps"])
    deal["max_loan_amount_cents"] = cap + delta
    assert bool(_fired(check_size_ltc_not_exceeded(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# size_drawn_within_commitment -- the draw is capped at the commitment
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_drawn_within_commitment_at_the_cent(delta: int, should_fail: bool) -> None:
    """DL-202 is fully drawn; a cent past the commitment is an over-draw."""
    payload = _payload()
    deal = _deal(payload, "DL-202")
    deal["drawn_amount_cents"] = deal["max_loan_amount_cents"] + delta
    assert bool(_fired(check_size_drawn_within_commitment(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# size_maturity_reconciles -- maturity equals term plus extensions, exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_maturity_reconciles_to_the_month(delta: int, should_fail: bool) -> None:
    payload = _payload()
    deal = _deal(payload, "DL-203")
    deal["stated_maturity_months"] += delta
    assert bool(_fired(check_size_maturity_reconciles(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rate_all_in_recomputes -- the all-in rate is the greater of build-up and floor
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_all_in_recomputes_to_the_basis_point(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _rate_row(payload, "DL-201")["all_in_rate_bps"] += delta
    assert bool(_fired(check_rate_all_in_recomputes(_ctx(payload)))) is should_fail


def test_all_in_takes_the_floor_when_it_governs() -> None:
    """DL-202's index-plus-spread lands below its floor, so the floor governs.

    The clean baseline states the floor as the all-in rate; the control agrees.
    """
    payload = _payload()
    assert not _fired(check_rate_all_in_recomputes(_ctx(payload)))
    assert _rate_row(payload, "DL-202")["all_in_rate_bps"] == 700  # the floor, not 600


# --------------------------------------------------------------------------- #
# fee_amount_recomputes -- the fee is its rate on its base, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_fee_amount_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _fee_amount_row(payload, "FEE-201A")["fee_amount_cents"] += delta
    assert bool(_fired(check_fee_amount_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exp_termsheet_not_expired -- expired on the pricing date, not the day before
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(-1, True), (0, True), (1, False)])
def test_expired_on_the_pricing_date(offset: int, should_fail: bool) -> None:
    """A term sheet expiring on ``as_of`` has lapsed; one day later is live."""
    payload = _payload()
    expiration = (_as_of() + timedelta(days=offset)).isoformat()
    _deal(payload, "DL-202")["termsheet_expiration_date"] = expiration
    assert bool(_fired(check_exp_termsheet_not_expired(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exp_termsheet_lead_time -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset, should_flag",
    [(COMMITMENT_LEAD_DAYS, True), (COMMITMENT_LEAD_DAYS + 1, False)],
)
def test_lead_time_window_edge(offset: int, should_flag: bool) -> None:
    """A term sheet ending exactly ``lead_days`` out is inside the window; a day
    past it is not."""
    payload = _payload()
    expiration = (_as_of() + timedelta(days=offset)).isoformat()
    _deal(payload, "DL-202")["termsheet_expiration_date"] = expiration
    fired = _fired(check_exp_termsheet_lead_time(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_lead_time_is_clean_far_out() -> None:
    """The baseline term sheets expire well beyond the window and raise no flag."""
    assert not _fired(check_exp_termsheet_lead_time(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup foots and ties from the deals, not the other way round
# --------------------------------------------------------------------------- #
def test_deal_count_must_tie_the_register() -> None:
    payload = _payload()
    assert not _fired(check_rpt_deal_count_ties(_ctx(payload)))
    _rollup(payload)["deal_count"] += 1
    assert _fired(check_rpt_deal_count_ties(_ctx(payload)))


def test_commitment_total_must_foot_the_deals() -> None:
    payload = _payload()
    assert not _fired(check_rpt_commitment_total_ties(_ctx(payload)))
    _rollup(payload)["total_commitment_cents"] += 1
    assert _fired(check_rpt_commitment_total_ties(_ctx(payload)))


def test_fee_total_must_foot_the_lines() -> None:
    payload = _payload()
    assert not _fired(check_rpt_fee_total_ties(_ctx(payload)))
    _rollup(payload)["total_fees_cents"] += 1
    assert _fired(check_rpt_fee_total_ties(_ctx(payload)))


def test_watchlist_must_tie_the_deals() -> None:
    payload = _payload()
    assert not _fired(check_rpt_expiry_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_EXPIRY_WATCHLIST)["entries"].append(
        {
            "deal_id": "DL-203",
            "termsheet_expiration_date": "2030-03-01",
            "days_remaining": 151,
        }
    )
    fired = _fired(check_rpt_expiry_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "deal_unique_ids": Status.FAIL,
    "deal_loan_type_valid": Status.FAIL,
    "deal_index_valid": Status.FAIL,
    "deal_recourse_valid": Status.FAIL,
    "deal_basis_declared": Status.FAIL,
    "size_ltc_not_exceeded": Status.FAIL,
    "size_drawn_within_commitment": Status.FAIL,
    "size_maturity_reconciles": Status.FAIL,
    "rate_buildup_present": Status.FAIL,
    "rate_all_in_recomputes": Status.FAIL,
    "fee_type_valid": Status.FAIL,
    "fee_base_type_valid": Status.FAIL,
    "fee_deal_exists": Status.FAIL,
    "fee_amount_recomputes": Status.FAIL,
    "exp_termsheet_not_expired": Status.FAIL,
    "exp_termsheet_lead_time": Status.FLAG,
    "rpt_deal_count_ties": Status.FAIL,
    "rpt_commitment_total_ties": Status.FAIL,
    "rpt_fee_total_ties": Status.FAIL,
    "rpt_expiry_watchlist_ties": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "deal", "size", "rate", "fee", "exp", "rpt"}
