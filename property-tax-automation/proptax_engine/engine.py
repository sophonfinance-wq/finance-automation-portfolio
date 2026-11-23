"""
Property tax control engine (READ-ONLY).
========================================

Loads each roll file (a ``.json`` file produced by :mod:`proptax_engine.generate`)
and runs an ordered *registry* of independent controls over it.

The shape of the problem
------------------------
A homebuilder's property tax exposure drifts for two reasons, and neither is
arithmetic.

The first is that the unit of taxation and the unit of ownership come apart. One
parent parcel is platted into forty; the assessor picks the split up on its own
schedule; then the units close one at a time over eighteen months, and each
closing moves one parcel off the developer's books while the roll keeps billing
the account it always has. The invoice is genuine, the payee is genuinely the
county, the amount genuinely matches the notice -- and the only thing wrong is
whose parcel it is.

The second is the calendar. Jurisdictions share no due dates, no instalment count
and no penalty arithmetic, so applying one's habits to another's parcel is how a
delinquency is found after the penalty has attached.

The registry is organised around that:

1. ``set_``   -- is the roll file complete?
2. ``par_``   -- is the parcel register sound, and does it cover the whole plat?
3. ``asmt_``  -- does the assessment foot, and does the charge follow from it?
4. ``inst_``  -- do the instalments match the jurisdiction's own regime?
5. ``own_``   -- did the tax follow the ownership through each closing?
6. ``acr_``   -- does the accrual match the charge, stop at escrow and tie to the GL?
7. ``pay_``   -- does what was paid match what was actually owed?

Design notes
------------
- **Strictly read-only.** Roll files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order. Every
  delinquency test is made against the ``as_of`` carried in the file.
- **Integer cents, no tolerance.** Amounts are compared with exact ``==``.
- **Regimes are data.** No control hard-codes a due date, an instalment count or a
  penalty rate; each reads the profile for the parcel's own jurisdiction.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.

Ownership is the spine
----------------------
Every money control here ultimately asks the same question: on the day this
charge arose, whose parcel was it? A payment, an accrual and a proration are all
correct or incorrect for the same reason, and it is never visible on the invoice.
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
    ASSESSMENT_VARIANCE_BPS,
    DOC_ACCRUAL_LEDGER,
    DOC_ASSESSMENT_HISTORY,
    DOC_GL_POSITIONS,
    DOC_INSTALMENT_SCHEDULE,
    DOC_PARCEL_REGISTER,
    DOC_PROJECT_REGISTER,
    DOC_REGIME_TABLE,
    DOC_SALE_REGISTER,
    DOC_TYPES,
    INTEREST_PERIOD_DAYS,
    PARCEL_HELD,
    PARCEL_RETIRED,
    PARCEL_SOLD,
    PARCEL_STATUSES,
    PRORATION_DAYS,
    STAGE_DEVELOPMENT,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, apply_rate, fmt, fmt_bps, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~proptax_engine.money.AmountInvalidError` as a finding."""
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
_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


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
# Roll helpers
# --------------------------------------------------------------------------- #
def _parcels(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PARCEL_REGISTER), "parcels")


def _parcel_no(row: dict[str, Any]) -> str:
    value = row.get("parcel_no")
    return value if isinstance(value, str) and value else "?"


def _parcel_index(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _parcels(ctx):
        key = _parcel_no(row)
        if key not in out:
            out[key] = row
    return out


def _projects(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_PROJECT_REGISTER), "projects"):
        code = _text(row, "code")
        if code and code not in out:
            out[code] = row
    return out


def _regimes(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_REGIME_TABLE), "regimes"):
        juris = _text(row, "jurisdiction")
        if juris and juris not in out:
            out[juris] = row
    return out


def _instalments(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_INSTALMENT_SCHEDULE), "instalments")


def _instalments_by_parcel(ctx: Context) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _instalments(ctx):
        parcel = _text(row, "parcel_no")
        if parcel:
            out.setdefault(parcel, []).append(row)
    return out


