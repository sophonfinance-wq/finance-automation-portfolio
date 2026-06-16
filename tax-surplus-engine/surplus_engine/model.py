"""Core data model for the tax-surplus engine.

These dataclasses describe the *fictional* multi-tier structure and the per-year
facts that flow into the surplus / ACB calculation. Keeping them as plain,
typed, frozen-where-possible dataclasses makes the engine deterministic and easy
to test.

Conventions
-----------
* All monetary amounts are stored in the entity's *functional currency* (its
  reporting currency, ``USD`` or ``CAD``) until the Summary layer converts to
  CAD via the :class:`FxTable`.
* A *distribution* is expressed as a positive number (the cash paid up to the
  owner). The waterfall consumes pools by that positive amount.
* Pool balances are never allowed to go negative; the waterfall caps draws at
  the available balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Surplus pool identifiers, in the statutory consumption order used by the
# distribution waterfall (Reg. 5907(1) ordering, simplified for the model).
EXEMPT = "exempt_surplus"
TAXABLE = "taxable_surplus"
PREACQ = "pre_acquisition_capital"

POOL_ORDER: tuple[str, ...] = (EXEMPT, TAXABLE, PREACQ)


@dataclass(frozen=True)
class Entity:
    """A node in the fictional ownership tree.

    Attributes
    ----------
    code:
        Short stable identifier (e.g. ``"BIRCH_OP"``).
    name:
        Display name — always an obviously fake name.
    tier:
        ``0`` = operating project (bottom), increasing up to the top holdco.
    currency:
        Functional currency of the entity (``"USD"`` or ``"CAD"``).
    parent:
        ``code`` of the immediate owner, or ``None`` for the top holdco.
    ownership_pct:
        Fraction (0..1) of this entity owned by ``parent``. The top holdco has
        ``1.0`` and no parent.
    """

    code: str
    name: str
    tier: int
    currency: str
    parent: Optional[str]
    ownership_pct: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.ownership_pct <= 1.0:
            raise ValueError(
                f"ownership_pct for {self.code} must be in [0,1], got {self.ownership_pct}"
            )
        if self.parent is None and self.ownership_pct != 1.0:
            raise ValueError(f"top entity {self.code} must have ownership_pct 1.0")


@dataclass(frozen=True)
class YearFacts:
    """Per-entity, per-year *standalone* facts (the cited evidence inputs).

    These correspond to the "Evidence" layer in the workpaper lineage: cited,
    hardcoded inputs that everything else is derived from.

    Attributes
    ----------
    entity:
        ``code`` of the entity.
    year:
        Fiscal year (e.g. ``2023``).
    standalone_taxable_income:
        Standalone taxable income for the year, functional currency. May be
        negative (a loss).
    reg_5907_2_adjustment:
        Net Reg. 5907(2)-style book-tax adjustment, functional currency. Signed
        (negative reduces surplus).
    exempt_portion:
        Fraction (0..1) of the post-adjustment current-year surplus that is
        *exempt* surplus; the remainder is taxable surplus.
    distribution:
        Cash distributed (paid up to the owner) during the year, functional
        currency. Positive. ``0`` if none.
    capital_contribution:
        Capital contributed *down* into this entity by its owner during the
        year (an ACB-increasing event), functional currency. Positive.
    return_of_capital:
        Portion of ``distribution`` that is characterised as a return of
        capital / pre-acquisition distribution (an ACB-decreasing event at the
        owner level), functional currency. Positive, and ``<= distribution``.
    """

    entity: str
    year: int
    standalone_taxable_income: float
    reg_5907_2_adjustment: float
    exempt_portion: float
    distribution: float
    capital_contribution: float
    return_of_capital: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.exempt_portion <= 1.0:
            raise ValueError(
                f"exempt_portion must be in [0,1], got {self.exempt_portion}"
            )
        if self.distribution < 0 or self.capital_contribution < 0 or self.return_of_capital < 0:
            raise ValueError("distribution / contribution / return_of_capital must be >= 0")
        if self.return_of_capital > self.distribution + 1e-9:
            raise ValueError("return_of_capital cannot exceed distribution")


@dataclass
class PoolBalances:
    """Cumulative surplus pool balances plus ACB for one entity.

    Used both as opening and closing balances during roll-forward.
    """

    exempt_surplus: float = 0.0
    taxable_surplus: float = 0.0
    pre_acquisition_capital: float = 0.0
    acb: float = 0.0

    def copy(self) -> "PoolBalances":
        return PoolBalances(
            exempt_surplus=self.exempt_surplus,
            taxable_surplus=self.taxable_surplus,
            pre_acquisition_capital=self.pre_acquisition_capital,
            acb=self.acb,
        )

    def get(self, pool: str) -> float:
        return getattr(self, pool)

    def add(self, pool: str, amount: float) -> None:
        setattr(self, pool, getattr(self, pool) + amount)


@dataclass
class Structure:
    """The full fictional structure: entities + per-(entity,year) facts + FX."""

    entities: Dict[str, Entity]
    facts: Dict[tuple[str, int], YearFacts]
    fx: "FxTable"
    years: List[int] = field(default_factory=list)

    def children_of(self, code: str) -> List[Entity]:
        """Return the direct subsidiaries of ``code`` (bottom-up elevation)."""
        return [e for e in self.entities.values() if e.parent == code]

    def ordered_bottom_up(self) -> List[Entity]:
        """Entities sorted by tier ascending (process subsidiaries first)."""
        return sorted(self.entities.values(), key=lambda e: (e.tier, e.code))


@dataclass(frozen=True)
class FxTable:
    """Fictional USD->CAD FX table, keyed by year.

    CAD is treated as the reporting currency; an entity whose functional
    currency is already CAD uses a rate of ``1.0``.
    """

    usd_cad: Dict[int, float]

    def rate(self, year: int, currency: str) -> float:
        """Rate to convert ``currency`` into CAD for ``year``."""
        if currency == "CAD":
            return 1.0
        if currency != "USD":
            raise ValueError(f"unsupported currency {currency!r}")
        if year not in self.usd_cad:
            raise KeyError(f"no FX rate for year {year}")
        return self.usd_cad[year]
