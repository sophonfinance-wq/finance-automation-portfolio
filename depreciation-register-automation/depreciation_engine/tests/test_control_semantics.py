"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one month, one cent or one period either side of
the line. A control that fires a cent early is as wrong as one that never fires,
and only a boundary test can tell the two apart.

The schedule kernel's edges carry the most weight. The final month of a schedule
absorbs the rounding remainder so the charges sum back to cost exactly; the
in-service month takes a full charge and the month before it takes none; a
capitalization at the threshold is a capitalization and a cent below it is not;
the first booked month of a late-set-up prepaid takes the catch-up for every
period it sat unbooked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from depreciation_engine.engine import (
    SEVERITY,
    check_cap_threshold_gate,
    check_date_fully_depreciated_zero,
    check_date_not_in_service_yet,
    check_disp_fully_depreciated_watch,
    check_gl_accum_ties,
    check_je_depreciation_ties,
    check_nbv_accum_rederives,
    check_pre_expense_rederives,
    check_pre_window_ending_watch,
    check_roll_accum_identity,
    check_sl_expense_rederives,
    check_sl_monthly_dep_rederives,
)
from depreciation_engine.generate import (
    CLOSE_MONTH,
    DISPOSAL_REVIEW_MONTHS,
    ENTITIES,
    PREPAID_WATCH_MONTHS,
    THRESHOLD_CENTS,
    baseline,
    rederive,
    rederive_asset_row,
)
from depreciation_engine.model import (
    DOC_ASSET_REGISTER,
    DOC_CAP_POLICY,
    DOC_GL_BALANCES,
    DOC_PREPAID_REGISTER,
    DOC_RECURRING_JE,
    DOC_ROLLFORWARD,
    GL_ACCUM,
    JE_DEPRECIATION,
    Context,
    Status,
)
from depreciation_engine.schedule import (
    accum_dep_cents,
    amort_expense_cents,
    depr_expense_cents,
    end_depr_month,
    month_str,
    months_elapsed,
    months_used,
    parse_month,
    prepaid_ending_cents,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(ENTITIES[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _asset(payload: dict, asset_id: str) -> dict:
    return next(
        a for a in _doc(payload, DOC_ASSET_REGISTER)["assets"]
        if a["asset_id"] == asset_id
    )


def _prepaid(payload: dict, item_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PREPAID_REGISTER)["items"]
        if p["item_id"] == item_id
    )


def _expense_item(payload: dict, item_id: str) -> dict:
    return next(
        i for i in _doc(payload, DOC_CAP_POLICY)["items"] if i["item_id"] == item_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


CLOSE = parse_month(CLOSE_MONTH)
assert CLOSE is not None


# --------------------------------------------------------------------------- #
# The schedule kernel at its edges
# --------------------------------------------------------------------------- #
def test_final_month_absorbs_the_remainder() -> None:
    """1000 over 3 months is 333 + 333 + 334, never 333 x 3."""
    start = CLOSE
    assert depr_expense_cents(1_000, 3, start, start) == 333
    assert depr_expense_cents(1_000, 3, start, start + 1) == 333
    assert depr_expense_cents(1_000, 3, start, start + 2) == 334
    assert (
        sum(depr_expense_cents(1_000, 3, start, start + k) for k in range(3)) == 1_000
    )


def test_charge_is_zero_outside_the_schedule() -> None:
    """No charge the month before service and none after the schedule completes."""
    start = CLOSE
    assert depr_expense_cents(1_000, 3, start, start - 1) == 0
    assert depr_expense_cents(1_000, 3, start, start + 3) == 0


def test_accumulated_caps_at_cost_exactly_at_the_final_month() -> None:
    """The cap is reached in the final month, not a month later."""
    start = CLOSE
    assert accum_dep_cents(1_000, 3, start, start + 1) == 666
    assert accum_dep_cents(1_000, 3, start, start + 2) == 1_000
    assert accum_dep_cents(1_000, 3, start, start + 99) == 1_000


def test_months_elapsed_counts_the_in_service_month_and_clamps() -> None:
    """Full-month convention: the in-service month is month one; before it, zero."""
    assert months_elapsed(CLOSE, CLOSE) == 1
    assert months_elapsed(CLOSE, CLOSE - 1) == 0
    assert months_elapsed(CLOSE, CLOSE + 11) == 12


@pytest.mark.parametrize("elapsed_offset, expected", [(34, 35), (35, 36), (60, 36)])
def test_months_used_caps_at_the_life(elapsed_offset: int, expected: int) -> None:
    assert months_used(CLOSE - elapsed_offset, CLOSE, 36) == expected


def test_end_depr_month_is_in_service_plus_life_less_one() -> None:
    """A 36-month asset in service 2027-03 takes its final charge in 2030-02."""
    in_service = parse_month("2027-03")
    assert in_service is not None
    assert month_str(end_depr_month(in_service, 36)) == "2030-02"


def test_prepaid_catchup_first_booked_month() -> None:
    """An item booked two periods late takes both periods' charge at once."""
    start = CLOSE - 2
    end = start + 11
    assert amort_expense_cents(1_200, start, end, CLOSE, CLOSE) == 300
    assert amort_expense_cents(1_200, start, end, CLOSE, CLOSE + 1) == 100
    assert amort_expense_cents(1_200, start, end, CLOSE, CLOSE - 1) == 0


def test_prepaid_final_period_absorbs_the_remainder_and_ends_at_zero() -> None:
    """The window's last period books what is left, and the balance closes at 0."""
    start = CLOSE
    end = CLOSE + 2
    assert amort_expense_cents(1_000, start, end, start, end) == 334
    assert amort_expense_cents(1_000, start, end, start, end + 1) == 0
    assert prepaid_ending_cents(1_000, start, end, start, end) == 0


# --------------------------------------------------------------------------- #
# cap_threshold_gate -- capitalized at the threshold, expensed a cent below
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "cost, capitalized, should_fail",
    [
        (THRESHOLD_CENTS, True, False),
        (THRESHOLD_CENTS, False, True),
        (THRESHOLD_CENTS - 1, False, False),
        (THRESHOLD_CENTS - 1, True, True),
    ],
)
def test_threshold_gate_at_the_cent(cost: int, capitalized: bool, should_fail: bool) -> None:
    payload = _payload()
    item = _expense_item(payload, "EX-201")
    item["cost_cents"] = cost
    item["capitalized"] = capitalized
    assert bool(_fired(check_cap_threshold_gate(_ctx(payload)))) is should_fail


def test_excluded_category_is_never_capitalized() -> None:
    """Annual software stays expensed no matter what it costs."""
    payload = _payload()
    assert not _fired(check_cap_threshold_gate(_ctx(payload)))
    _expense_item(payload, "EX-202")["capitalized"] = True
    assert _fired(check_cap_threshold_gate(_ctx(payload)))


# --------------------------------------------------------------------------- #
# sl_ -- the stated figures re-derive to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_monthly_dep_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _asset(payload, "FA-101")["monthly_dep_cents"] += delta
    assert bool(_fired(check_sl_monthly_dep_rederives(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_close_month_expense_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _asset(payload, "FA-103")["depr_exp_cents"] += delta
    assert bool(_fired(check_sl_expense_rederives(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_accum_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    """NBV moves with the accumulated balance so only the re-derivation is tested."""
    payload = _payload()
    row = _asset(payload, "FA-101")
    row["accum_dep_cents"] += delta
    row["nbv_cents"] -= delta
    assert bool(_fired(check_nbv_accum_rederives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# date_ -- the service gate flips exactly at the close month
# --------------------------------------------------------------------------- #
def test_asset_in_service_on_the_close_month_is_no_longer_staged() -> None:
    """In service during the close month means the pre-service gate steps aside."""
    payload = _payload()
    row = _asset(payload, "FA-106")
    row["in_service_month"] = CLOSE_MONTH
    rederive_asset_row(row)
    rederive(payload)
    assert not _fired(check_date_not_in_service_yet(_ctx(payload)))
    assert not _fired(check_sl_expense_rederives(_ctx(payload)))
    assert row["depr_exp_cents"] == row["monthly_dep_cents"]


def test_staged_asset_with_depreciation_fails_the_service_gate() -> None:
    payload = _payload()
    row = _asset(payload, "FA-106")
    row["accum_dep_cents"] = 1
    row["nbv_cents"] = row["cost_cents"] - 1
    assert _fired(check_date_not_in_service_yet(_ctx(payload)))


def test_final_month_asset_belongs_to_the_schedule_not_the_end_gate() -> None:
    """An asset in its exact final month is still depreciating: the end gate
    applies only after the schedule completes."""
    payload = _payload()
    row = _asset(payload, "FA-104")
    row["in_service_month"] = month_str(CLOSE - 35)  # 36-month life ends at close
    rederive_asset_row(row)
    rederive(payload)
    assert not _fired(check_date_fully_depreciated_zero(_ctx(payload)))
    assert not _fired(check_sl_expense_rederives(_ctx(payload)))
    assert row["depr_exp_cents"] > 0
    assert row["accum_dep_cents"] == row["cost_cents"]


def test_month_after_the_final_month_the_end_gate_owns_the_asset() -> None:
    payload = _payload()
    row = _asset(payload, "FA-104")
    row["in_service_month"] = month_str(CLOSE - 36)
    rederive_asset_row(row)
    rederive(payload)
    assert not _fired(check_date_fully_depreciated_zero(_ctx(payload)))
    row["nbv_cents"] += 1
    row["accum_dep_cents"] -= 1
    assert _fired(check_date_fully_depreciated_zero(_ctx(payload)))


# --------------------------------------------------------------------------- #
# disp_fully_depreciated_watch -- the review band closes at exactly its edge
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "months_past_end, should_flag",
    [(DISPOSAL_REVIEW_MONTHS, False), (DISPOSAL_REVIEW_MONTHS + 1, True)],
)
def test_disposal_review_band_edge(months_past_end: int, should_flag: bool) -> None:
    """An asset exactly at the band's edge is inside it; one month more is not."""
    payload = _payload()
    row = _asset(payload, "FA-104")
    end = CLOSE - months_past_end
    row["in_service_month"] = month_str(end - 35)  # 36-month life
    rederive_asset_row(row)
    fired = _fired(check_disp_fully_depreciated_watch(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# pre_ -- the waterfall and its watch at their edges
# --------------------------------------------------------------------------- #
def test_clean_baseline_carries_a_real_catchup() -> None:
    """The baseline's late-set-up licence takes two periods' charge this month,
    so the catch-up path is exercised by the clean corpus itself."""
    payload = _payload()
    row = _prepaid(payload, "PP-402")
    assert row["amort_this_period_cents"] == 2 * row["monthly_amort_cents"]
    assert not _fired(check_pre_expense_rederives(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_prepaid_expense_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _prepaid(payload, "PP-401")["amort_this_period_cents"] += delta
    assert bool(_fired(check_pre_expense_rederives(_ctx(payload)))) is should_fail


@pytest.mark.parametrize(
    "months_out, should_flag",
    [(0, True), (PREPAID_WATCH_MONTHS, True), (PREPAID_WATCH_MONTHS + 1, False)],
)
def test_prepaid_window_watch_edge(months_out: int, should_flag: bool) -> None:
    """A window ending exactly ``watch_months`` out is inside the watch; a month
    past it is not."""
    payload = _payload()
    _prepaid(payload, "PP-403")["window_end"] = month_str(CLOSE + months_out)
    fired = _fired(check_pre_window_ending_watch(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# roll_ / gl_ / je_ -- identities and tie-outs break at one cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_accum_rollforward_identity_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_ROLLFORWARD)["fixed_assets"]["opening_accum_cents"] += delta
    assert bool(_fired(check_roll_accum_identity(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_gl_accum_tie_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = next(
        a for a in _doc(payload, DOC_GL_BALANCES)["accounts"] if a["account"] == GL_ACCUM
    )
    row["balance_cents"] += delta
    assert bool(_fired(check_gl_accum_ties(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_je_depreciation_tie_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    line = next(
        ln for ln in _doc(payload, DOC_RECURRING_JE)["lines"]
        if ln["line_id"] == JE_DEPRECIATION
    )
    line["amount_cents"] += delta
    assert bool(_fired(check_je_depreciation_ties(_ctx(payload)))) is should_fail


def test_missing_je_line_is_a_failure_not_a_skip() -> None:
    """A JE that was never posted cannot tie; absence is the finding."""
    payload = _payload()
    je = _doc(payload, DOC_RECURRING_JE)
    je["lines"] = [ln for ln in je["lines"] if ln["line_id"] != JE_DEPRECIATION]
    fired = _fired(check_je_depreciation_ties(_ctx(payload)))
    assert fired
    assert "was not posted" in fired[0].message


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "cap_threshold_gate": Status.FAIL,
    "cap_register_meets_threshold": Status.FAIL,
    "life_class_known": Status.FAIL,
    "life_matches_class": Status.FAIL,
    "life_method_straight_line": Status.FAIL,
    "sl_monthly_dep_rederives": Status.FAIL,
    "sl_expense_rederives": Status.FAIL,
    "date_end_depr_rederives": Status.FAIL,
    "date_fully_depreciated_zero": Status.FAIL,
    "date_not_in_service_yet": Status.FAIL,
    "nbv_months_used_cap": Status.FAIL,
    "nbv_accum_rederives": Status.FAIL,
    "nbv_floor": Status.FAIL,
    "roll_accum_identity": Status.FAIL,
    "roll_closing_ties_register": Status.FAIL,
    "roll_prepaid_rollforward": Status.FAIL,
    "pre_window_valid": Status.FAIL,
    "pre_monthly_amort_rederives": Status.FAIL,
    "pre_expense_rederives": Status.FAIL,
    "pre_ending_balance_rederives": Status.FAIL,
    "pre_window_ending_watch": Status.FLAG,
    "disp_not_on_register": Status.FAIL,
    "disp_gain_loss_rederives": Status.FAIL,
    "disp_fully_depreciated_watch": Status.FLAG,
    "gl_cost_ties": Status.FAIL,
    "gl_accum_ties": Status.FAIL,
    "gl_prepaid_ties": Status.FAIL,
    "je_depreciation_ties": Status.FAIL,
    "je_prepaid_amort_ties": Status.FAIL,
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
        "set", "cap", "life", "sl", "date", "nbv", "roll", "pre", "disp", "gl", "je",
    }
