"""
Warranty reimbursement control engine (READ-ONLY).
==================================================

Loads each claim file (a ``.json`` file produced by
:mod:`warranty_engine.generate`) and runs an ordered *registry* of independent
controls over it.

The shape of the problem
------------------------
A builder buys a warranty policy at the start of a project, then spends years
claiming against it a few thousand dollars at a time. Each claim is trivially
small; the pool behind them is finite. So the failure mode is **accumulation**,
and the boundaries at the edges of each period. Any one claim is obviously fine.
The running total is what goes wrong, and nobody reviewing a single claim can see
it.

The registry is organised around that:

1. ``set_``  -- is the claim file complete enough to be worth reading?
2. ``pol_``  -- are the policy terms internally consistent, and is the pool intact?
3. ``clm_``  -- does each claim sit inside its period, and do the periods foot?
4. ``cost_`` -- is there a real warranty cost behind every claimed dollar?
5. ``unit_`` -- did the unit close before the defect it is being claimed for?
6. ``rem_``  -- is the money being sent to the right place?

Design notes
------------
- **Strictly read-only.** Claim files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Amounts are compared with exact ``==``.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.

The derivation chain
--------------------
Three numbers are typed once at policy inception and trusted forever after:
construction cost, premium, and coverage limit. The second is a rate on the
first and the third is a multiple of the second, so all three can be re-derived
and checked -- which matters because every later control measures against a
coverage limit that nobody re-examines once the policy is bound.
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
    DOC_CLAIMS_HISTORY,
    DOC_CLAIM_SUBMISSION,
    DOC_CLOSED_UNITS,
    DOC_COST_LEDGER,
    DOC_POLICY,
    DOC_TYPES,
    WARRANTY_COST_CODES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, apply_rate, fmt, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}

#: Coverage below this fraction of the limit is flagged as nearly exhausted.
COVERAGE_WARN_BPS = 1500  # 15.00% remaining


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~warranty_engine.money.AmountInvalidError` as a finding."""
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


