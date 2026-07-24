"""
Capital spending request gate control engine (READ-ONLY).
=========================================================

Loads each request package (a ``.json`` file produced by
:mod:`spending_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the request package conforms to the written
underwriting standards**, not whether the investment is worth making. The
investment merits are genuine business judgment and no control here opines on
them. Every control is a hard equality, threshold, date gate, membership test
or re-derivation.

The shape of the problem
------------------------
A developer commits capital to a project only through an ordered sequence of
Investment Committee phase gates, each opened by an approved Spending Request
that must conform to the underwriting standards: dollar triggers that demand
approval before the first spend, contingency floors, a standard growth
assumption, prescribed fee formulas, a phase-indexed estimate basis and
deliverable matrix, and a comparison basis that switches once feasibility is
waived.

Three failures hide inside that, and none of them look wrong in a bound
package: the pursuit spend that crossed its trigger before the Initial
Commitment Request was approved; the contingency a hair under the floor and the
fee a little off its formula, neither ever re-derived; and the gate summary
that calls every phase cleared on a determination nobody rebuilt from the
approvals and the checklist underneath it.

The registry is organised around that:

1. ``set_`` -- is the request package complete?
2. ``trg_`` -- did the dollar triggers fire only after the IC approval?
3. ``seq_`` -- were the five phase gates entered in order, and does the stated
   gate summary recompute?
4. ``del_`` -- is the phase-indexed deliverable matrix satisfied, and is the
   estimate basis the one the phase prescribes?
5. ``cty_`` -- do the contingencies meet their regional floors, exactly?
6. ``gro_`` -- is the growth assumption the standard default, or documented?
7. ``fee_`` -- do the stated fees and the total re-derive from their formulas?
8. ``cal_`` -- is the comparison basis right for the waiver status, and is the
   template the current refresh?
9. ``evt_`` -- did every interim-trigger event produce an interim request?
10. ``bid_`` -- is the construction-start bid coverage at its threshold?

Design notes
------------
- **Strictly read-only.** Request packages are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every threshold is compared with exact
  ``>=`` or ``==``; floors are tested cross-multiplied in integers.
- **One standards kernel.** Controls and the generator share
  :mod:`spending_engine.standards`, so a determination cannot disagree with the
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

from .model import (
    DELIVERABLE_STATUSES,
    DELIVERABLE_TYPES,
    DELIVERABLES_BY_PHASE,
    DOC_APPROVAL_LOG,
    DOC_BID_SCHEDULE,
    DOC_COST_BUDGET,
    DOC_DELIVERABLE_CHECKLIST,
    DOC_EVENT_LOG,
    DOC_GATE_SUMMARY,
    DOC_PLAN_COMPARISON,
    DOC_PROJECT_PROFILE,
    DOC_SPEND_LEDGER,
    DOC_TYPES,
    ESTIMATE_BASIS_BY_PHASE,
    EVENT_TYPES,
    GC_MODELS,
    GC_OWNER,
    GC_THIRD_PARTY,
    PHASE_CONSTRUCTION,
    PHASE_INITIAL_COMMITMENT,
    PHASES,
    REGION_MARRAN,
    REGION_VANTERRE,
    REGIONS,
    REQUEST_INTERIM,
    REQUEST_PHASE,
    REQUEST_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, apply_rate, fmt, fmt_bps, require_cents
from .standards import (
    BASES,
    BASIS_TEMPLATE,
    BID_COVERAGE_FLOOR_BPS,
    CM_FEE_RATE_BPS,
    DEV_FEE_RATE_BPS,
    HARD_FLOOR_BPS,
    NONREFUNDABLE_TRIGGER_CENTS,
    PURSUIT_TRIGGER_CENTS,
    REFUNDABLE_TRIGGER_CENTS,
    SITE_FLOOR_BPS,
    SOFT_FLOOR_BPS,
    STANDARD_GROWTH_BPS,
    VERTICAL_FLOOR_BPS,
    derive_variance,
    first_breach,
    gate_cleared,
    growth_is_standard,
    latest_template_refresh,
    meets_floor,
    required_basis,
    trigger_satisfied,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~spending_engine.money.AmountInvalidError` as a finding."""
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
# Request-package helpers
# --------------------------------------------------------------------------- #
def _profile(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_PROJECT_PROFILE)


def _budget(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_COST_BUDGET)


def _current_phase(ctx: Context) -> str | None:
    """The project's current phase, or ``None`` when unknown.

    An unknown phase is owned by ``seq_phase_known``; every phase-indexed
    control skips rather than double-reporting it.
    """
    profile = _profile(ctx)
    if profile is None:
        return None
    phase = _text(profile, "current_phase")
    return phase if phase in PHASES else None


def _region(ctx: Context) -> str | None:
    profile = _profile(ctx)
    if profile is None:
        return None
    return _text(profile, "region")


def _approvals(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_APPROVAL_LOG), "approvals")


def _phase_approval_dates(ctx: Context) -> dict[str, date]:
    """Earliest approval date per phase, from ``phase``-type approvals only."""
    out: dict[str, date] = {}
    for row in _approvals(ctx):
        if _text(row, "request_type") != REQUEST_PHASE:
            continue
        phase = _text(row, "phase")
        approved = _parse_date(row.get("approval_date"))
        if phase not in PHASES or approved is None:
            continue
        if phase not in out or approved < out[phase]:
            out[phase] = approved
    return out


def _interim_approval_ids(ctx: Context) -> set[str]:
    return {
        rid
        for row in _approvals(ctx)
        if _text(row, "request_type") == REQUEST_INTERIM
        and (rid := _text(row, "approval_id")) is not None
    }


