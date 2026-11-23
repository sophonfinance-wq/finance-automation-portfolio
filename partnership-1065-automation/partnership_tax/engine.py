"""Build 1065 workpapers, line mappings, K-1 allocations, and checks."""

from __future__ import annotations

from .money import allocate_by_bps
from .model import (
    CapitalActivity,
    FormLine,
    PartnerAllocation,
    ReviewCheck,
    TaxPackage,
    TaxSourcePackage,
)


def build_tax_package(source: TaxSourcePackage) -> TaxPackage:
    """Build the full fictional 1065 support package from source inputs."""
    income_total = sum(item.amount_cents for item in source.income_items)
    book_deductions = sum(item.amount_cents for item in source.deduction_items)
    book_income = income_total - book_deductions
    adjustment_total = sum(adj.amount_cents for adj in source.book_tax_adjustments)
    ordinary_income = book_income + adjustment_total

    tax_depreciation = abs(
        sum(adj.amount_cents for adj in source.book_tax_adjustments if adj.code == "M1-TDEP")
    )
    deductible_book = sum(
        item.amount_cents
        for item in source.deduction_items
        if item.deductible_for_tax and not item.is_book_depreciation
    )
    total_deductions = deductible_book + tax_depreciation

    package = TaxPackage(
        source=source,
        book_income_cents=book_income,
        ordinary_income_cents=ordinary_income,
        total_income_cents=income_total,
        total_deductions_cents=total_deductions,
        tax_depreciation_cents=tax_depreciation,
    )
    package.form_lines = _form_lines(source, package)
    package.partner_allocations = _partner_allocations(source, ordinary_income)
    package.checks = _review_checks(source, package)
    return package


def _form_lines(source: TaxSourcePackage, package: TaxPackage) -> list[FormLine]:
    income_sources = tuple(item.source_id for item in source.income_items)
    other_deduction_sources = tuple(
        item.source_id
        for item in source.deduction_items
        if item.deductible_for_tax and not item.is_book_depreciation
    )
    deduction_sources = other_deduction_sources + ("DEPR-001",)
    return [
        FormLine("Form 1065", "1c", "Gross receipts / income", package.total_income_cents, income_sources),
        FormLine("Form 1065", "14", "Depreciation", package.tax_depreciation_cents, ("DEPR-001",)),
        FormLine("Form 1065", "20", "Other deductions", package.total_deductions_cents - package.tax_depreciation_cents, other_deduction_sources),
        FormLine("Form 1065", "21", "Total deductions", package.total_deductions_cents, deduction_sources),
        FormLine("Form 1065", "22", "Ordinary business income", package.ordinary_income_cents, ("K-ORD",)),
        FormLine("Schedule K", "1", "Ordinary business income", package.ordinary_income_cents, ("K-ORD",)),
        FormLine("Schedule L", "14", "Total assets", source.balance_sheet.total_assets_cents, ("BS-CASH", "BS-REC", "BS-PROP")),
        FormLine("Schedule L", "21", "Total liabilities", source.balance_sheet.liabilities_cents, ("BS-LIAB",)),
        FormLine("Schedule M-1", "1", "Net income per books", package.book_income_cents, ("TB-4000", "TB-4900")),
        FormLine("Schedule M-1", "9", "Income per return", package.ordinary_income_cents, ("K-ORD",)),
        FormLine("Schedule M-2", "1", "Beginning capital", _capital_total(source.capital_activity, "beginning_capital_cents"), ("M2-BOY",)),
        FormLine("Schedule M-2", "2", "Capital contributed", _capital_total(source.capital_activity, "contributions_cents"), ("M2-CONTRIB",)),
        FormLine("Schedule M-2", "3", "Net income", package.ordinary_income_cents, ("K-ORD",)),
        FormLine("Schedule M-2", "6", "Distributions", _capital_total(source.capital_activity, "distributions_cents"), ("M2-DIST",)),
        FormLine("Schedule M-2", "9", "Ending capital", _ending_capital_total(source.capital_activity, package.ordinary_income_cents, source), ("M2-BOY", "M2-CONTRIB", "M2-DIST", "K-ORD")),
    ]


def _partner_allocations(source: TaxSourcePackage, ordinary_income: int) -> list[PartnerAllocation]:
    income_alloc = allocate_by_bps(ordinary_income, [p.profit_bps for p in source.partners])
    capital_by_partner = {row.partner_id: row for row in source.capital_activity}
    allocations: list[PartnerAllocation] = []
    for i, partner in enumerate(source.partners):
        cap = capital_by_partner[partner.partner_id]
        ending = (
            cap.beginning_capital_cents
            + cap.contributions_cents
            + income_alloc[i]
            - cap.distributions_cents
        )
        allocations.append(
            PartnerAllocation(
                partner_id=partner.partner_id,
                partner_name=partner.name,
                ordinary_income_cents=income_alloc[i],
                beginning_capital_cents=cap.beginning_capital_cents,
                contributions_cents=cap.contributions_cents,
                distributions_cents=cap.distributions_cents,
                ending_capital_cents=ending,
            )
        )
    return allocations


def _review_checks(source: TaxSourcePackage, package: TaxPackage) -> list[ReviewCheck]:
    line = {f"{ln.form}:{ln.line}": ln.amount_cents for ln in package.form_lines}
    assets = source.balance_sheet.total_assets_cents
    ending_capital = sum(p.ending_capital_cents for p in package.partner_allocations)
    m1_expected = package.book_income_cents + sum(
        adj.amount_cents for adj in source.book_tax_adjustments
    )
    return [
        ReviewCheck("CHK-001", "Form 1065 line 22 ties to Schedule K line 1", line["Schedule K:1"], line["Form 1065:22"], source="1065 line map"),
        ReviewCheck("CHK-002", "K-1 ordinary income allocations sum to Schedule K line 1", line["Schedule K:1"], sum(p.ordinary_income_cents for p in package.partner_allocations), source="Partner allocation engine"),
        ReviewCheck("CHK-003", "Schedule L balances", assets, source.balance_sheet.liabilities_cents + ending_capital, source="Balance Sheet + M-2"),
        ReviewCheck("CHK-004", "Schedule M-1 reconciles book income to return income", package.ordinary_income_cents, m1_expected, source="Book-tax adjustment schedule"),
        ReviewCheck("CHK-005", "Schedule M-2 ending capital ties to partner rollforward", line["Schedule M-2:9"], ending_capital, source="Member capital accounts"),
        ReviewCheck("CHK-006", "Partner percentages sum to 100%", 10_000, sum(p.profit_bps for p in source.partners), source="Partner master", is_money=False),
        ReviewCheck("CHK-007", "All mapped return lines have source references", len(package.form_lines), sum(1 for ln in package.form_lines if ln.source_ids), source="Source index", is_money=False),
    ]


def _capital_total(rows: list[CapitalActivity], attr: str) -> int:
    return sum(getattr(row, attr) for row in rows)


def _ending_capital_total(
    rows: list[CapitalActivity], ordinary_income: int, source: TaxSourcePackage
) -> int:
    beginning = _capital_total(rows, "beginning_capital_cents")
    contributions = _capital_total(rows, "contributions_cents")
    distributions = _capital_total(rows, "distributions_cents")
    return beginning + contributions + ordinary_income - distributions
