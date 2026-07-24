"""
Subcontract SOV & change-order control engine (READ-ONLY).
==========================================================

Loads each billing file (a ``.json`` file produced by
:mod:`sov_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether every figure on the commitment billing chain
re-derives from the figures beneath it**, not about which lender draw funds a
pay app (a separate engine's job) or whether a lien waiver's statutory form is
correct (another's). The cross-tie kept here is the arithmetic one: the
conditional release amount must equal the certified payment due including tax,
and each pay app must carry exactly one.

The shape of the problem
------------------------
A developer buys construction through subcontract commitments -- a contract
with a schedule of values breaking the price into lines, change orders amending
it, and a monthly pay application billing against it line by line. Every column
on that chain is derived from a column beneath it, and every one of them is
typed by hand somewhere: the SOV that no longer foots to the contract, the
revised commitment that counted a pending change order, the line billed past
its scheduled value, the "previously billed" that no longer equals last month's
"total billed", the retention and tax that stopped being the rate on the
request, the release signed for an amount nobody recomputed.

The registry is organised around that:

1.  ``set_``  -- is the billing file complete?
2.  ``cmt_``  -- is the commitment register sound, and does the committed-cost
    roster re-derive from it?
3.  ``co_``   -- do the change orders respect the authorization / naming gate?
4.  ``sov_``  -- is the schedule of values well-formed, and does it foot to the
    original contract?
5.  ``line_`` -- does every pay-app line and header re-derive arithmetically?
6.  ``cap_``  -- is every line billed within its scheduled value?
7.  ``ret_``  -- is retention the contract rate on the billing?
8.  ``tax_``  -- do the sales tax and the payment due re-derive?
9.  ``roll_`` -- does the pay-app sequence roll forward with no gap or break?
10. ``port_`` -- do the portfolio Total columns foot?
11. ``lien_`` -- does the conditional release tie the certified payment?

Design notes
------------
- **Strictly read-only.** Billing files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every equality is exact ``==`` and every cap
  is exact ``<=``.
- **One arithmetic kernel.** Controls and the generator share the formulas in
  :mod:`sov_engine.billing`, so a derived figure cannot disagree with the data
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

from .billing import (
    COMMITMENT_ID_RE,
    CO_STATUSES,
    balance_to_finish_cents,
    current_request_cents,
    make_commitment_id,
    net_approved_change_cents,
    payment_due_cents,
    percent_complete,
    retention_cents,
    revised_contract_cents,
    sales_tax_cents,
    total_completed_cents,
)
from .model import (
    COMMITMENT_ORIGINS,
    DOC_CHANGE_ORDER_LOG,
    DOC_COMMITMENT_REGISTER,
    DOC_COMMITMENT_ROLLUP,
    DOC_LIEN_RELEASE_REGISTER,
    DOC_PAY_APP_REGISTER,
    DOC_SOV_SCHEDULE,
    DOC_TYPES,
    RELEASE_CONDITIONAL,
    STANDARD_RETENTION_RATES_BPS,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~sov_engine.money.AmountInvalidError` as a finding."""
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
# Billing-file helpers
# --------------------------------------------------------------------------- #
def _commitments(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_COMMITMENT_REGISTER), "commitments")


def _commitment_id(row: dict[str, Any]) -> str:
    value = row.get("commitment_id")
    return value if isinstance(value, str) and value else "?"


def _commitment_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _commitments(ctx):
        cid = _commitment_id(row)
        if cid != "?" and cid not in out:
            out[cid] = row
    return out


def _change_orders(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CHANGE_ORDER_LOG), "change_orders")


def _co_id(row: dict[str, Any]) -> str:
    value = row.get("co_id")
    return value if isinstance(value, str) and value else "?"


def _sov_lines(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SOV_SCHEDULE), "lines")


def _sov_map(ctx: Context) -> dict[tuple[str, int], dict[str, Any]]:
    """First-wins map of ``(commitment_id, line_no)`` to its SOV line."""
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for row in _sov_lines(ctx):
        cid = _text(row, "commitment_id")
        line_no = _int(row, "line_no")
        if cid and line_no is not None and (cid, line_no) not in out:
            out[(cid, line_no)] = row
    return out


def _pay_apps(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PAY_APP_REGISTER), "pay_applications")


def _app_lines(app: dict[str, Any]) -> list[dict[str, Any]]:
    return _rows(app, "lines")


def _app_totals(app: dict[str, Any]) -> dict[str, Any]:
    totals = app.get("totals")
    return totals if isinstance(totals, dict) else {}


def _app_key(app: dict[str, Any]) -> str:
    return f"{_text(app, 'commitment_id') or '?'}/app-{app.get('app_no', '?')}"


