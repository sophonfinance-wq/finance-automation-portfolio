"""Fictional, validation-only job-cost-to-construction-draw controls.

The public component accepts generic structured records rather than workbook
paths or private layouts. It independently re-adds transaction draw amounts,
detail and category totals, lender-funding continuity, job-cost equations, and
same-period revisions. All money is integer cents. It cannot create a journal
entry, lender submission, import payload, posting action, or source mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Iterable


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_DATE_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])")
_CODE_RE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", re.IGNORECASE)
_FORMULA_ERROR_RE = re.compile(
    r"#(?:REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!|SPILL!|CALC!)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DrawTransaction:
    """One fictional job-cost line expressed in integer cents."""

    transaction_id: str
    detail_id: str
    job: str
    cost_code: str
    bank_category: str
    transaction_type: str
    transaction_date: str
    accounting_date: str
    vendor: str
    invoice: str
    description: str
    amount_cents: object
    retainage_cents: object
    adjustment_cents: object
    draw_cents: object


@dataclass(frozen=True)
class DetailTotal:
    """Displayed detail-sheet total independently re-added from transactions."""

    detail_id: str
    displayed_cents: object


@dataclass(frozen=True)
class CategoryTotal:
    """Displayed latest-draw category total."""

    bank_category: str
    displayed_cents: object


@dataclass(frozen=True)
class DrawSnapshot:
    """One generic reconciliation total row for a lender draw."""

    period: str
    draw_number: object
    current_draw_cents: object
    interest_to_date_cents: object
    cumulative_lender_draws_cents: object
    total_equity_cents: object
    total_loan_equity_cents: object
    total_debt_equity_cents: object
    job_cost_to_date_cents: object
    net_zero_adjustments_cents: object
    less_retention_cents: object
    net_job_cost_to_date_cents: object
    variance_cents: object
    project_report_total_cents: object


@dataclass(frozen=True)
class DependencyEvidence:
    """Generic formula or mapping dependency evidence."""

    label: str
    reference: object
    cached_value: object = None


@dataclass(frozen=True)
class CashDrawFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class CashDrawResult:
    current_period: str
    transaction_count: int
    detail_count: int
    category_count: int
    combined_detail_cents: int
    current_draw_cents: int | None
    period_interest_cents: int | None
    period_lender_funding_cents: int | None
    revision_draw_delta_cents: int | None
    findings: tuple[CashDrawFinding, ...]
    manual_gates: tuple[str, ...] = (
        "refresh and tie job-cost, commitment, and invoice-detail source reports",
        "confirm the lender statement, cash funding, and interest",
        "approve job, cost-code, bank-category, and classification mappings",
        "approve adjustments, retainage, and retention releases",
        "resolve project-report and reconciliation differences",
        "obtain controller and lender package sign-off",
        "submit nothing and post nothing from this validator",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    lender_submissions: tuple[object, ...] = field(default_factory=tuple)
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


_SNAPSHOT_AMOUNT_FIELDS = (
    "current_draw_cents",
    "interest_to_date_cents",
    "cumulative_lender_draws_cents",
    "total_equity_cents",
    "total_loan_equity_cents",
    "total_debt_equity_cents",
    "job_cost_to_date_cents",
    "net_zero_adjustments_cents",
    "less_retention_cents",
    "net_job_cost_to_date_cents",
    "variance_cents",
    "project_report_total_cents",
)


def _period_start(value: str, field_name: str) -> date:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def _previous_period(value: str) -> str:
    start = _period_start(value, "current_period")
    if start.month == 1:
        return f"{start.year - 1:04d}-12"
    return f"{start.year:04d}-{start.month - 1:02d}"


def _clean(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _date_value(value: object) -> date | None:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class CashDrawValidator:
    """Validate a fictional current draw, optional prior month, and revision."""

    def __init__(
        self,
        current_period: str,
        transactions: Iterable[DrawTransaction],
        detail_totals: Iterable[DetailTotal],
        category_totals: Iterable[CategoryTotal],
        current_snapshot: DrawSnapshot,
        prior_snapshot: DrawSnapshot | None = None,
        dependencies: Iterable[DependencyEvidence] = (),
        original_snapshot: DrawSnapshot | None = None,
        original_transactions: Iterable[DrawTransaction] = (),
    ) -> None:
        _period_start(current_period, "current_period")
        self.current_period = current_period
        self.transactions = tuple(transactions)
        self.detail_totals = tuple(detail_totals)
        self.category_totals = tuple(category_totals)
        self.current_snapshot = current_snapshot
        self.prior_snapshot = prior_snapshot
        self.dependencies = tuple(dependencies)
        self.original_snapshot = original_snapshot
        self.original_transactions = tuple(original_transactions)

    @staticmethod
    def _add(
        findings: list[CashDrawFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(CashDrawFinding(code, detail, location, severity))

    def _inspect_transactions(
        self,
        transactions: tuple[DrawTransaction, ...],
        findings: list[CashDrawFinding],
        *,
        prefix: str = "",
        enforce_current_period: bool = True,
    ) -> tuple[list[DrawTransaction], dict[str, int], dict[str, int]]:
        valid: list[DrawTransaction] = []
        details: dict[str, int] = {}
        categories: dict[str, int] = {}
        transaction_ids: set[str] = set()
        identities: set[tuple[object, ...]] = set()
        code_prefix = f"{prefix}_" if prefix else ""

        if not transactions:
            self._add(findings, f"{code_prefix}DETAIL_EMPTY", "no draw transactions were provided")

        for row_number, row in enumerate(transactions, start=1):
            location = f"{row.detail_id or 'detail'}:{row_number}"
            structure_valid = True
            required_text = (
                ("transaction_id", row.transaction_id),
                ("detail_id", row.detail_id),
                ("job", row.job),
                ("cost_code", row.cost_code),
                ("bank_category", row.bank_category),
                ("transaction_type", row.transaction_type),
                ("description", row.description),
            )
            invalid_text = [name for name, value in required_text if not _clean(value)]
            if invalid_text:
                self._add(
                    findings,
                    f"{code_prefix}IDENTIFIER_INVALID",
                    "trimmed nonblank text required for " + ", ".join(invalid_text),
                    location,
                )
                structure_valid = False
            if not isinstance(row.cost_code, str) or not _CODE_RE.fullmatch(row.cost_code):
                self._add(
                    findings,
                    f"{code_prefix}COST_CODE_INVALID",
                    "cost code is not canonical",
                    location,
                )
                structure_valid = False
            transaction_date = _date_value(row.transaction_date)
            accounting_date = _date_value(row.accounting_date)
            if transaction_date is None or accounting_date is None:
                self._add(
                    findings,
                    f"{code_prefix}DATE_INVALID",
                    "transaction and accounting dates must be real canonical YYYY-MM-DD dates",
                    location,
                )
                structure_valid = False
            elif enforce_current_period and accounting_date.strftime("%Y-%m") != self.current_period:
                self._add(
                    findings,
                    f"{code_prefix}ACCOUNTING_DATE_OUTSIDE_PERIOD",
                    f"accounting date {row.accounting_date} is outside {self.current_period}",
                    location,
                )
            amount_fields = (
                "amount_cents",
                "retainage_cents",
                "adjustment_cents",
                "draw_cents",
            )
            invalid_amounts = [name for name in amount_fields if not _amount(getattr(row, name))]
            if invalid_amounts:
                self._add(
                    findings,
                    f"{code_prefix}AMOUNT_INVALID",
                    "integer cents required for " + ", ".join(invalid_amounts),
                    location,
                )
                structure_valid = False
            if _clean(row.transaction_id):
                transaction_key = row.transaction_id.casefold()
                if transaction_key in transaction_ids:
                    self._add(
                        findings,
                        f"{code_prefix}TRANSACTION_ID_DUPLICATE",
                        "transaction id appears more than once",
                        location,
                    )
                transaction_ids.add(transaction_key)
            identity = (
                str(row.job).strip().casefold(),
                str(row.cost_code).strip().casefold(),
                str(row.transaction_type).strip().casefold(),
                row.transaction_date,
                row.accounting_date,
                str(row.vendor).strip().casefold(),
                str(row.invoice).strip().casefold(),
                str(row.description).strip().casefold(),
                row.amount_cents,
            )
            if identity in identities:
                self._add(
                    findings,
                    f"{code_prefix}TRANSACTION_IDENTITY_DUPLICATE",
                    "the same job-cost transaction identity appears more than once",
                    location,
                )
            identities.add(identity)
            if isinstance(row.transaction_type, str) and "ap" in row.transaction_type.casefold():
                if not _clean(row.vendor) or not _clean(row.invoice):
                    self._add(
                        findings,
                        f"{code_prefix}AP_SUPPORT_INCOMPLETE",
                        "AP-cost rows require a vendor and invoice",
                        location,
                    )
            if not structure_valid:
                continue
            expected_draw = row.amount_cents - row.retainage_cents + row.adjustment_cents
            if row.draw_cents != expected_draw:
                self._add(
                    findings,
                    f"{code_prefix}DRAW_AMOUNT_OUT_OF_TIE",
                    f"draw {row.draw_cents} != amount less retainage plus adjustment {expected_draw}",
                    location,
                )
            valid.append(row)
            detail_key = row.detail_id.casefold()
            category_key = row.bank_category.casefold()
            details[detail_key] = details.get(detail_key, 0) + row.draw_cents
            categories[category_key] = categories.get(category_key, 0) + row.draw_cents
        return valid, details, categories

    def _inspect_displayed_totals(
        self,
        findings: list[CashDrawFinding],
        details: dict[str, int],
        categories: dict[str, int],
    ) -> None:
        for label, controls, expected, invalid_code, duplicate_code, mismatch_code in (
            (
                "detail",
                self.detail_totals,
                details,
                "DETAIL_TOTAL_INVALID",
                "DETAIL_TOTAL_DUPLICATE",
                "DETAIL_TOTAL_OUT_OF_TIE",
            ),
            (
                "category",
                self.category_totals,
                categories,
                "CATEGORY_TOTAL_INVALID",
                "CATEGORY_TOTAL_DUPLICATE",
                "CATEGORY_TOTAL_OUT_OF_TIE",
            ),
        ):
            seen: set[str] = set()
            for position, control in enumerate(controls, start=1):
                raw_key = control.detail_id if label == "detail" else control.bank_category
                if not _clean(raw_key) or not _amount(control.displayed_cents):
                    self._add(
                        findings,
                        invalid_code,
                        f"{label} control {position} requires a trimmed key and integer cents",
                    )
                    continue
                key = raw_key.casefold()
                if key in seen:
                    self._add(findings, duplicate_code, f"{label} control {raw_key!r} is duplicated")
                    continue
                seen.add(key)
                if key not in expected:
                    self._add(
                        findings,
                        f"{label.upper()}_TOTAL_UNKNOWN",
                        f"displayed {label} {raw_key!r} has no supporting transactions",
                    )
                elif control.displayed_cents != expected[key]:
                    self._add(
                        findings,
                        mismatch_code,
                        f"{raw_key!r} displayed {control.displayed_cents} != transaction sum {expected[key]}",
                    )
            missing = sorted(set(expected) - seen)
            if missing:
                self._add(
                    findings,
                    f"{label.upper()}_TOTAL_MISSING",
                    f"missing displayed {label} totals: " + ", ".join(missing),
                )

    def _inspect_snapshot(
        self,
        snapshot: DrawSnapshot,
        findings: list[CashDrawFinding],
        *,
        prefix: str = "",
    ) -> bool:
        code_prefix = f"{prefix}_" if prefix else ""
        valid = True
        if not isinstance(snapshot.period, str) or not _PERIOD_RE.fullmatch(snapshot.period):
            self._add(findings, f"{code_prefix}SNAPSHOT_PERIOD_INVALID", "snapshot period must be canonical YYYY-MM")
            valid = False
        if not isinstance(snapshot.draw_number, int) or isinstance(snapshot.draw_number, bool) or snapshot.draw_number < 0:
            self._add(findings, f"{code_prefix}DRAW_NUMBER_INVALID", "draw number must be a nonnegative integer")
            valid = False
        invalid_amounts = [name for name in _SNAPSHOT_AMOUNT_FIELDS if not _amount(getattr(snapshot, name))]
        if invalid_amounts:
            self._add(
                findings,
                f"{code_prefix}SNAPSHOT_AMOUNT_INVALID",
                "integer cents required for " + ", ".join(invalid_amounts),
            )
            valid = False
        return valid

    def _inspect_current_equations(
        self,
        findings: list[CashDrawFinding],
        combined_detail: int,
    ) -> bool:
        snapshot = self.current_snapshot
        valid = self._inspect_snapshot(snapshot, findings)
        if not valid:
            return False
        if snapshot.period != self.current_period:
            self._add(
                findings,
                "SNAPSHOT_PERIOD_MISMATCH",
                f"snapshot period {snapshot.period} != target {self.current_period}",
            )
        if snapshot.current_draw_cents != combined_detail:
            self._add(
                findings,
                "DETAIL_TO_DRAW_OUT_OF_TIE",
                f"current draw {snapshot.current_draw_cents} != combined detail {combined_detail}",
            )
        expected_funding = snapshot.total_equity_cents + snapshot.cumulative_lender_draws_cents
        if snapshot.total_loan_equity_cents != expected_funding:
            self._add(
                findings,
                "LOAN_EQUITY_OUT_OF_TIE",
                f"loan/equity {snapshot.total_loan_equity_cents} != equity plus draws {expected_funding}",
            )
        if snapshot.total_debt_equity_cents != expected_funding:
            self._add(
                findings,
                "TOTAL_DEBT_EQUITY_OUT_OF_TIE",
                f"total debt/equity {snapshot.total_debt_equity_cents} != equity plus draws {expected_funding}",
            )
        expected_net_jc = (
            snapshot.job_cost_to_date_cents
            + snapshot.net_zero_adjustments_cents
            + snapshot.less_retention_cents
        )
        if snapshot.net_job_cost_to_date_cents != expected_net_jc:
            self._add(
                findings,
                "NET_JOB_COST_OUT_OF_TIE",
                f"net job cost {snapshot.net_job_cost_to_date_cents} != job cost plus adjustments and retention {expected_net_jc}",
            )
        expected_variance = snapshot.net_job_cost_to_date_cents - snapshot.total_debt_equity_cents
        if snapshot.variance_cents != expected_variance:
            self._add(
                findings,
                "VARIANCE_OUT_OF_TIE",
                f"variance {snapshot.variance_cents} != net job cost less funding {expected_variance}",
            )
        if snapshot.project_report_total_cents != snapshot.net_job_cost_to_date_cents:
            self._add(
                findings,
                "PROJECT_REPORT_OUT_OF_TIE",
                f"project report {snapshot.project_report_total_cents} != net job cost {snapshot.net_job_cost_to_date_cents}",
            )
        return True

    def _inspect_prior_continuity(
        self,
        findings: list[CashDrawFinding],
    ) -> tuple[int | None, int | None]:
        if self.prior_snapshot is None:
            self._add(
                findings,
                "PRIOR_COMPARATOR_NOT_PROVIDED",
                "funding continuity was not tested because no prior snapshot was supplied",
                severity="REVIEW",
            )
            return None, None
        prior_valid = self._inspect_snapshot(self.prior_snapshot, findings, prefix="PRIOR")
        current_valid = all(_amount(getattr(self.current_snapshot, name)) for name in _SNAPSHOT_AMOUNT_FIELDS)
        if not prior_valid or not current_valid:
            return None, None
        expected_prior = _previous_period(self.current_period)
        if self.prior_snapshot.period != expected_prior:
            self._add(
                findings,
                "PRIOR_PERIOD_MISMATCH",
                f"prior snapshot {self.prior_snapshot.period} != immediate prior {expected_prior}",
            )
        if self.current_snapshot.draw_number != self.prior_snapshot.draw_number + 1:
            self._add(
                findings,
                "DRAW_NUMBER_DISCONTINUITY",
                f"draw {self.current_snapshot.draw_number} does not follow {self.prior_snapshot.draw_number}",
            )
        interest = self.current_snapshot.interest_to_date_cents - self.prior_snapshot.interest_to_date_cents
        funding = (
            self.current_snapshot.cumulative_lender_draws_cents
            - self.prior_snapshot.cumulative_lender_draws_cents
        )
        expected_funding = self.current_snapshot.current_draw_cents + interest
        if funding != expected_funding:
            self._add(
                findings,
                "CUMULATIVE_FUNDING_CONTINUITY_FAILED",
                f"funding increase {funding} != current draw plus period interest {expected_funding}",
            )
        for code, current_amount, prior_amount in (
            (
                "LOAN_EQUITY_CONTINUITY_FAILED",
                self.current_snapshot.total_loan_equity_cents,
                self.prior_snapshot.total_loan_equity_cents,
            ),
            (
                "TOTAL_DEBT_EQUITY_CONTINUITY_FAILED",
                self.current_snapshot.total_debt_equity_cents,
                self.prior_snapshot.total_debt_equity_cents,
            ),
        ):
            if current_amount - prior_amount != funding:
                self._add(findings, code, f"balance increase {current_amount - prior_amount} != funding increase {funding}")
        return interest, funding

    def _inspect_dependencies(self, findings: list[CashDrawFinding]) -> None:
        seen: set[str] = set()
        for position, item in enumerate(self.dependencies, start=1):
            if not _clean(item.label) or not _clean(item.reference):
                self._add(
                    findings,
                    "DEPENDENCY_INVALID",
                    f"dependency {position} requires trimmed label and reference text",
                )
                continue
            key = item.label.casefold()
            if key in seen:
                self._add(findings, "DEPENDENCY_DUPLICATE", f"dependency {item.label!r} is duplicated")
            seen.add(key)
            reference = item.reference
            if "[" in reference or "]" in reference or "://" in reference or "#REF!" in reference.upper():
                self._add(
                    findings,
                    "DEPENDENCY_EXTERNAL_OR_BROKEN",
                    f"dependency {item.label!r} is external or broken",
                )
            if isinstance(item.cached_value, str) and _FORMULA_ERROR_RE.search(item.cached_value):
                self._add(
                    findings,
                    "DEPENDENCY_CACHED_ERROR",
                    f"dependency {item.label!r} has a cached spreadsheet error",
                )

    def _inspect_revision(
        self,
        findings: list[CashDrawFinding],
        current_detail_cents: int,
    ) -> int | None:
        if self.original_snapshot is None and not self.original_transactions:
            return None
        if self.original_snapshot is None or not self.original_transactions:
            self._add(
                findings,
                "REVISION_COMPARATOR_INCOMPLETE",
                "a revision requires both original snapshot and original transactions",
            )
            return None
        snapshot_valid = self._inspect_snapshot(self.original_snapshot, findings, prefix="ORIGINAL")
        original_findings: list[CashDrawFinding] = []
        original_rows, _details, _categories = self._inspect_transactions(
            self.original_transactions,
            original_findings,
            prefix="ORIGINAL",
            enforce_current_period=False,
        )
        findings.extend(original_findings)
        if not snapshot_valid or not original_rows:
            return None
        if self.original_snapshot.period != self.current_snapshot.period:
            self._add(
                findings,
                "REVISION_PERIOD_MISMATCH",
                "original and revision snapshots cover different periods",
            )
        if self.original_snapshot.draw_number != self.current_snapshot.draw_number:
            self._add(
                findings,
                "REVISION_DRAW_NUMBER_CHANGED",
                "a same-period revision changed the draw number",
            )
        original_detail = sum(row.draw_cents for row in original_rows)
        detail_delta = current_detail_cents - original_detail
        snapshot_delta = self.current_snapshot.current_draw_cents - self.original_snapshot.current_draw_cents
        if detail_delta != snapshot_delta:
            self._add(
                findings,
                "REVISION_DELTA_OUT_OF_TIE",
                f"detail change {detail_delta} != reconciliation draw change {snapshot_delta}",
            )
        if snapshot_delta:
            self._add(
                findings,
                "REVISION_APPROVAL_REQUIRED",
                f"same-period revision changed the draw by {snapshot_delta} cents",
                severity="REVIEW",
            )
        return snapshot_delta

    def run(self) -> CashDrawResult:
        findings: list[CashDrawFinding] = []
        valid_rows, details, categories = self._inspect_transactions(
            self.transactions, findings
        )
        self._inspect_displayed_totals(findings, details, categories)
        combined_detail = sum(row.draw_cents for row in valid_rows)
        current_valid = self._inspect_current_equations(findings, combined_detail)
        period_interest, period_funding = self._inspect_prior_continuity(findings)
        self._inspect_dependencies(findings)
        revision_delta = self._inspect_revision(findings, combined_detail)
        return CashDrawResult(
            current_period=self.current_period,
            transaction_count=len(self.transactions),
            detail_count=len(details),
            category_count=len(categories),
            combined_detail_cents=combined_detail,
            current_draw_cents=(self.current_snapshot.current_draw_cents if current_valid else None),
            period_interest_cents=period_interest,
            period_lender_funding_cents=period_funding,
            revision_draw_delta_cents=revision_delta,
            findings=tuple(findings),
        )


def demo_inputs() -> tuple[
    tuple[DrawTransaction, ...],
    tuple[DetailTotal, ...],
    tuple[CategoryTotal, ...],
    DrawSnapshot,
    DrawSnapshot,
]:
    """Return a clean, entirely fictional current/prior draw example."""

    transactions = (
        DrawTransaction(
            "TX-001",
            "Land Detail",
            "DEMO-01",
            "10-100",
            "Site Construction",
            "Job cost",
            "2026-06-18",
            "2026-06-30",
            "",
            "",
            "Fictional survey work",
            125_000,
            5_000,
            0,
            120_000,
        ),
        DrawTransaction(
            "TX-002",
            "Build Detail",
            "DEMO-02",
            "20-200",
            "General Conditions",
            "Job cost",
            "2026-06-25",
            "2026-06-30",
            "",
            "",
            "Fictional supervision cost",
            80_000,
            0,
            0,
            80_000,
        ),
    )
    details = (DetailTotal("Land Detail", 120_000), DetailTotal("Build Detail", 80_000))
    categories = (
        CategoryTotal("Site Construction", 120_000),
        CategoryTotal("General Conditions", 80_000),
    )
    prior = DrawSnapshot(
        "2026-05",
        8,
        50_000,
        25_000,
        500_000,
        1_000_000,
        1_500_000,
        1_500_000,
        1_510_000,
        0,
        -10_000,
        1_500_000,
        0,
        1_500_000,
    )
    current = DrawSnapshot(
        "2026-06",
        9,
        200_000,
        30_000,
        705_000,
        1_000_000,
        1_705_000,
        1_705_000,
        1_715_000,
        0,
        -10_000,
        1_705_000,
        0,
        1_705_000,
    )
    return transactions, details, categories, current, prior


__all__ = [
    "CashDrawFinding",
    "CashDrawResult",
    "CashDrawValidator",
    "CategoryTotal",
    "DependencyEvidence",
    "DetailTotal",
    "DrawSnapshot",
    "DrawTransaction",
    "demo_inputs",
]
