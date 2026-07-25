"""
Fictional project-report corpus generator.
==========================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the jurisdictions, the
budgets, the revenues, the business-plan versions and the milestone dates are
fictional, and the reporting period is set in a fictional future. No real entity,
person, jurisdiction, project or path appears anywhere. The generator is
deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the projects, the budget lines, the current-period revenue inputs, the two
comparative columns' own inputs and the three milestone dates are stated as base
facts. Everything the engine later checks as a derived column -- Cost to
Complete, net project revenue, total project expense, project profit, margin on
cost, both variance columns, both milestone variances, the slippage watchlist and
the report rollup -- is recomputed by :func:`rederive` from those base facts,
through the *same* :mod:`variance_engine.variance` kernel the engine recomputes
with. So the relationships the engine tests are the relationships that produced
the data.

Derivation runs in two stages, which is what keeps a planted defect confined to
one control. :func:`rederive_economics` rebuilds the per-project columns from the
base facts; :func:`rederive_downstream` rebuilds the variance tab, the watchlist
and the rollup from whatever those columns *say*. A defect that edits a base fact
re-derives both stages; a defect that overrides a stated column re-derives only
the second, so the break stays where it was planted.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    _cost_lines,
    _current_rows,
    _milestones,
    _plan_rows,
    _prior_rows,
    recompute_cost_to_complete,
    recompute_margin,
    recompute_milestone_variances,
    recompute_net_revenue,
    recompute_profit,
    recompute_project_expense,
    recompute_rollup,
    recompute_slippage_watchlist,
    recompute_variance_rows,
)
from .model import (
    COST_CONTINGENCY,
    COST_FINANCING,
    COST_HARD,
    COST_LAND,
    COST_SOFT,
    DEFAULT_SLIPPAGE_TOLERANCE_DAYS,
    DOC_BUDGET_VARIANCE,
    DOC_CURRENT_ECONOMICS,
    DOC_MILESTONE_SCHEDULE,
    DOC_PLAN_BASELINE,
    DOC_PRIOR_ECONOMICS,
    DOC_PROJECT_REGISTER,
    DOC_REPORT_ROLLUP,
    DOC_SLIPPAGE_WATCHLIST,
    DOC_VARIANCE_SUMMARY,
    METRIC_GROSS_REVENUE,
    METRIC_NET_REVENUE,
    MILESTONE_COMPLETION,
    MILESTONE_CONSTRUCTION_START,
    MILESTONE_ENTITLEMENT,
    MILESTONE_FIRST_CLOSING,
    MILESTONE_PERMIT,
    MILESTONE_TOPPING_OUT,
    PROJECT_FOR_SALE,
    PROJECT_LAND,
    PROJECT_MIXED_USE,
    PROJECT_RENTAL,
    Context,
)

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
    "Westmere",
)

PERIOD = "FY2029-Q3"
PRIOR_PERIOD = "FY2029-Q2"
#: The report date every schedule test is measured to.
AS_OF = "2029-10-01"
#: The frozen approved Business Plan version the plan column is struck against.
PLAN_VERSION = "BP-2028-R2"
#: The frozen baseline schedule the milestone variances measure to.
SCHEDULE_VERSION = "SCH-2028-R2"
#: Schedule tolerance, in days, before a milestone reaches the watchlist.
SLIPPAGE_TOLERANCE_DAYS = 5


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(project_id, name, project_type, jurisdiction)``. Invented project names in
#: invented jurisdictions.
PROJECTS: tuple[tuple[Any, ...], ...] = (
    ("PRJ-301", "Brightwater Commons", PROJECT_FOR_SALE, "City of Kelder"),
    ("PRJ-302", "Copperfield Yards", PROJECT_RENTAL, "State of Marran"),
    ("PRJ-303", "Ridgeline Terraces", PROJECT_MIXED_USE, "City of Kelder"),
    ("PRJ-304", "Hollowmere Flats", PROJECT_LAND, "State of Marran"),
)

#: ``(line_id, project_id, cost_category, total_budget, cost_to_date)``. Amounts
#: in dollars. CL-3011, CL-3021, CL-3031 and CL-3041 are fully spent, so a Cost to
#: Complete of exactly zero is exercised rather than assumed; CL-3014 is untouched
#: contingency, so a Cost to Complete equal to the whole budget is too.
COST_LINES: tuple[tuple[Any, ...], ...] = (
    ("CL-3011", "PRJ-301", COST_LAND, 18_000_000, 18_000_000),
    ("CL-3012", "PRJ-301", COST_HARD, 62_000_000, 41_000_000),
    ("CL-3013", "PRJ-301", COST_SOFT, 14_000_000, 9_000_000),
    ("CL-3014", "PRJ-301", COST_CONTINGENCY, 6_000_000, 0),
    ("CL-3021", "PRJ-302", COST_LAND, 12_000_000, 12_000_000),
    ("CL-3022", "PRJ-302", COST_HARD, 48_000_000, 30_000_000),
    ("CL-3023", "PRJ-302", COST_SOFT, 11_000_000, 7_000_000),
    ("CL-3024", "PRJ-302", COST_FINANCING, 9_000_000, 4_000_000),
    ("CL-3031", "PRJ-303", COST_LAND, 9_000_000, 9_000_000),
    ("CL-3032", "PRJ-303", COST_HARD, 34_000_000, 12_000_000),
    ("CL-3033", "PRJ-303", COST_SOFT, 8_000_000, 5_000_000),
    ("CL-3034", "PRJ-303", COST_FINANCING, 4_000_000, 1_000_000),
    ("CL-3041", "PRJ-304", COST_LAND, 7_000_000, 7_000_000),
    ("CL-3042", "PRJ-304", COST_HARD, 20_000_000, 6_000_000),
    ("CL-3043", "PRJ-304", COST_SOFT, 5_000_000, 3_000_000),
)

#: ``(project_id, gross_revenue, revenue_deduction, irr_bps)`` for the current
#: period. Amounts in dollars. Total project expense is not stated: it is footed
#: from the budget lines above, which is exactly what ``eco_expense_foots_budget``
#: proves.
CURRENT_ECONOMICS: tuple[tuple[Any, ...], ...] = (
    ("PRJ-301", 130_000_000, 5_000_000, 1820),
    ("PRJ-302", 104_000_000, 4_000_000, 1650),
    ("PRJ-303", 71_500_000, 2_500_000, 1740),
    ("PRJ-304", 41_000_000, 1_000_000, 1580),
)

#: ``(project_id, gross_revenue, revenue_deduction, total_project_expense,
#:   irr_bps)`` as the prior period re-issued it. The prior column carries its own
#: expense: last period's budget is not this period's budget, which is the whole
#: point of reporting a variance.
PRIOR_ECONOMICS: tuple[tuple[Any, ...], ...] = (
    ("PRJ-301", 128_000_000, 5_000_000, 99_000_000, 1795),
    ("PRJ-302", 103_000_000, 4_000_000, 79_500_000, 1630),
    ("PRJ-303", 70_000_000, 2_500_000, 54_000_000, 1710),
    ("PRJ-304", 40_500_000, 1_000_000, 31_500_000, 1565),
)

#: ``(project_id, gross_revenue, revenue_deduction, total_project_expense,
#:   irr_bps)`` as the frozen approved Business Plan struck them.
PLAN_BASELINE: tuple[tuple[Any, ...], ...] = (
    ("PRJ-301", 125_000_000, 5_000_000, 96_000_000, 1750),
    ("PRJ-302", 100_000_000, 4_000_000, 76_000_000, 1600),
    ("PRJ-303", 68_000_000, 2_500_000, 52_000_000, 1680),
    ("PRJ-304", 39_000_000, 1_000_000, 30_000_000, 1550),
)

#: ``(milestone_id, project_id, milestone_name, baseline_date, prior_date,
#:   current_date)``. MS-3043 sits exactly at the schedule tolerance -- six days
#: behind would reach the watchlist, five does not -- so a one-day boundary is the
#: whole of a slippage defect. MS-3022 is already behind the baseline but its date
#: has passed the report date, so it is history rather than a chase.
MILESTONES: tuple[tuple[Any, ...], ...] = (
    ("MS-3011", "PRJ-301", MILESTONE_ENTITLEMENT, "2029-03-15", "2029-03-15", "2029-03-15"),
    ("MS-3012", "PRJ-301", MILESTONE_CONSTRUCTION_START, "2029-07-01", "2029-07-01", "2029-06-28"),
    ("MS-3013", "PRJ-301", MILESTONE_COMPLETION, "2031-04-30", "2031-05-02", "2031-05-02"),
    ("MS-3021", "PRJ-302", MILESTONE_ENTITLEMENT, "2029-02-01", "2029-02-01", "2029-02-01"),
    ("MS-3022", "PRJ-302", MILESTONE_PERMIT, "2029-05-15", "2029-05-20", "2029-05-18"),
    ("MS-3023", "PRJ-302", MILESTONE_COMPLETION, "2031-09-30", "2031-09-30", "2031-09-25"),
    ("MS-3031", "PRJ-303", MILESTONE_ENTITLEMENT, "2029-04-01", "2029-04-01", "2029-04-01"),
    ("MS-3032", "PRJ-303", MILESTONE_CONSTRUCTION_START, "2029-09-01", "2029-09-01", "2029-09-01"),
    ("MS-3033", "PRJ-303", MILESTONE_TOPPING_OUT, "2030-11-15", "2030-11-15", "2030-11-10"),
    ("MS-3041", "PRJ-304", MILESTONE_ENTITLEMENT, "2029-01-15", "2029-01-15", "2029-01-15"),
    ("MS-3042", "PRJ-304", MILESTONE_FIRST_CLOSING, "2030-06-01", "2030-06-05", "2030-06-01"),
    ("MS-3043", "PRJ-304", MILESTONE_COMPLETION, "2031-02-28", "2031-02-28", "2031-03-05"),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _project(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PROJECT_REGISTER)
    assert register is not None
    for row in register["projects"]:
        if row.get("project_id") == project_id:
            return row
    raise KeyError(project_id)


def _line(payload: dict[str, Any], line_id: str) -> dict[str, Any]:
    budget = _doc(payload, DOC_BUDGET_VARIANCE)
    assert budget is not None
    for row in budget["cost_lines"]:
        if row.get("line_id") == line_id:
            return row
    raise KeyError(line_id)


def _economics_row(
    payload: dict[str, Any], doc_type: str, project_id: str
) -> dict[str, Any]:
    doc = _doc(payload, doc_type)
    assert doc is not None
    for row in doc["projects"]:
        if row.get("project_id") == project_id:
            return row
    raise KeyError(project_id)


def _milestone(payload: dict[str, Any], milestone_id: str) -> dict[str, Any]:
    schedule = _doc(payload, DOC_MILESTONE_SCHEDULE)
    assert schedule is not None
    for row in schedule["milestones"]:
        if row.get("milestone_id") == milestone_id:
            return row
    raise KeyError(milestone_id)


def _variance_row(
    payload: dict[str, Any], project_id: str, metric: str
) -> dict[str, Any]:
    summary = _doc(payload, DOC_VARIANCE_SUMMARY)
    assert summary is not None
    for row in summary["rows"]:
        if row.get("project_id") == project_id and row.get("metric") == metric:
            return row
    raise KeyError((project_id, metric))


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_SLIPPAGE_WATCHLIST)
    assert watchlist is not None
    return watchlist


def _rollup(payload: dict[str, Any]) -> dict[str, Any]:
    rollup = _doc(payload, DOC_REPORT_ROLLUP)
    assert rollup is not None
    return rollup


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive_economics(payload: dict[str, Any]) -> None:
    """Rebuild every per-project derived column from the payload's base facts."""
    budget = _doc(payload, DOC_BUDGET_VARIANCE)
    current = _doc(payload, DOC_CURRENT_ECONOMICS)
    prior = _doc(payload, DOC_PRIOR_ECONOMICS)
    plan = _doc(payload, DOC_PLAN_BASELINE)
    schedule = _doc(payload, DOC_MILESTONE_SCHEDULE)
    if budget is None or current is None or prior is None or plan is None:
        return
    ctx = Context(path=Path("<generated>"), data=payload)

    # Budget-variance tab: Cost to Complete is the remainder, never a typed cell.
    for line in _cost_lines(ctx):
        line["cost_to_complete_cents"] = recompute_cost_to_complete(line)

    # Current period: the expense foots the budget lines, then the revenue,
    # profit and margin fall out of it in the order the report reads.
    for row in _current_rows(ctx):
        pid = row.get("project_id") or "?"
        row["total_project_expense_cents"] = recompute_project_expense(ctx, pid)
        row["net_project_revenue_cents"] = recompute_net_revenue(row, f"current[{pid}]")
        row["project_profit_cents"] = recompute_profit(row, f"current[{pid}]")
        row["margin_on_cost_bps"] = recompute_margin(row, f"current[{pid}]")

    # Comparative columns: each carries its own expense, so only the revenue,
    # profit and margin are derived.
    for label, rows in (("prior", _prior_rows(ctx)), ("plan", _plan_rows(ctx))):
        for row in rows:
            pid = row.get("project_id") or "?"
            tag = f"{label}[{pid}]"
            row["net_project_revenue_cents"] = recompute_net_revenue(row, tag)
            row["project_profit_cents"] = recompute_profit(row, tag)
            row["margin_on_cost_bps"] = recompute_margin(row, tag)

    # Milestone block: both variance columns, under the + = ahead convention.
    if schedule is not None:
        for row in _milestones(ctx):
            vs_prior, vs_baseline = recompute_milestone_variances(row)
            row["variance_prior_days"] = vs_prior
            row["variance_baseline_days"] = vs_baseline


