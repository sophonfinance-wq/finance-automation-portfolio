"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The allocation and audit cases carry the most weight. A share that foots to the
premium can still put the residual cent on the wrong project; a true-up that sums
to the audit amount can still credit a project that never bore the deposit. Each
of those is two controls, and each boundary is one cent wide.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from insurance_engine.engine import (
    SEVERITY,
    check_alloc_shares_recompute,
    check_alloc_sums_to_premium,
    check_aud_credits_deposit_bearers,
    check_aud_true_up_sums,
    check_aud_uses_deposit_basis,
    check_br_completed_project_removed,
    check_br_term_covers_construction,
    check_br_value_ties_budget,
    check_gl_prepaid_amortisation_ties,
    check_pol_no_coverage_gap,
    check_pol_tower_has_no_gap,
    check_rpt_per_unit_recomputes,
)
from insurance_engine.generate import PROGRAMMES, baseline, prepaid_unearned
from insurance_engine.model import (
    DOC_ALLOCATION_SUMMARY,
    DOC_AUDIT_REGISTER,
    DOC_GL_POSITIONS,
    DOC_POLICY_REGISTER,
    DOC_PROJECT_REGISTER,
    STAGE_COMPLETE,
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


def _policy(payload: dict, policy_no: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_POLICY_REGISTER)["policies"]
        if p["policy_no"] == policy_no
    )


def _project(payload: dict, code: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PROJECT_REGISTER)["projects"] if p["code"] == code
    )


def _alloc(payload: dict, policy_no: str, code: str) -> dict:
    return next(
        r for r in _doc(payload, "allocation_schedule")["allocations"]
        if r["policy_no"] == policy_no and r["project_code"] == code
    )


def _audit(payload: dict, audit_no: str) -> dict:
    return next(
        a for a in _doc(payload, DOC_AUDIT_REGISTER)["audits"]
        if a["audit_no"] == audit_no
    )


def _realloc(payload: dict, audit_no: str, code: str) -> dict:
    return next(
        r for r in _audit(payload, audit_no)["reallocation"]
        if r["project_code"] == code
    )


def _summary(payload: dict, code: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_ALLOCATION_SUMMARY)["projects"]
        if r["project_code"] == code
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# The residual cent -- footing and re-derivation are two different controls
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_each_share_is_re_derived_to_the_cent(delta: int, should_fail: bool) -> None:
    """Moving a cent from one project to another keeps the policy footing.

    So ``alloc_sums_to_premium`` stays silent while ``alloc_shares_recompute`` is
    the only control that can see the misplaced penny.
    """
    payload = _payload()
    _alloc(payload, "GL-2029", "PRJ-101")["allocated_cents"] += delta
    _alloc(payload, "GL-2029", "PRJ-102")["allocated_cents"] -= delta
    assert bool(_fired(check_alloc_shares_recompute(_ctx(payload)))) is should_fail
    # The compensating move keeps the total intact by construction.
    assert not _fired(check_alloc_sums_to_premium(_ctx(payload)))


def test_moving_one_share_alone_breaks_the_footing() -> None:
    """One share changed without a compensating move fails the sum, not just the split."""
    payload = _payload()
    _alloc(payload, "GL-2029", "PRJ-101")["allocated_cents"] -= 500
    assert _fired(check_alloc_sums_to_premium(_ctx(payload)))
    assert _fired(check_alloc_shares_recompute(_ctx(payload)))


