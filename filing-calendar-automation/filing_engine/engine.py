"""
Filing-obligation calendar control engine (READ-ONLY).
======================================================

Loads each calendar file (a ``.json`` file produced by
:mod:`filing_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether every filing obligation was met or validly
deferred before its statutory deadline**, not what the return says or what the
tax is. Preparing the return and computing the tax are separate jobs; this engine
takes the finished calendar and proves, entity by entity and jurisdiction by
jurisdiction, that each obligation was filed or extended on time, each
fixed-amount payment was made in the exact statutory amount, and the status
register ties to the filed evidence with nothing missing and nothing orphaned.

The shape of the problem
------------------------
Four failures hide inside a filing calendar, and none of them look wrong in a
grid of dates: the due date typed a day off or keyed to the wrong form; the
obligation that slid past its deadline unfiled and unextended; the row marked
filed that no voucher backs (or the voucher no row claims); and the fixed annual
tax cut for anything other than the statutory constant.

The registry is organised around that:

1. ``set_``   -- is the calendar file complete?
2. ``due_``   -- does every due date re-derive from the form and the year-end?
3. ``ext_``   -- is the extension gate sound, and is anything overdue or late?
4. ``pay_``   -- is each fixed-amount payment the exact statutory constant?
5. ``evd_``   -- does every filed row tie to evidence, and every evidence to a row?
6. ``ros_``   -- is the entity roster complete and every obligation attributable?
7. ``wfl_``   -- is the internal workflow schedule ordered and on track?
8. ``cnt_``   -- does a final entity stay final across the year boundary?
9. ``rpt_``   -- does the status roll-up recompute from the register it summarises?

Design notes
------------
- **Strictly read-only.** Calendar files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Whole-month date arithmetic, exact comparison.** A deadline is met *at* the
  date, not a day past it; there is no grace band.
- **One due-date predicate.** Controls and the generator share the kernel in
  :mod:`filing_engine.duedates`, so a recomputed date or status cannot disagree
  with the data that produced it.
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

from .duedates import (
    STATUS_FILED,
    STATUS_FILED_LATE,
    STATUS_OPEN,
    STATUS_OVERDUE,
    applicable_due,
    derive_due_dates,
    obligation_status,
    within_due_window,
)
from .model import (
    DOC_DUE_DATES_TABLE,
    DOC_DUE_WATCHLIST,
    DOC_ENTITY_ROSTER,
    DOC_EVIDENCE_INDEX,
    DOC_OBLIGATION_REGISTER,
    DOC_PRIOR_YEAR_REGISTER,
    DOC_STATUS_SUMMARY,
    DOC_TYPES,
    EVIDENCE_EXTENSION,
    EVIDENCE_KINDS,
    FILING_EVIDENCE_KINDS,
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
    """Render an :class:`~filing_engine.money.AmountInvalidError` as a finding."""
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
# Calendar-file helpers
# --------------------------------------------------------------------------- #
def _entities(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ENTITY_ROSTER), "entities")


def _entity_id(row: dict[str, Any]) -> str:
    value = row.get("entity_id")
    return value if isinstance(value, str) and value else "?"


def _entity_ids(ctx: Context) -> set[str]:
    return {_entity_id(e) for e in _entities(ctx) if _entity_id(e) != "?"}


def _obligations(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_OBLIGATION_REGISTER), "obligations")


def _obligation_id(row: dict[str, Any]) -> str:
    value = row.get("obligation_id")
    return value if isinstance(value, str) and value else "?"


def _obligation_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _obligations(ctx):
        oid = _obligation_id(row)
        if oid != "?" and oid not in out:
            out[oid] = row
    return out


def _is_na(row: dict[str, Any]) -> bool:
    return bool(row.get("na"))


def _year_end_md(year_end: date) -> str:
    return f"{year_end.month:02d}-{year_end.day:02d}"


def _due_rules(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_DUE_DATES_TABLE), "rules"):
        form = _text(row, "form")
        ye = _text(row, "year_end")
        if form and ye and (form, ye) not in out:
            out[(form, ye)] = row
    return out


def _rule_for(
    obligation: dict[str, Any], rules: dict[tuple[str, str], dict[str, Any]]
) -> dict[str, Any] | None:
    form = _text(obligation, "form")
    year_end = _parse_date(obligation.get("year_end"))
    if form is None or year_end is None:
        return None
    return rules.get((form, _year_end_md(year_end)))


def derive_obligation_dates(
    obligation: dict[str, Any], rules: dict[tuple[str, str], dict[str, Any]]
) -> tuple[date | None, date | None]:
    """Re-derive ``(original_due, extended_due)`` for one obligation.

    Reads the statutory offsets from the due-dates table row for this obligation's
    ``(form, year-end)`` and hands them to the shared kernel. Returns
    ``(None, None)`` when the year-end is unreadable or the table has no matching
    row -- separate controls own those gaps. The ``extended_due`` returned is the
    date the form's offset *would* produce; whether it applies to this obligation
    depends on whether an extension was filed.
    """
    year_end = _parse_date(obligation.get("year_end"))
    rule = _rule_for(obligation, rules)
    if year_end is None or rule is None:
        return None, None
    original_month = _int(rule, "original_month")
    original_day = _int(rule, "original_day")
    offset = _int(rule, "extension_offset_months")
    if original_month is None or original_day is None or offset is None:
        return None, None
    return derive_due_dates(year_end, original_month, original_day, offset)


def _stored_applicable_due(obligation: dict[str, Any]) -> date | None:
    """The applicable due date read from the register's *own* stored dates."""
    original = _parse_date(obligation.get("original_due"))
    extended = _parse_date(obligation.get("extended_due"))
    return applicable_due(original, extended, bool(obligation.get("extension_filed")))


