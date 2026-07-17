"""Fictional, validation-only combined-financial-statement controls.

The public component accepts generic structured records expressed in integer
cents.  It demonstrates semantic package completeness, period authority,
formula/cache safety, dependency controls, statement ties, manual-adjustment
gates, and current/prior continuity without encoding a private workbook layout,
company, account map, amount, path, formula, or connector.
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
        "balance_sheet",
        "operations_statement",
        "equity_rollforward",
        "work_in_progress",
        "investments",
        "debt_and_covenants",
        "cash_flow",
        "accounts_receivable",
        "fee_income",
        "project_gains_losses",
        "related_party_matrix",
        "investment_change_bridge",
        "grossed_balance_sheet",
    }
)

APPROVED_DEPENDENCY_ROLES = frozenset(
    {
        "trial_balance",
        "debt_schedule",
        "investment_schedule",
        "operations_package",
        "prior_consolidation",
    }
)

REQUIRED_CONTROL_ROLES = frozenset(
    {
        "balance_sheet",
        "operations_statement",
        "equity_rollforward",
        "cash_flow",
        "accounts_receivable",
        "fee_income",
        "project_gains_losses",
        "related_party_matrix",
        "investment_change_bridge",
        "grossed_balance_sheet",
    }
)


@dataclass(frozen=True)
class StatementRole:
    """One semantic package component and its accounting month."""

    role: str
    period: str


@dataclass(frozen=True)
class FormulaEvidence:
    """Generic formula-result evidence; expressions are fictional signatures."""

    formula_id: str
    role: str
    signature: str
    cached_cents: object = None
    expects_numeric_cache: bool = True
    external_dependency_id: str = ""


@dataclass(frozen=True)
class DependencyEvidence:
    """One approved semantic external-source role."""

    dependency_id: str
    role: str
    period: str
    reference: object


@dataclass(frozen=True)
class ControlEvidence:
    """A rederived package assertion using integer cents."""

    control_id: str
    role: str
    actual_cents: object
    expected_cents: object


@dataclass(frozen=True)
class ManualAdjustment:
    """A judgmental amount that remains human-controlled."""

    adjustment_id: str
    role: str
    amount_cents: object
    support_reference: str = ""
    approval_reference: str = ""


@dataclass(frozen=True)
class ConsolidationSnapshot:
    """One generic monthly consolidation package."""

    period: str
    roles: tuple[StatementRole, ...]
    formulas: tuple[FormulaEvidence, ...]
    dependencies: tuple[DependencyEvidence, ...]
    controls: tuple[ControlEvidence, ...]
    entity_keys: tuple[str, ...] = ()
    project_keys: tuple[str, ...] = ()
    account_keys: tuple[str, ...] = ()
    manual_adjustments: tuple[ManualAdjustment, ...] = ()


@dataclass(frozen=True)
class ConsolidationFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class ConsolidationResult:
    current_period: str
    role_count: int
    formula_count: int
    external_formula_count: int
    dependency_count: int
    control_count: int
    manual_adjustment_count: int
    formula_added_count: int
    formula_removed_count: int
    formula_changed_count: int
    dependency_role_added_count: int
    dependency_role_removed_count: int
    entity_added_count: int
    entity_removed_count: int
    project_added_count: int
    project_removed_count: int
    account_added_count: int
    account_removed_count: int
    findings: tuple[ConsolidationFinding, ...]
    manual_gates: tuple[str, ...] = (
        "refresh and tie every trial balance and supporting schedule",
        "approve the consolidation perimeter, classifications, and eliminations",
        "support and approve every manual adjustment and balancing amount",
        "confirm debt and covenant inputs against lender-controlled sources",
        "resolve every statement, equity, cash-flow, and grossed-balance difference",
        "obtain controller approval for the completed reporting package",
        "generate no journal, import, submission, or posting action from this validator",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)
    posting_actions: tuple[object, ...] = field(default_factory=tuple)
    submissions: tuple[object, ...] = field(default_factory=tuple)

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


class ConsolidationValidator:
    """Validate a fictional current package and optional prior comparator."""

    def __init__(
        self,
        current: ConsolidationSnapshot,
        prior: ConsolidationSnapshot | None = None,
    ) -> None:
        _period_start(current.period, "current.period")
        if prior is not None:
            _period_start(prior.period, "prior.period")
        self.current = current
        self.prior = prior

    @staticmethod
    def _add(
        findings: list[ConsolidationFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(ConsolidationFinding(code, detail, location, severity))

    def _validate_roles(self, findings: list[ConsolidationFinding]) -> None:
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

    def _validate_dependencies(
        self, findings: list[ConsolidationFinding]
    ) -> dict[str, DependencyEvidence]:
        dependencies: dict[str, DependencyEvidence] = {}
        for duplicate in sorted(
            _duplicate_values(item.dependency_id for item in self.current.dependencies)
        ):
            self._add(findings, "DUPLICATE_DEPENDENCY_ID", "dependency id is not unique", duplicate)
        for item in self.current.dependencies:
            if not _clean_text(item.dependency_id):
                self._add(findings, "INVALID_DEPENDENCY_ID", "dependency id must be nonblank and trimmed")
                continue
            dependencies.setdefault(item.dependency_id, item)
            if item.role not in APPROVED_DEPENDENCY_ROLES:
                self._add(findings, "UNKNOWN_DEPENDENCY_ROLE", "dependency role is not approved", item.dependency_id)
            try:
                _period_start(item.period, f"dependency {item.dependency_id} period")
            except ValueError:
                self._add(findings, "INVALID_DEPENDENCY_PERIOD", "dependency period is not canonical", item.dependency_id)
                continue
            expected = (
                _previous_period(self.current.period)
                if item.role == "prior_consolidation"
                else self.current.period
            )
            if item.period != expected:
                self._add(
                    findings,
                    "DEPENDENCY_PERIOD_MISMATCH",
                    f"expected {expected}, observed {item.period}",
                    item.dependency_id,
                )
            reference = str(item.reference or "")
            if not _clean_text(item.reference) or _ERROR_RE.search(reference):
                self._add(findings, "UNSAFE_DEPENDENCY_REFERENCE", "dependency reference is blank, untrimmed, or broken", item.dependency_id)
        return dependencies

    def _validate_formulas(
        self,
        findings: list[ConsolidationFinding],
        dependencies: dict[str, DependencyEvidence],
    ) -> None:
        for duplicate in sorted(_duplicate_values(item.formula_id for item in self.current.formulas)):
            self._add(findings, "DUPLICATE_FORMULA_ID", "formula id is not unique", duplicate)
        for item in self.current.formulas:
            location = item.formula_id
            if not _clean_text(item.formula_id) or not _clean_text(item.signature):
                self._add(findings, "INVALID_FORMULA_EVIDENCE", "formula id and signature must be nonblank and trimmed", location)
            if item.role not in REQUIRED_ROLES:
                self._add(findings, "FORMULA_UNKNOWN_ROLE", "formula points to an unknown semantic role", location)
            if _ERROR_RE.search(str(item.signature)) or _ERROR_RE.search(str(item.cached_cents)):
                self._add(findings, "FORMULA_ERROR_TOKEN", "formula evidence contains a spreadsheet error token", location)
            if item.expects_numeric_cache and not _amount(item.cached_cents):
                self._add(findings, "FORMULA_CACHE_MISSING_OR_UNSAFE", "required cache must be integer cents", location)
            if item.external_dependency_id and item.external_dependency_id not in dependencies:
                self._add(findings, "FORMULA_DEPENDENCY_MISSING", "external formula has no approved dependency record", location)

    def _validate_controls(self, findings: list[ConsolidationFinding]) -> None:
        observed_roles = {item.role for item in self.current.controls}
        for role in sorted(REQUIRED_CONTROL_ROLES - observed_roles):
            self._add(
                findings,
                "MISSING_REQUIRED_CONTROL",
                "required consolidation control is absent",
                role,
            )
        for duplicate in sorted(_duplicate_values(item.control_id for item in self.current.controls)):
            self._add(findings, "DUPLICATE_CONTROL_ID", "control id is not unique", duplicate)
        for item in self.current.controls:
            location = item.control_id
            if not _clean_text(item.control_id):
                self._add(findings, "INVALID_CONTROL_ID", "control id must be nonblank and trimmed", location)
            if item.role not in REQUIRED_ROLES:
                self._add(findings, "CONTROL_UNKNOWN_ROLE", "control points to an unknown semantic role", location)
            if not _amount(item.actual_cents) or not _amount(item.expected_cents):
                self._add(findings, "UNSAFE_CONTROL_AMOUNT", "control values must be integer cents", location)
                continue
            if item.actual_cents != item.expected_cents:
                self._add(
                    findings,
                    "CONTROL_OUT_OF_TIE",
                    f"actual {item.actual_cents} does not equal expected {item.expected_cents} cents",
                    location,
                )

    def _validate_populations(self, findings: list[ConsolidationFinding]) -> None:
        for label, values in (
            ("entity", self.current.entity_keys),
            ("project", self.current.project_keys),
            ("account", self.current.account_keys),
        ):
            for duplicate in sorted(_duplicate_values(values)):
                self._add(
                    findings,
                    f"DUPLICATE_{label.upper()}_KEY",
                    f"{label} key is not unique",
                    duplicate,
                )
            for value in values:
                if not _clean_text(value):
                    self._add(
                        findings,
                        f"INVALID_{label.upper()}_KEY",
                        f"{label} key must be nonblank and trimmed",
                        str(value or ""),
                    )

    def _validate_adjustments(self, findings: list[ConsolidationFinding]) -> None:
        for duplicate in sorted(
            _duplicate_values(item.adjustment_id for item in self.current.manual_adjustments)
        ):
            self._add(findings, "DUPLICATE_ADJUSTMENT_ID", "adjustment id is not unique", duplicate)
        for item in self.current.manual_adjustments:
            location = item.adjustment_id
            if item.role not in REQUIRED_ROLES:
                self._add(findings, "ADJUSTMENT_UNKNOWN_ROLE", "adjustment points to an unknown role", location)
            if not _amount(item.amount_cents):
                self._add(findings, "UNSAFE_ADJUSTMENT_AMOUNT", "adjustment amount must be integer cents", location)
                continue
            if item.amount_cents == 0:
                continue
            if not _clean_text(item.support_reference) or not _clean_text(item.approval_reference):
                self._add(findings, "UNSUPPORTED_MANUAL_ADJUSTMENT", "nonzero adjustment lacks support or approval", location)
            else:
                self._add(
                    findings,
                    "MANUAL_ADJUSTMENT_REQUIRES_REVIEW",
                    "supported nonzero adjustment still requires controller review",
                    location,
                    "REVIEW",
                )

    def _compare_prior(self, findings: list[ConsolidationFinding]) -> dict[str, int]:
        counts = {
            "formula_added_count": 0,
            "formula_removed_count": 0,
            "formula_changed_count": 0,
            "dependency_role_added_count": 0,
            "dependency_role_removed_count": 0,
            "entity_added_count": 0,
            "entity_removed_count": 0,
            "project_added_count": 0,
            "project_removed_count": 0,
            "account_added_count": 0,
            "account_removed_count": 0,
        }
        if self.prior is None:
            return counts
        expected = _previous_period(self.current.period)
        if self.prior.period != expected:
            self._add(findings, "PRIOR_PERIOD_MISMATCH", f"expected {expected}, observed {self.prior.period}", "prior")
        current_formulas = {item.formula_id: item.signature for item in self.current.formulas}
        prior_formulas = {item.formula_id: item.signature for item in self.prior.formulas}
        added = set(current_formulas) - set(prior_formulas)
        removed = set(prior_formulas) - set(current_formulas)
        changed = {
            key
            for key in set(current_formulas) & set(prior_formulas)
            if current_formulas[key] != prior_formulas[key]
        }
        counts["formula_added_count"] = len(added)
        counts["formula_removed_count"] = len(removed)
        counts["formula_changed_count"] = len(changed)
        if added or removed or changed:
            self._add(
                findings,
                "FORMULA_POPULATION_CHANGED",
                f"added {len(added)}, removed {len(removed)}, changed {len(changed)}",
                "current/prior formulas",
                "REVIEW",
            )
        current_dependency_roles = {item.role for item in self.current.dependencies}
        prior_dependency_roles = {item.role for item in self.prior.dependencies}
        dependency_added = current_dependency_roles - prior_dependency_roles
        dependency_removed = prior_dependency_roles - current_dependency_roles
        counts["dependency_role_added_count"] = len(dependency_added)
        counts["dependency_role_removed_count"] = len(dependency_removed)
        if dependency_added or dependency_removed:
            self._add(
                findings,
                "DEPENDENCY_SET_CHANGED",
                f"added {sorted(dependency_added)}, removed {sorted(dependency_removed)}",
                "current/prior dependencies",
                "REVIEW",
            )
        for label, current_values, prior_values in (
            ("entity", set(self.current.entity_keys), set(self.prior.entity_keys)),
            ("project", set(self.current.project_keys), set(self.prior.project_keys)),
            ("account", set(self.current.account_keys), set(self.prior.account_keys)),
        ):
            added_values = current_values - prior_values
            removed_values = prior_values - current_values
            counts[f"{label}_added_count"] = len(added_values)
            counts[f"{label}_removed_count"] = len(removed_values)
            if added_values or removed_values:
                self._add(
                    findings,
                    f"{label.upper()}_POPULATION_CHANGED",
                    f"added {sorted(added_values)}, removed {sorted(removed_values)}",
                    f"current/prior {label}s",
                    "REVIEW",
                )
        return counts

    def validate(self) -> ConsolidationResult:
        findings: list[ConsolidationFinding] = []
        self._validate_roles(findings)
        dependencies = self._validate_dependencies(findings)
        self._validate_formulas(findings, dependencies)
        self._validate_controls(findings)
        self._validate_populations(findings)
        self._validate_adjustments(findings)
        comparison = self._compare_prior(findings)
        return ConsolidationResult(
            current_period=self.current.period,
            role_count=len(self.current.roles),
            formula_count=len(self.current.formulas),
            external_formula_count=sum(
                bool(item.external_dependency_id) for item in self.current.formulas
            ),
            dependency_count=len(self.current.dependencies),
            control_count=len(self.current.controls),
            manual_adjustment_count=len(self.current.manual_adjustments),
            findings=tuple(findings),
            **comparison,
        )