def _spend_entries(ctx: Context, category: str) -> list[tuple[date, int]]:
    """``(date, amount)`` pairs of one spend category, amounts validated.

    Raises :class:`AmountInvalidError` if an amount is not integer cents; the
    calling control's guard contains that. Rows with unreadable dates are
    skipped -- they cannot be placed against the approval date at all.
    """
    out: list[tuple[date, int]] = []
    for row in _rows(ctx.one(DOC_SPEND_LEDGER), "entries"):
        if _text(row, "category") != category:
            continue
        spent = _parse_date(row.get("spend_date"))
        if spent is None:
            continue
        amount = require_cents(
            f"spend_ledger[{_text(row, 'entry_id') or '?'}].amount_cents",
            row.get("amount_cents"),
        )
        out.append((spent, amount))
    return out


def _checklist_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DELIVERABLE_CHECKLIST), "items")


def _complete_deliverables(ctx: Context) -> set[str]:
    """Every known deliverable the checklist marks complete."""
    return {
        d
        for row in _checklist_rows(ctx)
        if (d := _text(row, "deliverable")) in DELIVERABLE_TYPES
        and _text(row, "status") == "complete"
    }


def recompute_gate_rows(ctx: Context) -> list[dict[str, Any]]:
    """The gate summary re-derived from the approvals and the checklist.

    One row per phase, in phase order: the gate cleared when the phase's
    Spending Request is approved and every deliverable required by the phases
    before it is complete. Shared with the generator through
    :mod:`spending_engine.standards`, so the stated summary can be tied to it.
    Reads no amounts, so it never raises on a malformed figure.
    """
    approved = _phase_approval_dates(ctx)
    complete = _complete_deliverables(ctx)
    rows: list[dict[str, Any]] = []
    for i, phase in enumerate(PHASES):
        prior_ok = all(
            d in complete for ph in PHASES[:i] for d in DELIVERABLES_BY_PHASE[ph]
        )
        rows.append(
            {"phase": phase, "gate_cleared": gate_cleared(phase in approved, prior_ok)}
        )
    return rows


def _trigger_check(
    ctx: Context,
    rule: str,
    category: str,
    threshold_cents: int,
    trigger_label: str,
) -> list[Finding]:
    """Shared body of the three dollar-trigger controls."""
    ledger = ctx.one(DOC_SPEND_LEDGER)
    log = ctx.one(DOC_APPROVAL_LOG)
    if ledger is None or log is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        entries = _spend_entries(ctx, category)
        breach = first_breach(entries, threshold_cents)
        ic = _phase_approval_dates(ctx).get(PHASE_INITIAL_COMMITMENT)
        if trigger_satisfied(breach, ic):
            if breach is None:
                out.append(
                    Finding(
                        rule,
                        Status.PASS,
                        "-",
                        f"the {trigger_label} trigger never fired across "
                        f"{len(entries)} ledger entr(ies)",
                    )
                )
            else:
                assert ic is not None
                out.append(
                    Finding(
                        rule,
                        Status.PASS,
                        "-",
                        f"the {trigger_label} trigger fired {breach.isoformat()}, "
                        f"after the Initial Commitment approval of {ic.isoformat()}",
                    )
                )
        else:
            assert breach is not None
            approved_text = (
                f"the Initial Commitment Request was not approved until "
                f"{ic.isoformat()}"
                if ic is not None
                else "no Initial Commitment Request approval is on record"
            )
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"entries/{category}"),
                    f"{trigger_label} crossed its trigger on {breach.isoformat()} "
                    f"but {approved_text}; capital was committed before the gate",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the request package depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the request package "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} request-package artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every calendar test "
                f"is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# trg_ -- the hard dollar triggers
# --------------------------------------------------------------------------- #
@check("trg_ic_before_pursuit_spend")
def check_trg_ic_before_pursuit_spend(ctx: Context) -> list[Finding]:
    """Cumulative pursuit costs crossed their trigger only after IC approval.

    The trigger is cumulative: no single invoice has to be large for the
    project to be past the threshold, which is exactly why the running total is
    re-derived rather than any one entry inspected.
    """
    rule = "trg_ic_before_pursuit_spend"
    _sev(rule, Status.FAIL)
    return _trigger_check(
        ctx,
        rule,
        "pursuit_cost",
        PURSUIT_TRIGGER_CENTS,
        f"cumulative pursuit-cost spend of {fmt(PURSUIT_TRIGGER_CENTS)}",
    )


@check("trg_ic_before_nonrefundable_deposit")
def check_trg_ic_before_nonrefundable_deposit(ctx: Context) -> list[Finding]:
    """Any non-refundable deposit was preceded by an IC approval.

    Refundable money can be walked back; a non-refundable deposit is committed
    capital from its first cent, so its threshold is one cent.
    """
    rule = "trg_ic_before_nonrefundable_deposit"
    _sev(rule, Status.FAIL)
    return _trigger_check(
        ctx,
        rule,
        "nonrefundable_deposit",
        NONREFUNDABLE_TRIGGER_CENTS,
        "the first non-refundable deposit",
    )


@check("trg_ic_before_refundable_deposits")
def check_trg_ic_before_refundable_deposits(ctx: Context) -> list[Finding]:
    """Cumulative refundable deposits crossed their trigger only after IC approval."""
    rule = "trg_ic_before_refundable_deposits"
    _sev(rule, Status.FAIL)
    return _trigger_check(
        ctx,
        rule,
        "refundable_deposit",
        REFUNDABLE_TRIGGER_CENTS,
        f"cumulative refundable deposits of {fmt(REFUNDABLE_TRIGGER_CENTS)}",
    )


