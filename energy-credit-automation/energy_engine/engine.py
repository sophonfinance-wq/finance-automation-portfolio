"""
Energy-Efficient Home Credit (§45L) control engine (READ-ONLY).
===============================================================

Loads each credit file (a ``.json`` file produced by
:mod:`energy_engine.generate`) and runs an ordered *registry* of independent
controls over it.

The shape of the problem
------------------------
The §45L homebuilder credit is a per-unit credit. A builder earns a fixed
statutory amount for each newly built dwelling unit it sells, but only for a unit
that clears two gates at once: it closed (close-of-escrow) inside the fiscal-year
window being filed, and it holds an energy certificate from a certified rater. The
gross credit is the count of qualifying units times the dated statutory per-unit
amount, and every figure above it -- profit addback, tax effect, net benefit,
partner split -- is arithmetic on that product.

Three failures hide inside that, and none of them look wrong on a footed
worksheet: the unit that was claimed but closed outside the period, past the
sunset, or was never certified; the unit counted twice across two successive
period filings; and the rollup -- gross credit, certified-unit tie-out,
roll-forward identity, net-benefit derivation, partner allocation -- stated on a
number nobody recomputed from the unit register underneath it.

The registry is organised around that:

1. ``set_``   -- is the credit file complete and are the statutory dates readable?
2. ``unit_``  -- is the unit register sound and attributable to known projects?
3. ``elig_``  -- did every claimed unit close in the period and before the sunset?
4. ``cert_``  -- is every claimed unit certified by a rater?
5. ``dup_``   -- is any unit claimed again that a prior filing already claimed?
6. ``rate_``  -- does the per-unit and gross credit re-derive as units x rate?
7. ``rpt_``   -- does the final report's units x rate tie its total credit?
8. ``roll_``  -- do project, region and grand totals re-derive from the units?
9. ``fwd_``   -- does the roll-forward identity hold, and what remains to close?
10. ``net_``  -- do addback, tax effect and net benefit re-derive?
11. ``alloc_``-- do the partner shares re-derive and sum to the net benefit?
12. ``recon_``-- do the report, worksheet and closings schedule reconcile?

Design notes
------------
- **Strictly read-only.** Credit files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every credit figure is compared with exact
  ``==``.
- **One credit kernel.** Controls and the generator share the kernel in
  :mod:`energy_engine.credit`, so a determination cannot disagree with the data
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

from .credit import (
    Statute,
    Unit,
    closed_in_period,
    gross_credit_cents,
    net_benefit_cents,
    tax_effect_cents,
    unit_credit_cents,
    within_sunset,
)
from .model import (
    DOC_CLOSINGS_SCHEDULE,
    DOC_CREDIT_WORKSHEET,
    DOC_FINAL_REPORT,
    DOC_PARTNER_ALLOCATION,
    DOC_PERIOD_ROLLFORWARD,
    DOC_TYPES,
    DOC_UNIT_REGISTER,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import (
    AmountInvalidError,
    allocate_by_ratio,
    apply_rate,
    fmt,
    require_cents,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~energy_engine.money.AmountInvalidError` as a finding."""
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
# Credit-file helpers
# --------------------------------------------------------------------------- #
def _units(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_UNIT_REGISTER), "units")


def _unit_id(row: dict[str, Any]) -> str:
    value = row.get("unit_id")
    return value if isinstance(value, str) and value else "?"


def _claimed(row: dict[str, Any]) -> bool:
    return bool(row.get("claimed"))


def _projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CREDIT_WORKSHEET), "projects")


def _project_id(row: dict[str, Any]) -> str:
    value = row.get("project_id")
    return value if isinstance(value, str) and value else "?"


def _project_ids(ctx: Context) -> set[str]:
    return {_project_id(p) for p in _projects(ctx) if _project_id(p) != "?"}


def _partners(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PARTNER_ALLOCATION), "partners")


def _rollforward_projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PERIOD_ROLLFORWARD), "projects")


def _closings_projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CLOSINGS_SCHEDULE), "projects")


def _statute(ctx: Context) -> Statute | None:
    """Read the file-level statutory parameters, or ``None`` if unreadable.

    Reads the per-unit rate and effective rate leniently (non-int -> ``None``) so
    constructing the statute never raises; the controls that must surface a
    malformed cents figure read it through :func:`require_cents` themselves.
    """
    per_unit = ctx.data.get("statutory_per_unit_cents")
    eff = ctx.data.get("effective_rate_bps")
    start = _parse_date(ctx.period_start)
    end = _parse_date(ctx.period_end)
    sunset = _parse_date(ctx.sunset_date)
    if (
        isinstance(per_unit, bool)
        or not isinstance(per_unit, int)
        or isinstance(eff, bool)
        or not isinstance(eff, int)
        or start is None
        or end is None
        or sunset is None
    ):
        return None
    return Statute(
        per_unit_cents=per_unit,
        sunset_date=sunset,
        period_start=start,
        period_end=end,
        effective_rate_bps=eff,
    )


