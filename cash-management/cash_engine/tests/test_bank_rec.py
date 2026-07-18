"""Controls for the fictional validation-only bank-reconciliation bridge."""

from dataclasses import replace

import pytest

from cash_engine.bank_rec import (
    BankReconciliation,
    BankReconciliationValidator,
    demo_reconciliations,
)

PERIOD = "2026-06"


def run(recs=None):
    return BankReconciliationValidator(
        PERIOD, demo_reconciliations() if recs is None else recs
    ).run()


def codes(result):
    return {finding.code for finding in result.findings}


def test_clean_set_reties_both_sides_and_stays_validation_only():
    result = run()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.account_count == 2
    assert result.tied_count == 2
    assert result.out_of_tie_count == 0
    assert "manual posting" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_period_must_be_canonical(period):
    with pytest.raises(ValueError, match="period must be canonical YYYY-MM"):
        BankReconciliationValidator(period, demo_reconciliations())


def test_bridge_is_independently_rederived():
    recs = demo_reconciliations()
    changed = (replace(recs[0], bank_ending_cents=1_050_001, displayed_adjusted_cents=None), recs[1])
    result = run(changed)
    assert "RECONCILIATION_OUT_OF_TIE" in codes(result)
    assert result.out_of_tie_count == 1
    assert result.tied_count == 1


def test_displayed_adjusted_must_tie_to_rederived():
    recs = demo_reconciliations()
    changed = (replace(recs[0], displayed_adjusted_cents=999_999), recs[1])
    assert "DISPLAYED_ADJUSTED_OUT_OF_TIE" in codes(run(changed))


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("deposits_in_transit_cents", "DEPOSITS_IN_TRANSIT_NEGATIVE"),
        ("outstanding_checks_cents", "OUTSTANDING_CHECKS_NEGATIVE"),
        ("bank_charges_cents", "BANK_CHARGES_NEGATIVE"),
        ("interest_earned_cents", "INTEREST_EARNED_NEGATIVE"),
    ],
)
def test_magnitudes_cannot_be_negative(field, code):
    recs = demo_reconciliations()
    changed = (replace(recs[0], **{field: -1, "displayed_adjusted_cents": None}), recs[1])
    assert code in codes(run(changed))


@pytest.mark.parametrize(
    ("field", "code"),
    [("bank_error_cents", "BANK_ERROR_REVIEW_REQUIRED"), ("book_error_cents", "BOOK_ERROR_REVIEW_REQUIRED")],
)
def test_error_plugs_are_review_gated_and_never_drafted(field, code):
    recs = demo_reconciliations()
    # Keep the bridge tied by moving the same plug onto both sides is not needed:
    # a bank plug ties book via displayed=None; assert the review flag + no drafting.
    changed = (replace(recs[0], **{field: 12_500, "displayed_adjusted_cents": None}), recs[1])
    result = run(changed)
    assert code in codes(result)
    assert result.verdict == "NEEDS REVIEW"
    assert result.journal_entries == ()


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_amounts_are_rejected_without_coercion(value):
    recs = demo_reconciliations()
    changed = (replace(recs[0], bank_ending_cents=value), recs[1])
    assert "AMOUNT_INVALID" in codes(run(changed))


def test_displayed_adjusted_type_is_strict():
    recs = demo_reconciliations()
    changed = (replace(recs[0], displayed_adjusted_cents=1.5), recs[1])
    assert "DISPLAYED_ADJUSTED_INVALID" in codes(run(changed))


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("entity", " Cedar Demo LLC", "ENTITY_INVALID"),
        ("account", "cash", "ACCOUNT_INVALID"),
        ("bank_name", "", "BANK_NAME_INVALID"),
    ],
)
def test_semantic_identifiers_are_strict(field, value, expected):
    recs = demo_reconciliations()
    changed = (replace(recs[0], **{field: value}), recs[1])
    assert expected in codes(run(changed))


def test_duplicate_entity_account_keys_are_blocked_case_insensitively():
    recs = demo_reconciliations()
    changed = (recs[0], replace(recs[1], account=recs[0].account.lower()))
    assert "ACCOUNT_DUPLICATE" in codes(run(changed))


def test_empty_set_is_not_a_clean_noop():
    assert "RECONCILIATION_SET_EMPTY" in codes(run(()))


def test_validator_does_not_mutate_input_sequence():
    recs = list(demo_reconciliations())
    before = tuple(recs)
    run(recs)
    assert tuple(recs) == before