# --------------------------------------------------------------------------- #
# seq_ -- the ordered phase gates
# --------------------------------------------------------------------------- #
@check("seq_phase_known")
def check_seq_phase_known(ctx: Context) -> list[Finding]:
    """The current phase and every approval row are well-formed.

    The phase is the key into the deliverable matrix, the estimate-basis lookup
    and the contingency floors; an unknown one has no row anywhere, so nothing
    downstream could say what standard the project was held to.
    """
    rule = "seq_phase_known"
    _sev(rule, Status.FAIL)
    profile = _profile(ctx)
    log = ctx.one(DOC_APPROVAL_LOG)
    if profile is None or log is None:
        return []
    out: list[Finding] = []
    stated = _text(profile, "current_phase")
    if stated not in PHASES:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(profile, "current_phase"),
                f"the project states phase {stated!r}, which is not one of the "
                f"ordered gates {PHASES}; no phase-indexed standard can be looked up",
            )
        )
    for row in _approvals(ctx):
        rid = _text(row, "approval_id") or "?"
        rtype = _text(row, "request_type")
        if rtype not in REQUEST_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"approvals/{rid}/request_type"),
                    f"approval {rid} is typed {rtype!r}, which is not one of "
                    f"{REQUEST_TYPES}",
                )
            )
            continue
        if rtype == REQUEST_PHASE and _text(row, "phase") not in PHASES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"approvals/{rid}/phase"),
                    f"approval {rid} names phase {_text(row, 'phase')!r}, which is "
                    f"not one of the ordered gates {PHASES}",
                )
            )
        if _parse_date(row.get("approval_date")) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"approvals/{rid}/approval_date"),
                    f"approval {rid} carries approval_date "
                    f"{row.get('approval_date')!r}, which is not a readable date; it "
                    f"cannot be placed against any spend or event",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the current phase and all {len(_approvals(ctx))} approvals are "
                f"well-formed",
            )
        )
    return out


@check("seq_approvals_in_order")
def check_seq_approvals_in_order(ctx: Context) -> list[Finding]:
    """Phase approvals carry dates in phase order.

    A later gate approved before an earlier one means the sequence exists on
    paper only -- the ordering of the five gates is the control, and the dates
    are the evidence it was followed.
    """
    rule = "seq_approvals_in_order"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_APPROVAL_LOG)
    if log is None:
        return []
    dates = _phase_approval_dates(ctx)
    out: list[Finding] = []
    checked = 0
    for earlier, later in zip(PHASES, PHASES[1:]):
        if earlier not in dates or later not in dates:
            continue
        checked += 1
        if dates[earlier] > dates[later]:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"approvals/{earlier}/approval_date"),
                    f"the {earlier} gate was approved {dates[earlier].isoformat()}, "
                    f"after the {later} gate of {dates[later].isoformat()}; the "
                    f"gates were not entered in sequence",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} adjacent phase-approval pairs are in date order",
            )
        )
    return out


@check("seq_no_phase_skipped")
def check_seq_no_phase_skipped(ctx: Context) -> list[Finding]:
    """Every phase before the current one has an approved Spending Request.

    A gap in the approval chain is a gate the project passed without opening:
    the phases are ordered exactly so that none can be skipped.
    """
    rule = "seq_no_phase_skipped"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_APPROVAL_LOG)
    current = _current_phase(ctx)
    if log is None or current is None:
        return []
    dates = _phase_approval_dates(ctx)
    prior = PHASES[: PHASES.index(current)]
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(log, f"approvals/{phase}"),
            f"the project is in {current} but the {phase} gate has no approved "
            f"Spending Request on record; a prior gate was skipped",
        )
        for phase in prior
        if phase not in dates
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(prior)} phases preceding {current} carry an approval",
            )
        )
    return out


@check("seq_current_phase_approved")
def check_seq_current_phase_approved(ctx: Context) -> list[Finding]:
    """The current phase itself was opened by an approved Spending Request."""
    rule = "seq_current_phase_approved"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_APPROVAL_LOG)
    current = _current_phase(ctx)
    if log is None or current is None:
        return []
    if current not in _phase_approval_dates(ctx):
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(log, f"approvals/{current}"),
                f"the project states it is in {current} but no approved Spending "
                f"Request for that phase is on record; the phase was entered "
                f"without its gate",
            )
        ]
    return [
        Finding(
            rule,
            Status.PASS,
            "-",
            f"the current phase {current} carries an approved Spending Request",
        )
    ]


@check("seq_gate_summary_recomputes")
def check_seq_gate_summary_recomputes(ctx: Context) -> list[Finding]:
    """Each phase's stated gate-cleared flag recomputes from the evidence.

    This is the control the engine exists for. The gate summary is a
    determination, and a determination that is not recomputed from the
    approvals and the deliverable checklist is an assertion. The engine rebuilds
    every flag through the shared standards kernel and compares.
    """
    rule = "seq_gate_summary_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_GATE_SUMMARY)
    log = ctx.one(DOC_APPROVAL_LOG)
    checklist = ctx.one(DOC_DELIVERABLE_CHECKLIST)
    if summary is None or log is None or checklist is None:
        return []
    stated = {
        phase: row.get("gate_cleared")
        for row in _rows(summary, "phases")
        if (phase := _text(row, "phase")) in PHASES
    }
    out: list[Finding] = []
    for row in recompute_gate_rows(ctx):
        phase = row["phase"]
        recomputed = row["gate_cleared"]
        if phase not in stated:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, f"phases/{phase}"),
                    f"the gate summary carries no row for {phase}; a phase with no "
                    f"stated determination cannot be tied to the evidence",
                )
            )
        elif stated[phase] != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, f"phases/{phase}/gate_cleared"),
                    f"the summary states the {phase} gate cleared={stated[phase]}; "
                    f"recomputing from the approvals and the deliverable checklist "
                    f"gives cleared={recomputed}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(PHASES)} stated gate determinations recompute from the "
                f"evidence",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# del_ -- the phase-indexed deliverable matrix and estimate basis