def _distinct_instalments(ctx: Context) -> dict[str, list[dict[str, Any]]]:
    """Instalments per parcel, keeping the first row of each sequence.

    Deduplication is deliberate. A sequence scheduled twice is a real defect, but
    it belongs to ``inst_no_duplicate_payment`` alone -- if the footing and
    calendar controls also counted the repeat, one mistake would light up three
    controls and the report would stop saying which one to fix.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for parcel, rows in _instalments_by_parcel(ctx).items():
        seen: set[Any] = set()
        kept: list[dict[str, Any]] = []
        for row in rows:
            sequence = row.get("sequence")
            if sequence in seen:
                continue
            seen.add(sequence)
            kept.append(row)
        out[parcel] = kept
    return out


def _sales(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SALE_REGISTER), "closings")


def _sale_index(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _sales(ctx):
        parcel = _text(row, "parcel_no")
        if parcel and parcel not in out:
            out[parcel] = row
    return out


def _accruals(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ACCRUAL_LEDGER), "accruals")


def _regime_for(ctx: Context, parcel: dict[str, Any]) -> dict[str, Any] | None:
    return _regimes(ctx).get(_text(parcel, "jurisdiction") or "")


def _due_date(regime: dict[str, Any], instalment: dict[str, Any], tax_year: int) -> date | None:
    """The statutory due date for one instalment of ``tax_year``.

    Derived from the regime's fiscal-year opening and the instalment's own
    month/day plus year offset, so a mid-year fiscal regime pushes its later
    instalment into the following calendar year without any control knowing that.
    """
    month_day = instalment.get("due_month_day")
    offset = instalment.get("due_year_offset")
    fiscal_start = regime.get("fiscal_year_start_month_day")
    if not isinstance(month_day, str) or not isinstance(fiscal_start, str):
        return None
    if isinstance(offset, bool) or not isinstance(offset, int):
        return None
    try:
        return date.fromisoformat(f"{tax_year + offset}-{month_day}")
    except ValueError:
        return None


def _fiscal_year_start(regime: dict[str, Any], tax_year: int) -> date | None:
    month_day = regime.get("fiscal_year_start_month_day")
    if not isinstance(month_day, str):
        return None
    try:
        return date.fromisoformat(f"{tax_year}-{month_day}")
    except ValueError:
        return None


def derive_penalty_interest(
    amount_cents: int, days_late: int, penalty_bps: int, interest_bps: int
) -> tuple[int, int]:
    """Penalty and interest on a delinquent instalment.

    Penalty attaches once, on the whole instalment, the moment it is late.
    Interest accrues per whole :data:`~proptax_engine.model.INTEREST_PERIOD_DAYS`
    period past the due date. Both use the money contract's truncating rate
    arithmetic, so the derived figure can be compared to the reported one with
    exact ``==`` rather than a tolerance.
    """
    if days_late <= 0:
        return 0, 0
    penalty = apply_rate(amount_cents, penalty_bps)
    periods = days_late // INTEREST_PERIOD_DAYS
    interest = apply_rate(amount_cents, interest_bps) * periods
    return penalty, interest


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the roll depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the roll file carries "
                    f"exactly one of each",
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
                f"as_of {ctx.as_of!r} is not a readable date; every delinquency test is "
                f"made against it",
            )
        )
    if ctx.tax_year is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                "tax_year is missing; every statutory due date is derived from it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# par_ -- parcel register
# --------------------------------------------------------------------------- #
@check("par_parcel_unique")
def check_par_parcel_unique(ctx: Context) -> list[Finding]:
    """No parcel number appears twice.

    The parcel number joins the register to the instalments, the closings and the
    accrual. Duplicate it and a single parcel's tax is counted twice on one side
    of the join and once on the other.
    """
    rule = "par_parcel_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _parcels(ctx):
        key = _parcel_no(row)
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"parcels/{parcel}"),
            f"parcel {parcel} appears {count} times; it is the join key to the "
            f"instalments, the closings and the accrual",
        )
        for parcel, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} parcel numbers are unique")
        )
    return out


@check("par_required_fields")
def check_par_required_fields(ctx: Context) -> list[Finding]:
    """Every parcel carries the fields the rest of the cycle reads."""
    rule = "par_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    required = ("parcel_no", "project_code", "jurisdiction", "status", "lot_unit")
    out: list[Finding] = []
    for row in _parcels(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parcels/{_parcel_no(row)}"),
                    f"parcel {_parcel_no(row)} is missing {', '.join(missing)}",
                )
            )
        if _text(row, "status") not in PARCEL_STATUSES and _text(row, "status"):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parcels/{_parcel_no(row)}/status"),
                    f"parcel {_parcel_no(row)} has status {_text(row, 'status')!r}, "
                    f"outside {PARCEL_STATUSES}; ownership controls key off it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_parcels(ctx))} parcels are fully described"
            )
        )
    return out


@check("par_project_mapped")
def check_par_project_mapped(ctx: Context) -> list[Finding]:
    """Every parcel belongs to a project in the project register."""
    rule = "par_project_mapped"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    projects = _projects(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"parcels/{_parcel_no(row)}/project_code"),
            f"parcel {_parcel_no(row)} names project {_text(row, 'project_code')!r}, "
            f"which is not in the project register; its tax cannot be costed",
        )
        for row in _parcels(ctx)
        if _text(row, "project_code") and _text(row, "project_code") not in projects
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"every parcel maps to one of {len(projects)} projects")
        )
    return out


@check("par_plat_completeness")
def check_par_plat_completeness(ctx: Context) -> list[Finding]:
    """The register carries one live parcel per lot the plat created.

    This is the completeness control, and it is the one that catches a segregation
    the assessor has not finished. A plat of forty lots that shows thirty-nine
    parcels is not missing a bill -- it is still being billed for the fortieth
    somewhere else, usually on the parent parcel nobody retired.
    """
    rule = "par_plat_completeness"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    counts: dict[str, int] = {}
    for row in _parcels(ctx):
        if _text(row, "status") == PARCEL_RETIRED:
            continue
        code = _text(row, "project_code")
        if code:
            counts[code] = counts.get(code, 0) + 1
    out: list[Finding] = []
    checked = 0
    for code, project in sorted(_projects(ctx).items()):
        expected = _int(project, "plat_lot_count")
        if expected is None:
            continue
        checked += 1
        found = counts.get(code, 0)
        if found != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parcels/{code}"),
                    f"project {code} platted {expected} lot(s) but the register carries "
                    f"{found} live parcel(s); the difference is being billed somewhere "
                    f"the register cannot see",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} plats are fully on the roll")
        )
    return out


@check("par_jurisdiction_known")
def check_par_jurisdiction_known(ctx: Context) -> list[Finding]:
    """Every parcel's jurisdiction has a regime profile.

    Without one there is no due date, no instalment count and no penalty
    arithmetic -- so the parcel would silently skip the calendar controls rather
    than fail them.
    """
    rule = "par_jurisdiction_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    regimes = _regimes(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"parcels/{_parcel_no(row)}/jurisdiction"),
            f"parcel {_parcel_no(row)} sits in {_text(row, 'jurisdiction')!r}, which has "
            f"no regime profile; it would skip every calendar control rather than fail one",
        )
        for row in _parcels(ctx)
        if _text(row, "jurisdiction") and _text(row, "jurisdiction") not in regimes
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"every parcel's jurisdiction is one of {len(regimes)} regimes"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# asmt_ -- assessment
# --------------------------------------------------------------------------- #
@check("asmt_components_tie_total")
def check_asmt_components_tie_total(ctx: Context) -> list[Finding]:
    """Land plus improvements equals the total assessed value.

    Compared at zero tolerance. The split matters beyond footing: land and
    improvements are reassessed on different triggers, and a total that does not
    equal its parts cannot be reconciled to either.
    """
    rule = "asmt_components_tie_total"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _parcels(ctx):
        parcel = _parcel_no(row)
        with amount_guard(rule, out):
            land = require_cents(f"parcel[{parcel}].assessed_land_cents",
                                 row.get("assessed_land_cents"))
            improvement = require_cents(f"parcel[{parcel}].assessed_improvement_cents",
                                        row.get("assessed_improvement_cents"))
            total = require_cents(f"parcel[{parcel}].assessed_total_cents",
                                  row.get("assessed_total_cents"))
            checked += 1
            if land + improvement != total:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"parcels/{parcel}/assessed_total_cents"),
                        f"parcel {parcel} assesses land {fmt(land)} plus improvements "
                        f"{fmt(improvement)} = {fmt(land + improvement)}, against a stated "
                        f"total of {fmt(total)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} assessments foot"))
    return out


@check("asmt_charge_follows_value")
def check_asmt_charge_follows_value(ctx: Context) -> list[Finding]:
    """The annual charge is the levy rate applied to the assessed value.

    Re-derived rather than trusted. The notice is a third-party document, and the
    one thing worth checking on it is the only thing that is pure arithmetic.
    """
    rule = "asmt_charge_follows_value"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _parcels(ctx):
        parcel = _parcel_no(row)
        if _text(row, "status") == PARCEL_RETIRED:
            continue
        with amount_guard(rule, out):
            total = require_cents(f"parcel[{parcel}].assessed_total_cents",
                                  row.get("assessed_total_cents"))
            rate = require_cents(f"parcel[{parcel}].levy_rate_bps",
                                 row.get("levy_rate_bps"), unit="basis points")
            charge = require_cents(f"parcel[{parcel}].annual_tax_cents",
                                   row.get("annual_tax_cents"))
            checked += 1
            expected = apply_rate(total, rate)
            if charge != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"parcels/{parcel}/annual_tax_cents"),
                        f"parcel {parcel} is charged {fmt(charge)}; {fmt_bps(rate)} of the "
                        f"{fmt(total)} assessed value is {fmt(expected)} "
                        f"(difference {fmt(charge - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges follow their assessed value")
        )
    return out


@check("asmt_variance_surfaced")
def check_asmt_variance_surfaced(ctx: Context) -> list[Finding]:
    """Surface assessments that moved sharply year over year.

    Not an error -- a deadline. Every jurisdiction's protest window opens and
    closes on the assessment, not on the bill, and by the time the bill arrives the
    window has usually shut.
    """
    rule = "asmt_variance_surfaced"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    prior: dict[str, int] = {}
    for row in _rows(ctx.one(DOC_ASSESSMENT_HISTORY), "prior_year"):
        parcel = _text(row, "parcel_no")
        value = _int(row, "assessed_total_cents")
        if parcel and value is not None:
            prior[parcel] = value
    out: list[Finding] = []
    checked = 0
    for row in _parcels(ctx):
        parcel = _parcel_no(row)
        was = prior.get(parcel)
        if was is None or was <= 0:
            continue
        with amount_guard(rule, out):
            now = require_cents(f"parcel[{parcel}].assessed_total_cents",
                                row.get("assessed_total_cents"))
            checked += 1
            move_bps = abs(now - was) * 10000 // was
            if move_bps > ASSESSMENT_VARIANCE_BPS:
                direction = "up" if now > was else "down"
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"parcels/{parcel}/assessed_total_cents"),
                        f"parcel {parcel} moved {direction} {fmt_bps(move_bps)} from "
                        f"{fmt(was)} to {fmt(now)}; the protest window runs from the "
                        f"assessment, not the bill",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"none of {checked} assessments moved beyond "
                f"{fmt_bps(ASSESSMENT_VARIANCE_BPS)}",
            )
        )
    return out


@check("asmt_exemption_has_authority")
def check_asmt_exemption_has_authority(ctx: Context) -> list[Finding]:
    """An exemption or abatement cites the authority that grants it."""
    rule = "asmt_exemption_has_authority"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _parcels(ctx):
        if not _text(row, "exemption_code"):
            continue
        checked += 1
        if not _text(row, "exemption_authority"):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"parcels/{_parcel_no(row)}/exemption_authority"),
                    f"parcel {_parcel_no(row)} claims exemption "
                    f"{_text(row, 'exemption_code')!r} with no authority cited; an "
                    f"exemption nobody can source is one the assessor can withdraw",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} exemptions cite an authority")
        )
    return out


# --------------------------------------------------------------------------- #
# inst_ -- instalments and the statutory calendar
# --------------------------------------------------------------------------- #
@check("inst_shares_tie_annual")
def check_inst_shares_tie_annual(ctx: Context) -> list[Finding]:
    """A parcel's instalments sum to its annual charge.

    Zero tolerance. An instalment schedule that is a penny off the annual charge
    has not been split; it has been rounded until it looked split, and the penny
    surfaces as a delinquency on the final instalment years later.
    """
    rule = "inst_shares_tie_annual"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_INSTALMENT_SCHEDULE)
    if schedule is None:
        return []
    by_parcel = _distinct_instalments(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _parcels(ctx):
        parcel = _parcel_no(row)
        if _text(row, "status") == PARCEL_RETIRED:
            continue
        rows = by_parcel.get(parcel, [])
        if not rows:
            continue
        with amount_guard(rule, out):
            annual = require_cents(f"parcel[{parcel}].annual_tax_cents",
                                   row.get("annual_tax_cents"))
            total = 0
            for inst in rows:
                total += require_cents(
                    f"instalment[{parcel}/{inst.get('sequence')}].amount_cents",
                    inst.get("amount_cents"),
                )
            checked += 1
            if total != annual:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(schedule, f"instalments/{parcel}"),
                        f"parcel {parcel} splits into instalments totalling {fmt(total)} "
                        f"against an annual charge of {fmt(annual)} "
                        f"(difference {fmt(total - annual)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} instalment schedules foot to the charge")
        )
    return out


@check("inst_matches_regime_calendar")
def check_inst_matches_regime_calendar(ctx: Context) -> list[Finding]:
    """Instalment count and due dates are the jurisdiction's, not a default.

    This is the control that makes a multi-state portfolio safe. Nothing about the
    dates is hard-coded: each parcel's instalments are compared to the regime
    profile for its own jurisdiction, so applying one state's calendar to
    another's parcel fails here rather than at the penalty.
    """
    rule = "inst_matches_regime_calendar"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_INSTALMENT_SCHEDULE)
    tax_year = ctx.tax_year
    if schedule is None or tax_year is None:
        return []
    by_parcel = _distinct_instalments(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _parcels(ctx):
        parcel = _parcel_no(row)
        regime = _regime_for(ctx, row)
        if regime is None:
            continue
        expected_rows = _rows(regime, "instalments")
        found = sorted(by_parcel.get(parcel, []), key=lambda r: r.get("sequence") or 0)
        if not found:
            continue
        checked += 1
        if len(found) != len(expected_rows):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"instalments/{parcel}"),
                    f"parcel {parcel} carries {len(found)} instalment(s); "
                    f"{_text(row, 'jurisdiction')} takes {len(expected_rows)}",
                )
            )
            continue
        for expected, actual in zip(expected_rows, found):
            want = _due_date(regime, expected, tax_year)
            got = _parse_date(actual.get("due_date"))
            if want is None or got is None or want == got:
                continue
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"instalments/{parcel}/{actual.get('sequence')}/due_date"),
                    f"parcel {parcel} instalment {actual.get('sequence')} is dated "
                    f"{got.isoformat()}; {_text(row, 'jurisdiction')} makes it due "
                    f"{want.isoformat()}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} schedules match their own jurisdiction"
            )
        )
    return out


@check("inst_delinquency_recomputed")
def check_inst_delinquency_recomputed(ctx: Context) -> list[Finding]:
    """Penalty and interest are re-derived, never taken from the notice.

    The county's figure is the one being checked, so trusting it would make the
    control circular. Penalty attaches once on the whole instalment; interest
    accrues per whole 30-day period past the due date; both at the regime's own
    rates.
    """
    rule = "inst_delinquency_recomputed"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_INSTALMENT_SCHEDULE)
    as_of = _parse_date(ctx.as_of)
    if schedule is None or as_of is None:
        return []
    parcels = _parcel_index(ctx)
    closings = _sale_index(ctx)
    out: list[Finding] = []
    checked = 0
    for inst in _instalments(ctx):
        parcel_no = _text(inst, "parcel_no")
        parcel = parcels.get(parcel_no or "")
        if parcel is None:
            continue
        regime = _regime_for(ctx, parcel)
        due = _parse_date(inst.get("due_date"))
        if regime is None or due is None:
            continue
        # A period that began after the parcel closed is the buyer's delinquency,
        # not the developer's. ``own_no_payment_after_escrow`` owns that period.
        closing = closings.get(parcel_no or "")
        if closing is not None:
            closed_on = _parse_date(closing.get("close_of_escrow_date"))
            if closed_on is not None and due > closed_on:
                continue
        settled = _parse_date(inst.get("paid_date"))
        reference = settled if settled is not None else as_of
        days_late = (reference - due).days
        with amount_guard(rule, out):
            amount = require_cents(
                f"instalment[{parcel_no}/{inst.get('sequence')}].amount_cents",
                inst.get("amount_cents"),
            )
            penalty_bps = require_cents(
                f"regime[{_text(parcel, 'jurisdiction')}].penalty_bps",
                regime.get("penalty_bps"), unit="basis points",
            )
            interest_bps = require_cents(
                f"regime[{_text(parcel, 'jurisdiction')}].interest_bps_per_period",
                regime.get("interest_bps_per_period"), unit="basis points",
            )
            stated_penalty = require_cents(
                f"instalment[{parcel_no}/{inst.get('sequence')}].penalty_cents",
                inst.get("penalty_cents"),
            )
            stated_interest = require_cents(
                f"instalment[{parcel_no}/{inst.get('sequence')}].interest_cents",
                inst.get("interest_cents"),
            )
            checked += 1
            want_penalty, want_interest = derive_penalty_interest(
                amount, days_late, penalty_bps, interest_bps
            )
            if (stated_penalty, stated_interest) != (want_penalty, want_interest):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            schedule,
                            f"instalments/{parcel_no}/{inst.get('sequence')}/penalty_cents",
                        ),
                        f"parcel {parcel_no} instalment {inst.get('sequence')} is "
                        f"{days_late} day(s) late and carries penalty {fmt(stated_penalty)} "
                        f"and interest {fmt(stated_interest)}; the regime derives "
                        f"{fmt(want_penalty)} and {fmt(want_interest)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"penalty and interest re-derive on all {checked} instalments"
            )
        )
    return out


@check("inst_no_duplicate_payment")
def check_inst_no_duplicate_payment(ctx: Context) -> list[Finding]:
    """One instalment per parcel per sequence, paid once.

    Duplicate payment of a property tax instalment is unusually easy: the county
    sends the notice, the title company pays it at closing, and both land in the
    same payables run under different vendor names.
    """
    rule = "inst_no_duplicate_payment"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_INSTALMENT_SCHEDULE)
    if schedule is None:
        return []
    seen: dict[tuple[str, Any], int] = {}
    for inst in _instalments(ctx):
        parcel = _text(inst, "parcel_no")
        if parcel is None:
            continue
        key = (parcel, inst.get("sequence"))
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(schedule, f"instalments/{parcel}/{sequence}"),
            f"parcel {parcel} carries {count} rows for instalment {sequence}; the same "
            f"charge is scheduled -- and payable -- more than once",
        )
        for (parcel, sequence), count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} instalments appear exactly once")
        )
    return out


@check("inst_receipt_on_file")
def check_inst_receipt_on_file(ctx: Context) -> list[Finding]:
    """A paid instalment carries the county's receipt reference."""
    rule = "inst_receipt_on_file"
    _sev(rule, Status.FLAG)
    schedule = ctx.one(DOC_INSTALMENT_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for inst in _instalments(ctx):
        if _parse_date(inst.get("paid_date")) is None:
            continue
        checked += 1
        if not _text(inst, "receipt_reference"):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(
                        schedule,
                        f"instalments/{_text(inst, 'parcel_no')}/"
                        f"{inst.get('sequence')}/receipt_reference",
                    ),
                    f"parcel {_text(inst, 'parcel_no')} instalment {inst.get('sequence')} "
                    f"is marked paid with no receipt; the payment is asserted, not evidenced",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} paid instalments carry a receipt")
        )
    return out


