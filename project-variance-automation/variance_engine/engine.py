"""
Project variance and business-plan compare control engine (READ-ONLY).
======================================================================

Loads each project report (a ``.json`` file produced by
:mod:`variance_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the periodic project report foots to the figures
underneath it**, not whether the proforma behind those figures is a good
proforma. Underwriting a development is somebody else's question. This engine is
the restatement check that runs before the report goes out.

The shape of the problem
------------------------
On a fixed periodic calendar every development project's proforma is re-issued as
a project report. Dedicated tabs restate the current period against the prior
period and against the approved Business Plan baseline -- gross revenue, net
project revenue, total project expense, project profit, margin on cost and
project IRR -- while a budget-variance tab breaks each cost line into Total
Budget / Cost to Date / Cost to Complete and a milestone block reports each
schedule date Current vs Prior vs Variance, ``+`` meaning ahead, against a frozen
baseline schedule.

Three failures hide inside that, and none of them look wrong in a tidy grid: the
variance column carried forward rather than derived, so it no longer equals the
difference of the two columns it sits between; the Cost to Complete maintained
beside the budget rather than struck as Total Budget less Cost to Date, so an
overrun rides in a column nobody re-footed; and the Business Plan column quietly
re-based to a revision nobody approved, which makes every plan variance smaller
at once.

The registry is organised around that:

1. ``set_``  -- is the project report complete?
2. ``prj_``  -- is the project register sound, and does every project have its
   two comparatives?
3. ``bud_``  -- is the budget-variance tab well-formed, and is Cost to Complete
   the remainder?
4. ``eco_``  -- do the current-period economics re-derive from their own inputs?
5. ``var_``  -- do the comparative columns foot internally, do the variance
   columns re-foot, and is the plan column the frozen approved plan?
6. ``mst_``  -- do the milestone variances re-derive with the right sign, and
   what has slipped past tolerance?
7. ``rpt_``  -- does the report rollup foot across all projects?

Design notes
------------
- **Strictly read-only.** Project reports are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every figure is compared with exact ``==``.
- **One restatement kernel.** Controls and the generator share
  :mod:`variance_engine.variance`, so a variance cannot disagree with the data
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

from .model import (
    COST_CATEGORIES,
    DOC_BUDGET_VARIANCE,
    DOC_CURRENT_ECONOMICS,
    DOC_MILESTONE_SCHEDULE,
    DOC_PLAN_BASELINE,
    DOC_PRIOR_ECONOMICS,
    DOC_PROJECT_REGISTER,
    DOC_REPORT_ROLLUP,
    DOC_SLIPPAGE_WATCHLIST,
    DOC_TYPES,
    DOC_VARIANCE_SUMMARY,
    METRIC_FIELDS,
    MILESTONE_NAMES,
    PROJECT_TYPES,
    UNIT_BPS,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents
from .variance import (
    behind_beyond_tolerance,
    cost_to_complete_cents,
    margin_on_cost_bps,
    milestone_variance_days,
    net_project_revenue_cents,
    project_profit_cents,
    variance,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~variance_engine.money.AmountInvalidError` as a finding."""
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


def _unit_label(unit: str) -> str:
    """What ``require_cents`` should say a metric field was expected to hold."""
    return "integer basis points" if unit == UNIT_BPS else "integer cents"


def _show(value: int, unit: str) -> str:
    """Render a metric value in its own unit for a finding message."""
    return fmt_bps(value) if unit == UNIT_BPS else fmt(value)


# --------------------------------------------------------------------------- #
# Project-report helpers
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


def _cost_lines(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_BUDGET_VARIANCE), "cost_lines")


def _line_id(row: dict[str, Any]) -> str:
    value = row.get("line_id")
    return value if isinstance(value, str) and value else "?"


def _lines_for(ctx: Context, project_id: str) -> list[dict[str, Any]]:
    return [line for line in _cost_lines(ctx) if _text(line, "project_id") == project_id]


def _current_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CURRENT_ECONOMICS), "projects")


def _prior_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PRIOR_ECONOMICS), "projects")


def _plan_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PLAN_BASELINE), "projects")


def _economics_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        pid = _text(row, "project_id")
        if pid and pid not in out:
            out[pid] = row
    return out


def _milestones(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_MILESTONE_SCHEDULE), "milestones")


def _milestone_id(row: dict[str, Any]) -> str:
    value = row.get("milestone_id")
    return value if isinstance(value, str) and value else "?"


def _variance_summary_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_VARIANCE_SUMMARY), "rows")


def _ordered_project_ids(ctx: Context) -> list[str]:
    """Distinct project ids in register order.

    Register order is report order, and a duplicated row must not double a
    project in anything derived from the register -- ``prj_unique_ids`` owns the
    duplicate itself.
    """
    seen: list[str] = []
    for row in _projects(ctx):
        pid = _project_id(row)
        if pid != "?" and pid not in seen:
            seen.append(pid)
    return seen


# --------------------------------------------------------------------------- #
# Re-derivation, shared with the generator
# --------------------------------------------------------------------------- #
def recompute_cost_to_complete(line: dict[str, Any]) -> int:
    """Cost to Complete for one cost line: Total Budget less Cost to Date.

    Raises :class:`AmountInvalidError` if either figure is not integer cents.
    """
    budget = require_cents(
        f"cost_line[{_line_id(line)}].total_budget_cents", line.get("total_budget_cents")
    )
    to_date = require_cents(
        f"cost_line[{_line_id(line)}].cost_to_date_cents", line.get("cost_to_date_cents")
    )
    return cost_to_complete_cents(budget, to_date)


