"""
The withholding determination, defined once.
============================================

Deciding the withholding rate that a cross-border FDAP payment is actually
subject to is the single determination this whole engine is built around, so it
lives here alone and both the generator and the controls import it. That is
deliberate: if the engine recomputed a payment's applicable rate by *different*
logic than the one that produced it, the two would disagree on the edge cases --
a payee whose W-8 expires on the review date, a portfolio-interest coupon that is
actually contingent, a non-participating FFI that also holds a treaty claim -- and
the rate-recompute control would be measuring the disagreement between two
implementations rather than the correctness of the determination.

Everything here works on already-extracted primitives -- booleans, integer
basis-point rates and :class:`datetime.date` objects -- so the caller owns reading
(and integer-validating) the raw fields. That keeps the kernel free of JSON-shape
and money-coercion concerns and lets the boundary rules -- a W-8 valid *through*
the review date, an exemption that turns off *at* contingency, a treaty rate the
table simply does not carry -- state exactly once.

The order of precedence is the whole of the rule
------------------------------------------------
A single payment can satisfy several reductions at once, and they do not commute.
FATCA (Chapter 4) comes first: a non-participating FFI is withheld at the
statutory rate no matter what treaty its residence country signed. Only then does
the portfolio-interest exemption apply, and only to interest that is *not*
contingent. Only then is a treaty rate looked up, and only behind a valid W-8.
Everything that reaches the bottom is withheld at the statutory default. Encoding
that order here, once, is what keeps a treaty payee who is also a non-participating
FFI from being quietly under-withheld.
"""

from __future__ import annotations

from datetime import date

#: Statutory Chapter 3 withholding rate on FDAP, in basis points (30.00%).
STATUTORY_RATE_BPS = 3000

#: The portfolio-interest exemption and treaty relief both bottom out at 0%.
EXEMPT_RATE_BPS = 0


def w8_is_valid(
    has_valid_w8: bool, w8_status_ok: bool, expiration: date | None, as_of: date
) -> bool:
    """Whether a payee's Form W-8 supports a treaty claim as of ``as_of``.

    A W-8 is valid only when the payee attests one is on file, its status reads
    valid, and its three-year term has not run out. Expiry is ``expiration <=
    as_of``: a form whose term ends exactly on the review date has already lapsed,
    so a treaty claim resting on it is unsupported that day.
    """
    if not has_valid_w8 or not w8_status_ok or expiration is None:
        return False
    return expiration > as_of


def within_renewal_window(expiration: date, as_of: date, lead_days: int) -> bool:
    """Whether a Form W-8 is due for renewal inside the lead-time window.

    The window is the half-open span ``(as_of, as_of + lead_days]``: a form that
    has already lapsed (``expiration <= as_of``) is expired, not renewing, and one
    whose term ends exactly ``lead_days`` out is still inside the window.
    """
    remaining = (expiration - as_of).days
    return 0 < remaining <= lead_days


def determined_rate_bps(
    *,
    is_nonparticipating_ffi: bool,
    is_portfolio_interest: bool,
    is_contingent_interest: bool,
    w8_valid: bool,
    treaty_rate_bps: int | None,
    statutory_bps: int = STATUTORY_RATE_BPS,
) -> int | None:
    """The withholding rate a *subject* FDAP payment is actually subject to.

    Called only for payments that are subject to Chapter 3 withholding at all --
    paid (not merely accrued) to a non-US person. The caller owns that gate; this
    function owns the rate once the payment is in scope.

    Returns the applicable rate in basis points, or ``None`` when the payment
    reaches the treaty branch and the rate table carries no row for its
    (country, income-type) pair -- an absent row is a completeness failure a
    separate control owns, not a rate this kernel may invent.
    """
    # Chapter 4 first: a non-participating FFI is withheld at the statutory rate
    # regardless of any treaty its residence country signed.
    if is_nonparticipating_ffi:
        return statutory_bps
    # Portfolio interest is exempt, but only when it is not contingent interest.
    if is_portfolio_interest and not is_contingent_interest:
        return EXEMPT_RATE_BPS
    # A treaty rate applies only behind a valid W-8; the rate itself comes from
    # the table, which may or may not carry the row.
    if w8_valid:
        return treaty_rate_bps
    # Everything else falls to the statutory default.
    return statutory_bps
