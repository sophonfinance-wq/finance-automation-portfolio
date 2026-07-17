"""Census grids: per-component parametric suites with independent recomputes.

Raises every recurring-entry component to the 300-test floor with meaningful
parametrized cases. Every expected amount is recomputed here with local,
engine-independent arithmetic (straight-line splitter, largest-remainder
allocator, fraction-based half-up rounding), so each case fails on a real
defect in the engine's math, line construction, schedules, or tie-outs.

Grid axes: seeds x periods x sub-ledger items x entities, on fully fictional
seeded data. Custom grids rebuild datasets with parametrized sub-ledgers to
exercise rounding and netting boundaries the generated data never hits.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from fractions import Fraction
from functools import lru_cache

import pytest

from close_engine import money
from close_engine.engine import CloseEngine
from close_engine.generate import (
    ENTITIES,
    FixedAsset,
    GnaAllocation,
    MgmtFee,
    Note,
    Prepaid,
    generate_dataset,
)
from close_engine.sentinel import Severity
from close_engine.sentinel.controls import c1_re_balance


# ---------------------------------------------------------------------------
# Shared grid and cached closes
# ---------------------------------------------------------------------------

SEEDS = [3, 42, 2026]
# Spread across the lease escalation steps: months where straight-line rent
# exceeds cash rent (deferred liability builds) and months where it lags
# (deferred asset builds), plus a year roll into 2027.
PERIODS = [
    "2026-01",
    "2026-03",
    "2026-05",
    "2026-06",
    "2026-08",
    "2026-10",
    "2026-12",
    "2027-02",
]
GRID = [(p, s) for p in PERIODS for s in SEEDS]

ENTITY_CODES = [e.code for e in ENTITIES]


@lru_cache(maxsize=None)
def _dataset(period: str, seed: int):
    return generate_dataset(period, seed=seed)


@lru_cache(maxsize=None)
def _result(period: str, seed: int):
    return CloseEngine(_dataset(period, seed)).run()


def _entry(result, suffix: str):
    """Return the single register entry whose je_id ends with ``suffix``."""
    matches = [je for je in result.register if je.je_id.endswith(suffix)]
    assert len(matches) == 1, f"expected one {suffix} entry, got {len(matches)}"
    return matches[0]


def _schedule(result, category: str):
    """Return the single schedule for a recurring-entry category."""
    matches = [s for s in result.schedules if s.category == category]
    assert len(matches) == 1
    return matches[0]


def _row(schedule, key: str):
    """Return the single schedule row with the given key."""
    matches = [r for r in schedule.rows if r.key == key]
    assert len(matches) == 1, f"expected one row {key}"
    return matches[0]


# ---------------------------------------------------------------------------
# Independent recomputes (deliberately NOT the engine's helpers)
# ---------------------------------------------------------------------------


def _months_between(start: str, current: str) -> int:
    """Whole months from ``start`` to ``current`` (independent recompute)."""
    sy, sm = (int(x) for x in start.split("-"))
    cy, cm = (int(x) for x in current.split("-"))
    return (cy - sy) * 12 + (cm - sm)


def _sl_part(total_cents: int, periods: int, k: int) -> int:
    """k-th straight-line part; the final part absorbs the remainder."""
    base = total_cents // periods
    if k == periods - 1:
        return total_cents - base * (periods - 1)
    return base


def _sl_booked_through(total_cents: int, periods: int, months: int) -> int:
    """Sum of straight-line parts for months [0, months), clamped to term."""
    n = max(0, min(months, periods))
    return sum(_sl_part(total_cents, periods, k) for k in range(n))


def _hamilton(total_cents: int, weights_bps: list[int]) -> list[int]:
    """Largest-remainder allocation, written independently of money.py."""
    assert sum(weights_bps) == 10000
    exact = [Fraction(total_cents * w, 10000) for w in weights_bps]
    floors = [int(x) for x in exact]
    leftover = total_cents - sum(floors)
    order = sorted(
        range(len(weights_bps)),
        key=lambda i: (-(exact[i] - floors[i]), i),
    )
    for i in order[:leftover]:
        floors[i] += 1
    return floors


def _half_up_monthly_interest(principal_cents: int, rate_bps: int) -> int:
    """principal * rate / 12, rounded half-up, via exact Fraction arithmetic."""
    x = Fraction(principal_cents * rate_bps, 10000 * 12)
    whole = x.numerator // x.denominator
    if x - whole >= Fraction(1, 2):
        whole += 1
    return whole


def _debits(je, entity: str, account: str, memo_prefix: str = "") -> int:
    return sum(
        ln.debit
        for ln in je.lines
        if ln.entity == entity
        and ln.account == account
        and ln.memo.startswith(memo_prefix)
    )


def _credits(je, entity: str, account: str, memo_prefix: str = "") -> int:
    return sum(
        ln.credit
        for ln in je.lines
        if ln.entity == entity
        and ln.account == account
        and ln.memo.startswith(memo_prefix)
    )


def _opening_balance(ds, entity: str, account: str) -> int:
    return sum(
        ln.debit - ln.credit
        for ln in ds.opening_tb
        if ln.entity == entity and ln.account == account
    )


# ---------------------------------------------------------------------------
# prepaid_amortization: amounts vs independent straight-line recompute
# ---------------------------------------------------------------------------

PREPAID_GRID = [(p, s, i) for p, s in GRID for i in range(4)]


def _prepaid_expected(pp, period: str) -> tuple[int, int]:
    """Return (monthly, remaining_after_entry) recomputed independently."""
    elapsed = _months_between(pp.start_period, period)
    active = 0 <= elapsed < pp.term_months
    monthly = _sl_part(pp.total_cents, pp.term_months, elapsed) if active else 0
    remaining = pp.total_cents - _sl_booked_through(
        pp.total_cents, pp.term_months, elapsed + 1
    )
    return monthly, remaining


@pytest.mark.parametrize("period,seed,idx", PREPAID_GRID)
def test_prepaid_amortization_debit_matches_independent_recompute(
    period, seed, idx
) -> None:
    ds = _dataset(period, seed)
    pp = ds.prepaids()[idx]
    monthly, _ = _prepaid_expected(pp, period)
    je = _entry(_result(period, seed), "PREPAID")
    booked = _debits(je, pp.entity, pp.expense_account, f"{pp.item_id} ")
    assert booked == monthly


@pytest.mark.parametrize("period,seed,idx", PREPAID_GRID)
def test_prepaid_amortization_relief_credit_matches_recompute(
    period, seed, idx
) -> None:
    ds = _dataset(period, seed)
    pp = ds.prepaids()[idx]
    monthly, _ = _prepaid_expected(pp, period)
    je = _entry(_result(period, seed), "PREPAID")
    relieved = _credits(je, pp.entity, "1400", f"Relieve prepaid {pp.item_id}")
    assert relieved == monthly


@pytest.mark.parametrize("period,seed,idx", PREPAID_GRID)
def test_prepaid_amortization_schedule_row_recomputes(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    pp = ds.prepaids()[idx]
    monthly, remaining = _prepaid_expected(pp, period)
    row = _row(_schedule(_result(period, seed), "prepaid_amortization"), pp.item_id)
    assert row.fields["remaining"] == money.fmt(remaining)
    assert row.fields["amortized_this_period"] == money.fmt(monthly)
    assert 0 <= remaining <= pp.total_cents


@pytest.mark.parametrize("period,seed", GRID)
def test_prepaid_amortization_tie_matches_summed_recompute(period, seed) -> None:
    ds = _dataset(period, seed)
    res = _result(period, seed)
    expected = sum(_prepaid_expected(pp, period)[1] for pp in ds.prepaids())
    tie = next(t for t in res.ties if t.account == "1400")
    assert tie.expected_cents == expected
    assert tie.actual_cents == expected
    assert tie.ties and tie.variance_cents == 0


def _period_minus(period: str, months: int) -> str:
    """Return the period ``months`` before ``period`` (independent helper)."""
    y, m = (int(x) for x in period.split("-"))
    idx = y * 12 + (m - 1) - months
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


# Totals with a non-zero straight-line remainder, so the final month's
# plugged part differs from the base part: a dropped remainder cent fails
# these grids where the evenly-divisible generated data cannot.
PREPAID_BOUNDARY_TOTALS = [100001, 999999, 3599987]
PREPAID_BOUNDARY_TERMS = [12, 7]
PREPAID_BOUNDARY_KINDS = ["first_month", "mid_term", "final_month", "expired"]
PREPAID_BOUNDARY = [
    (t, n, kind)
    for t in PREPAID_BOUNDARY_TOTALS
    for n in PREPAID_BOUNDARY_TERMS
    for kind in PREPAID_BOUNDARY_KINDS
]

_BOUNDARY_PERIOD = "2026-06"


def _boundary_elapsed(term: int, kind: str) -> int:
    return {
        "first_month": 0,
        "mid_term": term // 2,
        "mid_life": term // 2,
        "final_month": term - 1,
        "expired": term,
    }[kind]


def _entry_or_none(result, suffix: str):
    """Return the register entry ending with ``suffix``, or None if unposted."""
    matches = [je for je in result.register if je.je_id.endswith(suffix)]
    assert len(matches) <= 1
    return matches[0] if matches else None


@lru_cache(maxsize=None)
def _prepaid_boundary_close(total: int, term: int, kind: str):
    elapsed = _boundary_elapsed(term, kind)
    ds = generate_dataset(_BOUNDARY_PERIOD, seed=7)
    pp = Prepaid(
        item_id="PP-X1",
        entity="MF",
        vendor="Birch Services",
        description="Boundary maintenance contract",
        expense_account="5000",
        total_cents=total,
        start_period=_period_minus(_BOUNDARY_PERIOD, elapsed),
        term_months=term,
    )
    ds.subs.prepaids = [pp]
    return pp, CloseEngine(ds).run()


@pytest.mark.parametrize("total,term,kind", PREPAID_BOUNDARY)
def test_prepaid_amortization_boundary_books_the_exact_part(
    total, term, kind
) -> None:
    pp, res = _prepaid_boundary_close(total, term, kind)
    monthly, _ = _prepaid_expected(pp, _BOUNDARY_PERIOD)
    if kind == "final_month":
        # The plugged final part must absorb the full remainder.
        assert monthly == total - (total // term) * (term - 1)
    je = _entry_or_none(res, "PREPAID")
    if kind == "expired":
        # Nothing left to amortize: the engine must not post the entry at all.
        assert monthly == 0
        assert je is None
        return
    assert je is not None
    assert _debits(je, pp.entity, pp.expense_account, "PP-X1 ") == monthly
    assert _credits(je, pp.entity, "1400", "Relieve prepaid PP-X1") == monthly


@pytest.mark.parametrize("total,term,kind", PREPAID_BOUNDARY)
def test_prepaid_amortization_boundary_remaining_recomputes(
    total, term, kind
) -> None:
    pp, res = _prepaid_boundary_close(total, term, kind)
    _, remaining = _prepaid_expected(pp, _BOUNDARY_PERIOD)
    if kind in ("final_month", "expired"):
        # Fully amortized: not a cent of the total may linger.
        assert remaining == 0
    row = _row(_schedule(res, "prepaid_amortization"), "PP-X1")
    assert row.fields["remaining"] == money.fmt(remaining)
    sched = _schedule(res, "prepaid_amortization")
    assert sched.tie_expected_cents == remaining


# ---------------------------------------------------------------------------
# depreciation: straight-line amounts, contra mirror, accumulated roll
# ---------------------------------------------------------------------------

DEPREC_GRID = [(p, s, i) for p, s in GRID for i in range(5)]


def _deprec_expected(fa, period: str) -> tuple[int, int]:
    """Return (monthly, accumulated_through_period) independently."""
    elapsed = _months_between(fa.in_service_period, period)
    active = 0 <= elapsed < fa.useful_life_months
    monthly = (
        _sl_part(fa.cost_cents, fa.useful_life_months, elapsed) if active else 0
    )
    accum = _sl_booked_through(fa.cost_cents, fa.useful_life_months, elapsed + 1)
    return monthly, accum


@pytest.mark.parametrize("period,seed,idx", DEPREC_GRID)
def test_depreciation_expense_matches_independent_recompute(
    period, seed, idx
) -> None:
    ds = _dataset(period, seed)
    fa = ds.fixed_assets()[idx]
    monthly, _ = _deprec_expected(fa, period)
    je = _entry(_result(period, seed), "DEPREC")
    booked = _debits(je, fa.entity, "6100", f"{fa.asset_id} ")
    assert booked == monthly


@pytest.mark.parametrize("period,seed,idx", DEPREC_GRID)
def test_depreciation_contra_credit_mirrors_expense(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    fa = ds.fixed_assets()[idx]
    monthly, _ = _deprec_expected(fa, period)
    je = _entry(_result(period, seed), "DEPREC")
    accum_credit = _credits(je, fa.entity, "1510", f"Accum. dep. {fa.asset_id}")
    assert accum_credit == monthly


@pytest.mark.parametrize("period,seed,idx", DEPREC_GRID)
def test_depreciation_schedule_accum_and_nbv_recompute(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    fa = ds.fixed_assets()[idx]
    monthly, accum = _deprec_expected(fa, period)
    row = _row(_schedule(_result(period, seed), "depreciation"), fa.asset_id)
    assert row.fields["accum_dep"] == money.fmt(accum)
    assert row.fields["net_book_value"] == money.fmt(fa.cost_cents - accum)
    assert row.fields["depr_this_period"] == money.fmt(monthly)
    assert 0 <= accum <= fa.cost_cents


# Costs with a non-zero straight-line remainder plus end-of-life boundaries
# the generated mid-life assets never reach.
DEPREC_BOUNDARY_COSTS = [100000, 1000001, 3599999]
DEPREC_BOUNDARY_LIVES = [36, 48]
DEPREC_BOUNDARY_KINDS = ["first_month", "mid_life", "final_month", "expired"]
DEPREC_BOUNDARY = [
    (c, life, kind)
    for c in DEPREC_BOUNDARY_COSTS
    for life in DEPREC_BOUNDARY_LIVES
    for kind in DEPREC_BOUNDARY_KINDS
]


@lru_cache(maxsize=None)
def _deprec_boundary_close(cost: int, life: int, kind: str):
    elapsed = _boundary_elapsed(life, kind)
    ds = generate_dataset(_BOUNDARY_PERIOD, seed=7)
    fa = FixedAsset(
        asset_id="FA-X1",
        entity="BW",
        description="Boundary lab equipment",
        cost_cents=cost,
        in_service_period=_period_minus(_BOUNDARY_PERIOD, elapsed),
        useful_life_months=life,
    )
    ds.subs.fixed_assets = [fa]
    return fa, CloseEngine(ds).run()


@pytest.mark.parametrize("cost,life,kind", DEPREC_BOUNDARY)
def test_depreciation_boundary_books_the_exact_part(cost, life, kind) -> None:
    fa, res = _deprec_boundary_close(cost, life, kind)
    monthly, _ = _deprec_expected(fa, _BOUNDARY_PERIOD)
    if kind == "final_month":
        # The plugged final part must absorb the full remainder.
        assert monthly == cost - (cost // life) * (life - 1)
    je = _entry_or_none(res, "DEPREC")
    if kind == "expired":
        # A fully depreciated asset books nothing further: no entry posts.
        assert monthly == 0
        assert je is None
        return
    assert je is not None
    assert _debits(je, fa.entity, "6100", "FA-X1 ") == monthly
    assert _credits(je, fa.entity, "1510", "Accum. dep. FA-X1") == monthly


@pytest.mark.parametrize("cost,life,kind", DEPREC_BOUNDARY)
def test_depreciation_boundary_accum_never_exceeds_cost(cost, life, kind) -> None:
    fa, res = _deprec_boundary_close(cost, life, kind)
    _, accum = _deprec_expected(fa, _BOUNDARY_PERIOD)
    if kind in ("final_month", "expired"):
        assert accum == cost  # depreciated to exactly zero net book value
    row = _row(_schedule(res, "depreciation"), "FA-X1")
    assert row.fields["accum_dep"] == money.fmt(accum)
    assert row.fields["net_book_value"] == money.fmt(cost - accum)


# ---------------------------------------------------------------------------
# deferred_rent: hamilton shares, intercompany routing, movement direction
# ---------------------------------------------------------------------------

RENT_GRID = [(p, s, i) for p, s in GRID for i in range(len(ENTITY_CODES))]


def _lease_facts(ds, period: str):
    lease = ds.leases()[0]
    idx = _months_between(f"{period[:4]}-01", period)
    cash = lease.cash_rent_schedule_cents[idx]
    weights = [lease.split_bps[c] for c in ENTITY_CODES]
    rent_shares = _hamilton(lease.straight_line_cents, weights)
    cam_shares = _hamilton(lease.monthly_cam_cents, weights)
    return lease, idx, cash, rent_shares, cam_shares


@pytest.mark.parametrize("period,seed,ent_idx", RENT_GRID)
def test_deferred_rent_share_matches_independent_hamilton(
    period, seed, ent_idx
) -> None:
    ds = _dataset(period, seed)
    lease, _, _, rent_shares, _ = _lease_facts(ds, period)
    je = _entry(_result(period, seed), "LEASE")
    ent = ENTITY_CODES[ent_idx]
    assert _debits(je, ent, "6000", f"{lease.lease_id} rent share") == (
        rent_shares[ent_idx]
    )


@pytest.mark.parametrize("period,seed,ent_idx", RENT_GRID)
def test_deferred_rent_cam_share_matches_independent_hamilton(
    period, seed, ent_idx
) -> None:
    ds = _dataset(period, seed)
    lease, _, _, _, cam_shares = _lease_facts(ds, period)
    je = _entry(_result(period, seed), "LEASE")
    ent = ENTITY_CODES[ent_idx]
    assert _debits(je, ent, "6050", f"{lease.lease_id} CAM share") == (
        cam_shares[ent_idx]
    )


@pytest.mark.parametrize("period,seed,ent_idx", RENT_GRID)
def test_deferred_rent_due_to_routing_recomputes(period, seed, ent_idx) -> None:
    ds = _dataset(period, seed)
    lease, _, _, rent_shares, cam_shares = _lease_facts(ds, period)
    je = _entry(_result(period, seed), "LEASE")
    ent = ENTITY_CODES[ent_idx]
    due_to = _credits(je, ent, "2800")
    if ent == lease.entity:
        assert due_to == 0  # the holder never owes itself
    else:
        assert due_to == rent_shares[ent_idx] + cam_shares[ent_idx]


@pytest.mark.parametrize("period,seed,ent_idx", RENT_GRID)
def test_deferred_rent_entity_leg_self_balances(period, seed, ent_idx) -> None:
    je = _entry(_result(period, seed), "LEASE")
    ent = ENTITY_CODES[ent_idx]
    legs = je.balances_per_entity()
    assert ent in legs and legs[ent] == 0


@pytest.mark.parametrize("period,seed", GRID)
def test_deferred_rent_movement_and_holder_lines_recompute(period, seed) -> None:
    ds = _dataset(period, seed)
    lease, _, cash, rent_shares, cam_shares = _lease_facts(ds, period)
    je = _entry(_result(period, seed), "LEASE")
    holder = lease.entity
    hi = ENTITY_CODES.index(holder)
    delta = lease.straight_line_cents - cash
    if delta >= 0:
        assert _credits(je, holder, "2200") == delta
        assert _debits(je, holder, "1600") == 0
    else:
        assert _debits(je, holder, "1600") == -delta
        assert _credits(je, holder, "2200") == 0
    assert _credits(je, holder, "2100") == cash + lease.monthly_cam_cents
    expected_due_from = (
        lease.straight_line_cents
        - rent_shares[hi]
        + lease.monthly_cam_cents
        - cam_shares[hi]
    )
    assert _debits(je, holder, "1800", "Due from affiliates (lease") == (
        expected_due_from
    )


@pytest.mark.parametrize("period,seed", GRID)
def test_deferred_rent_schedule_month_and_movement_recompute(period, seed) -> None:
    ds = _dataset(period, seed)
    lease, idx, cash, _, _ = _lease_facts(ds, period)
    row = _row(_schedule(_result(period, seed), "deferred_rent_cam"), lease.lease_id)
    assert row.fields["month_index"] == str(idx + 1)
    assert row.fields["cash_rent"] == money.fmt(cash)
    assert row.fields["deferred_movement"] == money.fmt(
        lease.straight_line_cents - cash
    )


# ---------------------------------------------------------------------------
# mgmt_fee: netting arithmetic on generated and custom arrangements
# ---------------------------------------------------------------------------

MGMT_GRID = [(p, s, i) for p, s in GRID for i in range(2)]


@pytest.mark.parametrize("period,seed,idx", MGMT_GRID)
def test_mgmt_fee_expense_equals_monthly_charge(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    mf = ds.mgmt_fees()[idx]
    je = _entry(_result(period, seed), "MGMTFEE")
    booked = _debits(je, mf.payer_entity, "6200", f"{mf.arrangement_id} ")
    assert booked == mf.monthly_fee_cents


@pytest.mark.parametrize("period,seed,idx", MGMT_GRID)
def test_mgmt_fee_cash_and_payable_net_to_the_charge(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    mf = ds.mgmt_fees()[idx]
    je = _entry(_result(period, seed), "MGMTFEE")
    cash = _credits(je, mf.payer_entity, "1000", f"{mf.arrangement_id} ")
    payable = _credits(je, mf.payer_entity, "2300", f"{mf.arrangement_id} ")
    assert cash == mf.in_month_payment_cents
    assert payable == mf.monthly_fee_cents - mf.in_month_payment_cents
    assert cash + payable == mf.monthly_fee_cents


@pytest.mark.parametrize("period,seed,idx", MGMT_GRID)
def test_mgmt_fee_ledger_movement_ties_to_recompute(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    mf = ds.mgmt_fees()[idx]
    res = _result(period, seed)
    net = mf.monthly_fee_cents - mf.in_month_payment_cents
    # Only one arrangement per payer entity in the generated data.
    assert res.ledger.balance(mf.payer_entity, "2300") == -net
    assert res.ledger.balance(mf.payer_entity, "6200") == mf.monthly_fee_cents
    cash_movement = res.ledger.balance(mf.payer_entity, "1000") - _opening_balance(
        ds, mf.payer_entity, "1000"
    )
    assert cash_movement == -mf.in_month_payment_cents


MGMT_FEES_CENTS = [100000, 123457, 555555, 800000, 999999]
MGMT_PAYMENT_KINDS = ["zero", "one_cent", "half", "all_but_one", "full"]


def _mgmt_payment(fee: int, kind: str) -> int:
    return {
        "zero": 0,
        "one_cent": 1,
        "half": fee // 2,
        "all_but_one": fee - 1,
        "full": fee,
    }[kind]


MGMT_CUSTOM = [
    (fee, kind, payer)
    for fee in MGMT_FEES_CENTS
    for kind in MGMT_PAYMENT_KINDS
    for payer in ENTITY_CODES
]


@lru_cache(maxsize=None)
def _mgmt_custom_close(fee: int, payment: int, payer: str):
    ds = generate_dataset("2026-06", seed=7)
    ds.subs.mgmt_fees = [
        MgmtFee(
            arrangement_id="MGT-X1",
            payer_entity=payer,
            monthly_fee_cents=fee,
            in_month_payment_cents=payment,
        )
    ]
    return ds, CloseEngine(ds).run()


@pytest.mark.parametrize("fee,kind,payer", MGMT_CUSTOM)
def test_mgmt_fee_custom_lines_recompute(fee, kind, payer) -> None:
    payment = _mgmt_payment(fee, kind)
    _, res = _mgmt_custom_close(fee, payment, payer)
    je = _entry(res, "MGMTFEE")
    assert _debits(je, payer, "6200", "MGT-X1 ") == fee
    cash_lines = [ln for ln in je.lines if ln.account == "1000"]
    payable_lines = [ln for ln in je.lines if ln.account == "2300"]
    # Zero-amount credit lines are never booked (netting boundary).
    assert (len(cash_lines) == 1) == (payment > 0)
    assert (len(payable_lines) == 1) == (fee - payment > 0)
    assert sum(ln.credit for ln in cash_lines) == payment
    assert sum(ln.credit for ln in payable_lines) == fee - payment
    assert je.is_balanced and je.balances_per_entity()[payer] == 0


@pytest.mark.parametrize("fee,kind,payer", MGMT_CUSTOM)
def test_mgmt_fee_custom_close_stays_clean_and_ties(fee, kind, payer) -> None:
    payment = _mgmt_payment(fee, kind)
    ds, res = _mgmt_custom_close(fee, payment, payer)
    assert res.clean
    assert res.ledger.balance(payer, "2300") == -(fee - payment)
    cash_movement = res.ledger.balance(payer, "1000") - _opening_balance(
        ds, payer, "1000"
    )
    assert cash_movement == -payment


# ---------------------------------------------------------------------------
# note_interest: half-up rounding vs exact fraction recompute, both mirrors
# ---------------------------------------------------------------------------

NOTE_GRID = [(p, s, i) for p, s in GRID for i in range(2)]


@pytest.mark.parametrize("period,seed,idx", NOTE_GRID)
def test_note_interest_borrower_lines_match_fraction_recompute(
    period, seed, idx
) -> None:
    ds = _dataset(period, seed)
    note = ds.notes()[idx]
    expected = _half_up_monthly_interest(note.principal_cents, note.annual_rate_bps)
    je = _entry(_result(period, seed), "INTEREST")
    assert _debits(je, note.borrower_entity, "6300", f"{note.note_id} ") == expected
    assert _credits(je, note.borrower_entity, "2400", f"{note.note_id} ") == expected


@pytest.mark.parametrize("period,seed,idx", NOTE_GRID)
def test_note_interest_lender_mirror_matches_fraction_recompute(
    period, seed, idx
) -> None:
    ds = _dataset(period, seed)
    note = ds.notes()[idx]
    expected = _half_up_monthly_interest(note.principal_cents, note.annual_rate_bps)
    je = _entry(_result(period, seed), "INTEREST")
    assert _debits(je, note.lender_entity, "1800", f"{note.note_id} ") == expected
    assert _credits(je, note.lender_entity, "4900", f"{note.note_id} ") == expected


@pytest.mark.parametrize("period,seed,idx", NOTE_GRID)
def test_note_interest_schedule_amount_recomputes(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    note = ds.notes()[idx]
    expected = _half_up_monthly_interest(note.principal_cents, note.annual_rate_bps)
    row = _row(_schedule(_result(period, seed), "note_interest"), note.note_id)
    assert row.fields["monthly_interest"] == money.fmt(expected)
    assert row.fields["principal"] == money.fmt(note.principal_cents)


@pytest.mark.parametrize("period,seed,idx", NOTE_GRID)
def test_note_interest_entity_legs_self_balance(period, seed, idx) -> None:
    ds = _dataset(period, seed)
    note = ds.notes()[idx]
    je = _entry(_result(period, seed), "INTEREST")
    legs = je.balances_per_entity()
    assert legs[note.borrower_entity] == 0
    assert legs[note.lender_entity] == 0


# Principals and rates chosen to sit on and around the half-cent boundary:
# 100 cents at 600 bps is exactly half a cent per month (rounds UP to 1);
# 99 cents at 600 bps is just below (rounds DOWN to 0).
NOTE_PRINCIPALS = [1, 99, 100, 999, 100001, 33333333, 49999999, 123456789]
NOTE_RATES_BPS = [1, 425, 600, 999, 1200]
NOTE_CUSTOM = [(p, r) for p in NOTE_PRINCIPALS for r in NOTE_RATES_BPS]


@lru_cache(maxsize=None)
def _note_custom_close(principal: int, rate_bps: int):
    ds = generate_dataset("2026-06", seed=7)
    ds.subs.notes = [
        Note(
            note_id="NOTE-X1",
            lender_entity="DH",
            borrower_entity="MF",
            principal_cents=principal,
            annual_rate_bps=rate_bps,
        )
    ]
    return CloseEngine(ds).run()


@pytest.mark.parametrize("principal,rate_bps", NOTE_CUSTOM)
def test_note_interest_custom_rounds_half_up_exactly(principal, rate_bps) -> None:
    expected = _half_up_monthly_interest(principal, rate_bps)
    res = _note_custom_close(principal, rate_bps)
    je = _entry(res, "INTEREST")
    assert _debits(je, "MF", "6300", "NOTE-X1 ") == expected
    assert _credits(je, "MF", "2400", "NOTE-X1 ") == expected
    assert _debits(je, "DH", "1800", "NOTE-X1 ") == expected
    assert _credits(je, "DH", "4900", "NOTE-X1 ") == expected


@pytest.mark.parametrize("principal,rate_bps", NOTE_CUSTOM)
def test_note_interest_custom_close_stays_clean(principal, rate_bps) -> None:
    expected = _half_up_monthly_interest(principal, rate_bps)
    res = _note_custom_close(principal, rate_bps)
    assert res.clean
    assert res.ledger.balance("MF", "2400") == -expected
    assert res.ledger.balance("DH", "4900") == -expected


# ---------------------------------------------------------------------------
# gna_allocation: hamilton shares, pool relief, refusal boundaries
# ---------------------------------------------------------------------------

GNA_GRID = [(p, s, i) for p, s in GRID for i in range(len(ENTITY_CODES))]


@pytest.mark.parametrize("period,seed,ent_idx", GNA_GRID)
def test_gna_share_matches_independent_hamilton(period, seed, ent_idx) -> None:
    ds = _dataset(period, seed)
    gna = ds.gna()
    weights = [gna.split_bps[c] for c in ENTITY_CODES]
    shares = _hamilton(gna.monthly_pool_cents, weights)
    je = _entry(_result(period, seed), "GNA")
    ent = ENTITY_CODES[ent_idx]
    assert _debits(je, ent, "6600", "Allocated G&A share") == shares[ent_idx]


@pytest.mark.parametrize("period,seed,ent_idx", GNA_GRID)
def test_gna_routing_and_pool_relief_recompute(period, seed, ent_idx) -> None:
    ds = _dataset(period, seed)
    gna = ds.gna()
    weights = [gna.split_bps[c] for c in ENTITY_CODES]
    shares = _hamilton(gna.monthly_pool_cents, weights)
    je = _entry(_result(period, seed), "GNA")
    ent = ENTITY_CODES[ent_idx]
    if ent == gna.pool_entity:
        assert _credits(je, ent, "6650") == gna.monthly_pool_cents
        assert _debits(je, ent, "1800", "Due from affiliates (G&A") == (
            gna.monthly_pool_cents - shares[ent_idx]
        )
        assert _credits(je, ent, "2800") == 0
    else:
        assert _credits(je, ent, "2800") == shares[ent_idx]
        assert _credits(je, ent, "6650") == 0


@pytest.mark.parametrize("period,seed", GRID)
def test_gna_allocated_expense_conserves_the_pool(period, seed) -> None:
    ds = _dataset(period, seed)
    gna = ds.gna()
    res = _result(period, seed)
    je = _entry(res, "GNA")
    assert sum(ln.debit for ln in je.lines if ln.account == "6600") == (
        gna.monthly_pool_cents
    )
    assert res.ledger.account_balance("6600") == gna.monthly_pool_cents


GNA_SPLITS = [
    {"DH": 4000, "MF": 3500, "BW": 2500},
    {"DH": 10000, "MF": 0, "BW": 0},
    {"DH": 0, "MF": 5000, "BW": 5000},
    {"DH": 9999, "MF": 1, "BW": 0},
    {"DH": 3333, "MF": 3333, "BW": 3334},
    {"DH": 1, "MF": 1, "BW": 9998},
    {"DH": 2500, "MF": 2500, "BW": 5000},
    {"DH": 6, "MF": 6, "BW": 9988},
]
GNA_POOLS = [1, 999999, 1500001]
GNA_CUSTOM = [
    (si, pool) for si in range(len(GNA_SPLITS)) for pool in GNA_POOLS
]


@lru_cache(maxsize=None)
def _gna_custom_close(split_idx: int, pool: int):
    ds = generate_dataset("2026-06", seed=7)
    ds.subs.gna = GnaAllocation(
        pool_entity="DH",
        monthly_pool_cents=pool,
        split_bps=dict(GNA_SPLITS[split_idx]),
    )
    return CloseEngine(ds).run()


@pytest.mark.parametrize(
    "split_idx,pool,ent_idx",
    [(si, pool, i) for si, pool in GNA_CUSTOM for i in range(len(ENTITY_CODES))],
)
def test_gna_custom_split_share_matches_hamilton(split_idx, pool, ent_idx) -> None:
    weights = [GNA_SPLITS[split_idx][c] for c in ENTITY_CODES]
    shares = _hamilton(pool, weights)
    je = _entry(_gna_custom_close(split_idx, pool), "GNA")
    ent = ENTITY_CODES[ent_idx]
    assert _debits(je, ent, "6600", "Allocated G&A share") == shares[ent_idx]


@pytest.mark.parametrize("split_idx,pool", GNA_CUSTOM)
def test_gna_custom_split_conserves_and_stays_clean(split_idx, pool) -> None:
    res = _gna_custom_close(split_idx, pool)
    assert res.clean
    je = _entry(res, "GNA")
    assert sum(ln.debit for ln in je.lines if ln.account == "6600") == pool
    assert sum(ln.credit for ln in je.lines if ln.account == "6650") == pool
    assert je.is_balanced


GNA_BAD_SPLITS = [
    ("short_of_100pct", {"DH": 4000, "MF": 3500, "BW": 2499}),
    ("over_100pct", {"DH": 4000, "MF": 3500, "BW": 2501}),
    ("outside_entity", {"DH": 4000, "MF": 3500, "XX": 2500}),
    ("empty_map", {}),
]
GNA_BAD_GRID = [
    (name, p, s)
    for name, _ in GNA_BAD_SPLITS
    for p in ["2026-03", "2026-08"]
    for s in [3, 42]
]
GNA_BAD_BY_NAME = dict(GNA_BAD_SPLITS)


@pytest.mark.parametrize("bad_name,period,seed", GNA_BAD_GRID)
def test_gna_invalid_split_is_refused_not_posted(bad_name, period, seed) -> None:
    ds = generate_dataset(period, seed=seed)
    ds.subs.gna = GnaAllocation(
        pool_entity="DH",
        monthly_pool_cents=1500000,
        split_bps=dict(GNA_BAD_BY_NAME[bad_name]),
    )
    res = CloseEngine(ds).run()
    assert not res.clean
    assert not any(je.category == "gna_allocation" for je in res.register)
    refusal = next(
        r for r in res.refused if r.je.category == "gna_allocation"
    )
    assert "split_bps" in refusal.detail
    # The other seven recurring entries still post: a bad split never
    # cascades into a crash or blocks unrelated categories.
    assert len(res.register) == 7


# ---------------------------------------------------------------------------
# sentinel_controls: C1 fires on a one-cent tamper of EREDACTED register entry
# ---------------------------------------------------------------------------

SENTINEL_GRID = [
    (p, s, i)
    for p in ["2026-03", "2026-08"]
    for s in SEEDS
    for i in range(8)
]


@pytest.mark.parametrize("period,seed,entry_idx", SENTINEL_GRID)
def test_sentinel_control_c1_fires_on_a_one_cent_tamper_of_each_entry(
    period, seed, entry_idx
) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = res.register[entry_idx]
    debit_idx = next(i for i, ln in enumerate(je.lines) if ln.debit)
    line = je.lines[debit_idx]
    je.lines[debit_idx] = replace(line, debit=line.debit + 1)
    findings = c1_re_balance(_dataset(period, seed), res)
    assert any(
        f.severity is Severity.CRITICAL and je.je_id in f.detail
        for f in findings
    )
    # Silence boundary: the untampered close raises nothing from C1.
    assert c1_re_balance(_dataset(period, seed), _result(period, seed)) == []
