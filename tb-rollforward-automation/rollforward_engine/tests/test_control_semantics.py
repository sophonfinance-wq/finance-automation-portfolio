"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment, and stays quiet when it should: a control that
fires on everything is as useless as one that fires on nothing.

The basis cases carry the most weight. A column populated from the monthly
activity column still foots to zero, so no footing check can see it -- the corpus
is built to put a real book on that edge, and the tests below assert both halves:
that the activity column genuinely nets to zero, and that the footing control
genuinely stays silent while the basis control speaks. The chart-equivalence and
duplicated-row cases are the same shape: a balance that disappears without
unbalancing anything.

Each case mutates a fresh baseline in memory and re-analyzes it, so every
assertion is one deliberate change against a known-clean file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rollforward_engine.engine import REGISTRY, SEVERITY, analyze_document
from rollforward_engine.generate import PORTFOLIOS, baseline
from rollforward_engine.model import (
    DOC_BACKUP_TAB,
    DOC_CHART_MAP,
    DOC_ENTITY_REGISTER,
    DOC_SOURCE_EXTRACT,
    DOC_TWIN_EXPORT,
    DOC_WORKPAPER,
    DocumentReport,
    Status,
)
from rollforward_engine.workpaper import (
    balance_map,
    book_has_activity,
    codes_collected,
    column_entities,
    split_row_code,
)


# --------------------------------------------------------------------------- #
# Helpers: mutate a fresh baseline in memory, then analyze it
# --------------------------------------------------------------------------- #
def _fresh() -> dict[str, Any]:
    return baseline(PORTFOLIOS[0])


def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any]:
    for doc in payload["documents"]:
        if doc.get("doc_type") == doc_type:
            return doc
    raise KeyError(doc_type)


