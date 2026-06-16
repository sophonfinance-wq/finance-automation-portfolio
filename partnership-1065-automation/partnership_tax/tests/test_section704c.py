"""Tests for the IRC §704(c) built-in-gain submodule (traditional method).

These exercise the §704(c) engine in isolation from the existing Form 1065
workpaper pipeline:

* built-in gain (BIG) = FMV − tax basis at formation,
* book and tax capital each summing to partnership equity,
* the traditional method curing the non-contributing partner first,
* a CEILING-RULE case where the non-contributor is capped at the actual tax item,
* the §704(c) layer decreasing monotonically and never flipping sign,
* on-sale catch-up of the remaining built-in gain to the contributing partner,
* the K-1 roll-forward identity on both book and tax bases,
* a tax-basis balance sheet that balances, and
* determinism.
"""

from __future__ import annotations

import pytest

from partnership_tax import section704c as s
from partnership_tax.money import to_cents


# ---------------------------------------------------------------------------
# Small builders so each behaviour can be asserted in isolation.
# ---------------------------------------------------------------------------
def _two_partner(
    fmv: float,
    tax_basis: float,
    book_life: int,
    tax_life: int,
    cash: float,
    n_years: int = 1,
    sale_year=None,
    sale_price: float = 0.0,
    atlas_bps: int = 5000,
) -> s.Partnership:
    """A 50/50 (default) partnership: ATLAS contributes a building, BEACON cash."""
    partners = {
        "ATLAS": s.Partner(code="ATLAS", name="Atlas Capital LLC", interest_bps=atlas_bps),
        "BEACON": s.Partner(
            code="BEACON", name="Beacon Equity LLC", interest_bps=10000 - atlas_bps
        ),
    }
    properties = {
        "BLDG": s.ContributedProperty(
            code="BLDG",
            name="Building",
            contributor="ATLAS",
            fmv_cents=to_cents(fmv),
            tax_basis_cents=to_cents(tax_basis),
            depreciable=True,
            book_life_years=book_life,
            tax_life_years=tax_life,
        ),
        "CASH": s.ContributedProperty(
            code="CASH",
            name="Cash",
            contributor="BEACON",
            fmv_cents=to_cents(cash),
            tax_basis_cents=to_cents(cash),
            depreciable=False,
        ),
    }
    years = list(range(1, n_years + 1))
    property_years = {}
    if sale_year is not None:
        property_years[("BLDG", sale_year)] = s.PropertyYear(
            property="BLDG", year=sale_year, sold=True, sale_price_cents=to_cents(sale_price)
        )
    return s.Partnership(
        code="TEST_LP",
        name="Test Partners LP",
        partners=partners,
        properties=properties,
        property_years=property_years,
        partnership_years={},
        years=years,
    )


def _bldg_year(results, prop_code, year):
    yr = next(y for y in results if y.year == year)
    return next(p for p in yr.properties if p.property == prop_code)


# ---------------------------------------------------------------------------
# Built-in gain at formation
# ---------------------------------------------------------------------------
def test_built_in_gain_is_fmv_minus_tax_basis():
    prop = s.ContributedProperty(
        code="BLDG", name="b", contributor="ATLAS",
        fmv_cents=to_cents(1_200_000), tax_basis_cents=to_cents(300_000),
        depreciable=True, book_life_years=6, tax_life_years=6,
    )
    assert prop.built_in_gain_cents == to_cents(900_000)


def test_built_in_loss_is_negative():
    prop = s.ContributedProperty(
        code="BLDG", name="b", contributor="ATLAS",
        fmv_cents=to_cents(400_000), tax_basis_cents=to_cents(700_000),
        depreciable=True, book_life_years=5, tax_life_years=5,
    )
    assert prop.built_in_gain_cents == to_cents(-300_000)


def test_cash_contribution_has_no_built_in_gain():
    cash = s.ContributedProperty(
        code="CASH", name="c", contributor="BEACON",
        fmv_cents=to_cents(500_000), tax_basis_cents=to_cents(500_000),
    )
    assert cash.built_in_gain_cents == 0
    assert cash.is_cash is True


def test_formation_book_credited_at_fmv_tax_at_basis():
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000)
    form = s.Section704cEngine(p).formation_capital()
    assert form["ATLAS"].book_cents == to_cents(1_200_000)   # FMV
    assert form["ATLAS"].tax_cents == to_cents(300_000)      # carryover basis
    assert form["BEACON"].book_cents == to_cents(1_200_000)
    assert form["BEACON"].tax_cents == to_cents(1_200_000)


def test_formation_disparity_equals_built_in_gain():
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000)
    form = s.Section704cEngine(p).formation_capital()
    atlas = form["ATLAS"]
    assert atlas.book_cents - atlas.tax_cents == to_cents(900_000)
    beacon = form["BEACON"]
    assert beacon.book_cents - beacon.tax_cents == 0


