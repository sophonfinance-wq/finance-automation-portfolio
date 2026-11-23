"""
Project-proforma integrity (QPR) control engine (READ-ONLY).
============================================================

Loads each proforma file (a ``.json`` file produced by
:mod:`proforma_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the workbook still ties to itself**, not whether a
project should be built. Underwriting a rent or a cap rate is a different job; the
question here is entirely arithmetic and evidentiary: recomputed from its own base
ledger, does every stated figure on the summary tabs still hold, and did every
deliverable make its cycle on time?

The shape of the problem
------------------------
A quarterly proforma is a workbook that was internally consistent the day a
formula last recalculated, and it drifts when cells are overtyped or tabs rolled
forward without their precedents. The error-check tab keeps showing zeros because
the zeros themselves were typed. Three families of drift hide inside that, and
none of them look wrong in a grid of formatted numbers: the balances that stop
balancing (sources vs uses, hard+soft vs total, dev budget vs unlevered cost);
the profit chain that stops tying (net profit vs revenue-minus-cost, waterfall vs
budgeted vs distributed, sponsor+investor vs whole); and the report that drifts
from the evidence (a margin off a stale cost, a typed variance, a QPR that missed
the cycle or landed late, a count kept beside the filings instead of derived).

The registry is organised around that:

1. ``set_``   -- is the proforma file complete?
2. ``src_``   -- do the sources and uses total and balance?
3. ``cost_``  -- do the cost budgets tie (hard+soft, unlevered=dev budget, contingency)?
4. ``int_``   -- is the interest reserve adequate and the equity funded first?
5. ``prof_``  -- does the profit chain re-derive from revenue and cost?
6. ``wfl_``   -- does the waterfall tie to profit and do the splits sum to the whole?
7. ``mgn_``   -- do the margins and per-NSF metrics re-derive?
8. ``var_``   -- is each variance a real subtraction, and is any swing material?
9. ``rpt_``   -- is every project filed, on time, complete, and does the count tie?

Design notes
------------
- **Strictly read-only.** Proforma files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tie-out is compared with exact ``==``.
- **One derivation kernel.** Controls and the generator share the arithmetic in
  :mod:`proforma_engine.proforma`, so a stated figure cannot disagree with the
  logic that produced it.
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
    DOC_CYCLE_REPORT,
    DOC_FILING_REGISTER,
    DOC_PROFORMA_LEDGER,
    DOC_PROJECT_REGISTER,
    DOC_REPORTING_CALENDAR,
    DOC_TIEOUT_SUMMARY,
    DOC_TYPES,
    REGIONAL_DELIVERABLES,
    VARIANCE_METRICS,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents
from .proforma import (
    cost_per_nsf,
    exceeds_materiality,
    margin_bps,
    net_profit,
    schedule_variance_days,
    sponsor_share,
    total_project_cost,
    unlevered_cost,
    unlevered_profit,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~proforma_engine.money.AmountInvalidError` as a finding."""
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
# Proforma-file helpers
# --------------------------------------------------------------------------- #
def _projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PROJECT_REGISTER), "projects")


def _project_id(row: dict[str, Any]) -> str:
    value = row.get("project_id")
    return value if isinstance(value, str) and value else "?"


def _active_projects(ctx: Context) -> list[dict[str, Any]]:
    return [p for p in _projects(ctx) if bool(p.get("active"))]


def _region_of(ctx: Context, project_id: str) -> str | None:
    for row in _projects(ctx):
        if _project_id(row) == project_id:
            return _text(row, "region")
    return None


def _ledger_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_PROFORMA_LEDGER), "projects"):
        pid = _project_id(row)
        if pid != "?" and pid not in out:
            out[pid] = row
    return out


def _summary_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_TIEOUT_SUMMARY), "projects"):
        pid = _project_id(row)
        if pid != "?" and pid not in out:
            out[pid] = row
    return out


def _calendar_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_REPORTING_CALENDAR), "regions"):
        region = _text(row, "region")
        if region and region not in out:
            out[region] = row
    return out


def _qpr_filings(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_FILING_REGISTER), "qpr_filings")


def _regional_filings(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_FILING_REGISTER), "regional_filings")