def _apps_by_commitment(ctx: Context) -> dict[str, list[dict[str, Any]]]:
    """Pay apps grouped by commitment, ordered by integer ``app_no``.

    Apps whose ``app_no`` is not a readable integer are left out here -- the
    sequencing control owns them -- so the roll-forward control never orders a
    chain on an unreadable key.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        if cid and _int(app, "app_no") is not None:
            grouped.setdefault(cid, []).append(app)
    for apps in grouped.values():
        apps.sort(key=lambda a: (_int(a, "app_no") or 0))
    return grouped


def _rollup_doc(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_COMMITMENT_ROLLUP)


def _rollup_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(_rollup_doc(ctx), "rows")


def _rollup_totals(ctx: Context) -> dict[str, Any]:
    doc = _rollup_doc(ctx)
    if doc is None:
        return {}
    totals = doc.get("totals")
    return totals if isinstance(totals, dict) else {}


def _releases(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_LIEN_RELEASE_REGISTER), "releases")


def recompute_net_approved_changes(ctx: Context, commitment_id: str) -> int:
    """The net approved change-order movement on one commitment, re-derived.

    Only *approved* orders count -- the shared kernel states that once for both
    the generator and the engine. Raises :class:`AmountInvalidError` if an
    amount it must read is not integer cents; the calling control contains that
    to the row being read.
    """
    items: list[tuple[str, int]] = []
    for co in _change_orders(ctx):
        if _text(co, "commitment_id") != commitment_id:
            continue
        amount = require_cents(
            f"change_order[{_co_id(co)}].amount_cents", co.get("amount_cents")
        )
        items.append((_text(co, "status") or "", amount))
    return net_approved_change_cents(items)


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the billing file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the billing file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} billing artifacts are present",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cmt_ -- the commitment register and the committed-cost roster
# --------------------------------------------------------------------------- #
@check("cmt_ids_unique")
def check_cmt_ids_unique(ctx: Context) -> list[Finding]:
    """No commitment id appears twice.

    The commitment id joins the register to every change order, SOV line, pay
    app and release. A duplicate makes every one of those references ambiguous
    about which contract it bills.
    """
    rule = "cmt_ids_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COMMITMENT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _commitments(ctx):
        seen[_commitment_id(row)] = seen.get(_commitment_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"commitments/{cid}"),
            f"commitment id {cid} appears {count} times; a pay app that bills it "
            f"cannot be attributed to one contract",
        )
        for cid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} commitment ids are unique")
        )
    return out


@check("cmt_required_fields")
def check_cmt_required_fields(ctx: Context) -> list[Finding]:
    """Every commitment carries the fields the controls read.

    The descriptive fields join the register to the naming gate, and the three
    numeric terms -- original contract, retention rate, tax rate -- are the
    bases every re-derivation below starts from.
    """
    rule = "cmt_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COMMITMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _commitments(ctx):
        cid = _commitment_id(row)
        missing = [
            f
            for f in ("commitment_id", "vendor", "project_code", "vendor_code")
            if not _text(row, f)
        ]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"commitments/{cid}"),
                    f"commitment {cid} is missing {', '.join(missing)}",
                )
            )
        with amount_guard(rule, out):
            require_cents(
                f"commitment[{cid}].original_contract_cents",
                row.get("original_contract_cents"),
            )
            require_cents(
                f"commitment[{cid}].retention_rate_bps",
                row.get("retention_rate_bps"),
                unit="integer basis points",
            )
            require_cents(
                f"commitment[{cid}].tax_rate_bps",
                row.get("tax_rate_bps"),
                unit="integer basis points",
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_commitments(ctx))} commitments carry their required fields",
            )
        )
    return out


@check("cmt_rollup_ties_register")
def check_cmt_rollup_ties_register(ctx: Context) -> list[Finding]:
    """The committed-cost roster carries exactly the register, commitment for
    commitment, at the register's original amounts.

    A commitment missing from the roster is committed cost the Total columns
    never saw; a roster row for no commitment is cost with no contract behind
    it; an original that differs is two documents disagreeing about what was
    signed.
    """
    rule = "cmt_rollup_ties_register"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COMMITMENT_REGISTER)
    rollup = _rollup_doc(ctx)
    if register is None or rollup is None:
        return []
    commitments = _commitment_map(ctx)
    rows_by_cid: dict[str, list[dict[str, Any]]] = {}
    for row in _rollup_rows(ctx):
        cid = _text(row, "commitment_id")
        if cid:
            rows_by_cid.setdefault(cid, []).append(row)
    out: list[Finding] = []
    for cid, commitment in sorted(commitments.items()):
        rows = rows_by_cid.get(cid, [])
        if len(rows) != 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, f"rows/{cid}"),
                    f"commitment {cid} appears {len(rows)} time(s) on the "
                    f"committed-cost roster; each commitment carries exactly one row",
                )
            )
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"rollup[{cid}].original_contract_cents",
                rows[0].get("original_contract_cents"),
            )
            registered = require_cents(
                f"commitment[{cid}].original_contract_cents",
                commitment.get("original_contract_cents"),
            )
            if stated != registered:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollup, f"rows/{cid}/original_contract_cents"),
                        f"the roster states commitment {cid} original as {fmt(stated)}; "
                        f"the register carries {fmt(registered)}",
                    )
                )
    for cid in sorted(set(rows_by_cid) - set(commitments)):
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(rollup, f"rows/{cid}"),
                f"the roster carries a row for {cid}, which is not in the commitment "
                f"register; it is committed cost with no contract behind it",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the roster ties the register across all {len(commitments)} commitments",
            )
        )
    return out


@check("cmt_revised_rederives")
def check_cmt_revised_rederives(ctx: Context) -> list[Finding]:
    """Each roster row's revised contract = register original + net approved COs.

    This is the committed-cost equality the whole roster exists to state. The
    net change is re-derived from the change-order log through the shared
    kernel -- approved orders only -- and both the stated net and the stated
    revised are compared to it.
    """
    rule = "cmt_revised_rederives"
    _sev(rule, Status.FAIL)
    rollup = _rollup_doc(ctx)
    if rollup is None or ctx.one(DOC_CHANGE_ORDER_LOG) is None:
        return []
    commitments = _commitment_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _rollup_rows(ctx):
        cid = _text(row, "commitment_id")
        commitment = commitments.get(cid or "")
        if cid is None or commitment is None:
            continue  # cmt_rollup_ties_register owns this
        with amount_guard(rule, out):
            original = require_cents(
                f"commitment[{cid}].original_contract_cents",
                commitment.get("original_contract_cents"),
            )
            stated_net = require_cents(
                f"rollup[{cid}].net_changes_cents", row.get("net_changes_cents")
            )
            stated_revised = require_cents(
                f"rollup[{cid}].revised_contract_cents", row.get("revised_contract_cents")
            )
            net = recompute_net_approved_changes(ctx, cid)
            checked += 1
            if stated_net != net:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollup, f"rows/{cid}/net_changes_cents"),
                        f"the roster states {fmt(stated_net)} of net changes on {cid}; "
                        f"the approved change orders re-derive {fmt(net)} -- a pending "
                        f"or void order moves nothing until it is approved",
                    )
                )
            revised = revised_contract_cents(original, net)
            if stated_revised != revised:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollup, f"rows/{cid}/revised_contract_cents"),
                        f"the roster states commitment {cid} revised as "
                        f"{fmt(stated_revised)}; original {fmt(original)} + net approved "
                        f"changes {fmt(net)} re-derives {fmt(revised)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} revised contracts equal original + net approved changes",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# co_ -- the change-order authorization / naming gate
# --------------------------------------------------------------------------- #
@check("co_commitment_exists")
def check_co_commitment_exists(ctx: Context) -> list[Finding]:
    """Every change order names a commitment in the register.

    A change order against no commitment is an amendment to nothing: its amount
    can reach no revised contract and its approval gates nothing.
    """
    rule = "co_commitment_exists"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_CHANGE_ORDER_LOG)
    if log is None:
        return []
    commitments = _commitment_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(log, f"change_orders/{_co_id(row)}/commitment_id"),
            f"change order {_co_id(row)} names commitment "
            f"{_text(row, 'commitment_id')!r}, which is not in the commitment register",
        )
        for row in _change_orders(ctx)
        if _text(row, "commitment_id") and _text(row, "commitment_id") not in commitments
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every change order names a registered commitment"
            )
        )
    return out


@check("co_numbering_sequential")
def check_co_numbering_sequential(ctx: Context) -> list[Finding]:
    """Change orders on a commitment are numbered #-1..#-N with no gap or repeat.

    The procedure applies each change order to the original commitment as the
    next sequential number. A gap is an order that was logged somewhere else --
    or never -- and a repeat is two amendments claiming the same slot.
    """
    rule = "co_numbering_sequential"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_CHANGE_ORDER_LOG)
    if log is None:
        return []
    grouped: dict[str, list[int]] = {}
    out: list[Finding] = []
    for row in _change_orders(ctx):
        cid = _text(row, "commitment_id")
        number = _int(row, "co_number")
        if number is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"change_orders/{_co_id(row)}/co_number"),
                    f"change order {_co_id(row)} carries no readable sequence number; "
                    f"its place in the #-N chain cannot be established",
                )
            )
            continue
        if cid:
            grouped.setdefault(cid, []).append(number)
    for cid, numbers in sorted(grouped.items()):
        expected = list(range(1, len(numbers) + 1))
        if sorted(numbers) != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"change_orders/{cid}"),
                    f"commitment {cid} carries change orders numbered "
                    f"{sorted(numbers)}; the procedure numbers them sequentially "
                    f"{expected} against the original commitment",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"change orders on all {len(grouped)} commitments are numbered "
                f"sequentially",
            )
        )
    return out


@check("co_status_valid")
def check_co_status_valid(ctx: Context) -> list[Finding]:
    """Every change order carries a known status.

    The status decides whether the amount moves the revised contract. An
    unknown status is an order the committed-cost equality can neither count
    nor exclude.
    """
    rule = "co_status_valid"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_CHANGE_ORDER_LOG)
    if log is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(log, f"change_orders/{_co_id(row)}/status"),
            f"change order {_co_id(row)} carries status {_text(row, 'status')!r}, "
            f"which is not one of {CO_STATUSES}; whether it moves the revised "
            f"contract cannot be decided",
        )
        for row in _change_orders(ctx)
        if _text(row, "status") not in CO_STATUSES
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_change_orders(ctx))} change orders carry a known status",
            )
        )
    return out


@check("co_not_split_to_new_commitment")
def check_co_not_split_to_new_commitment(ctx: Context) -> list[Finding]:
    """No commitment on the register originated as a change order.

    The procedure is explicit: a change order -- soft-cost included -- is
    applied to the original commitment as ``#-N``, never booked as a separate
    commitment. A commitment born from a change order splits one contract's
    cost across two ids and breaks every roll-forward that follows it.
    """
    rule = "co_not_split_to_new_commitment"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COMMITMENT_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"commitments/{_commitment_id(row)}/origin"),
            f"commitment {_commitment_id(row)} carries origin "
            f"{_text(row, 'origin')!r}; change orders are applied to the original "
            f"commitment as #-N and must never be booked as a commitment of their own",
        )
        for row in _commitments(ctx)
        if _text(row, "origin") not in COMMITMENT_ORIGINS
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_commitments(ctx))} commitments originated as original "
                f"contracts",
            )
        )
    return out


@check("co_commitment_id_format")
def check_co_commitment_id_format(ctx: Context) -> list[Finding]:
    """Every commitment id is project abbrev + vendor code + sequential count.

    The id is the procedure's naming gate: ``BWC-KETT00-2`` says which project,
    which vendor and which contract with that vendor, in order. An id that does
    not compose from its own row's codes -- or a vendor whose counts skip --
    is a commitment filed under a name the procedure would never have minted.
    """
    rule = "co_commitment_id_format"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COMMITMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    grouped: dict[tuple[str, str], list[int]] = {}
    for row in _commitments(ctx):
        cid = _commitment_id(row)
        project = _text(row, "project_code")
        vendor = _text(row, "vendor_code")
        if cid == "?" or project is None or vendor is None:
            continue  # cmt_required_fields owns this
        match = COMMITMENT_ID_RE.match(cid)
        if match is None or make_commitment_id(project, vendor, int(match.group(3))) != cid:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"commitments/{cid}/commitment_id"),
                    f"commitment id {cid} does not compose as "
                    f"{make_commitment_id(project, vendor, 1)[:-1]}N from its own "
                    f"project code {project!r} and vendor code {vendor!r}",
                )
            )
            continue
        grouped.setdefault((project, vendor), []).append(int(match.group(3)))
    for (project, vendor), seqs in sorted(grouped.items()):
        expected = list(range(1, len(seqs) + 1))
        if sorted(seqs) != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"commitments/{project}-{vendor}"),
                    f"vendor {vendor} on project {project} carries commitment counts "
                    f"{sorted(seqs)}; the procedure numbers them sequentially {expected}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_commitments(ctx))} commitment ids compose from project, "
                f"vendor and sequential count",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# sov_ -- the schedule of values
# --------------------------------------------------------------------------- #
@check("sov_lines_wellformed")
def check_sov_lines_wellformed(ctx: Context) -> list[Finding]:
    """Every SOV line belongs to a registered commitment, once.

    The (commitment, line number) pair is what every pay-app line bills
    against. A line on an unknown commitment is scheduled value with no
    contract, and a duplicated pair makes the billed line ambiguous.
    """
    rule = "sov_lines_wellformed"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_SOV_SCHEDULE)
    if schedule is None:
        return []
    commitments = _commitment_map(ctx)
    seen: dict[tuple[str, int], int] = {}
    out: list[Finding] = []
    for row in _sov_lines(ctx):
        cid = _text(row, "commitment_id")
        line_no = _int(row, "line_no")
        if cid is None or line_no is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"lines/{cid or '?'}/{row.get('line_no', '?')}"),
                    f"an SOV line carries commitment {cid!r} and line number "
                    f"{row.get('line_no')!r}; without both, nothing can bill against it",
                )
            )
            continue
        if cid not in commitments:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"lines/{cid}/{line_no}"),
                    f"SOV line {line_no} names commitment {cid}, which is not in the "
                    f"commitment register",
                )
            )
        seen[(cid, line_no)] = seen.get((cid, line_no), 0) + 1
    for (cid, line_no), count in sorted(seen.items()):
        if count > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"lines/{cid}/{line_no}"),
                    f"SOV line {line_no} on commitment {cid} appears {count} times; a "
                    f"pay-app line that bills it cannot be matched to one scheduled value",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_sov_lines(ctx))} SOV lines are unique and attributable",
            )
        )
    return out


@check("sov_foots_to_original")
def check_sov_foots_to_original(ctx: Context) -> list[Finding]:
    """Each commitment's SOV lines sum exactly to its original contract amount.

    The SOV is the contract price *decomposed*, so the decomposition must foot.
    A schedule that sums past the contract has invented billable value; one
    that sums short has hidden some -- and either way every per-line cap below
    is measured against the wrong denominator.
    """
    rule = "sov_foots_to_original"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_COMMITMENT_REGISTER)
    schedule = ctx.one(DOC_SOV_SCHEDULE)
    if register is None or schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for cid, commitment in sorted(_commitment_map(ctx).items()):
        with amount_guard(rule, out):
            original = require_cents(
                f"commitment[{cid}].original_contract_cents",
                commitment.get("original_contract_cents"),
            )
            footed = 0
            for row in _sov_lines(ctx):
                if _text(row, "commitment_id") != cid:
                    continue
                footed += require_cents(
                    f"sov_line[{cid}/{row.get('line_no', '?')}].scheduled_value_cents",
                    row.get("scheduled_value_cents"),
                )
            checked += 1
            if footed != original:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"lines/{cid}"),
                        f"commitment {cid} SOV lines foot to {fmt(footed)}; the original "
                        f"contract amount is {fmt(original)} "
                        f"(difference {fmt(footed - original)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} commitment SOVs foot to their original contract amounts",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# line_ -- per-line and header pay-app arithmetic
# --------------------------------------------------------------------------- #
@check("line_ref_valid")
def check_line_ref_valid(ctx: Context) -> list[Finding]:
    """Every pay app bills a registered commitment, and every pay-app line an
    SOV line that exists, once.

    A billed line with no scheduled value has no cap, no percent and no balance
    -- every control that should hold it has nothing to hold it to.
    """
    rule = "line_ref_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    commitments = _commitment_map(ctx)
    sov = _sov_map(ctx)
    out: list[Finding] = []
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        if cid is None or cid not in commitments:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"pay_applications/{_app_key(app)}"),
                    f"pay app {_app_key(app)} bills commitment {cid!r}, which is not in "
                    f"the commitment register",
                )
            )
            continue
        seen: dict[int, int] = {}
        for line in _app_lines(app):
            line_no = _int(line, "line_no")
            if line_no is None or (cid, line_no) not in sov:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register,
                            f"pay_applications/{_app_key(app)}/lines/{line.get('line_no', '?')}",
                        ),
                        f"pay app {_app_key(app)} bills line {line.get('line_no')!r}, "
                        f"which is not on commitment {cid}'s schedule of values",
                    )
                )
                continue
            seen[line_no] = seen.get(line_no, 0) + 1
        for line_no, count in sorted(seen.items()):
            if count > 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register, f"pay_applications/{_app_key(app)}/lines/{line_no}"
                        ),
                        f"pay app {_app_key(app)} bills line {line_no} {count} times; "
                        f"the line's billing to date cannot be read off one row",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_pay_apps(ctx))} pay apps bill registered commitments and "
                f"scheduled lines",
            )
        )
    return out


@check("line_completed_rederives")
def check_line_completed_rederives(ctx: Context) -> list[Finding]:
    """Each line's completed-to-date = previously billed + work this period.

    This is the (D+E) column. It is the one figure that carries a line's
    history forward, so it is re-derived rather than read: a completed figure
    that is not the sum of its own two parts is a history that was typed, not
    accumulated.
    """
    rule = "line_completed_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        for line in _app_lines(app):
            key = f"pay_app[{_app_key(app)}].line[{line.get('line_no', '?')}]"
            with amount_guard(rule, out):
                prev = require_cents(
                    f"{key}.previously_billed_cents", line.get("previously_billed_cents")
                )
                work = require_cents(
                    f"{key}.work_this_period_cents", line.get("work_this_period_cents")
                )
                stated = require_cents(
                    f"{key}.total_completed_cents", line.get("total_completed_cents")
                )
                checked += 1
                derived = total_completed_cents(prev, work)
                if stated != derived:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                register,
                                f"pay_applications/{_app_key(app)}/lines/"
                                f"{line.get('line_no', '?')}/total_completed_cents",
                            ),
                            f"line {line.get('line_no')} on pay app {_app_key(app)} "
                            f"states {fmt(stated)} completed; previously billed "
                            f"{fmt(prev)} + this period {fmt(work)} re-derives "
                            f"{fmt(derived)}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} line completed-to-date figures re-derive as D+E",
            )
        )
    return out


@check("line_percent_rederives")
def check_line_percent_rederives(ctx: Context) -> list[Finding]:
    """Each line's stated percent complete re-derives from its own money columns.

    Deliberately a FLAG, not a failure: the money is checked by the equality
    and cap controls, and the percent column is what a reviewer's eye reads
    first -- a stated percent that drifts from the figures beneath it steers
    the review, not the cash. Floored basis points, exact ``==``.
    """
    rule = "line_percent_rederives"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    sov = _sov_map(ctx)
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        for line in _app_lines(app):
            line_no = _int(line, "line_no")
            sov_line = sov.get((cid or "", line_no if line_no is not None else -1))
            if sov_line is None:
                continue  # line_ref_valid owns this
            key = f"pay_app[{_app_key(app)}].line[{line_no}]"
            with amount_guard(rule, out):
                completed = require_cents(
                    f"{key}.total_completed_cents", line.get("total_completed_cents")
                )
                scheduled = require_cents(
                    f"sov_line[{cid}/{line_no}].scheduled_value_cents",
                    sov_line.get("scheduled_value_cents"),
                )
                stated = require_cents(
                    f"{key}.percent_complete_bps",
                    line.get("percent_complete_bps"),
                    unit="integer basis points",
                )
                checked += 1
                derived = percent_complete(completed, scheduled)
                if stated != derived:
                    out.append(
                        Finding(
                            rule,
                            Status.FLAG,
                            ctx.loc(
                                register,
                                f"pay_applications/{_app_key(app)}/lines/{line_no}/"
                                f"percent_complete_bps",
                            ),
                            f"line {line_no} on pay app {_app_key(app)} states "
                            f"{fmt_bps(stated)} complete; {fmt(completed)} against "
                            f"{fmt(scheduled)} scheduled re-derives {fmt_bps(derived)}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} stated percent-complete figures re-derive, floored",
            )
        )
    return out


@check("line_header_foots")
def check_line_header_foots(ctx: Context) -> list[Finding]:
    """Each pay app's header totals foot to its own lines.

    The header is what the certificate is signed on, and a header maintained
    beside the lines rather than summed from them drifts the first time a line
    moves and nobody re-adds the column.
    """
    rule = "line_header_foots"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        totals = _app_totals(app)
        key = f"pay_app[{_app_key(app)}]"
        with amount_guard(rule, out):
            completed_sum = 0
            prev_sum = 0
            for line in _app_lines(app):
                line_key = f"{key}.line[{line.get('line_no', '?')}]"
                completed_sum += require_cents(
                    f"{line_key}.total_completed_cents", line.get("total_completed_cents")
                )
                prev_sum += require_cents(
                    f"{line_key}.previously_billed_cents",
                    line.get("previously_billed_cents"),
                )
            stated_completed = require_cents(
                f"{key}.totals.total_completed_cents", totals.get("total_completed_cents")
            )
            stated_prev = require_cents(
                f"{key}.totals.total_previously_billed_cents",
                totals.get("total_previously_billed_cents"),
            )
            checked += 1
            for label, stated, footed in (
                ("total_completed_cents", stated_completed, completed_sum),
                ("total_previously_billed_cents", stated_prev, prev_sum),
            ):
                if stated != footed:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                register, f"pay_applications/{_app_key(app)}/totals/{label}"
                            ),
                            f"pay app {_app_key(app)} header states {label} of "
                            f"{fmt(stated)}; its own lines foot to {fmt(footed)}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} pay-app headers foot to their lines"
            )
        )
    return out


@check("line_current_request_rederives")
def check_line_current_request_rederives(ctx: Context) -> list[Finding]:
    """Each pay app's current request = completed to date - previously billed.

    The request is the only line on the certificate that moves money this
    period, and it is a difference, not a fact: stated anywhere other than as
    that difference, it double-bills or under-bills by exactly the drift.
    """
    rule = "line_current_request_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        totals = _app_totals(app)
        key = f"pay_app[{_app_key(app)}].totals"
        with amount_guard(rule, out):
            completed = require_cents(
                f"{key}.total_completed_cents", totals.get("total_completed_cents")
            )
            prev = require_cents(
                f"{key}.total_previously_billed_cents",
                totals.get("total_previously_billed_cents"),
            )
            stated = require_cents(
                f"{key}.current_request_cents", totals.get("current_request_cents")
            )
            checked += 1
            derived = current_request_cents(completed, prev)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register,
                            f"pay_applications/{_app_key(app)}/totals/current_request_cents",
                        ),
                        f"pay app {_app_key(app)} requests {fmt(stated)}; completed "
                        f"{fmt(completed)} - previously billed {fmt(prev)} re-derives "
                        f"{fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} current requests re-derive as completed - previously billed",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cap_ -- the billing-to-date cap
# --------------------------------------------------------------------------- #
@check("cap_not_overbilled")
def check_cap_not_overbilled(ctx: Context) -> list[Finding]:
    """No line bills past its scheduled value.

    Compared with exact ``<=``: a line completed to the cent of its scheduled
    value is fully billed, and a cent past it is billing against value the
    contract never scheduled. Overbilling hides well -- the app still foots --
    which is why the cap is tested per line, not per total.
    """
    rule = "cap_not_overbilled"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    sov = _sov_map(ctx)
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        for line in _app_lines(app):
            line_no = _int(line, "line_no")
            sov_line = sov.get((cid or "", line_no if line_no is not None else -1))
            if sov_line is None:
                continue  # line_ref_valid owns this
            key = f"pay_app[{_app_key(app)}].line[{line_no}]"
            with amount_guard(rule, out):
                completed = require_cents(
                    f"{key}.total_completed_cents", line.get("total_completed_cents")
                )
                scheduled = require_cents(
                    f"sov_line[{cid}/{line_no}].scheduled_value_cents",
                    sov_line.get("scheduled_value_cents"),
                )
                checked += 1
                if completed > scheduled:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                register,
                                f"pay_applications/{_app_key(app)}/lines/{line_no}/"
                                f"total_completed_cents",
                            ),
                            f"line {line_no} on pay app {_app_key(app)} is billed to "
                            f"{fmt(completed)} against a scheduled value of "
                            f"{fmt(scheduled)}; the line is overbilled by "
                            f"{fmt(completed - scheduled)}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} billed lines are within their scheduled values",
            )
        )
    return out


@check("cap_balance_rederives")
def check_cap_balance_rederives(ctx: Context) -> list[Finding]:
    """Each line's balance to finish = scheduled value - completed to date.

    The balance is what remains to buy on the line, and a stated balance that
    is not this difference misstates the cost to complete by exactly the drift
    -- in either direction.
    """
    rule = "cap_balance_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    sov = _sov_map(ctx)
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        for line in _app_lines(app):
            line_no = _int(line, "line_no")
            sov_line = sov.get((cid or "", line_no if line_no is not None else -1))
            if sov_line is None:
                continue  # line_ref_valid owns this
            key = f"pay_app[{_app_key(app)}].line[{line_no}]"
            with amount_guard(rule, out):
                completed = require_cents(
                    f"{key}.total_completed_cents", line.get("total_completed_cents")
                )
                scheduled = require_cents(
                    f"sov_line[{cid}/{line_no}].scheduled_value_cents",
                    sov_line.get("scheduled_value_cents"),
                )
                stated = require_cents(
                    f"{key}.balance_to_finish_cents", line.get("balance_to_finish_cents")
                )
                checked += 1
                derived = balance_to_finish_cents(scheduled, completed)
                if stated != derived:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                register,
                                f"pay_applications/{_app_key(app)}/lines/{line_no}/"
                                f"balance_to_finish_cents",
                            ),
                            f"line {line_no} on pay app {_app_key(app)} states "
                            f"{fmt(stated)} to finish; scheduled {fmt(scheduled)} - "
                            f"completed {fmt(completed)} re-derives {fmt(derived)}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} balance-to-finish figures re-derive exactly",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# ret_ -- retention re-derivation
# --------------------------------------------------------------------------- #
@check("ret_rate_known")
def check_ret_rate_known(ctx: Context) -> list[Finding]:
    """Each commitment's retention rate sits on the standard all-lines menu.

    Deliberately a FLAG, not a failure: the arithmetic control below holds the
    stated retention to whatever rate the contract carries, so an off-menu rate
    is not a broken figure -- it is a contract term someone should read the
    contract to confirm. The menu is 5% or 10%, all line items.
    """
    rule = "ret_rate_known"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_COMMITMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _commitments(ctx):
        cid = _commitment_id(row)
        with amount_guard(rule, out):
            rate = require_cents(
                f"commitment[{cid}].retention_rate_bps",
                row.get("retention_rate_bps"),
                unit="integer basis points",
            )
            checked += 1
            if rate not in STANDARD_RETENTION_RATES_BPS:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"commitments/{cid}/retention_rate_bps"),
                        f"commitment {cid} carries retention at {fmt_bps(rate)}; the "
                        f"standard all-lines menu is "
                        f"{' / '.join(fmt_bps(r) for r in STANDARD_RETENTION_RATES_BPS)}"
                        f" -- confirm the contract actually says so",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} retention rates sit on the standard menu",
            )
        )
    return out


@check("ret_rederives")
def check_ret_rederives(ctx: Context) -> list[Finding]:
    """Each pay app's retention = the contract rate on the current request.

    Truncating basis-point arithmetic through the shared kernel, compared with
    exact ``==``. Retention held short is protection the developer does not
    have; held long, it is the subcontractor's cash sitting in the wrong hands.
    """
    rule = "ret_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    commitments = _commitment_map(ctx)
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        commitment = commitments.get(cid or "")
        if commitment is None:
            continue  # line_ref_valid owns this
        totals = _app_totals(app)
        key = f"pay_app[{_app_key(app)}].totals"
        with amount_guard(rule, out):
            rate = require_cents(
                f"commitment[{cid}].retention_rate_bps",
                commitment.get("retention_rate_bps"),
                unit="integer basis points",
            )
            request = require_cents(
                f"{key}.current_request_cents", totals.get("current_request_cents")
            )
            stated = require_cents(
                f"{key}.retention_cents", totals.get("retention_cents")
            )
            checked += 1
            derived = retention_cents(request, rate)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register,
                            f"pay_applications/{_app_key(app)}/totals/retention_cents",
                        ),
                        f"pay app {_app_key(app)} states retention of {fmt(stated)}; "
                        f"{fmt_bps(rate)} on the {fmt(request)} request re-derives "
                        f"{fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} retention figures re-derive at the contract rate",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# tax_ -- tax and payment-due re-derivation
# --------------------------------------------------------------------------- #
@check("tax_rederives")
def check_tax_rederives(ctx: Context) -> list[Finding]:
    """Each pay app's sales tax = the contract tax rate on the taxable request,
    and the taxable request is the current request.

    These commitments bill fully-taxable construction, so the taxable base is
    the request itself; a base that drifts from the request un-taxes part of
    the billing, and a tax figure off the rate mis-certifies the remittance.
    """
    rule = "tax_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    commitments = _commitment_map(ctx)
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        commitment = commitments.get(cid or "")
        if commitment is None:
            continue  # line_ref_valid owns this
        totals = _app_totals(app)
        key = f"pay_app[{_app_key(app)}].totals"
        with amount_guard(rule, out):
            rate = require_cents(
                f"commitment[{cid}].tax_rate_bps",
                commitment.get("tax_rate_bps"),
                unit="integer basis points",
            )
            request = require_cents(
                f"{key}.current_request_cents", totals.get("current_request_cents")
            )
            taxable = require_cents(
                f"{key}.taxable_request_cents", totals.get("taxable_request_cents")
            )
            stated = require_cents(
                f"{key}.sales_tax_cents", totals.get("sales_tax_cents")
            )
            checked += 1
            if taxable != request:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register,
                            f"pay_applications/{_app_key(app)}/totals/taxable_request_cents",
                        ),
                        f"pay app {_app_key(app)} states a taxable request of "
                        f"{fmt(taxable)} against a current request of {fmt(request)}; "
                        f"these commitments bill fully-taxable work",
                    )
                )
            derived = sales_tax_cents(taxable, rate)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register,
                            f"pay_applications/{_app_key(app)}/totals/sales_tax_cents",
                        ),
                        f"pay app {_app_key(app)} states sales tax of {fmt(stated)}; "
                        f"{fmt_bps(rate)} on the {fmt(taxable)} taxable request "
                        f"re-derives {fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} sales-tax figures re-derive at the contract rate",
            )
        )
    return out


@check("tax_payment_due_rederives")
def check_tax_payment_due_rederives(ctx: Context) -> list[Finding]:
    """Each pay app's payment due incl tax = request - retention + sales tax.

    This is the certified figure the cheque is cut for and the conditional
    release is signed against, so it is re-derived from the three figures above
    it rather than read. A drift here pays the wrong amount with a straight
    face.
    """
    rule = "tax_payment_due_rederives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for app in _pay_apps(ctx):
        totals = _app_totals(app)
        key = f"pay_app[{_app_key(app)}].totals"
        with amount_guard(rule, out):
            request = require_cents(
                f"{key}.current_request_cents", totals.get("current_request_cents")
            )
            retention = require_cents(
                f"{key}.retention_cents", totals.get("retention_cents")
            )
            tax = require_cents(f"{key}.sales_tax_cents", totals.get("sales_tax_cents"))
            stated = require_cents(
                f"{key}.payment_due_incl_tax_cents",
                totals.get("payment_due_incl_tax_cents"),
            )
            checked += 1
            derived = payment_due_cents(request, retention, tax)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register,
                            f"pay_applications/{_app_key(app)}/totals/"
                            f"payment_due_incl_tax_cents",
                        ),
                        f"pay app {_app_key(app)} certifies {fmt(stated)} due; request "
                        f"{fmt(request)} - retention {fmt(retention)} + tax {fmt(tax)} "
                        f"re-derives {fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} payment-due figures re-derive as request - retention + tax",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# roll_ -- the pay-app roll-forward
# --------------------------------------------------------------------------- #
@check("roll_previously_ties_prior")
def check_roll_previously_ties_prior(ctx: Context) -> list[Finding]:
    """Previously billed on app N equals total completed on app N-1, and the
    first app starts from zero.

    This is the chain that makes twelve monthly certificates one continuous
    billing. A break here is a period whose opening balance was typed rather
    than carried, and every figure downstream of it inherits the drift.
    """
    rule = "roll_previously_ties_prior"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for cid, apps in sorted(_apps_by_commitment(ctx).items()):
        prior_completed = 0
        prior_label = "the opening of the commitment"
        for app in apps:
            totals = _app_totals(app)
            key = f"pay_app[{_app_key(app)}].totals"
            with amount_guard(rule, out):
                stated_prev = require_cents(
                    f"{key}.total_previously_billed_cents",
                    totals.get("total_previously_billed_cents"),
                )
                checked += 1
                if stated_prev != prior_completed:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                register,
                                f"pay_applications/{_app_key(app)}/totals/"
                                f"total_previously_billed_cents",
                            ),
                            f"pay app {_app_key(app)} opens with {fmt(stated_prev)} "
                            f"previously billed; {prior_label} closed at "
                            f"{fmt(prior_completed)} -- the roll-forward is broken by "
                            f"{fmt(stated_prev - prior_completed)}",
                        )
                    )
                prior_completed = require_cents(
                    f"{key}.total_completed_cents", totals.get("total_completed_cents")
                )
                prior_label = f"pay app {_app_key(app)}"
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} pay apps roll forward from the prior period exactly",
            )
        )
    return out


@check("roll_apps_sequential")
def check_roll_apps_sequential(ctx: Context) -> list[Finding]:
    """Each commitment's pay apps are numbered 1..N with periods that advance.

    A gap in the app numbers is a billing period unaccounted for; a repeat is
    two certificates claiming one period; and a period-end that fails to
    advance with the number puts the chain in an order the roll-forward
    control would silently misread.
    """
    rule = "roll_apps_sequential"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAY_APP_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        if _int(app, "app_no") is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"pay_applications/{_app_key(app)}/app_no"),
                    f"pay app {_app_key(app)} carries no readable app number; its place "
                    f"in the billing sequence cannot be established",
                )
            )
            continue
        if cid:
            grouped.setdefault(cid, []).append(app)
    for cid, apps in sorted(grouped.items()):
        numbers = sorted(_int(a, "app_no") or 0 for a in apps)
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"pay_applications/{cid}"),
                    f"commitment {cid} carries pay apps numbered {numbers}; a continuous "
                    f"billing runs {expected} with no gap or repeat",
                )
            )
        ordered = sorted(apps, key=lambda a: (_int(a, "app_no") or 0))
        prior: tuple[int, date] | None = None
        for app in ordered:
            period_end = _parse_date(app.get("period_end"))
            if period_end is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"pay_applications/{_app_key(app)}/period_end"),
                        f"pay app {_app_key(app)} carries no readable period end; the "
                        f"billing chain cannot be dated",
                    )
                )
                continue
            if prior is not None and period_end <= prior[1]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"pay_applications/{_app_key(app)}/period_end"),
                        f"pay app {_app_key(app)} closes {period_end.isoformat()}, not "
                        f"after app {prior[0]}'s {prior[1].isoformat()}; the periods do "
                        f"not advance with the numbering",
                    )
                )
            prior = (_int(app, "app_no") or 0, period_end)
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"pay apps on all {len(grouped)} commitments are sequential and dated "
                f"in order",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# port_ -- portfolio footing across commitments
# --------------------------------------------------------------------------- #
@check("port_totals_foot")
def check_port_totals_foot(ctx: Context) -> list[Finding]:
    """Each Total column on the committed-cost roster foots to its rows.

    The Total row is the number that leaves the workbook -- to the lender, to
    the job-cost report -- and a Total maintained beside the rows rather than
    summed from them drifts the first time a commitment moves.
    """
    rule = "port_totals_foot"
    _sev(rule, Status.FAIL)
    rollup = _rollup_doc(ctx)
    if rollup is None:
        return []
    totals = _rollup_totals(ctx)
    out: list[Finding] = []
    with amount_guard(rule, out):
        sums = {"original_contract_cents": 0, "net_changes_cents": 0, "revised_contract_cents": 0}
        for row in _rollup_rows(ctx):
            cid = _text(row, "commitment_id") or "?"
            for field in sums:
                sums[field] += require_cents(f"rollup[{cid}].{field}", row.get(field))
        for total_field, row_field in (
            ("original_total_cents", "original_contract_cents"),
            ("changes_total_cents", "net_changes_cents"),
            ("revised_total_cents", "revised_contract_cents"),
        ):
            stated = require_cents(
                f"rollup.totals.{total_field}", totals.get(total_field)
            )
            if stated != sums[row_field]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollup, f"totals/{total_field}"),
                        f"the roster states {total_field} of {fmt(stated)}; its "
                        f"{len(_rollup_rows(ctx))} commitment rows foot to "
                        f"{fmt(sums[row_field])}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all 3 Total columns foot across {len(_rollup_rows(ctx))} commitments",
            )
        )
    return out


@check("port_revised_identity")
def check_port_revised_identity(ctx: Context) -> list[Finding]:
    """The roster's revised total = original total + changes total.

    The committed-cost equality must hold at the Total row too: the three
    footers are three views of one portfolio, and if they disagree, at least
    one column was footed from different rows than the others.
    """
    rule = "port_revised_identity"
    _sev(rule, Status.FAIL)
    rollup = _rollup_doc(ctx)
    if rollup is None:
        return []
    totals = _rollup_totals(ctx)
    out: list[Finding] = []
    with amount_guard(rule, out):
        original = require_cents(
            "rollup.totals.original_total_cents", totals.get("original_total_cents")
        )
        changes = require_cents(
            "rollup.totals.changes_total_cents", totals.get("changes_total_cents")
        )
        revised = require_cents(
            "rollup.totals.revised_total_cents", totals.get("revised_total_cents")
        )
        derived = revised_contract_cents(original, changes)
        if revised != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, "totals/revised_total_cents"),
                    f"the roster's revised total is {fmt(revised)}; original total "
                    f"{fmt(original)} + changes total {fmt(changes)} re-derives "
                    f"{fmt(derived)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the revised total of {fmt(revised)} equals original + changes",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# lien_ -- the conditional release cross-tie
# --------------------------------------------------------------------------- #
@check("lien_release_per_app")
def check_lien_release_per_app(ctx: Context) -> list[Finding]:
    """Every pay app carries exactly one conditional release, and every release
    a pay app.

    A pay app with no release is money paid with the lien exposure still open;
    a release attached to no pay app is a waiver signed against nothing; and
    two releases on one app leave the certified amount ambiguous.
    """
    rule = "lien_release_per_app"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LIEN_RELEASE_REGISTER)
    if register is None or ctx.one(DOC_PAY_APP_REGISTER) is None:
        return []
    apps: dict[tuple[str, int], dict[str, Any]] = {}
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        app_no = _int(app, "app_no")
        if cid and app_no is not None and (cid, app_no) not in apps:
            apps[(cid, app_no)] = app
    matched: dict[tuple[str, int], int] = {}
    out: list[Finding] = []
    for release in _releases(ctx):
        cid = _text(release, "commitment_id")
        app_no = _int(release, "app_no")
        release_id = _text(release, "release_id") or "?"
        rtype = _text(release, "release_type")
        if rtype != RELEASE_CONDITIONAL:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"releases/{release_id}/release_type"),
                    f"release {release_id} is typed {rtype!r}; this register carries the "
                    f"conditional release exchanged for each current payment",
                )
            )
            continue
        if cid is None or app_no is None or (cid, app_no) not in apps:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"releases/{release_id}"),
                    f"release {release_id} references pay app {cid}/app-{app_no}, which "
                    f"is not in the pay-application register; it waives lien rights "
                    f"against no billing",
                )
            )
            continue
        matched[(cid, app_no)] = matched.get((cid, app_no), 0) + 1
    for (cid, app_no), _app in sorted(apps.items()):
        count = matched.get((cid, app_no), 0)
        if count != 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"releases/{cid}/app-{app_no}"),
                    f"pay app {cid}/app-{app_no} carries {count} conditional release(s); "
                    f"each certified payment is exchanged for exactly one",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(apps)} pay apps carry exactly one conditional release",
            )
        )
    return out


@check("lien_amount_ties")
def check_lien_amount_ties(ctx: Context) -> list[Finding]:
    """Each conditional release is signed for the certified payment due incl tax.

    This is the cross-tie the family exists for. The release is the document
    the money is exchanged for, and a release amount that differs from the
    certified payment waives the wrong rights -- too few, and the payment is
    exposed; too many, and the subcontractor waived rights it was never paid
    for.
    """
    rule = "lien_amount_ties"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_LIEN_RELEASE_REGISTER)
    if register is None or ctx.one(DOC_PAY_APP_REGISTER) is None:
        return []
    apps: dict[tuple[str, int], dict[str, Any]] = {}
    for app in _pay_apps(ctx):
        cid = _text(app, "commitment_id")
        app_no = _int(app, "app_no")
        if cid and app_no is not None and (cid, app_no) not in apps:
            apps[(cid, app_no)] = app
    out: list[Finding] = []
    checked = 0
    for release in _releases(ctx):
        cid = _text(release, "commitment_id")
        app_no = _int(release, "app_no")
        release_id = _text(release, "release_id") or "?"
        if _text(release, "release_type") != RELEASE_CONDITIONAL:
            continue  # lien_release_per_app owns this
        app = apps.get((cid or "", app_no if app_no is not None else -1))
        if app is None:
            continue  # lien_release_per_app owns this
        totals = _app_totals(app)
        with amount_guard(rule, out):
            stated = require_cents(
                f"release[{release_id}].amount_cents", release.get("amount_cents")
            )
            certified = require_cents(
                f"pay_app[{cid}/app-{app_no}].totals.payment_due_incl_tax_cents",
                totals.get("payment_due_incl_tax_cents"),
            )
            checked += 1
            if stated != certified:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"releases/{release_id}/amount_cents"),
                        f"release {release_id} is signed for {fmt(stated)}; pay app "
                        f"{cid}/app-{app_no} certifies {fmt(certified)} due including "
                        f"tax (difference {fmt(stated - certified)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} conditional releases tie the certified payment due",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one billing file."""
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
    """Analyze every ``.json`` billing file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of billing-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
