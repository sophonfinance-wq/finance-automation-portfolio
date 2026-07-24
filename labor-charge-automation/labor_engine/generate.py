"""
Fictional labor-charge corpus generator.
========================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The contractor entities, the employees, the projects,
the cost codes, the burdened costs and every authorization are fictional, and the
charge cycle is set in a fictional future. No real entity, person, project or path
appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the employees, the projects and the authorizations are stated as base facts.
Every figure the engine later checks as a tie-out -- each authorization's resolved
monthly charge, the monthly charge lines, the invoice totals they foot into, the
cumulative charge against budget, and the two general-ledger control totals -- is
recomputed by :func:`rederive` from those base facts, using the *same* truncating
rate primitive the engine re-derives with. So the relationships the engine tests are
the relationships that produced the data: a defect that changes a base fact
re-derives everything downstream and keeps the break confined to one control; a
defect that targets a stated tie-out edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import (
    DOC_CHARGE_AUTHORIZATION,
    DOC_EMPLOYEE_REGISTER,
    DOC_GL_POSITIONS,
    DOC_LABOR_CHARGE_LEDGER,
    DOC_MONTHLY_INVOICE,
    DOC_PROJECT_REGISTER,
    METHOD_FIXED,
    METHOD_PERCENT,
)
from .money import apply_rate

#: Fictional contractor entities, rotated for file identity only.
PROGRAMMES: tuple[str, ...] = (
    "Northmoor Construction Partners",
    "Halbrook Builders Group",
    "Stonecrest Development Co",
    "Ardenne Contracting",
)

PERIOD_LABEL = "CY2030-Q1"
#: The review date the charge run is measured to.
AS_OF = "2030-04-01"
#: The months the run charges over, in order.
CHARGE_PERIODS: tuple[str, ...] = ("2030-01", "2030-02", "2030-03")


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(id, name, monthly_burdened_cost_cents)``. Fully-burdened = salary + taxes +
#: benefits. Only the two employees on a percentage authorization have their burden
#: read by a tie-out; the third is charged on a fixed amount.
EMPLOYEES: tuple[tuple[Any, ...], ...] = (
    ("EMP-001", "Corwin Ashfield", d(12_000)),
    ("EMP-002", "Delphine Marrow", d(9_000)),
    ("EMP-003", "Ravel Thornbury", d(15_000)),
)

#: ``(code, name, cost_codes, labor_budget_cents, labor_budget_warn_bps)``. The
#: warning band is the project's own parameter, so the tolerant control reads it
#: rather than inventing one. DP-400 carries no authorizations -- a project on the
#: books that has not been charged this cycle.
PROJECTS: tuple[tuple[Any, ...], ...] = (
    ("BW-100", "Brightwater Commons", ("01-100", "01-200"), d(100_000), 9000),
    ("CF-200", "Copperfield Yards", ("02-100", "02-300"), d(80_000), 9000),
    ("AP-300", "Alderpoint Terraces", ("03-100",), d(60_000), 9000),
    ("DP-400", "Dunmore Flats", ("04-100",), d(50_000), 9000),
)

#: ``(authorization_id, employee_id, project_code, authorized_start, notice_date,
#:   cost_code, method, fixed_amount_cents, percent_bps, budget_confirmed)``. Notice
#: precedes each start; every cost code exists on its project; budget is confirmed.
AUTHORIZATIONS: tuple[tuple[Any, ...], ...] = (
    ("AUTH-1", "EMP-001", "BW-100", "2029-12-15", "2029-12-01", "01-100", METHOD_FIXED, d(12_000), 0, True),
    ("AUTH-2", "EMP-002", "BW-100", "2029-12-20", "2029-12-05", "01-200", METHOD_PERCENT, 0, 5000, True),
    ("AUTH-3", "EMP-003", "CF-200", "2029-12-10", "2029-11-25", "02-100", METHOD_FIXED, d(10_000), 0, True),
    ("AUTH-4", "EMP-001", "AP-300", "2030-02-01", "2030-01-15", "03-100", METHOD_PERCENT, 0, 2500, True),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _employee(payload: dict[str, Any], emp_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_EMPLOYEE_REGISTER)
    assert register is not None
    for row in register["employees"]:
        if row.get("id") == emp_id:
            return row
    raise KeyError(emp_id)


def _project(payload: dict[str, Any], code: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PROJECT_REGISTER)
    assert register is not None
    for row in register["projects"]:
        if row.get("code") == code:
            return row
    raise KeyError(code)


def _auth(payload: dict[str, Any], auth_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_CHARGE_AUTHORIZATION)
    assert register is not None
    for row in register["authorizations"]:
        if row.get("authorization_id") == auth_id:
            return row
    raise KeyError(auth_id)


def _charge(payload: dict[str, Any], emp: str, code: str, period: str) -> dict[str, Any]:
    ledger = _doc(payload, DOC_LABOR_CHARGE_LEDGER)
    assert ledger is not None
    for row in ledger["charges"]:
        if (
            row.get("employee_id") == emp
            and row.get("project_code") == code
            and row.get("period") == period
        ):
            return row
    raise KeyError((emp, code, period))


def _invoice(payload: dict[str, Any], code: str, period: str) -> dict[str, Any]:
    invoice_doc = _doc(payload, DOC_MONTHLY_INVOICE)
    assert invoice_doc is not None
    for row in invoice_doc["invoices"]:
        if row.get("project_code") == code and row.get("period") == period:
            return row
    raise KeyError((code, period))


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def resolved_monthly_charge(auth: dict[str, Any], burden_by_emp: dict[str, int]) -> int:
    """The monthly charge an authorization resolves to, from its own base facts.

    Mirrors :func:`labor_engine.engine.resolved_charge` exactly, so the derived
    baseline ties the control to the cent.
    """
    if auth["method"] == METHOD_PERCENT:
        burden = burden_by_emp.get(auth["employee_id"], 0)
        return apply_rate(burden, auth["percent_bps"])
    return auth["fixed_amount_cents"]


def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    employee_doc = _doc(payload, DOC_EMPLOYEE_REGISTER)
    project_doc = _doc(payload, DOC_PROJECT_REGISTER)
    auth_doc = _doc(payload, DOC_CHARGE_AUTHORIZATION)
    ledger = _doc(payload, DOC_LABOR_CHARGE_LEDGER)
    invoice_doc = _doc(payload, DOC_MONTHLY_INVOICE)
    gl = _doc(payload, DOC_GL_POSITIONS)
    if not all((employee_doc, project_doc, auth_doc, ledger, invoice_doc, gl)):
        return
    assert employee_doc and project_doc and auth_doc and ledger and invoice_doc and gl

    burden_by_emp = {
        e["id"]: e["monthly_burdened_cost_cents"] for e in employee_doc["employees"]
    }

    # Each authorization resolves to a monthly charge from its own method.
    for auth in auth_doc["authorizations"]:
        auth["monthly_charge_cents"] = resolved_monthly_charge(auth, burden_by_emp)

    # Charge ledger: one line per authorization per period on or after its start.
    ledger["charges"] = []
    for auth in auth_doc["authorizations"]:
        start_month = auth["authorized_start"][:7]
        monthly = auth["monthly_charge_cents"]
        for period in CHARGE_PERIODS:
            if period >= start_month:
                ledger["charges"].append(
                    {
                        "employee_id": auth["employee_id"],
                        "project_code": auth["project_code"],
                        "period": period,
                        "cost_code": auth["cost_code"],
                        "amount_cents": monthly,
                    }
                )

    # Monthly invoice: each project-period's charges foot into one total.
    totals: dict[tuple[str, str], int] = {}
    for row in ledger["charges"]:
        key = (row["project_code"], row["period"])
        totals[key] = totals.get(key, 0) + row["amount_cents"]
    invoice_doc["invoices"] = [
        {"project_code": code, "period": period, "total_cents": totals[(code, period)]}
        for code, period in sorted(totals)
    ]

    # General-ledger positions: the labor-charge total and the invoice control total.
    gl["total_labor_charge_cents"] = sum(r["amount_cents"] for r in ledger["charges"])
    gl["invoice_control_total_cents"] = sum(
        r["total_cents"] for r in invoice_doc["invoices"]
    )


def baseline(entity: str) -> dict[str, Any]:
    """Build a clean charge-run file for ``entity``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "entity": entity,
        "period_label": PERIOD_LABEL,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_EMPLOYEE_REGISTER,
                "document_id": "EMP-REG-2030",
                "employees": [
                    {
                        "id": emp_id,
                        "name": name,
                        "monthly_burdened_cost_cents": burden,
                    }
                    for emp_id, name, burden in EMPLOYEES
                ],
            },
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PRJ-REG-2030",
                "projects": [
                    {
                        "code": code,
                        "name": name,
                        "cost_codes": list(cost_codes),
                        "labor_budget_cents": budget,
                        "labor_budget_warn_bps": warn,
                    }
                    for code, name, cost_codes, budget, warn in PROJECTS
                ],
            },
            {
                "doc_type": DOC_CHARGE_AUTHORIZATION,
                "document_id": "AUTH-REG-2030",
                "authorizations": [
                    {
                        "authorization_id": auth_id,
                        "employee_id": emp_id,
                        "project_code": code,
                        "authorized_start": start,
                        "notice_date": notice,
                        "cost_code": cost_code,
                        "method": method,
                        "fixed_amount_cents": fixed_amount,
                        "percent_bps": percent_bps,
                        "budget_confirmed": confirmed,
                        "monthly_charge_cents": 0,
                    }
                    for (
                        auth_id, emp_id, code, start, notice, cost_code, method,
                        fixed_amount, percent_bps, confirmed,
                    ) in AUTHORIZATIONS
                ],
            },
            {
                "doc_type": DOC_LABOR_CHARGE_LEDGER,
                "document_id": "LEDGER-2030",
                "charges": [],
            },
            {
                "doc_type": DOC_MONTHLY_INVOICE,
                "document_id": "INVOICE-2030",
                "invoices": [],
            },
            {
                "doc_type": DOC_GL_POSITIONS,
                "document_id": "GL-2030",
                "total_labor_charge_cents": 0,
                "invoice_control_total_cents": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control
# --------------------------------------------------------------------------- #
def _missing_artifact(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_GL_POSITIONS
    ]


def _emp_missing_name(payload: dict[str, Any]) -> None:
    del _employee(payload, "EMP-001")["name"]


def _emp_duplicate_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_EMPLOYEE_REGISTER)
    assert register is not None
    register["employees"].append(dict(_employee(payload, "EMP-002")))