# --------------------------------------------------------------------------- #
# pol_tower_has_no_gap -- the excess attaches no higher than the primary limit
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_excess_attaches_no_higher_than_primary_limit(delta: int, should_fail: bool) -> None:
    payload = _payload()
    limit = _policy(payload, "GL-2029")["limit_cents"]
    _policy(payload, "XS-2029")["attachment_point_cents"] = limit + delta
    assert bool(_fired(check_pol_tower_has_no_gap(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# pol_no_coverage_gap -- the renewal must not leave an uninsured day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "inception, should_fail",
    [("2029-07-01", False), ("2029-06-30", False), ("2029-07-02", True)],
)
def test_renewal_leaves_no_uninsured_day(inception: str, should_fail: bool) -> None:
    """The prior GL term expires 2029-07-01; a renewal bound a day later leaves a gap.

    Binding it early is an overlap, which the continuity control tolerates -- only
    a genuine gap, where an occurrence would land with nothing to respond, fails.
    """
    payload = _payload()
    _policy(payload, "GL-2029")["inception_date"] = inception
    assert bool(_fired(check_pol_no_coverage_gap(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# br_value_ties_budget -- the band comes from the policy, not the engine
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("extra, should_flag", [(0, False), (1, True)])
def test_builders_risk_value_band_is_the_policys_own(extra: int, should_flag: bool) -> None:
    payload = _payload()
    project = _project(payload, "PRJ-101")
    budget = project["hard_cost_cents"]
    allowed = budget * _policy(payload, "BR-2029")["value_tolerance_bps"] // 10000
    project["insured_value_cents"] = budget + allowed + extra
    fired = _fired(check_br_value_ties_budget(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# br_term_covers_construction -- the term brackets the build, to the day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("end, should_fail", [("2030-07-01", False), ("2030-07-02", True)])
def test_builders_risk_term_brackets_construction(end: str, should_fail: bool) -> None:
    """The BR term expires 2030-07-01; construction ending a day later is uninsured."""
    payload = _payload()
    _project(payload, "PRJ-101")["construction_end"] = end
    assert bool(_fired(check_br_term_covers_construction(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# br_completed_project_removed -- a finished project leaves the schedule
# --------------------------------------------------------------------------- #
def test_a_completed_project_must_leave_the_builders_risk_schedule() -> None:
    payload = _payload()
    assert not _fired(check_br_completed_project_removed(_ctx(payload)))
    _project(payload, "PRJ-101")["stage"] = STAGE_COMPLETE
    assert _fired(check_br_completed_project_removed(_ctx(payload)))


# --------------------------------------------------------------------------- #
# aud_ -- the true-up returns to the projects that paid, on the basis they paid
# --------------------------------------------------------------------------- #
def test_true_up_must_return_to_the_deposit_bearers() -> None:
    """Crediting a project the policy never allocated to is wrong in both directions."""
    payload = _payload()
    _audit(payload, "AUD-2028")["reallocation"].append(
        {
            "project_code": "PRJ-777",
            "credit_cents": 0,
            "deposit_basis_cents": 0,
            "final_basis_cents": 0,
        }
    )
    assert _fired(check_aud_credits_deposit_bearers(_ctx(payload)))


def test_matching_bearers_passes() -> None:
    payload = _payload()
    assert not _fired(check_aud_credits_deposit_bearers(_ctx(payload)))


def test_true_up_splits_on_the_deposit_basis_to_the_cent() -> None:
    """Moving a credit between two bearers keeps the sum and breaks the derivation."""
    payload = _payload()
    _realloc(payload, "AUD-2028", "PRJ-101")["credit_cents"] -= 50
    _realloc(payload, "AUD-2028", "PRJ-102")["credit_cents"] += 50
    assert _fired(check_aud_uses_deposit_basis(_ctx(payload)))
    assert not _fired(check_aud_true_up_sums(_ctx(payload)))


# --------------------------------------------------------------------------- #
# gl_prepaid_amortisation_ties -- unearned premium re-derived from each term
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_prepaid_is_re_derived_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_GL_POSITIONS)["prepaid_insurance_cents"] += delta
    assert bool(_fired(check_gl_prepaid_amortisation_ties(_ctx(payload)))) is should_fail


def test_a_fully_earned_term_carries_no_prepaid() -> None:
    """The prior GL term has fully expired by the review date, so none is unearned."""
    payload = _payload()
    prior = [
        p for p in _doc(payload, DOC_POLICY_REGISTER)["policies"]
        if p["policy_no"] == "GL-2028"
    ]
    assert prepaid_unearned(prior, date(2029, 10, 1)) == 0


def test_a_current_term_carries_a_positive_prepaid() -> None:
    """A term still running at the review date leaves part of its premium unearned."""
    payload = _payload()
    current = [
        p for p in _doc(payload, DOC_POLICY_REGISTER)["policies"]
        if p["policy_no"] == "GL-2029"
    ]
    assert prepaid_unearned(current, date(2029, 10, 1)) > 0


# --------------------------------------------------------------------------- #
# rpt_per_unit_recomputes -- the board-pack figure nobody recalculates
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_flag", [(0, False), (1, True)])
def test_per_unit_recomputes_by_floor(delta: int, should_flag: bool) -> None:
    payload = _payload()
    _summary(payload, "PRJ-101")["per_unit_cents"] += delta
    fired = _fired(check_rpt_per_unit_recomputes(_ctx(payload)))
    assert bool(fired) is should_flag


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "pol_required_fields": Status.FAIL,
    "pol_no_duplicate": Status.FAIL,
    "pol_term_runs_forwards": Status.FAIL,
    "pol_no_coverage_gap": Status.FAIL,
    "pol_tower_has_no_gap": Status.FAIL,
    "alloc_basis_declared": Status.FAIL,
    "alloc_project_exists": Status.FAIL,
    "alloc_only_covered_projects": Status.FAIL,
    "alloc_basis_data_complete": Status.FAIL,
    "alloc_sums_to_premium": Status.FAIL,
    "alloc_shares_recompute": Status.FAIL,
    "alloc_no_negative": Status.FAIL,
    "br_value_ties_budget": Status.FLAG,
    "br_term_covers_construction": Status.FAIL,
    "br_completed_project_removed": Status.FAIL,
    "aud_true_up_sums": Status.FAIL,
    "aud_credits_deposit_bearers": Status.FAIL,
    "aud_uses_deposit_basis": Status.FAIL,
    "aud_basis_restated": Status.FLAG,
    "gl_allocation_ties_job_cost": Status.FAIL,
    "gl_prepaid_amortisation_ties": Status.FAIL,
    "gl_total_ties_programme": Status.FAIL,
    "rpt_per_unit_recomputes": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "pol", "alloc", "br", "aud", "gl", "rpt"}
