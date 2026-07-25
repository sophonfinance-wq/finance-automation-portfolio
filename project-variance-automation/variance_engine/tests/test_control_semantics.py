"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one basis point or one day either side of
the line. A control that fires a cent early is as wrong as one that never fires,
and only a boundary test can tell the two apart.

The variance and milestone cases carry the most weight. A variance column must
equal the difference of the two columns it sits between, to the cent and to the
basis point; Cost to Complete must be the remainder of the budget and nothing
else; and the schedule sign convention -- ``+`` is ahead -- has to hold in both
directions, because a flipped sign turns slippage into progress on the page a
committee reads. The corpus puts a real row on each edge: ``MS-3043`` is behind the
frozen baseline by exactly the file's own tolerance, and ``MS-3023`` and ``MS-3033``
are ahead by exactly the same span in the other direction.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from variance_engine.engine import (
    SEVERITY,
    check_bud_category_valid,
    check_bud_cost_to_complete_foots,
    check_bud_project_exists,
    check_eco_expense_foots_budget,
    check_eco_margin_on_cost_recomputes,
    check_eco_net_revenue_foots,
    check_eco_profit_foots,
    check_mst_baseline_variance_foots,
    check_mst_slippage_lead_time,
    check_mst_variance_sign_convention,
    check_prj_comparatives_present,
    check_prj_type_valid,
    check_rpt_rollup_foots,
    check_rpt_slippage_watchlist_ties,
    check_var_comparative_columns_foot,
    check_var_plan_column_ties,
    check_var_plan_version_frozen,
    check_var_prior_column_ties,
)
from variance_engine.generate import (
    PLAN_VERSION,
    PORTFOLIOS,
    SCHEDULE_VERSION,
    SLIPPAGE_TOLERANCE_DAYS,
    baseline,
)
from variance_engine.model import (
    DOC_BUDGET_VARIANCE,
    DOC_CURRENT_ECONOMICS,
    DOC_MILESTONE_SCHEDULE,
    DOC_PLAN_BASELINE,
    DOC_PRIOR_ECONOMICS,
    DOC_PROJECT_REGISTER,
    DOC_REPORT_ROLLUP,
    DOC_SLIPPAGE_WATCHLIST,
    DOC_VARIANCE_SUMMARY,
    METRIC_GROSS_REVENUE,
    METRIC_MARGIN,
    UNIT_BPS,
    Context,
    Status,
)
from variance_engine.variance import margin_on_cost_bps

#: The milestone the corpus places exactly on the slippage tolerance.
AT_TOLERANCE_MILESTONE = "MS-3043"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _project(payload: dict, project_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_PROJECT_REGISTER)["projects"]
        if r["project_id"] == project_id
    )


def _cost_line(payload: dict, line_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_BUDGET_VARIANCE)["cost_lines"]
        if r["line_id"] == line_id
    )


def _econ(payload: dict, doc_type: str, project_id: str) -> dict:
    return next(
        r for r in _doc(payload, doc_type)["projects"]
        if r["project_id"] == project_id
    )


def _var_row(payload: dict, project_id: str, metric: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_VARIANCE_SUMMARY)["rows"]
        if r["project_id"] == project_id and r["metric"] == metric
    )


