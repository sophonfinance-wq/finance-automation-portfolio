"""Fictional, read-only construction budget-variance validation.

The validator re-derives cost-code mechanics from generic structured inputs. It
does not read or change a live workbook, approve a change order, update a
forecast, create a journal entry, construct an ERP payload, or post anything.
All amounts are integer cents so the controls are exact and deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_CODE_RE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", re.IGNORECASE)


@dataclass(frozen=True)
class BudgetRow:
    """One fictional cost-code line, expressed entirely in integer cents."""

    cost_code: str
    description: str
    original_budget_cents: object
    approved_changes_cents: object
    current_budget_cents: object
    costs_to_date_cents: object
    current_ctc_cents: object
    period_update_cents: object
    revised_budget_cents: object
    revised_ctc_cents: object
    overrun_flag: str = ""


@dataclass(frozen=True)
class BudgetTotals:
    """Optional displayed project totals independently re-added by the validator."""

    current_budget_cents: object
    costs_to_date_cents: object
    current_ctc_cents: object
    period_update_cents: object
    revised_budget_cents: object
    revised_ctc_cents: object


@dataclass(frozen=True)
class BudgetFinding:
    code: str
    detail: str
    cost_code: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class BudgetVarianceResult:
    target_period: str
    row_count: int
    findings: tuple[BudgetFinding, ...]
    rederived_totals: BudgetTotals | None
    manual_gates: tuple[str, ...] = (
        "refresh and tie the controlled source system for the exact period",
        "obtain project-manager and change-order approval",
        "confirm commitment completeness",
        "update the approved forecast or pro forma",
        "human review and approval",
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
    def posting_authorized(self) -> bool:
        return False


_AMOUNT_FIELDS = (
    "original_budget_cents",
    "approved_changes_cents",
    "current_budget_cents",
    "costs_to_date_cents",
    "current_ctc_cents",
    "period_update_cents",
    "revised_budget_cents",
    "revised_ctc_cents",
)


def _valid_amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class BudgetVarianceValidator:
    """Validate one period without producing posting or source-system work."""

    def __init__(
        self,
        target_period: str,
        rows: Iterable[BudgetRow],
        displayed_totals: BudgetTotals | None = None,
    ) -> None:
        if not isinstance(target_period, str) or not _PERIOD_RE.fullmatch(target_period):
            raise ValueError("target_period must be canonical YYYY-MM")
        self.target_period = target_period
        self.rows = tuple(rows)
        self.displayed_totals = displayed_totals

    def run(self) -> BudgetVarianceResult:
        findings: list[BudgetFinding] = []
        valid_rows: list[BudgetRow] = []
        seen: set[str] = set()

        if not self.rows:
            findings.append(BudgetFinding("BUDGET_EMPTY", "no cost-code rows were provided"))

        for row_number, row in enumerate(self.rows, start=1):
            code = row.cost_code if isinstance(row.cost_code, str) else str(row.cost_code)

            def add(code_name: str, detail: str) -> None:
                findings.append(BudgetFinding(code_name, detail, code))

            if not isinstance(row.cost_code, str) or not _CODE_RE.fullmatch(row.cost_code):
                add("COST_CODE_INVALID", f"row {row_number} cost code is not canonical")
            elif row.cost_code.casefold() in seen:
                add("COST_CODE_DUPLICATE", f"row {row_number} duplicates a prior cost code")
            else:
                seen.add(row.cost_code.casefold())

            if (
                not isinstance(row.description, str)
                or not row.description.strip()
                or row.description != row.description.strip()
            ):
                add("DESCRIPTION_INVALID", f"row {row_number} description must be trimmed and nonblank")

            invalid_fields = [
                name for name in _AMOUNT_FIELDS if not _valid_amount(getattr(row, name))
            ]
            if invalid_fields:
                add(
                    "AMOUNT_INVALID",
                    "integer cents required for " + ", ".join(invalid_fields),
                )
                continue
            valid_rows.append(row)

            expected_current = row.original_budget_cents + row.approved_changes_cents
            if row.current_budget_cents != expected_current:
                add(
                    "CURRENT_BUDGET_OUT_OF_TIE",
                    f"current budget {row.current_budget_cents} != original plus approved changes {expected_current}",
                )
            expected_current_ctc = row.current_budget_cents - row.costs_to_date_cents
            if row.current_ctc_cents != expected_current_ctc:
                add(
                    "CURRENT_CTC_OUT_OF_TIE",
                    f"current CTC {row.current_ctc_cents} != current budget less costs to date {expected_current_ctc}",
                )
            expected_revised = row.current_budget_cents + row.period_update_cents
            if row.revised_budget_cents != expected_revised:
                add(
                    "REVISED_BUDGET_OUT_OF_TIE",
                    f"revised budget {row.revised_budget_cents} != current budget plus period update {expected_revised}",
                )
            expected_revised_ctc = row.revised_budget_cents - row.costs_to_date_cents
            if row.revised_ctc_cents != expected_revised_ctc:
                add(
                    "REVISED_CTC_OUT_OF_TIE",
                    f"revised CTC {row.revised_ctc_cents} != revised budget less costs to date {expected_revised_ctc}",
                )
            if row.revised_ctc_cents < 0:
                add("NEGATIVE_REVISED_CTC", "revised cost to complete is negative")
                if row.overrun_flag.strip().upper() not in {"ERR", "OVERRUN"}:
                    add("OVERRUN_FLAG_MISSING", "negative revised CTC is not visibly flagged")
            elif row.overrun_flag.strip().upper() in {"ERR", "OVERRUN"}:
                add("OVERRUN_FLAG_STALE", "overrun flag is present without a negative revised CTC")

        totals = None
        if valid_rows:
            sums = {
                name: sum(getattr(row, name) for row in valid_rows)
                for name in _AMOUNT_FIELDS
                if name not in {"original_budget_cents", "approved_changes_cents"}
            }
            totals = BudgetTotals(**sums)

        if self.displayed_totals is not None:
            invalid_total_fields = [
                name
                for name in BudgetTotals.__dataclass_fields__
                if not _valid_amount(getattr(self.displayed_totals, name))
            ]
            if invalid_total_fields:
                findings.append(
                    BudgetFinding(
                        "TOTAL_AMOUNT_INVALID",
                        "integer cents required for " + ", ".join(invalid_total_fields),
                    )
                )
            elif totals is None:
                findings.append(
                    BudgetFinding("TOTALS_UNVERIFIABLE", "no valid detail rows support the displayed totals")
                )
            else:
                for name in BudgetTotals.__dataclass_fields__:
                    displayed = getattr(self.displayed_totals, name)
                    expected = getattr(totals, name)
                    if displayed != expected:
                        findings.append(
                            BudgetFinding(
                                "PROJECT_TOTAL_OUT_OF_TIE",
                                f"{name} displayed {displayed} != detail sum {expected}",
                            )
                        )

        return BudgetVarianceResult(
            target_period=self.target_period,
            row_count=len(self.rows),
            findings=tuple(findings),
            rederived_totals=totals,
        )


def demo_rows() -> tuple[BudgetRow, ...]:
    """Return a clean, entirely fictional project example."""

    return (
        BudgetRow("10-100", "Design", 1_000_000, 100_000, 1_100_000, 600_000, 500_000, 50_000, 1_150_000, 550_000),
        BudgetRow("20-200", "Permits", 700_000, 0, 700_000, 250_000, 450_000, -25_000, 675_000, 425_000),
    )