def _entity(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    for row in _doc(payload, DOC_ENTITY_REGISTER)["entities"]:
        if row.get("entity_id") == entity_id:
            return row
    raise KeyError(entity_id)


def _book(payload: dict[str, Any], book_code: str) -> dict[str, Any]:
    for book in _doc(payload, DOC_SOURCE_EXTRACT)["books"]:
        if book.get("book_code") == book_code:
            return book
    raise KeyError(book_code)


def _analyze(payload: dict[str, Any], tmp_path: Path, name: str = "case") -> DocumentReport:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return analyze_document(path)


def _fired(report: DocumentReport, rule: str) -> list[str]:
    return [
        f.message for f in report.findings
        if f.rule == rule and f.status is not Status.PASS
    ]


# --------------------------------------------------------------------------- #
# The kernel: how a row collects its codes
# --------------------------------------------------------------------------- #
def test_a_single_code_row_collects_only_itself() -> None:
    assert split_row_code("0106") == ["0106"]


def test_a_dual_code_row_splits_on_the_slash() -> None:
    assert split_row_code("2001/1601") == ["2001", "1601"]


def test_a_row_collects_its_chart_equivalent_after_its_own_code() -> None:
    """Order matters: the row's own code is consumed before its equivalent."""
    assert codes_collected("3999", {"3999": "2999"}) == ["3999", "2999"]


def test_collection_never_repeats_a_code() -> None:
    """A code reachable twice is still consumed once, or a balance doubles."""
    assert codes_collected("2001/1601", {"2001": "1601"}) == ["2001", "1601"]


def test_an_unmapped_row_collects_nothing_extra() -> None:
    assert codes_collected("0106", {}) == ["0106"]


# --------------------------------------------------------------------------- #
# The signature defect: balance column vs activity column
# --------------------------------------------------------------------------- #
def test_only_the_parent_book_carries_an_activity_column() -> None:
    """The corpus needs exactly one book where the wrong column is available.

    If no book carried activity the signature defect could not be demonstrated;
    if every book did, the "read by role" lesson would be less pointed.
    """
    payload = _fresh()
    with_activity = [
        b["book_code"]
        for b in _doc(payload, DOC_SOURCE_EXTRACT)["books"]
        if book_has_activity(b)
    ]
    assert with_activity == ["BKP"]


def test_the_activity_column_also_foots_to_zero() -> None:
    """The premise of the whole engine, asserted rather than assumed.

    A footing check cannot distinguish balances from activity because activity
    nets to zero too. If this ever stopped being true the basis control would be
    redundant -- and this test would say so.
    """
    book = _book(_fresh(), "BKP")
    activity = [
        r["activity_cents"] for r in book["rows"]
        if r.get("position") == "code" and "activity_cents" in r
    ]
    assert activity, "the parent book lost its activity column"
    assert sum(activity) == 0


def test_the_two_columns_genuinely_differ() -> None:
    """So substituting one for the other is a real defect, not a no-op."""
    book = _book(_fresh(), "BKP")
    balances = balance_map(book)
    activity = {
        str(r["account"]).rsplit("-", 1)[1]: r["activity_cents"]
        for r in book["rows"]
        if r.get("position") == "code" and "activity_cents" in r
    }
    differing = [k for k in balances if activity.get(k, 0) != balances[k]]
    assert len(differing) >= 5


# --------------------------------------------------------------------------- #
# Mapping: exactness and both sweep directions
# --------------------------------------------------------------------------- #
def test_a_one_cent_cell_difference_is_reported(tmp_path: Path) -> None:
    """No tolerance band: a penny the extract does not support is an exception."""
    payload = _fresh()
    _doc(payload, DOC_WORKPAPER)["rows"][0]["cells"]["E-BRIGHTWATER"][
        "value_cents"
    ] += 1
    assert _fired(_analyze(payload, tmp_path), "map_values_exact")


def test_an_exact_cell_is_not_reported(tmp_path: Path) -> None:
    """The control stays quiet when every cell ties."""
    assert not _fired(_analyze(_fresh(), tmp_path), "map_values_exact")


def test_a_balance_collected_by_no_row_is_reported(tmp_path: Path) -> None:
    """The forward sweep: a balance that lands nowhere.

    Dropping the chart equivalence strands the legacy retained-earnings balance
    -- and both sides still foot, which is why enumeration is the only defence.
    """
    payload = _fresh()
    _doc(payload, DOC_CHART_MAP)["equivalences"] = []
    assert _fired(_analyze(payload, tmp_path), "map_forward_complete")


def test_a_zero_balance_collected_by_no_row_is_not_reported(tmp_path: Path) -> None:
    """Only *nonzero* orphans matter; a zero that lands nowhere loses nothing."""
    payload = _fresh()
    _book(payload, "BK1")["rows"].append(
        {
            "account": "BK1-8888",
            "account_title": "Suspense",
            "category": "Other",
            "balance_cents": 0,
            "position": "code",
        }
    )
    _doc(payload, DOC_BACKUP_TAB)["rows"].append(
        {"account": "BK1-8888", "title": "Suspense", "balance_cents": 0}
    )
    assert not _fired(_analyze(payload, tmp_path), "map_forward_complete")


def test_a_cell_the_book_does_not_support_is_reported(tmp_path: Path) -> None:
    """The reverse sweep: a phantom value is a number somebody authored."""
    payload = _fresh()
    _doc(payload, DOC_WORKPAPER)["rows"][10]["cells"]["E-BRIGHTWATER"][
        "value_cents"
    ] = 500_00
    assert _fired(_analyze(payload, tmp_path), "map_reverse_traces")


# --------------------------------------------------------------------------- #
# Dual codes and duplicated rows
# --------------------------------------------------------------------------- #
def test_the_dual_code_row_carries_each_chart_s_own_code() -> None:
    """One row, two charts: the parent books 1601, the projects book 2001."""
    wp = _doc(_fresh(), DOC_WORKPAPER)
    row = next(r for r in wp["rows"] if r["row_code"] == "2001/1601")
    assert row["cells"]["E-PARENT"]["value_cents"] == -96_750_00
    assert row["cells"]["E-BRIGHTWATER"]["value_cents"] == -44_200_00


def test_dropping_half_a_dual_code_row_is_reported(tmp_path: Path) -> None:
    payload = _fresh()
    wp = _doc(payload, DOC_WORKPAPER)
    row = next(r for r in wp["rows"] if r["row_code"] == "2001/1601")
    row["cells"]["E-BRIGHTWATER"]["value_cents"] = 0
    row["cells"]["E-BRIGHTWATER"].pop("link", None)
    assert _fired(_analyze(payload, tmp_path), "map_dual_codes_sum")


def test_an_equivalence_to_a_row_that_does_not_exist_is_reported(
    tmp_path: Path,
) -> None:
    """A map entry pointing at no row maps a balance to nowhere."""
    payload = _fresh()
    _doc(payload, DOC_CHART_MAP)["equivalences"].append(
        {"row_code": "4444", "book_code": "5555", "note": "points at no row"}
    )
    assert _fired(_analyze(payload, tmp_path), "map_dual_codes_sum")


def test_the_duplicated_row_code_is_zero_on_its_second_instance() -> None:
    """The first instance consumed the code; the second owes nothing."""
    rows = _doc(_fresh(), DOC_WORKPAPER)["rows"]
    threes = [r for r in rows if r["row_code"] == "3300"]
    assert len(threes) == 2, "the corpus lost its duplicated row code"
    assert threes[0]["cells"]["E-PARENT"]["value_cents"] == -18_000_00
    assert threes[1]["cells"]["E-PARENT"]["value_cents"] == 0


def test_populating_the_second_instance_is_reported(tmp_path: Path) -> None:
    payload = _fresh()
    rows = _doc(payload, DOC_WORKPAPER)["rows"]
    [r for r in rows if r["row_code"] == "3300"][1]["cells"]["E-PARENT"][
        "value_cents"
    ] = -18_000_00
    assert _fired(_analyze(payload, tmp_path), "map_duplicate_row_zero")


# --------------------------------------------------------------------------- #
# Scope: what gets a column
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "status,owed_column",
    [
        ("continuing", True),
        ("first_year", True),
        ("final_year", False),
        ("excluded", False),
    ],
)
def test_which_statuses_are_owed_a_column(status: str, owed_column: bool) -> None:
    """The roll-forward rule, stated as a table and checked against the kernel."""
    payload = _fresh()
    _doc(payload, DOC_ENTITY_REGISTER)["entities"].append(
        {
            "entity_id": "E-TESTCASE",
            "entity_name": "Test Case Holdings",
            "status": status,
            "book_code": "BK1",
            "fee_due_cents": 0,
            "registration_date": "2028-09-05",
        }
    )
    owed = {
        str(e["entity_id"])
        for e in column_entities(_doc(payload, DOC_ENTITY_REGISTER))
    }
    assert ("E-TESTCASE" in owed) is owed_column


