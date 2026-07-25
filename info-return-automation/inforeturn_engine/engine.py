"""
Information-return issuance control engine (READ-ONLY).
=======================================================

Loads each reporting file (a ``.json`` file produced by
:mod:`inforeturn_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the forms about to be issued match the ledger**,
not whether a payment should have been made. Approving and releasing a
disbursement is a separate engine's job, and that engine explicitly declines to
ask whether the payment it released was reportable. This engine is that question,
run once a year over the whole payee population.

The shape of the problem
------------------------
Every year the group reassembles, entity by entity, the payees it paid something
reportable to -- interest to lenders and affiliates, non-employee compensation to
vendors, card and third-party settlement -- applies the box threshold, issues a
form, and reconciles each box back to the payment lines it came from.

Three failures hide inside that, and none of them look wrong in a ledger that was
never organised around who has to receive a form: the payee who clears a
threshold in one entity and is never cut a form, or who has no taxpayer number on
file and has nothing withheld; the box amount re-keyed from a summary rather than
footed from the entity's own payment lines; and the transmittal whose count or
total is maintained beside the register rather than footed from it.

The registry is organised around that:

1. ``set_`` -- is the reporting file complete?
2. ``ent_`` -- is the payer entity register sound and identified?
3. ``pye_`` -- is the payee population sound, and are its taxpayer numbers readable?
4. ``box_`` -- is the box catalog defined once and only once per box?
5. ``led_`` -- is every payment line attributable, integral, and inside the year?
6. ``frm_`` -- is every form well-formed, attributed, unduplicated, and tied to the ledger?
7. ``thr_`` -- is a form issued exactly where one is owed, and what sits just under?
8. ``bwh_`` -- does backup withholding recompute at the statutory rate?
9. ``rpt_`` -- do the transmittals and the annual rollup foot the forms?

Design notes
------------
- **Strictly read-only.** Reporting files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tie-out is compared with exact ``==``.
- **One issuance predicate.** Controls and the generator share the kernel in
  :mod:`inforeturn_engine.issuance`, so a form cannot disagree with the data that
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

from .issuance import (
    BoxRule,
    backup_withholding_cents,
    form_required,
    near_threshold_shortfall,
    paid_in_year,
    tin_well_formed,
)
from .model import (
    DOC_BOX_CATALOG,
    DOC_ENTITY_REGISTER,
    DOC_FORM_REGISTER,
    DOC_ISSUANCE_REPORT,
    DOC_LEDGER_EXTRACT,
    DOC_PAYEE_REGISTER,
    DOC_THRESHOLD_WATCHLIST,
    DOC_TRANSMITTAL_REGISTER,
    DOC_TYPES,
    FORM_TYPES,
    PAYEE_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}

#: ``(entity_id, payee_id, form_type, box_code)`` -- the grain at which an
#: information return reconciles to the ledger, and the natural key of a form.
FormKey = tuple[str, str, str, str]


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~inforeturn_engine.money.AmountInvalidError` as a finding."""
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
# Reporting-file helpers
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


def _tin_present(payee: dict[str, Any] | None) -> bool:
    """Whether a payee has a taxpayer number on file at all.

    Presence, not shape: a malformed number is still a number somebody captured,
    and ``pye_tin_wellformed`` owns its shape. What drives backup withholding is
    the absence of one.
    """
    if payee is None:
        # An unresolvable payee is ``led_rows_attributable``'s finding. This
        # predicate declines to manufacture a withholding obligation for a payee
        # it cannot identify.
        return True
    return _text(payee, "payee_tin") is not None


def _catalog_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_BOX_CATALOG), "boxes")


def _box_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_text(row, "form_type") or "?", _text(row, "box_code") or "?")


def _catalog(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _catalog_rows(ctx):
        key = _box_key(row)
        if "?" not in key and key not in out:
            out[key] = row
    return out


def _box_rule(row: dict[str, Any]) -> BoxRule:
    """Read a catalog row into a :class:`~inforeturn_engine.issuance.BoxRule`.

    Raises :class:`AmountInvalidError` if the threshold is not integer cents.
    """
    form_type, box_code = _box_key(row)
    return BoxRule(
        threshold_cents=require_cents(
            f"box[{form_type}/{box_code}].threshold_cents", row.get("threshold_cents")
        ),
        withholding_applies=bool(row.get("withholding_applies")),
    )


def _payments(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_LEDGER_EXTRACT), "payments")


def _payment_id(row: dict[str, Any]) -> str:
    value = row.get("payment_id")
    return value if isinstance(value, str) and value else "?"


def _forms(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_FORM_REGISTER), "forms")


def _form_id(row: dict[str, Any]) -> str:
    value = row.get("form_id")
    return value if isinstance(value, str) and value else "?"


