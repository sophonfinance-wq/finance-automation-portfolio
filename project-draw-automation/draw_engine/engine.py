"""
Project draw control engine (READ-ONLY).
========================================

Loads each draw package (a ``.json`` file produced by
:mod:`draw_engine.generate`) and runs an ordered *registry* of independent
controls over it. Every check returns zero or more
:class:`~draw_engine.model.Finding` objects; the per-package findings roll up
into a :class:`~draw_engine.model.DocumentReport` with an overall
:class:`~draw_engine.model.Verdict`.

The registry opens with ``set_*``, the structural precondition -- is the package
complete enough to be worth reading? -- and then answers the questions a lender,
an auditor and a controller each ask of the same document:

1. ``recon_*`` -- do cumulative draws equal cumulative costs?
2. ``form_*``  -- does the form the lender receives agree with the working paper?
3. ``cont_*``  -- was contingency drawn only as fast as the work was earned?
4. ``cut_*``   -- were the costs actually incurred inside the period being billed?
5. ``acc_*``   -- were accruals used within policy, and reversed afterwards?
6. ``doc_*``   -- is the package supportable: signed, backed up, complete?
7. ``fund_*``  -- did the money arrive, and was a late draw chased?

Design notes
------------
- **Strictly read-only.** Packages are parsed and never written back. The engine
  is incapable of *introducing* a defect -- it can only report.
- **Deterministic.** Same inputs, same findings, in the same order. Every glob,
  dict and set iteration is forced through ``sorted()`` with a tiebreaker.
- **Integer cents, no tolerance.** Amounts are compared with exact ``==``. A
  value that should be integer cents but is not produces an ``AMOUNT_INVALID``
  finding -- at the owning rule's declared severity, contained to the one row it
  was read on -- rather than being coerced.
- **Absent evidence is not a passing control.** ``set_complete`` runs first and
  fails a package that does not carry every artifact type the registry reads.
- **Extensible.** A check is a function ``(Context) -> list[Finding]``
  registered by the :func:`check` decorator. New rules drop into
  :data:`REGISTRY` without touching the runner.

The reconciliation identity
---------------------------
The core of a draw is one equation. Fundings to date (A) plus the draw being
requested now (B) must equal total draws to date (C); and C must equal costs to
date net of retention (D). ``C - D == 0`` is the whole control in one line, and
every other reconciliation rule here exists to localise *why* it broke when it
does -- a category that does not foot, a retention release moved in one schedule
and not the other, a funding total that has drifted from the ledger.

Retention deserves its own note, because it is where the sign conventions bite.
Retention withheld is carried as a **negative** number in its own column. When it
is finally billed, it does not simply disappear: it leaves the retention column
and reappears in the current period as a **positive** amount. A package that
removes it from one place without adding it to the other still foots on the page
the accountant is looking at, and breaks the identity on the page they are not.
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
    COST_CLASSES,
    DOC_COST_DETAIL,
    DOC_CYCLE_CALENDAR,
    DOC_DRAW_REQUEST,
    DOC_FUNDING_LEDGER,
    DOC_JC_RECONCILIATION,
    DOC_SUPPORT_INDEX,
    DOC_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import (
    AmountInvalidError,
    fmt,
    fmt_bps,
    percent_complete_bps,
    require_cents,
    total,
)

# --------------------------------------------------------------------------- #
# Check registry
# --------------------------------------------------------------------------- #
CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs. Order is preserved so the
#: report is deterministic.
REGISTRY: list[tuple[str, CheckFn]] = []


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~draw_engine.money.AmountInvalidError` as a finding.

    The status is the rule's **declared** severity, read from :data:`SEVERITY` at
    call time. A malformed amount is evidence about the rule that read it, so it
    cannot be more severe than the control itself: a FLAG-only rule that
    hard-coded FAIL here would escalate a whole package from REVIEW to FAIL on a
    schema defect. An unregistered rule falls back to FAIL.
    """
    return Finding(
        rule_id,
        SEVERITY.get(rule_id, Status.FAIL),
        f"amount:{exc.field}",
        f"{exc} -- amounts are integer cents and are never coerced",
    )


@contextlib.contextmanager
def amount_guard(rule_id: str, out: list[Finding]) -> Iterator[None]:
    """Contain a malformed amount to the **one row** being read.

    A check wraps each line, transaction or funding row in this guard so a single
    bad amount costs that row and no more. Guarding the whole check body instead
    would abort the remaining iterations silently -- one malformed
    ``request_this_period_cents`` would end the cross-foot for an entire form,
    and the report would show no exception for the lines never examined.
    """
    try:
        yield
    except AmountInvalidError as exc:
        out.append(amount_invalid_finding(rule_id, exc))


