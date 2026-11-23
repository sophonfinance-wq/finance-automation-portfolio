"""
Intercompany reciprocity control engine (READ-ONLY).
====================================================

Loads each period file (a ``.json`` file produced by
:mod:`intercompany_engine.generate`) and runs an ordered *registry* of independent
controls over it.

The shape of the problem
------------------------
A development group is a tree of entities, not one company. Cash moves between them
every day -- advances down the chain, repayments back up, equity into projects --
and each movement lands two entries on two sets of books kept by two people. Each
entity's own books foot. The break, when there is one, lives *between* two
entities and surfaces only at consolidation, when the intercompany balances are
meant to eliminate to zero and instead leave a residual nobody can source.

The registry is organised around that:

1. ``set_``   -- is the period file complete, and does every code it names exist?
2. ``ent_``   -- is the entity tree itself sound: unique codes, real parents, no cycle?
3. ``rec_``   -- do the two sides reconcile: is every due-from faced by an equal due-to?
4. ``led_``   -- do the balances roll forward from the transactions that moved them?
5. ``fund_``  -- did the cash come from the protocol-correct entity and flow the right way?
6. ``liq_``   -- are the liquidity covenants and target bands respected?
7. ``appr_``  -- is the ledger approved, and are the large advances surfaced for a second look?

Design notes
------------
- **Strictly read-only.** Period files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Amounts are compared with exact ``==``.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.

Reciprocity is the spine
------------------------
A due-from on entity A against entity B is a claim that B owes A. The mirror of
that claim -- B's due-to A -- is booked by a different controller, and the whole
point of the reconciliation is that the two must agree. When they do for every
pair, the group's intercompany balances eliminate to zero on consolidation. When
one pair drifts, the residual is invisible on either entity alone.
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
    DOC_DUE_FROM,
    DOC_DUE_TO,
    DOC_ENTITY_REGISTER,
    DOC_FUNDING_PROTOCOL,
    DOC_IC_LEDGER,
    DOC_LIQUIDITY,
    DOC_TYPES,
    GROUP_CAPITAL,
    HOLDINGS_FUNDED_GROUPS,
    TXN_ADVANCE,
    TXN_EQUITY,
    TXN_REPAYMENT,
    TXN_TYPES,
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
    """Render an :class:`~intercompany_engine.money.AmountInvalidError` as a finding."""
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
_PERIOD_RE = re.compile(r"^\d{4}-Q[1-4]$")


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


# --------------------------------------------------------------------------- #
# Entity-tree helpers
# --------------------------------------------------------------------------- #
def _entities(ctx: Context) -> dict[str, dict[str, Any]]:
    """Map entity code -> entity row from the register (first wins on a dup)."""
    reg = ctx.one(DOC_ENTITY_REGISTER)
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(reg, "entities"):
        code = row.get("code")
        if isinstance(code, str) and code not in out:
            out[code] = row
    return out


def _top_parent(ctx: Context) -> str | None:
    reg = ctx.one(DOC_ENTITY_REGISTER)
    if not isinstance(reg, dict):
        return None
    tp = reg.get("top_parent")
    return tp if isinstance(tp, str) else None


def _group_of(entities: dict[str, dict[str, Any]], code: str) -> str | None:
    row = entities.get(code)
    grp = row.get("group") if row else None
    return grp if isinstance(grp, str) else None


def _region_of(entities: dict[str, dict[str, Any]], code: str) -> str | None:
    row = entities.get(code)
    reg = row.get("region") if row else None
    return reg if isinstance(reg, str) and reg else None


def _is_ancestor(
    entities: dict[str, dict[str, Any]], ancestor: str, code: str
) -> bool:
    """True if ``ancestor`` is strictly above ``code`` in the ownership chain."""
    seen: set[str] = set()
    cur = entities.get(code, {}).get("parent")
    while isinstance(cur, str) and cur and cur not in seen:
        if cur == ancestor:
            return True
        seen.add(cur)
        cur = entities.get(cur, {}).get("parent")
    return False


# --------------------------------------------------------------------------- #
# Position / ledger helpers
# --------------------------------------------------------------------------- #
def _due_from(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DUE_FROM), "positions")


def _due_to(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DUE_TO), "positions")


def _txns(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_IC_LEDGER), "transactions")


def _liquidity(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_LIQUIDITY), "positions")


# --------------------------------------------------------------------------- #
# 1. set_*
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
            out.append(Finding(rule, Status.FAIL, f"file:{ctx.file_id}/{doc_type}",
                               f"period file carries no {doc_type}; absent evidence is not "
                               f"a passing control, so no downstream rule may read it"))
        elif len(found) > 1:
            out.append(Finding(rule, Status.FAIL, f"file:{ctx.file_id}/{doc_type}",
                               f"period file carries {len(found)} {doc_type} documents; "
                               f"exactly one is expected"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(DOC_TYPES)} artifact types present exactly once"))
    return out


@check("set_period_label")
def set_period_label(ctx: Context) -> list[Finding]:
    """The period file must declare a well-formed quarterly reporting period."""
    rule = "set_period_label"
    _sev(rule, Status.FAIL)
    if not _PERIOD_RE.match(ctx.period):
        return [Finding(rule, Status.FAIL, f"file:{ctx.file_id}/period",
                        f"reporting period {ctx.period!r} is not a YYYY-Qn label; every "
                        f"intercompany schedule is filed against a quarter and cannot be "
                        f"placed without one")]
    return [Finding(rule, Status.PASS, "-",
                    f"reporting period {ctx.period} is well formed")]


@check("set_entities_exist")
def set_entities_exist(ctx: Context) -> list[Finding]:
    """Every entity code used anywhere in the file must be in the register.

    This is the entity-mapping control. A transaction or a balance that names a
    code the register has never heard of is not a small typo -- it is a position
    that cannot be placed in the tree, so its reciprocity and its funding source
    can never be checked. The break is silent because the row still foots on its
    own line.
    """
    rule = "set_entities_exist"
    _sev(rule, Status.FAIL)
    entities = _entities(ctx)
    if not entities:
        return []
    known = set(entities)
    used: dict[str, str] = {}  # code -> where first seen

    def note(code: object, where: str) -> None:
        if isinstance(code, str) and code and code not in used:
            used[code] = where

    for t in _txns(ctx):
        note(t.get("from_entity"), f"ledger txn {t.get('txn_no')} from_entity")
        note(t.get("to_entity"), f"ledger txn {t.get('txn_no')} to_entity")
    for r in _due_from(ctx):
        note(r.get("entity"), "due_from.entity")
        note(r.get("counterparty"), "due_from.counterparty")
    for r in _due_to(ctx):
        note(r.get("entity"), "due_to.entity")
        note(r.get("counterparty"), "due_to.counterparty")
    for r in _liquidity(ctx):
        note(r.get("entity"), "liquidity.entity")
    prot = ctx.one(DOC_FUNDING_PROTOCOL)
    if isinstance(prot, dict):
        note(prot.get("guarantor_code"), "protocol.guarantor_code")
        for tgt in _rows(prot, "targets"):
            note(tgt.get("code"), "protocol.target")

    out = [
        Finding(rule, Status.FAIL, f"{DOC_ENTITY_REGISTER}/{code}",
                f"code {code!r} is used at {where} but is not in the entity register; "
                f"a position on an unregistered entity cannot be reconciled or eliminated")
        for code, where in sorted(used.items()) if code not in known
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(used)} referenced entity codes are registered"))
    return out


# --------------------------------------------------------------------------- #
# 2. ent_* -- the entity tree is sound
# --------------------------------------------------------------------------- #
@check("ent_codes_unique")
def ent_codes_unique(ctx: Context) -> list[Finding]:
    """Entity codes in the register must be unique.

    A duplicate code makes every downstream lookup ambiguous: two entities answer
    to the same name, so a balance keyed on it could belong to either.
    """
    rule = "ent_codes_unique"
    _sev(rule, Status.FAIL)
    reg = ctx.one(DOC_ENTITY_REGISTER)
    if reg is None:
        return []
    counts: dict[str, int] = {}
    for row in _rows(reg, "entities"):
        code = row.get("code")
        if isinstance(code, str):
            counts[code] = counts.get(code, 0) + 1
    out = [
        Finding(rule, Status.FAIL, ctx.loc(reg, f"entities/{code}"),
                f"entity code {code!r} appears {n} times in the register; codes must be "
                f"unique or a balance keyed on it is ambiguous")
        for code, n in sorted(counts.items()) if n > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(counts)} entity codes are unique"))
    return out


@check("ent_parent_defined")
def ent_parent_defined(ctx: Context) -> list[Finding]:
    """Each entity's parent must be a known code; the top parent has none."""
    rule = "ent_parent_defined"
    _sev(rule, Status.FAIL)
    reg = ctx.one(DOC_ENTITY_REGISTER)
    if reg is None:
        return []
    entities = _entities(ctx)
    top = _top_parent(ctx)
    out: list[Finding] = []
    if top is None or top not in entities:
        out.append(Finding(rule, Status.FAIL, ctx.loc(reg, "top_parent"),
                           f"the register names top parent {top!r}, which is not an entity "
                           f"in the register"))
    for code, row in sorted(entities.items()):
        parent = row.get("parent")
        if code == top:
            if isinstance(parent, str) and parent.strip():
                out.append(Finding(rule, Status.FAIL, ctx.loc(reg, f"entities/{code}/parent"),
                                   f"top parent {code!r} declares a parent {parent!r}; the "
                                   f"root of the group owns everything and is owned by none"))
            continue
        if not (isinstance(parent, str) and parent.strip()):
            out.append(Finding(rule, Status.FAIL, ctx.loc(reg, f"entities/{code}/parent"),
                               f"entity {code!r} declares no parent; only the top parent may "
                               f"be a root"))
        elif parent not in entities:
            out.append(Finding(rule, Status.FAIL, ctx.loc(reg, f"entities/{code}/parent"),
                               f"entity {code!r} names parent {parent!r}, which is not in the "
                               f"register"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "every entity's parent is defined and the top parent is a root"))
    return out