def _emp_burden_nonpositive(payload: dict[str, Any]) -> None:
    # EMP-003 is charged on a fixed amount, so zeroing its burden breaks only the
    # positive-burden control, not the derivation of any percentage charge.
    _employee(payload, "EMP-003")["monthly_burdened_cost_cents"] = 0


def _prj_missing_name(payload: dict[str, Any]) -> None:
    del _project(payload, "BW-100")["name"]


def _prj_duplicate_code(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_PROJECT_REGISTER)
    assert register is not None
    register["projects"].append(dict(_project(payload, "CF-200")))


def _prj_budget_nonpositive(payload: dict[str, Any]) -> None:
    # DP-400 carries no charges, so a zero budget trips only the positive-budget
    # control and leaves every cumulative-charge test untouched.
    _project(payload, "DP-400")["labor_budget_cents"] = 0


def _auth_missing_field(payload: dict[str, Any]) -> None:
    # notice_date is required; the advance-notice control skips a row without it,
    # so the break is confined to the required-fields control.
    del _auth(payload, "AUTH-1")["notice_date"]


def _auth_unknown_employee(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CHARGE_AUTHORIZATION)
    assert register is not None
    register["authorizations"].append(
        {
            "authorization_id": "AUTH-X1",
            "employee_id": "EMP-999",
            "project_code": "BW-100",
            "authorized_start": "2030-01-05",
            "notice_date": "2029-12-20",
            "cost_code": "01-100",
            "method": METHOD_FIXED,
            "fixed_amount_cents": d(5_000),
            "percent_bps": 0,
            "budget_confirmed": True,
            "monthly_charge_cents": d(5_000),
        }
    )


