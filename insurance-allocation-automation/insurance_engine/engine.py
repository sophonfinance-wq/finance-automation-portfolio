"""
Insurance cost allocation control engine (READ-ONLY).
=====================================================

Loads each programme file (a ``.json`` file produced by
:mod:`insurance_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **where the cost lands**, not whether a certificate is on
file. Certificate currency, limits and endorsements gate a payment, and the
accounts-payable engine owns that gate. Nothing here re-checks a certificate.

The shape of the problem
------------------------
A developer buys a programme, not a policy per project: a liability tower, a
builder's risk policy over whatever is under construction, an excess layer above
the primary. One premium arrives, and it has to become a number on each project's
job cost -- correctly, reproducibly, and summing back to what was paid.

Three failures hide inside that, and none of them look wrong in a column of
six-figure numbers: the residual cent that is dropped or double-counted; a basis
value that never arrived, silently redistributing every *other* project's share;
and a carrier audit credited to whoever is open today rather than to the projects
that actually bore the deposit.

The registry is organised around that:

1. ``set_``   -- is the programme file complete?
2. ``pol_``   -- is the policy register sound, and does the tower hold together?
3. ``alloc_`` -- does every share re-derive from its declared basis, to the cent?
4. ``br_``    -- does builder's risk cover the right things for the right term?
5. ``aud_``   -- did the audit true-up go back to the year that earned it?
6. ``gl_``    -- does the allocation reach job cost and tie to the ledger?

Design notes
------------
- **Strictly read-only.** Programme files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every allocation is compared with exact ``==``.
  The single tolerant control (``br_value_ties_budget``) reads its band from the
  policy rather than inventing one.
- **One allocation method.** Controls re-derive shares with the same
  largest-remainder primitive that produced them, so a mismatch is a real
  difference and never an artifact of two roundings.
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

from .allocation import basis_weights_bps
from .model import (
    AUDIT_TYPES,
    BASES,
    DOC_ALLOCATION_SCHEDULE,
    DOC_ALLOCATION_SUMMARY,
    DOC_AUDIT_REGISTER,
    DOC_GL_POSITIONS,
    DOC_JOB_COST_LEDGER,
    DOC_POLICY_REGISTER,
    DOC_PROJECT_REGISTER,
    DOC_TYPES,
    LAYER_EXCESS,
    LAYERS,
    LINE_BUILDERS_RISK,
    LINES,
    STAGE_COMPLETE,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, allocate_by_ratio, apply_rate, fmt, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~insurance_engine.money.AmountInvalidError` as a finding."""
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
# Programme helpers
# --------------------------------------------------------------------------- #
def _policies(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_POLICY_REGISTER), "policies")


def _policy_no(row: dict[str, Any]) -> str:
    value = row.get("policy_no")
    return value if isinstance(value, str) and value else "?"


def _projects(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_PROJECT_REGISTER), "projects"):
        code = _text(row, "code")
        if code and code not in out:
            out[code] = row
    return out


def _allocations(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ALLOCATION_SCHEDULE), "allocations")


def _allocations_for(ctx: Context, policy_no: str) -> list[dict[str, Any]]:
    """Allocation rows for one policy, in file order."""
    return [r for r in _allocations(ctx) if _text(r, "policy_no") == policy_no]


def _audits(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_AUDIT_REGISTER), "audits")


def _covered(policy: dict[str, Any]) -> list[str]:
    schedule = policy.get("covered_projects")
    if not isinstance(schedule, list):
        return []
    return [c for c in schedule if isinstance(c, str)]


def derive_shares(premium_cents: int, basis_values: list[int]) -> list[int]:
    """The allocation every control compares against.

    Values become integer basis-point weights, weights become integer cents, both
    by largest remainder. Defined in one place so the engine and the generator
    cannot drift apart on the residual.
    """
    return allocate_by_ratio(premium_cents, basis_weights_bps(basis_values))


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the programme depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the programme file "
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
                f"as_of {ctx.as_of!r} is not a readable date; the prepaid amortisation "
                f"is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# pol_ -- policy register and the tower