@check("ent_tree_acyclic")
def ent_tree_acyclic(ctx: Context) -> list[Finding]:
    """The ownership chain from every entity must reach the top parent, no cycle.

    A cycle in the parent links -- A owns B owns A -- means the group has no root,
    so "flows down the chain" has no meaning and the funding-direction control
    below cannot be evaluated.
    """
    rule = "ent_tree_acyclic"
    _sev(rule, Status.FAIL)
    reg = ctx.one(DOC_ENTITY_REGISTER)
    if reg is None:
        return []
    entities = _entities(ctx)
    top = _top_parent(ctx)
    out: list[Finding] = []
    for code in sorted(entities):
        if code == top:
            continue
        # Walk parents until the top parent, a repeat (cycle), or a dead end.
        # A chain that dead-ends short of the top parent is a second root, which
        # is ent_parent_defined's finding; this control owns only the cycle.
        seen: set[str] = {code}
        cur = entities.get(code, {}).get("parent")
        while isinstance(cur, str) and cur and cur != top:
            if cur in seen:
                out.append(Finding(rule, Status.FAIL, ctx.loc(reg, f"entities/{code}/parent"),
                                   f"the ownership chain from {code!r} cycles through {cur!r} "
                                   f"and never reaches the top parent; the group has no root"))
                break
            seen.add(cur)
            cur = entities.get(cur, {}).get("parent")
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "every ownership chain reaches the top parent without a cycle"))
    return out


