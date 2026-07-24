"""
The compliance predicate, defined once.
=======================================

Deciding whether a party's certificates satisfy the contract is the single
operation this whole engine is built around, so it lives here alone and both the
generator and the controls import it. That is deliberate: if the engine
recomputed a party's compliant flag by *different* logic than the one that
produced it, the two would disagree on the edge cases -- an expired-today
certificate, a limit exactly at the requirement -- and the tie-out control would
be measuring the disagreement between two implementations rather than the
correctness of the determination.

Everything here works on already-extracted primitives -- integer cents, booleans
and :class:`datetime.date` objects -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw fields. That keeps the kernel free of
JSON-shape and money-coercion concerns and makes the boundary rules -- expired
*on* the review date, a limit met *at* the requirement, a renewal *at* the edge
of the lead window -- state exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Coverage:
    """A single certificate reduced to the facts the predicate needs."""

    per_occurrence_cents: int
    aggregate_cents: int
    additional_insured: bool
    waiver_of_subrogation: bool
    expiration: date


@dataclass(frozen=True)
class Requirement:
    """A requirement-matrix row reduced to the facts the predicate needs."""

    per_occurrence_cents: int
    aggregate_cents: int
    requires_additional_insured: bool
    requires_waiver_of_subrogation: bool


def governing(coverages: list[tuple[str, Coverage]]) -> tuple[str, Coverage] | None:
    """Return the currently-governing certificate for one coverage line.

    The governing certificate is the one whose term reaches furthest forward --
    the renewal, not the policy it replaced -- so expiry and limit tests read the
    coverage actually in force rather than a superseded one. Ties on the
    expiration date break on the certificate id, so the choice is stable rather
    than merely correct.

    Args:
        coverages: ``(certificate_id, Coverage)`` pairs of one coverage line.

    Returns:
        The governing pair, or ``None`` if the list is empty.
    """
    if not coverages:
        return None
    return max(coverages, key=lambda pair: (pair[1].expiration, pair[0]))


def coverage_satisfies(cov: Coverage, req: Requirement | None, as_of: date) -> bool:
    """Whether a governing certificate meets the contract as of ``as_of``.

    A certificate expired **on** the review date is not in force: expiry is
    ``expiration <= as_of``, so a term ending exactly on ``as_of`` has already
    lapsed. When ``req`` is ``None`` the requirement matrix carries no row for
    this (party type, coverage) pair -- a separate control owns that gap -- so the
    limit and endorsement tests are skipped and only currency is checked. Limits
    are met **at** the requirement: ``>=``, not ``>``.
    """
    if cov.expiration <= as_of:
        return False
    if req is None:
        return True
    if cov.per_occurrence_cents < req.per_occurrence_cents:
        return False
    if cov.aggregate_cents < req.aggregate_cents:
        return False
    if req.requires_additional_insured and not cov.additional_insured:
        return False
    if req.requires_waiver_of_subrogation and not cov.waiver_of_subrogation:
        return False
    return True


def within_renewal_window(expiration: date, as_of: date, lead_days: int) -> bool:
    """Whether a certificate is due for renewal inside the lead-time window.

    The window is the half-open span ``(as_of, as_of + lead_days]``: a term that
    has already lapsed (``expiration <= as_of``) is expired, not renewing, and a
    term ending exactly ``lead_days`` out is still inside the window.
    """
    remaining = (expiration - as_of).days
    return 0 < remaining <= lead_days
