"""
Gross-receipts & excise tax reconciliation control engine (READ-ONLY).
======================================================================

Loads each reconciliation file (a ``.json`` file produced by
:mod:`grt_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the tax on the worksheet is the tax the receipts
produce**. It re-derives every filed worksheet's tax from the GL revenue pull
and the jurisdiction's rate table, ties the recomputed figure to the number the
worksheet filed, and proves the filing calendar is complete, timely and
approved. Where a cost lands on a project is a different engine's job; this one
audits the tax return.

The shape of the problem
------------------------
A developer that manages projects across several taxing jurisdictions owes a
gross-receipts or excise tax in each one, each with its own classification rate,
filing cadence, deductions, thresholds and due dates, and each rate can change
mid-year. The tax on a worksheet is a derived figure, and it goes wrong in ways
that look right: a base that does not tie the ledger, a rate that was right last
quarter, a deduction taken twice, a below-threshold rule claimed above the
threshold, a filing that is missing or late or unapproved.

The registry is organised around that:

1. ``set_``   -- is the reconciliation file complete?
2. ``ent_``   -- is the entity register sound and its filing scope declared?
3. ``jur_``   -- is the jurisdiction rate table well-formed?
4. ``rev_``   -- is the GL pull sound, attributable, mapped, and does the base tie it?
5. ``fil_``   -- is every worksheet well-formed, unique and attributable?
6. ``eff_``   -- was the rate in force for the period the rate the worksheet used?
7. ``rate_``  -- does the tax re-derive from base x rate, and net of credit?
8. ``ded_``   -- do the base, the back-out and the credit follow the jurisdiction's rules?
9. ``cal_``   -- is every expected filing present, timely and approved?
10. ``lic_``  -- is each business licence active and not lapsing?
11. ``rpt_``  -- does the rollup recompute from the worksheets it summarises?

Design notes
------------
- **Strictly read-only.** Reconciliation files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tax is compared with exact ``==``.
- **One tax computation.** Controls and the generator share the kernel in
  :mod:`grt_engine.grt`, so a re-derived tax cannot disagree with the data that
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

from .grt import (
    RateWindow,
    effective_rate,
    expected_credit,
    net_tax,
    tax_before_credit,
    taxable_base,
)
from .model import (
    CADENCES,
    DOC_ENTITY_REGISTER,
    DOC_EXCISE_REPORT,
    DOC_FILING_REGISTER,
    DOC_JURISDICTION_REGISTER,
    DOC_LICENSE_REGISTER,
    DOC_REVENUE_LEDGER,
    DOC_TAX_SUMMARY,
    DOC_TYPES,
    LICENSE_ACTIVE,
    LICENSE_STATUSES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~grt_engine.money.AmountInvalidError` as a finding."""
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
# Reconciliation-file accessors
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


def _is_active(entity: dict[str, Any]) -> bool:
    return _text(entity, "status") == "active"


def _required_jurisdictions(entity: dict[str, Any]) -> list[str]:
    value = entity.get("required_jurisdictions")
    if not isinstance(value, list):
        return []
    return [j for j in value if isinstance(j, str)]


def _jurisdictions(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_JURISDICTION_REGISTER), "jurisdictions")


def _jur_code(row: dict[str, Any]) -> str:
    value = row.get("jurisdiction_code")
    return value if isinstance(value, str) and value else "?"


def _jur_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _jurisdictions(ctx):
        code = _jur_code(row)
        if code != "?" and code not in out:
            out[code] = row
    return out


def _windows_for(jur: dict[str, Any]) -> list[RateWindow]:
    """Parse a jurisdiction's rate windows, skipping malformed rows.

    Reads only dates and an integer basis-point rate, never a cents amount, so
    building the rate table cannot itself raise on a bad money field.
    """
    windows: list[RateWindow] = []
    raw = jur.get("rate_windows")
    if not isinstance(raw, list):
        return windows
    for w in raw:
        if not isinstance(w, dict):
            continue
        eff_from = _parse_date(w.get("effective_from"))
        eff_to = _parse_date(w.get("effective_to"))
        rate = _int(w, "rate_bps")
        if eff_from is None or eff_to is None or rate is None:
            continue
        windows.append(RateWindow(eff_from, eff_to, rate))
    return windows


def _ledger(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_REVENUE_LEDGER), "lines")


def _line_id(row: dict[str, Any]) -> str:
    value = row.get("gl_line_id")
    return value if isinstance(value, str) and value else "?"


def _filings(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_FILING_REGISTER), "filings")


def _filing_id(row: dict[str, Any]) -> str:
    value = row.get("filing_id")
    return value if isinstance(value, str) and value else "?"


def _key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    """The (entity, jurisdiction, classification, period) join key."""
    return (
        _text(row, "entity_id") or "?",
        _text(row, "jurisdiction_code") or "?",
        _text(row, "classification") or "?",
        _text(row, "period") or "?",
    )


