"""
Interest-accrual & loan-amortization control engine (READ-ONLY).
================================================================

Loads each loan file (a ``.json`` file produced by
:mod:`interest_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether a note's schedule proves itself** -- whether the
interest it reports is the interest its terms produce, whether the balance rolls
forward, whether the gates hold, and whether the two GL sides reconcile. Where a
financing cost lands or how a construction draw is funded are separate engines'
jobs. This engine is the arithmetic proof underneath the debt-service note.

The shape of the problem
------------------------
A lender carries notes receivable and interest income; the reciprocal borrower
carries notes payable and interest expense; and every period somebody accrues
interest, rolls the balance forward, and posts a journal entry.

Four failures hide inside that, and none of them look wrong in a column of
numbers: the accrual struck at the wrong rate, balance or day count; the
roll-forward whose ending is not the next beginning, or whose payoff leaves a
residual; the gate nobody enforced -- accrual past maturity, a default rate that
never stepped, an early prepayment, a subordinated note paid ahead of its senior;
and the two sides that quietly stopped reconciling.

The registry is organised around that:

1. ``set_``   -- is the loan file complete?
2. ``note_``  -- is the note register sound, and are each note's terms well-formed?
3. ``acc_``   -- does every period's accrued interest re-derive from the terms?
4. ``rf_``    -- does the balance roll forward, row to row, begin to end?
5. ``gate_``  -- do the maturity, rate-step and prepayment gates hold?
6. ``wf_``    -- does the payment waterfall and subordination ordering hold?
7. ``recip_`` -- do the reciprocal receivable/payable and income/expense agree?
8. ``gl_``    -- does the journal balance, tie the accrual, and cover every note?
9. ``rpt_``   -- do the rollups recompute from the schedule they summarise?

Design notes
------------
- **Strictly read-only.** Loan files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every balance and accrual is compared with
  exact ``==``/``>=``.
- **One accrual kernel.** Controls and the generator share the arithmetic in
  :mod:`interest_engine.accrual`, so a re-derivation cannot disagree with the
  data that produced it.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.
"""

from __future__ import annotations

