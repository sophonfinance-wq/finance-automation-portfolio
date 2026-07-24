"""
Entity good-standing control engine (READ-ONLY).
================================================

Loads each standing file (a ``.json`` file produced by
:mod:`standing_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether each entity is in good standing in every state it
belongs to**, not about computing an income-tax number. It re-derives the
statutory due dates and flat fees, confirms the annual/biennial report is filed,
the franchise tax is paid, the registered agent is current and the SOS status is
ACTIVE -- each within its date gate -- and confirms a wound-down entity is
cancelled everywhere it ever touched.

The shape of the problem
------------------------
A closely-held real-estate group forms one entity per project and qualifies it
into each state it operates in, and it has to prove, entity by entity and state
by state, that the paper on file actually keeps that entity alive.

Three failures hide inside that, and none of them look wrong in a register of
one-line entries: the filing that slipped past its due date while the register
still shows the entity Active; the franchise tax paid a dollar short of the flat
statutory amount, or the agent named on the state's record who is not the agent
under contract; and the monthly rollup that calls an entity in good standing on a
determination nobody recomputed from the state records underneath it.

The registry is organised around that:

1. ``set_``  -- is the standing file complete?
2. ``ent_``  -- is the entity register sound, and is each entity's jurisdiction set known?
3. ``jur_``  -- is every required (entity, state) obligation defined and evidenced?
4. ``rec_``  -- is every state record well-formed and attributable?
5. ``fil_``  -- is each report's due date re-derivable, filed on time, its fee met, and what is due to renew?
6. ``tax_``  -- is the franchise tax the statutory amount, on the statutory date, paid on time?
7. ``agt_``  -- is the registered agent of record the contracted agent, with fee paid?
8. ``sts_``  -- does the internal Active status reconcile to the SOS ACTIVE status?
9. ``lic_``  -- is any required business license current?
10. ``dis_`` -- is every dissolved entity cancelled in every state it belonged to?
11. ``roll_`` -- does the rollup recompute from the records it summarises?

Design notes
------------
- **Strictly read-only.** Standing files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every fee and tax is compared with exact ``>=``.
- **One good-standing predicate.** Controls and the generator share the kernel in
  :mod:`standing_engine.standing`, so a determination cannot disagree with the
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

from .money import AmountInvalidError, fmt, require_cents
from .model import (
    DOC_COMPLIANCE_REPORT,
    DOC_ENTITY_REGISTER,
    DOC_JURISDICTION_MATRIX,
    DOC_RENEWAL_WATCHLIST,
    DOC_STANDING_RECORD_REGISTER,
    DOC_STANDING_SUMMARY,
    DOC_TYPES,
    ENTITY_STATUSES,
    ENTITY_TYPES,
    KNOWN_STATES,
    LICENSE_CURRENT,
    SOS_ACTIVE,
    STATUS_ACTIVE,
    STATUS_DISSOLVED,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .standing import (
    Obligation,
    StandingRecord,
    record_in_good_standing,
    within_renewal_window,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~standing_engine.money.AmountInvalidError` as a finding."""
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
# Standing-file helpers
# --------------------------------------------------------------------------- #
def _entities(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ENTITY_REGISTER), "entities")


def _entity_id(row: dict[str, Any]) -> str:
    value = row.get("entity_id")
    return value if isinstance(value, str) and value else "?"


def _entity_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _entities(ctx):
        eid = _entity_id(row)
        if eid != "?" and eid not in out:
            out[eid] = row
    return out


def _qualified_states(entity: dict[str, Any]) -> list[str]:
    value = entity.get("qualified_states")
    if not isinstance(value, list):
        return []
    return [s for s in value if isinstance(s, str)]


def _required_states(entity: dict[str, Any]) -> list[str]:
    """Formation state UNION qualified states, de-duplicated, order-stable.

    Only known states are returned; an unknown one is a defect the
    ``ent_jurisdictions_declared`` control owns, not a state to build obligations
    against.
    """
    out: list[str] = []
    formation = _text(entity, "formation_state")
    if formation in KNOWN_STATES and formation not in out:
        out.append(formation)  # type: ignore[arg-type]
    for state in _qualified_states(entity):
        if state in KNOWN_STATES and state not in out:
            out.append(state)
    return out


def _is_active(entity: dict[str, Any]) -> bool:
    return _text(entity, "status") == STATUS_ACTIVE


def _requirements(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_JURISDICTION_MATRIX), "requirements")


