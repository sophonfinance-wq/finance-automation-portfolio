"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one status or one quarter either side of
the line. A control that fires a cent early is as wrong as one that never fires,
and only a boundary test can tell the two apart.

The re-derivation and footing cases carry the most weight. A capitalized figure
that re-derives to the cent must pass and a cent off must fail; a quarter that
capitalizes exactly its interest is in bounds and a cent more is not; an ending
balance that equals prior plus current ties and a cent off does not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capitalize_engine.capitalize import capitalized_for_quarter
from capitalize_engine.engine import (
    SEVERITY,
    check_cap_annual_total_foots,
    check_cap_ceased_on_completion,
    check_cap_no_leakage,
    check_cap_rate_consistent,
    check_cap_rederives,
    check_cap_within_interest,
    check_cmp_current_ties_schedule,
    check_cmp_prior_year_ties,
    check_data_ape_nondecreasing,
    check_prj_tb_complete,
    check_rpt_project_count_ties,
    check_rpt_total_capitalized_ties,
)
from capitalize_engine.generate import ENTITIES, baseline
from capitalize_engine.model import (
    DOC_INTEREST_BY_YEAR,
    DOC_PROJECT_DATA,
    DOC_TRIAL_BALANCE,
    STATUS_COMPLETE,
    Context,
    Status,
)

BR = "J-4101"  # Brightwater Commons, the project every boundary case works on


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(ENTITIES[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _data_row(payload: dict, job_no: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_PROJECT_DATA)["projects"] if r["job_no"] == job_no
    )


def _data_quarter(payload: dict, job_no: str, quarter_end: str) -> dict:
    return next(
        q for q in _data_row(payload, job_no)["quarters"] if q["quarter_end"] == quarter_end
    )


def _interest_row(payload: dict, job_no: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_INTEREST_BY_YEAR)["projects"] if r["job_no"] == job_no
    )