# --------------------------------------------------------------------------- #
# own_ -- ownership
# --------------------------------------------------------------------------- #
@check("own_sale_parcel_exists")
def check_own_sale_parcel_exists(ctx: Context) -> list[Finding]:
    """Every closing names a parcel that is on the register."""
    rule = "own_sale_parcel_exists"
    _sev(rule, Status.FAIL)
    sales = ctx.one(DOC_SALE_REGISTER)
    if sales is None:
        return []
    parcels = _parcel_index(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(sales, f"closings/{_text(row, 'parcel_no')}"),
            f"a closing names parcel {_text(row, 'parcel_no')!r}, which is not on the "
            f"register; the tax it prorates belongs to nothing",
        )
        for row in _sales(ctx)
        if _text(row, "parcel_no") and _text(row, "parcel_no") not in parcels
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_sales(ctx))} closings name a real parcel")
        )
    return out


@check("own_sold_parcel_flagged")
def check_own_sold_parcel_flagged(ctx: Context) -> list[Finding]:
    """A parcel that closed is carried as sold, and one that did not is not.

    The register's status is what every downstream ownership control reads. If it
    disagrees with the closing file, the controls below are all asking the wrong
    question correctly.
    """
    rule = "own_sold_parcel_flagged"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARCEL_REGISTER)
    if register is None:
        return []
    closings = _sale_index(ctx)
    out: list[Finding] = []
    for row in _parcels(ctx):
        parcel = _parcel_no(row)
        status = _text(row, "status")
        closed = parcel in closings
        if closed and status != PARCEL_SOLD:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parcels/{parcel}/status"),
                    f"parcel {parcel} closed on "
                    f"{_text(closings[parcel], 'close_of_escrow_date')} but is carried "
                    f"{status!r}; every ownership control below reads this field",
                )
            )
        elif not closed and status == PARCEL_SOLD:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parcels/{parcel}/status"),
                    f"parcel {parcel} is carried sold with no closing on file; the tax "
                    f"has been handed to a buyer nobody can name",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "register status agrees with the closing file")
        )
    return out


