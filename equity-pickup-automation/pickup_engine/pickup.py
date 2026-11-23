"""
The pickup arithmetic, defined once.
====================================

Deriving a parent's share of a subsidiary's result -- and rolling the
investment forward, and accruing the preferred return -- is the single family
of operations this whole engine is built around, so it lives here alone and
both the generator and the controls import it. That is deliberate: if the
engine recomputed a pickup by *different* logic than the one that produced it,
the two would disagree on the edge cases -- an odd-cent income split 50/50, a
truncated day-count accrual, a loss year -- and the tie-out control would be
measuring the disagreement between two implementations rather than the
correctness of the determination.

Everything here works on already-extracted primitives -- integer cents,
integer basis points and :class:`datetime.date` objects -- so the caller owns
reading (and, in the engine's case, integer-validating) the raw fields. That
keeps the kernel free of JSON-shape and money-coercion concerns and makes the
boundary rules -- floor division on a share, the residual cent to the final
holder, an inclusive day count -- state exactly once.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from .money import BPS_FULL


def share_of(amount_cents: int, ownership_bps: int) -> int:
    """One holder's ownership share of an amount, in integer cents.

    Floor division is the contract: a figure derived elsewhere as a percentage
    of a base is derived the same way, so the engine can compare the reported
    figure to the derived one with exact ``==``. Python's floor rounds toward
    negative infinity, which keeps a loss share deterministic too.
    """
    return amount_cents * ownership_bps // BPS_FULL


def allocate_shares(amount_cents: int, holder_bps: Sequence[int]) -> list[int]:
    """Split an amount across holders by ownership, penny-exactly when whole.

    Each holder receives :func:`share_of` its basis points. When the holders
    together own exactly 100.00% the residual cent(s) left by floor division
    are assigned to the **final** holder, so the shares sum back to the amount
    they divide -- an allocation that loses a penny against the income it
    allocates has not been allocated. When the holders own less than the whole
    (a partially-held sub) there is no residual to assign and each share stands
    on its own.

    Args:
        amount_cents: The amount being shared (net income, distributions).
        holder_bps: Ownership of each holder, in basis points, in a stable
            order the caller owns (the engine orders by holding id).

    Returns:
        One integer-cent share per holder, in the same order.
    """
    shares = [share_of(amount_cents, bps) for bps in holder_bps]
    if shares and sum(holder_bps) == BPS_FULL:
        shares[-1] = amount_cents - sum(shares[:-1])
    return shares


def rollforward_end(
    begin_cents: int, contributions_cents: int, pickup_cents: int, distributions_cents: int
) -> int:
    """The investment roll-forward identity, stated once.

    ``end = begin + contributions + pickup - distributions``. Every carrying
    value the engine re-derives -- and every carrying value the generator
    states -- comes through this one line.
    """
    return begin_cents + contributions_cents + pickup_cents - distributions_cents


def inclusive_days(start: date, end: date) -> int:
    """Day count of a period, inclusive of both endpoints.

    A period running from the 1st to the 30th is 30 days, not 29 -- the accrual
    formula in the source workpapers counts ``(end - start + 1)`` and the
    engine counts the same way, so the two can be compared with ``==``.
    """
    return (end - start).days + 1


def preferred_accrual(
    opening_capital_cents: int, rate_bps: int, days: int, day_basis: int
) -> int:
    """Preferred return accrued for one period, in integer cents.

    ``capital x rate x days / basis`` with a single truncating division at the
    end, so no intermediate rounding can drift the figure. The accrual is
    earned on the **opening** capital balance of the period -- a contribution
    received during the period starts earning in the next one -- and it does
    not compound: the accrued return is tracked beside the capital balance,
    never added into it.
    """
    return opening_capital_cents * rate_bps * days // (BPS_FULL * day_basis)
