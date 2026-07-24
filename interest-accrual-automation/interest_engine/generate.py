"""
Fictional interest-accrual & loan-amortization corpus generator.
================================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The lenders, the borrowers, the notes, the rates,
the balances and the GL accounts are fictional, and the accrual period is set in
a fictional future. No real entity, person, bank, jurisdiction or path appears
anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the note terms and the schedule *events* -- each period's dates, advance and
payment intent -- are stated as base facts. Every number the engine later checks
is computed from those through the *same* :mod:`interest_engine.accrual` kernel
the engine recomputes with: each period's accrued interest and ending balance,
each note's settled determination and accrued total, the reciprocal GL balances,
the interest journal, the maturity watchlist and the portfolio counts. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the rollup and keeps the break
confined to one control; a defect that targets a stated rollup edits that figure
alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .accrual import accrued_interest, ending_balance, period_rate_bps
from .engine import (
    _note_map,
    _notes,
    recompute_accrued_total,
    recompute_maturity_watchlist,
    recompute_settled,
)
from .model import (
    DEFAULT_MATURITY_LEAD_DAYS,
    DOC_DEBT_SERVICE_REPORT,
    DOC_INTEREST_JOURNAL,
    DOC_INTEREST_SUMMARY,
    DOC_MATURITY_WATCHLIST,
    DOC_NOTE_REGISTER,
    DOC_ROLLFORWARD,
    DOC_TRIAL_BALANCE,
    TB_KIND_EXPENSE,
    TB_KIND_INCOME,
    TB_KIND_NP,
    TB_KIND_NR,
    Context,
)

#: Fictional lender labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

PERIOD = "FY2029"
#: The review date every maturity and gate test is measured to.
AS_OF = "2029-10-01"
#: Lead-time window, in days, for the maturity watchlist.
MATURITY_LEAD_DAYS = 60

#: Fictional entities that lend and borrow across the note set.
E_NORTHMOOR = "Northmoor Development Group"
E_HALBROOK = "Halbrook Residential"
E_STONECREST = "Stonecrest Communities"
E_ARDENNE = "Ardenne Field Partners"
E_WESTMERE = "Westmere"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


# --------------------------------------------------------------------------- #
# Base facts: note terms and schedule events
# --------------------------------------------------------------------------- #
#: Each note is stated terms plus a list of period *events*
#: ``(period_start, period_end, advance_dollars, payment_mode)``. The generator
#: threads the beginning balance, re-derives the rate, accrual and ending through
#: the kernel, so the schedule that ships is the schedule the terms produce.
#:
#: ``payment_mode``: ``"interest"`` pays the period's accrued interest,
#: ``"none"`` pays nothing (PIK compounding), ``"payoff"`` clears the whole
#: balance to zero.
NOTES: tuple[dict[str, Any], ...] = (
    {
        "note_id": "NR-1401",
        "lender_entity": E_NORTHMOOR,
        "borrower_entity": E_HALBROOK,
        "principal": 2_000_000,
        "stated_rate_bps": 700,
        "default_rate_bps": 1200,
        "day_count_denom": 365,
        "maturity_date": "2031-06-30",
        "default_event_date": None,
        "prepayment_allowed": True,
        "subordinated_to": None,
        "pik": False,
        "payoff_expected": False,
        "nr_account": "1-101-1402",
        "np_account": "9-201-1402",
        "income_account": "1-101-4401",
        "expense_account": "9-201-4401",
        "events": (
            ("2029-06-01", "2029-07-01", 0, "interest"),
            ("2029-07-01", "2029-08-01", 0, "interest"),
        ),
    },
    {
        "note_id": "NR-1402",
        "lender_entity": E_NORTHMOOR,
        "borrower_entity": E_STONECREST,
        "principal": 1_500_000,
        "stated_rate_bps": 500,
        "default_rate_bps": 1000,
        "day_count_denom": 365,
        "maturity_date": "2031-12-31",
        "default_event_date": None,
        "prepayment_allowed": True,
        "subordinated_to": None,
        "pik": True,
        "payoff_expected": False,
        "nr_account": "1-101-1403",
        "np_account": "9-301-1403",
        "income_account": "1-101-4402",
        "expense_account": "9-301-4402",
        "events": (
            ("2029-06-01", "2029-07-01", 0, "none"),
            ("2029-07-01", "2029-08-01", 0, "none"),
        ),
    },
    {
        "note_id": "NR-1403",
        "lender_entity": E_HALBROOK,
        "borrower_entity": E_ARDENNE,
        "principal": 1_000_000,
        "stated_rate_bps": 800,
        "default_rate_bps": 1200,
        "day_count_denom": 365,
        "maturity_date": "2029-09-01",
        "default_event_date": None,
        "prepayment_allowed": False,
        "subordinated_to": None,
        "pik": False,
        "payoff_expected": True,
        "nr_account": "2-201-1402",
        "np_account": "9-401-1402",
        "income_account": "2-201-4401",
        "expense_account": "9-401-4401",
        "events": (
            ("2029-06-01", "2029-07-01", 0, "interest"),
            ("2029-07-01", "2029-08-01", 0, "interest"),
            ("2029-08-01", "2029-09-01", 0, "payoff"),
        ),
    },
    {
        "note_id": "NR-1404",
        "lender_entity": E_STONECREST,
        "borrower_entity": E_WESTMERE,
        "principal": 800_000,
        "stated_rate_bps": 600,
        "default_rate_bps": 1000,
        "day_count_denom": 365,
        "maturity_date": "2031-03-31",
        "default_event_date": None,
        "prepayment_allowed": True,
        "subordinated_to": None,
        "pik": False,
        "payoff_expected": False,
        "nr_account": "3-301-1402",
        "np_account": "9-501-1402",
        "income_account": "3-301-4401",
        "expense_account": "9-501-4401",
        "events": (
            ("2029-06-01", "2029-07-01", 0, "interest"),
            ("2029-07-01", "2029-08-01", 200_000, "interest"),
            ("2029-08-01", "2029-09-01", 0, "interest"),
        ),
    },
    {
        "note_id": "NR-1405",
        "lender_entity": E_ARDENNE,
        "borrower_entity": E_NORTHMOOR,
        "principal": 1_200_000,
        "stated_rate_bps": 700,
        "default_rate_bps": 1200,
        "day_count_denom": 365,
        "maturity_date": "2030-12-31",
        "default_event_date": "2029-08-01",
        "prepayment_allowed": True,
        "subordinated_to": "NR-1401",
        "pik": False,
        "payoff_expected": False,
        "nr_account": "4-401-1402",
        "np_account": "1-101-1409",
        "income_account": "4-401-4401",
        "expense_account": "1-101-4409",
        "events": (
            ("2029-06-01", "2029-07-01", 0, "interest"),
            ("2029-07-01", "2029-08-01", 0, "interest"),
            ("2029-08-01", "2029-09-01", 0, "interest"),
            ("2029-09-01", "2029-10-01", 0, "interest"),
        ),
    },
)


# --------------------------------------------------------------------------- #
# Schedule construction (through the shared kernel)
# --------------------------------------------------------------------------- #
def _build_rows(note: dict[str, Any]) -> list[dict[str, Any]]:
    """Roll a note's events forward into schedule rows via the accrual kernel."""
    rows: list[dict[str, Any]] = []
    denom = int(note["day_count_denom"])
    stated = int(note["stated_rate_bps"])
    default = int(note["default_rate_bps"])
    event = note["default_event_date"]
    event_date = date.fromisoformat(event) if event else None
    beginning = d(note["principal"])
    for start_s, end_s, advance_dollars, mode in note["events"]:
        start = date.fromisoformat(start_s)
        end = date.fromisoformat(end_s)
        days = (end - start).days
        rate = period_rate_bps(stated, default, start, event_date)
        accrued = accrued_interest(beginning, rate, days, denom)
        advance = d(advance_dollars)
        if mode == "interest":
            payment = accrued
        elif mode == "none":
            payment = 0
        elif mode == "payoff":
            payment = beginning + advance + accrued
        else:  # pragma: no cover - guard against a typo in the event table
            raise ValueError(f"unknown payment mode {mode!r}")
        ending = ending_balance(beginning, advance, accrued, payment)
        rows.append(
            {
                "note_id": note["note_id"],
                "period_start": start_s,
                "period_end": end_s,
                "days": days,
                "rate_bps": rate,
                "beginning_cents": beginning,
                "advance_cents": advance,
                "accrued_cents": accrued,
                "payment_cents": payment,
                "ending_cents": ending,
            }
        )
        beginning = ending
    return rows


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _note(payload: dict[str, Any], note_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_NOTE_REGISTER)
    assert register is not None
    for row in register["notes"]:
        if row.get("note_id") == note_id:
            return row
    raise KeyError(note_id)


