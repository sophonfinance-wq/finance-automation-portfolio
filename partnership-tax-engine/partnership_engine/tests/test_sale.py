"""On sale: remaining §704(c) built-in gain taxed to the contributing partner."""

from __future__ import annotations

from partnership_engine.engine import PartnershipEngine
from partnership_engine.money import to_cents


def _bldg_year(results, year):
    yr = next(y for y in results if y.year == year)
    return next(p for p in yr.properties if p.property == "BLDG")


def test_immediate_sale_taxes_full_big_to_contributor(two_partner_factory):
    # Sell in year 1 before any depreciation: the entire 600k BIG goes to Atlas
    # for tax; book gain splits 50/50.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=600_000, book_life=6, tax_life=6, cash=1_200_000,
        n_years=1, sale_year=1, sale_price=1_200_000,
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert pr.sold is True
    # Book gain = price - book basis (FMV) = 0; tax gain = price - tax basis 600k.
    assert pr.book_gain == 0
    assert pr.tax_gain == to_cents(600_000)
    # Entire built-in gain to the contributing partner.
    assert pr.tax_gain_alloc["ATLAS"] == to_cents(600_000)
    assert pr.tax_gain_alloc["BEACON"] == 0


def test_sale_residual_gain_split_by_interest(two_partner_factory):
    # Sell above FMV in year 1: 600k BIG to Atlas, the extra gain shared 50/50.
    # price 1.4M; tax basis 600k -> tax gain 800k; BIG 600k to Atlas, residual
    # 200k split 100k/100k -> Atlas 700k, Beacon 100k.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=600_000, book_life=6, tax_life=6, cash=1_200_000,
        n_years=1, sale_year=1, sale_price=1_400_000,
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert pr.tax_gain == to_cents(800_000)
    assert pr.book_gain == to_cents(200_000)
    assert pr.book_gain_alloc["ATLAS"] == to_cents(100_000)
    assert pr.book_gain_alloc["BEACON"] == to_cents(100_000)
    assert pr.tax_gain_alloc["ATLAS"] == to_cents(700_000)
    assert pr.tax_gain_alloc["BEACON"] == to_cents(100_000)


def test_sale_after_partial_cure_taxes_remaining_layer(two_partner_factory):
    # Depreciate for 5 years under the ceiling case, then sell in year 6. The
    # remaining 150k layer must be taxed to Atlas on sale.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000,
        n_years=6, sale_year=6, sale_price=700_000,
    )
    res = PartnershipEngine(p).run()
    sale = _bldg_year(res, 6)
    assert sale.layer_open == to_cents(150_000)        # remaining after 5 yrs cure
    assert sale.layer_close == 0
    # tax gain = 700k - 50k remaining tax basis = 650k. Atlas: 150k layer + 50%
    # of residual 500k = 400k; Beacon 250k.
    assert sale.tax_gain == to_cents(650_000)
    assert sale.tax_gain_alloc["ATLAS"] == to_cents(400_000)
    assert sale.tax_gain_alloc["BEACON"] == to_cents(250_000)


def test_layer_fully_cleared_on_sale(two_partner_factory):
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000,
        n_years=6, sale_year=6, sale_price=700_000,
    )
    res = PartnershipEngine(p).run()
    sale = _bldg_year(res, 6)
    assert sale.layer_close == 0
