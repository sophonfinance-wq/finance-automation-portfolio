"""
Fictional combined-group franchise (margin) tax corpus generator.
=================================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The combined group, the affiliates, the fictional
State of Marran and City of Kelder, the addresses, the registrations, the
consolidated revenue, the receipts and the elected deduction are fictional, and
the fiscal year is set in a fictional future. No real entity, person, state,
city, registration or path appears anywhere. The generator is deterministic and
takes no seed.

The baseline is derived, not typed
----------------------------------
Only the affiliate register, the roster's prior-year members and this year's
additions and removals, the consolidated trial-balance revenue lines, the
receipts rows and the group's elected deduction and rate are stated as base
facts. Every figure the engine later re-derives -- the current member list, the
receipts totals and apportionment factor, consolidated group revenue, the taxable
margin, the apportioned margin and the tax, the per-return tax summary and the
combined-return totals -- is recomputed by :func:`rederive` from those base facts,
through the *same* :mod:`franchise_engine.franchise` kernel the engine recomputes
with. So the relationships the engine tests are the relationships that produced
the data: a defect that changes a base fact re-derives the rollup and keeps the
break confined; a defect that targets a stated rollup edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .franchise import (
    apportioned_margin,
    apportionment_factor_bps,
    combined_members,
    margin_tax,
    taxable_margin,
)
from .model import (
    AFFILIATE_ACTIVE,
    DOC_AFFILIATE_REGISTER,
    DOC_COMBINED_GROUP,
    DOC_FRANCHISE_REPORT,
    DOC_MARGIN_WORKSHEET,
    DOC_RECEIPTS_FACTOR,
    DOC_TAX_SUMMARY,
    DOC_TRIAL_BALANCE,
    HOME_STATE_CODE,
)

#: Fictional combined-group labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
)

PERIOD = "FY2029"
#: The review date every registration-renewal test is measured to.
AS_OF = "2030-05-01"
#: Lead-time window, in days, for the registration-renewal flag.
LEAD_DAYS = 60
#: Fictional Marran combined-margin-tax return form.
FORM_REF = "Form MR-1120C"
#: Registration-renewal date every affiliate carries in the clean baseline (far
#: beyond the lead-time window).
FAR_RENEWAL = "2031-06-30"


# --------------------------------------------------------------------------- #
# Base facts
# --------------------------------------------------------------------------- #
#: ``(affiliate_id, name, street, city, postal_code, registration_id)``. Every
#: affiliate is registered active in the fictional State of Marran. AFF-04 is a
#: registered affiliate that is excluded from the combined group this year; AFF-05
#: joined the group this year.
AFFILIATES: tuple[tuple[Any, ...], ...] = (
    ("AFF-01", "Northmoor Development Group", "120 Brightwater Commons", "Kelder", "MR-40120", "MR-REG-3301"),
    ("AFF-02", "Halbrook Residential Partners", "8 Copperfield Yards", "Kelder", "MR-40118", "MR-REG-3302"),
    ("AFF-03", "Stonecrest Communities", "45 Brightwater Commons", "Kelder", "MR-40120", "MR-REG-3303"),
    ("AFF-04", "Ardenne Field Group", "17 Copperfield Yards", "Kelder", "MR-40118", "MR-REG-3304"),
    ("AFF-05", "Westmere Holdings", "63 Brightwater Commons", "Kelder", "MR-40121", "MR-REG-3305"),
)

#: The combined-group roster continuity: last year's members, the affiliate that
#: joined this year, the affiliate that left. The current member list is rebuilt
#: from these through the shared kernel.
PRIOR_YEAR_MEMBERS: tuple[str, ...] = ("AFF-01", "AFF-02", "AFF-03", "AFF-04")
ADDITIONS: tuple[str, ...] = ("AFF-05",)
REMOVALS: tuple[str, ...] = ("AFF-04",)
#: ``(affiliate_id, reason)`` -- the affiliates not included in the combined group
#: this year, enumerated and reconciled against the removals.
EXCLUDED: tuple[tuple[str, str], ...] = (
    ("AFF-04", "disposed mid-year; no continuing Marran nexus"),
)

#: ``(tb_line_id, affiliate_id, account, revenue_cents)``. The consolidated tax
#: trial-balance revenue lines. AFF-01 carries two lines so the revenue tie has a
#: real sum to check; the group revenue is their total across the members.
TRIAL_BALANCE: tuple[tuple[Any, ...], ...] = (
    ("TB-01", "AFF-01", "40000-development-revenue", 60_000_000_00),
    ("TB-02", "AFF-01", "40100-management-fees", 40_000_000_00),
    ("TB-03", "AFF-02", "40000-development-revenue", 50_000_000_00),
    ("TB-04", "AFF-03", "40000-development-revenue", 30_000_000_00),
    ("TB-05", "AFF-05", "40000-development-revenue", 20_000_000_00),
)

#: ``(affiliate_id, in_state_receipts_cents, everywhere_receipts_cents)``. The
#: single-factor receipts workpaper: in-state (Marran) receipts over everywhere
#: receipts, one row per combined member. In-state is a subset of everywhere.
RECEIPTS: tuple[tuple[Any, ...], ...] = (
    ("AFF-01", 30_000_000_00, 100_000_000_00),
    ("AFF-02", 20_000_000_00, 50_000_000_00),
    ("AFF-03", 10_000_000_00, 30_000_000_00),
    ("AFF-05", 15_000_000_00, 20_000_000_00),
)

#: The group's elected margin deduction, in cents, and the Marran margin-tax rate,
#: in integer basis points. Base facts: the margin, apportionment and tax all
#: re-derive from these.
ELECTED_DEDUCTION_CENTS = 70_000_000_00
RATE_BPS = 75


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _affiliate(payload: dict[str, Any], affiliate_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_AFFILIATE_REGISTER)
    assert register is not None
    for row in register["affiliates"]:
        if row.get("affiliate_id") == affiliate_id:
            return row
    raise KeyError(affiliate_id)


def _group(payload: dict[str, Any]) -> dict[str, Any]:
    group = _doc(payload, DOC_COMBINED_GROUP)
    assert group is not None
    return group


def _tb_line(payload: dict[str, Any], line_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_TRIAL_BALANCE)
    assert register is not None
    for row in register["lines"]:
        if row.get("tb_line_id") == line_id:
            return row
    raise KeyError(line_id)


def _receipts(payload: dict[str, Any]) -> dict[str, Any]:
    doc = _doc(payload, DOC_RECEIPTS_FACTOR)
    assert doc is not None
    return doc


def _worksheet(payload: dict[str, Any]) -> dict[str, Any]:
    worksheet = _doc(payload, DOC_MARGIN_WORKSHEET)
    assert worksheet is not None
    return worksheet


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _doc(payload, DOC_TAX_SUMMARY)
    assert summary is not None
    return summary


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_FRANCHISE_REPORT)
    assert report is not None
    return report


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    receipts = _doc(payload, DOC_RECEIPTS_FACTOR)
    tb = _doc(payload, DOC_TRIAL_BALANCE)
    worksheet = _doc(payload, DOC_MARGIN_WORKSHEET)
    summary = _doc(payload, DOC_TAX_SUMMARY)
    report = _doc(payload, DOC_FRANCHISE_REPORT)
    group = _doc(payload, DOC_COMBINED_GROUP)
    if not all((receipts, tb, worksheet, summary, report, group)):
        return
    assert (
        receipts is not None
        and tb is not None
        and worksheet is not None
        and summary is not None
        and report is not None
        and group is not None
    )

    # Receipts totals and the single apportionment factor, from the rows.
    in_state_total = sum(int(r["in_state_receipts_cents"]) for r in receipts["receipts"])
    everywhere_total = sum(int(r["everywhere_receipts_cents"]) for r in receipts["receipts"])
    factor = apportionment_factor_bps(in_state_total, everywhere_total)
    receipts["in_state_total_cents"] = in_state_total
    receipts["everywhere_total_cents"] = everywhere_total
    receipts["factor_bps"] = factor

    # Consolidated group revenue, from the trial-balance lines.
    revenue = sum(int(line["revenue_cents"]) for line in tb["lines"])
    deduction = int(worksheet["elected_deduction_cents"])
    rate = int(worksheet["rate_bps"])
    margin = taxable_margin(revenue, deduction)
    apportioned = apportioned_margin(margin, factor)
    tax = margin_tax(apportioned, rate)

    worksheet["group_revenue_cents"] = revenue
    worksheet["apportionment_factor_bps"] = factor
    worksheet["taxable_margin_cents"] = margin
    worksheet["apportioned_margin_cents"] = apportioned
    worksheet["tax_cents"] = tax

    # The determination restated, and the combined-return rollup.
    summary["taxable_margin_cents"] = margin
    summary["apportioned_margin_cents"] = apportioned
    summary["tax_cents"] = tax
    report["total_tax_due_cents"] = tax
    report["member_count"] = len(group.get("members", []))


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean combined-return file for ``portfolio``."""
    members = combined_members(PRIOR_YEAR_MEMBERS, ADDITIONS, REMOVALS)
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "form_ref": FORM_REF,
        "as_of": AS_OF,
        "lead_days": LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_AFFILIATE_REGISTER,
                "document_id": "AFFILIATES-2029",
                "affiliates": [
                    {
                        "affiliate_id": affiliate_id,
                        "name": name,
                        "street": street,
                        "city": city,
                        "state": HOME_STATE_CODE,
                        "postal_code": postal,
                        "registration_id": registration_id,
                        "status": AFFILIATE_ACTIVE,
                        "registration_renewal_date": FAR_RENEWAL,
                    }
                    for affiliate_id, name, street, city, postal, registration_id in AFFILIATES
                ],
            },
            {
                "doc_type": DOC_COMBINED_GROUP,
                "document_id": "GROUP-2029",
                "prior_year_members": list(PRIOR_YEAR_MEMBERS),
                "additions": list(ADDITIONS),
                "removals": list(REMOVALS),
                "members": members,
                "excluded": [
                    {"affiliate_id": affiliate_id, "reason": reason}
                    for affiliate_id, reason in EXCLUDED
                ],
            },
            {
                "doc_type": DOC_TRIAL_BALANCE,
                "document_id": "TB-2029",
                "lines": [
                    {
                        "tb_line_id": line_id,
                        "affiliate_id": affiliate_id,
                        "account": account,
                        "revenue_cents": revenue,
                    }
                    for line_id, affiliate_id, account, revenue in TRIAL_BALANCE
                ],
            },
            {
                "doc_type": DOC_RECEIPTS_FACTOR,
                "document_id": "RECEIPTS-2029",
                "receipts": [
                    {
                        "affiliate_id": affiliate_id,
                        "in_state_receipts_cents": in_state,
                        "everywhere_receipts_cents": everywhere,
                    }
                    for affiliate_id, in_state, everywhere in RECEIPTS
                ],
                "in_state_total_cents": 0,
                "everywhere_total_cents": 0,
                "factor_bps": 0,
            },
            {
                "doc_type": DOC_MARGIN_WORKSHEET,
                "document_id": "MARGIN-2029",
                "group_revenue_cents": 0,
                "elected_deduction_cents": ELECTED_DEDUCTION_CENTS,
                "taxable_margin_cents": 0,
                "apportionment_factor_bps": 0,
                "apportioned_margin_cents": 0,
                "rate_bps": RATE_BPS,
                "tax_cents": 0,
            },
            {
                "doc_type": DOC_TAX_SUMMARY,
                "document_id": "SUMMARY-2029",
                "taxable_margin_cents": 0,
                "apportioned_margin_cents": 0,
                "tax_cents": 0,
            },
            {
                "doc_type": DOC_FRANCHISE_REPORT,
                "document_id": "REPORT-2029",
                "total_tax_due_cents": 0,
                "member_count": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_FRANCHISE_REPORT
    ]


