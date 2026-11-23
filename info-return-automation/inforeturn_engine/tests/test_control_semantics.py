"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one day or one digit either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The threshold and withholding cases carry the most weight. A year total landing
exactly on a box threshold owes a form and a cent under it does not; a payee with
no taxpayer number owes a form however small the payment, because withheld tax is
reported whatever the payment was; and a shortfall sitting exactly at the edge of
the review band is inside it. Those three edges are the whole determination, and
the corpus is built to put a real row on each of them -- ``FRM-403-02`` sits on the
non-employee threshold to the cent, and ``FRM-402-04`` is owed only because
withholding attached to it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from inforeturn_engine.engine import (
    SEVERITY,
    check_box_catalog_unique,
    check_bwh_rate_recomputes,
    check_ent_payer_identity,
    check_frm_box_ties_ledger,
    check_frm_no_duplicates,
    check_frm_payer_identity,
    check_led_amounts_valid,
    check_led_payment_in_year,
    check_pye_tin_wellformed,
    check_pye_type_valid,
    check_rpt_annual_rollup_ties,
    check_rpt_transmittal_foots,
    check_rpt_watchlist_ties,
    check_thr_near_threshold_review,
    check_thr_no_unrequired_form,
    check_thr_required_form_issued,
)
from inforeturn_engine.generate import (
    BACKUP_WITHHOLDING_BPS,
    NEAR_THRESHOLD_CENTS,
    PORTFOLIOS,
    REPORTING_YEAR,
    baseline,
)
from inforeturn_engine.model import (
    DOC_BOX_CATALOG,
    DOC_ENTITY_REGISTER,
    DOC_FORM_REGISTER,
    DOC_ISSUANCE_REPORT,
    DOC_LEDGER_EXTRACT,
    DOC_PAYEE_REGISTER,
    DOC_THRESHOLD_WATCHLIST,
    DOC_TRANSMITTAL_REGISTER,
    FORM_NONEMPLOYEE,
    Context,
    Status,
)
from inforeturn_engine.money import apply_rate

#: The non-employee box threshold the corpus is built around, in cents.
NB1_THRESHOLD_CENTS = 75_000


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _form(payload: dict, form_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_FORM_REGISTER)["forms"]
        if r["form_id"] == form_id
    )


def _payment(payload: dict, payment_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_LEDGER_EXTRACT)["payments"]
        if r["payment_id"] == payment_id
    )


def _payee(payload: dict, payee_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_PAYEE_REGISTER)["payees"]
        if r["payee_id"] == payee_id
    )


def _entity(payload: dict, entity_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_ENTITY_REGISTER)["entities"]
        if r["entity_id"] == entity_id
    )


