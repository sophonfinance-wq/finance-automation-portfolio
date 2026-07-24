"""
The filing-obligation predicate, defined once.
==============================================

Deciding when a return or payment is *due*, and whether it was filed on time,
is the single operation this whole engine is built around, so it lives here
alone and both the generator and the controls import it. That is deliberate: if
the engine recomputed a due date -- or an obligation's filed/open/overdue status
-- by *different* logic than the one that produced it, the two would disagree on
the edge cases (a return filed exactly on the due date, a term ending exactly on
the review date, an extension with no extended date) and the tie-out control
would be measuring the disagreement between two implementations rather than the
correctness of the determination.

Everything here works on already-extracted primitives -- :class:`datetime.date`
objects, integers and booleans -- so the caller owns reading the raw JSON fields.
That keeps the kernel free of JSON-shape concerns and makes the boundary rules
state exactly once: a due date is derived by whole-month arithmetic; an
obligation is filed on time when ``return_filed <= applicable_due`` (met *at* the
deadline, not a day past it); an obligation is overdue when it is unfiled and its
applicable due date is on or before the review date.
"""

from __future__ import annotations

import calendar
from datetime import date

#: Canonical obligation statuses, recomputed from the register dates.
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_FILED = "filed"
STATUS_FILED_LATE = "filed_late"
STATUS_OVERDUE = "overdue"
STATUS_OPEN = "open"


def add_months(anchor: date, months: int) -> date:
    """Return ``anchor`` advanced by ``months`` whole calendar months.

    The day of month is clamped to the length of the target month, so a date
    landing on a short month never rolls forward into the next one. All statutory
    due dates in this engine fall on the 15th, so the clamp never bites in
    practice -- it is here so the arithmetic is total rather than merely correct
    on the shipped data.
    """
    index = anchor.month - 1 + months
    year = anchor.year + index // 12
    month = index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def derive_due_dates(
    year_end: date,
    original_month: int,
    original_day: int,
    extension_offset_months: int,
) -> tuple[date, date | None]:
    """Re-derive an obligation's ``(original_due, extended_due)`` from its year-end.

    The original due date lands on ``original_day`` of ``original_month`` in the
    first such month strictly after the fiscal year-end (so a June-30 year-end
    with a September deadline stays in the same calendar year, while a December
    year-end with a March deadline rolls into the next). The extended due date is
    the original advanced by the whole-month statutory offset, or ``None`` when the
    form carries no extension (``extension_offset_months <= 0``).
    """
    original_year = (
        year_end.year if original_month > year_end.month else year_end.year + 1
    )
    original_due = date(original_year, original_month, original_day)
    extended_due = (
        add_months(original_due, extension_offset_months)
        if extension_offset_months > 0
        else None
    )
    return original_due, extended_due


def applicable_due(
    original_due: date | None, extended_due: date | None, extension_filed: bool
) -> date | None:
    """The due date actually in force: extended when an extension was filed.

    When an extension was filed *and* an extended date exists, that is the
    controlling deadline; otherwise the original due date governs. Returns
    ``None`` only when the governing date itself is missing -- a separate control
    owns that gap.
    """
    if extension_filed and extended_due is not None:
        return extended_due
    return original_due


def obligation_status(
    the_applicable_due: date | None,
    return_filed: date | None,
    as_of: date,
    na: bool,
) -> str:
    """Recompute one obligation's status from its dates.

    - ``not_applicable`` when the obligation is marked n/a (no obligation exists).
    - ``filed`` when a return was filed on or before the applicable due date.
    - ``filed_late`` when a return was filed after it.
    - ``overdue`` when nothing was filed and the applicable due date is on or
      before the review date.
    - ``open`` when nothing was filed and the deadline is still ahead.

    A return filed **exactly on** the applicable due date is on time: the test is
    ``return_filed <= applicable_due``. An obligation whose deadline falls **on**
    the review date and is still unfiled is overdue: ``applicable_due <= as_of``.
    """
    if na:
        return STATUS_NOT_APPLICABLE
    if return_filed is not None:
        if the_applicable_due is not None and return_filed > the_applicable_due:
            return STATUS_FILED_LATE
        return STATUS_FILED
    if the_applicable_due is not None and the_applicable_due <= as_of:
        return STATUS_OVERDUE
    return STATUS_OPEN


def within_due_window(the_applicable_due: date, as_of: date, lead_days: int) -> bool:
    """Whether an unfiled obligation falls due inside the lead-time window.

    The window is the half-open span ``(as_of, as_of + lead_days]``: a deadline
    already past (``applicable_due <= as_of``) is overdue, not upcoming, and a
    deadline exactly ``lead_days`` out is still inside the window.
    """
    remaining = (the_applicable_due - as_of).days
    return 0 < remaining <= lead_days
