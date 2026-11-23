"""
The waterfall arithmetic, defined once.
=======================================

Turning a contribution history and an executed agreement's mechanics into the
money each member is owed is the single operation this whole engine is built
around, so it lives here alone and both the generator and the controls import
it. That is deliberate: if the engine recomputed a distribution by *different*
arithmetic than the one that produced it, the two would disagree on the edge
cases -- a truncated cent of monthly accrual, a hurdle satisfied to the dollar,
a pari-passu split of an odd amount -- and the tie-out control would be measuring
the disagreement between two implementations rather than the correctness of the
figure.

Everything here works on already-extracted primitives -- integer cents, integer
basis-point rates and integer month indices -- so the caller owns reading (and,
in the engine's case, integer-validating) the raw fields. Every rate is applied
with truncating integer division, so a figure derived here can be compared to a
reported figure with exact ``==`` and no tolerance band.
"""

from __future__ import annotations

from dataclasses import dataclass

from .money import BPS_FULL
from .model import (
    MONTHS_PER_YEAR,
    TIER_CAPITAL,
    TIER_HURDLE,
    TIER_PREF,
    TIER_PROMOTE,
    METHOD_IJB,
    METHOD_NUMDENOM,
    METHOD_RATIO,
)


@dataclass(frozen=True)
class Contribution:
    """One funded capital contribution, at an integer month index."""

    period: int
    amount_cents: int


@dataclass(frozen=True)
class Accounts:
    """A member's two capital accounts, re-derived to a review month."""

    contribution_account_cents: int
    investment_return_account_cents: int


def roll_forward(
    contributions: list[Contribution], rate_bps: int, periods: int
) -> Accounts:
    """Roll a member's capital accounts forward to month ``periods``.

    The Contribution Account is the running sum of capital funded on or before
    each month. The Investment Return Account (the preferred return) accrues at
    the monthly rate ``rate_bps / 12`` on the sum of *both* accounts -- so the
    preferred return itself earns preferred return, which is what "compounded
    monthly" means -- and it is applied at the end of every month from the first
    onward. Truncating integer division makes the balance exact and stable.

    A contribution carrying a month index beyond ``periods`` has not yet been
    funded at the review point and does not enter the balance.
    """
    contribution_account = 0
    return_account = 0
    for month in range(0, periods + 1):
        for c in contributions:
            if c.period == month:
                contribution_account += c.amount_cents
        if month >= 1:
            base = contribution_account + return_account
            return_account += base * rate_bps // (BPS_FULL * MONTHS_PER_YEAR)
    return Accounts(contribution_account, return_account)


def hurdle_target(
    contributions: list[Contribution], hurdle_rate_bps: int, periods: int
) -> int:
    """The cumulative distribution an investor needs to clear the hurdle.

    The hurdle is expressed as an internal rate of return, and an investor has
    reached it once its cumulative receipts equal its contributions grown at the
    hurdle rate -- exactly the roll-forward machinery of :func:`roll_forward`, run
    at the hurdle rate rather than the preferred rate. So the boundary between the
    hurdle tier and the promote tier is re-derivable from the same contributions.
    """
    accounts = roll_forward(contributions, hurdle_rate_bps, periods)
    return accounts.contribution_account_cents + accounts.investment_return_account_cents


