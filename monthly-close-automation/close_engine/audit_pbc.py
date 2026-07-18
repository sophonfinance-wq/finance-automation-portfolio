"""Fictional, validation-only audit/PBC package controls.

The public component accepts generic structured records rather than workbook
paths or company layouts.  It independently re-adds leadsheet equations,
continuity schedules, current/prior carryforwards, displayed checks, and
dependency evidence.  All money is integer cents.  It cannot create a journal
entry, import payload, posting action, or audit conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Iterable


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ACCOUNT_RE = re.compile(r"[A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8}){1,3}", re.IGNORECASE)
_FORMULA_ERROR_RE = re.compile(
    r"#(?:REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!|SPILL!|CALC!)",
    re.IGNORECASE,
)

REQUIRED_ROLES = frozenset(
    {
        "master_trial_balance",
        "cash_leadsheet",
        "receivables_leadsheet",
        "intercompany_leadsheet",
        "prepaids_leadsheet",
        "investments_leadsheet",
        "payables_leadsheet",
        "equity_leadsheet",
        "interest_leadsheet",
        "other_income_leadsheet",
        "general_admin_leadsheet",
        "cash_flow_proof",
    }
)


@dataclass(frozen=True)
class PackageRole:
    """One semantic sheet role, independent of a workbook tab name."""

    role: str
    label: str


@dataclass(frozen=True)
class LeadLine:
    """One generic PBC leadsheet row, expressed in integer cents."""

    schedule: str
    account: str
    description: str
    trial_balance_cents: object
    adjustment_cents: object
    final_cents: object
    prior_cents: object
    change_cents: object


@dataclass(frozen=True)
class ContinuityLine:
    """One opening-plus-movements-equals-ending control."""

    schedule: str
    line_id: str
    opening_cents: object
    movement_cents: object
    ending_cents: object


@dataclass(frozen=True)
class DisplayedCheck:
    """A displayed package control that must equal zero."""

    schedule: str
    label: str
    amount_cents: object


@dataclass(frozen=True)
class DependencyEvidence:
    """Generic formula/dependency evidence with an authoritative-range flag."""

    schedule: str
    label: str
    reference: object
    cached_value: object = None
    authoritative: object = True


@dataclass(frozen=True)
class AuditPbcFinding:
    code: str
    detail: str
    schedule: str = ""
    line_id: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class AuditPbcResult:
    current_period: str
    prior_period: str
    current_line_count: int
    prior_line_count: int
    shared_line_count: int
    added_line_count: int
    removed_line_count: int
    continuity_failure_count: int
    displayed_check_failure_count: int
    findings: tuple[AuditPbcFinding, ...]
    manual_gates: tuple[str, ...] = (
        "tie balances to the controlled audit trial balance and source support",
        "approve adjustments, classifications, estimates, and disclosures",
        "complete auditor request tracking and evidence delivery",
        "human review and accounting-owner approval",
        "manual posting and post-entry general-ledger tie-out",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    posting_actions: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)

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


def _period_start(value: str, field_name: str) -> date:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def _clean(value: object) -> bool:
    return isinstance(value, str) and value == value.strip() and bool(value)


def _amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class AuditPbcValidator:
    """Validate a fictional current/prior PBC package without posting."""

    def __init__(
        self,
        current_period: str,
        prior_period: str,
        roles: Iterable[PackageRole],
        current_lines: Iterable[LeadLine],
        prior_lines: Iterable[LeadLine],
        continuity_lines: Iterable[ContinuityLine] = (),
        displayed_checks: Iterable[DisplayedCheck] = (),
        dependencies: Iterable[DependencyEvidence] = (),
    ) -> None:
        current_start = _period_start(current_period, "current_period")
        prior_start = _period_start(prior_period, "prior_period")
        if prior_start >= current_start:
            raise ValueError("prior_period must precede current_period")
        self.current_period = current_period
        self.prior_period = prior_period
        self.roles = tuple(roles)
        self.current_lines = tuple(current_lines)
        self.prior_lines = tuple(prior_lines)
        self.continuity_lines = tuple(continuity_lines)
        self.displayed_checks = tuple(displayed_checks)
        self.dependencies = tuple(dependencies)

    def _inspect_roles(self, findings: list[AuditPbcFinding]) -> None:
        seen: dict[str, int] = {}
        for position, item in enumerate(self.roles, start=1):
            if not isinstance(item.role, str) or item.role not in REQUIRED_ROLES:
                findings.append(
                    AuditPbcFinding(
                        "ROLE_INVALID",
                        f"role {position} is not a supported semantic package role",
                    )
                )
                continue
            if not _clean(item.label):
                findings.append(
                    AuditPbcFinding(
                        "ROLE_LABEL_INVALID",
                        f"role {position} label must be trimmed and nonblank",
                    )
                )
            seen[item.role] = seen.get(item.role, 0) + 1
        missing = sorted(REQUIRED_ROLES - set(seen))
        duplicates = sorted(role for role, count in seen.items() if count > 1)
        if missing:
            findings.append(
                AuditPbcFinding(
                    "REQUIRED_ROLE_MISSING",
                    "missing roles: " + ", ".join(missing),
                )
            )
        if duplicates:
            findings.append(
                AuditPbcFinding(
                    "ROLE_DUPLICATE",
                    "duplicate roles: " + ", ".join(duplicates),
                )
            )

    @staticmethod
    def _inspect_lines(
        lines: tuple[LeadLine, ...],
        period_label: str,
        findings: list[AuditPbcFinding],
    ) -> dict[tuple[str, str], LeadLine]:
        indexed: dict[tuple[str, str], LeadLine] = {}
        if not lines:
            findings.append(
                AuditPbcFinding(
                    f"{period_label}_LEADSHEET_EMPTY",
                    f"no {period_label.lower()} leadsheet lines were provided",
                )
            )
        for position, line in enumerate(lines, start=1):
            schedule = line.schedule if isinstance(line.schedule, str) else str(line.schedule)
            account = line.account if isinstance(line.account, str) else str(line.account)
            structure_valid = True

            def add(code: str, detail: str, severity: str = "ERROR") -> None:
                findings.append(
                    AuditPbcFinding(code, detail, schedule, account, severity)
                )

            if not _clean(line.schedule):
                add(
                    f"{period_label}_SCHEDULE_INVALID",
                    f"line {position} schedule must be trimmed and nonblank",
                )
                structure_valid = False
            if not isinstance(line.account, str) or not _ACCOUNT_RE.fullmatch(line.account):
                add(
                    f"{period_label}_ACCOUNT_INVALID",
                    f"line {position} account is not canonical",
                )
                structure_valid = False
            if not _clean(line.description):
                add(
                    f"{period_label}_DESCRIPTION_INVALID",
                    f"line {position} description must be trimmed and nonblank",
                )
                structure_valid = False
            fields = (
                "trial_balance_cents",
                "adjustment_cents",
                "final_cents",
                "prior_cents",
                "change_cents",
            )
            invalid = [name for name in fields if not _amount(getattr(line, name))]
            if invalid:
                add(
                    f"{period_label}_AMOUNT_INVALID",
                    "integer cents required for " + ", ".join(invalid),
                )
                structure_valid = False
            if not structure_valid:
                continue

            key = (line.schedule.casefold(), line.account.casefold())
            if key in indexed:
                add(
                    f"{period_label}_LINE_DUPLICATE",
                    f"line {position} duplicates a schedule/account key",
                )
                continue
            indexed[key] = line

            expected_final = line.trial_balance_cents + line.adjustment_cents
            if line.final_cents != expected_final:
                add(
                    f"{period_label}_FINAL_EQUATION_OUT_OF_TIE",
                    f"final {line.final_cents} != trial balance plus adjustment {expected_final}",
                )
            expected_change = line.final_cents - line.prior_cents
            if line.change_cents != expected_change:
                add(
                    f"{period_label}_CHANGE_EQUATION_OUT_OF_TIE",
                    f"change {line.change_cents} != final less prior {expected_change}",
                )
            if line.adjustment_cents:
                add(
                    f"{period_label}_ADJUSTMENT_REVIEW_REQUIRED",
                    f"nonzero adjustment {line.adjustment_cents} requires support and approval",
                    severity="REVIEW",
                )
        return indexed

    def _inspect_continuity(self, findings: list[AuditPbcFinding]) -> int:
        failures = 0
        seen: set[tuple[str, str]] = set()
        for position, line in enumerate(self.continuity_lines, start=1):
            schedule = line.schedule if isinstance(line.schedule, str) else str(line.schedule)
            line_id = line.line_id if isinstance(line.line_id, str) else str(line.line_id)
            if not _clean(line.schedule) or not _clean(line.line_id):
                findings.append(
                    AuditPbcFinding(
                        "CONTINUITY_IDENTIFIER_INVALID",
                        f"continuity line {position} requires clean schedule and line identifiers",
                        schedule,
                        line_id,
                    )
                )
                continue
            key = (line.schedule.casefold(), line.line_id.casefold())
            if key in seen:
                findings.append(
                    AuditPbcFinding(
                        "CONTINUITY_LINE_DUPLICATE",
                        f"continuity line {position} duplicates a key",
                        line.schedule,
                        line.line_id,
                    )
                )
                continue
            seen.add(key)
            if not _amount(line.opening_cents) or not _amount(line.ending_cents):
                findings.append(
                    AuditPbcFinding(
                        "CONTINUITY_AMOUNT_INVALID",
                        "opening and ending balances must use integer cents",
                        line.schedule,
                        line.line_id,
                    )
                )
                continue
            if not isinstance(line.movement_cents, tuple) or any(
                not _amount(value) for value in line.movement_cents
            ):
                findings.append(
                    AuditPbcFinding(
                        "CONTINUITY_MOVEMENTS_INVALID",
                        "movements must be a tuple of integer cents",
                        line.schedule,
                        line.line_id,
                    )
                )
                continue
            expected = line.opening_cents + sum(line.movement_cents)
            if line.ending_cents != expected:
                failures += 1
                findings.append(
                    AuditPbcFinding(
                        "CONTINUITY_OUT_OF_TIE",
                        f"ending {line.ending_cents} != opening plus movements {expected}",
                        line.schedule,
                        line.line_id,
                    )
                )
        return failures

    def _inspect_checks(self, findings: list[AuditPbcFinding]) -> int:
        failures = 0
        seen: set[tuple[str, str]] = set()
        for position, check in enumerate(self.displayed_checks, start=1):
            schedule = check.schedule if isinstance(check.schedule, str) else str(check.schedule)
            label = check.label if isinstance(check.label, str) else str(check.label)
            if not _clean(check.schedule) or not _clean(check.label):
                findings.append(
                    AuditPbcFinding(
                        "DISPLAYED_CHECK_IDENTIFIER_INVALID",
                        f"check {position} requires clean schedule and label values",
                        schedule,
                        label,
                    )
                )
                continue
            key = (check.schedule.casefold(), check.label.casefold())
            if key in seen:
                findings.append(
                    AuditPbcFinding(
                        "DISPLAYED_CHECK_DUPLICATE",
                        f"check {position} duplicates a schedule/label key",
                        check.schedule,
                        check.label,
                    )
                )
                continue
            seen.add(key)
            if not _amount(check.amount_cents):
                findings.append(
                    AuditPbcFinding(
                        "DISPLAYED_CHECK_AMOUNT_INVALID",
                        "displayed check must use integer cents",
                        check.schedule,
                        check.label,
                    )
                )
                continue
            if check.amount_cents:
                failures += 1
                findings.append(
                    AuditPbcFinding(
                        "DISPLAYED_CHECK_FAILED",
                        f"displayed control is {check.amount_cents}, not zero",
                        check.schedule,
                        check.label,
                    )
                )
        return failures

    def _inspect_dependencies(self, findings: list[AuditPbcFinding]) -> None:
        for position, item in enumerate(self.dependencies, start=1):
            schedule = item.schedule if isinstance(item.schedule, str) else str(item.schedule)
            label = item.label if isinstance(item.label, str) else str(item.label)
            if not _clean(item.schedule) or not _clean(item.label):
                findings.append(
                    AuditPbcFinding(
                        "DEPENDENCY_IDENTIFIER_INVALID",
                        f"dependency {position} requires clean schedule and label values",
                        schedule,
                        label,
                    )
                )
            if not isinstance(item.authoritative, bool):
                findings.append(
                    AuditPbcFinding(
                        "DEPENDENCY_SCOPE_INVALID",
                        "authoritative must be a boolean",
                        schedule,
                        label,
                    )
                )
                continue
            if not _clean(item.reference):
                findings.append(
                    AuditPbcFinding(
                        "DEPENDENCY_REFERENCE_INVALID",
                        f"dependency {position} reference must be trimmed and nonblank",
                        schedule,
                        label,
                    )
                )
                continue
            reference = item.reference
            broken = (
                "[" in reference
                or "]" in reference
                or "#REF!" in reference.upper()
                or "_xlfn." in reference.casefold()
                or "://" in reference
            )
            cached_error = isinstance(item.cached_value, str) and bool(
                _FORMULA_ERROR_RE.search(item.cached_value)
            )
            severity = "ERROR" if item.authoritative else "REVIEW"
            if broken:
                findings.append(
                    AuditPbcFinding(
                        "DEPENDENCY_EXTERNAL_OR_BROKEN"
                        if item.authoritative
                        else "STALE_DEPENDENCY_EXTERNAL_OR_BROKEN",
                        "external, unsupported, or broken dependency",
                        item.schedule,
                        item.label,
                        severity,
                    )
                )
            if cached_error:
                findings.append(
                    AuditPbcFinding(
                        "DEPENDENCY_CACHED_ERROR"
                        if item.authoritative
                        else "STALE_DEPENDENCY_CACHED_ERROR",
                        f"cached dependency value is {item.cached_value}",
                        item.schedule,
                        item.label,
                        severity,
                    )
                )

    def run(self) -> AuditPbcResult:
        findings: list[AuditPbcFinding] = []
        self._inspect_roles(findings)
        current = self._inspect_lines(self.current_lines, "CURRENT", findings)
        prior = self._inspect_lines(self.prior_lines, "PRIOR", findings)

        shared = set(current) & set(prior)
        added = set(current) - set(prior)
        removed = set(prior) - set(current)
        pair_failures = 0
        for key in sorted(shared):
            current_line = current[key]
            prior_line = prior[key]
            if current_line.prior_cents != prior_line.final_cents:
                pair_failures += 1
                findings.append(
                    AuditPbcFinding(
                        "PRIOR_FINAL_CURRENT_PRIOR_OUT_OF_TIE",
                        f"current prior {current_line.prior_cents} != prior final {prior_line.final_cents}",
                        current_line.schedule,
                        current_line.account,
                    )
                )
        if added or removed:
            findings.append(
                AuditPbcFinding(
                    "ACCOUNT_POPULATION_CHANGED",
                    f"{len(added)} schedule/account keys added and {len(removed)} removed",
                    severity="REVIEW",
                )
            )

        continuity_failures = self._inspect_continuity(findings) + pair_failures
        check_failures = self._inspect_checks(findings)
        self._inspect_dependencies(findings)

        findings.sort(
            key=lambda item: (
                0 if item.severity == "ERROR" else 1,
                item.code,
                item.schedule.casefold(),
                item.line_id.casefold(),
                item.detail,
            )
        )
        return AuditPbcResult(
            current_period=self.current_period,
            prior_period=self.prior_period,
            current_line_count=len(self.current_lines),
            prior_line_count=len(self.prior_lines),
            shared_line_count=len(shared),
            added_line_count=len(added),
            removed_line_count=len(removed),
            continuity_failure_count=continuity_failures,
            displayed_check_failure_count=check_failures,
            findings=tuple(findings),
        )


def demo_package() -> tuple[
    tuple[PackageRole, ...],
    tuple[LeadLine, ...],
    tuple[LeadLine, ...],
    tuple[ContinuityLine, ...],
    tuple[DisplayedCheck, ...],
]:
    """Return a small, balanced, entirely fictional package."""

    roles = tuple(
        PackageRole(role, role.replace("_", " ").title())
        for role in sorted(REQUIRED_ROLES)
    )
    current = (
        LeadLine("Cash Leadsheet", "AST-100", "Operating cash", 1_250_000, 0, 1_250_000, 1_100_000, 150_000),
        LeadLine("Payables Leadsheet", "LIA-200", "Trade payables", -420_000, 0, -420_000, -390_000, -30_000),
    )
    prior = (
        LeadLine("Cash Leadsheet", "AST-100", "Operating cash", 1_100_000, 0, 1_100_000, 1_000_000, 100_000),
        LeadLine("Payables Leadsheet", "LIA-200", "Trade payables", -390_000, 0, -390_000, -350_000, -40_000),
    )
    continuity = (
        ContinuityLine("Debt Continuity", "Demo Facility", 500_000, (100_000, -75_000), 525_000),
    )
    checks = (DisplayedCheck("Cash Flow Proof", "Final Proof", 0),)
    return roles, current, prior, continuity, checks


__all__ = [
    "AuditPbcFinding",
    "AuditPbcResult",
    "AuditPbcValidator",
    "ContinuityLine",
    "DependencyEvidence",
    "DisplayedCheck",
    "LeadLine",
    "PackageRole",
    "REQUIRED_ROLES",
    "demo_package",
]