def _matrix(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _requirements(ctx):
        state = _text(row, "state")
        etype = _text(row, "entity_type")
        if state and etype and (state, etype) not in out:
            out[(state, etype)] = row
    return out


def _records(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_STANDING_RECORD_REGISTER), "records")


def _record_id(row: dict[str, Any]) -> str:
    value = row.get("record_id")
    return value if isinstance(value, str) and value else "?"


def _record_for(ctx: Context, entity_id: str, state: str) -> dict[str, Any] | None:
    """The single record for one (entity, state) pair, or ``None``.

    Selection reads only the entity id and state, never an amount, so choosing the
    governing record cannot itself raise on a malformed fee -- the fee is read
    later, by the control that needs it. On the (defective) duplicate, the record
    with the lowest id is chosen so the pick is stable rather than merely correct.
    """
    matches = [
        r
        for r in _records(ctx)
        if _text(r, "entity_id") == entity_id and _text(r, "state") == state
    ]
    if not matches:
        return None
    return min(matches, key=_record_id)


def _obligation_from_row(row: dict[str, Any]) -> Obligation:
    """Read a matrix row into an :class:`~standing_engine.standing.Obligation`.

    Raises :class:`AmountInvalidError` if either flat fee is not integer cents.
    """
    return Obligation(
        report_fee_cents=require_cents(
            "obligation.report_fee_cents", row.get("report_fee_cents")
        ),
        franchise_tax_cents=require_cents(
            "obligation.franchise_tax_cents", row.get("franchise_tax_cents")
        ),
        requires_registered_agent=bool(row.get("requires_registered_agent")),
        requires_business_license=bool(row.get("requires_business_license")),
    )


def _record_from_row(record: dict[str, Any]) -> StandingRecord:
    """Read a record into a :class:`~standing_engine.standing.StandingRecord`.

    Raises :class:`AmountInvalidError` if either paid amount is not integer cents.
    """
    return StandingRecord(
        sos_status=record.get("sos_status") if isinstance(record.get("sos_status"), str) else "",
        report_due=_parse_date(record.get("report_due_date")),
        report_filed=_parse_date(record.get("report_filed_date")),
        report_fee_paid_cents=require_cents(
            f"record[{_record_id(record)}].report_fee_paid_cents",
            record.get("report_fee_paid_cents"),
        ),
        franchise_due=_parse_date(record.get("franchise_tax_due_date")),
        franchise_paid=_parse_date(record.get("franchise_tax_paid_date")),
        franchise_paid_cents=require_cents(
            f"record[{_record_id(record)}].franchise_tax_paid_cents",
            record.get("franchise_tax_paid_cents"),
        ),
        sos_agent=record.get("sos_agent_name") if isinstance(record.get("sos_agent_name"), str) else "",
        contracted_agent=record.get("contracted_agent_name") if isinstance(record.get("contracted_agent_name"), str) else "",
        agent_fee_paid=_parse_date(record.get("agent_fee_paid_date")),
        license_status=record.get("license_status") if isinstance(record.get("license_status"), str) else "",
        license_due=_parse_date(record.get("license_due_date")),
    )


def _rederived_date(year: int | None, month: object, day: object) -> date | None:
    """Re-derive a statutory due date from ``(year, month, day)``, or ``None``."""
    if not isinstance(year, int) or isinstance(year, bool):
        return None
    if isinstance(month, bool) or not isinstance(month, int):
        return None
    if isinstance(day, bool) or not isinstance(day, int):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def recompute_entity_good_standing(
    ctx: Context,
    entity: dict[str, Any],
    matrix: dict[tuple[str, str], dict[str, Any]],
    as_of: date,
) -> bool:
    """Recompute an entity's good-standing determination from its state records.

    An entity is in good standing when every state it is required to be registered
    in has a record that meets that state's substantive obligations at ``as_of``.
    Shared with the generator through :mod:`standing_engine.standing`, so the
    determination the engine recomputes is the one that produced the data.

    Raises :class:`AmountInvalidError` if a fee it must read is not integer cents;
    the calling control contains that to the entity being read.
    """
    etype = _text(entity, "entity_type")
    eid = _entity_id(entity)
    for state in _required_states(entity):
        row = matrix.get((state, etype or ""))
        if row is None:
            return False
        rec = _record_for(ctx, eid, state)
        if rec is None:
            return False
        ob = _obligation_from_row(row)
        sr = _record_from_row(rec)
        if not record_in_good_standing(sr, ob, as_of):
            return False
    return True