def _duplicate_affiliate_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_AFFILIATE_REGISTER)
    assert register is not None
    register["affiliates"].append(dict(_affiliate(payload, "AFF-01")))


def _bad_address(payload: dict[str, Any]) -> None:
    # An affiliate whose address tab is missing its postal code cannot be placed.
    del _affiliate(payload, "AFF-02")["postal_code"]


def _bad_affiliate_status(payload: dict[str, Any]) -> None:
    _affiliate(payload, "AFF-03")["status"] = "pending"


def _registration_renewal_due(payload: dict[str, Any]) -> None:
    # The registration is still current but renews inside the lead-time window.
    _affiliate(payload, "AFF-01")["registration_renewal_date"] = "2030-05-21"


def _roster_discontinuity(payload: dict[str, Any]) -> None:
    # An extra prior-year member means the rebuilt roster no longer equals the
    # stated member list, while the members themselves stay valid and registered.
    _group(payload)["prior_year_members"].append("AFF-06")


def _member_unregistered(payload: dict[str, Any]) -> None:
    # A combined member is dropped from the affiliate register; it is still a
    # member, and now has no address or registration to be admitted on.
    register = _doc(payload, DOC_AFFILIATE_REGISTER)
    assert register is not None
    register["affiliates"] = [
        a for a in register["affiliates"] if a.get("affiliate_id") != "AFF-02"
    ]


