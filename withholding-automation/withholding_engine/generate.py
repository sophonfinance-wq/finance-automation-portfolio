"""
Fictional non-resident withholding corpus generator.
====================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The filers, the foreign payees, the jurisdictions,
the banks and benefit providers, the treaty rates, the income codes and the
amounts are fictional, and the reporting period is set in a fictional future. No
real entity, person, jurisdiction, bank or path appears anywhere. The generator is
deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the payees, the treaty table, the income-code table, the payment base facts
(gross, income code, sub-character, status) and the deposits are stated. Everything
the engine later checks as a determination or rollup -- each payment's applied rate
and tax withheld, the 1042-S slips, the Form 1042 totals, the W-8 renewal
watchlist -- is recomputed by :func:`rederive` from those base facts, the rate
through the *same* :mod:`withholding_engine.withholding` kernel the engine
recomputes with. So the relationships the engine tests are the relationships that
produced the data: a defect that changes a base fact re-derives the rollup and
keeps the break confined to one control; a defect that targets a stated
determination edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    _income_type_of,
    _is_portfolio,
    _payee_map,
    _payments,
    _text,
    _treaty_map,
    _w8_valid_for,
    recompute_slips,
    recompute_w8_watchlist,
)
from .model import (
    CH3_US_PERSON,
    DEFAULT_W8_RENEWAL_LEAD_DAYS,
    DOC_DEPOSIT_REGISTER,
    DOC_FORM_1042,
    DOC_INCOME_CODE_TABLE,
    DOC_PAYEE_REGISTER,
    DOC_PAYMENT_REGISTER,
    DOC_SLIP_REGISTER,
    DOC_TREATY_RATE_TABLE,
    DOC_W8_WATCHLIST,
    INTEREST_BASE,
    INTEREST_CONTINGENT,
    NONPARTICIPATING_FFI_CODES,
    PAYMENT_STATUS_ACCRUED,
    PAYMENT_STATUS_PAID,
    W8_STATUS_VALID,
    Context,
)
from .money import apply_rate
from .withholding import STATUTORY_RATE_BPS, determined_rate_bps

#: Fictional filer labels, rotated for file identity only.
FILERS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

PERIOD = "FY2029"
#: The review date every expiry and renewal test is measured to.
AS_OF = "2029-12-31"
#: Lead-time window, in days, for the W-8 renewal watchlist.
W8_RENEWAL_LEAD_DAYS = 60
#: Form 1042 due date and (timely) filed date for the cycle.
DUE_DATE = "2030-03-15"
FILED_DATE = "2030-03-10"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(payee_id, name, country, ch3_status, ch4_status, has_valid_w8, w8_status,
#:   w8_expiration, lob_code)``. Invented foreign recipients; one US person for
#: the exclusion case. W-8 terms sit well beyond the review date so the clean
#: baseline raises neither an expiry FAIL nor a renewal FLAG.
PAYEES: tuple[tuple[Any, ...], ...] = (
    ("PAYEE-01", "Copperline Holdings Ltd", "Marran", "16", "22", True, W8_STATUS_VALID, "2031-06-30", "03"),
    ("PAYEE-02", "Aldermere Capital Ltd", "Marran", "16", "22", True, W8_STATUS_VALID, "2031-09-30", "04"),
    ("PAYEE-03", "Harborline Bank", "Kelder", "16", "22", True, W8_STATUS_VALID, "2031-03-31", "01"),
    ("PAYEE-04", "Vantage Benefits", "Marran", "16", "09", True, W8_STATUS_VALID, "2031-12-31", "02"),
    ("PAYEE-05", "Westmere Funding LLC", "Domitia", CH3_US_PERSON, "22", False, "", "", ""),
)

#: ``(country, income_type, rate_bps)``. A full grid over the two fictional
#: jurisdictions. Marran is a treaty partner (reduced interest/royalty, a 15%
#: dividend rate); Kelder's treaty has lapsed, so every Kelder rate sits at the
#: statutory default -- the hard country-membership branch.
TREATY_RATES: tuple[tuple[Any, ...], ...] = (
    ("Marran", "interest", 0),
    ("Marran", "dividend", 1500),
    ("Marran", "royalty", 0),
    ("Marran", "rent", 3000),
    ("Kelder", "interest", 3000),
    ("Kelder", "dividend", 3000),
    ("Kelder", "royalty", 3000),
    ("Kelder", "rent", 3000),
)

#: ``(code, income_type, portfolio_interest)``. The fixed 1042-S income-code list.
INCOME_CODES: tuple[tuple[Any, ...], ...] = (
    ("01", "interest", False),
    ("02", "interest", True),
    ("06", "dividend", False),
    ("12", "royalty", False),
    ("14", "rent", False),
)

#: ``(payment_id, payee_id, income_code, interest_subcharacter, payment_status,
#:   gross_dollars)``. Base facts only -- the applied rate and tax withheld are
#: derived. PAYEE-01 has two paid payments (aggregated onto one slip); PAYEE-02
#: has a paid portfolio coupon and an accrued-only coupon; PAYEE-05 is the US
#: person whose payment is excluded from withholding.
PAYMENTS: tuple[tuple[Any, ...], ...] = (
    ("PMT-01", "PAYEE-01", "06", INTEREST_BASE, PAYMENT_STATUS_PAID, 1_000_000),
    ("PMT-02", "PAYEE-02", "02", INTEREST_BASE, PAYMENT_STATUS_PAID, 2_000_000),
    ("PMT-03", "PAYEE-03", "01", INTEREST_BASE, PAYMENT_STATUS_PAID, 800_000),
    ("PMT-04", "PAYEE-04", "06", INTEREST_BASE, PAYMENT_STATUS_PAID, 600_000),
    ("PMT-05", "PAYEE-01", "01", INTEREST_BASE, PAYMENT_STATUS_PAID, 500_000),
    ("PMT-06", "PAYEE-02", "01", INTEREST_BASE, PAYMENT_STATUS_ACCRUED, 300_000),
    ("PMT-07", "PAYEE-05", "01", INTEREST_BASE, PAYMENT_STATUS_PAID, 400_000),
)

#: ``(deposit_id, deposit_date, amount_dollars)``. Sum ties the tax withheld.
DEPOSITS: tuple[tuple[Any, ...], ...] = (
    ("DEP-01", "2029-07-15", 300_000),
    ("DEP-02", "2030-01-15", 270_000),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _payee(payload: dict[str, Any], payee_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PAYEE_REGISTER)
    assert register is not None
    for row in register["payees"]:
        if row.get("payee_id") == payee_id:
            return row
    raise KeyError(payee_id)


def _payment(payload: dict[str, Any], payment_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PAYMENT_REGISTER)
    assert register is not None
    for row in register["payments"]:
        if row.get("payment_id") == payment_id:
            return row
    raise KeyError(payment_id)


def _treaty_table(payload: dict[str, Any]) -> dict[str, Any]:
    table = _doc(payload, DOC_TREATY_RATE_TABLE)
    assert table is not None
    return table


def _slip_doc(payload: dict[str, Any]) -> dict[str, Any]:
    slip = _doc(payload, DOC_SLIP_REGISTER)
    assert slip is not None
    return slip


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_W8_WATCHLIST)
    assert watchlist is not None
    return watchlist


def _form(payload: dict[str, Any]) -> dict[str, Any]:
    form = _doc(payload, DOC_FORM_1042)
    assert form is not None
    return form


def _deposit(payload: dict[str, Any], deposit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_DEPOSIT_REGISTER)
    assert register is not None
    for row in register["deposits"]:
        if row.get("deposit_id") == deposit_id:
            return row
    raise KeyError(deposit_id)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every determination and rollup from the payload's base facts."""
    if not all(
        _doc(payload, dt)
        for dt in (
            DOC_PAYEE_REGISTER,
            DOC_TREATY_RATE_TABLE,
            DOC_INCOME_CODE_TABLE,
            DOC_PAYMENT_REGISTER,
            DOC_DEPOSIT_REGISTER,
            DOC_SLIP_REGISTER,
            DOC_W8_WATCHLIST,
            DOC_FORM_1042,
        )
    ):
        return

    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    lead = payload.get("w8_renewal_lead_days", DEFAULT_W8_RENEWAL_LEAD_DAYS)
    payees = _payee_map(ctx)
    treaty = _treaty_map(ctx)

    # Payment determinations: the applied rate is recomputed through the shared
    # kernel; the tax withheld is that rate applied to the gross. Non-subject
    # payments (accrued, or paid to a US person) carry a zero rate and no tax.
    for payment in _payments(ctx):
        payee = payees.get(_text(payment, "payee_id") or "")
        gross = payment.get("gross_cents", 0)
        subject = (
            payee is not None
            and _text(payment, "payment_status") == PAYMENT_STATUS_PAID
            and _text(payee, "chapter_3_status_code") != CH3_US_PERSON
        )
        if not subject or payee is None:
            payment["rate_applied_bps"] = 0
            payment["tax_withheld_cents"] = 0
            continue
        income_type = _income_type_of(ctx, payment)
        treaty_rate = treaty.get((_text(payee, "country") or "", income_type or "")) if income_type else None
        rate = determined_rate_bps(
            is_nonparticipating_ffi=_text(payee, "chapter_4_status_code") in NONPARTICIPATING_FFI_CODES,
            is_portfolio_interest=_is_portfolio(ctx, payment),
            is_contingent_interest=_text(payment, "interest_subcharacter") == INTEREST_CONTINGENT,
            w8_valid=_w8_valid_for(payee, as_of),
            treaty_rate_bps=treaty_rate,
        )
        rate = STATUTORY_RATE_BPS if rate is None else rate
        payment["rate_applied_bps"] = rate
        payment["tax_withheld_cents"] = apply_rate(gross, rate)

    # 1042-S slips: one per reportable payee, aggregated from the payments.
    slips = recompute_slips(ctx)
    _slip_doc(payload)["slips"] = slips

    # W-8 renewal watchlist: payees whose valid W-8 is inside the lead window.
    _watchlist(payload)["entries"] = recompute_w8_watchlist(ctx, as_of, lead)

    # Form 1042 panel: totals rebuilt from the slips and the deposits.
    form = _form(payload)
    form["total_gross_cents"] = sum(s["gross_cents"] for s in slips)
    form["total_withheld_cents"] = sum(s["withheld_cents"] for s in slips)
    form["total_deposits_cents"] = sum(
        dep.get("amount_cents", 0) for dep in _doc(payload, DOC_DEPOSIT_REGISTER)["deposits"]
    )
    form["slip_count"] = len(slips)
    form["transmitted_count"] = len(slips)