def _unit_from_row(row: dict[str, Any]) -> Unit | None:
    coe = _parse_date(row.get("coe_date"))
    if coe is None:
        return None
    return Unit(coe_date=coe, certified=bool(row.get("certified")), claimed=_claimed(row))


# --------------------------------------------------------------------------- #
# Shared re-derivation (also used by the generator)
# --------------------------------------------------------------------------- #
def recompute_project_units(ctx: Context, project_id: str) -> int:
    """The number of *claimed* register units belonging to one project."""
    return sum(
        1 for u in _units(ctx) if _text(u, "project_id") == project_id and _claimed(u)
    )


def recompute_closed_units(ctx: Context, project_id: str) -> int:
    """The number of register units belonging to one project (physically closed)."""
    return sum(1 for u in _units(ctx) if _text(u, "project_id") == project_id)


def recompute_project_summary(
    ctx: Context, project_id: str, region: str, statute: Statute
) -> dict[str, Any]:
    """Re-derive one project's whole worksheet line from its claimed units.

    Shared with the generator through :mod:`energy_engine.credit`, so the figures
    the engine recomputes are the ones that produced the data.
    """
    units = recompute_project_units(ctx, project_id)
    gross = gross_credit_cents(units, statute)
    return {
        "project_id": project_id,
        "region": region,
        "qualifying_units": units,
        "gross_credit_cents": gross,
        "addback_cents": gross,
        "tax_effect_cents": tax_effect_cents(gross, statute),
        "net_benefit_cents": net_benefit_cents(gross, statute),
    }


def recompute_partner_shares(ctx: Context, total_net_cents: int) -> list[int]:
    """Split the net benefit across partners by their integer basis-point shares.

    Uses the platform largest-remainder allocator so the shares sum exactly to the
    net benefit. Returns an empty list (rather than raising) when the ownership
    weights do not foot to 100%, leaving that to the allocation control.
    """
    weights = [_int(p, "ownership_bps") or 0 for p in _partners(ctx)]
    if sum(weights) != 10_000:
        return []
    return allocate_by_ratio(total_net_cents, weights)


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the credit file depends on is present, exactly once, and the
    statutory dates are readable.

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
                    f"{len(found)} {doc_type} documents present; the credit file carries "
                    f"exactly one of each",
                )
            )
    start = _parse_date(ctx.period_start)
    end = _parse_date(ctx.period_end)
    if start is None or end is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"period window {ctx.period_start!r}..{ctx.period_end!r} is not a readable "
                f"date range; every close-of-escrow test is measured to it",
            )
        )
    elif start > end:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"period window starts {start.isoformat()} after it ends "
                f"{end.isoformat()}; no unit could close inside it",
            )
        )
    if _parse_date(ctx.sunset_date) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"sunset_date {ctx.sunset_date!r} is not a readable date; the statutory "
                f"eligibility gate cannot be applied",
            )
        )
    if _statute(ctx) is None and _parse_date(ctx.period_start) is not None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                "statutory_per_unit_cents / effective_rate_bps are missing or not whole "
                "numbers; the credit cannot be re-derived",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} credit artifacts are present and the statute is readable",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# unit_ -- the unit register
# --------------------------------------------------------------------------- #
@check("unit_unique_ids")
def check_unit_unique_ids(ctx: Context) -> list[Finding]:
    """No unit id appears twice.

    The unit id is what a certificate, a closing and a credit are all attributed
    to. A duplicate makes a claimed credit ambiguous about which dwelling it is
    for -- and is how the same unit ends up counted twice.
    """
    rule = "unit_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _units(ctx):
        seen[_unit_id(row)] = seen.get(_unit_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"units/{uid}"),
            f"unit id {uid} appears {count} times; a credit that names it cannot be "
            f"attributed to one dwelling",
        )
        for uid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} unit ids are unique"))
    return out


@check("unit_required_fields")
def check_unit_required_fields(ctx: Context) -> list[Finding]:
    """Every unit carries the descriptive fields the controls read."""
    rule = "unit_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    if register is None:
        return []
    required = ("unit_id", "project_id", "address", "coe_date")
    out: list[Finding] = []
    for row in _units(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"units/{_unit_id(row)}"),
                    f"unit {_unit_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_units(ctx))} units carry their required fields",
            )
        )
    return out


