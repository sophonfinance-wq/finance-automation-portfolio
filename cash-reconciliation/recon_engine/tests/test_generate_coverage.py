"""Coverage for the synthetic data generator: determinism, structure, injection.

Exercises ``recon_engine.generate`` — the seeded dataset shape, the per-entity
account-number scheme, the intentionally injected discrepancies, and the small
record-lookup/replace helpers.
"""

from __future__ import annotations

import pytest

from recon_engine.generate import (
    DEFAULT_SEED,
    BankStatement,
    GLRecord,
    LenderStatement,
    SyntheticDataset,
    generate_dataset,
    _bank_by_acct,
    _gl_by_acct,
    _lender_by_acct,
    _replace_bank,
    _replace_gl,
    _replace_lender,
)


@pytest.fixture(scope="module")
def ds() -> SyntheticDataset:
    return generate_dataset()


# --------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------
def test_default_seed_value() -> None:
    assert DEFAULT_SEED == 20260331


def test_same_seed_is_byte_identical() -> None:
    a = generate_dataset(seed=123)
    b = generate_dataset(seed=123)
    assert [r.gl_balance for r in a.gl_records] == [r.gl_balance for r in b.gl_records]
    assert [r.account_number for r in a.gl_records] == [
        r.account_number for r in b.gl_records
    ]
    assert [s.ending_balance for s in a.bank_statements] == [
        s.ending_balance for s in b.bank_statements
    ]
    assert [ln.principal for ln in a.lender_statements] == [
        ln.principal for ln in b.lender_statements
    ]


def test_different_seed_changes_base_balances() -> None:
    a = generate_dataset(seed=1)
    b = generate_dataset(seed=2)
    # At least the clean (non-injected) cash balances should differ somewhere.
    assert [r.gl_balance for r in a.gl_records] != [r.gl_balance for r in b.gl_records]


# --------------------------------------------------------------------------
# structure / metadata
# --------------------------------------------------------------------------
def test_period_and_statement_date(ds: SyntheticDataset) -> None:
    assert ds.period == "March 2026"
    assert ds.statement_date == "2026-03-31"


def test_gl_record_count_includes_dormant(ds: SyntheticDataset) -> None:
    # 4 entities x (1 cash + 1 debt) + 1 injected dormant cash account = 9.
    assert len(ds.gl_records) == 9


def test_account_types_are_only_cash_or_debt(ds: SyntheticDataset) -> None:
    assert {r.account_type for r in ds.gl_records} <= {"cash", "debt"}


def test_account_numbers_are_unique(ds: SyntheticDataset) -> None:
    nums = [r.account_number for r in ds.gl_records]
    assert len(nums) == len(set(nums))


def test_gl_records_sorted_stably(ds: SyntheticDataset) -> None:
    key = [(r.entity, r.account_type, r.account_number) for r in ds.gl_records]
    assert key == sorted(key)


def test_bank_statements_sorted_by_account(ds: SyntheticDataset) -> None:
    nums = [b.account_number for b in ds.bank_statements]
    assert nums == sorted(nums)


def test_lender_statements_sorted_by_account(ds: SyntheticDataset) -> None:
    nums = [ln.account_number for ln in ds.lender_statements]
    assert nums == sorted(nums)


def test_injected_sorted_by_account(ds: SyntheticDataset) -> None:
    nums = [d.account_number for d in ds.injected]
    assert nums == sorted(nums)


@pytest.mark.parametrize(
    "acct",
    ["CASH-1000", "CASH-1001", "CASH-1002", "CASH-1003", "DEBT-2000", "DEBT-2001"],
)
def test_expected_account_numbers_present(ds: SyntheticDataset, acct: str) -> None:
    assert any(r.account_number == acct for r in ds.gl_records)


def test_every_cash_gl_has_a_bank_row(ds: SyntheticDataset) -> None:
    bank_accts = {b.account_number for b in ds.bank_statements}
    for r in ds.gl_records:
        if r.account_type == "cash":
            assert r.account_number in bank_accts


def test_every_debt_gl_has_a_lender_row(ds: SyntheticDataset) -> None:
    lender_accts = {ln.account_number for ln in ds.lender_statements}
    for r in ds.gl_records:
        if r.account_type == "debt":
            assert r.account_number in lender_accts


def test_money_values_are_cent_rounded(ds: SyntheticDataset) -> None:
    for r in ds.gl_records:
        assert round(r.gl_balance, 2) == r.gl_balance
    for b in ds.bank_statements:
        assert round(b.ending_balance, 2) == b.ending_balance


# --------------------------------------------------------------------------
# injected discrepancies (the deterministic, seeded scenario)
# --------------------------------------------------------------------------
def test_injected_kinds(ds: SyntheticDataset) -> None:
    assert {d.kind for d in ds.injected} == {"deposit_in_transit", "timing", "error"}


def test_exactly_three_injected(ds: SyntheticDataset) -> None:
    assert len(ds.injected) == 3


