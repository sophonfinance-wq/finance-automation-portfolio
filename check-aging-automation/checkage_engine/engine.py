"""
Outstanding-check aging and escheatment control engine (READ-ONLY).
===================================================================

Loads each aging file (a ``.json`` file produced by
:mod:`checkage_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **what is still out there**, not about whether the payment
should have been made. Approval, coding and release are somebody else's controls.
This one starts once the check has left the building: of everything issued, what
has never cleared, how old is it, and what has to happen to it now?

The shape of the problem
------------------------
A check register is a list of promises the bank has not yet been asked to keep.
Each row carries a check number, a check date, a check type, a payee, the amount
issued, the amount cleared and the date it cleared. Beside it sit the withdrawn
promises -- voided, zero-dollar and stop-payment checks.

Three failures hide in that, and none of them look wrong in a register:

* the outstanding schedule is maintained beside the register instead of derived
  from it, so it drifts from the evidence and the bank reconciliation ties to the
  drift;
* a voided, zero-dollar or stop-payment check keeps living -- still counted as
  outstanding, or with a void that never nets the amount to zero;
* the clock runs. Six months out the item is stale-dated and the bank may refuse
  it; a dormancy period out it is unclaimed property owed to a state, and the
  register looks exactly the same the day before and the day after.

The registry is organised around that:

1. ``set_``   -- is the aging file complete?
2. ``acct_``  -- is the bank account register sound and jurisdictioned?
3. ``chk_``   -- is every check row well-formed, unique, attributable and reconciled
   issued-against-cleared?
4. ``void_``  -- are the withdrawn checks really withdrawn -- off the outstanding
   set and netted to zero?
5. ``age_``   -- does the outstanding set, its aging and its follow-up marker
   re-derive from the register?
6. ``esc_``   -- is the escheatment schedule exactly the dormant items, reported to
   the right jurisdiction?
7. ``rpt_``   -- does the bank reconciliation tie the re-derived evidence?

Design notes
------------
- **Strictly read-only.** Aging files are parsed and never written back. The
  engine never voids, re-issues, escheats or pays anything.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every total is compared with exact ``==``.
- **One set of aging predicates.** Controls and the generator share the kernel in
  :mod:`checkage_engine.aging`, so a schedule cannot disagree with the data that
  produced it.
- **Every age is measured to the file's own ``as_of``,** never the system clock.
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

from .aging import (
    CheckLine,
    age_days,
    bucket_for,
    is_dormant,
    is_outstanding,
    is_stale_dated,
)
from .model import (
    AGING_BUCKETS,
    BUCKET_LABELS,
    CHECK_TYPES,
    DISPOSITIONS,
    DOC_ACCOUNT_REGISTER,
    DOC_BANK_RECONCILIATION,
    DOC_CHECK_REGISTER,
    DOC_ESCHEATMENT_SCHEDULE,
    DOC_OUTSTANDING_SCHEDULE,
    DOC_TYPES,
    DOC_VOID_REGISTER,
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
    """Render an :class:`~checkage_engine.money.AmountInvalidError` as a finding."""
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
# Aging-file helpers
# --------------------------------------------------------------------------- #
def _accounts(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ACCOUNT_REGISTER), "accounts")


def _account_id(row: dict[str, Any]) -> str:
    value = row.get("account_id")
    return value if isinstance(value, str) and value else "?"


def _account_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _accounts(ctx):
        aid = _account_id(row)
        if aid != "?" and aid not in out:
            out[aid] = row
    return out


def _checks(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CHECK_REGISTER), "checks")


def _check_number(row: dict[str, Any]) -> str:
    value = row.get("check_number")
    return value if isinstance(value, str) and value else "?"


def _key(row: dict[str, Any]) -> tuple[str, str]:
    """The identity of a check: its number *within* the account it was drawn on.

    Check numbers repeat across accounts by design -- two disbursement accounts
    each run their own series -- so the account is half the key. A control that
    keyed on the number alone would call an honest register duplicated.
    """
    return (_account_id(row), _check_number(row))


def _check_map(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _checks(ctx):
        key = _key(row)
        if key not in out:
            out[key] = row
    return out


def _voids(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_VOID_REGISTER), "entries")


def _void_keys(ctx: Context) -> frozenset[tuple[str, str]]:
    """``(account_id, check_number)`` of every withdrawn check.

    Reads no amount and no date, so building the withdrawal set can never itself
    raise on a malformed figure -- the amounts are read later, by the control that
    needs them.
    """
    return frozenset(_key(row) for row in _voids(ctx))


def _outstanding_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_OUTSTANDING_SCHEDULE), "items")


def _escheat_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ESCHEATMENT_SCHEDULE), "items")


def _check_line(row: dict[str, Any], check_date: date) -> CheckLine:
    """Read a register row into a :class:`~checkage_engine.aging.CheckLine`.

    Raises :class:`AmountInvalidError` if either amount is not integer cents.
    """
    account_id, check_number = _key(row)
    return CheckLine(
        account_id=account_id,
        check_number=check_number,
        check_date=check_date,
        check_amount_cents=require_cents(
            f"check[{account_id}/{check_number}].check_amount_cents",
            row.get("check_amount_cents"),
        ),
        cleared_amount_cents=require_cents(
            f"check[{account_id}/{check_number}].cleared_amount_cents",
            row.get("cleared_amount_cents"),
        ),
        cleared_date=_parse_date(row.get("cleared_date")),
    )


# --------------------------------------------------------------------------- #
# Re-derivation -- shared with the generator
# --------------------------------------------------------------------------- #
def recompute_outstanding(ctx: Context, as_of: date) -> list[dict[str, Any]]:
    """The outstanding-check schedule re-derived from the check register.

    One entry per check that nothing has cleared against and that no void,
    zero-dollar or stop-payment entry has withdrawn, carried with the age, aging
    band and follow-up marker the kernel derives for it. Rows whose check date
    cannot be read are skipped; ``chk_required_fields`` owns that gap.

    Shared with the generator through :mod:`checkage_engine.aging`, so the set the
    engine recomputes is the set that produced the data.

    Raises :class:`AmountInvalidError` if an amount it must read is not integer
    cents; the calling control contains that.
    """
    voided = _void_keys(ctx)
    stale = ctx.stale_dated_days
    entries: list[dict[str, Any]] = []
    for row in _checks(ctx):
        check_date = _parse_date(row.get("check_date"))
        if check_date is None:
            continue
        line = _check_line(row, check_date)
        if not is_outstanding(line, voided):
            continue
        age = age_days(check_date, as_of)
        entries.append(
            {
                "account_id": line.account_id,
                "check_number": line.check_number,
                "check_date": check_date.isoformat(),
                "amount_cents": line.check_amount_cents,
                "age_days": age,
                "aging_bucket": bucket_for(age),
                "follow_up_required": is_stale_dated(age, stale),
            }
        )
    entries.sort(key=lambda e: (e["account_id"], e["check_number"]))
    return entries


def recompute_escheatment(
    ctx: Context, as_of: date, dormancy_days: int
) -> list[dict[str, Any]]:
    """The escheatment schedule re-derived from the outstanding set.

    One entry per outstanding item that has run the full dormancy period, reported
    to the escheat jurisdiction declared for the account it was drawn on. An
    account with no declared jurisdiction reports ``"-"`` here;
    ``acct_jurisdiction_declared`` owns that gap.
    """
    accounts = _account_map(ctx)
    entries: list[dict[str, Any]] = []
    for item in recompute_outstanding(ctx, as_of):
        if not is_dormant(int(item["age_days"]), dormancy_days):
            continue
        account = accounts.get(str(item["account_id"]))
        jurisdiction = _text(account, "escheat_jurisdiction") if account else None
        entries.append(
            {
                "account_id": item["account_id"],
                "check_number": item["check_number"],
                "amount_cents": item["amount_cents"],
                "age_days": item["age_days"],
                "escheat_jurisdiction": jurisdiction or "-",
            }
        )
    entries.sort(key=lambda e: (e["account_id"], e["check_number"]))
    return entries


def recompute_bucket_totals(ctx: Context, as_of: date) -> list[dict[str, Any]]:
    """The aging subtotals re-derived from the outstanding set.

    Every band in :data:`~checkage_engine.model.AGING_BUCKETS` is emitted, empty
    ones included, so the reconciliation's shape is stable from period to period
    and a band that empties out is visible as a zero rather than as an absence.
    """
    counts: dict[str, int] = {label: 0 for label in BUCKET_LABELS}
    amounts: dict[str, int] = {label: 0 for label in BUCKET_LABELS}
    for item in recompute_outstanding(ctx, as_of):
        label = bucket_for(int(item["age_days"]))
        counts[label] = counts.get(label, 0) + 1
        amounts[label] = amounts.get(label, 0) + int(item["amount_cents"])
    return [
        {"bucket": label, "count": counts[label], "amount_cents": amounts[label]}
        for label in BUCKET_LABELS
    ]


def _outstanding_identity(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("account_id"),
        entry.get("check_number"),
        entry.get("amount_cents"),
    )


def _escheat_identity(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("account_id"),
        entry.get("check_number"),
        entry.get("amount_cents"),
        entry.get("age_days"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the aging file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the aging file carries "
                    f"exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} outstanding-check artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every age, stale-dating "
                f"and dormancy test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# acct_ -- the disbursement bank accounts
# --------------------------------------------------------------------------- #
@check("acct_unique_ids")
def check_acct_unique_ids(ctx: Context) -> list[Finding]:
    """No bank account id appears twice.

    The account id is half of every check's identity and the key to its escheat
    jurisdiction. A duplicate makes a check number ambiguous about which series it
    belongs to and an escheatable item ambiguous about which state it reports to.
    """
    rule = "acct_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ACCOUNT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _accounts(ctx):
        aid = _account_id(row)
        seen[aid] = seen.get(aid, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"accounts/{aid}"),
            f"bank account {aid} appears {count} times; a check drawn on it cannot be "
            f"attributed to one account series",
        )
        for aid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} bank account ids are unique")
        )
    return out


@check("acct_jurisdiction_declared")
def check_acct_jurisdiction_declared(ctx: Context) -> list[Finding]:
    """Every bank account declares the escheat jurisdiction it reports to.

    Unclaimed property reports to a jurisdiction, not to a company. An account
    with none declared cannot escheat anything, so a dormant item drawn on it
    would sit on a schedule addressed to nobody.
    """
    rule = "acct_jurisdiction_declared"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ACCOUNT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _accounts(ctx):
        if _text(row, "escheat_jurisdiction") is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"accounts/{_account_id(row)}/escheat_jurisdiction"),
                    f"bank account {_account_id(row)} declares no escheat jurisdiction; a "
                    f"dormant item drawn on it has nowhere to report",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_accounts(ctx))} bank accounts declare an escheat jurisdiction",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# chk_ -- the check register
# --------------------------------------------------------------------------- #
@check("chk_required_fields")
def check_chk_required_fields(ctx: Context) -> list[Finding]:
    """Every check row carries the descriptive fields the controls read."""
    rule = "chk_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHECK_REGISTER)
    if register is None:
        return []
    required = ("check_number", "account_id", "check_date", "check_type", "payee")
    out: list[Finding] = []
    for row in _checks(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            account_id, number = _key(row)
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"checks/{account_id}/{number}"),
                    f"check {account_id}/{number} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_checks(ctx))} check rows carry their required fields",
            )
        )
    return out


@check("chk_number_unique_per_account")
def check_chk_number_unique_per_account(ctx: Context) -> list[Finding]:
    """No check number appears twice within one bank account.

    Two accounts may legitimately run the same number, so the test is scoped to
    the account. Inside an account a repeat means one physical check was recorded
    twice, or two were cut on one number -- and either way the outstanding set can
    no longer say what is actually out there.
    """
    rule = "chk_number_unique_per_account"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHECK_REGISTER)
    if register is None:
        return []
    seen: dict[tuple[str, str], int] = {}
    for row in _checks(ctx):
        key = _key(row)
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"checks/{account_id}/{number}"),
            f"check number {number} appears {count} times in bank account "
            f"{account_id}; the register cannot say which row is the obligation",
        )
        for (account_id, number), count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(seen)} check numbers are unique within their bank account",
            )
        )
    return out


@check("chk_account_exists")
def check_chk_account_exists(ctx: Context) -> list[Finding]:
    """Every check is drawn on an account in the bank account register."""
    rule = "chk_account_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHECK_REGISTER)
    if register is None:
        return []
    accounts = _account_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"checks/{_account_id(row)}/{_check_number(row)}/account_id"),
            f"check {_check_number(row)} is drawn on account "
            f"{_text(row, 'account_id')!r}, which is not in the bank account register",
        )
        for row in _checks(ctx)
        if _text(row, "account_id") and _text(row, "account_id") not in accounts
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every check is drawn on an account in the register",
            )
        )
    return out


@check("chk_type_valid")
def check_chk_type_valid(ctx: Context) -> list[Finding]:
    """Every check declares a known check type.

    Manual and system checks are the two ways a check leaves the building, and the
    split matters: manual checks skip the disbursement run and are the ones that
    age unnoticed. An unknown type means the register cannot say which population
    an item belongs to.
    """
    rule = "chk_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHECK_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"checks/{_account_id(row)}/{_check_number(row)}/check_type"),
            f"check {_account_id(row)}/{_check_number(row)} is typed "
            f"{_text(row, 'check_type')!r}, which is not one of {CHECK_TYPES}",
        )
        for row in _checks(ctx)
        if _text(row, "check_type") and _text(row, "check_type") not in CHECK_TYPES
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_checks(ctx))} checks carry a known check type",
            )
        )
    return out


@check("chk_date_not_future")
def check_chk_date_not_future(ctx: Context) -> list[Finding]:
    """No check is dated after the as-of date.

    Age is measured forwards from the check date to the as-of date. A check dated
    after it produces a negative age, which lands in the youngest aging band and
    makes an item that cannot have been issued yet look like the freshest thing on
    the schedule.
    """
    rule = "chk_date_not_future"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHECK_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _checks(ctx):
        check_date = _parse_date(row.get("check_date"))
        if check_date is None:
            continue  # chk_required_fields owns this
        checked += 1
        if check_date > as_of:
            account_id, number = _key(row)
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"checks/{account_id}/{number}/check_date"),
                    f"check {account_id}/{number} is dated {check_date.isoformat()}, after "
                    f"the as-of date {as_of.isoformat()}; its age would be negative",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} check dates are on or before the as-of date",
            )
        )
    return out


@check("chk_cleared_pairing")
def check_chk_cleared_pairing(ctx: Context) -> list[Finding]:
    """A cleared amount and a cleared date arrive together, or not at all.

    The outstanding test reads both halves -- nothing cleared *and* no cleared date
    -- so a row carrying one without the other is the one shape that makes the test
    ambiguous. An amount with no date is a clearing nobody dated; a date with no
    amount is an item the schedule will keep reporting as outstanding forever.
    """
    rule = "chk_cleared_pairing"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHECK_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _checks(ctx):
        account_id, number = _key(row)
        with amount_guard(rule, out):
            cleared = require_cents(
                f"check[{account_id}/{number}].cleared_amount_cents",
                row.get("cleared_amount_cents"),
            )
            has_date = _text(row, "cleared_date") is not None
            checked += 1
            if (cleared != 0) != has_date:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"checks/{account_id}/{number}/cleared_date"),
                        f"check {account_id}/{number} carries a cleared amount of "
                        f"{fmt(cleared)} and "
                        f"{'a' if has_date else 'no'} cleared date; the two halves of the "
                        f"clearing must arrive together or the outstanding test is ambiguous",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} check rows pair their cleared amount and cleared date",
            )
        )
    return out


@check("chk_cleared_ties_issued")
def check_chk_cleared_ties_issued(ctx: Context) -> list[Finding]:
    """A cleared check cleared for exactly the amount it was issued for.

    This is the issued-against-cleared reconciliation, compared with exact ``==``.
    A cleared amount that differs from the issued amount is either an altered item
    or a partial presentment, and in both cases the difference is a real
    obligation that no longer appears anywhere: the check is off the outstanding
    schedule because something cleared, and the shortfall is off it too.
    """
    rule = "chk_cleared_ties_issued"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHECK_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _checks(ctx):
        account_id, number = _key(row)
        if _text(row, "cleared_date") is None:
            continue  # nothing cleared; the aging controls own this row
        with amount_guard(rule, out):
            cleared = require_cents(
                f"check[{account_id}/{number}].cleared_amount_cents",
                row.get("cleared_amount_cents"),
            )
            if cleared == 0:
                continue  # chk_cleared_pairing owns this shape
            issued = require_cents(
                f"check[{account_id}/{number}].check_amount_cents",
                row.get("check_amount_cents"),
            )
            checked += 1
            if cleared != issued:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"checks/{account_id}/{number}/cleared_amount_cents"),
                        f"check {account_id}/{number} was issued for {fmt(issued)} and "
                        f"cleared for {fmt(cleared)}; the {fmt(issued - cleared)} difference "
                        f"is an obligation that appears on no schedule",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} cleared checks cleared for the amount they were issued for",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# void_ -- the withdrawn checks
# --------------------------------------------------------------------------- #
@check("void_disposition_valid")
def check_void_disposition_valid(ctx: Context) -> list[Finding]:
    """Every void-register entry carries a known disposition and names a real check.

    Voided, zero-dollar and stop-payment are the three ways a promise is withdrawn.
    An unknown disposition is a withdrawal nobody can classify, and an entry that
    names no check in the register withdraws nothing at all while still removing a
    key from the outstanding set.
    """
    rule = "void_disposition_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_VOID_REGISTER)
    if register is None:
        return []
    checks = _check_map(ctx)
    out: list[Finding] = []
    for row in _voids(ctx):
        account_id, number = _key(row)
        disposition = _text(row, "disposition")
        if disposition not in DISPOSITIONS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entries/{account_id}/{number}/disposition"),
                    f"void entry {account_id}/{number} is dispositioned {disposition!r}, "
                    f"which is not one of {DISPOSITIONS}",
                )
            )
        if (account_id, number) not in checks:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entries/{account_id}/{number}"),
                    f"void entry {account_id}/{number} names no check in the register; it "
                    f"withdraws nothing while still suppressing that key",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_voids(ctx))} void entries are classified and name a real check",
            )
        )
    return out


@check("void_not_outstanding")
def check_void_not_outstanding(ctx: Context) -> list[Finding]:
    """No withdrawn check appears on the outstanding schedule.

    A voided, zero-dollar or stop-payment check is a promise that was taken back.
    Leaving it on the schedule puts a cancelled obligation on the bank
    reconciliation and, worse, ages it -- so a check that was never owed can walk
    all the way through the dormancy period and be escheated to a state.
    """
    rule = "void_not_outstanding"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_OUTSTANDING_SCHEDULE)
    if schedule is None:
        return []
    voided = _void_keys(ctx)
    out: list[Finding] = []
    for row in _outstanding_rows(ctx):
        account_id, number = _key(row)
        if (account_id, number) in voided:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"items/{account_id}/{number}"),
                    f"check {account_id}/{number} is on the outstanding schedule but the "
                    f"void register records it as withdrawn; a cancelled promise is not "
                    f"an outstanding obligation",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"none of the {len(voided)} withdrawn checks appears on the outstanding "
                f"schedule",
            )
        )
    return out


@check("void_nets_to_zero")
def check_void_nets_to_zero(ctx: Context) -> list[Finding]:
    """Every void nets its check's amount to exactly zero.

    A withdrawal that does not reverse the full amount leaves a residue: the check
    is off the outstanding set because the void removed it, and the unreversed
    balance is carried by nothing. Compared with exact ``==`` -- a void short by a
    cent has not voided the check.
    """
    rule = "void_nets_to_zero"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_VOID_REGISTER)
    if register is None:
        return []
    checks = _check_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _voids(ctx):
        account_id, number = _key(row)
        source = checks.get((account_id, number))
        if source is None:
            continue  # void_disposition_valid owns this
        with amount_guard(rule, out):
            issued = require_cents(
                f"check[{account_id}/{number}].check_amount_cents",
                source.get("check_amount_cents"),
            )
            reversal = require_cents(
                f"void[{account_id}/{number}].void_amount_cents",
                row.get("void_amount_cents"),
            )
            checked += 1
            if issued + reversal != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"entries/{account_id}/{number}/void_amount_cents"),
                        f"check {account_id}/{number} was issued for {fmt(issued)} and the "
                        f"{_text(row, 'disposition')} reverses {fmt(reversal)}, netting to "
                        f"{fmt(issued + reversal)} rather than zero",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} voids net their check to zero"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# age_ -- the outstanding set and its aging
# --------------------------------------------------------------------------- #
@check("age_outstanding_set_recomputes")
def check_age_outstanding_set_recomputes(ctx: Context) -> list[Finding]:
    """The outstanding schedule is exactly the set the register re-derives.

    This is the control the engine exists for. The schedule is a *filtered view* of
    the register -- nothing cleared, no cleared date, not withdrawn -- and the
    moment it is maintained beside the register rather than derived from it, it
    drifts. The engine rebuilds the set from the register through the shared kernel
    and compares it, key and amount. Rows the void register withdrew are left to
    ``void_not_outstanding``.
    """
    rule = "age_outstanding_set_recomputes"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_OUTSTANDING_SCHEDULE)
    as_of = _parse_date(ctx.as_of)
    if schedule is None or as_of is None:
        return []
    voided = _void_keys(ctx)
    want = sorted(_outstanding_identity(e) for e in recompute_outstanding(ctx, as_of))
    have = sorted(
        _outstanding_identity(r)
        for r in _outstanding_rows(ctx)
        if _key(r) not in voided
    )
    out: list[Finding] = []
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"items/{entry[0]}/{entry[1]}"),
                        f"the schedule carries check {entry[0]}/{entry[1]} at "
                        f"{fmt(entry[2]) if isinstance(entry[2], int) else entry[2]}, which "
                        f"the register does not re-derive as outstanding at "
                        f"{as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"items/{entry[0]}/{entry[1]}"),
                        f"check {entry[0]}/{entry[1]} at {fmt(int(entry[2]))} has not "
                        f"cleared and is not withdrawn, but is absent from the outstanding "
                        f"schedule",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the outstanding schedule re-derives exactly, {len(want)} item(s)",
            )
        )
    return out


@check("age_bucket_recomputes")
def check_age_bucket_recomputes(ctx: Context) -> list[Finding]:
    """Each outstanding item's age and aging band re-derive from its check date.

    The age is the as-of date less the check date, and the band is a lookup on that
    age. Both are stated on the schedule for the reviewer, and a stated age that
    was typed rather than derived is how an item slides one band younger and out of
    the follow-up population.
    """
    rule = "age_bucket_recomputes"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_OUTSTANDING_SCHEDULE)
    as_of = _parse_date(ctx.as_of)
    if schedule is None or as_of is None:
        return []
    checks = _check_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _outstanding_rows(ctx):
        account_id, number = _key(row)
        source = checks.get((account_id, number))
        if source is None:
            continue  # age_outstanding_set_recomputes owns this
        check_date = _parse_date(source.get("check_date"))
        if check_date is None:
            continue  # chk_required_fields owns this
        checked += 1
        age = age_days(check_date, as_of)
        bucket = bucket_for(age)
        if row.get("age_days") != age:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"items/{account_id}/{number}/age_days"),
                    f"check {account_id}/{number} is aged {row.get('age_days')!r} day(s) on "
                    f"the schedule; {check_date.isoformat()} to {as_of.isoformat()} is "
                    f"{age} day(s)",
                )
            )
        elif row.get("aging_bucket") != bucket:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"items/{account_id}/{number}/aging_bucket"),
                    f"check {account_id}/{number} is bucketed "
                    f"{row.get('aging_bucket')!r} on the schedule; {age} day(s) falls in "
                    f"the {bucket} band",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} outstanding items re-derive their age and aging band",
            )
        )
    return out


@check("age_stale_dated_flagged")
def check_age_stale_dated_flagged(ctx: Context) -> list[Finding]:
    """Every stale-dated item is marked for follow-up, and nothing else is.

    Deliberately a FLAG rather than a failure: the item is still a real obligation,
    but past the stale-dating threshold the bank may refuse it and somebody has to
    act -- chase the payee, re-issue, or re-void. A marker that does not agree with
    the age sends that work to the wrong items, and an unmarked stale item simply
    keeps aging until it escheats.
    """
    rule = "age_stale_dated_flagged"
    _sev(rule, Status.FLAG)
    schedule = ctx.one(DOC_OUTSTANDING_SCHEDULE)
    as_of = _parse_date(ctx.as_of)
    if schedule is None or as_of is None:
        return []
    checks = _check_map(ctx)
    threshold = ctx.stale_dated_days
    out: list[Finding] = []
    checked = 0
    for row in _outstanding_rows(ctx):
        account_id, number = _key(row)
        source = checks.get((account_id, number))
        if source is None:
            continue  # age_outstanding_set_recomputes owns this
        check_date = _parse_date(source.get("check_date"))
        if check_date is None:
            continue  # chk_required_fields owns this
        checked += 1
        age = age_days(check_date, as_of)
        stale = is_stale_dated(age, threshold)
        if bool(row.get("follow_up_required")) != stale:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(schedule, f"items/{account_id}/{number}/follow_up_required"),
                    f"check {account_id}/{number} is {age} day(s) old against a "
                    f"{threshold}-day stale-dating threshold, so follow_up_required "
                    f"re-derives as {stale}; the schedule states "
                    f"{bool(row.get('follow_up_required'))}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} follow-up markers agree with the {threshold}-day "
                f"stale-dating threshold",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# esc_ -- escheatment
# --------------------------------------------------------------------------- #
@check("esc_set_recomputes")
def check_esc_set_recomputes(ctx: Context) -> list[Finding]:
    """The escheatment schedule is exactly the outstanding items past dormancy.

    Once an outstanding check has run the full dormancy period it stops being the
    entity's money. An item missing from the schedule is unclaimed property still
    sitting on the books; an item on it that has not run the period is money about
    to be handed to a state early. Both are re-derived from the outstanding set and
    compared on key, amount and age.
    """
    rule = "esc_set_recomputes"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ESCHEATMENT_SCHEDULE)
    as_of = _parse_date(ctx.as_of)
    if schedule is None or as_of is None:
        return []
    dormancy = ctx.dormancy_days
    want = sorted(
        _escheat_identity(e) for e in recompute_escheatment(ctx, as_of, dormancy)
    )
    have = sorted(_escheat_identity(r) for r in _escheat_rows(ctx))
    out: list[Finding] = []
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"items/{entry[0]}/{entry[1]}"),
                        f"the escheatment schedule carries check {entry[0]}/{entry[1]}, "
                        f"which the outstanding set does not re-derive as {dormancy}+ "
                        f"day(s) dormant at {as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"items/{entry[0]}/{entry[1]}"),
                        f"check {entry[0]}/{entry[1]} at {fmt(int(entry[2]))} is "
                        f"{entry[3]} day(s) old, past the {dormancy}-day dormancy period, "
                        f"but is absent from the escheatment schedule",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the escheatment schedule re-derives exactly, {len(want)} item(s) past "
                f"the {dormancy}-day dormancy period",
            )
        )
    return out


@check("esc_jurisdiction_assigned")
def check_esc_jurisdiction_assigned(ctx: Context) -> list[Finding]:
    """Every escheatment item reports to the jurisdiction its account declares.

    Unclaimed property is reported per account, and the account carries the
    jurisdiction. An item filed to the wrong one is simultaneously an
    over-remittance to a jurisdiction owed nothing and an unfiled liability to the
    one that is. Accounts with no declared jurisdiction are left to
    ``acct_jurisdiction_declared``.
    """
    rule = "esc_jurisdiction_assigned"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ESCHEATMENT_SCHEDULE)
    if schedule is None:
        return []
    accounts = _account_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _escheat_rows(ctx):
        account_id, number = _key(row)
        account = accounts.get(account_id)
        declared = _text(account, "escheat_jurisdiction") if account else None
        if declared is None:
            continue  # acct_jurisdiction_declared owns this
        checked += 1
        stated = _text(row, "escheat_jurisdiction")
        if stated != declared:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"items/{account_id}/{number}/escheat_jurisdiction"),
                    f"check {account_id}/{number} is scheduled to escheat to {stated!r}; "
                    f"bank account {account_id} reports unclaimed property to {declared!r}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} escheatment items name their account's declared "
                f"jurisdiction",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the bank reconciliation ties the evidence
# --------------------------------------------------------------------------- #
@check("rpt_outstanding_total_ties")
def check_rpt_outstanding_total_ties(ctx: Context) -> list[Finding]:
    """The bank reconciliation's outstanding-checks line ties the re-derived set.

    The outstanding-checks line is the single figure that reconciles the bank
    balance to the book balance, and it is the number that leaves the department.
    Tying it to the *schedule* proves only that two documents agree; it is tied
    here to the set re-derived from the register, so a schedule and a reconciliation
    that drifted together still break.
    """
    rule = "rpt_outstanding_total_ties"
    _sev(rule, Status.FAIL)
    reconciliation = ctx.one(DOC_BANK_RECONCILIATION)
    as_of = _parse_date(ctx.as_of)
    if reconciliation is None or as_of is None:
        return []
    recomputed = recompute_outstanding(ctx, as_of)
    total = sum(int(item["amount_cents"]) for item in recomputed)
    count = len(recomputed)
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_total = require_cents(
            "bank_reconciliation.outstanding_checks_cents",
            reconciliation.get("outstanding_checks_cents"),
        )
        stated_count = require_cents(
            "bank_reconciliation.outstanding_count",
            reconciliation.get("outstanding_count"),
            unit="a whole count",
        )
        if stated_total != total or stated_count != count:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(reconciliation, "outstanding_checks_cents"),
                    f"the reconciliation states {fmt(stated_total)} across {stated_count} "
                    f"outstanding check(s); the register re-derives {fmt(total)} across "
                    f"{count} (difference {fmt(stated_total - total)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the outstanding-checks line of {fmt(total)} across {count} item(s) "
                    f"ties the register",
                )
            )
    return out


@check("rpt_bucket_totals_tie")
def check_rpt_bucket_totals_tie(ctx: Context) -> list[Finding]:
    """The reconciliation's aging subtotals tie the re-derived bands.

    A FLAG rather than a failure: the aging profile is how the outstanding
    population is triaged, not how the bank balance is proved. A band that
    overstates sends follow-up effort at items that are not there, and one that
    understates hides the population that is about to go dormant.
    """
    rule = "rpt_bucket_totals_tie"
    _sev(rule, Status.FLAG)
    reconciliation = ctx.one(DOC_BANK_RECONCILIATION)
    as_of = _parse_date(ctx.as_of)
    if reconciliation is None or as_of is None:
        return []
    recomputed = {row["bucket"]: row for row in recompute_bucket_totals(ctx, as_of)}
    stated = {
        _text(row, "bucket") or "?": row
        for row in _rows(reconciliation, "bucket_totals")
    }
    out: list[Finding] = []
    for label, _upper in AGING_BUCKETS:
        want = recomputed[label]
        have = stated.get(label)
        if have is None:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(reconciliation, f"bucket_totals/{label}"),
                    f"the reconciliation carries no {label} aging band; the register "
                    f"re-derives {want['count']} item(s) at {fmt(int(want['amount_cents']))} "
                    f"in it",
                )
            )
            continue
        with amount_guard(rule, out):
            stated_amount = require_cents(
                f"bucket_totals[{label}].amount_cents", have.get("amount_cents")
            )
            stated_count = require_cents(
                f"bucket_totals[{label}].count", have.get("count"), unit="a whole count"
            )
            if stated_amount != want["amount_cents"] or stated_count != want["count"]:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(reconciliation, f"bucket_totals/{label}/amount_cents"),
                        f"the {label} band states {fmt(stated_amount)} across "
                        f"{stated_count} item(s); the register re-derives "
                        f"{fmt(int(want['amount_cents']))} across {want['count']}",
                    )
                )
    for label in sorted(stated):
        if label not in recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(reconciliation, f"bucket_totals/{label}"),
                    f"the reconciliation carries an aging band {label!r}, which is not one "
                    f"of the {len(AGING_BUCKETS)} bands the schedule is aged into",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(AGING_BUCKETS)} aging bands tie the re-derived outstanding set",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one aging file."""
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
    """Analyze every ``.json`` aging file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of aging-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