@check("unit_project_known")
def check_unit_project_known(ctx: Context) -> list[Finding]:
    """Every unit names a project that the credit worksheet accounts for.

    A unit attributed to a project the worksheet does not carry has nowhere to
    roll up to; its credit would be counted in the register and lost in the
    worksheet, or vice versa.
    """
    rule = "unit_project_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    if register is None or worksheet is None:
        return []
    known = _project_ids(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"units/{_unit_id(row)}/project_id"),
            f"unit {_unit_id(row)} names project {_text(row, 'project_id')!r}, which the "
            f"credit worksheet does not carry",
        )
        for row in _units(ctx)
        if _text(row, "project_id") and _text(row, "project_id") not in known
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every unit names a project on the worksheet")
        )
    return out


# --------------------------------------------------------------------------- #
# elig_ -- per-unit eligibility gating
# --------------------------------------------------------------------------- #
@check("elig_close_in_period")
def check_elig_close_in_period(ctx: Context) -> list[Finding]:
    """Every claimed unit closed inside the fiscal-year window.

    A unit counts in a fiscal year only if its close-of-escrow date falls in that
    period. A claim on a unit that closed in a different year takes the credit into
    the wrong year -- or takes it at all, if that year was never open.
    """
    rule = "elig_close_in_period"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    statute = _statute(ctx)
    if register is None or statute is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _units(ctx):
        if not _claimed(row):
            continue
        coe = _parse_date(row.get("coe_date"))
        if coe is None:
            continue  # unit_required_fields owns this
        checked += 1
        if not closed_in_period(coe, statute):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"units/{_unit_id(row)}/coe_date"),
                    f"claimed unit {_unit_id(row)} closed {coe.isoformat()}, outside the "
                    f"fiscal-year window {statute.period_start.isoformat()}.."
                    f"{statute.period_end.isoformat()}; it cannot be claimed here",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} claimed units closed in the period")
        )
    return out


@check("elig_within_sunset")
def check_elig_within_sunset(ctx: Context) -> list[Finding]:
    """Every claimed unit closed on or before the statutory sunset.

    The credit sunsets on a statutory date; a unit that closed after it earns
    nothing even if it closed inside the fiscal year. The gate is ``<=`` -- a unit
    closing exactly on the sunset date is still eligible.
    """
    rule = "elig_within_sunset"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    statute = _statute(ctx)
    if register is None or statute is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _units(ctx):
        if not _claimed(row):
            continue
        coe = _parse_date(row.get("coe_date"))
        if coe is None:
            continue
        checked += 1
        if not within_sunset(coe, statute):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"units/{_unit_id(row)}/coe_date"),
                    f"claimed unit {_unit_id(row)} closed {coe.isoformat()}, after the "
                    f"statutory sunset {statute.sunset_date.isoformat()}; the credit had "
                    f"lapsed",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} claimed units closed within the sunset"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cert_ -- certification completeness
# --------------------------------------------------------------------------- #
@check("cert_present_for_credited")
def check_cert_present_for_credited(ctx: Context) -> list[Finding]:
    """Every claimed unit is certified and carries a certificate reference.

    Only a closed **and** certified unit flows to the credit. A claimed unit with
    no energy certificate is a unit the builder is claiming it cannot substantiate.
    """
    rule = "cert_present_for_credited"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _units(ctx):
        if not _claimed(row):
            continue
        checked += 1
        if not bool(row.get("certified")) or not _text(row, "certificate_ref"):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"units/{_unit_id(row)}/certificate_ref"),
                    f"claimed unit {_unit_id(row)} has no RESNET/HERS certificate on file; an "
                    f"uncertified closing cannot be claimed",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} claimed units are certified")
        )
    return out


@check("cert_rater_id")
def check_cert_rater_id(ctx: Context) -> list[Finding]:
    """Every certified, claimed unit names the rater who signed its certificate.

    One certificate per dwelling, signed by a certified rater carrying a rater id.
    A certificate with no rater id is unsigned evidence -- it names no one
    accountable for the energy determination it attests.
    """
    rule = "cert_rater_id"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _units(ctx):
        if not _claimed(row) or not bool(row.get("certified")):
            continue
        checked += 1
        if not _text(row, "rater_id"):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"units/{_unit_id(row)}/rater_id"),
                    f"unit {_unit_id(row)} carries a certificate with no rater id; the "
                    f"energy determination is unsigned",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} certificates name their rater")
        )
    return out


# --------------------------------------------------------------------------- #
# dup_ -- no double count across filings
# --------------------------------------------------------------------------- #
@check("dup_no_double_count")
def check_dup_no_double_count(ctx: Context) -> list[Finding]:
    """No claimed unit was already claimed in a prior period filing.

    The credit is taken once per dwelling, in the year it closed. A unit that
    appears in this filing and in the prior-period list of the closings schedule is
    a credit taken twice -- each filing internally consistent, the overlap visible
    only across them.
    """
    rule = "dup_no_double_count"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    closings = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if register is None or closings is None:
        return []
    prior = closings.get("prior_period_units")
    prior_ids = {p for p in prior if isinstance(p, str)} if isinstance(prior, list) else set()
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"units/{_unit_id(row)}"),
            f"claimed unit {_unit_id(row)} was already claimed in a prior period filing; "
            f"the §45L credit is taken once per dwelling",
        )
        for row in _units(ctx)
        if _claimed(row) and _unit_id(row) in prior_ids
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "no claimed unit was claimed in a prior filing")
        )
    return out