def check(rule_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register ``fn`` in :data:`REGISTRY` under ``rule_id``.

    The wrapper is the last-resort net for an
    :class:`~draw_engine.money.AmountInvalidError` raised outside any per-row
    :func:`amount_guard`, so a malformed amount anywhere in a package surfaces as
    an ``AMOUNT_INVALID`` exception on the owning rule -- at that rule's declared
    severity -- instead of crashing the run.
    """

    def wrapper(fn: CheckFn) -> CheckFn:
        @functools.wraps(fn)
        def guarded(ctx: Context) -> list[Finding]:
            try:
                return fn(ctx)
            except AmountInvalidError as exc:
                # SEVERITY is defined below this decorator, so the lookup has to
                # happen here, at call time, not when the rule is registered.
                return [amount_invalid_finding(rule_id, exc)]

        REGISTRY.append((rule_id, guarded))
        return guarded

    return wrapper


# --------------------------------------------------------------------------- #
# Rule configuration (kept here so checks stay declarative)
# --------------------------------------------------------------------------- #
#: Declared severity of every rule. Read by :func:`amount_invalid_finding` so a
#: schema defect can never be more severe than the control that tripped over it.
SEVERITY: dict[str, Status] = {}

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sev(rule_id: str, status: Status) -> Status:
    """Declare and return a rule's severity."""
    SEVERITY[rule_id] = status
    return status


def _parse_date(value: object) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` string, or return ``None``.

    Returning ``None`` rather than raising keeps date hygiene the business of the
    rule that reads the field: a missing cutoff is a different finding from a
    malformed one, and only the calling rule knows which of the two it is
    looking at.
    """
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _period_bounds(period: str) -> tuple[date, date] | None:
    """Return the first and last day of a ``YYYY-MM`` period."""
    if not _PERIOD_RE.match(period):
        return None
    year, month = int(period[:4]), int(period[5:7])
    first = date(year, month, 1)
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    return first, nxt - timedelta(days=1)


def _rows(doc: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    """Return a list-of-dicts field from a document, defensively."""
    if not isinstance(doc, dict):
        return []
    rows = doc.get(key)
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _totals(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Return a document's ``totals`` mapping, defensively."""
    if not isinstance(doc, dict):
        return {}
    t = doc.get("totals")
    return t if isinstance(t, dict) else {}


# --------------------------------------------------------------------------- #
# 1. set_* -- structural preconditions
# --------------------------------------------------------------------------- #
@check("set_complete")
def set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the registry reads must be present.

    This runs first and exists so that absence is never mistaken for compliance.
    A package missing its cost detail would otherwise sail through the tie-out
    rules -- there would be nothing to disagree with the form, and every
    comparison would vacuously hold.
    """
    rule = "set_complete"
    _sev(rule, Status.FAIL)
    out: list[Finding] = []
    for doc_type in DOC_TYPES:
        found = ctx.docs(doc_type)
        if not found:
            out.append(Finding(rule, Status.FAIL, f"package:{ctx.package_id}/{doc_type}",
                               f"package carries no {doc_type}; absent evidence is not "
                               f"a passing control, so no downstream rule may read it"))
        elif len(found) > 1:
            out.append(Finding(rule, Status.FAIL, f"package:{ctx.package_id}/{doc_type}",
                               f"package carries {len(found)} {doc_type} documents; "
                               f"exactly one is expected and the rules read the first"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(DOC_TYPES)} artifact types present exactly once"))
    return out


@check("set_period_aligned")
def set_period_aligned(ctx: Context) -> list[Finding]:
    """Every dated artifact must describe the same accounting period.

    A draw assembled from a reconciliation for one month and a calendar for
    another will tie internally and still bill the lender for the wrong period.
    """
    rule = "set_period_aligned"
    _sev(rule, Status.FAIL)
    out: list[Finding] = []
    if not _PERIOD_RE.match(ctx.period):
        return [Finding(rule, Status.FAIL, f"package:{ctx.package_id}/period",
                        f"package period {ctx.period!r} is not a YYYY-MM label")]
    for doc in ctx.documents:
        declared = doc.get("period")
        if declared is not None and declared != ctx.period:
            out.append(Finding(rule, Status.FAIL, ctx.loc(doc, "period"),
                               f"document period {declared!r} does not match the "
                               f"package period {ctx.period!r}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"every dated artifact declares period {ctx.period}"))
    return out


# --------------------------------------------------------------------------- #
# 2. recon_* -- the job-cost-to-draw reconciliation
# --------------------------------------------------------------------------- #
@check("recon_total_is_prior_plus_current")
def recon_total_is_prior_plus_current(ctx: Context) -> list[Finding]:
    """A + B == C: prior fundings plus this draw equal total draws to date."""
    rule = "recon_total_is_prior_plus_current"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_JC_RECONCILIATION)
    if doc is None:
        return []
    t = _totals(doc)
    prior = require_cents("recon.totals.prior_funding_cents", t.get("prior_funding_cents"))
    current = require_cents("recon.totals.current_draw_cents", t.get("current_draw_cents"))
    declared = require_cents("recon.totals.total_draws_to_date_cents",
                             t.get("total_draws_to_date_cents"))
    if prior + current != declared:
        return [Finding(rule, Status.FAIL, ctx.loc(doc, "totals/total_draws_to_date_cents"),
                        f"prior fundings {fmt(prior)} + current draw {fmt(current)} = "
                        f"{fmt(prior + current)}, but total draws to date is declared "
                        f"as {fmt(declared)} (difference {fmt(prior + current - declared)})")]
    return [Finding(rule, Status.PASS, "-",
                    f"{fmt(prior)} + {fmt(current)} = {fmt(declared)}")]


@check("recon_draws_tie_costs")
def recon_draws_tie_costs(ctx: Context) -> list[Finding]:
    """C - D == 0: total draws to date equal costs to date net of retention.

    This is the identity the whole package exists to demonstrate. If it does not
    hold, the project has either drawn money it has not spent or spent money it
    has not drawn, and no amount of internal footing elsewhere makes the request
    supportable.
    """
    rule = "recon_draws_tie_costs"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_JC_RECONCILIATION)
    if doc is None:
        return []
    t = _totals(doc)
    draws = require_cents("recon.totals.total_draws_to_date_cents",
                          t.get("total_draws_to_date_cents"))
    costs = require_cents("recon.totals.costs_to_date_net_retention_cents",
                          t.get("costs_to_date_net_retention_cents"))
    diff = draws - costs
    if diff != 0:
        return [Finding(rule, Status.FAIL, ctx.loc(doc, "totals"),
                        f"total draws to date {fmt(draws)} less costs to date net of "
                        f"retention {fmt(costs)} = {fmt(diff)}; this identity must be "
                        f"exactly zero for the draw to be supportable")]
    return [Finding(rule, Status.PASS, "-",
                    f"draws to date tie costs to date exactly at {fmt(draws)}")]


@check("recon_categories_foot")
def recon_categories_foot(ctx: Context) -> list[Finding]:
    """Every reconciliation column must foot from its category rows.

    Checked column by column so a break localises to the column that carries it
    rather than reporting one undifferentiated "does not foot".
    """
    rule = "recon_categories_foot"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_JC_RECONCILIATION)
    if doc is None:
        return []
    rows = _rows(doc, "categories")
    if not rows:
        return [Finding(rule, Status.FAIL, ctx.loc(doc, "categories"),
                        "reconciliation carries no category rows to foot")]
    t = _totals(doc)
    out: list[Finding] = []
    columns = (
        ("prior_funding_cents", "prior funding"),
        ("current_draw_cents", "current draw"),
        ("costs_to_date_cents", "costs to date"),
        ("retention_withheld_cents", "retention withheld"),
    )
    for key, label in columns:
        summed = 0
        readable = True
        for row in rows:
            try:
                summed += require_cents(f"recon.categories[{row.get('code')}].{key}",
                                        row.get(key))
            except AmountInvalidError as exc:
                out.append(amount_invalid_finding(rule, exc))
                readable = False
        if not readable:
            continue
        with amount_guard(rule, out):
            declared = require_cents(f"recon.totals.{key}", t.get(key))
            if summed != declared:
                out.append(Finding(rule, Status.FAIL, ctx.loc(doc, f"totals/{key}"),
                                   f"{label}: category rows sum to {fmt(summed)} but the "
                                   f"total row declares {fmt(declared)} "
                                   f"(difference {fmt(summed - declared)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(columns)} columns foot across {len(rows)} categories"))
    return out


@check("recon_retention_sign")
def recon_retention_sign(ctx: Context) -> list[Finding]:
    """Retention withheld is carried as a negative amount.

    The sign is the convention that makes the identity work: retention reduces
    what may be drawn. A positive value in this column inflates costs to date and
    would licence a draw against money the owner is still holding back.
    """
    rule = "recon_retention_sign"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_JC_RECONCILIATION)
    if doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _rows(doc, "categories"):
        with amount_guard(rule, out):
            held = require_cents(
                f"recon.categories[{row.get('code')}].retention_withheld_cents",
                row.get("retention_withheld_cents"))
            checked += 1
            if held > 0:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"categories/{row.get('code')}/retention_withheld_cents"),
                                   f"retention withheld is {fmt(held)}, a positive amount; "
                                   f"withheld retention reduces what may be drawn and is "
                                   f"carried negative"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"retention withheld is non-positive across {checked} categories"))
    return out


@check("recon_retention_release_moved")
def recon_retention_release_moved(ctx: Context) -> list[Finding]:
    """Released retention must leave the retention column and enter this period.

    This is the reconciliation's most common silent break. Retention billed in
    the current period is removed from the retention column and added to the
    current period column as a positive amount. A package that does one and not
    the other still foots on the page being read and breaks ``C - D`` on the page
    that is not.
    """
    rule = "recon_retention_release_moved"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_JC_RECONCILIATION)
    if doc is None:
        return []
    out: list[Finding] = []
    released_total = 0
    for row in _rows(doc, "categories"):
        with amount_guard(rule, out):
            released = require_cents(
                f"recon.categories[{row.get('code')}].retention_billed_current_cents",
                row.get("retention_billed_current_cents"))
            if released < 0:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"categories/{row.get('code')}/retention_billed_current_cents"),
                                   f"retention billed this period is {fmt(released)}; a "
                                   f"release is a positive amount moving into the current "
                                   f"period"))
                continue
            released_total += released
            if released and not row.get("retention_release_reflected_in_current", False):
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"categories/{row.get('code')}/retention_billed_current_cents"),
                                   f"{fmt(released)} of retention was released but the "
                                   f"current period column does not carry it; the release "
                                   f"must move, not merely disappear from retention"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"retention releases totalling {fmt(released_total)} are "
                           f"reflected in the current period"))
    return out


@check("recon_funding_ties_ledger")
def recon_funding_ties_ledger(ctx: Context) -> list[Finding]:
    """Equity and debt funding totals must tie to the general ledger.

    The reconciliation is a working paper; the ledger is the book of record. When
    they disagree the working paper is wrong until proven otherwise, which is why
    this is a failure rather than a flag.
    """
    rule = "recon_funding_ties_ledger"
    _sev(rule, Status.FAIL)
    recon = ctx.one(DOC_JC_RECONCILIATION)
    ledger = ctx.one(DOC_FUNDING_LEDGER)
    if recon is None or ledger is None:
        return []
    out: list[Finding] = []
    pairs = (
        ("ledger_equity_funding_cents", "gl_equity_balance_cents", "equity"),
        ("ledger_debt_funding_cents", "gl_debt_balance_cents", "debt"),
    )
    for recon_key, gl_key, label in pairs:
        with amount_guard(rule, out):
            claimed = require_cents(f"recon.{recon_key}", recon.get(recon_key))
            actual = require_cents(f"funding_ledger.{gl_key}", ledger.get(gl_key))
            if claimed != actual:
                out.append(Finding(rule, Status.FAIL, ctx.loc(recon, recon_key),
                                   f"{label} funding per the reconciliation is "
                                   f"{fmt(claimed)} but the ledger balance is "
                                   f"{fmt(actual)} (difference {fmt(claimed - actual)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "equity and debt funding both tie to the ledger"))
    return out


@check("recon_funding_rows_foot")
def recon_funding_rows_foot(ctx: Context) -> list[Finding]:
    """Individual funding events must sum to the ledger balances they support."""
    rule = "recon_funding_rows_foot"
    _sev(rule, Status.FAIL)
    ledger = ctx.one(DOC_FUNDING_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    sums = {"equity": 0, "debt": 0}
    for row in _rows(ledger, "fundings"):
        source = row.get("source")
        if source not in sums:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(ledger, f"fundings/{row.get('month')}/source"),
                               f"funding source {source!r} is neither equity nor debt"))
            continue
        with amount_guard(rule, out):
            sums[source] += require_cents(
                f"funding_ledger.fundings[{row.get('month')}].amount_cents",
                row.get("amount_cents"))
    for source, gl_key in (("equity", "gl_equity_balance_cents"),
                           ("debt", "gl_debt_balance_cents")):
        with amount_guard(rule, out):
            declared = require_cents(f"funding_ledger.{gl_key}", ledger.get(gl_key))
            if sums[source] != declared:
                out.append(Finding(rule, Status.FAIL, ctx.loc(ledger, gl_key),
                                   f"{source} funding events sum to {fmt(sums[source])} "
                                   f"but the ledger balance is {fmt(declared)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"funding events foot to both ledger balances"))
    return out


@check("recon_variance_explained")
def recon_variance_explained(ctx: Context) -> list[Finding]:
    """Any declared variance must carry an explanation.

    The procedure permits a variance to exist; it does not permit one to be
    unexplained. This is a flag rather than a failure because the explanation is
    a judgment the reviewer makes, not a number the engine can derive.
    """
    rule = "recon_variance_explained"
    _sev(rule, Status.FLAG)
    doc = ctx.one(DOC_JC_RECONCILIATION)
    if doc is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        variance = require_cents("recon.variance_cents", doc.get("variance_cents"))
        explanation = doc.get("variance_explanation")
        has_text = isinstance(explanation, str) and explanation.strip() != ""
        if variance != 0 and not has_text:
            out.append(Finding(rule, Status.FLAG, ctx.loc(doc, "variance_explanation"),
                               f"a variance of {fmt(variance)} is declared with no "
                               f"explanation; the project accountant must be able to "
                               f"explain any variance"))
        elif variance == 0 and has_text:
            out.append(Finding(rule, Status.FLAG, ctx.loc(doc, "variance_explanation"),
                               "an explanation is recorded against a zero variance; one "
                               "of the two is stale"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "variance and explanation agree"))
    return out


# --------------------------------------------------------------------------- #
# 3. form_* -- the lender's draw request form
# --------------------------------------------------------------------------- #
@check("form_lines_crossfoot")
def form_lines_crossfoot(ctx: Context) -> list[Finding]:
    """Each line's disbursed-to-date must equal previous plus this request."""
    rule = "form_lines_crossfoot"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_DRAW_REQUEST)
    if doc is None:
        return []
    out: list[Finding] = []
    lines = _rows(doc, "lines")
    for line in lines:
        code = line.get("code")
        with amount_guard(rule, out):
            prev = require_cents(f"form.lines[{code}].previous_applications_cents",
                                 line.get("previous_applications_cents"))
            req = require_cents(f"form.lines[{code}].request_this_period_cents",
                                line.get("request_this_period_cents"))
            disb = require_cents(f"form.lines[{code}].total_disbursed_to_date_cents",
                                 line.get("total_disbursed_to_date_cents"))
            if prev + req != disb:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"lines/{code}/total_disbursed_to_date_cents"),
                                   f"line {code}: previous {fmt(prev)} + this period "
                                   f"{fmt(req)} = {fmt(prev + req)}, but disbursed to date "
                                   f"is {fmt(disb)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(lines)} lines cross-foot"))
    return out


@check("form_remaining_is_budget_less_disbursed")
def form_remaining_is_budget_less_disbursed(ctx: Context) -> list[Finding]:
    """Remaining funds must equal revised budget less total disbursed to date."""
    rule = "form_remaining_is_budget_less_disbursed"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_DRAW_REQUEST)
    if doc is None:
        return []
    out: list[Finding] = []
    lines = _rows(doc, "lines")
    for line in lines:
        code = line.get("code")
        with amount_guard(rule, out):
            revised = require_cents(f"form.lines[{code}].revised_budget_cents",
                                    line.get("revised_budget_cents"))
            disb = require_cents(f"form.lines[{code}].total_disbursed_to_date_cents",
                                 line.get("total_disbursed_to_date_cents"))
            remaining = require_cents(f"form.lines[{code}].remaining_funds_cents",
                                      line.get("remaining_funds_cents"))
            if revised - disb != remaining:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"lines/{code}/remaining_funds_cents"),
                                   f"line {code}: revised budget {fmt(revised)} less "
                                   f"disbursed {fmt(disb)} = {fmt(revised - disb)}, but "
                                   f"remaining funds is stated as {fmt(remaining)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"remaining funds derives correctly on all {len(lines)} lines"))
    return out


@check("form_revised_budget_is_original_plus_adjustments")
def form_revised_budget_is_original_plus_adjustments(ctx: Context) -> list[Finding]:
    """Revised budget must equal the original budget plus declared adjustments.

    A revised budget that cannot be derived from an adjustment trail is a budget
    that moved without a decision behind it.
    """
    rule = "form_revised_budget_is_original_plus_adjustments"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_DRAW_REQUEST)
    if doc is None:
        return []
    out: list[Finding] = []
    lines = _rows(doc, "lines")
    for line in lines:
        code = line.get("code")
        with amount_guard(rule, out):
            original = require_cents(f"form.lines[{code}].original_budget_cents",
                                     line.get("original_budget_cents"))
            adj = require_cents(f"form.lines[{code}].budget_adjustments_cents",
                                line.get("budget_adjustments_cents"))
            revised = require_cents(f"form.lines[{code}].revised_budget_cents",
                                    line.get("revised_budget_cents"))
            if original + adj != revised:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"lines/{code}/revised_budget_cents"),
                                   f"line {code}: original {fmt(original)} + adjustments "
                                   f"{fmt(adj)} = {fmt(original + adj)}, but the revised "
                                   f"budget is {fmt(revised)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"revised budget derives from adjustments on {len(lines)} lines"))
    return out


@check("form_columns_foot")
def form_columns_foot(ctx: Context) -> list[Finding]:
    """Every form column total must foot from its own lines."""
    rule = "form_columns_foot"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_DRAW_REQUEST)
    if doc is None:
        return []
    out: list[Finding] = []
    lines = _rows(doc, "lines")
    if not lines:
        return [Finding(rule, Status.FAIL, ctx.loc(doc, "lines"),
                        "draw request form carries no lines to foot")]
    t = _totals(doc)
    columns = (
        ("original_budget_cents", "original budget"),
        ("budget_adjustments_cents", "budget adjustments"),
        ("revised_budget_cents", "revised budget"),
        ("previous_applications_cents", "previous applications"),
        ("request_this_period_cents", "request this period"),
        ("total_disbursed_to_date_cents", "total disbursed to date"),
        ("remaining_funds_cents", "remaining funds"),
    )
    for key, label in columns:
        summed = 0
        readable = True
        for line in lines:
            try:
                summed += require_cents(f"form.lines[{line.get('code')}].{key}",
                                        line.get(key))
            except AmountInvalidError as exc:
                out.append(amount_invalid_finding(rule, exc))
                readable = False
        if not readable:
            continue
        with amount_guard(rule, out):
            declared = require_cents(f"form.totals.{key}", t.get(key))
            if summed != declared:
                out.append(Finding(rule, Status.FAIL, ctx.loc(doc, f"totals/{key}"),
                                   f"{label}: lines sum to {fmt(summed)} but the total "
                                   f"row declares {fmt(declared)} "
                                   f"(difference {fmt(summed - declared)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(columns)} column totals foot across {len(lines)} lines"))
    return out


@check("form_disbursed_ties_recon")
def form_disbursed_ties_recon(ctx: Context) -> list[Finding]:
    """Total disbursed to date on the form must match the reconciliation.

    The form is what the lender sees; the reconciliation is what supports it. If
    the two disagree the package is internally inconsistent, and whichever
    number is right the other one is a misstatement to a lender.
    """
    rule = "form_disbursed_ties_recon"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_DRAW_REQUEST)
    recon = ctx.one(DOC_JC_RECONCILIATION)
    if form is None or recon is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        on_form = require_cents("form.totals.total_disbursed_to_date_cents",
                                _totals(form).get("total_disbursed_to_date_cents"))
        on_recon = require_cents("recon.totals.total_draws_to_date_cents",
                                 _totals(recon).get("total_draws_to_date_cents"))
        if on_form != on_recon:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(form, "totals/total_disbursed_to_date_cents"),
                               f"form shows {fmt(on_form)} disbursed to date; the "
                               f"reconciliation supporting it shows {fmt(on_recon)} "
                               f"(difference {fmt(on_form - on_recon)})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "form and reconciliation agree on disbursed to date"))
    return out


@check("form_previous_ties_trial_balance")
def form_previous_ties_trial_balance(ctx: Context) -> list[Finding]:
    """Previous applications must tie back to the trial balance."""
    rule = "form_previous_ties_trial_balance"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_DRAW_REQUEST)
    ledger = ctx.one(DOC_FUNDING_LEDGER)
    if form is None or ledger is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        on_form = require_cents("form.totals.previous_applications_cents",
                                _totals(form).get("previous_applications_cents"))
        on_tb = require_cents("funding_ledger.trial_balance_previous_applications_cents",
                              ledger.get("trial_balance_previous_applications_cents"))
        if on_form != on_tb:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(form, "totals/previous_applications_cents"),
                               f"previous applications on the form total {fmt(on_form)} "
                               f"but the trial balance carries {fmt(on_tb)}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           "previous applications tie to the trial balance"))
    return out


@check("form_request_ties_cost_detail")
def form_request_ties_cost_detail(ctx: Context) -> list[Finding]:
    """This period's request must equal the cost detail, subtotaled by category.

    Compared per category rather than in total, because two categories that are
    wrong in opposite directions net to a total that looks right.
    """
    rule = "form_request_ties_cost_detail"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_DRAW_REQUEST)
    detail = ctx.one(DOC_COST_DETAIL)
    if form is None or detail is None:
        return []
    out: list[Finding] = []
    by_code: dict[str, int] = {}
    for txn in _rows(detail, "transactions"):
        code = str(txn.get("code"))
        with amount_guard(rule, out):
            by_code[code] = by_code.get(code, 0) + require_cents(
                f"cost_detail.transactions[{txn.get('txn_id')}].amount_cents",
                txn.get("amount_cents"))
    seen: set[str] = set()
    for line in _rows(form, "lines"):
        code = str(line.get("code"))
        seen.add(code)
        with amount_guard(rule, out):
            requested = require_cents(f"form.lines[{code}].request_this_period_cents",
                                      line.get("request_this_period_cents"))
            detailed = by_code.get(code, 0)
            if requested != detailed:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(form, f"lines/{code}/request_this_period_cents"),
                                   f"line {code} requests {fmt(requested)} this period but "
                                   f"the transaction detail subtotals {fmt(detailed)} for "
                                   f"that category"))
    for code in sorted(set(by_code) - seen):
        out.append(Finding(rule, Status.FAIL, ctx.loc(detail, f"transactions/{code}"),
                           f"category {code} carries {fmt(by_code[code])} of current-period "
                           f"cost but appears on no line of the draw request form"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"request this period ties to cost detail across "
                           f"{len(seen)} categories"))
    return out


@check("form_no_negative_remaining")
def form_no_negative_remaining(ctx: Context) -> list[Finding]:
    """No line may show negative funds remaining.

    A negative remaining balance means the line is over budget and the draw is
    asking a lender to fund past its own commitment. The procedure requires it be
    corrected with a current-period budget adjustment before submittal, not
    explained afterwards.
    """
    rule = "form_no_negative_remaining"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_DRAW_REQUEST)
    if doc is None:
        return []
    out: list[Finding] = []
    lines = _rows(doc, "lines")
    for line in lines:
        code = line.get("code")
        with amount_guard(rule, out):
            remaining = require_cents(f"form.lines[{code}].remaining_funds_cents",
                                      line.get("remaining_funds_cents"))
            if remaining < 0:
                adj = line.get("budget_adjustments_cents")
                corrected = isinstance(adj, int) and not isinstance(adj, bool) and adj != 0
                detail = (" a budget adjustment is present but has not cleared the "
                          "shortfall" if corrected else
                          " no current-period budget adjustment has been made")
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"lines/{code}/remaining_funds_cents"),
                                   f"line {code} shows {fmt(remaining)} remaining, i.e. it "
                                   f"is over budget;{detail}"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"no negative funds to complete across {len(lines)} lines"))
    return out


# --------------------------------------------------------------------------- #
# 4. cont_* -- contingency discipline
# --------------------------------------------------------------------------- #
@check("cont_within_percent_complete")
def cont_within_percent_complete(ctx: Context) -> list[Finding]:
    """Contingency may only be drawn up to the percent complete of its class.

    Hard-cost contingency is capped at the actual percent complete of hard costs,
    and soft-cost contingency at the percent complete of soft costs -- computed
    by comparing actual costs against budget for the non-contingency lines of
    that class. The two classes are governed separately and deliberately: a
    project that is 80% through its sitework has not thereby earned the right to
    spend its soft-cost contingency.

    Drawing contingency faster than the work is earned is how a project arrives
    at its final draw with nothing left to fund the work that remains.
    """
    rule = "cont_within_percent_complete"
    _sev(rule, Status.FAIL)
    doc = ctx.one(DOC_DRAW_REQUEST)
    if doc is None:
        return []
    out: list[Finding] = []
    lines = _rows(doc, "lines")

    # Percent complete is measured on the productive lines only. Including the
    # contingency line in its own denominator would let a project manufacture
    # entitlement by drawing contingency: spending it would raise the measured
    # progress that authorises spending it.
    progress: dict[str, int] = {}
    for cost_class in COST_CLASSES:
        actual = 0
        budget = 0
        readable = True
        for line in lines:
            if line.get("cost_class") != cost_class or line.get("is_contingency"):
                continue
            try:
                actual += require_cents(
                    f"form.lines[{line.get('code')}].total_disbursed_to_date_cents",
                    line.get("total_disbursed_to_date_cents"))
                budget += require_cents(
                    f"form.lines[{line.get('code')}].revised_budget_cents",
                    line.get("revised_budget_cents"))
            except AmountInvalidError as exc:
                out.append(amount_invalid_finding(rule, exc))
                readable = False
        if readable:
            progress[cost_class] = percent_complete_bps(actual, budget)

    checked = 0
    for line in lines:
        if not line.get("is_contingency"):
            continue
        cost_class = line.get("cost_class")
        if cost_class not in progress:
            continue
        code = line.get("code")
        with amount_guard(rule, out):
            original = require_cents(f"form.lines[{code}].original_budget_cents",
                                     line.get("original_budget_cents"))
            drawn = require_cents(f"form.lines[{code}].total_disbursed_to_date_cents",
                                  line.get("total_disbursed_to_date_cents"))
            checked += 1
            ceiling = original * progress[cost_class] // 10000
            if drawn > ceiling:
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(doc, f"lines/{code}/total_disbursed_to_date_cents"),
                                   f"{cost_class}-cost contingency {code} has drawn "
                                   f"{fmt(drawn)} against a ceiling of {fmt(ceiling)} "
                                   f"({fmt_bps(progress[cost_class])} complete of "
                                   f"{fmt(original)} original contingency); contingency may "
                                   f"only be used on a percent-complete basis"))
    if not out:
        detail = ", ".join(f"{c} {fmt_bps(progress[c])}" for c in sorted(progress))
        out.append(Finding(rule, Status.PASS, "-",
                           f"{checked} contingency line(s) within their percent-complete "
                           f"ceiling ({detail})"))
    return out


@check("cont_not_negative")
def cont_not_negative(ctx: Context) -> list[Finding]:
    """A contingency line may not be drawn below zero remaining.

    Distinct from ``form_no_negative_remaining`` in intent: contingency is the
    line every other overrun is transferred into, so it is the line most likely
    to be quietly exhausted. It gets its own control so the report says
    "contingency is spent" rather than the generic "a line is over budget".
    """
    rule = "cont_not_negative"
    _sev(rule, Status.FLAG)
    doc = ctx.one(DOC_DRAW_REQUEST)
    if doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for line in _rows(doc, "lines"):
        if not line.get("is_contingency"):
            continue
        code = line.get("code")
        with amount_guard(rule, out):
            revised = require_cents(f"form.lines[{code}].revised_budget_cents",
                                    line.get("revised_budget_cents"))
            drawn = require_cents(f"form.lines[{code}].total_disbursed_to_date_cents",
                                  line.get("total_disbursed_to_date_cents"))
            checked += 1
            if revised > 0 and drawn * 10000 // revised >= 9000:
                out.append(Finding(rule, Status.FLAG,
                                   ctx.loc(doc, f"lines/{code}/total_disbursed_to_date_cents"),
                                   f"contingency {code} is {fmt_bps(drawn * 10000 // revised)} "
                                   f"consumed ({fmt(drawn)} of {fmt(revised)}); the project "
                                   f"has little left to absorb a further overrun"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"{checked} contingency line(s) retain headroom"))
    return out


# --------------------------------------------------------------------------- #
# 5. cut_* -- cycle and cutoff compliance
# --------------------------------------------------------------------------- #
@check("cut_costs_inside_period")
def cut_costs_inside_period(ctx: Context) -> list[Finding]:
    """Every cost billed must have an accounting date inside the draw period.

    The draw submits costs approved and posted **to the calendar month**. A cost
    dated outside it is either being billed twice or billed early.
    """
    rule = "cut_costs_inside_period"
    _sev(rule, Status.FAIL)
    detail = ctx.one(DOC_COST_DETAIL)
    if detail is None:
        return []
    bounds = _period_bounds(ctx.period)
    if bounds is None:
        return []
    first, last = bounds
    out: list[Finding] = []
    checked = 0
    for txn in _rows(detail, "transactions"):
        txn_id = txn.get("txn_id")
        acct = _parse_date(txn.get("accounting_date"))
        if acct is None:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(detail, f"transactions/{txn_id}/accounting_date"),
                               f"transaction {txn_id} has no readable accounting date"))
            continue
        checked += 1
        if not (first <= acct <= last):
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(detail, f"transactions/{txn_id}/accounting_date"),
                               f"transaction {txn_id} is dated {acct.isoformat()}, outside "
                               f"the draw period {ctx.period} "
                               f"({first.isoformat()}..{last.isoformat()})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} transactions fall inside {ctx.period}"))
    return out


@check("cut_posted_by_deadline")
def cut_posted_by_deadline(ctx: Context) -> list[Finding]:
    """Every cost billed must have been posted by the posting deadline.

    The cycle allows costs received through month end to be approved and posted
    by the third of the following month. Anything posted later belongs to the
    next draw; billing it now is what creates the reconciliation break that
    surfaces a month afterwards.
    """
    rule = "cut_posted_by_deadline"
    _sev(rule, Status.FAIL)
    detail = ctx.one(DOC_COST_DETAIL)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if detail is None or cal is None:
        return []
    deadline = _parse_date(cal.get("posting_deadline"))
    if deadline is None:
        return [Finding(rule, Status.FAIL, ctx.loc(cal, "posting_deadline"),
                        "cycle calendar carries no readable posting deadline, so no cost "
                        "in this package can be shown to have met it")]
    out: list[Finding] = []
    checked = 0
    for txn in _rows(detail, "transactions"):
        txn_id = txn.get("txn_id")
        posted = _parse_date(txn.get("posted_date"))
        if posted is None:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(detail, f"transactions/{txn_id}/posted_date"),
                               f"transaction {txn_id} has no readable posted date"))
            continue
        checked += 1
        if posted > deadline:
            out.append(Finding(rule, Status.FAIL,
                               ctx.loc(detail, f"transactions/{txn_id}/posted_date"),
                               f"transaction {txn_id} posted {posted.isoformat()}, after the "
                               f"{deadline.isoformat()} posting deadline; it belongs to the "
                               f"following draw"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} transactions posted by {deadline.isoformat()}"))
    return out


@check("cut_approvals_within_sla")
def cut_approvals_within_sla(ctx: Context) -> list[Finding]:
    """Approvers must clear their queue within the approval SLA.

    A flag, not a failure: a late approval that still landed before the posting
    deadline did not harm this draw. It is reported because the pattern is what
    pushes the *next* draw late.
    """
    rule = "cut_approvals_within_sla"
    _sev(rule, Status.FLAG)
    detail = ctx.one(DOC_COST_DETAIL)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if detail is None or cal is None:
        return []
    sla = cal.get("approval_sla_days")
    if not isinstance(sla, int) or isinstance(sla, bool):
        return [Finding(rule, Status.FLAG, ctx.loc(cal, "approval_sla_days"),
                        "cycle calendar declares no approval SLA in days")]
    out: list[Finding] = []
    checked = 0
    for txn in _rows(detail, "transactions"):
        txn_id = txn.get("txn_id")
        noticed = _parse_date(txn.get("approval_notice_date"))
        cleared = _parse_date(txn.get("approval_completed_date"))
        if noticed is None or cleared is None:
            continue
        checked += 1
        elapsed = (cleared - noticed).days
        if elapsed > sla:
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(detail, f"transactions/{txn_id}/approval_completed_date"),
                               f"transaction {txn_id} took {elapsed} days to approve against "
                               f"a {sla}-day SLA (notice {noticed.isoformat()}, cleared "
                               f"{cleared.isoformat()})"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {checked} approvals cleared within {sla} days"))
    return out


@check("cut_cycle_milestones_ordered")
def cut_cycle_milestones_ordered(ctx: Context) -> list[Finding]:
    """The cycle's milestones must fall in their intended order.

    Window opens, then costs cut off, then posting closes, then preparation
    starts, then the package is submitted. A package prepared before its own
    posting deadline was assembled from an incomplete ledger.
    """
    rule = "cut_cycle_milestones_ordered"
    _sev(rule, Status.FAIL)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if cal is None:
        return []
    sequence = ("window_opens", "cost_cutoff", "posting_deadline", "prep_start", "submitted")
    parsed: list[tuple[str, date]] = []
    out: list[Finding] = []
    for key in sequence:
        value = _parse_date(cal.get(key))
        if value is None:
            out.append(Finding(rule, Status.FAIL, ctx.loc(cal, key),
                               f"cycle milestone {key} is missing or unreadable"))
        else:
            parsed.append((key, value))
    for (prev_key, prev_date), (next_key, next_date) in zip(parsed, parsed[1:]):
        if next_date < prev_date:
            out.append(Finding(rule, Status.FAIL, ctx.loc(cal, next_key),
                               f"{next_key} ({next_date.isoformat()}) falls before "
                               f"{prev_key} ({prev_date.isoformat()}); the cycle cannot run "
                               f"in this order"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(sequence)} cycle milestones fall in order"))
    return out


@check("cut_submitted_by_target")
def cut_submitted_by_target(ctx: Context) -> list[Finding]:
    """The package should be submitted by the cycle's target date."""
    rule = "cut_submitted_by_target"
    _sev(rule, Status.FLAG)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if cal is None:
        return []
    submitted = _parse_date(cal.get("submitted"))
    target = _parse_date(cal.get("target_submit_by"))
    if submitted is None or target is None:
        return [Finding(rule, Status.FLAG, ctx.loc(cal, "submitted"),
                        "submittal date or its target is missing, so timeliness cannot be "
                        "demonstrated")]
    if submitted > target:
        return [Finding(rule, Status.FLAG, ctx.loc(cal, "submitted"),
                        f"submitted {submitted.isoformat()}, {(submitted - target).days} day(s) "
                        f"after the {target.isoformat()} target; late submittal pushes "
                        f"funding past the point where subcontractors can be paid on time")]
    return [Finding(rule, Status.PASS, "-",
                    f"submitted {submitted.isoformat()}, on or before target "
                    f"{target.isoformat()}")]


# --------------------------------------------------------------------------- #
# 6. acc_* -- accrual policy
# --------------------------------------------------------------------------- #
@check("acc_only_material")
def acc_only_material(ctx: Context) -> list[Finding]:
    """Accruals are permitted only above the materiality threshold.

    Accruing an unposted cost doubles the work of preparing the draw and creates
    a reconciliation item in the following month. The policy therefore restricts
    it to large amounts and to items that must be paid immediately -- an accrual
    below the threshold, with no such justification, is cost the cycle should
    simply have caught next month.
    """
    rule = "acc_only_material"
    _sev(rule, Status.FLAG)
    detail = ctx.one(DOC_COST_DETAIL)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if detail is None or cal is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        threshold = require_cents("cycle.accrual_materiality_cents",
                                  cal.get("accrual_materiality_cents"))
        accruals = 0
        for txn in _rows(detail, "transactions"):
            if not txn.get("is_accrual"):
                continue
            txn_id = txn.get("txn_id")
            with amount_guard(rule, out):
                amount = require_cents(
                    f"cost_detail.transactions[{txn_id}].amount_cents",
                    txn.get("amount_cents"))
                accruals += 1
                immediate = bool(txn.get("payment_required_immediately", False))
                if abs(amount) < threshold and not immediate:
                    out.append(Finding(rule, Status.FLAG,
                                       ctx.loc(detail, f"transactions/{txn_id}/is_accrual"),
                                       f"transaction {txn_id} is accrued at {fmt(amount)}, "
                                       f"below the {fmt(threshold)} materiality threshold, "
                                       f"and is not marked as requiring immediate payment"))
        if not out:
            out.append(Finding(rule, Status.PASS, "-",
                               f"{accruals} accrual(s) all material or payment-critical"))
    return out


@check("acc_prior_period_reversed")
def acc_prior_period_reversed(ctx: Context) -> list[Finding]:
    """Accruals raised in a prior draw must have been reversed.

    An accrual that is never reversed is billed twice: once when accrued and
    again when the real invoice posts.
    """
    rule = "acc_prior_period_reversed"
    _sev(rule, Status.FAIL)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if cal is None:
        return []
    out: list[Finding] = []
    rows = _rows(cal, "prior_period_accruals")
    for row in rows:
        txn_id = row.get("txn_id")
        if not row.get("reversed", False):
            with amount_guard(rule, out):
                amount = require_cents(
                    f"cycle.prior_period_accruals[{txn_id}].amount_cents",
                    row.get("amount_cents"))
                out.append(Finding(rule, Status.FAIL,
                                   ctx.loc(cal, f"prior_period_accruals/{txn_id}/reversed"),
                                   f"prior-period accrual {txn_id} of {fmt(amount)} has not "
                                   f"been reversed; when the invoice posts the cost will be "
                                   f"drawn twice"))
    if not out:
        out.append(Finding(rule, Status.PASS, "-",
                           f"all {len(rows)} prior-period accrual(s) reversed"))
    return out


# --------------------------------------------------------------------------- #
# 7. doc_* -- supporting documentation
# --------------------------------------------------------------------------- #
@check("doc_signed")
def doc_signed(ctx: Context) -> list[Finding]:
    """The draw request must be signed by an authorized signer."""
    rule = "doc_signed"
    _sev(rule, Status.FAIL)
    form = ctx.one(DOC_DRAW_REQUEST)
    support = ctx.one(DOC_SUPPORT_INDEX)
    if form is None or support is None:
        return []
    signer = form.get("signed_by")
    authorized = support.get("authorized_signers")
    authorized = authorized if isinstance(authorized, list) else []
    if not isinstance(signer, str) or not signer.strip():
        return [Finding(rule, Status.FAIL, ctx.loc(form, "signed_by"),
                        "the draw request carries no signature; almost every lender "
                        "requires the form or its summary to be signed before funding")]
    if signer not in authorized:
        return [Finding(rule, Status.FAIL, ctx.loc(form, "signed_by"),
                        f"the draw request is signed by {signer!r}, who is not on the "
                        f"authorized signer list ({', '.join(sorted(map(str, authorized))) or 'empty'})")]
    if _parse_date(form.get("signature_date")) is None:
        return [Finding(rule, Status.FAIL, ctx.loc(form, "signature_date"),
                        f"the signature by {signer!r} carries no readable date")]
    return [Finding(rule, Status.PASS, "-", f"signed by an authorized signer")]


@check("doc_backup_over_threshold")
def doc_backup_over_threshold(ctx: Context) -> list[Finding]:
    """Every transaction over the lender's threshold needs invoice backup.

    Most lenders require copies of invoices above a stated value. A missing copy
    does not merely delay funding -- it is one of the named conditions under
    which the lender is not obliged to fund at all.
    """
    rule = "doc_backup_over_threshold"
    _sev(rule, Status.FAIL)
    detail = ctx.one(DOC_COST_DETAIL)
    support = ctx.one(DOC_SUPPORT_INDEX)
    if detail is None or support is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        threshold = require_cents("support.invoice_backup_threshold_cents",
                                  support.get("invoice_backup_threshold_cents"))
        provided = support.get("backup_provided_txn_ids")
        provided_set = {str(x) for x in provided} if isinstance(provided, list) else set()
        required = 0
        for txn in _rows(detail, "transactions"):
            txn_id = str(txn.get("txn_id"))
            with amount_guard(rule, out):
                amount = require_cents(
                    f"cost_detail.transactions[{txn_id}].amount_cents",
                    txn.get("amount_cents"))
                if abs(amount) < threshold:
                    continue
                required += 1
                if txn_id not in provided_set:
                    out.append(Finding(rule, Status.FAIL,
                                       ctx.loc(support, f"backup_provided_txn_ids/{txn_id}"),
                                       f"transaction {txn_id} of {fmt(amount)} is at or above "
                                       f"the {fmt(threshold)} backup threshold but no invoice "
                                       f"copy is indexed in the package"))
        if not out:
            out.append(Finding(rule, Status.PASS, "-",
                               f"invoice backup indexed for all {required} transaction(s) "
                               f"at or above {fmt(threshold)}"))
    return out


@check("doc_schedule_of_values")
def doc_schedule_of_values(ctx: Context) -> list[Finding]:
    """Where the lender requires a schedule of values, it must be attached."""
    rule = "doc_schedule_of_values"
    _sev(rule, Status.FAIL)
    support = ctx.one(DOC_SUPPORT_INDEX)
    if support is None:
        return []
    required = bool(support.get("schedule_of_values_required", False))
    attached = bool(support.get("schedule_of_values_attached", False))
    if required and not attached:
        return [Finding(rule, Status.FAIL, ctx.loc(support, "schedule_of_values_attached"),
                        "this lender requires a schedule of values of committed values by "
                        "cost code and none is attached")]
    if not required and attached:
        return [Finding(rule, Status.PASS, "-",
                        "a schedule of values is attached though not required")]
    return [Finding(rule, Status.PASS, "-",
                    "schedule of values requirement satisfied" if required
                    else "no schedule of values required by this lender")]


@check("doc_distribution_complete")
def doc_distribution_complete(ctx: Context) -> list[Finding]:
    """The submittal must reach every required recipient.

    The lender contacts are the ones who fund it; the internal recipients are the
    ones who move the intercompany cash the day after it funds. A submittal that
    skips either does not fail arithmetically -- it just does not get paid.
    """
    rule = "doc_distribution_complete"
    _sev(rule, Status.FLAG)
    support = ctx.one(DOC_SUPPORT_INDEX)
    if support is None:
        return []
    required = support.get("required_recipients")
    actual = support.get("actual_recipients")
    required = [str(x) for x in required] if isinstance(required, list) else []
    actual_set = {str(x) for x in actual} if isinstance(actual, list) else set()
    missing = sorted(set(required) - actual_set)
    if missing:
        return [Finding(rule, Status.FLAG, ctx.loc(support, "actual_recipients"),
                        f"{len(missing)} required recipient(s) did not receive the "
                        f"submittal: {', '.join(missing)}")]
    return [Finding(rule, Status.PASS, "-",
                    f"all {len(required)} required recipients received the submittal")]


# --------------------------------------------------------------------------- #
# 8. fund_* -- funding and follow-up
# --------------------------------------------------------------------------- #
@check("fund_within_agreement_days")
def fund_within_agreement_days(ctx: Context) -> list[Finding]:
    """Funding must arrive within the loan agreement's stated window."""
    rule = "fund_within_agreement_days"
    _sev(rule, Status.FLAG)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if cal is None:
        return []
    submitted = _parse_date(cal.get("submitted"))
    funded = _parse_date(cal.get("funded"))
    max_days = cal.get("lender_funding_days_max")
    if submitted is None or not isinstance(max_days, int) or isinstance(max_days, bool):
        return [Finding(rule, Status.FLAG, ctx.loc(cal, "lender_funding_days_max"),
                        "submittal date or the agreement's funding window is missing")]
    if funded is None:
        return [Finding(rule, Status.FLAG, ctx.loc(cal, "funded"),
                        f"submitted {submitted.isoformat()} and not yet funded; the "
                        f"agreement allows {max_days} days")]
    elapsed = (funded - submitted).days
    if elapsed > max_days:
        return [Finding(rule, Status.FLAG, ctx.loc(cal, "funded"),
                        f"funded in {elapsed} days against a {max_days}-day agreement "
                        f"window ({submitted.isoformat()} to {funded.isoformat()})")]
    return [Finding(rule, Status.PASS, "-",
                    f"funded in {elapsed} days, within the {max_days}-day window")]


@check("fund_overdue_followed_up")
def fund_overdue_followed_up(ctx: Context) -> list[Finding]:
    """An overdue draw must have a follow-up on record.

    The procedure makes chasing the lender an explicit duty once the agreed
    window passes. This control only fires when the draw is actually late, so a
    package funded on time is never asked to evidence a chase it never needed.
    """
    rule = "fund_overdue_followed_up"
    _sev(rule, Status.FLAG)
    cal = ctx.one(DOC_CYCLE_CALENDAR)
    if cal is None:
        return []
    submitted = _parse_date(cal.get("submitted"))
    funded = _parse_date(cal.get("funded"))
    max_days = cal.get("lender_funding_days_max")
    if submitted is None or not isinstance(max_days, int) or isinstance(max_days, bool):
        return []
    overdue = funded is None or (funded - submitted).days > max_days
    if overdue and not bool(cal.get("followup_logged", False)):
        state = "unfunded" if funded is None else f"funded late on {funded.isoformat()}"
        return [Finding(rule, Status.FLAG, ctx.loc(cal, "followup_logged"),
                        f"the draw is {state} past the {max_days}-day window and no "
                        f"follow-up with the lender is recorded")]
    return [Finding(rule, Status.PASS, "-",
                    "the draw ran past its funding window and a follow-up with the "
                    "lender is on record" if overdue else
                    "funded inside the agreed window, so no follow-up was required")]


@check("fund_working_capital_floor")
def fund_working_capital_floor(ctx: Context) -> list[Finding]:
    """The project must carry its working-capital floor.

    Working capital is what lets a project fund the costs that fall outside the
    draw cycle. A project below its floor has to either delay those costs or
    force them into a draw they do not belong in, which is where cutoff breaks
    start.
    """
    rule = "fund_working_capital_floor"
    _sev(rule, Status.FLAG)
    ledger = ctx.one(DOC_FUNDING_LEDGER)
    if ledger is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        balance = require_cents("funding_ledger.working_capital_balance_cents",
                                ledger.get("working_capital_balance_cents"))
        floor = require_cents("funding_ledger.working_capital_floor_cents",
                              ledger.get("working_capital_floor_cents"))
        if balance < floor:
            out.append(Finding(rule, Status.FLAG,
                               ctx.loc(ledger, "working_capital_balance_cents"),
                               f"working capital is {fmt(balance)} against a floor of "
                               f"{fmt(floor)}; the project cannot fund costs that fall "
                               f"outside the draw cycle"))
        else:
            out.append(Finding(rule, Status.PASS, "-",
                               f"working capital {fmt(balance)} is at or above the "
                               f"{fmt(floor)} floor"))
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one draw package.

    Args:
        path: Path to a ``.json`` draw package.

    Returns:
        A :class:`~draw_engine.model.DocumentReport` for the package.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the file is not valid JSON or not a JSON object.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top level must be a JSON object")

    ctx = Context(path=path, data=raw)
    report = DocumentReport(document=ctx.package_id)
    for _rule_id, fn in REGISTRY:
        report.findings.extend(fn(ctx))
    return report


def analyze_folder(folder: Path) -> list[DocumentReport]:
    """Analyze every ``.json`` draw package in ``folder``.

    Files are processed in sorted order so the report is byte-stable across runs
    and platforms.
    """
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of package reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
