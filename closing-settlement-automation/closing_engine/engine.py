"""
Home-sale closing & settlement tie-out control engine (READ-ONLY).
==================================================================

Loads each closing file (a ``.json`` file produced by
:mod:`closing_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the paper the closing produced agrees with
itself**, not whether the deal should have been done. Underwriting -- what a home
should have sold for, whether the loan should have been made -- is a separate
question a different engine owns. This engine is that tie-out check.

The shape of the problem
------------------------
When a home closes escrow the accounting team assembles a package: a settlement
statement, a balanced journal entry, a revenue-recognition line, a loan release
tied to the lender's statement, and a cost-of-sale relief. Every one of those is
a spreadsheet, and each goes wrong in ways that do not look wrong in a folder:
the entry that does not foot; the settlement total that was keyed rather than
summed; the fee struck at the wrong rate; revenue recognised in the wrong month;
the loan release that does not tie; and the rollup that states a count or a total
nobody recomputed from the units underneath it.

The registry is organised around that:

1. ``set_``  -- is the closing file complete?
2. ``unit_`` -- is the unit register sound, and does every closed unit have its
   full package?
3. ``je_``   -- does each closing journal entry foot, with a derived receivable?
4. ``ss_``   -- does the settlement statement recompute?
5. ``fee_``  -- do the rate-derived fees strike at their proforma rates?
6. ``rev_``  -- was revenue recognised in the close month?
7. ``loan_`` -- does each loan release tie to the lender's loan statement?
8. ``cos_``  -- does the cost-of-sale / margin relief recompute?
9. ``rpt_``  -- does the rollup recompute from the units it summarises?

Design notes
------------
- **Strictly read-only.** Closing files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every figure is compared with exact ``==``.
- **One tie-out predicate.** Controls and the generator share the kernel in
  :mod:`closing_engine.settlement`, so a determination cannot disagree with the
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

from .money import AmountInvalidError, apply_rate, fmt, fmt_bps, require_cents
from .model import (
    ACCOUNT_ACCOUNTS_RECEIVABLE,
    DOC_CLOSING_JE_REGISTER,
    DOC_CLOSING_REPORT,
    DOC_CLOSING_SUMMARY,
    DOC_COS_SCHEDULE,
    DOC_LOAN_RELEASE_REGISTER,
    DOC_PROFORMA_ASSUMPTIONS,
    DOC_REVENUE_SCHEDULE,
    DOC_SETTLEMENT_REGISTER,
    DOC_TYPES,
    DOC_UNIT_REGISTER,
    STATUS_CLOSED,
    UNIT_STATUSES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .settlement import (
    CHARGE_FIELDS,
    ar_plug,
    coe_month,
    derived_fee,
    loan_ending_balance,
    margin_bps,
    net_to_seller,
    prepaid_commission_relieved,
    revised_project_profit,
    total_closing_costs,
    total_settlement_charges,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~closing_engine.money.AmountInvalidError` as a finding."""
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


def _text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) and value else None


def _int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# --------------------------------------------------------------------------- #
# Closing-file accessors
# --------------------------------------------------------------------------- #
def _rows(doc: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    rows = doc.get(key)
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _units(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_UNIT_REGISTER), "units")


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


def _closed_units(ctx: Context) -> list[dict[str, Any]]:
    return [u for u in _units(ctx) if _text(u, "status") == STATUS_CLOSED]


def _settlements(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SETTLEMENT_REGISTER), "settlements")


def _settlement_for(ctx: Context, unit_id: str) -> dict[str, Any] | None:
    rows = [s for s in _settlements(ctx) if _text(s, "unit_id") == unit_id]
    return rows[0] if len(rows) == 1 else None


def _jes(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CLOSING_JE_REGISTER), "entries")


def _jes_for(ctx: Context, unit_id: str) -> list[dict[str, Any]]:
    return [j for j in _jes(ctx) if _text(j, "unit_id") == unit_id]


def _revenue_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_REVENUE_SCHEDULE), "entries")


def _revenue_for(ctx: Context, unit_id: str) -> dict[str, Any] | None:
    rows = [r for r in _revenue_entries(ctx) if _text(r, "unit_id") == unit_id]
    return rows[0] if len(rows) == 1 else None


def _loan_releases(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_LOAN_RELEASE_REGISTER), "releases")


def _loan_for(ctx: Context, unit_id: str) -> dict[str, Any] | None:
    rows = [r for r in _loan_releases(ctx) if _text(r, "unit_id") == unit_id]
    return rows[0] if len(rows) == 1 else None


def _cos_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_COS_SCHEDULE), "entries")


def _cos_for(ctx: Context, unit_id: str) -> dict[str, Any] | None:
    rows = [r for r in _cos_entries(ctx) if _text(r, "unit_id") == unit_id]
    return rows[0] if len(rows) == 1 else None


def _summary_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CLOSING_SUMMARY), "units")


# --------------------------------------------------------------------------- #
# Proforma rate lookups
# --------------------------------------------------------------------------- #
def _bps(row: dict[str, Any] | None, key: str) -> int:
    """Read a basis-point rate; raises :class:`AmountInvalidError` if malformed."""
    if not isinstance(row, dict):
        raise AmountInvalidError(f"proforma_assumptions.{key}", None, "a basis-point rate")
    return require_cents(f"proforma_assumptions.{key}", row.get(key), unit="a basis-point rate")