# --------------------------------------------------------------------------- #
# rate_ -- statutory per-unit rate re-derivation
# --------------------------------------------------------------------------- #
@check("rate_per_unit")
def check_rate_per_unit(ctx: Context) -> list[Finding]:
    """Each unit's credited amount is the dated statutory rate, or zero.

    A claimed unit is credited the statutory per-unit amount to the cent; an
    unclaimed one is credited nothing. A credited amount struck at any other figure
    is a per-unit rate the statute does not authorise.
    """
    rule = "rate_per_unit"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_UNIT_REGISTER)
    statute = _statute(ctx)
    if register is None or statute is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _units(ctx):
        unit = _unit_from_row(row)
        if unit is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"unit[{_unit_id(row)}].credited_amount_cents",
                row.get("credited_amount_cents"),
            )
            expected = unit_credit_cents(unit, statute)
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"units/{_unit_id(row)}/credited_amount_cents"),
                        f"unit {_unit_id(row)} is credited {fmt(stated)}; the statutory "
                        f"amount for a {'claimed' if unit.claimed else 'unclaimed'} unit is "
                        f"{fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} units carry the statutory per-unit rate")
        )
    return out


@check("rate_gross_credit")
def check_rate_gross_credit(ctx: Context) -> list[Finding]:
    """Each project's gross credit is its qualifying units times the dated rate.

    The gross credit is nothing but ``units x rate``. A gross credit that is not
    exactly that product is a credit the unit count does not support.
    """
    rule = "rate_gross_credit"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    statute = _statute(ctx)
    if worksheet is None or statute is None:
        return []
    out: list[Finding] = []
    checked = 0
    for proj in _projects(ctx):
        units = _int(proj, "qualifying_units")
        if units is None:
            continue
        with amount_guard(rule, out):
            gross = require_cents(
                f"project[{_project_id(proj)}].gross_credit_cents",
                proj.get("gross_credit_cents"),
            )
            expected = gross_credit_cents(units, statute)
            checked += 1
            if gross != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(worksheet, f"projects/{_project_id(proj)}/gross_credit_cents"),
                        f"project {_project_id(proj)} states gross credit {fmt(gross)}; "
                        f"{units} units x {fmt(statute.per_unit_cents)} re-derives "
                        f"{fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} project gross credits re-derive")
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- final report internal tie-out
# --------------------------------------------------------------------------- #
@check("rpt_units_times_rate")
def check_rpt_units_times_rate(ctx: Context) -> list[Finding]:
    """The final report's certified units times the rate equals its total credit.

    The face of the certification report states a certified-unit count and a total
    credit received. The one is the other times the statutory rate; a total that is
    not that product is a report that does not foot to itself.
    """
    rule = "rpt_units_times_rate"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_FINAL_REPORT)
    statute = _statute(ctx)
    if report is None or statute is None:
        return []
    units = _int(report, "total_certified_units")
    if units is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(report, "total_certified_units"),
                "the final report states no whole certified-unit count to tie against",
            )
        ]
    out: list[Finding] = []
    with amount_guard(rule, out):
        total_credit = require_cents(
            "final_report.total_credits_cents", report.get("total_credits_cents")
        )
        expected = units * statute.per_unit_cents
        if total_credit != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "total_credits_cents"),
                    f"the report states {units} certified units and total credit "
                    f"{fmt(total_credit)}; {units} x {fmt(statute.per_unit_cents)} "
                    f"re-derives {fmt(expected)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report's {units} units x rate ties its total credit {fmt(total_credit)}",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# roll_ -- roll-up tie-out
# --------------------------------------------------------------------------- #
@check("roll_project_units")
def check_roll_project_units(ctx: Context) -> list[Finding]:
    """Each project's worksheet unit count equals its claimed units in the register.

    The worksheet's qualifying-unit count is a rollup of the register underneath
    it. A count maintained beside the register rather than derived from it drifts
    the first time a unit is added or dropped and nobody re-tallies the column.
    """
    rule = "roll_project_units"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    register = ctx.one(DOC_UNIT_REGISTER)
    if worksheet is None or register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for proj in _projects(ctx):
        stated = _int(proj, "qualifying_units")
        if stated is None:
            continue
        checked += 1
        recomputed = recompute_project_units(ctx, _project_id(proj))
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, f"projects/{_project_id(proj)}/qualifying_units"),
                    f"project {_project_id(proj)} states {stated} qualifying units; the "
                    f"register holds {recomputed} claimed units for it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} project unit counts tie the register")
        )
    return out


