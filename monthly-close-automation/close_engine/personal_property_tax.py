"""Fictional, validation-only personal-property FF&E schedule controls."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
import re


_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class AssetEvidence:
    asset_id: str
    category: str
    placed_in_service: str
    depreciation_end_date: object
    cost_cents: object
    useful_life_months: object
    months_used: object
    accumulated_depreciation_cents: object
    period_depreciation_cents: object
    net_book_value_cents: object
    source_reference: str
    manual_carryforward: object = False


@dataclass(frozen=True)
class AssetScheduleSnapshot:
    period: str
    entity_id: str
    assets: tuple[AssetEvidence, ...]
    cached_cost_cents: object
    cached_accumulated_depreciation_cents: object
    cached_period_depreciation_cents: object
    cached_net_book_value_cents: object
    displayed_control_difference_cents: object = 0


@dataclass(frozen=True)
class PersonalPropertyTaxFinding:
    code: str
    detail: str
    location: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class PersonalPropertyTaxResult:
    current_period: str
    asset_count: int
    unique_asset_count: int
    negative_cost_count: int
    manual_carryforward_count: int
    asset_added_count: int
    asset_removed_count: int
    asset_term_changed_count: int
    findings: tuple[PersonalPropertyTaxFinding, ...]
    manual_gates: tuple[str, ...] = (
        "tie the schedule to the fixed-asset register, general ledger, invoices, disposals, and prior filing",
        "approve situs, asset class, valuation, useful life, convention, taxability, and exemptions",
        "support reimbursements, manual carryforwards, additions, removals, and term changes",
        "obtain tax-owner approval before preparing or filing any return",
        "generate no journal, import, tax filing, system update, or posting action from this validator",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)
    tax_filings: tuple[object, ...] = field(default_factory=tuple)
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
    def filing_authorized(self) -> bool:
        return False

    @property
    def posting_authorized(self) -> bool:
        return False


def _period_end(value: object, field_name: str) -> date:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, monthrange(year, month)[1])


def _prior_year_period(value: str) -> str:
    end = _period_end(value, "current.period")
    return f"{end.year - 1:04d}-{end.month:02d}"


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class PersonalPropertyTaxValidator:
    """Validate fictional current and optional prior-year FF&E evidence."""

    def __init__(
        self,
        current: AssetScheduleSnapshot,
        prior: AssetScheduleSnapshot | None = None,
    ) -> None:
        _period_end(current.period, "current.period")
        if prior is not None:
            _period_end(prior.period, "prior.period")
        self.current = current
        self.prior = prior

    @staticmethod
    def _add(
        findings: list[PersonalPropertyTaxFinding],
        code: str,
        detail: str,
        location: str = "",
        severity: str = "ERROR",
    ) -> None:
        findings.append(PersonalPropertyTaxFinding(code, detail, location, severity))

    def _validate_current(
        self,
        findings: list[PersonalPropertyTaxFinding],
    ) -> tuple[dict[str, tuple[object, object]], int, int]:
        period_end = _period_end(self.current.period, "current.period")
        if not _clean_text(self.current.entity_id):
            self._add(findings, "UNSAFE_ENTITY_ID", "entity id is blank or untrimmed")
        if not self.current.assets:
            self._add(findings, "ASSET_POPULATION_MISSING", "at least one asset is required")

        identities: dict[str, tuple[object, object]] = {}
        totals = {"cost": 0, "accumulated": 0, "period": 0, "nbv": 0}
        negative_costs = 0
        manual_carryforwards = 0
        for asset in self.current.assets:
            location = str(asset.asset_id)
            for value, code in (
                (asset.asset_id, "UNSAFE_ASSET_ID"),
                (asset.category, "UNSAFE_ASSET_CATEGORY"),
                (asset.source_reference, "UNSAFE_SOURCE_REFERENCE"),
            ):
                if not _clean_text(value):
                    self._add(findings, code, "controlled text is blank or untrimmed", location)
            if asset.asset_id in identities:
                self._add(findings, "DUPLICATE_ASSET_ID", "asset id is not unique", location)
            identities[asset.asset_id] = (asset.cost_cents, asset.useful_life_months)

            placed = _parse_date(asset.placed_in_service)
            end_date = _parse_date(asset.depreciation_end_date)
            if placed is None:
                self._add(findings, "PLACED_IN_SERVICE_INVALID", "placed-in-service date must be a valid ISO date", location)
            elif placed > period_end:
                self._add(findings, "FUTURE_ASSET_DATE", "placed-in-service date is after the schedule period", location)
            if end_date is None:
                self._add(findings, "DEPRECIATION_END_DATE_MISSING", "depreciation end date must be a valid ISO date", location)
            elif placed is not None and end_date < placed:
                self._add(findings, "DEPRECIATION_END_BEFORE_START", "depreciation end date precedes placed-in-service date", location)

            if not _integer(asset.useful_life_months) or asset.useful_life_months <= 0:
                self._add(findings, "USEFUL_LIFE_UNSAFE", "useful life must be a positive integer month count", location)
            if not _integer(asset.months_used):
                self._add(findings, "MONTHS_USED_UNSAFE", "months used must be an integer", location)
            elif asset.months_used < 0 or (
                _integer(asset.useful_life_months) and asset.months_used > asset.useful_life_months
            ):
                self._add(findings, "MONTHS_USED_OUT_OF_RANGE", "months used must fall between zero and useful life", location)

            amounts = (
                ("cost", asset.cost_cents),
                ("accumulated", asset.accumulated_depreciation_cents),
                ("period", asset.period_depreciation_cents),
                ("nbv", asset.net_book_value_cents),
            )
            for name, amount in amounts:
                if not _integer(amount):
                    self._add(findings, f"UNSAFE_{name.upper()}_AMOUNT", "amount must be integer cents", location)
                else:
                    totals[name] += amount
            if _integer(asset.cost_cents) and asset.cost_cents < 0:
                negative_costs += 1
                self._add(findings, "NEGATIVE_COST_REVIEW", "negative cost or reimbursement requires support", location, "WARNING")
            if (
                _integer(asset.cost_cents)
                and _integer(asset.accumulated_depreciation_cents)
                and _integer(asset.net_book_value_cents)
                and asset.cost_cents - asset.accumulated_depreciation_cents != asset.net_book_value_cents
            ):
                self._add(findings, "NET_BOOK_VALUE_OUT_OF_TIE", "net book value does not equal cost less accumulated depreciation", location)
            if not isinstance(asset.manual_carryforward, bool):
                self._add(findings, "MANUAL_CARRYFORWARD_FLAG_UNSAFE", "manual-carryforward flag must be boolean", location)
            elif asset.manual_carryforward:
                manual_carryforwards += 1
                self._add(findings, "MANUAL_CARRYFORWARD_REVIEW", "manual depreciation carryforward requires support", location, "WARNING")

        cached_totals = (
            ("COST_TOTAL_OUT_OF_TIE", self.current.cached_cost_cents, totals["cost"]),
            ("ACCUMULATED_DEPRECIATION_TOTAL_OUT_OF_TIE", self.current.cached_accumulated_depreciation_cents, totals["accumulated"]),
            ("PERIOD_DEPRECIATION_TOTAL_OUT_OF_TIE", self.current.cached_period_depreciation_cents, totals["period"]),
            ("NET_BOOK_VALUE_TOTAL_OUT_OF_TIE", self.current.cached_net_book_value_cents, totals["nbv"]),
        )
        for code, cached, rederived in cached_totals:
            if not _integer(cached):
                self._add(findings, "UNSAFE_CACHED_TOTAL", "cached total must be integer cents", code)
            elif cached != rederived:
                self._add(findings, code, f"cached {cached} does not equal rederived {rederived}")
        control = self.current.displayed_control_difference_cents
        if not _integer(control):
            self._add(findings, "DISPLAYED_CONTROL_UNSAFE", "displayed control must be integer cents")
        elif control != 0:
            self._add(findings, "DISPLAYED_CONTROL_OUT_OF_BALANCE", "displayed control is not zero")
        return identities, negative_costs, manual_carryforwards

    def _compare_prior(
        self,
        current_assets: dict[str, tuple[object, object]],
        findings: list[PersonalPropertyTaxFinding],
    ) -> tuple[int, int, int]:
        if self.prior is None:
            return 0, 0, 0
        if self.prior.period != _prior_year_period(self.current.period):
            self._add(findings, "PRIOR_PERIOD_MISMATCH", "comparator is not the same month in the prior year", self.prior.period)
        if self.prior.entity_id != self.current.entity_id:
            self._add(findings, "PRIOR_ENTITY_MISMATCH", "current and prior schedules identify different entities", self.prior.entity_id)
        prior_assets = {asset.asset_id: (asset.cost_cents, asset.useful_life_months) for asset in self.prior.assets}
        added = current_assets.keys() - prior_assets.keys()
        removed = prior_assets.keys() - current_assets.keys()
        changed = {
            asset_id
            for asset_id in current_assets.keys() & prior_assets.keys()
            if current_assets[asset_id] != prior_assets[asset_id]
        }
        if added or removed or changed:
            self._add(
                findings,
                "ASSET_POPULATION_CHANGED",
                "annual asset additions, removals, or cost/life changes require support",
                ",".join(sorted(added | removed | changed)),
                "WARNING",
            )
        return len(added), len(removed), len(changed)

    def validate(self) -> PersonalPropertyTaxResult:
        findings: list[PersonalPropertyTaxFinding] = []
        assets, negative_count, carryforward_count = self._validate_current(findings)
        added, removed, changed = self._compare_prior(assets, findings)
        return PersonalPropertyTaxResult(
            current_period=self.current.period,
            asset_count=len(self.current.assets),
            unique_asset_count=len(assets),
            negative_cost_count=negative_count,
            manual_carryforward_count=carryforward_count,
            asset_added_count=added,
            asset_removed_count=removed,
            asset_term_changed_count=changed,
            findings=tuple(findings),
        )


__all__ = [
    "AssetEvidence",
    "AssetScheduleSnapshot",
    "PersonalPropertyTaxFinding",
    "PersonalPropertyTaxResult",
    "PersonalPropertyTaxValidator",
]
