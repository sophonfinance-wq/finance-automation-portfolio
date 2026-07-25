"""
The combined-group margin-tax computation, defined once.
========================================================

Turning a combined group's consolidated revenue into the franchise (margin) tax
a state is owed is the single operation this whole engine is built around, so it
lives here alone and both the generator and the controls import it. That is
deliberate: if the engine recomputed a return's tax by *different* arithmetic
than the arithmetic that produced it, the two would disagree on the edge cases --
a margin struck to the cent, a receipts factor floored at the same basis point,
an elected deduction that swallows the whole revenue -- and the tie-out control
would be measuring the disagreement between two implementations rather than the
correctness of the number.

Everything here works on already-extracted primitives -- integer cents, integer
basis points and lists of entity ids -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw fields. Truncating basis-point
arithmetic is reused from :mod:`franchise_engine.money` so a tax derived here
compares to a filed figure with exact ``==``. The boundary rules -- a roster that
is exactly the prior list plus additions less removals, a single-factor
apportionment bounded to ``[0, 100.00%]`` in basis points, an elected deduction
that cannot drive the margin below zero, and a tax taken as margin times
apportionment times rate in that order -- are stated exactly once.
"""

from __future__ import annotations

from collections.abc import Iterable

from .money import BPS_FULL, apply_rate


def combined_members(
    prior: Iterable[str], additions: Iterable[str], removals: Iterable[str]
) -> list[str]:
    """The current combined-group roster: prior year plus additions, less removals.

    The roster is rebuilt each fiscal year rather than carried forward blind: it
    is exactly last year's members, plus the affiliates joining the group this
    year, minus the affiliates leaving it. Returned sorted and de-duplicated so
    the comparison against the stated member list is stable, and a removal always
    wins over an addition of the same id (an affiliate cannot both join and stay
    excluded).
    """
    members = (set(prior) | set(additions)) - set(removals)
    return sorted(members)


def apportionment_factor_bps(in_state_cents: int, everywhere_cents: int) -> int:
    """The single-factor receipts apportionment factor, in integer basis points.

    The factor is in-state receipts over everywhere receipts, floored to a basis
    point and bounded to ``[0, 10000]`` (0.00%..100.00%). Flooring is deliberate:
    the factor scales the margin the state may tax, and flooring can only ever
    understate that share by a rounding artifact, never overstate it. A zero or
    negative everywhere-receipts figure yields ``0`` -- no receipts base means no
    share to apportion -- and in-state receipts exceeding everywhere clamp to
    ``10000`` rather than reporting a factor above 100%.
    """
    if everywhere_cents <= 0:
        return 0
    factor = in_state_cents * BPS_FULL // everywhere_cents
    if factor < 0:
        return 0
    if factor > BPS_FULL:
        return BPS_FULL
    return factor


def taxable_margin(revenue_cents: int, deduction_cents: int) -> int:
    """Group revenue reduced by the elected deduction, clamped at zero.

    The elected deduction (cost of goods sold, compensation, or the fixed
    percentage the group elects) is subtracted from consolidated revenue to reach
    the taxable margin. Clamped at zero: an elected deduction larger than the
    revenue leaves a zero margin, not a negative tax -- the excess simply does not
    carry.
    """
    margin = revenue_cents - deduction_cents
    return margin if margin > 0 else 0


def apportioned_margin(margin_cents: int, factor_bps: int) -> int:
    """The taxable margin scaled by the apportionment factor (truncating)."""
    return apply_rate(margin_cents, factor_bps)


def margin_tax(apportioned_margin_cents: int, rate_bps: int) -> int:
    """The franchise tax: the apportioned margin at the margin-tax rate (truncating).

    Taken as ``margin x apportionment x rate`` in that order, each step truncating
    basis-point arithmetic, so a tax derived elsewhere the same way ties with
    exact ``==``.
    """
    return apply_rate(apportioned_margin_cents, rate_bps)
