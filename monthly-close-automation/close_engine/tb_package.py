"""Fictional, validation-only multi-entity trial-balance package controls.

The public component accepts generic immutable records expressed in integer
cents.  It demonstrates semantic package completeness, formula/cache and
dependency safety, support-to-summary and operations-package ties, controlled
adjustments, and current/prior structural continuity.  It encodes no private
workbook layout, company, account map, path, formula, amount, or connector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Iterable


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ERROR_RE = re.compile(
    r"#(?:REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!|SPILL!|CALC!)",
    re.IGNORECASE,
)

REQUIRED_ROLES = frozenset(
    {
        "instructions",
        "consolidated_summary",
        "holding_company",
        "capital_entities",
        "service_entities",
        "predevelopment_activity",
        "fee_detail",
        "validation_lists",
    }
)

REQUIRED_CONTROL_IDS = frozenset(
    {
        "holding_to_summary",
        "capital_to_summary",
        "services_to_summary",
        "fees_to_summary",
        "consolidated_crossfoot",
        "operations_profit",
        "operations_fees",
        "operations_admin",
        "operations_total",
    }
)

APPROVED_DEPENDENCY_ROLES = frozenset({"operations_package"})


@dataclass(frozen=True)
class PackageRole:
    role: str
    period: str


@dataclass(frozen=True)
class FormulaEvidence:
    formula_id: str
    role: str
    signature: str
    cached_cents: object = None
    expects_numeric_cache: bool = True
    external_dependency_id: str = ""


@dataclass(frozen=True)
class DependencyEvidence:
    dependency_id: str
    role: str
    period: str
    reference: object


@dataclass(frozen=True)
class ControlEvidence:
    control_id: str
    actual_cents: object
    expected_cents: object


@dataclass(frozen=True)
class AdjustmentEvidence:
    adjustment_id: str
    role: str
    amount_cents: object
    is_formula_driven: bool
    support_reference: str = ""
    approval_reference: str = ""


@dataclass(frozen=True)
class TBPackageSnapshot:
    period: str
    roles: tuple[PackageRole, ...]
    formulas: tuple[FormulaEvidence, ...]
    dependencies: tuple[DependencyEvidence, ...]
    controls: tuple[ControlEvidence, ...]
    entity_keys: tuple[str, ...] = ()
    account_keys: tuple[str, ...] = ()
    row_keys: tuple[str, ...] = ()
    adjustments: tuple[AdjustmentEvidence, ...] = ()


@dataclass(frozen=True)
class TBPackageFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class TBPackageResult:
    current_period: str
    role_count: int
    formula_count: int
    external_formula_count: int
    dependency_count: int
    control_count: int
    adjustment_count: int
    formula_added_count: int
    formula_removed_count: int
    formula_changed_count: int
    entity_added_count: int
    entity_removed_count: int
    account_added_count: int
    account_removed_count: int
    row_added_count: int
    row_removed_count: int
    findings: tuple[TBPackageFinding, ...]
    manual_gates: tuple[str, ...] = (
        "refresh and tie every entity trial balance to an approved source report",
        "approve the entity perimeter, account mappings, and classifications",
        "support and approve every project result and manual adjustment",
        "confirm the current operations package is the approved source",
        "resolve every support, crossfoot, and operations-package difference",
        "obtain controller approval for the completed package",
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


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _duplicate_values(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


class TBPackageValidator:
    """Validate a fictional monthly package and optional prior comparator."""

    def __init__(self, current: TBPackageSnapshot, prior: TBPackageSnapshot | None = None) -> None:
        _period_start(current.period, "current.period")
        if prior is not None:
            _period_start(prior.period, "prior.period")
        self.current = current
        self.prior = prior

    @staticmethod
    def _add(
        findings: list[TBPackageFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(TBPackageFinding(code, detail, location, severity))

    def _validate_roles(self, findings: list[TBPackageFinding]) -> None:
        roles = [item.role for item in self.current.roles]
        for duplicate in sorted(_duplicate_values(roles)):
            self._add(findings, "DUPLICATE_ROLE", "semantic role appears more than once", duplicate)
        observed = set(roles)
        for role in sorted(REQUIRED_ROLES - observed):
            self._add(findings, "MISSING_ROLE", "required semantic role is absent", role)
        for role in sorted(observed - REQUIRED_ROLES):
            self._add(findings, "UNKNOWN_ROLE", "semantic role is not approved", role)
        for item in self.current.roles:
            try:
                _period_start(item.period, f"role {item.role} period")
            except ValueError:
                self._add(findings, "INVALID_ROLE_PERIOD", "role period is not canonical YYYY-MM", item.role)
                continue
            if item.period != self.current.period:
                self._add(
                    findings,
                    "ROLE_PERIOD_MISMATCH",
                    f"role period {item.period} does not equal {self.current.period}",
                    item.role,
                )

    def _validate_dependencies(self, findings: list[TBPackageFinding]) -> dict[str, DependencyEvidence]:
        dependencies: dict[str, DependencyEvidence] = {}
        for duplicate in sorted(_duplicate_values(item.dependency_id for item in self.current.dependencies)):
            self._add(findings, "DUPLICATE_DEPENDENCY_ID", "dependency id is not unique", duplicate)
        for item in self.current.dependencies:
            if item.dependency_id not in dependencies:
                dependencies[item.dependency_id] = item
            if item.role not in APPROVED_DEPENDENCY_ROLES:
                self._add(findings, "UNKNOWN_DEPENDENCY_ROLE", "dependency role is not approved", item.dependency_id)
            try:
                _period_start(item.period, f"dependency {item.dependency_id} period")
            except ValueError:
                self._add(findings, "INVALID_DEPENDENCY_PERIOD", "dependency period is not canonical YYYY-MM", item.dependency_id)
            else:
                if item.period != self.current.period:
                    self._add(
                        findings,
                        "DEPENDENCY_PERIOD_MISMATCH",
                        f"dependency period {item.period} does not equal {self.current.period}",
                        item.dependency_id,
                    )
            if not _clean_text(item.reference) or _ERROR_RE.search(str(item.reference)):
                self._add(findings, "UNSAFE_DEPENDENCY_REFERENCE", "dependency reference is blank, untrimmed, or broken", item.dependency_id)
        operation_sources = [item for item in self.current.dependencies if item.role == "operations_package"]
        if len(operation_sources) != 1:
            self._add(
                findings,
                "OPERATIONS_DEPENDENCY_COUNT",
                "exactly one current operations-package dependency is required",
                "operations_package",
            )
        return dependencies

    def _validate_formulas(
        self,
        findings: list[TBPackageFinding],
        dependencies: dict[str, DependencyEvidence],
    ) -> None:
        for duplicate in sorted(_duplicate_values(item.formula_id for item in self.current.formulas)):
            self._add(findings, "DUPLICATE_FORMULA_ID", "formula id is not unique", duplicate)
        for item in self.current.formulas:
            if item.role not in REQUIRED_ROLES:
                self._add(findings, "UNKNOWN_FORMULA_ROLE", "formula role is not approved", item.formula_id)
            if not _clean_text(item.signature) or _ERROR_RE.search(str(item.signature)):
                self._add(findings, "FORMULA_ERROR_TOKEN", "formula signature is blank, untrimmed, or broken", item.formula_id)
            if item.expects_numeric_cache and not _amount(item.cached_cents):
                self._add(findings, "FORMULA_CACHE_MISSING_OR_UNSAFE", "numeric formula cache must be integer cents", item.formula_id)
            if item.external_dependency_id and item.external_dependency_id not in dependencies:
                self._add(findings, "FORMULA_DEPENDENCY_MISSING", "external formula dependency is undeclared", item.formula_id)

    def _validate_controls(self, findings: list[TBPackageFinding]) -> None:
        ids = [item.control_id for item in self.current.controls]
        for duplicate in sorted(_duplicate_values(ids)):
            self._add(findings, "DUPLICATE_CONTROL_ID", "control id is not unique", duplicate)
        observed = set(ids)
        for control_id in sorted(REQUIRED_CONTROL_IDS - observed):
            self._add(findings, "MISSING_REQUIRED_CONTROL", "required package tie-out is absent", control_id)
        for item in self.current.controls:
            if item.control_id not in REQUIRED_CONTROL_IDS:
                self._add(findings, "UNKNOWN_CONTROL", "control id is not approved", item.control_id)
            if not _amount(item.actual_cents) or not _amount(item.expected_cents):
                self._add(findings, "UNSAFE_CONTROL_AMOUNT", "control amounts must be integer cents", item.control_id)
            elif item.actual_cents != item.expected_cents:
                self._add(
                    findings,
                    "CONTROL_OUT_OF_TIE",
                    f"actual {item.actual_cents} does not equal expected {item.expected_cents}",
                    item.control_id,
                )

    def _validate_adjustments(self, findings: list[TBPackageFinding]) -> None:
        for duplicate in sorted(_duplicate_values(item.adjustment_id for item in self.current.adjustments)):
            self._add(findings, "DUPLICATE_ADJUSTMENT_ID", "adjustment id is not unique", duplicate)
        for item in self.current.adjustments:
            if item.role not in REQUIRED_ROLES:
                self._add(findings, "UNKNOWN_ADJUSTMENT_ROLE", "adjustment role is not approved", item.adjustment_id)
            if not _amount(item.amount_cents):
                self._add(findings, "UNSAFE_ADJUSTMENT_AMOUNT", "adjustment amount must be integer cents", item.adjustment_id)
                continue
            if item.amount_cents and (
                not item.is_formula_driven
                and (not _clean_text(item.support_reference) or not _clean_text(item.approval_reference))
            ):
                self._add(
                    findings,
                    "UNSUPPORTED_MANUAL_ADJUSTMENT",
                    "non-formula adjustment requires support and approval references",
                    item.adjustment_id,
                )
            elif item.amount_cents:
                self._add(
                    findings,
                    "ADJUSTMENT_REQUIRES_HUMAN_REVIEW",
                    "supported adjustment remains a controller judgment",
                    item.adjustment_id,
                    "WARNING",
                )

    def _validate_populations(self, findings: list[TBPackageFinding]) -> None:
        for values, code in (
            (self.current.entity_keys, "DUPLICATE_ENTITY_KEY"),
            (self.current.account_keys, "DUPLICATE_ACCOUNT_KEY"),
            (self.current.row_keys, "DUPLICATE_ROW_KEY"),
        ):
            for duplicate in sorted(_duplicate_values(values)):
                self._add(findings, code, "population key is not unique", duplicate)
            for value in values:
                if not _clean_text(value):
                    self._add(findings, "UNSAFE_POPULATION_KEY", "population key is blank or untrimmed", str(value))

    def _compare_prior(self, findings: list[TBPackageFinding]) -> dict[str, int]:
        metrics = {
            "formula_added_count": 0,
            "formula_removed_count": 0,
            "formula_changed_count": 0,
            "entity_added_count": 0,
            "entity_removed_count": 0,
            "account_added_count": 0,
            "account_removed_count": 0,
            "row_added_count": 0,
            "row_removed_count": 0,
        }
        if self.prior is None:
            return metrics
        if self.prior.period != _previous_period(self.current.period):
            self._add(findings, "PRIOR_PERIOD_MISMATCH", "comparator is not the immediately preceding month", self.prior.period)
        current_formulas = {item.formula_id: item.signature for item in self.current.formulas}
        prior_formulas = {item.formula_id: item.signature for item in self.prior.formulas}
        added = set(current_formulas) - set(prior_formulas)
        removed = set(prior_formulas) - set(current_formulas)
        changed = {
            key
            for key in set(current_formulas) & set(prior_formulas)
            if current_formulas[key] != prior_formulas[key]
        }
        comparisons = (
            ("formula", added, removed, changed),
            ("entity", set(self.current.entity_keys) - set(self.prior.entity_keys), set(self.prior.entity_keys) - set(self.current.entity_keys), set()),
            ("account", set(self.current.account_keys) - set(self.prior.account_keys), set(self.prior.account_keys) - set(self.current.account_keys), set()),
            ("row", set(self.current.row_keys) - set(self.prior.row_keys), set(self.prior.row_keys) - set(self.current.row_keys), set()),
        )
        for name, added_values, removed_values, changed_values in comparisons:
            metrics[f"{name}_added_count"] = len(added_values)
            metrics[f"{name}_removed_count"] = len(removed_values)
            if name == "formula":
                metrics["formula_changed_count"] = len(changed_values)
            if added_values or removed_values or changed_values:
                self._add(
                    findings,
                    f"{name.upper()}_POPULATION_CHANGED",
                    "current/prior structural change requires approval",
                    ",".join(sorted(added_values | removed_values | changed_values)),
                    "WARNING",
                )
        return metrics

    def validate(self) -> TBPackageResult:
        findings: list[TBPackageFinding] = []
        self._validate_roles(findings)
        dependencies = self._validate_dependencies(findings)
        self._validate_formulas(findings, dependencies)
        self._validate_controls(findings)
        self._validate_adjustments(findings)
        self._validate_populations(findings)
        comparison = self._compare_prior(findings)
        return TBPackageResult(
            current_period=self.current.period,
            role_count=len(self.current.roles),
            formula_count=len(self.current.formulas),
            external_formula_count=sum(bool(item.external_dependency_id) for item in self.current.formulas),
            dependency_count=len(self.current.dependencies),
            control_count=len(self.current.controls),
            adjustment_count=len(self.current.adjustments),
            findings=tuple(findings),
            **comparison,
        )
