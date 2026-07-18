"""Controls for the fictional validation-only outstanding-check register."""

from datetime import date
from dataclasses import replace

import pytest

from recon_engine.outstanding_checks import (
    CheckRecord,
    OutstandingCheckValidator,
    _parse_iso_date,
    demo_checks,
    DEMO_PERIOD,
    DEMO_AS_OF_DATE,
    DEMO_STALE_DAYS,
    DEMO_OUTSTANDING_TOTAL_CENTS,
)


def make(
    checks=None,
    period=DEMO_PERIOD,
    as_of=DEMO_AS_OF_DATE,
    stale_days=DEMO_STALE_DAYS,
    displayed=DEMO_OUTSTANDING_TOTAL_CENTS,
):
    return OutstandingCheckValidator(
        period,
        as_of,
        stale_days,
        demo_checks() if checks is None else checks,
        displayed,
    )


def run(**kwargs):
    return make(**kwargs).run()


def codes(result):
    return {finding.code for finding in result.findings}


def find(result, code):
    return next(finding for finding in result.findings if finding.code == code)


# --- Clean case ------------------------------------------------------------
def test_clean_register_ties_and_stays_validation_only():
    result = run()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.check_count == 5
    assert result.outstanding_count == 2
    assert result.cleared_count == 1
    assert result.void_count == 1
    assert result.stale_count == 1
    assert result.outstanding_total_cents == DEMO_OUTSTANDING_TOTAL_CENTS == 195_000
    assert "manual posting" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


def test_outstanding_total_is_independently_rederived():
    assert run(displayed=None).outstanding_total_cents == 195_000


# --- Constructor-level config -------------------------------------------
@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_period_must_be_canonical(period):
    with pytest.raises(ValueError, match="period must be canonical YYYY-MM"):
        OutstandingCheckValidator(period, DEMO_AS_OF_DATE, DEMO_STALE_DAYS, demo_checks())


@pytest.mark.parametrize("value", [1.5, True, -1, "180", None, float("nan")])
def test_stale_days_must_be_nonnegative_integer(value):
    with pytest.raises(ValueError, match="stale_days must be a nonnegative integer"):
        OutstandingCheckValidator(DEMO_PERIOD, DEMO_AS_OF_DATE, value, demo_checks())


# --- Date validity (findings, never raises) ------------------------------
@pytest.mark.parametrize(
    "value",
    ["2026-6-30", "06-30-2026", "2026-13-01", "2026-02-30", " 2026-06-30", "20260630", "", "2026/06/30"],
)
def test_as_of_date_must_be_valid_iso(value):
    assert "AS_OF_DATE_INVALID" in codes(run(as_of=value, displayed=None))


@pytest.mark.parametrize(
    "value",
    ["2026-6-15", "15-06-2026", "2026-13-01", "2026-02-30", " 2026-06-15", "20260615", ""],
)
def test_issue_date_must_be_valid_iso(value):
    checks = list(demo_checks())
    checks[0] = replace(checks[0], issue_date=value)
    assert "ISSUE_DATE_INVALID" in codes(run(checks=tuple(checks), displayed=None))


@pytest.mark.parametrize(
    "value",
    ["2026-6-30", "06-30-2026", "2026-13-01", "2026-02-30", " 2026-06-30", "20260630", "", "2026/06/30", None, 20260630],
)
def test_parse_iso_date_rejects_malformed_without_raising(value):
    assert _parse_iso_date(value) is None


def test_parse_iso_date_accepts_a_real_date():
    assert _parse_iso_date("2026-06-30") == date(2026, 6, 30)


# --- Strict identifiers, status, amounts ---------------------------------
@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("entity", " Cedar Demo LLC", "ENTITY_INVALID"),
        ("account", "cash", "ACCOUNT_INVALID"),
        ("check_number", "", "CHECK_NUMBER_INVALID"),
        ("check_number", "   ", "CHECK_NUMBER_INVALID"),
        ("payee", "", "PAYEE_INVALID"),
        ("payee", " Demo Utility Co", "PAYEE_INVALID"),
        ("status", "pending", "STATUS_INVALID"),
    ],
)
def test_strict_identifiers_and_status(field, value, expected):
    checks = list(demo_checks())
    checks[0] = replace(checks[0], **{field: value})
    assert expected in codes(run(checks=tuple(checks), displayed=None))


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_amounts_are_rejected_without_coercion(value):
    checks = list(demo_checks())
    checks[0] = replace(checks[0], amount_cents=value)
    assert "AMOUNT_INVALID" in codes(run(checks=tuple(checks), displayed=None))


