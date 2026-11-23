"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a day early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The proration cases carry the most weight here. A closing date is a single fact,
but it produces a different seller's share in each regime, because each regime's
fiscal year opens on a different day. Testing the same date against two regimes is
the cheapest proof that nothing about the calendar is hard-coded.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from proptax_engine.engine import (
    SEVERITY,
    derive_penalty_interest,
    check_acr_stops_at_escrow,
    check_asmt_variance_surfaced,
    check_inst_delinquency_recomputed,
    check_inst_matches_regime_calendar,
    check_own_no_payment_after_escrow,
    check_own_proration_by_days_held,
    check_own_proration_sums_to_annual,
    check_par_plat_completeness,
)
from proptax_engine.generate import PORTFOLIOS, baseline, rederive
from proptax_engine.model import (
    ASSESSMENT_VARIANCE_BPS,
    DOC_ACCRUAL_LEDGER,
    DOC_INSTALMENT_SCHEDULE,
    DOC_PARCEL_REGISTER,
    DOC_PROJECT_REGISTER,
    DOC_SALE_REGISTER,
    INTEREST_PERIOD_DAYS,
    PRORATION_DAYS,
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


def _parcel(payload: dict, parcel_no: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PARCEL_REGISTER)["parcels"]
        if p["parcel_no"] == parcel_no
    )


def _instalment(payload: dict, parcel_no: str, sequence: int) -> dict:
    return next(
        r for r in _doc(payload, DOC_INSTALMENT_SCHEDULE)["instalments"]
        if r["parcel_no"] == parcel_no and r["sequence"] == sequence
    )