def test_a_registered_entity_with_no_column_is_reported(tmp_path: Path) -> None:
    """A missing column is a filing that will quietly not happen."""
    payload = _fresh()
    wp = _doc(payload, DOC_WORKPAPER)
    wp["columns"] = [c for c in wp["columns"] if c["entity_id"] != "E-COPPERFIELD"]
    assert _fired(_analyze(payload, tmp_path), "scope_register_matches_columns")


def test_a_column_with_no_register_row_is_reported(tmp_path: Path) -> None:
    """Scope nobody signed off is still scope."""
    payload = _fresh()
    _doc(payload, DOC_WORKPAPER)["columns"].append(
        {"entity_id": "E-UNKNOWN", "label": "Unknown"}
    )
    assert _fired(_analyze(payload, tmp_path), "scope_register_matches_columns")


def test_a_rename_that_drops_the_entity_is_reported(tmp_path: Path) -> None:
    """Carrying a rename badly can lose the entity as easily as double it."""
    payload = _fresh()
    wp = _doc(payload, DOC_WORKPAPER)
    wp["columns"] = [c for c in wp["columns"] if c["entity_id"] != "E-COPPERFIELD"]
    register = _doc(payload, DOC_ENTITY_REGISTER)
    register["entities"] = [
        e for e in register["entities"] if e["entity_id"] != "E-COPPERFIELD"
    ]
    assert _fired(_analyze(payload, tmp_path), "scope_renamed_once")


