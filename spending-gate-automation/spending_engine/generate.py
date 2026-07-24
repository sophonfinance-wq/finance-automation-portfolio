"""
Fictional capital spending request corpus generator.
====================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control
fire.

Everything here is invented. The developers, the projects, the regions, the
vendors, the dollar figures and every date are fictional, and the underwriting
period is set in a fictional future. No real entity, person, place, vendor,
project or path appears anywhere. The generator is deterministic and takes no
seed.

The baseline is derived, not typed
----------------------------------
Only the profile, the approvals, the spend ledger, the cost stack, the
checklist, the bid schedule and the comparison figures are stated as base
facts. Everything the engine later checks as a determination -- the stated
fees and the total, the gate summary, the plan-comparison variances -- is
recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`spending_engine.standards` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the determinations and keeps the
break confined to one control; a defect that targets a stated determination
edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import recompute_gate_rows
from .model import (
    DELIVERABLE_TYPES,
    DOC_APPROVAL_LOG,
    DOC_BID_SCHEDULE,
    DOC_COST_BUDGET,
    DOC_DELIVERABLE_CHECKLIST,
    DOC_EVENT_LOG,
    DOC_GATE_SUMMARY,
    DOC_PLAN_COMPARISON,
    DOC_PROJECT_PROFILE,
    DOC_SPEND_LEDGER,
    GC_OWNER,
    PHASE_APPROVALS,
    PHASE_CONSTRUCTION,
    PHASE_ENACTMENT_ZONING,
    PHASE_FEASIBILITY,
    PHASE_INITIAL_COMMITMENT,
    REGION_MARRAN,
    REGION_VANTERRE,
    REQUEST_INTERIM,
    REQUEST_PHASE,
    Context,
)
from .standards import (
    BASIS_ACTUAL_PLAN,
    BASIS_TEMPLATE,
    derive_fee_block,
    derive_variance,
)

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere",
)

#: Fictional project the request package underwrites.
PROJECT = "Brightwater Commons"

PERIOD = "FY2030"
#: The review date every calendar test is measured to.
AS_OF = "2030-03-15"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: The base cost stack, in dollars. The contingencies sit exactly at their
#: floors -- 10% site, 5% vertical, 5% soft -- so a one-cent shortfall is the
#: whole of a boundary defect. The fees and the total are never stated here;
#: :func:`rederive` derives them through the shared standards kernel.
SITE_HARD = 18_000_000
VERTICAL_HARD = 6_000_000
HARD_COST = SITE_HARD + VERTICAL_HARD
SITE_CONTINGENCY = 1_800_000
VERTICAL_CONTINGENCY = 300_000
HARD_CONTINGENCY = SITE_CONTINGENCY + VERTICAL_CONTINGENCY
SOFT_COST = 4_000_000
SOFT_CONTINGENCY = 200_000
FINANCING_COST = 1_500_000

#: ``(approval_id, request_type, phase, approval_date)``. The five phase gates
#: in date order, plus one interim request for the financing-closing event.
APPROVALS: tuple[tuple[Any, ...], ...] = (
    ("SR-01", REQUEST_PHASE, PHASE_INITIAL_COMMITMENT, "2028-09-15"),
    ("SR-02", REQUEST_PHASE, PHASE_FEASIBILITY, "2029-01-20"),
    ("SR-03", REQUEST_PHASE, PHASE_ENACTMENT_ZONING, "2029-06-18"),
    ("SR-04", REQUEST_PHASE, PHASE_APPROVALS, "2029-11-05"),
    ("SR-05", REQUEST_PHASE, PHASE_CONSTRUCTION, "2030-02-10"),
    ("INT-01", REQUEST_INTERIM, None, "2029-08-02"),
)

#: ``(entry_id, spend_date, category, amount)``. Amounts in dollars. Every
#: trigger-sensitive spend post-dates the Initial Commitment approval of
#: 2028-09-15; the pursuit trigger fires on the second entry, the refundable
#: trigger on its first.
SPEND_ENTRIES: tuple[tuple[Any, ...], ...] = (
    ("SP-01", "2028-10-01", "pursuit_cost", 30_000),
    ("SP-02", "2028-11-01", "pursuit_cost", 40_000),
    ("SP-03", "2028-12-01", "refundable_deposit", 150_000),
    ("SP-04", "2029-03-01", "nonrefundable_deposit", 250_000),
)

#: ``(line_id, description, amount, competitively_bid)``. Amounts in dollars;
#: the lines foot to the hard cost and every line is competitively bid, so both
#: GC-model coverage tests hold on the baseline.
BID_LINES: tuple[tuple[Any, ...], ...] = (
    ("BID-01", "Sitework & excavation -- Alderpoint Sitework", 6_000_000, True),
    ("BID-02", "Structural concrete -- Kettleridge Concrete", 6_000_000, True),
    ("BID-03", "Framing & carpentry -- Dunmore Timberworks", 4_500_000, True),
    ("BID-04", "Mechanical & plumbing -- Copperfield Mechanical", 3_500_000, True),
    ("BID-05", "Electrical -- Westmere Electric", 2_500_000, True),
    ("BID-06", "Finishes -- Halbrook Interiors", 1_500_000, True),
)

#: ``(metric, project, plan)``. Dollars. The variance column is never stated
#: here; :func:`rederive` derives it.
COMPARISON_ROWS: tuple[tuple[Any, ...], ...] = (
    ("net_operating_income", 2_150_000, 2_000_000),
    ("total_revenue", 41_000_000, 40_000_000),
    ("residual_land_value", 2_600_000, 2_750_000),
)

#: ``(event_id, event_type, event_date, interim_request_id)``.
EVENTS: tuple[tuple[Any, ...], ...] = (
    ("EV-01", "financing_closing", "2029-07-25", "INT-01"),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _profile(payload: dict[str, Any]) -> dict[str, Any]:
    profile = _doc(payload, DOC_PROJECT_PROFILE)
    assert profile is not None
    return profile


def _budget(payload: dict[str, Any]) -> dict[str, Any]:
    budget = _doc(payload, DOC_COST_BUDGET)
    assert budget is not None
    return budget


def _approval(payload: dict[str, Any], approval_id: str) -> dict[str, Any]:
    log = _doc(payload, DOC_APPROVAL_LOG)
    assert log is not None
    for row in log["approvals"]:
        if row.get("approval_id") == approval_id:
            return row
    raise KeyError(approval_id)


def _remove_approval(payload: dict[str, Any], approval_id: str) -> None:
    log = _doc(payload, DOC_APPROVAL_LOG)
    assert log is not None
    log["approvals"] = [
        row for row in log["approvals"] if row.get("approval_id") != approval_id
    ]


def _spend_ledger(payload: dict[str, Any]) -> dict[str, Any]:
    ledger = _doc(payload, DOC_SPEND_LEDGER)
    assert ledger is not None
    return ledger


def _checklist_row(payload: dict[str, Any], deliverable: str) -> dict[str, Any]:
    checklist = _doc(payload, DOC_DELIVERABLE_CHECKLIST)
    assert checklist is not None
    for row in checklist["items"]:
        if row.get("deliverable") == deliverable:
            return row
    raise KeyError(deliverable)


def _bid_line(payload: dict[str, Any], line_id: str) -> dict[str, Any]:
    schedule = _doc(payload, DOC_BID_SCHEDULE)
    assert schedule is not None
    for row in schedule["lines"]:
        if row.get("line_id") == line_id:
            return row
    raise KeyError(line_id)


def _comparison(payload: dict[str, Any]) -> dict[str, Any]:
    comparison = _doc(payload, DOC_PLAN_COMPARISON)
    assert comparison is not None
    return comparison


def _gate_row(payload: dict[str, Any], phase: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_GATE_SUMMARY)
    assert summary is not None
    for row in summary["phases"]:
        if row.get("phase") == phase:
            return row
    raise KeyError(phase)


def _events(payload: dict[str, Any]) -> dict[str, Any]:
    events = _doc(payload, DOC_EVENT_LOG)
    assert events is not None
    return events


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every determination from the payload's own base facts."""
    budget = _doc(payload, DOC_COST_BUDGET)
    summary = _doc(payload, DOC_GATE_SUMMARY)
    comparison = _doc(payload, DOC_PLAN_COMPARISON)
    log = _doc(payload, DOC_APPROVAL_LOG)
    checklist = _doc(payload, DOC_DELIVERABLE_CHECKLIST)
    if not all((budget, summary, comparison, log, checklist)):
        return
    assert budget is not None and summary is not None and comparison is not None

    # Fees and total: derived from the cost stack through the shared kernel.
    cm_fee, dev_fee, tpc = derive_fee_block(
        budget["hard_cost_cents"],
        budget["hard_contingency_cents"],
        budget["soft_cost_cents"],
        budget["soft_contingency_cents"],
        budget["financing_cost_cents"],
    )
    budget["cm_fee_cents"] = cm_fee
    budget["dev_fee_cents"] = dev_fee
    budget["total_project_cost_cents"] = tpc

    # Gate summary: one determination per phase, recomputed through the shared
    # kernel the engine recomputes with.
    ctx = Context(path=Path("<generated>"), data=payload)
    summary["phases"] = recompute_gate_rows(ctx)

    # Plan comparison: the variance column, derived from the stated figures.
    for row in comparison.get("rows", []):
        project = row.get("project_cents")
        plan = row.get("plan_cents")
        if isinstance(project, int) and isinstance(plan, int):
            row["variance_cents"] = derive_variance(project, plan)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean request package for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_PROJECT_PROFILE,
                "document_id": "PROFILE-2030",
                "project_id": "PRJ-2100",
                "project_name": PROJECT,
                "region": REGION_MARRAN,
                "gc_model": "third_party_gc",
                "current_phase": PHASE_CONSTRUCTION,
                "feasibility_waived": True,
                "revenue_growth_bps": 300,
                "cost_growth_bps": 300,
                "market_supported_growth": False,
            },
            {
                "doc_type": DOC_APPROVAL_LOG,
                "document_id": "APPROVALS-2030",
                "approvals": [
                    {
                        "approval_id": approval_id,
                        "request_type": request_type,
                        **({"phase": phase} if phase is not None else {}),
                        "approval_date": approval_date,
                    }
                    for approval_id, request_type, phase, approval_date in APPROVALS
                ],
            },
            {
                "doc_type": DOC_SPEND_LEDGER,
                "document_id": "SPEND-2030",
                "entries": [
                    {
                        "entry_id": entry_id,
                        "spend_date": spend_date,
                        "category": category,
                        "amount_cents": d(amount),
                    }
                    for entry_id, spend_date, category, amount in SPEND_ENTRIES
                ],
            },
            {
                "doc_type": DOC_COST_BUDGET,
                "document_id": "BUDGET-2030",
                "estimate_basis": "bindable_gmp",
                "hard_cost_cents": d(HARD_COST),
                "site_hard_cost_cents": d(SITE_HARD),
                "vertical_hard_cost_cents": d(VERTICAL_HARD),
                "hard_contingency_cents": d(HARD_CONTINGENCY),
                "site_contingency_cents": d(SITE_CONTINGENCY),
                "vertical_contingency_cents": d(VERTICAL_CONTINGENCY),
                "soft_cost_cents": d(SOFT_COST),
                "soft_contingency_cents": d(SOFT_CONTINGENCY),
                "soft_floor_justification_documented": False,
                "financing_cost_cents": d(FINANCING_COST),
                "cm_fee_cents": 0,
                "dev_fee_cents": 0,
                "total_project_cost_cents": 0,
            },
            {
                "doc_type": DOC_DELIVERABLE_CHECKLIST,
                "document_id": "DELIVERABLES-2030",
                "items": [
                    {"deliverable": deliverable, "status": "complete"}
                    for deliverable in DELIVERABLE_TYPES
                ],
            },
            {
                "doc_type": DOC_BID_SCHEDULE,
                "document_id": "BIDS-2030",
                "gmp_bindable": True,
                "lines": [
                    {
                        "line_id": line_id,
                        "description": description,
                        "amount_cents": d(amount),
                        "competitively_bid": bid,
                    }
                    for line_id, description, amount, bid in BID_LINES
                ],
            },
            {
                "doc_type": DOC_PLAN_COMPARISON,
                "document_id": "COMPARE-2030",
                "basis": BASIS_ACTUAL_PLAN,
                "rows": [
                    {
                        "metric": metric,
                        "project_cents": d(project),
                        "plan_cents": d(plan),
                        "variance_cents": 0,
                    }
                    for metric, project, plan in COMPARISON_ROWS
                ],
            },
            {
                "doc_type": DOC_GATE_SUMMARY,
                "document_id": "GATES-2030",
                "phases": [],
            },
            {
                "doc_type": DOC_EVENT_LOG,
                "document_id": "EVENTS-2030",
                "events": [
                    {
                        "event_id": event_id,
                        "event_type": event_type,
                        "event_date": event_date,
                        "interim_request_id": interim_request_id,
                    }
                    for event_id, event_type, event_date, interim_request_id in EVENTS
                ],
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_GATE_SUMMARY
    ]


