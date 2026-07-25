"""
Debt term-sheet sizing & loan-terms control engine (READ-ONLY).
===============================================================

Loads each sizing file (a ``.json`` file produced by
:mod:`sizing_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the term sheet's arithmetic reconciles to the
terms it states**, not whether a draw is funded. Advancing money against a budget
line is a separate engine's job, and that engine explicitly declines to re-foot a
term sheet. This engine is that tie-out.

The shape of the problem
------------------------
A borrower runs several projects through legal at once, and each period a new
dated workbook lays the deals out side by side: max loan amount, max
loan-to-cost, the index + spread rate build-up over a floor, the LC and overdraft
facilities, the origination / commitment / unused / admin fees, the term and its
extension options, the recourse.

Three failures hide inside that, and none of them look wrong in a tidy grid: the
loan sized a cent over max loan-to-cost times the cost basis; the all-in rate or
a fee re-keyed rather than re-derived, so the number is wrong against the right
rate; and the portfolio rollup footed beside the deals rather than from them.

The registry is organised around that:

1. ``set_``   -- is the sizing file complete?
2. ``deal_``  -- is the deal register sound, and is every enumerated field on its list?
3. ``size_``  -- is the loan within the advance rate, the draw within the loan, the maturity reconciled?
4. ``rate_``  -- does every deal have a build-up, and does the all-in rate recompute?
5. ``fee_``   -- is every fee line well-typed, attributable, and does its amount recompute?
6. ``exp_``   -- is the term sheet still live, and what is due to expire?
7. ``rpt_``   -- does the rollup foot and tie across the deals?

Design notes
------------
- **Strictly read-only.** Sizing files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every figure is compared with exact ``==``.
- **One arithmetic kernel.** Controls and the generator share the re-derivation
  in :mod:`sizing_engine.terms`, so a figure cannot disagree with the data that
  produced it.
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
    BASE_TYPES,
    DOC_DEAL_REGISTER,
    DOC_EXPIRY_WATCHLIST,
    DOC_FEE_SCHEDULE,
    DOC_FEE_SUMMARY,
    DOC_RATE_BUILDUP,
    DOC_RATE_SUMMARY,
    DOC_TERM_SHEET_ROLLUP,
    DOC_TYPES,
    FEE_TYPES,
    INDEX_NAMES,
    LOAN_TYPES,
    RECOURSE_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents
from .terms import (
    all_in_rate_bps,
    fee_amount_cents,
    fee_base_cents,
    ltc_cap_cents,
    maturity_months,
    termsheet_expired,
    within_expiry_window,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~sizing_engine.money.AmountInvalidError` as a finding."""
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

_BPS = "integer basis points"
_COUNT = "a whole count"
_MONTHS = "a whole number of months"


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


def _int_list(row: dict[str, Any], key: str) -> list[int]:
    value = row.get(key)
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, int) and not isinstance(v, bool)]


# --------------------------------------------------------------------------- #
# Sizing-file helpers
# --------------------------------------------------------------------------- #
def _deals(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DEAL_REGISTER), "deals")


def _deal_id(row: dict[str, Any]) -> str:
    value = row.get("deal_id")
    return value if isinstance(value, str) and value else "?"


def _deal_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _deals(ctx):
        did = _deal_id(row)
        if did != "?" and did not in out:
            out[did] = row
    return out


def _buildups(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_RATE_BUILDUP), "buildups")


def _buildup_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _buildups(ctx):
        did = _text(row, "deal_id")
        if did and did not in out:
            out[did] = row
    return out


def _fees(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_FEE_SCHEDULE), "fees")


def _fee_id(row: dict[str, Any]) -> str:
    value = row.get("fee_id")
    return value if isinstance(value, str) and value else "?"


def _fee_line_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _fees(ctx):
        fid = _fee_id(row)
        if fid != "?" and fid not in out:
            out[fid] = row
    return out


def _rate_summary_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_RATE_SUMMARY), "rates")


