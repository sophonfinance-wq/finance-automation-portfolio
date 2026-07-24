"""
Fictional entity good-standing compliance corpus generator.
===========================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The entity families, the entities, the fictional
jurisdictions, the registered agents, the SOS file numbers, the flat fees and the
filing dates are fictional, and the compliance period is set in a fictional
future. No real entity, person, agent, jurisdiction or path appears anywhere. The
generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the entities, the jurisdiction matrix and the state records are stated as
base facts (and even the records' statutory due dates are computed from the
matrix, so they cannot drift from the statute they claim to follow). Everything
the engine later checks as a rollup -- each entity's good-standing determination,
the renewal watchlist, the family in-good-standing / not counts -- is recomputed
by :func:`rederive` from those base facts, through the *same*
:mod:`standing_engine.standing` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .engine import (
    _matrix,
    _entities,
    _entity_id,
    _is_active,
    recompute_entity_good_standing,
    recompute_watchlist,
)
from .model import (
    DEFAULT_RENEWAL_LEAD_DAYS,
    DOC_COMPLIANCE_REPORT,
    DOC_ENTITY_REGISTER,
    DOC_JURISDICTION_MATRIX,
    DOC_RENEWAL_WATCHLIST,
    DOC_STANDING_RECORD_REGISTER,
    DOC_STANDING_SUMMARY,
    ENTITY_CORPORATION,
    ENTITY_LLC,
    ENTITY_LP,
    LICENSE_CURRENT,
    SOS_ACTIVE,
    SOS_DISSOLVED,
    STATE_KELDER,
    STATE_MARRAN,
    STATE_TOLVANE,
    STATE_VERRADO,
    STATUS_ACTIVE,
    STATUS_DISSOLVED,
    Context,
)

#: Fictional entity-family labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Westmere Holdings Group",
    "Brightwater Holdings",
    "Copperfield Holdings",
    "Alderpoint Holdings",
)

PERIOD = "FY2029"
#: The filing year every statutory due date is re-derived against.
PERIOD_YEAR = 2029
#: The review date every currency and renewal test is measured to.
AS_OF = "2029-09-15"
#: Lead-time window, in days, for the renewal watchlist.
RENEWAL_LEAD_DAYS = 30

#: Invented registered-agent providers. The contracted agent equals the agent of
#: record on every clean line; the alternate is only used to plant a mismatch.
AGENT_PRIMARY = "Paravance Agent Services"
AGENT_ALT = "Vantage Corporate Agents"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(state, entity_type, report_due_month, report_due_day, report_fee,
#:   franchise_tax, franchise_due_month, franchise_due_day, requires_agent,
#:   requires_license)``. Fees in dollars. Each fictional jurisdiction carries a
#: fixed statutory due date so a due date is a pure re-derivation. The records
#: below pay exactly these fees so a one-cent shortfall is the whole of a boundary
#: defect.
MATRIX: tuple[tuple[Any, ...], ...] = (
    (STATE_MARRAN, ENTITY_LLC, 3, 1, 50, 300, 6, 1, True, False),
    (STATE_KELDER, ENTITY_LLC, 4, 15, 70, 800, 4, 15, True, True),
    (STATE_MARRAN, ENTITY_CORPORATION, 3, 1, 60, 300, 6, 1, True, False),
    (STATE_TOLVANE, ENTITY_CORPORATION, 5, 15, 55, 500, 5, 15, True, False),
    (STATE_VERRADO, ENTITY_LP, 2, 1, 40, 250, 7, 1, True, False),
    (STATE_KELDER, ENTITY_LP, 4, 15, 70, 800, 4, 15, True, True),
)

#: ``(entity_id, name, entity_type, formation_state, qualified_states, status,
#:   ein, formation_date, dissolved_date)``. Invented entity names; each is
#: registered in its formation state plus its qualified state(s). ENT-104 is
#: wound down and must be cancelled everywhere it belonged.
ENTITIES: tuple[tuple[Any, ...], ...] = (
    ("ENT-101", "Northmoor Development Group LLC", ENTITY_LLC, STATE_MARRAN, (STATE_KELDER,), STATUS_ACTIVE, "88-1000101", "2024-02-10", None),
    ("ENT-102", "Halbrook Residential Corporation", ENTITY_CORPORATION, STATE_MARRAN, (STATE_TOLVANE,), STATUS_ACTIVE, "88-1000102", "2023-08-22", None),
    ("ENT-103", "Stonecrest Communities LP", ENTITY_LP, STATE_VERRADO, (STATE_KELDER,), STATUS_ACTIVE, "88-1000103", "2022-11-05", None),
    ("ENT-104", "Ardenne Field Partners LLC", ENTITY_LLC, STATE_MARRAN, (STATE_KELDER,), STATUS_DISSOLVED, "88-1000104", "2019-06-01", "2028-12-31"),
)


def _matrix_lookup() -> dict[tuple[str, str], dict[str, Any]]:
    """``(state, entity_type) -> statutory-parameter dict``."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for (
        state, etype, rm, rd, fee, tax, fm, fd, agent, lic,
    ) in MATRIX:
        out[(state, etype)] = {
            "report_due_month": rm,
            "report_due_day": rd,
            "report_fee": fee,
            "franchise_tax": tax,
            "franchise_due_month": fm,
            "franchise_due_day": fd,
            "requires_registered_agent": agent,
            "requires_business_license": lic,
        }
    return out


