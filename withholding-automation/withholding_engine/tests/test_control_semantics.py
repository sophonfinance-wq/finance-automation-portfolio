"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent, one basis point or one status
either side of the line. A control that fires a cent early is as wrong as one that
never fires, and only a boundary test can tell the two apart.

The rate, tax and expiry cases carry the most weight. A tax figure right to the
cent must pass and a cent off must fail; a W-8 valid on the review date is not the
same as one expiring the day after; a renewal at the very edge of the lead window
is inside it and a day past the edge is not.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from withholding_engine.engine import (
    SEVERITY,
    check_dep_1042_filed_on_time,
    check_dep_total_ties_withheld,
    check_exm_fatca_override,
    check_exm_portfolio_interest_eligible,
    check_exm_w8_not_expired,
    check_exm_w8_present_for_treaty,
    check_exm_w8_renewal_window,
    check_rec_gross_ties,
    check_rec_slip_count_ties_1042t,
    check_rec_slip_per_payee,
    check_rec_w8_watchlist_ties,
    check_rec_withheld_ties,
    check_wh_accrued_not_withheld,
    check_wh_rate_recomputes,
    check_wh_tax_recomputes,
    check_wh_us_payee_excluded,
)
from withholding_engine.generate import AS_OF, FILERS, W8_RENEWAL_LEAD_DAYS, baseline
from withholding_engine.model import (
    DOC_DEPOSIT_REGISTER,
    DOC_FORM_1042,
    DOC_PAYEE_REGISTER,
    DOC_PAYMENT_REGISTER,
    DOC_SLIP_REGISTER,
    DOC_W8_WATCHLIST,
    Context,
    Status,
)
from withholding_engine.money import apply_rate
from withholding_engine.withholding import STATUTORY_RATE_BPS


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(FILERS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _payee(payload: dict, payee_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PAYEE_REGISTER)["payees"]
        if p["payee_id"] == payee_id
    )


