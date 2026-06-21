"""IRC §704(c) built-in gain/(loss) module — traditional method + ceiling rule.

This is a *self-contained* submodule that deepens the partnership 1065 automation
engine with an IRC §704(c) built-in-gain (BIG) / built-in-loss (BIL) capability.
It is ported from a separately proven §704(c) traditional-method engine and kept
isolated here so it cannot disturb the existing Form 1065 workpaper pipeline.

What it models, deterministically, in integer cents
---------------------------------------------------
Two parallel capital accounts are tracked for every partner:

* **§704(b) book capital** — credited at the *fair market value* of what the
  partner contributes, then adjusted by the partner's share of *book* items
  (book depreciation, book gain/loss on sale).
* **tax capital** — credited at the *carryover tax basis* of the contribution,
  then adjusted by the partner's share of *tax* items.

The initial book-minus-tax disparity per partner equals the built-in gain/(loss)
on the property they contributed (BIG = FMV − tax basis). §704(c) governs how the
partnership's *tax* items are allocated to take that disparity into account.

Traditional method
    * Book items are allocated to all partners by their agreed interest %.
    * Tax depreciation is allocated FIRST to the **non-contributing** partners,
      up to their share of book depreciation, to cure the disparity; the
      contributing partner receives whatever tax depreciation remains.
    * **Ceiling rule.** Total tax item allocated can never exceed the actual tax
      item available. When tax depreciation is *less* than the non-contributors'
      book share, they are capped at the available tax item, the contributor
      gets none, and the disparity is only partially cured — a distortion this
      module *surfaces* (flags) rather than cures.
    * On sale: book gain/(loss) is allocated by interest %; for tax, the
      remaining §704(c) built-in gain is allocated entirely to the contributing
      partner to the extent it remains, residual tax gain/(loss) then by % .

LIMITATION (documented on purpose): only the **traditional method** is
implemented. The remedial and curative methods of Reg. §1.704-3 are NOT modelled.

Everything here is FICTIONAL portfolio data. The integer-cent money helpers are
reused from :mod:`partnership_tax.money`; :func:`split_evenly` is provided here
because the package's ``money`` module does not expose a straight-line splitter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .money import allocate_by_bps, fmt, to_cents

# Basis-point scale: 10000 bps == 100.00%.
BPS_SCALE = 10000


# ---------------------------------------------------------------------------
# Money helper (straight-line splitter) — not provided by package money.py
# ---------------------------------------------------------------------------
def split_evenly(total_cents: int, periods: int) -> List[int]:
    """Split a total into ``periods`` equal integer-cent parts.

    Parts sum exactly to ``total_cents``; any rounding remainder lands on the
    final part so straight-line depreciation schedules never drift.
    """
    if periods < 1:
        raise ValueError("periods must be >= 1")
    base = total_cents // periods
    parts = [base] * periods
    parts[-1] += total_cents - base * periods
    return parts


def _allocate(total_cents: int, weights_bps: List[int]) -> List[int]:
    """Allocate ``total_cents`` by basis-point weights summing to 10000.

    Thin wrapper over the package :func:`partnership_tax.money.allocate_by_bps`
    that validates the weights sum exactly to 100.00% so allocations always tie.
    """
    if sum(weights_bps) != BPS_SCALE:
        raise ValueError(
            f"allocation weights must sum to {BPS_SCALE} bps (100.00%); "
            f"got {sum(weights_bps)}"
        )
    return allocate_by_bps(total_cents, weights_bps)


# ---------------------------------------------------------------------------
# Small self-contained §704(c) model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Partner:
    """A partner with an agreed profit/loss interest in basis points."""

    code: str
    name: str
    interest_bps: int

    def __post_init__(self) -> None:
        if not 0 <= self.interest_bps <= BPS_SCALE:
            raise ValueError(
                f"interest_bps for {self.code} must be in [0,{BPS_SCALE}], "
                f"got {self.interest_bps}"
            )


@dataclass(frozen=True)
class ContributedProperty:
    """A property contributed by one partner at formation (year 0).

    Cash is modelled as a property with equal FMV and tax basis (zero BIG).
    """

    code: str
    name: str
    contributor: str
    fmv_cents: int
    tax_basis_cents: int
    depreciable: bool = False
    book_life_years: int = 0
    tax_life_years: int = 0

    def __post_init__(self) -> None:
        if self.fmv_cents < 0 or self.tax_basis_cents < 0:
            raise ValueError(f"{self.code}: FMV and tax basis must be >= 0")
        if self.depreciable and (self.book_life_years < 1 or self.tax_life_years < 1):
            raise ValueError(
                f"{self.code}: depreciable property needs book/tax lives >= 1"
            )

    @property
    def built_in_gain_cents(self) -> int:
        """Built-in gain/(loss) at formation = FMV − tax basis (signed)."""
        return self.fmv_cents - self.tax_basis_cents

    @property
    def is_cash(self) -> bool:
        return not self.depreciable and self.built_in_gain_cents == 0


@dataclass(frozen=True)
class PropertyYear:
    """Per-property, per-year facts (sale flag + price)."""

    property: str
    year: int
    sold: bool = False
    sale_price_cents: int = 0

    def __post_init__(self) -> None:
        if self.sale_price_cents < 0:
            raise ValueError(f"{self.property}: sale price must be >= 0")


@dataclass(frozen=True)
class PartnershipYear:
    """Per-partnership, per-year facts not tied to a property."""

    year: int
    ordinary_income_cents: int = 0
    cash_distribution_cents: int = 0


@dataclass
class CapitalAccount:
    """A partner's running §704(b) book and tax capital, in cents."""

    book_cents: int = 0
    tax_cents: int = 0

    def copy(self) -> "CapitalAccount":
        return CapitalAccount(book_cents=self.book_cents, tax_cents=self.tax_cents)