def _evidence(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_EVIDENCE_INDEX), "evidence")


def _prior_final(ctx: Context) -> set[str]:
    doc = ctx.one(DOC_PRIOR_YEAR_REGISTER)
    if not isinstance(doc, dict):
        return set()
    value = doc.get("final_entities")
    if not isinstance(value, list):
        return set()
    return {v for v in value if isinstance(v, str) and v}


# --------------------------------------------------------------------------- #
# Shared recompute (used by the engine and by the generator)
# --------------------------------------------------------------------------- #
def recompute_status(
    ctx: Context,
    obligation: dict[str, Any],
    as_of: date,
) -> str:
    """Recompute one obligation's status from its register dates.

    Reads the register's *stored* original/extended due dates (the dates a
    reviewer sees), resolves the applicable deadline through the shared kernel,
    and classifies against the review date. Shared with the generator so the
    stated status is the one the engine recomputes.
    """
    the_due = _stored_applicable_due(obligation)
    return_filed = _parse_date(obligation.get("return_filed"))
    return obligation_status(the_due, return_filed, as_of, _is_na(obligation))


def recompute_overdue_count(ctx: Context, as_of: date) -> int:
    """The number of obligations whose recomputed status is overdue."""
    return sum(
        1
        for o in _obligations(ctx)
        if recompute_status(ctx, o, as_of) == STATUS_OVERDUE
    )


def recompute_filed_count(ctx: Context, as_of: date) -> int:
    """The number of obligations recomputed to filed on time."""
    return sum(
        1 for o in _obligations(ctx) if recompute_status(ctx, o, as_of) == STATUS_FILED
    )


