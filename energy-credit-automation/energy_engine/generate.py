"""
Fictional §45L energy-credit corpus generator.
==============================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The builders, the projects, the dwelling addresses,
the rater ids, the unit counts and the closing dates are fictional, and the fiscal
year is set in a fictional future. No real entity, person, project, place or path
appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the units (their close dates, certification and claim status), the projects,
the roll-forward columns, the partner ownership and the statutory parameters are
stated as base facts. Everything the engine later checks as a rollup -- each
unit's credited amount, every project's gross credit / addback / tax effect / net
benefit, the region and grand totals, the partner shares, the closings counts and
the final-report tie-out -- is recomputed by :func:`rederive` from those base
facts, through the *same* :mod:`energy_engine.credit` kernel the engine recomputes
with. So the relationships the engine tests are the relationships that produced the
data: a defect that changes a base fact re-derives the rollup and keeps the break
confined; a defect that targets a stated rollup edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .credit import unit_credit_cents
from .engine import (
    _statute,
    _unit_from_row,
    recompute_closed_units,
    recompute_partner_shares,
    recompute_project_summary,
)
from .model import (
    DOC_CLOSINGS_SCHEDULE,
    DOC_CREDIT_WORKSHEET,
    DOC_FINAL_REPORT,
    DOC_PARTNER_ALLOCATION,
    DOC_PERIOD_ROLLFORWARD,
    DOC_UNIT_REGISTER,
    Context,
)

#: Fictional builder / portfolio labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere Homebuilders",
)

FISCAL_YEAR = "FYE 6/30/2029"
#: The fiscal-year close-of-escrow window (inclusive both ends).
PERIOD_START = "2028-07-01"
PERIOD_END = "2029-06-30"
#: The statutory sunset, deliberately inside the fiscal-year window so a unit can
#: close in the period yet after the sunset -- the two eligibility gates are
#: genuinely independent.
SUNSET_DATE = "2029-03-31"
#: The statutory per-unit credit, in dollars (pre-IRA §45L: $2,000).
PER_UNIT_DOLLARS = 2_000
#: The effective tax rate on the credit's profit addback, in basis points.
EFFECTIVE_RATE_BPS = 2_100


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(project_id, name, region)``. Invented projects across two fictional regions.
PROJECTS: tuple[tuple[str, str, str], ...] = (
    ("PRJ-ALDR", "Alderpoint Terraces", "Region of Marran"),
    ("PRJ-BRWT", "Brightwater Commons", "Region of Marran"),
    ("PRJ-CPFD", "Copperfield Yards", "Region of Vessen"),
)

#: ``(unit_id, project_id, address, coe_date, certified, certificate_ref, rater_id)``.
#: Every unit is claimed, certified and closes inside the window on or before the
#: sunset, so the baseline is clean. Closing dates span the fiscal year.
UNITS: tuple[tuple[Any, ...], ...] = (
    ("UNIT-A01", "PRJ-ALDR", "14 Alderpoint Terrace", "2028-08-15", True, "HERS-A01", "RTR-1180"),
    ("UNIT-A02", "PRJ-ALDR", "16 Alderpoint Terrace", "2028-10-01", True, "HERS-A02", "RTR-1180"),
    ("UNIT-A03", "PRJ-ALDR", "18 Alderpoint Terrace", "2028-12-10", True, "HERS-A03", "RTR-1180"),
    ("UNIT-A04", "PRJ-ALDR", "20 Alderpoint Terrace", "2029-02-20", True, "HERS-A04", "RTR-1204"),
    ("UNIT-B01", "PRJ-BRWT", "3 Brightwater Lane", "2028-09-05", True, "HERS-B01", "RTR-1204"),
    ("UNIT-B02", "PRJ-BRWT", "5 Brightwater Lane", "2028-11-18", True, "HERS-B02", "RTR-1204"),
    ("UNIT-B03", "PRJ-BRWT", "7 Brightwater Lane", "2029-01-22", True, "HERS-B03", "RTR-1180"),
    ("UNIT-C01", "PRJ-CPFD", "101 Copperfield Yard", "2028-08-30", True, "HERS-C01", "RTR-1332"),
    ("UNIT-C02", "PRJ-CPFD", "103 Copperfield Yard", "2028-12-01", True, "HERS-C02", "RTR-1332"),
    ("UNIT-C03", "PRJ-CPFD", "105 Copperfield Yard", "2029-03-15", True, "HERS-C03", "RTR-1332"),
)

#: ``(project_id, total_units, closed_by_period, remaining_units)``. The lifetime
#: roll-forward per project; each closes fully (remaining 0) so the baseline raises
#: no review flag. ``closed_by_period`` has one column per period window below.
ROLLFORWARD: tuple[tuple[Any, ...], ...] = (
    ("PRJ-ALDR", 10, (3, 3, 4), 0),
    ("PRJ-BRWT", 8, (2, 3, 3), 0),
    ("PRJ-CPFD", 7, (2, 2, 3), 0),
)

#: The date windows bounding each roll-forward column (ordered, disjoint).
PERIOD_WINDOWS: tuple[tuple[str, str], ...] = (
    ("2026-07-01", "2027-06-30"),
    ("2027-07-01", "2028-06-30"),
    ("2028-07-01", "2029-06-30"),
)

#: ``(partner_id, name, ownership_bps)``. Ownership foots to 10000 bps (100.00%).
PARTNERS: tuple[tuple[str, str, int], ...] = (
    ("PROG", "Progeny Capital", 5_600),
    ("NMSP", "Northmoor Sponsor", 4_400),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _unit(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_UNIT_REGISTER)
    assert register is not None
    for row in register["units"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _wsproject(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    ws = _doc(payload, DOC_CREDIT_WORKSHEET)
    assert ws is not None
    for row in ws["projects"]:
        if row.get("project_id") == project_id:
            return row
    raise KeyError(project_id)


def _region_subtotal(payload: dict[str, Any], region: str) -> dict[str, Any]:
    ws = _doc(payload, DOC_CREDIT_WORKSHEET)
    assert ws is not None
    for row in ws["region_subtotals"]:
        if row.get("region") == region:
            return row
    raise KeyError(region)


def _rfproject(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    rf = _doc(payload, DOC_PERIOD_ROLLFORWARD)
    assert rf is not None
    for row in rf["projects"]:
        if row.get("project_id") == project_id:
            return row
    raise KeyError(project_id)


def _clproject(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    cl = _doc(payload, DOC_CLOSINGS_SCHEDULE)
    assert cl is not None
    for row in cl["projects"]:
        if row.get("project_id") == project_id:
            return row
    raise KeyError(project_id)


def _partner(payload: dict[str, Any], partner_id: str) -> dict[str, Any]:
    alloc = _doc(payload, DOC_PARTNER_ALLOCATION)
    assert alloc is not None
    for row in alloc["partners"]:
        if row.get("partner_id") == partner_id:
            return row
    raise KeyError(partner_id)


def _final(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_FINAL_REPORT)
    assert report is not None
    return report


def _closings(payload: dict[str, Any]) -> dict[str, Any]:
    cl = _doc(payload, DOC_CLOSINGS_SCHEDULE)
    assert cl is not None
    return cl


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup figure from the payload's own base facts."""
    register = _doc(payload, DOC_UNIT_REGISTER)
    ws = _doc(payload, DOC_CREDIT_WORKSHEET)
    rf = _doc(payload, DOC_PERIOD_ROLLFORWARD)
    alloc = _doc(payload, DOC_PARTNER_ALLOCATION)
    closings = _doc(payload, DOC_CLOSINGS_SCHEDULE)
    report = _doc(payload, DOC_FINAL_REPORT)
    if not all((register, ws, rf, alloc, closings, report)):
        return
    assert register is not None and ws is not None and alloc is not None
    assert closings is not None and report is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    statute = _statute(ctx)
    if statute is None:
        return

    # Per-unit credited amount, through the shared kernel.
    for row in register["units"]:
        unit = _unit_from_row(row)
        row["credited_amount_cents"] = unit_credit_cents(unit, statute) if unit else 0

    # Per-project worksheet line, re-derived from the claimed units.
    for proj in ws["projects"]:
        summary = recompute_project_summary(
            ctx, proj["project_id"], proj.get("region", ""), statute
        )
        proj.update(summary)

    # Worksheet grand totals footed from the project lines.
    ws["total_qualifying_units"] = sum(p["qualifying_units"] for p in ws["projects"])
    ws["total_gross_credit_cents"] = sum(p["gross_credit_cents"] for p in ws["projects"])
    ws["total_net_benefit_cents"] = sum(p["net_benefit_cents"] for p in ws["projects"])

    # Region subtotals, in sorted-region order for byte stability.
    by_region: dict[str, int] = {}
    for p in ws["projects"]:
        by_region[p["region"]] = by_region.get(p["region"], 0) + p["gross_credit_cents"]
    ws["region_subtotals"] = [
        {"region": region, "gross_credit_cents": by_region[region]}
        for region in sorted(by_region)
    ]

    # Partner allocation from the net benefit at ownership shares.
    shares = recompute_partner_shares(ctx, ws["total_net_benefit_cents"])
    if len(shares) == len(alloc["partners"]):
        for partner, share in zip(alloc["partners"], shares):
            partner["allocated_cents"] = share

    # Closings schedule: physically closed units + the credited-unit tie.
    for c in closings["projects"]:
        c["closed_units"] = recompute_closed_units(ctx, c["project_id"])
    closings["total_credited_units"] = ws["total_qualifying_units"]

    # Final report face figures.
    report["total_certified_units"] = ws["total_qualifying_units"]
    report["total_credits_cents"] = ws["total_qualifying_units"] * statute.per_unit_cents


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean §45L credit file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "fiscal_year": FISCAL_YEAR,
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "sunset_date": SUNSET_DATE,
        "statutory_per_unit_cents": d(PER_UNIT_DOLLARS),
        "effective_rate_bps": EFFECTIVE_RATE_BPS,
        "documents": [
            {
                "doc_type": DOC_UNIT_REGISTER,
                "document_id": "UNITS-2029",
                "units": [
                    {
                        "unit_id": unit_id,
                        "project_id": project_id,
                        "address": address,
                        "coe_date": coe_date,
                        "certified": certified,
                        "certificate_ref": certificate_ref,
                        "rater_id": rater_id,
                        "claimed": True,
                        "credited_amount_cents": 0,
                    }
                    for (
                        unit_id, project_id, address, coe_date, certified,
                        certificate_ref, rater_id,
                    ) in UNITS
                ],
            },
            {
                "doc_type": DOC_CREDIT_WORKSHEET,
                "document_id": "WORKSHEET-2029",
                "projects": [
                    {
                        "project_id": project_id,
                        "name": name,
                        "region": region,
                        "qualifying_units": 0,
                        "gross_credit_cents": 0,
                        "addback_cents": 0,
                        "tax_effect_cents": 0,
                        "net_benefit_cents": 0,
                    }
                    for project_id, name, region in PROJECTS
                ],
                "region_subtotals": [],
                "total_qualifying_units": 0,
                "total_gross_credit_cents": 0,
                "total_net_benefit_cents": 0,
            },
            {
                "doc_type": DOC_PERIOD_ROLLFORWARD,
                "document_id": "ROLLFORWARD-2029",
                "period_windows": [
                    {"start": start, "end": end} for start, end in PERIOD_WINDOWS
                ],
                "projects": [
                    {
                        "project_id": project_id,
                        "total_units": total_units,
                        "closed_by_period": list(closed_by_period),
                        "remaining_units": remaining_units,
                    }
                    for project_id, total_units, closed_by_period, remaining_units in ROLLFORWARD
                ],
            },
            {
                "doc_type": DOC_PARTNER_ALLOCATION,
                "document_id": "ALLOCATION-2029",
                "partners": [
                    {
                        "partner_id": partner_id,
                        "name": name,
                        "ownership_bps": ownership_bps,
                        "allocated_cents": 0,
                    }
                    for partner_id, name, ownership_bps in PARTNERS
                ],
            },
            {
                "doc_type": DOC_CLOSINGS_SCHEDULE,
                "document_id": "CLOSINGS-2029",
                "projects": [
                    {"project_id": project_id, "closed_units": 0}
                    for project_id, _n, _r in PROJECTS
                ],
                "prior_period_units": [],
                "total_credited_units": 0,
            },
            {
                "doc_type": DOC_FINAL_REPORT,
                "document_id": "REPORT-2029",
                "total_certified_units": 0,
                "total_credits_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_FINAL_REPORT
    ]


def _duplicate_unit_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_UNIT_REGISTER)
    assert register is not None
    register["units"].append(dict(_unit(payload, "UNIT-A01")))


