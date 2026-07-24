"""
Project labor charge control engine (READ-ONLY).
================================================

Loads each charge-run file (a ``.json`` file produced by
:mod:`labor_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether a labor charge was authorized and computed
correctly**, not about how the employee was paid. Payroll owns the burdened rate;
this engine owns the charge that rides on it. A project manager notifies the
project accountant in advance -- start date, cost code, budget confirmation, and a
fixed monthly amount or a percentage of the fully-burdened cost -- and every month
a charge lands that must match that authorization, foot into an invoice, and stay
inside budget.

The shape of the problem
------------------------
Four failures hide inside a monthly invoice run, and none of them look wrong:

1. the charge that outruns the authorization (a fixed amount that does not match,
   or a percentage that does not re-derive from the burdened cost to the cent);
2. the charge that predates the authorized start date;
3. the charge that lands on a project or cost code nobody authorized;
4. the budget quietly overrun by the cumulative charge.

The registry is organised around that:

1. ``set_``   -- is the charge-run file complete?
2. ``emp_``   -- is the employee register sound (unique ids, positive burden)?
3. ``prj_``   -- is the project register sound (unique codes, positive budget)?
4. ``auth_``  -- is each authorization complete, valid, and correctly resolved?
5. ``chg_``   -- does every monthly charge match the authorization that permits it?
6. ``bud_``   -- does cumulative labor charge stay inside the project's budget?
7. ``inv_``   -- does each monthly invoice foot to the charges beneath it?
8. ``gl_``    -- does the ledger, and the invoiced total, tie the general ledger?

Design notes
------------
- **Strictly read-only.** Charge-run files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tie-out is compared with exact ``==``.
  The single tolerant control (``bud_near_budget``) reads its band from the project
  register rather than inventing one.
- **One derivation.** A percentage charge is re-derived with the same truncating
  rate primitive that produced it, so a mismatch is a real difference and never an
  artifact of two roundings.
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
    DOC_CHARGE_AUTHORIZATION,
    DOC_EMPLOYEE_REGISTER,
    DOC_GL_POSITIONS,
    DOC_LABOR_CHARGE_LEDGER,
    DOC_MONTHLY_INVOICE,
    DOC_PROJECT_REGISTER,
    DOC_TYPES,
    METHOD_FIXED,
    METHOD_PERCENT,
    METHODS,
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
    """Render an :class:`~labor_engine.money.AmountInvalidError` as a finding."""
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
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


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


def _valid_period(value: object) -> bool:
    return isinstance(value, str) and bool(_PERIOD_RE.match(value))


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
# Charge-run helpers
# --------------------------------------------------------------------------- #
def _employees(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_EMPLOYEE_REGISTER), "employees")


def _employee_index(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _employees(ctx):
        emp_id = _text(row, "id")
        if emp_id and emp_id not in out:
            out[emp_id] = row
    return out


def _projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PROJECT_REGISTER), "projects")


def _project_index(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _projects(ctx):
        code = _text(row, "code")
        if code and code not in out:
            out[code] = row
    return out


def _authorizations(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CHARGE_AUTHORIZATION), "authorizations")


def _auth_index(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    """Authorizations keyed by ``(employee_id, project_code)``; first row wins."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _authorizations(ctx):
        emp = _text(row, "employee_id")
        code = _text(row, "project_code")
        if emp and code and (emp, code) not in out:
            out[(emp, code)] = row
    return out


def _charges(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_LABOR_CHARGE_LEDGER), "charges")


def _invoices(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_MONTHLY_INVOICE), "invoices")


def _cost_codes(project: dict[str, Any]) -> list[str]:
    codes = project.get("cost_codes")
    if not isinstance(codes, list):
        return []
    return [c for c in codes if isinstance(c, str)]


def _auth_id(row: dict[str, Any]) -> str:
    value = row.get("authorization_id")
    return value if isinstance(value, str) and value else "?"


def _month_of(value: object) -> str | None:
    """The ``YYYY-MM`` month a date or period string falls in."""
    if not isinstance(value, str) or len(value) < 7:
        return None
    head = value[:7]
    if not _PERIOD_RE.match(head):
        return None
    return head


