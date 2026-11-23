"""
Financing Execution & Schedule-Variance control engine (READ-ONLY).
===================================================================

Loads each financing report (a ``.json`` file produced by
:mod:`financing_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the monthly "Upcoming Financings" report
reconciles to itself and to the month before it**, not whether any money moved.
Wire release, interest accrual and cash settlement are other engines' jobs. This
engine is the schedule-and-execution check: re-derive each milestone's variance,
tie this month's ``Prior`` column back to last month's ``Current`` column, hold
the ``Original`` baseline frozen, enforce the milestone playbook per financing
type, and gate on overdue milestones and a period-end report date.

The shape of the problem
------------------------
A capital-markets team publishes a monthly pipeline report: every active
financing is a workstream, typed as debt marketing, equity syndication or an
extension/refinancing, and each carries an ``Original | Prior | Current |
Variance`` block of milestone dates plus a summary Gantt.

Four failures hide inside that, and none of them look wrong in a spreadsheet: the
variance that no longer equals ``Current - Prior`` because a date was hand-edited;
the ``Prior`` column that no longer equals last month's ``Current`` or the
``Original`` baseline that was quietly overwritten; the workstream missing a
playbook milestone or a portfolio project with no workstream at all; and the
rollup count or Gantt bar that summarises the schedule on a figure nobody
recomputed from it.

The registry is organised around that:

1. ``set_``   -- is the financing report complete?
2. ``mem_``   -- is the workstream register sound, is each playbook defined and
                 complete, and does the report tie to the master portfolio?
3. ``var_``   -- does each variance, and each Gantt month, re-derive from the dates?
4. ``roll_``  -- does this month's Prior tie last month's Current?
5. ``base_``  -- is the Original baseline frozen across months?
6. ``date_``  -- is the report date the period-end, and does each overdue flag hold?
7. ``ord_``   -- are the milestones sequenced and their current dates non-decreasing?
8. ``rpt_``   -- do the rollup counts and the financing total recompute from the
                 workstreams they summarise?

Design notes
------------
- **Strictly read-only.** Financing reports are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every financing amount is compared with exact
  ``==``.
- **One derivation kernel.** Controls and the generator share the kernel in
  :mod:`financing_engine.schedule`, so a re-derived figure cannot disagree with
  the data that produced it.
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
    DOC_FINANCING_REPORT,
    DOC_GANTT_SUMMARY,
    DOC_MASTER_TRACKER,
    DOC_MILESTONE_SCHEDULE,
    DOC_PLAYBOOK_CATALOG,
    DOC_PRIOR_SCHEDULE,
    DOC_TYPES,
    DOC_WORKSTREAM_REGISTER,
    FINANCING_TYPES,
    STATUS_ACTIVE,
    STATUSES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents
from .schedule import gantt_month, is_overdue, period_end, variance_days

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~financing_engine.money.AmountInvalidError` as a finding."""
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
# Financing-report helpers
# --------------------------------------------------------------------------- #
def _workstreams(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_WORKSTREAM_REGISTER), "workstreams")


def _workstream_id(row: dict[str, Any]) -> str:
    value = row.get("workstream_id")
    return value if isinstance(value, str) and value else "?"


def _workstream_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _workstreams(ctx):
        wid = _workstream_id(row)
        if wid != "?" and wid not in out:
            out[wid] = row
    return out


def _milestones(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_MILESTONE_SCHEDULE), "milestones")


def _milestone_id(row: dict[str, Any]) -> str:
    value = row.get("milestone_id")
    return value if isinstance(value, str) and value else "?"


def _prior_milestones(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PRIOR_SCHEDULE), "prior_milestones")


def _prior_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _prior_milestones(ctx):
        mid = _milestone_id(row)
        if mid != "?" and mid not in out:
            out[mid] = row
    return out


def _playbooks(ctx: Context) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in _rows(ctx.one(DOC_PLAYBOOK_CATALOG), "playbooks"):
        ftype = _text(row, "financing_type")
        names = row.get("milestones")
        if ftype and ftype not in out and isinstance(names, list):
            out[ftype] = [n for n in names if isinstance(n, str)]
    return out


