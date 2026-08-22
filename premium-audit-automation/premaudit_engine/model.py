"""Domain model for the premium-audit response engine.

Everything here is fictional and deterministic: the engine consumes fixed-width
job-cost print reports (the kind a construction ERP prints), certificate-of-
insurance coverage listings, and a triage policy, and produces an audit-response
package. No real company's data ever enters this package.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum


class TranType(str, Enum):
    AP = "AP cost"          # invoice-backed cost with a vendor
    JC = "JC cost"          # journal-entry cost, no vendor


class PeriodBasis(str, Enum):
    """Which date cuts a line into (or out of) the audit window.

    The print report carries an accounting date and is blind about the
    underlying transaction date. A ledger export carries both. Totalling the
    same lines on ACCOUNTING vs TRANSACTION is how the dual-basis distance is
    measured once the two sources have been reconciled.
    """
    ACCOUNTING = "accounting"
    TRANSACTION = "transaction"


class Triage(str, Enum):
    JOURNAL_ENTRY = "NA - journal entry (no vendor)"
    CLEARING_ACCOUNT = "NA - clearing account (no certificate applicable)"
    COVERED_CURRENT = "COI on file"
    OCIP_ENROLLED = "NA - wrap-enrolled"
    MATERIALS_ONLY = "NA - materials only"
    PROFESSIONAL = "NA - legal/professional"
    CHASE = "Certificate required - chase"


@dataclass(frozen=True)
class CostLine:
    job: str
    job_name: str
    cost_code: str
    cost_code_desc: str
    tran_type: TranType
    acctg_date: dt.date
    vendor_id: str          # "" for JC lines
    vendor_name: str        # "" for JC lines
    invoice: str
    description: str
    amount_cents: int
    txn_date: dt.date | None = None

    def date_on(self, basis: PeriodBasis) -> dt.date | None:
        if basis is PeriodBasis.ACCOUNTING:
            return self.acctg_date
        return self.txn_date

    @property
    def line_key(self) -> tuple:
        return (self.job, self.cost_code, self.acctg_date, self.amount_cents)


@dataclass(frozen=True)
class LedgerRow:
    """One undifferentiated ledger-export row carrying both dates."""
    job: str
    cost_code: str
    tran_type: TranType
    txn_date: dt.date
    acctg_date: dt.date
    amount_cents: int

    @property
    def line_key(self) -> tuple:
        return (self.job, self.cost_code, self.acctg_date, self.amount_cents)


@dataclass
class Reconciliation:
    """Result of attaching ledger transaction dates to print lines."""
    lines: tuple[CostLine, ...]
    matched: int
    unmatched: int
    unused_ledger_rows: int

    @property
    def complete(self) -> bool:
        return self.unmatched == 0 and self.unused_ledger_rows == 0

    @property
    def coverage_pct(self) -> float:
        total = self.matched + self.unmatched
        if total == 0:
            return 100.0
        return 100.0 * self.matched / total


@dataclass(frozen=True)
class BasisDivergence:
    """Accounting-basis vs transaction-basis cut of the same line set."""
    accounting_cents: int
    transaction_cents: int
    moved_in: tuple[CostLine, ...]
    moved_out: tuple[CostLine, ...]

    @property
    def delta_cents(self) -> int:
        return self.transaction_cents - self.accounting_cents

    @property
    def movers(self) -> tuple[CostLine, ...]:
        return self.moved_in + self.moved_out


@dataclass(frozen=True)
class JobPrintTotal:
    """The report's own printed total for one job - the self-verification anchor."""
    job: str
    total_cents: int


@dataclass(frozen=True)
class ParsedReport:
    company: str
    date_from: dt.date
    date_to: dt.date
    lines: tuple[CostLine, ...]
    printed_totals: tuple[JobPrintTotal, ...]


@dataclass(frozen=True)
class CoverageRecord:
    vendor_name: str
    coverage: str           # e.g. "General"
    effective: dt.date
    expiration: dt.date
    limit_cents: int
    received: bool


@dataclass(frozen=True)
class AuditWindow:
    start: dt.date
    end: dt.date            # inclusive on both ends

    def contains(self, d: dt.date) -> bool:
        return self.start <= d <= self.end


@dataclass(frozen=True)
class TriagePolicy:
    """Deterministic classification policy, applied line by line."""
    clearing_vendor_ids: frozenset[str] = frozenset()
    wrap_enrolled_vendors: frozenset[str] = frozenset()   # upper-cased names
    materials_only_vendors: frozenset[str] = frozenset()
    professional_vendors: frozenset[str] = frozenset()
    required_coverage: str = "General"


@dataclass
class ReconciliationFailure:
    job: str
    parsed_cents: int
    printed_cents: int | None   # None = printed total line missing

    @property
    def delta_cents(self) -> int | None:
        if self.printed_cents is None:
            return None
        return self.parsed_cents - self.printed_cents


class ParseRefusal(RuntimeError):
    """Raised when parsed job sums do not tie to the report's printed totals.

    The engine refuses rather than delivering an untied workpaper.
    """

    def __init__(self, failures: list[ReconciliationFailure]):
        self.failures = failures
        detail = "; ".join(
            f"{f.job}: parsed {f.parsed_cents} vs printed "
            f"{'MISSING' if f.printed_cents is None else f.printed_cents}"
            for f in failures
        )
        super().__init__(f"printed-total reconciliation failed: {detail}")


@dataclass
class TriagedLine:
    line: CostLine
    in_window: bool
    triage: Triage


@dataclass
class AuditPackage:
    company: str
    window: AuditWindow
    lines: list[TriagedLine] = field(default_factory=list)

    @property
    def window_total_cents(self) -> int:
        return sum(t.line.amount_cents for t in self.lines if t.in_window)

    @property
    def full_total_cents(self) -> int:
        return sum(t.line.amount_cents for t in self.lines)
