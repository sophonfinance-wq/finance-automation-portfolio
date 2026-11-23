"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one basis point either side of
the line. A control that fires a cent early is as wrong as one that never fires,
and only a boundary test can tell the two apart.

The re-derivation cases carry the most weight. A derived column must match to the
cent and be wrong by one; a concession exactly equal to the price it discounts is
admissible and the cent past it is not; a discount exactly at the approved band is
inside sales authority; proof of closing falls due on the review date, not the day
after.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from sales_engine.engine import (
    SEVERITY,
    check_close_date_order,
    check_close_proof_received,
    check_close_sold_reconciles,
    check_comm_agent_known,
    check_comm_rate_defined,
    check_comm_splits_tie,
    check_comm_total_recomputes,
    check_price_concession_within_price,
    check_price_discount_to_list,
    check_price_net_proceeds_recomputes,
    check_price_rev_per_sqft_recomputes,
    check_rpt_commission_ties,
    check_rpt_revenue_ties,
    check_rpt_sold_count_ties,
)
from sales_engine.generate import AS_OF, PORTFOLIOS, PROJECTS, baseline
from sales_engine.model import (
    CHANNEL_CO_BROKE,
    DOC_COMMISSION_LOG,
    DOC_COMMISSION_SCHEDULE,
    DOC_PLAN_REGISTER,
    DOC_SALES_ROLLUP,
    DOC_SOLD_CLOSE_LOG,
    DOC_UNIT_MATRIX,
    UNIT_RESERVED,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0], PROJECTS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _unit(payload: dict, unit_id: str) -> dict:
    return next(
        u for u in _doc(payload, DOC_UNIT_MATRIX)["units"] if u["unit_id"] == unit_id
    )


def _closing(payload: dict, unit_id: str) -> dict:
    return next(
        c for c in _doc(payload, DOC_SOLD_CLOSE_LOG)["closings"]
        if c["unit_id"] == unit_id
    )


