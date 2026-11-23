"""Curated invariant grid for the annual headcount validator.

Generates a Cartesian product of entity counts x year counts x value patterns
(~1,000 cases) of fully fictional, well-formed headcount snapshots. Each case
asserts the load-bearing invariants: a clean snapshot is mechanically clean and
`READY FOR HUMAN REVIEW`, the entity and year counts are reported exactly, and
the current-year total the validator reports equals an independent re-add of
the as-of column. Every point must hold, so any case fails on a real defect in
the validator's re-add, year-structure, or verdict logic.

All data is fictional and generated at import time; the file stays small.
"""

from __future__ import annotations

import itertools

import pytest

from close_engine.headcount import EntityHeadcount, HeadcountSnapshot, HeadcountValidator


_AS_OF_YEAR = 2026
_ENTITY_COUNTS = range(1, 26)          # 25 values
_YEAR_COUNTS = range(1, 11)            # 10 values
_PATTERNS = [(0, 0), (1, 1), (10, 3), (100, 7)]   # (base, step) -> 4 values
_GRID = list(itertools.product(_ENTITY_COUNTS, _YEAR_COUNTS, _PATTERNS))  # 1,000


def _snapshot(entities: int, years: int, base: int, step: int):
    annual_years = tuple(_AS_OF_YEAR - offset for offset in range(years))
    rows = tuple(
        EntityHeadcount(
            entity_id=f"ENTITY-{k:03d}",
            annual_counts=tuple(base + step * offset + k for offset in range(years)),
            source_reference=f"fictional://headcount/{k:03d}",
        )
        for k in range(entities)
    )
    totals = tuple(sum(row.annual_counts[offset] for row in rows) for offset in range(years))
    snapshot = HeadcountSnapshot(
        as_of_year=_AS_OF_YEAR,
        as_of_month=6,
        annual_years=annual_years,
        entities=rows,
        cached_annual_totals=totals,
        source_fingerprint="a" * 64,
    )
    return snapshot, rows


@pytest.mark.parametrize("entities,years,pattern", _GRID)
def test_clean_headcount_snapshot_holds_every_invariant(entities, years, pattern):
    base, step = pattern
    snapshot, rows = _snapshot(entities, years, base, step)
    result = HeadcountValidator(snapshot).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.entity_count == entities
    assert result.year_count == years
    assert result.current_year_total == sum(row.annual_counts[0] for row in rows)
    assert result.validation_only
    assert not result.posting_authorized
    assert result.findings == () or all(f.severity != "ERROR" for f in result.findings)