def resolved_charge(method: str, fixed_amount_cents: int, percent_bps: int,
                    burdened_cost_cents: int) -> int:
    """The monthly charge an authorization resolves to.

    A fixed authorization charges its stated amount; a percentage authorization
    charges the truncated rate applied to the fully-burdened cost. Defined in one
    place so the engine and the generator cannot drift on the derivation.
    """
    if method == METHOD_PERCENT:
        return apply_rate(burdened_cost_cents, percent_bps)
    return fixed_amount_cents


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the charge run depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the charge-run file "
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
                f"as_of {ctx.as_of!r} is not a readable date; the charge run is "
                f"measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# emp_ -- employee register
# --------------------------------------------------------------------------- #
@check("emp_required_fields")
def check_emp_required_fields(ctx: Context) -> list[Finding]:
    """Every employee carries the fields the authorization and charge read."""
    rule = "emp_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    required = ("id", "name")
    out: list[Finding] = []
    for row in _employees(ctx):
        emp_id = _text(row, "id") or "?"
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"employees/{emp_id}"),
                    f"employee {emp_id} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_employees(ctx))} employees are fully described"
            )
        )
    return out


@check("emp_id_unique")
def check_emp_id_unique(ctx: Context) -> list[Finding]:
    """No employee id appears twice.

    The id joins the register to every authorization and charge. A duplicate makes
    the burdened cost -- and every percentage charge derived from it -- ambiguous.
    """
    rule = "emp_id_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _employees(ctx):
        key = _text(row, "id") or "?"
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"employees/{emp_id}"),
            f"employee id {emp_id} appears {count} times; its burdened cost is "
            f"ambiguous",
        )
        for emp_id, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} employee ids are unique")
        )
    return out


@check("emp_burdened_cost_positive")
def check_emp_burdened_cost_positive(ctx: Context) -> list[Finding]:
    """Each employee's fully-burdened monthly cost is a positive integer of cents.

    It is the base a percentage authorization multiplies. A zero or negative burden
    would silently zero out every percentage charge that rides on it.
    """
    rule = "emp_burdened_cost_positive"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _employees(ctx):
        emp_id = _text(row, "id") or "?"
        with amount_guard(rule, out):
            burden = require_cents(
                f"employee[{emp_id}].monthly_burdened_cost_cents",
                row.get("monthly_burdened_cost_cents"),
            )
            checked += 1
            if burden <= 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"employees/{emp_id}/monthly_burdened_cost_cents"),
                        f"employee {emp_id} carries a burdened cost of {fmt(burden)}; it "
                        f"must be positive to charge over",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} burdened costs are positive")
        )
    return out


# --------------------------------------------------------------------------- #
# prj_ -- project register
# --------------------------------------------------------------------------- #
@check("prj_required_fields")
def check_prj_required_fields(ctx: Context) -> list[Finding]:
    """Every project carries a code, a name and at least one cost code."""
    rule = "prj_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _projects(ctx):
        code = _text(row, "code") or "?"
        missing = [f for f in ("code", "name") if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{code}"),
                    f"project {code} is missing {', '.join(missing)}",
                )
            )
        if not _cost_codes(row):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{code}/cost_codes"),
                    f"project {code} carries no cost codes; an authorization cannot name "
                    f"one that exists on it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_projects(ctx))} projects are fully described"
            )
        )
    return out


@check("prj_code_unique")
def check_prj_code_unique(ctx: Context) -> list[Finding]:
    """No project code appears twice.

    The code joins the register to every authorization, charge and invoice. A
    duplicate makes the labor budget it carries ambiguous.
    """
    rule = "prj_code_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _projects(ctx):
        key = _text(row, "code") or "?"
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"projects/{code}"),
            f"project code {code} appears {count} times; its labor budget is ambiguous",
        )
        for code, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} project codes are unique")
        )
    return out


@check("prj_budget_positive")
def check_prj_budget_positive(ctx: Context) -> list[Finding]:
    """Each project carries a positive labor budget parameter in integer cents.

    It is the ceiling every cumulative-charge control is measured against. A zero
    or negative budget makes the overrun test meaningless.
    """
    rule = "prj_budget_positive"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _projects(ctx):
        code = _text(row, "code") or "?"
        with amount_guard(rule, out):
            budget = require_cents(
                f"project[{code}].labor_budget_cents", row.get("labor_budget_cents")
            )
            checked += 1
            if budget <= 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"projects/{code}/labor_budget_cents"),
                        f"project {code} carries a labor budget of {fmt(budget)}; the "
                        f"overrun control needs a positive ceiling",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} labor budgets are positive")
        )
    return out