@check("roll_grand_total")
def check_roll_grand_total(ctx: Context) -> list[Finding]:
    """The worksheet grand totals equal the sum of the project lines.

    Units, gross credit and net benefit each foot from the project lines. A grand
    total maintained apart from the lines it sums is the classic broken footer.
    """
    rule = "roll_grand_total"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    if worksheet is None:
        return []
    out: list[Finding] = []
    sum_units = 0
    for proj in _projects(ctx):
        u = _int(proj, "qualifying_units")
        if u is not None:
            sum_units += u
    with amount_guard(rule, out):
        sum_gross = 0
        sum_net = 0
        for proj in _projects(ctx):
            sum_gross += require_cents(
                f"project[{_project_id(proj)}].gross_credit_cents",
                proj.get("gross_credit_cents"),
            )
            sum_net += require_cents(
                f"project[{_project_id(proj)}].net_benefit_cents",
                proj.get("net_benefit_cents"),
            )
        stated_units = _int(worksheet, "total_qualifying_units")
        stated_gross = require_cents(
            "worksheet.total_gross_credit_cents", worksheet.get("total_gross_credit_cents")
        )
        stated_net = require_cents(
            "worksheet.total_net_benefit_cents", worksheet.get("total_net_benefit_cents")
        )
        if stated_units != sum_units:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "total_qualifying_units"),
                    f"the worksheet totals {stated_units} units; the project lines sum to "
                    f"{sum_units}",
                )
            )
        if stated_gross != sum_gross:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "total_gross_credit_cents"),
                    f"the worksheet totals gross credit {fmt(stated_gross)}; the project "
                    f"lines sum to {fmt(sum_gross)}",
                )
            )
        if stated_net != sum_net:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "total_net_benefit_cents"),
                    f"the worksheet totals net benefit {fmt(stated_net)}; the project lines "
                    f"sum to {fmt(sum_net)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the worksheet grand totals foot from the project lines")
        )
    return out


@check("roll_region_subtotal")
def check_roll_region_subtotal(ctx: Context) -> list[Finding]:
    """Each region subtotal equals the sum of its projects' gross credit.

    Between the project lines and the grand total sits a per-region subtotal; it
    must be exactly the gross credit of the projects in that region, and the set of
    regions it lists must be the set the projects occupy.
    """
    rule = "roll_region_subtotal"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    if worksheet is None:
        return []
    out: list[Finding] = []
    by_region: dict[str, int] = {}
    with amount_guard(rule, out):
        for proj in _projects(ctx):
            region = _text(proj, "region") or "?"
            gross = require_cents(
                f"project[{_project_id(proj)}].gross_credit_cents",
                proj.get("gross_credit_cents"),
            )
            by_region[region] = by_region.get(region, 0) + gross
        stated: dict[str, int] = {}
        for sub in _rows(worksheet, "region_subtotals"):
            region = _text(sub, "region") or "?"
            stated[region] = require_cents(
                f"region_subtotal[{region}].gross_credit_cents",
                sub.get("gross_credit_cents"),
            )
        for region in sorted(set(by_region) | set(stated)):
            if region not in stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(worksheet, f"region_subtotals/{region}"),
                        f"region {region!r} has projects on the worksheet but no subtotal line",
                    )
                )
            elif region not in by_region:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(worksheet, f"region_subtotals/{region}"),
                        f"region {region!r} carries a subtotal but no projects roll up to it",
                    )
                )
            elif stated[region] != by_region[region]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(worksheet, f"region_subtotals/{region}/gross_credit_cents"),
                        f"region {region!r} subtotal states {fmt(stated[region])}; its "
                        f"projects sum to {fmt(by_region[region])}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every region subtotal ties its projects")
        )
    return out


# --------------------------------------------------------------------------- #
# fwd_ -- roll-forward completeness identity
# --------------------------------------------------------------------------- #
@check("fwd_total_identity")
def check_fwd_total_identity(ctx: Context) -> list[Finding]:
    """For each project, total units = units closed per period + units remaining.

    The roll-forward proves nothing was lost between the total unit count and the
    period columns: total = the closings across every period plus the units left to
    close. When it does not hold, a closing was double-counted or dropped.
    """
    rule = "fwd_total_identity"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_PERIOD_ROLLFORWARD)
    if rollforward is None:
        return []
    out: list[Finding] = []
    checked = 0
    for proj in _rollforward_projects(ctx):
        total = _int(proj, "total_units")
        remaining = _int(proj, "remaining_units")
        closed = proj.get("closed_by_period")
        if total is None or remaining is None or not isinstance(closed, list):
            continue
        closed_ints = [c for c in closed if isinstance(c, int) and not isinstance(c, bool)]
        if len(closed_ints) != len(closed):
            continue
        checked += 1
        summed = sum(closed_ints) + remaining
        if total != summed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollforward, f"projects/{_project_id(proj)}/total_units"),
                    f"project {_project_id(proj)} states {total} total units; "
                    f"{sum(closed_ints)} closed across the periods plus {remaining} remaining "
                    f"re-derives {summed}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} roll-forward identities hold")
        )
    return out


