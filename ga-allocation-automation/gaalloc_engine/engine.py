"""
G&A expense allocation control engine (READ-ONLY).
==================================================

Loads each allocation file (a ``.json`` file produced by
:mod:`gaalloc_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **where a holding entity's shared cost lands**, and whether
the workbook that put it there can still prove the arithmetic. It does not ask
whether the cost should have been incurred, and it does not post the entry it
re-derives: it re-derives it and compares.

The shape of the problem
------------------------
A management or holding entity carries corporate G&A, shared overhead and the
postage meter for a group of operating entities and projects. None of that cost
belongs to it. Every month a recurring workbook -- one tab per month, a driver
tab and a lookup tab behind it, a stamped accounting date per period -- turns a
column of driver counts into a column of percentages, multiplies them by the
month's cost pool, and generates the allocation journal entry.

Four failures hide inside that, and none of them look wrong on the tab: the share
column that sums to 99.97% and quietly leaves cost behind in the holding entity;
the allocated column that was rounded recipient by recipient and no longer ties
the pool it divided; the entry that balances but no longer matches the schedule it
was posted from; and the month that was never rolled, or was rolled and stamped
to the date of the month it was copied from.

The registry is organised around that:

1. ``set_`` -- is the allocation file complete?
2. ``per_`` -- does the year run month by month, each tab present and stamped to
   its own accounting date?
3. ``rcp_`` -- is the recipient lookup sound, and does it exclude the holding
   entity that cannot allocate to itself?
4. ``drv_`` -- is the driver tab whole, and does it cover every recipient in
   every month?
5. ``pol_`` -- does the cost pool add up, and did it step month over month?
6. ``alc_`` -- do the shares sum to 100%, re-derive from the drivers, and do the
   amounts tie the pool and re-derive from the shares?
7. ``je_``  -- does the generated entry balance, tie the allocation, and net to
   zero at consolidation?
8. ``pst_`` -- does the postage allocation reconcile to the meter?
9. ``rpt_`` -- does the year-to-date rollup recompute from the tabs beneath it?

Design notes
------------
- **Strictly read-only.** Allocation files are parsed and never written back.
  Nothing is posted, filed or paid.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tie-out is compared with exact ``==``.
- **One allocation kernel.** Controls and the generator share
  :mod:`gaalloc_engine.allocation`, so a finding cannot disagree with the data
  that produced it.
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

from .allocation import (
    Rollup,
    allocate_pool,
    driver_shares_bps,
    meter_delta_cents,
    month_end,
    next_period,
    parse_period,
    variance_bps,
)
from .model import (
    DOC_ALLOCATION_JOURNAL,
    DOC_ALLOCATION_REPORT,
    DOC_ALLOCATION_SCHEDULE,
    DOC_COST_POOL_LEDGER,
    DOC_DRIVER_TABLE,
    DOC_PERIOD_CALENDAR,
    DOC_POSTAGE_LOG,
    DOC_RECIPIENT_REGISTER,
    DOC_TYPES,
    POSTAGE_CODE_WEIGHTS,
    POSTAGE_CODES,
    RECIPIENT_KINDS,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import BPS_FULL, AmountInvalidError, fmt, fmt_bps, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}

#: Cost-pool components that must add to the stated pool total.
POOL_COMPONENTS: tuple[str, ...] = (
    "shared_overhead_cents",
    "corporate_ga_cents",
    "postage_cents",
)


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~gaalloc_engine.money.AmountInvalidError` as a finding."""
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
# Allocation-file helpers
# --------------------------------------------------------------------------- #
def _calendar_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PERIOD_CALENDAR), "periods")


def _periods(ctx: Context) -> list[str]:
    """Readable period labels from the calendar, deduplicated, in tab order."""
    out: list[str] = []
    for row in _calendar_rows(ctx):
        period = _text(row, "period")
        if period and period not in out:
            out.append(period)
    return out


def _stamped_date(ctx: Context, period: str) -> str | None:
    """The accounting date the calendar stamps on ``period``."""
    for row in _calendar_rows(ctx):
        if _text(row, "period") == period:
            return _text(row, "accounting_date")
    return None


def _recipient_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_RECIPIENT_REGISTER), "recipients")


def _recipient_ids(ctx: Context) -> list[str]:
    """Recipient ids in lookup order: deduplicated, holding entity excluded.

    The holding entity cannot be a recipient of its own allocation --
    ``rcp_holding_not_recipient`` owns that -- so it is dropped here and every
    downstream derivation ignores it rather than allocating cost back to it.
    """
    holding = ctx.holding_entity_id
    out: list[str] = []
    for row in _recipient_rows(ctx):
        rid = _text(row, "recipient_id")
        if rid and rid != holding and rid not in out:
            out.append(rid)
    return out


def _recipient_accounts(ctx: Context) -> dict[str, str]:
    """Recipient id -> the GL account its allocated share is debited to."""
    out: dict[str, str] = {}
    for row in _recipient_rows(ctx):
        rid = _text(row, "recipient_id")
        account = _text(row, "gl_account")
        if rid and account and rid not in out:
            out[rid] = account
    return out


def _driver_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DRIVER_TABLE), "drivers")


def _driver_map(ctx: Context) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _driver_rows(ctx):
        period = _text(row, "period")
        rid = _text(row, "recipient_id")
        if period and rid:
            out.setdefault((period, rid), []).append(row)
    return out


def _pool_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_COST_POOL_LEDGER), "pools")


def _pool_map(ctx: Context) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _pool_rows(ctx):
        period = _text(row, "period")
        if period:
            out.setdefault(period, []).append(row)
    return out


def _pool_row(ctx: Context, period: str) -> dict[str, Any] | None:
    """The single cost-pool row for ``period``, or ``None``."""
    rows = _pool_map(ctx).get(period, [])
    return rows[0] if len(rows) == 1 else None


def _pool_total(ctx: Context, period: str) -> int | None:
    """The stated cost pool for ``period``, in integer cents, or ``None``.

    Raises :class:`AmountInvalidError` if the stated total is not integer cents.
    """
    row = _pool_row(ctx, period)
    if row is None:
        return None
    return require_cents(f"cost_pool[{period}].pool_total_cents", row.get("pool_total_cents"))


