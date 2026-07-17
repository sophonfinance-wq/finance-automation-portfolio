"""Controls for the fictional validation-only budget-variance component."""

from dataclasses import replace

import pytest

from close_engine.budget_variance import (
    BudgetRow,
    BudgetTotals,
    BudgetVarianceValidator,
    demo_rows,
)


PERIOD = "2026-06"


def run(rows=None, totals=None):
    return BudgetVarianceValidator(PERIOD, demo_rows() if rows is None else rows, totals).run()


def codes(result):
    return {finding.code for finding in result.findings}


def clean_totals():
    return BudgetTotals(1_800_000, 850_000, 950_000, 25_000, 1_825_000, 975_000)


def test_clean_fictional_budget_rederives_and_stays_review_gated():
    result = run(totals=clean_totals())
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.rederived_totals == clean_totals()
    assert "project-manager" in " | ".join(result.manual_gates)
    assert not result.posting_authorized
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_period_must_be_canonical(period):
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        BudgetVarianceValidator(period, [])


def test_current_budget_equation_is_independent():
    rows = list(demo_rows())
    rows[0] = replace(rows[0], current_budget_cents=1_100_001)
    assert "CURRENT_BUDGET_OUT_OF_TIE" in codes(run(rows))


def test_current_ctc_equation_is_independent():
    rows = list(demo_rows())
    rows[0] = replace(rows[0], current_ctc_cents=499_999)
    assert "CURRENT_CTC_OUT_OF_TIE" in codes(run(rows))


def test_revised_budget_equation_is_independent():
    rows = list(demo_rows())
    rows[0] = replace(rows[0], revised_budget_cents=1_150_001)
    assert "REVISED_BUDGET_OUT_OF_TIE" in codes(run(rows))


def test_revised_ctc_equation_is_independent():
    rows = list(demo_rows())
    rows[0] = replace(rows[0], revised_ctc_cents=550_001)
    assert "REVISED_CTC_OUT_OF_TIE" in codes(run(rows))


def test_negative_ctc_requires_visible_overrun_flag():
    rows = list(demo_rows())
    rows[0] = replace(
        rows[0], period_update_cents=-600_000, revised_budget_cents=500_000, revised_ctc_cents=-100_000
    )
    result = run(rows)
    assert {"NEGATIVE_REVISED_CTC", "OVERRUN_FLAG_MISSING"} <= codes(result)


def test_negative_ctc_with_flag_still_requires_review():
    rows = list(demo_rows())
    rows[0] = replace(
        rows[0], period_update_cents=-600_000, revised_budget_cents=500_000,
        revised_ctc_cents=-100_000, overrun_flag="ERR"
    )
    result = run(rows)
    assert "NEGATIVE_REVISED_CTC" in codes(result)
    assert "OVERRUN_FLAG_MISSING" not in codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_stale_overrun_flag_is_detected():
    rows = list(demo_rows())
    rows[0] = replace(rows[0], overrun_flag="OVERRUN")
    assert "OVERRUN_FLAG_STALE" in codes(run(rows))


def test_duplicate_cost_code_is_detected_case_insensitively():
    rows = list(demo_rows())
    rows[1] = replace(rows[1], cost_code="10-100")
    assert "COST_CODE_DUPLICATE" in codes(run(rows))


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_amounts_are_rejected_without_coercion(value):
    rows = list(demo_rows())
    rows[0] = replace(rows[0], costs_to_date_cents=value)
    result = run(rows)
    assert "AMOUNT_INVALID" in codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_project_total_difference_is_named():
    totals = replace(clean_totals(), revised_budget_cents=1_825_001)
    finding = next(f for f in run(totals=totals).findings if f.code == "PROJECT_TOTAL_OUT_OF_TIE")
    assert "revised_budget_cents" in finding.detail


def test_empty_detail_is_not_a_clean_noop():
    result = run([])
    assert "BUDGET_EMPTY" in codes(result)
    assert result.rederived_totals is None


def test_validator_does_not_mutate_input_rows():
    rows = list(demo_rows())
    before = tuple(rows)
    run(rows, clean_totals())
    assert tuple(rows) == before
