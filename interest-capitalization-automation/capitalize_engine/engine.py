"""
Section 263A interest-capitalization control engine (READ-ONLY).
================================================================

Loads each capitalization file (a ``.json`` file produced by
:mod:`capitalize_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the interest a schedule capitalized re-derives
from the expenditures and the rate**, not where the interest is booked. Posting
the entry is a separate system's job. This engine is the check that the split was
computed the way the avoided-cost method of IRC section 263A(f) requires and that
every tab ties to the one beneath it.

The shape of the problem
------------------------
A developer that builds designated property with borrowed money must capitalize
the interest production could have avoided -- the period rate applied to the
accumulated production expenditures -- into the property's basis, and may deduct
the rest. The annual schedule lays every active project across a grid of calendar
quarter-ends, pulls each project's interest expense by quarter, and computes the
capitalized and deducted portions. It is rebuilt every fiscal year.

Four failures hide inside that, and none of them look wrong in a grid of
quarters: the row that stops footing to its annual total; the split that leaks,
where interest is neither capitalized nor deducted; the project on the trial
balance that never reaches the schedule; and the capitalized figure that was
typed in rather than re-derived, or rolled at a rate applied inconsistently, or a
comparison that does not carry the prior year forward.

The registry is organised around that:

1. ``set_``  -- is the capitalization file complete?
2. ``prj_``  -- is the project roster sound, and complete against the trial balance?
3. ``data_`` -- are the expenditures and the rate well-formed for every quarter?
4. ``cap_``  -- does the capitalized / deducted split re-derive, foot and tie?
5. ``cmp_``  -- does the year-over-year comparison tie the schedule and roll forward?
6. ``rpt_``  -- do the schedule rollups recompute from the projects they summarise?

Design notes
------------
- **Strictly read-only.** Capitalization files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tie is compared with exact ``==``.
- **One capitalization kernel.** Controls and the generator share the arithmetic
  in :mod:`capitalize_engine.capitalize`, so a re-derived figure cannot disagree
  with the data that produced it.
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

from .capitalize import (
    capitalized_for_quarter,
    deducted_for_quarter,
    ending_capitalized,
)
from .model import (
    DOC_COMPARISON,
    DOC_INTEREST_BY_YEAR,
    DOC_PROJECT_DATA,
    DOC_PROJECT_STATUS,
    DOC_TRIAL_BALANCE,
    DOC_TYPES,
    PROJECT_STATUSES,
    STATUS_COMPLETE,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, BPS_FULL, fmt, fmt_bps, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~capitalize_engine.money.AmountInvalidError` as a finding."""
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
# Capitalization-file helpers
# --------------------------------------------------------------------------- #
def _key(row: dict[str, Any]) -> tuple[str, str]:
    """The (company_no, job_no) key that joins a project across the tabs."""
    company = row.get("company_no")
    job = row.get("job_no")
    company = company if isinstance(company, str) and company else "?"
    job = job if isinstance(job, str) and job else "?"
    return (company, job)


def _keystr(key: tuple[str, str]) -> str:
    return f"{key[0]}/{key[1]}"


def _status_projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PROJECT_STATUS), "projects")


def _roster_keys(ctx: Context) -> list[tuple[str, str]]:
    """Distinct project keys on the roster, in first-seen order."""
    out: list[tuple[str, str]] = []
    for row in _status_projects(ctx):
        key = _key(row)
        if key not in out:
            out.append(key)
    return out


def _tb_projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TRIAL_BALANCE), "projects")


def _data_projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PROJECT_DATA), "projects")


def _data_by_key(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _data_projects(ctx):
        key = _key(row)
        if key not in out:
            out[key] = row
    return out


def _interest_projects(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_INTEREST_BY_YEAR), "projects")


