"""
The reconciliation predicates, defined once.
============================================

Every determination this engine both *produces* (in the generator) and later
*recomputes* (in the controls) lives here alone, so the two can never disagree on
an edge case. If the engine recomputed an employer match, a statutory limit, a
per-period withholding or a plan tie by *different* arithmetic than the generator
used to produce it, the tie-out control would be measuring the gap between two
implementations rather than the correctness of the figure.

Everything here works on already-extracted primitives -- integer cents,
:class:`datetime.date` objects and small enums -- so the caller owns reading (and,
in the engine's case, integer-validating) the raw fields. That keeps the kernel
free of JSON-shape and money-coercion concerns and states the boundary rules --
a match capped *at* the compensation limit, a deposit landing *on* the safe-harbor
edge, a deferral *at* its ceiling -- exactly once.
"""

from __future__ import annotations

from datetime import date, timedelta

from .money import apply_rate, split_evenly

# --------------------------------------------------------------------------- #
# Date arithmetic
# --------------------------------------------------------------------------- #
def business_days_between(start: date, end: date) -> int:
    """Count business days in the half-open span ``(start, end]``.

    Weekends (Saturday and Sunday) are excluded; holidays are not modelled. The
    day money is withheld is not counted, the day it is deposited is: a deposit on
    the next business day is one business day out. When ``end`` precedes ``start``
    the count is negative, which is how :func:`~benefit_engine.engine` tells a
    remittance dated before its pay date apart from a merely late one.
    """
    if end == start:
        return 0
    step = 1 if end > start else -1
    count = 0
    cur = start
    while cur != end:
        cur += timedelta(days=step)
        if cur.weekday() < 5:
            count += step
    return count


def age_on(dob: date, as_of: date) -> int:
    """Whole years from ``dob`` to ``as_of`` (the catch-up eligibility age)."""
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years


# --------------------------------------------------------------------------- #
# Statutory limits
# --------------------------------------------------------------------------- #
def deferral_limit(base_cents: int, catchup_cents: int, catchup_age: int, age: int) -> int:
    """The 402(g) deferral ceiling for one employee.

    The catch-up is added once the employee has reached ``catchup_age`` by the
    plan-year-end; the boundary is inclusive (``age >= catchup_age``), so an
    employee who turns fifty during the plan year gets the catch-up.
    """
    return base_cents + (catchup_cents if age >= catchup_age else 0)


def hsa_limit(
    self_only_cents: int,
    family_cents: int,
    catchup_cents: int,
    catchup_age: int,
    tier: str,
    age: int,
) -> int:
    """The HSA contribution ceiling for one employee.

    The tier selects the base (self-only vs family) and the age-55 catch-up is
    added inclusively. A tier the engine does not recognise contributes a zero
    base, which the tier-membership control owns separately.
    """
    from .model import TIER_FAMILY, TIER_SELF_ONLY

    if tier == TIER_SELF_ONLY:
        base = self_only_cents
    elif tier == TIER_FAMILY:
        base = family_cents
    else:
        base = 0
    return base + (catchup_cents if age >= catchup_age else 0)


# --------------------------------------------------------------------------- #
# Employer match
# --------------------------------------------------------------------------- #
def derive_match(eligible_comp_cents: int, match_rate_bps: int, comp_cap_cents: int) -> int:
    """Recompute an employer match: rate applied to comp capped at 401(a)(17).

    Compensation above ``comp_cap_cents`` is ineligible, so the base is
    ``min(eligible_comp, cap)``. The rate is applied with the platform's
    truncating :func:`~benefit_engine.money.apply_rate`, so a match derived here
    compares to the booked match with exact ``==``.
    """
    base = min(eligible_comp_cents, comp_cap_cents)
    return apply_rate(base, match_rate_bps)


def capped_match(comp_cap_cents: int, match_rate_bps: int) -> int:
    """The match an over-cap employee may not exceed: rate on the cap itself."""
    return apply_rate(comp_cap_cents, match_rate_bps)


# --------------------------------------------------------------------------- #
# Per-period withholding
# --------------------------------------------------------------------------- #
def remaining_room(limit_cents: int, employer_annual_cents: int, prior_ytd_cents: int) -> int:
    """Contribution room left for the rest of the plan year.

    The annual ceiling less what the employer already puts in less what the
    employee has already contributed year to date. May be negative when the
    account is already over-funded, which the withholding recompute surfaces.
    """
    return limit_cents - employer_annual_cents - prior_ytd_cents


def per_period_base(room_cents: int, periods_remaining: int) -> int:
    """The level per-period withholding: room spread over the remaining periods.

    Uses :func:`~benefit_engine.money.split_evenly`, so the pieces sum back to the
    room exactly and the base is the level amount every period but the last
    carries. Negative room floors toward the level piece the split produces.
    """
    if periods_remaining < 1:
        periods_remaining = 1
    return split_evenly(room_cents, periods_remaining)[0]


def per_period_max(room_cents: int, periods_remaining: int) -> int:
    """The largest per-period piece the even split produces (the true-up period).

    The remainder lands on the final period, so this is the ceiling a per-period
    deduction may reach without over-withholding against the remaining room.
    """
    if periods_remaining < 1:
        periods_remaining = 1
    return max(split_evenly(room_cents, periods_remaining))


# --------------------------------------------------------------------------- #
# The plan tie-out predicate
# --------------------------------------------------------------------------- #
def plan_is_tied(
    register_total_cents: int,
    provider_totals_cents: list[int],
    je_liability_cents: int,
    cash_transfer_cents: int,
) -> bool:
    """Whether one plan's four legs all tie to the register.

    A plan is tied when the payroll register total equals every provider upload
    total (a 401(k) must tie to *both* the recordkeeper and the custodian), equals
    the journal-entry liability credit, and equals the settling cash transfer.
    Exact integer-cent equality throughout: a plan a penny off is a plan that does
    not tie. Shared with the generator so the stated tie flag is the one the
    engine recomputes.
    """
    for provider_total in provider_totals_cents:
        if provider_total != register_total_cents:
            return False
    if je_liability_cents != register_total_cents:
        return False
    if cash_transfer_cents != register_total_cents:
        return False
    return True