def recompute_watchlist(ctx: Context, as_of: date, lead_days: int) -> list[dict[str, Any]]:
    """The due-date watchlist re-derived from the register.

    One entry per unfiled, non-n/a obligation whose applicable deadline falls
    inside the lead-time window. Shared with the generator so the stated watchlist
    can be tied to it.
    """
    entries: list[dict[str, Any]] = []
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        if _parse_date(obligation.get("return_filed")) is not None:
            continue
        the_due = _stored_applicable_due(obligation)
        if the_due is None:
            continue
        if within_due_window(the_due, as_of, lead_days):
            entries.append(
                {
                    "obligation_id": _obligation_id(obligation),
                    "entity_id": _text(obligation, "entity_id"),
                    "form": _text(obligation, "form"),
                    "applicable_due": the_due.isoformat(),
                    "days_remaining": (the_due - as_of).days,
                }
            )
    entries.sort(key=lambda e: (e["obligation_id"],))
    return entries


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("obligation_id"),
        entry.get("entity_id"),
        entry.get("form"),
        entry.get("applicable_due"),
        entry.get("days_remaining"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the calendar file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the calendar file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} calendar artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every due-date and "
                f"overdue test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# due_ -- the due date re-derives from the form and the year-end
# --------------------------------------------------------------------------- #
@check("due_year_end_valid")
def check_due_year_end_valid(ctx: Context) -> list[Finding]:
    """Every obligation carries a readable fiscal year-end.

    The year-end is the key into the statutory due-dates table; an unreadable one
    has no lookup, so no due date downstream could be re-derived for that row.
    """
    rule = "due_year_end_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for obligation in _obligations(ctx):
        if _parse_date(obligation.get("year_end")) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/year_end"),
                    f"obligation {_obligation_id(obligation)} carries year-end "
                    f"{obligation.get('year_end')!r}, which is not a readable date; its "
                    f"statutory due dates cannot be looked up",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_obligations(ctx))} obligations carry a readable year-end"
            )
        )
    return out


@check("due_table_defined")
def check_due_table_defined(ctx: Context) -> list[Finding]:
    """Every obligation's (form, year-end) has a row in the statutory table.

    Without the table row the engine knows an obligation exists but not what
    deadline to hold it to, so the re-derivation controls would silently skip it.
    Obligations with an unreadable year-end are left to ``due_year_end_valid``.
    """
    rule = "due_table_defined"
    _sev(rule, Status.FAIL)
    table = ctx.one(DOC_DUE_DATES_TABLE)
    if table is None:
        return []
    rules = _due_rules(ctx)
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        year_end = _parse_date(obligation.get("year_end"))
        form = _text(obligation, "form")
        if year_end is None or form is None:
            continue  # due_year_end_valid owns the date gap
        checked += 1
        if (form, _year_end_md(year_end)) not in rules:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(table, f"rules/{form}/{_year_end_md(year_end)}"),
                    f"the due-dates table has no row for form {form!r} at year-end "
                    f"{_year_end_md(year_end)}, which obligation "
                    f"{_obligation_id(obligation)} requires; its due date cannot be "
                    f"re-derived",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} obligations map to a due-dates row")
        )
    return out


@check("due_original_matches")
def check_due_original_matches(ctx: Context) -> list[Finding]:
    """The register's stored original due date re-derives from the table.

    The original deadline is a function of the form and the year-end; a stored
    value that does not equal the re-derived one is a typo the whole register keys
    its follow-up off.
    """
    rule = "due_original_matches"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    rules = _due_rules(ctx)
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        derived_original, _derived_extended = derive_obligation_dates(obligation, rules)
        if derived_original is None:
            continue  # due_table_defined / due_year_end_valid own the gap
        stored = _parse_date(obligation.get("original_due"))
        checked += 1
        if stored != derived_original:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/original_due"),
                    f"obligation {_obligation_id(obligation)} stores original due "
                    f"{obligation.get('original_due')!r}; re-deriving from the table gives "
                    f"{derived_original.isoformat()}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} original due dates re-derive")
        )
    return out


