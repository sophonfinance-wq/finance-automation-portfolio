"""
Wire & transfer release-control engine (READ-ONLY).
===================================================

Loads each release-control file (a ``.json`` file produced by
:mod:`wire_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether a payment is safe to release**, not where the
transfer lands in the ledger. Booking the cash entry is a separate engine's job,
and that engine assumes the money was allowed to leave. This engine is that gate.

The shape of the problem
------------------------
Every outbound wire, ACH or book transfer has to clear a set of preventive
controls before the wire room releases it: two different people signed it, the
second signature and its date are complete, the beneficiary matches an approved
template (and a new or changed detail was called back), the routing number is
valid and names the right bank, the funding account can cover it, it is not a
second copy of a payment already sent, and it moved through the three workflow
stages in order.

Three failures hide inside that, and none of them look wrong in a folder of
one-page wire forms: the packet one person both initiated and authorized, or
released before the second signature was complete; the payment sent to a
beneficiary off the approved template, or to a changed bank detail that was never
called back, or on a routing number that fails its own checksum; and the daily
released-wire log that calls a packet releasable on a determination nobody
recomputed from the signatures and templates underneath it.

The registry is organised around that:

1. ``set_``  -- is the release-control file complete?
2. ``sod_``  -- were two distinct signers present and the authorization complete?
3. ``sig_``  -- is each signer authorized on the account and within their limit?
4. ``ben_``  -- does the beneficiary match an approved template (or clear callback)?
5. ``aba_``  -- is the routing number well-formed and resolved to the named bank?
6. ``fund_`` -- does the funding account exist and cover the amount?
7. ``dup_``  -- are packet ids unique and free of an already-posted duplicate?
8. ``flow_`` -- did the packet traverse the workflow stages in order?
9. ``rpt_``  -- does the release rollup recompute from the evidence it summarises?

Design notes
------------
- **Strictly read-only.** Release-control files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every amount and limit is compared with exact
  ``>`` / ``==``.
- **One release predicate.** Controls and the generator share the kernel in
  :mod:`wire_engine.release`, so a determination cannot disagree with the data
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

from .money import AmountInvalidError, fmt, require_cents
from .model import (
    DOC_ACCOUNT_REGISTER,
    DOC_BANK_DIRECTORY,
    DOC_BENEFICIARY_REGISTER,
    DOC_POSTED_LOG,
    DOC_RELEASE_REPORT,
    DOC_RELEASE_SUMMARY,
    DOC_SIGNER_REGISTER,
    DOC_TYPES,
    DOC_WIRE_REGISTER,
    REQUEST_BOOK_TRANSFER,
    REQUEST_TYPES,
    REQUEST_WIRE,
    STAGE_POSTED,
    STAGE_SCHEDULED,
    STAGES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .release import (
    ReleaseFacts,
    aba_check_digit_valid,
    release_ok,
    within_duplicate_window,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~wire_engine.money.AmountInvalidError` as a finding."""
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
# Release-file accessors
# --------------------------------------------------------------------------- #
def _wires(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_WIRE_REGISTER), "wires")


def _wire_id(row: dict[str, Any]) -> str:
    value = row.get("wire_id")
    return value if isinstance(value, str) and value else "?"


def _accounts(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ACCOUNT_REGISTER), "accounts")


def _account(ctx: Context, account_id: str | None) -> dict[str, Any] | None:
    if not account_id:
        return None
    for row in _accounts(ctx):
        if _text(row, "account_id") == account_id:
            return row
    return None


def _signers(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SIGNER_REGISTER), "signers")


def _account_signers(ctx: Context, account_id: str | None) -> list[dict[str, Any]]:
    if not account_id:
        return []
    return [s for s in _signers(ctx) if _text(s, "account_id") == account_id]


def _is_authorized(ctx: Context, account_id: str | None, signer_id: str | None) -> bool:
    if not account_id or not signer_id:
        return False
    return any(
        _text(s, "signer_id") == signer_id for s in _account_signers(ctx, account_id)
    )