def recompute_project_expense(ctx: Context, project_id: str) -> int:
    """Total project expense re-footed from the project's own budget lines.

    Raises :class:`AmountInvalidError` if a Total Budget is not integer cents.
    """
    return sum(
        require_cents(
            f"cost_line[{_line_id(line)}].total_budget_cents",
            line.get("total_budget_cents"),
        )
        for line in _lines_for(ctx, project_id)
    )


def recompute_net_revenue(row: dict[str, Any], label: str) -> int:
    """Net project revenue for one economics row: gross less deductions."""
    gross = require_cents(f"{label}.gross_revenue_cents", row.get("gross_revenue_cents"))
    deduction = require_cents(
        f"{label}.revenue_deduction_cents", row.get("revenue_deduction_cents")
    )
    return net_project_revenue_cents(gross, deduction)


def recompute_profit(row: dict[str, Any], label: str) -> int:
    """Project profit for one economics row: stated net revenue less stated expense.

    The *stated* net revenue is used deliberately. Whether that net revenue is
    itself the right figure belongs to ``eco_net_revenue_foots``; a profit control
    that silently re-derived its own net revenue would report the same break twice
    and leave the reader unable to tell which column moved.
    """
    net = require_cents(
        f"{label}.net_project_revenue_cents", row.get("net_project_revenue_cents")
    )
    expense = require_cents(
        f"{label}.total_project_expense_cents", row.get("total_project_expense_cents")
    )
    return project_profit_cents(net, expense)


def recompute_margin(row: dict[str, Any], label: str) -> int | None:
    """Margin on cost for one economics row, from the same inputs as the profit.

    Returns ``None`` when the expense is zero or negative: there is no cost to
    strike a margin on, and the control skips the row rather than inventing a
    denominator.
    """
    expense = require_cents(
        f"{label}.total_project_expense_cents", row.get("total_project_expense_cents")
    )
    return margin_on_cost_bps(recompute_profit(row, label), expense)


def recompute_milestone_variances(
    milestone: dict[str, Any],
) -> tuple[int | None, int | None]:
    """``(variance vs prior, variance vs baseline)`` in days, ``+`` = ahead.

    Either element is ``None`` when the date it needs is unreadable; the
    completeness control owns that, so the arithmetic controls skip the row.
    """
    current = _parse_date(milestone.get("current_date"))
    prior = _parse_date(milestone.get("prior_date"))
    baseline = _parse_date(milestone.get("baseline_date"))
    vs_prior = (
        milestone_variance_days(current, prior)
        if current is not None and prior is not None
        else None
    )
    vs_baseline = (
        milestone_variance_days(current, baseline)
        if current is not None and baseline is not None
        else None
    )
    return vs_prior, vs_baseline


def recompute_variance_rows(ctx: Context) -> list[dict[str, Any]]:
    """The variance tab re-derived from the three economics documents.

    One row per (project, metric) for every project that carries all three
    columns. A project missing a comparative is skipped here and reported by
    ``prj_comparatives_present``, so the variance controls never compare a column
    against a column that does not exist.

    Raises :class:`AmountInvalidError` if a metric it must read is malformed.
    """
    current = _economics_map(_current_rows(ctx))
    prior = _economics_map(_prior_rows(ctx))
    plan = _economics_map(_plan_rows(ctx))
    out: list[dict[str, Any]] = []
    for pid in _ordered_project_ids(ctx):
        if pid not in current or pid not in prior or pid not in plan:
            continue
        for metric, field_name, unit in METRIC_FIELDS:
            unit_label = _unit_label(unit)
            current_value = require_cents(
                f"current[{pid}].{field_name}",
                current[pid].get(field_name),
                unit=unit_label,
            )
            prior_value = require_cents(
                f"prior[{pid}].{field_name}", prior[pid].get(field_name), unit=unit_label
            )
            plan_value = require_cents(
                f"plan[{pid}].{field_name}", plan[pid].get(field_name), unit=unit_label
            )
            out.append(
                {
                    "project_id": pid,
                    "metric": metric,
                    "unit": unit,
                    "current_value": current_value,
                    "prior_value": prior_value,
                    "plan_value": plan_value,
                    "variance_vs_prior": variance(current_value, prior_value),
                    "variance_vs_plan": variance(current_value, plan_value),
                }
            )
    return out


def recompute_slippage_watchlist(
    ctx: Context, as_of: date, tolerance_days: int
) -> list[dict[str, Any]]:
    """Milestones still ahead of the report date and behind the frozen baseline.

    A milestone whose current date has already passed the report date is history;
    the chase is for the dates still in front of the team. Reads no amounts, so it
    never raises on a malformed figure.
    """
    entries: list[dict[str, Any]] = []
    for milestone in _milestones(ctx):
        baseline = _parse_date(milestone.get("baseline_date"))
        current = _parse_date(milestone.get("current_date"))
        if baseline is None or current is None or current <= as_of:
            continue
        days = milestone_variance_days(current, baseline)
        if behind_beyond_tolerance(days, tolerance_days):
            entries.append(
                {
                    "milestone_id": _milestone_id(milestone),
                    "project_id": _text(milestone, "project_id"),
                    "milestone_name": _text(milestone, "milestone_name"),
                    "baseline_date": milestone.get("baseline_date"),
                    "current_date": milestone.get("current_date"),
                    "variance_baseline_days": days,
                }
            )
    entries.sort(key=lambda e: (e["milestone_id"], e["project_id"] or ""))
    return entries


