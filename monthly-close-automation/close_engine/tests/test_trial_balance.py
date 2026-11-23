"""Controls for the fictional validation-only trial-balance component."""

from dataclasses import replace

import pytest

from close_engine.trial_balance import (
    DependencyEvidence,
    EntityControl,
    TrialBalanceContinuityValidator,
    TrialBalanceRow,
    demo_pair,
)


CURRENT_PERIOD = "2026-06"
PRIOR_PERIOD = "2026-05"


def run(current=None, prior=None, controls=None, dependencies=None):
    demo_current, demo_prior = demo_pair()
    return TrialBalanceContinuityValidator(
        CURRENT_PERIOD,
        demo_current if current is None else current,
        PRIOR_PERIOD,
        demo_prior if prior is None else prior,
        () if controls is None else controls,
        () if dependencies is None else dependencies,
    ).run()


def codes(result):
    return {finding.code for finding in result.findings}


def test_clean_pair_rederives_continuity_and_remains_validation_only():
    result = run(controls=(EntityControl("Cedar Demo LLC", 0),))
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.common_account_count == 2
    assert result.added_account_count == result.removed_account_count == 0
    assert result.continuity_failure_count == 0
    assert "manual posting" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_current_period_must_be_canonical(period):
    current, prior = demo_pair()
    with pytest.raises(ValueError, match="current_period must be canonical YYYY-MM"):
        TrialBalanceContinuityValidator(period, current, PRIOR_PERIOD, prior)


@pytest.mark.parametrize("period", ["2026-5", "05-2026", "2026-00", "2026-13", ""])
def test_prior_period_must_be_canonical(period):
    current, prior = demo_pair()
    with pytest.raises(ValueError, match="prior_period must be canonical YYYY-MM"):
        TrialBalanceContinuityValidator(CURRENT_PERIOD, current, period, prior)


@pytest.mark.parametrize("period", ["2026-06", "2026-07"])
def test_prior_period_must_precede_current(period):
    current, prior = demo_pair()
    with pytest.raises(ValueError, match="prior_period must precede"):
        TrialBalanceContinuityValidator(CURRENT_PERIOD, current, period, prior)


def test_current_line_rollforward_is_independently_rederived():
    current, _ = demo_pair()
    changed = (replace(current[0], closing_cents=1_075_001), current[1])
    assert "CURRENT_LINE_ROLLFORWARD_OUT_OF_TIE" in codes(run(current=changed))


def test_prior_line_rollforward_is_independently_rederived():
    _, prior = demo_pair()
    changed = (replace(prior[0], closing_cents=1_000_001), prior[1])
    assert "PRIOR_LINE_ROLLFORWARD_OUT_OF_TIE" in codes(run(prior=changed))


def test_current_opening_must_equal_prior_closing():
    current, _ = demo_pair()
    changed = (replace(current[0], opening_cents=999_999, activity_cents=75_001), current[1])
    result = run(current=changed)
    assert "PRIOR_CLOSE_CURRENT_OPEN_OUT_OF_TIE" in codes(result)
    assert result.continuity_failure_count == 1


def test_population_change_is_named_and_counted():
    current, _ = demo_pair()
    changed = (replace(current[0], account="AST-101"), current[1])
    result = run(current=changed)
    assert "ACCOUNT_POPULATION_CHANGED" in codes(result)
    assert result.added_account_count == result.removed_account_count == 1


@pytest.mark.parametrize("which", ["current", "prior"])
def test_duplicate_entity_account_keys_are_blocked_case_insensitively(which):
    current, prior = demo_pair()
    source = list(current if which == "current" else prior)
    source[1] = replace(source[1], account=source[0].account.lower())
    result = run(current=source) if which == "current" else run(prior=source)
    assert f"{which.upper()}_ACCOUNT_DUPLICATE" in codes(result)


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_amounts_are_rejected_without_coercion(value):
    current, _ = demo_pair()
    changed = (replace(current[0], activity_cents=value), current[1])
    assert "CURRENT_AMOUNT_INVALID" in codes(run(current=changed))


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("entity", " Cedar Demo LLC", "CURRENT_ENTITY_INVALID"),
        ("account", "cash", "CURRENT_ACCOUNT_INVALID"),
        ("account_title", "", "CURRENT_ACCOUNT_TITLE_INVALID"),
    ],
)
def test_semantic_identifiers_are_strict(field, value, expected):
    current, _ = demo_pair()
    changed = (replace(current[0], **{field: value}), current[1])
    assert expected in codes(run(current=changed))


def test_each_entity_must_net_to_zero():
    current, _ = demo_pair()
    changed = (replace(current[0], activity_cents=75_001, closing_cents=1_075_001), current[1])
    assert "CURRENT_ENTITY_NET_NOT_ZERO" in codes(run(current=changed))


def test_displayed_control_must_tie_to_rederived_entity_net():
    result = run(controls=(EntityControl("Cedar Demo LLC", 1),))
    assert "CONTROL_NET_OUT_OF_TIE" in codes(result)


def test_control_set_must_cover_current_entities_once():
    duplicate = (
        EntityControl("Cedar Demo LLC", 0),
        EntityControl("cedar demo llc", 0),
        EntityControl("Unknown Demo LLC", 0),
    )
    result = run(controls=duplicate)
    assert {"CONTROL_ENTITY_DUPLICATE", "CONTROL_ENTITY_UNKNOWN"} <= codes(result)


def test_nonzero_adjustment_is_review_gated_and_never_drafted():
    current, _ = demo_pair()
    changed = (replace(current[0], adjustment_cents=12_500), current[1])
    result = run(current=changed)
    assert "CURRENT_ADJUSTMENT_REVIEW_REQUIRED" in codes(result)
    assert result.verdict == "NEEDS REVIEW"
    assert result.journal_entries == ()


@pytest.mark.parametrize(
    ("reference", "cached", "expected"),
    [
        ("'[Source Book.xlsx]TB'!A1", 0, "DEPENDENCY_EXTERNAL_OR_BROKEN"),
        ("'TB'!#REF!", 0, "DEPENDENCY_EXTERNAL_OR_BROKEN"),
        ("https://example.invalid/source", 0, "DEPENDENCY_EXTERNAL_OR_BROKEN"),
        ("'TB'!A1", "#VALUE!", "DEPENDENCY_CACHED_ERROR"),
    ],
)
def test_external_broken_and_cached_dependency_errors_are_named(reference, cached, expected):
    result = run(dependencies=(DependencyEvidence("Fictional dependency", reference, cached),))
    assert expected in codes(result)


def test_empty_current_and_prior_are_not_clean_noops():
    result = run(current=(), prior=())
    assert {"CURRENT_TRIAL_BALANCE_EMPTY", "PRIOR_TRIAL_BALANCE_EMPTY"} <= codes(result)


def test_validator_does_not_mutate_input_sequences():
    current, prior = demo_pair()
    current_list = list(current)
    prior_list = list(prior)
    before = (tuple(current_list), tuple(prior_list))
    run(current=current_list, prior=prior_list)
    assert (tuple(current_list), tuple(prior_list)) == before
