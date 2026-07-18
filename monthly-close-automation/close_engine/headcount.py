"""Fictional, validation-only annual headcount-support controls.

This module re-derives the mechanics of a generic annual entity-headcount
support schedule (the kind of one-table workpaper an auditor might request):
one row per legal entity, one descending column per reporting year, and a
re-added total row. It is deliberately read-only. It never handles
employee-level data and never emits a journal, payroll, import,
audit-submission, or posting action.

All data exercised here is FICTIONAL. The module encodes no private workbook
path, formula, coordinate, entity name, headcount, or fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_MIN_YEAR = 2000
_MAX_YEAR = 2100


@dataclass(frozen=True)
class EntityHeadcount:
    entity_id: str
    annual_counts: tuple[object, ...]
    source_reference: str


@dataclass(frozen=True)
class HeadcountSnapshot:
    as_of_year: int
    as_of_month: int
    annual_years: tuple[object, ...]
    entities: tuple[EntityHeadcount, ...]
    cached_annual_totals: tuple[object, ...]
    source_fingerprint: str


@dataclass(frozen=True)
class HeadcountFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class HeadcountResult:
    as_of_year: int
    as_of_month: int
    entity_count: int
    year_count: int
    negative_count: int
    entity_added_count: int
    entity_removed_count: int
    historical_change_count: int
    current_year_total: int | None
    prior_year_total: int | None
    annual_total_change: int | None
    entity_change_sum: int
    findings: tuple[HeadcountFinding, ...]
    manual_gates: tuple[str, ...] = (
        "tie entity totals to the controlled employee roster, payroll/HR report, and approved legal-entity perimeter",
        "approve the as-of date and the employee, FTE, contractor, leave, termination, transfer, shared-service, and vacancy definitions",
        "protect personnel information and approve any auditor or third-party delivery",
        "approve any journal, payroll-system, import, audit-submission, or posting use outside this validator",
        "generate no journal, payroll, import, audit-submission, or posting action from this validator",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    payroll_actions: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)
    audit_submissions: tuple[object, ...] = field(default_factory=tuple)
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
    def audit_submission_authorized(self) -> bool:
        return False

    @property
    def posting_authorized(self) -> bool:
        return False


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_year(value: object) -> bool:
    return _integer(value) and _MIN_YEAR <= value <= _MAX_YEAR


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


class HeadcountValidator:
    """Validate fictional current and optional prior annual headcount evidence."""

    def __init__(
        self,
        current: HeadcountSnapshot,
        prior: HeadcountSnapshot | None = None,
    ) -> None:
        self._require_period(current, "current")
        if prior is not None:
            self._require_period(prior, "prior")
        self.current = current
        self.prior = prior

    @staticmethod
    def _require_period(snapshot: HeadcountSnapshot, label: str) -> None:
        if not _valid_year(snapshot.as_of_year):
            raise ValueError(f"{label}.as_of_year must be an integer in {_MIN_YEAR}..{_MAX_YEAR}")
        if not _integer(snapshot.as_of_month) or not 1 <= snapshot.as_of_month <= 12:
            raise ValueError(f"{label}.as_of_month must be an integer in 1..12")

    @staticmethod
    def _add(
        findings: list[HeadcountFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(HeadcountFinding(code, detail, location, severity))

    def _validate_years(
        self,
        snapshot: HeadcountSnapshot,
        findings: list[HeadcountFinding],
        code,
    ) -> None:
        raw = snapshot.annual_years
        if not raw:
            self._add(findings, code("YEAR_HEADERS_MISSING"), "at least one reporting-year header is required")
            return
        for value in raw:
            if not _integer(value):
                self._add(findings, code("UNSAFE_YEAR_HEADER"), "year header must be a whole integer", str(value))
        if _integer(raw[0]) and raw[0] != snapshot.as_of_year:
            self._add(
                findings,
                code("YEAR_HEADER_START_MISMATCH"),
                f"first year header {raw[0]} must equal as_of_year {snapshot.as_of_year}",
                str(raw[0]),
            )
        for index in range(1, len(raw)):
            previous, current = raw[index - 1], raw[index]
            if _integer(previous) and _integer(current) and current != previous - 1:
                self._add(
                    findings,
                    code("YEAR_HEADERS_NOT_CONSECUTIVE"),
                    f"year headers must descend by one; {previous} is followed by {current}",
                    str(current),
                )
        integer_years = [value for value in raw if _integer(value)]
        if len(set(integer_years)) != len(integer_years):
            self._add(findings, code("DUPLICATE_YEAR_HEADER"), "a reporting-year header appears more than once")

    def _validate_snapshot(
        self,
        snapshot: HeadcountSnapshot,
        findings: list[HeadcountFinding],
        *,
        prefix: str = "",
    ) -> tuple[dict[tuple[str, object], int], tuple[int, ...], set[str], int]:
        def code(value: str) -> str:
            return f"{prefix}{value}"

        if not isinstance(snapshot.source_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(snapshot.source_fingerprint):
            self._add(findings, code("UNSAFE_SOURCE_FINGERPRINT"), "source fingerprint must be lowercase SHA-256 evidence")

        self._validate_years(snapshot, findings, code)
        years = snapshot.annual_years
        year_count = len(years)
        column_totals = [0] * year_count

        if not snapshot.entities:
            self._add(findings, code("HEADCOUNT_POPULATION_MISSING"), "at least one entity row is required")

        counts: dict[tuple[str, object], int] = {}
        entity_keys: set[str] = set()
        negative_count = 0
        for entity in snapshot.entities:
            location = entity.entity_id if isinstance(entity.entity_id, str) else repr(entity.entity_id)
            for value, finding_code in (
                (entity.entity_id, "UNSAFE_ENTITY_ID"),
                (entity.source_reference, "UNSAFE_SOURCE_REFERENCE"),
            ):
                if not _clean_text(value):
                    self._add(findings, code(finding_code), "controlled text is blank or untrimmed", location)
            key = entity.entity_id.casefold() if isinstance(entity.entity_id, str) else location
            if key in entity_keys:
                self._add(findings, code("DUPLICATE_ENTITY"), "entity row is not unique", location)
            entity_keys.add(key)
            if len(entity.annual_counts) != year_count:
                self._add(
                    findings,
                    code("COUNT_VECTOR_LENGTH"),
                    f"entity counts must contain {year_count} values aligned to the year headers",
                    location,
                )
                continue
            for index, amount in enumerate(entity.annual_counts):
                if not _integer(amount):
                    self._add(findings, code("UNSAFE_HEADCOUNT"), "headcount must be a whole integer", location)
                    continue
                if amount < 0:
                    negative_count += 1
                    self._add(findings, code("NEGATIVE_HEADCOUNT"), "headcount cannot be negative", location)
                column_totals[index] += amount
                counts[(key, years[index])] = amount

        if len(snapshot.cached_annual_totals) != year_count:
            self._add(findings, code("TOTAL_VECTOR_LENGTH"), f"cached annual totals must contain {year_count} values")
        else:
            for index, cached in enumerate(snapshot.cached_annual_totals):
                location = str(years[index]) if index < year_count else str(index)
                if not _integer(cached):
                    self._add(findings, code("UNSAFE_CACHED_TOTAL"), "cached annual total must be a whole integer", location)
                elif cached < 0:
                    self._add(findings, code("NEGATIVE_CACHED_TOTAL"), "cached annual total cannot be negative", location)
                elif cached != column_totals[index]:
                    self._add(
                        findings,
                        code("TOTAL_OUT_OF_TIE"),
                        f"cached {cached} does not equal rederived {column_totals[index]}",
                        location,
                    )
        return counts, tuple(column_totals), entity_keys, negative_count

    def _as_of_total(self, snapshot: HeadcountSnapshot, totals: tuple[int, ...]) -> int | None:
        years = list(snapshot.annual_years)
        if snapshot.as_of_year in years:
            index = years.index(snapshot.as_of_year)
            if index < len(totals):
                return totals[index]
        return None

    def _compare_prior(
        self,
        current_counts: dict[tuple[str, object], int],
        current_totals: tuple[int, ...],
        current_entities: set[str],
        findings: list[HeadcountFinding],
    ) -> tuple[int, int, int, int | None, int | None, int]:
        if self.prior is None:
            return 0, 0, 0, None, None, 0

        if self.prior.as_of_year != self.current.as_of_year - 1:
            self._add(findings, "PRIOR_YEAR_MISMATCH", "comparator is not the immediately preceding year", str(self.prior.as_of_year))
        if self.prior.as_of_month != self.current.as_of_month:
            self._add(findings, "PRIOR_MONTH_MISMATCH", "comparator month does not match the current as-of month", str(self.prior.as_of_month))

        prior_counts, prior_totals, prior_entities, _ = self._validate_snapshot(self.prior, findings, prefix="PRIOR_")
        if self.current.source_fingerprint == self.prior.source_fingerprint:
            self._add(findings, "IDENTICAL_PERIOD_FINGERPRINTS", "sequential snapshots have the same source fingerprint", severity="WARNING")

        added = current_entities - prior_entities
        removed = prior_entities - current_entities
        if added or removed:
            self._add(findings, "ENTITY_POPULATION_CHANGED", "the current/prior entity population changed", severity="WARNING")

        current_years = {value for value in self.current.annual_years if _integer(value)}
        prior_years = {value for value in self.prior.annual_years if _integer(value)}
        overlap_years = current_years & prior_years
        historical_changes = 0
        for entity in current_entities & prior_entities:
            for year in overlap_years:
                if current_counts.get((entity, year)) != prior_counts.get((entity, year)):
                    historical_changes += 1
        if historical_changes:
            self._add(findings, "HISTORICAL_VALUE_CHANGED", "a previously reported entity/year headcount changed")

        current_year = self.current.as_of_year
        prior_year = self.prior.as_of_year
        current_total = self._as_of_total(self.current, current_totals)
        prior_total = self._as_of_total(self.prior, prior_totals)
        entity_change_sum = 0
        for entity in current_entities | prior_entities:
            entity_change_sum += current_counts.get((entity, current_year), 0) - prior_counts.get((entity, prior_year), 0)
        total_change = None if current_total is None or prior_total is None else current_total - prior_total
        if total_change is not None and total_change != entity_change_sum:
            self._add(
                findings,
                "TOTAL_CHANGE_OUT_OF_TIE",
                f"annual total change {total_change} does not equal entity change sum {entity_change_sum}",
            )
        elif total_change:
            self._add(findings, "ANNUAL_CHANGE_REVIEW", "the year-over-year headcount change requires roster support", severity="WARNING")
        return len(added), len(removed), historical_changes, prior_total, total_change, entity_change_sum

    def validate(self) -> HeadcountResult:
        findings: list[HeadcountFinding] = []
        current_counts, current_totals, current_entities, negative_count = self._validate_snapshot(self.current, findings)
        current_total = self._as_of_total(self.current, current_totals)
        entity_added, entity_removed, historical, prior_total, total_change, entity_change_sum = self._compare_prior(
            current_counts, current_totals, current_entities, findings
        )
        return HeadcountResult(
            as_of_year=self.current.as_of_year,
            as_of_month=self.current.as_of_month,
            entity_count=len(current_entities),
            year_count=len(self.current.annual_years),
            negative_count=negative_count,
            entity_added_count=entity_added,
            entity_removed_count=entity_removed,
            historical_change_count=historical,
            current_year_total=current_total,
            prior_year_total=prior_total,
            annual_total_change=total_change,
            entity_change_sum=entity_change_sum,
            findings=tuple(findings),
        )


__all__ = [
    "EntityHeadcount",
    "HeadcountFinding",
    "HeadcountResult",
    "HeadcountSnapshot",
    "HeadcountValidator",
]