# --------------------------------------------------------------------------- #
@check("del_items_known")
def check_del_items_known(ctx: Context) -> list[Finding]:
    """Every checklist row names a known deliverable in a known state.

    An unknown deliverable belongs to no phase, so it can neither block a gate
    nor satisfy one; it is paperwork that looks like evidence of something.
    """
    rule = "del_items_known"
    _sev(rule, Status.FAIL)
    checklist = ctx.one(DOC_DELIVERABLE_CHECKLIST)
    if checklist is None:
        return []
    out: list[Finding] = []
    for row in _checklist_rows(ctx):
        name = _text(row, "deliverable")
        status = _text(row, "status")
        if name not in DELIVERABLE_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(checklist, f"items/{name}"),
                    f"the checklist carries {name!r}, which is not a deliverable of "
                    f"any phase; it can neither block a gate nor satisfy one",
                )
            )
        elif status not in DELIVERABLE_STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(checklist, f"items/{name}/status"),
                    f"deliverable {name} is in state {status!r}, which is not one of "
                    f"{DELIVERABLE_STATUSES}; its completeness cannot be determined",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_checklist_rows(ctx))} checklist rows are well-formed",
            )
        )
    return out


@check("del_unique_rows")
def check_del_unique_rows(ctx: Context) -> list[Finding]:
    """No deliverable appears on the checklist twice.

    Two rows for one deliverable can disagree about its state, and a gate test
    that reads whichever row it meets first is not a control.
    """
    rule = "del_unique_rows"
    _sev(rule, Status.FAIL)
    checklist = ctx.one(DOC_DELIVERABLE_CHECKLIST)
    if checklist is None:
        return []
    seen: dict[str, int] = {}
    for row in _checklist_rows(ctx):
        name = _text(row, "deliverable")
        if name:
            seen[name] = seen.get(name, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(checklist, f"items/{name}"),
            f"deliverable {name} appears {count} times; two rows can disagree "
            f"about its state and the gate test becomes ambiguous",
        )
        for name, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(seen)} checklist deliverables are unique"
            )
        )
    return out


@check("del_prior_phase_complete")
def check_del_prior_phase_complete(ctx: Context) -> list[Finding]:
    """Every deliverable required by the phases already passed is complete.

    The current phase was entered on the strength of the prior phases'
    checklists; a prior-phase deliverable still outstanding means a gate was
    cleared on an incomplete record.
    """
    rule = "del_prior_phase_complete"
    _sev(rule, Status.FAIL)
    checklist = ctx.one(DOC_DELIVERABLE_CHECKLIST)
    current = _current_phase(ctx)
    if checklist is None or current is None:
        return []
    complete = _complete_deliverables(ctx)
    out: list[Finding] = []
    checked = 0
    for phase in PHASES[: PHASES.index(current)]:
        for deliverable in DELIVERABLES_BY_PHASE[phase]:
            checked += 1
            if deliverable not in complete:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(checklist, f"items/{deliverable}"),
                        f"{deliverable} is required by the {phase} phase, which the "
                        f"project has already passed, but is not marked complete",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} deliverables of the phases before {current} are "
                f"complete",
            )
        )
    return out


@check("del_current_phase_outstanding")
def check_del_current_phase_outstanding(ctx: Context) -> list[Finding]:
    """A current-phase deliverable still outstanding is flagged.

    Deliberately a FLAG, not a failure: the current phase's deliverables are
    due by its exit gate, not its entry, so an outstanding one is work to chase
    rather than a gate already breached.
    """
    rule = "del_current_phase_outstanding"
    _sev(rule, Status.FLAG)
    checklist = ctx.one(DOC_DELIVERABLE_CHECKLIST)
    current = _current_phase(ctx)
    if checklist is None or current is None:
        return []
    complete = _complete_deliverables(ctx)
    out = [
        Finding(
            rule,
            Status.FLAG,
            ctx.loc(checklist, f"items/{deliverable}"),
            f"{deliverable} is required by the current phase ({current}) and is "
            f"not yet complete; it must be in hand before the next gate",
        )
        for deliverable in DELIVERABLES_BY_PHASE[current]
        if deliverable not in complete
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DELIVERABLES_BY_PHASE[current])} current-phase "
                f"deliverables are complete",
            )
        )
    return out


@check("del_estimate_basis_matches")
def check_del_estimate_basis_matches(ctx: Context) -> list[Finding]:
    """The budget's estimate basis is the one the current phase prescribes.

    The basis must progress top-down to a bindable GMP as the gates advance; a
    construction-phase budget still standing on a divisional estimate is a
    commitment made on numbers the standards no longer accept.
    """
    rule = "del_estimate_basis_matches"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    current = _current_phase(ctx)
    if budget is None or current is None:
        return []
    expected = ESTIMATE_BASIS_BY_PHASE[current]
    stated = _text(budget, "estimate_basis")
    if stated != expected:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(budget, "estimate_basis"),
                f"the budget stands on estimate basis {stated!r}; the {current} "
                f"phase requires {expected!r}",
            )
        ]
    return [
        Finding(
            rule,
            Status.PASS,
            "-",
            f"the estimate basis {expected!r} matches the {current} phase",
        )
    ]


