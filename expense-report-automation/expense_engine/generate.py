"""
Fictional expense & P-Card corpus generator.
=============================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The companies, the cardholders, the merchants, the
card numbers, the projects and every amount are fictional, and the statement
cycle is set in a fictional future. No real entity, person, merchant, project or
path appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the cardholders, the policy, the projects and the charges are stated as base
facts. Every figure the engine later checks as a tie-out -- each report line's
amount, the general-ledger P-Card total -- is recomputed by :func:`rederive` from
those base facts, so the relationships the engine tests are the relationships that
produced the data: the report line mirrors its statement charge, and the ledger
mirrors the reports.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import (
    DOC_CARDHOLDER_REGISTER,
    DOC_EXPENSE_REPORT_REGISTER,
    DOC_GL_POSITIONS,
    DOC_POLICY,
    DOC_PROJECT_REGISTER,
    DOC_STATEMENT_REGISTER,
)

#: Fictional company labels, rotated for file identity only.
PROGRAMMES: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

CYCLE = "2029-09"
#: The bank statement close date for the cycle.
STATEMENT_DATE = "2029-09-30"
#: When the compliant reports were filed (10 days later, inside a 14-day window).
SUBMITTED_DATE = "2029-10-10"
#: The review date the cycle is measured to.
AS_OF = "2029-10-31"

#: Programme policy, stated once.
POLICY: dict[str, Any] = {
    "submission_window_days": 14,
    "per_charge_limit_cents": 5_000_00,
    "disallowed_categories": ["cash_advance", "gambling", "alcohol", "gift_card"],
    "valid_gl_codes": ["6010", "6020", "6030", "6040"],
}

#: ``(code, name, budget_cents)``.
PROJECTS: tuple[tuple[str, str, int], ...] = (
    ("PRJ-101", "Brightwater Commons", 4_800_000_00),
    ("PRJ-102", "Copperfield Yards", 3_600_000_00),
    ("PRJ-103", "Alderpoint Terraces", 2_400_000_00),
    ("PRJ-104", "Dunmore Flats", 1_800_000_00),
)


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: One base fact per charge:
#: ``(line_id, date, merchant, category, amount_cents, gl_code, project_code, purpose)``.
#: The statement carries the bank facts; the report carries the coding; both are
#: built from the same tuple so a charge and its report line cannot drift.
CARDHOLDERS: tuple[dict[str, Any], ...] = (
    {
        "cardholder_id": "CH-01",
        "name": "Marlowe Fenwick",
        "card_last4": "4417",
        "home_entity": "Northmoor Construction LLC",
        "approver": "Isolde Pemberton",
        "statement_id": "STMT-2909-01",
        "report_id": "EXP-2909-01",
        "charges": (
            ("L-0101", "2029-09-03", "Cascadia Air Charter", "airfare", d(842.50), "6010", "PRJ-101", "Site kickoff travel to Brightwater Commons"),
            ("L-0102", "2029-09-08", "Rivertown Lodging", "lodging", d(1_215.00), "6010", "PRJ-101", "Two nights lodging for the Brightwater Commons inspection"),
            ("L-0103", "2029-09-14", "Meridian Supply Co", "supplies", d(318.76), "6030", "PRJ-102", "Field office supplies for Copperfield Yards"),
            ("L-0104", "2029-09-21", "Harbor Fuel Stop", "fuel", d(96.40), "6040", "PRJ-101", "Fuel for the Brightwater Commons site truck"),
        ),
    },
    {
        "cardholder_id": "CH-02",
        "name": "Delia Ashcombe",
        "card_last4": "8823",
        "home_entity": "Halbrook Builders",
        "approver": "Isolde Pemberton",
        "statement_id": "STMT-2909-02",
        "report_id": "EXP-2909-02",
        "charges": (
            ("L-0201", "2029-09-05", "Cascadia Air Charter", "airfare", d(1_005.00), "6010", "PRJ-103", "Travel to the Alderpoint Terraces preconstruction meeting"),
            ("L-0202", "2029-09-11", "Green Fork Catering", "meals", d(284.15), "6020", "PRJ-103", "Working lunch for Alderpoint Terraces subcontractor coordination"),
            ("L-0203", "2029-09-19", "Pinehill Software", "software", d(1_499.00), "6030", "PRJ-104", "Estimating software renewal for Dunmore Flats"),
        ),
    },
    {
        "cardholder_id": "CH-03",
        "name": "Rupert Vance",
        "card_last4": "6190",
        "home_entity": "Stonecrest Holdings",
        "approver": "Cassian Merrow",
        "statement_id": "STMT-2909-03",
        "report_id": "EXP-2909-03",
        "charges": (
            ("L-0301", "2029-09-02", "Rivertown Lodging", "lodging", d(1_320.00), "6010", "PRJ-102", "Lodging for the Copperfield Yards walkthrough"),
            ("L-0302", "2029-09-13", "Meridian Supply Co", "supplies", d(742.88), "6030", "PRJ-104", "Safety supplies for Dunmore Flats"),
            ("L-0303", "2029-09-24", "Harbor Fuel Stop", "fuel", d(110.25), "6040", "PRJ-104", "Fuel for Dunmore Flats equipment transport"),
        ),
    },
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _cardholder(payload: dict[str, Any], cid: str) -> dict[str, Any]:
    register = _doc(payload, DOC_CARDHOLDER_REGISTER)
    assert register is not None
    for row in register["cardholders"]:
        if row.get("cardholder_id") == cid:
            return row
    raise KeyError(cid)


def _statement_of(payload: dict[str, Any], statement_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_STATEMENT_REGISTER)
    assert register is not None
    for stmt in register["statements"]:
        if stmt.get("statement_id") == statement_id:
            return stmt
    raise KeyError(statement_id)


def _report_of(payload: dict[str, Any], report_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_EXPENSE_REPORT_REGISTER)
    assert register is not None
    for report in register["reports"]:
        if report.get("report_id") == report_id:
            return report
    raise KeyError(report_id)


def _stmt_line(payload: dict[str, Any], line_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_STATEMENT_REGISTER)
    assert register is not None
    for stmt in register["statements"]:
        for line in stmt["lines"]:
            if line.get("line_id") == line_id:
                return line
    raise KeyError(line_id)


def _report_line(payload: dict[str, Any], statement_line_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_EXPENSE_REPORT_REGISTER)
    assert register is not None
    for report in register["reports"]:
        for line in report["lines"]:
            if line.get("statement_line_id") == statement_line_id:
                return line
    raise KeyError(statement_line_id)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts.

    The report line mirrors its statement charge to the cent, and the ledger's
    P-Card total mirrors the reports. Stated once here so the clean baseline is
    internally consistent by construction.
    """
    stmt_doc = _doc(payload, DOC_STATEMENT_REGISTER)
    report_doc = _doc(payload, DOC_EXPENSE_REPORT_REGISTER)
    gl = _doc(payload, DOC_GL_POSITIONS)
    if not all((stmt_doc, report_doc, gl)):
        return
    assert stmt_doc and report_doc and gl

    amount_by_line: dict[str, int] = {}
    for stmt in stmt_doc["statements"]:
        for line in stmt["lines"]:
            amount_by_line[line["line_id"]] = line["amount_cents"]

    total = 0
    for report in report_doc["reports"]:
        for line in report["lines"]:
            amount = amount_by_line.get(line["statement_line_id"], 0)
            line["amount_cents"] = amount
            total += amount

    gl["total_pcard_expense_cents"] = total


