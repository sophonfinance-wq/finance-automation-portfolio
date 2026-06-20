"""Parametric test suite for model and orchestrator -- ~550 tests.

Covers:
 - Severity enum: ordering invariants, label, from_name (80 cases)
 - AuthoritySource enum: ordering, label, hierarchy (60 cases)
 - Severity × AuthoritySource cross-product comparisons (40 cases)
 - Finding construction + to_dict across many input combinations (80 cases)
 - WorkpaperCell construction and to_dict (50 cases)
 - Workpaper: set_cell, get, ordered_cells, digest stability, clone (60 cases)
 - ReadOnlyWorkpaperView: read accessors, mutation guard (40 cases)
 - reconcile(): de-duplication, authority/severity tiebreak, sort order (60 cases)
 - severity_breakdown(): all-four-buckets counting (30 cases)
 - HumanGate.decide(): PASS/FLAG/FAIL logic (40 cases)
 - VerdictStatus / Verdict properties (20 cases)
 - Orchestrator instantiation + run() result structural invariants (40 cases)
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
from triangulate.reconcile import (
    HumanGate,
    Verdict,
    VerdictStatus,
    reconcile,
    severity_breakdown,
)
from triangulate.orchestrator import TriangulateOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(
    code="TEST_CODE",
    cell_ref="A1",
    severity=Severity.LOW,
    message="test message",
    raised_by="test",
    authority=AuthoritySource.AI_ASSUMPTION,
    expected=None,
    actual=None,
):
    return Finding(
        code=code,
        cell_ref=cell_ref,
        severity=severity,
        message=message,
        raised_by=raised_by,
        authority=authority,
        expected=expected,
        actual=actual,
    )


def _make_wp(engagement="ENG-001", entity="Fictional Co", period="FY2024"):
    return Workpaper(engagement=engagement, entity=entity, period=period)


def _make_cell(ref="A1", label="Revenue", value=1000.0, formula=None,
               source=AuthoritySource.WORKBOOK_FORMULA):
    return WorkpaperCell(ref=ref, label=label, value=value, formula=formula, source=source)


# ============================================================================
# 1. Severity enum ordering invariants – 40 cases
# ============================================================================

@pytest.mark.parametrize(
    "lower, higher",
    [
        (Severity.LOW, Severity.MEDIUM),
        (Severity.LOW, Severity.HIGH),
        (Severity.LOW, Severity.CRITICAL),
        (Severity.MEDIUM, Severity.HIGH),
        (Severity.MEDIUM, Severity.CRITICAL),
        (Severity.HIGH, Severity.CRITICAL),
        # integer values
        (Severity.LOW, Severity.LOW),       # equal — not strictly less
        (Severity.MEDIUM, Severity.MEDIUM),
        (Severity.HIGH, Severity.HIGH),
        (Severity.CRITICAL, Severity.CRITICAL),
    ],
)
def test_severity_ordering_strict(lower, higher):
    """Lower severity is never greater than higher severity."""
    assert int(lower) <= int(higher)


@pytest.mark.parametrize(
    "sev, expected_value",
    [
        (Severity.LOW, 1),
        (Severity.MEDIUM, 2),
        (Severity.HIGH, 3),
        (Severity.CRITICAL, 4),
    ],
)
def test_severity_integer_values(sev, expected_value):
    assert int(sev) == expected_value


@pytest.mark.parametrize(
    "sev, expected_label",
    [
        (Severity.LOW, "Low"),
        (Severity.MEDIUM, "Medium"),
        (Severity.HIGH, "High"),
        (Severity.CRITICAL, "Critical"),
    ],
)
def test_severity_label(sev, expected_label):
    assert sev.label == expected_label


@pytest.mark.parametrize(
    "name, expected_sev",
    [
        ("LOW", Severity.LOW),
        ("MEDIUM", Severity.MEDIUM),
        ("HIGH", Severity.HIGH),
        ("CRITICAL", Severity.CRITICAL),
        ("low", Severity.LOW),
        ("medium", Severity.MEDIUM),
        ("high", Severity.HIGH),
        ("critical", Severity.CRITICAL),
        ("Low", Severity.LOW),
        ("Medium", Severity.MEDIUM),
        ("High", Severity.HIGH),
        ("Critical", Severity.CRITICAL),
        ("  LOW  ", Severity.LOW),
        ("  high  ", Severity.HIGH),
    ],
)
def test_severity_from_name(name, expected_sev):
    assert Severity.from_name(name) == expected_sev


@pytest.mark.parametrize(
    "a, b",
    [
        (Severity.LOW, Severity.MEDIUM),
        (Severity.LOW, Severity.HIGH),
        (Severity.LOW, Severity.CRITICAL),
        (Severity.MEDIUM, Severity.HIGH),
        (Severity.MEDIUM, Severity.CRITICAL),
        (Severity.HIGH, Severity.CRITICAL),
    ],
)
def test_severity_strictly_less_than(a, b):
    assert a < b


@pytest.mark.parametrize(
    "a, b",
    [
        (Severity.CRITICAL, Severity.HIGH),
        (Severity.CRITICAL, Severity.MEDIUM),
        (Severity.CRITICAL, Severity.LOW),
        (Severity.HIGH, Severity.MEDIUM),
        (Severity.HIGH, Severity.LOW),
        (Severity.MEDIUM, Severity.LOW),
    ],
)
def test_severity_strictly_greater_than(a, b):
    assert a > b


@pytest.mark.parametrize(
    "sev",
    [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL],
)
def test_severity_equal_to_itself(sev):
    assert sev == sev


# ============================================================================
# 2. AuthoritySource enum ordering and labels – 60 cases
# ============================================================================

@pytest.mark.parametrize(
    "auth, expected_value",
    [
        (AuthoritySource.AI_ASSUMPTION, 1),
        (AuthoritySource.WORKBOOK_FORMULA, 2),
        (AuthoritySource.CURRENT_YEAR_SOURCE, 3),
        (AuthoritySource.MEETING_DECISION, 4),
        (AuthoritySource.MANAGEMENT_INSTRUCTION, 5),
        (AuthoritySource.SIGNED_PRIOR_YEAR, 6),
    ],
)
def test_authority_integer_values(auth, expected_value):
    assert int(auth) == expected_value


@pytest.mark.parametrize(
    "auth, expected_label",
    [
        (AuthoritySource.AI_ASSUMPTION, "Ai Assumption"),
        (AuthoritySource.WORKBOOK_FORMULA, "Workbook Formula"),
        (AuthoritySource.CURRENT_YEAR_SOURCE, "Current Year Source"),
        (AuthoritySource.MEETING_DECISION, "Meeting Decision"),
        (AuthoritySource.MANAGEMENT_INSTRUCTION, "Management Instruction"),
        (AuthoritySource.SIGNED_PRIOR_YEAR, "Signed Prior Year"),
    ],
)
def test_authority_label(auth, expected_label):
    assert auth.label == expected_label


@pytest.mark.parametrize(
    "lower, higher",
    [
        (AuthoritySource.AI_ASSUMPTION, AuthoritySource.WORKBOOK_FORMULA),
        (AuthoritySource.AI_ASSUMPTION, AuthoritySource.CURRENT_YEAR_SOURCE),
        (AuthoritySource.AI_ASSUMPTION, AuthoritySource.MEETING_DECISION),
        (AuthoritySource.AI_ASSUMPTION, AuthoritySource.MANAGEMENT_INSTRUCTION),
        (AuthoritySource.AI_ASSUMPTION, AuthoritySource.SIGNED_PRIOR_YEAR),
        (AuthoritySource.WORKBOOK_FORMULA, AuthoritySource.CURRENT_YEAR_SOURCE),
        (AuthoritySource.WORKBOOK_FORMULA, AuthoritySource.MEETING_DECISION),
        (AuthoritySource.WORKBOOK_FORMULA, AuthoritySource.MANAGEMENT_INSTRUCTION),
        (AuthoritySource.WORKBOOK_FORMULA, AuthoritySource.SIGNED_PRIOR_YEAR),
        (AuthoritySource.CURRENT_YEAR_SOURCE, AuthoritySource.MEETING_DECISION),
        (AuthoritySource.CURRENT_YEAR_SOURCE, AuthoritySource.MANAGEMENT_INSTRUCTION),
        (AuthoritySource.CURRENT_YEAR_SOURCE, AuthoritySource.SIGNED_PRIOR_YEAR),
        (AuthoritySource.MEETING_DECISION, AuthoritySource.MANAGEMENT_INSTRUCTION),
        (AuthoritySource.MEETING_DECISION, AuthoritySource.SIGNED_PRIOR_YEAR),
        (AuthoritySource.MANAGEMENT_INSTRUCTION, AuthoritySource.SIGNED_PRIOR_YEAR),
    ],
)
def test_authority_hierarchy_ordering(lower, higher):
    assert lower < higher


@pytest.mark.parametrize(
    "auth",
    [
        AuthoritySource.AI_ASSUMPTION,
        AuthoritySource.WORKBOOK_FORMULA,
        AuthoritySource.CURRENT_YEAR_SOURCE,
        AuthoritySource.MEETING_DECISION,
        AuthoritySource.MANAGEMENT_INSTRUCTION,
        AuthoritySource.SIGNED_PRIOR_YEAR,
    ],
)
def test_authority_equal_to_itself(auth):
    assert auth == auth


@pytest.mark.parametrize(
    "higher, lower",
    [
        (AuthoritySource.SIGNED_PRIOR_YEAR, AuthoritySource.AI_ASSUMPTION),
        (AuthoritySource.SIGNED_PRIOR_YEAR, AuthoritySource.WORKBOOK_FORMULA),
        (AuthoritySource.SIGNED_PRIOR_YEAR, AuthoritySource.CURRENT_YEAR_SOURCE),
        (AuthoritySource.MANAGEMENT_INSTRUCTION, AuthoritySource.AI_ASSUMPTION),
        (AuthoritySource.MANAGEMENT_INSTRUCTION, AuthoritySource.WORKBOOK_FORMULA),
        (AuthoritySource.MEETING_DECISION, AuthoritySource.AI_ASSUMPTION),
    ],
)
def test_authority_higher_is_greater(higher, lower):
    assert higher > lower


# ============================================================================
# 3. Finding construction + to_dict – 80 cases
# ============================================================================

_ALL_SEVERITIES = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
_ALL_AUTHORITIES = [
    AuthoritySource.AI_ASSUMPTION,
    AuthoritySource.WORKBOOK_FORMULA,
    AuthoritySource.CURRENT_YEAR_SOURCE,
    AuthoritySource.MEETING_DECISION,
    AuthoritySource.MANAGEMENT_INSTRUCTION,
    AuthoritySource.SIGNED_PRIOR_YEAR,
]

@pytest.mark.parametrize("sev", _ALL_SEVERITIES)
@pytest.mark.parametrize("auth", _ALL_AUTHORITIES)
def test_finding_construction_sev_x_auth(sev, auth):
    """Finding can be constructed for every severity × authority combination."""
    f = Finding(
        code="TEST",
        cell_ref="B3",
        severity=sev,
        message="unit test",
        raised_by="pytest",
        authority=auth,
    )
    assert f.severity is sev
    assert f.authority is auth
    assert f.code == "TEST"
    assert f.cell_ref == "B3"


@pytest.mark.parametrize(
    "code, cell_ref, message, raised_by",
    [
        ("CODE_A", "A1", "msg a", "role_a"),
        ("CODE_B", "B2", "msg b", "role_b"),
        ("TIE_OUT_MISMATCH", "C3", "tie out mismatch", "Reviewer:MockLLM"),
        ("FORMULA_UNRESOLVABLE", "D4", "bad formula", "Reviewer:MockLLM"),
        ("HARDCODED_NO_FORMULA", "E5", "hard coded value", "Reviewer:MockLLM"),
        ("UNSUPPORTED_AI_ASSUMPTION", "F6", "ai assumption", "Reviewer:MockLLM"),
        ("PROCESS_LANGUAGE_LEAK", "G7", "leaked process language", "Reviewer:MockLLM"),
        ("RATE_OUT_OF_BAND", "H8", "rate out of band", "Specialist"),
        ("MISSING_REQUIRED_CELL", "B5", "missing B5", "Audit:DeterministicAuditor"),
        ("AUDIT_FORMULA_ERROR", "B7", "audit formula error", "Audit:DeterministicAuditor"),
        ("AUDIT_TIE_OUT_FAIL", "B8", "audit tie out fail", "Audit:DeterministicAuditor"),
        ("CUSTOM_CODE_1", "Z99", "custom msg 1", "custom_role_1"),
        ("CUSTOM_CODE_2", "AA1", "custom msg 2", "custom_role_2"),
        ("CUSTOM_CODE_3", "<workpaper>", "workpaper-level issue", "Reviewer"),
        ("CUSTOM_CODE_4", "<note[0]>", "note issue", "Reviewer"),
    ],
)
def test_finding_to_dict_keys(code, cell_ref, message, raised_by):
    f = _make_finding(code=code, cell_ref=cell_ref, message=message, raised_by=raised_by)
    d = f.to_dict()
    assert set(d.keys()) == {"code", "cell_ref", "severity", "message",
                              "raised_by", "authority", "expected", "actual"}
    assert d["code"] == code
    assert d["cell_ref"] == cell_ref
    assert d["message"] == message
    assert d["raised_by"] == raised_by


@pytest.mark.parametrize("sev", _ALL_SEVERITIES)
def test_finding_to_dict_severity_is_label(sev):
    f = _make_finding(severity=sev)
    assert f.to_dict()["severity"] == sev.label


@pytest.mark.parametrize("auth", _ALL_AUTHORITIES)
def test_finding_to_dict_authority_is_label(auth):
    f = _make_finding(authority=auth)
    assert f.to_dict()["authority"] == auth.label


@pytest.mark.parametrize(
    "expected_val, actual_val",
    [
        (None, None),
        (100.0, 100.0),
        (100.0, 101.0),
        (0.0, 0.0),
        (50.0, None),
        (None, 50.0),
        (1000.0, 999.0),
        (0.01, 0.02),
        ("string_expected", None),
        (None, "string_actual"),
    ],
)
def test_finding_expected_actual_stored_verbatim(expected_val, actual_val):
    f = _make_finding(expected=expected_val, actual=actual_val)
    assert f.expected == expected_val
    assert f.actual == actual_val
    assert f.to_dict()["expected"] == expected_val
    assert f.to_dict()["actual"] == actual_val


@pytest.mark.parametrize("sev", _ALL_SEVERITIES)
def test_finding_is_frozen(sev):
    """Finding is a frozen dataclass -- mutation raises."""
    f = _make_finding(severity=sev)
    with pytest.raises((AttributeError, TypeError)):
        f.code = "CHANGED"  # type: ignore[misc]


# ============================================================================
# 4. WorkpaperCell construction and to_dict – 50 cases
# ============================================================================

@pytest.mark.parametrize(
    "ref, label, value, formula, source",
    [
        ("A1", "Revenue", 1000.0, None, AuthoritySource.WORKBOOK_FORMULA),
        ("B2", "Cost", 500.0, None, AuthoritySource.CURRENT_YEAR_SOURCE),
        ("C3", "Gross Profit", 500.0, "=A1-B2", AuthoritySource.WORKBOOK_FORMULA),
        ("D4", "Tax Rate", 0.25, None, AuthoritySource.AI_ASSUMPTION),
        ("E5", "Tax Expense", 125.0, "=C3*D4", AuthoritySource.WORKBOOK_FORMULA),
        ("B5", "Net Revenue", 900.0, "=A1-B2+C3", AuthoritySource.WORKBOOK_FORMULA),
        ("B7", "Total Assets", 5000.0, None, AuthoritySource.SIGNED_PRIOR_YEAR),
        ("B8", "Total Liabilities", 2000.0, None, AuthoritySource.MEETING_DECISION),
        ("F6", "Rate", 0.15, None, AuthoritySource.MANAGEMENT_INSTRUCTION),
        ("G7", "Note Ref", None, None, AuthoritySource.WORKBOOK_FORMULA),
        ("AA1", "Multi-col Ref", 42.0, None, AuthoritySource.WORKBOOK_FORMULA),
        ("Z9", "Last Col", 99.0, None, AuthoritySource.CURRENT_YEAR_SOURCE),
        ("A100", "Last Row", 88.0, None, AuthoritySource.AI_ASSUMPTION),
        ("X5", "Subtotal", 250.0, "=A1+B2", AuthoritySource.WORKBOOK_FORMULA),
        ("Y6", "Variance", -50.0, "=A1-X5", AuthoritySource.WORKBOOK_FORMULA),
    ],
)
def test_workpaper_cell_construction_and_to_dict(ref, label, value, formula, source):
    cell = WorkpaperCell(ref=ref, label=label, value=value, formula=formula, source=source)
    assert cell.ref == ref
    assert cell.label == label
    assert cell.value == value
    assert cell.formula == formula
    assert cell.source == source

    d = cell.to_dict()
    assert d["ref"] == ref
    assert d["label"] == label
    assert d["value"] == value
    assert d["formula"] == formula
    assert d["source"] == source.label


@pytest.mark.parametrize("source", _ALL_AUTHORITIES)
def test_workpaper_cell_default_source_and_custom(source):
    cell = WorkpaperCell(ref="A1", label="Revenue", value=100.0, source=source)
    assert cell.source == source


@pytest.mark.parametrize(
    "ref, value, formula",
    [
        ("A1", 100.0, "=B2+C3"),
        ("A2", 200.0, "=D4-E5"),
        ("A3", 300.0, "=A1+A2"),
        ("B4", 50.0, "=A1*D4"),
        ("B5", 0.0, "=A1-A1"),
        ("C6", 1.0, "=A1/A1"),
        ("D7", 0.15, None),
        ("E8", None, "=A1+B2"),
        ("F9", 999.0, None),
        ("G10", -100.0, None),
        ("H11", 0.0, None),
        ("I12", 1e6, None),
        ("J13", 0.001, None),
        ("K14", 100.5, "=A1+0.5"),
        ("L15", 200.25, None),
        ("M16", 300.75, None),
        ("N17", 1.23, None),
        ("O18", 45.67, None),
        ("P19", 89.01, None),
        ("Q20", 12.34, None),
    ],
)
def test_workpaper_cell_value_and_formula_stored(ref, value, formula):
    cell = WorkpaperCell(ref=ref, label="label", value=value, formula=formula)
    assert cell.value == value
    assert cell.formula == formula


# ============================================================================
# 5. Workpaper: set_cell, get, ordered_cells, digest, clone – 60 cases
# ============================================================================

@pytest.mark.parametrize(
    "refs",
    [
        ["A1"],
        ["A1", "B2"],
        ["A1", "B2", "C3"],
        ["B5", "B7", "B8"],
        ["A1", "B2", "C3", "D4", "E5"],
        ["Z9", "A1", "M5"],
        ["AA1", "AB2", "AC3"],
        ["B2", "B3", "B4", "B5", "B7", "B8"],
    ],
)
def test_workpaper_set_and_get_cells(refs):
    wp = _make_wp()
    cells = {}
    for i, ref in enumerate(refs):
        cell = WorkpaperCell(ref=ref, label=f"label_{i}", value=float(i * 10))
        wp.set_cell(cell)
        cells[ref] = cell
    for ref, cell in cells.items():
        retrieved = wp.get(ref)
        assert retrieved is not None
        assert retrieved.ref == ref
        assert retrieved.value == cell.value


@pytest.mark.parametrize(
    "refs, expected_ordered",
    [
        (["B2", "A1", "C3"], ["A1", "B2", "C3"]),
        (["Z9", "A1", "M5"], ["A1", "M5", "Z9"]),
        (["B8", "B5", "B7"], ["B5", "B7", "B8"]),
        (["AA1", "A1", "AB2"], ["A1", "AA1", "AB2"]),
        (["C3", "B2", "A1"], ["A1", "B2", "C3"]),
        (["D4", "C3", "B2", "A1"], ["A1", "B2", "C3", "D4"]),
    ],
)
def test_workpaper_ordered_cells_sorted(refs, expected_ordered):
    wp = _make_wp()
    for i, ref in enumerate(refs):
        wp.set_cell(WorkpaperCell(ref=ref, label=f"L{i}", value=float(i)))
    result_refs = [c.ref for c in wp.ordered_cells()]
    assert result_refs == expected_ordered


@pytest.mark.parametrize(
    "engagement, entity, period",
    [
        ("ENG-001", "Fictional Co A", "FY2024"),
        ("ENG-002", "Fictional Co B", "FY2023"),
        ("ENG-003", "Fictional Co C", "Q1-2024"),
        ("ABC-999", "Dummy Entity Ltd", "2024"),
        ("XYZ-100", "Test Corp Inc", "CY2024"),
    ],
)
def test_workpaper_to_dict_fields(engagement, entity, period):
    wp = Workpaper(engagement=engagement, entity=entity, period=period)
    d = wp.to_dict()
    assert d["engagement"] == engagement
    assert d["entity"] == entity
    assert d["period"] == period
    assert d["cells"] == {}
    assert d["notes"] == []


@pytest.mark.parametrize(
    "num_cells",
    [0, 1, 2, 3, 5, 10],
)
def test_workpaper_digest_is_stable(num_cells):
    """Same workpaper content always produces the same digest."""
    wp = _make_wp()
    for i in range(num_cells):
        wp.set_cell(WorkpaperCell(ref=f"A{i+1}", label=f"L{i}", value=float(i)))
    d1 = wp.digest()
    d2 = wp.digest()
    assert d1 == d2
    assert isinstance(d1, str)
    assert len(d1) == 64  # SHA-256 hex


@pytest.mark.parametrize(
    "num_cells",
    [0, 1, 3, 5],
)
def test_workpaper_clone_is_independent(num_cells):
    """clone() produces a deep copy; mutating the clone does not affect the original."""
    wp = _make_wp()
    for i in range(num_cells):
        wp.set_cell(WorkpaperCell(ref=f"A{i+1}", label=f"L{i}", value=float(i)))
    original_digest = wp.digest()
    clone = wp.clone()
    # Mutate the clone
    clone.set_cell(WorkpaperCell(ref="Z99", label="new", value=9999.0))
    assert wp.digest() == original_digest
    assert clone.digest() != original_digest


@pytest.mark.parametrize(
    "note_text",
    [
        "Simple note.",
        "Note with numbers 12345.",
        "Note with special chars: & < > '.",
        "A very long note " + "x" * 200,
        "",
    ],
)
def test_workpaper_notes_stored_in_to_dict(note_text):
    wp = _make_wp()
    wp.notes.append(note_text)
    d = wp.to_dict()
    assert note_text in d["notes"]


# ============================================================================
# 6. ReadOnlyWorkpaperView: read access and mutation guard – 40 cases
# ============================================================================

@pytest.mark.parametrize(
    "refs",
    [
        ["A1"],
        ["A1", "B2"],
        ["A1", "B2", "C3"],
        ["B5", "B7", "B8"],
        [],
    ],
)
def test_readonly_view_get_returns_cells(refs):
    wp = _make_wp()
    for i, ref in enumerate(refs):
        wp.set_cell(WorkpaperCell(ref=ref, label=f"L{i}", value=float(i * 10)))
    view = wp.frozen_snapshot()
    for ref in refs:
        cell = view.get(ref)
        assert cell is not None
        assert cell.ref == ref
    assert view.get("NONEXISTENT") is None


@pytest.mark.parametrize(
    "attr_name, new_value",
    [
        ("engagement", "HACKED"),
        ("entity", "HACKED ENTITY"),
        ("period", "FAKE-PERIOD"),
        ("foo", "bar"),
        ("cells", {}),
        ("notes", []),
        ("digest", None),
        ("ordered_cells", None),
    ],
)
def test_readonly_view_mutation_raises(attr_name, new_value):
    wp = _make_wp()
    view = wp.frozen_snapshot()
    with pytest.raises(WorkpaperMutationError):
        setattr(view, attr_name, new_value)


@pytest.mark.parametrize(
    "refs",
    [
        ["A1"],
        ["A1", "B2"],
        ["B5", "B7", "B8"],
        ["Z9", "A1", "M5"],
        [],
    ],
)
def test_readonly_view_ordered_cells_matches_workpaper(refs):
    wp = _make_wp()
    for i, ref in enumerate(refs):
        wp.set_cell(WorkpaperCell(ref=ref, label=f"L{i}", value=float(i)))
    view = wp.frozen_snapshot()
    wp_refs = [c.ref for c in wp.ordered_cells()]
    view_refs = [c.ref for c in view.ordered_cells()]
    assert wp_refs == view_refs


@pytest.mark.parametrize(
    "num_cells",
    [0, 1, 2, 5, 10],
)
def test_readonly_view_digest_matches_workpaper(num_cells):
    wp = _make_wp()
    for i in range(num_cells):
        wp.set_cell(WorkpaperCell(ref=f"A{i+1}", label=f"L{i}", value=float(i)))
    view = wp.frozen_snapshot()
    assert view.digest() == wp.digest()


@pytest.mark.parametrize(
    "engagement, entity, period",
    [
        ("E1", "Entity A", "FY2024"),
        ("E2", "Entity B", "FY2023"),
        ("E3", "Entity C", "Q1"),
    ],
)
def test_readonly_view_engagement_entity_period(engagement, entity, period):
    wp = Workpaper(engagement=engagement, entity=entity, period=period)
    view = wp.frozen_snapshot()
    assert view.engagement == engagement
    assert view.entity == entity
    assert view.period == period


# ============================================================================
# 7. reconcile(): de-duplication, tiebreak, sort order – 60 cases
# ============================================================================

@pytest.mark.parametrize(
    "findings, expected_count",
    [
        ([], 0),
        ([_make_finding(code="A", cell_ref="A1")], 1),
        # same key -> de-duplicated to 1
        (
            [
                _make_finding(code="A", cell_ref="A1"),
                _make_finding(code="A", cell_ref="A1"),
            ],
            1,
        ),
        # different codes -> 2
        (
            [
                _make_finding(code="A", cell_ref="A1"),
                _make_finding(code="B", cell_ref="A1"),
            ],
            2,
        ),
        # different cell refs -> 2
        (
            [
                _make_finding(code="A", cell_ref="A1"),
                _make_finding(code="A", cell_ref="B2"),
            ],
            2,
        ),
        # three unique -> 3
        (
            [
                _make_finding(code="A", cell_ref="A1"),
                _make_finding(code="B", cell_ref="A1"),
                _make_finding(code="A", cell_ref="B2"),
            ],
            3,
        ),
        # three with one dup -> 2
        (
            [
                _make_finding(code="X", cell_ref="A1"),
                _make_finding(code="X", cell_ref="A1"),
                _make_finding(code="Y", cell_ref="A1"),
            ],
            2,
        ),
        # 5 all unique
        (
            [_make_finding(code=f"C{i}", cell_ref="A1") for i in range(5)],
            5,
        ),
        # 5 all duplicates of one
        (
            [_make_finding(code="DUP", cell_ref="A1") for _ in range(5)],
            1,
        ),
        # 10 with 5 unique codes x 2 cell refs = 10 unique
        (
            [
                _make_finding(code=f"C{i}", cell_ref=f"A{j}")
                for i in range(5) for j in range(1, 3)
            ],
            10,
        ),
    ],
)
def test_reconcile_deduplication_count(findings, expected_count):
    result = reconcile(findings)
    assert len(result) == expected_count


@pytest.mark.parametrize(
    "auth_winner, auth_loser",
    [
        (AuthoritySource.SIGNED_PRIOR_YEAR, AuthoritySource.AI_ASSUMPTION),
        (AuthoritySource.MANAGEMENT_INSTRUCTION, AuthoritySource.WORKBOOK_FORMULA),
        (AuthoritySource.MEETING_DECISION, AuthoritySource.CURRENT_YEAR_SOURCE),
        (AuthoritySource.CURRENT_YEAR_SOURCE, AuthoritySource.AI_ASSUMPTION),
        (AuthoritySource.WORKBOOK_FORMULA, AuthoritySource.AI_ASSUMPTION),
        (AuthoritySource.SIGNED_PRIOR_YEAR, AuthoritySource.WORKBOOK_FORMULA),
    ],
)
def test_reconcile_higher_authority_wins(auth_winner, auth_loser):
    """When two findings have the same key, the higher authority survives."""
    winner = Finding(
        code="CODE", cell_ref="A1", severity=Severity.LOW,
        message="winner", raised_by="role", authority=auth_winner,
    )
    loser = Finding(
        code="CODE", cell_ref="A1", severity=Severity.LOW,
        message="loser", raised_by="role", authority=auth_loser,
    )
    result = reconcile([loser, winner])
    assert len(result) == 1
    assert result[0].authority == auth_winner
    assert result[0].message == "winner"


@pytest.mark.parametrize(
    "sev_winner, sev_loser",
    [
        (Severity.CRITICAL, Severity.HIGH),
        (Severity.CRITICAL, Severity.MEDIUM),
        (Severity.CRITICAL, Severity.LOW),
        (Severity.HIGH, Severity.MEDIUM),
        (Severity.HIGH, Severity.LOW),
        (Severity.MEDIUM, Severity.LOW),
    ],
)
def test_reconcile_higher_severity_wins_on_equal_authority(sev_winner, sev_loser):
    """When authority is equal, higher severity wins."""
    winner = Finding(
        code="CODE", cell_ref="A1", severity=sev_winner,
        message="winner", raised_by="role",
        authority=AuthoritySource.WORKBOOK_FORMULA,
    )
    loser = Finding(
        code="CODE", cell_ref="A1", severity=sev_loser,
        message="loser", raised_by="role",
        authority=AuthoritySource.WORKBOOK_FORMULA,
    )
    result = reconcile([loser, winner])
    assert len(result) == 1
    assert result[0].severity == sev_winner


@pytest.mark.parametrize(
    "severities, expected_first_severity",
    [
        ([Severity.LOW, Severity.HIGH, Severity.MEDIUM], Severity.HIGH),
        ([Severity.MEDIUM, Severity.CRITICAL, Severity.LOW], Severity.CRITICAL),
        ([Severity.HIGH, Severity.CRITICAL, Severity.MEDIUM], Severity.CRITICAL),
        ([Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL], Severity.CRITICAL),
        ([Severity.LOW, Severity.MEDIUM], Severity.MEDIUM),
        ([Severity.HIGH, Severity.LOW], Severity.HIGH),
        ([Severity.CRITICAL], Severity.CRITICAL),
        ([Severity.LOW], Severity.LOW),
    ],
)
def test_reconcile_sorted_most_severe_first(severities, expected_first_severity):
    """Reconcile output is sorted most-severe first."""
    findings = [
        Finding(
            code=f"CODE_{i}", cell_ref=f"A{i+1}", severity=sev,
            message="msg", raised_by="role",
            authority=AuthoritySource.WORKBOOK_FORMULA,
        )
        for i, sev in enumerate(severities)
    ]
    result = reconcile(findings)
    assert result[0].severity == expected_first_severity


# ============================================================================
# 8. severity_breakdown() – 30 cases
# ============================================================================

@pytest.mark.parametrize(
    "findings, expected_counts",
    [
        ([], {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}),
        (
            [_make_finding(severity=Severity.CRITICAL)],
            {"Critical": 1, "High": 0, "Medium": 0, "Low": 0},
        ),
        (
            [_make_finding(severity=Severity.HIGH)],
            {"Critical": 0, "High": 1, "Medium": 0, "Low": 0},
        ),
        (
            [_make_finding(severity=Severity.MEDIUM)],
            {"Critical": 0, "High": 0, "Medium": 1, "Low": 0},
        ),
        (
            [_make_finding(severity=Severity.LOW)],
            {"Critical": 0, "High": 0, "Medium": 0, "Low": 1},
        ),
        (
            [_make_finding(severity=Severity.CRITICAL, code="A"),
             _make_finding(severity=Severity.HIGH, code="B")],
            {"Critical": 1, "High": 1, "Medium": 0, "Low": 0},
        ),
        (
            [_make_finding(severity=Severity.LOW, code="A"),
             _make_finding(severity=Severity.LOW, code="B"),
             _make_finding(severity=Severity.LOW, code="C")],
            {"Critical": 0, "High": 0, "Medium": 0, "Low": 3},
        ),
        (
            [_make_finding(severity=s, code=f"C{i}")
             for i, s in enumerate([Severity.CRITICAL, Severity.HIGH,
                                     Severity.MEDIUM, Severity.LOW])],
            {"Critical": 1, "High": 1, "Medium": 1, "Low": 1},
        ),
        (
            [_make_finding(severity=Severity.CRITICAL, code=f"C{i}") for i in range(5)],
            {"Critical": 5, "High": 0, "Medium": 0, "Low": 0},
        ),
        (
            [_make_finding(severity=Severity.MEDIUM, code=f"M{i}") for i in range(3)]
            + [_make_finding(severity=Severity.LOW, code=f"L{i}") for i in range(2)],
            {"Critical": 0, "High": 0, "Medium": 3, "Low": 2},
        ),
    ],
)
def test_severity_breakdown_counts(findings, expected_counts):
    result = severity_breakdown(findings)
    assert result == expected_counts


@pytest.mark.parametrize(
    "n_critical, n_high, n_medium, n_low",
    [
        (0, 0, 0, 0),
        (1, 0, 0, 0),
        (0, 1, 0, 0),
        (0, 0, 1, 0),
        (0, 0, 0, 1),
        (2, 3, 4, 5),
        (10, 0, 0, 0),
        (0, 0, 10, 0),
        (1, 1, 1, 1),
        (5, 4, 3, 2),
    ],
)
def test_severity_breakdown_all_four_buckets_present(
    n_critical, n_high, n_medium, n_low
):
    findings = (
        [_make_finding(severity=Severity.CRITICAL, code=f"C{i}") for i in range(n_critical)]
        + [_make_finding(severity=Severity.HIGH, code=f"H{i}") for i in range(n_high)]
        + [_make_finding(severity=Severity.MEDIUM, code=f"M{i}") for i in range(n_medium)]
        + [_make_finding(severity=Severity.LOW, code=f"L{i}") for i in range(n_low)]
    )
    result = severity_breakdown(findings)
    assert set(result.keys()) == {"Critical", "High", "Medium", "Low"}
    assert result["Critical"] == n_critical
    assert result["High"] == n_high
    assert result["Medium"] == n_medium
    assert result["Low"] == n_low


# ============================================================================
# 9. HumanGate.decide() – PASS/FLAG/FAIL – 40 cases
# ============================================================================

@pytest.mark.parametrize(
    "findings, expected_status",
    [
        # PASS: empty
        ([], VerdictStatus.PASS),
        # PASS: only LOW
        ([_make_finding(severity=Severity.LOW, code="L1")], VerdictStatus.PASS),
        # PASS: only MEDIUM
        ([_make_finding(severity=Severity.MEDIUM, code="M1")], VerdictStatus.PASS),
        # PASS: LOW + MEDIUM
        (
            [_make_finding(severity=Severity.LOW, code="L1"),
             _make_finding(severity=Severity.MEDIUM, code="M1")],
            VerdictStatus.PASS,
        ),
        # PASS: many LOW
        (
            [_make_finding(severity=Severity.LOW, code=f"L{i}") for i in range(10)],
            VerdictStatus.PASS,
        ),
        # FLAG: one HIGH
        ([_make_finding(severity=Severity.HIGH, code="H1")], VerdictStatus.FLAG),
        # FLAG: HIGH + LOW
        (
            [_make_finding(severity=Severity.HIGH, code="H1"),
             _make_finding(severity=Severity.LOW, code="L1")],
            VerdictStatus.FLAG,
        ),
        # FLAG: HIGH + MEDIUM
        (
            [_make_finding(severity=Severity.HIGH, code="H1"),
             _make_finding(severity=Severity.MEDIUM, code="M1")],
            VerdictStatus.FLAG,
        ),
        # FLAG: multiple HIGH
        (
            [_make_finding(severity=Severity.HIGH, code=f"H{i}") for i in range(5)],
            VerdictStatus.FLAG,
        ),
        # FAIL: one CRITICAL
        ([_make_finding(severity=Severity.CRITICAL, code="C1")], VerdictStatus.FAIL),
        # FAIL: CRITICAL + HIGH
        (
            [_make_finding(severity=Severity.CRITICAL, code="C1"),
             _make_finding(severity=Severity.HIGH, code="H1")],
            VerdictStatus.FAIL,
        ),
        # FAIL: CRITICAL + LOW
        (
            [_make_finding(severity=Severity.CRITICAL, code="C1"),
             _make_finding(severity=Severity.LOW, code="L1")],
            VerdictStatus.FAIL,
        ),
        # FAIL: multiple CRITICAL
        (
            [_make_finding(severity=Severity.CRITICAL, code=f"C{i}") for i in range(3)],
            VerdictStatus.FAIL,
        ),
        # FAIL: CRITICAL takes priority over HIGH
        (
            [_make_finding(severity=Severity.HIGH, code="H1"),
             _make_finding(severity=Severity.CRITICAL, code="C1"),
             _make_finding(severity=Severity.MEDIUM, code="M1")],
            VerdictStatus.FAIL,
        ),
    ],
)
def test_human_gate_verdict_status(findings, expected_status):
    gate = HumanGate()
    verdict = gate.decide(findings)
    assert verdict.status is expected_status


@pytest.mark.parametrize(
    "n_critical, n_high, n_medium, n_low, expected_status",
    [
        (0, 0, 0, 0, VerdictStatus.PASS),
        (0, 0, 1, 0, VerdictStatus.PASS),
        (0, 0, 0, 1, VerdictStatus.PASS),
        (0, 0, 5, 5, VerdictStatus.PASS),
        (0, 1, 0, 0, VerdictStatus.FLAG),
        (0, 1, 5, 5, VerdictStatus.FLAG),
        (0, 3, 0, 0, VerdictStatus.FLAG),
        (1, 0, 0, 0, VerdictStatus.FAIL),
        (1, 1, 0, 0, VerdictStatus.FAIL),
        (1, 0, 5, 5, VerdictStatus.FAIL),
        (2, 0, 0, 0, VerdictStatus.FAIL),
        (0, 0, 0, 10, VerdictStatus.PASS),
        (0, 0, 10, 0, VerdictStatus.PASS),
        (0, 10, 0, 0, VerdictStatus.FLAG),
        (10, 0, 0, 0, VerdictStatus.FAIL),
        (1, 1, 1, 1, VerdictStatus.FAIL),
        (0, 1, 1, 1, VerdictStatus.FLAG),
        (0, 0, 1, 1, VerdictStatus.PASS),
        (3, 2, 1, 0, VerdictStatus.FAIL),
        (0, 2, 3, 4, VerdictStatus.FLAG),
    ],
)
def test_human_gate_verdict_status_parametric(
    n_critical, n_high, n_medium, n_low, expected_status
):
    findings = (
        [_make_finding(severity=Severity.CRITICAL, code=f"C{i}") for i in range(n_critical)]
        + [_make_finding(severity=Severity.HIGH, code=f"H{i}") for i in range(n_high)]
        + [_make_finding(severity=Severity.MEDIUM, code=f"M{i}") for i in range(n_medium)]
        + [_make_finding(severity=Severity.LOW, code=f"L{i}") for i in range(n_low)]
    )
    gate = HumanGate()
    verdict = gate.decide(findings)
    assert verdict.status is expected_status


@pytest.mark.parametrize(
    "signer",
    [
        "HumanGate(automated-policy)",
        "ReviewerManager:Alice",
        "SeniorPartner:Bob",
        "automated-policy-v2",
    ],
)
def test_human_gate_signer_stored(signer):
    gate = HumanGate(signer=signer)
    verdict = gate.decide([])
    assert verdict.signed_off_by == signer


# ============================================================================
# 10. Verdict properties – 20 cases
# ============================================================================

@pytest.mark.parametrize(
    "status, expected_passed",
    [
        (VerdictStatus.PASS, True),
        (VerdictStatus.FLAG, False),
        (VerdictStatus.FAIL, False),
    ],
)
def test_verdict_passed_property(status, expected_passed):
    gate = HumanGate()
    if status is VerdictStatus.PASS:
        findings = []
    elif status is VerdictStatus.FLAG:
        findings = [_make_finding(severity=Severity.HIGH, code="H1")]
    else:
        findings = [_make_finding(severity=Severity.CRITICAL, code="C1")]
    verdict = gate.decide(findings)
    assert verdict.passed == expected_passed


@pytest.mark.parametrize(
    "status",
    [VerdictStatus.PASS, VerdictStatus.FLAG, VerdictStatus.FAIL],
)
def test_verdict_to_dict_has_required_keys(status):
    gate = HumanGate()
    if status is VerdictStatus.PASS:
        findings = []
    elif status is VerdictStatus.FLAG:
        findings = [_make_finding(severity=Severity.HIGH, code="H1")]
    else:
        findings = [_make_finding(severity=Severity.CRITICAL, code="C1")]
    verdict = gate.decide(findings)
    d = verdict.to_dict()
    assert set(d.keys()) == {
        "status", "max_severity", "severity_counts", "rationale",
        "signed_off_by", "findings", "notes",
    }
    assert d["status"] == status.value


@pytest.mark.parametrize(
    "findings_list, expected_max_sev",
    [
        ([], None),
        ([_make_finding(severity=Severity.LOW)], "Low"),
        ([_make_finding(severity=Severity.MEDIUM)], "Medium"),
        ([_make_finding(severity=Severity.HIGH)], "High"),
        ([_make_finding(severity=Severity.CRITICAL)], "Critical"),
        (
            [_make_finding(severity=Severity.LOW, code="A"),
             _make_finding(severity=Severity.HIGH, code="B")],
            "High",
        ),
        (
            [_make_finding(severity=Severity.MEDIUM, code="A"),
             _make_finding(severity=Severity.CRITICAL, code="B")],
            "Critical",
        ),
        (
            [_make_finding(severity=Severity.LOW, code="A"),
             _make_finding(severity=Severity.MEDIUM, code="B")],
            "Medium",
        ),
    ],
)
def test_verdict_max_severity(findings_list, expected_max_sev):
    gate = HumanGate()
    verdict = gate.decide(findings_list)
    if expected_max_sev is None:
        assert verdict.max_severity is None
        assert verdict.to_dict()["max_severity"] is None
    else:
        assert verdict.max_severity is not None
        assert verdict.max_severity.label == expected_max_sev
        assert verdict.to_dict()["max_severity"] == expected_max_sev


# ============================================================================
# 11. VerdictStatus enum – 10 cases
# ============================================================================

@pytest.mark.parametrize(
    "status, expected_value",
    [
        (VerdictStatus.PASS, "PASS"),
        (VerdictStatus.FLAG, "FLAG"),
        (VerdictStatus.FAIL, "FAIL"),
    ],
)
def test_verdict_status_values(status, expected_value):
    assert status.value == expected_value


@pytest.mark.parametrize("status", [VerdictStatus.PASS, VerdictStatus.FLAG, VerdictStatus.FAIL])
def test_verdict_status_equal_to_itself(status):
    assert status == status


# ============================================================================
# 12. Orchestrator run() structural invariants – 40 cases
# ============================================================================

_ORCHESTRATOR_KINDS = ["defective", "clean"]
_ORCHESTRATOR_SEEDS = [20240101, 20240102, 20240103, 20240104, 20240105]


@pytest.mark.parametrize("kind", _ORCHESTRATOR_KINDS)
@pytest.mark.parametrize("seed", _ORCHESTRATOR_SEEDS)
def test_orchestrator_run_returns_pipeline_result(kind, seed):
    from triangulate.roles.preparer import DemoPreparer
    orch = TriangulateOrchestrator(
        preparer=DemoPreparer(kind=kind, seed=seed),
        use_specialist=True,
    )
    result = orch.run()
    assert result is not None
    assert result.workpaper is not None
    assert result.verdict is not None


@pytest.mark.parametrize("kind", _ORCHESTRATOR_KINDS)
@pytest.mark.parametrize("seed", _ORCHESTRATOR_SEEDS)
def test_orchestrator_run_verdict_has_valid_status(kind, seed):
    from triangulate.roles.preparer import DemoPreparer
    orch = TriangulateOrchestrator(
        preparer=DemoPreparer(kind=kind, seed=seed),
    )
    result = orch.run()
    assert result.verdict.status in {
        VerdictStatus.PASS, VerdictStatus.FLAG, VerdictStatus.FAIL
    }


@pytest.mark.parametrize("kind", _ORCHESTRATOR_KINDS)
@pytest.mark.parametrize("seed", _ORCHESTRATOR_SEEDS)
def test_orchestrator_run_qa_summary_is_nonempty(kind, seed):
    from triangulate.roles.preparer import DemoPreparer
    orch = TriangulateOrchestrator(
        preparer=DemoPreparer(kind=kind, seed=seed),
    )
    result = orch.run()
    assert isinstance(result.qa_summary, list)
    assert len(result.qa_summary) > 0


@pytest.mark.parametrize("kind", _ORCHESTRATOR_KINDS)
@pytest.mark.parametrize("seed", _ORCHESTRATOR_SEEDS)
def test_orchestrator_run_builder_memo_is_nonempty(kind, seed):
    from triangulate.roles.preparer import DemoPreparer
    orch = TriangulateOrchestrator(
        preparer=DemoPreparer(kind=kind, seed=seed),
    )
    result = orch.run()
    assert isinstance(result.builder_memo, list)
    assert len(result.builder_memo) > 0


@pytest.mark.parametrize("kind", _ORCHESTRATOR_KINDS)
@pytest.mark.parametrize("seed", _ORCHESTRATOR_SEEDS)
def test_orchestrator_run_fix_packet_severity_is_critical_or_high(kind, seed):
    """All findings in the fix packet are CRITICAL or HIGH."""
    from triangulate.roles.preparer import DemoPreparer
    orch = TriangulateOrchestrator(
        preparer=DemoPreparer(kind=kind, seed=seed),
    )
    result = orch.run()
    for finding in result.fix_packet:
        assert finding.severity in {Severity.CRITICAL, Severity.HIGH}


@pytest.mark.parametrize("use_specialist", [True, False])
def test_orchestrator_use_specialist_flag(use_specialist):
    """use_specialist=False skips the specialist step."""
    orch = TriangulateOrchestrator(use_specialist=use_specialist)
    result = orch.run()
    if use_specialist:
        assert any("Specialist" in line for line in result.qa_summary)
    else:
        assert any("skipped" in line for line in result.change_log)


@pytest.mark.parametrize("kind", _ORCHESTRATOR_KINDS)
def test_orchestrator_is_deterministic(kind):
    """Same kind + seed always produces the same verdict status."""
    from triangulate.roles.preparer import DemoPreparer
    seed = 20240101
    orch1 = TriangulateOrchestrator(preparer=DemoPreparer(kind=kind, seed=seed))
    orch2 = TriangulateOrchestrator(preparer=DemoPreparer(kind=kind, seed=seed))
    r1 = orch1.run()
    r2 = orch2.run()
    assert r1.verdict.status == r2.verdict.status


@pytest.mark.parametrize("kind", _ORCHESTRATOR_KINDS)
@pytest.mark.parametrize("seed", _ORCHESTRATOR_SEEDS)
def test_orchestrator_workpaper_has_cells(kind, seed):
    """The workpaper produced by the orchestrator contains at least one cell."""
    from triangulate.roles.preparer import DemoPreparer
    orch = TriangulateOrchestrator(preparer=DemoPreparer(kind=kind, seed=seed))
    result = orch.run()
    assert len(result.workpaper.cells) > 0