@check("own_no_payment_after_escrow")
def check_own_no_payment_after_escrow(ctx: Context) -> list[Finding]:
    """No instalment is paid for a period that began after the parcel closed.

    This is the control the engine exists for. Units close one at a time while the
    roll keeps billing the account it always has, and the payment clears every
    normal check on the way through: the invoice is genuine, the payee is genuinely
    the county, the amount genuinely matches the notice. The only thing wrong is
    whose parcel it is, and that fact lives in a closing file the approver has
    never seen.
    """
    rule = "own_no_payment_after_escrow"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_INSTALMENT_SCHEDULE)
    if schedule is None:
        return []
    closings = _sale_index(ctx)
    out: list[Finding] = []
    checked = 0
    for inst in _instalments(ctx):
        parcel = _text(inst, "parcel_no")
        closing = closings.get(parcel or "")
        if closing is None:
            continue
        closed_on = _parse_date(closing.get("close_of_escrow_date"))
        paid_on = _parse_date(inst.get("paid_date"))
        due = _parse_date(inst.get("due_date"))
        if closed_on is None or paid_on is None or due is None:
            continue
        checked += 1
        if due > closed_on:
            with amount_guard(rule, out):
                amount = require_cents(
                    f"instalment[{parcel}/{inst.get('sequence')}].paid_amount_cents",
                    inst.get("paid_amount_cents"),
                )
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            schedule,
                            f"instalments/{parcel}/{inst.get('sequence')}/paid_amount_cents",
                        ),
                        f"parcel {parcel} closed {closed_on.isoformat()} but "
                        f"{fmt(amount)} was paid on {paid_on.isoformat()} for an "
                        f"instalment due {due.isoformat()}; that period belongs to the "
                        f"buyer",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"none of {checked} instalments on closed parcels cover a post-escrow period",
            )
        )
    return out


