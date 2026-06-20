"""Additional engine coverage: variance, classification, reconcile flows, invariants.

These tests exercise the real ``recon_engine.engine`` API across boundary values,
the missing-statement and zero-activity branches, flag-id assignment, and the
``ReconResult`` aggregation properties.
"""

from __future__ import annotations

import pytest

from recon_engine import MATERIALITY_THRESHOLD
from recon_engine.engine import (
    TIE_TOLERANCE,
    ReconLine,
    ReconResult,
    classify,
    compute_variance,
    lender_three_part_total,
    reconcile,
    _is_zero_activity,
    _skip_line,
)
from recon_engine.generate import (
    BankStatement,
    GLRecord,
    LenderStatement,
    SyntheticDataset,
    generate_dataset,
)


# --------------------------------------------------------------------------
# compute_variance: sign, rounding, anti-symmetry
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("gl", "source", "expected"),
    [
        (0.0, 0.0, 0.0),
        (100.0, 100.0, 0.0),
        (100.0, 0.0, 100.0),
        (0.0, 100.0, -100.0),
        (250.5, 250.25, 0.25),
        (1.005, 0.0, 1.0),          # banker-ish: 1.005 rounds to 1.0 under round()
        (1.015, 0.0, 1.01),         # round-half-to-even residue
        (-50.0, -75.0, 25.0),
        (-75.0, -50.0, -25.0),
        (1_000_000.0, 999_999.99, 0.01),
    ],
)
def test_compute_variance_cases(gl: float, source: float, expected: float) -> None:
    assert compute_variance(gl, source) == expected


@pytest.mark.parametrize(
    ("gl", "source"),
    [
        (100.0, 90.0),
        (482_150.22, 480_000.00),
        (0.0, 12.34),
        (-5.0, 5.0),
    ],
)
def test_compute_variance_is_antisymmetric(gl: float, source: float) -> None:
    """variance(a, b) == -variance(b, a) for cent-clean inputs."""
    assert compute_variance(gl, source) == -compute_variance(source, gl)


def test_compute_variance_returns_float_for_float_inputs() -> None:
    assert isinstance(compute_variance(3.0, 1.0), float)


# --------------------------------------------------------------------------
# classify: boundaries around tie-tolerance and the threshold
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("variance", "threshold", "expected"),
    [
        (0.0, 50.0, "clean"),
        (TIE_TOLERANCE, 50.0, "clean"),         # exactly at tie tolerance
        (-TIE_TOLERANCE, 50.0, "clean"),        # sign-independent tie
        (TIE_TOLERANCE + 0.001, 50.0, "timing"),  # just past tie -> timing
        (49.99, 50.0, "timing"),
        (50.0, 50.0, "timing"),                 # exactly at threshold -> timing
        (-50.0, 50.0, "timing"),
        (50.01, 50.0, "flag"),                  # just over -> flag
        (1_000.0, 50.0, "flag"),
        (-1_000.0, 50.0, "flag"),
        (10.0, 0.0, "flag"),                    # zero threshold -> anything non-tie flags
        (0.0, 0.0, "clean"),                    # tie even with zero threshold
        (5.0, 5.0, "timing"),                   # at custom threshold
    ],
)
def test_classify_boundaries(variance: float, threshold: float, expected: str) -> None:
    assert classify(variance, threshold) == expected


def test_classify_is_magnitude_based() -> None:
    """Positive and negative variances of equal magnitude classify identically."""
    for mag in (0.02, 25.0, 49.99, 50.0, 75.0, 12_500.0):
        assert classify(mag, 50.0) == classify(-mag, 50.0)


# --------------------------------------------------------------------------
# lender_three_part_total
# --------------------------------------------------------------------------
def _lender(principal: float, interest: float, paydown: float) -> LenderStatement:
    return LenderStatement(
        account_number="DEBT-TEST",
        lender_name="Probe Lender",
        statement_date="2026-03-31",
        principal=principal,
        current_interest_reserve=interest,
        late_paydown=paydown,
    )


@pytest.mark.parametrize(
    ("principal", "interest", "paydown", "expected"),
    [
        (1_000_000.0, 5_000.0, 7_500.0, 1_012_500.0),
        (1_250_000.0, 0.0, 0.0, 1_250_000.0),
        (100.10, 0.20, 0.05, 100.35),
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 9_999.99, 9_999.99),
        (250_000.005, 0.0, 0.0, 250_000.01),  # float repr of .005 rounds up
    ],
)
def test_three_part_total_cases(
    principal: float, interest: float, paydown: float, expected: float
) -> None:
    assert lender_three_part_total(_lender(principal, interest, paydown)) == expected


