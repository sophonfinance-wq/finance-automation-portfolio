"""Tests proving every injected discrepancy is caught and classified correctly."""

from __future__ import annotations

import pytest

from recon_engine import MATERIALITY_THRESHOLD
from recon_engine.engine import ReconLine, ReconResult, reconcile
from recon_engine.generate import generate_dataset


@pytest.fixture(scope="module")
def result() -> ReconResult:
    dataset = generate_dataset()
    return reconcile(dataset, threshold=MATERIALITY_THRESHOLD)


@pytest.fixture(scope="module")
def by_account(result: ReconResult) -> dict[str, ReconLine]:
    return {ln.account_number: ln for ln in result.all_active_lines}


def test_dataset_is_deterministic() -> None:
    a = generate_dataset(seed=20260331)
    b = generate_dataset(seed=20260331)
    assert [r.gl_balance for r in a.gl_records] == [r.gl_balance for r in b.gl_records]
    assert [s.ending_balance for s in a.bank_statements] == [
        s.ending_balance for s in b.bank_statements
    ]


def test_all_injected_discrepancies_present() -> None:
    dataset = generate_dataset()
    kinds = {d.kind for d in dataset.injected}
    assert kinds == {"deposit_in_transit", "timing", "error"}


def test_deposit_in_transit_is_flagged(by_account: dict[str, ReconLine]) -> None:
    """CASH-1001: bank higher than GL by $1,875.40 -> material flag, GL below source."""
    line = by_account["CASH-1001"]
    assert line.classification == "flag"
    assert line.flag_id != ""
    assert line.variance == pytest.approx(-1_875.40)
    assert line.gl_balance < line.source_balance


def test_timing_difference_is_immaterial(by_account: dict[str, ReconLine]) -> None:
    """DEBT-2002: $18.75 GL accrual not on lender stmt -> timing (within threshold)."""
    line = by_account["DEBT-2002"]
    assert line.classification == "timing"
    assert line.variance == pytest.approx(18.75)
    assert abs(line.variance) <= MATERIALITY_THRESHOLD
    assert line.flag_id == ""


def test_outright_error_is_flagged(by_account: dict[str, ReconLine]) -> None:
    """DEBT-2003: GL overstated by $12,500 -> material flag, GL above source."""
    line = by_account["DEBT-2003"]
    assert line.classification == "flag"
    assert line.flag_id != ""
    assert line.variance == pytest.approx(12_500.0)
    assert line.gl_balance > line.source_balance


def test_late_paydown_leg_exercised_and_ties(by_account: dict[str, ReconLine]) -> None:
    """DEBT-2000: optional 3rd leg populated; GL still ties cleanly."""
    line = by_account["DEBT-2000"]
    assert line.late_paydown == pytest.approx(7_500.0)
    assert line.classification == "clean"
    assert line.variance == 0.0


def test_dormant_account_is_skipped(result: ReconResult) -> None:
    """CASH-1900 dormant zero-activity row skipped with a note, not reconciled."""
    skipped = {ln.account_number for ln in result.skipped_lines}
    assert "CASH-1900" in skipped
    active = {ln.account_number for ln in result.all_active_lines}
    assert "CASH-1900" not in active
    note = next(ln.note for ln in result.skipped_lines if ln.account_number == "CASH-1900")
    assert "dormant" in note.lower()


def test_exactly_two_flags_and_one_timing(result: ReconResult) -> None:
    """Sanity on the seeded scenario: 2 hard flags, 1 timing item."""
    counts = result.summary_counts()
    assert counts["flag"] == 2
    assert counts["timing"] == 1
    assert counts["skipped"] == 1


def test_flag_ids_are_sequential_and_unique(result: ReconResult) -> None:
    ids = [ln.flag_id for ln in result.flagged]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert all(fid.startswith("FLAG-") for fid in ids)


def test_clean_accounts_have_zero_variance(by_account: dict[str, ReconLine]) -> None:
    for line in by_account.values():
        if line.classification == "clean":
            assert line.variance == 0.0