def _authority_limit(
    ctx: Context, account_id: str | None, signer_id: str | None
) -> int | None:
    """The authorizing signer's dollar limit on the account, or ``None``.

    Reads the limit through :func:`require_cents`, so a malformed limit raises
    :class:`AmountInvalidError` up to the calling control's guard rather than
    silently reading as zero.
    """
    if not account_id or not signer_id:
        return None
    for s in _account_signers(ctx, account_id):
        if _text(s, "signer_id") == signer_id:
            return require_cents(
                f"signer[{signer_id}@{account_id}].authority_limit_cents",
                s.get("authority_limit_cents"),
            )
    return None


def _templates(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_BENEFICIARY_REGISTER), "templates")


def _template(ctx: Context, template_id: str | None) -> dict[str, Any] | None:
    if not template_id:
        return None
    for row in _templates(ctx):
        if _text(row, "template_id") == template_id:
            return row
    return None


def _directory(ctx: Context) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _rows(ctx.one(DOC_BANK_DIRECTORY), "banks"):
        aba = _text(row, "receiving_aba")
        name = _text(row, "bank_name")
        if aba and name and aba not in out:
            out[aba] = name
    return out


def _postings(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_POSTED_LOG), "postings")


def _is_external(row: dict[str, Any]) -> bool:
    return _text(row, "request_type") == REQUEST_WIRE


def _triplet(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        _text(row, "receiving_aba"),
        _text(row, "beneficiary_account"),
        _text(row, "beneficiary_name"),
    )


# --------------------------------------------------------------------------- #
# Derived-determination helpers (shared by the controls and the recompute)
# --------------------------------------------------------------------------- #
def _beneficiary_ok(ctx: Context, wire: dict[str, Any]) -> bool:
    """Whether a packet's beneficiary clears the whitelist / callback gate.

    Internal book transfers carry no external beneficiary, so the gate does not
    apply. An external wire on template must match its stored triplet; one off
    template must carry a completed callback.
    """
    if not _is_external(wire):
        return True
    if bool(wire.get("on_template")):
        tmpl = _template(ctx, _text(wire, "template_id"))
        if tmpl is None:
            return False
        return _triplet(wire) == _triplet(tmpl)
    return bool(wire.get("callback_completed"))


def _routing_ok(ctx: Context, wire: dict[str, Any]) -> bool:
    """Whether a packet's routing detail is well-formed and resolved.

    A book transfer is internal and must carry no routing detail. An external
    wire must carry a nine-digit ABA that passes its checksum and resolves,
    through the bank directory, to the receiving-bank name printed on the form.
    """
    aba = _text(wire, "receiving_aba")
    bank = _text(wire, "receiving_bank_name")
    if not _is_external(wire):
        return aba is None and bank is None
    if aba is None or bank is None:
        return False
    if not aba_check_digit_valid(aba):
        return False
    return _directory(ctx).get(aba) == bank


def _duplicate_exists(ctx: Context, wire: dict[str, Any]) -> bool:
    """Whether a not-yet-posted packet duplicates an already-posted payment.

    A posted packet is excluded -- it *is* the posting, not a duplicate of it. For
    every other packet, a posted payment sharing its beneficiary account and
    amount within the duplicate window is a suspected double payment.
    """
    if _text(wire, "stage") == STAGE_POSTED:
        return False
    beneficiary = _text(wire, "beneficiary_account")
    value_date = _parse_date(wire.get("value_date"))
    if beneficiary is None or value_date is None:
        return False
    try:
        amount = require_cents(f"wire[{_wire_id(wire)}].amount_cents", wire.get("amount_cents"))
    except AmountInvalidError:
        return False
    window = ctx.duplicate_window_days
    for posted in _postings(ctx):
        if _text(posted, "beneficiary_account") != beneficiary:
            continue
        posted_date = _parse_date(posted.get("posted_date"))
        if posted_date is None:
            continue
        try:
            posted_amount = require_cents(
                f"posting[{_text(posted, 'posted_id')}].amount_cents",
                posted.get("amount_cents"),
            )
        except AmountInvalidError:
            continue
        if posted_amount == amount and within_duplicate_window(value_date, posted_date, window):
            return True
    return False