# --------------------------------------------------------------------------- #
# Journal-entry helpers
# --------------------------------------------------------------------------- #
def _je_lines(je: dict[str, Any]) -> list[dict[str, Any]]:
    lines = je.get("lines")
    return [ln for ln in lines if isinstance(ln, dict)] if isinstance(lines, list) else []


def _je_id(je: dict[str, Any]) -> str:
    value = je.get("entry_id")
    return value if isinstance(value, str) and value else "?"


def _line_debit(je: dict[str, Any], line: dict[str, Any]) -> int:
    return require_cents(f"entry[{_je_id(je)}].line.debit_cents", line.get("debit_cents"))


def _line_credit(je: dict[str, Any], line: dict[str, Any]) -> int:
    return require_cents(f"entry[{_je_id(je)}].line.credit_cents", line.get("credit_cents"))


def _je_debit_total(je: dict[str, Any]) -> int:
    return sum(_line_debit(je, ln) for ln in _je_lines(je))


def _je_credit_total(je: dict[str, Any]) -> int:
    return sum(_line_credit(je, ln) for ln in _je_lines(je))


def _je_balances_ok(je: dict[str, Any]) -> bool:
    return _je_debit_total(je) == _je_credit_total(je)


def _je_ar_plug_ok(je: dict[str, Any]) -> bool:
    lines = _je_lines(je)
    ar_lines = [ln for ln in lines if _text(ln, "account") == ACCOUNT_ACCOUNTS_RECEIVABLE]
    if len(ar_lines) != 1:
        return False
    ar_debit = _line_debit(je, ar_lines[0])
    non_ar_debit = sum(
        _line_debit(je, ln)
        for ln in lines
        if _text(ln, "account") != ACCOUNT_ACCOUNTS_RECEIVABLE
    )
    credit_total = _je_credit_total(je)
    return ar_debit == ar_plug(credit_total, non_ar_debit)


# --------------------------------------------------------------------------- #
# Per-unit re-derivations (shared through settlement.py)
# --------------------------------------------------------------------------- #
def _charge_components(settlement: dict[str, Any]) -> list[int]:
    return [
        require_cents(f"settlement.{f}", settlement.get(f)) for f in CHARGE_FIELDS
    ]


def recompute_unit_tied(ctx: Context, unit: dict[str, Any]) -> bool:
    """Recompute a closed unit's tie-out determination from its package.

    A closed unit is *tied* when its settlement recomputes, its rate-derived fees
    strike at the proforma rates, its closing entry foots with a derived
    receivable, revenue was recognised in the close month, its loan release ties
    to the lender statement, and its cost-of-sale relief recomputes. Shared with
    the generator through the same primitives the controls use, so the
    determination the engine recomputes is the one that produced the data.

    Raises :class:`AmountInvalidError` if a figure it must read is not integer
    cents; the calling control contains that to the unit being read.
    """
    uid = _unit_id(unit)
    if _text(unit, "status") != STATUS_CLOSED:
        return False
    coe = _parse_date(unit.get("coe_date"))
    if coe is None:
        return False
    gross = require_cents(f"unit[{uid}].gross_sales_cents", unit.get("gross_sales_cents"))
    deferred = require_cents(
        f"unit[{uid}].deferred_upgrade_cents", unit.get("deferred_upgrade_cents")
    )
    prepaid_balance = require_cents(
        f"unit[{uid}].prepaid_balance_cents", unit.get("prepaid_balance_cents")
    )

    proforma = ctx.one(DOC_PROFORMA_ASSUMPTIONS)
    listing_bps = _bps(proforma, "listing_sales_fee_bps")
    warranty_bps = _bps(proforma, "warranty_reserve_bps")

    settlement = _settlement_for(ctx, uid)
    if settlement is None:
        return False
    components = _charge_components(settlement)
    charges = total_settlement_charges(components)
    broker = components[0]
    if require_cents("settlement.total_settlement_charges_cents", settlement.get("total_settlement_charges_cents")) != charges:
        return False
    if require_cents("settlement.total_closing_costs_cents", settlement.get("total_closing_costs_cents")) != total_closing_costs(charges, broker):
        return False
    if require_cents("settlement.net_to_seller_cents", settlement.get("net_to_seller_cents")) != net_to_seller(gross, charges):
        return False
    if require_cents("settlement.listing_sales_fee_cents", settlement.get("listing_sales_fee_cents")) != derived_fee(gross, listing_bps):
        return False
    if require_cents("settlement.warranty_reserve_cents", settlement.get("warranty_reserve_cents")) != derived_fee(gross, warranty_bps):
        return False

    jes = _jes_for(ctx, uid)
    if len(jes) != 1:
        return False
    if not _je_balances_ok(jes[0]) or not _je_ar_plug_ok(jes[0]):
        return False

    revenue = _revenue_for(ctx, uid)
    if revenue is None:
        return False
    if _text(revenue, "recognized_month") != coe_month(coe):
        return False
    if require_cents("revenue.deferred_upgrade_reversed_cents", revenue.get("deferred_upgrade_reversed_cents")) != deferred:
        return False

    loan = _loan_for(ctx, uid)
    if loan is None:
        return False
    ending = loan_ending_balance(
        require_cents("loan.beginning_balance_cents", loan.get("beginning_balance_cents")),
        require_cents("loan.draws_cents", loan.get("draws_cents")),
        require_cents("loan.interest_fees_cents", loan.get("interest_fees_cents")),
        require_cents("loan.bank_remittance_cents", loan.get("bank_remittance_cents")),
        require_cents("loan.paydowns_cents", loan.get("paydowns_cents")),
    )
    stated_ending = require_cents("loan.ending_balance_cents", loan.get("ending_balance_cents"))
    if stated_ending != ending:
        return False
    if require_cents("loan.lender_statement_ending_cents", loan.get("lender_statement_ending_cents")) != stated_ending:
        return False

    cos = _cos_for(ctx, uid)
    if cos is None:
        return False
    revised = revised_project_profit(
        require_cents("cos.projected_profit_cents", cos.get("projected_profit_cents")),
        require_cents("cos.carry_costs_cents", cos.get("carry_costs_cents")),
    )
    if require_cents("cos.revised_profit_cents", cos.get("revised_profit_cents")) != revised:
        return False
    pnr = require_cents("cos.projected_net_revenue_cents", cos.get("projected_net_revenue_cents"))
    if require_cents("cos.margin_bps", cos.get("margin_bps"), unit="a basis-point rate") != margin_bps(revised, pnr):
        return False
    commission_earned = require_cents("cos.commission_earned_cents", cos.get("commission_earned_cents"))
    if require_cents("cos.prepaid_relieved_cents", cos.get("prepaid_relieved_cents")) != prepaid_commission_relieved(commission_earned, prepaid_balance):
        return False
    return True


