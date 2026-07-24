"""
Depreciation & prepaid amortization register control engine (READ-ONLY).
========================================================================

Loads each close file (a ``.json`` file produced by
:mod:`depreciation_engine.generate`) and runs an ordered *registry* of
independent controls over it.

Scope
-----
This engine is about **whether the register's arithmetic is the stated
convention and whether its totals tie out**. The JE-posting cadence, loan
amortization and the prepaid-insurance allocation are neighbouring engines'
jobs; this engine owns the fixed-asset and prepaid subledgers themselves.

The shape of the problem
------------------------
An entity closes a month with a fixed-asset register and a prepaid schedule
full of tiny derived numbers -- a monthly charge per asset, a months-used
count, an accumulated balance, a net book value, a per-item amortization
waterfall -- and every one of them was once a formula somebody could have
overtyped. Three failures hide inside that, and none of them look wrong in a
register that still foots: the derivation that drifted from cost, life and
convention; the roll-forward that no longer closes; and the register total that
quietly stopped tying the GL control account and the recurring JE.

The registry is organised around that:

1.  ``set_``  -- is the close file complete?
2.  ``cap_``  -- did the capitalization threshold gate hold, both directions?
3.  ``life_`` -- is every asset's life and method the class table's?
4.  ``sl_``   -- does every straight-line charge re-derive?
5.  ``date_`` -- do the in-service / end-of-depreciation date gates hold?
6.  ``nbv_``  -- months-used cap, accumulated re-derivation, NBV identity?
7.  ``roll_`` -- do the accumulated and prepaid roll-forwards close and tie?
8.  ``pre_``  -- does every prepaid waterfall figure re-derive from its window?
9.  ``disp_`` -- are disposals rolled off, written off correctly, and watched?
10. ``gl_``   -- do the register totals tie the GL control accounts?
11. ``je_``   -- do the register totals tie the posted recurring JE?

Design notes
------------
- **Strictly read-only.** Close files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every re-derivation is compared with exact
  ``==``; every threshold with exact ``>=``.
- **One schedule kernel.** Controls and the generator share
  :mod:`depreciation_engine.schedule`, so a stated figure cannot disagree with
  the arithmetic that produced it.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.
"""

from __future__ import annotations

