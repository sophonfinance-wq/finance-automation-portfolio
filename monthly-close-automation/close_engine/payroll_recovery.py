"""Fictional, validation-only payroll-recovery schedule controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_FISCAL_MONTHS = (7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6)


@dataclass(frozen=True)
class RecoveryLine:
    entity_id: str
    project_id: str
    fiscal_month_amounts_cents: tuple[object, ...]
    cached_total_cents: object
    source_reference: str


@dataclass(frozen=True)
class PayrollRecoverySnapshot:
    period: str
    lines: tuple[RecoveryLine, ...]
    cached_month_totals_cents: tuple[object, ...]
    cached_grand_total_cents: object
    source_fingerprint: str


@dataclass(frozen=True)
class PayrollRecoveryFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class PayrollRecoveryResult:
    current_period: str
    line_count: int
    entity_count: int
    project_count: int
    negative_amount_count: int
    entity_added_count: int
    entity_removed_count: int
    project_added_count: int
    project_removed_count: int
    historical_change_count: int
    grand_total_change_cents: int | None
    findings: tuple[PayrollRecoveryFinding, ...]
    manual_gates: tuple[str, ...] = (
        "tie the schedule to the controlled payroll register, ledger, intercompany, and recovery support",
        "approve confidentiality, recoverability, classification, allocation basis, ownership, and cutoff",
        "confirm the schedule remains active and has not been superseded",
        "approve any journal, payroll-system, import, posting, or statement use outside this validator",
        "generate no journal, payroll update, import, or posting action from this validator",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    payroll_actions: tuple[object, ...] = field(default_factory=tuple)
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
    def payroll_update_authorized(self) -> bool:
        return False

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


def _fiscal_index(value: str) -> int:
    return _FISCAL_MONTHS.index(_period(value, "period").month)


def _fiscal_year(value: str) -> int:
    current = _period(value, "period")
    return current.year + 1 if current.month >= 7 else current.year


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class PayrollRecoveryValidator:
    """Validate fictional current and optional prior monthly recovery evidence."""

    def __init__(
        self,
        current: PayrollRecoverySnapshot,
        prior: PayrollRecoverySnapshot | None = None,
    ) -> None:
        _period(current.period, "current.period")
        if prior is not None:
            _period(prior.period, "prior.period")
        self.current = current
        self.prior = prior

    @staticmethod
    def _add(
        findings: list[PayrollRecoveryFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(PayrollRecoveryFinding(code, detail, location, severity))

    def _validate_snapshot(
        self,
        snapshot: PayrollRecoverySnapshot,
        findings: list[PayrollRecoveryFinding],
        *,
        prefix: str = "",
    ) -> tuple[dict[tuple[str, str], tuple[int, ...]], tuple[int, ...], int]:
        def code(value: str) -> str:
            return f"{prefix}{value}"

        if not isinstance(snapshot.source_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(snapshot.source_fingerprint):
            self._add(findings, code("UNSAFE_SOURCE_FINGERPRINT"), "source fingerprint must be lowercase SHA-256 evidence")
        if not snapshot.lines:
            self._add(findings, code("RECOVERY_POPULATION_MISSING"), "at least one recovery line is required")
        if len(snapshot.cached_month_totals_cents) != 12:
            self._add(findings, code("MONTH_TOTAL_VECTOR_LENGTH"), "cached fiscal-month totals must contain 12 values")

        target_index = _fiscal_index(snapshot.period)
        line_map: dict[tuple[str, str], tuple[int, ...]] = {}
        month_totals = [0] * 12
        negative_count = 0
        for line in snapshot.lines:
            location = f"{line.entity_id}/{line.project_id}"
            for value, finding_code in (
                (line.entity_id, "UNSAFE_ENTITY_ID"),
                (line.project_id, "UNSAFE_PROJECT_ID"),
                (line.source_reference, "UNSAFE_SOURCE_REFERENCE"),
            ):
                if not _clean_text(value):
                    self._add(findings, code(finding_code), "controlled text is blank or untrimmed", location)
            key = (line.entity_id, line.project_id)
            if key in line_map:
                self._add(findings, code("DUPLICATE_RECOVERY_LINE"), "entity/project line is not unique", location)
            if len(line.fiscal_month_amounts_cents) != 12:
                self._add(findings, code("MONTH_VECTOR_LENGTH"), "recovery line must contain 12 fiscal-month values", location)
                continue
            safe_amounts: list[int] = []
            for index, amount in enumerate(line.fiscal_month_amounts_cents):
                if not _integer(amount):
                    self._add(findings, code("UNSAFE_RECOVERY_AMOUNT"), "recovery amount must be integer cents", location)
                    safe_amounts.append(0)
                    continue
                safe_amounts.append(amount)
                month_totals[index] += amount
                if amount < 0:
                    negative_count += 1
                    self._add(findings, code("NEGATIVE_RECOVERY_REVIEW"), "negative recovery requires support", location, "WARNING")
                if index > target_index and amount != 0:
                    self._add(findings, code("FUTURE_PERIOD_ACTIVITY"), "recovery activity appears after the snapshot month", location)
            line_map[key] = tuple(safe_amounts)
            rederived = sum(safe_amounts)
            if not _integer(line.cached_total_cents):
                self._add(findings, code("UNSAFE_CACHED_LINE_TOTAL"), "cached line total must be integer cents", location)
            elif line.cached_total_cents != rederived:
                self._add(findings, code("LINE_TOTAL_OUT_OF_TIE"), f"cached {line.cached_total_cents} does not equal rederived {rederived}", location)

        if len(snapshot.cached_month_totals_cents) == 12:
            for index, (cached, rederived) in enumerate(zip(snapshot.cached_month_totals_cents, month_totals)):
                location = str(index + 1)
                if not _integer(cached):
                    self._add(findings, code("UNSAFE_CACHED_MONTH_TOTAL"), "cached month total must be integer cents", location)
                elif cached != rederived:
                    self._add(findings, code("MONTH_TOTAL_OUT_OF_TIE"), f"cached {cached} does not equal rederived {rederived}", location)
        grand_total = sum(month_totals)
        if not _integer(snapshot.cached_grand_total_cents):
            self._add(findings, code("UNSAFE_CACHED_GRAND_TOTAL"), "cached grand total must be integer cents")
        elif snapshot.cached_grand_total_cents != grand_total:
            self._add(findings, code("GRAND_TOTAL_OUT_OF_TIE"), f"cached {snapshot.cached_grand_total_cents} does not equal rederived {grand_total}")
        return line_map, tuple(month_totals), negative_count

    def _compare_prior(
        self,
        current_lines: dict[tuple[str, str], tuple[int, ...]],
        current_totals: tuple[int, ...],
        findings: list[PayrollRecoveryFinding],
    ) -> tuple[int, int, int, int, int, int | None]:
        if self.prior is None:
            return 0, 0, 0, 0, 0, None
        if self.prior.period != _previous_period(self.current.period):
            self._add(findings, "PRIOR_PERIOD_MISMATCH", "comparator is not the immediately preceding month", self.prior.period)
        prior_lines, prior_totals, _ = self._validate_snapshot(self.prior, findings, prefix="PRIOR_")
        if self.current.source_fingerprint == self.prior.source_fingerprint:
            self._add(findings, "IDENTICAL_PERIOD_FINGERPRINTS", "sequential snapshots have the same source fingerprint", severity="WARNING")

        current_entities = {key[0] for key in current_lines}
        prior_entities = {key[0] for key in prior_lines}
        current_projects = {key[1] for key in current_lines}
        prior_projects = {key[1] for key in prior_lines}
        entity_added = current_entities - prior_entities
        entity_removed = prior_entities - current_entities
        project_added = current_projects - prior_projects
        project_removed = prior_projects - current_projects
        if entity_added or entity_removed or project_added or project_removed:
            self._add(findings, "RECOVERY_POPULATION_CHANGED", "entity or project recovery population changed", severity="WARNING")

        historical_changes = 0
        if _fiscal_year(self.current.period) == _fiscal_year(self.prior.period):
            prior_index = _fiscal_index(self.prior.period)
            for key in current_lines.keys() & prior_lines.keys():
                for index in range(prior_index + 1):
                    if current_lines[key][index] != prior_lines[key][index]:
                        historical_changes += 1
            if historical_changes:
                self._add(findings, "HISTORICAL_ACTIVITY_CHANGED", "previously reported fiscal-month recovery activity changed")

        grand_change = sum(current_totals) - sum(prior_totals)
        target_activity = current_totals[_fiscal_index(self.current.period)]
        if grand_change != target_activity:
            self._add(findings, "TOTAL_CHANGE_OUT_OF_TIE", f"grand-total change {grand_change} does not equal target-month activity {target_activity}")
        elif grand_change:
            self._add(findings, "MONTHLY_CHANGE_REVIEW", "month-over-month recovery change requires source support", severity="WARNING")
        return (
            len(entity_added), len(entity_removed), len(project_added), len(project_removed),
            historical_changes, grand_change,
        )

    def validate(self) -> PayrollRecoveryResult:
        findings: list[PayrollRecoveryFinding] = []
        current_lines, current_totals, negative_count = self._validate_snapshot(self.current, findings)
        entity_added, entity_removed, project_added, project_removed, historical, grand_change = self._compare_prior(
            current_lines, current_totals, findings
        )
        return PayrollRecoveryResult(
            current_period=self.current.period,
            line_count=len(self.current.lines),
            entity_count=len({line.entity_id for line in self.current.lines}),
            project_count=len({line.project_id for line in self.current.lines}),
            negative_amount_count=negative_count,
            entity_added_count=entity_added,
            entity_removed_count=entity_removed,
            project_added_count=project_added,
            project_removed_count=project_removed,
            historical_change_count=historical,
            grand_total_change_cents=grand_change,
            findings=tuple(findings),
        )


__all__ = [
    "PayrollRecoveryFinding",
    "PayrollRecoveryResult",
    "PayrollRecoverySnapshot",
    "PayrollRecoveryValidator",
    "RecoveryLine",
]