def recompute_rollup(ctx: Context) -> dict[str, int]:
    """The report rollup re-footed across every current-period project row.

    Raises :class:`AmountInvalidError` if a figure it must add is malformed.
    """
    rows = _current_rows(ctx)
    totals = {
        "project_count": len(rows),
        "total_gross_revenue_cents": 0,
        "total_net_project_revenue_cents": 0,
        "total_project_expense_cents": 0,
        "total_project_profit_cents": 0,
    }
    for row in rows:
        pid = _text(row, "project_id") or "?"
        totals["total_gross_revenue_cents"] += require_cents(
            f"current[{pid}].gross_revenue_cents", row.get("gross_revenue_cents")
        )
        totals["total_net_project_revenue_cents"] += require_cents(
            f"current[{pid}].net_project_revenue_cents",
            row.get("net_project_revenue_cents"),
        )
        totals["total_project_expense_cents"] += require_cents(
            f"current[{pid}].total_project_expense_cents",
            row.get("total_project_expense_cents"),
        )
        totals["total_project_profit_cents"] += require_cents(
            f"current[{pid}].project_profit_cents", row.get("project_profit_cents")
        )
    return totals


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("milestone_id"),
        entry.get("project_id"),
        entry.get("milestone_name"),
        entry.get("baseline_date"),
        entry.get("current_date"),
        entry.get("variance_baseline_days"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the project report depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the project report "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} project-report artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every schedule test is "
                f"measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# prj_ -- the project register and its comparatives
# --------------------------------------------------------------------------- #
@check("prj_unique_ids")
def check_prj_unique_ids(ctx: Context) -> list[Finding]:
    """No project id appears twice in the register.

    The project id joins the register to the budget tab, all three economics
    columns and the milestone block. A duplicate makes a cost line ambiguous about
    which project it belongs to.
    """
    rule = "prj_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _projects(ctx):
        pid = _project_id(row)
        seen[pid] = seen.get(pid, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"projects/{pid}"),
            f"project id {pid} appears {count} times in the register; a cost line or "
            f"milestone that names it cannot be attributed to one project",
        )
        for pid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(seen)} project ids in the register are unique"
            )
        )
    return out


@check("prj_type_valid")
def check_prj_type_valid(ctx: Context) -> list[Finding]:
    """Every project carries a known development product type.

    The product type is how a reader knows which revenue line a project even has;
    an unrecognised one means the report is restating something the reporting
    convention does not describe.
    """
    rule = "prj_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _projects(ctx):
        ptype = _text(row, "project_type")
        if ptype not in PROJECT_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{_project_id(row)}/project_type"),
                    f"project {_project_id(row)} is typed {ptype!r}, which is not one of "
                    f"{PROJECT_TYPES}; the reporting convention does not describe it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_projects(ctx))} projects carry a known product type",
            )
        )
    return out


@check("prj_comparatives_present")
def check_prj_comparatives_present(ctx: Context) -> list[Finding]:
    """Every project has a current, a prior and a Business Plan column.

    A restatement needs something to restate against. A project with no prior row
    or no plan row has no variance to report, and a variance tab that quietly
    omits it lets the project disappear from the comparison rather than showing an
    empty column. Where all three columns exist, the variance tab must carry every
    metric for that project.
    """
    rule = "prj_comparatives_present"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    summary = ctx.one(DOC_VARIANCE_SUMMARY)
    if register is None or summary is None:
        return []
    current = _economics_map(_current_rows(ctx))
    prior = _economics_map(_prior_rows(ctx))
    plan = _economics_map(_plan_rows(ctx))
    stated = {
        (r.get("project_id"), r.get("metric")) for r in _variance_summary_rows(ctx)
    }
    out: list[Finding] = []
    checked = 0
    for pid in _ordered_project_ids(ctx):
        missing = [
            label
            for label, source in (
                ("current period", current),
                ("prior period", prior),
                ("business plan", plan),
            )
            if pid not in source
        ]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{pid}"),
                    f"project {pid} has no {' and no '.join(missing)} column; there is "
                    f"nothing for the variance tab to restate it against",
                )
            )
            continue
        checked += 1
        absent = [
            metric for metric, _f, _u in METRIC_FIELDS if (pid, metric) not in stated
        ]
        if absent:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, f"rows/{pid}"),
                    f"project {pid} carries all three columns but the variance tab omits "
                    f"{absent}; the metric drops out of the comparison unseen",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} projects carry a current, prior and business-plan column",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# bud_ -- the budget-variance tab