@check("own_proration_sums_to_annual")
def check_own_proration_sums_to_annual(ctx: Context) -> list[Finding]:
    """Seller's share plus buyer's share equals the annual charge.

    Zero tolerance, because the two shares are settled with two different parties.
    A proration that does not sum means somebody paid twice or nobody paid at all,
    and which one is not visible from either side of the closing table.
    """
    rule = "own_proration_sums_to_annual"
    _sev(rule, Status.FAIL)
    sales = ctx.one(DOC_SALE_REGISTER)
    if sales is None:
        return []
    parcels = _parcel_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _sales(ctx):
        parcel_no = _text(row, "parcel_no")
        parcel = parcels.get(parcel_no or "")
        if parcel is None:
            continue
        with amount_guard(rule, out):
            seller = require_cents(f"closing[{parcel_no}].seller_share_cents",
                                   row.get("seller_share_cents"))
            buyer = require_cents(f"closing[{parcel_no}].buyer_share_cents",
                                  row.get("buyer_share_cents"))
            annual = require_cents(f"parcel[{parcel_no}].annual_tax_cents",
                                   parcel.get("annual_tax_cents"))
            checked += 1
            if seller + buyer != annual:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(sales, f"closings/{parcel_no}/seller_share_cents"),
                        f"parcel {parcel_no} prorates {fmt(seller)} to the seller and "
                        f"{fmt(buyer)} to the buyer = {fmt(seller + buyer)}, against an "
                        f"annual charge of {fmt(annual)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} prorations sum to the annual charge")
        )
    return out


