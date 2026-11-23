"""
Unit sales and commission tie-out control engine (READ-ONLY).
=============================================================

Loads each sales file (a ``.json`` file produced by :mod:`sales_engine.generate`)
and runs an ordered *registry* of independent controls over it.

Scope
-----
This engine is about **whether the Matrix still ties to the tabs that feed it**,
not about whether a commission should be paid or a closing should be booked.
Nothing here posts, files or releases anything. Where the sale proceeds land in
the general ledger is a separate engine's job; this one asks only whether the
sales-administration workbook is internally true.

The shape of the problem
------------------------
A for-sale housing project is administered out of one workbook, instantiated from
the same template on every project. The Matrix carries every unit: plan, plan
square footage, list price, sales price, concession, revenue per square foot,
closing costs and total commission. The Sold/Close tab logs the offer date, the
actual date sold, the closing date and whether proof of closing came back. The
Commission Log splits each unit's total commission across named selling agents.

Three failures hide inside that, and none of them look wrong on the tab: the
derived column that somebody typed over, so revenue per square foot or net
proceeds no longer follows from the prices beside it; the commission splits that
no longer add to the total the Matrix authorised; and the tabs that stop
reconciling -- a unit marked Sold with no closing row, a sale date before the
offer date, a rollup the Matrix does not support.

The registry is organised around that:

1. ``set_``   -- is the sales file complete?
2. ``plan_``  -- is the plan register sound, and is every plan area real?
3. ``unit_``  -- is every Matrix row well-formed, uniquely identified and typed?
4. ``price_`` -- does each unit's price arithmetic re-derive?
5. ``comm_``  -- does the commission re-derive, and does the log split it exactly?
6. ``close_`` -- do sold units reconcile to the Sold/Close tab, in order, with proof?
7. ``rpt_``   -- does the rollup recompute from the Matrix it summarises?

Design notes
------------
- **Strictly read-only.** Sales files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every derived figure is compared with exact
  ``==``; a cent of drift on a commission split is a cent paid to nobody.
- **One tie-out kernel.** Controls and the generator share the arithmetic in
  :mod:`sales_engine.tieout`, so a derived figure cannot disagree with the data
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

from .model import (
    DOC_AGENT_REGISTER,
    DOC_COMMISSION_LOG,
    DOC_COMMISSION_SCHEDULE,
    DOC_PLAN_REGISTER,
    DOC_SALES_ROLLUP,
    DOC_SOLD_CLOSE_LOG,
    DOC_TYPES,
    DOC_UNIT_MATRIX,
    SALE_CHANNELS,
    UNIT_SOLD,
    UNIT_STATUSES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents
from .tieout import (
    CloseDates,
    concession_within_price,
    dates_in_order,
    discount_to_list_bps,
    net_proceeds,
    proof_due,
    revenue_per_sqft,
    splits_tie,
    total_commission,
    within_discount_band,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render a :class:`~sales_engine.money.AmountInvalidError` as a finding."""
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
# Sales-file helpers
# --------------------------------------------------------------------------- #
def _plans(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PLAN_REGISTER), "plans")


def _plan_code(row: dict[str, Any]) -> str:
    value = row.get("plan_code")
    return value if isinstance(value, str) and value else "?"


def _plan_codes(ctx: Context) -> set[str]:
    """Every plan code the register names, sound or not.

    Membership only. A plan whose square footage is missing or non-positive is
    still *declared*, so ``unit_plan_defined`` must not report the units on it as
    naming a plan that does not exist -- ``plan_sqft_positive`` owns that break.
    """
    return {_plan_code(row) for row in _plans(ctx)}


def _plan_sqft(ctx: Context) -> dict[str, int]:
    """Plan code -> plan square footage, restricted to sound rows.

    Only plans carrying a positive whole square footage appear, so every caller
    that divides by an area divides by one that exists.
    """
    out: dict[str, int] = {}
    for row in _plans(ctx):
        code = _plan_code(row)
        sqft = _int(row, "plan_sqft")
        if code != "?" and sqft is not None and sqft > 0 and code not in out:
            out[code] = sqft
    return out