# --------------------------------------------------------------------------- #
# 3. rec_* -- the two sides reconcile
# --------------------------------------------------------------------------- #
@check("rec_pairs_symmetric")
def rec_pairs_symmetric(ctx: Context) -> list[Finding]:
    """Every due-from pair must be faced by a due-to pair, and vice versa.

    A due-from on A against B with no due-to on B against A is an orphan: A is
    claiming a balance the counterparty has never acknowledged. It is the shape a
    reconciliation break takes before anyone has looked at the amounts.
    """
    rule = "rec_pairs_symmetric"
    _sev(rule, Status.FAIL)
    df = ctx.one(DOC_DUE_FROM)
    dt = ctx.one(DOC_DUE_TO)
    if df is None or dt is None:
        return []
    df_pairs = {(str(r.get("entity")), str(r.get("counterparty"))) for r in _due_from(ctx)}
    dt_pairs = {(str(r.get("entity")), str(r.get("counterparty"))) for r in _due_to(ctx)}
    out: list[Finding] = []
    for a, b in sorted(df_pairs):
        if (b, a) not in dt_pairs:
            out.append(Finding(rule, Status.FAIL, ctx.loc(df, f"positions/{a}->{b}"),
                               f"{a} books a due-from against {b}, but {b} books no due-to "
                               f"against {a}; the counterparty has not acknowledged the balance"))
    for b, a in sorted(dt_pairs):
        if (a, b) not in df_pairs:
            out.append(Finding(rule, Status.FAIL, ctx.loc(dt, f"positions/{b}->{a}"),
                               f"{b} books a due-to against {a}, but {a} books no due-from "
                               f"against {b}; the receivable side is missing"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(df_pairs)} intercompany pairs are two-sided"))
    return out


@check("rec_amounts_reciprocal")
def rec_amounts_reciprocal(ctx: Context) -> list[Finding]:
    """A due-from must equal the due-to that faces it, to the cent.

    This is the spine of the engine. Two controllers book the two sides
    independently; the reconciliation exists precisely because they drift. When
    every pair agrees, the group's intercompany balances eliminate to zero.
    """
    rule = "rec_amounts_reciprocal"
    _sev(rule, Status.FAIL)
    df = ctx.one(DOC_DUE_FROM)
    dt = ctx.one(DOC_DUE_TO)
    if df is None or dt is None:
        return []
    out: list[Finding] = []
    due_to: dict[tuple[str, str], int] = {}
    for r in _due_to(ctx):
        key = (str(r.get("entity")), str(r.get("counterparty")))
        with amount_guard(rule, out):
            due_to[key] = require_cents(f"due_to[{key[0]}->{key[1]}].closing_cents",
                                        r.get("closing_cents"))
    checked = 0
    for r in _due_from(ctx):
        a, b = str(r.get("entity")), str(r.get("counterparty"))
        with amount_guard(rule, out):
            from_amt = require_cents(f"due_from[{a}->{b}].closing_cents",
                                     r.get("closing_cents"))
            mirror = due_to.get((b, a))
            if mirror is None:
                continue  # rec_pairs_symmetric owns the missing-mirror finding
            checked += 1
            if from_amt != mirror:
                out.append(Finding(rule, Status.FAIL, ctx.loc(df, f"positions/{a}->{b}"),
                                   f"{a} books a due-from of {fmt(from_amt)} against {b}, but "
                                   f"{b} books a due-to of {fmt(mirror)} against {a} "
                                   f"(difference {fmt(from_amt - mirror)}); the balance will "
                                   f"not eliminate on consolidation"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} intercompany pairs are reciprocal to the cent"))
    return out


@check("rec_no_self_balance")
def rec_no_self_balance(ctx: Context) -> list[Finding]:
    """No entity may hold a due-from or due-to against itself.

    An entity owing itself is not a balance; it is a mis-keyed counterparty, and
    it inflates both the receivable and payable totals by the same amount so the
    group still appears to eliminate.
    """
    rule = "rec_no_self_balance"
    _sev(rule, Status.FAIL)
    df = ctx.one(DOC_DUE_FROM)
    dt = ctx.one(DOC_DUE_TO)
    if df is None or dt is None:
        return []
    out: list[Finding] = []
    for r in _due_from(ctx):
        if str(r.get("entity")) == str(r.get("counterparty")):
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(df, f"positions/{r.get('entity')}"),
                               f"entity {r.get('entity')!r} books a due-from against itself; "
                               f"a counterparty has been mis-keyed"))
    for r in _due_to(ctx):
        if str(r.get("entity")) == str(r.get("counterparty")):
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(dt, f"positions/{r.get('entity')}"),
                               f"entity {r.get('entity')!r} books a due-to against itself; "
                               f"a counterparty has been mis-keyed"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "no entity holds a balance against itself"))
    return out