def _allocation_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ALLOCATION_SCHEDULE), "allocations")


def _allocation_map(ctx: Context) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _allocation_rows(ctx):
        period = _text(row, "period")
        rid = _text(row, "recipient_id")
        if period and rid:
            out.setdefault((period, rid), []).append(row)
    return out


def _journal_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ALLOCATION_JOURNAL), "entries")


def _journal_map(ctx: Context) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _journal_rows(ctx):
        period = _text(row, "period")
        if period:
            out.setdefault(period, []).append(row)
    return out


def _journal_entry(ctx: Context, period: str) -> dict[str, Any] | None:
    entries = _journal_map(ctx).get(period, [])
    return entries[0] if len(entries) == 1 else None


def _journal_lines(entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if entry is None:
        return []
    lines = entry.get("lines")
    if not isinstance(lines, list):
        return []
    return [line for line in lines if isinstance(line, dict)]


def _meter_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_POSTAGE_LOG), "meters")


def _meter_map(ctx: Context) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _meter_rows(ctx):
        period = _text(row, "period")
        if period:
            out.setdefault(period, []).append(row)
    return out


def _meter_row(ctx: Context, period: str) -> dict[str, Any] | None:
    rows = _meter_map(ctx).get(period, [])
    return rows[0] if len(rows) == 1 else None


def _meter_allocations(row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if row is None:
        return []
    allocations = row.get("allocations")
    if not isinstance(allocations, list):
        return []
    return [a for a in allocations if isinstance(a, dict)]


def _meter_reading(ctx: Context, period: str) -> tuple[int, int] | None:
    """The ``(begin, end)`` meter readings for ``period``, in integer cents.

    Raises :class:`AmountInvalidError` if either reading is not integer cents.
    """
    row = _meter_row(ctx, period)
    if row is None:
        return None
    begin = require_cents(f"postage[{period}].begin_meter_cents", row.get("begin_meter_cents"))
    end = require_cents(f"postage[{period}].end_meter_cents", row.get("end_meter_cents"))
    return begin, end


def _allocation_coverage_ok(ctx: Context, period: str) -> bool:
    """Whether ``period``'s allocation tab carries exactly one row per recipient.

    Every downstream allocation control reads this first. A tab that is missing a
    recipient sums to less than the pool and to less than 100% for reasons that
    have nothing to do with the share arithmetic, so ``alc_recipient_coverage``
    owns the gap and the arithmetic controls decline to report it twice.
    """
    ids = _recipient_ids(ctx)
    if not ids:
        return False
    amap = _allocation_map(ctx)
    for rid in ids:
        if len(amap.get((period, rid), [])) != 1:
            return False
    known = set(ids)
    return all(
        _text(row, "recipient_id") in known
        for row in _allocation_rows(ctx)
        if _text(row, "period") == period
    )


def _stated_shares(ctx: Context, period: str) -> dict[str, int]:
    """Recipient id -> the share, in basis points, the tab states for ``period``.

    Raises :class:`AmountInvalidError` if a stated share is not a whole number of
    basis points.
    """
    amap = _allocation_map(ctx)
    out: dict[str, int] = {}
    for rid in _recipient_ids(ctx):
        rows = amap.get((period, rid), [])
        if len(rows) != 1:
            continue
        out[rid] = require_cents(
            f"allocation[{period}/{rid}].share_bps",
            rows[0].get("share_bps"),
            unit="whole basis points",
        )
    return out


# --------------------------------------------------------------------------- #
# Re-derivation -- shared with the generator through the allocation kernel
# --------------------------------------------------------------------------- #
def recompute_shares(ctx: Context, period: str) -> dict[str, int]:
    """Rebuild a period's allocation shares from the driver tab.

    Returns recipient id -> share in basis points, summing to exactly 10000.
    Returns an empty mapping when the drivers cannot support a share at all -- a
    recipient with no driver row or more than one, a count that is not a whole
    non-negative number, a period whose counts total zero. The controls that read
    it treat an empty mapping as "the driver family owns this" and decline to
    report a derived figure they could not derive.

    Shared with the generator through :mod:`gaalloc_engine.allocation`, so the
    shares the engine re-derives are the shares that produced the data.
    """
    ids = _recipient_ids(ctx)
    if not ids:
        return {}
    dmap = _driver_map(ctx)
    counts: list[int] = []
    for rid in ids:
        rows = dmap.get((period, rid), [])
        if len(rows) != 1:
            return {}
        count = _int(rows[0], "driver_count")
        if count is None or count < 0:
            return {}
        counts.append(count)
    if sum(counts) <= 0:
        return {}
    return dict(zip(ids, driver_shares_bps(counts), strict=True))


def recompute_allocation(ctx: Context, period: str) -> dict[str, int]:
    """Rebuild a period's allocated amounts: pool x driver share, by largest remainder.

    Returns recipient id -> integer cents, summing to exactly the period's cost
    pool. Returns an empty mapping when the shares or the pool are unavailable.

    Raises :class:`AmountInvalidError` if the stated pool total is not integer
    cents; the calling control contains that to the period being read.
    """
    shares = recompute_shares(ctx, period)
    if not shares or sum(shares.values()) != BPS_FULL:
        return {}
    pool = _pool_total(ctx, period)
    if pool is None:
        return {}
    amounts = allocate_pool(pool, list(shares.values()))
    return dict(zip(shares, amounts, strict=True))


def recompute_postage_codes(ctx: Context, period: str) -> list[dict[str, Any]] | None:
    """Rebuild a period's per-code postage split from the meter reading.

    The metered spend is the closing reading less the opening one, split across
    the postage classes by the policy weights in
    :data:`~gaalloc_engine.model.POSTAGE_CODE_WEIGHTS` -- again by largest
    remainder, so the split exhausts the meter delta exactly. Returns ``None``
    when there is no single meter row for the period or the meter ran backwards.

    Raises :class:`AmountInvalidError` if a reading is not integer cents.
    """
    reading = _meter_reading(ctx, period)
    if reading is None:
        return None
    begin, end = reading
    delta = meter_delta_cents(begin, end)
    if delta < 0:
        return None
    amounts = allocate_pool(delta, [weight for _code, weight in POSTAGE_CODE_WEIGHTS])
    return [
        {"postage_code": code, "amount_cents": amount}
        for (code, _weight), amount in zip(POSTAGE_CODE_WEIGHTS, amounts, strict=True)
    ]


def recompute_journal(ctx: Context, period: str) -> dict[str, Any] | None:
    """Rebuild a period's allocation journal entry from the derived allocation.

    One debit line per recipient, on the GL account the lookup tab gives it, and
    one credit line relieving the holding entity for the whole pool. Returns
    ``None`` when the allocation could not be derived.
    """
    allocation = recompute_allocation(ctx, period)
    if not allocation:
        return None
    accounts = _recipient_accounts(ctx)
    lines: list[dict[str, Any]] = [
        {
            "entity_id": rid,
            "account": accounts.get(rid, "-"),
            "debit_cents": amount,
            "credit_cents": 0,
        }
        for rid, amount in allocation.items()
    ]
    lines.append(
        {
            "entity_id": ctx.holding_entity_id,
            "account": ctx.holding_credit_account,
            "debit_cents": 0,
            "credit_cents": sum(allocation.values()),
        }
    )
    return {
        "period": period,
        "je_no": f"GA-{period}",
        "accounting_date": _stamped_date(ctx, period),
        "lines": lines,
    }


def recompute_rollup(ctx: Context) -> Rollup:
    """Rebuild the year-to-date rollup from the tabs beneath it.

    ``complete`` is ``False`` when any period failed to derive, so the tie-out
    control can decline to compare a total it could not fully rebuild.

    Raises :class:`AmountInvalidError` if a stated pool total is not integer
    cents.
    """
    periods = _periods(ctx)
    pool_total = 0
    allocated_total = 0
    complete = bool(periods)
    for period in periods:
        stated = _pool_total(ctx, period)
        if stated is None:
            complete = False
        else:
            pool_total += stated
        allocation = recompute_allocation(ctx, period)
        if not allocation:
            complete = False
        else:
            allocated_total += sum(allocation.values())
    return Rollup(
        period_count=len(periods),
        recipient_count=len(_recipient_ids(ctx)),
        pool_total_cents=pool_total,
        allocated_total_cents=allocated_total,
        complete=complete,
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the allocation file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the allocation file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} allocation artifacts are present",
            )
        )
    if parse_period(ctx.first_period) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"first_period {ctx.first_period!r} is not a readable YYYY-MM month; the "
                f"year the workbook covers cannot be established",
            )
        )
    if ctx.holding_entity_id == "-":
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                "the file does not name the holding entity whose G&A is allocated; every "
                "credit line and every recipient exclusion is measured against it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# per_ -- the month tabs and their accounting dates