def _split(payload: dict, unit_id: str, agent_id: str) -> dict:
    return next(
        s for s in _doc(payload, DOC_COMMISSION_LOG)["splits"]
        if s["unit_id"] == unit_id and s["agent_id"] == agent_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# price_rev_per_sqft_recomputes -- the formula column matches to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_rev_per_sqft_matches_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _unit(payload, "UNIT-101")["rev_per_sqft_cents"] += delta
    assert bool(_fired(check_price_rev_per_sqft_recomputes(_ctx(payload)))) is should_fail


def test_rev_per_sqft_floors_rather_than_rounds() -> None:
    """A cent of price on a 1,200-square-foot plan cannot move a floored figure.

    UNIT-101 sells for 600,000.00 on 1,200 square feet, so the column reads exactly
    500.00. One cent more still floors to 500.00 -- and a full 1,200 cents more is
    the first price that moves it.
    """
    payload = _payload()
    unit = _unit(payload, "UNIT-101")
    unit["sales_price_cents"] += 1
    assert not _fired(check_price_rev_per_sqft_recomputes(_ctx(payload)))
    unit["sales_price_cents"] += 1199
    assert _fired(check_price_rev_per_sqft_recomputes(_ctx(payload)))


def test_rev_per_sqft_is_skipped_when_the_plan_area_is_unusable() -> None:
    """A zero plan area is a denominator problem, and ``plan_sqft_positive`` owns it.

    This control must not report a second, derived exception on top of it: the
    figure in the column was correct when it was struck.
    """
    payload = _payload()
    plans = _doc(payload, DOC_PLAN_REGISTER)["plans"]
    next(p for p in plans if p["plan_code"] == "PL-A1")["plan_sqft"] = 0
    assert not _fired(check_price_rev_per_sqft_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# price_concession_within_price -- inclusive at the price, exclusive past it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_concession_sits_inside_the_price(delta: int, should_fail: bool) -> None:
    """A concession exactly equal to the sales price is admissible; a cent past it
    conveys the unit for a negative number."""
    payload = _payload()
    unit = _unit(payload, "UNIT-103")
    unit["concession_cents"] = unit["sales_price_cents"] + delta
    assert bool(_fired(check_price_concession_within_price(_ctx(payload)))) is should_fail


def test_negative_concession_is_not_a_concession() -> None:
    payload = _payload()
    _unit(payload, "UNIT-103")["concession_cents"] = -1
    assert _fired(check_price_concession_within_price(_ctx(payload)))


# --------------------------------------------------------------------------- #
# price_net_proceeds_recomputes -- three columns feed one, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_net_proceeds_matches_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _unit(payload, "UNIT-105")["net_proceeds_cents"] += delta
    assert bool(_fired(check_price_net_proceeds_recomputes(_ctx(payload)))) is should_fail


def test_net_proceeds_may_be_negative_without_being_wrong() -> None:
    """A unit that costs more to close than it sells for is a real outcome.

    The control tests the arithmetic, not the sign: clamping at zero would hide the
    one row worth reading.
    """
    payload = _payload()
    unit = _unit(payload, "UNIT-101")
    unit["closing_costs_cents"] = unit["sales_price_cents"] * 2
    unit["net_proceeds_cents"] = (
        unit["sales_price_cents"] - unit["concession_cents"] - unit["closing_costs_cents"]
    )
    assert unit["net_proceeds_cents"] < 0
    assert not _fired(check_price_net_proceeds_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# price_discount_to_list -- inclusive at the approved band
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "sales_price_cents, should_flag",
    [(95_000_000, False), (94_990_000, True)],
)
def test_discount_band_edge(sales_price_cents: int, should_flag: bool) -> None:
    """Against a list of 1,000,000.00, a sale at 950,000.00 is exactly 5.00% off and
    inside the band; the next step past it is not."""
    payload = _payload()
    unit = _unit(payload, "UNIT-101")
    unit["list_price_cents"] = 100_000_000
    unit["sales_price_cents"] = sales_price_cents
    fired = _fired(check_price_discount_to_list(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_discount_band_ignores_unsold_units() -> None:
    """An unsold unit has no struck price, so it has no discount to be outside."""
    payload = _payload()
    unit = _unit(payload, "UNIT-106")
    assert unit["sales_price_cents"] == 0
    assert not _fired(check_price_discount_to_list(_ctx(payload)))


def test_discount_band_is_clean_on_the_baseline() -> None:
    assert not _fired(check_price_discount_to_list(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# comm_ -- the commission re-derives and the log splits it exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_commission_total_matches_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _unit(payload, "UNIT-102")["total_commission_cents"] += delta
    assert bool(_fired(check_comm_total_recomputes(_ctx(payload)))) is should_fail


def test_commission_total_follows_the_scheduled_rate() -> None:
    """Move the schedule rate and the column stops re-deriving; the splits do not
    move with it, because the log divides the total the Matrix already carried."""
    payload = _payload()
    rate = next(
        r for r in _doc(payload, DOC_COMMISSION_SCHEDULE)["rates"]
        if r["sale_channel"] == CHANNEL_CO_BROKE
    )
    rate["commission_rate_bps"] = 550
    assert _fired(check_comm_total_recomputes(_ctx(payload)))
    assert not _fired(check_comm_splits_tie(_ctx(payload)))


def test_commission_rate_must_be_scheduled() -> None:
    payload = _payload()
    assert not _fired(check_comm_rate_defined(_ctx(payload)))
    schedule = _doc(payload, DOC_COMMISSION_SCHEDULE)
    schedule["rates"] = [
        r for r in schedule["rates"] if r["sale_channel"] != CHANNEL_CO_BROKE
    ]
    assert _fired(check_comm_rate_defined(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_agent_splits_tie_to_the_cent(delta: int, should_fail: bool) -> None:
    """The residual cent belongs to a named agent, so the tie is exact."""
    payload = _payload()
    _split(payload, "UNIT-105", "AG-02")["split_cents"] += delta
    assert bool(_fired(check_comm_splits_tie(_ctx(payload)))) is should_fail


def test_three_way_split_conserves_the_residual_cent() -> None:
    """UNIT-105 splits 44,550.00 three ways at 33.33 / 33.33 / 33.34 percent.

    Largest-remainder allocation puts the odd cent on one agent, so the log sums to
    the Matrix total rather than to one cent under it.
    """
    payload = _payload()
    unit = _unit(payload, "UNIT-105")
    splits = [
        s for s in _doc(payload, DOC_COMMISSION_LOG)["splits"]
        if s["unit_id"] == "UNIT-105"
    ]
    assert len(splits) == 3
    assert sum(s["split_cents"] for s in splits) == unit["total_commission_cents"]


def test_a_split_on_a_unit_not_on_the_matrix_is_unauthorised() -> None:
    payload = _payload()
    _doc(payload, DOC_COMMISSION_LOG)["splits"].append(
        {"unit_id": "UNIT-999", "agent_id": "AG-01", "split_bps": 10000, "split_cents": 1}
    )
    assert _fired(check_comm_splits_tie(_ctx(payload)))


def test_split_must_name_a_registered_agent() -> None:
    payload = _payload()
    assert not _fired(check_comm_agent_known(_ctx(payload)))
    _split(payload, "UNIT-101", "AG-02")["agent_id"] = "AG-99"
    assert _fired(check_comm_agent_known(_ctx(payload)))


# --------------------------------------------------------------------------- #
# close_ -- the Sold/Close tab reconciles, in order, with proof
# --------------------------------------------------------------------------- #
def test_sold_unit_must_appear_on_the_close_tab() -> None:
    payload = _payload()
    assert not _fired(check_close_sold_reconciles(_ctx(payload)))
    log = _doc(payload, DOC_SOLD_CLOSE_LOG)
    log["closings"] = [c for c in log["closings"] if c["unit_id"] != "UNIT-102"]
    assert _fired(check_close_sold_reconciles(_ctx(payload)))


def test_close_row_without_a_sold_unit_is_unaccounted_for() -> None:
    """The reconciliation runs both ways; a closing nobody counted is the harder
    direction to notice."""
    payload = _payload()
    _unit(payload, "UNIT-102")["status"] = UNIT_RESERVED
    assert _fired(check_close_sold_reconciles(_ctx(payload)))


@pytest.mark.parametrize("offset, should_fail", [(0, False), (-1, True)])
def test_sale_date_may_equal_the_offer_date(offset: int, should_fail: bool) -> None:
    """An offer accepted the day it is written is admissible; a sale logged the day
    before the offer is not."""
    payload = _payload()
    row = _closing(payload, "UNIT-103")
    offer = date.fromisoformat(row["offer_date"])
    row["actual_date_sold"] = (offer + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_close_date_order(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("offset, should_fail", [(0, False), (-1, True)])
def test_closing_date_may_equal_the_sale_date(offset: int, should_fail: bool) -> None:
    payload = _payload()
    row = _closing(payload, "UNIT-103")
    sold = date.fromisoformat(row["actual_date_sold"])
    row["closing_date"] = (sold + timedelta(days=offset)).isoformat()
    assert bool(_fired(check_close_date_order(_ctx(payload)))) is should_fail


def test_unreadable_closing_date_is_reported_not_skipped() -> None:
    payload = _payload()
    _closing(payload, "UNIT-103")["closing_date"] = "not-a-date"
    assert _fired(check_close_date_order(_ctx(payload)))


@pytest.mark.parametrize("offset, should_flag", [(0, True), (1, False)])
def test_proof_falls_due_on_the_review_date(offset: int, should_flag: bool) -> None:
    """A closing dated exactly ``as_of`` owes its proof; one dated the day after does
    not yet."""
    payload = _payload()
    row = _closing(payload, "UNIT-105")
    row["closing_date"] = (_as_of() + timedelta(days=offset)).isoformat()
    row["proof_received"] = False
    fired = _fired(check_close_proof_received(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_proof_is_clean_on_the_baseline() -> None:
    assert not _fired(check_close_proof_received(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the Matrix, not the other way round
# --------------------------------------------------------------------------- #
def test_sold_count_must_tie_the_matrix() -> None:
    payload = _payload()
    assert not _fired(check_rpt_sold_count_ties(_ctx(payload)))
    _doc(payload, DOC_SALES_ROLLUP)["sold_unit_count"] += 1
    assert _fired(check_rpt_sold_count_ties(_ctx(payload)))


@pytest.mark.parametrize(
    "key", ["total_sales_price_cents", "total_net_proceeds_cents"]
)
def test_revenue_totals_must_tie_the_matrix(key: str) -> None:
    payload = _payload()
    assert not _fired(check_rpt_revenue_ties(_ctx(payload)))
    _doc(payload, DOC_SALES_ROLLUP)[key] += 1
    assert _fired(check_rpt_revenue_ties(_ctx(payload)))


def test_commission_total_must_tie_the_matrix() -> None:
    payload = _payload()
    assert not _fired(check_rpt_commission_ties(_ctx(payload)))
    _doc(payload, DOC_SALES_ROLLUP)["total_commission_cents"] += 1
    assert _fired(check_rpt_commission_ties(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "plan_unique_codes": Status.FAIL,
    "plan_sqft_positive": Status.FAIL,
    "unit_required_fields": Status.FAIL,
    "unit_unique_ids": Status.FAIL,
    "unit_plan_defined": Status.FAIL,
    "unit_status_valid": Status.FAIL,
    "price_rev_per_sqft_recomputes": Status.FAIL,
    "price_concession_within_price": Status.FAIL,
    "price_net_proceeds_recomputes": Status.FAIL,
    "price_discount_to_list": Status.FLAG,
    "comm_rate_defined": Status.FAIL,
    "comm_total_recomputes": Status.FAIL,
    "comm_splits_tie": Status.FAIL,
    "comm_agent_known": Status.FAIL,
    "close_sold_reconciles": Status.FAIL,
    "close_date_order": Status.FAIL,
    "close_proof_received": Status.FLAG,
    "rpt_sold_count_ties": Status.FAIL,
    "rpt_revenue_ties": Status.FAIL,
    "rpt_commission_ties": Status.FAIL,
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
        "set", "plan", "unit", "price", "comm", "close", "rpt"
    }
