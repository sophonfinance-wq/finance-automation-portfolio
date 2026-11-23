"""
The issuance predicate, defined once.
=====================================

Deciding whether a payee/box owes a form, and what has to be withheld on it, is
the single operation this whole engine is built around, so it lives here alone
and both the generator and the controls import it. That is deliberate: if the
engine recomputed a form's requirement by *different* logic than the one that
produced it, the two would disagree on the edge cases -- a total landing exactly
on the threshold, a payee with no taxpayer number paid a token amount, a shortfall
sitting exactly at the edge of the review band -- and the tie-out control would be
measuring the disagreement between two implementations rather than the
correctness of the determination.

Everything here works on already-extracted primitives -- integer cents, booleans
and :class:`datetime.date` objects -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw fields. That keeps the kernel free of
JSON-shape and money-coercion concerns and makes the boundary rules -- a
threshold met *at* the cent, a payment made *on* the last day of the year, a
shortfall *at* the edge of the band -- state exactly once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .money import apply_rate

#: Taxpayer numbers in the fictional regime modelled here: the literal prefix
#: ``FTN-`` followed by exactly nine digits. Invented, and deliberately unlike any
#: real identifier format.
_TIN_RE = re.compile(r"^FTN-\d{9}$")


@dataclass(frozen=True)
class BoxRule:
    """A box-catalog row reduced to the facts the predicate needs."""

    threshold_cents: int
    withholding_applies: bool


def tin_well_formed(value: object) -> bool:
    """Whether ``value`` is a well-formed taxpayer number.

    Shape only. A well-formed number is not a verified one, and this engine makes
    no claim that it is -- but a number that cannot even be parsed is one that was
    never captured, and every downstream treatment turns on whether it is there.
    """
    return isinstance(value, str) and bool(_TIN_RE.match(value))


def form_required(total_cents: int, rule: BoxRule, tin_present: bool) -> bool:
    """Whether a payee/box owes an information return.

    Two independent reasons oblige a form. The ordinary one is the box threshold,
    met **at** the cent: a year total of exactly the threshold is reportable and a
    cent under it is not. The second overrides the threshold entirely -- where the
    box attracts backup withholding and the payee has no taxpayer number on file,
    tax is withheld on the payment, and withheld tax has to be reported however
    small the payment was.
    """
    if total_cents >= rule.threshold_cents:
        return True
    return rule.withholding_applies and not tin_present and total_cents > 0


def backup_withholding_cents(
    total_cents: int, rule: BoxRule, tin_present: bool, rate_bps: int
) -> int:
    """Backup withholding due on a reported box amount.

    Zero unless the box attracts withholding *and* the payee has no taxpayer
    number on file; otherwise the statutory rate applied to the reported amount
    with :func:`~inforeturn_engine.money.apply_rate`, which is truncating integer
    basis-point math, so the reported figure can be compared to the derived one
    with exact ``==``. A negative amount withholds nothing: a reversal is not a
    payment to withhold against.
    """
    if not rule.withholding_applies or tin_present or total_cents <= 0:
        return 0
    return apply_rate(total_cents, rate_bps)


def near_threshold_shortfall(
    total_cents: int, rule: BoxRule, tin_present: bool, band_cents: int
) -> int | None:
    """How far a payee/box sits below its threshold, when that is worth a look.

    Returns the shortfall in cents when the payee owes no form but lands inside
    the review band, and ``None`` otherwise. The band is the half-open span
    ``[threshold - band_cents, threshold)``: a total exactly ``band_cents`` short
    is inside it, and a total that has reached the threshold owes a form and is
    not a near miss at all.
    """
    if form_required(total_cents, rule, tin_present):
        return None
    shortfall = rule.threshold_cents - total_cents
    if 0 < shortfall <= band_cents:
        return shortfall
    return None


def paid_in_year(paid: date, year_start: date, year_end: date) -> bool:
    """Whether a payment date falls inside the reporting year.

    Inclusive of both endpoints: a payment made **on** the last day of the year
    belongs to that year's population, and one made the day after belongs to the
    next year's.
    """
    return year_start <= paid <= year_end