# --------------------------------------------------------------------------- #
# cty_ -- the contingency floors
# --------------------------------------------------------------------------- #
@check("cty_hard_floor")
def check_cty_hard_floor(ctx: Context) -> list[Finding]:
    """The hard-cost contingency meets its regional floor, exactly.

    Compared cross-multiplied in integer cents: a contingency met to the cent
    passes and a cent under fails. In Marran the floor splits at construction
    start -- 10% on site work, 5% on vertical -- so each leg is tested on its
    own base.
    """
    rule = "cty_hard_floor"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    profile = _profile(ctx)
    if budget is None or profile is None:
        return []
    region = _region(ctx)
    if region not in REGIONS:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(profile, "region"),
                f"the project is in region {region!r}, which is not one of "
                f"{REGIONS}; no contingency floor can be looked up",
            )
        ]
    current = _current_phase(ctx)
    if current is None:
        return []  # seq_phase_known owns this
    out: list[Finding] = []
    with amount_guard(rule, out):
        if region == REGION_MARRAN and current == PHASE_CONSTRUCTION:
            legs = (
                ("site", "site_hard_cost_cents", "site_contingency_cents", SITE_FLOOR_BPS),
                (
                    "vertical",
                    "vertical_hard_cost_cents",
                    "vertical_contingency_cents",
                    VERTICAL_FLOOR_BPS,
                ),
            )
            for label, base_key, cty_key, floor in legs:
                base = require_cents(f"cost_budget.{base_key}", budget.get(base_key))
                cty = require_cents(f"cost_budget.{cty_key}", budget.get(cty_key))
                if not meets_floor(cty, base, floor):
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(budget, cty_key),
                            f"the {label} contingency of {fmt(cty)} is under the "
                            f"{fmt_bps(floor)} floor on {label} hard cost of "
                            f"{fmt(base)}; the construction-start floor is unmet",
                        )
                    )
            if not out:
                out.append(
                    Finding(
                        rule,
                        Status.PASS,
                        "-",
                        f"both construction-start contingency legs meet the "
                        f"{fmt_bps(SITE_FLOOR_BPS)} site / "
                        f"{fmt_bps(VERTICAL_FLOOR_BPS)} vertical floors",
                    )
                )
        else:
            floor = HARD_FLOOR_BPS[region]
            base = require_cents("cost_budget.hard_cost_cents", budget.get("hard_cost_cents"))
            cty = require_cents(
                "cost_budget.hard_contingency_cents", budget.get("hard_contingency_cents")
            )
            if not meets_floor(cty, base, floor):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(budget, "hard_contingency_cents"),
                        f"the hard-cost contingency of {fmt(cty)} is under the "
                        f"{fmt_bps(floor)} {region} floor on hard cost of {fmt(base)}",
                    )
                )
            else:
                out.append(
                    Finding(
                        rule,
                        Status.PASS,
                        "-",
                        f"the hard-cost contingency meets the {fmt_bps(floor)} "
                        f"{region} floor",
                    )
                )
    return out


@check("cty_soft_floor")
def check_cty_soft_floor(ctx: Context) -> list[Finding]:
    """The soft-cost contingency meets its regional floor, or is documented.

    The standards allow the floor to be adjusted only with documented
    justification, so a shortfall with the justification flag set passes as a
    documented adjustment; a shortfall without it is a plain breach.
    """
    rule = "cty_soft_floor"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    profile = _profile(ctx)
    if budget is None or profile is None:
        return []
    region = _region(ctx)
    if region not in REGIONS:
        return []  # cty_hard_floor owns the unknown region
    floor = SOFT_FLOOR_BPS[region]
    out: list[Finding] = []
    with amount_guard(rule, out):
        base = require_cents("cost_budget.soft_cost_cents", budget.get("soft_cost_cents"))
        cty = require_cents(
            "cost_budget.soft_contingency_cents", budget.get("soft_contingency_cents")
        )
        if meets_floor(cty, base, floor):
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the soft-cost contingency meets the {fmt_bps(floor)} {region} floor",
                )
            )
        elif budget.get("soft_floor_justification_documented") is True:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the soft-cost contingency sits under the {fmt_bps(floor)} floor "
                    f"with a documented justification, which the standards permit",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(budget, "soft_contingency_cents"),
                    f"the soft-cost contingency of {fmt(cty)} is under the "
                    f"{fmt_bps(floor)} {region} floor on soft cost of {fmt(base)} "
                    f"and no justification is documented",
                )
            )
    return out


@check("cty_split_foots")
def check_cty_split_foots(ctx: Context) -> list[Finding]:
    """The construction-start site/vertical split foots to the totals.

    The two legs are tested against their own floors, so a split that does not
    sum back to the stated hard cost and contingency would let a shortfall hide
    in the difference between the split and the whole.
    """
    rule = "cty_split_foots"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    if budget is None:
        return []
    region = _region(ctx)
    current = _current_phase(ctx)
    if region != REGION_MARRAN or current != PHASE_CONSTRUCTION:
        return [
            Finding(
                rule,
                Status.PASS,
                "-",
                "no construction-start split is in effect; the flat floor applies",
            )
        ]
    out: list[Finding] = []
    with amount_guard(rule, out):
        pairs = (
            ("hard_cost_cents", "site_hard_cost_cents", "vertical_hard_cost_cents"),
            (
                "hard_contingency_cents",
                "site_contingency_cents",
                "vertical_contingency_cents",
            ),
        )
        for total_key, site_key, vertical_key in pairs:
            total_cents = require_cents(f"cost_budget.{total_key}", budget.get(total_key))
            site = require_cents(f"cost_budget.{site_key}", budget.get(site_key))
            vertical = require_cents(
                f"cost_budget.{vertical_key}", budget.get(vertical_key)
            )
            if site + vertical != total_cents:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(budget, total_key),
                        f"{site_key} {fmt(site)} + {vertical_key} {fmt(vertical)} = "
                        f"{fmt(site + vertical)}, which does not foot to {total_key} "
                        f"{fmt(total_cents)} (off {fmt(site + vertical - total_cents)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "the site/vertical split foots to the hard cost and contingency totals",
            )
        )
    return out


