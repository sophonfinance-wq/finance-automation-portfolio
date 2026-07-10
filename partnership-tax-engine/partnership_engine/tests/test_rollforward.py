"""Capital roll-forward identity, layer monotonicity, balance sheet, determinism."""

from __future__ import annotations

from partnership_engine.engine import PartnershipEngine
from partnership_engine.generate import generate_partnership
from partnership_engine.report import build_reports
from partnership_engine.money import to_cents


def _run_default():
    p = generate_partnership()
    eng = PartnershipEngine(p)
    formation = eng.formation_capital()
    return p, formation, eng.run()


def test_k1_book_rollforward_identity():
    # begin + contributions + income - distributions == ending, on book basis.
    _, formation, results = _run_default()
    for code in ("ATLAS", "BEACON"):
        prev = formation[code].book_cents
        for yr in results:
            pr = next(p for p in yr.partners if p.partner == code)
            assert pr.book_open == prev
            expected = pr.book_open + pr.contribution_book + pr.income_book - pr.distribution
            assert pr.book_close == expected
            prev = pr.book_close


def test_k1_tax_rollforward_identity():
    # Same identity on the tax basis.
    _, formation, results = _run_default()
    for code in ("ATLAS", "BEACON"):
        prev = formation[code].tax_cents
        for yr in results:
            pr = next(p for p in yr.partners if p.partner == code)
            assert pr.tax_open == prev
            expected = pr.tax_open + pr.contribution_tax + pr.income_tax - pr.distribution
            assert pr.tax_close == expected
            prev = pr.tax_close


def test_704c_layer_decreases_and_never_negative():
    _, _, results = _run_default()
    prev = None
    for yr in results:
        for pr in yr.properties:
            if pr.property != "HARBOR_BLDG":
                continue
            # BIG case: layer starts positive and never crosses zero.
            assert pr.layer_close >= 0
            assert pr.layer_close <= pr.layer_open
            if prev is not None:
                assert pr.layer_open == prev
            prev = pr.layer_close


def test_tax_basis_balance_sheet_balances():
    # Assets (cash + adjusted tax basis of property) == total tax capital.
    p = generate_partnership()
    summary = build_reports(p)["partnership_1065_summary.md"]
    assert "balances ✓" in summary
    assert "OUT OF BALANCE" not in summary


def test_final_total_tax_capital_matches_assets():
    # Recompute independently: after the sale the building basis is 0, so total
    # assets == contributed cash + initial tax basis + cumulative tax income.
    p, formation, results = _run_default()
    final = results[-1]
    total_tax_capital = sum(pr.tax_close for pr in final.partners)
    # Cash (1.2M) + building tax basis fully realised through depreciation/sale,
    # plus retained operating income net of distributions.
    # Operating income 180k/yr * 6 = 1.08M; distributions 120k/yr * 6 = 720k.
    # Tax depreciation 50k/yr * 5 = 250k (deductions); sale tax gain 650k.
    # Starting tax capital 1.5M.
    expected = (
        to_cents(1_500_000)            # formation tax capital
        + to_cents(180_000) * 6        # ordinary income (book == tax)
        - to_cents(120_000) * 6        # distributions
        - to_cents(50_000) * 5         # tax depreciation deductions
        + to_cents(650_000)            # tax gain on sale
    )
    assert total_tax_capital == expected
    assert formation["ATLAS"].tax_cents + formation["BEACON"].tax_cents == to_cents(1_500_000)


def test_determinism_same_seed_same_output():
    a = build_reports(generate_partnership(seed=42))
    b = build_reports(generate_partnership(seed=42))
    assert a == b


def test_ownership_pct_allocation_of_book_items():
    # 70/30 split: book depreciation follows the agreed interest exactly.
    from partnership_engine.tests.conftest import (
        make_partner,
        make_property,
        make_partnership,
    )

    partners = [make_partner("ATLAS", 7000), make_partner("BEACON", 3000)]
    properties = [
        make_property("BLDG", "ATLAS", 1_000_000, 1_000_000,
                      depreciable=True, book_life=10, tax_life=10),
        make_property("CASH", "BEACON", 1_000_000, 1_000_000),
    ]
    p = make_partnership(partners, properties, n_years=1)
    res = PartnershipEngine(p).run()
    pr = next(x for x in res[0].properties if x.property == "BLDG")
    assert pr.book_depreciation == to_cents(100_000)
    assert pr.book_dep_alloc["ATLAS"] == to_cents(70_000)
    assert pr.book_dep_alloc["BEACON"] == to_cents(30_000)