# --------------------------------------------------------------------------- #
# 4. led_* -- balances roll forward from the ledger
# --------------------------------------------------------------------------- #
@check("led_parties_distinct")
def led_parties_distinct(ctx: Context) -> list[Finding]:
    """An advance or repayment must move between two distinct entities."""
    rule = "led_parties_distinct"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for t in _txns(ctx):
        frm = t.get("from_entity")
        if not (isinstance(frm, str) and frm.strip()):
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(ledger, f"transactions/{t.get('txn_no')}/from_entity"),
                               f"transaction {t.get('txn_no')} names no source entity"))
            continue
        if t.get("txn_type") in (TXN_ADVANCE, TXN_REPAYMENT):
            to = t.get("to_entity")
            checked += 1
            if not (isinstance(to, str) and to.strip()):
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(ledger, f"transactions/{t.get('txn_no')}/to_entity"),
                                   f"{t.get('txn_type')} {t.get('txn_no')} names no counterparty"))
            elif to == frm:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(ledger, f"transactions/{t.get('txn_no')}/to_entity"),
                                   f"{t.get('txn_type')} {t.get('txn_no')} moves cash from "
                                   f"{frm} to itself; an entity cannot advance to or repay "
                                   f"itself"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} advances and repayments move between two entities"))
    return out