# --------------------------------------------------------------------------- #
@check("pol_required_fields")
def check_pol_required_fields(ctx: Context) -> list[Finding]:
    """Every policy carries the fields the allocation reads."""
    rule = "pol_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    required = ("policy_no", "line", "layer", "carrier", "inception_date", "expiration_date")
    out: list[Finding] = []
    for row in _policies(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"policies/{_policy_no(row)}"),
                    f"policy {_policy_no(row)} is missing {', '.join(missing)}",
                )
            )
        line = _text(row, "line")
        layer = _text(row, "layer")
        if line is not None and line not in LINES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"policies/{_policy_no(row)}/line"),
                    f"policy {_policy_no(row)} has line {line!r}, outside {LINES}; the "
                    f"continuity control groups by line",
                )
            )
        if layer is not None and layer not in LAYERS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"policies/{_policy_no(row)}/layer"),
                    f"policy {_policy_no(row)} has layer {layer!r}, outside {LAYERS}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_policies(ctx))} policies are fully described"
            )
        )
    return out


@check("pol_no_duplicate")
def check_pol_no_duplicate(ctx: Context) -> list[Finding]:
    """No policy number appears twice.

    The policy number joins the register to the allocation and the audit. A
    duplicate double-counts one premium across the programme total.
    """
    rule = "pol_no_duplicate"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _policies(ctx):
        key = _policy_no(row)
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"policies/{policy}"),
            f"policy {policy} appears {count} times; its premium is counted "
            f"{count} times in the programme total",
        )
        for policy, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} policy numbers are unique")
        )
    return out


@check("pol_term_runs_forwards")
def check_pol_term_runs_forwards(ctx: Context) -> list[Finding]:
    """A policy's term runs forwards.

    An inverted term makes the prepaid amortisation meaningless rather than merely
    wrong -- the remaining-days figure it produces is negative.
    """
    rule = "pol_term_runs_forwards"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _policies(ctx):
        inception = _parse_date(row.get("inception_date"))
        expiration = _parse_date(row.get("expiration_date"))
        if inception is None or expiration is None:
            continue
        checked += 1
        if inception >= expiration:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"policies/{_policy_no(row)}/inception_date"),
                    f"policy {_policy_no(row)} incepts {inception.isoformat()} and expires "
                    f"{expiration.isoformat()}; the term does not run forwards",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} policy terms run forwards"))
    return out


@check("pol_no_coverage_gap")
def check_pol_no_coverage_gap(ctx: Context) -> list[Finding]:
    """Successive terms of the same line leave no uninsured day.

    Both policies look perfectly valid on their own; the gap exists only *between*
    them, and an occurrence lands in it with nothing to respond.
    """
    rule = "pol_no_coverage_gap"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    by_line: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _policies(ctx):
        line = _text(row, "line")
        layer = _text(row, "layer")
        if line and layer and _parse_date(row.get("inception_date")):
            by_line.setdefault((line, layer), []).append(row)
    out: list[Finding] = []
    checked = 0
    for (line, layer), rows in sorted(by_line.items()):
        ordered = sorted(rows, key=lambda r: r["inception_date"])
        for prior, following in zip(ordered, ordered[1:]):
            prior_end = _parse_date(prior.get("expiration_date"))
            next_start = _parse_date(following.get("inception_date"))
            if prior_end is None or next_start is None:
                continue
            checked += 1
            if next_start > prior_end:
                gap = (next_start - prior_end).days
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"policies/{_policy_no(following)}/inception_date"),
                        f"{line} ({layer}) expires {prior_end.isoformat()} on "
                        f"{_policy_no(prior)} and does not resume until "
                        f"{next_start.isoformat()} on {_policy_no(following)}, leaving "
                        f"{gap} uninsured day(s)",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} renewal handovers are seamless")
        )
    return out