# --------------------------------------------------------------------------- #
@check("per_months_consecutive")
def check_per_months_consecutive(ctx: Context) -> list[Finding]:
    """The calendar runs month by month from the stated opening period.

    A workbook copied forward every month loses a tab the way a chain loses a
    link: silently, and only where nobody re-reads the sequence. A missing or
    repeated month means a period of the group's overhead was never pushed out,
    or was pushed out twice.
    """
    rule = "per_months_consecutive"
    _sev(rule, Status.FAIL)
    calendar = ctx.one(DOC_PERIOD_CALENDAR)
    if calendar is None:
        return []
    out: list[Finding] = []
    labels = [row.get("period") for row in _calendar_rows(ctx)]
    readable: list[str] = []
    for label in labels:
        if parse_period(label) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{label}"),
                    f"period {label!r} is not a readable YYYY-MM month; the tab cannot be "
                    f"placed in the year",
                )
            )
        else:
            readable.append(str(label))
    seen: dict[str, int] = {}
    for label in readable:
        seen[label] = seen.get(label, 0) + 1
    for label, count in seen.items():
        if count > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{label}"),
                    f"period {label} appears on {count} tabs; the month would be allocated "
                    f"more than once",
                )
            )
    for prior, current in zip(readable, readable[1:], strict=False):
        expected = next_period(prior)
        if expected is not None and current != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{current}"),
                    f"the tab after {prior} is {current}; the calendar skips {expected}, so "
                    f"that month's G&A was never allocated",
                )
            )
    if readable and readable[0] != ctx.first_period:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(calendar, "periods"),
                f"the calendar opens on {readable[0]} but the file states it opens on "
                f"{ctx.first_period}; one of the two has lost a month",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the calendar runs {len(readable)} consecutive months from "
                f"{ctx.first_period}",
            )
        )
    return out


