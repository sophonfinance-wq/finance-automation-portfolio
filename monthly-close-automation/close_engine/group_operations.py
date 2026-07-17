"""Fictional, validation-only group-operations reporting controls.

The public component accepts generic immutable records expressed in integer
cents. It demonstrates package completeness, formula-cache and dependency
safety, allocation and regional crossfoot controls, a disclosed rounding
boundary, manual-adjustment gates, and current/prior structural continuity.
It contains no private workbook layout, entity, path, formula, or amount.
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
        "executive_summary",
        "regional_summary_a",
        "regional_summary_b",
        "regional_summary_c",
        "regional_summary_d",
        "fee_revenue_detail",
        "project_profit_loss",
        "company_summary",
        "overhead_detail",
        "unit_activity",
        "overhead_allocation",
        "product_mix",
        "admin_region_a",
        "admin_region_b",
        "admin_region_c",
        "admin_region_d",
    }
)

REQUIRED_DEPENDENCY_ROLES = frozenset(
    {"trial_balance_package", "consolidation_package", "investment_schedule"}
)
OPTIONAL_DEPENDENCY_ROLES = frozenset({"business_plan"})
APPROVED_DEPENDENCY_ROLES = REQUIRED_DEPENDENCY_ROLES | OPTIONAL_DEPENDENCY_ROLES

CONTROL_TOLERANCES_CENTS = {
    "allocation_company": 2,
    "allocation_region_a": 2,
    "allocation_region_b": 2,
    "allocation_region_c": 2,
    "allocation_region_d": 2,
    "regional_crossfoot_a": 2,
    "regional_crossfoot_b": 2,
    "regional_crossfoot_c": 2,
    "regional_crossfoot_d": 2,
    "summary_rounding_boundary": 100,
}


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
    contains_embedded_amount: bool = False


@dataclass(frozen=True)
class DependencyEvidence:
    dependency_id: str
    role: str
    period: str
    reference: object


@dataclass(frozen=True)
class ControlEvidence:
    control_id: str
    difference_cents: object


@dataclass(frozen=True)
class ManualAdjustmentEvidence:
    adjustment_id: str
    role: str
    amount_cents: object
    support_reference: str = ""
    approval_reference: str = ""


@dataclass(frozen=True)
class GroupOperationsSnapshot:
    period: str
    roles: tuple[PackageRole, ...]
    formulas: tuple[FormulaEvidence, ...]
    dependencies: tuple[DependencyEvidence, ...]
    controls: tuple[ControlEvidence, ...]
    label_keys: tuple[str, ...] = ()
    manual_adjustments: tuple[ManualAdjustmentEvidence, ...] = ()


@dataclass(frozen=True)
class GroupOperationsFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class GroupOperationsResult:
    current_period: str
    role_count: int
    formula_count: int
    external_formula_count: int
    embedded_amount_formula_count: int
    dependency_count: int
    control_count: int
    manual_adjustment_count: int
    formula_added_count: int
    formula_removed_count: int
    formula_changed_count: int
    dependency_added_count: int
    dependency_removed_count: int
    label_added_count: int
    label_removed_count: int
    findings: tuple[GroupOperationsFinding, ...]
    manual_gates: tuple[str, ...] = (
        "refresh and tie the approved trial-balance, consolidation, and investment sources",
        "approve the reporting perimeter, classifications, and regional mappings",
        "support and approve every embedded amount and manual adjustment",
        "resolve every allocation, regional crossfoot, and rounding exception",
        "approve current/prior formula, dependency, and label changes",
        "obtain controller approval for the completed management package",
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


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


class GroupOperationsValidator:
    """Validate a fictional monthly management package and prior comparator."""

    def __init__(
        self,
        current: GroupOperationsSnapshot,
        prior: GroupOperationsSnapshot | None = None,
    ) -> None:
        _period_start(current.period, "current.period")
        if prior is not None:
            _period_start(prior.period, "prior.period")
        self.current = current
        self.prior = prior

    @staticmethod
    def _add(
        findings: list[GroupOperationsFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(GroupOperationsFinding(code, detail, location, severity))

    def _validate_roles(self, findings: list[GroupOperationsFinding]) -> None:
        roles = [item.role for item in self.current.roles]
        for duplicate in sorted(_duplicates(roles)):
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
            else:
                if item.period != self.current.period:
                    self._add(findings, "ROLE_PERIOD_MISMATCH", "role period does not equal package period", item.role)

    def _validate_dependencies(
        self,
        findings: list[GroupOperationsFinding],
    ) -> dict[str, DependencyEvidence]:
        dependencies: dict[str, DependencyEvidence] = {}
        for duplicate in sorted(_duplicates(item.dependency_id for item in self.current.dependencies)):
            self._add(findings, "DUPLICATE_DEPENDENCY_ID", "dependency id is not unique", duplicate)
        by_role: dict[str, int] = {}
        for item in self.current.dependencies:
            dependencies.setdefault(item.dependency_id, item)
            by_role[item.role] = by_role.get(item.role, 0) + 1
            if item.role not in APPROVED_DEPENDENCY_ROLES:
                self._add(findings, "UNKNOWN_DEPENDENCY_ROLE", "dependency role is not approved", item.dependency_id)
            try:
                _period_start(item.period, f"dependency {item.dependency_id} period")
            except ValueError:
                self._add(findings, "INVALID_DEPENDENCY_PERIOD", "dependency period is not canonical YYYY-MM", item.dependency_id)
            else:
                if item.period != self.current.period:
                    self._add(findings, "DEPENDENCY_PERIOD_MISMATCH", "dependency is not current-period", item.dependency_id)
            if not _clean_text(item.reference) or _ERROR_RE.search(str(item.reference)):
                self._add(findings, "UNSAFE_DEPENDENCY_REFERENCE", "dependency reference is blank, untrimmed, or broken", item.dependency_id)
        for role in sorted(REQUIRED_DEPENDENCY_ROLES):
            if by_role.get(role, 0) != 1:
                self._add(findings, "REQUIRED_DEPENDENCY_COUNT", "exactly one current dependency is required", role)
        for role in sorted(OPTIONAL_DEPENDENCY_ROLES):
            if by_role.get(role, 0) > 1:
                self._add(findings, "OPTIONAL_DEPENDENCY_COUNT", "optional dependency may appear at most once", role)
        return dependencies

    def _validate_formulas(
        self,
        findings: list[GroupOperationsFinding],
        dependencies: dict[str, DependencyEvidence],
    ) -> None:
        for duplicate in sorted(_duplicates(item.formula_id for item in self.current.formulas)):
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
            if item.contains_embedded_amount:
                self._add(
                    findings,
                    "EMBEDDED_AMOUNT_REQUIRES_REVIEW",
                    "embedded formula amount remains a controller judgment",
                    item.formula_id,
                    "WARNING",
                )

    def _validate_controls(self, findings: list[GroupOperationsFinding]) -> None:
        ids = [item.control_id for item in self.current.controls]
        for duplicate in sorted(_duplicates(ids)):
            self._add(findings, "DUPLICATE_CONTROL_ID", "control id is not unique", duplicate)
        observed = set(ids)
        for control_id in sorted(set(CONTROL_TOLERANCES_CENTS) - observed):
            self._add(findings, "MISSING_REQUIRED_CONTROL", "required package control is absent", control_id)
        for item in self.current.controls:
            if item.control_id not in CONTROL_TOLERANCES_CENTS:
                self._add(findings, "UNKNOWN_CONTROL", "control id is not approved", item.control_id)
                continue
            if not _amount(item.difference_cents):
                self._add(findings, "UNSAFE_CONTROL_AMOUNT", "control difference must be integer cents", item.control_id)
                continue
            tolerance = CONTROL_TOLERANCES_CENTS[item.control_id]
            if abs(item.difference_cents) > tolerance:
                self._add(
                    findings,
                    "CONTROL_OUT_OF_TOLERANCE",
                    f"absolute difference exceeds disclosed {tolerance}-cent tolerance",
                    item.control_id,
                )

    def _validate_manual_items(self, findings: list[GroupOperationsFinding]) -> None:
        for duplicate in sorted(_duplicates(item.adjustment_id for item in self.current.manual_adjustments)):
            self._add(findings, "DUPLICATE_ADJUSTMENT_ID", "manual adjustment id is not unique", duplicate)
        for item in self.current.manual_adjustments:
            if item.role not in REQUIRED_ROLES:
                self._add(findings, "UNKNOWN_ADJUSTMENT_ROLE", "manual adjustment role is not approved", item.adjustment_id)
            if not _amount(item.amount_cents):
                self._add(findings, "UNSAFE_ADJUSTMENT_AMOUNT", "manual adjustment must be integer cents", item.adjustment_id)
            elif item.amount_cents and (
                not _clean_text(item.support_reference) or not _clean_text(item.approval_reference)
            ):
                self._add(findings, "UNSUPPORTED_MANUAL_ADJUSTMENT", "manual adjustment requires support and approval", item.adjustment_id)
            elif item.amount_cents:
                self._add(
                    findings,
                    "MANUAL_ADJUSTMENT_REQUIRES_REVIEW",
                    "supported adjustment remains a controller judgment",
                    item.adjustment_id,
                    "WARNING",
                )

    def _validate_labels(self, findings: list[GroupOperationsFinding]) -> None:
        for duplicate in sorted(_duplicates(self.current.label_keys)):
            self._add(findings, "DUPLICATE_LABEL_KEY", "label key is not unique", duplicate)
        for label in self.current.label_keys:
            if not _clean_text(label):
                self._add(findings, "UNSAFE_LABEL_KEY", "label key is blank or untrimmed", str(label))

    def _compare_prior(self, findings: list[GroupOperationsFinding]) -> dict[str, int]:
        metrics = {
            "formula_added_count": 0,
            "formula_removed_count": 0,
            "formula_changed_count": 0,
            "dependency_added_count": 0,
            "dependency_removed_count": 0,
            "label_added_count": 0,
            "label_removed_count": 0,
        }
        if self.prior is None:
            return metrics
        if self.prior.period != _previous_period(self.current.period):
            self._add(findings, "PRIOR_PERIOD_MISMATCH", "comparator is not the immediately preceding month", self.prior.period)
        current_formulas = {item.formula_id: item.signature for item in self.current.formulas}
        prior_formulas = {item.formula_id: item.signature for item in self.prior.formulas}
        formula_added = set(current_formulas) - set(prior_formulas)
        formula_removed = set(prior_formulas) - set(current_formulas)
        formula_changed = {
            key for key in set(current_formulas) & set(prior_formulas)
            if current_formulas[key] != prior_formulas[key]
        }
        current_dependencies = {item.role for item in self.current.dependencies}
        prior_dependencies = {item.role for item in self.prior.dependencies}
        comparisons = (
            ("formula", formula_added, formula_removed, formula_changed),
            ("dependency", current_dependencies - prior_dependencies, prior_dependencies - current_dependencies, set()),
            ("label", set(self.current.label_keys) - set(self.prior.label_keys), set(self.prior.label_keys) - set(self.current.label_keys), set()),
        )
        for name, added, removed, changed in comparisons:
            metrics[f"{name}_added_count"] = len(added)
            metrics[f"{name}_removed_count"] = len(removed)
            if name == "formula":
                metrics["formula_changed_count"] = len(changed)
            if added or removed or changed:
                self._add(
                    findings,
                    f"{name.upper()}_POPULATION_CHANGED",
                    "current/prior structural change requires approval",
                    ",".join(sorted(added | removed | changed)),
                    "WARNING",
                )
        return metrics

    def validate(self) -> GroupOperationsResult:
        findings: list[GroupOperationsFinding] = []
        self._validate_roles(findings)
        dependencies = self._validate_dependencies(findings)
        self._validate_formulas(findings, dependencies)
        self._validate_controls(findings)
        self._validate_manual_items(findings)
        self._validate_labels(findings)
        comparison = self._compare_prior(findings)
        return GroupOperationsResult(
            current_period=self.current.period,
            role_count=len(self.current.roles),
            formula_count=len(self.current.formulas),
            external_formula_count=sum(bool(item.external_dependency_id) for item in self.current.formulas),
            embedded_amount_formula_count=sum(item.contains_embedded_amount for item in self.current.formulas),
            dependency_count=len(self.current.dependencies),
            control_count=len(self.current.controls),
            manual_adjustment_count=len(self.current.manual_adjustments),
            findings=tuple(findings),
            **comparison,
        )