def recompute_watchlist(ctx: Context, as_of: date, lead_days: int) -> list[dict[str, Any]]:
    """The renewal watchlist re-derived from the record evidence.

    One entry per active entity's state record whose *next* report due date falls
    inside the lead-time window. Shared with the generator so the stated watchlist
    can be tied to it. Reads no amounts, so it never raises on a malformed fee.
    """
    entries: list[dict[str, Any]] = []
    for entity in _entities(ctx):
        if not _is_active(entity):
            continue
        eid = _entity_id(entity)
        for state in _required_states(entity):
            rec = _record_for(ctx, eid, state)
            if rec is None:
                continue
            next_due = _parse_date(rec.get("next_report_due_date"))
            if next_due is None:
                continue
            if within_renewal_window(next_due, as_of, lead_days):
                entries.append(
                    {
                        "entity_id": eid,
                        "state": state,
                        "next_report_due_date": rec.get("next_report_due_date"),
                        "days_remaining": (next_due - as_of).days,
                    }
                )
    entries.sort(key=lambda e: (e["entity_id"], e["state"]))
    return entries


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("entity_id"),
        entry.get("state"),
        entry.get("next_report_due_date"),
        entry.get("days_remaining"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the standing file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the standing file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} standing artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every currency and renewal "
                f"test is measured to it",
            )
        )
    if ctx.period_year is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"period_year {ctx.data.get('period_year')!r} is not a whole year; every "
                f"statutory due date is re-derived against it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# ent_ -- the entity register
# --------------------------------------------------------------------------- #
@check("ent_unique_ids")
def check_ent_unique_ids(ctx: Context) -> list[Finding]:
    """No entity id appears twice.

    The entity id joins the register to every state record and to the summary. A
    duplicate makes a record ambiguous about which entity it belongs to.
    """
    rule = "ent_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ENTITY_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _entities(ctx):
        seen[_entity_id(row)] = seen.get(_entity_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"entities/{eid}"),
            f"entity id {eid} appears {count} times; a record that names it cannot be "
            f"attributed to one entity",
        )
        for eid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} entity ids are unique")
        )
    return out


@check("ent_type_valid")
def check_ent_type_valid(ctx: Context) -> list[Finding]:
    """Every entity carries a known entity type.

    The entity type is half the key into the jurisdiction matrix; an unknown one
    has no row, so nothing downstream could say what that entity owed.
    """
    rule = "ent_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ENTITY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _entities(ctx):
        etype = _text(row, "entity_type")
        if etype not in ENTITY_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{_entity_id(row)}/entity_type"),
                    f"entity {_entity_id(row)} is typed {etype!r}, which is not one of "
                    f"{ENTITY_TYPES}; its obligations cannot be looked up",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_entities(ctx))} entities carry a known type"
            )
        )
    return out


@check("ent_status_valid")
def check_ent_status_valid(ctx: Context) -> list[Finding]:
    """Every entity carries a known register status.

    The status is the on/off switch for the whole engine: it decides whether an
    entity carries live filing obligations or must instead be fully cancelled. An
    unknown status leaves that undecided.
    """
    rule = "ent_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ENTITY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _entities(ctx):
        status = _text(row, "status")
        if status not in ENTITY_STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{_entity_id(row)}/status"),
                    f"entity {_entity_id(row)} carries status {status!r}, which is not one "
                    f"of {ENTITY_STATUSES}; whether it owes filings is undecided",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_entities(ctx))} entities carry a known status"
            )
        )
    return out


@check("ent_jurisdictions_declared")
def check_ent_jurisdictions_declared(ctx: Context) -> list[Finding]:
    """Every entity declares a non-empty, known formation/qualified jurisdiction set.

    An empty set is not a compliant entity; it is an entity whose registrations
    were never captured, so every jurisdiction control below would have nothing to
    check and pass vacuously. An unknown state has no statute to test against.
    """
    rule = "ent_jurisdictions_declared"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ENTITY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _entities(ctx):
        eid = _entity_id(row)
        formation = _text(row, "formation_state")
        qualified = row.get("qualified_states")
        declared = ([formation] if formation else []) + (
            qualified if isinstance(qualified, list) else []
        )
        if not _required_states(row):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{eid}/formation_state"),
                    f"entity {eid} declares no known formation or qualified jurisdiction; "
                    f"its jurisdiction controls would pass on an empty requirement",
                )
            )
            continue
        unknown = [s for s in declared if isinstance(s, str) and s and s not in KNOWN_STATES]
        if unknown:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{eid}/qualified_states"),
                    f"entity {eid} is registered in {unknown}, which is not among the "
                    f"known jurisdictions {KNOWN_STATES}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_entities(ctx))} entities declare a known jurisdiction set",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# jur_ -- the required (entity, state) obligations