import contextlib
import functools
import json
import re
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from .accrual import (
    accrued_interest,
    ending_balance,
    period_rate_bps,
    reduces_principal,
    within_maturity_window,
)
from .model import (
    DAY_COUNT_DENOMINATORS,
    DOC_DEBT_SERVICE_REPORT,
    DOC_INTEREST_JOURNAL,
    DOC_INTEREST_SUMMARY,
    DOC_MATURITY_WATCHLIST,
    DOC_NOTE_REGISTER,
    DOC_ROLLFORWARD,
    DOC_TRIAL_BALANCE,
    DOC_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~interest_engine.money.AmountInvalidError` as a finding."""
    return Finding(
        rule_id,
        SEVERITY.get(rule_id, Status.FAIL),
        f"amount:{exc.field}",
        f"{exc} -- amounts are integer cents and are never coerced",
    )


@contextlib.contextmanager
def amount_guard(rule_id: str, out: list[Finding]) -> Iterator[None]:
    """Contain a malformed amount to the one row being read."""
    try:
        yield
    except AmountInvalidError as exc:
        out.append(amount_invalid_finding(rule_id, exc))


def check(rule_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register ``fn`` in :data:`REGISTRY` under ``rule_id``."""

    def wrapper(fn: CheckFn) -> CheckFn:
        @functools.wraps(fn)
        def guarded(ctx: Context) -> list[Finding]:
            try:
                return fn(ctx)
            except AmountInvalidError as exc:
                return [amount_invalid_finding(rule_id, exc)]

        REGISTRY.append((rule_id, guarded))
        return guarded

    return wrapper


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sev(rule_id: str, status: Status) -> Status:
    SEVERITY[rule_id] = status
    return status


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _rows(doc: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    rows = doc.get(key)
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) and value else None


def _int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# --------------------------------------------------------------------------- #
# Loan-file helpers
# --------------------------------------------------------------------------- #
def _notes(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_NOTE_REGISTER), "notes")


def _note_id(row: dict[str, Any]) -> str:
    value = row.get("note_id")
    return value if isinstance(value, str) and value else "?"


def _note_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _notes(ctx):
        nid = _note_id(row)
        if nid != "?" and nid not in out:
            out[nid] = row
    return out


def _schedule_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ROLLFORWARD), "rows")


def _rows_for(ctx: Context, note_id: str) -> list[dict[str, Any]]:
    """Every schedule row of one note, ordered by (period_start, period_end).

    Ordering reads only the two dates, never an amount, so assembling a note's
    schedule cannot itself raise on a malformed balance -- the balances are read
    later, by the control that needs them.
    """
    dated: list[tuple[date, date, int, dict[str, Any]]] = []
    for i, row in enumerate(_schedule_rows(ctx)):
        if _text(row, "note_id") != note_id:
            continue
        start = _parse_date(row.get("period_start"))
        end = _parse_date(row.get("period_end"))
        if start is None or end is None:
            continue
        dated.append((start, end, i, row))
    dated.sort(key=lambda t: (t[0], t[1], t[2]))
    return [t[3] for t in dated]


def _final_row(ctx: Context, note_id: str) -> dict[str, Any] | None:
    ordered = _rows_for(ctx, note_id)
    return ordered[-1] if ordered else None


def _tb_accounts(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TRIAL_BALANCE), "accounts")


def _tb_by_account(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _tb_accounts(ctx):
        acct = _text(row, "account")
        if acct and acct not in out:
            out[acct] = row
    return out


def _journal_lines(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_INTEREST_JOURNAL), "lines")


# --------------------------------------------------------------------------- #
# Shared recompute spine (imported by the generator too)
# --------------------------------------------------------------------------- #
def recompute_accrued_total(ctx: Context, note_id: str) -> int:
    """Sum the accrued interest across a note's schedule rows.

    Raises :class:`AmountInvalidError` if an accrued figure it must read is not
    integer cents; the calling control contains that to the note being read.
    """
    total = 0
    for row in _rows_for(ctx, note_id):
        total += require_cents(
            f"row[{note_id}/{row.get('period_end')}].accrued_cents",
            row.get("accrued_cents"),
        )
    return total


def recompute_settled(ctx: Context, note_id: str) -> bool:
    """Whether a note is settled: its final row's ending balance is exactly zero.

    A note with no schedule rows is not settled. Raises
    :class:`AmountInvalidError` if the final ending balance is not integer cents.
    """
    final = _final_row(ctx, note_id)
    if final is None:
        return False
    ending = require_cents(
        f"row[{note_id}].ending_cents", final.get("ending_cents")
    )
    return ending == 0


def recompute_maturity_watchlist(
    ctx: Context, as_of: date, lead_days: int
) -> list[dict[str, Any]]:
    """The maturity watchlist re-derived from the note terms and schedule.

    One entry per note that is **not** settled and whose maturity falls inside the
    lead-time window. Reads no amounts except through :func:`recompute_settled`, so
    a malformed balance surfaces there rather than here.
    """
    entries: list[dict[str, Any]] = []
    for note in _notes(ctx):
        nid = _note_id(note)
        maturity = _parse_date(note.get("maturity_date"))
        if maturity is None:
            continue
        if recompute_settled(ctx, nid):
            continue
        if within_maturity_window(maturity, as_of, lead_days):
            entries.append(
                {
                    "note_id": nid,
                    "maturity_date": note.get("maturity_date"),
                    "days_remaining": (maturity - as_of).days,
                }
            )
    entries.sort(key=lambda e: (e["maturity_date"], e["note_id"]))
    return entries


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("note_id"),
        entry.get("maturity_date"),
        entry.get("days_remaining"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the loan file depends on is present, exactly once.

    This runs first and deliberately owns the "missing artifact" finding. A
    control that silently passes because its input is absent is worse than no
    control: it reports assurance it never performed.
    """
    rule = "set_complete"
    _sev(rule, Status.FAIL)
    out: list[Finding] = []
    for doc_type in DOC_TYPES:
        found = ctx.docs(doc_type)
        if not found:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"{doc_type} is missing; the controls that read it cannot run and "
                    f"must not be reported as having passed",
                )
            )
        elif len(found) > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"{len(found)} {doc_type} documents present; the loan file carries "
                    f"exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} loan-file artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every maturity and gate "
                f"test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# note_ -- the note register and each note's terms
# --------------------------------------------------------------------------- #
@check("note_unique_ids")
def check_note_unique_ids(ctx: Context) -> list[Finding]:
    """No note id appears twice.

    The note id joins the register to every schedule row, GL account and summary
    line. A duplicate makes a row ambiguous about which note it rolls forward.
    """
    rule = "note_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_NOTE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _notes(ctx):
        seen[_note_id(row)] = seen.get(_note_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"notes/{nid}"),
            f"note id {nid} appears {count} times; a schedule row that names it cannot "
            f"be attributed to one note",
        )
        for nid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} note ids are unique")
        )
    return out


@check("note_required_fields")
def check_note_required_fields(ctx: Context) -> list[Finding]:
    """Every note carries the descriptive term fields the controls read."""
    rule = "note_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_NOTE_REGISTER)
    if register is None:
        return []
    required = (
        "note_id",
        "lender_entity",
        "borrower_entity",
        "maturity_date",
        "nr_account",
        "np_account",
        "income_account",
        "expense_account",
    )
    out: list[Finding] = []
    for row in _notes(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"notes/{_note_id(row)}"),
                    f"note {_note_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_notes(ctx))} notes carry their required term fields",
            )
        )
    return out


@check("note_terms_valid")
def check_note_terms_valid(ctx: Context) -> list[Finding]:
    """Each note's rate, day-count and principal are economically well-formed.

    A negative rate, a default rate below the stated rate, a non-positive
    principal or an unknown day-count denominator has no defined accrual, so the
    re-derivation below would either be meaningless or silently skip the note.
    """
    rule = "note_terms_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_NOTE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _notes(ctx):
        nid = _note_id(row)
        with amount_guard(rule, out):
            principal = require_cents(
                f"note[{nid}].principal_cents", row.get("principal_cents")
            )
            stated = require_cents(
                f"note[{nid}].stated_rate_bps",
                row.get("stated_rate_bps"),
                unit="an integer basis-point rate",
            )
            default = require_cents(
                f"note[{nid}].default_rate_bps",
                row.get("default_rate_bps"),
                unit="an integer basis-point rate",
            )
            denom = _int(row, "day_count_denom")
            if principal <= 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"notes/{nid}/principal_cents"),
                        f"note {nid} states principal {fmt(principal)}; a note accrues on "
                        f"a positive balance",
                    )
                )
            if stated < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"notes/{nid}/stated_rate_bps"),
                        f"note {nid} states a negative rate of {stated} bps",
                    )
                )
            if default < stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"notes/{nid}/default_rate_bps"),
                        f"note {nid} default rate {default} bps is below its stated rate "
                        f"{stated} bps; the default rate steps up, never down",
                    )
                )
            if denom not in DAY_COUNT_DENOMINATORS:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"notes/{nid}/day_count_denom"),
                        f"note {nid} states day-count denominator {denom!r}, not one of "
                        f"{DAY_COUNT_DENOMINATORS}; its accrual year is undefined",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_notes(ctx))} notes carry well-formed terms"
            )
        )
    return out


@check("note_entities_distinct")
def check_note_entities_distinct(ctx: Context) -> list[Finding]:
    """A note's lender and borrower are two different entities.

    A note to oneself has no reciprocal side to tie out: the receivable and the
    payable would sit on one entity's books, and interest income would net its own
    expense to nothing.
    """
    rule = "note_entities_distinct"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_NOTE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _notes(ctx):
        lender = _text(row, "lender_entity")
        borrower = _text(row, "borrower_entity")
        if lender and borrower and lender == borrower:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"notes/{_note_id(row)}/borrower_entity"),
                    f"note {_note_id(row)} names {lender!r} as both lender and borrower; a "
                    f"note has two sides",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_notes(ctx))} notes have distinct sides"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# acc_ -- the accrual re-derives from the terms
# --------------------------------------------------------------------------- #
@check("acc_row_fields_present")
def check_acc_row_fields_present(ctx: Context) -> list[Finding]:
    """Every schedule row carries the note id, both period dates and the day count.

    Without them a row cannot be attributed, ordered, or day-counted, so the
    accrual and roll-forward controls below would skip it and pass vacuously. The
    integer balances are read later, guarded, by the controls that need them.
    """
    rule = "acc_row_fields_present"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    out: list[Finding] = []
    for i, row in enumerate(_schedule_rows(ctx)):
        problems: list[str] = []
        if not _text(row, "note_id"):
            problems.append("note_id")
        if _parse_date(row.get("period_start")) is None:
            problems.append("period_start")
        if _parse_date(row.get("period_end")) is None:
            problems.append("period_end")
        if _int(row, "days") is None:
            problems.append("days")
        if _int(row, "rate_bps") is None:
            problems.append("rate_bps")
        if problems:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"rows/{i}"),
                    f"schedule row {i} ({_text(row, 'note_id') or '?'}) is missing or "
                    f"malformed: {', '.join(problems)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_schedule_rows(ctx))} schedule rows carry their key fields",
            )
        )
    return out


@check("acc_day_count_ties")
def check_acc_day_count_ties(ctx: Context) -> list[Finding]:
    """Each row's stated day count equals its own period span.

    The day count feeds the accrual directly, so a row that claims more days than
    its dates span accrues more interest than the period earned -- and the accrual
    still re-derives, because it re-derives against the very day count that is
    wrong.
    """
    rule = "acc_day_count_ties"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for i, row in enumerate(_schedule_rows(ctx)):
        start = _parse_date(row.get("period_start"))
        end = _parse_date(row.get("period_end"))
        days = _int(row, "days")
        if start is None or end is None or days is None:
            continue  # acc_row_fields_present owns this
        checked += 1
        span = (end - start).days
        if days != span:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"rows/{i}/days"),
                    f"row {i} ({_text(row, 'note_id')}) states {days} day(s) but "
                    f"{start.isoformat()}..{end.isoformat()} spans {span}; the accrual "
                    f"day count does not tie the period",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} rows' day counts tie their period span"
            )
        )
    return out


@check("acc_interest_rederives")
def check_acc_interest_rederives(ctx: Context) -> list[Finding]:
    """Each period's accrued interest re-derives from beginning x rate x days.

    The control the engine exists for. Interest is rebuilt through the shared
    kernel -- ``beginning x rate_bps x days / year``, truncated to the cent -- and
    compared with exact ``==``. A cent of drift here is a cent the note either
    over- or under-charged.
    """
    rule = "acc_interest_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    notes = _note_map(ctx)
    out: list[Finding] = []
    checked = 0
    for i, row in enumerate(_schedule_rows(ctx)):
        nid = _text(row, "note_id")
        note = notes.get(nid or "")
        if note is None:
            continue  # rf_row_note_exists owns an orphan row
        days = _int(row, "days")
        rate = _int(row, "rate_bps")
        denom = _int(note, "day_count_denom")
        if days is None or rate is None or denom not in DAY_COUNT_DENOMINATORS:
            continue  # acc_row_fields_present / note_terms_valid own these
        with amount_guard(rule, out):
            beginning = require_cents(
                f"row[{nid}/{row.get('period_end')}].beginning_cents",
                row.get("beginning_cents"),
            )
            accrued = require_cents(
                f"row[{nid}/{row.get('period_end')}].accrued_cents",
                row.get("accrued_cents"),
            )
            checked += 1
            expected = accrued_interest(beginning, rate, days, denom)
            if accrued != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"rows/{i}/accrued_cents"),
                        f"row {i} ({nid}) books {fmt(accrued)} accrued on {fmt(beginning)} "
                        f"at {rate} bps for {days} day(s); re-deriving gives "
                        f"{fmt(expected)} (off {fmt(accrued - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} accruals re-derive from the note terms"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rf_ -- the balance rolls forward
# --------------------------------------------------------------------------- #
@check("rf_row_note_exists")
def check_rf_row_note_exists(ctx: Context) -> list[Finding]:
    """Every schedule row names a note in the register."""
    rule = "rf_row_note_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    notes = _note_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"rows/{i}/note_id"),
            f"schedule row {i} names note {_text(row, 'note_id')!r}, which is not in the "
            f"note register",
        )
        for i, row in enumerate(_schedule_rows(ctx))
        if _text(row, "note_id") and _text(row, "note_id") not in notes
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every schedule row names a note in the register")
        )
    return out


@check("rf_ending_balance_rederives")
def check_rf_ending_balance_rederives(ctx: Context) -> list[Finding]:
    """Each row's ending balance rebuilds from begin + advance + accrued - payment.

    The roll-forward identity, checked row by row with exact ``==``. A row whose
    ending does not rebuild has an advance that never landed, a payment that never
    posted, or a keying error -- and every balance after it inherits the break.
    """
    rule = "rf_ending_balance_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for i, row in enumerate(_schedule_rows(ctx)):
        nid = _text(row, "note_id")
        with amount_guard(rule, out):
            beginning = require_cents(f"row[{i}].beginning_cents", row.get("beginning_cents"))
            advance = require_cents(f"row[{i}].advance_cents", row.get("advance_cents"))
            accrued = require_cents(f"row[{i}].accrued_cents", row.get("accrued_cents"))
            payment = require_cents(f"row[{i}].payment_cents", row.get("payment_cents"))
            ending = require_cents(f"row[{i}].ending_cents", row.get("ending_cents"))
            checked += 1
            expected = ending_balance(beginning, advance, accrued, payment)
            if ending != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"rows/{i}/ending_cents"),
                        f"row {i} ({nid}) ends {fmt(ending)}; "
                        f"{fmt(beginning)} + {fmt(advance)} + {fmt(accrued)} - "
                        f"{fmt(payment)} = {fmt(expected)} (off {fmt(ending - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} ending balances re-derive")
        )
    return out


@check("rf_continuity")
def check_rf_continuity(ctx: Context) -> list[Finding]:
    """Each period's ending balance is the next period's beginning balance.

    Both rows can be internally sound and the schedule still break between them:
    ending[t] must equal beginning[t+1], or a balance was silently reset between
    two periods and the accrual after it runs off the wrong number.
    """
    rule = "rf_continuity"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for nid in sorted(_note_map(ctx)):
        ordered = _rows_for(ctx, nid)
        for prior, following in zip(ordered, ordered[1:]):
            with amount_guard(rule, out):
                prior_end = require_cents(
                    f"row[{nid}/{prior.get('period_end')}].ending_cents",
                    prior.get("ending_cents"),
                )
                next_begin = require_cents(
                    f"row[{nid}/{following.get('period_end')}].beginning_cents",
                    following.get("beginning_cents"),
                )
                checked += 1
                if prior_end != next_begin:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"rows/{nid}/{following.get('period_end')}/beginning_cents"),
                            f"note {nid} ends period {prior.get('period_end')} at "
                            f"{fmt(prior_end)} but opens {following.get('period_end')} at "
                            f"{fmt(next_begin)}; the roll-forward is broken",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} period handovers are continuous")
        )
    return out


@check("rf_opening_ties_principal")
def check_rf_opening_ties_principal(ctx: Context) -> list[Finding]:
    """Each note's first period opens at its stated principal.

    The schedule has to start from the note itself: the earliest row's beginning
    balance must equal the principal on the register, or the whole roll-forward is
    built on a number the note never advanced.
    """
    rule = "rf_opening_ties_principal"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    note_reg = ctx.one(DOC_NOTE_REGISTER)
    if register is None or note_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        nid = _note_id(note)
        ordered = _rows_for(ctx, nid)
        if not ordered:
            continue  # a note with no schedule is left to rpt_/completeness
        with amount_guard(rule, out):
            principal = require_cents(
                f"note[{nid}].principal_cents", note.get("principal_cents")
            )
            opening = require_cents(
                f"row[{nid}].beginning_cents", ordered[0].get("beginning_cents")
            )
            checked += 1
            if opening != principal:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"rows/{nid}/opening/beginning_cents"),
                        f"note {nid} opens its schedule at {fmt(opening)}; the register "
                        f"states principal {fmt(principal)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} notes open at their principal")
        )
    return out


# --------------------------------------------------------------------------- #
# gate_ -- maturity, rate-step and prepayment gates
# --------------------------------------------------------------------------- #
@check("gate_rate_step")
def check_gate_rate_step(ctx: Context) -> list[Finding]:
    """Each row accrues at the rate its note's terms dictate for that period.

    The rate steps to the default rate on and after an event of default and holds
    at the stated rate before it. A row carrying the wrong rate accrues the wrong
    interest, and because the accrual re-derives against that same wrong rate the
    only place the error shows is here.
    """
    rule = "gate_rate_step"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    notes = _note_map(ctx)
    out: list[Finding] = []
    checked = 0
    for i, row in enumerate(_schedule_rows(ctx)):
        nid = _text(row, "note_id")
        note = notes.get(nid or "")
        if note is None:
            continue
        start = _parse_date(row.get("period_start"))
        rate = _int(row, "rate_bps")
        stated = _int(note, "stated_rate_bps")
        default = _int(note, "default_rate_bps")
        if start is None or rate is None or stated is None or default is None:
            continue  # note_terms_valid / acc_row_fields_present own these
        event = _parse_date(note.get("default_event_date"))
        checked += 1
        expected = period_rate_bps(stated, default, start, event)
        if rate != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"rows/{i}/rate_bps"),
                    f"row {i} ({nid}) starting {start.isoformat()} accrues at {rate} bps; "
                    f"the note's terms call for {expected} bps"
                    + (f" (default rate stepped in {event.isoformat()})" if event else ""),
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} rows accrue at the correct rate")
        )
    return out


@check("gate_maturity_stop")
def check_gate_maturity_stop(ctx: Context) -> list[Finding]:
    """No interest accrues on a period that begins on or after maturity.

    Accrual stops at maturity. A period whose start is at or past the maturity
    date and still books interest is accruing on a note that has already come due.
    """
    rule = "gate_maturity_stop"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    notes = _note_map(ctx)
    out: list[Finding] = []
    checked = 0
    for i, row in enumerate(_schedule_rows(ctx)):
        nid = _text(row, "note_id")
        note = notes.get(nid or "")
        if note is None:
            continue
        start = _parse_date(row.get("period_start"))
        maturity = _parse_date(note.get("maturity_date"))
        if start is None or maturity is None:
            continue
        if start < maturity:
            continue
        checked += 1
        with amount_guard(rule, out):
            accrued = require_cents(f"row[{i}].accrued_cents", row.get("accrued_cents"))
            if accrued != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"rows/{i}/accrued_cents"),
                        f"row {i} ({nid}) accrues {fmt(accrued)} on a period beginning "
                        f"{start.isoformat()}, on or after maturity "
                        f"{maturity.isoformat()}; accrual should have stopped",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} post-maturity rows accrue nothing"
            )
        )
    return out


@check("gate_no_prepayment")
def check_gate_no_prepayment(ctx: Context) -> list[Finding]:
    """A note that prohibits prepayment is not paid down before maturity.

    Where the note bars prepayment, no period ending before the maturity date may
    carry a payment that relieves principal (a payment above that period's accrued
    interest). Interest service is fine; principal reduction ahead of maturity is
    the prohibited act.
    """
    rule = "gate_no_prepayment"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    notes = _note_map(ctx)
    out: list[Finding] = []
    checked = 0
    for i, row in enumerate(_schedule_rows(ctx)):
        nid = _text(row, "note_id")
        note = notes.get(nid or "")
        if note is None:
            continue
        if bool(note.get("prepayment_allowed")):
            continue
        end = _parse_date(row.get("period_end"))
        maturity = _parse_date(note.get("maturity_date"))
        if end is None or maturity is None or end >= maturity:
            continue
        checked += 1
        with amount_guard(rule, out):
            accrued = require_cents(f"row[{i}].accrued_cents", row.get("accrued_cents"))
            payment = require_cents(f"row[{i}].payment_cents", row.get("payment_cents"))
            if reduces_principal(payment, accrued):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"rows/{i}/payment_cents"),
                        f"note {nid} bars prepayment, yet row {i} pays {fmt(payment)} against "
                        f"{fmt(accrued)} accrued on {end.isoformat()}, before maturity "
                        f"{maturity.isoformat()}; {fmt(payment - accrued)} reduces principal",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} pre-maturity payments service interest only"
            )
        )
    return out


@check("gate_maturity_approaching")
def check_gate_maturity_approaching(ctx: Context) -> list[Finding]:
    """An unsettled note maturing inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the note is still current, but the payoff
    or extension needs to be arranged before it comes due. The window comes from
    the file's own ``maturity_lead_days``.
    """
    rule = "gate_maturity_approaching"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_NOTE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    lead = ctx.maturity_lead_days
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        nid = _note_id(note)
        maturity = _parse_date(note.get("maturity_date"))
        if maturity is None:
            continue
        with amount_guard(rule, out):
            if recompute_settled(ctx, nid):
                continue
            checked += 1
            if within_maturity_window(maturity, as_of, lead):
                remaining = (maturity - as_of).days
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"notes/{nid}/maturity_date"),
                        f"note {nid} matures {maturity.isoformat()}, in {remaining} day(s); "
                        f"inside the {lead}-day window and due to be refinanced or repaid",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} unsettled notes mature outside the lead-time window",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# wf_ -- payment waterfall and subordination ordering
# --------------------------------------------------------------------------- #
@check("wf_payment_within_balance")
def check_wf_payment_within_balance(ctx: Context) -> list[Finding]:
    """No period pays more than the balance owed in it.

    A payment may relieve at most the beginning balance plus the period's advance
    and accrued interest. Anything above that is money leaving against a debt that
    was not there, and it drives the ending balance negative.
    """
    rule = "wf_payment_within_balance"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for i, row in enumerate(_schedule_rows(ctx)):
        nid = _text(row, "note_id")
        with amount_guard(rule, out):
            beginning = require_cents(f"row[{i}].beginning_cents", row.get("beginning_cents"))
            advance = require_cents(f"row[{i}].advance_cents", row.get("advance_cents"))
            accrued = require_cents(f"row[{i}].accrued_cents", row.get("accrued_cents"))
            payment = require_cents(f"row[{i}].payment_cents", row.get("payment_cents"))
            checked += 1
            available = beginning + advance + accrued
            if payment > available:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"rows/{i}/payment_cents"),
                        f"row {i} ({nid}) pays {fmt(payment)} against {fmt(available)} owed "
                        f"({fmt(beginning)} + {fmt(advance)} + {fmt(accrued)}); "
                        f"{fmt(payment - available)} overpays the balance",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} payments are within the balance owed")
        )
    return out


@check("wf_final_settles_zero")
def check_wf_final_settles_zero(ctx: Context) -> list[Finding]:
    """A note scheduled to be paid off settles to exactly zero.

    Where a note carries ``payoff_expected``, its final period must close the
    balance to nothing -- not a residual cent, not a negative. A payoff that leaves
    a balance behind has under-relieved the note; one that goes negative has
    over-paid it.
    """
    rule = "wf_final_settles_zero"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    note_reg = ctx.one(DOC_NOTE_REGISTER)
    if register is None or note_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        if not bool(note.get("payoff_expected")):
            continue
        nid = _note_id(note)
        final = _final_row(ctx, nid)
        if final is None:
            continue
        with amount_guard(rule, out):
            ending = require_cents(f"row[{nid}].ending_cents", final.get("ending_cents"))
            checked += 1
            if ending != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"rows/{nid}/final/ending_cents"),
                        f"note {nid} is scheduled to pay off, yet its final period ends at "
                        f"{fmt(ending)} instead of settling to zero",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} payoff notes settle to zero")
        )
    return out


@check("wf_subordination_order")
def check_wf_subordination_order(ctx: Context) -> list[Finding]:
    """A subordinated note is not paid down while its senior is unrepaid.

    Where a note sits behind a senior note, no period may reduce the subordinate's
    principal until the senior is settled. Interest may still be serviced; it is
    principal ahead of the senior that the waterfall forbids.
    """
    rule = "wf_subordination_order"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ROLLFORWARD)
    note_reg = ctx.one(DOC_NOTE_REGISTER)
    if register is None or note_reg is None:
        return []
    notes = _note_map(ctx)
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        senior_id = _text(note, "subordinated_to")
        if not senior_id:
            continue
        nid = _note_id(note)
        with amount_guard(rule, out):
            senior_settled = senior_id in notes and recompute_settled(ctx, senior_id)
            if senior_settled:
                continue
            for i, row in enumerate(_rows_for(ctx, nid)):
                accrued = require_cents(
                    f"row[{nid}/{row.get('period_end')}].accrued_cents",
                    row.get("accrued_cents"),
                )
                payment = require_cents(
                    f"row[{nid}/{row.get('period_end')}].payment_cents",
                    row.get("payment_cents"),
                )
                checked += 1
                if reduces_principal(payment, accrued):
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"rows/{nid}/{row.get('period_end')}/payment_cents"),
                            f"note {nid} is subordinated to {senior_id}, which is not repaid, "
                            f"yet it pays {fmt(payment)} against {fmt(accrued)} accrued on "
                            f"{row.get('period_end')}; {fmt(payment - accrued)} reduces "
                            f"principal ahead of the senior",
                        )
                    )
                    break
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} subordinate payments respect the senior's priority",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# recip_ -- the two sides reconcile
# --------------------------------------------------------------------------- #
def _tb_balance(ctx: Context, account: str | None) -> int | None:
    """Read one trial-balance account's balance, or ``None`` if it is absent.

    Raises :class:`AmountInvalidError` if the account is present but its balance
    is not integer cents.
    """
    if not account:
        return None
    row = _tb_by_account(ctx).get(account)
    if row is None:
        return None
    return require_cents(f"trial_balance[{account}].balance_cents", row.get("balance_cents"))


@check("recip_nr_np_equal")
def check_recip_nr_np_equal(ctx: Context) -> list[Finding]:
    """Each note's receivable balance equals its payable balance and its schedule.

    The lender's notes-receivable and the borrower's notes-payable are the same
    debt seen from two sides; they must equal each other and equal the note's own
    ending balance. When they drift, one side has recorded a payment or advance the
    other has not.
    """
    rule = "recip_nr_np_equal"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if tb is None:
        return []
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        nid = _note_id(note)
        nr_acct = _text(note, "nr_account")
        np_acct = _text(note, "np_account")
        with amount_guard(rule, out):
            nr = _tb_balance(ctx, nr_acct)
            np = _tb_balance(ctx, np_acct)
            if nr is None or np is None:
                continue  # gl_note_on_tb owns a missing account
            final = _final_row(ctx, nid)
            if final is None:
                continue
            ending = require_cents(f"row[{nid}].ending_cents", final.get("ending_cents"))
            checked += 1
            if not (nr == np == ending):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"accounts/{np_acct}/balance_cents"),
                        f"note {nid} carries receivable {fmt(nr)} and payable {fmt(np)} "
                        f"against a schedule balance of {fmt(ending)}; the two sides do not "
                        f"reconcile",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} notes' two sides reconcile")
        )
    return out


@check("recip_income_expense_equal")
def check_recip_income_expense_equal(ctx: Context) -> list[Finding]:
    """Each note's interest income equals its interest expense and its accrual.

    Interest income booked by the lender is interest expense booked by the
    borrower is the interest the schedule accrued. Any of the three out of step is
    a break in the reciprocal posting.
    """
    rule = "recip_income_expense_equal"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if tb is None:
        return []
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        nid = _note_id(note)
        inc_acct = _text(note, "income_account")
        exp_acct = _text(note, "expense_account")
        with amount_guard(rule, out):
            income = _tb_balance(ctx, inc_acct)
            expense = _tb_balance(ctx, exp_acct)
            if income is None or expense is None:
                continue  # gl_note_on_tb owns a missing account
            accrued = recompute_accrued_total(ctx, nid)
            checked += 1
            if not (income == expense == accrued):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"accounts/{exp_acct}/balance_cents"),
                        f"note {nid} books interest income {fmt(income)} and expense "
                        f"{fmt(expense)} against {fmt(accrued)} accrued; the reciprocal "
                        f"interest does not tie",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} notes' income and expense tie the accrual"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# gl_ -- the journal balances and the schedule is complete
# --------------------------------------------------------------------------- #
@check("gl_journal_balances")
def check_gl_journal_balances(ctx: Context) -> list[Finding]:
    """The interest journal entry is self-proving: total debits equal total credits.

    A journal entry that does not balance was never a journal entry; it is a note
    to post one. Debits and credits are summed and compared with exact ``==``.
    """
    rule = "gl_journal_balances"
    _sev(rule, Status.FAIL)
    journal = ctx.one(DOC_INTEREST_JOURNAL)
    if journal is None:
        return []
    out: list[Finding] = []
    debits = 0
    credits = 0
    with amount_guard(rule, out):
        for i, line in enumerate(_journal_lines(ctx)):
            debits += require_cents(f"line[{i}].debit_cents", line.get("debit_cents"))
            credits += require_cents(f"line[{i}].credit_cents", line.get("credit_cents"))
        if debits != credits:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(journal, "lines"),
                    f"the interest journal debits {fmt(debits)} and credits {fmt(credits)}; "
                    f"it is out of balance by {fmt(debits - credits)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the interest journal balances at {fmt(debits)}",
                )
            )
    return out


@check("gl_journal_ties_accrual")
def check_gl_journal_ties_accrual(ctx: Context) -> list[Finding]:
    """The journal's total interest equals the interest the schedules accrued.

    The monthly entry records the accrual, so the debits that book it must sum to
    the total interest re-derived across every note's schedule. A journal that no
    longer ties the accrual is recording a number the schedules do not support.
    """
    rule = "gl_journal_ties_accrual"
    _sev(rule, Status.FAIL)
    journal = ctx.one(DOC_INTEREST_JOURNAL)
    if journal is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        booked = 0
        for i, line in enumerate(_journal_lines(ctx)):
            booked += require_cents(f"line[{i}].debit_cents", line.get("debit_cents"))
        accrued = 0
        for nid in sorted(_note_map(ctx)):
            accrued += recompute_accrued_total(ctx, nid)
        if booked != accrued:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(journal, "lines"),
                    f"the interest journal books {fmt(booked)} of interest; the schedules "
                    f"accrue {fmt(accrued)} (off {fmt(booked - accrued)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the journal's {fmt(booked)} ties the accrued interest",
                )
            )
    return out


@check("gl_note_on_tb")
def check_gl_note_on_tb(ctx: Context) -> list[Finding]:
    """Every note's receivable and payable accounts appear on the trial balance.

    A note whose GL accounts are not on the trial balance cannot be tied out at
    all -- the reciprocal control has nothing to read -- so the completeness gate
    owns the missing account and reports it once.
    """
    rule = "gl_note_on_tb"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    note_reg = ctx.one(DOC_NOTE_REGISTER)
    if tb is None or note_reg is None:
        return []
    present = set(_tb_by_account(ctx))
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        nid = _note_id(note)
        for field_name in ("nr_account", "np_account", "income_account", "expense_account"):
            acct = _text(note, field_name)
            if not acct:
                continue  # note_required_fields owns a missing account field
            checked += 1
            if acct not in present:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"accounts/{acct}"),
                        f"note {nid} maps {field_name} to {acct}, which is not on the trial "
                        f"balance; the note cannot be tied out",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} note GL accounts are on the trial balance"
            )
        )
    return out


@check("gl_tb_complete")
def check_gl_tb_complete(ctx: Context) -> list[Finding]:
    """Every trial-balance account maps back to a note.

    The trial balance carries the note accounts and only the note accounts. An
    account on the trial balance that no note claims is an orphan balance -- a
    receivable or payable with no schedule behind it -- and it is exactly what a
    completeness sweep exists to catch.
    """
    rule = "gl_tb_complete"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    note_reg = ctx.one(DOC_NOTE_REGISTER)
    if tb is None or note_reg is None:
        return []
    claimed: set[str] = set()
    for note in _notes(ctx):
        for field_name in ("nr_account", "np_account", "income_account", "expense_account"):
            acct = _text(note, field_name)
            if acct:
                claimed.add(acct)
    out: list[Finding] = []
    checked = 0
    for row in _tb_accounts(ctx):
        acct = _text(row, "account")
        if not acct:
            continue
        checked += 1
        if acct not in claimed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(tb, f"accounts/{acct}"),
                    f"trial-balance account {acct} is claimed by no note; it is an orphan "
                    f"balance with no schedule behind it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} trial-balance accounts map to a note")
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollups recompute from the evidence
# --------------------------------------------------------------------------- #
@check("rpt_note_settled_recomputes")
def check_rpt_note_settled_recomputes(ctx: Context) -> list[Finding]:
    """Each note's stated settled flag and accrued total recompute from the schedule.

    The interest summary is a determination, and a determination that is not
    recomputed from the schedule is an assertion. The engine rebuilds each note's
    settled flag from its final ending balance and its accrued total from every
    row, and compares.
    """
    rule = "rpt_note_settled_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_INTEREST_SUMMARY)
    if summary is None:
        return []
    notes = _note_map(ctx)
    out: list[Finding] = []
    for row in _rows(summary, "notes"):
        nid = _text(row, "note_id")
        if nid is None or nid not in notes:
            continue
        stated_settled = row.get("settled")
        with amount_guard(rule, out):
            recomputed_settled = recompute_settled(ctx, nid)
            if recomputed_settled != stated_settled:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"notes/{nid}/settled"),
                        f"note {nid} is summarised settled={stated_settled}; recomputing "
                        f"from its schedule gives settled={recomputed_settled}",
                    )
                )
            recomputed_accrued = recompute_accrued_total(ctx, nid)
            stated_accrued = require_cents(
                f"summary[{nid}].accrued_total_cents", row.get("accrued_total_cents")
            )
            if recomputed_accrued != stated_accrued:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"notes/{nid}/accrued_total_cents"),
                        f"note {nid} is summarised at {fmt(stated_accrued)} accrued; "
                        f"recomputing from its schedule gives {fmt(recomputed_accrued)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every note's settled flag and accrued total recompute from its schedule",
            )
        )
    return out


@check("rpt_report_count_ties")
def check_rpt_report_count_ties(ctx: Context) -> list[Finding]:
    """The debt-service report's settled / outstanding counts tie the summary.

    The number that reaches a treasurer is a count, and a count maintained beside
    the summary rather than derived from it drifts the first time a note settles
    and nobody re-adds the column.
    """
    rule = "rpt_report_count_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_DEBT_SERVICE_REPORT)
    summary = ctx.one(DOC_INTEREST_SUMMARY)
    if report is None or summary is None:
        return []
    settled = 0
    outstanding = 0
    for row in _rows(summary, "notes"):
        value = row.get("settled")
        if value is True:
            settled += 1
        elif value is False:
            outstanding += 1
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_settled = require_cents(
            "debt_service_report.settled_count",
            report.get("settled_count"),
            unit="a whole count",
        )
        stated_outstanding = require_cents(
            "debt_service_report.outstanding_count",
            report.get("outstanding_count"),
            unit="a whole count",
        )
        if stated_settled != settled or stated_outstanding != outstanding:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "settled_count"),
                    f"the report states {stated_settled} settled / {stated_outstanding} "
                    f"outstanding; the interest summary recomputes {settled} / {outstanding}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report counts of {settled} / {outstanding} tie the summary",
                )
            )
    return out


@check("rpt_watchlist_ties")
def check_rpt_watchlist_ties(ctx: Context) -> list[Finding]:
    """The maturity watchlist ties the note evidence.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a note not actually due -- or omits one that is -- sends
    the refinancing chase to the wrong place. It is rebuilt from the note terms and
    schedule and compared.
    """
    rule = "rpt_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_MATURITY_WATCHLIST)
    as_of = _parse_date(ctx.as_of)
    if watchlist is None or as_of is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        recomputed = [
            _normalize_entry(e)
            for e in recompute_maturity_watchlist(ctx, as_of, ctx.maturity_lead_days)
        ]
        stated = [_normalize_entry(e) for e in _rows(watchlist, "entries")]
        want = sorted(recomputed)
        have = sorted(stated)
        if want != have:
            for entry in have:
                if entry not in want:
                    out.append(
                        Finding(
                            rule,
                            Status.FLAG,
                            ctx.loc(watchlist, f"entries/{entry[0]}"),
                            f"the watchlist lists note {entry[0]} as maturing soon, but it is "
                            f"not inside the lead-time window as of {as_of.isoformat()}",
                        )
                    )
            for entry in want:
                if entry not in have:
                    out.append(
                        Finding(
                            rule,
                            Status.FLAG,
                            ctx.loc(watchlist, f"entries/{entry[0]}"),
                            f"note {entry[0]} matures within the lead-time window but is not "
                            f"on the watchlist",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the maturity watchlist ties the note evidence")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one loan file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top level must be a JSON object")

    ctx = Context(path=path, data=raw)
    report = DocumentReport(document=ctx.file_id)
    for _rule_id, fn in REGISTRY:
        report.findings.extend(fn(ctx))
    return report


def analyze_folder(folder: Path) -> list[DocumentReport]:
    """Analyze every ``.json`` loan file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of loan-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
