"""
Fictional information-return issuance corpus generator.
=======================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The groups, the payer entities, the payees, the
taxpayer numbers, the box thresholds, the payment amounts and the dates are
fictional, and the reporting year is set in a fictional future. No real entity,
person, jurisdiction, identifier, form number or path appears anywhere. The
generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the payer entities, the payees, the box catalog and the ledger payment lines
are stated as base facts. Everything the engine later checks as a derivation --
which payee/box owes a form, what that form reports, what it withholds, the
near-threshold watchlist, each entity's transmittal and the annual rollup -- is
recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`inforeturn_engine.issuance` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the forms and the rollups and keeps
the break confined to one control; a defect that targets an issued form
re-derives only the rollups; a defect that targets a stated rollup edits that
figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    _entities,
    _entity_id,
    _entity_map,
    _payee_map,
    recompute_expected_forms,
    recompute_transmittal,
    recompute_watchlist,
)
from .model import (
    DOC_BOX_CATALOG,
    DOC_ENTITY_REGISTER,
    DOC_FORM_REGISTER,
    DOC_ISSUANCE_REPORT,
    DOC_LEDGER_EXTRACT,
    DOC_PAYEE_REGISTER,
    DOC_THRESHOLD_WATCHLIST,
    DOC_TRANSMITTAL_REGISTER,
    FORM_CARD_SETTLEMENT,
    FORM_INTEREST,
    FORM_NONEMPLOYEE,
    PAYEE_AFFILIATE,
    PAYEE_LENDER,
    PAYEE_SETTLEMENT_ENTITY,
    PAYEE_VENDOR,
    Context,
)

#: Fictional group labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
    "Westmere",
)

PERIOD = "FY2029"
#: The calendar year the payee population is assembled for.
REPORTING_YEAR = 2029
#: The issuance review date the cycle is measured at.
AS_OF = "2030-01-15"
#: The date every form in the corpus is issued on.
ISSUE_DATE = "2030-01-31"
#: Statutory backup-withholding rate for the fictional regime, in basis points.
BACKUP_WITHHOLDING_BPS = 2500
#: Review band, in cents, below a box threshold.
NEAR_THRESHOLD_CENTS = 5000


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(entity_id, entity_name, payer_tin)``. Invented project entities; each files
#: information returns in its own name.
ENTITIES: tuple[tuple[str, str, str], ...] = (
    ("ENT-401", "Brightwater Commons", "FTN-400100011"),
    ("ENT-402", "Copperfield Yards", "FTN-400100022"),
    ("ENT-403", "Hollowmere Flats", "FTN-400100033"),
)

#: ``(payee_id, payee_name, payee_type, payee_tin)``. Invented counterparties.
#: PYE-504 and PYE-507 have no taxpayer number on file, so backup withholding
#: attaches to them; PYE-507 is paid under the box threshold, which is exactly the
#: case where withheld tax obliges a form the threshold would not have.
PAYEES: tuple[tuple[Any, ...], ...] = (
    ("PYE-501", "Marrowfield Capital", PAYEE_LENDER, "FTN-500200011"),
    ("PYE-502", "Ellersby Holdings", PAYEE_AFFILIATE, "FTN-500200022"),
    ("PYE-503", "Talbourne Concrete", PAYEE_VENDOR, "FTN-500200033"),
    ("PYE-504", "Quillhaven Engineering", PAYEE_VENDOR, None),
    ("PYE-505", "Ashgrove Payment Network", PAYEE_SETTLEMENT_ENTITY, "FTN-500200055"),
    ("PYE-506", "Dunmarrow Electric", PAYEE_VENDOR, "FTN-500200066"),
    ("PYE-507", "Wrenmoor Surveying", PAYEE_VENDOR, None),
)

#: ``(form_type, box_code, box_label, threshold, withholding_applies)``. Thresholds
#: in dollars, invented for this fictional regime. Card and third-party settlement
#: does not attract backup withholding, so the kernel's withholding branch is
#: exercised in both directions.
BOXES: tuple[tuple[Any, ...], ...] = (
    (FORM_INTEREST, "IB-1", "Interest paid to lenders", 25, True),
    (FORM_INTEREST, "IB-2", "Interest paid to affiliates", 25, True),
    (FORM_NONEMPLOYEE, "NB-1", "Non-employee compensation", 750, True),
    (FORM_NONEMPLOYEE, "NB-2", "Contract labour", 750, True),
    (FORM_CARD_SETTLEMENT, "CB-1", "Card and third-party settlement", 15_000, False),
)

#: ``(payment_id, entity_id, payee_id, form_type, box_code, amount, paid_date)``.
#: Amounts in dollars. ENT-403 pays PYE-503 exactly the non-employee threshold, so
#: a one-cent shortfall is the whole of a boundary defect; ENT-401 pays PYE-506
#: well under it, so the clean baseline carries a below-threshold payee that owes
#: no form and raises no review flag.
PAYMENTS: tuple[tuple[Any, ...], ...] = (
    ("PAY-4101", "ENT-401", "PYE-501", FORM_INTEREST, "IB-1", 120_000, "2029-03-31"),
    ("PAY-4102", "ENT-401", "PYE-501", FORM_INTEREST, "IB-1", 120_000, "2029-06-30"),
    ("PAY-4103", "ENT-401", "PYE-501", FORM_INTEREST, "IB-1", 120_000, "2029-09-30"),
    ("PAY-4104", "ENT-401", "PYE-503", FORM_NONEMPLOYEE, "NB-1", 45_000, "2029-04-15"),
    ("PAY-4105", "ENT-401", "PYE-503", FORM_NONEMPLOYEE, "NB-1", 30_000, "2029-08-15"),
    ("PAY-4106", "ENT-401", "PYE-504", FORM_NONEMPLOYEE, "NB-1", 12_000, "2029-05-20"),
    ("PAY-4107", "ENT-401", "PYE-504", FORM_NONEMPLOYEE, "NB-1", 8_000, "2029-10-20"),
    ("PAY-4108", "ENT-401", "PYE-506", FORM_NONEMPLOYEE, "NB-1", 500, "2029-07-01"),
    ("PAY-4201", "ENT-402", "PYE-502", FORM_INTEREST, "IB-2", 90_000, "2029-06-30"),
    ("PAY-4202", "ENT-402", "PYE-502", FORM_INTEREST, "IB-2", 90_000, "2029-12-31"),
    ("PAY-4203", "ENT-402", "PYE-503", FORM_NONEMPLOYEE, "NB-2", 60_000, "2029-09-01"),
    ("PAY-4204", "ENT-402", "PYE-505", FORM_CARD_SETTLEMENT, "CB-1", 250_000, "2029-05-31"),
    ("PAY-4205", "ENT-402", "PYE-505", FORM_CARD_SETTLEMENT, "CB-1", 300_000, "2029-11-30"),
    ("PAY-4206", "ENT-402", "PYE-507", FORM_NONEMPLOYEE, "NB-1", 400, "2029-02-28"),
    ("PAY-4301", "ENT-403", "PYE-501", FORM_INTEREST, "IB-1", 75_000, "2029-12-31"),
    ("PAY-4302", "ENT-403", "PYE-504", FORM_NONEMPLOYEE, "NB-1", 40_000, "2029-07-31"),
    ("PAY-4303", "ENT-403", "PYE-503", FORM_NONEMPLOYEE, "NB-1", 750, "2029-10-31"),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _require(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    doc = _doc(payload, doc_type)
    assert doc is not None
    return doc


def _entity(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_ENTITY_REGISTER)["entities"]:
        if row.get("entity_id") == entity_id:
            return row
    raise KeyError(entity_id)


def _payee(payload: dict[str, Any], payee_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_PAYEE_REGISTER)["payees"]:
        if row.get("payee_id") == payee_id:
            return row
    raise KeyError(payee_id)


def _payment(payload: dict[str, Any], payment_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_LEDGER_EXTRACT)["payments"]:
        if row.get("payment_id") == payment_id:
            return row
    raise KeyError(payment_id)


def _form(payload: dict[str, Any], form_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_FORM_REGISTER)["forms"]:
        if row.get("form_id") == form_id:
            return row
    raise KeyError(form_id)


def _transmittal(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_TRANSMITTAL_REGISTER)["transmittals"]:
        if row.get("entity_id") == entity_id:
            return row
    raise KeyError(entity_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    return _require(payload, DOC_ISSUANCE_REPORT)


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    return _require(payload, DOC_THRESHOLD_WATCHLIST)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive_forms(payload: dict[str, Any]) -> None:
    """Rebuild the form register from the ledger, the catalog and the payees.

    One form per payee/box the :mod:`~inforeturn_engine.issuance` kernel says is
    owed, reporting the entity's own ledger total for that box and carrying the
    withholding the kernel derives. Form ids run in key order within each entity,
    so the register is stable rather than merely correct.
    """
    register = _doc(payload, DOC_FORM_REGISTER)
    if register is None:
        return
    ctx = Context(path=Path("<generated>"), data=payload)
    entities = _entity_map(ctx)
    payees = _payee_map(ctx)
    seq: dict[str, int] = {}
    forms: list[dict[str, Any]] = []
    for entry in recompute_expected_forms(ctx):
        entity_id = entry["entity_id"]
        entity = entities.get(entity_id, {})
        payee = payees.get(entry["payee_id"], {})
        seq[entity_id] = seq.get(entity_id, 0) + 1
        forms.append(
            {
                "form_id": f"FRM-{entity_id.split('-')[-1]}-{seq[entity_id]:02d}",
                "entity_id": entity_id,
                "payee_id": entry["payee_id"],
                "form_type": entry["form_type"],
                "box_code": entry["box_code"],
                "payer_name": entity.get("entity_name"),
                "payer_tin": entity.get("payer_tin"),
                "payee_tin": payee.get("payee_tin"),
                "box_amount_cents": entry["box_amount_cents"],
                "backup_withholding_cents": entry["backup_withholding_cents"],
                "issue_date": ISSUE_DATE,
            }
        )
    register["forms"] = forms


def rederive_rollups(payload: dict[str, Any]) -> None:
    """Recompute every rollup from the forms and the ledger as they now stand.

    The transmittals foot the forms actually on the register -- not the forms the
    ledger would have obliged -- because that is what a transmittal accompanies.
    The watchlist comes from the ledger, and the annual report from the
    transmittals, so a defect planted in a form leaves the rollups tied and the
    break confined to the control that owns it.
    """
    register = _doc(payload, DOC_TRANSMITTAL_REGISTER)
    watchlist = _doc(payload, DOC_THRESHOLD_WATCHLIST)
    report = _doc(payload, DOC_ISSUANCE_REPORT)
    ctx = Context(path=Path("<generated>"), data=payload)

    if register is not None:
        register["transmittals"] = []
        for row in _entities(ctx):
            entity_id = _entity_id(row)
            count, reported, withheld = recompute_transmittal(ctx, entity_id)
            register["transmittals"].append(
                {
                    "transmittal_id": f"TRM-{entity_id.split('-')[-1]}",
                    "entity_id": entity_id,
                    "form_count": count,
                    "total_reported_cents": reported,
                    "total_withheld_cents": withheld,
                }
            )

    if watchlist is not None:
        watchlist["entries"] = recompute_watchlist(ctx)

    if report is not None and register is not None:
        report["form_count"] = sum(r["form_count"] for r in register["transmittals"])
        report["total_reported_cents"] = sum(
            r["total_reported_cents"] for r in register["transmittals"]
        )
        report["total_withheld_cents"] = sum(
            r["total_withheld_cents"] for r in register["transmittals"]
        )


def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    rederive_forms(payload)
    rederive_rollups(payload)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean reporting file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "reporting_year": REPORTING_YEAR,
        "as_of": AS_OF,
        "backup_withholding_bps": BACKUP_WITHHOLDING_BPS,
        "near_threshold_cents": NEAR_THRESHOLD_CENTS,
        "documents": [
            {
                "doc_type": DOC_ENTITY_REGISTER,
                "document_id": "ENTITIES-2029",
                "entities": [
                    {
                        "entity_id": entity_id,
                        "entity_name": name,
                        "payer_tin": payer_tin,
                    }
                    for entity_id, name, payer_tin in ENTITIES
                ],
            },
            {
                "doc_type": DOC_PAYEE_REGISTER,
                "document_id": "PAYEES-2029",
                "payees": [
                    {
                        "payee_id": payee_id,
                        "payee_name": name,
                        "payee_type": payee_type,
                        "payee_tin": payee_tin,
                    }
                    for payee_id, name, payee_type, payee_tin in PAYEES
                ],
            },
            {
                "doc_type": DOC_BOX_CATALOG,
                "document_id": "BOXES-2029",
                "boxes": [
                    {
                        "form_type": form_type,
                        "box_code": box_code,
                        "box_label": label,
                        "threshold_cents": d(threshold),
                        "withholding_applies": withholding,
                    }
                    for form_type, box_code, label, threshold, withholding in BOXES
                ],
            },
            {
                "doc_type": DOC_LEDGER_EXTRACT,
                "document_id": "LEDGER-2029",
                "payments": [
                    {
                        "payment_id": payment_id,
                        "entity_id": entity_id,
                        "payee_id": payee_id,
                        "form_type": form_type,
                        "box_code": box_code,
                        "amount_cents": d(amount),
                        "paid_date": paid_date,
                    }
                    for (
                        payment_id, entity_id, payee_id, form_type, box_code, amount,
                        paid_date,
                    ) in PAYMENTS
                ],
            },
            {
                "doc_type": DOC_FORM_REGISTER,
                "document_id": "FORMS-2029",
                "forms": [],
            },
            {
                "doc_type": DOC_TRANSMITTAL_REGISTER,
                "document_id": "TRANSMITTALS-2029",
                "transmittals": [],
            },
            {
                "doc_type": DOC_THRESHOLD_WATCHLIST,
                "document_id": "WATCHLIST-2029",
                "entries": [],
            },
            {
                "doc_type": DOC_ISSUANCE_REPORT,
                "document_id": "ISSUANCE-2029",
                "form_count": 0,
                "total_reported_cents": 0,
                "total_withheld_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_ISSUANCE_REPORT
    ]


def _duplicate_entity_id(payload: dict[str, Any]) -> None:
    register = _require(payload, DOC_ENTITY_REGISTER)
    register["entities"].append(dict(_entity(payload, "ENT-402")))


def _entity_tin_malformed(payload: dict[str, Any]) -> None:
    # The register's own payer number is unreadable; the forms are re-derived from
    # it, so they print exactly what the register holds and only the register
    # control sees the break.
    _entity(payload, "ENT-403")["payer_tin"] = "FTN-77"
    rederive(payload)


def _duplicate_payee_id(payload: dict[str, Any]) -> None:
    register = _require(payload, DOC_PAYEE_REGISTER)
    register["payees"].append(dict(_payee(payload, "PYE-506")))


def _bad_payee_type(payload: dict[str, Any]) -> None:
    _payee(payload, "PYE-506")["payee_type"] = "contractor"


def _payee_tin_malformed(payload: dict[str, Any]) -> None:
    # The number was captured and cannot be read. It still counts as on file, so
    # nothing downstream changes -- which is the point of the control.
    _payee(payload, "PYE-506")["payee_tin"] = "FTN-77"


def _unknown_form_type(payload: dict[str, Any]) -> None:
    catalog = _require(payload, DOC_BOX_CATALOG)
    catalog["boxes"].append(
        {
            "form_type": "royalty_return",
            "box_code": "RB-1",
            "box_label": "Royalties paid",
            "threshold_cents": d(500),
            "withholding_applies": True,
        }
    )


def _duplicate_box_row(payload: dict[str, Any]) -> None:
    catalog = _require(payload, DOC_BOX_CATALOG)
    catalog["boxes"].append(dict(catalog["boxes"][0]))


def _ledger_orphan_payee(payload: dict[str, Any]) -> None:
    # A payment coded to a payee who never made it into this year's population.
    # The amount is well under the box threshold, so nothing is reported for it --
    # which is exactly how an unattributable line disappears.
    extract = _require(payload, DOC_LEDGER_EXTRACT)
    extract["payments"].append(
        {
            "payment_id": "PAY-9001",
            "entity_id": "ENT-401",
            "payee_id": "PYE-999",
            "form_type": FORM_NONEMPLOYEE,
            "box_code": "NB-1",
            "amount_cents": d(10),
            "paid_date": "2029-06-15",
        }
    )
    rederive(payload)


def _negative_payment(payload: dict[str, Any]) -> None:
    # A reversal carried into the population as a line of its own instead of being
    # netted at source. The forms re-derive around it, so only the ledger control
    # sees it.
    extract = _require(payload, DOC_LEDGER_EXTRACT)
    extract["payments"].append(
        {
            "payment_id": "PAY-9002",
            "entity_id": "ENT-401",
            "payee_id": "PYE-501",
            "form_type": FORM_INTEREST,
            "box_code": "IB-1",
            "amount_cents": d(-500),
            "paid_date": "2029-11-15",
        }
    )
    rederive(payload)


def _payment_outside_year(payload: dict[str, Any]) -> None:
    _payment(payload, "PAY-4103")["paid_date"] = "2030-01-05"
    rederive(payload)


def _form_missing_field(payload: dict[str, Any]) -> None:
    del _form(payload, "FRM-401-02")["issue_date"]


def _payer_tin_mismatch(payload: dict[str, Any]) -> None:
    # A well-formed number belonging to a different entity: the form looks
    # complete and would be filed under the wrong payer.
    _form(payload, "FRM-403-01")["payer_tin"] = _entity(payload, "ENT-401")["payer_tin"]


def _duplicate_form(payload: dict[str, Any]) -> None:
    register = _require(payload, DOC_FORM_REGISTER)
    copy = dict(_form(payload, "FRM-401-01"))
    copy["form_id"] = "FRM-401-04"
    register["forms"].append(copy)
    rederive_rollups(payload)


def _form_box_off_ledger(payload: dict[str, Any]) -> None:
    # The box is re-keyed from a summary rather than footed from the payment
    # lines. The payee has a taxpayer number, so no withholding moves with it.
    _form(payload, "FRM-401-02")["box_amount_cents"] += d(100)
    rederive_rollups(payload)


def _missing_required_form(payload: dict[str, Any]) -> None:
    register = _require(payload, DOC_FORM_REGISTER)
    register["forms"] = [f for f in register["forms"] if f.get("form_id") != "FRM-402-02"]
    rederive_rollups(payload)


def _form_below_threshold(payload: dict[str, Any]) -> None:
    # A payee well under the threshold with nothing withheld is cut a form anyway.
    register = _require(payload, DOC_FORM_REGISTER)
    entity = _entity(payload, "ENT-401")
    payee = _payee(payload, "PYE-506")
    register["forms"].append(
        {
            "form_id": "FRM-401-04",
            "entity_id": "ENT-401",
            "payee_id": "PYE-506",
            "form_type": FORM_NONEMPLOYEE,
            "box_code": "NB-1",
            "payer_name": entity["entity_name"],
            "payer_tin": entity["payer_tin"],
            "payee_tin": payee["payee_tin"],
            "box_amount_cents": d(500),
            "backup_withholding_cents": 0,
            "issue_date": ISSUE_DATE,
        }
    )
    rederive_rollups(payload)


def _near_threshold_payee(payload: dict[str, Any]) -> None:
    # The payee lands inside the review band under the threshold. The watchlist is
    # re-derived with it, so only the review flag remains.
    _payment(payload, "PAY-4108")["amount_cents"] = d(720)
    rederive(payload)


def _withholding_wrong(payload: dict[str, Any]) -> None:
    _form(payload, "FRM-401-03")["backup_withholding_cents"] = d(4_000)
    rederive_rollups(payload)


def _transmittal_total_wrong(payload: dict[str, Any]) -> None:
    # The transmittal and the rollup are moved together, so the rollup still ties
    # the transmittals and only the footing control sees the break.
    _transmittal(payload, "ENT-402")["total_reported_cents"] += d(1)
    _report(payload)["total_reported_cents"] += d(1)


def _rollup_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["form_count"] += 1


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {
            "entity_id": "ENT-401",
            "payee_id": "PYE-506",
            "form_type": FORM_NONEMPLOYEE,
            "box_code": "NB-1",
            "amount_cents": d(500),
            "shortfall_cents": d(250),
        }
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    form = _form(payload, "FRM-401-02")
    form["box_amount_cents"] = float(form["box_amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_entity_id": ("ent_unique_ids", _duplicate_entity_id),
    "entity_tin_malformed": ("ent_payer_identity", _entity_tin_malformed),
    "duplicate_payee_id": ("pye_unique_ids", _duplicate_payee_id),
    "bad_payee_type": ("pye_type_valid", _bad_payee_type),
    "payee_tin_malformed": ("pye_tin_wellformed", _payee_tin_malformed),
    "unknown_form_type": ("box_catalog_defined", _unknown_form_type),
    "duplicate_box_row": ("box_catalog_unique", _duplicate_box_row),
    "ledger_orphan_payee": ("led_rows_attributable", _ledger_orphan_payee),
    "negative_payment": ("led_amounts_valid", _negative_payment),
    "payment_outside_year": ("led_payment_in_year", _payment_outside_year),
    "form_missing_field": ("frm_required_fields", _form_missing_field),
    "payer_tin_mismatch": ("frm_payer_identity", _payer_tin_mismatch),
    "duplicate_form": ("frm_no_duplicates", _duplicate_form),
    "form_box_off_ledger": ("frm_box_ties_ledger", _form_box_off_ledger),
    "missing_required_form": ("thr_required_form_issued", _missing_required_form),
    "form_below_threshold": ("thr_no_unrequired_form", _form_below_threshold),
    "near_threshold_payee": ("thr_near_threshold_review", _near_threshold_payee),
    "withholding_wrong": ("bwh_rate_recomputes", _withholding_wrong),
    "transmittal_total_wrong": ("rpt_transmittal_foots", _transmittal_total_wrong),
    "rollup_count_wrong": ("rpt_annual_rollup_ties", _rollup_count_wrong),
    "watchlist_overstated": ("rpt_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("frm_box_ties_ledger", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PORTFOLIOS[0])
    clean["file_id"] = f"clean__{PORTFOLIOS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        portfolio = PORTFOLIOS[(i + 1) % len(PORTFOLIOS)]
        f = baseline(portfolio)
        f["file_id"] = f"{name}__{portfolio.replace(' ', '_')}"
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