# --------------------------------------------------------------------------- #
# auth_ -- charge authorization
# --------------------------------------------------------------------------- #
@check("auth_required_fields")
def check_auth_required_fields(ctx: Context) -> list[Finding]:
    """Every authorization carries the fields every charge is checked against."""
    rule = "auth_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    required = (
        "employee_id", "project_code", "authorized_start", "notice_date",
        "cost_code", "method",
    )
    out: list[Finding] = []
    for row in _authorizations(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"authorizations/{_auth_id(row)}"),
                    f"authorization {_auth_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(_authorizations(ctx))} authorizations are fully described",
            )
        )
    return out


@check("auth_employee_exists")
def check_auth_employee_exists(ctx: Context) -> list[Finding]:
    """Every authorized employee is in the employee register."""
    rule = "auth_employee_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    employees = _employee_index(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"authorizations/{_auth_id(row)}/employee_id"),
            f"authorization {_auth_id(row)} names employee "
            f"{_text(row, 'employee_id')!r}, which is not in the register",
        )
        for row in _authorizations(ctx)
        if _text(row, "employee_id") and _text(row, "employee_id") not in employees
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every authorization names a known employee")
        )
    return out


@check("auth_project_exists")
def check_auth_project_exists(ctx: Context) -> list[Finding]:
    """Every authorized project is in the project register."""
    rule = "auth_project_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    projects = _project_index(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"authorizations/{_auth_id(row)}/project_code"),
            f"authorization {_auth_id(row)} names project "
            f"{_text(row, 'project_code')!r}, which is not in the register",
        )
        for row in _authorizations(ctx)
        if _text(row, "project_code") and _text(row, "project_code") not in projects
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every authorization names a known project")
        )
    return out


@check("auth_notice_before_start")
def check_auth_notice_before_start(ctx: Context) -> list[Finding]:
    """The project manager gave notice on or before the authorized start date.

    The point of the process is that the accountant is told *in advance*. A notice
    date after the start is a charge that was authorized retroactively -- the
    control the whole notify-in-advance rule exists to enforce.
    """
    rule = "auth_notice_before_start"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _authorizations(ctx):
        notice = _parse_date(row.get("notice_date"))
        start = _parse_date(row.get("authorized_start"))
        if notice is None or start is None:
            continue
        checked += 1
        if notice > start:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"authorizations/{_auth_id(row)}/notice_date"),
                    f"authorization {_auth_id(row)} gives notice {notice.isoformat()} for a "
                    f"start of {start.isoformat()}; the charge was authorized after it "
                    f"began, not in advance",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} authorizations gave advance notice")
        )
    return out


@check("auth_cost_code_on_project")
def check_auth_cost_code_on_project(ctx: Context) -> list[Finding]:
    """The authorized cost code exists on the project it charges.

    A cost code the project does not carry sends the charge to a bucket that does
    not exist, and the job-cost report silently drops it.
    """
    rule = "auth_cost_code_on_project"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    projects = _project_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _authorizations(ctx):
        code = _text(row, "project_code")
        cost_code = _text(row, "cost_code")
        project = projects.get(code or "")
        if project is None or cost_code is None:
            continue  # auth_project_exists / auth_required_fields own these
        checked += 1
        if cost_code not in _cost_codes(project):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"authorizations/{_auth_id(row)}/cost_code"),
                    f"authorization {_auth_id(row)} charges {code} on cost code "
                    f"{cost_code!r}, which is not one of that project's cost codes "
                    f"{_cost_codes(project)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} cost codes exist on their project")
        )
    return out


