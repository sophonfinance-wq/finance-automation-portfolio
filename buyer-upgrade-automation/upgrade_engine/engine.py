"""
Buyer upgrade control engine (READ-ONLY).
=========================================

Loads each upgrade book (a ``.json`` file produced by
:mod:`upgrade_engine.generate`) and runs an ordered *registry* of independent
controls over it.

The shape of the problem
------------------------
A buyer pays for an upgrade months before the home closes. That money is not
revenue when it arrives -- it is a liability, and it stays one until the unit
actually closes. Between those two dates the same figure has to appear
consistently in four places maintained by different people on different cadences:
the closings schedule, the general ledger, the cost-to-complete report and the
proforma.

So the failure mode is almost never a wrong number. It is the *same* number
failing to move everywhere at once. The registry is organised around that:

1. ``set_``  -- is the book complete enough to be worth reading?
2. ``unit_`` -- does every upgrade belong to a real unit, exactly once?
3. ``def_``  -- is deferred revenue released when the unit closes, and only then?
4. ``cos_``  -- does the closing entry balance, and is cost coded where it belongs?
5. ``tax_``  -- is sales tax carried as a liability rather than as revenue?
6. ``tie_``  -- do the four schedules agree with each other?
7. ``flag_`` -- has the budgeted/actual marker kept up with reality?

Design notes
------------
- **Strictly read-only.** Books are parsed and never written back. The engine is
  incapable of *introducing* a defect -- it can only report.
- **Deterministic.** Same inputs, same findings, in the same order. Every dict
  and set iteration is forced through ``sorted()`` with a tiebreaker.
- **Integer cents, no tolerance.** Amounts are compared with exact ``==``. A
  value that should be integer cents but is not produces an ``AMOUNT_INVALID``
  finding -- at the owning rule's declared severity, contained to the one row it
  was read on -- rather than being coerced.
- **Absent evidence is not a passing control.** ``set_complete`` runs first and
  fails a book that does not carry every artifact the registry reads.

The revenue timing rule
-----------------------
Recognition is gated on the close of escrow date, not on the upgrade being
finished, invoiced or paid for. A buyer can pay in full, the work can be
complete, and the revenue still belongs in the liability until the unit closes.
That is the single rule most likely to be got wrong by a spreadsheet that is
being kept up to date by hand, because every other signal says the money is
earned.
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
    ACCT_CONTRA_WIP,
    ACCT_COST_OF_SALES,
    ACCT_REVENUE,
    ACCT_SALES_TAX,
    ACCT_UNEARNED,
    DOC_CLOSINGS_SCHEDULE,
    DOC_COST_TO_COMPLETE,
    DOC_LEDGER_BALANCES,
    DOC_PROFORMA,
    DOC_TYPES,
    DOC_UPGRADE_REGISTER,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import (
    AmountInvalidError,
    apply_rate,
    fmt,
    percent_complete_bps,
    require_cents,
)

# --------------------------------------------------------------------------- #
# Check registry
# --------------------------------------------------------------------------- #
CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs. Order is preserved so the
#: report is deterministic.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule. Read by :func:`amount_invalid_finding` so a
#: schema defect can never be more severe than the control that tripped over it.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~upgrade_engine.money.AmountInvalidError` as a finding."""
    return Finding(
        rule_id,
        SEVERITY.get(rule_id, Status.FAIL),
        f"amount:{exc.field}",
        f"{exc} -- amounts are integer cents and are never coerced",
    )


@contextlib.contextmanager
def amount_guard(rule_id: str, out: list[Finding]) -> Iterator[None]:
    """Contain a malformed amount to the **one row** being read.

    Guarding the whole check body instead would abort the remaining iterations
    silently -- one malformed price would end the tie-out for an entire register,
    and the report would show no exception for the rows never examined.
    """
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


_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
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


def _balances(ctx: Context) -> dict[str, int]:
    """Ledger balances keyed by account, skipping unreadable ones."""
    doc = ctx.one(DOC_LEDGER_BALANCES)
    out: dict[str, int] = {}
    for row in _rows(doc, "accounts"):
        name = row.get("account")
        try:
            out[str(name)] = require_cents(f"ledger.{name}", row.get("balance_cents"))
        except AmountInvalidError:
            continue
    return out


