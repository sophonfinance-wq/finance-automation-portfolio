"""
Earnest-money deposit (EMD) trust control engine (READ-ONLY).
=============================================================

Loads each deposit file (a ``.json`` file produced by
:mod:`deposit_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **the pre-close deposit trust**: whether the internal
deposit ledger, the escrow agent's record and the construction-loan paydown
register describe the same money, unit by unit, to the cent. The settlement
statement of a fully-closed unit belongs to the close-of-escrow engine, and
the upgrade deposit's selection/pricing story belongs to the buyer-upgrades
engine; here the upgrade column is only the segregation counterpart that must
sum with earnest money to the cash that moved.

The shape of the problem
------------------------
A buyer's earnest money is receipted into escrow, split from any upgrade
deposit, swept to the construction loan as a principal paydown, and -- if the
buyer cancels -- decomposed into a retained termination fee, a refund, and a
reversal of the earlier paydown. Three failures hide inside that, and none of
them look wrong on any single page: the agent's record and the books disagree
on a unit; the sweep drifts from the ledger's own status column; and the
reconciliation summary carries variances and totals nobody recomputed.

The registry is organised around that:

1. ``set_`` -- is the deposit file complete?
2. ``led_`` -- is the deposit ledger itself sound?
3. ``seg_`` -- does every row's cash split into upgrade + earnest money?
4. ``tie_`` -- do ledger, escrow agent and loan paydowns tie three ways, per unit?
5. ``swp_`` -- does the sweep register match the ledger's own status column?
6. ``cxl_`` -- does every cancellation split, book and reverse correctly?
7. ``sts_`` -- is every deposit in exactly one known bucket, in scope?
8. ``bnk_`` -- do the segregated trust-bank balances recompute?
9. ``net_`` -- does the sales matrix net concessions as revenue, exactly?
10. ``rpt_`` -- does the reconciliation summary recompute from the evidence?

Design notes
------------
- **Strictly read-only.** Deposit files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every equality is exact ``==``; a variance
  of one cent is a variance.
- **One reconciliation kernel.** Controls and the generator share
  :mod:`deposit_engine.reconcile`, so a stated determination cannot disagree
  with the logic that produced it.
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
    CONCESSION_REVENUE_ACCOUNT,
    DOC_CANCELLATION_REGISTER,
    DOC_DEPOSIT_LEDGER,
    DOC_ESCROW_STATEMENT,
    DOC_PAYDOWN_REGISTER,
    DOC_RECON_SUMMARY,
    DOC_SALES_MATRIX,
    DOC_TRUST_BALANCES,
    DOC_TYPES,
    FORFEITURE_ACCOUNT,
    KIND_PAYDOWN,
    KIND_REVERSAL,
    PAYDOWN_KINDS,
    STATE_CANCELLED,
    STATES,
    STATUS_ALREADY_POSTED,
    STATUS_BUCKETS,
    STATUS_NEED_TO_POST,
    STATUS_UNIT_CLOSED,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents
from .reconcile import (
    DepositFacts,
    expected_agent_em,
    expected_net_paydown,
    expected_upgrade_bank,
    is_swept,
    net_sale,
    unit_variance,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~deposit_engine.money.AmountInvalidError` as a finding."""
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
# Deposit-file helpers
# --------------------------------------------------------------------------- #
def _deposits(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DEPOSIT_LEDGER), "deposits")


def _deposit_id(row: dict[str, Any]) -> str:
    value = row.get("deposit_id")
    return value if isinstance(value, str) and value else "?"