@dataclass
class Partnership:
    """The §704(c) partnership: partners, properties, and per-year facts."""

    code: str
    name: str
    partners: Dict[str, Partner]
    properties: Dict[str, ContributedProperty]
    property_years: Dict[tuple[str, int], PropertyYear]
    partnership_years: Dict[int, PartnershipYear]
    years: List[int] = field(default_factory=list)
    method: str = "traditional"

    def __post_init__(self) -> None:
        if self.method not in ("traditional", "remedial"):
            raise ValueError(
                f"method must be 'traditional' or 'remedial', got {self.method!r}"
            )
        total_bps = sum(p.interest_bps for p in self.partners.values())
        if total_bps != BPS_SCALE:
            raise ValueError(
                f"partner interests must sum to {BPS_SCALE} bps (100%); got {total_bps}"
            )
        for prop in self.properties.values():
            if prop.contributor not in self.partners:
                raise ValueError(
                    f"property {prop.code} contributed by unknown partner "
                    f"{prop.contributor!r}"
                )

    def ordered_partners(self) -> List[Partner]:
        return [self.partners[c] for c in sorted(self.partners)]

    def ordered_properties(self) -> List[ContributedProperty]:
        return [self.properties[c] for c in sorted(self.properties)]

    def interest_weights(self) -> List[int]:
        return [p.interest_bps for p in self.ordered_partners()]

    def property_year(self, prop_code: str, year: int) -> PropertyYear:
        return self.property_years.get(
            (prop_code, year), PropertyYear(property=prop_code, year=year)
        )

    def partnership_year(self, year: int) -> PartnershipYear:
        return self.partnership_years.get(year, PartnershipYear(year=year))


# ---------------------------------------------------------------------------
# Per-year result records
# ---------------------------------------------------------------------------
@dataclass
class PropertyYearResult:
    """§704(c) result for one property in one fiscal year (integer cents)."""

    property: str
    year: int
    contributor: str
    sold: bool = False

    book_depreciation: int = 0
    tax_depreciation: int = 0
    book_gain: int = 0            # on sale only
    tax_gain: int = 0            # on sale only (the actual tax item available)

    book_dep_alloc: Dict[str, int] = field(default_factory=dict)
    tax_dep_alloc: Dict[str, int] = field(default_factory=dict)
    book_gain_alloc: Dict[str, int] = field(default_factory=dict)
    tax_gain_alloc: Dict[str, int] = field(default_factory=dict)

    layer_open: int = 0
    layer_close: int = 0
    layer_cured: int = 0

    ceiling_binding: bool = False
    ceiling_shortfall: int = 0

    # Remedial method (Reg. §1.704-3(d)); empty/zero under the traditional method.
    method_used: str = "traditional"
    remedial_income_alloc: Dict[str, int] = field(default_factory=dict)
    remedial_deduction_alloc: Dict[str, int] = field(default_factory=dict)
    remedial_net: int = 0


@dataclass
class PartnerYearResult:
    """Capital-account movement for one partner in one fiscal year (cents)."""

    partner: str
    year: int
    book_open: int = 0
    tax_open: int = 0
    contribution_book: int = 0
    contribution_tax: int = 0
    income_book: int = 0
    income_tax: int = 0
    distribution: int = 0
    book_close: int = 0
    tax_close: int = 0