@check("due_extended_matches")
def check_due_extended_matches(ctx: Context) -> list[Finding]:
    """A stored extended due date re-derives as the original plus the offset.

    Only obligations that carry an extended date are checked: the extended
    deadline is the original advanced by the form's whole-month statutory offset,
    and a stored value that does not equal it is applied to the wrong window.
    """
    rule = "due_extended_matches"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    rules = _due_rules(ctx)
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        stored = _parse_date(obligation.get("extended_due"))
        if stored is None:
            continue  # no extended date to check
        _derived_original, derived_extended = derive_obligation_dates(obligation, rules)
        if derived_extended is None:
            continue  # due_table_defined owns the missing row
        checked += 1
        if stored != derived_extended:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/extended_due"),
                    f"obligation {_obligation_id(obligation)} stores extended due "
                    f"{obligation.get('extended_due')!r}; re-deriving the original plus the "
                    f"statutory offset gives {derived_extended.isoformat()}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} extended due dates re-derive")
        )
    return out


# --------------------------------------------------------------------------- #
# ext_ -- the extension gate, overdue and late detection
# --------------------------------------------------------------------------- #
@check("ext_flag_valid")
def check_ext_flag_valid(ctx: Context) -> list[Finding]:
    """The extension flag and the extended date agree.

    An obligation that filed an extension must carry the extended date it now
    runs to; an obligation with an extended date on file must have filed the
    extension that produced it. A mismatch means the applicable deadline is being
    read from a field the other half of the record contradicts.
    """
    rule = "ext_flag_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        extension_filed = bool(obligation.get("extension_filed"))
        has_extended = _parse_date(obligation.get("extended_due")) is not None
        if extension_filed and not has_extended:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/extended_due"),
                    f"obligation {_obligation_id(obligation)} is marked extension-filed but "
                    f"carries no extended due date to run to",
                )
            )
        elif has_extended and not extension_filed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/extension_filed"),
                    f"obligation {_obligation_id(obligation)} carries an extended due date but "
                    f"is not marked extension-filed; the deferral has no basis",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every extension flag agrees with its extended date")
        )
    return out


@check("ext_applicable_overdue")
def check_ext_applicable_overdue(ctx: Context) -> list[Finding]:
    """No obligation is past its applicable deadline, unfiled and unextended.

    The applicable deadline is the extended date when an extension was filed, the
    original otherwise. An obligation unfiled at a deadline on or before the review
    date is a missed filing -- a penalty waiting in a row that looks like every
    other open one.
    """
    rule = "ext_applicable_overdue"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        checked += 1
        if recompute_status(ctx, obligation, as_of) == STATUS_OVERDUE:
            the_due = _stored_applicable_due(obligation)
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/return_filed"),
                    f"obligation {_obligation_id(obligation)} is unfiled and its applicable "
                    f"deadline {the_due.isoformat() if the_due else '?'} is on or before the "
                    f"review date {as_of.isoformat()}; the obligation is overdue",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} obligations are filed, extended or still open")
        )
    return out


@check("ext_filed_on_time")
def check_ext_filed_on_time(ctx: Context) -> list[Finding]:
    """A filed return was filed on or before its applicable deadline.

    Filing at all is not the test; filing on time is. A return lodged after the
    applicable due date is a late filing, and it is invisible in a register that
    records only that it was filed.
    """
    rule = "ext_filed_on_time"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        if _parse_date(obligation.get("return_filed")) is None:
            continue
        checked += 1
        if recompute_status(ctx, obligation, as_of) == STATUS_FILED_LATE:
            the_due = _stored_applicable_due(obligation)
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/return_filed"),
                    f"obligation {_obligation_id(obligation)} was filed "
                    f"{obligation.get('return_filed')!r}, after its applicable deadline "
                    f"{the_due.isoformat() if the_due else '?'}; the filing is late",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} filed returns were filed on time")
        )
    return out


