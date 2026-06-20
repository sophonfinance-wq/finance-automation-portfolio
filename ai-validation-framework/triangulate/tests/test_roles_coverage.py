"""Coverage tests for the pluggable roles: Reviewer backends, Auditor,
Specialist and Preparer.
"""

from __future__ import annotations

import pytest

from triangulate.generate import make_clean_workpaper, make_defective_workpaper
from triangulate.model import (
    AuthoritySource,
    Severity,
    Workpaper,
    WorkpaperCell,
)
from triangulate.roles.auditor import DeterministicAuditor
from triangulate.roles.preparer import DemoPreparer
from triangulate.roles.reviewer import (
    AdversarialReviewer,
    AnthropicReviewer,
    MockLLMReviewer,
    _authority_from,
    _has_process_language,
)
from triangulate.roles.specialist import DemoSpecialist


# --------------------------------------------------------------------------- #
# Helpers in reviewer.py                                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text, expected",
    [
        ("Signed Prior Year", AuthoritySource.SIGNED_PRIOR_YEAR),
        ("signed_prior_year", AuthoritySource.SIGNED_PRIOR_YEAR),
        ("MANAGEMENT INSTRUCTION", AuthoritySource.MANAGEMENT_INSTRUCTION),
        ("AI Assumption", AuthoritySource.AI_ASSUMPTION),
        ("Workbook Formula", AuthoritySource.WORKBOOK_FORMULA),
        (None, AuthoritySource.AI_ASSUMPTION),  # safe default
        ("", AuthoritySource.AI_ASSUMPTION),
        ("nonsense-label", AuthoritySource.AI_ASSUMPTION),  # unknown -> default
    ],
)
def test_authority_from_mapping(text, expected):
    assert _authority_from(text) is expected


@pytest.mark.parametrize(
    "text, flagged",
    [
        ("TODO: ask the LLM to recheck this", True),
        ("as the AI suggested, assume 12%", True),
        ("placeholder until Reviewer confirms", True),
        ("THE AI did it", True),
        ("Total Revenue", False),
        ("Estimated Tax", False),
        ("", False),
        (None, False),
    ],
)
def test_has_process_language(text, flagged):
    assert _has_process_language(text) is flagged


# --------------------------------------------------------------------------- #
# MockLLMReviewer                                                              #
# --------------------------------------------------------------------------- #
def test_mock_reviewer_flags_defective_codes():
    wp = make_defective_workpaper()
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    codes = {f.code for f in findings}
    assert "TIE_OUT_MISMATCH" in codes
    assert "UNSUPPORTED_AI_ASSUMPTION" in codes
    assert "PROCESS_LANGUAGE_LEAK" in codes


def test_mock_reviewer_defective_has_critical_tie_out():
    wp = make_defective_workpaper()
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    tie_outs = [f for f in findings if f.code == "TIE_OUT_MISMATCH"]
    assert tie_outs
    assert all(f.severity is Severity.CRITICAL for f in tie_outs)
    # Tie-out finding carries expected/actual diagnostic values.
    assert all(f.expected is not None and f.actual is not None for f in tie_outs)


def test_mock_reviewer_clean_has_nothing_high_or_critical():
    wp = make_clean_workpaper()
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    assert all(f.severity < Severity.HIGH for f in findings)


def test_mock_reviewer_is_deterministic():
    wp = make_defective_workpaper()
    a = [f.to_dict() for f in MockLLMReviewer().generate_findings(wp.frozen_snapshot())]
    b = [f.to_dict() for f in MockLLMReviewer().generate_findings(wp.frozen_snapshot())]
    assert a == b


def test_mock_reviewer_flags_unresolvable_formula():
    wp = Workpaper("E", "Ent", "P")
    # Formula references a cell that does not exist -> FORMULA_UNRESOLVABLE.
    wp.set_cell(WorkpaperCell("B5", "Total", 10.0, formula="=B2+B3"))
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    codes = {f.code for f in findings}
    assert "FORMULA_UNRESOLVABLE" in codes
    assert all(
        f.severity is Severity.HIGH
        for f in findings
        if f.code == "FORMULA_UNRESOLVABLE"
    )


def test_mock_reviewer_flags_hardcoded_ai_monetary_cell():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell(
        "B7", "Estimated Tax", 50_000.0, formula=None,
        source=AuthoritySource.AI_ASSUMPTION,
    ))
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    codes = {f.code for f in findings}
    assert "HARDCODED_NO_FORMULA" in codes
    assert "UNSUPPORTED_AI_ASSUMPTION" in codes