def split_pro_rata(amount_cents: int, weights: list[int]) -> list[int]:
    """Split an amount across integer weights, exact to the cent.

    Used for the pari-passu tiers, where an amount is shared in proportion to the
    members' account balances. Floors first, then hands the leftover cents to the
    largest fractional remainders (Hamilton's method), so the parts sum exactly to
    the amount and the split is stable rather than merely close. A non-positive
    amount or zero total weight splits to zeros.
    """
    total_w = sum(weights)
    if total_w <= 0 or amount_cents <= 0:
        return [0] * len(weights)
    amount = min(amount_cents, total_w)
    floors = [amount * w // total_w for w in weights]
    leftover = amount - sum(floors)
    order = sorted(
        range(len(weights)),
        key=lambda i: (-(amount * weights[i] - floors[i] * total_w), i),
    )
    for i in range(leftover):
        floors[order[i]] += 1
    return floors


@dataclass(frozen=True)
class WaterfallResult:
    """The full distribution of one pool of proceeds."""

    #: ``(tier, member_id, amount_cents)`` in strict tier order, positive amounts.
    entries: tuple[tuple[str, str, int], ...]
    #: ``member_id -> total distributed`` across every tier.
    per_member: dict[str, int]
    #: ``member_id -> preferred-return receipts`` (the tier-A share).
    preferred: dict[str, int]
    #: ``member_id -> promote receipts`` (the hurdle + promote tier shares).
    promote: dict[str, int]
    #: The re-derived hurdle target the split boundary was solved to.
    hurdle_target_cents: int
    #: The proceeds actually distributed (sum of every entry).
    total_distributed_cents: int


def run_waterfall(
    proceeds_cents: int,
    investor_id: str,
    developer_id: str,
    preferred: dict[str, int],
    capital: dict[str, int],
    hurdle_target_cents: int,
    tier_c_investor_bps: int,
    tier_c_developer_bps: int,
    tier_d_investor_bps: int,
    tier_d_developer_bps: int,
) -> WaterfallResult:
    """Run the Section 3.3 non-land-sale waterfall over one pool of proceeds.

    The tiers pay in strict order:

    * **A -- preferred return**, pari passu to each member until its Investment
      Return Account is exhausted;
    * **B -- return of capital**, pari passu until its Contribution Account is
      exhausted;
    * **C -- hurdle split**, ``tier_c`` to investor / developer until the
      investor's cumulative receipts reach the hurdle target;
    * **D -- promote split**, ``tier_d`` thereafter.

    Every rate is applied with truncating division and the developer takes the
    residual cent of each split, so the whole distribution is exact and stable.
    """
    remaining = proceeds_cents
    entries: list[tuple[str, str, int]] = []
    received = {investor_id: 0, developer_id: 0}

    def pay(tier: str, amounts: dict[str, int]) -> None:
        # Investor before developer, so entry order is stable.
        for mid in (investor_id, developer_id):
            amt = amounts.get(mid, 0)
            received[mid] += amt
            if amt > 0:
                entries.append((tier, mid, amt))

    # Tier A -- preferred return, pari passu on the preferred balances.
    pay_a = min(remaining, preferred[investor_id] + preferred[developer_id])
    a_inv, a_dev = split_pro_rata(
        pay_a, [preferred[investor_id], preferred[developer_id]]
    )
    pay(TIER_PREF, {investor_id: a_inv, developer_id: a_dev})
    remaining -= pay_a
    preferred_receipts = {investor_id: a_inv, developer_id: a_dev}

    # Tier B -- return of capital, pari passu on the contribution balances.
    pay_b = min(remaining, capital[investor_id] + capital[developer_id])
    b_inv, b_dev = split_pro_rata(pay_b, [capital[investor_id], capital[developer_id]])
    pay(TIER_CAPITAL, {investor_id: b_inv, developer_id: b_dev})
    remaining -= pay_b

    # Tier C -- hurdle split until the investor's cumulative receipts reach the
    # hurdle target. Solve for the pool X whose investor share closes the gap.
    investor_gap = max(0, hurdle_target_cents - received[investor_id])
    if tier_c_investor_bps > 0 and investor_gap > 0:
        tier_c_full = (investor_gap * BPS_FULL + tier_c_investor_bps - 1) // tier_c_investor_bps
    else:
        tier_c_full = 0
    pay_c = min(remaining, tier_c_full)
    c_inv = pay_c * tier_c_investor_bps // BPS_FULL
    c_dev = pay_c - c_inv
    pay(TIER_HURDLE, {investor_id: c_inv, developer_id: c_dev})
    remaining -= pay_c

    # Tier D -- promote split on everything left.
    pay_d = remaining
    d_inv = pay_d * tier_d_investor_bps // BPS_FULL
    d_dev = pay_d - d_inv
    pay(TIER_PROMOTE, {investor_id: d_inv, developer_id: d_dev})
    remaining -= pay_d

    promote = {
        investor_id: c_inv + d_inv,
        developer_id: c_dev + d_dev,
    }
    total = sum(amt for _t, _m, amt in entries)
    return WaterfallResult(
        entries=tuple(entries),
        per_member=dict(received),
        preferred=preferred_receipts,
        promote=promote,
        hurdle_target_cents=hurdle_target_cents,
        total_distributed_cents=total,
    )


def loan_repayment(principal_cents: int, rate_bps: int, periods: int) -> int:
    """Repay a member loan in full -- principal plus monthly-compounded interest.

    The balance compounds at ``rate_bps / 12`` each month with truncating
    division, so the repayment figure is exact and re-derivable. Interest is the
    difference between the repayment and the principal.
    """
    balance = principal_cents
    for _ in range(periods):
        balance += balance * rate_bps // (BPS_FULL * MONTHS_PER_YEAR)
    return balance


def dilution_interest(
    method: str,
    defaulting_prior_cents: int,
    funding_prior_cents: int,
    aggregate_cents: int,
    substitute_cents: int,
    penalty_bps: int,
) -> int:
    """Re-derive a diluted member's interest, in basis points, by ``method``.

    When a member fails to fund a capital call, the shortfall is funded by the
    other member as a substitute contribution, and the defaulting member's
    interest is recomputed with a penalty applied to that substitute. Three
    partner-specific formula variants are maintained; each is deterministic:

    * ``ratio_method`` -- the penalized substitute inflates the denominator;
    * ``numerator_denominator_method`` -- the raw substitute enters the
      denominator, the penalty landing on the funding member's numerator;
    * ``i_plus_ii_minus_b_method`` -- the defaulting member's numerator is reduced
      by the penalty premium (penalized minus raw substitute).

    Returns ``0`` for an unknown method -- a separate control owns that gap.
    """
    penalized = substitute_cents * penalty_bps // BPS_FULL
    if method == METHOD_RATIO:
        denom = aggregate_cents + penalized
        return defaulting_prior_cents * BPS_FULL // denom if denom > 0 else 0
    if method == METHOD_NUMDENOM:
        denom = aggregate_cents + substitute_cents
        return defaulting_prior_cents * BPS_FULL // denom if denom > 0 else 0
    if method == METHOD_IJB:
        denom = aggregate_cents + penalized
        numerator = max(0, defaulting_prior_cents - (penalized - substitute_cents))
        return numerator * BPS_FULL // denom if denom > 0 else 0
    return 0


def equity_multiple_bps(distributions_cents: int, contributions_cents: int) -> int:
    """A member's equity multiple, in basis points (``1.51x`` -> ``15100``).

    Truncating division so a reported multiple can be compared with exact ``==``.
    A zero or negative contribution returns ``0`` -- no capital in, no multiple.
    """
    if contributions_cents <= 0:
        return 0
    return distributions_cents * BPS_FULL // contributions_cents