def _rows(payload: dict[str, Any], note_id: str) -> list[dict[str, Any]]:
    schedule = _doc(payload, DOC_ROLLFORWARD)
    assert schedule is not None
    return [r for r in schedule["rows"] if r.get("note_id") == note_id]


def _final(payload: dict[str, Any], note_id: str) -> dict[str, Any]:
    rows = _rows(payload, note_id)
    return sorted(rows, key=lambda r: (r["period_start"], r["period_end"]))[-1]


def _tb_row(payload: dict[str, Any], account: str) -> dict[str, Any]:
    tb = _doc(payload, DOC_TRIAL_BALANCE)
    assert tb is not None
    for row in tb["accounts"]:
        if row.get("account") == account:
            return row
    raise KeyError(account)


def _summary_row(payload: dict[str, Any], note_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_INTEREST_SUMMARY)
    assert summary is not None
    for row in summary["notes"]:
        if row.get("note_id") == note_id:
            return row
    raise KeyError(note_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_DEBT_SERVICE_REPORT)
    assert report is not None
    return report


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_MATURITY_WATCHLIST)
    assert watchlist is not None
    return watchlist


def _journal(payload: dict[str, Any]) -> dict[str, Any]:
    journal = _doc(payload, DOC_INTEREST_JOURNAL)
    assert journal is not None
    return journal


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup figure from the payload's own base facts."""
    note_doc = _doc(payload, DOC_NOTE_REGISTER)
    sched_doc = _doc(payload, DOC_ROLLFORWARD)
    tb = _doc(payload, DOC_TRIAL_BALANCE)
    summary = _doc(payload, DOC_INTEREST_SUMMARY)
    watchlist = _doc(payload, DOC_MATURITY_WATCHLIST)
    report = _doc(payload, DOC_DEBT_SERVICE_REPORT)
    journal = _doc(payload, DOC_INTEREST_JOURNAL)
    if not all((note_doc, sched_doc, tb, summary, watchlist, report, journal)):
        return
    assert summary is not None and watchlist is not None and report is not None
    assert tb is not None and journal is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    lead = payload.get("maturity_lead_days", DEFAULT_MATURITY_LEAD_DAYS)

    # Interest summary: one settled determination and accrued total per note,
    # recomputed through the shared kernel the engine recomputes with.
    summary["notes"] = [
        {
            "note_id": note["note_id"],
            "settled": recompute_settled(ctx, note["note_id"]),
            "accrued_total_cents": recompute_accrued_total(ctx, note["note_id"]),
        }
        for note in _notes(ctx)
    ]

    # Trial balance: the reciprocal receivable/payable equal the note's ending
    # balance; interest income and expense equal the accrued total.
    accounts: list[dict[str, Any]] = []
    for note in _notes(ctx):
        nid = note["note_id"]
        final_ending = _final(payload, nid)["ending_cents"]
        accrued_total = recompute_accrued_total(ctx, nid)
        accounts.append({"account": note["nr_account"], "note_id": nid, "kind": TB_KIND_NR, "balance_cents": final_ending})
        accounts.append({"account": note["np_account"], "note_id": nid, "kind": TB_KIND_NP, "balance_cents": final_ending})
        accounts.append({"account": note["income_account"], "note_id": nid, "kind": TB_KIND_INCOME, "balance_cents": accrued_total})
        accounts.append({"account": note["expense_account"], "note_id": nid, "kind": TB_KIND_EXPENSE, "balance_cents": accrued_total})
    tb["accounts"] = accounts

    # Interest journal: for each note, DR interest expense and CR interest income
    # for the accrued total -- self-proving, and tying to the accrual.
    lines: list[dict[str, Any]] = []
    for note in _notes(ctx):
        nid = note["note_id"]
        accrued_total = recompute_accrued_total(ctx, nid)
        lines.append({"account": note["expense_account"], "note_id": nid, "debit_cents": accrued_total, "credit_cents": 0, "description": f"{nid} interest expense"})
        lines.append({"account": note["income_account"], "note_id": nid, "debit_cents": 0, "credit_cents": accrued_total, "description": f"{nid} interest income"})
    journal["lines"] = lines

    # Maturity watchlist: unsettled notes maturing inside the lead-time window.
    watchlist["entries"] = recompute_maturity_watchlist(ctx, as_of, lead)

    # Debt-service report: the portfolio counts, derived from the summary flags.
    settled = sum(1 for row in summary["notes"] if row["settled"])
    total = len(summary["notes"])
    report["settled_count"] = settled
    report["outstanding_count"] = total - settled


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean loan file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "maturity_lead_days": MATURITY_LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_NOTE_REGISTER,
                "document_id": "NOTES-2029",
                "notes": [
                    {
                        "note_id": note["note_id"],
                        "lender_entity": note["lender_entity"],
                        "borrower_entity": note["borrower_entity"],
                        "principal_cents": d(note["principal"]),
                        "stated_rate_bps": note["stated_rate_bps"],
                        "default_rate_bps": note["default_rate_bps"],
                        "day_count_denom": note["day_count_denom"],
                        "maturity_date": note["maturity_date"],
                        "default_event_date": note["default_event_date"],
                        "prepayment_allowed": note["prepayment_allowed"],
                        "subordinated_to": note["subordinated_to"],
                        "pik": note["pik"],
                        "payoff_expected": note["payoff_expected"],
                        "nr_account": note["nr_account"],
                        "np_account": note["np_account"],
                        "income_account": note["income_account"],
                        "expense_account": note["expense_account"],
                    }
                    for note in NOTES
                ],
            },
            {
                "doc_type": DOC_ROLLFORWARD,
                "document_id": "ROLLFWD-2029",
                "rows": [row for note in NOTES for row in _build_rows(note)],
            },
            {
                "doc_type": DOC_INTEREST_JOURNAL,
                "document_id": "JE-2029",
                "lines": [],
            },
            {
                "doc_type": DOC_TRIAL_BALANCE,
                "document_id": "TB-2029",
                "accounts": [],
            },
            {
                "doc_type": DOC_INTEREST_SUMMARY,
                "document_id": "SUMMARY-2029",
                "notes": [],
            },
            {
                "doc_type": DOC_MATURITY_WATCHLIST,
                "document_id": "WATCHLIST-2029",
                "entries": [],
            },
            {
                "doc_type": DOC_DEBT_SERVICE_REPORT,
                "document_id": "REPORT-2029",
                "settled_count": 0,
                "outstanding_count": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control
# --------------------------------------------------------------------------- #
def _missing_document(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_DEBT_SERVICE_REPORT
    ]


def _duplicate_note_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_NOTE_REGISTER)
    assert register is not None
    register["notes"].append(dict(_note(payload, "NR-1401")))