def _units(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_UNIT_MATRIX), "units")


def _unit_id(row: dict[str, Any]) -> str:
    value = row.get("unit_id")
    return value if isinstance(value, str) and value else "?"


def _unit_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _units(ctx):
        uid = _unit_id(row)
        if uid != "?" and uid not in out:
            out[uid] = row
    return out


def _sold_unit_ids(ctx: Context) -> list[str]:
    """Unit ids the Matrix marks Sold, in Matrix order, de-duplicated."""
    out: list[str] = []
    for row in _units(ctx):
        if _text(row, "status") == UNIT_SOLD:
            uid = _unit_id(row)
            if uid not in out:
                out.append(uid)
    return out


def _schedule(ctx: Context) -> dict[str, dict[str, Any]]:
    """Sale channel -> commission-schedule row."""
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_COMMISSION_SCHEDULE), "rates"):
        channel = _text(row, "sale_channel")
        if channel and channel not in out:
            out[channel] = row
    return out


def _closings(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SOLD_CLOSE_LOG), "closings")


def _closing_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _closings(ctx):
        uid = _text(row, "unit_id")
        if uid and uid not in out:
            out[uid] = row
    return out


def _agents(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_AGENT_REGISTER), "agents")


def _agent_ids(ctx: Context) -> set[str]:
    out: set[str] = set()
    for row in _agents(ctx):
        agent_id = _text(row, "agent_id")
        if agent_id is not None:
            out.add(agent_id)
    return out


def _split_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_COMMISSION_LOG), "splits")


def _splits_by_unit(ctx: Context) -> dict[str, list[dict[str, Any]]]:
    """Unit id -> its Commission-Log rows, in log order."""
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _split_rows(ctx):
        uid = _text(row, "unit_id")
        if uid:
            out.setdefault(uid, []).append(row)
    return out


def _rate_bps(ctx: Context, unit: dict[str, Any]) -> int | None:
    """The commission rate governing a unit, or ``None`` when undeclared.

    Reads the schedule row for the unit's sale channel. Raises
    :class:`AmountInvalidError` if the row carries a rate that is not an integer
    basis-point figure; the calling control contains that to the row being read.
    """
    row = _schedule(ctx).get(_text(unit, "sale_channel") or "")
    if row is None:
        return None
    return require_cents(
        f"commission_schedule[{_text(unit, 'sale_channel')}].commission_rate_bps",
        row.get("commission_rate_bps"),
        unit="an integer basis-point rate",
    )


def _close_dates(row: dict[str, Any]) -> CloseDates | None:
    """Read a Sold/Close row into a :class:`~sales_engine.tieout.CloseDates`."""
    offer = _parse_date(row.get("offer_date"))
    sold = _parse_date(row.get("actual_date_sold"))
    closing = _parse_date(row.get("closing_date"))
    if offer is None or sold is None or closing is None:
        return None
    return CloseDates(offer_date=offer, actual_date_sold=sold, closing_date=closing)


# --------------------------------------------------------------------------- #
# Re-derivation shared with the generator
# --------------------------------------------------------------------------- #
def recompute_unit_derived(ctx: Context, unit: dict[str, Any]) -> dict[str, int | None]:
    """Re-derive one Matrix row's three computed columns from its base facts.

    Revenue per square foot, net proceeds and total commission are formulas on the
    Matrix, and this is the formula. Shared with the generator through
    :mod:`sales_engine.tieout`, so the columns the engine recomputes are the
    columns that produced the data. A value is ``None`` where the input it needs
    is undeclared -- an unknown plan area, an unpriced sale channel -- and a named
    control owns each of those gaps.

    Raises :class:`AmountInvalidError` if a price it must read is not integer
    cents; the calling control contains that to the unit being read.
    """
    uid = _unit_id(unit)
    sales_price = require_cents(
        f"unit[{uid}].sales_price_cents", unit.get("sales_price_cents")
    )
    concession = require_cents(
        f"unit[{uid}].concession_cents", unit.get("concession_cents")
    )
    closing_costs = require_cents(
        f"unit[{uid}].closing_costs_cents", unit.get("closing_costs_cents")
    )
    sqft = _plan_sqft(ctx).get(_text(unit, "plan_code") or "")
    rate = _rate_bps(ctx, unit)
    return {
        "rev_per_sqft_cents": (
            revenue_per_sqft(sales_price, sqft) if sqft is not None else None
        ),
        "net_proceeds_cents": net_proceeds(sales_price, concession, closing_costs),
        "total_commission_cents": (
            total_commission(sales_price, rate) if rate is not None else None
        ),
    }


