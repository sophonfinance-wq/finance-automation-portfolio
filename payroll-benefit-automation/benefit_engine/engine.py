"""
Payroll & benefit contribution reconciliation control engine (READ-ONLY).
=========================================================================

Loads each reconciliation file (a ``.json`` file produced by
:mod:`benefit_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether one pay period's benefit money tied out**: did
every deduction on the payroll register reach the provider, the ledger and cash
in the same amount; did the employer match recompute from the plan formula; did
anyone breach a statutory limit; did participant money land inside the deposit
safe harbor. It never runs payroll, never moves money and never writes to a
source artifact -- it is the check that the paper the period produced agrees with
itself and with the law.

The registry is organised by family, each family owning its structural gap:

1. ``set_``  -- is the reconciliation file complete?
2. ``emp_``  -- is the employee register sound?
3. ``pln_``  -- is the plan catalog sound?
4. ``ded_``  -- do the register deductions reference real rows and reach the provider per employee?
5. ``tie_``  -- does each plan's register total tie to every provider, the ledger and cash?
6. ``ent_``  -- do the entity subtotals recompute and sum to the consolidated total?
7. ``mat_``  -- does the employer match recompute from the formula, capped at 401(a)(17)?
8. ``lim_``  -- is every employee inside the 402(g), HSA, FSA and 415(c) ceilings?
9. ``whh_``  -- does the per-period HSA withholding recompute from the remaining room?
10. ``dol_`` -- did participant money remit inside the safe harbor, on-or-after the pay date?
11. ``je_``  -- does the journal entry balance and does the benefit clearing account zero out?
12. ``rpt_`` -- does the rollup recompute from the evidence it summarises?

Design notes
------------
- **Strictly read-only.** Reconciliation files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tie-out is compared with exact ``==``.
- **One set of predicates.** Controls and the generator share the kernel in
  :mod:`benefit_engine.reconcile`, so a determination cannot disagree with the
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
    DOC_DEDUCTION_REGISTER,
    DOC_EMPLOYEE_REGISTER,
    DOC_ENTITY_SUMMARY,
    DOC_JOURNAL_ENTRY,
    DOC_PLAN_CATALOG,
    DOC_PROVIDER_FILE,
    DOC_RECONCILIATION_REPORT,
    DOC_REMITTANCE_SCHEDULE,
    DOC_TYPES,
    ENTITIES,
    HSA_TIERS,
    PLAN_DEFERRAL,
    PLAN_FSA_DEPENDENT,
    PLAN_FSA_MEDICAL,
    PLAN_HSA,
    PLAN_MATCH,
    PLAN_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents
from .reconcile import (
    age_on,
    business_days_between,
    capped_match,
    deferral_limit,
    derive_match,
    hsa_limit,
    per_period_base,
    per_period_max,
    plan_is_tied,
    remaining_room,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~benefit_engine.money.AmountInvalidError` as a finding."""
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


def _amount(row: dict[str, Any], key: str, label: str) -> int:
    """Read an integer-cent field or raise :class:`AmountInvalidError`."""
    return require_cents(label, row.get(key))


# --------------------------------------------------------------------------- #
# Employee-register helpers
# --------------------------------------------------------------------------- #
def _employees(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_EMPLOYEE_REGISTER), "employees")


def _employee_id(row: dict[str, Any]) -> str:
    value = row.get("employee_id")
    return value if isinstance(value, str) and value else "?"


def _employee_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _employees(ctx):
        eid = _employee_id(row)
        if eid != "?" and eid not in out:
            out[eid] = row
    return out


def _prior_ytd(emp: dict[str, Any], plan_code: str) -> int:
    """Employee's prior year-to-date contribution to ``plan_code`` (0 if absent)."""
    prior = emp.get("prior_ytd")
    if not isinstance(prior, dict) or plan_code not in prior:
        return 0
    return require_cents(f"employee[{_employee_id(emp)}].prior_ytd.{plan_code}", prior[plan_code])


# --------------------------------------------------------------------------- #
# Plan-catalog helpers
# --------------------------------------------------------------------------- #
def _plans(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PLAN_CATALOG), "plans")


def _plan_code(row: dict[str, Any]) -> str:
    value = row.get("plan_code")
    return value if isinstance(value, str) and value else "?"


def _plan_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _plans(ctx):
        pc = _plan_code(row)
        if pc != "?" and pc not in out:
            out[pc] = row
    return out


def _plan_type(plan: dict[str, Any]) -> str | None:
    return _text(plan, "plan_type")


def _plan_providers(plan: dict[str, Any]) -> list[str]:
    value = plan.get("providers")
    if not isinstance(value, list):
        return []
    return [p for p in value if isinstance(p, str) and p]


def _plans_of_type(ctx: Context, plan_type: str) -> list[dict[str, Any]]:
    return [p for p in _plans(ctx) if _plan_type(p) == plan_type]


def _match_plan(ctx: Context) -> dict[str, Any] | None:
    matches = _plans_of_type(ctx, PLAN_MATCH)
    return matches[0] if matches else None


# --------------------------------------------------------------------------- #
# Deduction / provider / remittance / JE helpers
# --------------------------------------------------------------------------- #
def _deductions(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DEDUCTION_REGISTER), "deductions")


def _uploads(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PROVIDER_FILE), "uploads")


def _remittances(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_REMITTANCE_SCHEDULE), "remittances")


def _entity_subtotals(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ENTITY_SUMMARY), "subtotals")


def _consolidated(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ENTITY_SUMMARY), "consolidated")


def _je_lines(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_JOURNAL_ENTRY), "lines")


def _deduction_amount(ctx: Context, employee_id: str, plan_code: str) -> int:
    """Sum of register deductions for one (employee, plan) pair (0 if none)."""
    total = 0
    for row in _deductions(ctx):
        if _text(row, "employee_id") == employee_id and _text(row, "plan_code") == plan_code:
            total += _amount(row, "amount_cents", f"deduction[{employee_id}/{plan_code}].amount_cents")
    return total


def register_total(ctx: Context, plan_code: str) -> int:
    """Payroll-register total deducted for ``plan_code`` this period."""
    total = 0
    for row in _deductions(ctx):
        if _text(row, "plan_code") == plan_code:
            total += _amount(row, "amount_cents", f"deduction[{_text(row, 'employee_id')}/{plan_code}].amount_cents")
    return total