def test_mock_reviewer_small_rate_is_not_treated_as_monetary():
    # A small fractional rate (< 1000) must not trigger HARDCODED_NO_FORMULA.
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell(
        "B6", "Tax Rate", 0.18, formula=None,
        source=AuthoritySource.AI_ASSUMPTION,
    ))
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    assert "HARDCODED_NO_FORMULA" not in {f.code for f in findings}


def test_mock_reviewer_clean_workbook_cell_not_flagged_as_assumption():
    wp = make_clean_workpaper()
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    # Clean sample has no AI_ASSUMPTION cells -> no assumption findings.
    assert "UNSUPPORTED_AI_ASSUMPTION" not in {f.code for f in findings}


def test_mock_reviewer_flags_process_language_in_label():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B1", "TODO recheck this with the AI", 5.0))
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    leaks = [f for f in findings if f.code == "PROCESS_LANGUAGE_LEAK"]
    assert leaks
    assert all(f.severity is Severity.LOW for f in leaks)


def test_mock_reviewer_flags_process_language_in_notes_with_note_ref():
    wp = Workpaper("E", "Ent", "P")
    wp.notes.append("placeholder until Reviewer confirms")
    findings = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    note_leaks = [
        f for f in findings
        if f.code == "PROCESS_LANGUAGE_LEAK" and f.cell_ref.startswith("<note[")
    ]
    assert note_leaks


def test_mock_reviewer_backend_name_constant():
    assert MockLLMReviewer().backend_name == "MockLLMReviewer"


# --------------------------------------------------------------------------- #
# AdversarialReviewer wrapper                                                  #
# --------------------------------------------------------------------------- #
def test_adversarial_reviewer_defaults_to_mock_backend():
    reviewer = AdversarialReviewer()
    assert isinstance(reviewer.backend, MockLLMReviewer)
    assert reviewer.name == "Reviewer:MockLLMReviewer"


def test_adversarial_reviewer_name_reflects_backend():
    reviewer = AdversarialReviewer(AnthropicReviewer())
    assert reviewer.name == "Reviewer:AnthropicReviewer"


def test_adversarial_reviewer_delegates_to_backend():
    wp = make_defective_workpaper()
    direct = MockLLMReviewer().generate_findings(wp.frozen_snapshot())
    via = AdversarialReviewer().review(wp.frozen_snapshot())
    assert [f.to_dict() for f in direct] == [f.to_dict() for f in via]


# --------------------------------------------------------------------------- #
# AnthropicReviewer stub (no key, no network)                                 #
# --------------------------------------------------------------------------- #
def test_anthropic_reviewer_default_model():
    assert AnthropicReviewer().model == "claude-opus-4-8"


def test_anthropic_reviewer_custom_model():
    assert AnthropicReviewer(model="claude-sonnet-4-5").model == "claude-sonnet-4-5"


def test_anthropic_reviewer_raises_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reviewer = AnthropicReviewer()
    wp = make_clean_workpaper()
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        reviewer.generate_findings(wp.frozen_snapshot())


def test_anthropic_reviewer_system_prompt_has_guardrails():
    prompt = AnthropicReviewer().SYSTEM_PROMPT
    assert "Reviewer" in prompt
    assert "NEVER" in prompt
    assert "severity" in prompt.lower()


# --------------------------------------------------------------------------- #
# DeterministicAuditor                                                         #
# --------------------------------------------------------------------------- #
def test_auditor_passes_clean_workpaper():
    wp = make_clean_workpaper()
    findings = DeterministicAuditor().audit(wp.frozen_snapshot())
    # Clean workpaper ties out and has all required cells -> no audit findings.
    assert findings == []


def test_auditor_catches_tie_out_on_defective():
    wp = make_defective_workpaper()
    findings = DeterministicAuditor().audit(wp.frozen_snapshot())
    codes = {f.code for f in findings}
    assert "AUDIT_TIE_OUT_FAIL" in codes
    fails = [f for f in findings if f.code == "AUDIT_TIE_OUT_FAIL"]
    assert all(f.severity is Severity.CRITICAL for f in fails)


def test_auditor_flags_missing_required_cells():
    wp = Workpaper("E", "Ent", "P")  # has none of B5/B7/B8
    findings = DeterministicAuditor().audit(wp.frozen_snapshot())
    missing = {f.cell_ref for f in findings if f.code == "MISSING_REQUIRED_CELL"}
    assert missing == {"B5", "B7", "B8"}
    assert all(
        f.severity is Severity.HIGH
        for f in findings
        if f.code == "MISSING_REQUIRED_CELL"
    )