@check("own_proration_by_days_held")
def check_own_proration_by_days_held(ctx: Context) -> list[Finding]:
    """The seller's share is re-derived from the days actually held.

    Computed on the regime's own fiscal year -- which is the whole point, because a
    mid-year fiscal year makes "days held" a different number from the one a
    calendar-year instinct produces, on exactly the same closing date.
    """
    rule = "own_proration_by_days_held"
    _sev(rule, Status.FAIL)
    sales = ctx.one(DOC_SALE_REGISTER)
    tax_year = ctx.tax_year
    if sales is None or tax_year is None:
        return []
    parcels = _parcel_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _sales(ctx):
        parcel_no = _text(row, "parcel_no")
        parcel = parcels.get(parcel_no or "")
        if parcel is None:
            continue
        regime = _regime_for(ctx, parcel)
        closed_on = _parse_date(row.get("close_of_escrow_date"))
        if regime is None or closed_on is None:
            continue
        opens = _fiscal_year_start(regime, tax_year)
        if opens is None:
            continue
        with amount_guard(rule, out):
            annual = require_cents(f"parcel[{parcel_no}].annual_tax_cents",
                                   parcel.get("annual_tax_cents"))
            seller = require_cents(f"closing[{parcel_no}].seller_share_cents",
                                   row.get("seller_share_cents"))
            checked += 1
            days_held = (closed_on - opens).days
            days_held = max(0, min(days_held, PRORATION_DAYS))
            expected = annual * days_held // PRORATION_DAYS
            if seller != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(sales, f"closings/{parcel_no}/seller_share_cents"),
                        f"parcel {parcel_no} closed {closed_on.isoformat()}, "
                        f"{days_held} day(s) into a fiscal year opening "
                        f"{opens.isoformat()}; the seller's share of {fmt(annual)} derives "
                        f"to {fmt(expected)}, not {fmt(seller)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} prorations re-derive from days held"
            )
        )
    return out