@check("ext_due_soon")
def check_ext_due_soon(ctx: Context) -> list[Finding]:
    """An unfiled obligation falling due inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the deadline has not passed, but the
    filing needs to be chased before it does. The window comes from the file's own
    ``due_lead_days``.
    """
    rule = "ext_due_soon"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    lead = ctx.due_lead_days
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        if _parse_date(obligation.get("return_filed")) is not None:
            continue
        the_due = _stored_applicable_due(obligation)
        if the_due is None:
            continue
        checked += 1
        if within_due_window(the_due, as_of, lead):
            remaining = (the_due - as_of).days
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/original_due"),
                    f"obligation {_obligation_id(obligation)} falls due "
                    f"{the_due.isoformat()}, in {remaining} day(s); inside the {lead}-day "
                    f"window and due to be chased",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} unfiled obligations are outside the window")
        )
    return out


# --------------------------------------------------------------------------- #
# pay_ -- the fixed-amount payment is the statutory constant
# --------------------------------------------------------------------------- #
@check("pay_fixed_amount")
def check_pay_fixed_amount(ctx: Context) -> list[Finding]:
    """A fixed-amount obligation's payment is the exact statutory constant.

    Some forms print a statutory dollar amount on the face of the voucher -- the
    annual LLC tax is the archetype. Compared with exact equality: an amount a cent
    off the constant is wrong on its face, whatever else the row says.
    """
    rule = "pay_fixed_amount"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    rules = _due_rules(ctx)
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        rule_row = _rule_for(obligation, rules)
        if rule_row is None or rule_row.get("fixed_amount_cents") is None:
            continue  # not a fixed-amount form
        with amount_guard(rule, out):
            required = require_cents(
                f"due_rule[{_text(obligation, 'form')}].fixed_amount_cents",
                rule_row.get("fixed_amount_cents"),
            )
            actual = require_cents(
                f"obligation[{_obligation_id(obligation)}].amount_required_cents",
                obligation.get("amount_required_cents"),
            )
            checked += 1
            if actual != required:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"obligations/{_obligation_id(obligation)}/amount_required_cents"),
                        f"obligation {_obligation_id(obligation)} states amount {fmt(actual)}; "
                        f"the statutory fixed amount for form {_text(obligation, 'form')} is "
                        f"{fmt(required)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} fixed-amount payments are the statutory constant")
        )
    return out


# --------------------------------------------------------------------------- #
# evd_ -- the register ties to the evidence, and the evidence to the register
# --------------------------------------------------------------------------- #
def _evidence_kinds_for(ctx: Context) -> dict[str, set[str]]:
    """Map obligation_id -> the set of evidence kinds on file for it."""
    out: dict[str, set[str]] = {}
    for row in _evidence(ctx):
        oid = _text(row, "obligation_id")
        kind = _text(row, "kind")
        if oid and kind:
            out.setdefault(oid, set()).add(kind)
    return out


@check("evd_filed_has_evidence")
def check_evd_filed_has_evidence(ctx: Context) -> list[Finding]:
    """Every filed obligation is backed by a filed-return or payment voucher.

    A row marked filed with no archived evidence is a claim the file cannot
    support: the reviewer sees "filed" and there is nothing behind it.
    """
    rule = "evd_filed_has_evidence"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    evidence = ctx.one(DOC_EVIDENCE_INDEX)
    if register is None or evidence is None:
        return []
    kinds = _evidence_kinds_for(ctx)
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        if _parse_date(obligation.get("return_filed")) is None:
            continue
        checked += 1
        on_file = kinds.get(_obligation_id(obligation), set())
        if not (on_file & set(FILING_EVIDENCE_KINDS)):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(evidence, f"evidence/{_obligation_id(obligation)}"),
                    f"obligation {_obligation_id(obligation)} is marked filed but no "
                    f"filed-return or payment voucher is on file for it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} filed obligations are backed by evidence")
        )
    return out


