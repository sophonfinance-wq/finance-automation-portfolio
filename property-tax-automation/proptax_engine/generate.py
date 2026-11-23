"""
Fictional property tax roll generator.
======================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The portfolio, the states, the projects, the parcel
numbers, the assessed values and every rate are fictional, and the tax year is set
in a fictional future. No real entity, person, county, parcel, project or path
appears anywhere. The generator is deterministic and takes no seed.

Three regimes, none of them hard-coded
--------------------------------------
The corpus carries three jurisdictions with genuinely different calendars: a
two-instalment spring/autumn regime on a calendar fiscal year, a two-instalment
regime on a mid-year fiscal year that reassesses on change of ownership (so its
second instalment lands in the *following* calendar year), and a single-instalment
regime. The engine reads all of it from the regime table; a fourth jurisdiction
would be a row here, not a change to any control.

The baseline is derived, not typed
----------------------------------
Only the regimes, the projects, the parcels' assessed values and the closings are
stated. :func:`rederive` computes everything the engine later checks as a
tie-out: each parcel's annual charge from the levy rate on its assessed value, the
instalment split from the regime's own shares, the due dates from the regime's
calendar, penalty and interest from the days actually late, each closing's
proration from the days held in that regime's fiscal year, the monthly accrual,
and the ledger balance behind it.

So the relationships the engine tests are the same relationships that produced the
data. A defect that changes a base fact re-derives everything downstream, which
keeps the break confined to the one control it was built for; a defect that
targets a tie-out edits the stated figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .model import (
    DOC_ACCRUAL_LEDGER,
    DOC_ASSESSMENT_HISTORY,
    DOC_GL_POSITIONS,
    DOC_INSTALMENT_SCHEDULE,
    DOC_PARCEL_REGISTER,
    DOC_PROJECT_REGISTER,
    DOC_REGIME_TABLE,
    DOC_SALE_REGISTER,
    PARCEL_HELD,
    PARCEL_RETIRED,
    PARCEL_SOLD,
    PRORATION_DAYS,
    STAGE_COMPLETE,
    STAGE_DEVELOPMENT,
)
from .money import allocate_by_ratio, apply_rate, split_evenly

#: Fictional portfolio labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Residential Portfolio",
    "Halbrook Lot Holdings",
    "Stonecrest Land Group",
    "Ardenne Field Portfolio",
)

TAX_YEAR = 2029
AS_OF = "2029-11-15"

J_CASCADIA = "Cascadia"
J_ARDENNE = "Ardenne"
J_BELMAR = "Belmar"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(jurisdiction, fiscal_start_MM-DD, penalty_bps, interest_bps_per_period,
#:   supplemental_on_transfer, ((sequence, due_MM-DD, year_offset, share_bps), ...))``
REGIMES: tuple[tuple[str, str, int, int, bool, tuple[tuple[int, str, int, int], ...]], ...] = (
    (
        J_CASCADIA, "01-01", 1200, 100, False,
        ((1, "04-30", 0, 5000), (2, "10-31", 0, 5000)),
    ),
    (
        # A mid-year fiscal year: the second instalment falls in the next calendar
        # year, and a change of ownership triggers a supplemental assessment.
        J_ARDENNE, "07-01", 1000, 150, True,
        ((1, "12-10", 0, 5000), (2, "04-10", 1, 5000)),
    ),
    (
        J_BELMAR, "01-01", 600, 100, False,
        ((1, "01-31", 0, 10000),),
    ),
)

#: ``(code, name, jurisdiction, stage, plat_lot_count)``
PROJECTS: tuple[tuple[str, str, str, str, int], ...] = (
    ("PRJ-210", "Alderway Cottages", J_CASCADIA, STAGE_DEVELOPMENT, 4),
    ("PRJ-224", "Kestrel Landing", J_ARDENNE, STAGE_COMPLETE, 3),
    ("PRJ-231", "Bexley Court", J_BELMAR, STAGE_DEVELOPMENT, 2),
)

#: ``(parcel_no, project, lot_unit, jurisdiction, land_cents, improvement_cents,
#:   levy_rate_bps, status, exemption_code, exemption_authority)``
#: The annual charge and the assessed total are derived, not stated.
PARCELS: tuple[tuple[Any, ...], ...] = (
    # The parent parcel of the Alderway plat, retired once its lots hit the roll.
    ("P-2100", "PRJ-210", "Parent", J_CASCADIA, d(720_000), 0, 110, PARCEL_RETIRED, None, None),
    ("P-2101", "PRJ-210", "Lot 1", J_CASCADIA, d(180_000), d(420_000), 110, PARCEL_HELD, None, None),
    ("P-2102", "PRJ-210", "Lot 2", J_CASCADIA, d(180_000), d(400_000), 110, PARCEL_HELD, None, None),
    ("P-2103", "PRJ-210", "Lot 3", J_CASCADIA, d(180_000), d(440_000), 110, PARCEL_SOLD, None, None),
    ("P-2104", "PRJ-210", "Lot 4", J_CASCADIA, d(180_000), d(380_000), 110, PARCEL_HELD, None, None),
    ("P-2241", "PRJ-224", "Unit A", J_ARDENNE, d(250_000), d(550_000), 125, PARCEL_HELD, None, None),
    ("P-2242", "PRJ-224", "Unit B", J_ARDENNE, d(250_000), d(500_000), 125, PARCEL_SOLD, None, None),
    (
        "P-2243", "PRJ-224", "Unit C", J_ARDENNE, d(250_000), d(600_000), 125, PARCEL_HELD,
        "MULTIFAMILY-DEFERRAL", "Ardenne Rev. Code 84.14 application 2029-0117",
    ),
    ("P-2311", "PRJ-231", "Lot 1", J_BELMAR, d(120_000), d(280_000), 240, PARCEL_HELD, None, None),
    ("P-2312", "PRJ-231", "Lot 2", J_BELMAR, d(120_000), d(300_000), 240, PARCEL_HELD, None, None),
)

#: ``(parcel_no, close_of_escrow_date)``. Shares and supplementals are derived.
CLOSINGS: tuple[tuple[str, str], ...] = (
    ("P-2103", "2029-05-15"),
    ("P-2242", "2029-09-30"),
)

#: ``(parcel_no, sequence, paid_date | None)`` -- when each instalment settled.
#: ``P-2312`` settled seven weeks late on purpose, so the clean baseline exercises
#: the penalty and interest arithmetic rather than only asserting it stays at zero.
PAYMENTS: tuple[tuple[str, int, str | None], ...] = (
    ("P-2101", 1, "2029-04-25"), ("P-2101", 2, "2029-10-28"),
    ("P-2102", 1, "2029-04-25"), ("P-2102", 2, "2029-10-28"),
    ("P-2103", 1, "2029-04-25"), ("P-2103", 2, None),
    ("P-2104", 1, "2029-04-25"), ("P-2104", 2, "2029-10-28"),
    ("P-2241", 1, None), ("P-2241", 2, None),
    ("P-2242", 1, None), ("P-2242", 2, None),
    ("P-2243", 1, None), ("P-2243", 2, None),
    ("P-2311", 1, "2029-01-28"),
    ("P-2312", 1, "2029-03-20"),
)

#: Prior-year assessed totals, all inside the protest-review band.
PRIOR_YEAR: tuple[tuple[str, int], ...] = (
    ("P-2101", d(552_000)), ("P-2102", d(534_000)), ("P-2103", d(570_000)),
    ("P-2104", d(516_000)), ("P-2241", d(736_000)), ("P-2242", d(690_000)),
    ("P-2243", d(782_000)), ("P-2311", d(368_000)), ("P-2312", d(386_000)),
)


# --------------------------------------------------------------------------- #
# Payload helpers
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _parcel(payload: dict[str, Any], parcel_no: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PARCEL_REGISTER)
    assert register is not None
    for row in register["parcels"]:
        if row.get("parcel_no") == parcel_no:
            return row
    raise KeyError(parcel_no)


def _instalment(payload: dict[str, Any], parcel_no: str, sequence: int) -> dict[str, Any]:
    schedule = _doc(payload, DOC_INSTALMENT_SCHEDULE)
    assert schedule is not None
    for row in schedule["instalments"]:
        if row.get("parcel_no") == parcel_no and row.get("sequence") == sequence:
            return row
    raise KeyError((parcel_no, sequence))


def _closing(payload: dict[str, Any], parcel_no: str) -> dict[str, Any]:
    sales = _doc(payload, DOC_SALE_REGISTER)
    assert sales is not None
    for row in sales["closings"]:
        if row.get("parcel_no") == parcel_no:
            return row
    raise KeyError(parcel_no)


def _accrual(payload: dict[str, Any], parcel_no: str, period: str) -> dict[str, Any]:
    ledger = _doc(payload, DOC_ACCRUAL_LEDGER)
    assert ledger is not None
    for row in ledger["accruals"]:
        if row.get("parcel_no") == parcel_no and row.get("period") == period:
            return row
    raise KeyError((parcel_no, period))


def rederive(payload: dict[str, Any], *, recompute_charge: bool = True) -> None:
    """Recompute every derived figure from the payload's own base facts.

    ``recompute_charge`` is the one seam. Normally the annual charge is derived
    from the levy rate on the assessed value; the defect that breaks *that*
    relationship sets the charge by hand and asks everything downstream to follow
    it, so the break lands on one control instead of every schedule built on it.
    """
    register = _doc(payload, DOC_PARCEL_REGISTER)
    schedule = _doc(payload, DOC_INSTALMENT_SCHEDULE)
    sales = _doc(payload, DOC_SALE_REGISTER)
    ledger = _doc(payload, DOC_ACCRUAL_LEDGER)
    gl = _doc(payload, DOC_GL_POSITIONS)
    table = _doc(payload, DOC_REGIME_TABLE)
    projects_doc = _doc(payload, DOC_PROJECT_REGISTER)
    if not all((register, schedule, sales, ledger, gl, table, projects_doc)):
        return
    assert register and schedule and sales and ledger and gl and table and projects_doc

    tax_year = payload["tax_year"]
    as_of = date.fromisoformat(payload["as_of"])
    regimes = {r["jurisdiction"]: r for r in table["regimes"]}
    projects = {p["code"]: p for p in projects_doc["projects"]}

    # Assessed total and the annual charge that follows from it.
    for row in register["parcels"]:
        row["assessed_total_cents"] = (
            row["assessed_land_cents"] + row["assessed_improvement_cents"]
        )
        if recompute_charge:
            row["annual_tax_cents"] = (
                0
                if row["status"] == PARCEL_RETIRED
                else apply_rate(row["assessed_total_cents"], row["levy_rate_bps"])
            )

    parcels = {p["parcel_no"]: p for p in register["parcels"]}
    closed_on = {
        c["parcel_no"]: date.fromisoformat(c["close_of_escrow_date"])
        for c in sales["closings"]
        if c.get("close_of_escrow_date") and c["parcel_no"] in parcels
    }

    # Instalments: the regime's own shares, dates and delinquency arithmetic.
    for row in schedule["instalments"]:
        parcel = parcels.get(row["parcel_no"])
        if parcel is None:
            continue
        regime = regimes.get(parcel["jurisdiction"])
        if regime is None:
            continue
        shares = [r["share_bps"] for r in regime["instalments"]]
        split = allocate_by_ratio(parcel["annual_tax_cents"], shares)
        spec = next(
            (r for r in regime["instalments"] if r["sequence"] == row["sequence"]), None
        )
        if spec is None:
            continue
        row["amount_cents"] = split[regime["instalments"].index(spec)]
        row["due_date"] = f"{tax_year + spec['due_year_offset']}-{spec['due_month_day']}"

        due = date.fromisoformat(row["due_date"])
        closed = closed_on.get(row["parcel_no"])
        paid = date.fromisoformat(row["paid_date"]) if row.get("paid_date") else None
        if closed is not None and due > closed:
            # The buyer's period: no penalty accrues to the developer here.
            row["penalty_cents"], row["interest_cents"] = 0, 0
        else:
            reference = paid if paid is not None else as_of
            days_late = (reference - due).days
            if days_late <= 0:
                row["penalty_cents"], row["interest_cents"] = 0, 0
            else:
                row["penalty_cents"] = apply_rate(row["amount_cents"], regime["penalty_bps"])
                row["interest_cents"] = (
                    apply_rate(row["amount_cents"], regime["interest_bps_per_period"])
                    * (days_late // 30)
                )
        row["paid_amount_cents"] = (
            row["amount_cents"] + row["penalty_cents"] + row["interest_cents"]
            if paid is not None
            else 0
        )
        row["receipt_reference"] = (
            f"RCT-{row['parcel_no']}-{row['sequence']}" if paid is not None else None
        )

    # Closings: the proration by days held in that regime's own fiscal year.
    for row in sales["closings"]:
        parcel = parcels.get(row["parcel_no"])
        if parcel is None:
            continue
        regime = regimes.get(parcel["jurisdiction"])
        if regime is None:
            continue
        opens = date.fromisoformat(f"{tax_year}-{regime['fiscal_year_start_month_day']}")
        closed = date.fromisoformat(row["close_of_escrow_date"])
        days_held = max(0, min((closed - opens).days, PRORATION_DAYS))
        seller = parcel["annual_tax_cents"] * days_held // PRORATION_DAYS
        row["seller_share_cents"] = seller
        row["buyer_share_cents"] = parcel["annual_tax_cents"] - seller
        row["supplemental_recorded"] = bool(regime["supplemental_on_transfer"])

    # Monthly accrual: the full charge for a parcel held all year, the seller's
    # share for one that closed, and nothing at all after the month it closed.
    ledger["accruals"] = []
    for parcel_no in sorted(parcels):
        parcel = parcels[parcel_no]
        if parcel["status"] == PARCEL_RETIRED:
            continue
        project = projects.get(parcel["project_code"])
        capitalised = bool(project and project["stage"] == STAGE_DEVELOPMENT)
        closed = closed_on.get(parcel_no)
        if closed is None:
            amounts = split_evenly(parcel["annual_tax_cents"], 12)
            months = list(range(1, 13))
        else:
            closing_row = next(
                c for c in sales["closings"] if c["parcel_no"] == parcel_no
            )
            amounts = split_evenly(closing_row["seller_share_cents"], closed.month)
            amounts += [0] * (12 - closed.month)
            months = list(range(1, 13))
        for month, amount in zip(months, amounts):
            ledger["accruals"].append(
                {
                    "parcel_no": parcel_no,
                    "period": f"{tax_year:04d}-{month:02d}",
                    "amount_cents": amount,
                    "capitalised": capitalised,
                }
            )

    gl["property_tax_accrued_cents"] = sum(r["amount_cents"] for r in ledger["accruals"])


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean roll file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "tax_year": TAX_YEAR,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_REGIME_TABLE,
                "document_id": "REGIME-2029",
                "regimes": [
                    {
                        "jurisdiction": juris,
                        "fiscal_year_start_month_day": fiscal_start,
                        "penalty_bps": penalty,
                        "interest_bps_per_period": interest,
                        "supplemental_on_transfer": supplemental,
                        "instalments": [
                            {
                                "sequence": sequence,
                                "due_month_day": due,
                                "due_year_offset": offset,
                                "share_bps": share,
                            }
                            for sequence, due, offset, share in instalments
                        ],
                    }
                    for juris, fiscal_start, penalty, interest, supplemental, instalments
                    in REGIMES
                ],
            },
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PROJ-2029",
                "projects": [
                    {
                        "code": code,
                        "name": name,
                        "jurisdiction": juris,
                        "stage": stage,
                        "plat_lot_count": lots,
                    }
                    for code, name, juris, stage, lots in PROJECTS
                ],
            },
            {
                "doc_type": DOC_PARCEL_REGISTER,
                "document_id": "PARCEL-2029",
                "parcels": [
                    {
                        "parcel_no": parcel_no,
                        "project_code": project,
                        "lot_unit": lot,
                        "jurisdiction": juris,
                        "assessed_land_cents": land,
                        "assessed_improvement_cents": improvement,
                        "assessed_total_cents": 0,
                        "levy_rate_bps": rate,
                        "annual_tax_cents": 0,
                        "status": status,
                        "exemption_code": exemption,
                        "exemption_authority": authority,
                    }
                    for (
                        parcel_no, project, lot, juris, land, improvement, rate,
                        status, exemption, authority,
                    ) in PARCELS
                ],
            },
            {
                "doc_type": DOC_ASSESSMENT_HISTORY,
                "document_id": "HIST-2028",
                "prior_year": [
                    {"parcel_no": parcel_no, "assessed_total_cents": value}
                    for parcel_no, value in PRIOR_YEAR
                ],
            },
            {
                "doc_type": DOC_INSTALMENT_SCHEDULE,
                "document_id": "INST-2029",
                "instalments": [
                    {
                        "parcel_no": parcel_no,
                        "sequence": sequence,
                        "due_date": "",
                        "amount_cents": 0,
                        "penalty_cents": 0,
                        "interest_cents": 0,
                        "paid_date": paid,
                        "paid_amount_cents": 0,
                        "receipt_reference": None,
                    }
                    for parcel_no, sequence, paid in PAYMENTS
                ],
            },
            {
                "doc_type": DOC_SALE_REGISTER,
                "document_id": "SALE-2029",
                "closings": [
                    {
                        "parcel_no": parcel_no,
                        "close_of_escrow_date": closed,
                        "seller_share_cents": 0,
                        "buyer_share_cents": 0,
                        "supplemental_recorded": False,
                    }
                    for parcel_no, closed in CLOSINGS
                ],
            },
            {
                "doc_type": DOC_ACCRUAL_LEDGER,
                "document_id": "ACCR-2029",
                "accruals": [],
            },
            {
                "doc_type": DOC_GL_POSITIONS,
                "document_id": "GL-2029",
                "property_tax_accrued_cents": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects
# --------------------------------------------------------------------------- #
def _drop_document(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        d for d in payload["documents"] if d.get("doc_type") != DOC_ASSESSMENT_HISTORY
    ]


def _duplicate_parcel(payload: dict[str, Any]) -> None:
    # The retired parent is duplicated on purpose: a repeated *live* parcel would
    # also overrun the plat count, and this file is meant to isolate one control.
    register = _doc(payload, DOC_PARCEL_REGISTER)
    assert register is not None
    register["parcels"].append(dict(_parcel(payload, "P-2100")))


def _missing_required_field(payload: dict[str, Any]) -> None:
    _parcel(payload, "P-2311")["lot_unit"] = None


def _unmapped_project(payload: dict[str, Any]) -> None:
    _parcel(payload, "P-2243")["project_code"] = "PRJ-999"


def _plat_short(payload: dict[str, Any]) -> None:
    # The assessor has not finished segregating: the plat says five, the roll four.
    projects = _doc(payload, DOC_PROJECT_REGISTER)
    assert projects is not None
    next(p for p in projects["projects"] if p["code"] == "PRJ-210")["plat_lot_count"] = 5


def _unknown_jurisdiction(payload: dict[str, Any]) -> None:
    _parcel(payload, "P-2311")["jurisdiction"] = "Northmarch"


def _assessment_split_break(payload: dict[str, Any]) -> None:
    # The components no longer foot; the total -- and so the charge -- is untouched.
    _parcel(payload, "P-2102")["assessed_improvement_cents"] += d(15_000)


def _charge_off_rate(payload: dict[str, Any]) -> None:
    _parcel(payload, "P-2101")["annual_tax_cents"] += d(400)
    rederive(payload, recompute_charge=False)


def _instalment_split_break(payload: dict[str, Any]) -> None:
    # Planted on an instalment that is neither due nor paid, so only the footing
    # control has anything to say about it.
    _instalment(payload, "P-2241", 1)["amount_cents"] += d(120)


def _wrong_due_date(payload: dict[str, Any]) -> None:
    _instalment(payload, "P-2241", 1)["due_date"] = "2029-12-20"


def _delinquency_math(payload: dict[str, Any]) -> None:
    row = _instalment(payload, "P-2312", 1)
    row["penalty_cents"] -= d(200)
    row["paid_amount_cents"] = (
        row["amount_cents"] + row["penalty_cents"] + row["interest_cents"]
    )


def _duplicate_instalment(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_INSTALMENT_SCHEDULE)
    assert schedule is not None
    schedule["instalments"].append(dict(_instalment(payload, "P-2101", 1)))


def _missing_receipt(payload: dict[str, Any]) -> None:
    _instalment(payload, "P-2102", 2)["receipt_reference"] = None


def _sale_unknown_parcel(payload: dict[str, Any]) -> None:
    sales = _doc(payload, DOC_SALE_REGISTER)
    assert sales is not None
    sales["closings"].append(
        {
            "parcel_no": "P-9999",
            "close_of_escrow_date": "2029-06-01",
            "seller_share_cents": 0,
            "buyer_share_cents": 0,
            "supplemental_recorded": False,
        }
    )


def _status_mismatch(payload: dict[str, Any]) -> None:
    # Carried sold with no closing on file: the tax has been handed to a buyer
    # nobody can name.
    _parcel(payload, "P-2104")["status"] = PARCEL_SOLD
    rederive(payload)


def _paid_after_escrow(payload: dict[str, Any]) -> None:
    """The headline: the roll kept billing a parcel that had already closed."""
    row = _instalment(payload, "P-2103", 2)
    row["paid_date"] = "2029-10-28"
    row["paid_amount_cents"] = row["amount_cents"]
    row["receipt_reference"] = "RCT-P-2103-2"


def _proration_gap(payload: dict[str, Any]) -> None:
    _closing(payload, "P-2103")["buyer_share_cents"] -= d(150)


def _proration_days_wrong(payload: dict[str, Any]) -> None:
    # Prorated on a calendar year instead of the regime's mid-year fiscal year.
    closing = _closing(payload, "P-2242")
    parcel = _parcel(payload, "P-2242")
    days = (date(2029, 9, 30) - date(2029, 1, 1)).days
    seller = parcel["annual_tax_cents"] * days // PRORATION_DAYS
    closing["seller_share_cents"] = seller
    closing["buyer_share_cents"] = parcel["annual_tax_cents"] - seller


def _missing_supplemental(payload: dict[str, Any]) -> None:
    _closing(payload, "P-2242")["supplemental_recorded"] = False


def _accrual_footing(payload: dict[str, Any]) -> None:
    row = _accrual(payload, "P-2101", "2029-07")
    row["amount_cents"] -= d(90)
    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["property_tax_accrued_cents"] -= d(90)


def _accrual_after_escrow(payload: dict[str, Any]) -> None:
    row = _accrual(payload, "P-2103", "2029-08")
    row["amount_cents"] = d(560)
    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["property_tax_accrued_cents"] += d(560)


def _gl_break(payload: dict[str, Any]) -> None:
    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["property_tax_accrued_cents"] += d(1_250)


def _wrong_capitalisation(payload: dict[str, Any]) -> None:
    _accrual(payload, "P-2241", "2029-04")["capitalised"] = True


def _payment_mismatch(payload: dict[str, Any]) -> None:
    _instalment(payload, "P-2311", 1)["paid_amount_cents"] += d(75)


def _assessment_jump(payload: dict[str, Any]) -> None:
    history = _doc(payload, DOC_ASSESSMENT_HISTORY)
    assert history is not None
    next(r for r in history["prior_year"] if r["parcel_no"] == "P-2101")[
        "assessed_total_cents"
    ] = d(360_000)


def _exemption_without_authority(payload: dict[str, Any]) -> None:
    _parcel(payload, "P-2243")["exemption_authority"] = None


def _amount_not_integer(payload: dict[str, Any]) -> None:
    _accrual(payload, "P-2102", "2029-03")["amount_cents"] = 53166.0


#: ``name -> (rule the file is built to trip, mutation)``
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _drop_document),
    "duplicate_parcel": ("par_parcel_unique", _duplicate_parcel),
    "missing_required_field": ("par_required_fields", _missing_required_field),
    "unmapped_project": ("par_project_mapped", _unmapped_project),
    "plat_short": ("par_plat_completeness", _plat_short),
    "unknown_jurisdiction": ("par_jurisdiction_known", _unknown_jurisdiction),
    "assessment_split_break": ("asmt_components_tie_total", _assessment_split_break),
    "charge_off_rate": ("asmt_charge_follows_value", _charge_off_rate),
    "assessment_jump": ("asmt_variance_surfaced", _assessment_jump),
    "exemption_without_authority": (
        "asmt_exemption_has_authority",
        _exemption_without_authority,
    ),
    "instalment_split_break": ("inst_shares_tie_annual", _instalment_split_break),
    "wrong_due_date": ("inst_matches_regime_calendar", _wrong_due_date),
    "delinquency_math": ("inst_delinquency_recomputed", _delinquency_math),
    "duplicate_instalment": ("inst_no_duplicate_payment", _duplicate_instalment),
    "missing_receipt": ("inst_receipt_on_file", _missing_receipt),
    "sale_unknown_parcel": ("own_sale_parcel_exists", _sale_unknown_parcel),
    "status_mismatch": ("own_sold_parcel_flagged", _status_mismatch),
    "paid_after_escrow": ("own_no_payment_after_escrow", _paid_after_escrow),
    "proration_gap": ("own_proration_sums_to_annual", _proration_gap),
    "proration_days_wrong": ("own_proration_by_days_held", _proration_days_wrong),
    "missing_supplemental": ("own_supplemental_on_transfer", _missing_supplemental),
    "accrual_footing": ("acr_periods_tie_annual", _accrual_footing),
    "accrual_after_escrow": ("acr_stops_at_escrow", _accrual_after_escrow),
    "gl_break": ("acr_ties_gl_liability", _gl_break),
    "wrong_capitalisation": ("acr_capitalisation_matches_stage", _wrong_capitalisation),
    "payment_mismatch": ("pay_amount_ties_notice", _payment_mismatch),
    "amount_not_integer": ("acr_ties_gl_liability", _amount_not_integer),
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