# ---------------------------------------------------------------------------
# Book & tax capital each sum to partnership equity
# ---------------------------------------------------------------------------
def test_book_and_tax_capital_each_sum_to_partnership_equity():
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000)
    form = s.Section704cEngine(p).formation_capital()
    assert sum(a.book_cents for a in form.values()) == to_cents(2_400_000)
    assert sum(a.tax_cents for a in form.values()) == to_cents(1_500_000)


def test_partner_interests_must_sum_to_100pct():
    with pytest.raises(ValueError):
        s.Partnership(
            code="X", name="X",
            partners={
                "A": s.Partner(code="A", name="A", interest_bps=6000),
                "B": s.Partner(code="B", name="B", interest_bps=5000),  # 110%
            },
            properties={},
            property_years={},
            partnership_years={},
            years=[1],
        )


# ---------------------------------------------------------------------------
# Traditional method: non-contributor cured first; book by %
# ---------------------------------------------------------------------------
def test_book_depreciation_allocated_by_interest_pct():
    p = _two_partner(1_200_000, 600_000, 6, 6, 1_200_000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.book_depreciation == to_cents(200_000)
    assert pr.book_dep_alloc["ATLAS"] == to_cents(100_000)
    assert pr.book_dep_alloc["BEACON"] == to_cents(100_000)


def test_tax_depreciation_goes_to_noncontributor_first():
    # Tax basis 600k / 6 -> 100k tax dep; non-contributor book share 100k.
    p = _two_partner(1_200_000, 600_000, 6, 6, 1_200_000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.tax_depreciation == to_cents(100_000)
    assert pr.tax_dep_alloc["BEACON"] == to_cents(100_000)   # non-contributor first
    assert pr.tax_dep_alloc["ATLAS"] == 0
    assert pr.ceiling_binding is False


def test_contributor_gets_excess_tax_depreciation():
    # Tax basis 900k / 6 -> 150k tax dep; Beacon gets its 100k, Atlas the 50k excess.
    p = _two_partner(1_200_000, 900_000, 6, 6, 1_200_000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.tax_depreciation == to_cents(150_000)
    assert pr.tax_dep_alloc["BEACON"] == to_cents(100_000)
    assert pr.tax_dep_alloc["ATLAS"] == to_cents(50_000)
    assert pr.ceiling_binding is False


def test_layer_curing_matches_book_minus_tax_difference():
    p = _two_partner(1_200_000, 600_000, 6, 6, 1_200_000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.layer_open == to_cents(600_000)        # BIG = 1.2M - 0.6M
    assert pr.layer_cured == to_cents(100_000)       # book(200k) - tax(100k)
    assert pr.layer_close == to_cents(500_000)


# ---------------------------------------------------------------------------
# Ceiling rule
# ---------------------------------------------------------------------------
def test_ceiling_rule_caps_noncontributor_and_flags():
    # Canonical case: book dep 200k (Beacon share 100k) but only 50k tax dep.
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.book_dep_alloc["BEACON"] == to_cents(100_000)
    assert pr.tax_depreciation == to_cents(50_000)
    assert pr.ceiling_binding is True
    assert pr.tax_dep_alloc["BEACON"] == to_cents(50_000)    # capped at actual
    assert pr.tax_dep_alloc["ATLAS"] == 0                    # contributor gets none
    assert pr.ceiling_shortfall == to_cents(50_000)


def test_ceiling_shortfall_is_book_share_minus_available_tax():
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.ceiling_shortfall == pr.book_dep_alloc["BEACON"] - pr.tax_depreciation


def test_ceiling_rule_total_tax_alloc_respects_actual():
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000)
    res = s.Section704cEngine(p).run()
    for yr in res:
        for pr in yr.properties:
            assert sum(pr.tax_dep_alloc.values()) <= pr.tax_depreciation


def test_no_ceiling_when_tax_dep_covers_book_share():
    p = _two_partner(1_000_000, 1_000_000, 5, 5, 1_000_000, n_years=5)
    res = s.Section704cEngine(p).run()
    for yr in res:
        pr = next(x for x in yr.properties if x.property == "BLDG")
        assert pr.ceiling_binding is False
        assert pr.ceiling_shortfall == 0


# ---------------------------------------------------------------------------
# On sale: remaining built-in gain taxed to the contributor
# ---------------------------------------------------------------------------
def test_immediate_sale_taxes_full_big_to_contributor():
    # Sell in year 1 at FMV before any depreciation: entire 600k BIG to Atlas.
    p = _two_partner(1_200_000, 600_000, 6, 6, 1_200_000, n_years=1, sale_year=1, sale_price=1_200_000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.sold is True
    assert pr.book_gain == 0
    assert pr.tax_gain == to_cents(600_000)
    assert pr.tax_gain_alloc["ATLAS"] == to_cents(600_000)
    assert pr.tax_gain_alloc["BEACON"] == 0


def test_sale_after_partial_cure_taxes_remaining_layer():
    # Ceiling case, depreciate 5 yrs then sell in yr 6; remaining 150k layer to Atlas.
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000, n_years=6, sale_year=6, sale_price=700_000)
    res = s.Section704cEngine(p).run()
    sale = _bldg_year(res, "BLDG", 6)
    assert sale.layer_open == to_cents(150_000)
    assert sale.layer_close == 0
    assert sale.tax_gain == to_cents(650_000)
    # Atlas: 150k layer + 50% of residual 500k = 400k; Beacon 250k.
    assert sale.tax_gain_alloc["ATLAS"] == to_cents(400_000)
    assert sale.tax_gain_alloc["BEACON"] == to_cents(250_000)


def test_layer_fully_cleared_on_sale():
    p = _two_partner(1_200_000, 300_000, 6, 6, 1_200_000, n_years=6, sale_year=6, sale_price=700_000)
    res = s.Section704cEngine(p).run()
    assert _bldg_year(res, "BLDG", 6).layer_close == 0


# ---------------------------------------------------------------------------
# Layer monotonicity, roll-forward identity, balance sheet, determinism
# ---------------------------------------------------------------------------
def test_704c_layer_decreases_and_never_negative():
    p = s.generate_partnership()
    res = s.Section704cEngine(p).run()
    prev = None
    for yr in res:
        for pr in yr.properties:
            if pr.property != "HARBOR_BLDG":
                continue
            assert pr.layer_close >= 0                 # BIG never crosses zero
            assert pr.layer_close <= pr.layer_open     # decreases toward zero
            if prev is not None:
                assert pr.layer_open == prev
            prev = pr.layer_close


def test_k1_book_rollforward_identity():
    p = s.generate_partnership()
    eng = s.Section704cEngine(p)
    formation = eng.formation_capital()
    results = eng.run()
    for code in ("ATLAS", "BEACON"):
        prev = formation[code].book_cents
        for yr in results:
            pr = next(x for x in yr.partners if x.partner == code)
            assert pr.book_open == prev
            assert pr.book_close == (
                pr.book_open + pr.contribution_book + pr.income_book - pr.distribution
            )
            prev = pr.book_close


def test_k1_tax_rollforward_identity():
    p = s.generate_partnership()
    eng = s.Section704cEngine(p)
    formation = eng.formation_capital()
    results = eng.run()
    for code in ("ATLAS", "BEACON"):
        prev = formation[code].tax_cents
        for yr in results:
            pr = next(x for x in yr.partners if x.partner == code)
            assert pr.tax_open == prev
            assert pr.tax_close == (
                pr.tax_open + pr.contribution_tax + pr.income_tax - pr.distribution
            )
            prev = pr.tax_close


def test_tax_basis_balance_sheet_balances():
    summary = s.build_reports(s.generate_partnership())["section704c_summary.md"]
    assert "balances" in summary
    assert "OUT OF BALANCE" not in summary


def test_final_total_tax_capital_matches_independent_recompute():
    p = s.generate_partnership()
    results = s.Section704cEngine(p).run()
    total_tax_capital = sum(pr.tax_close for pr in results[-1].partners)
    expected = (
        to_cents(1_500_000)        # formation tax capital
        + to_cents(180_000) * 6    # ordinary income
        - to_cents(120_000) * 6    # distributions
        - to_cents(50_000) * 5     # tax depreciation deductions
        + to_cents(650_000)        # tax gain on sale
    )
    assert total_tax_capital == expected


def test_determinism_same_seed_same_output():
    a = s.build_reports(s.generate_partnership(seed=42))
    b = s.build_reports(s.generate_partnership(seed=42))
    assert a == b


def test_build_reports_emits_summary_and_a_k1_per_partner():
    artifacts = s.build_reports(s.generate_partnership())
    assert "section704c_summary.md" in artifacts
    assert "section704c_k1_ATLAS.md" in artifacts
    assert "section704c_k1_BEACON.md" in artifacts
    # Ceiling rule is surfaced (flagged), not hidden.
    assert "BINDING" in artifacts["section704c_summary.md"]
    # K-1 carries the built-in gain at formation for the contributor.
    assert "900,000.00" in artifacts["section704c_k1_ATLAS.md"]


def test_ownership_pct_allocation_of_book_items_70_30():
    p = _two_partner(1_000_000, 1_000_000, 10, 10, 1_000_000, atlas_bps=7000)
    res = s.Section704cEngine(p).run()
    pr = _bldg_year(res, "BLDG", 1)
    assert pr.book_depreciation == to_cents(100_000)
    assert pr.book_dep_alloc["ATLAS"] == to_cents(70_000)
    assert pr.book_dep_alloc["BEACON"] == to_cents(30_000)


def test_run_demo_writes_files(tmp_path):
    partnership, written = s.run_demo(tmp_path)
    names = {p.name for p in written}
    assert "section704c_summary.md" in names
    assert "section704c_k1_ATLAS.md" in names
    assert "section704c_k1_BEACON.md" in names
    assert (tmp_path / "section704c_summary.md").exists()
