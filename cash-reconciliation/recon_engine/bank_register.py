"""Fictional, validation-only bank-register continuity controls.

A cash manager keeps a per-account running cash register that must foot and roll
forward: each posted transaction advances a running balance, the running balance
must reconcile row by row, the displayed closing must equal the opening balance
plus every signed movement, the opening must continue the prior period's close,
and the whole thing must tie to the controlled bank statement ending balance.

This validator independently re-derives that chain for one account's register:

    running[0]   == opening        + amount[0]
    running[i]   == running[i-1]   + amount[i]
    closing      == opening        + sum(amounts)
    opening      == prior_closing                (when a prior close is supplied)
    bank ending  == rederived closing            (when a statement is supplied)

It works on generic structured inputs rather than a workbook layout, holds every
amount in integer cents, and is strictly read-only: it never creates a journal
entry, import payload, posting action, or source-system mutation, and it contains
no private workbook coordinates, paths, formulas, entity names, or amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ACCOUNT_RE = re.compile(r"[A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8}){1,3}", re.IGNORECASE)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _valid_amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _canonical_period(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    return value


def _iso_date(value: object) -> date | None:
    """Return a real calendar date only for a strict ``YYYY-MM-DD`` string."""

    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class RegisterTransaction:
    """One fictional register line: a signed movement and its running balance."""

    txn_id: str
    txn_date: str
    amount_cents: object
    running_balance_cents: object


@dataclass(frozen=True)
class BankRegister:
    """One fictional account register for a period, expressed in integer cents.

    ``prior_closing_cents`` (opening continuity) and ``bank_statement_ending_cents``
    (bank tie-out control) are optional; when omitted their controls are skipped.
    """

    entity: str
    account: str
    period: str
    opening_balance_cents: object
    transactions: tuple[RegisterTransaction, ...]
    displayed_closing_cents: object
    prior_closing_cents: object = None
    bank_statement_ending_cents: object = None


@dataclass(frozen=True)
class BankRegisterFinding:
    code: str
    detail: str
    entity: str = ""
    account: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class BankRegisterResult:
    period: str
    entity: str
    account: str
    transaction_count: int
    out_of_tie_row_count: int
    rederived_closing_cents: object
    findings: tuple[BankRegisterFinding, ...]
    manual_gates: tuple[str, ...] = (
        "obtain and tie the controlled bank statement and check register for the exact period",
        "confirm every register transaction to supporting cash-side evidence",
        "confirm opening balance continues the approved prior-period close",
        "approve reconciling items and any bank tie-out difference",
        "human review and approval",
        "manual posting and post-entry general-ledger tie-out",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    posting_actions: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)

    @property
    def mechanical_clean(self) -> bool:
        return not self.findings

    @property
    def verdict(self) -> str:
        return "READY FOR HUMAN REVIEW" if self.mechanical_clean else "NEEDS REVIEW"

    @property
    def validation_only(self) -> bool:
        return True

    @property
    def posting_authorized(self) -> bool:
        return False


class BankRegisterValidator:
    """Validate one fictional account register's continuity without posting."""

    def __init__(self, register: BankRegister) -> None:
        self.register = register
        self.period = _canonical_period(register.period, "period")

    def run(self) -> BankRegisterResult:
        register = self.register
        findings: list[BankRegisterFinding] = []

        entity = register.entity if isinstance(register.entity, str) else str(register.entity)
        account = register.account if isinstance(register.account, str) else str(register.account)

        def add(code: str, detail: str, severity: str = "ERROR") -> None:
            findings.append(BankRegisterFinding(code, detail, entity, account, severity))

        # --- register-level identifiers ---------------------------------
        if not _clean_text(register.entity):
            add("ENTITY_INVALID", "entity must be trimmed and nonblank")
        if not isinstance(register.account, str) or not _ACCOUNT_RE.fullmatch(register.account):
            add("ACCOUNT_INVALID", "account is not canonical")

        # --- register-level amounts -------------------------------------
        opening_valid = _valid_amount(register.opening_balance_cents)
        if not opening_valid:
            add("OPENING_BALANCE_INVALID", "opening balance must use integer cents")
        displayed_valid = _valid_amount(register.displayed_closing_cents)
        if not displayed_valid:
            add("DISPLAYED_CLOSING_INVALID", "displayed closing must use integer cents")

        prior_present = register.prior_closing_cents is not None
        prior_valid = prior_present and _valid_amount(register.prior_closing_cents)
        if prior_present and not prior_valid:
            add("PRIOR_CLOSING_INVALID", "prior closing must use integer cents when provided")

        bank_present = register.bank_statement_ending_cents is not None
        bank_valid = bank_present and _valid_amount(register.bank_statement_ending_cents)
        if bank_present and not bank_valid:
            add("BANK_STATEMENT_INVALID", "bank statement ending must use integer cents when provided")

        transactions = tuple(register.transactions)
        if not transactions:
            add("REGISTER_EMPTY", "no register transactions were provided")

        year, month = (int(part) for part in self.period.split("-"))

        # --- per-transaction structure ----------------------------------
        seen: set[str] = set()
        amounts_all_valid = True
        for position, txn in enumerate(transactions, start=1):
            if not _clean_text(txn.txn_id):
                add("TXN_ID_INVALID", f"transaction {position} id must be trimmed and nonblank")
            elif txn.txn_id.casefold() in seen:
                add("TXN_ID_DUPLICATE", f"transaction {position} id duplicates an earlier transaction")
            else:
                seen.add(txn.txn_id.casefold())

            parsed = _iso_date(txn.txn_date)
            if parsed is None:
                add("TXN_DATE_INVALID", f"transaction {position} date is not a valid ISO YYYY-MM-DD date")
            elif (parsed.year, parsed.month) != (year, month):
                add("TXN_DATE_OUT_OF_PERIOD", f"transaction {position} date {txn.txn_date} is outside the period month")

            invalid = [
                name
                for name in ("amount_cents", "running_balance_cents")
                if not _valid_amount(getattr(txn, name))
            ]
            if invalid:
                amounts_all_valid = False
                add("AMOUNT_INVALID", f"transaction {position}: integer cents required for " + ", ".join(invalid))

        # --- running-balance continuity (row by row) --------------------
        out_of_tie = 0
        prev_running = register.opening_balance_cents
        prev_valid = opening_valid
        for position, txn in enumerate(transactions, start=1):
            amount_valid = _valid_amount(txn.amount_cents)
            running_valid = _valid_amount(txn.running_balance_cents)
            if amount_valid and running_valid and prev_valid:
                expected = prev_running + txn.amount_cents
                if txn.running_balance_cents != expected:
                    out_of_tie += 1
                    add(
                        "RUNNING_BALANCE_OUT_OF_TIE",
                        f"transaction {position} running balance {txn.running_balance_cents} "
                        f"!= prior {prev_running} plus amount {txn.amount_cents} ({expected})",
                    )
            if running_valid:
                prev_running = txn.running_balance_cents
                prev_valid = True
            else:
                prev_valid = False

        # --- closing / continuity / bank tie-out ------------------------
        if opening_valid and amounts_all_valid:
            rederived_closing: object = register.opening_balance_cents + sum(
                txn.amount_cents for txn in transactions
            )
        else:
            rederived_closing = None

        if rederived_closing is not None and displayed_valid:
            if register.displayed_closing_cents != rederived_closing:
                add(
                    "CLOSING_OUT_OF_TIE",
                    f"displayed closing {register.displayed_closing_cents} "
                    f"!= opening plus movements {rederived_closing}",
                )

        if prior_valid and opening_valid:
            if register.opening_balance_cents != register.prior_closing_cents:
                add(
                    "OPENING_CONTINUITY_OUT_OF_TIE",
                    f"opening {register.opening_balance_cents} != prior closing {register.prior_closing_cents}",
                )

        if bank_valid and rederived_closing is not None:
            if register.bank_statement_ending_cents != rederived_closing:
                add(
                    "BANK_TIE_OUT",
                    f"bank statement ending {register.bank_statement_ending_cents} "
                    f"!= rederived closing {rederived_closing}",
                    severity="REVIEW",
                )

        return BankRegisterResult(
            period=self.period,
            entity=entity,
            account=account,
            transaction_count=len(transactions),
            out_of_tie_row_count=out_of_tie,
            rederived_closing_cents=rederived_closing,
            findings=tuple(findings),
        )


def demo_register() -> BankRegister:
    """Return a clean, fully tying fictional account register (integer cents)."""

    return BankRegister(
        entity="Cedar Demo LLC",
        account="CASH-1001",
        period="2026-06",
        opening_balance_cents=1_000_000,
        transactions=(
            RegisterTransaction("TXN-0001", "2026-06-02", 250_000, 1_250_000),
            RegisterTransaction("TXN-0002", "2026-06-09", -125_000, 1_125_000),
            RegisterTransaction("TXN-0003", "2026-06-18", 75_000, 1_200_000),
            RegisterTransaction("TXN-0004", "2026-06-27", -50_000, 1_150_000),
        ),
        displayed_closing_cents=1_150_000,
        prior_closing_cents=1_000_000,
        bank_statement_ending_cents=1_150_000,
    )


__all__ = [
    "BankRegister",
    "BankRegisterFinding",
    "BankRegisterResult",
    "BankRegisterValidator",
    "RegisterTransaction",
    "demo_register",
]