def _interest_by_key(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _interest_projects(ctx):
        key = _key(row)
        if key not in out:
            out[key] = row
    return out


def _comparison_by_key(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _rows(ctx.one(DOC_COMPARISON), "projects"):
        key = _key(row)
        if key not in out:
            out[key] = row
    return out


def _quarters(row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(row, dict):
        return []
    qs = row.get("quarters")
    if not isinstance(qs, list):
        return []
    return [q for q in qs if isinstance(q, dict)]


def _rate_bps(data_row: dict[str, Any] | None) -> int | None:
    """The project's capitalization rate if it is a valid basis-point rate.

    Returns ``None`` when the rate is missing, non-integer or outside the
    ``0..10000`` basis-point band, so the controls that apply the rate can defer
    the malformed case to ``data_rate_valid`` rather than each re-reporting it.
    """
    if not isinstance(data_row, dict):
        return None
    value = data_row.get("capitalization_rate_bps")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > BPS_FULL:
        return None
    return value


def recompute_annual_capitalized(ctx: Context, key: tuple[str, str]) -> int | None:
    """Annual capitalized interest re-derived from a project's own base facts.

    The rate applied to each quarter's accumulated production expenditures,
    rolled across the quarters. Shared with the generator through
    :mod:`capitalize_engine.capitalize`, so the annual figure the engine
    recomputes is the one that produced the schedule. Returns ``None`` when the
    project's data or rate is absent or malformed, leaving those cases to the
    ``data_`` controls.

    Raises :class:`AmountInvalidError` if an expenditure it must read is not
    integer cents; the calling control contains that to the row being read.
    """
    data_row = _data_by_key(ctx).get(key)
    rate = _rate_bps(data_row)
    if data_row is None or rate is None:
        return None
    total = 0
    for q in _quarters(data_row):
        ape = require_cents(
            f"project_data[{_keystr(key)}].accumulated_production_expenditures_cents",
            q.get("accumulated_production_expenditures_cents"),
        )
        total += capitalized_for_quarter(ape, rate)
    return total


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every tab the capitalization file depends on is present, exactly once.

    This runs first and deliberately owns the "missing artifact" finding. A
    control that silently passes because its input is absent is worse than no
    control: it reports assurance it never performed. The quarter grid the whole
    schedule is built across is checked here too, since every ``data_`` and
    ``cap_`` control iterates it.
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
                    f"{len(found)} {doc_type} documents present; the capitalization file "
                    f"carries exactly one of each",
                )
            )
    if not ctx.quarter_ends:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                "quarter_ends is missing or empty; the schedule has no quarter grid to "
                "foot across",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; the completion review is "
                f"measured to it",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} capitalization tabs are present over a "
                f"{len(ctx.quarter_ends)}-quarter grid",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# prj_ -- the project roster and completeness against the trial balance
# --------------------------------------------------------------------------- #
@check("prj_unique_keys")
def check_prj_unique_keys(ctx: Context) -> list[Finding]:
    """No (company_no, job_no) project key appears twice on the roster.

    The project key joins the roster to the data, interest and comparison tabs. A
    duplicate makes a quarter of interest ambiguous about which project it
    belongs to.
    """
    rule = "prj_unique_keys"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_STATUS)
    if register is None:
        return []
    seen: dict[tuple[str, str], int] = {}
    for row in _status_projects(ctx):
        key = _key(row)
        seen[key] = seen.get(key, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"projects/{_keystr(key)}"),
            f"project {_keystr(key)} appears {count} times; a quarter of interest that "
            f"names it cannot be attributed to one project",
        )
        for key, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} project keys are unique")
        )
    return out


@check("prj_name_present")
def check_prj_name_present(ctx: Context) -> list[Finding]:
    """Every project on the roster carries a project name.

    The name is what a reviewer reads the schedule by; a keyed row with no name
    is a project nobody reading the workbook can identify.
    """
    rule = "prj_name_present"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_STATUS)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _status_projects(ctx):
        if _text(row, "project_name") is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{_keystr(_key(row))}/project_name"),
                    f"project {_keystr(_key(row))} carries no project name",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_status_projects(ctx))} roster projects carry a name",
            )
        )
    return out