@check("per_tab_continuity")
def check_per_tab_continuity(ctx: Context) -> list[Finding]:
    """Every month on the calendar carries every tab, stamped to its own month end.

    Continuity is the control the recurring workbook needs most. Each period must
    have exactly one cost pool, one journal entry and one meter reading, at least
    one driver and one allocation row, and an accounting date that is the last day
    of the month it allocates -- a tab rolled forward but dated to the month it
    was copied from posts real cost into the wrong period. No artifact may name a
    period the calendar does not carry.
    """
    rule = "per_tab_continuity"
    _sev(rule, Status.FAIL)
    calendar = ctx.one(DOC_PERIOD_CALENDAR)
    if calendar is None:
        return []
    periods = _periods(ctx)
    known = set(periods)
    out: list[Finding] = []
    for period in periods:
        expected = month_end(period)
        stamped = _stamped_date(ctx, period)
        if expected is not None and stamped != expected.isoformat():
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{period}/accounting_date"),
                    f"period {period} is stamped {stamped!r}; a monthly allocation posts on "
                    f"{expected.isoformat()}, the last day of the month it allocates",
                )
            )
        for label, rows in (
            ("cost pool", _pool_map(ctx).get(period, [])),
            ("journal entry", _journal_map(ctx).get(period, [])),
            ("postage meter reading", _meter_map(ctx).get(period, [])),
        ):
            if len(rows) != 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(calendar, f"periods/{period}"),
                        f"period {period} carries {len(rows)} {label} rows; the tab is "
                        f"complete only with exactly one",
                    )
                )
        if not any(_text(r, "period") == period for r in _driver_rows(ctx)):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{period}"),
                    f"period {period} has no driver rows at all; there is no basis on which "
                    f"its pool could have been allocated",
                )
            )
        if not any(_text(r, "period") == period for r in _allocation_rows(ctx)):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{period}"),
                    f"period {period} has no allocation rows at all; its pool was never "
                    f"pushed out of the holding entity",
                )
            )
        entry = _journal_entry(ctx, period)
        if entry is not None and _text(entry, "accounting_date") != stamped:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{period}/accounting_date"),
                    f"period {period} is stamped {stamped!r} on the calendar and "
                    f"{_text(entry, 'accounting_date')!r} on its journal entry; the entry "
                    f"would post into a different accounting period",
                )
            )
    for doc_type, rows in (
        (DOC_COST_POOL_LEDGER, _pool_rows(ctx)),
        (DOC_DRIVER_TABLE, _driver_rows(ctx)),
        (DOC_ALLOCATION_SCHEDULE, _allocation_rows(ctx)),
        (DOC_ALLOCATION_JOURNAL, _journal_rows(ctx)),
        (DOC_POSTAGE_LOG, _meter_rows(ctx)),
    ):
        orphans = sorted({
            str(_text(row, "period"))
            for row in rows
            if _text(row, "period") is not None and _text(row, "period") not in known
        })
        for orphan in orphans:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(calendar, f"periods/{orphan}"),
                    f"{doc_type} carries rows for {orphan}, which is not a month on the "
                    f"calendar; the figures belong to a tab the year does not have",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(periods)} month tabs are complete and stamped to their own "
                f"month end",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rcp_ -- the recipient lookup tab
# --------------------------------------------------------------------------- #
@check("rcp_unique_ids")
def check_rcp_unique_ids(ctx: Context) -> list[Finding]:
    """No recipient id appears twice in the lookup tab.

    The recipient id joins the lookup tab to the driver counts, the allocation
    rows and the journal lines. A duplicate makes a driver count ambiguous about
    whose share it sets.
    """
    rule = "rcp_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_RECIPIENT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _recipient_rows(ctx):
        rid = _text(row, "recipient_id") or "?"
        seen[rid] = seen.get(rid, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"recipients/{rid}"),
            f"recipient id {rid} appears {count} times; a driver count that names it "
            f"cannot be attributed to one recipient",
        )
        for rid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} recipient ids are unique")
        )
    return out


@check("rcp_rows_wellformed")
def check_rcp_rows_wellformed(ctx: Context) -> list[Finding]:
    """Every recipient carries an id, a name, a known kind and a GL account.

    The kind says whether the allocation lands on an entity or a project, and the
    GL account is the debit side of every line generated for it. A row missing
    either is a recipient the entry cannot be written for.
    """
    rule = "rcp_rows_wellformed"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_RECIPIENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _recipient_rows(ctx):
        rid = _text(row, "recipient_id") or "?"
        missing = [f for f in ("recipient_id", "name", "gl_account") if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"recipients/{rid}"),
                    f"recipient {rid} is missing {', '.join(missing)}; the allocation line "
                    f"for it cannot be written",
                )
            )
        kind = _text(row, "kind")
        if kind not in RECIPIENT_KINDS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"recipients/{rid}/kind"),
                    f"recipient {rid} is typed {kind!r}, which is not one of "
                    f"{RECIPIENT_KINDS}; the allocation policy has no rule for it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_recipient_rows(ctx))} recipient rows are well-formed",
            )
        )
    return out


@check("rcp_holding_not_recipient")
def check_rcp_holding_not_recipient(ctx: Context) -> list[Finding]:
    """The holding entity is not a recipient of its own allocation.

    The whole point of the entry is to move cost off the holding entity. A lookup
    tab that lists the holding entity as a recipient allocates a slice of the pool
    straight back to it, so the entry both charges and relieves the same books and
    the group's overhead never actually leaves.
    """
    rule = "rcp_holding_not_recipient"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_RECIPIENT_REGISTER)
    if register is None:
        return []
    holding = ctx.holding_entity_id
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"recipients/{holding}"),
            f"the holding entity {holding} is listed as a recipient; it cannot allocate "
            f"its own G&A to itself, and the slice it took would never leave the group's "
            f"overhead",
        )
        for row in _recipient_rows(ctx)
        if _text(row, "recipient_id") == holding
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the holding entity {holding} is not among the allocation recipients",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# drv_ -- the driver tab
# --------------------------------------------------------------------------- #
@check("drv_counts_whole")
def check_drv_counts_whole(ctx: Context) -> list[Finding]:
    """Driver counts are whole, non-negative, and total something in every month.

    A driver is a count of things -- headcount-equivalents, units, doors. A
    fractional count is a typed-over formula and a negative count is a reversal
    entered into a basis column; both would push a negative share onto some
    recipient and take cost off it. A month whose counts total zero has no basis
    at all.
    """
    rule = "drv_counts_whole"
    _sev(rule, Status.FAIL)
    table = ctx.one(DOC_DRIVER_TABLE)
    if table is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _driver_rows(ctx):
        period = _text(row, "period") or "?"
        rid = _text(row, "recipient_id") or "?"
        with amount_guard(rule, out):
            count = require_cents(
                f"driver[{period}/{rid}].driver_count",
                row.get("driver_count"),
                unit="a whole driver count",
            )
            checked += 1
            if count < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(table, f"drivers/{period}/{rid}/driver_count"),
                        f"recipient {rid} carries a driver count of {count} in {period}; a "
                        f"negative basis would allocate cost away from a recipient rather "
                        f"than to it",
                    )
                )
    for period in _periods(ctx):
        counts = [
            _int(row, "driver_count")
            for row in _driver_rows(ctx)
            if _text(row, "period") == period
        ]
        present = [c for c in counts if c is not None]
        if present and sum(present) <= 0:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(table, f"drivers/{period}"),
                    f"the driver counts for {period} total {sum(present)}; there is no "
                    f"basis on which that month's pool could be shared out",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} driver counts are whole and non-negative",
            )
        )
    return out