def recompute_wire_releasable(ctx: Context, wire: dict[str, Any]) -> bool:
    """Recompute a packet's releasable determination from the base facts.

    Rebuilds the release primitives -- signers, limit, beneficiary, routing,
    funding and duplicate status -- and runs them through the shared
    :func:`wire_engine.release.release_ok` kernel the generator produced the data
    with, so the determination the engine recomputes is the one that produced it.

    Raises :class:`AmountInvalidError` if an amount or limit it must read is not
    integer cents; the calling control contains that to the packet being read.
    """
    account_id = _text(wire, "from_account")
    initiated_by = _text(wire, "initiated_by") or ""
    authorized_by = _text(wire, "authorized_by") or ""
    account = _account(ctx, account_id)
    amount = require_cents(f"wire[{_wire_id(wire)}].amount_cents", wire.get("amount_cents"))
    limit = _authority_limit(ctx, account_id, authorized_by)
    available: int | None = None
    if account is not None:
        available = require_cents(
            f"account[{account_id}].available_cents", account.get("available_cents")
        )
    facts = ReleaseFacts(
        initiated_by=initiated_by,
        authorized_by=authorized_by,
        initiated_date=_parse_date(wire.get("initiated_date")),
        authorized_date=_parse_date(wire.get("authorized_date")),
        account_exists=account is not None,
        initiator_authorized=_is_authorized(ctx, account_id, initiated_by),
        authorizer_authorized=_is_authorized(ctx, account_id, authorized_by),
        amount_cents=amount,
        authority_limit_cents=limit,
        beneficiary_ok=_beneficiary_ok(ctx, wire),
        routing_ok=_routing_ok(ctx, wire),
        available_cents=available,
        duplicate=_duplicate_exists(ctx, wire),
    )
    return release_ok(facts)


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the release-control file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the release-control file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} release-control artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; the daily release log is "
                f"measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# sod_ -- segregation of duties and dual authorization
# --------------------------------------------------------------------------- #
@check("sod_two_distinct_signers")
def check_sod_two_distinct_signers(ctx: Context) -> list[Finding]:
    """Every packet names two different people to initiate and to authorize.

    One person on both roles is the whole failure the wire room's segregation of
    duties exists to prevent: nobody independent ever looked at the payment.
    """
    rule = "sod_two_distinct_signers"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        initiated = _text(wire, "initiated_by")
        authorized = _text(wire, "authorized_by")
        if initiated is None or authorized is None:
            continue  # completeness is sod_dual_auth_complete / flow's job
        checked += 1
        if initiated == authorized:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/authorized_by"),
                    f"packet {_wire_id(wire)} was initiated and authorized by the same "
                    f"signer {initiated!r}; segregation of duties requires two distinct "
                    f"signers",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} packets carry two distinct signers")
        )
    return out


@check("sod_dual_auth_complete")
def check_sod_dual_auth_complete(ctx: Context) -> list[Finding]:
    """A scheduled packet carries both signers and both dates.

    The dual-authorization gate: both signer fields and both date fields must be
    populated before a packet may leave the pending tray and enter 'Approved &
    Scheduled'. A scheduled packet missing any of the four never actually cleared
    that gate.
    """
    rule = "sod_dual_auth_complete"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    fields = ("initiated_by", "authorized_by", "initiated_date", "authorized_date")
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if _text(wire, "stage") != STAGE_SCHEDULED:
            continue
        checked += 1
        missing = [f for f in fields if not _text(wire, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}"),
                    f"packet {_wire_id(wire)} is Approved & Scheduled but is missing "
                    f"{', '.join(missing)}; it cannot have cleared the dual-authorization "
                    f"gate",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} scheduled packets are fully authorized"
            )
        )
    return out


