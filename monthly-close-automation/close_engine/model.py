"""Core accounting data model for the close engine.

Defines the chart of accounts, journal entries with a hard balance control,
and a general ledger that posts entries and reports balances. All amounts are
integer cents (see :mod:`close_engine.money`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from . import money


class AccountType(str, Enum):
    """Normal-balance classification for an account."""

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"

    @property
    def normal_is_debit(self) -> bool:
        """True if the account's normal balance is a debit."""
        return self in (AccountType.ASSET, AccountType.EXPENSE)


@dataclass(frozen=True)
class Account:
    """A single chart-of-accounts line.

    Attributes:
        code: Account number (e.g. ``"1400"``).
        name: Human-readable account name.
        type: Normal-balance classification.
    """

    code: str
    name: str
    type: AccountType

    @property
    def label(self) -> str:
        """Return ``"<code> · <name>"`` for display."""
        return f"{self.code} · {self.name}"


@dataclass(frozen=True)
class JournalLine:
    """One debit or credit line of a journal entry.

    Exactly one of ``debit``/``credit`` is non-zero. Amounts are integer cents.

    Attributes:
        entity: Entity code the line belongs to (e.g. ``"DH"``).
        account: Account code.
        debit: Debit amount in cents (>= 0).
        credit: Credit amount in cents (>= 0).
        memo: Free-text description.
    """

    entity: str
    account: str
    debit: int
    credit: int
    memo: str = ""


@dataclass
class JournalEntry:
    """A balanced journal entry made of one or more :class:`JournalLine`.

    Attributes:
        je_id: Stable identifier (e.g. ``"JE-2026-03-PREPAID"``).
        period: Period label ``YYYY-MM``.
        category: Recurring-entry class (e.g. ``"prepaid_amortization"``).
        description: Human-readable summary.
        lines: The debit/credit lines.
    """

    je_id: str
    period: str
    category: str
    description: str
    lines: list[JournalLine] = field(default_factory=list)

    @property
    def total_debits(self) -> int:
        """Sum of all debit amounts, in cents."""
        return money.total(line.debit for line in self.lines)

    @property
    def total_credits(self) -> int:
        """Sum of all credit amounts, in cents."""
        return money.total(line.credit for line in self.lines)

    @property
    def is_balanced(self) -> bool:
        """True iff total debits equal total credits."""
        return self.total_debits == self.total_credits

    @property
    def out_of_tie(self) -> int:
        """Signed imbalance (debits - credits), in cents. 0 when balanced."""
        return self.total_debits - self.total_credits

    def entities(self) -> set[str]:
        """Return the distinct entity codes touched by this entry."""
        return {line.entity for line in self.lines}

    def balances_per_entity(self) -> dict[str, int]:
        """Return per-entity (debits - credits) so each leg can self-balance.

        A multi-entity intercompany entry must balance **within each entity**,
        not merely in aggregate. This exposes that for the controls layer.
        """
        out: dict[str, int] = {}
        for line in self.lines:
            out[line.entity] = out.get(line.entity, 0) + line.debit - line.credit
        return out


class OutOfTieError(Exception):
    """Raised when an entry that must post is not in tie.

    Attributes:
        je: The offending entry.
        detail: Human-readable explanation.
    """

    def __init__(self, je: JournalEntry, detail: str) -> None:
        self.je = je
        self.detail = detail
        super().__init__(f"{je.je_id}: {detail}")


class ChartOfAccounts:
    """An indexed chart of accounts."""

    def __init__(self, accounts: Iterable[Account]) -> None:
        self._by_code: dict[str, Account] = {a.code: a for a in accounts}

    def __contains__(self, code: str) -> bool:
        return code in self._by_code

    def __iter__(self):
        return iter(self._by_code.values())

    def get(self, code: str) -> Account:
        """Look up an account by code.

        Raises:
            KeyError: If the code is not in the chart.
        """
        if code not in self._by_code:
            raise KeyError(f"unknown account code: {code}")
        return self._by_code[code]


class Ledger:
    """A general ledger keyed by ``(entity, account)`` with integer-cent balances.

    Balances are stored as signed debit-minus-credit cents. The opening trial
    balance is loaded first; recurring entries are then posted on top. Every
    posting is validated for balance before it touches the ledger.
    """

    def __init__(self, coa: ChartOfAccounts) -> None:
        self.coa = coa
        # (entity, account) -> signed cents (debit positive, credit negative)
        self._bal: dict[tuple[str, str], int] = {}
        self.posted: list[JournalEntry] = []

    def load_opening(self, lines: Iterable[JournalLine]) -> None:
        """Load opening balances from trial-balance lines (no tie control).

        The opening trial balance is treated as the starting state, not a
        posted entry. It is validated for whole-group balance separately by the
        controls layer.
        """
        for line in lines:
            key = (line.entity, line.account)
            self._bal[key] = self._bal.get(key, 0) + line.debit - line.credit

    def post(self, je: JournalEntry, *, require_entity_balance: bool = True) -> None:
        """Post a journal entry after enforcing the balance control.

        Args:
            je: The entry to post.
            require_entity_balance: If True, each entity leg must also balance
                (required for intercompany entries that span entities).

        Raises:
            OutOfTieError: If the entry is not balanced (in aggregate, or
                per-entity when ``require_entity_balance`` is True).
        """
        if not je.is_balanced:
            raise OutOfTieError(
                je,
                f"debits {money.fmt(je.total_debits)} != "
                f"credits {money.fmt(je.total_credits)} "
                f"(out of tie by {money.fmt(je.out_of_tie)})",
            )
        if require_entity_balance:
            for entity, diff in je.balances_per_entity().items():
                if diff != 0:
                    raise OutOfTieError(
                        je,
                        f"entity {entity} leg out of tie by {money.fmt(diff)}",
                    )
        for line in je.lines:
            key = (line.entity, line.account)
            self._bal[key] = self._bal.get(key, 0) + line.debit - line.credit
        self.posted.append(je)

    def balance(self, entity: str, account: str) -> int:
        """Return the signed (debit-positive) balance for one entity/account."""
        return self._bal.get((entity, account), 0)

    def account_balance(self, account: str) -> int:
        """Return the group-wide signed balance for an account across entities."""
        return sum(v for (_, a), v in self._bal.items() if a == account)

    def keys(self) -> list[tuple[str, str]]:
        """Return all ``(entity, account)`` keys with a recorded balance."""
        return list(self._bal.keys())

    def trial_balance(self) -> list[tuple[str, str, int, int]]:
        """Return the trial balance as ``(entity, account, debit, credit)`` rows.

        Each non-zero balance is presented in its natural debit or credit
        column. Rows are sorted by entity then account code.
        """
        rows: list[tuple[str, str, int, int]] = []
        for (entity, account), signed in sorted(self._bal.items()):
            if signed == 0:
                continue
            if signed > 0:
                rows.append((entity, account, signed, 0))
            else:
                rows.append((entity, account, 0, -signed))
        return rows

    def total_debits_credits(self) -> tuple[int, int]:
        """Return total (debits, credits) across the whole ledger, in cents."""
        debits = sum(v for v in self._bal.values() if v > 0)
        credits = sum(-v for v in self._bal.values() if v < 0)
        return debits, credits