def _note_missing_field(payload: dict[str, Any]) -> None:
    del _note(payload, "NR-1404")["lender_entity"]


def _bad_day_count(payload: dict[str, Any]) -> None:
    _note(payload, "NR-1402")["day_count_denom"] = 364


def _same_entity(payload: dict[str, Any]) -> None:
    note = _note(payload, "NR-1403")
    note["borrower_entity"] = note["lender_entity"]


def _row_missing_field(payload: dict[str, Any]) -> None:
    del _rows(payload, "NR-1401")[0]["days"]


def _day_count_mismatch(payload: dict[str, Any]) -> None:
    # Stretch the final period's end date without touching its stated day count,
    # so the day count no longer ties the span while the accrual (which reads the
    # stated day count) still re-derives.
    _rows(payload, "NR-1401")[-1]["period_end"] = "2029-08-10"


def _accrual_wrong(payload: dict[str, Any]) -> None:
    _rows(payload, "NR-1401")[-1]["accrued_cents"] += d(10)


def _orphan_row(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_ROLLFORWARD)
    assert schedule is not None
    schedule["rows"].append(
        {
            "note_id": "NR-9999",
            "period_start": "2029-06-01",
            "period_end": "2029-07-01",
            "days": 30,
            "rate_bps": 700,
            "beginning_cents": d(500_000),
            "advance_cents": 0,
            "accrued_cents": 0,
            "payment_cents": 0,
            "ending_cents": d(500_000),
        }
    )