def _sum_amounts(rows: list[dict[str, Any]], label: str) -> int:
    """Sum the ``amount_cents`` of a list of ``{label, amount_cents}`` rows.

    Raises :class:`AmountInvalidError` on any non-integer amount, so a malformed
    line is surfaced by the control reading it rather than silently coerced.
    """
    return sum(
        require_cents(f"{label}[{i}].amount_cents", row.get("amount_cents"))
        for i, row in enumerate(rows)
    )


def recompute_derived(ledger_row: dict[str, Any]) -> dict[str, Any]:
    """Re-derive every stated summary figure for one project from its ledger.

    Shared with the generator so the figures the engine recomputes are the figures
    that produced the data. Reads amounts through :func:`require_cents`, so a
    malformed ledger amount raises :class:`AmountInvalidError` for the caller to
    contain.
    """
    pid = _project_id(ledger_row)
    hard = require_cents(f"ledger[{pid}].hard_cost_cents", ledger_row.get("hard_cost_cents"))
    soft = require_cents(f"ledger[{pid}].soft_cost_cents", ledger_row.get("soft_cost_cents"))
    interest = require_cents(
        f"ledger[{pid}].interest_cost_cents", ledger_row.get("interest_cost_cents")
    )
    revenue = require_cents(
        f"ledger[{pid}].net_revenue_cents", ledger_row.get("net_revenue_cents")
    )
    nsf = require_cents(f"ledger[{pid}].nsf", ledger_row.get("nsf"), unit="a whole count")
    sponsor_bps = require_cents(
        f"ledger[{pid}].sponsor_bps", ledger_row.get("sponsor_bps"), unit="basis points"
    )
    investor_bps = require_cents(
        f"ledger[{pid}].investor_bps", ledger_row.get("investor_bps"), unit="basis points"
    )

    tpc = total_project_cost(hard, soft)
    unlev = unlevered_cost(hard, soft, interest)
    np = net_profit(revenue, hard, soft)
    up = unlevered_profit(revenue, hard, soft, interest)

    current = {"net_profit_cents": np, "total_project_cost_cents": tpc}
    prior = ledger_row.get("prior") if isinstance(ledger_row.get("prior"), dict) else {}
    variance: dict[str, int] = {}
    for metric in VARIANCE_METRICS:
        prior_val = require_cents(
            f"ledger[{pid}].prior.{metric}", prior.get(metric)
        )
        variance[metric] = current[metric] - prior_val

    schedule: dict[str, int] = {}
    milestones = ledger_row.get("milestones")
    if isinstance(milestones, list):
        for m in milestones:
            if not isinstance(m, dict):
                continue
            name = _text(m, "name")
            cur = _parse_date(m.get("current"))
            base = _parse_date(m.get("baseline"))
            if name and cur is not None and base is not None:
                schedule[name] = schedule_variance_days(cur, base)

    return {
        "project_id": pid,
        "total_sources_cents": _sum_amounts(_rows(ledger_row, "sources"), f"ledger[{pid}].sources"),
        "total_uses_cents": _sum_amounts(_rows(ledger_row, "uses"), f"ledger[{pid}].uses"),
        "total_project_cost_cents": tpc,
        "unlevered_cost_cents": unlev,
        "net_profit_cents": np,
        "unlevered_profit_cents": up,
        "margin_on_cost_bps": margin_bps(np, tpc),
        "margin_on_revenue_bps": margin_bps(np, revenue),
        "cost_per_nsf_cents": cost_per_nsf(tpc, nsf),
        "waterfall_profit_cents": np,
        "budgeted_profit_cents": np,
        "distributed_profit_cents": np,
        "sponsor_profit_cents": sponsor_share(np, sponsor_bps, investor_bps),
        "investor_profit_cents": np - sponsor_share(np, sponsor_bps, investor_bps),
        "variance": variance,
        "schedule_variance_days": schedule,
    }


def recompute_filed_qpr_count(ctx: Context) -> int:
    """The number of QPR filings whose project is an active project in the register."""
    active = {_project_id(p) for p in _active_projects(ctx)}
    filed = {
        _text(f, "project_id")
        for f in _qpr_filings(ctx)
        if _text(f, "project_id") in active
    }
    return len(filed)


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the proforma file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the proforma file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(DOC_TYPES)} proforma artifacts are present"
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every filing due-date gate "
                f"is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# src_ -- sources and uses
