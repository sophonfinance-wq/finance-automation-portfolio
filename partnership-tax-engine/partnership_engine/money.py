"""Money primitives for the partnership-tax engine.

All monetary amounts inside the engine are stored as **integer cents** so that
capital-account roll-forwards and §704(c) layer arithmetic are exact and tie out
to the penny. Floating-point dollars are never used for accumulation or
comparison; they appear only at the formatting edge.

Two helpers handle the operations that can otherwise lose pennies:

* ``split_evenly`` distributes an amount across N periods so the parts sum back
  to the whole (the rounding remainder lands on the final period). Used for
  straight-line book and tax depreciation.
* ``allocate_by_ratio`` splits an amount by integer basis-point weights using
  the largest-remainder (Hamilton) method, guaranteeing the parts sum to the
  original. Used to allocate book items among partners by their interest %.
"""

from __future__ import annotations

from typing import Iterable, Sequence

# A cent is the atomic unit. 100 cents == 1 currency unit (USD, fictional).
CENTS_PER_UNIT = 100


def to_cents(amount: float | int | str) -> int:
    """Convert a dollar amount to integer cents, rounding half away from zero.

    Args:
        amount: A dollar figure (e.g. ``1200.00`` or ``"1200.00"``).

    Returns:
        The amount expressed as an integer number of cents.
    """
    # Scaled-integer rounding keeps us stdlib-light and avoids binary float drift
    # right on the half-cent boundary.
    dollars = float(amount)
    return int((dollars * CENTS_PER_UNIT) + (0.5 if dollars >= 0 else -0.5))


def fmt(cents: int) -> str:
    """Format integer cents as a fixed two-decimal dollar string.

    Negatives are rendered in accounting parentheses, e.g. ``"(50.00)"``, to
    match the convention used across the workpaper reports.

    Args:
        cents: Amount in integer cents (may be negative).

    Returns:
        A string like ``"1,200.00"`` or ``"(50.00)"`` (no currency symbol).
    """
    whole, frac = divmod(abs(cents), CENTS_PER_UNIT)
    body = f"{whole:,}.{frac:02d}"
    return f"({body})" if cents < 0 else body


def split_evenly(total_cents: int, periods: int) -> list[int]:
    """Split a total into ``periods`` equal integer-cent parts.

    The parts sum exactly to ``total_cents``; any rounding remainder is added to
    the **final** part so straight-line depreciation schedules never drift.

    Args:
        total_cents: Amount to split, in cents (may be negative).
        periods: Number of periods (must be >= 1).

    Returns:
        A list of ``periods`` integer-cent amounts summing to ``total_cents``.

    Raises:
        ValueError: If ``periods`` < 1.
    """
    if periods < 1:
        raise ValueError("periods must be >= 1")
    base = total_cents // periods
    parts = [base] * periods
    remainder = total_cents - base * periods
    parts[-1] += remainder
    return parts


def allocate_by_ratio(total_cents: int, weights_bps: Sequence[int]) -> list[int]:
    """Allocate a total across weights given in basis points (sum == 10000).

    Uses the largest-remainder (Hamilton) method so the allocated parts sum
    exactly to ``total_cents`` with no penny lost or created. Works for negative
    totals too (a book loss allocated among partners), with the leftover applied
    toward the largest fractional remainders in magnitude.

    Args:
        total_cents: Amount to allocate, in cents (may be negative).
        weights_bps: Integer basis-point weights; must sum to 10000 (100.00%).

    Returns:
        A list of integer-cent allocations, one per weight, summing to
        ``total_cents``.

    Raises:
        ValueError: If the weights do not sum to exactly 10000 basis points.
    """
    if sum(weights_bps) != 10000:
        raise ValueError(
            f"allocation weights must sum to 10000 bps (100.00%); "
            f"got {sum(weights_bps)}"
        )
    sign = -1 if total_cents < 0 else 1
    magnitude = abs(total_cents)
    floors: list[int] = []
    remainders: list[tuple[int, int]] = []  # (fractional_remainder, index)
    for idx, w in enumerate(weights_bps):
        exact = magnitude * w
        floor = exact // 10000
        floors.append(floor)
        remainders.append((exact - floor * 10000, idx))
    leftover = magnitude - sum(floors)
    # Hand out the leftover cents to the largest fractional remainders first.
    remainders.sort(key=lambda t: (-t[0], t[1]))
    for i in range(leftover):
        floors[remainders[i][1]] += 1
    return [sign * f for f in floors]


def total(amounts: Iterable[int]) -> int:
    """Sum an iterable of integer-cent amounts."""
    return sum(amounts)
