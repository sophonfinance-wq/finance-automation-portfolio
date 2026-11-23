"""
Mechanics-lien waiver tracking control engine (READ-ONLY).
==========================================================

Loads each portfolio file (a ``.json`` file produced by
:mod:`lien_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether a lien waiver stands behind every dollar paid**,
not whether the payment should have gone out. Invoice approval, three-way match
and budget release gate a payment, and the accounts-payable engine owns that
gate. Nothing here re-authorises a payment.

The shape of the problem
------------------------
A developer pays down a tier chain, and every party in it can file a mechanics
lien. A lien waiver is the release, and it has to march in lockstep with the
money -- the right *kind* of waiver, running through the right *date*, for the
right *amount*, at every *tier*.

Three failures hide inside that, and none of them look wrong when a waiver is on
file:

- the *conditional* signed at payment that was never upgraded to the
  *unconditional* owed once the cheque cleared;
- the waiver whose through-date stops short of the date the payment covered;
- the lower-tier supplier, paid out of the same progress payment, that never
  released at all.

The registry is organised around that:

1. ``set_``   -- is the portfolio file complete?
2. ``party_`` -- is the contract register sound, and does the tier chain hold?
3. ``pay_``   -- is each progress payment fully and sensibly described?
4. ``wvr_``   -- is each waiver well-formed and tied to a real payment?
5. ``cov_``   -- is every payment covered, and every cleared payment released
                 unconditionally through the date it was paid through?
6. ``tier_``  -- did every required lower-tier party release through its parent's
                 paid-through date?
7. ``exp_``   -- does the unwaived exposure per project re-derive?
8. ``rpt_``   -- do the waiver-log counts reconcile?

Design notes
------------
- **Strictly read-only.** Portfolio files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every amount tie is compared with exact ``==``.
  The single tolerant control (``cov_stale_conditional``) reads its ageing band
  from the waiver register rather than inventing one.
- **Absent evidence is not a passing control.** ``set_complete`` runs first and
  owns the "missing artifact" finding.
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
    DOC_CONTRACT_REGISTER,
    DOC_EXPOSURE_SUMMARY,
    DOC_LOWER_TIER_REGISTER,
    DOC_PAYMENT_REGISTER,
    DOC_TYPES,
    DOC_WAIVER_LOG,
    DOC_WAIVER_REGISTER,
    PROJECTS,
    TIER_MIN,
    WAIVER_TYPES,
    WAIVER_UNCONDITIONAL,
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
    """Render an :class:`~lien_engine.money.AmountInvalidError` as a finding."""
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
# Portfolio helpers
# --------------------------------------------------------------------------- #
def _contracts(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CONTRACT_REGISTER), "subcontracts")


def _sub_no(row: dict[str, Any]) -> str:
    value = row.get("sub_id")
    return value if isinstance(value, str) and value else "?"


def _sub_ids(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _contracts(ctx):
        sub_id = _text(row, "sub_id")
        if sub_id and sub_id not in out:
            out[sub_id] = row
    return out


def _payments(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PAYMENT_REGISTER), "payments")


def _pay_no(row: dict[str, Any]) -> str:
    value = row.get("payment_id")
    return value if isinstance(value, str) and value else "?"


def _payments_by_id(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _payments(ctx):
        pay_id = _text(row, "payment_id")
        if pay_id and pay_id not in out:
            out[pay_id] = row
    return out


def _waivers(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_WAIVER_REGISTER), "waivers")


def _waivers_for(ctx: Context, payment_id: str) -> list[dict[str, Any]]:
    """Waiver rows that reference one payment, in file order."""
    return [r for r in _waivers(ctx) if _text(r, "payment_id") == payment_id]


def _parties(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_LOWER_TIER_REGISTER), "parties")


def _exposure_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_EXPOSURE_SUMMARY), "projects")


def _has_unconditional(ctx: Context, payment_id: str) -> bool:
    """True if some waiver of type ``unconditional`` references the payment.

    Coverage-through-date is a separate control (``cov_cleared_unconditional``);
    exposure and the log counts only ask whether an unconditional release exists,
    so they stay robust when a payment's paid-through date is itself malformed.
    """
    return any(
        _text(w, "waiver_type") == WAIVER_UNCONDITIONAL
        for w in _waivers_for(ctx, payment_id)
    )


def unwaived_exposure(ctx: Context) -> dict[str, int]:
    """Unwaived exposure per project, re-derived from payments and waivers.

    A payment adds to its project's exposure until an *unconditional* waiver
    stands behind it. Defined here so the engine and the generator cannot drift on
    what "unwaived" means.
    """
    out: dict[str, int] = {}
    for row in _payments(ctx):
        project = _text(row, "project")
        pay_id = _text(row, "payment_id")
        if project is None or pay_id is None:
            continue
        if _has_unconditional(ctx, pay_id):
            continue
        amount = require_cents(f"payment[{pay_id}].amount_cents", row.get("amount_cents"))
        out[project] = out.get(project, 0) + amount
    return out


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the portfolio depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the portfolio file "
                    f"carries exactly one of each",
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
                f"as_of {ctx.as_of!r} is not a readable date; every coverage and ageing "
                f"test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# party_ -- the contract register and the tier chain
# --------------------------------------------------------------------------- #
@check("party_required_fields")
def check_party_required_fields(ctx: Context) -> list[Finding]:
    """Every subcontract carries the fields the coverage tests read."""
    rule = "party_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CONTRACT_REGISTER)
    if register is None:
        return []
    required = ("sub_id", "name", "project")
    out: list[Finding] = []
    for row in _contracts(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"subcontracts/{_sub_no(row)}"),
                    f"subcontract {_sub_no(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_contracts(ctx))} subcontracts are fully described"
            )
        )
    return out


@check("party_unique_ids")
def check_party_unique_ids(ctx: Context) -> list[Finding]:
    """No sub id appears twice.

    The sub id joins the contract register to every payment and waiver. A
    duplicate makes each of those joins ambiguous.
    """
    rule = "party_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CONTRACT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _contracts(ctx):
        key = _sub_no(row)
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"subcontracts/{sub}"),
            f"sub id {sub} appears {count} times; the joins to payments and waivers "
            f"become ambiguous",
        )
        for sub, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} sub ids are unique"))
    return out


@check("party_tier_valid")
def check_party_tier_valid(ctx: Context) -> list[Finding]:
    """Every subcontract sits at a whole tier of one or greater.

    Tier drives the release chain: a tier-1 sub is paid by the developer, and a
    tier below it is paid out of that money. A tier of zero or a fractional tier
    has no place in that chain.
    """
    rule = "party_tier_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CONTRACT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _contracts(ctx):
        tier = _int(row, "tier")
        if tier is None or tier < TIER_MIN:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"subcontracts/{_sub_no(row)}/tier"),
                    f"subcontract {_sub_no(row)} has tier {row.get('tier')!r}; a tier is a "
                    f"whole number {TIER_MIN} or greater",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_contracts(ctx))} subcontracts carry a valid tier")
        )
    return out


@check("party_lower_tier_parent")
def check_party_lower_tier_parent(ctx: Context) -> list[Finding]:
    """A lower-tier subcontract names a parent that exists above it.

    A tier-2 sub without a real tier-1 parent cannot be tied back to the payment
    it was funded from, so its release obligation can never be checked.
    """
    rule = "party_lower_tier_parent"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CONTRACT_REGISTER)
    if register is None:
        return []
    subs = _sub_ids(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _contracts(ctx):
        tier = _int(row, "tier")
        if tier is None or tier <= TIER_MIN:
            continue
        checked += 1
        parent = _text(row, "parent_sub")
        parent_row = subs.get(parent or "")
        if parent_row is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"subcontracts/{_sub_no(row)}/parent_sub"),
                    f"subcontract {_sub_no(row)} is tier {tier} but names parent "
                    f"{parent!r}, which is not in the register; its release cannot be "
                    f"tied to a payment",
                )
            )
            continue
        parent_tier = _int(parent_row, "tier")
        if parent_tier is not None and parent_tier >= tier:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"subcontracts/{_sub_no(row)}/parent_sub"),
                    f"subcontract {_sub_no(row)} is tier {tier} but its parent "
                    f"{parent} is tier {parent_tier}; a parent must sit above its child",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} lower-tier subcontracts sit under a real parent")
        )
    return out


@check("party_project_exists")
def check_party_project_exists(ctx: Context) -> list[Finding]:
    """Every subcontract names a project the portfolio actually runs.

    A mistyped project name is not a loud error: it silently drops the party out
    of the per-project exposure roll-up, and the total still looks complete.
    """
    rule = "party_project_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CONTRACT_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"subcontracts/{_sub_no(row)}/project"),
            f"subcontract {_sub_no(row)} names project {_text(row, 'project')!r}, "
            f"which is not one of {PROJECTS}",
        )
        for row in _contracts(ctx)
        if _text(row, "project") not in PROJECTS
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_contracts(ctx))} subcontracts name a known project")
        )
    return out


# --------------------------------------------------------------------------- #
# pay_ -- the payment register
# --------------------------------------------------------------------------- #
@check("pay_required_fields")
def check_pay_required_fields(ctx: Context) -> list[Finding]:
    """Every progress payment carries the fields coverage reads."""
    rule = "pay_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    required = ("payment_id", "sub_id", "project", "period", "paid_through_date")
    out: list[Finding] = []
    for row in _payments(ctx):
        missing = [f for f in required if not _text(row, f)]
        if "amount_cents" not in row:
            missing.append("amount_cents")
        if "cleared" not in row:
            missing.append("cleared")
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payments/{_pay_no(row)}"),
                    f"payment {_pay_no(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_payments(ctx))} payments are fully described")
        )
    return out


@check("pay_sub_exists")
def check_pay_sub_exists(ctx: Context) -> list[Finding]:
    """Every payment names a subcontractor in the contract register."""
    rule = "pay_sub_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    subs = _sub_ids(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"payments/{_pay_no(row)}/sub_id"),
            f"payment {_pay_no(row)} pays sub {_text(row, 'sub_id')!r}, which is not in "
            f"the contract register",
        )
        for row in _payments(ctx)
        if _text(row, "sub_id") and _text(row, "sub_id") not in subs
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every payment names a sub in the register")
        )
    return out


@check("pay_amount_positive")
def check_pay_amount_positive(ctx: Context) -> list[Finding]:
    """Every progress payment is a positive integer-cent amount.

    A payment is money that already left the building; a zero or negative one is
    not a progress payment, and a fractional-cent one was never a real figure.
    """
    rule = "pay_amount_positive"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payments(ctx):
        with amount_guard(rule, out):
            amount = require_cents(
                f"payment[{_pay_no(row)}].amount_cents", row.get("amount_cents")
            )
            checked += 1
            if amount <= 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"payments/{_pay_no(row)}/amount_cents"),
                        f"payment {_pay_no(row)} is {fmt(amount)}; a progress payment must "
                        f"be a positive amount",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} payments are positive"))
    return out


@check("pay_dates_sensible")
def check_pay_dates_sensible(ctx: Context) -> list[Finding]:
    """Each payment's paid-through date is readable and not in the future.

    The paid-through date is the far edge of what a waiver has to cover. A date the
    review has not yet reached, or a date that will not parse, makes every coverage
    test downstream meaningless.
    """
    rule = "pay_dates_sensible"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payments(ctx):
        paid_through = _parse_date(row.get("paid_through_date"))
        if paid_through is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payments/{_pay_no(row)}/paid_through_date"),
                    f"payment {_pay_no(row)} has paid-through date "
                    f"{row.get('paid_through_date')!r}, which is not a readable date",
                )
            )
            continue
        checked += 1
        if paid_through > as_of:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payments/{_pay_no(row)}/paid_through_date"),
                    f"payment {_pay_no(row)} is paid through {paid_through.isoformat()}, "
                    f"after the review date {as_of.isoformat()}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} paid-through dates are sensible")
        )
    return out


# --------------------------------------------------------------------------- #
# wvr_ -- the waiver register
# --------------------------------------------------------------------------- #
@check("wvr_required_fields")
def check_wvr_required_fields(ctx: Context) -> list[Finding]:
    """Every waiver carries the fields the coverage tests read."""
    rule = "wvr_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WAIVER_REGISTER)
    if register is None:
        return []
    required = ("waiver_id", "sub_id", "project", "waiver_type", "through_date", "payment_id")
    out: list[Finding] = []
    for row in _waivers(ctx):
        wid = _text(row, "waiver_id") or "?"
        missing = [f for f in required if not _text(row, f)]
        if "amount_cents" not in row:
            missing.append("amount_cents")
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"waivers/{wid}"),
                    f"waiver {wid} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_waivers(ctx))} waivers are fully described")
        )
    return out


@check("wvr_unique_ids")
def check_wvr_unique_ids(ctx: Context) -> list[Finding]:
    """No waiver id appears twice."""
    rule = "wvr_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WAIVER_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _waivers(ctx):
        key = _text(row, "waiver_id") or "?"
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"waivers/{wid}"),
            f"waiver id {wid} appears {count} times; a waiver must be uniquely "
            f"identifiable to be tracked",
        )
        for wid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} waiver ids are unique"))
    return out


@check("wvr_type_valid")
def check_wvr_type_valid(ctx: Context) -> list[Finding]:
    """Every waiver is either conditional or unconditional.

    The distinction is the whole point: only an *unconditional* waiver actually
    releases the lien once the money has cleared. A waiver of some third,
    unrecognised type cannot be reasoned about at all.
    """
    rule = "wvr_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WAIVER_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"waivers/{_text(row, 'waiver_id') or '?'}/waiver_type"),
            f"waiver {_text(row, 'waiver_id') or '?'} is type "
            f"{_text(row, 'waiver_type')!r}, which is not one of {WAIVER_TYPES}",
        )
        for row in _waivers(ctx)
        if _text(row, "waiver_type") not in WAIVER_TYPES
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_waivers(ctx))} waivers carry a known type")
        )
    return out


@check("wvr_references_payment")
def check_wvr_references_payment(ctx: Context) -> list[Finding]:
    """Every waiver references a payment that exists.

    A waiver that releases against a payment not in the register is releasing
    against nothing the engine can see, and its coverage can never be proven.
    """
    rule = "wvr_references_payment"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WAIVER_REGISTER)
    if register is None:
        return []
    payments = _payments_by_id(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"waivers/{_text(row, 'waiver_id') or '?'}/payment_id"),
            f"waiver {_text(row, 'waiver_id') or '?'} references payment "
            f"{_text(row, 'payment_id')!r}, which is not in the payment register",
        )
        for row in _waivers(ctx)
        if _text(row, "payment_id") and _text(row, "payment_id") not in payments
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every waiver references a real payment")
        )
    return out


@check("wvr_amount_ties_payment")
def check_wvr_amount_ties_payment(ctx: Context) -> list[Finding]:
    """A waiver releases exactly the amount of the payment it backs.

    A waiver for less than the payment leaves the balance unwaived; a waiver for
    more releases a lien over money that was never paid. Either way the release no
    longer matches the money, and only an exact tie proves it does.
    """
    rule = "wvr_amount_ties_payment"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WAIVER_REGISTER)
    if register is None:
        return []
    payments = _payments_by_id(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _waivers(ctx):
        wid = _text(row, "waiver_id") or "?"
        pay_id = _text(row, "payment_id")
        payment = payments.get(pay_id or "")
        if payment is None:
            continue  # wvr_references_payment owns this
        with amount_guard(rule, out):
            waived = require_cents(f"waiver[{wid}].amount_cents", row.get("amount_cents"))
            paid = require_cents(
                f"payment[{pay_id}].amount_cents", payment.get("amount_cents")
            )
            checked += 1
            if waived != paid:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"waivers/{wid}/amount_cents"),
                        f"waiver {wid} releases {fmt(waived)} against a payment of "
                        f"{fmt(paid)} (difference {fmt(waived - paid)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} waivers tie the payment they back")
        )
    return out


# --------------------------------------------------------------------------- #
# cov_ -- coverage of the money by the waivers
# --------------------------------------------------------------------------- #
@check("cov_payment_covered")
def check_cov_payment_covered(ctx: Context) -> list[Finding]:
    """Every payment is backed by a waiver that runs at least as far as the money.

    The first line of defence: a payment with no waiver whose through-date reaches
    its paid-through date is money out the door with the lien right still live.
    Whether that waiver is conditional or unconditional is the next control's job;
    this one only asks that *some* release reaches the date.
    """
    rule = "cov_payment_covered"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payments(ctx):
        paid_through = _parse_date(row.get("paid_through_date"))
        if paid_through is None:
            continue  # pay_dates_sensible owns this
        pay_id = _pay_no(row)
        checked += 1
        covering = [
            w
            for w in _waivers_for(ctx, pay_id)
            if (td := _parse_date(w.get("through_date"))) is not None and td >= paid_through
        ]
        if not covering:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payments/{pay_id}/paid_through_date"),
                    f"payment {pay_id} is paid through {paid_through.isoformat()} but no "
                    f"waiver releases at least that far; the lien right is still live",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} payments are covered to their paid-through date")
        )
    return out


@check("cov_cleared_unconditional")
def check_cov_cleared_unconditional(ctx: Context) -> list[Finding]:
    """A cleared payment carries an unconditional waiver through its paid date.

    This is the control the engine exists for. A conditional waiver releases
    *only if* the payment clears; once it has cleared, the release is owed
    unconditionally. A cleared payment sitting behind a conditional waiver alone
    -- because the unconditional was never chased -- looks covered and is not.
    """
    rule = "cov_cleared_unconditional"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payments(ctx):
        if row.get("cleared") is not True:
            continue
        paid_through = _parse_date(row.get("paid_through_date"))
        if paid_through is None:
            continue  # pay_dates_sensible owns this
        pay_id = _pay_no(row)
        checked += 1
        released = [
            w
            for w in _waivers_for(ctx, pay_id)
            if _text(w, "waiver_type") == WAIVER_UNCONDITIONAL
            and (td := _parse_date(w.get("through_date"))) is not None
            and td >= paid_through
        ]
        if not released:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payments/{pay_id}/cleared"),
                    f"payment {pay_id} cleared and is paid through "
                    f"{paid_through.isoformat()}, but no unconditional waiver releases "
                    f"through that date; a conditional release does not survive the "
                    f"cheque clearing",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} cleared payments are released unconditionally")
        )
    return out


@check("cov_stale_conditional")
def check_cov_stale_conditional(ctx: Context) -> list[Finding]:
    """A conditional waiver that has aged past its upgrade window is flagged.

    Deliberately a review signal, and the ageing band comes from the waiver
    register rather than the engine's opinion. A payment that is still uncleared
    long after it was paid through is a conditional waiver nobody upgraded; it is
    not yet a failure, but it is exactly what a controller should chase before it
    becomes one.
    """
    rule = "cov_stale_conditional"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_WAIVER_REGISTER)
    pay_register = ctx.one(DOC_PAYMENT_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or pay_register is None or as_of is None:
        return []
    band = _int(register, "stale_conditional_days")
    if band is None or band < 0:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payments(ctx):
        if row.get("cleared") is True:
            continue
        paid_through = _parse_date(row.get("paid_through_date"))
        if paid_through is None:
            continue
        pay_id = _pay_no(row)
        has_conditional = any(
            _text(w, "waiver_type") != WAIVER_UNCONDITIONAL
            for w in _waivers_for(ctx, pay_id)
        )
        if not has_conditional:
            continue
        checked += 1
        aged = (as_of - paid_through).days
        if aged > band:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(pay_register, f"payments/{pay_id}/paid_through_date"),
                    f"payment {pay_id} is paid through {paid_through.isoformat()} and "
                    f"still uncleared {aged} days later (band {band}); its conditional "
                    f"waiver should have been upgraded by now",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} conditional waivers are inside the upgrade window")
        )
    return out


# --------------------------------------------------------------------------- #
# tier_ -- lower-tier releases
# --------------------------------------------------------------------------- #
def _required_through(ctx: Context, parent_sub: str, project: str) -> date | None:
    """The date a lower-tier party must release through: the parent's latest paid.

    Re-derived from the parent tier-1 sub's own payments so the generator and the
    engine cannot drift on what "far enough" means.
    """
    dates = [
        d
        for row in _payments(ctx)
        if _text(row, "sub_id") == parent_sub and _text(row, "project") == project
        if (d := _parse_date(row.get("paid_through_date"))) is not None
    ]
    return max(dates) if dates else None


@check("tier_party_has_waiver")
def check_tier_party_has_waiver(ctx: Context) -> list[Finding]:
    """Every required lower-tier party has actually released something.

    The subcontractor's own release does not reach its rebar supplier. A required
    party with no waiver-through date on record is a downstream lien that survived
    the upstream release.
    """
    rule = "tier_party_has_waiver"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LOWER_TIER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _parties(ctx):
        party = _text(row, "party_id") or "?"
        if _parse_date(row.get("waiver_through_date")) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parties/{party}/waiver_through_date"),
                    f"lower-tier party {party} has no readable waiver-through date; it "
                    f"has not released, and its lien survives the payment it was funded "
                    f"from",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_parties(ctx))} lower-tier parties have released")
        )
    return out


@check("tier_waiver_covers")
def check_tier_waiver_covers(ctx: Context) -> list[Finding]:
    """A lower-tier release runs through its parent's paid-through date.

    A supplier that releases only through last month, while its sub was paid
    through this month, has left the most recent tranche of downstream work
    unwaived.
    """
    rule = "tier_waiver_covers"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LOWER_TIER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _parties(ctx):
        party = _text(row, "party_id") or "?"
        waived = _parse_date(row.get("waiver_through_date"))
        required = _parse_date(row.get("required_through_date"))
        if waived is None or required is None:
            continue
        checked += 1
        if waived < required:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parties/{party}/waiver_through_date"),
                    f"lower-tier party {party} releases through {waived.isoformat()} but "
                    f"its parent was paid through {required.isoformat()}; the gap is "
                    f"unwaived downstream work",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} lower-tier releases reach the parent's paid date")
        )
    return out


@check("tier_required_recomputes")
def check_tier_required_recomputes(ctx: Context) -> list[Finding]:
    """The date a party must release through re-derives from its parent's payments.

    The required date is not a figure to be trusted; it is the parent tier-1 sub's
    latest paid-through date, and if the register carries a different one the whole
    coverage test above is aimed at the wrong day.
    """
    rule = "tier_required_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LOWER_TIER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _parties(ctx):
        party = _text(row, "party_id") or "?"
        parent = _text(row, "parent_sub")
        project = _text(row, "project")
        stated = _parse_date(row.get("required_through_date"))
        if parent is None or project is None or stated is None:
            continue
        derived = _required_through(ctx, parent, project)
        if derived is None:
            continue
        checked += 1
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parties/{party}/required_through_date"),
                    f"lower-tier party {party} records a required-through date of "
                    f"{stated.isoformat()}; its parent {parent} was last paid through "
                    f"{derived.isoformat()}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} required-through dates re-derive from the parent")
        )
    return out


# --------------------------------------------------------------------------- #
# exp_ -- unwaived exposure per project
# --------------------------------------------------------------------------- #
@check("exp_recomputes")
def check_exp_recomputes(ctx: Context) -> list[Finding]:
    """Unwaived exposure per project re-derives from payments and waivers.

    The exposure figure is the number a controller reports to the lender: how much
    has been paid out that no unconditional waiver yet stands behind. The engine
    re-derives it from the payments and the releases rather than trusting the
    carried-forward total.
    """
    rule = "exp_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_EXPOSURE_SUMMARY)
    if summary is None:
        return []
    out: list[Finding] = []
    derived = unwaived_exposure(ctx)
    checked = 0
    for row in _exposure_rows(ctx):
        project = _text(row, "project")
        if project is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"exposure[{project}].unwaived_exposure_cents",
                row.get("unwaived_exposure_cents"),
            )
            checked += 1
            want = derived.get(project, 0)
            if stated != want:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{project}/unwaived_exposure_cents"),
                        f"project {project} reports {fmt(stated)} of unwaived exposure; "
                        f"payments not yet released unconditionally sum to {fmt(want)} "
                        f"(difference {fmt(stated - want)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} project exposures re-derive")
        )
    return out


@check("exp_all_projects_present")
def check_exp_all_projects_present(ctx: Context) -> list[Finding]:
    """Every project with a payment appears in the exposure summary.

    A project dropped from the summary reports no exposure at all, which reads as
    fully waived when it may be the opposite.
    """
    rule = "exp_all_projects_present"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_EXPOSURE_SUMMARY)
    if summary is None:
        return []
    listed = {_text(row, "project") for row in _exposure_rows(ctx)}
    with_payments = sorted(
        {p for row in _payments(ctx) if (p := _text(row, "project")) is not None}
    )
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(summary, f"projects/{project}"),
            f"project {project} carries payments but is absent from the exposure "
            f"summary; its unwaived exposure is reported as nothing",
        )
        for project in with_payments
        if project not in listed
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(with_payments)} paid projects appear in the summary")
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the waiver log roll-up
# --------------------------------------------------------------------------- #
@check("rpt_waiver_counts_tie")
def check_rpt_waiver_counts_tie(ctx: Context) -> list[Finding]:
    """The waiver-log counts reconcile to the waiver register."""
    rule = "rpt_waiver_counts_tie"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_WAIVER_LOG)
    if log is None:
        return []
    waivers = _waivers(ctx)
    conditional = sum(1 for w in waivers if _text(w, "waiver_type") != WAIVER_UNCONDITIONAL)
    unconditional = sum(1 for w in waivers if _text(w, "waiver_type") == WAIVER_UNCONDITIONAL)
    checks = (
        ("waiver_count", len(waivers)),
        ("conditional_count", conditional),
        ("unconditional_count", unconditional),
    )
    out: list[Finding] = []
    for key, derived in checks:
        stated = _int(log, key)
        if stated is None or stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, key),
                    f"{key} in the waiver log is {log.get(key)!r}; the register holds "
                    f"{derived}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"the waiver log reconciles to {len(waivers)} waivers")
        )
    return out


@check("rpt_covered_count_ties")
def check_rpt_covered_count_ties(ctx: Context) -> list[Finding]:
    """The count of unconditionally-released payments reconciles.

    A review-level reconciliation on the headline figure of the log -- how many
    payments are fully released -- which is the one number a reader is most likely
    to quote and least likely to recompute.
    """
    rule = "rpt_covered_count_ties"
    _sev(rule, Status.FLAG)
    log = ctx.one(DOC_WAIVER_LOG)
    if log is None:
        return []
    derived = sum(
        1
        for row in _payments(ctx)
        if (pid := _text(row, "payment_id")) is not None and _has_unconditional(ctx, pid)
    )
    stated = _int(log, "covered_payment_count")
    out: list[Finding] = []
    if stated is None or stated != derived:
        out.append(
            Finding(
                rule,
                Status.FLAG,
                ctx.loc(log, "covered_payment_count"),
                f"covered_payment_count in the waiver log is {log.get('covered_payment_count')!r}; "
                f"{derived} payments carry an unconditional release",
            )
        )
    else:
        out.append(
            Finding(rule, Status.PASS, "-", f"{derived} unconditionally-released payments reconcile")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one portfolio file."""
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
    """Analyze every ``.json`` portfolio file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of portfolio-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
