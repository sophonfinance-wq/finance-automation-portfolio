"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one day or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The rollforward and adequacy cases carry the most weight. An identity that holds
to the cent must pass and a cent either side must fail; a draw exactly equal to
the balance in front of it spends the bucket to zero and is allowed, while a cent
more is an overdraw; a bucket whose projection exactly equals its balance is
adequate, and a bucket sitting exactly on the watch band is inside it.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from contingency_engine.engine import (
    SEVERITY,
    check_adq_flag_recomputes,
    check_adq_headroom_watch,
    check_adq_projection_nonnegative,
    check_alc_amount_positive,
    check_alc_within_period,
    check_ctg_allocated_ties_line_items,
    check_ctg_budget_reconciles,
    check_ctg_current_rolls_forward,
    check_ctg_no_overdraw,
    check_ctg_to_date_rolls_forward,
    check_rpt_inadequate_count_ties,
    check_rpt_portfolio_foots,
    check_rpt_watchlist_ties,
)
from contingency_engine.generate import (
    PERIOD_END,
    PERIOD_START,
    PORTFOLIOS,
    WATCH_THRESHOLD_BPS,
    baseline,
)
from contingency_engine.model import (
    BUCKET_CONSTRUCTION,
    BUCKET_PROJECT,
    DOC_ALLOCATION_REGISTER,
    DOC_BUDGET_REGISTER,
    DOC_CONTINGENCY_BLOCK,
    DOC_EXPOSURE_WATCHLIST,
    DOC_PORTFOLIO_ROLLUP,
    Context,
    Status,
)
from contingency_engine.money import apply_rate


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _bucket(payload: dict, project_id: str, bucket: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_CONTINGENCY_BLOCK)["buckets"]
        if r["project_id"] == project_id and r["bucket"] == bucket
    )


def _budget_line(payload: dict, project_id: str, bucket: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_BUDGET_REGISTER)["contingency_lines"]
        if r["project_id"] == project_id and r["bucket"] == bucket
    )


