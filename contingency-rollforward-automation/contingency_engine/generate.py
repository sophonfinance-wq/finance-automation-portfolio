"""
Fictional contingency rollforward corpus generator.
===================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the jurisdictions, the
budget contingency lines, the draw descriptions and every amount and date are
fictional, and the reporting period is set in a fictional future. No real entity,
person, project, jurisdiction or path appears anywhere. The generator is
deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the projects, the budget contingency lines, the draw register, each bucket's
prior-period cumulative allocation and its projected potential use are stated as
base facts. Everything the engine later checks as a rollforward -- the prior
balance, the allocated-this-period total, the current balance, the cumulative
allocation, the adequacy word, the exposure watchlist and the portfolio rollup --
is recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`contingency_engine.rollforward` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the block and keeps the break confined
to one control; a defect that targets a stated figure edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    _block_key,
    _blocks,
    _budget_map,
    count_inadequate,
    recompute_period_allocation,
    recompute_rollup_totals,
    recompute_watchlist,
)
from .model import (
    BUCKET_CONSTRUCTION,
    BUCKET_PROJECT,
    DEFAULT_WATCH_THRESHOLD_BPS,
    DOC_ALLOCATION_REGISTER,
    DOC_BUDGET_REGISTER,
    DOC_CONTINGENCY_BLOCK,
    DOC_EXPOSURE_WATCHLIST,
    DOC_PORTFOLIO_ROLLUP,
    DOC_PROJECT_REGISTER,
    PROJECT_ACTIVE,
    PROJECT_CLOSED,
    Context,
)
from .rollforward import allocated_to_date, assess_adequacy, current_balance

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
)

PERIOD = "FY2031-Q3"
#: First and last day of the reporting period every draw must fall inside.
PERIOD_START = "2031-07-01"
PERIOD_END = "2031-09-30"
#: Watch band, in basis points of the current balance.
WATCH_THRESHOLD_BPS = 8000


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(project_id, name, jurisdiction, status)``. Invented projects in invented
#: jurisdictions. Only active projects restate a contingency block, so the closed
#: one is here to prove the completeness control reads status rather than
#: demanding a block from everything in the register.
PROJECTS: tuple[tuple[Any, ...], ...] = (
    ("PRJ-401", "Brightwater Commons", "City of Kelder", PROJECT_ACTIVE),
    ("PRJ-402", "Copperfield Yards", "State of Marran", PROJECT_ACTIVE),
    ("PRJ-403", "Alderfen Crossing", "City of Kelder", PROJECT_ACTIVE),
    ("PRJ-404", "Thistlebrook Landing", "State of Marran", PROJECT_CLOSED),
)

#: ``(project_id, bucket, budget_contingency)``. Dollars. This is the contingency
#: the project budget funded; every bucket reconciles back to it.
BUDGET: tuple[tuple[Any, ...], ...] = (
    ("PRJ-401", BUCKET_CONSTRUCTION, 4_000_000),
    ("PRJ-401", BUCKET_PROJECT, 1_500_000),
    ("PRJ-402", BUCKET_CONSTRUCTION, 2_800_000),
    ("PRJ-402", BUCKET_PROJECT, 900_000),
    ("PRJ-403", BUCKET_CONSTRUCTION, 6_200_000),
    ("PRJ-403", BUCKET_PROJECT, 2_100_000),
)

#: ``(allocation_id, project_id, bucket, description, allocation_date, amount)``.
#: Dollars. These are the draws against contingency taken in the period; the
#: allocated-this-period line on every bucket is summed from them, never typed.
ALLOCATIONS: tuple[tuple[Any, ...], ...] = (
    ("ALC-5001", "PRJ-401", BUCKET_CONSTRUCTION, "Unforeseen subgrade remediation, Block A", "2031-07-14", 180_000),
    ("ALC-5002", "PRJ-401", BUCKET_CONSTRUCTION, "Storm drain re-route around existing easement", "2031-08-05", 95_000),
    ("ALC-5003", "PRJ-401", BUCKET_PROJECT, "Design clarification package 3", "2031-08-22", 42_000),
    ("ALC-5004", "PRJ-402", BUCKET_CONSTRUCTION, "Elevator hoistway rework", "2031-07-28", 210_000),
    ("ALC-5005", "PRJ-402", BUCKET_PROJECT, "Permit expediting overrun", "2031-09-09", 35_000),
    ("ALC-5006", "PRJ-403", BUCKET_CONSTRUCTION, "Curtain wall anchor redesign", "2031-08-11", 320_000),
    ("ALC-5007", "PRJ-403", BUCKET_CONSTRUCTION, "Winter weather protection", "2031-09-18", 145_000),
    ("ALC-5008", "PRJ-403", BUCKET_PROJECT, "Third-party envelope peer review", "2031-07-06", 58_000),
)

#: ``(project_id, bucket, allocated_prior, projected_use)``. Dollars. The two
#: figures the block cannot derive: what earlier periods already took out of the
#: bucket, and what the project team still expects to need from it. Everything
#: else on the row is computed from these, the budget and the draw register.
BLOCK_BASIS: tuple[tuple[Any, ...], ...] = (
    ("PRJ-401", BUCKET_CONSTRUCTION, 620_000, 1_900_000),
    ("PRJ-401", BUCKET_PROJECT, 210_000, 640_000),
    ("PRJ-402", BUCKET_CONSTRUCTION, 450_000, 1_250_000),
    ("PRJ-402", BUCKET_PROJECT, 120_000, 380_000),
    ("PRJ-403", BUCKET_CONSTRUCTION, 1_100_000, 2_750_000),
    ("PRJ-403", BUCKET_PROJECT, 300_000, 900_000),
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


def _budget_line(payload: dict[str, Any], project_id: str, bucket: str) -> dict[str, Any]:
    register = _doc(payload, DOC_BUDGET_REGISTER)
    assert register is not None
    for row in register["contingency_lines"]:
        if row.get("project_id") == project_id and row.get("bucket") == bucket:
            return row
    raise KeyError((project_id, bucket))


def _allocation(payload: dict[str, Any], allocation_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_ALLOCATION_REGISTER)
    assert register is not None
    for row in register["allocations"]:
        if row.get("allocation_id") == allocation_id:
            return row
    raise KeyError(allocation_id)


def _bucket_row(payload: dict[str, Any], project_id: str, bucket: str) -> dict[str, Any]:
    block = _doc(payload, DOC_CONTINGENCY_BLOCK)
    assert block is not None
    for row in block["buckets"]:
        if row.get("project_id") == project_id and row.get("bucket") == bucket:
            return row
    raise KeyError((project_id, bucket))


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_EXPOSURE_WATCHLIST)
    assert watchlist is not None
    return watchlist


def _rollup_doc(payload: dict[str, Any]) -> dict[str, Any]:
    rollup = _doc(payload, DOC_PORTFOLIO_ROLLUP)
    assert rollup is not None
    return rollup


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts.

    The set of bucket rows is itself a base fact -- which projects restated which
    buckets is what ``ctg_block_complete`` audits -- so this fills each existing
    row rather than rebuilding the list, then re-derives the watchlist and the
    rollup from the rows that are there.
    """
    docs = [
        _doc(payload, DOC_PROJECT_REGISTER),
        _doc(payload, DOC_BUDGET_REGISTER),
        _doc(payload, DOC_ALLOCATION_REGISTER),
        _doc(payload, DOC_CONTINGENCY_BLOCK),
        _doc(payload, DOC_EXPOSURE_WATCHLIST),
        _doc(payload, DOC_PORTFOLIO_ROLLUP),
    ]
    if not all(docs):
        return
    watchlist = _watchlist(payload)
    rollup = _rollup_doc(payload)

    ctx = Context(path=Path("<generated>"), data=payload)
    budget = _budget_map(ctx)
    band = payload.get("watch_threshold_bps", DEFAULT_WATCH_THRESHOLD_BPS)

    # Contingency block: every derived cell on the row, through the shared kernel.
    for row in _blocks(ctx):
        key = _block_key(row)
        line = budget.get(key)
        if line is None:
            continue
        funded = line["budget_contingency_cents"]
        prior_alloc = row["allocated_prior_cents"]
        period_alloc = recompute_period_allocation(ctx, key[0], key[1])
        prior_balance = funded - prior_alloc
        current = current_balance(prior_balance, period_alloc)
        row["prior_balance_cents"] = prior_balance
        row["allocated_period_cents"] = period_alloc
        row["current_balance_cents"] = current
        row["allocated_to_date_cents"] = allocated_to_date(prior_alloc, period_alloc)
        row["adequacy"] = assess_adequacy(current, row["projected_use_cents"])

    # Exposure watchlist: adequate buckets sitting inside the watch band.
    watchlist["entries"] = recompute_watchlist(ctx, band)

    # Portfolio rollup: the block, added up.
    rollup.update(recompute_rollup_totals(ctx))
    rollup["inadequate_count"] = count_inadequate(ctx)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean period file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "watch_threshold_bps": WATCH_THRESHOLD_BPS,
        "documents": [
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PROJECTS-2031Q3",
                "projects": [
                    {
                        "project_id": project_id,
                        "name": name,
                        "jurisdiction": jurisdiction,
                        "status": status,
                    }
                    for project_id, name, jurisdiction, status in PROJECTS
                ],
            },
            {
                "doc_type": DOC_BUDGET_REGISTER,
                "document_id": "BUDGET-2031Q3",
                "contingency_lines": [
                    {
                        "project_id": project_id,
                        "bucket": bucket,
                        "budget_contingency_cents": d(funded),
                    }
                    for project_id, bucket, funded in BUDGET
                ],
            },
            {
                "doc_type": DOC_ALLOCATION_REGISTER,
                "document_id": "DRAWS-2031Q3",
                "allocations": [
                    {
                        "allocation_id": allocation_id,
                        "project_id": project_id,
                        "bucket": bucket,
                        "description": description,
                        "allocation_date": when,
                        "amount_cents": d(amount),
                    }
                    for allocation_id, project_id, bucket, description, when, amount in ALLOCATIONS
                ],
            },
            {
                "doc_type": DOC_CONTINGENCY_BLOCK,
                "document_id": "BLOCK-2031Q3",
                "buckets": [
                    {
                        "project_id": project_id,
                        "bucket": bucket,
                        "prior_balance_cents": 0,
                        "allocated_prior_cents": d(allocated_prior),
                        "allocated_period_cents": 0,
                        "allocated_to_date_cents": 0,
                        "current_balance_cents": 0,
                        "projected_use_cents": d(projected_use),
                        "adequacy": "",
                    }
                    for project_id, bucket, allocated_prior, projected_use in BLOCK_BASIS
                ],
            },
            {
                "doc_type": DOC_EXPOSURE_WATCHLIST,
                "document_id": "WATCH-2031Q3",
                "entries": [],
            },
            {
                "doc_type": DOC_PORTFOLIO_ROLLUP,
                "document_id": "ROLLUP-2031Q3",
                "total_allocated_period_cents": 0,
                "total_current_balance_cents": 0,
                "total_projected_use_cents": 0,
                "inadequate_count": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_PORTFOLIO_ROLLUP
    ]