@check("led_amounts_positive")
def led_amounts_positive(ctx: Context) -> list[Finding]:
    """Every transaction amount must be a positive integer number of cents.

    Direction is carried by the transaction type and the from/to entities, not by
    the sign of the amount. A negative or zero advance is a data error hiding a
    reversal that should have been booked as a repayment.
    """
    rule = "led_amounts_positive"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for t in _txns(ctx):
        with amount_guard(rule, out):
            amt = require_cents(f"ledger.transactions[{t.get('txn_no')}].amount_cents",
                                t.get("amount_cents"))
            checked += 1
            if amt <= 0:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(ledger, f"transactions/{t.get('txn_no')}/amount_cents"),
                                   f"transaction {t.get('txn_no')} carries a non-positive "
                                   f"amount {fmt(amt)}; direction is carried by the type and "
                                   f"the parties, not the sign"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} transaction amounts are positive"))
    return out


@check("led_totals_foot")
def led_totals_foot(ctx: Context) -> list[Finding]:
    """The ledger's declared totals per type must foot from its own lines."""
    rule = "led_totals_foot"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    summed: dict[str, int] = {t: 0 for t in TXN_TYPES}
    for t in _txns(ctx):
        ttype = t.get("txn_type")
        if ttype not in summed:
            continue
        with amount_guard(rule, out):
            summed[ttype] += require_cents(
                f"ledger.transactions[{t.get('txn_no')}].amount_cents", t.get("amount_cents"))
    totals = ledger.get("totals")
    if not isinstance(totals, dict):
        out.append(Finding(rule, Status.FAIL, ctx.loc(ledger, "totals"),
                           "the ledger declares no totals block to foot against"))
        return out
    for ttype in TXN_TYPES:
        with amount_guard(rule, out):
            declared = require_cents(f"ledger.totals.{ttype}_cents",
                                     totals.get(f"{ttype}_cents"))
            if declared != summed[ttype]:
                out.append(Finding(rule, Status.FAIL, ctx.loc(ledger, f"totals/{ttype}_cents"),
                                   f"{ttype} lines sum to {fmt(summed[ttype])} but the ledger "
                                   f"declares {fmt(declared)} "
                                   f"(difference {fmt(summed[ttype] - declared)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "the ledger totals foot from the transaction lines"))
    return out


@check("led_rollforward_ties")
def led_rollforward_ties(ctx: Context) -> list[Finding]:
    """Each due-from closing must equal opening plus advances less repayments.

    This is the link between the balances and the transactions that moved them.
    Equity fundings do not appear: they debit an investment account, not a
    due-from, so a closing that moved by an equity amount has booked capital as a
    receivable.
    """
    rule = "led_rollforward_ties"
    _sev(rule, Status.FAIL)
    df = ctx.one(DOC_DUE_FROM)
    ledger = ctx.one(DOC_IC_LEDGER)
    if df is None or ledger is None:
        return []
    out: list[Finding] = []
    # An advance's cash flows creditor -> debtor, so it is keyed on the same
    # (creditor, debtor) pair the due-from is. A repayment's cash flows the other
    # way -- debtor -> creditor -- so it is keyed (debtor, creditor) and reduces
    # the balance of the reversed pair.
    advances: dict[tuple[str, str], int] = {}
    repayments: dict[tuple[str, str], int] = {}
    for t in _txns(ctx):
        ttype = t.get("txn_type")
        if ttype not in (TXN_ADVANCE, TXN_REPAYMENT):
            continue
        key = (str(t.get("from_entity")), str(t.get("to_entity")))
        with amount_guard(rule, out):
            amt = require_cents(f"ledger.transactions[{t.get('txn_no')}].amount_cents",
                                t.get("amount_cents"))
            bucket = advances if ttype == TXN_ADVANCE else repayments
            bucket[key] = bucket.get(key, 0) + amt
    checked = 0
    for r in _due_from(ctx):
        a, b = str(r.get("entity")), str(r.get("counterparty"))
        with amount_guard(rule, out):
            opening = require_cents(f"due_from[{a}->{b}].opening_cents", r.get("opening_cents"))
            closing = require_cents(f"due_from[{a}->{b}].closing_cents", r.get("closing_cents"))
            expected = opening + advances.get((a, b), 0) - repayments.get((b, a), 0)
            checked += 1
            if closing != expected:
                out.append(Finding(rule, Status.FAIL, ctx.loc(df, f"positions/{a}->{b}"),
                                   f"{a}->{b}: opening {fmt(opening)} plus advances "
                                   f"{fmt(advances.get((a, b), 0))} less repayments "
                                   f"{fmt(repayments.get((a, b), 0))} = {fmt(expected)}, but "
                                   f"the closing balance is {fmt(closing)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} due-from balances roll forward from the ledger"))
    return out


@check("led_dates_inside_window")
def led_dates_inside_window(ctx: Context) -> list[Finding]:
    """Every transaction must be dated inside the ledger's reporting window."""
    rule = "led_dates_inside_window"
    _sev(rule, Status.FLAG)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    start = _parse_date(ledger.get("from_date"))
    end = _parse_date(ledger.get("to_date"))
    if start is None or end is None:
        return [Finding(rule, Status.FLAG, ctx.loc(ledger, "from_date"),
                        "the ledger declares no readable reporting window")]
    out: list[Finding] = []
    checked = 0
    for t in _txns(ctx):
        when = _parse_date(t.get("txn_date"))
        if when is None:
            continue
        checked += 1
        if not (start <= when <= end):
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(ledger, f"transactions/{t.get('txn_no')}/txn_date"),
                               f"transaction {t.get('txn_no')} is dated {when.isoformat()}, "
                               f"outside the {start.isoformat()}..{end.isoformat()} window"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} transactions fall inside the reporting window"))
    return out


# --------------------------------------------------------------------------- #
# 5. fund_* -- cash came from the protocol-correct entity
# --------------------------------------------------------------------------- #
@check("fund_equity_from_capital")
def fund_equity_from_capital(ctx: Context) -> list[Finding]:
    """Project equity funding must originate from a Capital-group entity.

    Once a project entity becomes a subsidiary of the capital arm, its equity is
    funded from there. Equity coming from anywhere else routes project capital
    around the guarantor structure the lenders relied on.
    """
    rule = "fund_equity_from_capital"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    entities = _entities(ctx)
    out: list[Finding] = []
    checked = 0
    for t in _txns(ctx):
        if t.get("txn_type") != TXN_EQUITY:
            continue
        frm = str(t.get("from_entity"))
        checked += 1
        if _group_of(entities, frm) != GROUP_CAPITAL:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(ledger, f"transactions/{t.get('txn_no')}/from_entity"),
                               f"equity funding {t.get('txn_no')} for {t.get('project')!r} "
                               f"comes from {frm} ({_group_of(entities, frm)}), but project "
                               f"equity must be funded from the Capital group"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} equity fundings originate in the Capital group"))
    return out


