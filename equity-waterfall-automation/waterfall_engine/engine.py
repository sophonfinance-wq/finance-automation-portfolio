"""
Equity-waterfall & JV-promote control engine (READ-ONLY).
=========================================================

Loads each deal file (a ``.json`` file produced by
:mod:`waterfall_engine.generate`) and runs an ordered *registry* of independent
controls over it.

The shape of the problem
------------------------
A real-estate joint venture pools an investor's and a developer's capital, accrues
a preferred return on it, then distributes proceeds down a contractual waterfall
whose tiers pay in a strict order and whose upper tiers split the upside between
the two on a promote. Every one of those numbers is derived from the ones above
it, so a single wrong figure -- a mis-compounded month, a tier out of order, a
split struck off the wrong weights -- travels silently to the developer's carry
and the investor's multiple.

The registry is organised around that chain:

1. ``set_``    -- is the deal file complete?
2. ``mbr_``    -- is the member register sound and the venture well-formed?
3. ``pref_``   -- does the preferred-return accrual re-derive?
4. ``cap_``    -- does each capital account roll forward and zero out?
5. ``wf_``     -- do the tiers pay in order and split pari passu correctly?
6. ``hurdle_`` -- is the hurdle boundary solved from the contributions?
7. ``promo_``  -- do the promote splits sum, and does the carry re-derive?
8. ``loan_``   -- are the member-loan rates sound and repaid before distribution?
9. ``dil_``    -- does the capital-call dilution recompute?
10. ``dist_``  -- does every distributed cent tie out with no leakage?
11. ``ret_``   -- does the realized-returns summary recompute from the waterfall?
12. ``cov_``   -- do the financing covenants hold (secondary)?
13. ``syn_``   -- does the syndicate draw re-derive (secondary)?

Design notes
------------
- **Strictly read-only.** Deal files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every figure is compared with exact ``==``.
- **One waterfall kernel.** Controls and the generator share the arithmetic in
  :mod:`waterfall_engine.waterfall`, so a figure the engine recomputes cannot
  disagree with the arithmetic that produced it.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.
"""

from __future__ import annotations