# --------------------------------------------------------------------------- #
@check("jur_matrix_defined")
def check_jur_matrix_defined(ctx: Context) -> list[Finding]:
    """Every state an active entity belongs to has a matrix row for its type.

    Without the row the engine knows the entity is registered somewhere but not
    what report cadence, fee or franchise tax to hold it to, so the amount and
    date controls would silently skip it. Entities whose type is itself unknown
    are left to ``ent_type_valid``.
    """
    rule = "jur_matrix_defined"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_JURISDICTION_MATRIX)
    if register is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for entity in _entities(ctx):
        if not _is_active(entity):
            continue
        etype = _text(entity, "entity_type")
        if etype not in ENTITY_TYPES:
            continue  # ent_type_valid owns this
        for state in _required_states(entity):
            checked += 1
            if (state, etype) not in matrix:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"requirements/{state}/{etype}"),
                        f"the jurisdiction matrix has no row for {state}/{etype}, which "
                        f"entity {_entity_id(entity)} is registered in; its obligations "
                        f"cannot be tested",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} required jurisdictions have a matrix row"
            )
        )
    return out


@check("jur_record_present")
def check_jur_record_present(ctx: Context) -> list[Finding]:
    """Every state an active entity belongs to has a standing record on file.

    Presence, not currency: a required jurisdiction with no record at all is the
    plainest failure, and lateness is a separate control's job.
    """
    rule = "jur_record_present"
    _sev(rule, Status.FAIL)
    ent_reg = ctx.one(DOC_ENTITY_REGISTER)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if ent_reg is None or rec_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for entity in _entities(ctx):
        if not _is_active(entity):
            continue
        eid = _entity_id(entity)
        for state in _required_states(entity):
            checked += 1
            if _record_for(ctx, eid, state) is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rec_reg, f"records/{eid}/{state}"),
                        f"entity {eid} is registered in {state} but has no good-standing "
                        f"record on file for it",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} required jurisdictions have a record on file",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rec_ -- the standing record register
# --------------------------------------------------------------------------- #
@check("rec_required_fields")
def check_rec_required_fields(ctx: Context) -> list[Finding]:
    """Every record carries the descriptive fields the controls read."""
    rule = "rec_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if register is None:
        return []
    required = ("record_id", "entity_id", "state", "sos_file_number", "sos_status")
    out: list[Finding] = []
    for row in _records(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"records/{_record_id(row)}"),
                    f"record {_record_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_records(ctx))} records carry their required fields",
            )
        )
    return out


@check("rec_file_number_unique")
def check_rec_file_number_unique(ctx: Context) -> list[Finding]:
    """No SOS file number appears on two records.

    A shared file number means one state filing was copied onto two lines or two
    entities, and the register can no longer prove they are distinct registrations.
    """
    rule = "rec_file_number_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _records(ctx):
        number = _text(row, "sos_file_number")
        if number:
            seen[number] = seen.get(number, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"records/sos_file_number/{number}"),
            f"SOS file number {number} appears on {count} records; they cannot both be "
            f"independent evidence of a registration",
        )
        for number, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(seen)} SOS file numbers are unique"
            )
        )
    return out


@check("rec_entity_exists")
def check_rec_entity_exists(ctx: Context) -> list[Finding]:
    """Every record names an entity in the register."""
    rule = "rec_entity_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"records/{_record_id(row)}/entity_id"),
            f"record {_record_id(row)} names entity {_text(row, 'entity_id')!r}, which is "
            f"not in the entity register",
        )
        for row in _records(ctx)
        if _text(row, "entity_id") and _text(row, "entity_id") not in entities
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every record names an entity in the register")
        )
    return out


@check("rec_state_required")
def check_rec_state_required(ctx: Context) -> list[Finding]:
    """Every record's state is one its entity is actually registered in.

    A record for a state outside the entity's formation/qualified set is a stray
    registration -- evidence of an obligation nobody has established the entity
    owes, which would silently pad the good-standing determination.
    """
    rule = "rec_state_required"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    out: list[Finding] = []
    for row in _records(ctx):
        eid = _text(row, "entity_id")
        state = _text(row, "state")
        entity = entities.get(eid or "")
        if entity is None or state is None:
            continue  # rec_entity_exists / rec_required_fields own these
        if state not in _required_states(entity):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"records/{_record_id(row)}/state"),
                    f"record {_record_id(row)} registers entity {eid} in {state}, which is "
                    f"not in its formation/qualified jurisdiction set",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_records(ctx))} records name a jurisdiction the entity belongs to",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# fil_ -- the annual/biennial report
