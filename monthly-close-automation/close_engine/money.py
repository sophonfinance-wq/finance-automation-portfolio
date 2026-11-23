"""Money primitives for the close engine.

All monetary amounts inside the engine are stored as **integer cents** to make
arithmetic exact and tie-outs deterministic. Floating-point dollars are never
used for accumulation or comparison; they appear only at the formatting edge.

A handful of small helpers handle the two operations that can lose pennies:

* ``split_evenly`` distributes an amount across N periods so the parts sum back
  to the whole (the rounding remainder lands on the final period).
* ``allocate_by_ratio`` splits an amount by integer basis-point weights using
  the largest-remainder method, guaranteeing the parts sum to the original.
"""

from __future__ import annotations

from typing import Iterable, Sequence

# A cent is the atomic unit. 100 cents == 1 currency unit (USD, fictional).
CENTS_PER_UNIT = 100


def to_cents(amount: float | int | str) -> int:
    """Convert a dollar amount to integer cents, rounding half-up.

    Args:
        amount: A dollar figure (e.g. ``1200.00`` or ``"1200.00"``).

    Returns:
        The amount expressed as an integer number of cents.
    """
    # Use Decimal-free rounding via scaled integer to stay stdlib-light and
    # avoid binary float drift on the boundary.
    dollars = float(amount)
    # Round half up on the cent.
    return int((dollars * CENTS_PER_UNIT) + (0.5 if dollars >= 0 else -0.5))


def fmt(cents: int) -> str:
    """Format integer cents as a fixed two-decimal dollar string.

    Args:
        cents: Amount in integer cents (may be negative).

    Returns:
        A string like ``"1,200.00"`` or ``"-50.00"`` (no currency symbol).
    """
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), CENTS_PER_UNIT)
    return f"{sign}{whole:,}.{frac:02d}"


def split_evenly(total_cents: int, periods: int) -> list[int]:
    """Split a total into ``periods`` equal integer-cent parts.

    The parts sum exactly to ``total_cents``; any rounding remainder is added
    to the **final** part so straight-line schedules never drift.

    Args:
        total_cents: Amount to split, in cents.
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
    exactly to ``total_cents`` with no penny lost or created.

    Args:
        total_cents: Amount to allocate, in cents.
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
    # Floor allocation plus distribution of the remainder by largest fraction.
    floors: list[int] = []
    remainders: list[tuple[int, int]] = []  # (fractional_remainder, index)
    for idx, w in enumerate(weights_bps):
        exact = total_cents * w
        floor = exact // 10000
        floors.append(floor)
        remainders.append((exact - floor * 10000, idx))
    leftover = total_cents - sum(floors)
    # Hand out the leftover cents to the largest fractional remainders first.
    remainders.sort(key=lambda t: (-t[0], t[1]))
    for i in range(leftover):
        floors[remainders[i][1]] += 1
    return floors


def total(amounts: Iterable[int]) -> int:
    """Sum an iterable of integer-cent amounts."""
    return sum(amounts)