@check("drv_coverage_complete")
def check_drv_coverage_complete(ctx: Context) -> list[Finding]:
    """Every recipient has exactly one driver row in every month.

    A recipient with no driver row is not a recipient with a zero share; it is a
    recipient whose basis was never captured, and the shares of everyone else
    silently absorb what should have been its slice. Two rows are worse: the tab
    would count the same basis twice.
    """
    rule = "drv_coverage_complete"
    _sev(rule, Status.FAIL)
    table = ctx.one(DOC_DRIVER_TABLE)
    if table is None:
        return []
    ids = _recipient_ids(ctx)
    dmap = _driver_map(ctx)
    known = set(ids)
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        for rid in ids:
            rows = dmap.get((period, rid), [])
            checked += 1
            if len(rows) != 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(table, f"drivers/{period}/{rid}"),
                        f"recipient {rid} has {len(rows)} driver rows in {period}; its share "
                        f"of that month's pool cannot be derived from exactly one basis",
                    )
                )
    for row in _driver_rows(ctx):
        rid = _text(row, "recipient_id")
        if rid is not None and rid not in known:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(table, f"drivers/{_text(row, 'period')}/{rid}"),
                    f"the driver tab carries a count for {rid}, which is not an allocation "
                    f"recipient; the basis it adds belongs to nobody",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} recipient-months carry exactly one driver row",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# pol_ -- the cost pool
# --------------------------------------------------------------------------- #
@check("pol_components_sum")
def check_pol_components_sum(ctx: Context) -> list[Finding]:
    """A period's pool components add to the pool total the allocation divides.

    The total is the figure the allocation multiplies against, and the components
    are what a reviewer reads to understand it. When they stop agreeing, the
    review is being done on one number and the entry on another.
    """
    rule = "pol_components_sum"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_COST_POOL_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        row = _pool_row(ctx, period)
        if row is None:
            continue  # per_tab_continuity owns this
        with amount_guard(rule, out):
            components = {
                key: require_cents(f"cost_pool[{period}].{key}", row.get(key))
                for key in POOL_COMPONENTS
            }
            stated = require_cents(
                f"cost_pool[{period}].pool_total_cents", row.get("pool_total_cents")
            )
            checked += 1
            derived = sum(components.values())
            if derived != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger, f"pools/{period}/pool_total_cents"),
                        f"the {period} pool states a total of {fmt(stated)}; its components "
                        f"add to {fmt(derived)} (out by {fmt(stated - derived)}), so the "
                        f"figure being allocated is not the figure being reviewed",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} cost pools add to their stated total"
            )
        )
    return out


@check("pol_month_over_month_variance")
def check_pol_month_over_month_variance(ctx: Context) -> list[Finding]:
    """A cost pool that steps month over month beyond the file's band is flagged.

    Deliberately a FLAG, not a failure: a pool is allowed to move, and the entry
    built on it is arithmetically correct either way. But a recurring workbook is
    copied forward precisely because the figures are stable, so a step outside the
    band is either a real change in the group's cost base or a component typed
    into the wrong month, and a human should say which.
    """
    rule = "pol_month_over_month_variance"
    _sev(rule, Status.FLAG)
    ledger = ctx.one(DOC_COST_POOL_LEDGER)
    if ledger is None:
        return []
    band = ctx.variance_flag_bps
    out: list[Finding] = []
    checked = 0
    periods = _periods(ctx)
    for prior, current in zip(periods, periods[1:], strict=False):
        with amount_guard(rule, out):
            prior_total = _pool_total(ctx, prior)
            current_total = _pool_total(ctx, current)
            if prior_total is None or current_total is None:
                continue  # per_tab_continuity owns this
            checked += 1
            moved = variance_bps(current_total, prior_total)
            if moved > band:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(ledger, f"pools/{current}/pool_total_cents"),
                        f"the pool moved from {fmt(prior_total)} in {prior} to "
                        f"{fmt(current_total)} in {current}, a step of {fmt_bps(moved)} "
                        f"against a {fmt_bps(band)} band; a recurring pool that steps this "
                        f"far has changed in substance",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} month-over-month pool steps are inside the "
                f"{fmt_bps(band)} band",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# alc_ -- the allocation itself
# --------------------------------------------------------------------------- #
@check("alc_recipient_coverage")
def check_alc_recipient_coverage(ctx: Context) -> list[Finding]:
    """Every recipient has exactly one allocation row in every month.

    This is the precondition every other allocation control reads. A tab that lost
    a recipient sums to less than 100% and to less than the pool for a reason that
    has nothing to do with the share arithmetic, so the gap is named here once
    rather than reported three more times downstream.
    """
    rule = "alc_recipient_coverage"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    ids = _recipient_ids(ctx)
    known = set(ids)
    amap = _allocation_map(ctx)
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        for rid in ids:
            rows = amap.get((period, rid), [])
            checked += 1
            if len(rows) != 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"allocations/{period}/{rid}"),
                        f"recipient {rid} has {len(rows)} allocation rows in {period}; the "
                        f"month's pool cannot be pushed out across a tab that is missing a "
                        f"recipient or carries one twice",
                    )
                )
    for row in _allocation_rows(ctx):
        rid = _text(row, "recipient_id")
        if rid is not None and rid not in known:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"allocations/{_text(row, 'period')}/{rid}"),
                    f"the allocation tab carries a row for {rid}, which is not an allocation "
                    f"recipient; the amount beside it is charged to nobody",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} recipient-months carry exactly one allocation row",
            )
        )
    return out