def _fee_summary_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_FEE_SUMMARY), "amounts")


def _watchlist_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_EXPIRY_WATCHLIST), "entries")


# --------------------------------------------------------------------------- #
# Re-derivation shared with the generator
# --------------------------------------------------------------------------- #
def recompute_all_in(ctx: Context, deal: dict[str, Any]) -> int | None:
    """The deal's all-in rate re-derived from its build-up, or ``None``.

    ``None`` when the deal has no build-up row -- ``rate_buildup_present`` owns
    that gap. Raises :class:`AmountInvalidError` if a build-up figure it must read
    is not an integer basis-point value; the calling control contains that.
    """
    buildup = _buildup_map(ctx).get(_deal_id(deal))
    if buildup is None:
        return None
    index = require_cents("rate_buildup.index_bps", buildup.get("index_bps"), unit=_BPS)
    spread = require_cents("rate_buildup.spread_bps", buildup.get("spread_bps"), unit=_BPS)
    floor = require_cents("rate_buildup.floor_bps", buildup.get("floor_bps"), unit=_BPS)
    return all_in_rate_bps(index, spread, floor)


def recompute_fee_amount(ctx: Context, fee_line: dict[str, Any]) -> int | None:
    """A fee line's amount re-derived from its base and rate, or ``None``.

    ``None`` when the line names no deal in the register (``fee_deal_exists``
    owns it) or carries an unknown base type (``fee_base_type_valid`` owns it), so
    a line that could not be priced is skipped rather than mispriced. Raises
    :class:`AmountInvalidError` if an amount it must read is not integer cents.
    """
    deal = _deal_map(ctx).get(_text(fee_line, "deal_id") or "")
    if deal is None:
        return None
    base_type = _text(fee_line, "base_type")
    if base_type not in BASE_TYPES:
        return None
    commitment = require_cents(
        f"deal[{_deal_id(deal)}].max_loan_amount_cents", deal.get("max_loan_amount_cents")
    )
    drawn = require_cents(
        f"deal[{_deal_id(deal)}].drawn_amount_cents", deal.get("drawn_amount_cents")
    )
    facility = require_cents(
        f"deal[{_deal_id(deal)}].facility_limit_cents", deal.get("facility_limit_cents")
    )
    base = fee_base_cents(base_type, commitment, drawn, facility)
    if base is None:
        return None
    rate = require_cents(
        f"fee[{_fee_id(fee_line)}].fee_rate_bps", fee_line.get("fee_rate_bps"), unit=_BPS
    )
    return fee_amount_cents(base, rate)


def recompute_total_commitment(ctx: Context) -> int:
    """Portfolio total commitment: the sum of every deal's max loan amount.

    Raises :class:`AmountInvalidError` on a malformed max-loan figure; the calling
    control contains it.
    """
    total = 0
    for deal in _deals(ctx):
        total += require_cents(
            f"deal[{_deal_id(deal)}].max_loan_amount_cents",
            deal.get("max_loan_amount_cents"),
        )
    return total


def recompute_total_fees(ctx: Context) -> int:
    """Portfolio total fees: the sum of every priceable fee line's amount.

    Lines that cannot be priced -- no deal, unknown base -- are skipped, exactly
    as the fee-amount control skips them, so the total foots the same set of lines
    the per-line control checks.
    """
    total = 0
    for line in _fees(ctx):
        amount = recompute_fee_amount(ctx, line)
        if amount is not None:
            total += amount
    return total


