"""Data model for the partnership 1065 automation demo."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Partner:
    """A fictional partner with allocation percentages."""

    partner_id: str
    name: str
    entity_type: str
    profit_bps: int
    loss_bps: int
    capital_bps: int


@dataclass(frozen=True)
class SourceRecord:
    """One source value as if extracted from a workpaper tab or return PDF."""

    source_id: str
    tab: str
    cell: str
    label: str
    amount_cents: int
    note: str


@dataclass(frozen=True)
class IncomeItem:
    """A book income item from the source trial balance / P&L."""

    label: str
    amount_cents: int
    source_id: str


@dataclass(frozen=True)
class DeductionItem:
    """A book deduction item, with tax treatment."""

    label: str
    amount_cents: int
    source_id: str
    deductible_for_tax: bool = True
    is_book_depreciation: bool = False


@dataclass(frozen=True)
class BookTaxAdjustment:
    """Schedule M-1 style adjustment from book income to tax income."""

    code: str
    description: str
    amount_cents: int
    source_id: str


@dataclass(frozen=True)
class BalanceSheet:
    """Schedule L source balances."""

    cash_cents: int
    receivables_cents: int
    property_net_cents: int
    liabilities_cents: int

    @property
    def total_assets_cents(self) -> int:
        return self.cash_cents + self.receivables_cents + self.property_net_cents


@dataclass(frozen=True)
class CapitalActivity:
    """Partner capital activity before current-year income allocation."""

    partner_id: str
    beginning_capital_cents: int
    contributions_cents: int
    distributions_cents: int


@dataclass
class TaxSourcePackage:
    """All fictional inputs extracted from the 'Excel + PDF' source bundle."""

    year: int
    partnership_name: str
    ein: str
    partners: list[Partner]
    source_records: list[SourceRecord]
    income_items: list[IncomeItem]
    deduction_items: list[DeductionItem]
    book_tax_adjustments: list[BookTaxAdjustment]
    balance_sheet: BalanceSheet
    capital_activity: list[CapitalActivity]


@dataclass(frozen=True)
class FormLine:
    """A mapped return line with source support."""

    form: str
    line: str
    description: str
    amount_cents: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class PartnerAllocation:
    """One partner's K-1 and capital rollforward output."""

    partner_id: str
    partner_name: str
    ordinary_income_cents: int
    beginning_capital_cents: int
    contributions_cents: int
    distributions_cents: int
    ending_capital_cents: int


@dataclass(frozen=True)
class ReviewCheck:
    """A reviewer-facing control check."""

    check_id: str
    description: str
    expected_cents: int
    actual_cents: int
    tolerance_cents: int = 0
    source: str = ""
    is_money: bool = True

    @property
    def difference_cents(self) -> int:
        return self.actual_cents - self.expected_cents

    @property
    def status(self) -> str:
        return "OK" if abs(self.difference_cents) <= self.tolerance_cents else "FAIL"


@dataclass
class TaxPackage:
    """Computed workpapers, return line mappings, allocations, and checks."""

    source: TaxSourcePackage
    book_income_cents: int
    ordinary_income_cents: int
    total_income_cents: int
    total_deductions_cents: int
    tax_depreciation_cents: int
    form_lines: list[FormLine] = field(default_factory=list)
    partner_allocations: list[PartnerAllocation] = field(default_factory=list)
    checks: list[ReviewCheck] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(check.status == "OK" for check in self.checks)