@check("pol_tower_has_no_gap")
def check_pol_tower_has_no_gap(ctx: Context) -> list[Finding]:
    """An excess layer attaches no higher than the primary limit beneath it.

    A tower with a gap is the most expensive kind of clerical error in insurance:
    it is invisible until a loss lands in the band nobody bought, and both
    policies respond correctly by declining.
    """
    rule = "pol_tower_has_no_gap"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _policies(ctx):
        if _text(row, "layer") != LAYER_EXCESS:
            continue
        underlying_no = _text(row, "attaches_over")
        underlying = next(
            (p for p in _policies(ctx) if _policy_no(p) == underlying_no), None
        )
        if underlying is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"policies/{_policy_no(row)}/attaches_over"),
                    f"excess policy {_policy_no(row)} names underlying policy "
                    f"{underlying_no!r}, which is not in the register; the attachment "
                    f"point cannot be proven",
                )
            )
            continue
        with amount_guard(rule, out):
            attaches = require_cents(
                f"policy[{_policy_no(row)}].attachment_point_cents",
                row.get("attachment_point_cents"),
            )
            beneath = require_cents(
                f"policy[{underlying_no}].limit_cents", underlying.get("limit_cents")
            )
            checked += 1
            if attaches > beneath:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"policies/{_policy_no(row)}/attachment_point_cents"),
                        f"excess policy {_policy_no(row)} attaches at {fmt(attaches)} over a "
                        f"primary limit of {fmt(beneath)}; {fmt(attaches - beneath)} of the "
                        f"tower is uninsured",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} excess layers attach without a gap")
        )
    return out


# --------------------------------------------------------------------------- #
# alloc_ -- the allocation itself
# --------------------------------------------------------------------------- #
@check("alloc_basis_declared")
def check_alloc_basis_declared(ctx: Context) -> list[Finding]:
    """Every policy declares the basis its premium is allocated on.

    The basis is a choice, and an undeclared one is a choice somebody made once and
    nobody can now reconstruct. It is also the input to every control below.
    """
    rule = "alloc_basis_declared"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"policies/{_policy_no(row)}/allocation_basis"),
            f"policy {_policy_no(row)} declares allocation basis "
            f"{_text(row, 'allocation_basis')!r}, which is not one of {BASES}",
        )
        for row in _policies(ctx)
        if _text(row, "allocation_basis") not in BASES
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_policies(ctx))} policies declare a known basis"
            )
        )
    return out


@check("alloc_project_exists")
def check_alloc_project_exists(ctx: Context) -> list[Finding]:
    """Every allocated project is in the project register."""
    rule = "alloc_project_exists"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    projects = _projects(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(
                schedule,
                f"allocations/{_text(row, 'policy_no')}/{_text(row, 'project_code')}",
            ),
            f"policy {_text(row, 'policy_no')} allocates to project "
            f"{_text(row, 'project_code')!r}, which is not in the register",
        )
        for row in _allocations(ctx)
        if _text(row, "project_code") and _text(row, "project_code") not in projects
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every allocation names a project in the register")
        )
    return out


@check("alloc_only_covered_projects")
def check_alloc_only_covered_projects(ctx: Context) -> list[Finding]:
    """A policy's premium reaches its covered schedule, and nothing else.

    Both directions matter. A project charged for cover it does not have is
    carrying somebody else's cost; a covered project charged nothing has had its
    cost absorbed by its neighbours, and the total still ties either way.
    """
    rule = "alloc_only_covered_projects"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for policy in _policies(ctx):
        policy_no = _policy_no(policy)
        covered = set(_covered(policy))
        allocated = {
            _text(r, "project_code")
            for r in _allocations_for(ctx, policy_no)
            if _text(r, "project_code")
        }
        checked += 1
        for extra in sorted(allocated - covered):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"allocations/{policy_no}/{extra}"),
                    f"policy {policy_no} allocates cost to {extra}, which is not on its "
                    f"covered schedule; that project is carrying cover it does not have",
                )
            )
        for missing in sorted(covered - allocated):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"allocations/{policy_no}/{missing}"),
                    f"policy {policy_no} covers {missing} but allocates it nothing; its "
                    f"share has been absorbed by the other covered projects",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} policies allocate exactly their schedule"
            )
        )
    return out