def register_total_entity(ctx: Context, entity: str, plan_code: str) -> int:
    """Register total for ``plan_code`` limited to employees in ``entity``."""
    emap = _employee_map(ctx)
    total = 0
    for row in _deductions(ctx):
        if _text(row, "plan_code") != plan_code:
            continue
        emp = emap.get(_text(row, "employee_id") or "")
        if emp is not None and _text(emp, "entity") == entity:
            total += _amount(row, "amount_cents", f"deduction[{_text(row, 'employee_id')}/{plan_code}].amount_cents")
    return total


def provider_total(ctx: Context, provider: str, plan_code: str) -> int:
    """Total uploaded to ``provider`` for ``plan_code``."""
    total = 0
    for row in _uploads(ctx):
        if _text(row, "provider") == provider and _text(row, "plan_code") == plan_code:
            total += _amount(row, "amount_cents", f"upload[{provider}/{plan_code}].amount_cents")
    return total


def je_liability_credit(ctx: Context, plan_code: str) -> int:
    """Journal-entry liability credit accrued for ``plan_code``.

    Sums the credits posted to that plan's liability account for that plan; the
    remittance debit relieving the same account is a separate leg.
    """
    plan = _plan_map(ctx).get(plan_code)
    if plan is None:
        return 0
    account = _text(plan, "gl_liability_account")
    if account is None:
        return 0
    total = 0
    for line in _je_lines(ctx):
        if _text(line, "gl_account") == account and _text(line, "plan_code") == plan_code:
            total += _amount(line, "credit_cents", f"je[{account}/{plan_code}].credit_cents")
    return total


def _cash_transfer(ctx: Context, plan_code: str) -> int | None:
    for row in _remittances(ctx):
        if _text(row, "plan_code") == plan_code:
            return _amount(row, "cash_transfer_cents", f"remittance[{plan_code}].cash_transfer_cents")
    return None


def _plan_codes_in_register(ctx: Context) -> list[str]:
    seen: list[str] = []
    for row in _deductions(ctx):
        pc = _text(row, "plan_code")
        if pc and pc not in seen:
            seen.append(pc)
    return sorted(seen)


def _known_plan_codes_in_register(ctx: Context) -> list[str]:
    """Register plan codes that resolve to a plan in the catalog.

    Deductions naming a plan the catalog does not carry are left entirely to
    ``ded_refs_valid``, so the tie-out and entity controls neither skip a real
    plan nor fire twice on one that was never defined.
    """
    plans = _plan_map(ctx)
    return [pc for pc in _plan_codes_in_register(ctx) if pc in plans]


def _entities_in_register(ctx: Context) -> list[str]:
    emap = _employee_map(ctx)
    seen: list[str] = []
    for row in _deductions(ctx):
        emp = emap.get(_text(row, "employee_id") or "")
        ent = _text(emp, "entity") if emp is not None else None
        if ent and ent not in seen:
            seen.append(ent)
    return sorted(seen)


# --------------------------------------------------------------------------- #
# Shared re-derivations (used by the generator too)
# --------------------------------------------------------------------------- #
def recompute_plan_tied(ctx: Context, plan_code: str) -> bool:
    """Recompute one plan's tie determination from the evidence.

    A plan ties when its register total equals every provider upload total, the
    journal-entry liability credit and the settling cash transfer. Shared with the
    generator through :func:`~benefit_engine.reconcile.plan_is_tied`.
    """
    plan = _plan_map(ctx).get(plan_code)
    providers = _plan_providers(plan) if plan is not None else []
    reg = register_total(ctx, plan_code)
    provider_totals = [provider_total(ctx, p, plan_code) for p in providers]
    liability = je_liability_credit(ctx, plan_code)
    cash = _cash_transfer(ctx, plan_code)
    if cash is None:
        return False
    return plan_is_tied(reg, provider_totals, liability, cash)


def _emp_age(ctx: Context, emp: dict[str, Any]) -> int | None:
    dob = _parse_date(emp.get("dob"))
    year_end = _parse_date(ctx.plan_year_end)
    if dob is None or year_end is None:
        return None
    return age_on(dob, year_end)


def _deferral_eval(ctx: Context, emp: dict[str, Any], plan: dict[str, Any]) -> tuple[int, int] | None:
    """(ytd, limit) for one employee's deferral plan, or ``None`` if inactive."""
    pc = _plan_code(plan)
    this = _deduction_amount(ctx, _employee_id(emp), pc)
    prior = _prior_ytd(emp, pc)
    if this == 0 and prior == 0:
        return None
    age = _emp_age(ctx, emp)
    if age is None:
        return None
    base = _amount(plan, "flat_limit_cents", f"plan[{pc}].flat_limit_cents")
    catchup = _amount(plan, "catchup_limit_cents", f"plan[{pc}].catchup_limit_cents")
    catchup_age = plan.get("catchup_age")
    if isinstance(catchup_age, bool) or not isinstance(catchup_age, int):
        return None
    return prior + this, deferral_limit(base, catchup, catchup_age, age)


def _hsa_eval(ctx: Context, emp: dict[str, Any], plan: dict[str, Any]) -> tuple[int, int] | None:
    pc = _plan_code(plan)
    this = _deduction_amount(ctx, _employee_id(emp), pc)
    prior = _prior_ytd(emp, pc)
    if this == 0 and prior == 0:
        return None
    age = _emp_age(ctx, emp)
    if age is None:
        return None
    tier = _text(emp, "hsa_coverage_tier") or ""
    self_only = _amount(plan, "self_only_limit_cents", f"plan[{pc}].self_only_limit_cents")
    family = _amount(plan, "family_limit_cents", f"plan[{pc}].family_limit_cents")
    catchup = _amount(plan, "catchup_limit_cents", f"plan[{pc}].catchup_limit_cents")
    catchup_age = plan.get("catchup_age")
    if isinstance(catchup_age, bool) or not isinstance(catchup_age, int):
        return None
    return prior + this, hsa_limit(self_only, family, catchup, catchup_age, tier, age)


def _fsa_eval(ctx: Context, emp: dict[str, Any], plan: dict[str, Any]) -> tuple[int, int] | None:
    pc = _plan_code(plan)
    this = _deduction_amount(ctx, _employee_id(emp), pc)
    prior = _prior_ytd(emp, pc)
    if this == 0 and prior == 0:
        return None
    cap = _amount(plan, "flat_limit_cents", f"plan[{pc}].flat_limit_cents")
    return prior + this, cap