# --------------------------------------------------------------------------- #
# 1. set_* -- structural preconditions
# --------------------------------------------------------------------------- #
@check("set_complete")
def set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the registry reads must be present, exactly once."""
    rule = "set_complete"
    _sev(rule, Status.FAIL)
    out: list[Finding] = []
    for doc_type in DOC_TYPES:
        found = ctx.docs(doc_type)
        if not found:
            out.append(Finding(rule, Status.FAIL, f"book:{ctx.book_id}/{doc_type}",
                               f"book carries no {doc_type}; absent evidence is not a "
                               f"passing control, so no downstream rule may read it"))
        elif len(found) > 1:
            out.append(Finding(rule, Status.FAIL, f"book:{ctx.book_id}/{doc_type}",
                               f"book carries {len(found)} {doc_type} documents; exactly "
                               f"one is expected and the rules read the first"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(DOC_TYPES)} artifact types present exactly once"))
    return out


@check("set_period_aligned")
def set_period_aligned(ctx: Context) -> list[Finding]:
    """Every dated artifact must describe the same accounting period."""
    rule = "set_period_aligned"
    _sev(rule, Status.FAIL)
    if not _PERIOD_RE.match(ctx.period):
        return [Finding(rule, Status.FAIL, f"book:{ctx.book_id}/period",
                        f"book period {ctx.period!r} is not a YYYY-MM label")]
    out: list[Finding] = []
    for doc in ctx.documents:
        declared = doc.get("period")
        if declared is not None and declared != ctx.period:
            out.append(Finding(rule, Status.FAIL, ctx.loc(doc, "period"),
                               f"document period {declared!r} does not match the book "
                               f"period {ctx.period!r}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"every dated artifact declares period {ctx.period}"))
    return out


# --------------------------------------------------------------------------- #
# 2. unit_* -- unit integrity
# --------------------------------------------------------------------------- #
@check("unit_upgrade_maps_to_a_unit")
def unit_upgrade_maps_to_a_unit(ctx: Context) -> list[Finding]:
    """Every upgrade order must reference a unit on the closings schedule.

    An upgrade billed against a unit that is not in the schedule has nowhere to
    be recognised: there is no close date to release it, so it would sit in
    deferred revenue forever without anyone noticing it was orphaned.
    """
    rule = "unit_upgrade_maps_to_a_unit"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    register = ctx.one(DOC_UPGRADE_REGISTER)
    if schedule is None or register is None:
        return []
    known = {str(u.get("unit")) for u in _rows(schedule, "units")}
    out: list[Finding] = []
    checked = 0
    for order in _rows(register, "orders"):
        checked += 1
        unit = str(order.get("unit"))
        if unit not in known:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(register, f"orders/{order.get('order_id')}/unit"),
                               f"upgrade order {order.get('order_id')} references unit "
                               f"{unit!r}, which is not on the closings schedule"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} upgrade orders map to a scheduled unit"))
    return out


@check("unit_no_duplicate_orders")
def unit_no_duplicate_orders(ctx: Context) -> list[Finding]:
    """The same upgrade order id must not appear twice.

    A duplicated order double-counts both the liability and, once the unit
    closes, the revenue.
    """
    rule = "unit_no_duplicate_orders"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UPGRADE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for order in _rows(register, "orders"):
        oid = str(order.get("order_id"))
        seen[oid] = seen.get(oid, 0) + 1
    out = [
        Finding(rule, Status.FAIL, ctx.loc(register, f"orders/{oid}"),
                f"upgrade order {oid} appears {n} times; a duplicate double-counts "
                f"both the liability and the revenue it becomes")
        for oid, n in sorted(seen.items()) if n > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(seen)} upgrade order ids are unique"))
    return out


@check("unit_closed_has_close_date")
def unit_closed_has_close_date(ctx: Context) -> list[Finding]:
    """A unit marked closed must carry a close-of-escrow date.

    The date is what every recognition rule keys on, so a unit flagged closed
    without one cannot be shown to have been recognised in the right period.
    """
    rule = "unit_closed_has_close_date"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    closed = 0
    for unit in _rows(schedule, "units"):
        if not unit.get("closed"):
            continue
        closed += 1
        if _parse_date(unit.get("close_date")) is None:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(schedule, f"units/{unit.get('unit')}/close_date"),
                               f"unit {unit.get('unit')} is marked closed but carries no "
                               f"readable close-of-escrow date"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {closed} closed unit(s) carry a close date"))
    return out


# --------------------------------------------------------------------------- #
# 3. def_* -- deferred revenue lifecycle
# --------------------------------------------------------------------------- #
@check("def_released_only_on_close")
def def_released_only_on_close(ctx: Context) -> list[Finding]:
    """Upgrade revenue is recognised when the unit closes, and not before.

    This is the rule a hand-maintained schedule is most likely to get wrong,
    because every other signal says the money is earned: the buyer has paid, the
    work is finished, the invoice is settled. None of that recognises revenue.
    Close of escrow does.
    """
    rule = "def_released_only_on_close"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _rows(schedule, "units"):
        uid = unit.get("unit")
        with amount_guard(rule, out):
            recognised = require_cents(f"schedule.units[{uid}].revenue_recognised_cents",
                                       unit.get("revenue_recognised_cents"))
            deferred = require_cents(f"schedule.units[{uid}].deferred_balance_cents",
                                     unit.get("deferred_balance_cents"))
            checked += 1
            is_closed = bool(unit.get("closed"))
            if not is_closed and recognised != 0:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(schedule, f"units/{uid}/revenue_recognised_cents"),
                                   f"unit {uid} has not closed but {fmt(recognised)} of "
                                   f"upgrade revenue is already recognised; the money is a "
                                   f"liability until close of escrow"))
            if is_closed and deferred != 0:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(schedule, f"units/{uid}/deferred_balance_cents"),
                                   f"unit {uid} closed but {fmt(deferred)} remains in "
                                   f"deferred revenue; closing releases the whole balance"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"recognition follows close of escrow across {checked} units"))
    return out


@check("def_unit_total_is_deposit")
def def_unit_total_is_deposit(ctx: Context) -> list[Finding]:
    """Each unit's recognised plus deferred must equal what the buyer contracted.

    Nothing may leak between the two buckets: an upgrade is either still owed to
    the buyer as work, or earned. There is no third place for it to be.
    """
    rule = "def_unit_total_is_deposit"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    register = ctx.one(DOC_UPGRADE_REGISTER)
    if schedule is None or register is None:
        return []
    out: list[Finding] = []
    contracted: dict[str, int] = {}
    for order in _rows(register, "orders"):
        unit = str(order.get("unit"))
        with amount_guard(rule, out):
            contracted[unit] = contracted.get(unit, 0) + require_cents(
                f"register.orders[{order.get('order_id')}].price_cents",
                order.get("price_cents"))
    checked = 0
    for unit in _rows(schedule, "units"):
        uid = str(unit.get("unit"))
        with amount_guard(rule, out):
            recognised = require_cents(f"schedule.units[{uid}].revenue_recognised_cents",
                                       unit.get("revenue_recognised_cents"))
            deferred = require_cents(f"schedule.units[{uid}].deferred_balance_cents",
                                     unit.get("deferred_balance_cents"))
            expected = contracted.get(uid, 0)
            checked += 1
            if recognised + deferred != expected:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(schedule, f"units/{uid}"),
                                   f"unit {uid}: recognised {fmt(recognised)} + deferred "
                                   f"{fmt(deferred)} = {fmt(recognised + deferred)}, but "
                                   f"the register contracts {fmt(expected)} of upgrades"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"recognised plus deferred equals contracted on {checked} units"))
    return out


@check("def_schedule_ties_ledger")
def def_schedule_ties_ledger(ctx: Context) -> list[Finding]:
    """The schedule's deferred total must equal the unearned-revenue ledger balance.

    This is the month-end comparison the procedure calls for by name, and it is
    the one that catches a release posted in one place and not the other.
    """
    rule = "def_schedule_ties_ledger"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    total = 0
    for unit in _rows(schedule, "units"):
        with amount_guard(rule, out):
            total += require_cents(
                f"schedule.units[{unit.get('unit')}].deferred_balance_cents",
                unit.get("deferred_balance_cents"))
    balances = _balances(ctx)
    if ACCT_UNEARNED not in balances:
        return out + [Finding(rule, Status.FAIL, f"book:{ctx.book_id}/{ACCT_UNEARNED}",
                              f"no ledger balance for {ACCT_UNEARNED}; the schedule cannot "
                              f"be shown to tie to anything")]
    actual = balances[ACCT_UNEARNED]
    if total != actual:
        out.append(Finding(rule, Status.FAIL, f"ledger:{ACCT_UNEARNED}",
                           f"the closings schedule carries {fmt(total)} of deferred upgrade "
                           f"revenue but the ledger balance is {fmt(actual)} "
                           f"(difference {fmt(total - actual)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"schedule deferred total ties the ledger at {fmt(total)}"))
    return out


@check("def_revenue_ties_ledger")
def def_revenue_ties_ledger(ctx: Context) -> list[Finding]:
    """Recognised revenue on the schedule must equal the revenue ledger balance."""
    rule = "def_revenue_ties_ledger"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    total = 0
    for unit in _rows(schedule, "units"):
        with amount_guard(rule, out):
            total += require_cents(
                f"schedule.units[{unit.get('unit')}].revenue_recognised_cents",
                unit.get("revenue_recognised_cents"))
    balances = _balances(ctx)
    if ACCT_REVENUE not in balances:
        return out + [Finding(rule, Status.FAIL, f"book:{ctx.book_id}/{ACCT_REVENUE}",
                              f"no ledger balance for {ACCT_REVENUE}")]
    actual = balances[ACCT_REVENUE]
    if total != actual:
        out.append(Finding(rule, Status.FAIL, f"ledger:{ACCT_REVENUE}",
                           f"the schedule recognises {fmt(total)} of upgrade revenue but "
                           f"the ledger carries {fmt(actual)} "
                           f"(difference {fmt(total - actual)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"recognised revenue ties the ledger at {fmt(total)}"))
    return out


# --------------------------------------------------------------------------- #
# 4. cos_* -- the closing entry
# --------------------------------------------------------------------------- #
@check("cos_entry_balances")
def cos_entry_balances(ctx: Context) -> list[Finding]:
    """Cost of sales debited must equal the contra-WIP credited.

    The closing entry moves accumulated cost out of work in progress and into
    cost of sales. It is one entry with two equal halves; if they differ, cost
    has been created or destroyed rather than reclassified.
    """
    rule = "cos_entry_balances"
    _sev(rule, Status.FAIL)
    balances = _balances(ctx)
    missing = [a for a in (ACCT_COST_OF_SALES, ACCT_CONTRA_WIP) if a not in balances]
    if missing:
        return [Finding(rule, Status.FAIL, f"book:{ctx.book_id}/ledger",
                        f"no ledger balance for {', '.join(missing)}; the closing entry "
                        f"cannot be shown to balance")]
    debit = balances[ACCT_COST_OF_SALES]
    credit = balances[ACCT_CONTRA_WIP]
    # Contra-WIP is carried as a credit, i.e. negative, so the two must sum to zero.
    if debit + credit != 0:
        return [Finding(rule, Status.FAIL, f"ledger:{ACCT_CONTRA_WIP}",
                        f"cost of sales {fmt(debit)} and contra work-in-progress "
                        f"{fmt(credit)} do not offset (net {fmt(debit + credit)}); the "
                        f"closing entry reclassifies cost, it does not create it")]
    return [Finding(rule, Status.PASS, "-",
                    f"cost of sales and contra-WIP offset exactly at {fmt(debit)}")]


@check("cos_only_closed_units_costed")
def cos_only_closed_units_costed(ctx: Context) -> list[Finding]:
    """Cost of sales is taken only for units that have closed.

    Cost follows revenue. Relieving work in progress before the unit closes
    overstates cost of sales in one period and understates it in the next.
    """
    rule = "cos_only_closed_units_costed"
    _sev(rule, Status.FAIL)
    ctc = ctx.one(DOC_COST_TO_COMPLETE)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if ctc is None or schedule is None:
        return []
    closed = {str(u.get("unit")) for u in _rows(schedule, "units") if u.get("closed")}
    out: list[Finding] = []
    checked = 0
    for row in _rows(ctc, "units"):
        uid = str(row.get("unit"))
        with amount_guard(rule, out):
            relieved = require_cents(f"ctc.units[{uid}].cost_of_sales_cents",
                                     row.get("cost_of_sales_cents"))
            checked += 1
            if relieved != 0 and uid not in closed:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(ctc, f"units/{uid}/cost_of_sales_cents"),
                                   f"unit {uid} has {fmt(relieved)} relieved to cost of "
                                   f"sales but has not closed; cost follows revenue"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"cost of sales taken only on closed units across {checked} rows"))
    return out


@check("cos_costs_within_committed")
def cos_costs_within_committed(ctx: Context) -> list[Finding]:
    """Costs to date must not exceed the committed cost without a change order.

    An overrun is not automatically wrong -- it is unapproved that makes it
    wrong. This flags rather than fails, because the resolution is a change
    order somebody has to execute, not an arithmetic correction.
    """
    rule = "cos_costs_within_committed"
    _sev(rule, Status.FLAG)
    ctc = ctx.one(DOC_COST_TO_COMPLETE)
    if ctc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rows(ctc, "units"):
        uid = str(row.get("unit"))
        with amount_guard(rule, out):
            committed = require_cents(f"ctc.units[{uid}].committed_cost_cents",
                                      row.get("committed_cost_cents"))
            to_date = require_cents(f"ctc.units[{uid}].costs_to_date_cents",
                                    row.get("costs_to_date_cents"))
            checked += 1
            if to_date > committed:
                pct = percent_complete_bps(to_date, committed)
                out.append(Finding(rule, Status.FLAG,
                                   ctx.loc(ctc, f"units/{uid}/costs_to_date_cents"),
                                   f"unit {uid} has incurred {fmt(to_date)} against a "
                                   f"committed cost of {fmt(committed)} "
                                   f"({pct / 100:.2f}%); an executed change order should "
                                   f"raise the commitment before the cost lands"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"costs to date are within committed cost on {checked} units"))
    return out


@check("cos_change_order_referenced")
def cos_change_order_referenced(ctx: Context) -> list[Finding]:
    """A committed cost above the original budget needs a change order reference."""
    rule = "cos_change_order_referenced"
    _sev(rule, Status.FLAG)
    ctc = ctx.one(DOC_COST_TO_COMPLETE)
    if ctc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rows(ctc, "units"):
        uid = str(row.get("unit"))
        with amount_guard(rule, out):
            budget = require_cents(f"ctc.units[{uid}].budgeted_cost_cents",
                                   row.get("budgeted_cost_cents"))
            committed = require_cents(f"ctc.units[{uid}].committed_cost_cents",
                                      row.get("committed_cost_cents"))
            checked += 1
            ref = row.get("change_order_ref")
            if committed != budget and not (isinstance(ref, str) and ref.strip()):
                out.append(Finding(rule, Status.FLAG,
                                   ctx.loc(ctc, f"units/{uid}/change_order_ref"),
                                   f"unit {uid} is committed at {fmt(committed)} against a "
                                   f"budget of {fmt(budget)} with no change order "
                                   f"referenced"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"every commitment change carries a reference across "
                           f"{checked} units"))
    return out


# --------------------------------------------------------------------------- #
# 5. tax_* -- sales tax
# --------------------------------------------------------------------------- #
@check("tax_derived_from_rate")
def tax_derived_from_rate(ctx: Context) -> list[Finding]:
    """Sales tax on each order must equal the taxable base at the declared rate.

    Derived with the same truncating basis-point arithmetic the order itself
    uses, so the reported line and the derived line compare with exact equality.
    """
    rule = "tax_derived_from_rate"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UPGRADE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    rate = register.get("sales_tax_rate_bps")
    if not isinstance(rate, int) or isinstance(rate, bool):
        return [Finding(rule, Status.FAIL, ctx.loc(register, "sales_tax_rate_bps"),
                        "the register declares no integer basis-point sales tax rate, so "
                        "no tax line in it can be shown to be correct")]
    checked = 0
    for order in _rows(register, "orders"):
        oid = order.get("order_id")
        with amount_guard(rule, out):
            price = require_cents(f"register.orders[{oid}].price_cents",
                                  order.get("price_cents"))
            tax = require_cents(f"register.orders[{oid}].sales_tax_cents",
                                order.get("sales_tax_cents"))
            checked += 1
            expected = apply_rate(price, rate)
            if tax != expected:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(register, f"orders/{oid}/sales_tax_cents"),
                                   f"order {oid}: {fmt(price)} at {rate / 100:.2f}% derives "
                                   f"{fmt(expected)} of sales tax, but {fmt(tax)} is "
                                   f"recorded"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"sales tax derives correctly on all {checked} orders"))
    return out


@check("tax_not_recognised_as_revenue")
def tax_not_recognised_as_revenue(ctx: Context) -> list[Finding]:
    """Sales tax collected is a liability, never upgrade revenue.

    Folding tax into the revenue figure inflates the top line and understates
    what is owed to the taxing authority -- and because both move together, the
    schedule still foots.
    """
    rule = "tax_not_recognised_as_revenue"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UPGRADE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    tax_total = 0
    for order in _rows(register, "orders"):
        with amount_guard(rule, out):
            tax_total += require_cents(
                f"register.orders[{order.get('order_id')}].sales_tax_cents",
                order.get("sales_tax_cents"))
    balances = _balances(ctx)
    if ACCT_SALES_TAX not in balances:
        return out + [Finding(rule, Status.FAIL, f"book:{ctx.book_id}/{ACCT_SALES_TAX}",
                              f"no ledger balance for {ACCT_SALES_TAX}")]
    actual = balances[ACCT_SALES_TAX]
    if tax_total != actual:
        out.append(Finding(rule, Status.FAIL, f"ledger:{ACCT_SALES_TAX}",
                           f"orders carry {fmt(tax_total)} of sales tax but the liability "
                           f"account holds {fmt(actual)}; tax collected is owed onward, "
                           f"not earned"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"sales tax of {fmt(tax_total)} sits in the liability account"))
    return out


# --------------------------------------------------------------------------- #
# 6. tie_* -- the four schedules must agree
# --------------------------------------------------------------------------- #
@check("tie_ctc_revenue_to_proforma")
def tie_ctc_revenue_to_proforma(ctx: Context) -> list[Finding]:
    """Net upgrade revenue on the cost-to-complete must equal proforma income."""
    rule = "tie_ctc_revenue_to_proforma"
    _sev(rule, Status.FAIL)
    ctc = ctx.one(DOC_COST_TO_COMPLETE)
    proforma = ctx.one(DOC_PROFORMA)
    if ctc is None or proforma is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        on_ctc = require_cents("ctc.totals.net_upgrade_revenue_cents",
                               (ctc.get("totals") or {}).get("net_upgrade_revenue_cents"))
        on_pf = require_cents("proforma.upgrade_income_cents",
                              proforma.get("upgrade_income_cents"))
        if on_ctc != on_pf:
            out.append(Finding(rule, Status.FAIL, ctx.loc(proforma, "upgrade_income_cents"),
                               f"the cost-to-complete reports {fmt(on_ctc)} of net upgrade "
                               f"revenue; the proforma carries {fmt(on_pf)} "
                               f"(difference {fmt(on_ctc - on_pf)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "cost-to-complete revenue ties the proforma"))
    return out


@check("tie_ctc_costs_to_proforma")
def tie_ctc_costs_to_proforma(ctx: Context) -> list[Finding]:
    """Costs to date on the cost-to-complete must equal the proforma's job-cost line.

    The two carry opposite signs by convention: the cost-to-complete states cost
    as a positive figure, while the proforma posts it to a job-cost line as a
    negative, so that income and cost can simply be summed on the variance tab.
    The comparison therefore negates one side. Comparing them raw would make the
    control fire on every correctly-prepared book -- and, worse, hold on one where
    somebody had entered the cost with the wrong sign.
    """
    rule = "tie_ctc_costs_to_proforma"
    _sev(rule, Status.FAIL)
    ctc = ctx.one(DOC_COST_TO_COMPLETE)
    proforma = ctx.one(DOC_PROFORMA)
    if ctc is None or proforma is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        on_ctc = require_cents("ctc.totals.costs_to_date_cents",
                               (ctc.get("totals") or {}).get("costs_to_date_cents"))
        on_pf = require_cents("proforma.upgrade_costs_to_date_cents",
                              proforma.get("upgrade_costs_to_date_cents"))
        if on_ctc != -on_pf:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(proforma, "upgrade_costs_to_date_cents"),
                               f"the cost-to-complete reports {fmt(on_ctc)} of costs to "
                               f"date; the proforma's upgrade job-cost line carries "
                               f"{fmt(on_pf)}, which negates to {fmt(-on_pf)} "
                               f"(difference {fmt(on_ctc + on_pf)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "cost-to-complete costs tie the proforma job-cost line"))
    return out


@check("tie_proforma_to_variance")
def tie_proforma_to_variance(ctx: Context) -> list[Finding]:
    """Proforma upgrade income plus its cost line must equal the variance tab.

    The last link in the chain. Each of the three ties can hold on its own while
    the summary the reader actually looks at disagrees with all of them.
    """
    rule = "tie_proforma_to_variance"
    _sev(rule, Status.FAIL)
    proforma = ctx.one(DOC_PROFORMA)
    if proforma is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        income = require_cents("proforma.upgrade_income_cents",
                               proforma.get("upgrade_income_cents"))
        costs = require_cents("proforma.upgrade_costs_to_date_cents",
                              proforma.get("upgrade_costs_to_date_cents"))
        variance = require_cents("proforma.variance_tab_net_cents",
                                 proforma.get("variance_tab_net_cents"))
        # Costs are carried as a negative on the proforma line, so the net is a sum.
        if income + costs != variance:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(proforma, "variance_tab_net_cents"),
                               f"upgrade income {fmt(income)} plus the job-cost line "
                               f"{fmt(costs)} = {fmt(income + costs)}, but the variance tab "
                               f"shows {fmt(variance)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "the proforma reconciles to its own variance tab"))
    return out


@check("tie_ctc_units_foot")
def tie_ctc_units_foot(ctx: Context) -> list[Finding]:
    """The cost-to-complete totals must foot from its own unit rows."""
    rule = "tie_ctc_units_foot"
    _sev(rule, Status.FAIL)
    ctc = ctx.one(DOC_COST_TO_COMPLETE)
    if ctc is None:
        return []
    out: list[Finding] = []
    rows = _rows(ctc, "units")
    if not rows:
        return [Finding(rule, Status.FAIL, ctx.loc(ctc, "units"),
                        "the cost-to-complete carries no unit rows to foot")]
    totals = ctc.get("totals") or {}
    for key, label in (("net_upgrade_revenue_cents", "net upgrade revenue"),
                       ("costs_to_date_cents", "costs to date"),
                       ("committed_cost_cents", "committed cost")):
        summed = 0
        readable = True
        for row in rows:
            try:
                summed += require_cents(f"ctc.units[{row.get('unit')}].{key}", row.get(key))
            except AmountInvalidError as exc:
                out.append(amount_invalid_finding(rule, exc))
                readable = False
        if not readable:
            continue
        with amount_guard(rule, out):
            declared = require_cents(f"ctc.totals.{key}", totals.get(key))
            if summed != declared:
                out.append(Finding(rule, Status.FAIL, ctx.loc(ctc, f"totals/{key}"),
                                   f"{label}: unit rows sum to {fmt(summed)} but the total "
                                   f"declares {fmt(declared)} "
                                   f"(difference {fmt(summed - declared)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all three columns foot across {len(rows)} units"))
    return out


# --------------------------------------------------------------------------- #
# 7. flag_* -- the budgeted/actual marker
# --------------------------------------------------------------------------- #
@check("flag_actual_on_closed_units")
def flag_actual_on_closed_units(ctx: Context) -> list[Finding]:
    """A closed unit's revenue must be marked actual rather than budgeted.

    The marker is what tells the next reader whether a figure is a forecast or a
    fact. Left on "budgeted" after close, a real number keeps being treated as an
    estimate that somebody is still free to revise.
    """
    rule = "flag_actual_on_closed_units"
    _sev(rule, Status.FLAG)
    ctc = ctx.one(DOC_COST_TO_COMPLETE)
    schedule = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if ctc is None or schedule is None:
        return []
    closed = {str(u.get("unit")) for u in _rows(schedule, "units") if u.get("closed")}
    out: list[Finding] = []
    checked = 0
    for row in _rows(ctc, "units"):
        uid = str(row.get("unit"))
        basis = row.get("revenue_basis")
        checked += 1
        if uid in closed and basis != "actual":
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(ctc, f"units/{uid}/revenue_basis"),
                               f"unit {uid} has closed but its revenue is still marked "
                               f"{basis!r}; a closed unit's figure is a fact, not a forecast"))
        elif uid not in closed and basis == "actual":
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(ctc, f"units/{uid}/revenue_basis"),
                               f"unit {uid} is marked actual but has not closed; the figure "
                               f"is still an estimate"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"the budgeted/actual marker matches close status on "
                           f"{checked} units"))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one upgrade book."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top level must be a JSON object")

    ctx = Context(path=path, data=raw)
    report = DocumentReport(document=ctx.book_id)
    for _rule_id, fn in REGISTRY:
        report.findings.extend(fn(ctx))
    return report


def analyze_folder(folder: Path) -> list[DocumentReport]:
    """Analyze every ``.json`` upgrade book in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of book reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
