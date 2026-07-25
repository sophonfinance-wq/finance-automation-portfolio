"""
The unit tie-out arithmetic, defined once.
==========================================

Every derived figure on the Matrix -- revenue per square foot, net proceeds,
total commission, the discount to list -- is produced here, and the controls
recompute it from here too. That is deliberate: if the engine re-derived a column
by *different* arithmetic than the arithmetic that produced it, the two would
disagree on the edge cases -- a price that does not divide evenly into the plan
area, a rate that truncates on the half cent -- and the tie-out control would be
measuring the disagreement between two implementations rather than the
correctness of the figure.

Everything here works on already-extracted primitives -- integer cents, integer
basis points, whole square feet and :class:`datetime.date` objects -- so the
caller owns reading (and, in the engine's case, integer-validating) the raw
fields. That keeps the kernel free of JSON-shape and money-coercion concerns and
makes the boundary rules -- a concession exactly equal to the sales price, a
discount exactly at the band, a proof due exactly on the review date -- state
exactly once.

Truncation is the contract in both directions. Revenue per square foot floors,
and the commission rate is applied through :func:`~sales_engine.money.apply_rate`,
which also floors. A figure derived by flooring can be compared to the reported
figure with exact ``==``; a figure derived by rounding somewhere else cannot.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from .money import allocate_by_ratio, apply_rate, percent_complete_bps, total


@dataclass(frozen=True)
class UnitPricing:
    """One Matrix row reduced to the base facts the arithmetic needs."""

    list_price_cents: int
    sales_price_cents: int
    concession_cents: int
    closing_costs_cents: int


@dataclass(frozen=True)
class CloseDates:
    """One Sold/Close row reduced to the dates the gate needs."""

    offer_date: date
    actual_date_sold: date
    closing_date: date


def revenue_per_sqft(sales_price_cents: int, plan_sqft: int) -> int | None:
    """Revenue per plan square foot, in integer cents, floored.

    ``None`` when the plan area is absent or non-positive: there is no revenue per
    square foot without a square footage, and a separate control owns that gap
    rather than this arithmetic inventing a figure for it.

    Args:
        sales_price_cents: The price the unit actually sold for, in cents.
        plan_sqft: The plan's square footage, a whole count.

    Returns:
        Cents of revenue per square foot, or ``None`` when undefined.
    """
    if plan_sqft <= 0:
        return None
    return sales_price_cents // plan_sqft


def net_proceeds(
    sales_price_cents: int, concession_cents: int, closing_costs_cents: int
) -> int:
    """Proceeds to the developer after the concession and the closing costs.

    Plain integer subtraction, and deliberately unbounded below: a unit that
    closes for less than it costs to close is a real outcome, and clamping it at
    zero would hide the one row worth reading.
    """
    return sales_price_cents - concession_cents - closing_costs_cents


def total_commission(sales_price_cents: int, commission_rate_bps: int) -> int:
    """Total selling commission: the channel rate applied to the sales price.

    Applied through :func:`~sales_engine.money.apply_rate`, so the derivation
    truncates and the reported figure can be compared with exact ``==``.
    """
    return apply_rate(sales_price_cents, commission_rate_bps)


def concession_within_price(concession_cents: int, sales_price_cents: int) -> bool:
    """Whether the concession is a real concession against the price.

    A negative concession is a credit dressed as a discount; a concession larger
    than the price is a unit given away with change. The band is inclusive at both
    ends: a concession exactly equal to the sales price is arithmetically
    admissible, and it is the cent past it that is not.
    """
    return 0 <= concession_cents <= sales_price_cents


def discount_to_list_bps(list_price_cents: int, sales_price_cents: int) -> int:
    """Discount from list to sales price, in integer basis points, floored.

    Flooring can only ever understate the discount, so the band below never flags
    a unit on a rounding artifact. A sale at or above list reports ``0``.
    """
    return percent_complete_bps(list_price_cents - sales_price_cents, list_price_cents)


def within_discount_band(discount_bps: int, max_discount_bps: int) -> bool:
    """Whether a discount is inside the approved band.

    Inclusive at the band: a discount of exactly ``max_discount_bps`` is inside
    sales authority, and the basis point past it is not.
    """
    return discount_bps <= max_discount_bps


def dates_in_order(dates: CloseDates) -> bool:
    """Whether a closing's three dates run forwards.

    ``offer_date <= actual_date_sold <= closing_date``. Same-day is admissible at
    both steps -- an offer accepted the day it is written, a closing that funds the
    day the sale goes hard -- so the gate is ``<=`` and not ``<``.
    """
    return dates.offer_date <= dates.actual_date_sold <= dates.closing_date


def proof_due(closing_date: date, as_of: date) -> bool:
    """Whether proof of closing is owed at the review date.

    Proof falls due the moment the closing date arrives, so a unit closing exactly
    on ``as_of`` owes its proof; one closing the day after does not yet.
    """
    return closing_date <= as_of


def split_commission(
    total_commission_cents: int, weights_bps: Sequence[int]
) -> list[int]:
    """Split a unit's total commission across agents by basis-point weights.

    Delegates to :func:`~sales_engine.money.allocate_by_ratio`, so the splits sum
    to the total exactly -- the residual cent lands on one named agent rather than
    disappearing into the rounding.
    """
    return allocate_by_ratio(total_commission_cents, weights_bps)


def splits_tie(split_cents: Iterable[int], total_commission_cents: int) -> bool:
    """Whether the logged agent splits sum to the commission on the Matrix row."""
    return total(split_cents) == total_commission_cents
