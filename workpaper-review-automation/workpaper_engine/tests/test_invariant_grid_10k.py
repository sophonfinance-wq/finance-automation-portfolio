"""Extended curated invariant grid -- exact identities over the money kernel and
the two controls whose correctness is a property, not a case.

Every assertion below is an exact equality or an exact classification checked
across a bounded integer-cent domain, so it gates CI on every push rather than
living behind ``SWEEP=1``. ``SWEEP=1`` widens the same grids rather than adding
different ones, so a sweep failure always reproduces at the gated size.

Two of these grids are not arithmetic. ``CITATION_MISMATCH`` and ``DATE_MISREAD``
are the controls this engine exists for, and both have a property that must hold
at *every* point of a domain rather than at a few chosen cases:

* a citation matches **iff** the quoted figure equals the resolved figure -- with
  no tolerance anywhere, including at a distance of exactly one cent, which is
  where a tolerance band would hide the defect;
* a value is a date candidate **iff** it is a whole number of dollars inside the
  serial band -- and being a candidate never by itself converts anything, because
  the structural rule is that a date is never an addend.
"""

from __future__ import annotations

import itertools
import os

import pytest

from workpaper_engine.engine import (
    FAIL,
    FLAG,
    control_citation_mismatch,
    control_date_misread,
)
from workpaper_engine.model import (
    DATE_SERIAL_HIGH,
    DATE_SERIAL_LOW,
    Citation,
    Package,
    WorkpaperCell,
)
from workpaper_engine.money import allocate_by_ratio, apply_rate, split_evenly

SWEEP = os.environ.get("SWEEP") == "1"


def _pkg(cells=(), citations=()) -> Package:
    return Package(
        doc_type="workpaper_package",
        package_id="GRID",
        entity="Invented Holdings LLC",
        period_label="FYE 6/30/2026",
        attachment_sha256="0" * 64,
        cells=tuple(cells),
        citations=tuple(citations),
    )


def _cell(value_cents: int, *, kind: str = "amount", feeds_total: bool = False) -> WorkpaperCell:
    return WorkpaperCell(
        sheet="Consolidation",
        cell="D20",
        label="Grid cell",
        value_cents=value_cents,
        origin="sourced",
        is_current_year=True,
        display_kind=kind,
        feeds_total=feeds_total,
        source_ref="SRC-GRID",
    )


# --------------------------------------------------------------------------- #
# Grid 1: split_evenly conserves the total exactly. 2,000 totals x 3 = 6,000.
# --------------------------------------------------------------------------- #
_SPLIT_GRID = list(itertools.product(range(-1000, 1000), range(1, 4)))


@pytest.mark.parametrize("total_cents,parts", _SPLIT_GRID)
def test_split_evenly_conserves_total(total_cents: int, parts: int) -> None:
    got = split_evenly(total_cents, parts)
    assert len(got) == parts
    assert sum(got) == total_cents
    if parts > 1:
        assert len(set(got[:-1])) == 1
        assert got[0] == total_cents // parts
    assert split_evenly(total_cents, parts) == got


# --------------------------------------------------------------------------- #
# Grid 2: allocate_by_ratio neither loses nor mints a cent. A flow-through leg
# derived as receipts x profit percentage is built with it, and the weights below
# are the shapes a two- and three-member split actually takes.
# 1,000 totals x 2 shapes = 2,000.
# --------------------------------------------------------------------------- #
_WEIGHT_SHAPES: tuple[tuple[int, ...], ...] = ((2569, 7431), (2500, 2500, 5000))
_ALLOC_GRID = list(itertools.product(range(0, 1000), _WEIGHT_SHAPES))


@pytest.mark.parametrize("total_cents,weights", _ALLOC_GRID)
def test_allocate_by_ratio_conserves_total(total_cents: int, weights: tuple[int, ...]) -> None:
    parts = allocate_by_ratio(total_cents, weights)
    assert len(parts) == len(weights)
    assert sum(parts) == total_cents
    assert allocate_by_ratio(total_cents, weights) == parts


# --------------------------------------------------------------------------- #
# Grid 3: apply_rate is exact truncating integer math, bounded by its base.
# 100 bases x 20 rates = 2,000.
# --------------------------------------------------------------------------- #
_RATE_GRID = list(itertools.product(range(0, 100), range(0, 10000, 500)))