# --------------------------------------------------------------------------- #
@check("src_sources_total_ties")
def check_src_sources_total_ties(ctx: Context) -> list[Finding]:
    """Each project's stated total sources equals the sum of its source lines."""
    rule = "src_sources_total_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(f"summary[{pid}].total_sources_cents", srow.get("total_sources_cents"))
            computed = _sum_amounts(_rows(led, "sources"), f"ledger[{pid}].sources")
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/total_sources_cents"),
                        f"project {pid} states total sources {fmt(stated)}; its source lines "
                        f"sum to {fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} source totals tie their lines"))
    return out


@check("src_uses_total_ties")
def check_src_uses_total_ties(ctx: Context) -> list[Finding]:
    """Each project's stated total uses equals the sum of its use lines."""
    rule = "src_uses_total_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(f"summary[{pid}].total_uses_cents", srow.get("total_uses_cents"))
            computed = _sum_amounts(_rows(led, "uses"), f"ledger[{pid}].uses")
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/total_uses_cents"),
                        f"project {pid} states total uses {fmt(stated)}; its use lines "
                        f"sum to {fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} use totals tie their lines"))
    return out


@check("src_source_use_balance")
def check_src_source_use_balance(ctx: Context) -> list[Finding]:
    """Total sources equals total uses -- the source-and-use error line is zero.

    Recomputed from the ledger's own source and use lines, so it holds regardless
    of what the summary totals happen to say.
    """
    rule = "src_source_use_balance"
    _sev(rule, Status.FAIL)
    ledger_doc = ctx.one(DOC_PROFORMA_LEDGER)
    if ledger_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for pid, led in _ledger_map(ctx).items():
        with amount_guard(rule, out):
            sources = _sum_amounts(_rows(led, "sources"), f"ledger[{pid}].sources")
            uses = _sum_amounts(_rows(led, "uses"), f"ledger[{pid}].uses")
            checked += 1
            if sources != uses:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger_doc, f"projects/{pid}/uses"),
                        f"project {pid} funds {fmt(sources)} of sources against {fmt(uses)} "
                        f"of uses; the source-and-use error is {fmt(sources - uses)}, not zero",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} projects balance sources to uses"))
    return out


# --------------------------------------------------------------------------- #
# cost_ -- cost-budget tie-outs
# --------------------------------------------------------------------------- #
@check("cost_hard_soft_total")
def check_cost_hard_soft_total(ctx: Context) -> list[Finding]:
    """Stated total project cost equals hard cost plus soft cost."""
    rule = "cost_hard_soft_total"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
            soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
            stated = require_cents(
                f"summary[{pid}].total_project_cost_cents", srow.get("total_project_cost_cents")
            )
            computed = total_project_cost(hard, soft)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/total_project_cost_cents"),
                        f"project {pid} states total project cost {fmt(stated)}; hard {fmt(hard)} "
                        f"plus soft {fmt(soft)} is {fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} total project costs tie hard+soft"))
    return out


@check("cost_unlevered_ties_devbudget")
def check_cost_unlevered_ties_devbudget(ctx: Context) -> list[Finding]:
    """The dev-cost budget equals the proforma's unlevered cost.

    Unlevered cost is hard plus soft less financing interest, recomputed from the
    ledger; the dev-cost budget is carried on its own tab and must match it -- the
    unlevered-cost error line is zero.
    """
    rule = "cost_unlevered_ties_devbudget"
    _sev(rule, Status.FAIL)
    ledger_doc = ctx.one(DOC_PROFORMA_LEDGER)
    if ledger_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for pid, led in _ledger_map(ctx).items():
        with amount_guard(rule, out):
            hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
            soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
            interest = require_cents(
                f"ledger[{pid}].interest_cost_cents", led.get("interest_cost_cents")
            )
            devbudget = require_cents(
                f"ledger[{pid}].dev_cost_budget_cents", led.get("dev_cost_budget_cents")
            )
            computed = unlevered_cost(hard, soft, interest)
            checked += 1
            if devbudget != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger_doc, f"projects/{pid}/dev_cost_budget_cents"),
                        f"project {pid} carries a dev-cost budget of {fmt(devbudget)}; the "
                        f"proforma's unlevered cost is {fmt(computed)} "
                        f"(unlevered-cost error {fmt(devbudget - computed)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} dev-cost budgets tie the unlevered cost")
        )
    return out


