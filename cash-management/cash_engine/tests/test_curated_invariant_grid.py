"""Curated invariant grid for the five cash-manager validators (5,000 cases).

Each parametrized case drives one of the real validators END-TO-END twice:
once on a constructed-to-tie input that must come back mechanically clean, and
once on a one-cent (or one-field) tamper of the same input that must trip the
exact finding code. Both sides are asserted from independently re-derived
integer-cent arithmetic, so a validator stub that always passes (or always
fails) cannot survive any point of the grid.

1,000 cases per validator x 5 validators = 5,000 curated cases:

* bank_rec              — adjusted-bank == adjusted-book bridge
* outstanding_checks    — outstanding-total crossfoot (outstanding + stale)
* wire_approval         — dual-approval / segregation-of-duties
* bank_register         — running-balance continuity + closing foot
* cash_concentration    — sweep tie-out + concentration roll-forward
"""

from __future__ import annotations

import itertools

import pytest

from cash_engine.bank_rec import BankReconciliation, BankReconciliationValidator
from cash_engine.outstanding_checks import CheckRecord, OutstandingCheckValidator
from cash_engine.wire_approval import WireRequest, WireApprovalValidator
from cash_engine.bank_register import (
    BankRegister,
    BankRegisterValidator,
    RegisterTransaction,
)
from cash_engine.cash_concentration import (
    CashConcentrationValidator,
    ConcentrationAccount,
    SweepLine,
)

PERIOD = "2026-06"

# ---------------------------------------------------------------------------
# 1. bank_rec — 10 x 10 x 10 = 1,000 (bank, deposits-in-transit, outstanding)
# ---------------------------------------------------------------------------
_BANK = [-250_000, -1, 0, 1, 99, 5_000, 123_456, 1_000_000, 7_654_321, 99_999_999]
_DIT = [0, 1, 50, 999, 7_500, 12_345, 100_000, 654_321, 5_000_000, 43_210_987]
_OC = [0, 1, 49, 500, 9_999, 87_654, 250_000, 1_111_111, 9_876_543, 55_555_555]


@pytest.mark.parametrize("bank,dit,oc", list(itertools.product(_BANK, _DIT, _OC)))
def test_bank_rec_bridge_grid(bank: int, dit: int, oc: int) -> None:
    gl = bank + dit - oc  # constructed so adjusted bank == adjusted book
    rec = BankReconciliation(
        entity="Cedar Demo LLC",
        account="CASH-1001",
        bank_name="Demo National Bank",
        bank_ending_cents=bank,
        gl_balance_cents=gl,
        deposits_in_transit_cents=dit,
        outstanding_checks_cents=oc,
        displayed_adjusted_cents=gl,
    )
    clean = BankReconciliationValidator(PERIOD, (rec,)).run()
    assert clean.mechanical_clean
    assert clean.tied_count == 1 and clean.out_of_tie_count == 0

    # One-cent tamper on the GL side must break the bridge — and only it.
    from dataclasses import replace

    broken = BankReconciliationValidator(
        PERIOD, (replace(rec, gl_balance_cents=gl + 1, displayed_adjusted_cents=None),)
    ).run()
    assert broken.out_of_tie_count == 1
    assert "RECONCILIATION_OUT_OF_TIE" in {f.code for f in broken.findings}


# ---------------------------------------------------------------------------
# 2. outstanding_checks — 10 x 10 x 10 = 1,000 (two amounts x check count)
# ---------------------------------------------------------------------------
_AMT_A = [1, 2, 99, 500, 1_234, 9_999, 50_000, 123_456, 2_500_000, 99_999_999]
_AMT_B = [1, 3, 77, 450, 6_789, 10_001, 49_999, 654_321, 7_777_777, 12_345_678]
_N_CLEARED = list(range(10))


@pytest.mark.parametrize(
    "amt_a,amt_b,n_cleared", list(itertools.product(_AMT_A, _AMT_B, _N_CLEARED))
)
def test_outstanding_total_crossfoot_grid(amt_a: int, amt_b: int, n_cleared: int) -> None:
    checks = [
        CheckRecord("Cedar Demo LLC", "CASH-1001", "1001", "Demo Vendor", "2026-06-05", amt_a, "outstanding"),
        CheckRecord("Cedar Demo LLC", "CASH-1001", "1002", "Demo Vendor", "2026-06-06", amt_b, "outstanding"),
    ] + [
        CheckRecord("Cedar Demo LLC", "CASH-1001", f"2{i:03d}", "Demo Vendor", "2026-06-07", 100 + i, "cleared")
        for i in range(n_cleared)
    ]
    total = amt_a + amt_b  # cleared checks must NOT count toward outstanding
    clean = OutstandingCheckValidator(PERIOD, "2026-06-30", 180, checks, total).run()
    assert clean.mechanical_clean
    assert clean.outstanding_total_cents == total
    assert clean.outstanding_count == 2 and clean.cleared_count == n_cleared

    broken = OutstandingCheckValidator(PERIOD, "2026-06-30", 180, checks, total + 1).run()
    assert "OUTSTANDING_TOTAL_OUT_OF_TIE" in {f.code for f in broken.findings}


# ---------------------------------------------------------------------------
# 3. wire_approval — 20 x 50 = 1,000 (amount x distinct-people naming)
# ---------------------------------------------------------------------------
_W_AMT = [1, 2, 500, 999, 12_345, 50_000, 99_999, 123_456, 777_777, 1_000_000,
          2_222_222, 5_000_000, 9_999_999, 10_000_001, 33_333_333, 55_555_555,
          77_777_777, 99_999_999, 123_456_789, 999_999_999]
_W_IDX = list(range(50))


