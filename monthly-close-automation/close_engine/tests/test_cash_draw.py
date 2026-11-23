"""Controls for the fictional validation-only construction-draw component."""

from dataclasses import replace

import pytest

from close_engine.cash_draw import (
    CashDrawValidator,
    CategoryTotal,
    DependencyEvidence,
    DetailTotal,
    DrawTransaction,
    demo_inputs,
)


CURRENT_PERIOD = "2026-06"


def run(
    transactions=None,
    details=None,
    categories=None,
    current=None,
    prior="demo",
    dependencies=(),
    original_snapshot=None,
    original_transactions=(),
):
    demo_transactions, demo_details, demo_categories, demo_current, demo_prior = demo_inputs()
    return CashDrawValidator(
        CURRENT_PERIOD,
        demo_transactions if transactions is None else transactions,
        demo_details if details is None else details,
        demo_categories if categories is None else categories,
        demo_current if current is None else current,
        demo_prior if prior == "demo" else prior,
        dependencies,
        original_snapshot,
        original_transactions,
    ).run()


def codes(result):
    return {finding.code for finding in result.findings}


def test_clean_pair_rederives_draw_and_never_posts_or_submits():
    result = run()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.transaction_count == result.detail_count == result.category_count == 2
    assert result.combined_detail_cents == result.current_draw_cents == 200_000
    assert result.period_interest_cents == 5_000
    assert result.period_lender_funding_cents == 205_000
    assert result.revision_draw_delta_cents is None
    assert "submit nothing and post nothing" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.lender_submissions == ()
    assert result.posting_actions == result.import_payloads == ()


@pytest.mark.parametrize(
    "period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""]
)
def test_period_must_be_canonical(period):
    transactions, details, categories, current, prior = demo_inputs()
    with pytest.raises(ValueError, match="current_period must be canonical YYYY-MM"):
        CashDrawValidator(period, transactions, details, categories, current, prior)


def test_missing_prior_is_visible_review_gate_not_mechanical_error():
    result = run(prior=None)
    assert result.mechanical_clean
    assert "PRIOR_COMPARATOR_NOT_PROVIDED" in codes(result)
    assert result.period_interest_cents is None
    assert result.period_lender_funding_cents is None


def test_transaction_amount_equation_is_rederived():
    transactions, *_ = demo_inputs()
    changed = (replace(transactions[0], draw_cents=120_001), transactions[1])
    result = run(transactions=changed)
    assert "DRAW_AMOUNT_OUT_OF_TIE" in codes(result)
    assert "DETAIL_TO_DRAW_OUT_OF_TIE" in codes(result)


@pytest.mark.parametrize("bad_amount", [1.25, "125", True, None])
def test_transaction_amounts_require_integer_cents(bad_amount):
    transactions, *_ = demo_inputs()
    changed = (replace(transactions[0], amount_cents=bad_amount), transactions[1])
    result = run(transactions=changed)
    assert "AMOUNT_INVALID" in codes(result)


def test_accounting_date_must_match_target_period():
    transactions, *_ = demo_inputs()
    changed = (replace(transactions[0], accounting_date="2026-05-31"), transactions[1])
    assert "ACCOUNTING_DATE_OUTSIDE_PERIOD" in codes(run(transactions=changed))


@pytest.mark.parametrize("bad_date", ["2026-02-30", "06/30/2026", "2026-6-30", ""])
def test_dates_must_be_real_and_canonical(bad_date):
    transactions, *_ = demo_inputs()
    changed = (replace(transactions[0], transaction_date=bad_date), transactions[1])
    assert "DATE_INVALID" in codes(run(transactions=changed))


def test_cost_code_and_required_mapping_text_are_controlled():
    transactions, *_ = demo_inputs()
    changed = (replace(transactions[0], cost_code="100", bank_category=" site "), transactions[1])
    result = run(transactions=changed)
    assert {"COST_CODE_INVALID", "IDENTIFIER_INVALID"} <= codes(result)


def test_duplicate_transaction_id_and_identity_are_both_detected():
    transactions, *_ = demo_inputs()
    duplicate = replace(transactions[0])
    result = run(transactions=(transactions[0], duplicate))
    assert {"TRANSACTION_ID_DUPLICATE", "TRANSACTION_IDENTITY_DUPLICATE"} <= codes(result)


def test_ap_rows_require_vendor_and_invoice_support():
    transactions, *_ = demo_inputs()
    changed = (replace(transactions[0], transaction_type="AP cost"), transactions[1])
    assert "AP_SUPPORT_INCOMPLETE" in codes(run(transactions=changed))


def test_detail_totals_detect_mismatch_missing_unknown_and_duplicate():
    controls = (
        DetailTotal("Land Detail", 119_999),
        DetailTotal("Land Detail", 120_000),
        DetailTotal("Unknown Detail", 1),
    )
    result = run(details=controls)
    assert {
        "DETAIL_TOTAL_OUT_OF_TIE",
        "DETAIL_TOTAL_DUPLICATE",
        "DETAIL_TOTAL_UNKNOWN",
        "DETAIL_TOTAL_MISSING",
    } <= codes(result)