@check("cost_contingency_rollup")
def check_cost_contingency_rollup(ctx: Context) -> list[Finding]:
    """The stated contingency total equals the sum of its category lines."""
    rule = "cost_contingency_rollup"
    _sev(rule, Status.FAIL)
    ledger_doc = ctx.one(DOC_PROFORMA_LEDGER)
    if ledger_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for pid, led in _ledger_map(ctx).items():
        with amount_guard(rule, out):
            stated = require_cents(
                f"ledger[{pid}].contingency_total_cents", led.get("contingency_total_cents")
            )
            computed = _sum_amounts(_rows(led, "contingencies"), f"ledger[{pid}].contingencies")
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger_doc, f"projects/{pid}/contingency_total_cents"),
                        f"project {pid} states a contingency total of {fmt(stated)}; its lines "
                        f"sum to {fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} contingency totals tie their lines"))
    return out


# --------------------------------------------------------------------------- #
# int_ -- interest reserve and equity funding
# --------------------------------------------------------------------------- #
@check("int_reserve_adequate")
def check_int_reserve_adequate(ctx: Context) -> list[Finding]:
    """The budgeted interest cost does not exceed the interest reserve.

    Compared with exact ``<=``: a reserve a cent under the interest it must fund is
    a reserve that runs dry before the loan is repaid.
    """
    rule = "int_reserve_adequate"
    _sev(rule, Status.FAIL)
    ledger_doc = ctx.one(DOC_PROFORMA_LEDGER)
    if ledger_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for pid, led in _ledger_map(ctx).items():
        with amount_guard(rule, out):
            interest = require_cents(
                f"ledger[{pid}].interest_cost_cents", led.get("interest_cost_cents")
            )
            reserve = require_cents(
                f"ledger[{pid}].interest_reserve_cents", led.get("interest_reserve_cents")
            )
            checked += 1
            if interest > reserve:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger_doc, f"projects/{pid}/interest_reserve_cents"),
                        f"project {pid} budgets {fmt(interest)} of interest against a reserve of "
                        f"{fmt(reserve)}; the reserve is short {fmt(interest - reserve)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} interest reserves cover the interest cost"))
    return out


@check("int_equity_funded_before_construction")
def check_int_equity_funded_before_construction(ctx: Context) -> list[Finding]:
    """Every project's equity is funded before construction draws begin.

    A boolean gate: equity funded first is the condition the construction loan was
    sized against, so a project that fails it is levered before its equity is in.
    """
    rule = "int_equity_funded_before_construction"
    _sev(rule, Status.FAIL)
    ledger_doc = ctx.one(DOC_PROFORMA_LEDGER)
    if ledger_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for pid, led in _ledger_map(ctx).items():
        checked += 1
        if led.get("equity_funded_before_construction") is not True:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger_doc, f"projects/{pid}/equity_funded_before_construction"),
                    f"project {pid} does not fund its equity before construction; the loan was "
                    f"sized on the assumption that it does",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} projects fund equity before construction"))
    return out


# --------------------------------------------------------------------------- #
# prof_ -- the profit chain
# --------------------------------------------------------------------------- #
@check("prof_net_profit_derivation")
def check_prof_net_profit_derivation(ctx: Context) -> list[Finding]:
    """Stated net profit equals net revenue less total project cost."""
    rule = "prof_net_profit_derivation"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
            soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
            revenue = require_cents(f"ledger[{pid}].net_revenue_cents", led.get("net_revenue_cents"))
            stated = require_cents(f"summary[{pid}].net_profit_cents", srow.get("net_profit_cents"))
            computed = net_profit(revenue, hard, soft)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/net_profit_cents"),
                        f"project {pid} states net profit {fmt(stated)}; revenue {fmt(revenue)} "
                        f"less cost is {fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} net profits re-derive from revenue and cost"))
    return out


