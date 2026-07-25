"""
The avoided-cost capitalization arithmetic, defined once.
=========================================================

Splitting a project's quarterly interest into the portion that must be
capitalized and the portion that may be deducted is the single operation this
whole engine is built around, so it lives here alone and both the generator and
the controls import it. That is deliberate: if the engine recomputed a
capitalized figure by *different* arithmetic than the one that produced it, the
two would disagree on the edge cases -- a truncated cent on the rate, a quarter
that rolls to exactly the annual total -- and the tie-out control would be
measuring the disagreement between two implementations rather than the
correctness of the schedule.

Everything here works on already-extracted primitives -- integer cents and
integer basis-point rates -- so the caller owns reading (and, in the engine's
case, integer-validating) the raw fields. The one arithmetic decision the method
turns on is stated exactly once, here: the capitalized interest for a quarter is
the period rate applied to that quarter's accumulated production expenditures,
computed with the platform's truncating :func:`~capitalize_engine.money.apply_rate`
so a derived figure compares to a reported figure with exact ``==``.
"""

from __future__ import annotations

from collections.abc import Iterable

from .money import apply_rate


def capitalized_for_quarter(ape_cents: int, rate_bps: int) -> int:
    """Avoided-cost interest capitalized for one quarter.

    Under the avoided-cost method the interest a quarter's production could have
    avoided is the period rate applied to the accumulated production
    expenditures tied up in the project that quarter. ``apply_rate`` truncates,
    so this re-derives the reported figure with exact ``==``.

    Args:
        ape_cents: Accumulated production expenditures for the quarter, in cents.
        rate_bps: The period capitalization rate, in basis points.

    Returns:
        The interest to capitalize for the quarter, in integer cents.
    """
    return apply_rate(ape_cents, rate_bps)


def deducted_for_quarter(interest_expense_cents: int, capitalized_cents: int) -> int:
    """The deductible remainder of a quarter's interest.

    Interest not required to be capitalized is deducted, so the deducted portion
    is exactly what is left of the interest incurred once the capitalized portion
    is carved out. Defined here so the identity ``interest == capitalized +
    deducted`` is stated once and cannot leak.

    Args:
        interest_expense_cents: Interest incurred on the project that quarter.
        capitalized_cents: The portion capitalized, from
            :func:`capitalized_for_quarter`.

    Returns:
        The deducted portion, in integer cents (negative if the capitalized
        portion exceeds the interest incurred, which ``cap_within_interest``
        exists to catch).
    """
    return interest_expense_cents - capitalized_cents


def roll_capitalized(ape_by_quarter: Iterable[int], rate_bps: int) -> int:
    """Annual capitalized interest, rolled across the quarter grid.

    The annual figure is the quarters summed, not a rate applied to a full-year
    expenditure, because each quarter carries its own accumulated balance. This
    is the "rolled by quarter" the schedule's annual column is meant to be.

    Args:
        ape_by_quarter: Accumulated production expenditures, one per quarter.
        rate_bps: The period capitalization rate, in basis points.

    Returns:
        The annual capitalized interest, in integer cents.
    """
    return sum(capitalized_for_quarter(ape, rate_bps) for ape in ape_by_quarter)


def ending_capitalized(prior_year_cents: int, current_year_cents: int) -> int:
    """The capitalized basis carried to the end of the year.

    The comparison tab rolls the prior year's ending capitalized balance forward
    and adds the current year's capitalized interest. Stating the rollforward
    here keeps ``ending == prior + current`` a single definition the comparison
    control recomputes against.
    """
    return prior_year_cents + current_year_cents
