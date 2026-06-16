"""Tests for the close engine: JE balance, math, allocation, tie-out, roll."""

from __future__ import annotations

from close_engine import money
from close_engine.engine import CloseEngine
from close_engine.generate import (
    GnaAllocation,
    Prepaid,
    FixedAsset,
    generate_dataset,
    months_elapsed,
)
from close_engine.model import JournalEntry, JournalLine, Ledger, OutOfTieError


PERIOD = "2026-03"


def _run(period: str = PERIOD, seed: int = 2026):
    return CloseEngine(generate_dataset(period, seed=seed)).run()


# --------------------------------------------------------------------------- #
# Every JE balances (aggregate AND per entity)
# --------------------------------------------------------------------------- #


def test_every_posted_entry_balances() -> None:
    result = _run()
    assert result.register, "expected entries to be posted"
    for je in result.register:
        assert je.is_balanced, f"{je.je_id} not balanced"
        # Each entity leg must self-balance too (intercompany correctness).
        for entity, diff in je.balances_per_entity().items():
            assert diff == 0, f"{je.je_id} entity {entity} off by {diff}"


def test_trial_balance_is_in_balance() -> None:
    result = _run()
    debits, credits = result.ledger.total_debits_credits()
    assert debits == credits


def test_nothing_refused_on_clean_run() -> None:
    result = _run()
    assert result.refused == []
    assert result.clean


# --------------------------------------------------------------------------- #
# Prepaid amortization math
# --------------------------------------------------------------------------- #


def test_prepaid_amortization_is_straight_line() -> None:
    result = _run()
    prepaid_je = next(
        je for je in result.register if je.category == "prepaid_amortization"
    )
    # Debits (expense) equal credits (relief of 1400) and are positive.
    assert prepaid_je.total_debits == prepaid_je.total_credits > 0
    # Every credit line hits the prepaid asset account.
    credit_accts = {ln.account for ln in prepaid_je.lines if ln.credit}
    assert credit_accts == {"1400"}


def test_prepaid_monthly_equals_total_over_term() -> None:
    pp = Prepaid(
        item_id="PP-X",
        entity="DH",
        vendor="Demo Co.",
        description="annual",
        expense_account="6400",
        total_cents=money.to_cents(12000),
        start_period="2026-01",
        term_months=12,
    )
    engine = CloseEngine(generate_dataset("2026-06", seed=1))
    engine.period = "2026-06"
    monthly = engine._prepaid_monthly(pp)
    assert monthly == money.to_cents(1000)  # 12,000 / 12


def test_prepaid_not_amortized_after_term_ends() -> None:
    pp = Prepaid(
        item_id="PP-Y",
        entity="DH",
        vendor="Demo Co.",
        description="short",
        expense_account="6400",
        total_cents=money.to_cents(6000),
        start_period="2025-01",
        term_months=6,
    )
    engine = CloseEngine(generate_dataset("2026-03", seed=1))
    engine.period = "2026-03"  # long after the 6-month term
    assert engine._prepaid_monthly(pp) == 0
    assert engine._prepaid_remaining(pp) == 0


# --------------------------------------------------------------------------- #
# Depreciation math
# --------------------------------------------------------------------------- #


def test_depreciation_is_straight_line() -> None:
    fa = FixedAsset(
        asset_id="FA-X",
        entity="DH",
        description="equipment",
        cost_cents=money.to_cents(48000),
        in_service_period="2026-01",
        useful_life_months=48,
    )
    engine = CloseEngine(generate_dataset("2026-03", seed=1))
    engine.period = "2026-03"
    monthly = engine._depreciation_monthly(fa)
    assert monthly == money.to_cents(1000)  # 48,000 / 48
    # After 3 months in service (Jan, Feb, Mar) accumulated = 3 * 1000.
    assert engine._accumulated_depreciation(fa) == money.to_cents(3000)


def test_depreciation_stops_at_end_of_life() -> None:
    fa = FixedAsset(
        asset_id="FA-Z",
        entity="DH",
        description="old",
        cost_cents=money.to_cents(36000),
        in_service_period="2020-01",
        useful_life_months=36,
    )
    engine = CloseEngine(generate_dataset("2026-03", seed=1))
    engine.period = "2026-03"
    assert engine._depreciation_monthly(fa) == 0
    # Fully depreciated: accumulated == cost.
    assert engine._accumulated_depreciation(fa) == fa.cost_cents


# --------------------------------------------------------------------------- #
# Allocation ratios sum to 100%
# --------------------------------------------------------------------------- #


def test_gna_split_sums_to_100_percent() -> None:
    result = _run()
    from close_engine.generate import generate_dataset as gd

    gna = gd(PERIOD).gna()
    assert sum(gna.split_bps.values()) == 10000  # 100.00%


def test_lease_split_sums_to_100_percent() -> None:
    from close_engine.generate import generate_dataset as gd

    for lease in gd(PERIOD).leases():
        assert sum(lease.split_bps.values()) == 10000


def test_gna_allocation_distributes_full_pool() -> None:
    result = _run()
    gna_je = next(je for je in result.register if je.category == "gna_allocation")
    # Allocated G&A (6600) debits across entities equal the pool relieved (6650).
    allocated = sum(ln.debit for ln in gna_je.lines if ln.account == "6600")
    relieved = sum(ln.credit for ln in gna_je.lines if ln.account == "6650")
    assert allocated == relieved
    from close_engine.generate import generate_dataset as gd

    assert allocated == gd(PERIOD).gna().monthly_pool_cents