def _excluded_unreconciled(payload: dict[str, Any]) -> None:
    # The removed affiliate is no longer enumerated on the excluded list.
    _group(payload)["excluded"] = []


def _tb_missing_field(payload: dict[str, Any]) -> None:
    del _tb_line(payload, "TB-03")["account"]


def _tb_duplicate_line(payload: dict[str, Any]) -> None:
    # A second line reuses an existing id but carries no revenue, so the revenue
    # tie still holds and only the uniqueness control sees it.
    twin = dict(_tb_line(payload, "TB-01"))
    twin["revenue_cents"] = 0
    _doc(payload, DOC_TRIAL_BALANCE)["lines"].append(twin)


def _tb_unknown_member(payload: dict[str, Any]) -> None:
    # A revenue line attributed to an affiliate that is not a combined member; the
    # revenue figure is unchanged, so only the membership control sees it.
    _tb_line(payload, "TB-05")["affiliate_id"] = "AFF-77"


def _receipts_unsound(payload: dict[str, Any]) -> None:
    # One member reports in-state receipts above its everywhere receipts. The
    # rollup is re-derived so only the soundness control sees the break.
    row = next(
        r for r in _receipts(payload)["receipts"] if r["affiliate_id"] == "AFF-02"
    )
    row["in_state_receipts_cents"] = 60_000_000_00
    row["everywhere_receipts_cents"] = 50_000_000_00
    rederive(payload)