def recompute_closed_count(ctx: Context) -> int:
    """The number of closed units, recomputed from the unit register."""
    return len(_closed_units(ctx))


def recompute_net_to_seller_total(ctx: Context) -> int:
    """Total net-to-seller across closed units, re-derived from the settlements.

    Reads each closed unit's gross sales and settlement charges and sums the
    re-derived net proceeds, so the report total ties to the evidence rather than
    to a separately maintained figure. Raises on a malformed amount.
    """
    running = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue
        gross = require_cents(
            f"unit[{_unit_id(unit)}].gross_sales_cents", unit.get("gross_sales_cents")
        )
        charges = total_settlement_charges(_charge_components(settlement))
        running += net_to_seller(gross, charges)
    return running


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the closing file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the closing file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(DOC_TYPES)} closing artifacts are present"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# unit_ -- the unit register
# --------------------------------------------------------------------------- #
@check("unit_unique_ids")
def check_unit_unique_ids(ctx: Context) -> list[Finding]:
    """No unit id appears twice.

    The unit id joins the register to every settlement, entry, loan release and
    summary row. A duplicate makes a closing artifact ambiguous about which home
    it belongs to.
    """
    rule = "unit_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _units(ctx):
        seen[_unit_id(row)] = seen.get(_unit_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"units/{uid}"),
            f"unit id {uid} appears {count} times; a settlement that names it cannot "
            f"be attributed to one home",
        )
        for uid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} unit ids are unique"))
    return out


@check("unit_status_valid")
def check_unit_status_valid(ctx: Context) -> list[Finding]:
    """Every unit carries a known sale status.

    The status decides whether a unit requires a closing package at all; an
    unknown status would leave the completeness controls unable to say whether the
    unit should have closed.
    """
    rule = "unit_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"units/{_unit_id(row)}/status"),
            f"unit {_unit_id(row)} is status {_text(row, 'status')!r}, which is not one "
            f"of {UNIT_STATUSES}",
        )
        for row in _units(ctx)
        if _text(row, "status") not in UNIT_STATUSES
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_units(ctx))} units carry a known status")
        )
    return out


@check("unit_required_fields")
def check_unit_required_fields(ctx: Context) -> list[Finding]:
    """Every closed unit carries the close-of-escrow base facts.

    A closed unit with no close date, gross sales, deferred upgrades or prepaid
    balance cannot have its settlement, revenue or commission relief recomputed,
    so the tie-out controls would have nothing to measure against.
    """
    rule = "unit_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for unit in _closed_units(ctx):
        uid = _unit_id(unit)
        missing: list[str] = []
        if _parse_date(unit.get("coe_date")) is None:
            missing.append("coe_date")
        for f in ("gross_sales_cents", "deferred_upgrade_cents", "prepaid_balance_cents"):
            if _int(unit, f) is None:
                missing.append(f)
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"units/{uid}"),
                    f"closed unit {uid} is missing {', '.join(missing)}; its closing "
                    f"cannot be recomputed",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_closed_units(ctx))} closed units carry their base facts",
            )
        )
    return out