def recompute_sold_count(ctx: Context) -> int:
    """The number of units the Matrix marks Sold.

    Reads no amounts, so it never raises on a malformed price: a count that could
    be lost to a bad cent somewhere else would not be a count.
    """
    return sum(1 for row in _units(ctx) if _text(row, "status") == UNIT_SOLD)


def recompute_revenue_totals(ctx: Context) -> dict[str, int]:
    """Sold-unit sales price and net proceeds, summed off the Matrix.

    Raises :class:`AmountInvalidError` if a figure it must read is not integer
    cents.
    """
    sales = 0
    proceeds = 0
    for unit in _units(ctx):
        if _text(unit, "status") != UNIT_SOLD:
            continue
        uid = _unit_id(unit)
        sales += require_cents(
            f"unit[{uid}].sales_price_cents", unit.get("sales_price_cents")
        )
        proceeds += require_cents(
            f"unit[{uid}].net_proceeds_cents", unit.get("net_proceeds_cents")
        )
    return {"total_sales_price_cents": sales, "total_net_proceeds_cents": proceeds}


def recompute_commission_total(ctx: Context) -> int:
    """Total selling commission, summed off the Matrix commission column.

    Summed over every unit, not only the sold ones: an unsold unit carries no
    commission, and a rollup that quietly skipped rows would hide the one that
    does.
    """
    running = 0
    for unit in _units(ctx):
        running += require_cents(
            f"unit[{_unit_id(unit)}].total_commission_cents",
            unit.get("total_commission_cents"),
        )
    return running


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the sales file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the sales file carries "
                    f"exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} sales artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every closing test is "
                f"measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# plan_ -- the plan register the Matrix divides by
# --------------------------------------------------------------------------- #
@check("plan_unique_codes")
def check_plan_unique_codes(ctx: Context) -> list[Finding]:
    """No plan code appears twice in the plan register.

    The plan code is how a Matrix row finds its square footage. A duplicate makes
    the area ambiguous, and revenue per square foot is only as sound as the
    denominator it divided by.
    """
    rule = "plan_unique_codes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PLAN_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _plans(ctx):
        code = _plan_code(row)
        seen[code] = seen.get(code, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"plans/{code}"),
            f"plan code {code} appears {count} times; a unit that names it cannot be "
            f"priced against one square footage",
        )
        for code, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} plan codes are unique")
        )
    return out


@check("plan_sqft_positive")
def check_plan_sqft_positive(ctx: Context) -> list[Finding]:
    """Every plan carries a positive whole square footage.

    A zero or missing area is not a small plan; it is a denominator, and the
    revenue-per-square-foot column above it is meaningless until it is fixed.
    """
    rule = "plan_sqft_positive"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PLAN_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _plans(ctx):
        code = _plan_code(row)
        with amount_guard(rule, out):
            sqft = require_cents(
                f"plan[{code}].plan_sqft",
                row.get("plan_sqft"),
                unit="a whole square-foot count",
            )
            if sqft <= 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"plans/{code}/plan_sqft"),
                        f"plan {code} states {sqft} square feet; revenue per square foot "
                        f"divides by this figure and cannot divide by it",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_plans(ctx))} plans carry a positive square footage",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# unit_ -- the Matrix rows themselves