def _entity_required_states(entity: tuple[Any, ...]) -> list[str]:
    """Formation state UNION qualified states, order-stable, from an ENTITIES row."""
    _eid, _name, _etype, formation, qualified, *_rest = entity
    out: list[str] = [formation]
    for state in qualified:
        if state not in out:
            out.append(state)
    return out


def _build_records() -> list[dict[str, Any]]:
    """Build one state record per (entity, required-state), dates from the matrix."""
    params = _matrix_lookup()
    records: list[dict[str, Any]] = []
    seq = 1001
    for entity in ENTITIES:
        eid, _name, etype, _formation, _qualified, status, *_rest = entity
        active = status == STATUS_ACTIVE
        for state in _entity_required_states(entity):
            mp = params[(state, etype)]
            report_due = date(PERIOD_YEAR, mp["report_due_month"], mp["report_due_day"])
            report_filed = report_due - timedelta(days=15)
            franchise_due = date(PERIOD_YEAR, mp["franchise_due_month"], mp["franchise_due_day"])
            franchise_paid = franchise_due - timedelta(days=10)
            next_report_due = date(PERIOD_YEAR + 1, mp["report_due_month"], mp["report_due_day"])
            records.append(
                {
                    "record_id": f"GS-{seq}",
                    "entity_id": eid,
                    "state": state,
                    "sos_file_number": f"SOS-{PERIOD_YEAR}-{seq}",
                    "sos_status": SOS_ACTIVE if active else SOS_DISSOLVED,
                    "report_due_date": report_due.isoformat(),
                    "report_filed_date": report_filed.isoformat(),
                    "report_fee_paid_cents": d(mp["report_fee"]),
                    "franchise_tax_due_date": franchise_due.isoformat(),
                    "franchise_tax_paid_date": franchise_paid.isoformat(),
                    "franchise_tax_paid_cents": d(mp["franchise_tax"]),
                    "sos_agent_name": AGENT_PRIMARY,
                    "contracted_agent_name": AGENT_PRIMARY,
                    "agent_fee_paid_date": "2029-01-15",
                    "license_status": LICENSE_CURRENT,
                    "license_due_date": "2030-06-01",
                    "next_report_due_date": next_report_due.isoformat(),
                    "cancellation_filed": not active,
                }
            )
            seq += 1
    return records


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _entity(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_ENTITY_REGISTER)
    assert register is not None
    for row in register["entities"]:
        if row.get("entity_id") == entity_id:
            return row
    raise KeyError(entity_id)