@check("sod_auth_not_before_init")
def check_sod_auth_not_before_init(ctx: Context) -> list[Finding]:
    """A packet's authorization is not dated before its initiation.

    Authorizing a packet before it was initiated is not an ordering quirk; it
    means the two dates were not recorded from the workflow, so the audit trail
    the dual signature exists to leave cannot be trusted.
    """
    rule = "sod_auth_not_before_init"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        initiated = _parse_date(wire.get("initiated_date"))
        authorized = _parse_date(wire.get("authorized_date"))
        if initiated is None or authorized is None:
            continue
        checked += 1
        if authorized < initiated:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/authorized_date"),
                    f"packet {_wire_id(wire)} is authorized {authorized.isoformat()}, before "
                    f"it was initiated {initiated.isoformat()}; the authorization cannot "
                    f"precede the request",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} packets are authorized on or after initiation")
        )
    return out


# --------------------------------------------------------------------------- #
# sig_ -- authorized-signer register and dollar-limit membership
# --------------------------------------------------------------------------- #
@check("sig_initiator_authorized")
def check_sig_initiator_authorized(ctx: Context) -> list[Finding]:
    """The initiator of each packet is on the funding account's signer register."""
    rule = "sig_initiator_authorized"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        account_id = _text(wire, "from_account")
        initiated = _text(wire, "initiated_by")
        if initiated is None or _account(ctx, account_id) is None:
            continue  # fund_account_exists owns a missing account
        checked += 1
        if not _is_authorized(ctx, account_id, initiated):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/initiated_by"),
                    f"packet {_wire_id(wire)} was initiated by {initiated!r}, who is not on "
                    f"the authorized-signer register for account {account_id}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} initiators are authorized on their account")
        )
    return out


@check("sig_authorizer_authorized")
def check_sig_authorizer_authorized(ctx: Context) -> list[Finding]:
    """The authorizer of each packet is on the funding account's signer register."""
    rule = "sig_authorizer_authorized"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        account_id = _text(wire, "from_account")
        authorized = _text(wire, "authorized_by")
        if authorized is None or _account(ctx, account_id) is None:
            continue
        checked += 1
        if not _is_authorized(ctx, account_id, authorized):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/authorized_by"),
                    f"packet {_wire_id(wire)} was authorized by {authorized!r}, who is not "
                    f"on the authorized-signer register for account {account_id}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} authorizers are authorized on their account")
        )
    return out


@check("sig_within_authority_limit")
def check_sig_within_authority_limit(ctx: Context) -> list[Finding]:
    """The amount is within the authorizing signer's dollar limit.

    Compared with exact ``>``: an amount a cent over the signer's authority is an
    amount over the signer's authority.
    """
    rule = "sig_within_authority_limit"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        account_id = _text(wire, "from_account")
        authorized = _text(wire, "authorized_by")
        if authorized is None or _account(ctx, account_id) is None:
            continue
        with amount_guard(rule, out):
            limit = _authority_limit(ctx, account_id, authorized)
            if limit is None:
                continue  # sig_authorizer_authorized owns a non-signer authorizer
            amount = require_cents(
                f"wire[{_wire_id(wire)}].amount_cents", wire.get("amount_cents")
            )
            checked += 1
            if amount > limit:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"wires/{_wire_id(wire)}/amount_cents"),
                        f"packet {_wire_id(wire)} is {fmt(amount)}; authorizer {authorized} "
                        f"carries a {fmt(limit)} authority limit on account {account_id} "
                        f"(over by {fmt(amount - limit)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} amounts are within the authorizer's limit")
        )
    return out


# --------------------------------------------------------------------------- #
# ben_ -- beneficiary-master integrity and new-account callback
# --------------------------------------------------------------------------- #
@check("ben_template_exists")
def check_ben_template_exists(ctx: Context) -> list[Finding]:
    """An on-template external wire names a beneficiary template that exists."""
    rule = "ben_template_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if not _is_external(wire) or not bool(wire.get("on_template")):
            continue
        checked += 1
        template_id = _text(wire, "template_id")
        if _template(ctx, template_id) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/template_id"),
                    f"packet {_wire_id(wire)} claims template {template_id!r}, which is not "
                    f"in the approved-beneficiary register",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} on-template wires name an existing template")
        )
    return out


