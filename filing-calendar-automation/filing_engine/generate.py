"""
Fictional filing-obligation calendar corpus generator.
=====================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The filing groups, the entities, the jurisdictions,
the form codes, the EINs, the dates and the amounts are fictional, and the fiscal
year is set in a fictional future. No real entity, person, agency, jurisdiction
or path appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the roster, the statutory due-dates table, the obligation base facts
(form, year-end, extension flag, filed dates, amounts, receipts) and the evidence
are stated. Everything the engine later checks as a rollup -- each obligation's
original/extended due date, its status, the portfolio overdue/filed counts, the
due-soon watchlist -- is recomputed by :func:`rederive` from those base facts,
through the *same* :mod:`filing_engine.duedates` kernel the engine recomputes
with. So the relationships the engine tests are the relationships that produced
the data: a defect that changes a base fact re-derives the rollup and keeps the
break confined to one control; a defect that targets a stated rollup edits that
figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    _due_rules,
    _is_na,
    _obligation_id,
    _obligations,
    derive_obligation_dates,
    recompute_filed_count,
    recompute_overdue_count,
    recompute_status,
    recompute_watchlist,
)
from .model import (
    DEFAULT_DUE_LEAD_DAYS,
    DOC_DUE_DATES_TABLE,
    DOC_DUE_WATCHLIST,
    DOC_ENTITY_ROSTER,
    DOC_EVIDENCE_INDEX,
    DOC_OBLIGATION_REGISTER,
    DOC_PRIOR_YEAR_REGISTER,
    DOC_STATUS_SUMMARY,
    EVIDENCE_EXTENSION,
    EVIDENCE_PAYMENT,
    EVIDENCE_RETURN,
    Context,
)

#: Fictional filing-group labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

PERIOD = "FYE 2028"
#: The review date every due-date and overdue test is measured to.
AS_OF = "2028-12-01"
#: Lead-time window, in days, for the due-date watchlist.
DUE_LEAD_DAYS = 30
#: The single fiscal year-end all obligations share in the corpus.
YEAR_END = "2028-06-30"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


# --------------------------------------------------------------------------- #
# Base facts
# --------------------------------------------------------------------------- #
#: ``(form, year_end_md, original_month, original_day, extension_offset_months,
#:   fixed_amount_dollars)``. Invented form codes; the offsets are the statutory
#: rule each obligation's due dates re-derive from. A zero offset means the form
#: carries no extension; a fixed amount means the voucher prints a statutory
#: constant.
DUE_RULES: tuple[tuple[Any, ...], ...] = (
    ("FED-1065", "06-30", 9, 15, 6, None),
    ("FED-1120", "06-30", 9, 15, 7, None),
    ("MAR-568", "06-30", 9, 15, 6, None),
    ("MAR-3522", "06-30", 10, 15, 0, 800),
    ("MAR-3536", "06-30", 12, 15, 0, None),
    ("VEL-FR", "06-30", 11, 15, 6, None),
)

#: ``(entity_id, name, ein, active)``. Invented entities and EINs.
ENTITIES: tuple[tuple[Any, ...], ...] = (
    ("ENT-101", "Northmoor Development Group", "EIN-44-0000101", True),
    ("ENT-102", "Halbrook Residential Partners", "EIN-44-0000102", True),
    ("ENT-103", "Stonecrest Communities", "EIN-44-0000103", True),
    ("ENT-104", "Ardenne Field Partners", "EIN-44-0000104", True),
    ("ENT-105", "Brightwater Holdings", "EIN-44-0000105", True),
)

#: ``(obligation_id, entity_id, jurisdiction, form, extension_filed, return_filed,
#:   amount_dollars, receipt_no, na)``. year-end is shared (:data:`YEAR_END`).
#: Every baseline obligation is either filed on time, extended and still open, or
#: not applicable -- so the clean file rolls up to PASS with no flags.
OBLIGATIONS: tuple[tuple[Any, ...], ...] = (
    ("OB-1001", "ENT-101", "Federal", "FED-1065", True, None, None, None, False),
    ("OB-1002", "ENT-101", "State of Marran", "MAR-568", True, None, None, None, False),
    ("OB-1003", "ENT-101", "State of Marran", "MAR-3522", False, "2028-10-10", 800, "RC-3001", False),
    ("OB-1004", "ENT-102", "Federal", "FED-1065", False, "2028-09-10", None, None, False),
    ("OB-1005", "ENT-102", "State of Marran", "MAR-3522", False, "2028-10-12", 800, "RC-3002", False),
    ("OB-1006", "ENT-103", "Federal", "FED-1120", True, None, None, None, False),
    ("OB-1007", "ENT-103", "State of Veldt", "VEL-FR", True, None, None, None, False),
    ("OB-1008", "ENT-104", "Federal", "FED-1065", False, "2028-09-14", None, None, False),
    ("OB-1009", "ENT-104", "State of Veldt", "VEL-FR", False, None, None, None, True),
    ("OB-1010", "ENT-105", "State of Marran", "MAR-3522", False, "2028-10-15", 800, "RC-3003", False),
    ("OB-1011", "ENT-105", "State of Marran", "MAR-568", True, None, None, None, False),
    ("OB-1012", "ENT-102", "State of Marran", "MAR-3536", False, "2028-11-20", None, None, False),
)

#: Shared internal-workflow schedule for every live obligation, well before any
#: deadline and in order (prep <= review <= sent).
WORKFLOW = {
    "prep_goal": "2028-08-01",
    "review_goal": "2028-08-15",
    "sent_goal": "2028-09-01",
    "prep_actual": "2028-07-28",
    "review_actual": "2028-08-14",
    "sent_actual": "2028-08-30",
}

#: Entities marked FINAL in the prior fiscal year. ENT-900 dissolved last year and
#: carries no obligation this year, so the continuity control has something to
#: check and holds.
PRIOR_FINAL: tuple[str, ...] = ("ENT-900",)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _obligation(payload: dict[str, Any], obligation_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_OBLIGATION_REGISTER)
    assert register is not None
    for row in register["obligations"]:
        if row.get("obligation_id") == obligation_id:
            return row
    raise KeyError(obligation_id)


def _summary_row(payload: dict[str, Any], obligation_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_STATUS_SUMMARY)
    assert summary is not None
    for row in summary["obligations"]:
        if row.get("obligation_id") == obligation_id:
            return row
    raise KeyError(obligation_id)


def _evidence_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = _doc(payload, DOC_EVIDENCE_INDEX)
    assert evidence is not None
    return evidence["evidence"]


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _doc(payload, DOC_STATUS_SUMMARY)
    assert summary is not None
    return summary


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_DUE_WATCHLIST)
    assert watchlist is not None
    return watchlist


# --------------------------------------------------------------------------- #
# Evidence construction (a base fact, derived deterministically from obligations)
# --------------------------------------------------------------------------- #
def _build_evidence() -> list[dict[str, Any]]:
    """One evidence row per obligation that filed, paid or extended."""
    rows: list[dict[str, Any]] = []
    n = 0
    for (
        obligation_id, _entity, _jur, _form, extension_filed, return_filed,
        amount_dollars, _receipt, na,
    ) in OBLIGATIONS:
        if na:
            continue
        n += 1
        if extension_filed:
            kind, ref = EVIDENCE_EXTENSION, f"EXT-{obligation_id[3:]}"
        elif return_filed is not None:
            if amount_dollars is not None:
                kind, ref = EVIDENCE_PAYMENT, f"PAY-{obligation_id[3:]}"
            else:
                kind, ref = EVIDENCE_RETURN, f"RET-{obligation_id[3:]}"
        else:
            continue
        rows.append(
            {
                "evidence_id": f"EV-{n:02d}",
                "obligation_id": obligation_id,
                "kind": kind,
                "reference": ref,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    roster = _doc(payload, DOC_ENTITY_ROSTER)
    table = _doc(payload, DOC_DUE_DATES_TABLE)
    register = _doc(payload, DOC_OBLIGATION_REGISTER)
    evidence = _doc(payload, DOC_EVIDENCE_INDEX)
    prior = _doc(payload, DOC_PRIOR_YEAR_REGISTER)
    summary = _doc(payload, DOC_STATUS_SUMMARY)
    watchlist = _doc(payload, DOC_DUE_WATCHLIST)
    if not all((roster, table, register, evidence, prior, summary, watchlist)):
        return
    assert summary is not None and watchlist is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    lead = payload.get("due_lead_days", DEFAULT_DUE_LEAD_DAYS)
    rules = _due_rules(ctx)

    # Register due dates: re-derived from the statutory table. The extended date
    # is stored only when an extension was filed, so the flag and the date agree.
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            obligation["original_due"] = None
            obligation["extended_due"] = None
            continue
        original_due, extended_due = derive_obligation_dates(obligation, rules)
        obligation["original_due"] = original_due.isoformat() if original_due else None
        obligation["extended_due"] = (
            extended_due.isoformat()
            if (extended_due is not None and bool(obligation.get("extension_filed")))
            else None
        )

    # Status summary: one recomputed status per obligation, plus the counts.
    summary["obligations"] = [
        {"obligation_id": _obligation_id(o), "status": recompute_status(ctx, o, as_of)}
        for o in _obligations(ctx)
    ]
    summary["overdue_count"] = recompute_overdue_count(ctx, as_of)
    summary["filed_count"] = recompute_filed_count(ctx, as_of)

    # Due-soon watchlist: unfiled obligations falling due inside the window.
    watchlist["entries"] = recompute_watchlist(ctx, as_of, lead)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean calendar file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "due_lead_days": DUE_LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_ENTITY_ROSTER,
                "document_id": "ROSTER-2028",
                "entities": [
                    {"entity_id": eid, "name": name, "ein": ein, "active": active}
                    for eid, name, ein, active in ENTITIES
                ],
            },
            {
                "doc_type": DOC_DUE_DATES_TABLE,
                "document_id": "DUEDATES-2028",
                "rules": [
                    {
                        "form": form,
                        "year_end": year_end,
                        "original_month": original_month,
                        "original_day": original_day,
                        "extension_offset_months": offset,
                        "fixed_amount_cents": (d(fixed) if fixed is not None else None),
                    }
                    for form, year_end, original_month, original_day, offset, fixed in DUE_RULES
                ],
            },
            {
                "doc_type": DOC_OBLIGATION_REGISTER,
                "document_id": "REGISTER-2028",
                "obligations": [
                    {
                        "obligation_id": obligation_id,
                        "entity_id": entity_id,
                        "jurisdiction": jurisdiction,
                        "form": form,
                        "year_end": YEAR_END,
                        "extension_filed": extension_filed,
                        "original_due": None,
                        "extended_due": None,
                        "return_filed": return_filed,
                        "amount_required_cents": (
                            d(amount_dollars) if amount_dollars is not None else None
                        ),
                        "certified_receipt_no": receipt,
                        "na": na,
                        **({} if na else dict(WORKFLOW)),
                    }
                    for (
                        obligation_id, entity_id, jurisdiction, form, extension_filed,
                        return_filed, amount_dollars, receipt, na,
                    ) in OBLIGATIONS
                ],
            },
            {
                "doc_type": DOC_EVIDENCE_INDEX,
                "document_id": "EVIDENCE-2028",
                "evidence": _build_evidence(),
            },
            {
                "doc_type": DOC_PRIOR_YEAR_REGISTER,
                "document_id": "PRIOR-2027",
                "final_entities": list(PRIOR_FINAL),
            },
            {
                "doc_type": DOC_STATUS_SUMMARY,
                "document_id": "SUMMARY-2028",
                "obligations": [],
                "overdue_count": 0,
                "filed_count": 0,
            },
            {
                "doc_type": DOC_DUE_WATCHLIST,
                "document_id": "WATCHLIST-2028",
                "entries": [],
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_STATUS_SUMMARY
    ]


def _bad_year_end(payload: dict[str, Any]) -> None:
    # An impossible calendar date; the statutory table cannot be keyed to it.
    _obligation(payload, "OB-1004")["year_end"] = "2028-13-40"


def _form_not_in_table(payload: dict[str, Any]) -> None:
    # The form is not in the due-dates table, so no deadline can be re-derived.
    _obligation(payload, "OB-1006")["form"] = "ZZZ-999"


def _wrong_original_due(payload: dict[str, Any]) -> None:
    # The stored original due date is a day off the re-derived statutory one.
    _obligation(payload, "OB-1004")["original_due"] = "2028-09-16"


def _wrong_extended_due(payload: dict[str, Any]) -> None:
    # The stored extended due date is applied to the wrong window (a month late).
    _obligation(payload, "OB-1001")["extended_due"] = "2029-04-15"


def _extension_date_without_flag(payload: dict[str, Any]) -> None:
    # An extended date sits on a row that never filed an extension; the date is
    # the correct one, so only the flag-agreement control sees the contradiction.
    _obligation(payload, "OB-1004")["extended_due"] = "2029-03-15"


def _unfiled_overdue(payload: dict[str, Any]) -> None:
    # A filing that never happened; its original deadline has already passed.
    _obligation(payload, "OB-1004")["return_filed"] = None
    rederive(payload)


def _filed_after_due(payload: dict[str, Any]) -> None:
    # The return was lodged after its applicable deadline; the register only
    # recorded that it was filed.
    _obligation(payload, "OB-1004")["return_filed"] = "2028-10-01"
    rederive(payload)


def _obligation_due_soon(payload: dict[str, Any]) -> None:
    # An unfiled obligation whose deadline is inside the lead-time window; the
    # rollup is re-derived so only the due-soon FLAG remains.
    _obligation(payload, "OB-1012")["return_filed"] = None
    rederive(payload)


def _wrong_fixed_amount(payload: dict[str, Any]) -> None:
    # The annual fixed tax is a dollar short of the statutory constant.
    _obligation(payload, "OB-1003")["amount_required_cents"] -= d(1)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    obligation = _obligation(payload, "OB-1003")
    obligation["amount_required_cents"] = float(obligation["amount_required_cents"]) + 0.5


def _missing_filed_evidence(payload: dict[str, Any]) -> None:
    # OB-1003 is marked paid, but its voucher is gone from the archive.
    evidence = _doc(payload, DOC_EVIDENCE_INDEX)
    assert evidence is not None
    evidence["evidence"] = [
        e for e in evidence["evidence"] if e.get("obligation_id") != "OB-1003"
    ]


def _missing_extension_evidence(payload: dict[str, Any]) -> None:
    # OB-1002 filed an extension, but no acceptance is on file.
    evidence = _doc(payload, DOC_EVIDENCE_INDEX)
    assert evidence is not None
    evidence["evidence"] = [
        e for e in evidence["evidence"] if e.get("obligation_id") != "OB-1002"
    ]


def _orphan_evidence(payload: dict[str, Any]) -> None:
    # A voucher for an obligation that is not in the register.
    _evidence_rows(payload).append(
        {
            "evidence_id": "EV-99",
            "obligation_id": "OB-9999",
            "kind": EVIDENCE_RETURN,
            "reference": "RET-9999",
        }
    )


def _entity_missing_obligation(payload: dict[str, Any]) -> None:
    # An active entity whose filings nobody is tracking.
    roster = _doc(payload, DOC_ENTITY_ROSTER)
    assert roster is not None
    roster["entities"].append(
        {"entity_id": "ENT-106", "name": "Copperfield Capital", "ein": "EIN-44-0000106", "active": True}
    )


def _unknown_entity(payload: dict[str, Any]) -> None:
    # An obligation naming an entity not in the roster; marked n/a so only the
    # attribution control sees it.
    register = _doc(payload, DOC_OBLIGATION_REGISTER)
    assert register is not None
    register["obligations"].append(
        {
            "obligation_id": "OB-2001",
            "entity_id": "ENT-777",
            "jurisdiction": "State of Marran",
            "form": "MAR-3522",
            "year_end": YEAR_END,
            "extension_filed": False,
            "original_due": None,
            "extended_due": None,
            "return_filed": None,
            "amount_required_cents": None,
            "certified_receipt_no": None,
            "na": True,
        }
    )


def _duplicate_obligation_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_OBLIGATION_REGISTER)
    assert register is not None
    register["obligations"].append(dict(_obligation(payload, "OB-1009")))


def _goal_out_of_order(payload: dict[str, Any]) -> None:
    # Prep is scheduled after review; the internal schedule runs backwards while
    # every actual still meets its own goal, so only the ordering control fires.
    _obligation(payload, "OB-1001")["prep_goal"] = "2028-08-20"


def _workflow_slippage(payload: dict[str, Any]) -> None:
    # The review step completed after its goal; the goals are still in order.
    _obligation(payload, "OB-1002")["review_actual"] = "2028-09-05"


def _final_entity_recurring(payload: dict[str, Any]) -> None:
    prior = _doc(payload, DOC_PRIOR_YEAR_REGISTER)
    assert prior is not None
    prior["final_entities"].append("ENT-101")


def _status_wrong(payload: dict[str, Any]) -> None:
    # The stated status contradicts the register; the counts are left tying the
    # register, so only the recompute control sees the break.
    _summary_row(payload, "OB-1001")["status"] = "filed"


def _count_wrong(payload: dict[str, Any]) -> None:
    _summary(payload)["overdue_count"] += 1


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {
            "obligation_id": "OB-1001",
            "entity_id": "ENT-101",
            "form": "FED-1065",
            "applicable_due": "2029-03-15",
            "days_remaining": 469,
        }
    )


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "bad_year_end": ("due_year_end_valid", _bad_year_end),
    "form_not_in_table": ("due_table_defined", _form_not_in_table),
    "wrong_original_due": ("due_original_matches", _wrong_original_due),
    "wrong_extended_due": ("due_extended_matches", _wrong_extended_due),
    "extension_date_without_flag": ("ext_flag_valid", _extension_date_without_flag),
    "unfiled_overdue": ("ext_applicable_overdue", _unfiled_overdue),
    "filed_after_due": ("ext_filed_on_time", _filed_after_due),
    "obligation_due_soon": ("ext_due_soon", _obligation_due_soon),
    "wrong_fixed_amount": ("pay_fixed_amount", _wrong_fixed_amount),
    "amount_not_integer": ("pay_fixed_amount", _amount_not_integer),
    "missing_filed_evidence": ("evd_filed_has_evidence", _missing_filed_evidence),
    "missing_extension_evidence": ("evd_extension_evidence", _missing_extension_evidence),
    "orphan_evidence": ("evd_no_orphan_evidence", _orphan_evidence),
    "entity_missing_obligation": ("ros_entity_has_row", _entity_missing_obligation),
    "unknown_entity": ("ros_row_entity_known", _unknown_entity),
    "duplicate_obligation_id": ("ros_unique_obligation_ids", _duplicate_obligation_id),
    "goal_out_of_order": ("wfl_goal_monotonic", _goal_out_of_order),
    "workflow_slippage": ("wfl_actual_slippage", _workflow_slippage),
    "final_entity_recurring": ("cnt_final_not_recurring", _final_entity_recurring),
    "status_wrong": ("rpt_status_recomputes", _status_wrong),
    "count_wrong": ("rpt_counts_tie", _count_wrong),
    "watchlist_overstated": ("rpt_watchlist_ties", _watchlist_overstated),
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
