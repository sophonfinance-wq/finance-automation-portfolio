"""
Employee-expense & company card (P-Card) control engine (READ-ONLY).
====================================================================

Loads each cycle file (a ``.json`` file produced by
:mod:`expense_engine.generate`) and runs an ordered *registry* of independent
controls over it.

The shape of the problem
------------------------
A company issues a card, the bank issues a statement, and the cardholder owes a
matching expense report. One report line per statement charge, each with a
receipt on file, a business purpose, a valid general-ledger code and a real
project, filed inside the submission window, under the per-charge limit, approved
by somebody other than the cardholder.

Three failures hide inside that, and none of them look wrong in a page of small
numbers: the charge that never gets a report line (a company expense nobody coded
and nobody has a receipt for); the residual cent between the report and the bank
(a report that foots to a round number and is still a penny off the statement);
and the charge that should never have been on the card (over the limit, in a
disallowed category, coded to a project that does not exist, or approved by the
person who incurred it).

The registry is organised around that:

1. ``set_``  -- is the cycle file complete?
2. ``card_`` -- is the cardholder register sound?
3. ``stmt_`` -- are the statement lines well-formed, unique and integer cents?
4. ``rpt_``  -- does every report line carry a receipt, a purpose and its fields?
5. ``rec_``  -- does every charge reconcile to a report line, to the cent?
6. ``cod_``  -- is every line coded to a valid GL and a real project?
7. ``pol_``  -- filed in time, under the limit, approved by someone else?
8. ``dup_``  -- is any charge a duplicate of another?

Design notes
------------
- **Strictly read-only.** Cycle files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every reconciliation is compared with exact
  ``==``.
- **Absent evidence is not a passing control.** ``set_complete`` runs first and
  owns the "missing artifact" / "unreadable review date" findings.
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

from .model import (
    DOC_CARDHOLDER_REGISTER,
    DOC_EXPENSE_REPORT_REGISTER,
    DOC_GL_POSITIONS,
    DOC_POLICY,
    DOC_PROJECT_REGISTER,
    DOC_STATEMENT_REGISTER,
    DOC_TYPES,
    ENTITIES,
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
    """Render an :class:`~expense_engine.money.AmountInvalidError` as a finding."""
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
_LAST4_RE = re.compile(r"^\d{4}$")


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


def _bool(row: dict[str, Any], key: str) -> bool | None:
    value = row.get(key)
    return value if isinstance(value, bool) else None


def _present(row: dict[str, Any], key: str) -> bool:
    return key in row and row.get(key) is not None


# --------------------------------------------------------------------------- #
# Programme helpers
# --------------------------------------------------------------------------- #
def _cardholders(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CARDHOLDER_REGISTER), "cardholders")


def _card_id(row: dict[str, Any]) -> str:
    return _text(row, "cardholder_id") or "?"


def _card_last4_by_id(ctx: Context) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _cardholders(ctx):
        cid = _text(row, "cardholder_id")
        last4 = _text(row, "card_last4")
        if cid and cid not in out and last4:
            out[cid] = last4
    return out


def _card_name_by_id(ctx: Context) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _cardholders(ctx):
        cid = _text(row, "cardholder_id")
        name = _text(row, "name")
        if cid and cid not in out and name:
            out[cid] = name
    return out


def _projects(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_PROJECT_REGISTER), "projects"):
        code = _text(row, "code")
        if code and code not in out:
            out[code] = row
    return out


def _statements(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_STATEMENT_REGISTER), "statements")


def _statements_by_id(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for stmt in _statements(ctx):
        sid = _text(stmt, "statement_id")
        if sid and sid not in out:
            out[sid] = stmt
    return out


def _reports(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_EXPENSE_REPORT_REGISTER), "reports")


def _statement_lines(ctx: Context) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every ``(statement, line)`` pair, in file order."""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for stmt in _statements(ctx):
        for line in _rows(stmt, "lines"):
            out.append((stmt, line))
    return out