def _pursuit_spend_before_ic(payload: dict[str, Any]) -> None:
    # A pursuit invoice pre-dating the Initial Commitment approval carries the
    # cumulative total past the trigger on its own.
    _spend_ledger(payload)["entries"].append(
        {
            "entry_id": "SP-90",
            "spend_date": "2028-08-01",
            "category": "pursuit_cost",
            "amount_cents": d(60_000),
        }
    )


def _nonrefundable_before_ic(payload: dict[str, Any]) -> None:
    _spend_ledger(payload)["entries"].append(
        {
            "entry_id": "SP-91",
            "spend_date": "2028-08-20",
            "category": "nonrefundable_deposit",
            "amount_cents": d(10_000),
        }
    )


def _refundable_before_ic(payload: dict[str, Any]) -> None:
    _spend_ledger(payload)["entries"].append(
        {
            "entry_id": "SP-92",
            "spend_date": "2028-08-10",
            "category": "refundable_deposit",
            "amount_cents": d(120_000),
        }
    )


def _unknown_phase(payload: dict[str, Any]) -> None:
    # The stated phase is not one of the five gates, so no phase-indexed
    # standard can be looked up at all.
    _profile(payload)["current_phase"] = "stabilization"


def _approvals_out_of_order(payload: dict[str, Any]) -> None:
    # The feasibility gate is dated after the gates that follow it.
    _approval(payload, "SR-02")["approval_date"] = "2029-12-01"