@check("alloc_basis_data_complete")
def check_alloc_basis_data_complete(ctx: Context) -> list[Finding]:
    """Every covered project carries a usable value for the declared basis.

    A missing basis value does not fail loudly; it drops the project out of the
    weighting and silently moves every *other* project's share. The total still
    ties to the premium, which is exactly why this needs its own control.
    """
    rule = "alloc_basis_data_complete"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for policy in _policies(ctx):
        basis = _text(policy, "allocation_basis")
        if basis not in BASES:
            continue
        for code in _covered(policy):
            project = projects.get(code)
            if project is None:
                continue
            checked += 1
            value = _int(project, basis)
            if value is None or value <= 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"projects/{code}/{basis}"),
                        f"project {code} is covered by policy {_policy_no(policy)} on a "
                        f"{basis} basis but carries {project.get(basis)!r}; it would drop "
                        f"out of the weighting and move every other project's share",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} covered projects carry their basis")
        )
    return out


@check("alloc_sums_to_premium")
def check_alloc_sums_to_premium(ctx: Context) -> list[Finding]:
    """Allocated cost equals the premium, exactly.

    Zero tolerance, and the identity the whole engine rests on. An allocation that
    is a penny short has not been allocated; a penny of real premium is sitting on
    no project at all, and it surfaces later as a job-cost tie-out nobody can
    source.
    """
    rule = "alloc_sums_to_premium"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for policy in _policies(ctx):
        policy_no = _policy_no(policy)
        with amount_guard(rule, out):
            premium = require_cents(
                f"policy[{policy_no}].premium_cents", policy.get("premium_cents")
            )
            allocated = 0
            for row in _allocations_for(ctx, policy_no):
                allocated += require_cents(
                    f"allocation[{policy_no}/{_text(row, 'project_code')}].allocated_cents",
                    row.get("allocated_cents"),
                )
            checked += 1
            if allocated != premium:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"allocations/{policy_no}"),
                        f"policy {policy_no} allocates {fmt(allocated)} against a premium of "
                        f"{fmt(premium)} (difference {fmt(allocated - premium)}); the "
                        f"residual is on no project at all",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} policies allocate to the cent")
        )
    return out


@check("alloc_shares_recompute")
def check_alloc_shares_recompute(ctx: Context) -> list[Finding]:
    """Each project's share re-derives from the declared basis.

    This is where the residual cent lives. Summing to the premium is necessary and
    not sufficient: an allocation can foot perfectly while the leftover penny sits
    on the wrong project. The engine re-derives every share by the same
    largest-remainder method that should have produced it and compares each one
    exactly -- so the penny is checked where it landed, not merely counted.
    """
    rule = "alloc_shares_recompute"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for policy in _policies(ctx):
        policy_no = _policy_no(policy)
        basis = _text(policy, "allocation_basis")
        covered = _covered(policy)
        if basis not in BASES or not covered:
            continue
        values: list[int] = []
        usable = True
        for code in covered:
            project = projects.get(code)
            value = _int(project, basis) if project else None
            if value is None or value <= 0:
                usable = False
                break
            values.append(value)
        if not usable:
            continue  # alloc_basis_data_complete owns this
        with amount_guard(rule, out):
            premium = require_cents(
                f"policy[{policy_no}].premium_cents", policy.get("premium_cents")
            )
            expected = dict(zip(covered, derive_shares(premium, values)))
            for row in _allocations_for(ctx, policy_no):
                code = _text(row, "project_code")
                if code not in expected:
                    continue
                stated = require_cents(
                    f"allocation[{policy_no}/{code}].allocated_cents",
                    row.get("allocated_cents"),
                )
                checked += 1
                if stated != expected[code]:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(schedule, f"allocations/{policy_no}/{code}"),
                            f"policy {policy_no} allocates {fmt(stated)} to {code}; "
                            f"{fmt(premium)} weighted by {basis} derives "
                            f"{fmt(expected[code])} (difference "
                            f"{fmt(stated - expected[code])})",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} shares re-derive from their basis")
        )
    return out


