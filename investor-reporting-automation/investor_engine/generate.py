"""
Fictional JV investor reporting corpus generator.
=================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The project entities, the members, the chart of
accounts, the divisions of job cost, the equity draws, the notes and every amount
and date are fictional, and the reporting period is set in a fictional future. No
real entity, person, project, street, neighbourhood, jurisdiction or path appears
anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the base facts are stated: the non-capital ledger accounts, the job cost
detail by division, the cost carried in the ledger and not in the cost report,
the equity draw schedule, the prior package's closing capital, each member's
distributions and sharing ratio, the presentation the statement of operations
declares, the cover's assertions, the notes' cell references, the tie-out rows
and the artifact list.

Everything the engine later checks as a derived figure -- the package trial
balance, the balance sheet and its section totals, every capital column and the
Total column across it, the contribution detail, the development cost total, the
job cost report total, the bank reconciliation balances, the parent's reciprocal
investment and every figure quoted in a note -- is recomputed by :func:`rederive`
from those base facts, through the *same* :mod:`investor_engine.package` kernel
and the *same* ``recompute_*`` helpers in :mod:`investor_engine.engine` that the
controls recompute with.

So the relationships the engine tests are the relationships that produced the
data: a defect that changes a base fact re-derives the package and keeps the
break confined to one control, and a defect that targets a stated figure edits
that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    recompute_balance_sheet,
    recompute_capital_columns,
    recompute_cash_support,
    recompute_contribution_detail,
    recompute_trial_balance,
    resolve_cell,
)
from .model import (
    ACCT_ASSET,
    ACCT_EQUITY,
    ACCT_EXPENSE,
    ACCT_LIABILITY,
    ACCT_REVENUE,
    CAPITAL_BEGINNING,
    CAPITAL_CONTRIBUTIONS,
    CAPITAL_DISTRIBUTIONS,
    CAPITAL_ENDING,
    CAPITAL_NET_INCOME,
    CAPITAL_RATIO_ROW,
    DOC_BALANCE_SHEET,
    DOC_CAPITAL_STATEMENT,
    DOC_CASH_SUPPORT,
    DOC_DEVCOST_SCHEDULE,
    DOC_DRAW_SCHEDULE,
    DOC_ENTITY_LEDGER,
    DOC_FOOTNOTES,
    DOC_INCOME_STATEMENT,
    DOC_JOB_COST_DETAIL,
    DOC_JOBCOST_REPORT,
    DOC_PACKAGE_COVER,
    DOC_PARENT_LEDGER,
    DOC_PRIOR_PACKAGE,
    DOC_RELEASE_LOG,
    DOC_TRIAL_BALANCE,
    DOC_TYPES,
    DRAW_CANCELLED,
    DRAW_EXECUTED,
    DRAW_SCHEDULED,
    RELEASE_HELD,
    RELEASE_RELEASED,
    ROLE_CAPITAL,
    ROLE_CASH,
    ROLE_INTERCOMPANY,
    ROLE_NONE,
    ROLE_WIP,
    SCHEDULE_COST_TO_DATE,
    SCHEDULE_PERIOD_ACTIVITY,
    SECTION_ASSETS,
    TOTAL_COLUMN,
    Context,
)

#: Fictional project entities, rotated for file identity only.
PROJECT_ENTITIES: tuple[str, ...] = (
    "Brightwater Commons",
    "Copperfield Yards",
    "Alderpoint Terraces",
    "Dunmore Flats",
)

#: The package is monthly. The period is set in a fictional future.
PERIOD = "FY2032-M04"
PERIOD_START = "2032-04-01"
PERIOD_END = "2032-04-30"
PRIOR_PERIOD = "FY2032-M03"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(member_id, name, role, ownership_bps)``. Two members: the developer that
#: manages the project entity and the joint-venture equity partner that funds
#: most of it. The ratio is disclosed in the capital statement and has to
#: cross-foot to a whole like any other row.
MEMBERS: tuple[tuple[Any, ...], ...] = (
    ("MEM-01", "Northmoor Development Group", "managing", 2000),
    ("MEM-02", "Halbrook Residential Partners", "investor", 8000),
)

#: ``(account_no, name, type, role, member_id, debit, credit)``. Dollars. The
#: project entity's chart of accounts as the ledger extract reports it.
#:
#: Four accounts are here for what they prove rather than for what they hold.
#: ``1290`` cycled the same amount in and out, so it has activity and a nil
#: balance -- exactly the account a package drops. ``1500`` is numbered as an
#: asset and sits in credit, so it has to be reclassified rather than netted.
#: ``2060``, ``4100`` and ``6100`` are nil, which is why they are legitimately
#: absent from the trial balance -- and why giving one of them a balance is a
#: silent omission rather than a visible error. The two capital accounts are
#: derived from the capital statement, so they open at nil here.
LEDGER: tuple[tuple[Any, ...], ...] = (
    ("1010", "Cash - operating", ACCT_ASSET, ROLE_CASH, "", 1_842_000, 0),
    ("1020", "Cash - restricted reserve", ACCT_ASSET, ROLE_CASH, "", 350_000, 0),
    ("1290", "Construction cost clearing", ACCT_ASSET, ROLE_NONE, "", 45_000, 45_000),
    ("1310", "Work in process - development cost", ACCT_ASSET, ROLE_WIP, "", 38_400_000, 0),
    ("1400", "Prepaid insurance", ACCT_ASSET, ROLE_NONE, "", 96_000, 0),
    (
        "1500",
        "Intercompany - managing member advances",
        ACCT_ASSET,
        ROLE_INTERCOMPANY,
        "",
        0,
        640_000,
    ),
    ("2010", "Accounts payable", ACCT_LIABILITY, ROLE_NONE, "", 0, 1_120_000),
    ("2020", "Retainage payable", ACCT_LIABILITY, ROLE_NONE, "", 0, 985_000),
    ("2050", "Accrued interest payable", ACCT_LIABILITY, ROLE_NONE, "", 0, 214_000),
    ("2060", "Accrued property tax", ACCT_LIABILITY, ROLE_NONE, "", 0, 0),
    ("2100", "Construction loan payable", ACCT_LIABILITY, ROLE_NONE, "", 0, 22_000_000),
    ("3010", "Members' capital - managing member", ACCT_EQUITY, ROLE_CAPITAL, "MEM-01", 0, 0),
    ("3020", "Members' capital - investor member", ACCT_EQUITY, ROLE_CAPITAL, "MEM-02", 0, 0),
    ("4100", "Other income", ACCT_REVENUE, ROLE_NONE, "", 0, 0),
    ("6100", "Marketing and promotion", ACCT_EXPENSE, ROLE_NONE, "", 0, 0),
)

#: ``(division_code, label, cost_to_date)``. Dollars. Job cost detail by
#: division, as the cost system reports it. The job cost report total is footed
#: from this and never typed.
DIVISIONS: tuple[tuple[Any, ...], ...] = (
    ("DIV-01", "General conditions", 2_860_000),
    ("DIV-02", "Sitework and demolition", 3_140_000),
    ("DIV-03", "Concrete", 6_920_000),
    ("DIV-05", "Structural steel", 2_480_000),
    ("DIV-06", "Wood and plastics", 5_760_000),
    ("DIV-08", "Openings", 1_940_000),
    ("DIV-09", "Finishes", 3_020_000),
    ("DIV-15", "Mechanical and plumbing", 4_180_000),
    ("DIV-16", "Electrical", 2_610_000),
    ("SOFT-01", "Design and consultants", 2_150_000),
    ("SOFT-02", "Permits and fees", 1_180_000),
    ("SOFT-03", "Financing costs", 1_470_000),
)

#: ``(division_code, label, cost_to_date)``. Dollars. Cost capitalised in the
#: ledger that the cost system never sees, which is the whole reason the job cost
#: report and work in process differ -- routinely, and for a good reason. It is
#: on the development cost schedule and it is the reconciling item in the bridge.
LEDGER_ONLY_COST: tuple[tuple[Any, ...], ...] = (
    ("GL-INT", "Capitalized interest recorded in the general ledger", 690_000),
)

#: ``(item_id, label, amount, exception_id, covers_divisions)``. Dollars. The
#: bridge between the job cost report and the ledger, itemized and disclosed --
#: which is the control, not agreement.
RECONCILING: tuple[tuple[Any, ...], ...] = (
    (
        "REC-01",
        "Capitalized interest recorded in the general ledger and excluded from the job cost report",
        690_000,
        "EXC-01",
        ("GL-INT",),
    ),
)

#: ``(draw_id, member_id, funded_date, amount, status)``. Dollars. The executed
#: equity draw schedule, which is the document the partner also holds.
#:
#: The cancelled pair is inside the period and the scheduled pair is after it, so
#: a contribution total that counted either would be visibly wrong -- and a
#: control that summed the schedule without filtering would pass on data that
#: happened to agree.
DRAWS: tuple[tuple[Any, ...], ...] = (
    ("DRAW-101", "MEM-01", "2032-04-06", 160_000, DRAW_EXECUTED),
    ("DRAW-102", "MEM-02", "2032-04-06", 640_000, DRAW_EXECUTED),
    ("DRAW-103", "MEM-01", "2032-04-11", 40_000, DRAW_CANCELLED),
    ("DRAW-104", "MEM-02", "2032-04-11", 160_000, DRAW_CANCELLED),
    ("DRAW-105", "MEM-01", "2032-04-15", 100_000, DRAW_EXECUTED),
    ("DRAW-106", "MEM-02", "2032-04-15", 400_000, DRAW_EXECUTED),
    ("DRAW-107", "MEM-01", "2032-04-26", 140_000, DRAW_EXECUTED),
    ("DRAW-108", "MEM-02", "2032-04-26", 560_000, DRAW_EXECUTED),
    ("DRAW-109", "MEM-01", "2032-05-08", 120_000, DRAW_SCHEDULED),
    ("DRAW-110", "MEM-02", "2032-05-08", 480_000, DRAW_SCHEDULED),
)

#: ``(member_id, ending)``. Dollars. What the prior package closed each member
#: at, and therefore what this one has to open at.
PRIOR_CLOSING: tuple[tuple[Any, ...], ...] = (
    ("MEM-01", 2_795_800),
    ("MEM-02", 11_183_200),
)

#: ``(member_id, distributions)``. Dollars. Returns of capital in the period --
#: the one capital row that comes from neither the draw schedule nor the prior
#: package.
DISTRIBUTIONS: tuple[tuple[Any, ...], ...] = (
    ("MEM-01", 50_000),
    ("MEM-02", 200_000),
)

#: ``(note_id, text, cell_ref)``. Each note quotes one figure and names the cell
#: it came from; the figure itself is resolved from that cell by
#: :func:`rederive`, so a clean note is a note that agrees by construction.
FOOTNOTES: tuple[tuple[Any, ...], ...] = (
    ("NOTE-01", "Construction loan payable outstanding at the period end", "balance_sheet/row/2100"),
    ("NOTE-02", "Retainage withheld from trade contractors", "balance_sheet/row/2020"),
    (
        "NOTE-03",
        "Investor member capital at the period end",
        "capital_statement/column/MEM-02/ending_cents",
    ),
    ("NOTE-04", "Job cost incurred to date per the cost report", "jobcost_report/total_cents"),
    (
        "NOTE-05",
        "Members' capital at the beginning of the period",
        "capital_statement/column/total/beginning_cents",
    ),
)

#: ``(row_id, statement, label)``. The reviewer's own arithmetic. Every one of
#: these is outside the released print area in the clean baseline, which is where
#: all of them belong.
CHECK_ROWS: tuple[tuple[Any, ...], ...] = (
    ("CHK-01", DOC_TRIAL_BALANCE, "Check: debits less credits"),
    ("CHK-02", DOC_BALANCE_SHEET, "Check: assets less liabilities and capital"),
    ("CHK-03", DOC_CAPITAL_STATEMENT, "Check: ending capital less ledger capital"),
    ("CHK-04", DOC_DEVCOST_SCHEDULE, "Check: schedule less work in process"),
)

#: ``(artifact_id, label, preparer_only, released)``. What is in the workbook
#: against what leaves it. The three preparer-only artifacts travel with the file
#: because they live in the same workbook, and none of them is part of the
#: package.
ARTIFACTS: tuple[tuple[Any, ...], ...] = (
    ("ART-01", "Statement of financial position", False, True),
    ("ART-02", "Statement of members' capital", False, True),
    ("ART-03", "Statement of operations", False, True),
    ("ART-04", "Development cost schedule", False, True),
    ("ART-05", "Job cost bridge", False, True),
    ("ART-06", "Trial balance", False, True),
    ("ART-07", "Notes to the financial statements", False, True),
    ("ART-08", "Preparer tickmark sheet", True, False),
    ("ART-09", "Ledger extract worksheet", True, False),
    ("ART-10", "Reviewer comment log", True, False),
)

#: The statements the cover's contents page names, in issue order.
CONTENTS: tuple[str, ...] = (
    DOC_TRIAL_BALANCE,
    DOC_BALANCE_SHEET,
    DOC_INCOME_STATEMENT,
    DOC_CAPITAL_STATEMENT,
    DOC_DEVCOST_SCHEDULE,
    DOC_JOBCOST_REPORT,
    DOC_FOOTNOTES,
)

#: The basis of presentation the cover asserts over the whole package.
BASIS_OF_PRESENTATION = (
    "Prepared from the books of the project entity on the accrual basis. Development cost is "
    "capitalized to work in process during construction and no depreciation is recorded. Amounts "
    "are stated in whole currency units."
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _need(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    doc = _doc(payload, doc_type)
    assert doc is not None, doc_type
    return doc


def _ledger_account(payload: dict[str, Any], account_no: str) -> dict[str, Any]:
    for row in _need(payload, DOC_ENTITY_LEDGER)["accounts"]:
        if row.get("account_no") == account_no:
            return row
    raise KeyError(account_no)


def _tb_row(payload: dict[str, Any], account_no: str) -> dict[str, Any]:
    for row in _need(payload, DOC_TRIAL_BALANCE)["rows"]:
        if row.get("account_no") == account_no:
            return row
    raise KeyError(account_no)


def _sort_tb(payload: dict[str, Any]) -> None:
    """Re-sort the trial balance the way an export of it comes out.

    Reading order, not account order -- the same key
    :func:`~investor_engine.engine.recompute_trial_balance` uses, so a mutation
    that adds a row leaves a file that still looks like something a preparer
    exported.
    """
    rows = _need(payload, DOC_TRIAL_BALANCE)["rows"]
    rows.sort(key=lambda r: (r.get("account_name", ""), r.get("account_no", "")))


def _bs_row(payload: dict[str, Any], *, account_no: str = "", member_id: str = "") -> dict[str, Any]:
    for row in _need(payload, DOC_BALANCE_SHEET)["rows"]:
        if account_no and row.get("account_no") == account_no:
            return row
        if member_id and row.get("member_id") == member_id:
            return row
    raise KeyError(account_no or member_id)


def _column(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return _need(payload, DOC_CAPITAL_STATEMENT)["columns"][key]


def _devcost_row(payload: dict[str, Any], division_code: str) -> dict[str, Any]:
    for row in _need(payload, DOC_DEVCOST_SCHEDULE)["rows"]:
        if row.get("division_code") == division_code:
            return row
    raise KeyError(division_code)


def _draw(payload: dict[str, Any], draw_id: str) -> dict[str, Any]:
    for row in _need(payload, DOC_DRAW_SCHEDULE)["draws"]:
        if row.get("draw_id") == draw_id:
            return row
    raise KeyError(draw_id)


def _note(payload: dict[str, Any], note_id: str) -> dict[str, Any]:
    for row in _need(payload, DOC_FOOTNOTES)["notes"]:
        if row.get("note_id") == note_id:
            return row
    raise KeyError(note_id)


def _prior_row(payload: dict[str, Any], member_id: str) -> dict[str, Any]:
    for row in _need(payload, DOC_PRIOR_PACKAGE)["closing_capital"]:
        if row.get("member_id") == member_id:
            return row
    raise KeyError(member_id)


def _check_row(payload: dict[str, Any], row_id: str) -> dict[str, Any]:
    for row in _need(payload, DOC_RELEASE_LOG)["check_rows"]:
        if row.get("row_id") == row_id:
            return row
    raise KeyError(row_id)


def _artifact(payload: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    for row in _need(payload, DOC_RELEASE_LOG)["artifacts"]:
        if row.get("artifact_id") == artifact_id:
            return row
    raise KeyError(artifact_id)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure in the package from its own base facts.

    Order matters exactly once: the members' capital statement is rebuilt first,
    because the ledger's capital accounts, the balance sheet's equity section and
    the parent's reciprocal investment are all derived from it. Everything else is
    independent.

    The re-derivation runs through the same helpers the controls use, so a clean
    baseline is clean by construction rather than by arithmetic performed twice.
    """
    if any(_doc(payload, doc_type) is None for doc_type in DOC_TYPES):
        return
    ctx = Context(path=Path("<generated>"), data=payload)

    statement = _need(payload, DOC_CAPITAL_STATEMENT)
    statement["columns"] = recompute_capital_columns(ctx)
    statement["contribution_detail"] = recompute_contribution_detail(ctx)
    columns = statement["columns"]

    for account in _need(payload, DOC_ENTITY_LEDGER)["accounts"]:
        if account.get("role") != ROLE_CAPITAL:
            continue
        column = columns.get(account.get("member_id"), {})
        account["credit_cents"] = column.get(CAPITAL_ENDING, 0)

    _need(payload, DOC_TRIAL_BALANCE)["rows"] = recompute_trial_balance(ctx)
    _need(payload, DOC_BALANCE_SHEET).update(recompute_balance_sheet(ctx))

    schedule = _need(payload, DOC_DEVCOST_SCHEDULE)
    schedule["total_cents"] = sum(row["cost_to_date_cents"] for row in schedule["rows"])

    report = _need(payload, DOC_JOBCOST_REPORT)
    report["total_cents"] = sum(
        row["cost_to_date_cents"] for row in _need(payload, DOC_JOB_COST_DETAIL)["divisions"]
    )

    _need(payload, DOC_CASH_SUPPORT)["reconciliations"] = recompute_cash_support(ctx)

    parent = _need(payload, DOC_PARENT_LEDGER)
    held = columns.get(parent["parent_member_id"], {}).get(CAPITAL_ENDING, 0)
    for account in parent["accounts"]:
        account["balance_cents"] = held

    for note in _need(payload, DOC_FOOTNOTES)["notes"]:
        resolved = resolve_cell(ctx, note["cell_ref"])
        note["quoted_cents"] = 0 if resolved is None else resolved

    cover = _need(payload, DOC_PACKAGE_COVER)
    cover["referenced_exception_ids"] = [
        item["exception_id"] for item in cover["disclosed_exceptions"]
    ]


