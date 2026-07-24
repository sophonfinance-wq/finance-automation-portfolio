"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The coverage and tier cases carry the most weight. A payment can foot to a waiver
amount and still be released only *conditionally* after the cheque cleared; a
lower-tier release can be on file and still stop a day short of the money above
it. Each of those boundaries is one day or one cent wide.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from lien_engine.engine import (
    SEVERITY,
    check_cov_cleared_unconditional,
    check_cov_payment_covered,
    check_cov_stale_conditional,
    check_exp_recomputes,
    check_party_tier_valid,
    check_pay_dates_sensible,
    check_tier_required_recomputes,
    check_tier_waiver_covers,
    check_wvr_amount_ties_payment,
)
from lien_engine.generate import PORTFOLIOS, STALE_CONDITIONAL_DAYS, baseline
from lien_engine.model import (
    DOC_CONTRACT_REGISTER,
    DOC_EXPOSURE_SUMMARY,
    DOC_LOWER_TIER_REGISTER,
    DOC_PAYMENT_REGISTER,
    DOC_WAIVER_REGISTER,
    Context,
    Status,
)

AS_OF = date(2031, 3, 15)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _payment(payload: dict, payment_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PAYMENT_REGISTER)["payments"]
        if p["payment_id"] == payment_id
    )


def _waiver(payload: dict, waiver_id: str) -> dict:
    return next(
        w for w in _doc(payload, DOC_WAIVER_REGISTER)["waivers"]
        if w["waiver_id"] == waiver_id
    )


def _party(payload: dict, party_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_LOWER_TIER_REGISTER)["parties"]
        if p["party_id"] == party_id
    )


def _sub(payload: dict, sub_id: str) -> dict:
    return next(
        s for s in _doc(payload, DOC_CONTRACT_REGISTER)["subcontracts"]
        if s["sub_id"] == sub_id
    )


def _exposure(payload: dict, project: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_EXPOSURE_SUMMARY)["projects"]
        if r["project"] == project
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _iso(day: date) -> str:
    return day.isoformat()