# --------------------------------------------------------------------------- #
@check("bud_line_required_fields")
def check_bud_line_required_fields(ctx: Context) -> list[Finding]:
    """Every cost line carries the descriptive fields the controls read."""
    rule = "bud_line_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BUDGET_VARIANCE)
    if register is None:
        return []
    required = ("line_id", "project_id", "cost_category")
    out: list[Finding] = []
    for row in _cost_lines(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"cost_lines/{_line_id(row)}"),
                    f"cost line {_line_id(row)} is missing {', '.join(missing)}; the "
                    f"budget tab cannot place it on a project",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_cost_lines(ctx))} cost lines carry their required fields",
            )
        )
    return out


@check("bud_category_valid")
def check_bud_category_valid(ctx: Context) -> list[Finding]:
    """Every cost line sits in a known budget category.

    Categories are how the budget tab subtotals; a line in an unrecognised one is
    money in the total that no subtotal ever shows, which is how a cost stops
    being reviewed while still being spent.
    """
    rule = "bud_category_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BUDGET_VARIANCE)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"cost_lines/{_line_id(row)}/cost_category"),
            f"cost line {_line_id(row)} sits in category "
            f"{_text(row, 'cost_category')!r}, which is not one of {COST_CATEGORIES}",
        )
        for row in _cost_lines(ctx)
        if _text(row, "cost_category")
        and _text(row, "cost_category") not in COST_CATEGORIES
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_cost_lines(ctx))} cost lines sit in a known budget category",
            )
        )
    return out


@check("bud_project_exists")
def check_bud_project_exists(ctx: Context) -> list[Finding]:
    """Every cost line names a project in the register.

    A line pointing at a project the report does not carry is budget that reaches
    no project total, so the expense it represents is invisible to every column
    that matters.
    """
    rule = "bud_project_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BUDGET_VARIANCE)
    if register is None:
        return []
    projects = _project_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"cost_lines/{_line_id(row)}/project_id"),
            f"cost line {_line_id(row)} names project {_text(row, 'project_id')!r}, "
            f"which is not in the project register",
        )
        for row in _cost_lines(ctx)
        if _text(row, "project_id") and _text(row, "project_id") not in projects
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every cost line names a project in the register"
            )
        )
    return out


@check("bud_cost_to_complete_foots")
def check_bud_cost_to_complete_foots(ctx: Context) -> list[Finding]:
    """Cost to Complete is Total Budget less Cost to Date, on every cost line.

    This is the control the budget tab exists for. Cost to Complete has exactly
    one definition, and a column maintained beside the budget rather than struck
    from it is an overrun that has not been reported yet: the project shows budget
    remaining it has already spent.
    """
    rule = "bud_cost_to_complete_foots"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BUDGET_VARIANCE)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _cost_lines(ctx):
        with amount_guard(rule, out):
            derived = recompute_cost_to_complete(row)
            stated = require_cents(
                f"cost_line[{_line_id(row)}].cost_to_complete_cents",
                row.get("cost_to_complete_cents"),
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register, f"cost_lines/{_line_id(row)}/cost_to_complete_cents"
                        ),
                        f"cost line {_line_id(row)} states cost to complete "
                        f"{fmt(stated)}; total budget less cost to date is "
                        f"{fmt(derived)} (out by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} cost lines foot to total budget less cost to date",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# eco_ -- the current-period economics
# --------------------------------------------------------------------------- #
@check("eco_net_revenue_foots")
def check_eco_net_revenue_foots(ctx: Context) -> list[Finding]:
    """Net project revenue is gross revenue less the revenue deductions."""
    rule = "eco_net_revenue_foots"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_CURRENT_ECONOMICS)
    if doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _current_rows(ctx):
        pid = _text(row, "project_id") or "?"
        with amount_guard(rule, out):
            derived = recompute_net_revenue(row, f"current[{pid}]")
            stated = require_cents(
                f"current[{pid}].net_project_revenue_cents",
                row.get("net_project_revenue_cents"),
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(doc, f"projects/{pid}/net_project_revenue_cents"),
                        f"project {pid} states net project revenue {fmt(stated)}; gross "
                        f"revenue less deductions is {fmt(derived)} "
                        f"(out by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} current net project revenues foot to gross less deductions",
            )
        )
    return out


@check("eco_expense_foots_budget")
def check_eco_expense_foots_budget(ctx: Context) -> list[Finding]:
    """Total project expense foots the project's own budget lines.

    The economics tab and the budget tab are two renderings of the same money, and
    they are keyed by hand in different places. A total project expense that no
    longer adds up the Total Budget column is the point where the two tabs stop
    describing the same project.
    """
    rule = "eco_expense_foots_budget"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_CURRENT_ECONOMICS)
    budget = ctx.one(DOC_BUDGET_VARIANCE)
    if doc is None or budget is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _current_rows(ctx):
        pid = _text(row, "project_id") or "?"
        lines = _lines_for(ctx, pid)
        if not lines:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(budget, f"cost_lines/{pid}"),
                    f"project {pid} reports a total project expense but the budget tab "
                    f"carries no cost line for it; the expense cannot be re-footed",
                )
            )
            continue
        with amount_guard(rule, out):
            derived = recompute_project_expense(ctx, pid)
            stated = require_cents(
                f"current[{pid}].total_project_expense_cents",
                row.get("total_project_expense_cents"),
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(doc, f"projects/{pid}/total_project_expense_cents"),
                        f"project {pid} states total project expense {fmt(stated)}; its "
                        f"{len(lines)} budget lines total {fmt(derived)} "
                        f"(out by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} project expenses foot the total budget column",
            )
        )
    return out