def _tracker_projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_MASTER_TRACKER), "projects")


def _gantt_bars(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_GANTT_SUMMARY), "bars")


def _milestones_for(ctx: Context, workstream_id: str) -> list[dict[str, Any]]:
    return [m for m in _milestones(ctx) if _text(m, "workstream_id") == workstream_id]


def _is_active(workstream: dict[str, Any] | None) -> bool:
    return workstream is not None and _text(workstream, "status") == STATUS_ACTIVE


# --------------------------------------------------------------------------- #
# Shared re-derivations (used by the generator too)
# --------------------------------------------------------------------------- #
def recompute_variance(milestone: dict[str, Any]) -> int | None:
    """The variance a milestone's dates imply, or ``None`` if a date is unreadable.

    Reads only the prior and current dates, never an amount, so re-deriving a
    variance cannot raise on a malformed limit.
    """
    prior = _parse_date(milestone.get("prior_date"))
    current = _parse_date(milestone.get("current_date"))
    if prior is None or current is None:
        return None
    return variance_days(prior, current)


def recompute_overdue(
    ctx: Context,
    milestone: dict[str, Any],
    workstream_map: dict[str, dict[str, Any]],
    report_date: date,
) -> bool | None:
    """Whether a milestone is overdue, or ``None`` if its current date is unreadable."""
    current = _parse_date(milestone.get("current_date"))
    if current is None:
        return None
    workstream = workstream_map.get(_text(milestone, "workstream_id") or "")
    return is_overdue(current, report_date, _is_active(workstream))


def recompute_overdue_count(ctx: Context, report_date: date) -> int:
    """The number of milestones the schedule implies are overdue."""
    workstream_map = _workstream_map(ctx)
    count = 0
    for milestone in _milestones(ctx):
        overdue = recompute_overdue(ctx, milestone, workstream_map, report_date)
        if overdue:
            count += 1
    return count


def recompute_active_count(ctx: Context) -> int:
    """The number of workstreams the register marks ACTIVE."""
    return sum(1 for w in _workstreams(ctx) if _is_active(w))


def recompute_financing_total(ctx: Context) -> int:
    """The sum of every ACTIVE workstream's financing amount, in integer cents.

    Raises :class:`AmountInvalidError` if an amount it must read is not integer
    cents; the calling control contains that.
    """
    total = 0
    for workstream in _workstreams(ctx):
        if not _is_active(workstream):
            continue
        total += require_cents(
            f"workstream[{_workstream_id(workstream)}].financing_amount_cents",
            workstream.get("financing_amount_cents"),
        )
    return total


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the financing report depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the financing report "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} financing-report artifacts are present",
            )
        )
    if _parse_date(ctx.report_date) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"report_date {ctx.report_date!r} is not a readable date; every overdue "
                f"and period-end test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# mem_ -- register soundness, playbook and portfolio completeness
# --------------------------------------------------------------------------- #
@check("mem_workstream_ids_unique")
def check_mem_workstream_ids_unique(ctx: Context) -> list[Finding]:
    """No workstream id appears twice.

    The workstream id joins the register to every milestone, to the Gantt and to
    the master tracker. A duplicate makes a milestone ambiguous about which
    financing it belongs to.
    """
    rule = "mem_workstream_ids_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WORKSTREAM_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _workstreams(ctx):
        seen[_workstream_id(row)] = seen.get(_workstream_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"workstreams/{wid}"),
            f"workstream id {wid} appears {count} times; a milestone that names it "
            f"cannot be attributed to one financing",
        )
        for wid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} workstream ids are unique")
        )
    return out