@check("unit_artifacts_complete")
def check_unit_artifacts_complete(ctx: Context) -> list[Finding]:
    """Every closed unit has exactly one of each closing artifact.

    A closed home must carry exactly one settlement, one journal entry, one
    revenue line, one loan release, one cost-of-sale entry and one summary row.
    A missing one is an incomplete package; a duplicate makes the tie-out
    ambiguous. This owns the "artifact absent" finding so the recompute controls
    can skip a unit whose row is missing rather than pass vacuously.
    """
    rule = "unit_artifacts_complete"
    _sev(rule, Status.FAIL)
    if ctx.one(DOC_UNIT_REGISTER) is None:
        return []
    checks: tuple[tuple[str, Callable[[Context, str], list[dict[str, Any]]]], ...] = (
        ("settlement", lambda c, u: [s for s in _settlements(c) if _text(s, "unit_id") == u]),
        ("closing entry", lambda c, u: _jes_for(c, u)),
        ("revenue line", lambda c, u: [r for r in _revenue_entries(c) if _text(r, "unit_id") == u]),
        ("loan release", lambda c, u: [r for r in _loan_releases(c) if _text(r, "unit_id") == u]),
        ("cost-of-sale entry", lambda c, u: [r for r in _cos_entries(c) if _text(r, "unit_id") == u]),
        ("summary row", lambda c, u: [r for r in _summary_rows(c) if _text(r, "unit_id") == u]),
    )
    out: list[Finding] = []
    for unit in _closed_units(ctx):
        uid = _unit_id(unit)
        for label, getter in checks:
            n = len(getter(ctx, uid))
            if n != 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ctx.one(DOC_UNIT_REGISTER), f"units/{uid}"),
                        f"closed unit {uid} has {n} {label} rows; a complete package "
                        f"carries exactly one",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_closed_units(ctx))} closed units have a complete package",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# je_ -- the closing journal entry foots
# --------------------------------------------------------------------------- #
@check("je_unit_exists")
def check_je_unit_exists(ctx: Context) -> list[Finding]:
    """Every closing entry names a unit in the register."""
    rule = "je_unit_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CLOSING_JE_REGISTER)
    if register is None:
        return []
    units = _unit_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"entries/{_je_id(je)}/unit_id"),
            f"closing entry {_je_id(je)} names unit {_text(je, 'unit_id')!r}, which is "
            f"not in the unit register",
        )
        for je in _jes(ctx)
        if _text(je, "unit_id") and _text(je, "unit_id") not in units
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every closing entry names a unit in the register")
        )
    return out


@check("je_balances")
def check_je_balances(ctx: Context) -> list[Finding]:
    """Each closing entry foots: total debits equal total credits.

    An entry whose debits and credits do not balance posts a number that ties to
    nothing. Compared with exact ``==`` on integer cents.
    """
    rule = "je_balances"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CLOSING_JE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        for je in _jes_for(ctx, _unit_id(unit)):
            with amount_guard(rule, out):
                debit = _je_debit_total(je)
                credit = _je_credit_total(je)
                checked += 1
                if debit != credit:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"entries/{_je_id(je)}"),
                            f"closing entry {_je_id(je)} for unit {_unit_id(unit)} posts "
                            f"{fmt(debit)} debits against {fmt(credit)} credits; the entry "
                            f"does not foot (off {fmt(debit - credit)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} closing entries foot"))
    return out


@check("je_ar_plug_recomputes")
def check_je_ar_plug_recomputes(ctx: Context) -> list[Finding]:
    """The Accounts Receivable line equals the derived balancing plug.

    The receivable is the plug -- total credits less the non-receivable debits --
    so a receivable that was typed rather than derived is caught here even when
    the entry happens to foot. Re-derived and compared with exact ``==``.
    """
    rule = "je_ar_plug_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CLOSING_JE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        for je in _jes_for(ctx, _unit_id(unit)):
            lines = _je_lines(je)
            ar_lines = [
                ln for ln in lines if _text(ln, "account") == ACCOUNT_ACCOUNTS_RECEIVABLE
            ]
            if len(ar_lines) != 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"entries/{_je_id(je)}"),
                        f"closing entry {_je_id(je)} for unit {_unit_id(unit)} carries "
                        f"{len(ar_lines)} Accounts Receivable lines; the entry needs exactly "
                        f"one to plug",
                    )
                )
                continue
            with amount_guard(rule, out):
                ar_debit = _line_debit(je, ar_lines[0])
                non_ar_debit = sum(
                    _line_debit(je, ln)
                    for ln in lines
                    if _text(ln, "account") != ACCOUNT_ACCOUNTS_RECEIVABLE
                )
                plug = ar_plug(_je_credit_total(je), non_ar_debit)
                checked += 1
                if ar_debit != plug:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"entries/{_je_id(je)}/Accounts_Receivable"),
                            f"closing entry {_je_id(je)} for unit {_unit_id(unit)} states an "
                            f"Accounts Receivable of {fmt(ar_debit)}; the derived plug is "
                            f"{fmt(plug)} (off {fmt(ar_debit - plug)})",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} receivable plugs recompute")
        )
    return out


