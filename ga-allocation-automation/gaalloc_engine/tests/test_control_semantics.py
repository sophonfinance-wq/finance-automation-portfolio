"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one basis point or one day either side
of the line. A control that fires a cent early is as wrong as one that never
fires, and only a boundary test can tell the two apart.

The tie-out cases carry the most weight. A share column one basis point off
100.00% must fail and one exactly on it must pass; an allocated column a cent
over the pool must fail and one exactly on it must pass; a pool step exactly at
the variance band is inside it and a basis point past it is not; a meter that
closes exactly where it opened has spent nothing, and one that closes a cent
lower has been reset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gaalloc_engine.allocation import (
    driver_shares_bps,
    month_end,
    next_period,
    parse_period,
    variance_bps,
)
from gaalloc_engine.engine import (
    SEVERITY,
    check_alc_amounts_rederive,
    check_alc_amounts_tie_pool,
    check_alc_recipient_coverage,
    check_alc_shares_rederive,
    check_alc_shares_sum_to_full,
    check_drv_counts_whole,
    check_je_balanced,
    check_je_consolidation_nets_zero,
    check_je_ties_allocation,
    check_per_months_consecutive,
    check_per_tab_continuity,
    check_pol_month_over_month_variance,
    check_pst_allocations_tie_meter_delta,
    check_pst_meter_rolls_forward,
    check_pst_pool_component_ties,
    check_rcp_holding_not_recipient,
    check_rpt_rollup_ties,
)
from gaalloc_engine.generate import (
    HOLDING_ENTITY_ID,
    PORTFOLIOS,
    VARIANCE_FLAG_BPS,
    baseline,
)
from gaalloc_engine.model import (
    DOC_ALLOCATION_JOURNAL,
    DOC_ALLOCATION_REPORT,
    DOC_ALLOCATION_SCHEDULE,
    DOC_COST_POOL_LEDGER,
    DOC_DRIVER_TABLE,
    DOC_PERIOD_CALENDAR,
    DOC_POSTAGE_LOG,
    DOC_RECIPIENT_REGISTER,
    Context,
    Status,
)

#: The pool of the opening month, used to build variance cases at the band edge.
_OPENING_POOL_CENTS = 28_123_450


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _calendar_row(payload: dict, period: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_PERIOD_CALENDAR)["periods"] if r["period"] == period
    )


def _driver(payload: dict, period: str, recipient_id: str) -> dict:
    return next(
        r
        for r in _doc(payload, DOC_DRIVER_TABLE)["drivers"]
        if r["period"] == period and r["recipient_id"] == recipient_id
    )


def _pool(payload: dict, period: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_COST_POOL_LEDGER)["pools"] if r["period"] == period
    )


def _alloc(payload: dict, period: str, recipient_id: str) -> dict:
    return next(
        r
        for r in _doc(payload, DOC_ALLOCATION_SCHEDULE)["allocations"]
        if r["period"] == period and r["recipient_id"] == recipient_id
    )


def _entry(payload: dict, period: str) -> dict:
    return next(
        e for e in _doc(payload, DOC_ALLOCATION_JOURNAL)["entries"] if e["period"] == period
    )


def _line(payload: dict, period: str, entity_id: str) -> dict:
    return next(
        line for line in _entry(payload, period)["lines"] if line["entity_id"] == entity_id
    )


def _meter(payload: dict, period: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_POSTAGE_LOG)["meters"] if r["period"] == period
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# The allocation kernel -- the two identities every control reduces to
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "counts",
    [(1,), (1, 1, 1), (42, 31, 27, 18, 9, 6), (7, 0, 3), (1, 2, 3, 4, 5, 6, 7)],
)
def test_driver_shares_always_sum_to_one_hundred_percent(counts: tuple[int, ...]) -> None:
    """The share column lands on exactly 10000 bps, however the remainder falls."""
    shares = driver_shares_bps(counts)
    assert len(shares) == len(counts)
    assert sum(shares) == 10000


