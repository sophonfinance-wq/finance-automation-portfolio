"""
The restatement arithmetic, defined once.
=========================================

Re-deriving a Cost to Complete, a net project revenue, a project profit, a margin
on cost, a variance column and a milestone variance in days is what this whole
engine is built around, so those operations live here alone and both the
generator and the controls import them. That is deliberate: if the engine
recomputed a variance column by *different* logic than the one that produced it,
the two would disagree on the edge cases -- a margin that truncates at the basis
point, a milestone that moves by exactly the tolerance, a profit struck on a
negative expense -- and the tie-out control would be measuring the disagreement
between two implementations rather than the correctness of the figure.

Everything here works on already-extracted primitives -- integer cents, integer
basis points and :class:`datetime.date` objects -- so the caller owns reading
(and, in the engine's case, integer-validating) the raw fields. That keeps the
kernel free of JSON-shape and money-coercion concerns and makes the boundary
rules -- the remainder exact to the cent, the margin truncated toward zero, the
sign convention on a schedule variance, a slip met *at* the tolerance -- state
exactly once.

The sign convention
-------------------
A schedule variance is reported ``+`` when the project is **ahead**. A date that
moved earlier than the comparison is ahead, so the variance is
``comparison - current`` in days, never the other way round. Stating it once here
is the whole reason a control can enforce it: the direction is a definition, and
a definition that lives in two places is a definition that eventually disagrees
with itself.
"""

from __future__ import annotations

from datetime import date

from .money import BPS_FULL


def cost_to_complete_cents(total_budget_cents: int, cost_to_date_cents: int) -> int:
    """Cost to Complete: the remainder of the budget, exact to the cent.

    ``Total Budget - Cost to Date``. This is the only definition Cost to Complete
    has, so a column maintained beside the budget rather than struck from it is
    an overrun that has not been reported yet.
    """
    return total_budget_cents - cost_to_date_cents


def net_project_revenue_cents(
    gross_revenue_cents: int, revenue_deduction_cents: int
) -> int:
    """Net project revenue: gross revenue less the revenue deductions."""
    return gross_revenue_cents - revenue_deduction_cents


def project_profit_cents(
    net_project_revenue_cents_: int, total_project_expense_cents: int
) -> int:
    """Project profit: net project revenue less total project expense."""
    return net_project_revenue_cents_ - total_project_expense_cents


def margin_on_cost_bps(
    profit_cents: int, total_project_expense_cents: int
) -> int | None:
    """Margin on cost in integer basis points, truncated toward zero.

    ``profit / total project expense``, struck on the *same* inputs the profit
    was struck on so the two cannot disagree. Truncation is toward zero rather
    than floored so a loss and a profit of the same magnitude round the same
    way -- flooring would make a negative margin one basis point wider than its
    positive mirror for no reason a reader could defend.

    A zero or negative expense returns ``None``: there is no cost to strike a
    margin on, and the control that would compare it skips the row rather than
    inventing a denominator.
    """
    if total_project_expense_cents <= 0:
        return None
    scaled = profit_cents * BPS_FULL
    magnitude = abs(scaled) // total_project_expense_cents
    return -magnitude if scaled < 0 else magnitude


def variance(current_value: int, comparison_value: int) -> int:
    """A variance column: the current figure less the column it is measured to.

    The same subtraction for money and for basis points, and the same one for the
    Prior column and the Plan column, so a variance cell can be compared to the
    two cells beside it with exact ``==``.
    """
    return current_value - comparison_value


def milestone_variance_days(current: date, comparison: date) -> int:
    """A schedule variance in days, positive when the project is **ahead**.

    ``comparison - current``: a current date earlier than the comparison date is
    an earlier finish, which is ahead, which is positive. A current date later is
    behind, which is negative.
    """
    return (comparison - current).days


def behind_beyond_tolerance(variance_days: int, tolerance_days: int) -> bool:
    """Whether a milestone has slipped past the file's own schedule tolerance.

    Behind is a negative variance under the sign convention above. A milestone
    behind by exactly ``tolerance_days`` is **at** the tolerance and not yet on
    the watchlist; one day further behind is past it.
    """
    return -variance_days > tolerance_days