import contextlib
import functools
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .money import AmountInvalidError, fmt, fmt_bps, require_cents
from .model import (
    DILUTION_METHODS,
    DILUTION_PENALTY_BPS,
    DOC_CAPITAL_LEDGER,
    DOC_DEAL_TERMS,
    DOC_DILUTION_WORKSHEET,
    DOC_LOAN_COVENANT,
    DOC_MEMBER_REGISTER,
    DOC_RETURNS_SUMMARY,
    DOC_TYPES,
    DOC_WATERFALL_SCHEDULE,
    ROLE_DEVELOPER,
    ROLE_INVESTOR,
    ROLES,
    SYNDICATE_CALL_BPS,
    TIER_CAPITAL,
    TIER_ORDER,
    TIER_PREF,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .waterfall import (
    Contribution,
    WaterfallResult,
    dilution_interest,
    equity_multiple_bps,
    hurdle_target,
    loan_repayment,
    roll_forward,
    run_waterfall,
    split_pro_rata,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~waterfall_engine.money.AmountInvalidError` as a finding."""
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


def _sev(rule_id: str, status: Status) -> Status:
    SEVERITY[rule_id] = status
    return status


# --------------------------------------------------------------------------- #
# Field readers
# --------------------------------------------------------------------------- #
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
    """Read an integer field non-raisingly (``bool`` rejected)."""
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# --------------------------------------------------------------------------- #
# Deal-file helpers
# --------------------------------------------------------------------------- #
def _terms(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_DEAL_TERMS)


def _members(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_MEMBER_REGISTER), "members")


def _member_id(row: dict[str, Any]) -> str:
    value = row.get("member_id")
    return value if isinstance(value, str) and value else "?"


def _role(row: dict[str, Any]) -> str | None:
    return _text(row, "role")


def _member_by_id(ctx: Context, member_id: str) -> dict[str, Any] | None:
    for row in _members(ctx):
        if _member_id(row) == member_id:
            return row
    return None


def _first_id_with_role(ctx: Context, role: str) -> str | None:
    for row in _members(ctx):
        if _role(row) == role:
            mid = _member_id(row)
            if mid != "?":
                return mid
    return None


def _investor_id(ctx: Context) -> str | None:
    return _first_id_with_role(ctx, ROLE_INVESTOR)


def _developer_id(ctx: Context) -> str | None:
    return _first_id_with_role(ctx, ROLE_DEVELOPER)


def _contributions(row: dict[str, Any]) -> list[Contribution]:
    """Parse a member's funded contributions.

    Raises :class:`AmountInvalidError` if an amount is not integer cents; a
    contribution with a non-integer month index is skipped as structurally
    unreadable rather than coerced.
    """
    out: list[Contribution] = []
    raw = row.get("contributions")
    if not isinstance(raw, list):
        return out
    for c in raw:
        if not isinstance(c, dict):
            continue
        period = c.get("period")
        if isinstance(period, bool) or not isinstance(period, int):
            continue
        amount = require_cents(
            f"member[{_member_id(row)}].contribution.amount_cents",
            c.get("amount_cents"),
        )
        out.append(Contribution(period, amount))
    return out


def _total_contributions(row: dict[str, Any]) -> int:
    return sum(c.amount_cents for c in _contributions(row))


# --------------------------------------------------------------------------- #
# Shared re-derivation (imported by the generator, so the data it produces is
# the data these controls recompute).
# --------------------------------------------------------------------------- #
def recompute_accounts(ctx: Context) -> dict[str, Any] | None:
    """Each member's capital accounts rolled forward to ``as_of_period``."""
    terms = _terms(ctx)
    periods = ctx.as_of_period
    if terms is None or periods is None:
        return None
    rate = _int(terms, "pref_rate_bps")
    if rate is None:
        return None
    out: dict[str, Any] = {}
    for row in _members(ctx):
        mid = _member_id(row)
        if mid == "?":
            continue
        out[mid] = roll_forward(_contributions(row), rate, periods)
    return out


def recompute_hurdle_target(ctx: Context) -> int | None:
    """The investor's hurdle target, re-derived from its contributions."""
    terms = _terms(ctx)
    periods = ctx.as_of_period
    inv = _investor_id(ctx)
    if terms is None or periods is None or inv is None:
        return None
    hrate = _int(terms, "hurdle_rate_bps")
    inv_row = _member_by_id(ctx, inv)
    if hrate is None or inv_row is None:
        return None
    return hurdle_target(_contributions(inv_row), hrate, periods)


def recompute_loan(ctx: Context) -> dict[str, int] | None:
    """The member loan's repayment and interest, re-derived."""
    terms = _terms(ctx)
    loan = ctx.one(DOC_LOAN_COVENANT)
    if terms is None or loan is None:
        return None
    rate = _int(terms, "member_loan_rate_bps")
    periods = _int(loan, "member_loan_periods")
    if rate is None or periods is None:
        return None
    principal = require_cents(
        "loan_covenant.member_loan_principal_cents",
        loan.get("member_loan_principal_cents"),
    )
    repayment = loan_repayment(principal, rate, periods)
    return {"principal": principal, "repayment": repayment, "interest": repayment - principal}


def recompute_waterfall(ctx: Context) -> WaterfallResult | None:
    """The full distribution, re-derived from the base facts."""
    terms = _terms(ctx)
    accounts = recompute_accounts(ctx)
    inv = _investor_id(ctx)
    dev = _developer_id(ctx)
    loan = recompute_loan(ctx)
    ht = recompute_hurdle_target(ctx)
    if terms is None or accounts is None or inv is None or dev is None:
        return None
    if loan is None or ht is None or inv not in accounts or dev not in accounts:
        return None
    tc_inv = _int(terms, "tier_c_investor_bps")
    tc_dev = _int(terms, "tier_c_developer_bps")
    td_inv = _int(terms, "tier_d_investor_bps")
    td_dev = _int(terms, "tier_d_developer_bps")
    if None in (tc_inv, tc_dev, td_inv, td_dev):
        return None
    proceeds = require_cents("deal_terms.proceeds_cents", terms.get("proceeds_cents"))
    proceeds_after = proceeds - loan["repayment"]
    preferred = {
        inv: accounts[inv].investment_return_account_cents,
        dev: accounts[dev].investment_return_account_cents,
    }
    capital = {
        inv: accounts[inv].contribution_account_cents,
        dev: accounts[dev].contribution_account_cents,
    }
    return run_waterfall(
        proceeds_after, inv, dev, preferred, capital, ht,
        tc_inv, tc_dev, td_inv, td_dev,
    )


def recompute_syndicate_draw(ctx: Context) -> int | None:
    """The syndicate capital-call draw, re-derived from the commitment."""
    terms = _terms(ctx)
    loan = ctx.one(DOC_LOAN_COVENANT)
    if terms is None or loan is None:
        return None
    call_bps = _int(terms, "syndicate_call_bps")
    if call_bps is None:
        return None
    commitment = require_cents(
        "loan_covenant.syndicate_commitment_cents",
        loan.get("syndicate_commitment_cents"),
    )
    return commitment * call_bps // 10000


def recompute_dilution(ctx: Context) -> dict[str, Any] | None:
    """The capital-call dilution recompute, from the default event's inputs."""
    terms = _terms(ctx)
    work = ctx.one(DOC_DILUTION_WORKSHEET)
    if terms is None or work is None:
        return None
    penalty = _int(terms, "dilution_penalty_bps")
    method = _text(work, "method")
    defaulting = _text(work, "defaulting_member_id")
    funding = _text(work, "funding_member_id")
    if penalty is None or method is None or defaulting is None or funding is None:
        return None
    def_row = _member_by_id(ctx, defaulting)
    fund_row = _member_by_id(ctx, funding)
    if def_row is None or fund_row is None:
        return None
    shortfall = require_cents("dilution_worksheet.shortfall_cents", work.get("shortfall_cents"))
    aggregate = sum(_total_contributions(m) for m in _members(ctx))
    defaulting_prior = _total_contributions(def_row)
    funding_prior = _total_contributions(fund_row)
    penalized = shortfall * penalty // 10000
    interest = dilution_interest(
        method, defaulting_prior, funding_prior, aggregate, shortfall, penalty
    )
    return {
        "substitute": shortfall,
        "penalized": penalized,
        "aggregate": aggregate,
        "defaulting_prior": defaulting_prior,
        "funding_prior": funding_prior,
        "diluted_interest_bps": interest,
    }


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the deal file depends on is present, exactly once.

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
                    rule, Status.FAIL, f"{doc_type}:-",
                    f"{doc_type} is missing; the controls that read it cannot run and "
                    f"must not be reported as having passed",
                )
            )
        elif len(found) > 1:
            out.append(
                Finding(
                    rule, Status.FAIL, f"{doc_type}:-",
                    f"{len(found)} {doc_type} documents present; the deal file carries "
                    f"exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(DOC_TYPES)} deal artifacts are present")
        )
    if ctx.as_of_period is None:
        out.append(
            Finding(
                rule, Status.FAIL, "-",
                f"as_of_period {ctx.data.get('as_of_period')!r} is not a readable month "
                f"index; every accrual and covenant window is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# mbr_ -- the member register
# --------------------------------------------------------------------------- #
@check("mbr_unique_ids")
def check_mbr_unique_ids(ctx: Context) -> list[Finding]:
    """No member id appears twice.

    The member id joins the register to every capital account, waterfall entry and
    return figure; a duplicate makes those attributions ambiguous.
    """
    rule = "mbr_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_MEMBER_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _members(ctx):
        seen[_member_id(row)] = seen.get(_member_id(row), 0) + 1
    out = [
        Finding(
            rule, Status.FAIL, ctx.loc(register, f"members/{mid}"),
            f"member id {mid} appears {count} times; its capital account and "
            f"distributions cannot be attributed to one member",
        )
        for mid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} member ids are unique"))
    return out


@check("mbr_role_valid")
def check_mbr_role_valid(ctx: Context) -> list[Finding]:
    """Every member carries a known role.

    The role is what tells the waterfall who takes the promote and who pays it; an
    unknown role has no place in the split.
    """
    rule = "mbr_role_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_MEMBER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _members(ctx):
        if _role(row) not in ROLES:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(register, f"members/{_member_id(row)}/role"),
                    f"member {_member_id(row)} carries role {_role(row)!r}, which is not "
                    f"one of {ROLES}; the waterfall cannot place it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_members(ctx))} members carry a known role")
        )
    return out


@check("mbr_roles_complete")
def check_mbr_roles_complete(ctx: Context) -> list[Finding]:
    """The venture has exactly one investor and exactly one developer.

    The Section 3.3 waterfall is written for a two-sided venture; a second
    investor or a missing developer means the promote has no well-defined split.
    """
    rule = "mbr_roles_complete"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_MEMBER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for role in (ROLE_INVESTOR, ROLE_DEVELOPER):
        count = sum(1 for m in _members(ctx) if _role(m) == role)
        if count != 1:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(register, f"members/role/{role}"),
                    f"the venture carries {count} member(s) with role {role!r}; the "
                    f"two-sided waterfall requires exactly one",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the venture has exactly one investor and one developer")
        )
    return out


@check("mbr_commitment_honored")
def check_mbr_commitment_honored(ctx: Context) -> list[Finding]:
    """No member funds more capital than it committed.

    The commitment is the ceiling the capital calls draw against; contributions
    beyond it are capital that was never committed and should never have funded.
    """
    rule = "mbr_commitment_honored"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_MEMBER_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _members(ctx):
        mid = _member_id(row)
        with amount_guard(rule, out):
            commitment = require_cents(
                f"member[{mid}].commitment_cents", row.get("commitment_cents")
            )
            funded = _total_contributions(row)
            checked += 1
            if commitment <= 0:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(register, f"members/{mid}/commitment_cents"),
                        f"member {mid} carries a non-positive commitment of {fmt(commitment)}",
                    )
                )
            elif funded > commitment:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(register, f"members/{mid}/commitment_cents"),
                        f"member {mid} funded {fmt(funded)} against a commitment of "
                        f"{fmt(commitment)} (over by {fmt(funded - commitment)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} members funded within their commitment")
        )
    return out


# --------------------------------------------------------------------------- #
# pref_ -- the preferred-return accrual
# --------------------------------------------------------------------------- #
@check("pref_rate_valid")
def check_pref_rate_valid(ctx: Context) -> list[Finding]:
    """The preferred-return rate is a positive basis-point figure.

    A zero or absent rate would accrue no preferred return at all, silently
    collapsing the first tier of the waterfall.
    """
    rule = "pref_rate_valid"
    _sev(rule, Status.FAIL)
    terms = _terms(ctx)
    if terms is None:
        return []
    rate = _int(terms, "pref_rate_bps")
    out: list[Finding] = []
    if rate is None or rate <= 0:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(terms, "pref_rate_bps"),
                f"preferred-return rate {terms.get('pref_rate_bps')!r} is not a positive "
                f"basis-point figure; the preferred tier would accrue nothing",
            )
        )
    else:
        out.append(
            Finding(rule, Status.PASS, "-", f"the preferred-return rate is {fmt_bps(rate)} per annum")
        )
    return out


@check("pref_accrual_recomputes")
def check_pref_accrual_recomputes(ctx: Context) -> list[Finding]:
    """Each member's stated preferred-return balance recomputes from its
    contributions.

    The Investment Return Account compounds monthly on unreturned capital; a
    stated balance that does not rebuild from the contribution history to the cent
    is a balance nobody can stand behind.
    """
    rule = "pref_accrual_recomputes"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_CAPITAL_LEDGER)
    accounts = recompute_accounts(ctx)
    if ledger is None or accounts is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rows(ledger, "accounts"):
        mid = _text(row, "member_id")
        acct = accounts.get(mid or "")
        if acct is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"capital_ledger[{mid}].investment_return_account_cents",
                row.get("investment_return_account_cents"),
            )
            checked += 1
            if stated != acct.investment_return_account_cents:
                out.append(
                    Finding(
                        rule, Status.FAIL,
                        ctx.loc(ledger, f"accounts/{mid}/investment_return_account_cents"),
                        f"member {mid} states a preferred-return balance of {fmt(stated)}; "
                        f"recomputing from its contributions gives "
                        f"{fmt(acct.investment_return_account_cents)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} preferred-return balances recompute")
        )
    return out


# --------------------------------------------------------------------------- #
# cap_ -- the capital-account roll-forward
# --------------------------------------------------------------------------- #
@check("cap_contribution_recomputes")
def check_cap_contribution_recomputes(ctx: Context) -> list[Finding]:
    """Each member's stated Contribution Account equals its funded capital.

    The Contribution Account is the running sum of what a member put in; if the
    ledger states a different figure the return of capital in tier B is measured
    against the wrong base.
    """
    rule = "cap_contribution_recomputes"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_CAPITAL_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rows(ledger, "accounts"):
        mid = _text(row, "member_id")
        member = _member_by_id(ctx, mid or "")
        if member is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"capital_ledger[{mid}].contribution_account_cents",
                row.get("contribution_account_cents"),
            )
            funded = _total_contributions(member)
            checked += 1
            if stated != funded:
                out.append(
                    Finding(
                        rule, Status.FAIL,
                        ctx.loc(ledger, f"accounts/{mid}/contribution_account_cents"),
                        f"member {mid} states a Contribution Account of {fmt(stated)}; its "
                        f"funded contributions sum to {fmt(funded)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} contribution accounts recompute")
        )
    return out


@check("cap_rollforward_zeroes")
def check_cap_rollforward_zeroes(ctx: Context) -> list[Finding]:
    """After the waterfall, each capital account rolls forward to zero.

    Tiers A and B exist to return the preferred return and the capital in full, so
    a member's ending Investment Return and Contribution accounts must land at zero
    once the waterfall has run. A non-zero ending balance is capital the schedule
    left unreturned while claiming a full distribution.
    """
    rule = "cap_rollforward_zeroes"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_CAPITAL_LEDGER)
    accounts = recompute_accounts(ctx)
    result = recompute_waterfall(ctx)
    if ledger is None or accounts is None or result is None:
        return []
    pref_paid: dict[str, int] = {}
    cap_paid: dict[str, int] = {}
    for tier, mid, amt in result.entries:
        if tier == TIER_PREF:
            pref_paid[mid] = pref_paid.get(mid, 0) + amt
        elif tier == TIER_CAPITAL:
            cap_paid[mid] = cap_paid.get(mid, 0) + amt
    out: list[Finding] = []
    checked = 0
    for row in _rows(ledger, "accounts"):
        mid = _text(row, "member_id")
        acct = accounts.get(mid or "")
        if acct is None:
            continue
        with amount_guard(rule, out):
            stated_ret = require_cents(
                f"capital_ledger[{mid}].ending_investment_return_account_cents",
                row.get("ending_investment_return_account_cents"),
            )
            stated_cap = require_cents(
                f"capital_ledger[{mid}].ending_contribution_account_cents",
                row.get("ending_contribution_account_cents"),
            )
            end_ret = acct.investment_return_account_cents - pref_paid.get(mid or "", 0)
            end_cap = acct.contribution_account_cents - cap_paid.get(mid or "", 0)
            checked += 1
            if stated_ret != end_ret or stated_cap != end_cap:
                out.append(
                    Finding(
                        rule, Status.FAIL,
                        ctx.loc(ledger, f"accounts/{mid}/ending_contribution_account_cents"),
                        f"member {mid} states ending accounts of {fmt(stated_cap)} capital / "
                        f"{fmt(stated_ret)} preferred; the roll-forward gives "
                        f"{fmt(end_cap)} / {fmt(end_ret)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} capital accounts roll forward to zero")
        )
    return out


# --------------------------------------------------------------------------- #
# wf_ -- the waterfall tiers
# --------------------------------------------------------------------------- #
def _schedule_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_WATERFALL_SCHEDULE), "entries")


@check("wf_tier_order_valid")
def check_wf_tier_order_valid(ctx: Context) -> list[Finding]:
    """The schedule's tiers appear in the contractual order.

    Section 3.3 fixes the order -- preferred, capital, hurdle, promote -- and a
    tier that pays out of turn is a tier paid before the one above it was
    satisfied.
    """
    rule = "wf_tier_order_valid"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    last_index = -1
    for i, row in enumerate(_schedule_entries(ctx)):
        tier = _text(row, "tier")
        if tier not in TIER_ORDER:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, f"entries/{i}/tier"),
                    f"schedule entry {i} names tier {tier!r}, which is not one of the "
                    f"contractual tiers {TIER_ORDER}",
                )
            )
            continue
        idx = TIER_ORDER.index(tier)
        if idx < last_index:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, f"entries/{i}/tier"),
                    f"tier {tier!r} pays at entry {i} after a later tier has already "
                    f"begun; the waterfall order is broken",
                )
            )
        last_index = max(last_index, idx)
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the schedule tiers pay in contractual order")
        )
    return out


@check("wf_pari_passu_split")
def check_wf_pari_passu_split(ctx: Context) -> list[Finding]:
    """Tiers A and B split pari passu on the members' account balances.

    The preferred return and the return of capital are shared in proportion to
    each member's preferred and contribution balances; a split struck off any
    other weights favours one member over the other before the promote even
    begins.
    """
    rule = "wf_pari_passu_split"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    accounts = recompute_accounts(ctx)
    inv = _investor_id(ctx)
    dev = _developer_id(ctx)
    if schedule is None or accounts is None or inv is None or dev is None:
        return []
    if inv not in accounts or dev not in accounts:
        return []
    weights = {
        TIER_PREF: [
            accounts[inv].investment_return_account_cents,
            accounts[dev].investment_return_account_cents,
        ],
        TIER_CAPITAL: [
            accounts[inv].contribution_account_cents,
            accounts[dev].contribution_account_cents,
        ],
    }
    out: list[Finding] = []
    checked = 0
    for tier in (TIER_PREF, TIER_CAPITAL):
        stated = {inv: 0, dev: 0}
        with amount_guard(rule, out):
            for row in _schedule_entries(ctx):
                if _text(row, "tier") != tier:
                    continue
                mid = _text(row, "member_id")
                if mid not in stated:
                    continue
                stated[mid] += require_cents(
                    f"waterfall_schedule[{tier}/{mid}].amount_cents", row.get("amount_cents")
                )
            tier_total = stated[inv] + stated[dev]
            expected = split_pro_rata(tier_total, weights[tier])
            checked += 1
            if [stated[inv], stated[dev]] != expected:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(schedule, f"entries/tier/{tier}"),
                        f"tier {tier} splits {fmt(stated[inv])} / {fmt(stated[dev])} to "
                        f"investor / developer; a pari-passu split of {fmt(tier_total)} on the "
                        f"account balances is {fmt(expected[0])} / {fmt(expected[1])}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} pari-passu tiers split on the balances")
        )
    return out


def _normalize_entries(entries: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    return sorted(entries)


@check("wf_tier_allocation_recomputes")
def check_wf_tier_allocation_recomputes(ctx: Context) -> list[Finding]:
    """Every tier/member allocation recomputes from the base facts.

    This is the control the engine exists for. The whole distribution -- who is
    paid, in which tier, how much -- is rebuilt from the contributions, the
    accruals, the hurdle and the splits, and compared entry by entry.
    """
    rule = "wf_tier_allocation_recomputes"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    result = recompute_waterfall(ctx)
    if schedule is None or result is None:
        return []
    out: list[Finding] = []
    stated: list[tuple[str, str, int]] = []
    with amount_guard(rule, out):
        for row in _schedule_entries(ctx):
            tier = _text(row, "tier") or "?"
            mid = _text(row, "member_id") or "?"
            amt = require_cents(
                f"waterfall_schedule[{tier}/{mid}].amount_cents", row.get("amount_cents")
            )
            stated.append((tier, mid, amt))
        want = _normalize_entries(list(result.entries))
        have = _normalize_entries(stated)
        if want != have:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, "entries"),
                    f"the stated waterfall allocations do not recompute from the base "
                    f"facts: stated {have}, recomputed {want}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(result.entries)} tier allocations recompute")
        )
    return out


# --------------------------------------------------------------------------- #
# hurdle_ -- the hurdle boundary
# --------------------------------------------------------------------------- #
@check("hurdle_rate_valid")
def check_hurdle_rate_valid(ctx: Context) -> list[Finding]:
    """The hurdle rate sits above the preferred rate.

    The hurdle is the investor's target return before the developer's promote
    steps up; a hurdle at or below the preferred rate would be cleared the moment
    the preferred tier was paid, collapsing the promote structure.
    """
    rule = "hurdle_rate_valid"
    _sev(rule, Status.FAIL)
    terms = _terms(ctx)
    if terms is None:
        return []
    pref = _int(terms, "pref_rate_bps")
    hurdle = _int(terms, "hurdle_rate_bps")
    out: list[Finding] = []
    if hurdle is None or pref is None or hurdle <= pref or hurdle <= 0:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(terms, "hurdle_rate_bps"),
                f"hurdle rate {terms.get('hurdle_rate_bps')!r} does not sit above the "
                f"preferred rate {terms.get('pref_rate_bps')!r}; the promote boundary is "
                f"ill-defined",
            )
        )
    else:
        out.append(
            Finding(rule, Status.PASS, "-", f"the hurdle rate {fmt_bps(hurdle)} sits above the preferred")
        )
    return out


@check("hurdle_boundary_recomputes")
def check_hurdle_boundary_recomputes(ctx: Context) -> list[Finding]:
    """The stated hurdle target recomputes from the investor's contributions.

    The boundary between the hurdle split and the promote split is the point where
    the investor's cumulative receipts reach its contributions grown at the hurdle
    rate. A stated target that does not rebuild from the contributions moves that
    boundary and the promote with it.
    """
    rule = "hurdle_boundary_recomputes"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    target = recompute_hurdle_target(ctx)
    if schedule is None or target is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "waterfall_schedule.hurdle_target_cents", schedule.get("hurdle_target_cents")
        )
        if stated != target:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, "hurdle_target_cents"),
                    f"the schedule states a hurdle target of {fmt(stated)}; recomputing "
                    f"from the investor's contributions gives {fmt(target)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the hurdle target recomputes from the contributions")
        )
    return out


# --------------------------------------------------------------------------- #
# promo_ -- the promote split
# --------------------------------------------------------------------------- #
@check("promo_split_ratios_valid")
def check_promo_split_ratios_valid(ctx: Context) -> list[Finding]:
    """Each upper-tier split allocates exactly 100% of the tier.

    The hurdle and promote tiers each divide their pool between investor and
    developer; a split whose shares do not sum to 10,000 basis points either
    creates or destroys a fraction of every dollar that passes through it.
    """
    rule = "promo_split_ratios_valid"
    _sev(rule, Status.FAIL)
    terms = _terms(ctx)
    if terms is None:
        return []
    out: list[Finding] = []
    for label, inv_key, dev_key in (
        ("hurdle", "tier_c_investor_bps", "tier_c_developer_bps"),
        ("promote", "tier_d_investor_bps", "tier_d_developer_bps"),
    ):
        inv = _int(terms, inv_key)
        dev = _int(terms, dev_key)
        if inv is None or dev is None or inv + dev != 10000:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(terms, inv_key),
                    f"the {label} split {terms.get(inv_key)!r} / {terms.get(dev_key)!r} does "
                    f"not sum to 10,000 basis points",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the hurdle and promote splits each allocate 100%")
        )
    return out


@check("promo_carry_recomputes")
def check_promo_carry_recomputes(ctx: Context) -> list[Finding]:
    """The stated developer promote equals its upper-tier receipts.

    The promote (carried interest) is what the developer takes in the hurdle and
    promote tiers above its capital share; the schedule's stated promote figure
    must equal the developer's receipts in those tiers, summed from the entries.
    """
    rule = "promo_carry_recomputes"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    dev = _developer_id(ctx)
    if schedule is None or dev is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        carry = 0
        for row in _schedule_entries(ctx):
            if _text(row, "member_id") != dev:
                continue
            if _text(row, "tier") in (TIER_ORDER[2], TIER_ORDER[3]):
                carry += require_cents(
                    f"waterfall_schedule[{dev}].amount_cents", row.get("amount_cents")
                )
        stated = require_cents(
            "waterfall_schedule.promote_split_cents", schedule.get("promote_split_cents")
        )
        if stated != carry:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, "promote_split_cents"),
                    f"the schedule states a developer promote of {fmt(stated)}; its receipts "
                    f"in the hurdle and promote tiers sum to {fmt(carry)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the developer promote ties its upper-tier receipts")
        )
    return out


# --------------------------------------------------------------------------- #
# loan_ -- member and default loans
# --------------------------------------------------------------------------- #
@check("loan_rate_valid")
def check_loan_rate_valid(ctx: Context) -> list[Finding]:
    """The default-loan rate sits above the member-loan rate, both positive.

    A member loan carries a rate; a default (deficit) loan carries a higher one,
    because failing to fund is meant to cost more than lending. A default rate at
    or below the member rate inverts that incentive.
    """
    rule = "loan_rate_valid"
    _sev(rule, Status.FAIL)
    terms = _terms(ctx)
    if terms is None:
        return []
    member = _int(terms, "member_loan_rate_bps")
    default = _int(terms, "default_loan_rate_bps")
    out: list[Finding] = []
    if member is None or default is None or member <= 0 or default <= member:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(terms, "default_loan_rate_bps"),
                f"default-loan rate {terms.get('default_loan_rate_bps')!r} does not sit "
                f"above the member-loan rate {terms.get('member_loan_rate_bps')!r}",
            )
        )
    else:
        out.append(
            Finding(
                rule, Status.PASS, "-",
                f"member loan {fmt_bps(member)} < default loan {fmt_bps(default)}",
            )
        )
    return out


@check("loan_repaid_before_distribution")
def check_loan_repaid_before_distribution(ctx: Context) -> list[Finding]:
    """The member loan is repaid in full before any member distribution.

    Member-loan interest compounds monthly and the loan -- interest first, then
    principal -- is repaid off the top, before the waterfall runs. The stated
    repayment must equal the re-derived principal-plus-interest, and the proceeds
    the waterfall distributes must be the gross proceeds net of it.
    """
    rule = "loan_repaid_before_distribution"
    _sev(rule, Status.FAIL)
    terms = _terms(ctx)
    loan_doc = ctx.one(DOC_LOAN_COVENANT)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    loan = recompute_loan(ctx)
    if terms is None or loan_doc is None or schedule is None or loan is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_repay = require_cents(
            "loan_covenant.member_loan_repayment_cents",
            loan_doc.get("member_loan_repayment_cents"),
        )
        proceeds = require_cents("deal_terms.proceeds_cents", terms.get("proceeds_cents"))
        after = require_cents(
            "waterfall_schedule.proceeds_after_loans_cents",
            schedule.get("proceeds_after_loans_cents"),
        )
        if stated_repay != loan["repayment"]:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(loan_doc, "member_loan_repayment_cents"),
                    f"the stated member-loan repayment {fmt(stated_repay)} does not equal the "
                    f"re-derived principal plus interest {fmt(loan['repayment'])}",
                )
            )
        elif after != proceeds - stated_repay:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, "proceeds_after_loans_cents"),
                    f"proceeds after loans {fmt(after)} do not equal gross proceeds "
                    f"{fmt(proceeds)} net of the {fmt(stated_repay)} loan repayment",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the member loan is repaid in full before distribution")
        )
    return out


# --------------------------------------------------------------------------- #
# dil_ -- capital-call dilution
# --------------------------------------------------------------------------- #
@check("dil_method_valid")
def check_dil_method_valid(ctx: Context) -> list[Finding]:
    """The dilution worksheet names a known recompute method."""
    rule = "dil_method_valid"
    _sev(rule, Status.FAIL)
    work = ctx.one(DOC_DILUTION_WORKSHEET)
    if work is None:
        return []
    out: list[Finding] = []
    method = _text(work, "method")
    if method not in DILUTION_METHODS:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(work, "method"),
                f"the dilution worksheet names method {method!r}, which is not one of the "
                f"maintained variants {DILUTION_METHODS}",
            )
        )
    else:
        out.append(Finding(rule, Status.PASS, "-", f"the dilution method {method!r} is known"))
    return out


@check("dil_penalty_multiplier")
def check_dil_penalty_multiplier(ctx: Context) -> list[Finding]:
    """The dilution penalty is the statutory 200% multiplier.

    Failing to fund a capital call dilutes the defaulting member as though it had
    contributed only half of the substitute the other member funded; that 2x
    penalty is a fixed term, not a free parameter.
    """
    rule = "dil_penalty_multiplier"
    _sev(rule, Status.FAIL)
    terms = _terms(ctx)
    if terms is None:
        return []
    out: list[Finding] = []
    penalty = _int(terms, "dilution_penalty_bps")
    if penalty != DILUTION_PENALTY_BPS:
        out.append(
            Finding(
                rule, Status.FAIL, ctx.loc(terms, "dilution_penalty_bps"),
                f"the dilution penalty {terms.get('dilution_penalty_bps')!r} is not the "
                f"statutory {DILUTION_PENALTY_BPS} basis points (200%)",
            )
        )
    else:
        out.append(Finding(rule, Status.PASS, "-", "the dilution penalty is the statutory 200%"))
    return out


@check("dil_recompute")
def check_dil_recompute(ctx: Context) -> list[Finding]:
    """The stated diluted interest recomputes by the worksheet's own method.

    The penalized substitute and the resulting diluted interest are both rebuilt
    from the default event's inputs, through the named formula variant, and
    compared.
    """
    rule = "dil_recompute"
    _sev(rule, Status.FAIL)
    work = ctx.one(DOC_DILUTION_WORKSHEET)
    dil = recompute_dilution(ctx)
    if work is None or dil is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_penalized = require_cents(
            "dilution_worksheet.penalized_substitute_cents",
            work.get("penalized_substitute_cents"),
        )
        stated_interest = _int(work, "diluted_interest_bps")
        if stated_penalized != dil["penalized"]:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(work, "penalized_substitute_cents"),
                    f"the stated penalized substitute {fmt(stated_penalized)} does not equal "
                    f"the re-derived {fmt(dil['penalized'])}",
                )
            )
        elif stated_interest != dil["diluted_interest_bps"]:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(work, "diluted_interest_bps"),
                    f"the stated diluted interest {stated_interest} bps does not recompute to "
                    f"{dil['diluted_interest_bps']} bps by the {_text(work, 'method')!r} method",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "the dilution recompute ties by its own method"))
    return out


# --------------------------------------------------------------------------- #
# dist_ -- distribution completeness / no leakage
# --------------------------------------------------------------------------- #
@check("dist_no_leakage")
def check_dist_no_leakage(ctx: Context) -> list[Finding]:
    """Every distributed cent is accounted for, with no leakage.

    The sum of the schedule's entries must equal its stated total distributed,
    which must equal the proceeds left after the loans. A residual either way is a
    cent created or lost between the pool and the members.
    """
    rule = "dist_no_leakage"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        entry_sum = 0
        for row in _schedule_entries(ctx):
            entry_sum += require_cents(
                "waterfall_schedule.entry.amount_cents", row.get("amount_cents")
            )
        total = require_cents(
            "waterfall_schedule.total_distributed_cents", schedule.get("total_distributed_cents")
        )
        after = require_cents(
            "waterfall_schedule.proceeds_after_loans_cents",
            schedule.get("proceeds_after_loans_cents"),
        )
        if entry_sum != total:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, "total_distributed_cents"),
                    f"the schedule entries sum to {fmt(entry_sum)} but state a total distributed "
                    f"of {fmt(total)} (leak {fmt(total - entry_sum)})",
                )
            )
        elif total != after:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, "total_distributed_cents"),
                    f"the total distributed {fmt(total)} does not equal the {fmt(after)} of "
                    f"proceeds available after loans",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every distributed cent ties out with no leakage"))
    return out


@check("dist_within_available")
def check_dist_within_available(ctx: Context) -> list[Finding]:
    """The total distributed never exceeds the proceeds available.

    A distribution larger than the pool it draws from is money the venture never
    had; the waterfall can only ever pay out what the sale, net of the loans,
    brought in.
    """
    rule = "dist_within_available"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_WATERFALL_SCHEDULE)
    if schedule is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = require_cents(
            "waterfall_schedule.total_distributed_cents", schedule.get("total_distributed_cents")
        )
        after = require_cents(
            "waterfall_schedule.proceeds_after_loans_cents",
            schedule.get("proceeds_after_loans_cents"),
        )
        if total > after:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(schedule, "total_distributed_cents"),
                    f"the total distributed {fmt(total)} exceeds the {fmt(after)} of proceeds "
                    f"available after loans (over by {fmt(total - after)})",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the total distributed is within the proceeds available")
        )
    return out


# --------------------------------------------------------------------------- #
# ret_ -- realized-returns tie-out
# --------------------------------------------------------------------------- #
def _returns_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_RETURNS_SUMMARY), "members")


@check("ret_multiple_recomputes")
def check_ret_multiple_recomputes(ctx: Context) -> list[Finding]:
    """Each member's stated equity multiple recomputes from the waterfall.

    The equity multiple is total distributions over total contributions; a stated
    multiple that does not rebuild from the recomputed distribution is a headline
    return figure nobody derived.
    """
    rule = "ret_multiple_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RETURNS_SUMMARY)
    accounts = recompute_accounts(ctx)
    result = recompute_waterfall(ctx)
    if summary is None or accounts is None or result is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _returns_rows(ctx):
        mid = _text(row, "member_id")
        acct = accounts.get(mid or "")
        if acct is None or mid not in result.per_member:
            continue
        with amount_guard(rule, out):
            stated = _int(row, "equity_multiple_bps")
            expected = equity_multiple_bps(
                result.per_member[mid], acct.contribution_account_cents
            )
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(summary, f"members/{mid}/equity_multiple_bps"),
                        f"member {mid} states an equity multiple of {fmt_bps(stated or 0)}; "
                        f"recomputing from the waterfall gives {fmt_bps(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} equity multiples recompute")
        )
    return out


@check("ret_preferred_ties")
def check_ret_preferred_ties(ctx: Context) -> list[Finding]:
    """Each member's stated preferred return ties its tier-A receipts."""
    rule = "ret_preferred_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RETURNS_SUMMARY)
    result = recompute_waterfall(ctx)
    if summary is None or result is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _returns_rows(ctx):
        mid = _text(row, "member_id")
        if mid not in result.preferred:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"returns_summary[{mid}].preferred_return_cents", row.get("preferred_return_cents")
            )
            expected = result.preferred[mid]
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(summary, f"members/{mid}/preferred_return_cents"),
                        f"member {mid} states a preferred return of {fmt(stated)}; its tier-A "
                        f"receipts recompute to {fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} preferred returns tie the waterfall")
        )
    return out


@check("ret_profit_split_ties")
def check_ret_profit_split_ties(ctx: Context) -> list[Finding]:
    """Each member's stated profit split ties its promote receipts.

    The profit split is what a member takes in the upper (hurdle and promote)
    tiers; the reported figure must equal the recomputed promote to the cent, so a
    developer's carry cannot be overstated on the face of the returns table.
    """
    rule = "ret_profit_split_ties"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_RETURNS_SUMMARY)
    result = recompute_waterfall(ctx)
    if summary is None or result is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _returns_rows(ctx):
        mid = _text(row, "member_id")
        if mid not in result.promote:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"returns_summary[{mid}].profit_split_cents", row.get("profit_split_cents")
            )
            expected = result.promote[mid]
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(summary, f"members/{mid}/profit_split_cents"),
                        f"member {mid} states a profit split of {fmt(stated)}; its promote "
                        f"receipts recompute to {fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} profit splits tie the waterfall")
        )
    return out


# --------------------------------------------------------------------------- #
# cov_ -- financing covenants (secondary)
# --------------------------------------------------------------------------- #
@check("cov_maturity_window")
def check_cov_maturity_window(ctx: Context) -> list[Finding]:
    """A financing maturing inside the warning window is flagged.

    Deliberately a FLAG, not a failure: the loan is still current, but a maturity
    inside the lead window needs a refinance or extension chased before it falls
    due. The window comes from the file's own ``maturity_lead_periods``.
    """
    rule = "cov_maturity_window"
    _sev(rule, Status.FLAG)
    loan = ctx.one(DOC_LOAN_COVENANT)
    as_of = ctx.as_of_period
    if loan is None or as_of is None:
        return []
    maturity = _int(loan, "maturity_period")
    if maturity is None:
        return []
    lead = ctx.maturity_lead_periods
    remaining = maturity - as_of
    out: list[Finding] = []
    if 0 < remaining <= lead:
        out.append(
            Finding(
                rule, Status.FLAG, ctx.loc(loan, "maturity_period"),
                f"the financing matures in {remaining} month(s), inside the {lead}-month "
                f"window; a refinance or extension is due to be chased",
            )
        )
    else:
        out.append(
            Finding(rule, Status.PASS, "-", "the financing matures outside the warning window")
        )
    return out


@check("cov_ltc_within_max")
def check_cov_ltc_within_max(ctx: Context) -> list[Finding]:
    """The loan-to-cost ratio does not exceed the covenant maximum.

    The senior financing is capped at a fraction of total project cost; a
    re-derived LTC above the covenant maximum is a draw larger than the loan
    documents allow.
    """
    rule = "cov_ltc_within_max"
    _sev(rule, Status.FAIL)
    loan = ctx.one(DOC_LOAN_COVENANT)
    if loan is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        senior = require_cents("loan_covenant.senior_loan_cents", loan.get("senior_loan_cents"))
        cost = require_cents("loan_covenant.total_cost_cents", loan.get("total_cost_cents"))
        max_ltc = _int(loan, "max_ltc_bps")
        if cost <= 0 or max_ltc is None:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(loan, "total_cost_cents"),
                    f"total project cost {loan.get('total_cost_cents')!r} or LTC cap "
                    f"{loan.get('max_ltc_bps')!r} is not usable for the ratio",
                )
            )
        else:
            ltc = senior * 10000 // cost
            if ltc > max_ltc:
                out.append(
                    Finding(
                        rule, Status.FAIL, ctx.loc(loan, "senior_loan_cents"),
                        f"loan-to-cost {fmt_bps(ltc)} ({fmt(senior)} of {fmt(cost)}) exceeds the "
                        f"covenant maximum {fmt_bps(max_ltc)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "loan-to-cost is within the covenant maximum"))
    return out


# --------------------------------------------------------------------------- #
# syn_ -- the syndicate (secondary)
# --------------------------------------------------------------------------- #
@check("syn_capital_call_ratio")
def check_syn_capital_call_ratio(ctx: Context) -> list[Finding]:
    """The syndicate draw is the fixed ratio of the commitment.

    A fund-of-projects syndicate calls capital at a fixed 33.5% of each investor's
    commitment; the stated draw must equal that ratio applied to the commitment.
    """
    rule = "syn_capital_call_ratio"
    _sev(rule, Status.FAIL)
    loan = ctx.one(DOC_LOAN_COVENANT)
    draw = recompute_syndicate_draw(ctx)
    if loan is None or draw is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents("loan_covenant.syndicate_draw_cents", loan.get("syndicate_draw_cents"))
        if stated != draw:
            out.append(
                Finding(
                    rule, Status.FAIL, ctx.loc(loan, "syndicate_draw_cents"),
                    f"the stated syndicate draw {fmt(stated)} does not equal {SYNDICATE_CALL_BPS} "
                    f"basis points of the commitment, {fmt(draw)}",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "the syndicate draw is the fixed 33.5% of commitment"))
    return out


@check("syn_report_due")
def check_syn_report_due(ctx: Context) -> list[Finding]:
    """A syndicate report due inside the lead window is flagged.

    A FLAG rather than a failure: the quarterly investor report is not yet late,
    but a due date inside the lead window is an operational to-do to prepare it.
    """
    rule = "syn_report_due"
    _sev(rule, Status.FLAG)
    loan = ctx.one(DOC_LOAN_COVENANT)
    as_of = ctx.as_of_period
    if loan is None or as_of is None:
        return []
    due = _int(loan, "report_due_period")
    if due is None:
        return []
    lead = ctx.report_lead_periods
    remaining = due - as_of
    out: list[Finding] = []
    if 0 < remaining <= lead:
        out.append(
            Finding(
                rule, Status.FLAG, ctx.loc(loan, "report_due_period"),
                f"the syndicate report is due in {remaining} month(s), inside the {lead}-month "
                f"window; it is due to be prepared",
            )
        )
    else:
        out.append(
            Finding(rule, Status.PASS, "-", "the syndicate report is outside the lead window")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one deal file."""
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
    """Analyze every ``.json`` deal file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of deal-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
