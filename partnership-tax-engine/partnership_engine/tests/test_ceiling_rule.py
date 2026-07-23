"""The ceiling rule: non-contributor capped at the actual tax item available."""

from __future__ import annotations

from partnership_engine.engine import PartnershipEngine
from partnership_engine.money import to_cents


def _bldg_year(results, year):
    yr = next(y for y in results if y.year == year)
    return next(p for p in yr.properties if p.property == "BLDG")


def test_ceiling_rule_caps_noncontributor_and_flags(two_partner_factory):
    # The canonical case: book dep 200k/yr (non-contributor share 100k) but only
    # 50k of tax dep available -> Beacon is capped at 50k, Atlas gets 0, and the
    # ceiling rule is flagged with a 50k shortfall.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert pr.book_dep_alloc["BEACON"] == to_cents(100_000)   # book share
    assert pr.tax_depreciation == to_cents(50_000)            # actual tax item
    assert pr.ceiling_binding is True
    assert pr.tax_dep_alloc["BEACON"] == to_cents(50_000)     # capped at actual
    assert pr.tax_dep_alloc["ATLAS"] == 0                     # contributor gets none
    assert pr.ceiling_shortfall == to_cents(50_000)           # uncured this year


def test_ceiling_shortfall_is_book_share_minus_available_tax(two_partner_factory):
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    noncontrib_book = pr.book_dep_alloc["BEACON"]
    assert pr.ceiling_shortfall == noncontrib_book - pr.tax_depreciation


def test_no_ceiling_when_tax_dep_covers_book_share(two_partner_factory):
    # Equal book and tax lives on the same basis -> tax dep covers the book share.
    p = two_partner_factory(
        fmv=1_000_000, tax_basis=1_000_000, book_life=5, tax_life=5, cash=1_000_000
    )
    res = PartnershipEngine(p).run()
    for yr in res:
        pr = next(p for p in yr.properties if p.property == "BLDG")
        assert pr.ceiling_binding is False
        assert pr.ceiling_shortfall == 0


def test_ceiling_rule_total_tax_alloc_respects_actual(two_partner_factory):
    # Even when the ceiling binds, allocated tax depreciation == actual tax item.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert sum(pr.tax_dep_alloc.values()) == pr.tax_depreciation