@check("mem_workstream_type_valid")
def check_mem_workstream_type_valid(ctx: Context) -> list[Finding]:
    """Every workstream carries a known financing type.

    The financing type is the key into the playbook catalog; an unknown one has no
    playbook, so nothing downstream could say what milestones that workstream was
    required to carry.
    """
    rule = "mem_workstream_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WORKSTREAM_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _workstreams(ctx):
        ftype = _text(row, "financing_type")
        if ftype not in FINANCING_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"workstreams/{_workstream_id(row)}/financing_type"),
                    f"workstream {_workstream_id(row)} is typed {ftype!r}, which is not one "
                    f"of {FINANCING_TYPES}; its playbook cannot be looked up",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_workstreams(ctx))} workstreams carry a known financing type",
            )
        )
    return out


@check("mem_workstream_status_valid")
def check_mem_workstream_status_valid(ctx: Context) -> list[Finding]:
    """Every workstream carries a known status.

    Status ``ACTIVE`` / ``CLOSED`` drives the overdue gate and the portfolio
    completeness check; an unknown status leaves both unable to say whether the
    financing is still live.
    """
    rule = "mem_workstream_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WORKSTREAM_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _workstreams(ctx):
        status = _text(row, "status")
        if status not in STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"workstreams/{_workstream_id(row)}/status"),
                    f"workstream {_workstream_id(row)} carries status {status!r}, which is "
                    f"not one of {STATUSES}; its overdue gate cannot be applied",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_workstreams(ctx))} workstreams carry a known status",
            )
        )
    return out


@check("mem_milestone_workstream_exists")
def check_mem_milestone_workstream_exists(ctx: Context) -> list[Finding]:
    """Every milestone names a workstream in the register."""
    rule = "mem_milestone_workstream_exists"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    workstreams = _workstream_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(schedule, f"milestones/{_milestone_id(row)}/workstream_id"),
            f"milestone {_milestone_id(row)} names workstream "
            f"{_text(row, 'workstream_id')!r}, which is not in the register",
        )
        for row in _milestones(ctx)
        if _text(row, "workstream_id")
        and _text(row, "workstream_id") not in workstreams
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every milestone names a workstream in the register"
            )
        )
    return out


@check("mem_playbook_defined")
def check_mem_playbook_defined(ctx: Context) -> list[Finding]:
    """Every financing type a workstream uses has a playbook in the catalog.

    Without the playbook the engine knows the workstream is (say) a debt marketing
    but not which milestones it must carry, so the completeness control would
    silently skip it. Workstreams whose type is itself unknown are left to
    ``mem_workstream_type_valid``.
    """
    rule = "mem_playbook_defined"
    _sev(rule, Status.FAIL)
    catalog = ctx.one(DOC_PLAYBOOK_CATALOG)
    if catalog is None:
        return []
    playbooks = _playbooks(ctx)
    out: list[Finding] = []
    checked = 0
    for workstream in _workstreams(ctx):
        ftype = _text(workstream, "financing_type")
        if ftype not in FINANCING_TYPES:
            continue  # mem_workstream_type_valid owns this
        checked += 1
        if ftype not in playbooks:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(catalog, f"playbooks/{ftype}"),
                    f"the playbook catalog has no entry for {ftype!r}, which workstream "
                    f"{_workstream_id(workstream)} is typed as; its milestone set cannot "
                    f"be enforced",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} workstream types have a playbook"
            )
        )
    return out


@check("mem_playbook_complete")
def check_mem_playbook_complete(ctx: Context) -> list[Finding]:
    """Every active workstream carries each milestone its playbook names.

    The playbook is the standardised milestone set for a financing type; a live
    workstream missing one of its milestones is a workstream whose deal team has a
    gap in the plan of record, and the missing step is exactly the one nobody is
    tracking.
    """
    rule = "mem_playbook_complete"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    playbooks = _playbooks(ctx)
    out: list[Finding] = []
    checked = 0
    for workstream in _workstreams(ctx):
        if not _is_active(workstream):
            continue
        ftype = _text(workstream, "financing_type")
        expected = playbooks.get(ftype or "")
        if expected is None:
            continue  # mem_playbook_defined owns this
        wid = _workstream_id(workstream)
        present = {_text(m, "name") for m in _milestones_for(ctx, wid)}
        for name in expected:
            checked += 1
            if name not in present:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"milestones/{wid}/{name}"),
                        f"active workstream {wid} ({ftype}) is missing playbook milestone "
                        f"{name!r}; its standard milestone set is incomplete",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} required playbook milestones are present"
            )
        )
    return out


