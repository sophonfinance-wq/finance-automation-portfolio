"""Deterministic synthetic-data generator for the fictional structure.

Everything here is invented for a portfolio demo. Names are obviously fake
(``Birchwood Op Co``, ``Maple Fund LP`` ...), figures are random but SEEDED so
runs are fully reproducible, and the FX table is fictional.

The structure is a four-tier chain:

    Birchwood Op Co (operating project, USD)
        -> Cedar Mezz Holdings LLC (mezzanine, USD)
            -> Maple Fund LP (fund / holding, USD)
                -> Demo Holdings Inc. (top holdco, CAD)

Ownership %s are < 100% at some tiers so the ownership-allocation logic is
exercised.
"""

from __future__ import annotations

import random
from typing import Dict, List

from .model import Entity, FxTable, Structure, YearFacts

# Fixed seed -> identical output every run. Tests rely on this.
DEFAULT_SEED = 20240607


def build_entities() -> Dict[str, Entity]:
    """Return the fictional four-tier ownership tree."""
    entities = [
        Entity(
            code="BIRCH_OP",
            name="Birchwood Op Co",
            tier=0,
            currency="USD",
            parent="CEDAR_MEZZ",
            ownership_pct=0.80,
        ),
        Entity(
            code="CEDAR_MEZZ",
            name="Cedar Mezz Holdings LLC",
            tier=1,
            currency="USD",
            parent="MAPLE_FUND",
            ownership_pct=0.90,
        ),
        Entity(
            code="MAPLE_FUND",
            name="Maple Fund LP",
            tier=2,
            currency="USD",
            parent="DEMO_HOLDCO",
            ownership_pct=1.00,
        ),
        Entity(
            code="DEMO_HOLDCO",
            name="Demo Holdings Inc.",
            tier=3,
            currency="CAD",
            parent=None,
            ownership_pct=1.00,
        ),
    ]
    return {e.code: e for e in entities}


def build_fx_table(years: List[int], rng: random.Random) -> FxTable:
    """Build a fictional USD->CAD table that drifts gently around ~1.33."""
    table: Dict[int, float] = {}
    rate = 1.30
    for year in sorted(years):
        rate = round(rate + rng.uniform(-0.03, 0.05), 4)
        rate = max(1.20, min(1.45, rate))
        table[year] = rate
    return FxTable(usd_cad=table)


def _entity_profile(code: str) -> Dict[str, float]:
    """Per-entity earnings/behaviour profile used to scale random facts.

    Operating entities earn the most; upper tiers are mostly conduits.
    """
    return {
        "BIRCH_OP": {"income": 4_000_000, "exempt": 0.65, "dist": 0.55, "contrib": 0.15},
        "CEDAR_MEZZ": {"income": 350_000, "exempt": 0.50, "dist": 0.70, "contrib": 0.10},
        "MAPLE_FUND": {"income": 120_000, "exempt": 0.40, "dist": 0.75, "contrib": 0.05},
        "DEMO_HOLDCO": {"income": 90_000, "exempt": 0.30, "dist": 0.00, "contrib": 0.00},
    }[code]


def build_facts(
    entities: Dict[str, Entity], years: List[int], rng: random.Random
) -> Dict[tuple[str, int], YearFacts]:
    """Generate per-(entity, year) facts with a seeded RNG."""
    facts: Dict[tuple[str, int], YearFacts] = {}
    for code in entities:
        profile = _entity_profile(code)
        for year in sorted(years):
            base = profile["income"]
            income = round(base * rng.uniform(0.6, 1.25), 2)

            # Reg. 5907(2) net adjustment: a modest signed book-tax difference.
            adj = round(income * rng.uniform(-0.12, 0.06), 2)

            exempt_portion = round(min(0.95, max(0.05, profile["exempt"] + rng.uniform(-0.1, 0.1))), 4)

            # Distributions: only sometimes, and only a fraction of earnings.
            distribution = 0.0
            return_of_capital = 0.0
            if profile["dist"] > 0 and rng.random() < profile["dist"]:
                distribution = round(max(0.0, income) * rng.uniform(0.2, 0.6), 2)
                # A slice of the distribution is a return of capital (ACB event).
                if rng.random() < 0.35:
                    return_of_capital = round(distribution * rng.uniform(0.1, 0.4), 2)

            # Capital contributions DOWN into the entity (ACB-increasing).
            capital_contribution = 0.0
            if profile["contrib"] > 0 and rng.random() < profile["contrib"]:
                capital_contribution = round(base * rng.uniform(0.05, 0.2), 2)

            facts[(code, year)] = YearFacts(
                entity=code,
                year=year,
                standalone_taxable_income=income,
                reg_5907_2_adjustment=adj,
                exempt_portion=exempt_portion,
                distribution=distribution,
                capital_contribution=capital_contribution,
                return_of_capital=return_of_capital,
            )
    return facts


def generate_structure(
    start_year: int = 2021,
    end_year: int = 2024,
    seed: int = DEFAULT_SEED,
) -> Structure:
    """Generate a complete, deterministic fictional :class:`Structure`.

    Parameters
    ----------
    start_year, end_year:
        Inclusive fiscal-year range.
    seed:
        RNG seed for reproducibility.
    """
    if end_year < start_year:
        raise ValueError("end_year must be >= start_year")
    rng = random.Random(seed)
    years = list(range(start_year, end_year + 1))
    entities = build_entities()
    # FX first, then facts, so the RNG stream is stable given the seed.
    fx = build_fx_table(years, rng)
    facts = build_facts(entities, years, rng)
    return Structure(entities=entities, facts=facts, fx=fx, years=years)