@check("cty_escalation_reserved")
def check_cty_escalation_reserved(ctx: Context) -> list[Finding]:
    """A Vanterre project carries its separate escalation contingency.

    The Vanterre hard-cost floor is lower precisely because escalation is
    reserved separately; a project on the low floor with no escalation reserve
    has taken the discount without the offset.
    """
    rule = "cty_escalation_reserved"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    profile = _profile(ctx)
    if budget is None or profile is None:
        return []
    region = _region(ctx)
    if region != REGION_VANTERRE:
        return [
            Finding(
                rule,
                Status.PASS,
                "-",
                f"region {region!r} carries no separate escalation-contingency "
                f"requirement",
            )
        ]
    value = budget.get("escalation_contingency_cents")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(budget, "escalation_contingency_cents"),
                f"a vanterre project must reserve a separate escalation contingency; "
                f"the budget carries {value!r}",
            )
        ]
    return [
        Finding(
            rule,
            Status.PASS,
            "-",
            f"a separate escalation contingency of {fmt(value)} is reserved",
        )
    ]


# --------------------------------------------------------------------------- #
# gro_ -- the growth-assumption default
# --------------------------------------------------------------------------- #
@check("gro_growth_default")
def check_gro_growth_default(ctx: Context) -> list[Finding]:
    """The growth assumption is the standard 3/3 default, or market-supported.

    The default exists so that every project's underwriting is comparable; a
    deviation is permitted only with a documented market-supported alternative,
    which is a membership fact, not a judgment.
    """
    rule = "gro_growth_default"
    _sev(rule, Status.FAIL)
    profile = _profile(ctx)
    if profile is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        revenue = require_cents(
            "project_profile.revenue_growth_bps",
            profile.get("revenue_growth_bps"),
            unit="integer basis points",
        )
        cost = require_cents(
            "project_profile.cost_growth_bps",
            profile.get("cost_growth_bps"),
            unit="integer basis points",
        )
        if growth_is_standard(revenue, cost):
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the growth assumption is the standard "
                    f"{fmt_bps(STANDARD_GROWTH_BPS)} / {fmt_bps(STANDARD_GROWTH_BPS)} "
                    f"default",
                )
            )
        elif profile.get("market_supported_growth") is True:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the growth assumption of {fmt_bps(revenue)} / {fmt_bps(cost)} "
                    f"departs from the default with a documented market-supported "
                    f"alternative, which the standards permit",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(profile, "revenue_growth_bps"),
                    f"the growth assumption is {fmt_bps(revenue)} / {fmt_bps(cost)}; "
                    f"the standard is {fmt_bps(STANDARD_GROWTH_BPS)} / "
                    f"{fmt_bps(STANDARD_GROWTH_BPS)} and no market-supported "
                    f"alternative is documented",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# fee_ -- the fee formulas and the total, re-derived
# --------------------------------------------------------------------------- #
@check("fee_cm_rederives")
def check_fee_cm_rederives(ctx: Context) -> list[Finding]:
    """The stated CM Fee re-derives as 1.5% of hard cost, exactly.

    The formula is prescribed, so the stated figure is compared to the derived
    one with exact ``==``; a fee a cent off its formula is a fee off its
    formula.
    """
    rule = "fee_cm_rederives"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    if budget is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        hard = require_cents("cost_budget.hard_cost_cents", budget.get("hard_cost_cents"))
        stated = require_cents("cost_budget.cm_fee_cents", budget.get("cm_fee_cents"))
        derived = apply_rate(hard, CM_FEE_RATE_BPS)
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(budget, "cm_fee_cents"),
                    f"the stated CM Fee of {fmt(stated)} does not re-derive as "
                    f"{fmt_bps(CM_FEE_RATE_BPS)} of hard cost {fmt(hard)} = "
                    f"{fmt(derived)} (off {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the CM Fee of {fmt(stated)} re-derives from its formula",
                )
            )
    return out


@check("fee_dev_rederives")
def check_fee_dev_rederives(ctx: Context) -> list[Finding]:
    """The stated Development Fee re-derives as 3% of (total cost less financing)."""
    rule = "fee_dev_rederives"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    if budget is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        tpc = require_cents(
            "cost_budget.total_project_cost_cents", budget.get("total_project_cost_cents")
        )
        financing = require_cents(
            "cost_budget.financing_cost_cents", budget.get("financing_cost_cents")
        )
        stated = require_cents("cost_budget.dev_fee_cents", budget.get("dev_fee_cents"))
        derived = apply_rate(tpc - financing, DEV_FEE_RATE_BPS)
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(budget, "dev_fee_cents"),
                    f"the stated Development Fee of {fmt(stated)} does not re-derive "
                    f"as {fmt_bps(DEV_FEE_RATE_BPS)} of (total project cost "
                    f"{fmt(tpc)} less financing {fmt(financing)}) = {fmt(derived)} "
                    f"(off {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the Development Fee of {fmt(stated)} re-derives from its formula",
                )
            )
    return out


@check("fee_tpc_foots")
def check_fee_tpc_foots(ctx: Context) -> list[Finding]:
    """The stated total project cost foots to its components, to the cent."""
    rule = "fee_tpc_foots"
    _sev(rule, Status.FAIL)
    budget = _budget(ctx)
    if budget is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        components = [
            require_cents(f"cost_budget.{key}", budget.get(key))
            for key in (
                "hard_cost_cents",
                "hard_contingency_cents",
                "soft_cost_cents",
                "soft_contingency_cents",
                "financing_cost_cents",
                "cm_fee_cents",
                "dev_fee_cents",
            )
        ]
        stated = require_cents(
            "cost_budget.total_project_cost_cents", budget.get("total_project_cost_cents")
        )
        footed = sum(components)
        if stated != footed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(budget, "total_project_cost_cents"),
                    f"the stated total project cost of {fmt(stated)} does not foot to "
                    f"its components' sum of {fmt(footed)} "
                    f"(off {fmt(stated - footed)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the total project cost of {fmt(stated)} foots to its components",
                )
            )
    return out