@check("alc_shares_sum_to_full")
def check_alc_shares_sum_to_full(ctx: Context) -> list[Finding]:
    """A period's allocation shares sum to exactly 10000 basis points.

    100.00%, to the basis point, with no tolerance band. A column that sums to
    9997 bps does not "round to" a hundred percent: it pushes out 99.97% of the
    pool and leaves the rest sitting in the holding entity, every month, for as
    long as the workbook is copied forward.
    """
    rule = "alc_shares_sum_to_full"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        if not _allocation_coverage_ok(ctx, period):
            continue  # alc_recipient_coverage owns this
        with amount_guard(rule, out):
            shares = _stated_shares(ctx, period)
            checked += 1
            stated = sum(shares.values())
            if stated != BPS_FULL:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"allocations/{period}/share_bps"),
                        f"the {period} shares sum to {fmt_bps(stated)}, not "
                        f"{fmt_bps(BPS_FULL)} (out by {fmt_bps(stated - BPS_FULL)}); the "
                        f"month's pool is not fully pushed out of the holding entity",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} month share columns sum to exactly {fmt_bps(BPS_FULL)}",
            )
        )
    return out


@check("alc_shares_rederive")
def check_alc_shares_rederive(ctx: Context) -> list[Finding]:
    """Each stated share re-derives from the driver counts behind it.

    A share column is a *derivation*, and a derivation nobody recomputes is a
    typed constant that happens to have been right once. The engine rebuilds every
    share from the driver tab by largest remainder -- the same arithmetic that
    produced it -- and compares to the basis point.
    """
    rule = "alc_shares_rederive"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        if not _allocation_coverage_ok(ctx, period):
            continue  # alc_recipient_coverage owns this
        derived = recompute_shares(ctx, period)
        if not derived:
            continue  # the drv_ family owns this
        with amount_guard(rule, out):
            stated = _stated_shares(ctx, period)
            if sum(stated.values()) != BPS_FULL:
                continue  # alc_shares_sum_to_full owns this
            for rid, want in derived.items():
                have = stated.get(rid)
                if have is None:
                    continue
                checked += 1
                if have != want:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(schedule, f"allocations/{period}/{rid}/share_bps"),
                            f"recipient {rid} is given {fmt_bps(have)} of the {period} pool; "
                            f"its driver count re-derives {fmt_bps(want)} "
                            f"(out by {fmt_bps(have - want)})",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} stated shares re-derive from their driver counts",
            )
        )
    return out


@check("alc_amounts_tie_pool")
def check_alc_amounts_tie_pool(ctx: Context) -> list[Finding]:
    """A period's allocated amounts sum to exactly the cost pool they divide.

    Exact ``==``, no tolerance. An allocation that tolerates a penny against the
    pool it divides has not been allocated; the residual cent belongs to exactly
    one recipient, and the largest-remainder split is how it gets there.
    """
    rule = "alc_amounts_tie_pool"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    amap = _allocation_map(ctx)
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        if not _allocation_coverage_ok(ctx, period):
            continue  # alc_recipient_coverage owns this
        amounts: dict[str, int] = {}
        unreadable = False
        for rid in _recipient_ids(ctx):
            row = amap[(period, rid)][0]
            try:
                amounts[rid] = require_cents(
                    f"allocation[{period}/{rid}].allocated_cents", row.get("allocated_cents")
                )
            except AmountInvalidError as exc:
                out.append(amount_invalid_finding(rule, exc))
                unreadable = True
        if unreadable:
            continue
        with amount_guard(rule, out):
            pool = _pool_total(ctx, period)
            if pool is None:
                continue  # per_tab_continuity owns this
            checked += 1
            allocated = sum(amounts.values())
            if allocated != pool:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"allocations/{period}/allocated_cents"),
                        f"the {period} allocation sums to {fmt(allocated)} against a pool of "
                        f"{fmt(pool)} (out by {fmt(allocated - pool)}); the difference stays "
                        f"in, or is over-relieved from, the holding entity",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} month allocations tie their cost pool"
            )
        )
    return out


@check("alc_amounts_rederive")
def check_alc_amounts_rederive(ctx: Context) -> list[Finding]:
    """Each allocated amount re-derives as driver share x pool, by largest remainder.

    This is the control the engine exists for. An allocated column is the product
    of two things the file already carries, and the only way to know it is still
    that product is to compute it again. The engine rebuilds every amount through
    the same kernel that produced it and compares to the cent.
    """
    rule = "alc_amounts_rederive"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    amap = _allocation_map(ctx)
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        if not _allocation_coverage_ok(ctx, period):
            continue  # alc_recipient_coverage owns this
        amounts: dict[str, int] = {}
        unreadable = False
        for rid in _recipient_ids(ctx):
            row = amap[(period, rid)][0]
            try:
                amounts[rid] = require_cents(
                    f"allocation[{period}/{rid}].allocated_cents", row.get("allocated_cents")
                )
            except AmountInvalidError as exc:
                out.append(amount_invalid_finding(rule, exc))
                unreadable = True
        if unreadable:
            continue
        with amount_guard(rule, out):
            derived = recompute_allocation(ctx, period)
            if not derived:
                continue  # the drv_ and per_ families own this
            pool = _pool_total(ctx, period)
            if pool is not None and sum(amounts.values()) != pool:
                continue  # alc_amounts_tie_pool owns this
            for rid, want in derived.items():
                have = amounts.get(rid)
                if have is None:
                    continue
                checked += 1
                if have != want:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(schedule, f"allocations/{period}/{rid}/allocated_cents"),
                            f"recipient {rid} is allocated {fmt(have)} of the {period} pool; "
                            f"its driver share re-derives {fmt(want)} "
                            f"(out by {fmt(have - want)})",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} allocated amounts re-derive as share x pool",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# je_ -- the generated allocation journal entry
