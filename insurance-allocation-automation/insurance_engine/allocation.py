"""
The allocation primitive, defined once.
=======================================

Turning a set of basis values into integer basis-point weights is the single
operation this whole engine is built around, so it lives here alone and both the
generator and the controls import it. That is deliberate: if the engine re-derived
an allocation by a *different* method than the one that produced it, every share
would disagree by a cent or two and the controls would be measuring the
disagreement between two roundings rather than the correctness of the allocation.

The method is largest remainder (Hamilton), the same one
:func:`~insurance_engine.money.allocate_by_ratio` uses to turn weights back into
cents. Applying it twice -- values to weights, weights to cents -- is what makes
the residual land in exactly one place and stay there.
"""

from __future__ import annotations

from collections.abc import Sequence

from .money import BPS_FULL


def basis_weights_bps(values: Sequence[int]) -> list[int]:
    """Convert basis values into integer basis-point weights summing to 10000.

    Each weight is the floor of its exact share, and the leftover basis points are
    handed out to the largest fractional remainders first -- ties broken by
    position, so the result is stable rather than merely correct.

    Args:
        values: Basis values (hard cost in cents, insured value in cents, unit
            counts -- any non-negative integers on a common scale).

    Returns:
        One integer basis-point weight per value, summing to exactly 10000.

    Raises:
        ValueError: If ``values`` is empty or its total is not positive. An
            allocation across nothing, or across a basis that sums to zero, has no
            defensible answer -- and inventing an even split would hide the fact
            that the basis data never arrived.
    """
    if not values:
        raise ValueError("cannot allocate across an empty basis")
    total = sum(values)
    if total <= 0:
        raise ValueError(f"basis must sum to a positive value; got {total}")

    floors = [v * BPS_FULL // total for v in values]
    remainders = sorted(
        range(len(values)),
        key=lambda i: (-((values[i] * BPS_FULL) % total), i),
    )
    leftover = BPS_FULL - sum(floors)
    for i in range(leftover):
        floors[remainders[i]] += 1
    return floors