def _additions_eval(ctx: Context, emp: dict[str, Any]) -> tuple[int, int, str] | None:
    """(annual additions, 415(c) limit, match plan code) for a match-eligible employee."""
    if not bool(emp.get("match_eligible")):
        return None
    match_plan = _match_plan(ctx)
    if match_plan is None:
        return None
    mpc = _plan_code(match_plan)
    additions = _deduction_amount(ctx, _employee_id(emp), mpc)
    for plan in _plans_of_type(ctx, PLAN_DEFERRAL):
        pc = _plan_code(plan)
        additions += _prior_ytd(emp, pc) + _deduction_amount(ctx, _employee_id(emp), pc)
    if additions == 0:
        return None
    limit = _amount(match_plan, "additions_limit_cents", f"plan[{mpc}].additions_limit_cents")
    return additions, limit, mpc


def recompute_exceptions(ctx: Context) -> list[dict[str, Any]]:
    """The statutory exception watchlist re-derived from the evidence.

    One entry per employee/plan that breaches -- or, for deferrals, approaches --
    a statutory ceiling. Shared with the generator so the stated watchlist ties to
    it. Kinds: ``deferral_over``/``deferral_watch`` (402(g)), ``hsa_over`` (tier
    limit), ``fsa_over`` (FSA cap), ``additions_over`` (415(c)).
    """
    band = ctx.deferral_watch_band_cents
    out: list[dict[str, Any]] = []
    for emp in _employees(ctx):
        eid = _employee_id(emp)
        for plan in _plans_of_type(ctx, PLAN_DEFERRAL):
            res = _deferral_eval(ctx, emp, plan)
            if res is None:
                continue
            ytd, limit = res
            if ytd > limit:
                out.append({"employee_id": eid, "plan_code": _plan_code(plan), "kind": "deferral_over"})
            elif ytd >= limit - band:
                out.append({"employee_id": eid, "plan_code": _plan_code(plan), "kind": "deferral_watch"})
        for plan in _plans_of_type(ctx, PLAN_HSA):
            res = _hsa_eval(ctx, emp, plan)
            if res is None:
                continue
            ytd, limit = res
            if ytd > limit:
                out.append({"employee_id": eid, "plan_code": _plan_code(plan), "kind": "hsa_over"})
        for plan in (*_plans_of_type(ctx, PLAN_FSA_MEDICAL), *_plans_of_type(ctx, PLAN_FSA_DEPENDENT)):
            res = _fsa_eval(ctx, emp, plan)
            if res is None:
                continue
            ytd, cap = res
            if ytd > cap:
                out.append({"employee_id": eid, "plan_code": _plan_code(plan), "kind": "fsa_over"})
        add = _additions_eval(ctx, emp)
        if add is not None:
            additions, limit, mpc = add
            if additions > limit:
                out.append({"employee_id": eid, "plan_code": mpc, "kind": "additions_over"})
    out.sort(key=lambda e: (e["employee_id"], e["plan_code"], e["kind"]))
    return out


def _normalize_exception(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (entry.get("employee_id"), entry.get("plan_code"), entry.get("kind"))


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the reconciliation file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the reconciliation file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(DOC_TYPES)} reconciliation artifacts are present")
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every date-gate is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# emp_ -- the employee register
# --------------------------------------------------------------------------- #
@check("emp_unique_ids")
def check_emp_unique_ids(ctx: Context) -> list[Finding]:
    """No employee id appears twice.

    The employee id joins the register to every deduction and every provider
    upload. A duplicate makes a deduction ambiguous about whom it belongs to.
    """
    rule = "emp_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _employees(ctx):
        seen[_employee_id(row)] = seen.get(_employee_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"employees/{eid}"),
            f"employee id {eid} appears {count} times; a deduction that names it cannot "
            f"be attributed to one employee",
        )
        for eid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} employee ids are unique"))
    return out


@check("emp_entity_valid")
def check_emp_entity_valid(ctx: Context) -> list[Finding]:
    """Every employee is assigned to a known employing entity.

    Payroll is partitioned by entity; an employee typed to an unknown entity has
    no subtotal to roll into and no consolidated total to reconcile against.
    """
    rule = "emp_entity_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _employees(ctx):
        entity = _text(row, "entity")
        if entity not in ENTITIES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"employees/{_employee_id(row)}/entity"),
                    f"employee {_employee_id(row)} is assigned entity {entity!r}, not one of "
                    f"{ENTITIES}; its deductions cannot be partitioned",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(_employees(ctx))} employees carry a known entity"))
    return out


@check("emp_fields_valid")
def check_emp_fields_valid(ctx: Context) -> list[Finding]:
    """Every employee carries a parseable DOB, a known HSA tier and integer comp.

    The date of birth drives the age-50 and age-55 catch-up gates, the tier
    selects the HSA limit, and the eligible compensation feeds the match; a
    malformed one silently disables the control that reads it.
    """
    rule = "emp_fields_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _employees(ctx):
        eid = _employee_id(row)
        if _parse_date(row.get("dob")) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"employees/{eid}/dob"),
                    f"employee {eid} has DOB {row.get('dob')!r}, which is not a readable date; "
                    f"the age-50/55 catch-up gate cannot be measured",
                )
            )
        if _text(row, "hsa_coverage_tier") not in HSA_TIERS:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"employees/{eid}/hsa_coverage_tier"),
                    f"employee {eid} has HSA tier {row.get('hsa_coverage_tier')!r}, not one of "
                    f"{HSA_TIERS}; the HSA limit cannot be selected",
                )
            )
        with amount_guard(rule, out):
            _amount(row, "eligible_comp_cents", f"employee[{eid}].eligible_comp_cents")
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(_employees(ctx))} employees carry valid fields"))
    return out


# --------------------------------------------------------------------------- #
# pln_ -- the plan catalog
# --------------------------------------------------------------------------- #
@check("pln_unique_codes")
def check_pln_unique_codes(ctx: Context) -> list[Finding]:
    """No plan code appears twice.

    The plan code keys every deduction, provider upload and journal line to its
    plan; a duplicate makes the plan a deduction settles against ambiguous.
    """
    rule = "pln_unique_codes"
    _sev(rule, Status.FAIL)
    catalog = ctx.one(DOC_PLAN_CATALOG)
    if catalog is None:
        return []
    seen: dict[str, int] = {}
    for row in _plans(ctx):
        seen[_plan_code(row)] = seen.get(_plan_code(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(catalog, f"plans/{pc}"),
            f"plan code {pc} appears {count} times; a deduction that names it cannot be "
            f"attributed to one plan",
        )
        for pc, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} plan codes are unique"))
    return out