def baseline(project_entity: str) -> dict[str, Any]:
    """Build a clean package file for ``project_entity``."""
    distributions = dict(DISTRIBUTIONS)
    payload: dict[str, Any] = {
        "file_id": "clean",
        "project_entity": project_entity,
        "period": PERIOD,
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "documents": [
            {
                "doc_type": DOC_ENTITY_LEDGER,
                "document_id": "GL-2032M04",
                "accounts": [
                    {
                        "account_no": account_no,
                        "name": name,
                        "type": account_type,
                        "role": role,
                        "member_id": member_id,
                        "debit_cents": d(debit),
                        "credit_cents": d(credit),
                    }
                    for account_no, name, account_type, role, member_id, debit, credit in LEDGER
                ],
            },
            {
                "doc_type": DOC_JOB_COST_DETAIL,
                "document_id": "JC-2032M04",
                "divisions": [
                    {
                        "division_code": code,
                        "label": label,
                        "cost_to_date_cents": d(cost),
                    }
                    for code, label, cost in DIVISIONS
                ],
            },
            {
                "doc_type": DOC_DRAW_SCHEDULE,
                "document_id": "DRAWS-2032M04",
                "draws": [
                    {
                        "draw_id": draw_id,
                        "member_id": member_id,
                        "funded_date": funded_date,
                        "amount_cents": d(amount),
                        "status": status,
                    }
                    for draw_id, member_id, funded_date, amount, status in DRAWS
                ],
            },
            {
                "doc_type": DOC_PARENT_LEDGER,
                "document_id": "PGL-2032M04",
                "parent_member_id": "MEM-01",
                "accounts": [
                    {
                        "account_no": "1710",
                        "name": "Investment in project entity",
                        "balance_cents": 0,
                    }
                ],
            },
            {
                "doc_type": DOC_PRIOR_PACKAGE,
                "document_id": "PKG-2032M03",
                "period": PRIOR_PERIOD,
                "closing_capital": [
                    {"member_id": member_id, "ending_cents": d(ending)}
                    for member_id, ending in PRIOR_CLOSING
                ],
                "closing_total_cents": d(sum(ending for _member_id, ending in PRIOR_CLOSING)),
            },
            {
                "doc_type": DOC_PACKAGE_COVER,
                "document_id": "COVER-2032M04",
                "contents": list(CONTENTS),
                "basis_of_presentation": BASIS_OF_PRESENTATION,
                "asserts_no_exceptions": False,
                "disclosed_exceptions": [
                    {
                        "exception_id": exception_id,
                        "label": label,
                        "amount_cents": d(amount),
                    }
                    for _item_id, label, amount, exception_id, _covers in RECONCILING
                ],
                "referenced_exception_ids": [],
            },
            {
                "doc_type": DOC_TRIAL_BALANCE,
                "document_id": "TB-2032M04",
                "rows": [],
            },
            {
                "doc_type": DOC_BALANCE_SHEET,
                "document_id": "BS-2032M04",
                "rows": [],
                "total_assets_cents": 0,
                "total_liabilities_cents": 0,
                "total_equity_cents": 0,
            },
            {
                "doc_type": DOC_INCOME_STATEMENT,
                "document_id": "IS-2032M04",
                "schedule_type": SCHEDULE_PERIOD_ACTIVITY,
                "caption": "Results of operations for the period",
                "presented_nil": True,
                "revenue_rows": [],
                "expense_rows": [],
                "net_income_cents": 0,
            },
            {
                "doc_type": DOC_CAPITAL_STATEMENT,
                "document_id": "CAP-2032M04",
                "schedule_type": SCHEDULE_PERIOD_ACTIVITY,
                "caption": "Members' capital activity for the period",
                "members": [
                    {
                        "member_id": member_id,
                        "name": name,
                        "role": role,
                        "ownership_bps": bps,
                    }
                    for member_id, name, role, bps in MEMBERS
                ],
                "columns": {
                    **{
                        member_id: {
                            CAPITAL_BEGINNING: 0,
                            CAPITAL_CONTRIBUTIONS: 0,
                            CAPITAL_NET_INCOME: 0,
                            CAPITAL_DISTRIBUTIONS: d(distributions[member_id]),
                            CAPITAL_ENDING: 0,
                            CAPITAL_RATIO_ROW: bps,
                        }
                        for member_id, _name, _role, bps in MEMBERS
                    },
                    TOTAL_COLUMN: {
                        CAPITAL_BEGINNING: 0,
                        CAPITAL_CONTRIBUTIONS: 0,
                        CAPITAL_NET_INCOME: 0,
                        CAPITAL_DISTRIBUTIONS: 0,
                        CAPITAL_ENDING: 0,
                        CAPITAL_RATIO_ROW: 0,
                    },
                },
                "contribution_detail": [],
            },
            {
                "doc_type": DOC_DEVCOST_SCHEDULE,
                "document_id": "DEV-2032M04",
                "schedule_type": SCHEDULE_COST_TO_DATE,
                "caption": "Development cost incurred to date",
                "rows": [
                    {
                        "division_code": code,
                        "label": label,
                        "cost_to_date_cents": d(cost),
                    }
                    for code, label, cost in (*DIVISIONS, *LEDGER_ONLY_COST)
                ],
                "total_cents": 0,
            },
            {
                "doc_type": DOC_JOBCOST_REPORT,
                "document_id": "JCB-2032M04",
                "schedule_type": SCHEDULE_COST_TO_DATE,
                "caption": "Job cost incurred to date",
                "total_cents": 0,
                "reconciling_items": [
                    {
                        "item_id": item_id,
                        "label": label,
                        "amount_cents": d(amount),
                        "disclosed": True,
                        "exception_id": exception_id,
                        "covers_divisions": list(covers),
                    }
                    for item_id, label, amount, exception_id, covers in RECONCILING
                ],
            },
            {
                "doc_type": DOC_CASH_SUPPORT,
                "document_id": "CASH-2032M04",
                "reconciliations": [],
            },
            {
                "doc_type": DOC_FOOTNOTES,
                "document_id": "NOTES-2032M04",
                "notes": [
                    {
                        "note_id": note_id,
                        "text": text,
                        "cell_ref": cell_ref,
                        "quoted_cents": 0,
                    }
                    for note_id, text, cell_ref in FOOTNOTES
                ],
            },
            {
                "doc_type": DOC_RELEASE_LOG,
                "document_id": "REL-2032M04",
                "controls_cleared": True,
                "release_decision": RELEASE_RELEASED,
                "check_rows": [
                    {
                        "row_id": row_id,
                        "statement": statement,
                        "label": label,
                        "in_print_area": False,
                    }
                    for row_id, statement, label in CHECK_ROWS
                ],
                "artifacts": [
                    {
                        "artifact_id": artifact_id,
                        "label": label,
                        "preparer_only": preparer_only,
                        "released": released,
                    }
                    for artifact_id, label, preparer_only, released in ARTIFACTS
                ],
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control
# --------------------------------------------------------------------------- #
def _one_sided_entry(payload: dict[str, Any]) -> None:
    # A property tax accrual posts its credit and loses its debit on the way in,
    # so the ledger itself no longer nets and the package trial balance inherits
    # it. The balance sheet was prepared before the entry and still balances,
    # which is why nothing else objects.
    account = _ledger_account(payload, "2060")
    account["credit_cents"] = d(1_000)
    _need(payload, DOC_TRIAL_BALANCE)["rows"].append(
        {
            "account_no": account["account_no"],
            "account_name": account["name"],
            "debit_cents": 0,
            "credit_cents": d(1_000),
        }
    )
    _sort_tb(payload)


def _ledger_account_omitted(payload: dict[str, Any]) -> None:
    # The clearing account nets to nil, so dropping it from the package trial
    # balance changes no total and hides the 45,000 that cycled through it.
    rows = _need(payload, DOC_TRIAL_BALANCE)["rows"]
    _need(payload, DOC_TRIAL_BALANCE)["rows"] = [r for r in rows if r["account_no"] != "1290"]


def _balance_taken_by_position(payload: dict[str, Any]) -> None:
    # The trial balance is exported in reading order and the balances were pasted
    # in account order, so two accounts swap figures. The trial balance still
    # nets, because the two amounts are still both in it.
    payable = _tb_row(payload, "2010")
    retainage = _tb_row(payload, "2020")
    payable["credit_cents"], retainage["credit_cents"] = (
        retainage["credit_cents"],
        payable["credit_cents"],
    )


def _bs_equity_transposed(payload: dict[str, Any]) -> None:
    # A digit transposition in the investor member's equity line, carried into
    # the section total, so the section still foots and the statement no longer
    # balances.
    row = _bs_row(payload, member_id="MEM-02")
    row["amount_cents"] -= d(45_000)
    sheet = _need(payload, DOC_BALANCE_SHEET)
    sheet["total_equity_cents"] -= d(45_000)


def _interco_netted_in_assets(payload: dict[str, Any]) -> None:
    # The credit intercompany balance is netted against assets instead of
    # reclassified. Both sides fall by the same amount, so the statement still
    # balances and every section still foots -- which is exactly why the
    # reclassification gets missed.
    row = _bs_row(payload, account_no="1500")
    row["section"] = SECTION_ASSETS
    row["amount_cents"] = -row["amount_cents"]
    sheet = _need(payload, DOC_BALANCE_SHEET)
    sheet["total_assets_cents"] -= d(640_000)
    sheet["total_liabilities_cents"] -= d(640_000)


def _capital_ending_off_ledger(payload: dict[str, Any]) -> None:
    # A distribution is written into the managing member's column and never
    # posts to the ledger. The rollforward is restated around it and the Total
    # column is re-added, and the parent's consolidation is built from the same
    # statement, so only the tie to the ledger capital account breaks.
    member = _column(payload, "MEM-01")
    member[CAPITAL_DISTRIBUTIONS] += d(30_000)
    member[CAPITAL_ENDING] -= d(30_000)
    total = _column(payload, TOTAL_COLUMN)
    total[CAPITAL_DISTRIBUTIONS] += d(30_000)
    total[CAPITAL_ENDING] -= d(30_000)
    for account in _need(payload, DOC_PARENT_LEDGER)["accounts"]:
        account["balance_cents"] = member[CAPITAL_ENDING]


def _contribution_line_omitted(payload: dict[str, Any]) -> None:
    # One capital call drops out of the contribution detail while the column
    # total keeps counting it, so the member column reports money the schedule
    # underneath it cannot account for.
    statement = _need(payload, DOC_CAPITAL_STATEMENT)
    statement["contribution_detail"] = [
        row for row in statement["contribution_detail"] if row["draw_id"] != "DRAW-106"
    ]


def _total_row_links_elsewhere(payload: dict[str, Any]) -> None:
    # The Total column's contribution cell is linked to a funding notice that
    # included a draw executed after the period end, instead of summing the
    # member columns beside it.
    _column(payload, TOTAL_COLUMN)[CAPITAL_CONTRIBUTIONS] += d(60_000)


def _distribution_dropped_from_rollforward(payload: dict[str, Any]) -> None:
    # Part of a distribution is trimmed out of the column and the ending balance
    # stays where it was, so the capital statement stops rolling forward while
    # still agreeing to the ledger and still cross-footing.
    _column(payload, "MEM-01")[CAPITAL_DISTRIBUTIONS] -= d(30_000)
    _column(payload, TOTAL_COLUMN)[CAPITAL_DISTRIBUTIONS] -= d(30_000)


def _net_income_off_statement(payload: dict[str, Any]) -> None:
    # A fee credit reaches the statement of operations after the capital
    # statement was allocated, so the package tells the partner two different
    # things about what the project earned.
    income = _need(payload, DOC_INCOME_STATEMENT)
    income["presented_nil"] = False
    income["revenue_rows"] = [
        {"account_no": "4100", "label": "Other income", "amount_cents": d(45_000)}
    ]
    income["net_income_cents"] = d(45_000)


def _devcost_row_understated(payload: dict[str, Any]) -> None:
    # A permit refund is netted into the schedule and never reaches work in
    # process, so the schedule foots to its own total and analyses less cost than
    # the ledger holds.
    _devcost_row(payload, "SOFT-02")["cost_to_date_cents"] -= d(27_000)
    schedule = _need(payload, DOC_DEVCOST_SCHEDULE)
    schedule["total_cents"] -= d(27_000)


def _bridge_difference_undisclosed(payload: dict[str, Any]) -> None:
    # The reconciling item is dropped out of the bridge, so the difference
    # between the job cost report and the ledger is neither itemized nor
    # disclosed -- which is what happens when a gap is absorbed rather than
    # explained.
    _need(payload, DOC_JOBCOST_REPORT)["reconciling_items"] = []


def _division_renumbered(payload: dict[str, Any]) -> None:
    # A division is renumbered in the cost system and the schedule keeps the old
    # code, so the schedule still foots to the same total while a whole trade has
    # stopped being reported.
    _devcost_row(payload, "DIV-09")["division_code"] = "DIV-19"


def _draw_schedule_variance(payload: dict[str, Any]) -> None:
    # The executed draw funded more than the package recorded as contributed, and
    # the package does not quantify the variance. Which figure is right is a
    # question about an executed transfer.
    _draw(payload, "DRAW-108")["amount_cents"] += d(45_000)


def _reciprocal_investment_stale(payload: dict[str, Any]) -> None:
    # The parent's investment account is left at last period's figure, so the
    # project entity's package and the parent's consolidation disagree about the
    # same relationship.
    for account in _need(payload, DOC_PARENT_LEDGER)["accounts"]:
        account["balance_cents"] = d(2_795_800)


def _nil_masks_activity(payload: dict[str, Any]) -> None:
    # A fee credit and a marketing cost net to nil, so the bottom line is still
    # zero, the trial balance still nets and two accounts with real activity
    # appear nowhere the partner can see them.
    income = _ledger_account(payload, "4100")
    income["credit_cents"] = d(65_000)
    expense = _ledger_account(payload, "6100")
    expense["debit_cents"] = d(65_000)
    rows = _need(payload, DOC_TRIAL_BALANCE)["rows"]
    rows.append(
        {
            "account_no": income["account_no"],
            "account_name": income["name"],
            "debit_cents": 0,
            "credit_cents": d(65_000),
        }
    )
    rows.append(
        {
            "account_no": expense["account_no"],
            "account_name": expense["name"],
            "debit_cents": d(65_000),
            "credit_cents": 0,
        }
    )
    _sort_tb(payload)


def _cash_support_absent(payload: dict[str, Any]) -> None:
    # The reserve account's bank statement has not arrived. The engine can report
    # the absence and cannot manufacture the support, which is why this is a flag
    # and not a failure.
    support = _need(payload, DOC_CASH_SUPPORT)
    support["reconciliations"] = [
        row for row in support["reconciliations"] if row["account_no"] != "1020"
    ]


def _footnote_quotes_stale_figure(payload: dict[str, Any]) -> None:
    # The loan note keeps last period's balance. The sentence is still true in
    # shape and the amount is a month old.
    _note(payload, "NOTE-01")["quoted_cents"] = d(21_400_000)


def _caption_implies_period_cost(payload: dict[str, Any]) -> None:
    # The development cost schedule is cost to date and carries a caption saying
    # the cost arose in the period, so a reader takes three years of spend for
    # one month of it. Every figure on the page is right.
    schedule = _need(payload, DOC_DEVCOST_SCHEDULE)
    schedule["caption"] = "Development cost incurred during the period"


def _cover_asserts_no_exceptions(payload: dict[str, Any]) -> None:
    # The cover was written before the bridge was finished and still asserts a
    # package free of exceptions, over notes that disclose one.
    _need(payload, DOC_PACKAGE_COVER)["asserts_no_exceptions"] = True


def _check_row_in_print_area(payload: dict[str, Any]) -> None:
    # A row got inserted above the print range and the range was never reset, so
    # the reviewer's tie-out ships as a line of the balance sheet.
    _check_row(payload, "CHK-02")["in_print_area"] = True


def _preparer_artifact_released(payload: dict[str, Any]) -> None:
    # The whole workbook was sent rather than the statements, so the reviewer
    # comment log went with it.
    _artifact(payload, "ART-10")["released"] = True


def _prior_closing_restated(payload: dict[str, Any]) -> None:
    # The prior package's closing capital is restated after issue, so this
    # period's opening balance no longer continues the package the partner holds.
    _prior_row(payload, "MEM-01")["ending_cents"] -= d(50_000)


def _statement_missing(payload: dict[str, Any]) -> None:
    # The statement of operations is named on the contents page and is not in the
    # package. Every control that reads it produces nothing at all rather than a
    # PASS, and this is the control that says so.
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_INCOME_STATEMENT
    ]


def _released_uncleared(payload: dict[str, Any]) -> None:
    # The release record says the controls were not cleared and the package is
    # marked released. Nothing else in the package is wrong: somebody knew, and
    # sent it anyway.
    log = _need(payload, DOC_RELEASE_LOG)
    log["controls_cleared"] = False
    log["release_decision"] = RELEASE_RELEASED


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _tb_row(payload, "1310")
    row["debit_cents"] = float(row["debit_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``. One file per control,
#: plus one for the money contract: an amount that is not integer cents is
#: reported as ``AMOUNT_INVALID`` rather than coerced, because rounding a source
#: figure would make the engine the author of the number it is auditing.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "one_sided_entry": ("tb_nets_zero", _one_sided_entry),
    "ledger_account_omitted": ("tb_completeness", _ledger_account_omitted),
    "balance_taken_by_position": ("tb_agrees_ledger", _balance_taken_by_position),
    "bs_equity_transposed": ("bs_balances", _bs_equity_transposed),
    "interco_netted_in_assets": ("interco_classified", _interco_netted_in_assets),
    "capital_ending_off_ledger": ("capital_agrees_ledger", _capital_ending_off_ledger),
    "contribution_line_omitted": ("contributions_foot", _contribution_line_omitted),
    "total_row_links_elsewhere": ("total_cross_foots", _total_row_links_elsewhere),
    "distribution_dropped_from_rollforward": (
        "capital_rollforward",
        _distribution_dropped_from_rollforward,
    ),
    "net_income_off_statement": ("net_income_agrees", _net_income_off_statement),
    "devcost_row_understated": ("devcost_agrees_wip", _devcost_row_understated),
    "bridge_difference_undisclosed": ("jobcost_bridge", _bridge_difference_undisclosed),
    "division_renumbered": ("division_coverage", _division_renumbered),
    "draw_schedule_variance": ("draw_schedule_agrees", _draw_schedule_variance),
    "reciprocal_investment_stale": ("reciprocal_investment", _reciprocal_investment_stale),
    "nil_masks_activity": ("nil_is_genuine", _nil_masks_activity),
    "cash_support_absent": ("cash_supported", _cash_support_absent),
    "footnote_quotes_stale_figure": ("footnote_figures", _footnote_quotes_stale_figure),
    "caption_implies_period_cost": ("caption_matches_type", _caption_implies_period_cost),
    "cover_asserts_no_exceptions": ("cover_consistent", _cover_asserts_no_exceptions),
    "check_row_in_print_area": ("checkrows_excluded", _check_row_in_print_area),
    "preparer_artifact_released": ("no_preparer_artifacts", _preparer_artifact_released),
    "prior_closing_restated": ("prior_period_continuity", _prior_closing_restated),
    "statement_missing": ("package_complete", _statement_missing),
    "released_uncleared": ("release_gate", _released_uncleared),
    "amount_not_integer": ("tb_nets_zero", _amount_not_integer),
}

#: The one defect whose file must stay marked released, because being released
#: over an open exception is the defect.
_GATE_DEFECT = "released_uncleared"


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written.

    Every defect file is marked **held** before its mutation is applied. That is
    not bookkeeping convenience: a package with a known exception is held, so a
    defect file that stayed marked released would trip the release gate as well
    as its own control, and a corpus in which one break fires two controls cannot
    prove that either of them is independent. The gate's own file is the
    exception, because being released over an open exception is what it is for.
    """
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PROJECT_ENTITIES[0])
    clean["file_id"] = f"clean__{PROJECT_ENTITIES[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        entity = PROJECT_ENTITIES[(i + 1) % len(PROJECT_ENTITIES)]
        payload = baseline(entity)
        payload["file_id"] = f"{name}__{entity.replace(' ', '_')}"
        payload["planted_defect"] = name
        if name != _GATE_DEFECT:
            _need(payload, DOC_RELEASE_LOG)["release_decision"] = RELEASE_HELD
        mutate(payload)
        files.append(payload)

    for payload in files:
        path = folder / f"{payload['file_id']}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
