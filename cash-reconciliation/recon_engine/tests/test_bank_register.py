"""Controls for the fictional validation-only bank-register continuity engine."""

from dataclasses import replace

import pytest

from recon_engine.bank_register import (
    BankRegister,
    BankRegisterValidator,
    RegisterTransaction,
    demo_register,
)


def run(register=None):
    return BankRegisterValidator(demo_register() if register is None else register).run()


def codes(result):
    return {finding.code for finding in result.findings}


def retime(register, transactions):
    """Return a copy of ``register`` with a fresh transaction tuple."""

    return replace(register, transactions=tuple(transactions))


def test_clean_register_reties_the_chain_and_stays_validation_only():
    result = run()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.transaction_count == 4
    assert result.out_of_tie_row_count == 0
    assert result.rederived_closing_cents == 1_150_000
    assert "manual posting" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_period_must_be_canonical(period):
    with pytest.raises(ValueError, match="period must be canonical YYYY-MM"):
        BankRegisterValidator(replace(demo_register(), period=period))


def test_running_balance_first_row_is_checked_against_opening():
    reg = demo_register()
    txns = list(reg.transactions)
    txns[0] = replace(txns[0], running_balance_cents=1_250_001)
    result = run(retime(reg, txns))
    assert "RUNNING_BALANCE_OUT_OF_TIE" in codes(result)
    # Row 0 breaks against opening; row 1 is then checked against the displayed
    # (tampered) row-0 balance, so the break cascades to exactly one more row.
    assert result.out_of_tie_row_count == 2


def test_running_balance_last_row_break_is_isolated():
    reg = demo_register()
    txns = list(reg.transactions)
    txns[-1] = replace(txns[-1], running_balance_cents=1_149_999)
    result = run(retime(reg, txns))
    assert "RUNNING_BALANCE_OUT_OF_TIE" in codes(result)
    assert result.out_of_tie_row_count == 1


def test_running_balance_mid_row_is_independently_rederived():
    reg = demo_register()
    txns = list(reg.transactions)
    txns[2] = replace(txns[2], running_balance_cents=1_199_999)
    result = run(retime(reg, txns))
    assert "RUNNING_BALANCE_OUT_OF_TIE" in codes(result)
    # A single displayed running balance breaks its own row and the next row's tie.
    assert result.out_of_tie_row_count == 2


def test_closing_must_equal_opening_plus_movements():
    reg = replace(demo_register(), displayed_closing_cents=1_149_999)
    assert "CLOSING_OUT_OF_TIE" in codes(run(reg))


def test_opening_continuity_out_of_tie():
    reg = replace(demo_register(), prior_closing_cents=999_999)
    assert "OPENING_CONTINUITY_OUT_OF_TIE" in codes(run(reg))


def test_opening_continuity_skipped_when_prior_absent():
    reg = replace(demo_register(), prior_closing_cents=None)
    result = run(reg)
    assert result.mechanical_clean
    assert "OPENING_CONTINUITY_OUT_OF_TIE" not in codes(result)


def test_bank_tie_out_flags_material_difference():
    reg = replace(demo_register(), bank_statement_ending_cents=1_150_500)
    assert "BANK_TIE_OUT" in codes(run(reg))


def test_bank_tie_out_is_review_severity_and_never_drafts():
    reg = replace(demo_register(), bank_statement_ending_cents=1_150_500)
    result = run(reg)
    flagged = [f for f in result.findings if f.code == "BANK_TIE_OUT"]
    assert flagged and flagged[0].severity == "REVIEW"
    assert result.verdict == "NEEDS REVIEW"
    assert result.journal_entries == ()


def test_bank_tie_out_skipped_when_statement_absent():
    reg = replace(demo_register(), bank_statement_ending_cents=None)
    result = run(reg)
    assert result.mechanical_clean
    assert "BANK_TIE_OUT" not in codes(result)


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_transaction_amounts_are_rejected_without_coercion(value):
    reg = demo_register()
    txns = list(reg.transactions)
    txns[0] = replace(txns[0], amount_cents=value)
    assert "AMOUNT_INVALID" in codes(run(retime(reg, txns)))


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_running_balances_are_rejected_without_coercion(value):
    reg = demo_register()
    txns = list(reg.transactions)
    txns[1] = replace(txns[1], running_balance_cents=value)
    assert "AMOUNT_INVALID" in codes(run(retime(reg, txns)))


