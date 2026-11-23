"""
Combined-group franchise (margin) tax control engine (READ-ONLY).
=================================================================

Loads each combined-return file (a ``.json`` file produced by
:mod:`franchise_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the tax on the combined return is the tax the
workpapers produce**. It rebuilds the combined-group roster from the prior year
and this year's changes, ties consolidated group revenue to the consolidated tax
trial-balance workpaper, recomputes the single receipts apportionment factor,
and re-derives the whole margin tax -- margin, apportioned margin, tax -- from
those workpapers, tying the recomputed figure to the number the return filed.
Where a cost lands on a project is a different engine's job; this one audits the
combined franchise return.

The shape of the problem
------------------------
A group of affiliated development companies files one combined franchise-tax
return each fiscal year in the fictional State of Marran. The roster is rebuilt
each year, the group margin is apportioned by a single receipts factor, and the
tax is a derived figure. It goes wrong in ways that look right: an affiliate that
quietly falls off the roster, a member with no registration, a base that does not
tie the trial balance, a factor struck against the wrong denominator, a margin or
tax that does not re-derive.

The registry is organised around that:

1. ``set_`` -- is the combined-return file complete?
2. ``aff_`` -- is the affiliate register sound, addressed and registered?
3. ``grp_`` -- does the combined roster rebuild, and are its members and exclusions reconciled?
4. ``tb_``  -- is the consolidated trial-balance workpaper sound and attributable?
5. ``apt_`` -- do the receipts tie, and does the apportionment factor recompute?
6. ``mgn_`` -- does group revenue tie the trial balance, and does the margin tax re-derive?
7. ``rpt_`` -- does the rollup recompute from the workpapers it summarises?

Design notes
------------
- **Strictly read-only.** Combined-return files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tax is compared with exact ``==``.
- **One margin computation.** Controls and the generator share the kernel in
  :mod:`franchise_engine.franchise`, so a re-derived tax cannot disagree with the
  data that produced it.
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

from .franchise import (
    apportioned_margin,
    apportionment_factor_bps,
    combined_members,
    margin_tax,
    taxable_margin,
)
from .model import (
    AFFILIATE_STATUSES,
    DOC_AFFILIATE_REGISTER,
    DOC_COMBINED_GROUP,
    DOC_FRANCHISE_REPORT,
    DOC_MARGIN_WORKSHEET,
    DOC_RECEIPTS_FACTOR,
    DOC_TAX_SUMMARY,
    DOC_TRIAL_BALANCE,
    DOC_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import BPS_FULL, AmountInvalidError, fmt, fmt_bps, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~franchise_engine.money.AmountInvalidError` as a finding."""
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


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


# --------------------------------------------------------------------------- #
# Combined-return-file accessors
# --------------------------------------------------------------------------- #
def _affiliates(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_AFFILIATE_REGISTER), "affiliates")


def _affiliate_id(row: dict[str, Any]) -> str:
    value = row.get("affiliate_id")
    return value if isinstance(value, str) and value else "?"


def _affiliate_ids(ctx: Context) -> set[str]:
    return {_affiliate_id(row) for row in _affiliates(ctx) if _affiliate_id(row) != "?"}


def _group(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_COMBINED_GROUP)


def _members(ctx: Context) -> list[str]:
    """The current-year combined-group member ids as stated on the roster."""
    group = _group(ctx)
    if group is None:
        return []
    return _str_list(group.get("members"))


def _member_set(ctx: Context) -> set[str]:
    return set(_members(ctx))


def _tb_lines(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TRIAL_BALANCE), "lines")


def _tb_line_id(row: dict[str, Any]) -> str:
    value = row.get("tb_line_id")
    return value if isinstance(value, str) and value else "?"


def _receipts_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_RECEIPTS_FACTOR), "receipts")


def _worksheet(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_MARGIN_WORKSHEET)


