"""
Fictional "Upcoming Financings" report corpus generator.
========================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the regions, the
financial partners, the milestone dates and the financing amounts are fictional,
and the report period is set in a fictional future. No real entity, person, bank,
city, state or path appears anywhere. The generator is deterministic and takes no
seed.

The baseline is derived, not typed
----------------------------------
Only the workstreams, the milestone dates, the playbooks and the master tracker
are stated as base facts. Everything the engine later checks as a re-derivation --
each milestone's variance and overdue flag, each Gantt month, and the portfolio's
active / overdue / financing-total counts -- is recomputed by :func:`rederive`
from those base facts, through the *same* :mod:`financing_engine.schedule` kernel
the engine recomputes with. So the relationships the engine tests are the
relationships that produced the data: a defect that changes a base fact
re-derives the rollup and keeps the break confined to one control; a defect that
targets a stated rollup edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .engine import (
    recompute_active_count,
    recompute_financing_total,
    recompute_overdue,
    recompute_overdue_count,
    recompute_variance,
    _workstream_map,
)
from .model import (
    DOC_FINANCING_REPORT,
    DOC_GANTT_SUMMARY,
    DOC_MASTER_TRACKER,
    DOC_MILESTONE_SCHEDULE,
    DOC_PLAYBOOK_CATALOG,
    DOC_PRIOR_SCHEDULE,
    DOC_WORKSTREAM_REGISTER,
    FINANCING_DEBT,
    FINANCING_EQUITY,
    FINANCING_EXTENSION,
    STATUS_ACTIVE,
    STATUS_CLOSED,
    Context,
)
from .schedule import gantt_month

#: Fictional developer labels, rotated for file identity only.
ENTITIES: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere Capital",
)

PERIOD = "2029-06"
#: The report date every overdue and period-end test is measured to.
REPORT_DATE = "2029-06-30"
#: The base report date as a ``date`` for the schedule arithmetic below.
REPORT = date(2029, 6, 30)


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: The canonical ordered milestone set for each financing type.
PLAYBOOK_NAMES: dict[str, list[str]] = {
    FINANCING_DEBT: [
        "Finalize Marketing Materials",
        "Receive Term Sheets",
        "Best & Final with Lenders",
        "Credit Approval",
        "Close",
    ],
    FINANCING_EQUITY: [
        "Updated Calling List",
        "Finalize Materials",
        "Launch Marketing",
        "Commitments Received",
        "Investor Funding",
    ],
    FINANCING_EXTENSION: [
        "Check-in with Lender",
        "Lender Appraisal Published",
        "Extension Terms",
        "Extension Credit Approval",
        "Finalize Extension Docs",
    ],
}

#: ``(workstream_id, project, region, financing_type, status, target_closing,
#:   financial_partner, financing_amount_dollars)``. Invented projects, regions
#: and partners; each active workstream carries its type's full playbook below.
WORKSTREAMS: tuple[tuple[Any, ...], ...] = (
    ("WS-01", "Brightwater Commons", "State of Marran", FINANCING_DEBT, STATUS_ACTIVE, "2029-09-15", "Harborline Bank", 40_000_000),
    ("WS-02", "Copperfield Yards", "State of Marran", FINANCING_EQUITY, STATUS_ACTIVE, "2029-10-20", "Kelder Equity Partners", 25_000_000),
    ("WS-03", "Alderpoint Terraces", "City of Kelder", FINANCING_EXTENSION, STATUS_ACTIVE, "2029-11-10", "Meridian Mezzanine", 60_000_000),
    ("WS-04", "Dunmore Flats", "City of Kelder", FINANCING_DEBT, STATUS_ACTIVE, "2029-12-05", "Vantage Capital Trust", 35_000_000),
    ("WS-05", "Millbrook Court", "State of Marran", FINANCING_EQUITY, STATUS_CLOSED, "2029-07-31", "Kelder Equity Partners", 18_000_000),
)

#: Fictional responsible-team labels, rotated across workstreams.
RESP = ("Deal Team A", "Deal Team B", "Deal Team C", "Deal Team D", "Deal Team E")


# --------------------------------------------------------------------------- #
# Base schedule construction
# --------------------------------------------------------------------------- #
def _schedule_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the milestone rows and the prior-schedule snapshot.

    Current dates rise with milestone sequence and stay in the future, so no
    milestone is overdue; each Prior is the current minus 25 days (last month's
    Current) and each Original sits 60 days back (the frozen baseline). The
    prior-schedule row carries last month's Original (identical) and Current (this
    month's Prior), so the roll-forward and baseline controls tie.
    """
    milestones: list[dict[str, Any]] = []
    prior: list[dict[str, Any]] = []
    for i, (wid, _project, _region, ftype, _status, _target, _partner, _amount) in enumerate(
        WORKSTREAMS
    ):
        for j, name in enumerate(PLAYBOOK_NAMES[ftype]):
            current = REPORT + timedelta(days=30 + i * 3 + j * 20)
            prior_date = current - timedelta(days=25)
            original = current - timedelta(days=60)
            mid = f"{wid}-M{j + 1}"
            milestones.append(
                {
                    "milestone_id": mid,
                    "workstream_id": wid,
                    "name": name,
                    "sequence": j + 1,
                    "original_date": original.isoformat(),
                    "prior_date": prior_date.isoformat(),
                    "current_date": current.isoformat(),
                    "variance_days": 0,
                    "overdue": False,
                    "resp": RESP[i % len(RESP)],
                }
            )
            prior.append(
                {
                    "milestone_id": mid,
                    "original_date": original.isoformat(),
                    "current_date": prior_date.isoformat(),
                }
            )
    return milestones, prior


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _workstream(payload: dict[str, Any], workstream_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_WORKSTREAM_REGISTER)
    assert register is not None
    for row in register["workstreams"]:
        if row.get("workstream_id") == workstream_id:
            return row
    raise KeyError(workstream_id)


