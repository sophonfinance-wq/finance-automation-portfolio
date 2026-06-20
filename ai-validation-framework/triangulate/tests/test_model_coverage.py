"""Coverage tests for the domain model (``triangulate.model``).

Covers the Severity / AuthoritySource enums, the immutable Finding, the
Workpaper digest/clone/ordering helpers, and the read-only-view separation-of-
duties backstop.
"""

from __future__ import annotations

import pytest

from triangulate.model import (
    AuthoritySource,
    Finding,
    ReadOnlyWorkpaperView,
    Severity,
    Workpaper,
    WorkpaperCell,
    WorkpaperMutationError,
)


# --------------------------------------------------------------------------- #
# Severity                                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name, expected",
    [
        ("low", Severity.LOW),
        ("Low", Severity.LOW),
        ("LOW", Severity.LOW),
        ("  medium  ", Severity.MEDIUM),
        ("High", Severity.HIGH),
        ("critical", Severity.CRITICAL),
    ],
)
def test_severity_from_name_case_and_whitespace_insensitive(name, expected):
    assert Severity.from_name(name) is expected


def test_severity_from_name_rejects_unknown():
    with pytest.raises(ValueError):
        Severity.from_name("urgent")


@pytest.mark.parametrize(
    "sev, label",
    [
        (Severity.LOW, "Low"),
        (Severity.MEDIUM, "Medium"),
        (Severity.HIGH, "High"),
        (Severity.CRITICAL, "Critical"),
    ],
)
def test_severity_label_is_title_case(sev, label):
    assert sev.label == label


def test_severity_integer_ordering():
    assert int(Severity.LOW) == 1
    assert int(Severity.CRITICAL) == 4
    assert Severity.CRITICAL > Severity.HIGH > Severity.MEDIUM > Severity.LOW


def test_severity_max_picks_highest():
    assert max([Severity.LOW, Severity.CRITICAL, Severity.MEDIUM]) is Severity.CRITICAL


# --------------------------------------------------------------------------- #
# AuthoritySource                                                              #
# --------------------------------------------------------------------------- #
def test_authority_hierarchy_ordering():
    # README hierarchy: signed prior year is most authoritative, AI lowest.
    assert (
        AuthoritySource.SIGNED_PRIOR_YEAR
        > AuthoritySource.MANAGEMENT_INSTRUCTION
        > AuthoritySource.MEETING_DECISION
        > AuthoritySource.CURRENT_YEAR_SOURCE
        > AuthoritySource.WORKBOOK_FORMULA
        > AuthoritySource.AI_ASSUMPTION
    )


@pytest.mark.parametrize(
    "src, label",
    [
        (AuthoritySource.AI_ASSUMPTION, "Ai Assumption"),
        (AuthoritySource.WORKBOOK_FORMULA, "Workbook Formula"),
        (AuthoritySource.CURRENT_YEAR_SOURCE, "Current Year Source"),
        (AuthoritySource.MEETING_DECISION, "Meeting Decision"),
        (AuthoritySource.MANAGEMENT_INSTRUCTION, "Management Instruction"),
        (AuthoritySource.SIGNED_PRIOR_YEAR, "Signed Prior Year"),
    ],
)
def test_authority_labels(src, label):
    assert src.label == label


def test_ai_assumption_is_lowest_authority():
    assert min(AuthoritySource) is AuthoritySource.AI_ASSUMPTION


# --------------------------------------------------------------------------- #
# Finding                                                                      #
# --------------------------------------------------------------------------- #
def test_finding_is_frozen():
    f = Finding("C", "B1", Severity.HIGH, "m", "r")
    with pytest.raises(Exception):
        f.code = "OTHER"  # type: ignore[misc]


def test_finding_default_authority_is_ai_assumption():
    f = Finding("C", "B1", Severity.HIGH, "m", "r")
    assert f.authority is AuthoritySource.AI_ASSUMPTION
    assert f.expected is None
    assert f.actual is None


def test_finding_to_dict_shape_and_labels():
    f = Finding(
        code="TIE_OUT_MISMATCH",
        cell_ref="B7",
        severity=Severity.CRITICAL,
        message="boom",
        raised_by="Reviewer:X",
        authority=AuthoritySource.WORKBOOK_FORMULA,
        expected=10.0,
        actual=9.0,
    )
    d = f.to_dict()
    assert d["code"] == "TIE_OUT_MISMATCH"
    assert d["cell_ref"] == "B7"
    assert d["severity"] == "Critical"  # label form, not the enum
    assert d["authority"] == "Workbook Formula"
    assert d["expected"] == 10.0
    assert d["actual"] == 9.0
    assert set(d) == {
        "code", "cell_ref", "severity", "message",
        "raised_by", "authority", "expected", "actual",
    }


