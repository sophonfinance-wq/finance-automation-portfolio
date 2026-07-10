"""Formation: built-in gain, and book/tax capital seeding from contributions."""

from __future__ import annotations

from partnership_engine.engine import PartnershipEngine
from partnership_engine.money import to_cents
from partnership_engine.tests.conftest import (
    make_partner,
    make_property,
    make_partnership,
)


def test_built_in_gain_is_fmv_minus_tax_basis():
    prop = make_property(
        "BLDG", "ATLAS", fmv=1_200_000, tax_basis=300_000,
        depreciable=True, book_life=6, tax_life=6,
    )
    assert prop.built_in_gain_cents == to_cents(900_000)


def test_built_in_loss_is_negative():
    prop = make_property(
        "BLDG", "ATLAS", fmv=400_000, tax_basis=700_000,
        depreciable=True, book_life=5, tax_life=5,
    )
    assert prop.built_in_gain_cents == to_cents(-300_000)


def test_cash_contribution_has_no_built_in_gain():
    cash = make_property("CASH", "BEACON", fmv=500_000, tax_basis=500_000)
    assert cash.built_in_gain_cents == 0
    assert cash.is_cash is True


def test_formation_book_capital_credited_at_fmv(two_partner_factory):
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000
    )
    form = PartnershipEngine(p).formation_capital()
    # Atlas book capital == FMV of the building; Beacon book == cash.
    assert form["ATLAS"].book_cents == to_cents(1_200_000)
    assert form["BEACON"].book_cents == to_cents(1_200_000)


def test_formation_tax_capital_credited_at_basis(two_partner_factory):
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000
    )
    form = PartnershipEngine(p).formation_capital()
    # Atlas tax capital == carryover tax basis; Beacon tax == cash.
    assert form["ATLAS"].tax_cents == to_cents(300_000)
    assert form["BEACON"].tax_cents == to_cents(1_200_000)


def test_formation_disparity_equals_built_in_gain(two_partner_factory):
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000
    )
    form = PartnershipEngine(p).formation_capital()
    atlas = form["ATLAS"]
    # Book-minus-tax disparity == the BIG on the contributed building.
    assert atlas.book_cents - atlas.tax_cents == to_cents(900_000)
    # The cash partner carries no disparity.
    beacon = form["BEACON"]
    assert beacon.book_cents - beacon.tax_cents == 0


def test_book_and_tax_capital_each_sum_to_partnership_equity(two_partner_factory):
    p = two_partner_factory(
        fmv=1_200_000, tax_basis=300_000, book_life=6, tax_life=6, cash=1_200_000
    )
    form = PartnershipEngine(p).formation_capital()
    total_book = sum(a.book_cents for a in form.values())
    total_tax = sum(a.tax_cents for a in form.values())
    # Book equity = total FMV contributed; tax equity = total tax basis.
    assert total_book == to_cents(2_400_000)
    assert total_tax == to_cents(1_500_000)


def test_partner_interests_must_sum_to_100pct():
    import pytest

    with pytest.raises(ValueError):
        make_partnership(
            [make_partner("A", 6000), make_partner("B", 5000)],  # 110%
            [make_property("CASH", "A", 100, 100)],
        )