def test_a_final_year_entity_keeps_no_column() -> None:
    """The clean corpus retires the final-year entity rather than carrying it."""
    columns = {
        c["entity_id"] for c in _doc(_fresh(), DOC_WORKPAPER)["columns"]
    }
    assert "E-LARKFIELD" not in columns


# --------------------------------------------------------------------------- #
# First-year registration, at the window edges
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "registered,should_fail",
    [
        ("2028-07-01", False),  # first day of the window
        ("2029-06-30", False),  # last day of the window
        ("2028-06-30", True),   # one day before
        ("2029-07-01", True),   # one day after
    ],
)
def test_registration_at_the_window_edges(
    registered: str, should_fail: bool, tmp_path: Path
) -> None:
    """Inclusive on both ends: the window is a closed interval."""
    payload = _fresh()
    _entity(payload, "E-ALDERPOINT")["registration_date"] = registered
    fired = _fired(_analyze(payload, tmp_path), "scope_first_year_registered")
    assert bool(fired) is should_fail


@pytest.mark.parametrize(
    "registered,should_flag",
    [
        ("2028-09-29", False),  # exactly 90 days in -- at the band, not past it
        ("2028-09-30", True),   # 91 days in
    ],
)
def test_short_period_band_edge(
    registered: str, should_flag: bool, tmp_path: Path
) -> None:
    """The review band is exclusive: *more than* the band, not equal to it."""
    payload = _fresh()
    _entity(payload, "E-ALDERPOINT")["registration_date"] = registered
    fired = _fired(_analyze(payload, tmp_path), "reg_short_period_review")
    assert bool(fired) is should_flag


def test_an_unreadable_registration_date_is_not_double_reported(
    tmp_path: Path,
) -> None:
    """One fact, one complaint.

    The scope control owns an unreadable date; the review signal stands down
    rather than adding a second finding about the same field.
    """
    payload = _fresh()
    _entity(payload, "E-ALDERPOINT")["registration_date"] = "not-a-date"
    report = _analyze(payload, tmp_path)
    assert _fired(report, "scope_first_year_registered")
    assert not _fired(report, "reg_short_period_review")


# --------------------------------------------------------------------------- #
# Footing, eliminations and the combined column
# --------------------------------------------------------------------------- #
def test_every_baseline_column_foots_to_zero() -> None:
    """The self-proving property of a trial balance, asserted on the corpus."""
    totals: dict[str, int] = {}
    for row in _doc(_fresh(), DOC_WORKPAPER)["rows"]:
        for entity_id, cell in row["cells"].items():
            totals[entity_id] = totals.get(entity_id, 0) + cell["value_cents"]
    for entity_id, net in totals.items():
        assert net == 0, f"{entity_id} foots to {net}"


def test_a_column_that_does_not_foot_is_reported(tmp_path: Path) -> None:
    payload = _fresh()
    _doc(payload, DOC_WORKPAPER)["rows"][0]["cells"]["E-BRIGHTWATER"][
        "value_cents"
    ] = 0
    assert _fired(_analyze(payload, tmp_path), "col_self_balance")


def test_a_column_outside_the_elimination_range_is_reported(tmp_path: Path) -> None:
    """The range that silently stops at last year's final column."""
    payload = _fresh()
    elim = _doc(payload, DOC_WORKPAPER)["eliminations"]
    elim["covered_entities"] = [
        e for e in elim["covered_entities"] if e != "E-ALDERPOINT"
    ]
    assert _fired(_analyze(payload, tmp_path), "elim_covers_all_columns")


def test_an_elimination_the_combined_column_ignores_is_reported(
    tmp_path: Path,
) -> None:
    """An elimination the combined column never absorbed did not happen."""
    payload = _fresh()
    _doc(payload, DOC_WORKPAPER)["eliminations"]["rows"] = {"0": -1_000_00}
    assert _fired(_analyze(payload, tmp_path), "combined_foots")