def _phase_skipped(payload: dict[str, Any]) -> None:
    _remove_approval(payload, "SR-03")
    rederive(payload)


def _current_phase_unapproved(payload: dict[str, Any]) -> None:
    _remove_approval(payload, "SR-05")
    rederive(payload)


def _gate_summary_wrong(payload: dict[str, Any]) -> None:
    # The stated determination contradicts the approvals and the checklist.
    _gate_row(payload, PHASE_APPROVALS)["gate_cleared"] = False


def _unknown_deliverable(payload: dict[str, Any]) -> None:
    checklist = _doc(payload, DOC_DELIVERABLE_CHECKLIST)
    assert checklist is not None
    checklist["items"].append({"deliverable": "heliport_clearance", "status": "complete"})


def _duplicate_deliverable(payload: dict[str, Any]) -> None:
    checklist = _doc(payload, DOC_DELIVERABLE_CHECKLIST)
    assert checklist is not None
    checklist["items"].append(dict(_checklist_row(payload, "title_report")))


def _prior_deliverable_incomplete(payload: dict[str, Any]) -> None:
    _checklist_row(payload, "environmental_phase_2")["status"] = "outstanding"
    rederive(payload)


def _current_deliverable_outstanding(payload: dict[str, Any]) -> None:
    # A current-phase deliverable is still open; the gate summary re-derives
    # unchanged (entry gates read only prior phases), so only the FLAG remains.
    _checklist_row(payload, "building_permits")["status"] = "outstanding"
    rederive(payload)