@check("fee_variance_rederives")
def check_fee_variance_rederives(ctx: Context) -> list[Finding]:
    """Every stated plan-comparison variance re-derives as project minus plan.

    The variance column is the whole point of the side-by-side; a variance
    maintained beside the figures rather than derived from them drifts the
    first time either figure moves.
    """
    rule = "fee_variance_rederives"
    _sev(rule, Status.FAIL)
    comparison = ctx.one(DOC_PLAN_COMPARISON)
    if comparison is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rows(comparison, "rows"):
        metric = _text(row, "metric") or "?"
        with amount_guard(rule, out):
            project = require_cents(
                f"plan_comparison[{metric}].project_cents", row.get("project_cents")
            )
            plan = require_cents(
                f"plan_comparison[{metric}].plan_cents", row.get("plan_cents")
            )
            stated = require_cents(
                f"plan_comparison[{metric}].variance_cents", row.get("variance_cents")
            )
            checked += 1
            derived = derive_variance(project, plan)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(comparison, f"rows/{metric}/variance_cents"),
                        f"the stated {metric} variance of {fmt(stated)} does not "
                        f"re-derive as project {fmt(project)} less plan {fmt(plan)} "
                        f"= {fmt(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} plan-comparison variances re-derive",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cal_ -- the comparison basis and the template calendar
# --------------------------------------------------------------------------- #
@check("cal_basis_matches_waiver")
def check_cal_basis_matches_waiver(ctx: Context) -> list[Finding]:
    """The comparison basis matches the feasibility-waiver status.

    Pre-waiver requests compare to the Business Plan template; once feasibility
    is waived the project enters the annual plan and must show variance to the
    actual plan. A basis on the wrong side of the switch hides the variance the
    IC was meant to see.
    """
    rule = "cal_basis_matches_waiver"
    _sev(rule, Status.FAIL)
    comparison = ctx.one(DOC_PLAN_COMPARISON)
    profile = _profile(ctx)
    if comparison is None or profile is None:
        return []
    waived = profile.get("feasibility_waived")
    if not isinstance(waived, bool):
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(profile, "feasibility_waived"),
                f"feasibility_waived is {waived!r}, not a boolean; the required "
                f"comparison basis cannot be determined",
            )
        ]
    stated = _text(comparison, "basis")
    if stated not in BASES:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(comparison, "basis"),
                f"the comparison basis {stated!r} is not one of {BASES}",
            )
        ]
    expected = required_basis(waived)
    if stated != expected:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(comparison, "basis"),
                f"feasibility_waived={waived} requires the {expected!r} comparison "
                f"basis; the package compares to {stated!r}",
            )
        ]
    return [
        Finding(
            rule,
            Status.PASS,
            "-",
            f"the {stated!r} comparison basis matches feasibility_waived={waived}",
        )
    ]


@check("cal_template_current")
def check_cal_template_current(ctx: Context) -> list[Finding]:
    """A template-basis comparison uses the current template refresh.

    Deliberately a FLAG, not a failure: the comparison was made, just against a
    template a refresh cycle old, so the figures deserve a re-run rather than a
    hard stop. The template refreshes each January and June; runs only when the
    template regime is correctly in effect, since a wrong basis is owned by
    ``cal_basis_matches_waiver``.
    """
    rule = "cal_template_current"
    _sev(rule, Status.FLAG)
    comparison = ctx.one(DOC_PLAN_COMPARISON)
    profile = _profile(ctx)
    as_of = _parse_date(ctx.as_of)
    if comparison is None or profile is None or as_of is None:
        return []
    if (
        profile.get("feasibility_waived") is not False
        or _text(comparison, "basis") != BASIS_TEMPLATE
    ):
        return [
            Finding(
                rule,
                Status.PASS,
                "-",
                "the template-basis regime is not in effect; no refresh date to check",
            )
        ]
    expected = latest_template_refresh(as_of)
    stated = _parse_date(comparison.get("template_effective_date"))
    if stated is None:
        return [
            Finding(
                rule,
                Status.FLAG,
                ctx.loc(comparison, "template_effective_date"),
                f"the comparison names no readable template_effective_date; the "
                f"refresh in force at {as_of.isoformat()} is {expected.isoformat()} "
                f"and the comparison cannot be tied to it",
            )
        ]
    if stated != expected:
        return [
            Finding(
                rule,
                Status.FLAG,
                ctx.loc(comparison, "template_effective_date"),
                f"the comparison stands on the {stated.isoformat()} template; the "
                f"refresh in force at {as_of.isoformat()} is {expected.isoformat()}, "
                f"so the comparison should be re-run on the current template",
            )
        ]
    return [
        Finding(
            rule,
            Status.PASS,
            "-",
            f"the comparison stands on the current {expected.isoformat()} template "
            f"refresh",
        )
    ]


# --------------------------------------------------------------------------- #
# evt_ -- interim-request events
# --------------------------------------------------------------------------- #
@check("evt_type_known")
def check_evt_type_known(ctx: Context) -> list[Finding]:
    """Every logged event carries a known interim-trigger type.

    The event type is what makes the out-of-cycle requirement mechanical; an
    unknown type is an event nobody can say required a request or not.
    """
    rule = "evt_type_known"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_EVENT_LOG)
    if log is None:
        return []
    out: list[Finding] = []
    for row in _rows(log, "events"):
        etype = _text(row, "event_type")
        if etype not in EVENT_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"events/{_text(row, 'event_id') or '?'}/event_type"),
                    f"event {_text(row, 'event_id') or '?'} is typed {etype!r}, which "
                    f"is not one of the interim-trigger events {EVENT_TYPES}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_rows(log, 'events'))} logged events carry a known "
                f"interim-trigger type",
            )
        )
    return out