# --------------------------------------------------------------------------- #
# ss_ -- the settlement statement recomputes
# --------------------------------------------------------------------------- #
@check("ss_total_charges_recompute")
def check_ss_total_charges_recompute(ctx: Context) -> list[Finding]:
    """Total settlement charges equals the sum of the charge components.

    A total that was keyed rather than summed drifts silently from the lines it is
    meant to total. Re-summed and compared with exact ``==``.
    """
    rule = "ss_total_charges_recompute"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_SETTLEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue  # unit_artifacts_complete owns this
        with amount_guard(rule, out):
            charges = total_settlement_charges(_charge_components(settlement))
            stated = require_cents(
                "settlement.total_settlement_charges_cents",
                settlement.get("total_settlement_charges_cents"),
            )
            checked += 1
            if stated != charges:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"settlements/{_unit_id(unit)}/total_settlement_charges_cents"),
                        f"unit {_unit_id(unit)} states total settlement charges of "
                        f"{fmt(stated)}; the components sum to {fmt(charges)} "
                        f"(off {fmt(stated - charges)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} settlement totals recompute")
        )
    return out


@check("ss_total_closing_costs_recompute")
def check_ss_total_closing_costs_recompute(ctx: Context) -> list[Finding]:
    """Total closing costs equals total settlement charges less broker commission.

    The broker commission is a selling cost, not a closing cost, so the closing
    total is the settlement total net of it. Re-derived and compared with ``==``.
    """
    rule = "ss_total_closing_costs_recompute"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_SETTLEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue
        with amount_guard(rule, out):
            components = _charge_components(settlement)
            expected = total_closing_costs(total_settlement_charges(components), components[0])
            stated = require_cents(
                "settlement.total_closing_costs_cents",
                settlement.get("total_closing_costs_cents"),
            )
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"settlements/{_unit_id(unit)}/total_closing_costs_cents"),
                        f"unit {_unit_id(unit)} states total closing costs of {fmt(stated)}; "
                        f"charges less broker commission is {fmt(expected)} "
                        f"(off {fmt(stated - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} closing-cost totals recompute")
        )
    return out


@check("ss_net_to_seller_recompute")
def check_ss_net_to_seller_recompute(ctx: Context) -> list[Finding]:
    """Net to seller equals gross sales less total settlement charges.

    This is the figure the whole statement exists to produce, so it is re-derived
    from the gross price and the charge components and compared with exact ``==``.
    """
    rule = "ss_net_to_seller_recompute"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_SETTLEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue
        with amount_guard(rule, out):
            gross = require_cents(
                f"unit[{_unit_id(unit)}].gross_sales_cents", unit.get("gross_sales_cents")
            )
            charges = total_settlement_charges(_charge_components(settlement))
            expected = net_to_seller(gross, charges)
            stated = require_cents(
                "settlement.net_to_seller_cents", settlement.get("net_to_seller_cents")
            )
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"settlements/{_unit_id(unit)}/net_to_seller_cents"),
                        f"unit {_unit_id(unit)} states net to seller of {fmt(stated)}; gross "
                        f"less settlement charges is {fmt(expected)} "
                        f"(off {fmt(stated - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} net-to-seller figures recompute")
        )
    return out


# --------------------------------------------------------------------------- #
# fee_ -- rate-derived fees and proforma variance
# --------------------------------------------------------------------------- #
@check("fee_listing_sales_rederives")
def check_fee_listing_sales_rederives(ctx: Context) -> list[Finding]:
    """The LISTING sales fee equals its proforma rate applied to gross sales.

    A rate-derived fee that was keyed can drift off its rate; re-derived at the
    proforma basis-point rate and compared with exact ``==``.
    """
    rule = "fee_listing_sales_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_SETTLEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue
        with amount_guard(rule, out):
            gross = require_cents(
                f"unit[{_unit_id(unit)}].gross_sales_cents", unit.get("gross_sales_cents")
            )
            rate = _bps(ctx.one(DOC_PROFORMA_ASSUMPTIONS), "listing_sales_fee_bps")
            expected = derived_fee(gross, rate)
            stated = require_cents(
                "settlement.listing_sales_fee_cents", settlement.get("listing_sales_fee_cents")
            )
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"settlements/{_unit_id(unit)}/listing_sales_fee_cents"),
                        f"unit {_unit_id(unit)} states an LISTING sales fee of {fmt(stated)}; "
                        f"{fmt_bps(rate)} of gross is {fmt(expected)} "
                        f"(off {fmt(stated - expected)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} LISTING sales fees re-derive"))
    return out


@check("fee_warranty_reserve_rederives")
def check_fee_warranty_reserve_rederives(ctx: Context) -> list[Finding]:
    """The warranty reserve equals its proforma rate applied to gross sales."""
    rule = "fee_warranty_reserve_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_SETTLEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue
        with amount_guard(rule, out):
            gross = require_cents(
                f"unit[{_unit_id(unit)}].gross_sales_cents", unit.get("gross_sales_cents")
            )
            rate = _bps(ctx.one(DOC_PROFORMA_ASSUMPTIONS), "warranty_reserve_bps")
            expected = derived_fee(gross, rate)
            stated = require_cents(
                "settlement.warranty_reserve_cents", settlement.get("warranty_reserve_cents")
            )
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"settlements/{_unit_id(unit)}/warranty_reserve_cents"),
                        f"unit {_unit_id(unit)} states a warranty reserve of {fmt(stated)}; "
                        f"{fmt_bps(rate)} of gross is {fmt(expected)} "
                        f"(off {fmt(stated - expected)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} warranty reserves re-derive"))
    return out