@check("fwd_period_bounds")
def check_fwd_period_bounds(ctx: Context) -> list[Finding]:
    """The roll-forward period windows are ordered, disjoint and complete.

    Each period column is bounded by a date window. The windows must run forward
    (start on or before end), not overlap one another, and there must be exactly
    one per closings column -- otherwise a closing could be counted in two periods
    or in none.
    """
    rule = "fwd_period_bounds"
    _sev(rule, Status.FAIL)
    rollforward = ctx.one(DOC_PERIOD_ROLLFORWARD)
    if rollforward is None:
        return []
    out: list[Finding] = []
    windows = _rows(rollforward, "period_windows")
    parsed: list[tuple[date, date]] = []
    ok = True
    for i, w in enumerate(windows):
        start = _parse_date(w.get("start"))
        end = _parse_date(w.get("end"))
        if start is None or end is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollforward, f"period_windows/{i}"),
                    f"period window {i} has an unreadable start/end date",
                )
            )
            ok = False
            continue
        if start > end:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollforward, f"period_windows/{i}/start"),
                    f"period window {i} starts {start.isoformat()} after it ends "
                    f"{end.isoformat()}",
                )
            )
            ok = False
        parsed.append((start, end))
    if ok:
        ordered = sorted(parsed, key=lambda t: (t[0], t[1]))
        for (prior_start, prior_end), (next_start, _n_end) in zip(ordered, ordered[1:]):
            if next_start <= prior_end:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rollforward, "period_windows"),
                        f"period windows overlap: one ends {prior_end.isoformat()} and the "
                        f"next starts {next_start.isoformat()}; a closing could fall in both",
                    )
                )
    for proj in _rollforward_projects(ctx):
        closed = proj.get("closed_by_period")
        if isinstance(closed, list) and len(closed) != len(windows):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollforward, f"projects/{_project_id(proj)}/closed_by_period"),
                    f"project {_project_id(proj)} reports {len(closed)} period column(s) but "
                    f"{len(windows)} period window(s) are defined",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the {len(windows)} period windows are ordered, disjoint and complete",
            )
        )
    return out


@check("fwd_remaining_to_close")
def check_fwd_remaining_to_close(ctx: Context) -> list[Finding]:
    """A project with units still to close in a future period is flagged.

    Deliberately a FLAG, not a failure: remaining units are not an error, they are
    a credit still to come. The flag keeps a project with an open roll-forward on
    the reviewer's radar for the next filing.
    """
    rule = "fwd_remaining_to_close"
    _sev(rule, Status.FLAG)
    rollforward = ctx.one(DOC_PERIOD_ROLLFORWARD)
    if rollforward is None:
        return []
    out: list[Finding] = []
    checked = 0
    for proj in _rollforward_projects(ctx):
        remaining = _int(proj, "remaining_units")
        if remaining is None:
            continue
        checked += 1
        if remaining > 0:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(rollforward, f"projects/{_project_id(proj)}/remaining_units"),
                    f"project {_project_id(proj)} has {remaining} unit(s) still to close in a "
                    f"future period; the credit for them is not yet earned",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} projects have fully closed out")
        )
    return out


# --------------------------------------------------------------------------- #
# net_ -- net-benefit re-derivation
# --------------------------------------------------------------------------- #
@check("net_addback")
def check_net_addback(ctx: Context) -> list[Finding]:
    """Each project's profit addback equals its gross credit.

    The credit is added back to book profit dollar for dollar before it is taxed,
    so the addback is the gross credit exactly. Any other figure breaks the tax
    effect derived on top of it.
    """
    rule = "net_addback"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    if worksheet is None:
        return []
    out: list[Finding] = []
    checked = 0
    for proj in _projects(ctx):
        with amount_guard(rule, out):
            gross = require_cents(
                f"project[{_project_id(proj)}].gross_credit_cents",
                proj.get("gross_credit_cents"),
            )
            addback = require_cents(
                f"project[{_project_id(proj)}].addback_cents", proj.get("addback_cents")
            )
            checked += 1
            if addback != gross:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(worksheet, f"projects/{_project_id(proj)}/addback_cents"),
                        f"project {_project_id(proj)} states a profit addback of {fmt(addback)}; "
                        f"the gross credit added back is {fmt(gross)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} profit addbacks equal the gross credit")
        )
    return out


