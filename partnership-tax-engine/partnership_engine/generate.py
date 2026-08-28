"""Deterministic fictional-data generator for the partnership-tax engine.

Everything here is invented for a portfolio demo. The partnership and partner
names are obviously fake (``Harborview Partners LP``, ``Atlas Capital LLC`` ...),
and the figures are chosen — not random — so the §704(c) mechanics are clean to
read and so the suite can pin an exact **ceiling-rule** case.

The canonical fixture is a two-partner, 50/50 real-estate partnership:

* **Atlas Capital LLC** contributes a fully fictional appreciated, *already
  partly depreciated* building: FMV \\$1,200,000 but only \\$300,000 of tax basis
  left, with a long book life (6 yrs) and a short remaining tax life (6 yrs).
  That makes annual book depreciation (\\$200,000) far exceed annual tax
  depreciation (\\$50,000) — the classic setup where the traditional method's
  ceiling rule binds.
* **Beacon Equity LLC** contributes \\$1,200,000 of cash.

A seeded RNG is accepted for interface parity with the other engines, but the
figures are fixed so the worked example and tests are reproducible.
"""

from __future__ import annotations

import random
from typing import Dict, List

from .model import (
    ContributedProperty,
    Partner,
    Partnership,
    PartnershipYear,
    PropertyYear,
)
from .money import to_cents

# Fixed seed -> identical output every run (kept for interface parity).
DEFAULT_SEED = 20240704

# Number of fiscal years rolled forward after formation.
DEFAULT_YEARS = 6


def build_partners() -> Dict[str, Partner]:
    """Return the fictional 50/50 partner roster."""
    partners = [
        Partner(code="ATLAS", name="Atlas Capital LLC", interest_bps=5000),
        Partner(code="BEACON", name="Beacon Equity LLC", interest_bps=5000),
    ]
    return {p.code: p for p in partners}


def build_properties() -> Dict[str, ContributedProperty]:
    """Return the fictional contributed properties (one building, one cash).

    The building's short remaining *tax* life vs. its longer *book* life is what
    forces the ceiling rule under the traditional method.
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
    """Per-property facts: the building is sold in the final modelled year."""
    facts: Dict[tuple[str, int], PropertyYear] = {}
    sale_year = max(years)
    # Sell the building at a fictional price in the final year to demonstrate
    # the on-sale §704(c) catch-up to the contributing partner.
    facts[("HARBOR_BLDG", sale_year)] = PropertyYear(
        property="HARBOR_BLDG",
        year=sale_year,
        sold=True,
        sale_price_cents=to_cents(700_000),
    )
    return facts


def build_partnership_years(
    years: List[int], rng: random.Random
) -> Dict[int, PartnershipYear]:
    """Per-partnership facts: a steady fictional operating profit each year.

    The RNG is accepted for interface parity but the figures are fixed so the
    worked example and the tests stay reproducible.
    """
    out: Dict[int, PartnershipYear] = {}
    for year in years:
        out[year] = PartnershipYear(
            year=year,
            ordinary_income_cents=to_cents(180_000),
            cash_distribution_cents=to_cents(120_000),
        )
    return out


def generate_partnership(
    n_years: int = DEFAULT_YEARS, seed: int = DEFAULT_SEED
) -> Partnership:
    """Generate the complete, deterministic fictional :class:`Partnership`.

    Parameters
    ----------
    n_years:
        Number of fiscal years after formation to roll forward (>= 1).
    seed:
        RNG seed for reproducibility (kept for interface parity).
    """
    if n_years < 1:
        raise ValueError("n_years must be >= 1")
    rng = random.Random(seed)
    years = list(range(1, n_years + 1))
    return Partnership(
        code="HARBORVIEW_LP",
        name="Harborview Partners LP",
        partners=build_partners(),
        properties=build_properties(),
        property_years=build_property_years(years),
        partnership_years=build_partnership_years(years, rng),
        years=years,
    )