def rederive_downstream(payload: dict[str, Any]) -> None:
    """Rebuild the variance tab, the watchlist and the rollup from the columns.

    Everything here reads what the per-project columns *say*, not the base facts
    underneath them, so a defect that overrides a stated column can re-derive the
    downstream tabs and leave the break where it was planted.
    """
    summary = _doc(payload, DOC_VARIANCE_SUMMARY)
    watchlist = _doc(payload, DOC_SLIPPAGE_WATCHLIST)
    rollup = _doc(payload, DOC_REPORT_ROLLUP)
    if summary is None or watchlist is None or rollup is None:
        return
    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    tolerance = payload.get("slippage_tolerance_days", DEFAULT_SLIPPAGE_TOLERANCE_DAYS)

    summary["rows"] = recompute_variance_rows(ctx)
    watchlist["entries"] = recompute_slippage_watchlist(ctx, as_of, tolerance)
    rollup.update(recompute_rollup(ctx))


def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    rederive_economics(payload)
    rederive_downstream(payload)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean project report for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "prior_period": PRIOR_PERIOD,
        "as_of": AS_OF,
        "slippage_tolerance_days": SLIPPAGE_TOLERANCE_DAYS,
        "documents": [
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PROJECTS-2029Q3",
                "projects": [
                    {
                        "project_id": project_id,
                        "name": name,
                        "project_type": project_type,
                        "jurisdiction": jurisdiction,
                        "plan_version": PLAN_VERSION,
                        "baseline_schedule_version": SCHEDULE_VERSION,
                    }
                    for project_id, name, project_type, jurisdiction in PROJECTS
                ],
            },
            {
                "doc_type": DOC_BUDGET_VARIANCE,
                "document_id": "BUDGET-2029Q3",
                "cost_lines": [
                    {
                        "line_id": line_id,
                        "project_id": project_id,
                        "cost_category": category,
                        "total_budget_cents": d(total_budget),
                        "cost_to_date_cents": d(cost_to_date),
                        "cost_to_complete_cents": 0,
                    }
                    for line_id, project_id, category, total_budget, cost_to_date in COST_LINES
                ],
            },
            {
                "doc_type": DOC_CURRENT_ECONOMICS,
                "document_id": "CURRENT-2029Q3",
                "period": PERIOD,
                "projects": [
                    {
                        "project_id": project_id,
                        "gross_revenue_cents": d(gross),
                        "revenue_deduction_cents": d(deduction),
                        "net_project_revenue_cents": 0,
                        "total_project_expense_cents": 0,
                        "project_profit_cents": 0,
                        "margin_on_cost_bps": 0,
                        "irr_bps": irr,
                    }
                    for project_id, gross, deduction, irr in CURRENT_ECONOMICS
                ],
            },
            {
                "doc_type": DOC_PRIOR_ECONOMICS,
                "document_id": "PRIOR-2029Q2",
                "period": PRIOR_PERIOD,
                "projects": [
                    {
                        "project_id": project_id,
                        "gross_revenue_cents": d(gross),
                        "revenue_deduction_cents": d(deduction),
                        "net_project_revenue_cents": 0,
                        "total_project_expense_cents": d(expense),
                        "project_profit_cents": 0,
                        "margin_on_cost_bps": 0,
                        "irr_bps": irr,
                    }
                    for project_id, gross, deduction, expense, irr in PRIOR_ECONOMICS
                ],
            },
            {
                "doc_type": DOC_PLAN_BASELINE,
                "document_id": "PLAN-2028R2",
                "plan_version": PLAN_VERSION,
                "approved_date": "2028-11-15",
                "projects": [
                    {
                        "project_id": project_id,
                        "gross_revenue_cents": d(gross),
                        "revenue_deduction_cents": d(deduction),
                        "net_project_revenue_cents": 0,
                        "total_project_expense_cents": d(expense),
                        "project_profit_cents": 0,
                        "margin_on_cost_bps": 0,
                        "irr_bps": irr,
                    }
                    for project_id, gross, deduction, expense, irr in PLAN_BASELINE
                ],
            },
            {
                "doc_type": DOC_VARIANCE_SUMMARY,
                "document_id": "VARIANCE-2029Q3",
                "basis_plan_version": PLAN_VERSION,
                "basis_prior_period": PRIOR_PERIOD,
                "rows": [],
            },
            {
                "doc_type": DOC_MILESTONE_SCHEDULE,
                "document_id": "SCHEDULE-2029Q3",
                "baseline_schedule_version": SCHEDULE_VERSION,
                "milestones": [
                    {
                        "milestone_id": milestone_id,
                        "project_id": project_id,
                        "milestone_name": name,
                        "baseline_date": baseline_date,
                        "prior_date": prior_date,
                        "current_date": current_date,
                        "variance_prior_days": 0,
                        "variance_baseline_days": 0,
                    }
                    for (
                        milestone_id, project_id, name, baseline_date, prior_date,
                        current_date,
                    ) in MILESTONES
                ],
            },
            {
                "doc_type": DOC_SLIPPAGE_WATCHLIST,
                "document_id": "SLIPPAGE-2029Q3",
                "entries": [],
            },
            {
                "doc_type": DOC_REPORT_ROLLUP,
                "document_id": "ROLLUP-2029Q3",
                "project_count": 0,
                "total_gross_revenue_cents": 0,
                "total_net_project_revenue_cents": 0,
                "total_project_expense_cents": 0,
                "total_project_profit_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_REPORT_ROLLUP
    ]