def test_gna_allocation_rejected_when_ratios_do_not_sum_to_100() -> None:
    """A bad allocation map raises before any out-of-tie entry can post."""
    import pytest

    ds = generate_dataset(PERIOD)
    # Corrupt the split so it no longer sums to 10000 bps.
    ds.subs.gna = GnaAllocation(
        pool_entity="DH",
        monthly_pool_cents=money.to_cents(15000),
        split_bps={"DH": 4000, "MF": 3500, "BW": 2000},  # sums to 9500
    )
    with pytest.raises(ValueError):
        CloseEngine(ds).run()


# --------------------------------------------------------------------------- #
# Note interest accrual
# --------------------------------------------------------------------------- #


def test_note_interest_monthly_amount() -> None:
    result = _run()
    interest_je = next(
        je for je in result.register if je.category == "note_interest"
    )
    # NOTE-01: principal 500,000 @ 6.00% -> 30,000/yr -> 2,500/mo.
    bw_interest = sum(
        ln.debit
        for ln in interest_je.lines
        if ln.entity == "BW" and ln.account == "6300"
    )
    assert bw_interest == money.to_cents(2500)


def test_note_interest_lender_and_borrower_mirror() -> None:
    result = _run()
    interest_je = next(
        je for je in result.register if je.category == "note_interest"
    )
    # Total interest expense (borrowers) equals total interest income (lenders).
    exp = sum(ln.debit for ln in interest_je.lines if ln.account == "6300")
    inc = sum(ln.credit for ln in interest_je.lines if ln.account == "4900")
    assert exp == inc


# --------------------------------------------------------------------------- #
# Management-fee accrual netting
# --------------------------------------------------------------------------- #


def test_mgmt_fee_nets_in_month_payment() -> None:
    result = _run()
    mf_je = next(je for je in result.register if je.category == "mgmt_fee_accrual")
    # BW MGT-01: fee 8,000, paid 3,000 -> expense 8,000, cash -3,000, payable 5,000.
    bw_expense = sum(
        ln.debit for ln in mf_je.lines if ln.entity == "BW" and ln.account == "6200"
    )
    bw_cash = sum(
        ln.credit for ln in mf_je.lines if ln.entity == "BW" and ln.account == "1000"
    )
    bw_payable = sum(
        ln.credit for ln in mf_je.lines if ln.entity == "BW" and ln.account == "2300"
    )
    assert bw_expense == money.to_cents(8000)
    assert bw_cash == money.to_cents(3000)
    assert bw_payable == money.to_cents(5000)


# --------------------------------------------------------------------------- #
# Out-of-tie detection
# --------------------------------------------------------------------------- #


def test_engine_refuses_out_of_tie_entry() -> None:
    """The engine captures (does not raise) an out-of-tie entry as refused."""
    ds = generate_dataset(PERIOD)
    engine = CloseEngine(ds)
    engine.ledger.load_opening(ds.opening_tb)
    bad = JournalEntry(
        "JE-BAD",
        PERIOD,
        "test",
        "deliberately unbalanced",
        [
            JournalLine("DH", "6100", 1000, 0, "expense"),
            JournalLine("DH", "1510", 0, 950, "short credit"),
        ],
    )
    engine._post(bad)
    assert bad not in engine.register
    assert len(engine.refused) == 1
    assert engine.refused[0].je.je_id == "JE-BAD"


def test_ledger_post_raises_out_of_tie_error() -> None:
    import pytest

    ledger = Ledger(generate_dataset(PERIOD).coa)
    bad = JournalEntry(
        "JE-BAD2",
        PERIOD,
        "test",
        "unbalanced",
        [JournalLine("DH", "6100", 100, 0, "x")],
    )
    with pytest.raises(OutOfTieError):
        ledger.post(bad)


# --------------------------------------------------------------------------- #
# Tie-out
# --------------------------------------------------------------------------- #


def test_prepaid_schedule_ties_to_gl() -> None:
    result = _run()
    prepaid_tie = next(t for t in result.ties if t.account == "1400")
    assert prepaid_tie.ties
    assert prepaid_tie.variance_cents == 0


def test_all_schedules_tie() -> None:
    result = _run()
    assert result.all_tie


# --------------------------------------------------------------------------- #
# Period roll-forward / determinism
# --------------------------------------------------------------------------- #


def test_period_roll_forward_changes_amortization_progress() -> None:
    """Rolling the period forward advances schedules deterministically."""
    march = _run("2026-03")
    april = _run("2026-04")
    # Remaining prepaid balance must not increase month over month.
    march_tie = next(t for t in march.ties if t.account == "1400")
    april_tie = next(t for t in april.ties if t.account == "1400")
    assert april_tie.expected_cents <= march_tie.expected_cents
    # Both still tie to their own GL.
    assert march_tie.ties and april_tie.ties


def test_determinism_same_seed_same_result() -> None:
    a = _run("2026-03", seed=2026)
    b = _run("2026-03", seed=2026)
    # Same register: identical JE ids, totals, and line counts.
    assert [je.je_id for je in a.register] == [je.je_id for je in b.register]
    assert [je.total_debits for je in a.register] == [
        je.total_debits for je in b.register
    ]
    assert a.ledger.total_debits_credits() == b.ledger.total_debits_credits()


def test_different_seed_changes_generated_data() -> None:
    a = _run("2026-03", seed=2026)
    b = _run("2026-03", seed=99)
    # Opening balances differ, so the trial-balance totals should differ.
    assert a.ledger.total_debits_credits() != b.ledger.total_debits_credits()


def test_months_elapsed_helper() -> None:
    assert months_elapsed("2026-01", "2026-01") == 0
    assert months_elapsed("2026-01", "2026-03") == 2
    assert months_elapsed("2025-12", "2026-01") == 1
    assert months_elapsed("2026-03", "2026-01") == -2