def _all_claims(ctx: Context) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every claim line paired with the reporting period it sits in."""
    history = ctx.one(DOC_CLAIMS_HISTORY)
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for period in _rows(history, "periods"):
        for line in _rows(period, "claims"):
            out.append((period, line))
    return out


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
                               f"claim file carries no {doc_type}; absent evidence is not "
                               f"a passing control, so no downstream rule may read it"))
        elif len(found) > 1:
            out.append(Finding(rule, Status.FAIL, f"file:{ctx.file_id}/{doc_type}",
                               f"claim file carries {len(found)} {doc_type} documents; "
                               f"exactly one is expected"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(DOC_TYPES)} artifact types present exactly once"))
    return out


@check("set_period_label")
def set_period_label(ctx: Context) -> list[Finding]:
    """The claim file must declare a well-formed quarterly reporting period."""
    rule = "set_period_label"
    _sev(rule, Status.FAIL)
    if not _PERIOD_RE.match(ctx.period):
        return [Finding(rule, Status.FAIL, f"file:{ctx.file_id}/period",
                        f"reporting period {ctx.period!r} is not a YYYY-Qn label; every "
                        f"claim is filed against a quarter and cannot be placed without one")]
    return [Finding(rule, Status.PASS, "-",
                    f"reporting period {ctx.period} is well formed")]


# --------------------------------------------------------------------------- #
# 2. pol_* -- policy terms and the pool
# --------------------------------------------------------------------------- #
@check("pol_premium_derived_from_cost")
def pol_premium_derived_from_cost(ctx: Context) -> list[Finding]:
    """Premium must equal construction cost at the declared rate.

    Typed once at inception and trusted forever after. Every later control
    measures against a coverage limit that descends from this number, so an error
    here silently rescales the whole policy.
    """
    rule = "pol_premium_derived_from_cost"
    _sev(rule, Status.FAIL)
    pol = ctx.one(DOC_POLICY)
    if pol is None:
        return []
    out: list[Finding] = []
    rate = pol.get("premium_rate_bps")
    if not isinstance(rate, int) or isinstance(rate, bool):
        return [Finding(rule, Status.FAIL, ctx.loc(pol, "premium_rate_bps"),
                        "the policy declares no integer basis-point premium rate, so the "
                        "premium cannot be shown to be right")]
    with amount_guard(rule, out):
        cost = require_cents("policy.construction_cost_cents",
                             pol.get("construction_cost_cents"))
        premium = require_cents("policy.premium_cents", pol.get("premium_cents"))
        expected = apply_rate(cost, rate)
        if premium != expected:
            out.append(Finding(rule, Status.FAIL, ctx.loc(pol, "premium_cents"),
                               f"construction cost {fmt(cost)} at {rate / 100:.2f}% derives "
                               f"a premium of {fmt(expected)}, but {fmt(premium)} is "
                               f"recorded"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "premium derives from construction cost"))
    return out


@check("pol_coverage_derived_from_premium")
def pol_coverage_derived_from_premium(ctx: Context) -> list[Finding]:
    """The coverage limit must equal the premium at the declared multiple."""
    rule = "pol_coverage_derived_from_premium"
    _sev(rule, Status.FAIL)
    pol = ctx.one(DOC_POLICY)
    if pol is None:
        return []
    out: list[Finding] = []
    mult = pol.get("coverage_multiple_bps")
    if not isinstance(mult, int) or isinstance(mult, bool):
        return [Finding(rule, Status.FAIL, ctx.loc(pol, "coverage_multiple_bps"),
                        "the policy declares no integer basis-point coverage multiple")]
    with amount_guard(rule, out):
        premium = require_cents("policy.premium_cents", pol.get("premium_cents"))
        limit = require_cents("policy.coverage_limit_cents",
                              pol.get("coverage_limit_cents"))
        expected = apply_rate(premium, mult)
        if limit != expected:
            out.append(Finding(rule, Status.FAIL, ctx.loc(pol, "coverage_limit_cents"),
                               f"premium {fmt(premium)} at {mult / 100:.2f}% derives a "
                               f"coverage limit of {fmt(expected)}, but {fmt(limit)} is "
                               f"recorded"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "coverage limit derives from premium"))
    return out


@check("pol_period_length")
def pol_period_length(ctx: Context) -> list[Finding]:
    """The policy period must run for the declared number of months."""
    rule = "pol_period_length"
    _sev(rule, Status.FAIL)
    pol = ctx.one(DOC_POLICY)
    if pol is None:
        return []
    start = _parse_date(pol.get("policy_start"))
    end = _parse_date(pol.get("policy_end"))
    months = pol.get("policy_months")
    if start is None or end is None:
        return [Finding(rule, Status.FAIL, ctx.loc(pol, "policy_start"),
                        "the policy period has no readable start or end date, so no claim "
                        "in this file can be shown to fall inside it")]
    if not isinstance(months, int) or isinstance(months, bool):
        return [Finding(rule, Status.FAIL, ctx.loc(pol, "policy_months"),
                        "the policy declares no term in months")]
    expected_year = start.year + (start.month - 1 + months) // 12
    expected_month = (start.month - 1 + months) % 12 + 1
    expected = date(expected_year, expected_month, start.day)
    if end != expected:
        return [Finding(rule, Status.FAIL, ctx.loc(pol, "policy_end"),
                        f"a {months}-month policy starting {start.isoformat()} ends "
                        f"{expected.isoformat()}, but {end.isoformat()} is recorded")]
    return [Finding(rule, Status.PASS, "-",
                    f"the policy runs {months} months, {start.isoformat()} to "
                    f"{end.isoformat()}")]


@check("pol_cumulative_within_limit")
def pol_cumulative_within_limit(ctx: Context) -> list[Finding]:
    """Cumulative reimbursement, including this request, may not exceed the limit.

    The pool is finite and this is the control that says so. Every individual
    claim looks affordable; only the running total does not.
    """
    rule = "pol_cumulative_within_limit"
    _sev(rule, Status.FAIL)
    pol = ctx.one(DOC_POLICY)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if pol is None or sub is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        limit = require_cents("policy.coverage_limit_cents",
                              pol.get("coverage_limit_cents"))
        cumulative = require_cents("submission.cumulative_reimbursement_cents",
                                   sub.get("cumulative_reimbursement_cents"))
        if cumulative > limit:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(sub, "cumulative_reimbursement_cents"),
                               f"cumulative reimbursement of {fmt(cumulative)} exceeds the "
                               f"{fmt(limit)} coverage limit by "
                               f"{fmt(cumulative - limit)}; the pool is finite and the "
                               f"excess is not recoverable"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "cumulative reimbursement is inside the coverage limit"))
    return out


@check("pol_remaining_is_limit_less_cumulative")
def pol_remaining_is_limit_less_cumulative(ctx: Context) -> list[Finding]:
    """Coverage remaining must equal the limit less cumulative reimbursement."""
    rule = "pol_remaining_is_limit_less_cumulative"
    _sev(rule, Status.FAIL)
    pol = ctx.one(DOC_POLICY)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if pol is None or sub is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        limit = require_cents("policy.coverage_limit_cents",
                              pol.get("coverage_limit_cents"))
        cumulative = require_cents("submission.cumulative_reimbursement_cents",
                                   sub.get("cumulative_reimbursement_cents"))
        remaining = require_cents("submission.coverage_remaining_cents",
                                  sub.get("coverage_remaining_cents"))
        if limit - cumulative != remaining:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(sub, "coverage_remaining_cents"),
                               f"limit {fmt(limit)} less cumulative {fmt(cumulative)} = "
                               f"{fmt(limit - cumulative)}, but coverage remaining is "
                               f"stated as {fmt(remaining)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "coverage remaining derives correctly"))
    return out


@check("pol_coverage_not_nearly_exhausted")
def pol_coverage_not_nearly_exhausted(ctx: Context) -> list[Finding]:
    """Flag when little of the pool is left.

    Not a failure -- the claim is still valid. It is reported because the point at
    which someone needs to know the pool is running out is well before the claim
    that finally breaches it.
    """
    rule = "pol_coverage_not_nearly_exhausted"
    _sev(rule, Status.FLAG)
    pol = ctx.one(DOC_POLICY)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if pol is None or sub is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        limit = require_cents("policy.coverage_limit_cents",
                              pol.get("coverage_limit_cents"))
        remaining = require_cents("submission.coverage_remaining_cents",
                                  sub.get("coverage_remaining_cents"))
        if limit > 0 and 0 <= remaining * 10000 // limit < COVERAGE_WARN_BPS:
            pct = remaining * 10000 // limit
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(sub, "coverage_remaining_cents"),
                               f"only {fmt(remaining)} of the {fmt(limit)} pool remains "
                               f"({pct / 100:.2f}%); further defects on this project will "
                               f"not be recoverable once it is gone"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "coverage remaining is comfortable"))
    return out


# --------------------------------------------------------------------------- #
# 3. clm_* -- claims and reporting periods
# --------------------------------------------------------------------------- #
@check("clm_period_subtotals_foot")
def clm_period_subtotals_foot(ctx: Context) -> list[Finding]:
    """Each reporting period's subtotal must foot from its own claim lines."""
    rule = "clm_period_subtotals_foot"
    _sev(rule, Status.FAIL)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    if history is None:
        return []
    out: list[Finding] = []
    periods = _rows(history, "periods")
    for period in periods:
        label = period.get("period")
        summed = 0
        readable = True
        for line in _rows(period, "claims"):
            try:
                summed += require_cents(
                    f"history.{label}.claims[{line.get('claim_no')}].amount_cents",
                    line.get("amount_cents"))
            except AmountInvalidError as exc:
                out.append(amount_invalid_finding(rule, exc))
                readable = False
        if not readable:
            continue
        with amount_guard(rule, out):
            declared = require_cents(f"history.{label}.subtotal_cents",
                                     period.get("subtotal_cents"))
            if summed != declared:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(history, f"periods/{label}/subtotal_cents"),
                                   f"{label}: claim lines sum to {fmt(summed)} but the "
                                   f"subtotal declares {fmt(declared)} "
                                   f"(difference {fmt(summed - declared)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(periods)} reporting periods foot"))
    return out