@pytest.mark.parametrize("amount,idx", list(itertools.product(_W_AMT, _W_IDX)))
def test_wire_dual_approval_grid(amount: int, idx: int) -> None:
    wire = WireRequest(
        wire_id=f"WIRE-{idx:04d}",
        entity="Cedar Demo LLC",
        beneficiary="Demo Vendor LLC",
        amount_cents=amount,
        initiator=f"Initiator {idx}",
        first_approver=f"Approver A{idx}",
        second_approver=f"Approver B{idx}",
        status="approved",
        request_date="2026-06-10",
    )
    clean = WireApprovalValidator(PERIOD, (wire,)).run()
    assert clean.mechanical_clean
    assert clean.approved_count == 1 and clean.blocked_count == 0

    from dataclasses import replace

    # Second approver identical to the initiator => segregation breach.
    self_approved = WireApprovalValidator(
        PERIOD, (replace(wire, second_approver=f"Initiator {idx}"),)
    ).run()
    assert "SELF_APPROVAL" in {f.code for f in self_approved.findings}
    assert self_approved.blocked_count == 1

    # Missing second approver on an approved wire => control failure.
    unapproved = WireApprovalValidator(PERIOD, (replace(wire, second_approver=""),)).run()
    assert "MISSING_SECONDARY_APPROVAL" in {f.code for f in unapproved.findings}


# ---------------------------------------------------------------------------
# 4. bank_register — 10 x 10 x 10 = 1,000 (opening x two signed amounts)
# ---------------------------------------------------------------------------
_OPEN = [-500_000, -1, 0, 1, 100, 9_999, 123_456, 1_000_000, 43_210_987, 99_999_999]
_TX1 = [-99_999_999, -123_456, -500, -1, 0, 1, 999, 55_555, 2_500_000, 87_654_321]
_TX2 = [-12_345_678, -54_321, -100, -1, 0, 1, 777, 10_000, 999_999, 11_111_111]


@pytest.mark.parametrize("opening,tx1,tx2", list(itertools.product(_OPEN, _TX1, _TX2)))
def test_bank_register_continuity_grid(opening: int, tx1: int, tx2: int) -> None:
    r1 = opening + tx1
    r2 = r1 + tx2  # independently re-derived closing
    register = BankRegister(
        entity="Cedar Demo LLC",
        account="CASH-1001",
        period=PERIOD,
        opening_balance_cents=opening,
        transactions=(
            RegisterTransaction("TXN-001", "2026-06-03", tx1, r1),
            RegisterTransaction("TXN-002", "2026-06-17", tx2, r2),
        ),
        displayed_closing_cents=r2,
        prior_closing_cents=opening,
        bank_statement_ending_cents=r2,
    )
    clean = BankRegisterValidator(register).run()
    assert clean.mechanical_clean
    assert clean.rederived_closing_cents == r2
    assert clean.out_of_tie_row_count == 0

    from dataclasses import replace

    # One-cent tamper on the first running balance must break row continuity.
    broken = BankRegisterValidator(
        replace(
            register,
            transactions=(
                RegisterTransaction("TXN-001", "2026-06-03", tx1, r1 + 1),
                RegisterTransaction("TXN-002", "2026-06-17", tx2, r2),
            ),
        )
    ).run()
    assert "RUNNING_BALANCE_OUT_OF_TIE" in {f.code for f in broken.findings}
    assert broken.out_of_tie_row_count >= 1


# ---------------------------------------------------------------------------
# 5. cash_concentration — 10 x 10 x 10 = 1,000 (opening x two sweep legs)
# ---------------------------------------------------------------------------
_C_OPEN = [0, 1, 500, 9_999, 100_000, 1_234_567, 10_000_000, 55_555_555, 99_999_999, 123_456_789]
_SWEEP_A = [0, 1, 250, 4_999, 65_432, 500_000, 1_000_001, 24_999_999, 50_000_000, 87_654_321]
_SWEEP_B = [0, 2, 749, 5_001, 34_568, 750_000, 1_999_999, 25_000_001, 49_999_999, 12_345_679]


@pytest.mark.parametrize(
    "opening,sweep_a,sweep_b", list(itertools.product(_C_OPEN, _SWEEP_A, _SWEEP_B))
)
def test_cash_concentration_grid(opening: int, sweep_a: int, sweep_b: int) -> None:
    sweeps_in = sweep_a + sweep_b
    disbursements = min(opening, sweeps_in)  # never overdraw; varies with the grid
    closing = opening + sweeps_in - disbursements
    account = ConcentrationAccount(
        entity="Cedar Demo LLC",
        account="CASH-1900",
        period=PERIOD,
        opening_cents=opening,
        sweeps_in_cents=sweeps_in,
        disbursements_cents=disbursements,
        displayed_closing_cents=closing,
    )
    lines = (SweepLine("CASH-1001", sweep_a), SweepLine("CASH-1002", sweep_b))
    clean = CashConcentrationValidator(account, lines).run()
    assert clean.mechanical_clean
    assert clean.swept_total_cents == sweeps_in
    assert clean.rederived_closing_cents == closing

    from dataclasses import replace

    # A one-cent short sweep must break the sweep tie-out.
    short = CashConcentrationValidator(
        replace(account, sweeps_in_cents=sweeps_in + 1, displayed_closing_cents=closing + 1),
        lines,
    ).run()
    assert "SWEEP_TIE_OUT" in {f.code for f in short.findings}

    # A one-cent tamper on the displayed closing must break the roll-forward.
    drifted = CashConcentrationValidator(
        replace(account, displayed_closing_cents=closing + 1), lines
    ).run()
    assert "CONCENTRATION_ROLLFORWARD_OUT_OF_TIE" in {f.code for f in drifted.findings}