def _closing(payload: dict, parcel_no: str) -> dict:
    return next(
        c for c in _doc(payload, DOC_SALE_REGISTER)["closings"]
        if c["parcel_no"] == parcel_no
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# The regimes really are different -- proved on one shared closing date
# --------------------------------------------------------------------------- #
def test_the_same_closing_date_prorates_differently_by_regime() -> None:
    """One date, two fiscal years, two seller's shares.

    ``P-2103`` sits in a calendar-year regime and ``P-2242`` in one opening on
    1 July. Closing both on the same day must produce different proportions of
    the year held -- which is the whole reason the regime table exists.
    """
    payload = _payload()
    shared = "2029-09-30"
    for parcel_no in ("P-2103", "P-2242"):
        _closing(payload, parcel_no)["close_of_escrow_date"] = shared
    rederive(payload)

    cascadia = _closing(payload, "P-2103")
    ardenne = _closing(payload, "P-2242")
    cascadia_ratio = (
        cascadia["seller_share_cents"] / _parcel(payload, "P-2103")["annual_tax_cents"]
    )
    ardenne_ratio = (
        ardenne["seller_share_cents"] / _parcel(payload, "P-2242")["annual_tax_cents"]
    )
    assert cascadia_ratio > ardenne_ratio
    assert not _fired(check_own_proration_by_days_held(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_seller_share_is_re_derived_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    closing = _closing(payload, "P-2103")
    closing["seller_share_cents"] += delta
    closing["buyer_share_cents"] -= delta
    assert bool(_fired(check_own_proration_by_days_held(_ctx(payload)))) is should_fail


def test_proration_sum_is_checked_independently_of_the_split() -> None:
    """The two shares can each be wrong and still sum, or be right and not sum.

    Moving one share alone breaks the sum; moving both in opposite directions
    keeps the sum and breaks the derivation. Two controls, two failure modes.
    """
    payload = _payload()
    _closing(payload, "P-2103")["buyer_share_cents"] -= 500
    assert _fired(check_own_proration_sums_to_annual(_ctx(payload)))
    assert not _fired(check_own_proration_by_days_held(_ctx(payload)))


def test_a_closing_on_the_first_day_of_the_fiscal_year_gives_the_seller_nothing() -> None:
    payload = _payload()
    _closing(payload, "P-2103")["close_of_escrow_date"] = "2029-01-01"
    rederive(payload)
    assert _closing(payload, "P-2103")["seller_share_cents"] == 0
    assert not _fired(check_own_proration_by_days_held(_ctx(payload)))


def test_proration_is_capped_at_a_full_year() -> None:
    """A closing beyond the year cannot hand the seller more than the whole charge."""
    payload = _payload()
    _closing(payload, "P-2103")["close_of_escrow_date"] = "2031-06-01"
    rederive(payload)
    closing = _closing(payload, "P-2103")
    assert closing["seller_share_cents"] == _parcel(payload, "P-2103")["annual_tax_cents"]
    assert closing["buyer_share_cents"] == 0


# --------------------------------------------------------------------------- #
# inst_matches_regime_calendar -- dates come from the regime, not a default
# --------------------------------------------------------------------------- #
def test_a_mid_year_regime_pushes_its_later_instalment_into_the_next_year() -> None:
    payload = _payload()
    assert _instalment(payload, "P-2241", 1)["due_date"] == "2029-12-10"
    assert _instalment(payload, "P-2241", 2)["due_date"] == "2030-04-10"
    assert not _fired(check_inst_matches_regime_calendar(_ctx(payload)))


def test_applying_another_jurisdictions_calendar_fails() -> None:
    """The Cascadia due date on an Ardenne parcel is exactly the real-world error."""
    payload = _payload()
    _instalment(payload, "P-2241", 1)["due_date"] = "2029-04-30"
    assert _fired(check_inst_matches_regime_calendar(_ctx(payload)))


def test_a_single_instalment_regime_takes_exactly_one() -> None:
    payload = _payload()
    schedule = _doc(payload, DOC_INSTALMENT_SCHEDULE)
    schedule["instalments"].append(
        {
            "parcel_no": "P-2311", "sequence": 2, "due_date": "2029-07-31",
            "amount_cents": 0, "penalty_cents": 0, "interest_cents": 0,
            "paid_date": None, "paid_amount_cents": 0, "receipt_reference": None,
        }
    )
    assert _fired(check_inst_matches_regime_calendar(_ctx(payload)))


# --------------------------------------------------------------------------- #
# inst_delinquency_recomputed -- penalty attaches once, interest accrues
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "days_late, periods",
    [(0, 0), (1, 0), (INTEREST_PERIOD_DAYS - 1, 0), (INTEREST_PERIOD_DAYS, 1),
     (INTEREST_PERIOD_DAYS * 2 + 5, 2)],
)
def test_interest_accrues_per_whole_period_only(days_late: int, periods: int) -> None:
    penalty, interest = derive_penalty_interest(1_000_000, days_late, 1200, 100)
    assert interest == (10_000 * periods)
    assert penalty == (120_000 if days_late > 0 else 0)


def test_penalty_attaches_once_however_late() -> None:
    """Penalty is a one-off on the instalment; only interest compounds with time."""
    early, _ = derive_penalty_interest(1_000_000, 1, 1200, 100)
    late, _ = derive_penalty_interest(1_000_000, 400, 1200, 100)
    assert early == late


def test_an_instalment_paid_on_its_due_date_is_not_late() -> None:
    payload = _payload()
    row = _instalment(payload, "P-2312", 1)
    row["paid_date"] = row["due_date"]
    rederive(payload)
    assert row["penalty_cents"] == 0
    assert not _fired(check_inst_delinquency_recomputed(_ctx(payload)))


def test_a_period_after_escrow_is_not_the_developers_delinquency() -> None:
    """The buyer's unpaid instalment must not surface as the seller's penalty."""
    payload = _payload()
    row = _instalment(payload, "P-2103", 2)
    assert row["paid_date"] is None
    assert row["penalty_cents"] == 0
    assert not _fired(check_inst_delinquency_recomputed(_ctx(payload)))


# --------------------------------------------------------------------------- #
# own_no_payment_after_escrow -- the headline control
# --------------------------------------------------------------------------- #
def test_paying_a_post_escrow_instalment_fails() -> None:
    payload = _payload()
    row = _instalment(payload, "P-2103", 2)
    row["paid_date"] = "2029-10-28"
    row["paid_amount_cents"] = row["amount_cents"]
    assert _fired(check_own_no_payment_after_escrow(_ctx(payload)))


def test_paying_a_pre_escrow_instalment_is_correct() -> None:
    """The seller genuinely owes the instalment that fell due before closing."""
    payload = _payload()
    assert _instalment(payload, "P-2103", 1)["paid_date"] is not None
    assert not _fired(check_own_no_payment_after_escrow(_ctx(payload)))


def test_an_unsold_parcel_is_out_of_scope_for_the_control() -> None:
    payload = _payload()
    _doc(payload, DOC_SALE_REGISTER)["closings"] = []
    rederive(payload)
    assert not _fired(check_own_no_payment_after_escrow(_ctx(payload)))


# --------------------------------------------------------------------------- #
# acr_stops_at_escrow -- the ledger side of the same fact
# --------------------------------------------------------------------------- #
def test_accrual_in_the_closing_month_is_allowed() -> None:
    """The developer owned the parcel for part of that month."""
    payload = _payload()
    assert _next_accrual(payload, "P-2103", "2029-05")["amount_cents"] > 0
    assert not _fired(check_acr_stops_at_escrow(_ctx(payload)))


def test_accrual_after_the_closing_month_fails() -> None:
    payload = _payload()
    _next_accrual(payload, "P-2103", "2029-06")["amount_cents"] = 100
    assert _fired(check_acr_stops_at_escrow(_ctx(payload)))


def _next_accrual(payload: dict, parcel_no: str, period: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_ACCRUAL_LEDGER)["accruals"]
        if r["parcel_no"] == parcel_no and r["period"] == period
    )


# --------------------------------------------------------------------------- #
# par_plat_completeness -- the retired parent does not count
# --------------------------------------------------------------------------- #
def test_a_retired_parent_parcel_is_not_a_live_lot() -> None:
    """Counting it would mask exactly the segregation gap the control looks for."""
    payload = _payload()
    assert _parcel(payload, "P-2100")["status"] == "retired"
    assert not _fired(check_par_plat_completeness(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_plat_count_must_match_exactly(delta: int, should_fail: bool) -> None:
    payload = _payload()
    projects = _doc(payload, DOC_PROJECT_REGISTER)["projects"]
    next(p for p in projects if p["code"] == "PRJ-210")["plat_lot_count"] = 4 + delta
    assert bool(_fired(check_par_plat_completeness(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# asmt_variance_surfaced -- the protest-review threshold
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("move_bps, should_flag", [(2400, False), (2500, False), (2600, True)])
def test_variance_flags_only_past_the_threshold(move_bps: int, should_flag: bool) -> None:
    payload = _payload()
    now = _parcel(payload, "P-2101")["assessed_total_cents"]
    prior = now * 10000 // (10000 + move_bps)
    history = _doc(payload, "assessment_history")
    next(r for r in history["prior_year"] if r["parcel_no"] == "P-2101")[
        "assessed_total_cents"
    ] = prior
    fired = _fired(check_asmt_variance_surfaced(_ctx(payload)))
    assert bool(fired) is should_flag


def test_variance_is_symmetric() -> None:
    """A collapse in value is as much a protest signal as a spike."""
    payload = _payload()
    now = _parcel(payload, "P-2101")["assessed_total_cents"]
    history = _doc(payload, "assessment_history")
    next(r for r in history["prior_year"] if r["parcel_no"] == "P-2101")[
        "assessed_total_cents"
    ] = now * 3
    fired = _fired(check_asmt_variance_surfaced(_ctx(payload)))
    assert fired and "down" in fired[0].message


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "par_parcel_unique": Status.FAIL,
    "par_required_fields": Status.FAIL,
    "par_project_mapped": Status.FAIL,
    "par_plat_completeness": Status.FAIL,
    "par_jurisdiction_known": Status.FAIL,
    "asmt_components_tie_total": Status.FAIL,
    "asmt_charge_follows_value": Status.FAIL,
    "asmt_variance_surfaced": Status.FLAG,
    "asmt_exemption_has_authority": Status.FLAG,
    "inst_shares_tie_annual": Status.FAIL,
    "inst_matches_regime_calendar": Status.FAIL,
    "inst_delinquency_recomputed": Status.FAIL,
    "inst_no_duplicate_payment": Status.FAIL,
    "inst_receipt_on_file": Status.FLAG,
    "own_sale_parcel_exists": Status.FAIL,
    "own_sold_parcel_flagged": Status.FAIL,
    "own_no_payment_after_escrow": Status.FAIL,
    "own_proration_sums_to_annual": Status.FAIL,
    "own_proration_by_days_held": Status.FAIL,
    "own_supplemental_on_transfer": Status.FLAG,
    "acr_periods_tie_annual": Status.FAIL,
    "acr_stops_at_escrow": Status.FAIL,
    "acr_ties_gl_liability": Status.FAIL,
    "acr_capitalisation_matches_stage": Status.FLAG,
    "pay_amount_ties_notice": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "par", "asmt", "inst", "own", "acr", "pay"}


def test_proration_convention_is_stated_once() -> None:
    """The convention is a constant, not a literal scattered through the controls."""
    assert PRORATION_DAYS == 365
    assert ASSESSMENT_VARIANCE_BPS == 2500