@check("auth_budget_confirmed")
def check_auth_budget_confirmed(ctx: Context) -> list[Finding]:
    """The authorization records that budget was confirmed before charging began.

    Confirming the labor budget is a precondition of the notify-in-advance process.
    An authorization that never confirmed it commits the project to a cost nobody
    checked it could carry.
    """
    rule = "auth_budget_confirmed"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _authorizations(ctx):
        checked += 1
        if row.get("budget_confirmed") is not True:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"authorizations/{_auth_id(row)}/budget_confirmed"),
                    f"authorization {_auth_id(row)} carries budget_confirmed="
                    f"{row.get('budget_confirmed')!r}; charging began without a confirmed "
                    f"budget",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} authorizations confirmed budget")
        )
    return out


@check("auth_method_valid")
def check_auth_method_valid(ctx: Context) -> list[Finding]:
    """Every authorization declares a charge method the engine understands."""
    rule = "auth_method_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"authorizations/{_auth_id(row)}/method"),
            f"authorization {_auth_id(row)} declares method "
            f"{_text(row, 'method')!r}, which is not one of {METHODS}",
        )
        for row in _authorizations(ctx)
        if _text(row, "method") not in METHODS
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(_authorizations(ctx))} authorizations declare a known method",
            )
        )
    return out


@check("auth_charge_derives")
def check_auth_charge_derives(ctx: Context) -> list[Finding]:
    """The resolved monthly charge re-derives from the method it was set on.

    A fixed authorization resolves to its stated amount; a percentage authorization
    resolves to the truncated rate applied to the employee's fully-burdened cost.
    The engine re-derives it the same way and compares to the cent, so a percentage
    that was resolved on a stale burden -- or simply keyed wrong -- is caught before
    a single month is charged.
    """
    rule = "auth_charge_derives"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CHARGE_AUTHORIZATION)
    if register is None:
        return []
    employees = _employee_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _authorizations(ctx):
        method = _text(row, "method")
        if method not in METHODS:
            continue  # auth_method_valid owns this
        emp_id = _text(row, "employee_id")
        employee = employees.get(emp_id or "")
        with amount_guard(rule, out):
            stated = require_cents(
                f"authorization[{_auth_id(row)}].monthly_charge_cents",
                row.get("monthly_charge_cents"),
            )
            if method == METHOD_PERCENT:
                if employee is None:
                    continue  # auth_employee_exists owns the missing burden
                burden = require_cents(
                    f"employee[{emp_id}].monthly_burdened_cost_cents",
                    employee.get("monthly_burdened_cost_cents"),
                )
                percent_bps = require_cents(
                    f"authorization[{_auth_id(row)}].percent_bps",
                    row.get("percent_bps"),
                    unit="basis points",
                )
                expected = apply_rate(burden, percent_bps)
                detail = (
                    f"{fmt_bps(percent_bps)} of a burdened cost of {fmt(burden)} "
                    f"derives {fmt(expected)}"
                )
            else:
                expected = require_cents(
                    f"authorization[{_auth_id(row)}].fixed_amount_cents",
                    row.get("fixed_amount_cents"),
                )
                detail = f"the fixed amount is {fmt(expected)}"
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"authorizations/{_auth_id(row)}/monthly_charge_cents"),
                        f"authorization {_auth_id(row)} resolves to a monthly charge of "
                        f"{fmt(stated)}; {detail} (difference {fmt(stated - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} monthly charges re-derive")
        )
    return out


# --------------------------------------------------------------------------- #
# chg_ -- the monthly charges
# --------------------------------------------------------------------------- #
@check("chg_authorized")
def check_chg_authorized(ctx: Context) -> list[Finding]:
    """Every charge names an employee-project pair some authorization permits.

    A charge to a pair no authorization covers is labor cost landing on a project
    no project manager ever agreed to carry it.
    """
    rule = "chg_authorized"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_LABOR_CHARGE_LEDGER)
    if ledger is None:
        return []
    authorized = _auth_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _charges(ctx):
        emp = _text(row, "employee_id")
        code = _text(row, "project_code")
        if emp is None or code is None:
            continue
        checked += 1
        if (emp, code) not in authorized:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"charges/{emp}/{code}/{_text(row, 'period')}"),
                    f"charge for {emp} on {code} in {_text(row, 'period')} has no "
                    f"authorization; the project never agreed to carry this employee",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges are authorized")
        )
    return out


