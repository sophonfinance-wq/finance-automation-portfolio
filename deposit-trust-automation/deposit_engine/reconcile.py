"""
The reconciliation kernel, defined once.
========================================

Deciding what the escrow agent *should* hold for a unit, what the loan
*should* have been paid down by, and what the segregated upgrade bank *should*
carry is the single operation this whole engine is built around, so it lives
here alone and both the generator and the controls import it. That is
deliberate: if the engine recomputed a unit's variance by *different* logic
than the one that produced it, the two would disagree on the edge cases -- a
cancelled deposit, a closed unit, a deposit still waiting to post -- and the
tie-out control would be measuring the disagreement between two
implementations rather than the correctness of the reconciliation.

Everything here works on already-extracted primitives -- integer cents,
strings and booleans folded into :class:`DepositFacts` -- so the caller owns
reading (and, in the engine's case, integer-validating) the raw fields. That
keeps the kernel free of JSON-shape and money-coercion concerns and makes the
boundary rules -- a cancelled deposit leaves the agent's scope, a closed unit
keeps its paydown but leaves the trust bank, a variance is agent-minus-books
with a missing side read as zero -- state exactly once.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .model import (
    STATUS_ALREADY_POSTED,
    STATUS_NEED_TO_POST,
    STATUS_UNIT_CLOSED,
)


@dataclass(frozen=True)
class DepositFacts:
    """A single ledger deposit reduced to the facts the kernel needs."""

    deposit_id: str
    unit_id: str
    em_cents: int
    upgrade_cents: int
    status: str
    cancelled: bool


def is_pre_close(deposit: DepositFacts) -> bool:
    """Whether a deposit is still inside the pre-close escrow world.

    A deposit is in the agent's open-escrow scope while it is active and its
    unit has not closed: cancelled deposits have been refunded or forfeited and
    a closed unit's escrow has settled, so neither belongs on the agent's open
    statement or in the segregated upgrade bank.
    """
    return not deposit.cancelled and deposit.status in (
        STATUS_NEED_TO_POST,
        STATUS_ALREADY_POSTED,
    )


def is_swept(deposit: DepositFacts) -> bool:
    """Whether a deposit's earnest money has been applied to the loan.

    An active deposit is swept once posted, and stays swept through unit close
    (the principal paydown survives the closing). A cancelled deposit keeps the
    bucket it held at cancellation, so ``already_posted`` on a cancelled
    deposit means the paydown happened -- and must therefore be reversed.
    """
    if deposit.cancelled:
        return deposit.status == STATUS_ALREADY_POSTED
    return deposit.status in (STATUS_ALREADY_POSTED, STATUS_UNIT_CLOSED)


def expected_agent_em(deposits: Iterable[DepositFacts], unit_id: str) -> int:
    """Earnest money the escrow agent should hold for ``unit_id``, in cents.

    The agent's open-escrow statement carries the earnest money of every
    active, pre-close deposit of the unit -- posted or not, since the sweep is
    the developer's bookkeeping, not a release from escrow -- and nothing for
    cancelled deposits or closed units.
    """
    return sum(
        d.em_cents for d in deposits if d.unit_id == unit_id and is_pre_close(d)
    )


def expected_net_paydown(deposits: Iterable[DepositFacts], unit_id: str) -> int:
    """Net construction-loan principal ``unit_id`` should have paid down.

    Every active swept deposit contributes its earnest money; a cancelled
    deposit contributes nothing net, because its paydown (if any) must have
    been reversed. This is the third leg of the three-way tie-out.
    """
    return sum(
        d.em_cents
        for d in deposits
        if d.unit_id == unit_id and not d.cancelled and is_swept(d)
    )


def expected_upgrade_bank(deposits: Iterable[DepositFacts]) -> int:
    """Balance the segregated upgrade-deposit bank account should carry.

    Upgrade money stays in the segregated bank for exactly as long as the
    deposit is pre-close: a cancellation refunds it and a closing releases it,
    so only active, unclosed deposits contribute.
    """
    return sum(d.upgrade_cents for d in deposits if is_pre_close(d))


def unit_variance(agent_cents: int | None, expected_em_cents: int) -> int:
    """The reconciliation variance for one unit, in cents.

    Variance is the agent's recorded earnest money **minus** the figure our
    books support, with a side the other does not carry read as zero -- so a
    deposit on the agent's side with nothing on our books surfaces as a
    positive variance (a completeness gap) and a booked deposit the agent
    never recorded surfaces as a negative one (an over-release). Zero is the
    only passing value.
    """
    return (agent_cents if agent_cents is not None else 0) - expected_em_cents


def split_is_balanced(em_cents: int, fee_cents: int, refund_cents: int) -> bool:
    """Whether a cancellation's forfeiture split accounts for the deposit.

    On cancellation the earnest money decomposes into exactly two pieces: the
    termination fee the seller retains and the remainder refunded to the
    buyer. The split balances only when the pieces sum back to the deposit --
    to the cent, with no tolerance.
    """
    return fee_cents + refund_cents == em_cents


def net_sale(sales_price_cents: int, concession_cents: int) -> int:
    """Net sale price: the contract price plus the (negative) concession.

    Concessions are stored as negative amounts and reduce revenue, so the net
    sale is a straight sum -- never a subtraction hidden in a sign convention.
    """
    return sales_price_cents + concession_cents
