"""Controls for the fictional validation-only cash-concentration sweep bridge."""

from dataclasses import replace

import pytest

from recon_engine.cash_concentration import (
    CashConcentrationValidator,
    ConcentrationAccount,
    SweepLine,
    demo_concentration,
)


def run(account=None, lines=None):
    demo_account, demo_lines = demo_concentration()
    return CashConcentrationValidator(
        demo_account if account is None else account,
        demo_lines if lines is None else lines,
    ).run()


def codes(result):
    return {finding.code for finding in result.findings}


def test_clean_sweep_ties_both_sides_and_stays_validation_only():
    result = run()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.sub_account_count == 2
    assert result.swept_total_cents == 800_000
    assert result.rederived_closing_cents == 1_100_000
    assert "manual posting" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


def test_clean_sweep_has_no_findings():
    assert run().findings == ()


def test_result_echoes_period_entity_and_account():
    result = run()
    assert result.period == "2026-06"
    assert result.entity == "Cedar Demo LLC"
    assert result.account == "CASH-1900"


@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_period_must_be_canonical(period):
    account, lines = demo_concentration()
    with pytest.raises(ValueError, match="period must be canonical YYYY-MM"):
        CashConcentrationValidator(replace(account, period=period), lines)


@pytest.mark.parametrize("period", [None, 202606, 2026.06])
def test_non_string_period_is_rejected(period):
    account, lines = demo_concentration()
    with pytest.raises(ValueError, match="period must be canonical YYYY-MM"):
        CashConcentrationValidator(replace(account, period=period), lines)


def test_sweep_tie_out_is_independently_rederived():
    account, lines = demo_concentration()
    changed = (lines[0], replace(lines[1], swept_amount_cents=500_001))
    result = run(lines=changed)
    assert "SWEEP_TIE_OUT" in codes(result)


def test_sweep_tie_out_flags_missing_sub_account():
    account, lines = demo_concentration()
    # Drop a sweep line so the swept total no longer matches sweeps in.
    result = run(lines=(lines[0],))
    assert "SWEEP_TIE_OUT" in codes(result)


def test_rollforward_must_tie_to_displayed_closing():
    account, _ = demo_concentration()
    changed = replace(account, displayed_closing_cents=1_099_999)
    assert "CONCENTRATION_ROLLFORWARD_OUT_OF_TIE" in codes(run(account=changed))


def test_rollforward_reacts_to_opening_tamper():
    account, _ = demo_concentration()
    changed = replace(account, opening_cents=500_001)
    assert "CONCENTRATION_ROLLFORWARD_OUT_OF_TIE" in codes(run(account=changed))


def test_rollforward_reacts_to_disbursements_tamper():
    account, _ = demo_concentration()
    changed = replace(account, disbursements_cents=199_999)
    assert "CONCENTRATION_ROLLFORWARD_OUT_OF_TIE" in codes(run(account=changed))


def test_sweeps_in_tamper_breaks_both_tie_outs():
    account, _ = demo_concentration()
    # Raising sweeps in breaks the sub-account tie and the roll-forward at once.
    changed = replace(account, sweeps_in_cents=800_001)
    result_codes = codes(run(account=changed))
    assert "SWEEP_TIE_OUT" in result_codes
    assert "CONCENTRATION_ROLLFORWARD_OUT_OF_TIE" in result_codes


def test_disbursements_cannot_be_negative():
    account, _ = demo_concentration()
    # Keep the roll-forward tied so only the negativity finding remains isolated.
    changed = replace(
        account,
        disbursements_cents=-200_000,
        displayed_closing_cents=1_500_000,
    )
    assert "DISBURSEMENTS_NEGATIVE" in codes(run(account=changed))


def test_swept_amount_cannot_be_negative():
    account, lines = demo_concentration()
    changed = (replace(lines[0], swept_amount_cents=-1), lines[1])
    assert "SWEPT_AMOUNT_NEGATIVE" in codes(run(lines=changed))


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_concentration_amounts_are_rejected_without_coercion(value):
    account, _ = demo_concentration()
    changed = replace(account, opening_cents=value)
    assert "AMOUNT_INVALID" in codes(run(account=changed))


