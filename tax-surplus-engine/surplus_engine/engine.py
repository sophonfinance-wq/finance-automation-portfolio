"""The surplus / ACB calculation engine.

This module is the showpiece. Given a :class:`~surplus_engine.model.Structure`
and a range of fiscal years, it computes — deterministically — per-entity,
per-year:

1. **Standalone surplus**: ``standalone_taxable_income + Reg.5907(2) adjustment``.
2. **Current-year pool additions**: split into exempt vs taxable surplus by
   ``exempt_portion``. (Only positive surplus adds to pools; a net loss reduces
   the taxable pool but never below zero.)
3. **Elevation (Reg. 5907(1)(d) style)**: surplus moves UP one tier *only* when
   a subsidiary makes an actual distribution, and only at the owner's ownership
   %. Operating income alone never elevates.
4. **Distribution waterfall**: a distribution consumes pools in statutory order
   ``exempt -> taxable -> pre-acquisition capital``, subject to an
   **exempt-distribution cap** (no more than ``EXEMPT_CAP`` of the distribution
   may be sourced from exempt surplus, modelling the practical limit on
   tax-free repatriation).
5. **ACB tracking**: ACB moves ONLY on capital events — capital contributions
   increase it; returns of capital / pre-acquisition distributions decrease it.
   Operating income/loss never touches ACB. A return of capital beyond ACB
   surfaces a deemed capital gain to the owner (ITA 40(3)-style); ACB is deemed
   nil rather than negative.
6. **Roll-forward**: closing balances of year *N* become opening balances of
   year *N+1*.

The engine returns rich per-row records so the reporting layer can produce the
Evidence -> Surplus-Details -> Summary lineage and so tests can assert on every
intermediate quantity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .model import (
    EXEMPT,
    PREACQ,
    POOL_ORDER,
    TAXABLE,
    Entity,
    PoolBalances,
    Structure,
    YearFacts,
)

# Exempt-distribution cap: at most this fraction of any single distribution may
# be drawn from the exempt-surplus pool. Models the practical ceiling on
# tax-free repatriation in a single year. Fictional, but enforced rigorously.
EXEMPT_CAP: float = 0.60

# Rounding precision for stored monetary results (functional currency units).
_MONEY_DP = 2


def _r(x: float) -> float:
    """Round to money precision, normalising ``-0.0`` to ``0.0``."""
    v = round(x, _MONEY_DP)
    return 0.0 if v == 0 else v


@dataclass
class WaterfallStep:
    """One pool draw inside a distribution waterfall."""

    pool: str
    amount: float


@dataclass
class EntityYearResult:
    """Everything computed for one entity in one fiscal year.

    This is intentionally verbose: the reporting layer and the test-suite both
    read directly off these fields, so each statutory quantity is exposed.
    """

    entity: str
    year: int
    currency: str

    # --- Evidence (echoed inputs) ---
    standalone_taxable_income: float
    reg_5907_2_adjustment: float
    exempt_portion: float
    distribution: float
    capital_contribution: float
    return_of_capital: float

    # --- Surplus details ---
    standalone_surplus: float = 0.0          # income + 5907(2) adj
    allocable_surplus: float = 0.0           # standalone_surplus * ownership_pct (for elevation up)
    current_exempt_addition: float = 0.0     # added to own exempt pool this year
    current_taxable_addition: float = 0.0    # added to own taxable pool this year
    elevated_exempt: float = 0.0             # exempt surplus elevated FROM subsidiaries this year
    elevated_taxable: float = 0.0            # taxable surplus elevated FROM subsidiaries this year

    # --- Waterfall ---
    waterfall: List[WaterfallStep] = field(default_factory=list)
    exempt_cap_amount: float = 0.0           # cap value applied to the distribution
    exempt_cap_binding: bool = False         # True if the cap actually limited the exempt draw

    # --- Balances ---
    opening: PoolBalances = field(default_factory=PoolBalances)
    closing: PoolBalances = field(default_factory=PoolBalances)

    # --- FX (filled by reporting) ---
    fx_rate_to_cad: float = 1.0

    # --- Tax consequence: return of capital beyond ACB (ITA 40(3)-style) ---
    deemed_gain_on_negative_acb: float = 0.0


def _split_current_surplus(
    standalone_surplus: float, exempt_portion: float
) -> Tuple[float, float]:
    """Split post-adjustment current surplus into (exempt, taxable) additions.

    A net positive surplus is split by ``exempt_portion``. A net loss is applied
    wholly against the taxable pool (it cannot create negative exempt surplus),
    and the engine later floors the taxable pool at zero during roll-forward.
    """
    if standalone_surplus >= 0:
        exempt_add = standalone_surplus * exempt_portion
        taxable_add = standalone_surplus * (1.0 - exempt_portion)
    else:
        exempt_add = 0.0
        taxable_add = standalone_surplus  # negative; reduces taxable pool
    return _r(exempt_add), _r(taxable_add)


def run_waterfall(
    distribution: float,
    opening: PoolBalances,
    exempt_cap_fraction: float = EXEMPT_CAP,
) -> Tuple[List[WaterfallStep], float, bool]:
    """Consume pools for a distribution in statutory order, with an exempt cap.

    Parameters
    ----------
    distribution:
        Positive cash amount distributed.
    opening:
        Pool balances available *before* the distribution (already including any
        current-year additions and elevations).
    exempt_cap_fraction:
        Maximum fraction of ``distribution`` sourced from exempt surplus.

    Returns
    -------
    (steps, exempt_cap_amount, cap_binding)
        ``steps`` are the ordered draws; ``exempt_cap_amount`` is the cap value;
        ``cap_binding`` is ``True`` if the cap actually constrained the exempt
        draw (i.e. exempt surplus would otherwise have funded more).
    """
    steps: List[WaterfallStep] = []
    remaining = distribution
    exempt_cap_amount = _r(distribution * exempt_cap_fraction)
    cap_binding = False

    if remaining <= 0:
        return steps, exempt_cap_amount, cap_binding

    # 1) Exempt surplus, but no more than the cap.
    exempt_available = opening.get(EXEMPT)
    exempt_uncapped = min(exempt_available, remaining)
    exempt_draw = min(exempt_uncapped, exempt_cap_amount)
    if exempt_uncapped > exempt_cap_amount + 1e-9:
        cap_binding = True
    if exempt_draw > 0:
        steps.append(WaterfallStep(EXEMPT, _r(exempt_draw)))
        remaining = _r(remaining - exempt_draw)

    # 2) Taxable surplus.
    if remaining > 0:
        taxable_draw = min(opening.get(TAXABLE), remaining)
        if taxable_draw > 0:
            steps.append(WaterfallStep(TAXABLE, _r(taxable_draw)))
            remaining = _r(remaining - taxable_draw)

    # 3) Pre-acquisition capital (absorbs whatever is left, floored at balance).
    if remaining > 0:
        preacq_draw = min(opening.get(PREACQ), remaining)
        if preacq_draw > 0:
            steps.append(WaterfallStep(PREACQ, _r(preacq_draw)))
            remaining = _r(remaining - preacq_draw)

    return steps, exempt_cap_amount, cap_binding


class SurplusEngine:
    """Stateful engine that rolls a structure forward across fiscal years."""

    def __init__(self, structure: Structure, exempt_cap_fraction: float = EXEMPT_CAP):
        self.structure = structure
        self.exempt_cap_fraction = exempt_cap_fraction
        # Running closing balances, keyed by entity code. Seeded at zero.
        self._balances: Dict[str, PoolBalances] = {
            code: PoolBalances() for code in structure.entities
        }

    # -- public API -------------------------------------------------------

    def run(self, years: List[int]) -> List[EntityYearResult]:
        """Compute results for every entity across ``years`` (ascending).

        Years are processed in order so roll-forward continuity holds. Within a
        year, entities are processed bottom-up so a subsidiary's distribution is
        known before its parent elevates it.
        """
        results: List[EntityYearResult] = []
        for year in sorted(years):
            results.extend(self._run_year(year))
        return results

    # -- internals --------------------------------------------------------

    def _run_year(self, year: int) -> List[EntityYearResult]:
        # Elevation that each parent will receive this year, accumulated as we
        # walk subsidiaries bottom-up.
        elevation_in: Dict[str, Dict[str, float]] = {
            code: {EXEMPT: 0.0, TAXABLE: 0.0} for code in self.structure.entities
        }

        year_results: Dict[str, EntityYearResult] = {}

        for entity in self.structure.ordered_bottom_up():
            facts = self._facts_for(entity, year)
            opening = self._balances[entity.code].copy()

            result = self._compute_entity_year(
                entity, facts, opening, elevation_in[entity.code]
            )
            year_results[entity.code] = result

            # Record elevation to the parent: distributed surplus moves up at the
            # owner's ownership %. We elevate the *characterised* exempt/taxable
            # amounts actually drawn in the waterfall (pre-acq capital does not
            # create surplus at the parent).
            if entity.parent is not None and facts.distribution > 0:
                drawn = {step.pool: step.amount for step in result.waterfall}
                pct = entity.ownership_pct
                elevation_in[entity.parent][EXEMPT] += _r(drawn.get(EXEMPT, 0.0) * pct)
                elevation_in[entity.parent][TAXABLE] += _r(drawn.get(TAXABLE, 0.0) * pct)

            # Commit closing balances for next year's roll-forward.
            self._balances[entity.code] = result.closing.copy()

        # Return ordered top-down for readability in reports.
        return [
            year_results[e.code]
            for e in sorted(self.structure.entities.values(), key=lambda x: (-x.tier, x.code))
        ]

    def _facts_for(self, entity: Entity, year: int) -> YearFacts:
        key = (entity.code, year)
        if key in self.structure.facts:
            return self.structure.facts[key]
        # A quiet year: no activity.
        return YearFacts(
            entity=entity.code,
            year=year,
            standalone_taxable_income=0.0,
            reg_5907_2_adjustment=0.0,
            exempt_portion=0.0,
            distribution=0.0,
            capital_contribution=0.0,
            return_of_capital=0.0,
        )

    def _compute_entity_year(
        self,
        entity: Entity,
        facts: YearFacts,
        opening: PoolBalances,
        elevation: Dict[str, float],
    ) -> EntityYearResult:
        # 1) Standalone surplus = income + 5907(2) adjustment.
        standalone_surplus = _r(
            facts.standalone_taxable_income + facts.reg_5907_2_adjustment
        )
        allocable = _r(standalone_surplus * entity.ownership_pct)

        # 2) Current-year pool additions (own operations).
        cur_exempt, cur_taxable = _split_current_surplus(
            standalone_surplus, facts.exempt_portion
        )

        # 3) Elevation received from subsidiaries (computed earlier this year).
        elev_exempt = _r(elevation.get(EXEMPT, 0.0))
        elev_taxable = _r(elevation.get(TAXABLE, 0.0))

        # Build the pre-distribution balance: opening + current + elevation.
        # ACB stays untouched by operating income — only capital events move it.
        working = opening.copy()
        working.add(EXEMPT, cur_exempt + elev_exempt)
        working.add(TAXABLE, cur_taxable + elev_taxable)

        # Capital contribution: pre-acquisition capital pool *and* ACB both rise.
        if facts.capital_contribution > 0:
            working.add(PREACQ, facts.capital_contribution)
            working.acb = _r(working.acb + facts.capital_contribution)

        # Floor the taxable pool at zero (a net loss cannot drive it negative;
        # the deficit is simply not available to distribute).
        if working.get(TAXABLE) < 0:
            working.taxable_surplus = 0.0

        # 4) Distribution waterfall against the working balances.
        steps, cap_amount, cap_binding = run_waterfall(
            facts.distribution, working, self.exempt_cap_fraction
        )

        closing = working.copy()
        for step in steps:
            closing.add(step.pool, -step.amount)

        # 5) ACB on capital events only: a return of capital / pre-acq dividend
        #    reduces ACB. Operating distributions do not. If the return of
        #    capital exceeds ACB, the excess is a deemed capital gain to the
        #    owner (ITA 40(3)-style) and ACB is deemed nil rather than negative.
        deemed_gain = 0.0
        if facts.return_of_capital > 0:
            acb_before = closing.acb
            deemed_gain = _r(max(0.0, facts.return_of_capital - acb_before))
            closing.acb = _r(max(0.0, acb_before - facts.return_of_capital))

        # Normalise stored balances.
        closing.exempt_surplus = _r(closing.exempt_surplus)
        closing.taxable_surplus = _r(closing.taxable_surplus)
        closing.pre_acquisition_capital = _r(closing.pre_acquisition_capital)
        closing.acb = _r(closing.acb)

        return EntityYearResult(
            entity=entity.code,
            year=facts.year,
            currency=entity.currency,
            standalone_taxable_income=_r(facts.standalone_taxable_income),
            reg_5907_2_adjustment=_r(facts.reg_5907_2_adjustment),
            exempt_portion=facts.exempt_portion,
            distribution=_r(facts.distribution),
            capital_contribution=_r(facts.capital_contribution),
            return_of_capital=_r(facts.return_of_capital),
            standalone_surplus=standalone_surplus,
            allocable_surplus=allocable,
            current_exempt_addition=cur_exempt,
            current_taxable_addition=cur_taxable,
            elevated_exempt=elev_exempt,
            elevated_taxable=elev_taxable,
            waterfall=steps,
            exempt_cap_amount=cap_amount,
            exempt_cap_binding=cap_binding,
            opening=opening,
            closing=closing,
            deemed_gain_on_negative_acb=deemed_gain,
        )