def _unit_missing_field(payload: dict[str, Any]) -> None:
    del _unit(payload, "UNIT-A02")["address"]


def _unit_unknown_project(payload: dict[str, Any]) -> None:
    _unit(payload, "UNIT-B01")["project_id"] = "PRJ-ZZZ"


def _close_out_of_period(payload: dict[str, Any]) -> None:
    # The unit closed a year before the fiscal-year window opened; its claim takes
    # the credit into a year it does not belong to.
    _unit(payload, "UNIT-A03")["coe_date"] = "2027-05-01"


def _close_after_sunset(payload: dict[str, Any]) -> None:
    # The unit closed inside the fiscal year but after the statutory sunset, so it
    # earns nothing while still sitting inside the period window.
    _unit(payload, "UNIT-A04")["coe_date"] = "2029-05-01"


def _uncertified_claim(payload: dict[str, Any]) -> None:
    _unit(payload, "UNIT-B02")["certified"] = False


def _missing_rater_id(payload: dict[str, Any]) -> None:
    del _unit(payload, "UNIT-C01")["rater_id"]


def _double_count(payload: dict[str, Any]) -> None:
    _closings(payload)["prior_period_units"].append("UNIT-A01")


def _per_unit_wrong(payload: dict[str, Any]) -> None:
    _unit(payload, "UNIT-A02")["credited_amount_cents"] = d(1_500)