def _record(payload: dict[str, Any], record_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_STANDING_RECORD_REGISTER)
    assert register is not None
    for row in register["records"]:
        if row.get("record_id") == record_id:
            return row
    raise KeyError(record_id)


def _matrix_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    register = _doc(payload, DOC_JURISDICTION_MATRIX)
    assert register is not None
    return register["requirements"]


def _summary_row(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_STANDING_SUMMARY)
    assert summary is not None
    for row in summary["entities"]:
        if row.get("entity_id") == entity_id:
            return row
    raise KeyError(entity_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_COMPLIANCE_REPORT)
    assert report is not None
    return report


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_RENEWAL_WATCHLIST)
    assert watchlist is not None
    return watchlist


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup figure from the payload's own base facts."""
    ent_doc = _doc(payload, DOC_ENTITY_REGISTER)
    matrix_doc = _doc(payload, DOC_JURISDICTION_MATRIX)
    rec_doc = _doc(payload, DOC_STANDING_RECORD_REGISTER)
    summary = _doc(payload, DOC_STANDING_SUMMARY)
    watchlist = _doc(payload, DOC_RENEWAL_WATCHLIST)
    report = _doc(payload, DOC_COMPLIANCE_REPORT)
    if not all((ent_doc, matrix_doc, rec_doc, summary, watchlist, report)):
        return
    assert summary is not None and watchlist is not None and report is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    lead = payload.get("renewal_lead_days", DEFAULT_RENEWAL_LEAD_DAYS)
    matrix = _matrix(ctx)

    # Standing summary: one good-standing determination per active entity,
    # recomputed through the shared kernel the engine recomputes with.
    summary["entities"] = [
        {
            "entity_id": _entity_id(entity),
            "good_standing": recompute_entity_good_standing(ctx, entity, matrix, as_of),
        }
        for entity in _entities(ctx)
        if _is_active(entity)
    ]

    # Renewal watchlist: active-entity records whose next report is due inside the
    # lead-time window.
    watchlist["entries"] = recompute_watchlist(ctx, as_of, lead)

    # Compliance report: the family counts, derived from the summary flags.
    good = sum(1 for row in summary["entities"] if row["good_standing"])
    total = len(summary["entities"])
    report["good_standing_count"] = good
    report["not_in_good_standing_count"] = total - good


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean standing file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "period_year": PERIOD_YEAR,
        "as_of": AS_OF,
        "renewal_lead_days": RENEWAL_LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_ENTITY_REGISTER,
                "document_id": "ENTITIES-2029",
                "entities": [
                    {
                        "entity_id": entity_id,
                        "name": name,
                        "entity_type": entity_type,
                        "formation_state": formation_state,
                        "qualified_states": list(qualified_states),
                        "status": status,
                        "ein": ein,
                        "formation_date": formation_date,
                        "dissolved_date": dissolved_date,
                    }
                    for (
                        entity_id, name, entity_type, formation_state, qualified_states,
                        status, ein, formation_date, dissolved_date,
                    ) in ENTITIES
                ],
            },
            {
                "doc_type": DOC_JURISDICTION_MATRIX,
                "document_id": "MATRIX-2029",
                "requirements": [
                    {
                        "state": state,
                        "entity_type": entity_type,
                        "report_due_month": rm,
                        "report_due_day": rd,
                        "report_fee_cents": d(fee),
                        "franchise_tax_cents": d(tax),
                        "franchise_due_month": fm,
                        "franchise_due_day": fd,
                        "requires_registered_agent": agent,
                        "requires_business_license": lic,
                    }
                    for (
                        state, entity_type, rm, rd, fee, tax, fm, fd, agent, lic,
                    ) in MATRIX
                ],
            },
            {
                "doc_type": DOC_STANDING_RECORD_REGISTER,
                "document_id": "RECORDS-2029",
                "records": _build_records(),
            },
            {
                "doc_type": DOC_STANDING_SUMMARY,
                "document_id": "SUMMARY-2029",
                "entities": [],
            },
            {
                "doc_type": DOC_RENEWAL_WATCHLIST,
                "document_id": "WATCHLIST-2029",
                "entries": [],
            },
            {
                "doc_type": DOC_COMPLIANCE_REPORT,
                "document_id": "REPORT-2029",
                "good_standing_count": 0,
                "not_in_good_standing_count": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_COMPLIANCE_REPORT
    ]