def recompute_expiry_watchlist(ctx: Context, as_of: date, lead_days: int) -> list[dict[str, Any]]:
    """The expiry watchlist re-derived from the deals.

    One entry per deal whose term sheet expires inside the lead-time window.
    Shared with the generator so the stated watchlist can be tied to it. Reads no
    amounts, so it never raises on a malformed figure.
    """
    entries: list[dict[str, Any]] = []
    for deal in _deals(ctx):
        expiration = _parse_date(deal.get("termsheet_expiration_date"))
        if expiration is None:
            continue
        if within_expiry_window(expiration, as_of, lead_days):
            entries.append(
                {
                    "deal_id": _deal_id(deal),
                    "termsheet_expiration_date": deal.get("termsheet_expiration_date"),
                    "days_remaining": (expiration - as_of).days,
                }
            )
    entries.sort(key=lambda e: (e["deal_id"], e["termsheet_expiration_date"]))
    return entries


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("deal_id"),
        entry.get("termsheet_expiration_date"),
        entry.get("days_remaining"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the sizing file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the sizing file carries "
                    f"exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} sizing artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every term-sheet expiry test "
                f"is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# deal_ -- the deal register and its enumerated fields
# --------------------------------------------------------------------------- #
@check("deal_unique_ids")
def check_deal_unique_ids(ctx: Context) -> list[Finding]:
    """No deal id appears twice.

    The deal id joins the register to the build-up, the fees and every rollup. A
    duplicate double-counts the deal in the portfolio total and makes a fee
    ambiguous about which deal it prices.
    """
    rule = "deal_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _deals(ctx):
        seen[_deal_id(row)] = seen.get(_deal_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"deals/{did}"),
            f"deal id {did} appears {count} times; it would be double-counted in the "
            f"portfolio total and its fees could not be attributed",
        )
        for did, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} deal ids are unique"))
    return out


@check("deal_loan_type_valid")
def check_deal_loan_type_valid(ctx: Context) -> list[Finding]:
    """Every deal carries a loan type from the allowed list.

    An unlisted loan type is a re-keying error in a governing field; the workbook
    would sort and total it as a product the sizing rhythm does not recognise.
    """
    rule = "deal_loan_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _deals(ctx):
        loan_type = _text(row, "loan_type")
        if loan_type not in LOAN_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deals/{_deal_id(row)}/loan_type"),
                    f"deal {_deal_id(row)} is typed {loan_type!r}, which is not one of "
                    f"{LOAN_TYPES}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_deals(ctx))} deals carry a known loan type")
        )
    return out


@check("deal_index_valid")
def check_deal_index_valid(ctx: Context) -> list[Finding]:
    """Every deal names a reference index from the allowed list.

    The index name is the label the rate build-up is struck against; an unlisted
    one describes a build-up nobody can source or reprice.
    """
    rule = "deal_index_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _deals(ctx):
        index = _text(row, "index_name")
        if index not in INDEX_NAMES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deals/{_deal_id(row)}/index_name"),
                    f"deal {_deal_id(row)} names index {index!r}, which is not one of "
                    f"{INDEX_NAMES}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_deals(ctx))} deals name a known index")
        )
    return out


@check("deal_recourse_valid")
def check_deal_recourse_valid(ctx: Context) -> list[Finding]:
    """Every deal carries a recourse structure from the allowed list.

    Recourse governs who stands behind the loan; an unlisted value is a term the
    credit approval never granted riding on the term sheet.
    """
    rule = "deal_recourse_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _deals(ctx):
        recourse = _text(row, "recourse_type")
        if recourse not in RECOURSE_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deals/{_deal_id(row)}/recourse_type"),
                    f"deal {_deal_id(row)} carries recourse {recourse!r}, which is not one "
                    f"of {RECOURSE_TYPES}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_deals(ctx))} deals carry a known recourse type")
        )
    return out


@check("deal_basis_declared")
def check_deal_basis_declared(ctx: Context) -> list[Finding]:
    """Every deal declares a positive cost basis and advance rate.

    These are the two inputs the over-advance control divides against. A deal with
    no cost basis or no max loan-to-cost is a deal whose sizing terms were never
    captured, so the advance-rate control would have nothing to hold the loan to
    and pass vacuously.
    """
    rule = "deal_basis_declared"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _deals(ctx):
        did = _deal_id(row)
        cost_basis = _int(row, "cost_basis_cents")
        max_ltc = _int(row, "max_ltc_bps")
        if cost_basis is None or cost_basis <= 0:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deals/{did}/cost_basis_cents"),
                    f"deal {did} declares no positive cost basis; the advance-rate control "
                    f"would have no base to size the loan against",
                )
            )
        elif max_ltc is None or max_ltc <= 0:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deals/{did}/max_ltc_bps"),
                    f"deal {did} declares no positive max loan-to-cost; the advance-rate "
                    f"control would have no rate to size the loan against",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_deals(ctx))} deals declare a cost basis and an advance rate",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# size_ -- the sizing constraints
