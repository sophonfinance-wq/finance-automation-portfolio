"""
Contingency rollforward and adequacy control engine (READ-ONLY).
================================================================

Loads each period file (a ``.json`` file produced by
:mod:`contingency_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **the contingency status block in a periodic project
report**: the two buckets rolled forward from last period's balance, through the
draws allocated against them, to the balance remaining and the adequacy call made
on it. It does not forecast. Whether the projected potential use is a sound
estimate is a judgement no engine can make; whether the block that states it is
arithmetically the block those figures produce is exactly what an engine can
settle.

The shape of the problem
------------------------
Six numbers and a word, restated by hand, every period, for every active project,
then added up into a portfolio rollup. Three failures hide in that, and none of
them look wrong on the page: the current balance typed rather than derived, so it
no longer equals prior less allocated; the allocated-this-period total maintained
beside the draw detail rather than from it, so a draw never reaches the total --
or a single draw is written for more than the balance it draws against; and the
adequacy word carried forward from a period in which it was true, while the
projected potential use climbs past the balance behind it.

The registry is organised around that:

1. ``set_`` -- is the period file complete?
2. ``prj_`` -- is the project register sound, and is each active project budgeted?
3. ``alc_`` -- is every draw well-formed, attributable and inside the period?
4. ``ctg_`` -- does the block roll forward, tie its line items, reconcile to the
   budget, and stay inside the balance it draws against?
5. ``adq_`` -- is the adequacy call the one the figures produce, and how thin is
   the headroom behind it?
6. ``rpt_`` -- does the portfolio rollup foot from the blocks it summarises?

Design notes
------------
- **Strictly read-only.** Period files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every rollforward identity is exact ``==``.
- **One rollforward kernel.** Controls and the generator share
  :mod:`contingency_engine.rollforward`, so a finding cannot disagree with the
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
    ADEQUACY_INADEQUATE,
    ADEQUACY_VALUES,
    BUCKETS,
    DOC_ALLOCATION_REGISTER,
    DOC_BUDGET_REGISTER,
    DOC_CONTINGENCY_BLOCK,
    DOC_EXPOSURE_WATCHLIST,
    DOC_PORTFOLIO_ROLLUP,
    DOC_PROJECT_REGISTER,
    DOC_TYPES,
    PROJECT_ACTIVE,
    PROJECT_STATUSES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents
from .rollforward import (
    allocated_to_date,
    assess_adequacy,
    current_balance,
    first_overdraw,
    headroom,
    within_watch_band,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~contingency_engine.money.AmountInvalidError` as a finding."""
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
# Period-file helpers
# --------------------------------------------------------------------------- #
def _projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PROJECT_REGISTER), "projects")


def _project_id(row: dict[str, Any]) -> str:
    value = row.get("project_id")
    return value if isinstance(value, str) and value else "?"


def _project_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _projects(ctx):
        pid = _project_id(row)
        if pid != "?" and pid not in out:
            out[pid] = row
    return out


