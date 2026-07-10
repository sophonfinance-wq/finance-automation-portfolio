"""Shared test fixtures and helpers.

Builds small, hand-controlled partnerships so each §704(c) behaviour can be
asserted in isolation, independent of the canonical generator.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from partnership_engine.model import (
    ContributedProperty,
    Partner,
    Partnership,
    PartnershipYear,
    PropertyYear,
)
from partnership_engine.money import to_cents


def make_partner(code: str, interest_bps: int, name: Optional[str] = None) -> Partner:
    return Partner(code=code, name=name or f"{code} Demo LLC", interest_bps=interest_bps)


def make_property(
    code: str,
    contributor: str,
    fmv: float,
    tax_basis: float,
    depreciable: bool = False,
    book_life: int = 0,
    tax_life: int = 0,
    name: Optional[str] = None,
) -> ContributedProperty:
    return ContributedProperty(
        code=code,
        name=name or f"{code} property",
        contributor=contributor,
        fmv_cents=to_cents(fmv),
        tax_basis_cents=to_cents(tax_basis),
        depreciable=depreciable,
        book_life_years=book_life,
        tax_life_years=tax_life,
    )


def make_partnership(
    partners: List[Partner],
    properties: List[ContributedProperty],
    n_years: int = 1,
    property_years: Optional[List[PropertyYear]] = None,
    partnership_years: Optional[List[PartnershipYear]] = None,
) -> Partnership:
    years = list(range(1, n_years + 1))
    py_map: Dict[tuple[str, int], PropertyYear] = {
        (p.property, p.year): p for p in (property_years or [])
    }
    pn_map: Dict[int, PartnershipYear] = {p.year: p for p in (partnership_years or [])}
    return Partnership(
        code="TEST_LP",
        name="Test Partners LP",
        partners={p.code: p for p in partners},
        properties={p.code: p for p in properties},
        property_years=py_map,
        partnership_years=pn_map,
        years=years,
    )


@pytest.fixture
def two_partner_factory():
    """Factory: a 50/50 partnership where ATLAS contributes a building and
    BEACON contributes cash. Lives, prices and years are caller-controlled so a
    test can dial the ceiling rule in or out.
    """

    def _factory(
        fmv: float,
        tax_basis: float,
        book_life: int,
        tax_life: int,
        cash: float,
        n_years: int = 1,
        sale_year: Optional[int] = None,
        sale_price: float = 0.0,
        atlas_bps: int = 5000,
    ) -> Partnership:
        partners = [
            make_partner("ATLAS", atlas_bps),
            make_partner("BEACON", 10000 - atlas_bps),
        ]
        properties = [
            make_property(
                "BLDG", "ATLAS", fmv, tax_basis,
                depreciable=True, book_life=book_life, tax_life=tax_life,
            ),
            make_property("CASH", "BEACON", cash, cash, depreciable=False),
        ]
        property_years = []
        if sale_year is not None:
            property_years.append(
                PropertyYear(
                    property="BLDG", year=sale_year, sold=True,
                    sale_price_cents=to_cents(sale_price),
                )
            )
        return make_partnership(
            partners, properties, n_years=n_years, property_years=property_years
        )

    return _factory