@check("own_supplemental_on_transfer")
def check_own_supplemental_on_transfer(ctx: Context) -> list[Finding]:
    """Where the regime reassesses on transfer, a supplemental is recorded.

    A supplemental assessment lands months after the closing, addressed to a
    property the developer no longer owns, for a period during which it did. It is
    genuinely owed and genuinely easy to miss.
    """
    rule = "own_supplemental_on_transfer"
    _sev(rule, Status.FLAG)
    sales = ctx.one(DOC_SALE_REGISTER)
    if sales is None:
        return []
    parcels = _parcel_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _sales(ctx):
        parcel_no = _text(row, "parcel_no")
        parcel = parcels.get(parcel_no or "")
        if parcel is None:
            continue
        regime = _regime_for(ctx, parcel)
        if regime is None or regime.get("supplemental_on_transfer") is not True:
            continue
        checked += 1
        if row.get("supplemental_recorded") is not True:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(sales, f"closings/{parcel_no}/supplemental_recorded"),
                    f"parcel {parcel_no} sits in {_text(parcel, 'jurisdiction')}, which "
                    f"reassesses on change of ownership, and no supplemental is recorded "
                    f"against the closing",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} closings in reassessing jurisdictions record a supplemental",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# acr_ -- accrual and the ledger
# --------------------------------------------------------------------------- #
@check("acr_periods_tie_annual")
def check_acr_periods_tie_annual(ctx: Context) -> list[Finding]:
    """A held parcel's monthly accruals sum to its annual charge.

    Zero tolerance. Property tax is one of the few charges where the annual figure
    is known at the start of the year, so an accrual that does not foot to it is
    not an estimate -- it is a mistake.
    """
    rule = "acr_periods_tie_annual"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_ACCRUAL_LEDGER)
    if ledger is None:
        return []
    totals: dict[str, int] = {}
    out: list[Finding] = []
    for row in _accruals(ctx):
        parcel = _text(row, "parcel_no")
        if parcel is None:
            continue
        with amount_guard(rule, out):
            totals[parcel] = totals.get(parcel, 0) + require_cents(
                f"accrual[{parcel}/{_text(row, 'period')}].amount_cents",
                row.get("amount_cents"),
            )
    checked = 0
    for row in _parcels(ctx):
        parcel = _parcel_no(row)
        if _text(row, "status") != PARCEL_HELD:
            continue
        if parcel not in totals:
            continue
        with amount_guard(rule, out):
            annual = require_cents(f"parcel[{parcel}].annual_tax_cents",
                                   row.get("annual_tax_cents"))
            checked += 1
            if totals[parcel] != annual:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger, f"accruals/{parcel}"),
                        f"parcel {parcel} accrues {fmt(totals[parcel])} across the year "
                        f"against an annual charge of {fmt(annual)} "
                        f"(difference {fmt(totals[parcel] - annual)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} held parcels accrue to their charge")
        )
    return out