@check("chg_not_before_start")
def check_chg_not_before_start(ctx: Context) -> list[Finding]:
    """No charge falls in a month before its authorization's start date.

    The authorization takes effect on a start date; a charge dated before the month
    that date falls in is a period nobody authorized -- notice was late, or the
    start slipped and the charge did not follow it.
    """
    rule = "chg_not_before_start"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_LABOR_CHARGE_LEDGER)
    if ledger is None:
        return []
    authorized = _auth_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _charges(ctx):
        emp = _text(row, "employee_id")
        code = _text(row, "project_code")
        auth = authorized.get((emp or "", code or ""))
        if auth is None:
            continue  # chg_authorized owns this
        start_month = _month_of(auth.get("authorized_start"))
        charge_month = _month_of(row.get("period"))
        if start_month is None or charge_month is None:
            continue
        checked += 1
        if charge_month < start_month:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"charges/{emp}/{code}/{charge_month}"),
                    f"charge for {emp} on {code} is dated {charge_month}, before the "
                    f"authorized start month {start_month}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges fall on or after their start")
        )
    return out


@check("chg_amount_matches_auth")
def check_chg_amount_matches_auth(ctx: Context) -> list[Finding]:
    """Each charge's amount equals the authorization's resolved monthly charge.

    This is the control the engine exists for: a fixed amount that was authorized,
    charged at a different figure, or a percentage charge that drifted from the one
    the authorization resolved to. The invoice still foots; the project simply
    carries the wrong number.
    """
    rule = "chg_amount_matches_auth"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_LABOR_CHARGE_LEDGER)
    if ledger is None:
        return []
    authorized = _auth_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _charges(ctx):
        emp = _text(row, "employee_id")
        code = _text(row, "project_code")
        auth = authorized.get((emp or "", code or ""))
        if auth is None:
            continue  # chg_authorized owns this
        with amount_guard(rule, out):
            amount = require_cents(
                f"charge[{emp}/{code}/{_text(row, 'period')}].amount_cents",
                row.get("amount_cents"),
            )
            expected = require_cents(
                f"authorization[{_auth_id(auth)}].monthly_charge_cents",
                auth.get("monthly_charge_cents"),
            )
            checked += 1
            if amount != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger, f"charges/{emp}/{code}/{_text(row, 'period')}"),
                        f"charge for {emp} on {code} in {_text(row, 'period')} is "
                        f"{fmt(amount)}; authorization {_auth_id(auth)} resolves to "
                        f"{fmt(expected)} (difference {fmt(amount - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges match their authorization")
        )
    return out


@check("chg_cost_code_matches_auth")
def check_chg_cost_code_matches_auth(ctx: Context) -> list[Finding]:
    """Each charge carries the cost code its authorization named.

    A charge posted to a different cost code -- even a valid one on the same project
    -- lands the labor cost in the wrong bucket of the job-cost report, and the
    variance surfaces against a line that never authorized the spend.
    """
    rule = "chg_cost_code_matches_auth"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_LABOR_CHARGE_LEDGER)
    if ledger is None:
        return []
    authorized = _auth_index(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _charges(ctx):
        emp = _text(row, "employee_id")
        code = _text(row, "project_code")
        auth = authorized.get((emp or "", code or ""))
        if auth is None:
            continue  # chg_authorized owns this
        charge_cost = _text(row, "cost_code")
        auth_cost = _text(auth, "cost_code")
        if charge_cost is None or auth_cost is None:
            continue
        checked += 1
        if charge_cost != auth_cost:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"charges/{emp}/{code}/{_text(row, 'period')}/cost_code"),
                    f"charge for {emp} on {code} in {_text(row, 'period')} posts to cost "
                    f"code {charge_cost!r}; authorization {_auth_id(auth)} named "
                    f"{auth_cost!r}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charges match their cost code")
        )
    return out


@check("chg_period_valid")
def check_chg_period_valid(ctx: Context) -> list[Finding]:
    """Every charge period is a well-formed ``YYYY-MM`` month.

    The period keys the charge to an invoice and to the start-date test. A malformed
    month cannot be compared to either, so it is caught before it can hide from them.
    """
    rule = "chg_period_valid"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_LABOR_CHARGE_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _charges(ctx):
        emp = _text(row, "employee_id") or "?"
        code = _text(row, "project_code") or "?"
        checked += 1
        if not _valid_period(row.get("period")):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"charges/{emp}/{code}/period"),
                    f"charge for {emp} on {code} carries period {row.get('period')!r}, "
                    f"which is not a well-formed YYYY-MM month",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} charge periods are well-formed")
        )
    return out


