"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The charge, budget and derivation cases carry the most weight. A charge that foots
into its invoice can still be a cent adrift of the authorization that permits it; a
cumulative charge a cent under the warning band must not flag, and a cent over it
must.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labor_engine.engine import (
    SEVERITY,
    check_auth_charge_derives,
    check_auth_cost_code_on_project,
    check_auth_notice_before_start,
    check_bud_near_budget,
    check_bud_within_budget,
    check_chg_amount_matches_auth,
    check_chg_authorized,
    check_chg_not_before_start,
    check_gl_total_ties_ledger,
    check_inv_total_ties_charges,
)
from labor_engine.generate import PROGRAMMES, baseline
from labor_engine.model import (
    DOC_CHARGE_AUTHORIZATION,
    DOC_EMPLOYEE_REGISTER,
    DOC_GL_POSITIONS,
    DOC_LABOR_CHARGE_LEDGER,
    DOC_MONTHLY_INVOICE,
    DOC_PROJECT_REGISTER,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PROGRAMMES[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _project(payload: dict, code: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PROJECT_REGISTER)["projects"] if p["code"] == code
    )


def _auth(payload: dict, auth_id: str) -> dict:
    return next(
        a for a in _doc(payload, DOC_CHARGE_AUTHORIZATION)["authorizations"]
        if a["authorization_id"] == auth_id
    )


def _charge(payload: dict, emp: str, code: str, period: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_LABOR_CHARGE_LEDGER)["charges"]
        if r["employee_id"] == emp and r["project_code"] == code and r["period"] == period
    )


def _invoice(payload: dict, code: str, period: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_MONTHLY_INVOICE)["invoices"]
        if r["project_code"] == code and r["period"] == period
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# auth_notice_before_start -- notice on or before the start, to the day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "notice, should_fail",
    [("2029-12-14", False), ("2029-12-15", False), ("2029-12-16", True)],
)
def test_notice_must_not_fall_after_the_start(notice: str, should_fail: bool) -> None:
    """AUTH-1 starts 2029-12-15; notice the day after is authorized in arrears."""
    payload = _payload()
    _auth(payload, "AUTH-1")["notice_date"] = notice
    assert bool(_fired(check_auth_notice_before_start(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# chg_not_before_start -- no charge in a month before the authorized start
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "start, should_fail",
    [("2030-01-01", False), ("2030-01-31", False), ("2030-02-01", True)],
)
def test_a_charge_may_not_predate_the_start_month(start: str, should_fail: bool) -> None:
    """AUTH-1 has a 2030-01 charge; a start anywhere in January still allows it,
    a February start does not."""
    payload = _payload()
    _auth(payload, "AUTH-1")["authorized_start"] = start
    assert bool(_fired(check_chg_not_before_start(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# auth_charge_derives -- the percentage resolves to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_percentage_charge_re_derives_to_the_cent(delta: int, should_fail: bool) -> None:
    """AUTH-2 is 50.00% of a $9,000 burden -> $4,500; a cent either side fails."""
    payload = _payload()
    _auth(payload, "AUTH-2")["monthly_charge_cents"] += delta
    assert bool(_fired(check_auth_charge_derives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# chg_amount_matches_auth -- the charge equals the resolved monthly charge
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_charge_matches_its_authorization_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _charge(payload, "EMP-002", "BW-100", "2030-01")["amount_cents"] += delta
    assert bool(_fired(check_chg_amount_matches_auth(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# bud_within_budget -- at the budget passes, a cent over fails
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_cumulative_charge_at_the_budget_is_allowed(delta: int, should_fail: bool) -> None:
    """BW-100 has been charged 49,500.00; a budget set to that exact figure holds,
    a cent below it is an overrun."""
    payload = _payload()
    charged = 4_950_000  # 3 x 1,200,000 + 3 x 450,000
    _project(payload, "BW-100")["labor_budget_cents"] = charged + delta
    assert bool(_fired(check_bud_within_budget(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# bud_near_budget -- at the warning band flags, a cent under does not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_flag", [(-1, False), (0, True)])
def test_cumulative_charge_at_the_warning_band_flags(delta: int, should_flag: bool) -> None:
    """With a 55,000.00 budget and a 90% band the threshold is 49,500.00; the
    cumulative charge at the threshold flags, a cent under it stays silent."""
    payload = _payload()
    _project(payload, "BW-100")["labor_budget_cents"] = 5_500_000  # threshold 4,950,000
    _charge(payload, "EMP-001", "BW-100", "2030-01")["amount_cents"] += delta
    fired = _fired(check_bud_near_budget(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# inv_total_ties_charges -- the invoice foots to the charges, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_invoice_foots_to_its_charges_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _invoice(payload, "BW-100", "2030-01")["total_cents"] += delta
    assert bool(_fired(check_inv_total_ties_charges(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# gl_total_ties_ledger -- the ledger total re-sums the charges, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_gl_total_re_sums_the_charges_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_GL_POSITIONS)["total_labor_charge_cents"] += delta
    assert bool(_fired(check_gl_total_ties_ledger(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# chg_authorized / auth_cost_code_on_project -- membership, not arithmetic
# --------------------------------------------------------------------------- #
def test_a_charge_to_an_unauthorized_pair_fails() -> None:
    """Relabelling a charge to an employee the project never authorized fails,
    without disturbing any total."""
    payload = _payload()
    assert not _fired(check_chg_authorized(_ctx(payload)))
    _charge(payload, "EMP-001", "BW-100", "2030-01")["employee_id"] = "EMP-003"
    assert _fired(check_chg_authorized(_ctx(payload)))


def test_a_cost_code_off_the_project_fails() -> None:
    payload = _payload()
    assert not _fired(check_auth_cost_code_on_project(_ctx(payload)))
    _auth(payload, "AUTH-1")["cost_code"] = "77-777"
    assert _fired(check_auth_cost_code_on_project(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "emp_required_fields": Status.FAIL,
    "emp_id_unique": Status.FAIL,
    "emp_burdened_cost_positive": Status.FAIL,
    "prj_required_fields": Status.FAIL,
    "prj_code_unique": Status.FAIL,
    "prj_budget_positive": Status.FAIL,
    "auth_required_fields": Status.FAIL,
    "auth_employee_exists": Status.FAIL,
    "auth_project_exists": Status.FAIL,
    "auth_notice_before_start": Status.FAIL,
    "auth_cost_code_on_project": Status.FAIL,
    "auth_budget_confirmed": Status.FAIL,
    "auth_method_valid": Status.FAIL,
    "auth_charge_derives": Status.FAIL,
    "chg_authorized": Status.FAIL,
    "chg_not_before_start": Status.FAIL,
    "chg_amount_matches_auth": Status.FAIL,
    "chg_cost_code_matches_auth": Status.FAIL,
    "chg_period_valid": Status.FAIL,
    "bud_within_budget": Status.FAIL,
    "bud_near_budget": Status.FLAG,
    "inv_total_ties_charges": Status.FAIL,
    "inv_matches_charge_periods": Status.FAIL,
    "gl_total_ties_ledger": Status.FAIL,
    "gl_invoice_total_ties": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {
        "set", "emp", "prj", "auth", "chg", "bud", "inv", "gl"
    }
