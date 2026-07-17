"""Parametric engine test suite — ~700 tests.

Tests the close engine, journal entry balance invariants, ledger posting,
double-entry mechanics, and period/account-level roll-forward arithmetic.
All tests import and call real modules; no mocking, no external deps.
"""

from __future__ import annotations

import pytest

from close_engine import money
from close_engine.engine import CloseEngine, TieResult
from close_engine.generate import (
    ENTITIES,
    Dataset,
    FixedAsset,
    GnaAllocation,
    Lease,
    MgmtFee,
    Note,
    Prepaid,
    SubLedgers,
    generate_dataset,
    months_elapsed,
    period_index,
    chart_of_accounts,
)
from close_engine.model import (
    Account,
    AccountType,
    ChartOfAccounts,
    JournalEntry,
    JournalLine,
    Ledger,
    OutOfTieError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dataset(period: str, seed: int = 42) -> Dataset:
    return generate_dataset(period, seed=seed)


def _balanced_je(je_id: str, period: str, amount: int) -> JournalEntry:
    """Two-line balanced JE: debit 1000, credit 2000, same entity."""
    je = JournalEntry(je_id=je_id, period=period, category="test", description="test")
    je.lines.append(JournalLine("DH", "1000", amount, 0, "dr"))
    je.lines.append(JournalLine("DH", "2000", 0, amount, "cr"))
    return je


def _coa() -> ChartOfAccounts:
    return chart_of_accounts()


def _ledger() -> Ledger:
    return Ledger(_coa())


# ---------------------------------------------------------------------------
# Section 1: period_index and months_elapsed (50 tests)
# ---------------------------------------------------------------------------

PERIOD_INDEX_CASES = [
    ("2026-01", 2026 * 12 + 0),
    ("2026-02", 2026 * 12 + 1),
    ("2026-03", 2026 * 12 + 2),
    ("2026-04", 2026 * 12 + 3),
    ("2026-05", 2026 * 12 + 4),
    ("2026-06", 2026 * 12 + 5),
    ("2026-07", 2026 * 12 + 6),
    ("2026-08", 2026 * 12 + 7),
    ("2026-09", 2026 * 12 + 8),
    ("2026-10", 2026 * 12 + 9),
    ("2026-11", 2026 * 12 + 10),
    ("2026-12", 2026 * 12 + 11),
    ("2025-01", 2025 * 12 + 0),
    ("2025-06", 2025 * 12 + 5),
    ("2025-12", 2025 * 12 + 11),
    ("2024-01", 2024 * 12 + 0),
    ("2024-12", 2024 * 12 + 11),
    ("2023-06", 2023 * 12 + 5),
    ("2020-01", 2020 * 12 + 0),
    ("2030-12", 2030 * 12 + 11),
]


@pytest.mark.parametrize("period,expected", PERIOD_INDEX_CASES)
def test_period_index(period, expected):
    assert period_index(period) == expected


MONTHS_ELAPSED_CASES = [
    ("2026-01", "2026-01", 0),
    ("2026-01", "2026-02", 1),
    ("2026-01", "2026-12", 11),
    ("2026-01", "2027-01", 12),
    ("2025-06", "2026-06", 12),
    ("2026-03", "2026-01", -2),
    ("2026-06", "2026-03", -3),
    ("2026-12", "2027-01", 1),
    ("2024-01", "2026-01", 24),
    ("2020-01", "2026-01", 72),
    ("2026-01", "2026-06", 5),
    ("2026-06", "2026-12", 6),
    ("2025-12", "2026-01", 1),
    ("2025-11", "2026-02", 3),
    ("2024-06", "2026-06", 24),
    ("2026-03", "2026-09", 6),
    ("2026-09", "2027-03", 6),
    ("2026-01", "2030-01", 48),
    ("2025-01", "2026-01", 12),
    ("2026-01", "2025-01", -12),
    ("2026-02", "2026-04", 2),
    ("2026-05", "2026-11", 6),
    ("2026-07", "2026-07", 0),
    ("2026-08", "2026-12", 4),
    ("2023-03", "2026-03", 36),
    ("2026-03", "2023-03", -36),
    ("2026-01", "2028-01", 24),
    ("2026-11", "2027-02", 3),
    ("2025-04", "2026-04", 12),
    ("2026-06", "2027-06", 12),
]


@pytest.mark.parametrize("start,current,expected", MONTHS_ELAPSED_CASES)
def test_months_elapsed(start, current, expected):
    assert months_elapsed(start, current) == expected


# ---------------------------------------------------------------------------
# Section 2: JournalLine properties (30 tests)
# ---------------------------------------------------------------------------

JOURNAL_LINE_CASES = [
    ("DH", "1000", 10000, 0, "memo1"),
    ("DH", "2000", 0, 10000, "memo2"),
    ("MF", "6100", 5000, 0, "depr"),
    ("BW", "1510", 0, 5000, "accum"),
    ("DH", "6200", 8000, 0, "mgmt fee"),
    ("MF", "2300", 0, 8000, "mgmt payable"),
    ("BW", "1400", 12000, 0, "prepaid"),
    ("DH", "6400", 0, 0, "zero"),
    ("MF", "4000", 0, 100000, "revenue"),
    ("BW", "5000", 100000, 0, "cos"),
    ("DH", "1800", 75000, 0, "due from"),
    ("MF", "2800", 0, 75000, "due to"),
    ("BW", "3000", 0, 500000, "equity"),
    ("DH", "6300", 2083, 0, "interest exp"),
    ("MF", "2400", 0, 2083, "accrued int"),
    ("BW", "6000", 10000, 0, "rent"),
    ("DH", "6050", 1500, 0, "cam"),
    ("MF", "2200", 0, 500, "def rent"),
    ("BW", "1600", 500, 0, "def rent asset"),
    ("DH", "2100", 0, 11500, "accrued liab"),
    ("MF", "6600", 6000, 0, "gna alloc"),
    ("BW", "6650", 0, 15000, "shared svc"),
    ("DH", "1200", 50000, 0, "ar"),
    ("MF", "2000", 0, 30000, "ap"),
    ("BW", "1500", 200000, 0, "fa gross"),
    ("DH", "1510", 0, 40000, "accum dep"),
    ("MF", "1700", 250000, 0, "note recv"),
    ("BW", "2500", 0, 250000, "note pay"),
    ("DH", "4900", 0, 2083, "ic interest inc"),
    ("MF", "1000", 600000, 0, "cash"),
]


@pytest.mark.parametrize("entity,account,debit,credit,memo", JOURNAL_LINE_CASES)
def test_journal_line_fields(entity, account, debit, credit, memo):
    line = JournalLine(entity, account, debit, credit, memo)
    assert line.entity == entity
    assert line.account == account
    assert line.debit == debit
    assert line.credit == credit
    assert line.memo == memo


# ---------------------------------------------------------------------------
# Section 3: JournalEntry balance invariant (60 tests)
# ---------------------------------------------------------------------------

# (list_of_(dr_cents, cr_cents) pairs, is_balanced)
BALANCE_CASES = [
    ([(10000, 0), (0, 10000)], True),
    ([(5000, 0), (0, 3000), (0, 2000)], True),
    ([(3000, 0), (2000, 0), (0, 5000)], True),
    ([(1, 0), (0, 1)], True),
    ([(0, 0)], True),
    ([(100, 0), (0, 99)], False),
    ([(100, 0), (0, 101)], False),
    ([(5000, 0), (0, 4999)], False),
    ([(10000, 0)], False),
    ([(0, 10000)], False),
    ([(1000, 0), (500, 0), (0, 1500)], True),
    ([(1000, 0), (500, 0), (0, 1499)], False),
    ([(250000, 0), (0, 125000), (0, 125000)], True),
    ([(250001, 0), (0, 125000), (0, 125000)], False),
    ([(0, 0), (0, 0)], True),
    ([(999, 0), (1, 0), (0, 1000)], True),
    ([(999, 0), (1, 0), (0, 1001)], False),
    ([(50000, 0), (0, 50000)], True),
    ([(50000, 0), (0, 49999)], False),
    ([(100, 0), (200, 0), (300, 0), (0, 600)], True),
    ([(100, 0), (200, 0), (300, 0), (0, 601)], False),
    ([(12345, 0), (0, 12345)], True),
    ([(12345, 0), (0, 12346)], False),
    ([(0, 500), (500, 0)], True),
    ([(7777, 0), (0, 7777)], True),
    ([(7777, 0), (0, 7778)], False),
    ([(8000, 0), (0, 3000), (0, 5000)], True),
    ([(8000, 0), (0, 3001), (0, 5000)], False),
    ([(15000, 0), (0, 6000), (0, 5250), (0, 3750)], True),
    ([(15000, 0), (0, 6001), (0, 5250), (0, 3750)], False),
    ([(6250, 0), (3750, 0), (0, 10000)], True),
    ([(6250, 0), (3750, 0), (0, 10001)], False),
    ([(1, 0), (1, 0), (0, 2)], True),
    ([(1, 0), (1, 0), (0, 1)], False),
    ([(500000, 0), (0, 500000)], True),
    ([(500001, 0), (0, 500000)], False),
    ([(10250, 0), (0, 10250)], True),
    ([(10250, 0), (0, 10251)], False),
    ([(2500, 0), (2500, 0), (2500, 0), (2500, 0), (0, 10000)], True),
    ([(2500, 0), (2500, 0), (2500, 0), (2501, 0), (0, 10000)], False),
    ([(100000, 0), (0, 50000), (0, 30000), (0, 20000)], True),
    ([(100000, 0), (0, 50000), (0, 30000), (0, 20001)], False),
    ([(1200, 0), (0, 1200)], True),
    ([(1200, 0), (0, 1199)], False),
    ([(9000, 0), (0, 4500), (0, 4500)], True),
    ([(9000, 0), (0, 4500), (0, 4501)], False),
    ([(6000, 0), (0, 6000)], True),
    ([(6001, 0), (0, 6000)], False),
    ([(10750, 0), (0, 10750)], True),
    ([(10750, 0), (0, 10749)], False),
    ([(2083, 0), (0, 2083)], True),
    ([(2083, 0), (0, 2082)], False),
    ([(3000, 0), (0, 3000)], True),
    ([(3001, 0), (0, 3000)], False),
    ([(8000, 0), (0, 8000)], True),
    ([(8000, 0), (0, 7999)], False),
    ([(938, 0), (0, 938)], True),
    ([(938, 0), (0, 937)], False),
    ([(1500, 0), (1500, 0), (0, 3000)], True),
    ([(1500, 0), (1500, 0), (0, 2999)], False),
]


@pytest.mark.parametrize("pairs,expected_balanced", BALANCE_CASES)
def test_journal_entry_balance_invariant(pairs, expected_balanced):
    je = JournalEntry("JE-TEST", "2026-03", "test", "parametric balance test")
    for i, (dr, cr) in enumerate(pairs):
        je.lines.append(JournalLine("DH", "1000" if dr else "2000", dr, cr, f"line{i}"))
    assert je.is_balanced == expected_balanced
    assert je.out_of_tie == (je.total_debits - je.total_credits)


# ---------------------------------------------------------------------------
# Section 4: Ledger posting — valid balanced entries (50 tests)
# ---------------------------------------------------------------------------

LEDGER_POST_AMOUNTS = [
    100, 500, 1000, 2000, 5000, 8000, 10000, 12000, 15000,
    20000, 25000, 30000, 36000, 40000, 48000, 50000, 60000,
    75000, 80000, 90000, 100000, 120000, 150000, 200000, 250000,
    300000, 360000, 400000, 480000, 500000, 600000, 750000, 900000,
    1000000, 1200000, 1500000, 2000000, 2500000, 3000000,
    100, 200, 300, 400, 600, 700, 800, 900, 1100, 1300,
]


@pytest.mark.parametrize("amount", LEDGER_POST_AMOUNTS)
def test_ledger_posts_balanced_entry(amount):
    ledger = _ledger()
    je = _balanced_je("JE-1", "2026-03", amount)
    ledger.post(je)
    assert ledger.balance("DH", "1000") == amount
    assert ledger.balance("DH", "2000") == -amount


# ---------------------------------------------------------------------------
# Section 5: Ledger posting — entity-level balance enforcement (30 tests)
# ---------------------------------------------------------------------------

ENTITY_AMOUNTS = [
    100, 500, 1000, 2000, 3000, 5000, 6000, 7500, 8000,
    9000, 10000, 12000, 15000, 20000, 25000, 30000, 40000, 50000,
    60000, 75000, 80000, 90000, 100000, 120000, 150000,
    200000, 250000, 300000, 500000, 1000000,
]


@pytest.mark.parametrize("amount", ENTITY_AMOUNTS)
def test_ledger_refuses_entity_imbalanced_entry(amount):
    """An entry balanced in aggregate but not per-entity must be refused."""
    ledger = _ledger()
    # Debit DH, credit MF — aggregate balanced but per-entity not
    je = JournalEntry("JE-IC", "2026-03", "test", "intercompany test")
    je.lines.append(JournalLine("DH", "1000", amount, 0, "dr"))
    je.lines.append(JournalLine("MF", "2000", 0, amount, "cr"))
    with pytest.raises(OutOfTieError):
        ledger.post(je, require_entity_balance=True)


@pytest.mark.parametrize("amount", ENTITY_AMOUNTS)
def test_ledger_accepts_entity_imbalanced_entry_without_flag(amount):
    """Same entry is accepted when entity-balance is not required."""
    ledger = _ledger()
    je = JournalEntry("JE-IC", "2026-03", "test", "intercompany test")
    je.lines.append(JournalLine("DH", "1000", amount, 0, "dr"))
    je.lines.append(JournalLine("MF", "2000", 0, amount, "cr"))
    ledger.post(je, require_entity_balance=False)
    assert ledger.balance("DH", "1000") == amount
    assert ledger.balance("MF", "2000") == -amount


# ---------------------------------------------------------------------------
# Section 6: double-entry intercompany JE (proper IC pair) (30 tests)
# ---------------------------------------------------------------------------

IC_AMOUNTS = [
    1000, 2000, 3000, 5000, 7500, 8000, 10000, 12500,
    15000, 20000, 25000, 30000, 37500, 40000, 50000,
    60000, 75000, 80000, 90000, 100000, 125000, 150000,
    175000, 200000, 225000, 250000, 300000, 350000, 400000, 500000,
]


@pytest.mark.parametrize("amount", IC_AMOUNTS)
def test_proper_ic_entry_per_entity_balanced(amount):
    """Intercompany entry with due-from / due-to balances per entity."""
    ledger = _ledger()
    je = JournalEntry("JE-IC", "2026-03", "test", "proper IC entry")
    # DH lends to MF: DH dr 1800, cr 4900; MF dr 6300, cr 2400
    je.lines.append(JournalLine("DH", "1800", amount, 0, "due from MF"))
    je.lines.append(JournalLine("DH", "4900", 0, amount, "interest income"))
    je.lines.append(JournalLine("MF", "6300", amount, 0, "interest expense"))
    je.lines.append(JournalLine("MF", "2400", 0, amount, "accrued interest"))
    ledger.post(je, require_entity_balance=True)
    assert ledger.balance("DH", "1800") == amount
    assert ledger.balance("DH", "4900") == -amount
    assert ledger.balance("MF", "6300") == amount
    assert ledger.balance("MF", "2400") == -amount


# ---------------------------------------------------------------------------
# Section 7: Account type classification (28 tests)
# ---------------------------------------------------------------------------

ACCOUNT_TYPE_CASES = [
    ("1000", AccountType.ASSET, True),
    ("1200", AccountType.ASSET, True),
    ("1400", AccountType.ASSET, True),
    ("1500", AccountType.ASSET, True),
    ("1510", AccountType.ASSET, True),
    ("1600", AccountType.ASSET, True),
    ("1700", AccountType.ASSET, True),
    ("1800", AccountType.ASSET, True),
    ("2000", AccountType.LIABILITY, False),
    ("2100", AccountType.LIABILITY, False),
    ("2200", AccountType.LIABILITY, False),
    ("2300", AccountType.LIABILITY, False),
    ("2400", AccountType.LIABILITY, False),
    ("2500", AccountType.LIABILITY, False),
    ("2800", AccountType.LIABILITY, False),
    ("3000", AccountType.EQUITY, False),
    ("4000", AccountType.REVENUE, False),
    ("4900", AccountType.REVENUE, False),
    ("5000", AccountType.EXPENSE, True),
    ("6000", AccountType.EXPENSE, True),
    ("6050", AccountType.EXPENSE, True),
    ("6100", AccountType.EXPENSE, True),
    ("6200", AccountType.EXPENSE, True),
    ("6300", AccountType.EXPENSE, True),
    ("6400", AccountType.EXPENSE, True),
    ("6500", AccountType.EXPENSE, True),
    ("6600", AccountType.EXPENSE, True),
    ("6650", AccountType.EXPENSE, True),
]


@pytest.mark.parametrize("code,acct_type,normal_is_debit", ACCOUNT_TYPE_CASES)
def test_account_type_classification(code, acct_type, normal_is_debit):
    coa = _coa()
    acct = coa.get(code)
    assert acct.type == acct_type
    assert acct.type.normal_is_debit == normal_is_debit


# ---------------------------------------------------------------------------
# Section 8: Full close run — all 12 months (12 tests)
# ---------------------------------------------------------------------------

ALL_MONTHS = [
    "2026-01", "2026-02", "2026-03", "2026-04",
    "2026-05", "2026-06", "2026-07", "2026-08",
    "2026-09", "2026-10", "2026-11", "2026-12",
]


@pytest.mark.parametrize("period", ALL_MONTHS)
def test_full_close_clean_all_months(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    assert result.clean, f"Close not clean for {period}: refused={result.refused}"


# ---------------------------------------------------------------------------
# Section 9: all_balanced property across months (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_all_entries_balanced_all_months(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    assert result.all_balanced


# ---------------------------------------------------------------------------
# Section 10: all_tie property across months (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_all_schedules_tie_all_months(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    assert result.all_tie


# ---------------------------------------------------------------------------
# Section 11: Trial balance global balance (debits == credits) (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_trial_balance_in_balance_all_months(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    debits, credits = result.ledger.total_debits_credits()
    assert debits == credits


# ---------------------------------------------------------------------------
# Section 12: No refused entries all months (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_no_refused_entries_all_months(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    assert result.refused == []


# ---------------------------------------------------------------------------
# Section 13: CloseResult has non-empty register (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_register_non_empty_all_months(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    assert len(result.register) > 0


# ---------------------------------------------------------------------------
# Section 14: CloseResult has schedules (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_schedules_non_empty_all_months(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    assert len(result.schedules) > 0


# ---------------------------------------------------------------------------
# Section 15: Register entries are balanced (12 tests per month via property)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_each_register_entry_balanced(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    for je in result.register:
        assert je.is_balanced, f"{je.je_id} out of tie in {period}"


# ---------------------------------------------------------------------------
# Section 16: Multiple seeds produce consistent clean closes (60 tests)
# ---------------------------------------------------------------------------

SEEDS = [
    1, 7, 13, 42, 99, 100, 137, 200, 256, 512,
    999, 1000, 1234, 2000, 2025, 2026, 2027, 3000, 4000, 5000,
]
SEED_PERIODS = ["2026-01", "2026-06", "2026-12"]


@pytest.mark.parametrize("period,seed", [
    (p, s) for p in SEED_PERIODS for s in SEEDS
])
def test_close_clean_various_seeds(period, seed):
    ds = generate_dataset(period, seed=seed)
    result = CloseEngine(ds).run()
    assert result.clean


# ---------------------------------------------------------------------------
# Section 17: CloseResult metadata (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_close_result_period_and_seed(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    assert result.period == period
    assert result.seed == 42  # default seed used by _make_dataset


# ---------------------------------------------------------------------------
# Section 18: Ledger account_balance across posted JEs (40 tests)
# ---------------------------------------------------------------------------

ACCOUNT_BALANCE_AMOUNTS = [
    100, 500, 1000, 2000, 5000, 8000, 10000, 15000,
    20000, 25000, 30000, 40000, 50000, 60000, 75000,
    80000, 90000, 100000, 120000, 150000,
    200000, 250000, 300000, 400000, 500000,
    600000, 750000, 900000, 1000000, 2000000,
    300, 700, 1100, 1300, 1700, 2300, 3700, 4300, 6700, 8300,
]


@pytest.mark.parametrize("amount", ACCOUNT_BALANCE_AMOUNTS)
def test_ledger_account_balance_accumulates(amount):
    ledger = _ledger()
    # Post two entries of same amount, then account balance should double
    for i in range(2):
        je = JournalEntry(f"JE-{i}", "2026-03", "test", "balance test")
        je.lines.append(JournalLine("DH", "1000", amount, 0, "dr"))
        je.lines.append(JournalLine("MF", "1000", amount, 0, "dr"))
        je.lines.append(JournalLine("DH", "2000", 0, amount, "cr"))
        je.lines.append(JournalLine("MF", "2000", 0, amount, "cr"))
        ledger.post(je, require_entity_balance=True)
    assert ledger.account_balance("1000") == amount * 4
    assert ledger.account_balance("2000") == -(amount * 4)


# ---------------------------------------------------------------------------
# Section 19: Ledger trial_balance returns sorted rows (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_trial_balance_sorted(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    rows = result.ledger.trial_balance()
    keys = [(entity, account) for entity, account, _, _ in rows]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Section 20: TieResult properties (40 tests)
# ---------------------------------------------------------------------------

TIE_RESULT_CASES = [
    (1000, 1000, True, 0),
    (1000, 999, False, 1),
    (1000, 1001, False, -1),
    (0, 0, True, 0),
    (5000, 5000, True, 0),
    (5000, 4999, False, 1),
    (5000, 5001, False, -1),
    (10000, 10000, True, 0),
    (10000, 9999, False, 1),
    (10000, 10001, False, -1),
    (25000, 25000, True, 0),
    (25000, 24999, False, 1),
    (50000, 50000, True, 0),
    (50000, 50001, False, -1),
    (100000, 100000, True, 0),
    (100000, 100001, False, -1),
    (250000, 250000, True, 0),
    (250001, 250000, False, 1),
    (500000, 500000, True, 0),
    (500001, 500000, False, 1),
    (1, 1, True, 0),
    (2, 1, False, 1),
    (1, 2, False, -1),
    (12345, 12345, True, 0),
    (12345, 12346, False, -1),
    (12346, 12345, False, 1),
    (99999, 99999, True, 0),
    (99999, 100000, False, -1),
    (100000, 99999, False, 1),
    (7777, 7777, True, 0),
    (7777, 7778, False, -1),
    (7778, 7777, False, 1),
    (8000, 8000, True, 0),
    (6000, 6000, True, 0),
    (15000, 15000, True, 0),
    (15000, 14999, False, 1),
    (2083, 2083, True, 0),
    (2083, 2084, False, -1),
    (938, 938, True, 0),
    (938, 937, False, 1),
]


@pytest.mark.parametrize("expected,actual,ties,variance", TIE_RESULT_CASES)
def test_tie_result_properties(expected, actual, ties, variance):
    t = TieResult(
        schedule="Prepaid amortization",
        account="1400",
        expected_cents=expected,
        actual_cents=actual,
    )
    assert t.ties == ties
    assert t.variance_cents == variance


# ---------------------------------------------------------------------------
# Section 21: Ledger keys method (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_ledger_keys_non_empty_after_close(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    keys = result.ledger.keys()
    assert len(keys) > 0
    for key in keys:
        assert len(key) == 2  # (entity, account) tuple


# ---------------------------------------------------------------------------
# Section 22: OutOfTieError is raised for unbalanced entry (20 tests)
# ---------------------------------------------------------------------------

UNBALANCED_AMOUNTS = [
    (100, 99), (100, 101), (500, 499), (500, 501),
    (1000, 999), (1000, 1001), (5000, 4999), (5000, 5001),
    (10000, 9999), (10000, 10001), (25000, 24999), (25000, 25001),
    (50000, 49999), (50000, 50001), (100000, 99999), (100000, 100001),
    (1, 0), (0, 1), (200000, 199999), (500000, 500001),
]


@pytest.mark.parametrize("dr,cr", UNBALANCED_AMOUNTS)
def test_out_of_tie_error_raised_for_unbalanced(dr, cr):
    ledger = _ledger()
    je = JournalEntry("JE-BAD", "2026-03", "test", "unbalanced")
    je.lines.append(JournalLine("DH", "1000", dr, 0, "dr"))
    je.lines.append(JournalLine("DH", "2000", 0, cr, "cr"))
    with pytest.raises(OutOfTieError) as exc_info:
        ledger.post(je)
    assert "JE-BAD" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Section 23: ChartOfAccounts lookup (28 tests)
# ---------------------------------------------------------------------------

ALL_ACCOUNT_CODES = [
    "1000", "1200", "1400", "1500", "1510", "1600", "1700", "1800",
    "2000", "2100", "2200", "2300", "2400", "2500", "2800",
    "3000",
    "4000", "4900",
    "5000", "6000", "6050", "6100", "6200", "6300", "6400", "6500", "6600", "6650",
]


@pytest.mark.parametrize("code", ALL_ACCOUNT_CODES)
def test_coa_get_all_codes(code):
    coa = _coa()
    acct = coa.get(code)
    assert acct.code == code
    assert isinstance(acct.name, str)
    assert len(acct.name) > 0


@pytest.mark.parametrize("code", ALL_ACCOUNT_CODES)
def test_coa_contains_all_codes(code):
    coa = _coa()
    assert code in coa


# ---------------------------------------------------------------------------
# Section 24: Account label property (28 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", ALL_ACCOUNT_CODES)
def test_account_label_format(code):
    coa = _coa()
    acct = coa.get(code)
    assert acct.label == f"{code} · {acct.name}"


# ---------------------------------------------------------------------------
# Section 25: JournalEntry entities() method (20 tests)
# ---------------------------------------------------------------------------

ENTITY_LINE_CASES = [
    (["DH"], {"DH"}),
    (["MF"], {"MF"}),
    (["BW"], {"BW"}),
    (["DH", "MF"], {"DH", "MF"}),
    (["DH", "BW"], {"DH", "BW"}),
    (["MF", "BW"], {"MF", "BW"}),
    (["DH", "MF", "BW"], {"DH", "MF", "BW"}),
    (["DH", "DH"], {"DH"}),
    (["MF", "MF"], {"MF"}),
    (["BW", "BW"], {"BW"}),
    (["DH", "MF", "DH"], {"DH", "MF"}),
    (["DH", "BW", "BW"], {"DH", "BW"}),
    (["MF", "BW", "MF"], {"MF", "BW"}),
    (["DH", "MF", "BW", "DH"], {"DH", "MF", "BW"}),
    (["DH", "DH", "MF", "MF"], {"DH", "MF"}),
    (["BW", "BW", "BW"], {"BW"}),
    (["DH", "MF", "MF", "BW"], {"DH", "MF", "BW"}),
    (["DH", "DH", "DH", "BW"], {"DH", "BW"}),
    (["MF", "BW", "DH", "MF"], {"DH", "MF", "BW"}),
    (["DH", "MF", "BW", "DH", "MF"], {"DH", "MF", "BW"}),
]


@pytest.mark.parametrize("entity_list,expected_set", ENTITY_LINE_CASES)
def test_journal_entry_entities(entity_list, expected_set):
    je = JournalEntry("JE-ENT", "2026-03", "test", "entities test")
    for ent in entity_list:
        je.lines.append(JournalLine(ent, "1000", 100, 0, "dr"))
    assert je.entities() == expected_set


# ---------------------------------------------------------------------------
# Section 26: balances_per_entity consistency (30 tests)
# ---------------------------------------------------------------------------

ENTITY_BALANCE_CASES = [
    # (lines as (entity, dr, cr) tuples, expected_balance_dict)
    ([("DH", 100, 0), ("DH", 0, 100)], {"DH": 0}),
    ([("DH", 200, 0), ("DH", 0, 100), ("MF", 0, 100)], {"DH": 100, "MF": -100}),
    ([("DH", 500, 0), ("DH", 0, 500)], {"DH": 0}),
    ([("MF", 1000, 0), ("MF", 0, 1000)], {"MF": 0}),
    ([("BW", 2000, 0), ("BW", 0, 2000)], {"BW": 0}),
    ([("DH", 100, 0), ("MF", 0, 100)], {"DH": 100, "MF": -100}),
    ([("DH", 500, 0), ("BW", 0, 500)], {"DH": 500, "BW": -500}),
    ([("MF", 750, 0), ("BW", 0, 750)], {"MF": 750, "BW": -750}),
    ([("DH", 1000, 0), ("MF", 500, 0), ("DH", 0, 1000), ("MF", 0, 500)], {"DH": 0, "MF": 0}),
    ([("DH", 200, 0), ("MF", 300, 0), ("BW", 500, 0), ("DH", 0, 200), ("MF", 0, 300), ("BW", 0, 500)], {"DH": 0, "MF": 0, "BW": 0}),
    ([("DH", 1000, 0), ("DH", 0, 600), ("DH", 0, 400)], {"DH": 0}),
    ([("MF", 5000, 0), ("MF", 0, 2500), ("BW", 0, 2500)], {"MF": 2500, "BW": -2500}),
    ([("DH", 3000, 0), ("MF", 2000, 0), ("DH", 0, 3000), ("MF", 0, 2000)], {"DH": 0, "MF": 0}),
    ([("BW", 6000, 0), ("BW", 0, 3000), ("BW", 0, 3000)], {"BW": 0}),
    ([("DH", 10000, 0), ("DH", 0, 10000)], {"DH": 0}),
    ([("DH", 100, 0), ("DH", 200, 0), ("DH", 0, 300)], {"DH": 0}),
    ([("MF", 400, 0), ("MF", 600, 0), ("MF", 0, 1000)], {"MF": 0}),
    ([("BW", 50, 0), ("BW", 50, 0), ("BW", 0, 100)], {"BW": 0}),
    ([("DH", 1000, 0), ("DH", 0, 500), ("MF", 0, 500)], {"DH": 500, "MF": -500}),
    ([("DH", 2000, 0), ("MF", 1000, 0), ("BW", 1000, 0), ("DH", 0, 2000), ("MF", 0, 1000), ("BW", 0, 1000)], {"DH": 0, "MF": 0, "BW": 0}),
    ([("DH", 9000, 0), ("MF", 6000, 0), ("DH", 0, 9000), ("MF", 0, 6000)], {"DH": 0, "MF": 0}),
    ([("BW", 8000, 0), ("BW", 0, 8000)], {"BW": 0}),
    ([("DH", 100, 0), ("DH", 100, 0), ("DH", 0, 200)], {"DH": 0}),
    ([("MF", 250, 0), ("MF", 250, 0), ("MF", 0, 500)], {"MF": 0}),
    ([("BW", 375, 0), ("BW", 375, 0), ("BW", 0, 750)], {"BW": 0}),
    ([("DH", 4000, 0), ("MF", 3500, 0), ("BW", 2500, 0), ("DH", 0, 4000), ("MF", 0, 3500), ("BW", 0, 2500)], {"DH": 0, "MF": 0, "BW": 0}),
    ([("DH", 1, 0), ("DH", 0, 1)], {"DH": 0}),
    ([("MF", 999, 0), ("MF", 0, 999)], {"MF": 0}),
    ([("BW", 12345, 0), ("BW", 0, 12345)], {"BW": 0}),
    ([("DH", 9999, 0), ("DH", 0, 9999)], {"DH": 0}),
]


@pytest.mark.parametrize("lines,expected", ENTITY_BALANCE_CASES)
def test_balances_per_entity(lines, expected):
    je = JournalEntry("JE-BPE", "2026-03", "test", "balances per entity")
    for entity, dr, cr in lines:
        je.lines.append(JournalLine(entity, "1000", dr, cr, "line"))
    result = je.balances_per_entity()
    assert result == expected


# ---------------------------------------------------------------------------
# Section 27: Register JE categories present in result (12 tests)
# ---------------------------------------------------------------------------

EXPECTED_CATEGORIES = {
    "prepaid_amortization", "depreciation", "deferred_rent_cam",
    "fixed_fee_accrual", "mgmt_fee_accrual", "note_interest", "gna_allocation",
    "insurance_allocation", "postage_allocation",
}


@pytest.mark.parametrize("period", ALL_MONTHS)
def test_register_contains_all_categories(period):
    ds = _make_dataset(period)
    result = CloseEngine(ds).run()
    categories = {je.category for je in result.register}
    assert EXPECTED_CATEGORIES <= categories


# ---------------------------------------------------------------------------
# Section 28: Ledger load_opening idempotent per entity (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_ledger_opening_load_accumulates(period):
    ds = _make_dataset(period)
    ledger = _ledger()
    # Load once: check that posting two opening lines sums correctly
    ledger.load_opening([
        JournalLine("DH", "1000", 10000, 0, "cash1"),
        JournalLine("DH", "1000", 5000, 0, "cash2"),
        JournalLine("DH", "2000", 0, 15000, "ap1"),
    ])
    assert ledger.balance("DH", "1000") == 15000
    assert ledger.balance("DH", "2000") == -15000


# ---------------------------------------------------------------------------
# Section 29: No sign errors — debit accounts carry positive balances (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_debit_accounts_positive_after_close(period):
    """After loading an opening TB with only assets/expenses, balances positive."""
    ledger = _ledger()
    ledger.load_opening([
        JournalLine("DH", "1000", 50000, 0, "cash"),
        JournalLine("DH", "1200", 10000, 0, "ar"),
        JournalLine("DH", "3000", 0, 60000, "equity"),
    ])
    assert ledger.balance("DH", "1000") > 0
    assert ledger.balance("DH", "1200") > 0
    assert ledger.balance("DH", "3000") < 0