# --------------------------------------------------------------------------- #
# WorkpaperCell                                                                #
# --------------------------------------------------------------------------- #
def test_cell_defaults():
    c = WorkpaperCell("B1", "Label")
    assert c.value is None
    assert c.formula is None
    assert c.source is AuthoritySource.WORKBOOK_FORMULA


def test_cell_to_dict_renders_source_label():
    c = WorkpaperCell("B1", "Lbl", 12.0, formula="=B2", source=AuthoritySource.AI_ASSUMPTION)
    d = c.to_dict()
    assert d == {
        "ref": "B1",
        "label": "Lbl",
        "value": 12.0,
        "formula": "=B2",
        "source": "Ai Assumption",
    }


# --------------------------------------------------------------------------- #
# Workpaper: ordering, get, digest, clone                                      #
# --------------------------------------------------------------------------- #
def _wp_with_cells():
    wp = Workpaper("ENG", "Ent", "FY24")
    wp.set_cell(WorkpaperCell("B10", "ten", 10.0))
    wp.set_cell(WorkpaperCell("B2", "two", 2.0))
    wp.set_cell(WorkpaperCell("B1", "one", 1.0))
    return wp


def test_ordered_cells_is_sorted_by_ref():
    wp = _wp_with_cells()
    assert [c.ref for c in wp.ordered_cells()] == ["B1", "B10", "B2"]


def test_get_returns_cell_or_none():
    wp = _wp_with_cells()
    assert wp.get("B1").label == "one"
    assert wp.get("ZZ99") is None


def test_set_cell_overwrites_same_ref():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B1", "first", 1.0))
    wp.set_cell(WorkpaperCell("B1", "second", 2.0))
    assert len(wp.cells) == 1
    assert wp.get("B1").label == "second"


def test_digest_is_stable_for_same_content():
    a = _wp_with_cells()
    b = _wp_with_cells()
    assert a.digest() == b.digest()


def test_digest_changes_when_a_value_changes():
    wp = _wp_with_cells()
    before = wp.digest()
    wp.get("B1").value = 999.0
    assert wp.digest() != before


def test_digest_changes_when_a_note_added():
    wp = _wp_with_cells()
    before = wp.digest()
    wp.notes.append("new note")
    assert wp.digest() != before


def test_digest_is_64_char_hex():
    wp = _wp_with_cells()
    digest = wp.digest()
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


def test_clone_is_deep_and_independent():
    wp = _wp_with_cells()
    clone = wp.clone()
    assert clone.digest() == wp.digest()
    clone.notes.append("only on clone")
    clone.get("B1").value = -1.0
    assert "only on clone" not in wp.notes
    assert wp.get("B1").value == 1.0
    assert clone.digest() != wp.digest()


def test_to_dict_round_trips_cells_and_notes():
    wp = _wp_with_cells()
    wp.notes.append("a note")
    d = wp.to_dict()
    assert d["engagement"] == "ENG"
    assert set(d["cells"]) == {"B1", "B2", "B10"}
    assert d["notes"] == ["a note"]


# --------------------------------------------------------------------------- #
# ReadOnlyWorkpaperView (separation-of-duties backstop)                        #
# --------------------------------------------------------------------------- #
def test_view_exposes_read_accessors():
    wp = _wp_with_cells()
    wp.notes.append("n1")
    view = wp.frozen_snapshot()
    assert isinstance(view, ReadOnlyWorkpaperView)
    assert view.engagement == "ENG"
    assert view.entity == "Ent"
    assert view.period == "FY24"
    assert view.notes == ["n1"]
    assert view.digest() == wp.digest()


def test_view_blocks_attribute_assignment():
    view = _wp_with_cells().frozen_snapshot()
    with pytest.raises(WorkpaperMutationError):
        view.period = "tampered"  # type: ignore[misc]


def test_view_notes_list_is_a_copy():
    wp = _wp_with_cells()
    wp.notes.append("orig")
    view = wp.frozen_snapshot()
    returned = view.notes
    returned.append("mutate the returned copy")
    # Mutating the returned list must not change the underlying workpaper.
    assert wp.notes == ["orig"]
    assert view.notes == ["orig"]


def test_view_get_returns_isolated_copies():
    wp = _wp_with_cells()
    view = wp.frozen_snapshot()
    cell = view.get("B1")
    cell.value = -12345.0
    assert wp.get("B1").value == 1.0
    assert wp.digest() == view.digest()


def test_view_get_missing_returns_none():
    view = _wp_with_cells().frozen_snapshot()
    assert view.get("NOPE") is None


def test_view_ordered_cells_are_copies():
    wp = _wp_with_cells()
    view = wp.frozen_snapshot()
    cells = view.ordered_cells()
    cells[0].value = -1.0
    assert wp.ordered_cells()[0].value != -1.0