@check("pln_type_valid")
def check_pln_type_valid(ctx: Context) -> list[Finding]:
    """Every plan carries a known plan type.

    The plan type selects which controls apply and which statutory limit is
    tested; an unknown type has no controls, so a deduction to it checks nothing.
    """
    rule = "pln_type_valid"
    _sev(rule, Status.FAIL)
    catalog = ctx.one(DOC_PLAN_CATALOG)
    if catalog is None:
        return []
    out: list[Finding] = []
    for row in _plans(ctx):
        ptype = _plan_type(row)
        if ptype not in PLAN_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(catalog, f"plans/{_plan_code(row)}/plan_type"),
                    f"plan {_plan_code(row)} is typed {ptype!r}, which is not one of "
                    f"{PLAN_TYPES}; no control applies to it",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(_plans(ctx))} plans carry a known type"))
    return out


# --------------------------------------------------------------------------- #
# ded_ -- the deduction register and the per-employee provider hand-off
# --------------------------------------------------------------------------- #
@check("ded_refs_valid")
def check_ded_refs_valid(ctx: Context) -> list[Finding]:
    """Every deduction names an employee in the register and a plan in the catalog."""
    rule = "ded_refs_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEDUCTION_REGISTER)
    if register is None:
        return []
    employees = _employee_map(ctx)
    plans = _plan_map(ctx)
    out: list[Finding] = []
    for row in _deductions(ctx):
        eid = _text(row, "employee_id")
        pc = _text(row, "plan_code")
        if eid and eid not in employees:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deductions/{eid}/{pc}/employee_id"),
                    f"deduction names employee {eid!r}, which is not in the employee register",
                )
            )
        if pc and pc not in plans:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deductions/{eid}/{pc}/plan_code"),
                    f"deduction names plan {pc!r}, which is not in the plan catalog",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(_deductions(ctx))} deductions reference known rows"))
    return out


@check("ded_unique_pairs")
def check_ded_unique_pairs(ctx: Context) -> list[Finding]:
    """No (employee, plan) pair carries two deduction rows.

    One employee's deduction to one plan is one figure; two rows for it double the
    withholding and make every downstream total for that plan ambiguous.
    """
    rule = "ded_unique_pairs"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEDUCTION_REGISTER)
    if register is None:
        return []
    seen: dict[tuple[str, str], int] = {}
    for row in _deductions(ctx):
        key = (_text(row, "employee_id") or "?", _text(row, "plan_code") or "?")
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"deductions/{eid}/{pc}"),
            f"employee {eid} has {count} deduction rows for plan {pc}; the pair must be a "
            f"single figure",
        )
        for (eid, pc), count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} employee/plan deduction pairs are unique"))
    return out


@check("ded_matches_provider")
def check_ded_matches_provider(ctx: Context) -> list[Finding]:
    """Each employee's deduction equals what reached each of the plan's providers.

    This is the per-employee hand-off: the amount withheld on the register must be
    the amount uploaded to the recordkeeper *and* the custodian (a 401(k) has two),
    to the cent. A deduction with no matching upload never left the building.
    """
    rule = "ded_matches_provider"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROVIDER_FILE)
    if register is None:
        return []
    plans = _plan_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _deductions(ctx):
        eid = _text(row, "employee_id")
        pc = _text(row, "plan_code")
        plan = plans.get(pc or "")
        if eid is None or plan is None:
            continue  # ded_refs_valid owns this
        with amount_guard(rule, out):
            deducted = _amount(row, "amount_cents", f"deduction[{eid}/{pc}].amount_cents")
            for provider in _plan_providers(plan):
                checked += 1
                uploads = [
                    u
                    for u in _uploads(ctx)
                    if _text(u, "provider") == provider
                    and _text(u, "plan_code") == pc
                    and _text(u, "employee_id") == eid
                ]
                if not uploads:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"uploads/{provider}/{pc}/{eid}"),
                            f"employee {eid} was deducted {fmt(deducted)} for {pc} but no upload "
                            f"to {provider} carries it; the money never reached the provider",
                        )
                    )
                    continue
                uploaded = sum(
                    _amount(u, "amount_cents", f"upload[{provider}/{pc}/{eid}].amount_cents") for u in uploads
                )
                if uploaded != deducted:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"uploads/{provider}/{pc}/{eid}/amount_cents"),
                            f"employee {eid} {pc}: register deducted {fmt(deducted)} but "
                            f"{provider} received {fmt(uploaded)} "
                            f"(off {fmt(uploaded - deducted)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} per-employee provider hand-offs tie"))
    return out


# --------------------------------------------------------------------------- #
# tie_ -- plan-level multi-way tie-out
# --------------------------------------------------------------------------- #
@check("tie_provider_total")
def check_tie_provider_total(ctx: Context) -> list[Finding]:
    """Each plan's register total equals every provider's upload total.

    Where the per-employee control catches a single mis-keyed line, this catches a
    plan that ties to the recordkeeper but not the custodian, or an upload file
    carrying a row that answers to no deduction.
    """
    rule = "tie_provider_total"
    _sev(rule, Status.FAIL)
    provider_reg = ctx.one(DOC_PROVIDER_FILE)
    if provider_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for plan in _plans(ctx):
        pc = _plan_code(plan)
        with amount_guard(rule, out):
            reg = register_total(ctx, pc)
            for provider in _plan_providers(plan):
                checked += 1
                total = provider_total(ctx, provider, pc)
                if total != reg:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(provider_reg, f"uploads/{provider}/{pc}"),
                            f"plan {pc}: register total {fmt(reg)} but {provider} upload total "
                            f"{fmt(total)} (off {fmt(total - reg)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} plan/provider upload totals tie the register"))
    return out


