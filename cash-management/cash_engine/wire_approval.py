"""Fictional, validation-only wire dual-approval / segregation-of-duties controls.

A cash manager's release control: no wire leaves the building without a distinct
second approver.  This validator inspects wire requests moving from *Pending
Secondary Approval* toward *Approved* / *Scheduled* and independently re-checks
the segregation-of-duties invariant that the initiator, first approver, and
second approver are three different people:

    releasable = initiator != first_approver != second_approver != initiator
                 and both approvers present for an approved or scheduled wire
                 and a scheduled wire is dated on or after its request

It works on generic structured inputs rather than a workbook layout, holds every
amount in integer cents, and is strictly read-only: it never creates a journal
entry, import payload, posting action, wire release, or source-system mutation,
and it contains no real bank, entity, person, amount, path, or workbook
coordinate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _valid_amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _clean_or_blank(value: object) -> bool:
    """A field that is either the empty string or trimmed, nonblank text."""

    return isinstance(value, str) and (value == "" or _clean_text(value))


def _valid_iso_date(value: object) -> bool:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_optional_date(value: object) -> bool:
    """A scheduled date that is either the empty string or a real ISO date."""

    return isinstance(value, str) and (value == "" or _valid_iso_date(value))


def _canonical_period(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    return value


@dataclass(frozen=True)
class WireRequest:
    """One fictional wire request, expressed in integer cents.

    ``second_approver`` and ``scheduled_date`` are empty strings while a wire is
    still pending its second approval; an approved or scheduled wire must name a
    distinct second approver, and a scheduled wire must carry a scheduled date on
    or after its request date.
    """

    wire_id: str
    entity: str
    beneficiary: str
    amount_cents: object
    initiator: str
    first_approver: str
    status: str
    request_date: str
    second_approver: str = ""
    scheduled_date: str = ""


@dataclass(frozen=True)
class WireApprovalFinding:
    code: str
    detail: str
    entity: str = ""
    account: str = ""  # carries the wire_id for per-record context
    severity: str = "ERROR"


@dataclass(frozen=True)
class WireApprovalResult:
    period: str
    wire_count: int
    approved_count: int
    scheduled_count: int
    pending_count: int
    blocked_count: int
    findings: tuple[WireApprovalFinding, ...]
    manual_gates: tuple[str, ...] = (
        "obtain the controlled wire-request log for the exact period",
        "confirm the second approver is distinct from the initiator and first approver",
        "confirm each approver holds authority within their wire limit",
        "confirm beneficiary banking details through an out-of-band channel",
        "human review and approval",
        "manual release to the bank and post-release confirmation",
    )
    journal_entries: tuple[object, ...] = field(default_factory=tuple)
    posting_actions: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)

    @property
    def mechanical_clean(self) -> bool:
        return not self.findings

    @property
    def verdict(self) -> str:
        return "READY FOR HUMAN REVIEW" if self.mechanical_clean else "NEEDS REVIEW"

    @property
    def validation_only(self) -> bool:
        return True

    @property
    def posting_authorized(self) -> bool:
        return False


class WireApprovalValidator:
    """Validate a set of fictional wire requests without releasing any wire."""

    _VALID_STATUSES = frozenset({"pending_secondary", "approved", "scheduled"})

    def __init__(self, period: str, wires: Iterable[WireRequest]) -> None:
        self.period = _canonical_period(period, "period")
        self.wires = tuple(wires)

    def run(self) -> WireApprovalResult:
        findings: list[WireApprovalFinding] = []
        seen: set[str] = set()
        approved = 0
        scheduled = 0
        pending = 0
        blocked = 0

        if not self.wires:
            findings.append(
                WireApprovalFinding("WIRE_SET_EMPTY", "no wire requests were provided")
            )

        for position, wire in enumerate(self.wires, start=1):
            entity = wire.entity if isinstance(wire.entity, str) else str(wire.entity)
            account = wire.wire_id if isinstance(wire.wire_id, str) else str(wire.wire_id)
            before = len(findings)

            def add(code: str, detail: str, severity: str = "ERROR") -> None:
                findings.append(WireApprovalFinding(code, detail, entity, account, severity))

            # Status tally over recognized statuses only.
            if wire.status == "approved":
                approved += 1
            elif wire.status == "scheduled":
                scheduled += 1
            elif wire.status == "pending_secondary":
                pending += 1

            structure_valid = True
            if not _clean_text(wire.wire_id):
                add("WIRE_ID_INVALID", f"wire {position} id must be trimmed and nonblank")
                structure_valid = False
            if not _clean_text(wire.entity):
                add("ENTITY_INVALID", f"wire {position} entity must be trimmed and nonblank")
                structure_valid = False
            if not _clean_text(wire.beneficiary):
                add("BENEFICIARY_INVALID", f"wire {position} beneficiary must be trimmed and nonblank")
                structure_valid = False
            if not _clean_text(wire.initiator):
                add("INITIATOR_INVALID", f"wire {position} initiator must be trimmed and nonblank")
                structure_valid = False
            if not _clean_text(wire.first_approver):
                add("FIRST_APPROVER_INVALID", f"wire {position} first approver must be trimmed and nonblank")
                structure_valid = False
            if not _clean_or_blank(wire.second_approver):
                add("SECOND_APPROVER_INVALID", f"wire {position} second approver must be blank or trimmed text")
                structure_valid = False
            if not _valid_amount(wire.amount_cents):
                add("AMOUNT_INVALID", f"wire {position} amount must be integer cents")
                structure_valid = False
            if wire.status not in self._VALID_STATUSES:
                add("STATUS_INVALID", f"wire {position} status is not a recognized wire state")
                structure_valid = False
            if not _valid_iso_date(wire.request_date):
                add("REQUEST_DATE_INVALID", f"wire {position} request date is not a valid ISO date")
                structure_valid = False
            if not _valid_optional_date(wire.scheduled_date):
                add("SCHEDULED_DATE_INVALID", f"wire {position} scheduled date must be blank or a valid ISO date")
                structure_valid = False

            if not structure_valid:
                blocked += 1
                continue

            key = wire.wire_id.casefold()
            if key in seen:
                add("WIRE_ID_DUPLICATE", f"wire {position} duplicates a wire id")
                blocked += 1
                continue
            seen.add(key)

            # Amount must be strictly positive.
            if wire.amount_cents <= 0:
                add("AMOUNT_NOT_POSITIVE", f"wire amount {wire.amount_cents} must be strictly positive")

            # Both approvers required once a wire is approved or scheduled.
            if wire.status in ("approved", "scheduled") and not (
                wire.first_approver.strip() and wire.second_approver.strip()
            ):
                add(
                    "MISSING_SECONDARY_APPROVAL",
                    "an approved or scheduled wire requires a nonblank first and second approver",
                )

            # Segregation of duties: three distinct people.
            initiator_key = wire.initiator.casefold()
            approver_keys: list[str] = []
            if wire.first_approver.strip():
                approver_keys.append(wire.first_approver.casefold())
            if wire.second_approver.strip():
                approver_keys.append(wire.second_approver.casefold())
            if any(approver == initiator_key for approver in approver_keys):
                add("SELF_APPROVAL", "an approver may not be the initiator of the same wire")
            if len(approver_keys) == 2 and approver_keys[0] == approver_keys[1]:
                add("DUPLICATE_APPROVER", "the first and second approver must be two different people")

            # Scheduling discipline.
            if wire.status == "scheduled":
                if not wire.scheduled_date.strip():
                    add("SCHEDULED_DATE_MISSING", "a scheduled wire must carry a scheduled date")
                elif date.fromisoformat(wire.scheduled_date) < date.fromisoformat(wire.request_date):
                    add(
                        "SCHEDULED_DATE_BEFORE_REQUEST",
                        f"scheduled date {wire.scheduled_date} precedes request date {wire.request_date}",
                    )
            if wire.status == "pending_secondary" and wire.scheduled_date.strip():
                add("PENDING_WIRE_SCHEDULED", "a wire pending secondary approval must not already be scheduled")

            if len(findings) > before:
                blocked += 1

        return WireApprovalResult(
            period=self.period,
            wire_count=len(self.wires),
            approved_count=approved,
            scheduled_count=scheduled,
            pending_count=pending,
            blocked_count=blocked,
            findings=tuple(findings),
        )


def demo_wires() -> tuple[WireRequest, ...]:
    """Return a clean set of fictional wires, three distinct names on each."""

    return (
        # Approved and awaiting scheduling: initiator + two distinct approvers.
        WireRequest(
            wire_id="WIRE-2026-0001",
            entity="Cedar Demo LLC",
            beneficiary="Northwind Vendor Trust",
            amount_cents=4_500_000,
            initiator="Dana Rivera",
            first_approver="Priya Anand",
            second_approver="Grace Okafor",
            status="approved",
            request_date="2026-06-10",
        ),
        # Fully approved and scheduled for release on a later date.
        WireRequest(
            wire_id="WIRE-2026-0002",
            entity="Cedar Demo LLC",
            beneficiary="Cascade Payroll Services",
            amount_cents=1_200_000,
            initiator="Marcus Bell",
            first_approver="Priya Anand",
            second_approver="Grace Okafor",
            status="scheduled",
            request_date="2026-06-12",
            scheduled_date="2026-06-15",
        ),
        # Still pending its second approval: second approver blank, not scheduled.
        WireRequest(
            wire_id="WIRE-2026-0003",
            entity="Cedar Demo LLC",
            beneficiary="Summit Tax Authority",
            amount_cents=800_000,
            initiator="Dana Rivera",
            first_approver="Marcus Bell",
            status="pending_secondary",
            request_date="2026-06-14",
        ),
    )


__all__ = [
    "WireRequest",
    "WireApprovalValidator",
    "WireApprovalFinding",
    "WireApprovalResult",
    "demo_wires",
]