def _key_of(row: dict[str, Any]) -> FormKey:
    """The ``(entity, payee, form_type, box)`` key a payment or form belongs to."""
    return (
        _text(row, "entity_id") or "?",
        _text(row, "payee_id") or "?",
        _text(row, "form_type") or "?",
        _text(row, "box_code") or "?",
    )


def _transmittals(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TRANSMITTAL_REGISTER), "transmittals")


def _watchlist_entries(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_THRESHOLD_WATCHLIST), "entries")


# --------------------------------------------------------------------------- #
# Re-derivation, shared with the generator
# --------------------------------------------------------------------------- #
def recompute_box_totals(ctx: Context) -> dict[FormKey, int]:
    """The ledger total for every ``(entity, payee, form_type, box)`` key.

    This is the figure an information return is supposed to report, footed from
    the entity's own payment lines rather than read back from a summary. Keys are
    returned in sorted order so every consumer iterates identically.

    Raises :class:`AmountInvalidError` if a payment amount is not integer cents.
    """
    totals: dict[FormKey, int] = {}
    for row in _payments(ctx):
        key = _key_of(row)
        amount = require_cents(
            f"payment[{_payment_id(row)}].amount_cents", row.get("amount_cents")
        )
        totals[key] = totals.get(key, 0) + amount
    return {key: totals[key] for key in sorted(totals)}


def recompute_expected_forms(ctx: Context) -> list[dict[str, Any]]:
    """Every form the ledger obliges, re-derived through the shared kernel.

    One entry per ``(entity, payee, form_type, box)`` key whose year total meets
    its box threshold, plus every key where backup withholding attaches because
    the payee has no taxpayer number on file. Keys whose box is not in the catalog
    are skipped -- ``led_rows_attributable`` owns an unknown box, and a threshold
    that was never defined cannot be applied.

    Shared with the generator, so the form set the engine expects is the one that
    produced the register. Raises :class:`AmountInvalidError` if an amount or a
    threshold it must read is not integer cents.
    """
    catalog = _catalog(ctx)
    payees = _payee_map(ctx)
    rate = ctx.backup_withholding_bps
    out: list[dict[str, Any]] = []
    for key, total in recompute_box_totals(ctx).items():
        entity_id, payee_id, form_type, box_code = key
        row = catalog.get((form_type, box_code))
        if row is None:
            continue
        rule = _box_rule(row)
        tin_present = _tin_present(payees.get(payee_id))
        if not form_required(total, rule, tin_present):
            continue
        out.append(
            {
                "entity_id": entity_id,
                "payee_id": payee_id,
                "form_type": form_type,
                "box_code": box_code,
                "box_amount_cents": total,
                "backup_withholding_cents": backup_withholding_cents(
                    total, rule, tin_present, rate
                ),
            }
        )
    return out


def recompute_watchlist(ctx: Context) -> list[dict[str, Any]]:
    """The near-threshold watchlist re-derived from the ledger.

    One entry per key that owes no form but sits inside the file's own review
    band below its threshold. Shared with the generator so the stated watchlist
    can be tied to it.

    Raises :class:`AmountInvalidError` if an amount or a threshold it must read is
    not integer cents.
    """
    catalog = _catalog(ctx)
    payees = _payee_map(ctx)
    band = ctx.near_threshold_cents
    out: list[dict[str, Any]] = []
    for key, total in recompute_box_totals(ctx).items():
        entity_id, payee_id, form_type, box_code = key
        row = catalog.get((form_type, box_code))
        if row is None:
            continue
        rule = _box_rule(row)
        shortfall = near_threshold_shortfall(
            total, rule, _tin_present(payees.get(payee_id)), band
        )
        if shortfall is None:
            continue
        out.append(
            {
                "entity_id": entity_id,
                "payee_id": payee_id,
                "form_type": form_type,
                "box_code": box_code,
                "amount_cents": total,
                "shortfall_cents": shortfall,
            }
        )
    return out


def recompute_transmittal(ctx: Context, entity_id: str) -> tuple[int, int, int]:
    """An entity's transmittal footed from the forms actually in the register.

    Returns ``(form_count, total_reported_cents, total_withheld_cents)``. Footed
    from the stated forms rather than from the ledger on purpose: the transmittal
    accompanies the forms that go out, so it has to foot *them*, and whether those
    forms are the right ones is a separate control's question.

    Raises :class:`AmountInvalidError` if a form amount is not integer cents.
    """
    count = 0
    reported = 0
    withheld = 0
    for form in _forms(ctx):
        if _text(form, "entity_id") != entity_id:
            continue
        count += 1
        reported += require_cents(
            f"form[{_form_id(form)}].box_amount_cents", form.get("box_amount_cents")
        )
        withheld += require_cents(
            f"form[{_form_id(form)}].backup_withholding_cents",
            form.get("backup_withholding_cents"),
        )
    return count, reported, withheld


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("entity_id"),
        entry.get("payee_id"),
        entry.get("form_type"),
        entry.get("box_code"),
        entry.get("amount_cents"),
        entry.get("shortfall_cents"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the reporting file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the reporting file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} issuance artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; the issuance cycle is "
                f"reviewed as at that date",
            )
        )
    if ctx.reporting_year is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"reporting_year {ctx.data.get('reporting_year')!r} is not a readable "
                f"year; the payee population is assembled for one calendar year and "
                f"every payment date is tested against it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# ent_ -- the payer entities