# --------------------------------------------------------------------------- #
def _active_pairs(ctx: Context) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    """``(entity, state, record)`` for every active-entity required jurisdiction
    that has both a matrix row and a record. Iterated by the substantive controls.
    """
    matrix = _matrix(ctx)
    out: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for entity in _entities(ctx):
        if not _is_active(entity):
            continue
        etype = _text(entity, "entity_type")
        eid = _entity_id(entity)
        for state in _required_states(entity):
            row = matrix.get((state, etype or ""))
            if row is None:
                continue  # jur_matrix_defined owns this
            rec = _record_for(ctx, eid, state)
            if rec is None:
                continue  # jur_record_present owns this
            out.append((entity, state, rec))
    return out


@check("fil_due_date_recomputes")
def check_fil_due_date_recomputes(ctx: Context) -> list[Finding]:
    """Each record's stated report due date re-derives from the statute.

    The due date is a determination -- filing year plus the statutory month/day --
    and a stated due date that does not recompute is a date nobody can defend the
    timeliness test against.
    """
    rule = "fil_due_date_recomputes"
    _sev(rule, Status.FAIL)
    matrix_reg = ctx.one(DOC_JURISDICTION_MATRIX)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if matrix_reg is None or rec_reg is None:
        return []
    matrix = _matrix(ctx)
    year = ctx.period_year
    out: list[Finding] = []
    checked = 0
    for entity, state, rec in _active_pairs(ctx):
        etype = _text(entity, "entity_type")
        row = matrix[(state, etype or "")]
        expected = _rederived_date(year, row.get("report_due_month"), row.get("report_due_day"))
        stated = _parse_date(rec.get("report_due_date"))
        if expected is None:
            continue
        checked += 1
        if stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/report_due_date"),
                    f"record {_record_id(rec)} states a report due date of "
                    f"{rec.get('report_due_date')!r}; the {state} statute re-derives "
                    f"{expected.isoformat()} for {year}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} report due dates re-derive from statute")
        )
    return out


@check("fil_report_filed_on_time")
def check_fil_report_filed_on_time(ctx: Context) -> list[Finding]:
    """The annual/biennial report was filed on-or-before its statutory due date.

    Filed on the due date is on time; one day later is late, and a late report is
    the first step toward administrative suspension.
    """
    rule = "fil_report_filed_on_time"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if rec_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for _entity, state, rec in _active_pairs(ctx):
        due = _parse_date(rec.get("report_due_date"))
        filed = _parse_date(rec.get("report_filed_date"))
        checked += 1
        if due is None or filed is None or filed > due:
            when = filed.isoformat() if filed else "never"
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/report_filed_date"),
                    f"record {_record_id(rec)} ({state}) filed its report {when}; the "
                    f"statutory due date is {rec.get('report_due_date')!r} and a report "
                    f"must be filed on-or-before it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} reports were filed on time")
        )
    return out


@check("fil_report_fee_paid")
def check_fil_report_fee_paid(ctx: Context) -> list[Finding]:
    """The report filing fee paid meets the statutory fee. Exact ``>=``."""
    rule = "fil_report_fee_paid"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if rec_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for entity, state, rec in _active_pairs(ctx):
        etype = _text(entity, "entity_type")
        row = matrix[(state, etype or "")]
        with amount_guard(rule, out):
            paid = require_cents(
                f"record[{_record_id(rec)}].report_fee_paid_cents",
                rec.get("report_fee_paid_cents"),
            )
            required = require_cents(
                f"obligation[{state}/{etype}].report_fee_cents", row.get("report_fee_cents")
            )
            checked += 1
            if paid < required:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rec_reg, f"records/{_record_id(rec)}/report_fee_paid_cents"),
                        f"record {_record_id(rec)} ({state}) paid {fmt(paid)} in report fees; "
                        f"the statute requires {fmt(required)} (short {fmt(required - paid)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} report fees meet the statute")
        )
    return out