# --------------------------------------------------------------------------- #
@check("je_balanced")
def check_je_balanced(ctx: Context) -> list[Finding]:
    """Each period's allocation entry balances: debits equal credits, exactly.

    The first thing anyone assumes about a generated entry and the last thing
    anyone re-checks. An entry generated from a formula column that lost a row
    still looks like an entry; it simply does not balance, and a ledger that
    accepts it carries the difference as an unexplained suspense.
    """
    rule = "je_balanced"
    _sev(rule, Status.FAIL)
    journal = ctx.one(DOC_ALLOCATION_JOURNAL)
    if journal is None:
        return []
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        entry = _journal_entry(ctx, period)
        if entry is None:
            continue  # per_tab_continuity owns this
        with amount_guard(rule, out):
            debits = 0
            credits = 0
            for i, line in enumerate(_journal_lines(entry)):
                debits += require_cents(
                    f"journal[{period}].lines[{i}].debit_cents", line.get("debit_cents")
                )
                credits += require_cents(
                    f"journal[{period}].lines[{i}].credit_cents", line.get("credit_cents")
                )
            checked += 1
            if debits != credits:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(journal, f"entries/{period}/lines"),
                        f"the {period} allocation entry debits {fmt(debits)} against credits "
                        f"of {fmt(credits)} (out by {fmt(debits - credits)}); it does not "
                        f"balance and cannot be posted as written",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} allocation entries balance")
        )
    return out


@check("je_ties_allocation")
def check_je_ties_allocation(ctx: Context) -> list[Finding]:
    """Each recipient's net debit in the entry equals its re-derived allocation.

    The schedule is one artifact and the entry posted from it is another, and they
    drift the moment a figure is retyped on either side. The engine rebuilds the
    allocation from the drivers and the pool and reads the entry against it, net of
    any credit on the same recipient, so a line pair that appears to correct itself
    is not mistaken for the right answer.
    """
    rule = "je_ties_allocation"
    _sev(rule, Status.FAIL)
    journal = ctx.one(DOC_ALLOCATION_JOURNAL)
    if journal is None:
        return []
    group = set(_recipient_ids(ctx)) | {ctx.holding_entity_id}
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        entry = _journal_entry(ctx, period)
        if entry is None:
            continue  # per_tab_continuity owns this
        derived = recompute_allocation(ctx, period)
        if not derived:
            continue  # the drv_ and per_ families own this
        with amount_guard(rule, out):
            nets: dict[str, int] = {}
            for i, line in enumerate(_journal_lines(entry)):
                entity = _text(line, "entity_id") or "?"
                debit = require_cents(
                    f"journal[{period}].lines[{i}].debit_cents", line.get("debit_cents")
                )
                credit = require_cents(
                    f"journal[{period}].lines[{i}].credit_cents", line.get("credit_cents")
                )
                nets[entity] = nets.get(entity, 0) + debit - credit
                if entity not in group:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(journal, f"entries/{period}/lines/{entity}"),
                            f"the {period} entry posts to {entity}, which is neither an "
                            f"allocation recipient nor the holding entity; the amount leaves "
                            f"the group the allocation is defined over",
                        )
                    )
            for rid, want in derived.items():
                checked += 1
                have = nets.get(rid, 0)
                if have != want:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(journal, f"entries/{period}/lines/{rid}"),
                            f"the {period} entry charges {rid} a net {fmt(have)}; the "
                            f"allocation re-derives {fmt(want)} (out by {fmt(have - want)})",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} entry lines tie the re-derived allocation",
            )
        )
    return out


@check("je_consolidation_nets_zero")
def check_je_consolidation_nets_zero(ctx: Context) -> list[Finding]:
    """The allocation moves cost inside the group without creating any of it.

    Two things make that true, and both are checked. Across every month the
    group's debits and credits must net to exactly zero, so the year's allocation
    is a transfer and not a cost. And no entity may be both charged and relieved
    inside one entry: a debit and a credit on the same books net to nothing at
    that entity while inflating both sides of the entry, so cost appears to have
    moved when it has not, and the consolidated total cannot see it.
    """
    rule = "je_consolidation_nets_zero"
    _sev(rule, Status.FAIL)
    journal = ctx.one(DOC_ALLOCATION_JOURNAL)
    if journal is None:
        return []
    out: list[Finding] = []
    group_debits = 0
    group_credits = 0
    checked = 0
    for period in _periods(ctx):
        entry = _journal_entry(ctx, period)
        if entry is None:
            continue  # per_tab_continuity owns this
        with amount_guard(rule, out):
            charged: dict[str, int] = {}
            relieved: dict[str, int] = {}
            for i, line in enumerate(_journal_lines(entry)):
                entity = _text(line, "entity_id") or "?"
                debit = require_cents(
                    f"journal[{period}].lines[{i}].debit_cents", line.get("debit_cents")
                )
                credit = require_cents(
                    f"journal[{period}].lines[{i}].credit_cents", line.get("credit_cents")
                )
                group_debits += debit
                group_credits += credit
                if debit:
                    charged[entity] = charged.get(entity, 0) + debit
                if credit:
                    relieved[entity] = relieved.get(entity, 0) + credit
            checked += 1
            for entity in sorted(set(charged) & set(relieved)):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(journal, f"entries/{period}/lines/{entity}"),
                        f"the {period} entry both charges {entity} {fmt(charged[entity])} "
                        f"and relieves it {fmt(relieved[entity])}; the pair nets to nothing "
                        f"at that entity while inflating both sides of the entry",
                    )
                )
    if group_debits != group_credits:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(journal, "entries"),
                f"across all periods the allocation debits {fmt(group_debits)} against "
                f"credits of {fmt(group_credits)} (out by "
                f"{fmt(group_debits - group_credits)}); at consolidation the year's "
                f"allocation creates cost rather than moving it",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} entries net to zero at consolidation with no entity both "
                f"charged and relieved",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# pst_ -- the postage meter
