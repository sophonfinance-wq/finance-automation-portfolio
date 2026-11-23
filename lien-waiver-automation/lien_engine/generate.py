"""
Fictional lien-waiver corpus generator.
========================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the subcontractors, the suppliers,
the payments and every amount are fictional, and the construction period is set
in a fictional future. No real entity, person, project or path appears anywhere.
The generator is deterministic and takes no seed.

The baseline is derived, not typed
-----------------------------------
Only the subcontracts, the payments and the lower-tier parties are stated as base
facts. Every figure the engine later checks as a tie-out -- the waiver behind each
payment, the date each lower-tier party must release through, the unwaived
exposure per project, and the waiver-log counts -- is recomputed by
:func:`rederive` from those base facts. So the relationships the engine tests are
the relationships that produced the data: a defect that changes a base fact
re-derives everything downstream and keeps the break confined to one control; a
defect that targets a stated tie-out edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .model import (
    DOC_CONTRACT_REGISTER,
    DOC_EXPOSURE_SUMMARY,
    DOC_LOWER_TIER_REGISTER,
    DOC_PAYMENT_REGISTER,
    DOC_WAIVER_LOG,
    DOC_WAIVER_REGISTER,
    WAIVER_CONDITIONAL,
    WAIVER_UNCONDITIONAL,
)

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

PERIOD = "FY2031-Q1"
#: The review date every coverage and ageing test is measured to.
AS_OF = "2031-03-15"
#: The ageing band, in days, past which an uncleared conditional waiver is flagged.
STALE_CONDITIONAL_DAYS = 60


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(sub_id, name, tier, parent_sub, project)``. Three tier-1 subs the developer
#: pays directly, and one tier-2 sub beneath the first, so the tier-chain control
#: has a real parent link to verify.
CONTRACTS: tuple[tuple[Any, ...], ...] = (
    ("SUB-100", "Ridgeway Concrete",      1, None,      "Brightwater Commons"),
    ("SUB-200", "Calder Steel Erectors",  1, None,      "Copperfield Yards"),
    ("SUB-300", "Thornfield Mechanical",  1, None,      "Alderpoint Terraces"),
    ("SUB-110", "Vellum Rebar Supply",    2, "SUB-100", "Brightwater Commons"),
)

#: ``(payment_id, sub_id, project, period, paid_through_date, amount_cents,
#:   cleared)``. A cleared payment earns both a conditional and an unconditional
#: waiver; an uncleared one earns only the conditional and so sits in exposure.
PAYMENTS: tuple[tuple[Any, ...], ...] = (
    ("PAY-1", "SUB-100", "Brightwater Commons", "2031-01", "2031-01-31", d(120_000), True),
    ("PAY-2", "SUB-100", "Brightwater Commons", "2031-02", "2031-02-28", d(95_000),  False),
    ("PAY-3", "SUB-200", "Copperfield Yards",   "2031-01", "2031-01-31", d(80_000),  True),
    ("PAY-4", "SUB-300", "Alderpoint Terraces", "2031-01", "2031-01-31", d(60_000),  True),
    ("PAY-5", "SUB-300", "Alderpoint Terraces", "2031-02", "2031-02-28", d(45_000),  False),
    ("PAY-6", "SUB-200", "Copperfield Yards",   "2031-02", "2031-02-28", d(30_000),  False),
)

#: ``(party_id, name, parent_sub, project, waiver_through_date)``. The date a party
#: must release through (``required_through_date``) is derived from its parent's
#: payments; the date it actually released through is the base fact stated here.
LOWER_TIER: tuple[tuple[Any, ...], ...] = (
    ("LTP-1", "Meridian Aggregate Co", "SUB-100", "Brightwater Commons", "2031-02-28"),
    ("LTP-2", "Halcyon Fixtures",      "SUB-300", "Alderpoint Terraces", "2031-02-28"),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _sub(payload: dict[str, Any], sub_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_CONTRACT_REGISTER)
    assert register is not None
    for row in register["subcontracts"]:
        if row.get("sub_id") == sub_id:
            return row
    raise KeyError(sub_id)


def _payment(payload: dict[str, Any], payment_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PAYMENT_REGISTER)
    assert register is not None
    for row in register["payments"]:
        if row.get("payment_id") == payment_id:
            return row
    raise KeyError(payment_id)


def _waiver(payload: dict[str, Any], waiver_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_WAIVER_REGISTER)
    assert register is not None
    for row in register["waivers"]:
        if row.get("waiver_id") == waiver_id:
            return row
    raise KeyError(waiver_id)


def _party(payload: dict[str, Any], party_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_LOWER_TIER_REGISTER)
    assert register is not None
    for row in register["parties"]:
        if row.get("party_id") == party_id:
            return row
    raise KeyError(party_id)


def _exposure(payload: dict[str, Any], project: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_EXPOSURE_SUMMARY)
    assert summary is not None
    for row in summary["projects"]:
        if row.get("project") == project:
            return row
    raise KeyError(project)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    contract_doc = _doc(payload, DOC_CONTRACT_REGISTER)
    payment_doc = _doc(payload, DOC_PAYMENT_REGISTER)
    waiver_doc = _doc(payload, DOC_WAIVER_REGISTER)
    lower_doc = _doc(payload, DOC_LOWER_TIER_REGISTER)
    exposure_doc = _doc(payload, DOC_EXPOSURE_SUMMARY)
    log_doc = _doc(payload, DOC_WAIVER_LOG)
    if not all((contract_doc, payment_doc, waiver_doc, lower_doc, exposure_doc, log_doc)):
        return
    assert contract_doc and payment_doc and waiver_doc and lower_doc and exposure_doc and log_doc

    payments = payment_doc["payments"]

    # Waivers: a conditional for every payment, plus an unconditional once cleared.
    waivers: list[dict[str, Any]] = []
    for pay in payments:
        waivers.append(
            {
                "waiver_id": f"WV-C-{pay['payment_id']}",
                "sub_id": pay["sub_id"],
                "project": pay["project"],
                "waiver_type": WAIVER_CONDITIONAL,
                "through_date": pay["paid_through_date"],
                "amount_cents": pay["amount_cents"],
                "payment_id": pay["payment_id"],
            }
        )
        if pay["cleared"] is True:
            waivers.append(
                {
                    "waiver_id": f"WV-U-{pay['payment_id']}",
                    "sub_id": pay["sub_id"],
                    "project": pay["project"],
                    "waiver_type": WAIVER_UNCONDITIONAL,
                    "through_date": pay["paid_through_date"],
                    "amount_cents": pay["amount_cents"],
                    "payment_id": pay["payment_id"],
                }
            )
    waiver_doc["waivers"] = waivers

    # Lower-tier required-through date: the parent's latest paid-through date.
    for party in lower_doc["parties"]:
        parent = party["parent_sub"]
        project = party["project"]
        parent_dates = [
            p["paid_through_date"]
            for p in payments
            if p["sub_id"] == parent and p["project"] == project
        ]
        party["required_through_date"] = max(parent_dates) if parent_dates else None

    # Unwaived exposure per project: payments with no unconditional release.
    covered = {
        w["payment_id"] for w in waivers if w["waiver_type"] == WAIVER_UNCONDITIONAL
    }
    exposure: dict[str, int] = {}
    for pay in payments:
        if pay["payment_id"] in covered:
            continue
        exposure[pay["project"]] = exposure.get(pay["project"], 0) + pay["amount_cents"]
    paid_projects = sorted({p["project"] for p in payments})
    exposure_doc["projects"] = [
        {"project": project, "unwaived_exposure_cents": exposure.get(project, 0)}
        for project in paid_projects
    ]

    # Waiver-log roll-up.
    log_doc["waiver_count"] = len(waivers)
    log_doc["conditional_count"] = sum(
        1 for w in waivers if w["waiver_type"] != WAIVER_UNCONDITIONAL
    )
    log_doc["unconditional_count"] = sum(
        1 for w in waivers if w["waiver_type"] == WAIVER_UNCONDITIONAL
    )
    log_doc["covered_payment_count"] = len(covered)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean portfolio file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_CONTRACT_REGISTER,
                "document_id": "CONTRACT-2031",
                "subcontracts": [
                    {
                        "sub_id": sub_id,
                        "name": name,
                        "tier": tier,
                        "parent_sub": parent,
                        "project": project,
                    }
                    for sub_id, name, tier, parent, project in CONTRACTS
                ],
            },
            {
                "doc_type": DOC_PAYMENT_REGISTER,
                "document_id": "PAYMENT-2031",
                "payments": [
                    {
                        "payment_id": payment_id,
                        "sub_id": sub_id,
                        "project": project,
                        "period": period,
                        "paid_through_date": paid_through,
                        "amount_cents": amount,
                        "cleared": cleared,
                    }
                    for payment_id, sub_id, project, period, paid_through, amount, cleared in PAYMENTS
                ],
            },
            {
                "doc_type": DOC_WAIVER_REGISTER,
                "document_id": "WAIVER-2031",
                "stale_conditional_days": STALE_CONDITIONAL_DAYS,
                "waivers": [],
            },
            {
                "doc_type": DOC_LOWER_TIER_REGISTER,
                "document_id": "LOWERTIER-2031",
                "parties": [
                    {
                        "party_id": party_id,
                        "name": name,
                        "parent_sub": parent,
                        "project": project,
                        "waiver_through_date": waiver_through,
                        "required_through_date": None,
                    }
                    for party_id, name, parent, project, waiver_through in LOWER_TIER
                ],
            },
            {
                "doc_type": DOC_EXPOSURE_SUMMARY,
                "document_id": "EXPOSURE-2031",
                "projects": [],
            },
            {
                "doc_type": DOC_WAIVER_LOG,
                "document_id": "WAIVERLOG-2031",
                "waiver_count": 0,
                "conditional_count": 0,
                "unconditional_count": 0,
                "covered_payment_count": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_WAIVER_LOG
    ]


def _party_missing_field(payload: dict[str, Any]) -> None:
    del _sub(payload, "SUB-200")["name"]


def _party_duplicate_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CONTRACT_REGISTER)
    assert register is not None
    register["subcontracts"].append(dict(_sub(payload, "SUB-100")))


def _party_bad_tier(payload: dict[str, Any]) -> None:
    _sub(payload, "SUB-200")["tier"] = 0


def _party_orphan_lower_tier(payload: dict[str, Any]) -> None:
    _sub(payload, "SUB-110")["parent_sub"] = "SUB-909"


def _party_bad_project(payload: dict[str, Any]) -> None:
    _sub(payload, "SUB-200")["project"] = "Elsewhere Point"


def _pay_missing_field(payload: dict[str, Any]) -> None:
    del _payment(payload, "PAY-3")["period"]


def _pay_unknown_sub(payload: dict[str, Any]) -> None:
    _payment(payload, "PAY-4")["sub_id"] = "SUB-909"


def _pay_negative_amount(payload: dict[str, Any]) -> None:
    _payment(payload, "PAY-1")["amount_cents"] = -d(120_000)


def _pay_bad_paid_through(payload: dict[str, Any]) -> None:
    # Reads in the right format but is not a real date, so it will not parse.
    _payment(payload, "PAY-3")["paid_through_date"] = "2031-02-30"


def _wvr_missing_field(payload: dict[str, Any]) -> None:
    del _waiver(payload, "WV-C-PAY-1")["through_date"]


def _wvr_duplicate_id(payload: dict[str, Any]) -> None:
    _waiver(payload, "WV-C-PAY-2")["waiver_id"] = "WV-C-PAY-1"


def _wvr_bad_type(payload: dict[str, Any]) -> None:
    _waiver(payload, "WV-C-PAY-1")["waiver_type"] = "partial"


def _wvr_bad_reference(payload: dict[str, Any]) -> None:
    _waiver(payload, "WV-C-PAY-1")["payment_id"] = "PAY-909"


def _wvr_amount_mismatch(payload: dict[str, Any]) -> None:
    _waiver(payload, "WV-U-PAY-4")["amount_cents"] += d(1_000)


def _cov_payment_uncovered(payload: dict[str, Any]) -> None:
    # The only waiver on an uncleared payment no longer reaches its paid date.
    _waiver(payload, "WV-C-PAY-2")["through_date"] = "2031-01-01"


def _cov_cleared_conditional_only(payload: dict[str, Any]) -> None:
    # The unconditional release stops short, leaving only the conditional in reach.
    _waiver(payload, "WV-U-PAY-1")["through_date"] = "2031-01-01"


def _cov_conditional_stale(payload: dict[str, Any]) -> None:
    # An uncleared payment under a sub with no lower-tier party, aged well past
    # the upgrade window; the break stays confined to the ageing flag.
    _payment(payload, "PAY-6")["paid_through_date"] = "2030-11-01"


def _tier_no_waiver(payload: dict[str, Any]) -> None:
    _party(payload, "LTP-1")["waiver_through_date"] = None


def _tier_short_waiver(payload: dict[str, Any]) -> None:
    _party(payload, "LTP-1")["waiver_through_date"] = "2031-01-15"


def _tier_wrong_required(payload: dict[str, Any]) -> None:
    # An earlier-than-actual required date: still covered by the release on file,
    # so only the re-derivation control sees the break.
    _party(payload, "LTP-1")["required_through_date"] = "2031-01-10"


def _exp_wrong_figure(payload: dict[str, Any]) -> None:
    _exposure(payload, "Brightwater Commons")["unwaived_exposure_cents"] += d(500)


def _exp_missing_project(payload: dict[str, Any]) -> None:
    summary = _doc(payload, DOC_EXPOSURE_SUMMARY)
    assert summary is not None
    summary["projects"] = [
        row for row in summary["projects"] if row.get("project") != "Copperfield Yards"
    ]


def _rpt_wrong_count(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_WAIVER_LOG)["waiver_count"] += 1


def _rpt_wrong_covered(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_WAIVER_LOG)["covered_payment_count"] += 1


def _amount_not_integer(payload: dict[str, Any]) -> None:
    pay = _payment(payload, "PAY-3")
    pay["amount_cents"] = float(pay["amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "party_missing_field": ("party_required_fields", _party_missing_field),
    "party_duplicate_id": ("party_unique_ids", _party_duplicate_id),
    "party_bad_tier": ("party_tier_valid", _party_bad_tier),
    "party_orphan_lower_tier": ("party_lower_tier_parent", _party_orphan_lower_tier),
    "party_bad_project": ("party_project_exists", _party_bad_project),
    "pay_missing_field": ("pay_required_fields", _pay_missing_field),
    "pay_unknown_sub": ("pay_sub_exists", _pay_unknown_sub),
    "pay_negative_amount": ("pay_amount_positive", _pay_negative_amount),
    "pay_bad_paid_through": ("pay_dates_sensible", _pay_bad_paid_through),
    "wvr_missing_field": ("wvr_required_fields", _wvr_missing_field),
    "wvr_duplicate_id": ("wvr_unique_ids", _wvr_duplicate_id),
    "wvr_bad_type": ("wvr_type_valid", _wvr_bad_type),
    "wvr_bad_reference": ("wvr_references_payment", _wvr_bad_reference),
    "wvr_amount_mismatch": ("wvr_amount_ties_payment", _wvr_amount_mismatch),
    "cov_payment_uncovered": ("cov_payment_covered", _cov_payment_uncovered),
    "cov_cleared_conditional_only": ("cov_cleared_unconditional", _cov_cleared_conditional_only),
    "cov_conditional_stale": ("cov_stale_conditional", _cov_conditional_stale),
    "tier_no_waiver": ("tier_party_has_waiver", _tier_no_waiver),
    "tier_short_waiver": ("tier_waiver_covers", _tier_short_waiver),
    "tier_wrong_required": ("tier_required_recomputes", _tier_wrong_required),
    "exp_wrong_figure": ("exp_recomputes", _exp_wrong_figure),
    "exp_missing_project": ("exp_all_projects_present", _exp_missing_project),
    "rpt_wrong_count": ("rpt_waiver_counts_tie", _rpt_wrong_count),
    "rpt_wrong_covered": ("rpt_covered_count_ties", _rpt_wrong_covered),
    "amount_not_integer": ("pay_amount_positive", _amount_not_integer),
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
