"""Semantics of the individual controls, exercised directly rather than via the corpus.

The corpus proves each control fires on one planted shape. These tests pin the
*boundaries*: the point at which a difference becomes material, the difference
between a reclassification and a change, what happens when an artifact is absent
rather than wrong, and the cases where a control must deliberately stand down
instead of inventing an input.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from baseline_engine.budget import (
    budget_lines,
    budget_total,
    detect_reclassifications,
    milestone_dates,
    pair_lines,
    parse_iso,
    phase_totals,
)
from baseline_engine.engine import analyze_document
from baseline_engine.generate import DOC_BUDGET_VERSION, baseline
from baseline_engine.model import (
    DOC_AGREEMENT,
    DOC_DERIVED_SCHEDULE,
    DOC_FUNDING_REGISTER,
    DOC_MILESTONE_SET,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _write(tmp_path: Path, data: dict[str, Any], name: str = "case") -> Path:
    data = dict(data)
    data["file_id"] = name
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return p


def _fired(path: Path) -> dict[str, Status]:
    report = analyze_document(path)
    out: dict[str, Status] = {}
    for f in report.findings:
        if f.status is not Status.PASS:
            out[f.rule] = f.status
    return out


def _ver(f: dict[str, Any], doc_id: str) -> dict[str, Any]:
    return next(
        d
        for d in f["documents"]
        if d.get("doc_type") == DOC_BUDGET_VERSION and d.get("document_id") == doc_id
    )


def _doc(f: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(d for d in f["documents"] if d.get("doc_type") == doc_type)


def _line(version: dict[str, Any], category: str) -> dict[str, Any]:
    return next(r for r in version["lines"] if r.get("category") == category)


# --------------------------------------------------------------------------- #
# Kernel: pairing and reclassification
# --------------------------------------------------------------------------- #
def test_pair_lines_reports_three_disjoint_groups() -> None:
    left = {"a": 1, "b": 2, "c": 3}
    right = {"b": 2, "c": 9, "d": 4}
    paired, left_only, right_only = pair_lines(left, right)
    assert paired == ["b", "c"]
    assert left_only == ["a"]
    assert right_only == ["d"]
    assert not (set(paired) & set(left_only) & set(right_only))


def test_pair_lines_is_symmetric_in_shape() -> None:
    left, right = {"a": 1}, {"b": 2}
    p1, lo1, ro1 = pair_lines(left, right)
    p2, lo2, ro2 = pair_lines(right, left)
    assert p1 == p2 == []
    assert lo1 == ro2 and ro1 == lo2


def test_reclassification_requires_an_unchanged_total() -> None:
    """Equal and opposite moves are a re-carve only when the total holds."""
    left = {"a": 100, "b": 100}
    right = {"a": 60, "b": 140}
    assert detect_reclassifications(left, right) == [("a", "b", 40)]

    # Same shape of movement, but the total moved: that is a change, not a re-carve.
    right_changed = {"a": 60, "b": 150}
    assert detect_reclassifications(left, right_changed) == []


def test_reclassification_ignores_unmoved_lines() -> None:
    left = {"a": 100, "b": 100, "c": 500}
    right = {"a": 60, "b": 140, "c": 500}
    assert detect_reclassifications(left, right) == [("a", "b", 40)]


def test_reclassification_is_empty_when_nothing_moved() -> None:
    same = {"a": 1, "b": 2}
    assert detect_reclassifications(same, dict(same)) == []


def test_budget_total_sums_duplicated_categories() -> None:
    """A repeated category is summed, so the lines and the total cannot disagree."""
    version = {
        "document_id": "V",
        "lines": [
            {"category": "Land", "amount_cents": 100},
            {"category": "Land", "amount_cents": 250},
        ],
    }
    assert budget_lines(version) == {"Land": 350}
    assert budget_total(version) == 350


def test_phase_totals_exclude_a_line_with_no_phase() -> None:
    version = {
        "document_id": "V",
        "lines": [
            {"category": "a", "phase": "pre_conversion", "amount_cents": 10},
            {"category": "b", "amount_cents": 90},
        ],
    }
    assert phase_totals(version) == {"pre_conversion": 10}
    assert budget_total(version) == 100


def test_parse_iso_returns_none_rather_than_raising() -> None:
    assert parse_iso("2031-06-30") is not None
    assert parse_iso("30/06/2031") is None
    assert parse_iso(None) is None
    assert parse_iso(20310630) is None


def test_milestone_dates_distinguishes_absent_from_undated() -> None:
    ms = {
        "milestones": [
            {"milestone_id": "start", "date": "2032-06-01"},
            {"milestone_id": "end", "date": None},
        ]
    }
    dates = milestone_dates(ms)
    assert dates["start"] is not None
    assert dates["end"] is None
    assert "missing" not in dates


# --------------------------------------------------------------------------- #
# Materiality is a grading tool, never a detection tool
# --------------------------------------------------------------------------- #
def test_difference_at_the_threshold_is_material(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    threshold = f["materiality_cents"]
    v = _ver(f, "BV-WORK")
    _line(v, "Consultants")["amount_cents"] += threshold
    v["stated_total_cents"] = budget_total(v)
    fired = _fired(_write(tmp_path, f, "at_threshold"))
    assert fired.get("lin_values_agree") is Status.FAIL


def test_difference_one_cent_below_the_threshold_is_a_flag(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    threshold = f["materiality_cents"]
    v = _ver(f, "BV-WORK")
    _line(v, "Consultants")["amount_cents"] += threshold - 1
    v["stated_total_cents"] = budget_total(v)
    fired = _fired(_write(tmp_path, f, "below_threshold"))
    assert "lin_values_agree" not in fired
    assert fired.get("lin_immaterial_drift_review") is Status.FLAG


def test_a_sub_threshold_difference_is_never_silent(tmp_path: Path) -> None:
    """The threshold grades a difference; it must not suppress one."""
    f = baseline("Brightwater Commons")
    v = _ver(f, "BV-SUMM")
    _line(v, "Permits")["amount_cents"] += 1
    v["stated_total_cents"] = budget_total(v)
    fired = _fired(_write(tmp_path, f, "one_cent"))
    assert "lin_immaterial_drift_review" in fired


# --------------------------------------------------------------------------- #
# Stand-down behaviour
# --------------------------------------------------------------------------- #
def test_controls_stand_down_when_the_baseline_is_ambiguous(tmp_path: Path) -> None:
    """With two baselines, comparison controls report nothing rather than guess."""
    f = baseline("Copperfield Yards")
    _ver(f, "BV-WORK")["role"] = "contractual_baseline"
    fired = _fired(_write(tmp_path, f, "two_baselines"))
    assert fired.get("ver_single_baseline") is Status.FAIL
    assert "lin_values_agree" not in fired
    assert "lin_categories_reconcile" not in fired


def test_date_controls_stand_down_when_the_period_is_unreadable(tmp_path: Path) -> None:
    f = baseline("Copperfield Yards")
    f["period_end"] = "not-a-date"
    fired = _fired(_write(tmp_path, f, "bad_period"))
    assert fired.get("set_complete") is Status.FAIL
    assert "ver_prepared_within_period" not in fired
    assert "stl_cost_through_current" not in fired


def test_absent_artifact_is_reported_once_by_set_complete(tmp_path: Path) -> None:
    f = baseline("Dunmore Flats")
    f["documents"] = [d for d in f["documents"] if d.get("doc_type") != DOC_MILESTONE_SET]
    report = analyze_document(_write(tmp_path, f, "no_milestones"))
    complaints = [
        f_ for f_ in report.findings if f_.status is not Status.PASS
    ]
    rules = {c.rule for c in complaints}
    assert "set_complete" in rules
    # Milestone-dependent controls must not each raise their own absence complaint.
    assert "drv_milestones_populated" not in rules


# --------------------------------------------------------------------------- #
# Individual control boundaries
# --------------------------------------------------------------------------- #
def test_baseline_dated_on_the_execution_date_is_accepted(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    agreement = _doc(f, DOC_AGREEMENT)
    _ver(f, "BV-BASE")["prepared_date"] = agreement["executed_date"]
    fired = _fired(_write(tmp_path, f, "same_day"))
    assert "ver_baseline_postdates_agreement" not in fired


def test_baseline_dated_one_day_early_is_rejected(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    _ver(f, "BV-BASE")["prepared_date"] = "2030-11-17"
    fired = _fired(_write(tmp_path, f, "day_early"))
    assert fired.get("ver_baseline_postdates_agreement") is Status.FAIL


def test_cost_through_exactly_on_the_stale_boundary_is_accepted(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    f["stale_days"] = 30
    _ver(f, "BV-WORK")["cost_through_date"] = "2031-05-31"  # 30 days before 06-30
    fired = _fired(_write(tmp_path, f, "on_boundary"))
    assert "stl_cost_through_current" not in fired


def test_cost_through_one_day_past_the_boundary_is_rejected(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    f["stale_days"] = 30
    _ver(f, "BV-WORK")["cost_through_date"] = "2031-05-30"
    fired = _fired(_write(tmp_path, f, "past_boundary"))
    assert fired.get("stl_cost_through_current") is Status.FAIL


def test_cost_through_beyond_the_period_end_is_rejected(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    _ver(f, "BV-WORK")["cost_through_date"] = "2031-07-31"
    fired = _fired(_write(tmp_path, f, "future_cost"))
    assert fired.get("stl_cost_through_current") is Status.FAIL


def test_change_backed_by_the_wrong_amount_is_rejected(tmp_path: Path) -> None:
    """Paperwork that exists but is for a different figure is the harder case."""
    f = baseline("Alderpoint Terraces")
    row = _line(_ver(f, "BV-BILL"), "Consultants")
    row["current_changes_cents"] += 1
    row["approved_cents"] -= 1
    fired = _fired(_write(tmp_path, f, "wrong_amount"))
    assert fired.get("amd_changes_trace_to_log") is Status.FAIL


def test_split_is_checked_against_the_declared_phase(tmp_path: Path) -> None:
    """The post-conversion ratio is wrong while the deal is pre-conversion."""
    f = baseline("Alderpoint Terraces")
    for m in _doc(f, DOC_FUNDING_REGISTER)["members"]:
        m["split_bps"] = 9000 if m["member_id"] == "investor" else 1000
    fired = _fired(_write(tmp_path, f, "wrong_phase_split"))
    assert fired.get("eqt_split_matches_phase") is Status.FAIL

    # The same ratio is correct once the agreement declares the later phase.
    f2 = baseline("Alderpoint Terraces")
    _doc(f2, DOC_AGREEMENT)["phase"] = "post_conversion"
    for m in _doc(f2, DOC_FUNDING_REGISTER)["members"]:
        m["split_bps"] = 9000 if m["member_id"] == "investor" else 1000
    assert "eqt_split_matches_phase" not in _fired(_write(tmp_path, f2, "right_phase_split"))


def test_commitment_equal_to_the_cap_is_accepted(tmp_path: Path) -> None:
    f = baseline("Dunmore Flats")
    for m in _doc(f, DOC_FUNDING_REGISTER)["members"]:
        m["cap_cents"] = m["commitment_cents"]
    assert "eqt_contributed_within_commitment" not in _fired(_write(tmp_path, f, "cap_eq"))


def test_schedule_with_a_dateless_input_is_rejected(tmp_path: Path) -> None:
    f = baseline("Dunmore Flats")
    for row in _doc(f, DOC_MILESTONE_SET)["milestones"]:
        if row["milestone_id"] == "construction_start":
            row["date"] = None
    fired = _fired(_write(tmp_path, f, "dateless_input"))
    assert fired.get("drv_milestones_populated") is Status.FAIL


def test_undated_milestone_that_no_schedule_uses_is_not_a_failure(tmp_path: Path) -> None:
    """Only inputs a schedule actually depends on are load-bearing."""
    f = baseline("Dunmore Flats")
    for row in _doc(f, DOC_MILESTONE_SET)["milestones"]:
        if row["milestone_id"] == "first_delivery":
            row["date"] = None
    assert "drv_milestones_populated" not in _fired(_write(tmp_path, f, "unused_undated"))


def test_locked_line_unchanged_in_every_copy_passes(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    assert "amd_locked_lines_unchanged" not in _fired(_write(tmp_path, f, "locked_ok"))


def test_non_integer_amount_is_reported_not_coerced(tmp_path: Path) -> None:
    f = baseline("Brightwater Commons")
    _line(_ver(f, "BV-WORK"), "Marketing")["amount_cents"] = 1.5
    report = analyze_document(_write(tmp_path, f, "float_amount"))
    messages = [x.message for x in report.findings if x.status is not Status.PASS]
    assert any("AMOUNT_INVALID" in m for m in messages)


def test_schedule_periods_must_match_the_instalment_count(tmp_path: Path) -> None:
    f = baseline("Copperfield Yards")
    s = _doc(f, DOC_DERIVED_SCHEDULE)
    s["instalments_cents"] = s["instalments_cents"][:-1]
    fired = _fired(_write(tmp_path, f, "short_schedule"))
    assert fired.get("drv_instalments_conserve") is Status.FAIL


@pytest.mark.parametrize("bad_state", ["draft", "", "APPROVED"])
def test_unknown_amendment_state_is_rejected(tmp_path: Path, bad_state: str) -> None:
    from baseline_engine.model import DOC_AMENDMENT_LOG

    f = baseline("Copperfield Yards")
    _doc(f, DOC_AMENDMENT_LOG)["amendments"][0]["state"] = bad_state
    fired = _fired(_write(tmp_path, f, f"state_{bad_state or 'blank'}"))
    assert fired.get("amd_pending_not_billed") is Status.FAIL