def test_auditor_flags_unresolvable_formula():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B5", "Total", 1.0, formula="=B2+B3"))  # B2/B3 absent
    wp.set_cell(WorkpaperCell("B7", "x", 1.0))
    wp.set_cell(WorkpaperCell("B8", "y", 1.0))
    findings = DeterministicAuditor().audit(wp.frozen_snapshot())
    assert "AUDIT_FORMULA_ERROR" in {f.code for f in findings}


def test_auditor_is_read_only():
    wp = make_defective_workpaper()
    before = wp.digest()
    DeterministicAuditor().audit(wp.frozen_snapshot())
    assert wp.digest() == before


def test_auditor_is_deterministic():
    wp = make_defective_workpaper()
    a = [f.to_dict() for f in DeterministicAuditor().audit(wp.frozen_snapshot())]
    b = [f.to_dict() for f in DeterministicAuditor().audit(wp.frozen_snapshot())]
    assert a == b


# --------------------------------------------------------------------------- #
# DemoSpecialist                                                               #
# --------------------------------------------------------------------------- #
def test_specialist_second_opinion_flags_out_of_band_rate():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B6", "Tax Rate", 0.50))  # above the 0.35 ceiling
    findings = DemoSpecialist().second_opinion(wp.frozen_snapshot())
    assert [f.code for f in findings] == ["RATE_OUT_OF_BAND"]
    assert findings[0].severity is Severity.MEDIUM


@pytest.mark.parametrize("rate", [0.10, 0.21, 0.35])
def test_specialist_in_band_rate_not_flagged(rate):
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B6", "Tax Rate", rate))
    assert DemoSpecialist().second_opinion(wp.frozen_snapshot()) == []


@pytest.mark.parametrize("rate", [0.05, 0.40, 0.99])
def test_specialist_out_of_band_rate_flagged(rate):
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B6", "Tax Rate", rate))
    findings = DemoSpecialist().second_opinion(wp.frozen_snapshot())
    assert [f.code for f in findings] == ["RATE_OUT_OF_BAND"]


def test_specialist_ignores_non_rate_labels():
    wp = Workpaper("E", "Ent", "P")
    # Fractional value but the label is not a "rate" -> ignored.
    wp.set_cell(WorkpaperCell("B1", "Margin Factor", 0.99))
    assert DemoSpecialist().second_opinion(wp.frozen_snapshot()) == []


def test_specialist_transform_normalises_float_noise():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B1", "v", 1.23456))
    log = DemoSpecialist().apply_transform(wp)
    assert wp.get("B1").value == 1.23
    assert any("normalised" in line for line in log)


def test_specialist_transform_noop_when_clean():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B1", "v", 2.50))
    log = DemoSpecialist().apply_transform(wp)
    assert log == ["No normalisation required; values already clean."]


def test_specialist_transform_ignores_int_values():
    wp = Workpaper("E", "Ent", "P")
    wp.set_cell(WorkpaperCell("B1", "v", 5))  # int, not float
    log = DemoSpecialist().apply_transform(wp)
    assert log == ["No normalisation required; values already clean."]
    assert wp.get("B1").value == 5


# --------------------------------------------------------------------------- #
# DemoPreparer                                                                 #
# --------------------------------------------------------------------------- #
def test_preparer_build_defective_returns_workpaper():
    wp = DemoPreparer(kind="defective").build()
    assert isinstance(wp, Workpaper)
    assert wp.get("B5") is not None


def test_preparer_build_clean_returns_workpaper():
    wp = DemoPreparer(kind="clean").build()
    assert wp.get("B5") is not None


def test_preparer_build_is_deterministic_for_same_seed():
    a = DemoPreparer(kind="defective", seed=7).build().to_dict()
    b = DemoPreparer(kind="defective", seed=7).build().to_dict()
    assert a == b


def test_preparer_memo_lists_ai_assumptions_for_defective():
    prep = DemoPreparer(kind="defective")
    wp = prep.build()
    memo = prep.builder_memo(wp)
    joined = "\n".join(memo)
    assert "Assumptions requiring verification" in joined
    assert prep.name in joined


def test_preparer_memo_notes_no_assumptions_for_clean():
    prep = DemoPreparer(kind="clean")
    wp = prep.build()
    memo = prep.builder_memo(wp)
    assert any("No AI-generated assumptions" in line for line in memo)


def test_preparer_memo_reports_cell_count():
    prep = DemoPreparer(kind="clean")
    wp = prep.build()
    memo = prep.builder_memo(wp)
    assert any(f"Cells prepared: {len(wp.cells)}" in line for line in memo)