def _estimate_basis_wrong(payload: dict[str, Any]) -> None:
    _budget(payload)["estimate_basis"] = "divisional"


def _hard_contingency_below_floor(payload: dict[str, Any]) -> None:
    # One cent under the construction-start site floor; the fee block is
    # re-derived so the break stays confined to the floor control.
    budget = _budget(payload)
    budget["site_contingency_cents"] -= 1
    budget["hard_contingency_cents"] -= 1
    rederive(payload)


def _soft_contingency_below_floor(payload: dict[str, Any]) -> None:
    budget = _budget(payload)
    budget["soft_contingency_cents"] -= 1
    rederive(payload)


def _hard_split_does_not_foot(payload: dict[str, Any]) -> None:
    # The site leg was restated without the total moving with it.
    _budget(payload)["site_hard_cost_cents"] -= d(100)


def _escalation_reserve_missing(payload: dict[str, Any]) -> None:
    # A vanterre project on the low hard-cost floor with no separate
    # escalation contingency reserved.
    _profile(payload)["region"] = REGION_VANTERRE


def _growth_not_default(payload: dict[str, Any]) -> None:
    _profile(payload)["revenue_growth_bps"] = 450


def _cm_fee_overstated(payload: dict[str, Any]) -> None:
    _budget(payload)["cm_fee_cents"] += d(50_000)


def _dev_fee_overstated(payload: dict[str, Any]) -> None:
    _budget(payload)["dev_fee_cents"] += d(25_000)


def _tpc_does_not_foot(payload: dict[str, Any]) -> None:
    _budget(payload)["total_project_cost_cents"] += d(100)