def _gross_wrong(payload: dict[str, Any]) -> None:
    _wsproject(payload, "PRJ-ALDR")["gross_credit_cents"] += d(2_000)


def _units_times_rate_wrong(payload: dict[str, Any]) -> None:
    _final(payload)["total_credits_cents"] += 1


def _project_units_wrong(payload: dict[str, Any]) -> None:
    # An extra claimed unit is added to the register without re-deriving the
    # worksheet, so the worksheet count no longer ties the register.
    register = _doc(payload, DOC_UNIT_REGISTER)
    assert register is not None
    register["units"].append(
        {
            "unit_id": "UNIT-A05",
            "project_id": "PRJ-ALDR",
            "address": "22 Alderpoint Terrace",
            "coe_date": "2029-01-15",
            "certified": True,
            "certificate_ref": "HERS-A05",
            "rater_id": "RTR-1180",
            "claimed": True,
            "credited_amount_cents": d(2_000),
        }
    )


def _grand_total_wrong(payload: dict[str, Any]) -> None:
    ws = _doc(payload, DOC_CREDIT_WORKSHEET)
    assert ws is not None
    ws["total_gross_credit_cents"] += d(2_000)


def _region_subtotal_wrong(payload: dict[str, Any]) -> None:
    _region_subtotal(payload, "Region of Marran")["gross_credit_cents"] += d(1_000)