@check("mem_portfolio_present")
def check_mem_portfolio_present(ctx: Context) -> list[Finding]:
    """Every active project on the master tracker appears as a workstream.

    The master tracker is the portfolio of record; an active financing that is on
    the tracker but has no workstream in this report is a deal the report simply
    forgot to cover.
    """
    rule = "mem_portfolio_present"
    _sev(rule, Status.FAIL)
    tracker = ctx.one(DOC_MASTER_TRACKER)
    if tracker is None:
        return []
    workstreams = _workstream_map(ctx)
    out: list[Finding] = []
    checked = 0
    for project in _tracker_projects(ctx):
        if _text(project, "status") != STATUS_ACTIVE:
            continue
        wid = _text(project, "workstream_id")
        checked += 1
        if not wid or wid not in workstreams:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(tracker, f"projects/{wid or '?'}"),
                    f"active portfolio project {_text(project, 'project')!r} ({wid}) has no "
                    f"workstream in the report; the financing is uncovered",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} active portfolio projects appear as workstreams",
            )
        )
    return out


@check("mem_workstream_in_tracker")
def check_mem_workstream_in_tracker(ctx: Context) -> list[Finding]:
    """Every workstream in the report is a project on the master tracker.

    The reverse of portfolio completeness: a workstream that is not on the tracker
    is a financing the report is tracking off the books, outside the portfolio of
    record.
    """
    rule = "mem_workstream_in_tracker"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_WORKSTREAM_REGISTER)
    tracker = ctx.one(DOC_MASTER_TRACKER)
    if register is None or tracker is None:
        return []
    tracked = {
        _text(p, "workstream_id")
        for p in _tracker_projects(ctx)
        if _text(p, "workstream_id")
    }
    out: list[Finding] = []
    for workstream in _workstreams(ctx):
        wid = _workstream_id(workstream)
        if wid not in tracked:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"workstreams/{wid}"),
                    f"workstream {wid} is not on the master tracker; it is being reported "
                    f"outside the portfolio of record",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_workstreams(ctx))} workstreams appear on the master tracker",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# var_ -- variance and Gantt re-derivation
# --------------------------------------------------------------------------- #
@check("var_dates_wellformed")
def check_var_dates_wellformed(ctx: Context) -> list[Finding]:
    """Every milestone carries readable Original, Prior and Current dates.

    Every variance, roll-forward, baseline and ordering test reads these three
    dates; an unreadable one makes all of them meaningless, so this owns the
    malformed-date finding and the others defer to it.
    """
    rule = "var_dates_wellformed"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    for row in _milestones(ctx):
        bad = [
            field
            for field in ("original_date", "prior_date", "current_date")
            if _parse_date(row.get(field)) is None
        ]
        if bad:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{_milestone_id(row)}"),
                    f"milestone {_milestone_id(row)} has unreadable {', '.join(bad)}; its "
                    f"variance and roll-forward cannot be re-derived",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_milestones(ctx))} milestones carry readable dates",
            )
        )
    return out


@check("var_recomputes")
def check_var_recomputes(ctx: Context) -> list[Finding]:
    """Each milestone's stated Variance equals ``Current - Prior`` in days.

    Compared with exact ``==``: the variance is the report's own claim about how
    far a milestone slipped, and a variance that no longer matches its dates is a
    number the deal team reads and trusts while it silently lies.
    """
    rule = "var_recomputes"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _milestones(ctx):
        recomputed = recompute_variance(row)
        if recomputed is None:
            continue  # var_dates_wellformed owns this
        stated = _int(row, "variance_days")
        if stated is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{_milestone_id(row)}/variance_days"),
                    f"milestone {_milestone_id(row)} states a non-integer variance "
                    f"{row.get('variance_days')!r}; the variance is a whole day count",
                )
            )
            continue
        checked += 1
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{_milestone_id(row)}/variance_days"),
                    f"milestone {_milestone_id(row)} states variance {stated} day(s); its "
                    f"Prior->Current dates re-derive {recomputed}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} milestone variances re-derive"
            )
        )
    return out