def _ending_wrong(payload: dict[str, Any]) -> None:
    _rows(payload, "NR-1401")[0]["ending_cents"] += d(5)


def _continuity_break(payload: dict[str, Any]) -> None:
    _rows(payload, "NR-1401")[-1]["beginning_cents"] += d(5)


def _opening_mismatch(payload: dict[str, Any]) -> None:
    _note(payload, "NR-1402")["principal_cents"] -= d(10)


def _rate_step_wrong(payload: dict[str, Any]) -> None:
    # The first period is before the event of default and should accrue at the
    # stated rate; overwrite it with the default rate.
    _rows(payload, "NR-1405")[0]["rate_bps"] = 1200


def _accrual_past_maturity(payload: dict[str, Any]) -> None:
    # Pull the maturity date back so an existing accruing period now begins after
    # it, while the note stays out of the maturity window (already past due).
    _note(payload, "NR-1401")["maturity_date"] = "2029-06-15"


def _early_prepayment(payload: dict[str, Any]) -> None:
    row = _rows(payload, "NR-1403")[0]
    row["payment_cents"] = row["accrued_cents"] + d(50_000)


def _maturity_approaching(payload: dict[str, Any]) -> None:
    # An unsettled note whose maturity is pulled inside the lead-time window; the
    # rollup is re-derived so only the maturity FLAG remains.
    _note(payload, "NR-1401")["maturity_date"] = "2029-11-15"
    rederive(payload)


