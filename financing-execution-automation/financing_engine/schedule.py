"""
The schedule-derivation kernel, defined once.
=============================================

Turning a milestone's dates into a variance, deciding whether a milestone is
overdue, and placing a Gantt bar in a month are the derivations this whole engine
is built around, so they live here alone and both the generator and the controls
import them. That is deliberate: if the engine recomputed a variance by
*different* arithmetic than the one that produced it, the two would disagree on
the edge cases -- a milestone falling exactly on the report date, a span that
crosses a month boundary -- and the tie-out control would be measuring the
disagreement between two implementations rather than the correctness of the
number.

Everything here works on already-extracted primitives -- :class:`datetime.date`
objects, booleans and small ints -- so the caller owns reading (and, in the
engine's case, validating) the raw fields. That keeps the kernel free of
JSON-shape concerns and makes the boundary rules -- overdue *on* the report date,
a variance measured *in whole days* -- state exactly once.
"""

from __future__ import annotations

import calendar
from datetime import date


def variance_days(prior: date, current: date) -> int:
    """The schedule variance of a milestone, in whole calendar days.

    Defined as ``Current - Prior``: a milestone whose current date is later than
    its prior date has slipped by a positive number of days, and one pulled
    forward carries a negative variance. This is the exact figure the ``Variance``
    column is meant to hold, so the control can compare with ``==``.
    """
    return (current - prior).days


def is_overdue(current: date, report_date: date, active: bool) -> bool:
    """Whether an active milestone's current date has already passed the report.

    A milestone is overdue when its workstream is ``ACTIVE`` and its current
    target date is strictly before the report date: a date landing exactly **on**
    the report date is due today, not yet overdue. A closed workstream is never
    overdue -- its milestones are behind it, not ahead of it.
    """
    return active and current < report_date


def gantt_month(target_closing: date) -> int:
    """The month (1-12) a summary Gantt bar should be placed in.

    The bar sits in the month the deal is set to close, so its placement is simply
    ``MONTH(Target Closing)``. Reading the month back off the target date is what
    lets the control prove the drawn bar and the closing date have not drifted
    apart.
    """
    return target_closing.month


def period_end(period: str) -> date | None:
    """The last calendar day of a ``YYYY-MM`` report period, or ``None``.

    The report date is meant to be the period-end date, so the gate needs the last
    day of the report month -- 28th, 29th, 30th or 31st depending on the month and
    the year. Returns ``None`` when ``period`` is not a readable ``YYYY-MM`` label,
    leaving the calling control to own that malformed-input finding.
    """
    if not isinstance(period, str) or len(period) != 7 or period[4] != "-":
        return None
    year_text, month_text = period[:4], period[5:]
    if not (year_text.isdigit() and month_text.isdigit()):
        return None
    year, month = int(year_text), int(month_text)
    if not 1 <= month <= 12:
        return None
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)
