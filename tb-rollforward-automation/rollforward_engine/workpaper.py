"""
Roll-forward kernel shared by the controls and the generator.
=============================================================

Everything here is the arithmetic and mapping heart of the engine: how a book's
declared columns are located by **role** rather than position, how a dual-code
workpaper row collects its constituent codes through the chart-equivalence map,
and how the populated grid, the backup tab and the combined column are
re-derived from the extract. The generator builds its baseline through these
same functions, so a control and the data it audits cannot quietly disagree
about the derivation.

The population contract, stated once
------------------------------------
* A book's **balance column is found by its declared role** (:data:`COL_BALANCE`
  in the book's ``columns`` list), never by position. Books that also carry a
  :data:`COL_ACTIVITY` column are exactly why: activity sits beside balance, and
  a positional read populates movement instead of balances -- and still foots.
* Only rows in **code position** are trial-balance rows. Memo rows are
  side-schedule annotations; a memo balance populated into the grid double
  counts something a schedule already explains.
* A workpaper row may carry **several codes** (``"2001/1601"``): charts of
  accounts share the row. The cell owed there is the **sum** of every code the
  row collects, where each code also collects its **chart equivalents** (a row
  coded ``3999`` collects the book's ``2999`` when the map says they are the
  same account). Each book code is consumed by the **first** row that claims
  it, in row order, so a code can never be counted into two rows.
* A **duplicated row code** (the same code appearing on a later row again) owes
  **zero** on the later row -- the first instance consumed the code.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .model import (
    COL_ACTIVITY,
    COL_BALANCE,
    COL_CATEGORY,
    COL_TITLE,
    POS_CODE,
    POS_MEMO,
    STATUS_CONTINUING,
    STATUS_FIRST_YEAR,
)
from .money import require_cents

# --------------------------------------------------------------------------- #
# Row / code helpers
# --------------------------------------------------------------------------- #


def split_row_code(row_code: str) -> list[str]:
    """Split a workpaper row code into its constituent codes.

    ``"2001/1601"`` -> ``["2001", "1601"]``; a single-code row returns itself.
    Order is preserved: it is the order equivalents are consumed in.
    """
    return [part.strip() for part in str(row_code).split("/") if part.strip()]


def equivalence_map(chart_doc: dict[str, Any] | None) -> dict[str, str]:
    """Return ``{row_chart_code: book_code}`` from the chart-map document.

    The map is directional: the workpaper row carries the *canonical* code and
    the book carries the *equivalent*. A malformed entry is skipped -- the
    ``set_complete`` control owns structural complaints about the artifact.
    """
    out: dict[str, str] = {}
    if not isinstance(chart_doc, dict):
        return out
    entries = chart_doc.get("equivalences")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        canonical = entry.get("row_code")
        equivalent = entry.get("book_code")
        if isinstance(canonical, str) and isinstance(equivalent, str):
            out[canonical] = equivalent
    return out


def codes_collected(row_code: str, equiv: dict[str, str]) -> list[str]:
    """Every book code a workpaper row collects, in consumption order.

    The row's own codes come first, then each code's chart equivalent (if any),
    de-duplicated while preserving order.
    """
    own = split_row_code(row_code)
    out: list[str] = []
    for code in own:
        if code not in out:
            out.append(code)
        alias = equiv.get(code)
        if alias is not None and alias not in out:
            out.append(alias)
    return out


# --------------------------------------------------------------------------- #
# Book helpers
# --------------------------------------------------------------------------- #


def book_columns(book: dict[str, Any]) -> list[str]:
    """The declared column roles of a book table, in declared order."""
    cols = book.get("columns")
    if not isinstance(cols, list):
        return []
    return [c for c in cols if isinstance(c, str)]


def book_has_activity(book: dict[str, Any]) -> bool:
    """True when the book carries a monthly-activity column beside the balance."""
    return COL_ACTIVITY in book_columns(book)


def book_declares_balance(book: dict[str, Any]) -> bool:
    """True when the book declares a balance column at all."""
    return COL_BALANCE in book_columns(book)


def book_rows(book: dict[str, Any]) -> list[dict[str, Any]]:
    """All row dicts of a book table, in file order."""
    rows = book.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def code_rows(book: dict[str, Any]) -> list[dict[str, Any]]:
    """Only the rows in code position -- the actual trial-balance rows."""
    return [r for r in book_rows(book) if r.get("position") == POS_CODE]


def memo_rows(book: dict[str, Any]) -> list[dict[str, Any]]:
    """Only the memo rows -- side-schedule annotations, never populated."""
    return [r for r in book_rows(book) if r.get("position") == POS_MEMO]


def row_suffix(row: dict[str, Any]) -> str | None:
    """The account suffix of a book row (``"BWC-1206"`` -> ``"1206"``)."""
    code = row.get("account")
    if not isinstance(code, str) or "-" not in code:
        return None
    return code.rsplit("-", 1)[1]


def balance_map(book: dict[str, Any], *, field_prefix: str = "") -> dict[str, int]:
    """``{suffix: balance_cents}`` over the book's code rows.

    Reads the **balance** field because the role is declared; the activity
    figure is deliberately not a fallback.

    Raises:
        AmountInvalidError: If a balance is not integer cents.
    """
    out: dict[str, int] = {}
    for row in code_rows(book):
        suffix = row_suffix(row)
        if suffix is None:
            continue
        label = f"{field_prefix}{row.get('account', '?')}/balance_cents"
        out[suffix] = require_cents(label, row.get("balance_cents"))
    return out


def activity_map(book: dict[str, Any]) -> dict[str, int]:
    """``{suffix: activity_cents}`` over the book's code rows (may be empty)."""
    out: dict[str, int] = {}
    if not book_has_activity(book):
        return out
    for row in code_rows(book):
        suffix = row_suffix(row)
        value = row.get("activity_cents")
        if suffix is None or isinstance(value, bool) or not isinstance(value, int):
            continue
        out[suffix] = value
    return out


