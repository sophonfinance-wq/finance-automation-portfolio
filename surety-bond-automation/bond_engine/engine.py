"""
Surety bond & collateral control engine (READ-ONLY).
====================================================

Loads each programme file (a ``.json`` file produced by
:mod:`bond_engine.generate`) and runs an ordered *registry* of independent
controls over it.

The shape of the problem
------------------------
A developer's bonds are not one instrument, they are a portfolio of obligations
with staggered terms and different obligees, and the money attached to them moves
in two directions: premium out, collateral out and then -- if anyone remembers to
ask -- collateral back. Nothing in the ordinary accounting cycle notices when the
last step does not happen. A released bond raises no payable, ages on no report,
and its collateral is indistinguishable from cash until the register is tied to
the restricted-cash ledger.

The registry is organised around the lifecycle:

1. ``set_``   -- is the programme file complete?
2. ``reg_``   -- is the register itself sound: unique numbers, real projects, sane terms?
3. ``stat_``  -- does each bond meet the statute and take the right obligee?
4. ``life_``  -- does the bond's life hang together: in force, renewed, released properly?
5. ``coll_``  -- did the collateral follow the bond, and did it come back?
6. ``prem_``  -- is the premium rated, amortised and stopped at the right time?
7. ``expo_``  -- does the aggregate exposure fit inside the facility?

Design notes
------------
- **Strictly read-only.** Programme files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order. Every date
  test is made against the ``as_of`` carried in the file, never the system clock.
- **Integer cents, no tolerance.** Amounts are compared with exact ``==``, except
  the one control that is explicitly a reasonableness band (``prem_rate_within_schedule``),
  which reads its tolerance from the rate schedule rather than inventing one.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.

Collateral is the spine
-----------------------
A bond's collateral has to be traceable three ways at once: to the penal sum it
supports (it can never exceed it), to the ledger entries that moved it (posted
less refunded), and to the restricted-cash balance on the general ledger. When all
three agree the programme is reconciled. When a released bond still carries a
balance, the developer has lent the surety money interest-free and forgotten.
"""

from __future__ import annotations