def _duplicate_project_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_PROJECT_REGISTER)
    assert register is not None
    register["projects"].append(dict(_project(payload, "PRJ-401")))


def _unknown_project_status(payload: dict[str, Any]) -> None:
    # The closed project is re-marked with a status the engine does not know, so
    # whether it owes a block this period can no longer be decided.
    _project(payload, "PRJ-404")["status"] = "mothballed"


def _budget_line_missing(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_BUDGET_REGISTER)
    assert register is not None
    register["contingency_lines"] = [
        r
        for r in register["contingency_lines"]
        if not (r["project_id"] == "PRJ-402" and r["bucket"] == BUCKET_PROJECT)
    ]


def _allocation_missing_field(payload: dict[str, Any]) -> None:
    del _allocation(payload, "ALC-5002")["description"]


def _duplicate_allocation_id(payload: dict[str, Any]) -> None:
    _allocation(payload, "ALC-5007")["allocation_id"] = "ALC-5006"


def _allocation_unknown_project(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_ALLOCATION_REGISTER)
    assert register is not None
    register["allocations"].append(
        {
            "allocation_id": "ALC-5090",
            "project_id": "PRJ-999",
            "bucket": BUCKET_CONSTRUCTION,
            "description": "Temporary shoring at party wall",
            "allocation_date": "2031-08-30",
            "amount_cents": d(64_000),
        }
    )