@check("ben_triplet_matches_template")
def check_ben_triplet_matches_template(ctx: Context) -> list[Finding]:
    """The (ABA, beneficiary account, beneficiary name) triplet matches the template.

    The whitelist is keyed on the whole triplet: a wire whose routing number,
    account or name differs from the stored template is being sent somewhere the
    entity never approved, even if the template id it cites is real.
    """
    rule = "ben_triplet_matches_template"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if not _is_external(wire) or not bool(wire.get("on_template")):
            continue
        tmpl = _template(ctx, _text(wire, "template_id"))
        if tmpl is None:
            continue  # ben_template_exists owns a missing template
        checked += 1
        if _triplet(wire) != _triplet(tmpl):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/beneficiary_account"),
                    f"packet {_wire_id(wire)} beneficiary {_triplet(wire)} does not match "
                    f"the stored template {_triplet(tmpl)}; the payment is bound for an "
                    f"unapproved destination",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} on-template triplets match their template")
        )
    return out


@check("ben_new_account_callback")
def check_ben_new_account_callback(ctx: Context) -> list[Finding]:
    """An off-template (new or changed) beneficiary carries a completed callback.

    A first-time or changed bank detail is the single highest-value fraud vector
    in a wire room; releasing it without a callback to verify it is the control
    that stops a redirected payment.
    """
    rule = "ben_new_account_callback"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if not _is_external(wire) or bool(wire.get("on_template")):
            continue
        checked += 1
        if not bool(wire.get("callback_completed")):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/callback_completed"),
                    f"packet {_wire_id(wire)} pays an off-template beneficiary with no "
                    f"completed callback; a new or changed bank detail must be verified "
                    f"before release",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} off-template wires cleared a callback")
        )
    return out


@check("ben_off_template_review")
def check_ben_off_template_review(ctx: Context) -> list[Finding]:
    """An off-template beneficiary is flagged for a second look before release.

    Deliberately a FLAG, not a failure: the callback may be complete and the
    payment releasable, but a beneficiary that is not on the whitelist is exactly
    the packet a reviewer should eyeball before the money leaves.
    """
    rule = "ben_off_template_review"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if not _is_external(wire):
            continue
        checked += 1
        if not bool(wire.get("on_template")):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/on_template"),
                    f"packet {_wire_id(wire)} pays an off-template beneficiary; even with a "
                    f"callback on file it should be reviewed before the wire is released",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} external wires pay a whitelisted beneficiary")
        )
    return out


# --------------------------------------------------------------------------- #
# aba_ -- routing checksum and receiving-bank-name re-derivation
# --------------------------------------------------------------------------- #
@check("aba_classification_fields")
def check_aba_classification_fields(ctx: Context) -> list[Finding]:
    """Each packet carries the routing detail its request type requires.

    An external wire must carry a receiving ABA and bank name; an internal book
    transfer must carry neither. The classification drives which routing controls
    apply, so a packet that carries the wrong shape is mis-typed at the root.
    """
    rule = "aba_classification_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        request_type = _text(wire, "request_type")
        if request_type not in REQUEST_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/request_type"),
                    f"packet {_wire_id(wire)} is typed {request_type!r}, which is not one of "
                    f"{REQUEST_TYPES}; the routing controls cannot be selected",
                )
            )
            continue
        checked += 1
        aba = _text(wire, "receiving_aba")
        bank = _text(wire, "receiving_bank_name")
        if request_type == REQUEST_WIRE and (aba is None or bank is None):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/receiving_aba"),
                    f"external wire {_wire_id(wire)} is missing a receiving ABA or bank name; "
                    f"an outbound wire cannot be routed without both",
                )
            )
        elif request_type == REQUEST_BOOK_TRANSFER and (aba is not None or bank is not None):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/receiving_aba"),
                    f"book transfer {_wire_id(wire)} carries a receiving ABA/bank name; an "
                    f"internal transfer stays within the bank and names no routing detail",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} packets carry the routing shape their type requires")
        )
    return out