def test_three_part_total_equals_compute_variance_zero_when_gl_matches() -> None:
    stmt = _lender(800_000.0, 4_321.0, 1_000.0)
    total = lender_three_part_total(stmt)
    assert compute_variance(total, total) == 0.0


# --------------------------------------------------------------------------
# reconcile: cash / debt happy paths against a controlled dataset
# --------------------------------------------------------------------------
def _mini_dataset() -> SyntheticDataset:
    """A small, fully controlled dataset (one clean cash + one clean debt)."""
    ds = SyntheticDataset(period="March 2026", statement_date="2026-03-31")
    ds.gl_records.append(
        GLRecord(
            entity="Probe LLC",
            account_type="cash",
            account_number="CASH-5000",
            description="probe cash",
            gl_balance=10_000.00,
        )
    )
    ds.gl_records.append(
        GLRecord(
            entity="Probe LLC",
            account_type="debt",
            account_number="DEBT-6000",
            description="probe loan",
            gl_balance=500_500.00,
        )
    )
    ds.bank_statements.append(
        BankStatement(
            account_number="CASH-5000",
            bank_name="Probe Bank",
            statement_date="2026-03-31",
            ending_balance=10_000.00,
        )
    )
    ds.lender_statements.append(
        LenderStatement(
            account_number="DEBT-6000",
            lender_name="Probe Lender",
            statement_date="2026-03-31",
            principal=500_000.00,
            current_interest_reserve=500.00,
            late_paydown=0.0,
        )
    )
    return ds


def test_reconcile_clean_cash_line() -> None:
    result = reconcile(_mini_dataset(), threshold=50.0)
    assert len(result.cash_lines) == 1
    ln = result.cash_lines[0]
    assert ln.classification == "clean"
    assert ln.variance == 0.0
    assert ln.gl_balance == 10_000.00
    assert ln.source_balance == 10_000.00
    assert ln.flag_id == ""
    assert "Probe Bank" in ln.source_label


def test_reconcile_clean_debt_line_carries_legs() -> None:
    result = reconcile(_mini_dataset(), threshold=50.0)
    ln = result.debt_lines[0]
    assert ln.classification == "clean"
    assert ln.variance == 0.0
    assert ln.principal == 500_000.00
    assert ln.interest_reserve == 500.00
    assert ln.late_paydown == 0.0
    assert ln.source_balance == 500_500.00


def test_reconcile_cash_flag_when_bank_differs() -> None:
    ds = _mini_dataset()
    ds.bank_statements = [
        BankStatement(
            account_number="CASH-5000",
            bank_name="Probe Bank",
            statement_date="2026-03-31",
            ending_balance=8_000.00,  # GL 10k higher -> +2000 variance, flag
        )
    ]
    result = reconcile(ds, threshold=50.0)
    ln = result.cash_lines[0]
    assert ln.classification == "flag"
    assert ln.variance == 2_000.00
    assert ln.flag_id == "FLAG-001"


def test_reconcile_cash_timing_when_within_threshold() -> None:
    ds = _mini_dataset()
    ds.bank_statements = [
        BankStatement(
            account_number="CASH-5000",
            bank_name="Probe Bank",
            statement_date="2026-03-31",
            ending_balance=9_970.00,  # +30 variance, within $50
        )
    ]
    result = reconcile(ds, threshold=50.0)
    ln = result.cash_lines[0]
    assert ln.classification == "timing"
    assert ln.variance == 30.00
    assert ln.flag_id == ""


def test_reconcile_missing_bank_statement_flags_full_balance() -> None:
    ds = _mini_dataset()
    ds.bank_statements = []  # no bank for CASH-5000
    result = reconcile(ds, threshold=50.0)
    ln = result.cash_lines[0]
    assert ln.source_label == "no bank statement found"
    assert ln.variance == 10_000.00          # entire GL becomes the variance
    assert ln.classification == "flag"       # 10k > 50 threshold
    assert "No matching bank statement" in ln.note


def test_reconcile_missing_bank_small_balance_is_timing() -> None:
    ds = _mini_dataset()
    ds.gl_records = [
        GLRecord(
            entity="Probe LLC",
            account_type="cash",
            account_number="CASH-5000",
            description="tiny cash",
            gl_balance=10.0,  # below threshold
        )
    ]
    ds.bank_statements = []
    ds.lender_statements = []
    result = reconcile(ds, threshold=50.0)
    ln = result.cash_lines[0]
    assert ln.source_label == "no bank statement found"
    assert ln.classification == "timing"


