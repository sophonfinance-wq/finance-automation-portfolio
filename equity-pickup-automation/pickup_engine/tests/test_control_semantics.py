"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day or one cent either side of the line. A
control that fires a cent early is as wrong as one that never fires, and only a
boundary test can tell the two apart.

The re-derivation cases carry the most weight. A pickup met to the cent must
pass and a cent off must fail in *either* direction; an accrual period starting
the day after the prior one ends is contiguous while one day either side is a
gap or a double-count; and the kernel's floor division and residual-cent rules
are pinned so neither side of the shared arithmetic can drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pickup_engine.engine import (
    SEVERITY,
    check_alloc_foots,
    check_alloc_member_is_holder,
    check_alloc_tb_adjustment_math,
    check_alloc_tb_investment_ties,
    check_alloc_tb_pickup_ties,
    check_alloc_tb_unposted_adjustment,
    check_alloc_ties_net_income,
    check_elim_account_link_key,
    check_elim_block_balances,
    check_elim_extinguishes_investment,
    check_elim_pairing_complete,
    check_epu_cost_no_pickup,
    check_epu_ownership_bounds,
    check_epu_pickup_rederives,
    check_pref_accrual_rederives,
    check_pref_capital_chains,
    check_pref_day_count,
    check_pref_periods_contiguous,
    check_rf_distributions_rederive,
    check_rf_identity,
)
from pickup_engine.generate import GROUPS, baseline
from pickup_engine.model import (
    DOC_ALLOCATION_SUMMARY,
    DOC_ELIMINATION_SCHEDULE,
    DOC_INVESTMENT_ROLLFORWARD,
    DOC_PREFERRED_RETURN,
    DOC_TRIAL_BALANCE,
    Context,
    Status,
)
from pickup_engine.pickup import (
    allocate_shares,
    inclusive_days,
    preferred_accrual,
    rollforward_end,
    share_of,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(GROUPS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _rf_row(payload: dict, holding_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_INVESTMENT_ROLLFORWARD)["rows"]
        if r["holding_id"] == holding_id
    )


def _block(payload: dict, holding_id: str) -> dict:
    return next(
        b for b in _doc(payload, DOC_ELIMINATION_SCHEDULE)["blocks"]
        if b["holding_id"] == holding_id
    )


def _schedule(payload: dict, member_id: str) -> dict:
    return next(
        s for s in _doc(payload, DOC_PREFERRED_RETURN)["schedules"]
        if s["member_id"] == member_id
    )


def _entry(payload: dict, sub_id: str) -> dict:
    return next(
        e for e in _doc(payload, DOC_ALLOCATION_SUMMARY)["entries"]
        if e["sub_id"] == sub_id
    )


def _holding(payload: dict, holding_id: str) -> dict:
    return next(
        h for h in _doc(payload, "holding_register")["holdings"]
        if h["holding_id"] == holding_id
    )


def _tb(payload: dict, entity_id: str, account: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_TRIAL_BALANCE)["rows"]
        if r["entity_id"] == entity_id and r["account"] == account
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# Kernel arithmetic -- the shared boundary both sides must agree on
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "amount,bps,expected",
    [
        (48_250_137, 5000, 24_125_068),  # the odd cent floors away
        (48_250_137, 10000, 48_250_137),
        (-8_443_500, 6000, -5_066_100),  # a loss share is exact too
        (-1, 5000, -1),                  # floor rounds toward -inf on a loss
        (1, 5000, 0),
        (0, 10000, 0),
    ],
)
def test_share_of_floors(amount: int, bps: int, expected: int) -> None:
    assert share_of(amount, bps) == expected


def test_allocate_shares_residual_cent_to_final_holder() -> None:
    """A 50/50 split of an odd cent sums back to the whole."""
    shares = allocate_shares(48_250_137, [5000, 5000])
    assert shares == [24_125_068, 24_125_069]
    assert sum(shares) == 48_250_137


