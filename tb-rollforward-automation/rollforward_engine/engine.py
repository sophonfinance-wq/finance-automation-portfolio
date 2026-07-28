"""
Controls for the trial-balance roll-forward engine.
===================================================

Every control re-derives what the workpaper claims from the artifacts beneath it
and compares with exact ``==``. The registry order is the report order: scope
first (is the column structure the confirmed population), then source (is the
extract readable and balanced), then mapping (does every cell tie the extract),
then presentation (eliminations, combined, backup, links, twins, fees), then the
two review signals.

The controls share one kernel with the generator (:mod:`.workpaper`), so a
control and the corpus it audits cannot quietly disagree about how a cell is
derived. That is the point: the failure modes this engine exists for are the
ones that *survive* a footing check, and the only defence against those is
re-derivation from the declared roles -- the balance column found by its header
role, the title column found by its role, the equivalence map applied the same
way everywhere.
"""

from __future__ import annotations

import contextlib
import functools
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .model import (
    DOC_BACKUP_TAB,
    DOC_CHART_MAP,
    DOC_ENTITY_REGISTER,
    DOC_PRIOR_STRUCTURE,
    DOC_SOURCE_EXTRACT,
    DOC_TWIN_EXPORT,
    DOC_TYPES,
    DOC_WORKPAPER,
    ENTITY_STATUSES,
    STATUS_CONTINUING,
    STATUS_EXCLUDED,
    STATUS_FINAL_YEAR,
    STATUS_FIRST_YEAR,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents
from .workpaper import (
    activity_map,
    balance_map,
    books_by_code,
    category_map,
    codes_collected,
    column_entities,
    combined_expected,
    equivalence_map,
    expected_backup,
    expected_cells,
    memo_rows,
    parse_iso,
    register_rows,
    row_suffix,
    title_map,
    workpaper_columns,
    workpaper_rows,
)

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~rollforward_engine.money.AmountInvalidError` as a finding."""
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
# Shared derived views
# --------------------------------------------------------------------------- #


def _row_codes(ctx: Context) -> list[str]:
    """The workpaper's row codes in row order, duplicates preserved."""
    wp = ctx.one(DOC_WORKPAPER)
    return [str(r.get("row_code", "?")) for r in workpaper_rows(wp)]


def _cells_of(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cells = row.get("cells")
    if not isinstance(cells, dict):
        return {}
    return {str(k): v for k, v in cells.items() if isinstance(v, dict)}


def _cell_value(rule: str, entity_id: str, idx: int, cell: dict[str, Any]) -> int:
    return require_cents(
        f"workpaper[{entity_id}/row {idx}]/value_cents", cell.get("value_cents")
    )


def _actual_grid(ctx: Context, rule: str, out: list[Finding]) -> dict[str, dict[int, int]]:
    """``{entity_id: {row_index: cents}}`` as the workpaper actually carries it.

    Malformed amounts are contained to their cell via the amount guard so one bad
    value does not silence a whole column's comparison.
    """
    wp = ctx.one(DOC_WORKPAPER)
    grid: dict[str, dict[int, int]] = {}
    for idx, row in enumerate(workpaper_rows(wp)):
        for entity_id, cell in _cells_of(row).items():
            with amount_guard(rule, out):
                grid.setdefault(entity_id, {})[idx] = _cell_value(
                    rule, entity_id, idx, cell
                )
    return grid


def _expected_grid(ctx: Context) -> dict[str, dict[int, int]]:
    return expected_cells(
        ctx.one(DOC_ENTITY_REGISTER),
        ctx.one(DOC_SOURCE_EXTRACT),
        ctx.one(DOC_CHART_MAP),
        _row_codes(ctx),
    )


def _elim_rows(ctx: Context) -> dict[int, int]:
    wp = ctx.one(DOC_WORKPAPER)
    if not isinstance(wp, dict):
        return {}
    elim = wp.get("eliminations")
    if not isinstance(elim, dict):
        return {}
    rows = elim.get("rows")
    if not isinstance(rows, dict):
        return {}
    out: dict[int, int] = {}
    for key, value in rows.items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        out[idx] = value
    return out


def _register_by_id(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in register_rows(ctx.one(DOC_ENTITY_REGISTER)):
        entity_id = row.get("entity_id")
        if isinstance(entity_id, str) and entity_id not in out:
            out[entity_id] = row
    return out


# --------------------------------------------------------------------------- #
# 1. Completeness
# --------------------------------------------------------------------------- #
_SEV_SET_COMPLETE = _sev("set_complete", Status.FAIL)


@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """The workpaper file carries one of each artifact and a readable period.

    Every later control assumes its artifact exists; this one owns absence, so a
    missing backup tab is one finding here rather than a different complaint
    from every rule that wanted it.
    """
    rule = "set_complete"
    out: list[Finding] = []
    for doc_type in DOC_TYPES:
        found = ctx.docs(doc_type)
        if not found:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"required artifact {doc_type!r} is missing -- the cycle "
                    "cannot be audited from a partial record",
                )
            )
        elif len(found) > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"artifact {doc_type!r} appears {len(found)} times; the file "
                    "must carry exactly one of each",
                )
            )
    if ctx.fiscal_start is None or ctx.fiscal_end is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "fiscal_year_start/-",
                "the fiscal-year window is absent or unreadable -- registration "
                "dates cannot be tested against a window the engine invents",
            )
        )
    elif ctx.fiscal_start > ctx.fiscal_end:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "fiscal_year_start/-",
                f"fiscal year runs backwards ({ctx.fiscal_start} after "
                f"{ctx.fiscal_end})",
            )
        )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "all artifacts present, period readable")
        )
    return out


# --------------------------------------------------------------------------- #
# 2. Register integrity
# --------------------------------------------------------------------------- #
_SEV_REG = _sev("reg_entities_valid", Status.FAIL)


@check("reg_entities_valid")
def check_reg_entities_valid(ctx: Context) -> list[Finding]:
    """Entity ids are unique, statuses known, and column entities carry books.

    The register is the confirmed filing population -- the one list everybody
    signed off. A duplicated id or an unknown status means two people can read
    the same register and roll forward two different workpapers.
    """
    rule = "reg_entities_valid"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    books = books_by_code(ctx.one(DOC_SOURCE_EXTRACT))
    seen: set[str] = set()
    for row in register_rows(register):
        entity_id = row.get("entity_id")
        loc = ctx.loc(register or {}, f"entities[{entity_id}]")
        if not isinstance(entity_id, str) or not entity_id:
            out.append(
                Finding(rule, Status.FAIL, loc, "an entity row carries no entity_id")
            )
            continue
        if entity_id in seen:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    loc,
                    f"entity id {entity_id!r} appears more than once -- the same "
                    "entity cannot be rolled forward twice",
                )
            )
        seen.add(entity_id)
        status = row.get("status")
        if status not in ENTITY_STATUSES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    loc,
                    f"status {status!r} is not one of {ENTITY_STATUSES} -- an "
                    "uncharacterised entity is one nobody decided the "
                    "roll-forward treatment for",
                )
            )
            continue
        if status in (STATUS_CONTINUING, STATUS_FIRST_YEAR):
            book_code = row.get("book_code")
            if not isinstance(book_code, str) or book_code not in books:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        loc,
                        f"column entity {entity_id!r} names book "
                        f"{book_code!r}, which the extract does not carry -- a "
                        "column with no book cannot be populated, only invented",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the entity register is internally sound")
        )
    return out


# --------------------------------------------------------------------------- #
# 3-5. Source extract
# --------------------------------------------------------------------------- #
_SEV_MEMO = _sev("src_code_rows_only", Status.FAIL)


@check("src_code_rows_only")
def check_src_code_rows_only(ctx: Context) -> list[Finding]:
    """Memo-row accounts never reach the backup tab.

    A book table carries side-schedule annotations whose codes *look* like
    trial-balance rows but sit in memo position. Population reads code rows
    only; a memo account surfacing in the backup means the harvest read by
    position, not by role -- the same class of error as reading the wrong
    value column.
    """
    rule = "src_code_rows_only"
    out: list[Finding] = []
    source = ctx.one(DOC_SOURCE_EXTRACT)
    backup = ctx.one(DOC_BACKUP_TAB)
    backup_accounts: set[str] = set()
    if isinstance(backup, dict):
        rows = backup.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("account"), str):
                    backup_accounts.add(row["account"])
    for book in books_by_code(source).values():
        code_accounts = {
            r.get("account")
            for r in book.get("rows", [])
            if isinstance(r, dict) and r.get("position") == "code"
        }
        for row in memo_rows(book):
            account = row.get("account")
            if not isinstance(account, str):
                continue
            if account in backup_accounts and account not in code_accounts:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(source or {}, f"memo[{account}]"),
                        f"memo-row account {account!r} was harvested into the "
                        "backup tab -- memo rows are side-schedule annotations "
                        "and populating one double counts what a schedule "
                        "already explains",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "only code-position rows were harvested")
        )
    return out


_SEV_BOOKS = _sev("src_books_self_balance", Status.FAIL)


@check("src_books_self_balance")
def check_src_books_self_balance(ctx: Context) -> list[Finding]:
    """Every book in the extract sums to zero over its code rows.

    A book that does not foot was caught mid-posting or truncated in transit,
    and populating from it spreads the imbalance into a workpaper that will
    then fail in a place far from the cause.
    """
    rule = "src_books_self_balance"
    out: list[Finding] = []
    source = ctx.one(DOC_SOURCE_EXTRACT)
    for book_code, book in sorted(books_by_code(source).items()):
        with amount_guard(rule, out):
            balances = balance_map(book, field_prefix=f"{book_code}/")
            net = sum(balances.values())
            if net != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(source or {}, f"books[{book_code}]"),
                        f"book {book_code!r} sums to {fmt(net)}, not zero -- an "
                        "unbalanced extract is incomplete or mid-posting, and "
                        "nothing populated from it can be trusted",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every book self-balances to zero"))
    return out


_SEV_BASIS = _sev("src_balance_basis", Status.FAIL)


@check("src_balance_basis")
def check_src_balance_basis(ctx: Context) -> list[Finding]:
    """No column was populated from the activity column.

    The signature defect of this whole cycle: a book carrying monthly activity
    beside the balance, and a harvest that read by position. Activity foots to
    zero exactly the way balances do, so the resulting column self-balances and
    every footing check passes. The only tell is the pattern -- the column's
    differences from the balance derivation all equal the activity figures --
    and this control looks for exactly that pattern so the finding can say what
    actually happened rather than reporting a hundred unrelated cell breaks.
    """
    rule = "src_balance_basis"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    source = ctx.one(DOC_SOURCE_EXTRACT)
    books = books_by_code(source)
    equiv = equivalence_map(ctx.one(DOC_CHART_MAP))
    row_codes = _row_codes(ctx)
    expected = _expected_grid(ctx)
    actual = _actual_grid(ctx, rule, out)
    for entity in column_entities(register):
        entity_id = str(entity.get("entity_id", "?"))
        book = books.get(str(entity.get("book_code", "")))
        if book is None:
            continue
        activity = activity_map(book)
        if not activity:
            continue  # no activity column, no wrong column to read
        # Re-derive the grid this column WOULD carry if populated from activity.
        consumed: set[str] = set()
        wrong: dict[int, int] = {}
        for idx, row_code in enumerate(row_codes):
            value = 0
            for code in codes_collected(row_code, equiv):
                if code in consumed:
                    continue
                if code in activity:
                    value += activity[code]
                    consumed.add(code)
            wrong[idx] = value
        exp = expected.get(entity_id, {})
        act = actual.get(entity_id, {})
        diff_rows = [i for i in exp if act.get(i, 0) != exp[i]]
        if diff_rows and all(act.get(i, 0) == wrong.get(i, 0) for i in diff_rows):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"workpaper:{entity_id}/column",
                    f"column {entity_id!r} matches the book's monthly-activity "
                    f"column on every differing row ({len(diff_rows)} of them) "
                    "-- it was populated from the activity column, not the "
                    "balance column. Activity foots to zero too, so the column "
                    "self-balances while carrying movement instead of balances",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every column derives from its book's declared balance column",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 6-9. Roll-forward scope
# --------------------------------------------------------------------------- #
_SEV_FINAL = _sev("scope_final_year_removed", Status.FAIL)


@check("scope_final_year_removed")
def check_scope_final_year_removed(ctx: Context) -> list[Finding]:
    """Entities in their final year lost their column.

    A final-year entity filed its last return off last year's workpaper.
    Carrying its column forward invites populating it, and populating it
    invites paying a fee the dissolution already ended.
    """
    rule = "scope_final_year_removed"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    columns = {c.get("entity_id") for c in workpaper_columns(ctx.one(DOC_WORKPAPER))}
    for row in register_rows(register):
        if row.get("status") != STATUS_FINAL_YEAR:
            continue
        entity_id = row.get("entity_id")
        if entity_id in columns:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register or {}, f"entities[{entity_id}]"),
                    f"final-year entity {entity_id!r} still has a workpaper "
                    "column -- its last return was prepared off the prior "
                    "year, and a live column here will be populated by habit",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every final-year entity was retired")
        )
    return out


_SEV_RENAME = _sev("scope_renamed_once", Status.FAIL)


@check("scope_renamed_once")
def check_scope_renamed_once(ctx: Context) -> list[Finding]:
    """A renamed entity appears exactly once, under its new identity.

    The classic double count: the old name survives in one system while the new
    name arrives from another, and the roll-forward carries both columns for
    what is legally one entity -- one fee paid twice, one balance counted twice.
    """
    rule = "scope_renamed_once"
    out: list[Finding] = []
    prior = ctx.one(DOC_PRIOR_STRUCTURE)
    columns = [
        str(c.get("entity_id", "?")) for c in workpaper_columns(ctx.one(DOC_WORKPAPER))
    ]
    renames = []
    if isinstance(prior, dict) and isinstance(prior.get("renames"), list):
        renames = [r for r in prior["renames"] if isinstance(r, dict)]
    for rename in renames:
        old_id = str(rename.get("old_entity_id", "?"))
        new_id = str(rename.get("new_entity_id", "?"))
        loc = ctx.loc(prior or {}, f"renames[{old_id}->{new_id}]")
        if old_id in columns:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    loc,
                    f"renamed entity still carries a column under its old "
                    f"identity {old_id!r} beside {new_id!r} -- one entity, two "
                    "columns, every balance at risk of being counted twice",
                )
            )
        if columns.count(new_id) > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    loc,
                    f"new identity {new_id!r} appears {columns.count(new_id)} "
                    "times among the columns",
                )
            )
        if new_id not in columns:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    loc,
                    f"renamed entity {new_id!r} has no column at all -- the "
                    "rename dropped the entity instead of carrying it",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every rename carried exactly one column over"
            )
        )
    return out


_SEV_FIRSTYEAR = _sev("scope_first_year_registered", Status.FAIL)


@check("scope_first_year_registered")
def check_scope_first_year_registered(ctx: Context) -> list[Finding]:
    """First-year entities carry a registration date inside the fiscal window.

    The preparer's first question about a new entity is the date its first
    period starts. A missing or out-of-window registration date means the
    first-year return will be prepared over a period nobody verified.
    """
    rule = "scope_first_year_registered"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    start, end = ctx.fiscal_start, ctx.fiscal_end
    for row in register_rows(register):
        if row.get("status") != STATUS_FIRST_YEAR:
            continue
        entity_id = row.get("entity_id")
        loc = ctx.loc(register or {}, f"entities[{entity_id}]/registration_date")
        registered = parse_iso(row.get("registration_date"))
        if registered is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    loc,
                    f"first-year entity {entity_id!r} carries no readable "
                    "registration date -- its first-period start is the one "
                    "fact the preparer cannot infer",
                )
            )
            continue
        if start is not None and end is not None and not (start <= registered <= end):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    loc,
                    f"first-year entity {entity_id!r} was registered "
                    f"{registered}, outside the fiscal window {start}..{end} -- "
                    "either the status is wrong or the date is",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every first-year entity is registered inside the window",
            )
        )
    return out


_SEV_SCOPE = _sev("scope_register_matches_columns", Status.FAIL)


@check("scope_register_matches_columns")
def check_scope_register_matches_columns(ctx: Context) -> list[Finding]:
    """The column set equals the register's column population, both directions.

    Completeness beats spot-checks. A column with no register row is an entity
    nobody confirmed; a register row with no column is a filing that will be
    missed. Both directions, exact set equality.
    """
    rule = "scope_register_matches_columns"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    wp = ctx.one(DOC_WORKPAPER)
    owed = {str(r.get("entity_id", "?")) for r in column_entities(register)}
    have = [str(c.get("entity_id", "?")) for c in workpaper_columns(wp)]
    for entity_id in sorted(owed - set(have)):
        out.append(
            Finding(
                rule,
                Status.FAIL,
                f"workpaper:-/columns[{entity_id}]",
                f"registered entity {entity_id!r} has no workpaper column -- a "
                "missing column is a filing that will quietly not happen",
            )
        )
    for entity_id in sorted(set(have) - owed):
        out.append(
            Finding(
                rule,
                Status.FAIL,
                f"workpaper:-/columns[{entity_id}]",
                f"column {entity_id!r} is not in the confirmed register -- an "
                "unconfirmed column is scope nobody signed off",
            )
        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "columns and register agree one-to-one, both directions",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# 10-15. Mapping
# --------------------------------------------------------------------------- #
_SEV_FWD = _sev("map_forward_complete", Status.FAIL)


@check("map_forward_complete")
def check_map_forward_complete(ctx: Context) -> list[Finding]:
    """Every nonzero balance of every mapped book lands somewhere in its column.

    The forward sweep. A balance no row collects -- typically one riding a chart
    code the row list never carried -- simply vanishes, and because both sides
    still foot, only enumeration finds it.
    """
    rule = "map_forward_complete"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    source = ctx.one(DOC_SOURCE_EXTRACT)
    books = books_by_code(source)
    equiv = equivalence_map(ctx.one(DOC_CHART_MAP))
    row_codes = _row_codes(ctx)
    collected: set[str] = set()
    for row_code in row_codes:
        collected.update(codes_collected(row_code, equiv))
    for entity in column_entities(register):
        entity_id = str(entity.get("entity_id", "?"))
        book = books.get(str(entity.get("book_code", "")))
        if book is None:
            continue
        with amount_guard(rule, out):
            balances = balance_map(book, field_prefix=f"{entity_id}/")
            for suffix in sorted(balances):
                if balances[suffix] != 0 and suffix not in collected:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            f"source_extract:{entity_id}/{suffix}",
                            f"book balance {fmt(balances[suffix])} on code "
                            f"{suffix!r} is collected by no workpaper row -- "
                            "the balance lands nowhere, and both sides still "
                            "foot, which is why only enumeration catches it",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every nonzero book balance is collected"
            )
        )
    return out


_SEV_REV = _sev("map_reverse_traces", Status.FAIL)


@check("map_reverse_traces")
def check_map_reverse_traces(ctx: Context) -> list[Finding]:
    """Every nonzero workpaper cell traces back to the extract.

    The reverse sweep: a phantom -- a cell with a value the book does not
    support -- is a number somebody keyed. The workpaper's job is to carry the
    ledger's numbers, not to author new ones.
    """
    rule = "map_reverse_traces"
    out: list[Finding] = []
    expected = _expected_grid(ctx)
    actual = _actual_grid(ctx, rule, out)
    row_codes = _row_codes(ctx)
    for entity_id in sorted(actual):
        exp = expected.get(entity_id, {})
        for idx in sorted(actual[entity_id]):
            got = actual[entity_id][idx]
            if got != 0 and exp.get(idx, 0) == 0:
                code = row_codes[idx] if idx < len(row_codes) else "?"
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        f"workpaper:{entity_id}/row {idx} ({code})",
                        f"cell carries {fmt(got)} but the book supports no "
                        "balance on that row -- a phantom value is a number "
                        "somebody authored rather than harvested",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every nonzero cell traces to the extract")
        )
    return out


_SEV_EXACT = _sev("map_values_exact", Status.FAIL)


@check("map_values_exact")
def check_map_values_exact(ctx: Context) -> list[Finding]:
    """Every cell equals its re-derivation from the extract, to the penny.

    The core tie. Exact ``==`` -- a tolerated penny is a figure the ledger does
    not support, inherited by every schedule downstream.
    """
    rule = "map_values_exact"
    out: list[Finding] = []
    expected = _expected_grid(ctx)
    actual = _actual_grid(ctx, rule, out)
    row_codes = _row_codes(ctx)
    for entity_id in sorted(expected):
        exp = expected[entity_id]
        act = actual.get(entity_id, {})
        for idx in sorted(exp):
            if act.get(idx, 0) != exp[idx]:
                code = row_codes[idx] if idx < len(row_codes) else "?"
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        f"workpaper:{entity_id}/row {idx} ({code})",
                        f"cell carries {fmt(act.get(idx, 0))}; the balance "
                        f"column derives {fmt(exp[idx])} -- the difference of "
                        f"{fmt(act.get(idx, 0) - exp[idx])} is a figure the "
                        "extract does not support",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every cell ties the extract to the penny"
            )
        )
    return out


_SEV_DUAL = _sev("map_dual_codes_sum", Status.FAIL)


@check("map_dual_codes_sum")
def check_map_dual_codes_sum(ctx: Context) -> list[Finding]:
    """Dual-code rows carry the sum of every code they collect.

    Two charts of accounts share one row. The cell owed there is the sum of the
    row's own codes plus their chart equivalents -- dropping either half leaves
    a balance stranded on a code the sheet displays but the sum ignored. The
    equivalence map itself must also be sound: an equivalence pointing at a row
    the workpaper does not carry maps a balance to nowhere.
    """
    rule = "map_dual_codes_sum"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    source = ctx.one(DOC_SOURCE_EXTRACT)
    chart = ctx.one(DOC_CHART_MAP)
    equiv = equivalence_map(chart)
    books = books_by_code(source)
    row_codes = _row_codes(ctx)
    own_codes: set[str] = set()
    for row_code in row_codes:
        own_codes.update(codes_collected(row_code, equiv))
    for canonical in sorted(equiv):
        if not any(canonical in codes_collected(rc, equiv) for rc in row_codes):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(chart or {}, f"equivalences[{canonical}]"),
                    f"equivalence {canonical!r}->{equiv[canonical]!r} names a "
                    "row code the workpaper does not carry -- the mapped "
                    "balance has nowhere to land",
                )
            )
    actual = _actual_grid(ctx, rule, out)
    multi = [
        (idx, rc)
        for idx, rc in enumerate(row_codes)
        if len(codes_collected(rc, equiv)) > 1
    ]
    for entity in column_entities(register):
        entity_id = str(entity.get("entity_id", "?"))
        book = books.get(str(entity.get("book_code", "")))
        if book is None:
            continue
        with amount_guard(rule, out):
            balances = balance_map(book, field_prefix=f"{entity_id}/")
            consumed: set[str] = set()
            for idx, row_code in enumerate(row_codes):
                codes = codes_collected(row_code, equiv)
                owed = 0
                for code in codes:
                    if code in consumed:
                        continue
                    if code in balances:
                        owed += balances[code]
                        consumed.add(code)
                if len(codes) > 1:
                    got = actual.get(entity_id, {}).get(idx, 0)
                    if got != owed:
                        out.append(
                            Finding(
                                rule,
                                Status.FAIL,
                                f"workpaper:{entity_id}/row {idx} ({row_code})",
                                f"dual-code row collects {codes} and is owed "
                                f"{fmt(owed)}, but carries {fmt(got)} -- part "
                                "of the balance is stranded on a code the sum "
                                "ignored",
                            )
                        )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                "every dual-code row sums all its codes through the map",
            )
        )
    return out


_SEV_DUP = _sev("map_duplicate_row_zero", Status.FAIL)


@check("map_duplicate_row_zero")
def check_map_duplicate_row_zero(ctx: Context) -> list[Finding]:
    """The later instance of a duplicated row code carries only zeros.

    Legacy sheets carry the same code twice under different labels. The first
    instance consumed the code; a value on the second is the same balance
    counted twice -- and the column still foots if the duplicate merely copies
    a prior year's habit.
    """
    rule = "map_duplicate_row_zero"
    out: list[Finding] = []
    row_codes = _row_codes(ctx)
    actual = _actual_grid(ctx, rule, out)
    seen: set[str] = set()
    for idx, row_code in enumerate(row_codes):
        if row_code not in seen:
            seen.add(row_code)
            continue
        for entity_id in sorted(actual):
            got = actual[entity_id].get(idx, 0)
            if got != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        f"workpaper:{entity_id}/row {idx} ({row_code})",
                        f"duplicated row code {row_code!r} carries {fmt(got)} "
                        "on its later instance -- the first instance consumed "
                        "the code, so this is the same balance twice",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every duplicated row code is zero later")
        )
    return out


_SEV_COL = _sev("col_self_balance", Status.FAIL)


@check("col_self_balance")
def check_col_self_balance(ctx: Context) -> list[Finding]:
    """Every entity column sums to zero.

    A trial-balance column is self-proving: assets, liabilities, equity and the
    year's activity net to zero or the column is not a trial balance. Necessary
    -- but deliberately not sufficient, which is why the basis and mapping
    controls exist beside it.
    """
    rule = "col_self_balance"
    out: list[Finding] = []
    actual = _actual_grid(ctx, rule, out)
    for entity_id in sorted(actual):
        net = sum(actual[entity_id].values())
        if net != 0:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"workpaper:{entity_id}/column",
                    f"column sums to {fmt(net)}, not zero -- something is "
                    "unmapped, dropped or half-posted in this column",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "every column sums to zero"))
    return out


# --------------------------------------------------------------------------- #
# 16-17. Eliminations and combined
# --------------------------------------------------------------------------- #
_SEV_ELIM = _sev("elim_covers_all_columns", Status.FAIL)


@check("elim_covers_all_columns")
def check_elim_covers_all_columns(ctx: Context) -> list[Finding]:
    """The eliminations range covers every entity column.

    Ranges written over last year's structure keep evaluating after columns are
    added beyond their end -- nothing errors, the new columns simply are not
    eliminated. Coverage is declared, so coverage is checked.
    """
    rule = "elim_covers_all_columns"
    out: list[Finding] = []
    wp = ctx.one(DOC_WORKPAPER)
    columns = [str(c.get("entity_id", "?")) for c in workpaper_columns(wp)]
    covered: list[str] = []
    if isinstance(wp, dict):
        elim = wp.get("eliminations")
        if isinstance(elim, dict) and isinstance(elim.get("covered_entities"), list):
            covered = [str(e) for e in elim["covered_entities"]]
    for entity_id in columns:
        if entity_id not in covered:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"workpaper:-/eliminations[{entity_id}]",
                    f"column {entity_id!r} sits outside the eliminations range "
                    "-- a range that ends at last year's final column silently "
                    "excludes every column added this year",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "the eliminations range covers every column")
        )
    return out


_SEV_COMBINED = _sev("combined_foots", Status.FAIL)


@check("combined_foots")
def check_combined_foots(ctx: Context) -> list[Finding]:
    """The combined column equals entity cells plus eliminations, row by row."""
    rule = "combined_foots"
    out: list[Finding] = []
    wp = ctx.one(DOC_WORKPAPER)
    row_codes = _row_codes(ctx)
    actual = _actual_grid(ctx, rule, out)
    elim = _elim_rows(ctx)
    expected = combined_expected(actual, elim, len(row_codes))
    combined: dict[int, int] = {}
    if isinstance(wp, dict) and isinstance(wp.get("combined"), dict):
        for key, value in wp["combined"].items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            if not isinstance(value, bool) and isinstance(value, int):
                combined[idx] = value
    for idx in range(len(row_codes)):
        got = combined.get(idx, 0)
        if got != expected.get(idx, 0):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"workpaper:-/combined[row {idx} ({row_codes[idx]})]",
                    f"combined carries {fmt(got)}; the cells and eliminations "
                    f"foot to {fmt(expected.get(idx, 0))} -- a combined column "
                    "maintained beside the grid rather than struck from it",
                )
            )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "the combined column foots"))
    return out


# --------------------------------------------------------------------------- #
# 18-21. Backup, links, twins
# --------------------------------------------------------------------------- #
_SEV_BAK = _sev("bak_backup_complete", Status.FAIL)


@check("bak_backup_complete")
def check_bak_backup_complete(ctx: Context) -> list[Finding]:
    """The backup tab carries every mapped account once, balances exact.

    The backup is the reviewer's landing spot: click a figure, find its
    account. A backup missing accounts -- or quoting different balances --
    sends every review down a hole.
    """
    rule = "bak_backup_complete"
    out: list[Finding] = []
    backup = ctx.one(DOC_BACKUP_TAB)
    with amount_guard(rule, out):
        owed = expected_backup(
            ctx.one(DOC_ENTITY_REGISTER), ctx.one(DOC_SOURCE_EXTRACT)
        )
        have: dict[str, int] = {}
        seen_twice: set[str] = set()
        if isinstance(backup, dict) and isinstance(backup.get("rows"), list):
            for row in backup["rows"]:
                if not isinstance(row, dict):
                    continue
                account = row.get("account")
                if not isinstance(account, str):
                    continue
                if account in have:
                    seen_twice.add(account)
                    continue
                have[account] = require_cents(
                    f"backup_tab[{account}]/balance_cents", row.get("balance_cents")
                )
        for account in sorted(seen_twice):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"backup_tab:-/{account}",
                    f"account {account!r} appears more than once in the backup",
                )
            )
        for account in sorted(set(owed) - set(have)):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"backup_tab:-/{account}",
                    f"mapped account {account!r} is missing from the backup tab "
                    "-- a figure with no backup row cannot be reviewed",
                )
            )
        for account in sorted(set(have) - set(owed)):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"backup_tab:-/{account}",
                    f"backup account {account!r} belongs to no mapped book",
                )
            )
        for account in sorted(set(have) & set(owed)):
            if have[account] != owed[account][1]:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        f"backup_tab:-/{account}",
                        f"backup carries {fmt(have[account])} for "
                        f"{account!r}; the extract carries "
                        f"{fmt(owed[account][1])}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "the backup tab is complete and ties exactly"
            )
        )
    return out


_SEV_TITLES = _sev("bak_titles_from_title_column", Status.FAIL)


@check("bak_titles_from_title_column")
def check_bak_titles_from_title_column(ctx: Context) -> list[Finding]:
    """Backup titles quote the source's title column, not its category column.

    The text twin of the wrong-value-column defect. A backup titled from the
    category column reads plausibly -- "Cash", "Equity" -- and reconciles to
    nothing a reviewer can look up in the ledger. Text columns are located by
    role for the same reason value columns are.
    """
    rule = "bak_titles_from_title_column"
    out: list[Finding] = []
    backup = ctx.one(DOC_BACKUP_TAB)
    source = ctx.one(DOC_SOURCE_EXTRACT)
    titles: dict[str, str] = {}
    categories: dict[str, str] = {}
    for book in books_by_code(source).values():
        titles.update(title_map(book))
        categories.update(category_map(book))
    if isinstance(backup, dict) and isinstance(backup.get("rows"), list):
        for row in backup["rows"]:
            if not isinstance(row, dict):
                continue
            account = row.get("account")
            got = row.get("title")
            if not isinstance(account, str) or account not in titles:
                continue
            if not isinstance(got, str) or got != titles[account]:
                hint = ""
                if isinstance(got, str) and got == categories.get(account):
                    hint = (
                        " -- this is the source's CATEGORY column, the text "
                        "neighbour of the title column: the harvest read text "
                        "by position, not by role"
                    )
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        f"backup_tab:-/{account}/title",
                        f"backup titles {account!r} as {got!r}; the source's "
                        f"title column says {titles[account]!r}{hint}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every backup title quotes the title column"
            )
        )
    return out


_SEV_LINKS = _sev("lnk_links_resolve", Status.FAIL)


@check("lnk_links_resolve")
def check_lnk_links_resolve(ctx: Context) -> list[Finding]:
    """Every nonzero cell is linked, every link resolves, every link agrees.

    The live-link contract: a reviewer clicks a figure and lands on the backup
    row that supports it. A nonzero cell with no link is a keyed number; a link
    to a missing account is a dead end; a link whose backup balance differs is
    worse than either, because it *looks* reviewed.
    """
    rule = "lnk_links_resolve"
    out: list[Finding] = []
    wp = ctx.one(DOC_WORKPAPER)
    backup = ctx.one(DOC_BACKUP_TAB)
    backup_balances: dict[str, int] = {}
    if isinstance(backup, dict) and isinstance(backup.get("rows"), list):
        for row in backup["rows"]:
            if isinstance(row, dict) and isinstance(row.get("account"), str):
                value = row.get("balance_cents")
                if not isinstance(value, bool) and isinstance(value, int):
                    backup_balances.setdefault(row["account"], value)
    for idx, row in enumerate(workpaper_rows(wp)):
        row_code = row.get("row_code", "?")
        for entity_id, cell in sorted(_cells_of(row).items()):
            with amount_guard(rule, out):
                value = _cell_value(rule, entity_id, idx, cell)
                link = cell.get("link")
                loc = f"workpaper:{entity_id}/row {idx} ({row_code})"
                if value != 0 and link is None:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            loc,
                            f"nonzero cell {fmt(value)} carries no link -- an "
                            "unlinked figure is a keyed number, not a "
                            "harvested one",
                        )
                    )
                elif isinstance(link, str):
                    if link not in backup_balances:
                        out.append(
                            Finding(
                                rule,
                                Status.FAIL,
                                loc,
                                f"link points at {link!r}, which the backup tab "
                                "does not carry -- a dead link fails exactly "
                                "when a reviewer follows it",
                            )
                        )
                    elif backup_balances[link] != value:
                        out.append(
                            Finding(
                                rule,
                                Status.FAIL,
                                loc,
                                f"cell carries {fmt(value)} but its backup row "
                                f"{link!r} carries "
                                f"{fmt(backup_balances[link])} -- a link that "
                                "disagrees with its cell looks reviewed and "
                                "is not",
                            )
                        )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every link resolves and agrees")
        )
    return out


_SEV_TWIN = _sev("twin_exports_match", Status.FAIL)


@check("twin_exports_match")
def check_twin_exports_match(ctx: Context) -> list[Finding]:
    """Both rendered formats of the workpaper carry identical values.

    The workpaper ships twice -- a legacy format for the reviewer's convention
    and a modern one for tooling. A repair applied to one and not the other
    leaves two truths in circulation, and the reviewer always finds the stale
    one.
    """
    rule = "twin_exports_match"
    out: list[Finding] = []
    twin = ctx.one(DOC_TWIN_EXPORT)
    actual = _actual_grid(ctx, rule, out)
    row_codes = _row_codes(ctx)
    values: dict[str, dict[int, int]] = {}
    if isinstance(twin, dict) and isinstance(twin.get("values"), dict):
        for entity_id, cells in twin["values"].items():
            if not isinstance(cells, dict):
                continue
            for key, value in cells.items():
                try:
                    idx = int(key)
                except (TypeError, ValueError):
                    continue
                if not isinstance(value, bool) and isinstance(value, int):
                    values.setdefault(str(entity_id), {})[idx] = value
    for entity_id in sorted(set(actual) | set(values)):
        act = actual.get(entity_id, {})
        tw = values.get(entity_id, {})
        for idx in sorted(set(act) | set(tw)):
            if act.get(idx, 0) != tw.get(idx, 0):
                code = row_codes[idx] if idx < len(row_codes) else "?"
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        f"twin_export:{entity_id}/row {idx} ({code})",
                        f"the twin carries {fmt(tw.get(idx, 0))} where the "
                        f"workpaper carries {fmt(act.get(idx, 0))} -- two "
                        "formats, two truths, and the reviewer always finds "
                        "the stale one",
                    )
                )
    if not out:
        out.append(Finding(rule, Status.PASS, "-", "both rendered twins agree"))
    return out


# --------------------------------------------------------------------------- #
# 22. Fees
# --------------------------------------------------------------------------- #
_SEV_FEE = _sev("fee_final_year_suppressed", Status.FAIL)


@check("fee_final_year_suppressed")
def check_fee_final_year_suppressed(ctx: Context) -> list[Finding]:
    """The fixed annual fee is owed by live entities and never by final-year ones.

    The jurisdiction's fixed fee attaches to the *coming* year, so an entity in
    its final year owes none -- charging it there hands money to a fiscal year
    the entity will not see. Continuing and first-year entities owe exactly the
    fixed fee, no more, no less.
    """
    rule = "fee_final_year_suppressed"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    fee = ctx.fixed_fee_cents
    for row in register_rows(register):
        entity_id = row.get("entity_id")
        status = row.get("status")
        loc = ctx.loc(register or {}, f"entities[{entity_id}]/fee_due_cents")
        with amount_guard(rule, out):
            due = require_cents(
                f"entities[{entity_id}]/fee_due_cents", row.get("fee_due_cents")
            )
            if status == STATUS_FINAL_YEAR and due != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        loc,
                        f"final-year entity {entity_id!r} shows a fee of "
                        f"{fmt(due)} -- the fixed fee attaches to the coming "
                        "year, which this entity will not see",
                    )
                )
            elif status in (STATUS_CONTINUING, STATUS_FIRST_YEAR) and due != fee:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        loc,
                        f"live entity {entity_id!r} shows a fee of {fmt(due)}; "
                        f"the fixed fee is {fmt(fee)}",
                    )
                )
            elif status == STATUS_EXCLUDED and due != 0:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        loc,
                        f"excluded entity {entity_id!r} shows a fee of "
                        f"{fmt(due)} -- an entity outside the group files "
                        "nothing here and owes nothing here",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "fees follow status exactly")
        )
    return out


# --------------------------------------------------------------------------- #
# 23-24. Review signals
# --------------------------------------------------------------------------- #
_SEV_DORMANT = _sev("dormant_entity_review", Status.FLAG)


@check("dormant_entity_review")
def check_dormant_entity_review(ctx: Context) -> list[Finding]:
    """A column that is genuinely all zero is held for human confirmation.

    Consistency is not the question here -- the zeros tie the extract exactly.
    The question is whether an empty book is *right*: a dormant entity is
    sometimes an entity whose activity landed in somebody else's book. The
    engine cannot decide that; it can only make sure a human does.
    """
    rule = "dormant_entity_review"
    out: list[Finding] = []
    expected = _expected_grid(ctx)
    actual = _actual_grid(ctx, rule, out)
    for entity_id in sorted(expected):
        exp_zero = all(v == 0 for v in expected[entity_id].values())
        act_zero = all(v == 0 for v in actual.get(entity_id, {}).values())
        if exp_zero and act_zero and expected[entity_id]:
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    f"workpaper:{entity_id}/column",
                    f"column {entity_id!r} is genuinely empty -- the book "
                    "carries no balances at all. Confirm the entity is dormant "
                    "rather than booked somewhere else",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "no dormant columns to confirm")
        )
    return out


_SEV_SHORT = _sev("reg_short_period_review", Status.FLAG)


@check("reg_short_period_review")
def check_reg_short_period_review(ctx: Context) -> list[Finding]:
    """A first-year entity registered well into the year implies a short period.

    Not an error -- the registration is inside the window -- but the preparer
    must be told the first period starts at registration, not at the fiscal
    start, or the first return will quietly cover months the entity did not
    exist.
    """
    rule = "reg_short_period_review"
    out: list[Finding] = []
    register = ctx.one(DOC_ENTITY_REGISTER)
    start = ctx.fiscal_start
    band = ctx.short_period_days
    for row in register_rows(register):
        if row.get("status") != STATUS_FIRST_YEAR:
            continue
        registered = parse_iso(row.get("registration_date"))
        if registered is None or start is None:
            continue  # scope_first_year_registered owns unreadable dates
        days_in = (registered - start).days
        if days_in > band:
            entity_id = row.get("entity_id")
            out.append(
                Finding(
                    rule,
                    Status.FLAG,
                    ctx.loc(register or {}, f"entities[{entity_id}]/registration_date"),
                    f"first-year entity {entity_id!r} registered {days_in} days "
                    f"into the fiscal year (band is {band}) -- its first period "
                    f"starts {registered}, not at the fiscal start, and the "
                    "preparer needs that date",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "no short first periods to note")
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one workpaper file."""
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
    """Analyze every ``.json`` workpaper file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of workpaper-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
