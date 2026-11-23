from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.headcount import (
    EntityHeadcount,
    HeadcountSnapshot,
    HeadcountValidator,
)


def entity(entity_id: str, counts: tuple[object, ...]) -> EntityHeadcount:
    return EntityHeadcount(
        entity_id=entity_id,
        annual_counts=counts,
        source_reference=f"fictional://headcount/{entity_id}",
    )


def _totals(entities: tuple[EntityHeadcount, ...], year_count: int) -> tuple[int, ...]:
    return tuple(
        sum(
            item.annual_counts[index]
            for item in entities
            if index < len(item.annual_counts)
            and isinstance(item.annual_counts[index], int)
            and not isinstance(item.annual_counts[index], bool)
        )
        for index in range(year_count)
    )


def rebuild(snapshot: HeadcountSnapshot) -> HeadcountSnapshot:
    """Recompute cached column totals so a mutated snapshot stays crossfooted."""

    return replace(snapshot, cached_annual_totals=_totals(snapshot.entities, len(snapshot.annual_years)))


def current_snapshot() -> HeadcountSnapshot:
    years = (2026, 2025, 2024, 2023, 2022)
    entities = (
        entity("ENTITY-NORTH", (33, 31, 29, 28, 27)),
        entity("ENTITY-SOUTH", (25, 24, 23, 22, 20)),
        entity("ENTITY-EAST", (12, 13, 14, 15, 16)),
        entity("ENTITY-WEST", (8, 9, 10, 11, 12)),
    )
    return HeadcountSnapshot(
        as_of_year=2026,
        as_of_month=6,
        annual_years=years,
        entities=entities,
        cached_annual_totals=_totals(entities, len(years)),
        source_fingerprint="a" * 64,
    )


def prior_snapshot() -> HeadcountSnapshot:
    years = (2025, 2024, 2023, 2022)
    entities = (
        entity("ENTITY-NORTH", (31, 29, 28, 27)),
        entity("ENTITY-SOUTH", (24, 23, 22, 20)),
        entity("ENTITY-EAST", (13, 14, 15, 16)),
        entity("ENTITY-WEST", (9, 10, 11, 12)),
    )
    return HeadcountSnapshot(
        as_of_year=2025,
        as_of_month=6,
        annual_years=years,
        entities=entities,
        cached_annual_totals=_totals(entities, len(years)),
        source_fingerprint="b" * 64,
    )


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def with_entity(snapshot: HeadcountSnapshot, index: int, **changes: object) -> HeadcountSnapshot:
    changed = replace(snapshot.entities[index], **changes)
    entities = snapshot.entities[:index] + (changed,) + snapshot.entities[index + 1:]
    return replace(snapshot, entities=entities)


def test_clean_current_is_validation_only_and_ready_for_human_review() -> None:
    result = HeadcountValidator(current_snapshot()).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.payroll_update_authorized
    assert not result.audit_submission_authorized
    assert not result.posting_authorized
    assert result.entity_count == 4
    assert result.year_count == 5
    assert result.current_year_total == 78
    assert result.journal_entries == ()
    assert result.payroll_actions == ()
    assert result.import_payloads == ()
    assert result.audit_submissions == ()
    assert result.posting_actions == ()


@pytest.mark.parametrize("as_of_year", [1999, 2101, 2026.0, "2026"])
def test_invalid_as_of_year_is_rejected(as_of_year: object) -> None:
    with pytest.raises(ValueError, match="as_of_year"):
        HeadcountValidator(replace(current_snapshot(), as_of_year=as_of_year))


@pytest.mark.parametrize("as_of_month", [0, 13, 6.5, "6"])
def test_invalid_as_of_month_is_rejected(as_of_month: object) -> None:
    with pytest.raises(ValueError, match="as_of_month"):
        HeadcountValidator(replace(current_snapshot(), as_of_month=as_of_month))


def test_missing_population_blocks() -> None:
    result = HeadcountValidator(replace(current_snapshot(), entities=())).validate()
    assert "HEADCOUNT_POPULATION_MISSING" in codes(result)


@pytest.mark.parametrize(
    ("field", "code"),
    [("entity_id", "UNSAFE_ENTITY_ID"), ("source_reference", "UNSAFE_SOURCE_REFERENCE")],
)
def test_blank_or_untrimmed_core_text_blocks(field: str, code: str) -> None:
    result = HeadcountValidator(with_entity(current_snapshot(), 0, **{field: " BAD"})).validate()
    assert code in codes(result)


def test_duplicate_entity_row_blocks() -> None:
    current = with_entity(current_snapshot(), 1, entity_id="ENTITY-NORTH")
    assert "DUPLICATE_ENTITY" in codes(HeadcountValidator(current).validate())


@pytest.mark.parametrize("length", [4, 6])
def test_count_vector_must_align_to_year_headers(length: int) -> None:
    current = with_entity(current_snapshot(), 0, annual_counts=(0,) * length)
    assert "COUNT_VECTOR_LENGTH" in codes(HeadcountValidator(current).validate())


@pytest.mark.parametrize("unsafe", [None, 1.5, True, "5"])
def test_headcount_must_be_whole_integer(unsafe: object) -> None:
    counts = list(current_snapshot().entities[0].annual_counts)
    counts[0] = unsafe
    current = with_entity(current_snapshot(), 0, annual_counts=tuple(counts))
    assert "UNSAFE_HEADCOUNT" in codes(HeadcountValidator(current).validate())


