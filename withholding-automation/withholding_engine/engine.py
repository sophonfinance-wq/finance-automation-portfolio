"""
Non-resident withholding & 1042-S control engine (READ-ONLY).
=============================================================

Loads each withholding file (a ``.json`` file produced by
:mod:`withholding_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the withholding the workpapers state is right, on
file, remitted and reconciled** -- not about paying anyone or filing anything. A
US withholding agent that pays cross-border interest, dividends, royalties or rent
to foreign recipients has to withhold Chapter 3 tax at the right rate, support
every reduced rate with a valid W-8, deposit what it withheld, and reconcile the
annual Form 1042 to the 1042-S slips. This engine is that proof.

The shape of the problem
------------------------
Four failures hide inside a folder of withholding workpapers, and none of them
look wrong: the treaty rate applied behind a missing or expired W-8; the US payee
withheld or the accrued coupon treated as paid; the deposits that do not equal the
liability; and the Form 1042 that does not tie to the slips it transmits.

The registry is organised around that:

1. ``set_``   -- is the withholding file complete?
2. ``payee_`` -- is the payee register sound and are its status codes classified?
3. ``rate_``  -- does the treaty table define, and bound, every rate it must?
4. ``pay_``   -- is every payment well-formed, coded and attributable to a payee?
5. ``wh_``    -- does each payment's rate and tax recompute, and is the withholding
   gate (paid, non-US) respected?
6. ``exm_``   -- is every reduced rate supported by a valid, unexpired W-8, and are
   the exemption classifications sound?
7. ``dep_``   -- do the deposits tie the liability and is the return filed on time?
8. ``rec_``   -- does the Form 1042 recompute from the slips it transmits?

Design notes
------------
- **Strictly read-only.** Withholding files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every total is compared with exact ``==``.
- **One determination.** Controls and the generator share the kernel in
  :mod:`withholding_engine.withholding`, so a rate cannot disagree with the data
  that produced it.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.
"""

from __future__ import annotations

