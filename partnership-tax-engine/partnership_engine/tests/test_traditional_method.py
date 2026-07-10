"""§704(c) traditional method: non-contributing partner cured first; book by %."""

from __future__ import annotations

from partnership_engine.engine import PartnershipEngine
from partnership_engine.money import to_cents


def _bldg_year(results, year):
    yr = next(y for y in results if y.year == year)
    return next(p for p in yr.properties if p.property == "BLDG")


def test_book_depreciation_allocated_by_interest_pct(two_partner_factory):
    # FMV 1.2M over 6 yrs -> 200k book dep; 50/50 -> 100k each.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=600_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert pr.book_depreciation == to_cents(200_000)
    assert pr.book_dep_alloc["ATLAS"] == to_cents(100_000)
    assert pr.book_dep_alloc["BEACON"] == to_cents(100_000)


def test_tax_depreciation_goes_to_noncontributor_first(two_partner_factory):
    # Tax basis 600k over 6 yrs -> 100k tax dep. Non-contributor (Beacon) book
    # share is 100k; tax dep exactly covers it, so Beacon gets the full 100k and
    # the contributor (Atlas) gets the remainder (0 here).
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=600_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert pr.tax_depreciation == to_cents(100_000)
    assert pr.tax_dep_alloc["BEACON"] == to_cents(100_000)
    assert pr.tax_dep_alloc["ATLAS"] == 0
    assert pr.ceiling_binding is False


def test_contributor_gets_excess_tax_depreciation(two_partner_factory):
    # Tax basis 900k over 6 yrs -> 150k tax dep. Non-contributor book share 100k.
    # Beacon gets 100k (its book share); Atlas (contributor) gets the excess 50k.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=900_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert pr.tax_depreciation == to_cents(150_000)
    assert pr.tax_dep_alloc["BEACON"] == to_cents(100_000)
    assert pr.tax_dep_alloc["ATLAS"] == to_cents(50_000)
    assert pr.ceiling_binding is False


def test_total_tax_dep_alloc_never_exceeds_actual_tax_dep(two_partner_factory):
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=900_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    for yr in res:
        for pr in yr.properties:
            assert sum(pr.tax_dep_alloc.values()) <= pr.tax_depreciation


def test_layer_curing_matches_book_minus_tax_difference(two_partner_factory):
    # Book dep 200k, tax dep 100k -> the 100k difference cures the BIG each year.
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=600_000, book_life=6, tax_life=6, cash=1_200_000
    )
    res = PartnershipEngine(p).run()
    pr = _bldg_year(res, 1)
    assert pr.layer_open == to_cents(600_000)        # BIG = 1.2M - 0.6M
    assert pr.layer_cured == to_cents(100_000)       # book(200k) - tax(100k)
    assert pr.layer_close == to_cents(500_000)