# --------------------------------------------------------------------------- #
# Shared re-derivation
# --------------------------------------------------------------------------- #
def stated_receipts_factor_bps(ctx: Context) -> int:
    """The apportionment factor recomputed from the receipts workpaper's totals.

    Reads the *stated* in-state and everywhere totals on the receipts workpaper
    and applies the shared :mod:`franchise_engine.franchise` kernel, so the
    worksheet's factor and the receipts factor are both measured against the same
    denominator. Raises :class:`AmountInvalidError` if either total is not integer
    cents.
    """
    doc = ctx.one(DOC_RECEIPTS_FACTOR)
    if doc is None:
        return 0
    in_state = require_cents(
        "receipts_factor.in_state_total_cents", doc.get("in_state_total_cents")
    )
    everywhere = require_cents(
        "receipts_factor.everywhere_total_cents", doc.get("everywhere_total_cents")
    )
    return apportionment_factor_bps(in_state, everywhere)


def recompute_group_tax(ctx: Context) -> int | None:
    """Recompute the combined tax end to end from the workpapers' base facts.

    Group revenue is summed from the consolidated trial-balance lines; the elected
    deduction and margin-tax rate are read from the margin worksheet; the
    apportionment factor is recomputed from the receipts rows -- the base facts,
    not the stated totals -- and the whole tax is taken as margin times
    apportionment times rate through the shared kernel the generator derived the
    data with. Returns ``None`` when the rate is unreadable, and raises
    :class:`AmountInvalidError` if a money field it must read is not integer
    cents.
    """
    worksheet = _worksheet(ctx)
    if worksheet is None:
        return None
    revenue = 0
    for line in _tb_lines(ctx):
        revenue += require_cents(
            f"trial_balance[{_tb_line_id(line)}].revenue_cents",
            line.get("revenue_cents"),
        )
    deduction = require_cents(
        "margin_worksheet.elected_deduction_cents",
        worksheet.get("elected_deduction_cents"),
    )
    rate = _int(worksheet, "rate_bps")
    if rate is None:
        return None
    in_state = 0
    everywhere = 0
    for row in _receipts_rows(ctx):
        in_state += require_cents(
            f"receipts[{_affiliate_id(row)}].in_state_receipts_cents",
            row.get("in_state_receipts_cents"),
        )
        everywhere += require_cents(
            f"receipts[{_affiliate_id(row)}].everywhere_receipts_cents",
            row.get("everywhere_receipts_cents"),
        )
    factor = apportionment_factor_bps(in_state, everywhere)
    margin = taxable_margin(revenue, deduction)
    return margin_tax(apportioned_margin(margin, factor), rate)


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the combined-return file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the combined-return file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(DOC_TYPES)} artifacts are present")
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every registration-renewal "
                f"test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# aff_ -- the affiliate register / address tab
# --------------------------------------------------------------------------- #
@check("aff_unique_ids")
def check_aff_unique_ids(ctx: Context) -> list[Finding]:
    """No affiliate id appears twice.

    The affiliate id joins the register to the roster, the trial balance and the
    receipts workpaper. A duplicate makes a revenue line ambiguous about which
    affiliate earned it.
    """
    rule = "aff_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_AFFILIATE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _affiliates(ctx):
        seen[_affiliate_id(row)] = seen.get(_affiliate_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"affiliates/{aid}"),
            f"affiliate id {aid} appears {count} times; a revenue line that names it "
            f"cannot be attributed to one affiliate",
        )
        for aid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} affiliate ids are unique")
        )
    return out


@check("aff_address_valid")
def check_aff_address_valid(ctx: Context) -> list[Finding]:
    """Every affiliate carries a complete address and a state registration.

    The address tab is the return's proof that each affiliate is a real, addressed,
    registered taxpayer in the group. A member with a blank address line or no
    registration id is an affiliate the state cannot place, and the combined return
    rests on it being placeable.
    """
    rule = "aff_address_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_AFFILIATE_REGISTER)
    if register is None:
        return []
    required = ("street", "city", "state", "postal_code", "registration_id")
    out: list[Finding] = []
    for row in _affiliates(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"affiliates/{_affiliate_id(row)}"),
                    f"affiliate {_affiliate_id(row)} is missing {', '.join(missing)} on the "
                    f"address tab; it cannot be placed or registered",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_affiliates(ctx))} affiliates carry a complete address and registration",
            )
        )
    return out