@check("aba_check_digit_valid")
def check_aba_check_digit_valid(ctx: Context) -> list[Finding]:
    """An external wire's routing number passes the ABA check-digit test."""
    rule = "aba_check_digit_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if not _is_external(wire):
            continue
        aba = _text(wire, "receiving_aba")
        if aba is None:
            continue  # aba_classification_fields owns a missing ABA
        checked += 1
        if not aba_check_digit_valid(aba):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/receiving_aba"),
                    f"packet {_wire_id(wire)} routing number {aba!r} fails the ABA "
                    f"check-digit (mod-10, weights 3-7-1); it cannot be a valid routing "
                    f"number",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} external routing numbers pass the checksum")
        )
    return out


@check("aba_resolves_to_bank_name")
def check_aba_resolves_to_bank_name(ctx: Context) -> list[Finding]:
    """An external wire's routing number resolves to the named receiving bank.

    The routing number and the bank name are two independent facts on the form; a
    valid number that resolves to a different bank than the one printed is a
    transposed or copied field, and a check-digit-valid number is not enough.
    """
    rule = "aba_resolves_to_bank_name"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    directory = _directory(ctx)
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if not _is_external(wire):
            continue
        aba = _text(wire, "receiving_aba")
        bank = _text(wire, "receiving_bank_name")
        if aba is None or bank is None:
            continue  # aba_classification_fields owns missing fields
        checked += 1
        resolved = directory.get(aba)
        if resolved != bank:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/receiving_bank_name"),
                    f"packet {_wire_id(wire)} routing number {aba} resolves to "
                    f"{resolved!r} in the bank directory, but the form names {bank!r}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} routing numbers resolve to their named bank")
        )
    return out


# --------------------------------------------------------------------------- #
# fund_ -- funding account existence and sufficiency
# --------------------------------------------------------------------------- #
@check("fund_account_exists")
def check_fund_account_exists(ctx: Context) -> list[Finding]:
    """Every packet draws on a funding account in the account register."""
    rule = "fund_account_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for wire in _wires(ctx):
        account_id = _text(wire, "from_account")
        if account_id is None or _account(ctx, account_id) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/from_account"),
                    f"packet {_wire_id(wire)} draws on account {account_id!r}, which is not "
                    f"in the funding-account register; its balance cannot be checked",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_wires(ctx))} packets draw on a known funding account")
        )
    return out


@check("fund_sufficient_balance")
def check_fund_sufficient_balance(ctx: Context) -> list[Finding]:
    """The amount is within the funding account's available balance.

    Compared with exact ``>``: an amount a cent over the available balance is an
    overdraft the moment it releases.
    """
    rule = "fund_sufficient_balance"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        account_id = _text(wire, "from_account")
        account = _account(ctx, account_id)
        if account is None:
            continue  # fund_account_exists owns a missing account
        with amount_guard(rule, out):
            available = require_cents(
                f"account[{account_id}].available_cents", account.get("available_cents")
            )
            amount = require_cents(
                f"wire[{_wire_id(wire)}].amount_cents", wire.get("amount_cents")
            )
            checked += 1
            if amount > available:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"wires/{_wire_id(wire)}/amount_cents"),
                        f"packet {_wire_id(wire)} is {fmt(amount)}; account {account_id} has "
                        f"{fmt(available)} available (short {fmt(amount - available)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} amounts are within the funding balance")
        )
    return out