def _auth_unknown_project(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CHARGE_AUTHORIZATION)
    assert register is not None
    register["authorizations"].append(
        {
            "authorization_id": "AUTH-X2",
            "employee_id": "EMP-001",
            "project_code": "ZZ-999",
            "authorized_start": "2030-01-05",
            "notice_date": "2029-12-20",
            "cost_code": "01-100",
            "method": METHOD_FIXED,
            "fixed_amount_cents": d(5_000),
            "percent_bps": 0,
            "budget_confirmed": True,
            "monthly_charge_cents": d(5_000),
        }
    )


def _auth_notice_after_start(payload: dict[str, Any]) -> None:
    # Notice a day after the start: authorized in arrears, not in advance.
    _auth(payload, "AUTH-1")["notice_date"] = "2029-12-16"


def _auth_cost_code_off_project(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CHARGE_AUTHORIZATION)
    assert register is not None
    register["authorizations"].append(
        {
            "authorization_id": "AUTH-X3",
            "employee_id": "EMP-002",
            "project_code": "AP-300",
            "authorized_start": "2030-01-05",
            "notice_date": "2029-12-20",
            "cost_code": "99-999",
            "method": METHOD_FIXED,
            "fixed_amount_cents": d(5_000),
            "percent_bps": 0,
            "budget_confirmed": True,
            "monthly_charge_cents": d(5_000),
        }
    )


