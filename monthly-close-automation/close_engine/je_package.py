"""Fictional, validation-only monthly journal-entry support-package controls.

Re-derives the mechanics of a generic monthly per-project journal-entry
support workbook: several journal entries (one per tab), each a set of
account lines with debits and credits, plus carryforward and intercompany
entries. It is deliberately read-only — it independently re-adds each entry,
proves debits equal credits, and compares to the prior month, but it never
emits a journal line, import payload, or posting action.

All data exercised here is FICTIONAL. The module encodes no private workbook
path, formula, coordinate, account, entity, memo, amount, or fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class JournalLine:
    account_id: str
    description: str
    debit_cents: object
    credit_cents: object


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    period: str
    lines: tuple[JournalLine, ...]
    cached_debit_total_cents: object
    cached_credit_total_cents: object
    one_sided_allowed: bool = False
    carryforward: bool = False


@dataclass(frozen=True)
class JournalEntryPackage:
    period: str
    entries: tuple[JournalEntry, ...]
    source_fingerprint: str


@dataclass(frozen=True)
class JournalPackageFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class JournalPackageResult:
    period: str
    entry_count: int
    line_count: int
    balanced_entry_count: int
    out_of_balance_count: int
    one_sided_count: int
    carryforward_count: int
    stale_period_count: int
    total_debits_cents: int
    total_credits_cents: int
    entry_added_count: int
    entry_removed_count: int
    carryforward_change_count: int
    findings: tuple[JournalPackageFinding, ...]
    manual_gates: tuple[str, ...] = (
        "tie each entry to the controlled account/entity/intercompany map and its invoice or contract support",
        "approve classification, cutoff, and the intercompany counterparty leg booked on the other entity",
        "confirm the package is the authoritative month and has not been superseded",
        "post only through the approved human-controlled process and complete a post-entry GL tie-out",
        "generate no journal, import, or posting action from this validator",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)
    posting_actions: tuple[object, ...] = field(default_factory=tuple)

    @property
    def mechanical_clean(self) -> bool:
        return not any(finding.severity == "ERROR" for finding in self.findings)

    @property
    def verdict(self) -> str:
        return "READY FOR HUMAN REVIEW" if self.mechanical_clean else "NEEDS REVIEW"

    @property
    def validation_only(self) -> bool:
        return True

    @property
    def posting_authorized(self) -> bool:
        return False


def _period(value: object, field_name: str) -> date:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def _previous_period(value: str) -> str:
    current = _period(value, "current.period")
    if current.month == 1:
        return f"{current.year - 1:04d}-12"
    return f"{current.year:04d}-{current.month - 1:02d}"


def _is_period(value: object) -> bool:
    return isinstance(value, str) and bool(_PERIOD_RE.fullmatch(value))


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


class JournalPackageValidator:
    """Validate a fictional current and optional prior monthly JE support package."""

    def __init__(
        self,
        current: JournalEntryPackage,
        prior: JournalEntryPackage | None = None,
    ) -> None:
        _period(current.period, "current.period")
        if prior is not None:
            _period(prior.period, "prior.period")
        self.current = current
        self.prior = prior

    @staticmethod
    def _add(
        findings: list[JournalPackageFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(JournalPackageFinding(code, detail, location, severity))

    def _validate_entry(
        self,
        entry: JournalEntry,
        package_period: str,
        findings: list[JournalPackageFinding],
        code,
    ) -> tuple[int, int, bool]:
        location = entry.entry_id if isinstance(entry.entry_id, str) else repr(entry.entry_id)
        if not _clean_text(entry.entry_id):
            self._add(findings, code("UNSAFE_ENTRY_ID"), "entry id is blank or untrimmed", location)

        if not _is_period(entry.period):
            self._add(findings, code("UNSAFE_ENTRY_PERIOD"), "entry period must be canonical YYYY-MM", location)
        elif entry.period != package_period and not entry.carryforward:
            self._add(findings, code("STALE_ENTRY_PERIOD"), f"entry period {entry.period} does not match package period {package_period}", location)

        debit_sum = 0
        credit_sum = 0
        for index, line in enumerate(entry.lines):
            line_location = f"{location}#{index + 1}"
            if not _clean_text(line.account_id):
                self._add(findings, code("UNSAFE_ACCOUNT_ID"), "account id is blank or untrimmed", line_location)
            if not _clean_text(line.description):
                self._add(findings, code("UNSAFE_LINE_DESCRIPTION"), "line description is blank or untrimmed", line_location)
            debit_ok = _integer(line.debit_cents) and line.debit_cents >= 0
            credit_ok = _integer(line.credit_cents) and line.credit_cents >= 0
            if not debit_ok or not credit_ok:
                self._add(findings, code("UNSAFE_LINE_AMOUNT"), "debit and credit must be non-negative integer cents", line_location)
                continue
            if line.debit_cents > 0 and line.credit_cents > 0:
                self._add(findings, code("LINE_BOTH_DEBIT_AND_CREDIT"), "a line cannot be both a debit and a credit", line_location)
            debit_sum += line.debit_cents
            credit_sum += line.credit_cents

        if not _integer(entry.cached_debit_total_cents) or entry.cached_debit_total_cents != debit_sum:
            self._add(findings, code("ENTRY_DEBIT_TOTAL_OUT_OF_TIE"), f"cached debit total does not equal rederived {debit_sum}", location)
        if not _integer(entry.cached_credit_total_cents) or entry.cached_credit_total_cents != credit_sum:
            self._add(findings, code("ENTRY_CREDIT_TOTAL_OUT_OF_TIE"), f"cached credit total does not equal rederived {credit_sum}", location)

        balanced = debit_sum == credit_sum
        if not balanced:
            if entry.one_sided_allowed:
                self._add(findings, code("ONE_SIDED_ENTRY_REVIEW"), f"intercompany entry is one-sided (debits {debit_sum} vs credits {credit_sum}); confirm the counterparty leg", location, "WARNING")
            else:
                self._add(findings, code("ENTRY_OUT_OF_BALANCE"), f"debits {debit_sum} do not equal credits {credit_sum}", location)
        return debit_sum, credit_sum, balanced

    def _validate_package(
        self,
        package: JournalEntryPackage,
        findings: list[JournalPackageFinding],
        *,
        prefix: str = "",
    ) -> dict[str, tuple[int, int, bool]]:
        def code(value: str) -> str:
            return f"{prefix}{value}"

        if not isinstance(package.source_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(package.source_fingerprint):
            self._add(findings, code("UNSAFE_SOURCE_FINGERPRINT"), "source fingerprint must be lowercase SHA-256 evidence")
        if not package.entries:
            self._add(findings, code("PACKAGE_POPULATION_MISSING"), "at least one journal entry is required")

        entry_map: dict[str, tuple[int, int, bool]] = {}
        seen: set[str] = set()
        for entry in package.entries:
            key = entry.entry_id.casefold() if isinstance(entry.entry_id, str) else repr(entry.entry_id)
            if key in seen:
                self._add(findings, code("DUPLICATE_ENTRY"), "journal entry id is not unique", key)
            seen.add(key)
            debit_sum, credit_sum, balanced = self._validate_entry(entry, package.period, findings, code)
            entry_map[key] = (debit_sum, credit_sum, balanced)
        return entry_map

    def _compare_prior(
        self,
        current_entries: set[str],
        findings: list[JournalPackageFinding],
    ) -> tuple[int, int, int]:
        if self.prior is None:
            return 0, 0, 0
        if self.prior.period != _previous_period(self.current.period):
            self._add(findings, "PRIOR_PERIOD_MISMATCH", "comparator is not the immediately preceding month", self.prior.period)
        prior_map = self._validate_package(self.prior, findings, prefix="PRIOR_")
        if self.current.source_fingerprint == self.prior.source_fingerprint:
            self._add(findings, "IDENTICAL_PERIOD_FINGERPRINTS", "sequential packages have the same source fingerprint", severity="WARNING")

        prior_entries = set(prior_map)
        added = current_entries - prior_entries
        removed = prior_entries - current_entries
        if added or removed:
            self._add(findings, "ENTRY_POPULATION_CHANGED", "the current/prior journal-entry population changed", severity="WARNING")

        carryforward_changes = 0
        current_carry = {e.entry_id.casefold(): e for e in self.current.entries if isinstance(e.entry_id, str) and e.carryforward}
        prior_carry = {e.entry_id.casefold(): e for e in self.prior.entries if isinstance(e.entry_id, str) and e.carryforward}
        for key in current_carry.keys() & prior_carry.keys():
            cur = self._entry_totals(current_carry[key])
            pri = self._entry_totals(prior_carry[key])
            if cur != pri:
                carryforward_changes += 1
                self._add(findings, "CARRYFORWARD_ENTRY_CHANGED", "a carryforward entry changed between months", key)
        return len(added), len(removed), carryforward_changes

    @staticmethod
    def _entry_totals(entry: JournalEntry) -> tuple[int, int]:
        debit = sum(line.debit_cents for line in entry.lines if _integer(line.debit_cents))
        credit = sum(line.credit_cents for line in entry.lines if _integer(line.credit_cents))
        return debit, credit

    def validate(self) -> JournalPackageResult:
        findings: list[JournalPackageFinding] = []
        entry_map = self._validate_package(self.current, findings)
        entry_added, entry_removed, carryforward_changes = self._compare_prior(set(entry_map), findings)

        total_debits = sum(debit for debit, _credit, _balanced in entry_map.values())
        total_credits = sum(credit for _debit, credit, _balanced in entry_map.values())
        balanced = sum(1 for _d, _c, is_balanced in entry_map.values() if is_balanced)
        one_sided = sum(1 for entry in self.current.entries if entry.one_sided_allowed)
        out_of_balance = sum(
            1
            for entry, (_d, _c, is_balanced) in zip(self.current.entries, entry_map.values())
            if not is_balanced and not entry.one_sided_allowed
        )
        stale = sum(
            1
            for entry in self.current.entries
            if _is_period(entry.period) and entry.period != self.current.period and not entry.carryforward
        )
        return JournalPackageResult(
            period=self.current.period,
            entry_count=len(self.current.entries),
            line_count=sum(len(entry.lines) for entry in self.current.entries),
            balanced_entry_count=balanced,
            out_of_balance_count=out_of_balance,
            one_sided_count=one_sided,
            carryforward_count=sum(1 for entry in self.current.entries if entry.carryforward),
            stale_period_count=stale,
            total_debits_cents=total_debits,
            total_credits_cents=total_credits,
            entry_added_count=entry_added,
            entry_removed_count=entry_removed,
            carryforward_change_count=carryforward_changes,
            findings=tuple(findings),
        )


__all__ = [
    "JournalEntry",
    "JournalEntryPackage",
    "JournalLine",
    "JournalPackageFinding",
    "JournalPackageResult",
    "JournalPackageValidator",
]
