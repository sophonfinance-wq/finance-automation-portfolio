"""
JV investor reporting package control engine (READ-ONLY).
=========================================================

Loads each package file (a ``.json`` file produced by
:mod:`investor_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **the monthly financial reporting package a developer issues
to the joint-venture equity partner of a single project entity**: the trial
balance, the balance sheet, the statement of operations, the statement of
members' capital, the development cost schedule, the job cost bridge, the notes,
the cover that asserts a basis of presentation over all of it, and the release
record that says whether it went out.

It re-derives the package from its sources and reports exceptions. It never
mutates an input and it never posts an entry. Where two sources disagree about
what a figure *is* -- a cost the ledger calls one thing and the draw schedule
calls another -- the engine reports the disagreement and stops. Picking a winner
is classification judgement and belongs to a person.

The shape of the problem
------------------------
Monthly, per project, per investor, prepared by hand from five sources, and the
failure mode is a wrong figure sent to an outside equity partner. Five failures
found during a manual build of one such package took three rounds of human review
to surface: a difference dropped instead of disclosed, a contribution column that
agreed to no executed draw, a cost-to-date schedule captioned as period activity,
a cover asserting no exceptions over notes that disclosed one, and a tie-out
check row left inside the released print area.

The registry is organised around the package, front to back:

1. ``tb_`` -- does the trial balance net, cover the ledger, and agree to it by
   account number?
2. ``bs_`` / ``interco_`` -- does the balance sheet balance, and is a credit
   intercompany balance presented as the liability it is?
3. ``capital_`` / ``contributions_`` / ``total_`` / ``net_income_`` -- does the
   members' capital statement agree to the ledger, foot, cross-foot and roll
   forward, and does its result agree to the statement of operations?
4. ``devcost_`` / ``jobcost_`` / ``division_`` -- does development cost tie to
   work in process, does the job cost bridge close, and is every division
   covered?
5. ``draw_`` / ``reciprocal_`` -- do contributions agree to the executed draw
   schedule, and does the parent's investment account agree to the capital it
   represents?
6. ``nil_`` / ``cash_`` / ``footnote_`` / ``caption_`` / ``cover_`` -- is a nil
   statement genuinely nil, is cash supported, does every quoted figure match
   the cell it describes, does every caption fit its schedule, and does the cover
   agree with what the notes disclose?
7. ``checkrows_`` / ``no_preparer_`` / ``prior_`` / ``package_`` / ``release_`` --
   is the released artifact the released artifact, does it continue from last
   period, is it complete, and was it allowed to leave?

Design notes
------------
- **Strictly read-only.** Package files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every tie-out is exact ``==``.
- **Matched by identity, never by position.** Balances join on account number and
  capital joins on member id. ``tb_agrees_ledger`` reports positional agreement
  explicitly when it finds it, because that is the signature of a package built
  by paste rather than by lookup.
- **One package kernel.** Controls and the generator share
  :mod:`investor_engine.package`, so a finding cannot disagree with the data that
  produced it.
- **Absent evidence is not a passing control.** A control whose document is
  missing returns nothing at all rather than a PASS, and
  ``package_complete`` reports the absence.
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
    ACCT_ASSET,
    ACCT_LIABILITY,
    CAPITAL_BEGINNING,
    CAPITAL_CONTRIBUTIONS,
    CAPITAL_DISTRIBUTIONS,
    CAPITAL_ENDING,
    CAPITAL_NET_INCOME,
    CAPITAL_RATIO_ROW,
    CAPITAL_ROWS,
    DOC_BALANCE_SHEET,
    DOC_CAPITAL_STATEMENT,
    DOC_CASH_SUPPORT,
    DOC_DEVCOST_SCHEDULE,
    DOC_DRAW_SCHEDULE,
    DOC_ENTITY_LEDGER,
    DOC_FOOTNOTES,
    DOC_INCOME_STATEMENT,
    DOC_JOB_COST_DETAIL,
    DOC_JOBCOST_REPORT,
    DOC_PACKAGE_COVER,
    DOC_PARENT_LEDGER,
    DOC_PRIOR_PACKAGE,
    DOC_RELEASE_LOG,
    DOC_TRIAL_BALANCE,
    DOC_TYPES,
    DRAW_EXECUTED,
    RELEASE_DECISIONS,
    RELEASE_HELD,
    RELEASE_RELEASED,
    RESULT_ACCOUNT_TYPES,
    ROLE_CAPITAL,
    ROLE_CASH,
    ROLE_INTERCOMPANY,
    ROLE_WIP,
    SCHEDULE_TYPES,
    SECTION_ASSETS,
    SECTION_EQUITY,
    SECTION_LIABILITIES,
    STATEMENT_CONTENT,
    TOTAL_COLUMN,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, fmt_bps, require_cents
from .package import (
    bridge_gap,
    capital_ending,
    caption_matches,
    cross_foot,
    has_activity,
    net_balance,
    presentation_section,
    release_decision_required,
    variance,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~investor_engine.money.AmountInvalidError` as a finding."""
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


def _bool(row: dict[str, Any], key: str) -> bool | None:
    value = row.get(key)
    return value if isinstance(value, bool) else None


# --------------------------------------------------------------------------- #
# Source accessors -- the project entity's own books
# --------------------------------------------------------------------------- #
def _ledger_accounts(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_ENTITY_LEDGER), "accounts")


def _account_no(row: dict[str, Any]) -> str:
    value = row.get("account_no")
    return value if isinstance(value, str) and value else "?"


def _account_label(row: dict[str, Any]) -> str:
    name = _text(row, "name") or _text(row, "account_name") or "unnamed"
    return f"{_account_no(row)} {name}"


def _ledger_map(ctx: Context) -> dict[str, dict[str, Any]]:
    """Ledger accounts keyed by account number, first occurrence winning."""
    out: dict[str, dict[str, Any]] = {}
    for row in _ledger_accounts(ctx):
        no = _account_no(row)
        if no != "?" and no not in out:
            out[no] = row
    return out


def account_net(row: dict[str, Any], *, label: str) -> int:
    """Signed balance of one ledger or trial balance row, validated.

    Raises :class:`~investor_engine.money.AmountInvalidError` when either column
    is not integer cents; the calling control contains that to the one row.
    """
    debit = require_cents(f"{label}.debit_cents", row.get("debit_cents"))
    credit = require_cents(f"{label}.credit_cents", row.get("credit_cents"))
    return net_balance(debit, credit)


def ledger_account_net(ctx: Context, account_no: str) -> int | None:
    """Signed ledger balance of one account, or ``None`` when it is not there."""
    row = _ledger_map(ctx).get(account_no)
    if row is None:
        return None
    return account_net(row, label=f"ledger[{account_no}]")


def ledger_accounts_by_role(ctx: Context, role: str) -> list[dict[str, Any]]:
    """Every ledger account carrying ``role``, in ledger order."""
    return [row for row in _ledger_accounts(ctx) if _text(row, "role") == role]


def wip_balance(ctx: Context) -> int | None:
    """The work-in-process balance the development cost schedule ties to.

    Summed across every account carrying the WIP role, so a chart of accounts
    that splits development cost over more than one account still reconciles.
    Returns ``None`` when the ledger carries no WIP account at all, which is a
    completeness question rather than a tie-out one.
    """
    accounts = ledger_accounts_by_role(ctx, ROLE_WIP)
    if not accounts:
        return None
    return sum(account_net(row, label=f"ledger[{_account_no(row)}]") for row in accounts)


def member_capital_balance(ctx: Context, member_id: str) -> int | None:
    """A member's capital per the ledger, as a positive equity balance.

    Capital sits in the ledger as a credit, so the sign is flipped once here and
    every control compares like with like against the capital statement.
    """
    for row in ledger_accounts_by_role(ctx, ROLE_CAPITAL):
        if _text(row, "member_id") == member_id:
            return -account_net(row, label=f"ledger[{_account_no(row)}]")
    return None


def _job_divisions(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_JOB_COST_DETAIL), "divisions")


def _draws(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DRAW_SCHEDULE), "draws")


def _draw_id(row: dict[str, Any]) -> str:
    value = row.get("draw_id")
    return value if isinstance(value, str) and value else "?"


def executed_draws_for(ctx: Context, member_id: str) -> list[dict[str, Any]]:
    """Executed draws funded by one member inside the reporting period.

    Three filters, each load-bearing. Only ``executed`` draws count: a scheduled
    draw is a plan and a cancelled one is a withdrawn plan, and neither funded a
    cent. Only draws inside the period count: a draw funded after the period end
    is next month's contribution, and one funded before the period start is
    already inside the opening balance. A draw whose date cannot be read sorts
    last and is kept rather than dropped, so an unreadable date shows up as a
    variance instead of silently reducing the total the package is measured
    against.
    """
    period_start = _parse_date(ctx.period_start)
    period_end = _parse_date(ctx.period_end)
    rows: list[dict[str, Any]] = []
    for row in _draws(ctx):
        if _text(row, "member_id") != member_id:
            continue
        if _text(row, "status") != DRAW_EXECUTED:
            continue
        when = _parse_date(row.get("funded_date"))
        if when is not None and period_start is not None and when < period_start:
            continue
        if when is not None and period_end is not None and when > period_end:
            continue
        rows.append(row)
    return sorted(rows, key=lambda r: (_parse_date(r.get("funded_date")) or date.max, _draw_id(r)))