def test_driver_shares_with_no_basis_are_all_zero() -> None:
    """A month with no driver units has no basis, and says so rather than guessing."""
    assert driver_shares_bps((0, 0, 0)) == [0, 0, 0]


def test_driver_shares_hand_the_remainder_to_the_largest_fraction() -> None:
    """Three equal counts cannot split 10000 evenly; the extra bp is placed, not lost."""
    assert driver_shares_bps((1, 1, 1)) == [3334, 3333, 3333]


@pytest.mark.parametrize(
    "period,expected",
    [
        ("2031-01", "2031-01-31"),
        ("2031-02", "2031-02-28"),
        ("2032-02", "2032-02-29"),
        ("2031-04", "2031-04-30"),
        ("2031-12", "2031-12-31"),
    ],
)
def test_month_end_is_the_accounting_date(period: str, expected: str) -> None:
    """February is the case that catches a hand-typed accounting date."""
    end = month_end(period)
    assert end is not None
    assert end.isoformat() == expected


def test_next_period_rolls_the_year() -> None:
    assert next_period("2031-12") == "2032-01"
    assert next_period("2031-01") == "2031-02"
    assert next_period("not-a-month") is None
    assert parse_period("2031-13") is None


def test_variance_bps_has_no_base_to_measure_against() -> None:
    """A zero prior pool reports no step rather than an infinite one."""
    assert variance_bps(100, 0) == 0