# --------------------------------------------------------------------------- #
@check("size_ltc_not_exceeded")
def check_size_ltc_not_exceeded(ctx: Context) -> list[Finding]:
    """The max loan amount does not exceed max loan-to-cost times the cost basis.

    This is the over-advance control. The cap is recomputed with truncating
    basis-point math and compared with exact ``<=``: a loan a cent above the cap
    is a loan over the advance rate. Deals with no declared basis are left to
    ``deal_basis_declared``.
    """
    rule = "size_ltc_not_exceeded"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _deals(ctx):
        did = _deal_id(row)
        cost_basis = _int(row, "cost_basis_cents")
        max_ltc = _int(row, "max_ltc_bps")
        if cost_basis is None or cost_basis <= 0 or max_ltc is None or max_ltc <= 0:
            continue  # deal_basis_declared owns this
        with amount_guard(rule, out):
            max_loan = require_cents(
                f"deal[{did}].max_loan_amount_cents", row.get("max_loan_amount_cents")
            )
            cap = ltc_cap_cents(cost_basis, max_ltc)
            checked += 1
            if max_loan > cap:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"deals/{did}/max_loan_amount_cents"),
                        f"deal {did} is sized to {fmt(max_loan)}; max loan-to-cost "
                        f"{fmt_bps(max_ltc)} of cost basis {fmt(cost_basis)} caps the loan at "
                        f"{fmt(cap)} (over by {fmt(max_loan - cap)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} loans are within the advance rate")
        )
    return out


@check("size_drawn_within_commitment")
def check_size_drawn_within_commitment(ctx: Context) -> list[Finding]:
    """The drawn amount does not exceed the committed max loan amount.

    A draw above the commitment is either a re-keyed drawn balance or a facility
    advancing past its own ceiling; the undrawn base every unused fee is struck on
    would go negative underneath it.
    """
    rule = "size_drawn_within_commitment"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _deals(ctx):
        did = _deal_id(row)
        with amount_guard(rule, out):
            max_loan = require_cents(
                f"deal[{did}].max_loan_amount_cents", row.get("max_loan_amount_cents")
            )
            drawn = require_cents(
                f"deal[{did}].drawn_amount_cents", row.get("drawn_amount_cents")
            )
            checked += 1
            if drawn > max_loan:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"deals/{did}/drawn_amount_cents"),
                        f"deal {did} is drawn {fmt(drawn)} against a commitment of "
                        f"{fmt(max_loan)} (over by {fmt(drawn - max_loan)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} draws are within their commitment")
        )
    return out


@check("size_maturity_reconciles")
def check_size_maturity_reconciles(ctx: Context) -> list[Finding]:
    """Base term plus every extension option reconciles to the stated maturity.

    The maturity on the term sheet is the fully-extended one, so it must equal the
    base term plus the sum of the extension options, exactly. A mismatch is a term
    re-keyed without re-adding the extensions.
    """
    rule = "size_maturity_reconciles"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _deals(ctx):
        did = _deal_id(row)
        base_term = _int(row, "base_term_months")
        stated = _int(row, "stated_maturity_months")
        if base_term is None or stated is None:
            continue
        extensions = _int_list(row, "extension_options_months")
        recomputed = maturity_months(base_term, extensions)
        checked += 1
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deals/{did}/stated_maturity_months"),
                    f"deal {did} states a {stated}-month maturity; base term {base_term} plus "
                    f"extensions {extensions} reconciles to {recomputed}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} maturities reconcile to term plus extensions")
        )
    return out