def test_reconcile_missing_lender_statement_flags() -> None:
    ds = _mini_dataset()
    ds.lender_statements = []  # no lender for DEBT-6000
    result = reconcile(ds, threshold=50.0)
    ln = result.debt_lines[0]
    assert ln.source_label == "no lender statement found"
    assert ln.variance == 500_500.00
    assert ln.classification == "flag"
    assert "No matching lender statement" in ln.note


def test_reconcile_targets_by_account_number_not_row() -> None:
    """Shuffling the source order must not change which line ties."""
    ds = _mini_dataset()
    # Add a second cash account whose bank row is listed *before* CASH-5000's.
    ds.gl_records.insert(
        0,
        GLRecord(
            entity="Probe LLC",
            account_type="cash",
            account_number="CASH-5001",
            description="second cash",
            gl_balance=2_222.22,
        ),
    )
    ds.bank_statements.insert(
        0,
        BankStatement(
            account_number="CASH-5001",
            bank_name="Probe Bank",
            statement_date="2026-03-31",
            ending_balance=2_222.22,
        ),
    )
    result = reconcile(ds, threshold=50.0)
    by_acct = {ln.account_number: ln for ln in result.cash_lines}
    assert by_acct["CASH-5000"].variance == 0.0
    assert by_acct["CASH-5001"].variance == 0.0


# --------------------------------------------------------------------------
# zero-activity / skipping branches
# --------------------------------------------------------------------------
def test_dormant_flag_routes_to_skipped() -> None:
    ds = _mini_dataset()
    ds.gl_records.append(
        GLRecord(
            entity="Probe LLC",
            account_type="cash",
            account_number="CASH-9000",
            description="dormant",
            gl_balance=0.0,
            dormant=True,
        )
    )
    result = reconcile(ds, threshold=50.0)
    skipped = {ln.account_number for ln in result.skipped_lines}
    assert "CASH-9000" in skipped
    active = {ln.account_number for ln in result.all_active_lines}
    assert "CASH-9000" not in active


def test_zero_activity_cash_is_skipped_even_without_dormant_flag() -> None:
    ds = SyntheticDataset(period="P", statement_date="2026-03-31")
    ds.gl_records.append(
        GLRecord(
            entity="Z",
            account_type="cash",
            account_number="CASH-0",
            description="zero",
            gl_balance=0.0,
            dormant=False,
        )
    )
    ds.bank_statements.append(
        BankStatement(
            account_number="CASH-0",
            bank_name="B",
            statement_date="2026-03-31",
            ending_balance=0.0,
        )
    )
    result = reconcile(ds, threshold=50.0)
    assert [ln.account_number for ln in result.skipped_lines] == ["CASH-0"]
    assert result.cash_lines == []


def test_is_zero_activity_true_for_matched_zero_debt() -> None:
    rec = GLRecord(
        entity="Z",
        account_type="debt",
        account_number="DEBT-0",
        description="zero loan",
        gl_balance=0.0,
    )
    lenders = {
        "DEBT-0": LenderStatement(
            account_number="DEBT-0",
            lender_name="L",
            statement_date="2026-03-31",
            principal=0.0,
            current_interest_reserve=0.0,
            late_paydown=0.0,
        )
    }
    assert _is_zero_activity(rec, banks={}, lenders=lenders) is True


def test_is_zero_activity_false_when_gl_nonzero() -> None:
    rec = GLRecord(
        entity="Z",
        account_type="cash",
        account_number="CASH-0",
        description="x",
        gl_balance=123.45,
    )
    banks = {
        "CASH-0": BankStatement(
            account_number="CASH-0",
            bank_name="B",
            statement_date="2026-03-31",
            ending_balance=0.0,
        )
    }
    assert _is_zero_activity(rec, banks=banks, lenders={}) is False


def test_is_zero_activity_false_when_source_missing() -> None:
    """A zero GL with no matching source is NOT auto-skipped (returns False)."""
    rec = GLRecord(
        entity="Z",
        account_type="cash",
        account_number="CASH-X",
        description="x",
        gl_balance=0.0,
    )
    assert _is_zero_activity(rec, banks={}, lenders={}) is False