@check("fee_broker_commission_variance")
def check_fee_broker_commission_variance(ctx: Context) -> list[Finding]:
    """The booked broker commission is flagged where it varies from the proforma.

    Deliberately a FLAG, not a failure: a commission negotiated off the proforma
    rate is a business fact for a reviewer to confirm, not an arithmetic error.
    The assumption rate comes from the proforma and is applied to gross sales.
    """
    rule = "fee_broker_commission_variance"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_SETTLEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue
        with amount_guard(rule, out):
            gross = require_cents(
                f"unit[{_unit_id(unit)}].gross_sales_cents", unit.get("gross_sales_cents")
            )
            rate = _bps(ctx.one(DOC_PROFORMA_ASSUMPTIONS), "broker_commission_bps")
            assumed = apply_rate(gross, rate)
            stated = require_cents(
                "settlement.broker_commission_cents", settlement.get("broker_commission_cents")
            )
            checked += 1
            if stated != assumed:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"settlements/{_unit_id(unit)}/broker_commission_cents"),
                        f"unit {_unit_id(unit)} books a broker commission of {fmt(stated)}; the "
                        f"proforma assumption of {fmt_bps(rate)} is {fmt(assumed)} "
                        f"(variance {fmt(stated - assumed)}) -- confirm the negotiated rate",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} broker commissions match the proforma")
        )
    return out


@check("fee_concessions_within_assumption")
def check_fee_concessions_within_assumption(ctx: Context) -> list[Finding]:
    """Concessions above the proforma allowance are flagged for review.

    A threshold FLAG: concessions up to the assumed allowance are expected, but a
    concession above it eats into the proforma margin and is a business fact a
    reviewer should confirm. The allowance rate comes from the proforma.
    """
    rule = "fee_concessions_within_assumption"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_SETTLEMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        settlement = _settlement_for(ctx, _unit_id(unit))
        if settlement is None:
            continue
        with amount_guard(rule, out):
            gross = require_cents(
                f"unit[{_unit_id(unit)}].gross_sales_cents", unit.get("gross_sales_cents")
            )
            rate = _bps(ctx.one(DOC_PROFORMA_ASSUMPTIONS), "concessions_bps")
            allowance = apply_rate(gross, rate)
            stated = require_cents(
                "settlement.concessions_cents", settlement.get("concessions_cents")
            )
            checked += 1
            if stated > allowance:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"settlements/{_unit_id(unit)}/concessions_cents"),
                        f"unit {_unit_id(unit)} grants concessions of {fmt(stated)}; the "
                        f"proforma allowance of {fmt_bps(rate)} is {fmt(allowance)} "
                        f"(over by {fmt(stated - allowance)}) -- confirm the concession",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} concessions are within the allowance")
        )
    return out


# --------------------------------------------------------------------------- #
# rev_ -- revenue recognised in the close month
# --------------------------------------------------------------------------- #
@check("rev_recognized_in_coe_month")
def check_rev_recognized_in_coe_month(ctx: Context) -> list[Finding]:
    """Residential sales revenue is recognised in the unit's close-of-escrow month.

    Revenue is earned only at close of escrow, so its recognition month must be
    the month of the unit's COE date -- a date-gate, not a judgement.
    """
    rule = "rev_recognized_in_coe_month"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_REVENUE_SCHEDULE)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        coe = _parse_date(unit.get("coe_date"))
        if coe is None:
            continue  # unit_required_fields owns this
        revenue = _revenue_for(ctx, _unit_id(unit))
        if revenue is None:
            continue  # unit_artifacts_complete owns this
        checked += 1
        stated_month = _text(revenue, "recognized_month")
        expected = coe_month(coe)
        if stated_month != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entries/{_unit_id(unit)}/recognized_month"),
                    f"unit {_unit_id(unit)} recognises revenue in {stated_month!r}; close of "
                    f"escrow is {coe.isoformat()}, so it must land in {expected!r}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} revenue lines land in the close month")
        )
    return out


@check("rev_deferred_upgrade_reversed")
def check_rev_deferred_upgrade_reversed(ctx: Context) -> list[Finding]:
    """The deferred upgrade revenue reversed at closing equals the unit's balance.

    Upgrade revenue is deferred until closing and then reversed in full into
    income; the amount reversed must equal the unit's deferred balance to the cent.
    """
    rule = "rev_deferred_upgrade_reversed"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_REVENUE_SCHEDULE)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        revenue = _revenue_for(ctx, _unit_id(unit))
        if revenue is None:
            continue
        with amount_guard(rule, out):
            deferred = require_cents(
                f"unit[{_unit_id(unit)}].deferred_upgrade_cents",
                unit.get("deferred_upgrade_cents"),
            )
            reversed_ = require_cents(
                "revenue.deferred_upgrade_reversed_cents",
                revenue.get("deferred_upgrade_reversed_cents"),
            )
            checked += 1
            if reversed_ != deferred:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"entries/{_unit_id(unit)}/deferred_upgrade_reversed_cents"),
                        f"unit {_unit_id(unit)} reverses {fmt(reversed_)} of deferred upgrade "
                        f"revenue; the unit's deferred balance is {fmt(deferred)} "
                        f"(off {fmt(reversed_ - deferred)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} deferred-upgrade reversals tie")
        )
    return out


