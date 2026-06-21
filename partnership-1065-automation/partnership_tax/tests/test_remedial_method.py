"""Tests for the §704(c) REMEDIAL method (Reg. §1.704-3(d)).

The remedial method cures the ceiling-rule distortion that the traditional
method only surfaces, by creating equal and offsetting notional items: a
remedial deduction to the short-changed non-contributor and an equal remedial
income item to the contributor.

The numeric oracles below are the canonical Reg. §1.704-3 published example
(property FMV 10,000 / tax basis 4,000 / 10-yr straight-line; the other partner
contributes 10,000 cash; book items shared 50/50), independently reproduced and
reconciled to consensus against the regulation. The traditional-method oracle is
included to prove the remedial path is purely additive — the traditional numbers
are unchanged.
"""

from __future__ import annotations

import pytest

from partnership_tax import section704c as s
from partnership_tax.money import to_cents


# ---------------------------------------------------------------------------
# Builders (ATLAS = contributor "A"; BEACON = non-contributor cash "B")
# ---------------------------------------------------------------------------
def _canonical(method: str = "traditional", n_years: int = 2) -> s.Partnership:
    """Reg. §1.704-3 published example: A contributes property FMV 10,000 /
    basis 4,000 (BIG 6,000), 10-yr book & tax life; B contributes 10,000 cash."""
    partners = {
        "ATLAS": s.Partner(code="ATLAS", name="Atlas (contributor)", interest_bps=5000),
        "BEACON": s.Partner(code="BEACON", name="Beacon (cash)", interest_bps=5000),
    }
    properties = {
        "BLDG": s.ContributedProperty(
            code="BLDG", name="Contributed building", contributor="ATLAS",
            fmv_cents=to_cents(10_000), tax_basis_cents=to_cents(4_000),
            depreciable=True, book_life_years=10, tax_life_years=10,
        ),
        "CASH": s.ContributedProperty(
            code="CASH", name="Beacon cash", contributor="BEACON",
            fmv_cents=to_cents(10_000), tax_basis_cents=to_cents(10_000),
            depreciable=False,
        ),
    }
    return s.Partnership(
        code="CANON_LP", name="Canonical 704(c) Example LP",
        partners=partners, properties=properties,
        property_years={}, partnership_years={},
        years=list(range(1, n_years + 1)), method=method,
    )


def _run(p: s.Partnership):
    eng = s.Section704cEngine(p)
    formation = eng.formation_capital()
    results = eng.run()
    return eng, formation, results


def _bldg(results, year):
    yr = next(y for y in results if y.year == year)
    return next(pr for pr in yr.properties if pr.property == "BLDG")


def _prop(results, year, code):
    yr = next(y for y in results if y.year == year)
    return next(pr for pr in yr.properties if pr.property == code)


def _partner(results, year, code):
    yr = next(y for y in results if y.year == year)
    return next(pr for pr in yr.partners if pr.partner == code)


# ---------------------------------------------------------------------------
# Method selector / validation
# ---------------------------------------------------------------------------
def test_method_defaults_to_traditional():
    assert _canonical().method == "traditional"


def test_invalid_method_raises():
    with pytest.raises(ValueError, match="method"):
        _canonical(method="curative")  # not implemented (documented non-goal)


def test_generate_partnership_threads_method():
    assert s.generate_partnership(method="remedial").method == "remedial"


# ---------------------------------------------------------------------------
# TRADITIONAL oracle on the canonical example (proves additivity: unchanged)
# ---------------------------------------------------------------------------
def test_traditional_canonical_oracle():
    _, formation, results = _run(_canonical("traditional"))

    assert formation["ATLAS"].book_cents == to_cents(10_000)
    assert formation["ATLAS"].tax_cents == to_cents(4_000)
    assert formation["BEACON"].tax_cents == to_cents(10_000)

    for year in (1, 2):
        b = _bldg(results, year)
        assert b.book_depreciation == to_cents(1_000)
        assert b.tax_depreciation == to_cents(400)
        assert b.book_dep_alloc["ATLAS"] == to_cents(500)
        assert b.book_dep_alloc["BEACON"] == to_cents(500)
        assert b.tax_dep_alloc["BEACON"] == to_cents(400)
        assert b.tax_dep_alloc["ATLAS"] == 0
        assert b.ceiling_binding is True
        assert b.ceiling_shortfall == to_cents(100)

    assert _partner(results, 1, "ATLAS").tax_close == to_cents(4_000)
    assert _partner(results, 1, "BEACON").tax_close == to_cents(9_600)
    assert _partner(results, 2, "ATLAS").tax_close == to_cents(4_000)
    assert _partner(results, 2, "BEACON").tax_close == to_cents(9_200)
    # A's residual book/tax disparity declines 500/yr under the ceiling.
    a1 = _partner(results, 1, "ATLAS")
    a2 = _partner(results, 2, "ATLAS")
    assert a1.book_close - a1.tax_close == to_cents(5_500)
    assert a2.book_close - a2.tax_close == to_cents(5_000)