# --------------------------------------------------------------------------- #
# bud_ -- cumulative charge against the budget
# --------------------------------------------------------------------------- #
def _cumulative_by_project(ctx: Context, out: list[Finding], rule: str) -> dict[str, int]:
    """Sum of every charge, by project code, reading amounts as integer cents."""
    totals: dict[str, int] = {}
    for row in _charges(ctx):
        code = _text(row, "project_code")
        if code is None:
            continue
        with amount_guard(rule, out):
            totals[code] = totals.get(code, 0) + require_cents(
                f"charge[{code}/{_text(row, 'period')}].amount_cents",
                row.get("amount_cents"),
            )
    return totals


@check("bud_within_budget")
def check_bud_within_budget(ctx: Context) -> list[Finding]:
    """Cumulative labor charge does not exceed the project's labor budget.

    Over the budget is a hard failure: the job is being charged more labor than it
    was ever cleared to carry, and every month that passes makes the correction
    larger.
    """
    rule = "bud_within_budget"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    projects = _project_index(ctx)
    out: list[Finding] = []
    totals = _cumulative_by_project(ctx, out, rule)
    checked = 0
    for code, project in projects.items():
        with amount_guard(rule, out):
            budget = require_cents(
                f"project[{code}].labor_budget_cents", project.get("labor_budget_cents")
            )
            charged = totals.get(code, 0)
            checked += 1
            if charged > budget:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"projects/{code}/labor_budget_cents"),
                        f"project {code} has been charged {fmt(charged)} of labor against a "
                        f"budget of {fmt(budget)} (over by {fmt(charged - budget)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} projects are within labor budget")
        )
    return out


@check("bud_near_budget")
def check_bud_near_budget(ctx: Context) -> list[Finding]:
    """Cumulative labor charge nearing the budget is flagged for review.

    The warning band is read from the project's own ``labor_budget_warn_bps`` rather
    than an opinion baked into the engine. A project inside the band is not wrong --
    it is close enough that the next authorization needs a human's eyes before it is
    approved.
    """
    rule = "bud_near_budget"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_PROJECT_REGISTER)
    if register is None:
        return []
    projects = _project_index(ctx)
    out: list[Finding] = []
    totals = _cumulative_by_project(ctx, out, rule)
    checked = 0
    for code, project in projects.items():
        with amount_guard(rule, out):
            budget = require_cents(
                f"project[{code}].labor_budget_cents", project.get("labor_budget_cents")
            )
            warn_bps = require_cents(
                f"project[{code}].labor_budget_warn_bps",
                project.get("labor_budget_warn_bps"),
                unit="basis points",
            )
            charged = totals.get(code, 0)
            threshold = apply_rate(budget, warn_bps)
            checked += 1
            if charged > 0 and charged >= threshold:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"projects/{code}/labor_budget_cents"),
                        f"project {code} has been charged {fmt(charged)} of labor, at or "
                        f"above the {fmt_bps(warn_bps)} warning band ({fmt(threshold)}) of "
                        f"its {fmt(budget)} budget",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} projects are clear of the warning band")
        )
    return out


# --------------------------------------------------------------------------- #
# inv_ -- the monthly invoice
# --------------------------------------------------------------------------- #
@check("inv_total_ties_charges")
def check_inv_total_ties_charges(ctx: Context) -> list[Finding]:
    """Each monthly invoice total equals the sum of that project-period's charges.

    The invoice is what the project is billed; the charges are what it owes. Between
    them is an addition, and an addition is where a labor charge stops being a ledger
    row and becomes a number on a bill.
    """
    rule = "inv_total_ties_charges"
    _sev(rule, Status.FAIL)
    invoice_doc = ctx.one(DOC_MONTHLY_INVOICE)
    if invoice_doc is None:
        return []
    out: list[Finding] = []
    charged: dict[tuple[str, str], int] = {}
    for row in _charges(ctx):
        code = _text(row, "project_code")
        period = _text(row, "period")
        if code is None or period is None:
            continue
        with amount_guard(rule, out):
            key = (code, period)
            charged[key] = charged.get(key, 0) + require_cents(
                f"charge[{code}/{period}].amount_cents", row.get("amount_cents")
            )
    checked = 0
    for row in _invoices(ctx):
        code = _text(row, "project_code")
        period = _text(row, "period")
        if code is None or period is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"invoice[{code}/{period}].total_cents", row.get("total_cents")
            )
            charged_total = charged.get((code, period), 0)
            checked += 1
            if stated != charged_total:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(invoice_doc, f"invoices/{code}/{period}"),
                        f"invoice for {code} in {period} totals {fmt(stated)}; the charges "
                        f"for that project-period sum to {fmt(charged_total)} "
                        f"(difference {fmt(stated - charged_total)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} invoices foot to their charges")
        )
    return out