@dataclass
class YearResult:
    """Everything computed for the partnership in one fiscal year."""

    year: int
    properties: List[PropertyYearResult] = field(default_factory=list)
    partners: List[PartnerYearResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def _other_weights(partnership: Partnership, contributor: str) -> List[int]:
    """Interest weights (bps) renormalised over the NON-contributing partners."""
    partners = partnership.ordered_partners()
    others = [p for p in partners if p.code != contributor]
    total = sum(p.interest_bps for p in others)
    if total == 0:
        n = len(others)
        base = [BPS_SCALE // n] * n
        base[-1] += BPS_SCALE - sum(base)
        return base
    weights = [round(p.interest_bps * BPS_SCALE / total) for p in others]
    drift = BPS_SCALE - sum(weights)
    if drift and weights:
        idx = max(range(len(others)), key=lambda i: others[i].interest_bps)
        weights[idx] += drift
    return weights


class Section704cEngine:
    """Stateful §704(c) engine that rolls a partnership forward by fiscal year."""

    def __init__(self, partnership: Partnership):
        self.p = partnership
        self._capital: Dict[str, CapitalAccount] = {
            code: CapitalAccount() for code in partnership.partners
        }
        # Remaining §704(c) layer per property (signed), seeded at BIG/BIL.
        self._layer: Dict[str, int] = {
            code: prop.built_in_gain_cents
            for code, prop in partnership.properties.items()
        }
        self._book_basis: Dict[str, int] = {
            code: prop.fmv_cents for code, prop in partnership.properties.items()
        }
        self._tax_basis: Dict[str, int] = {
            code: prop.tax_basis_cents
            for code, prop in partnership.properties.items()
        }
        self._sold: Dict[str, bool] = {c: False for c in partnership.properties}
        self._formation_done = False

    # -- public API -------------------------------------------------------
    def run(self) -> List[YearResult]:
        """Roll the partnership forward across all of its fiscal years."""
        self._apply_formation()
        return [self._run_year(year) for year in sorted(self.p.years)]

    def formation_capital(self) -> Dict[str, CapitalAccount]:
        """Capital accounts immediately after formation contributions.

        Book capital is credited at FMV; tax capital at carryover tax basis. The
        per-partner book-minus-tax disparity equals the BIG/BIL on the property
        contributed.
        """
        self._apply_formation()
        return {c: acct.copy() for c, acct in self._capital.items()}

    # -- internals --------------------------------------------------------
    def _apply_formation(self) -> None:
        if self._formation_done:
            return
        for prop in self.p.properties.values():
            acct = self._capital[prop.contributor]
            acct.book_cents += prop.fmv_cents
            acct.tax_cents += prop.tax_basis_cents
        self._formation_done = True

    def _run_year(self, year: int) -> YearResult:
        partners = self.p.ordered_partners()
        weights = self.p.interest_weights()

        income_book: Dict[str, int] = {p.code: 0 for p in partners}
        income_tax: Dict[str, int] = {p.code: 0 for p in partners}
        prop_results: List[PropertyYearResult] = []

        # 1) Ordinary operating income/(loss): identical book and tax, by %.
        py = self.p.partnership_year(year)
        if py.ordinary_income_cents:
            for partner, amt in zip(partners, _allocate(py.ordinary_income_cents, weights)):
                income_book[partner.code] += amt
                income_tax[partner.code] += amt

        # 2) Each contributed property: depreciation OR sale.
        for prop in self.p.ordered_properties():
            if not prop.depreciable or self._sold[prop.code]:
                continue
            pyr = self.p.property_year(prop.code, year)
            if pyr.sold:
                res = self._handle_sale(prop, year, pyr.sale_price_cents)
            elif self.p.method == "remedial":
                res = self._remedial_depreciation(prop, year)
            else:
                res = self._handle_depreciation(prop, year)
            res.method_used = self.p.method
            prop_results.append(res)
            for code, amt in res.book_dep_alloc.items():
                income_book[code] -= amt
            for code, amt in res.tax_dep_alloc.items():
                income_tax[code] -= amt
            for code, amt in res.book_gain_alloc.items():
                income_book[code] += amt
            for code, amt in res.tax_gain_alloc.items():
                income_tax[code] += amt
            # Remedial notional items (Reg. §1.704-3(d)): tax-only, equal and
            # offsetting, net to zero, no effect on book capital.
            for code, amt in res.remedial_income_alloc.items():
                income_tax[code] += amt
            for code, amt in res.remedial_deduction_alloc.items():
                income_tax[code] -= amt

        # 3) Cash distribution: pro-rata by interest, reduces both bases.
        dist_parts = (
            _allocate(py.cash_distribution_cents, weights)
            if py.cash_distribution_cents
            else [0] * len(partners)
        )
        dist_by_code = {p.code: d for p, d in zip(partners, dist_parts)}

        # 4) Roll forward each partner's capital account.
        partner_results: List[PartnerYearResult] = []
        for partner in partners:
            acct = self._capital[partner.code]
            book_open, tax_open = acct.book_cents, acct.tax_cents
            ib = income_book[partner.code]
            it = income_tax[partner.code]
            dist = dist_by_code[partner.code]
            acct.book_cents = book_open + ib - dist
            acct.tax_cents = tax_open + it - dist
            partner_results.append(
                PartnerYearResult(
                    partner=partner.code,
                    year=year,
                    book_open=book_open,
                    tax_open=tax_open,
                    income_book=ib,
                    income_tax=it,
                    distribution=dist,
                    book_close=acct.book_cents,
                    tax_close=acct.tax_cents,
                )
            )

        return YearResult(year=year, properties=prop_results, partners=partner_results)

    # -- property mechanics ----------------------------------------------
    def _book_dep_amount(self, prop: ContributedProperty) -> int:
        return split_evenly(prop.fmv_cents, prop.book_life_years)[0]

    def _tax_dep_amount(self, prop: ContributedProperty) -> int:
        return split_evenly(prop.tax_basis_cents, prop.tax_life_years)[0]

    def _handle_depreciation(
        self, prop: ContributedProperty, year: int
    ) -> PropertyYearResult:
        weights = self.p.interest_weights()
        partners = self.p.ordered_partners()

        book_dep = min(self._book_basis[prop.code], self._book_dep_amount(prop))
        tax_dep = min(self._tax_basis[prop.code], self._tax_dep_amount(prop))

        book_alloc_list = _allocate(book_dep, weights)
        book_dep_alloc = {p.code: a for p, a in zip(partners, book_alloc_list)}

        noncontrib_book_share = sum(
            a for code, a in book_dep_alloc.items() if code != prop.contributor
        )

        ceiling_binding = False
        ceiling_shortfall = 0
        tax_dep_alloc = {p.code: 0 for p in partners}
        others = [p for p in partners if p.code != prop.contributor]

        if tax_dep >= noncontrib_book_share:
            # Enough tax depreciation: non-contributors get their full book
            # share; the contributing partner gets the remainder.
            other_shares = _allocate(
                noncontrib_book_share, _other_weights(self.p, prop.contributor)
            )
            for partner, amt in zip(others, other_shares):
                tax_dep_alloc[partner.code] = amt
            tax_dep_alloc[prop.contributor] = tax_dep - noncontrib_book_share
        else:
            # CEILING RULE: not enough actual tax depreciation to give the
            # non-contributors their full book share. They are limited to the
            # available tax depreciation; the contributor gets zero. The
            # disparity is only partially cured this year (a distortion).
            ceiling_binding = True
            ceiling_shortfall = noncontrib_book_share - tax_dep
            other_shares = _allocate(tax_dep, _other_weights(self.p, prop.contributor))
            for partner, amt in zip(others, other_shares):
                tax_dep_alloc[partner.code] = amt
            tax_dep_alloc[prop.contributor] = 0

        layer_open = self._layer[prop.code]
        cured = self._cure_layer(prop.code, book_dep - tax_dep)
        layer_close = self._layer[prop.code]

        self._book_basis[prop.code] -= book_dep
        self._tax_basis[prop.code] -= tax_dep

        return PropertyYearResult(
            property=prop.code,
            year=year,
            contributor=prop.contributor,
            sold=False,
            book_depreciation=book_dep,
            tax_depreciation=tax_dep,
            book_dep_alloc=book_dep_alloc,
            tax_dep_alloc=tax_dep_alloc,
            layer_open=layer_open,
            layer_close=layer_close,
            layer_cured=cured,
            ceiling_binding=ceiling_binding,
            ceiling_shortfall=ceiling_shortfall,
        )

    def _remedial_depreciation(
        self, prop: ContributedProperty, year: int
    ) -> PropertyYearResult:
        """Remedial method (Reg. §1.704-3(d)): cure the ceiling shortfall with
        equal, offsetting notional items.

        Actual tax depreciation is allocated exactly as under the traditional
        method (non-contributors first, up to their book share; the ceiling caps
        them at the available tax item). Where the ceiling would bind, the
        partnership then creates a *remedial deduction* for the short-changed
        non-contributors and an equal, offsetting *remedial income* item of the
        same character for the contributor. The pair nets to zero, never touches
        book capital, and eliminates the non-contributor's book/tax disparity.

        Book depreciation note: §1.704-3(d)(2) recovers the tax-basis portion of
        book value over its remaining tax life and the book-over-tax excess over
        a new recovery period. When that new period equals the book life (as in
        these fixtures), the two-layer schedule coincides exactly with
        straight-line FMV / book life, which is what is used here.
        """
        weights = self.p.interest_weights()
        partners = self.p.ordered_partners()

        book_dep = min(self._book_basis[prop.code], self._book_dep_amount(prop))
        tax_dep = min(self._tax_basis[prop.code], self._tax_dep_amount(prop))

        book_alloc_list = _allocate(book_dep, weights)
        book_dep_alloc = {p.code: a for p, a in zip(partners, book_alloc_list)}
        noncontrib_book_share = sum(
            a for code, a in book_dep_alloc.items() if code != prop.contributor
        )

        others = [p for p in partners if p.code != prop.contributor]
        tax_dep_alloc = {p.code: 0 for p in partners}
        remedial_deduction_alloc: Dict[str, int] = {}
        remedial_income_alloc: Dict[str, int] = {}

        if tax_dep >= noncontrib_book_share:
            # No ceiling problem: identical to the traditional method; no
            # remedial items are required.
            other_shares = _allocate(
                noncontrib_book_share, _other_weights(self.p, prop.contributor)
            )
            for partner, amt in zip(others, other_shares):
                tax_dep_alloc[partner.code] = amt
            tax_dep_alloc[prop.contributor] = tax_dep - noncontrib_book_share
        else:
            # Ceiling binds at the ACTUAL level; remedial items cure it.
            other_shares = _allocate(tax_dep, _other_weights(self.p, prop.contributor))
            for partner, amt in zip(others, other_shares):
                tax_dep_alloc[partner.code] = amt
            tax_dep_alloc[prop.contributor] = 0
            for partner in others:
                shortfall = book_dep_alloc[partner.code] - tax_dep_alloc[partner.code]
                if shortfall:
                    remedial_deduction_alloc[partner.code] = shortfall
            total_remedial = sum(remedial_deduction_alloc.values())
            if total_remedial:
                remedial_income_alloc[prop.contributor] = total_remedial

        remedial_net = (
            sum(remedial_income_alloc.values())
            - sum(remedial_deduction_alloc.values())
        )

        layer_open = self._layer[prop.code]
        cured = self._cure_layer(prop.code, book_dep - tax_dep)
        layer_close = self._layer[prop.code]

        self._book_basis[prop.code] -= book_dep
        self._tax_basis[prop.code] -= tax_dep

        return PropertyYearResult(
            property=prop.code,
            year=year,
            contributor=prop.contributor,
            sold=False,
            book_depreciation=book_dep,
            tax_depreciation=tax_dep,
            book_dep_alloc=book_dep_alloc,
            tax_dep_alloc=tax_dep_alloc,
            layer_open=layer_open,
            layer_close=layer_close,
            layer_cured=cured,
            ceiling_binding=False,
            ceiling_shortfall=0,
            method_used="remedial",
            remedial_income_alloc=remedial_income_alloc,
            remedial_deduction_alloc=remedial_deduction_alloc,
            remedial_net=remedial_net,
        )

    def _handle_sale(
        self, prop: ContributedProperty, year: int, sale_price: int
    ) -> PropertyYearResult:
        weights = self.p.interest_weights()
        partners = self.p.ordered_partners()

        book_basis = self._book_basis[prop.code]
        tax_basis = self._tax_basis[prop.code]
        book_gain = sale_price - book_basis      # signed
        tax_gain = sale_price - tax_basis        # signed; the actual tax item
        layer_open = self._layer[prop.code]

        book_gain_list = _allocate(book_gain, weights)
        book_gain_alloc = {p.code: a for p, a in zip(partners, book_gain_list)}

        ceiling_binding = False
        ceiling_shortfall = 0
        tax_gain_alloc = {p.code: 0 for p in partners}

        if layer_open >= 0:
            # Built-in GAIN: contributor taxed on the remaining layer first;
            # ceiling caps it at the actual tax gain available.
            contrib_704c = min(layer_open, max(tax_gain, 0))
            if layer_open > contrib_704c:
                ceiling_binding = True
                ceiling_shortfall = layer_open - contrib_704c
            residual = tax_gain - contrib_704c
            residual_alloc = _allocate(residual, weights) if residual else [0] * len(partners)
            for partner, amt in zip(partners, residual_alloc):
                tax_gain_alloc[partner.code] = amt
            tax_gain_alloc[prop.contributor] += contrib_704c
        else:
            # Built-in LOSS: contributor absorbs the remaining built-in loss
            # first (negative layer), capped by actual tax loss available.
            contrib_704c = max(layer_open, min(tax_gain, 0))  # negative
            if layer_open < contrib_704c:
                ceiling_binding = True
                ceiling_shortfall = layer_open - contrib_704c  # negative
            residual = tax_gain - contrib_704c
            residual_alloc = _allocate(residual, weights) if residual else [0] * len(partners)
            for partner, amt in zip(partners, residual_alloc):
                tax_gain_alloc[partner.code] = amt
            tax_gain_alloc[prop.contributor] += contrib_704c

        cured = layer_open
        self._layer[prop.code] = 0
        self._book_basis[prop.code] = 0
        self._tax_basis[prop.code] = 0
        self._sold[prop.code] = True

        return PropertyYearResult(
            property=prop.code,
            year=year,
            contributor=prop.contributor,
            sold=True,
            book_gain=book_gain,
            tax_gain=tax_gain,
            book_gain_alloc=book_gain_alloc,
            tax_gain_alloc=tax_gain_alloc,
            layer_open=layer_open,
            layer_close=0,
            layer_cured=cured,
            ceiling_binding=ceiling_binding,
            ceiling_shortfall=ceiling_shortfall,
        )

    def _cure_layer(self, prop_code: str, book_minus_tax: int) -> int:
        """Move the §704(c) layer toward zero by ``book_minus_tax`` (never flips)."""
        layer = self._layer[prop_code]
        if layer == 0:
            return 0
        if layer > 0:
            cure = max(0, min(book_minus_tax, layer))
            self._layer[prop_code] = layer - cure
            return cure
        cure = min(0, max(book_minus_tax, layer))
        self._layer[prop_code] = layer - cure
        return cure


# ---------------------------------------------------------------------------
# Fictional seed data — Harborview Partners LP
# ---------------------------------------------------------------------------
DEFAULT_SEED = 20240704
DEFAULT_YEARS = 6


def build_partners() -> Dict[str, Partner]:
    """The fictional 50/50 partner roster."""
    partners = [
        Partner(code="ATLAS", name="Atlas Capital LLC", interest_bps=5000),
        Partner(code="BEACON", name="Beacon Equity LLC", interest_bps=5000),
    ]
    return {p.code: p for p in partners}


def build_properties() -> Dict[str, ContributedProperty]:
    """Contributed property: Atlas's appreciated building + Beacon's cash.

    Atlas contributes appreciated, already-partly-depreciated property: FMV
    1,200,000 but only 300,000 of tax basis. With a 6-year book life and a
    6-year tax life on the much smaller tax basis, annual book depreciation
    (200,000) far exceeds annual tax depreciation (50,000) — the classic setup
    where the traditional method's ceiling rule binds.
    """
    properties = [
        ContributedProperty(
            code="HARBOR_BLDG",
            name="Harborview mixed-use building",
            contributor="ATLAS",
            fmv_cents=to_cents(1_200_000),
            tax_basis_cents=to_cents(300_000),
            depreciable=True,
            book_life_years=6,   # book depreciation = 200,000 / yr
            tax_life_years=6,    # tax depreciation  =  50,000 / yr
        ),
        ContributedProperty(
            code="BEACON_CASH",
            name="Beacon cash contribution",
            contributor="BEACON",
            fmv_cents=to_cents(1_200_000),
            tax_basis_cents=to_cents(1_200_000),
            depreciable=False,
        ),
    ]
    return {p.code: p for p in properties}


def build_property_years(years: List[int]) -> Dict[tuple[str, int], PropertyYear]:
    """The building is sold in the final modelled year to trigger the catch-up."""
    sale_year = max(years)
    return {
        ("HARBOR_BLDG", sale_year): PropertyYear(
            property="HARBOR_BLDG",
            year=sale_year,
            sold=True,
            sale_price_cents=to_cents(700_000),
        )
    }


def build_partnership_years(years: List[int]) -> Dict[int, PartnershipYear]:
    """A steady fictional operating profit and distribution each year."""
    return {
        year: PartnershipYear(
            year=year,
            ordinary_income_cents=to_cents(180_000),
            cash_distribution_cents=to_cents(120_000),
        )
        for year in years
    }


def generate_partnership(
    n_years: int = DEFAULT_YEARS,
    seed: int = DEFAULT_SEED,
    method: str = "traditional",
) -> Partnership:
    """Generate the deterministic fictional Harborview Partners LP.

    The ``seed`` is accepted for interface parity; the figures are fixed so the
    worked example and the tests stay reproducible. ``method`` selects the
    §704(c) allocation method ('traditional' or 'remedial'); it defaults to
    'traditional' so the canonical demo is unchanged.
    """
    if n_years < 1:
        raise ValueError("n_years must be >= 1")
    years = list(range(1, n_years + 1))
    return Partnership(
        code="HARBORVIEW_LP",
        name="Harborview Partners LP",
        partners=build_partners(),
        properties=build_properties(),
        property_years=build_property_years(years),
        partnership_years=build_partnership_years(years),
        years=years,
        method=method,
    )


# ---------------------------------------------------------------------------
# Reporting — Markdown artifacts
# ---------------------------------------------------------------------------
def _gather_partner_rows(
    results: List[YearResult], partner_code: str
) -> List[PartnerYearResult]:
    return [pr for yr in results for pr in yr.partners if pr.partner == partner_code]


def _gather_property_rows(
    results: List[YearResult], prop_code: str
) -> List[PropertyYearResult]:
    return [pr for yr in results for pr in yr.properties if pr.property == prop_code]


def partner_k1(
    partnership: Partnership,
    results: List[YearResult],
    formation: Dict[str, CapitalAccount],
    partner_code: str,
) -> str:
    """Render a partner's Schedule K-1-style capital analysis (Markdown).

    Shows beginning, contributions, share of income/(loss), distributions, and
    ending capital on BOTH a §704(b) book basis and a tax basis, plus the
    §704(c) built-in gain/(loss) the partner carries.
    """
    partner = partnership.partners[partner_code]
    rows = _gather_partner_rows(results, partner_code)
    form = formation[partner_code]
    pct = partner.interest_bps / 100.0

    big = sum(
        p.built_in_gain_cents
        for p in partnership.properties.values()
        if p.contributor == partner_code
    )

    out: List[str] = []
    out.append(f"# Schedule K-1 §704(c) Capital Analysis — {partner.name} [FICTIONAL]")
    out.append("")
    out.append(
        "> Invented partner and amounts for demonstration. Implements the public "
        "US partnership-tax framework (Form 1065, IRC §704(b)/§704(c), traditional "
        "method) generically; not real methodology or figures."
    )
    out.append("")
    out.append(
        f"**Partnership:** {partnership.name} &nbsp;·&nbsp; "
        f"**Profit/loss interest:** {pct:.2f}% &nbsp;·&nbsp; "
        f"**§704(c) built-in gain/(loss) at formation:** {fmt(big)}"
    )
    out.append("")

    out.append("## Capital account on a §704(b) book basis")
    out.append("")
    out.append(
        "| FY | Beginning | + Contributions | + Income/(loss) | - Distributions | Ending |"
    )
    out.append("|----|----------:|----------------:|----------------:|----------------:|-------:|")
    out.append(
        f"| 0 (formation) | {fmt(0)} | {fmt(form.book_cents)} | {fmt(0)} | "
        f"{fmt(0)} | {fmt(form.book_cents)} |"
    )
    for r in rows:
        out.append(
            f"| {r.year} | {fmt(r.book_open)} | {fmt(r.contribution_book)} | "
            f"{fmt(r.income_book)} | {fmt(r.distribution)} | {fmt(r.book_close)} |"
        )
    out.append("")

    out.append("## Capital account on a tax basis")
    out.append("")
    out.append(
        "| FY | Beginning | + Contributions | + Income/(loss) | - Distributions | Ending |"
    )
    out.append("|----|----------:|----------------:|----------------:|----------------:|-------:|")
    out.append(
        f"| 0 (formation) | {fmt(0)} | {fmt(form.tax_cents)} | {fmt(0)} | "
        f"{fmt(0)} | {fmt(form.tax_cents)} |"
    )
    for r in rows:
        out.append(
            f"| {r.year} | {fmt(r.tax_open)} | {fmt(r.contribution_tax)} | "
            f"{fmt(r.income_tax)} | {fmt(r.distribution)} | {fmt(r.tax_close)} |"
        )
    out.append("")

    out.append("## §704(c) effect — book vs. tax disparity over time")
    out.append("")
    out.append("| FY | Book capital | Tax capital | Book - Tax disparity |")
    out.append("|----|-------------:|------------:|---------------------:|")
    out.append(
        f"| 0 (formation) | {fmt(form.book_cents)} | {fmt(form.tax_cents)} | "
        f"{fmt(form.book_cents - form.tax_cents)} |"
    )
    for r in rows:
        out.append(
            f"| {r.year} | {fmt(r.book_close)} | {fmt(r.tax_close)} | "
            f"{fmt(r.book_close - r.tax_close)} |"
        )
    out.append("")
    out.append(
        "_The disparity opens at the §704(c) built-in gain/(loss) the partner "
        "contributed and narrows over time as the traditional method shifts tax "
        "items between partners. Where the **ceiling rule** binds (see the summary), "
        "the disparity may **not** close fully until the property is sold — that "
        "residual is the traditional-method distortion the model surfaces rather "
        "than cures._"
    )
    out.append("")
    return "\n".join(out)


def partnership_summary(
    partnership: Partnership,
    results: List[YearResult],
    formation: Dict[str, CapitalAccount],
) -> str:
    """Render the §704(c) summary (Markdown).

    Includes contributed property with BIG, the §704(c) layer roll-forward per
    property (ceiling rule flagged), a book-vs-tax capital reconciliation, and a
    tax-basis balance sheet (assets = liabilities + tax capital).
    """
    partners = partnership.ordered_partners()
    final = results[-1]
    final_by_partner = {pr.partner: pr for pr in final.partners}

    out: List[str] = []
    out.append(f"# §704(c) Built-In Gain Summary — {partnership.name} [FICTIONAL]")
    out.append("")
    out.append(
        "> Invented partnership and amounts for demonstration. Implements the "
        "public US partnership-tax framework (Form 1065, IRC §704(b)/§704(c), "
        "traditional method with the ceiling rule) generically; not real "
        "methodology or figures."
    )
    out.append("")
    out.append(
        "> **Method limitation (by design):** only the §704(c) *traditional "
        "method* is modelled. The *remedial* and *curative* methods of Reg. "
        "§1.704-3 are **not** implemented; where the ceiling rule binds, the "
        "resulting distortion is **surfaced**, not cured."
    )
    out.append("")

    out.append("## Contributed property at formation")
    out.append("")
    out.append(
        "| Property | Contributor | §704(b) book (FMV) | Tax basis | "
        "Built-in gain/(loss) |"
    )
    out.append("|----------|-------------|-------------------:|----------:|---------------------:|")
    for prop in partnership.ordered_properties():
        contributor = partnership.partners[prop.contributor].name
        out.append(
            f"| {prop.name} | {contributor} | {fmt(prop.fmv_cents)} | "
            f"{fmt(prop.tax_basis_cents)} | {fmt(prop.built_in_gain_cents)} |"
        )
    out.append("")

    out.append("## §704(c) built-in gain/(loss) layer roll-forward")
    out.append("")
    out.append(
        "| Property | FY | Book dep | Tax dep | Book gain | Tax gain | "
        "Layer (open -> close) | Ceiling? |"
    )
    out.append("|----------|----|---------:|--------:|----------:|---------:|:--------------------|:--------:|")
    for prop in partnership.ordered_properties():
        if not prop.depreciable:
            continue
        for r in _gather_property_rows(results, prop.code):
            ceiling = (
                f"BINDING short {fmt(r.ceiling_shortfall)}" if r.ceiling_binding else "-"
            )
            layer = f"{fmt(r.layer_open)} -> {fmt(r.layer_close)}"
            out.append(
                f"| {prop.code} | {r.year} | {fmt(r.book_depreciation)} | "
                f"{fmt(r.tax_depreciation)} | {fmt(r.book_gain)} | "
                f"{fmt(r.tax_gain)} | {layer} | {ceiling} |"
            )
    out.append("")
    out.append(
        "_**BINDING** = the ceiling rule was binding: actual tax depreciation was "
        "less than the non-contributing partners' share of book depreciation, so "
        "they were capped at the available tax item and the contributing partner "
        "received none. Under the traditional method this distortion is left in "
        "place; the residual built-in gain is caught up to the contributor on "
        "sale._"
    )
    out.append("")

    out.append("## Book vs. tax capital reconciliation (ending)")
    out.append("")
    out.append("| Partner | §704(b) book capital | Tax capital | Book - Tax |")
    out.append("|---------|---------------------:|------------:|-----------:|")
    tot_book = tot_tax = 0
    for partner in partners:
        pr = final_by_partner[partner.code]
        tot_book += pr.book_close
        tot_tax += pr.tax_close
        out.append(
            f"| {partner.name} | {fmt(pr.book_close)} | {fmt(pr.tax_close)} | "
            f"{fmt(pr.book_close - pr.tax_close)} |"
        )
    out.append(
        f"| **Total** | **{fmt(tot_book)}** | **{fmt(tot_tax)}** | "
        f"**{fmt(tot_book - tot_tax)}** |"
    )
    out.append("")

    cash = _final_cash(partnership, results)
    property_basis = sum(_final_property_tax_basis(partnership, results).values())
    total_assets = cash + property_basis

    out.append("## Tax-basis balance sheet (ending)")
    out.append("")
    out.append("| Assets | Amount | | Liabilities & capital | Amount |")
    out.append("|--------|-------:|---|----------------------|-------:|")
    out.append(f"| Cash | {fmt(cash)} | | Liabilities | {fmt(0)} |")
    out.append(
        f"| Property (adj. tax basis) | {fmt(property_basis)} | | "
        f"Tax capital | {fmt(tot_tax)} |"
    )
    out.append(
        f"| **Total assets** | **{fmt(total_assets)}** | | "
        f"**Total liab. & capital** | **{fmt(tot_tax)}** |"
    )
    out.append("")
    balanced = "balances" if total_assets == tot_tax else "OUT OF BALANCE"
    out.append(
        f"_Tax-basis balance sheet {balanced}: assets ({fmt(total_assets)}) = "
        f"liabilities (0) + tax capital ({fmt(tot_tax)})._"
    )
    out.append("")
    return "\n".join(out)


def _final_property_tax_basis(
    partnership: Partnership, results: List[YearResult]
) -> Dict[str, int]:
    """Reconstruct ending adjusted tax basis per depreciable property."""
    basis: Dict[str, int] = {}
    sold: Dict[str, bool] = {}
    for prop in partnership.properties.values():
        if prop.depreciable:
            basis[prop.code] = prop.tax_basis_cents
            sold[prop.code] = False
    for yr in results:
        for pr in yr.properties:
            if pr.property not in basis:
                continue
            if pr.sold:
                basis[pr.property] = 0
                sold[pr.property] = True
            elif not sold[pr.property]:
                basis[pr.property] -= pr.tax_depreciation
    return basis


def _final_cash(partnership: Partnership, results: List[YearResult]) -> int:
    """Reconstruct the partnership's ending cash on a tax basis."""
    cash = sum(
        p.tax_basis_cents
        for p in partnership.properties.values()
        if not p.depreciable
    )
    for yr in results:
        py = partnership.partnership_year(yr.year)
        cash += py.ordinary_income_cents
        cash -= py.cash_distribution_cents
        for pr in yr.properties:
            if pr.sold:
                cash += partnership.property_year(pr.property, pr.year).sale_price_cents
    return cash


def build_reports(partnership: Partnership) -> Dict[str, str]:
    """Run the §704(c) engine and render every Markdown artifact, by filename."""
    eng = Section704cEngine(partnership)
    formation = eng.formation_capital()
    results = eng.run()
    artifacts: Dict[str, str] = {}
    for code in partnership.partners:
        artifacts[f"section704c_k1_{code}.md"] = partner_k1(
            partnership, results, formation, code
        )
    artifacts["section704c_summary.md"] = partnership_summary(
        partnership, results, formation
    )
    return artifacts


def run_demo(out_dir, n_years: int = DEFAULT_YEARS, seed: int = DEFAULT_SEED):
    """Build the Harborview §704(c) demo and write artifacts to ``out_dir``.

    Writes ``section704c_summary.md`` plus one ``section704c_k1_<PARTNER>.md`` per
    partner. Returns ``(partnership, written_paths)``.
    """
    from pathlib import Path

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    partnership = generate_partnership(n_years=n_years, seed=seed)
    artifacts = build_reports(partnership)
    written = []
    # Write the summary first, then the K-1s, for stable ordering.
    for filename in ["section704c_summary.md"] + sorted(
        k for k in artifacts if k.startswith("section704c_k1_")
    ):
        path = out_path / filename
        path.write_text(artifacts[filename], encoding="utf-8")
        written.append(path)
    return partnership, written