def test_allocate_shares_partial_holders_get_no_residual() -> None:
    """Holders of less than the whole take exactly their floors."""
    assert allocate_shares(101, [3000, 3000]) == [30, 30]


def test_allocate_shares_sole_holder_takes_everything() -> None:
    assert allocate_shares(-8_443_500, [10000]) == [-8_443_500]


def test_allocate_shares_empty_is_empty() -> None:
    assert allocate_shares(100, []) == []


@pytest.mark.parametrize(
    "begin,contrib,pickup,distr,expected",
    [(0, 0, 0, 0, 0), (100, 25, 10, -5, 140), (100, 0, -30, 20, 50)],
)
def test_rollforward_end(begin, contrib, pickup, distr, expected) -> None:
    assert rollforward_end(begin, contrib, pickup, distr) == expected


def test_inclusive_days_counts_both_endpoints() -> None:
    from datetime import date

    assert inclusive_days(date(2030, 1, 1), date(2030, 1, 1)) == 1
    assert inclusive_days(date(2030, 1, 1), date(2030, 3, 31)) == 90
    assert inclusive_days(date(2029, 7, 1), date(2029, 9, 30)) == 92


def test_preferred_accrual_truncates_once_at_the_end() -> None:
    """250,000,000 x 800 bps x 92/365 is 5,041,095.89...; one floor, no drift."""
    assert preferred_accrual(250_000_000, 800, 92, 365) == 5_041_095


def test_preferred_accrual_zero_capital_accrues_nothing() -> None:
    assert preferred_accrual(0, 800, 92, 365) == 0