import contextlib
import functools
import json
import re
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from .model import (
    CH3_STATUS_CODES,
    CH3_US_PERSON,
    CH4_STATUS_CODES,
    DOC_DEPOSIT_REGISTER,
    DOC_FORM_1042,
    DOC_INCOME_CODE_TABLE,
    DOC_PAYEE_REGISTER,
    DOC_PAYMENT_REGISTER,
    DOC_SLIP_REGISTER,
    DOC_TREATY_RATE_TABLE,
    DOC_TYPES,
    DOC_W8_WATCHLIST,
    INCOME_TYPES,
    INTEREST_CONTINGENT,
    LOB_CODES,
    NONPARTICIPATING_FFI_CODES,
    PAYMENT_STATUS_ACCRUED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUSES,
    W8_STATUS_VALID,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, apply_rate, fmt, fmt_bps, require_cents
from .withholding import (
    STATUTORY_RATE_BPS,
    determined_rate_bps,
    w8_is_valid,
    within_renewal_window,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~withholding_engine.money.AmountInvalidError` as a finding."""
    return Finding(
        rule_id,
        SEVERITY.get(rule_id, Status.FAIL),
        f"amount:{exc.field}",
        f"{exc} -- amounts are integer cents and are never coerced",
    )


@contextlib.contextmanager
def amount_guard(rule_id: str, out: list[Finding]) -> Iterator[None]:
    """Contain a malformed amount to the one row being read."""
    try:
        yield
    except AmountInvalidError as exc:
        out.append(amount_invalid_finding(rule_id, exc))


def check(rule_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register ``fn`` in :data:`REGISTRY` under ``rule_id``."""

    def wrapper(fn: CheckFn) -> CheckFn:
        @functools.wraps(fn)
        def guarded(ctx: Context) -> list[Finding]:
            try:
                return fn(ctx)
            except AmountInvalidError as exc:
                return [amount_invalid_finding(rule_id, exc)]

        REGISTRY.append((rule_id, guarded))
        return guarded

    return wrapper


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sev(rule_id: str, status: Status) -> Status:
    SEVERITY[rule_id] = status
    return status


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _rows(doc: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    rows = doc.get(key)
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) and value else None


def _int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# --------------------------------------------------------------------------- #
# Withholding-file accessors
# --------------------------------------------------------------------------- #
def _payees(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PAYEE_REGISTER), "payees")


def _payee_id(row: dict[str, Any]) -> str:
    value = row.get("payee_id")
    return value if isinstance(value, str) and value else "?"


def _payee_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _payees(ctx):
        pid = _payee_id(row)
        if pid != "?" and pid not in out:
            out[pid] = row
    return out


def _treaty_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TREATY_RATE_TABLE), "rates")


def _treaty_map(ctx: Context) -> dict[tuple[str, str], int]:
    """``(country, income_type) -> rate_bps`` for well-formed table rows."""
    out: dict[tuple[str, str], int] = {}
    for row in _treaty_rows(ctx):
        country = _text(row, "country")
        income_type = _text(row, "income_type")
        rate = _int(row, "rate_bps")
        if country and income_type and rate is not None and (country, income_type) not in out:
            out[(country, income_type)] = rate
    return out


def _treaty_countries(ctx: Context) -> set[str]:
    return {c for (c, _t) in _treaty_map(ctx)}


def _income_codes(ctx: Context) -> dict[str, dict[str, Any]]:
    """``income_code -> {income_type, portfolio_interest}`` for the code table."""
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_INCOME_CODE_TABLE), "codes"):
        code = _text(row, "code")
        if code and code not in out:
            out[code] = row
    return out


def _payments(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PAYMENT_REGISTER), "payments")


def _payment_id(row: dict[str, Any]) -> str:
    value = row.get("payment_id")
    return value if isinstance(value, str) and value else "?"


def _deposits(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DEPOSIT_REGISTER), "deposits")


def _slips(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_SLIP_REGISTER), "slips")


def _income_type_of(ctx: Context, payment: dict[str, Any]) -> str | None:
    code = _text(payment, "income_code")
    entry = _income_codes(ctx).get(code or "")
    return _text(entry, "income_type") if entry else None


def _is_portfolio(ctx: Context, payment: dict[str, Any]) -> bool:
    code = _text(payment, "income_code")
    entry = _income_codes(ctx).get(code or "")
    return bool(entry.get("portfolio_interest")) if entry else False


def _payee_is_us(payee: dict[str, Any] | None) -> bool:
    return bool(payee) and _text(payee, "chapter_3_status_code") == CH3_US_PERSON


def _is_reportable(ctx: Context, payment: dict[str, Any], payees: dict[str, dict[str, Any]]) -> bool:
    """A payment is reportable when it is paid to a known non-US payee.

    Reportable payments are the ones that carry Chapter 3 withholding, feed a
    1042-S slip and count toward the deposit liability. Accrued-only amounts and
    payments to US persons are out of scope, as is a payment whose payee is not in
    the register (a separate control owns that).
    """
    if _text(payment, "payment_status") != PAYMENT_STATUS_PAID:
        return False
    payee = payees.get(_text(payment, "payee_id") or "")
    if payee is None or _payee_is_us(payee):
        return False
    return True


def _w8_valid_for(payee: dict[str, Any], as_of: date) -> bool:
    return w8_is_valid(
        bool(payee.get("has_valid_w8")),
        _text(payee, "w8_status") == W8_STATUS_VALID,
        _parse_date(payee.get("w8_expiration")),
        as_of,
    )


def _determined_rate_for(
    ctx: Context,
    payment: dict[str, Any],
    payee: dict[str, Any],
    treaty: dict[tuple[str, str], int],
    as_of: date,
) -> int | None:
    """Re-derive a subject payment's applicable rate through the shared kernel.

    Returns the rate in basis points, or ``None`` when the determination reaches
    the treaty branch and the table carries no row for the payment's
    (country, income-type) pair -- an absent row is owned by ``rate_table_defined``,
    not invented here. Callers pass only payments already known to be reportable.
    """
    income_type = _income_type_of(ctx, payment)
    country = _text(payee, "country")
    treaty_rate = treaty.get((country or "", income_type or "")) if income_type else None
    return determined_rate_bps(
        is_nonparticipating_ffi=_text(payee, "chapter_4_status_code") in NONPARTICIPATING_FFI_CODES,
        is_portfolio_interest=_is_portfolio(ctx, payment),
        is_contingent_interest=_text(payment, "interest_subcharacter") == INTEREST_CONTINGENT,
        w8_valid=_w8_valid_for(payee, as_of),
        treaty_rate_bps=treaty_rate,
    )


# --------------------------------------------------------------------------- #
# Recompute helpers (shared with the generator through this module)
# --------------------------------------------------------------------------- #
def recompute_slips(ctx: Context) -> list[dict[str, Any]]:
    """Rebuild the 1042-S slip set from the payment register.

    One slip per reportable payee, its gross and tax the sum of that payee's
    reportable payments. Shared with the generator so the stated slips can be tied
    to it. Reads stated gross and tax as integer cents; a malformed amount
    propagates as :class:`AmountInvalidError` to the calling control.
    """
    payees = _payee_map(ctx)
    gross: dict[str, int] = {}
    withheld: dict[str, int] = {}
    for payment in _payments(ctx):
        if not _is_reportable(ctx, payment, payees):
            continue
        pid = _text(payment, "payee_id") or "?"
        g = require_cents(f"payment[{_payment_id(payment)}].gross_cents", payment.get("gross_cents"))
        w = require_cents(
            f"payment[{_payment_id(payment)}].tax_withheld_cents", payment.get("tax_withheld_cents")
        )
        gross[pid] = gross.get(pid, 0) + g
        withheld[pid] = withheld.get(pid, 0) + w
    return [
        {"payee_id": pid, "gross_cents": gross[pid], "withheld_cents": withheld[pid]}
        for pid in sorted(gross)
    ]


def recompute_w8_watchlist(ctx: Context, as_of: date, lead_days: int) -> list[dict[str, Any]]:
    """The W-8 renewal watchlist re-derived from the payee register.

    One entry per payee whose W-8 is on file, currently valid, and due to expire
    inside the lead-time window. Shared with the generator so the stated watchlist
    can be tied to it. Reads no amounts, so it never raises on a malformed figure.
    """
    entries: list[dict[str, Any]] = []
    for payee in _payees(ctx):
        if not bool(payee.get("has_valid_w8")):
            continue
        if _text(payee, "w8_status") != W8_STATUS_VALID:
            continue
        expiration = _parse_date(payee.get("w8_expiration"))
        if expiration is None:
            continue
        if within_renewal_window(expiration, as_of, lead_days):
            entries.append(
                {
                    "payee_id": _payee_id(payee),
                    "w8_expiration": payee.get("w8_expiration"),
                    "days_remaining": (expiration - as_of).days,
                }
            )
    entries.sort(key=lambda e: (e["payee_id"], e["w8_expiration"]))
    return entries


def _normalize_watch_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("payee_id"),
        entry.get("w8_expiration"),
        entry.get("days_remaining"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the withholding file depends on is present, exactly once.

    This runs first and deliberately owns the "missing artifact" finding. A
    control that silently passes because its input is absent is worse than no
    control: it reports assurance it never performed.
    """
    rule = "set_complete"
    _sev(rule, Status.FAIL)
    out: list[Finding] = []
    for doc_type in DOC_TYPES:
        found = ctx.docs(doc_type)
        if not found:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"{doc_type} is missing; the controls that read it cannot run and "
                    f"must not be reported as having passed",
                )
            )
        elif len(found) > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"{len(found)} {doc_type} documents present; the withholding file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(DOC_TYPES)} withholding artifacts are present")
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every expiry and renewal "
                f"test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# payee_ -- the payee register and its classifications
# --------------------------------------------------------------------------- #
@check("payee_unique_ids")
def check_payee_unique_ids(ctx: Context) -> list[Finding]:
    """No payee id appears twice.

    The payee id joins the register to every payment and to every slip. A
    duplicate makes a payment ambiguous about whom it paid.
    """
    rule = "payee_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _payees(ctx):
        seen[_payee_id(row)] = seen.get(_payee_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"payees/{pid}"),
            f"payee id {pid} appears {count} times; a payment that names it cannot be "
            f"attributed to one payee",
        )
        for pid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} payee ids are unique"))
    return out


@check("payee_country_known")
def check_payee_country_known(ctx: Context) -> list[Finding]:
    """Every foreign payee's residence country is one the treaty table carries.

    The country is the key into the treaty rate table; a foreign payee whose
    country has no rows has no rate to look up, so the treaty branch could not
    resolve. US persons are out of scope -- they are not withheld on at all.
    """
    rule = "payee_country_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    table = ctx.one(DOC_TREATY_RATE_TABLE)
    if register is None or table is None:
        return []
    countries = _treaty_countries(ctx)
    out: list[Finding] = []
    for row in _payees(ctx):
        if _payee_is_us(row):
            continue
        country = _text(row, "country")
        if country not in countries:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payees/{_payee_id(row)}/country"),
                    f"payee {_payee_id(row)} resides in {country!r}, which the treaty rate "
                    f"table does not carry; no rate could be looked up for it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every foreign payee's country is in the rate table")
        )
    return out


@check("payee_ch3_status_valid")
def check_payee_ch3_status_valid(ctx: Context) -> list[Finding]:
    """Every payee carries a known Chapter 3 status code.

    The Chapter 3 status decides whether a payee is withheld on at all; an unknown
    code cannot be classified, so the withholding gate could not be applied to it.
    """
    rule = "payee_ch3_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"payees/{_payee_id(row)}/chapter_3_status_code"),
            f"payee {_payee_id(row)} carries Chapter 3 status {_text(row, 'chapter_3_status_code')!r}, "
            f"which is not one of {CH3_STATUS_CODES}",
        )
        for row in _payees(ctx)
        if _text(row, "chapter_3_status_code") not in CH3_STATUS_CODES
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_payees(ctx))} payees carry a known Chapter 3 status")
        )
    return out


@check("payee_ch4_status_valid")
def check_payee_ch4_status_valid(ctx: Context) -> list[Finding]:
    """Every payee carries a known Chapter 4 (FATCA) status code.

    The Chapter 4 status decides the FATCA override; an unknown code cannot be
    tested against the non-participating-FFI list, so the override could not fire.
    """
    rule = "payee_ch4_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"payees/{_payee_id(row)}/chapter_4_status_code"),
            f"payee {_payee_id(row)} carries Chapter 4 status {_text(row, 'chapter_4_status_code')!r}, "
            f"which is not one of {CH4_STATUS_CODES}",
        )
        for row in _payees(ctx)
        if _text(row, "chapter_4_status_code") not in CH4_STATUS_CODES
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_payees(ctx))} payees carry a known Chapter 4 status")
        )
    return out


@check("payee_lob_code_valid")
def check_payee_lob_code_valid(ctx: Context) -> list[Finding]:
    """Every payee claiming a treaty benefit carries a known LOB code.

    A treaty claim on an entity is supported only by a limitation-on-benefits
    (Article XXIX-A) code; a payee that attests a valid W-8 but carries an LOB code
    outside the known list has claimed a benefit on a code that cannot be tested.
    """
    rule = "payee_lob_code_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _payees(ctx):
        if not bool(row.get("has_valid_w8")):
            continue  # no treaty claim, no LOB code required
        lob = _text(row, "lob_code")
        if lob not in LOB_CODES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payees/{_payee_id(row)}/lob_code"),
                    f"payee {_payee_id(row)} claims a treaty benefit but carries LOB code "
                    f"{lob!r}, which is not one of {LOB_CODES}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every treaty-claiming payee carries a known LOB code")
        )
    return out


# --------------------------------------------------------------------------- #
# rate_ -- the treaty rate table
# --------------------------------------------------------------------------- #
@check("rate_table_defined")
def check_rate_table_defined(ctx: Context) -> list[Finding]:
    """The treaty table has a row for every (country, income-type) a payment needs.

    Without the row the engine knows a payment must be rated but not at what rate,
    so the treaty branch of the determination could not resolve. Payees whose
    country is itself unknown are left to ``payee_country_known``.
    """
    rule = "rate_table_defined"
    _sev(rule, Status.FAIL)
    table = ctx.one(DOC_TREATY_RATE_TABLE)
    if table is None:
        return []
    treaty = _treaty_map(ctx)
    countries = _treaty_countries(ctx)
    payees = _payee_map(ctx)
    seen: set[tuple[str, str]] = set()
    out: list[Finding] = []
    for payment in _payments(ctx):
        if not _is_reportable(ctx, payment, payees):
            continue
        payee = payees[_text(payment, "payee_id") or ""]
        country = _text(payee, "country")
        income_type = _income_type_of(ctx, payment)
        if country not in countries or income_type is None:
            continue  # payee_country_known / pay_income_code_known own these
        key = (country, income_type)
        if key in seen:
            continue
        seen.add(key)
        if key not in treaty:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(table, f"rates/{country}/{income_type}"),
                    f"the treaty table has no row for {country}/{income_type}, which payment "
                    f"{_payment_id(payment)} needs; its treaty rate cannot be looked up",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} needed (country, income-type) rates are defined")
        )
    return out


@check("rate_within_bounds")
def check_rate_within_bounds(ctx: Context) -> list[Finding]:
    """Every rate in the treaty table sits between 0 and the statutory default.

    A treaty rate can only reduce the statutory rate, never exceed it: a table
    rate above 30.00% or below 0 is a data error that would make a reduced-rate
    determination read as an increase.
    """
    rule = "rate_within_bounds"
    _sev(rule, Status.FAIL)
    table = ctx.one(DOC_TREATY_RATE_TABLE)
    if table is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _treaty_rows(ctx):
        country = _text(row, "country")
        income_type = _text(row, "income_type")
        with amount_guard(rule, out):
            rate = require_cents(
                f"treaty[{country}/{income_type}].rate_bps", row.get("rate_bps"), unit="a basis-point rate"
            )
            checked += 1
            if rate < 0 or rate > STATUTORY_RATE_BPS:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(table, f"rates/{country}/{income_type}/rate_bps"),
                        f"treaty rate for {country}/{income_type} is {fmt_bps(rate)}; it must be "
                        f"between 0.00% and the statutory {fmt_bps(STATUTORY_RATE_BPS)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} treaty rates are within bounds"))
    return out


# --------------------------------------------------------------------------- #
# pay_ -- the payment register
# --------------------------------------------------------------------------- #
@check("pay_required_fields")
def check_pay_required_fields(ctx: Context) -> list[Finding]:
    """Every payment carries the descriptive fields the controls read."""
    rule = "pay_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    required = (
        "payment_id",
        "payee_id",
        "income_code",
        "payment_status",
        "interest_subcharacter",
    )
    out: list[Finding] = []
    for row in _payments(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payments/{_payment_id(row)}"),
                    f"payment {_payment_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_payments(ctx))} payments carry their required fields")
        )
    return out


@check("pay_income_code_known")
def check_pay_income_code_known(ctx: Context) -> list[Finding]:
    """Every payment carries a 1042-S income code the code table defines.

    The income code maps the payment to an income type and tells the engine whether
    it is portfolio interest; an unknown code cannot be mapped, so the payment
    could not be rated or slipped.
    """
    rule = "pay_income_code_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    table = ctx.one(DOC_INCOME_CODE_TABLE)
    if register is None or table is None:
        return []
    codes = _income_codes(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"payments/{_payment_id(row)}/income_code"),
            f"payment {_payment_id(row)} carries income code {_text(row, 'income_code')!r}, "
            f"which the income-code table does not define",
        )
        for row in _payments(ctx)
        if _text(row, "income_code") not in codes
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_payments(ctx))} payments carry a known income code")
        )
    return out


@check("pay_payee_exists")
def check_pay_payee_exists(ctx: Context) -> list[Finding]:
    """Every payment names a payee in the register."""
    rule = "pay_payee_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    payees = _payee_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"payments/{_payment_id(row)}/payee_id"),
            f"payment {_payment_id(row)} names payee {_text(row, 'payee_id')!r}, which is not "
            f"in the payee register",
        )
        for row in _payments(ctx)
        if _text(row, "payee_id") and _text(row, "payee_id") not in payees
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every payment names a payee in the register"))
    return out


@check("pay_status_valid")
def check_pay_status_valid(ctx: Context) -> list[Finding]:
    """Every payment carries a known payment status.

    The status decides whether the amount was actually paid -- and so subject to
    withholding -- or merely accrued. An unknown status cannot be gated on.
    """
    rule = "pay_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"payments/{_payment_id(row)}/payment_status"),
            f"payment {_payment_id(row)} carries status {_text(row, 'payment_status')!r}, "
            f"which is not one of {PAYMENT_STATUSES}",
        )
        for row in _payments(ctx)
        if _text(row, "payment_status") not in PAYMENT_STATUSES
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_payments(ctx))} payments carry a known status")
        )
    return out


# --------------------------------------------------------------------------- #
# wh_ -- the withholding gate and the rate/tax recompute
# --------------------------------------------------------------------------- #
@check("wh_us_payee_excluded")
def check_wh_us_payee_excluded(ctx: Context) -> list[Finding]:
    """A payment to a US person is not withheld on.

    Chapter 3 withholding reaches FDAP paid to a *non-US* person. A US payee that
    shows tax withheld has been withheld on in error -- the amount is not owed and
    should never have reached a 1042-S.
    """
    rule = "wh_us_payee_excluded"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    payees = _payee_map(ctx)
    out: list[Finding] = []
    for payment in _payments(ctx):
        payee = payees.get(_text(payment, "payee_id") or "")
        if payee is None or not _payee_is_us(payee):
            continue
        with amount_guard(rule, out):
            withheld = require_cents(
                f"payment[{_payment_id(payment)}].tax_withheld_cents", payment.get("tax_withheld_cents")
            )
            if withheld != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"payments/{_payment_id(payment)}/tax_withheld_cents"),
                        f"payment {_payment_id(payment)} to US payee {_payee_id(payee)} shows "
                        f"{fmt(withheld)} withheld; a US person is not subject to Chapter 3 "
                        f"withholding",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "no US payee is withheld on"))
    return out


@check("wh_accrued_not_withheld")
def check_wh_accrued_not_withheld(ctx: Context) -> list[Finding]:
    """An accrued-only amount is not withheld on.

    Only FDAP that is *paid* is subject to Chapter 3 withholding. An amount marked
    accrued has not been paid, so any tax withheld against it treats an accrual as
    a payment and overstates the liability.
    """
    rule = "wh_accrued_not_withheld"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for payment in _payments(ctx):
        if _text(payment, "payment_status") != PAYMENT_STATUS_ACCRUED:
            continue
        with amount_guard(rule, out):
            withheld = require_cents(
                f"payment[{_payment_id(payment)}].tax_withheld_cents", payment.get("tax_withheld_cents")
            )
            if withheld != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"payments/{_payment_id(payment)}/tax_withheld_cents"),
                        f"payment {_payment_id(payment)} is accrued-only but shows {fmt(withheld)} "
                        f"withheld; only a paid amount is subject to withholding",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "no accrued-only amount is withheld on"))
    return out


@check("wh_rate_recomputes")
def check_wh_rate_recomputes(ctx: Context) -> list[Finding]:
    """Each subject payment's stated rate recomputes from the payee's status.

    This is the control the engine exists for. The rate applied to a payment is a
    *determination* -- FATCA override, then portfolio-interest exemption, then a
    treaty rate behind a valid W-8, then the statutory default -- and a
    determination that is not recomputed from the evidence is an assertion. The
    engine rebuilds every rate through the shared kernel and compares. Payments
    whose treaty rate the table does not carry are left to ``rate_table_defined``.
    """
    rule = "wh_rate_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    payees = _payee_map(ctx)
    treaty = _treaty_map(ctx)
    out: list[Finding] = []
    checked = 0
    for payment in _payments(ctx):
        if not _is_reportable(ctx, payment, payees):
            continue  # wh_us_payee_excluded / wh_accrued_not_withheld own the gate
        payee = payees[_text(payment, "payee_id") or ""]
        determined = _determined_rate_for(ctx, payment, payee, treaty, as_of)
        if determined is None:
            continue  # rate_table_defined owns the missing row
        with amount_guard(rule, out):
            stated = require_cents(
                f"payment[{_payment_id(payment)}].rate_applied_bps",
                payment.get("rate_applied_bps"),
                unit="a basis-point rate",
            )
            checked += 1
            if stated != determined:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"payments/{_payment_id(payment)}/rate_applied_bps"),
                        f"payment {_payment_id(payment)} applied {fmt_bps(stated)}; recomputing "
                        f"from payee {_payee_id(payee)}'s status gives {fmt_bps(determined)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} applied rates recompute from the evidence"))
    return out


@check("wh_tax_recomputes")
def check_wh_tax_recomputes(ctx: Context) -> list[Finding]:
    """Each payment's tax withheld equals its rate applied to its gross.

    The arithmetic is exact: ``tax == gross * rate // 10000`` in integer cents,
    with no tolerance. A tax that does not recompute from the rate and gross on the
    same line is a keying error the deposit and slip totals will inherit.
    """
    rule = "wh_tax_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for payment in _payments(ctx):
        with amount_guard(rule, out):
            gross = require_cents(
                f"payment[{_payment_id(payment)}].gross_cents", payment.get("gross_cents")
            )
            rate = require_cents(
                f"payment[{_payment_id(payment)}].rate_applied_bps",
                payment.get("rate_applied_bps"),
                unit="a basis-point rate",
            )
            withheld = require_cents(
                f"payment[{_payment_id(payment)}].tax_withheld_cents", payment.get("tax_withheld_cents")
            )
            checked += 1
            expected = apply_rate(gross, rate)
            if withheld != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"payments/{_payment_id(payment)}/tax_withheld_cents"),
                        f"payment {_payment_id(payment)} shows {fmt(withheld)} withheld; "
                        f"{fmt_bps(rate)} of {fmt(gross)} is {fmt(expected)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} tax figures recompute from rate x gross"))
    return out


# --------------------------------------------------------------------------- #
# exm_ -- exemption, validity and expiry
# --------------------------------------------------------------------------- #
@check("exm_w8_present_for_treaty")
def check_exm_w8_present_for_treaty(ctx: Context) -> list[Finding]:
    """A treaty-reduced rate is supported by a payee W-8 on file.

    A reduced rate that is neither the portfolio-interest exemption nor a FATCA
    override rests on a treaty claim, and a treaty claim is supported only by a
    Form W-8. A reduced rate against a payee with no valid W-8 on file is an
    unsupported reduction.
    """
    rule = "exm_w8_present_for_treaty"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    payees = _payee_map(ctx)
    out: list[Finding] = []
    for payment in _payments(ctx):
        if not _is_reportable(ctx, payment, payees):
            continue
        payee = payees[_text(payment, "payee_id") or ""]
        if _text(payee, "chapter_4_status_code") in NONPARTICIPATING_FFI_CODES:
            continue  # FATCA override, not a treaty reduction
        if _is_portfolio(ctx, payment) and _text(payment, "interest_subcharacter") != INTEREST_CONTINGENT:
            continue  # portfolio exemption, not a treaty reduction
        with amount_guard(rule, out):
            stated = require_cents(
                f"payment[{_payment_id(payment)}].rate_applied_bps",
                payment.get("rate_applied_bps"),
                unit="a basis-point rate",
            )
            if stated < STATUTORY_RATE_BPS and not bool(payee.get("has_valid_w8")):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"payments/{_payment_id(payment)}/rate_applied_bps"),
                        f"payment {_payment_id(payment)} applied a treaty-reduced {fmt_bps(stated)} "
                        f"but payee {_payee_id(payee)} has no valid Form W-8 on file",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every treaty-reduced rate is supported by a W-8"))
    return out


@check("exm_w8_not_expired")
def check_exm_w8_not_expired(ctx: Context) -> list[Finding]:
    """A payee's Form W-8 is unexpired at the review date.

    A W-8 has a three-year term; once it lapses the treaty claim resting on it is
    no longer supported. A payee that attests a valid W-8 whose term ends on or
    before the review date is holding an expired form.
    """
    rule = "exm_w8_not_expired"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    for payee in _payees(ctx):
        if not bool(payee.get("has_valid_w8")):
            continue
        expiration = _parse_date(payee.get("w8_expiration"))
        if expiration is None:
            continue
        if expiration <= as_of:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payees/{_payee_id(payee)}/w8_expiration"),
                    f"payee {_payee_id(payee)} holds a W-8 expiring {expiration.isoformat()}, on or "
                    f"before the review date {as_of.isoformat()}; the treaty claim is unsupported",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every payee W-8 is unexpired at the review date"))
    return out


@check("exm_w8_renewal_window")
def check_exm_w8_renewal_window(ctx: Context) -> list[Finding]:
    """A W-8 expiring inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the W-8 is still valid, but a fresh form
    needs to be collected before it lapses. The window comes from the file's own
    ``w8_renewal_lead_days``.
    """
    rule = "exm_w8_renewal_window"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_PAYEE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    lead = ctx.w8_renewal_lead_days
    out: list[Finding] = []
    for payee in _payees(ctx):
        if not bool(payee.get("has_valid_w8")) or _text(payee, "w8_status") != W8_STATUS_VALID:
            continue
        expiration = _parse_date(payee.get("w8_expiration"))
        if expiration is None:
            continue
        if within_renewal_window(expiration, as_of, lead):
            remaining = (expiration - as_of).days
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"payees/{_payee_id(payee)}/w8_expiration"),
                    f"payee {_payee_id(payee)} holds a W-8 expiring {expiration.isoformat()}, in "
                    f"{remaining} day(s); inside the {lead}-day renewal window and due to be refreshed",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "no payee W-8 is inside the renewal window"))
    return out


@check("exm_portfolio_interest_eligible")
def check_exm_portfolio_interest_eligible(ctx: Context) -> list[Finding]:
    """Portfolio-interest coding is used only on eligible interest.

    The portfolio-interest exemption reaches fixed interest, not contingent
    interest. A payment coded as portfolio interest whose sub-character is
    contingent has claimed an exemption the coupon is barred from.
    """
    rule = "exm_portfolio_interest_eligible"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    table = ctx.one(DOC_INCOME_CODE_TABLE)
    if register is None or table is None:
        return []
    out: list[Finding] = []
    for payment in _payments(ctx):
        if not _is_portfolio(ctx, payment):
            continue
        if _text(payment, "interest_subcharacter") == INTEREST_CONTINGENT:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payments/{_payment_id(payment)}/interest_subcharacter"),
                    f"payment {_payment_id(payment)} is coded portfolio interest but is contingent "
                    f"interest, which is ineligible for the portfolio-interest exemption",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every portfolio-interest coupon is eligible"))
    return out


@check("exm_fatca_override")
def check_exm_fatca_override(ctx: Context) -> list[Finding]:
    """A non-participating FFI is withheld at the statutory rate.

    Chapter 4 overrides Chapter 3: a payment to a non-participating FFI is withheld
    at the statutory 30% regardless of any treaty its residence country signed. A
    reduced rate on such a payee ignores the FATCA override.
    """
    rule = "exm_fatca_override"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYMENT_REGISTER)
    if register is None:
        return []
    payees = _payee_map(ctx)
    out: list[Finding] = []
    for payment in _payments(ctx):
        if not _is_reportable(ctx, payment, payees):
            continue
        payee = payees[_text(payment, "payee_id") or ""]
        if _text(payee, "chapter_4_status_code") not in NONPARTICIPATING_FFI_CODES:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"payment[{_payment_id(payment)}].rate_applied_bps",
                payment.get("rate_applied_bps"),
                unit="a basis-point rate",
            )
            if stated != STATUTORY_RATE_BPS:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"payments/{_payment_id(payment)}/rate_applied_bps"),
                        f"payment {_payment_id(payment)} to non-participating FFI {_payee_id(payee)} "
                        f"applied {fmt_bps(stated)}; the FATCA override requires the statutory "
                        f"{fmt_bps(STATUTORY_RATE_BPS)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every non-participating FFI is withheld at statutory"))
    return out


# --------------------------------------------------------------------------- #
# dep_ -- the deposits and the return filing
# --------------------------------------------------------------------------- #
@check("dep_total_ties_withheld")
def check_dep_total_ties_withheld(ctx: Context) -> list[Finding]:
    """The deposits equal the tax withheld across reportable payments.

    Every dollar withheld is a dollar owed to the government, and the deposits are
    how it gets there. A deposit total that does not equal the withheld total is an
    under- or over-deposit against the year's liability.
    """
    rule = "dep_total_ties_withheld"
    _sev(rule, Status.FAIL)
    deposit_reg = ctx.one(DOC_DEPOSIT_REGISTER)
    payment_reg = ctx.one(DOC_PAYMENT_REGISTER)
    if deposit_reg is None or payment_reg is None:
        return []
    payees = _payee_map(ctx)
    out: list[Finding] = []
    with amount_guard(rule, out):
        withheld = 0
        for payment in _payments(ctx):
            if not _is_reportable(ctx, payment, payees):
                continue
            withheld += require_cents(
                f"payment[{_payment_id(payment)}].tax_withheld_cents", payment.get("tax_withheld_cents")
            )
        deposited = 0
        for deposit in _deposits(ctx):
            deposited += require_cents(
                f"deposit[{_text(deposit, 'deposit_id')}].amount_cents", deposit.get("amount_cents")
            )
        if withheld != deposited:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(deposit_reg, "deposits"),
                    f"deposits total {fmt(deposited)}; tax withheld across reportable payments is "
                    f"{fmt(withheld)} (difference {fmt(deposited - withheld)})",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"deposits of {fmt(deposited)} tie the tax withheld")
            )
    return out


@check("dep_1042_filed_on_time")
def check_dep_1042_filed_on_time(ctx: Context) -> list[Finding]:
    """Form 1042 is filed on or before its due date.

    The annual return is due by a fixed date; a return filed after it is late,
    regardless of whether the deposits were made on time. Filing on the due date
    itself is timely -- the gate is ``filed <= due``.
    """
    rule = "dep_1042_filed_on_time"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_FORM_1042)
    if form is None:
        return []
    due = _parse_date(form.get("due_date"))
    filed = _parse_date(form.get("filed_date"))
    if due is None or filed is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(form, "filed_date"),
                f"Form 1042 carries due_date {form.get('due_date')!r} and filed_date "
                f"{form.get('filed_date')!r}; both must be readable dates to test timeliness",
            )
        ]
    if filed > due:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(form, "filed_date"),
                f"Form 1042 was filed {filed.isoformat()}, after its due date {due.isoformat()}; "
                f"the return is late",
            )
        ]
    return [Finding(rule, Status.PASS, "-", f"Form 1042 was filed {filed.isoformat()}, on or before {due.isoformat()}")]


# --------------------------------------------------------------------------- #
# rec_ -- the Form 1042 recomputes from the slips
# --------------------------------------------------------------------------- #
@check("rec_slip_per_payee")
def check_rec_slip_per_payee(ctx: Context) -> list[Finding]:
    """Exactly one 1042-S slip is filed per reportable payee.

    A 1042-S is filed for every non-US person paid reportable FDAP -- one per
    payee, no more and no fewer. A reportable payee with no slip is unreported; a
    payee with two slips double-counts; a slip for a payee with no reportable
    payment reports income that was never paid.
    """
    rule = "rec_slip_per_payee"
    _sev(rule, Status.FAIL)
    slip_reg = ctx.one(DOC_SLIP_REGISTER)
    payment_reg = ctx.one(DOC_PAYMENT_REGISTER)
    if slip_reg is None or payment_reg is None:
        return []
    payees = _payee_map(ctx)
    reportable = {
        _text(p, "payee_id")
        for p in _payments(ctx)
        if _is_reportable(ctx, p, payees)
    }
    slip_counts: dict[str, int] = {}
    for slip in _slips(ctx):
        pid = _text(slip, "payee_id")
        if pid:
            slip_counts[pid] = slip_counts.get(pid, 0) + 1
    out: list[Finding] = []
    for pid in sorted(x for x in reportable if x):
        count = slip_counts.get(pid, 0)
        if count != 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(slip_reg, f"slips/{pid}"),
                    f"reportable payee {pid} has {count} 1042-S slip(s); exactly one is filed per "
                    f"reportable payee",
                )
            )
    for pid in sorted(slip_counts):
        if pid not in reportable:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(slip_reg, f"slips/{pid}"),
                    f"a 1042-S slip is filed for payee {pid}, which has no reportable payment",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(reportable)} reportable payees have exactly one slip")
        )
    return out


@check("rec_gross_ties")
def check_rec_gross_ties(ctx: Context) -> list[Finding]:
    """Form 1042 total gross equals the sum of the 1042-S slips.

    The annual return's total income must equal the sum of the slips it transmits,
    which in turn is rebuilt from the reportable payments. A total that does not tie
    is a return that reports a different number than the slips underneath it.
    """
    rule = "rec_gross_ties"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_FORM_1042)
    slip_reg = ctx.one(DOC_SLIP_REGISTER)
    if form is None or slip_reg is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents("form_1042.total_gross_cents", form.get("total_gross_cents"))
        slip_total = 0
        for slip in _slips(ctx):
            slip_total += require_cents(
                f"slip[{_text(slip, 'payee_id')}].gross_cents", slip.get("gross_cents")
            )
        if stated != slip_total:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(form, "total_gross_cents"),
                    f"Form 1042 states total gross {fmt(stated)}; the 1042-S slips sum to "
                    f"{fmt(slip_total)} (difference {fmt(stated - slip_total)})",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"Form 1042 total gross of {fmt(stated)} ties the slips")
            )
    return out


@check("rec_withheld_ties")
def check_rec_withheld_ties(ctx: Context) -> list[Finding]:
    """Form 1042 total tax equals the sum of the 1042-S slips.

    The return's total withholding must equal the sum of the tax on the slips it
    transmits. A total that does not tie is a return whose tax line was maintained
    beside the slips rather than derived from them.
    """
    rule = "rec_withheld_ties"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_FORM_1042)
    slip_reg = ctx.one(DOC_SLIP_REGISTER)
    if form is None or slip_reg is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents("form_1042.total_withheld_cents", form.get("total_withheld_cents"))
        slip_total = 0
        for slip in _slips(ctx):
            slip_total += require_cents(
                f"slip[{_text(slip, 'payee_id')}].withheld_cents", slip.get("withheld_cents")
            )
        if stated != slip_total:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(form, "total_withheld_cents"),
                    f"Form 1042 states total tax {fmt(stated)}; the 1042-S slips sum to "
                    f"{fmt(slip_total)} (difference {fmt(stated - slip_total)})",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"Form 1042 total tax of {fmt(stated)} ties the slips")
            )
    return out


@check("rec_slip_count_ties_1042t")
def check_rec_slip_count_ties_1042t(ctx: Context) -> list[Finding]:
    """The 1042-T transmitted count equals the number of 1042-S slips.

    The 1042-T transmits the slips, and its count is what the government expects to
    receive. A transmitted count that does not equal the number of slips on file
    means the transmittal claims a different number of slips than were prepared.
    """
    rule = "rec_slip_count_ties_1042t"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_FORM_1042)
    slip_reg = ctx.one(DOC_SLIP_REGISTER)
    if form is None or slip_reg is None:
        return []
    actual = len(_slips(ctx))
    out: list[Finding] = []
    with amount_guard(rule, out):
        transmitted = require_cents(
            "form_1042.transmitted_count", form.get("transmitted_count"), unit="a whole count"
        )
        stated_count = require_cents("form_1042.slip_count", form.get("slip_count"), unit="a whole count")
        if transmitted != actual or stated_count != actual:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(form, "transmitted_count"),
                    f"Form 1042 states slip_count {stated_count} and 1042-T transmitted_count "
                    f"{transmitted}; {actual} 1042-S slip(s) are on file",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"the 1042-T count of {transmitted} ties the {actual} slips")
            )
    return out


@check("rec_w8_watchlist_ties")
def check_rec_w8_watchlist_ties(ctx: Context) -> list[Finding]:
    """The W-8 renewal watchlist ties the payee evidence.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a payee not actually due -- or omits one that is -- sends
    the W-8 refresh to the wrong place. It is rebuilt from the payee register and
    compared.
    """
    rule = "rec_w8_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_W8_WATCHLIST)
    as_of = _parse_date(ctx.as_of)
    if watchlist is None or as_of is None:
        return []
    recomputed = [
        _normalize_watch_entry(e) for e in recompute_w8_watchlist(ctx, as_of, ctx.w8_renewal_lead_days)
    ]
    stated = [_normalize_watch_entry(e) for e in _rows(watchlist, "entries")]
    want = sorted(recomputed)
    have = sorted(stated)
    out: list[Finding] = []
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"the watchlist lists payee {entry[0]} as due for W-8 renewal, but its W-8 is "
                        f"not inside the lead-time window as of {as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"payee {entry[0]} is due for W-8 renewal within the lead-time window but is "
                        f"not on the watchlist",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "the W-8 renewal watchlist ties the payee evidence"))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one withholding file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top level must be a JSON object")

    ctx = Context(path=path, data=raw)
    report = DocumentReport(document=ctx.file_id)
    for _rule_id, fn in REGISTRY:
        report.findings.extend(fn(ctx))
    return report


def analyze_folder(folder: Path) -> list[DocumentReport]:
    """Analyze every ``.json`` withholding file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of withholding-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