def _prior_package(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_PRIOR_PACKAGE)


def _prior_closing_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(_prior_package(ctx), "closing_capital"):
        member_id = _text(row, "member_id")
        if member_id and member_id not in out:
            out[member_id] = row
    return out


# --------------------------------------------------------------------------- #
# Package accessors -- the statements that get issued
# --------------------------------------------------------------------------- #
def _tb_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_TRIAL_BALANCE), "rows")


def _bs_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_BALANCE_SHEET), "rows")


def _bs_section_rows(ctx: Context, section: str) -> list[dict[str, Any]]:
    return [row for row in _bs_rows(ctx) if _text(row, "section") == section]


def _capital(ctx: Context) -> dict[str, Any] | None:
    return ctx.one(DOC_CAPITAL_STATEMENT)


def _members(ctx: Context) -> list[dict[str, Any]]:
    """The member roster, in presentation order, deduplicated by member id."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in _rows(_capital(ctx), "members"):
        member_id = _text(row, "member_id")
        if member_id and member_id not in seen:
            seen.add(member_id)
            out.append(row)
    return out


def _member_id(row: dict[str, Any]) -> str:
    value = row.get("member_id")
    return value if isinstance(value, str) and value else "?"


def _member_label(row: dict[str, Any]) -> str:
    name = _text(row, "name")
    return f"{_member_id(row)} ({name})" if name else _member_id(row)


def _capital_columns(ctx: Context) -> dict[str, dict[str, Any]]:
    doc = _capital(ctx)
    if doc is None:
        return {}
    columns = doc.get("columns")
    if not isinstance(columns, dict):
        return {}
    return {k: v for k, v in columns.items() if isinstance(k, str) and isinstance(v, dict)}


def _column(ctx: Context, key: str) -> dict[str, Any] | None:
    return _capital_columns(ctx).get(key)


def _contribution_detail(ctx: Context) -> list[dict[str, Any]]:
    return _rows(_capital(ctx), "contribution_detail")


def _devcost_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_DEVCOST_SCHEDULE), "rows")


def _reconciling_items(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_JOBCOST_REPORT), "reconciling_items")


def _notes(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_FOOTNOTES), "notes")


def _disclosed_exceptions(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PACKAGE_COVER), "disclosed_exceptions")


def _check_rows(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_RELEASE_LOG), "check_rows")


def _artifacts(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_RELEASE_LOG), "artifacts")


def _captioned_docs(ctx: Context) -> list[dict[str, Any]]:
    """Every document that declares what it measures, in file order."""
    return [doc for doc in ctx.documents if isinstance(doc.get("schedule_type"), str)]


# --------------------------------------------------------------------------- #
# Shared re-derivation -- the generator computes with these too
# --------------------------------------------------------------------------- #
def recompute_trial_balance(ctx: Context) -> list[dict[str, Any]]:
    """The package trial balance the ledger produces.

    One row per ledger account with activity, ordered by account **name** rather
    than account number. That ordering is deliberate in the shipped corpus: the
    trial balance a preparer exports is sorted the way the report is read, so a
    package built by pasting a column of balances alongside it lines nothing up,
    and ``tb_agrees_ledger`` has to join on the account number to be right.
    """
    rows: list[dict[str, Any]] = []
    for account in _ledger_accounts(ctx):
        debit = require_cents(
            f"ledger[{_account_no(account)}].debit_cents", account.get("debit_cents")
        )
        credit = require_cents(
            f"ledger[{_account_no(account)}].credit_cents", account.get("credit_cents")
        )
        if not has_activity(debit, credit):
            continue
        rows.append(
            {
                "account_no": _account_no(account),
                "account_name": _text(account, "name") or "unnamed",
                "debit_cents": debit,
                "credit_cents": credit,
            }
        )
    return sorted(rows, key=lambda r: (r["account_name"], r["account_no"]))


def recompute_capital_columns(ctx: Context) -> dict[str, dict[str, int]]:
    """The capital statement the sources produce.

    Beginning comes from the prior package's closing capital, contributions from
    the executed draw schedule, the result and the distributions from what the
    file states for them, and ending from the shared rollforward kernel. The
    Total column is cross-footed from the member columns rather than carried
    beside them, which is the whole point of ``total_cross_foots``.
    """
    prior = _prior_closing_map(ctx)
    columns: dict[str, dict[str, int]] = {}
    for member in _members(ctx):
        member_id = _member_id(member)
        stated = _column(ctx, member_id) or {}
        beginning = 0
        prior_row = prior.get(member_id)
        if prior_row is not None:
            beginning = require_cents(
                f"prior_package[{member_id}].ending_cents", prior_row.get("ending_cents")
            )
        contributions = sum(
            require_cents(f"draw[{_draw_id(d)}].amount_cents", d.get("amount_cents"))
            for d in executed_draws_for(ctx, member_id)
        )
        net_income = require_cents(
            f"capital[{member_id}].{CAPITAL_NET_INCOME}", stated.get(CAPITAL_NET_INCOME)
        )
        distributions = require_cents(
            f"capital[{member_id}].{CAPITAL_DISTRIBUTIONS}", stated.get(CAPITAL_DISTRIBUTIONS)
        )
        ratio = require_cents(
            f"capital[{member_id}].{CAPITAL_RATIO_ROW}",
            stated.get(CAPITAL_RATIO_ROW),
            unit="integer basis points",
        )
        columns[member_id] = {
            CAPITAL_BEGINNING: beginning,
            CAPITAL_CONTRIBUTIONS: contributions,
            CAPITAL_NET_INCOME: net_income,
            CAPITAL_DISTRIBUTIONS: distributions,
            CAPITAL_ENDING: capital_ending(beginning, contributions, net_income, distributions),
            CAPITAL_RATIO_ROW: ratio,
        }
    columns[TOTAL_COLUMN] = {
        row_key: cross_foot(col[row_key] for col in columns.values())
        for row_key in (*CAPITAL_ROWS, CAPITAL_RATIO_ROW)
    }
    return columns


def recompute_contribution_detail(ctx: Context) -> list[dict[str, Any]]:
    """The contribution detail the executed draw schedule produces."""
    detail: list[dict[str, Any]] = []
    for member in _members(ctx):
        member_id = _member_id(member)
        for draw in executed_draws_for(ctx, member_id):
            detail.append(
                {
                    "member_id": member_id,
                    "draw_id": _draw_id(draw),
                    "received_date": _text(draw, "funded_date") or "",
                    "amount_cents": require_cents(
                        f"draw[{_draw_id(draw)}].amount_cents", draw.get("amount_cents")
                    ),
                }
            )
    return sorted(detail, key=lambda r: (r["received_date"], r["draw_id"], r["member_id"]))


def recompute_balance_sheet(ctx: Context) -> dict[str, Any]:
    """The balance sheet the ledger and the capital statement produce.

    Section membership comes from the shared
    :func:`~investor_engine.package.presentation_section` rule, so an
    intercompany account in credit lands in liabilities here for the same reason
    ``interco_classified`` insists on finding it there. Members' equity is taken
    from the capital statement rather than re-derived, because the capital
    statement is the statement that owns it.
    """
    rows: list[dict[str, Any]] = []
    for account in _ledger_accounts(ctx):
        account_type = _text(account, "type") or ""
        if account_type not in (ACCT_ASSET, ACCT_LIABILITY):
            continue
        net = account_net(account, label=f"ledger[{_account_no(account)}]")
        if net == 0:
            continue
        section = presentation_section(net)
        rows.append(
            {
                "section": section,
                "account_no": _account_no(account),
                "member_id": "",
                "label": _text(account, "name") or "unnamed",
                "amount_cents": net if section == SECTION_ASSETS else -net,
            }
        )
    rows.sort(key=lambda r: (r["section"], r["account_no"]))

    columns = _capital_columns(ctx)
    equity_rows: list[dict[str, Any]] = []
    for member in _members(ctx):
        member_id = _member_id(member)
        column = columns.get(member_id, {})
        equity_rows.append(
            {
                "section": SECTION_EQUITY,
                "account_no": "",
                "member_id": member_id,
                "label": f"Members' capital - {_text(member, 'name') or member_id}",
                "amount_cents": require_cents(
                    f"capital[{member_id}].{CAPITAL_ENDING}", column.get(CAPITAL_ENDING)
                ),
            }
        )
    rows.extend(equity_rows)

    def _section_total(section: str) -> int:
        return sum(r["amount_cents"] for r in rows if r["section"] == section)

    return {
        "rows": rows,
        "total_assets_cents": _section_total(SECTION_ASSETS),
        "total_liabilities_cents": _section_total(SECTION_LIABILITIES),
        "total_equity_cents": _section_total(SECTION_EQUITY),
    }


def recompute_cash_support(ctx: Context) -> list[dict[str, Any]]:
    """The bank reconciliation set the ledger's cash accounts call for."""
    out: list[dict[str, Any]] = []
    for account in ledger_accounts_by_role(ctx, ROLE_CASH):
        out.append(
            {
                "account_no": _account_no(account),
                "statement_date": ctx.period_end,
                "reconciled_balance_cents": account_net(
                    account, label=f"ledger[{_account_no(account)}]"
                ),
                "support_attached": True,
            }
        )
    return sorted(out, key=lambda r: r["account_no"])