@check("prj_status_valid")
def check_prj_status_valid(ctx: Context) -> list[Finding]:
    """Every project carries a known status.

    The status decides whether a project is still in its capitalization period;
    an unknown status leaves the completion review with nothing to key on.
    """
    rule = "prj_status_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PROJECT_STATUS)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _status_projects(ctx):
        status = _text(row, "status")
        if status not in PROJECT_STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"projects/{_keystr(_key(row))}/status"),
                    f"project {_keystr(_key(row))} is in status {status!r}, which is not "
                    f"one of {PROJECT_STATUSES}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_status_projects(ctx))} roster projects carry a known status",
            )
        )
    return out


@check("prj_tb_complete")
def check_prj_tb_complete(ctx: Context) -> list[Finding]:
    """Every project on the entity trial balance appears on the schedule.

    This is the completeness control. A construction project carrying an interest
    balance on the trial balance but absent from the schedule has all of its
    interest deducted and none capitalized, and nothing in the workbook notices.
    The trial balance is the authoritative population; the roster is proved
    against it.
    """
    rule = "prj_tb_complete"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    roster = ctx.one(DOC_PROJECT_STATUS)
    if tb is None or roster is None:
        return []
    on_roster = set(_roster_keys(ctx))
    out: list[Finding] = []
    checked = 0
    for row in _tb_projects(ctx):
        key = _key(row)
        checked += 1
        if key not in on_roster:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(roster, f"projects/{_keystr(key)}"),
                    f"project {_keystr(key)} carries an interest balance on the trial "
                    f"balance but is absent from the schedule; its interest would be "
                    f"deducted in full with none capitalized",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} trial-balance projects appear on the schedule",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# data_ -- the expenditures and the rate, well-formed for every quarter
# --------------------------------------------------------------------------- #
@check("data_project_coverage")
def check_data_project_coverage(ctx: Context) -> list[Finding]:
    """Every roster project has data, interest and comparison rows for every quarter.

    A project on the roster with no data tab, no interest tab, or a quarter
    missing from either, would have its capitalized interest skipped by the
    controls that read those tabs -- passing vacuously on an absent quarter. The
    grid is the file's own ``quarter_ends``.
    """
    rule = "data_project_coverage"
    _sev(rule, Status.FAIL)
    roster = ctx.one(DOC_PROJECT_STATUS)
    data_doc = ctx.one(DOC_PROJECT_DATA)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    comparison_doc = ctx.one(DOC_COMPARISON)
    if None in (roster, data_doc, interest_doc, comparison_doc):
        return []
    grid = set(ctx.quarter_ends)
    data_map = _data_by_key(ctx)
    interest_map = _interest_by_key(ctx)
    comparison_map = _comparison_by_key(ctx)
    out: list[Finding] = []
    checked = 0
    for key in _roster_keys(ctx):
        checked += 1
        data_row = data_map.get(key)
        interest_row = interest_map.get(key)
        if data_row is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(data_doc, f"projects/{_keystr(key)}"),
                    f"project {_keystr(key)} is on the roster but has no Project Data row",
                )
            )
        else:
            missing = grid - {_text(q, "quarter_end") for q in _quarters(data_row)}
            if missing:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(data_doc, f"projects/{_keystr(key)}/quarters"),
                        f"project {_keystr(key)} Project Data is missing quarter(s) "
                        f"{sorted(missing)}; its capitalized interest cannot be re-derived",
                    )
                )
        if interest_row is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(interest_doc, f"projects/{_keystr(key)}"),
                    f"project {_keystr(key)} is on the roster but has no Interest by Year row",
                )
            )
        else:
            missing = grid - {_text(q, "quarter_end") for q in _quarters(interest_row)}
            if missing:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(interest_doc, f"projects/{_keystr(key)}/quarters"),
                        f"project {_keystr(key)} Interest by Year is missing quarter(s) "
                        f"{sorted(missing)}; its columns cannot foot",
                    )
                )
        if key not in comparison_map:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(comparison_doc, f"projects/{_keystr(key)}"),
                    f"project {_keystr(key)} is on the roster but has no Comparison row",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} roster projects are covered across every tab and quarter",
            )
        )
    return out