@check("alloc_no_negative")
def check_alloc_no_negative(ctx: Context) -> list[Finding]:
    """No project is allocated a negative share of a premium.

    A negative allocation is how a correction gets made without reversing the
    original: it nets to the right total and leaves two wrong numbers behind it.
    """
    rule = "alloc_no_negative"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_ALLOCATION_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _allocations(ctx):
        with amount_guard(rule, out):
            amount = require_cents(
                f"allocation[{_text(row, 'policy_no')}/{_text(row, 'project_code')}]"
                f".allocated_cents",
                row.get("allocated_cents"),
            )
            checked += 1
            if amount < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            schedule,
                            f"allocations/{_text(row, 'policy_no')}/"
                            f"{_text(row, 'project_code')}",
                        ),
                        f"policy {_text(row, 'policy_no')} allocates {fmt(amount)} to "
                        f"{_text(row, 'project_code')}; a negative share nets to the right "
                        f"total and leaves two wrong numbers behind it",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} allocations are positive"))
    return out


# --------------------------------------------------------------------------- #
# br_ -- builder's risk
# --------------------------------------------------------------------------- #
@check("br_value_ties_budget")
def check_br_value_ties_budget(ctx: Context) -> list[Finding]:
    """Insured value tracks the project's hard-cost budget.

    Deliberately tolerant, and the band comes from the policy rather than from the
    engine's opinion. Builder's risk is written on an estimate that moves with the
    budget, and a value well adrift of it is either a project insured for less than
    it costs or a premium paid on money nobody is spending.
    """
    rule = "br_value_ties_budget"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for policy in _policies(ctx):
        if _text(policy, "line") != LINE_BUILDERS_RISK:
            continue
        for code in _covered(policy):
            project = projects.get(code)
            if project is None:
                continue
            with amount_guard(rule, out):
                insured = require_cents(
                    f"project[{code}].insured_value_cents", project.get("insured_value_cents")
                )
                budget = require_cents(
                    f"project[{code}].hard_cost_cents", project.get("hard_cost_cents")
                )
                tolerance_bps = require_cents(
                    f"policy[{_policy_no(policy)}].value_tolerance_bps",
                    policy.get("value_tolerance_bps"),
                    unit="basis points",
                )
                checked += 1
                allowed = apply_rate(budget, tolerance_bps)
                if abs(insured - budget) > allowed:
                    out.append(
                        Finding(
                            rule,
                            Status.FLAG,
                            ctx.loc(register, f"projects/{code}/insured_value_cents"),
                            f"project {code} is insured for {fmt(insured)} against a "
                            f"hard-cost budget of {fmt(budget)} "
                            f"(tolerance {fmt(allowed)})",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} insured values track their budget")
        )
    return out


@check("br_term_covers_construction")
def check_br_term_covers_construction(ctx: Context) -> list[Finding]:
    """A builder's risk term brackets the construction it insures.

    Cover that starts after the first delivery, or ends before the last one, is a
    gap on the one asset that cannot be replaced from working capital.
    """
    rule = "br_term_covers_construction"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for policy in _policies(ctx):
        if _text(policy, "line") != LINE_BUILDERS_RISK:
            continue
        inception = _parse_date(policy.get("inception_date"))
        expiration = _parse_date(policy.get("expiration_date"))
        if inception is None or expiration is None:
            continue
        for code in _covered(policy):
            project = projects.get(code)
            if project is None:
                continue
            starts = _parse_date(project.get("construction_start"))
            ends = _parse_date(project.get("construction_end"))
            if starts is None or ends is None:
                continue
            checked += 1
            if inception > starts or expiration < ends:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"policies/{_policy_no(policy)}/inception_date"),
                        f"policy {_policy_no(policy)} runs {inception.isoformat()} to "
                        f"{expiration.isoformat()} while {code} builds "
                        f"{starts.isoformat()} to {ends.isoformat()}; the construction is "
                        f"not fully bracketed",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} builder's risk terms bracket construction"
            )
        )
    return out