def _duplicate_project_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_PROJECT_REGISTER)
    assert register is not None
    register["projects"].append(dict(_project(payload, "PRJ-301")))


def _bad_project_type(payload: dict[str, Any]) -> None:
    _project(payload, "PRJ-303")["project_type"] = "industrial_flex"


def _prior_column_missing(payload: dict[str, Any]) -> None:
    # The prior-period tab lost a project, so there is nothing to restate it
    # against. The downstream tabs are re-derived, leaving only the gap.
    prior = _doc(payload, DOC_PRIOR_ECONOMICS)
    assert prior is not None
    prior["projects"] = [
        row for row in prior["projects"] if row.get("project_id") != "PRJ-304"
    ]
    rederive_downstream(payload)


def _line_missing_field(payload: dict[str, Any]) -> None:
    del _line(payload, "CL-3013")["cost_category"]


def _bad_cost_category(payload: dict[str, Any]) -> None:
    _line(payload, "CL-3022")["cost_category"] = "marketing_reserve"


def _orphan_cost_line(payload: dict[str, Any]) -> None:
    budget = _doc(payload, DOC_BUDGET_VARIANCE)
    assert budget is not None
    budget["cost_lines"].append(
        {
            "line_id": "CL-3099",
            "project_id": "PRJ-999",
            "cost_category": COST_HARD,
            "total_budget_cents": d(1_000_000),
            "cost_to_date_cents": d(250_000),
            "cost_to_complete_cents": d(750_000),
        }
    )