def test_skip_line_shape() -> None:
    rec = GLRecord(
        entity="E",
        account_type="cash",
        account_number="CASH-7",
        description="d",
        gl_balance=999.0,
    )
    sl = _skip_line(rec)
    assert sl.classification == "skipped"
    assert sl.variance == 0.0
    assert sl.source_balance == 0.0
    assert sl.gl_balance == 999.0
    assert "Dormant" in sl.note


# --------------------------------------------------------------------------
# ReconResult aggregation properties & flag-id assignment
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def seeded_result() -> ReconResult:
    return reconcile(generate_dataset(), threshold=MATERIALITY_THRESHOLD)


def test_all_active_lines_excludes_skipped(seeded_result: ReconResult) -> None:
    active_accts = {ln.account_number for ln in seeded_result.all_active_lines}
    skipped_accts = {ln.account_number for ln in seeded_result.skipped_lines}
    assert active_accts.isdisjoint(skipped_accts)


def test_all_active_lines_is_cash_then_debt(seeded_result: ReconResult) -> None:
    expected = [*seeded_result.cash_lines, *seeded_result.debt_lines]
    assert seeded_result.all_active_lines == expected


def test_flagged_property_matches_classification(seeded_result: ReconResult) -> None:
    assert all(ln.classification == "flag" for ln in seeded_result.flagged)
    expected = [
        ln for ln in seeded_result.all_active_lines if ln.classification == "flag"
    ]
    assert seeded_result.flagged == expected


def test_summary_counts_partition_sums(seeded_result: ReconResult) -> None:
    counts = seeded_result.summary_counts()
    # clean + timing + flag == reconciled active total
    assert (
        counts["clean"] + counts["timing"] + counts["flag"]
        == counts["accounts_reconciled"]
    )
    # active + skipped == total in scope
    assert (
        counts["accounts_reconciled"] + counts["skipped"]
        == counts["accounts_total"]
    )
    # cash + debt == active
    assert counts["cash_accounts"] + counts["debt_accounts"] == counts[
        "accounts_reconciled"
    ]


def test_summary_counts_keys(seeded_result: ReconResult) -> None:
    counts = seeded_result.summary_counts()
    assert set(counts) == {
        "accounts_total",
        "accounts_reconciled",
        "cash_accounts",
        "debt_accounts",
        "clean",
        "timing",
        "flag",
        "skipped",
    }


def test_flag_ids_only_on_flagged_lines(seeded_result: ReconResult) -> None:
    for ln in seeded_result.all_active_lines:
        if ln.classification == "flag":
            assert ln.flag_id.startswith("FLAG-")
        else:
            assert ln.flag_id == ""


def test_flag_ids_zero_padded_and_consecutive() -> None:
    """With three flags, ids are FLAG-001..FLAG-003 in active (cash-then-debt) order."""
    ds = _mini_dataset()
    # Make both lines flag and add a third flagged cash line.
    ds.bank_statements = [
        BankStatement("CASH-5000", "B", "2026-03-31", 1.0),  # huge variance
    ]
    ds.lender_statements = []  # debt becomes a flag (no lender)
    ds.gl_records.append(
        GLRecord("Probe LLC", "cash", "CASH-5002", "c", 99_999.0)
    )
    result = reconcile(ds, threshold=50.0)
    ids = [ln.flag_id for ln in result.flagged]
    assert ids == ["FLAG-001", "FLAG-002", "FLAG-003"]


def test_reconcile_threshold_changes_classification() -> None:
    """A line that is 'timing' at $50 becomes 'flag' at a tighter threshold."""
    ds = _mini_dataset()
    ds.bank_statements = [
        BankStatement("CASH-5000", "B", "2026-03-31", 9_960.0)  # +40 variance
    ]
    loose = reconcile(ds, threshold=50.0).cash_lines[0]
    tight = reconcile(ds, threshold=10.0).cash_lines[0]
    assert loose.classification == "timing"
    assert tight.classification == "flag"


def test_empty_dataset_reconciles_to_empty_result() -> None:
    ds = SyntheticDataset(period="P", statement_date="2026-03-31")
    result = reconcile(ds, threshold=50.0)
    assert result.cash_lines == []
    assert result.debt_lines == []
    assert result.skipped_lines == []
    assert result.flagged == []
    counts = result.summary_counts()
    assert counts["accounts_total"] == 0


def test_reconcile_preserves_period_and_date() -> None:
    ds = _mini_dataset()
    result = reconcile(ds, threshold=50.0)
    assert result.period == "March 2026"
    assert result.statement_date == "2026-03-31"
    assert result.threshold == 50.0