@check("prof_unlevered_profit_derivation")
def check_prof_unlevered_profit_derivation(ctx: Context) -> list[Finding]:
    """Stated unlevered profit equals net revenue less unlevered cost.

    The levered net profit and the unlevered profit differ by exactly the
    financing interest; recomputing the unlevered figure proves the two tabs were
    not typed to the same number by mistake.
    """
    rule = "prof_unlevered_profit_derivation"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
            soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
            interest = require_cents(f"ledger[{pid}].interest_cost_cents", led.get("interest_cost_cents"))
            revenue = require_cents(f"ledger[{pid}].net_revenue_cents", led.get("net_revenue_cents"))
            stated = require_cents(
                f"summary[{pid}].unlevered_profit_cents", srow.get("unlevered_profit_cents")
            )
            computed = unlevered_profit(revenue, hard, soft, interest)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/unlevered_profit_cents"),
                        f"project {pid} states unlevered profit {fmt(stated)}; revenue less "
                        f"unlevered cost is {fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} unlevered profits re-derive"))
    return out


# --------------------------------------------------------------------------- #
# wfl_ -- the owner-repayment waterfall
# --------------------------------------------------------------------------- #
def _recomputed_net(led: dict[str, Any], pid: str) -> int:
    hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
    soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
    revenue = require_cents(f"ledger[{pid}].net_revenue_cents", led.get("net_revenue_cents"))
    return net_profit(revenue, hard, soft)


def _waterfall_tie(ctx: Context, rule: str, field: str, label: str) -> list[Finding]:
    """Shared body for the three 'this profit figure equals net profit' controls."""
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(f"summary[{pid}].{field}", srow.get(field))
            computed = _recomputed_net(led, pid)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/{field}"),
                        f"project {pid} states {label} {fmt(stated)}; net profit re-derives to "
                        f"{fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} {label} figures tie net profit"))
    return out


@check("wfl_waterfall_ties_net")
def check_wfl_waterfall_ties_net(ctx: Context) -> list[Finding]:
    """The waterfall profit equals net profit -- the waterfall closes on the whole."""
    rule = "wfl_waterfall_ties_net"
    _sev(rule, Status.FAIL)
    return _waterfall_tie(ctx, rule, "waterfall_profit_cents", "waterfall profit")


@check("wfl_budgeted_ties_net")
def check_wfl_budgeted_ties_net(ctx: Context) -> list[Finding]:
    """The budgeted profit equals net profit -- the budget tab ties the derivation."""
    rule = "wfl_budgeted_ties_net"
    _sev(rule, Status.FAIL)
    return _waterfall_tie(ctx, rule, "budgeted_profit_cents", "budgeted profit")


@check("wfl_distributed_ties_net")
def check_wfl_distributed_ties_net(ctx: Context) -> list[Finding]:
    """The distributed profit equals net profit -- distributions do not exceed profit."""
    rule = "wfl_distributed_ties_net"
    _sev(rule, Status.FAIL)
    return _waterfall_tie(ctx, rule, "distributed_profit_cents", "distributed profit")


@check("wfl_sponsor_share_derivation")
def check_wfl_sponsor_share_derivation(ctx: Context) -> list[Finding]:
    """The sponsor's stated profit equals its share under the equity split.

    Recomputed with the same largest-remainder split the generator used, so the
    odd cent lands where the split put it rather than becoming a spurious break.
    """
    rule = "wfl_sponsor_share_derivation"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            sponsor_bps = require_cents(f"ledger[{pid}].sponsor_bps", led.get("sponsor_bps"), unit="basis points")
            investor_bps = require_cents(f"ledger[{pid}].investor_bps", led.get("investor_bps"), unit="basis points")
            stated = require_cents(f"summary[{pid}].sponsor_profit_cents", srow.get("sponsor_profit_cents"))
            computed = sponsor_share(_recomputed_net(led, pid), sponsor_bps, investor_bps)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/sponsor_profit_cents"),
                        f"project {pid} states a sponsor profit of {fmt(stated)}; the equity "
                        f"split gives {fmt(computed)} (off {fmt(stated - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} sponsor profits re-derive from the split"))
    return out


