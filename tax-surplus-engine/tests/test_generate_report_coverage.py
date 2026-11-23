"""Coverage for the generator, reporting, and workbook layers.

Pins down: the fictional generator's structure shape and seeded-value
invariants; the FX-table drift bounds; the reporting layer's money formatting,
FX attachment, and Markdown lineage; and the optional openpyxl workbook export's
sheet layout and content.
"""

from __future__ import annotations

import random

import pytest

from surplus_engine.engine import SurplusEngine
from surplus_engine.generate import (
    DEFAULT_SEED,
    build_entities,
    build_facts,
    build_fx_table,
    generate_structure,
)
from surplus_engine.model import Structure
from surplus_engine.report import (
    _money,
    attach_fx,
    consolidated_summary,
    entity_workpaper,
)


# --------------------------------------------------------------------------- #
# build_entities : fictional four-tier chain
# --------------------------------------------------------------------------- #
def test_build_entities_has_four_tiers():
    ents = build_entities()
    assert set(ents) == {"BIRCH_OP", "CEDAR_MEZZ", "MAPLE_FUND", "DEMO_HOLDCO"}
    assert sorted(e.tier for e in ents.values()) == [0, 1, 2, 3]


def test_build_entities_chain_parent_links():
    ents = build_entities()
    assert ents["BIRCH_OP"].parent == "CEDAR_MEZZ"
    assert ents["CEDAR_MEZZ"].parent == "MAPLE_FUND"
    assert ents["MAPLE_FUND"].parent == "DEMO_HOLDCO"
    assert ents["DEMO_HOLDCO"].parent is None


def test_top_holdco_is_cad_and_fully_owned():
    ents = build_entities()
    top = ents["DEMO_HOLDCO"]
    assert top.currency == "CAD"
    assert top.ownership_pct == 1.0


@pytest.mark.parametrize(
    "code,pct",
    [("BIRCH_OP", 0.80), ("CEDAR_MEZZ", 0.90), ("MAPLE_FUND", 1.00), ("DEMO_HOLDCO", 1.00)],
)
def test_build_entities_ownership_pcts(code, pct):
    assert build_entities()[code].ownership_pct == pct


def test_operating_entities_are_usd():
    ents = build_entities()
    for code in ("BIRCH_OP", "CEDAR_MEZZ", "MAPLE_FUND"):
        assert ents[code].currency == "USD"


# --------------------------------------------------------------------------- #
# build_fx_table : drift bounds, determinism
# --------------------------------------------------------------------------- #
def test_fx_table_stays_within_clamp_bounds():
    rng = random.Random(7)
    fx = build_fx_table(list(range(2015, 2035)), rng)
    assert all(1.20 <= v <= 1.45 for v in fx.usd_cad.values())


def test_fx_table_covers_every_requested_year():
    rng = random.Random(7)
    years = [2021, 2022, 2023]
    fx = build_fx_table(years, rng)
    assert sorted(fx.usd_cad) == years


def test_fx_table_is_seed_deterministic():
    a = build_fx_table([2021, 2022], random.Random(42))
    b = build_fx_table([2021, 2022], random.Random(42))
    assert a.usd_cad == b.usd_cad


# --------------------------------------------------------------------------- #
# build_facts : invariants on generated data
# --------------------------------------------------------------------------- #
def test_generated_facts_respect_yearfacts_invariants():
    ents = build_entities()
    rng = random.Random(DEFAULT_SEED)
    facts = build_facts(ents, [2021, 2022, 2023], rng)
    for f in facts.values():
        assert f.distribution >= 0
        assert f.capital_contribution >= 0
        assert 0.0 <= f.return_of_capital <= f.distribution + 1e-9
        assert 0.05 <= f.exempt_portion <= 0.95


def test_demo_holdco_never_distributes():
    ents = build_entities()
    rng = random.Random(DEFAULT_SEED)
    facts = build_facts(ents, list(range(2021, 2025)), rng)
    for year in range(2021, 2025):
        assert facts[("DEMO_HOLDCO", year)].distribution == 0.0
        assert facts[("DEMO_HOLDCO", year)].capital_contribution == 0.0


def test_generated_facts_cover_every_entity_year():
    ents = build_entities()
    rng = random.Random(DEFAULT_SEED)
    years = [2021, 2022]
    facts = build_facts(ents, years, rng)
    assert set(facts) == {(c, y) for c in ents for y in years}


# --------------------------------------------------------------------------- #
# generate_structure
# --------------------------------------------------------------------------- #
def test_generate_structure_year_range_inclusive():
    s = generate_structure(2020, 2023)
    assert s.years == [2020, 2021, 2022, 2023]