def _total_identity_wrong(payload: dict[str, Any]) -> None:
    _rfproject(payload, "PRJ-CPFD")["total_units"] += 2


def _period_overlap(payload: dict[str, Any]) -> None:
    # The second window is pulled back so it overlaps the first; a closing could
    # then be counted in two periods.
    rf = _doc(payload, DOC_PERIOD_ROLLFORWARD)
    assert rf is not None
    rf["period_windows"][1]["start"] = "2027-01-01"


def _remaining_open(payload: dict[str, Any]) -> None:
    # Units still to close in a future period -- a review flag, not a failure. The
    # total is bumped with the remaining so the roll-forward identity still holds.
    proj = _rfproject(payload, "PRJ-BRWT")
    proj["remaining_units"] += 4
    proj["total_units"] += 4


def _addback_wrong(payload: dict[str, Any]) -> None:
    _wsproject(payload, "PRJ-ALDR")["addback_cents"] += d(500)


def _tax_effect_wrong(payload: dict[str, Any]) -> None:
    _wsproject(payload, "PRJ-ALDR")["tax_effect_cents"] += d(500)


def _net_benefit_wrong(payload: dict[str, Any]) -> None:
    _wsproject(payload, "PRJ-BRWT")["net_benefit_cents"] += d(500)


def _shares_sum_wrong(payload: dict[str, Any]) -> None:
    _partner(payload, "PROG")["allocated_cents"] += d(100)