# --------------------------------------------------------------------------- #
# dup_ -- duplicate-payment detection
# --------------------------------------------------------------------------- #
@check("dup_wire_ids_unique")
def check_dup_wire_ids_unique(ctx: Context) -> list[Finding]:
    """No packet id appears twice in the wire register.

    The packet id joins the register to the release summary and the posted log. A
    duplicate makes a posting ambiguous about which request it settled.
    """
    rule = "dup_wire_ids_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for wire in _wires(ctx):
        seen[_wire_id(wire)] = seen.get(_wire_id(wire), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"wires/{wid}"),
            f"packet id {wid} appears {count} times; a posting that settles it cannot be "
            f"attributed to one request",
        )
        for wid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} packet ids are unique")
        )
    return out


@check("dup_not_already_posted")
def check_dup_not_already_posted(ctx: Context) -> list[Finding]:
    """A not-yet-posted packet does not duplicate an already-posted payment.

    The same beneficiary and amount within the duplicate window as a payment
    already in the posted log is a second copy about to be sent; the posted log is
    the record that stops it.
    """
    rule = "dup_not_already_posted"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    log = ctx.one(DOC_POSTED_LOG)
    if register is None or log is None:
        return []
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if _text(wire, "stage") == STAGE_POSTED:
            continue
        checked += 1
        if _duplicate_exists(ctx, wire):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/beneficiary_account"),
                    f"packet {_wire_id(wire)} matches an already-posted payment to the same "
                    f"beneficiary for the same amount inside the {ctx.duplicate_window_days}-"
                    f"day window; releasing it would pay twice",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} unposted packets are free of a posted duplicate")
        )
    return out


# --------------------------------------------------------------------------- #
# flow_ -- workflow-stage completeness
# --------------------------------------------------------------------------- #
@check("flow_stage_valid")
def check_flow_stage_valid(ctx: Context) -> list[Finding]:
    """Every packet sits in one of the three known workflow stages."""
    rule = "flow_stage_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"wires/{_wire_id(wire)}/stage"),
            f"packet {_wire_id(wire)} is in stage {_text(wire, 'stage')!r}, which is not one "
            f"of {STAGES}; its place in the release workflow is unknown",
        )
        for wire in _wires(ctx)
        if _text(wire, "stage") not in STAGES
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_wires(ctx))} packets sit in a known workflow stage")
        )
    return out


@check("flow_posted_has_approval")
def check_flow_posted_has_approval(ctx: Context) -> list[Finding]:
    """A posted packet carries its secondary-approval evidence.

    Lifecycle completeness: a packet that reached the posted log with no complete
    dual authorization skipped the secondary-approval stage, and a released wire
    with no evidence it was ever second-signed is the exception this control
    exists to surface.
    """
    rule = "flow_posted_has_approval"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    if register is None:
        return []
    fields = ("initiated_by", "authorized_by", "initiated_date", "authorized_date")
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if _text(wire, "stage") != STAGE_POSTED:
            continue
        checked += 1
        missing = [f for f in fields if not _text(wire, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}"),
                    f"posted packet {_wire_id(wire)} is missing {', '.join(missing)}; it was "
                    f"released with no evidence of a complete secondary approval",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} posted packets carry secondary-approval evidence")
        )
    return out


