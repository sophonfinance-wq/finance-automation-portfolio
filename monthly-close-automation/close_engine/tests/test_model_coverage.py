"""Additional coverage for the accounting data model.

Covers the AccountType normal-balance classification, Account/JournalLine/
JournalEntry value semantics and balance properties, the OutOfTieError message,
ChartOfAccounts membership/iteration/lookup, and Ledger posting, balances,
trial-balance presentation, and totals — including the per-entity balance
control for intercompany entries.
"""

from __future__ import annotations

import pytest

from close_engine.generate import chart_of_accounts
from close_engine.model import (
    Account,
    AccountType,
    ChartOfAccounts,
    JournalEntry,
    JournalLine,
    Ledger,
    OutOfTieError,
)


def _entry(lines: list[JournalLine], je_id: str = "JE-TEST") -> JournalEntry:
    return JournalEntry(je_id, "2026-03", "test", "test entry", lines)


# --------------------------------------------------------------------------- #
# AccountType normal-balance classification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "acct_type, normal_is_debit",
    [
        (AccountType.ASSET, True),
        (AccountType.EXPENSE, True),
        (AccountType.LIABILITY, False),
        (AccountType.EQUITY, False),
        (AccountType.REVENUE, False),
    ],
)
def test_account_type_normal_is_debit(acct_type, normal_is_debit) -> None:
    assert acct_type.normal_is_debit is normal_is_debit


@pytest.mark.parametrize(
    "acct_type, value",
    [
        (AccountType.ASSET, "asset"),
        (AccountType.LIABILITY, "liability"),
        (AccountType.EQUITY, "equity"),
        (AccountType.REVENUE, "revenue"),
        (AccountType.EXPENSE, "expense"),
    ],
)
def test_account_type_str_value(acct_type, value) -> None:
    # AccountType is a str-Enum, so it compares equal to its string value.
    assert acct_type == value
    assert acct_type.value == value


# --------------------------------------------------------------------------- #
# Account
# --------------------------------------------------------------------------- #


def test_account_label_format() -> None:
    acct = Account("1400", "Prepaid expenses", AccountType.ASSET)
    assert acct.label == "1400 · Prepaid expenses"
    assert acct.label.startswith("1400")
    assert acct.label.endswith("Prepaid expenses")


def test_account_is_frozen() -> None:
    acct = Account("1000", "Cash", AccountType.ASSET)
    with pytest.raises(Exception):
        acct.code = "9999"  # type: ignore[misc]


def test_account_equality_by_value() -> None:
    a = Account("1000", "Cash", AccountType.ASSET)
    b = Account("1000", "Cash", AccountType.ASSET)
    c = Account("1000", "Cash", AccountType.LIABILITY)
    assert a == b
    assert a != c


# --------------------------------------------------------------------------- #
# JournalLine / JournalEntry properties
# --------------------------------------------------------------------------- #


def test_journal_line_default_memo_is_empty() -> None:
    line = JournalLine("DH", "1000", 100, 0)
    assert line.memo == ""


def test_journal_entry_totals_and_balance() -> None:
    je = _entry(
        [
            JournalLine("DH", "6100", 1500, 0, "a"),
            JournalLine("DH", "6200", 500, 0, "b"),
            JournalLine("DH", "1510", 0, 2000, "c"),
        ]
    )
    assert je.total_debits == 2000
    assert je.total_credits == 2000
    assert je.is_balanced is True
    assert je.out_of_tie == 0


@pytest.mark.parametrize(
    "debit, credit, expected_out_of_tie, balanced",
    [
        (1000, 1000, 0, True),
        (1000, 900, 100, False),
        (900, 1000, -100, False),
        (0, 0, 0, True),
    ],
)
def test_journal_entry_out_of_tie_signed(
    debit, credit, expected_out_of_tie, balanced
) -> None:
    je = _entry(
        [
            JournalLine("DH", "6100", debit, 0, "dr"),
            JournalLine("DH", "1510", 0, credit, "cr"),
        ]
    )
    assert je.out_of_tie == expected_out_of_tie
    assert je.is_balanced is balanced