def _milestone(payload: dict[str, Any], milestone_id: str) -> dict[str, Any]:
    schedule = _doc(payload, DOC_MILESTONE_SCHEDULE)
    assert schedule is not None
    for row in schedule["milestones"]:
        if row.get("milestone_id") == milestone_id:
            return row
    raise KeyError(milestone_id)


def _prior_row(payload: dict[str, Any], milestone_id: str) -> dict[str, Any]:
    prior = _doc(payload, DOC_PRIOR_SCHEDULE)
    assert prior is not None
    for row in prior["prior_milestones"]:
        if row.get("milestone_id") == milestone_id:
            return row
    raise KeyError(milestone_id)


def _gantt_bar(payload: dict[str, Any], workstream_id: str) -> dict[str, Any]:
    gantt = _doc(payload, DOC_GANTT_SUMMARY)
    assert gantt is not None
    for row in gantt["bars"]:
        if row.get("workstream_id") == workstream_id:
            return row
    raise KeyError(workstream_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_FINANCING_REPORT)
    assert report is not None
    return report


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    schedule = _doc(payload, DOC_MILESTONE_SCHEDULE)
    gantt = _doc(payload, DOC_GANTT_SUMMARY)
    report = _doc(payload, DOC_FINANCING_REPORT)
    register = _doc(payload, DOC_WORKSTREAM_REGISTER)
    if not all((schedule, gantt, report, register)):
        return
    assert schedule is not None and gantt is not None and report is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    report_date = date.fromisoformat(payload["report_date"])
    workstream_map = _workstream_map(ctx)

    # Milestone variance and overdue, recomputed through the shared kernel.
    for milestone in schedule["milestones"]:
        variance = recompute_variance(milestone)
        if variance is not None:
            milestone["variance_days"] = variance
        overdue = recompute_overdue(ctx, milestone, workstream_map, report_date)
        if overdue is not None:
            milestone["overdue"] = overdue

    # Gantt bar month, recomputed from each bar's target closing.
    for bar in gantt["bars"]:
        target = bar.get("target_closing")
        if isinstance(target, str):
            try:
                bar["gantt_month"] = gantt_month(date.fromisoformat(target))
            except ValueError:
                pass

    # Portfolio rollup, derived from the register and the schedule.
    report["active_count"] = recompute_active_count(ctx)
    report["overdue_count"] = recompute_overdue_count(ctx, report_date)
    report["total_financing_cents"] = recompute_financing_total(ctx)