def test_the_combined_column_ties_when_the_elimination_is_carried(
    tmp_path: Path,
) -> None:
    """With the elimination carried through, the control is quiet again."""
    payload = _fresh()
    wp = _doc(payload, DOC_WORKPAPER)
    wp["eliminations"]["rows"] = {"0": -1_000_00}
    wp["combined"]["0"] = int(wp["combined"]["0"]) - 1_000_00
    assert not _fired(_analyze(payload, tmp_path), "combined_foots")


# --------------------------------------------------------------------------- #
# Backup, titles and links
# --------------------------------------------------------------------------- #
def test_every_baseline_backup_title_comes_from_the_title_column() -> None:
    """The clean corpus quotes titles, never categories."""
    payload = _fresh()
    titles: dict[str, str] = {}
    for book in _doc(payload, DOC_SOURCE_EXTRACT)["books"]:
        for row in book["rows"]:
            if row.get("position") == "code":
                titles[row["account"]] = row["account_title"]
    for row in _doc(payload, DOC_BACKUP_TAB)["rows"]:
        assert row["title"] == titles[row["account"]]


def test_a_title_taken_from_the_category_column_is_reported(tmp_path: Path) -> None:
    payload = _fresh()
    _doc(payload, DOC_BACKUP_TAB)["rows"][0]["title"] = "Cash"
    assert _fired(_analyze(payload, tmp_path), "bak_titles_from_title_column")


def test_the_backup_never_carries_a_memo_account() -> None:
    """Memo rows are annotations; harvesting one double counts a schedule."""
    accounts = {r["account"] for r in _doc(_fresh(), DOC_BACKUP_TAB)["rows"]}
    assert "BKP-9100" not in accounts


def test_a_harvested_memo_account_is_reported(tmp_path: Path) -> None:
    payload = _fresh()
    _doc(payload, DOC_BACKUP_TAB)["rows"].append(
        {
            "account": "BKP-9100",
            "title": "Memo - reserve rollforward",
            "balance_cents": 18_250_00,
        }
    )
    assert _fired(_analyze(payload, tmp_path), "src_code_rows_only")


def test_every_nonzero_baseline_cell_carries_a_link() -> None:
    """The live-link contract on the clean corpus."""
    for row in _doc(_fresh(), DOC_WORKPAPER)["rows"]:
        for entity_id, cell in row["cells"].items():
            if cell["value_cents"] != 0:
                assert "link" in cell, (
                    f"{entity_id} row {row['row_code']} has a value and no link"
                )


def test_a_link_that_disagrees_with_its_cell_is_reported(tmp_path: Path) -> None:
    """Worse than a dead link: this one looks reviewed."""
    payload = _fresh()
    _doc(payload, DOC_WORKPAPER)["rows"][0]["cells"]["E-PARENT"]["link"] = (
        "BKP-0126"  # a real account, wrong balance
    )
    assert _fired(_analyze(payload, tmp_path), "lnk_links_resolve")


def test_the_clean_corpus_resolves_every_link(tmp_path: Path) -> None:
    """Nothing to support means nothing to link, and everything else resolves."""
    assert not _fired(_analyze(_fresh(), tmp_path), "lnk_links_resolve")


def test_a_backup_balance_that_differs_from_the_extract_is_reported(
    tmp_path: Path,
) -> None:
    payload = _fresh()
    _doc(payload, DOC_BACKUP_TAB)["rows"][0]["balance_cents"] += 1
    assert _fired(_analyze(payload, tmp_path), "bak_backup_complete")


# --------------------------------------------------------------------------- #
# Fees, by status
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "entity_id,owed",
    [
        ("E-PARENT", 800_00),
        ("E-ALDERPOINT", 800_00),
        ("E-LARKFIELD", 0),
        ("E-MARLOWE", 0),
    ],
)
def test_fee_owed_follows_status(entity_id: str, owed: int) -> None:
    """Live entities owe the fixed fee; final-year and excluded ones owe nothing."""
    assert _entity(_fresh(), entity_id)["fee_due_cents"] == owed


def test_charging_a_final_year_entity_is_reported(tmp_path: Path) -> None:
    """The fee attaches to a year this entity will not see."""
    payload = _fresh()
    _entity(payload, "E-LARKFIELD")["fee_due_cents"] = 800_00
    assert _fired(_analyze(payload, tmp_path), "fee_final_year_suppressed")