# --------------------------------------------------------------------------- #
@check("ent_unique_ids")
def check_ent_unique_ids(ctx: Context) -> list[Finding]:
    """No payer entity id appears twice.

    The entity id joins the register to every payment line, every form and every
    transmittal. A duplicate makes a form ambiguous about which entity issued it.
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
            f"entity id {eid} appears {count} times; a form that names it cannot be "
            f"attributed to one payer",
        )
        for eid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} payer entity ids are unique")
        )
    return out


@check("ent_payer_identity")
def check_ent_payer_identity(ctx: Context) -> list[Finding]:
    """Every payer entity carries a name and a well-formed taxpayer number.

    This is the identity every form printed in that entity's name inherits, so it
    is checked once at the register and tied to the form by
    ``frm_payer_identity``. An unreadable payer number is a return the authority
    cannot associate with a filer.
    """
    rule = "ent_payer_identity"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ENTITY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _entities(ctx):
        eid = _entity_id(row)
        if _text(row, "entity_name") is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{eid}/entity_name"),
                    f"payer entity {eid} carries no name; every form issued in its name "
                    f"would go out unattributed",
                )
            )
        tin = row.get("payer_tin")
        if not tin_well_formed(tin):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{eid}/payer_tin"),
                    f"payer entity {eid} carries taxpayer number {tin!r}, which is not a "
                    f"well-formed identifier; the returns it issues cannot be associated "
                    f"with a filer",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_entities(ctx))} payer entities are named and identified",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# pye_ -- the payee population
# --------------------------------------------------------------------------- #
@check("pye_unique_ids")
def check_pye_unique_ids(ctx: Context) -> list[Finding]:
    """No payee id appears twice.

    The payee population is reassembled from scratch every year, and the same
    vendor entered twice is the ordinary way one payee ends up with two partial
    year totals and two understated forms.
    """
    rule = "pye_unique_ids"
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
            f"payee id {pid} appears {count} times; the year total for that payee can "
            f"be split across the duplicates and understate every box",
        )
        for pid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} payee ids are unique"))
    return out


@check("pye_type_valid")
def check_pye_type_valid(ctx: Context) -> list[Finding]:
    """Every payee carries a known payee class.

    The class does not set the threshold -- the box does -- but a payee whose
    class is unknown is one whose reporting treatment nobody decided, and it is
    the population, not the ledger, that has to prove somebody did.
    """
    rule = "pye_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _payees(ctx):
        ptype = _text(row, "payee_type")
        if ptype not in PAYEE_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payees/{_payee_id(row)}/payee_type"),
                    f"payee {_payee_id(row)} is classed {ptype!r}, which is not one of "
                    f"{PAYEE_TYPES}; its reporting treatment was never decided",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_payees(ctx))} payees carry a known class"
            )
        )
    return out


@check("pye_tin_wellformed")
def check_pye_tin_wellformed(ctx: Context) -> list[Finding]:
    """Where a payee taxpayer number is on file, it is well-formed.

    A payee with **no** number is not an exception here: that is the condition
    backup withholding exists for, and ``bwh_rate_recomputes`` owns it. What is an
    exception is a number that was captured and cannot be read, because it will be
    treated as present, suppress the withholding, and print on the form unusable.
    """
    rule = "pye_tin_wellformed"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PAYEE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payees(ctx):
        raw = row.get("payee_tin")
        if raw is None:
            continue  # withheld against instead; bwh_rate_recomputes owns this
        checked += 1
        if not tin_well_formed(raw):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"payees/{_payee_id(row)}/payee_tin"),
                    f"payee {_payee_id(row)} carries taxpayer number {raw!r}, which is not "
                    f"a well-formed identifier; it counts as on file, suppresses backup "
                    f"withholding, and prints on the form unusable",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} taxpayer numbers on file are well-formed",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# box_ -- the reportable boxes and their thresholds
# --------------------------------------------------------------------------- #
@check("box_catalog_defined")
def check_box_catalog_defined(ctx: Context) -> list[Finding]:
    """Every catalog row names a known return series and a usable threshold.

    The threshold is what decides whether a payee is reported at all, so a row
    with an unknown series or a threshold that is not a non-negative integer-cent
    figure cannot be applied to anything.
    """
    rule = "box_catalog_defined"
    _sev(rule, Status.FAIL)
    catalog = ctx.one(DOC_BOX_CATALOG)
    if catalog is None:
        return []
    out: list[Finding] = []
    for row in _catalog_rows(ctx):
        form_type, box_code = _box_key(row)
        if form_type not in FORM_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(catalog, f"boxes/{form_type}/{box_code}/form_type"),
                    f"box {box_code} is catalogued under return series {form_type!r}, "
                    f"which is not one of {FORM_TYPES}; no form of that series can be "
                    f"issued",
                )
            )
        with amount_guard(rule, out):
            threshold = require_cents(
                f"box[{form_type}/{box_code}].threshold_cents", row.get("threshold_cents")
            )
            if threshold < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(catalog, f"boxes/{form_type}/{box_code}/threshold_cents"),
                        f"box {form_type}/{box_code} carries a threshold of "
                        f"{fmt(threshold)}; a negative threshold reports every payee and "
                        f"decides nothing",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_catalog_rows(ctx))} catalogued boxes carry a known series and "
                f"a usable threshold",
            )
        )
    return out


@check("box_catalog_unique")
def check_box_catalog_unique(ctx: Context) -> list[Finding]:
    """No box is catalogued twice.

    Two rows for one box means two thresholds, and whichever is read first decides
    the population -- silently, and differently from whichever a reader would have
    picked.
    """
    rule = "box_catalog_unique"
    _sev(rule, Status.FAIL)
    catalog = ctx.one(DOC_BOX_CATALOG)
    if catalog is None:
        return []
    seen: dict[tuple[str, str], int] = {}
    for row in _catalog_rows(ctx):
        key = _box_key(row)
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(catalog, f"boxes/{key[0]}/{key[1]}"),
            f"box {key[0]}/{key[1]} is catalogued {count} times; the threshold applied to "
            f"the population is whichever row is read first",
        )
        for key, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} catalogued boxes are defined once")
        )
    return out


# --------------------------------------------------------------------------- #
# led_ -- the ledger extract
# --------------------------------------------------------------------------- #
@check("led_rows_attributable")
def check_led_rows_attributable(ctx: Context) -> list[Finding]:
    """Every payment line names an entity, a payee and a catalogued box.

    A line that cannot be attributed cannot reach a form. It does not fail loudly
    either -- it simply never joins a total, so the payee it belonged to is
    under-reported by exactly the amount nobody could place.
    """
    rule = "led_rows_attributable"
    _sev(rule, Status.FAIL)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    if extract is None:
        return []
    entities = _entity_map(ctx)
    payees = _payee_map(ctx)
    catalog = _catalog(ctx)
    out: list[Finding] = []
    for row in _payments(ctx):
        pay_id = _payment_id(row)
        entity_id, payee_id, form_type, box_code = _key_of(row)
        if entity_id not in entities:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(extract, f"payments/{pay_id}/entity_id"),
                    f"payment {pay_id} is booked to entity {entity_id!r}, which is not in "
                    f"the payer entity register; no entity would issue its form",
                )
            )
        if payee_id not in payees:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(extract, f"payments/{pay_id}/payee_id"),
                    f"payment {pay_id} is booked to payee {payee_id!r}, which is not in "
                    f"the payee register; the amount joins no year total and the payee is "
                    f"under-reported by it",
                )
            )
        if (form_type, box_code) not in catalog:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(extract, f"payments/{pay_id}/box_code"),
                    f"payment {pay_id} is coded to box {form_type}/{box_code}, which is "
                    f"not in the box catalog; no threshold exists to test it against",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_payments(ctx))} payment lines are attributable to an entity, a "
                f"payee and a catalogued box",
            )
        )
    return out


@check("led_amounts_valid")
def check_led_amounts_valid(ctx: Context) -> list[Finding]:
    """Every payment line carries a non-negative integer-cent amount.

    A return reports what was paid in the year, and a box cannot report a negative
    figure. A reversal belongs netted against the payment it reverses at source,
    where the ledger can prove which payment that was -- not carried into the
    population as a line of its own.
    """
    rule = "led_amounts_valid"
    _sev(rule, Status.FAIL)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    if extract is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payments(ctx):
        pay_id = _payment_id(row)
        with amount_guard(rule, out):
            amount = require_cents(
                f"payment[{pay_id}].amount_cents", row.get("amount_cents")
            )
            checked += 1
            if amount < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(extract, f"payments/{pay_id}/amount_cents"),
                        f"payment {pay_id} carries {fmt(amount)}; a reversal has to be "
                        f"netted against the payment it reverses before the population is "
                        f"assembled, not reported as a negative box",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} payment amounts are non-negative cents"
            )
        )
    return out


@check("led_payment_in_year")
def check_led_payment_in_year(ctx: Context) -> list[Finding]:
    """Every payment line falls inside the reporting year.

    The population is a calendar-year population. A payment dated outside it is
    either reported in the wrong year or double-counted in two, and both are
    invisible once the totals are struck.
    """
    rule = "led_payment_in_year"
    _sev(rule, Status.FAIL)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    start = ctx.year_start
    end = ctx.year_end
    if extract is None or start is None or end is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _payments(ctx):
        pay_id = _payment_id(row)
        paid = _parse_date(row.get("paid_date"))
        if paid is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(extract, f"payments/{pay_id}/paid_date"),
                    f"payment {pay_id} carries paid_date {row.get('paid_date')!r}, which is "
                    f"not a readable date; it cannot be placed in a reporting year",
                )
            )
            continue
        checked += 1
        if not paid_in_year(paid, start, end):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(extract, f"payments/{pay_id}/paid_date"),
                    f"payment {pay_id} is dated {paid.isoformat()}, outside the reporting "
                    f"year {start.isoformat()} to {end.isoformat()}; it belongs to another "
                    f"year's population",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} payment dates fall inside the reporting year",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# frm_ -- the form register
# --------------------------------------------------------------------------- #
@check("frm_required_fields")
def check_frm_required_fields(ctx: Context) -> list[Finding]:
    """Every form carries the fields the controls read, and names a real payer
    and payee.

    A form missing its issue date or pointing at a payee nobody can find is not a
    form; it is a row that will still be counted on a transmittal.
    """
    rule = "frm_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FORM_REGISTER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    payees = _payee_map(ctx)
    required = (
        "form_id",
        "entity_id",
        "payee_id",
        "form_type",
        "box_code",
        "payer_name",
        "payer_tin",
        "issue_date",
    )
    out: list[Finding] = []
    for row in _forms(ctx):
        form_id = _form_id(row)
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{form_id}"),
                    f"form {form_id} is missing {', '.join(missing)}",
                )
            )
        if _text(row, "issue_date") and _parse_date(row.get("issue_date")) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{form_id}/issue_date"),
                    f"form {form_id} carries issue_date {row.get('issue_date')!r}, which is "
                    f"not a readable date",
                )
            )
        entity_id = _text(row, "entity_id")
        if entity_id and entity_id not in entities:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{form_id}/entity_id"),
                    f"form {form_id} is issued by entity {entity_id!r}, which is not in the "
                    f"payer entity register",
                )
            )
        payee_id = _text(row, "payee_id")
        if payee_id and payee_id not in payees:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{form_id}/payee_id"),
                    f"form {form_id} is issued to payee {payee_id!r}, which is not in the "
                    f"payee register",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_forms(ctx))} forms are complete and attributable",
            )
        )
    return out


@check("frm_payer_identity")
def check_frm_payer_identity(ctx: Context) -> list[Finding]:
    """The payer name and taxpayer number printed on a form are the entity's own.

    The form is what the payee and the authority see, and it carries the payer
    identity as printed text rather than as a reference. Re-keyed text drifts: a
    form issued by one entity can go out carrying another entity's number and
    still look complete. The register is the source; ``ent_payer_identity`` proves
    the register itself is readable.
    """
    rule = "frm_payer_identity"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FORM_REGISTER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _forms(ctx):
        form_id = _form_id(row)
        entity = entities.get(_text(row, "entity_id") or "")
        if entity is None:
            continue  # frm_required_fields owns this
        checked += 1
        stated_name = _text(row, "payer_name")
        expected_name = _text(entity, "entity_name")
        if stated_name != expected_name:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{form_id}/payer_name"),
                    f"form {form_id} prints payer name {stated_name!r}; entity "
                    f"{_entity_id(entity)} is registered as {expected_name!r}",
                )
            )
        stated_tin = _text(row, "payer_tin")
        expected_tin = _text(entity, "payer_tin")
        if stated_tin != expected_tin:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{form_id}/payer_tin"),
                    f"form {form_id} prints payer taxpayer number {stated_tin!r}; entity "
                    f"{_entity_id(entity)} is registered as {expected_tin!r}, so the return "
                    f"would be filed under the wrong payer",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} forms print the payer identity their entity is registered "
                f"under",
            )
        )
    return out


@check("frm_no_duplicates")
def check_frm_no_duplicates(ctx: Context) -> list[Finding]:
    """No two forms cover the same entity, payee, series and box.

    A form reconciles at that grain, so two of them report the same year total
    twice. The payee receives contradictory statements and the transmittal foots
    to double the ledger while footing perfectly to the register.
    """
    rule = "frm_no_duplicates"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FORM_REGISTER)
    if register is None:
        return []
    seen: dict[FormKey, list[str]] = {}
    for row in _forms(ctx):
        seen.setdefault(_key_of(row), []).append(_form_id(row))
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"forms/{key[0]}/{key[1]}/{key[2]}/{key[3]}"),
            f"forms {', '.join(sorted(ids))} all report entity {key[0]} payee {key[1]} "
            f"box {key[2]}/{key[3]}; the same year total would be reported "
            f"{len(ids)} times",
        )
        for key, ids in seen.items()
        if len(ids) > 1
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(seen)} entity/payee/box combinations carry exactly one form",
            )
        )
    return out


@check("frm_box_ties_ledger")
def check_frm_box_ties_ledger(ctx: Context) -> list[Finding]:
    """Each form's box amount equals the entity's ledger total for that payee and box.

    This is the control the engine exists for. The box is the number the payee is
    told and the authority receives, and a box footed from anything other than the
    entity's own payment lines is a number nobody can point at a ledger for.
    Compared with exact ``==``: there is no tolerance on a reported amount.
    """
    rule = "frm_box_ties_ledger"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FORM_REGISTER)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    if register is None or extract is None:
        return []
    totals = recompute_box_totals(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _forms(ctx):
        form_id = _form_id(row)
        key = _key_of(row)
        with amount_guard(rule, out):
            stated = require_cents(
                f"form[{form_id}].box_amount_cents", row.get("box_amount_cents")
            )
            expected = totals.get(key, 0)
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"forms/{form_id}/box_amount_cents"),
                        f"form {form_id} reports {fmt(stated)} in box {key[2]}/{key[3]} for "
                        f"payee {key[1]}; entity {key[0]} ledger lines for that box total "
                        f"{fmt(expected)} (difference {fmt(stated - expected)})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} form boxes tie the entity ledger total"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# thr_ -- the threshold decides who gets a form
# --------------------------------------------------------------------------- #
@check("thr_required_form_issued")
def check_thr_required_form_issued(ctx: Context) -> list[Finding]:
    """Every payee/box that owes a form has one.

    Completeness, and the failure the annual cycle is most exposed to. A payee
    that clears the threshold and is never cut a form leaves nothing behind in the
    ledger to notice: the payments posted, the invoices closed, and the omission
    exists only in the population nobody re-ran.
    """
    rule = "thr_required_form_issued"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FORM_REGISTER)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    catalog = ctx.one(DOC_BOX_CATALOG)
    if register is None or extract is None or catalog is None:
        return []
    issued = {_key_of(row) for row in _forms(ctx)}
    expected = recompute_expected_forms(ctx)
    out: list[Finding] = []
    for entry in expected:
        key: FormKey = (
            entry["entity_id"],
            entry["payee_id"],
            entry["form_type"],
            entry["box_code"],
        )
        if key not in issued:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{key[0]}/{key[1]}/{key[2]}/{key[3]}"),
                    f"entity {key[0]} paid payee {key[1]} {fmt(entry['box_amount_cents'])} "
                    f"in box {key[2]}/{key[3]}, which obliges a return, and no form is on "
                    f"the register",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(expected)} payee/box totals that oblige a return have one",
            )
        )
    return out


@check("thr_no_unrequired_form")
def check_thr_no_unrequired_form(ctx: Context) -> list[Finding]:
    """No form is issued where none is owed.

    The exact complement of the completeness control, and not a harmless excess: a
    form below the threshold with nothing withheld reports a payee who was not
    reportable, and the payee has to reconcile a statement against a return that
    should never have been filed. A below-threshold form **is** owed where backup
    withholding was taken, because withheld tax is reported whatever the payment.
    """
    rule = "thr_no_unrequired_form"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FORM_REGISTER)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    catalog_doc = ctx.one(DOC_BOX_CATALOG)
    if register is None or extract is None or catalog_doc is None:
        return []
    totals = recompute_box_totals(ctx)
    catalog = _catalog(ctx)
    payees = _payee_map(ctx)
    out: list[Finding] = []
    checked = 0
    seen: set[FormKey] = set()
    for row in _forms(ctx):
        key = _key_of(row)
        if key in seen:
            continue  # frm_no_duplicates owns this
        seen.add(key)
        entity_id, payee_id, form_type, box_code = key
        catalog_row = catalog.get((form_type, box_code))
        if catalog_row is None:
            continue  # led_rows_attributable owns an uncatalogued box
        rule_row = _box_rule(catalog_row)
        total = totals.get(key, 0)
        checked += 1
        if not form_required(total, rule_row, _tin_present(payees.get(payee_id))):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"forms/{_form_id(row)}"),
                    f"form {_form_id(row)} reports payee {payee_id} for box "
                    f"{form_type}/{box_code}, where entity {entity_id} paid {fmt(total)} "
                    f"against a threshold of {fmt(rule_row.threshold_cents)} and no backup "
                    f"withholding attaches; the payee was not reportable",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} issued forms are owed under the catalog"
            )
        )
    return out


@check("thr_near_threshold_review")
def check_thr_near_threshold_review(ctx: Context) -> list[Finding]:
    """A payee sitting just under a box threshold is held for review.

    Deliberately a FLAG, not a failure: no form is owed today. But a payee this
    close tips over the moment a late invoice posts to the year, and the band is
    where the cycle is re-run rather than re-opened after the forms have gone out.
    The band comes from the file's own ``near_threshold_cents``.
    """
    rule = "thr_near_threshold_review"
    _sev(rule, Status.FLAG)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    catalog = ctx.one(DOC_BOX_CATALOG)
    if extract is None or catalog is None:
        return []
    band = ctx.near_threshold_cents
    entries = recompute_watchlist(ctx)
    out = [
        Finding(
            rule,
            Status.FLAG,
            ctx.loc(extract, f"payments/{e['entity_id']}/{e['payee_id']}/{e['box_code']}"),
            f"entity {e['entity_id']} paid payee {e['payee_id']} "
            f"{fmt(e['amount_cents'])} in box {e['form_type']}/{e['box_code']}, "
            f"{fmt(e['shortfall_cents'])} under the threshold and inside the "
            f"{fmt(band)} review band; a late invoice posting to the year makes it "
            f"reportable",
        )
        for e in entries
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"no payee/box total sits inside the {fmt(band)} review band below its "
                f"threshold",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# bwh_ -- backup withholding
# --------------------------------------------------------------------------- #
@check("bwh_rate_recomputes")
def check_bwh_rate_recomputes(ctx: Context) -> list[Finding]:
    """Backup withholding on every form recomputes at the statutory rate.

    Both directions, from one re-derivation. Where the box attracts withholding
    and the payee has no taxpayer number on file, the statutory rate is applied to
    the reported amount and the form has to carry it -- the tax is the group's
    liability whether or not it was taken. Where a number **is** on file, the
    correct figure is zero, and withholding taken anyway is the payee's money held
    without cause.
    """
    rule = "bwh_rate_recomputes"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FORM_REGISTER)
    catalog_doc = ctx.one(DOC_BOX_CATALOG)
    if register is None or catalog_doc is None:
        return []
    catalog = _catalog(ctx)
    payees = _payee_map(ctx)
    rate = ctx.backup_withholding_bps
    out: list[Finding] = []
    checked = 0
    for row in _forms(ctx):
        form_id = _form_id(row)
        _entity, payee_id, form_type, box_code = _key_of(row)
        catalog_row = catalog.get((form_type, box_code))
        if catalog_row is None:
            continue  # led_rows_attributable owns an uncatalogued box
        payee = payees.get(payee_id)
        if payee is None:
            continue  # frm_required_fields owns this
        with amount_guard(rule, out):
            box_rule = _box_rule(catalog_row)
            reported = require_cents(
                f"form[{form_id}].box_amount_cents", row.get("box_amount_cents")
            )
            stated = require_cents(
                f"form[{form_id}].backup_withholding_cents",
                row.get("backup_withholding_cents"),
            )
            tin_present = _tin_present(payee)
            expected = backup_withholding_cents(reported, box_rule, tin_present, rate)
            checked += 1
            if stated != expected:
                reason = (
                    "no taxpayer number is on file for the payee"
                    if not tin_present
                    else "the payee has a taxpayer number on file"
                )
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"forms/{form_id}/backup_withholding_cents"),
                        f"form {form_id} carries {fmt(stated)} of backup withholding on "
                        f"{fmt(reported)} reported; {reason}, so the statutory "
                        f"{fmt_bps(rate)} rate recomputes {fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} forms carry backup withholding that recomputes at "
                f"{fmt_bps(rate)}",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the transmittals and the annual rollup foot the forms
# --------------------------------------------------------------------------- #
@check("rpt_transmittal_foots")
def check_rpt_transmittal_foots(ctx: Context) -> list[Finding]:
    """Each entity's transmittal foots the forms it accompanies.

    The transmittal is the one page the authority reads before the forms behind
    it, and a count or a total maintained beside the register rather than footed
    from it drifts the first time a form moves and nobody re-adds the column. Every
    entity with forms carries exactly one.
    """
    rule = "rpt_transmittal_foots"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_TRANSMITTAL_REGISTER)
    form_doc = ctx.one(DOC_FORM_REGISTER)
    if register is None or form_doc is None:
        return []
    out: list[Finding] = []
    stated_entities: dict[str, int] = {}
    for row in _transmittals(ctx):
        entity_id = _text(row, "entity_id") or "?"
        stated_entities[entity_id] = stated_entities.get(entity_id, 0) + 1
        with amount_guard(rule, out):
            count, reported, withheld = recompute_transmittal(ctx, entity_id)
            stated_count = require_cents(
                f"transmittal[{entity_id}].form_count",
                row.get("form_count"),
                unit="a whole count",
            )
            stated_reported = require_cents(
                f"transmittal[{entity_id}].total_reported_cents",
                row.get("total_reported_cents"),
            )
            stated_withheld = require_cents(
                f"transmittal[{entity_id}].total_withheld_cents",
                row.get("total_withheld_cents"),
            )
            if (stated_count, stated_reported, stated_withheld) != (
                count,
                reported,
                withheld,
            ):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"transmittals/{entity_id}"),
                        f"entity {entity_id} transmits {stated_count} form(s) reporting "
                        f"{fmt(stated_reported)} with {fmt(stated_withheld)} withheld; the "
                        f"forms on the register foot to {count} form(s) reporting "
                        f"{fmt(reported)} with {fmt(withheld)} withheld",
                    )
                )
    for entity_id in sorted({_key_of(f)[0] for f in _forms(ctx)}):
        if stated_entities.get(entity_id, 0) != 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"transmittals/{entity_id}"),
                    f"entity {entity_id} has forms on the register and "
                    f"{stated_entities.get(entity_id, 0)} transmittal(s); each filing entity "
                    f"transmits its forms exactly once",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_transmittals(ctx))} transmittals foot the forms they accompany",
            )
        )
    return out


@check("rpt_annual_rollup_ties")
def check_rpt_annual_rollup_ties(ctx: Context) -> list[Finding]:
    """The annual issuance rollup ties the sum of the transmittals.

    The figure that reaches a controller is the rollup, and a rollup that is not
    added up from the transmittals underneath it is an assertion about a year
    nobody re-added.
    """
    rule = "rpt_annual_rollup_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_ISSUANCE_REPORT)
    register = ctx.one(DOC_TRANSMITTAL_REGISTER)
    if report is None or register is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        count = 0
        reported = 0
        withheld = 0
        for row in _transmittals(ctx):
            entity_id = _text(row, "entity_id") or "?"
            count += require_cents(
                f"transmittal[{entity_id}].form_count",
                row.get("form_count"),
                unit="a whole count",
            )
            reported += require_cents(
                f"transmittal[{entity_id}].total_reported_cents",
                row.get("total_reported_cents"),
            )
            withheld += require_cents(
                f"transmittal[{entity_id}].total_withheld_cents",
                row.get("total_withheld_cents"),
            )
        stated_count = require_cents(
            "issuance_report.form_count", report.get("form_count"), unit="a whole count"
        )
        stated_reported = require_cents(
            "issuance_report.total_reported_cents", report.get("total_reported_cents")
        )
        stated_withheld = require_cents(
            "issuance_report.total_withheld_cents", report.get("total_withheld_cents")
        )
        if (stated_count, stated_reported, stated_withheld) != (count, reported, withheld):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "form_count"),
                    f"the annual rollup states {stated_count} form(s) reporting "
                    f"{fmt(stated_reported)} with {fmt(stated_withheld)} withheld; the "
                    f"transmittals sum to {count} form(s) reporting {fmt(reported)} with "
                    f"{fmt(withheld)} withheld",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the annual rollup of {count} form(s) and {fmt(reported)} ties the "
                    f"transmittals",
                )
            )
    return out


@check("rpt_watchlist_ties")
def check_rpt_watchlist_ties(ctx: Context) -> list[Finding]:
    """The near-threshold watchlist ties the ledger evidence.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a payee who is not actually near the line -- or omits one
    who is -- sends the year-end review to the wrong payee. It is rebuilt from the
    ledger totals and compared.
    """
    rule = "rpt_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_THRESHOLD_WATCHLIST)
    extract = ctx.one(DOC_LEDGER_EXTRACT)
    if watchlist is None or extract is None:
        return []
    want = sorted(_normalize_entry(e) for e in recompute_watchlist(ctx))
    have = sorted(_normalize_entry(e) for e in _watchlist_entries(ctx))
    out: list[Finding] = []
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}/{entry[1]}"),
                        f"the watchlist holds entity {entry[0]} payee {entry[1]} box "
                        f"{entry[2]}/{entry[3]} as near its threshold, and the ledger totals "
                        f"do not put it inside the review band",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}/{entry[1]}"),
                        f"entity {entry[0]} payee {entry[1]} box {entry[2]}/{entry[3]} sits "
                        f"inside the review band below its threshold and is not on the "
                        f"watchlist",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the near-threshold watchlist ties the ledger")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one reporting file."""
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
    """Analyze every ``.json`` reporting file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of reporting-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
