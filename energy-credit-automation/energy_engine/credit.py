"""
The §45L credit predicate and derivation, defined once.
=======================================================

Deciding whether a claimed dwelling unit qualifies for the credit -- and what the
credit, tax effect and net benefit derived from it are -- is the single operation
this whole engine is built around, so it lives here alone and both the generator
and the controls import it. That is deliberate: if the engine re-derived a unit's
credit by *different* logic than the one that produced it, the two would disagree
on the edge cases -- a unit closing exactly on the sunset date, a unit closing on
the last day of the period -- and the tie-out control would be measuring the
disagreement between two implementations rather than the correctness of the
determination.

Everything here works on already-extracted primitives -- integer cents, booleans
and :class:`datetime.date` objects -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw fields. That keeps the kernel free of
JSON-shape and money-coercion concerns and makes the boundary rules -- a unit
closing *on* the period-start, a unit closing *on* the sunset date -- state
exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .money import apply_rate


@dataclass(frozen=True)
class Statute:
    """The dated statutory parameters every unit is measured against."""

    per_unit_cents: int
    sunset_date: date
    period_start: date
    period_end: date
    effective_rate_bps: int


@dataclass(frozen=True)
class Unit:
    """A closed dwelling unit reduced to the facts the predicate needs."""

    coe_date: date
    certified: bool
    claimed: bool


def closed_in_period(coe: date, statute: Statute) -> bool:
    """Whether a close-of-escrow date falls inside the fiscal-year window.

    The window is the closed span ``[period_start, period_end]``: a unit closing
    exactly on the first or last day of the period is inside it.
    """
    return statute.period_start <= coe <= statute.period_end


def within_sunset(coe: date, statute: Statute) -> bool:
    """Whether a close-of-escrow date is on or before the statutory sunset.

    A unit closing exactly **on** the sunset date is still eligible: the gate is
    ``coe <= sunset_date``. A unit closing the day after has missed the statute.
    """
    return coe <= statute.sunset_date


def unit_qualifies(unit: Unit, statute: Statute) -> bool:
    """Whether a claimed unit actually earns the credit.

    A unit qualifies when it was certified by a rater, it closed inside the
    fiscal-year window, and it closed on or before the statutory sunset. Shared
    with the generator so the determination the engine recomputes is the one that
    produced the data.
    """
    return (
        unit.certified
        and closed_in_period(unit.coe_date, statute)
        and within_sunset(unit.coe_date, statute)
    )


def unit_credit_cents(unit: Unit, statute: Statute) -> int:
    """The credit a claimed unit contributes: the statutory rate, or zero.

    The taxpayer claims the rate on every unit marked ``claimed``; whether that
    claim survives the eligibility gates is a separate control's question. This
    returns the amount the register states for a claimed unit (the dated rate) and
    zero for an unclaimed one, so the per-unit rate control has one number to
    re-derive.
    """
    return statute.per_unit_cents if unit.claimed else 0


def gross_credit_cents(qualifying_units: int, statute: Statute) -> int:
    """Gross credit for a project: qualifying units times the dated rate."""
    return qualifying_units * statute.per_unit_cents


def tax_effect_cents(gross_credit: int, statute: Statute) -> int:
    """The tax effect of the credit's profit addback, a negative amount.

    The credit is added back to book profit and taxed at the effective rate, so
    the tax effect is ``-(credit x rate)``, derived with the platform-standard
    truncating :func:`~energy_engine.money.apply_rate` so a reported figure
    compares to the derived one with exact ``==``.
    """
    return -apply_rate(gross_credit, statute.effective_rate_bps)


def net_benefit_cents(gross_credit: int, statute: Statute) -> int:
    """Net tax benefit: the gross credit plus its (negative) tax effect."""
    return gross_credit + tax_effect_cents(gross_credit, statute)
