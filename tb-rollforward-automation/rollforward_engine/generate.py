"""
Fictional corpus generator for the trial-balance roll-forward engine.
=====================================================================

Builds one clean workpaper file plus one file per planted defect. The clean file
is constructed **through the same kernel the controls use** (:mod:`.workpaper`),
so the corpus cannot drift from the derivation the engine audits: the grid, the
backup tab, the combined column, the links and the twin are all re-derived here
rather than typed.

Each defect file starts from a fresh baseline and applies exactly one mutation,
so a defect file demonstrates exactly one control firing. Mutations are applied
**after** re-derivation, which is what makes them defects rather than a
differently-shaped truth.

Every name, code, date and balance here is invented. No real entity, project,
place or ledger appears anywhere in this package.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import (
    COL_ACTIVITY,
    COL_BALANCE,
    COL_CATEGORY,
    COL_TITLE,
    DOC_BACKUP_TAB,
    DOC_CHART_MAP,
    DOC_ENTITY_REGISTER,
    DOC_PRIOR_STRUCTURE,
    DOC_SOURCE_EXTRACT,
    DOC_TWIN_EXPORT,
    DOC_WORKPAPER,
    POS_CODE,
    POS_MEMO,
    STATUS_CONTINUING,
    STATUS_EXCLUDED,
    STATUS_FINAL_YEAR,
    STATUS_FIRST_YEAR,
)
from .workpaper import (
    books_by_code,
    codes_collected,
    column_entities,
    combined_expected,
    equivalence_map,
    expected_backup,
    expected_cells,
)

#: Fictional groups whose roll-forward cycles the corpus carries.
PORTFOLIOS: tuple[str, ...] = (
    "Rivermont Holdings",
    "Calderwood Group",
    "Westmere Partners",
    "Ashfield Holdings",
)

#: Fictional-future fiscal period.
PERIOD = "FY2029"
FISCAL_START = "2028-07-01"
FISCAL_END = "2029-06-30"
AS_OF = "2029-07-27"

#: The fixed annual filing fee, in cents.
FIXED_FEE_CENTS = 80000


def d(dollars: float) -> int:
    """Dollars -> integer cents, for readable literals below."""
    return int(round(dollars * 100))


# --------------------------------------------------------------------------- #
# The workpaper row list -- the structure carried forward each year
# --------------------------------------------------------------------------- #
#: ``(row_code, label)`` in row order. ``2001/1601`` is the dual-chart row; the
#: 3300 code appears twice, which is the duplicated-row-code case; 3999 is the
#: legacy retained-earnings code the chart map equates to 2999.
ROWS: tuple[tuple[str, str], ...] = (
    ("0106", "Cash - operating"),
    ("0126", "Cash - reserve"),
    ("1206", "Investment in project"),
    ("1222", "Investment in joint venture"),
    ("2001/1601", "Accounts payable"),
    ("2936", "Equity - parent"),
    ("2973", "Distributions - parent"),
    ("3999", "Retained earnings - beginning"),
    ("3300", "Management fees"),
    ("3300", "Marketing fees"),
    ("7829", "Permits and fees"),
    ("7901", "Filing fee expense"),
)

#: The chart equivalence: the workpaper's legacy row code and the book's code.
CHART_EQUIVALENCES: tuple[tuple[str, str], ...] = (("3999", "2999"),)


# --------------------------------------------------------------------------- #
# Books
# --------------------------------------------------------------------------- #
def _row(
    account: str,
    title: str,
    category: str,
    balance: int,
    *,
    position: str = POS_CODE,
    activity: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "account": account,
        COL_TITLE: title,
        COL_CATEGORY: category,
        "balance_cents": balance,
        "position": position,
    }
    if activity is not None:
        row["activity_cents"] = activity
    return row


def _parent_book() -> dict[str, Any]:
    """The parent book -- the one that also carries a monthly-activity column.

    This is the book whose extra column makes a positional harvest read movement
    instead of balances, so the corpus can demonstrate that defect honestly.
    """
    return {
        "book_code": "BKP",
        "book_name": "Parent book",
        "columns": [COL_TITLE, COL_CATEGORY, COL_ACTIVITY, COL_BALANCE],
        "rows": [
            _row("BKP-0106", "Cash - operating", "Cash", d(41_500.00), activity=d(2_100.00)),
            _row("BKP-0126", "Cash - reserve", "Cash", d(18_250.00), activity=d(900.00)),
            _row("BKP-1206", "Investment in project", "Investments", d(2_450_000.00), activity=d(15_000.00)),
            _row("BKP-1222", "Investment in joint venture", "Investments", d(610_000.00), activity=d(-4_000.00)),
            _row("BKP-1601", "Accounts payable", "Payables", d(-96_750.00), activity=d(-3_100.00)),
            # The month's movement is funded by a capital contribution, so the
            # activity column nets to zero exactly the way the balance column
            # does -- which is precisely why a footing check cannot tell them
            # apart, and why ``src_balance_basis`` exists.
            _row("BKP-2936", "Equity - parent", "Equity", d(-3_180_000.00), activity=d(-23_600.00)),
            _row("BKP-2973", "Distributions - parent", "Equity", d(240_000.00), activity=d(11_000.00)),
            _row("BKP-2999", "Retained earnings - beginning", "Equity", d(-96_500.00), activity=d(0.00)),
            _row("BKP-3300", "Management fees", "Income", d(-18_000.00), activity=d(-1_500.00)),
            _row("BKP-7829", "Permits and fees", "Expense", d(29_700.00), activity=d(2_400.00)),
            _row("BKP-7901", "Filing fee expense", "Expense", d(1_800.00), activity=d(800.00)),
            # A memo row: a side-schedule annotation that must never be harvested.
            _row("BKP-9100", "Memo - reserve rollforward", "Memo", d(18_250.00), position=POS_MEMO),
        ],
    }


def _project_book(
    code: str, name: str, cash: int, investment: int, payable: int, equity_note: int
) -> dict[str, Any]:
    """A project book: balance column only, no activity column."""
    retained = -(cash + investment + payable + equity_note)
    return {
        "book_code": code,
        "book_name": name,
        "columns": [COL_TITLE, COL_CATEGORY, COL_BALANCE],
        "rows": [
            _row(f"{code}-0106", "Cash - operating", "Cash", cash),
            _row(f"{code}-1206", "Investment in project", "Investments", investment),
            _row(f"{code}-2001", "Accounts payable", "Payables", payable),
            _row(f"{code}-2936", "Equity - parent", "Equity", equity_note),
            _row(f"{code}-2999", "Retained earnings - beginning", "Equity", retained),
        ],
    }


def _dormant_book() -> dict[str, Any]:
    """A genuinely empty book -- every balance zero, and it still foots."""
    return {
        "book_code": "BKD",
        "book_name": "Dormant book",
        "columns": [COL_TITLE, COL_CATEGORY, COL_BALANCE],
        "rows": [
            _row("BKD-0106", "Cash - operating", "Cash", 0),
            _row("BKD-2936", "Equity - parent", "Equity", 0),
            _row("BKD-2999", "Retained earnings - beginning", "Equity", 0),
        ],
    }


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload["documents"]:
        if doc.get("doc_type") == doc_type:
            return doc
    return None


def _require(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    doc = _doc(payload, doc_type)
    if doc is None:
        raise KeyError(f"baseline is missing {doc_type}")
    return doc


def _entity(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    for row in _require(payload, DOC_ENTITY_REGISTER)["entities"]:
        if row.get("entity_id") == entity_id:
            return row
    raise KeyError(entity_id)


def _wp_row(payload: dict[str, Any], index: int) -> dict[str, Any]:
    return _require(payload, DOC_WORKPAPER)["rows"][index]


def _book(payload: dict[str, Any], book_code: str) -> dict[str, Any]:
    for book in _require(payload, DOC_SOURCE_EXTRACT)["books"]:
        if book.get("book_code") == book_code:
            return book
    raise KeyError(book_code)


def rederive(payload: dict[str, Any]) -> None:
    """Rebuild the grid, links, backup, combined and twin from the artifacts.

    Called once when the baseline is assembled. Every planted defect mutates the
    payload *after* this, so a defect is a real divergence from the derivation
    rather than a different starting point.
    """
    register = _doc(payload, DOC_ENTITY_REGISTER)
    source = _doc(payload, DOC_SOURCE_EXTRACT)
    chart = _doc(payload, DOC_CHART_MAP)
    workpaper = _require(payload, DOC_WORKPAPER)
    row_codes = [str(r["row_code"]) for r in workpaper["rows"]]
    equiv = equivalence_map(chart)
    books = books_by_code(source)

    grid = expected_cells(register, source, chart, row_codes)

    # Cells + links. A cell's link names the backup row that supports it: the
    # first code the row actually collected in that entity's book.
    for idx, row in enumerate(workpaper["rows"]):
        cells: dict[str, Any] = {}
        for entity in column_entities(register):
            entity_id = str(entity["entity_id"])
            book = books.get(str(entity.get("book_code", "")))
            value = grid.get(entity_id, {}).get(idx, 0)
            cell: dict[str, Any] = {"value_cents": value}
            if value != 0 and book is not None:
                accounts = {
                    str(r.get("account", "")).rsplit("-", 1)[-1]: str(r.get("account"))
                    for r in book["rows"]
                    if r.get("position") == POS_CODE
                }
                consumed_before: set[str] = set()
                for prev_idx in range(idx):
                    for code in codes_collected(row_codes[prev_idx], equiv):
                        if code in accounts:
                            consumed_before.add(code)
                for code in codes_collected(row_codes[idx], equiv):
                    if code in accounts and code not in consumed_before:
                        cell["link"] = accounts[code]
                        break
            cells[entity_id] = cell
        row["cells"] = cells

    # Eliminations cover every column and carry no amounts in the clean file.
    workpaper["eliminations"] = {
        "covered_entities": [
            str(e["entity_id"]) for e in column_entities(register)
        ],
        "rows": {},
    }
    workpaper["combined"] = {
        str(k): v
        for k, v in combined_expected(grid, {}, len(row_codes)).items()
    }

    backup = _require(payload, DOC_BACKUP_TAB)
    backup["rows"] = [
        {"account": account, "title": title, "balance_cents": balance}
        for account, (title, balance) in sorted(expected_backup(register, source).items())
    ]

    twin = _require(payload, DOC_TWIN_EXPORT)
    twin["values"] = {
        entity_id: {str(idx): value for idx, value in sorted(cells.items())}
        for entity_id, cells in sorted(grid.items())
    }


def baseline(portfolio: str) -> dict[str, Any]:
    """Build one clean workpaper file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "fiscal_year_start": FISCAL_START,
        "fiscal_year_end": FISCAL_END,
        "fixed_fee_cents": FIXED_FEE_CENTS,
        "short_period_days": 90,
        "documents": [
            {
                "doc_type": DOC_ENTITY_REGISTER,
                "document_id": "REG-2029",
                "entities": [
                    {
                        "entity_id": "E-PARENT",
                        "entity_name": "Rivermont Capital",
                        "status": STATUS_CONTINUING,
                        "book_code": "BKP",
                        "fee_due_cents": FIXED_FEE_CENTS,
                    },
                    {
                        "entity_id": "E-BRIGHTWATER",
                        "entity_name": "Brightwater Commons Investor",
                        "status": STATUS_CONTINUING,
                        "book_code": "BK1",
                        "fee_due_cents": FIXED_FEE_CENTS,
                    },
                    {
                        "entity_id": "E-COPPERFIELD",
                        "entity_name": "Copperfield Yards Investor",
                        "status": STATUS_CONTINUING,
                        "book_code": "BK2",
                        "fee_due_cents": FIXED_FEE_CENTS,
                    },
                    {
                        "entity_id": "E-ALDERPOINT",
                        "entity_name": "Alderpoint Terraces Owner",
                        "status": STATUS_FIRST_YEAR,
                        "registration_date": "2028-09-05",
                        "book_code": "BK3",
                        "fee_due_cents": FIXED_FEE_CENTS,
                    },
                    {
                        "entity_id": "E-LARKFIELD",
                        "entity_name": "Larkfield Row Investor",
                        "status": STATUS_FINAL_YEAR,
                        "book_code": "BK9",
                        "fee_due_cents": 0,
                    },
                    {
                        "entity_id": "E-MARLOWE",
                        "entity_name": "Marlowe Court Venture",
                        "status": STATUS_EXCLUDED,
                        "book_code": "BK8",
                        "fee_due_cents": 0,
                    },
                ],
            },
            {
                "doc_type": DOC_PRIOR_STRUCTURE,
                "document_id": "PRIOR-2028",
                "columns": [
                    "E-PARENT",
                    "E-BRIGHTWATER",
                    "E-COPPERFIELD",
                    "E-LARKFIELD",
                    "E-HAWTHORNE",
                ],
                "renames": [
                    {
                        "old_entity_id": "E-HAWTHORNE",
                        "new_entity_id": "E-COPPERFIELD",
                        "note": "Hawthorne Bend Investor renamed Copperfield Yards Investor",
                    }
                ],
            },
            {
                "doc_type": DOC_SOURCE_EXTRACT,
                "document_id": "TB-2029-06-30",
                "books": [
                    _parent_book(),
                    _project_book(
                        "BK1",
                        "Brightwater Commons book",
                        d(96_400.00),
                        d(1_820_000.00),
                        d(-44_200.00),
                        d(-1_640_000.00),
                    ),
                    _project_book(
                        "BK2",
                        "Copperfield Yards book",
                        d(58_900.00),
                        d(2_310_000.00),
                        d(-71_500.00),
                        d(-2_010_000.00),
                    ),
                    _project_book(
                        "BK3",
                        "Alderpoint Terraces book",
                        d(22_750.00),
                        d(940_000.00),
                        d(-16_800.00),
                        d(-880_000.00),
                    ),
                    _dormant_book(),
                ],
            },
            {
                "doc_type": DOC_CHART_MAP,
                "document_id": "MAP-2029",
                "equivalences": [
                    {
                        "row_code": row_code,
                        "book_code": book_code,
                        "note": "legacy chart code equals current chart code",
                    }
                    for row_code, book_code in CHART_EQUIVALENCES
                ],
            },
            {
                "doc_type": DOC_WORKPAPER,
                "document_id": "WP-2029",
                "columns": [
                    {"entity_id": "E-PARENT", "label": "Rivermont Capital"},
                    {"entity_id": "E-BRIGHTWATER", "label": "Brightwater Commons"},
                    {"entity_id": "E-COPPERFIELD", "label": "Copperfield Yards"},
                    {"entity_id": "E-ALDERPOINT", "label": "Alderpoint Terraces"},
                ],
                "rows": [
                    {"row_code": code, "label": label} for code, label in ROWS
                ],
                "eliminations": {"covered_entities": [], "rows": {}},
                "combined": {},
            },
            {
                "doc_type": DOC_BACKUP_TAB,
                "document_id": "BAK-2029",
                "source_note": (
                    "Flat backup of the year-end trial-balance extract; every "
                    "workpaper figure links here"
                ),
                "rows": [],
            },
            {
                "doc_type": DOC_TWIN_EXPORT,
                "document_id": "TWIN-2029",
                "format": "legacy",
                "values": {},
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per control
# --------------------------------------------------------------------------- #
def _missing_artifact(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        d_ for d_ in payload["documents"] if d_.get("doc_type") != DOC_BACKUP_TAB
    ]


def _duplicate_entity_id(payload: dict[str, Any]) -> None:
    register = _require(payload, DOC_ENTITY_REGISTER)
    twin = dict(register["entities"][1])
    register["entities"].append(twin)


def _unknown_entity_status(payload: dict[str, Any]) -> None:
    _entity(payload, "E-BRIGHTWATER")["status"] = "pending_review"


def _memo_row_harvested(payload: dict[str, Any]) -> None:
    backup = _require(payload, DOC_BACKUP_TAB)
    backup["rows"].append(
        {
            "account": "BKP-9100",
            "title": "Memo - reserve rollforward",
            "balance_cents": d(18_250.00),
        }
    )


def _book_out_of_balance(payload: dict[str, Any]) -> None:
    book = _book(payload, "BK1")
    book["rows"][0]["balance_cents"] += d(500.00)


def _activity_column_used(payload: dict[str, Any]) -> None:
    """Populate the parent column from the activity column, the signature defect."""
    register = _doc(payload, DOC_ENTITY_REGISTER)
    source = _doc(payload, DOC_SOURCE_EXTRACT)
    chart = _doc(payload, DOC_CHART_MAP)
    workpaper = _require(payload, DOC_WORKPAPER)
    row_codes = [str(r["row_code"]) for r in workpaper["rows"]]
    equiv = equivalence_map(chart)
    book = books_by_code(source)["BKP"]
    activity = {
        str(r["account"]).rsplit("-", 1)[1]: r["activity_cents"]
        for r in book["rows"]
        if r.get("position") == POS_CODE and "activity_cents" in r
    }
    consumed: set[str] = set()
    for idx, row_code in enumerate(row_codes):
        value = 0
        for code in codes_collected(row_code, equiv):
            if code in consumed:
                continue
            if code in activity:
                value += activity[code]
                consumed.add(code)
        workpaper["rows"][idx]["cells"]["E-PARENT"]["value_cents"] = value
        if value == 0:
            workpaper["rows"][idx]["cells"]["E-PARENT"].pop("link", None)
    # The combined column and the twin were rebuilt from the same wrong figures,
    # exactly as they would be in a real workpaper.
    grid = {
        entity_id: {
            idx: workpaper["rows"][idx]["cells"][entity_id]["value_cents"]
            for idx in range(len(row_codes))
        }
        for entity_id in workpaper["rows"][0]["cells"]
    }
    workpaper["combined"] = {
        str(k): v for k, v in combined_expected(grid, {}, len(row_codes)).items()
    }
    _require(payload, DOC_TWIN_EXPORT)["values"] = {
        entity_id: {str(idx): value for idx, value in sorted(cells.items())}
        for entity_id, cells in sorted(grid.items())
    }


def _final_year_column_kept(payload: dict[str, Any]) -> None:
    workpaper = _require(payload, DOC_WORKPAPER)
    workpaper["columns"].append(
        {"entity_id": "E-LARKFIELD", "label": "Larkfield Row"}
    )


def _rename_double_counted(payload: dict[str, Any]) -> None:
    workpaper = _require(payload, DOC_WORKPAPER)
    workpaper["columns"].append({"entity_id": "E-HAWTHORNE", "label": "Hawthorne Bend"})


def _first_year_no_registration(payload: dict[str, Any]) -> None:
    _entity(payload, "E-ALDERPOINT").pop("registration_date", None)


def _column_not_in_register(payload: dict[str, Any]) -> None:
    workpaper = _require(payload, DOC_WORKPAPER)
    workpaper["columns"].append({"entity_id": "E-THORNBURY", "label": "Thornbury Mews"})


def _balance_lands_nowhere(payload: dict[str, Any]) -> None:
    """Drop the chart equivalence so the legacy retained-earnings code strands."""
    _require(payload, DOC_CHART_MAP)["equivalences"] = []


def _phantom_cell(payload: dict[str, Any]) -> None:
    row = _wp_row(payload, 10)  # permits and fees -- project books carry none
    row["cells"]["E-BRIGHTWATER"]["value_cents"] = d(3_400.00)
    row["cells"]["E-BRIGHTWATER"]["link"] = "BK1-0106"


def _cell_off_extract(payload: dict[str, Any]) -> None:
    row = _wp_row(payload, 0)
    row["cells"]["E-COPPERFIELD"]["value_cents"] += d(1_000.00)


def _dual_code_half_dropped(payload: dict[str, Any]) -> None:
    """The dual-chart payable row carries only the parent's half."""
    row = _wp_row(payload, 4)
    row["cells"]["E-BRIGHTWATER"]["value_cents"] = 0
    row["cells"]["E-BRIGHTWATER"].pop("link", None)


def _duplicate_row_populated(payload: dict[str, Any]) -> None:
    row = _wp_row(payload, 9)  # the second 3300 row
    row["cells"]["E-PARENT"]["value_cents"] = d(-18_000.00)
    row["cells"]["E-PARENT"]["link"] = "BKP-3300"


def _column_does_not_foot(payload: dict[str, Any]) -> None:
    """A cell dropped to zero: the column no longer foots, nothing else moves."""
    row = _wp_row(payload, 2)
    row["cells"]["E-ALDERPOINT"]["value_cents"] = 0
    row["cells"]["E-ALDERPOINT"].pop("link", None)


def _elimination_range_short(payload: dict[str, Any]) -> None:
    elim = _require(payload, DOC_WORKPAPER)["eliminations"]
    elim["covered_entities"] = [
        e for e in elim["covered_entities"] if e != "E-ALDERPOINT"
    ]


def _combined_maintained_by_hand(payload: dict[str, Any]) -> None:
    combined = _require(payload, DOC_WORKPAPER)["combined"]
    combined["0"] = int(combined.get("0", 0)) + d(250.00)


def _backup_row_missing(payload: dict[str, Any]) -> None:
    backup = _require(payload, DOC_BACKUP_TAB)
    backup["rows"] = [r for r in backup["rows"] if r.get("account") != "BK2-1206"]


def _backup_title_from_category(payload: dict[str, Any]) -> None:
    """Title the backup from the source's category column, not its title column."""
    source = _doc(payload, DOC_SOURCE_EXTRACT)
    categories: dict[str, str] = {}
    for book in books_by_code(source).values():
        for row in book["rows"]:
            if row.get("position") == POS_CODE:
                categories[str(row["account"])] = str(row[COL_CATEGORY])
    for row in _require(payload, DOC_BACKUP_TAB)["rows"]:
        account = row.get("account")
        if account in categories:
            row["title"] = categories[account]


def _link_dangles(payload: dict[str, Any]) -> None:
    _wp_row(payload, 0)["cells"]["E-PARENT"]["link"] = "BKP-0000"


def _twin_drifts(payload: dict[str, Any]) -> None:
    twin = _require(payload, DOC_TWIN_EXPORT)
    twin["values"]["E-BRIGHTWATER"]["0"] = (
        int(twin["values"]["E-BRIGHTWATER"]["0"]) + d(75.00)
    )


def _final_year_fee_charged(payload: dict[str, Any]) -> None:
    _entity(payload, "E-LARKFIELD")["fee_due_cents"] = FIXED_FEE_CENTS


def _short_first_period(payload: dict[str, Any]) -> None:
    _entity(payload, "E-ALDERPOINT")["registration_date"] = "2029-04-02"


def _dormant_column_present(payload: dict[str, Any]) -> None:
    """Admit an entity whose book is genuinely empty.

    Every consistency control holds -- the zeros tie the extract exactly -- so
    only the review signal fires, which is the point: the engine cannot decide
    whether a dormant entity is right, only make sure a human confirms it.
    """
    _require(payload, DOC_ENTITY_REGISTER)["entities"].append(
        {
            "entity_id": "E-DUNMORE",
            "entity_name": "Dunmore Flats Development",
            "status": STATUS_CONTINUING,
            "book_code": "BKD",
            "fee_due_cents": FIXED_FEE_CENTS,
        }
    )
    workpaper = _require(payload, DOC_WORKPAPER)
    workpaper["columns"].append({"entity_id": "E-DUNMORE", "label": "Dunmore Flats"})
    # Admit it properly: the column is populated, linked, backed up and carried
    # into both twins exactly as any other. Every consistency control therefore
    # holds, and the only thing left to say about the entity is the judgement
    # the engine cannot make.
    rederive(payload)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _wp_row(payload, 1)
    cell = row["cells"]["E-PARENT"]
    cell["value_cents"] = float(cell["value_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_entity_id": ("reg_entities_valid", _duplicate_entity_id),
    "unknown_entity_status": ("reg_entities_valid", _unknown_entity_status),
    "memo_row_harvested": ("src_code_rows_only", _memo_row_harvested),
    "book_out_of_balance": ("src_books_self_balance", _book_out_of_balance),
    "activity_column_used": ("src_balance_basis", _activity_column_used),
    "final_year_column_kept": ("scope_final_year_removed", _final_year_column_kept),
    "rename_double_counted": ("scope_renamed_once", _rename_double_counted),
    "first_year_no_registration": (
        "scope_first_year_registered",
        _first_year_no_registration,
    ),
    "column_not_in_register": (
        "scope_register_matches_columns",
        _column_not_in_register,
    ),
    "balance_lands_nowhere": ("map_forward_complete", _balance_lands_nowhere),
    "phantom_cell": ("map_reverse_traces", _phantom_cell),
    "cell_off_extract": ("map_values_exact", _cell_off_extract),
    "dual_code_half_dropped": ("map_dual_codes_sum", _dual_code_half_dropped),
    "duplicate_row_populated": ("map_duplicate_row_zero", _duplicate_row_populated),
    "column_does_not_foot": ("col_self_balance", _column_does_not_foot),
    "elimination_range_short": ("elim_covers_all_columns", _elimination_range_short),
    "combined_maintained_by_hand": ("combined_foots", _combined_maintained_by_hand),
    "backup_row_missing": ("bak_backup_complete", _backup_row_missing),
    "backup_title_from_category": (
        "bak_titles_from_title_column",
        _backup_title_from_category,
    ),
    "link_dangles": ("lnk_links_resolve", _link_dangles),
    "twin_drifts": ("twin_exports_match", _twin_drifts),
    "final_year_fee_charged": ("fee_final_year_suppressed", _final_year_fee_charged),
    "short_first_period": ("reg_short_period_review", _short_first_period),
    "dormant_column_present": ("dormant_entity_review", _dormant_column_present),
    "amount_not_integer": ("map_values_exact", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PORTFOLIOS[0])
    clean["file_id"] = f"clean__{PORTFOLIOS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        portfolio = PORTFOLIOS[(i + 1) % len(PORTFOLIOS)]
        f = baseline(portfolio)
        f["file_id"] = f"{name}__{portfolio.replace(' ', '_')}"
        f["planted_defect"] = name
        mutate(f)
        files.append(f)

    for f in files:
        path = folder / f"{f['file_id']}.json"
        path.write_text(
            json.dumps(f, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