@check("br_completed_project_removed")
def check_br_completed_project_removed(ctx: Context) -> list[Finding]:
    """A completed project is off the builder's risk schedule.

    Builder's risk covers work in progress. Leaving a finished project on the
    schedule keeps it in the weighting, so it takes a share of a premium for cover
    that no longer applies to it -- and every other project pays less than it
    should.
    """
    rule = "br_completed_project_removed"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_POLICY_REGISTER)
    if register is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for policy in _policies(ctx):
        if _text(policy, "line") != LINE_BUILDERS_RISK:
            continue
        for code in _covered(policy):
            project = projects.get(code)
            if project is None:
                continue
            checked += 1
            if _text(project, "stage") == STAGE_COMPLETE:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"policies/{_policy_no(policy)}/covered_projects"),
                        f"policy {_policy_no(policy)} still schedules {code}, which is "
                        f"complete; it is taking a share of a builder's risk premium for "
                        f"cover that no longer applies",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} scheduled projects are still building"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# aud_ -- carrier audit true-up
# --------------------------------------------------------------------------- #
@check("aud_true_up_sums")
def check_aud_true_up_sums(ctx: Context) -> list[Finding]:
    """A reallocated audit sums to the audit amount, exactly."""
    rule = "aud_true_up_sums"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_AUDIT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for audit in _audits(ctx):
        audit_no = _text(audit, "audit_no") or "?"
        with amount_guard(rule, out):
            amount = require_cents(f"audit[{audit_no}].amount_cents", audit.get("amount_cents"))
            allocated = 0
            for row in _rows(audit, "reallocation"):
                allocated += require_cents(
                    f"audit[{audit_no}].reallocation[{_text(row, 'project_code')}]"
                    f".credit_cents",
                    row.get("credit_cents"),
                )
            checked += 1
            if allocated != amount:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"audits/{audit_no}/reallocation"),
                        f"audit {audit_no} reallocates {fmt(allocated)} of a {fmt(amount)} "
                        f"true-up (difference {fmt(allocated - amount)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} audits reallocate to the cent")
        )
    return out


@check("aud_credits_deposit_bearers")
def check_aud_credits_deposit_bearers(ctx: Context) -> list[Finding]:
    """A true-up goes back to the projects that bore the deposit premium.

    This is the control worth having. A carrier audits after the term and issues
    the credit months later, by which time the open projects are not the same
    projects -- some have closed. Crediting whoever is open today is the intuitive
    booking and it is wrong in both directions at once: a project that never paid
    the deposit receives money, and one that did, and has since closed, never gets
    it back.
    """
    rule = "aud_credits_deposit_bearers"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_AUDIT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for audit in _audits(ctx):
        audit_no = _text(audit, "audit_no") or "?"
        policy_no = _text(audit, "policy_no")
        if policy_no is None:
            continue
        bore = {
            _text(r, "project_code")
            for r in _allocations_for(ctx, policy_no)
            if _text(r, "project_code")
        }
        credited = {
            _text(r, "project_code")
            for r in _rows(audit, "reallocation")
            if _text(r, "project_code")
        }
        if not bore:
            continue
        checked += 1
        for extra in sorted(credited - bore):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"audits/{audit_no}/reallocation/{extra}"),
                    f"audit {audit_no} on policy {policy_no} credits {extra}, which never "
                    f"bore the deposit premium on that policy",
                )
            )
        for missed in sorted(bore - credited):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"audits/{audit_no}/reallocation/{missed}"),
                    f"audit {audit_no} on policy {policy_no} does not credit {missed}, which "
                    f"bore the deposit premium; a closed project is still owed its share",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} true-ups return to the projects that paid"
            )
        )
    return out