@check("fund_region_matches")
def fund_region_matches(ctx: Context) -> list[Finding]:
    """Equity funding must come from the capital entity of the project's region.

    The Seattle capital entity funds Seattle projects and the Southern California
    capital entity funds Southern California projects. Cross-region funding puts a
    project on the wrong balance sheet.
    """
    rule = "fund_region_matches"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    entities = _entities(ctx)
    out: list[Finding] = []
    checked = 0
    for t in _txns(ctx):
        if t.get("txn_type") != TXN_EQUITY:
            continue
        region = t.get("region")
        if not (isinstance(region, str) and region):
            continue
        frm = str(t.get("from_entity"))
        src_region = _region_of(entities, frm)
        checked += 1
        if src_region != region:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(ledger, f"transactions/{t.get('txn_no')}/from_entity"),
                               f"equity funding {t.get('txn_no')} for a {region} project comes "
                               f"from {frm} (region {src_region!r}); the funding entity's "
                               f"region must match the project's"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} regional equity fundings match their project region"))
    return out


@check("fund_services_from_holdings")
def fund_services_from_holdings(ctx: Context) -> list[Finding]:
    """Services and predevelopment funding must come from the top parent.

    The employer entities and the predevelopment arm are funded down from
    Holdings, never from the Capital group. Capital funding a Services entity
    crosses the wall between the group that guarantees the loans and the group
    that carries the people.
    """
    rule = "fund_services_from_holdings"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    entities = _entities(ctx)
    top = _top_parent(ctx)
    out: list[Finding] = []
    checked = 0
    for t in _txns(ctx):
        to = t.get("to_entity")
        if not (isinstance(to, str) and to):
            continue
        if _group_of(entities, to) not in HOLDINGS_FUNDED_GROUPS:
            continue
        frm = str(t.get("from_entity"))
        checked += 1
        if frm != top:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(ledger, f"transactions/{t.get('txn_no')}/from_entity"),
                               f"{t.get('txn_type')} {t.get('txn_no')} funds {to} "
                               f"({_group_of(entities, to)}) from {frm}, but Services and "
                               f"predevelopment funding must come from the top parent {top!r}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} Services/predevelopment fundings come from the "
                           f"top parent"))
    return out