def _payment(payload: dict, payment_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PAYMENT_REGISTER)["payments"]
        if p["payment_id"] == payment_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# wh_tax_recomputes -- the tax is rate x gross to the cent, not a cent off
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tax_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    payment = _payment(payload, "PMT-03")
    payment["tax_withheld_cents"] = apply_rate(
        payment["gross_cents"], payment["rate_applied_bps"]
    ) + delta
    assert bool(_fired(check_wh_tax_recomputes(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# wh_rate_recomputes -- the applied rate matches the determination exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rate, should_fail", [(1500, False), (1499, True), (1501, True), (3000, True)])
def test_rate_recomputes_from_determination(rate: int, should_fail: bool) -> None:
    """PMT-01 is a Marran dividend behind a valid W-8: the treaty rate is 15.00%."""
    payload = _payload()
    _payment(payload, "PMT-01")["rate_applied_bps"] = rate
    assert bool(_fired(check_wh_rate_recomputes(_ctx(payload)))) is should_fail


def test_rate_recompute_clean_on_baseline() -> None:
    assert not _fired(check_wh_rate_recomputes(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# wh_us_payee_excluded / wh_accrued_not_withheld -- the withholding gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("withheld, should_fail", [(0, False), (1, True)])
def test_us_payee_may_not_be_withheld(withheld: int, should_fail: bool) -> None:
    payload = _payload()
    payment = _payment(payload, "PMT-07")  # PAYEE-05 is the US person
    payment["tax_withheld_cents"] = withheld
    assert bool(_fired(check_wh_us_payee_excluded(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("withheld, should_fail", [(0, False), (1, True)])
def test_accrued_may_not_be_withheld(withheld: int, should_fail: bool) -> None:
    payload = _payload()
    payment = _payment(payload, "PMT-06")  # the accrued-only coupon
    payment["tax_withheld_cents"] = withheld
    assert bool(_fired(check_wh_accrued_not_withheld(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exm_fatca_override -- a non-participating FFI sits at statutory, no lower
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rate, should_fail", [(STATUTORY_RATE_BPS, False), (STATUTORY_RATE_BPS - 1, True), (0, True)])
def test_fatca_override_forces_statutory(rate: int, should_fail: bool) -> None:
    """PMT-04 pays PAYEE-04, a non-participating FFI (Chapter 4 code 09)."""
    payload = _payload()
    _payment(payload, "PMT-04")["rate_applied_bps"] = rate
    assert bool(_fired(check_exm_fatca_override(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exm_portfolio_interest_eligible -- contingent interest is barred from it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "subchar, should_fail",
    [("base", False), ("make_whole", False), ("contingent", True)],
)
def test_portfolio_interest_excludes_contingent(subchar: str, should_fail: bool) -> None:
    """PMT-02 is coded portfolio interest (income code 02)."""
    payload = _payload()
    _payment(payload, "PMT-02")["interest_subcharacter"] = subchar
    assert bool(_fired(check_exm_portfolio_interest_eligible(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exm_w8_present_for_treaty -- a treaty-reduced rate needs a W-8 on file
# --------------------------------------------------------------------------- #
def test_treaty_reduction_requires_a_w8() -> None:
    payload = _payload()
    assert not _fired(check_exm_w8_present_for_treaty(_ctx(payload)))
    _payee(payload, "PAYEE-01")["has_valid_w8"] = False
    assert _fired(check_exm_w8_present_for_treaty(_ctx(payload)))


# --------------------------------------------------------------------------- #
# exm_w8_not_expired -- expired on the review date, not the day after
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(0, True), (1, False)])
def test_w8_expired_on_the_review_date(offset: int, should_fail: bool) -> None:
    """A W-8 expiring exactly on ``as_of`` has lapsed; one day later still supports
    the claim. PAYEE-03 sits at Kelder's statutory rate, so only the expiry control
    reacts."""
    payload = _payload()
    expiration = (_as_of() + timedelta(days=offset)).isoformat()
    _payee(payload, "PAYEE-03")["w8_expiration"] = expiration
    assert bool(_fired(check_exm_w8_not_expired(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exm_w8_renewal_window -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset, should_flag",
    [(W8_RENEWAL_LEAD_DAYS, True), (W8_RENEWAL_LEAD_DAYS + 1, False)],
)
def test_w8_renewal_window_edge(offset: int, should_flag: bool) -> None:
    """A W-8 ending exactly ``lead_days`` out is inside the window; a day past it is
    not."""
    payload = _payload()
    expiration = (_as_of() + timedelta(days=offset)).isoformat()
    _payee(payload, "PAYEE-03")["w8_expiration"] = expiration
    fired = _fired(check_exm_w8_renewal_window(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_w8_renewal_window_is_clean_far_out() -> None:
    """The baseline W-8s expire well beyond the window and raise no flag."""
    assert not _fired(check_exm_w8_renewal_window(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# dep_total_ties_withheld -- the deposits equal the liability to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True), (-1, True)])
def test_deposits_tie_the_withheld(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_DEPOSIT_REGISTER)["deposits"][0]["amount_cents"] += delta
    assert bool(_fired(check_dep_total_ties_withheld(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# dep_1042_filed_on_time -- filing on the due date is timely, a day late is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("filed, should_fail", [("2030-03-15", False), ("2030-03-14", False), ("2030-03-16", True)])
def test_filed_on_or_before_due(filed: str, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_FORM_1042)["filed_date"] = filed
    assert bool(_fired(check_dep_1042_filed_on_time(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rec_ -- the return recomputes from the slips, not the other way round
# --------------------------------------------------------------------------- #
def test_gross_must_tie_the_slips() -> None:
    payload = _payload()
    assert not _fired(check_rec_gross_ties(_ctx(payload)))
    _doc(payload, DOC_FORM_1042)["total_gross_cents"] += 1
    assert _fired(check_rec_gross_ties(_ctx(payload)))


def test_withheld_must_tie_the_slips() -> None:
    payload = _payload()
    assert not _fired(check_rec_withheld_ties(_ctx(payload)))
    _doc(payload, DOC_FORM_1042)["total_withheld_cents"] += 1
    assert _fired(check_rec_withheld_ties(_ctx(payload)))


def test_slip_count_must_tie_the_1042t() -> None:
    payload = _payload()
    assert not _fired(check_rec_slip_count_ties_1042t(_ctx(payload)))
    _doc(payload, DOC_FORM_1042)["transmitted_count"] += 1
    assert _fired(check_rec_slip_count_ties_1042t(_ctx(payload)))


def test_slip_per_reportable_payee() -> None:
    payload = _payload()
    assert not _fired(check_rec_slip_per_payee(_ctx(payload)))
    slips = _doc(payload, DOC_SLIP_REGISTER)["slips"]
    slips.pop()
    assert _fired(check_rec_slip_per_payee(_ctx(payload)))


def test_watchlist_must_tie_the_evidence() -> None:
    payload = _payload()
    assert not _fired(check_rec_w8_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_W8_WATCHLIST)["entries"].append(
        {"payee_id": "PAYEE-01", "w8_expiration": "2031-06-30", "days_remaining": 546}
    )
    fired = _fired(check_rec_w8_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "payee_unique_ids": Status.FAIL,
    "payee_country_known": Status.FAIL,
    "payee_ch3_status_valid": Status.FAIL,
    "payee_ch4_status_valid": Status.FAIL,
    "payee_lob_code_valid": Status.FAIL,
    "rate_table_defined": Status.FAIL,
    "rate_within_bounds": Status.FAIL,
    "pay_required_fields": Status.FAIL,
    "pay_income_code_known": Status.FAIL,
    "pay_payee_exists": Status.FAIL,
    "pay_status_valid": Status.FAIL,
    "wh_us_payee_excluded": Status.FAIL,
    "wh_accrued_not_withheld": Status.FAIL,
    "wh_rate_recomputes": Status.FAIL,
    "wh_tax_recomputes": Status.FAIL,
    "exm_w8_present_for_treaty": Status.FAIL,
    "exm_w8_not_expired": Status.FAIL,
    "exm_w8_renewal_window": Status.FLAG,
    "exm_portfolio_interest_eligible": Status.FAIL,
    "exm_fatca_override": Status.FAIL,
    "dep_total_ties_withheld": Status.FAIL,
    "dep_1042_filed_on_time": Status.FAIL,
    "rec_slip_per_payee": Status.FAIL,
    "rec_gross_ties": Status.FAIL,
    "rec_withheld_ties": Status.FAIL,
    "rec_slip_count_ties_1042t": Status.FAIL,
    "rec_w8_watchlist_ties": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "payee", "rate", "pay", "wh", "exm", "dep", "rec"}
