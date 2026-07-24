"""
The underwriting standards, defined once.
=========================================

Every determination this engine both *derives* (in the generator) and
*recomputes* (in the controls) lives here alone, so the two cannot disagree.
That is deliberate: if the engine recomputed a phase gate, a fee, a trigger
breach or a template-refresh date by *different* logic than the one that
produced the data, the tie-out controls would be measuring the disagreement
between two implementations rather than the correctness of the determination.

Everything here works on already-extracted primitives -- integer cents, integer
basis points, booleans and :class:`datetime.date` objects -- so the caller owns
reading (and, in the engine's case, integer-validating) the raw fields. That
keeps the kernel free of JSON-shape and money-coercion concerns and makes the
boundary rules -- a contingency met *at* the floor, a trigger breached *on* the
approval date, a template refreshed *on* the review date -- state exactly once.

All thresholds are fictional policy constants for a fictional developer; no
real organisation's standards are reproduced.
"""

from __future__ import annotations

from datetime import date

from .money import BPS_FULL, apply_rate

# --------------------------------------------------------------------------- #
# Hard dollar triggers (integer cents)
# --------------------------------------------------------------------------- #
#: Cumulative pursuit costs at or above this figure require a prior approved
#: Initial Commitment Request.
PURSUIT_TRIGGER_CENTS = 5_000_000  # 50,000.00

#: Cumulative refundable deposits at or above this figure require a prior
#: approved Initial Commitment Request.
REFUNDABLE_TRIGGER_CENTS = 10_000_000  # 100,000.00

#: Any non-refundable deposit -- the first cent -- requires a prior approved
#: Initial Commitment Request.
NONREFUNDABLE_TRIGGER_CENTS = 1  # 0.01

# --------------------------------------------------------------------------- #
# Contingency floors (integer basis points), keyed by region
# --------------------------------------------------------------------------- #
#: Hard-cost contingency floor per region, at every phase before construction.
HARD_FLOOR_BPS: dict[str, int] = {"marran": 1000, "vanterre": 300}

#: Soft-cost contingency floor per region.
SOFT_FLOOR_BPS: dict[str, int] = {"marran": 500, "vanterre": 300}

#: At construction start a Marran hard-cost contingency splits: 10% on site
#: work, 5% on vertical construction.
SITE_FLOOR_BPS = 1000
VERTICAL_FLOOR_BPS = 500

# --------------------------------------------------------------------------- #
# Fee formulas and coverage thresholds (integer basis points)
# --------------------------------------------------------------------------- #
#: CM Fee = 1.5% of hard cost.
CM_FEE_RATE_BPS = 150

#: Development Fee = 3% of (total project cost less financing).
DEV_FEE_RATE_BPS = 300

#: Construction may not start until at least 80% of hard costs (third-party GC)
#: or 80% of cost line items (owner-GC) are competitively bid.
BID_COVERAGE_FLOOR_BPS = 8000

#: The standard growth assumption is "3/3" -- 3% revenue growth and 3% cost
#: growth -- unless a market-supported alternative is documented.
STANDARD_GROWTH_BPS = 300

# --------------------------------------------------------------------------- #
# Comparison bases
# --------------------------------------------------------------------------- #
#: Before feasibility is waived a Spending Request compares to the Business
#: Plan *template*; after the waiver the project enters the annual Business
#: Plan and must show variance to the *actual* plan.
BASIS_TEMPLATE = "template"
BASIS_ACTUAL_PLAN = "actual_plan"
BASES: tuple[str, ...] = (BASIS_TEMPLATE, BASIS_ACTUAL_PLAN)


def required_basis(feasibility_waived: bool) -> str:
    """The comparison basis a request must use, given the waiver status.

    The switch is the control: pre-waiver requests that compare to the actual
    plan are comparing to a plan the project is not yet in, and post-waiver
    requests still pointing at the template are hiding their variance.
    """
    return BASIS_ACTUAL_PLAN if feasibility_waived else BASIS_TEMPLATE


