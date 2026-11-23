"""Reconciliation engine: variance, materiality, classification.

The engine reconciles **by account number** (never by row position):

* **Cash rec** — GL cash balance vs. the bank statement ending balance.
* **Debt rec** — GL loan balance vs. a lender 3-part total computed as
  ``principal + current_interest_reserve + late_paydown``.

For each account it computes the variance, compares it to a materiality
threshold, and classifies the line:

* ``clean``  — variance is effectively zero (an exact tie).
* ``timing`` — non-zero but within the materiality threshold (immaterial noise,
  expected to clear).
* ``flag``   — variance exceeds the threshold and is escalated for review.

Dormant zero-activity rows are skipped with a documented note rather than
reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .generate import (
    BankStatement,
    GLRecord,
    LenderStatement,
    SyntheticDataset,
)

# A line is treated as an exact tie if its absolute variance is at or below this
# rounding tolerance (guards against float noise on cent-rounded inputs).
TIE_TOLERANCE: float = 0.005

Classification = Literal["clean", "timing", "flag", "skipped"]


def lender_three_part_total(stmt: LenderStatement) -> float:
    """Return the reconciled lender balance from the 3-part formula.

    ``principal + current_interest_reserve + late_paydown`` (the late-paydown
    term is optional and frequently zero).

    Args:
        stmt: The lender statement for a debt account.

    Returns:
        The combined lender total rounded to cents.
    """
    return round(
        stmt.principal + stmt.current_interest_reserve + stmt.late_paydown, 2
    )


def compute_variance(gl_balance: float, source_balance: float) -> float:
    """Return ``gl_balance - source_balance`` rounded to cents.

    A positive variance means the GL is *higher* than the source; a negative
    variance means the GL is *lower* than the source.
    """
    return round(gl_balance - source_balance, 2)


def classify(variance: float, threshold: float) -> Classification:
    """Classify a variance against the materiality threshold.

    Args:
        variance: GL-minus-source variance (signed).
        threshold: Absolute materiality threshold in dollars.

    Returns:
        ``"clean"`` for an exact tie, ``"timing"`` when the absolute variance is
        non-zero but at or below ``threshold``, otherwise ``"flag"``.
    """
    magnitude = abs(variance)
    if magnitude <= TIE_TOLERANCE:
        return "clean"
    if magnitude <= threshold:
        return "timing"
    return "flag"


@dataclass
class ReconLine:
    """One reconciled account line (cash or debt)."""

    entity: str
    account_type: Literal["cash", "debt"]
    account_number: str
    description: str
    gl_balance: float
    source_balance: float
    variance: float
    classification: Classification
    source_label: str
    note: str = ""
    flag_id: str = ""

    # Debt-only detail (the 3-part legs); zero/absent for cash lines.
    principal: float = 0.0
    interest_reserve: float = 0.0
    late_paydown: float = 0.0


@dataclass
class ReconResult:
    """The complete reconciliation output."""

    period: str
    statement_date: str
    threshold: float
    cash_lines: list[ReconLine] = field(default_factory=list)
    debt_lines: list[ReconLine] = field(default_factory=list)
    skipped_lines: list[ReconLine] = field(default_factory=list)

    @property
    def all_active_lines(self) -> list[ReconLine]:
        """All reconciled (non-skipped) cash and debt lines."""
        return [*self.cash_lines, *self.debt_lines]

    @property
    def flagged(self) -> list[ReconLine]:
        """Only the lines escalated for review."""
        return [ln for ln in self.all_active_lines if ln.classification == "flag"]

    def summary_counts(self) -> dict[str, int]:
        """Return aggregate counts used in the summary section."""
        active = self.all_active_lines
        return {
            "accounts_total": len(active) + len(self.skipped_lines),
            "accounts_reconciled": len(active),
            "cash_accounts": len(self.cash_lines),
            "debt_accounts": len(self.debt_lines),
            "clean": sum(1 for ln in active if ln.classification == "clean"),
            "timing": sum(1 for ln in active if ln.classification == "timing"),
            "flag": sum(1 for ln in active if ln.classification == "flag"),
            "skipped": len(self.skipped_lines),
        }


def _index_banks(banks: list[BankStatement]) -> dict[str, BankStatement]:
    return {b.account_number: b for b in banks}


def _index_lenders(lenders: list[LenderStatement]) -> dict[str, LenderStatement]:
    return {ln.account_number: ln for ln in lenders}


def reconcile(
    dataset: SyntheticDataset, threshold: float
) -> ReconResult:
    """Reconcile a dataset by account number and classify every line.

    Args:
        dataset: The synthetic workpapers (GL, bank, lender).
        threshold: Materiality threshold in dollars.

    Returns:
        A fully populated :class:`ReconResult`. Flag IDs (``FLAG-001`` …) are
        assigned in a stable order across cash then debt lines.
    """
    banks = _index_banks(dataset.bank_statements)
    lenders = _index_lenders(dataset.lender_statements)

    result = ReconResult(
        period=dataset.period,
        statement_date=dataset.statement_date,
        threshold=threshold,
    )

    for rec in dataset.gl_records:
        # Dormant zero-activity rows are skipped with a documented note.
        if rec.dormant or _is_zero_activity(rec, banks, lenders):
            result.skipped_lines.append(_skip_line(rec))
            continue

        if rec.account_type == "cash":
            result.cash_lines.append(_reconcile_cash(rec, banks, threshold))
        else:
            result.debt_lines.append(_reconcile_debt(rec, lenders, threshold))

    _assign_flag_ids(result)
    return result


def _is_zero_activity(
    rec: GLRecord,
    banks: dict[str, BankStatement],
    lenders: dict[str, LenderStatement],
) -> bool:
    """True when GL and the matching source are both zero (no activity)."""
    if abs(rec.gl_balance) > TIE_TOLERANCE:
        return False
    if rec.account_type == "cash":
        b = banks.get(rec.account_number)
        return b is not None and abs(b.ending_balance) <= TIE_TOLERANCE
    ln = lenders.get(rec.account_number)
    return ln is not None and abs(lender_three_part_total(ln)) <= TIE_TOLERANCE


def _skip_line(rec: GLRecord) -> ReconLine:
    return ReconLine(
        entity=rec.entity,
        account_type=rec.account_type,
        account_number=rec.account_number,
        description=rec.description,
        gl_balance=rec.gl_balance,
        source_balance=0.0,
        variance=0.0,
        classification="skipped",
        source_label="dormant / zero-activity",
        note="Dormant zero-activity account skipped per policy (no reconciliation required).",
    )


def _reconcile_cash(
    rec: GLRecord,
    banks: dict[str, BankStatement],
    threshold: float,
) -> ReconLine:
    bank = banks.get(rec.account_number)
    if bank is None:
        return ReconLine(
            entity=rec.entity,
            account_type="cash",
            account_number=rec.account_number,
            description=rec.description,
            gl_balance=rec.gl_balance,
            source_balance=0.0,
            variance=round(rec.gl_balance, 2),
            classification="flag" if abs(rec.gl_balance) > threshold else "timing",
            source_label="no bank statement found",
            note="No matching bank statement for this account number.",
        )

    variance = compute_variance(rec.gl_balance, bank.ending_balance)
    classification = classify(variance, threshold)
    return ReconLine(
        entity=rec.entity,
        account_type="cash",
        account_number=rec.account_number,
        description=rec.description,
        gl_balance=round(rec.gl_balance, 2),
        source_balance=round(bank.ending_balance, 2),
        variance=variance,
        classification=classification,
        source_label=f"{bank.bank_name}, ending {bank.statement_date}",
        note=_default_note(classification, variance, "bank ending balance"),
    )


def _reconcile_debt(
    rec: GLRecord,
    lenders: dict[str, LenderStatement],
    threshold: float,
) -> ReconLine:
    ln = lenders.get(rec.account_number)
    if ln is None:
        return ReconLine(
            entity=rec.entity,
            account_type="debt",
            account_number=rec.account_number,
            description=rec.description,
            gl_balance=rec.gl_balance,
            source_balance=0.0,
            variance=round(rec.gl_balance, 2),
            classification="flag" if abs(rec.gl_balance) > threshold else "timing",
            source_label="no lender statement found",
            note="No matching lender statement for this account number.",
        )

    source_total = lender_three_part_total(ln)
    variance = compute_variance(rec.gl_balance, source_total)
    classification = classify(variance, threshold)
    return ReconLine(
        entity=rec.entity,
        account_type="debt",
        account_number=rec.account_number,
        description=rec.description,
        gl_balance=round(rec.gl_balance, 2),
        source_balance=source_total,
        variance=variance,
        classification=classification,
        source_label=f"{ln.lender_name}, stmt {ln.statement_date}",
        note=_default_note(classification, variance, "lender 3-part total"),
        principal=round(ln.principal, 2),
        interest_reserve=round(ln.current_interest_reserve, 2),
        late_paydown=round(ln.late_paydown, 2),
    )


def _default_note(
    classification: Classification, variance: float, source_desc: str
) -> str:
    if classification == "clean":
        return f"Ties to {source_desc}."
    if classification == "timing":
        return (
            f"Immaterial variance of ${variance:,.2f} vs. {source_desc} "
            "(within threshold; treated as timing/noise)."
        )
    return (
        f"Material variance of ${variance:,.2f} vs. {source_desc} "
        "— escalated for review."
    )


def _assign_flag_ids(result: ReconResult) -> None:
    """Assign sequential FLAG-### ids to flagged lines (cash then debt)."""
    counter = 1
    for ln in result.all_active_lines:
        if ln.classification == "flag":
            ln.flag_id = f"FLAG-{counter:03d}"
            counter += 1