def _deposit_map(ctx: Context) -> dict[str, dict[str, Any]]:
    """Deposits keyed by id, first occurrence winning.

    First-wins is deliberate: a duplicated id is ``led_unique_ids``'s finding,
    and deduplicating here keeps the duplicate from silently doubling every
    recomputed sum downstream of it.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in _deposits(ctx):
        did = _deposit_id(row)
        if did != "?" and did not in out:
            out[did] = row
    return out


def _row_status_valid(row: dict[str, Any]) -> bool:
    return _text(row, "status") in STATUS_BUCKETS and _text(row, "state") in STATES


def _deposit_facts(ctx: Context) -> list[DepositFacts]:
    """The deduplicated ledger reduced to kernel facts.

    Rows whose status or state is not in the known vocabulary are excluded --
    ``sts_valid_bucket`` owns them, and a row the kernel cannot classify must
    not silently shift every expected sum it would have contributed to.

    Raises :class:`AmountInvalidError` if a row's earnest-money or upgrade
    amount is not integer cents; the calling control contains that.
    """
    facts: list[DepositFacts] = []
    for did, row in sorted(_deposit_map(ctx).items()):
        if not _row_status_valid(row):
            continue
        facts.append(
            DepositFacts(
                deposit_id=did,
                unit_id=_text(row, "unit_id") or "?",
                em_cents=require_cents(f"deposit[{did}].em_cents", row.get("em_cents")),
                upgrade_cents=require_cents(
                    f"deposit[{did}].upgrade_cents", row.get("upgrade_cents")
                ),
                status=_text(row, "status") or "?",
                cancelled=_text(row, "state") == STATE_CANCELLED,
            )
        )
    return facts


def _ledger_units(ctx: Context) -> set[str]:
    """Every unit named by any ledger row, valid or not."""
    return {u for row in _deposits(ctx) if (u := _text(row, "unit_id"))}


def _unit_has_invalid_row(ctx: Context, unit_id: str) -> bool:
    return any(
        _text(row, "unit_id") == unit_id and not _row_status_valid(row)
        for row in _deposits(ctx)
    )


def _agent_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ESCROW_STATEMENT), "entries")


def _agent_rows_by_unit(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _agent_entries(ctx):
        unit = _text(row, "unit_id")
        if unit and unit not in out:
            out[unit] = row
    return out


def _paydowns(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PAYDOWN_REGISTER), "movements")


def _paydown_id(row: dict[str, Any]) -> str:
    value = row.get("paydown_id")
    return value if isinstance(value, str) and value else "?"


def _movements_for(ctx: Context, deposit_id: str, kind: str) -> list[dict[str, Any]]:
    return [
        m
        for m in _paydowns(ctx)
        if _text(m, "deposit_id") == deposit_id and _text(m, "kind") == kind
    ]


def _cancellations(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CANCELLATION_REGISTER), "cancellations")


def _cancellation_id(row: dict[str, Any]) -> str:
    value = row.get("cancellation_id")
    return value if isinstance(value, str) and value else "?"


def _sales_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SALES_MATRIX), "units")


def _paydown_preconditions_ok(ctx: Context, unit_id: str, facts: list[DepositFacts]) -> bool:
    """Whether the loan leg of ``unit_id`` is structurally sound enough to tie.

    The per-unit loan tie-out is an *amount* control; when a sweep is missing,
    premature, orphaned or unreversed, the ``swp_``/``cxl_`` controls own the
    break, and re-flagging the same unit here would report one defect twice.
    """
    known = _deposit_map(ctx)
    for m in _paydowns(ctx):
        if _text(m, "unit_id") != unit_id:
            continue
        did = _text(m, "deposit_id")
        if did not in known or _text(m, "kind") not in PAYDOWN_KINDS:
            return False
    for d in facts:
        if d.unit_id != unit_id:
            continue
        paydown_count = len(_movements_for(ctx, d.deposit_id, KIND_PAYDOWN))
        reversal_count = len(_movements_for(ctx, d.deposit_id, KIND_REVERSAL))
        if is_swept(d):
            if paydown_count != 1:
                return False
        elif paydown_count != 0:
            return False
        if d.cancelled and is_swept(d):
            if reversal_count != 1:
                return False
        elif reversal_count != 0:
            return False
    return True


# --------------------------------------------------------------------------- #
# Shared recomputations (used by the controls and by the generator)
# --------------------------------------------------------------------------- #
def recompute_recon_units(ctx: Context) -> list[dict[str, Any]]:
    """The per-unit reconciliation rows re-derived from the evidence.

    One row per unit named by either side -- the ledger or the agent's
    statement -- with the variance and exception flag recomputed through the
    kernel. Shared with the generator, so the stated summary can be tied to it.

    Raises :class:`AmountInvalidError` on a malformed amount; the calling
    control contains that.
    """
    facts = _deposit_facts(ctx)
    agent_rows = _agent_rows_by_unit(ctx)
    units = sorted(_ledger_units(ctx) | set(agent_rows))
    out: list[dict[str, Any]] = []
    for unit in units:
        row = agent_rows.get(unit)
        agent_cents = (
            require_cents(
                f"escrow_entry[{unit}].agent_deposit_cents",
                row.get("agent_deposit_cents"),
            )
            if row is not None
            else None
        )
        variance = unit_variance(agent_cents, expected_agent_em(facts, unit))
        out.append(
            {
                "unit_id": unit,
                "variance_cents": variance,
                "exception_flag": variance != 0,
            }
        )
    return out


def recompute_bucket_totals(ctx: Context) -> dict[str, int]:
    """Earnest money of active deposits, totalled per posting bucket."""
    totals = {bucket: 0 for bucket in STATUS_BUCKETS}
    for d in _deposit_facts(ctx):
        if not d.cancelled:
            totals[d.status] += d.em_cents
    return totals


def recompute_upgrade_bank(ctx: Context) -> int:
    """The segregated upgrade-deposit bank balance the ledger supports."""
    return expected_upgrade_bank(_deposit_facts(ctx))


def recompute_forfeiture_income(ctx: Context) -> int:
    """Forfeiture income to date: the sum of retained termination fees."""
    return sum(
        require_cents(
            f"cancellation[{_cancellation_id(row)}].termination_fee_cents",
            row.get("termination_fee_cents"),
        )
        for row in _cancellations(ctx)
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the deposit file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the deposit file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} deposit artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; the whole reconciliation "
                f"is drawn at that ledger cut-off",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# led_ -- the deposit ledger itself
# --------------------------------------------------------------------------- #
@check("led_unique_ids")
def check_led_unique_ids(ctx: Context) -> list[Finding]:
    """No deposit id appears twice.

    The deposit id joins the ledger to every paydown and every cancellation
    row. A duplicate makes a principal payment ambiguous about which receipt it
    applied, and would double every sum the reconciliation recomputes.
    """
    rule = "led_unique_ids"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if ledger is None:
        return []
    seen: dict[str, int] = {}
    for row in _deposits(ctx):
        seen[_deposit_id(row)] = seen.get(_deposit_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(ledger, f"deposits/{did}"),
            f"deposit id {did} appears {count} times; a paydown or cancellation that "
            f"names it cannot be attributed to one receipt",
        )
        for did, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} deposit ids are unique")
        )
    return out


@check("led_required_fields")
def check_led_required_fields(ctx: Context) -> list[Finding]:
    """Every ledger row carries the fields the reconciliation reads.

    A deposit with no receipt date, unit or buyer is a cash movement with no
    provenance; a row with no amounts is not a deposit at all.
    """
    rule = "led_required_fields"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if ledger is None:
        return []
    text_fields = ("deposit_id", "unit_id", "buyer", "receipt_date", "status", "state")
    amount_fields = ("amount_cents", "upgrade_cents", "em_cents")
    out: list[Finding] = []
    for row in _deposits(ctx):
        missing = [f for f in text_fields if not _text(row, f)]
        missing += [f for f in amount_fields if row.get(f) is None]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"deposits/{_deposit_id(row)}"),
                    f"deposit {_deposit_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_deposits(ctx))} ledger rows carry their required fields",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# seg_ -- the segregation identity
# --------------------------------------------------------------------------- #
@check("seg_amount_splits")
def check_seg_amount_splits(ctx: Context) -> list[Finding]:
    """Every row's cash amount equals its upgrade + earnest-money split.

    The deposit amount is the cash that moved; the two components are the GL
    streams it must be carried in. A row whose components do not sum to the
    cash has invented or lost money between the bank and the books.
    """
    rule = "seg_amount_splits"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for did, row in sorted(_deposit_map(ctx).items()):
        with amount_guard(rule, out):
            amount = require_cents(f"deposit[{did}].amount_cents", row.get("amount_cents"))
            upgrade = require_cents(f"deposit[{did}].upgrade_cents", row.get("upgrade_cents"))
            em = require_cents(f"deposit[{did}].em_cents", row.get("em_cents"))
            checked += 1
            if amount != upgrade + em:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger, f"deposits/{did}/amount_cents"),
                        f"deposit {did} moved {fmt(amount)} of cash but splits into "
                        f"{fmt(upgrade)} upgrade + {fmt(em)} earnest money = "
                        f"{fmt(upgrade + em)}; the segregation identity does not hold",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} deposits split exactly into upgrade + earnest money",
            )
        )
    return out


@check("seg_components_nonnegative")
def check_seg_components_nonnegative(ctx: Context) -> list[Finding]:
    """Neither component of the split is negative.

    A negative component can make any split "sum" while moving money between
    the two GL streams; the identity is only meaningful over non-negative
    pieces.
    """
    rule = "seg_components_nonnegative"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for did, row in sorted(_deposit_map(ctx).items()):
        with amount_guard(rule, out):
            upgrade = require_cents(f"deposit[{did}].upgrade_cents", row.get("upgrade_cents"))
            em = require_cents(f"deposit[{did}].em_cents", row.get("em_cents"))
            checked += 1
            for name, value in (("upgrade_cents", upgrade), ("em_cents", em)):
                if value < 0:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(ledger, f"deposits/{did}/{name}"),
                            f"deposit {did} carries {name} of {fmt(value)}; a negative "
                            f"component fakes the segregation identity by moving money "
                            f"between the two deposit streams",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} deposits carry non-negative split components",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# tie_ -- the three-way reconciliation
# --------------------------------------------------------------------------- #
@check("tie_agent_variance_zero")
def check_tie_agent_variance_zero(ctx: Context) -> list[Finding]:
    """The agent's recorded earnest money equals the books, per unit, exactly.

    This is the control the engine exists for. Variance is agent-minus-books
    and zero is the only passing value: a positive variance is money the agent
    holds that the books never captured, a negative one is a release the books
    claim that the agent never recorded.
    """
    rule = "tie_agent_variance_zero"
    _sev(rule, Status.FAIL)
    statement = ctx.one(DOC_ESCROW_STATEMENT)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if statement is None or ledger is None:
        return []
    ledger_units = _ledger_units(ctx)
    out: list[Finding] = []
    checked = 0
    for unit, row in sorted(_agent_rows_by_unit(ctx).items()):
        if unit not in ledger_units:
            continue  # tie_agent_completeness owns this
        if _unit_has_invalid_row(ctx, unit):
            continue  # sts_valid_bucket owns this
        with amount_guard(rule, out):
            agent_cents = require_cents(
                f"escrow_entry[{unit}].agent_deposit_cents",
                row.get("agent_deposit_cents"),
            )
            facts = _deposit_facts(ctx)
            expected = expected_agent_em(facts, unit)
            if expected == 0:
                continue  # sts_closed_excluded_from_agent owns this
            checked += 1
            variance = unit_variance(agent_cents, expected)
            if variance != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"entries/{unit}/agent_deposit_cents"),
                        f"unit {unit}: the escrow agent records {fmt(agent_cents)} of "
                        f"earnest money; the deposit ledger supports {fmt(expected)} "
                        f"(variance {fmt(variance)}); zero is the only passing value",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} agent-held units reconcile to the ledger at zero variance",
            )
        )
    return out


@check("tie_agent_completeness")
def check_tie_agent_completeness(ctx: Context) -> list[Finding]:
    """Every unit on the agent's statement exists in the deposit ledger.

    A deposit on the agent's side with nothing on our books is the classic
    completeness gap: real buyer money, held in escrow, that the accounting
    records never captured at all.
    """
    rule = "tie_agent_completeness"
    _sev(rule, Status.FAIL)
    statement = ctx.one(DOC_ESCROW_STATEMENT)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if statement is None or ledger is None:
        return []
    ledger_units = _ledger_units(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(statement, f"entries/{unit}"),
            f"the escrow agent holds earnest money for unit {unit}, which has no "
            f"deposit on the ledger at all; the receipt was never booked",
        )
        for unit in sorted(_agent_rows_by_unit(ctx))
        if unit not in ledger_units
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every unit on the agent's statement has a deposit on the ledger",
            )
        )
    return out


@check("tie_ledger_completeness")
def check_tie_ledger_completeness(ctx: Context) -> list[Finding]:
    """Every unit the books say is in escrow appears on the agent's statement.

    A booked pre-close deposit the agent does not hold means the money left
    escrow while the books still carry it -- an over-release, invisible until
    the closing that expected the funds.
    """
    rule = "tie_ledger_completeness"
    _sev(rule, Status.FAIL)
    statement = ctx.one(DOC_ESCROW_STATEMENT)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if statement is None or ledger is None:
        return []
    agent_units = set(_agent_rows_by_unit(ctx))
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        facts = _deposit_facts(ctx)
        for unit in sorted({d.unit_id for d in facts}):
            expected = expected_agent_em(facts, unit)
            if expected == 0:
                continue
            checked += 1
            if unit not in agent_units:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"entries/{unit}"),
                        f"the ledger carries {fmt(expected)} of pre-close earnest money "
                        f"for unit {unit}, but the escrow agent's statement does not "
                        f"list the unit; the funds have left escrow on paper only",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} units the ledger holds in escrow appear on the "
                f"agent's statement",
            )
        )
    return out


@check("tie_loan_leg_zero")
def check_tie_loan_leg_zero(ctx: Context) -> list[Finding]:
    """Net loan principal paydowns equal the swept earnest money, per unit.

    The third leg of the three-way tie-out: for every unit, the paydown
    register's net principal (paydowns minus reversals) must equal the earnest
    money the ledger says was swept. Units whose sweep structure is broken are
    left to the ``swp_``/``cxl_`` controls that own those breaks.
    """
    rule = "tie_loan_leg_zero"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYDOWN_REGISTER)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if register is None or ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for unit in sorted(_ledger_units(ctx)):
        if _unit_has_invalid_row(ctx, unit):
            continue  # sts_valid_bucket owns this
        with amount_guard(rule, out):
            facts = _deposit_facts(ctx)
            if not _paydown_preconditions_ok(ctx, unit, facts):
                continue  # swp_ / cxl_ controls own the structural break
            net = 0
            for m in _paydowns(ctx):
                if _text(m, "unit_id") != unit:
                    continue
                principal = require_cents(
                    f"movement[{_paydown_id(m)}].principal_cents",
                    m.get("principal_cents"),
                )
                net += principal if _text(m, "kind") == KIND_PAYDOWN else -principal
            expected = expected_net_paydown(facts, unit)
            checked += 1
            if net != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"movements/{unit}"),
                        f"unit {unit}: the loan register nets {fmt(net)} of principal "
                        f"paydown; the ledger's swept earnest money supports "
                        f"{fmt(expected)} (variance {fmt(net - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} units' net loan paydowns equal their swept earnest money",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# swp_ -- the sweep register against the ledger's own status column
# --------------------------------------------------------------------------- #
@check("swp_posted_has_paydown")
def check_swp_posted_has_paydown(ctx: Context) -> list[Finding]:
    """Every swept deposit has exactly one principal paydown behind it.

    A deposit marked posted (or carried through a closing) with no paydown row
    is a status the loan never saw; two paydown rows for one receipt is the
    same money applied twice.
    """
    rule = "swp_posted_has_paydown"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYDOWN_REGISTER)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if register is None or ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        for d in _deposit_facts(ctx):
            if not is_swept(d):
                continue
            checked += 1
            count = len(_movements_for(ctx, d.deposit_id, KIND_PAYDOWN))
            if count != 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"movements/{d.deposit_id}"),
                        f"deposit {d.deposit_id} (unit {d.unit_id}) is marked "
                        f"{d.status} but the loan register carries {count} paydown "
                        f"row(s) for it; a swept deposit has exactly one",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} swept deposits carry exactly one principal paydown",
            )
        )
    return out


@check("swp_paydown_has_deposit")
def check_swp_paydown_has_deposit(ctx: Context) -> list[Finding]:
    """Every loan-register movement joins a ledger deposit, coherently.

    An orphan principal payment is loan money moving with no receipt behind
    it; a movement of unknown kind, or one naming a different unit than its
    deposit, cannot be tied to anything.
    """
    rule = "swp_paydown_has_deposit"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYDOWN_REGISTER)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if register is None or ledger is None:
        return []
    known = _deposit_map(ctx)
    out: list[Finding] = []
    for m in _paydowns(ctx):
        mid = _paydown_id(m)
        did = _text(m, "deposit_id")
        kind = _text(m, "kind")
        if did not in known:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"movements/{mid}/deposit_id"),
                    f"movement {mid} names deposit {did!r}, which is not on the "
                    f"ledger; principal moved with no receipt behind it",
                )
            )
            continue
        if kind not in PAYDOWN_KINDS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"movements/{mid}/kind"),
                    f"movement {mid} is of kind {kind!r}, which is not one of "
                    f"{PAYDOWN_KINDS}; it cannot be netted into the loan leg",
                )
            )
        if _text(m, "unit_id") != _text(known[did], "unit_id"):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"movements/{mid}/unit_id"),
                    f"movement {mid} names unit {_text(m, 'unit_id')!r} but its "
                    f"deposit {did} belongs to unit {_text(known[did], 'unit_id')!r}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_paydowns(ctx))} loan movements join a ledger deposit coherently",
            )
        )
    return out


@check("swp_need_to_post_not_swept")
def check_swp_need_to_post_not_swept(ctx: Context) -> list[Finding]:
    """A deposit still marked need-to-post has no paydown behind it.

    The inverse drift of a missing sweep: the loan was paid down but the
    ledger still queues the deposit for posting, so the next posting run will
    apply the same money a second time.
    """
    rule = "swp_need_to_post_not_swept"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYDOWN_REGISTER)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if register is None or ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        for d in _deposit_facts(ctx):
            if is_swept(d):
                continue
            checked += 1
            count = len(_movements_for(ctx, d.deposit_id, KIND_PAYDOWN))
            if count:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"movements/{d.deposit_id}"),
                        f"deposit {d.deposit_id} (unit {d.unit_id}) is still marked "
                        f"{d.status} yet the loan register already carries {count} "
                        f"paydown row(s) for it; the next posting run would sweep the "
                        f"same money twice",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} unswept deposits have no paydown behind them",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cxl_ -- the cancellation / forfeiture split gate
# --------------------------------------------------------------------------- #
@check("cxl_row_joins")
def check_cxl_row_joins(ctx: Context) -> list[Finding]:
    """Cancellation rows and cancelled deposits pair one-to-one.

    A cancellation row for a deposit that is not cancelled (or does not exist)
    splits money that never left; a cancelled deposit with no row is a buyer
    walked away with no record of where the deposit went.
    """
    rule = "cxl_row_joins"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CANCELLATION_REGISTER)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if register is None or ledger is None:
        return []
    known = _deposit_map(ctx)
    out: list[Finding] = []
    row_count: dict[str, int] = {}
    for row in _cancellations(ctx):
        cid = _cancellation_id(row)
        did = _text(row, "deposit_id")
        if did is None or did not in known:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cancellations/{cid}/deposit_id"),
                    f"cancellation {cid} names deposit {did!r}, which is not on the "
                    f"ledger; it splits money that was never receipted",
                )
            )
            continue
        row_count[did] = row_count.get(did, 0) + 1
        if _text(known[did], "state") != STATE_CANCELLED:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cancellations/{cid}/deposit_id"),
                    f"cancellation {cid} names deposit {did}, which the ledger still "
                    f"carries as {_text(known[did], 'state')!r}; only a cancelled "
                    f"deposit passes the split gate",
                )
            )
    for did, row in sorted(known.items()):
        if _text(row, "state") == STATE_CANCELLED and row_count.get(did, 0) != 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cancellations/{did}"),
                    f"cancelled deposit {did} has {row_count.get(did, 0)} cancellation "
                    f"row(s); every cancelled buyer has exactly one forfeiture split",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "cancellation rows and cancelled deposits pair one-to-one",
            )
        )
    return out


@check("cxl_split_sums")
def check_cxl_split_sums(ctx: Context) -> list[Finding]:
    """Termination fee + refund equals the cancelled earnest money, exactly.

    The split is the whole of the gate: every cent of the walked-away buyer's
    earnest money is either retained as forfeiture income or refunded, and a
    split that does not sum has quietly created or destroyed deposit money.
    """
    rule = "cxl_split_sums"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CANCELLATION_REGISTER)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if register is None or ledger is None:
        return []
    known = _deposit_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _cancellations(ctx):
        cid = _cancellation_id(row)
        did = _text(row, "deposit_id")
        if did is None or did not in known:
            continue  # cxl_row_joins owns this
        if _text(known[did], "state") != STATE_CANCELLED:
            continue  # cxl_row_joins owns this
        with amount_guard(rule, out):
            em = require_cents(f"deposit[{did}].em_cents", known[did].get("em_cents"))
            fee = require_cents(
                f"cancellation[{cid}].termination_fee_cents",
                row.get("termination_fee_cents"),
            )
            refund = require_cents(
                f"cancellation[{cid}].refund_cents", row.get("refund_cents")
            )
            checked += 1
            if fee + refund != em:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"cancellations/{cid}/termination_fee_cents"),
                        f"cancellation {cid}: retained fee {fmt(fee)} + refund "
                        f"{fmt(refund)} = {fmt(fee + refund)} does not account for the "
                        f"{fmt(em)} earnest money of deposit {did} "
                        f"(difference {fmt(fee + refund - em)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} forfeiture splits sum exactly to the cancelled deposit",
            )
        )
    return out


@check("cxl_reversal_matches_sweep")
def check_cxl_reversal_matches_sweep(ctx: Context) -> list[Finding]:
    """A cancelled deposit's earlier loan paydown is reversed, exactly once.

    If the deposit had been swept before the buyer cancelled, the construction
    loan is carrying a paydown funded by money that must now be refunded or
    retained -- so exactly one reversal of exactly that amount must exist. A
    never-swept cancellation must have no reversal, and no active deposit may
    have one at all.
    """
    rule = "cxl_reversal_matches_sweep"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYDOWN_REGISTER)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if register is None or ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        for d in _deposit_facts(ctx):
            reversals = _movements_for(ctx, d.deposit_id, KIND_REVERSAL)
            if d.cancelled and is_swept(d):
                checked += 1
                if len(reversals) != 1:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"movements/{d.deposit_id}"),
                            f"cancelled deposit {d.deposit_id} (unit {d.unit_id}) was "
                            f"swept to the loan but the register carries "
                            f"{len(reversals)} reversal row(s); its {fmt(d.em_cents)} "
                            f"paydown must be reversed exactly once",
                        )
                    )
                    continue
                principal = require_cents(
                    f"movement[{_paydown_id(reversals[0])}].principal_cents",
                    reversals[0].get("principal_cents"),
                )
                if principal != d.em_cents:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                register,
                                f"movements/{_paydown_id(reversals[0])}/principal_cents",
                            ),
                            f"cancelled deposit {d.deposit_id} swept {fmt(d.em_cents)} "
                            f"to the loan but the reversal unwinds {fmt(principal)} "
                            f"(short {fmt(d.em_cents - principal)})",
                        )
                    )
            elif reversals:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register, f"movements/{_paydown_id(reversals[0])}"
                        ),
                        f"deposit {d.deposit_id} (unit {d.unit_id}) was never swept as "
                        f"a cancelled deposit, yet the register carries "
                        f"{len(reversals)} reversal row(s) for it",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} swept cancellations reverse their paydown exactly",
            )
        )
    return out


@check("cxl_fee_account")
def check_cxl_fee_account(ctx: Context) -> list[Finding]:
    """Every retained termination fee is booked to the forfeitures account.

    The fee is income to the seller. Booked anywhere else -- above all to a
    construction cost code -- it hides forfeiture income inside job cost and
    understates both revenue and cost at once.
    """
    rule = "cxl_fee_account"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CANCELLATION_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _cancellations(ctx):
        cid = _cancellation_id(row)
        account = _text(row, "fee_account")
        if account != FORFEITURE_ACCOUNT:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cancellations/{cid}/fee_account"),
                    f"cancellation {cid} books its retained fee to {account!r}; a "
                    f"termination fee is forfeiture income and belongs in "
                    f"{FORFEITURE_ACCOUNT!r}, never a cost code",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_cancellations(ctx))} retained fees are booked to "
                f"{FORFEITURE_ACCOUNT!r}",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# sts_ -- status completeness and scope
# --------------------------------------------------------------------------- #
@check("sts_valid_bucket")
def check_sts_valid_bucket(ctx: Context) -> list[Finding]:
    """Every deposit sits in exactly one known bucket and lifecycle state.

    The status column is what drives every expected sum -- the agent's scope,
    the loan leg, the trust bank. A deposit in an unknown bucket cannot be
    placed on any side of the reconciliation, so it is excluded from all of
    them and reported here instead.
    """
    rule = "sts_valid_bucket"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    for row in _deposits(ctx):
        did = _deposit_id(row)
        status = _text(row, "status")
        state = _text(row, "state")
        if status not in STATUS_BUCKETS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"deposits/{did}/status"),
                    f"deposit {did} carries status {status!r}, which is not one of "
                    f"{STATUS_BUCKETS}; it cannot be placed in any reconciliation "
                    f"bucket",
                )
            )
        if state not in STATES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"deposits/{did}/state"),
                    f"deposit {did} carries state {state!r}, which is not one of "
                    f"{STATES}; the split gate cannot classify it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_deposits(ctx))} deposits sit in exactly one known bucket",
            )
        )
    return out


@check("sts_closed_excluded_from_agent")
def check_sts_closed_excluded_from_agent(ctx: Context) -> list[Finding]:
    """The agent's open-escrow statement carries only pre-close units.

    Deliberately a FLAG, not a failure: money is not misstated, but a unit
    whose deposits have all closed or cancelled and that still shows on the
    agent's open statement is a stale escrow -- and the fully-closed unit's
    settlement tie-out belongs to the close-of-escrow engine, not here.
    """
    rule = "sts_closed_excluded_from_agent"
    _sev(rule, Status.FLAG)
    statement = ctx.one(DOC_ESCROW_STATEMENT)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if statement is None or ledger is None:
        return []
    ledger_units = _ledger_units(ctx)
    out: list[Finding] = []
    checked = 0
    for unit in sorted(_agent_rows_by_unit(ctx)):
        if unit not in ledger_units:
            continue  # tie_agent_completeness owns this
        if _unit_has_invalid_row(ctx, unit):
            continue  # sts_valid_bucket owns this
        with amount_guard(rule, out):
            checked += 1
            if expected_agent_em(_deposit_facts(ctx), unit) == 0:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(statement, f"entries/{unit}"),
                        f"unit {unit} still appears on the agent's open-escrow "
                        f"statement, but every deposit the ledger carries for it has "
                        f"closed or cancelled; the escrow is stale and belongs to the "
                        f"close-of-escrow handoff",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} units on the agent's statement are pre-close",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# bnk_ -- the segregated trust-account balances
# --------------------------------------------------------------------------- #
@check("bnk_upgrade_bank_ties")
def check_bnk_upgrade_bank_ties(ctx: Context) -> list[Finding]:
    """The segregated upgrade-deposit bank balance recomputes from the ledger.

    The upgrade bank is a trust of buyer money: its stated balance must equal
    the upgrade portion of every active, unclosed deposit, to the cent. A
    shortfall is buyer money spent early; an excess is cash nobody can
    attribute to a buyer.
    """
    rule = "bnk_upgrade_bank_ties"
    _sev(rule, Status.FAIL)
    trust = ctx.one(DOC_TRUST_BALANCES)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if trust is None or ledger is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "trust.upgrade_bank_balance_cents", trust.get("upgrade_bank_balance_cents")
        )
        derived = recompute_upgrade_bank(ctx)
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(trust, "upgrade_bank_balance_cents"),
                    f"the segregated upgrade-deposit bank states {fmt(stated)}; the "
                    f"ledger's active pre-close upgrade deposits support "
                    f"{fmt(derived)} (variance {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the upgrade-deposit bank balance of {fmt(stated)} ties the ledger",
                )
            )
    return out


@check("bnk_forfeiture_income_ties")
def check_bnk_forfeiture_income_ties(ctx: Context) -> list[Finding]:
    """Forfeiture income to date recomputes from the cancellation register.

    Every retained termination fee lands in the forfeitures account, so the
    account's stated balance is exactly the sum of the fees -- a figure
    maintained beside the register rather than derived from it drifts the
    first time a cancellation is booked and nobody re-adds the column.
    """
    rule = "bnk_forfeiture_income_ties"
    _sev(rule, Status.FAIL)
    trust = ctx.one(DOC_TRUST_BALANCES)
    register = ctx.one(DOC_CANCELLATION_REGISTER)
    if trust is None or register is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "trust.forfeiture_income_cents", trust.get("forfeiture_income_cents")
        )
        derived = recompute_forfeiture_income(ctx)
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(trust, "forfeiture_income_cents"),
                    f"forfeiture income is stated as {fmt(stated)}; the cancellation "
                    f"register's retained fees sum to {fmt(derived)} "
                    f"(variance {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"forfeiture income of {fmt(stated)} ties the cancellation register",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# net_ -- concession netting on the sales matrix
# --------------------------------------------------------------------------- #
@check("net_sale_recomputes")
def check_net_sale_recomputes(ctx: Context) -> list[Finding]:
    """Each unit's net sale price equals sales price plus concession, exactly.

    The net figure is what revenue recognition and the deposit percentage are
    measured against; a net that does not recompute means someone edited one
    column without the other.
    """
    rule = "net_sale_recomputes"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_SALES_MATRIX)
    if matrix is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _sales_rows(ctx):
        unit = _text(row, "unit_id") or "?"
        with amount_guard(rule, out):
            sales = require_cents(f"sale[{unit}].sales_price_cents", row.get("sales_price_cents"))
            concession = require_cents(
                f"sale[{unit}].concession_cents", row.get("concession_cents")
            )
            stated = require_cents(f"sale[{unit}].net_sale_cents", row.get("net_sale_cents"))
            checked += 1
            derived = net_sale(sales, concession)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(matrix, f"units/{unit}/net_sale_cents"),
                        f"unit {unit} states a net sale of {fmt(stated)}; sales price "
                        f"{fmt(sales)} plus concession {fmt(concession)} recomputes to "
                        f"{fmt(derived)} (variance {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} net sale prices recompute from price plus concession",
            )
        )
    return out


@check("net_concession_sign")
def check_net_concession_sign(ctx: Context) -> list[Finding]:
    """A concession is stored as a non-positive amount.

    The sign convention is load-bearing: concessions reduce revenue, and a
    positive concession would silently *raise* the net sale price while still
    passing the recompute identity.
    """
    rule = "net_concession_sign"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_SALES_MATRIX)
    if matrix is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _sales_rows(ctx):
        unit = _text(row, "unit_id") or "?"
        with amount_guard(rule, out):
            concession = require_cents(
                f"sale[{unit}].concession_cents", row.get("concession_cents")
            )
            checked += 1
            if concession > 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(matrix, f"units/{unit}/concession_cents"),
                        f"unit {unit} carries a concession of {fmt(concession)}; a "
                        f"concession reduces revenue and is stored as a non-positive "
                        f"amount, so a positive one inflates the net sale price",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} concessions are stored as non-positive reductions",
            )
        )
    return out


@check("net_concession_account")
def check_net_concession_account(ctx: Context) -> list[Finding]:
    """Every concession is booked against revenue, never a construction cost.

    A concession routed to job cost overstates both revenue and construction
    cost by the same amount -- the margin is right and both lines are wrong,
    which is exactly why nobody notices.
    """
    rule = "net_concession_account"
    _sev(rule, Status.FAIL)
    matrix = ctx.one(DOC_SALES_MATRIX)
    if matrix is None:
        return []
    out: list[Finding] = []
    for row in _sales_rows(ctx):
        unit = _text(row, "unit_id") or "?"
        account = _text(row, "concession_account")
        if account != CONCESSION_REVENUE_ACCOUNT:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(matrix, f"units/{unit}/concession_account"),
                    f"unit {unit} books its concession to {account!r}; a concession "
                    f"is a reduction of revenue and belongs in "
                    f"{CONCESSION_REVENUE_ACCOUNT!r}, never a construction cost code",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_sales_rows(ctx))} concessions are booked against revenue",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the reconciliation summary recomputes from the evidence
# --------------------------------------------------------------------------- #
@check("rpt_unit_variance_recomputes")
def check_rpt_unit_variance_recomputes(ctx: Context) -> list[Finding]:
    """Each unit's stated variance recomputes from the ledger and the agent.

    The summary is a determination, and a determination that is not recomputed
    from the evidence is an assertion. The engine rebuilds every unit's
    variance through the shared kernel and compares -- including that the
    summary lists exactly the units the evidence names.
    """
    rule = "rpt_unit_variance_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RECON_SUMMARY)
    if summary is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = {r["unit_id"]: r for r in recompute_recon_units(ctx)}
        stated_rows = {u: r for r in _rows(summary, "units") if (u := _text(r, "unit_id"))}
        for unit in sorted(set(stated_rows) - set(derived)):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, f"units/{unit}"),
                    f"the summary reconciles unit {unit}, which neither the ledger "
                    f"nor the agent's statement names",
                )
            )
        for unit in sorted(set(derived) - set(stated_rows)):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, f"units/{unit}"),
                    f"unit {unit} appears in the evidence but is missing from the "
                    f"reconciliation summary; its variance was never stated",
                )
            )
        for unit in sorted(set(derived) & set(stated_rows)):
            stated = require_cents(
                f"summary[{unit}].variance_cents",
                stated_rows[unit].get("variance_cents"),
            )
            want = derived[unit]["variance_cents"]
            if stated != want:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"units/{unit}/variance_cents"),
                        f"unit {unit} is summarised at a variance of {fmt(stated)}; "
                        f"recomputing agent-minus-books gives {fmt(want)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every stated unit variance recomputes from the ledger and the agent",
            )
        )
    return out


@check("rpt_exception_flags_tie")
def check_rpt_exception_flags_tie(ctx: Context) -> list[Finding]:
    """Each unit's exception flag equals (recomputed variance != 0).

    A FLAG rather than a failure: the flag column is the reviewer's work
    queue, and a flag that contradicts the variance sends the follow-up to the
    wrong unit -- or hides the one that needed it.
    """
    rule = "rpt_exception_flags_tie"
    _sev(rule, Status.FLAG)
    summary = ctx.one(DOC_RECON_SUMMARY)
    if summary is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = {r["unit_id"]: r for r in recompute_recon_units(ctx)}
        for row in _rows(summary, "units"):
            unit = _text(row, "unit_id")
            if unit is None or unit not in derived:
                continue  # rpt_unit_variance_recomputes owns this
            stated = bool(row.get("exception_flag"))
            want = derived[unit]["exception_flag"]
            if stated != want:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(summary, f"units/{unit}/exception_flag"),
                        f"unit {unit} is flagged {stated} but its recomputed variance "
                        f"of {fmt(derived[unit]['variance_cents'])} says {want}; the "
                        f"reviewer's work queue does not match the evidence",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every exception flag ties its recomputed variance",
            )
        )
    return out


@check("rpt_total_variance_ties")
def check_rpt_total_variance_ties(ctx: Context) -> list[Finding]:
    """The summary's total variance equals the sum of the unit variances.

    The total line is what proves the reconciliation is live: a total
    maintained beside the rows rather than derived from them drifts the first
    time a unit moves and nobody re-foots the column.
    """
    rule = "rpt_total_variance_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RECON_SUMMARY)
    if summary is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "summary.total_variance_cents", summary.get("total_variance_cents")
        )
        derived = sum(r["variance_cents"] for r in recompute_recon_units(ctx))
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, "total_variance_cents"),
                    f"the summary states a total variance of {fmt(stated)}; the "
                    f"recomputed unit variances foot to {fmt(derived)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the total variance of {fmt(stated)} foots the unit variances",
                )
            )
    return out


@check("rpt_bucket_totals_tie")
def check_rpt_bucket_totals_tie(ctx: Context) -> list[Finding]:
    """The stated posting-bucket totals recompute from the ledger.

    The three bucket totals -- need-to-post, already-posted, unit-closed --
    are the operational to-do list for the next posting run; a total that does
    not recompute posts too much or too little to the loan.
    """
    rule = "rpt_bucket_totals_tie"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RECON_SUMMARY)
    ledger = ctx.one(DOC_DEPOSIT_LEDGER)
    if summary is None or ledger is None:
        return []
    stated_doc = summary.get("bucket_totals")
    stated_doc = stated_doc if isinstance(stated_doc, dict) else {}
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = recompute_bucket_totals(ctx)
        for bucket in STATUS_BUCKETS:
            stated = require_cents(
                f"summary.bucket_totals.{bucket}_cents",
                stated_doc.get(f"{bucket}_cents"),
            )
            if stated != derived[bucket]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"bucket_totals/{bucket}_cents"),
                        f"the summary states {fmt(stated)} of earnest money in the "
                        f"{bucket} bucket; the ledger recomputes {fmt(derived[bucket])}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "all three posting-bucket totals recompute from the ledger",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one deposit file."""
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
    """Analyze every ``.json`` deposit file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of deposit-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