@check("fund_advance_flows_down")
def fund_advance_flows_down(ctx: Context) -> list[Finding]:
    """An advance should flow down the ownership chain, not up it.

    Not a hard failure -- an upstream movement can be legitimate -- but an
    "advance" from a subsidiary to its parent is more often a distribution or a
    cash sweep mislabelled, and booking it as a receivable overstates what the
    child is owed. It is surfaced for a human to classify.
    """
    rule = "fund_advance_flows_down"
    _sev(rule, Status.FLAG)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    entities = _entities(ctx)
    out: list[Finding] = []
    checked = 0
    for t in _txns(ctx):
        if t.get("txn_type") != TXN_ADVANCE:
            continue
        frm, to = str(t.get("from_entity")), t.get("to_entity")
        if not (isinstance(to, str) and to) or frm not in entities or to not in entities:
            continue
        checked += 1
        if not _is_ancestor(entities, frm, to):
            direction = ("up the chain" if _is_ancestor(entities, to, frm)
                         else "across the tree")
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(ledger, f"transactions/{t.get('txn_no')}/to_entity"),
                               f"advance {t.get('txn_no')} runs from {frm} to {to} "
                               f"({direction}); an advance that is not to a descendant is "
                               f"often a distribution or sweep and wants classifying"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} advances flow down the ownership chain"))
    return out


