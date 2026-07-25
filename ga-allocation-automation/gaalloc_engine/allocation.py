"""
The allocation kernel, defined once.
====================================

Turning a column of driver counts into a column of dollars is the single
operation this whole engine is built around, so it lives here alone and both the
generator and the controls import it. That is deliberate: if the engine
re-derived an allocation by *different* arithmetic than the one that produced it,
the two would disagree on exactly the cases that matter -- the residual cent, the
share that lands on a fractional basis point -- and the tie-out control would be
measuring the disagreement between two implementations rather than the
correctness of the allocation.

Everything here works on already-extracted primitives -- integer cents, integer
counts, integer basis points and ``YYYY-MM`` period labels -- so the caller owns
reading (and, in the engine's case, integer-validating) the raw fields. That
keeps the kernel free of JSON-shape and money-coercion concerns and makes the
boundary rules -- a share column that must land on exactly 10000 bps, a residual
cent that belongs to exactly one recipient, an accounting date that must be the
last day of its month -- state exactly once.

Two rounding decisions are the whole kernel:

* :func:`driver_shares_bps` converts counts to basis points by the
  largest-remainder (Hamilton) method, so the share column sums to exactly
  10000 rather than to 9999 with a comment beside it.
* :func:`allocate_pool` splits the cost pool by those shares through the shared
  money kernel, again by largest remainder, so the allocated column sums to
  exactly the pool it divides.

Rounding each recipient independently would satisfy neither identity, which is
precisely how a workbook ends up pushing out 99.98% of its own cost pool every
month without anyone noticing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .money import BPS_FULL, allocate_by_ratio

#: A period label is a calendar month, ``YYYY-MM``.
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")

_DAYS_IN_MONTH: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass(frozen=True)
class Rollup:
    """The year-to-date figures re-derived from an allocation file's base facts.

    ``complete`` is ``False`` when at least one period could not be re-derived --
    a missing driver row, a malformed count, an absent cost pool. The tie-out
    control reads it and declines to compare a total it could not fully rebuild,
    rather than reporting a shortfall that is really an upstream gap.
    """

    period_count: int
    recipient_count: int
    pool_total_cents: int
    allocated_total_cents: int
    complete: bool


def parse_period(value: object) -> tuple[int, int] | None:
    """Read a ``YYYY-MM`` period label into ``(year, month)``, or ``None``.

    Args:
        value: The candidate label.

    Returns:
        The ``(year, month)`` pair, or ``None`` if the label is not a readable
        calendar month.
    """
    if not isinstance(value, str):
        return None
    match = _PERIOD_RE.match(value)
    if match is None:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return year, month


def period_label(year: int, month: int) -> str:
    """Render ``(year, month)`` as a ``YYYY-MM`` period label."""
    return f"{year:04d}-{month:02d}"


def next_period(period: str) -> str | None:
    """The calendar month after ``period``, or ``None`` if it is unreadable."""
    parsed = parse_period(period)
    if parsed is None:
        return None
    year, month = parsed
    if month == 12:
        return period_label(year + 1, 1)
    return period_label(year, month + 1)


def is_leap_year(year: int) -> bool:
    """Whether ``year`` is a leap year on the proleptic Gregorian calendar."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def month_end(period: str) -> date | None:
    """The accounting date a period tab must be stamped to: its last day.

    A monthly allocation posts on the last day of the month it allocates. A tab
    rolled forward but dated to the month it was copied from posts real cost into
    the wrong accounting period, and the only evidence is this date.

    Args:
        period: A ``YYYY-MM`` label.

    Returns:
        The last calendar day of that month, or ``None`` if the label is
        unreadable.
    """
    parsed = parse_period(period)
    if parsed is None:
        return None
    year, month = parsed
    day = _DAYS_IN_MONTH[month - 1]
    if month == 2 and is_leap_year(year):
        day = 29
    return date(year, month, day)


def driver_shares_bps(counts: Sequence[int]) -> list[int]:
    """Convert driver counts to allocation shares in basis points.

    Uses the largest-remainder (Hamilton) method, so the returned shares sum to
    exactly :data:`~gaalloc_engine.money.BPS_FULL` -- 10000 bps, 100.00% -- with
    no basis point lost or minted. Ties on the fractional remainder break on
    position, so the column is stable rather than merely correct: the same driver
    tab produces the same shares on every run and in every month it is copied to.

    Args:
        counts: Non-negative whole driver counts, one per recipient, in recipient
            order.

    Returns:
        One integer basis-point share per count, summing to 10000. A total driver
        count of zero returns all zeros -- there is no basis on which to allocate,
        and the caller's control owns that.
    """
    total = sum(counts)
    if total <= 0:
        return [0] * len(counts)
    floors: list[int] = []
    remainders: list[tuple[int, int]] = []  # (fractional_remainder, index)
    for idx, count in enumerate(counts):
        exact = BPS_FULL * count
        floor = exact // total
        floors.append(floor)
        remainders.append((exact - floor * total, idx))
    leftover = BPS_FULL - sum(floors)
    # Hand out the leftover basis points to the largest fractional remainders.
    remainders.sort(key=lambda t: (-t[0], t[1]))
    for i in range(leftover):
        floors[remainders[i][1]] += 1
    return floors


def allocate_pool(pool_cents: int, shares_bps: Sequence[int]) -> list[int]:
    """Split a cost pool across shares given in basis points.

    A named wrapper over :func:`~gaalloc_engine.money.allocate_by_ratio` so the
    allocation reads as what it is at every call site, and so there is exactly one
    place the pool-to-recipient arithmetic happens.

    Args:
        pool_cents: The period's cost pool, in integer cents.
        shares_bps: Integer basis-point shares; must sum to 10000.

    Returns:
        One integer-cent amount per share, summing to exactly ``pool_cents``.

    Raises:
        ValueError: If the shares do not sum to exactly 10000 basis points.
    """
    return allocate_by_ratio(pool_cents, shares_bps)


def meter_delta_cents(begin_cents: int, end_cents: int) -> int:
    """The metered postage spend for a period: the closing reading less the opening.

    The meter is cumulative, so the period's spend is a difference and never a
    balance. A negative result means the meter was reset or misread, which the
    caller's control owns.
    """
    return end_cents - begin_cents


def variance_bps(current_cents: int, prior_cents: int) -> int:
    """Month-over-month movement of a cost pool, in basis points, floored.

    The result is reported, not acted on -- it says how far a pool stepped from
    the month before it -- and flooring keeps the engine from ever overstating a
    step by a rounding artifact. A zero or negative prior returns ``0``: there is
    no base to measure the step against.

    Args:
        current_cents: This period's pool.
        prior_cents: The preceding period's pool.

    Returns:
        The absolute movement as a proportion of the prior pool, in basis points
        (``500`` == 5.00%).
    """
    if prior_cents <= 0:
        return 0
    return abs(current_cents - prior_cents) * BPS_FULL // prior_cents
