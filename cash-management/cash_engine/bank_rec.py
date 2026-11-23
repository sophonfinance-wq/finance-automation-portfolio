"""Fictional, validation-only bank-reconciliation bridge controls.

A cash manager's core monthly control: prove that each account's bank statement
ending balance, adjusted for deposits in transit and outstanding checks, ties to
the general-ledger "should-be" balance.  This validator independently re-derives
both sides of the classic two-column reconciliation and confirms they meet:

    adjusted bank = bank ending + deposits in transit - outstanding checks + bank errors
    adjusted book = GL balance   + interest/credits   - charges/debits      + book errors
    control       = adjusted bank == adjusted book

It works on generic structured inputs rather than a workbook layout, holds every
amount in integer cents, and is strictly read-only: it never creates a journal
entry, import payload, posting action, or source-system mutation, and it contains
no private workbook coordinates, paths, formulas, entity names, or amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ACCOUNT_RE = re.compile(r"[A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8}){1,3}", re.IGNORECASE)


def _valid_amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _canonical_period(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    return value


@dataclass(frozen=True)
class BankReconciliation:
    """One fictional account reconciliation, expressed in integer cents.

    ``deposits_in_transit`` and ``outstanding_checks`` are magnitudes (>= 0);
    ``bank_error`` and ``book_error`` are signed adjusting plugs that require
    human approval whenever nonzero.
    """

    entity: str
    account: str
    bank_name: str
    bank_ending_cents: object
    gl_balance_cents: object
    deposits_in_transit_cents: object = 0
    outstanding_checks_cents: object = 0
    bank_error_cents: object = 0
    interest_earned_cents: object = 0
    bank_charges_cents: object = 0
    book_error_cents: object = 0
    displayed_adjusted_cents: object = None


@dataclass(frozen=True)
class BankRecFinding:
    code: str
    detail: str
    entity: str = ""
    account: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class BankRecResult:
    period: str
    account_count: int
    tied_count: int
    out_of_tie_count: int
    findings: tuple[BankRecFinding, ...]
    manual_gates: tuple[str, ...] = (
        "obtain and tie the controlled bank statement for the exact period",
        "confirm deposits in transit clear in the subsequent statement",
        "confirm outstanding checks against the check register and stale-date policy",
        "approve reconciling adjustments and any bank or book error plugs",
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


class BankReconciliationValidator:
    """Validate a set of fictional bank reconciliations without posting."""

    def __init__(self, period: str, reconciliations: Iterable[BankReconciliation]) -> None:
        self.period = _canonical_period(period, "period")
        self.reconciliations = tuple(reconciliations)

    _AMOUNT_FIELDS = (
        "bank_ending_cents",
        "gl_balance_cents",
        "deposits_in_transit_cents",
        "outstanding_checks_cents",
        "bank_error_cents",
        "interest_earned_cents",
        "bank_charges_cents",
        "book_error_cents",
    )

    def run(self) -> BankRecResult:
        findings: list[BankRecFinding] = []
        seen: set[tuple[str, str]] = set()
        tied = 0
        out_of_tie = 0

        if not self.reconciliations:
            findings.append(
                BankRecFinding("RECONCILIATION_SET_EMPTY", "no reconciliations were provided")
            )

        for position, rec in enumerate(self.reconciliations, start=1):
            entity = rec.entity if isinstance(rec.entity, str) else str(rec.entity)
            account = rec.account if isinstance(rec.account, str) else str(rec.account)

            def add(code: str, detail: str, severity: str = "ERROR") -> None:
                findings.append(BankRecFinding(code, detail, entity, account, severity))

            structure_valid = True
            if not _clean_text(rec.entity):
                add("ENTITY_INVALID", f"reconciliation {position} entity must be trimmed and nonblank")
                structure_valid = False
            if not isinstance(rec.account, str) or not _ACCOUNT_RE.fullmatch(rec.account):
                add("ACCOUNT_INVALID", f"reconciliation {position} account is not canonical")
                structure_valid = False
            if not _clean_text(rec.bank_name):
                add("BANK_NAME_INVALID", f"reconciliation {position} bank name must be trimmed and nonblank")
                structure_valid = False

            invalid = [name for name in self._AMOUNT_FIELDS if not _valid_amount(getattr(rec, name))]
            if invalid:
                add("AMOUNT_INVALID", "integer cents required for " + ", ".join(invalid))
                structure_valid = False
            if rec.displayed_adjusted_cents is not None and not _valid_amount(
                rec.displayed_adjusted_cents
            ):
                add("DISPLAYED_ADJUSTED_INVALID", "displayed adjusted balance must use integer cents")
                structure_valid = False

            if not structure_valid:
                continue

            key = (rec.entity.casefold(), rec.account.casefold())
            if key in seen:
                add("ACCOUNT_DUPLICATE", f"reconciliation {position} duplicates an entity/account key")
                continue
            seen.add(key)

            # Magnitudes must not be negative.
            if rec.deposits_in_transit_cents < 0:
                add("DEPOSITS_IN_TRANSIT_NEGATIVE", "deposits in transit is a magnitude and cannot be negative")
            if rec.outstanding_checks_cents < 0:
                add("OUTSTANDING_CHECKS_NEGATIVE", "outstanding checks is a magnitude and cannot be negative")
            if rec.bank_charges_cents < 0:
                add("BANK_CHARGES_NEGATIVE", "bank charges is a magnitude and cannot be negative")
            if rec.interest_earned_cents < 0:
                add("INTEREST_EARNED_NEGATIVE", "interest earned is a magnitude and cannot be negative")

            adjusted_bank = (
                rec.bank_ending_cents
                + rec.deposits_in_transit_cents
                - rec.outstanding_checks_cents
                + rec.bank_error_cents
            )
            adjusted_book = (
                rec.gl_balance_cents
                + rec.interest_earned_cents
                - rec.bank_charges_cents
                + rec.book_error_cents
            )

            if adjusted_bank == adjusted_book:
                tied += 1
            else:
                out_of_tie += 1
                add(
                    "RECONCILIATION_OUT_OF_TIE",
                    f"adjusted bank {adjusted_bank} != adjusted book {adjusted_book} "
                    f"(difference {adjusted_bank - adjusted_book})",
                )

            if rec.displayed_adjusted_cents is not None and rec.displayed_adjusted_cents != adjusted_bank:
                add(
                    "DISPLAYED_ADJUSTED_OUT_OF_TIE",
                    f"displayed adjusted {rec.displayed_adjusted_cents} != rederived {adjusted_bank}",
                )

            # Signed error plugs are legitimate but never self-certify.
            if rec.bank_error_cents:
                add(
                    "BANK_ERROR_REVIEW_REQUIRED",
                    f"nonzero bank error plug {rec.bank_error_cents} requires approval",
                    severity="REVIEW",
                )
            if rec.book_error_cents:
                add(
                    "BOOK_ERROR_REVIEW_REQUIRED",
                    f"nonzero book error plug {rec.book_error_cents} requires approval",
                    severity="REVIEW",
                )

        return BankRecResult(
            period=self.period,
            account_count=len(self.reconciliations),
            tied_count=tied,
            out_of_tie_count=out_of_tie,
            findings=tuple(findings),
        )


def demo_reconciliations() -> tuple[BankReconciliation, ...]:
    """Return a clean, tying set of fictional reconciliations (integer cents)."""

    return (
        # Operating account: bank + DIT - outstanding = GL, no plugs.
        BankReconciliation(
            entity="Cedar Demo LLC",
            account="CASH-1001",
            bank_name="Demo National Bank",
            bank_ending_cents=1_050_000,
            gl_balance_cents=1_000_000,
            deposits_in_transit_cents=75_000,
            outstanding_checks_cents=125_000,
            displayed_adjusted_cents=1_000_000,
        ),
        # Concentration account with a service charge on the book side.
        BankReconciliation(
            entity="Cedar Demo LLC",
            account="CASH-1900",
            bank_name="Demo National Bank",
            bank_ending_cents=2_000_000,
            gl_balance_cents=2_000_500,
            outstanding_checks_cents=0,
            deposits_in_transit_cents=0,
            bank_charges_cents=500,
            displayed_adjusted_cents=2_000_000,
        ),
    )


__all__ = [
    "BankReconciliation",
    "BankReconciliationValidator",
    "BankRecFinding",
    "BankRecResult",
    "demo_reconciliations",
]