@check("data_ape_nonneg")
def check_data_ape_nonneg(ctx: Context) -> list[Finding]:
    """Accumulated production expenditures are non-negative integer cents.

    Accumulated expenditures are a running balance of cost incurred; a negative
    balance is not a smaller project, it is a data error, and it would drive a
    negative -- capitalized -- interest figure straight into basis.
    """
    rule = "data_ape_nonneg"
    _sev(rule, Status.FAIL)
    data_doc = ctx.one(DOC_PROJECT_DATA)
    if data_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _data_projects(ctx):
        key = _key(row)
        for q in _quarters(row):
            with amount_guard(rule, out):
                ape = require_cents(
                    f"project_data[{_keystr(key)}].accumulated_production_expenditures_cents",
                    q.get("accumulated_production_expenditures_cents"),
                )
                checked += 1
                if ape < 0:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                data_doc,
                                f"projects/{_keystr(key)}/{_text(q, 'quarter_end')}"
                                f"/accumulated_production_expenditures_cents",
                            ),
                            f"project {_keystr(key)} shows {fmt(ape)} accumulated production "
                            f"expenditures at {_text(q, 'quarter_end')}; the balance cannot "
                            f"be negative",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} accumulated-expenditure balances are non-negative",
            )
        )
    return out


@check("data_ape_nondecreasing")
def check_data_ape_nondecreasing(ctx: Context) -> list[Finding]:
    """Accumulated production expenditures do not fall quarter over quarter.

    Accumulated expenditures are cumulative within the year: production cost adds
    up, it does not unwind. A quarter-end balance below the quarter before it is
    a break in the accumulation, and every quarterly capitalized figure past it
    is computed on the wrong base.
    """
    rule = "data_ape_nondecreasing"
    _sev(rule, Status.FAIL)
    data_doc = ctx.one(DOC_PROJECT_DATA)
    if data_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _data_projects(ctx):
        key = _key(row)
        dated: list[tuple[date, int]] = []
        for q in _quarters(row):
            quarter_end = _parse_date(q.get("quarter_end"))
            if quarter_end is None:
                continue
            with amount_guard(rule, out):
                ape = require_cents(
                    f"project_data[{_keystr(key)}].accumulated_production_expenditures_cents",
                    q.get("accumulated_production_expenditures_cents"),
                )
                dated.append((quarter_end, ape))
        dated.sort(key=lambda t: t[0])
        for (prior_end, prior_ape), (this_end, this_ape) in zip(dated, dated[1:]):
            checked += 1
            if this_ape < prior_ape:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            data_doc,
                            f"projects/{_keystr(key)}/{this_end.isoformat()}"
                            f"/accumulated_production_expenditures_cents",
                        ),
                        f"project {_keystr(key)} accumulated expenditures fall from "
                        f"{fmt(prior_ape)} at {prior_end.isoformat()} to {fmt(this_ape)} at "
                        f"{this_end.isoformat()}; the accumulation cannot decrease",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} quarter-over-quarter expenditure steps are non-decreasing",
            )
        )
    return out


@check("data_rate_valid")
def check_data_rate_valid(ctx: Context) -> list[Finding]:
    """Every project's capitalization rate is a valid basis-point rate.

    The rate is the multiplier the whole capitalized figure turns on. A missing,
    non-integer or out-of-band rate -- below zero or above 100.00% -- is not a
    rate to apply, so the controls that apply it defer the malformed case here
    rather than each re-reporting it.
    """
    rule = "data_rate_valid"
    _sev(rule, Status.FAIL)
    data_doc = ctx.one(DOC_PROJECT_DATA)
    if data_doc is None:
        return []
    out: list[Finding] = []
    for row in _data_projects(ctx):
        key = _key(row)
        if _rate_bps(row) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(data_doc, f"projects/{_keystr(key)}/capitalization_rate_bps"),
                    f"project {_keystr(key)} carries capitalization rate "
                    f"{row.get('capitalization_rate_bps')!r}, which is not a basis-point "
                    f"rate in 0..{BPS_FULL}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_data_projects(ctx))} projects carry a valid capitalization rate",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cap_ -- the capitalized / deducted split re-derives, foots and ties