@check("inv_matches_charge_periods")
def check_inv_matches_charge_periods(ctx: Context) -> list[Finding]:
    """Every charged project-period is invoiced, and no invoice stands without charges.

    A project-period with charges but no invoice is labor cost that was never
    billed; an invoice with no charges bills a project for a month it did not work.
    Both foot cleanly in isolation, which is exactly why the two sets are compared.
    """
    rule = "inv_matches_charge_periods"
    _sev(rule, Status.FAIL)
    invoice_doc = ctx.one(DOC_MONTHLY_INVOICE)
    if invoice_doc is None:
        return []
    charged = {
        (_text(r, "project_code"), _text(r, "period"))
        for r in _charges(ctx)
        if _text(r, "project_code") and _text(r, "period")
    }
    invoiced = {
        (_text(r, "project_code"), _text(r, "period"))
        for r in _invoices(ctx)
        if _text(r, "project_code") and _text(r, "period")
    }
    out: list[Finding] = []
    for code, period in sorted(charged - invoiced):
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(invoice_doc, f"invoices/{code}/{period}"),
                f"project {code} carries charges in {period} but no invoice was raised; "
                f"the labor cost was never billed",
            )
        )
    for code, period in sorted(invoiced - charged):
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(invoice_doc, f"invoices/{code}/{period}"),
                f"an invoice was raised for {code} in {period} with no charges beneath it; "
                f"the project is billed for a month it did not work",
            )
        )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"all {len(charged)} charged project-periods are invoiced exactly once",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# gl_ -- the general ledger
# --------------------------------------------------------------------------- #
@check("gl_total_ties_ledger")
def check_gl_total_ties_ledger(ctx: Context) -> list[Finding]:
    """The GL labor-charge total equals the sum of every charge in the ledger."""
    rule = "gl_total_ties_ledger"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    if gl is None:
        return []
    out: list[Finding] = []
    derived = 0
    for row in _charges(ctx):
        with amount_guard(rule, out):
            derived += require_cents(
                f"charge[{_text(row, 'project_code')}/{_text(row, 'period')}].amount_cents",
                row.get("amount_cents"),
            )
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.total_labor_charge_cents", gl.get("total_labor_charge_cents")
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "total_labor_charge_cents"),
                    f"the ledger carries {fmt(stated)} of labor charge; the charge lines sum "
                    f"to {fmt(derived)} (difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"labor charge of {fmt(derived)} ties the ledger"
                )
            )
    return out


@check("gl_invoice_total_ties")
def check_gl_invoice_total_ties(ctx: Context) -> list[Finding]:
    """The GL invoice-control total equals the sum of every monthly invoice."""
    rule = "gl_invoice_total_ties"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    if gl is None:
        return []
    out: list[Finding] = []
    derived = 0
    for row in _invoices(ctx):
        with amount_guard(rule, out):
            derived += require_cents(
                f"invoice[{_text(row, 'project_code')}/{_text(row, 'period')}].total_cents",
                row.get("total_cents"),
            )
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.invoice_control_total_cents",
            gl.get("invoice_control_total_cents"),
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "invoice_control_total_cents"),
                    f"the invoice control account carries {fmt(stated)}; the monthly "
                    f"invoices sum to {fmt(derived)} (difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"invoiced total of {fmt(derived)} ties the ledger"
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one charge-run file."""
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
    """Analyze every ``.json`` charge-run file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of charge-run reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