# --------------------------------------------------------------------------- #
# alc_shares_sum_to_full -- 100.00%, to the basis point
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_shares_sum_at_the_basis_point(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _alloc(payload, "2031-01", "ENT-201")["share_bps"] += delta
    assert bool(_fired(check_alc_shares_sum_to_full(_ctx(payload)))) is should_fail


def test_shares_rederive_at_the_basis_point() -> None:
    """Offsetting a basis point keeps the column at 100.00% and still fails."""
    payload = _payload()
    assert not _fired(check_alc_shares_rederive(_ctx(payload)))
    _alloc(payload, "2031-01", "ENT-201")["share_bps"] += 1
    _alloc(payload, "2031-01", "ENT-202")["share_bps"] -= 1
    assert _fired(check_alc_shares_rederive(_ctx(payload)))


# --------------------------------------------------------------------------- #
# alc_amounts_tie_pool / alc_amounts_rederive -- exact to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_allocated_amounts_tie_the_pool_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _alloc(payload, "2031-03", "ENT-204")["allocated_cents"] += delta
    assert bool(_fired(check_alc_amounts_tie_pool(_ctx(payload)))) is should_fail


def test_allocated_amounts_rederive_at_the_cent() -> None:
    """Moving a cent between two recipients still ties the pool -- and still fails."""
    payload = _payload()
    assert not _fired(check_alc_amounts_rederive(_ctx(payload)))
    _alloc(payload, "2031-01", "ENT-201")["allocated_cents"] += 1
    _alloc(payload, "2031-01", "ENT-202")["allocated_cents"] -= 1
    assert _fired(check_alc_amounts_rederive(_ctx(payload)))


def test_recipient_coverage_owns_a_missing_row() -> None:
    """A tab missing a recipient is named once, not three times downstream."""
    payload = _payload()
    schedule = _doc(payload, DOC_ALLOCATION_SCHEDULE)
    schedule["allocations"] = [
        r
        for r in schedule["allocations"]
        if not (r["period"] == "2031-04" and r["recipient_id"] == "PRJ-301")
    ]
    ctx = _ctx(payload)
    assert _fired(check_alc_recipient_coverage(ctx))
    assert not _fired(check_alc_shares_sum_to_full(ctx))
    assert not _fired(check_alc_amounts_tie_pool(ctx))


# --------------------------------------------------------------------------- #
# drv_counts_whole -- zero is a basis, negative is not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("count, should_fail", [(0, False), (-1, True)])
def test_driver_count_zero_is_allowed_and_negative_is_not(
    count: int, should_fail: bool
) -> None:
    payload = _payload()
    _driver(payload, "2031-02", "PRJ-302")["driver_count"] = count
    assert bool(_fired(check_drv_counts_whole(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# pol_month_over_month_variance -- the band closes at exactly the stated width
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "step_cents, should_flag", [(1_406_173, False), (1_408_985, True)]
)
def test_pool_variance_band_edge(step_cents: int, should_flag: bool) -> None:
    """A step of exactly the band is inside it; a basis point past it is not."""
    payload = _payload()
    _pool(payload, "2031-02")["pool_total_cents"] = _OPENING_POOL_CENTS + step_cents
    fired = _fired(check_pol_month_over_month_variance(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_pool_variance_is_clean_on_the_baseline() -> None:
    """The baseline pools move month to month well inside the band."""
    assert not _fired(check_pol_month_over_month_variance(_ctx(_payload())))
    assert VARIANCE_FLAG_BPS == 500


# --------------------------------------------------------------------------- #
# je_ -- balance, tie-out and the consolidation identity
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_entry_balances_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _line(payload, "2031-02", HOLDING_ENTITY_ID)["credit_cents"] += delta
    assert bool(_fired(check_je_balanced(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_entry_ties_the_allocation_at_the_cent(delta: int, should_fail: bool) -> None:
    """The credit moves with the debit, so only the tie-out control can see it."""
    payload = _payload()
    _line(payload, "2031-02", "ENT-201")["debit_cents"] += delta
    _line(payload, "2031-02", HOLDING_ENTITY_ID)["credit_cents"] += delta
    assert bool(_fired(check_je_ties_allocation(_ctx(payload)))) is should_fail


def test_entry_line_outside_the_group_is_caught() -> None:
    payload = _payload()
    _line(payload, "2031-02", "ENT-201")["entity_id"] = "ENT-909"
    assert _fired(check_je_ties_allocation(_ctx(payload)))


def test_self_wash_nets_to_nothing_and_is_still_caught() -> None:
    """A debit and a credit on one entity leave balance and net untouched."""
    payload = _payload()
    assert not _fired(check_je_consolidation_nets_zero(_ctx(payload)))
    _entry(payload, "2031-02")["lines"].extend(
        [
            {"entity_id": "ENT-203", "account": "1490", "debit_cents": 1, "credit_cents": 0},
            {"entity_id": "ENT-203", "account": "1490", "debit_cents": 0, "credit_cents": 1},
        ]
    )
    ctx = _ctx(payload)
    assert not _fired(check_je_balanced(ctx))
    assert not _fired(check_je_ties_allocation(ctx))
    assert _fired(check_je_consolidation_nets_zero(ctx))


# --------------------------------------------------------------------------- #
# pst_ -- the meter is the evidence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(0, False), (-1, True)])
def test_meter_may_close_where_it_opened_but_not_below(
    delta: int, should_fail: bool
) -> None:
    """A month with no postage spent is a zero delta, not a backwards meter."""
    payload = _payload()
    meter = _meter(payload, "2031-06")
    meter["end_meter_cents"] = meter["begin_meter_cents"] + delta
    assert bool(_fired(check_pst_meter_rolls_forward(_ctx(payload)))) is should_fail


def test_meter_roll_forward_break_is_caught() -> None:
    payload = _payload()
    _meter(payload, "2031-04")["begin_meter_cents"] += 1
    assert _fired(check_pst_meter_rolls_forward(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_postage_split_ties_the_meter_delta_at_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _meter(payload, "2031-03")["allocations"][0]["amount_cents"] += delta
    assert (
        bool(_fired(check_pst_allocations_tie_meter_delta(_ctx(payload)))) is should_fail
    )


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_pool_postage_component_ties_the_meter_at_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _pool(payload, "2031-05")["postage_cents"] += delta
    assert bool(_fired(check_pst_pool_component_ties(_ctx(payload)))) is should_fail


def test_backwards_meter_is_owned_by_one_control() -> None:
    """A reset meter is reported once, not by every control that reads the delta."""
    payload = _payload()
    meter = _meter(payload, "2031-06")
    meter["end_meter_cents"] = meter["begin_meter_cents"] - 100
    ctx = _ctx(payload)
    assert _fired(check_pst_meter_rolls_forward(ctx))
    assert not _fired(check_pst_allocations_tie_meter_delta(ctx))
    assert not _fired(check_pst_pool_component_ties(ctx))


# --------------------------------------------------------------------------- #
# per_ -- the month tabs and the stamped accounting date
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "accounting_date, should_fail",
    [("2031-02-28", False), ("2031-02-27", True), ("2031-03-01", True)],
)
def test_period_is_stamped_to_its_own_month_end(
    accounting_date: str, should_fail: bool
) -> None:
    """A tab rolled forward but dated a day out posts into the wrong period."""
    payload = _payload()
    _calendar_row(payload, "2031-02")["accounting_date"] = accounting_date
    _entry(payload, "2031-02")["accounting_date"] = accounting_date
    assert bool(_fired(check_per_tab_continuity(_ctx(payload)))) is should_fail


def test_entry_dated_off_its_calendar_tab_is_caught() -> None:
    payload = _payload()
    _entry(payload, "2031-02")["accounting_date"] = "2031-01-31"
    assert _fired(check_per_tab_continuity(_ctx(payload)))


def test_calendar_must_run_month_by_month() -> None:
    payload = _payload()
    assert not _fired(check_per_months_consecutive(_ctx(payload)))
    _calendar_row(payload, "2031-04")["period"] = "2031-09"
    assert _fired(check_per_months_consecutive(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rcp_ / rpt_ -- the holding entity, and the rollup that recomputes
# --------------------------------------------------------------------------- #
def test_holding_entity_cannot_receive_its_own_allocation() -> None:
    payload = _payload()
    assert not _fired(check_rcp_holding_not_recipient(_ctx(payload)))
    _doc(payload, DOC_RECIPIENT_REGISTER)["recipients"].append(
        {
            "recipient_id": HOLDING_ENTITY_ID,
            "name": "Westmere Holdings",
            "kind": "operating_entity",
            "gl_account": "7100",
        }
    )
    assert _fired(check_rcp_holding_not_recipient(_ctx(payload)))


@pytest.mark.parametrize(
    "field_name, delta",
    [
        ("period_count", 1),
        ("recipient_count", -1),
        ("pool_total_cents", 1),
        ("allocated_total_cents", -1),
    ],
)
def test_rollup_must_recompute_field_by_field(field_name: str, delta: int) -> None:
    payload = _payload()
    assert not _fired(check_rpt_rollup_ties(_ctx(payload)))
    _doc(payload, DOC_ALLOCATION_REPORT)[field_name] += delta
    assert _fired(check_rpt_rollup_ties(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "per_months_consecutive": Status.FAIL,
    "per_tab_continuity": Status.FAIL,
    "rcp_unique_ids": Status.FAIL,
    "rcp_rows_wellformed": Status.FAIL,
    "rcp_holding_not_recipient": Status.FAIL,
    "drv_counts_whole": Status.FAIL,
    "drv_coverage_complete": Status.FAIL,
    "pol_components_sum": Status.FAIL,
    "pol_month_over_month_variance": Status.FLAG,
    "alc_recipient_coverage": Status.FAIL,
    "alc_shares_sum_to_full": Status.FAIL,
    "alc_shares_rederive": Status.FAIL,
    "alc_amounts_tie_pool": Status.FAIL,
    "alc_amounts_rederive": Status.FAIL,
    "je_balanced": Status.FAIL,
    "je_ties_allocation": Status.FAIL,
    "je_consolidation_nets_zero": Status.FAIL,
    "pst_meter_rolls_forward": Status.FAIL,
    "pst_allocations_tie_meter_delta": Status.FAIL,
    "pst_pool_component_ties": Status.FAIL,
    "rpt_rollup_ties": Status.FAIL,
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
        "set", "per", "rcp", "drv", "pol", "alc", "je", "pst", "rpt"
    }
