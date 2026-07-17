from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.personal_property_tax import (
    AssetEvidence,
    AssetScheduleSnapshot,
    PersonalPropertyTaxValidator,
)


def asset(
    asset_id: str,
    *,
    cost_cents: object = 120_000,
    useful_life_months: object = 60,
    months_used: object = 18,
    accumulated_cents: object = 36_000,
    period_cents: object = 2_000,
    nbv_cents: object = 84_000,
    manual_carryforward: object = False,
) -> AssetEvidence:
    return AssetEvidence(
        asset_id=asset_id,
        category="FURNITURE",
        placed_in_service="2024-09-15",
        depreciation_end_date="2029-08-31",
        cost_cents=cost_cents,
        useful_life_months=useful_life_months,
        months_used=months_used,
        accumulated_depreciation_cents=accumulated_cents,
        period_depreciation_cents=period_cents,
        net_book_value_cents=nbv_cents,
        source_reference=f"fictional://asset/{asset_id}",
        manual_carryforward=manual_carryforward,
    )


def snapshot(period: str = "2026-02") -> AssetScheduleSnapshot:
    assets = (
        asset("ASSET-001"),
        asset("ASSET-002", cost_cents=60_000, accumulated_cents=12_000, period_cents=1_000, nbv_cents=48_000),
    )
    return AssetScheduleSnapshot(
        period=period,
        entity_id="ENTITY-DEMO",
        assets=assets,
        cached_cost_cents=180_000,
        cached_accumulated_depreciation_cents=48_000,
        cached_period_depreciation_cents=3_000,
        cached_net_book_value_cents=132_000,
    )


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def with_first(current: AssetScheduleSnapshot, **changes: object) -> AssetScheduleSnapshot:
    changed = replace(current.assets[0], **changes)
    return replace(current, assets=(changed,) + current.assets[1:])


def test_clean_schedule_is_validation_only_and_ready_for_human_review() -> None:
    result = PersonalPropertyTaxValidator(snapshot()).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.filing_authorized
    assert not result.posting_authorized
    assert result.asset_count == 2
    assert result.unique_asset_count == 2
    assert result.journal_entries == ()
    assert result.import_payloads == ()
    assert result.tax_filings == ()
    assert result.posting_actions == ()


@pytest.mark.parametrize("period", ["2026-2", "February 2026", "", "2026-13"])
def test_invalid_period_is_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        PersonalPropertyTaxValidator(replace(snapshot(), period=period))


def test_missing_asset_population_and_unsafe_entity_block() -> None:
    result = PersonalPropertyTaxValidator(replace(snapshot(), entity_id=" ENTITY", assets=())).validate()
    assert {"UNSAFE_ENTITY_ID", "ASSET_POPULATION_MISSING"}.issubset(codes(result))


@pytest.mark.parametrize(("field", "code"), [("asset_id", "UNSAFE_ASSET_ID"), ("category", "UNSAFE_ASSET_CATEGORY"), ("source_reference", "UNSAFE_SOURCE_REFERENCE")])
def test_blank_or_untrimmed_core_text_blocks(field: str, code: str) -> None:
    result = PersonalPropertyTaxValidator(with_first(snapshot(), **{field: " BAD"})).validate()
    assert code in codes(result)


def test_duplicate_asset_id_blocks() -> None:
    current = snapshot()
    duplicate = replace(current.assets[1], asset_id="ASSET-001")
    result = PersonalPropertyTaxValidator(replace(current, assets=(current.assets[0], duplicate))).validate()
    assert "DUPLICATE_ASSET_ID" in codes(result)
    assert result.unique_asset_count == 1


@pytest.mark.parametrize("value", ["2026-2-01", "", "2026-02-30"])
def test_invalid_placed_in_service_date_blocks(value: str) -> None:
    assert "PLACED_IN_SERVICE_INVALID" in codes(PersonalPropertyTaxValidator(with_first(snapshot(), placed_in_service=value)).validate())


def test_future_asset_date_blocks() -> None:
    assert "FUTURE_ASSET_DATE" in codes(PersonalPropertyTaxValidator(with_first(snapshot(), placed_in_service="2026-03-01")).validate())


@pytest.mark.parametrize("value", [None, "", "2029-02-30"])
def test_missing_or_invalid_depreciation_end_date_blocks(value: object) -> None:
    assert "DEPRECIATION_END_DATE_MISSING" in codes(PersonalPropertyTaxValidator(with_first(snapshot(), depreciation_end_date=value)).validate())


def test_depreciation_end_before_start_blocks() -> None:
    assert "DEPRECIATION_END_BEFORE_START" in codes(PersonalPropertyTaxValidator(with_first(snapshot(), depreciation_end_date="2024-08-31")).validate())


@pytest.mark.parametrize("value", [0, -1, 60.0, True, "60"])
def test_unsafe_useful_life_blocks(value: object) -> None:
    assert "USEFUL_LIFE_UNSAFE" in codes(PersonalPropertyTaxValidator(with_first(snapshot(), useful_life_months=value)).validate())