@check("clm_cumulative_is_sum_of_periods")
def clm_cumulative_is_sum_of_periods(ctx: Context) -> list[Finding]:
    """Cumulative reimbursement must equal the sum of every period subtotal.

    This is the link between the individual claims and the pool. Without it the
    two halves of the file can each be internally consistent while disagreeing
    about how much has been spent.
    """
    rule = "clm_cumulative_is_sum_of_periods"
    _sev(rule, Status.FAIL)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if history is None or sub is None:
        return []
    out: list[Finding] = []
    summed = 0
    for period in _rows(history, "periods"):
        with amount_guard(rule, out):
            summed += require_cents(f"history.{period.get('period')}.subtotal_cents",
                                    period.get("subtotal_cents"))
    with amount_guard(rule, out):
        cumulative = require_cents("submission.cumulative_reimbursement_cents",
                                   sub.get("cumulative_reimbursement_cents"))
        if summed != cumulative:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(sub, "cumulative_reimbursement_cents"),
                               f"period subtotals sum to {fmt(summed)} but cumulative "
                               f"reimbursement is stated as {fmt(cumulative)} "
                               f"(difference {fmt(summed - cumulative)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"cumulative reimbursement equals the period subtotals at "
                           f"{fmt(summed)}"))
    return out


@check("clm_request_matches_current_period")
def clm_request_matches_current_period(ctx: Context) -> list[Finding]:
    """The amount being requested must equal this period's subtotal."""
    rule = "clm_request_matches_current_period"
    _sev(rule, Status.FAIL)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if history is None or sub is None:
        return []
    current = next((p for p in _rows(history, "periods")
                    if p.get("period") == ctx.period), None)
    if current is None:
        return [Finding(rule, Status.FAIL, ctx.loc(history, "periods"),
                        f"the claims history carries no period {ctx.period}, which is the "
                        f"period this submission is filed for")]
    out: list[Finding] = []
    with amount_guard(rule, out):
        requested = require_cents("submission.reimbursement_requested_cents",
                                  sub.get("reimbursement_requested_cents"))
        subtotal = require_cents(f"history.{ctx.period}.subtotal_cents",
                                 current.get("subtotal_cents"))
        if requested != subtotal:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(sub, "reimbursement_requested_cents"),
                               f"the submission requests {fmt(requested)} but the claims "
                               f"filed for {ctx.period} total {fmt(subtotal)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"the request matches the {ctx.period} claims"))
    return out


