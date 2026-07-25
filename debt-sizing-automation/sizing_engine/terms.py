"""
The term-sheet arithmetic, defined once.
========================================

Re-deriving a deal's all-in rate, a fee against its base, an advance-rate cap and
the expiry window is what this whole engine is built around, so those operations
live here alone and both the generator and the controls import them. That is
deliberate: if the engine recomputed an all-in rate by *different* logic than the
one that produced it, the two would disagree on the edge cases -- a floor that
governs by a single basis point, a fee base that rounds at the truncation
boundary, a term sheet expiring exactly on the review date -- and the tie-out
control would be measuring the disagreement between two implementations rather
than the correctness of the figure.

Everything here works on already-extracted primitives -- integer cents, integer
basis points and :class:`datetime.date` objects -- so the caller owns reading
(and, in the engine's case, integer-validating) the raw fields. That keeps the
kernel free of JSON-shape and money-coercion concerns and makes the boundary
rules -- the floor met *at* a basis point, the cap met *at* the cent, a window
closing *at* the lead day -- state exactly once.
"""

from __future__ import annotations

from datetime import date

from .money import apply_rate


def all_in_rate_bps(index_bps: int, spread_bps: int, floor_bps: int) -> int:
    """The all-in rate: the greater of the index-plus-spread build-up and the floor.

    ``max(index + spread, floor)``. The floor governs **at** a basis point:
    a build-up equal to the floor takes the build-up, and a build-up one basis
    point under takes the floor.
    """
    return max(index_bps + spread_bps, floor_bps)


def ltc_cap_cents(cost_basis_cents: int, max_ltc_bps: int) -> int:
    """The maximum loan the advance rate allows: max loan-to-cost times cost basis.

    Derived with :func:`~sizing_engine.money.apply_rate` -- truncating integer
    basis-point math -- so the reported max loan can be compared to the cap with
    exact ``<=``.
    """
    return apply_rate(cost_basis_cents, max_ltc_bps)


def fee_base_cents(
    base_type: str,
    commitment_cents: int,
    drawn_cents: int,
    facility_cents: int,
) -> int | None:
    """The base a fee rate is struck on, or ``None`` for an unknown base type.

    ``undrawn`` is commitment less drawn. Returning ``None`` rather than raising
    lets ``fee_base_type_valid`` own the unknown-base finding, so the amount
    control skips a line it could not have priced.
    """
    if base_type == "commitment":
        return commitment_cents
    if base_type == "drawn":
        return drawn_cents
    if base_type == "undrawn":
        return commitment_cents - drawn_cents
    if base_type == "facility":
        return facility_cents
    return None


def fee_amount_cents(base_cents: int, fee_rate_bps: int) -> int:
    """A fee line's amount: its rate applied to its base, truncating.

    The same truncating basis-point math the generator used to place the amount,
    so a re-keyed amount can be compared to the derived one with exact ``==``.
    """
    return apply_rate(base_cents, fee_rate_bps)


def maturity_months(base_term_months: int, extension_options_months: list[int]) -> int:
    """The reconciled maturity: base term plus every extension option.

    A straight sum, so the stated maturity can be compared with exact ``==``. An
    option is counted whether or not it has been exercised: the term sheet's
    stated maturity is the fully-extended one.
    """
    return base_term_months + sum(extension_options_months)


def termsheet_expired(expiration: date, as_of: date) -> bool:
    """Whether a term sheet has lapsed by the review date.

    Expiry is ``expiration <= as_of``: a term sheet expiring exactly **on** the
    pricing date has already lapsed and can no longer be relied on to close.
    """
    return expiration <= as_of


def within_expiry_window(expiration: date, as_of: date, lead_days: int) -> bool:
    """Whether a term sheet is due to expire inside the lead-time window.

    The window is the half-open span ``(as_of, as_of + lead_days]``: a term sheet
    that has already lapsed (``expiration <= as_of``) is expired, not expiring,
    and one ending exactly ``lead_days`` out is still inside the window.
    """
    remaining = (expiration - as_of).days
    return 0 < remaining <= lead_days