def _allocation_bad_bucket(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_ALLOCATION_REGISTER)
    assert register is not None
    register["allocations"].append(
        {
            "allocation_id": "ALC-5091",
            "project_id": "PRJ-401",
            "bucket": "soft_cost",
            "description": "Marketing suite fit-out overrun",
            "allocation_date": "2031-09-02",
            "amount_cents": d(28_000),
        }
    )


def _allocation_outside_period(payload: dict[str, Any]) -> None:
    # The draw is booked to this period but dated in the one before it, so the
    # prior balance it is subtracted from already reflected it.
    _allocation(payload, "ALC-5003")["allocation_date"] = "2031-06-15"


def _allocation_not_positive(payload: dict[str, Any]) -> None:
    # A voided authorization is carried as a nil draw rather than removed, so it
    # changes no total while still sitting in the register as a release.
    register = _doc(payload, DOC_ALLOCATION_REGISTER)
    assert register is not None
    register["allocations"].append(
        {
            "allocation_id": "ALC-5092",
            "project_id": "PRJ-402",
            "bucket": BUCKET_PROJECT,
            "description": "Duplicate authorization reversed",
            "allocation_date": "2031-09-20",
            "amount_cents": 0,
        }
    )


def _block_row_missing(payload: dict[str, Any]) -> None:
    # An active project stops restating one of its two buckets; the rollup is
    # re-derived over the rows that remain, so only the completeness control sees
    # the break.
    block = _doc(payload, DOC_CONTINGENCY_BLOCK)
    assert block is not None
    block["buckets"] = [
        r
        for r in block["buckets"]
        if not (r["project_id"] == "PRJ-402" and r["bucket"] == BUCKET_PROJECT)
    ]
    rederive(payload)