@check("evd_extension_evidence")
def check_evd_extension_evidence(ctx: Context) -> list[Finding]:
    """Every extension-filed obligation is backed by an extension acceptance.

    A deferral is only as good as the acceptance that granted it. An obligation
    marked extension-filed with no acceptance on file has no proof the deadline
    actually moved.
    """
    rule = "evd_extension_evidence"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    evidence = ctx.one(DOC_EVIDENCE_INDEX)
    if register is None or evidence is None:
        return []
    kinds = _evidence_kinds_for(ctx)
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        if not bool(obligation.get("extension_filed")):
            continue
        checked += 1
        if EVIDENCE_EXTENSION not in kinds.get(_obligation_id(obligation), set()):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(evidence, f"evidence/{_obligation_id(obligation)}"),
                    f"obligation {_obligation_id(obligation)} is marked extension-filed but no "
                    f"extension acceptance is on file for it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} extensions are backed by an acceptance")
        )
    return out


@check("evd_no_orphan_evidence")
def check_evd_no_orphan_evidence(ctx: Context) -> list[Finding]:
    """Every piece of evidence points at an obligation in the register.

    A voucher or acceptance whose obligation is not in the register is an orphan:
    a piece of "done" that no row claims, so the completeness count cannot be
    trusted in either direction. The evidence kind is also gated to the known set.
    """
    rule = "evd_no_orphan_evidence"
    _sev(rule, Status.FAIL)
    evidence = ctx.one(DOC_EVIDENCE_INDEX)
    if evidence is None:
        return []
    obligations = _obligation_map(ctx)
    out: list[Finding] = []
    for row in _evidence(ctx):
        eid = _text(row, "evidence_id") or "?"
        oid = _text(row, "obligation_id")
        kind = _text(row, "kind")
        if oid is None or oid not in obligations:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(evidence, f"evidence/{eid}/obligation_id"),
                    f"evidence {eid} points at obligation {oid!r}, which is not in the "
                    f"register; it is an orphan with no row to claim it",
                )
            )
        elif kind not in EVIDENCE_KINDS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(evidence, f"evidence/{eid}/kind"),
                    f"evidence {eid} is of kind {kind!r}, which is not one of "
                    f"{EVIDENCE_KINDS}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_evidence(ctx))} evidence rows tie to a register obligation")
        )
    return out


# --------------------------------------------------------------------------- #
# ros_ -- the roster is complete and every obligation is attributable
# --------------------------------------------------------------------------- #
@check("ros_entity_has_row")
def check_ros_entity_has_row(ctx: Context) -> list[Finding]:
    """Every active entity in the roster carries at least one obligation.

    The roster is the completeness source: an active entity with no obligation row
    is an entity whose filings nobody is tracking, and it would never show up in
    any downstream control because it has no row to be checked.
    """
    rule = "ros_entity_has_row"
    _sev(rule, Status.FAIL)
    roster = ctx.one(DOC_ENTITY_ROSTER)
    if roster is None:
        return []
    with_rows = {_text(o, "entity_id") for o in _obligations(ctx)}
    out: list[Finding] = []
    checked = 0
    for entity in _entities(ctx):
        if not bool(entity.get("active")):
            continue
        checked += 1
        if _entity_id(entity) not in with_rows:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roster, f"entities/{_entity_id(entity)}"),
                    f"active entity {_entity_id(entity)} carries no obligation row; its "
                    f"filings are untracked",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} active entities carry at least one obligation")
        )
    return out


@check("ros_row_entity_known")
def check_ros_row_entity_known(ctx: Context) -> list[Finding]:
    """Every obligation names an entity in the roster."""
    rule = "ros_row_entity_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    known = _entity_ids(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"obligations/{_obligation_id(o)}/entity_id"),
            f"obligation {_obligation_id(o)} names entity {_text(o, 'entity_id')!r}, which "
            f"is not in the roster",
        )
        for o in _obligations(ctx)
        if _text(o, "entity_id") and _text(o, "entity_id") not in known
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every obligation names an entity in the roster")
        )
    return out