# --------------------------------------------------------------------------- #
@check("cap_rate_consistent")
def check_cap_rate_consistent(ctx: Context) -> list[Finding]:
    """The capitalization rate is applied consistently across the period.

    The avoided-cost rate is a single applicable rate for the entity's
    non-traced debt in the period; it is not chosen project by project. Two
    valid rates on one schedule means one project was rolled at a rate the others
    were not, and the capitalized figures are no longer comparable. Projects
    whose rate is itself malformed are left to ``data_rate_valid``.
    """
    rule = "cap_rate_consistent"
    _sev(rule, Status.FAIL)
    data_doc = ctx.one(DOC_PROJECT_DATA)
    if data_doc is None:
        return []
    rated: list[tuple[tuple[str, str], int]] = []
    for row in _data_projects(ctx):
        rate = _rate_bps(row)
        if rate is not None:
            rated.append((_key(row), rate))
    distinct = sorted({rate for _k, rate in rated})
    out: list[Finding] = []
    if len(distinct) > 1:
        # The period rate is the one most projects share; the minority are the
        # outliers, so a single mis-rolled project is named rather than the many
        # it disagrees with. Ties break on the smaller rate, keeping it stable.
        counts: dict[int, int] = {}
        for _k, rate in rated:
            counts[rate] = counts.get(rate, 0) + 1
        base = min(counts, key=lambda r: (-counts[r], r))
        for key, rate in rated:
            if rate != base:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(data_doc, f"projects/{_keystr(key)}/capitalization_rate_bps"),
                        f"project {_keystr(key)} is rolled at {fmt_bps(rate)}, but the period "
                        f"rate elsewhere on the schedule is {fmt_bps(base)}; the rate must be "
                        f"applied consistently",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(rated)} projects are rolled at the same capitalization rate",
            )
        )
    return out


@check("cap_rederives")
def check_cap_rederives(ctx: Context) -> list[Finding]:
    """Each quarter's capitalized interest re-derives from expenditures and rate.

    This is the control the engine exists for. The capitalized column is a
    *derivation*, and a capitalized figure that is not recomputed from the
    accumulated production expenditures times the period rate is an assertion.
    The engine rebuilds every quarter's capitalized interest through the shared
    kernel -- expenditures rolled at the rate -- and compares. Projects whose
    rate or data is malformed are left to the ``data_`` controls.
    """
    rule = "cap_rederives"
    _sev(rule, Status.FAIL)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    if interest_doc is None:
        return []
    data_map = _data_by_key(ctx)
    out: list[Finding] = []
    checked = 0
    for interest_row in _interest_projects(ctx):
        key = _key(interest_row)
        data_row = data_map.get(key)
        rate = _rate_bps(data_row)
        if data_row is None or rate is None:
            continue  # data_project_coverage / data_rate_valid own this
        ape_by_quarter: dict[str, Any] = {
            _text(q, "quarter_end"): q.get("accumulated_production_expenditures_cents")
            for q in _quarters(data_row)
        }
        for q in _quarters(interest_row):
            quarter_end = _text(q, "quarter_end")
            if quarter_end not in ape_by_quarter:
                continue  # data_project_coverage owns the missing quarter
            with amount_guard(rule, out):
                ape = require_cents(
                    f"project_data[{_keystr(key)}].accumulated_production_expenditures_cents",
                    ape_by_quarter[quarter_end],
                )
                stated = require_cents(
                    f"interest_by_year[{_keystr(key)}].capitalized_cents",
                    q.get("capitalized_cents"),
                )
                expected = capitalized_for_quarter(ape, rate)
                checked += 1
                if stated != expected:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                interest_doc,
                                f"projects/{_keystr(key)}/{quarter_end}/capitalized_cents",
                            ),
                            f"project {_keystr(key)} capitalizes {fmt(stated)} at {quarter_end}; "
                            f"{fmt(ape)} of expenditures at {fmt_bps(rate)} re-derives "
                            f"{fmt(expected)}",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} quarterly capitalized figures re-derive from expenditures "
                f"and rate",
            )
        )
    return out