def _filing_keys(ctx: Context) -> set[tuple[str, str, str, str]]:
    return {_key(f) for f in _filings(ctx)}


def _filing_by_key(ctx: Context) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    out: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for f in _filings(ctx):
        out.setdefault(_key(f), f)
    return out


def _filing_by_id(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in _filings(ctx):
        out.setdefault(_filing_id(f), f)
    return out


def _ledger_for(ctx: Context, key: tuple[str, str, str, str]) -> list[dict[str, Any]]:
    return [line for line in _ledger(ctx) if _key(line) == key]


def _summary_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TAX_SUMMARY), "filings")


def _licenses(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_LICENSE_REGISTER), "licenses")


# --------------------------------------------------------------------------- #
# Shared re-derivation
# --------------------------------------------------------------------------- #
def recompute_tax_due(ctx: Context, filing: dict[str, Any]) -> int | None:
    """Recompute one worksheet's net tax from its receipts and the rate table.

    Reads the worksheet's own gross, non-taxable back-out and standard deduction,
    finds the classification rate in force for the period from the jurisdiction's
    windows, and applies the deduction, threshold and small-business-credit rules
    through the shared :mod:`grt_engine.grt` kernel the generator derived the data
    with. Returns ``None`` when no rate window covers the period -- a separate
    control owns that gap -- and raises :class:`AmountInvalidError` if a money
    field it must read is not integer cents.
    """
    jmap = _jur_map(ctx)
    jur = jmap.get(_text(filing, "jurisdiction_code") or "")
    gross = require_cents(
        f"filing[{_filing_id(filing)}].gross_receipts_cents",
        filing.get("gross_receipts_cents"),
    )
    nontaxable = require_cents(
        f"filing[{_filing_id(filing)}].nontaxable_cents",
        filing.get("nontaxable_cents"),
    )
    standard = require_cents(
        f"filing[{_filing_id(filing)}].standard_deduction_applied_cents",
        filing.get("standard_deduction_applied_cents"),
    )
    base = taxable_base(gross, nontaxable, standard)
    on = _parse_date(filing.get("period_start"))
    windows = _windows_for(jur) if jur is not None else []
    rate = effective_rate(windows, on) if on is not None else None
    if rate is None:
        return None
    tb = tax_before_credit(base, rate)
    threshold = require_cents(
        f"jurisdiction[{_text(filing, 'jurisdiction_code')}].threshold_cents",
        jur.get("threshold_cents"),
    ) if jur is not None else 0
    cap = require_cents(
        f"jurisdiction[{_text(filing, 'jurisdiction_code')}].sb_cap_cents",
        jur.get("sb_cap_cents"),
    ) if jur is not None else 0
    credit = expected_credit(gross, tb, threshold, cap)
    return net_tax(tb, credit)


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the reconciliation file depends on is present, exactly once.

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
                    f"{len(found)} {doc_type} documents present; the reconciliation file "
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
                f"as_of {ctx.as_of!r} is not a readable date; every due-date and renewal "
                f"test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# ent_ -- the entity register
