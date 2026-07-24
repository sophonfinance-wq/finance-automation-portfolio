"""
The good-standing predicate, defined once.
==========================================

Deciding whether an entity's state records satisfy its statutory obligations is
the single operation this whole engine is built around, so it lives here alone
and both the generator and the controls import it. That is deliberate: if the
engine recomputed an entity's good-standing flag by *different* logic than the
one that produced it, the two would disagree on the edge cases -- a report filed
exactly on the due date, a franchise tax paid to the exact statutory cent, a
renewal at the very edge of the lead window -- and the tie-out control would be
measuring the disagreement between two implementations rather than the
correctness of the determination.

Everything here works on already-extracted primitives -- integer cents, booleans
and :class:`datetime.date` objects -- so the caller owns reading (and, in the
engine's case, integer-validating) the raw fields. That keeps the kernel free of
JSON-shape and money-coercion concerns and makes the boundary rules -- filed *on*
the due date, a fee met *at* the statutory amount, a renewal *at* the edge of the
lead window -- state exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .model import LICENSE_CURRENT, SOS_ACTIVE


@dataclass(frozen=True)
class Obligation:
    """A jurisdiction-matrix row reduced to the facts the predicate needs."""

    report_fee_cents: int
    franchise_tax_cents: int
    requires_registered_agent: bool
    requires_business_license: bool


@dataclass(frozen=True)
class StandingRecord:
    """A single state record reduced to the facts the predicate needs."""

    sos_status: str
    report_due: date | None
    report_filed: date | None
    report_fee_paid_cents: int
    franchise_due: date | None
    franchise_paid: date | None
    franchise_paid_cents: int
    sos_agent: str
    contracted_agent: str
    agent_fee_paid: date | None
    license_status: str
    license_due: date | None


def report_filed_on_time(rec: StandingRecord) -> bool:
    """The annual/biennial report was filed on-or-before its statutory due date.

    Filed **on** the due date is on time: the gate is ``filed <= due``, so a
    filing dated exactly on the deadline still counts and one day later is late.
    An absent filing date -- or an absent due date -- is not on time.
    """
    if rec.report_filed is None or rec.report_due is None:
        return False
    return rec.report_filed <= rec.report_due


def report_fee_met(rec: StandingRecord, ob: Obligation) -> bool:
    """The report filing fee paid meets the statutory fee. Exact ``>=``."""
    return rec.report_fee_paid_cents >= ob.report_fee_cents


def franchise_amount_met(rec: StandingRecord, ob: Obligation) -> bool:
    """The franchise tax paid meets the flat statutory amount. Exact ``>=``.

    A dollar under the flat amount is a dollar under the flat amount: the state
    does not part-credit a franchise tax, so a shortfall is an unpaid tax.
    """
    return rec.franchise_paid_cents >= ob.franchise_tax_cents


def franchise_paid_on_time(rec: StandingRecord) -> bool:
    """The franchise tax was paid on-or-before its statutory due date.

    Paid **on** the due date is on time (``paid <= due``); one day later is late.
    """
    if rec.franchise_paid is None or rec.franchise_due is None:
        return False
    return rec.franchise_paid <= rec.franchise_due


def sos_status_active(rec: StandingRecord) -> bool:
    """The Secretary-of-State reported status is ACTIVE."""
    return rec.sos_status == SOS_ACTIVE


def agent_current(rec: StandingRecord, ob: Obligation) -> bool:
    """The registered agent of record is the contracted agent, with fee paid.

    Where the jurisdiction requires a registered agent, the agent named on the
    state's record must equal the agent actually under contract and that agent's
    annual fee must be paid. Where no agent is required the test is vacuously met.
    """
    if not ob.requires_registered_agent:
        return True
    return rec.sos_agent == rec.contracted_agent and rec.agent_fee_paid is not None


def license_current(rec: StandingRecord, ob: Obligation, as_of: date) -> bool:
    """The business license is current and not past its renewal date at ``as_of``.

    Where the jurisdiction requires a city business license, the license status
    must read current and its renewal date must still be ahead of the review date
    (``due > as_of``): a licence whose renewal date has arrived is due, not
    current. Where no licence is required the test is vacuously met.
    """
    if not ob.requires_business_license:
        return True
    if rec.license_status != LICENSE_CURRENT:
        return False
    return rec.license_due is not None and rec.license_due > as_of


def record_in_good_standing(rec: StandingRecord, ob: Obligation, as_of: date) -> bool:
    """Whether one state record meets every substantive obligation as of ``as_of``.

    Good standing is the conjunction of the substantive gates: the report filed on
    time and its fee met, the franchise tax paid in full and on time, the SOS
    status ACTIVE, the registered agent current, and any required business licence
    current. The data-integrity controls (stated due date == statutory, no stray
    record) are deliberately *not* part of standing -- they guard the paper, not
    the protection -- so they can fail without moving this determination.
    """
    return (
        report_filed_on_time(rec)
        and report_fee_met(rec, ob)
        and franchise_amount_met(rec, ob)
        and franchise_paid_on_time(rec)
        and sos_status_active(rec)
        and agent_current(rec, ob)
        and license_current(rec, ob, as_of)
    )


def within_renewal_window(due: date, as_of: date, lead_days: int) -> bool:
    """Whether a filing is due for renewal inside the lead-time window.

    The window is the half-open span ``(as_of, as_of + lead_days]``: an obligation
    already past due (``due <= as_of``) is overdue, not renewing, and one due
    exactly ``lead_days`` out is still inside the window.
    """
    remaining = (due - as_of).days
    return 0 < remaining <= lead_days