import contextlib
import functools
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .model import (
    DOC_ASSET_REGISTER,
    DOC_CAP_POLICY,
    DOC_DISPOSAL_REGISTER,
    DOC_GL_BALANCES,
    DOC_LIFE_TABLE,
    DOC_PREPAID_REGISTER,
    DOC_RECURRING_JE,
    DOC_ROLLFORWARD,
    DOC_TYPES,
    GL_ACCUM,
    GL_COST,
    GL_PREPAID,
    JE_AMORTIZATION,
    JE_DEPRECIATION,
    LIFE_SOURCE_FIXED,
    LIFE_SOURCE_LEASE_TERM,
    METHOD_STRAIGHT_LINE,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents
from .schedule import (
    accum_dep_cents,
    amort_expense_cents,
    capitalization_required,
    depr_expense_cents,
    end_depr_month,
    monthly_amort_cents,
    monthly_dep_cents,
    month_str,
    months_elapsed,
    months_used,
    parse_month,
    past_disposal_review,
    prepaid_beginning_cents,
    prepaid_ending_cents,
    window_ending_soon,
    window_periods,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~depreciation_engine.money.AmountInvalidError` as a finding."""
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


def _sev(rule_id: str, status: Status) -> Status:
    SEVERITY[rule_id] = status
    return status


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
# Close-file helpers
# --------------------------------------------------------------------------- #
def _close(ctx: Context) -> int | None:
    return parse_month(ctx.close_month)


def _assets(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ASSET_REGISTER), "assets")


def _asset_id(row: dict[str, Any]) -> str:
    value = row.get("asset_id")
    return value if isinstance(value, str) and value else "?"


def _prepaids(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PREPAID_REGISTER), "items")


def _item_id(row: dict[str, Any]) -> str:
    value = row.get("item_id")
    return value if isinstance(value, str) and value else "?"


def _disposals(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DISPOSAL_REGISTER), "disposals")


def _life_table(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_LIFE_TABLE), "classes"):
        cls = _text(row, "asset_class")
        if cls and cls not in out:
            out[cls] = row
    return out


def _asset_base(row: dict[str, Any]) -> tuple[int, int, int] | None:
    """``(cost_cents, life_months, in_service_index)`` or ``None`` if unreadable.

    Raises :class:`AmountInvalidError` if the cost is present but not integer
    cents; returns ``None`` only when a base fact is absent or unusable, so the
    derivation controls skip a row exactly when there is nothing to derive from.
    """
    cost = require_cents(f"asset[{_asset_id(row)}].cost_cents", row.get("cost_cents"))
    life = _int(row, "useful_life_months")
    in_service = parse_month(row.get("in_service_month"))
    if life is None or life < 1 or in_service is None:
        return None
    return cost, life, in_service


def _prepaid_window(row: dict[str, Any]) -> tuple[int, int, int] | None:
    """``(start, end, booked_from)`` month indexes, or ``None`` if invalid.

    The window is usable only when it parses, runs forward, and books from a
    month inside itself; ``pre_window_valid`` owns reporting anything else.
    """
    start = parse_month(row.get("window_start"))
    end = parse_month(row.get("window_end"))
    booked = parse_month(row.get("booked_from"))
    if start is None or end is None or booked is None:
        return None
    if start > end or booked < start or booked > end:
        return None
    return start, end, booked


def _gl_account(ctx: Context, account: str) -> dict[str, Any] | None:
    for row in _rows(ctx.one(DOC_GL_BALANCES), "accounts"):
        if _text(row, "account") == account:
            return row
    return None


def _je_line(ctx: Context, line_id: str) -> dict[str, Any] | None:
    for row in _rows(ctx.one(DOC_RECURRING_JE), "lines"):
        if _text(row, "line_id") == line_id:
            return row
    return None


def _sum_asset_column(ctx: Context, key: str) -> int:
    """Sum a stated integer-cent column over the asset register.

    Raises :class:`AmountInvalidError` on the first malformed amount; the
    calling control contains that to itself via :func:`amount_guard`.
    """
    total = 0
    for row in _assets(ctx):
        total += require_cents(f"asset[{_asset_id(row)}].{key}", row.get(key))
    return total


def _sum_prepaid_column(ctx: Context, key: str) -> int:
    total = 0
    for row in _prepaids(ctx):
        total += require_cents(f"prepaid[{_item_id(row)}].{key}", row.get(key))
    return total


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the close file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the close file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} close artifacts are present",
            )
        )
    if _close(ctx) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"close_month {ctx.close_month!r} is not a readable YYYY-MM month; "
                f"every derivation and date gate is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cap_ -- the capitalization threshold gate
# --------------------------------------------------------------------------- #
@check("cap_threshold_gate")
def check_cap_threshold_gate(ctx: Context) -> list[Finding]:
    """Every expense-log item sits on the correct side of the threshold.

    The gate is a hard predicate in both directions: an item at or above the
    threshold (and not category-excluded) must be capitalized, and an item below
    it -- or excluded outright, like annual software -- must be expensed. A
    sub-threshold item capitalized clutters the register for years; a
    qualifying item expensed understates assets in one quiet line.
    """
    rule = "cap_threshold_gate"
    _sev(rule, Status.FAIL)
    policy = ctx.one(DOC_CAP_POLICY)
    if policy is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        threshold = require_cents(
            "capitalization_policy.threshold_cents", policy.get("threshold_cents")
        )
        excluded_raw = policy.get("excluded_categories")
        excluded = tuple(
            c for c in excluded_raw if isinstance(c, str)
        ) if isinstance(excluded_raw, list) else ()
        checked = 0
        for row in _rows(policy, "items"):
            item = _text(row, "item_id") or "?"
            with amount_guard(rule, out):
                cost = require_cents(f"expense_item[{item}].cost_cents", row.get("cost_cents"))
                category = _text(row, "category") or ""
                stated = bool(row.get("capitalized"))
                required = capitalization_required(cost, threshold, category, excluded)
                checked += 1
                if stated != required:
                    side = (
                        "must be capitalized under the policy"
                        if required
                        else "must be expensed under the policy"
                    )
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(policy, f"items/{item}/capitalized"),
                            f"item {item} costs {fmt(cost)} (threshold {fmt(threshold)}, "
                            f"category {category!r}) and {side}; it is recorded "
                            f"capitalized={stated}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} expense-log items sit on the correct side of the gate",
            )
        )
    return out


@check("cap_register_meets_threshold")
def check_cap_register_meets_threshold(ctx: Context) -> list[Finding]:
    """No capitalized asset on the register costs less than the threshold.

    The register is the capitalized side of the same gate: an asset below the
    threshold should never have been set up, and once it is, it draws a monthly
    charge and a reviewer's attention for its whole invented life.
    """
    rule = "cap_register_meets_threshold"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    policy = ctx.one(DOC_CAP_POLICY)
    if register is None or policy is None:
        return []
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        threshold = require_cents(
            "capitalization_policy.threshold_cents", policy.get("threshold_cents")
        )
        for row in _assets(ctx):
            with amount_guard(rule, out):
                cost = require_cents(
                    f"asset[{_asset_id(row)}].cost_cents", row.get("cost_cents")
                )
                checked += 1
                if cost < threshold:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"assets/{_asset_id(row)}/cost_cents"),
                            f"asset {_asset_id(row)} was capitalized at {fmt(cost)}, below "
                            f"the {fmt(threshold)} capitalization threshold; it belongs in "
                            f"expense, not on the register",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} capitalized assets meet the capitalization threshold",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# life_ -- the useful-life class mapping
# --------------------------------------------------------------------------- #
@check("life_class_known")
def check_life_class_known(ctx: Context) -> list[Finding]:
    """Every asset carries a class the useful-life table defines.

    The class is the key into the life table; an unknown one has no row, so
    nothing downstream could say what life the asset was required to use.
    """
    rule = "life_class_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    if register is None:
        return []
    table = _life_table(ctx)
    out: list[Finding] = []
    for row in _assets(ctx):
        cls = _text(row, "asset_class")
        if cls not in table:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"assets/{_asset_id(row)}/asset_class"),
                    f"asset {_asset_id(row)} is classed {cls!r}, which is not in the "
                    f"useful-life table; its required life cannot be looked up",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_assets(ctx))} assets carry a class the life table defines",
            )
        )
    return out


@check("life_matches_class")
def check_life_matches_class(ctx: Context) -> list[Finding]:
    """Every asset's useful life is the one its class prescribes.

    A fixed-life class (computers, furniture, automobiles) prescribes one life
    for every asset in it; leasehold improvements depreciate over the asset's
    own stated lease term. Either way the life is a lookup, not a judgment, and
    a register life that differs from the lookup rewrites every derived figure
    beneath it. Assets whose class is unknown are left to ``life_class_known``.
    """
    rule = "life_matches_class"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    if register is None:
        return []
    table = _life_table(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        cls = _text(row, "asset_class")
        table_row = table.get(cls or "")
        if table_row is None:
            continue  # life_class_known owns this
        life = _int(row, "useful_life_months")
        source = _text(table_row, "life_source")
        checked += 1
        if source == LIFE_SOURCE_LEASE_TERM:
            lease = _int(row, "lease_term_months")
            if lease is None or life != lease:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/useful_life_months"),
                        f"asset {_asset_id(row)} is a {cls} and must depreciate over its "
                        f"lease term of {lease} month(s); the register carries a life of "
                        f"{life} month(s)",
                    )
                )
        else:
            required = _int(table_row, "life_months")
            if life != required:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/useful_life_months"),
                        f"asset {_asset_id(row)} is classed {cls}, whose table life is "
                        f"{required} month(s); the register carries {life} month(s), so "
                        f"every derived figure beneath it is off-convention",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} asset lives match the class table's prescription",
            )
        )
    return out


@check("life_method_straight_line")
def check_life_method_straight_line(ctx: Context) -> list[Finding]:
    """Every asset and every class row states the straight-line method.

    Straight-line is the only method these books use; method is carried as a
    field so a tax-basis method could extend the model later, but until it does,
    any other value is a register keyed to arithmetic this engine has never
    agreed to re-derive.
    """
    rule = "life_method_straight_line"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    life_doc = ctx.one(DOC_LIFE_TABLE)
    if register is None or life_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        checked += 1
        if _text(row, "method") != METHOD_STRAIGHT_LINE:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"assets/{_asset_id(row)}/method"),
                    f"asset {_asset_id(row)} states method {_text(row, 'method')!r}; these "
                    f"books depreciate straight-line only, and a stated figure derived any "
                    f"other way cannot be re-derived by this engine's convention",
                )
            )
    for row in _rows(life_doc, "classes"):
        cls = _text(row, "asset_class") or "?"
        checked += 1
        if _text(row, "method") != METHOD_STRAIGHT_LINE:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(life_doc, f"classes/{cls}/method"),
                    f"class {cls} states method {_text(row, 'method')!r}; the class table "
                    f"prescribes straight-line for every class in these books",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} asset and class rows state the straight-line method",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# sl_ -- the straight-line re-derivation
# --------------------------------------------------------------------------- #
@check("sl_monthly_dep_rederives")
def check_sl_monthly_dep_rederives(ctx: Context) -> list[Finding]:
    """Each asset's stated monthly charge is exactly cost over life.

    The monthly charge is the seed of every other derived column, and it is the
    cell most often overtyped -- an extra digit here compounds into every month
    that follows. Compared with exact ``==`` in integer cents.
    """
    rule = "sl_monthly_dep_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            cost, life, _in_service = base
            stated = require_cents(
                f"asset[{_asset_id(row)}].monthly_dep_cents", row.get("monthly_dep_cents")
            )
            derived = monthly_dep_cents(cost, life)
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/monthly_dep_cents"),
                        f"asset {_asset_id(row)} states a monthly charge of {fmt(stated)}; "
                        f"cost {fmt(cost)} over {life} month(s) re-derives {fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} monthly depreciation charges re-derive from cost and life",
            )
        )
    return out


@check("sl_expense_rederives")
def check_sl_expense_rederives(ctx: Context) -> list[Finding]:
    """Each asset's stated charge for the close month is the schedule's charge.

    Zero before service, zero after the schedule completes, the base charge in
    between, and the base plus the rounding remainder in the final month -- so
    the schedule sums back to cost exactly. The stated expense is the number the
    recurring JE posts, which is why it is re-derived per asset rather than
    trusted in total.
    """
    rule = "sl_expense_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            cost, life, in_service = base
            stated = require_cents(
                f"asset[{_asset_id(row)}].depr_exp_cents", row.get("depr_exp_cents")
            )
            derived = depr_expense_cents(cost, life, in_service, close)
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/depr_exp_cents"),
                        f"asset {_asset_id(row)} states {fmt(stated)} of depreciation for "
                        f"{ctx.close_month}; the schedule re-derives {fmt(derived)} for "
                        f"that month",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} close-month depreciation charges re-derive from the schedule",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# date_ -- the in-service and end-of-depreciation date gates
# --------------------------------------------------------------------------- #
@check("date_end_depr_rederives")
def check_date_end_depr_rederives(ctx: Context) -> list[Finding]:
    """Each asset's stated end-of-depreciation month is in-service plus life.

    The end month is the date gate every later close reads to stop the charge;
    a stated end a month late is a month of depreciation charged against an
    asset already fully depreciated.
    """
    rule = "date_end_depr_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            _cost, life, in_service = base
            stated = _text(row, "end_depr_month")
            derived = month_str(end_depr_month(in_service, life))
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/end_depr_month"),
                        f"asset {_asset_id(row)} states end-of-depreciation {stated!r}; "
                        f"in service {row.get('in_service_month')} over {life} month(s) "
                        f"re-derives {derived}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} end-of-depreciation months re-derive from service date and life",
            )
        )
    return out


@check("date_fully_depreciated_zero")
def check_date_fully_depreciated_zero(ctx: Context) -> list[Finding]:
    """An asset past its end month carries full accumulation and nothing else.

    Once the close month passes the end of the schedule the asset is fully
    depreciated: accumulated equals cost, the month's charge is zero, and net
    book value is zero. An asset still carrying NBV past its end date is
    depreciation that silently stopped short -- or never stopped.
    """
    rule = "date_fully_depreciated_zero"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            cost, life, in_service = base
            if months_elapsed(in_service, close) <= life:
                continue  # in-life assets belong to the sl_/nbv_ controls
            accum = require_cents(
                f"asset[{_asset_id(row)}].accum_dep_cents", row.get("accum_dep_cents")
            )
            expense = require_cents(
                f"asset[{_asset_id(row)}].depr_exp_cents", row.get("depr_exp_cents")
            )
            nbv = require_cents(f"asset[{_asset_id(row)}].nbv_cents", row.get("nbv_cents"))
            checked += 1
            if accum != cost or expense != 0 or nbv != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/accum_dep_cents"),
                        f"asset {_asset_id(row)} completed its schedule in "
                        f"{month_str(end_depr_month(in_service, life))} yet states accum "
                        f"{fmt(accum)} against cost {fmt(cost)}, expense {fmt(expense)} and "
                        f"NBV {fmt(nbv)}; past the end month those must be cost, zero and zero",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} fully depreciated assets carry full accumulation and zero NBV",
            )
        )
    return out


@check("date_not_in_service_yet")
def check_date_not_in_service_yet(ctx: Context) -> list[Finding]:
    """An asset not yet in service carries no depreciation at all.

    Before the in-service month the schedule has not opened: months used is
    zero, accumulated is zero, the month's charge is zero and NBV is the full
    cost. Depreciation booked before service is expense invented ahead of the
    asset.
    """
    rule = "date_not_in_service_yet"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            cost, _life, in_service = base
            if months_elapsed(in_service, close) > 0:
                continue  # in-service assets belong to the sl_/nbv_ controls
            used = _int(row, "months_used")
            accum = require_cents(
                f"asset[{_asset_id(row)}].accum_dep_cents", row.get("accum_dep_cents")
            )
            expense = require_cents(
                f"asset[{_asset_id(row)}].depr_exp_cents", row.get("depr_exp_cents")
            )
            nbv = require_cents(f"asset[{_asset_id(row)}].nbv_cents", row.get("nbv_cents"))
            checked += 1
            if used != 0 or accum != 0 or expense != 0 or nbv != cost:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/in_service_month"),
                        f"asset {_asset_id(row)} enters service {row.get('in_service_month')}"
                        f", after the {ctx.close_month} close, yet states months_used "
                        f"{used}, accum {fmt(accum)}, expense {fmt(expense)} and NBV "
                        f"{fmt(nbv)}; before service those must be zero and NBV must be cost",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} not-yet-in-service assets carry no depreciation",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# nbv_ -- months-used cap, accumulated re-derivation, NBV identity
# --------------------------------------------------------------------------- #
@check("nbv_months_used_cap")
def check_nbv_months_used_cap(ctx: Context) -> list[Finding]:
    """Each asset's stated months-used is elapsed months capped at the life.

    Months used is the multiplier under the accumulated balance; a count past
    the life keeps depreciating a finished asset, and one behind the calendar
    understates every balance built on it.
    """
    rule = "nbv_months_used_cap"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            _cost, life, in_service = base
            stated = _int(row, "months_used")
            derived = months_used(in_service, close, life)
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/months_used"),
                        f"asset {_asset_id(row)} states {stated} month(s) used; in service "
                        f"{row.get('in_service_month')} through {ctx.close_month} with a "
                        f"{life}-month life re-derives min(elapsed, life) = {derived}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} months-used counts equal elapsed months capped at the life",
            )
        )
    return out


@check("nbv_accum_rederives")
def check_nbv_accum_rederives(ctx: Context) -> list[Finding]:
    """Each in-life asset's accumulated depreciation re-derives from the kernel.

    ``base x months used``, capped at cost -- the running balance the register
    exists to carry. Pre-service and fully-depreciated assets are owned by their
    date gates, so this control reads exactly the assets whose balance is still
    moving.
    """
    rule = "nbv_accum_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            cost, life, in_service = base
            elapsed = months_elapsed(in_service, close)
            if elapsed <= 0 or elapsed > life:
                continue  # date_not_in_service_yet / date_fully_depreciated_zero own those
            stated = require_cents(
                f"asset[{_asset_id(row)}].accum_dep_cents", row.get("accum_dep_cents")
            )
            derived = accum_dep_cents(cost, life, in_service, close)
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/accum_dep_cents"),
                        f"asset {_asset_id(row)} states accumulated depreciation of "
                        f"{fmt(stated)}; {months_used(in_service, close, life)} month(s) of "
                        f"the schedule re-derive {fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} in-life accumulated balances re-derive from the schedule",
            )
        )
    return out


@check("nbv_floor")
def check_nbv_floor(ctx: Context) -> list[Finding]:
    """NBV equals cost less accumulated, and accumulated never exceeds cost.

    The identity is universal -- it holds for every asset at every point of its
    life -- and it is the floor: accumulated capped at cost is exactly what
    keeps net book value from going negative. A register row that breaks it has
    stopped being a derivation at all.
    """
    rule = "nbv_floor"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ASSET_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            cost = require_cents(
                f"asset[{_asset_id(row)}].cost_cents", row.get("cost_cents")
            )
            accum = require_cents(
                f"asset[{_asset_id(row)}].accum_dep_cents", row.get("accum_dep_cents")
            )
            nbv = require_cents(f"asset[{_asset_id(row)}].nbv_cents", row.get("nbv_cents"))
            checked += 1
            if nbv != cost - accum or accum > cost or accum < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"assets/{_asset_id(row)}/nbv_cents"),
                        f"asset {_asset_id(row)} states cost {fmt(cost)}, accum "
                        f"{fmt(accum)} and NBV {fmt(nbv)}; NBV must equal cost less "
                        f"accumulated, and accumulated must stay within [0, cost]",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} NBV identities hold with accumulation inside [0, cost]",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# roll_ -- the balance roll-forwards
# --------------------------------------------------------------------------- #
@check("roll_accum_identity")
def check_roll_accum_identity(ctx: Context) -> list[Finding]:
    """The accumulated-depreciation roll-forward closes on itself.

    Opening plus the month's depreciation less what disposals removed equals
    closing -- the identity that makes accumulated depreciation a balance rather
    than a column someone re-foots. A roll-forward that does not close is a
    balance with an unexplained plug in it.
    """
    rule = "roll_accum_identity"
    _sev(rule, Status.FAIL)
    roll = ctx.one(DOC_ROLLFORWARD)
    if roll is None:
        return []
    section = roll.get("fixed_assets")
    if not isinstance(section, dict):
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(roll, "fixed_assets"),
                "the roll-forward schedule carries no fixed_assets section, so the "
                "accumulated-depreciation identity cannot be tested",
            )
        ]
    out: list[Finding] = []
    with amount_guard(rule, out):
        opening = require_cents(
            "rollforward.fixed_assets.opening_accum_cents",
            section.get("opening_accum_cents"),
        )
        depreciation = require_cents(
            "rollforward.fixed_assets.depreciation_cents", section.get("depreciation_cents")
        )
        removed = require_cents(
            "rollforward.fixed_assets.disposal_accum_removed_cents",
            section.get("disposal_accum_removed_cents"),
        )
        closing = require_cents(
            "rollforward.fixed_assets.closing_accum_cents",
            section.get("closing_accum_cents"),
        )
        if opening + depreciation - removed != closing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roll, "fixed_assets/closing_accum_cents"),
                    f"the accumulated-depreciation roll-forward does not close: opening "
                    f"{fmt(opening)} + depreciation {fmt(depreciation)} - disposals "
                    f"{fmt(removed)} = {fmt(opening + depreciation - removed)}, but closing "
                    f"is stated as {fmt(closing)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the accumulated-depreciation roll-forward closes at {fmt(closing)}",
                )
            )
    return out


@check("roll_closing_ties_register")
def check_roll_closing_ties_register(ctx: Context) -> list[Finding]:
    """The roll-forward's closing balance and charge tie the asset register.

    The roll-forward summarises the register; a closing balance or a
    depreciation total maintained beside it rather than derived from it drifts
    the first time a row is edited and nobody re-adds the column.
    """
    rule = "roll_closing_ties_register"
    _sev(rule, Status.FAIL)
    roll = ctx.one(DOC_ROLLFORWARD)
    register = ctx.one(DOC_ASSET_REGISTER)
    if roll is None or register is None:
        return []
    section = roll.get("fixed_assets")
    if not isinstance(section, dict):
        return []  # roll_accum_identity owns the missing section
    out: list[Finding] = []
    with amount_guard(rule, out):
        closing = require_cents(
            "rollforward.fixed_assets.closing_accum_cents",
            section.get("closing_accum_cents"),
        )
        depreciation = require_cents(
            "rollforward.fixed_assets.depreciation_cents", section.get("depreciation_cents")
        )
        register_accum = _sum_asset_column(ctx, "accum_dep_cents")
        register_exp = _sum_asset_column(ctx, "depr_exp_cents")
        if closing != register_accum:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roll, "fixed_assets/closing_accum_cents"),
                    f"the roll-forward closes accumulated depreciation at {fmt(closing)}; "
                    f"the asset register foots to {fmt(register_accum)} "
                    f"(variance {fmt(closing - register_accum)})",
                )
            )
        if depreciation != register_exp:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roll, "fixed_assets/depreciation_cents"),
                    f"the roll-forward carries {fmt(depreciation)} of depreciation for the "
                    f"month; the asset register foots to {fmt(register_exp)} "
                    f"(variance {fmt(depreciation - register_exp)})",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "the roll-forward's closing balance and monthly charge both foot the register",
            )
        )
    return out


@check("roll_prepaid_rollforward")
def check_roll_prepaid_rollforward(ctx: Context) -> list[Finding]:
    """The prepaid roll-forward closes on itself and foots the prepaid register.

    Opening plus additions less the month's amortization equals closing, and
    every figure in that identity foots the register it summarises -- opening to
    the beginning balances, amortization to the month's charges, closing to the
    ending balances.
    """
    rule = "roll_prepaid_rollforward"
    _sev(rule, Status.FAIL)
    roll = ctx.one(DOC_ROLLFORWARD)
    register = ctx.one(DOC_PREPAID_REGISTER)
    if roll is None or register is None:
        return []
    section = roll.get("prepaid")
    if not isinstance(section, dict):
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(roll, "prepaid"),
                "the roll-forward schedule carries no prepaid section, so the prepaid "
                "balance identity cannot be tested",
            )
        ]
    out: list[Finding] = []
    with amount_guard(rule, out):
        opening = require_cents("rollforward.prepaid.opening_cents", section.get("opening_cents"))
        additions = require_cents(
            "rollforward.prepaid.additions_cents", section.get("additions_cents")
        )
        amort = require_cents("rollforward.prepaid.amort_cents", section.get("amort_cents"))
        closing = require_cents("rollforward.prepaid.closing_cents", section.get("closing_cents"))
        beginning_sum = _sum_prepaid_column(ctx, "beginning_balance_cents")
        amort_sum = _sum_prepaid_column(ctx, "amort_this_period_cents")
        ending_sum = _sum_prepaid_column(ctx, "ending_balance_cents")
        if opening + additions - amort != closing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roll, "prepaid/closing_cents"),
                    f"the prepaid roll-forward does not close: opening {fmt(opening)} + "
                    f"additions {fmt(additions)} - amortization {fmt(amort)} = "
                    f"{fmt(opening + additions - amort)}, but closing is stated as "
                    f"{fmt(closing)}",
                )
            )
        if opening != beginning_sum:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roll, "prepaid/opening_cents"),
                    f"the prepaid roll-forward opens at {fmt(opening)}; the register's "
                    f"beginning balances foot to {fmt(beginning_sum)}",
                )
            )
        if amort != amort_sum:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roll, "prepaid/amort_cents"),
                    f"the prepaid roll-forward carries {fmt(amort)} of amortization; the "
                    f"register's monthly charges foot to {fmt(amort_sum)}",
                )
            )
        if closing != ending_sum:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roll, "prepaid/closing_cents"),
                    f"the prepaid roll-forward closes at {fmt(closing)}; the register's "
                    f"ending balances foot to {fmt(ending_sum)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "the prepaid roll-forward closes on itself and foots the prepaid register",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# pre_ -- the prepaid amortization waterfall
# --------------------------------------------------------------------------- #
@check("pre_window_valid")
def check_pre_window_valid(ctx: Context) -> list[Finding]:
    """Every prepaid item states a usable amortization window.

    The window is the whole derivation's frame: it must parse, run forward, and
    book from a month inside itself. An item with an unusable window has no
    schedule, so every figure it states is unanchored.
    """
    rule = "pre_window_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PREPAID_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _prepaids(ctx):
        item = _item_id(row)
        start = parse_month(row.get("window_start"))
        end = parse_month(row.get("window_end"))
        booked = parse_month(row.get("booked_from"))
        if start is None or end is None or booked is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"items/{item}/window_start"),
                    f"item {item} states window {row.get('window_start')!r} to "
                    f"{row.get('window_end')!r} booked from {row.get('booked_from')!r}; "
                    f"all three must be readable YYYY-MM months",
                )
            )
        elif start > end:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"items/{item}/window_end"),
                    f"item {item} states an amortization window from "
                    f"{row.get('window_start')} to {row.get('window_end')}; the window "
                    f"does not run forwards, so no schedule can be derived from it",
                )
            )
        elif booked < start or booked > end:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"items/{item}/booked_from"),
                    f"item {item} books from {row.get('booked_from')}, outside its own "
                    f"window {row.get('window_start')} to {row.get('window_end')}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_prepaids(ctx))} prepaid items state a usable amortization window",
            )
        )
    return out


@check("pre_monthly_amort_rederives")
def check_pre_monthly_amort_rederives(ctx: Context) -> list[Finding]:
    """Each item's stated monthly amortization is additions over the window.

    ``additions // periods`` -- the per-month straight-line of the term window,
    with the final period absorbing the remainder. Items with an unusable
    window are left to ``pre_window_valid``.
    """
    rule = "pre_monthly_amort_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PREPAID_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _prepaids(ctx):
        window = _prepaid_window(row)
        if window is None:
            continue  # pre_window_valid owns this
        start, end, _booked = window
        with amount_guard(rule, out):
            additions = require_cents(
                f"prepaid[{_item_id(row)}].additions_cents", row.get("additions_cents")
            )
            stated = require_cents(
                f"prepaid[{_item_id(row)}].monthly_amort_cents",
                row.get("monthly_amort_cents"),
            )
            periods = window_periods(start, end)
            derived = monthly_amort_cents(additions, periods)
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"items/{_item_id(row)}/monthly_amort_cents"),
                        f"item {_item_id(row)} states monthly amortization of {fmt(stated)}; "
                        f"additions {fmt(additions)} over the {periods}-period window "
                        f"re-derive {fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} monthly amortization figures re-derive from the window",
            )
        )
    return out


@check("pre_expense_rederives")
def check_pre_expense_rederives(ctx: Context) -> list[Finding]:
    """Each item's stated charge for the close month is the waterfall's charge.

    Date-gated to the window, with the first booked month taking the catch-up
    for the periods the item sat unbooked and the final period absorbing the
    rounding remainder. This is the figure the recurring JE posts, so it is
    re-derived per item rather than trusted in total.
    """
    rule = "pre_expense_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PREPAID_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _prepaids(ctx):
        window = _prepaid_window(row)
        if window is None:
            continue  # pre_window_valid owns this
        start, end, booked = window
        with amount_guard(rule, out):
            additions = require_cents(
                f"prepaid[{_item_id(row)}].additions_cents", row.get("additions_cents")
            )
            stated = require_cents(
                f"prepaid[{_item_id(row)}].amort_this_period_cents",
                row.get("amort_this_period_cents"),
            )
            derived = amort_expense_cents(additions, start, end, booked, close)
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"items/{_item_id(row)}/amort_this_period_cents"),
                        f"item {_item_id(row)} states {fmt(stated)} of amortization for "
                        f"{ctx.close_month}; the window {row.get('window_start')} to "
                        f"{row.get('window_end')} booked from {row.get('booked_from')} "
                        f"re-derives {fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} close-month amortization charges re-derive from the waterfall",
            )
        )
    return out


@check("pre_ending_balance_rederives")
def check_pre_ending_balance_rederives(ctx: Context) -> list[Finding]:
    """Each item's beginning and ending balances re-derive from the schedule.

    Additions less cumulative booked amortization, at the month's opening and
    at its close. The ending balance is what the GL prepaid account carries, so
    a balance that does not re-derive is a balance nobody can support.
    """
    rule = "pre_ending_balance_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PREPAID_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _prepaids(ctx):
        window = _prepaid_window(row)
        if window is None:
            continue  # pre_window_valid owns this
        start, end, booked = window
        with amount_guard(rule, out):
            additions = require_cents(
                f"prepaid[{_item_id(row)}].additions_cents", row.get("additions_cents")
            )
            stated_begin = require_cents(
                f"prepaid[{_item_id(row)}].beginning_balance_cents",
                row.get("beginning_balance_cents"),
            )
            stated_end = require_cents(
                f"prepaid[{_item_id(row)}].ending_balance_cents",
                row.get("ending_balance_cents"),
            )
            derived_begin = prepaid_beginning_cents(additions, start, end, booked, close)
            derived_end = prepaid_ending_cents(additions, start, end, booked, close)
            checked += 1
            if stated_begin != derived_begin or stated_end != derived_end:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"items/{_item_id(row)}/ending_balance_cents"),
                        f"item {_item_id(row)} states balances {fmt(stated_begin)} opening "
                        f"and {fmt(stated_end)} closing for {ctx.close_month}; the schedule "
                        f"re-derives {fmt(derived_begin)} and {fmt(derived_end)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} prepaid balances re-derive from the amortization schedule",
            )
        )
    return out


@check("pre_window_ending_watch")
def check_pre_window_ending_watch(ctx: Context) -> list[Finding]:
    """A prepaid window ending inside the look-ahead watch is flagged.

    Deliberately a FLAG, not a failure: the schedule is running exactly as
    stated, but the term it amortizes -- a policy, a licence, a subscription --
    is about to end, and the renewal (or the decision not to renew) needs a
    human before next close. The look-ahead comes from the file's own
    ``prepaid_watch_months``.
    """
    rule = "pre_window_ending_watch"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_PREPAID_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    watch = ctx.prepaid_watch_months
    out: list[Finding] = []
    checked = 0
    for row in _prepaids(ctx):
        window = _prepaid_window(row)
        if window is None:
            continue  # pre_window_valid owns this
        _start, end, _booked = window
        checked += 1
        if window_ending_soon(end, close, watch):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"items/{_item_id(row)}/window_end"),
                    f"item {_item_id(row)} amortizes through {row.get('window_end')}, "
                    f"within {watch} month(s) of the {ctx.close_month} close; the "
                    f"underlying term is ending and its renewal needs a decision",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} prepaid windows run beyond the look-ahead watch",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# disp_ -- disposal roll-off
# --------------------------------------------------------------------------- #
@check("disp_not_on_register")
def check_disp_not_on_register(ctx: Context) -> list[Finding]:
    """No disposed asset still sits on the fixed-asset register.

    Disposal removes the asset's cost and accumulation from the register and
    stops its depreciation. An asset on both registers at once is being
    depreciated and written off simultaneously -- its cost is counted twice and
    its expense keeps running after the asset is gone.
    """
    rule = "disp_not_on_register"
    _sev(rule, Status.FAIL)
    disposal_doc = ctx.one(DOC_DISPOSAL_REGISTER)
    register = ctx.one(DOC_ASSET_REGISTER)
    if disposal_doc is None or register is None:
        return []
    active = {_asset_id(row) for row in _assets(ctx)}
    out: list[Finding] = []
    for row in _disposals(ctx):
        asset = _asset_id(row)
        if asset in active:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"assets/{asset}"),
                    f"asset {asset} appears on the disposal register (disposed "
                    f"{row.get('disposal_month')}) and is still on the fixed-asset "
                    f"register; depreciation must stop at disposal and the cost must "
                    f"roll off",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_disposals(ctx))} disposed assets are off the fixed-asset register",
            )
        )
    return out


@check("disp_gain_loss_rederives")
def check_disp_gain_loss_rederives(ctx: Context) -> list[Finding]:
    """Each disposal's write-off is exactly the net book value it removed.

    Cost less accumulated at disposal is the remaining NBV, and that is the
    whole of the gain/loss on an abandonment write-off. A write-off that
    differs is a plug; and accumulation beyond cost on the way out is the same
    impossibility it would be on the register.
    """
    rule = "disp_gain_loss_rederives"
    _sev(rule, Status.FAIL)
    disposal_doc = ctx.one(DOC_DISPOSAL_REGISTER)
    if disposal_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _disposals(ctx):
        asset = _asset_id(row)
        with amount_guard(rule, out):
            cost = require_cents(f"disposal[{asset}].cost_cents", row.get("cost_cents"))
            accum = require_cents(
                f"disposal[{asset}].accum_at_disposal_cents",
                row.get("accum_at_disposal_cents"),
            )
            writeoff = require_cents(
                f"disposal[{asset}].writeoff_cents", row.get("writeoff_cents")
            )
            checked += 1
            if writeoff != cost - accum or accum > cost or accum < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(disposal_doc, f"disposals/{asset}/writeoff_cents"),
                        f"disposal of asset {asset} states a write-off of {fmt(writeoff)}; "
                        f"cost {fmt(cost)} less accumulated {fmt(accum)} re-derives "
                        f"{fmt(cost - accum)}, and accumulation must stay within [0, cost]",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} disposal write-offs equal the net book value removed",
            )
        )
    return out


@check("disp_fully_depreciated_watch")
def check_disp_fully_depreciated_watch(ctx: Context) -> list[Finding]:
    """An asset long past its end month, still on the register, is flagged.

    Deliberately a FLAG, not a failure: a fully depreciated asset carried at
    zero NBV is arithmetically clean, but one sitting more than the
    disposal-review band past its end month is almost certainly gone from the
    building and should be reviewed for disposal, so the register keeps
    describing assets that exist.
    """
    rule = "disp_fully_depreciated_watch"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_ASSET_REGISTER)
    close = _close(ctx)
    if register is None or close is None:
        return []
    review = ctx.disposal_review_months
    out: list[Finding] = []
    checked = 0
    for row in _assets(ctx):
        with amount_guard(rule, out):
            base = _asset_base(row)
            if base is None:
                continue
            _cost, life, in_service = base
            end = end_depr_month(in_service, life)
            checked += 1
            if past_disposal_review(end, close, review):
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"assets/{_asset_id(row)}/end_depr_month"),
                        f"asset {_asset_id(row)} completed its schedule in {month_str(end)}, "
                        f"more than {review} month(s) before the {ctx.close_month} close, "
                        f"and is still on the register; it is due for disposal review",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} register assets are inside the disposal-review band",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# gl_ -- the register-to-GL control-account tie-out
# --------------------------------------------------------------------------- #
def _gl_tie(ctx: Context, rule: str, account: str, label: str, register_total: int) -> list[Finding]:
    """Compare one GL control-account balance to a register footing."""
    gl_doc = ctx.one(DOC_GL_BALANCES)
    assert gl_doc is not None
    row = _gl_account(ctx, account)
    if row is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(gl_doc, f"accounts/{account}"),
                f"GL control account {account} ({label}) is not in the balance listing; "
                f"the register total has nothing to tie to",
            )
        ]
    out: list[Finding] = []
    with amount_guard(rule, out):
        balance = require_cents(f"gl[{account}].balance_cents", row.get("balance_cents"))
        if balance != register_total:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl_doc, f"accounts/{account}/balance_cents"),
                    f"GL account {account} ({label}) carries {fmt(balance)}; the register "
                    f"foots to {fmt(register_total)} "
                    f"(variance {fmt(balance - register_total)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"GL account {account} ({label}) ties the register at {fmt(balance)}",
                )
            )
    return out


@check("gl_cost_ties")
def check_gl_cost_ties(ctx: Context) -> list[Finding]:
    """The fixed-asset cost control account ties the register's cost footing.

    The register is the subledger of the cost account; a control balance that
    differs means an asset was booked to one and not the other, and every NBV
    built on the register is reconciling to a different population than the GL.
    """
    rule = "gl_cost_ties"
    _sev(rule, Status.FAIL)
    if ctx.one(DOC_GL_BALANCES) is None or ctx.one(DOC_ASSET_REGISTER) is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = _sum_asset_column(ctx, "cost_cents")
        out.extend(_gl_tie(ctx, rule, GL_COST, "fixed assets at cost", total))
    return out


@check("gl_accum_ties")
def check_gl_accum_ties(ctx: Context) -> list[Finding]:
    """The accumulated-depreciation control account ties the register footing.

    Accumulated depreciation is the register's running product; the control
    account that differs from it is carrying depreciation nobody can trace to
    an asset, or missing depreciation an asset has already taken.
    """
    rule = "gl_accum_ties"
    _sev(rule, Status.FAIL)
    if ctx.one(DOC_GL_BALANCES) is None or ctx.one(DOC_ASSET_REGISTER) is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = _sum_asset_column(ctx, "accum_dep_cents")
        out.extend(_gl_tie(ctx, rule, GL_ACCUM, "accumulated depreciation", total))
    return out


@check("gl_prepaid_ties")
def check_gl_prepaid_ties(ctx: Context) -> list[Finding]:
    """The prepaid control account ties the prepaid register's ending balances.

    The prepaid schedule exists to support the balance-sheet line; an account
    balance that does not foot to the schedule's ending balances is a prepaid
    asset with no schedule behind part of it.
    """
    rule = "gl_prepaid_ties"
    _sev(rule, Status.FAIL)
    if ctx.one(DOC_GL_BALANCES) is None or ctx.one(DOC_PREPAID_REGISTER) is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = _sum_prepaid_column(ctx, "ending_balance_cents")
        out.extend(_gl_tie(ctx, rule, GL_PREPAID, "prepaid expenses", total))
    return out


# --------------------------------------------------------------------------- #
# je_ -- the register-total to recurring-JE tie-out
# --------------------------------------------------------------------------- #
def _je_tie(ctx: Context, rule: str, line_id: str, label: str, register_total: int) -> list[Finding]:
    """Compare one recurring-JE line amount to a register footing."""
    je_doc = ctx.one(DOC_RECURRING_JE)
    assert je_doc is not None
    line = _je_line(ctx, line_id)
    if line is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(je_doc, f"lines/{line_id}"),
                f"recurring-JE line {line_id} ({label}) was not posted; the register "
                f"total has no journal entry to tie to",
            )
        ]
    out: list[Finding] = []
    with amount_guard(rule, out):
        amount = require_cents(f"je[{line_id}].amount_cents", line.get("amount_cents"))
        if amount != register_total:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(je_doc, f"lines/{line_id}/amount_cents"),
                    f"recurring-JE line {line_id} ({label}) posted {fmt(amount)}; the "
                    f"register foots to {fmt(register_total)} "
                    f"(variance {fmt(amount - register_total)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"recurring-JE line {line_id} ({label}) ties the register at {fmt(amount)}",
                )
            )
    return out


@check("je_depreciation_ties")
def check_je_depreciation_ties(ctx: Context) -> list[Finding]:
    """The posted depreciation JE equals the register's total monthly charge.

    The recurring entry is the only way the register's arithmetic reaches the
    GL; a posted amount that differs from the register total is a month of
    depreciation the books took on a number nobody derived.
    """
    rule = "je_depreciation_ties"
    _sev(rule, Status.FAIL)
    if ctx.one(DOC_RECURRING_JE) is None or ctx.one(DOC_ASSET_REGISTER) is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = _sum_asset_column(ctx, "depr_exp_cents")
        out.extend(_je_tie(ctx, rule, JE_DEPRECIATION, "monthly depreciation", total))
    return out


@check("je_prepaid_amort_ties")
def check_je_prepaid_amort_ties(ctx: Context) -> list[Finding]:
    """The posted amortization JE equals the prepaid register's monthly total.

    Same contract as depreciation: the JE is posted *from* the schedule, so the
    schedule total is the only defensible amount. A variance here is the drift
    between what was amortized and what was booked.
    """
    rule = "je_prepaid_amort_ties"
    _sev(rule, Status.FAIL)
    if ctx.one(DOC_RECURRING_JE) is None or ctx.one(DOC_PREPAID_REGISTER) is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = _sum_prepaid_column(ctx, "amort_this_period_cents")
        out.extend(_je_tie(ctx, rule, JE_AMORTIZATION, "prepaid amortization", total))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one close file."""
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
    """Analyze every ``.json`` close file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of close-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