def resolve_cell(ctx: Context, ref: str) -> int | None:
    """Resolve a footnote's cell reference to the figure printed in that cell.

    A note quotes a figure and names the cell it came from. The reference grammar
    is small and explicit on purpose -- there is no expression language here,
    because a note that has to be evaluated is a note nobody can check by eye:

    * ``balance_sheet/row/<account_no>``
    * ``balance_sheet/<total_assets_cents|total_liabilities_cents|total_equity_cents>``
    * ``capital_statement/column/<member_id|total>/<row_key>``
    * ``devcost_schedule/total_cents``
    * ``jobcost_report/total_cents``
    * ``income_statement/net_income_cents``
    * ``trial_balance/row/<account_no>/<debit_cents|credit_cents>``

    Returns ``None`` when the reference names a cell the package does not have,
    which ``footnote_figures`` reports as its own failure: a note pointing at a
    cell that is not there quotes nothing.
    """
    parts = ref.split("/")
    if not parts:
        return None
    head, rest = parts[0], parts[1:]

    if head == DOC_BALANCE_SHEET:
        sheet = ctx.one(DOC_BALANCE_SHEET)
        if sheet is None:
            return None
        if len(rest) == 2 and rest[0] == "row":
            for row in _bs_rows(ctx):
                if _text(row, "account_no") == rest[1]:
                    return _int(row, "amount_cents")
            return None
        if len(rest) == 1 and rest[0] in (
            "total_assets_cents",
            "total_liabilities_cents",
            "total_equity_cents",
        ):
            return _int(sheet, rest[0])
        return None

    if head == DOC_CAPITAL_STATEMENT:
        if len(rest) == 3 and rest[0] == "column":
            column = _column(ctx, rest[1])
            if column is None:
                return None
            return _int(column, rest[2])
        return None

    if head == DOC_DEVCOST_SCHEDULE and rest == ["total_cents"]:
        doc = ctx.one(DOC_DEVCOST_SCHEDULE)
        return None if doc is None else _int(doc, "total_cents")

    if head == DOC_JOBCOST_REPORT and rest == ["total_cents"]:
        doc = ctx.one(DOC_JOBCOST_REPORT)
        return None if doc is None else _int(doc, "total_cents")

    if head == DOC_INCOME_STATEMENT and rest == ["net_income_cents"]:
        doc = ctx.one(DOC_INCOME_STATEMENT)
        return None if doc is None else _int(doc, "net_income_cents")

    if head == DOC_TRIAL_BALANCE and len(rest) == 3 and rest[0] == "row":
        if rest[2] not in ("debit_cents", "credit_cents"):
            return None
        for row in _tb_rows(ctx):
            if _text(row, "account_no") == rest[1]:
                return _int(row, rest[2])
        return None

    return None


def blocking_findings(ctx: Context, gate_rule: str) -> list[Finding]:
    """Every non-PASS finding the registry produced before the release gate.

    The gate is the only control that reads the run's own output, and it reads it
    from here so the reason a package is held is always a named rule rather than
    a summary judgement.
    """
    return [
        f for f in ctx.prior_findings if f.status is not Status.PASS and f.rule != gate_rule
    ]


def _statement_non_empty(doc: dict[str, Any], keys: tuple[str, ...]) -> bool:
    """Whether a statement carries content, or declares itself nil.

    A statement that declares ``presented_nil`` counts as issued: a nil
    statement of operations is a real presentation for a project entity that
    capitalises everything, and whether the nil is genuine is
    ``nil_is_genuine``'s question, not this one's.
    """
    if doc.get("presented_nil") is True:
        return True
    for key in keys:
        value = doc.get(key)
        if isinstance(value, list | dict) and value:
            return True
        if isinstance(value, int) and not isinstance(value, bool):
            return True
    return False


# --------------------------------------------------------------------------- #
# 1-3  tb_ -- the package trial balance against the ledger behind it
# --------------------------------------------------------------------------- #
@check("tb_nets_zero")
def check_tb_nets_zero(ctx: Context) -> list[Finding]:
    """The trial balance nets to zero: debits equal credits.

    Everything downstream inherits this. A trial balance that is off by any
    amount carries a difference that has to land somewhere in the package, and
    wherever it lands is a figure the ledger does not support. There is no
    tolerance band, because a package out by a penny is a package whose
    difference nobody has looked for.
    """
    rule = "tb_nets_zero"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    if tb is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        debits = 0
        credits = 0
        for row in _tb_rows(ctx):
            label = f"trial_balance[{_account_no(row)}]"
            debits += require_cents(f"{label}.debit_cents", row.get("debit_cents"))
            credits += require_cents(f"{label}.credit_cents", row.get("credit_cents"))
        if debits != credits:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(tb, "rows"),
                    f"the trial balance carries {fmt(debits)} of debits against "
                    f"{fmt(credits)} of credits, out by {fmt(debits - credits)}; every "
                    f"statement built on it inherits a difference that has to land "
                    f"somewhere",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the {len(_tb_rows(ctx))} trial balance rows net to zero at "
                    f"{fmt(debits)} on each side",
                )
            )
    return out


@check("tb_completeness")
def check_tb_completeness(ctx: Context) -> list[Finding]:
    """Every ledger account with activity appears in the package trial balance.

    Activity means either column moved, never the net. A clearing account that
    took in an amount and released the same amount has a net balance of zero and
    is exactly the account a package drops -- and dropping it hides the whole of
    what it did, along with any part of it that should not have cleared.
    """
    rule = "tb_completeness"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if tb is None or ledger is None:
        return []
    present = {_account_no(row) for row in _tb_rows(ctx)}
    out: list[Finding] = []
    checked = 0
    for account in _ledger_accounts(ctx):
        with amount_guard(rule, out):
            net = account_net(account, label=f"ledger[{_account_no(account)}]")
            debit = require_cents(
                f"ledger[{_account_no(account)}].debit_cents", account.get("debit_cents")
            )
            credit = require_cents(
                f"ledger[{_account_no(account)}].credit_cents", account.get("credit_cents")
            )
            if not has_activity(debit, credit):
                continue
            checked += 1
            if _account_no(account) not in present:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"rows/{_account_no(account)}"),
                        f"ledger account {_account_label(account)} moved "
                        f"{fmt(debit)} of debits and {fmt(credit)} of credits in the "
                        f"period and does not appear in the package trial balance; its "
                        f"net balance of {fmt(net)} is why nobody missed it",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} ledger account(s) with activity appear in the trial balance",
            )
        )
    return out


@check("tb_agrees_ledger")
def check_tb_agrees_ledger(ctx: Context) -> list[Finding]:
    """Each package balance equals its ledger account balance, matched by number.

    The join is on the account number and only on the account number. A trial
    balance is exported in reading order and the ledger extract comes out in
    account order, so a package assembled by pasting one column beside the other
    agrees on the rows where the two orders happen to coincide and is wrong
    everywhere else -- and it foots, and it nets, and it balances.

    When a stated balance disagrees with its own account but does match the
    ledger account in the *same row position*, the finding says so. That is the
    fingerprint of a positional paste, and naming it saves a reviewer the hour it
    otherwise takes to work out why two figures that look unrelated are both
    wrong by the same pair of amounts.
    """
    rule = "tb_agrees_ledger"
    _sev(rule, Status.FAIL)
    tb = ctx.one(DOC_TRIAL_BALANCE)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if tb is None or ledger is None:
        return []
    accounts = _ledger_accounts(ctx)
    by_number = _ledger_map(ctx)
    out: list[Finding] = []
    checked = 0
    for index, row in enumerate(_tb_rows(ctx)):
        no = _account_no(row)
        with amount_guard(rule, out):
            stated = account_net(row, label=f"trial_balance[{no}]")
            account = by_number.get(no)
            if account is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(tb, f"rows/{no}"),
                        f"the trial balance carries account {no} at {fmt(stated)}; the "
                        f"ledger extract has no such account, so the balance agrees to "
                        f"nothing",
                    )
                )
                continue
            checked += 1
            derived = account_net(account, label=f"ledger[{no}]")
            if stated == derived:
                continue
            hint = ""
            if index < len(accounts):
                positional = accounts[index]
                if _account_no(positional) != no and stated == account_net(
                    positional, label=f"ledger[{_account_no(positional)}]"
                ):
                    hint = (
                        f" -- the figure does agree to ledger account "
                        f"{_account_label(positional)}, which sits in the same row "
                        f"position, so the column was matched by position rather than "
                        f"by account number"
                    )
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(tb, f"rows/{no}"),
                    f"account {_account_label(account)} is stated at {fmt(stated)} in "
                    f"the package trial balance; the ledger carries {fmt(derived)} "
                    f"(off by {fmt(variance(stated, derived))}){hint}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} package balance(s) agree to the ledger account of the "
                f"same account number",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 4-5  bs_ / interco_ -- the statement of financial position