def test_negative_headcount_blocks_but_still_crossfoots() -> None:
    counts = list(current_snapshot().entities[0].annual_counts)
    counts[0] = -1
    current = rebuild(with_entity(current_snapshot(), 0, annual_counts=tuple(counts)))
    result = HeadcountValidator(current).validate()
    assert "NEGATIVE_HEADCOUNT" in codes(result)
    assert "TOTAL_OUT_OF_TIE" not in codes(result)
    assert result.negative_count == 1
    assert not result.mechanical_clean


def test_year_headers_must_start_with_as_of_year() -> None:
    current = replace(current_snapshot(), annual_years=(2027, 2026, 2025, 2024, 2023))
    assert "YEAR_HEADER_START_MISMATCH" in codes(HeadcountValidator(current).validate())


def test_year_headers_must_descend_consecutively() -> None:
    current = replace(current_snapshot(), annual_years=(2026, 2025, 2023, 2022, 2021))
    assert "YEAR_HEADERS_NOT_CONSECUTIVE" in codes(HeadcountValidator(current).validate())


def test_duplicate_year_header_blocks() -> None:
    current = replace(current_snapshot(), annual_years=(2026, 2025, 2025, 2024, 2023))
    assert "DUPLICATE_YEAR_HEADER" in codes(HeadcountValidator(current).validate())


@pytest.mark.parametrize("length", [4, 6])
def test_cached_total_vector_length(length: int) -> None:
    current = replace(current_snapshot(), cached_annual_totals=(0,) * length)
    assert "TOTAL_VECTOR_LENGTH" in codes(HeadcountValidator(current).validate())


def test_cached_total_must_readd_and_be_nonnegative_integer() -> None:
    current = current_snapshot()
    totals = list(current.cached_annual_totals)
    totals[0] += 1
    assert "TOTAL_OUT_OF_TIE" in codes(HeadcountValidator(replace(current, cached_annual_totals=tuple(totals))).validate())
    totals[0] = 1.5
    assert "UNSAFE_CACHED_TOTAL" in codes(HeadcountValidator(replace(current, cached_annual_totals=tuple(totals))).validate())
    totals[0] = -1
    assert "NEGATIVE_CACHED_TOTAL" in codes(HeadcountValidator(replace(current, cached_annual_totals=tuple(totals))).validate())


@pytest.mark.parametrize("fingerprint", ["", "A" * 64, "a" * 63, "private-path"])
def test_source_fingerprint_must_be_lowercase_sha256(fingerprint: str) -> None:
    result = HeadcountValidator(replace(current_snapshot(), source_fingerprint=fingerprint)).validate()
    assert "UNSAFE_SOURCE_FINGERPRINT" in codes(result)


def test_clean_current_prior_pair_ties_and_flags_review() -> None:
    result = HeadcountValidator(current_snapshot(), prior_snapshot()).validate()
    assert result.mechanical_clean
    assert "ANNUAL_CHANGE_REVIEW" in codes(result)
    assert "TOTAL_CHANGE_OUT_OF_TIE" not in codes(result)
    assert "HISTORICAL_VALUE_CHANGED" not in codes(result)
    assert result.current_year_total == 78
    assert result.prior_year_total == 77
    assert result.annual_total_change == 1
    assert result.entity_change_sum == 1
    assert result.historical_change_count == 0
    assert result.entity_added_count == 0
    assert result.entity_removed_count == 0


def test_prior_year_must_be_immediately_preceding() -> None:
    prior = replace(prior_snapshot(), as_of_year=2024)
    assert "PRIOR_YEAR_MISMATCH" in codes(HeadcountValidator(current_snapshot(), prior).validate())


def test_prior_month_must_match_current() -> None:
    prior = replace(prior_snapshot(), as_of_month=5)
    assert "PRIOR_MONTH_MISMATCH" in codes(HeadcountValidator(current_snapshot(), prior).validate())


def test_identical_sequential_fingerprints_are_visible_warning() -> None:
    prior = replace(prior_snapshot(), source_fingerprint="a" * 64)
    result = HeadcountValidator(current_snapshot(), prior).validate()
    assert "IDENTICAL_PERIOD_FINGERPRINTS" in codes(result)
    assert result.mechanical_clean


def test_entity_population_change_is_visible_warning() -> None:
    prior = with_entity(prior_snapshot(), 3, entity_id="ENTITY-OLD")
    result = HeadcountValidator(current_snapshot(), prior).validate()
    assert "ENTITY_POPULATION_CHANGED" in codes(result)
    assert result.entity_added_count == 1
    assert result.entity_removed_count == 1
    assert result.mechanical_clean


def test_changed_overlapping_history_blocks() -> None:
    counts = list(current_snapshot().entities[0].annual_counts)
    counts[1] = 32  # prior-year (2025) value differs from the prior snapshot's 31
    current = rebuild(with_entity(current_snapshot(), 0, annual_counts=tuple(counts)))
    result = HeadcountValidator(current, prior_snapshot()).validate()
    assert "HISTORICAL_VALUE_CHANGED" in codes(result)
    assert result.historical_change_count == 1
    assert not result.mechanical_clean
