"""Additional coverage for the distribution waterfall and money-rounding helpers
(``surplus_engine.engine.run_waterfall``, ``_r``, ``_split_current_surplus``).

Focus areas the existing ``test_waterfall.py`` does not cover: the money-rounding
normalisation (including ``-0.0`` and banker's rounding), the surplus split's
loss path, exact-cap boundary behaviour, conservation of cash across the
waterfall, and ordering invariants under parametrized inputs.
"""

from __future__ import annotations

import pytest

from surplus_engine.engine import _r, _split_current_surplus, run_waterfall
from surplus_engine.model import EXEMPT, PREACQ, TAXABLE, PoolBalances


# --------------------------------------------------------------------------- #
# _r : money rounding / normalisation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        (-0.0, 0.0),          # negative zero normalised
        (0.004, 0.0),         # rounds down to 0
        (0.005, 0.01),        # rounds up
        (1.005, 1.0),         # banker's rounding (round-half-to-even)
        (2.675, 2.67),        # banker's rounding artifact
        (123.456, 123.46),
        (-123.454, -123.45),
        (1000000.0, 1000000.0),
    ],
)
def test_r_rounds_to_money_precision(value, expected):
    assert _r(value) == expected


def test_r_never_returns_negative_zero():
    out = _r(-0.0)
    # 0.0 and -0.0 are equal but their sign bit differs; assert the positive one.
    import math
    assert not math.copysign(1.0, out) < 0


# --------------------------------------------------------------------------- #
# _split_current_surplus
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "surplus,portion,expected",
    [
        (1000.0, 0.4, (400.0, 600.0)),
        (1000.0, 0.0, (0.0, 1000.0)),     # nothing exempt
        (1000.0, 1.0, (1000.0, 0.0)),     # all exempt
        (0.0, 0.5, (0.0, 0.0)),           # zero surplus splits to zero
        (250.0, 0.25, (62.5, 187.5)),
    ],
)
def test_split_positive_surplus(surplus, portion, expected):
    assert _split_current_surplus(surplus, portion) == expected


@pytest.mark.parametrize("loss", [-1.0, -500.0, -1_234_567.89])
def test_split_loss_routes_entirely_to_taxable(loss):
    exempt_add, taxable_add = _split_current_surplus(loss, 0.7)
    # A loss never creates negative exempt surplus; it lands wholly on taxable.
    assert exempt_add == 0.0
    assert taxable_add == _r(loss)


def test_split_components_sum_back_to_surplus_for_gains():
    surplus = 987_654.32
    exempt_add, taxable_add = _split_current_surplus(surplus, 0.37)
    assert exempt_add + taxable_add == pytest.approx(surplus, abs=0.01)


# --------------------------------------------------------------------------- #
# run_waterfall : boundaries and conservation
# --------------------------------------------------------------------------- #
def test_waterfall_cap_exactly_equal_is_not_binding():
    # Exempt available equals the cap exactly -> the cap did not *limit* anything.
    opening = PoolBalances(exempt_surplus=60, taxable_surplus=1000)
    steps, cap, binding = run_waterfall(100, opening, exempt_cap_fraction=0.60)
    drawn = {s.pool: s.amount for s in steps}
    assert cap == 60.0
    assert binding is False
    assert drawn[EXEMPT] == 60
    assert drawn[TAXABLE] == 40


def test_waterfall_negative_distribution_is_noop():
    opening = PoolBalances(exempt_surplus=100)
    steps, cap, binding = run_waterfall(-50, opening)
    assert steps == []
    assert binding is False
    # Cap value still computed off the (negative) distribution, but no draws.
    assert cap == _r(-50 * 0.60)


def test_waterfall_conserves_cash_when_pools_suffice():
    opening = PoolBalances(exempt_surplus=500, taxable_surplus=500,
                           pre_acquisition_capital=500)
    dist = 900
    steps, _, _ = run_waterfall(dist, opening, exempt_cap_fraction=1.0)
    assert sum(s.amount for s in steps) == dist


def test_waterfall_total_drawn_capped_by_available_when_short():
    opening = PoolBalances(exempt_surplus=10, taxable_surplus=20,
                           pre_acquisition_capital=5)
    steps, _, _ = run_waterfall(1000, opening, exempt_cap_fraction=1.0)
    assert sum(s.amount for s in steps) == 35  # only what existed


@pytest.mark.parametrize(
    "ex,tx,pa,dist,expected_pools",
    [
        (100, 0, 0, 50, [EXEMPT]),
        (0, 100, 0, 50, [TAXABLE]),
        (0, 0, 100, 50, [PREACQ]),
        (10, 10, 10, 25, [EXEMPT, TAXABLE, PREACQ]),
        (10, 0, 10, 15, [EXEMPT, PREACQ]),  # taxable empty -> skipped
    ],
)
def test_waterfall_emits_only_pools_that_contribute(ex, tx, pa, dist, expected_pools):
    opening = PoolBalances(exempt_surplus=ex, taxable_surplus=tx,
                           pre_acquisition_capital=pa)
    steps, _, _ = run_waterfall(dist, opening, exempt_cap_fraction=1.0)
    assert [s.pool for s in steps] == expected_pools


def test_waterfall_empty_pools_yield_no_steps_for_positive_dist():
    opening = PoolBalances()  # all zero
    steps, _, binding = run_waterfall(100, opening, exempt_cap_fraction=1.0)
    assert steps == []
    assert binding is False


def test_waterfall_steps_never_exceed_per_pool_balance():
    opening = PoolBalances(exempt_surplus=30, taxable_surplus=20,
                           pre_acquisition_capital=10)
    steps, _, _ = run_waterfall(1000, opening, exempt_cap_fraction=1.0)
    drawn = {s.pool: s.amount for s in steps}
    assert drawn.get(EXEMPT, 0) <= 30
    assert drawn.get(TAXABLE, 0) <= 20
    assert drawn.get(PREACQ, 0) <= 10


def test_waterfall_zero_cap_routes_everything_past_exempt():
    # A 0% exempt cap means no exempt surplus may fund the distribution.
    opening = PoolBalances(exempt_surplus=1000, taxable_surplus=1000)
    steps, cap, binding = run_waterfall(100, opening, exempt_cap_fraction=0.0)
    drawn = {s.pool: s.amount for s in steps}
    assert cap == 0.0
    assert binding is True            # exempt could have funded but cap forbade it
    assert EXEMPT not in drawn
    assert drawn[TAXABLE] == 100


def test_waterfall_amounts_are_rounded_to_cents():
    opening = PoolBalances(exempt_surplus=1000)
    steps, _, _ = run_waterfall(33.337, opening, exempt_cap_fraction=1.0)
    # The single exempt draw must be money-rounded.
    assert steps[0].amount == 33.34
