"""Seeded fictional source package for the partnership 1065 demo."""

from __future__ import annotations

import random

from .money import allocate_by_bps, to_cents
from .model import (
    BalanceSheet,
    BookTaxAdjustment,
    CapitalActivity,
    DeductionItem,
    IncomeItem,
    Partner,
    SourceRecord,
    TaxSourcePackage,
)

DEFAULT_SEED = 1065


def generate_source_package(year: int = 2025, seed: int = DEFAULT_SEED) -> TaxSourcePackage:
    """Generate a fictional Excel/PDF source bundle for one partnership return."""
    rng = random.Random(seed)

    partners = [
        Partner("GP", "Demo Sponsor GP Inc.", "Domestic corporation", 1, 1, 1),
        Partner("LP1", "Maple Institutional Partner LLC", "Domestic LLC", 8_999, 8_999, 8_999),
        Partner("LP2", "Cedar Class B Investor LLC", "Domestic LLC", 1_000, 1_000, 1_000),
    ]

    rental_income = to_cents(1_845_000 + rng.randint(-2, 2) * 1_000)
    interest_income = to_cents(24_500)
    deductions = [
        DeductionItem("Management fees", to_cents(185_000), "TB-6200"),
        DeductionItem("Repairs and maintenance", to_cents(74_250), "TB-6100"),
        DeductionItem("Real estate taxes", to_cents(121_800), "TB-6350"),
        DeductionItem("Interest expense", to_cents(312_500), "TB-7000"),
        DeductionItem("Professional fees", to_cents(58_400), "TB-7300"),
        DeductionItem("Book depreciation", to_cents(415_000), "TB-7600", is_book_depreciation=True),
        DeductionItem(
            "Syndication costs",
            to_cents(85_000),
            "SYN-001",
            deductible_for_tax=False,
        ),
    ]
    income = [
        IncomeItem("Rental revenue", rental_income, "TB-4000"),
        IncomeItem("Interest income", interest_income, "TB-4900"),
    ]
    adjustments = [
        BookTaxAdjustment("M1-SYN", "Nondeductible syndication costs", to_cents(85_000), "SYN-001"),
        BookTaxAdjustment("M1-BDEP", "Book depreciation addback", to_cents(415_000), "TB-7600"),
        BookTaxAdjustment("M1-TDEP", "Tax depreciation deduction", -to_cents(462_000), "DEPR-001"),
    ]

    # Capital is built so Schedule L, M-2, and K-1 allocations all reconcile.
    book_income = sum(i.amount_cents for i in income) - sum(d.amount_cents for d in deductions)
    ordinary_income = book_income + sum(adj.amount_cents for adj in adjustments)
    beginning_total = to_cents(2_800_000)
    contributions_total = to_cents(1_250_000)
    distributions_total = to_cents(100_000)
    ending_capital_total = beginning_total + contributions_total + ordinary_income - distributions_total
    liabilities = to_cents(8_750_000)
    total_assets = liabilities + ending_capital_total
    balance_sheet = BalanceSheet(
        cash_cents=to_cents(740_000),
        receivables_cents=to_cents(90_000),
        property_net_cents=total_assets - to_cents(740_000) - to_cents(90_000),
        liabilities_cents=liabilities,
    )

    capital_bps = [p.capital_bps for p in partners]
    beginning = allocate_by_bps(beginning_total, capital_bps)
    contributions = allocate_by_bps(contributions_total, capital_bps)
    distributions = allocate_by_bps(distributions_total, capital_bps)
    capital = [
        CapitalActivity(p.partner_id, beginning[i], contributions[i], distributions[i])
        for i, p in enumerate(partners)
    ]

    source_records = _source_records(
        income, deductions, adjustments, balance_sheet, beginning_total, contributions_total,
        distributions_total, ordinary_income
    )

    return TaxSourcePackage(
        year=year,
        partnership_name="Demo 721 Development LP",
        ein="00-0000000",
        partners=partners,
        source_records=source_records,
        income_items=income,
        deduction_items=deductions,
        book_tax_adjustments=adjustments,
        balance_sheet=balance_sheet,
        capital_activity=capital,
    )


def _source_records(
    income: list[IncomeItem],
    deductions: list[DeductionItem],
    adjustments: list[BookTaxAdjustment],
    balance_sheet: BalanceSheet,
    beginning_total: int,
    contributions_total: int,
    distributions_total: int,
    ordinary_income: int,
) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for item in income:
        records.append(SourceRecord(item.source_id, "Trial Balance", "E12", item.label, item.amount_cents, "Pulled from fictional GL export."))
    for item in deductions:
        tab = "Syndication Costs" if item.source_id.startswith("SYN") else "P&L"
        records.append(SourceRecord(item.source_id, tab, "D8", item.label, item.amount_cents, "Mapped from fictional workpaper detail."))
    for adj in adjustments:
        records.append(SourceRecord(adj.source_id, "Book-Tax Adjustments", "C14", adj.description, adj.amount_cents, "Schedule M-1 support."))
    records.extend(
        [
            SourceRecord("BS-CASH", "Balance Sheet", "C9", "Cash", balance_sheet.cash_cents, "Schedule L input."),
            SourceRecord("BS-REC", "Balance Sheet", "C10", "Receivables", balance_sheet.receivables_cents, "Schedule L input."),
            SourceRecord("BS-PROP", "Balance Sheet", "C14", "Property, net", balance_sheet.property_net_cents, "Schedule L input."),
            SourceRecord("BS-LIAB", "Balance Sheet", "C24", "Liabilities", balance_sheet.liabilities_cents, "Schedule L input."),
            SourceRecord("M2-BOY", "Member Capital Accounts", "F19", "Beginning capital", beginning_total, "Partner capital rollforward source."),
            SourceRecord("M2-CONTRIB", "Member Capital Accounts", "I19", "Capital contributions", contributions_total, "Partner capital rollforward source."),
            SourceRecord("M2-DIST", "Member Capital Accounts", "L19", "Distributions", distributions_total, "Partner capital rollforward source."),
            SourceRecord("K-ORD", "1065 Line Map", "K1", "Ordinary income", ordinary_income, "Mapped to Schedule K and K-1 line 1."),
        ]
    )
    return records