def _auth_budget_unconfirmed(payload: dict[str, Any]) -> None:
    _auth(payload, "AUTH-2")["budget_confirmed"] = False


def _auth_bad_method(payload: dict[str, Any]) -> None:
    # An unknown method; the derivation control steps aside for it by design.
    _auth(payload, "AUTH-3")["method"] = "hourly"


def _auth_charge_mis_derived(payload: dict[str, Any]) -> None:
    # The percentage is re-keyed but the resolved monthly charge is left as it was;
    # it no longer re-derives from the burdened cost, while the charges (which match
    # the resolved figure) still foot.
    _auth(payload, "AUTH-2")["percent_bps"] = 6000


def _chg_unauthorized_pair(payload: dict[str, Any]) -> None:
    # One charge is relabelled to an employee the project never authorized; the
    # amount is unchanged, so every tie-out still foots.
    _charge(payload, "EMP-001", "BW-100", "2030-01")["employee_id"] = "EMP-003"


def _chg_before_start(payload: dict[str, Any]) -> None:
    # The authorized start slips two months after charging already began; the
    # January charge is now dated before it.
    _auth(payload, "AUTH-1")["authorized_start"] = "2030-02-15"


def _chg_amount_mismatch(payload: dict[str, Any]) -> None:
    # The authorization is restated to $11,000/mo (and re-derives cleanly), but the
    # ledger still charges the old $10,000 -- the charge no longer matches its auth.
    auth = _auth(payload, "AUTH-3")
    auth["fixed_amount_cents"] = d(11_000)
    auth["monthly_charge_cents"] = d(11_000)


def _chg_cost_code_mismatch(payload: dict[str, Any]) -> None:
    # A charge posts to a different (still valid) cost code than the one authorized.
    _charge(payload, "EMP-001", "BW-100", "2030-01")["cost_code"] = "01-200"


def _chg_bad_period(payload: dict[str, Any]) -> None:
    _charge(payload, "EMP-003", "CF-200", "2030-02")["period"] = "2030-13"


def _bud_over_budget(payload: dict[str, Any]) -> None:
    # The budget is cut below what has already been charged.
    _project(payload, "BW-100")["labor_budget_cents"] = d(40_000)