@check("eco_profit_foots")
def check_eco_profit_foots(ctx: Context) -> list[Finding]:
    """Project profit is net project revenue less total project expense."""
    rule = "eco_profit_foots"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_CURRENT_ECONOMICS)
    if doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _current_rows(ctx):
        pid = _text(row, "project_id") or "?"
        with amount_guard(rule, out):
            derived = recompute_profit(row, f"current[{pid}]")
            stated = require_cents(
                f"current[{pid}].project_profit_cents", row.get("project_profit_cents")
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(doc, f"projects/{pid}/project_profit_cents"),
                        f"project {pid} states profit {fmt(stated)}; net project revenue "
                        f"less total project expense is {fmt(derived)} "
                        f"(out by {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} current project profits foot to net revenue less expense",
            )
        )
    return out


@check("eco_margin_on_cost_recomputes")
def check_eco_margin_on_cost_recomputes(ctx: Context) -> list[Finding]:
    """Margin on cost re-derives from the same inputs the profit was struck on.

    Margin on cost is the headline the report is read for, and it is the figure
    most often carried across from the prior period's workbook. It is rebuilt here
    as profit over total project expense in truncating integer basis points, from
    the very inputs the profit came from, and compared with exact ``==``.
    """
    rule = "eco_margin_on_cost_recomputes"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_CURRENT_ECONOMICS)
    if doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _current_rows(ctx):
        pid = _text(row, "project_id") or "?"
        with amount_guard(rule, out):
            derived = recompute_margin(row, f"current[{pid}]")
            if derived is None:
                continue  # no cost to strike a margin on
            stated = require_cents(
                f"current[{pid}].margin_on_cost_bps",
                row.get("margin_on_cost_bps"),
                unit="integer basis points",
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(doc, f"projects/{pid}/margin_on_cost_bps"),
                        f"project {pid} states margin on cost {fmt_bps(stated)}; profit "
                        f"over total project expense recomputes {fmt_bps(derived)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} margins on cost recompute from profit and expense",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# var_ -- the comparative and variance columns
# --------------------------------------------------------------------------- #
@check("var_comparative_columns_foot")
def check_var_comparative_columns_foot(ctx: Context) -> list[Finding]:
    """The Prior and Business Plan columns foot inside themselves.

    A comparative is only a comparative if it is internally consistent. Each of
    those columns carries its own gross revenue, deductions and expense, so its
    own net revenue, profit and margin must re-derive from them exactly as the
    current column's do -- otherwise the variance is measured against a column
    that never footed.
    """
    rule = "var_comparative_columns_foot"
    _sev(rule, Status.FAIL)
    prior_doc = ctx.one(DOC_PRIOR_ECONOMICS)
    plan_doc = ctx.one(DOC_PLAN_BASELINE)
    if prior_doc is None or plan_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for label, doc, rows in (
        ("prior period", prior_doc, _prior_rows(ctx)),
        ("business plan", plan_doc, _plan_rows(ctx)),
    ):
        for row in rows:
            pid = _text(row, "project_id") or "?"
            tag = f"{label.replace(' ', '_')}[{pid}]"
            with amount_guard(rule, out):
                net_derived = recompute_net_revenue(row, tag)
                net_stated = require_cents(
                    f"{tag}.net_project_revenue_cents",
                    row.get("net_project_revenue_cents"),
                )
                checked += 1
                if net_stated != net_derived:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(doc, f"projects/{pid}/net_project_revenue_cents"),
                            f"the {label} column for project {pid} states net project "
                            f"revenue {fmt(net_stated)}; its own gross less deductions is "
                            f"{fmt(net_derived)}",
                        )
                    )
                profit_derived = recompute_profit(row, tag)
                profit_stated = require_cents(
                    f"{tag}.project_profit_cents", row.get("project_profit_cents")
                )
                if profit_stated != profit_derived:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(doc, f"projects/{pid}/project_profit_cents"),
                            f"the {label} column for project {pid} states profit "
                            f"{fmt(profit_stated)}; its own net revenue less expense is "
                            f"{fmt(profit_derived)}",
                        )
                    )
                margin_derived = recompute_margin(row, tag)
                if margin_derived is None:
                    continue
                margin_stated = require_cents(
                    f"{tag}.margin_on_cost_bps",
                    row.get("margin_on_cost_bps"),
                    unit="integer basis points",
                )
                if margin_stated != margin_derived:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(doc, f"projects/{pid}/margin_on_cost_bps"),
                            f"the {label} column for project {pid} states margin on cost "
                            f"{fmt_bps(margin_stated)}; its own profit over expense "
                            f"recomputes {fmt_bps(margin_derived)}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} comparative columns foot inside themselves",
            )
        )
    return out


