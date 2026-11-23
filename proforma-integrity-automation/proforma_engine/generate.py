"""
Fictional project-proforma (QPR) corpus generator.
==================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the fictional regions,
the costs, the revenues and the reporting dates are fictional, and the reporting
period is set in a fictional future. No real entity, person, project, region or
path appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only each project's base ledger -- its source and use lines, hard and soft cost,
interest, revenue, area, equity split, prior-period figures and milestone dates
-- is stated as base fact. Everything the engine later checks as a stated summary
figure -- total sources and uses, total project cost, net and unlevered profit,
margins, per-NSF cost, the waterfall and split profits, the variances -- is
recomputed by :func:`rederive` from those base facts through the *same*
:mod:`proforma_engine.proforma` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the summary and keeps the break
confined to one control; a defect that targets a stated figure edits that cell
alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    recompute_derived,
    recompute_filed_qpr_count,
)
from .model import (
    DOC_CYCLE_REPORT,
    DOC_FILING_REGISTER,
    DOC_PROFORMA_LEDGER,
    DOC_PROJECT_REGISTER,
    DOC_REPORTING_CALENDAR,
    DOC_TIEOUT_SUMMARY,
    Context,
)

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere Urban Partners",
)

PERIOD = "2031-Q1"
#: The review date every filing due-date gate is measured to.
AS_OF = "2031-02-28"
#: Materiality band, in cents, for the period-over-period profit-swing flag.
MATERIALITY_CENTS = 100_000_000  # $1,000,000.00


def c(dollars: int) -> int:
    """Whole dollars to integer cents."""
    return dollars * 100


#: ``(project_id, name, region, hard, soft, interest, reserve,
#:   [(contingency_label, amount)], net_revenue, nsf, senior_loan,
#:   sponsor_bps, investor_bps, prior_net_profit, prior_total_project_cost,
#:   [(milestone, current, baseline)])``. Dollars are whole dollars; the ledger
#: is built in cents. Each project is internally consistent by construction:
#: sources balance uses, the dev-cost budget equals hard+soft-interest, and the
#: contingency lines sum to their total.
PROJECTS: tuple[tuple[Any, ...], ...] = (
    (
        "PRJ-01", "Brightwater Commons", "Marran",
        30_000_000, 12_000_000, 2_000_000, 2_500_000,
        [("hard_contingency", 1_000_000), ("soft_contingency", 500_000)],
        52_000_000, 200_000, 27_000_000, 3000, 7000,
        9_500_000, 41_800_000,
        [
            ("construction_start", "2031-03-15", "2031-03-01"),
            ("completion", "2032-09-30", "2032-09-15"),
        ],
    ),
    (
        "PRJ-02", "Copperfield Yards", "Marran",
        45_000_000, 18_000_000, 3_000_000, 3_000_000,
        [("hard_contingency", 1_500_000), ("soft_contingency", 750_000)],
        78_000_000, 300_000, 40_000_000, 3000, 7000,
        14_300_000, 62_500_000,
        [
            ("construction_start", "2031-05-01", "2031-04-20"),
            ("completion", "2033-01-15", "2033-01-01"),
        ],
    ),
    (
        "PRJ-03", "Alderpoint Terraces", "Kelder",
        20_000_000, 9_000_000, 1_500_000, 1_800_000,
        [("hard_contingency", 700_000), ("soft_contingency", 300_000)],
        36_000_000, 150_000, 18_000_000, 3500, 6500,
        6_650_000, 28_900_000,
        [
            ("construction_start", "2031-06-15", "2031-06-01"),
            ("completion", "2032-12-20", "2032-12-10"),
        ],
    ),
)

#: ``region -> (qpr_due, market_update_due, apartment_report_due, acq_summary_due)``.
CALENDAR: dict[str, tuple[str, str, str, str]] = {
    "Marran": ("2031-01-22", "2031-01-25", "2031-01-25", "2031-01-25"),
    "Kelder": ("2031-02-19", "2031-02-22", "2031-02-22", "2031-02-22"),
}

#: ``project_id -> qpr filed date`` (all on or before the region due date).
QPR_FILED: dict[str, str] = {
    "PRJ-01": "2031-01-20",
    "PRJ-02": "2031-01-21",
    "PRJ-03": "2031-02-18",
}

#: ``region -> filed date`` for each regional deliverable (on or before due).
REGIONAL_FILED: dict[str, str] = {
    "Marran": "2031-01-24",
    "Kelder": "2031-02-21",
}


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _ledger_row(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_PROFORMA_LEDGER)
    assert doc is not None
    for row in doc["projects"]:
        if row.get("project_id") == project_id:
            return row
    raise KeyError(project_id)


def _summary_row(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_TIEOUT_SUMMARY)
    assert doc is not None
    for row in doc["projects"]:
        if row.get("project_id") == project_id:
            return row
    raise KeyError(project_id)


def _cycle(payload: dict[str, Any]) -> dict[str, Any]:
    doc = _doc(payload, DOC_CYCLE_REPORT)
    assert doc is not None
    return doc


def _filing(payload: dict[str, Any]) -> dict[str, Any]:
    doc = _doc(payload, DOC_FILING_REGISTER)
    assert doc is not None
    return doc


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every stated summary figure and the cycle count from base facts."""
    ledger_doc = _doc(payload, DOC_PROFORMA_LEDGER)
    summary = _doc(payload, DOC_TIEOUT_SUMMARY)
    cycle = _doc(payload, DOC_CYCLE_REPORT)
    if ledger_doc is None or summary is None or cycle is None:
        return

    summary["projects"] = [recompute_derived(row) for row in ledger_doc["projects"]]

    ctx = Context(path=Path("<generated>"), data=payload)
    cycle["filed_qpr_count"] = recompute_filed_qpr_count(ctx)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean proforma file for ``portfolio``."""
    ledger_projects: list[dict[str, Any]] = []
    register_projects: list[dict[str, Any]] = []
    for (
        pid, name, region, hard, soft, interest, reserve, contingencies,
        revenue, nsf, senior, sponsor_bps, investor_bps, prior_np, prior_tpc, milestones,
    ) in PROJECTS:
        tpc = c(hard) + c(soft)
        register_projects.append(
            {"project_id": pid, "name": name, "region": region, "active": True}
        )
        ledger_projects.append(
            {
                "project_id": pid,
                "sources": [
                    {"label": "senior_loan", "amount_cents": c(senior)},
                    {"label": "equity", "amount_cents": tpc - c(senior)},
                ],
                "uses": [
                    {"label": "hard_costs", "amount_cents": c(hard)},
                    {"label": "soft_costs", "amount_cents": c(soft)},
                ],
                "hard_cost_cents": c(hard),
                "soft_cost_cents": c(soft),
                "interest_cost_cents": c(interest),
                "interest_reserve_cents": c(reserve),
                "contingencies": [
                    {"label": label, "amount_cents": c(amount)} for label, amount in contingencies
                ],
                "contingency_total_cents": sum(c(amount) for _label, amount in contingencies),
                "dev_cost_budget_cents": c(hard) + c(soft) - c(interest),
                "net_revenue_cents": c(revenue),
                "nsf": nsf,
                "equity_funded_before_construction": True,
                "sponsor_bps": sponsor_bps,
                "investor_bps": investor_bps,
                "prior": {
                    "net_profit_cents": c(prior_np),
                    "total_project_cost_cents": c(prior_tpc),
                },
                "milestones": [
                    {"name": mname, "current": cur, "baseline": base}
                    for mname, cur, base in milestones
                ],
            }
        )

    regions_used = sorted({p["region"] for p in register_projects})
    calendar_rows = [
        {
            "region": region,
            "qpr_due_date": CALENDAR[region][0],
            "market_update_due_date": CALENDAR[region][1],
            "apartment_report_due_date": CALENDAR[region][2],
            "acq_summary_due_date": CALENDAR[region][3],
        }
        for region in regions_used
    ]
    qpr_filings = [
        {"project_id": p["project_id"], "filed_date": QPR_FILED[p["project_id"]]}
        for p in register_projects
    ]
    regional_filings = [
        {"region": region, "deliverable": deliverable, "filed_date": REGIONAL_FILED[region]}
        for region in regions_used
        for deliverable in ("market_update", "apartment_report", "acq_summary")
    ]

    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "materiality_cents": MATERIALITY_CENTS,
        "documents": [
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PROJECTS-2031Q1",
                "projects": register_projects,
            },
            {
                "doc_type": DOC_PROFORMA_LEDGER,
                "document_id": "LEDGER-2031Q1",
                "projects": ledger_projects,
            },
            {
                "doc_type": DOC_TIEOUT_SUMMARY,
                "document_id": "SUMMARY-2031Q1",
                "projects": [],
            },
            {
                "doc_type": DOC_REPORTING_CALENDAR,
                "document_id": "CALENDAR-2031Q1",
                "regions": calendar_rows,
            },
            {
                "doc_type": DOC_FILING_REGISTER,
                "document_id": "FILINGS-2031Q1",
                "qpr_filings": qpr_filings,
                "regional_filings": regional_filings,
            },
            {
                "doc_type": DOC_CYCLE_REPORT,
                "document_id": "CYCLE-2031Q1",
                "filed_qpr_count": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_CYCLE_REPORT
    ]


def _sources_total_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["total_sources_cents"] += 1


def _uses_total_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["total_uses_cents"] += 1


def _source_use_imbalance(payload: dict[str, Any]) -> None:
    # An unfunded use line is appended, so uses exceed sources. Re-deriving keeps
    # the stated totals tied to their lines, leaving only the balance broken.
    _ledger_row(payload, "PRJ-01")["uses"].append(
        {"label": "unfunded_overrun", "amount_cents": c(250_000)}
    )
    rederive(payload)


def _hard_soft_total_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["total_project_cost_cents"] += 1


def _devbudget_wrong(payload: dict[str, Any]) -> None:
    _ledger_row(payload, "PRJ-01")["dev_cost_budget_cents"] += 1


def _contingency_rollup_wrong(payload: dict[str, Any]) -> None:
    _ledger_row(payload, "PRJ-01")["contingency_total_cents"] += 1


def _interest_reserve_short(payload: dict[str, Any]) -> None:
    row = _ledger_row(payload, "PRJ-01")
    row["interest_reserve_cents"] = row["interest_cost_cents"] - 1


def _equity_not_funded_first(payload: dict[str, Any]) -> None:
    _ledger_row(payload, "PRJ-01")["equity_funded_before_construction"] = False


def _net_profit_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["net_profit_cents"] += 1


def _unlevered_profit_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["unlevered_profit_cents"] += 1


def _waterfall_profit_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["waterfall_profit_cents"] += 1


def _budgeted_profit_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["budgeted_profit_cents"] += 1


def _distributed_profit_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["distributed_profit_cents"] += 1


def _sponsor_share_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["sponsor_profit_cents"] += 1


def _split_leaks(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["investor_profit_cents"] += 1


def _margin_on_cost_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["margin_on_cost_bps"] += 1


def _margin_on_revenue_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["margin_on_revenue_bps"] += 1


def _cost_per_nsf_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["cost_per_nsf_cents"] += 1


def _variance_typed(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["variance"]["net_profit_cents"] += 1


def _schedule_variance_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "PRJ-01")["schedule_variance_days"]["construction_start"] += 1


def _profit_swing_material(payload: dict[str, Any]) -> None:
    # Revenue jumps, so net profit swings far beyond the materiality band against
    # prior. Re-deriving keeps every tie-out intact, leaving only the FLAG.
    row = _ledger_row(payload, "PRJ-01")
    row["net_revenue_cents"] += c(2_500_000)
    rederive(payload)


def _qpr_missing(payload: dict[str, Any]) -> None:
    filing = _filing(payload)
    filing["qpr_filings"] = [
        f for f in filing["qpr_filings"] if f.get("project_id") != "PRJ-02"
    ]
    rederive(payload)


def _qpr_late(payload: dict[str, Any]) -> None:
    for f in _filing(payload)["qpr_filings"]:
        if f.get("project_id") == "PRJ-01":
            f["filed_date"] = "2031-02-01"  # after the Marran QPR due date


def _regional_deliverable_missing(payload: dict[str, Any]) -> None:
    filing = _filing(payload)
    filing["regional_filings"] = [
        r
        for r in filing["regional_filings"]
        if not (r.get("region") == "Marran" and r.get("deliverable") == "market_update")
    ]


def _cycle_count_wrong(payload: dict[str, Any]) -> None:
    _cycle(payload)["filed_qpr_count"] += 1


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _ledger_row(payload, "PRJ-01")
    row["hard_cost_cents"] = float(row["hard_cost_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "sources_total_wrong": ("src_sources_total_ties", _sources_total_wrong),
    "uses_total_wrong": ("src_uses_total_ties", _uses_total_wrong),
    "source_use_imbalance": ("src_source_use_balance", _source_use_imbalance),
    "hard_soft_total_wrong": ("cost_hard_soft_total", _hard_soft_total_wrong),
    "devbudget_wrong": ("cost_unlevered_ties_devbudget", _devbudget_wrong),
    "contingency_rollup_wrong": ("cost_contingency_rollup", _contingency_rollup_wrong),
    "interest_reserve_short": ("int_reserve_adequate", _interest_reserve_short),
    "equity_not_funded_first": ("int_equity_funded_before_construction", _equity_not_funded_first),
    "net_profit_wrong": ("prof_net_profit_derivation", _net_profit_wrong),
    "unlevered_profit_wrong": ("prof_unlevered_profit_derivation", _unlevered_profit_wrong),
    "waterfall_profit_wrong": ("wfl_waterfall_ties_net", _waterfall_profit_wrong),
    "budgeted_profit_wrong": ("wfl_budgeted_ties_net", _budgeted_profit_wrong),
    "distributed_profit_wrong": ("wfl_distributed_ties_net", _distributed_profit_wrong),
    "sponsor_share_wrong": ("wfl_sponsor_share_derivation", _sponsor_share_wrong),
    "split_leaks": ("wfl_split_completeness", _split_leaks),
    "margin_on_cost_wrong": ("mgn_margin_on_cost", _margin_on_cost_wrong),
    "margin_on_revenue_wrong": ("mgn_margin_on_revenue", _margin_on_revenue_wrong),
    "cost_per_nsf_wrong": ("mgn_cost_per_nsf", _cost_per_nsf_wrong),
    "variance_typed": ("var_metric_delta", _variance_typed),
    "schedule_variance_wrong": ("var_schedule_days", _schedule_variance_wrong),
    "profit_swing_material": ("var_materiality_flag", _profit_swing_material),
    "qpr_missing": ("rpt_project_qpr_filed", _qpr_missing),
    "qpr_late": ("rpt_qpr_due_date_gate", _qpr_late),
    "regional_deliverable_missing": ("rpt_regional_deliverables_present", _regional_deliverable_missing),
    "cycle_count_wrong": ("rpt_cycle_count_ties", _cycle_count_wrong),
    "amount_not_integer": ("cost_hard_soft_total", _amount_not_integer),
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