@check("cap_no_leakage")
def check_cap_no_leakage(ctx: Context) -> list[Finding]:
    """Each quarter's interest equals its capitalized plus deducted portions.

    The interest a project incurred is either capitalized into basis or deducted;
    there is no third destination. When the capitalized and deducted columns do
    not add back to the interest column, a slice of interest has leaked out of
    the schedule -- capitalized nowhere and deducted nowhere.
    """
    rule = "cap_no_leakage"
    _sev(rule, Status.FAIL)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    if interest_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _interest_projects(ctx):
        key = _key(row)
        for q in _quarters(row):
            with amount_guard(rule, out):
                interest = require_cents(
                    f"interest_by_year[{_keystr(key)}].interest_expense_cents",
                    q.get("interest_expense_cents"),
                )
                capitalized = require_cents(
                    f"interest_by_year[{_keystr(key)}].capitalized_cents",
                    q.get("capitalized_cents"),
                )
                deducted = require_cents(
                    f"interest_by_year[{_keystr(key)}].deducted_cents",
                    q.get("deducted_cents"),
                )
                checked += 1
                if capitalized + deducted != interest:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                interest_doc,
                                f"projects/{_keystr(key)}/{_text(q, 'quarter_end')}",
                            ),
                            f"project {_keystr(key)} at {_text(q, 'quarter_end')} incurs "
                            f"{fmt(interest)} interest but capitalizes {fmt(capitalized)} and "
                            f"deducts {fmt(deducted)} ({fmt(interest - capitalized - deducted)} "
                            f"leaked)",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} quarterly splits close to the interest incurred",
            )
        )
    return out


@check("cap_within_interest")
def check_cap_within_interest(ctx: Context) -> list[Finding]:
    """A quarter never capitalizes more interest than it incurred.

    The avoided-cost method capitalizes the interest production could have
    avoided, capped at the interest actually paid: it cannot capitalize interest
    that was never incurred. A capitalized figure above the quarter's interest
    expense drives a negative deduction and overstates basis.
    """
    rule = "cap_within_interest"
    _sev(rule, Status.FAIL)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    if interest_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _interest_projects(ctx):
        key = _key(row)
        for q in _quarters(row):
            with amount_guard(rule, out):
                interest = require_cents(
                    f"interest_by_year[{_keystr(key)}].interest_expense_cents",
                    q.get("interest_expense_cents"),
                )
                capitalized = require_cents(
                    f"interest_by_year[{_keystr(key)}].capitalized_cents",
                    q.get("capitalized_cents"),
                )
                checked += 1
                if capitalized > interest:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(
                                interest_doc,
                                f"projects/{_keystr(key)}/{_text(q, 'quarter_end')}"
                                f"/capitalized_cents",
                            ),
                            f"project {_keystr(key)} at {_text(q, 'quarter_end')} capitalizes "
                            f"{fmt(capitalized)} against {fmt(interest)} of interest incurred "
                            f"(excess {fmt(capitalized - interest)})",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} quarters capitalize no more than the interest incurred",
            )
        )
    return out