# --------------------------------------------------------------------------- #
# rate_ -- the rate build-up
# --------------------------------------------------------------------------- #
@check("rate_buildup_present")
def check_rate_buildup_present(ctx: Context) -> list[Finding]:
    """Every deal has a rate build-up row.

    Without the build-up the engine knows the deal carries an all-in rate but not
    the index, spread and floor it was struck from, so the recompute control would
    silently skip it. Duplicate build-ups for one deal are a break for the same
    reason: the recompute would not know which one governs.
    """
    rule = "rate_buildup_present"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_RATE_BUILDUP)
    if register is None:
        return []
    counts: dict[str, int] = {}
    for row in _buildups(ctx):
        did = _text(row, "deal_id")
        if did:
            counts[did] = counts.get(did, 0) + 1
    out: list[Finding] = []
    for deal in _deals(ctx):
        did = _deal_id(deal)
        seen = counts.get(did, 0)
        if seen == 0:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"buildups/{did}"),
                    f"deal {did} has no rate build-up row; its all-in rate cannot be "
                    f"recomputed from an index, spread and floor",
                )
            )
        elif seen > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"buildups/{did}"),
                    f"deal {did} has {seen} rate build-up rows; the recompute cannot know "
                    f"which one governs",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_deals(ctx))} deals have exactly one build-up")
        )
    return out


@check("rate_all_in_recomputes")
def check_rate_all_in_recomputes(ctx: Context) -> list[Finding]:
    """Each deal's stated all-in rate recomputes from its build-up.

    This is a re-derivation control. The all-in rate is ``max(index + spread,
    floor)``; a rate typed as index-plus-spread where the floor governs, or the
    other way round, is caught by rebuilding it from the components and comparing.
    """
    rule = "rate_all_in_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RATE_SUMMARY)
    if summary is None:
        return []
    deals = _deal_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _rate_summary_rows(ctx):
        did = _text(row, "deal_id")
        deal = deals.get(did or "")
        if deal is None:
            continue
        with amount_guard(rule, out):
            recomputed = recompute_all_in(ctx, deal)
            if recomputed is None:
                continue  # rate_buildup_present owns this
            stated = require_cents(
                f"rate_summary[{did}].all_in_rate_bps", row.get("all_in_rate_bps"), unit=_BPS
            )
            checked += 1
            if stated != recomputed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"rates/{did}/all_in_rate_bps"),
                        f"deal {did} states an all-in rate of {fmt_bps(stated)}; the build-up "
                        f"recomputes to {fmt_bps(recomputed)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} all-in rates recompute from their build-up")
        )
    return out


# --------------------------------------------------------------------------- #
# fee_ -- the fee schedule
# --------------------------------------------------------------------------- #
@check("fee_type_valid")
def check_fee_type_valid(ctx: Context) -> list[Finding]:
    """Every fee line carries a fee type from the allowed list."""
    rule = "fee_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FEE_SCHEDULE)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _fees(ctx):
        fee_type = _text(row, "fee_type")
        if fee_type not in FEE_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"fees/{_fee_id(row)}/fee_type"),
                    f"fee {_fee_id(row)} is typed {fee_type!r}, which is not one of {FEE_TYPES}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_fees(ctx))} fee lines carry a known type")
        )
    return out


@check("fee_base_type_valid")
def check_fee_base_type_valid(ctx: Context) -> list[Finding]:
    """Every fee line is struck on a base from the allowed list.

    The base -- commitment, drawn, undrawn or facility -- is what the rate is
    applied to. An unknown base cannot be priced, so a line carrying one satisfies
    nothing while looking like a fee.
    """
    rule = "fee_base_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FEE_SCHEDULE)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _fees(ctx):
        base_type = _text(row, "base_type")
        if base_type not in BASE_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"fees/{_fee_id(row)}/base_type"),
                    f"fee {_fee_id(row)} is struck on base {base_type!r}, which is not one of "
                    f"{BASE_TYPES}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_fees(ctx))} fee lines carry a known base")
        )
    return out


