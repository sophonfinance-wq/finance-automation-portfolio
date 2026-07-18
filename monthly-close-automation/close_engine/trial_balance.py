"""Fictional, validation-only trial-balance continuity controls.

The validator works on generic structured inputs rather than a workbook layout.
It independently re-adds line roll-forwards, entity nets, and current-opening to
prior-close continuity.  It never creates a journal entry, import payload,
posting action, or source-system mutation.  All amounts are integer cents so
every control is deterministic and exact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ACCOUNT_RE = re.compile(r"[A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8}){1,3}", re.IGNORECASE)
_FORMULA_ERROR_RE = re.compile(
    r"#(?:REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!|SPILL!|CALC!)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TrialBalanceRow:
    """One fictional trial-balance line, expressed in integer cents."""

    entity: str
    account: str
    account_title: str
    opening_cents: object
    activity_cents: object
    closing_cents: object
    adjustment_cents: object = 0


@dataclass(frozen=True)
class EntityControl:
    """Optional displayed entity net independently recomputed by the validator."""

    entity: str
    displayed_net_cents: object


@dataclass(frozen=True)
class DependencyEvidence:
    """Generic evidence about one formula or named dependency."""

    label: str
    reference: object
    cached_value: object = None


@dataclass(frozen=True)
class TrialBalanceFinding:
    code: str
    detail: str
    entity: str = ""
    account: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class TrialBalanceResult:
    current_period: str
    prior_period: str
    current_row_count: int
    prior_row_count: int
    common_account_count: int
    added_account_count: int
    removed_account_count: int
    continuity_failure_count: int
    findings: tuple[TrialBalanceFinding, ...]
    manual_gates: tuple[str, ...] = (
        "refresh and tie the controlled source system for the exact period",
        "approve account mappings and population changes",
        "review and approve adjustments",
        "approve consolidation and management-reporting treatment",
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


def _period_start(value: str, field_name: str) -> date:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def _valid_amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


class TrialBalanceContinuityValidator:
    """Validate a fictional current/prior trial-balance pair without posting."""

    def __init__(
        self,
        current_period: str,
        current_rows: Iterable[TrialBalanceRow],
        prior_period: str,
        prior_rows: Iterable[TrialBalanceRow],
        entity_controls: Iterable[EntityControl] = (),
        dependencies: Iterable[DependencyEvidence] = (),
    ) -> None:
        current_start = _period_start(current_period, "current_period")
        prior_start = _period_start(prior_period, "prior_period")
        if prior_start >= current_start:
            raise ValueError("prior_period must precede current_period")
        self.current_period = current_period
        self.prior_period = prior_period
        self.current_rows = tuple(current_rows)
        self.prior_rows = tuple(prior_rows)
        self.entity_controls = tuple(entity_controls)
        self.dependencies = tuple(dependencies)

    @staticmethod
    def _inspect_rows(
        rows: tuple[TrialBalanceRow, ...],
        period_label: str,
        findings: list[TrialBalanceFinding],
    ) -> tuple[dict[tuple[str, str], TrialBalanceRow], dict[str, int]]:
        indexed: dict[tuple[str, str], TrialBalanceRow] = {}
        entity_nets: dict[str, int] = {}

        if not rows:
            findings.append(
                TrialBalanceFinding(
                    f"{period_label}_TRIAL_BALANCE_EMPTY",
                    f"no {period_label.lower()} trial-balance rows were provided",
                )
            )

        for row_number, row in enumerate(rows, start=1):
            entity = row.entity if isinstance(row.entity, str) else str(row.entity)
            account = row.account if isinstance(row.account, str) else str(row.account)

            def add(code: str, detail: str, severity: str = "ERROR") -> None:
                findings.append(
                    TrialBalanceFinding(code, detail, entity, account, severity)
                )

            structure_valid = True
            if not _clean_text(row.entity):
                add(
                    f"{period_label}_ENTITY_INVALID",
                    f"row {row_number} entity must be trimmed and nonblank",
                )
                structure_valid = False
            if not isinstance(row.account, str) or not _ACCOUNT_RE.fullmatch(row.account):
                add(
                    f"{period_label}_ACCOUNT_INVALID",
                    f"row {row_number} account is not canonical",
                )
                structure_valid = False
            if not _clean_text(row.account_title):
                add(
                    f"{period_label}_ACCOUNT_TITLE_INVALID",
                    f"row {row_number} account title must be trimmed and nonblank",
                )
                structure_valid = False

            amount_names = (
                "opening_cents",
                "activity_cents",
                "closing_cents",
                "adjustment_cents",
            )
            invalid_amounts = [
                name for name in amount_names if not _valid_amount(getattr(row, name))
            ]
            if invalid_amounts:
                add(
                    f"{period_label}_AMOUNT_INVALID",
                    "integer cents required for " + ", ".join(invalid_amounts),
                )
                structure_valid = False
            if not structure_valid:
                continue

            key = (row.entity.casefold(), row.account.casefold())
            if key in indexed:
                add(
                    f"{period_label}_ACCOUNT_DUPLICATE",
                    f"row {row_number} duplicates an entity/account key",
                )
                continue
            indexed[key] = row
            entity_nets[row.entity] = entity_nets.get(row.entity, 0) + row.closing_cents

            expected_closing = row.opening_cents + row.activity_cents
            if row.closing_cents != expected_closing:
                add(
                    f"{period_label}_LINE_ROLLFORWARD_OUT_OF_TIE",
                    f"closing {row.closing_cents} != opening plus activity {expected_closing}",
                )
            if row.adjustment_cents:
                add(
                    f"{period_label}_ADJUSTMENT_REVIEW_REQUIRED",
                    f"nonzero adjustment {row.adjustment_cents} requires approval",
                    severity="REVIEW",
                )

        for entity, net in sorted(entity_nets.items(), key=lambda item: item[0].casefold()):
            if net:
                findings.append(
                    TrialBalanceFinding(
                        f"{period_label}_ENTITY_NET_NOT_ZERO",
                        f"entity closing balances net to {net}, not zero",
                        entity=entity,
                    )
                )
        return indexed, entity_nets

    def _inspect_controls(
        self,
        current_entity_nets: dict[str, int],
        findings: list[TrialBalanceFinding],
    ) -> None:
        if not self.entity_controls:
            return
        seen: set[str] = set()
        available = {entity.casefold(): (entity, net) for entity, net in current_entity_nets.items()}
        for position, control in enumerate(self.entity_controls, start=1):
            entity = control.entity if isinstance(control.entity, str) else str(control.entity)
            if not _clean_text(control.entity):
                findings.append(
                    TrialBalanceFinding(
                        "CONTROL_ENTITY_INVALID",
                        f"control {position} entity must be trimmed and nonblank",
                        entity=entity,
                    )
                )
                continue
            key = control.entity.casefold()
            if key in seen:
                findings.append(
                    TrialBalanceFinding(
                        "CONTROL_ENTITY_DUPLICATE",
                        f"control {position} duplicates an entity",
                        entity=control.entity,
                    )
                )
                continue
            seen.add(key)
            if not _valid_amount(control.displayed_net_cents):
                findings.append(
                    TrialBalanceFinding(
                        "CONTROL_AMOUNT_INVALID",
                        "displayed net must use integer cents",
                        entity=control.entity,
                    )
                )
                continue
            if key not in available:
                findings.append(
                    TrialBalanceFinding(
                        "CONTROL_ENTITY_UNKNOWN",
                        "displayed control has no matching current entity",
                        entity=control.entity,
                    )
                )
                continue
            canonical_entity, rederived = available[key]
            if control.displayed_net_cents != rederived:
                findings.append(
                    TrialBalanceFinding(
                        "CONTROL_NET_OUT_OF_TIE",
                        f"displayed net {control.displayed_net_cents} != rederived net {rederived}",
                        entity=canonical_entity,
                    )
                )
        for key, (entity, _) in available.items():
            if key not in seen:
                findings.append(
                    TrialBalanceFinding(
                        "CONTROL_ENTITY_MISSING",
                        "current entity has no displayed control",
                        entity=entity,
                    )
                )

    def _inspect_dependencies(self, findings: list[TrialBalanceFinding]) -> None:
        for position, dependency in enumerate(self.dependencies, start=1):
            label = dependency.label if isinstance(dependency.label, str) else str(dependency.label)
            if not _clean_text(dependency.label):
                findings.append(
                    TrialBalanceFinding(
                        "DEPENDENCY_LABEL_INVALID",
                        f"dependency {position} label must be trimmed and nonblank",
                    )
                )
            if not _clean_text(dependency.reference):
                findings.append(
                    TrialBalanceFinding(
                        "DEPENDENCY_REFERENCE_INVALID",
                        f"dependency {position} reference must be trimmed and nonblank",
                    )
                )
                continue
            reference = dependency.reference
            if "[" in reference or "]" in reference or "#REF!" in reference.upper() or "://" in reference:
                findings.append(
                    TrialBalanceFinding(
                        "DEPENDENCY_EXTERNAL_OR_BROKEN",
                        f"dependency {label!r} is external or broken",
                    )
                )
            if isinstance(dependency.cached_value, str) and _FORMULA_ERROR_RE.search(
                dependency.cached_value
            ):
                findings.append(
                    TrialBalanceFinding(
                        "DEPENDENCY_CACHED_ERROR",
                        f"dependency {label!r} has a cached formula error",
                    )
                )

    def run(self) -> TrialBalanceResult:
        findings: list[TrialBalanceFinding] = []
        current, current_nets = self._inspect_rows(
            self.current_rows, "CURRENT", findings
        )
        prior, _ = self._inspect_rows(self.prior_rows, "PRIOR", findings)
        self._inspect_controls(current_nets, findings)
        self._inspect_dependencies(findings)

        current_keys = set(current)
        prior_keys = set(prior)
        common = current_keys & prior_keys
        added = current_keys - prior_keys
        removed = prior_keys - current_keys
        if added or removed:
            findings.append(
                TrialBalanceFinding(
                    "ACCOUNT_POPULATION_CHANGED",
                    f"{len(added)} account keys added and {len(removed)} removed",
                    severity="REVIEW",
                )
            )

        continuity_failures = 0
        for key in sorted(common):
            current_row = current[key]
            prior_row = prior[key]
            if current_row.opening_cents != prior_row.closing_cents:
                continuity_failures += 1
                findings.append(
                    TrialBalanceFinding(
                        "PRIOR_CLOSE_CURRENT_OPEN_OUT_OF_TIE",
                        f"current opening {current_row.opening_cents} != prior closing {prior_row.closing_cents}",
                        entity=current_row.entity,
                        account=current_row.account,
                    )
                )

        return TrialBalanceResult(
            current_period=self.current_period,
            prior_period=self.prior_period,
            current_row_count=len(self.current_rows),
            prior_row_count=len(self.prior_rows),
            common_account_count=len(common),
            added_account_count=len(added),
            removed_account_count=len(removed),
            continuity_failure_count=continuity_failures,
            findings=tuple(findings),
        )


def demo_pair() -> tuple[tuple[TrialBalanceRow, ...], tuple[TrialBalanceRow, ...]]:
    """Return a clean current/prior pair using fictional names and cents."""

    prior = (
        TrialBalanceRow("Cedar Demo LLC", "AST-100", "Operating cash", 900_000, 100_000, 1_000_000),
        TrialBalanceRow("Cedar Demo LLC", "EQT-900", "Member capital", -900_000, -100_000, -1_000_000),
    )
    current = (
        TrialBalanceRow("Cedar Demo LLC", "AST-100", "Operating cash", 1_000_000, 75_000, 1_075_000),
        TrialBalanceRow("Cedar Demo LLC", "EQT-900", "Member capital", -1_000_000, -75_000, -1_075_000),
    )
    return current, prior


__all__ = [
    "DependencyEvidence",
    "EntityControl",
    "TrialBalanceContinuityValidator",
    "TrialBalanceFinding",
    "TrialBalanceResult",
    "TrialBalanceRow",
    "demo_pair",
]