# --------------------------------------------------------------------------- #
@check("unit_required_fields")
def check_unit_required_fields(ctx: Context) -> list[Finding]:
    """Every Matrix row carries the descriptive fields the controls read."""
    rule = "unit_required_fields"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    required = ("unit_id", "building", "plan_code", "sale_channel", "status")
    out: list[Finding] = []
    for row in _units(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(matrix, f"units/{_unit_id(row)}"),
                    f"unit {_unit_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_units(ctx))} Matrix rows carry their required fields",
            )
        )
    return out


@check("unit_unique_ids")
def check_unit_unique_ids(ctx: Context) -> list[Finding]:
    """No unit id appears twice on the Matrix.

    The unit id joins the Matrix to the Sold/Close tab and to the Commission Log.
    A duplicate makes a closing row ambiguous about which unit closed and a
    commission split ambiguous about which row authorised it.
    """
    rule = "unit_unique_ids"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    seen: dict[str, int] = {}
    for row in _units(ctx):
        uid = _unit_id(row)
        seen[uid] = seen.get(uid, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(matrix, f"units/{uid}"),
            f"unit id {uid} appears {count} times; a closing or a commission split that "
            f"names it cannot be attributed to one unit",
        )
        for uid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} unit ids are unique")
        )
    return out


@check("unit_plan_defined")
def check_unit_plan_defined(ctx: Context) -> list[Finding]:
    """Every Matrix row names a plan the register declares.

    Without the plan there is no square footage, so the revenue-per-square-foot
    control would skip the row and the Matrix would carry an untested column.
    """
    rule = "unit_plan_defined"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PLAN_REGISTER)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if register is None or matrix is None:
        return []
    codes = _plan_codes(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(matrix, f"units/{_unit_id(row)}/plan_code"),
            f"unit {_unit_id(row)} names plan {_text(row, 'plan_code')!r}, which is not "
            f"in the plan register; its square footage is unknown",
        )
        for row in _units(ctx)
        if _text(row, "plan_code") and _text(row, "plan_code") not in codes
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every Matrix row names a plan in the register"
            )
        )
    return out


@check("unit_status_valid")
def check_unit_status_valid(ctx: Context) -> list[Finding]:
    """Every Matrix row carries a known status.

    Status is what obliges a unit to appear on the Sold/Close tab and what puts it
    into the rollup. An unknown status is a unit that is neither counted nor
    reconciled, and it disappears between the two.
    """
    rule = "unit_status_valid"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(matrix, f"units/{_unit_id(row)}/status"),
            f"unit {_unit_id(row)} is marked {_text(row, 'status')!r}, which is not one "
            f"of {UNIT_STATUSES}; it is neither counted nor reconciled",
        )
        for row in _units(ctx)
        if _text(row, "status") not in UNIT_STATUSES
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_units(ctx))} Matrix rows carry a known status",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# price_ -- the derived price columns re-derive
# --------------------------------------------------------------------------- #
@check("price_rev_per_sqft_recomputes")
def check_price_rev_per_sqft_recomputes(ctx: Context) -> list[Finding]:
    """Revenue per square foot equals the sales price over the plan area.

    Compared with exact ``==`` in integer cents. This is the column the sales
    office reports to the market and the column an appraiser reads back, and it is
    a formula until somebody types over one cell of it.
    """
    rule = "price_rev_per_sqft_recomputes"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    areas = _plan_sqft(ctx)
    out: list[Finding] = []
    checked = 0
    for unit in _units(ctx):
        uid = _unit_id(unit)
        sqft = areas.get(_text(unit, "plan_code") or "")
        if sqft is None:
            continue  # unit_plan_defined / plan_sqft_positive own this
        with amount_guard(rule, out):
            sales_price = require_cents(
                f"unit[{uid}].sales_price_cents", unit.get("sales_price_cents")
            )
            stated = require_cents(
                f"unit[{uid}].rev_per_sqft_cents", unit.get("rev_per_sqft_cents")
            )
            derived = revenue_per_sqft(sales_price, sqft)
            checked += 1
            if derived != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(matrix, f"units/{uid}/rev_per_sqft_cents"),
                        f"unit {uid} states {fmt(stated)} per square foot; "
                        f"{fmt(sales_price)} over {sqft} square feet re-derives "
                        f"{fmt(derived or 0)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} revenue-per-square-foot figures re-derive",
            )
        )
    return out