def _totals_tie_break(payload: dict[str, Any]) -> None:
    # The stated in-state total no longer sums the rows, by a margin too small to
    # move the floored factor, so only the totals tie sees it.
    _receipts(payload)["in_state_total_cents"] += 100


def _factor_wrong(payload: dict[str, Any]) -> None:
    _receipts(payload)["factor_bps"] += 50


def _worksheet_factor_wrong(payload: dict[str, Any]) -> None:
    _worksheet(payload)["apportionment_factor_bps"] += 50


def _revenue_tie_break(payload: dict[str, Any]) -> None:
    # The stated group revenue no longer sums the trial balance; the margin is
    # moved with it so only the revenue tie sees the break.
    worksheet = _worksheet(payload)
    worksheet["group_revenue_cents"] += 1
    worksheet["taxable_margin_cents"] += 1


def _margin_wrong(payload: dict[str, Any]) -> None:
    _worksheet(payload)["taxable_margin_cents"] += 1


def _apportioned_wrong(payload: dict[str, Any]) -> None:
    _worksheet(payload)["apportioned_margin_cents"] += 1


def _tax_wrong(payload: dict[str, Any]) -> None:
    _worksheet(payload)["tax_cents"] += 1


def _summary_recompute_break(payload: dict[str, Any]) -> None:
    # The summarised tax contradicts the workpapers; the report total is moved with
    # it so only the recompute control sees the break.
    _summary(payload)["tax_cents"] += 1
    _report(payload)["total_tax_due_cents"] += 1


def _report_total_break(payload: dict[str, Any]) -> None:
    _report(payload)["total_tax_due_cents"] += 1


def _amount_not_integer(payload: dict[str, Any]) -> None:
    worksheet = _worksheet(payload)
    worksheet["group_revenue_cents"] = float(worksheet["group_revenue_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_affiliate_id": ("aff_unique_ids", _duplicate_affiliate_id),
    "bad_address": ("aff_address_valid", _bad_address),
    "bad_affiliate_status": ("aff_status_valid", _bad_affiliate_status),
    "registration_renewal_due": ("aff_registration_renewal", _registration_renewal_due),
    "roster_discontinuity": ("grp_roster_continuity", _roster_discontinuity),
    "member_unregistered": ("grp_members_registered", _member_unregistered),
    "excluded_unreconciled": ("grp_excluded_reconciled", _excluded_unreconciled),
    "tb_missing_field": ("tb_required_fields", _tb_missing_field),
    "tb_duplicate_line": ("tb_line_unique", _tb_duplicate_line),
    "tb_unknown_member": ("tb_member_known", _tb_unknown_member),
    "receipts_unsound": ("apt_receipts_sound", _receipts_unsound),
    "totals_tie_break": ("apt_totals_tie_receipts", _totals_tie_break),
    "factor_wrong": ("apt_factor_recomputes", _factor_wrong),
    "worksheet_factor_wrong": ("apt_worksheet_factor_recomputes", _worksheet_factor_wrong),
    "revenue_tie_break": ("mgn_revenue_ties_tb", _revenue_tie_break),
    "margin_wrong": ("mgn_margin_recomputes", _margin_wrong),
    "apportioned_wrong": ("mgn_apportioned_recomputes", _apportioned_wrong),
    "tax_wrong": ("mgn_tax_recomputes", _tax_wrong),
    "summary_recompute_break": ("rpt_summary_recomputes", _summary_recompute_break),
    "report_total_break": ("rpt_report_totals_tie", _report_total_break),
    "amount_not_integer": ("mgn_revenue_ties_tb", _amount_not_integer),
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