def test_journal_entry_empty_is_balanced() -> None:
    je = _entry([])
    assert je.total_debits == 0
    assert je.total_credits == 0
    assert je.is_balanced is True


def test_journal_entry_entities_distinct() -> None:
    je = _entry(
        [
            JournalLine("DH", "6100", 100, 0, "a"),
            JournalLine("MF", "6100", 100, 0, "b"),
            JournalLine("DH", "1510", 0, 200, "c"),
        ]
    )
    assert je.entities() == {"DH", "MF"}


def test_journal_entry_balances_per_entity_signed() -> None:
    je = _entry(
        [
            JournalLine("DH", "6100", 300, 0, "a"),
            JournalLine("MF", "2100", 0, 300, "b"),
        ]
    )
    assert je.balances_per_entity() == {"DH": 300, "MF": -300}


def test_journal_entry_balances_per_entity_each_zero_when_self_balanced() -> None:
    je = _entry(
        [
            JournalLine("DH", "6100", 100, 0, "a"),
            JournalLine("DH", "1510", 0, 100, "b"),
            JournalLine("MF", "6100", 50, 0, "c"),
            JournalLine("MF", "1510", 0, 50, "d"),
        ]
    )
    assert je.balances_per_entity() == {"DH": 0, "MF": 0}


# --------------------------------------------------------------------------- #
# OutOfTieError
# --------------------------------------------------------------------------- #


def test_out_of_tie_error_carries_je_and_detail() -> None:
    je = _entry([JournalLine("DH", "6100", 100, 0, "x")], je_id="JE-OOT")
    err = OutOfTieError(je, "off by 100")
    assert err.je is je
    assert err.detail == "off by 100"
    assert "JE-OOT" in str(err)
    assert "off by 100" in str(err)
    assert isinstance(err, Exception)


# --------------------------------------------------------------------------- #
# ChartOfAccounts
# --------------------------------------------------------------------------- #


def test_chart_membership_and_lookup() -> None:
    coa = chart_of_accounts()
    assert "1400" in coa
    assert "9999" not in coa
    assert coa.get("1400").name == "Prepaid expenses"


def test_chart_get_unknown_raises_keyerror() -> None:
    coa = chart_of_accounts()
    with pytest.raises(KeyError):
        coa.get("0000")


def test_chart_iteration_yields_accounts() -> None:
    coa = chart_of_accounts()
    accounts = list(coa)
    assert len(accounts) == 31
    assert all(isinstance(a, Account) for a in accounts)
    codes = {a.code for a in accounts}
    assert {"1000", "1400", "1450", "6600", "6650"} <= codes


def test_chart_built_from_custom_accounts() -> None:
    coa = ChartOfAccounts(
        [
            Account("1000", "Cash", AccountType.ASSET),
            Account("3000", "Equity", AccountType.EQUITY),
        ]
    )
    assert "1000" in coa
    assert "2000" not in coa
    assert len(list(coa)) == 2


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def test_ledger_post_updates_signed_balances() -> None:
    ledger = Ledger(chart_of_accounts())
    je = _entry(
        [
            JournalLine("DH", "1000", 5000, 0, "cash up"),
            JournalLine("DH", "4000", 0, 5000, "revenue"),
        ]
    )
    ledger.post(je)
    assert ledger.balance("DH", "1000") == 5000  # debit positive
    assert ledger.balance("DH", "4000") == -5000  # credit negative
    assert je in ledger.posted


def test_ledger_balance_unknown_key_is_zero() -> None:
    ledger = Ledger(chart_of_accounts())
    assert ledger.balance("XX", "9999") == 0


def test_ledger_load_opening_accumulates() -> None:
    ledger = Ledger(chart_of_accounts())
    ledger.load_opening(
        [
            JournalLine("DH", "1000", 1000, 0, "a"),
            JournalLine("DH", "1000", 500, 0, "b"),
            JournalLine("DH", "1000", 0, 200, "c"),
        ]
    )
    assert ledger.balance("DH", "1000") == 1300