@check("clm_claim_inside_its_period")
def clm_claim_inside_its_period(ctx: Context) -> list[Finding]:
    """Every claim must be dated inside the reporting period it is filed under.

    A defect repaired in one quarter and filed in the next is not fraud, but it
    does mean two quarters both look wrong to anyone reconciling them later.
    """
    rule = "clm_claim_inside_its_period"
    _sev(rule, Status.FAIL)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    if history is None:
        return []
    out: list[Finding] = []
    checked = 0
    for period, line in _all_claims(ctx):
        label = period.get("period")
        start = _parse_date(period.get("from_date"))
        end = _parse_date(period.get("to_date"))
        when = _parse_date(line.get("claim_date"))
        if start is None or end is None:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(history, f"periods/{label}/from_date"),
                               f"reporting period {label} has no readable date range, so "
                               f"no claim inside it can be placed"))
            continue
        if when is None:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(history, f"periods/{label}/claims/"
                                                f"{line.get('claim_no')}/claim_date"),
                               f"claim {line.get('claim_no')} in {label} has no readable date"))
            continue
        checked += 1
        if not (start <= when <= end):
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(history, f"periods/{label}/claims/"
                                                f"{line.get('claim_no')}/claim_date"),
                               f"claim {line.get('claim_no')} is dated {when.isoformat()}, "
                               f"outside its {label} window "
                               f"({start.isoformat()}..{end.isoformat()})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} claims fall inside their reporting period"))
    return out