def _duplicate_entity_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_ENTITY_REGISTER)
    assert register is not None
    register["entities"].append(dict(_entity(payload, "ENT-101")))


def _bad_entity_type(payload: dict[str, Any]) -> None:
    _entity(payload, "ENT-102")["entity_type"] = "trust"


def _bad_entity_status(payload: dict[str, Any]) -> None:
    _entity(payload, "ENT-103")["status"] = "pending"


def _undeclared_jurisdiction(payload: dict[str, Any]) -> None:
    # The entity's registrations were never captured: no formation, no qualified
    # states, and its records removed so only the declaration control sees it.
    entity = _entity(payload, "ENT-102")
    entity["formation_state"] = ""
    entity["qualified_states"] = []
    register = _doc(payload, DOC_STANDING_RECORD_REGISTER)
    assert register is not None
    register["records"] = [
        r for r in register["records"] if r.get("entity_id") != "ENT-102"
    ]


def _matrix_row_missing(payload: dict[str, Any]) -> None:
    # The Tolvane corporation obligation is gone; ENT-102 still qualifies there, so
    # its franchise tax can no longer be tested.
    register = _doc(payload, DOC_JURISDICTION_MATRIX)
    assert register is not None
    register["requirements"] = [
        r
        for r in _matrix_rows(payload)
        if not (r["state"] == STATE_TOLVANE and r["entity_type"] == ENTITY_CORPORATION)
    ]


def _record_present_missing(payload: dict[str, Any]) -> None:
    # ENT-102's Tolvane record is off the register entirely.
    register = _doc(payload, DOC_STANDING_RECORD_REGISTER)
    assert register is not None
    register["records"] = [
        r for r in register["records"] if r.get("record_id") != "GS-1004"
    ]


def _record_missing_field(payload: dict[str, Any]) -> None:
    del _record(payload, "GS-1005")["sos_file_number"]


