"""
The gross-receipts tax computation, defined once.
=================================================

Turning a period's receipts into the tax a jurisdiction is owed is the single
operation this whole engine is built around, so it lives here alone and both the
generator and the controls import it. That is deliberate: if the engine
recomputed a worksheet's tax by *different* arithmetic than the arithmetic that
produced it, the two would disagree on the edge cases -- a base struck to the
cent, a rate on the day its window opens, receipts a dollar below the threshold
-- and the tie-out control would be measuring the disagreement between two
implementations rather than the correctness of the number.

Everything here works on already-extracted primitives -- integer cents, integer
basis points and :class:`datetime.date` objects -- so the caller owns reading
(and, in the engine's case, integer-validating) the raw fields. Truncating
basis-point arithmetic is reused from :mod:`grt_engine.money` so a tax derived
here compares to a filed figure with exact ``==``. The boundary rules -- a
deduction that cannot drive the base below zero, a rate window that is closed on
both ends, a threshold that wipes the tax *below* it but not *at* it -- are
stated exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .money import apply_rate


@dataclass(frozen=True)
class RateWindow:
    """One classification rate in force over a closed date span."""

    effective_from: date
    effective_to: date
    rate_bps: int


def effective_rate(windows: list[RateWindow], on: date) -> int | None:
    """Return the classification rate in force on ``on``, or ``None``.

    The span is closed on both ends -- a rate whose window is
    ``[effective_from, effective_to]`` applies on both endpoints -- so a period
    starting exactly on the day a new rate opens is taxed at the new rate. When
    two windows would cover the same day the earliest-opening one wins, which
    keeps the choice stable; a well-formed table never overlaps. ``None`` means
    no window covers the day, and a separate control owns that gap.
    """
    covering = [
        w for w in windows if w.effective_from <= on <= w.effective_to
    ]
    if not covering:
        return None
    covering.sort(key=lambda w: (w.effective_from, w.effective_to))
    return covering[0].rate_bps


def taxable_base(gross_cents: int, nontaxable_cents: int, standard_deduction_cents: int) -> int:
    """Receipts reduced by the non-taxable back-out and the standard deduction.

    Clamped at zero: a deduction larger than the receipts leaves a zero base, not
    a negative tax. Deductions never turn into a refund here -- the excess simply
    does not carry.
    """
    base = gross_cents - nontaxable_cents - standard_deduction_cents
    return base if base > 0 else 0


def tax_before_credit(base_cents: int, rate_bps: int) -> int:
    """Apply the classification rate to the taxable base (truncating)."""
    return apply_rate(base_cents, rate_bps)


def small_business_credit(tax_cents: int, cap_cents: int) -> int:
    """The small-business credit for a tax figure, as a bracket-free schedule.

    A jurisdiction with a ``cap`` gives a full offset up to the cap and phases the
    credit down linearly to zero at twice the cap: tax at or below ``cap`` is
    wiped to nothing, tax at or above ``2*cap`` gets no credit, and in between the
    credit is ``2*cap - tax``. A jurisdiction with ``cap == 0`` never grants a
    credit. The schedule is exact integer arithmetic, so it re-derives to the
    cent.
    """
    if cap_cents <= 0 or tax_cents <= 0:
        return 0
    if tax_cents <= cap_cents:
        return tax_cents
    if tax_cents >= 2 * cap_cents:
        return 0
    return 2 * cap_cents - tax_cents


def expected_credit(
    gross_cents: int,
    tax_before_credit_cents: int,
    threshold_cents: int,
    cap_cents: int,
) -> int:
    """The credit a worksheet should carry, from the jurisdiction's own rules.

    A below-threshold no-tax rule comes first: when the jurisdiction sets a
    positive threshold and the period's gross receipts fall *below* it, the whole
    tax is credited away (net tax zero). Receipts exactly *at* the threshold are
    over it and taxed normally. Otherwise the small-business credit schedule
    applies.
    """
    if threshold_cents > 0 and gross_cents < threshold_cents:
        return tax_before_credit_cents
    return small_business_credit(tax_before_credit_cents, cap_cents)


def net_tax(tax_before_credit_cents: int, credit_cents: int) -> int:
    """Tax after credit, clamped at zero: a credit never becomes a refund."""
    net = tax_before_credit_cents - credit_cents
    return net if net > 0 else 0
