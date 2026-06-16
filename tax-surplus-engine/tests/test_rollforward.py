"""Roll-forward continuity and end-to-end generator/CLI smoke tests."""

from __future__ import annotations

from surplus_engine.engine import SurplusEngine
from surplus_engine.generate import generate_structure
from surplus_engine.model import PoolBalances
from tests.conftest import make_facts


def test_closing_n_equals_opening_n_plus_1(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, income=1_000_000, exempt_portion=0.5,
                   capital_contribution=200_000),
        make_facts("SOLO", 2022, income=500_000, exempt_portion=0.5,
                   distribution=100_000),
        make_facts("SOLO", 2023, income=300_000, exempt_portion=1.0),
    ]
    struct = single_entity_factory(facts)
    eng = SurplusEngine(struct)
    out = {(r.entity, r.year): r for r in eng.run([2021, 2022, 2023])}

    for y in (2021, 2022):
        closing = out[("SOLO", y)].closing
        opening_next = out[("SOLO", y + 1)].opening
        assert closing.exempt_surplus == opening_next.exempt_surplus
        assert closing.taxable_surplus == opening_next.taxable_surplus
        assert closing.pre_acquisition_capital == opening_next.pre_acquisition_capital
        assert closing.acb == opening_next.acb


def test_rollforward_holds_across_full_generated_structure():
    struct = generate_structure(2021, 2024)
    eng = SurplusEngine(struct)
    results = eng.run([2021, 2022, 2023, 2024])
    by_entity = {}
    for r in results:
        by_entity.setdefault(r.entity, {})[r.year] = r
    for code, years in by_entity.items():
        ordered = sorted(years)
        for y in ordered[:-1]:
            c = years[y].closing
            o = years[y + 1].opening
            assert c.exempt_surplus == o.exempt_surplus, code
            assert c.taxable_surplus == o.taxable_surplus, code
            assert c.pre_acquisition_capital == o.pre_acquisition_capital, code
            assert c.acb == o.acb, code


def test_generator_is_deterministic():
    a = generate_structure(2021, 2024, seed=123)
    b = generate_structure(2021, 2024, seed=123)
    assert a.fx.usd_cad == b.fx.usd_cad
    for key in a.facts:
        fa, fb = a.facts[key], b.facts[key]
        assert fa.standalone_taxable_income == fb.standalone_taxable_income
        assert fa.distribution == fb.distribution
        assert fa.capital_contribution == fb.capital_contribution


def test_first_year_opening_is_zero():
    struct = generate_structure(2021, 2021)
    eng = SurplusEngine(struct)
    results = eng.run([2021])
    zero = PoolBalances()
    for r in results:
        assert r.opening.exempt_surplus == zero.exempt_surplus
        assert r.opening.taxable_surplus == zero.taxable_surplus
        assert r.opening.pre_acquisition_capital == zero.pre_acquisition_capital
        assert r.opening.acb == zero.acb


def test_cli_runs_and_writes_outputs(tmp_path):
    from surplus_engine.cli import main

    out_dir = tmp_path / "out"
    rc = main(["--start", "2021", "--end", "2023", "--out", str(out_dir), "--xlsx"])
    assert rc == 0
    # Four workpapers + consolidated summary + workbook.
    assert (out_dir / "consolidated_summary.md").exists()
    assert (out_dir / "workpaper_BIRCH_OP.md").exists()
    assert (out_dir / "surplus_model.xlsx").exists()
    summary_text = (out_dir / "consolidated_summary.md").read_text(encoding="utf-8")
    assert "Consolidated Surplus & ACB Summary" in summary_text
    assert "Birchwood Op Co" in summary_text


def test_cli_rejects_bad_year_range():
    from surplus_engine.cli import main

    assert main(["--start", "2024", "--end", "2021"]) == 2