# --------------------------------------------------------------------------- #
@check("bs_balances")
def check_bs_balances(ctx: Context) -> list[Finding]:
    """Total assets equals total liabilities plus members' equity.

    Both halves of that are checked, because a balance sheet fails in two
    different places. Each stated section total is re-added from the rows printed
    under it -- a total maintained beside its rows drifts the first time a row is
    inserted -- and then the accounting identity itself is struck across the
    three stated totals.
    """
    rule = "bs_balances"
    _sev(rule, Status.FAIL)
    sheet = ctx.one(DOC_BALANCE_SHEET)
    if sheet is None:
        return []
    totals = {
        SECTION_ASSETS: "total_assets_cents",
        SECTION_LIABILITIES: "total_liabilities_cents",
        SECTION_EQUITY: "total_equity_cents",
    }
    out: list[Finding] = []
    stated_totals: dict[str, int] = {}
    with amount_guard(rule, out):
        for section, key in totals.items():
            rows = _bs_section_rows(ctx, section)
            derived = sum(
                require_cents(
                    f"balance_sheet[{_text(r, 'account_no') or _text(r, 'member_id') or '?'}]"
                    f".amount_cents",
                    r.get("amount_cents"),
                )
                for r in rows
            )
            stated = require_cents(f"balance_sheet.{key}", sheet.get(key))
            stated_totals[section] = stated
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(sheet, key),
                        f"the {section} section states {fmt(stated)}; the "
                        f"{len(rows)} row(s) printed under it add to {fmt(derived)} "
                        f"(off by {fmt(variance(stated, derived))})",
                    )
                )
        if len(stated_totals) == len(totals):
            assets = stated_totals[SECTION_ASSETS]
            funding = stated_totals[SECTION_LIABILITIES] + stated_totals[SECTION_EQUITY]
            if assets != funding:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(sheet, "total_assets_cents"),
                        f"total assets of {fmt(assets)} does not equal total liabilities "
                        f"of {fmt(stated_totals[SECTION_LIABILITIES])} plus members' "
                        f"equity of {fmt(stated_totals[SECTION_EQUITY])} "
                        f"({fmt(funding)}); the statement is out by "
                        f"{fmt(variance(assets, funding))}",
                    )
                )
        if not out:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"all {len(totals)} section totals foot their rows and total assets of "
                    f"{fmt(stated_totals[SECTION_ASSETS])} equals liabilities plus "
                    f"members' equity",
                )
            )
    return out


@check("interco_classified")
def check_interco_classified(ctx: Context) -> list[Finding]:
    """A credit-balance intercompany account is reclassified, not netted.

    An intercompany account in credit is money the project entity owes, whatever
    the chart of accounts numbered it. Netting it against the asset it was
    numbered beside understates assets and liabilities by the same amount, which
    is precisely why the balance sheet still balances and the reclassification
    gets missed -- and the partner reads a project entity with less on both sides
    of it than it has.
    """
    rule = "interco_classified"
    _sev(rule, Status.FAIL)
    sheet = ctx.one(DOC_BALANCE_SHEET)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if sheet is None or ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for account in ledger_accounts_by_role(ctx, ROLE_INTERCOMPANY):
        no = _account_no(account)
        with amount_guard(rule, out):
            net = account_net(account, label=f"ledger[{no}]")
            required = presentation_section(net)
            checked += 1
            sections = [
                _text(row, "section") or "?"
                for row in _bs_rows(ctx)
                if _text(row, "account_no") == no
            ]
            if not sections:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(sheet, f"rows/{no}"),
                        f"intercompany account {_account_label(account)} carries a balance "
                        f"of {fmt(net)} and appears nowhere on the balance sheet; a "
                        f"balance netted out of the statement is a balance the partner "
                        f"cannot see",
                    )
                )
                continue
            for section in sections:
                if section != required:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(sheet, f"rows/{no}"),
                            f"intercompany account {_account_label(account)} is in credit "
                            f"at {fmt(net)} and is presented in {section}; a credit "
                            f"intercompany balance is a liability and belongs in "
                            f"{required}, not netted against assets",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} intercompany account(s) are presented in the section "
                f"their balance requires",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 6-10  the statement of members' capital
# --------------------------------------------------------------------------- #
@check("capital_agrees_ledger")
def check_capital_agrees_ledger(ctx: Context) -> list[Finding]:
    """Members' capital ending balance per member equals its ledger account.

    Per member, matched on member id. This is the control that catches a
    statement figure that was arrived at rather than agreed: a distribution
    written into the statement that never posted, a contribution booked to the
    wrong member's account. The statement can roll forward perfectly and
    cross-foot perfectly and still not be what the books say each member has.
    """
    rule = "capital_agrees_ledger"
    _sev(rule, Status.FAIL)
    statement = _capital(ctx)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if statement is None or ledger is None:
        return []
    out: list[Finding] = []
    checked = 0
    for member in _members(ctx):
        member_id = _member_id(member)
        column = _column(ctx, member_id)
        if column is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(statement, f"columns/{member_id}"),
                    f"member {_member_label(member)} is on the roster and has no column "
                    f"in the capital statement",
                )
            )
            continue
        with amount_guard(rule, out):
            stated = require_cents(
                f"capital[{member_id}].{CAPITAL_ENDING}", column.get(CAPITAL_ENDING)
            )
            derived = member_capital_balance(ctx, member_id)
            if derived is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{member_id}/{CAPITAL_ENDING}"),
                        f"member {_member_label(member)} ends at {fmt(stated)} and the "
                        f"ledger carries no capital account for it; the balance agrees to "
                        f"nothing",
                    )
                )
                continue
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{member_id}/{CAPITAL_ENDING}"),
                        f"member {_member_label(member)} ends at {fmt(stated)} on the "
                        f"capital statement; its ledger capital account carries "
                        f"{fmt(derived)} (off by {fmt(variance(stated, derived))})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} member ending balance(s) agree to the ledger capital "
                f"account of the same member",
            )
        )
    return out


@check("contributions_foot")
def check_contributions_foot(ctx: Context) -> list[Finding]:
    """Member contributions foot to the contribution detail behind them.

    The column figure is a total; the detail is the evidence for it. They are
    maintained side by side, so they part company the first time a capital call
    is added to one and not the other -- and the member column then reports
    money the schedule underneath it cannot account for. Only the member columns
    are footed here: the Total column is ``total_cross_foots``'s to own, so one
    break never fires two controls.
    """
    rule = "contributions_foot"
    _sev(rule, Status.FAIL)
    statement = _capital(ctx)
    if statement is None:
        return []
    out: list[Finding] = []
    checked = 0
    detail = _contribution_detail(ctx)
    for member in _members(ctx):
        member_id = _member_id(member)
        column = _column(ctx, member_id)
        if column is None:
            continue  # capital_agrees_ledger owns a member with no column
        lines = [r for r in detail if _text(r, "member_id") == member_id]
        with amount_guard(rule, out):
            stated = require_cents(
                f"capital[{member_id}].{CAPITAL_CONTRIBUTIONS}",
                column.get(CAPITAL_CONTRIBUTIONS),
            )
            derived = sum(
                require_cents(
                    f"contribution_detail[{_text(r, 'draw_id') or '?'}].amount_cents",
                    r.get("amount_cents"),
                )
                for r in lines
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{member_id}/{CAPITAL_CONTRIBUTIONS}"),
                        f"member {_member_label(member)} is shown contributing "
                        f"{fmt(stated)} in the period; the {len(lines)} contribution "
                        f"line(s) listed for it foot to {fmt(derived)} "
                        f"(off by {fmt(variance(stated, derived))})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} member contribution column(s) foot to the "
                f"{len(detail)} contribution line(s) behind them",
            )
        )
    return out