# --------------------------------------------------------------------------- #
@check("ent_unique_ids")
def check_ent_unique_ids(ctx: Context) -> list[Finding]:
    """No entity id appears twice.

    The entity id joins the register to every ledger line, worksheet and licence.
    A duplicate makes a filing ambiguous about which entity it belongs to.
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
            f"entity id {eid} appears {count} times; a worksheet that names it cannot "
            f"be attributed to one entity",
        )
        for eid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} entity ids are unique"))
    return out


@check("ent_jurisdictions_declared")
def check_ent_jurisdictions_declared(ctx: Context) -> list[Finding]:
    """Every active entity declares a non-empty, known set of filing jurisdictions.

    An empty set is not a compliant entity; it is an entity whose filing scope was
    never captured, so the calendar controls below would have nothing to require
    of it and pass vacuously.
    """
    rule = "ent_jurisdictions_declared"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_ENTITY_REGISTER)
    if register is None:
        return []
    known = set(_jur_map(ctx))
    out: list[Finding] = []
    for row in _entities(ctx):
        if not _is_active(row):
            continue
        eid = _entity_id(row)
        declared = row.get("required_jurisdictions")
        if not isinstance(declared, list) or not _required_jurisdictions(row):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{eid}/required_jurisdictions"),
                    f"active entity {eid} declares no filing jurisdiction; its calendar "
                    f"controls would pass on an empty obligation",
                )
            )
            continue
        unknown = [j for j in _required_jurisdictions(row) if j not in known]
        if unknown:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"entities/{eid}/required_jurisdictions"),
                    f"entity {eid} is required to file in {unknown}, which is not in the "
                    f"jurisdiction register",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every active entity declares a known filing scope")
        )
    return out


# --------------------------------------------------------------------------- #
# jur_ -- the jurisdiction rate table
# --------------------------------------------------------------------------- #
@check("jur_cadence_valid")
def check_jur_cadence_valid(ctx: Context) -> list[Finding]:
    """Every jurisdiction carries a known filing cadence and a classification.

    The cadence and classification are how the calendar and the rate lookup key
    into a jurisdiction; an unknown cadence has no expected-period set and a
    missing classification cannot be matched to a worksheet.
    """
    rule = "jur_cadence_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_JURISDICTION_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _jurisdictions(ctx):
        code = _jur_code(row)
        cadence = _text(row, "cadence")
        if cadence not in CADENCES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"jurisdictions/{code}/cadence"),
                    f"jurisdiction {code} files at cadence {cadence!r}, which is not one of "
                    f"{CADENCES}; its expected-period set cannot be built",
                )
            )
        if _text(row, "classification") is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"jurisdictions/{code}/classification"),
                    f"jurisdiction {code} carries no classification; its rate cannot be "
                    f"matched to a worksheet line",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_jurisdictions(ctx))} jurisdictions carry a known cadence")
        )
    return out


@check("jur_rate_windows_sound")
def check_jur_rate_windows_sound(ctx: Context) -> list[Finding]:
    """Each rate window runs forward and carries a non-negative rate.

    A window entered back to front, or with a negative basis-point rate, makes the
    effective-rate lookup meaningless: no day it should cover is covered, and any
    rate it appears to state is a rate no receipts should ever be taxed at.
    """
    rule = "jur_rate_windows_sound"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_JURISDICTION_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _jurisdictions(ctx):
        code = _jur_code(row)
        raw = row.get("rate_windows")
        if not isinstance(raw, list):
            continue
        for i, w in enumerate(raw):
            if not isinstance(w, dict):
                continue
            eff_from = _parse_date(w.get("effective_from"))
            eff_to = _parse_date(w.get("effective_to"))
            rate = _int(w, "rate_bps")
            if eff_from is None or eff_to is None or rate is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"jurisdictions/{code}/rate_windows/{i}"),
                        f"jurisdiction {code} rate window {i} is malformed; a window needs "
                        f"two readable dates and an integer basis-point rate",
                    )
                )
                continue
            checked += 1
            if eff_from > eff_to:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"jurisdictions/{code}/rate_windows/{i}/effective_from"),
                        f"jurisdiction {code} rate window {i} opens {eff_from.isoformat()} and "
                        f"closes {eff_to.isoformat()}; the window does not run forwards",
                    )
                )
            elif rate < 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"jurisdictions/{code}/rate_windows/{i}/rate_bps"),
                        f"jurisdiction {code} rate window {i} states a negative rate {rate}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} rate windows are sound"))
    return out


# --------------------------------------------------------------------------- #
# rev_ -- the GL revenue pull
# --------------------------------------------------------------------------- #
@check("rev_required_fields")
def check_rev_required_fields(ctx: Context) -> list[Finding]:
    """Every ledger line carries the descriptive and amount fields the controls read."""
    rule = "rev_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_REVENUE_LEDGER)
    if register is None:
        return []
    text_fields = ("gl_line_id", "entity_id", "jurisdiction_code", "classification", "period")
    amount_fields = ("gross_receipts_cents", "nontaxable_cents")
    out: list[Finding] = []
    for row in _ledger(ctx):
        missing = [f for f in text_fields if not _text(row, f)]
        missing += [f for f in amount_fields if row.get(f) is None]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"lines/{_line_id(row)}"),
                    f"ledger line {_line_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_ledger(ctx))} ledger lines carry their fields")
        )
    return out


@check("rev_line_unique")
def check_rev_line_unique(ctx: Context) -> list[Finding]:
    """No GL line id appears twice.

    A shared line id means one receipt was counted onto two lines, and the pull
    can no longer prove the taxable base is not double-counting a dollar.
    """
    rule = "rev_line_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_REVENUE_LEDGER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _ledger(ctx):
        seen[_line_id(row)] = seen.get(_line_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"lines/{lid}"),
            f"GL line id {lid} appears {count} times; the same receipt cannot be counted "
            f"twice into the taxable base",
        )
        for lid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(seen)} GL line ids are unique"))
    return out


@check("rev_entity_known")
def check_rev_entity_known(ctx: Context) -> list[Finding]:
    """Every ledger line names an entity and a jurisdiction in the registers."""
    rule = "rev_entity_known"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_REVENUE_LEDGER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    jurisdictions = _jur_map(ctx)
    out: list[Finding] = []
    for row in _ledger(ctx):
        eid = _text(row, "entity_id")
        code = _text(row, "jurisdiction_code")
        if eid and eid not in entities:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"lines/{_line_id(row)}/entity_id"),
                    f"ledger line {_line_id(row)} names entity {eid!r}, which is not in the "
                    f"entity register",
                )
            )
        if code and code not in jurisdictions:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"lines/{_line_id(row)}/jurisdiction_code"),
                    f"ledger line {_line_id(row)} names jurisdiction {code!r}, which is not in "
                    f"the jurisdiction register",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every ledger line names a known entity and jurisdiction"))
    return out


@check("rev_ledger_mapped")
def check_rev_ledger_mapped(ctx: Context) -> list[Finding]:
    """Every ledger line maps to a worksheet.

    A receipt with no worksheet to carry it is revenue that was earned in a
    jurisdiction and never taxed there; completeness runs both ways, and this is
    the orphan-receipt direction of it.
    """
    rule = "rev_ledger_mapped"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_REVENUE_LEDGER)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if register is None or filing_reg is None:
        return []
    keys = _filing_keys(ctx)
    out: list[Finding] = []
    for row in _ledger(ctx):
        key = _key(row)
        if key not in keys:
            eid, code, classification, period = key
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"lines/{_line_id(row)}"),
                    f"ledger line {_line_id(row)} ({eid} / {code} / {classification} / "
                    f"{period}) has no worksheet; its receipts are taxed nowhere",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(_ledger(ctx))} ledger lines map to a worksheet"))
    return out


@check("rev_gross_ties_ledger")
def check_rev_gross_ties_ledger(ctx: Context) -> list[Finding]:
    """Each worksheet's stated gross receipts sum the GL lines under it.

    This is the base-completeness control: the monthly (or quarterly) GL lines
    for an entity-jurisdiction-period must sum to the gross the worksheet struck
    its rate against. A line dropped on the way to the worksheet is a base short
    of the receipts, and the tax is short with it.
    """
    rule = "rev_gross_ties_ledger"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    ledger_reg = ctx.one(DOC_REVENUE_LEDGER)
    if filing_reg is None or ledger_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        with amount_guard(rule, out):
            stated = require_cents(
                f"filing[{_filing_id(filing)}].gross_receipts_cents",
                filing.get("gross_receipts_cents"),
            )
            summed = 0
            for line in _ledger_for(ctx, _key(filing)):
                summed += require_cents(
                    f"ledger[{_line_id(line)}].gross_receipts_cents",
                    line.get("gross_receipts_cents"),
                )
            checked += 1
            if stated != summed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/gross_receipts_cents"),
                        f"worksheet {_filing_id(filing)} states gross {fmt(stated)}; the GL "
                        f"lines under it sum to {fmt(summed)} "
                        f"(off by {fmt(stated - summed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} worksheet gross figures tie the ledger"))
    return out


# --------------------------------------------------------------------------- #
# fil_ -- the filing register
# --------------------------------------------------------------------------- #
@check("fil_required_fields")
def check_fil_required_fields(ctx: Context) -> list[Finding]:
    """Every worksheet carries the descriptive fields the controls read."""
    rule = "fil_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FILING_REGISTER)
    if register is None:
        return []
    required = (
        "filing_id",
        "entity_id",
        "jurisdiction_code",
        "classification",
        "period",
        "period_start",
        "due_date",
        "worksheet_ref",
    )
    out: list[Finding] = []
    for row in _filings(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"filings/{_filing_id(row)}"),
                    f"worksheet {_filing_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(_filings(ctx))} worksheets carry their fields")
        )
    return out


@check("fil_unique")
def check_fil_unique(ctx: Context) -> list[Finding]:
    """No worksheet id, and no entity-jurisdiction-period, appears twice.

    Two worksheets for one obligation double-count the tax and make the rollup
    ambiguous about which one governs.
    """
    rule = "fil_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FILING_REGISTER)
    if register is None:
        return []
    ids: dict[str, int] = {}
    keys: dict[tuple[str, str, str, str], int] = {}
    for row in _filings(ctx):
        ids[_filing_id(row)] = ids.get(_filing_id(row), 0) + 1
        keys[_key(row)] = keys.get(_key(row), 0) + 1
    out: list[Finding] = []
    for fid, count in ids.items():
        if count > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"filings/{fid}"),
                    f"worksheet id {fid} appears {count} times",
                )
            )
    for key, count in keys.items():
        if count > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"filings/{'/'.join(key)}"),
                    f"obligation {' / '.join(key)} has {count} worksheets; exactly one governs",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {len(_filings(ctx))} worksheets are unique"))
    return out


@check("fil_refs_exist")
def check_fil_refs_exist(ctx: Context) -> list[Finding]:
    """Every worksheet names an entity and a jurisdiction in the registers."""
    rule = "fil_refs_exist"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_FILING_REGISTER)
    if register is None:
        return []
    entities = _entity_map(ctx)
    jurisdictions = _jur_map(ctx)
    out: list[Finding] = []
    for row in _filings(ctx):
        eid = _text(row, "entity_id")
        code = _text(row, "jurisdiction_code")
        if eid and eid not in entities:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"filings/{_filing_id(row)}/entity_id"),
                    f"worksheet {_filing_id(row)} names entity {eid!r}, which is not in the "
                    f"entity register",
                )
            )
        if code and code not in jurisdictions:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"filings/{_filing_id(row)}/jurisdiction_code"),
                    f"worksheet {_filing_id(row)} names jurisdiction {code!r}, which is not in "
                    f"the jurisdiction register",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every worksheet names a known entity and jurisdiction"))
    return out


# --------------------------------------------------------------------------- #
# eff_ -- the rate in force for the period
# --------------------------------------------------------------------------- #
@check("eff_rate_matches_period")
def check_eff_rate_matches_period(ctx: Context) -> list[Finding]:
    """The rate the worksheet applied is the rate in force for its period.

    A classification rate that changed mid-year is the trap: a worksheet that
    applied the prior window's rate to a period inside the new window is
    internally consistent and still wrong. The rate in force is looked up from the
    jurisdiction's windows against the period's start date and compared.
    """
    rule = "eff_rate_matches_period"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    jur_reg = ctx.one(DOC_JURISDICTION_REGISTER)
    if filing_reg is None or jur_reg is None:
        return []
    jmap = _jur_map(ctx)
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        jur = jmap.get(_text(filing, "jurisdiction_code") or "")
        if jur is None:
            continue  # fil_refs_exist owns this
        on = _parse_date(filing.get("period_start"))
        if on is None:
            continue  # fil_required_fields owns this
        stated = _int(filing, "rate_bps")
        expected = effective_rate(_windows_for(jur), on)
        checked += 1
        if expected is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/period_start"),
                    f"worksheet {_filing_id(filing)} covers a period starting "
                    f"{on.isoformat()}, which no {_jur_code(jur)} rate window covers",
                )
            )
        elif stated != expected:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/rate_bps"),
                    f"worksheet {_filing_id(filing)} applied rate {stated} bps; the "
                    f"{_jur_code(jur)} rate in force for a period starting {on.isoformat()} "
                    f"is {expected} bps",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} worksheets applied the rate in force"))
    return out


# --------------------------------------------------------------------------- #
# rate_ -- the tax re-derives from base x rate
# --------------------------------------------------------------------------- #
@check("rate_tax_before_credit_recomputes")
def check_rate_tax_before_credit_recomputes(ctx: Context) -> list[Finding]:
    """The pre-credit tax equals the taxable base times the stated rate.

    Compared with exact ``==``: the tax on the worksheet before any credit is the
    base struck at the classification rate, and truncating basis-point arithmetic
    is the platform contract, so a figure derived any other way does not tie.
    """
    rule = "rate_tax_before_credit_recomputes"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if filing_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        rate = _int(filing, "rate_bps")
        if rate is None:
            continue  # eff_rate_matches_period owns a malformed rate
        with amount_guard(rule, out):
            base = require_cents(
                f"filing[{_filing_id(filing)}].taxable_base_cents",
                filing.get("taxable_base_cents"),
            )
            stated = require_cents(
                f"filing[{_filing_id(filing)}].tax_before_credit_cents",
                filing.get("tax_before_credit_cents"),
            )
            expected = tax_before_credit(base, rate)
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/tax_before_credit_cents"),
                        f"worksheet {_filing_id(filing)} states pre-credit tax {fmt(stated)}; "
                        f"{fmt(base)} at {rate} bps re-derives {fmt(expected)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} pre-credit taxes re-derive"))
    return out


@check("rate_tax_due_recomputes")
def check_rate_tax_due_recomputes(ctx: Context) -> list[Finding]:
    """The tax due equals the pre-credit tax net of the credit.

    This is the figure that reaches the return. Net tax is the pre-credit tax less
    the credit, clamped at zero, and it must equal the worksheet's stated tax due
    to the cent.
    """
    rule = "rate_tax_due_recomputes"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if filing_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        with amount_guard(rule, out):
            tb = require_cents(
                f"filing[{_filing_id(filing)}].tax_before_credit_cents",
                filing.get("tax_before_credit_cents"),
            )
            credit = require_cents(
                f"filing[{_filing_id(filing)}].credit_cents",
                filing.get("credit_cents"),
            )
            stated = require_cents(
                f"filing[{_filing_id(filing)}].tax_due_cents",
                filing.get("tax_due_cents"),
            )
            expected = net_tax(tb, credit)
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/tax_due_cents"),
                        f"worksheet {_filing_id(filing)} states tax due {fmt(stated)}; "
                        f"{fmt(tb)} less credit {fmt(credit)} re-derives {fmt(expected)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} tax-due figures re-derive"))
    return out


# --------------------------------------------------------------------------- #
# ded_ -- deductions, back-outs and credits
# --------------------------------------------------------------------------- #
@check("ded_base_recomputes")
def check_ded_base_recomputes(ctx: Context) -> list[Finding]:
    """The taxable base equals gross less the back-out and the standard deduction.

    The base is receipts reduced by the non-taxable back-out and the standard
    deduction, clamped at zero. A base that does not re-derive is a base someone
    adjusted after the receipts were reconciled to it.
    """
    rule = "ded_base_recomputes"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if filing_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        with amount_guard(rule, out):
            gross = require_cents(
                f"filing[{_filing_id(filing)}].gross_receipts_cents",
                filing.get("gross_receipts_cents"),
            )
            nontaxable = require_cents(
                f"filing[{_filing_id(filing)}].nontaxable_cents",
                filing.get("nontaxable_cents"),
            )
            standard = require_cents(
                f"filing[{_filing_id(filing)}].standard_deduction_applied_cents",
                filing.get("standard_deduction_applied_cents"),
            )
            stated = require_cents(
                f"filing[{_filing_id(filing)}].taxable_base_cents",
                filing.get("taxable_base_cents"),
            )
            expected = taxable_base(gross, nontaxable, standard)
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/taxable_base_cents"),
                        f"worksheet {_filing_id(filing)} states taxable base {fmt(stated)}; "
                        f"{fmt(gross)} less back-out {fmt(nontaxable)} less standard deduction "
                        f"{fmt(standard)} re-derives {fmt(expected)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} taxable bases re-derive"))
    return out


@check("ded_nontaxable_ties_ledger")
def check_ded_nontaxable_ties_ledger(ctx: Context) -> list[Finding]:
    """Each worksheet's non-taxable back-out sums the GL lines under it.

    The back-out of non-taxable and out-of-jurisdiction receipts is not a
    free-standing number; it is the sum of the non-taxable portions the GL pull
    carries. An overstated back-out is an understated base, and the tax with it.
    """
    rule = "ded_nontaxable_ties_ledger"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    ledger_reg = ctx.one(DOC_REVENUE_LEDGER)
    if filing_reg is None or ledger_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        with amount_guard(rule, out):
            stated = require_cents(
                f"filing[{_filing_id(filing)}].nontaxable_cents",
                filing.get("nontaxable_cents"),
            )
            summed = 0
            for line in _ledger_for(ctx, _key(filing)):
                summed += require_cents(
                    f"ledger[{_line_id(line)}].nontaxable_cents",
                    line.get("nontaxable_cents"),
                )
            checked += 1
            if stated != summed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/nontaxable_cents"),
                        f"worksheet {_filing_id(filing)} backs out {fmt(stated)} non-taxable; "
                        f"the GL lines under it sum to {fmt(summed)} "
                        f"(off by {fmt(stated - summed)})",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} back-outs tie the ledger"))
    return out


@check("ded_credit_recomputes")
def check_ded_credit_recomputes(ctx: Context) -> list[Finding]:
    """The credit follows the jurisdiction's threshold and small-business rules.

    A below-threshold no-tax rule credits the whole tax away when the period's
    receipts fall below the threshold; otherwise the small-business credit
    schedule applies. The credit a worksheet carries is recomputed from those
    rules and compared, so a credit read off the wrong bracket -- or claimed above
    the threshold -- does not pass.
    """
    rule = "ded_credit_recomputes"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if filing_reg is None:
        return []
    jmap = _jur_map(ctx)
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        jur = jmap.get(_text(filing, "jurisdiction_code") or "")
        if jur is None:
            continue  # fil_refs_exist owns this
        with amount_guard(rule, out):
            gross = require_cents(
                f"filing[{_filing_id(filing)}].gross_receipts_cents",
                filing.get("gross_receipts_cents"),
            )
            tb = require_cents(
                f"filing[{_filing_id(filing)}].tax_before_credit_cents",
                filing.get("tax_before_credit_cents"),
            )
            stated = require_cents(
                f"filing[{_filing_id(filing)}].credit_cents",
                filing.get("credit_cents"),
            )
            threshold = require_cents(
                f"jurisdiction[{_jur_code(jur)}].threshold_cents", jur.get("threshold_cents")
            )
            cap = require_cents(
                f"jurisdiction[{_jur_code(jur)}].sb_cap_cents", jur.get("sb_cap_cents")
            )
            expected = expected_credit(gross, tb, threshold, cap)
            checked += 1
            if stated != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/credit_cents"),
                        f"worksheet {_filing_id(filing)} claims credit {fmt(stated)}; the "
                        f"{_jur_code(jur)} rules on gross {fmt(gross)} and pre-credit tax "
                        f"{fmt(tb)} allow {fmt(expected)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} credits re-derive"))
    return out


# --------------------------------------------------------------------------- #
# cal_ -- the filing calendar
# --------------------------------------------------------------------------- #
@check("cal_completeness")
def check_cal_completeness(ctx: Context) -> list[Finding]:
    """Every active entity has a worksheet for every expected period.

    The calendar is the enumeration: for each active entity, each jurisdiction it
    files in, each period that jurisdiction expects this cycle, a worksheet must
    exist. A hole here is an obligation nobody filed, invisible until an
    assessment arrives.
    """
    rule = "cal_completeness"
    _sev(rule, Status.FAIL)
    entity_reg = ctx.one(DOC_ENTITY_REGISTER)
    jur_reg = ctx.one(DOC_JURISDICTION_REGISTER)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if entity_reg is None or jur_reg is None or filing_reg is None:
        return []
    jmap = _jur_map(ctx)
    keys = _filing_keys(ctx)
    out: list[Finding] = []
    checked = 0
    for entity in _entities(ctx):
        if not _is_active(entity):
            continue
        eid = _entity_id(entity)
        for code in _required_jurisdictions(entity):
            jur = jmap.get(code)
            if jur is None:
                continue  # ent_jurisdictions_declared owns this
            classification = _text(jur, "classification") or "?"
            periods = jur.get("periods")
            if not isinstance(periods, list):
                continue
            for period in periods:
                if not isinstance(period, str):
                    continue
                checked += 1
                if (eid, code, classification, period) not in keys:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(filing_reg, f"filings/{eid}/{code}/{period}"),
                            f"entity {eid} has no {code} worksheet for period {period}; the "
                            f"obligation is unfiled",
                        )
                    )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} expected worksheets are present"))
    return out


@check("cal_due_date_gate")
def check_cal_due_date_gate(ctx: Context) -> list[Finding]:
    """A filed worksheet was filed on or before its due date.

    A return filed after its due date is a late return whether or not the tax was
    right. The filing date is compared to the due date the worksheet carries.
    """
    rule = "cal_due_date_gate"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if filing_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        if not bool(filing.get("filed")):
            continue
        filed_on = _parse_date(filing.get("filing_date"))
        due = _parse_date(filing.get("due_date"))
        if filed_on is None or due is None:
            continue  # fil_required_fields owns a missing due date
        checked += 1
        if filed_on > due:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/filing_date"),
                    f"worksheet {_filing_id(filing)} was filed {filed_on.isoformat()}, after "
                    f"its due date {due.isoformat()} ({(filed_on - due).days} day(s) late)",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} filed worksheets were on time"))
    return out


@check("cal_due_soon")
def check_cal_due_soon(ctx: Context) -> list[Finding]:
    """An unfiled worksheet due inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the obligation is not yet late, but the
    return needs to be filed before its due date passes. The window comes from the
    file's own ``lead_days``.
    """
    rule = "cal_due_soon"
    _sev(rule, Status.FLAG)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if filing_reg is None or as_of is None:
        return []
    lead = ctx.lead_days
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        if bool(filing.get("filed")):
            continue
        due = _parse_date(filing.get("due_date"))
        if due is None:
            continue
        checked += 1
        remaining = (due - as_of).days
        if 0 < remaining <= lead:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/due_date"),
                    f"worksheet {_filing_id(filing)} is unfiled and due {due.isoformat()}, in "
                    f"{remaining} day(s); inside the {lead}-day window and due to be filed",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"no unfiled worksheet is due within {lead} days"))
    return out


@check("cal_approval_before_filing")
def check_cal_approval_before_filing(ctx: Context) -> list[Finding]:
    """A filed worksheet was approved before it was filed.

    The approval signature is the control that a return was reviewed before it
    went out. A worksheet filed with no approval, or approved after it was filed,
    is a return that went out unreviewed.
    """
    rule = "cal_approval_before_filing"
    _sev(rule, Status.FAIL)
    filing_reg = ctx.one(DOC_FILING_REGISTER)
    if filing_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for filing in _filings(ctx):
        if not bool(filing.get("filed")):
            continue
        filed_on = _parse_date(filing.get("filing_date"))
        approved_on = _parse_date(filing.get("approval_date"))
        checked += 1
        if not bool(filing.get("approval_signed")) or approved_on is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/approval_signed"),
                    f"worksheet {_filing_id(filing)} was filed with no approval signature",
                )
            )
        elif filed_on is not None and approved_on > filed_on:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(filing_reg, f"filings/{_filing_id(filing)}/approval_date"),
                    f"worksheet {_filing_id(filing)} was approved {approved_on.isoformat()}, "
                    f"after it was filed {filed_on.isoformat()}",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} filed worksheets were approved first"))
    return out


# --------------------------------------------------------------------------- #
# lic_ -- business-licence status (secondary)
# --------------------------------------------------------------------------- #
@check("lic_status_active")
def check_lic_status_active(ctx: Context) -> list[Finding]:
    """Every active entity holds an active licence in each jurisdiction it files in.

    A gross-receipts filing rests on a live business licence in the jurisdiction.
    A cancelled or missing licence is a filing made against a registration the
    jurisdiction no longer recognises.
    """
    rule = "lic_status_active"
    _sev(rule, Status.FAIL)
    entity_reg = ctx.one(DOC_ENTITY_REGISTER)
    license_reg = ctx.one(DOC_LICENSE_REGISTER)
    if entity_reg is None or license_reg is None:
        return []
    held: dict[tuple[str, str], str] = {}
    for lic in _licenses(ctx):
        eid = _text(lic, "entity_id")
        code = _text(lic, "jurisdiction_code")
        status = _text(lic, "status")
        if eid and code:
            held[(eid, code)] = status or "?"
    out: list[Finding] = []
    checked = 0
    for entity in _entities(ctx):
        if not _is_active(entity):
            continue
        eid = _entity_id(entity)
        for code in _required_jurisdictions(entity):
            checked += 1
            status = held.get((eid, code))
            if status is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(license_reg, f"licenses/{eid}/{code}"),
                        f"entity {eid} files in {code} but holds no business licence there",
                    )
                )
            elif status != LICENSE_ACTIVE:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(license_reg, f"licenses/{eid}/{code}/status"),
                        f"entity {eid} files in {code} on a licence whose status is "
                        f"{status!r}, not {LICENSE_ACTIVE!r}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} required licences are active"))
    return out


@check("lic_renewal_current")
def check_lic_renewal_current(ctx: Context) -> list[Finding]:
    """An active licence renewing inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the licence is still active, but its
    renewal is due and needs to be lodged before it lapses. The window comes from
    the file's own ``lead_days``.
    """
    rule = "lic_renewal_current"
    _sev(rule, Status.FLAG)
    license_reg = ctx.one(DOC_LICENSE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if license_reg is None or as_of is None:
        return []
    lead = ctx.lead_days
    out: list[Finding] = []
    checked = 0
    for lic in _licenses(ctx):
        if _text(lic, "status") != LICENSE_ACTIVE:
            continue
        renewal = _parse_date(lic.get("renewal_date"))
        if renewal is None:
            continue
        checked += 1
        remaining = (renewal - as_of).days
        if remaining <= lead:
            eid = _text(lic, "entity_id") or "?"
            code = _text(lic, "jurisdiction_code") or "?"
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(license_reg, f"licenses/{eid}/{code}/renewal_date"),
                    f"entity {eid} {code} licence renews {renewal.isoformat()}, in "
                    f"{remaining} day(s); inside the {lead}-day window and due to be renewed",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", f"all {checked} active licences are outside the renewal window"))
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the worksheets
# --------------------------------------------------------------------------- #
@check("rpt_summary_recomputes")
def check_rpt_summary_recomputes(ctx: Context) -> list[Finding]:
    """Each summarised tax-due figure recomputes from the worksheet's receipts.

    This is the control the engine exists for. The tax summary is a
    determination, and a determination not recomputed from the receipts and the
    rate table is an assertion. The engine rebuilds every tax-due figure from the
    worksheet's gross, back-out and standard deduction through the shared kernel
    and compares.
    """
    rule = "rpt_summary_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_TAX_SUMMARY)
    if summary is None:
        return []
    filings = _filing_by_id(ctx)
    out: list[Finding] = []
    for row in _summary_rows(ctx):
        fid = _text(row, "filing_id")
        filing = filings.get(fid or "")
        if filing is None:
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"tax_summary[{fid}].tax_due_cents", row.get("tax_due_cents")
            )
            recomputed = recompute_tax_due(ctx, filing)
            if recomputed is None:
                continue  # eff_rate_matches_period owns an uncovered period
            if stated != recomputed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"filings/{fid}/tax_due_cents"),
                        f"worksheet {fid} is summarised at tax due {fmt(stated)}; recomputing "
                        f"from its receipts gives {fmt(recomputed)}",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every summarised tax figure recomputes from the receipts"))
    return out


@check("rpt_report_totals_tie")
def check_rpt_report_totals_tie(ctx: Context) -> list[Finding]:
    """The portfolio total and filing count tie the tax summary.

    The number that reaches a controller is a total, and a total maintained beside
    the summary rather than derived from it drifts the first time a worksheet moves
    and nobody re-adds the column.
    """
    rule = "rpt_report_totals_tie"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_EXCISE_REPORT)
    summary = ctx.one(DOC_TAX_SUMMARY)
    if report is None or summary is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        total = 0
        count = 0
        for row in _summary_rows(ctx):
            total += require_cents(
                f"tax_summary[{_text(row, 'filing_id')}].tax_due_cents",
                row.get("tax_due_cents"),
            )
            count += 1
        stated_total = require_cents(
            "excise_report.total_tax_due_cents", report.get("total_tax_due_cents")
        )
        stated_count = require_cents(
            "excise_report.filing_count", report.get("filing_count"), unit="a whole count"
        )
        if stated_total != total or stated_count != count:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "total_tax_due_cents"),
                    f"the report states total {fmt(stated_total)} over {stated_count} "
                    f"worksheet(s); the summary recomputes {fmt(total)} over {count}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report total {fmt(total)} over {count} worksheet(s) ties the summary",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one reconciliation file."""
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
    """Analyze every ``.json`` reconciliation file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of reconciliation-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