@check("tie_je_liability")
def check_tie_je_liability(ctx: Context) -> list[Finding]:
    """Each plan's register total equals the journal-entry liability credit.

    The payable the ledger accrues for a plan is the money the register withheld
    for it; a credit that does not equal the register total books a liability the
    payroll never created.
    """
    rule = "tie_je_liability"
    _sev(rule, Status.FAIL)
    je = ctx.one(DOC_JOURNAL_ENTRY)
    if je is None:
        return []
    out: list[Finding] = []
    checked = 0
    for pc in _known_plan_codes_in_register(ctx):
        with amount_guard(rule, out):
            reg = register_total(ctx, pc)
            liability = je_liability_credit(ctx, pc)
            checked += 1
            if liability != reg:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(je, f"lines/{pc}/credit_cents"),
                        f"plan {pc}: register total {fmt(reg)} but journal-entry liability credit "
                        f"{fmt(liability)} (off {fmt(liability - reg)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} liability credits tie the register"))
    return out


@check("tie_cash_transfer")
def check_tie_cash_transfer(ctx: Context) -> list[Finding]:
    """Each plan's register total equals the settling cash transfer.

    The cash that leaves the operating account to fund a plan is the money the
    register withheld for it; a transfer off the liability it settles either
    overfunds the provider or leaves the payable short.
    """
    rule = "tie_cash_transfer"
    _sev(rule, Status.FAIL)
    remit = ctx.one(DOC_REMITTANCE_SCHEDULE)
    if remit is None:
        return []
    out: list[Finding] = []
    checked = 0
    for pc in _known_plan_codes_in_register(ctx):
        with amount_guard(rule, out):
            reg = register_total(ctx, pc)
            cash = _cash_transfer(ctx, pc)
            checked += 1
            if cash is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(remit, f"remittances/{pc}/cash_transfer_cents"),
                        f"plan {pc}: register withheld {fmt(reg)} but the schedule carries no "
                        f"cash transfer for it",
                    )
                )
            elif cash != reg:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(remit, f"remittances/{pc}/cash_transfer_cents"),
                        f"plan {pc}: register total {fmt(reg)} but cash transfer {fmt(cash)} "
                        f"(off {fmt(cash - reg)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} cash transfers tie the register"))
    return out


# --------------------------------------------------------------------------- #
# ent_ -- multi-entity completeness
# --------------------------------------------------------------------------- #
@check("ent_subtotal_recomputes")
def check_ent_subtotal_recomputes(ctx: Context) -> list[Finding]:
    """Each (entity, plan) subtotal recomputes from the register.

    Payroll is filed per entity; a subtotal that does not equal the sum of that
    entity's own deductions -- or is missing entirely -- means an entity's file
    was built from something other than its register.
    """
    rule = "ent_subtotal_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_ENTITY_SUMMARY)
    if summary is None:
        return []
    stated: dict[tuple[str, str], int] = {}
    out: list[Finding] = []
    for row in _entity_subtotals(ctx):
        ent = _text(row, "entity")
        pc = _text(row, "plan_code")
        if ent and pc:
            with amount_guard(rule, out):
                stated[(ent, pc)] = _amount(row, "subtotal_cents", f"subtotal[{ent}/{pc}].subtotal_cents")
    checked = 0
    for ent in _entities_in_register(ctx):
        for pc in _known_plan_codes_in_register(ctx):
            with amount_guard(rule, out):
                expected = register_total_entity(ctx, ent, pc)
                if expected == 0:
                    continue
                checked += 1
                if (ent, pc) not in stated:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(summary, f"subtotals/{ent}/{pc}"),
                            f"entity {ent} plan {pc}: register sums to {fmt(expected)} but the "
                            f"entity summary carries no subtotal for it",
                        )
                    )
                elif stated[(ent, pc)] != expected:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(summary, f"subtotals/{ent}/{pc}/subtotal_cents"),
                            f"entity {ent} plan {pc}: subtotal {fmt(stated[(ent, pc)])} does not "
                            f"recompute to the register sum {fmt(expected)}",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} entity subtotals recompute from the register"))
    return out


@check("ent_consolidated_ties")
def check_ent_consolidated_ties(ctx: Context) -> list[Finding]:
    """Each plan's entity subtotals sum to the consolidated total, and to the register.

    The consolidated figure is what a single benefit provider is funded for; it
    must equal both the sum of the per-entity subtotals and the register total, or
    the entities do not add up to the whole.
    """
    rule = "ent_consolidated_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_ENTITY_SUMMARY)
    if summary is None:
        return []
    stated: dict[str, int] = {}
    out: list[Finding] = []
    for row in _consolidated(ctx):
        pc = _text(row, "plan_code")
        if pc:
            with amount_guard(rule, out):
                stated[pc] = _amount(row, "total_cents", f"consolidated[{pc}].total_cents")
    subtotal_sum: dict[str, int] = {}
    for row in _entity_subtotals(ctx):
        pc = _text(row, "plan_code")
        if pc:
            with amount_guard(rule, out):
                subtotal_sum[pc] = subtotal_sum.get(pc, 0) + _amount(
                    row, "subtotal_cents", f"subtotal[{_text(row, 'entity')}/{pc}].subtotal_cents"
                )
    checked = 0
    for pc in _known_plan_codes_in_register(ctx):
        with amount_guard(rule, out):
            reg = register_total(ctx, pc)
            checked += 1
            consolidated = stated.get(pc)
            if consolidated is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"consolidated/{pc}"),
                        f"plan {pc}: register total {fmt(reg)} but the summary carries no "
                        f"consolidated total for it",
                    )
                )
                continue
            if consolidated != reg:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"consolidated/{pc}/total_cents"),
                        f"plan {pc}: consolidated total {fmt(consolidated)} does not tie the "
                        f"register total {fmt(reg)}",
                    )
                )
            if subtotal_sum.get(pc, 0) != consolidated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"consolidated/{pc}/total_cents"),
                        f"plan {pc}: entity subtotals sum to {fmt(subtotal_sum.get(pc, 0))} but the "
                        f"consolidated total is {fmt(consolidated)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} consolidated totals tie the subtotals and register"))
    return out