@check("aff_status_valid")
def check_aff_status_valid(ctx: Context) -> list[Finding]:
    """Every affiliate carries a known registration status.

    The status is either active or inactive; an unknown status is a registration
    whose standing the return cannot assert, and standing is what a combined member
    is admitted on.
    """
    rule = "aff_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_AFFILIATE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _affiliates(ctx):
        status = _text(row, "status")
        if status not in AFFILIATE_STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"affiliates/{_affiliate_id(row)}/status"),
                    f"affiliate {_affiliate_id(row)} carries status {status!r}, which is not "
                    f"one of {AFFILIATE_STATUSES}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_affiliates(ctx))} affiliates carry a known status"
            )
        )
    return out


@check("aff_registration_renewal")
def check_aff_registration_renewal(ctx: Context) -> list[Finding]:
    """An affiliate registration renewing inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the registration is still current, but its
    renewal is due and needs to be lodged before it lapses. The window comes from
    the file's own ``lead_days`` and is measured to the ``as_of`` date.
    """
    rule = "aff_registration_renewal"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_AFFILIATE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    lead = ctx.lead_days
    out: list[Finding] = []
    checked = 0
    for row in _affiliates(ctx):
        renewal = _parse_date(row.get("registration_renewal_date"))
        if renewal is None:
            continue
        checked += 1
        remaining = (renewal - as_of).days
        if 0 < remaining <= lead:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"affiliates/{_affiliate_id(row)}/registration_renewal_date"),
                    f"affiliate {_affiliate_id(row)} registration renews {renewal.isoformat()}, "
                    f"in {remaining} day(s); inside the {lead}-day window and due to be renewed",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} affiliate registrations are outside the renewal window",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# grp_ -- the combined-group roster
# --------------------------------------------------------------------------- #
@check("grp_roster_continuity")
def check_grp_roster_continuity(ctx: Context) -> list[Finding]:
    """The combined roster equals the prior year plus additions, less removals.

    This is the roster-continuity control. The combined group is rebuilt each year,
    and the stated member list must be exactly last year's members plus the
    affiliates that joined minus the ones that left. A member list that does not
    rebuild is a roster someone edited outside the prior-plus-changes discipline,
    and an affiliate can vanish from -- or slip into -- the combined base unnoticed.
    """
    rule = "grp_roster_continuity"
    _sev(rule, Status.FAIL)
    group = _group(ctx)
    if group is None:
        return []
    prior = _str_list(group.get("prior_year_members"))
    additions = _str_list(group.get("additions"))
    removals = _str_list(group.get("removals"))
    expected = combined_members(prior, additions, removals)
    stated = sorted(_str_list(group.get("members")))
    out: list[Finding] = []
    if stated != expected:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(group, "members"),
                f"the combined roster states members {stated}; rebuilding from prior "
                f"{sorted(prior)} plus additions {sorted(additions)} less removals "
                f"{sorted(removals)} gives {expected}",
            )
        )
    else:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the combined roster of {len(stated)} member(s) rebuilds from the prior year",
            )
        )
    return out


@check("grp_members_registered")
def check_grp_members_registered(ctx: Context) -> list[Finding]:
    """Every combined-group member is an affiliate in the register.

    A member the group taxes on but that has no entry on the affiliate register is
    a taxpayer with no address and no registration -- a member the state cannot
    place. Membership is admitted on registration.
    """
    rule = "grp_members_registered"
    _sev(rule, Status.FAIL)
    group = _group(ctx)
    register = ctx.one(DOC_AFFILIATE_REGISTER)
    if group is None or register is None:
        return []
    known = _affiliate_ids(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"affiliates/{member}"),
            f"combined member {member} is not on the affiliate register; it has no "
            f"address or registration to be admitted on",
        )
        for member in _members(ctx)
        if member not in known
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_members(ctx))} combined members are registered affiliates"
            )
        )
    return out