@check("var_prior_column_ties")
def check_var_prior_column_ties(ctx: Context) -> list[Finding]:
    """The Current-vs-Prior variance re-foots from the two columns beside it.

    Both source cells are proved against the tabs they come from first, then the
    variance is re-struck as current less prior. A variance carried forward from
    last period's workbook -- or nudged to explain a number -- fails here even
    though the grid still reads left to right.
    """
    rule = "var_prior_column_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_VARIANCE_SUMMARY)
    if summary is None:
        return []
    current = _economics_map(_current_rows(ctx))
    prior = _economics_map(_prior_rows(ctx))
    fields = {metric: (field_name, unit) for metric, field_name, unit in METRIC_FIELDS}
    out: list[Finding] = []
    checked = 0
    for row in _variance_summary_rows(ctx):
        pid = _text(row, "project_id")
        metric = _text(row, "metric")
        if pid is None or metric not in fields:
            continue
        if pid not in current or pid not in prior:
            continue  # prj_comparatives_present owns this
        field_name, unit = fields[metric]
        unit_label = _unit_label(unit)
        with amount_guard(rule, out):
            source_current = require_cents(
                f"current[{pid}].{field_name}",
                current[pid].get(field_name),
                unit=unit_label,
            )
            source_prior = require_cents(
                f"prior[{pid}].{field_name}", prior[pid].get(field_name), unit=unit_label
            )
            stated_current = require_cents(
                f"variance[{pid}/{metric}].current_value",
                row.get("current_value"),
                unit=unit_label,
            )
            stated_prior = require_cents(
                f"variance[{pid}/{metric}].prior_value",
                row.get("prior_value"),
                unit=unit_label,
            )
            stated_variance = require_cents(
                f"variance[{pid}/{metric}].variance_vs_prior",
                row.get("variance_vs_prior"),
                unit=unit_label,
            )
            checked += 1
            if stated_current != source_current:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"rows/{pid}/{metric}/current_value"),
                        f"project {pid} {metric} shows current "
                        f"{_show(stated_current, unit)} on the variance tab; the current "
                        f"period reports {_show(source_current, unit)}",
                    )
                )
            if stated_prior != source_prior:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"rows/{pid}/{metric}/prior_value"),
                        f"project {pid} {metric} shows prior {_show(stated_prior, unit)} "
                        f"on the variance tab; the prior period reports "
                        f"{_show(source_prior, unit)}",
                    )
                )
            expected = variance(stated_current, stated_prior)
            if stated_variance != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"rows/{pid}/{metric}/variance_vs_prior"),
                        f"project {pid} {metric} states a prior-period variance of "
                        f"{_show(stated_variance, unit)}; current less prior is "
                        f"{_show(expected, unit)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} current-vs-prior variances re-foot from their own columns",
            )
        )
    return out


@check("var_plan_column_ties")
def check_var_plan_column_ties(ctx: Context) -> list[Finding]:
    """The Current-vs-Business-Plan variance re-foots from the two columns beside it.

    The plan cell is proved against the frozen baseline document first, then the
    variance is re-struck as current less plan. This is the column an investment
    committee reads as performance against the approved plan, so a hardcoded
    override here overstates or understates the whole thesis at once.
    """
    rule = "var_plan_column_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_VARIANCE_SUMMARY)
    if summary is None:
        return []
    plan = _economics_map(_plan_rows(ctx))
    fields = {metric: (field_name, unit) for metric, field_name, unit in METRIC_FIELDS}
    out: list[Finding] = []
    checked = 0
    for row in _variance_summary_rows(ctx):
        pid = _text(row, "project_id")
        metric = _text(row, "metric")
        if pid is None or metric not in fields or pid not in plan:
            continue  # prj_comparatives_present owns a missing plan column
        field_name, unit = fields[metric]
        unit_label = _unit_label(unit)
        with amount_guard(rule, out):
            source_plan = require_cents(
                f"plan[{pid}].{field_name}", plan[pid].get(field_name), unit=unit_label
            )
            stated_current = require_cents(
                f"variance[{pid}/{metric}].current_value",
                row.get("current_value"),
                unit=unit_label,
            )
            stated_plan = require_cents(
                f"variance[{pid}/{metric}].plan_value",
                row.get("plan_value"),
                unit=unit_label,
            )
            stated_variance = require_cents(
                f"variance[{pid}/{metric}].variance_vs_plan",
                row.get("variance_vs_plan"),
                unit=unit_label,
            )
            checked += 1
            if stated_plan != source_plan:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"rows/{pid}/{metric}/plan_value"),
                        f"project {pid} {metric} shows a business-plan figure of "
                        f"{_show(stated_plan, unit)}; the approved baseline carries "
                        f"{_show(source_plan, unit)}",
                    )
                )
            expected = variance(stated_current, stated_plan)
            if stated_variance != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"rows/{pid}/{metric}/variance_vs_plan"),
                        f"project {pid} {metric} states a business-plan variance of "
                        f"{_show(stated_variance, unit)}; current less plan is "
                        f"{_show(expected, unit)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} current-vs-plan variances re-foot from their own columns",
            )
        )
    return out


