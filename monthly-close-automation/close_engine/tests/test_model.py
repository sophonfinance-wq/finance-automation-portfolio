"""Tests for the data model and the hard balance control."""

from __future__ import annotations

import pytest

from close_engine.generate import chart_of_accounts
from close_engine.model import (
    JournalEntry,
    JournalLine,
    Ledger,
    OutOfTieError,
)


def _entry(lines: list[JournalLine]) -> JournalEntry:
    return JournalEntry("JE-TEST", "2026-03", "test", "test entry", lines)


def test_balanced_entry_posts() -> None:
    coa = chart_of_accounts()
    ledger = Ledger(coa)
    je = _entry(
        [
            JournalLine("DH", "6100", 1000, 0, "expense"),
            JournalLine("DH", "1510", 0, 1000, "accum dep"),
        ]
    )
    assert je.is_balanced
    ledger.post(je)
    assert ledger.balance("DH", "6100") == 1000
    assert ledger.balance("DH", "1510") == -1000
    assert je in ledger.posted


def test_out_of_tie_entry_is_refused() -> None:
    coa = chart_of_accounts()
    ledger = Ledger(coa)
    je = _entry(
        [
            JournalLine("DH", "6100", 1000, 0, "expense"),
            JournalLine("DH", "1510", 0, 900, "accum dep"),  # off by 100
        ]
    )
    assert not je.is_balanced
    assert je.out_of_tie == 100
    with pytest.raises(OutOfTieError):
        ledger.post(je)
    # Nothing posted.
    assert ledger.posted == []
    assert ledger.balance("DH", "6100") == 0


def test_entity_leg_must_balance_for_intercompany() -> None:
    """Aggregate balance is not enough: each entity leg must self-balance."""
    coa = chart_of_accounts()
    ledger = Ledger(coa)
    # Aggregate balances (2000 == 2000) but neither entity leg does.
    je = _entry(
        [
            JournalLine("DH", "6100", 2000, 0, "DH expense"),
            JournalLine("MF", "2100", 0, 2000, "MF credit"),
        ]
    )
    assert je.is_balanced  # aggregate ok
    assert je.balances_per_entity() == {"DH": 2000, "MF": -2000}
    with pytest.raises(OutOfTieError):
        ledger.post(je, require_entity_balance=True)


def test_trial_balance_in_balance() -> None:
    coa = chart_of_accounts()
    ledger = Ledger(coa)
    ledger.load_opening(
        [
            JournalLine("DH", "1000", 5000, 0, "cash"),
            JournalLine("DH", "3000", 0, 5000, "equity"),
        ]
    )
    debits, credits = ledger.total_debits_credits()
    assert debits == credits == 5000