def baseline(filer: str) -> dict[str, Any]:
    """Build a clean withholding file for ``filer``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "filer": filer,
        "period": PERIOD,
        "as_of": AS_OF,
        "w8_renewal_lead_days": W8_RENEWAL_LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_PAYEE_REGISTER,
                "document_id": "PAYEES-2029",
                "payees": [
                    {
                        "payee_id": payee_id,
                        "name": name,
                        "country": country,
                        "chapter_3_status_code": ch3,
                        "chapter_4_status_code": ch4,
                        "has_valid_w8": has_w8,
                        "w8_status": w8_status,
                        "w8_expiration": w8_expiration,
                        "lob_code": lob,
                    }
                    for payee_id, name, country, ch3, ch4, has_w8, w8_status, w8_expiration, lob in PAYEES
                ],
            },
            {
                "doc_type": DOC_TREATY_RATE_TABLE,
                "document_id": "TREATY-2029",
                "rates": [
                    {"country": country, "income_type": income_type, "rate_bps": rate}
                    for country, income_type, rate in TREATY_RATES
                ],
            },
            {
                "doc_type": DOC_INCOME_CODE_TABLE,
                "document_id": "CODES-2029",
                "codes": [
                    {"code": code, "income_type": income_type, "portfolio_interest": portfolio}
                    for code, income_type, portfolio in INCOME_CODES
                ],
            },
            {
                "doc_type": DOC_PAYMENT_REGISTER,
                "document_id": "PAYMENTS-2029",
                "payments": [
                    {
                        "payment_id": payment_id,
                        "payee_id": payee_id,
                        "income_code": income_code,
                        "interest_subcharacter": subchar,
                        "payment_status": status,
                        "gross_cents": d(gross),
                        "rate_applied_bps": 0,
                        "tax_withheld_cents": 0,
                    }
                    for payment_id, payee_id, income_code, subchar, status, gross in PAYMENTS
                ],
            },
            {
                "doc_type": DOC_DEPOSIT_REGISTER,
                "document_id": "DEPOSITS-2029",
                "deposits": [
                    {"deposit_id": deposit_id, "deposit_date": deposit_date, "amount_cents": d(amount)}
                    for deposit_id, deposit_date, amount in DEPOSITS
                ],
            },
            {
                "doc_type": DOC_SLIP_REGISTER,
                "document_id": "SLIPS-2029",
                "slips": [],
            },
            {
                "doc_type": DOC_W8_WATCHLIST,
                "document_id": "WATCHLIST-2029",
                "entries": [],
            },
            {
                "doc_type": DOC_FORM_1042,
                "document_id": "FORM1042-2029",
                "total_gross_cents": 0,
                "total_withheld_cents": 0,
                "total_deposits_cents": 0,
                "slip_count": 0,
                "transmitted_count": 0,
                "due_date": DUE_DATE,
                "filed_date": FILED_DATE,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control
# --------------------------------------------------------------------------- #
def _missing_artifact(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_FORM_1042
    ]


def _duplicate_payee_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_PAYEE_REGISTER)
    assert register is not None
    register["payees"].append(dict(_payee(payload, "PAYEE-01")))


def _unknown_country(payload: dict[str, Any]) -> None:
    # A residence country the treaty table does not carry; the country check owns
    # it while the treaty branch of the rate determination simply cannot resolve.
    _payee(payload, "PAYEE-02")["country"] = "Ostreach"


def _bad_ch3_status(payload: dict[str, Any]) -> None:
    _payee(payload, "PAYEE-03")["chapter_3_status_code"] = "ZZ"


def _bad_ch4_status(payload: dict[str, Any]) -> None:
    _payee(payload, "PAYEE-03")["chapter_4_status_code"] = "88"


def _bad_lob_code(payload: dict[str, Any]) -> None:
    _payee(payload, "PAYEE-01")["lob_code"] = "99"


def _rate_row_missing(payload: dict[str, Any]) -> None:
    # The Marran dividend rate is gone; PAYEE-01's dividend can no longer be rated
    # by the treaty branch, so the completeness control owns the gap.
    table = _treaty_table(payload)
    table["rates"] = [
        r for r in table["rates"] if not (r["country"] == "Marran" and r["income_type"] == "dividend")
    ]


def _rate_out_of_bounds(payload: dict[str, Any]) -> None:
    # An unused cell (Marran rent) is pushed above the statutory ceiling, so the
    # bounds control fires without disturbing any payment's determination.
    for row in _treaty_table(payload)["rates"]:
        if row["country"] == "Marran" and row["income_type"] == "rent":
            row["rate_bps"] = 3100


def _payment_missing_field(payload: dict[str, Any]) -> None:
    del _payment(payload, "PMT-03")["income_code"]


def _unknown_income_code(payload: dict[str, Any]) -> None:
    _payment(payload, "PMT-01")["income_code"] = "77"


def _unknown_payment_payee(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_PAYMENT_REGISTER)
    assert register is not None
    register["payments"].append(
        {
            "payment_id": "PMT-99",
            "payee_id": "PAYEE-999",
            "income_code": "01",
            "interest_subcharacter": INTEREST_BASE,
            "payment_status": PAYMENT_STATUS_PAID,
            "gross_cents": d(100_000),
            "rate_applied_bps": 0,
            "tax_withheld_cents": 0,
        }
    )


def _bad_payment_status(payload: dict[str, Any]) -> None:
    # The accrued coupon is given an unknown status; it stays out of scope so the
    # tie-outs are untouched and only the status-vocabulary control sees it.
    _payment(payload, "PMT-06")["payment_status"] = "pending"


def _us_payee_withheld(payload: dict[str, Any]) -> None:
    # The US payee is erroneously withheld at the statutory rate; rate and tax stay
    # internally consistent so only the exclusion control fires.
    payment = _payment(payload, "PMT-07")
    payment["rate_applied_bps"] = STATUTORY_RATE_BPS
    payment["tax_withheld_cents"] = apply_rate(payment["gross_cents"], STATUTORY_RATE_BPS)


def _accrued_withheld(payload: dict[str, Any]) -> None:
    # The accrued coupon is withheld on as though paid; rate and tax stay
    # consistent so only the accrued-gate control fires.
    payment = _payment(payload, "PMT-06")
    payment["rate_applied_bps"] = STATUTORY_RATE_BPS
    payment["tax_withheld_cents"] = apply_rate(payment["gross_cents"], STATUTORY_RATE_BPS)


def _rate_applied_wrong(payload: dict[str, Any]) -> None:
    # A treaty payee is under-rated: the stated rate no longer recomputes.
    _payment(payload, "PMT-01")["rate_applied_bps"] = 1000


def _tax_withheld_wrong(payload: dict[str, Any]) -> None:
    _payment(payload, "PMT-03")["tax_withheld_cents"] += d(1_000)


def _treaty_without_w8(payload: dict[str, Any]) -> None:
    # The reduced dividend rate on PAYEE-01 stays, but its W-8 support is removed.
    _payee(payload, "PAYEE-01")["has_valid_w8"] = False


def _w8_expired(payload: dict[str, Any]) -> None:
    # PAYEE-03's W-8 lapses before the review date. Kelder's treaty rate equals the
    # statutory default, so the recomputed rate is unchanged and only the expiry
    # control fires.
    _payee(payload, "PAYEE-03")["w8_expiration"] = "2029-06-30"


def _w8_renewal_due(payload: dict[str, Any]) -> None:
    # PAYEE-04's W-8 expires inside the lead-time window but is still valid; the
    # rollup is re-derived so only the renewal FLAG remains.
    _payee(payload, "PAYEE-04")["w8_expiration"] = "2030-02-09"
    rederive(payload)


def _portfolio_contingent(payload: dict[str, Any]) -> None:
    # The portfolio-interest coupon is actually contingent interest, which is
    # ineligible for the exemption.
    _payment(payload, "PMT-02")["interest_subcharacter"] = INTEREST_CONTINGENT


def _fatca_override_ignored(payload: dict[str, Any]) -> None:
    # The non-participating FFI is given a treaty-reduced rate, ignoring the FATCA
    # override that forces the statutory rate.
    _payment(payload, "PMT-04")["rate_applied_bps"] = 1500


def _deposits_short(payload: dict[str, Any]) -> None:
    _deposit(payload, "DEP-02")["amount_cents"] -= d(50_000)


def _filed_late(payload: dict[str, Any]) -> None:
    _form(payload)["filed_date"] = "2030-03-20"


def _slip_missing(payload: dict[str, Any]) -> None:
    slip_doc = _slip_doc(payload)
    slip_doc["slips"] = [s for s in slip_doc["slips"] if s.get("payee_id") != "PAYEE-03"]


def _gross_untied(payload: dict[str, Any]) -> None:
    _form(payload)["total_gross_cents"] += d(100_000)


def _withheld_untied(payload: dict[str, Any]) -> None:
    _form(payload)["total_withheld_cents"] += d(1_000)


def _slip_count_untied(payload: dict[str, Any]) -> None:
    _form(payload)["transmitted_count"] += 1


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {"payee_id": "PAYEE-01", "w8_expiration": "2031-06-30", "days_remaining": 546}
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    payment = _payment(payload, "PMT-03")
    payment["gross_cents"] = float(payment["gross_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_payee_id": ("payee_unique_ids", _duplicate_payee_id),
    "unknown_country": ("payee_country_known", _unknown_country),
    "bad_ch3_status": ("payee_ch3_status_valid", _bad_ch3_status),
    "bad_ch4_status": ("payee_ch4_status_valid", _bad_ch4_status),
    "bad_lob_code": ("payee_lob_code_valid", _bad_lob_code),
    "rate_row_missing": ("rate_table_defined", _rate_row_missing),
    "rate_out_of_bounds": ("rate_within_bounds", _rate_out_of_bounds),
    "payment_missing_field": ("pay_required_fields", _payment_missing_field),
    "unknown_income_code": ("pay_income_code_known", _unknown_income_code),
    "unknown_payment_payee": ("pay_payee_exists", _unknown_payment_payee),
    "bad_payment_status": ("pay_status_valid", _bad_payment_status),
    "us_payee_withheld": ("wh_us_payee_excluded", _us_payee_withheld),
    "accrued_withheld": ("wh_accrued_not_withheld", _accrued_withheld),
    "rate_applied_wrong": ("wh_rate_recomputes", _rate_applied_wrong),
    "tax_withheld_wrong": ("wh_tax_recomputes", _tax_withheld_wrong),
    "treaty_without_w8": ("exm_w8_present_for_treaty", _treaty_without_w8),
    "w8_expired": ("exm_w8_not_expired", _w8_expired),
    "w8_renewal_due": ("exm_w8_renewal_window", _w8_renewal_due),
    "portfolio_contingent": ("exm_portfolio_interest_eligible", _portfolio_contingent),
    "fatca_override_ignored": ("exm_fatca_override", _fatca_override_ignored),
    "deposits_short": ("dep_total_ties_withheld", _deposits_short),
    "filed_late": ("dep_1042_filed_on_time", _filed_late),
    "slip_missing": ("rec_slip_per_payee", _slip_missing),
    "gross_untied": ("rec_gross_ties", _gross_untied),
    "withheld_untied": ("rec_withheld_ties", _withheld_untied),
    "slip_count_untied": ("rec_slip_count_ties_1042t", _slip_count_untied),
    "watchlist_overstated": ("rec_w8_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("wh_tax_recomputes", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(FILERS[0])
    clean["file_id"] = f"clean__{FILERS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        filer = FILERS[(i + 1) % len(FILERS)]
        f = baseline(filer)
        f["file_id"] = f"{name}__{filer.replace(' ', '_')}"
        f["planted_defect"] = name
        mutate(f)
        files.append(f)

    for f in files:
        path = folder / f"{f['file_id']}.json"
        path.write_text(
            json.dumps(f, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