@pytest.mark.parametrize(
    "field",
    ["opening_cents", "sweeps_in_cents", "disbursements_cents", "displayed_closing_cents"],
)
def test_each_concentration_amount_field_is_checked(field):
    account, _ = demo_concentration()
    changed = replace(account, **{field: 1.5})
    assert "AMOUNT_INVALID" in codes(run(account=changed))


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_swept_amounts_are_rejected_without_coercion(value):
    account, lines = demo_concentration()
    changed = (replace(lines[0], swept_amount_cents=value), lines[1])
    assert "SUB_ACCOUNT_AMOUNT_INVALID" in codes(run(lines=changed))


def test_invalid_swept_amount_suppresses_tie_out_without_coercion():
    account, lines = demo_concentration()
    changed = (replace(lines[0], swept_amount_cents="300000"), lines[1])
    result = run(lines=changed)
    assert "SUB_ACCOUNT_AMOUNT_INVALID" in codes(result)
    assert "SWEEP_TIE_OUT" not in codes(result)
    assert result.swept_total_cents is None


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("entity", " Cedar Demo LLC", "ENTITY_INVALID"),
        ("entity", "", "ENTITY_INVALID"),
        ("account", "cash", "ACCOUNT_INVALID"),
        ("account", "CASH_1900", "ACCOUNT_INVALID"),
    ],
)
def test_concentration_identifiers_are_strict(field, value, expected):
    account, _ = demo_concentration()
    changed = replace(account, **{field: value})
    assert expected in codes(run(account=changed))


@pytest.mark.parametrize("bad", ["sub", "CASH_2001", " CASH-2001", "cash-2001x-", ""])
def test_sub_account_must_be_canonical(bad):
    account, lines = demo_concentration()
    changed = (replace(lines[0], sub_account=bad), lines[1])
    assert "SUB_ACCOUNT_INVALID" in codes(run(lines=changed))


def test_duplicate_sub_accounts_are_blocked_case_insensitively():
    account, lines = demo_concentration()
    changed = (lines[0], replace(lines[1], sub_account=lines[0].sub_account.lower()))
    assert "SUB_ACCOUNT_DUPLICATE" in codes(run(lines=changed))


def test_empty_sweep_set_is_not_a_clean_noop():
    result = run(lines=())
    assert "SUB_ACCOUNT_SET_EMPTY" in codes(result)
    assert not result.mechanical_clean
    assert result.verdict == "NEEDS REVIEW"


def test_structural_failure_suppresses_rollforward_rederivation():
    account, _ = demo_concentration()
    changed = replace(account, opening_cents=None)
    result = run(account=changed)
    assert "AMOUNT_INVALID" in codes(result)
    assert "CONCENTRATION_ROLLFORWARD_OUT_OF_TIE" not in codes(result)
    assert result.rederived_closing_cents is None


def test_any_finding_flips_verdict_to_needs_review():
    account, _ = demo_concentration()
    changed = replace(account, displayed_closing_cents=1_099_999)
    result = run(account=changed)
    assert not result.mechanical_clean
    assert result.verdict == "NEEDS REVIEW"


def test_findings_never_authorize_posting():
    account, _ = demo_concentration()
    changed = replace(account, sweeps_in_cents=800_001)
    result = run(account=changed)
    assert not result.posting_authorized
    assert result.validation_only
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


def test_validator_does_not_mutate_input_sequence():
    account, lines = demo_concentration()
    line_list = list(lines)
    before = tuple(line_list)
    CashConcentrationValidator(account, line_list).run()
    assert tuple(line_list) == before


def test_validator_does_not_mutate_account_or_lines():
    account, lines = demo_concentration()
    result = run(account=account, lines=lines)
    assert result.mechanical_clean
    # Frozen dataclasses are unchanged and still tie on a second run.
    assert account == ConcentrationAccount(
        entity="Cedar Demo LLC",
        account="CASH-1900",
        period="2026-06",
        opening_cents=500_000,
        sweeps_in_cents=800_000,
        disbursements_cents=200_000,
        displayed_closing_cents=1_100_000,
    )
    assert lines[0] == SweepLine(sub_account="CASH-2001", swept_amount_cents=300_000)


def test_run_is_deterministic():
    first = run()
    second = run()
    assert codes(first) == codes(second)
    assert first.swept_total_cents == second.swept_total_cents
    assert first.rederived_closing_cents == second.rederived_closing_cents