def latest_template_refresh(as_of: date) -> date:
    """The most recent template refresh on or before ``as_of``.

    The Business Plan template is refreshed each January and June. The refresh
    in force is the latest 1 January or 1 June that is not after the review
    date -- a template dated exactly ``as_of`` is current, one refresh older is
    stale.
    """
    candidates = [
        date(year, month, 1)
        for year in (as_of.year - 1, as_of.year)
        for month in (1, 6)
    ]
    return max(c for c in candidates if c <= as_of)


def first_breach(entries: list[tuple[date, int]], threshold_cents: int) -> date | None:
    """The date a cumulative spend first reaches ``threshold_cents``.

    Entries are accumulated in date order and the breach lands on the entry
    that carries the running total to (or past) the threshold -- reaching it
    exactly is a breach, one cent under is not. Returns ``None`` when the
    threshold is never reached.
    """
    running = 0
    for entry_date, amount_cents in sorted(entries, key=lambda t: t[0]):
        running += amount_cents
        if running >= threshold_cents:
            return entry_date
    return None


def trigger_satisfied(breach: date | None, ic_approval: date | None) -> bool:
    """Whether the Initial Commitment approval preceded the trigger breach.

    No breach means nothing to authorize. A breach with no approval at all, or
    with an approval dated after it, is capital committed before the gate. An
    approval dated *on* the breach date satisfies the trigger: the gate opened
    the day the spend crossed it.
    """
    if breach is None:
        return True
    return ic_approval is not None and ic_approval <= breach


def meets_floor(part_cents: int, base_cents: int, floor_bps: int) -> bool:
    """Whether ``part`` is at least ``floor_bps`` of ``base``, exactly.

    Compared cross-multiplied in integers -- ``part * 10000 >= base * floor`` --
    so a contingency met to the cent passes and a cent under fails, with no
    floating-point ratio in between. A non-positive base carries no floor.
    """
    if base_cents <= 0:
        return True
    return part_cents * BPS_FULL >= base_cents * floor_bps


def derive_fee_block(
    hard_cents: int,
    hard_contingency_cents: int,
    soft_cents: int,
    soft_contingency_cents: int,
    financing_cents: int,
) -> tuple[int, int, int]:
    """Derive ``(cm_fee, dev_fee, total_project_cost)`` from the cost stack.

    The CM Fee is a straight rate on hard cost. The Development Fee is 3% of
    (total project cost less financing) where the total *includes* the fee
    itself, so it is solved as an integer fixed point: the derived fee is fed
    back into the total until it stops moving. Both fees use
    :func:`~spending_engine.money.apply_rate`, so a stated figure can be tied
    to the derived one with exact ``==``.
    """
    cm_fee = apply_rate(hard_cents, CM_FEE_RATE_BPS)
    base = (
        hard_cents
        + hard_contingency_cents
        + soft_cents
        + soft_contingency_cents
        + financing_cents
        + cm_fee
    )
    dev_fee = 0
    for _ in range(100):
        next_fee = apply_rate(base + dev_fee - financing_cents, DEV_FEE_RATE_BPS)
        if next_fee == dev_fee:
            break
        dev_fee = next_fee
    return cm_fee, dev_fee, base + dev_fee


def gate_cleared(phase_approved: bool, prior_deliverables_complete: bool) -> bool:
    """Whether a phase gate cleared.

    A phase may be entered only after the IC approves that phase's Spending
    Request *and* every deliverable required by the phases before it is
    complete. Both legs are membership facts; neither is a judgment.
    """
    return phase_approved and prior_deliverables_complete


def growth_is_standard(revenue_growth_bps: int, cost_growth_bps: int) -> bool:
    """Whether the growth assumption is the standard 3/3 default."""
    return (
        revenue_growth_bps == STANDARD_GROWTH_BPS
        and cost_growth_bps == STANDARD_GROWTH_BPS
    )


def derive_variance(project_cents: int, plan_cents: int) -> int:
    """The stated-vs-plan variance: project figure minus plan figure."""
    return project_cents - plan_cents