@check("grp_excluded_reconciled")
def check_grp_excluded_reconciled(ctx: Context) -> list[Finding]:
    """Every affiliate removed this year is enumerated and reconciled as excluded.

    An affiliate left off the combined roster is not simply dropped: each removal
    must appear on the "not included this year" list with a stated reason, and no
    excluded affiliate may also be a current member. This is the reconciliation
    that keeps a member from quietly leaving the combined base with nobody
    recording why.
    """
    rule = "grp_excluded_reconciled"
    _sev(rule, Status.FAIL)
    group = _group(ctx)
    if group is None:
        return []
    removals = _str_list(group.get("removals"))
    members = _member_set(ctx)
    excluded_rows = _rows(group, "excluded")
    reason_by_id: dict[str, str | None] = {}
    for row in excluded_rows:
        aid = _affiliate_id(row)
        if aid != "?":
            reason_by_id[aid] = _text(row, "reason")
    out: list[Finding] = []
    for removed in removals:
        if removed not in reason_by_id:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(group, f"excluded/{removed}"),
                    f"affiliate {removed} was removed from the combined group but is not "
                    f"enumerated on the excluded list; the exclusion is unreconciled",
                )
            )
        elif not reason_by_id[removed]:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(group, f"excluded/{removed}/reason"),
                    f"affiliate {removed} is listed as excluded with no reason; a removal "
                    f"must record why it left the combined group",
                )
            )
    for aid in reason_by_id:
        if aid in members:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(group, f"excluded/{aid}"),
                    f"affiliate {aid} is on the excluded list and is also a current "
                    f"combined member; it cannot be both",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(removals)} removed affiliate(s) are enumerated and reconciled"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# tb_ -- the consolidated trial-balance workpaper
# --------------------------------------------------------------------------- #
@check("tb_required_fields")
def check_tb_required_fields(ctx: Context) -> list[Finding]:
    """Every trial-balance line carries the descriptive and amount fields the controls read."""
    rule = "tb_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_TRIAL_BALANCE)
    if register is None:
        return []
    text_fields = ("tb_line_id", "affiliate_id", "account")
    out: list[Finding] = []
    for row in _tb_lines(ctx):
        missing = [f for f in text_fields if not _text(row, f)]
        if row.get("revenue_cents") is None:
            missing.append("revenue_cents")
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"lines/{_tb_line_id(row)}"),
                    f"trial-balance line {_tb_line_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_tb_lines(ctx))} trial-balance lines carry their fields")
        )
    return out


@check("tb_line_unique")
def check_tb_line_unique(ctx: Context) -> list[Finding]:
    """No trial-balance line id appears twice.

    A shared line id means one revenue figure was counted onto two lines, and the
    workpaper can no longer prove the consolidated revenue is not double-counting a
    dollar.
    """
    rule = "tb_line_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_TRIAL_BALANCE)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _tb_lines(ctx):
        seen[_tb_line_id(row)] = seen.get(_tb_line_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"lines/{lid}"),
            f"trial-balance line id {lid} appears {count} times; the same revenue cannot "
            f"be counted twice into the consolidated base",
        )
        for lid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} trial-balance line ids are unique")
        )
    return out


@check("tb_member_known")
def check_tb_member_known(ctx: Context) -> list[Finding]:
    """Every trial-balance line belongs to a current combined member.

    A revenue line attributed to an affiliate that is not in the combined group is
    revenue pulled into the consolidated base from outside the group -- a member's
    receipts the group is not entitled to combine, or a stray line nobody mapped.
    """
    rule = "tb_member_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_TRIAL_BALANCE)
    group = _group(ctx)
    if register is None or group is None:
        return []
    members = _member_set(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"lines/{_tb_line_id(row)}/affiliate_id"),
            f"trial-balance line {_tb_line_id(row)} is attributed to {_text(row, 'affiliate_id')!r}, "
            f"which is not a current combined member",
        )
        for row in _tb_lines(ctx)
        if _text(row, "affiliate_id") and _text(row, "affiliate_id") not in members
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every trial-balance line belongs to a combined member")
        )
    return out


# --------------------------------------------------------------------------- #
# apt_ -- receipts and the apportionment factor
# --------------------------------------------------------------------------- #
@check("apt_receipts_sound")
def check_apt_receipts_sound(ctx: Context) -> list[Finding]:
    """Each receipts row carries both figures, and in-state never exceeds everywhere.

    In-state receipts are a subset of everywhere receipts, so a row whose in-state
    figure is above its everywhere figure is a factor component that cannot be
    real. Presence of both figures is checked first: a missing everywhere figure is
    a denominator that never existed.
    """
    rule = "apt_receipts_sound"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_RECEIPTS_FACTOR)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _receipts_rows(ctx):
        aid = _affiliate_id(row)
        with amount_guard(rule, out):
            in_state = require_cents(
                f"receipts[{aid}].in_state_receipts_cents", row.get("in_state_receipts_cents")
            )
            everywhere = require_cents(
                f"receipts[{aid}].everywhere_receipts_cents", row.get("everywhere_receipts_cents")
            )
            checked += 1
            if in_state > everywhere:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"receipts/{aid}/in_state_receipts_cents"),
                        f"affiliate {aid} reports in-state receipts {fmt(in_state)} above its "
                        f"everywhere receipts {fmt(everywhere)}; in-state is a subset of everywhere",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} receipts rows are sound")
        )
    return out


