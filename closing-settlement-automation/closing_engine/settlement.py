"""
The close-of-escrow determinations, defined once.
=================================================

Recomputing a home sale's closing is the single operation this whole engine is
built around, so the arithmetic lives here alone and both the generator and the
controls import it. That is deliberate: if the engine recomputed a unit's
settlement, its balanced closing entry or its loan release by *different* logic
than the one that produced the data, the two would disagree on the edge cases --
a fee derived to the cent, a plug that foots exactly -- and the tie-out control
would be measuring the disagreement between two implementations rather than the
correctness of the determination.

Everything here works on already-extracted primitives -- integer cents and
:class:`datetime.date` objects -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw JSON fields. That keeps the kernel
free of JSON-shape and money-coercion concerns and states each boundary rule --
the total that foots, the plug that balances, the relief capped *at* the prepaid
balance, revenue recognised *in* the close month -- exactly once.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from .money import BPS_FULL, apply_rate

#: The settlement charge components, in canonical order. The total settlement
#: charges is their sum; the total closing costs is that sum less the broker
#: commission (the commission is a selling cost, not a closing cost).
CHARGE_FIELDS: tuple[str, ...] = (
    "broker_commission_cents",
    "settlement_closing_fee_cents",
    "title_insurance_cents",
    "excise_tax_cents",
    "bank_processing_fee_cents",
    "concessions_cents",
    "listing_sales_fee_cents",
    "warranty_reserve_cents",
    "holdback_cents",
    "real_estate_taxes_cents",
)


def total_settlement_charges(components: Sequence[int]) -> int:
    """Sum the settlement charge components into total settlement charges."""
    return sum(components)


def total_closing_costs(charges_total: int, broker_commission: int) -> int:
    """Total closing costs = total settlement charges less the broker commission.

    The broker commission is a selling cost carried on the settlement statement
    but excluded from the closing-cost line the proforma is measured against, so
    it is netted out here exactly once.
    """
    return charges_total - broker_commission


def net_to_seller(gross_sales: int, charges_total: int) -> int:
    """Net proceeds to the seller = gross sales less total settlement charges."""
    return gross_sales - charges_total


def derived_fee(gross_sales: int, rate_bps: int) -> int:
    """A rate-derived fee: ``gross_sales`` times an integer basis-point rate.

    Truncating (the platform money contract), so the reported fee compares to the
    derived fee with exact ``==``. Used for the LISTING sales fee (0.50%) and the
    warranty reserve (1.00%), whose rates come from the proforma assumptions.
    """
    return apply_rate(gross_sales, rate_bps)


def ar_plug(credit_total: int, non_ar_debit_total: int) -> int:
    """The Accounts Receivable plug that balances the closing entry.

    The receivable is the balancing figure: total credits less the debits already
    posted to the non-receivable lines. With it in place the entry foots, so this
    is the value the balanced-entry control re-derives and compares to the stated
    receivable line.
    """
    return credit_total - non_ar_debit_total


def loan_ending_balance(
    beginning: int, draws: int, interest_fees: int, bank_remittance: int, paydowns: int
) -> int:
    """Roll a loan release forward to its ending balance.

    ``ending = beginning + draws + interest & fees - bank remittance - paydowns``.
    The same roll the lender's loan statement performs, so the ending balance can
    be tied to it with exact ``==``.
    """
    return beginning + draws + interest_fees - bank_remittance - paydowns


def prepaid_commission_relieved(commission_earned: int, prepaid_balance: int) -> int:
    """Prepaid commission relieved at closing, capped at the prepaid balance.

    ``MIN(commission earned, prepaid balance)``: a closing can relieve only the
    commission that was actually prepaid, so relief is capped *at* the prepaid
    balance and never draws the account negative.
    """
    return min(commission_earned, prepaid_balance)


def revised_project_profit(projected_profit: int, carry_costs: int) -> int:
    """Revised project profit = projected project profit + carry costs."""
    return projected_profit + carry_costs


def margin_bps(revised_profit: int, projected_net_revenue: int) -> int:
    """Project margin as integer basis points of projected net revenue, floored.

    Floor division is the platform contract for a reported ratio: it can only ever
    understate the margin by a rounding artifact, never overstate it. A zero or
    negative revenue base reports ``0`` -- no base, no ratio.
    """
    if projected_net_revenue <= 0 or revised_profit <= 0:
        return 0
    return revised_profit * BPS_FULL // projected_net_revenue


def coe_month(coe_date: date) -> str:
    """The close-of-escrow month, ``"YYYY-MM"``, revenue must be recognised in."""
    return f"{coe_date.year:04d}-{coe_date.month:02d}"