# ---------------------------------------------------------------------------
# REMEDIAL oracle on the canonical example (the new core)
# ---------------------------------------------------------------------------
def test_remedial_canonical_oracle():
    _, _, results = _run(_canonical("remedial"))

    for year in (1, 2):
        b = _bldg(results, year)
        assert b.method_used == "remedial"
        assert b.book_depreciation == to_cents(1_000)
        assert b.tax_depreciation == to_cents(400)
        # Actual tax depreciation allocated exactly as under traditional.
        assert b.tax_dep_alloc["BEACON"] == to_cents(400)
        assert b.tax_dep_alloc["ATLAS"] == 0
        # Remedial items cure the 100 ceiling shortfall, net to zero.
        assert b.remedial_deduction_alloc["BEACON"] == to_cents(100)
        assert b.remedial_income_alloc["ATLAS"] == to_cents(100)
        assert b.remedial_net == 0
        # Ceiling is reported cured under the remedial method.
        assert b.ceiling_binding is False
        assert b.ceiling_shortfall == 0

    assert _partner(results, 1, "ATLAS").tax_close == to_cents(4_100)
    assert _partner(results, 1, "BEACON").tax_close == to_cents(9_500)
    assert _partner(results, 2, "ATLAS").tax_close == to_cents(4_200)
    assert _partner(results, 2, "BEACON").tax_close == to_cents(9_000)
    # Book capital unaffected by the remedial (tax-only) items.
    for year in (1, 2):
        assert _partner(results, year, "ATLAS").book_close == _partner(
            results, year, "BEACON"
        ).book_close


def test_remedial_cures_noncontributor_disparity():
    _, _, results = _run(_canonical("remedial"))
    for year in (1, 2):
        beacon = _partner(results, year, "BEACON")
        assert beacon.book_close == beacon.tax_close  # disparity fully cured


def test_remedial_contributor_tax_capital_increases():
    _, _, results = _run(_canonical("remedial"))
    closes = [_partner(results, y, "ATLAS").tax_close for y in (1, 2)]
    assert closes == [to_cents(4_100), to_cents(4_200)]
    assert closes[1] > closes[0] > to_cents(4_000)  # rises, never falls


def test_remedial_contributor_residual_disparity():
    # A's book-minus-tax disparity equals the remaining built-in gain.
    _, _, results = _run(_canonical("remedial"))
    a1 = _partner(results, 1, "ATLAS")
    a2 = _partner(results, 2, "ATLAS")
    assert a1.book_close - a1.tax_close == to_cents(5_400)
    assert a2.book_close - a2.tax_close == to_cents(4_800)


def test_remedial_pair_nets_to_zero_every_year():
    _, _, results = _run(_canonical("remedial"))
    for year in (1, 2):
        b = _bldg(results, year)
        assert sum(b.remedial_income_alloc.values()) == sum(
            b.remedial_deduction_alloc.values()
        )
        assert b.remedial_net == 0


def test_remedial_total_tax_capital_declines_only_by_actual_dep():
    # Remedial items net to zero across partners, so total tax capital can fall
    # only by the actual tax depreciation (400/yr): 20,000 -> 13,600 -> 13,200.
    _, _, results = _run(_canonical("remedial"))
    for year, expected in ((1, 14_000 - 400), (2, 14_000 - 800)):
        total = sum(p.tax_close for p in next(y for y in results if y.year == year).partners)
        assert total == to_cents(expected)


def test_remedial_layer_matches_contributor_disparity():
    # With the non-contributor cured to zero, the property's §704(c) layer equals
    # the contributor's residual built-in gain each year.
    _, _, results = _run(_canonical("remedial"))
    assert _bldg(results, 1).layer_close == to_cents(5_400)
    assert _bldg(results, 2).layer_close == to_cents(4_800)


# ---------------------------------------------------------------------------
# Harborview seed: remedial offset is $50k; traditional figures unchanged
# ---------------------------------------------------------------------------
def test_harborview_remedial_offset_is_50k():
    _, _, results = _run(s.generate_partnership(method="remedial"))
    b = _prop(results, 1, "HARBOR_BLDG")
    assert b.remedial_deduction_alloc["BEACON"] == to_cents(50_000)
    assert b.remedial_income_alloc["ATLAS"] == to_cents(50_000)
    assert b.remedial_net == 0
    assert b.ceiling_binding is False
    assert b.ceiling_shortfall == 0


def test_harborview_traditional_unchanged():
    _, _, results = _run(s.generate_partnership())  # default traditional
    b = _prop(results, 1, "HARBOR_BLDG")
    assert b.tax_depreciation == to_cents(50_000)
    assert b.book_dep_alloc["BEACON"] == to_cents(100_000)
    assert b.ceiling_binding is True
    assert b.ceiling_shortfall == to_cents(50_000)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_remedial_is_deterministic():
    closes = []
    for _ in range(2):
        _, _, results = _run(_canonical("remedial"))
        closes.append(
            [(_partner(results, y, c).tax_close) for y in (1, 2) for c in ("ATLAS", "BEACON")]
        )
    assert closes[0] == closes[1]