# --------------------------------------------------------------------------- #
# 6. liq_* -- liquidity covenants and target bands
# --------------------------------------------------------------------------- #
@check("liq_guarantor_minimum")
def liq_guarantor_minimum(ctx: Context) -> list[Finding]:
    """The guarantor entity must hold at least its minimum liquidity.

    The capital arm's parent guarantees the construction loans and is bound by a
    liquidity covenant. Falling under the floor is a covenant breach whether or
    not any single transaction looks wrong.
    """
    rule = "liq_guarantor_minimum"
    _sev(rule, Status.FAIL)
    prot = ctx.one(DOC_FUNDING_PROTOCOL)
    liq = ctx.one(DOC_LIQUIDITY)
    if prot is None or liq is None:
        return []
    guarantor = prot.get("guarantor_code")
    if not (isinstance(guarantor, str) and guarantor):
        return [Finding(rule, Status.FAIL, ctx.loc(prot, "guarantor_code"),
                        "the protocol names no guarantor entity")]
    out: list[Finding] = []
    with amount_guard(rule, out):
        floor = require_cents("protocol.min_liquidity_cents", prot.get("min_liquidity_cents"))
        cash_by_entity = {str(r.get("entity")): r for r in _liquidity(ctx)}
        row = cash_by_entity.get(guarantor)
        if row is None:
            out.append(Finding(rule, Status.FAIL, ctx.loc(liq, f"positions/{guarantor}"),
                               f"the guarantor {guarantor!r} has no liquidity position, so its "
                               f"covenant cannot be shown to hold"))
        else:
            cash = require_cents(f"liquidity[{guarantor}].cash_cents", row.get("cash_cents"))
            if cash < floor:
                out.append(Finding(rule, Status.FAIL, ctx.loc(liq, f"positions/{guarantor}"),
                                   f"the guarantor {guarantor} holds {fmt(cash)}, below its "
                                   f"{fmt(floor)} minimum liquidity covenant "
                                   f"(short {fmt(floor - cash)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "the guarantor meets its minimum liquidity covenant"))
    return out


@check("liq_no_negative_cash")
def liq_no_negative_cash(ctx: Context) -> list[Finding]:
    """No entity may report a negative cash balance."""
    rule = "liq_no_negative_cash"
    _sev(rule, Status.FAIL)
    liq = ctx.one(DOC_LIQUIDITY)
    if liq is None:
        return []
    out: list[Finding] = []
    checked = 0
    for r in _liquidity(ctx):
        entity = str(r.get("entity"))
        with amount_guard(rule, out):
            cash = require_cents(f"liquidity[{entity}].cash_cents", r.get("cash_cents"))
            checked += 1
            if cash < 0:
                out.append(Finding(rule, Status.FAIL, ctx.loc(liq, f"positions/{entity}"),
                                   f"entity {entity} reports negative cash {fmt(cash)}; a bank "
                                   f"balance cannot be overdrawn on the books"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} entities report non-negative cash"))
    return out


@check("liq_target_band")
def liq_target_band(ctx: Context) -> list[Finding]:
    """Flag entities whose cash sits outside its protocol target band.

    Not a failure -- the target is a management guideline, not a covenant -- but an
    entity far below its band is undercapitalised for the cash it is meant to
    hold, and far above it is trapping cash the sweep should have pulled up.
    """
    rule = "liq_target_band"
    _sev(rule, Status.FLAG)
    prot = ctx.one(DOC_FUNDING_PROTOCOL)
    liq = ctx.one(DOC_LIQUIDITY)
    if prot is None or liq is None:
        return []
    cash_by_entity = {str(r.get("entity")): r for r in _liquidity(ctx)}
    out: list[Finding] = []
    checked = 0
    for tgt in _rows(prot, "targets"):
        code = str(tgt.get("code"))
        row = cash_by_entity.get(code)
        if row is None:
            continue
        with amount_guard(rule, out):
            low = require_cents(f"protocol.targets[{code}].target_low_cents",
                                tgt.get("target_low_cents"))
            high = require_cents(f"protocol.targets[{code}].target_high_cents",
                                 tgt.get("target_high_cents"))
            cash = require_cents(f"liquidity[{code}].cash_cents", row.get("cash_cents"))
            checked += 1
            if cash < low:
                out.append(Finding(rule, Status.FLAG, ctx.loc(liq, f"positions/{code}"),
                                   f"{code} holds {fmt(cash)}, below its target band floor of "
                                   f"{fmt(low)}; it is undercapitalised for the cash it should "
                                   f"carry"))
            elif cash > high:
                out.append(Finding(rule, Status.FLAG, ctx.loc(liq, f"positions/{code}"),
                                   f"{code} holds {fmt(cash)}, above its target band ceiling of "
                                   f"{fmt(high)}; cash the sweep should have pulled up is "
                                   f"trapped here"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} targeted entities sit inside their band"))
    return out


# --------------------------------------------------------------------------- #
# 7. appr_* -- governance
# --------------------------------------------------------------------------- #
@check("appr_ledger_approved")
def appr_ledger_approved(ctx: Context) -> list[Finding]:
    """The intercompany ledger must carry an approver and a date."""
    rule = "appr_ledger_approved"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if ledger is None:
        return []
    approver = ledger.get("approved_by")
    if not (isinstance(approver, str) and approver.strip()):
        return [Finding(rule, Status.FAIL, ctx.loc(ledger, "approved_by"),
                        "the intercompany ledger carries no approver; cash moved between "
                        "entities without a sign-off")]
    if _parse_date(ledger.get("approval_date")) is None:
        return [Finding(rule, Status.FAIL, ctx.loc(ledger, "approval_date"),
                        f"the approval by {approver!r} carries no readable date")]
    return [Finding(rule, Status.PASS, "-", "the ledger is approved and dated")]


@check("appr_large_advance_flagged")
def appr_large_advance_flagged(ctx: Context) -> list[Finding]:
    """Flag single advances at or above the protocol's second-signature threshold.

    A large intercompany advance is not wrong, but it is exactly the movement that
    should carry a second signature. Surfacing it is cheaper than discovering an
    unreviewed eight-figure advance after the quarter closed.
    """
    rule = "appr_large_advance_flagged"
    _sev(rule, Status.FLAG)
    prot = ctx.one(DOC_FUNDING_PROTOCOL)
    ledger = ctx.one(DOC_IC_LEDGER)
    if prot is None or ledger is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        threshold = require_cents("protocol.large_advance_threshold_cents",
                                  prot.get("large_advance_threshold_cents"))
        checked = 0
        for t in _txns(ctx):
            if t.get("txn_type") != TXN_ADVANCE:
                continue
            with amount_guard(rule, out):
                amt = require_cents(f"ledger.transactions[{t.get('txn_no')}].amount_cents",
                                    t.get("amount_cents"))
                checked += 1
                if amt >= threshold:
                    out.append(Finding(rule, Status.FLAG,
                                       ctx.loc(ledger, f"transactions/{t.get('txn_no')}/amount_cents"),
                                       f"advance {t.get('txn_no')} of {fmt(amt)} meets the "
                                       f"{fmt(threshold)} second-signature threshold and should "
                                       f"be reviewed before funding"))
        if not out:
            out.append(Finding(rule, Status.PASS, "-",
                               f"none of the {checked} advances reach the review threshold"))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one period file."""
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
    """Analyze every ``.json`` period file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of period-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