@check("var_plan_version_frozen")
def check_var_plan_version_frozen(ctx: Context) -> list[Finding]:
    """The plan column is struck against the frozen version named in the header.

    The Business Plan baseline is approved once and frozen. The variance tab names
    the version it is measured to in its own header, the baseline document carries
    the version it actually is, and each project declares the version it was
    approved under. A baseline quietly re-based to a later revision makes every
    plan variance smaller at once, and the report reads as on-plan against a plan
    nobody approved.
    """
    rule = "var_plan_version_frozen"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_VARIANCE_SUMMARY)
    plan_doc = ctx.one(DOC_PLAN_BASELINE)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if summary is None or plan_doc is None or register is None:
        return []
    header = _text(summary, "basis_plan_version")
    approved = _text(plan_doc, "plan_version")
    out: list[Finding] = []
    if header is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(summary, "basis_plan_version"),
                "the variance tab names no business-plan version; the plan column cannot "
                "be shown to be the approved one",
            )
        )
    if approved is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(plan_doc, "plan_version"),
                "the business-plan baseline carries no plan version; it cannot be shown "
                "to be the frozen approved plan",
            )
        )
    if header is not None and approved is not None and header != approved:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(summary, "basis_plan_version"),
                f"the variance tab is headed business plan {header} but the baseline "
                f"document is version {approved}; the plan column is not the plan named",
            )
        )
    for row in _projects(ctx):
        pid = _project_id(row)
        declared = _text(row, "plan_version")
        if declared is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{pid}/plan_version"),
                    f"project {pid} declares no approved business-plan version; the plan "
                    f"column it is measured against cannot be shown to be frozen",
                )
            )
        elif approved is not None and declared != approved:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{pid}/plan_version"),
                    f"project {pid} was approved under business plan {declared} but the "
                    f"baseline column is version {approved}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the plan column, the tab header and every project agree on business "
                f"plan {approved}",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# mst_ -- the milestone block
# --------------------------------------------------------------------------- #
@check("mst_required_fields")
def check_mst_required_fields(ctx: Context) -> list[Finding]:
    """Every milestone is identified, attributable, named and fully dated.

    The milestone block reports three dates side by side. A row missing one of
    them, naming a milestone the frozen schedule does not define, or pointing at a
    project the report does not carry, produces a variance nobody can trace back
    to a schedule.
    """
    rule = "mst_required_fields"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    projects = _project_map(ctx)
    out: list[Finding] = []
    for row in _milestones(ctx):
        mid = _milestone_id(row)
        missing = [f for f in ("milestone_id", "project_id", "milestone_name") if not _text(row, f)]
        undated = [
            f
            for f in ("baseline_date", "prior_date", "current_date")
            if _parse_date(row.get(f)) is None
        ]
        if missing or undated:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{mid}"),
                    f"milestone {mid} is missing {', '.join(missing + undated) or 'a field'}; "
                    f"its Current vs Prior vs Variance line cannot be read",
                )
            )
            continue
        name = _text(row, "milestone_name")
        if name not in MILESTONE_NAMES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{mid}/milestone_name"),
                    f"milestone {mid} is named {name!r}, which the frozen baseline "
                    f"schedule does not define",
                )
            )
        pid = _text(row, "project_id")
        if pid and pid not in projects:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"milestones/{mid}/project_id"),
                    f"milestone {mid} names project {pid!r}, which is not in the project "
                    f"register",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_milestones(ctx))} milestones are named, dated and attributable",
            )
        )
    return out


@check("mst_variance_sign_convention")
def check_mst_variance_sign_convention(ctx: Context) -> list[Finding]:
    """The Current-vs-Prior milestone variance is prior less current, ``+`` = ahead.

    The sign convention is the whole content of a schedule variance column, and it
    is the thing a hand-maintained column gets backwards. A date that moved earlier
    is ahead and reports positive; a date that moved later is behind and reports
    negative. A flipped sign turns two weeks of slippage into two weeks of
    progress on the page a committee reads.
    """
    rule = "mst_variance_sign_convention"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _milestones(ctx):
        mid = _milestone_id(row)
        derived, _baseline = recompute_milestone_variances(row)
        if derived is None:
            continue  # mst_required_fields owns this
        with amount_guard(rule, out):
            stated = require_cents(
                f"milestone[{mid}].variance_prior_days",
                row.get("variance_prior_days"),
                unit="a whole number of days",
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"milestones/{mid}/variance_prior_days"),
                        f"milestone {mid} states a prior variance of {stated:+d} day(s); "
                        f"prior date less current date is {derived:+d} day(s) under the "
                        f"convention that + is ahead",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} prior-period milestone variances carry the + = ahead sign",
            )
        )
    return out


@check("mst_baseline_variance_foots")
def check_mst_baseline_variance_foots(ctx: Context) -> list[Finding]:
    """The milestone variance to the frozen baseline schedule re-foots.

    The baseline schedule is frozen at the version each project declares, so the
    baseline variance is the one figure that measures cumulative slippage rather
    than movement since last period. It is re-struck as baseline date less current
    date and compared exactly, and the schedule version on the block is proved
    against the version each project was approved under.
    """
    rule = "mst_baseline_variance_foots"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if schedule is None or register is None:
        return []
    out: list[Finding] = []
    frozen = _text(schedule, "baseline_schedule_version")
    if frozen is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(schedule, "baseline_schedule_version"),
                "the milestone block names no baseline schedule version; its variances "
                "cannot be shown to measure against a frozen schedule",
            )
        )
    else:
        for row in _projects(ctx):
            declared = _text(row, "baseline_schedule_version")
            if declared is not None and declared != frozen:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            register,
                            f"projects/{_project_id(row)}/baseline_schedule_version",
                        ),
                        f"project {_project_id(row)} was approved on baseline schedule "
                        f"{declared} but the milestone block measures to {frozen}",
                    )
                )
    checked = 0
    for row in _milestones(ctx):
        mid = _milestone_id(row)
        _prior, derived = recompute_milestone_variances(row)
        if derived is None:
            continue  # mst_required_fields owns this
        with amount_guard(rule, out):
            stated = require_cents(
                f"milestone[{mid}].variance_baseline_days",
                row.get("variance_baseline_days"),
                unit="a whole number of days",
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"milestones/{mid}/variance_baseline_days"),
                        f"milestone {mid} states a baseline variance of {stated:+d} "
                        f"day(s); baseline date less current date is {derived:+d} day(s)",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} baseline milestone variances re-foot to the frozen schedule",
            )
        )
    return out