@check("aud_uses_deposit_basis")
def check_aud_uses_deposit_basis(ctx: Context) -> list[Finding]:
    """The true-up is split on the same basis that split the deposit.

    Reallocating on the *current* basis would move money between projects for a
    period none of them can influence any more. The deposit basis is a historical
    fact; the audit's job is to correct its size, not its shape.
    """
    rule = "aud_uses_deposit_basis"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_AUDIT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for audit in _audits(ctx):
        audit_no = _text(audit, "audit_no") or "?"
        rows = _rows(audit, "reallocation")
        codes = [_text(r, "project_code") for r in rows]
        if not rows or any(c is None for c in codes):
            continue
        with amount_guard(rule, out):
            amount = require_cents(f"audit[{audit_no}].amount_cents", audit.get("amount_cents"))
            bases = [
                require_cents(
                    f"audit[{audit_no}].reallocation[{code}].deposit_basis_cents",
                    row.get("deposit_basis_cents"),
                )
                for code, row in zip(codes, rows)
            ]
            if any(b <= 0 for b in bases):
                continue
            expected = derive_shares(amount, bases)
            for code, row, want in zip(codes, rows, expected):
                stated = require_cents(
                    f"audit[{audit_no}].reallocation[{code}].credit_cents",
                    row.get("credit_cents"),
                )
                checked += 1
                if stated != want:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"audits/{audit_no}/reallocation/{code}"),
                            f"audit {audit_no} credits {fmt(stated)} to {code}; the deposit "
                            f"basis derives {fmt(want)} (difference {fmt(stated - want)})",
                        )
                    )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} credits split on the deposit basis")
        )
    return out


@check("aud_basis_restated")
def check_aud_basis_restated(ctx: Context) -> list[Finding]:
    """The audit records the final exposure it was actually settled on.

    Without it the credit can be checked for arithmetic but not for cause, and
    next year's deposit is estimated from the same figure that was just proven
    wrong.
    """
    rule = "aud_basis_restated"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_AUDIT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for audit in _audits(ctx):
        audit_no = _text(audit, "audit_no") or "?"
        if _text(audit, "audit_type") not in AUDIT_TYPES:
            continue
        for row in _rows(audit, "reallocation"):
            checked += 1
            if _int(row, "final_basis_cents") is None:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(
                            register,
                            f"audits/{audit_no}/reallocation/"
                            f"{_text(row, 'project_code')}/final_basis_cents",
                        ),
                        f"audit {audit_no} records no final exposure for "
                        f"{_text(row, 'project_code')}; next year's deposit will be "
                        f"estimated from the figure this audit just corrected",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} audit rows restate their basis")
        )
    return out


# --------------------------------------------------------------------------- #
# gl_ -- job cost and the ledger
# --------------------------------------------------------------------------- #
@check("gl_allocation_ties_job_cost")
def check_gl_allocation_ties_job_cost(ctx: Context) -> list[Finding]:
    """What was allocated per project equals what landed on its job cost.

    The allocation schedule is a working paper; the job-cost ledger is the
    accounting. Between them is a posting, and a posting is where an allocation
    stops being arithmetic and starts being a number somebody reports on.
    """
    rule = "gl_allocation_ties_job_cost"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_JOB_COST_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    derived: dict[str, int] = {}
    for row in _allocations(ctx):
        code = _text(row, "project_code")
        if code is None:
            continue
        with amount_guard(rule, out):
            derived[code] = derived.get(code, 0) + require_cents(
                f"allocation[{_text(row, 'policy_no')}/{code}].allocated_cents",
                row.get("allocated_cents"),
            )
    stated: dict[str, int] = {}
    for row in _rows(ledger, "postings"):
        code = _text(row, "project_code")
        if code is None:
            continue
        with amount_guard(rule, out):
            stated[code] = stated.get(code, 0) + require_cents(
                f"job_cost[{code}].amount_cents", row.get("amount_cents")
            )
    for code in sorted(set(derived) | set(stated)):
        want, got = derived.get(code, 0), stated.get(code, 0)
        if want != got:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"postings/{code}"),
                    f"project {code} carries {fmt(got)} of insurance in job cost; the "
                    f"allocation schedule gives it {fmt(want)} "
                    f"(difference {fmt(got - want)})",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"job cost ties the allocation across {len(derived)} projects",
            )
        )
    return out