def _cost_to_complete_wrong(payload: dict[str, Any]) -> None:
    # The remainder column was nudged without re-striking it against the budget,
    # so the project reports budget it has already spent.
    _line(payload, "CL-3032")["cost_to_complete_cents"] += d(250_000)


def _net_revenue_off(payload: dict[str, Any]) -> None:
    # A revenue deduction was booked after the net revenue line was typed, so the
    # net no longer foots to gross less deductions.
    _economics_row(payload, DOC_CURRENT_ECONOMICS, "PRJ-302")[
        "revenue_deduction_cents"
    ] += d(250_000)


def _expense_off_budget(payload: dict[str, Any]) -> None:
    # A budget line grew, its own remainder was re-struck with it, and the
    # economics tab was never re-footed against the budget tab.
    line = _line(payload, "CL-3042")
    line["total_budget_cents"] += d(500_000)
    line["cost_to_complete_cents"] += d(500_000)


def _profit_off(payload: dict[str, Any]) -> None:
    _economics_row(payload, DOC_CURRENT_ECONOMICS, "PRJ-302")["project_profit_cents"] += d(
        500_000
    )
    rederive_downstream(payload)


def _margin_overstated(payload: dict[str, Any]) -> None:
    _economics_row(payload, DOC_CURRENT_ECONOMICS, "PRJ-301")["margin_on_cost_bps"] += 100
    rederive_downstream(payload)


