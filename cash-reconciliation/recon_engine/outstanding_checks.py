"""Fictional, validation-only outstanding-check register & aging controls.

A cash manager's control over uncleared checks: every check issued against a
disbursement account is tracked until it clears, is voided, or ages past the
stale-date policy.  This validator independently re-derives the outstanding
total and confirms the register is internally consistent:

    outstanding total = sum(amount for status in {outstanding, stale})
    control           = displayed outstanding total == rederived total
    aging             = outstanding checks older than stale_days are flagged
                        for stale-dating review

It works on generic structured inputs rather than a workbook layout, holds every
amount in integer cents, and is strictly read-only: it never creates a journal
entry, import payload, posting action, or source-system mutation, and it contains
no private workbook coordinates, paths, formulas, entity names, or amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_ACCOUNT_RE = re.compile(r"[A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8}){1,3}", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

_ALLOWED_STATUSES = frozenset({"outstanding", "cleared", "void", "stale"})
_LIVE_STATUSES = frozenset({"outstanding", "cleared", "stale"})
_OUTSTANDING_STATUSES = frozenset({"outstanding", "stale"})


def _valid_amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _canonical_period(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be canonical YYYY-MM")
    return value


def _valid_stale_days(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_iso_date(value: object) -> date | None:
    """Parse a strict ``YYYY-MM-DD`` string, returning ``None`` when malformed.

    Rejects loose formats (``2026-6-1``, ``20260601``, leading blanks) and
    impossible calendar dates (``2026-02-30``) without ever raising, so callers
    can emit a finding instead of crashing on bad register data.
    """

    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        return None
    year, month, day = (int(part) for part in value.split("-"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass(frozen=True)
class CheckRecord:
    """One fictional issued-check register line, expressed in integer cents.

    ``amount_cents`` is a magnitude carried as an object so non-integer inputs
    are rejected rather than coerced; ``status`` is one of
    ``{outstanding, cleared, void, stale}``.  Live checks (outstanding, cleared,
    stale) carry a positive amount; a ``void`` check must carry amount zero.
    """

    entity: str
    account: str
    check_number: str
    payee: str
    issue_date: str
    amount_cents: object
    status: str


@dataclass(frozen=True)
class OutstandingCheckFinding:
    code: str
    detail: str
    entity: str = ""
    account: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class OutstandingCheckResult:
    period: str
    as_of_date: str
    stale_days: int
    check_count: int
    outstanding_count: int
    stale_count: int
    void_count: int
    cleared_count: int
    outstanding_total_cents: object
    findings: tuple[OutstandingCheckFinding, ...]
    manual_gates: tuple[str, ...] = (
        "obtain the controlled check register and bank clearing report for the exact period",
        "confirm each outstanding check against the subsequent bank statement",
        "apply the stale-date and unclaimed-property policy to aged checks",
        "approve any void or reissue before it is recorded",
        "human review and approval",
        "manual posting and post-entry general-ledger tie-out",
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


class OutstandingCheckValidator:
    """Validate one fictional outstanding-check register without posting."""

    def __init__(
        self,
        period: str,
        as_of_date: str,
        stale_days: int,
        checks: Iterable[CheckRecord],
        displayed_outstanding_total_cents: object = None,
    ) -> None:
        self.period = _canonical_period(period, "period")
        if not _valid_stale_days(stale_days):
            raise ValueError("stale_days must be a nonnegative integer number of days")
        self.as_of_date = as_of_date
        self.stale_days = stale_days
        self.checks = tuple(checks)
        self.displayed_outstanding_total_cents = displayed_outstanding_total_cents

    def run(self) -> OutstandingCheckResult:
        findings: list[OutstandingCheckFinding] = []

        as_of = _parse_iso_date(self.as_of_date)
        if as_of is None:
            findings.append(
                OutstandingCheckFinding(
                    "AS_OF_DATE_INVALID",
                    f"as-of date {self.as_of_date!r} is not a valid YYYY-MM-DD date",
                )
            )

        if not self.checks:
            findings.append(
                OutstandingCheckFinding(
                    "CHECK_REGISTER_EMPTY", "no checks were provided"
                )
            )

        seen: set[tuple[str, str]] = set()
        outstanding_count = 0
        cleared_count = 0
        void_count = 0
        stale_count = 0
        outstanding_total = 0

        for position, check in enumerate(self.checks, start=1):
            entity = check.entity if isinstance(check.entity, str) else str(check.entity)
            account = check.account if isinstance(check.account, str) else str(check.account)

            def add(code: str, detail: str, severity: str = "ERROR") -> None:
                findings.append(OutstandingCheckFinding(code, detail, entity, account, severity))

            structure_valid = True
            if not _clean_text(check.entity):
                add("ENTITY_INVALID", f"check {position} entity must be trimmed and nonblank")
                structure_valid = False
            if not isinstance(check.account, str) or not _ACCOUNT_RE.fullmatch(check.account):
                add("ACCOUNT_INVALID", f"check {position} account is not canonical")
                structure_valid = False
            if not _clean_text(check.check_number):
                add("CHECK_NUMBER_INVALID", f"check {position} check number must be trimmed and nonblank")
                structure_valid = False
            if not _clean_text(check.payee):
                add("PAYEE_INVALID", f"check {position} payee must be trimmed and nonblank")
                structure_valid = False
            if not _valid_amount(check.amount_cents):
                add("AMOUNT_INVALID", f"check {position} amount must use integer cents")
                structure_valid = False
            if not (isinstance(check.status, str) and check.status in _ALLOWED_STATUSES):
                add(
                    "STATUS_INVALID",
                    f"check {position} status must be one of "
                    + ", ".join(sorted(_ALLOWED_STATUSES)),
                )
                structure_valid = False

            issue = _parse_iso_date(check.issue_date)
            if issue is None:
                add("ISSUE_DATE_INVALID", f"check {position} issue date is not a valid YYYY-MM-DD date")
                structure_valid = False

            if not structure_valid:
                continue

            key = (check.account.casefold(), check.check_number.casefold())
            if key in seen:
                add("CHECK_NUMBER_DUPLICATE", f"check {position} duplicates a check number for its account")
                continue
            seen.add(key)

            if check.status == "outstanding":
                outstanding_count += 1
            elif check.status == "cleared":
                cleared_count += 1
            elif check.status == "void":
                void_count += 1
            elif check.status == "stale":
                stale_count += 1

            # Live checks must carry a positive amount; a void must carry zero.
            if check.status in _LIVE_STATUSES and check.amount_cents <= 0:
                add(
                    "CHECK_AMOUNT_NONPOSITIVE",
                    f"check {position} status {check.status} requires an amount greater than zero",
                )
            if check.status == "void" and check.amount_cents != 0:
                add(
                    "VOID_AMOUNT_NONZERO",
                    f"check {position} is void and must carry a zero amount, not {check.amount_cents}",
                )

            if check.status in _OUTSTANDING_STATUSES:
                outstanding_total += check.amount_cents

            # Issue date cannot post-date the as-of date.
            if as_of is not None and issue > as_of:
                add(
                    "ISSUE_DATE_AFTER_AS_OF",
                    f"check {position} issue date {check.issue_date} is after as-of date {self.as_of_date}",
                )

            # An outstanding check aged beyond the stale threshold should have
            # been stale-dated; flag it for review rather than posting anything.
            if (
                as_of is not None
                and check.status == "outstanding"
                and issue <= as_of
                and (as_of - issue).days > self.stale_days
            ):
                add(
                    "STALE_CHECK_REVIEW",
                    f"check {position} is outstanding {(as_of - issue).days} days "
                    f"(> {self.stale_days}) and should be reviewed for stale-dating",
                    severity="REVIEW",
                )

        displayed = self.displayed_outstanding_total_cents
        if displayed is not None:
            if not _valid_amount(displayed):
                findings.append(
                    OutstandingCheckFinding(
                        "DISPLAYED_OUTSTANDING_TOTAL_INVALID",
                        "displayed outstanding total must use integer cents",
                    )
                )
            elif displayed != outstanding_total:
                findings.append(
                    OutstandingCheckFinding(
                        "OUTSTANDING_TOTAL_OUT_OF_TIE",
                        f"displayed outstanding total {displayed} != rederived total {outstanding_total}",
                    )
                )

        return OutstandingCheckResult(
            period=self.period,
            as_of_date=self.as_of_date,
            stale_days=self.stale_days,
            check_count=len(self.checks),
            outstanding_count=outstanding_count,
            stale_count=stale_count,
            void_count=void_count,
            cleared_count=cleared_count,
            outstanding_total_cents=outstanding_total,
            findings=tuple(findings),
        )


def demo_checks() -> tuple[CheckRecord, ...]:
    """Return a clean, tying fictional check register (integer cents).

    As of 2026-06-30 with a 180-day stale threshold: two outstanding checks and
    one correctly stale-dated check sum to the displayed outstanding total, one
    check has cleared, and one is a zero-amount void.  Nothing is aged past the
    threshold while still marked outstanding, so the register is clean.
    """

    return (
        CheckRecord(
            entity="Cedar Demo LLC",
            account="CASH-1001",
            check_number="1050",
            payee="Demo Utility Co",
            issue_date="2026-06-15",
            amount_cents=125_000,
            status="outstanding",
        ),
        CheckRecord(
            entity="Cedar Demo LLC",
            account="CASH-1001",
            check_number="1051",
            payee="Demo Vendor Inc",
            issue_date="2026-05-20",
            amount_cents=40_000,
            status="outstanding",
        ),
        CheckRecord(
            entity="Cedar Demo LLC",
            account="CASH-1001",
            check_number="1052",
            payee="Demo Supplier LLC",
            issue_date="2026-04-10",
            amount_cents=50_000,
            status="cleared",
        ),
        CheckRecord(
            entity="Cedar Demo LLC",
            account="CASH-1001",
            check_number="1053",
            payee="Demo Refund Payee",
            issue_date="2026-06-01",
            amount_cents=0,
            status="void",
        ),
        CheckRecord(
            entity="Cedar Demo LLC",
            account="CASH-1002",
            check_number="2200",
            payee="Demo Contractor",
            issue_date="2025-11-01",
            amount_cents=30_000,
            status="stale",
        ),
    )


# Independently known outstanding total for the clean demo register above:
# 125_000 (outstanding) + 40_000 (outstanding) + 30_000 (stale) == 195_000.
DEMO_PERIOD = "2026-06"
DEMO_AS_OF_DATE = "2026-06-30"
DEMO_STALE_DAYS = 180
DEMO_OUTSTANDING_TOTAL_CENTS = 195_000


__all__ = [
    "CheckRecord",
    "OutstandingCheckFinding",
    "OutstandingCheckResult",
    "OutstandingCheckValidator",
    "demo_checks",
    "DEMO_PERIOD",
    "DEMO_AS_OF_DATE",
    "DEMO_STALE_DAYS",
    "DEMO_OUTSTANDING_TOTAL_CENTS",
]
