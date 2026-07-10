"""Core data model for the partnership-tax (§704(c)) engine.

These dataclasses describe a *fictional* US partnership (Form 1065), its
partners, the property each partner contributes at formation, and the per-year
facts that flow into the §704(b) book vs. tax capital and §704(c) built-in
gain/loss (BIG/BIL) calculations.

Two parallel capital accounts are maintained for every partner:

* **§704(b) book capital** — credited at the *fair market value* of what the
  partner contributes, and adjusted each year by the partner's share of *book*
  items (book depreciation, book gain/loss on sale).
* **tax capital** (outside-basis-style inside accounting) — credited at the
  *tax basis* of what the partner contributes, and adjusted by the partner's
  share of *tax* items.

The initial book-minus-tax disparity per partner equals the built-in gain/loss
on the property they contributed. §704(c) governs how the partnership's *tax*
items are allocated so as to take that disparity into account.

Conventions
-----------
* All monetary amounts are stored as **integer cents** (see :mod:`.money`).
* Ownership / profit-sharing interests are stored as integer **basis points**
  (``5000`` == 50.00%) so allocations sum exactly to 100%.
* Built-in gain (BIG) is positive (FMV > tax basis); built-in loss (BIL) is
  negative. The §704(c) "layer" tracked per property is signed the same way and
  is amortised toward zero — never flipping sign.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Basis-point scale: 10000 bps == 100.00%.
BPS_SCALE = 10000


@dataclass(frozen=True)
class Partner:
    """A partner in the fictional partnership.

    Attributes
    ----------
    code:
        Short stable identifier (e.g. ``"ATLAS"``).
    name:
        Display name — always an obviously fake entity name.
    interest_bps:
        Agreed profit/loss-sharing interest in basis points (e.g. ``5000`` for
        50.00%). Book items are allocated by this interest. Across all partners
        these must sum to ``BPS_SCALE``.
    """

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
    """A single property contributed by one partner at formation (year 0).

    Cash contributions are modelled as a property with equal FMV and tax basis,
    no depreciable life, and therefore zero built-in gain/loss.

    Attributes
    ----------
    code:
        Stable identifier for the property (e.g. ``"WAREHOUSE"``).
    name:
        Display name (e.g. ``"Distribution warehouse"``).
    contributor:
        ``code`` of the contributing :class:`Partner`.
    fmv_cents:
        §704(b) book value on contribution = fair market value, in cents.
    tax_basis_cents:
        Carryover tax basis on contribution, in cents.
    depreciable:
        ``True`` for depreciable property that generates book/tax depreciation.
        Cash and non-depreciable property are ``False``.
    book_life_years:
        Remaining book recovery period at contribution (straight-line). Ignored
        if ``depreciable`` is ``False``.
    tax_life_years:
        Remaining tax recovery period at contribution (straight-line over the
        carryover tax basis). Often *shorter* than ``book_life_years`` for
        previously-depreciated property — which is exactly what creates the
        ceiling-rule pressure under the traditional method.
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
        if self.depreciable:
            if self.book_life_years < 1 or self.tax_life_years < 1:
                raise ValueError(
                    f"{self.code}: depreciable property needs book/tax lives >= 1"
                )

    @property
    def built_in_gain_cents(self) -> int:
        """Built-in gain/(loss) at formation = FMV - tax basis (signed)."""
        return self.fmv_cents - self.tax_basis_cents

    @property
    def is_cash(self) -> bool:
        """Cash is non-depreciable property with no book/tax disparity."""
        return not self.depreciable and self.built_in_gain_cents == 0


@dataclass(frozen=True)
class PropertyYear:
    """Per-property, per-year operating facts.

    Attributes
    ----------
    property: ``code`` of the :class:`ContributedProperty`.
    year:     Fiscal year (relative; ``1`` is the first full year after
              formation).
    sold:     ``True`` if the property is sold during this year. When sold, no
              depreciation is taken in the sale year and the remaining §704(c)
              layer is triggered into gain/loss.
    sale_price_cents:
              Gross sale proceeds in cents (only meaningful when ``sold``).
    """

    property: str
    year: int
    sold: bool = False
    sale_price_cents: int = 0

    def __post_init__(self) -> None:
        if self.sale_price_cents < 0:
            raise ValueError(f"{self.property}: sale price must be >= 0")


@dataclass(frozen=True)
class PartnershipYear:
    """Per-partnership, per-year operating facts (not tied to a property).

    Attributes
    ----------
    year:
        Fiscal year.
    ordinary_income_cents:
        Ordinary operating income/(loss) for the year before depreciation, in
        cents. Signed. Allocated among partners by interest %.
    cash_distribution_cents:
        Total cash distributed pro-rata to partners during the year, in cents.
        Reduces both book and tax capital by each partner's interest share.
    """

    year: int
    ordinary_income_cents: int = 0
    cash_distribution_cents: int = 0


@dataclass
class CapitalAccount:
    """A single partner's running book and tax capital, in cents.

    Tracked as a mutable roll-forward container: closing balances of year *N*
    become opening balances of year *N+1*.
    """

    book_cents: int = 0
    tax_cents: int = 0

    def copy(self) -> "CapitalAccount":
        return CapitalAccount(book_cents=self.book_cents, tax_cents=self.tax_cents)


@dataclass
class Partnership:
    """The full fictional partnership: partners, properties, and per-year facts.

    Attributes
    ----------
    code/name:
        Identifier and display name of the partnership.
    partners:
        Mapping of partner ``code`` -> :class:`Partner`.
    properties:
        Mapping of property ``code`` -> :class:`ContributedProperty`.
    property_years:
        Mapping of ``(property_code, year)`` -> :class:`PropertyYear`.
    partnership_years:
        Mapping of ``year`` -> :class:`PartnershipYear`.
    years:
        Sorted list of fiscal years to roll forward (``1..N``).
    """

    code: str
    name: str
    partners: Dict[str, Partner]
    properties: Dict[str, ContributedProperty]
    property_years: Dict[tuple[str, int], PropertyYear]
    partnership_years: Dict[int, PartnershipYear]
    years: List[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        total_bps = sum(p.interest_bps for p in self.partners.values())
        if total_bps != BPS_SCALE:
            raise ValueError(
                f"partner interests must sum to {BPS_SCALE} bps (100%); "
                f"got {total_bps}"
            )
        for prop in self.properties.values():
            if prop.contributor not in self.partners:
                raise ValueError(
                    f"property {prop.code} contributed by unknown partner "
                    f"{prop.contributor!r}"
                )

    def ordered_partners(self) -> List[Partner]:
        """Partners in a stable display order (by code)."""
        return [self.partners[c] for c in sorted(self.partners)]

    def ordered_properties(self) -> List[ContributedProperty]:
        """Properties in a stable display order (by code)."""
        return [self.properties[c] for c in sorted(self.properties)]

    def interest_weights(self) -> List[int]:
        """Interest weights (bps) aligned with :meth:`ordered_partners`."""
        return [p.interest_bps for p in self.ordered_partners()]

    def property_year(self, prop_code: str, year: int) -> PropertyYear:
        """Facts for a property in a year (a quiet, non-sale year if absent)."""
        key = (prop_code, year)
        if key in self.property_years:
            return self.property_years[key]
        return PropertyYear(property=prop_code, year=year)

    def partnership_year(self, year: int) -> PartnershipYear:
        """Partnership-level facts for a year (zero activity if absent)."""
        if year in self.partnership_years:
            return self.partnership_years[year]
        return PartnershipYear(year=year)