@check("total_cross_foots")
def check_total_cross_foots(ctx: Context) -> list[Finding]:
    """The Total column cross-foots to the member columns on every row.

    Every row, including the sharing-ratio row, which is not money and still has
    to add to a whole. The defect this exists for is a Total cell that links
    somewhere else instead of summing the row it sits on -- to the ledger, to a
    funding notice, to last period's total. Such a cell is right often enough to
    survive review and wrong exactly when a member column moves, which is the
    month it matters.
    """
    rule = "total_cross_foots"
    _sev(rule, Status.FAIL)
    statement = _capital(ctx)
    if statement is None:
        return []
    total_column = _column(ctx, TOTAL_COLUMN)
    if total_column is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(statement, f"columns/{TOTAL_COLUMN}"),
                "the capital statement carries no Total column; the figures the partner "
                "reads first are the ones that are not there",
            )
        ]
    members = _members(ctx)
    out: list[Finding] = []
    checked = 0
    for row_key in (*CAPITAL_ROWS, CAPITAL_RATIO_ROW):
        is_ratio = row_key == CAPITAL_RATIO_ROW
        unit = "integer basis points" if is_ratio else "integer cents"
        with amount_guard(rule, out):
            stated = require_cents(
                f"capital[{TOTAL_COLUMN}].{row_key}", total_column.get(row_key), unit=unit
            )
            parts: list[int] = []
            for member in members:
                column = _column(ctx, _member_id(member))
                if column is None:
                    continue
                parts.append(
                    require_cents(
                        f"capital[{_member_id(member)}].{row_key}",
                        column.get(row_key),
                        unit=unit,
                    )
                )
            derived = cross_foot(parts)
            checked += 1
            if stated != derived:
                shown = fmt_bps if is_ratio else fmt
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{TOTAL_COLUMN}/{row_key}"),
                        f"the Total column states {shown(stated)} on the {row_key} row; "
                        f"the {len(parts)} member column(s) on that row add to "
                        f"{shown(derived)} (off by {shown(stated - derived)}); a Total "
                        f"cell that does not sum its own row is linked to something else",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the Total column cross-foots to the {len(members)} member column(s) on "
                f"all {checked} rows",
            )
        )
    return out


@check("capital_rollforward")
def check_capital_rollforward(ctx: Context) -> list[Finding]:
    """Ending equals beginning plus contributions plus result less distributions.

    Struck per member through the shared kernel, so the identity the engine tests
    is the identity that produced the data. The Total row is deliberately not
    tested here: if every member rolls forward and the Total column cross-foots
    every row, the Total rolls forward too, and testing it twice would make one
    break fire two controls.
    """
    rule = "capital_rollforward"
    _sev(rule, Status.FAIL)
    statement = _capital(ctx)
    if statement is None:
        return []
    out: list[Finding] = []
    checked = 0
    for member in _members(ctx):
        member_id = _member_id(member)
        column = _column(ctx, member_id)
        if column is None:
            continue  # capital_agrees_ledger owns a member with no column
        with amount_guard(rule, out):
            values = {
                key: require_cents(f"capital[{member_id}].{key}", column.get(key))
                for key in CAPITAL_ROWS
            }
            derived = capital_ending(
                values[CAPITAL_BEGINNING],
                values[CAPITAL_CONTRIBUTIONS],
                values[CAPITAL_NET_INCOME],
                values[CAPITAL_DISTRIBUTIONS],
            )
            checked += 1
            if values[CAPITAL_ENDING] != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{member_id}/{CAPITAL_ENDING}"),
                        f"member {_member_label(member)} ends at "
                        f"{fmt(values[CAPITAL_ENDING])}; beginning "
                        f"{fmt(values[CAPITAL_BEGINNING])} plus contributions "
                        f"{fmt(values[CAPITAL_CONTRIBUTIONS])} plus result "
                        f"{fmt(values[CAPITAL_NET_INCOME])} less distributions "
                        f"{fmt(values[CAPITAL_DISTRIBUTIONS])} is {fmt(derived)} "
                        f"(off by {fmt(variance(values[CAPITAL_ENDING], derived))})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} member column(s) roll forward exactly",
            )
        )
    return out


@check("net_income_agrees")
def check_net_income_agrees(ctx: Context) -> list[Finding]:
    """Net income on the capital statement equals the income statement's result.

    The same figure is printed twice, in two statements, and allocated between
    members in one of them. The two are prepared at different moments, so an
    amount that arrives late reaches one and not the other, and the package tells
    the partner two different things about what the project earned.
    """
    rule = "net_income_agrees"
    _sev(rule, Status.FAIL)
    statement = _capital(ctx)
    income = ctx.one(DOC_INCOME_STATEMENT)
    if statement is None or income is None:
        return []
    total_column = _column(ctx, TOTAL_COLUMN)
    if total_column is None:
        return []  # total_cross_foots owns a missing Total column
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents(
            f"capital[{TOTAL_COLUMN}].{CAPITAL_NET_INCOME}", total_column.get(CAPITAL_NET_INCOME)
        )
        derived = require_cents(
            "income_statement.net_income_cents", income.get("net_income_cents")
        )
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(statement, f"columns/{TOTAL_COLUMN}/{CAPITAL_NET_INCOME}"),
                    f"the capital statement allocates {fmt(stated)} of result to the "
                    f"members; the statement of operations reports {fmt(derived)} "
                    f"(off by {fmt(variance(stated, derived))})",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the {fmt(stated)} of result allocated on the capital statement "
                    f"agrees to the statement of operations",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# 11-13  development cost, the job cost bridge and division coverage
# --------------------------------------------------------------------------- #
@check("devcost_agrees_wip")
def check_devcost_agrees_wip(ctx: Context) -> list[Finding]:
    """The development cost schedule total equals work in process in the ledger.

    The schedule is the only place the partner sees what the project has spent,
    and it is assembled outside the ledger from a cost report that is not the
    ledger. Both directions are checked: the stated total against the rows
    printed under it, and the rows against the work-in-process account they are
    meant to analyse.
    """
    rule = "devcost_agrees_wip"
    _sev(rule, Status.FAIL)
    schedule = ctx.one(DOC_DEVCOST_SCHEDULE)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if schedule is None or ledger is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        rows = _devcost_rows(ctx)
        derived = sum(
            require_cents(
                f"devcost[{_text(r, 'division_code') or '?'}].cost_to_date_cents",
                r.get("cost_to_date_cents"),
            )
            for r in rows
        )
        stated = require_cents("devcost_schedule.total_cents", schedule.get("total_cents"))
        if stated != derived:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, "total_cents"),
                    f"the development cost schedule states {fmt(stated)}; the "
                    f"{len(rows)} row(s) printed under it add to {fmt(derived)} "
                    f"(off by {fmt(variance(stated, derived))})",
                )
            )
        wip = wip_balance(ctx)
        if wip is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, "total_cents"),
                    f"the development cost schedule states {fmt(stated)} and the ledger "
                    f"carries no work-in-process account; the schedule reconciles to "
                    f"nothing",
                )
            )
        elif derived != wip:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, "rows"),
                    f"the development cost schedule analyses {fmt(derived)} of cost; "
                    f"work in process in the ledger carries {fmt(wip)} "
                    f"(off by {fmt(variance(derived, wip))})",
                )
            )
        if not out:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the {len(rows)} development cost row(s) foot to {fmt(stated)} and "
                    f"agree to work in process",
                )
            )
    return out


@check("jobcost_bridge")
def check_jobcost_bridge(ctx: Context) -> list[Finding]:
    """The job cost report reconciles to the ledger, and every difference is disclosed.

    A job cost report is maintained in the cost system and the ledger is
    maintained in the ledger, so they differ -- routinely, and for good reasons:
    interest capitalised in one and not the other, an accrual posted after the
    cost cut-off. The control is not that they agree. The control is that the
    difference is **itemized and disclosed**, because the alternative is what
    actually happens: the gap is absorbed into a rounding line and the partner is
    told a figure nobody can rebuild.

    Both legs are struck. The report has to foot to the job cost detail behind
    it, and the report plus everything itemized against it has to reach the
    ledger exactly -- there is no closing tolerance, because a bridge that nearly
    closes has an unexplained figure in it.
    """
    rule = "jobcost_bridge"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_JOBCOST_REPORT)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if report is None or ledger is None:
        return []
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated = require_cents("jobcost_report.total_cents", report.get("total_cents"))
        divisions = _job_divisions(ctx)
        detail_total = sum(
            require_cents(
                f"job_cost_detail[{_text(d, 'division_code') or '?'}].cost_to_date_cents",
                d.get("cost_to_date_cents"),
            )
            for d in divisions
        )
        if divisions and stated != detail_total:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "total_cents"),
                    f"the job cost report states {fmt(stated)}; the {len(divisions)} "
                    f"division(s) of job cost detail behind it add to "
                    f"{fmt(detail_total)} (off by {fmt(variance(stated, detail_total))})",
                )
            )
        items = _reconciling_items(ctx)
        undisclosed = [r for r in items if _bool(r, "disclosed") is not True]
        for item in undisclosed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, f"reconciling_items/{_text(item, 'item_id') or '?'}"),
                    f"reconciling item {_text(item, 'item_id') or '?'} "
                    f"({_text(item, 'label') or 'unlabelled'}) is carried in the bridge "
                    f"and not disclosed; a difference the partner is not told about is a "
                    f"difference the partner cannot check",
                )
            )
        reconciled = sum(
            require_cents(
                f"reconciling_item[{_text(r, 'item_id') or '?'}].amount_cents",
                r.get("amount_cents"),
            )
            for r in items
        )
        wip = wip_balance(ctx)
        if wip is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "total_cents"),
                    "the ledger carries no work-in-process account, so the job cost "
                    "bridge has nothing to reconcile to",
                )
            )
        else:
            gap = bridge_gap(wip, stated, reconciled)
            if gap != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(report, "reconciling_items"),
                        f"the job cost report of {fmt(stated)} plus {len(items)} "
                        f"reconciling item(s) totalling {fmt(reconciled)} reaches "
                        f"{fmt(stated + reconciled)} against work in process of "
                        f"{fmt(wip)}; {fmt(gap)} of the difference is neither itemized "
                        f"nor disclosed",
                    )
                )
        if not out:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the job cost report of {fmt(stated)} bridges to work in process "
                    f"through {len(items)} disclosed reconciling item(s)",
                )
            )
    return out