def _variance_misstated(payload: dict[str, Any]) -> None:
    _comparison(payload)["rows"][0]["variance_cents"] += d(1_000)


def _comparison_basis_wrong(payload: dict[str, Any]) -> None:
    # Feasibility is waived but the comparison still points at the template.
    _comparison(payload)["basis"] = BASIS_TEMPLATE


def _stale_template(payload: dict[str, Any]) -> None:
    # The template regime is correctly in effect, but the comparison stands on
    # the previous refresh rather than the one in force at the review date.
    _profile(payload)["feasibility_waived"] = False
    comparison = _comparison(payload)
    comparison["basis"] = BASIS_TEMPLATE
    comparison["template_effective_date"] = "2029-06-01"


def _bid_coverage_short(payload: dict[str, Any]) -> None:
    # The largest sitework line was never competitively bid, dropping coverage
    # to 75% of hard cost.
    _bid_line(payload, "BID-01")["competitively_bid"] = False


def _gmp_not_bindable(payload: dict[str, Any]) -> None:
    _profile(payload)["gc_model"] = GC_OWNER
    schedule = _doc(payload, DOC_BID_SCHEDULE)
    assert schedule is not None
    schedule["gmp_bindable"] = False


def _unknown_event_type(payload: dict[str, Any]) -> None:
    _events(payload)["events"].append(
        {"event_id": "EV-90", "event_type": "meteor_watch", "event_date": "2029-09-01"}
    )


def _interim_request_missing(payload: dict[str, Any]) -> None:
    _events(payload)["events"].append(
        {
            "event_id": "EV-91",
            "event_type": "material_change",
            "event_date": "2029-09-10",
            "interim_request_id": "INT-09",
        }
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    budget = _budget(payload)
    budget["cm_fee_cents"] = float(budget["cm_fee_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "pursuit_spend_before_ic": ("trg_ic_before_pursuit_spend", _pursuit_spend_before_ic),
    "nonrefundable_before_ic": (
        "trg_ic_before_nonrefundable_deposit",
        _nonrefundable_before_ic,
    ),
    "refundable_before_ic": ("trg_ic_before_refundable_deposits", _refundable_before_ic),
    "unknown_phase": ("seq_phase_known", _unknown_phase),
    "approvals_out_of_order": ("seq_approvals_in_order", _approvals_out_of_order),
    "phase_skipped": ("seq_no_phase_skipped", _phase_skipped),
    "current_phase_unapproved": ("seq_current_phase_approved", _current_phase_unapproved),
    "gate_summary_wrong": ("seq_gate_summary_recomputes", _gate_summary_wrong),
    "unknown_deliverable": ("del_items_known", _unknown_deliverable),
    "duplicate_deliverable": ("del_unique_rows", _duplicate_deliverable),
    "prior_deliverable_incomplete": (
        "del_prior_phase_complete",
        _prior_deliverable_incomplete,
    ),
    "current_deliverable_outstanding": (
        "del_current_phase_outstanding",
        _current_deliverable_outstanding,
    ),
    "estimate_basis_wrong": ("del_estimate_basis_matches", _estimate_basis_wrong),
    "hard_contingency_below_floor": ("cty_hard_floor", _hard_contingency_below_floor),
    "soft_contingency_below_floor": ("cty_soft_floor", _soft_contingency_below_floor),
    "hard_split_does_not_foot": ("cty_split_foots", _hard_split_does_not_foot),
    "escalation_reserve_missing": ("cty_escalation_reserved", _escalation_reserve_missing),
    "growth_not_default": ("gro_growth_default", _growth_not_default),
    "cm_fee_overstated": ("fee_cm_rederives", _cm_fee_overstated),
    "dev_fee_overstated": ("fee_dev_rederives", _dev_fee_overstated),
    "tpc_does_not_foot": ("fee_tpc_foots", _tpc_does_not_foot),
    "variance_misstated": ("fee_variance_rederives", _variance_misstated),
    "comparison_basis_wrong": ("cal_basis_matches_waiver", _comparison_basis_wrong),
    "stale_template": ("cal_template_current", _stale_template),
    "bid_coverage_short": ("bid_coverage_meets", _bid_coverage_short),
    "gmp_not_bindable": ("bid_gmp_bindable", _gmp_not_bindable),
    "unknown_event_type": ("evt_type_known", _unknown_event_type),
    "interim_request_missing": ("evt_interim_request_filed", _interim_request_missing),
    "amount_not_integer": ("fee_cm_rederives", _amount_not_integer),
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
