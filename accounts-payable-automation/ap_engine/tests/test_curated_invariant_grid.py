"""Curated invariant grid -- bounded, and it gates CI.

Every identity below is **exact** over the integer domain it is swept across.
The grid is deliberately kept in the low thousands so it stays fast enough to
run on every push; the unbounded version lives in ``test_bulk_invariant_grid.py``
behind ``SWEEP=1``.

Invariants:

* ``sum(split_evenly(t, n)) == t`` for every integer total and every period
  count, with the remainder always on the final part.
* ``sum(allocate_by_ratio(t, w)) == t`` whenever the weights sum to 10000 bps,
  no matter how the remainder falls.
* ``apply_rate(b, r)`` is exactly ``b * r // 10000`` and never exceeds the base
  for a rate at or below 100.00%.
* ``fmt`` round-trips through ``to_cents`` for every two-decimal value.
* The verdict rollup is FAIL > FLAG > PASS for every combination of statuses.
"""

from __future__ import annotations

import itertools

import pytest

from ap_engine.model import DocumentReport, Finding, Status, Verdict
from ap_engine.money import allocate_by_ratio, apply_rate, fmt, split_evenly, to_cents

# --------------------------------------------------------------------------- #
# Grid 1: split_evenly conserves the total exactly. 150 totals x 5 period
# counts = 750 cases, spanning negatives, zero and positives.
# --------------------------------------------------------------------------- #
_SPLIT_TOTALS = range(-75, 75)  # 150 values
_SPLIT_PERIODS = range(1, 6)  # 5 values
_SPLIT_GRID = list(itertools.product(_SPLIT_TOTALS, _SPLIT_PERIODS))


@pytest.mark.parametrize("total_cents,periods", _SPLIT_GRID)
def test_split_evenly_conserves_the_total(total_cents: int, periods: int) -> None:
    parts = split_evenly(total_cents, periods)
    assert len(parts) == periods
    assert sum(parts) == total_cents
    # Every part but the last is the same floor value, so no drift accumulates.
    if periods > 1:
        assert len(set(parts[:-1])) == 1
        assert parts[0] == total_cents // periods
    # Determinism: the pure function returns the same list on a second call.
    assert split_evenly(total_cents, periods) == parts


# --------------------------------------------------------------------------- #
# Grid 2: allocate_by_ratio creates and loses no penny. 150 totals x 4 weight
# shapes = 600 cases, including a lopsided split and a single full weight.
# --------------------------------------------------------------------------- #
_WEIGHT_SHAPES: tuple[tuple[int, ...], ...] = (
    (10_000,),
    (5_000, 5_000),
    (3_333, 3_333, 3_334),
    (1, 9_999),
)
_ALLOC_TOTALS = range(0, 150)  # 150 values
_ALLOC_GRID = list(itertools.product(_ALLOC_TOTALS, _WEIGHT_SHAPES))


@pytest.mark.parametrize("total_cents,weights", _ALLOC_GRID)
def test_allocate_by_ratio_conserves_the_total(
    total_cents: int, weights: tuple[int, ...]
) -> None:
    parts = allocate_by_ratio(total_cents, weights)
    assert len(parts) == len(weights)
    assert sum(parts) == total_cents
    assert all(isinstance(p, int) and p >= 0 for p in parts)
    # Each part is within one cent of its exact share, which is what the
    # largest-remainder method guarantees.
    for part, weight in zip(parts, weights, strict=True):
        exact = total_cents * weight
        assert exact // 10_000 <= part <= exact // 10_000 + 1


# --------------------------------------------------------------------------- #
# Grid 3: apply_rate is exact truncating arithmetic. 40 bases x 5 rates = 200.
# --------------------------------------------------------------------------- #
_RATE_BASES = range(0, 400, 10)  # 40 values
_RATES = (0, 875, 1_000, 5_000, 10_000)  # 5 values
_RATE_GRID = list(itertools.product(_RATE_BASES, _RATES))


@pytest.mark.parametrize("base_cents,rate_bps", _RATE_GRID)
def test_apply_rate_is_exact_and_bounded(base_cents: int, rate_bps: int) -> None:
    rated = apply_rate(base_cents, rate_bps)
    assert rated == base_cents * rate_bps // 10_000
    assert 0 <= rated <= base_cents
    # A retention plus its net always foots back to the base, exactly.
    assert rated + (base_cents - rated) == base_cents


# --------------------------------------------------------------------------- #
# Grid 4: fmt round-trips through to_cents for every two-decimal value.
# 400 values across the sign boundary.
# --------------------------------------------------------------------------- #
_FMT_VALUES = range(-200, 200)  # 400 values


@pytest.mark.parametrize("cents", _FMT_VALUES)
def test_fmt_round_trips(cents: int) -> None:
    text = fmt(cents)
    assert to_cents(text.replace(",", "")) == cents
    assert text.count(".") == 1
    assert len(text.split(".")[1]) == 2
    assert (text.startswith("-")) == (cents < 0)


# --------------------------------------------------------------------------- #
# Grid 5: verdict precedence over every combination of three statuses.
# 3^3 = 27 cases.
# --------------------------------------------------------------------------- #
_STATUS_TRIPLES = list(itertools.product(list(Status), repeat=3))


@pytest.mark.parametrize("statuses", _STATUS_TRIPLES)
def test_verdict_precedence(statuses: tuple[Status, ...]) -> None:
    findings = [Finding(f"r{i}", s, "-", "m") for i, s in enumerate(statuses)]
    report = DocumentReport("d.json", findings)
    if Status.FAIL in statuses:
        expected = Verdict.FAIL
    elif Status.FLAG in statuses:
        expected = Verdict.REVIEW
    else:
        expected = Verdict.PASS
    assert report.verdict is expected
    counts = report.counts()
    assert sum(counts.values()) == len(statuses)
    assert counts["FAIL"] == statuses.count(Status.FAIL)
    assert counts["FLAG"] == statuses.count(Status.FLAG)
    assert counts["PASS"] == statuses.count(Status.PASS)
