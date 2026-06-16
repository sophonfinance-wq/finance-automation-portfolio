"""Shared test fixtures and helpers.

Builds small, hand-controlled structures so each statutory behaviour can be
asserted in isolation, independent of the random generator.
"""

from __future__ import annotations

from typing import Dict, Optional

import pytest

from surplus_engine.model import Entity, FxTable, Structure, YearFacts


def make_entity(
    code: str,
    tier: int,
    parent: Optional[str],
    ownership_pct: float,
    currency: str = "USD",
    name: Optional[str] = None,
) -> Entity:
    return Entity(
        code=code,
        name=name or f"{code} Demo Co",
        tier=tier,
        currency=currency,
        parent=parent,
        ownership_pct=ownership_pct,
    )


def make_facts(
    entity: str,
    year: int,
    income: float = 0.0,
    adj: float = 0.0,
    exempt_portion: float = 1.0,
    distribution: float = 0.0,
    capital_contribution: float = 0.0,
    return_of_capital: float = 0.0,
) -> YearFacts:
    return YearFacts(
        entity=entity,
        year=year,
        standalone_taxable_income=income,
        reg_5907_2_adjustment=adj,
        exempt_portion=exempt_portion,
        distribution=distribution,
        capital_contribution=capital_contribution,
        return_of_capital=return_of_capital,
    )


def make_structure(entities, facts_list, fx=None, years=None) -> Structure:
    ent_map: Dict[str, Entity] = {e.code: e for e in entities}
    facts_map = {(f.entity, f.year): f for f in facts_list}
    if fx is None:
        all_years = years or sorted({f.year for f in facts_list}) or [2021]
        fx = FxTable(usd_cad={y: 1.30 for y in all_years})
    yrs = years or sorted({f.year for f in facts_list})
    return Structure(entities=ent_map, facts=facts_map, fx=fx, years=yrs)


@pytest.fixture
def single_entity_factory():
    """Factory: build a one-entity (top holdco) structure with given facts."""

    def _factory(facts_list, currency="USD", fx=None):
        ent = make_entity("SOLO", tier=0, parent=None, ownership_pct=1.0, currency=currency)
        return make_structure([ent], facts_list, fx=fx)

    return _factory