import contextlib
import functools
import json
import re
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .model import (
    BOND_LICENCE,
    BOND_MAINTENANCE,
    BOND_STATUSES,
    BOND_TYPES,
    COLL_POSTED,
    COLL_REFUNDED,
    COLLATERAL_AGE_BANDS,
    COLLATERAL_ENTRY_TYPES,
    DOC_BOND_REGISTER,
    DOC_COLLATERAL_LEDGER,
    DOC_GL_POSITIONS,
    DOC_PREMIUM_LEDGER,
    DOC_PROJECT_REGISTER,
    DOC_RATE_SCHEDULE,
    DOC_STATUTORY_TABLE,
    DOC_SURETY_FACILITY,
    DOC_TYPES,
    EXPIRY_HORIZON_DAYS,
    OBLIGEE_MUNICIPAL,
    OBLIGEE_STATE,
    PERMIT_LINKED_TYPES,
    PREM_RETURN,
    PREMIUM_ENTRY_TYPES,
    STATUS_ACTIVE,
    STATUS_RELEASED,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, apply_rate, fmt, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~bond_engine.money.AmountInvalidError` as a finding."""
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


# --------------------------------------------------------------------------- #
# Programme helpers
# --------------------------------------------------------------------------- #
def _bonds(ctx: Context) -> list[dict[str, Any]]:
    """Every bond row in the register, in file order."""
    return _rows(ctx.one(DOC_BOND_REGISTER), "bonds")


def _bond_no(row: dict[str, Any]) -> str:
    value = row.get("bond_no")
    return value if isinstance(value, str) and value else "?"


def _projects(ctx: Context) -> dict[str, dict[str, Any]]:
    """Map project code -> project row (first wins on a duplicate)."""
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_PROJECT_REGISTER), "projects"):
        code = _text(row, "code")
        if code and code not in out:
            out[code] = row
    return out


def _collateral_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_COLLATERAL_LEDGER), "entries")


def _premium_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PREMIUM_LEDGER), "entries")


def _statutory(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    """Map ``(jurisdiction, bond_type)`` -> statutory row."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_STATUTORY_TABLE), "minimums"):
        juris = _text(row, "jurisdiction")
        btype = _text(row, "bond_type")
        if juris and btype and (juris, btype) not in out:
            out[(juris, btype)] = row
    return out


def _rate_rows(ctx: Context) -> dict[str, dict[str, Any]]:
    """Map bond type -> rate-card row."""
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_RATE_SCHEDULE), "rates"):
        btype = _text(row, "bond_type")
        if btype and btype not in out:
            out[btype] = row
    return out


def _collateral_by_bond(ctx: Context, rule: str, out: list[Finding]) -> dict[str, tuple[int, int]]:
    """Map bond number -> ``(posted_cents, refunded_cents)`` from the ledger."""
    totals: dict[str, tuple[int, int]] = {}
    for entry in _collateral_entries(ctx):
        bond = _text(entry, "bond_no")
        etype = _text(entry, "entry_type")
        if not bond or etype not in COLLATERAL_ENTRY_TYPES:
            continue
        with amount_guard(rule, out):
            amount = require_cents(
                f"collateral_ledger.entries[{entry.get('entry_no')}].amount_cents",
                entry.get("amount_cents"),
            )
            posted, refunded = totals.get(bond, (0, 0))
            if etype == COLL_POSTED:
                totals[bond] = (posted + amount, refunded)
            else:
                totals[bond] = (posted, refunded + amount)
    return totals


def _obligation_end(ctx: Context, bond: dict[str, Any]) -> date | None:
    """The date the obligation a bond secures actually ends.

    A maintenance bond runs to the end of the warranty period; every other
    project-linked bond runs to the municipality's acceptance of the work. A
    licence bond secures a registration rather than a project, so it has no
    project-derived obligation end and returns ``None``.
    """
    btype = _text(bond, "bond_type")
    if btype == BOND_LICENCE:
        return None
    project = _projects(ctx).get(_text(bond, "project_code") or "")
    if project is None:
        return None
    key = "warranty_end_date" if btype == BOND_MAINTENANCE else "acceptance_date"
    return _parse_date(project.get(key))


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the programme depends on is present, exactly once.

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
                    f"{doc_type} is missing; the controls that read it cannot run "
                    f"and must not be reported as having passed",
                )
            )
        elif len(found) > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"{len(found)} {doc_type} documents present; the programme file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(DOC_TYPES)} artifacts present")
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every expiry and "
                f"ageing test is made against it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# reg_ -- register integrity
# --------------------------------------------------------------------------- #
@check("reg_bond_number_unique")
def check_reg_bond_number_unique(ctx: Context) -> list[Finding]:
    """No bond number appears twice in the register.

    The bond number is the join key to the collateral ledger, the premium ledger
    and the surety's own records. Duplicate it and every downstream total silently
    doubles or halves depending on which side of the join you stand.
    """
    rule = "reg_bond_number_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    out: list[Finding] = []
    for row in _bonds(ctx):
        bond = _bond_no(row)
        seen[bond] = seen.get(bond, 0) + 1
    for bond, count in seen.items():
        if count > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}"),
                    f"bond number {bond} appears {count} times; it is the join key to "
                    f"the collateral and premium ledgers",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} bond numbers are unique")
        )
    return out


@check("reg_required_fields")
def check_reg_required_fields(ctx: Context) -> list[Finding]:
    """Every bond carries the fields the rest of the programme reads.

    A bond with no obligee cannot be released -- there is nobody to ask.
    """
    rule = "reg_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    required = (
        "bond_no",
        "project_code",
        "bond_type",
        "obligee",
        "obligee_kind",
        "jurisdiction",
        "status",
        "effective_date",
        "expiration_date",
    )
    out: list[Finding] = []
    for row in _bonds(ctx):
        bond = _bond_no(row)
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}"),
                    f"bond {bond} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_bonds(ctx))} bonds carry every required field"
            )
        )
    return out


@check("reg_status_domain")
def check_reg_status_domain(ctx: Context) -> list[Finding]:
    """Status and bond type are drawn from the declared vocabularies.

    A status the engine does not know is not a harmless label: every lifecycle
    control keys off it, so an unknown value quietly exempts the bond from the
    controls that matter most.
    """
    rule = "reg_status_domain"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _bonds(ctx):
        bond = _bond_no(row)
        status = _text(row, "status")
        btype = _text(row, "bond_type")
        obligee_kind = _text(row, "obligee_kind")
        if status is not None and status not in BOND_STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/status"),
                    f"bond {bond} has status {status!r}, which is outside "
                    f"{BOND_STATUSES}; every lifecycle control keys off status",
                )
            )
        if btype is not None and btype not in BOND_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/bond_type"),
                    f"bond {bond} has type {btype!r}, which is outside {BOND_TYPES}",
                )
            )
        if obligee_kind is not None and obligee_kind not in (
            OBLIGEE_STATE,
            OBLIGEE_MUNICIPAL,
        ):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/obligee_kind"),
                    f"bond {bond} has obligee kind {obligee_kind!r}, which is outside "
                    f"{(OBLIGEE_STATE, OBLIGEE_MUNICIPAL)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every status, type and obligee kind is in vocabulary")
        )
    return out


@check("reg_effective_before_expiration")
def check_reg_effective_before_expiration(ctx: Context) -> list[Finding]:
    """A bond's term runs forwards.

    An inverted term is usually a transposed pair of dates, and it makes the
    expiry and amortisation maths meaningless rather than merely wrong.
    """
    rule = "reg_effective_before_expiration"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        eff = _parse_date(row.get("effective_date"))
        exp = _parse_date(row.get("expiration_date"))
        if eff is None or exp is None:
            continue
        checked += 1
        if eff >= exp:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/effective_date"),
                    f"bond {bond} is effective {eff.isoformat()} but expires "
                    f"{exp.isoformat()}; the term does not run forwards",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} bond terms run forwards"))
    return out


@check("reg_project_mapped")
def check_reg_project_mapped(ctx: Context) -> list[Finding]:
    """Every bond points at a project that exists in the project register.

    The project is where the obligation end comes from. A bond against an unknown
    project cannot be tested for early release, because nothing says when the
    obligation it secures actually ended.
    """
    rule = "reg_project_mapped"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    for row in _bonds(ctx):
        bond = _bond_no(row)
        code = _text(row, "project_code")
        if code and code not in projects:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/project_code"),
                    f"bond {bond} names project {code!r}, which is not in the project "
                    f"register; its obligation end cannot be derived",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"every bond maps to one of {len(projects)} projects")
        )
    return out


# --------------------------------------------------------------------------- #
# stat_ -- statutory and form compliance
# --------------------------------------------------------------------------- #
@check("stat_licence_minimum")
def check_stat_licence_minimum(ctx: Context) -> list[Finding]:
    """A statutory bond is written for at least its statutory penal sum.

    The minimum is set by the state, not by the job or the surety. Writing one
    cent under it does not merely understate cover -- it leaves the registration
    it supports defective, which is a licensing problem, not an accounting one.
    """
    rule = "stat_licence_minimum"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    table = _statutory(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        btype = _text(row, "bond_type")
        juris = _text(row, "jurisdiction")
        if not btype or not juris:
            continue
        stat_row = table.get((juris, btype))
        if stat_row is None:
            continue
        with amount_guard(rule, out):
            minimum = require_cents(
                f"statutory_table[{juris}/{btype}].minimum_penal_sum_cents",
                stat_row.get("minimum_penal_sum_cents"),
            )
            penal = require_cents(
                f"bond[{bond}].penal_sum_cents", row.get("penal_sum_cents")
            )
            checked += 1
            if penal < minimum:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"bonds/{bond}/penal_sum_cents"),
                        f"bond {bond} is written for {fmt(penal)} against a statutory "
                        f"minimum of {fmt(minimum)} in {juris}; the registration it "
                        f"supports is defective",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} statutory bonds meet their minimum"
            )
        )
    return out


@check("stat_obligee_kind_matches_type")
def check_stat_obligee_kind_matches_type(ctx: Context) -> list[Finding]:
    """The obligee is the kind of body that holds that kind of bond.

    A licence bond is held by the state agency that issues the registration; a
    permit or plat bond is held by the municipality that issued the permit. A
    mismatch usually means the bond was filed with the wrong body, and a bond the
    obligee does not hold secures nothing.
    """
    rule = "stat_obligee_kind_matches_type"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        btype = _text(row, "bond_type")
        kind = _text(row, "obligee_kind")
        if btype not in BOND_TYPES or kind not in (OBLIGEE_STATE, OBLIGEE_MUNICIPAL):
            continue
        checked += 1
        expected = OBLIGEE_STATE if btype == BOND_LICENCE else OBLIGEE_MUNICIPAL
        if kind != expected:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"bonds/{bond}/obligee_kind"),
                    f"bond {bond} is a {btype} bond held by a {kind}; a {btype} bond is "
                    f"held by a {expected}, so it may have been filed with the wrong body",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} bonds take the expected obligee kind")
        )
    return out


@check("stat_permit_reference_present")
def check_stat_permit_reference_present(ctx: Context) -> list[Finding]:
    """A permit- or plat-linked bond records the permit it was issued against.

    The permit number is how the release is eventually requested. Without it the
    bond can be found in the register but not matched to the obligation it
    secures, and releases stall on evidence nobody kept.
    """
    rule = "stat_permit_reference_present"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        btype = _text(row, "bond_type")
        if btype not in PERMIT_LINKED_TYPES:
            continue
        checked += 1
        if not _text(row, "permit_no"):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"bonds/{bond}/permit_no"),
                    f"bond {bond} is a {btype} bond with no permit number; the release "
                    f"request has nothing to cite",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} permit-linked bonds cite a permit number"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# life_ -- lifecycle and expiry
# --------------------------------------------------------------------------- #
@check("life_active_not_expired")
def check_life_active_not_expired(ctx: Context) -> list[Finding]:
    """A bond carried as active has not already expired.

    An expired bond still shown as active is the worst of both states: the
    programme believes it has cover it does not have, and the penal sum keeps
    consuming facility capacity that could be written elsewhere.
    """
    rule = "life_active_not_expired"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        if _text(row, "status") != STATUS_ACTIVE:
            continue
        exp = _parse_date(row.get("expiration_date"))
        if exp is None:
            continue
        checked += 1
        if exp < as_of:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/expiration_date"),
                    f"bond {bond} is carried active but expired {exp.isoformat()}, "
                    f"before the {as_of.isoformat()} review date; the programme believes "
                    f"it holds cover it does not hold",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} active bonds are in force"))
    return out


@check("life_expiry_horizon")
def check_life_expiry_horizon(ctx: Context) -> list[Finding]:
    """Surface active bonds inside the renewal horizon.

    Not an error -- a decision. Every bond nearing expiry is either renewed (pay
    the premium) or released (recover the collateral), and the only bad outcome is
    letting the date arrive without choosing.
    """
    rule = "life_expiry_horizon"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_BOND_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    horizon = as_of + timedelta(days=EXPIRY_HORIZON_DAYS)
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        if _text(row, "status") != STATUS_ACTIVE:
            continue
        exp = _parse_date(row.get("expiration_date"))
        if exp is None:
            continue
        checked += 1
        if as_of <= exp <= horizon:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"bonds/{bond}/expiration_date"),
                    f"bond {bond} expires {exp.isoformat()}, within {EXPIRY_HORIZON_DAYS} "
                    f"days of the review date; renew it or release it and recover the "
                    f"collateral",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"none of the {checked} active bonds expire within {EXPIRY_HORIZON_DAYS} days",
            )
        )
    return out


@check("life_renewal_continuity")
def check_life_renewal_continuity(ctx: Context) -> list[Finding]:
    """A renewal picks up where the bond it replaces left off.

    A gap between the old term ending and the new one starting is a window in
    which the obligation was unbonded. It is invisible afterwards -- both bonds
    look perfectly valid on their own -- and it is exactly the window a claim
    would land in.
    """
    rule = "life_renewal_continuity"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    by_no = {_bond_no(r): r for r in _bonds(ctx)}
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        prior_no = _text(row, "renewed_from")
        if not prior_no:
            continue
        prior = by_no.get(prior_no)
        if prior is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/renewed_from"),
                    f"bond {bond} renews {prior_no}, which is not in the register; the "
                    f"continuity of cover cannot be proven",
                )
            )
            continue
        new_eff = _parse_date(row.get("effective_date"))
        prior_exp = _parse_date(prior.get("expiration_date"))
        if new_eff is None or prior_exp is None:
            continue
        checked += 1
        # Continuity holds when the new term starts no later than the day after
        # the old one ended. Same-day or earlier (an overlap) is fine for cover.
        if new_eff > prior_exp + timedelta(days=1):
            gap = (new_eff - prior_exp).days - 1
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/effective_date"),
                    f"bond {bond} takes effect {new_eff.isoformat()} but {prior_no} expired "
                    f"{prior_exp.isoformat()}, leaving {gap} day(s) in which the obligation "
                    f"was unbonded",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} renewals are continuous"))
    return out


@check("life_released_has_evidence")
def check_life_released_has_evidence(ctx: Context) -> list[Finding]:
    """A bond marked released carries the date and the document that released it.

    "Released" is an assertion about what a third party did. Without the obligee's
    release letter it is an assertion about what somebody believes the third party
    did, and the collateral recovery that follows rests on it.
    """
    rule = "life_released_has_evidence"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        if _text(row, "status") != STATUS_RELEASED:
            continue
        checked += 1
        released_on = _parse_date(row.get("release_date"))
        reference = _text(row, "release_reference")
        if released_on is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/release_date"),
                    f"bond {bond} is marked released with no readable release date",
                )
            )
        if not reference:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/release_reference"),
                    f"bond {bond} is marked released with no obligee release document; "
                    f"the release is asserted, not evidenced",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} released bonds carry release evidence")
        )
    return out


@check("life_release_after_obligation")
def check_life_release_after_obligation(ctx: Context) -> list[Finding]:
    """A bond is not released before the obligation it secures has ended.

    A maintenance bond runs to the end of the warranty period; a performance or
    plat bond runs to the municipality's acceptance of the work. Releasing before
    that date means the developer stood down cover while still on the hook.
    """
    rule = "life_release_after_obligation"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        if _text(row, "status") != STATUS_RELEASED:
            continue
        released_on = _parse_date(row.get("release_date"))
        ends = _obligation_end(ctx, row)
        if released_on is None or ends is None:
            continue
        checked += 1
        if released_on < ends:
            btype = _text(row, "bond_type")
            label = (
                "the warranty period ended"
                if btype == BOND_MAINTENANCE
                else "the work was accepted"
            )
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/release_date"),
                    f"bond {bond} was released {released_on.isoformat()} but {label} "
                    f"{ends.isoformat()}; cover was stood down while the obligation ran",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} releases follow the obligation they secured"
            )
        )
    return out


@check("life_maintenance_follows_acceptance")
def check_life_maintenance_follows_acceptance(ctx: Context) -> list[Finding]:
    """A maintenance bond starts when the work is accepted, not before.

    The warranty period it covers begins at acceptance. A maintenance bond
    incepting earlier is paying premium for a period in which it secures nothing,
    and it usually means the performance bond was converted on the wrong date.
    """
    rule = "life_maintenance_follows_acceptance"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    projects = _projects(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        if _text(row, "bond_type") != BOND_MAINTENANCE:
            continue
        project = projects.get(_text(row, "project_code") or "")
        if project is None:
            continue
        accepted = _parse_date(project.get("acceptance_date"))
        eff = _parse_date(row.get("effective_date"))
        if accepted is None or eff is None:
            continue
        checked += 1
        if eff < accepted:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"bonds/{bond}/effective_date"),
                    f"maintenance bond {bond} incepts {eff.isoformat()} but the work was "
                    f"accepted {accepted.isoformat()}; it is carrying premium for a period "
                    f"in which it secures nothing",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} maintenance bonds start at acceptance"
            )
        )
    return out


@check("life_no_release_while_collateral_outstanding")
def check_life_no_release_while_collateral_outstanding(ctx: Context) -> list[Finding]:
    """A released bond has had its collateral returned, or says why not.

    This is the control the programme exists for. The obligee discharges the
    bond, the register is updated, the premium stops -- and the cash the developer
    posted to the surety stays where it is. Nothing else in the accounting cycle
    notices: a released bond raises no payable and ages on no report, and the
    balance sits in restricted cash looking exactly like cash.

    A refund that is genuinely in flight is fine, and says so in
    ``collateral_refund_status``. Silence is the failure.
    """
    rule = "life_no_release_while_collateral_outstanding"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    totals = _collateral_by_bond(ctx, rule, out)
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        if _text(row, "status") != STATUS_RELEASED:
            continue
        posted, refunded = totals.get(bond, (0, 0))
        outstanding = posted - refunded
        if outstanding <= 0:
            checked += 1
            continue
        checked += 1
        if not _text(row, "collateral_refund_status"):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"bonds/{bond}/collateral_refund_status"),
                    f"bond {bond} is released but {fmt(outstanding)} of collateral is still "
                    f"with the surety and no refund is recorded as in flight; the cash is "
                    f"sitting in restricted cash with nothing chasing it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} released bonds are refunded or have a refund in flight",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# coll_ -- collateral
# --------------------------------------------------------------------------- #
@check("coll_not_exceed_penal_sum")
def check_coll_not_exceed_penal_sum(ctx: Context) -> list[Finding]:
    """Collateral posted never exceeds the penal sum it supports.

    The penal sum is the surety's maximum exposure. Collateral above it is money
    secured against a risk that cannot occur, and it is almost always a keying
    error -- the same digits, one place left.
    """
    rule = "coll_not_exceed_penal_sum"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    totals = _collateral_by_bond(ctx, rule, out)
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        posted, _refunded = totals.get(bond, (0, 0))
        if posted == 0:
            continue
        with amount_guard(rule, out):
            penal = require_cents(
                f"bond[{bond}].penal_sum_cents", row.get("penal_sum_cents")
            )
            checked += 1
            if posted > penal:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"bonds/{bond}/penal_sum_cents"),
                        f"bond {bond} has {fmt(posted)} of collateral against a penal sum of "
                        f"{fmt(penal)}; collateral cannot exceed the exposure it secures",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} collateralised bonds sit within their penal sum")
        )
    return out


@check("coll_ledger_ties_register")
def check_coll_ledger_ties_register(ctx: Context) -> list[Finding]:
    """The register's outstanding collateral equals posted less refunded.

    Two independent records of the same money: a summary column somebody
    maintains by hand, and the movements that actually happened. They are compared
    at zero tolerance, because a collateral balance that is nearly right is a
    balance nobody has reconciled.
    """
    rule = "coll_ledger_ties_register"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    totals = _collateral_by_bond(ctx, rule, out)
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        with amount_guard(rule, out):
            stated = require_cents(
                f"bond[{bond}].collateral_outstanding_cents",
                row.get("collateral_outstanding_cents"),
            )
            posted, refunded = totals.get(bond, (0, 0))
            derived = posted - refunded
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"bonds/{bond}/collateral_outstanding_cents"),
                        f"bond {bond} states {fmt(stated)} outstanding; the ledger shows "
                        f"{fmt(posted)} posted less {fmt(refunded)} refunded = {fmt(derived)} "
                        f"(difference {fmt(stated - derived)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} bonds tie to the collateral ledger")
        )
    return out


@check("coll_refund_not_exceed_posted")
def check_coll_refund_not_exceed_posted(ctx: Context) -> list[Finding]:
    """Cumulative refunds never exceed cumulative postings.

    Getting back more than was posted is not a windfall, it is a mis-keyed refund
    or a refund applied to the wrong bond -- which means some *other* bond's
    recovery has quietly been consumed.
    """
    rule = "coll_refund_not_exceed_posted"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_COLLATERAL_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    totals = _collateral_by_bond(ctx, rule, out)
    for bond in sorted(totals):
        posted, refunded = totals[bond]
        if refunded > posted:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(ledger, f"entries/{bond}"),
                    f"bond {bond} has {fmt(refunded)} refunded against {fmt(posted)} posted; "
                    f"the excess {fmt(refunded - posted)} belongs to another bond",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"no bond has been refunded more than it posted")
        )
    return out


@check("coll_refund_aging")
def check_coll_refund_aging(ctx: Context) -> list[Finding]:
    """Age collateral still outstanding after a bond was released.

    A refund in flight is normal; a refund in flight for a year is not. Reporting
    the age in bands is what turns "pending" from a permanent state into an
    escalation, and the oldest band is where the real money has always been.
    """
    rule = "coll_refund_aging"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_BOND_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if register is None or as_of is None:
        return []
    out: list[Finding] = []
    totals = _collateral_by_bond(ctx, rule, out)
    threshold = COLLATERAL_AGE_BANDS[0]
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        if _text(row, "status") != STATUS_RELEASED:
            continue
        posted, refunded = totals.get(bond, (0, 0))
        outstanding = posted - refunded
        released_on = _parse_date(row.get("release_date"))
        if outstanding <= 0 or released_on is None:
            continue
        checked += 1
        age = (as_of - released_on).days
        if age < threshold:
            continue
        band = threshold
        for edge in COLLATERAL_AGE_BANDS:
            if age >= edge:
                band = edge
        out.append(
            Finding(
                rule,
                Status.FLAG,
                ctx.loc(register, f"bonds/{bond}/collateral_outstanding_cents"),
                f"bond {bond} was released {released_on.isoformat()} and {fmt(outstanding)} "
                f"of collateral is still outstanding {age} days later (>{band}-day band)",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"no released bond has collateral outstanding beyond {threshold} days",
            )
        )
    return out


@check("coll_location_recorded")
def check_coll_location_recorded(ctx: Context) -> list[Finding]:
    """Posted collateral records where it is held.

    Recovery starts with knowing who has the money. A balance with no custodian is
    a balance somebody will have to reconstruct from correspondence, and by then
    the person who posted it has usually moved on.
    """
    rule = "coll_location_recorded"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    totals = _collateral_by_bond(ctx, rule, out)
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        posted, refunded = totals.get(bond, (0, 0))
        if posted - refunded <= 0:
            continue
        checked += 1
        if not _text(row, "collateral_location"):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register, f"bonds/{bond}/collateral_location"),
                    f"bond {bond} holds {fmt(posted - refunded)} of collateral with no "
                    f"recorded custodian; recovery starts with knowing who has it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} outstanding balances record a custodian"
            )
        )
    return out


@check("coll_ties_restricted_cash_gl")
def check_coll_ties_restricted_cash_gl(ctx: Context) -> list[Finding]:
    """Total collateral outstanding equals the restricted-cash balance.

    The third leg of the tie-out, and the one that makes the other two matter. The
    register can agree with its own ledger and still disagree with the balance
    sheet, and it is the balance sheet that gets audited.
    """
    rule = "coll_ties_restricted_cash_gl"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    if gl is None:
        return []
    out: list[Finding] = []
    totals = _collateral_by_bond(ctx, rule, out)
    derived = sum(posted - refunded for posted, refunded in totals.values())
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.restricted_cash_collateral_cents",
            gl.get("restricted_cash_collateral_cents"),
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "restricted_cash_collateral_cents"),
                    f"restricted cash carries {fmt(stated)}; the collateral ledger nets to "
                    f"{fmt(derived)} (difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"collateral outstanding of {fmt(derived)} ties restricted cash",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# prem_ -- premium
# --------------------------------------------------------------------------- #
@check("prem_rate_within_schedule")
def check_prem_rate_within_schedule(ctx: Context) -> list[Finding]:
    """Premium charged is close to the rate card applied to the penal sum.

    This is the one deliberately tolerant control in the engine, and the tolerance
    comes from the rate schedule rather than from the engine's opinion. Sureties
    do adjust for credit and term, so an exact match is not expected -- but a
    premium well off the card is either a bond written at the wrong penal sum or
    an invoice nobody checked.
    """
    rule = "prem_rate_within_schedule"
    _sev(rule, Status.FLAG)
    register = ctx.one(DOC_BOND_REGISTER)
    schedule = ctx.one(DOC_RATE_SCHEDULE)
    if register is None or schedule is None:
        return []
    rates = _rate_rows(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _bonds(ctx):
        bond = _bond_no(row)
        btype = _text(row, "bond_type")
        rate_row = rates.get(btype or "")
        if rate_row is None:
            continue
        with amount_guard(rule, out):
            penal = require_cents(
                f"bond[{bond}].penal_sum_cents", row.get("penal_sum_cents")
            )
            charged = require_cents(
                f"bond[{bond}].annual_premium_cents", row.get("annual_premium_cents")
            )
            rate_bps = require_cents(
                f"rate_schedule[{btype}].rate_bps", rate_row.get("rate_bps"), unit="basis points"
            )
            minimum = require_cents(
                f"rate_schedule[{btype}].minimum_premium_cents",
                rate_row.get("minimum_premium_cents"),
            )
            tolerance_bps = require_cents(
                f"rate_schedule[{btype}].tolerance_bps",
                rate_row.get("tolerance_bps"),
                unit="basis points",
            )
            expected = max(apply_rate(penal, rate_bps), minimum)
            allowed = apply_rate(expected, tolerance_bps)
            checked += 1
            if abs(charged - expected) > allowed:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(register, f"bonds/{bond}/annual_premium_cents"),
                        f"bond {bond} carries premium {fmt(charged)}; the card rates a "
                        f"{btype} bond of {fmt(penal)} at {fmt(expected)} "
                        f"(tolerance {fmt(allowed)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} premiums sit within the rate card")
        )
    return out


@check("prem_no_premium_after_release")
def check_prem_no_premium_after_release(ctx: Context) -> list[Finding]:
    """No premium period begins after the bond was released.

    Renewal is usually automatic; release is usually manual. So the default
    outcome for a discharged bond nobody told the surety about is that it keeps
    billing, and the charge is small enough every year to clear approval without
    anyone asking what it is for.
    """
    rule = "prem_no_premium_after_release"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_PREMIUM_LEDGER)
    if ledger is None:
        return []
    released: dict[str, date] = {}
    for row in _bonds(ctx):
        if _text(row, "status") != STATUS_RELEASED:
            continue
        when = _parse_date(row.get("release_date"))
        if when is not None:
            released[_bond_no(row)] = when
    out: list[Finding] = []
    checked = 0
    for entry in _premium_entries(ctx):
        bond = _text(entry, "bond_no")
        if bond is None or bond not in released:
            continue
        starts = _parse_date(entry.get("period_from"))
        if starts is None:
            continue
        checked += 1
        if starts > released[bond]:
            with amount_guard(rule, out):
                amount = require_cents(
                    f"premium_ledger.entries[{entry.get('entry_no')}].amount_cents",
                    entry.get("amount_cents"),
                )
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(ledger, f"entries/{entry.get('entry_no')}/period_from"),
                        f"bond {bond} was released {released[bond].isoformat()} but is charged "
                        f"{fmt(amount)} for a period starting {starts.isoformat()}; the surety "
                        f"was never told to stop",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"none of {checked} post-release periods carry premium"
            )
        )
    return out


@check("prem_prepaid_amortisation_ties")
def check_prem_prepaid_amortisation_ties(ctx: Context) -> list[Finding]:
    """Unamortised premium is re-derived from each term and ties the GL.

    Premium is paid up front for a term, so at any review date part of it is still
    an asset. The engine re-derives that figure straight-line across the days of
    each term rather than trusting the number carried forward, and compares the
    total to prepaid on the balance sheet at zero tolerance.
    """
    rule = "prem_prepaid_amortisation_ties"
    _sev(rule, Status.FAIL)
    gl = ctx.one(DOC_GL_POSITIONS)
    ledger = ctx.one(DOC_PREMIUM_LEDGER)
    as_of = _parse_date(ctx.as_of)
    if gl is None or ledger is None or as_of is None:
        return []
    out: list[Finding] = []
    derived = 0
    for entry in _premium_entries(ctx):
        if _text(entry, "entry_type") == PREM_RETURN:
            continue
        starts = _parse_date(entry.get("period_from"))
        ends = _parse_date(entry.get("period_to"))
        if starts is None or ends is None or ends <= starts:
            continue
        with amount_guard(rule, out):
            amount = require_cents(
                f"premium_ledger.entries[{entry.get('entry_no')}].amount_cents",
                entry.get("amount_cents"),
            )
            span = (ends - starts).days
            remaining = (ends - as_of).days
            if remaining <= 0:
                continue
            if remaining > span:
                remaining = span
            # Truncating division matches the money contract, so the figure the
            # engine derives can be compared to the reported one with exact ==.
            derived += amount * remaining // span
    with amount_guard(rule, out):
        stated = require_cents(
            "gl_positions.prepaid_bond_premium_cents", gl.get("prepaid_bond_premium_cents")
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(gl, "prepaid_bond_premium_cents"),
                    f"prepaid bond premium carries {fmt(stated)}; straight-line amortisation "
                    f"of the premium ledger to {as_of.isoformat()} gives {fmt(derived)} "
                    f"(difference {fmt(stated - derived)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule, Status.PASS, "-", f"unamortised premium of {fmt(derived)} ties prepaid"
                )
            )
    return out


@check("prem_return_has_rider")
def check_prem_return_has_rider(ctx: Context) -> list[Finding]:
    """A return premium cites the rider that reduced the penal sum.

    Return premium arises because the bonded amount came down, and the bonded
    amount comes down by rider. A credit with no rider is a credit nobody can tie
    to a change in exposure -- which is the same shape as a credit applied to the
    wrong bond.
    """
    rule = "prem_return_has_rider"
    _sev(rule, Status.FLAG)
    ledger = ctx.one(DOC_PREMIUM_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for entry in _premium_entries(ctx):
        if _text(entry, "entry_type") != PREM_RETURN:
            continue
        checked += 1
        if not _text(entry, "rider_reference"):
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(ledger, f"entries/{entry.get('entry_no')}/rider_reference"),
                    f"return premium entry {entry.get('entry_no')} on bond "
                    f"{_text(entry, 'bond_no')} cites no rider; nothing ties the credit to a "
                    f"reduction in the penal sum",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} return premiums cite a rider")
        )
    return out


@check("prem_entry_type_domain")
def check_prem_entry_type_domain(ctx: Context) -> list[Finding]:
    """Premium and collateral entries use the declared entry-type vocabularies.

    Both ledgers are summed by entry type. A type the engine does not recognise is
    not merely unlabelled -- it is silently excluded from every total built on it.
    """
    rule = "prem_entry_type_domain"
    _sev(rule, Status.FAIL)
    premium = ctx.one(DOC_PREMIUM_LEDGER)
    collateral = ctx.one(DOC_COLLATERAL_LEDGER)
    if premium is None or collateral is None:
        return []
    out: list[Finding] = []
    for entry in _premium_entries(ctx):
        etype = _text(entry, "entry_type")
        if etype is not None and etype not in PREMIUM_ENTRY_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(premium, f"entries/{entry.get('entry_no')}/entry_type"),
                    f"premium entry {entry.get('entry_no')} has type {etype!r}, outside "
                    f"{PREMIUM_ENTRY_TYPES}; it is excluded from every total built on type",
                )
            )
    for entry in _collateral_entries(ctx):
        etype = _text(entry, "entry_type")
        if etype is not None and etype not in COLLATERAL_ENTRY_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(collateral, f"entries/{entry.get('entry_no')}/entry_type"),
                    f"collateral entry {entry.get('entry_no')} has type {etype!r}, outside "
                    f"{COLLATERAL_ENTRY_TYPES}; it is excluded from posted and refunded alike",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every ledger entry type is in vocabulary"))
    return out


# --------------------------------------------------------------------------- #
# expo_ -- aggregate exposure
# --------------------------------------------------------------------------- #
@check("expo_within_facility_limit")
def check_expo_within_facility_limit(ctx: Context) -> list[Finding]:
    """Active penal sums together fit inside the facility's aggregate limit.

    The indemnity agreement caps what the surety will write in total. Exposure is
    consumed by every bond still carried active -- including the ones whose
    obligations ended years ago -- so a programme that does not release cleanly
    runs out of capacity long before it runs out of credit.
    """
    rule = "expo_within_facility_limit"
    _sev(rule, Status.FAIL)
    facility = ctx.one(DOC_SURETY_FACILITY)
    if facility is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        limit = require_cents(
            "surety_facility.aggregate_limit_cents", facility.get("aggregate_limit_cents")
        )
        exposure = 0
        for row in _bonds(ctx):
            if _text(row, "status") != STATUS_ACTIVE:
                continue
            with amount_guard(rule, out):
                exposure += require_cents(
                    f"bond[{_bond_no(row)}].penal_sum_cents", row.get("penal_sum_cents")
                )
        if exposure > limit:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(facility, "aggregate_limit_cents"),
                    f"active penal sums total {fmt(exposure)} against an aggregate limit of "
                    f"{fmt(limit)}; the programme is {fmt(exposure - limit)} over and the next "
                    f"bond will be declined for capacity",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"active exposure {fmt(exposure)} of {fmt(limit)} limit "
                    f"({fmt(limit - exposure)} of capacity remaining)",
                )
            )
    return out


@check("expo_by_obligee_ties_total")
def check_expo_by_obligee_ties_total(ctx: Context) -> list[Finding]:
    """The exposure summary by obligee foots to active exposure.

    The summary is what gets reported to the surety and to management. If it does
    not foot to the register it came from, the capacity conversation is being had
    over a number nobody can source.
    """
    rule = "expo_by_obligee_ties_total"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_BOND_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    derived: dict[str, int] = {}
    for row in _bonds(ctx):
        if _text(row, "status") != STATUS_ACTIVE:
            continue
        obligee = _text(row, "obligee")
        if obligee is None:
            continue
        with amount_guard(rule, out):
            derived[obligee] = derived.get(obligee, 0) + require_cents(
                f"bond[{_bond_no(row)}].penal_sum_cents", row.get("penal_sum_cents")
            )
    stated: dict[str, int] = {}
    for row in _rows(register, "exposure_by_obligee"):
        obligee = _text(row, "obligee")
        if obligee is None:
            continue
        with amount_guard(rule, out):
            stated[obligee] = require_cents(
                f"exposure_by_obligee[{obligee}].penal_sum_cents", row.get("penal_sum_cents")
            )
    for obligee in sorted(set(stated) | set(derived)):
        want = derived.get(obligee, 0)
        got = stated.get(obligee, 0)
        if want != got:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"exposure_by_obligee/{obligee}"),
                    f"the summary shows {fmt(got)} of active exposure with {obligee}; the "
                    f"register carries {fmt(want)} (difference {fmt(got - want)})",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the summary foots to the register across {len(derived)} obligee(s)",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one programme file."""
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
    """Analyze every ``.json`` programme file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of programme-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
