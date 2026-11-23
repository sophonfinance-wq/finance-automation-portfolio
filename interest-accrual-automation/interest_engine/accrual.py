"""
The accrual arithmetic, defined once.
=====================================

Rebuilding a note's interest from its terms is the single operation this whole
engine is built around, so it lives here alone and both the generator and the
controls import it. That is deliberate: if the engine re-derived an accrual by
*different* arithmetic than the one that produced it, the two would disagree on
the edge cases -- a truncated fraction of a cent, a period that ends exactly on
the maturity date, a rate that steps on the day of an event of default -- and the
re-derivation control would be measuring the disagreement between two
implementations rather than the correctness of the number.

Everything here works on already-extracted primitives -- integer cents, integer
basis points, integer day counts and :class:`datetime.date` objects -- so the
caller owns reading (and, in the engine's case, integer-validating) the raw
fields. That keeps the kernel free of JSON-shape and money-coercion concerns and
makes the boundary rules -- interest truncated to the cent, an ending balance
rebuilt from its beginning, a rate that steps *on* the event date, a maturity
*at* the edge of the lead window -- state exactly once.
"""

from __future__ import annotations

from datetime import date

from .money import BPS_FULL


def accrued_interest(beginning_cents: int, rate_bps: int, days: int, denom: int) -> int:
    """Interest accrued over one period, truncated to the cent.

    The contract is ``beginning x rate x days / (year)`` with **truncating**
    integer division, exactly as :func:`interest_engine.money.apply_rate`
    truncates a rated figure: a number derived elsewhere the same way compares to
    the reported figure with exact ``==``. The rate is integer basis points and
    the year is the day-count denominator (``365`` for actual/365, ``360`` for
    30/360), so the whole computation stays in integers and never touches a float.

    Args:
        beginning_cents: The balance interest accrues on, in integer cents.
        rate_bps: The annual rate in integer basis points (``700`` == 7.00%).
        days: The number of days in the period.
        denom: The day-count denominator (days in the accrual year).

    Returns:
        The accrued interest in integer cents, truncated toward zero.
    """
    return beginning_cents * rate_bps * days // (BPS_FULL * denom)


def ending_balance(
    beginning_cents: int, advance_cents: int, accrued_cents: int, payment_cents: int
) -> int:
    """The period's ending balance, rebuilt from its parts.

    ``ending = beginning + advance + accrued - payment``. This is the roll-forward
    identity every schedule row is supposed to satisfy and the next row's
    beginning is supposed to continue from.
    """
    return beginning_cents + advance_cents + accrued_cents - payment_cents


def period_rate_bps(
    stated_rate_bps: int,
    default_rate_bps: int,
    period_start: date,
    default_event_date: date | None,
) -> int:
    """The rate a period should accrue at, given the note's terms.

    The default rate steps in **on** the event date: a period beginning on or
    after ``default_event_date`` accrues at ``default_rate_bps``; every period
    before it accrues at the stated rate. When there is no event of default the
    stated rate governs throughout.
    """
    if default_event_date is not None and period_start >= default_event_date:
        return default_rate_bps
    return stated_rate_bps


def reduces_principal(payment_cents: int, accrued_cents: int) -> bool:
    """Whether a payment relieves principal, not just the period's interest.

    A payment at or below the interest accrued in the period is interest service;
    anything above it pays principal down. Prepayment and subordination gates key
    on that distinction, so it is stated once here.
    """
    return payment_cents > accrued_cents


def within_maturity_window(maturity: date, as_of: date, lead_days: int) -> bool:
    """Whether a note is due to mature inside the lead-time window.

    The window is the half-open span ``(as_of, as_of + lead_days]``: a note that
    has already matured (``maturity <= as_of``) is past due, not upcoming, and a
    note maturing exactly ``lead_days`` out is still inside the window.
    """
    remaining = (maturity - as_of).days
    return 0 < remaining <= lead_days