# --------------------------------------------------------------------------- #
# loan_ -- the loan release ties to the lender statement
# --------------------------------------------------------------------------- #
@check("loan_ending_recomputes")
def check_loan_ending_recomputes(ctx: Context) -> list[Finding]:
    """The loan ending balance rolls forward from beginning plus activity.

    ``ending = beginning + draws + interest & fees - bank remittance - paydowns``,
    re-derived and compared with exact ``==``.
    """
    rule = "loan_ending_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LOAN_RELEASE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        loan = _loan_for(ctx, _unit_id(unit))
        if loan is None:
            continue
        with amount_guard(rule, out):
            ending = loan_ending_balance(
                require_cents("loan.beginning_balance_cents", loan.get("beginning_balance_cents")),
                require_cents("loan.draws_cents", loan.get("draws_cents")),
                require_cents("loan.interest_fees_cents", loan.get("interest_fees_cents")),
                require_cents("loan.bank_remittance_cents", loan.get("bank_remittance_cents")),
                require_cents("loan.paydowns_cents", loan.get("paydowns_cents")),
            )
            stated = require_cents("loan.ending_balance_cents", loan.get("ending_balance_cents"))
            checked += 1
            if stated != ending:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"releases/{_unit_id(unit)}/ending_balance_cents"),
                        f"unit {_unit_id(unit)} states a loan ending balance of {fmt(stated)}; "
                        f"the roll-forward gives {fmt(ending)} (off {fmt(stated - ending)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} loan ending balances recompute")
        )
    return out


@check("loan_ties_lender_statement")
def check_loan_ties_lender_statement(ctx: Context) -> list[Finding]:
    """The loan ending balance ties to the lender's loan statement.

    The internal release schedule and the lender's statement must agree to the
    cent; a break here is coverage the developer thinks it released that the
    lender has not.
    """
    rule = "loan_ties_lender_statement"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LOAN_RELEASE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        loan = _loan_for(ctx, _unit_id(unit))
        if loan is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents("loan.ending_balance_cents", loan.get("ending_balance_cents"))
            lender = require_cents(
                "loan.lender_statement_ending_cents", loan.get("lender_statement_ending_cents")
            )
            checked += 1
            if stated != lender:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"releases/{_unit_id(unit)}/lender_statement_ending_cents"),
                        f"unit {_unit_id(unit)} carries a loan ending balance of {fmt(stated)}; "
                        f"the lender statement shows {fmt(lender)} (off {fmt(stated - lender)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} loan balances tie the lender statement")
        )
    return out


@check("loan_release_price_covered")
def check_loan_release_price_covered(ctx: Context) -> list[Finding]:
    """The bank remittance covers the unit's scheduled release price.

    A unit cannot be released from the loan for less than its release-schedule
    price, so the remittance to the bank must be at least that price. A threshold,
    compared with exact ``>=``.
    """
    rule = "loan_release_price_covered"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LOAN_RELEASE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        loan = _loan_for(ctx, _unit_id(unit))
        if loan is None:
            continue
        with amount_guard(rule, out):
            remittance = require_cents(
                "loan.bank_remittance_cents", loan.get("bank_remittance_cents")
            )
            release_price = require_cents(
                "loan.release_price_cents", loan.get("release_price_cents")
            )
            checked += 1
            if remittance < release_price:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"releases/{_unit_id(unit)}/bank_remittance_cents"),
                        f"unit {_unit_id(unit)} remits {fmt(remittance)} to the bank; the "
                        f"scheduled release price is {fmt(release_price)} "
                        f"(short {fmt(release_price - remittance)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} remittances cover the release price")
        )
    return out


# --------------------------------------------------------------------------- #
# cos_ -- cost-of-sale / margin relief recomputes
# --------------------------------------------------------------------------- #
@check("cos_margin_recompute")
def check_cos_margin_recompute(ctx: Context) -> list[Finding]:
    """Revised project profit and margin recompute from the base facts.

    ``revised profit = projected profit + carry costs`` and
    ``margin = revised profit / projected net revenue`` (floored basis points),
    each re-derived and compared with exact ``==``.
    """
    rule = "cos_margin_recompute"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COS_SCHEDULE)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        cos = _cos_for(ctx, _unit_id(unit))
        if cos is None:
            continue
        with amount_guard(rule, out):
            revised = revised_project_profit(
                require_cents("cos.projected_profit_cents", cos.get("projected_profit_cents")),
                require_cents("cos.carry_costs_cents", cos.get("carry_costs_cents")),
            )
            stated_revised = require_cents("cos.revised_profit_cents", cos.get("revised_profit_cents"))
            pnr = require_cents("cos.projected_net_revenue_cents", cos.get("projected_net_revenue_cents"))
            expected_margin = margin_bps(revised, pnr)
            stated_margin = require_cents("cos.margin_bps", cos.get("margin_bps"), unit="a basis-point rate")
            checked += 1
            if stated_revised != revised:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"entries/{_unit_id(unit)}/revised_profit_cents"),
                        f"unit {_unit_id(unit)} states a revised project profit of "
                        f"{fmt(stated_revised)}; projected profit plus carry costs is "
                        f"{fmt(revised)} (off {fmt(stated_revised - revised)})",
                    )
                )
            elif stated_margin != expected_margin:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"entries/{_unit_id(unit)}/margin_bps"),
                        f"unit {_unit_id(unit)} states a margin of {fmt_bps(stated_margin)}; "
                        f"revised profit over projected net revenue is {fmt_bps(expected_margin)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} margin figures recompute"))
    return out


