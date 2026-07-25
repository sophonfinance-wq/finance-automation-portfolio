"""
Fictional Section 263A interest-capitalization corpus generator.
================================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the company and job
numbers, the expenditures, the interest and the capitalization rate are
fictional, and the fiscal year is set in a fictional future. No real entity,
person, project, index or path appears anywhere. The generator is deterministic
and takes no seed.

The schedule is derived, not typed
----------------------------------
Only the roster, the trial balance, the accumulated production expenditures, the
period rate, the quarterly interest expense and each project's prior-year
capitalized balance are stated as base facts. Everything the engine later checks
as a re-derivation -- each quarter's capitalized and deducted interest, the
annual totals, the year-over-year ending balance and the schedule rollups -- is
recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`capitalize_engine.capitalize` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the schedule and keeps the break
confined to one control; a defect that targets a stated figure edits that figure
alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .capitalize import (
    capitalized_for_quarter,
    deducted_for_quarter,
    ending_capitalized,
)
from .engine import _data_by_key, _key, _rate_bps, _roster_keys
from .model import (
    DOC_COMPARISON,
    DOC_INTEREST_BY_YEAR,
    DOC_PROJECT_DATA,
    DOC_PROJECT_STATUS,
    DOC_TRIAL_BALANCE,
    STATUS_ACTIVE,
    STATUS_COMPLETE,
    Context,
)

#: Fictional developer labels, rotated for file identity only.
ENTITIES: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
    "Westmere",
)

PERIOD = "FY2029"
#: The review date the completion test is measured to.
AS_OF = "2029-12-31"
#: The calendar quarter-end grid the schedule is built across.
QUARTER_ENDS: tuple[str, ...] = (
    "2029-03-31",
    "2029-06-30",
    "2029-09-30",
    "2029-12-31",
)
#: The single applicable capitalization rate for the period, in basis points.
RATE_BPS = 150


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(company_no, job_no, project_name, status)``. Invented development projects.
PROJECTS: tuple[tuple[str, str, str, str], ...] = (
    ("100", "J-4101", "Brightwater Commons", STATUS_ACTIVE),
    ("100", "J-4102", "Copperfield Yards", STATUS_ACTIVE),
    ("200", "J-4201", "Larkfield Terrace", STATUS_ACTIVE),
    ("200", "J-4202", "Hollowmere Landing", STATUS_ACTIVE),
)

#: Base facts per project, keyed by job number. ``ape`` is the accumulated
#: production expenditures at each quarter-end (dollars, non-decreasing);
#: ``interest`` is the interest expense incurred that quarter (dollars, struck
#: above the capitalized figure so the split has a real deducted remainder);
#: ``prior_year_capitalized`` is the capitalized basis carried in from last year.
PROJECT_FACTS: dict[str, dict[str, Any]] = {
    "J-4101": {
        "ape": (40_000_000, 55_000_000, 68_000_000, 80_000_000),
        "interest": (700_000, 900_000, 1_100_000, 1_300_000),
        "prior_year_capitalized": 2_500_000,
    },
    "J-4102": {
        "ape": (20_000_000, 26_000_000, 30_000_000, 34_000_000),
        "interest": (400_000, 500_000, 560_000, 640_000),
        "prior_year_capitalized": 1_200_000,
    },
    "J-4201": {
        "ape": (12_000_000, 16_000_000, 20_000_000, 24_000_000),
        "interest": (250_000, 320_000, 400_000, 460_000),
        "prior_year_capitalized": 800_000,
    },
    "J-4202": {
        "ape": (8_000_000, 10_000_000, 12_000_000, 15_000_000),
        "interest": (180_000, 220_000, 260_000, 320_000),
        "prior_year_capitalized": 500_000,
    },
}


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _status_row(payload: dict[str, Any], job_no: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_PROJECT_STATUS)
    assert doc is not None
    for row in doc["projects"]:
        if row.get("job_no") == job_no:
            return row
    raise KeyError(job_no)


def _data_row(payload: dict[str, Any], job_no: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_PROJECT_DATA)
    assert doc is not None
    for row in doc["projects"]:
        if row.get("job_no") == job_no:
            return row
    raise KeyError(job_no)


def _data_quarter(payload: dict[str, Any], job_no: str, quarter_end: str) -> dict[str, Any]:
    for q in _data_row(payload, job_no)["quarters"]:
        if q.get("quarter_end") == quarter_end:
            return q
    raise KeyError(quarter_end)


def _interest_row(payload: dict[str, Any], job_no: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_INTEREST_BY_YEAR)
    assert doc is not None
    for row in doc["projects"]:
        if row.get("job_no") == job_no:
            return row
    raise KeyError(job_no)


def _interest_quarter(payload: dict[str, Any], job_no: str, quarter_end: str) -> dict[str, Any]:
    for q in _interest_row(payload, job_no)["quarters"]:
        if q.get("quarter_end") == quarter_end:
            return q
    raise KeyError(quarter_end)


def _comparison_row(payload: dict[str, Any], job_no: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_COMPARISON)
    assert doc is not None
    for row in doc["projects"]:
        if row.get("job_no") == job_no:
            return row
    raise KeyError(job_no)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    interest_doc = _doc(payload, DOC_INTEREST_BY_YEAR)
    comparison_doc = _doc(payload, DOC_COMPARISON)
    status_doc = _doc(payload, DOC_PROJECT_STATUS)
    data_doc = _doc(payload, DOC_PROJECT_DATA)
    if not all((interest_doc, comparison_doc, status_doc, data_doc)):
        return
    assert interest_doc is not None and comparison_doc is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    data_map = _data_by_key(ctx)

    # Interest by Year: each quarter's capitalized interest is the rate applied to
    # the accumulated production expenditures; the deducted portion is what is
    # left of the interest incurred. Annual columns foot the quarters.
    annual_cap_by_key: dict[tuple[str, str], int] = {}
    for interest_row in interest_doc["projects"]:
        key = _key(interest_row)
        data_row = data_map.get(key)
        rate = _rate_bps(data_row)
        if data_row is None or rate is None:
            continue
        ape_by_quarter = {
            q["quarter_end"]: q["accumulated_production_expenditures_cents"]
            for q in data_row["quarters"]
        }
        annual_interest = annual_cap = annual_ded = 0
        for q in interest_row["quarters"]:
            quarter_end = q["quarter_end"]
            if quarter_end not in ape_by_quarter:
                continue
            ape = ape_by_quarter[quarter_end]
            interest = q["interest_expense_cents"]
            capitalized = capitalized_for_quarter(ape, rate)
            deducted = deducted_for_quarter(interest, capitalized)
            q["capitalized_cents"] = capitalized
            q["deducted_cents"] = deducted
            annual_interest += interest
            annual_cap += capitalized
            annual_ded += deducted
        interest_row["annual_interest_cents"] = annual_interest
        interest_row["annual_capitalized_cents"] = annual_cap
        interest_row["annual_deducted_cents"] = annual_ded
        annual_cap_by_key[key] = annual_cap

    # Comparison: roll the prior-year capitalized balance forward by the current
    # year's capitalized interest.
    for row in comparison_doc["projects"]:
        key = _key(row)
        current = annual_cap_by_key.get(key, 0)
        row["current_year_capitalized_cents"] = current
        row["ending_capitalized_cents"] = ending_capitalized(
            row["prior_year_capitalized_cents"], current
        )

    # Schedule rollups: the portfolio total capitalized and the project count.
    interest_doc["total_capitalized_cents"] = sum(
        row.get("annual_capitalized_cents", 0) for row in interest_doc["projects"]
    )
    interest_doc["project_count"] = len(_roster_keys(ctx))


def baseline(entity: str) -> dict[str, Any]:
    """Build a clean capitalization file for ``entity``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "entity": entity,
        "period": PERIOD,
        "as_of": AS_OF,
        "quarter_ends": list(QUARTER_ENDS),
        "documents": [
            {
                "doc_type": DOC_TRIAL_BALANCE,
                "document_id": "TB-2029",
                "projects": [
                    {"company_no": company_no, "job_no": job_no}
                    for company_no, job_no, _name, _status in PROJECTS
                ],
            },
            {
                "doc_type": DOC_PROJECT_STATUS,
                "document_id": "STATUS-2029",
                "projects": [
                    {
                        "company_no": company_no,
                        "job_no": job_no,
                        "project_name": name,
                        "status": status,
                    }
                    for company_no, job_no, name, status in PROJECTS
                ],
            },
            {
                "doc_type": DOC_PROJECT_DATA,
                "document_id": "DATA-2029",
                "projects": [
                    {
                        "company_no": company_no,
                        "job_no": job_no,
                        "capitalization_rate_bps": RATE_BPS,
                        "quarters": [
                            {
                                "quarter_end": quarter_end,
                                "accumulated_production_expenditures_cents": d(ape),
                            }
                            for quarter_end, ape in zip(
                                QUARTER_ENDS, PROJECT_FACTS[job_no]["ape"]
                            )
                        ],
                    }
                    for company_no, job_no, _name, _status in PROJECTS
                ],
            },
            {
                "doc_type": DOC_INTEREST_BY_YEAR,
                "document_id": "INTEREST-2029",
                "projects": [
                    {
                        "company_no": company_no,
                        "job_no": job_no,
                        "quarters": [
                            {
                                "quarter_end": quarter_end,
                                "interest_expense_cents": d(interest),
                                "capitalized_cents": 0,
                                "deducted_cents": 0,
                            }
                            for quarter_end, interest in zip(
                                QUARTER_ENDS, PROJECT_FACTS[job_no]["interest"]
                            )
                        ],
                        "annual_interest_cents": 0,
                        "annual_capitalized_cents": 0,
                        "annual_deducted_cents": 0,
                    }
                    for company_no, job_no, _name, _status in PROJECTS
                ],
                "total_capitalized_cents": 0,
                "project_count": 0,
            },
            {
                "doc_type": DOC_COMPARISON,
                "document_id": "COMPARISON-2029",
                "projects": [
                    {
                        "company_no": company_no,
                        "job_no": job_no,
                        "prior_year_capitalized_cents": d(
                            PROJECT_FACTS[job_no]["prior_year_capitalized"]
                        ),
                        "current_year_capitalized_cents": 0,
                        "ending_capitalized_cents": 0,
                    }
                    for company_no, job_no, _name, _status in PROJECTS
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_COMPARISON
    ]


def _duplicate_project_key(payload: dict[str, Any]) -> None:
    doc = _doc(payload, DOC_PROJECT_STATUS)
    assert doc is not None
    doc["projects"].append(dict(_status_row(payload, "J-4101")))


def _blank_project_name(payload: dict[str, Any]) -> None:
    _status_row(payload, "J-4101")["project_name"] = ""


def _bad_project_status(payload: dict[str, Any]) -> None:
    _status_row(payload, "J-4101")["status"] = "suspended"


def _tb_project_missing(payload: dict[str, Any]) -> None:
    # A project carries an interest balance on the trial balance but was never
    # added to the schedule roster.
    doc = _doc(payload, DOC_TRIAL_BALANCE)
    assert doc is not None
    doc["projects"].append({"company_no": "300", "job_no": "J-9001"})


def _data_quarter_missing(payload: dict[str, Any]) -> None:
    row = _data_row(payload, "J-4101")
    row["quarters"] = [q for q in row["quarters"] if q["quarter_end"] != "2029-09-30"]


def _negative_ape(payload: dict[str, Any]) -> None:
    # A first-quarter accumulated balance entered negative; the schedule is
    # re-derived so only the non-negativity control sees the break.
    _data_quarter(payload, "J-4101", "2029-03-31")[
        "accumulated_production_expenditures_cents"
    ] = d(-5_000_000)
    rederive(payload)


def _ape_decreases(payload: dict[str, Any]) -> None:
    # A third-quarter accumulated balance below the second; re-derived so only the
    # non-decreasing control fires.
    _data_quarter(payload, "J-4101", "2029-09-30")[
        "accumulated_production_expenditures_cents"
    ] = d(40_000_000)
    rederive(payload)


def _invalid_rate(payload: dict[str, Any]) -> None:
    # A rate above 100.00%; left un-derived so the rate-applying controls defer to
    # data_rate_valid and only it fires.
    _data_row(payload, "J-4101")["capitalization_rate_bps"] = 15000


def _rate_inconsistent(payload: dict[str, Any]) -> None:
    # One project rolled at a different valid rate; re-derived so its capitalized
    # figures still re-derive and only the consistency control fires.
    _data_row(payload, "J-4101")["capitalization_rate_bps"] = 120
    rederive(payload)


def _capitalized_misderived(payload: dict[str, Any]) -> None:
    # A base expenditure is raised without re-deriving the capitalized column, so
    # the stated capitalized no longer re-derives from the expenditures.
    _data_quarter(payload, "J-4101", "2029-12-31")[
        "accumulated_production_expenditures_cents"
    ] = d(90_000_000)


def _interest_leaks(payload: dict[str, Any]) -> None:
    # A quarter's interest is raised, and its annual total with it, but the
    # capitalized and deducted split is not -- so a slice of interest leaks.
    _interest_quarter(payload, "J-4101", "2029-06-30")["interest_expense_cents"] += d(50_000)
    _interest_row(payload, "J-4101")["annual_interest_cents"] += d(50_000)


def _capitalized_exceeds_interest(payload: dict[str, Any]) -> None:
    # A quarter's interest is cut below its capitalized figure; re-derived so the
    # split still closes and only the cap-within-interest control fires.
    _interest_quarter(payload, "J-4101", "2029-03-31")["interest_expense_cents"] = d(500_000)
    rederive(payload)


def _annual_total_miscast(payload: dict[str, Any]) -> None:
    # An annual interest total edited without touching the quarters it foots.
    _interest_row(payload, "J-4101")["annual_interest_cents"] += d(100_000)


def _capitalizing_after_completion(payload: dict[str, Any]) -> None:
    # A project placed in service that is still capitalizing interest.
    _status_row(payload, "J-4101")["status"] = STATUS_COMPLETE


def _comparison_current_off(payload: dict[str, Any]) -> None:
    # The comparison's current-year capitalized drifts from the schedule; the
    # ending balance is moved with it so only the schedule-tie control fires.
    row = _comparison_row(payload, "J-4101")
    row["current_year_capitalized_cents"] += d(10_000)
    row["ending_capitalized_cents"] += d(10_000)


def _prior_year_untied(payload: dict[str, Any]) -> None:
    _comparison_row(payload, "J-4101")["ending_capitalized_cents"] += 1


def _total_capitalized_off(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_INTEREST_BY_YEAR)["total_capitalized_cents"] += 1


def _project_count_off(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_INTEREST_BY_YEAR)["project_count"] += 1


def _amount_not_integer(payload: dict[str, Any]) -> None:
    quarter = _data_quarter(payload, "J-4101", "2029-03-31")
    quarter["accumulated_production_expenditures_cents"] = (
        float(quarter["accumulated_production_expenditures_cents"]) + 0.5
    )


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_project_key": ("prj_unique_keys", _duplicate_project_key),
    "blank_project_name": ("prj_name_present", _blank_project_name),
    "bad_project_status": ("prj_status_valid", _bad_project_status),
    "tb_project_missing": ("prj_tb_complete", _tb_project_missing),
    "data_quarter_missing": ("data_project_coverage", _data_quarter_missing),
    "negative_ape": ("data_ape_nonneg", _negative_ape),
    "ape_decreases": ("data_ape_nondecreasing", _ape_decreases),
    "invalid_rate": ("data_rate_valid", _invalid_rate),
    "rate_inconsistent": ("cap_rate_consistent", _rate_inconsistent),
    "capitalized_misderived": ("cap_rederives", _capitalized_misderived),
    "interest_leaks": ("cap_no_leakage", _interest_leaks),
    "capitalized_exceeds_interest": ("cap_within_interest", _capitalized_exceeds_interest),
    "annual_total_miscast": ("cap_annual_total_foots", _annual_total_miscast),
    "capitalizing_after_completion": ("cap_ceased_on_completion", _capitalizing_after_completion),
    "comparison_current_off": ("cmp_current_ties_schedule", _comparison_current_off),
    "prior_year_untied": ("cmp_prior_year_ties", _prior_year_untied),
    "total_capitalized_off": ("rpt_total_capitalized_ties", _total_capitalized_off),
    "project_count_off": ("rpt_project_count_ties", _project_count_off),
    "amount_not_integer": ("cap_rederives", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(ENTITIES[0])
    clean["file_id"] = f"clean__{ENTITIES[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        entity = ENTITIES[(i + 1) % len(ENTITIES)]
        f = baseline(entity)
        f["file_id"] = f"{name}__{entity.replace(' ', '_')}"
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