def _interest_quarter(payload: dict, job_no: str, quarter_end: str) -> dict:
    return next(
        q for q in _interest_row(payload, job_no)["quarters"] if q["quarter_end"] == quarter_end
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# cap_within_interest -- capitalize at most the interest incurred, not a cent more
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_within_interest_at_the_cent(delta: int, should_fail: bool) -> None:
    """A quarter capitalizing exactly its interest is in bounds; a cent over is not."""
    payload = _payload()
    quarter = _interest_quarter(payload, BR, "2029-03-31")
    quarter["interest_expense_cents"] = quarter["capitalized_cents"] + delta
    assert bool(_fired(check_cap_within_interest(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cap_rederives -- the capitalized figure re-derives to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    ape = _data_quarter(payload, BR, "2029-03-31")[
        "accumulated_production_expenditures_cents"
    ]
    rate = _data_row(payload, BR)["capitalization_rate_bps"]
    expected = capitalized_for_quarter(ape, rate)
    _interest_quarter(payload, BR, "2029-03-31")["capitalized_cents"] = expected + delta
    assert bool(_fired(check_cap_rederives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cap_no_leakage -- the split closes exactly to the interest incurred
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_no_leakage_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    quarter = _interest_quarter(payload, BR, "2029-06-30")
    quarter["deducted_cents"] = quarter["deducted_cents"] + delta
    assert bool(_fired(check_cap_no_leakage(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cap_annual_total_foots -- the annual column foots its quarters to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_annual_capitalized_foots_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _interest_row(payload, BR)
    footed = sum(q["capitalized_cents"] for q in row["quarters"])
    row["annual_capitalized_cents"] = footed + delta
    assert bool(_fired(check_cap_annual_total_foots(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cmp_current_ties_schedule -- the comparison current ties the schedule annual
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_comparison_current_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    annual = _interest_row(payload, BR)["annual_capitalized_cents"]
    row = next(
        r for r in _doc(payload, "comparison")["projects"] if r["job_no"] == BR
    )
    row["current_year_capitalized_cents"] = annual + delta
    assert bool(_fired(check_cmp_current_ties_schedule(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cmp_prior_year_ties -- ending equals prior plus current, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_prior_year_rolls_forward_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = next(
        r for r in _doc(payload, "comparison")["projects"] if r["job_no"] == BR
    )
    row["ending_capitalized_cents"] = (
        row["prior_year_capitalized_cents"] + row["current_year_capitalized_cents"] + delta
    )
    assert bool(_fired(check_cmp_prior_year_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# data_ape_nondecreasing -- equal is allowed, a cent lower is a break
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (-1, True)])
def test_accumulated_expenditures_may_hold_but_not_fall(delta: int, should_fail: bool) -> None:
    """A quarter equal to the one before it holds; a cent below it breaks the roll."""
    payload = _payload()
    prior = _data_quarter(payload, BR, "2029-06-30")[
        "accumulated_production_expenditures_cents"
    ]
    _data_quarter(payload, BR, "2029-09-30")[
        "accumulated_production_expenditures_cents"
    ] = prior + delta
    assert bool(_fired(check_data_ape_nondecreasing(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rpt_ -- the rollups recompute from the schedule, not the other way round
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_total_capitalized_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    doc = _doc(payload, DOC_INTEREST_BY_YEAR)
    footed = sum(r["annual_capitalized_cents"] for r in doc["projects"])
    doc["total_capitalized_cents"] = footed + delta
    assert bool(_fired(check_rpt_total_capitalized_ties(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_project_count_ties_the_roster(delta: int, should_fail: bool) -> None:
    payload = _payload()
    doc = _doc(payload, DOC_INTEREST_BY_YEAR)
    doc["project_count"] = doc["project_count"] + delta
    assert bool(_fired(check_rpt_project_count_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cap_ceased_on_completion -- a placed-in-service project still capitalizing flags
# --------------------------------------------------------------------------- #
def test_completion_flag_is_a_review_not_a_failure() -> None:
    payload = _payload()
    assert not _fired(check_cap_ceased_on_completion(_ctx(payload)))
    status_row = next(
        r for r in _doc(payload, "project_status")["projects"] if r["job_no"] == BR
    )
    status_row["status"] = STATUS_COMPLETE
    fired = _fired(check_cap_ceased_on_completion(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# cap_rate_consistent -- one applicable rate across the period
# --------------------------------------------------------------------------- #
def test_rate_must_be_consistent_across_projects() -> None:
    payload = _payload()
    assert not _fired(check_cap_rate_consistent(_ctx(payload)))
    _data_row(payload, "J-4102")["capitalization_rate_bps"] = 120
    assert _fired(check_cap_rate_consistent(_ctx(payload)))


# --------------------------------------------------------------------------- #
# prj_tb_complete -- every trial-balance project reaches the schedule
# --------------------------------------------------------------------------- #
def test_trial_balance_project_must_reach_the_schedule() -> None:
    payload = _payload()
    assert not _fired(check_prj_tb_complete(_ctx(payload)))
    _doc(payload, DOC_TRIAL_BALANCE)["projects"].append(
        {"company_no": "300", "job_no": "J-9001"}
    )
    assert _fired(check_prj_tb_complete(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "prj_unique_keys": Status.FAIL,
    "prj_name_present": Status.FAIL,
    "prj_status_valid": Status.FAIL,
    "prj_tb_complete": Status.FAIL,
    "data_project_coverage": Status.FAIL,
    "data_ape_nonneg": Status.FAIL,
    "data_ape_nondecreasing": Status.FAIL,
    "data_rate_valid": Status.FAIL,
    "cap_rate_consistent": Status.FAIL,
    "cap_rederives": Status.FAIL,
    "cap_no_leakage": Status.FAIL,
    "cap_within_interest": Status.FAIL,
    "cap_annual_total_foots": Status.FAIL,
    "cap_ceased_on_completion": Status.FLAG,
    "cmp_current_ties_schedule": Status.FAIL,
    "cmp_prior_year_ties": Status.FAIL,
    "rpt_total_capitalized_ties": Status.FAIL,
    "rpt_project_count_ties": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "prj", "data", "cap", "cmp", "rpt"}