@check("var_gantt_month_recomputes")
def check_var_gantt_month_recomputes(ctx: Context) -> list[Finding]:
    """Each summary Gantt bar sits in the month of its target closing.

    The bar's month is meant to be ``MONTH(Target Closing)``; a bar drawn in a
    different month tells a reviewer the deal closes when it does not.
    """
    rule = "var_gantt_month_recomputes"
    _sev(rule, Status.FAIL)
    gantt = ctx.one(DOC_GANTT_SUMMARY)
    if gantt is None:
        return []
    out: list[Finding] = []
    checked = 0
    for bar in _gantt_bars(ctx):
        target = _parse_date(bar.get("target_closing"))
        wid = _text(bar, "workstream_id") or "?"
        if target is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gantt, f"bars/{wid}/target_closing"),
                    f"Gantt bar {wid} has an unreadable target_closing "
                    f"{bar.get('target_closing')!r}; its month cannot be re-derived",
                )
            )
            continue
        stated = _int(bar, "gantt_month")
        if stated is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gantt, f"bars/{wid}/gantt_month"),
                    f"Gantt bar {wid} states a non-integer month {bar.get('gantt_month')!r}",
                )
            )
            continue
        checked += 1
        expected = gantt_month(target)
        if stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gantt, f"bars/{wid}/gantt_month"),
                    f"Gantt bar {wid} is placed in month {stated}; its target closing "
                    f"{target.isoformat()} re-derives month {expected}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} Gantt bars sit in their closing month"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# roll_ -- month-over-month roll-forward
# --------------------------------------------------------------------------- #
@check("roll_prior_ties_current")
def check_roll_prior_ties_current(ctx: Context) -> list[Finding]:
    """This month's Prior date equals last month's Current date, per milestone.

    The ``Prior`` column is meant to be a verbatim carry of last month's
    ``Current`` column; when it does not tie, the month-over-month chain is broken
    and every variance measured against it is measured off a date that was never
    reported.
    """
    rule = "roll_prior_ties_current"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    prior_doc = ctx.one(DOC_PRIOR_SCHEDULE)
    if schedule is None or prior_doc is None:
        return []
    prior_map = _prior_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _milestones(ctx):
        mid = _milestone_id(row)
        this_prior = _parse_date(row.get("prior_date"))
        if this_prior is None:
            continue  # var_dates_wellformed owns this
        last = prior_map.get(mid)
        if last is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(prior_doc, f"prior_milestones/{mid}"),
                    f"milestone {mid} has no prior-schedule row; this month's Prior date "
                    f"cannot be tied back to last month's Current",
                )
            )
            continue
        last_current = _parse_date(last.get("current_date"))
        if last_current is None:
            continue
        checked += 1
        if this_prior != last_current:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{mid}/prior_date"),
                    f"milestone {mid} carries Prior {this_prior.isoformat()}, but last "
                    f"month's Current was {last_current.isoformat()}; the roll-forward is "
                    f"broken",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} milestones tie Prior to last Current"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# base_ -- the Original baseline is frozen
# --------------------------------------------------------------------------- #
@check("base_original_immutable")
def check_base_original_immutable(ctx: Context) -> list[Finding]:
    """Each milestone's Original date is unchanged from last month.

    The ``Original`` column is the frozen baseline the whole slippage story is
    measured against; a mutated Original quietly re-bases the deal so a slipped
    milestone reads as on-plan.
    """
    rule = "base_original_immutable"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    prior_doc = ctx.one(DOC_PRIOR_SCHEDULE)
    if schedule is None or prior_doc is None:
        return []
    prior_map = _prior_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _milestones(ctx):
        mid = _milestone_id(row)
        this_original = _parse_date(row.get("original_date"))
        if this_original is None:
            continue  # var_dates_wellformed owns this
        last = prior_map.get(mid)
        if last is None:
            continue  # roll_prior_ties_current owns the missing prior row
        last_original = _parse_date(last.get("original_date"))
        if last_original is None:
            continue
        checked += 1
        if this_original != last_original:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{mid}/original_date"),
                    f"milestone {mid} carries Original {this_original.isoformat()}, but the "
                    f"frozen baseline was {last_original.isoformat()}; the baseline has been "
                    f"mutated",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} milestone baselines are unchanged"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# date_ -- the report date gate and the overdue flag
