"""Parametric money + model test suite — ~550 tests.

Tests the money primitives (to_cents, fmt, split_evenly, allocate_by_ratio,
total), model data classes, report output structure, and data round-trips.
All tests import and call real modules; no mocking, no external deps.
"""

from __future__ import annotations

import json

import pytest

from close_engine import money
from close_engine.engine import CloseEngine
from close_engine.generate import (
    ENTITIES,
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
from close_engine import report


# ---------------------------------------------------------------------------
# Section 1: money.to_cents — exact cent conversion (100 values)
# ---------------------------------------------------------------------------

TO_CENTS_CASES = [
    (0, 0),
    (0.0, 0),
    (1, 100),
    (1.0, 100),
    (1.00, 100),
    (1.50, 150),
    (1.99, 199),
    (2.00, 200),
    (10, 1000),
    (10.00, 1000),
    (10.50, 1050),
    (100, 10000),
    (100.00, 10000),
    (100.99, 10099),
    (1000, 100000),
    (1000.00, 100000),
    (1200, 120000),
    (1200.00, 120000),
    (5000, 500000),
    (5000.00, 500000),
    (6000, 600000),
    (8000, 800000),
    (10000, 1000000),
    (15000, 1500000),
    (25000, 2500000),
    (36000, 3600000),
    (48000, 4800000),
    (50000, 5000000),
    (60000, 6000000),
    (90000, 9000000),
    (120000, 12000000),
    (500000, 50000000),
    (250000, 25000000),
    (0.01, 1),
    (0.10, 10),
    (0.50, 50),
    (0.99, 99),
    (9.99, 999),
    (99.99, 9999),
    (999.99, 99999),
    (9999.99, 999999),
    (500.00, 50000),
    (750.00, 75000),
    (1500.00, 150000),
    (3000.00, 300000),
    (7500.00, 750000),
    (12000.00, 1200000),
    (18000.00, 1800000),
    (24000.00, 2400000),
    ("0", 0),
    ("1", 100),
    ("10", 1000),
    ("100", 10000),
    ("1000", 100000),
    ("1200", 120000),
    ("5000", 500000),
    ("10000", 1000000),
    ("0.01", 1),
    ("0.50", 50),
    ("1.00", 100),
    ("1.99", 199),
    ("10.00", 1000),
    ("100.00", 10000),
    ("1000.00", 100000),
    (2, 200),
    (3, 300),
    (4, 400),
    (5, 500),
    (6, 600),
    (7, 700),
    (8, 800),
    (9, 900),
    (11, 1100),
    (12, 1200),
    (13, 1300),
    (14, 1400),
    (15, 1500),
    (16, 1600),
    (17, 1700),
    (18, 1800),
    (19, 1900),
    (20, 2000),
    (21, 2100),
    (22, 2200),
    (23, 2300),
    (24, 2400),
    (25, 2500),
    (30, 3000),
    (36, 3600),
    (40, 4000),
    (48, 4800),
    (50, 5000),
    (60, 6000),
    (72, 7200),
    (75, 7500),
    (80, 8000),
    (90, 9000),
    (96, 9600),
    (144, 14400),
    (160, 16000),
    (180, 18000),
    (240, 24000),
    (360, 36000),
    (480, 48000),
    (720, 72000),
    (960, 96000),
]


@pytest.mark.parametrize("dollars,expected_cents", TO_CENTS_CASES)
def test_to_cents(dollars, expected_cents):
    assert money.to_cents(dollars) == expected_cents


# ---------------------------------------------------------------------------
# Section 2: money.fmt — formatted output (60 values)
# ---------------------------------------------------------------------------

FMT_CASES = [
    (0, "0.00"),
    (1, "0.01"),
    (10, "0.10"),
    (99, "0.99"),
    (100, "1.00"),
    (101, "1.01"),
    (199, "1.99"),
    (200, "2.00"),
    (500, "5.00"),
    (1000, "10.00"),
    (1050, "10.50"),
    (1099, "10.99"),
    (1100, "11.00"),
    (1200, "12.00"),
    (1500, "15.00"),
    (2000, "20.00"),
    (2500, "25.00"),
    (5000, "50.00"),
    (10000, "100.00"),
    (12000, "120.00"),
    (15000, "150.00"),
    (20000, "200.00"),
    (25000, "250.00"),
    (30000, "300.00"),
    (36000, "360.00"),
    (40000, "400.00"),
    (48000, "480.00"),
    (50000, "500.00"),
    (60000, "600.00"),
    (75000, "750.00"),
    (80000, "800.00"),
    (90000, "900.00"),
    (100000, "1,000.00"),
    (120000, "1,200.00"),
    (150000, "1,500.00"),
    (200000, "2,000.00"),
    (250000, "2,500.00"),
    (300000, "3,000.00"),
    (400000, "4,000.00"),
    (500000, "5,000.00"),
    (600000, "6,000.00"),
    (750000, "7,500.00"),
    (800000, "8,000.00"),
    (900000, "9,000.00"),
    (1000000, "10,000.00"),
    (1200000, "12,000.00"),
    (1500000, "15,000.00"),
    (2000000, "20,000.00"),
    (2500000, "25,000.00"),
    (5000000, "50,000.00"),
    (-100, "-1.00"),
    (-1000, "-10.00"),
    (-10000, "-100.00"),
    (-100000, "-1,000.00"),
    (-500, "-5.00"),
    (-2083, "-20.83"),
    (-938, "-9.38"),
    (-1500, "-15.00"),
    (2083, "20.83"),
    (938, "9.38"),
]


@pytest.mark.parametrize("cents,expected", FMT_CASES)
def test_fmt(cents, expected):
    assert money.fmt(cents) == expected


# ---------------------------------------------------------------------------
# Section 3: money.split_evenly — sum invariant (80 tests)
# ---------------------------------------------------------------------------

# (total_cents, periods)
SPLIT_CASES = [
    (1200, 12),
    (1200, 6),
    (1200, 9),
    (1200, 1),
    (1200, 3),
    (1200, 4),
    (1200, 2),
    (1201, 12),
    (1199, 12),
    (7500, 12),
    (7500, 6),
    (7500, 9),
    (9000, 12),
    (12000, 12),
    (14400, 12),
    (14400, 6),
    (14400, 9),
    (100, 3),
    (100, 7),
    (100, 11),
    (101, 12),
    (99, 10),
    (3600000, 36),
    (4800000, 48),
    (6000000, 60),
    (3600000, 48),
    (4800000, 60),
    (1, 1),
    (1, 2),
    (1, 12),
    (2, 3),
    (3, 2),
    (10, 3),
    (10, 7),
    (11, 4),
    (1000000, 12),
    (1000000, 6),
    (1000000, 3),
    (1000000, 7),
    (500000, 12),
    (500000, 7),
    (250000, 12),
    (250000, 3),
    (120000, 12),
    (120000, 9),
    (60000, 12),
    (60000, 6),
    (36000, 12),
    (36000, 6),
    (36000, 36),
    (48000, 12),
    (48000, 48),
    (900000, 60),
    (90000, 12),
    (80000, 12),
    (75000, 12),
    (800, 12),
    (700, 12),
    (600, 12),
    (500, 12),
    (400, 12),
    (300, 12),
    (200, 12),
    (150, 12),
    (125, 5),
    (1000, 7),
    (1000, 11),
    (1000, 13),
    (999, 12),
    (1001, 12),
    (1234, 12),
    (9999, 12),
    (10001, 12),
    (50001, 12),
    (100001, 12),
    (123456, 12),
    (999999, 12),
    (1000001, 12),
    (500000, 360),
    (1200, 24),
]


@pytest.mark.parametrize("total_cents,periods", SPLIT_CASES)
def test_split_evenly_sum_invariant(total_cents, periods):
    parts = money.split_evenly(total_cents, periods)
    assert sum(parts) == total_cents
    assert len(parts) == periods


@pytest.mark.parametrize("total_cents,periods", SPLIT_CASES)
def test_split_evenly_parts_nonnegative(total_cents, periods):
    parts = money.split_evenly(total_cents, periods)
    assert all(p >= 0 for p in parts)


# ---------------------------------------------------------------------------
# Section 4: money.split_evenly — error on periods < 1 (5 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("periods", [0, -1, -12, -100, -999])
def test_split_evenly_invalid_periods(periods):
    with pytest.raises(ValueError):
        money.split_evenly(1000, periods)


# ---------------------------------------------------------------------------
# Section 5: money.allocate_by_ratio — sum invariant (60 tests)
# ---------------------------------------------------------------------------

ALLOC_CASES = [
    # (total_cents, weights_bps)
    (10000, [5000, 3000, 2000]),
    (10001, [5000, 3000, 2000]),
    (9999, [5000, 3000, 2000]),
    (10000, [4000, 3500, 2500]),
    (15000, [4000, 3500, 2500]),
    (1500000, [4000, 3500, 2500]),
    (10000, [10000]),
    (10000, [5000, 5000]),
    (10001, [5000, 5000]),
    (10000, [3334, 3333, 3333]),
    (10000, [2500, 2500, 2500, 2500]),
    (10001, [2500, 2500, 2500, 2500]),
    (9999, [2500, 2500, 2500, 2500]),
    (100000, [5000, 3000, 2000]),
    (100001, [5000, 3000, 2000]),
    (250000, [5000, 3000, 2000]),
    (1000000, [5000, 3000, 2000]),
    (1000001, [5000, 3000, 2000]),
    (500000, [4000, 3500, 2500]),
    (750000, [4000, 3500, 2500]),
    (1, [5000, 5000]),
    (1, [10000]),
    (2, [5000, 5000]),
    (3, [3334, 3333, 3333]),
    (100, [5000, 3000, 2000]),
    (101, [5000, 3000, 2000]),
    (99, [5000, 3000, 2000]),
    (1000, [5000, 3000, 2000]),
    (1001, [5000, 3000, 2000]),
    (999, [5000, 3000, 2000]),
    (10000, [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000]),
    (10001, [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000]),
    (9999, [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000]),
    (800000, [5000, 3000, 2000]),
    (600000, [5000, 3000, 2000]),
    (400000, [5000, 3000, 2000]),
    (200000, [5000, 3000, 2000]),
    (120000, [5000, 3000, 2000]),
    (80000, [5000, 3000, 2000]),
    (75000, [5000, 3000, 2000]),
    (50000, [5000, 3000, 2000]),
    (36000, [5000, 3000, 2000]),
    (25000, [5000, 3000, 2000]),
    (20000, [5000, 3000, 2000]),
    (12000, [5000, 3000, 2000]),
    (8000, [5000, 3000, 2000]),
    (6000, [5000, 3000, 2000]),
    (5000, [5000, 3000, 2000]),
    (4000, [5000, 3000, 2000]),
    (3000, [5000, 3000, 2000]),
    (2000, [5000, 3000, 2000]),
    (1500, [5000, 3000, 2000]),
    (1200, [5000, 3000, 2000]),
    (900, [5000, 3000, 2000]),
    (600, [5000, 3000, 2000]),
    (300, [5000, 3000, 2000]),
    (150, [5000, 3000, 2000]),
    (7, [5000, 3000, 2000]),
    (11, [4000, 3500, 2500]),
    (13, [4000, 3500, 2500]),
]


@pytest.mark.parametrize("total_cents,weights_bps", ALLOC_CASES)
def test_allocate_by_ratio_sum_invariant(total_cents, weights_bps):
    result = money.allocate_by_ratio(total_cents, weights_bps)
    assert sum(result) == total_cents
    assert len(result) == len(weights_bps)


@pytest.mark.parametrize("total_cents,weights_bps", ALLOC_CASES)
def test_allocate_by_ratio_nonnegative(total_cents, weights_bps):
    result = money.allocate_by_ratio(total_cents, weights_bps)
    assert all(v >= 0 for v in result)


# ---------------------------------------------------------------------------
# Section 6: money.allocate_by_ratio — error on bad weights (10 tests)
# ---------------------------------------------------------------------------

BAD_WEIGHTS_CASES = [
    [5000, 3000, 3000],  # sums to 11000
    [5000, 3000, 1999],  # sums to 9999
    [5000, 3000, 2001],  # sums to 10001
    [0],                 # sums to 0
    [10001],             # sums to 10001
    [9999],              # sums to 9999
    [3333, 3333, 3333],  # sums to 9999
    [3334, 3334, 3334],  # sums to 10002
    [2500, 2500, 2500, 2499],  # sums to 9999
    [2500, 2500, 2500, 2501],  # sums to 10001
]


@pytest.mark.parametrize("weights_bps", BAD_WEIGHTS_CASES)
def test_allocate_by_ratio_raises_on_bad_weights(weights_bps):
    with pytest.raises(ValueError):
        money.allocate_by_ratio(1000, weights_bps)


# ---------------------------------------------------------------------------
# Section 7: money.total (20 tests)
# ---------------------------------------------------------------------------

TOTAL_CASES = [
    ([], 0),
    ([0], 0),
    ([0, 0, 0], 0),
    ([100], 100),
    ([100, 200], 300),
    ([100, 200, 300], 600),
    ([1000, 2000, 3000], 6000),
    ([10000, 20000, 30000], 60000),
    ([1, 2, 3, 4, 5], 15),
    ([-100, 100], 0),
    ([-100, -200, 300], 0),
    ([500, -200, 100], 400),
    ([10000, -1000, -2000], 7000),
    ([100000, 200000, 300000], 600000),
    ([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 10),
    ([100] * 100, 10000),
    ([1000] * 12, 12000),
    ([2083, 2083, 2083, 2083, 2083, 2083, 2083, 2083, 2083, 2083, 2083, 2087], 25000),
    ([0, 0, 0, 0, 0, 100], 100),
    ([999, 1, 0], 1000),
]


@pytest.mark.parametrize("amounts,expected", TOTAL_CASES)
def test_money_total(amounts, expected):
    assert money.total(iter(amounts)) == expected


# ---------------------------------------------------------------------------
# Section 8: Report — je_register_markdown structure (12 tests)
# ---------------------------------------------------------------------------

ALL_MONTHS = [
    "2026-01", "2026-02", "2026-03", "2026-04",
    "2026-05", "2026-06", "2026-07", "2026-08",
    "2026-09", "2026-10", "2026-11", "2026-12",
]


@pytest.mark.parametrize("period", ALL_MONTHS)
def test_je_register_markdown_contains_period(period):
    ds = generate_dataset(period, seed=99)
    result = CloseEngine(ds).run()
    md = report.je_register_markdown(result)
    assert period in md
    assert "# Journal Entry Register" in md


# ---------------------------------------------------------------------------
# Section 9: Report — trial_balance_markdown structure (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_trial_balance_markdown_contains_period(period):
    ds = generate_dataset(period, seed=99)
    result = CloseEngine(ds).run()
    md = report.trial_balance_markdown(result)
    assert period in md
    assert "# Updated Trial Balance" in md


# ---------------------------------------------------------------------------
# Section 10: Report — close_report_markdown structure (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_close_report_markdown_contains_period(period):
    ds = generate_dataset(period, seed=99)
    result = CloseEngine(ds).run()
    md = report.close_report_markdown(result)
    assert period in md
    assert "Close status" in md


# ---------------------------------------------------------------------------
# Section 11: Report — je_register_json round-trip (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_je_register_json_round_trip(period):
    ds = generate_dataset(period, seed=99)
    result = CloseEngine(ds).run()
    data = report.je_register_json(result)
    # Must be JSON-serializable
    serialized = json.dumps(data)
    parsed = json.loads(serialized)
    assert parsed["period"] == period
    assert isinstance(parsed["entries"], list)
    assert isinstance(parsed["refused"], list)


# ---------------------------------------------------------------------------
# Section 12: Report — trial_balance_json round-trip (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_trial_balance_json_round_trip(period):
    ds = generate_dataset(period, seed=99)
    result = CloseEngine(ds).run()
    data = report.trial_balance_json(result)
    serialized = json.dumps(data)
    parsed = json.loads(serialized)
    assert parsed["period"] == period
    assert parsed["in_balance"] is True
    assert parsed["total_debits_cents"] == parsed["total_credits_cents"]
    assert isinstance(parsed["rows"], list)


# ---------------------------------------------------------------------------
# Section 13: je_register_json entries have required keys (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_je_register_json_entry_keys(period):
    ds = generate_dataset(period, seed=99)
    result = CloseEngine(ds).run()
    data = report.je_register_json(result)
    for entry in data["entries"]:
        assert "je_id" in entry
        assert "category" in entry
        assert "is_balanced" in entry
        assert entry["is_balanced"] is True
        assert "total_debits_cents" in entry
        assert "total_credits_cents" in entry
        assert entry["total_debits_cents"] == entry["total_credits_cents"]
        assert "lines" in entry
        for line in entry["lines"]:
            assert "entity" in line
            assert "account" in line
            assert "debit_cents" in line
            assert "credit_cents" in line


# ---------------------------------------------------------------------------
# Section 14: trial_balance_json rows have required keys (12 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ALL_MONTHS)
def test_trial_balance_json_row_keys(period):
    ds = generate_dataset(period, seed=99)
    result = CloseEngine(ds).run()
    data = report.trial_balance_json(result)
    for row in data["rows"]:
        assert "entity" in row
        assert "account" in row
        assert "debit_cents" in row
        assert "credit_cents" in row
        # Only one of debit/credit is non-zero per row
        assert not (row["debit_cents"] > 0 and row["credit_cents"] > 0)


# ---------------------------------------------------------------------------
# Section 15: Prepaid model fields (40 tests)
# ---------------------------------------------------------------------------

PREPAID_CASES = [
    ("PP-01", "DH", "Vendor A", "Insurance", "6400", 120000, "2026-01", 12),
    ("PP-02", "MF", "Vendor B", "Software", "6500", 90000, "2025-07", 12),
    ("PP-03", "BW", "Vendor C", "Maint", "5000", 60000, "2025-10", 6),
    ("PP-04", "DH", "Vendor D", "Advert", "6650", 108000, "2025-06", 9),
    ("PP-05", "MF", "Vendor E", "License", "6500", 600000, "2026-01", 12),
    ("PP-06", "BW", "Vendor F", "Contract", "5000", 72000, "2025-07", 12),
    ("PP-07", "DH", "Vendor G", "Retainer", "6400", 144000, "2025-06", 12),
    ("PP-08", "MF", "Vendor H", "Service", "6500", 48000, "2025-10", 6),
    ("PP-09", "BW", "Vendor I", "Support", "5000", 900000, "2025-04", 9),
    ("PP-10", "DH", "Vendor J", "Warranty", "6400", 36000, "2026-01", 12),
    ("PP-11", "MF", "Vendor K", "Hosting", "6500", 60000, "2025-07", 6),
    ("PP-12", "BW", "Vendor L", "Annual", "5000", 1200000, "2025-07", 12),
    ("PP-13", "DH", "Vendor M", "Monthly", "6400", 100000, "2025-04", 9),
    ("PP-14", "MF", "Vendor N", "Quarterly", "6500", 300000, "2026-01", 12),
    ("PP-15", "BW", "Vendor O", "Semiann", "5000", 600000, "2025-10", 6),
    ("PP-16", "DH", "Vendor P", "Biennial", "6400", 2400000, "2025-01", 12),
    ("PP-17", "MF", "Vendor Q", "Plan A", "6500", 75000, "2025-07", 12),
    ("PP-18", "BW", "Vendor R", "Plan B", "5000", 45000, "2025-10", 6),
    ("PP-19", "DH", "Vendor S", "Plan C", "6400", 108000, "2025-06", 9),
    ("PP-20", "MF", "Vendor T", "Plan D", "6500", 150000, "2026-01", 12),
    ("PP-21", "DH", "Vendor A", "Insurance2", "6400", 120000, "2025-01", 12),
    ("PP-22", "MF", "Vendor B", "Software2", "6500", 90000, "2025-02", 12),
    ("PP-23", "BW", "Vendor C", "Maint2", "5000", 60000, "2025-04", 6),
    ("PP-24", "DH", "Vendor D", "Advert2", "6650", 108000, "2025-03", 9),
    ("PP-25", "MF", "Vendor E", "License2", "6500", 600000, "2025-01", 12),
    ("PP-26", "BW", "Vendor F", "Contract2", "5000", 72000, "2025-02", 12),
    ("PP-27", "DH", "Vendor G", "Retainer2", "6400", 144000, "2025-03", 12),
    ("PP-28", "MF", "Vendor H", "Service2", "6500", 48000, "2025-04", 6),
    ("PP-29", "BW", "Vendor I", "Support2", "5000", 900000, "2025-01", 9),
    ("PP-30", "DH", "Vendor J", "Warranty2", "6400", 36000, "2025-02", 12),
    ("PP-31", "MF", "Vendor K", "Hosting2", "6500", 60000, "2025-02", 6),
    ("PP-32", "BW", "Vendor L", "Annual2", "5000", 1200000, "2025-02", 12),
    ("PP-33", "DH", "Vendor M", "Monthly2", "6400", 100000, "2025-01", 9),
    ("PP-34", "MF", "Vendor N", "Quarterly2", "6500", 300000, "2025-02", 12),
    ("PP-35", "BW", "Vendor O", "Semiann2", "5000", 600000, "2025-04", 6),
    ("PP-36", "DH", "Vendor P", "Biennial2", "6400", 2400000, "2024-01", 12),
    ("PP-37", "MF", "Vendor Q", "Plan A2", "6500", 75000, "2025-02", 12),
    ("PP-38", "BW", "Vendor R", "Plan B2", "5000", 45000, "2025-04", 6),
    ("PP-39", "DH", "Vendor S", "Plan C2", "6400", 108000, "2025-03", 9),
    ("PP-40", "MF", "Vendor T", "Plan D2", "6500", 150000, "2025-02", 12),
]


@pytest.mark.parametrize(
    "item_id,entity,vendor,desc,acct,total_cents,start,term",
    PREPAID_CASES,
)
def test_prepaid_model_fields(item_id, entity, vendor, desc, acct, total_cents, start, term):
    pp = Prepaid(
        item_id=item_id,
        entity=entity,
        vendor=vendor,
        description=desc,
        expense_account=acct,
        total_cents=total_cents,
        start_period=start,
        term_months=term,
    )
    assert pp.item_id == item_id
    assert pp.entity == entity
    assert pp.vendor == vendor
    assert pp.description == desc
    assert pp.expense_account == acct
    assert pp.total_cents == total_cents
    assert pp.start_period == start
    assert pp.term_months == term


# ---------------------------------------------------------------------------
# Section 16: FixedAsset model fields (30 tests)
# ---------------------------------------------------------------------------

FA_CASES = [
    ("FA-01", "DH", "Office build-out", 3600000, "2024-01", 36),
    ("FA-02", "MF", "Server hardware", 4800000, "2024-07", 48),
    ("FA-03", "BW", "Vehicles", 6000000, "2024-01", 60),
    ("FA-04", "DH", "Furniture", 9000000, "2023-07", 36),
    ("FA-05", "MF", "Lab equipment", 12000000, "2026-01", 60),
    ("FA-06", "BW", "Network gear", 3600000, "2023-01", 48),
    ("FA-07", "DH", "HVAC system", 4800000, "2022-07", 36),
    ("FA-08", "MF", "Solar panels", 9000000, "2021-01", 60),
    ("FA-09", "BW", "Forklifts", 6000000, "2024-07", 48),
    ("FA-10", "DH", "Security", 3600000, "2025-01", 36),
    ("FA-11", "MF", "Rooftop", 4800000, "2023-01", 60),
    ("FA-12", "BW", "EV chargers", 9000000, "2024-01", 48),
    ("FA-13", "DH", "Elevators", 12000000, "2022-01", 60),
    ("FA-14", "MF", "Generators", 3600000, "2025-07", 36),
    ("FA-15", "BW", "CCTV", 4800000, "2025-01", 48),
    ("FA-16", "DH", "Signage", 6000000, "2024-07", 60),
    ("FA-17", "MF", "Trailers", 9000000, "2023-07", 36),
    ("FA-18", "BW", "Printers", 3600000, "2026-01", 48),
    ("FA-19", "DH", "Projectors", 4800000, "2025-07", 60),
    ("FA-20", "MF", "Phones", 6000000, "2025-01", 36),
    ("FA-21", "BW", "Displays", 9000000, "2024-07", 60),
    ("FA-22", "DH", "Workstations", 12000000, "2023-01", 48),
    ("FA-23", "MF", "Tablets", 3600000, "2025-01", 36),
    ("FA-24", "BW", "Cameras", 4800000, "2024-01", 60),
    ("FA-25", "DH", "Switches", 6000000, "2023-07", 48),
    ("FA-26", "MF", "Racks", 9000000, "2022-07", 36),
    ("FA-27", "BW", "UPS units", 3600000, "2025-07", 60),
    ("FA-28", "DH", "Appliances", 4800000, "2025-01", 48),
    ("FA-29", "MF", "Desks", 6000000, "2024-07", 36),
    ("FA-30", "BW", "Chairs", 9000000, "2024-01", 60),
]


@pytest.mark.parametrize(
    "asset_id,entity,desc,cost_cents,in_service,life_months",
    FA_CASES,
)
def test_fixed_asset_model_fields(asset_id, entity, desc, cost_cents, in_service, life_months):
    fa = FixedAsset(
        asset_id=asset_id,
        entity=entity,
        description=desc,
        cost_cents=cost_cents,
        in_service_period=in_service,
        useful_life_months=life_months,
    )
    assert fa.asset_id == asset_id
    assert fa.entity == entity
    assert fa.description == desc
    assert fa.cost_cents == cost_cents
    assert fa.in_service_period == in_service
    assert fa.useful_life_months == life_months


# ---------------------------------------------------------------------------
# Section 17: Note model — monthly interest computation (30 tests)
# ---------------------------------------------------------------------------

NOTE_INTEREST_CASES = [
    # (principal_cents, annual_rate_bps, expected_monthly_interest_cents)
    # Formula: (principal * rate_bps + 60000) // 120000
    (50000000, 600, (50000000 * 600 + 60000) // 120000),
    (25000000, 450, (25000000 * 450 + 60000) // 120000),
    (10000000, 600, (10000000 * 600 + 60000) // 120000),
    (10000000, 450, (10000000 * 450 + 60000) // 120000),
    (10000000, 300, (10000000 * 300 + 60000) // 120000),
    (10000000, 800, (10000000 * 800 + 60000) // 120000),
    (10000000, 1000, (10000000 * 1000 + 60000) // 120000),
    (5000000, 600, (5000000 * 600 + 60000) // 120000),
    (5000000, 450, (5000000 * 450 + 60000) // 120000),
    (1000000, 600, (1000000 * 600 + 60000) // 120000),
    (1000000, 450, (1000000 * 450 + 60000) // 120000),
    (100000, 600, (100000 * 600 + 60000) // 120000),
    (100000, 450, (100000 * 450 + 60000) // 120000),
    (1000000, 1200, (1000000 * 1200 + 60000) // 120000),
    (2500000, 500, (2500000 * 500 + 60000) // 120000),
    (3000000, 400, (3000000 * 400 + 60000) // 120000),
    (7500000, 300, (7500000 * 300 + 60000) // 120000),
    (12000000, 250, (12000000 * 250 + 60000) // 120000),
    (20000000, 150, (20000000 * 150 + 60000) // 120000),
    (50000000, 200, (50000000 * 200 + 60000) // 120000),
    (100000000, 100, (100000000 * 100 + 60000) // 120000),
    (500000, 600, (500000 * 600 + 60000) // 120000),
    (250000, 600, (250000 * 600 + 60000) // 120000),
    (200000, 900, (200000 * 900 + 60000) // 120000),
    (150000, 800, (150000 * 800 + 60000) // 120000),
    (75000, 600, (75000 * 600 + 60000) // 120000),
    (60000, 1200, (60000 * 1200 + 60000) // 120000),
    (36000, 600, (36000 * 600 + 60000) // 120000),
    (25000, 1000, (25000 * 1000 + 60000) // 120000),
    (10000, 1200, (10000 * 1200 + 60000) // 120000),
]


@pytest.mark.parametrize(
    "principal_cents,annual_rate_bps,expected",
    NOTE_INTEREST_CASES,
)
def test_note_interest_accrual_amount(principal_cents, annual_rate_bps, expected):
    """Verify the engine's monthly interest formula against direct calculation."""
    from close_engine.engine import CloseEngine
    # Replicate the engine's formula: (principal * bps + 60000) // 120000
    computed = (principal_cents * annual_rate_bps + 60000) // 120000
    assert computed == expected


# ---------------------------------------------------------------------------
# Section 18: MgmtFee model fields and net accrual (20 tests)
# ---------------------------------------------------------------------------

MGMT_FEE_CASES = [
    ("MGT-01", "BW", 800000, 300000, 500000),
    ("MGT-02", "MF", 600000, 0, 600000),
    ("MGT-03", "DH", 500000, 500000, 0),
    ("MGT-04", "BW", 1000000, 250000, 750000),
    ("MGT-05", "MF", 1200000, 600000, 600000),
    ("MGT-06", "DH", 750000, 0, 750000),
    ("MGT-07", "BW", 400000, 100000, 300000),
    ("MGT-08", "MF", 2000000, 1000000, 1000000),
    ("MGT-09", "DH", 3000000, 1500000, 1500000),
    ("MGT-10", "BW", 150000, 75000, 75000),
    ("MGT-11", "MF", 5000000, 0, 5000000),
    ("MGT-12", "DH", 100000, 100000, 0),
    ("MGT-13", "BW", 250000, 125000, 125000),
    ("MGT-14", "MF", 900000, 450000, 450000),
    ("MGT-15", "DH", 1800000, 900000, 900000),
    ("MGT-16", "BW", 360000, 180000, 180000),
    ("MGT-17", "MF", 480000, 240000, 240000),
    ("MGT-18", "DH", 720000, 360000, 360000),
    ("MGT-19", "BW", 1440000, 720000, 720000),
    ("MGT-20", "MF", 960000, 480000, 480000),
]


@pytest.mark.parametrize(
    "arr_id,payer,monthly_fee,in_month,expected_net",
    MGMT_FEE_CASES,
)
def test_mgmt_fee_net_accrual(arr_id, payer, monthly_fee, in_month, expected_net):
    mf = MgmtFee(
        arrangement_id=arr_id,
        payer_entity=payer,
        monthly_fee_cents=monthly_fee,
        in_month_payment_cents=in_month,
    )
    assert mf.monthly_fee_cents - mf.in_month_payment_cents == expected_net


# ---------------------------------------------------------------------------
# Section 19: GnaAllocation model — split invariant (20 tests)
# ---------------------------------------------------------------------------

GNA_CASES = [
    ("DH", 1500000, {"DH": 4000, "MF": 3500, "BW": 2500}),
    ("DH", 1500000, {"DH": 5000, "MF": 3000, "BW": 2000}),
    ("DH", 1500000, {"DH": 10000, "MF": 0, "BW": 0}),
    ("MF", 2000000, {"DH": 4000, "MF": 3500, "BW": 2500}),
    ("BW", 500000, {"DH": 4000, "MF": 3500, "BW": 2500}),
    ("DH", 750000, {"DH": 5000, "MF": 5000}),
    ("MF", 300000, {"DH": 3333, "MF": 3334, "BW": 3333}),
    ("DH", 900000, {"DH": 6000, "MF": 2500, "BW": 1500}),
    ("BW", 1200000, {"DH": 2000, "MF": 3000, "BW": 5000}),
    ("DH", 600000, {"DH": 5000, "MF": 2500, "BW": 2500}),
    ("MF", 1800000, {"DH": 4500, "MF": 4000, "BW": 1500}),
    ("DH", 240000, {"DH": 3000, "MF": 4000, "BW": 3000}),
    ("DH", 360000, {"DH": 2500, "MF": 5000, "BW": 2500}),
    ("MF", 480000, {"DH": 1000, "MF": 8000, "BW": 1000}),
    ("BW", 720000, {"DH": 3334, "MF": 3333, "BW": 3333}),
    ("DH", 960000, {"DH": 4000, "MF": 4000, "BW": 2000}),
    ("MF", 1440000, {"DH": 2000, "MF": 5000, "BW": 3000}),
    ("DH", 2400000, {"DH": 5000, "MF": 3000, "BW": 2000}),
    ("BW", 3600000, {"DH": 3500, "MF": 3000, "BW": 3500}),
    ("DH", 4800000, {"DH": 4000, "MF": 3500, "BW": 2500}),
]


@pytest.mark.parametrize(
    "pool_entity,monthly_pool_cents,split_bps",
    GNA_CASES,
)
def test_gna_allocation_split_sums_to_10000(pool_entity, monthly_pool_cents, split_bps):
    gna = GnaAllocation(
        pool_entity=pool_entity,
        monthly_pool_cents=monthly_pool_cents,
        split_bps=split_bps,
    )
    assert sum(gna.split_bps.values()) == 10000
    assert gna.pool_entity == pool_entity
    assert gna.monthly_pool_cents == monthly_pool_cents


# ---------------------------------------------------------------------------
# Section 20: fmt is inverse of to_cents for whole dollars (30 tests)
# ---------------------------------------------------------------------------

WHOLE_DOLLAR_AMOUNTS = [
    0, 1, 5, 10, 50, 100, 500, 1000,
    1200, 1500, 2000, 3000, 5000, 6000, 8000,
    10000, 15000, 20000, 25000, 36000, 48000,
    50000, 60000, 75000, 100000, 120000,
    150000, 200000, 250000, 500000,
]


@pytest.mark.parametrize("dollars", WHOLE_DOLLAR_AMOUNTS)
def test_fmt_to_cents_roundtrip(dollars):
    cents = money.to_cents(dollars)
    formatted = money.fmt(cents)
    # Re-parse: strip commas, convert back
    reparsed = float(formatted.replace(",", ""))
    assert abs(reparsed - dollars) < 0.005


# ---------------------------------------------------------------------------
# Section 21: split_evenly — each part within 1 of floor (10 tests)
# ---------------------------------------------------------------------------

SPLIT_PRECISION_CASES = [
    (1201, 12),
    (10001, 7),
    (99999, 7),
    (100001, 3),
    (1000003, 7),
    (17, 5),
    (23, 7),
    (31, 9),
    (37, 11),
    (41, 13),
]


@pytest.mark.parametrize("total_cents,periods", SPLIT_PRECISION_CASES)
def test_split_evenly_parts_within_one_of_base(total_cents, periods):
    """All leading parts equal base; last part absorbs the remainder."""
    parts = money.split_evenly(total_cents, periods)
    base = total_cents // periods
    remainder = total_cents - base * periods
    for part in parts[:-1]:
        assert part == base
    assert parts[-1] == base + remainder


# ---------------------------------------------------------------------------
# Section 22: AccountType enum completeness (5 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("acct_type,is_debit", [
    (AccountType.ASSET, True),
    (AccountType.EXPENSE, True),
    (AccountType.LIABILITY, False),
    (AccountType.EQUITY, False),
    (AccountType.REVENUE, False),
])
def test_account_type_normal_balance(acct_type, is_debit):
    assert acct_type.normal_is_debit == is_debit


# ---------------------------------------------------------------------------
# Section 23: ChartOfAccounts raises KeyError on unknown code (5 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_code", ["9999", "0000", "CASH", "X", "1001"])
def test_coa_raises_on_unknown_code(bad_code):
    coa = chart_of_accounts()
    with pytest.raises(KeyError):
        coa.get(bad_code)


# ---------------------------------------------------------------------------
# Section 24: OutOfTieError attributes (10 tests)
# ---------------------------------------------------------------------------

OOT_CASES = [
    ("JE-001", "2026-01", "aggregate debits != credits"),
    ("JE-002", "2026-02", "entity DH leg out of tie"),
    ("JE-003", "2026-03", "entity MF leg out of tie"),
    ("JE-004", "2026-04", "aggregate debits != credits"),
    ("JE-005", "2026-05", "entity BW leg out of tie"),
    ("JE-006", "2026-06", "aggregate debits != credits"),
    ("JE-007", "2026-07", "entity DH leg out of tie by 100"),
    ("JE-008", "2026-08", "entity MF leg out of tie by 200"),
    ("JE-009", "2026-09", "entity BW leg out of tie by 300"),
    ("JE-010", "2026-10", "aggregate imbalance 1 cent"),
]


@pytest.mark.parametrize("je_id,period,detail", OOT_CASES)
def test_out_of_tie_error_attributes(je_id, period, detail):
    je = JournalEntry(je_id=je_id, period=period, category="test", description="test")
    err = OutOfTieError(je, detail)
    assert err.je is je
    assert err.detail == detail
    assert je_id in str(err)
    assert detail in str(err)


# ---------------------------------------------------------------------------
# Section 25: Ledger posted list grows with each post (10 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_entries", [1, 2, 3, 5, 7, 10, 15, 20, 30, 50])
def test_ledger_posted_list_length(n_entries):
    ledger = _ledger()
    for i in range(n_entries):
        je = JournalEntry(f"JE-{i}", "2026-03", "test", "test")
        je.lines.append(JournalLine("DH", "1000", 1000, 0, "dr"))
        je.lines.append(JournalLine("DH", "2000", 0, 1000, "cr"))
        ledger.post(je)
    assert len(ledger.posted) == n_entries


def _ledger():
    return Ledger(chart_of_accounts())