@pytest.mark.parametrize("value", [1.5, True, "100", float("nan"), float("inf")])
def test_opening_balance_must_be_integer(value):
    assert "OPENING_BALANCE_INVALID" in codes(run(replace(demo_register(), opening_balance_cents=value)))


@pytest.mark.parametrize("value", [1.5, True, "100", float("nan"), float("inf")])
def test_displayed_closing_must_be_integer(value):
    assert "DISPLAYED_CLOSING_INVALID" in codes(run(replace(demo_register(), displayed_closing_cents=value)))


@pytest.mark.parametrize("value", [1.5, True, "100", float("nan"), float("inf")])
def test_prior_closing_must_be_integer_when_present(value):
    assert "PRIOR_CLOSING_INVALID" in codes(run(replace(demo_register(), prior_closing_cents=value)))


@pytest.mark.parametrize("value", [1.5, True, "100", float("nan"), float("inf")])
def test_bank_statement_must_be_integer_when_present(value):
    assert "BANK_STATEMENT_INVALID" in codes(run(replace(demo_register(), bank_statement_ending_cents=value)))


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("entity", " Cedar Demo LLC", "ENTITY_INVALID"),
        ("entity", "", "ENTITY_INVALID"),
        ("account", "cash", "ACCOUNT_INVALID"),
        ("account", "CASH_1001", "ACCOUNT_INVALID"),
    ],
)
def test_register_identifiers_are_strict(field, value, expected):
    assert expected in codes(run(replace(demo_register(), **{field: value})))


@pytest.mark.parametrize("bad_id", ["", "   ", " TXN-0009"])
def test_txn_id_must_be_trimmed_and_nonblank(bad_id):
    reg = demo_register()
    txns = list(reg.transactions)
    txns[1] = replace(txns[1], txn_id=bad_id)
    assert "TXN_ID_INVALID" in codes(run(retime(reg, txns)))


def test_duplicate_txn_ids_are_blocked_case_insensitively():
    reg = demo_register()
    txns = list(reg.transactions)
    txns[1] = replace(txns[1], txn_id=txns[0].txn_id.lower())
    result = run(retime(reg, txns))
    assert "TXN_ID_DUPLICATE" in codes(result)


@pytest.mark.parametrize("bad_date", ["2026-6-2", "06/02/2026", "2026-06-31", "2026-02-30", "not-a-date"])
def test_txn_date_must_be_valid_iso(bad_date):
    reg = demo_register()
    txns = list(reg.transactions)
    txns[0] = replace(txns[0], txn_date=bad_date)
    assert "TXN_DATE_INVALID" in codes(run(retime(reg, txns)))


@pytest.mark.parametrize("wrong_month", ["2026-05-31", "2026-07-01", "2025-06-15"])
def test_txn_date_must_be_within_the_period_month(wrong_month):
    reg = demo_register()
    txns = list(reg.transactions)
    txns[0] = replace(txns[0], txn_date=wrong_month)
    assert "TXN_DATE_OUT_OF_PERIOD" in codes(run(retime(reg, txns)))


def test_empty_register_is_not_a_clean_noop():
    reg = retime(demo_register(), ())
    assert "REGISTER_EMPTY" in codes(run(reg))
    assert not run(reg).mechanical_clean


def test_rederived_closing_is_none_when_an_amount_is_unsafe():
    reg = demo_register()
    txns = list(reg.transactions)
    txns[0] = replace(txns[0], amount_cents="oops")
    result = run(retime(reg, txns))
    assert result.rederived_closing_cents is None


def test_transaction_count_reflects_input():
    reg = demo_register()
    result = run(retime(reg, reg.transactions[:2]))
    assert result.transaction_count == 2


def test_results_are_deterministic():
    first = run()
    second = run()
    assert codes(first) == codes(second)
    assert first.rederived_closing_cents == second.rederived_closing_cents
    assert first.out_of_tie_row_count == second.out_of_tie_row_count


def test_validator_does_not_mutate_the_register():
    reg = demo_register()
    before_txns = reg.transactions
    run(reg)
    assert reg.transactions == before_txns
    assert reg == demo_register()


def test_no_posting_artifacts_even_when_findings_present():
    reg = replace(demo_register(), displayed_closing_cents=1)
    result = run(reg)
    assert not result.mechanical_clean
    assert result.journal_entries == ()
    assert result.posting_actions == ()
    assert result.import_payloads == ()
    assert result.posting_authorized is False