@check("acr_stops_at_escrow")
def check_acr_stops_at_escrow(ctx: Context) -> list[Finding]:
    """Accrual stops in the month a parcel closes.

    The mirror of the payment control, on the other side of the ledger. Accruing
    tax on a house somebody else owns overstates the liability and understates the
    margin on the sale that already happened.
    """
    rule = "acr_stops_at_escrow"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_ACCRUAL_LEDGER)
    if ledger is None:
        return []
    closings = _sale_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _accruals(ctx):
        parcel = _text(row, "parcel_no")
        closing = closings.get(parcel or "")
        period = _text(row, "period")
        if closing is None or period is None or not _PERIOD_RE.match(period):
            continue
        closed_on = _parse_date(closing.get("close_of_escrow_date"))
        if closed_on is None:
            continue
        checked += 1
        closed_period = f"{closed_on.year:04d}-{closed_on.month:02d}"
        if period <= closed_period:
            continue
        with amount_guard(rule, out):
            amount = require_cents(
                f"accrual[{parcel}/{period}].amount_cents", row.get("amount_cents")
            )
            if amount != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger, f"accruals/{parcel}/{period}"),
                        f"parcel {parcel} closed {closed_on.isoformat()} but still accrues "
                        f"{fmt(amount)} in {period}; the liability is for a house the "
                        f"developer no longer owns",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"accrual stops at escrow across {checked} period rows"
            )
        )
    return out


@check("acr_ties_gl_liability")
def check_acr_ties_gl_liability(ctx: Context) -> list[Finding]:
    """Total accrued property tax equals the general-ledger liability."""
    rule = "acr_ties_gl_liability"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    if gl is None:
        return []
    out: list[Finding] = []
    derived = 0
    for row in _accruals(ctx):
        with amount_guard(rule, out):
            derived += require_cents(
                f"accrual[{_text(row, 'parcel_no')}/{_text(row, 'period')}].amount_cents",
                row.get("amount_cents"),
            )
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.property_tax_accrued_cents", gl.get("property_tax_accrued_cents")
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "property_tax_accrued_cents"),
                    f"the ledger carries {fmt(stated)} of accrued property tax; the accrual "
                    f"detail sums to {fmt(derived)} (difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"accrued property tax of {fmt(derived)} ties the GL"
                )
            )
    return out


@check("acr_capitalisation_matches_stage")
def check_acr_capitalisation_matches_stage(ctx: Context) -> list[Finding]:
    """Tax capitalises while a project is in development and expenses after.

    Carrying cost on land under development belongs in the job; the same charge on
    a finished project is period expense. The distinction is the project's stage,
    not the parcel's, and it moves once.
    """
    rule = "acr_capitalisation_matches_stage"
    _sev(rule, Status.FLAG)
    ledger = ctx.one(DOC_ACCRUAL_LEDGER)
    if ledger is None:
        return []
    parcels = _parcel_index(ctx)
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _accruals(ctx):
        parcel_no = _text(row, "parcel_no")
        parcel = parcels.get(parcel_no or "")
        if parcel is None:
            continue
        project = projects.get(_text(parcel, "project_code") or "")
        if project is None or not isinstance(row.get("capitalised"), bool):
            continue
        checked += 1
        expected = _text(project, "stage") == STAGE_DEVELOPMENT
        if row["capitalised"] is not expected:
            treatment = "capitalised" if row["capitalised"] else "expensed"
            want = "capitalised" if expected else "expensed"
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(ledger, f"accruals/{parcel_no}/{_text(row, 'period')}/capitalised"),
                    f"parcel {parcel_no} is {treatment} in {_text(row, 'period')} while its "
                    f"project is {_text(project, 'stage')!r}; tax on a "
                    f"{_text(project, 'stage')} project is {want}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} accrual rows match their project's stage"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# pay_ -- what was actually paid
# --------------------------------------------------------------------------- #
@check("pay_amount_ties_notice")
def check_pay_amount_ties_notice(ctx: Context) -> list[Finding]:
    """What was paid equals the instalment plus any penalty and interest.

    The last arithmetic in the cycle, and the one that catches a payment made
    against the wrong notice: paying the right county the right way for the wrong
    parcel produces a figure that matches nothing here.
    """
    rule = "pay_amount_ties_notice"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_INSTALMENT_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for inst in _instalments(ctx):
        if _parse_date(inst.get("paid_date")) is None:
            continue
        parcel = _text(inst, "parcel_no")
        with amount_guard(rule, out):
            amount = require_cents(
                f"instalment[{parcel}/{inst.get('sequence')}].amount_cents",
                inst.get("amount_cents"),
            )
            penalty = require_cents(
                f"instalment[{parcel}/{inst.get('sequence')}].penalty_cents",
                inst.get("penalty_cents"),
            )
            interest = require_cents(
                f"instalment[{parcel}/{inst.get('sequence')}].interest_cents",
                inst.get("interest_cents"),
            )
            paid = require_cents(
                f"instalment[{parcel}/{inst.get('sequence')}].paid_amount_cents",
                inst.get("paid_amount_cents"),
            )
            checked += 1
            expected = amount + penalty + interest
            if paid != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            schedule,
                            f"instalments/{parcel}/{inst.get('sequence')}/paid_amount_cents",
                        ),
                        f"parcel {parcel} instalment {inst.get('sequence')} paid {fmt(paid)} "
                        f"against {fmt(amount)} charged plus {fmt(penalty)} penalty and "
                        f"{fmt(interest)} interest = {fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} payments tie to what was owed")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one roll file."""
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
    """Analyze every ``.json`` roll file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of roll-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