@pytest.mark.parametrize("index", [0, 2, 4])  # outstanding, cleared, stale
@pytest.mark.parametrize("amount", [0, -100])
def test_live_status_amount_must_be_positive(index, amount):
    checks = list(demo_checks())
    checks[index] = replace(checks[index], amount_cents=amount)
    assert "CHECK_AMOUNT_NONPOSITIVE" in codes(run(checks=tuple(checks), displayed=None))


@pytest.mark.parametrize("amount", [1, -1, 500])
def test_void_check_must_carry_zero_amount(amount):
    checks = list(demo_checks())
    checks[3] = replace(checks[3], amount_cents=amount)  # the void check
    assert "VOID_AMOUNT_NONZERO" in codes(run(checks=tuple(checks), displayed=None))


def test_valid_void_with_zero_amount_is_clean():
    # The demo already carries a zero-amount void; it must raise no finding.
    result = run(displayed=None)
    assert "VOID_AMOUNT_NONZERO" not in codes(result)
    assert result.void_count == 1


# --- Uniqueness ----------------------------------------------------------
def test_check_number_unique_per_account_case_insensitive():
    checks = list(demo_checks())
    checks[0] = replace(checks[0], check_number="A-100")
    checks[1] = replace(checks[1], check_number="a-100")  # same account CASH-1001
    assert "CHECK_NUMBER_DUPLICATE" in codes(run(checks=tuple(checks), displayed=None))


def test_same_check_number_on_different_accounts_is_allowed():
    checks = list(demo_checks())
    checks[4] = replace(checks[4], check_number="1050")  # CASH-1002, collides with CASH-1001/1050
    assert "CHECK_NUMBER_DUPLICATE" not in codes(run(checks=tuple(checks), displayed=None))


# --- Dating / aging ------------------------------------------------------
def test_issue_date_after_as_of_is_flagged():
    checks = list(demo_checks())
    checks[0] = replace(checks[0], issue_date="2026-07-15")  # after 2026-06-30
    assert "ISSUE_DATE_AFTER_AS_OF" in codes(run(checks=tuple(checks), displayed=None))


def test_stale_outstanding_check_is_review_gated_and_never_drafted():
    checks = list(demo_checks())
    checks[0] = replace(checks[0], issue_date="2024-01-01")  # far older than 180 days
    result = run(checks=tuple(checks), displayed=None)
    assert "STALE_CHECK_REVIEW" in codes(result)
    assert find(result, "STALE_CHECK_REVIEW").severity == "REVIEW"
    assert result.verdict == "NEEDS REVIEW"
    assert result.journal_entries == ()


def test_stale_boundary_exactly_at_threshold_is_not_flagged():
    checks = list(demo_checks())
    checks[0] = replace(checks[0], issue_date="2026-01-01")  # exactly 180 days before 2026-06-30
    assert "STALE_CHECK_REVIEW" not in codes(run(checks=tuple(checks), displayed=None))


def test_stale_one_day_past_threshold_is_flagged():
    checks = list(demo_checks())
    checks[0] = replace(checks[0], issue_date="2025-12-31")  # 181 days before 2026-06-30
    assert "STALE_CHECK_REVIEW" in codes(run(checks=tuple(checks), displayed=None))


def test_already_stale_status_check_is_not_flagged_for_review():
    # The demo's aged check is marked ``stale`` (correctly), so STALE_CHECK_REVIEW
    # — which only fires for status ``outstanding`` — must not appear.
    assert "STALE_CHECK_REVIEW" not in codes(run(displayed=None))


# --- Outstanding-total tie-out ------------------------------------------
def test_outstanding_total_must_tie_to_displayed():
    assert "OUTSTANDING_TOTAL_OUT_OF_TIE" in codes(run(displayed=195_001))


def test_displayed_outstanding_total_type_is_strict():
    assert "DISPLAYED_OUTSTANDING_TOTAL_INVALID" in codes(run(displayed=1.5))


def test_displayed_none_skips_the_tie_out():
    result = run(displayed=None)
    assert result.mechanical_clean
    assert "OUTSTANDING_TOTAL_OUT_OF_TIE" not in codes(result)


# --- Population & mutation ----------------------------------------------
def test_empty_register_is_not_a_clean_noop():
    assert "CHECK_REGISTER_EMPTY" in codes(run(checks=(), displayed=None))


def test_validator_does_not_mutate_input_sequence():
    checks = list(demo_checks())
    before = tuple(checks)
    run(checks=checks, displayed=None)
    assert tuple(checks) == before