@check("price_concession_within_price")
def check_price_concession_within_price(ctx: Context) -> list[Finding]:
    """The concession is non-negative and never exceeds the sales price.

    A concession larger than the price is a unit conveyed for a negative number,
    and a negative concession is a charge to the buyer entered in the discount
    column. Either way the net-proceeds figure below it is describing a
    transaction that did not happen.
    """
    rule = "price_concession_within_price"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _units(ctx):
        uid = _unit_id(unit)
        with amount_guard(rule, out):
            sales_price = require_cents(
                f"unit[{uid}].sales_price_cents", unit.get("sales_price_cents")
            )
            concession = require_cents(
                f"unit[{uid}].concession_cents", unit.get("concession_cents")
            )
            checked += 1
            if not concession_within_price(concession, sales_price):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(matrix, f"units/{uid}/concession_cents"),
                        f"unit {uid} grants a concession of {fmt(concession)} against a "
                        f"sales price of {fmt(sales_price)}; a concession sits inside "
                        f"the price it discounts",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} concessions sit inside the price"
            )
        )
    return out


@check("price_net_proceeds_recomputes")
def check_price_net_proceeds_recomputes(ctx: Context) -> list[Finding]:
    """Net proceeds equal sales price less concession less closing costs.

    Compared with exact ``==``. This is the figure the project pro forma is
    measured against, and it is the one column on the Matrix that three other
    columns feed.
    """
    rule = "price_net_proceeds_recomputes"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _units(ctx):
        uid = _unit_id(unit)
        with amount_guard(rule, out):
            sales_price = require_cents(
                f"unit[{uid}].sales_price_cents", unit.get("sales_price_cents")
            )
            concession = require_cents(
                f"unit[{uid}].concession_cents", unit.get("concession_cents")
            )
            closing_costs = require_cents(
                f"unit[{uid}].closing_costs_cents", unit.get("closing_costs_cents")
            )
            stated = require_cents(
                f"unit[{uid}].net_proceeds_cents", unit.get("net_proceeds_cents")
            )
            derived = net_proceeds(sales_price, concession, closing_costs)
            checked += 1
            if derived != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(matrix, f"units/{uid}/net_proceeds_cents"),
                        f"unit {uid} states net proceeds of {fmt(stated)}; "
                        f"{fmt(sales_price)} less {fmt(concession)} concession less "
                        f"{fmt(closing_costs)} closing costs re-derives {fmt(derived)} "
                        f"(off by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} net-proceeds figures re-derive")
        )
    return out


@check("price_discount_to_list")
def check_price_discount_to_list(ctx: Context) -> list[Finding]:
    """A sold unit discounted beyond the approved band is flagged.

    Deliberately a FLAG, not a failure: the price was struck and the sale is real,
    but a discount past the band was outside the sales office's own authority and
    wants a signature behind it. The band comes from the file's own
    ``max_discount_bps``.
    """
    rule = "price_discount_to_list"
    _sev(rule, Status.FLAG)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    band = ctx.max_discount_bps
    out: list[Finding] = []
    checked = 0
    for unit in _units(ctx):
        if _text(unit, "status") != UNIT_SOLD:
            continue  # an unsold unit has no struck price to discount
        uid = _unit_id(unit)
        with amount_guard(rule, out):
            list_price = require_cents(
                f"unit[{uid}].list_price_cents", unit.get("list_price_cents")
            )
            sales_price = require_cents(
                f"unit[{uid}].sales_price_cents", unit.get("sales_price_cents")
            )
            discount = discount_to_list_bps(list_price, sales_price)
            checked += 1
            if not within_discount_band(discount, band):
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(matrix, f"units/{uid}/sales_price_cents"),
                        f"unit {uid} sold at {fmt(sales_price)} against a list of "
                        f"{fmt(list_price)}, a discount of {fmt_bps(discount)}; the "
                        f"approved band is {fmt_bps(band)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} sold units priced inside the {fmt_bps(band)} band",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# comm_ -- the commission and the split of it