@check("clm_claim_inside_policy_period")
def clm_claim_inside_policy_period(ctx: Context) -> list[Finding]:
    """Every claim must fall inside the policy period.

    Distinct from the reporting-period check: a claim can sit correctly inside
    its quarter and still be outside the policy entirely, which is the case
    nobody catches because the quarter foots.
    """
    rule = "clm_claim_inside_policy_period"
    _sev(rule, Status.FAIL)
    pol = ctx.one(DOC_POLICY)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    if pol is None or history is None:
        return []
    start = _parse_date(pol.get("policy_start"))
    end = _parse_date(pol.get("policy_end"))
    if start is None or end is None:
        return [Finding(rule, Status.FAIL, ctx.loc(pol, "policy_start"),
                        "the policy period is unreadable, so no claim can be shown to fall "
                        "inside it")]
    out: list[Finding] = []
    checked = 0
    for period, line in _all_claims(ctx):
        when = _parse_date(line.get("claim_date"))
        if when is None:
            continue
        checked += 1
        if not (start <= when <= end):
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(history, f"periods/{period.get('period')}/claims/"
                                                f"{line.get('claim_no')}/claim_date"),
                               f"claim {line.get('claim_no')} is dated {when.isoformat()}, "
                               f"outside the policy period "
                               f"({start.isoformat()}..{end.isoformat()}); it is not covered"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} claims fall inside the policy period"))
    return out


@check("clm_no_duplicate_invoice")
def clm_no_duplicate_invoice(ctx: Context) -> list[Finding]:
    """The same vendor invoice must not be claimed twice.

    Across quarters as well as within one. A repair claimed again three periods
    later is invisible to anyone reviewing either quarter alone.
    """
    rule = "clm_no_duplicate_invoice"
    _sev(rule, Status.FAIL)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    if history is None:
        return []
    seen: dict[tuple[str, str], list[str]] = {}
    for period, line in _all_claims(ctx):
        key = (str(line.get("vendor")), str(line.get("invoice_number")))
        seen.setdefault(key, []).append(str(period.get("period")))
    out = [
        Finding(rule, Status.FAIL, ctx.loc(history, f"claims/{vendor}/{invoice}"),
                f"invoice {invoice} from {vendor} is claimed in "
                f"{len(periods)} periods ({', '.join(periods)}); the same repair is being "
                f"reimbursed more than once")
        for (vendor, invoice), periods in sorted(seen.items()) if len(periods) > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(seen)} vendor invoices are claimed once"))
    return out


# --------------------------------------------------------------------------- #
# 4. cost_* -- is there a real cost behind the claim
# --------------------------------------------------------------------------- #
@check("cost_claim_traces_to_ledger")
def cost_claim_traces_to_ledger(ctx: Context) -> list[Finding]:
    """Every claim must trace to a warranty cost transaction of the same amount.

    A claim with no cost behind it is a request for money the builder never
    spent. Matching on vendor and invoice rather than on amount alone, because
    two repairs of the same value are common and are not each other.
    """
    rule = "cost_claim_traces_to_ledger"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_COST_LEDGER)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    if ledger is None or history is None:
        return []
    out: list[Finding] = []
    by_key: dict[tuple[str, str], int] = {}
    for txn in _rows(ledger, "transactions"):
        key = (str(txn.get("vendor")), str(txn.get("invoice_number")))
        with amount_guard(rule, out):
            by_key[key] = by_key.get(key, 0) + require_cents(
                f"ledger.transactions[{txn.get('invoice_number')}].amount_cents",
                txn.get("amount_cents"))
    checked = 0
    for period, line in _all_claims(ctx):
        key = (str(line.get("vendor")), str(line.get("invoice_number")))
        with amount_guard(rule, out):
            claimed = require_cents(
                f"history.claims[{line.get('claim_no')}].amount_cents",
                line.get("amount_cents"))
            checked += 1
            if key not in by_key:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(history, f"periods/{period.get('period')}/claims/"
                                                    f"{line.get('claim_no')}"),
                                   f"claim {line.get('claim_no')} for {fmt(claimed)} cites "
                                   f"invoice {key[1]} from {key[0]}, which has no matching "
                                   f"warranty cost in the job-cost ledger"))
            elif by_key[key] != claimed:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(history, f"periods/{period.get('period')}/claims/"
                                                    f"{line.get('claim_no')}/amount_cents"),
                                   f"claim {line.get('claim_no')} requests {fmt(claimed)} "
                                   f"but the ledger carries {fmt(by_key[key])} for invoice "
                                   f"{key[1]}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} claims trace to a warranty cost"))
    return out