@check("apt_totals_tie_receipts")
def check_apt_totals_tie_receipts(ctx: Context) -> list[Finding]:
    """The stated in-state and everywhere totals sum the receipts rows.

    The apportionment factor is struck against these two totals, so a total that
    does not sum the rows underneath it is a numerator or denominator nobody
    reconciled -- and the factor is wrong before the division even happens.
    """
    rule = "apt_totals_tie_receipts"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_RECEIPTS_FACTOR)
    if register is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        in_state_sum = 0
        everywhere_sum = 0
        for row in _receipts_rows(ctx):
            aid = _affiliate_id(row)
            in_state_sum += require_cents(
                f"receipts[{aid}].in_state_receipts_cents", row.get("in_state_receipts_cents")
            )
            everywhere_sum += require_cents(
                f"receipts[{aid}].everywhere_receipts_cents", row.get("everywhere_receipts_cents")
            )
        stated_in_state = require_cents(
            "receipts_factor.in_state_total_cents", register.get("in_state_total_cents")
        )
        stated_everywhere = require_cents(
            "receipts_factor.everywhere_total_cents", register.get("everywhere_total_cents")
        )
        if stated_in_state != in_state_sum or stated_everywhere != everywhere_sum:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, "in_state_total_cents"),
                    f"the receipts workpaper states totals in-state {fmt(stated_in_state)} / "
                    f"everywhere {fmt(stated_everywhere)}; the rows sum to {fmt(in_state_sum)} / "
                    f"{fmt(everywhere_sum)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the receipts totals of {fmt(in_state_sum)} / {fmt(everywhere_sum)} tie the rows",
                )
            )
    return out


@check("apt_factor_recomputes")
def check_apt_factor_recomputes(ctx: Context) -> list[Finding]:
    """The stated apportionment factor equals in-state over everywhere, bounded 0..1.

    The receipts factor is in-state receipts divided by everywhere receipts, floored
    to a basis point and bounded to ``[0.00%, 100.00%]``. The stated factor is
    recomputed from the workpaper's own totals and compared with exact ``==``; a
    factor read off the wrong denominator, or one outside the bound, does not tie.
    """
    rule = "apt_factor_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_RECEIPTS_FACTOR)
    if register is None:
        return []
    out: list[Finding] = []
    stated = _int(register, "factor_bps")
    if stated is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(register, "factor_bps"),
                "the receipts workpaper carries no integer basis-point factor",
            )
        )
        return out
    with amount_guard(rule, out):
        expected = stated_receipts_factor_bps(ctx)
        if not 0 <= stated <= BPS_FULL:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, "factor_bps"),
                    f"the apportionment factor {fmt_bps(stated)} is outside the bound "
                    f"[0.00%, 100.00%]",
                )
            )
        elif stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, "factor_bps"),
                    f"the receipts workpaper states an apportionment factor of {fmt_bps(stated)}; "
                    f"in-state over everywhere recomputes {fmt_bps(expected)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"the apportionment factor {fmt_bps(stated)} recomputes"
                )
            )
    return out


@check("apt_worksheet_factor_recomputes")
def check_apt_worksheet_factor_recomputes(ctx: Context) -> list[Finding]:
    """The margin worksheet's apportionment factor equals the recomputed receipts factor.

    The margin worksheet carries the factor it applied to the group margin; it must
    equal the factor recomputed from the receipts workpaper's totals, or the tax was
    apportioned by a share the receipts do not support.
    """
    rule = "apt_worksheet_factor_recomputes"
    _sev(rule, Status.FAIL)
    worksheet = _worksheet(ctx)
    receipts = ctx.one(DOC_RECEIPTS_FACTOR)
    if worksheet is None or receipts is None:
        return []
    out: list[Finding] = []
    stated = _int(worksheet, "apportionment_factor_bps")
    if stated is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(worksheet, "apportionment_factor_bps"),
                "the margin worksheet carries no integer basis-point apportionment factor",
            )
        )
        return out
    with amount_guard(rule, out):
        expected = stated_receipts_factor_bps(ctx)
        if stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "apportionment_factor_bps"),
                    f"the margin worksheet applied an apportionment factor of {fmt_bps(stated)}; "
                    f"the receipts workpaper recomputes {fmt_bps(expected)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"the worksheet apportionment factor {fmt_bps(stated)} ties the receipts"
                )
            )
    return out