@check("division_coverage")
def check_division_coverage(ctx: Context) -> list[Finding]:
    """Every job cost division appears in the schedule or in a disclosed item.

    A division that is in the cost system and in neither the schedule nor the
    disclosures has left the package without being accounted for. The usual cause
    is benign and the effect is not: a division is renumbered in the cost system
    and the schedule keeps the old code, so the schedule still foots to the same
    total while a whole trade has quietly stopped being reported.
    """
    rule = "division_coverage"
    _sev(rule, Status.FAIL)
    detail = ctx.one(DOC_JOB_COST_DETAIL)
    schedule = ctx.one(DOC_DEVCOST_SCHEDULE)
    if detail is None or schedule is None:
        return []
    covered = {_text(r, "division_code") for r in _devcost_rows(ctx)}
    for item in _reconciling_items(ctx):
        if _bool(item, "disclosed") is not True:
            continue
        codes = item.get("covers_divisions")
        if isinstance(codes, list):
            covered.update(c for c in codes if isinstance(c, str))
    out: list[Finding] = []
    checked = 0
    for division in _job_divisions(ctx):
        code = _text(division, "division_code")
        if code is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(detail, "divisions"),
                    "a job cost division carries no division code, so whether the "
                    "schedule covers it cannot be decided",
                )
            )
            continue
        checked += 1
        if code not in covered:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(schedule, f"rows/{code}"),
                    f"job cost division {code} ({_text(division, 'label') or 'unlabelled'}) "
                    f"carries "
                    f"{fmt(_int(division, 'cost_to_date_cents') or 0)} of cost and appears "
                    f"in neither the development cost schedule nor a disclosed "
                    f"reconciling item",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} job cost division(s) are covered by the schedule or a "
                f"disclosed reconciling item",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 14-15  the executed draw schedule and the reciprocal investment account
# --------------------------------------------------------------------------- #
@check("draw_schedule_agrees")
def check_draw_schedule_agrees(ctx: Context) -> list[Finding]:
    """Contributions agree per member to the executed equity draw schedule.

    The draw schedule is the one document outside the package that says what each
    member actually funded, and it is the document the partner also holds. When
    the two disagree the engine quantifies the variance per member and stops
    there: which figure is right is a question about an executed transfer, and
    answering it is not arithmetic.
    """
    rule = "draw_schedule_agrees"
    _sev(rule, Status.FAIL)
    statement = _capital(ctx)
    schedule = ctx.one(DOC_DRAW_SCHEDULE)
    if statement is None or schedule is None:
        return []
    out: list[Finding] = []
    checked = 0
    for member in _members(ctx):
        member_id = _member_id(member)
        column = _column(ctx, member_id)
        if column is None:
            continue  # capital_agrees_ledger owns a member with no column
        draws = executed_draws_for(ctx, member_id)
        with amount_guard(rule, out):
            stated = require_cents(
                f"capital[{member_id}].{CAPITAL_CONTRIBUTIONS}",
                column.get(CAPITAL_CONTRIBUTIONS),
            )
            derived = sum(
                require_cents(f"draw[{_draw_id(d)}].amount_cents", d.get("amount_cents"))
                for d in draws
            )
            checked += 1
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{member_id}/{CAPITAL_CONTRIBUTIONS}"),
                        f"member {_member_label(member)} is shown contributing "
                        f"{fmt(stated)}; the {len(draws)} draw(s) executed between "
                        f"{ctx.period_start} and {ctx.period_end} fund {fmt(derived)}, a "
                        f"variance of {fmt(variance(stated, derived))} that the package "
                        f"does not quantify",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} member contribution column(s) agree to the executed "
                f"equity draw schedule",
            )
        )
    return out


@check("reciprocal_investment")
def check_reciprocal_investment(ctx: Context) -> list[Finding]:
    """The parent's investment account equals the project entity's capital account.

    Two ledgers, one relationship, and the reciprocal pair is maintained by hand
    on both sides. When they drift the project entity's package is right and the
    parent's consolidation is wrong, or the other way around, and the difference
    is found at year end by whoever is unlucky.
    """
    rule = "reciprocal_investment"
    _sev(rule, Status.FAIL)
    parent = ctx.one(DOC_PARENT_LEDGER)
    statement = _capital(ctx)
    if parent is None or statement is None:
        return []
    member_id = _text(parent, "parent_member_id")
    if member_id is None:
        return [
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(parent, "parent_member_id"),
                "the parent ledger does not say which member it holds, so its investment "
                "account cannot be matched to a capital account",
            )
        ]
    column = _column(ctx, member_id)
    accounts = _rows(parent, "accounts")
    out: list[Finding] = []
    with amount_guard(rule, out):
        derived = None if column is None else _int(column, CAPITAL_ENDING)
        if derived is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(parent, "accounts"),
                    f"the parent ledger holds member {member_id}, which has no readable "
                    f"ending capital in the package; the reciprocal pair cannot be struck",
                )
            )
        else:
            stated = sum(
                require_cents(
                    f"parent_ledger[{_account_no(a)}].balance_cents", a.get("balance_cents")
                )
                for a in accounts
            )
            if stated != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(parent, "accounts"),
                        f"the parent carries {fmt(stated)} of investment in the project "
                        f"entity across {len(accounts)} account(s); member {member_id} "
                        f"ends at {fmt(derived)} in the package "
                        f"(off by {fmt(variance(stated, derived))})",
                    )
                )
            else:
                out.append(
                    Finding(
                        rule,
                        Status.PASS,
                        "-",
                        f"the parent's investment of {fmt(stated)} agrees to member "
                        f"{member_id}'s capital account",
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# 16-20  presentation: nil, cash support, footnotes, captions, the cover
# --------------------------------------------------------------------------- #
@check("nil_is_genuine")
def check_nil_is_genuine(ctx: Context) -> list[Finding]:
    """A nil statement of operations is nil only if every result account is nil.

    A project entity in development capitalises what it spends, so a nil
    statement of operations is a real and correct presentation -- which is
    exactly why it survives as a presentation after it stops being true. The
    failure is a silent omission: a fee credit and a marketing cost that happen
    to net, so the bottom line is still zero and two accounts with real activity
    never appear anywhere the partner can see them.
    """
    rule = "nil_is_genuine"
    _sev(rule, Status.FAIL)
    income = ctx.one(DOC_INCOME_STATEMENT)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if income is None or ledger is None:
        return []
    presented_nil = income.get("presented_nil") is True or (
        not _rows(income, "revenue_rows") and not _rows(income, "expense_rows")
    )
    if not presented_nil:
        return [
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the statement of operations is presented with "
                f"{len(_rows(income, 'revenue_rows'))} revenue and "
                f"{len(_rows(income, 'expense_rows'))} expense line(s), so there is no "
                f"nil presentation to test",
            )
        ]
    out: list[Finding] = []
    checked = 0
    for account in _ledger_accounts(ctx):
        if (_text(account, "type") or "") not in RESULT_ACCOUNT_TYPES:
            continue
        with amount_guard(rule, out):
            debit = require_cents(
                f"ledger[{_account_no(account)}].debit_cents", account.get("debit_cents")
            )
            credit = require_cents(
                f"ledger[{_account_no(account)}].credit_cents", account.get("credit_cents")
            )
            checked += 1
            if has_activity(debit, credit):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(income, "presented_nil"),
                        f"the statement of operations is presented nil while ledger "
                        f"account {_account_label(account)} carries {fmt(debit)} of "
                        f"debits and {fmt(credit)} of credits; a bottom line of nil is "
                        f"not the same thing as no activity, and the omission is silent",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the nil statement of operations is genuine: all {checked} revenue and "
                f"expense account(s) are nil",
            )
        )
    return out


