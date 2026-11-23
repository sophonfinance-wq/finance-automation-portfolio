"""
The rollforward arithmetic, defined once.
=========================================

Rolling a contingency bucket forward -- and deciding, from the balance that
survives, whether it is adequate -- is the single operation this whole engine is
built around, so it lives here alone and both the generator and the controls
import it. That is deliberate: if the engine recomputed a bucket's current
balance or its adequacy word by *different* logic than the one that produced it,
the two would disagree on the edge cases -- a projected use exactly equal to the
balance, a draw exactly equal to the headroom, a bucket sitting exactly on the
watch band -- and the tie-out controls would be measuring the disagreement
between two implementations rather than the correctness of the block.

Everything here works on already-extracted primitives -- integer cents and
integer basis points -- so the caller owns reading (and, in the engine's case,
integer-validating) the raw fields. That keeps the kernel free of JSON-shape and
money-coercion concerns and makes the boundary rules -- adequate *at* the
projection, a draw allowed *at* the remaining balance, a bucket watched *at* the
band -- state exactly once.
"""

from __future__ import annotations

from collections.abc import Sequence

from .model import ADEQUACY_ADEQUATE, ADEQUACY_INADEQUATE
from .money import apply_rate


def current_balance(prior_balance_cents: int, allocated_period_cents: int) -> int:
    """The balance a bucket carries out of the period.

    The whole of the rollforward: what was there, less what was allocated against
    it. Nothing is netted in from the other bucket and nothing is added back, so
    a restored draw is a negative line item in the register, never a silent
    adjustment to the balance.
    """
    return prior_balance_cents - allocated_period_cents


def allocated_to_date(allocated_prior_cents: int, allocated_period_cents: int) -> int:
    """Cumulative allocation against a bucket, through the end of the period."""
    return allocated_prior_cents + allocated_period_cents


def headroom(current_balance_cents: int, projected_use_cents: int) -> int:
    """What is left after the projected potential use is honoured.

    Negative headroom is the definition of an inadequate bucket: the report has
    already named more potential use than the balance behind it.
    """
    return current_balance_cents - projected_use_cents


def assess_adequacy(current_balance_cents: int, projected_use_cents: int) -> str:
    """The adequacy word the two amounts produce.

    A bucket is adequate when the balance remaining meets the projected potential
    use **at** the projection: ``>=``, not ``>``. A bucket that exactly covers what
    it is expected to spend is adequate, and one cent short of it is not.
    """
    if headroom(current_balance_cents, projected_use_cents) >= 0:
        return ADEQUACY_ADEQUATE
    return ADEQUACY_INADEQUATE


def within_watch_band(
    current_balance_cents: int, projected_use_cents: int, watch_bps: int
) -> bool:
    """Whether an adequate bucket's headroom is thin enough to be watched.

    The band is a share of what is left, in integer basis points, applied through
    the shared truncating :func:`~contingency_engine.money.apply_rate` so the
    threshold is an exact integer-cent figure rather than a rounded one. A bucket
    sitting exactly **on** the band is inside it.

    An inadequate bucket is not watched and an exhausted one is not watched: the
    first is a hard failure that a separate control owns, and the second has no
    balance left for a share of it to mean anything.
    """
    if current_balance_cents <= 0:
        return False
    if projected_use_cents > current_balance_cents:
        return False
    return projected_use_cents >= apply_rate(current_balance_cents, watch_bps)


def first_overdraw(
    prior_balance_cents: int, draws: Sequence[tuple[str, int]]
) -> tuple[str, int, int] | None:
    """The first draw that exceeds the balance standing in front of it.

    The draws are walked in the order they were taken, each one measured against
    what the ones before it left behind. That is the only way the control can name
    the draw that broke the bucket rather than merely observing that the bucket
    ended up negative -- by the time the period total is compared, the individual
    overdraw has already been averaged into it.

    A draw exactly equal to the remaining balance is allowed: it spends the bucket
    to zero, which is what a contingency is for.

    Args:
        prior_balance_cents: Balance the bucket carried into the period.
        draws: ``(allocation_id, amount_cents)`` pairs, in draw order.

    Returns:
        ``(allocation_id, amount_cents, remaining_before_cents)`` for the first
        offending draw, or ``None`` when every draw fits.
    """
    remaining = prior_balance_cents
    for allocation_id, amount_cents in draws:
        if amount_cents > remaining:
            return (allocation_id, amount_cents, remaining)
        remaining -= amount_cents
    return None