def _share_rederive_wrong(payload: dict[str, Any]) -> None:
    # The two partners' shares are swapped: the sum is unchanged (so the sum control
    # holds) but neither share re-derives from its ownership.
    prog = _partner(payload, "PROG")
    nmsp = _partner(payload, "NMSP")
    prog["allocated_cents"], nmsp["allocated_cents"] = (
        nmsp["allocated_cents"],
        prog["allocated_cents"],
    )


def _final_report_units_wrong(payload: dict[str, Any]) -> None:
    # The report claims one more certified unit than the worksheet and closings
    # schedule; its total credit is moved with it so the report still foots to
    # itself and only the cross-artifact reconciliation breaks.
    report = _final(payload)
    report["total_certified_units"] += 1
    report["total_credits_cents"] += d(2_000)


def _closed_lt_credited(payload: dict[str, Any]) -> None:
    # The closings schedule shows fewer closed units than the worksheet credits.
    _clproject(payload, "PRJ-CPFD")["closed_units"] = 2


def _certification_gap(payload: dict[str, Any]) -> None:
    # More units closed than were certified and credited -- a review flag inviting a
    # chase for the missing certificates, not a failure.
    _clproject(payload, "PRJ-ALDR")["closed_units"] = 7


def _amount_not_integer(payload: dict[str, Any]) -> None:
    proj = _wsproject(payload, "PRJ-BRWT")
    proj["gross_credit_cents"] = float(proj["gross_credit_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_unit_id": ("unit_unique_ids", _duplicate_unit_id),
    "unit_missing_field": ("unit_required_fields", _unit_missing_field),
    "unit_unknown_project": ("unit_project_known", _unit_unknown_project),
    "close_out_of_period": ("elig_close_in_period", _close_out_of_period),
    "close_after_sunset": ("elig_within_sunset", _close_after_sunset),
    "uncertified_claim": ("cert_present_for_credited", _uncertified_claim),
    "missing_rater_id": ("cert_rater_id", _missing_rater_id),
    "double_count": ("dup_no_double_count", _double_count),
    "per_unit_wrong": ("rate_per_unit", _per_unit_wrong),
    "gross_wrong": ("rate_gross_credit", _gross_wrong),
    "units_times_rate_wrong": ("rpt_units_times_rate", _units_times_rate_wrong),
    "project_units_wrong": ("roll_project_units", _project_units_wrong),
    "grand_total_wrong": ("roll_grand_total", _grand_total_wrong),
    "region_subtotal_wrong": ("roll_region_subtotal", _region_subtotal_wrong),
    "total_identity_wrong": ("fwd_total_identity", _total_identity_wrong),
    "period_overlap": ("fwd_period_bounds", _period_overlap),
    "remaining_open": ("fwd_remaining_to_close", _remaining_open),
    "addback_wrong": ("net_addback", _addback_wrong),
    "tax_effect_wrong": ("net_tax_effect", _tax_effect_wrong),
    "net_benefit_wrong": ("net_benefit", _net_benefit_wrong),
    "shares_sum_wrong": ("alloc_shares_sum", _shares_sum_wrong),
    "share_rederive_wrong": ("alloc_share_rederived", _share_rederive_wrong),
    "final_report_units_wrong": ("recon_final_report_ties", _final_report_units_wrong),
    "closed_lt_credited": ("recon_closed_ge_credited", _closed_lt_credited),
    "certification_gap": ("recon_certification_gap", _certification_gap),
    "amount_not_integer": ("rate_gross_credit", _amount_not_integer),
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