@check("cash_supported")
def check_cash_supported(ctx: Context) -> list[Finding]:
    """Cash is supported by a bank reconciliation; unsupported cash is flagged.

    Deliberately a FLAG, not a failure. The engine can see that the support is
    not there and it cannot manufacture it: a bank statement that has not arrived
    is a document that does not exist yet, and no amount of recomputation
    conjures one. The same is true of support that does not agree -- deciding
    which of the two figures is right needs somebody to look at the account, so
    the engine reports the position and hands it over.
    """
    rule = "cash_supported"
    _sev(rule, Status.FLAG)
    support = ctx.one(DOC_CASH_SUPPORT)
    ledger = ctx.one(DOC_ENTITY_LEDGER)
    if support is None or ledger is None:
        return []
    by_account = {
        _text(row, "account_no"): row for row in _rows(support, "reconciliations")
    }
    out: list[Finding] = []
    checked = 0
    for account in ledger_accounts_by_role(ctx, ROLE_CASH):
        no = _account_no(account)
        with amount_guard(rule, out):
            balance = account_net(account, label=f"ledger[{no}]")
            checked += 1
            row = by_account.get(no)
            if row is None or _bool(row, "support_attached") is not True:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(support, f"reconciliations/{no}"),
                        f"cash account {_account_label(account)} is reported at "
                        f"{fmt(balance)} with no bank reconciliation attached; the "
                        f"support is a document the engine cannot produce, so the "
                        f"balance goes to a person",
                    )
                )
                continue
            reconciled = require_cents(
                f"cash_support[{no}].reconciled_balance_cents",
                row.get("reconciled_balance_cents"),
            )
            if reconciled != balance:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(support, f"reconciliations/{no}"),
                        f"cash account {_account_label(account)} is reported at "
                        f"{fmt(balance)} and its bank reconciliation as of "
                        f"{_text(row, 'statement_date') or '-'} reconciles to "
                        f"{fmt(reconciled)} (off by {fmt(variance(balance, reconciled))}); "
                        f"which figure is right is a question about the account",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} cash account(s) are supported by a bank reconciliation "
                f"that agrees to the reported balance",
            )
        )
    return out


@check("footnote_figures")
def check_footnote_figures(ctx: Context) -> list[Finding]:
    """Every figure quoted inside a footnote equals the figure in the cell it describes.

    A note is prose with a number in it, retyped, and the number is the part
    nobody re-reads. Notes are also where last period's figure survives longest:
    the sentence is still true in shape, the amount is a month old, and it sits
    beside a statement that has moved. Each note names the cell it quotes and the
    engine resolves it.
    """
    rule = "footnote_figures"
    _sev(rule, Status.FAIL)
    notes_doc = ctx.one(DOC_FOOTNOTES)
    if notes_doc is None:
        return []
    out: list[Finding] = []
    checked = 0
    for note in _notes(ctx):
        note_id = _text(note, "note_id") or "?"
        ref = _text(note, "cell_ref")
        with amount_guard(rule, out):
            quoted = require_cents(f"footnote[{note_id}].quoted_cents", note.get("quoted_cents"))
            if ref is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(notes_doc, f"notes/{note_id}"),
                        f"note {note_id} quotes {fmt(quoted)} and names no cell; a figure "
                        f"in a note that describes no cell cannot be checked against "
                        f"anything",
                    )
                )
                continue
            derived = resolve_cell(ctx, ref)
            if derived is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(notes_doc, f"notes/{note_id}/cell_ref"),
                        f"note {note_id} quotes {fmt(quoted)} from {ref}, which is not a "
                        f"cell this package carries",
                    )
                )
                continue
            checked += 1
            if quoted != derived:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(notes_doc, f"notes/{note_id}/quoted_cents"),
                        f"note {note_id} quotes {fmt(quoted)} for {ref}; that cell prints "
                        f"{fmt(derived)} (off by {fmt(variance(quoted, derived))})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} quoted figure(s) equal the cell each note describes",
            )
        )
    return out


@check("caption_matches_type")
def check_caption_matches_type(ctx: Context) -> list[Finding]:
    """Each schedule's period caption matches what the schedule measures.

    A cost-to-date schedule captioned as period activity is the quietest wrong
    figure in the package: every number on it is right, and a reader adds a month
    of spend that was really every month since the ground broke. Nothing on the
    page contradicts the caption, which is why it survives review, and the
    caption is the only thing telling the partner which of the two they are
    looking at.
    """
    rule = "caption_matches_type"
    _sev(rule, Status.FAIL)
    docs = _captioned_docs(ctx)
    if not docs:
        return []
    out: list[Finding] = []
    checked = 0
    for doc in docs:
        schedule_type = _text(doc, "schedule_type") or ""
        caption = _text(doc, "caption")
        if schedule_type not in SCHEDULE_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(doc, "schedule_type"),
                    f"{doc.get('doc_type', '?')} declares itself {schedule_type!r}, which "
                    f"is not one of {SCHEDULE_TYPES}; what the schedule measures cannot "
                    f"be decided, so neither can its caption",
                )
            )
            continue
        if caption is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(doc, "caption"),
                    f"{doc.get('doc_type', '?')} is a {schedule_type} schedule and "
                    f"carries no caption; the caption is the only thing on the page that "
                    f"says which period the figures belong to",
                )
            )
            continue
        checked += 1
        ok, offending = caption_matches(schedule_type, caption)
        if ok:
            continue
        if offending:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(doc, "caption"),
                    f"{doc.get('doc_type', '?')} is a {schedule_type} schedule captioned "
                    f"{caption!r}, which says {', '.join(repr(m) for m in offending)}; the "
                    f"figures on it are cumulative and the caption presents them as one "
                    f"period's activity",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(doc, "caption"),
                    f"{doc.get('doc_type', '?')} is a {schedule_type} schedule captioned "
                    f"{caption!r}, which says nothing about the period it covers",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} captioned schedule(s) carry a caption that matches what "
                f"they measure",
            )
        )
    return out


@check("cover_consistent")
def check_cover_consistent(ctx: Context) -> list[Finding]:
    """Cover assertions are consistent with every disclosed exception.

    The cover is written first and the exceptions are found last, so the cover
    keeps asserting a package that no longer exists. It is also the only page
    most readers read closely, which makes an assertion of no exceptions over
    notes that disclose one the single most misleading sentence the package can
    contain.
    """
    rule = "cover_consistent"
    _sev(rule, Status.FAIL)
    cover = ctx.one(DOC_PACKAGE_COVER)
    if cover is None:
        return []
    disclosed = _disclosed_exceptions(ctx)
    disclosed_ids = [_text(r, "exception_id") or "?" for r in disclosed]
    referenced = cover.get("referenced_exception_ids")
    referenced_ids = (
        [r for r in referenced if isinstance(r, str)] if isinstance(referenced, list) else []
    )
    out: list[Finding] = []
    if cover.get("asserts_no_exceptions") is True and disclosed:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(cover, "asserts_no_exceptions"),
                f"the basis of presentation asserts the package is free of exceptions "
                f"while the notes disclose {len(disclosed)} "
                f"({', '.join(disclosed_ids)}); the cover is the page the partner reads "
                f"closest",
            )
        )
    for exception_id in disclosed_ids:
        if exception_id not in referenced_ids:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(cover, "referenced_exception_ids"),
                    f"exception {exception_id} is disclosed and the cover does not "
                    f"reference it; an exception the basis of presentation does not "
                    f"acknowledge is an exception the reader is not directed to",
                )
            )
    for exception_id in referenced_ids:
        if exception_id not in disclosed_ids:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(cover, "referenced_exception_ids"),
                    f"the cover references exception {exception_id}, which the package "
                    f"does not disclose; the reader is sent to a note that is not there",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the cover's assertions are consistent with all {len(disclosed)} "
                f"disclosed exception(s)",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 21-25  what actually left the building
# --------------------------------------------------------------------------- #
@check("checkrows_excluded")
def check_checkrows_excluded(ctx: Context) -> list[Finding]:
    """Internal tie-out check rows are excluded from the released print area.

    Every statement in the package is built over a row that subtracts one figure
    from another and expects nil. Those rows are the reviewer's, not the
    partner's: a line reading "check: assets less liabilities and capital -" in
    an issued statement invites the exact question nobody wants to answer, and a
    non-nil one invites a worse one.
    """
    rule = "checkrows_excluded"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_RELEASE_LOG)
    if log is None:
        return []
    rows = _check_rows(ctx)
    out: list[Finding] = []
    for row in rows:
        if _bool(row, "in_print_area") is True:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"check_rows/{_text(row, 'row_id') or '?'}"),
                    f"tie-out row {_text(row, 'row_id') or '?'} "
                    f"({_text(row, 'label') or 'unlabelled'}) on "
                    f"{_text(row, 'statement') or 'an unnamed statement'} is inside the "
                    f"released print area; the reviewer's arithmetic ships to the "
                    f"partner as though it were a line of the statement",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(rows)} internal tie-out row(s) are outside the released print "
                f"area",
            )
        )
    return out