# --------------------------------------------------------------------------- #
# rf_ -- the identity closes at the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_rollforward_identity_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _rf_row(payload, "HLD-03")["end_cents"] += delta
    assert bool(_fired(check_rf_identity(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_distribution_share_at_the_cent(delta: int, should_fail: bool) -> None:
    """The share is an equality, so a cent off in either direction fails."""
    payload = _payload()
    row = _rf_row(payload, "HLD-03")
    row["distributions_cents"] += delta
    row["contributions_cents"] += delta  # keep the identity out of the picture
    assert bool(_fired(check_rf_distributions_rederive(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# epu_ -- the pickup re-derives exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_pickup_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _rf_row(payload, "HLD-03")
    row["pickup_cents"] += delta
    row["contributions_cents"] -= delta
    assert bool(_fired(check_epu_pickup_rederives(_ctx(payload)))) is should_fail


def test_residual_cent_lands_on_the_final_holder() -> None:
    """The 50/50 JV books the odd cent on the last holding, and only there."""
    payload = _payload()
    assert _rf_row(payload, "HLD-01")["pickup_cents"] == 24_125_068
    assert _rf_row(payload, "HLD-02")["pickup_cents"] == 24_125_069
    assert not _fired(check_epu_pickup_rederives(_ctx(payload)))


def test_cost_method_books_no_pickup() -> None:
    payload = _payload()
    assert not _fired(check_epu_cost_no_pickup(_ctx(payload)))
    row = _rf_row(payload, "HLD-06")
    row["pickup_cents"] = 1
    row["contributions_cents"] -= 1
    assert _fired(check_epu_cost_no_pickup(_ctx(payload)))


@pytest.mark.parametrize(
    "bps, should_fail",
    [(10000, False), (10001, True), (1, False), (0, True), (-500, True)],
)
def test_ownership_bounds_edges(bps: int, should_fail: bool) -> None:
    """HLD-03 is the sole holder of its sub, so only the bounds move."""
    payload = _payload()
    _holding(payload, "HLD-03")["ownership_bps"] = bps
    assert bool(_fired(check_epu_ownership_bounds(_ctx(payload)))) is should_fail


def test_ownership_over_allocation_across_holders() -> None:
    """Each holder is in bounds alone; together they claim more than the sub."""
    payload = _payload()
    _holding(payload, "HLD-01")["ownership_bps"] = 6000  # 6000 + 5000 > 10000
    fired = _fired(check_epu_ownership_bounds(_ctx(payload)))
    assert fired
    assert any("SUB-285" in f.message for f in fired)


# --------------------------------------------------------------------------- #
# elim_ -- balanced, paired, extinguished, linkable
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_elimination_balances_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _block(payload, "HLD-03")["lines"][0]["debit_cents"] += delta
    assert bool(_fired(check_elim_block_balances(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_elimination_extinguishes_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    block = _block(payload, "HLD-01")
    block["lines"][0]["debit_cents"] += delta
    block["lines"][1]["credit_cents"] += delta  # stays balanced either way
    assert bool(_fired(check_elim_extinguishes_investment(_ctx(payload)))) is should_fail


def test_pairing_requires_both_sides() -> None:
    """Dropping the investment credit line un-pairs the holding."""
    payload = _payload()
    assert not _fired(check_elim_pairing_complete(_ctx(payload)))
    block = _block(payload, "HLD-01")
    block["lines"] = [line for line in block["lines"] if line["credit_cents"] == 0]
    fired = _fired(check_elim_pairing_complete(_ctx(payload)))
    assert fired
    assert "credit to investment account" in fired[0].message


def test_pairing_requires_a_block_at_all() -> None:
    payload = _payload()
    schedule = _doc(payload, DOC_ELIMINATION_SCHEDULE)
    schedule["blocks"] = [b for b in schedule["blocks"] if b["holding_id"] != "HLD-02"]
    assert _fired(check_elim_pairing_complete(_ctx(payload)))


def test_link_key_derives_every_account() -> None:
    payload = _payload()
    assert not _fired(check_elim_account_link_key(_ctx(payload)))
    _holding(payload, "HLD-04")["pickup_account"] = "100-9160"
    fired = _fired(check_elim_account_link_key(_ctx(payload)))
    assert fired
    assert "100-3160" in fired[0].message


# --------------------------------------------------------------------------- #
# pref_ -- day counts, accruals, chain and continuity
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_day_count_at_the_day(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _schedule(payload, "MBR-01")["rows"][0]["days"] += delta
    assert bool(_fired(check_pref_day_count(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_accrual_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _schedule(payload, "MBR-02")["rows"][0]["accrued_cents"] += delta
    assert bool(_fired(check_pref_accrual_rederives(_ctx(payload)))) is should_fail


def test_accrual_is_derived_from_dates_not_stated_days() -> None:
    """A misstated day count cannot launder the accrual it multiplied."""
    payload = _payload()
    _schedule(payload, "MBR-01")["rows"][0]["days"] += 3
    assert not _fired(check_pref_accrual_rederives(_ctx(payload)))
    assert _fired(check_pref_day_count(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_capital_chain_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    rows = _schedule(payload, "MBR-01")["rows"]
    rows[-1]["ending_capital_cents"] += delta  # last row: no successor to double-fire
    assert bool(_fired(check_pref_capital_chains(_ctx(payload)))) is should_fail


@pytest.mark.parametrize(
    "start, should_fail",
    [("2029-10-01", False), ("2029-10-02", True), ("2029-09-30", True)],
)
def test_periods_abut_exactly(start: str, should_fail: bool) -> None:
    """The day after the prior end is contiguous; either side is a gap or a
    double-count."""
    payload = _payload()
    _schedule(payload, "MBR-01")["rows"][1]["start_date"] = start
    assert bool(_fired(check_pref_periods_contiguous(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# alloc_ -- footing, income tie, membership and the TB tie-out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_allocation_foots_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _entry(payload, "SUB-322")["stated_total_cents"] += delta
    assert bool(_fired(check_alloc_foots(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_allocation_ties_income_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    entry = _entry(payload, "SUB-285")
    entry["members"][0]["allocated_cents"] += delta
    entry["stated_total_cents"] += delta  # keep the footing out of the picture
    assert bool(_fired(check_alloc_ties_net_income(_ctx(payload)))) is should_fail


def test_allocation_must_exist_for_a_fully_held_sub() -> None:
    payload = _payload()
    summary = _doc(payload, DOC_ALLOCATION_SUMMARY)
    summary["entries"] = [e for e in summary["entries"] if e["sub_id"] != "SUB-322"]
    fired = _fired(check_alloc_ties_net_income(_ctx(payload)))
    assert fired
    assert "allocated exactly once" in fired[0].message


def test_allocation_member_must_hold_the_sub() -> None:
    payload = _payload()
    assert not _fired(check_alloc_member_is_holder(_ctx(payload)))
    _entry(payload, "SUB-285")["members"].append(
        {"parent_id": "PAR-777", "allocated_cents": 0}
    )
    assert _fired(check_alloc_member_is_holder(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tb_investment_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _tb(payload, "PAR-100", "100-1322")
    row["balance_cents"] += delta
    row["should_be_cents"] += delta  # keep the adjustment math out of the picture
    assert bool(_fired(check_alloc_tb_investment_ties(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tb_pickup_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _tb(payload, "PAR-200", "200-3285")
    row["balance_cents"] += delta
    row["should_be_cents"] += delta
    assert bool(_fired(check_alloc_tb_pickup_ties(_ctx(payload)))) is should_fail


def test_pickup_tie_reads_the_rederived_share_not_the_stated_one() -> None:
    """A mis-keyed roll-forward cannot vouch for a mis-keyed ledger."""
    payload = _payload()
    row = _rf_row(payload, "HLD-03")
    row["pickup_cents"] += 100
    row["contributions_cents"] -= 100
    assert not _fired(check_alloc_tb_pickup_ties(_ctx(payload)))
    assert _fired(check_epu_pickup_rederives(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_adjustment_math_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _tb(payload, "SUB-285", "285-2999")["should_be_cents"] += delta
    assert bool(_fired(check_alloc_tb_adjustment_math(_ctx(payload)))) is should_fail


def test_unposted_adjustment_is_a_flag_not_a_failure() -> None:
    payload = _payload()
    assert not _fired(check_alloc_tb_unposted_adjustment(_ctx(payload)))
    row = _tb(payload, "SUB-322", "322-2999")
    row["should_be_cents"] += 4200
    row["adjustment_cents"] = 4200
    fired = _fired(check_alloc_tb_unposted_adjustment(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG
    assert not _fired(check_alloc_tb_adjustment_math(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "rf_identity": Status.FAIL,
    "rf_row_has_holding": Status.FAIL,
    "rf_coverage_complete": Status.FAIL,
    "rf_distributions_rederive": Status.FAIL,
    "epu_pickup_rederives": Status.FAIL,
    "epu_cost_no_pickup": Status.FAIL,
    "epu_ownership_bounds": Status.FAIL,
    "epu_refs_resolve": Status.FAIL,
    "elim_block_balances": Status.FAIL,
    "elim_pairing_complete": Status.FAIL,
    "elim_extinguishes_investment": Status.FAIL,
    "elim_refs_known": Status.FAIL,
    "elim_account_link_key": Status.FAIL,
    "pref_day_count": Status.FAIL,
    "pref_accrual_rederives": Status.FAIL,
    "pref_capital_chains": Status.FAIL,
    "pref_periods_contiguous": Status.FAIL,
    "alloc_foots": Status.FAIL,
    "alloc_ties_net_income": Status.FAIL,
    "alloc_member_is_holder": Status.FAIL,
    "alloc_tb_investment_ties": Status.FAIL,
    "alloc_tb_pickup_ties": Status.FAIL,
    "alloc_tb_adjustment_math": Status.FAIL,
    "alloc_tb_unposted_adjustment": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "rf", "epu", "elim", "pref", "alloc"}