def title_map(book: dict[str, Any]) -> dict[str, str]:
    """``{account: title}`` from the book's **title** column, code rows only."""
    out: dict[str, str] = {}
    for row in code_rows(book):
        account = row.get("account")
        title = row.get(COL_TITLE)
        if isinstance(account, str) and isinstance(title, str):
            out[account] = title
    return out


def category_map(book: dict[str, Any]) -> dict[str, str]:
    """``{account: category}`` -- the neighbouring text column, for diagnostics."""
    out: dict[str, str] = {}
    for row in code_rows(book):
        account = row.get("account")
        category = row.get(COL_CATEGORY)
        if isinstance(account, str) and isinstance(category, str):
            out[account] = category
    return out


# --------------------------------------------------------------------------- #
# Register / workpaper helpers
# --------------------------------------------------------------------------- #


def register_rows(register: dict[str, Any] | None) -> list[dict[str, Any]]:
    """All entity rows of the register, in file order."""
    if not isinstance(register, dict):
        return []
    rows = register.get("entities")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def column_entities(register: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Register rows that are owed a workpaper column this year.

    Continuing and first-year entities carry columns; final-year and excluded
    entities do not.
    """
    return [
        r
        for r in register_rows(register)
        if r.get("status") in (STATUS_CONTINUING, STATUS_FIRST_YEAR)
    ]


def workpaper_columns(workpaper: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The workpaper's column declarations, in file order."""
    if not isinstance(workpaper, dict):
        return []
    cols = workpaper.get("columns")
    if not isinstance(cols, list):
        return []
    return [c for c in cols if isinstance(c, dict)]


def workpaper_rows(workpaper: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The workpaper's row declarations, in file order (duplicates preserved)."""
    if not isinstance(workpaper, dict):
        return []
    rows = workpaper.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def parse_iso(value: object) -> date | None:
    """Parse a strict ISO date, returning ``None`` on anything else."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Re-derivation
# --------------------------------------------------------------------------- #


def books_by_code(source: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """``{book_code: book_table}`` over the extract, first declaration wins."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(source, dict):
        return out
    books = source.get("books")
    if not isinstance(books, list):
        return out
    for book in books:
        if not isinstance(book, dict):
            continue
        code = book.get("book_code")
        if isinstance(code, str) and code not in out:
            out[code] = book
    return out


def expected_cells(
    register: dict[str, Any] | None,
    source: dict[str, Any] | None,
    chart_doc: dict[str, Any] | None,
    row_codes: list[str],
) -> dict[str, dict[int, int]]:
    """Re-derive the whole grid: ``{entity_id: {row_index: cents}}``.

    ``row_codes`` is the workpaper's row-code list **in row order, duplicates
    included** -- the index keys the result because a duplicated code owes zero
    on its later instances and a dict keyed by code could not express that.

    Every code a row collects (through :func:`codes_collected`) is consumed at
    most once per entity, in row order.
    """
    equiv = equivalence_map(chart_doc)
    books = books_by_code(source)
    grid: dict[str, dict[int, int]] = {}
    for entity in column_entities(register):
        entity_id = str(entity.get("entity_id", "?"))
        book = books.get(str(entity.get("book_code", "")))
        balances = balance_map(book, field_prefix=f"{entity_id}/") if book else {}
        consumed: set[str] = set()
        cells: dict[int, int] = {}
        for idx, row_code in enumerate(row_codes):
            value = 0
            for code in codes_collected(row_code, equiv):
                if code in consumed:
                    continue
                if code in balances:
                    value += balances[code]
                    consumed.add(code)
            cells[idx] = value
        grid[entity_id] = cells
    return grid


def expected_backup(
    register: dict[str, Any] | None, source: dict[str, Any] | None
) -> dict[str, tuple[str, int]]:
    """Re-derive the backup tab: ``{account: (title, balance_cents)}``.

    One row per code-position account of every **mapped** book (a book named by
    a column entity), titled from the book's title column. Unmapped books stay
    out: the backup documents the population, not the whole extract.
    """
    books = books_by_code(source)
    out: dict[str, tuple[str, int]] = {}
    for entity in column_entities(register):
        book = books.get(str(entity.get("book_code", "")))
        if book is None:
            continue
        titles = title_map(book)
        for row in code_rows(book):
            account = row.get("account")
            if not isinstance(account, str) or account in out:
                continue
            balance = row.get("balance_cents")
            if isinstance(balance, bool) or not isinstance(balance, int):
                continue
            out[account] = (titles.get(account, ""), balance)
    return out


def combined_expected(
    grid: dict[str, dict[int, int]], elim_rows: dict[int, int], row_count: int
) -> dict[int, int]:
    """Re-derive the combined column: entity cells plus eliminations, per row."""
    out: dict[int, int] = {}
    for idx in range(row_count):
        out[idx] = sum(cells.get(idx, 0) for cells in grid.values()) + elim_rows.get(
            idx, 0
        )
    return out
