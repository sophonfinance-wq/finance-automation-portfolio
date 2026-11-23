"""
The schedule kernel, defined once.
==================================

Re-deriving a straight-line depreciation figure or a prepaid amortization
waterfall figure is the single operation this whole engine is built around, so
it lives here alone and both the generator and the controls import it. That is
deliberate: if the engine recomputed a monthly charge by *different* logic than
the one that produced it, the two would disagree on the edge cases -- the final
month that absorbs the rounding remainder, the month an asset enters service,
the catch-up an item booked late takes in its first month -- and the
re-derivation controls would be measuring the disagreement between two
implementations rather than the correctness of the register.

Everything here works on already-extracted primitives -- integer cents, integer
month indexes and integer lives -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw fields. Months are handled as a flat
integer index (``year * 12 + month - 1``) so month arithmetic is plain integer
arithmetic and every boundary -- the in-service month, the end-of-depreciation
month, the amortization window edges -- states exactly once.

Conventions, stated once
------------------------
- **Full-month convention.** An asset placed in service in a month takes a full
  month of depreciation for that month; there is no mid-month proration.
- **The remainder lands in the final month.** The monthly charge is
  ``cost // life`` and the final month of the schedule absorbs whatever is left,
  so the schedule sums back to cost exactly -- the same contract as
  :func:`depreciation_engine.money.split_evenly`.
- **Caps and floors are structural.** Months used never exceeds the life,
  accumulated depreciation never exceeds cost, and net book value never goes
  below zero, because the arithmetic cannot produce it -- not because a floor
  was applied afterwards.
"""

from __future__ import annotations

import re

#: ``YYYY-MM`` month labels, the only date grain the registers carry.
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# --------------------------------------------------------------------------- #
# Month arithmetic
# --------------------------------------------------------------------------- #
def parse_month(value: object) -> int | None:
    """Parse a ``YYYY-MM`` label into a flat month index, or ``None``.

    The index is ``year * 12 + month - 1``, so consecutive months differ by
    exactly one and month arithmetic is integer arithmetic.
    """
    if not isinstance(value, str) or not MONTH_RE.match(value):
        return None
    year, month = value.split("-")
    return int(year) * 12 + int(month) - 1


def month_str(index: int) -> str:
    """Render a flat month index back to its ``YYYY-MM`` label."""
    year, month = divmod(index, 12)
    return f"{year:04d}-{month + 1:02d}"


def months_elapsed(in_service: int, close: int) -> int:
    """Months of depreciation taken through the close month, inclusive.

    Full-month convention: the in-service month itself counts as month one. An
    asset entering service after the close month has taken zero months.
    """
    return max(close - in_service + 1, 0)


def end_depr_month(in_service: int, life_months: int) -> int:
    """The final month of the schedule: in-service month plus life, less one.

    A 36-month asset placed in service in month N takes its last charge in month
    ``N + 35``; from the following month it is fully depreciated.
    """
    return in_service + life_months - 1


# --------------------------------------------------------------------------- #
# Straight-line depreciation
# --------------------------------------------------------------------------- #
def monthly_dep_cents(cost_cents: int, life_months: int) -> int:
    """The standard monthly charge: ``cost // life``, in integer cents.

    The final month of the schedule absorbs the rounding remainder, so the
    charges sum back to cost exactly; this figure is every month but the last.
    """
    return cost_cents // life_months


def months_used(in_service: int, close: int, life_months: int) -> int:
    """Months of depreciation taken to date, capped at the useful life."""
    return min(months_elapsed(in_service, close), life_months)


def accum_dep_cents(cost_cents: int, life_months: int, in_service: int, close: int) -> int:
    """Accumulated depreciation through the close month, capped at cost.

    ``base * months_used`` until the schedule completes; exactly ``cost`` from
    the final month onward, because the final month absorbs the remainder.
    """
    used = months_used(in_service, close, life_months)
    if used >= life_months:
        return cost_cents
    return monthly_dep_cents(cost_cents, life_months) * used


def depr_expense_cents(cost_cents: int, life_months: int, in_service: int, close: int) -> int:
    """The depreciation charge belonging to the close month itself.

    Zero before the in-service month and zero once the schedule has completed;
    the base charge in between; and the base plus the rounding remainder in the
    final month, so the whole schedule sums to cost.
    """
    elapsed = months_elapsed(in_service, close)
    if elapsed <= 0 or elapsed > life_months:
        return 0
    base = monthly_dep_cents(cost_cents, life_months)
    if elapsed == life_months:
        return cost_cents - base * (life_months - 1)
    return base