@check("no_preparer_artifacts")
def check_no_preparer_artifacts(ctx: Context) -> list[Finding]:
    """No preparer-only artifact appears in the released package.

    A tickmark sheet, a ledger extract worksheet, a reviewer comment log: each
    one is part of how the package was built and none of them is part of the
    package. They travel with the file because they live in the same workbook,
    and a released comment log is a reviewer's private doubts in an investor's
    inbox.
    """
    rule = "no_preparer_artifacts"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_RELEASE_LOG)
    if log is None:
        return []
    artifacts = _artifacts(ctx)
    out: list[Finding] = []
    released = 0
    for artifact in artifacts:
        if _bool(artifact, "released") is True:
            released += 1
        if _bool(artifact, "preparer_only") is True and _bool(artifact, "released") is True:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(log, f"artifacts/{_text(artifact, 'artifact_id') or '?'}"),
                    f"{_text(artifact, 'label') or 'an unlabelled artifact'} "
                    f"({_text(artifact, 'artifact_id') or '?'}) is a preparer-only "
                    f"artifact and is marked released; it is part of how the package was "
                    f"built and not part of the package",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the {released} released artifact(s) of {len(artifacts)} carry no "
                f"preparer-only material",
            )
        )
    return out


@check("prior_period_continuity")
def check_prior_period_continuity(ctx: Context) -> list[Finding]:
    """Opening balances equal the prior package's closing balances.

    The partner holds last month's package. When this month opens somewhere else,
    every figure after it is defensible on its own and the series is not, and the
    restatement is discovered by the reader rather than declared by the preparer.
    """
    rule = "prior_period_continuity"
    _sev(rule, Status.FAIL)
    prior = _prior_package(ctx)
    statement = _capital(ctx)
    if prior is None or statement is None:
        return []
    closing = _prior_closing_map(ctx)
    out: list[Finding] = []
    checked = 0
    for member in _members(ctx):
        member_id = _member_id(member)
        column = _column(ctx, member_id)
        if column is None:
            continue  # capital_agrees_ledger owns a member with no column
        prior_row = closing.get(member_id)
        with amount_guard(rule, out):
            opening = require_cents(
                f"capital[{member_id}].{CAPITAL_BEGINNING}", column.get(CAPITAL_BEGINNING)
            )
            if prior_row is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(prior, f"closing_capital/{member_id}"),
                        f"member {_member_label(member)} opens at {fmt(opening)} and the "
                        f"{_text(prior, 'period') or 'prior'} package carries no closing "
                        f"balance for it; the series starts again this period",
                    )
                )
                continue
            checked += 1
            closed = require_cents(
                f"prior_package[{member_id}].ending_cents", prior_row.get("ending_cents")
            )
            if opening != closed:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{member_id}/{CAPITAL_BEGINNING}"),
                        f"member {_member_label(member)} opens at {fmt(opening)}; the "
                        f"{_text(prior, 'period') or 'prior'} package closed it at "
                        f"{fmt(closed)} (off by {fmt(variance(opening, closed))}), and "
                        f"the partner holds that package",
                    )
                )
    total_column = _column(ctx, TOTAL_COLUMN)
    if total_column is not None:
        with amount_guard(rule, out):
            opening_total = require_cents(
                f"capital[{TOTAL_COLUMN}].{CAPITAL_BEGINNING}",
                total_column.get(CAPITAL_BEGINNING),
            )
            closed_total = require_cents(
                "prior_package.closing_total_cents", prior.get("closing_total_cents")
            )
            if opening_total != closed_total:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(statement, f"columns/{TOTAL_COLUMN}/{CAPITAL_BEGINNING}"),
                        f"members' capital opens at {fmt(opening_total)} in total; the "
                        f"{_text(prior, 'period') or 'prior'} package closed at "
                        f"{fmt(closed_total)} "
                        f"(off by {fmt(variance(opening_total, closed_total))})",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} member opening balance(s) and the total continue the "
                f"{_text(prior, 'period') or 'prior'} package exactly",
            )
        )
    return out


@check("package_complete")
def check_package_complete(ctx: Context) -> list[Finding]:
    """Every statement named in the contents exists and is non-empty.

    This is the control that keeps the rest of the registry honest, so it owns
    every absence. A control whose document is missing produces nothing at all
    rather than a PASS: a package that omits its statement of operations must not
    come back clean on the controls that read it, because a clean report on
    evidence that is not there is worse than no report.

    Two things are asked. Every artifact the engine depends on is present exactly
    once -- one of each, because two trial balances is a package where nobody
    knows which was issued. And every statement the contents page names is not
    only present but carries something, since a contents page is a promise.
    """
    rule = "package_complete"
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
                    f"{len(found)} {doc_type} documents present; the package carries "
                    f"exactly one of each, or nobody can say which one was issued",
                )
            )
    cover = ctx.one(DOC_PACKAGE_COVER)
    if cover is not None:
        contents = cover.get("contents")
        listed = [c for c in contents if isinstance(c, str)] if isinstance(contents, list) else []
        if not listed:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(cover, "contents"),
                    "the cover names no statements; a package with no contents page "
                    "cannot be checked for completeness",
                )
            )
        for name in listed:
            doc = ctx.one(name)
            if doc is None:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(cover, f"contents/{name}"),
                        f"the contents page names {name} and the package does not carry "
                        f"it; a contents page is a promise",
                    )
                )
                continue
            if not _statement_non_empty(doc, STATEMENT_CONTENT.get(name, ())):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(doc, "-"),
                        f"{name} is named in the contents and carries nothing; an empty "
                        f"statement is issued as though it said something",
                    )
                )
    for label, value in (("period_start", ctx.period_start), ("period_end", ctx.period_end)):
        if _parse_date(value) is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    "-",
                    f"{label} {value!r} is not a readable date; the period an executed "
                    f"draw is tested against cannot be bounded",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} artifacts are present exactly once and every "
                f"statement named in the contents carries content",
            )
        )
    return out


@check("release_gate")
def check_release_gate(ctx: Context) -> list[Finding]:
    """The package is held unless every control above passes.

    The only control that reads the run's own output, and the reason the engine
    is worth running at all: everything above it produces findings, and this
    turns findings into the one decision that matters. One open exception is
    enough to hold the package, and there is no materiality gate -- materiality
    is a judgement about a figure the partner has not seen yet, and the engine's
    job is to make sure whoever makes that judgement is looking at the exception
    rather than at a package already sent.

    The package's own release record is audited too. A record that says the
    controls were not cleared, on a package marked released, is the failure in
    its plainest form: somebody knew.
    """
    rule = "release_gate"
    _sev(rule, Status.FAIL)
    log = ctx.one(DOC_RELEASE_LOG)
    if log is None:
        return []
    blocking = blocking_findings(ctx, rule)
    required = release_decision_required(len(blocking))
    stated = _text(log, "release_decision")
    cleared = _bool(log, "controls_cleared")
    out: list[Finding] = []
    if stated not in RELEASE_DECISIONS:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(log, "release_decision"),
                f"the release record states {stated!r}, which is not one of "
                f"{RELEASE_DECISIONS}; whether the package was issued cannot be read",
            )
        )
    elif blocking and stated != RELEASE_HELD:
        rules_fired = sorted({f.rule for f in blocking})
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(log, "release_decision"),
                f"the package is marked {stated} with {len(blocking)} open exception(s) "
                f"across {len(rules_fired)} control(s) ({', '.join(rules_fired)}); it "
                f"must be {required} until every one of them is cleared or disclosed",
            )
        )
    if cleared is not True and stated == RELEASE_RELEASED:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                ctx.loc(log, "controls_cleared"),
                "the release record itself says the controls were not cleared, and the "
                "package is marked released; the exception was known before it was sent",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"the package is {stated} with {len(blocking)} open exception(s), which "
                f"is the decision its control position requires",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one package file.

    Findings are accumulated onto the context as the registry runs, so
    ``release_gate`` -- the last control, and the only one that is a control over
    the other controls -- sees exactly what the twenty-four before it found.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top level must be a JSON object")
    ctx = Context(path=path, data=raw)
    report = DocumentReport(document=ctx.file_id)
    for _rule_id, fn in REGISTRY:
        found = fn(ctx)
        report.findings.extend(found)
        ctx.prior_findings.extend(found)
    return report


def analyze_folder(folder: Path) -> list[DocumentReport]:
    """Analyze every ``.json`` package file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of package-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