@check("wfl_split_completeness")
def check_wfl_split_completeness(ctx: Context) -> list[Finding]:
    """The sponsor and investor profit shares sum to net profit -- no leakage."""
    rule = "wfl_split_completeness"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            sponsor = require_cents(f"summary[{pid}].sponsor_profit_cents", srow.get("sponsor_profit_cents"))
            investor = require_cents(f"summary[{pid}].investor_profit_cents", srow.get("investor_profit_cents"))
            computed = _recomputed_net(led, pid)
            checked += 1
            if sponsor + investor != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/investor_profit_cents"),
                        f"project {pid} splits net profit into sponsor {fmt(sponsor)} plus investor "
                        f"{fmt(investor)} = {fmt(sponsor + investor)}; net profit is {fmt(computed)} "
                        f"(leakage {fmt(sponsor + investor - computed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} profit splits sum to net profit"))
    return out


# --------------------------------------------------------------------------- #
# mgn_ -- margins and per-NSF metrics
# --------------------------------------------------------------------------- #
@check("mgn_margin_on_cost")
def check_mgn_margin_on_cost(ctx: Context) -> list[Finding]:
    """Stated margin on cost equals net profit over total project cost, in bps."""
    rule = "mgn_margin_on_cost"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
            soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
            revenue = require_cents(f"ledger[{pid}].net_revenue_cents", led.get("net_revenue_cents"))
            stated = require_cents(
                f"summary[{pid}].margin_on_cost_bps", srow.get("margin_on_cost_bps"), unit="basis points"
            )
            tpc = total_project_cost(hard, soft)
            computed = margin_bps(net_profit(revenue, hard, soft), tpc)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/margin_on_cost_bps"),
                        f"project {pid} quotes a margin on cost of {fmt_bps(stated)}; net profit "
                        f"over cost re-derives to {fmt_bps(computed)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} margins on cost re-derive"))
    return out


@check("mgn_margin_on_revenue")
def check_mgn_margin_on_revenue(ctx: Context) -> list[Finding]:
    """Stated margin on revenue equals net profit over net revenue, in bps."""
    rule = "mgn_margin_on_revenue"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
            soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
            revenue = require_cents(f"ledger[{pid}].net_revenue_cents", led.get("net_revenue_cents"))
            stated = require_cents(
                f"summary[{pid}].margin_on_revenue_bps", srow.get("margin_on_revenue_bps"), unit="basis points"
            )
            computed = margin_bps(net_profit(revenue, hard, soft), revenue)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/margin_on_revenue_bps"),
                        f"project {pid} quotes a margin on revenue of {fmt_bps(stated)}; net profit "
                        f"over revenue re-derives to {fmt_bps(computed)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} margins on revenue re-derive"))
    return out


@check("mgn_cost_per_nsf")
def check_mgn_cost_per_nsf(ctx: Context) -> list[Finding]:
    """Stated cost per net square foot equals total project cost over NSF."""
    rule = "mgn_cost_per_nsf"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        with amount_guard(rule, out):
            hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
            soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
            nsf = require_cents(f"ledger[{pid}].nsf", led.get("nsf"), unit="a whole count")
            stated = require_cents(f"summary[{pid}].cost_per_nsf_cents", srow.get("cost_per_nsf_cents"))
            computed = cost_per_nsf(total_project_cost(hard, soft), nsf)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/cost_per_nsf_cents"),
                        f"project {pid} states {fmt(stated)} per NSF; cost over {nsf} NSF "
                        f"re-derives to {fmt(computed)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} per-NSF costs re-derive"))
    return out


# --------------------------------------------------------------------------- #
# var_ -- current-versus-prior variance
# --------------------------------------------------------------------------- #
def _current_metric(led: dict[str, Any], pid: str, metric: str) -> int:
    hard = require_cents(f"ledger[{pid}].hard_cost_cents", led.get("hard_cost_cents"))
    soft = require_cents(f"ledger[{pid}].soft_cost_cents", led.get("soft_cost_cents"))
    revenue = require_cents(f"ledger[{pid}].net_revenue_cents", led.get("net_revenue_cents"))
    if metric == "net_profit_cents":
        return net_profit(revenue, hard, soft)
    if metric == "total_project_cost_cents":
        return total_project_cost(hard, soft)
    raise KeyError(metric)