# --------------------------------------------------------------------------- #
# mat_ -- employer-match re-derivation
# --------------------------------------------------------------------------- #
@check("mat_recomputes")
def check_mat_recomputes(ctx: Context) -> list[Finding]:
    """The booked employer match recomputes from the formula and eligible comp.

    Match is a re-derivation, not a stored figure: rate applied to eligible
    compensation (capped at 401(a)(17)). A booked match that does not equal the
    recomputed one credited an amount the formula does not produce.
    """
    rule = "mat_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEDUCTION_REGISTER)
    match_plan = _match_plan(ctx)
    if register is None or match_plan is None:
        return []
    mpc = _plan_code(match_plan)
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        rate = _amount(match_plan, "match_rate_bps", f"plan[{mpc}].match_rate_bps")
        cap = _amount(match_plan, "comp_cap_cents", f"plan[{mpc}].comp_cap_cents")
        for emp in _employees(ctx):
            if not bool(emp.get("match_eligible")):
                continue
            eid = _employee_id(emp)
            booked = _deduction_amount(ctx, eid, mpc)
            if booked == 0:
                continue
            comp = _amount(emp, "eligible_comp_cents", f"employee[{eid}].eligible_comp_cents")
            derived = derive_match(comp, rate, cap)
            checked += 1
            if booked != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"deductions/{eid}/{mpc}/amount_cents"),
                        f"employee {eid}: booked match {fmt(booked)} but the formula on "
                        f"{fmt(comp)} eligible comp recomputes {fmt(derived)} "
                        f"(off {fmt(booked - derived)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} employer matches recompute from the formula"))
    return out


@check("mat_comp_cap")
def check_mat_comp_cap(ctx: Context) -> list[Finding]:
    """A match on above-cap compensation is limited to the cap.

    Compensation above the 401(a)(17) ceiling is ineligible for match, so a
    high-earner's booked match may not exceed the rate applied to the cap itself.
    """
    rule = "mat_comp_cap"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEDUCTION_REGISTER)
    match_plan = _match_plan(ctx)
    if register is None or match_plan is None:
        return []
    mpc = _plan_code(match_plan)
    out: list[Finding] = []
    checked = 0
    with amount_guard(rule, out):
        rate = _amount(match_plan, "match_rate_bps", f"plan[{mpc}].match_rate_bps")
        cap = _amount(match_plan, "comp_cap_cents", f"plan[{mpc}].comp_cap_cents")
        ceiling = capped_match(cap, rate)
        for emp in _employees(ctx):
            if not bool(emp.get("match_eligible")):
                continue
            eid = _employee_id(emp)
            comp = _amount(emp, "eligible_comp_cents", f"employee[{eid}].eligible_comp_cents")
            if comp <= cap:
                continue
            booked = _deduction_amount(ctx, eid, mpc)
            checked += 1
            if booked > ceiling:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"deductions/{eid}/{mpc}/amount_cents"),
                        f"employee {eid} earns {fmt(comp)}, above the {fmt(cap)} comp cap; the "
                        f"booked match {fmt(booked)} exceeds the capped ceiling {fmt(ceiling)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} above-cap matches are limited to the cap"))
    return out


# --------------------------------------------------------------------------- #
# lim_ -- statutory annual-limit thresholds
# --------------------------------------------------------------------------- #
@check("lim_402g_deferral")
def check_lim_402g_deferral(ctx: Context) -> list[Finding]:
    """No employee's year-to-date deferral exceeds the 402(g) limit.

    The ceiling includes the age-50 catch-up for anyone fifty by plan-year-end;
    compared with exact ``>``, a deferral a cent over the limit is over the limit.
    """
    rule = "lim_402g_deferral"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for emp in _employees(ctx):
        for plan in _plans_of_type(ctx, PLAN_DEFERRAL):
            with amount_guard(rule, out):
                res = _deferral_eval(ctx, emp, plan)
                if res is None:
                    continue
                ytd, limit = res
                checked += 1
                if ytd > limit:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"employees/{_employee_id(emp)}/prior_ytd/{_plan_code(plan)}"),
                            f"employee {_employee_id(emp)} {_plan_code(plan)}: year-to-date deferral "
                            f"{fmt(ytd)} exceeds the 402(g) limit {fmt(limit)} "
                            f"(over {fmt(ytd - limit)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} deferrals are within the 402(g) limit"))
    return out


@check("lim_hsa_tier")
def check_lim_hsa_tier(ctx: Context) -> list[Finding]:
    """No employee's year-to-date HSA exceeds the tier limit.

    Self-only and family carry different ceilings, plus an age-55 catch-up; the
    tier and the DOB together select the limit the contribution is tested against.
    """
    rule = "lim_hsa_tier"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for emp in _employees(ctx):
        for plan in _plans_of_type(ctx, PLAN_HSA):
            with amount_guard(rule, out):
                res = _hsa_eval(ctx, emp, plan)
                if res is None:
                    continue
                ytd, limit = res
                checked += 1
                if ytd > limit:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"employees/{_employee_id(emp)}/prior_ytd/{_plan_code(plan)}"),
                            f"employee {_employee_id(emp)} ({_text(emp, 'hsa_coverage_tier')}): "
                            f"year-to-date HSA {fmt(ytd)} exceeds the tier limit {fmt(limit)} "
                            f"(over {fmt(ytd - limit)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} HSA contributions are within the tier limit"))
    return out


@check("lim_fsa_cap")
def check_lim_fsa_cap(ctx: Context) -> list[Finding]:
    """No employee's year-to-date FSA election exceeds the plan cap."""
    rule = "lim_fsa_cap"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for emp in _employees(ctx):
        for plan in (*_plans_of_type(ctx, PLAN_FSA_MEDICAL), *_plans_of_type(ctx, PLAN_FSA_DEPENDENT)):
            with amount_guard(rule, out):
                res = _fsa_eval(ctx, emp, plan)
                if res is None:
                    continue
                ytd, cap = res
                checked += 1
                if ytd > cap:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"employees/{_employee_id(emp)}/prior_ytd/{_plan_code(plan)}"),
                            f"employee {_employee_id(emp)} {_plan_code(plan)}: year-to-date FSA "
                            f"{fmt(ytd)} exceeds the cap {fmt(cap)} (over {fmt(ytd - cap)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} FSA elections are within the cap"))
    return out


@check("lim_415c_additions")
def check_lim_415c_additions(ctx: Context) -> list[Finding]:
    """No employee's annual additions exceed the 415(c) ceiling.

    Annual additions are employee deferrals plus the employer match; the ceiling
    is the outer bound on everything that can go into the defined-contribution plan
    in a year.
    """
    rule = "lim_415c_additions"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for emp in _employees(ctx):
        with amount_guard(rule, out):
            res = _additions_eval(ctx, emp)
            if res is None:
                continue
            additions, limit, mpc = res
            checked += 1
            if additions > limit:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"employees/{_employee_id(emp)}/annual_additions"),
                        f"employee {_employee_id(emp)}: annual additions {fmt(additions)} exceed "
                        f"the 415(c) limit {fmt(limit)} (over {fmt(additions - limit)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} employees are within the 415(c) limit"))
    return out