@check("fil_renewal_lead_time")
def check_fil_renewal_lead_time(ctx: Context) -> list[Finding]:
    """A next report due date inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the entity is still in good standing, but
    the upcoming report needs to be filed before it lapses. The window comes from
    the file's own ``renewal_lead_days``.
    """
    rule = "fil_renewal_lead_time"
    _sev(rule, Status.FLAG)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if rec_reg is None or as_of is None:
        return []
    lead = ctx.renewal_lead_days
    out: list[Finding] = []
    checked = 0
    for _entity, state, rec in _active_pairs(ctx):
        next_due = _parse_date(rec.get("next_report_due_date"))
        if next_due is None:
            continue
        checked += 1
        if within_renewal_window(next_due, as_of, lead):
            remaining = (next_due - as_of).days
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/next_report_due_date"),
                    f"record {_record_id(rec)} ({state}) has its next report due "
                    f"{next_due.isoformat()}, in {remaining} day(s); inside the {lead}-day "
                    f"renewal window and due to be filed",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} next report due dates are outside the renewal window",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# tax_ -- the franchise tax
# --------------------------------------------------------------------------- #
@check("tax_amount_meets")
def check_tax_amount_meets(ctx: Context) -> list[Finding]:
    """The franchise tax paid meets the flat statutory amount. Exact ``>=``.

    A dollar under the flat amount is an unpaid franchise tax: the state does not
    part-credit it, and the shortfall accrues penalty and interest until the
    entity is suspended.
    """
    rule = "tax_amount_meets"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if rec_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for entity, state, rec in _active_pairs(ctx):
        etype = _text(entity, "entity_type")
        row = matrix[(state, etype or "")]
        with amount_guard(rule, out):
            paid = require_cents(
                f"record[{_record_id(rec)}].franchise_tax_paid_cents",
                rec.get("franchise_tax_paid_cents"),
            )
            required = require_cents(
                f"obligation[{state}/{etype}].franchise_tax_cents",
                row.get("franchise_tax_cents"),
            )
            checked += 1
            if paid < required:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rec_reg, f"records/{_record_id(rec)}/franchise_tax_paid_cents"),
                        f"record {_record_id(rec)} ({state}) paid {fmt(paid)} in franchise "
                        f"tax; the statute sets a flat {fmt(required)} "
                        f"(short {fmt(required - paid)})",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} franchise-tax payments meet the statute")
        )
    return out


@check("tax_due_date_recomputes")
def check_tax_due_date_recomputes(ctx: Context) -> list[Finding]:
    """Each record's stated franchise-tax due date re-derives from the statute."""
    rule = "tax_due_date_recomputes"
    _sev(rule, Status.FAIL)
    matrix_reg = ctx.one(DOC_JURISDICTION_MATRIX)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if matrix_reg is None or rec_reg is None:
        return []
    matrix = _matrix(ctx)
    year = ctx.period_year
    out: list[Finding] = []
    checked = 0
    for entity, state, rec in _active_pairs(ctx):
        etype = _text(entity, "entity_type")
        row = matrix[(state, etype or "")]
        expected = _rederived_date(year, row.get("franchise_due_month"), row.get("franchise_due_day"))
        stated = _parse_date(rec.get("franchise_tax_due_date"))
        if expected is None:
            continue
        checked += 1
        if stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/franchise_tax_due_date"),
                    f"record {_record_id(rec)} states a franchise-tax due date of "
                    f"{rec.get('franchise_tax_due_date')!r}; the {state} statute re-derives "
                    f"{expected.isoformat()} for {year}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} franchise-tax due dates re-derive from statute"
            )
        )
    return out


@check("tax_paid_on_time")
def check_tax_paid_on_time(ctx: Context) -> list[Finding]:
    """The franchise tax was paid on-or-before its statutory due date.

    Paid on the due date is on time; one day later is late, and a late franchise
    tax carries the penalty the on-time payment avoids.
    """
    rule = "tax_paid_on_time"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if rec_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for _entity, state, rec in _active_pairs(ctx):
        due = _parse_date(rec.get("franchise_tax_due_date"))
        paid = _parse_date(rec.get("franchise_tax_paid_date"))
        checked += 1
        if due is None or paid is None or paid > due:
            when = paid.isoformat() if paid else "never"
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/franchise_tax_paid_date"),
                    f"record {_record_id(rec)} ({state}) paid its franchise tax {when}; the "
                    f"statutory due date is {rec.get('franchise_tax_due_date')!r} and it "
                    f"must be paid on-or-before it",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} franchise taxes were paid on time")
        )
    return out