# --------------------------------------------------------------------------- #
# cov_payment_covered -- a waiver must reach the paid-through date, to the day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta_days, should_fail", [(-1, True), (0, False), (1, False)])
def test_a_waiver_must_reach_the_paid_through_date(delta_days: int, should_fail: bool) -> None:
    """PAY-2 is paid through 2031-02-28 and carries only a conditional waiver.

    The waiver releasing a day short leaves the money unwaived; releasing on the
    day, or beyond, covers it.
    """
    payload = _payload()
    paid_through = date.fromisoformat(_payment(payload, "PAY-2")["paid_through_date"])
    _waiver(payload, "WV-C-PAY-2")["through_date"] = _iso(paid_through + timedelta(days=delta_days))
    assert bool(_fired(check_cov_payment_covered(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cov_cleared_unconditional -- the conditional does not survive the cheque
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta_days, should_fail", [(-1, True), (0, False), (1, False)])
def test_a_cleared_payment_needs_an_unconditional_that_reaches_the_date(
    delta_days: int, should_fail: bool
) -> None:
    """PAY-1 cleared and is paid through 2031-01-31.

    A conditional waiver reaches that date, so ``cov_payment_covered`` stays quiet;
    only the unconditional running short is a failure here, and only this control
    can see it.
    """
    payload = _payload()
    paid_through = date.fromisoformat(_payment(payload, "PAY-1")["paid_through_date"])
    _waiver(payload, "WV-U-PAY-1")["through_date"] = _iso(paid_through + timedelta(days=delta_days))
    assert bool(_fired(check_cov_cleared_unconditional(_ctx(payload)))) is should_fail
    # The conditional still reaches the date, so the payment is nominally covered.
    assert not _fired(check_cov_payment_covered(_ctx(payload)))


# --------------------------------------------------------------------------- #
# cov_stale_conditional -- the ageing band is the register's, not the engine's
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "aged_days, should_flag",
    [(STALE_CONDITIONAL_DAYS, False), (STALE_CONDITIONAL_DAYS + 1, True)],
)
def test_conditional_ages_out_exactly_at_the_band(aged_days: int, should_flag: bool) -> None:
    """PAY-6 is uncleared and under a sub with no lower-tier party.

    Aged exactly to the band it is still inside the window; one day past, it is
    flagged for upgrade.
    """
    payload = _payload()
    _payment(payload, "PAY-6")["paid_through_date"] = _iso(AS_OF - timedelta(days=aged_days))
    fired = _fired(check_cov_stale_conditional(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# wvr_amount_ties_payment -- the release ties the payment to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta_cents, should_fail", [(-1, True), (0, False), (1, True)])
def test_waiver_amount_ties_to_the_cent(delta_cents: int, should_fail: bool) -> None:
    payload = _payload()
    _waiver(payload, "WV-U-PAY-4")["amount_cents"] += delta_cents
    assert bool(_fired(check_wvr_amount_ties_payment(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# tier_waiver_covers -- the lower-tier release reaches the parent's paid date
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta_days, should_fail", [(-1, True), (0, False), (1, False)])
def test_lower_tier_release_reaches_the_parents_paid_date(
    delta_days: int, should_fail: bool
) -> None:
    payload = _payload()
    required = date.fromisoformat(_party(payload, "LTP-1")["required_through_date"])
    _party(payload, "LTP-1")["waiver_through_date"] = _iso(required + timedelta(days=delta_days))
    assert bool(_fired(check_tier_waiver_covers(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# tier_required_recomputes -- the required date is the parent's latest paid date
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta_days, should_fail", [(-1, True), (0, False), (1, True)])
def test_required_through_date_recomputes_from_the_parent(
    delta_days: int, should_fail: bool
) -> None:
    payload = _payload()
    derived = date.fromisoformat(_party(payload, "LTP-1")["required_through_date"])
    _party(payload, "LTP-1")["required_through_date"] = _iso(derived + timedelta(days=delta_days))
    assert bool(_fired(check_tier_required_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exp_recomputes -- unwaived exposure re-derives to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta_cents, should_fail", [(-1, True), (0, False), (1, True)])
def test_exposure_recomputes_to_the_cent(delta_cents: int, should_fail: bool) -> None:
    payload = _payload()
    _exposure(payload, "Brightwater Commons")["unwaived_exposure_cents"] += delta_cents
    assert bool(_fired(check_exp_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# pay_dates_sensible -- paid through the review date is fine; a day past is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta_days, should_fail", [(0, False), (1, True)])
def test_paid_through_may_reach_but_not_pass_the_review_date(
    delta_days: int, should_fail: bool
) -> None:
    payload = _payload()
    _payment(payload, "PAY-3")["paid_through_date"] = _iso(AS_OF + timedelta(days=delta_days))
    assert bool(_fired(check_pay_dates_sensible(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# party_tier_valid -- a tier is a whole number one or greater
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier, should_fail", [(1, False), (0, True), (-1, True)])
def test_tier_must_be_one_or_greater(tier: int, should_fail: bool) -> None:
    payload = _payload()
    _sub(payload, "SUB-200")["tier"] = tier
    assert bool(_fired(check_party_tier_valid(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "party_required_fields": Status.FAIL,
    "party_unique_ids": Status.FAIL,
    "party_tier_valid": Status.FAIL,
    "party_lower_tier_parent": Status.FAIL,
    "party_project_exists": Status.FAIL,
    "pay_required_fields": Status.FAIL,
    "pay_sub_exists": Status.FAIL,
    "pay_amount_positive": Status.FAIL,
    "pay_dates_sensible": Status.FAIL,
    "wvr_required_fields": Status.FAIL,
    "wvr_unique_ids": Status.FAIL,
    "wvr_type_valid": Status.FAIL,
    "wvr_references_payment": Status.FAIL,
    "wvr_amount_ties_payment": Status.FAIL,
    "cov_payment_covered": Status.FAIL,
    "cov_cleared_unconditional": Status.FAIL,
    "cov_stale_conditional": Status.FLAG,
    "tier_party_has_waiver": Status.FAIL,
    "tier_waiver_covers": Status.FAIL,
    "tier_required_recomputes": Status.FAIL,
    "exp_recomputes": Status.FAIL,
    "exp_all_projects_present": Status.FAIL,
    "rpt_waiver_counts_tie": Status.FAIL,
    "rpt_covered_count_ties": Status.FLAG,
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
        "set", "party", "pay", "wvr", "cov", "tier", "exp", "rpt"
    }
