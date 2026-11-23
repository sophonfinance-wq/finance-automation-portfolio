"""
The release predicate, defined once.
====================================

Deciding whether a payment packet is *safe to release* is the single operation
this whole engine is built around, so it lives here alone and both the generator
and the controls import it. That is deliberate: if the engine recomputed a
packet's releasable flag by *different* logic than the one that produced it, the
two would disagree on the edge cases -- an amount exactly at a signer's limit, a
funding balance exactly equal to the wire, an authorization dated the same day as
the initiation -- and the tie-out control would be measuring the disagreement
between two implementations rather than the correctness of the determination.

Everything here works on already-extracted primitives -- integer cents, booleans,
strings and :class:`datetime.date` objects -- so the caller owns reading (and, in
the engine's case, integer-validating) the raw fields. That keeps the kernel free
of JSON-shape and money-coercion concerns and makes the boundary rules -- an
amount met *at* the authority limit, a balance met *at* the wire amount, an
authorization *on* the initiation date -- state exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def aba_check_digit_valid(aba: object) -> bool:
    """Whether a 9-digit ABA routing number passes its check-digit test.

    The American Bankers Association routing checksum is a mod-10 test with the
    fixed weight pattern 3-7-1 repeated across the nine digits::

        3(d1+d4+d7) + 7(d2+d5+d8) + 1(d3+d6+d9)  ==  0  (mod 10)

    A value that is not exactly nine digits fails: an ABA that is not nine digits
    is not an ABA.
    """
    if not isinstance(aba, str) or len(aba) != 9 or not aba.isdigit():
        return False
    d = [int(c) for c in aba]
    checksum = (
        3 * (d[0] + d[3] + d[6])
        + 7 * (d[1] + d[4] + d[7])
        + 1 * (d[2] + d[5] + d[8])
    ) % 10
    return checksum == 0


def within_duplicate_window(
    value_date: date, posted_date: date, window_days: int
) -> bool:
    """Whether two payments fall inside the same duplicate-detection window.

    The window is symmetric and inclusive: a scheduled wire dated up to
    ``window_days`` either side of an already-posted payment of the same
    beneficiary and amount is a suspected duplicate. A window of zero days matches
    only same-dated payments.
    """
    return abs((value_date - posted_date).days) <= window_days


@dataclass(frozen=True)
class ReleaseFacts:
    """A single packet reduced to the facts the release predicate needs.

    ``limit`` and ``available`` are ``None`` when the packet names a signer who is
    not authorized on the account, or an account that does not exist -- the
    predicate treats an unknown limit or balance as a block, never as a pass.
    """

    initiated_by: str
    authorized_by: str
    initiated_date: date | None
    authorized_date: date | None
    account_exists: bool
    initiator_authorized: bool
    authorizer_authorized: bool
    amount_cents: int
    authority_limit_cents: int | None
    beneficiary_ok: bool
    routing_ok: bool
    available_cents: int | None
    duplicate: bool


def release_ok(f: ReleaseFacts) -> bool:
    """Whether a packet clears every hard release control.

    The gates are ANDed in a fixed order so the determination is total and
    stable. Boundary rules are stated once here: an amount met **at** the
    authority limit passes (``>`` blocks, not ``>=``); a balance met **at** the
    wire amount passes; an authorization dated **on** the initiation date passes
    (``<`` blocks). A missing signer, limit, account or balance is a block, so an
    unknown is never mistaken for an approval.
    """
    if not f.initiated_by or not f.authorized_by:
        return False
    if f.initiated_by == f.authorized_by:
        return False
    if f.initiated_date is None or f.authorized_date is None:
        return False
    if f.authorized_date < f.initiated_date:
        return False
    if not f.account_exists:
        return False
    if not f.initiator_authorized or not f.authorizer_authorized:
        return False
    if f.authority_limit_cents is None or f.amount_cents > f.authority_limit_cents:
        return False
    if not f.beneficiary_ok:
        return False
    if not f.routing_ok:
        return False
    if f.available_cents is None or f.amount_cents > f.available_cents:
        return False
    if f.duplicate:
        return False
    return True