@check("evt_interim_request_filed")
def check_evt_interim_request_filed(ctx: Context) -> list[Finding]:
    """Every interim-trigger event links to an interim request in the log.

    The circumstances that force an out-of-cycle Spending Request are
    enumerated, so the control is pure membership: each event must name an
    interim approval that actually exists.
    """
    rule = "evt_interim_request_filed"
    _sev(rule, Status.FAIL)
    events = ctx.one(DOC_EVENT_LOG)
    log = ctx.one(DOC_APPROVAL_LOG)
    if events is None or log is None:
        return []
    interim_ids = _interim_approval_ids(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _rows(events, "events"):
        if _text(row, "event_type") not in EVENT_TYPES:
            continue  # evt_type_known owns this
        checked += 1
        eid = _text(row, "event_id") or "?"
        rid = _text(row, "interim_request_id")
        if rid is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(events, f"events/{eid}/interim_request_id"),
                    f"event {eid} ({_text(row, 'event_type')}) forces an out-of-cycle "
                    f"Spending Request but links to no interim request at all",
                )
            )
        elif rid not in interim_ids:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(events, f"events/{eid}/interim_request_id"),
                    f"event {eid} links to interim request {rid}, which is not an "
                    f"interim approval in the approval log",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} interim-trigger events link to an interim request",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# bid_ -- the construction-start bid coverage
# --------------------------------------------------------------------------- #
@check("bid_coverage_meets")
def check_bid_coverage_meets(ctx: Context) -> list[Finding]:
    """The construction-start bid coverage is at its 80% threshold.

    A third-party GC must show bid coverage for at least 80% of hard costs; an
    owner-GC project must have at least 80% of its cost line items
    competitively bid. Both compared cross-multiplied in integers, so exactly
    80% passes and a hair under fails.
    """
    rule = "bid_coverage_meets"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_BID_SCHEDULE)
    budget = _budget(ctx)
    profile = _profile(ctx)
    if schedule is None or budget is None or profile is None:
        return []
    current = _current_phase(ctx)
    if current != PHASE_CONSTRUCTION:
        return [
            Finding(
                rule,
                Status.PASS,
                "-",
                "the project has not reached construction start; the bid-coverage "
                "gate is not yet in effect",
            )
        ]
    gc_model = _text(profile, "gc_model")
    if gc_model not in GC_MODELS:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(profile, "gc_model"),
                f"the project's GC model {gc_model!r} is not one of {GC_MODELS}; no "
                f"bid-coverage test can be selected",
            )
        ]
    lines = _rows(schedule, "lines")
    out: list[Finding] = []
    with amount_guard(rule, out):
        if gc_model == GC_THIRD_PARTY:
            hard = require_cents(
                "cost_budget.hard_cost_cents", budget.get("hard_cost_cents")
            )
            covered = sum(
                require_cents(
                    f"bid_schedule[{_text(row, 'line_id') or '?'}].amount_cents",
                    row.get("amount_cents"),
                )
                for row in lines
                if row.get("competitively_bid") is True
            )
            if covered * 10000 >= hard * BID_COVERAGE_FLOOR_BPS:
                out.append(
                    Finding(
                        rule,
                        Status.PASS,
                        "-",
                        f"bid coverage of {fmt(covered)} meets the "
                        f"{fmt_bps(BID_COVERAGE_FLOOR_BPS)} threshold on hard cost "
                        f"{fmt(hard)}",
                    )
                )
            else:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, "lines"),
                        f"bid coverage of {fmt(covered)} is under the "
                        f"{fmt_bps(BID_COVERAGE_FLOOR_BPS)} threshold on hard cost "
                        f"{fmt(hard)}; construction may not start",
                    )
                )
        else:
            bid_count = sum(1 for row in lines if row.get("competitively_bid") is True)
            total = len(lines)
            if total > 0 and bid_count * 10000 >= total * BID_COVERAGE_FLOOR_BPS:
                out.append(
                    Finding(
                        rule,
                        Status.PASS,
                        "-",
                        f"{bid_count} of {total} cost line items are competitively "
                        f"bid, meeting the {fmt_bps(BID_COVERAGE_FLOOR_BPS)} threshold",
                    )
                )
            else:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, "lines"),
                        f"{bid_count} of {total} cost line items are competitively "
                        f"bid, under the {fmt_bps(BID_COVERAGE_FLOOR_BPS)} "
                        f"owner-GC threshold; construction may not start",
                    )
                )
    return out


@check("bid_gmp_bindable")
def check_bid_gmp_bindable(ctx: Context) -> list[Finding]:
    """An owner-GC project at construction start holds a bindable GMP.

    The bid coverage proves the pricing is competitive; the bindable GMP is
    what makes it enforceable. Without it the owner-GC project starts
    construction on an estimate nobody is bound to.
    """
    rule = "bid_gmp_bindable"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_BID_SCHEDULE)
    profile = _profile(ctx)
    if schedule is None or profile is None:
        return []
    current = _current_phase(ctx)
    if current != PHASE_CONSTRUCTION or _text(profile, "gc_model") != GC_OWNER:
        return [
            Finding(
                rule,
                Status.PASS,
                "-",
                "the owner-GC bindable-GMP gate is not in effect for this project",
            )
        ]
    if schedule.get("gmp_bindable") is not True:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(schedule, "gmp_bindable"),
                f"an owner-GC project at construction start must hold a bindable "
                f"GMP; the schedule states gmp_bindable="
                f"{schedule.get('gmp_bindable')!r}",
            )
        ]
    return [
        Finding(rule, Status.PASS, "-", "a bindable GMP is in place at construction start")
    ]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one request package."""
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
    """Analyze every ``.json`` request package in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of request-package reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
