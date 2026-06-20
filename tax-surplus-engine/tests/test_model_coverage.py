"""Coverage for the data-model layer (``surplus_engine.model``).

Pins down the validation invariants on :class:`Entity` and :class:`YearFacts`,
the pool-identifier ordering constants, :class:`PoolBalances` accessor/mutator
semantics, the :class:`FxTable` conversion rules, and the :class:`Structure`
traversal helpers. All inputs are fictional and hand-built.
"""

from __future__ import annotations

import pytest

from surplus_engine.model import (
    EXEMPT,
    PREACQ,
    POOL_ORDER,
    TAXABLE,
    Entity,
    FxTable,
    PoolBalances,
    Structure,
    YearFacts,
)
from tests.conftest import make_entity, make_facts, make_structure


# --------------------------------------------------------------------------- #
# Pool identifier constants
# --------------------------------------------------------------------------- #
def test_pool_order_is_statutory_sequence():
    # Waterfall consumes exempt -> taxable -> pre-acq; the constant must match.
    assert POOL_ORDER == (EXEMPT, TAXABLE, PREACQ)
    assert POOL_ORDER == ("exempt_surplus", "taxable_surplus", "pre_acquisition_capital")


def test_pool_identifiers_are_distinct():
    assert len({EXEMPT, TAXABLE, PREACQ}) == 3


@pytest.mark.parametrize("pool", [EXEMPT, TAXABLE, PREACQ])
def test_pool_identifiers_are_poolbalances_attributes(pool):
    # Each identifier must be a real attribute name the waterfall can get/set.
    assert hasattr(PoolBalances(), pool)


# --------------------------------------------------------------------------- #
# Entity validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pct", [-0.01, 1.01, 1.5, -5.0, 2.0])
def test_entity_rejects_ownership_out_of_unit_interval(pct):
    with pytest.raises(ValueError, match="ownership_pct"):
        Entity(code="X", name="X", tier=0, currency="USD", parent="P", ownership_pct=pct)


@pytest.mark.parametrize("pct", [0.0, 0.5, 1.0])
def test_entity_accepts_ownership_on_unit_interval(pct):
    e = Entity(code="X", name="X", tier=0, currency="USD", parent="P", ownership_pct=pct)
    assert e.ownership_pct == pct


def test_top_entity_must_be_fully_owned():
    with pytest.raises(ValueError, match="must have ownership_pct 1.0"):
        Entity(code="TOP", name="Top", tier=3, currency="CAD", parent=None, ownership_pct=0.9)


def test_top_entity_with_full_ownership_is_valid():
    e = Entity(code="TOP", name="Top", tier=3, currency="CAD", parent=None, ownership_pct=1.0)
    assert e.parent is None and e.ownership_pct == 1.0


def test_entity_is_frozen():
    e = make_entity("X", tier=0, parent=None, ownership_pct=1.0)
    with pytest.raises(Exception):
        e.tier = 5  # frozen dataclass -> mutation forbidden


# --------------------------------------------------------------------------- #
# YearFacts validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("portion", [-0.01, 1.01, 2.0, -1.0])
def test_yearfacts_rejects_exempt_portion_out_of_range(portion):
    with pytest.raises(ValueError, match="exempt_portion"):
        make_facts("X", 2021, income=100, exempt_portion=portion)


@pytest.mark.parametrize(
    "field_kwargs",
    [
        {"distribution": -1.0},
        {"capital_contribution": -1.0},
        {"return_of_capital": -1.0},
    ],
)
def test_yearfacts_rejects_negative_cash_fields(field_kwargs):
    with pytest.raises(ValueError, match="must be >= 0"):
        make_facts("X", 2021, income=100, **field_kwargs)


def test_yearfacts_rejects_return_of_capital_exceeding_distribution():
    with pytest.raises(ValueError, match="cannot exceed distribution"):
        make_facts("X", 2021, distribution=100.0, return_of_capital=150.0)


def test_yearfacts_allows_return_of_capital_equal_to_distribution():
    f = make_facts("X", 2021, distribution=100.0, return_of_capital=100.0)
    assert f.return_of_capital == f.distribution == 100.0


def test_yearfacts_allows_negative_income():
    # A standalone loss is a legitimate input (it is floored later in the engine).
    f = make_facts("X", 2021, income=-250_000.0)
    assert f.standalone_taxable_income == -250_000.0


def test_yearfacts_is_frozen():
    f = make_facts("X", 2021, income=100)
    with pytest.raises(Exception):
        f.distribution = 999


# --------------------------------------------------------------------------- #
# PoolBalances
# --------------------------------------------------------------------------- #
def test_poolbalances_defaults_to_zero():
    pb = PoolBalances()
    assert pb.exempt_surplus == 0.0
    assert pb.taxable_surplus == 0.0
    assert pb.pre_acquisition_capital == 0.0
    assert pb.acb == 0.0