def baseline(entity: str) -> dict[str, Any]:
    """Build a clean financing report for ``entity``."""
    milestones, prior = _schedule_rows()
    payload: dict[str, Any] = {
        "file_id": "clean",
        "entity": entity,
        "period": PERIOD,
        "report_date": REPORT_DATE,
        "documents": [
            {
                "doc_type": DOC_WORKSTREAM_REGISTER,
                "document_id": "WORKSTREAMS-2029-06",
                "workstreams": [
                    {
                        "workstream_id": wid,
                        "project": project,
                        "region": region,
                        "financing_type": ftype,
                        "status": status,
                        "target_closing": target,
                        "financial_partner": partner,
                        "financing_amount_cents": d(amount),
                    }
                    for wid, project, region, ftype, status, target, partner, amount in WORKSTREAMS
                ],
            },
            {
                "doc_type": DOC_MILESTONE_SCHEDULE,
                "document_id": "SCHEDULE-2029-06",
                "milestones": milestones,
            },
            {
                "doc_type": DOC_PRIOR_SCHEDULE,
                "document_id": "PRIOR-2029-05",
                "prior_milestones": prior,
            },
            {
                "doc_type": DOC_PLAYBOOK_CATALOG,
                "document_id": "PLAYBOOKS-2029",
                "playbooks": [
                    {"financing_type": ftype, "milestones": list(names)}
                    for ftype, names in PLAYBOOK_NAMES.items()
                ],
            },
            {
                "doc_type": DOC_MASTER_TRACKER,
                "document_id": "TRACKER-2029-06",
                "projects": [
                    {
                        "workstream_id": wid,
                        "project": project,
                        "financing_type": ftype,
                        "status": status,
                    }
                    for wid, project, _region, ftype, status, _target, _partner, _amount in WORKSTREAMS
                ],
            },
            {
                "doc_type": DOC_GANTT_SUMMARY,
                "document_id": "GANTT-2029-06",
                "bars": [
                    {
                        "workstream_id": wid,
                        "target_closing": target,
                        "gantt_month": 0,
                    }
                    for wid, _project, _region, _ftype, _status, target, _partner, _amount in WORKSTREAMS
                ],
            },
            {
                "doc_type": DOC_FINANCING_REPORT,
                "document_id": "REPORT-2029-06",
                "active_count": 0,
                "overdue_count": 0,
                "total_financing_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_FINANCING_REPORT
    ]


def _duplicate_workstream_id(payload: dict[str, Any]) -> None:
    # A second row carries an id already in use; marked CLOSED so it does not
    # disturb the active count, leaving only the uniqueness control to see it.
    register = _doc(payload, DOC_WORKSTREAM_REGISTER)
    assert register is not None
    clone = dict(_workstream(payload, "WS-01"))
    clone["status"] = STATUS_CLOSED
    register["workstreams"].append(clone)


def _bad_financing_type(payload: dict[str, Any]) -> None:
    _workstream(payload, "WS-04")["financing_type"] = "mezzanine"


def _bad_status(payload: dict[str, Any]) -> None:
    # A closed workstream carries an unknown status, so no active/overdue rollup
    # shifts and only the status-validity control sees it.
    _workstream(payload, "WS-05")["status"] = "WOUND_DOWN"


def _orphan_milestone(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_MILESTONE_SCHEDULE)
    prior = _doc(payload, DOC_PRIOR_SCHEDULE)
    assert schedule is not None and prior is not None
    current = REPORT + timedelta(days=90)
    prior_date = current - timedelta(days=25)
    original = current - timedelta(days=60)
    schedule["milestones"].append(
        {
            "milestone_id": "WS-999-M1",
            "workstream_id": "WS-999",
            "name": "Close",
            "sequence": 1,
            "original_date": original.isoformat(),
            "prior_date": prior_date.isoformat(),
            "current_date": current.isoformat(),
            "variance_days": 25,
            "overdue": False,
            "resp": "Deal Team A",
        }
    )
    prior["prior_milestones"].append(
        {
            "milestone_id": "WS-999-M1",
            "original_date": original.isoformat(),
            "current_date": prior_date.isoformat(),
        }
    )


def _playbook_undefined(payload: dict[str, Any]) -> None:
    # The debt playbook is gone; the debt workstreams still require it, so their
    # milestone set can no longer be enforced.
    catalog = _doc(payload, DOC_PLAYBOOK_CATALOG)
    assert catalog is not None
    catalog["playbooks"] = [
        p for p in catalog["playbooks"] if p.get("financing_type") != FINANCING_DEBT
    ]


def _missing_playbook_milestone(payload: dict[str, Any]) -> None:
    # An active debt workstream is missing one of its playbook milestones.
    schedule = _doc(payload, DOC_MILESTONE_SCHEDULE)
    assert schedule is not None
    schedule["milestones"] = [
        m for m in schedule["milestones"] if m.get("milestone_id") != "WS-01-M3"
    ]


def _missing_project(payload: dict[str, Any]) -> None:
    # The tracker lists an active project the report never covers.
    tracker = _doc(payload, DOC_MASTER_TRACKER)
    assert tracker is not None
    tracker["projects"].append(
        {
            "workstream_id": "WS-06",
            "project": "Saltaire Wharf",
            "financing_type": FINANCING_DEBT,
            "status": STATUS_ACTIVE,
        }
    )


def _untracked_workstream(payload: dict[str, Any]) -> None:
    # A closed workstream is reported that never appears on the master tracker.
    register = _doc(payload, DOC_WORKSTREAM_REGISTER)
    assert register is not None
    register["workstreams"].append(
        {
            "workstream_id": "WS-07",
            "project": "Fernbrook Landing",
            "region": "State of Marran",
            "financing_type": FINANCING_EQUITY,
            "status": STATUS_CLOSED,
            "target_closing": "2029-08-31",
            "financial_partner": "Kelder Equity Partners",
            "financing_amount_cents": d(12_000_000),
        }
    )


def _bad_milestone_date(payload: dict[str, Any]) -> None:
    _milestone(payload, "WS-02-M1")["current_date"] = "TBD"


def _variance_wrong(payload: dict[str, Any]) -> None:
    _milestone(payload, "WS-03-M2")["variance_days"] += 1


def _gantt_month_wrong(payload: dict[str, Any]) -> None:
    bar = _gantt_bar(payload, "WS-01")
    bar["gantt_month"] = (bar["gantt_month"] % 12) + 1


def _broken_rollforward(payload: dict[str, Any]) -> None:
    # Last month's Current no longer matches this month's Prior for one milestone.
    row = _prior_row(payload, "WS-04-M2")
    shifted = date.fromisoformat(row["current_date"]) + timedelta(days=5)
    row["current_date"] = shifted.isoformat()


def _mutated_baseline(payload: dict[str, Any]) -> None:
    # The frozen Original is overwritten this month.
    milestone = _milestone(payload, "WS-01-M1")
    shifted = date.fromisoformat(milestone["original_date"]) + timedelta(days=10)
    milestone["original_date"] = shifted.isoformat()


def _wrong_report_date(payload: dict[str, Any]) -> None:
    # A day before period-end; still before every current date, so no overdue
    # rollup shifts and only the period-end gate sees it.
    payload["report_date"] = "2029-06-29"


def _overdue_flag_wrong(payload: dict[str, Any]) -> None:
    # A not-yet-due milestone carries a stale overdue flag.
    _milestone(payload, "WS-02-M2")["overdue"] = True


def _duplicate_sequence(payload: dict[str, Any]) -> None:
    _milestone(payload, "WS-03-M3")["sequence"] = 2


def _out_of_order_milestone(payload: dict[str, Any]) -> None:
    # A later-sequence milestone is pulled back before its predecessor, while
    # staying in the future; the variance is re-derived so only ordering breaks.
    later = _milestone(payload, "WS-04-M4")
    earlier = _milestone(payload, "WS-04-M2")
    later["current_date"] = earlier["current_date"]
    rederive(payload)


def _active_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["active_count"] += 1


def _overdue_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["overdue_count"] += 1


def _financing_total_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["total_financing_cents"] += d(1_000_000)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    workstream = _workstream(payload, "WS-01")
    workstream["financing_amount_cents"] = float(workstream["financing_amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_workstream_id": ("mem_workstream_ids_unique", _duplicate_workstream_id),
    "bad_financing_type": ("mem_workstream_type_valid", _bad_financing_type),
    "bad_status": ("mem_workstream_status_valid", _bad_status),
    "orphan_milestone": ("mem_milestone_workstream_exists", _orphan_milestone),
    "playbook_undefined": ("mem_playbook_defined", _playbook_undefined),
    "missing_playbook_milestone": ("mem_playbook_complete", _missing_playbook_milestone),
    "missing_project": ("mem_portfolio_present", _missing_project),
    "untracked_workstream": ("mem_workstream_in_tracker", _untracked_workstream),
    "bad_milestone_date": ("var_dates_wellformed", _bad_milestone_date),
    "variance_wrong": ("var_recomputes", _variance_wrong),
    "gantt_month_wrong": ("var_gantt_month_recomputes", _gantt_month_wrong),
    "broken_rollforward": ("roll_prior_ties_current", _broken_rollforward),
    "mutated_baseline": ("base_original_immutable", _mutated_baseline),
    "wrong_report_date": ("date_report_is_period_end", _wrong_report_date),
    "overdue_flag_wrong": ("date_overdue_flag", _overdue_flag_wrong),
    "duplicate_sequence": ("ord_sequence_unique", _duplicate_sequence),
    "out_of_order_milestone": ("ord_current_nondecreasing", _out_of_order_milestone),
    "active_count_wrong": ("rpt_active_count_ties", _active_count_wrong),
    "overdue_count_wrong": ("rpt_overdue_count_ties", _overdue_count_wrong),
    "financing_total_wrong": ("rpt_financing_total_ties", _financing_total_wrong),
    "amount_not_integer": ("rpt_financing_total_ties", _amount_not_integer),
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