def test_category_totals_detect_invalid_mismatch_and_missing():
    controls = (
        CategoryTotal("Site Construction", 119_999),
        CategoryTotal("", 80_000),
    )
    result = run(categories=controls)
    assert {
        "CATEGORY_TOTAL_OUT_OF_TIE",
        "CATEGORY_TOTAL_INVALID",
        "CATEGORY_TOTAL_MISSING",
    } <= codes(result)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("total_loan_equity_cents", 1_705_001, "LOAN_EQUITY_OUT_OF_TIE"),
        ("total_debt_equity_cents", 1_705_001, "TOTAL_DEBT_EQUITY_OUT_OF_TIE"),
        ("net_job_cost_to_date_cents", 1_705_001, "NET_JOB_COST_OUT_OF_TIE"),
        ("variance_cents", 1, "VARIANCE_OUT_OF_TIE"),
        ("project_report_total_cents", 1_704_999, "PROJECT_REPORT_OUT_OF_TIE"),
    ],
)
def test_current_reconciliation_equations_are_independently_rederived(field, value, code):
    *_, current, _prior = demo_inputs()
    assert code in codes(run(current=replace(current, **{field: value})))


def test_current_snapshot_period_and_draw_total_must_tie():
    *_, current, _prior = demo_inputs()
    result = run(current=replace(current, period="2026-05", current_draw_cents=199_999))
    assert {"SNAPSHOT_PERIOD_MISMATCH", "DETAIL_TO_DRAW_OUT_OF_TIE"} <= codes(result)


@pytest.mark.parametrize("value", [1.5, "200000", True, None])
def test_snapshot_money_requires_integer_cents(value):
    *_, current, _prior = demo_inputs()
    result = run(current=replace(current, current_draw_cents=value))
    assert "SNAPSHOT_AMOUNT_INVALID" in codes(result)
    assert result.current_draw_cents is None


def test_prior_period_draw_number_and_funding_continuity_are_controlled():
    *_, prior = demo_inputs()
    changed = replace(
        prior,
        period="2026-04",
        draw_number=6,
        cumulative_lender_draws_cents=499_999,
    )
    result = run(prior=changed)
    assert {
        "PRIOR_PERIOD_MISMATCH",
        "DRAW_NUMBER_DISCONTINUITY",
        "CUMULATIVE_FUNDING_CONTINUITY_FAILED",
        "LOAN_EQUITY_CONTINUITY_FAILED",
        "TOTAL_DEBT_EQUITY_CONTINUITY_FAILED",
    } <= codes(result)


def test_external_broken_and_cached_formula_dependencies_are_blockers():
    result = run(
        dependencies=(
            DependencyEvidence("Job cost feed", "[other.xlsx]Sheet1!A1", "#REF!"),
            DependencyEvidence("Cash feed", "https://example.invalid/source", 100),
        )
    )
    assert {"DEPENDENCY_EXTERNAL_OR_BROKEN", "DEPENDENCY_CACHED_ERROR"} <= codes(result)


def test_dependency_keys_are_trimmed_and_unique():
    result = run(
        dependencies=(
            DependencyEvidence("Mapping", "Local!A1"),
            DependencyEvidence("mapping", "Local!B1"),
            DependencyEvidence(" bad ", "Local!C1"),
        )
    )
    assert {"DEPENDENCY_DUPLICATE", "DEPENDENCY_INVALID"} <= codes(result)


def test_same_period_revision_delta_ties_and_requires_approval():
    transactions, _details, _categories, current, _prior = demo_inputs()
    original_transactions = (
        replace(transactions[0], amount_cents=100_000, draw_cents=95_000),
        transactions[1],
    )
    original_snapshot = replace(current, current_draw_cents=175_000)
    result = run(
        original_snapshot=original_snapshot,
        original_transactions=original_transactions,
    )
    assert result.revision_draw_delta_cents == 25_000
    assert "REVISION_APPROVAL_REQUIRED" in codes(result)
    assert "REVISION_DELTA_OUT_OF_TIE" not in codes(result)


def test_revision_delta_mismatch_and_period_change_are_blockers():
    transactions, _details, _categories, current, _prior = demo_inputs()
    original_transactions = (
        replace(transactions[0], amount_cents=100_000, draw_cents=95_000),
        transactions[1],
    )
    original_snapshot = replace(current, period="2026-05", current_draw_cents=170_000)
    result = run(
        original_snapshot=original_snapshot,
        original_transactions=original_transactions,
    )
    assert {"REVISION_PERIOD_MISMATCH", "REVISION_DELTA_OUT_OF_TIE"} <= codes(result)


def test_revision_comparator_must_be_complete():
    *_, current, _prior = demo_inputs()
    assert "REVISION_COMPARATOR_INCOMPLETE" in codes(run(original_snapshot=current))


def test_empty_input_is_explicit_and_does_not_crash():
    result = run(transactions=(), details=(), categories=())
    assert "DETAIL_EMPTY" in codes(result)
    assert "DETAIL_TO_DRAW_OUT_OF_TIE" in codes(result)
    assert result.transaction_count == result.combined_detail_cents == 0


def test_validator_does_not_mutate_input_sequences():
    transactions, details, categories, current, prior = demo_inputs()
    transaction_list = list(transactions)
    detail_list = list(details)
    category_list = list(categories)
    before = (transaction_list.copy(), detail_list.copy(), category_list.copy())
    CashDrawValidator(
        CURRENT_PERIOD,
        transaction_list,
        detail_list,
        category_list,
        current,
        prior,
    ).run()
    assert (transaction_list, detail_list, category_list) == before


def test_public_demo_contains_only_generic_fictional_identifiers():
    transactions, details, categories, _current, _prior = demo_inputs()
    text = repr((transactions, details, categories)).casefold()
    assert "demo" in text
    assert "fictional" in text