def _allocation(payload: dict, allocation_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_ALLOCATION_REGISTER)["allocations"]
        if r["allocation_id"] == allocation_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# ctg_current_rolls_forward -- current is prior less allocated, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_current_balance_rolls_forward_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _bucket(payload, "PRJ-401", BUCKET_CONSTRUCTION)["current_balance_cents"] += delta
    assert bool(_fired(check_ctg_current_rolls_forward(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_allocated_to_date_rolls_forward_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _bucket(payload, "PRJ-403", BUCKET_CONSTRUCTION)["allocated_to_date_cents"] += delta
    assert bool(_fired(check_ctg_to_date_rolls_forward(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ctg_allocated_ties_line_items -- the total is the draws, not a figure beside them
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_period_total_ties_its_draw_detail(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _allocation(payload, "ALC-5006")["amount_cents"] += delta
    assert bool(_fired(check_ctg_allocated_ties_line_items(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ctg_budget_reconciles -- remaining plus allocated to date is what was funded
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_bucket_reconciles_to_the_budget_line(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _budget_line(payload, "PRJ-402", BUCKET_CONSTRUCTION)["budget_contingency_cents"] += delta
    assert bool(_fired(check_ctg_budget_reconciles(_ctx(payload)))) is should_fail


def test_bucket_without_a_budget_line_is_left_to_the_completeness_control() -> None:
    """A missing budget line is a completeness failure, not a reconciliation one."""
    payload = _payload()
    register = _doc(payload, DOC_BUDGET_REGISTER)
    register["contingency_lines"] = [
        r for r in register["contingency_lines"]
        if not (r["project_id"] == "PRJ-402" and r["bucket"] == BUCKET_PROJECT)
    ]
    assert not _fired(check_ctg_budget_reconciles(_ctx(payload)))


# --------------------------------------------------------------------------- #
# ctg_no_overdraw -- a draw may spend the bucket to zero, not a cent past it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True)])
def test_draw_may_spend_the_bucket_to_zero(delta: int, should_fail: bool) -> None:
    """PRJ-402 construction carries one draw; sizing it at exactly the prior balance
    empties the bucket, and one cent more is an overdraw."""
    payload = _payload()
    prior = _bucket(payload, "PRJ-402", BUCKET_CONSTRUCTION)["prior_balance_cents"]
    _allocation(payload, "ALC-5004")["amount_cents"] = prior + delta
    assert bool(_fired(check_ctg_no_overdraw(_ctx(payload)))) is should_fail


def test_overdraw_is_measured_against_what_earlier_draws_left() -> None:
    """PRJ-401 construction takes two draws. The second is sized to fit the opening
    balance but not what the first one left, so only the walk catches it."""
    payload = _payload()
    prior = _bucket(payload, "PRJ-401", BUCKET_CONSTRUCTION)["prior_balance_cents"]
    first = _allocation(payload, "ALC-5001")["amount_cents"]
    _allocation(payload, "ALC-5002")["amount_cents"] = prior - first + 1
    fired = _fired(check_ctg_no_overdraw(_ctx(payload)))
    assert fired
    assert "ALC-5002" in fired[0].message


# --------------------------------------------------------------------------- #
# alc_within_period -- the period is inclusive at both ends
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "when, should_fail",
    [
        (PERIOD_START, False),
        ((date.fromisoformat(PERIOD_START) - timedelta(days=1)).isoformat(), True),
        (PERIOD_END, False),
        ((date.fromisoformat(PERIOD_END) + timedelta(days=1)).isoformat(), True),
    ],
)
def test_draw_date_at_the_period_edges(when: str, should_fail: bool) -> None:
    payload = _payload()
    _allocation(payload, "ALC-5003")["allocation_date"] = when
    assert bool(_fired(check_alc_within_period(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# alc_amount_positive -- a draw is a release out of the bucket
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("amount, should_fail", [(1, False), (0, True), (-1, True)])
def test_draw_must_be_a_positive_amount(amount: int, should_fail: bool) -> None:
    payload = _payload()
    _allocation(payload, "ALC-5005")["amount_cents"] = amount
    assert bool(_fired(check_alc_amount_positive(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# adq_flag_recomputes -- adequate at the projection, not a cent above it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (1, True)])
def test_adequate_is_met_at_the_projection(delta: int, should_fail: bool) -> None:
    """A bucket that exactly covers its projection is adequate; a cent short is not,
    and the stated word then contradicts the row."""
    payload = _payload()
    row = _bucket(payload, "PRJ-401", BUCKET_PROJECT)
    row["projected_use_cents"] = row["current_balance_cents"] + delta
    assert bool(_fired(check_adq_flag_recomputes(_ctx(payload)))) is should_fail


def test_an_unknown_adequacy_word_never_recomputes() -> None:
    payload = _payload()
    _bucket(payload, "PRJ-403", BUCKET_PROJECT)["adequacy"] = "under review"
    fired = _fired(check_adq_flag_recomputes(_ctx(payload)))
    assert fired
    assert "under review" in fired[0].message


@pytest.mark.parametrize("projected, should_fail", [(1, False), (0, False), (-1, True)])
def test_projected_use_may_be_zero_but_not_negative(projected: int, should_fail: bool) -> None:
    payload = _payload()
    _bucket(payload, "PRJ-402", BUCKET_PROJECT)["projected_use_cents"] = projected
    assert bool(_fired(check_adq_projection_nonnegative(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# adq_headroom_watch -- the band closes at exactly the stated share
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_flag", [(0, True), (-1, False)])
def test_watch_band_edge(delta: int, should_flag: bool) -> None:
    """A bucket whose projection sits exactly on the band is inside it; a cent under
    is outside."""
    payload = _payload()
    row = _bucket(payload, "PRJ-402", BUCKET_PROJECT)
    threshold = apply_rate(row["current_balance_cents"], WATCH_THRESHOLD_BPS)
    row["projected_use_cents"] = threshold + delta
    fired = _fired(check_adq_headroom_watch(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_an_inadequate_bucket_is_not_also_watched() -> None:
    """The hard failure owns it; a bucket cannot be both short and merely thin."""
    payload = _payload()
    row = _bucket(payload, "PRJ-402", BUCKET_PROJECT)
    row["projected_use_cents"] = row["current_balance_cents"] + 1
    assert not _fired(check_adq_headroom_watch(_ctx(payload)))


def test_watch_band_is_clean_on_the_baseline() -> None:
    """The baseline buckets hold headroom well outside the band and raise no flag."""
    assert not _fired(check_adq_headroom_watch(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup foots from the block, not the other way round
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "key",
    [
        "total_allocated_period_cents",
        "total_current_balance_cents",
        "total_projected_use_cents",
    ],
)
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_rollup_totals_foot_to_the_cent(key: str, delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_PORTFOLIO_ROLLUP)[key] += delta
    assert bool(_fired(check_rpt_portfolio_foots(_ctx(payload)))) is should_fail


def test_inadequate_count_must_tie_the_block() -> None:
    payload = _payload()
    assert not _fired(check_rpt_inadequate_count_ties(_ctx(payload)))
    _doc(payload, DOC_PORTFOLIO_ROLLUP)["inadequate_count"] += 1
    assert _fired(check_rpt_inadequate_count_ties(_ctx(payload)))


def test_watchlist_must_tie_the_block() -> None:
    payload = _payload()
    assert not _fired(check_rpt_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_EXPOSURE_WATCHLIST)["entries"].append(
        {
            "project_id": "PRJ-403",
            "bucket": BUCKET_CONSTRUCTION,
            "current_balance_cents": 463_500_000,
            "projected_use_cents": 275_000_000,
            "headroom_cents": 188_500_000,
        }
    )
    fired = _fired(check_rpt_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "prj_unique_ids": Status.FAIL,
    "prj_status_valid": Status.FAIL,
    "prj_budget_defined": Status.FAIL,
    "alc_required_fields": Status.FAIL,
    "alc_unique_ids": Status.FAIL,
    "alc_project_exists": Status.FAIL,
    "alc_bucket_valid": Status.FAIL,
    "alc_within_period": Status.FAIL,
    "alc_amount_positive": Status.FAIL,
    "ctg_block_complete": Status.FAIL,
    "ctg_current_rolls_forward": Status.FAIL,
    "ctg_to_date_rolls_forward": Status.FAIL,
    "ctg_allocated_ties_line_items": Status.FAIL,
    "ctg_budget_reconciles": Status.FAIL,
    "ctg_no_overdraw": Status.FAIL,
    "adq_projection_nonnegative": Status.FAIL,
    "adq_flag_recomputes": Status.FAIL,
    "adq_headroom_watch": Status.FLAG,
    "rpt_portfolio_foots": Status.FAIL,
    "rpt_inadequate_count_ties": Status.FAIL,
    "rpt_watchlist_ties": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "prj", "alc", "ctg", "adq", "rpt"}
