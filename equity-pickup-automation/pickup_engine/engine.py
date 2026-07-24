"""
Equity-method pickup & eliminations control engine (READ-ONLY).
===============================================================

Loads each consolidation file (a ``.json`` file produced by
:mod:`pickup_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the equity-method arithmetic re-derives and the
eliminations extinguish**, not what an investment is worth. Impairment and
fair value are judgment questions owned by a valuation workpaper, and that
workpaper does not re-foot a roll-forward. This engine is that re-foot.

The shape of the problem
------------------------
A parent holds interests in subsidiaries and joint ventures, and every period
three things must stay true at once: the pickup it books must equal its
ownership share of each sub's net income; the investment carrying value must
roll forward as begin + contributions + pickup - distributions = end; and on
consolidation every Investment account must be paired against the sub's
Equity-Parent account and net to zero. Around those sit the feeding schedules:
a preferred-return accrual built on a day count, and a member allocation that
must sum back to the income it splits and tie to the trial balance.

The registry is organised around that:

1. ``set_``   -- is the consolidation file complete?
2. ``rf_``    -- does every investment roll-forward foot, cover every holding,
   and carry the ownership share of distributions?
3. ``epu_``   -- does the pickup recompute from ownership x sub net income,
   with cost-method holdings booking none, ownership within bounds, and every
   reference resolvable?
4. ``elim_``  -- does every elimination block balance, pair investment to
   sub equity, extinguish the carrying value, and follow the account link-key
   convention?
5. ``pref_``  -- does the preferred-return schedule re-derive its day counts,
   accruals, capital chain and period continuity?
6. ``alloc_`` -- do the member allocations foot and tie to net income, and do
   the roll-forward and pickup figures tie to the trial balance?

Design notes
------------
- **Strictly read-only.** Consolidation files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every equality is exact ``==``.
- **One pickup arithmetic.** Controls and the generator share the kernel in
  :mod:`pickup_engine.pickup`, so a determination cannot disagree with the
  data that produced it.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.
"""

from __future__ import annotations

