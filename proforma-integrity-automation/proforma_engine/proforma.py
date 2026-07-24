"""
The proforma derivation kernel, defined once.
=============================================

Re-deriving a project's stated figures from its base ledger is the single
operation this whole engine is built around, so the arithmetic lives here alone
and both the generator and the controls import it. That is deliberate: if the
engine recomputed net profit, a margin, or a waterfall split by *different* logic
than the generator used to produce the data, the two would disagree at the edges
-- a truncating margin at a fractional basis point, a largest-remainder split of
an odd cent -- and the tie-out control would be measuring the disagreement
between two implementations rather than the correctness of the figure on the tab.

Everything here works on already-extracted primitives -- integer cents, integer
square feet, integer basis points and :class:`datetime.date` objects -- so the
caller owns reading (and, in the engine's case, integer-validating) the raw
fields. That keeps the kernel free of JSON-shape and money-coercion concerns and
makes the boundary rules -- a margin floored to the basis point, a split whose
odd cent lands by largest remainder, a variance that is a plain subtraction --
state exactly once.
"""

from __future__ import annotations

from datetime import date

from .money import BPS_FULL, allocate_by_ratio


def total_project_cost(hard_cents: int, soft_cents: int) -> int:
    """Total project cost is hard cost plus soft cost, exactly."""
    return hard_cents + soft_cents


def unlevered_cost(hard_cents: int, soft_cents: int, interest_cents: int) -> int:
    """Unlevered (dev-budget) cost strips the financing interest out of the total."""
    return hard_cents + soft_cents - interest_cents


def net_profit(net_revenue_cents: int, hard_cents: int, soft_cents: int) -> int:
    """Net profit is net revenue less total project cost."""
    return net_revenue_cents - total_project_cost(hard_cents, soft_cents)


def unlevered_profit(
    net_revenue_cents: int, hard_cents: int, soft_cents: int, interest_cents: int
) -> int:
    """Unlevered profit is net revenue less the unlevered cost."""
    return net_revenue_cents - unlevered_cost(hard_cents, soft_cents, interest_cents)


def margin_bps(numerator_cents: int, denominator_cents: int) -> int:
    """A margin as integer basis points, truncated toward zero.

    Truncation is the contract: the figure on the tab is derived this way, so the
    engine can compare the stated basis points to the recomputed ones with exact
    ``==``. A non-positive denominator yields ``0`` -- there is no base to divide.
    """
    if denominator_cents <= 0:
        return 0
    return numerator_cents * BPS_FULL // denominator_cents


def cost_per_nsf(total_cost_cents: int, nsf: int) -> int:
    """Cost per net square foot, in integer cents, truncated.

    A non-positive area yields ``0`` -- there is no denominator to divide by.
    """
    if nsf <= 0:
        return 0
    return total_cost_cents // nsf


def sponsor_share(profit_cents: int, sponsor_bps: int, investor_bps: int) -> int:
    """The sponsor's share of profit under the equity split.

    Split by the largest-remainder method so the sponsor and investor shares sum
    back to the whole profit with no cent lost or created.
    """
    return allocate_by_ratio(profit_cents, [sponsor_bps, investor_bps])[0]


def investor_share(profit_cents: int, sponsor_bps: int, investor_bps: int) -> int:
    """The investor's share of profit under the equity split (see :func:`sponsor_share`)."""
    return allocate_by_ratio(profit_cents, [sponsor_bps, investor_bps])[1]


def schedule_variance_days(current: date, baseline: date) -> int:
    """Milestone schedule variance, in days, as current minus baseline.

    Positive is a slip (the milestone moved later than the business plan); negative
    is ahead of plan. A plain date subtraction, stated once.
    """
    return (current - baseline).days


def exceeds_materiality(variance_cents: int, band_cents: int) -> bool:
    """Whether a period-over-period swing is outside the materiality band.

    The band is symmetric: a swing is material when its absolute value is strictly
    greater than ``band_cents``. A swing exactly at the band is inside it.
    """
    return abs(variance_cents) > band_cents