# --------------------------------------------------------------------------- #
@check("pst_meter_rolls_forward")
def check_pst_meter_rolls_forward(ctx: Context) -> list[Finding]:
    """The postage meter reads forward, month to month, without a break.

    The meter is a cumulative counter, so a period's spend is a difference and
    every month's opening reading is the prior month's close. A reading that runs
    backwards inside a month, or an opening that does not pick up where the last
    month left off, means the meter was reset, re-keyed or read out of order -- and
    the delta the allocation is built on is not the postage that was actually
    bought.
    """
    rule = "pst_meter_rolls_forward"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_POSTAGE_LOG)
    if log is None:
        return []
    out: list[Finding] = []
    checked = 0
    periods = _periods(ctx)
    for period in periods:
        with amount_guard(rule, out):
            reading = _meter_reading(ctx, period)
            if reading is None:
                continue  # per_tab_continuity owns this
            begin, end = reading
            checked += 1
            if end < begin:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(log, f"meters/{period}/end_meter_cents"),
                        f"the {period} meter opens at {fmt(begin)} and closes at {fmt(end)}; "
                        f"a cumulative meter cannot run backwards, so the period's spend "
                        f"cannot be taken as the difference",
                    )
                )
    for prior, current in zip(periods, periods[1:], strict=False):
        with amount_guard(rule, out):
            prior_reading = _meter_reading(ctx, prior)
            current_reading = _meter_reading(ctx, current)
            if prior_reading is None or current_reading is None:
                continue  # per_tab_continuity owns this
            if current_reading[0] != prior_reading[1]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(log, f"meters/{current}/begin_meter_cents"),
                        f"the {current} meter opens at {fmt(current_reading[0])} while "
                        f"{prior} closed at {fmt(prior_reading[1])}; the roll-forward is "
                        f"broken and {fmt(current_reading[0] - prior_reading[1])} of metered "
                        f"spend is unaccounted for",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} meter readings run forward and roll into the next month",
            )
        )
    return out


@check("pst_allocations_tie_meter_delta")
def check_pst_allocations_tie_meter_delta(ctx: Context) -> list[Finding]:
    """The per-code postage split sums to exactly the meter delta it divides.

    Postage is the one component of the pool with a physical counter behind it, so
    it is the one component that can be tied to something outside the workbook.
    The per-code amounts must exhaust the month's metered spend exactly, and every
    code must be one the policy recognises.
    """
    rule = "pst_allocations_tie_meter_delta"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_POSTAGE_LOG)
    if log is None:
        return []
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        with amount_guard(rule, out):
            reading = _meter_reading(ctx, period)
            if reading is None:
                continue  # per_tab_continuity owns this
            begin, end = reading
            delta = meter_delta_cents(begin, end)
            if delta < 0:
                continue  # pst_meter_rolls_forward owns this
            allocated = 0
            for i, row in enumerate(_meter_allocations(_meter_row(ctx, period))):
                code = _text(row, "postage_code")
                allocated += require_cents(
                    f"postage[{period}].allocations[{i}].amount_cents", row.get("amount_cents")
                )
                if code not in POSTAGE_CODES:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(log, f"meters/{period}/allocations/{code}"),
                            f"the {period} postage split carries code {code!r}, which is not "
                            f"one of {POSTAGE_CODES}; the amount beside it reconciles to "
                            f"nothing on the meter",
                        )
                    )
            checked += 1
            if allocated != delta:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(log, f"meters/{period}/allocations"),
                        f"the {period} postage split sums to {fmt(allocated)} against a meter "
                        f"delta of {fmt(delta)} (out by {fmt(allocated - delta)}); the "
                        f"physical counter and the workbook disagree",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} postage splits reconcile to their meter delta",
            )
        )
    return out


@check("pst_pool_component_ties")
def check_pst_pool_component_ties(ctx: Context) -> list[Finding]:
    """The pool's postage component equals the month's meter delta.

    The meter is the evidence and the pool line is the assertion built on it. When
    they part company the group allocates postage it never bought, or buys postage
    it never allocates, and the only artifact that would show it is the reading the
    workbook already carries.
    """
    rule = "pst_pool_component_ties"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_POSTAGE_LOG)
    ledger = ctx.one(DOC_COST_POOL_LEDGER)
    if log is None or ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for period in _periods(ctx):
        with amount_guard(rule, out):
            reading = _meter_reading(ctx, period)
            if reading is None:
                continue  # per_tab_continuity owns this
            begin, end = reading
            delta = meter_delta_cents(begin, end)
            if delta < 0:
                continue  # pst_meter_rolls_forward owns this
            row = _pool_row(ctx, period)
            if row is None:
                continue  # per_tab_continuity owns this
            stated = require_cents(
                f"cost_pool[{period}].postage_cents", row.get("postage_cents")
            )
            checked += 1
            if stated != delta:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger, f"pools/{period}/postage_cents"),
                        f"the {period} pool carries postage of {fmt(stated)}; the meter read "
                        f"{fmt(delta)} of spend (out by {fmt(stated - delta)}), so the pool "
                        f"being allocated is not the postage that was bought",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} pool postage components equal their meter delta",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the tabs
# --------------------------------------------------------------------------- #
@check("rpt_rollup_ties")
def check_rpt_rollup_ties(ctx: Context) -> list[Finding]:
    """The year-to-date rollup recomputes from the tabs beneath it.

    The rollup is the figure that leaves the workbook -- it goes into the close
    package and onto the management report -- and a rollup maintained beside the
    tabs rather than derived from them drifts the first time a month is restated
    and nobody re-adds the column. Every stated figure is rebuilt and compared.
    The allocated total is compared only when every month re-derived: reporting a
    shortfall that is really an upstream gap would name the wrong control.
    """
    rule = "rpt_rollup_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_ALLOCATION_REPORT)
    if report is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        rollup = recompute_rollup(ctx)
        comparisons: list[tuple[str, int, str]] = [
            ("period_count", rollup.period_count, "a whole count"),
            ("recipient_count", rollup.recipient_count, "a whole count"),
            ("pool_total_cents", rollup.pool_total_cents, "integer cents"),
        ]
        if rollup.complete:
            comparisons.append(
                ("allocated_total_cents", rollup.allocated_total_cents, "integer cents")
            )
        for field_name, want, unit in comparisons:
            have = require_cents(
                f"allocation_report.{field_name}", report.get(field_name), unit=unit
            )
            if have != want:
                rendered_have = fmt(have) if unit == "integer cents" else str(have)
                rendered_want = fmt(want) if unit == "integer cents" else str(want)
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(report, field_name),
                        f"the rollup states {field_name} of {rendered_have}; the tabs beneath "
                        f"it recompute {rendered_want}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "the year-to-date rollup recomputes from the month tabs beneath it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one allocation file."""
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
    """Analyze every ``.json`` allocation file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of allocation-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
