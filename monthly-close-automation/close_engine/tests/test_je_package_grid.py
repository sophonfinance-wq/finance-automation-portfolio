"""Curated invariant grid for the monthly JE support-package validator.

Generates a Cartesian product of entry counts x base amounts x spreads x line
shapes (~1,000 cases) of fully fictional, balanced journal-entry packages. Each
case asserts the load-bearing invariants: a balanced package is mechanically
clean and `READY FOR HUMAN REVIEW`, every entry is counted as balanced, none is
out of balance, and the package debit/credit totals equal an independent re-add.
Two- and three-line entries exercise both single-offset and multi-line balance.

All data is fictional and generated at import time; the file stays small.
"""

from __future__ import annotations

import itertools

import pytest

from close_engine.je_package import JournalEntry, JournalEntryPackage, JournalLine, JournalPackageValidator


_ENTRY_COUNTS = range(1, 21)                       # 20 values
_BASES = [100, 2500, 40000, 750000, 1000000]       # 5 values (integer cents)
_SPREADS = [0, 1, 5, 25, 100]                      # 5 values
_LINE_SHAPES = [2, 3]                              # 2 values
_GRID = list(itertools.product(_ENTRY_COUNTS, _BASES, _SPREADS, _LINE_SHAPES))  # 1,000


def _entry(index: int, base: int, spread: int, shape: int):
    amount = base + spread * index
    if shape == 2:
        lines = (
            JournalLine(f"ACCT-D{index}", "debit line", amount, 0),
            JournalLine(f"ACCT-C{index}", "credit line", 0, amount),
        )
        debit = credit = amount
    else:
        second = amount + 7
        lines = (
            JournalLine(f"ACCT-D{index}", "debit line one", amount, 0),
            JournalLine(f"ACCT-E{index}", "debit line two", second, 0),
            JournalLine(f"ACCT-C{index}", "credit line", 0, amount + second),
        )
        debit = credit = amount + second
    entry = JournalEntry(
        entry_id=f"JE-{index:03d}",
        period="2026-06",
        lines=lines,
        cached_debit_total_cents=debit,
        cached_credit_total_cents=credit,
    )
    return entry, debit, credit


@pytest.mark.parametrize("count,base,spread,shape", _GRID)
def test_balanced_je_package_holds_every_invariant(count, base, spread, shape):
    entries = []
    total_debit = total_credit = 0
    for index in range(count):
        entry, debit, credit = _entry(index, base, spread, shape)
        entries.append(entry)
        total_debit += debit
        total_credit += credit
    package = JournalEntryPackage(period="2026-06", entries=tuple(entries), source_fingerprint="a" * 64)
    result = JournalPackageValidator(package).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.entry_count == count
    assert result.balanced_entry_count == count
    assert result.out_of_balance_count == 0
    assert result.total_debits_cents == total_debit
    assert result.total_credits_cents == total_credit
    assert result.validation_only
    assert not result.posting_authorized