def _prior_balance_restated(payload: dict[str, Any]) -> None:
    # The opening balance is nudged without the closing balance following it, so
    # current no longer equals prior less allocated.
    _bucket_row(payload, "PRJ-401", BUCKET_CONSTRUCTION)["prior_balance_cents"] += d(50_000)


def _line_item_dropped(payload: dict[str, Any]) -> None:
    # A draw falls out of the register while the period total keeps counting it.
    register = _doc(payload, DOC_ALLOCATION_REGISTER)
    assert register is not None
    register["allocations"] = [
        r for r in register["allocations"] if r["allocation_id"] != "ALC-5002"
    ]


def _allocated_prior_restated(payload: dict[str, Any]) -> None:
    # The prior-periods column is trimmed without the cumulative column following.
    _bucket_row(payload, "PRJ-403", BUCKET_CONSTRUCTION)["allocated_prior_cents"] -= d(25_000)


def _budget_line_restated(payload: dict[str, Any]) -> None:
    # The bucket is topped up in the budget outside the rollforward: every period
    # identity still holds and the bucket no longer ties to what funded it.
    _budget_line(payload, "PRJ-402", BUCKET_CONSTRUCTION)["budget_contingency_cents"] += d(75_000)


def _draw_exceeds_balance(payload: dict[str, Any]) -> None:
    # One draw is written for more than the bucket held; the block is re-derived
    # around it, so the period arithmetic is internally consistent and only the
    # drawdown walk names the draw that broke it.
    _allocation(payload, "ALC-5005")["amount_cents"] = d(900_000)
    rederive(payload)