@pytest.mark.parametrize(("value", "code"), [(1.5, "MONTHS_USED_UNSAFE"), (True, "MONTHS_USED_UNSAFE"), (-1, "MONTHS_USED_OUT_OF_RANGE"), (61, "MONTHS_USED_OUT_OF_RANGE")])
def test_unsafe_or_out_of_range_months_used_blocks(value: object, code: str) -> None:
    assert code in codes(PersonalPropertyTaxValidator(with_first(snapshot(), months_used=value)).validate())


@pytest.mark.parametrize(("field", "code"), [("cost_cents", "UNSAFE_COST_AMOUNT"), ("accumulated_depreciation_cents", "UNSAFE_ACCUMULATED_AMOUNT"), ("period_depreciation_cents", "UNSAFE_PERIOD_AMOUNT"), ("net_book_value_cents", "UNSAFE_NBV_AMOUNT")])
@pytest.mark.parametrize("unsafe", [None, 1.5, True, "100"])
def test_unsafe_amount_types_block(field: str, code: str, unsafe: object) -> None:
    assert code in codes(PersonalPropertyTaxValidator(with_first(snapshot(), **{field: unsafe})).validate())


def test_asset_level_net_book_value_must_rederive() -> None:
    assert "NET_BOOK_VALUE_OUT_OF_TIE" in codes(PersonalPropertyTaxValidator(with_first(snapshot(), net_book_value_cents=83_999)).validate())


def test_negative_cost_and_manual_carryforward_are_visible_warnings() -> None:
    current = with_first(snapshot(), cost_cents=-10_000, accumulated_depreciation_cents=-2_000, period_depreciation_cents=-500, net_book_value_cents=-8_000, manual_carryforward=True)
    current = replace(current, cached_cost_cents=50_000, cached_accumulated_depreciation_cents=10_000, cached_period_depreciation_cents=500, cached_net_book_value_cents=40_000)
    result = PersonalPropertyTaxValidator(current).validate()
    assert {"NEGATIVE_COST_REVIEW", "MANUAL_CARRYFORWARD_REVIEW"}.issubset(codes(result))
    assert result.negative_cost_count == 1
    assert result.manual_carryforward_count == 1
    assert result.mechanical_clean


def test_manual_carryforward_flag_must_be_boolean() -> None:
    assert "MANUAL_CARRYFORWARD_FLAG_UNSAFE" in codes(PersonalPropertyTaxValidator(with_first(snapshot(), manual_carryforward="yes")).validate())


@pytest.mark.parametrize(("field", "code"), [("cached_cost_cents", "COST_TOTAL_OUT_OF_TIE"), ("cached_accumulated_depreciation_cents", "ACCUMULATED_DEPRECIATION_TOTAL_OUT_OF_TIE"), ("cached_period_depreciation_cents", "PERIOD_DEPRECIATION_TOTAL_OUT_OF_TIE"), ("cached_net_book_value_cents", "NET_BOOK_VALUE_TOTAL_OUT_OF_TIE")])
def test_cached_totals_must_independently_readd(field: str, code: str) -> None:
    assert code in codes(PersonalPropertyTaxValidator(replace(snapshot(), **{field: 1})).validate())


@pytest.mark.parametrize("unsafe", [None, 1.5, True, "100"])
def test_cached_totals_must_use_integer_cents(unsafe: object) -> None:
    assert "UNSAFE_CACHED_TOTAL" in codes(PersonalPropertyTaxValidator(replace(snapshot(), cached_cost_cents=unsafe)).validate())


def test_displayed_control_must_be_integer_zero() -> None:
    assert "DISPLAYED_CONTROL_UNSAFE" in codes(PersonalPropertyTaxValidator(replace(snapshot(), displayed_control_difference_cents="OOB")).validate())
    assert "DISPLAYED_CONTROL_OUT_OF_BALANCE" in codes(PersonalPropertyTaxValidator(replace(snapshot(), displayed_control_difference_cents=1)).validate())


def test_prior_must_be_same_month_in_prior_year() -> None:
    assert "PRIOR_PERIOD_MISMATCH" not in codes(PersonalPropertyTaxValidator(snapshot("2026-02"), snapshot("2025-02")).validate())
    assert "PRIOR_PERIOD_MISMATCH" in codes(PersonalPropertyTaxValidator(snapshot("2026-02"), snapshot("2025-01")).validate())


def test_prior_entity_must_match() -> None:
    prior = replace(snapshot("2025-02"), entity_id="ENTITY-OTHER")
    assert "PRIOR_ENTITY_MISMATCH" in codes(PersonalPropertyTaxValidator(snapshot(), prior).validate())


def test_annual_asset_population_and_term_changes_are_warnings() -> None:
    current = snapshot()
    prior = AssetScheduleSnapshot(period="2025-02", entity_id=current.entity_id, assets=(replace(current.assets[0], cost_cents=119_000), asset("ASSET-OLD")), cached_cost_cents=239_000, cached_accumulated_depreciation_cents=72_000, cached_period_depreciation_cents=4_000, cached_net_book_value_cents=168_000)
    result = PersonalPropertyTaxValidator(current, prior).validate()
    assert "ASSET_POPULATION_CHANGED" in codes(result)
    assert result.asset_added_count == 1
    assert result.asset_removed_count == 1
    assert result.asset_term_changed_count == 1
    assert result.mechanical_clean