def _plan_column_broken(payload: dict[str, Any]) -> None:
    # The frozen plan column no longer foots inside itself: its profit is not its
    # own net revenue less its own expense.
    _economics_row(payload, DOC_PLAN_BASELINE, "PRJ-303")["project_profit_cents"] += d(
        400_000
    )
    rederive_downstream(payload)


def _prior_variance_wrong(payload: dict[str, Any]) -> None:
    _variance_row(payload, "PRJ-301", METRIC_GROSS_REVENUE)["variance_vs_prior"] += d(
        100_000
    )


def _plan_variance_wrong(payload: dict[str, Any]) -> None:
    _variance_row(payload, "PRJ-302", METRIC_NET_REVENUE)["plan_value"] -= d(100_000)


def _plan_version_rebased(payload: dict[str, Any]) -> None:
    # The variance tab is headed against a later plan revision than the one the
    # baseline document and the register were approved under.
    summary = _doc(payload, DOC_VARIANCE_SUMMARY)
    assert summary is not None
    summary["basis_plan_version"] = "BP-2029-R1"


def _milestone_unnamed(payload: dict[str, Any]) -> None:
    _milestone(payload, "MS-3022")["milestone_name"] = "site_mobilization"


def _milestone_sign_flipped(payload: dict[str, Any]) -> None:
    # Three days ahead is reported as three days behind: the sign convention was
    # applied backwards when the column was re-keyed.
    row = _milestone(payload, "MS-3012")
    row["variance_prior_days"] = -row["variance_prior_days"]