@check("cap_annual_total_foots")
def check_cap_annual_total_foots(ctx: Context) -> list[Finding]:
    """Each project's quarterly columns foot to its stated annual totals.

    The annual interest, capitalized and deducted totals are the figures that
    leave the schedule for the return; a quarter is edited and the annual beside
    it is not re-added, and the row stops footing. Every column is re-summed
    across the grid and compared with exact ``==``.
    """
    rule = "cap_annual_total_foots"
    _sev(rule, Status.FAIL)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    if interest_doc is None:
        return []
    columns = (
        ("interest_expense_cents", "annual_interest_cents", "interest"),
        ("capitalized_cents", "annual_capitalized_cents", "capitalized"),
        ("deducted_cents", "annual_deducted_cents", "deducted"),
    )
    out: list[Finding] = []
    checked = 0
    for row in _interest_projects(ctx):
        key = _key(row)
        for quarter_field, annual_field, label in columns:
            with amount_guard(rule, out):
                footed = 0
                for q in _quarters(row):
                    footed += require_cents(
                        f"interest_by_year[{_keystr(key)}].{quarter_field}",
                        q.get(quarter_field),
                    )
                stated = require_cents(
                    f"interest_by_year[{_keystr(key)}].{annual_field}",
                    row.get(annual_field),
                )
                checked += 1
                if footed != stated:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(interest_doc, f"projects/{_keystr(key)}/{annual_field}"),
                            f"project {_keystr(key)} states annual {label} of {fmt(stated)}, "
                            f"but its quarters foot to {fmt(footed)} "
                            f"(off {fmt(stated - footed)})",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} annual columns foot to their quarters",
            )
        )
    return out


@check("cap_ceased_on_completion")
def check_cap_ceased_on_completion(ctx: Context) -> list[Finding]:
    """A project placed in service is no longer capitalizing interest.

    Deliberately a FLAG, not a failure: the capitalization period ends when the
    property is placed in service, so a project in status ``complete`` that still
    shows current-year capitalized interest needs a human's eyes to confirm the
    in-service date and stop the capitalization -- it is not a footing error the
    engine can adjudicate.
    """
    rule = "cap_ceased_on_completion"
    _sev(rule, Status.FLAG)
    roster = ctx.one(DOC_PROJECT_STATUS)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    if roster is None or interest_doc is None:
        return []
    interest_map = _interest_by_key(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _status_projects(ctx):
        if _text(row, "status") != STATUS_COMPLETE:
            continue
        key = _key(row)
        interest_row = interest_map.get(key)
        if interest_row is None:
            continue
        checked += 1
        with amount_guard(rule, out):
            annual_capitalized = require_cents(
                f"interest_by_year[{_keystr(key)}].annual_capitalized_cents",
                interest_row.get("annual_capitalized_cents"),
            )
            if annual_capitalized != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(interest_doc, f"projects/{_keystr(key)}/annual_capitalized_cents"),
                        f"project {_keystr(key)} is placed in service but still capitalizes "
                        f"{fmt(annual_capitalized)} this year; capitalization should cease at "
                        f"the in-service date",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"no placed-in-service project is still capitalizing "
                f"(checked {checked})",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cmp_ -- the year-over-year comparison ties the schedule and rolls forward
# --------------------------------------------------------------------------- #
@check("cmp_current_ties_schedule")
def check_cmp_current_ties_schedule(ctx: Context) -> list[Finding]:
    """The comparison's current-year capitalized ties the interest schedule.

    The comparison tab restates each project's current-year capitalized interest
    beside its prior-year balance. That current-year figure is the same number
    the Interest by Year tab already foots to as annual capitalized; carried on
    the comparison separately, it drifts the first time the schedule moves and
    the comparison is not refreshed.
    """
    rule = "cmp_current_ties_schedule"
    _sev(rule, Status.FAIL)
    comparison_doc = ctx.one(DOC_COMPARISON)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    if comparison_doc is None or interest_doc is None:
        return []
    interest_map = _interest_by_key(ctx)
    out: list[Finding] = []
    checked = 0
    for row in _rows(comparison_doc, "projects"):
        key = _key(row)
        interest_row = interest_map.get(key)
        if interest_row is None:
            continue  # data_project_coverage owns this
        with amount_guard(rule, out):
            current = require_cents(
                f"comparison[{_keystr(key)}].current_year_capitalized_cents",
                row.get("current_year_capitalized_cents"),
            )
            annual = require_cents(
                f"interest_by_year[{_keystr(key)}].annual_capitalized_cents",
                interest_row.get("annual_capitalized_cents"),
            )
            checked += 1
            if current != annual:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            comparison_doc,
                            f"projects/{_keystr(key)}/current_year_capitalized_cents",
                        ),
                        f"project {_keystr(key)} shows {fmt(current)} current-year capitalized "
                        f"on the comparison; the schedule foots {fmt(annual)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} comparison current-year figures tie the schedule",
            )
        )
    return out