@check("lim_deferral_watch")
def check_lim_deferral_watch(ctx: Context) -> list[Finding]:
    """A deferral approaching its 402(g) limit is flagged for review.

    Deliberately a FLAG, not a failure: the employee is still under the limit, but
    inside the watch band and will breach if the deferral election is not trimmed
    for the periods that remain. The band comes from the file's own setting.
    """
    rule = "lim_deferral_watch"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_EMPLOYEE_REGISTER)
    if register is None:
        return []
    band = ctx.deferral_watch_band_cents
    out: list[Finding] = []
    checked = 0
    for emp in _employees(ctx):
        for plan in _plans_of_type(ctx, PLAN_DEFERRAL):
            with amount_guard(rule, out):
                res = _deferral_eval(ctx, emp, plan)
                if res is None:
                    continue
                ytd, limit = res
                checked += 1
                if limit - band <= ytd <= limit:
                    out.append(
                        Finding(
                            rule,
                            Status.FLAG,
                            ctx.loc(register, f"employees/{_employee_id(emp)}/prior_ytd/{_plan_code(plan)}"),
                            f"employee {_employee_id(emp)} {_plan_code(plan)}: year-to-date deferral "
                            f"{fmt(ytd)} is within {fmt(limit - ytd)} of the 402(g) limit "
                            f"{fmt(limit)}; trim before it breaches",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} deferrals are clear of the watch band"))
    return out


# --------------------------------------------------------------------------- #
# whh_ -- per-period withholding re-derivation
# --------------------------------------------------------------------------- #
@check("whh_per_period_recomputes")
def check_whh_per_period_recomputes(ctx: Context) -> list[Finding]:
    """The per-period HSA deduction recomputes from the remaining room.

    The level withholding is the room left this plan year -- tier limit less the
    employer contribution less the prior year-to-date -- spread over the remaining
    periods. A deduction that does not equal the recomputed base was not set from
    the room it is meant to consume.
    """
    rule = "whh_per_period_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEDUCTION_REGISTER)
    if register is None:
        return []
    periods = ctx.periods_remaining
    out: list[Finding] = []
    checked = 0
    for emp in _employees(ctx):
        for plan in _plans_of_type(ctx, PLAN_HSA):
            pc = _plan_code(plan)
            with amount_guard(rule, out):
                res = _hsa_eval(ctx, emp, plan)
                if res is None:
                    continue
                _ytd, limit = res
                employer = require_cents(
                    f"employee[{_employee_id(emp)}].hsa_employer_annual_cents",
                    emp.get("hsa_employer_annual_cents", 0),
                )
                prior = _prior_ytd(emp, pc)
                room = remaining_room(limit, employer, prior)
                expected = per_period_base(room, periods)
                actual = _deduction_amount(ctx, _employee_id(emp), pc)
                checked += 1
                if actual != expected:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"deductions/{_employee_id(emp)}/{pc}/amount_cents"),
                            f"employee {_employee_id(emp)} {pc}: per-period HSA {fmt(actual)} does "
                            f"not recompute to {fmt(expected)} = room {fmt(room)} over {periods} "
                            f"periods",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} HSA per-period deductions recompute"))
    return out


@check("whh_not_over_max")
def check_whh_not_over_max(ctx: Context) -> list[Finding]:
    """No per-period HSA deduction exceeds the largest pro-rated piece.

    Even the true-up period cannot withhold more than the remaining room divided
    across the remaining periods allows; a deduction above it over-withholds and
    drives the account past its limit before year-end.
    """
    rule = "whh_not_over_max"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEDUCTION_REGISTER)
    if register is None:
        return []
    periods = ctx.periods_remaining
    out: list[Finding] = []
    checked = 0
    for emp in _employees(ctx):
        for plan in _plans_of_type(ctx, PLAN_HSA):
            pc = _plan_code(plan)
            with amount_guard(rule, out):
                res = _hsa_eval(ctx, emp, plan)
                if res is None:
                    continue
                _ytd, limit = res
                employer = require_cents(
                    f"employee[{_employee_id(emp)}].hsa_employer_annual_cents",
                    emp.get("hsa_employer_annual_cents", 0),
                )
                prior = _prior_ytd(emp, pc)
                room = remaining_room(limit, employer, prior)
                ceiling = per_period_max(room, periods)
                actual = _deduction_amount(ctx, _employee_id(emp), pc)
                checked += 1
                if actual > ceiling:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(register, f"deductions/{_employee_id(emp)}/{pc}/amount_cents"),
                            f"employee {_employee_id(emp)} {pc}: per-period HSA {fmt(actual)} exceeds "
                            f"the pro-rated ceiling {fmt(ceiling)} (over {fmt(actual - ceiling)})",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} HSA per-period deductions are within the ceiling"))
    return out


# --------------------------------------------------------------------------- #
# dol_ -- deposit-timing safe harbor
# --------------------------------------------------------------------------- #
def _employee_money_plan_codes(ctx: Context) -> list[str]:
    return [
        _plan_code(p)
        for p in _plans(ctx)
        if bool(p.get("is_employee_money"))
    ]


@check("dol_safe_harbor")
def check_dol_safe_harbor(ctx: Context) -> list[Finding]:
    """Participant money reached the provider inside the deposit safe harbor.

    Employee 401(k) and HSA money must be deposited within the DOL small-plan
    seven-business-day safe harbor of the pay date; the boundary is inclusive, so a
    deposit exactly on the seventh business day is timely and the eighth is late.
    """
    rule = "dol_safe_harbor"
    _sev(rule, Status.FAIL)
    remit = ctx.one(DOC_REMITTANCE_SCHEDULE)
    if remit is None:
        return []
    limit = ctx.safe_harbor_business_days
    employee_money = set(_employee_money_plan_codes(ctx))
    out: list[Finding] = []
    checked = 0
    for row in _remittances(ctx):
        pc = _text(row, "plan_code")
        if pc not in employee_money:
            continue
        pay = _parse_date(row.get("pay_date"))
        deposit = _parse_date(row.get("remit_date"))
        if pay is None or deposit is None:
            continue
        elapsed = business_days_between(pay, deposit)
        checked += 1
        if elapsed > limit:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(remit, f"remittances/{pc}/remit_date"),
                    f"plan {pc}: participant money paid {pay.isoformat()} was not deposited until "
                    f"{deposit.isoformat()}, {elapsed} business days out, past the {limit}-day "
                    f"safe harbor",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} participant deposits are inside the safe harbor"))
    return out