def _active_projects(ctx: Context) -> list[dict[str, Any]]:
    """Projects that restate a contingency block this period, deduplicated.

    Only an active project carries a block. A project whose status is not one the
    engine knows is skipped here and left to ``prj_status_valid``: guessing that an
    unreadable status means active would invent a completeness failure out of a
    vocabulary failure.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in _projects(ctx):
        pid = _project_id(row)
        if pid in seen:
            continue
        seen.add(pid)
        if _text(row, "status") == PROJECT_ACTIVE:
            out.append(row)
    return out


def _budget_lines(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_BUDGET_REGISTER), "contingency_lines")


def _budget_map(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _budget_lines(ctx):
        pid = _text(row, "project_id")
        bucket = _text(row, "bucket")
        if pid and bucket and (pid, bucket) not in out:
            out[(pid, bucket)] = row
    return out


def _allocations(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ALLOCATION_REGISTER), "allocations")


def _allocation_id(row: dict[str, Any]) -> str:
    value = row.get("allocation_id")
    return value if isinstance(value, str) and value else "?"


def _allocations_for(ctx: Context, project_id: str, bucket: str) -> list[dict[str, Any]]:
    """Every draw in the period against one project's bucket, in draw order.

    Ordered by draw date then allocation id, so the drawdown walk measures each
    draw against what the draws before it actually left. A draw whose date cannot
    be read sorts last rather than being dropped: ``alc_required_fields`` owns the
    unreadable date, and losing the draw here would understate the drawdown.
    """
    rows = [
        r
        for r in _allocations(ctx)
        if _text(r, "project_id") == project_id and _text(r, "bucket") == bucket
    ]
    return sorted(
        rows,
        key=lambda r: (_parse_date(r.get("allocation_date")) or date.max, _allocation_id(r)),
    )


def _blocks(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CONTINGENCY_BLOCK), "buckets")


def _block_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_text(row, "project_id") or "?", _text(row, "bucket") or "?")


def _block_label(row: dict[str, Any]) -> str:
    pid, bucket = _block_key(row)
    return f"{pid}/{bucket}"


def _rollup(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_PORTFOLIO_ROLLUP)


# --------------------------------------------------------------------------- #
# Shared re-derivation -- the generator computes with these too
# --------------------------------------------------------------------------- #
def recompute_period_allocation(ctx: Context, project_id: str, bucket: str) -> int:
    """Sum the period's draw detail for one project bucket.

    This is what the block's allocated-this-period line is supposed to be. Shared
    with the generator, so the total the engine ties to is the total that produced
    the data.

    Raises :class:`AmountInvalidError` if a draw amount is not integer cents; the
    calling control contains that to the bucket being read.
    """
    return sum(
        require_cents(
            f"allocation[{_allocation_id(row)}].amount_cents", row.get("amount_cents")
        )
        for row in _allocations_for(ctx, project_id, bucket)
    )


def recompute_watchlist(ctx: Context, watch_bps: int) -> list[dict[str, Any]]:
    """The exposure watchlist re-derived from the contingency block.

    One entry per adequate bucket whose projected potential use reaches the watch
    band. Amounts are read defensively rather than validated: a malformed figure
    is owned by the rollforward controls, and a watchlist that refused to build
    because of one bad cell would report a tie-out failure that is really a
    schema failure.
    """
    entries: list[dict[str, Any]] = []
    for row in _blocks(ctx):
        pid, bucket = _block_key(row)
        current = _int(row, "current_balance_cents")
        projected = _int(row, "projected_use_cents")
        if current is None or projected is None:
            continue
        if within_watch_band(current, projected, watch_bps):
            entries.append(
                {
                    "project_id": pid,
                    "bucket": bucket,
                    "current_balance_cents": current,
                    "projected_use_cents": projected,
                    "headroom_cents": headroom(current, projected),
                }
            )
    entries.sort(key=lambda e: (e["project_id"], e["bucket"]))
    return entries


def recompute_rollup_totals(ctx: Context) -> dict[str, int]:
    """The portfolio totals re-derived by adding the block up.

    Raises :class:`AmountInvalidError` if a block amount is not integer cents; the
    calling control contains that.
    """
    totals = {
        "total_allocated_period_cents": 0,
        "total_current_balance_cents": 0,
        "total_projected_use_cents": 0,
    }
    for row in _blocks(ctx):
        label = _block_label(row)
        totals["total_allocated_period_cents"] += require_cents(
            f"block[{label}].allocated_period_cents", row.get("allocated_period_cents")
        )
        totals["total_current_balance_cents"] += require_cents(
            f"block[{label}].current_balance_cents", row.get("current_balance_cents")
        )
        totals["total_projected_use_cents"] += require_cents(
            f"block[{label}].projected_use_cents", row.get("projected_use_cents")
        )
    return totals


def count_inadequate(ctx: Context) -> int:
    """How many buckets the block itself calls inadequate.

    Counts the stated words, not recomputed ones: ``adq_flag_recomputes`` owns
    whether each word is right, and this control owns whether the rollup counted
    the words that are there. Splitting them keeps one break from firing two
    controls.
    """
    return sum(1 for row in _blocks(ctx) if _text(row, "adequacy") == ADEQUACY_INADEQUATE)


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("project_id"),
        entry.get("bucket"),
        entry.get("current_balance_cents"),
        entry.get("projected_use_cents"),
        entry.get("headroom_cents"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the period file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the period file carries "
                    f"exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} contingency artifacts are present",
            )
        )
    for label, value in (("period_start", ctx.period_start), ("period_end", ctx.period_end)):
        if _parse_date(value) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    "-",
                    f"{label} {value!r} is not a readable date; the period every draw is "
                    f"tested against cannot be bounded",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# prj_ -- the project register and the budget behind it
# --------------------------------------------------------------------------- #
@check("prj_unique_ids")
def check_prj_unique_ids(ctx: Context) -> list[Finding]:
    """No project id appears twice.

    The project id joins the register to the budget, to every draw and to the
    block. A duplicate makes a draw ambiguous about which project it burned.
    """
    rule = "prj_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _projects(ctx):
        seen[_project_id(row)] = seen.get(_project_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"projects/{pid}"),
            f"project id {pid} appears {count} times; a draw that names it cannot be "
            f"attributed to one project",
        )
        for pid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} project ids are unique")
        )
    return out


@check("prj_status_valid")
def check_prj_status_valid(ctx: Context) -> list[Finding]:
    """Every project carries a known status.

    Status is what decides whether a project restates a block this period. An
    unreadable status means the engine cannot say whether a missing block is a
    closed project or an omission.
    """
    rule = "prj_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _projects(ctx):
        status = _text(row, "status")
        if status not in PROJECT_STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{_project_id(row)}/status"),
                    f"project {_project_id(row)} is marked {status!r}, which is not one of "
                    f"{PROJECT_STATUSES}; whether it owes a contingency block cannot be "
                    f"determined",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_projects(ctx))} projects carry a known status",
            )
        )
    return out


@check("prj_budget_defined")
def check_prj_budget_defined(ctx: Context) -> list[Finding]:
    """Every active project budgets both contingency buckets.

    The budget contingency line is the figure the whole bucket reconciles to.
    Without it the engine knows a bucket exists but not what it was funded with,
    so the reconciliation control would silently skip it.
    """
    rule = "prj_budget_defined"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BUDGET_REGISTER)
    if register is None:
        return []
    budget = _budget_map(ctx)
    out: list[Finding] = []
    checked = 0
    for project in _active_projects(ctx):
        pid = _project_id(project)
        for bucket in BUCKETS:
            checked += 1
            if (pid, bucket) not in budget:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"contingency_lines/{pid}/{bucket}"),
                        f"the budget carries no {bucket} contingency line for active project "
                        f"{pid}; the bucket has nothing to reconcile to",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} active-project buckets carry a budget contingency line",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# alc_ -- the draws allocated this period
# --------------------------------------------------------------------------- #
@check("alc_required_fields")
def check_alc_required_fields(ctx: Context) -> list[Finding]:
    """Every draw carries the descriptive fields the controls read.

    The description is required, not decorative: a contingency draw with no stated
    reason is an amount nobody can review, and the whole point of holding
    contingency separately is that each release is justified.
    """
    rule = "alc_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    if register is None:
        return []
    required = ("allocation_id", "project_id", "bucket", "description", "allocation_date")
    out: list[Finding] = []
    for row in _allocations(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"allocations/{_allocation_id(row)}"),
                    f"allocation {_allocation_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_allocations(ctx))} allocations carry their required fields",
            )
        )
    return out


@check("alc_unique_ids")
def check_alc_unique_ids(ctx: Context) -> list[Finding]:
    """No allocation id appears twice.

    A repeated id is how one draw becomes two entries, or two draws become one
    reviewable event. Either way the register stops being a list of distinct
    releases against the bucket.
    """
    rule = "alc_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _allocations(ctx):
        seen[_allocation_id(row)] = seen.get(_allocation_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"allocations/{aid}"),
            f"allocation id {aid} appears {count} times; the register can no longer "
            f"prove these are distinct draws",
        )
        for aid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} allocation ids are unique")
        )
    return out


@check("alc_project_exists")
def check_alc_project_exists(ctx: Context) -> list[Finding]:
    """Every draw names a project in the register.

    A draw against a project nobody is reporting on is contingency spent outside
    the block entirely: it lands in job cost and never reduces a stated balance.
    """
    rule = "alc_project_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    if register is None:
        return []
    projects = _project_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"allocations/{_allocation_id(row)}/project_id"),
            f"allocation {_allocation_id(row)} draws on project "
            f"{_text(row, 'project_id')!r}, which is not in the project register",
        )
        for row in _allocations(ctx)
        if _text(row, "project_id") and _text(row, "project_id") not in projects
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every allocation names a project in the register")
        )
    return out


@check("alc_bucket_valid")
def check_alc_bucket_valid(ctx: Context) -> list[Finding]:
    """Every draw names a known contingency bucket.

    Construction and project contingency roll forward separately and are never
    netted. A draw filed to a third, invented bucket reduces neither balance while
    still appearing to be a contingency release.
    """
    rule = "alc_bucket_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"allocations/{_allocation_id(row)}/bucket"),
            f"allocation {_allocation_id(row)} is filed to bucket "
            f"{_text(row, 'bucket')!r}, which is not one of {BUCKETS}; it reduces no "
            f"stated balance",
        )
        for row in _allocations(ctx)
        if _text(row, "bucket") and _text(row, "bucket") not in BUCKETS
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_allocations(ctx))} allocations name a known bucket",
            )
        )
    return out


@check("alc_within_period")
def check_alc_within_period(ctx: Context) -> list[Finding]:
    """Every draw falls inside the reporting period it is allocated to.

    The block says *allocated this period*. A draw dated outside the period is
    either in the wrong block or in two of them, and the prior balance it is being
    subtracted from already reflected it.
    """
    rule = "alc_within_period"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    start = _parse_date(ctx.period_start)
    end = _parse_date(ctx.period_end)
    if register is None or start is None or end is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _allocations(ctx):
        when = _parse_date(row.get("allocation_date"))
        if when is None:
            continue  # alc_required_fields owns an unreadable date
        checked += 1
        if when < start or when > end:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"allocations/{_allocation_id(row)}/allocation_date"),
                    f"allocation {_allocation_id(row)} is dated {when.isoformat()}, outside "
                    f"the reporting period {start.isoformat()} to {end.isoformat()}; it "
                    f"cannot be an allocation of this period",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} allocations fall inside the period"
            )
        )
    return out


@check("alc_amount_positive")
def check_alc_amount_positive(ctx: Context) -> list[Finding]:
    """Every draw is a positive amount.

    A draw is a release *out* of contingency. A zero or negative line is a
    restoration or a void dressed as a draw, and it walks through the drawdown
    control untouched while quietly raising the balance the next draw is measured
    against.
    """
    rule = "alc_amount_positive"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _allocations(ctx):
        with amount_guard(rule, out):
            amount = require_cents(
                f"allocation[{_allocation_id(row)}].amount_cents", row.get("amount_cents")
            )
            checked += 1
            if amount <= 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"allocations/{_allocation_id(row)}/amount_cents"),
                        f"allocation {_allocation_id(row)} draws {fmt(amount)} against "
                        f"contingency; a draw is a release out of the bucket and must be "
                        f"a positive amount",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} allocations draw a positive amount")
        )
    return out


# --------------------------------------------------------------------------- #
# ctg_ -- the rollforward itself
# --------------------------------------------------------------------------- #
@check("ctg_block_complete")
def check_ctg_block_complete(ctx: Context) -> list[Finding]:
    """Every active project restates both buckets, exactly once.

    A bucket that quietly stops being restated is a balance nobody is watching. A
    bucket restated twice is two rollforwards of the same money, and the portfolio
    rollup will foot to whichever pair of rows was added up.
    """
    rule = "ctg_block_complete"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if block is None:
        return []
    present: dict[tuple[str, str], int] = {}
    for row in _blocks(ctx):
        key = _block_key(row)
        present[key] = present.get(key, 0) + 1
    out: list[Finding] = []
    checked = 0
    for project in _active_projects(ctx):
        pid = _project_id(project)
        for bucket in BUCKETS:
            checked += 1
            count = present.get((pid, bucket), 0)
            if count == 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(block, f"buckets/{pid}/{bucket}"),
                        f"active project {pid} restates no {bucket} contingency bucket this "
                        f"period; the balance is carried forward unreported",
                    )
                )
            elif count > 1:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(block, f"buckets/{pid}/{bucket}"),
                        f"project {pid} restates the {bucket} contingency bucket {count} "
                        f"times; the rollup would add the same balance more than once",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} active-project buckets are restated once"
            )
        )
    return out


@check("ctg_current_rolls_forward")
def check_ctg_current_rolls_forward(ctx: Context) -> list[Finding]:
    """Current contingency equals prior less allocated this period, per bucket.

    This is the identity the block is named after, and it is the one most often
    broken, because the current balance is the column people type. Compared with
    exact ``==``: a bucket that is off by a cent is a bucket that was not rolled
    forward, it was re-entered.
    """
    rule = "ctg_current_rolls_forward"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if block is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        label = _block_label(row)
        with amount_guard(rule, out):
            prior = require_cents(
                f"block[{label}].prior_balance_cents", row.get("prior_balance_cents")
            )
            allocated = require_cents(
                f"block[{label}].allocated_period_cents", row.get("allocated_period_cents")
            )
            stated = require_cents(
                f"block[{label}].current_balance_cents", row.get("current_balance_cents")
            )
            checked += 1
            derived = current_balance(prior, allocated)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(block, f"buckets/{label}/current_balance_cents"),
                        f"{label} states a current balance of {fmt(stated)}; prior "
                        f"{fmt(prior)} less allocated {fmt(allocated)} is {fmt(derived)} "
                        f"(off by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} buckets roll forward exactly")
        )
    return out


@check("ctg_to_date_rolls_forward")
def check_ctg_to_date_rolls_forward(ctx: Context) -> list[Finding]:
    """Allocated to date equals allocated in prior periods plus this period.

    The cumulative column is what the budget reconciliation leans on, and it is
    maintained separately from the period column. When the two stop agreeing the
    bucket appears to reconcile in one direction and not the other.
    """
    rule = "ctg_to_date_rolls_forward"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if block is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        label = _block_label(row)
        with amount_guard(rule, out):
            prior_alloc = require_cents(
                f"block[{label}].allocated_prior_cents", row.get("allocated_prior_cents")
            )
            period_alloc = require_cents(
                f"block[{label}].allocated_period_cents", row.get("allocated_period_cents")
            )
            stated = require_cents(
                f"block[{label}].allocated_to_date_cents", row.get("allocated_to_date_cents")
            )
            checked += 1
            derived = allocated_to_date(prior_alloc, period_alloc)
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(block, f"buckets/{label}/allocated_to_date_cents"),
                        f"{label} states {fmt(stated)} allocated to date; prior periods "
                        f"{fmt(prior_alloc)} plus this period {fmt(period_alloc)} is "
                        f"{fmt(derived)} (off by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} cumulative allocations roll forward exactly"
            )
        )
    return out


@check("ctg_allocated_ties_line_items")
def check_ctg_allocated_ties_line_items(ctx: Context) -> list[Finding]:
    """The allocated-this-period line equals the draws behind it.

    The total is the number that leaves the balance; the register is the evidence
    for it. Maintained side by side, they part company the first time a draw is
    added to one and not the other -- and the bucket then reports headroom that
    was already spent.
    """
    rule = "ctg_allocated_ties_line_items"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    if block is None or register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        pid, bucket = _block_key(row)
        label = _block_label(row)
        with amount_guard(rule, out):
            stated = require_cents(
                f"block[{label}].allocated_period_cents", row.get("allocated_period_cents")
            )
            derived = recompute_period_allocation(ctx, pid, bucket)
            count = len(_allocations_for(ctx, pid, bucket))
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(block, f"buckets/{label}/allocated_period_cents"),
                        f"{label} states {fmt(stated)} allocated this period; the {count} "
                        f"draw(s) in the register sum to {fmt(derived)} "
                        f"(off by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} period totals tie their draw detail"
            )
        )
    return out


@check("ctg_budget_reconciles")
def check_ctg_budget_reconciles(ctx: Context) -> list[Finding]:
    """Each bucket reconciles to the contingency line in the project budget.

    The balance left plus everything ever allocated out of the bucket is the
    contingency the budget funded. This is the control that catches a bucket
    quietly topped up -- or trimmed -- outside the rollforward: the period
    identities all still hold, and the bucket no longer ties to the budget it came
    from. Buckets with no budget line are left to ``prj_budget_defined``.
    """
    rule = "ctg_budget_reconciles"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if block is None:
        return []
    budget = _budget_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        key = _block_key(row)
        label = _block_label(row)
        line = budget.get(key)
        if line is None:
            continue  # prj_budget_defined owns this
        with amount_guard(rule, out):
            funded = require_cents(
                f"budget[{label}].budget_contingency_cents", line.get("budget_contingency_cents")
            )
            current = require_cents(
                f"block[{label}].current_balance_cents", row.get("current_balance_cents")
            )
            to_date = require_cents(
                f"block[{label}].allocated_to_date_cents", row.get("allocated_to_date_cents")
            )
            checked += 1
            if funded != current + to_date:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(block, f"buckets/{label}/allocated_to_date_cents"),
                        f"{label} carries {fmt(current)} remaining plus {fmt(to_date)} "
                        f"allocated to date, which is {fmt(current + to_date)}; the budget "
                        f"funds this bucket at {fmt(funded)} "
                        f"(off by {fmt(current + to_date - funded)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} buckets reconcile to the budget line"
            )
        )
    return out


@check("ctg_no_overdraw")
def check_ctg_no_overdraw(ctx: Context) -> list[Finding]:
    """No single draw exceeds the balance standing in front of it.

    The draws are walked in date order from the prior balance, each measured
    against what the ones before it left. Only the walk can name the draw that
    broke the bucket: once the period total is struck, an individual overdraw has
    already been averaged into it, and a bucket that ends the period positive can
    still have been overdrawn in the middle of it.
    """
    rule = "ctg_no_overdraw"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    register = ctx.one(DOC_ALLOCATION_REGISTER)
    if block is None or register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        pid, bucket = _block_key(row)
        label = _block_label(row)
        with amount_guard(rule, out):
            prior = require_cents(
                f"block[{label}].prior_balance_cents", row.get("prior_balance_cents")
            )
            draws = [
                (
                    _allocation_id(a),
                    require_cents(
                        f"allocation[{_allocation_id(a)}].amount_cents", a.get("amount_cents")
                    ),
                )
                for a in _allocations_for(ctx, pid, bucket)
            ]
            checked += 1
            offending = first_overdraw(prior, draws)
            if offending is not None:
                allocation_id, amount, remaining = offending
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"allocations/{allocation_id}/amount_cents"),
                        f"allocation {allocation_id} draws {fmt(amount)} against {label} when "
                        f"only {fmt(remaining)} remained; the draw exceeds the balance it is "
                        f"drawn against by {fmt(amount - remaining)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} bucket drawdowns stay inside the balance"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# adq_ -- the adequacy assessment
# --------------------------------------------------------------------------- #
@check("adq_projection_nonnegative")
def check_adq_projection_nonnegative(ctx: Context) -> list[Finding]:
    """Projected potential use is never negative.

    A negative projection is not an expectation of savings; it is a sign error
    that makes every bucket adequate by construction, because a balance always
    exceeds a negative call on it.
    """
    rule = "adq_projection_nonnegative"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if block is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        label = _block_label(row)
        with amount_guard(rule, out):
            projected = require_cents(
                f"block[{label}].projected_use_cents", row.get("projected_use_cents")
            )
            checked += 1
            if projected < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(block, f"buckets/{label}/projected_use_cents"),
                        f"{label} projects {fmt(projected)} of potential use; a negative "
                        f"projection makes the adequacy test pass on any balance at all",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} projected-use figures are non-negative"
            )
        )
    return out


@check("adq_flag_recomputes")
def check_adq_flag_recomputes(ctx: Context) -> list[Finding]:
    """Each bucket's adequacy word recomputes from its own two amounts.

    This is the control the engine exists for. Adequacy is a *determination*, and
    a determination that is not recomputed from the evidence is an assertion. A
    bucket is adequate exactly when the balance remaining meets the projected
    potential use -- met at the projection, ``>=`` not ``>`` -- and the word on
    the row is rebuilt from those two figures and compared.
    """
    rule = "adq_flag_recomputes"
    _sev(rule, Status.FAIL)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if block is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        label = _block_label(row)
        stated = _text(row, "adequacy")
        with amount_guard(rule, out):
            current = require_cents(
                f"block[{label}].current_balance_cents", row.get("current_balance_cents")
            )
            projected = require_cents(
                f"block[{label}].projected_use_cents", row.get("projected_use_cents")
            )
            checked += 1
            derived = assess_adequacy(current, projected)
            if stated != derived:
                detail = (
                    f"{fmt(current)} remaining against {fmt(projected)} projected "
                    f"({fmt(headroom(current, projected))} of headroom)"
                )
                if stated not in ADEQUACY_VALUES:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(block, f"buckets/{label}/adequacy"),
                            f"{label} is assessed {stated!r}, which is not one of "
                            f"{ADEQUACY_VALUES}; the figures on the row give {derived!r} "
                            f"-- {detail}",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(block, f"buckets/{label}/adequacy"),
                            f"{label} is assessed {stated!r}; recomputing from the row gives "
                            f"{derived!r} -- {detail}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} adequacy assessments recompute from the balances behind them",
            )
        )
    return out


@check("adq_headroom_watch")
def check_adq_headroom_watch(ctx: Context) -> list[Finding]:
    """An adequate bucket whose headroom is inside the watch band is flagged.

    Deliberately a FLAG, not a failure: the bucket still covers what is projected
    against it. But a bucket whose projected use has reached the file's own watch
    share of the balance has one bad month of headroom left, and that is a
    conversation to have before the block says inadequate rather than after.
    Buckets with a malformed amount are left to the rollforward controls.
    """
    rule = "adq_headroom_watch"
    _sev(rule, Status.FLAG)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if block is None:
        return []
    band = ctx.watch_threshold_bps
    out: list[Finding] = []
    checked = 0
    for row in _blocks(ctx):
        label = _block_label(row)
        current = _int(row, "current_balance_cents")
        projected = _int(row, "projected_use_cents")
        if current is None or projected is None:
            continue
        checked += 1
        if within_watch_band(current, projected, band):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(block, f"buckets/{label}/projected_use_cents"),
                    f"{label} still covers its projection, with {fmt(headroom(current, projected))} "
                    f"of headroom on {fmt(current)} remaining; projected use has reached the "
                    f"{fmt_bps(band)} watch band and the bucket is one revision from inadequate",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} buckets hold headroom outside the {fmt_bps(band)} watch band",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the portfolio rollup foots from the blocks
# --------------------------------------------------------------------------- #
@check("rpt_portfolio_foots")
def check_rpt_portfolio_foots(ctx: Context) -> list[Finding]:
    """The portfolio rollup adds up to the per-project blocks.

    The rollup is the figure that reaches a board packet, and it is maintained
    beside the blocks rather than derived from them. Each total is re-added from
    the block rows and compared with exact ``==``.
    """
    rule = "rpt_portfolio_foots"
    _sev(rule, Status.FAIL)
    rollup = _rollup(ctx)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if rollup is None or block is None:
        return []
    labels = {
        "total_allocated_period_cents": "allocated this period",
        "total_current_balance_cents": "current contingency",
        "total_projected_use_cents": "projected potential use",
    }
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = recompute_rollup_totals(ctx)
        for key in ("total_allocated_period_cents", "total_current_balance_cents",
                    "total_projected_use_cents"):
            stated = require_cents(f"portfolio_rollup.{key}", rollup.get(key))
            if stated != derived[key]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollup, key),
                        f"the rollup states {fmt(stated)} of {labels[key]}; the "
                        f"{len(_blocks(ctx))} bucket(s) in the block foot to "
                        f"{fmt(derived[key])} (off by {fmt(stated - derived[key])})",
                    )
                )
        if not out:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"all {len(labels)} rollup totals foot to the {len(_blocks(ctx))} "
                    f"bucket(s) in the block",
                )
            )
    return out


@check("rpt_inadequate_count_ties")
def check_rpt_inadequate_count_ties(ctx: Context) -> list[Finding]:
    """The rollup's inadequate-bucket count ties the block.

    The count is what a reader looks at first, and a count maintained beside the
    block rather than derived from it drifts the first time an assessment moves
    and nobody re-adds the column.
    """
    rule = "rpt_inadequate_count_ties"
    _sev(rule, Status.FAIL)
    rollup = _rollup(ctx)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if rollup is None or block is None:
        return []
    counted = count_inadequate(ctx)
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "portfolio_rollup.inadequate_count",
            rollup.get("inadequate_count"),
            unit="a whole count",
        )
        if stated != counted:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, "inadequate_count"),
                    f"the rollup states {stated} inadequate bucket(s); the contingency block "
                    f"assesses {counted} as inadequate",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the rollup count of {counted} inadequate bucket(s) ties the block",
                )
            )
    return out


@check("rpt_watchlist_ties")
def check_rpt_watchlist_ties(ctx: Context) -> list[Finding]:
    """The exposure watchlist ties the contingency block.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a bucket not actually thin -- or omits one that is --
    sends the cost-control conversation to the wrong project. It is rebuilt from
    the block and compared.
    """
    rule = "rpt_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_EXPOSURE_WATCHLIST)
    block = ctx.one(DOC_CONTINGENCY_BLOCK)
    if watchlist is None or block is None:
        return []
    want = sorted(_normalize_entry(e) for e in recompute_watchlist(ctx, ctx.watch_threshold_bps))
    have = sorted(_normalize_entry(e) for e in _rows(watchlist, "entries"))
    out: list[Finding] = []
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}/{entry[1]}"),
                        f"the watchlist carries {entry[0]}/{entry[1]} as thin on headroom, but "
                        f"the block does not put it inside the watch band",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}/{entry[1]}"),
                        f"{entry[0]}/{entry[1]} sits inside the watch band in the block but is "
                        f"not on the exposure watchlist",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the exposure watchlist ties the contingency block")
        )
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