import contextlib
import functools
import json
import re
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .model import (
    DOC_ALLOCATION_SUMMARY,
    DOC_ELIMINATION_SCHEDULE,
    DOC_ENTITY_REGISTER,
    DOC_HOLDING_REGISTER,
    DOC_INVESTMENT_ROLLFORWARD,
    DOC_PREFERRED_RETURN,
    DOC_SUB_RESULTS,
    DOC_TRIAL_BALANCE,
    DOC_TYPES,
    DEFAULT_DAY_BASIS,
    METHOD_COST,
    METHOD_EQUITY,
    METHODS,
    ROLE_PARENT,
    ROLE_SUBSIDIARY,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, BPS_FULL, fmt, require_cents
from .pickup import (
    allocate_shares,
    inclusive_days,
    preferred_accrual,
    rollforward_end,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~pickup_engine.money.AmountInvalidError` as a finding."""
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


# --------------------------------------------------------------------------- #
# Consolidation-file helpers
# --------------------------------------------------------------------------- #
def _entities(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ENTITY_REGISTER), "entities")


def _entity_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _entities(ctx):
        eid = _text(row, "entity_id")
        if eid and eid not in out:
            out[eid] = row
    return out


def _subsidiaries(ctx: Context) -> list[dict[str, Any]]:
    return [e for e in _entities(ctx) if _text(e, "role") == ROLE_SUBSIDIARY]


def _holdings(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_HOLDING_REGISTER), "holdings")


def _holding_id(row: dict[str, Any]) -> str:
    value = row.get("holding_id")
    return value if isinstance(value, str) and value else "?"


def _holding_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _holdings(ctx):
        hid = _holding_id(row)
        if hid != "?" and hid not in out:
            out[hid] = row
    return out


def _results(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SUB_RESULTS), "results")


def _result_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _results(ctx):
        sid = _text(row, "sub_id")
        if sid and sid not in out:
            out[sid] = row
    return out


def _rf_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_INVESTMENT_ROLLFORWARD), "rows")


def _rf_by_holding(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rf_rows(ctx):
        hid = _text(row, "holding_id")
        if hid and hid not in out:
            out[hid] = row
    return out


def _blocks(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ELIMINATION_SCHEDULE), "blocks")


def _block_id(row: dict[str, Any]) -> str:
    value = row.get("block_id")
    return value if isinstance(value, str) and value else "?"


def _block_by_holding(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for block in _blocks(ctx):
        hid = _text(block, "holding_id")
        if hid and hid not in out:
            out[hid] = block
    return out


def _schedules(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PREFERRED_RETURN), "schedules")


def _entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ALLOCATION_SUMMARY), "entries")


def _tb_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TRIAL_BALANCE), "rows")


def _tb_row(ctx: Context, entity_id: str, account: str) -> dict[str, Any] | None:
    for row in _tb_rows(ctx):
        if _text(row, "entity_id") == entity_id and _text(row, "account") == account:
            return row
    return None


def _equity_holdings_of(ctx: Context, sub_id: str) -> list[dict[str, Any]]:
    """Equity-method holdings of one sub, in stable holding-id order.

    The order is load-bearing: :func:`~pickup_engine.pickup.allocate_shares`
    assigns the residual cent to the final holder, so both the generator and
    every control must walk the holders the same way.
    """
    held = [
        h
        for h in _holdings(ctx)
        if _text(h, "sub_id") == sub_id and _text(h, "method") == METHOD_EQUITY
    ]
    held.sort(key=_holding_id)
    return held


def equity_holder_shares(ctx: Context, sub_id: str, amount_cents: int) -> dict[str, int]:
    """Each equity holder's share of an amount of one sub, by holding id.

    Shared with the generator, so the share the engine re-derives is the share
    that produced the data. Raises :class:`AmountInvalidError` if any holder's
    ownership is not integer basis points; the calling control contains that.
    """
    holders = _equity_holdings_of(ctx, sub_id)
    bps = [
        require_cents(
            f"holding[{_holding_id(h)}].ownership_bps",
            h.get("ownership_bps"),
            unit="integer basis points",
        )
        for h in holders
    ]
    shares = allocate_shares(amount_cents, bps)
    return {_holding_id(h): share for h, share in zip(holders, shares)}


def expected_pickup(ctx: Context, holding: dict[str, Any]) -> int | None:
    """Re-derive the pickup one equity holding should have booked, or ``None``.

    ``None`` when the sub's result row is absent (a membership control owns
    that) or the holding is not equity-method. Shared with the generator
    through the kernel split in :func:`equity_holder_shares`.
    """
    if _text(holding, "method") != METHOD_EQUITY:
        return None
    sub_id = _text(holding, "sub_id")
    result = _result_map(ctx).get(sub_id or "")
    if result is None:
        return None
    net_income = require_cents(
        f"sub_results[{sub_id}].net_income_cents", result.get("net_income_cents")
    )
    return equity_holder_shares(ctx, sub_id or "", net_income)[_holding_id(holding)]


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the consolidation file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the consolidation file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} consolidation artifacts are present",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rf_ -- the investment roll-forward
# --------------------------------------------------------------------------- #
@check("rf_identity")
def check_rf_identity(ctx: Context) -> list[Finding]:
    """Every roll-forward row foots: begin + contributions + pickup -
    distributions = end.

    This is the closure identity of the whole workpaper. A row that does not
    foot means the carrying value the trial balance shows was not produced by
    the activity the schedule claims produced it.
    """
    rule = "rf_identity"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_INVESTMENT_ROLLFORWARD)
    if rollforward is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rf_rows(ctx):
        hid = _text(row, "holding_id") or "?"
        with amount_guard(rule, out):
            begin = require_cents(f"rollforward[{hid}].begin_cents", row.get("begin_cents"))
            contributions = require_cents(
                f"rollforward[{hid}].contributions_cents", row.get("contributions_cents")
            )
            pickup = require_cents(f"rollforward[{hid}].pickup_cents", row.get("pickup_cents"))
            distributions = require_cents(
                f"rollforward[{hid}].distributions_cents", row.get("distributions_cents")
            )
            end = require_cents(f"rollforward[{hid}].end_cents", row.get("end_cents"))
            checked += 1
            derived = rollforward_end(begin, contributions, pickup, distributions)
            if end != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollforward, f"rows/{hid}/end_cents"),
                        f"holding {hid} states end {fmt(end)}; begin {fmt(begin)} + "
                        f"contributions {fmt(contributions)} + pickup {fmt(pickup)} - "
                        f"distributions {fmt(distributions)} re-derives {fmt(derived)} "
                        f"(off by {fmt(end - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} roll-forward rows foot exactly")
        )
    return out


@check("rf_row_has_holding")
def check_rf_row_has_holding(ctx: Context) -> list[Finding]:
    """Every roll-forward row names a holding in the register.

    A roll-forward row with no holding is a carrying value moving for an
    interest nobody has declared owning.
    """
    rule = "rf_row_has_holding"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_INVESTMENT_ROLLFORWARD)
    if rollforward is None:
        return []
    holdings = _holding_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(rollforward, f"rows/{_text(row, 'holding_id')}/holding_id"),
            f"roll-forward row names holding {_text(row, 'holding_id')!r}, which is not "
            f"in the holding register; its carrying value belongs to nobody",
        )
        for row in _rf_rows(ctx)
        if _text(row, "holding_id") and _text(row, "holding_id") not in holdings
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every roll-forward row names a registered holding"
            )
        )
    return out


@check("rf_coverage_complete")
def check_rf_coverage_complete(ctx: Context) -> list[Finding]:
    """Every holding has exactly one roll-forward row.

    A holding with no row is an investment whose period activity was never
    scheduled; two rows make its carrying value ambiguous. Either way the
    downstream ties have nothing sound to read.
    """
    rule = "rf_coverage_complete"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_INVESTMENT_ROLLFORWARD)
    register = ctx.one(DOC_HOLDING_REGISTER)
    if rollforward is None or register is None:
        return []
    counts: dict[str, int] = {}
    for row in _rf_rows(ctx):
        hid = _text(row, "holding_id")
        if hid:
            counts[hid] = counts.get(hid, 0) + 1
    out: list[Finding] = []
    for holding in _holdings(ctx):
        hid = _holding_id(holding)
        n = counts.get(hid, 0)
        if n != 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollforward, f"rows/{hid}"),
                    f"holding {hid} has {n} roll-forward row(s); every holding carries "
                    f"exactly one, or its carrying value cannot be tied",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_holdings(ctx))} holdings have exactly one roll-forward row",
            )
        )
    return out


@check("rf_distributions_rederive")
def check_rf_distributions_rederive(ctx: Context) -> list[Finding]:
    """Each equity holding's distributions equal its share of the sub's declared
    distributions.

    The sub declares one distribution; each holder's slice of it is ownership
    math, not an entry someone types. A slice that does not recompute means
    cash left the sub in a proportion nobody's ownership produces.
    """
    rule = "rf_distributions_rederive"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_INVESTMENT_ROLLFORWARD)
    if rollforward is None:
        return []
    rf = _rf_by_holding(ctx)
    results = _result_map(ctx)
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        if _text(holding, "method") != METHOD_EQUITY:
            continue  # epu_cost_no_pickup owns the cost side
        hid = _holding_id(holding)
        row = rf.get(hid)
        if row is None:
            continue  # rf_coverage_complete owns this
        sub_id = _text(holding, "sub_id")
        result = results.get(sub_id or "")
        if result is None:
            continue  # epu_refs_resolve owns this
        with amount_guard(rule, out):
            declared = require_cents(
                f"sub_results[{sub_id}].distributions_declared_cents",
                result.get("distributions_declared_cents"),
            )
            stated = require_cents(
                f"rollforward[{hid}].distributions_cents", row.get("distributions_cents")
            )
            derived = equity_holder_shares(ctx, sub_id or "", declared)[hid]
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollforward, f"rows/{hid}/distributions_cents"),
                        f"holding {hid} states distributions {fmt(stated)}; its ownership "
                        f"share of the {fmt(declared)} the sub declared re-derives "
                        f"{fmt(derived)} (off by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} equity-holding distribution shares re-derive exactly",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# epu_ -- the pickup re-derivation
# --------------------------------------------------------------------------- #
@check("epu_pickup_rederives")
def check_epu_pickup_rederives(ctx: Context) -> list[Finding]:
    """Each equity holding's pickup equals its ownership share of the sub's net
    income.

    This is the control the engine exists for. The pickup is a *determination*,
    and a determination that is not recomputed from the ownership percentage
    and the sub's result is an assertion. The engine rebuilds every pickup
    through the shared kernel -- residual cent to the final holder -- and
    compares exactly.
    """
    rule = "epu_pickup_rederives"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_INVESTMENT_ROLLFORWARD)
    if rollforward is None:
        return []
    rf = _rf_by_holding(ctx)
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        if _text(holding, "method") != METHOD_EQUITY:
            continue  # epu_cost_no_pickup owns the cost side
        hid = _holding_id(holding)
        row = rf.get(hid)
        if row is None:
            continue  # rf_coverage_complete owns this
        with amount_guard(rule, out):
            derived = expected_pickup(ctx, holding)
            if derived is None:
                continue  # epu_refs_resolve owns the missing result row
            stated = require_cents(
                f"rollforward[{hid}].pickup_cents", row.get("pickup_cents")
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollforward, f"rows/{hid}/pickup_cents"),
                        f"holding {hid} books pickup {fmt(stated)}; ownership x sub net "
                        f"income re-derives {fmt(derived)} "
                        f"(off by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} equity pickups re-derive exactly")
        )
    return out


@check("epu_cost_no_pickup")
def check_epu_cost_no_pickup(ctx: Context) -> list[Finding]:
    """A cost-method holding books no pickup and no distribution against the
    investment.

    Cost-vs-equity is configured per holding because real books are not
    uniform. Under cost the carrying value moves only by contributions; a
    pickup routed into a cost holding is equity accounting wearing a cost
    label, and the two methods produce different balance sheets.
    """
    rule = "epu_cost_no_pickup"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_INVESTMENT_ROLLFORWARD)
    if rollforward is None:
        return []
    rf = _rf_by_holding(ctx)
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        if _text(holding, "method") != METHOD_COST:
            continue
        hid = _holding_id(holding)
        row = rf.get(hid)
        if row is None:
            continue  # rf_coverage_complete owns this
        with amount_guard(rule, out):
            pickup = require_cents(f"rollforward[{hid}].pickup_cents", row.get("pickup_cents"))
            distributions = require_cents(
                f"rollforward[{hid}].distributions_cents", row.get("distributions_cents")
            )
            checked += 1
            if pickup != 0 or distributions != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollforward, f"rows/{hid}/pickup_cents"),
                        f"holding {hid} is carried at cost yet rolls pickup {fmt(pickup)} "
                        f"and distributions {fmt(distributions)} through the investment; "
                        f"a cost-method carrying value moves only by contributions",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} cost-method holdings roll no pickup or distributions",
            )
        )
    return out


@check("epu_ownership_bounds")
def check_epu_ownership_bounds(ctx: Context) -> list[Finding]:
    """Ownership is positive, at most 100.00%, and never over-allocated per sub.

    A holding of 0 bps owns nothing and books nothing; over 10000 bps -- on one
    holding or summed across a sub's holders -- allocates more than the whole
    of an income that only has a whole.
    """
    rule = "epu_ownership_bounds"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_HOLDING_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    totals: dict[str, int] = {}
    for holding in _holdings(ctx):
        hid = _holding_id(holding)
        with amount_guard(rule, out):
            bps = require_cents(
                f"holding[{hid}].ownership_bps",
                holding.get("ownership_bps"),
                unit="integer basis points",
            )
            if not 0 < bps <= BPS_FULL:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"holdings/{hid}/ownership_bps"),
                        f"holding {hid} states ownership {bps} bps; a holding owns more "
                        f"than 0 and at most {BPS_FULL} bps of its sub",
                    )
                )
            sub_id = _text(holding, "sub_id")
            if sub_id:
                totals[sub_id] = totals.get(sub_id, 0) + bps
    for sub_id, total_bps in sorted(totals.items()):
        if total_bps > BPS_FULL:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{sub_id}/ownership_bps"),
                    f"the holders of {sub_id} claim {total_bps} bps between them; a sub "
                    f"has exactly {BPS_FULL} bps to give",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_holdings(ctx))} ownership percentages are in bounds",
            )
        )
    return out


@check("epu_refs_resolve")
def check_epu_refs_resolve(ctx: Context) -> list[Finding]:
    """Every holding resolves: a registered parent, a registered sub with a
    result row, and a known method.

    The holding register is the join table of the whole workpaper. A reference
    that does not resolve leaves the pickup, the elimination and the trial-
    balance tie all silently unrunnable for that interest.
    """
    rule = "epu_refs_resolve"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_HOLDING_REGISTER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    results = _result_map(ctx)
    out: list[Finding] = []
    for holding in _holdings(ctx):
        hid = _holding_id(holding)
        parent = entities.get(_text(holding, "parent_id") or "")
        sub = entities.get(_text(holding, "sub_id") or "")
        if parent is None or _text(parent, "role") != ROLE_PARENT:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{hid}/parent_id"),
                    f"holding {hid} names parent {_text(holding, 'parent_id')!r}, which is "
                    f"not a registered parent entity",
                )
            )
        if sub is None or _text(sub, "role") != ROLE_SUBSIDIARY:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{hid}/sub_id"),
                    f"holding {hid} names sub {_text(holding, 'sub_id')!r}, which is not a "
                    f"registered subsidiary entity",
                )
            )
        elif _text(holding, "sub_id") not in results:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{hid}/sub_id"),
                    f"holding {hid}'s sub {_text(holding, 'sub_id')} has no sub_results "
                    f"row; there is no income to pick up a share of",
                )
            )
        if _text(holding, "method") not in METHODS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{hid}/method"),
                    f"holding {hid} is carried under method {_text(holding, 'method')!r}, "
                    f"which is not one of {METHODS}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_holdings(ctx))} holdings resolve to registered entities, a "
                f"result row and a known method",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# elim_ -- consolidation eliminations
# --------------------------------------------------------------------------- #
@check("elim_block_balances")
def check_elim_block_balances(ctx: Context) -> list[Finding]:
    """Every elimination block self-balances: debits equal credits.

    An unbalanced elimination is not an elimination; it is a one-sided entry
    that moves the consolidated totals while claiming to cancel something.
    """
    rule = "elim_block_balances"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ELIMINATION_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for block in _blocks(ctx):
        bid = _block_id(block)
        with amount_guard(rule, out):
            debits = 0
            credits = 0
            for i, line in enumerate(_rows(block, "lines")):
                debits += require_cents(
                    f"elimination[{bid}].lines[{i}].debit_cents", line.get("debit_cents")
                )
                credits += require_cents(
                    f"elimination[{bid}].lines[{i}].credit_cents", line.get("credit_cents")
                )
            checked += 1
            if debits != credits:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"blocks/{bid}"),
                        f"block {bid} debits {fmt(debits)} against credits {fmt(credits)} "
                        f"(off by {fmt(debits - credits)}); an elimination that does not "
                        f"balance moves the consolidated totals",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} elimination blocks self-balance")
        )
    return out


@check("elim_pairing_complete")
def check_elim_pairing_complete(ctx: Context) -> list[Finding]:
    """Every equity holding is paired: a block that debits the sub's
    Equity-Parent account and credits the parent's Investment account.

    Pairing completeness is what makes consolidation net to zero entity block
    by entity block. An unpaired holding leaves both the investment and the
    sub's equity standing in the consolidated totals, double-counting the same
    net assets.
    """
    rule = "elim_pairing_complete"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ELIMINATION_SCHEDULE)
    register = ctx.one(DOC_HOLDING_REGISTER)
    if schedule is None or register is None:
        return []
    by_holding = _block_by_holding(ctx)
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        if _text(holding, "method") != METHOD_EQUITY:
            continue  # cost interests are not consolidated line by line
        hid = _holding_id(holding)
        checked += 1
        block = by_holding.get(hid)
        if block is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"blocks/{hid}"),
                    f"equity holding {hid} has no elimination block; its investment and "
                    f"the sub's equity both survive into consolidation, double-counting "
                    f"the same net assets",
                )
            )
            continue
        inv_account = _text(holding, "investment_account")
        eq_account = _text(holding, "equity_parent_account")
        lines = _rows(block, "lines")
        has_credit = any(
            _text(line, "account") == inv_account
            and isinstance(line.get("credit_cents"), int)
            and not isinstance(line.get("credit_cents"), bool)
            and line.get("credit_cents") != 0
            for line in lines
        )
        has_debit = any(
            _text(line, "account") == eq_account
            and isinstance(line.get("debit_cents"), int)
            and not isinstance(line.get("debit_cents"), bool)
            and line.get("debit_cents") != 0
            for line in lines
        )
        if not has_credit or not has_debit:
            missing = []
            if not has_credit:
                missing.append(f"a credit to investment account {inv_account}")
            if not has_debit:
                missing.append(f"a debit to equity-parent account {eq_account}")
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"blocks/{_block_id(block)}/lines"),
                    f"holding {hid}'s elimination block {_block_id(block)} lacks "
                    f"{' and '.join(missing)}; the investment/equity pair is not "
                    f"extinguished together",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} equity holdings are paired investment-to-equity",
            )
        )
    return out


@check("elim_extinguishes_investment")
def check_elim_extinguishes_investment(ctx: Context) -> list[Finding]:
    """The elimination credits the investment account for exactly the carrying
    value the roll-forward ends at.

    The carrying value moved all period; an elimination still crediting last
    period's figure leaves a residual on consolidation that is neither an
    asset nor equity -- invisible until the blocks stop netting to zero.
    """
    rule = "elim_extinguishes_investment"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ELIMINATION_SCHEDULE)
    if schedule is None:
        return []
    by_holding = _block_by_holding(ctx)
    rf = _rf_by_holding(ctx)
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        if _text(holding, "method") != METHOD_EQUITY:
            continue
        hid = _holding_id(holding)
        block = by_holding.get(hid)
        if block is None:
            continue  # elim_pairing_complete owns this
        row = rf.get(hid)
        if row is None:
            continue  # rf_coverage_complete owns this
        inv_account = _text(holding, "investment_account")
        with amount_guard(rule, out):
            end = require_cents(f"rollforward[{hid}].end_cents", row.get("end_cents"))
            credited = 0
            for i, line in enumerate(_rows(block, "lines")):
                if _text(line, "account") == inv_account:
                    credited += require_cents(
                        f"elimination[{_block_id(block)}].lines[{i}].credit_cents",
                        line.get("credit_cents"),
                    )
            checked += 1
            if credited != end:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"blocks/{_block_id(block)}/lines"),
                        f"block {_block_id(block)} credits {inv_account} {fmt(credited)}; "
                        f"the roll-forward carries {fmt(end)}, leaving "
                        f"{fmt(end - credited)} of holding {hid} unextinguished on "
                        f"consolidation",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} eliminations extinguish the full carrying value",
            )
        )
    return out


@check("elim_refs_known")
def check_elim_refs_known(ctx: Context) -> list[Finding]:
    """Every elimination block names a registered equity-method holding.

    An orphan block eliminates something nobody holds; a block against a
    cost-method interest eliminates an investment that consolidation never
    picks up line by line in the first place.
    """
    rule = "elim_refs_known"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ELIMINATION_SCHEDULE)
    if schedule is None:
        return []
    holdings = _holding_map(ctx)
    out: list[Finding] = []
    for block in _blocks(ctx):
        bid = _block_id(block)
        hid = _text(block, "holding_id")
        holding = holdings.get(hid or "")
        if holding is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"blocks/{bid}/holding_id"),
                    f"block {bid} eliminates holding {hid!r}, which is not in the holding "
                    f"register; it cancels an interest nobody holds",
                )
            )
        elif _text(holding, "method") != METHOD_EQUITY:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"blocks/{bid}/holding_id"),
                    f"block {bid} eliminates holding {hid}, which is carried at cost; a "
                    f"cost-method interest is not consolidated line by line and has no "
                    f"equity to eliminate against",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_blocks(ctx))} elimination blocks name equity-method holdings",
            )
        )
    return out


@check("elim_account_link_key")
def check_elim_account_link_key(ctx: Context) -> list[Finding]:
    """The holding's GL accounts embed the entity codes that link them.

    The parenthetical company code is the machine link key of the whole
    pairing: Investment is ``<parent code>-1<sub code>``, the pickup account is
    ``<parent code>-3<sub code>``, and the sub's Equity-Parent account opens
    with ``<sub code>-29``. Break the convention and the pairing stops being
    mechanically checkable -- which is exactly when eliminations go stale.
    """
    rule = "elim_account_link_key"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_HOLDING_REGISTER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        hid = _holding_id(holding)
        parent = entities.get(_text(holding, "parent_id") or "")
        sub = entities.get(_text(holding, "sub_id") or "")
        if parent is None or sub is None:
            continue  # epu_refs_resolve owns this
        parent_code = _text(parent, "entity_code")
        sub_code = _text(sub, "entity_code")
        if not parent_code or not sub_code:
            continue  # nothing to derive the convention from
        checked += 1
        expected_inv = f"{parent_code}-1{sub_code}"
        expected_pick = f"{parent_code}-3{sub_code}"
        eq_prefix = f"{sub_code}-29"
        inv = _text(holding, "investment_account")
        pick = _text(holding, "pickup_account")
        eq = _text(holding, "equity_parent_account")
        if inv != expected_inv:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{hid}/investment_account"),
                    f"holding {hid} books its investment at {inv!r}; the code link key "
                    f"derives {expected_inv} from parent {parent_code} and sub "
                    f"{sub_code}, and the pairing is only mechanical while it holds",
                )
            )
        if pick != expected_pick:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{hid}/pickup_account"),
                    f"holding {hid} routes its pickup to {pick!r}; the code link key "
                    f"derives {expected_pick}",
                )
            )
        if not (eq or "").startswith(eq_prefix):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"holdings/{hid}/equity_parent_account"),
                    f"holding {hid} pairs against equity account {eq!r}, which does not "
                    f"open with {eq_prefix}; the sub-side of the pair is not linkable "
                    f"by code",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} holdings follow the account link-key convention",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# pref_ -- preferred-return day-count accrual
# --------------------------------------------------------------------------- #
@check("pref_day_count")
def check_pref_day_count(ctx: Context) -> list[Finding]:
    """Each accrual row's stated day count equals its dates, counted inclusively.

    The day count is the multiplier of the whole accrual. One day misstated
    compounds forward through every later period the schedule accrues.
    """
    rule = "pref_day_count"
    _sev(rule, Status.FAIL)
    schedule_doc = ctx.one(DOC_PREFERRED_RETURN)
    if schedule_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for schedule in _schedules(ctx):
        mid = _text(schedule, "member_id") or "?"
        for row in _rows(schedule, "rows"):
            rno = row.get("row_no", "?")
            start = _parse_date(row.get("start_date"))
            end = _parse_date(row.get("end_date"))
            if start is None or end is None or end < start:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule_doc, f"schedules/{mid}/rows/{rno}"),
                        f"schedule {mid} row {rno} carries dates "
                        f"{row.get('start_date')!r}..{row.get('end_date')!r}, which do "
                        f"not form a forward-running period; no day count can be derived",
                    )
                )
                continue
            with amount_guard(rule, out):
                stated = require_cents(
                    f"preferred[{mid}].rows[{rno}].days",
                    row.get("days"),
                    unit="a whole day count",
                )
                derived = inclusive_days(start, end)
                checked += 1
                if stated != derived:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(schedule_doc, f"schedules/{mid}/rows/{rno}/days"),
                            f"schedule {mid} row {rno} states {stated} day(s); "
                            f"{start.isoformat()}..{end.isoformat()} counted inclusively "
                            f"is {derived}",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} accrual day counts re-derive exactly")
        )
    return out


@check("pref_accrual_rederives")
def check_pref_accrual_rederives(ctx: Context) -> list[Finding]:
    """Each period's accrued preferred return recomputes as capital x rate x
    days / basis.

    The accrual is derived from the row's own dates, not its stated day count,
    so a misstated count cannot launder a misstated accrual. One truncating
    division, no intermediate rounding.
    """
    rule = "pref_accrual_rederives"
    _sev(rule, Status.FAIL)
    schedule_doc = ctx.one(DOC_PREFERRED_RETURN)
    if schedule_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for schedule in _schedules(ctx):
        mid = _text(schedule, "member_id") or "?"
        with amount_guard(rule, out):
            rate = require_cents(
                f"preferred[{mid}].rate_bps",
                schedule.get("rate_bps"),
                unit="integer basis points",
            )
            basis = schedule.get("day_basis", DEFAULT_DAY_BASIS)
            basis = require_cents(
                f"preferred[{mid}].day_basis", basis, unit="a whole day-count basis"
            )
            if basis < 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule_doc, f"schedules/{mid}/day_basis"),
                        f"schedule {mid} states a day-count basis of {basis}; the accrual "
                        f"divides by it and cannot",
                    )
                )
                continue
            for row in _rows(schedule, "rows"):
                rno = row.get("row_no", "?")
                start = _parse_date(row.get("start_date"))
                end = _parse_date(row.get("end_date"))
                if start is None or end is None or end < start:
                    continue  # pref_day_count owns this
                with amount_guard(rule, out):
                    opening = require_cents(
                        f"preferred[{mid}].rows[{rno}].opening_capital_cents",
                        row.get("opening_capital_cents"),
                    )
                    stated = require_cents(
                        f"preferred[{mid}].rows[{rno}].accrued_cents",
                        row.get("accrued_cents"),
                    )
                    derived = preferred_accrual(opening, rate, inclusive_days(start, end), basis)
                    checked += 1
                    if stated != derived:
                        out.append(
                            Finding(
                                rule,
                                Status.FAIL,
                                ctx.loc(
                                    schedule_doc, f"schedules/{mid}/rows/{rno}/accrued_cents"
                                ),
                                f"schedule {mid} row {rno} states accrued {fmt(stated)}; "
                                f"{fmt(opening)} x {rate} bps x "
                                f"{inclusive_days(start, end)}/{basis} re-derives "
                                f"{fmt(derived)} (off by {fmt(stated - derived)})",
                            )
                        )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} preferred accruals re-derive exactly")
        )
    return out


@check("pref_capital_chains")
def check_pref_capital_chains(ctx: Context) -> list[Finding]:
    """The capital balance chains: each row ends at opening + contribution, and
    each row opens where the prior one ended.

    The accrual is earned on the opening balance, so a broken chain does not
    stay a display error -- every later period accrues on capital that was
    never contributed or has already left.
    """
    rule = "pref_capital_chains"
    _sev(rule, Status.FAIL)
    schedule_doc = ctx.one(DOC_PREFERRED_RETURN)
    if schedule_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for schedule in _schedules(ctx):
        mid = _text(schedule, "member_id") or "?"
        with amount_guard(rule, out):
            expected_opening = require_cents(
                f"preferred[{mid}].opening_capital_cents",
                schedule.get("opening_capital_cents"),
            )
            for row in _rows(schedule, "rows"):
                rno = row.get("row_no", "?")
                with amount_guard(rule, out):
                    opening = require_cents(
                        f"preferred[{mid}].rows[{rno}].opening_capital_cents",
                        row.get("opening_capital_cents"),
                    )
                    contribution = require_cents(
                        f"preferred[{mid}].rows[{rno}].contribution_cents",
                        row.get("contribution_cents"),
                    )
                    ending = require_cents(
                        f"preferred[{mid}].rows[{rno}].ending_capital_cents",
                        row.get("ending_capital_cents"),
                    )
                    checked += 1
                    if opening != expected_opening:
                        out.append(
                            Finding(
                                rule,
                                Status.FAIL,
                                ctx.loc(
                                    schedule_doc,
                                    f"schedules/{mid}/rows/{rno}/opening_capital_cents",
                                ),
                                f"schedule {mid} row {rno} opens at {fmt(opening)}; the "
                                f"chain carries {fmt(expected_opening)} forward from the "
                                f"prior period (off by {fmt(opening - expected_opening)})",
                            )
                        )
                    if ending != opening + contribution:
                        out.append(
                            Finding(
                                rule,
                                Status.FAIL,
                                ctx.loc(
                                    schedule_doc,
                                    f"schedules/{mid}/rows/{rno}/ending_capital_cents",
                                ),
                                f"schedule {mid} row {rno} ends at {fmt(ending)}; opening "
                                f"{fmt(opening)} + contribution {fmt(contribution)} "
                                f"re-derives {fmt(opening + contribution)} -- the return "
                                f"does not compound into capital",
                            )
                        )
                    expected_opening = ending
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} capital-chain rows link exactly")
        )
    return out


@check("pref_periods_contiguous")
def check_pref_periods_contiguous(ctx: Context) -> list[Finding]:
    """Accrual periods abut: each row starts the day after the prior row ends.

    A gap is capital earning nothing for days the agreement accrues on; an
    overlap accrues the same day twice. Both are date arithmetic, not judgment.
    """
    rule = "pref_periods_contiguous"
    _sev(rule, Status.FAIL)
    schedule_doc = ctx.one(DOC_PREFERRED_RETURN)
    if schedule_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for schedule in _schedules(ctx):
        mid = _text(schedule, "member_id") or "?"
        rows = _rows(schedule, "rows")
        for prior, current in zip(rows, rows[1:]):
            prior_end = _parse_date(prior.get("end_date"))
            start = _parse_date(current.get("start_date"))
            if prior_end is None or start is None:
                continue  # pref_day_count owns unreadable dates
            checked += 1
            if start != prior_end + timedelta(days=1):
                gap = (start - prior_end).days - 1
                what = f"leaves {gap} unaccrued day(s)" if gap > 0 else (
                    f"re-accrues {-gap} day(s) already earned"
                )
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            schedule_doc,
                            f"schedules/{mid}/rows/{current.get('row_no', '?')}/start_date",
                        ),
                        f"schedule {mid} row {current.get('row_no', '?')} starts "
                        f"{start.isoformat()} but the prior period ended "
                        f"{prior_end.isoformat()}; the handover {what}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} accrual-period handovers abut exactly")
        )
    return out


# --------------------------------------------------------------------------- #
# alloc_ -- member allocation and the trial-balance tie-out
# --------------------------------------------------------------------------- #
@check("alloc_foots")
def check_alloc_foots(ctx: Context) -> list[Finding]:
    """Each allocation entry's stated total equals the sum of its member rows.

    A total maintained beside the rows rather than derived from them drifts
    the first time an allocation moves and nobody re-adds the column.
    """
    rule = "alloc_foots"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_ALLOCATION_SUMMARY)
    if summary is None:
        return []
    out: list[Finding] = []
    checked = 0
    for entry in _entries(ctx):
        sid = _text(entry, "sub_id") or "?"
        with amount_guard(rule, out):
            member_sum = 0
            for i, member in enumerate(_rows(entry, "members")):
                member_sum += require_cents(
                    f"allocation[{sid}].members[{i}].allocated_cents",
                    member.get("allocated_cents"),
                )
            stated = require_cents(
                f"allocation[{sid}].stated_total_cents", entry.get("stated_total_cents")
            )
            checked += 1
            if stated != member_sum:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"entries/{sid}/stated_total_cents"),
                        f"the {sid} allocation states a total of {fmt(stated)}; its member "
                        f"rows sum to {fmt(member_sum)} (off by {fmt(stated - member_sum)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} allocation entries foot exactly")
        )
    return out


@check("alloc_ties_net_income")
def check_alloc_ties_net_income(ctx: Context) -> list[Finding]:
    """For every fully equity-held sub, the member allocations sum to exactly
    the sub's net income.

    Income allocated is income owned: when the holders own the whole sub,
    every cent of the result belongs to exactly one member and none is left
    over. A missing entry, or a sum a cent off the income, is income that
    silently belongs to nobody.
    """
    rule = "alloc_ties_net_income"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_ALLOCATION_SUMMARY)
    if summary is None:
        return []
    results = _result_map(ctx)
    entries_by_sub: dict[str, list[dict[str, Any]]] = {}
    for entry in _entries(ctx):
        sid = _text(entry, "sub_id")
        if sid:
            entries_by_sub.setdefault(sid, []).append(entry)
    out: list[Finding] = []
    checked = 0
    for sub in _subsidiaries(ctx):
        sid = _text(sub, "entity_id") or "?"
        holders = _equity_holdings_of(ctx, sid)
        if not holders:
            continue  # nothing allocated where nothing is equity-held
        with amount_guard(rule, out):
            total_bps = sum(
                require_cents(
                    f"holding[{_holding_id(h)}].ownership_bps",
                    h.get("ownership_bps"),
                    unit="integer basis points",
                )
                for h in holders
            )
            if total_bps != BPS_FULL:
                continue  # a partially-held sub allocates only its holders' slices
            result = results.get(sid)
            if result is None:
                continue  # epu_refs_resolve owns this
            net_income = require_cents(
                f"sub_results[{sid}].net_income_cents", result.get("net_income_cents")
            )
            found = entries_by_sub.get(sid, [])
            checked += 1
            if len(found) != 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"entries/{sid}"),
                        f"fully-held sub {sid} has {len(found)} allocation entrie(s); its "
                        f"{fmt(net_income)} of net income must be allocated exactly once",
                    )
                )
                continue
            member_sum = sum(
                require_cents(
                    f"allocation[{sid}].members[{i}].allocated_cents",
                    member.get("allocated_cents"),
                )
                for i, member in enumerate(_rows(found[0], "members"))
            )
            if member_sum != net_income:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"entries/{sid}/members"),
                        f"the {sid} member allocations sum to {fmt(member_sum)}; the sub "
                        f"earned {fmt(net_income)}, leaving {fmt(net_income - member_sum)} "
                        f"of income belonging to nobody",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} fully-held subs allocate exactly their net income",
            )
        )
    return out


@check("alloc_member_is_holder")
def check_alloc_member_is_holder(ctx: Context) -> list[Finding]:
    """Every allocation member actually holds an equity interest in that sub.

    An allocation to a non-holder hands a share of income to an entity whose
    ownership percentage is zero -- the arithmetic can still foot while the
    income lands in the wrong books.
    """
    rule = "alloc_member_is_holder"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_ALLOCATION_SUMMARY)
    if summary is None:
        return []
    out: list[Finding] = []
    checked = 0
    for entry in _entries(ctx):
        sid = _text(entry, "sub_id") or "?"
        holder_parents = {_text(h, "parent_id") for h in _equity_holdings_of(ctx, sid)}
        for member in _rows(entry, "members"):
            pid = _text(member, "parent_id")
            checked += 1
            if pid not in holder_parents:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"entries/{sid}/members/{pid}"),
                        f"the {sid} allocation includes member {pid!r}, which holds no "
                        f"equity interest in {sid}; income is landing in books with no "
                        f"ownership behind them",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} allocation members hold their sub"
            )
        )
    return out


@check("alloc_tb_investment_ties")
def check_alloc_tb_investment_ties(ctx: Context) -> list[Finding]:
    """Each holding's trial-balance investment account carries exactly the
    roll-forward ending value.

    The schedule and the ledger describe one asset. A carrying value that
    ended the roll-forward somewhere the TB does not show is a workpaper that
    stopped describing the books it supports.
    """
    rule = "alloc_tb_investment_ties"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if tb is None:
        return []
    rf = _rf_by_holding(ctx)
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        hid = _holding_id(holding)
        row = rf.get(hid)
        if row is None:
            continue  # rf_coverage_complete owns this
        parent_id = _text(holding, "parent_id") or "?"
        account = _text(holding, "investment_account") or "?"
        tb_row = _tb_row(ctx, parent_id, account)
        if tb_row is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(tb, f"rows/{parent_id}/{account}"),
                    f"holding {hid}'s investment account {account} has no trial-balance "
                    f"row on {parent_id}; the roll-forward supports a balance the books "
                    f"do not carry",
                )
            )
            continue
        with amount_guard(rule, out):
            end = require_cents(f"rollforward[{hid}].end_cents", row.get("end_cents"))
            balance = require_cents(
                f"trial_balance[{parent_id}/{account}].balance_cents",
                tb_row.get("balance_cents"),
            )
            checked += 1
            if balance != end:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"rows/{parent_id}/{account}/balance_cents"),
                        f"account {account} carries {fmt(balance)} on the trial balance; "
                        f"holding {hid}'s roll-forward ends at {fmt(end)} "
                        f"(off by {fmt(balance - end)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} investment accounts tie the roll-forward exactly",
            )
        )
    return out


@check("alloc_tb_pickup_ties")
def check_alloc_tb_pickup_ties(ctx: Context) -> list[Finding]:
    """Each equity holding's pickup account carries exactly the re-derived
    share of income, as a credit.

    The pickup account is an income account, so the share sits as a credit
    (negative) balance. Compared against the *re-derived* share, not the
    stated one, so a mis-keyed roll-forward cannot vouch for a mis-keyed
    ledger.
    """
    rule = "alloc_tb_pickup_ties"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if tb is None:
        return []
    out: list[Finding] = []
    checked = 0
    for holding in _holdings(ctx):
        if _text(holding, "method") != METHOD_EQUITY:
            continue  # a cost holding routes no pickup anywhere
        hid = _holding_id(holding)
        parent_id = _text(holding, "parent_id") or "?"
        account = _text(holding, "pickup_account") or "?"
        with amount_guard(rule, out):
            derived = expected_pickup(ctx, holding)
            if derived is None:
                continue  # epu_refs_resolve owns the missing result row
            tb_row = _tb_row(ctx, parent_id, account)
            if tb_row is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"rows/{parent_id}/{account}"),
                        f"holding {hid}'s pickup account {account} has no trial-balance "
                        f"row on {parent_id}; a {fmt(derived)} share of income was never "
                        f"booked anywhere",
                    )
                )
                continue
            balance = require_cents(
                f"trial_balance[{parent_id}/{account}].balance_cents",
                tb_row.get("balance_cents"),
            )
            checked += 1
            if balance != -derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"rows/{parent_id}/{account}/balance_cents"),
                        f"pickup account {account} carries {fmt(balance)}; ownership x sub "
                        f"net income re-derives a credit of {fmt(-derived)} "
                        f"(off by {fmt(balance + derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} pickup accounts tie the re-derived share exactly",
            )
        )
    return out


@check("alloc_tb_adjustment_math")
def check_alloc_tb_adjustment_math(ctx: Context) -> list[Finding]:
    """Every trial-balance adjustment equals should-be minus balance.

    The should-be and adjustment columns are one subtraction apart by
    construction. An adjustment that is not that subtraction posts a
    correction of the wrong size -- and looks reviewed while doing it.
    """
    rule = "alloc_tb_adjustment_math"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if tb is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _tb_rows(ctx):
        entity_id = _text(row, "entity_id") or "?"
        account = _text(row, "account") or "?"
        with amount_guard(rule, out):
            balance = require_cents(
                f"trial_balance[{entity_id}/{account}].balance_cents",
                row.get("balance_cents"),
            )
            should_be = require_cents(
                f"trial_balance[{entity_id}/{account}].should_be_cents",
                row.get("should_be_cents"),
            )
            adjustment = require_cents(
                f"trial_balance[{entity_id}/{account}].adjustment_cents",
                row.get("adjustment_cents"),
            )
            checked += 1
            if adjustment != should_be - balance:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"rows/{entity_id}/{account}/adjustment_cents"),
                        f"account {account} on {entity_id} states adjustment "
                        f"{fmt(adjustment)}; should-be {fmt(should_be)} minus balance "
                        f"{fmt(balance)} re-derives {fmt(should_be - balance)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} trial-balance adjustments re-derive exactly",
            )
        )
    return out


@check("alloc_tb_unposted_adjustment")
def check_alloc_tb_unposted_adjustment(ctx: Context) -> list[Finding]:
    """A non-zero trial-balance adjustment is flagged for review.

    Deliberately a FLAG, not a failure: the workpaper is internally consistent
    -- the adjustment is exactly should-be minus balance -- but a correction
    someone derived and never posted is a book that still shows the old
    figure, and a human decides when it moves.
    """
    rule = "alloc_tb_unposted_adjustment"
    _sev(rule, Status.FLAG)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if tb is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _tb_rows(ctx):
        entity_id = _text(row, "entity_id") or "?"
        account = _text(row, "account") or "?"
        with amount_guard(rule, out):
            adjustment = require_cents(
                f"trial_balance[{entity_id}/{account}].adjustment_cents",
                row.get("adjustment_cents"),
            )
            checked += 1
            if adjustment != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(tb, f"rows/{entity_id}/{account}/adjustment_cents"),
                        f"account {account} on {entity_id} carries an unposted adjustment "
                        f"of {fmt(adjustment)}; the correction is derived but the books "
                        f"still show the old figure -- due for a human's entry",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} trial-balance rows carry no unposted adjustment",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one consolidation file."""
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
    """Analyze every ``.json`` consolidation file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of consolidation-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