def baseline(programme: str) -> dict[str, Any]:
    """Build a clean cycle file for ``programme``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "programme": programme,
        "cycle": CYCLE,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_CARDHOLDER_REGISTER,
                "document_id": "CARD-2909",
                "cardholders": [
                    {
                        "cardholder_id": ch["cardholder_id"],
                        "name": ch["name"],
                        "card_last4": ch["card_last4"],
                        "home_entity": ch["home_entity"],
                    }
                    for ch in CARDHOLDERS
                ],
            },
            {
                "doc_type": DOC_POLICY,
                "document_id": "POL-2909",
                "submission_window_days": POLICY["submission_window_days"],
                "per_charge_limit_cents": POLICY["per_charge_limit_cents"],
                "disallowed_categories": list(POLICY["disallowed_categories"]),
                "valid_gl_codes": list(POLICY["valid_gl_codes"]),
            },
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PROJ-2909",
                "projects": [
                    {"code": code, "name": name, "budget_cents": budget}
                    for code, name, budget in PROJECTS
                ],
            },
            {
                "doc_type": DOC_STATEMENT_REGISTER,
                "document_id": "STMT-2909",
                "statements": [
                    {
                        "statement_id": ch["statement_id"],
                        "cardholder_id": ch["cardholder_id"],
                        "statement_date": STATEMENT_DATE,
                        "cycle": CYCLE,
                        "lines": [
                            {
                                "line_id": line_id,
                                "date": cdate,
                                "merchant": merchant,
                                "category": category,
                                "amount_cents": amount,
                                "last4": ch["card_last4"],
                            }
                            for (line_id, cdate, merchant, category, amount, _gl, _prj, _purpose) in ch["charges"]
                        ],
                    }
                    for ch in CARDHOLDERS
                ],
            },
            {
                "doc_type": DOC_EXPENSE_REPORT_REGISTER,
                "document_id": "EXP-2909",
                "reports": [
                    {
                        "report_id": ch["report_id"],
                        "cardholder_id": ch["cardholder_id"],
                        "statement_id": ch["statement_id"],
                        "cycle": CYCLE,
                        "submitted_date": SUBMITTED_DATE,
                        "approver": ch["approver"],
                        "lines": [
                            {
                                "line_id": f"R-{line_id}",
                                "statement_line_id": line_id,
                                "gl_code": gl_code,
                                "project_code": project_code,
                                "purpose": purpose,
                                "receipt_on_file": True,
                                "amount_cents": 0,
                            }
                            for (line_id, _cdate, _merchant, _category, _amount, gl_code, project_code, purpose) in ch["charges"]
                        ],
                    }
                    for ch in CARDHOLDERS
                ],
            },
            {
                "doc_type": DOC_GL_POSITIONS,
                "document_id": "GL-2909",
                "total_pcard_expense_cents": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control
# --------------------------------------------------------------------------- #
def _set_charge_amount(payload: dict[str, Any], line_id: str, new_cents: int) -> None:
    """Move a charge to ``new_cents`` on the statement, its report line and the GL.

    Keeps every tie-out intact so the mutation is confined to the control it is
    built to trip.
    """
    stmt_line = _stmt_line(payload, line_id)
    old = stmt_line["amount_cents"]
    stmt_line["amount_cents"] = new_cents
    _report_line(payload, line_id)["amount_cents"] = new_cents
    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["total_pcard_expense_cents"] += new_cents - old


def _missing_artifact(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_GL_POSITIONS
    ]


def _card_missing_field(payload: dict[str, Any]) -> None:
    del _cardholder(payload, "CH-02")["home_entity"]


def _card_duplicate_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CARDHOLDER_REGISTER)
    assert register is not None
    register["cardholders"].append(dict(_cardholder(payload, "CH-01")))


def _card_bad_last4(payload: dict[str, Any]) -> None:
    # Three digits: cannot be the last four of a card number.
    _cardholder(payload, "CH-03")["card_last4"] = "619"


def _card_unknown_entity(payload: dict[str, Any]) -> None:
    _cardholder(payload, "CH-01")["home_entity"] = "Westmere Group"


def _stmt_missing_field(payload: dict[str, Any]) -> None:
    del _stmt_line(payload, "L-0202")["merchant"]


def _stmt_duplicate_line_id(payload: dict[str, Any]) -> None:
    # A second charge is entered under an existing line id.
    _stmt_line(payload, "L-0203")["line_id"] = "L-0201"


def _stmt_wrong_last4(payload: dict[str, Any]) -> None:
    _stmt_line(payload, "L-0102")["last4"] = "0000"


def _rpt_missing_field(payload: dict[str, Any]) -> None:
    del _report_line(payload, "L-0202")["gl_code"]


def _rpt_no_receipt(payload: dict[str, Any]) -> None:
    _report_line(payload, "L-0103")["receipt_on_file"] = False


def _rpt_blank_purpose(payload: dict[str, Any]) -> None:
    _report_line(payload, "L-0301")["purpose"] = ""


def _rec_unreported_charge(payload: dict[str, Any]) -> None:
    # The report line for a real charge is dropped; the bank charge stands alone.
    report = _report_of(payload, "EXP-2909-01")
    report["lines"] = [
        line for line in report["lines"] if line.get("statement_line_id") != "L-0104"
    ]


def _rec_orphan_report_line(payload: dict[str, Any]) -> None:
    _report_line(payload, "L-0203")["statement_line_id"] = "L-9999"


def _rec_total_untied(payload: dict[str, Any]) -> None:
    _report_line(payload, "L-0302")["amount_cents"] += d(1.00)


def _gl_total_untied(payload: dict[str, Any]) -> None:
    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["total_pcard_expense_cents"] += d(100.00)


def _cod_bad_gl(payload: dict[str, Any]) -> None:
    _report_line(payload, "L-0101")["gl_code"] = "9999"


def _cod_bad_project(payload: dict[str, Any]) -> None:
    _report_line(payload, "L-0201")["project_code"] = "PRJ-999"


def _cod_disallowed(payload: dict[str, Any]) -> None:
    _stmt_line(payload, "L-0303")["category"] = "gambling"


def _pol_late_submission(payload: dict[str, Any]) -> None:
    # Filed six weeks after the statement, well outside the window.
    _report_of(payload, "EXP-2909-02")["submitted_date"] = "2029-11-15"


def _pol_over_limit(payload: dict[str, Any]) -> None:
    policy = _doc(payload, DOC_POLICY)
    assert policy is not None
    _set_charge_amount(payload, "L-0203", policy["per_charge_limit_cents"] + d(1.00))


def _pol_self_approved(payload: dict[str, Any]) -> None:
    _report_of(payload, "EXP-2909-03")["approver"] = _cardholder(payload, "CH-03")["name"]


def _dup_charge(payload: dict[str, Any]) -> None:
    # A duplicate of L-0101 is added, with a matching report line and a GL bump,
    # so only the duplicate-charge control trips.
    stmt = _statement_of(payload, "STMT-2909-01")
    original = next(line for line in stmt["lines"] if line["line_id"] == "L-0101")
    duplicate = dict(original)
    duplicate["line_id"] = "L-0105"
    stmt["lines"].append(duplicate)

    report = _report_of(payload, "EXP-2909-01")
    rorig = next(line for line in report["lines"] if line["statement_line_id"] == "L-0101")
    rdup = dict(rorig)
    rdup["line_id"] = "R-L-0105"
    rdup["statement_line_id"] = "L-0105"
    report["lines"].append(rdup)

    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["total_pcard_expense_cents"] += original["amount_cents"]


def _amount_not_integer(payload: dict[str, Any]) -> None:
    line = _stmt_line(payload, "L-0101")
    line["amount_cents"] = float(line["amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "card_missing_field": ("card_required_fields", _card_missing_field),
    "card_duplicate_id": ("card_id_unique", _card_duplicate_id),
    "card_bad_last4": ("card_last4_valid", _card_bad_last4),
    "card_unknown_entity": ("card_home_entity_known", _card_unknown_entity),
    "stmt_missing_field": ("stmt_required_fields", _stmt_missing_field),
    "stmt_duplicate_line_id": ("stmt_line_unique", _stmt_duplicate_line_id),
    "stmt_wrong_last4": ("stmt_last4_matches_card", _stmt_wrong_last4),
    "rpt_missing_field": ("rpt_required_fields", _rpt_missing_field),
    "rpt_no_receipt": ("rpt_receipt_on_file", _rpt_no_receipt),
    "rpt_blank_purpose": ("rpt_purpose_present", _rpt_blank_purpose),
    "rec_unreported_charge": ("rec_every_charge_reported", _rec_unreported_charge),
    "rec_orphan_report_line": ("rec_no_orphan_report_line", _rec_orphan_report_line),
    "rec_total_untied": ("rec_report_total_ties", _rec_total_untied),
    "gl_total_untied": ("rec_gl_ties_reports", _gl_total_untied),
    "cod_bad_gl": ("cod_gl_valid", _cod_bad_gl),
    "cod_bad_project": ("cod_project_exists", _cod_bad_project),
    "cod_disallowed": ("cod_disallowed_category", _cod_disallowed),
    "pol_late_submission": ("pol_submitted_within_window", _pol_late_submission),
    "pol_over_limit": ("pol_per_charge_limit", _pol_over_limit),
    "pol_self_approved": ("pol_approver_distinct", _pol_self_approved),
    "dup_charge": ("dup_no_duplicate_charge", _dup_charge),
    "amount_not_integer": ("stmt_amounts_integer", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PROGRAMMES[0])
    clean["file_id"] = f"clean__{PROGRAMMES[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        programme = PROGRAMMES[(i + 1) % len(PROGRAMMES)]
        f = baseline(programme)
        f["file_id"] = f"{name}__{programme.replace(' ', '_')}"
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