@check("gl_prepaid_amortisation_ties")
def check_gl_prepaid_amortisation_ties(ctx: Context) -> list[Finding]:
    """Unearned premium is re-derived from each term and ties the ledger.

    Premium is paid up front, so at any review date part of it is still an asset.
    The engine re-derives that straight-line across the days of each policy term
    rather than trusting the number carried forward.
    """
    rule = "gl_prepaid_amortisation_ties"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    as_of = _parse_date(ctx.as_of)
    if gl is None or as_of is None:
        return []
    out: list[Finding] = []
    derived = 0
    for policy in _policies(ctx):
        inception = _parse_date(policy.get("inception_date"))
        expiration = _parse_date(policy.get("expiration_date"))
        if inception is None or expiration is None or expiration <= inception:
            continue
        with amount_guard(rule, out):
            premium = require_cents(
                f"policy[{_policy_no(policy)}].premium_cents", policy.get("premium_cents")
            )
            span = (expiration - inception).days
            remaining = (expiration - as_of).days
            if remaining <= 0:
                continue
            remaining = min(remaining, span)
            derived += premium * remaining // span
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.prepaid_insurance_cents", gl.get("prepaid_insurance_cents")
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "prepaid_insurance_cents"),
                    f"prepaid insurance carries {fmt(stated)}; straight-line amortisation of "
                    f"the policy register to {as_of.isoformat()} gives {fmt(derived)} "
                    f"(difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"unearned premium of {fmt(derived)} ties prepaid"
                )
            )
    return out


@check("gl_total_ties_programme")
def check_gl_total_ties_programme(ctx: Context) -> list[Finding]:
    """Total insurance cost equals the sum of the policies written."""
    rule = "gl_total_ties_programme"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    if gl is None:
        return []
    out: list[Finding] = []
    derived = 0
    for policy in _policies(ctx):
        with amount_guard(rule, out):
            derived += require_cents(
                f"policy[{_policy_no(policy)}].premium_cents", policy.get("premium_cents")
            )
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.total_insurance_cost_cents", gl.get("total_insurance_cost_cents")
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "total_insurance_cost_cents"),
                    f"the ledger carries {fmt(stated)} of programme cost; the policy "
                    f"register sums to {fmt(derived)} (difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"programme cost of {fmt(derived)} ties the ledger"
                )
            )
    return out


@check("rpt_per_unit_recomputes")
def check_rpt_per_unit_recomputes(ctx: Context) -> list[Finding]:
    """The per-unit metric re-derives from allocated cost and unit count.

    It is the figure that ends up in a board pack, and it is the one nobody
    recalculates -- which is exactly why it is worth recalculating.
    """
    rule = "rpt_per_unit_recomputes"
    _sev(rule, Status.FLAG)
    summary = ctx.one(DOC_ALLOCATION_SUMMARY)
    if summary is None:
        return []
    projects = _projects(ctx)
    allocated: dict[str, int] = {}
    out: list[Finding] = []
    for row in _allocations(ctx):
        code = _text(row, "project_code")
        if code is None:
            continue
        with amount_guard(rule, out):
            allocated[code] = allocated.get(code, 0) + require_cents(
                f"allocation[{_text(row, 'policy_no')}/{code}].allocated_cents",
                row.get("allocated_cents"),
            )
    checked = 0
    for row in _rows(summary, "projects"):
        code = _text(row, "project_code")
        project = projects.get(code or "")
        if project is None:
            continue
        units = _int(project, "unit_count")
        if units is None or units <= 0:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"summary[{code}].per_unit_cents", row.get("per_unit_cents")
            )
            checked += 1
            expected = allocated.get(code, 0) // units
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(summary, f"projects/{code}/per_unit_cents"),
                        f"project {code} reports {fmt(stated)} per unit; "
                        f"{fmt(allocated.get(code, 0))} across {units} units is "
                        f"{fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} per-unit metrics recompute")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one programme file."""
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
    """Analyze every ``.json`` programme file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of programme-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