def _bud_near_warn(payload: dict[str, Any]) -> None:
    # The budget is cut so the cumulative charge sits exactly at the warning band
    # (90% of 55,000 is 49,500, and BW-100 has been charged 49,500), still inside it.
    _project(payload, "BW-100")["labor_budget_cents"] = d(55_000)


def _inv_total_off(payload: dict[str, Any]) -> None:
    _invoice(payload, "BW-100", "2030-01")["total_cents"] += d(25)


def _inv_orphan(payload: dict[str, Any]) -> None:
    # An invoice for a project-period that carries no charges at all.
    invoice_doc = _doc(payload, DOC_MONTHLY_INVOICE)
    assert invoice_doc is not None
    invoice_doc["invoices"].append(
        {"project_code": "DP-400", "period": "2030-01", "total_cents": 0}
    )


def _gl_charge_untied(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_GL_POSITIONS)["total_labor_charge_cents"] += d(10)


def _gl_invoice_untied(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_GL_POSITIONS)["invoice_control_total_cents"] += d(10)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _charge(payload, "EMP-001", "BW-100", "2030-01")
    row["amount_cents"] = float(row["amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "emp_missing_name": ("emp_required_fields", _emp_missing_name),
    "emp_duplicate_id": ("emp_id_unique", _emp_duplicate_id),
    "emp_burden_nonpositive": ("emp_burdened_cost_positive", _emp_burden_nonpositive),
    "prj_missing_name": ("prj_required_fields", _prj_missing_name),
    "prj_duplicate_code": ("prj_code_unique", _prj_duplicate_code),
    "prj_budget_nonpositive": ("prj_budget_positive", _prj_budget_nonpositive),
    "auth_missing_field": ("auth_required_fields", _auth_missing_field),
    "auth_unknown_employee": ("auth_employee_exists", _auth_unknown_employee),
    "auth_unknown_project": ("auth_project_exists", _auth_unknown_project),
    "auth_notice_after_start": ("auth_notice_before_start", _auth_notice_after_start),
    "auth_cost_code_off_project": ("auth_cost_code_on_project", _auth_cost_code_off_project),
    "auth_budget_unconfirmed": ("auth_budget_confirmed", _auth_budget_unconfirmed),
    "auth_bad_method": ("auth_method_valid", _auth_bad_method),
    "auth_charge_mis_derived": ("auth_charge_derives", _auth_charge_mis_derived),
    "chg_unauthorized_pair": ("chg_authorized", _chg_unauthorized_pair),
    "chg_before_start": ("chg_not_before_start", _chg_before_start),
    "chg_amount_mismatch": ("chg_amount_matches_auth", _chg_amount_mismatch),
    "chg_cost_code_mismatch": ("chg_cost_code_matches_auth", _chg_cost_code_mismatch),
    "chg_bad_period": ("chg_period_valid", _chg_bad_period),
    "bud_over_budget": ("bud_within_budget", _bud_over_budget),
    "bud_near_warn": ("bud_near_budget", _bud_near_warn),
    "inv_total_off": ("inv_total_ties_charges", _inv_total_off),
    "inv_orphan": ("inv_matches_charge_periods", _inv_orphan),
    "gl_charge_untied": ("gl_total_ties_ledger", _gl_charge_untied),
    "gl_invoice_untied": ("gl_invoice_total_ties", _gl_invoice_untied),
    "amount_not_integer": ("chg_amount_matches_auth", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PROGRAMMES[0])
    clean["file_id"] = f"clean__{PROGRAMMES[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        entity = PROGRAMMES[(i + 1) % len(PROGRAMMES)]
        f = baseline(entity)
        f["file_id"] = f"{name}__{entity.replace(' ', '_')}"
        f["planted_defect"] = name
        mutate(f)
        files.append(f)

    for f in files:
        path = folder / f"{f['file_id']}.json"
        path.write_text(
            json.dumps(f, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