@check("cmp_prior_year_ties")
def check_cmp_prior_year_ties(ctx: Context) -> list[Finding]:
    """The comparison rolls the prior-year capitalized balance forward.

    A capitalized balance is cumulative basis: it does not restart each year. The
    comparison's ending balance must be the prior-year capitalized balance plus
    the current year's capitalized interest. An ending balance that does not
    equal prior plus current has lost -- or double-counted -- a year of basis.
    """
    rule = "cmp_prior_year_ties"
    _sev(rule, Status.FAIL)
    comparison_doc = ctx.one(DOC_COMPARISON)
    if comparison_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rows(comparison_doc, "projects"):
        key = _key(row)
        with amount_guard(rule, out):
            prior = require_cents(
                f"comparison[{_keystr(key)}].prior_year_capitalized_cents",
                row.get("prior_year_capitalized_cents"),
            )
            current = require_cents(
                f"comparison[{_keystr(key)}].current_year_capitalized_cents",
                row.get("current_year_capitalized_cents"),
            )
            ending = require_cents(
                f"comparison[{_keystr(key)}].ending_capitalized_cents",
                row.get("ending_capitalized_cents"),
            )
            checked += 1
            expected = ending_capitalized(prior, current)
            if ending != expected:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(
                            comparison_doc,
                            f"projects/{_keystr(key)}/ending_capitalized_cents",
                        ),
                        f"project {_keystr(key)} ends at {fmt(ending)} capitalized; "
                        f"{fmt(prior)} prior plus {fmt(current)} current rolls forward to "
                        f"{fmt(expected)}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} comparison rows roll the prior year forward",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the schedule rollups recompute from the projects they summarise
# --------------------------------------------------------------------------- #
@check("rpt_total_capitalized_ties")
def check_rpt_total_capitalized_ties(ctx: Context) -> list[Finding]:
    """The schedule's total capitalized ties the sum of the project annuals.

    The portfolio total capitalized is the figure that reaches the return
    workpaper. Maintained beside the schedule rather than summed from it, it
    drifts the first time a project's annual capitalized moves and the total is
    not re-added.
    """
    rule = "rpt_total_capitalized_ties"
    _sev(rule, Status.FAIL)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    if interest_doc is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        footed = 0
        for row in _interest_projects(ctx):
            footed += require_cents(
                f"interest_by_year[{_keystr(_key(row))}].annual_capitalized_cents",
                row.get("annual_capitalized_cents"),
            )
        stated = require_cents(
            "interest_by_year.total_capitalized_cents",
            interest_doc.get("total_capitalized_cents"),
        )
        if footed != stated:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(interest_doc, "total_capitalized_cents"),
                    f"the schedule states {fmt(stated)} total capitalized; the project "
                    f"annuals sum to {fmt(footed)} (off {fmt(stated - footed)})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the total capitalized of {fmt(stated)} ties the project annuals",
                )
            )
    return out


@check("rpt_project_count_ties")
def check_rpt_project_count_ties(ctx: Context) -> list[Finding]:
    """The schedule's stated project count ties the roster.

    The project count is a completeness figure a reviewer reads first. Held
    beside the schedule rather than counted from the roster, it stops matching
    the first time a project is added or dropped and the count is not changed.
    """
    rule = "rpt_project_count_ties"
    _sev(rule, Status.FAIL)
    interest_doc = ctx.one(DOC_INTEREST_BY_YEAR)
    roster = ctx.one(DOC_PROJECT_STATUS)
    if interest_doc is None or roster is None:
        return []
    counted = len(_roster_keys(ctx))
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            "interest_by_year.project_count",
            interest_doc.get("project_count"),
            unit="a whole count",
        )
        if stated != counted:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(interest_doc, "project_count"),
                    f"the schedule states {stated} project(s); the roster carries {counted}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the stated project count of {counted} ties the roster",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one capitalization file."""
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
    """Analyze every ``.json`` capitalization file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of capitalization-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