@check("cost_uses_warranty_cost_code")
def cost_uses_warranty_cost_code(ctx: Context) -> list[Finding]:
    """Warranty costs must sit at a warranty cost code.

    A cost outside those codes is not a warranty cost whatever its description
    says, and claiming it puts an ordinary construction cost into the policy.
    """
    rule = "cost_uses_warranty_cost_code"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_COST_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for txn in _rows(ledger, "transactions"):
        code = str(txn.get("cost_code"))
        checked += 1
        if code not in WARRANTY_COST_CODES:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(ledger, f"transactions/"
                                               f"{txn.get('invoice_number')}/cost_code"),
                               f"transaction on invoice {txn.get('invoice_number')} is "
                               f"coded {code}, which is not a warranty cost code "
                               f"({', '.join(WARRANTY_COST_CODES)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} ledger transactions use a warranty cost code"))
    return out


@check("cost_accounting_date_inside_period")
def cost_accounting_date_inside_period(ctx: Context) -> list[Finding]:
    """Ledger transactions must be accounted for inside the reporting window."""
    rule = "cost_accounting_date_inside_period"
    _sev(rule, Status.FLAG)
    ledger = ctx.one(DOC_COST_LEDGER)
    if ledger is None:
        return []
    start = _parse_date(ledger.get("from_date"))
    end = _parse_date(ledger.get("to_date"))
    if start is None or end is None:
        return [Finding(rule, Status.FLAG, ctx.loc(ledger, "from_date"),
                        "the cost ledger declares no readable reporting window")]
    out: list[Finding] = []
    checked = 0
    for txn in _rows(ledger, "transactions"):
        when = _parse_date(txn.get("accounting_date"))
        if when is None:
            continue
        checked += 1
        if not (start <= when <= end):
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(ledger, f"transactions/"
                                               f"{txn.get('invoice_number')}/accounting_date"),
                               f"transaction on invoice {txn.get('invoice_number')} is "
                               f"accounted {when.isoformat()}, outside the ledger's "
                               f"{start.isoformat()}..{end.isoformat()} window"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} ledger transactions sit inside the window"))
    return out


# --------------------------------------------------------------------------- #
# 5. unit_* -- coverage begins at close of escrow
# --------------------------------------------------------------------------- #
@check("unit_claim_unit_has_closed")
def unit_claim_unit_has_closed(ctx: Context) -> list[Finding]:
    """A claim must relate to a unit that has closed.

    Warranty coverage begins at close of escrow. Before that the builder still
    owns the home and a defect is ordinary construction cost, not a warranty
    claim -- which makes this the cheapest way to move cost into the policy.
    """
    rule = "unit_claim_unit_has_closed"
    _sev(rule, Status.FAIL)
    units = ctx.one(DOC_CLOSED_UNITS)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    if units is None or history is None:
        return []
    closed = {str(u.get("unit")) for u in _rows(units, "units")
              if _parse_date(u.get("close_date")) is not None}
    out: list[Finding] = []
    checked = 0
    for period, line in _all_claims(ctx):
        unit = str(line.get("unit"))
        checked += 1
        if unit not in closed:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(history, f"periods/{period.get('period')}/claims/"
                                                f"{line.get('claim_no')}/unit"),
                               f"claim {line.get('claim_no')} is for unit {unit}, which has "
                               f"no recorded close of escrow; warranty coverage does not "
                               f"begin until the home is sold"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} claims relate to a closed unit"))
    return out