# --------------------------------------------------------------------------- #
# mgn_ -- group revenue and the margin tax
# --------------------------------------------------------------------------- #
@check("mgn_revenue_ties_tb")
def check_mgn_revenue_ties_tb(ctx: Context) -> list[Finding]:
    """The margin worksheet's group revenue sums the consolidated trial-balance lines.

    This is the base-completeness control: the revenue the group margin is struck
    from must be the sum of the consolidated trial-balance lines. A line dropped on
    the way to the return is a revenue base short of the workpaper, and the tax is
    short with it.
    """
    rule = "mgn_revenue_ties_tb"
    _sev(rule, Status.FAIL)
    worksheet = _worksheet(ctx)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if worksheet is None or tb is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "margin_worksheet.group_revenue_cents", worksheet.get("group_revenue_cents")
        )
        summed = 0
        for line in _tb_lines(ctx):
            summed += require_cents(
                f"trial_balance[{_tb_line_id(line)}].revenue_cents", line.get("revenue_cents")
            )
        if stated != summed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "group_revenue_cents"),
                    f"the margin worksheet states group revenue {fmt(stated)}; the "
                    f"consolidated trial-balance lines sum to {fmt(summed)} "
                    f"(off by {fmt(stated - summed)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"group revenue {fmt(summed)} ties the consolidated trial balance"
                )
            )
    return out


@check("mgn_margin_recomputes")
def check_mgn_margin_recomputes(ctx: Context) -> list[Finding]:
    """The taxable margin equals group revenue less the elected deduction.

    The margin is consolidated revenue reduced by the group's elected deduction,
    clamped at zero. A margin that does not re-derive is a margin someone adjusted
    after the revenue was reconciled to it.
    """
    rule = "mgn_margin_recomputes"
    _sev(rule, Status.FAIL)
    worksheet = _worksheet(ctx)
    if worksheet is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        revenue = require_cents(
            "margin_worksheet.group_revenue_cents", worksheet.get("group_revenue_cents")
        )
        deduction = require_cents(
            "margin_worksheet.elected_deduction_cents", worksheet.get("elected_deduction_cents")
        )
        stated = require_cents(
            "margin_worksheet.taxable_margin_cents", worksheet.get("taxable_margin_cents")
        )
        expected = taxable_margin(revenue, deduction)
        if stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "taxable_margin_cents"),
                    f"the margin worksheet states taxable margin {fmt(stated)}; revenue "
                    f"{fmt(revenue)} less elected deduction {fmt(deduction)} re-derives {fmt(expected)}",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"the taxable margin {fmt(expected)} re-derives")
            )
    return out


@check("mgn_apportioned_recomputes")
def check_mgn_apportioned_recomputes(ctx: Context) -> list[Finding]:
    """The apportioned margin equals the taxable margin at the recomputed factor.

    The apportioned margin is the taxable margin scaled by the receipts factor, in
    truncating basis-point arithmetic. It is re-derived against the factor recomputed
    from the receipts -- not the worksheet's stated factor -- and compared with exact
    ``==``.
    """
    rule = "mgn_apportioned_recomputes"
    _sev(rule, Status.FAIL)
    worksheet = _worksheet(ctx)
    if worksheet is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        margin = require_cents(
            "margin_worksheet.taxable_margin_cents", worksheet.get("taxable_margin_cents")
        )
        stated = require_cents(
            "margin_worksheet.apportioned_margin_cents", worksheet.get("apportioned_margin_cents")
        )
        factor = stated_receipts_factor_bps(ctx)
        expected = apportioned_margin(margin, factor)
        if stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "apportioned_margin_cents"),
                    f"the margin worksheet states apportioned margin {fmt(stated)}; "
                    f"{fmt(margin)} at {fmt_bps(factor)} re-derives {fmt(expected)}",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"the apportioned margin {fmt(expected)} re-derives")
            )
    return out


