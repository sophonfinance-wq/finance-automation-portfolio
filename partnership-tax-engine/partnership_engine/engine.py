"""The §704(c) partnership-tax calculation engine (traditional method).

This module is the showpiece. Given a :class:`~partnership_engine.model.Partnership`
it computes — deterministically, in integer cents — for each fiscal year:

1. **Book vs. tax depreciation** on each contributed depreciable property:
   book depreciation is straight-line over the book life on the §704(b) book
   value (FMV); tax depreciation is straight-line over the tax life on the
   carryover tax basis.
2. **§704(c) traditional-method tax allocations** on each property:
   * *Book* items (book depreciation; book gain/loss on sale) are allocated to
     partners by their agreed interest %.
   * *Tax* depreciation is allocated FIRST to the **non-contributing** partners,
     up to their share of book depreciation, to cure the book-tax disparity; the
     **contributing** partner receives whatever tax depreciation remains.
   * **Ceiling rule.** The total tax item allocated can never exceed the actual
     tax item available. If actual tax depreciation is *less* than the
     non-contributing partners' book-depreciation share, they are capped at the
     available tax depreciation (a ceiling-rule distortion): the contributing
     partner gets zero, and the disparity is only partially cured this year.
     The engine flags this on the per-year, per-property record.
3. **On sale**: book gain/(loss) is allocated by interest %; for tax, the
   remaining §704(c) built-in gain is allocated entirely to the contributing
   partner to the extent it remains, and any residual tax gain/(loss) is then
   allocated by interest %. The ceiling rule still applies.
4. **§704(c) layer roll-forward**: the remaining built-in gain/(loss) starts at
   FMV − tax basis and is amortised toward zero as the book/tax depreciation
   difference cures it (and is fully cleared on sale). It never flips sign.
5. **Capital-account roll-forward**: per partner, both §704(b) book and tax
   capital are rolled forward (contributions, share of income/(loss),
   distributions) so a Schedule K-1-style analysis can be produced on both
   bases.

LIMITATION (documented on purpose): only the **traditional method** is
implemented. The remedial and curative allocation methods of Reg. §1.704-3 are
NOT implemented; where the ceiling rule bites, the resulting distortion is
*surfaced* rather than cured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .model import (
    BPS_SCALE,
    CapitalAccount,
    ContributedProperty,
    Partnership,
)
from .money import allocate_by_ratio, split_evenly


def _other_weights(partnership: Partnership, contributor: str) -> List[int]:
    """Interest weights (bps) renormalised over the NON-contributing partners.

    Used to split a pooled non-contributor amount among those partners in
    proportion to their interests. If the non-contributors hold no interest at
    all (degenerate), falls back to an equal split.
    """
    partners = partnership.ordered_partners()
    others = [p for p in partners if p.code != contributor]
    total = sum(p.interest_bps for p in others)
    if total == 0:
        n = len(others)
        base = [BPS_SCALE // n] * n
        base[-1] += BPS_SCALE - sum(base)
        return base
    # Renormalise to exactly BPS_SCALE using the Hamilton method on a dummy.
    weights = [round(p.interest_bps * BPS_SCALE / total) for p in others]
    # Fix any rounding drift on the largest interest.
    drift = BPS_SCALE - sum(weights)
    if drift and weights:
        idx = max(range(len(others)), key=lambda i: others[i].interest_bps)
        weights[idx] += drift
    return weights


@dataclass
class PropertyYearResult:
    """§704(c) result for one property in one fiscal year.

    All amounts are integer cents. ``tax_alloc`` / ``book_alloc`` are keyed by
    partner code. A positive depreciation figure is the *deduction* amount
    (it reduces capital); gains on sale are positive, losses negative.
    """

    property: str
    year: int
    contributor: str
    sold: bool = False

    # --- Book vs. tax items (partnership totals) ---
    book_depreciation: int = 0
    tax_depreciation: int = 0
    book_gain: int = 0            # on sale only
    tax_gain: int = 0            # on sale only (actual tax item available)

    # --- Per-partner allocations (deductions negative? no: stored positive,
    #     applied with sign by the capital roll-forward) ---
    book_dep_alloc: Dict[str, int] = field(default_factory=dict)
    tax_dep_alloc: Dict[str, int] = field(default_factory=dict)
    book_gain_alloc: Dict[str, int] = field(default_factory=dict)
    tax_gain_alloc: Dict[str, int] = field(default_factory=dict)

    # --- §704(c) layer ---
    layer_open: int = 0
    layer_close: int = 0
    layer_cured: int = 0          # amount the disparity moved toward zero

    # --- Ceiling rule ---
    ceiling_binding: bool = False
    ceiling_shortfall: int = 0    # book share the non-contributors could NOT get


@dataclass
class PartnerYearResult:
    """Capital-account movement for one partner in one fiscal year (cents)."""

    partner: str
    year: int
    book_open: int = 0
    tax_open: int = 0
    contribution_book: int = 0
    contribution_tax: int = 0
    income_book: int = 0          # share of book income/(loss), incl. dep & gain
    income_tax: int = 0           # share of tax income/(loss), incl. dep & gain
    distribution: int = 0         # cash distributed (reduces both bases)
    book_close: int = 0
    tax_close: int = 0


@dataclass
class YearResult:
    """Everything computed for the whole partnership in one fiscal year."""

    year: int
    properties: List[PropertyYearResult] = field(default_factory=list)
    partners: List[PartnerYearResult] = field(default_factory=list)


class PartnershipEngine:
    """Stateful engine that rolls a partnership forward across fiscal years."""

    def __init__(self, partnership: Partnership):
        self.p = partnership
        # Running capital accounts, keyed by partner code.
        self._capital: Dict[str, CapitalAccount] = {
            code: CapitalAccount() for code in partnership.partners
        }
        # Remaining §704(c) layer per property (signed), seeded at BIG/BIL.
        self._layer: Dict[str, int] = {
            code: prop.built_in_gain_cents
            for code, prop in partnership.properties.items()
        }
        # Remaining book / tax adjusted bases per property, for sale gain calc.
        self._book_basis: Dict[str, int] = {
            code: prop.fmv_cents for code, prop in partnership.properties.items()
        }
        self._tax_basis: Dict[str, int] = {
            code: prop.tax_basis_cents
            for code, prop in partnership.properties.items()
        }
        self._sold: Dict[str, bool] = {code: False for code in partnership.properties}
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
        they contributed.
        """
        self._apply_formation()
        return {c: acct.copy() for c, acct in self._capital.items()}

    # -- internals --------------------------------------------------------

    def _apply_formation(self) -> None:
        """Credit each partner's book/tax capital for their contribution."""
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

        # Per-partner book/tax income accumulators for the year.
        income_book: Dict[str, int] = {p.code: 0 for p in partners}
        income_tax: Dict[str, int] = {p.code: 0 for p in partners}

        prop_results: List[PropertyYearResult] = []

        # 1) Ordinary operating income/(loss): identical book and tax, by %.
        py = self.p.partnership_year(year)
        if py.ordinary_income_cents:
            parts = allocate_by_ratio(py.ordinary_income_cents, weights)
            for partner, amt in zip(partners, parts):
                income_book[partner.code] += amt
                income_tax[partner.code] += amt

        # 2) Each contributed property: depreciation OR sale.
        for prop in self.p.ordered_properties():
            if not prop.depreciable or self._sold[prop.code]:
                continue
            pyr = self.p.property_year(prop.code, year)
            if pyr.sold:
                res = self._handle_sale(prop, year, pyr.sale_price_cents)
            else:
                res = self._handle_depreciation(prop, year)
            prop_results.append(res)
            # Apply per-partner book/tax effects (depreciation reduces capital;
            # gains increase, losses decrease).
            for code, amt in res.book_dep_alloc.items():
                income_book[code] -= amt
            for code, amt in res.tax_dep_alloc.items():
                income_tax[code] -= amt
            for code, amt in res.book_gain_alloc.items():
                income_book[code] += amt
            for code, amt in res.tax_gain_alloc.items():
                income_tax[code] += amt

        # 3) Cash distribution: pro-rata by interest, reduces both bases.
        dist_parts = (
            allocate_by_ratio(py.cash_distribution_cents, weights)
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
        """Annual straight-line BOOK depreciation on the §704(b) book value."""
        return split_evenly(prop.fmv_cents, prop.book_life_years)[0]

    def _tax_dep_amount(self, prop: ContributedProperty) -> int:
        """Annual straight-line TAX depreciation on the carryover tax basis."""
        return split_evenly(prop.tax_basis_cents, prop.tax_life_years)[0]

    def _handle_depreciation(
        self, prop: ContributedProperty, year: int
    ) -> PropertyYearResult:
        """Allocate one year of book & tax depreciation under §704(c)."""
        weights = self.p.interest_weights()
        partners = self.p.ordered_partners()

        # Available book & tax depreciation this year, capped at remaining basis.
        book_dep = min(self._book_basis[prop.code], self._book_dep_amount(prop))
        tax_dep = min(self._tax_basis[prop.code], self._tax_dep_amount(prop))

        # Book depreciation is allocated to all partners by interest %.
        book_alloc_list = allocate_by_ratio(book_dep, weights)
        book_dep_alloc = {p.code: a for p, a in zip(partners, book_alloc_list)}

        # Non-contributing partners' aggregate share of BOOK depreciation: the
        # target the traditional method tries to cover with tax depreciation.
        noncontrib_book_share = sum(
            a for p, a in book_dep_alloc.items() if p != prop.contributor
        )

        ceiling_binding = False
        ceiling_shortfall = 0
        tax_dep_alloc = {p.code: 0 for p in partners}

        if tax_dep >= noncontrib_book_share:
            # Enough tax depreciation: non-contributors get their full book
            # share; the contributing partner gets the remainder.
            others = [p for p in partners if p.code != prop.contributor]
            other_shares = allocate_by_ratio(
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
            others = [p for p in partners if p.code != prop.contributor]
            other_shares = allocate_by_ratio(
                tax_dep, _other_weights(self.p, prop.contributor)
            )
            for partner, amt in zip(others, other_shares):
                tax_dep_alloc[partner.code] = amt
            tax_dep_alloc[prop.contributor] = 0

        # §704(c) layer movement. The book/tax depreciation difference is what
        # cures the built-in gain/(loss). Cure cannot exceed the remaining
        # layer magnitude, and the layer never flips sign.
        layer_open = self._layer[prop.code]
        cured = self._cure_layer(prop.code, book_dep - tax_dep)
        layer_close = self._layer[prop.code]

        # Reduce remaining bases.
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

    def _handle_sale(
        self, prop: ContributedProperty, year: int, sale_price: int
    ) -> PropertyYearResult:
        """Allocate book & tax gain/(loss) on a sale under §704(c)."""
        weights = self.p.interest_weights()
        partners = self.p.ordered_partners()

        book_basis = self._book_basis[prop.code]
        tax_basis = self._tax_basis[prop.code]
        book_gain = sale_price - book_basis      # signed
        tax_gain = sale_price - tax_basis        # signed; the actual tax item
        layer_open = self._layer[prop.code]

        # Book gain/(loss): allocated to all partners by interest %.
        book_gain_list = allocate_by_ratio(book_gain, weights)
        book_gain_alloc = {p.code: a for p, a in zip(partners, book_gain_list)}

        # Tax gain: first allocate the REMAINING §704(c) built-in gain to the
        # contributing partner, to the extent it remains AND tax gain exists.
        # The ceiling rule caps total allocated tax gain at the actual tax gain.
        ceiling_binding = False
        ceiling_shortfall = 0
        tax_gain_alloc = {p.code: 0 for p in partners}

        if layer_open >= 0:
            # Built-in GAIN: contributor should be taxed on the remaining layer
            # first; ceiling caps it at the actual tax gain available.
            contrib_704c = min(layer_open, max(tax_gain, 0))
            if layer_open > contrib_704c:
                ceiling_binding = True
                ceiling_shortfall = layer_open - contrib_704c
            residual = tax_gain - contrib_704c
            residual_alloc = allocate_by_ratio(residual, weights) if residual else [0] * len(partners)
            for partner, amt in zip(partners, residual_alloc):
                tax_gain_alloc[partner.code] = amt
            tax_gain_alloc[prop.contributor] += contrib_704c
        else:
            # Built-in LOSS: contributor absorbs the remaining built-in loss
            # first (a negative layer), capped by actual tax loss available.
            contrib_704c = max(layer_open, min(tax_gain, 0))  # negative
            if layer_open < contrib_704c:
                ceiling_binding = True
                ceiling_shortfall = layer_open - contrib_704c  # negative shortfall
            residual = tax_gain - contrib_704c
            residual_alloc = allocate_by_ratio(residual, weights) if residual else [0] * len(partners)
            for partner, amt in zip(partners, residual_alloc):
                tax_gain_alloc[partner.code] = amt
            tax_gain_alloc[prop.contributor] += contrib_704c

        # The layer is fully cleared on sale (the built-in gain/loss is realised).
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
        """Move the §704(c) layer toward zero by ``book_minus_tax``.

        For a built-in GAIN (positive layer) faster book depreciation
        (book > tax) cures the gain; the cure is the positive book−tax
        difference, capped at the remaining layer. For a built-in LOSS
        (negative layer) the difference is negative and cures toward zero the
        same way. The layer never crosses zero.
        """
        layer = self._layer[prop_code]
        if layer == 0:
            return 0
        if layer > 0:
            cure = max(0, min(book_minus_tax, layer))
            self._layer[prop_code] = layer - cure
            return cure
        # layer < 0
        cure = min(0, max(book_minus_tax, layer))
        self._layer[prop_code] = layer - cure
        return cure