@check("cos_prepaid_commission_relief_cap")
def check_cos_prepaid_commission_relief_cap(ctx: Context) -> list[Finding]:
    """Prepaid commission relieved is capped at the prepaid balance.

    Relief = ``MIN(commission earned, prepaid balance)``: a closing can relieve
    only the commission actually prepaid, so relieving more draws the prepaid
    account negative. Re-derived and compared with exact ``==``.
    """
    rule = "cos_prepaid_commission_relief_cap"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COS_SCHEDULE)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in _closed_units(ctx):
        cos = _cos_for(ctx, _unit_id(unit))
        if cos is None:
            continue
        with amount_guard(rule, out):
            commission_earned = require_cents(
                "cos.commission_earned_cents", cos.get("commission_earned_cents")
            )
            prepaid_balance = require_cents(
                f"unit[{_unit_id(unit)}].prepaid_balance_cents", unit.get("prepaid_balance_cents")
            )
            expected = prepaid_commission_relieved(commission_earned, prepaid_balance)
            stated = require_cents("cos.prepaid_relieved_cents", cos.get("prepaid_relieved_cents"))
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"entries/{_unit_id(unit)}/prepaid_relieved_cents"),
                        f"unit {_unit_id(unit)} relieves {fmt(stated)} of prepaid commission; "
                        f"MIN(earned {fmt(commission_earned)}, prepaid {fmt(prepaid_balance)}) "
                        f"is {fmt(expected)} (off {fmt(stated - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} prepaid-commission reliefs are capped")
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the units
# --------------------------------------------------------------------------- #
@check("rpt_closed_count_ties")
def check_rpt_closed_count_ties(ctx: Context) -> list[Finding]:
    """The report's closed-unit count ties the unit register.

    The count that reaches a controller is a count, and a count maintained beside
    the register rather than derived from it drifts the first time a unit closes
    and nobody re-adds the column.
    """
    rule = "rpt_closed_count_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_CLOSING_REPORT)
    if report is None or ctx.one(DOC_UNIT_REGISTER) is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "closing_report.closed_count", report.get("closed_count"), unit="a whole count"
        )
        recomputed = recompute_closed_count(ctx)
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "closed_count"),
                    f"the report states {stated} closed unit(s); the register has "
                    f"{recomputed}",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"the report's closed count of {recomputed} ties"
                )
            )
    return out


@check("rpt_net_to_seller_total_ties")
def check_rpt_net_to_seller_total_ties(ctx: Context) -> list[Finding]:
    """The report's total net to seller recomputes from the settlements.

    The portfolio total is re-derived from each closed unit's gross price and
    settlement charges and compared with exact ``==``, so the headline figure ties
    to the evidence rather than to a separately kept sum.
    """
    rule = "rpt_net_to_seller_total_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_CLOSING_REPORT)
    if report is None or ctx.one(DOC_SETTLEMENT_REGISTER) is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "closing_report.total_net_to_seller_cents", report.get("total_net_to_seller_cents")
        )
        recomputed = recompute_net_to_seller_total(ctx)
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "total_net_to_seller_cents"),
                    f"the report states a total net to seller of {fmt(stated)}; the "
                    f"settlements recompute {fmt(recomputed)} (off {fmt(stated - recomputed)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report's total net to seller of {fmt(recomputed)} ties",
                )
            )
    return out


@check("rpt_unit_tied_recomputes")
def check_rpt_unit_tied_recomputes(ctx: Context) -> list[Finding]:
    """Each closed unit's stated tie-out flag recomputes from its package.

    This is the control the engine exists for. The summary is a determination, and
    a determination not recomputed from the evidence is an assertion. The engine
    rebuilds every flag from the settlement, entry, revenue line, loan release and
    cost-of-sale entry, and compares.
    """
    rule = "rpt_unit_tied_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_CLOSING_SUMMARY)
    if summary is None or ctx.one(DOC_UNIT_REGISTER) is None:
        return []
    units = _unit_map(ctx)
    out: list[Finding] = []
    for row in _summary_rows(ctx):
        uid = _text(row, "unit_id")
        unit = units.get(uid or "")
        if unit is None:
            continue
        stated = row.get("tied")
        with amount_guard(rule, out):
            recomputed = recompute_unit_tied(ctx, unit)
            if recomputed != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"units/{uid}/tied"),
                        f"unit {uid} is summarised tied={stated}; recomputing from its "
                        f"closing package gives tied={recomputed}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every unit tie-out flag recomputes from its package"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one closing file."""
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
    """Analyze every ``.json`` closing file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of closing-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
