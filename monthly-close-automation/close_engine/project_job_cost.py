"""Fictional, validation-only monthly project/job-cost export controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import re
from typing import Iterable


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class JobTransaction:
    transaction_id: str
    job_id: str
    cost_code: str
    transaction_type: str
    transaction_date: str
    accounting_date: str
    amount_cents: object
    description: str
    source_reference: str


@dataclass(frozen=True)
class JobExport:
    job_id: str
    period: str
    transactions: tuple[JobTransaction, ...]
    cached_total_cents: object


@dataclass(frozen=True)
class ProjectJobCostSnapshot:
    period: str
    jobs: tuple[JobExport, ...]


@dataclass(frozen=True)
class ProjectJobCostFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class ProjectJobCostResult:
    current_period: str
    job_count: int
    transaction_count: int
    cost_code_count: int
    negative_transaction_count: int
    post_period_transaction_count: int
    duplicate_transaction_count: int
    job_added_count: int
    job_removed_count: int
    cost_code_added_count: int
    cost_code_removed_count: int
    transaction_type_added_count: int
    transaction_type_removed_count: int
    findings: tuple[ProjectJobCostFinding, ...]
    manual_gates: tuple[str, ...] = (
        "refresh and tie the controlled source-system export",
        "approve job and cost-code mappings and period cutoff",
        "retain invoice, credit, reversal, and approval support",
        "determine capitalization, commitments, and cost to complete",
        "approve any statement, draw, forecast, journal, import, or posting use",
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


def _period_start(value: object, field_name: str) -> date:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def _previous_period(value: str) -> str:
    start = _period_start(value, "current_period")
    if start.month == 1:
        return f"{start.year - 1:04d}-12"
    return f"{start.year:04d}-{start.month - 1:02d}"


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


class ProjectJobCostValidator:
    """Validate fictional current and optional prior monthly job-cost exports."""

    def __init__(
        self,
        current: ProjectJobCostSnapshot,
        prior: ProjectJobCostSnapshot | None = None,
    ) -> None:
        _period_start(current.period, "current.period")
        if prior is not None:
            _period_start(prior.period, "prior.period")
        self.current = current
        self.prior = prior

    @staticmethod
    def _add(
        findings: list[ProjectJobCostFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(ProjectJobCostFinding(code, detail, location, severity))

    def _validate_current(self, findings: list[ProjectJobCostFinding]) -> dict[str, object]:
        period_start = _period_start(self.current.period, "current.period")
        period_end = (
            date(period_start.year + (period_start.month == 12), period_start.month % 12 + 1, 1)
            - timedelta(days=1)
        )
        for duplicate in sorted(_duplicates(job.job_id for job in self.current.jobs)):
            self._add(findings, "DUPLICATE_JOB_EXPORT", "job appears more than once", duplicate)
        if not self.current.jobs:
            self._add(findings, "JOB_EXPORT_MISSING", "at least one job export is required")

        transaction_ids: list[str] = []
        exact_keys: set[tuple[object, ...]] = set()
        exact_duplicates = 0
        negative = 0
        post_period = 0
        cost_codes: set[str] = set()
        transaction_types: set[str] = set()
        for job in self.current.jobs:
            if not _clean_text(job.job_id):
                self._add(findings, "UNSAFE_JOB_ID", "job id is blank or untrimmed", str(job.job_id))
            if job.period != self.current.period:
                self._add(findings, "JOB_PERIOD_MISMATCH", "job period does not equal snapshot period", job.job_id)
            total = 0
            for item in job.transactions:
                transaction_ids.append(item.transaction_id)
                location = item.transaction_id
                for value, code in (
                    (item.transaction_id, "UNSAFE_TRANSACTION_ID"),
                    (item.job_id, "UNSAFE_TRANSACTION_JOB"),
                    (item.cost_code, "UNSAFE_COST_CODE"),
                    (item.transaction_type, "UNSAFE_TRANSACTION_TYPE"),
                    (item.description, "UNSAFE_DESCRIPTION"),
                    (item.source_reference, "UNSAFE_SOURCE_REFERENCE"),
                ):
                    if not _clean_text(value):
                        self._add(findings, code, "controlled text is blank or untrimmed", location)
                if item.job_id != job.job_id:
                    self._add(findings, "TRANSACTION_JOB_MISMATCH", "transaction job differs from export authority", location)
                accounting_date = _parse_date(item.accounting_date)
                transaction_date = _parse_date(item.transaction_date)
                if accounting_date is None or not (period_start <= accounting_date <= period_end):
                    self._add(findings, "ACCOUNTING_DATE_OUT_OF_RANGE", "accounting date is invalid or outside the snapshot month", location)
                if transaction_date is None:
                    self._add(findings, "TRANSACTION_DATE_INVALID", "transaction date is not canonical ISO date", location)
                elif transaction_date > period_end:
                    post_period += 1
                    self._add(findings, "POST_PERIOD_TRANSACTION_DATE_REVIEW", "post-period transaction date carries a current-period accounting date", location, "WARNING")
                if not _amount(item.amount_cents):
                    self._add(findings, "UNSAFE_TRANSACTION_AMOUNT", "amount must be integer cents", location)
                else:
                    total += item.amount_cents
                    if item.amount_cents < 0:
                        negative += 1
                        self._add(findings, "NEGATIVE_TRANSACTION_REVIEW", "negative or reversal transaction requires support", location, "WARNING")
                cost_codes.add(item.cost_code)
                transaction_types.add(item.transaction_type)
                key = (
                    item.job_id,
                    item.cost_code,
                    item.transaction_type,
                    item.transaction_date,
                    item.accounting_date,
                    item.amount_cents,
                    item.description,
                    item.source_reference,
                )
                if key in exact_keys:
                    exact_duplicates += 1
                    self._add(findings, "EXACT_DUPLICATE_TRANSACTION", "exact duplicate transaction key detected", location)
                exact_keys.add(key)
            if not _amount(job.cached_total_cents):
                self._add(findings, "UNSAFE_CACHED_JOB_TOTAL", "cached job total must be integer cents", job.job_id)
            elif job.cached_total_cents != total:
                self._add(findings, "JOB_TOTAL_OUT_OF_TIE", f"cached {job.cached_total_cents} does not equal rederived {total}", job.job_id)

        for duplicate in sorted(_duplicates(transaction_ids)):
            self._add(findings, "DUPLICATE_TRANSACTION_ID", "transaction id is not unique", duplicate)
        return {
            "jobs": {job.job_id for job in self.current.jobs},
            "cost_codes": cost_codes,
            "transaction_types": transaction_types,
            "transaction_count": len(transaction_ids),
            "negative_count": negative,
            "post_period_count": post_period,
            "duplicate_count": exact_duplicates,
        }

    @staticmethod
    def _populations(snapshot: ProjectJobCostSnapshot) -> dict[str, set[str]]:
        return {
            "job": {job.job_id for job in snapshot.jobs},
            "cost_code": {item.cost_code for job in snapshot.jobs for item in job.transactions},
            "transaction_type": {item.transaction_type for job in snapshot.jobs for item in job.transactions},
        }

    def _compare_prior(self, findings: list[ProjectJobCostFinding]) -> dict[str, int]:
        metrics = {
            "job_added_count": 0,
            "job_removed_count": 0,
            "cost_code_added_count": 0,
            "cost_code_removed_count": 0,
            "transaction_type_added_count": 0,
            "transaction_type_removed_count": 0,
        }
        if self.prior is None:
            return metrics
        if self.prior.period != _previous_period(self.current.period):
            self._add(findings, "PRIOR_PERIOD_MISMATCH", "comparator is not the immediately preceding month", self.prior.period)
        current = self._populations(self.current)
        prior = self._populations(self.prior)
        for name in ("job", "cost_code", "transaction_type"):
            added = current[name] - prior[name]
            removed = prior[name] - current[name]
            metrics[f"{name}_added_count"] = len(added)
            metrics[f"{name}_removed_count"] = len(removed)
            if added or removed:
                self._add(
                    findings,
                    f"{name.upper()}_POPULATION_CHANGED",
                    "current/prior population change requires approval",
                    ",".join(sorted(added | removed)),
                    "WARNING",
                )
        return metrics

    def validate(self) -> ProjectJobCostResult:
        findings: list[ProjectJobCostFinding] = []
        evidence = self._validate_current(findings)
        comparison = self._compare_prior(findings)
        return ProjectJobCostResult(
            current_period=self.current.period,
            job_count=len(evidence["jobs"]),
            transaction_count=int(evidence["transaction_count"]),
            cost_code_count=len(evidence["cost_codes"]),
            negative_transaction_count=int(evidence["negative_count"]),
            post_period_transaction_count=int(evidence["post_period_count"]),
            duplicate_transaction_count=int(evidence["duplicate_count"]),
            findings=tuple(findings),
            **comparison,
        )