def nbv_cents(cost_cents: int, accum_cents: int) -> int:
    """Net book value: cost less accumulated depreciation."""
    return cost_cents - accum_cents


# --------------------------------------------------------------------------- #
# Prepaid term-window amortization
# --------------------------------------------------------------------------- #
def window_periods(start: int, end: int) -> int:
    """Number of monthly periods in an inclusive amortization window."""
    return end - start + 1


def monthly_amort_cents(additions_cents: int, periods: int) -> int:
    """The standard monthly amortization: ``additions // periods``.

    As with depreciation, the final period of the window absorbs the remainder.
    """
    return additions_cents // periods


def cum_amort_cents(additions_cents: int, start: int, end: int, month: int) -> int:
    """Scheduled cumulative amortization through ``month``.

    Zero before the window opens; ``base * k`` through the ``k``-th period; and
    exactly ``additions`` from the final period onward.
    """
    if month < start:
        return 0
    periods = window_periods(start, end)
    k = min(month - start + 1, periods)
    if k >= periods:
        return additions_cents
    return monthly_amort_cents(additions_cents, periods) * k


def booked_cum_cents(
    additions_cents: int, start: int, end: int, booked_from: int, month: int
) -> int:
    """Cumulative amortization actually booked through ``month``.

    An item set up late books nothing before ``booked_from``; from that month it
    is caught up to the scheduled cumulative, which is what makes the first
    booked month a catch-up month.
    """
    if month < booked_from:
        return 0
    return cum_amort_cents(additions_cents, start, end, month)


def amort_expense_cents(
    additions_cents: int, start: int, end: int, booked_from: int, close: int
) -> int:
    """The amortization charge belonging to the close month itself.

    Zero outside ``[booked_from, end]``. In the first booked month the charge is
    the whole scheduled cumulative to date -- the catch-up proration for the
    periods the item sat unbooked. After that it is the month-over-month step of
    the schedule, which is the base charge until the final period absorbs the
    remainder.
    """
    if close < booked_from or close > end:
        return 0
    if close == booked_from:
        return cum_amort_cents(additions_cents, start, end, close)
    return cum_amort_cents(additions_cents, start, end, close) - cum_amort_cents(
        additions_cents, start, end, close - 1
    )


def prepaid_beginning_cents(
    additions_cents: int, start: int, end: int, booked_from: int, close: int
) -> int:
    """The unamortized balance at the opening of the close month."""
    return additions_cents - booked_cum_cents(
        additions_cents, start, end, booked_from, close - 1
    )


def prepaid_ending_cents(
    additions_cents: int, start: int, end: int, booked_from: int, close: int
) -> int:
    """The unamortized balance at the close of the close month."""
    return additions_cents - booked_cum_cents(
        additions_cents, start, end, booked_from, close
    )


# --------------------------------------------------------------------------- #
# Gates and watches
# --------------------------------------------------------------------------- #
def capitalization_required(
    cost_cents: int, threshold_cents: int, category: str, excluded: tuple[str, ...]
) -> bool:
    """Whether the policy requires an item to be capitalized.

    An item is capitalized when its cost meets the threshold **at** the
    threshold (``>=``, not ``>``) and its category is not excluded outright.
    Everything else is expensed. The gate is a hard equality on this predicate:
    a sub-threshold item capitalized is as wrong as a qualifying item expensed.
    """
    return cost_cents >= threshold_cents and category not in excluded


def past_disposal_review(end_month: int, close: int, review_months: int) -> bool:
    """Whether a fully depreciated asset has sat past the disposal-review band.

    True when the close month is *strictly more than* ``review_months`` past the
    asset's final depreciation month: an asset exactly at the band's edge is
    still inside it.
    """
    return close - end_month > review_months


def window_ending_soon(end: int, close: int, watch_months: int) -> bool:
    """Whether a prepaid window ends inside the look-ahead watch.

    The watch is the inclusive span ``[close, close + watch_months]``: a window
    ending this close month is already ending, and one ending exactly
    ``watch_months`` out is still inside the watch.
    """
    return 0 <= end - close <= watch_months