@check("mst_slippage_lead_time")
def check_mst_slippage_lead_time(ctx: Context) -> list[Finding]:
    """A milestone behind the frozen baseline beyond tolerance is flagged.

    Deliberately a FLAG, not a failure: the report is arithmetically correct and
    the date has simply moved. Only milestones still ahead of the report date are
    raised -- a date already passed is history, and the chase is for the ones in
    front of the team. The tolerance comes from the file's own
    ``slippage_tolerance_days``.
    """
    rule = "mst_slippage_lead_time"
    _sev(rule, Status.FLAG)
    schedule = ctx.one(DOC_MILESTONE_SCHEDULE)
    as_of = _parse_date(ctx.as_of)
    if schedule is None or as_of is None:
        return []
    tolerance = ctx.slippage_tolerance_days
    out: list[Finding] = []
    for entry in recompute_slippage_watchlist(ctx, as_of, tolerance):
        out.append(
            Finding(
                rule,
                Status.FLAG,
                ctx.loc(schedule, f"milestones/{entry['milestone_id']}/current_date"),
                f"milestone {entry['milestone_id']} on project {entry['project_id']} now "
                f"dates {entry['current_date']} against a frozen baseline of "
                f"{entry['baseline_date']}, {-entry['variance_baseline_days']} day(s) "
                f"behind and past the {tolerance}-day tolerance",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"no forthcoming milestone is more than {tolerance} day(s) behind the "
                f"frozen baseline schedule",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the report rollup
# --------------------------------------------------------------------------- #
@check("rpt_rollup_foots")
def check_rpt_rollup_foots(ctx: Context) -> list[Finding]:
    """The report rollup foots across all projects.

    The rollup is the page that leaves the reporting pack, and a total maintained
    beside the project grid rather than added up from it drifts the first time a
    project moves and nobody re-adds the column. The project count and all four
    totals are re-footed from the current-period rows and compared with exact
    ``==``.
    """
    rule = "rpt_rollup_foots"
    _sev(rule, Status.FAIL)
    rollup = ctx.one(DOC_REPORT_ROLLUP)
    current = ctx.one(DOC_CURRENT_ECONOMICS)
    if rollup is None or current is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = recompute_rollup(ctx)
        for key, label in (
            ("project_count", "project count"),
            ("total_gross_revenue_cents", "total gross revenue"),
            ("total_net_project_revenue_cents", "total net project revenue"),
            ("total_project_expense_cents", "total project expense"),
            ("total_project_profit_cents", "total project profit"),
        ):
            unit = "a whole count" if key == "project_count" else "integer cents"
            stated = require_cents(f"report_rollup.{key}", rollup.get(key), unit=unit)
            if stated != derived[key]:
                shown_stated = (
                    str(stated) if key == "project_count" else fmt(stated)
                )
                shown_derived = (
                    str(derived[key]) if key == "project_count" else fmt(derived[key])
                )
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollup, key),
                        f"the rollup states a {label} of {shown_stated}; footing the "
                        f"{derived['project_count']} current-period rows gives "
                        f"{shown_derived}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "the report rollup count and all four totals foot across the projects",
            )
        )
    return out


@check("rpt_slippage_watchlist_ties")
def check_rpt_slippage_watchlist_ties(ctx: Context) -> list[Finding]:
    """The slippage watchlist ties the milestone schedule.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a milestone not actually behind -- or omits one that is --
    sends the schedule chase to the wrong project. It is rebuilt from the
    milestone dates and compared.
    """
    rule = "rpt_slippage_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_SLIPPAGE_WATCHLIST)
    as_of = _parse_date(ctx.as_of)
    if watchlist is None or as_of is None:
        return []
    recomputed = [
        _normalize_entry(e)
        for e in recompute_slippage_watchlist(ctx, as_of, ctx.slippage_tolerance_days)
    ]
    stated = [_normalize_entry(e) for e in _rows(watchlist, "entries")]
    out: list[Finding] = []
    want = sorted(recomputed, key=lambda t: tuple(str(v) for v in t))
    have = sorted(stated, key=lambda t: tuple(str(v) for v in t))
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"the watchlist lists milestone {entry[0]} as behind the frozen "
                        f"baseline, but the schedule does not put it past tolerance as of "
                        f"{as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"milestone {entry[0]} is behind the frozen baseline past "
                        f"tolerance but is not on the slippage watchlist",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "the slippage watchlist ties the milestone schedule exactly",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one project report."""
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
    """Analyze every ``.json`` project report in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of project-report reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