@check("var_metric_delta")
def check_var_metric_delta(ctx: Context) -> list[Finding]:
    """Each stated variance equals the current value minus the prior value.

    A variance column that was typed rather than subtracted is invisible until the
    subtraction is redone; this redoes it for every tracked metric.
    """
    rule = "var_metric_delta"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        variance = srow.get("variance")
        prior = led.get("prior")
        if not isinstance(variance, dict) or not isinstance(prior, dict):
            continue
        for metric in VARIANCE_METRICS:
            with amount_guard(rule, out):
                stated = require_cents(f"summary[{pid}].variance.{metric}", variance.get(metric))
                prior_val = require_cents(f"ledger[{pid}].prior.{metric}", prior.get(metric))
                computed = _current_metric(led, pid, metric) - prior_val
                checked += 1
                if stated != computed:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(summary, f"projects/{pid}/variance/{metric}"),
                            f"project {pid} states a {metric} variance of {fmt(stated)}; current "
                            f"less prior is {fmt(computed)} (off {fmt(stated - computed)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} variances are current minus prior"))
    return out


@check("var_schedule_days")
def check_var_schedule_days(ctx: Context) -> list[Finding]:
    """Each stated milestone schedule variance equals current date minus baseline."""
    rule = "var_schedule_days"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for pid, srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        stated_days = srow.get("schedule_variance_days")
        milestones = led.get("milestones")
        if not isinstance(stated_days, dict) or not isinstance(milestones, list):
            continue
        for m in milestones:
            if not isinstance(m, dict):
                continue
            name = _text(m, "name")
            cur = _parse_date(m.get("current"))
            base = _parse_date(m.get("baseline"))
            if name is None or cur is None or base is None:
                continue
            stated = stated_days.get(name)
            if not isinstance(stated, int) or isinstance(stated, bool):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/schedule_variance_days/{name}"),
                        f"project {pid} milestone {name} has no readable schedule variance",
                    )
                )
                continue
            computed = schedule_variance_days(cur, base)
            checked += 1
            if stated != computed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"projects/{pid}/schedule_variance_days/{name}"),
                        f"project {pid} milestone {name} states a schedule variance of {stated} "
                        f"day(s); current less baseline is {computed} day(s)",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} schedule variances re-derive"))
    return out


@check("var_materiality_flag")
def check_var_materiality_flag(ctx: Context) -> list[Finding]:
    """A period-over-period net-profit swing beyond the materiality band is flagged.

    Deliberately a FLAG, not a failure: the swing is real and correctly derived,
    but a move this large between quarters is a reviewer's call. The band comes
    from the file's own ``materiality_cents``.
    """
    rule = "var_materiality_flag"
    _sev(rule, Status.FLAG)
    summary = ctx.one(DOC_TIEOUT_SUMMARY)
    if summary is None:
        return []
    ledger = _ledger_map(ctx)
    band = ctx.materiality_cents
    out: list[Finding] = []
    checked = 0
    for pid, _srow in _summary_map(ctx).items():
        led = ledger.get(pid)
        if led is None:
            continue
        prior = led.get("prior")
        if not isinstance(prior, dict):
            continue
        with amount_guard(rule, out):
            prior_np = require_cents(f"ledger[{pid}].prior.net_profit_cents", prior.get("net_profit_cents"))
            swing = _current_metric(led, pid, "net_profit_cents") - prior_np
            checked += 1
            if exceeds_materiality(swing, band):
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(summary, f"projects/{pid}/variance/net_profit_cents"),
                        f"project {pid} swings net profit {fmt(swing)} against prior, beyond the "
                        f"{fmt(band)} materiality band; the move is real and wants a reviewer",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} profit swings are within the materiality band"))
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- reporting completeness and the calendar date-gate
# --------------------------------------------------------------------------- #
@check("rpt_project_qpr_filed")
def check_rpt_project_qpr_filed(ctx: Context) -> list[Finding]:
    """Every active project produced a QPR this cycle."""
    rule = "rpt_project_qpr_filed"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    filing = ctx.one(DOC_FILING_REGISTER)
    if register is None or filing is None:
        return []
    filed = {_text(f, "project_id") for f in _qpr_filings(ctx)}
    out: list[Finding] = []
    checked = 0
    for project in _active_projects(ctx):
        pid = _project_id(project)
        checked += 1
        if pid not in filed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(filing, f"qpr_filings/{pid}"),
                    f"active project {pid} has no QPR on file this cycle; the deck is incomplete "
                    f"without it",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} active projects filed a QPR"))
    return out