def _duplicate_file_number(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1002")["sos_file_number"] = _record(payload, "GS-1001")["sos_file_number"]


def _unknown_entity_record(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_STANDING_RECORD_REGISTER)
    assert register is not None
    stray = dict(_record(payload, "GS-1001"))
    stray.update(
        {
            "record_id": "GS-2002",
            "entity_id": "ENT-999",
            "sos_file_number": "SOS-2029-2002",
        }
    )
    register["records"].append(stray)


def _stray_state_record(payload: dict[str, Any]) -> None:
    # A record registering ENT-101 in Tolvane, a state it never qualified into.
    register = _doc(payload, DOC_STANDING_RECORD_REGISTER)
    assert register is not None
    stray = dict(_record(payload, "GS-1001"))
    stray.update(
        {
            "record_id": "GS-2001",
            "state": STATE_TOLVANE,
            "sos_file_number": "SOS-2029-2001",
        }
    )
    register["records"].append(stray)


def _report_due_date_wrong(payload: dict[str, Any]) -> None:
    # A due date that does not re-derive from the statute, but still after the
    # filing date so the timeliness gate is untouched.
    _record(payload, "GS-1001")["report_due_date"] = "2029-03-08"


def _report_filed_late(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1001")["report_filed_date"] = "2029-03-02"


def _report_fee_short(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1001")["report_fee_paid_cents"] -= d(5)


def _franchise_tax_short(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1001")["franchise_tax_paid_cents"] -= d(50)


def _franchise_due_date_wrong(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1001")["franchise_tax_due_date"] = "2029-06-10"


def _franchise_paid_late(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1001")["franchise_tax_paid_date"] = "2029-06-02"


def _agent_mismatch(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1001")["sos_agent_name"] = AGENT_ALT


def _agent_fee_unpaid(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1001")["agent_fee_paid_date"] = ""


def _sos_suspended(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1002")["sos_status"] = "SUSPENDED"


def _license_lapsed(payload: dict[str, Any]) -> None:
    _record(payload, "GS-1002")["license_status"] = "lapsed"


def _incomplete_dissolution(payload: dict[str, Any]) -> None:
    # The wound-down entity was cancelled in Kelder but not in its formation state.
    _record(payload, "GS-1007")["cancellation_filed"] = False


def _standing_flag_wrong(payload: dict[str, Any]) -> None:
    # The stated determination contradicts the records; the count is moved with it
    # so only the recompute control sees the break.
    _summary_row(payload, "ENT-101")["good_standing"] = False
    report = _report(payload)
    report["good_standing_count"] = 2
    report["not_in_good_standing_count"] = 1


def _report_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["good_standing_count"] += 1


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {
            "entity_id": "ENT-101",
            "state": STATE_MARRAN,
            "next_report_due_date": "2030-03-01",
            "days_remaining": 167,
        }
    )


def _renewal_due_soon(payload: dict[str, Any]) -> None:
    # The next report is still far off in fact, but this record's next due date is
    # inside the lead window; the rollup is re-derived so only the renewal FLAG
    # remains.
    _record(payload, "GS-1001")["next_report_due_date"] = "2029-10-05"
    rederive(payload)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    rec = _record(payload, "GS-1001")
    rec["franchise_tax_paid_cents"] = float(rec["franchise_tax_paid_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_entity_id": ("ent_unique_ids", _duplicate_entity_id),
    "bad_entity_type": ("ent_type_valid", _bad_entity_type),
    "bad_entity_status": ("ent_status_valid", _bad_entity_status),
    "undeclared_jurisdiction": ("ent_jurisdictions_declared", _undeclared_jurisdiction),
    "matrix_row_missing": ("jur_matrix_defined", _matrix_row_missing),
    "record_present_missing": ("jur_record_present", _record_present_missing),
    "record_missing_field": ("rec_required_fields", _record_missing_field),
    "duplicate_file_number": ("rec_file_number_unique", _duplicate_file_number),
    "unknown_entity_record": ("rec_entity_exists", _unknown_entity_record),
    "stray_state_record": ("rec_state_required", _stray_state_record),
    "report_due_date_wrong": ("fil_due_date_recomputes", _report_due_date_wrong),
    "report_filed_late": ("fil_report_filed_on_time", _report_filed_late),
    "report_fee_short": ("fil_report_fee_paid", _report_fee_short),
    "franchise_tax_short": ("tax_amount_meets", _franchise_tax_short),
    "franchise_due_date_wrong": ("tax_due_date_recomputes", _franchise_due_date_wrong),
    "franchise_paid_late": ("tax_paid_on_time", _franchise_paid_late),
    "agent_mismatch": ("agt_matches_sos", _agent_mismatch),
    "agent_fee_unpaid": ("agt_fee_current", _agent_fee_unpaid),
    "sos_suspended": ("sts_sos_active", _sos_suspended),
    "license_lapsed": ("lic_current", _license_lapsed),
    "incomplete_dissolution": ("dis_cancellation_complete", _incomplete_dissolution),
    "standing_flag_wrong": ("roll_standing_recomputes", _standing_flag_wrong),
    "report_count_wrong": ("roll_report_counts_tie", _report_count_wrong),
    "watchlist_overstated": ("roll_watchlist_ties", _watchlist_overstated),
    "renewal_due_soon": ("fil_renewal_lead_time", _renewal_due_soon),
    "amount_not_integer": ("tax_amount_meets", _amount_not_integer),
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