@check("ros_unique_obligation_ids")
def check_ros_unique_obligation_ids(ctx: Context) -> list[Finding]:
    """No obligation id appears twice.

    The obligation id joins the register to the evidence and to the status
    summary. A duplicate makes a voucher ambiguous about which obligation it
    proves and a status ambiguous about which row it reports.
    """
    rule = "ros_unique_obligation_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _obligations(ctx):
        seen[_obligation_id(row)] = seen.get(_obligation_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"obligations/{oid}"),
            f"obligation id {oid} appears {count} times; a voucher or status that names "
            f"it cannot be attributed to one obligation",
        )
        for oid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} obligation ids are unique")
        )
    return out


# --------------------------------------------------------------------------- #
# wfl_ -- the internal workflow schedule
# --------------------------------------------------------------------------- #
def _workflow_dates(obligation: dict[str, Any]) -> dict[str, date | None]:
    return {
        "prep_goal": _parse_date(obligation.get("prep_goal")),
        "review_goal": _parse_date(obligation.get("review_goal")),
        "sent_goal": _parse_date(obligation.get("sent_goal")),
    }


@check("wfl_goal_monotonic")
def check_wfl_goal_monotonic(ctx: Context) -> list[Finding]:
    """The internal workflow goals run in order and land before the deadline.

    Prep before review before sent-to-preparer, and the last of them on or before
    the applicable due date. A schedule that runs backwards is not a plan; it is a
    deadline nobody can meet, hidden as three tidy dates.
    """
    rule = "wfl_goal_monotonic"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        goals = _workflow_dates(obligation)
        prep, review, sent = goals["prep_goal"], goals["review_goal"], goals["sent_goal"]
        if prep is None or review is None or sent is None:
            continue  # no internal schedule to order
        checked += 1
        the_due = _stored_applicable_due(obligation)
        ok = prep <= review <= sent and (the_due is None or sent <= the_due)
        if not ok:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"obligations/{_obligation_id(obligation)}/review_goal"),
                    f"obligation {_obligation_id(obligation)} workflow goals are out of order: "
                    f"prep {prep.isoformat()}, review {review.isoformat()}, sent "
                    f"{sent.isoformat()}, due "
                    f"{the_due.isoformat() if the_due else 'n/a'}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} workflow schedules run in order")
        )
    return out


@check("wfl_actual_slippage")
def check_wfl_actual_slippage(ctx: Context) -> list[Finding]:
    """An internal workflow step completed after its goal is flagged.

    A FLAG, not a failure: slipping an internal prep or review goal does not miss
    a statutory deadline, but it is the early warning that one is about to be
    missed, and it is worth a human's eyes.
    """
    rule = "wfl_actual_slippage"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    if register is None:
        return []
    steps = (
        ("prep_goal", "prep_actual", "prep"),
        ("review_goal", "review_actual", "review"),
        ("sent_goal", "sent_actual", "sent-to-preparer"),
    )
    out: list[Finding] = []
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        for goal_key, actual_key, label in steps:
            goal = _parse_date(obligation.get(goal_key))
            actual = _parse_date(obligation.get(actual_key))
            if goal is None or actual is None:
                continue
            if actual > goal:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"obligations/{_obligation_id(obligation)}/{actual_key}"),
                        f"obligation {_obligation_id(obligation)} {label} completed "
                        f"{actual.isoformat()}, after its goal {goal.isoformat()}; the "
                        f"schedule is slipping",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every workflow actual met its goal")
        )
    return out