def test_ledger_account_balance_aggregates_across_entities() -> None:
    ledger = Ledger(chart_of_accounts())
    ledger.load_opening(
        [
            JournalLine("DH", "1400", 1000, 0, "a"),
            JournalLine("MF", "1400", 2000, 0, "b"),
            JournalLine("BW", "1400", 0, 500, "c"),
        ]
    )
    assert ledger.account_balance("1400") == 2500


def test_ledger_post_out_of_tie_leaves_ledger_untouched() -> None:
    ledger = Ledger(chart_of_accounts())
    bad = _entry(
        [
            JournalLine("DH", "6100", 1000, 0, "dr"),
            JournalLine("DH", "1510", 0, 999, "cr short"),
        ]
    )
    with pytest.raises(OutOfTieError):
        ledger.post(bad)
    assert ledger.posted == []
    assert ledger.balance("DH", "6100") == 0
    assert ledger.keys() == []


def test_ledger_entity_balance_not_required_when_flag_off() -> None:
    # Aggregate balances but entity legs don't; with the control disabled the
    # entry posts anyway.
    ledger = Ledger(chart_of_accounts())
    je = _entry(
        [
            JournalLine("DH", "6100", 2000, 0, "dr"),
            JournalLine("MF", "2100", 0, 2000, "cr"),
        ]
    )
    ledger.post(je, require_entity_balance=False)
    assert je in ledger.posted
    assert ledger.balance("DH", "6100") == 2000
    assert ledger.balance("MF", "2100") == -2000


def test_ledger_trial_balance_splits_debit_credit_columns() -> None:
    ledger = Ledger(chart_of_accounts())
    ledger.load_opening(
        [
            JournalLine("DH", "1000", 5000, 0, "cash"),  # debit balance
            JournalLine("DH", "3000", 0, 5000, "equity"),  # credit balance
        ]
    )
    rows = ledger.trial_balance()
    by_acct = {acct: (dr, cr) for _, acct, dr, cr in rows}
    assert by_acct["1000"] == (5000, 0)
    assert by_acct["3000"] == (0, 5000)


def test_ledger_trial_balance_omits_zero_balances() -> None:
    ledger = Ledger(chart_of_accounts())
    ledger.load_opening(
        [
            JournalLine("DH", "1000", 1000, 0, "a"),
            JournalLine("DH", "1000", 0, 1000, "b"),  # nets to zero
            JournalLine("DH", "4000", 0, 500, "c"),
        ]
    )
    rows = ledger.trial_balance()
    accts = {acct for _, acct, _, _ in rows}
    assert "1000" not in accts  # zero-balance account dropped
    assert "4000" in accts


def test_ledger_trial_balance_sorted_by_entity_then_account() -> None:
    ledger = Ledger(chart_of_accounts())
    ledger.load_opening(
        [
            JournalLine("MF", "2000", 0, 100, "a"),
            JournalLine("DH", "1400", 100, 0, "b"),
            JournalLine("DH", "1000", 100, 0, "c"),
            JournalLine("BW", "1000", 100, 0, "d"),
        ]
    )
    rows = ledger.trial_balance()
    keys = [(ent, acct) for ent, acct, _, _ in rows]
    assert keys == sorted(keys)


def test_ledger_total_debits_credits_balanced() -> None:
    ledger = Ledger(chart_of_accounts())
    ledger.load_opening(
        [
            JournalLine("DH", "1000", 5000, 0, "cash"),
            JournalLine("DH", "3000", 0, 5000, "equity"),
        ]
    )
    debits, credits = ledger.total_debits_credits()
    assert (debits, credits) == (5000, 5000)


def test_ledger_keys_returns_all_recorded_pairs() -> None:
    ledger = Ledger(chart_of_accounts())
    ledger.load_opening(
        [
            JournalLine("DH", "1000", 100, 0, "a"),
            JournalLine("MF", "2000", 0, 100, "b"),
        ]
    )
    assert set(ledger.keys()) == {("DH", "1000"), ("MF", "2000")}