def _report_lines(ctx: Context) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every ``(report, line)`` pair, in file order."""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for report in _reports(ctx):
        for line in _rows(report, "lines"):
            out.append((report, line))
    return out


def _stmt_loc(ctx: Context, stmt: dict[str, Any], line: dict[str, Any], field: str) -> str:
    doc = ctx.one(DOC_STATEMENT_REGISTER) or {}
    sid = _text(stmt, "statement_id") or "?"
    lid = _text(line, "line_id") or "?"
    return ctx.loc(doc, f"statements/{sid}/{lid}/{field}")


def _rpt_loc(ctx: Context, report: dict[str, Any], line: dict[str, Any], field: str) -> str:
    doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER) or {}
    rid = _text(report, "report_id") or "?"
    lid = _text(line, "line_id") or "?"
    return ctx.loc(doc, f"reports/{rid}/{lid}/{field}")


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the cycle depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the cycle file carries "
                    f"exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(DOC_TYPES)} artifacts present")
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; the cycle's submission "
                f"window is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# card_ -- the cardholder register
# --------------------------------------------------------------------------- #
@check("card_required_fields")
def check_card_required_fields(ctx: Context) -> list[Finding]:
    """Every cardholder carries the fields the rest of the engine reads."""
    rule = "card_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CARDHOLDER_REGISTER)
    if register is None:
        return []
    required = ("cardholder_id", "name", "card_last4", "home_entity")
    out: list[Finding] = []
    for row in _cardholders(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cardholders/{_card_id(row)}"),
                    f"cardholder {_card_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_cardholders(ctx))} cardholders are fully described"
            )
        )
    return out


@check("card_id_unique")
def check_card_id_unique(ctx: Context) -> list[Finding]:
    """No cardholder id appears twice.

    The id joins the register to every statement and report. A duplicate makes a
    charge's ownership -- and its card last four -- ambiguous.
    """
    rule = "card_id_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CARDHOLDER_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _cardholders(ctx):
        seen[_card_id(row)] = seen.get(_card_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"cardholders/{cid}"),
            f"cardholder {cid} appears {count} times; a charge's ownership is ambiguous",
        )
        for cid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} cardholder ids are unique")
        )
    return out


@check("card_last4_valid")
def check_card_last4_valid(ctx: Context) -> list[Finding]:
    """A registered card last four is exactly four digits.

    Anything else cannot be the last four of a card number, so it can never
    match a statement line and the receipt trail is unverifiable.
    """
    rule = "card_last4_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CARDHOLDER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _cardholders(ctx):
        last4 = _text(row, "card_last4")
        if last4 is None:
            continue  # card_required_fields owns absence
        checked += 1
        if not _LAST4_RE.match(last4):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cardholders/{_card_id(row)}/card_last4"),
                    f"cardholder {_card_id(row)} has card last four {last4!r}, which is not "
                    f"four digits",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} card last-fours are valid"))
    return out


@check("card_home_entity_known")
def check_card_home_entity_known(ctx: Context) -> list[Finding]:
    """A cardholder's home entity is one the programme recognises.

    Coding a charge to an entity that is not on the books puts the expense on a
    ledger nobody reconciles.
    """
    rule = "card_home_entity_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CARDHOLDER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _cardholders(ctx):
        entity = _text(row, "home_entity")
        if entity is None:
            continue  # card_required_fields owns absence
        checked += 1
        if entity not in ENTITIES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cardholders/{_card_id(row)}/home_entity"),
                    f"cardholder {_card_id(row)} has home entity {entity!r}, which is not one "
                    f"of {ENTITIES}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} home entities are recognised")
        )
    return out


# --------------------------------------------------------------------------- #
# stmt_ -- the bank statement lines
# --------------------------------------------------------------------------- #
@check("stmt_required_fields")
def check_stmt_required_fields(ctx: Context) -> list[Finding]:
    """Every statement line carries the fields reconciliation reads."""
    rule = "stmt_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STATEMENT_REGISTER)
    if register is None:
        return []
    text_fields = ("line_id", "date", "merchant", "category", "last4")
    out: list[Finding] = []
    for stmt, line in _statement_lines(ctx):
        missing = [f for f in text_fields if not _text(line, f)]
        if not _present(line, "amount_cents"):
            missing.append("amount_cents")
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _stmt_loc(ctx, stmt, line, "-"),
                    f"statement {_text(stmt, 'statement_id')} line "
                    f"{_text(line, 'line_id') or '?'} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_statement_lines(ctx))} statement lines are complete"
            )
        )
    return out


@check("stmt_line_unique")
def check_stmt_line_unique(ctx: Context) -> list[Finding]:
    """No statement line id is used twice.

    The line id is the join a report line reconciles against; a duplicate makes
    one bank charge indistinguishable from another.
    """
    rule = "stmt_line_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STATEMENT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for _stmt, line in _statement_lines(ctx):
        lid = _text(line, "line_id")
        if lid:
            seen[lid] = seen.get(lid, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"statements/*/{lid}"),
            f"statement line id {lid} appears {count} times; a report line cannot "
            f"reconcile against it unambiguously",
        )
        for lid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} statement line ids are unique")
        )
    return out


@check("stmt_amounts_integer")
def check_stmt_amounts_integer(ctx: Context) -> list[Finding]:
    """Every statement amount is integer cents.

    A dollar figure that arrived as a float has already lost the guarantee that
    it reconciles exactly; the engine reports the value rather than coercing it.
    """
    rule = "stmt_amounts_integer"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STATEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for stmt, line in _statement_lines(ctx):
        with amount_guard(rule, out):
            require_cents(
                f"statement[{_text(stmt, 'statement_id')}/{_text(line, 'line_id')}]"
                f".amount_cents",
                line.get("amount_cents"),
            )
            checked += 1
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} statement amounts are integer cents")
        )
    return out


@check("stmt_last4_matches_card")
def check_stmt_last4_matches_card(ctx: Context) -> list[Finding]:
    """Each statement line carries the last four of its cardholder's card.

    A charge tagged with a different last four either belongs to another card or
    was mistyped; either way the receipt trail no longer proves whose card paid.
    """
    rule = "stmt_last4_matches_card"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STATEMENT_REGISTER)
    if register is None:
        return []
    cards = _card_last4_by_id(ctx)
    out: list[Finding] = []
    checked = 0
    for stmt in _statements(ctx):
        cid = _text(stmt, "cardholder_id")
        expected = cards.get(cid or "")
        if cid is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"statements/{_text(stmt, 'statement_id') or '?'}"),
                    f"statement {_text(stmt, 'statement_id') or '?'} names no cardholder",
                )
            )
            continue
        if expected is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"statements/{_text(stmt, 'statement_id') or '?'}"),
                    f"statement {_text(stmt, 'statement_id') or '?'} names cardholder {cid}, "
                    f"who is not in the register with a card last four",
                )
            )
            continue
        for line in _rows(stmt, "lines"):
            last4 = _text(line, "last4")
            if last4 is None:
                continue  # stmt_required_fields owns absence
            checked += 1
            if last4 != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        _stmt_loc(ctx, stmt, line, "last4"),
                        f"charge {_text(line, 'line_id')} carries last four {last4!r}; "
                        f"cardholder {cid}'s card ends {expected!r}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges match their cardholder's card")
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the expense report lines
# --------------------------------------------------------------------------- #
@check("rpt_required_fields")
def check_rpt_required_fields(ctx: Context) -> list[Finding]:
    """Every report line and its header carry the fields the controls read."""
    rule = "rpt_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if register is None:
        return []
    header_fields = ("report_id", "cardholder_id", "statement_id", "submitted_date", "approver")
    line_text_fields = ("line_id", "statement_line_id", "gl_code", "project_code")
    line_present_fields = ("purpose", "receipt_on_file", "amount_cents")
    out: list[Finding] = []
    for report in _reports(ctx):
        missing = [f for f in header_fields if not _text(report, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"reports/{_text(report, 'report_id') or '?'}"),
                    f"report {_text(report, 'report_id') or '?'} is missing "
                    f"{', '.join(missing)}",
                )
            )
        for line in _rows(report, "lines"):
            miss = [f for f in line_text_fields if not _text(line, f)]
            miss += [f for f in line_present_fields if not _present(line, f)]
            if miss:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        _rpt_loc(ctx, report, line, "-"),
                        f"report {_text(report, 'report_id') or '?'} line "
                        f"{_text(line, 'line_id') or '?'} is missing {', '.join(miss)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_report_lines(ctx))} report lines are complete"
            )
        )
    return out


@check("rpt_receipt_on_file")
def check_rpt_receipt_on_file(ctx: Context) -> list[Finding]:
    """Every report line has a receipt on file.

    The receipt is the evidence the charge was a real business expense at the
    time, place and amount claimed. A line without one is an unsupported
    disbursement of company money.
    """
    rule = "rpt_receipt_on_file"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for report, line in _report_lines(ctx):
        if not _present(line, "receipt_on_file"):
            continue  # rpt_required_fields owns absence
        checked += 1
        if _bool(line, "receipt_on_file") is not True:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _rpt_loc(ctx, report, line, "receipt_on_file"),
                    f"report {_text(report, 'report_id')} line {_text(line, 'line_id')} has no "
                    f"receipt on file; the charge is unsupported",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} report lines have a receipt on file")
        )
    return out


@check("rpt_purpose_present")
def check_rpt_purpose_present(ctx: Context) -> list[Finding]:
    """Every report line states a business purpose.

    A charge without a stated purpose cannot be reviewed for whether it was an
    appropriate use of the card; a blank purpose passes the schema and fails the
    test.
    """
    rule = "rpt_purpose_present"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for report, line in _report_lines(ctx):
        if not _present(line, "purpose"):
            continue  # rpt_required_fields owns absence
        checked += 1
        if _text(line, "purpose") is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _rpt_loc(ctx, report, line, "purpose"),
                    f"report {_text(report, 'report_id')} line {_text(line, 'line_id')} states "
                    f"no business purpose",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} report lines state a purpose")
        )
    return out


# --------------------------------------------------------------------------- #
# rec_ -- reconciliation of the report to the bank statement
# --------------------------------------------------------------------------- #
@check("rec_every_charge_reported")
def check_rec_every_charge_reported(ctx: Context) -> list[Finding]:
    """Every statement charge has exactly one report line, tied to the cent.

    This is the control the engine exists for. A statement line with no report
    line is a company expense nobody coded and nobody has a receipt for; one with
    two report lines is a charge claimed twice; one whose report line differs by a
    cent has not reconciled. All three are invisible in a footed total.
    """
    rule = "rec_every_charge_reported"
    _sev(rule, Status.FAIL)
    stmt_doc = ctx.one(DOC_STATEMENT_REGISTER)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if stmt_doc is None or report_doc is None:
        return []
    by_sl: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for report, line in _report_lines(ctx):
        sl = _text(line, "statement_line_id")
        if sl:
            by_sl.setdefault(sl, []).append((report, line))
    out: list[Finding] = []
    checked = 0
    for stmt, line in _statement_lines(ctx):
        lid = _text(line, "line_id")
        if lid is None:
            continue  # stmt_required_fields owns absence
        matches = by_sl.get(lid, [])
        checked += 1
        if len(matches) == 0:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _stmt_loc(ctx, stmt, line, "-"),
                    f"charge {lid} on statement {_text(stmt, 'statement_id')} has no report "
                    f"line; it is an uncoded, unreceipted company expense",
                )
            )
            continue
        if len(matches) > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _stmt_loc(ctx, stmt, line, "-"),
                    f"charge {lid} on statement {_text(stmt, 'statement_id')} is claimed by "
                    f"{len(matches)} report lines; it has been reported more than once",
                )
            )
            continue
        report, rline = matches[0]
        with amount_guard(rule, out):
            stated = require_cents(f"statement[{lid}].amount_cents", line.get("amount_cents"))
            claimed = require_cents(
                f"report[{_text(rline, 'line_id')}].amount_cents", rline.get("amount_cents")
            )
            if stated != claimed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        _rpt_loc(ctx, report, rline, "amount_cents"),
                        f"charge {lid} is {fmt(stated)} on the statement but {fmt(claimed)} on "
                        f"the report (difference {fmt(claimed - stated)}); it does not "
                        f"reconcile to the cent",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges reconcile to one report line")
        )
    return out


@check("rec_no_orphan_report_line")
def check_rec_no_orphan_report_line(ctx: Context) -> list[Finding]:
    """No report line reconciles against a statement charge that does not exist.

    An orphan report line is a reimbursement claimed for a charge the bank never
    made -- the mirror image of an unreported charge, and just as costly.
    """
    rule = "rec_no_orphan_report_line"
    _sev(rule, Status.FAIL)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    stmt_doc = ctx.one(DOC_STATEMENT_REGISTER)
    if report_doc is None or stmt_doc is None:
        return []
    known = {_text(line, "line_id") for _stmt, line in _statement_lines(ctx) if _text(line, "line_id")}
    out: list[Finding] = []
    checked = 0
    for report, line in _report_lines(ctx):
        sl = _text(line, "statement_line_id")
        if sl is None:
            continue  # rpt_required_fields owns absence
        checked += 1
        if sl not in known:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _rpt_loc(ctx, report, line, "statement_line_id"),
                    f"report {_text(report, 'report_id')} line {_text(line, 'line_id')} claims "
                    f"charge {sl!r}, which is on no statement in the cycle",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} report lines claim a real charge")
        )
    return out


@check("rec_report_total_ties")
def check_rec_report_total_ties(ctx: Context) -> list[Finding]:
    """Each cardholder's report total ties their statement total, to the cent.

    The line-by-line control catches a misplaced charge; this catches the whole
    report drifting from the bank -- a claim that reimburses more or less than the
    card actually spent.
    """
    rule = "rec_report_total_ties"
    _sev(rule, Status.FAIL)
    stmt_doc = ctx.one(DOC_STATEMENT_REGISTER)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if stmt_doc is None or report_doc is None:
        return []
    stmt_lines_by_ch: dict[str, list[dict[str, Any]]] = {}
    for stmt in _statements(ctx):
        cid = _text(stmt, "cardholder_id") or "?"
        stmt_lines_by_ch.setdefault(cid, []).extend(_rows(stmt, "lines"))
    report_lines_by_ch: dict[str, list[dict[str, Any]]] = {}
    for report in _reports(ctx):
        cid = _text(report, "cardholder_id") or "?"
        report_lines_by_ch.setdefault(cid, []).extend(_rows(report, "lines"))
    out: list[Finding] = []
    checked = 0
    for cid in sorted(set(stmt_lines_by_ch) | set(report_lines_by_ch)):
        with amount_guard(rule, out):
            stmt_total = sum(
                require_cents(f"statement[{cid}].amount_cents", ln.get("amount_cents"))
                for ln in stmt_lines_by_ch.get(cid, [])
            )
            report_total = sum(
                require_cents(f"report[{cid}].amount_cents", ln.get("amount_cents"))
                for ln in report_lines_by_ch.get(cid, [])
            )
            checked += 1
            if stmt_total != report_total:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(report_doc, f"reports/{cid}"),
                        f"cardholder {cid} reports {fmt(report_total)} against a statement of "
                        f"{fmt(stmt_total)} (difference {fmt(report_total - stmt_total)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} cardholder reports tie their statement")
        )
    return out


@check("rec_gl_ties_reports")
def check_rec_gl_ties_reports(ctx: Context) -> list[Finding]:
    """The general ledger's P-Card total equals the sum of the report lines.

    The reports are the working paper; the GL is the accounting. Between them is a
    posting, and a posting is where a reconciled report becomes a number somebody
    reports on.
    """
    rule = "rec_gl_ties_reports"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if gl is None or report_doc is None:
        return []
    out: list[Finding] = []
    derived = 0
    for report, line in _report_lines(ctx):
        with amount_guard(rule, out):
            derived += require_cents(
                f"report[{_text(line, 'line_id')}].amount_cents", line.get("amount_cents")
            )
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.total_pcard_expense_cents", gl.get("total_pcard_expense_cents")
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "total_pcard_expense_cents"),
                    f"the ledger carries {fmt(stated)} of P-Card expense; the report lines sum "
                    f"to {fmt(derived)} (difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"P-Card expense of {fmt(derived)} ties the ledger"
                )
            )
    return out


# --------------------------------------------------------------------------- #
# cod_ -- general-ledger and project coding
# --------------------------------------------------------------------------- #
@check("cod_gl_valid")
def check_cod_gl_valid(ctx: Context) -> list[Finding]:
    """Every report line is coded to a GL account the policy allows."""
    rule = "cod_gl_valid"
    _sev(rule, Status.FAIL)
    policy = ctx.one(DOC_POLICY)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if policy is None or report_doc is None:
        return []
    valid = policy.get("valid_gl_codes")
    valid_set = {c for c in valid if isinstance(c, str)} if isinstance(valid, list) else set()
    out: list[Finding] = []
    checked = 0
    for report, line in _report_lines(ctx):
        gl = _text(line, "gl_code")
        if gl is None:
            continue  # rpt_required_fields owns absence
        checked += 1
        if gl not in valid_set:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _rpt_loc(ctx, report, line, "gl_code"),
                    f"report {_text(report, 'report_id')} line {_text(line, 'line_id')} is "
                    f"coded to GL {gl!r}, which is not in the policy's valid set",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} lines carry a valid GL code"))
    return out


@check("cod_project_exists")
def check_cod_project_exists(ctx: Context) -> list[Finding]:
    """Every report line is coded to a project in the register."""
    rule = "cod_project_exists"
    _sev(rule, Status.FAIL)
    projects_doc = ctx.one(DOC_PROJECT_REGISTER)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if projects_doc is None or report_doc is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for report, line in _report_lines(ctx):
        code = _text(line, "project_code")
        if code is None:
            continue  # rpt_required_fields owns absence
        checked += 1
        if code not in projects:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    _rpt_loc(ctx, report, line, "project_code"),
                    f"report {_text(report, 'report_id')} line {_text(line, 'line_id')} is "
                    f"coded to project {code!r}, which is not in the register",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} lines name a project in the register")
        )
    return out


@check("cod_disallowed_category")
def check_cod_disallowed_category(ctx: Context) -> list[Finding]:
    """A charge in a disallowed merchant category is flagged for review.

    A cash advance, a gambling charge or a bar tab is not necessarily fraud, but
    it is never routine, and the policy names the categories a reviewer should
    always look at by hand.
    """
    rule = "cod_disallowed_category"
    _sev(rule, Status.FLAG)
    policy = ctx.one(DOC_POLICY)
    stmt_doc = ctx.one(DOC_STATEMENT_REGISTER)
    if policy is None or stmt_doc is None:
        return []
    disallowed = policy.get("disallowed_categories")
    disallowed_set = (
        {c for c in disallowed if isinstance(c, str)} if isinstance(disallowed, list) else set()
    )
    out: list[Finding] = []
    checked = 0
    for stmt, line in _statement_lines(ctx):
        category = _text(line, "category")
        if category is None:
            continue  # stmt_required_fields owns absence
        checked += 1
        if category in disallowed_set:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    _stmt_loc(ctx, stmt, line, "category"),
                    f"charge {_text(line, 'line_id')} at {_text(line, 'merchant')} is category "
                    f"{category!r}, which the policy disallows; a reviewer must clear it by hand",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"none of {checked} charges are in a disallowed category")
        )
    return out


# --------------------------------------------------------------------------- #
# pol_ -- programme policy
# --------------------------------------------------------------------------- #
@check("pol_submitted_within_window")
def check_pol_submitted_within_window(ctx: Context) -> list[Finding]:
    """Each report is filed within the submission window after the statement.

    A report filed weeks late is a review flag, not a hard failure: the charges
    may all be legitimate, but stale reports are how receipts go missing and how a
    disputed charge passes its chargeback deadline.
    """
    rule = "pol_submitted_within_window"
    _sev(rule, Status.FLAG)
    policy = ctx.one(DOC_POLICY)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if policy is None or report_doc is None:
        return []
    window = _int(policy, "submission_window_days")
    statements = _statements_by_id(ctx)
    out: list[Finding] = []
    checked = 0
    for report in _reports(ctx):
        submitted = _parse_date(report.get("submitted_date"))
        stmt = statements.get(_text(report, "statement_id") or "")
        stmt_date = _parse_date(stmt.get("statement_date")) if stmt else None
        if submitted is None or stmt_date is None or window is None:
            continue
        checked += 1
        elapsed = (submitted - stmt_date).days
        if elapsed > window:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(report_doc, f"reports/{_text(report, 'report_id')}/submitted_date"),
                    f"report {_text(report, 'report_id')} was filed {elapsed} days after the "
                    f"statement dated {stmt_date.isoformat()}; the window is {window} days",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} reports were filed within the window")
        )
    return out


@check("pol_per_charge_limit")
def check_pol_per_charge_limit(ctx: Context) -> list[Finding]:
    """No single charge exceeds the per-charge limit.

    The limit is the card's spending control; a charge above it should have gone
    through purchasing, and its presence on the card is the control break whether
    or not the expense itself was legitimate.
    """
    rule = "pol_per_charge_limit"
    _sev(rule, Status.FAIL)
    policy = ctx.one(DOC_POLICY)
    stmt_doc = ctx.one(DOC_STATEMENT_REGISTER)
    if policy is None or stmt_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        limit = require_cents(
            "policy.per_charge_limit_cents", policy.get("per_charge_limit_cents")
        )
        for stmt, line in _statement_lines(ctx):
            with amount_guard(rule, out):
                amount = require_cents(
                    f"statement[{_text(line, 'line_id')}].amount_cents", line.get("amount_cents")
                )
                checked += 1
                if amount > limit:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            _stmt_loc(ctx, stmt, line, "amount_cents"),
                            f"charge {_text(line, 'line_id')} at {_text(line, 'merchant')} is "
                            f"{fmt(amount)}, over the per-charge limit of {fmt(limit)}",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges are within the per-charge limit")
        )
    return out


@check("pol_approver_distinct")
def check_pol_approver_distinct(ctx: Context) -> list[Finding]:
    """Each report is approved by someone other than the cardholder.

    Self-approval is the whole point of an approval: a cardholder who signs off
    their own report has removed the second person the control depends on.
    """
    rule = "pol_approver_distinct"
    _sev(rule, Status.FAIL)
    report_doc = ctx.one(DOC_EXPENSE_REPORT_REGISTER)
    if report_doc is None:
        return []
    names = _card_name_by_id(ctx)
    out: list[Finding] = []
    checked = 0
    for report in _reports(ctx):
        approver = _text(report, "approver")
        cid = _text(report, "cardholder_id")
        if approver is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report_doc, f"reports/{_text(report, 'report_id') or '?'}/approver"),
                    f"report {_text(report, 'report_id') or '?'} names no approver",
                )
            )
            continue
        checked += 1
        cardholder_name = names.get(cid or "")
        if approver == cardholder_name or approver == cid:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report_doc, f"reports/{_text(report, 'report_id')}/approver"),
                    f"report {_text(report, 'report_id')} was approved by {approver!r}, the "
                    f"cardholder themself; approval requires a second person",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} reports were approved by a second person")
        )
    return out


# --------------------------------------------------------------------------- #
# dup_ -- duplicate charge detection
# --------------------------------------------------------------------------- #
@check("dup_no_duplicate_charge")
def check_dup_no_duplicate_charge(ctx: Context) -> list[Finding]:
    """No charge is a duplicate of another on the same card.

    A duplicate charge -- the same amount at the same merchant on the same day on
    the same card -- is either a merchant double-post the company should dispute
    or a claim submitted twice. The four-way key is what tells the two apart from
    a legitimate repeat purchase.
    """
    rule = "dup_no_duplicate_charge"
    _sev(rule, Status.FAIL)
    stmt_doc = ctx.one(DOC_STATEMENT_REGISTER)
    if stmt_doc is None:
        return []
    seen: dict[tuple[str, str, object, str], list[str]] = {}
    for _stmt, line in _statement_lines(ctx):
        date_s = _text(line, "date")
        merchant = _text(line, "merchant")
        last4 = _text(line, "last4")
        lid = _text(line, "line_id")
        if date_s is None or merchant is None or last4 is None or lid is None:
            continue  # stmt_required_fields owns absence
        key = (date_s, merchant, line.get("amount_cents"), last4)
        seen.setdefault(key, []).append(lid)
    out: list[Finding] = []
    for key, lids in seen.items():
        if len(lids) > 1:
            date_s, merchant, amount, last4 = key
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(stmt_doc, f"statements/*/{lids[0]}"),
                    f"charges {', '.join(lids)} are duplicates: {merchant} on {date_s} for "
                    f"{fmt(amount) if isinstance(amount, int) and not isinstance(amount, bool) else amount} "
                    f"on card ending {last4}; one should be disputed or removed",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"no duplicate charges across {len(seen)} distinct charges")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one cycle file."""
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
    """Analyze every ``.json`` cycle file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of cycle-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