# --------------------------------------------------------------------------- #
# cnt_ -- cross-year continuity
# --------------------------------------------------------------------------- #
@check("cnt_final_not_recurring")
def check_cnt_final_not_recurring(ctx: Context) -> list[Finding]:
    """An entity marked FINAL in the prior year carries no live obligation now.

    A final return dissolves an entity's filing obligation. If the prior year's
    register flagged an entity final and it reappears this year with a live (not
    n/a) obligation, either the dissolution was wrong or the obligation is.
    """
    rule = "cnt_final_not_recurring"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_OBLIGATION_REGISTER)
    prior = ctx.one(DOC_PRIOR_YEAR_REGISTER)
    if register is None or prior is None:
        return []
    final = _prior_final(ctx)
    live: dict[str, list[str]] = {}
    for obligation in _obligations(ctx):
        if _is_na(obligation):
            continue
        entity = _text(obligation, "entity_id")
        if entity in final:
            live.setdefault(entity, []).append(_obligation_id(obligation))
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"obligations/{entity}"),
            f"entity {entity} was marked FINAL in the prior fiscal year but carries live "
            f"obligations this year: {', '.join(sorted(oids))}",
        )
        for entity, oids in sorted(live.items())
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"no prior-year final entity ({len(final)}) recurs with a live obligation")
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the roll-up recomputes from the register
# --------------------------------------------------------------------------- #
@check("rpt_status_recomputes")
def check_rpt_status_recomputes(ctx: Context) -> list[Finding]:
    """Each obligation's stated status recomputes from its register dates.

    This is the control the engine exists for. The status summary is a
    determination, and a determination that is not recomputed from the register is
    an assertion. The engine rebuilds every status from the obligation's dates and
    compares.
    """
    rule = "rpt_status_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_STATUS_SUMMARY)
    as_of = _parse_date(ctx.as_of)
    if summary is None or as_of is None:
        return []
    obligations = _obligation_map(ctx)
    out: list[Finding] = []
    for row in _rows(summary, "obligations"):
        oid = _text(row, "obligation_id")
        obligation = obligations.get(oid or "")
        if obligation is None:
            continue
        stated = row.get("status")
        recomputed = recompute_status(ctx, obligation, as_of)
        if recomputed != stated:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, f"obligations/{oid}/status"),
                    f"obligation {oid} is summarised status={stated!r}; recomputing from its "
                    f"register dates gives status={recomputed!r}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every obligation status recomputes from the register")
        )
    return out


@check("rpt_counts_tie")
def check_rpt_counts_tie(ctx: Context) -> list[Finding]:
    """The summary's overdue and filed counts tie the register.

    The numbers that reach a controller are counts, and a count maintained beside
    the register rather than derived from it drifts the first time a status moves
    and nobody re-adds the column.
    """
    rule = "rpt_counts_tie"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_STATUS_SUMMARY)
    as_of = _parse_date(ctx.as_of)
    if summary is None or as_of is None:
        return []
    overdue = recompute_overdue_count(ctx, as_of)
    filed = recompute_filed_count(ctx, as_of)
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_overdue = require_cents(
            "status_summary.overdue_count", summary.get("overdue_count"), unit="a whole count"
        )
        stated_filed = require_cents(
            "status_summary.filed_count", summary.get("filed_count"), unit="a whole count"
        )
        if stated_overdue != overdue or stated_filed != filed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, "overdue_count"),
                    f"the summary states {stated_overdue} overdue / {stated_filed} filed; the "
                    f"register recomputes {overdue} / {filed}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the summary counts of {overdue} overdue / {filed} filed tie the register",
                )
            )
    return out


@check("rpt_watchlist_ties")
def check_rpt_watchlist_ties(ctx: Context) -> list[Finding]:
    """The due-soon watchlist ties the register.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists an obligation not actually due -- or omits one that is --
    sends the follow-up to the wrong place. It is rebuilt from the register and
    compared.
    """
    rule = "rpt_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_DUE_WATCHLIST)
    as_of = _parse_date(ctx.as_of)
    if watchlist is None or as_of is None:
        return []
    recomputed = [_normalize_entry(e) for e in recompute_watchlist(ctx, as_of, ctx.due_lead_days)]
    stated = [_normalize_entry(e) for e in _rows(watchlist, "entries")]
    out: list[Finding] = []
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
                        f"the watchlist lists obligation {entry[0]} as due soon, but it is not "
                        f"inside the lead-time window as of {as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"obligation {entry[0]} falls due within the lead-time window but is "
                        f"not on the watchlist",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the due-soon watchlist ties the register")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one calendar file."""
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
    """Analyze every ``.json`` calendar file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of calendar-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