@check("dol_remit_after_pay")
def check_dol_remit_after_pay(ctx: Context) -> list[Finding]:
    """No remittance is dated before the pay date it settles.

    A deposit that predates the payroll it funds is a date entered backwards; every
    business-day count measured from it is meaningless, so it is caught before the
    safe-harbor test relies on it.
    """
    rule = "dol_remit_after_pay"
    _sev(rule, Status.FAIL)
    remit = ctx.one(DOC_REMITTANCE_SCHEDULE)
    if remit is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _remittances(ctx):
        pc = _text(row, "plan_code")
        pay = _parse_date(row.get("pay_date"))
        deposit = _parse_date(row.get("remit_date"))
        if pay is None or deposit is None:
            continue
        checked += 1
        if deposit < pay:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(remit, f"remittances/{pc}/remit_date"),
                    f"plan {pc}: remit date {deposit.isoformat()} precedes the pay date "
                    f"{pay.isoformat()}; the deposit cannot have settled before the payroll",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} remit dates fall on or after their pay date"))
    return out


# --------------------------------------------------------------------------- #
# je_ -- the journal entry
# --------------------------------------------------------------------------- #
@check("je_balances")
def check_je_balances(ctx: Context) -> list[Finding]:
    """The pay-period journal entry balances: total debits equal total credits."""
    rule = "je_balances"
    _sev(rule, Status.FAIL)
    je = ctx.one(DOC_JOURNAL_ENTRY)
    if je is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        debits = sum(_amount(line, "debit_cents", "je.debit_cents") for line in _je_lines(ctx))
        credits = sum(_amount(line, "credit_cents", "je.credit_cents") for line in _je_lines(ctx))
        if debits != credits:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(je, "lines"),
                    f"journal entry does not balance: debits {fmt(debits)} vs credits "
                    f"{fmt(credits)} (off {fmt(debits - credits)})",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"the journal entry balances at {fmt(debits)}")
            )
    return out


@check("je_clearing_zeroes")
def check_je_clearing_zeroes(ctx: Context) -> list[Finding]:
    """Every benefit clearing/payable account nets to zero after remittance.

    Each plan's liability account is credited when the deduction is accrued and
    debited when the money is remitted; if it does not net to zero, a payable was
    booked and never relieved, or relieved and never booked.
    """
    rule = "je_clearing_zeroes"
    _sev(rule, Status.FAIL)
    je = ctx.one(DOC_JOURNAL_ENTRY)
    if je is None:
        return []
    clearing = {
        _text(p, "gl_liability_account")
        for p in _plans(ctx)
        if _text(p, "gl_liability_account")
    }
    net: dict[str, int] = {}
    out: list[Finding] = []
    with amount_guard(rule, out):
        for line in _je_lines(ctx):
            account = _text(line, "gl_account")
            if account not in clearing:
                continue
            credit = _amount(line, "credit_cents", f"je[{account}].credit_cents")
            debit = _amount(line, "debit_cents", f"je[{account}].debit_cents")
            net[account] = net.get(account, 0) + credit - debit
    for account in sorted(net):
        if net[account] != 0:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(je, f"lines/{account}"),
                    f"clearing account {account} nets to {fmt(net[account])} after remittance; "
                    f"the benefit payable did not zero out",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(net)} clearing accounts net to zero"))
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence
# --------------------------------------------------------------------------- #
@check("rpt_tie_status_recomputes")
def check_rpt_tie_status_recomputes(ctx: Context) -> list[Finding]:
    """Each plan's stated tie determination recomputes from the evidence.

    This is the control the engine exists for. The reconciliation report calls a
    plan tied; the engine rebuilds that determination from the register, the
    provider files, the ledger and the cash transfer, and compares. A tie flag not
    recomputed from the legs beneath it is an assertion, not a reconciliation.
    """
    rule = "rpt_tie_status_recomputes"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_RECONCILIATION_REPORT)
    if report is None:
        return []
    out: list[Finding] = []
    for row in _rows(report, "plans"):
        pc = _text(row, "plan_code")
        if pc is None:
            continue
        stated = row.get("tied")
        with amount_guard(rule, out):
            recomputed = recompute_plan_tied(ctx, pc)
            if recomputed != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(report, f"plans/{pc}/tied"),
                        f"plan {pc} is reported tied={stated}; recomputing from its register, "
                        f"provider, ledger and cash legs gives tied={recomputed}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every plan tie flag recomputes from its evidence"))
    return out


@check("rpt_exception_watchlist_ties")
def check_rpt_exception_watchlist_ties(ctx: Context) -> list[Finding]:
    """The statutory exception watchlist ties the evidence.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists an exception the numbers do not support -- or omits one
    they do -- sends the review to the wrong place. It is rebuilt from the same
    limit re-derivations and compared.
    """
    rule = "rpt_exception_watchlist_ties"
    _sev(rule, Status.FLAG)
    report = ctx.one(DOC_RECONCILIATION_REPORT)
    if report is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        recomputed = [_normalize_exception(e) for e in recompute_exceptions(ctx)]
        stated = [_normalize_exception(e) for e in _rows(report, "exceptions")]
        want = sorted(recomputed)
        have = sorted(stated)
        if want != have:
            for entry in have:
                if entry not in want:
                    out.append(
                        Finding(
                            rule,
                            Status.FLAG,
                            ctx.loc(report, f"exceptions/{entry[0]}/{entry[1]}"),
                            f"the watchlist lists {entry[2]} for employee {entry[0]} plan {entry[1]}, "
                            f"but the contributions do not support it",
                        )
                    )
            for entry in want:
                if entry not in have:
                    out.append(
                        Finding(
                            rule,
                            Status.FLAG,
                            ctx.loc(report, f"exceptions/{entry[0]}/{entry[1]}"),
                            f"employee {entry[0]} plan {entry[1]} breaches {entry[2]} but is not on "
                            f"the exception watchlist",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "the exception watchlist ties the re-derived exceptions"))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one reconciliation file."""
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
    """Analyze every ``.json`` reconciliation file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of reconciliation-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