def _transmittal(payload: dict, entity_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_TRANSMITTAL_REGISTER)["transmittals"]
        if r["entity_id"] == entity_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# frm_box_ties_ledger -- the box is the payment lines, not a figure beside them
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_box_amount_ties_its_payment_lines_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _form(payload, "FRM-401-01")["box_amount_cents"] += delta
    assert bool(_fired(check_frm_box_ties_ledger(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_box_amount_follows_a_moved_payment_line(
    delta: int, should_fail: bool
) -> None:
    """Editing the ledger and not the form breaks the tie-out from the other side."""
    payload = _payload()
    _payment(payload, "PAY-4101")["amount_cents"] += delta
    assert bool(_fired(check_frm_box_ties_ledger(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# bwh_rate_recomputes -- the statutory rate, both directions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_withholding_recomputes_at_the_statutory_rate(
    delta: int, should_fail: bool
) -> None:
    """PYE-504 has no taxpayer number, so the rate applies to the reported amount."""
    payload = _payload()
    form = _form(payload, "FRM-401-03")
    expected = apply_rate(form["box_amount_cents"], BACKUP_WITHHOLDING_BPS)
    form["backup_withholding_cents"] = expected + delta
    assert bool(_fired(check_bwh_rate_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("stated, should_fail", [(0, False), (1, True)])
def test_a_payee_with_a_number_on_file_has_nothing_withheld(
    stated: int, should_fail: bool
) -> None:
    """Withholding taken where a number is on file is the payee's money held
    without cause, so the correct figure is exactly zero."""
    payload = _payload()
    _form(payload, "FRM-401-01")["backup_withholding_cents"] = stated
    assert bool(_fired(check_bwh_rate_recomputes(_ctx(payload)))) is should_fail


def test_withholding_attaches_below_the_threshold(reports) -> None:
    """FRM-402-04 reports 400.00 against a 750.00 threshold and still withholds.

    The payment is far under the box threshold. The form exists because the payee
    has no taxpayer number and the box attracts withholding, and withheld tax is
    reported however small the payment was.
    """
    payload = _payload()
    form = _form(payload, "FRM-402-04")
    assert form["box_amount_cents"] < NB1_THRESHOLD_CENTS
    assert form["backup_withholding_cents"] == apply_rate(
        form["box_amount_cents"], BACKUP_WITHHOLDING_BPS
    )
    assert not _fired(check_bwh_rate_recomputes(_ctx(payload)))


def test_card_settlement_never_withholds() -> None:
    """CB-1 does not attract withholding, so a missing number changes nothing there."""
    payload = _payload()
    _payee(payload, "PYE-505")["payee_tin"] = None
    assert _form(payload, "FRM-402-03")["backup_withholding_cents"] == 0
    assert not _fired(check_bwh_rate_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# thr_ -- a form is owed exactly where one is owed
# --------------------------------------------------------------------------- #
def test_a_total_exactly_on_the_threshold_owes_a_form() -> None:
    """ENT-403 pays PYE-503 exactly the non-employee threshold, and FRM-403-02
    reports it. Met *at* the cent is met."""
    payload = _payload()
    assert _form(payload, "FRM-403-02")["box_amount_cents"] == NB1_THRESHOLD_CENTS
    assert not _fired(check_thr_required_form_issued(_ctx(payload)))
    assert not _fired(check_thr_no_unrequired_form(_ctx(payload)))


def test_a_cent_under_the_threshold_owes_nothing() -> None:
    """A cent off that payment and the form on the register is no longer owed."""
    payload = _payload()
    _payment(payload, "PAY-4303")["amount_cents"] -= 1
    _form(payload, "FRM-403-02")["box_amount_cents"] -= 1
    fired = _fired(check_thr_no_unrequired_form(_ctx(payload)))
    assert fired
    assert "FRM-403-02" in fired[0].message


def test_a_required_form_that_is_missing_is_reported() -> None:
    payload = _payload()
    register = _doc(payload, DOC_FORM_REGISTER)
    register["forms"] = [r for r in register["forms"] if r["form_id"] != "FRM-403-02"]
    fired = _fired(check_thr_required_form_issued(_ctx(payload)))
    assert fired
    assert "PYE-503" in fired[0].message


def test_giving_the_withheld_payee_a_number_makes_its_form_unrequired() -> None:
    """The withholding override is the only reason FRM-402-04 is owed.

    Put a taxpayer number on file for PYE-507 and the below-threshold form stops
    being owed, which is what proves the override is doing the work rather than the
    threshold.
    """
    payload = _payload()
    _payee(payload, "PYE-507")["payee_tin"] = "FTN-500200077"
    fired = _fired(check_thr_no_unrequired_form(_ctx(payload)))
    assert fired
    assert "FRM-402-04" in fired[0].message


# --------------------------------------------------------------------------- #
# thr_near_threshold_review -- the band closes at exactly the stated span
# --------------------------------------------------------------------------- #
def test_no_payee_sits_in_the_review_band_on_the_baseline() -> None:
    """PYE-506 is paid well under its threshold, far outside the band."""
    assert not _fired(check_thr_near_threshold_review(_ctx(_payload())))


@pytest.mark.parametrize(
    "shortfall, should_flag",
    [(1, True), (NEAR_THRESHOLD_CENTS, True), (NEAR_THRESHOLD_CENTS + 1, False)],
)
def test_review_band_edge(shortfall: int, should_flag: bool) -> None:
    """The band is half-open: exactly ``near_threshold_cents`` short is inside it."""
    payload = _payload()
    _payment(payload, "PAY-4108")["amount_cents"] = NB1_THRESHOLD_CENTS - shortfall
    fired = _fired(check_thr_near_threshold_review(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_a_payee_that_reached_the_threshold_is_not_a_near_miss() -> None:
    """At the threshold a form is owed, which is a different control's business."""
    payload = _payload()
    _payment(payload, "PAY-4108")["amount_cents"] = NB1_THRESHOLD_CENTS
    assert not _fired(check_thr_near_threshold_review(_ctx(payload)))


# --------------------------------------------------------------------------- #
# led_ -- the payment population
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "when, should_fail",
    [
        (date(REPORTING_YEAR, 1, 1).isoformat(), False),
        (date(REPORTING_YEAR - 1, 12, 31).isoformat(), True),
        (date(REPORTING_YEAR, 12, 31).isoformat(), False),
        (date(REPORTING_YEAR + 1, 1, 1).isoformat(), True),
    ],
)
def test_payment_date_at_the_year_edges(when: str, should_fail: bool) -> None:
    """The reporting year is inclusive of both endpoints."""
    payload = _payload()
    _payment(payload, "PAY-4101")["paid_date"] = when
    assert bool(_fired(check_led_payment_in_year(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("amount, should_fail", [(1, False), (0, False), (-1, True)])
def test_a_payment_may_be_zero_but_not_negative(
    amount: int, should_fail: bool
) -> None:
    """A reversal is netted at source, not carried in as a negative box."""
    payload = _payload()
    _payment(payload, "PAY-4102")["amount_cents"] = amount
    assert bool(_fired(check_led_amounts_valid(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# pye_ -- the payee population
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tin, should_fail",
    [
        ("FTN-500200011", False),
        (None, False),
        ("FTN-50020001", True),
        ("FTN-5002000111", True),
        ("XYZ-500200011", True),
        ("FTN-50020001A", True),
        ("", True),
    ],
)
def test_taxpayer_number_shape(tin: object, should_fail: bool) -> None:
    """A number absent is a withholding case; a number present must be readable."""
    payload = _payload()
    _payee(payload, "PYE-501")["payee_tin"] = tin
    assert bool(_fired(check_pye_tin_wellformed(_ctx(payload)))) is should_fail


def test_an_unknown_payee_type_is_reported() -> None:
    payload = _payload()
    _payee(payload, "PYE-501")["payee_type"] = "beneficiary"
    fired = _fired(check_pye_type_valid(_ctx(payload)))
    assert fired
    assert "beneficiary" in fired[0].message


# --------------------------------------------------------------------------- #
# identity -- the payer on the form is the payer on the register
# --------------------------------------------------------------------------- #
def test_a_form_carrying_the_wrong_payer_number_is_reported() -> None:
    payload = _payload()
    _form(payload, "FRM-401-01")["payer_tin"] = "FTN-400100099"
    assert _fired(check_frm_payer_identity(_ctx(payload)))


def test_an_entity_with_an_unreadable_payer_number_is_reported() -> None:
    payload = _payload()
    _entity(payload, "ENT-401")["payer_tin"] = "FTN-4001000"
    assert _fired(check_ent_payer_identity(_ctx(payload)))


def test_two_forms_for_the_same_payee_and_box_are_a_duplicate() -> None:
    payload = _payload()
    register = _doc(payload, DOC_FORM_REGISTER)
    twin = dict(_form(payload, "FRM-401-01"))
    twin["form_id"] = "FRM-401-99"
    register["forms"].append(twin)
    assert _fired(check_frm_no_duplicates(_ctx(payload)))


def test_a_box_catalogued_twice_is_reported() -> None:
    payload = _payload()
    catalog = _doc(payload, DOC_BOX_CATALOG)
    catalog["boxes"].append(dict(catalog["boxes"][0]))
    assert _fired(check_box_catalog_unique(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rpt_ -- the transmittals and the rollup foot the forms
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "key", ["form_count", "total_reported_cents", "total_withheld_cents"]
)
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_transmittal_foots_to_the_cent(
    key: str, delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _transmittal(payload, "ENT-401")[key] += delta
    assert bool(_fired(check_rpt_transmittal_foots(_ctx(payload)))) is should_fail


@pytest.mark.parametrize(
    "key", ["form_count", "total_reported_cents", "total_withheld_cents"]
)
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_annual_rollup_foots_to_the_cent(
    key: str, delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_ISSUANCE_REPORT)[key] += delta
    assert bool(_fired(check_rpt_annual_rollup_ties(_ctx(payload)))) is should_fail


def test_watchlist_must_tie_the_population() -> None:
    payload = _payload()
    assert not _fired(check_rpt_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_THRESHOLD_WATCHLIST)["entries"].append(
        {
            "entity_id": "ENT-401",
            "payee_id": "PYE-501",
            "form_type": FORM_NONEMPLOYEE,
            "box_code": "NB-1",
            "amount_cents": 70_000,
            "shortfall_cents": 5_000,
        }
    )
    fired = _fired(check_rpt_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "ent_unique_ids": Status.FAIL,
    "ent_payer_identity": Status.FAIL,
    "pye_unique_ids": Status.FAIL,
    "pye_type_valid": Status.FAIL,
    "pye_tin_wellformed": Status.FAIL,
    "box_catalog_defined": Status.FAIL,
    "box_catalog_unique": Status.FAIL,
    "led_rows_attributable": Status.FAIL,
    "led_amounts_valid": Status.FAIL,
    "led_payment_in_year": Status.FAIL,
    "frm_required_fields": Status.FAIL,
    "frm_payer_identity": Status.FAIL,
    "frm_no_duplicates": Status.FAIL,
    "frm_box_ties_ledger": Status.FAIL,
    "thr_required_form_issued": Status.FAIL,
    "thr_no_unrequired_form": Status.FAIL,
    "thr_near_threshold_review": Status.FLAG,
    "bwh_rate_recomputes": Status.FAIL,
    "rpt_transmittal_foots": Status.FAIL,
    "rpt_annual_rollup_ties": Status.FAIL,
    "rpt_watchlist_ties": Status.FLAG,
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
        "set", "ent", "pye", "box", "led", "frm", "thr", "bwh", "rpt"
    }
