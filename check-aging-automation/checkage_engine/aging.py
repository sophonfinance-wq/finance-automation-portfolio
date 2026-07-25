"""
The aging predicates, defined once.
===================================

Deciding whether a check is still outstanding, how old it is, which band it falls
in, and whether the clock has run far enough to require follow-up or escheatment
is the single operation this whole engine is built around. So it lives here alone
and both the generator and the controls import it.

That is deliberate. If the engine re-derived the outstanding set by *different*
logic than the one that produced it, the two would disagree on exactly the edge
cases that matter -- a check cleared for zero, a check dated on the as-of date, an
item sitting on the stale-dating threshold to the day -- and the tie-out controls
would be measuring the disagreement between two implementations rather than the
correctness of the schedule.

Everything here works on already-extracted primitives -- integer cents and
:class:`datetime.date` objects -- so the caller owns reading (and, in the engine's
case, integer-validating) the raw fields. That keeps the kernel free of JSON-shape
and money-coercion concerns and makes the boundary rules state exactly once:

* **Outstanding** means cleared amount of exactly zero *and* no cleared date, and
  the check is not in the void register. Either half alone is ambiguous: a
  zero cleared amount with a cleared date is a cleared zero-dollar item, and a
  cleared date with no amount is a register that is mid-edit.
* **Age** is whole days from the check date to the as-of date, so an item issued
  on the as-of date is nought days old, not one.
* **Stale-dated** and **dormant** are both strictly past the threshold: an item
  sitting exactly on the threshold day has not yet crossed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .model import AGING_BUCKETS


@dataclass(frozen=True)
class CheckLine:
    """A check-register row reduced to the facts the predicates need."""

    account_id: str
    check_number: str
    check_date: date
    check_amount_cents: int
    cleared_amount_cents: int
    cleared_date: date | None


def is_outstanding(line: CheckLine, voided_keys: frozenset[tuple[str, str]]) -> bool:
    """Whether a check is still outstanding at the as-of date.

    A check is outstanding when nothing has cleared against it -- cleared amount
    of exactly zero **and** no cleared date -- and it has not been withdrawn by a
    void, zero-dollar or stop-payment entry. A withdrawn check is not an
    obligation, so counting it as outstanding would put a cancelled promise on
    the bank reconciliation.

    Args:
        line: The check-register row.
        voided_keys: ``(account_id, check_number)`` of every void-register entry.

    Returns:
        ``True`` when the check belongs in the outstanding set.
    """
    if (line.account_id, line.check_number) in voided_keys:
        return False
    if line.cleared_amount_cents != 0:
        return False
    return line.cleared_date is None


def age_days(check_date: date, as_of: date) -> int:
    """Whole days from the check date to the as-of date.

    A check issued on the as-of date is nought days old. A negative result means
    the check is dated after the as-of date, which a separate control owns; the
    arithmetic here does not hide it.
    """
    return (as_of - check_date).days


def bucket_for(age: int) -> str:
    """The aging band an age in days falls in.

    Bands are inclusive of their upper bound and are read in
    :data:`~checkage_engine.model.AGING_BUCKETS` order, so the first band whose
    bound the age does not exceed wins and the final open-ended band catches
    everything older.
    """
    for label, upper in AGING_BUCKETS:
        if upper is None or age <= upper:
            return label
    return AGING_BUCKETS[-1][0]


def is_stale_dated(age: int, stale_dated_days: int) -> bool:
    """Whether an outstanding item has passed the stale-dating threshold.

    Strictly greater than the threshold: an item sitting exactly on the threshold
    day is at the boundary, not past it. A stale-dated item needs a human -- the
    payee chased, the check re-issued, or the item re-voided -- which is why the
    control that reads this is a review flag rather than a hard failure.
    """
    return age > stale_dated_days


def is_dormant(age: int, dormancy_days: int) -> bool:
    """Whether an outstanding item has run the full dormancy period.

    Strictly greater than the period, on the same convention as
    :func:`is_stale_dated`. Once true the item is unclaimed property: it belongs
    to the escheat jurisdiction of the account it was drawn on, not to the entity
    that wrote it.
    """
    return age > dormancy_days