@check("fee_deal_exists")
def check_fee_deal_exists(ctx: Context) -> list[Finding]:
    """Every fee line names a deal in the register."""
    rule = "fee_deal_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FEE_SCHEDULE)
    if register is None:
        return []
    deals = _deal_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"fees/{_fee_id(row)}/deal_id"),
            f"fee {_fee_id(row)} names deal {_text(row, 'deal_id')!r}, which is not in the "
            f"deal register",
        )
        for row in _fees(ctx)
        if _text(row, "deal_id") and _text(row, "deal_id") not in deals
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every fee line names a deal in the register"))
    return out


@check("fee_amount_recomputes")
def check_fee_amount_recomputes(ctx: Context) -> list[Finding]:
    """Each fee line's stated amount recomputes from its base and rate.

    A re-derivation control. Every fee is the truncating basis-point product of its
    rate and its correct base; a fee struck on the wrong base, or copied across
    from another line, is caught by rebuilding it and comparing with exact ``==``.
    """
    rule = "fee_amount_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_FEE_SUMMARY)
    if summary is None:
        return []
    lines = _fee_line_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _fee_summary_rows(ctx):
        fid = _text(row, "fee_id")
        line = lines.get(fid or "")
        if line is None:
            continue
        with amount_guard(rule, out):
            recomputed = recompute_fee_amount(ctx, line)
            if recomputed is None:
                continue  # fee_deal_exists / fee_base_type_valid own this
            stated = require_cents(
                f"fee_summary[{fid}].fee_amount_cents", row.get("fee_amount_cents")
            )
            checked += 1
            if stated != recomputed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"amounts/{fid}/fee_amount_cents"),
                        f"fee {fid} states {fmt(stated)}; its rate on the "
                        f"{_text(line, 'base_type')} base recomputes to {fmt(recomputed)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} fee amounts recompute from base and rate")
        )
    return out


# --------------------------------------------------------------------------- #
# exp_ -- term-sheet currency
# --------------------------------------------------------------------------- #
@check("exp_termsheet_not_expired")
def check_exp_termsheet_not_expired(ctx: Context) -> list[Finding]:
    """Every deal's term sheet is still live at the pricing date.

    A term sheet expiring on or before the review date can no longer be relied on
    to close; the workbook still shows terms, but the lender's commitment behind
    them has lapsed.
    """
    rule = "exp_termsheet_not_expired"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_DEAL_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _deals(ctx):
        expiration = _parse_date(row.get("termsheet_expiration_date"))
        if expiration is None:
            continue
        checked += 1
        if termsheet_expired(expiration, as_of):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"deals/{_deal_id(row)}/termsheet_expiration_date"),
                    f"deal {_deal_id(row)} term sheet expired {expiration.isoformat()}, on or "
                    f"before the pricing date {as_of.isoformat()}; its terms cannot close",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} term sheets are live at the pricing date")
        )
    return out


@check("exp_termsheet_lead_time")
def check_exp_termsheet_lead_time(ctx: Context) -> list[Finding]:
    """A term sheet expiring inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the term sheet is still live, but it needs
    to close before it lapses. The window comes from the file's own
    ``commitment_lead_days``.
    """
    rule = "exp_termsheet_lead_time"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_DEAL_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    lead = ctx.commitment_lead_days
    out: list[Finding] = []
    checked = 0
    for row in _deals(ctx):
        expiration = _parse_date(row.get("termsheet_expiration_date"))
        if expiration is None:
            continue
        checked += 1
        if within_expiry_window(expiration, as_of, lead):
            remaining = (expiration - as_of).days
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"deals/{_deal_id(row)}/termsheet_expiration_date"),
                    f"deal {_deal_id(row)} term sheet expires {expiration.isoformat()}, in "
                    f"{remaining} day(s); inside the {lead}-day window and due to close",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} term sheets are outside the lead-time window"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup foots and ties