# --------------------------------------------------------------------------- #
# agt_ -- the registered agent
# --------------------------------------------------------------------------- #
@check("agt_matches_sos")
def check_agt_matches_sos(ctx: Context) -> list[Finding]:
    """Where required, the agent named on the SOS record is the contracted agent.

    A mismatch means the state will serve process on an agent the family no longer
    retains -- so a lawsuit or a suspension notice lands somewhere nobody is
    watching, and the first the entity hears of it is a default.
    """
    rule = "agt_matches_sos"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if rec_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for entity, state, rec in _active_pairs(ctx):
        etype = _text(entity, "entity_type")
        if not bool(matrix[(state, etype or "")].get("requires_registered_agent")):
            continue
        checked += 1
        sos_agent = _text(rec, "sos_agent_name")
        contracted = _text(rec, "contracted_agent_name")
        if sos_agent != contracted:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/sos_agent_name"),
                    f"record {_record_id(rec)} ({state}) names {sos_agent!r} as agent of "
                    f"record; the contracted agent is {contracted!r}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} agents of record match the contract")
        )
    return out


@check("agt_fee_current")
def check_agt_fee_current(ctx: Context) -> list[Finding]:
    """Where required, the registered agent's annual fee has been paid.

    An unpaid agent resigns, and an entity with no agent of record is one filing
    away from administrative dissolution.
    """
    rule = "agt_fee_current"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if rec_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for entity, state, rec in _active_pairs(ctx):
        etype = _text(entity, "entity_type")
        if not bool(matrix[(state, etype or "")].get("requires_registered_agent")):
            continue
        checked += 1
        if _parse_date(rec.get("agent_fee_paid_date")) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/agent_fee_paid_date"),
                    f"record {_record_id(rec)} ({state}) shows no paid date for the "
                    f"registered-agent fee; an unpaid agent resigns",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} registered-agent fees are paid")
        )
    return out


# --------------------------------------------------------------------------- #
# sts_ -- the good-standing status tie-out
# --------------------------------------------------------------------------- #
@check("sts_sos_active")
def check_sts_sos_active(ctx: Context) -> list[Finding]:
    """An entity the register calls Active reads ACTIVE on every SOS record.

    The register is what the family believes; the SOS record is what the state
    says. When the two disagree -- the register shows Active while the state shows
    the entity suspended -- the family is operating on a status that is no longer
    true.
    """
    rule = "sts_sos_active"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if rec_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for _entity, state, rec in _active_pairs(ctx):
        checked += 1
        sos_status = _text(rec, "sos_status")
        if sos_status != SOS_ACTIVE:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/sos_status"),
                    f"record {_record_id(rec)} ({state}) reads SOS status {sos_status!r} for "
                    f"an entity the register calls {STATUS_ACTIVE!r}; the two must reconcile",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} active entities read ACTIVE at the SOS"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# lic_ -- the business license
# --------------------------------------------------------------------------- #
@check("lic_current")
def check_lic_current(ctx: Context) -> list[Finding]:
    """Where a jurisdiction requires a city business license, it is current.

    The licence must read current and its renewal date must still be ahead of the
    review date: a licence whose renewal date has arrived is due, not current, and
    operating without it is its own violation regardless of state standing.
    """
    rule = "lic_current"
    _sev(rule, Status.FAIL)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if rec_reg is None or as_of is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for entity, state, rec in _active_pairs(ctx):
        etype = _text(entity, "entity_type")
        if not bool(matrix[(state, etype or "")].get("requires_business_license")):
            continue
        checked += 1
        status = _text(rec, "license_status")
        due = _parse_date(rec.get("license_due_date"))
        if status != LICENSE_CURRENT or due is None or due <= as_of:
            shown = due.isoformat() if due else "none"
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(rec_reg, f"records/{_record_id(rec)}/license_status"),
                    f"record {_record_id(rec)} ({state}) shows business licence "
                    f"{status!r} renewing {shown}; it must read current and renew after "
                    f"the review date {as_of.isoformat()}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} required business licences are current")
        )
    return out


# --------------------------------------------------------------------------- #
# dis_ -- dissolution completeness
# --------------------------------------------------------------------------- #
@check("dis_cancellation_complete")
def check_dis_cancellation_complete(ctx: Context) -> list[Finding]:
    """Every dissolved entity is cancelled in every state it ever belonged to.

    A wound-down entity that keeps a live registration in even one state it once
    qualified into keeps accruing that state's franchise tax and report
    obligations -- a dormant liability that surfaces years later as a suspension
    and a bill. The cancellation must be complete across formation and every
    qualified state.
    """
    rule = "dis_cancellation_complete"
    _sev(rule, Status.FAIL)
    ent_reg = ctx.one(DOC_ENTITY_REGISTER)
    rec_reg = ctx.one(DOC_STANDING_RECORD_REGISTER)
    if ent_reg is None or rec_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for entity in _entities(ctx):
        if _text(entity, "status") != STATUS_DISSOLVED:
            continue
        eid = _entity_id(entity)
        for state in _required_states(entity):
            checked += 1
            rec = _record_for(ctx, eid, state)
            if rec is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rec_reg, f"records/{eid}/{state}"),
                        f"dissolved entity {eid} has no cancellation record for {state}, "
                        f"which it belonged to; the registration is still live there",
                    )
                )
            elif not bool(rec.get("cancellation_filed")):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(rec_reg, f"records/{_record_id(rec)}/cancellation_filed"),
                        f"dissolved entity {eid} record {_record_id(rec)} shows no filed "
                        f"certificate of cancellation for {state}; the dissolution is "
                        f"incomplete there",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} dissolved-entity jurisdictions carry a cancellation",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# roll_ -- the rollup recomputes from the evidence