def _adequacy_flag_overridden(payload: dict[str, Any]) -> None:
    # The stated assessment contradicts the two amounts on its own row; the rollup
    # count is moved with it so only the recompute control sees the break.
    _bucket_row(payload, "PRJ-401", BUCKET_CONSTRUCTION)["adequacy"] = "inadequate"
    _rollup_doc(payload)["inadequate_count"] = 1


def _projection_negative(payload: dict[str, Any]) -> None:
    _bucket_row(payload, "PRJ-403", BUCKET_PROJECT)["projected_use_cents"] = d(-50_000)
    rederive(payload)


def _headroom_watch(payload: dict[str, Any]) -> None:
    # The bucket still covers its projection, with the headroom inside the watch
    # band; the watchlist is re-derived so only the review flag remains.
    _bucket_row(payload, "PRJ-402", BUCKET_PROJECT)["projected_use_cents"] = d(700_000)
    rederive(payload)


def _portfolio_total_wrong(payload: dict[str, Any]) -> None:
    _rollup_doc(payload)["total_current_balance_cents"] += d(100_000)


def _inadequate_count_wrong(payload: dict[str, Any]) -> None:
    _rollup_doc(payload)["inadequate_count"] += 1


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {
            "project_id": "PRJ-403",
            "bucket": BUCKET_CONSTRUCTION,
            "current_balance_cents": d(4_635_000),
            "projected_use_cents": d(2_750_000),
            "headroom_cents": d(1_885_000),
        }
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _bucket_row(payload, "PRJ-401", BUCKET_CONSTRUCTION)
    row["current_balance_cents"] = float(row["current_balance_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_project_id": ("prj_unique_ids", _duplicate_project_id),
    "unknown_project_status": ("prj_status_valid", _unknown_project_status),
    "budget_line_missing": ("prj_budget_defined", _budget_line_missing),
    "allocation_missing_field": ("alc_required_fields", _allocation_missing_field),
    "duplicate_allocation_id": ("alc_unique_ids", _duplicate_allocation_id),
    "allocation_unknown_project": ("alc_project_exists", _allocation_unknown_project),
    "allocation_bad_bucket": ("alc_bucket_valid", _allocation_bad_bucket),
    "allocation_outside_period": ("alc_within_period", _allocation_outside_period),
    "allocation_not_positive": ("alc_amount_positive", _allocation_not_positive),
    "block_row_missing": ("ctg_block_complete", _block_row_missing),
    "prior_balance_restated": ("ctg_current_rolls_forward", _prior_balance_restated),
    "allocated_prior_restated": ("ctg_to_date_rolls_forward", _allocated_prior_restated),
    "line_item_dropped": ("ctg_allocated_ties_line_items", _line_item_dropped),
    "budget_line_restated": ("ctg_budget_reconciles", _budget_line_restated),
    "draw_exceeds_balance": ("ctg_no_overdraw", _draw_exceeds_balance),
    "projection_negative": ("adq_projection_nonnegative", _projection_negative),
    "adequacy_flag_overridden": ("adq_flag_recomputes", _adequacy_flag_overridden),
    "headroom_watch": ("adq_headroom_watch", _headroom_watch),
    "portfolio_total_wrong": ("rpt_portfolio_foots", _portfolio_total_wrong),
    "inadequate_count_wrong": ("rpt_inadequate_count_ties", _inadequate_count_wrong),
    "watchlist_overstated": ("rpt_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("ctg_current_rolls_forward", _amount_not_integer),
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