@pytest.mark.parametrize(
    "pool,expected",
    [(EXEMPT, 10.0), (TAXABLE, 5.0), (PREACQ, 2.0), ("acb", 3.0)],
)
def test_poolbalances_get_reads_each_field(pool, expected):
    pb = PoolBalances(exempt_surplus=10.0, taxable_surplus=5.0,
                      pre_acquisition_capital=2.0, acb=3.0)
    assert pb.get(pool) == expected


def test_poolbalances_add_accumulates():
    pb = PoolBalances(exempt_surplus=10.0)
    pb.add(EXEMPT, 5.0)
    pb.add(EXEMPT, -3.0)
    assert pb.get(EXEMPT) == 12.0


def test_poolbalances_copy_is_independent():
    pb = PoolBalances(exempt_surplus=10.0, acb=4.0)
    clone = pb.copy()
    clone.add(EXEMPT, 100.0)
    clone.acb = 999.0
    # Mutating the copy must not touch the original.
    assert pb.exempt_surplus == 10.0
    assert pb.acb == 4.0
    assert clone.exempt_surplus == 110.0


def test_poolbalances_copy_preserves_all_fields():
    pb = PoolBalances(exempt_surplus=1.0, taxable_surplus=2.0,
                      pre_acquisition_capital=3.0, acb=4.0)
    c = pb.copy()
    assert (c.exempt_surplus, c.taxable_surplus, c.pre_acquisition_capital, c.acb) == \
        (1.0, 2.0, 3.0, 4.0)


# --------------------------------------------------------------------------- #
# FxTable
# --------------------------------------------------------------------------- #
def test_fxtable_cad_is_unit_rate_even_without_table_entry():
    # A CAD entity needs no USD->CAD entry; rate is always 1.0.
    fx = FxTable(usd_cad={})
    assert fx.rate(2021, "CAD") == 1.0


def test_fxtable_usd_rate_reads_from_table():
    fx = FxTable(usd_cad={2021: 1.40, 2022: 1.35})
    assert fx.rate(2021, "USD") == 1.40
    assert fx.rate(2022, "USD") == 1.35


def test_fxtable_unsupported_currency_raises_value_error():
    fx = FxTable(usd_cad={2021: 1.40})
    with pytest.raises(ValueError, match="unsupported currency"):
        fx.rate(2021, "EUR")


def test_fxtable_missing_year_raises_key_error():
    fx = FxTable(usd_cad={2021: 1.40})
    with pytest.raises(KeyError):
        fx.rate(2099, "USD")


def test_fxtable_missing_year_is_irrelevant_for_cad():
    # CAD short-circuits before the year lookup.
    fx = FxTable(usd_cad={2021: 1.40})
    assert fx.rate(2099, "CAD") == 1.0


# --------------------------------------------------------------------------- #
# Structure traversal helpers
# --------------------------------------------------------------------------- #
def _three_tier_structure() -> Structure:
    op = make_entity("OP", tier=0, parent="MID", ownership_pct=0.8)
    mid = make_entity("MID", tier=1, parent="TOP", ownership_pct=0.9)
    top = make_entity("TOP", tier=2, parent=None, ownership_pct=1.0)
    facts = [make_facts("OP", 2021, income=100)]
    return make_structure([op, mid, top], facts, years=[2021])


def test_children_of_returns_only_direct_subsidiaries():
    s = _three_tier_structure()
    assert [e.code for e in s.children_of("MID")] == ["OP"]
    assert [e.code for e in s.children_of("TOP")] == ["MID"]


def test_children_of_leaf_is_empty():
    s = _three_tier_structure()
    assert s.children_of("OP") == []


def test_children_of_unknown_code_is_empty():
    s = _three_tier_structure()
    assert s.children_of("DOES_NOT_EXIST") == []


def test_ordered_bottom_up_sorts_by_tier_then_code():
    s = _three_tier_structure()
    assert [e.code for e in s.ordered_bottom_up()] == ["OP", "MID", "TOP"]


def test_ordered_bottom_up_breaks_ties_by_code():
    a = make_entity("ZEBRA", tier=0, parent="TOP", ownership_pct=1.0)
    b = make_entity("ALPHA", tier=0, parent="TOP", ownership_pct=1.0)
    top = make_entity("TOP", tier=1, parent=None, ownership_pct=1.0)
    s = make_structure([a, b, top], [make_facts("TOP", 2021, income=0)], years=[2021])
    ordered = [e.code for e in s.ordered_bottom_up()]
    assert ordered == ["ALPHA", "ZEBRA", "TOP"]