def test_deposit_in_transit_makes_bank_exceed_gl(ds: SyntheticDataset) -> None:
    """CASH-1001 bank ending is GL + $1,875.40 (deposit not yet booked)."""
    gl = _gl_by_acct(ds, "CASH-1001").gl_balance
    bank = _bank_by_acct(ds, "CASH-1001").ending_balance
    assert round(bank - gl, 2) == 1_875.40


def test_timing_injection_is_small(ds: SyntheticDataset) -> None:
    """DEBT-2002 GL exceeds the lender 3-part total by exactly $18.75."""
    gl = _gl_by_acct(ds, "DEBT-2002").gl_balance
    ln = _lender_by_acct(ds, "DEBT-2002")
    total = round(ln.principal + ln.current_interest_reserve + ln.late_paydown, 2)
    assert round(gl - total, 2) == 18.75


def test_error_injection_is_large(ds: SyntheticDataset) -> None:
    """DEBT-2003 GL overstated by exactly $12,500.00."""
    gl = _gl_by_acct(ds, "DEBT-2003").gl_balance
    ln = _lender_by_acct(ds, "DEBT-2003")
    total = round(ln.principal + ln.current_interest_reserve + ln.late_paydown, 2)
    assert round(gl - total, 2) == 12_500.00


def test_late_paydown_leg_populated_and_ties(ds: SyntheticDataset) -> None:
    """DEBT-2000 exercises the 3rd leg ($7,500) and still ties to GL."""
    ln = _lender_by_acct(ds, "DEBT-2000")
    gl = _gl_by_acct(ds, "DEBT-2000").gl_balance
    assert ln.late_paydown == 7_500.00
    total = round(ln.principal + ln.current_interest_reserve + ln.late_paydown, 2)
    assert gl == total


def test_dormant_account_injected(ds: SyntheticDataset) -> None:
    dormant = [r for r in ds.gl_records if r.dormant]
    assert len(dormant) == 1
    rec = dormant[0]
    assert rec.account_number == "CASH-1900"
    assert rec.gl_balance == 0.0


def test_dormant_account_has_zero_bank_row(ds: SyntheticDataset) -> None:
    bank = _bank_by_acct(ds, "CASH-1900")
    assert bank.ending_balance == 0.0


def test_injected_notes_are_nonempty(ds: SyntheticDataset) -> None:
    for d in ds.injected:
        assert d.note.strip() != ""
        assert d.entity.strip() != ""


# --------------------------------------------------------------------------
# record lookup / replace helpers
# --------------------------------------------------------------------------
def test_bank_by_acct_returns_match(ds: SyntheticDataset) -> None:
    b = _bank_by_acct(ds, "CASH-1000")
    assert b.account_number == "CASH-1000"


def test_bank_by_acct_raises_on_missing(ds: SyntheticDataset) -> None:
    with pytest.raises(KeyError):
        _bank_by_acct(ds, "CASH-NOPE")


def test_lender_by_acct_raises_on_missing(ds: SyntheticDataset) -> None:
    with pytest.raises(KeyError):
        _lender_by_acct(ds, "DEBT-NOPE")


def test_gl_by_acct_raises_on_missing(ds: SyntheticDataset) -> None:
    with pytest.raises(KeyError):
        _gl_by_acct(ds, "ZZZ")


def test_replace_bank_swaps_only_target() -> None:
    local = generate_dataset(seed=42)
    original_count = len(local.bank_statements)
    new = BankStatement(
        account_number="CASH-1000",
        bank_name="Swapped Bank",
        statement_date="2026-03-31",
        ending_balance=1.0,
    )
    _replace_bank(local, new)
    assert len(local.bank_statements) == original_count
    assert _bank_by_acct(local, "CASH-1000").bank_name == "Swapped Bank"
    assert _bank_by_acct(local, "CASH-1000").ending_balance == 1.0


def test_replace_lender_swaps_only_target() -> None:
    local = generate_dataset(seed=42)
    new = LenderStatement(
        account_number="DEBT-2000",
        lender_name="Swapped Lender",
        statement_date="2026-03-31",
        principal=1.0,
        current_interest_reserve=0.0,
        late_paydown=0.0,
    )
    _replace_lender(local, new)
    assert _lender_by_acct(local, "DEBT-2000").lender_name == "Swapped Lender"


def test_replace_gl_swaps_only_target() -> None:
    local = generate_dataset(seed=42)
    target = _gl_by_acct(local, "CASH-1000")
    new = GLRecord(
        entity=target.entity,
        account_type=target.account_type,
        account_number="CASH-1000",
        description=target.description,
        gl_balance=777.0,
    )
    _replace_gl(local, new)
    assert _gl_by_acct(local, "CASH-1000").gl_balance == 777.0


def test_dataclasses_are_frozen() -> None:
    """GLRecord / BankStatement / LenderStatement are immutable (frozen=True)."""
    rec = GLRecord("E", "cash", "C", "d", 1.0)
    with pytest.raises(Exception):
        rec.gl_balance = 2.0  # type: ignore[misc]
    bank = BankStatement("C", "B", "2026-03-31", 1.0)
    with pytest.raises(Exception):
        bank.ending_balance = 2.0  # type: ignore[misc]