# --------------------------------------------------------------------------- #
@check("rpt_deal_count_ties")
def check_rpt_deal_count_ties(ctx: Context) -> list[Finding]:
    """The rollup's active-deal count ties the deal register."""
    rule = "rpt_deal_count_ties"
    _sev(rule, Status.FAIL)
    rollup = ctx.one(DOC_TERM_SHEET_ROLLUP)
    register = ctx.one(DOC_DEAL_REGISTER)
    if rollup is None or register is None:
        return []
    recomputed = len(_deals(ctx))
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "term_sheet_rollup.deal_count", rollup.get("deal_count"), unit=_COUNT
        )
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, "deal_count"),
                    f"the rollup states {stated} active deals; the register carries "
                    f"{recomputed}",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"the rollup count of {recomputed} ties the register"
                )
            )
    return out


@check("rpt_commitment_total_ties")
def check_rpt_commitment_total_ties(ctx: Context) -> list[Finding]:
    """The rollup's total commitment foots the sum of the deals' max loan amounts."""
    rule = "rpt_commitment_total_ties"
    _sev(rule, Status.FAIL)
    rollup = ctx.one(DOC_TERM_SHEET_ROLLUP)
    register = ctx.one(DOC_DEAL_REGISTER)
    if rollup is None or register is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        recomputed = recompute_total_commitment(ctx)
        stated = require_cents(
            "term_sheet_rollup.total_commitment_cents", rollup.get("total_commitment_cents")
        )
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, "total_commitment_cents"),
                    f"the rollup states {fmt(stated)} total commitment; the deals foot to "
                    f"{fmt(recomputed)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the rollup total commitment of {fmt(recomputed)} foots the deals",
                )
            )
    return out


@check("rpt_fee_total_ties")
def check_rpt_fee_total_ties(ctx: Context) -> list[Finding]:
    """The rollup's total fees foots the sum of every priceable fee line."""
    rule = "rpt_fee_total_ties"
    _sev(rule, Status.FAIL)
    rollup = ctx.one(DOC_TERM_SHEET_ROLLUP)
    schedule = ctx.one(DOC_FEE_SCHEDULE)
    if rollup is None or schedule is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        recomputed = recompute_total_fees(ctx)
        stated = require_cents(
            "term_sheet_rollup.total_fees_cents", rollup.get("total_fees_cents")
        )
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rollup, "total_fees_cents"),
                    f"the rollup states {fmt(stated)} total fees; the fee lines foot to "
                    f"{fmt(recomputed)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"the rollup total fees of {fmt(recomputed)} foots the lines"
                )
            )
    return out


@check("rpt_expiry_watchlist_ties")
def check_rpt_expiry_watchlist_ties(ctx: Context) -> list[Finding]:
    """The expiry watchlist ties the deals actually due to expire.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a term sheet not actually expiring -- or omits one that
    is -- sends the close chase to the wrong deal. It is rebuilt from the deals
    and compared.
    """
    rule = "rpt_expiry_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_EXPIRY_WATCHLIST)
    as_of = _parse_date(ctx.as_of)
    if watchlist is None or as_of is None:
        return []
    recomputed = [
        _normalize_entry(e)
        for e in recompute_expiry_watchlist(ctx, as_of, ctx.commitment_lead_days)
    ]
    stated = [_normalize_entry(e) for e in _watchlist_entries(ctx)]
    out: list[Finding] = []
    want = sorted(recomputed)
    have = sorted(stated)
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"the watchlist lists deal {entry[0]} as expiring, but its term sheet "
                        f"is not inside the lead-time window as of {as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"deal {entry[0]} term sheet is inside the lead-time window but is not "
                        f"on the expiry watchlist",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the expiry watchlist ties the deals due to expire")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one sizing file."""
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
    """Analyze every ``.json`` sizing file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of sizing-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