@check("net_tax_effect")
def check_net_tax_effect(ctx: Context) -> list[Finding]:
    """Each project's tax effect equals minus the credit at the effective rate.

    The addback is taxed at the effective rate, so the tax effect is
    ``-(credit x rate)`` computed with truncating division. A tax effect struck any
    other way understates or overstates the net benefit below it.
    """
    rule = "net_tax_effect"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    statute = _statute(ctx)
    if worksheet is None or statute is None:
        return []
    out: list[Finding] = []
    checked = 0
    for proj in _projects(ctx):
        with amount_guard(rule, out):
            gross = require_cents(
                f"project[{_project_id(proj)}].gross_credit_cents",
                proj.get("gross_credit_cents"),
            )
            stated = require_cents(
                f"project[{_project_id(proj)}].tax_effect_cents", proj.get("tax_effect_cents")
            )
            expected = tax_effect_cents(gross, statute)
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(worksheet, f"projects/{_project_id(proj)}/tax_effect_cents"),
                        f"project {_project_id(proj)} states a tax effect of {fmt(stated)}; "
                        f"-({fmt(gross)} x {statute.effective_rate_bps} bps) re-derives "
                        f"{fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} tax effects re-derive at the effective rate")
        )
    return out


@check("net_benefit")
def check_net_benefit(ctx: Context) -> list[Finding]:
    """Each project's net benefit equals its gross credit plus its tax effect.

    The net benefit is the last link in the chain: gross credit less the tax on its
    addback. Stated apart from the two figures it sums, it is the number a partner
    allocation is then split from -- so a break here propagates.
    """
    rule = "net_benefit"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    if worksheet is None:
        return []
    out: list[Finding] = []
    checked = 0
    for proj in _projects(ctx):
        with amount_guard(rule, out):
            gross = require_cents(
                f"project[{_project_id(proj)}].gross_credit_cents",
                proj.get("gross_credit_cents"),
            )
            tax = require_cents(
                f"project[{_project_id(proj)}].tax_effect_cents", proj.get("tax_effect_cents")
            )
            stated = require_cents(
                f"project[{_project_id(proj)}].net_benefit_cents", proj.get("net_benefit_cents")
            )
            checked += 1
            if stated != gross + tax:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(worksheet, f"projects/{_project_id(proj)}/net_benefit_cents"),
                        f"project {_project_id(proj)} states a net benefit of {fmt(stated)}; "
                        f"{fmt(gross)} + {fmt(tax)} re-derives {fmt(gross + tax)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} net benefits re-derive")
        )
    return out


# --------------------------------------------------------------------------- #
# alloc_ -- partner allocation
# --------------------------------------------------------------------------- #
@check("alloc_shares_sum")
def check_alloc_shares_sum(ctx: Context) -> list[Finding]:
    """The partner shares sum to the worksheet's total net benefit.

    Allocation cannot lose or create a cent: the split of the net benefit across
    partners must add back to the net benefit it divides.
    """
    rule = "alloc_shares_sum"
    _sev(rule, Status.FAIL)
    allocation = ctx.one(DOC_PARTNER_ALLOCATION)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    if allocation is None or worksheet is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = require_cents(
            "worksheet.total_net_benefit_cents", worksheet.get("total_net_benefit_cents")
        )
        allocated = 0
        for p in _partners(ctx):
            allocated += require_cents(
                f"partner[{_text(p, 'partner_id')}].allocated_cents", p.get("allocated_cents")
            )
        if allocated != total:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(allocation, "partners"),
                    f"the partner shares sum to {fmt(allocated)}; the net benefit to allocate "
                    f"is {fmt(total)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the partner shares sum to the net benefit {fmt(total)}",
                )
            )
    return out