def _overpayment(payload: dict[str, Any]) -> None:
    _rows(payload, "NR-1401")[-1]["payment_cents"] += d(10_000_000)


def _payoff_residual(payload: dict[str, Any]) -> None:
    # The payoff leaves a residual instead of settling to zero; re-derive so the
    # summary and reciprocal figures follow and only the payoff control fires.
    final = _final(payload, "NR-1403")
    final["payment_cents"] -= d(5_000)
    final["ending_cents"] += d(5_000)
    rederive(payload)


def _subordination_breach(payload: dict[str, Any]) -> None:
    row = _rows(payload, "NR-1405")[0]
    row["payment_cents"] = row["accrued_cents"] + d(50_000)


def _receivable_break(payload: dict[str, Any]) -> None:
    _tb_row(payload, _note(payload, "NR-1401")["np_account"])["balance_cents"] += d(10_000)


def _income_expense_break(payload: dict[str, Any]) -> None:
    _tb_row(payload, _note(payload, "NR-1402")["income_account"])["balance_cents"] += d(10_000)


def _journal_unbalanced(payload: dict[str, Any]) -> None:
    # Inflate one credit line without a matching debit; the entry no longer proves.
    for line in _journal(payload)["lines"]:
        if line["credit_cents"] > 0:
            line["credit_cents"] += d(10_000)
            return