# --------------------------------------------------------------------------- #
@check("comm_rate_defined")
def check_comm_rate_defined(ctx: Context) -> list[Finding]:
    """Every unit's sale channel carries a commission-schedule rate.

    Without the rate the engine knows a commission was booked but not what rate
    should have produced it, so the re-derivation control would silently skip the
    row.
    """
    rule = "comm_rate_defined"
    _sev(rule, Status.FAIL)
    schedule_doc = ctx.one(DOC_COMMISSION_SCHEDULE)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if schedule_doc is None or matrix is None:
        return []
    schedule = _schedule(ctx)
    out: list[Finding] = []
    checked = 0
    for unit in _units(ctx):
        channel = _text(unit, "sale_channel")
        if channel is None:
            continue  # unit_required_fields owns this
        checked += 1
        if channel not in schedule:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule_doc, f"rates/{channel}"),
                    f"the commission schedule has no rate for sale channel {channel!r}, "
                    f"which unit {_unit_id(unit)} was sold through; the known channels "
                    f"are {SALE_CHANNELS}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} units price against a scheduled rate"
            )
        )
    return out


@check("comm_total_recomputes")
def check_comm_total_recomputes(ctx: Context) -> list[Finding]:
    """Total commission equals the channel rate applied to the sales price.

    Compared with exact ``==`` after truncating basis-point arithmetic. The Matrix
    commission column is what the Commission Log divides, so a commission that
    does not re-derive misstates every split beneath it.
    """
    rule = "comm_total_recomputes"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if matrix is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _units(ctx):
        uid = _unit_id(unit)
        with amount_guard(rule, out):
            rate = _rate_bps(ctx, unit)
            if rate is None:
                continue  # comm_rate_defined owns this
            sales_price = require_cents(
                f"unit[{uid}].sales_price_cents", unit.get("sales_price_cents")
            )
            stated = require_cents(
                f"unit[{uid}].total_commission_cents", unit.get("total_commission_cents")
            )
            derived = total_commission(sales_price, rate)
            checked += 1
            if derived != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(matrix, f"units/{uid}/total_commission_cents"),
                        f"unit {uid} states commission of {fmt(stated)}; {fmt_bps(rate)} "
                        f"on a sales price of {fmt(sales_price)} re-derives "
                        f"{fmt(derived)} (off by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} commission totals re-derive")
        )
    return out


@check("comm_splits_tie")
def check_comm_splits_tie(ctx: Context) -> list[Finding]:
    """The Commission-Log splits on a unit sum to the commission on the Matrix.

    This is the control the engine exists for. The log is what names an agent and
    an amount, and the Matrix row is what authorised the total. Compared with
    exact ``==``: a cent of drift is a cent paid to nobody or a cent paid twice,
    and it recurs on every unit the template produced.
    """
    rule = "comm_splits_tie"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_COMMISSION_LOG)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if log is None or matrix is None:
        return []
    grouped = _splits_by_unit(ctx)
    units = _unit_map(ctx)
    out: list[Finding] = []
    checked = 0
    for uid in sorted(set(units) | set(grouped)):
        unit = units.get(uid)
        rows = grouped.get(uid, [])
        if unit is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"splits/{uid}"),
                    f"the Commission Log splits {len(rows)} amount(s) on unit {uid}, "
                    f"which is not on the Matrix; no row authorised the total",
                )
            )
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"unit[{uid}].total_commission_cents", unit.get("total_commission_cents")
            )
            splits = [
                require_cents(
                    f"commission_log[{uid}/{_text(row, 'agent_id')}].split_cents",
                    row.get("split_cents"),
                )
                for row in rows
            ]
            checked += 1
            if not splits_tie(splits, stated):
                logged = sum(splits)
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(log, f"splits/{uid}"),
                        f"unit {uid} splits {fmt(logged)} across {len(splits)} agent(s); "
                        f"the Matrix authorises {fmt(stated)} "
                        f"(off by {fmt(logged - stated)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} units split exactly their commission"
            )
        )
    return out