@check("flow_posted_ref_ties")
def check_flow_posted_ref_ties(ctx: Context) -> list[Finding]:
    """Posted packets and the posted log tie to each other, both ways.

    A packet marked posted must reference a posting that exists and matches its
    beneficiary and amount, and every posting must map back to a packet in the
    register. A posting with no request, or a request pointing at no posting,
    breaks the three-way reconciliation from Approved & Scheduled to the posted
    log to the register.
    """
    rule = "flow_posted_ref_ties"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WIRE_REGISTER)
    log = ctx.one(DOC_POSTED_LOG)
    if register is None or log is None:
        return []
    postings = {_text(p, "posted_id"): p for p in _postings(ctx) if _text(p, "posted_id")}
    wire_ids = {_wire_id(w) for w in _wires(ctx)}
    out: list[Finding] = []
    checked = 0
    for wire in _wires(ctx):
        if _text(wire, "stage") != STAGE_POSTED:
            continue
        checked += 1
        ref = _text(wire, "posted_ref")
        posting = postings.get(ref) if ref else None
        if posting is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"wires/{_wire_id(wire)}/posted_ref"),
                    f"posted packet {_wire_id(wire)} references posting {ref!r}, which is not "
                    f"in the posted log; the release cannot be tied to an execution",
                )
            )
            continue
        with amount_guard(rule, out):
            wire_amount = require_cents(
                f"wire[{_wire_id(wire)}].amount_cents", wire.get("amount_cents")
            )
            posted_amount = require_cents(
                f"posting[{ref}].amount_cents", posting.get("amount_cents")
            )
            if (
                _text(posting, "beneficiary_account") != _text(wire, "beneficiary_account")
                or posted_amount != wire_amount
            ):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"wires/{_wire_id(wire)}/posted_ref"),
                        f"posted packet {_wire_id(wire)} does not match posting {ref} on "
                        f"beneficiary or amount; the execution on file settles a different "
                        f"payment",
                    )
                )
    for posting in _postings(ctx):
        ref_wire = _text(posting, "wire_id")
        if ref_wire not in wire_ids:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"postings/{_text(posting, 'posted_id')}/wire_id"),
                    f"posting {_text(posting, 'posted_id')} settles packet {ref_wire!r}, "
                    f"which is not in the wire register; a payment left with no request on "
                    f"file",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} posted packets tie to the posted log both ways")
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence
# --------------------------------------------------------------------------- #
@check("rpt_release_flag_recomputes")
def check_rpt_release_flag_recomputes(ctx: Context) -> list[Finding]:
    """Each packet's stated releasable flag recomputes from its evidence.

    This is the control the engine exists for. The release summary is a
    determination, and a determination that is not recomputed from the evidence
    is an assertion. The engine rebuilds every flag from the signers, templates,
    routing directory and funding balances, and compares.
    """
    rule = "rpt_release_flag_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RELEASE_SUMMARY)
    if summary is None:
        return []
    wires = {_wire_id(w): w for w in _wires(ctx)}
    out: list[Finding] = []
    for row in _rows(summary, "wires"):
        wid = _text(row, "wire_id")
        wire = wires.get(wid or "")
        if wire is None:
            continue
        stated = row.get("releasable")
        with amount_guard(rule, out):
            recomputed = recompute_wire_releasable(ctx, wire)
            if recomputed != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"wires/{wid}/releasable"),
                        f"packet {wid} is summarised releasable={stated}; recomputing from "
                        f"the release evidence gives releasable={recomputed}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every packet releasable flag recomputes from its evidence")
        )
    return out


@check("rpt_report_count_ties")
def check_rpt_report_count_ties(ctx: Context) -> list[Finding]:
    """The release report's releasable / blocked counts tie the summary.

    The number that reaches the cash manager is a count, and a count maintained
    beside the summary rather than derived from it drifts the first time a flag
    moves and nobody re-adds the column.
    """
    rule = "rpt_report_count_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_RELEASE_REPORT)
    summary = ctx.one(DOC_RELEASE_SUMMARY)
    if report is None or summary is None:
        return []
    releasable = 0
    blocked = 0
    for row in _rows(summary, "wires"):
        value = row.get("releasable")
        if value is True:
            releasable += 1
        elif value is False:
            blocked += 1
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_releasable = require_cents(
            "release_report.releasable_count", report.get("releasable_count"), unit="a whole count"
        )
        stated_blocked = require_cents(
            "release_report.blocked_count", report.get("blocked_count"), unit="a whole count"
        )
        if stated_releasable != releasable or stated_blocked != blocked:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "releasable_count"),
                    f"the report states {stated_releasable} releasable / {stated_blocked} "
                    f"blocked; the release summary recomputes {releasable} / {blocked}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report counts of {releasable} / {blocked} tie the summary",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one release-control file."""
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
    """Analyze every ``.json`` release-control file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of release-control file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