def _journal_off_accrual(payload: dict[str, Any]) -> None:
    # Inflate a matched debit/credit pair so the entry still balances but overstates
    # the interest it books relative to the accrual.
    lines = _journal(payload)["lines"]
    debit = next(line for line in lines if line["debit_cents"] > 0)
    credit = next(line for line in lines if line["credit_cents"] > 0)
    debit["debit_cents"] += d(10_000)
    credit["credit_cents"] += d(10_000)


def _note_off_tb(payload: dict[str, Any]) -> None:
    account = _note(payload, "NR-1404")["np_account"]
    tb = _doc(payload, DOC_TRIAL_BALANCE)
    assert tb is not None
    tb["accounts"] = [row for row in tb["accounts"] if row.get("account") != account]


def _orphan_tb_account(payload: dict[str, Any]) -> None:
    tb = _doc(payload, DOC_TRIAL_BALANCE)
    assert tb is not None
    tb["accounts"].append(
        {"account": "8-808-8888", "note_id": None, "kind": TB_KIND_NR, "balance_cents": d(250_000)}
    )


def _settled_flag_wrong(payload: dict[str, Any]) -> None:
    # The stated determination contradicts the schedule; the count is moved with it
    # so only the recompute control sees the break.
    _summary_row(payload, "NR-1403")["settled"] = False
    report = _report(payload)
    report["settled_count"] -= 1
    report["outstanding_count"] += 1


def _report_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["settled_count"] += 1


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {"note_id": "NR-1402", "maturity_date": "2031-12-31", "days_remaining": 821}
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _rows(payload, "NR-1401")[0]
    row["beginning_cents"] = float(row["beginning_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_document": ("set_complete", _missing_document),
    "duplicate_note_id": ("note_unique_ids", _duplicate_note_id),
    "note_missing_field": ("note_required_fields", _note_missing_field),
    "bad_day_count": ("note_terms_valid", _bad_day_count),
    "same_entity": ("note_entities_distinct", _same_entity),
    "row_missing_field": ("acc_row_fields_present", _row_missing_field),
    "day_count_mismatch": ("acc_day_count_ties", _day_count_mismatch),
    "accrual_wrong": ("acc_interest_rederives", _accrual_wrong),
    "orphan_row": ("rf_row_note_exists", _orphan_row),
    "ending_wrong": ("rf_ending_balance_rederives", _ending_wrong),
    "continuity_break": ("rf_continuity", _continuity_break),
    "opening_mismatch": ("rf_opening_ties_principal", _opening_mismatch),
    "rate_step_wrong": ("gate_rate_step", _rate_step_wrong),
    "accrual_past_maturity": ("gate_maturity_stop", _accrual_past_maturity),
    "early_prepayment": ("gate_no_prepayment", _early_prepayment),
    "maturity_approaching": ("gate_maturity_approaching", _maturity_approaching),
    "overpayment": ("wf_payment_within_balance", _overpayment),
    "payoff_residual": ("wf_final_settles_zero", _payoff_residual),
    "subordination_breach": ("wf_subordination_order", _subordination_breach),
    "receivable_break": ("recip_nr_np_equal", _receivable_break),
    "income_expense_break": ("recip_income_expense_equal", _income_expense_break),
    "journal_unbalanced": ("gl_journal_balances", _journal_unbalanced),
    "journal_off_accrual": ("gl_journal_ties_accrual", _journal_off_accrual),
    "note_off_tb": ("gl_note_on_tb", _note_off_tb),
    "orphan_tb_account": ("gl_tb_complete", _orphan_tb_account),
    "settled_flag_wrong": ("rpt_note_settled_recomputes", _settled_flag_wrong),
    "report_count_wrong": ("rpt_report_count_ties", _report_count_wrong),
    "watchlist_overstated": ("rpt_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("acc_interest_rederives", _amount_not_integer),
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