@check("mgn_tax_recomputes")
def check_mgn_tax_recomputes(ctx: Context) -> list[Finding]:
    """The franchise tax equals the apportioned margin at the margin-tax rate.

    This is the figure that reaches the return. The tax is the apportioned margin
    struck at the margin-tax rate, in truncating basis-point arithmetic, and must
    equal the worksheet's stated tax to the cent.
    """
    rule = "mgn_tax_recomputes"
    _sev(rule, Status.FAIL)
    worksheet = _worksheet(ctx)
    if worksheet is None:
        return []
    out: list[Finding] = []
    rate = _int(worksheet, "rate_bps")
    if rate is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(worksheet, "rate_bps"),
                "the margin worksheet carries no integer basis-point margin-tax rate",
            )
        )
        return out
    with amount_guard(rule, out):
        apportioned = require_cents(
            "margin_worksheet.apportioned_margin_cents", worksheet.get("apportioned_margin_cents")
        )
        stated = require_cents("margin_worksheet.tax_cents", worksheet.get("tax_cents"))
        expected = margin_tax(apportioned, rate)
        if stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(worksheet, "tax_cents"),
                    f"the margin worksheet states tax {fmt(stated)}; {fmt(apportioned)} at "
                    f"{fmt_bps(rate)} re-derives {fmt(expected)}",
                )
            )
        else:
            out.append(
                Finding(rule, Status.PASS, "-", f"the franchise tax {fmt(expected)} re-derives")
            )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the workpapers
# --------------------------------------------------------------------------- #
@check("rpt_summary_recomputes")
def check_rpt_summary_recomputes(ctx: Context) -> list[Finding]:
    """The summarised tax recomputes end to end from the workpapers.

    This is the control the engine exists for. The tax summary is a determination,
    and a determination not recomputed from the workpapers is an assertion. The
    engine rebuilds the whole tax -- group revenue from the trial balance, the
    apportionment factor from the receipts, the margin from the elected deduction,
    the tax from the rate -- through the shared kernel and compares it to the
    summarised figure.
    """
    rule = "rpt_summary_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TAX_SUMMARY)
    if summary is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents("tax_summary.tax_cents", summary.get("tax_cents"))
        recomputed = recompute_group_tax(ctx)
        if recomputed is None:
            return out  # mgn_tax_recomputes owns an unreadable rate
        if stated != recomputed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(summary, "tax_cents"),
                    f"the tax summary states franchise tax {fmt(stated)}; recomputing from "
                    f"the workpapers gives {fmt(recomputed)}",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"the summarised franchise tax {fmt(stated)} recomputes from the workpapers"
                )
            )
    return out


@check("rpt_report_totals_tie")
def check_rpt_report_totals_tie(ctx: Context) -> list[Finding]:
    """The combined-return total and member count tie the summary and the roster.

    The number that reaches the state is a total, and a total maintained beside the
    summary rather than derived from it drifts the first time the tax moves and
    nobody re-adds the column. The stated combined-member count is checked against
    the roster the same way.
    """
    rule = "rpt_report_totals_tie"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_FRANCHISE_REPORT)
    summary = ctx.one(DOC_TAX_SUMMARY)
    if report is None or summary is None:
        return []
    out: list[Finding] = []
    member_count = len(_members(ctx))
    with amount_guard(rule, out):
        summary_tax = require_cents("tax_summary.tax_cents", summary.get("tax_cents"))
        stated_total = require_cents(
            "franchise_report.total_tax_due_cents", report.get("total_tax_due_cents")
        )
        stated_count = require_cents(
            "franchise_report.member_count", report.get("member_count"), unit="a whole count"
        )
        if stated_total != summary_tax or stated_count != member_count:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "total_tax_due_cents"),
                    f"the report states total {fmt(stated_total)} over {stated_count} "
                    f"combined member(s); the summary and roster give {fmt(summary_tax)} "
                    f"over {member_count}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report total {fmt(summary_tax)} over {member_count} member(s) ties the summary and roster",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one combined-return file."""
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
    """Analyze every ``.json`` combined-return file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of combined-return-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
