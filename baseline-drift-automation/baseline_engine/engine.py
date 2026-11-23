"""
Controls for the baseline & version drift engine.
=================================================

Every control re-derives what a set of budget copies claims about each other and
compares with exact ``==``. The registry order is the report order: completeness
first (are all the artifacts here), then the version inventory (is there exactly
one governing copy and is it plausibly dated), then agreement (do the category
sets reconcile, do the paired values agree, do the totals), then currency (is
each copy still speaking about this period), then amendments (does every
movement trace to an approval), then derived schedules, then funding.

The controls share one kernel with the generator (:mod:`.budget`), so a control
and the corpus it audits cannot quietly disagree about what agreement means.
That is the point: every failure mode this engine exists for *survives* a
within-document check, because each copy is internally consistent. The only
defence is to reconcile the copies against one another -- category sets before
values, totals derived rather than read, and every difference graded before it
is reported.
"""

from __future__ import annotations

import contextlib
import functools
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .budget import (
    budget_lines,
    budget_total,
    detect_reclassifications,
    milestone_dates,
    pair_lines,
    parse_iso,
    phase_totals,
    revised_from_changes,
    schedule_inputs,
    version_by_role,
)
from .model import (
    CHANGE_APPROVED,
    CHANGE_PENDING,
    CHANGE_STATES,
    DOC_AGREEMENT,
    DOC_AMENDMENT_LOG,
    DOC_BUDGET_VERSION,
    DOC_DERIVED_SCHEDULE,
    DOC_FUNDING_REGISTER,
    DOC_MILESTONE_SET,
    DOC_TYPES,
    PHASES,
    ROLE_BASELINE,
    ROLE_BILLING,
    ROLE_SUMMARY,
    ROLE_WORKING,
    VERSION_ROLES,
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
    """Render an :class:`~baseline_engine.money.AmountInvalidError` as a finding."""
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


def _sev(rule_id: str, status: Status) -> Status:
    SEVERITY[rule_id] = status
    return status


def _ok(rule: str, message: str) -> Finding:
    """A PASS finding for a control that ran and held."""
    return Finding(rule, Status.PASS, "-", message)


# --------------------------------------------------------------------------- #
# Shared derived views
# --------------------------------------------------------------------------- #
def _versions(ctx: Context) -> list[dict[str, Any]]:
    return ctx.docs(DOC_BUDGET_VERSION)


def _baseline(ctx: Context) -> dict[str, Any] | None:
    found = version_by_role(_versions(ctx), ROLE_BASELINE)
    return found[0] if len(found) == 1 else None


def _lines_of(ctx: Context, rule: str, out: list[Finding]) -> dict[str, dict[str, int]]:
    """``{version_id: {category: cents}}`` for every version, amounts guarded."""
    grid: dict[str, dict[str, int]] = {}
    for v in _versions(ctx):
        vid = str(v.get("document_id", "?"))
        with amount_guard(rule, out):
            grid[vid] = budget_lines(v)
    return grid


def _vid(v: dict[str, Any]) -> str:
    return str(v.get("document_id", "?"))


def _role(v: dict[str, Any]) -> str:
    role = v.get("role")
    return role if isinstance(role, str) else "?"


def _members(ctx: Context) -> list[dict[str, Any]]:
    reg = ctx.one(DOC_FUNDING_REGISTER)
    if not isinstance(reg, dict):
        return []
    rows = reg.get("members")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _amendments(ctx: Context) -> list[dict[str, Any]]:
    log = ctx.one(DOC_AMENDMENT_LOG)
    if not isinstance(log, dict):
        return []
    rows = log.get("amendments")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


# --------------------------------------------------------------------------- #
# 1. Completeness
# --------------------------------------------------------------------------- #
_SEV_SET_COMPLETE = _sev("set_complete", Status.FAIL)


@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """The cycle file carries every artifact and a readable reporting period.

    Every later control assumes its artifact exists; this one owns absence, so a
    missing amendment log is one finding here rather than a different complaint
    from every rule that wanted it.
    """
    out: list[Finding] = []
    for doc_type in DOC_TYPES:
        if not ctx.docs(doc_type):
            out.append(
                Finding(
                    "set_complete",
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"no {doc_type} document in the cycle file; "
                    "every control that reads it stands down rather than "
                    "inventing the artifact",
                )
            )
    if ctx.period_start is None or ctx.period_end is None:
        out.append(
            Finding(
                "set_complete",
                Status.FAIL,
                "-",
                "period_start/period_end missing or unreadable; the date "
                "controls stand down rather than measuring versions against a "
                "period they had to invent",
            )
        )
    elif ctx.period_end < ctx.period_start:
        out.append(
            Finding(
                "set_complete",
                Status.FAIL,
                "-",
                f"period ends {ctx.period_end} before it starts {ctx.period_start}",
            )
        )
    if not out:
        out.append(
            _ok("set_complete", f"all {len(DOC_TYPES)} artifacts present, period readable")
        )
    return out


# --------------------------------------------------------------------------- #
# 2. Version inventory
# --------------------------------------------------------------------------- #
_SEV_VER_DECLARED = _sev("ver_versions_declared", Status.FAIL)


@check("ver_versions_declared")
def check_ver_versions_declared(ctx: Context) -> list[Finding]:
    """Every budget version declares an id, a known role and a prepared date.

    A copy with no provenance cannot be ranked against the others, so it cannot
    be graded stale, superseded or authoritative. Undeclared provenance is the
    condition that lets a copy circulate on nothing but familiarity.
    """
    out: list[Finding] = []
    seen: set[str] = set()
    for v in _versions(ctx):
        vid = _vid(v)
        loc = ctx.loc(v, "document_id")
        if vid == "?":
            out.append(Finding("ver_versions_declared", Status.FAIL, loc, "version carries no document_id"))
        elif vid in seen:
            out.append(
                Finding(
                    "ver_versions_declared",
                    Status.FAIL,
                    loc,
                    f"duplicate version id {vid}; two copies cannot share one identity",
                )
            )
        seen.add(vid)
        if _role(v) not in VERSION_ROLES:
            out.append(
                Finding(
                    "ver_versions_declared",
                    Status.FAIL,
                    ctx.loc(v, "role"),
                    f"version {vid} declares role {_role(v)!r}, not one of "
                    f"{', '.join(VERSION_ROLES)}",
                )
            )
        if parse_iso(v.get("prepared_date")) is None:
            out.append(
                Finding(
                    "ver_versions_declared",
                    Status.FAIL,
                    ctx.loc(v, "prepared_date"),
                    f"version {vid} carries no readable prepared_date; without one "
                    "it cannot be ranked against the copies it disagrees with",
                )
            )
    if not out:
        out.append(_ok("ver_versions_declared", f"{len(_versions(ctx))} versions fully declared"))
    return out


_SEV_VER_SINGLE = _sev("ver_single_baseline", Status.FAIL)


@check("ver_single_baseline")
def check_ver_single_baseline(ctx: Context) -> list[Finding]:
    """Exactly one version is the contractual baseline, and the agreement names it.

    Variance is measured against the baseline. Two baselines means two different
    variances are both defensible; none means the number every report quotes is
    measured against whichever copy the preparer had open.
    """
    out: list[Finding] = []
    found = version_by_role(_versions(ctx), ROLE_BASELINE)
    if len(found) != 1:
        out.append(
            Finding(
                "ver_single_baseline",
                Status.FAIL,
                f"{DOC_BUDGET_VERSION}:-",
                f"{len(found)} versions carry role {ROLE_BASELINE!r}; exactly one "
                "must, because every variance in the reporting pack is measured "
                "against it",
            )
        )
        return out
    agr = ctx.one(DOC_AGREEMENT)
    named = agr.get("baseline_document_id") if isinstance(agr, dict) else None
    vid = _vid(found[0])
    if isinstance(named, str) and named != vid:
        out.append(
            Finding(
                "ver_single_baseline",
                Status.FAIL,
                ctx.loc(agr, "baseline_document_id"),
                f"the agreement names {named} as the baseline but version {vid} "
                "carries the baseline role; the governing copy is whichever the "
                "executed agreement says it is",
            )
        )
    if not out:
        out.append(_ok("ver_single_baseline", f"one baseline ({vid}), named by the agreement"))
    return out


_SEV_VER_POSTDATES = _sev("ver_baseline_postdates_agreement", Status.FAIL)


@check("ver_baseline_postdates_agreement")
def check_ver_baseline_postdates_agreement(ctx: Context) -> list[Finding]:
    """The contractual baseline is not dated before the agreement it is an exhibit to.

    An exhibit prepared before the deal it is attached to was executed is, on its
    face, a different document from the one the parties signed against -- however
    familiar its numbers look.
    """
    out: list[Finding] = []
    base = _baseline(ctx)
    agr = ctx.one(DOC_AGREEMENT)
    if base is None or not isinstance(agr, dict):
        return [_ok("ver_baseline_postdates_agreement", "stood down: no single baseline to test")]
    executed = parse_iso(agr.get("executed_date"))
    prepared = parse_iso(base.get("prepared_date"))
    if executed is None or prepared is None:
        return [_ok("ver_baseline_postdates_agreement", "stood down: dates unreadable")]
    if prepared < executed:
        out.append(
            Finding(
                "ver_baseline_postdates_agreement",
                Status.FAIL,
                ctx.loc(base, "prepared_date"),
                f"baseline {_vid(base)} prepared {prepared}, before the agreement "
                f"was executed {executed}; an exhibit cannot predate the agreement "
                "it is attached to",
            )
        )
    else:
        out.append(
            _ok(
                "ver_baseline_postdates_agreement",
                f"baseline prepared {prepared}, on or after execution {executed}",
            )
        )
    return out


_SEV_VER_WITHIN = _sev("ver_prepared_within_period", Status.FAIL)


@check("ver_prepared_within_period")
def check_ver_prepared_within_period(ctx: Context) -> list[Finding]:
    """No version claims to have been prepared after the period it reports on.

    A copy dated beyond the period end is either mis-stamped or belongs to a
    later cycle; either way it is not evidence for this one.
    """
    out: list[Finding] = []
    end = ctx.period_end
    if end is None:
        return [_ok("ver_prepared_within_period", "stood down: period unreadable")]
    for v in _versions(ctx):
        prepared = parse_iso(v.get("prepared_date"))
        if prepared is not None and prepared > end:
            out.append(
                Finding(
                    "ver_prepared_within_period",
                    Status.FAIL,
                    ctx.loc(v, "prepared_date"),
                    f"version {_vid(v)} prepared {prepared}, after the period ended "
                    f"{end}; it is evidence for a later cycle, not this one",
                )
            )
    if not out:
        out.append(_ok("ver_prepared_within_period", f"every version prepared on or before {end}"))
    return out


# --------------------------------------------------------------------------- #
# 3. Agreement between copies
# --------------------------------------------------------------------------- #
_SEV_LIN_CATS = _sev("lin_categories_reconcile", Status.FAIL)


@check("lin_categories_reconcile")
def check_lin_categories_reconcile(ctx: Context) -> list[Finding]:
    """Every version carries the same category set as the baseline.

    Reconciling the sets *before* comparing values is the load-bearing step. A
    comparison that walks the baseline's lines and looks each up in another copy
    silently skips whatever was renamed, split or merged -- which is precisely
    the line that moved.
    """
    out: list[Finding] = []
    base = _baseline(ctx)
    if base is None:
        return [_ok("lin_categories_reconcile", "stood down: no single baseline to compare against")]
    grid = _lines_of(ctx, "lin_categories_reconcile", out)
    base_lines = grid.get(_vid(base), {})
    for v in _versions(ctx):
        vid = _vid(v)
        if vid == _vid(base):
            continue
        _paired, base_only, other_only = pair_lines(base_lines, grid.get(vid, {}))
        for cat in base_only:
            out.append(
                Finding(
                    "lin_categories_reconcile",
                    Status.FAIL,
                    ctx.loc(v, f"lines/{cat}"),
                    f"category {cat!r} is in the baseline but absent from {vid} "
                    f"({_role(v)}); a category present in one copy and not another "
                    "is what a renamed or split line looks like, and pairing on "
                    "names alone would skip it",
                )
            )
        for cat in other_only:
            out.append(
                Finding(
                    "lin_categories_reconcile",
                    Status.FAIL,
                    ctx.loc(v, f"lines/{cat}"),
                    f"category {cat!r} appears in {vid} ({_role(v)}) but not in the "
                    "baseline; it entered the budget without entering the governing copy",
                )
            )
    if not out:
        out.append(_ok("lin_categories_reconcile", "every version carries the baseline category set"))
    return out


_SEV_LIN_VALUES = _sev("lin_values_agree", Status.FAIL)


@check("lin_values_agree")
def check_lin_values_agree(ctx: Context) -> list[Finding]:
    """Every paired line agrees with the baseline, at or above materiality.

    Exact ``==`` decides whether a difference exists. The materiality threshold
    only grades one that has already been found -- it never suppresses the
    finding, because a line nobody reconciles is how a small difference becomes a
    large one.
    """
    out: list[Finding] = []
    base = _baseline(ctx)
    if base is None:
        return [_ok("lin_values_agree", "stood down: no single baseline to compare against")]
    grid = _lines_of(ctx, "lin_values_agree", out)
    base_lines = grid.get(_vid(base), {})
    threshold = ctx.materiality_cents
    for v in _versions(ctx):
        vid = _vid(v)
        if vid == _vid(base):
            continue
        other = grid.get(vid, {})
        paired, _bo, _oo = pair_lines(base_lines, other)
        reclass = {c for a, b, _amt in detect_reclassifications(base_lines, other) for c in (a, b)}
        for cat in paired:
            delta = other[cat] - base_lines[cat]
            if delta == 0 or cat in reclass:
                continue
            if abs(delta) >= threshold:
                out.append(
                    Finding(
                        "lin_values_agree",
                        Status.FAIL,
                        ctx.loc(v, f"lines/{cat}"),
                        f"{cat}: {vid} ({_role(v)}) carries {fmt(other[cat])} against "
                        f"the baseline {fmt(base_lines[cat])}, a difference of "
                        f"{fmt(delta)} at or above the {fmt(threshold)} materiality "
                        "threshold",
                    )
                )
    if not out:
        out.append(_ok("lin_values_agree", "every paired line agrees with the baseline"))
    return out


_SEV_LIN_IMMATERIAL = _sev("lin_immaterial_drift_review", Status.FLAG)


@check("lin_immaterial_drift_review")
def check_lin_immaterial_drift_review(ctx: Context) -> list[Finding]:
    """A confirmed line difference below materiality is surfaced for review.

    Below-threshold differences are still differences. They are graded FLAG so a
    reviewer sees them accumulate rather than discovering them once they have
    crossed the threshold together.
    """
    out: list[Finding] = []
    base = _baseline(ctx)
    if base is None:
        return [_ok("lin_immaterial_drift_review", "stood down: no single baseline")]
    grid = _lines_of(ctx, "lin_immaterial_drift_review", out)
    base_lines = grid.get(_vid(base), {})
    threshold = ctx.materiality_cents
    for v in _versions(ctx):
        vid = _vid(v)
        if vid == _vid(base):
            continue
        other = grid.get(vid, {})
        paired, _bo, _oo = pair_lines(base_lines, other)
        reclass = {c for a, b, _amt in detect_reclassifications(base_lines, other) for c in (a, b)}
        for cat in paired:
            delta = other[cat] - base_lines[cat]
            if delta == 0 or cat in reclass or abs(delta) >= threshold:
                continue
            out.append(
                Finding(
                    "lin_immaterial_drift_review",
                    Status.FLAG,
                    ctx.loc(v, f"lines/{cat}"),
                    f"{cat}: {vid} differs from the baseline by {fmt(delta)}, below "
                    f"the {fmt(threshold)} threshold -- reported so it is reconciled "
                    "now rather than after it has grown",
                )
            )
    if not out:
        out.append(_ok("lin_immaterial_drift_review", "no sub-threshold line differences"))
    return out


_SEV_LIN_TOTALS = _sev("lin_totals_agree", Status.FAIL)


@check("lin_totals_agree")
def check_lin_totals_agree(ctx: Context) -> list[Finding]:
    """Every version's derived total equals the baseline's, and its stated total.

    The total is summed from the lines, never read from a stated figure, and then
    compared to the stated figure. A stated total that disagrees with its own
    lines is the shape a hand-maintained summary takes.
    """
    out: list[Finding] = []
    base = _baseline(ctx)
    if base is None:
        return [_ok("lin_totals_agree", "stood down: no single baseline")]
    with amount_guard("lin_totals_agree", out):
        base_total = budget_total(base)
    for v in _versions(ctx):
        vid = _vid(v)
        with amount_guard("lin_totals_agree", out):
            derived = budget_total(v)
        stated = v.get("stated_total_cents")
        if isinstance(stated, int) and not isinstance(stated, bool) and stated != derived:
            out.append(
                Finding(
                    "lin_totals_agree",
                    Status.FAIL,
                    ctx.loc(v, "stated_total_cents"),
                    f"{vid} states a total of {fmt(stated)} but its own lines sum to "
                    f"{fmt(derived)}; the stated figure was typed, not computed",
                )
            )
        if vid != _vid(base) and derived != base_total:
            gap = derived - base_total
            material = abs(gap) >= ctx.materiality_cents
            out.append(
                Finding(
                    "lin_totals_agree",
                    Status.FAIL if material else Status.FLAG,
                    ctx.loc(v, "lines"),
                    f"{vid} ({_role(v)}) totals {fmt(derived)} against the baseline "
                    f"{fmt(base_total)}, a difference of {fmt(gap)}"
                    + (
                        "; each copy can be internally perfect and still disagree"
                        if material
                        else f", below the {fmt(ctx.materiality_cents)} threshold -- "
                        "reported for review rather than as a failure, because the "
                        "aggregate of a sub-threshold line difference is the same "
                        "difference"
                    ),
                )
            )
    if not out:
        out.append(_ok("lin_totals_agree", f"every version totals {fmt(base_total)}"))
    return out


_SEV_LIN_PHASE = _sev("lin_phase_totals_tie", Status.FAIL)


@check("lin_phase_totals_tie")
def check_lin_phase_totals_tie(ctx: Context) -> list[Finding]:
    """Each version's phase totals sum to its budget total, with no unphased line.

    A line carrying no phase is excluded from both phase totals while still
    sitting in the grand total, so the split silently stops footing.
    """
    out: list[Finding] = []
    for v in _versions(ctx):
        vid = _vid(v)
        with amount_guard("lin_phase_totals_tie", out):
            phases = phase_totals(v)
            derived = budget_total(v)
        unknown = sorted(p for p in phases if p not in PHASES)
        for p in unknown:
            out.append(
                Finding(
                    "lin_phase_totals_tie",
                    Status.FAIL,
                    ctx.loc(v, f"lines/phase/{p}"),
                    f"{vid} carries phase {p!r}, not one of {', '.join(PHASES)}",
                )
            )
        if sum(phases.values()) != derived:
            out.append(
                Finding(
                    "lin_phase_totals_tie",
                    Status.FAIL,
                    ctx.loc(v, "lines/phase"),
                    f"{vid} phase totals sum to {fmt(sum(phases.values()))} against a "
                    f"budget total of {fmt(derived)}; a line with no phase sits in the "
                    "total while belonging to neither side of the split",
                )
            )
    if not out:
        out.append(_ok("lin_phase_totals_tie", "every version's phase totals foot to its total"))
    return out


_SEV_LIN_RECLASS = _sev("lin_reclass_review", Status.FLAG)


@check("lin_reclass_review")
def check_lin_reclass_review(ctx: Context) -> list[Finding]:
    """Offsetting line movements with an unchanged total are graded as re-carves.

    Two lines moving by equal and opposite amounts is a reclassification, not a
    budget change. Reporting it as a change buries the genuine ones; reporting it
    as nothing at all hides a re-carve nobody approved.
    """
    out: list[Finding] = []
    base = _baseline(ctx)
    if base is None:
        return [_ok("lin_reclass_review", "stood down: no single baseline")]
    grid = _lines_of(ctx, "lin_reclass_review", out)
    base_lines = grid.get(_vid(base), {})
    for v in _versions(ctx):
        vid = _vid(v)
        if vid == _vid(base):
            continue
        for frm, to, amt in detect_reclassifications(base_lines, grid.get(vid, {})):
            out.append(
                Finding(
                    "lin_reclass_review",
                    Status.FLAG,
                    ctx.loc(v, f"lines/{frm}"),
                    f"{vid} ({_role(v)}) moves {fmt(amt)} from {frm} to {to} with the "
                    "total unchanged -- a re-carve of the same money rather than a "
                    "budget change, and it still needs an approval behind it",
                )
            )
    if not out:
        out.append(_ok("lin_reclass_review", "no offsetting movements between versions"))
    return out


# --------------------------------------------------------------------------- #
# 4. Currency of each copy
# --------------------------------------------------------------------------- #
_SEV_STL_THROUGH = _sev("stl_cost_through_current", Status.FAIL)


@check("stl_cost_through_current")
def check_stl_cost_through_current(ctx: Context) -> list[Finding]:
    """A version reporting cost-to-date carries a cost-through date near period end.

    A copy whose cost-through date is months behind the period being reported was
    right when it was prepared. Every figure read off it since is quoted with a
    confidence the document does not support.
    """
    out: list[Finding] = []
    end = ctx.period_end
    if end is None:
        return [_ok("stl_cost_through_current", "stood down: period unreadable")]
    band = ctx.stale_days
    for v in _versions(ctx):
        through = parse_iso(v.get("cost_through_date"))
        if through is None:
            continue
        if through > end:
            out.append(
                Finding(
                    "stl_cost_through_current",
                    Status.FAIL,
                    ctx.loc(v, "cost_through_date"),
                    f"{_vid(v)} reports cost through {through}, beyond the period end "
                    f"{end}; it carries cost this cycle has not incurred",
                )
            )
        elif (end - through).days > band:
            out.append(
                Finding(
                    "stl_cost_through_current",
                    Status.FAIL,
                    ctx.loc(v, "cost_through_date"),
                    f"{_vid(v)} ({_role(v)}) reports cost only through {through}, "
                    f"{(end - through).days} days behind the period end {end} and "
                    f"outside the {band}-day band; it is stale rather than wrong, "
                    "which is why nobody notices",
                )
            )
    if not out:
        out.append(_ok("stl_cost_through_current", f"every reporting version is current to within {band} days"))
    return out


_SEV_STL_SUMMARY = _sev("stl_summary_not_superseded", Status.FLAG)


@check("stl_summary_not_superseded")
def check_stl_summary_not_superseded(ctx: Context) -> list[Finding]:
    """A summary restatement is not older than the copy it restates.

    A memo circulated to a lender quoting a superseded working model is the
    mechanism by which a stale figure escapes the building.
    """
    out: list[Finding] = []
    working = version_by_role(_versions(ctx), ROLE_WORKING)
    latest = max(
        (parse_iso(w.get("prepared_date")) for w in working if parse_iso(w.get("prepared_date"))),
        default=None,
    )
    if latest is None:
        return [_ok("stl_summary_not_superseded", "stood down: no dated working model")]
    for s in version_by_role(_versions(ctx), ROLE_SUMMARY):
        prepared = parse_iso(s.get("prepared_date"))
        if prepared is not None and prepared < latest:
            out.append(
                Finding(
                    "stl_summary_not_superseded",
                    Status.FLAG,
                    ctx.loc(s, "prepared_date"),
                    f"summary {_vid(s)} prepared {prepared} restates a budget the "
                    f"working model has moved past ({latest}); a memo already in "
                    "circulation is quoting figures that changed after it left",
                )
            )
    if not out:
        out.append(_ok("stl_summary_not_superseded", "no summary predates the working model"))
    return out


# --------------------------------------------------------------------------- #
# 5. Amendments
# --------------------------------------------------------------------------- #
_SEV_AMD_FOOT = _sev("amd_change_columns_foot", Status.FAIL)


@check("amd_change_columns_foot")
def check_amd_change_columns_foot(ctx: Context) -> list[Finding]:
    """On the billing instrument, approved + previous + current == revised, per line.

    The revised figure is what the investor is billed against. Re-deriving it
    from its own change columns is the only way to catch one that was typed.
    """
    out: list[Finding] = []
    for v in version_by_role(_versions(ctx), ROLE_BILLING):
        vid = _vid(v)
        rows = v.get("lines")
        if not isinstance(rows, list):
            continue
        for idx, row in enumerate(rows):
            if not isinstance(row, dict) or "approved_cents" not in row:
                continue
            with amount_guard("amd_change_columns_foot", out):
                expected = revised_from_changes(row, vid, idx)
                actual = require_cents(
                    f"budget_version[{vid}]/lines[{idx}]/amount_cents",
                    row.get("amount_cents"),
                )
                if expected != actual:
                    cat = row.get("category", "?")
                    out.append(
                        Finding(
                            "amd_change_columns_foot",
                            Status.FAIL,
                            ctx.loc(v, f"lines/{cat}"),
                            f"{cat}: revised reads {fmt(actual)} but approved plus "
                            f"changes derives {fmt(expected)}, a difference of "
                            f"{fmt(actual - expected)}; the revised column was typed "
                            "rather than computed",
                        )
                    )
    if not out:
        out.append(_ok("amd_change_columns_foot", "every billing line re-derives from its change columns"))
    return out


_SEV_AMD_TRACE = _sev("amd_changes_trace_to_log", Status.FAIL)


@check("amd_changes_trace_to_log")
def check_amd_changes_trace_to_log(ctx: Context) -> list[Finding]:
    """Every non-zero current change traces to an approved amendment for its amount.

    A change with no approval behind it is a movement someone made; a change
    whose approval is for a different figure is worse, because the paperwork
    exists and reads clean.
    """
    out: list[Finding] = []
    approved: dict[str, int] = {}
    for a in _amendments(ctx):
        cat = a.get("category")
        if not isinstance(cat, str) or a.get("state") != CHANGE_APPROVED:
            continue
        with amount_guard("amd_changes_trace_to_log", out):
            approved[cat] = approved.get(cat, 0) + require_cents(
                f"amendment_log/{cat}/amount_cents", a.get("amount_cents")
            )
    for v in version_by_role(_versions(ctx), ROLE_BILLING):
        vid = _vid(v)
        rows = v.get("lines")
        if not isinstance(rows, list):
            continue
        for idx, row in enumerate(rows):
            if not isinstance(row, dict) or "current_changes_cents" not in row:
                continue
            cat = row.get("category")
            if not isinstance(cat, str):
                continue
            with amount_guard("amd_changes_trace_to_log", out):
                change = require_cents(
                    f"budget_version[{vid}]/lines[{idx}]/current_changes_cents",
                    row.get("current_changes_cents"),
                )
            if change == 0:
                continue
            backing = approved.get(cat, 0)
            if backing != change:
                out.append(
                    Finding(
                        "amd_changes_trace_to_log",
                        Status.FAIL,
                        ctx.loc(v, f"lines/{cat}"),
                        f"{cat}: current change of {fmt(change)} is backed by "
                        f"{fmt(backing)} of approved amendments; a movement is only "
                        "as good as the approval behind it",
                    )
                )
    if not out:
        out.append(_ok("amd_changes_trace_to_log", "every current change traces to an approved amendment"))
    return out


_SEV_AMD_PENDING = _sev("amd_pending_not_billed", Status.FAIL)


@check("amd_pending_not_billed")
def check_amd_pending_not_billed(ctx: Context) -> list[Finding]:
    """A pending amendment has not been billed as though it were approved.

    Pending means the counterparty has not agreed. Billing it converts a request
    into a fact without anyone deciding to.
    """
    out: list[Finding] = []
    for a in _amendments(ctx):
        state = a.get("state")
        if state not in CHANGE_STATES:
            out.append(
                Finding(
                    "amd_pending_not_billed",
                    Status.FAIL,
                    f"{DOC_AMENDMENT_LOG}:{a.get('amendment_id', '?')}/state",
                    f"amendment state {state!r} is not one of {', '.join(CHANGE_STATES)}",
                )
            )
    pending = {
        a.get("category")
        for a in _amendments(ctx)
        if a.get("state") == CHANGE_PENDING and isinstance(a.get("category"), str)
    }
    for v in version_by_role(_versions(ctx), ROLE_BILLING):
        rows = v.get("lines")
        if not isinstance(rows, list):
            continue
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            cat = row.get("category")
            if cat not in pending:
                continue
            with amount_guard("amd_pending_not_billed", out):
                change = require_cents(
                    f"budget_version[{_vid(v)}]/lines[{idx}]/current_changes_cents",
                    row.get("current_changes_cents", 0),
                )
            if change != 0:
                out.append(
                    Finding(
                        "amd_pending_not_billed",
                        Status.FAIL,
                        ctx.loc(v, f"lines/{cat}"),
                        f"{cat}: {fmt(change)} billed as a current change while its "
                        "amendment is still pending; billing it decides the question "
                        "the counterparty has not answered",
                    )
                )
    if not out:
        out.append(_ok("amd_pending_not_billed", "no pending amendment has been billed"))
    return out


_SEV_AMD_LOCKED = _sev("amd_locked_lines_unchanged", Status.FAIL)


@check("amd_locked_lines_unchanged")
def check_amd_locked_lines_unchanged(ctx: Context) -> list[Finding]:
    """A line marked locked carries no change in any copy.

    Locked lines are the ones the parties fixed at closing. Movement in one is
    not a budget revision; it is a term being renegotiated in a spreadsheet.
    """
    out: list[Finding] = []
    base = _baseline(ctx)
    if base is None:
        return [_ok("amd_locked_lines_unchanged", "stood down: no single baseline")]
    locked: set[str] = set()
    rows = base.get("lines")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("locked") is True:
                cat = row.get("category")
                if isinstance(cat, str):
                    locked.add(cat)
    if not locked:
        return [_ok("amd_locked_lines_unchanged", "no locked lines declared")]
    grid = _lines_of(ctx, "amd_locked_lines_unchanged", out)
    base_lines = grid.get(_vid(base), {})
    for v in _versions(ctx):
        vid = _vid(v)
        if vid == _vid(base):
            continue
        other = grid.get(vid, {})
        for cat in sorted(locked):
            if cat in other and cat in base_lines and other[cat] != base_lines[cat]:
                out.append(
                    Finding(
                        "amd_locked_lines_unchanged",
                        Status.FAIL,
                        ctx.loc(v, f"lines/{cat}"),
                        f"{cat} is locked at {fmt(base_lines[cat])} but {vid} carries "
                        f"{fmt(other[cat])}; a locked line moving is a term being "
                        "renegotiated, not a budget being revised",
                    )
                )
    if not out:
        out.append(_ok("amd_locked_lines_unchanged", f"{len(locked)} locked lines unchanged across every copy"))
    return out


# --------------------------------------------------------------------------- #
# 6. Derived schedules
# --------------------------------------------------------------------------- #
_SEV_DRV_INPUTS = _sev("drv_inputs_declared", Status.FAIL)


@check("drv_inputs_declared")
def check_drv_inputs_declared(ctx: Context) -> list[Finding]:
    """Every milestone a derived schedule declares as an input exists in the set."""
    out: list[Finding] = []
    known = set(milestone_dates(ctx.one(DOC_MILESTONE_SET)))
    for s in ctx.docs(DOC_DERIVED_SCHEDULE):
        for mid in schedule_inputs(s):
            if mid not in known:
                out.append(
                    Finding(
                        "drv_inputs_declared",
                        Status.FAIL,
                        ctx.loc(s, f"input_milestones/{mid}"),
                        f"schedule {s.get('schedule_id', '?')} declares milestone "
                        f"{mid!r} as an input, but no such milestone exists",
                    )
                )
    if not out:
        out.append(_ok("drv_inputs_declared", "every declared schedule input exists"))
    return out


_SEV_DRV_MILESTONES = _sev("drv_milestones_populated", Status.FAIL)


@check("drv_milestones_populated")
def check_drv_milestones_populated(ctx: Context) -> list[Finding]:
    """Every milestone a derived schedule depends on carries a date.

    This is the quiet one. Blank a milestone and the schedule does not error: it
    keeps the last amortisation it was handed, and the figure it drives stops
    matching the term it is meant to span. Nothing downstream looks wrong.
    """
    out: list[Finding] = []
    dates = milestone_dates(ctx.one(DOC_MILESTONE_SET))
    for s in ctx.docs(DOC_DERIVED_SCHEDULE):
        for mid in schedule_inputs(s):
            if mid in dates and dates[mid] is None:
                out.append(
                    Finding(
                        "drv_milestones_populated",
                        Status.FAIL,
                        ctx.loc(s, f"input_milestones/{mid}"),
                        f"schedule {s.get('schedule_id', '?')} amortises across "
                        f"milestone {mid!r}, which carries no date; the schedule will "
                        "not error, it will silently keep its last amortisation",
                    )
                )
    if not out:
        out.append(_ok("drv_milestones_populated", "every schedule input carries a date"))
    return out


_SEV_DRV_CONSERVE = _sev("drv_instalments_conserve", Status.FAIL)


@check("drv_instalments_conserve")
def check_drv_instalments_conserve(ctx: Context) -> list[Finding]:
    """A schedule's instalments sum to its amortisation base, over its own periods."""
    out: list[Finding] = []
    for s in ctx.docs(DOC_DERIVED_SCHEDULE):
        sid = s.get("schedule_id", "?")
        inst = s.get("instalments_cents")
        if not isinstance(inst, list):
            continue
        with amount_guard("drv_instalments_conserve", out):
            parts = [
                require_cents(f"derived_schedule[{sid}]/instalments_cents[{i}]", x)
                for i, x in enumerate(inst)
            ]
            base = require_cents(f"derived_schedule[{sid}]/base_cents", s.get("base_cents"))
        periods = s.get("periods")
        if isinstance(periods, int) and not isinstance(periods, bool) and len(parts) != periods:
            out.append(
                Finding(
                    "drv_instalments_conserve",
                    Status.FAIL,
                    ctx.loc(s, "instalments_cents"),
                    f"schedule {sid} declares {periods} periods but carries "
                    f"{len(parts)} instalments",
                )
            )
        if sum(parts) != base:
            out.append(
                Finding(
                    "drv_instalments_conserve",
                    Status.FAIL,
                    ctx.loc(s, "instalments_cents"),
                    f"schedule {sid} instalments sum to {fmt(sum(parts))} against a "
                    f"base of {fmt(base)}; an amortisation that does not conserve its "
                    "base pays out a different figure than the one approved",
                )
            )
    if not out:
        out.append(_ok("drv_instalments_conserve", "every schedule conserves its base"))
    return out


_SEV_DRV_BASE = _sev("drv_base_net_of_advances", Status.FAIL)


@check("drv_base_net_of_advances")
def check_drv_base_net_of_advances(ctx: Context) -> list[Finding]:
    """The amortisation base equals the total fee less advances already taken.

    Amortising the gross figure after advances have been drawn pays the advanced
    portion twice, and every instalment thereafter is overstated by the same
    proportion.
    """
    out: list[Finding] = []
    for s in ctx.docs(DOC_DERIVED_SCHEDULE):
        sid = s.get("schedule_id", "?")
        if "total_cents" not in s:
            continue
        with amount_guard("drv_base_net_of_advances", out):
            total = require_cents(f"derived_schedule[{sid}]/total_cents", s.get("total_cents"))
            advances = require_cents(
                f"derived_schedule[{sid}]/advances_cents", s.get("advances_cents", 0)
            )
            base = require_cents(f"derived_schedule[{sid}]/base_cents", s.get("base_cents"))
            if base != total - advances:
                out.append(
                    Finding(
                        "drv_base_net_of_advances",
                        Status.FAIL,
                        ctx.loc(s, "base_cents"),
                        f"schedule {sid} amortises {fmt(base)} where total less "
                        f"advances is {fmt(total - advances)}; the advanced portion "
                        "would be paid a second time across the instalments",
                    )
                )
    if not out:
        out.append(_ok("drv_base_net_of_advances", "every base is net of advances taken"))
    return out


_SEV_DRV_CAP = _sev("drv_cap_not_exceeded", Status.FAIL)


@check("drv_cap_not_exceeded")
def check_drv_cap_not_exceeded(ctx: Context) -> list[Finding]:
    """Advances taken under a schedule stay inside its declared cap."""
    out: list[Finding] = []
    for s in ctx.docs(DOC_DERIVED_SCHEDULE):
        sid = s.get("schedule_id", "?")
        if "cap_cents" not in s:
            continue
        with amount_guard("drv_cap_not_exceeded", out):
            cap = require_cents(f"derived_schedule[{sid}]/cap_cents", s.get("cap_cents"))
            advances = require_cents(
                f"derived_schedule[{sid}]/advances_cents", s.get("advances_cents", 0)
            )
            if advances > cap:
                out.append(
                    Finding(
                        "drv_cap_not_exceeded",
                        Status.FAIL,
                        ctx.loc(s, "advances_cents"),
                        f"schedule {sid} has advanced {fmt(advances)} against a cap of "
                        f"{fmt(cap)}, {fmt(advances - cap)} beyond it",
                    )
                )
    if not out:
        out.append(_ok("drv_cap_not_exceeded", "every schedule is inside its cap"))
    return out


# --------------------------------------------------------------------------- #
# 7. Funding
# --------------------------------------------------------------------------- #
_SEV_EQT_COMMIT = _sev("eqt_commitments_agree", Status.FAIL)


@check("eqt_commitments_agree")
def check_eqt_commitments_agree(ctx: Context) -> list[Finding]:
    """Each member's commitment is the same figure in every copy that states one.

    The remaining-commitment column of a funding request is derived from this. A
    commitment that differs between copies produces two defensible answers to
    "how much is left".
    """
    out: list[Finding] = []
    stated: dict[str, dict[str, int]] = {}
    for v in _versions(ctx):
        commits = v.get("commitments")
        if not isinstance(commits, dict):
            continue
        vid = _vid(v)
        for member, amount in commits.items():
            with amount_guard("eqt_commitments_agree", out):
                stated.setdefault(str(member), {})[vid] = require_cents(
                    f"budget_version[{vid}]/commitments/{member}", amount
                )
    for member, by_version in sorted(stated.items()):
        distinct = sorted(set(by_version.values()))
        if len(distinct) > 1:
            detail = ", ".join(f"{v}={fmt(a)}" for v, a in sorted(by_version.items()))
            out.append(
                Finding(
                    "eqt_commitments_agree",
                    Status.FAIL,
                    f"{DOC_BUDGET_VERSION}:-/commitments/{member}",
                    f"{member} is committed for {len(distinct)} different amounts "
                    f"across the copies ({detail}); the remaining-commitment figure "
                    "on a funding request depends on which copy was open",
                )
            )
    if not out:
        out.append(_ok("eqt_commitments_agree", f"{len(stated)} member commitments agree across copies"))
    return out


_SEV_EQT_SPLIT = _sev("eqt_split_matches_phase", Status.FAIL)


@check("eqt_split_matches_phase")
def check_eqt_split_matches_phase(ctx: Context) -> list[Finding]:
    """The funding split in force matches the agreement's ratio for the current phase.

    The split is a function of the phase, so a split compared without its phase is
    compared against the wrong ratio half the time.
    """
    out: list[Finding] = []
    agr = ctx.one(DOC_AGREEMENT)
    reg = ctx.one(DOC_FUNDING_REGISTER)
    if not isinstance(agr, dict) or not isinstance(reg, dict):
        return [_ok("eqt_split_matches_phase", "stood down: agreement or register absent")]
    phase = agr.get("phase")
    splits = agr.get("splits")
    if not isinstance(splits, dict) or phase not in splits:
        out.append(
            Finding(
                "eqt_split_matches_phase",
                Status.FAIL,
                ctx.loc(agr, "splits"),
                f"the agreement declares phase {phase!r} but carries no split for it",
            )
        )
        return out
    expected = splits[phase]
    if not isinstance(expected, dict):
        return [_ok("eqt_split_matches_phase", "stood down: split unreadable")]
    for m in _members(ctx):
        mid = str(m.get("member_id", "?"))
        want = expected.get(mid)
        got = m.get("split_bps")
        if not isinstance(want, int) or isinstance(want, bool):
            continue
        if not isinstance(got, int) or isinstance(got, bool) or got != want:
            out.append(
                Finding(
                    "eqt_split_matches_phase",
                    Status.FAIL,
                    ctx.loc(reg, f"members/{mid}/split_bps"),
                    f"{mid} funds at {got} bps in the register but the agreement sets "
                    f"{want} bps for phase {phase!r}; the ratio changes with the phase, "
                    "and the wrong one is only visibly wrong once money moves",
                )
            )
    total_bps = sum(
        v for v in expected.values() if isinstance(v, int) and not isinstance(v, bool)
    )
    if total_bps != 10000:
        out.append(
            Finding(
                "eqt_split_matches_phase",
                Status.FAIL,
                ctx.loc(agr, f"splits/{phase}"),
                f"phase {phase!r} splits sum to {total_bps} bps, not 10000",
            )
        )
    if not out:
        out.append(_ok("eqt_split_matches_phase", f"every member funds at the phase {phase!r} ratio"))
    return out


_SEV_EQT_WITHIN = _sev("eqt_contributed_within_commitment", Status.FAIL)


@check("eqt_contributed_within_commitment")
def check_eqt_contributed_within_commitment(ctx: Context) -> list[Finding]:
    """Contributed <= commitment <= cap, for every member.

    Three figures that are each individually plausible and only wrong in relation
    to each other.
    """
    out: list[Finding] = []
    reg = ctx.one(DOC_FUNDING_REGISTER)
    if not isinstance(reg, dict):
        return [_ok("eqt_contributed_within_commitment", "stood down: no funding register")]
    for m in _members(ctx):
        mid = str(m.get("member_id", "?"))
        with amount_guard("eqt_contributed_within_commitment", out):
            commitment = require_cents(
                f"funding_register/{mid}/commitment_cents", m.get("commitment_cents")
            )
            contributed = require_cents(
                f"funding_register/{mid}/contributed_cents", m.get("contributed_cents")
            )
            cap = require_cents(f"funding_register/{mid}/cap_cents", m.get("cap_cents"))
            if contributed > commitment:
                out.append(
                    Finding(
                        "eqt_contributed_within_commitment",
                        Status.FAIL,
                        ctx.loc(reg, f"members/{mid}/contributed_cents"),
                        f"{mid} has contributed {fmt(contributed)} against a commitment "
                        f"of {fmt(commitment)}, {fmt(contributed - commitment)} beyond it",
                    )
                )
            if commitment > cap:
                out.append(
                    Finding(
                        "eqt_contributed_within_commitment",
                        Status.FAIL,
                        ctx.loc(reg, f"members/{mid}/commitment_cents"),
                        f"{mid} is committed for {fmt(commitment)} against a cap of "
                        f"{fmt(cap)}; the commitment exceeds what the agreement permits "
                        "to be called",
                    )
                )
    if not out:
        out.append(
            _ok("eqt_contributed_within_commitment", "every member is inside commitment and cap")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one cycle file."""
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
    """Analyze every ``.json`` cycle file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of cycle-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