@check("unit_claim_after_close")
def unit_claim_after_close(ctx: Context) -> list[Finding]:
    """A claim must be dated on or after its unit's close of escrow."""
    rule = "unit_claim_after_close"
    _sev(rule, Status.FAIL)
    units = ctx.one(DOC_CLOSED_UNITS)
    history = ctx.one(DOC_CLAIMS_HISTORY)
    if units is None or history is None:
        return []
    coe = {str(u.get("unit")): _parse_date(u.get("close_date"))
           for u in _rows(units, "units")}
    out: list[Finding] = []
    checked = 0
    for period, line in _all_claims(ctx):
        unit = str(line.get("unit"))
        when = _parse_date(line.get("claim_date"))
        closed_on = coe.get(unit)
        if when is None or closed_on is None:
            continue
        checked += 1
        if when < closed_on:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(history, f"periods/{period.get('period')}/claims/"
                                                f"{line.get('claim_no')}/claim_date"),
                               f"claim {line.get('claim_no')} is dated {when.isoformat()}, "
                               f"before unit {unit} closed on {closed_on.isoformat()}; the "
                               f"defect predates the coverage"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} claims postdate their unit's close"))
    return out


# --------------------------------------------------------------------------- #
# 6. rem_* -- where the money goes
# --------------------------------------------------------------------------- #
@check("rem_insured_entity_matches")
def rem_insured_entity_matches(ctx: Context) -> list[Finding]:
    """Reimbursement must be remitted to the insured entity.

    The policy names one insured. Money going anywhere else is a different
    problem from an accounting error, which is why the entity is compared rather
    than assumed.
    """
    rule = "rem_insured_entity_matches"
    _sev(rule, Status.FAIL)
    pol = ctx.one(DOC_POLICY)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if pol is None or sub is None:
        return []
    insured = pol.get("insured_entity")
    remit_to = sub.get("remit_to_entity")
    if not isinstance(insured, str) or not insured.strip():
        return [Finding(rule, Status.FAIL, ctx.loc(pol, "insured_entity"),
                        "the policy names no insured entity")]
    if remit_to != insured:
        return [Finding(rule, Status.FAIL, ctx.loc(sub, "remit_to_entity"),
                        f"reimbursement is directed to {remit_to!r} but the policy insures "
                        f"{insured!r}")]
    return [Finding(rule, Status.PASS, "-",
                    "reimbursement is directed to the insured entity")]


@check("rem_bank_details_present")
def rem_bank_details_present(ctx: Context) -> list[Finding]:
    """Wire instructions must be complete enough to pay against."""
    rule = "rem_bank_details_present"
    _sev(rule, Status.FLAG)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if sub is None:
        return []
    missing = [
        field for field in ("remit_bank_name", "remit_account_reference",
                            "remit_routing_reference")
        if not (isinstance(sub.get(field), str) and str(sub.get(field)).strip())
    ]
    if missing:
        return [Finding(rule, Status.FLAG, ctx.loc(sub, "remit_bank_name"),
                        f"wire instructions are incomplete: {', '.join(missing)} "
                        f"{'is' if len(missing) == 1 else 'are'} missing, so the claim "
                        f"cannot be paid as submitted")]
    return [Finding(rule, Status.PASS, "-", "wire instructions are complete")]


@check("rem_submission_approved")
def rem_submission_approved(ctx: Context) -> list[Finding]:
    """The submission must carry an approval and a date."""
    rule = "rem_submission_approved"
    _sev(rule, Status.FAIL)
    sub = ctx.one(DOC_CLAIM_SUBMISSION)
    if sub is None:
        return []
    approver = sub.get("approved_by")
    if not (isinstance(approver, str) and approver.strip()):
        return [Finding(rule, Status.FAIL, ctx.loc(sub, "approved_by"),
                        "the claim submission carries no approver; a request for money "
                        "leaves the business unapproved")]
    if _parse_date(sub.get("approval_date")) is None:
        return [Finding(rule, Status.FAIL, ctx.loc(sub, "approval_date"),
                        f"the approval by {approver!r} carries no readable date")]
    return [Finding(rule, Status.PASS, "-", "the submission is approved and dated")]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one claim file."""
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
    """Analyze every ``.json`` claim file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of claim-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