@check("alloc_share_rederived")
def check_alloc_share_rederived(ctx: Context) -> list[Finding]:
    """Each partner's share re-derives from its ownership at largest-remainder.

    The split is not free-hand: each partner's share is the net benefit at its
    ownership basis points, apportioned by the largest-remainder method so the
    residual cent lands deterministically. A share that does not re-derive is an
    allocation someone adjusted by hand.
    """
    rule = "alloc_share_rederived"
    _sev(rule, Status.FAIL)
    allocation = ctx.one(DOC_PARTNER_ALLOCATION)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    if allocation is None or worksheet is None:
        return []
    partners = _partners(ctx)
    weights = [_int(p, "ownership_bps") for p in partners]
    if any(w is None for w in weights):
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(allocation, "partners"),
                "a partner carries no whole ownership basis-point weight to re-derive from",
            )
        ]
    if sum(weights) != 10_000:  # type: ignore[arg-type]
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(allocation, "partners"),
                f"partner ownership sums to {sum(weights)} bps, not 10000 (100.00%); the "  # type: ignore[arg-type]
                f"shares cannot be re-derived",
            )
        ]
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = require_cents(
            "worksheet.total_net_benefit_cents", worksheet.get("total_net_benefit_cents")
        )
        expected = allocate_by_ratio(total, weights)  # type: ignore[arg-type]
        for p, want in zip(partners, expected):
            got = require_cents(
                f"partner[{_text(p, 'partner_id')}].allocated_cents", p.get("allocated_cents")
            )
            if got != want:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(allocation, f"partners/{_text(p, 'partner_id')}/allocated_cents"),
                        f"partner {_text(p, 'partner_id')} is allocated {fmt(got)}; its "
                        f"{_int(p, 'ownership_bps')} bps of {fmt(total)} re-derives {fmt(want)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every partner share re-derives from its ownership")
        )
    return out


# --------------------------------------------------------------------------- #
# recon_ -- cross-artifact reconciliation
# --------------------------------------------------------------------------- #
@check("recon_final_report_ties")
def check_recon_final_report_ties(ctx: Context) -> list[Finding]:
    """The report, worksheet and closings schedule agree on the credited units.

    Three artifacts count the same credited units from three directions: the final
    report's certified-unit count, the worksheet's total qualifying units, and the
    closings schedule's credited-unit count. They must be one number.
    """
    rule = "recon_final_report_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_FINAL_REPORT)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    closings = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if report is None or worksheet is None or closings is None:
        return []
    report_units = _int(report, "total_certified_units")
    worksheet_units = _int(worksheet, "total_qualifying_units")
    closings_units = _int(closings, "total_credited_units")
    if report_units is None or worksheet_units is None or closings_units is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(report, "total_certified_units"),
                "one of the report / worksheet / closings credited-unit counts is not a "
                "whole number to reconcile",
            )
        ]
    if report_units == worksheet_units == closings_units:
        return [
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the report, worksheet and closings schedule all tie at {report_units} units",
            )
        ]
    return [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(report, "total_certified_units"),
            f"credited-unit counts disagree across artifacts: final report {report_units}, "
            f"worksheet {worksheet_units}, closings schedule {closings_units}",
        )
    ]


@check("recon_closed_ge_credited")
def check_recon_closed_ge_credited(ctx: Context) -> list[Finding]:
    """No project credits more units than physically closed.

    Only closed units can be credited, so the closings schedule's closed count is a
    ceiling on the worksheet's credited units. A project claiming more units than it
    closed has claimed a unit that does not exist.
    """
    rule = "recon_closed_ge_credited"
    _sev(rule, Status.FAIL)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    closings = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if worksheet is None or closings is None:
        return []
    closed_by = {
        _project_id(c): _int(c, "closed_units")
        for c in _closings_projects(ctx)
    }
    out: list[Finding] = []
    checked = 0
    for proj in _projects(ctx):
        credited = _int(proj, "qualifying_units")
        closed = closed_by.get(_project_id(proj))
        if credited is None or closed is None:
            continue
        checked += 1
        if closed < credited:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(closings, f"projects/{_project_id(proj)}/closed_units"),
                    f"project {_project_id(proj)} credits {credited} units but only {closed} "
                    f"closed; a credited unit did not close",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} projects closed at least what they credit")
        )
    return out


@check("recon_certification_gap")
def check_recon_certification_gap(ctx: Context) -> list[Finding]:
    """A project that closed more units than it credited is flagged for review.

    Deliberately a FLAG, not a failure: closing more units than were certified is
    a certification gap, not an error -- there may be a credit left on the table for
    units that closed but were never certified. It is surfaced for a human to chase
    the missing certificates.
    """
    rule = "recon_certification_gap"
    _sev(rule, Status.FLAG)
    worksheet = ctx.one(DOC_CREDIT_WORKSHEET)
    closings = ctx.one(DOC_CLOSINGS_SCHEDULE)
    if worksheet is None or closings is None:
        return []
    credited_by = {_project_id(p): _int(p, "qualifying_units") for p in _projects(ctx)}
    out: list[Finding] = []
    checked = 0
    for proj in _closings_projects(ctx):
        closed = _int(proj, "closed_units")
        credited = credited_by.get(_project_id(proj))
        if closed is None or credited is None:
            continue
        checked += 1
        if closed > credited:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(closings, f"projects/{_project_id(proj)}/closed_units"),
                    f"project {_project_id(proj)} closed {closed} units but credited only "
                    f"{credited}; {closed - credited} closed unit(s) may be uncertified and "
                    f"worth chasing",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"no certification gap across {checked} projects")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one credit file."""
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
    """Analyze every ``.json`` credit file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of credit-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