@check("comm_agent_known")
def check_comm_agent_known(ctx: Context) -> list[Finding]:
    """Every Commission-Log split names an agent in the agent register.

    A split paid to an id nobody registered is a commission with no payee behind
    it, and it ties to the Matrix total perfectly while doing so.
    """
    rule = "comm_agent_known"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_COMMISSION_LOG)
    register = ctx.one(DOC_AGENT_REGISTER)
    if log is None or register is None:
        return []
    known = _agent_ids(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(log, f"splits/{_text(row, 'unit_id')}/{_text(row, 'agent_id')}"),
            f"unit {_text(row, 'unit_id')} splits commission to agent "
            f"{_text(row, 'agent_id')!r}, who is not in the agent register",
        )
        for row in _split_rows(ctx)
        if _text(row, "agent_id") not in known
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_split_rows(ctx))} splits name a registered agent",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# close_ -- the Sold/Close tab reconciles to the Matrix
# --------------------------------------------------------------------------- #
@check("close_sold_reconciles")
def check_close_sold_reconciles(ctx: Context) -> list[Finding]:
    """Units marked Sold on the Matrix reconcile one-to-one to the Sold/Close tab.

    Both directions, because both directions happen. A unit marked Sold with no
    closing row is revenue the Matrix claims and the tab cannot evidence; a closing
    row for a unit the Matrix does not call Sold is a closing nobody counted.
    """
    rule = "close_sold_reconciles"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    log = ctx.one(DOC_SOLD_CLOSE_LOG)
    if matrix is None or log is None:
        return []
    sold = _sold_unit_ids(ctx)
    logged = _closing_map(ctx)
    out: list[Finding] = []
    for uid in sold:
        if uid not in logged:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"closings/{uid}"),
                    f"unit {uid} is marked {UNIT_SOLD} on the Matrix but has no row on "
                    f"the Sold/Close tab; the sale is claimed and not evidenced",
                )
            )
    for uid in logged:
        if uid not in sold:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(matrix, f"units/{uid}/status"),
                    f"the Sold/Close tab logs a closing for unit {uid}, which the Matrix "
                    f"does not mark {UNIT_SOLD}; the closing is unaccounted for",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(sold)} sold units reconcile one-to-one to the Sold/Close tab",
            )
        )
    return out


@check("close_date_order")
def check_close_date_order(ctx: Context) -> list[Finding]:
    """A closing's dates run offer, sale, closing -- in that order.

    Out-of-order dates are how a sale lands in the wrong period. A closing logged
    before the offer that produced it, or a sale date after the closing that
    settled it, cannot both be true, and whichever one is wrong is the one the
    revenue cut-off used.
    """
    rule = "close_date_order"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_SOLD_CLOSE_LOG)
    if log is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _closings(ctx):
        uid = _text(row, "unit_id") or "?"
        dates = _close_dates(row)
        if dates is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"closings/{uid}"),
                    f"unit {uid} carries an unreadable offer, sale or closing date; the "
                    f"ordering gate cannot be applied to it",
                )
            )
            continue
        checked += 1
        if not dates_in_order(dates):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"closings/{uid}/actual_date_sold"),
                    f"unit {uid} was offered {dates.offer_date.isoformat()}, sold "
                    f"{dates.actual_date_sold.isoformat()} and closed "
                    f"{dates.closing_date.isoformat()}; the sequence does not run "
                    f"offer, sale, closing",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} closings run in date order")
        )
    return out