def _baseline_variance_wrong(payload: dict[str, Any]) -> None:
    _milestone(payload, "MS-3033")["variance_baseline_days"] += 10


def _milestone_slipped(payload: dict[str, Any]) -> None:
    # The completion date moves one day past the schedule tolerance; the report is
    # re-derived so only the slippage flag remains.
    _milestone(payload, "MS-3043")["current_date"] = "2031-03-06"
    rederive(payload)


def _rollup_total_wrong(payload: dict[str, Any]) -> None:
    _rollup(payload)["total_project_profit_cents"] += d(1_000_000)


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {
            "milestone_id": "MS-3013",
            "project_id": "PRJ-301",
            "milestone_name": MILESTONE_COMPLETION,
            "baseline_date": "2031-04-30",
            "current_date": "2031-05-02",
            "variance_baseline_days": -2,
        }
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    line = _line(payload, "CL-3012")
    line["total_budget_cents"] = float(line["total_budget_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_project_id": ("prj_unique_ids", _duplicate_project_id),
    "bad_project_type": ("prj_type_valid", _bad_project_type),
    "prior_column_missing": ("prj_comparatives_present", _prior_column_missing),
    "line_missing_field": ("bud_line_required_fields", _line_missing_field),
    "bad_cost_category": ("bud_category_valid", _bad_cost_category),
    "orphan_cost_line": ("bud_project_exists", _orphan_cost_line),
    "cost_to_complete_wrong": ("bud_cost_to_complete_foots", _cost_to_complete_wrong),
    "net_revenue_off": ("eco_net_revenue_foots", _net_revenue_off),
    "expense_off_budget": ("eco_expense_foots_budget", _expense_off_budget),
    "profit_off": ("eco_profit_foots", _profit_off),
    "margin_overstated": ("eco_margin_on_cost_recomputes", _margin_overstated),
    "plan_column_broken": ("var_comparative_columns_foot", _plan_column_broken),
    "prior_variance_wrong": ("var_prior_column_ties", _prior_variance_wrong),
    "plan_variance_wrong": ("var_plan_column_ties", _plan_variance_wrong),
    "plan_version_rebased": ("var_plan_version_frozen", _plan_version_rebased),
    "milestone_unnamed": ("mst_required_fields", _milestone_unnamed),
    "milestone_sign_flipped": ("mst_variance_sign_convention", _milestone_sign_flipped),
    "baseline_variance_wrong": ("mst_baseline_variance_foots", _baseline_variance_wrong),
    "milestone_slipped": ("mst_slippage_lead_time", _milestone_slipped),
    "rollup_total_wrong": ("rpt_rollup_foots", _rollup_total_wrong),
    "watchlist_overstated": ("rpt_slippage_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("bud_cost_to_complete_foots", _amount_not_integer),
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
