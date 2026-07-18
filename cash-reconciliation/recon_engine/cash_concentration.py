"""Fictional, validation-only cash-concentration / sweep tie-out controls.

A cash manager's daily control over a concentration (header) account: every
funded sub-account sweeps its balance up into the concentration account, and the
totals must tie.  This validator independently re-derives both the sweep total
and the concentration roll-forward and confirms they meet:

    swept total = sum(sub-account swept amounts)  == concentration sweeps in
    closing     = opening + sweeps in - disbursements
    control     = displayed closing == rederived closing

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
class SweepLine:
    """One fictional sub-account sweep line, expressed in integer cents.

    ``swept_amount_cents`` is a magnitude (>= 0): the balance the sub-account
    swept up into the concentration account for the period.
    """

    sub_account: str
    swept_amount_cents: object


@dataclass(frozen=True)
class ConcentrationAccount:
    """One fictional concentration account roll-forward, in integer cents.

    ``sweeps_in_cents`` is the total funding swept up from the sub-accounts and
    must tie to the sum of the sweep lines; ``disbursements_cents`` is a
    magnitude (>= 0); ``displayed_closing_cents`` is the presented ending
    balance the validator independently re-derives.
    """

    entity: str
    account: str
    period: str
    opening_cents: object
    sweeps_in_cents: object
    disbursements_cents: object
    displayed_closing_cents: object


@dataclass(frozen=True)
class CashConcentrationFinding:
    code: str
    detail: str
    entity: str = ""
    account: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class CashConcentrationResult:
    period: str
    entity: str
    account: str
    sub_account_count: int
    swept_total_cents: object
    rederived_closing_cents: object
    findings: tuple[CashConcentrationFinding, ...]
    manual_gates: tuple[str, ...] = (
        "obtain and tie the controlled bank feed for the exact period",
        "confirm each sub-account swept balance against its own statement",
        "confirm the concentration credit posts for the full swept total",
        "approve disbursements and any manual funding adjustments",
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


class CashConcentrationValidator:
    """Validate one fictional concentration sweep tie-out without posting."""

    def __init__(
        self, account: ConcentrationAccount, sweep_lines: Iterable[SweepLine]
    ) -> None:
        self.period = _canonical_period(account.period, "period")
        self.account = account
        self.sweep_lines = tuple(sweep_lines)

    _AMOUNT_FIELDS = (
        "opening_cents",
        "sweeps_in_cents",
        "disbursements_cents",
        "displayed_closing_cents",
    )

    def run(self) -> CashConcentrationResult:
        findings: list[CashConcentrationFinding] = []
        account = self.account
        entity = account.entity if isinstance(account.entity, str) else str(account.entity)
        code = account.account if isinstance(account.account, str) else str(account.account)

        def add(finding_code: str, detail: str, severity: str = "ERROR") -> None:
            findings.append(CashConcentrationFinding(finding_code, detail, entity, code, severity))

        # Concentration-account structure.
        concentration_valid = True
        if not _clean_text(account.entity):
            add("ENTITY_INVALID", "concentration entity must be trimmed and nonblank")
            concentration_valid = False
        if not isinstance(account.account, str) or not _ACCOUNT_RE.fullmatch(account.account):
            add("ACCOUNT_INVALID", "concentration account is not canonical")
            concentration_valid = False

        invalid = [name for name in self._AMOUNT_FIELDS if not _valid_amount(getattr(account, name))]
        if invalid:
            add("AMOUNT_INVALID", "integer cents required for " + ", ".join(invalid))
            concentration_valid = False

        # Concentration magnitudes must not be negative (only when integers).
        if concentration_valid and account.disbursements_cents < 0:
            add("DISBURSEMENTS_NEGATIVE", "disbursements is a magnitude and cannot be negative")

        # Sub-account sweep lines.
        seen: set[str] = set()
        swept_total = 0
        swept_total_valid = True
        if not self.sweep_lines:
            add("SUB_ACCOUNT_SET_EMPTY", "no sub-account sweep lines were provided")

        for position, line in enumerate(self.sweep_lines, start=1):
            sub = line.sub_account if isinstance(line.sub_account, str) else str(line.sub_account)

            def add_line(finding_code: str, detail: str, severity: str = "ERROR") -> None:
                findings.append(CashConcentrationFinding(finding_code, detail, entity, sub, severity))

            line_valid = True
            if not isinstance(line.sub_account, str) or not _ACCOUNT_RE.fullmatch(line.sub_account):
                add_line("SUB_ACCOUNT_INVALID", f"sweep line {position} sub-account is not canonical")
                line_valid = False
            if not _valid_amount(line.swept_amount_cents):
                add_line("SUB_ACCOUNT_AMOUNT_INVALID", f"sweep line {position} swept amount must use integer cents")
                line_valid = False
                swept_total_valid = False
            if not line_valid:
                continue

            key = line.sub_account.casefold()
            if key in seen:
                add_line("SUB_ACCOUNT_DUPLICATE", f"sweep line {position} duplicates a sub-account key")
                continue
            seen.add(key)

            if line.swept_amount_cents < 0:
                add_line("SWEPT_AMOUNT_NEGATIVE", f"sweep line {position} swept amount cannot be negative")
            swept_total += line.swept_amount_cents

        # Sweep tie-out: swept total must equal the concentration sweeps in.
        swept_total_out = swept_total if swept_total_valid else None
        sweeps_in_valid = _valid_amount(account.sweeps_in_cents)
        if swept_total_valid and sweeps_in_valid and self.sweep_lines:
            if swept_total != account.sweeps_in_cents:
                add(
                    "SWEEP_TIE_OUT",
                    f"sub-account swept total {swept_total} != concentration sweeps in "
                    f"{account.sweeps_in_cents} (difference {swept_total - account.sweeps_in_cents})",
                )

        # Concentration roll-forward: closing = opening + sweeps in - disbursements.
        rederived_closing: object = None
        if concentration_valid:
            rederived_closing = (
                account.opening_cents + account.sweeps_in_cents - account.disbursements_cents
            )
            if account.displayed_closing_cents != rederived_closing:
                add(
                    "CONCENTRATION_ROLLFORWARD_OUT_OF_TIE",
                    f"displayed closing {account.displayed_closing_cents} != rederived closing "
                    f"{rederived_closing}",
                )

        return CashConcentrationResult(
            period=self.period,
            entity=entity,
            account=code,
            sub_account_count=len(self.sweep_lines),
            swept_total_cents=swept_total_out,
            rederived_closing_cents=rederived_closing,
            findings=tuple(findings),
        )


def demo_concentration() -> tuple[ConcentrationAccount, tuple[SweepLine, ...]]:
    """Return a clean, tying fictional concentration sweep (integer cents).

    Two sub-account sweeps sum exactly to the concentration sweeps in, and the
    roll-forward ties: opening + sweeps in - disbursements == displayed closing.
    """

    account = ConcentrationAccount(
        entity="Cedar Demo LLC",
        account="CASH-1900",
        period="2026-06",
        opening_cents=500_000,
        sweeps_in_cents=800_000,
        disbursements_cents=200_000,
        displayed_closing_cents=1_100_000,
    )
    sweep_lines = (
        SweepLine(sub_account="CASH-2001", swept_amount_cents=300_000),
        SweepLine(sub_account="CASH-2002", swept_amount_cents=500_000),
    )
    return account, sweep_lines


__all__ = [
    "CashConcentrationFinding",
    "CashConcentrationResult",
    "CashConcentrationValidator",
    "ConcentrationAccount",
    "SweepLine",
    "demo_concentration",
]