# --------------------------------------------------------------------------- #
@check("date_report_is_period_end")
def check_date_report_is_period_end(ctx: Context) -> list[Finding]:
    """The report date is the last calendar day of the report period.

    The report is a period-end snapshot, so its date must be the last day of the
    period month; a report dated mid-month is measuring overdue milestones against
    the wrong line.
    """
    rule = "date_report_is_period_end"
    _sev(rule, Status.FAIL)
    report_date = _parse_date(ctx.report_date)
    if report_date is None:
        return []  # set_complete owns the unreadable report date
    expected = period_end(ctx.period)
    if expected is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"period {ctx.period!r} is not a readable YYYY-MM label; the period-end "
                f"date cannot be derived",
            )
        ]
    if report_date != expected:
        return [
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"report_date {report_date.isoformat()} is not the period-end for "
                f"{ctx.period}; the last day of the period is {expected.isoformat()}",
            )
        ]
    return [
        Finding(
            rule,
            Status.PASS,
            "-",
            f"report_date {report_date.isoformat()} is the period-end for {ctx.period}",
        )
    ]


@check("date_overdue_flag")
def check_date_overdue_flag(ctx: Context) -> list[Finding]:
    """Each milestone's stated overdue flag matches the date gate.

    Deliberately a FLAG, not a failure: an overdue milestone is a live signal for
    the deal team, not a broken report. The gate is ``ACTIVE and Current <
    ReportDate``, recomputed and compared to the flag on the row so a slipped
    milestone cannot hide behind a stale flag.
    """
    rule = "date_overdue_flag"
    _sev(rule, Status.FLAG)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    report_date = _parse_date(ctx.report_date)
    if schedule is None or report_date is None:
        return []
    workstream_map = _workstream_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _milestones(ctx):
        recomputed = recompute_overdue(ctx, row, workstream_map, report_date)
        if recomputed is None:
            continue  # var_dates_wellformed owns this
        checked += 1
        stated = bool(row.get("overdue"))
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(schedule, f"milestones/{_milestone_id(row)}/overdue"),
                    f"milestone {_milestone_id(row)} is flagged overdue={stated}; the date "
                    f"gate against {report_date.isoformat()} re-derives overdue={recomputed}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} overdue flags match the date gate"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# ord_ -- sequencing and ordering
# --------------------------------------------------------------------------- #
@check("ord_sequence_unique")
def check_ord_sequence_unique(ctx: Context) -> list[Finding]:
    """No two milestones in a workstream share a sequence number.

    The sequence number is what orders a workstream's milestones; a duplicate
    makes the order ambiguous and the non-decreasing check below unable to say
    which milestone comes first.
    """
    rule = "ord_sequence_unique"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    seen: dict[tuple[str, int], int] = {}
    for row in _milestones(ctx):
        wid = _text(row, "workstream_id")
        seq = _int(row, "sequence")
        if wid and seq is not None:
            key = (wid, seq)
            seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(schedule, f"milestones/{wid}/sequence/{seq}"),
            f"workstream {wid} has {count} milestones at sequence {seq}; their order is "
            f"ambiguous",
        )
        for (wid, seq), count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(seen)} workstream sequence numbers are unique"
            )
        )
    return out