def test_underpaying_a_live_entity_is_reported(tmp_path: Path) -> None:
    payload = _fresh()
    _entity(payload, "E-PARENT")["fee_due_cents"] = 400_00
    assert _fired(_analyze(payload, tmp_path), "fee_final_year_suppressed")


# --------------------------------------------------------------------------- #
# Twins
# --------------------------------------------------------------------------- #
def test_the_twin_matches_the_workpaper_on_the_baseline() -> None:
    payload = _fresh()
    twin = _doc(payload, DOC_TWIN_EXPORT)["values"]
    for idx, row in enumerate(_doc(payload, DOC_WORKPAPER)["rows"]):
        for entity_id, cell in row["cells"].items():
            assert twin[entity_id][str(idx)] == cell["value_cents"]


def test_a_repair_applied_to_one_twin_only_is_reported(tmp_path: Path) -> None:
    """Two formats, two truths -- and the reviewer always finds the stale one."""
    payload = _fresh()
    _doc(payload, DOC_WORKPAPER)["rows"][0]["cells"]["E-PARENT"][
        "value_cents"
    ] += 100
    assert _fired(_analyze(payload, tmp_path), "twin_exports_match")


# --------------------------------------------------------------------------- #
# Register integrity
# --------------------------------------------------------------------------- #
def test_a_column_entity_naming_no_book_is_reported(tmp_path: Path) -> None:
    """A column with no book cannot be populated, only invented."""
    payload = _fresh()
    _entity(payload, "E-BRIGHTWATER")["book_code"] = "BK-NONE"
    assert _fired(_analyze(payload, tmp_path), "reg_entities_valid")


def test_a_book_that_does_not_foot_is_reported(tmp_path: Path) -> None:
    """An unbalanced extract is incomplete, and nothing from it can be trusted."""
    payload = _fresh()
    _book(payload, "BK1")["rows"][0]["balance_cents"] += 500_00
    assert _fired(_analyze(payload, tmp_path), "src_books_self_balance")


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
#: The declared severity of every control, as a design decision rather than an
#: implementation detail. A control that changes rung has changed meaning.
DESIGN_SEVERITY: dict[str, Status] = {
    "set_complete": Status.FAIL,
    "reg_entities_valid": Status.FAIL,
    "src_code_rows_only": Status.FAIL,
    "src_books_self_balance": Status.FAIL,
    "src_balance_basis": Status.FAIL,
    "scope_final_year_removed": Status.FAIL,
    "scope_renamed_once": Status.FAIL,
    "scope_first_year_registered": Status.FAIL,
    "scope_register_matches_columns": Status.FAIL,
    "map_forward_complete": Status.FAIL,
    "map_reverse_traces": Status.FAIL,
    "map_values_exact": Status.FAIL,
    "map_dual_codes_sum": Status.FAIL,
    "map_duplicate_row_zero": Status.FAIL,
    "col_self_balance": Status.FAIL,
    "elim_covers_all_columns": Status.FAIL,
    "combined_foots": Status.FAIL,
    "bak_backup_complete": Status.FAIL,
    "bak_titles_from_title_column": Status.FAIL,
    "lnk_links_resolve": Status.FAIL,
    "twin_exports_match": Status.FAIL,
    "fee_final_year_suppressed": Status.FAIL,
    "dormant_entity_review": Status.FLAG,
    "reg_short_period_review": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGN_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    assert SEVERITY[rule_id] is DESIGN_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    """A new control must make a deliberate severity decision, not inherit one."""
    assert sorted(DESIGN_SEVERITY) == sorted(r for r, _f in REGISTRY)


@pytest.mark.parametrize("rule_id", [r for r, _f in REGISTRY])
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    """Rule ids are grouped by prefix so the report reads as sections."""
    prefixes = (
        "set_", "reg_", "src_", "scope_", "map_", "col_", "elim_",
        "combined_", "bak_", "lnk_", "twin_", "fee_", "dormant_",
    )
    assert rule_id.startswith(prefixes), f"{rule_id} belongs to no family"