def _milestone(payload: dict, milestone_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_MILESTONE_SCHEDULE)["milestones"]
        if r["milestone_id"] == milestone_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# bud_cost_to_complete_foots -- the remainder of the budget, nothing else
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_cost_to_complete_is_the_remainder_to_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _cost_line(payload, "CL-3011")["cost_to_complete_cents"] += delta
    assert bool(_fired(check_bud_cost_to_complete_foots(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_cost_to_complete_follows_a_moved_cost_to_date(
    delta: int, should_fail: bool
) -> None:
    """Spending more without re-striking the remainder is the overrun that hides."""
    payload = _payload()
    _cost_line(payload, "CL-3011")["cost_to_date_cents"] += delta
    assert bool(_fired(check_bud_cost_to_complete_foots(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# eco_ -- the current-period economics re-derive from their own inputs
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_net_revenue_foots_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _econ(payload, DOC_CURRENT_ECONOMICS, "PRJ-301")["net_project_revenue_cents"] += delta
    assert bool(_fired(check_eco_net_revenue_foots(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_profit_foots_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _econ(payload, DOC_CURRENT_ECONOMICS, "PRJ-301")["project_profit_cents"] += delta
    assert bool(_fired(check_eco_profit_foots(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_expense_foots_the_budget_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _econ(payload, DOC_CURRENT_ECONOMICS, "PRJ-301")["total_project_expense_cents"] += delta
    assert bool(_fired(check_eco_expense_foots_budget(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_margin_recomputes_to_the_basis_point(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _econ(payload, DOC_CURRENT_ECONOMICS, "PRJ-301")["margin_on_cost_bps"] += delta
    assert bool(_fired(check_eco_margin_on_cost_recomputes(_ctx(payload)))) is should_fail


def test_margin_on_a_zero_expense_is_not_invented() -> None:
    """There is no cost to strike a margin on, so the control skips the row."""
    payload = _payload()
    _econ(payload, DOC_CURRENT_ECONOMICS, "PRJ-301")["total_project_expense_cents"] = 0
    assert not _fired(check_eco_margin_on_cost_recomputes(_ctx(payload)))


def test_margin_truncates_toward_zero_in_both_directions() -> None:
    """A loss and a profit of the same magnitude round the same way.

    Flooring would make a negative margin one basis point wider than its positive
    mirror, which is a difference no reader could defend.
    """
    expense = 3_000_000
    assert margin_on_cost_bps(1_000_001, expense) == -margin_on_cost_bps(
        -1_000_001, expense
    )


def test_a_stated_margin_that_matches_a_loss_passes() -> None:
    """The control follows the arithmetic, not the sign of the answer.

    The margin is struck on the *stated* net revenue less the stated expense, not
    on the stated profit -- so a loss is modelled by moving the net revenue under
    the expense and letting the margin follow it down.
    """
    payload = _payload()
    row = _econ(payload, DOC_CURRENT_ECONOMICS, "PRJ-301")
    expense = row["total_project_expense_cents"]
    row["net_project_revenue_cents"] = expense - 1_000_000_000
    expected = margin_on_cost_bps(-1_000_000_000, expense)
    row["margin_on_cost_bps"] = expected
    assert expected is not None and expected < 0
    assert not _fired(check_eco_margin_on_cost_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# var_ -- the comparative and variance columns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("doc_type", [DOC_PRIOR_ECONOMICS, DOC_PLAN_BASELINE])
@pytest.mark.parametrize(
    "key",
    ["net_project_revenue_cents", "project_profit_cents", "margin_on_cost_bps"],
)
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_comparative_columns_foot_inside_themselves(
    doc_type: str, key: str, delta: int, should_fail: bool
) -> None:
    """A comparative is only a comparative if it is internally consistent.

    Each of the Prior and Business Plan columns carries its own gross revenue,
    deductions and expense, so its own net revenue, profit and margin have to
    re-derive from them exactly as the current column's do. Otherwise the variance
    is measured against a column that never footed.
    """
    payload = _payload()
    _econ(payload, doc_type, "PRJ-301")[key] += delta
    assert bool(_fired(check_var_comparative_columns_foot(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_prior_variance_is_the_difference_of_the_columns_beside_it(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _var_row(payload, "PRJ-301", METRIC_GROSS_REVENUE)["variance_vs_prior"] += delta
    assert bool(_fired(check_var_prior_column_ties(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_plan_variance_is_the_difference_of_the_columns_beside_it(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _var_row(payload, "PRJ-301", METRIC_GROSS_REVENUE)["variance_vs_plan"] += delta
    assert bool(_fired(check_var_plan_column_ties(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_a_basis_point_variance_foots_like_a_cent_one(
    delta: int, should_fail: bool
) -> None:
    """The margin row is carried in basis points and re-foots by the same rule."""
    payload = _payload()
    row = _var_row(payload, "PRJ-301", METRIC_MARGIN)
    assert row["unit"] == UNIT_BPS
    row["variance_vs_prior"] += delta
    assert bool(_fired(check_var_prior_column_ties(_ctx(payload)))) is should_fail


def test_a_rebased_plan_column_is_reported() -> None:
    """Re-basing the plan makes every plan variance smaller at once."""
    payload = _payload()
    _doc(payload, DOC_VARIANCE_SUMMARY)["basis_plan_version"] = "BP-2029-R1"
    assert _fired(check_var_plan_version_frozen(_ctx(payload)))


def test_a_project_approved_on_another_plan_version_is_reported() -> None:
    payload = _payload()
    _project(payload, "PRJ-302")["plan_version"] = "BP-2029-R1"
    assert _fired(check_var_plan_version_frozen(_ctx(payload)))


def test_the_frozen_plan_version_is_the_one_on_the_baseline_document() -> None:
    payload = _payload()
    assert _doc(payload, DOC_PLAN_BASELINE)["plan_version"] == PLAN_VERSION
    assert not _fired(check_var_plan_version_frozen(_ctx(payload)))


# --------------------------------------------------------------------------- #
# mst_ -- the schedule sign convention and the frozen baseline
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_prior_milestone_variance_foots_to_the_day(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _milestone(payload, "MS-3022")["variance_prior_days"] += delta
    assert bool(_fired(check_mst_variance_sign_convention(_ctx(payload)))) is should_fail


def test_a_flipped_sign_turns_slippage_into_progress() -> None:
    """MS-3022 moved earlier and reports +2. Negated it claims the opposite."""
    payload = _payload()
    row = _milestone(payload, "MS-3022")
    assert row["variance_prior_days"] > 0
    row["variance_prior_days"] = -row["variance_prior_days"]
    fired = _fired(check_mst_variance_sign_convention(_ctx(payload)))
    assert fired
    assert "MS-3022" in fired[0].message


def test_a_date_that_moved_later_reports_negative() -> None:
    """The convention is a definition: later than the comparison is behind."""
    payload = _payload()
    row = _milestone(payload, "MS-3011")
    current = date.fromisoformat(row["prior_date"]) + timedelta(days=7)
    row["current_date"] = current.isoformat()
    row["variance_prior_days"] = -7
    assert not _fired(check_mst_variance_sign_convention(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_baseline_milestone_variance_foots_to_the_day(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _milestone(payload, "MS-3013")["variance_baseline_days"] += delta
    assert bool(_fired(check_mst_baseline_variance_foots(_ctx(payload)))) is should_fail


def test_a_project_measured_against_another_baseline_schedule_is_reported() -> None:
    payload = _payload()
    _project(payload, "PRJ-303")["baseline_schedule_version"] = "SCH-2029-R1"
    fired = _fired(check_mst_baseline_variance_foots(_ctx(payload)))
    assert fired
    assert "PRJ-303" in fired[0].message


def test_the_schedule_block_names_the_frozen_version() -> None:
    payload = _payload()
    assert (
        _doc(payload, DOC_MILESTONE_SCHEDULE)["baseline_schedule_version"]
        == SCHEDULE_VERSION
    )


# --------------------------------------------------------------------------- #
# mst_slippage_lead_time -- the tolerance closes at exactly the stated span
# --------------------------------------------------------------------------- #
def test_no_forthcoming_milestone_is_past_tolerance_on_the_baseline() -> None:
    """MS-3043 is behind by exactly the tolerance, which is *at* it, not past it."""
    payload = _payload()
    row = _milestone(payload, AT_TOLERANCE_MILESTONE)
    assert row["variance_baseline_days"] == -SLIPPAGE_TOLERANCE_DAYS
    assert not _fired(check_mst_slippage_lead_time(_ctx(payload)))


@pytest.mark.parametrize(
    "behind_days, should_flag",
    [
        (SLIPPAGE_TOLERANCE_DAYS, False),
        (SLIPPAGE_TOLERANCE_DAYS + 1, True),
    ],
)
def test_slippage_tolerance_edge(behind_days: int, should_flag: bool) -> None:
    """Behind by exactly the tolerance is not yet on the watchlist."""
    payload = _payload()
    row = _milestone(payload, AT_TOLERANCE_MILESTONE)
    base = date.fromisoformat(row["baseline_date"])
    row["current_date"] = (base + timedelta(days=behind_days)).isoformat()
    fired = _fired(check_mst_slippage_lead_time(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_a_milestone_already_passed_is_history_not_a_chase() -> None:
    """A date behind the report date cannot be chased, so it is not flagged."""
    payload = _payload()
    row = _milestone(payload, "MS-3011")
    base = date.fromisoformat(row["baseline_date"])
    row["current_date"] = (base + timedelta(days=90)).isoformat()
    assert not _fired(check_mst_slippage_lead_time(_ctx(payload)))


def test_a_milestone_ahead_of_baseline_is_never_flagged() -> None:
    payload = _payload()
    row = _milestone(payload, AT_TOLERANCE_MILESTONE)
    base = date.fromisoformat(row["baseline_date"])
    row["current_date"] = (base - timedelta(days=30)).isoformat()
    assert not _fired(check_mst_slippage_lead_time(_ctx(payload)))


# --------------------------------------------------------------------------- #
# register and budget hygiene
# --------------------------------------------------------------------------- #
def test_an_unknown_project_type_is_reported() -> None:
    payload = _payload()
    _project(payload, "PRJ-301")["project_type"] = "industrial_park"
    fired = _fired(check_prj_type_valid(_ctx(payload)))
    assert fired
    assert "industrial_park" in fired[0].message


def test_a_project_missing_a_comparative_is_reported() -> None:
    payload = _payload()
    doc = _doc(payload, DOC_PRIOR_ECONOMICS)
    doc["projects"] = [r for r in doc["projects"] if r["project_id"] != "PRJ-302"]
    fired = _fired(check_prj_comparatives_present(_ctx(payload)))
    assert fired
    assert "PRJ-302" in fired[0].message


def test_an_unknown_cost_category_is_reported() -> None:
    payload = _payload()
    _cost_line(payload, "CL-3011")["cost_category"] = "marketing"
    fired = _fired(check_bud_category_valid(_ctx(payload)))
    assert fired
    assert "marketing" in fired[0].message


def test_a_cost_line_on_no_declared_project_is_reported() -> None:
    payload = _payload()
    _cost_line(payload, "CL-3011")["project_id"] = "PRJ-999"
    fired = _fired(check_bud_project_exists(_ctx(payload)))
    assert fired
    assert "PRJ-999" in fired[0].message


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup foots from the projects, not the other way round
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "key",
    [
        "project_count",
        "total_gross_revenue_cents",
        "total_net_project_revenue_cents",
        "total_project_expense_cents",
        "total_project_profit_cents",
    ],
)
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_rollup_totals_foot_to_the_cent(
    key: str, delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_REPORT_ROLLUP)[key] += delta
    assert bool(_fired(check_rpt_rollup_foots(_ctx(payload)))) is should_fail


def test_slippage_watchlist_must_tie_the_schedule() -> None:
    payload = _payload()
    assert not _fired(check_rpt_slippage_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_SLIPPAGE_WATCHLIST)["entries"].append(
        {
            "milestone_id": "MS-3013",
            "project_id": "PRJ-301",
            "milestone_name": "project_completion",
            "baseline_date": "2031-04-30",
            "current_date": "2031-05-02",
            "variance_baseline_days": -2,
        }
    )
    fired = _fired(check_rpt_slippage_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "prj_unique_ids": Status.FAIL,
    "prj_type_valid": Status.FAIL,
    "prj_comparatives_present": Status.FAIL,
    "bud_line_required_fields": Status.FAIL,
    "bud_category_valid": Status.FAIL,
    "bud_project_exists": Status.FAIL,
    "bud_cost_to_complete_foots": Status.FAIL,
    "eco_net_revenue_foots": Status.FAIL,
    "eco_expense_foots_budget": Status.FAIL,
    "eco_profit_foots": Status.FAIL,
    "eco_margin_on_cost_recomputes": Status.FAIL,
    "var_comparative_columns_foot": Status.FAIL,
    "var_prior_column_ties": Status.FAIL,
    "var_plan_column_ties": Status.FAIL,
    "var_plan_version_frozen": Status.FAIL,
    "mst_required_fields": Status.FAIL,
    "mst_variance_sign_convention": Status.FAIL,
    "mst_baseline_variance_foots": Status.FAIL,
    "mst_slippage_lead_time": Status.FLAG,
    "rpt_rollup_foots": Status.FAIL,
    "rpt_slippage_watchlist_ties": Status.FLAG,
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
        "set", "prj", "bud", "eco", "var", "mst", "rpt"
    }