# --------------------------------------------------------------------------- #
@check("roll_standing_recomputes")
def check_roll_standing_recomputes(ctx: Context) -> list[Finding]:
    """Each entity's stated good-standing flag recomputes from its records.

    This is the control the engine exists for. The standing summary is a
    determination, and a determination that is not recomputed from the evidence is
    an assertion. The engine rebuilds every flag from the jurisdiction matrix and
    the state records, and compares.
    """
    rule = "roll_standing_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_STANDING_SUMMARY)
    as_of = _parse_date(ctx.as_of)
    if summary is None or as_of is None:
        return []
    entities = _entity_map(ctx)
    matrix = _matrix(ctx)
    out: list[Finding] = []
    for row in _rows(summary, "entities"):
        eid = _text(row, "entity_id")
        entity = entities.get(eid or "")
        if entity is None:
            continue
        stated = row.get("good_standing")
        with amount_guard(rule, out):
            recomputed = recompute_entity_good_standing(ctx, entity, matrix, as_of)
            if recomputed != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"entities/{eid}/good_standing"),
                        f"entity {eid} is summarised good_standing={stated}; recomputing "
                        f"from its records gives good_standing={recomputed}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every entity good-standing flag recomputes from its records"
            )
        )
    return out


@check("roll_report_counts_tie")
def check_roll_report_counts_tie(ctx: Context) -> list[Finding]:
    """The compliance report's good / not-good counts tie the summary.

    The number that reaches a manager is a count, and a count maintained beside the
    summary rather than derived from it drifts the first time a flag moves and
    nobody re-adds the column.
    """
    rule = "roll_report_counts_tie"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_COMPLIANCE_REPORT)
    summary = ctx.one(DOC_STANDING_SUMMARY)
    if report is None or summary is None:
        return []
    good = 0
    not_good = 0
    for row in _rows(summary, "entities"):
        value = row.get("good_standing")
        if value is True:
            good += 1
        elif value is False:
            not_good += 1
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_good = require_cents(
            "compliance_report.good_standing_count",
            report.get("good_standing_count"),
            unit="a whole count",
        )
        stated_not_good = require_cents(
            "compliance_report.not_in_good_standing_count",
            report.get("not_in_good_standing_count"),
            unit="a whole count",
        )
        if stated_good != good or stated_not_good != not_good:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "good_standing_count"),
                    f"the report states {stated_good} in good standing / {stated_not_good} "
                    f"not; the summary recomputes {good} / {not_good}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report counts of {good} / {not_good} tie the summary",
                )
            )
    return out


@check("roll_watchlist_ties")
def check_roll_watchlist_ties(ctx: Context) -> list[Finding]:
    """The renewal watchlist ties the record evidence.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a filing not actually due -- or omits one that is --
    sends the filing chase to the wrong place. It is rebuilt from the records and
    compared.
    """
    rule = "roll_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_RENEWAL_WATCHLIST)
    as_of = _parse_date(ctx.as_of)
    if watchlist is None or as_of is None:
        return []
    recomputed = [_normalize_entry(e) for e in recompute_watchlist(ctx, as_of, ctx.renewal_lead_days)]
    stated = [_normalize_entry(e) for e in _rows(watchlist, "entries")]
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
                        ctx.loc(watchlist, f"entries/{entry[0]}/{entry[1]}"),
                        f"the watchlist lists {entry[0]} ({entry[1]}) as due for renewal, "
                        f"but it is not inside the lead-time window as of {as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}/{entry[1]}"),
                        f"{entry[0]} ({entry[1]}) is due for renewal within the lead-time "
                        f"window but is not on the watchlist",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "the renewal watchlist ties the record evidence"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one standing file."""
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
    """Analyze every ``.json`` standing file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of standing-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