@check("ord_current_nondecreasing")
def check_ord_current_nondecreasing(ctx: Context) -> list[Finding]:
    """Within a workstream, milestone Current dates do not run backwards.

    Milestones are an ordered plan: a later milestone dated before an earlier one
    is a schedule that has a step happening before its own predecessor, which no
    real timeline does.
    """
    rule = "ord_current_nondecreasing"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    by_ws: dict[str, list[tuple[int, date, str]]] = {}
    for row in _milestones(ctx):
        wid = _text(row, "workstream_id")
        seq = _int(row, "sequence")
        current = _parse_date(row.get("current_date"))
        if wid and seq is not None and current is not None:
            by_ws.setdefault(wid, []).append((seq, current, _milestone_id(row)))
    out: list[Finding] = []
    checked = 0
    for wid, rows in sorted(by_ws.items()):
        ordered = sorted(rows, key=lambda t: (t[0], t[2]))
        for (prev_seq, prev_cur, _prev_id), (seq, cur, mid) in zip(ordered, ordered[1:]):
            checked += 1
            if cur < prev_cur:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"milestones/{mid}/current_date"),
                        f"workstream {wid} milestone {mid} (seq {seq}) is dated "
                        f"{cur.isoformat()}, before its predecessor seq {prev_seq} at "
                        f"{prev_cur.isoformat()}; the schedule runs backwards",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} milestone handovers run forwards"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the schedule
# --------------------------------------------------------------------------- #
@check("rpt_active_count_ties")
def check_rpt_active_count_ties(ctx: Context) -> list[Finding]:
    """The report's active-financing count equals the ACTIVE workstreams.

    The headline count of live financings is a number that reaches a committee; a
    count maintained beside the register rather than derived from it drifts the
    first time a workstream closes and nobody re-adds the column.
    """
    rule = "rpt_active_count_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_FINANCING_REPORT)
    register = ctx.one(DOC_WORKSTREAM_REGISTER)
    if report is None or register is None:
        return []
    recomputed = recompute_active_count(ctx)
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "financing_report.active_count",
            report.get("active_count"),
            unit="a whole count",
        )
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "active_count"),
                    f"the report states {stated} active financing(s); the register recomputes "
                    f"{recomputed}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the active count of {recomputed} ties the register",
                )
            )
    return out


@check("rpt_overdue_count_ties")
def check_rpt_overdue_count_ties(ctx: Context) -> list[Finding]:
    """The report's overdue-milestone count equals the recomputed date gate.

    The overdue count is what tells a reader how much of the pipeline has slipped
    past the report date; a stated count that no longer matches the schedule
    understates or overstates the slippage the report exists to surface.
    """
    rule = "rpt_overdue_count_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_FINANCING_REPORT)
    report_date = _parse_date(ctx.report_date)
    if report is None or report_date is None:
        return []
    recomputed = recompute_overdue_count(ctx, report_date)
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "financing_report.overdue_count",
            report.get("overdue_count"),
            unit="a whole count",
        )
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "overdue_count"),
                    f"the report states {stated} overdue milestone(s); the schedule recomputes "
                    f"{recomputed} against {report_date.isoformat()}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the overdue count of {recomputed} ties the schedule",
                )
            )
    return out


@check("rpt_financing_total_ties")
def check_rpt_financing_total_ties(ctx: Context) -> list[Finding]:
    """The report's financing total equals the sum of active financing amounts.

    Compared with exact ``==`` on integer cents: the total capital in flight is
    the figure a treasurer plans around, and a total that does not tie the sum of
    the live workstreams is a planning number the register no longer supports.
    """
    rule = "rpt_financing_total_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_FINANCING_REPORT)
    register = ctx.one(DOC_WORKSTREAM_REGISTER)
    if report is None or register is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        recomputed = recompute_financing_total(ctx)
        stated = require_cents(
            "financing_report.total_financing_cents",
            report.get("total_financing_cents"),
        )
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "total_financing_cents"),
                    f"the report states a financing total of {fmt(stated)}; the active "
                    f"workstreams sum to {fmt(recomputed)} "
                    f"(off by {fmt(stated - recomputed)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the financing total of {fmt(recomputed)} ties the register",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one financing report."""
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
    """Analyze every ``.json`` financing report in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of financing-report reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
