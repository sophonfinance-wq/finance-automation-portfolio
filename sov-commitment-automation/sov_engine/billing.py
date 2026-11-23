"""
The billing arithmetic, defined once.
=====================================

Re-deriving the pay-application chain is the single operation this whole engine
is built around, so its formulas live here alone and both the generator and the
controls import them. That is deliberate: if the engine recomputed a derived
figure by *different* logic than the one that produced it, the two would
disagree on the edge cases -- a truncated retention cent, a floored
percent-complete, a line billed exactly to its scheduled value -- and the
tie-out controls would be measuring the disagreement between two implementations
rather than the correctness of the figure.

Everything here works on already-extracted primitives -- integer cents and
integer basis points -- so the caller owns reading (and, in the engine's case,
integer-validating) the raw fields. That keeps the kernel free of JSON-shape and
money-coercion concerns and makes the boundary rules -- retention truncated on
the request, percent floored on the scheduled value, only an *approved* change
order counted toward the revised contract -- state exactly once.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .money import apply_rate, percent_complete_bps

# --------------------------------------------------------------------------- #
# Change-order status vocabulary
# --------------------------------------------------------------------------- #
#: A change order that has been signed into the contract and moves the revised
#: commitment.
CO_APPROVED = "approved"
#: A change order raised but not yet signed; it moves nothing until it is.
CO_PENDING = "pending"
#: A change order withdrawn; it never moves anything.
CO_VOID = "void"
#: Every status a change order may carry.
CO_STATUSES: tuple[str, ...] = (CO_APPROVED, CO_PENDING, CO_VOID)

#: The shape of a commitment id: project abbreviation, vendor code, sequential
#: count -- e.g. ``BWC-KETT00-1``. The count is 1-based with no leading zero.
COMMITMENT_ID_RE = re.compile(r"^([A-Z]{3})-([A-Z]{4}\d{2})-([1-9]\d*)$")


def make_commitment_id(project_code: str, vendor_code: str, seq: int) -> str:
    """The canonical commitment id: project abbrev + vendor code + count.

    Shared with the generator so the id the engine validates is the id the
    procedure constructs. A change order never mints a new id; it is applied to
    the original commitment as ``#-N``.
    """
    return f"{project_code}-{vendor_code}-{seq}"


def net_approved_change_cents(change_orders: Iterable[tuple[str, int]]) -> int:
    """Net change-order movement on a commitment: approved orders only.

    A pending change order moves nothing until it is signed, and a void one
    never moves anything -- counting either early is exactly the drift the
    committed-cost control exists to catch.

    Args:
        change_orders: ``(status, amount_cents)`` pairs for one commitment.

    Returns:
        The signed sum of the approved amounts, in integer cents.
    """
    return sum(amount for status, amount in change_orders if status == CO_APPROVED)


def revised_contract_cents(original_cents: int, net_change_cents: int) -> int:
    """Revised (total-to-date) contract = original + net approved change orders."""
    return original_cents + net_change_cents


def total_completed_cents(previously_billed_cents: int, work_this_period_cents: int) -> int:
    """A line's completed-and-stored to date: previously billed + this period (D+E)."""
    return previously_billed_cents + work_this_period_cents


def balance_to_finish_cents(scheduled_value_cents: int, completed_cents: int) -> int:
    """A line's balance to finish: scheduled value - completed to date.

    The sign is meaningful: a negative balance is a line billed past its
    committed value, which the billing-cap control fails.
    """
    return scheduled_value_cents - completed_cents


def percent_complete(completed_cents: int, scheduled_value_cents: int) -> int:
    """A line's percent complete in integer basis points, floored.

    Floor division through :func:`~sov_engine.money.percent_complete_bps` is the
    contract: the stated column can be compared with exact ``==``, and flooring
    can only ever understate progress, never overstate it.
    """
    return percent_complete_bps(completed_cents, scheduled_value_cents)


def current_request_cents(
    total_completed_cents: int, total_previously_billed_cents: int
) -> int:
    """The current request for payment: completed to date - previously billed."""
    return total_completed_cents - total_previously_billed_cents


def retention_cents(current_request_cents: int, retention_rate_bps: int) -> int:
    """Retention held this period: the contract rate on the current request.

    Truncating division through :func:`~sov_engine.money.apply_rate`, so the
    stated retention can be compared with exact ``==``.
    """
    return apply_rate(current_request_cents, retention_rate_bps)


def sales_tax_cents(taxable_request_cents: int, tax_rate_bps: int) -> int:
    """State sales tax on the current taxable request, truncated like retention."""
    return apply_rate(taxable_request_cents, tax_rate_bps)


def payment_due_cents(
    current_request_cents: int, retention_cents: int, sales_tax_cents: int
) -> int:
    """Current payment due including tax: request - retention held + sales tax.

    This is the certified figure the conditional lien release must be signed
    for, so it is derived here once and tied out everywhere it appears.
    """
    return current_request_cents - retention_cents + sales_tax_cents