@check("rpt_qpr_due_date_gate")
def check_rpt_qpr_due_date_gate(ctx: Context) -> list[Finding]:
    """Every QPR was filed on or before its region's due date."""
    rule = "rpt_qpr_due_date_gate"
    _sev(rule, Status.FAIL)
    filing = ctx.one(DOC_FILING_REGISTER)
    calendar = ctx.one(DOC_REPORTING_CALENDAR)
    if filing is None or calendar is None:
        return []
    cal = _calendar_map(ctx)
    out: list[Finding] = []
    checked = 0
    for f in _qpr_filings(ctx):
        pid = _text(f, "project_id")
        if pid is None:
            continue
        region = _region_of(ctx, pid)
        cal_row = cal.get(region or "")
        if cal_row is None:
            continue  # region completeness is a different concern
        filed = _parse_date(f.get("filed_date"))
        due = _parse_date(cal_row.get("qpr_due_date"))
        if filed is None or due is None:
            continue
        checked += 1
        if filed > due:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(filing, f"qpr_filings/{pid}/filed_date"),
                    f"project {pid} filed its QPR {filed.isoformat()}, after the {region} due date "
                    f"{due.isoformat()} ({(filed - due).days} day(s) late)",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} QPRs filed on or before their due date"))
    return out


@check("rpt_regional_deliverables_present")
def check_rpt_regional_deliverables_present(ctx: Context) -> list[Finding]:
    """Every region with active projects filed each regional deliverable.

    The deck is not complete on the per-project QPRs alone: each region owes a
    market update, an apartment report and an acquisition/QPR summary.
    """
    rule = "rpt_regional_deliverables_present"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    filing = ctx.one(DOC_FILING_REGISTER)
    if register is None or filing is None:
        return []
    filed: dict[str, set[str]] = {}
    for row in _regional_filings(ctx):
        region = _text(row, "region")
        deliverable = _text(row, "deliverable")
        if region and deliverable:
            filed.setdefault(region, set()).add(deliverable)
    regions = sorted({_text(p, "region") for p in _active_projects(ctx) if _text(p, "region")})
    out: list[Finding] = []
    checked = 0
    for region in regions:
        have = filed.get(region, set())
        for deliverable in REGIONAL_DELIVERABLES:
            checked += 1
            if deliverable not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(filing, f"regional_filings/{region}/{deliverable}"),
                        f"region {region} did not file its {deliverable} this cycle; the deck is "
                        f"incomplete without it",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} regional deliverables are on file"))
    return out


@check("rpt_cycle_count_ties")
def check_rpt_cycle_count_ties(ctx: Context) -> list[Finding]:
    """The cycle report's filed-QPR count recomputes from the filing register.

    The number that reaches the reporting deck is a count, and a count maintained
    beside the filings rather than derived from them drifts the first time a
    project is added or dropped and nobody re-adds the column.
    """
    rule = "rpt_cycle_count_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_CYCLE_REPORT)
    filing = ctx.one(DOC_FILING_REGISTER)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if report is None or filing is None or register is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "cycle_report.filed_qpr_count", report.get("filed_qpr_count"), unit="a whole count"
        )
        computed = recompute_filed_qpr_count(ctx)
        if stated != computed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "filed_qpr_count"),
                    f"the cycle report states {stated} filed QPR(s); the filing register recomputes "
                    f"{computed} for the active projects",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the cycle report's {computed} filed QPR(s) tie the filing register",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one proforma file."""
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
    """Analyze every ``.json`` proforma file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of proforma-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
