from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.payroll_recovery import (
    PayrollRecoverySnapshot,
    PayrollRecoveryValidator,
    RecoveryLine,
)


def line(
    entity_id: str,
    project_id: str,
    amounts: tuple[object, ...],
    *,
    cached_total: object | None = None,
) -> RecoveryLine:
    safe_total = sum(value for value in amounts if isinstance(value, int) and not isinstance(value, bool))
    return RecoveryLine(
        entity_id=entity_id,
        project_id=project_id,
        fiscal_month_amounts_cents=amounts,
        cached_total_cents=safe_total if cached_total is None else cached_total,
        source_reference=f"fictional://recovery/{entity_id}/{project_id}",
    )


def snapshot(period: str = "2026-09", *, include_target: bool = True) -> PayrollRecoverySnapshot:
    first = (10_000, 20_000, 30_000 if include_target else 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    second = (5_000, 7_500, 12_500 if include_target else 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    lines = (line("ENTITY-A", "PROJECT-A", first), line("ENTITY-B", "PROJECT-B", second))
    totals = tuple(sum(item.fiscal_month_amounts_cents[index] for item in lines) for index in range(12))
    return PayrollRecoverySnapshot(
        period=period,
        lines=lines,
        cached_month_totals_cents=totals,
        cached_grand_total_cents=sum(totals),
        source_fingerprint="a" * 64 if include_target else "b" * 64,
    )


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def with_first(current: PayrollRecoverySnapshot, **changes: object) -> PayrollRecoverySnapshot:
    changed = replace(current.lines[0], **changes)
    return replace(current, lines=(changed,) + current.lines[1:])


def test_clean_schedule_is_validation_only_and_ready_for_human_review() -> None:
    result = PayrollRecoveryValidator(snapshot()).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.payroll_update_authorized
    assert not result.posting_authorized
    assert result.line_count == 2
    assert result.entity_count == 2
    assert result.project_count == 2
    assert result.journal_entries == ()
    assert result.payroll_actions == ()
    assert result.import_payloads == ()
    assert result.posting_actions == ()


@pytest.mark.parametrize("period", ["2026-9", "September 2026", "", "2026-13"])
def test_invalid_period_is_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        PayrollRecoveryValidator(replace(snapshot(), period=period))


def test_missing_population_blocks() -> None:
    result = PayrollRecoveryValidator(replace(snapshot(), lines=())).validate()
    assert "RECOVERY_POPULATION_MISSING" in codes(result)


@pytest.mark.parametrize(("field", "code"), [("entity_id", "UNSAFE_ENTITY_ID"), ("project_id", "UNSAFE_PROJECT_ID"), ("source_reference", "UNSAFE_SOURCE_REFERENCE")])
def test_blank_or_untrimmed_core_text_blocks(field: str, code: str) -> None:
    result = PayrollRecoveryValidator(with_first(snapshot(), **{field: " BAD"})).validate()
    assert code in codes(result)


def test_duplicate_entity_project_line_blocks() -> None:
    current = snapshot()
    duplicate = replace(current.lines[1], entity_id="ENTITY-A", project_id="PROJECT-A")
    result = PayrollRecoveryValidator(replace(current, lines=(current.lines[0], duplicate))).validate()
    assert "DUPLICATE_RECOVERY_LINE" in codes(result)


@pytest.mark.parametrize("length", [0, 11, 13])
def test_line_month_vector_requires_twelve_values(length: int) -> None:
    result = PayrollRecoveryValidator(with_first(snapshot(), fiscal_month_amounts_cents=(0,) * length)).validate()
    assert "MONTH_VECTOR_LENGTH" in codes(result)


@pytest.mark.parametrize("unsafe", [None, 1.5, True, "100"])
def test_recovery_amounts_must_be_integer_cents(unsafe: object) -> None:
    amounts = list(snapshot().lines[0].fiscal_month_amounts_cents)
    amounts[0] = unsafe
    result = PayrollRecoveryValidator(with_first(snapshot(), fiscal_month_amounts_cents=tuple(amounts))).validate()
    assert "UNSAFE_RECOVERY_AMOUNT" in codes(result)


def test_line_total_must_readd_and_use_integer_cents() -> None:
    assert "LINE_TOTAL_OUT_OF_TIE" in codes(PayrollRecoveryValidator(with_first(snapshot(), cached_total_cents=1)).validate())
    assert "UNSAFE_CACHED_LINE_TOTAL" in codes(PayrollRecoveryValidator(with_first(snapshot(), cached_total_cents=1.5)).validate())


@pytest.mark.parametrize("length", [0, 11, 13])
def test_month_total_vector_requires_twelve_values(length: int) -> None:
    result = PayrollRecoveryValidator(replace(snapshot(), cached_month_totals_cents=(0,) * length)).validate()
    assert "MONTH_TOTAL_VECTOR_LENGTH" in codes(result)


def test_month_total_must_readd_and_use_integer_cents() -> None:
    current = snapshot()
    totals = list(current.cached_month_totals_cents)
    totals[0] += 1
    assert "MONTH_TOTAL_OUT_OF_TIE" in codes(PayrollRecoveryValidator(replace(current, cached_month_totals_cents=tuple(totals))).validate())
    totals[0] = 1.5
    assert "UNSAFE_CACHED_MONTH_TOTAL" in codes(PayrollRecoveryValidator(replace(current, cached_month_totals_cents=tuple(totals))).validate())


def test_grand_total_must_readd_and_use_integer_cents() -> None:
    assert "GRAND_TOTAL_OUT_OF_TIE" in codes(PayrollRecoveryValidator(replace(snapshot(), cached_grand_total_cents=1)).validate())
    assert "UNSAFE_CACHED_GRAND_TOTAL" in codes(PayrollRecoveryValidator(replace(snapshot(), cached_grand_total_cents=1.5)).validate())


@pytest.mark.parametrize("fingerprint", ["", "A" * 64, "a" * 63, "private-path"])
def test_source_fingerprint_must_be_lowercase_sha256(fingerprint: str) -> None:
    result = PayrollRecoveryValidator(replace(snapshot(), source_fingerprint=fingerprint)).validate()
    assert "UNSAFE_SOURCE_FINGERPRINT" in codes(result)


def test_future_period_activity_blocks() -> None:
    amounts = list(snapshot().lines[0].fiscal_month_amounts_cents)
    amounts[3] = 100
    current = with_first(snapshot(), fiscal_month_amounts_cents=tuple(amounts), cached_total_cents=60_100)
    totals = list(current.cached_month_totals_cents)
    totals[3] = 100
    current = replace(current, cached_month_totals_cents=tuple(totals), cached_grand_total_cents=85_100)
    assert "FUTURE_PERIOD_ACTIVITY" in codes(PayrollRecoveryValidator(current).validate())


def test_negative_recovery_is_visible_warning() -> None:
    amounts = (-1_000, 20_000, 30_000, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    current = with_first(snapshot(), fiscal_month_amounts_cents=amounts, cached_total_cents=49_000)
    totals = (4_000, 27_500, 42_500, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    current = replace(current, cached_month_totals_cents=totals, cached_grand_total_cents=74_000)
    result = PayrollRecoveryValidator(current).validate()
    assert "NEGATIVE_RECOVERY_REVIEW" in codes(result)
    assert result.negative_amount_count == 1
    assert result.mechanical_clean


def test_prior_must_be_immediately_preceding_month() -> None:
    prior = snapshot("2026-07", include_target=False)
    assert "PRIOR_PERIOD_MISMATCH" in codes(PayrollRecoveryValidator(snapshot(), prior).validate())


def test_clean_current_prior_pair_ties_target_activity_to_total_change() -> None:
    current = snapshot()
    prior = snapshot("2026-08", include_target=False)
    result = PayrollRecoveryValidator(current, prior).validate()
    assert result.mechanical_clean
    assert "MONTHLY_CHANGE_REVIEW" in codes(result)
    assert "TOTAL_CHANGE_OUT_OF_TIE" not in codes(result)
    assert result.grand_total_change_cents == 42_500
    assert result.historical_change_count == 0


def test_identical_sequential_fingerprints_are_visible_warning() -> None:
    current = snapshot()
    prior = replace(snapshot("2026-08", include_target=False), source_fingerprint=current.source_fingerprint)
    result = PayrollRecoveryValidator(current, prior).validate()
    assert "IDENTICAL_PERIOD_FINGERPRINTS" in codes(result)
    assert result.mechanical_clean


def test_population_changes_are_visible_warnings() -> None:
    current = snapshot()
    prior = snapshot("2026-08", include_target=False)
    changed = replace(prior.lines[1], entity_id="ENTITY-OLD", project_id="PROJECT-OLD")
    prior = replace(prior, lines=(prior.lines[0], changed))
    result = PayrollRecoveryValidator(current, prior).validate()
    assert "RECOVERY_POPULATION_CHANGED" in codes(result)
    assert result.entity_added_count == 1
    assert result.entity_removed_count == 1
    assert result.project_added_count == 1
    assert result.project_removed_count == 1
    assert result.mechanical_clean


def test_historical_activity_change_and_total_delta_block() -> None:
    current = snapshot()
    amounts = list(current.lines[0].fiscal_month_amounts_cents)
    amounts[0] += 1
    current = with_first(current, fiscal_month_amounts_cents=tuple(amounts), cached_total_cents=60_001)
    totals = list(current.cached_month_totals_cents)
    totals[0] += 1
    current = replace(current, cached_month_totals_cents=tuple(totals), cached_grand_total_cents=85_001)
    prior = snapshot("2026-08", include_target=False)
    result = PayrollRecoveryValidator(current, prior).validate()
    assert "HISTORICAL_ACTIVITY_CHANGED" in codes(result)
    assert "TOTAL_CHANGE_OUT_OF_TIE" in codes(result)
    assert result.historical_change_count == 1
    assert not result.mechanical_clean


def test_july_rollover_does_not_compare_prior_fiscal_year_history() -> None:
    current = replace(snapshot("2027-07", include_target=False), cached_month_totals_cents=(15_000,) + (0,) * 11, cached_grand_total_cents=15_000)
    current_lines = (
        line("ENTITY-A", "PROJECT-A", (10_000,) + (0,) * 11),
        line("ENTITY-B", "PROJECT-B", (5_000,) + (0,) * 11),
    )
    current = replace(current, lines=current_lines)
    prior = snapshot("2026-06", include_target=True)
    result = PayrollRecoveryValidator(current, prior).validate()
    assert "HISTORICAL_ACTIVITY_CHANGED" not in codes(result)
    assert result.historical_change_count == 0