@check("close_proof_received")
def check_close_proof_received(ctx: Context) -> list[Finding]:
    """A closing whose date has arrived has its proof of closing on file.

    Deliberately a FLAG, not a failure: the sale closed, and what is missing is the
    evidence of it. Proof falls due the moment the closing date arrives, so a unit
    closing after the review date is not yet late.
    """
    rule = "close_proof_received"
    _sev(rule, Status.FLAG)
    log = ctx.one(DOC_SOLD_CLOSE_LOG)
    as_of = _parse_date(ctx.as_of)
    if log is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _closings(ctx):
        uid = _text(row, "unit_id") or "?"
        closing = _parse_date(row.get("closing_date"))
        if closing is None:
            continue  # close_date_order owns this
        if not proof_due(closing, as_of):
            continue
        checked += 1
        if row.get("proof_received") is not True:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(log, f"closings/{uid}/proof_received"),
                    f"unit {uid} closed {closing.isoformat()}, on or before the review "
                    f"date {as_of.isoformat()}, and its proof of closing has not been "
                    f"received; the sale is recorded on an unevidenced settlement",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} due closings have proof on file"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the Matrix
# --------------------------------------------------------------------------- #
@check("rpt_sold_count_ties")
def check_rpt_sold_count_ties(ctx: Context) -> list[Finding]:
    """The rollup's sold-unit count ties the Matrix.

    The number that reaches an investor letter is a count, and a count maintained
    beside the Matrix rather than derived from it drifts the first time a unit
    status moves and nobody re-adds the column.
    """
    rule = "rpt_sold_count_ties"
    _sev(rule, Status.FAIL)
    rollup = ctx.one(DOC_SALES_ROLLUP)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if rollup is None or matrix is None:
        return []
    derived = recompute_sold_count(ctx)
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "sales_rollup.sold_unit_count",
            rollup.get("sold_unit_count"),
            unit="a whole count",
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, "sold_unit_count"),
                    f"the rollup states {stated} sold unit(s); the Matrix recomputes "
                    f"{derived}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the rollup count of {derived} sold unit(s) ties the Matrix",
                )
            )
    return out


@check("rpt_revenue_ties")
def check_rpt_revenue_ties(ctx: Context) -> list[Finding]:
    """The rollup's sales price and net proceeds tie the sold rows of the Matrix.

    Two totals, one control: they are the same summation over the same rows, and a
    rollup that agreed on one and not the other would still be a rollup nobody
    re-added.
    """
    rule = "rpt_revenue_ties"
    _sev(rule, Status.FAIL)
    rollup = ctx.one(DOC_SALES_ROLLUP)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if rollup is None or matrix is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = recompute_revenue_totals(ctx)
        for key, label in (
            ("total_sales_price_cents", "sales price"),
            ("total_net_proceeds_cents", "net proceeds"),
        ):
            stated = require_cents(f"sales_rollup.{key}", rollup.get(key))
            if stated != derived[key]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollup, key),
                        f"the rollup states {fmt(stated)} of {label}; the sold rows of "
                        f"the Matrix sum to {fmt(derived[key])} "
                        f"(off by {fmt(stated - derived[key])})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "the rollup sales price and net proceeds tie the Matrix",
            )
        )
    return out


@check("rpt_commission_ties")
def check_rpt_commission_ties(ctx: Context) -> list[Finding]:
    """The rollup's total commission ties the Matrix commission column.

    The commission total is what the sales office reports as its cost of sale, and
    it is the figure a Commission Log is reconciled to unit by unit. Overstated, it
    understates the margin the project is measured on.
    """
    rule = "rpt_commission_ties"
    _sev(rule, Status.FAIL)
    rollup = ctx.one(DOC_SALES_ROLLUP)
    matrix = ctx.one(DOC_UNIT_MATRIX)
    if rollup is None or matrix is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = recompute_commission_total(ctx)
        stated = require_cents(
            "sales_rollup.total_commission_cents",
            rollup.get("total_commission_cents"),
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, "total_commission_cents"),
                    f"the rollup states {fmt(stated)} of total commission; the Matrix "
                    f"commission column sums to {fmt(derived)} "
                    f"(off by {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the rollup commission of {fmt(derived)} ties the Matrix",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one sales file."""
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
    """Analyze every ``.json`` sales file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of sales-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