@pytest.mark.parametrize("base_cents,rate_bps", _RATE_GRID)
def test_apply_rate_is_exact_and_bounded(base_cents: int, rate_bps: int) -> None:
    got = apply_rate(base_cents, rate_bps)
    assert got == base_cents * rate_bps // 10000
    assert 0 <= got <= base_cents


# --------------------------------------------------------------------------- #
# Grid 4: CITATION_MISMATCH fires iff the quoted figure differs from the resolved
# figure. The offsets deliberately include +/-1 cent, because a rounding-sized
# gap is exactly the one a tolerance band would swallow and exactly the one that
# survives longest in a real package. 1,000 bases x 5 offsets = 5,000.
# --------------------------------------------------------------------------- #
_BASES = range(46_000_00, 46_100_00, 10)          # 1,000 bases, inside the date band
_OFFSETS = (-100, -1, 0, 1, 100)


@pytest.mark.parametrize("base_cents", _BASES)
@pytest.mark.parametrize("offset_cents", _OFFSETS)
def test_citation_matches_iff_amounts_are_equal(base_cents: int, offset_cents: int) -> None:
    target = _cell(base_cents)
    cite = Citation(
        citation_id="E-GRID",
        describes="grid",
        quoted_cents=base_cents + offset_cents,
        resolves_to=target.address,
    )
    found = control_citation_mismatch(_pkg([target], [cite]))
    if offset_cents == 0:
        assert found == []
    else:
        assert len(found) == 1
        f = found[0]
        assert f.severity == FAIL
        assert f.detail["difference_cents"] == -offset_cents
        assert f.detail["rounding_sized"] is (abs(offset_cents) <= 100)


# --------------------------------------------------------------------------- #
# Grid 5: a value is a date candidate iff it is whole dollars inside the serial
# band. Straddles both boundaries and includes fractional cents, which can never
# be a date however date-shaped the dollar part looks.
# 2,000 wholes x 2 cent-parts = 4,000.
# --------------------------------------------------------------------------- #
_WHOLES = range(DATE_SERIAL_LOW - 1000, DATE_SERIAL_LOW + 1000)
_CENTS = (0, 37)


@pytest.mark.parametrize("whole", _WHOLES)
@pytest.mark.parametrize("cents", _CENTS)
def test_date_candidacy_is_exactly_whole_dollars_in_band(whole: int, cents: int) -> None:
    value = whole * 100 + cents
    cell = _cell(value, kind="amount")
    expected = cents == 0 and DATE_SERIAL_LOW <= whole <= DATE_SERIAL_HIGH
    assert cell.in_date_serial_range is expected

    fired = [f for f in control_date_misread(_pkg([cell])) if f.control == "DATE_MISREAD"]
    assert bool(fired) is expected
    if expected:
        # A candidate is flagged and protected -- never silently converted.
        assert fired[0].severity == FLAG
        assert fired[0].detail["protected"] is True


# --------------------------------------------------------------------------- #
# Grid 6: the structural rule. A cell presented as a date that is an addend in a
# total is a hard failure at every point of the band -- its value can never make
# it acceptable, because a date is never an addend. 1,000 points.
# --------------------------------------------------------------------------- #
_ADDEND_GRID = range(DATE_SERIAL_LOW, DATE_SERIAL_LOW + 1000)


@pytest.mark.parametrize("whole", _ADDEND_GRID)
def test_a_date_is_never_an_addend(whole: int) -> None:
    cell = _cell(whole * 100, kind="date", feeds_total=True)
    fired = control_date_misread(_pkg([cell]))
    assert len(fired) == 1
    assert fired[0].severity == FAIL
    assert fired[0].detail["feeds_total"] is True


# --------------------------------------------------------------------------- #
# SWEEP=1 widens grids 4 and 5 rather than adding new ones, so any sweep failure
# reproduces at the gated size.
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not SWEEP, reason="set SWEEP=1 to run the wide sweep")
def test_sweep_citation_and_date_bands() -> None:
    for base in range(45_000_00, 47_500_00, 100):
        target = _cell(base)
        for offset in (-1, 0, 1):
            cite = Citation("E", "grid", base + offset, target.address)
            found = control_citation_mismatch(_pkg([target], [cite]))
            assert (found == []) is (offset == 0)
    for whole in range(DATE_SERIAL_LOW - 5000, DATE_SERIAL_HIGH + 5000):
        cell = _cell(whole * 100, kind="amount")
        assert cell.in_date_serial_range is (DATE_SERIAL_LOW <= whole <= DATE_SERIAL_HIGH)