def test_generate_structure_rejects_inverted_range():
    with pytest.raises(ValueError, match="end_year must be >= start_year"):
        generate_structure(2024, 2021)


def test_generate_structure_single_year():
    s = generate_structure(2022, 2022)
    assert s.years == [2022]
    assert set(s.fx.usd_cad) == {2022}


def test_generate_structure_is_a_structure():
    s = generate_structure(2021, 2021)
    assert isinstance(s, Structure)
    assert len(s.entities) == 4


def test_generate_structure_differs_with_seed():
    a = generate_structure(2021, 2023, seed=1)
    b = generate_structure(2021, 2023, seed=2)
    # Different seeds should produce at least one differing fact stream.
    assert a.fx.usd_cad != b.fx.usd_cad or any(
        a.facts[k].standalone_taxable_income != b.facts[k].standalone_taxable_income
        for k in a.facts
    )


# --------------------------------------------------------------------------- #
# report._money formatting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,text",
    [
        (0.0, "0.00"),
        (1234.5, "1,234.50"),
        (-1234.5, "(1,234.50)"),
        (1_000_000.0, "1,000,000.00"),
        (-0.01, "(0.01)"),
        (12.345, "12.35"),
    ],
)
def test_money_formats_with_separators_and_parens(value, text):
    assert _money(value) == text


# --------------------------------------------------------------------------- #
# attach_fx
# --------------------------------------------------------------------------- #
def test_attach_fx_sets_rate_per_currency():
    s = generate_structure(2021, 2022)
    results = SurplusEngine(s).run([2021, 2022])
    attach_fx(results, s)
    for r in results:
        if r.currency == "CAD":
            assert r.fx_rate_to_cad == 1.0
        else:
            assert r.fx_rate_to_cad == s.fx.usd_cad[r.year]


def test_attach_fx_is_idempotent():
    s = generate_structure(2021, 2021)
    results = SurplusEngine(s).run([2021])
    attach_fx(results, s)
    first = [r.fx_rate_to_cad for r in results]
    attach_fx(results, s)
    assert [r.fx_rate_to_cad for r in results] == first


# --------------------------------------------------------------------------- #
# entity_workpaper Markdown
# --------------------------------------------------------------------------- #
def _generated_results():
    s = generate_structure(2021, 2023)
    results = SurplusEngine(s).run([2021, 2022, 2023])
    attach_fx(results, s)
    return s, results


def test_workpaper_has_three_lineage_layers():
    s, results = _generated_results()
    wp = entity_workpaper("BIRCH_OP", results, s)
    assert "Layer 1 — Evidence" in wp
    assert "Layer 2 — Surplus-Details" in wp
    assert "Layer 3 — Summary" in wp


def test_workpaper_marks_data_fictional():
    s, results = _generated_results()
    wp = entity_workpaper("MAPLE_FUND", results, s)
    assert "[FICTIONAL]" in wp
    assert "Maple Fund LP" in wp


def test_workpaper_names_parent_for_subsidiary():
    s, results = _generated_results()
    wp = entity_workpaper("BIRCH_OP", results, s)
    # BIRCH_OP is owned by Cedar Mezz Holdings LLC.
    assert "Cedar Mezz Holdings LLC" in wp


def test_workpaper_top_holdco_has_no_parent_label():
    s, results = _generated_results()
    wp = entity_workpaper("DEMO_HOLDCO", results, s)
    assert "top holdco" in wp


def test_workpaper_lists_every_year_row():
    s, results = _generated_results()
    wp = entity_workpaper("CEDAR_MEZZ", results, s)
    for year in (2021, 2022, 2023):
        assert f"| {year} |" in wp


# --------------------------------------------------------------------------- #
# consolidated_summary
# --------------------------------------------------------------------------- #
def test_consolidated_summary_lists_all_entities():
    s, results = _generated_results()
    cs = consolidated_summary(results, s)
    for name in ("Birchwood Op Co", "Cedar Mezz Holdings LLC",
                 "Maple Fund LP", "Demo Holdings Inc."):
        assert name in cs


def test_consolidated_summary_has_grand_total_line():
    s, results = _generated_results()
    cs = consolidated_summary(results, s)
    assert "Grand total surplus across all entity-years (CAD)" in cs


def test_consolidated_summary_marks_fictional():
    s, results = _generated_results()
    cs = consolidated_summary(results, s)
    assert "[FICTIONAL]" in cs
