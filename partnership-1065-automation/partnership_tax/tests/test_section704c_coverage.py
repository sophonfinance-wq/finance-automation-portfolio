"""Coverage tests for the IRC §704(c) submodule's helpers and edge paths.

The existing §704(c) suites cover the canonical oracles. This file pins down the
surrounding machinery: ``split_evenly`` / ``_allocate`` invariants, dataclass
validation (``__post_init__`` guards), the Partnership accessor helpers and their
defaults, capital-account copy semantics, formation idempotency, the
non-contributor weight renormalisation, the built-in-LOSS sale path, the
``_cure_layer`` clamp, and the rendered Markdown content.
"""

from __future__ import annotations

import pytest

from partnership_tax import section704c as s
from partnership_tax.money import to_cents


# ---------------------------------------------------------------------------
# split_evenly
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "total,periods,expected",
    [
        (100, 1, [100]),
        (100, 2, [50, 50]),
        (100, 3, [33, 33, 34]),
        (10, 1, [10]),
        (7, 7, [1, 1, 1, 1, 1, 1, 1]),
        (0, 5, [0, 0, 0, 0, 0]),
        (-100, 3, [-34, -34, -32]),
        (1, 3, [0, 0, 1]),
    ],
)
def test_split_evenly_known_pairs(total, periods, expected) -> None:
    assert s.split_evenly(total, periods) == expected


@pytest.mark.parametrize(
    "total,periods",
    [(100, 3), (123457, 7), (-9991, 4), (5, 5), (1, 8)],
)
def test_split_evenly_sums_to_total(total, periods) -> None:
    assert sum(s.split_evenly(total, periods)) == total


@pytest.mark.parametrize(
    "total,periods",
    [(100, 3), (123457, 7), (5, 5), (1, 8)],
)
def test_split_evenly_remainder_lands_on_last_part(total, periods) -> None:
    parts = s.split_evenly(total, periods)
    base = total // periods
    assert all(p == base for p in parts[:-1])
    assert parts[-1] == base + (total - base * periods)


@pytest.mark.parametrize("periods", [0, -1, -5])
def test_split_evenly_rejects_nonpositive_periods(periods) -> None:
    with pytest.raises(ValueError, match="periods"):
        s.split_evenly(100, periods)


# ---------------------------------------------------------------------------
# _allocate wrapper validation
# ---------------------------------------------------------------------------
def test_allocate_requires_weights_sum_to_full_scale() -> None:
    with pytest.raises(ValueError, match="100.00%"):
        s._allocate(100, [5000, 4000])


@pytest.mark.parametrize(
    "total,weights,expected",
    [
        (100, [5000, 5000], [50, 50]),
        (101, [5000, 5000], [51, 50]),
        (100, [7000, 3000], [70, 30]),
    ],
)
def test_allocate_valid_weights(total, weights, expected) -> None:
    assert s._allocate(total, weights) == expected


# ---------------------------------------------------------------------------
# Partner / ContributedProperty / PropertyYear validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bps", [-1, 10001, 99999])
def test_partner_interest_out_of_range_rejected(bps) -> None:
    with pytest.raises(ValueError, match="interest_bps"):
        s.Partner(code="A", name="a", interest_bps=bps)


@pytest.mark.parametrize("bps", [0, 1, 5000, 10000])
def test_partner_interest_in_range_accepted(bps) -> None:
    assert s.Partner(code="A", name="a", interest_bps=bps).interest_bps == bps


def test_property_negative_fmv_rejected() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        s.ContributedProperty(
            code="P", name="p", contributor="A",
            fmv_cents=-1, tax_basis_cents=50,
        )


def test_property_negative_basis_rejected() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        s.ContributedProperty(
            code="P", name="p", contributor="A",
            fmv_cents=50, tax_basis_cents=-1,
        )


@pytest.mark.parametrize("book_life,tax_life", [(0, 5), (5, 0), (0, 0)])
def test_depreciable_property_requires_positive_lives(book_life, tax_life) -> None:
    with pytest.raises(ValueError, match="lives >= 1"):
        s.ContributedProperty(
            code="P", name="p", contributor="A",
            fmv_cents=100, tax_basis_cents=50,
            depreciable=True, book_life_years=book_life, tax_life_years=tax_life,
        )


def test_property_year_negative_sale_price_rejected() -> None:
    with pytest.raises(ValueError, match="sale price"):
        s.PropertyYear(property="P", year=1, sale_price_cents=-5)


# ---------------------------------------------------------------------------
# built_in_gain_cents / is_cash
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fmv,basis,big",
    [
        (1_200_000, 300_000, 900_000),
        (400_000, 700_000, -300_000),
        (500_000, 500_000, 0),
        (0, 0, 0),
    ],
)
def test_built_in_gain_signed(fmv, basis, big) -> None:
    prop = s.ContributedProperty(
        code="P", name="p", contributor="A",
        fmv_cents=to_cents(fmv), tax_basis_cents=to_cents(basis),
    )
    assert prop.built_in_gain_cents == to_cents(big)


def test_is_cash_true_for_equal_fmv_basis_nondepreciable() -> None:
    prop = s.ContributedProperty(
        code="C", name="c", contributor="B",
        fmv_cents=to_cents(500_000), tax_basis_cents=to_cents(500_000),
    )
    assert prop.is_cash is True


def test_is_cash_false_for_depreciable_even_with_zero_big() -> None:
    prop = s.ContributedProperty(
        code="D", name="d", contributor="A",
        fmv_cents=100, tax_basis_cents=100,
        depreciable=True, book_life_years=2, tax_life_years=2,
    )
    assert prop.built_in_gain_cents == 0
    assert prop.is_cash is False


def test_is_cash_false_when_big_nonzero() -> None:
    prop = s.ContributedProperty(
        code="P", name="p", contributor="A",
        fmv_cents=200, tax_basis_cents=100,
    )
    assert prop.is_cash is False


# ---------------------------------------------------------------------------
# Partnership validation & accessors
# ---------------------------------------------------------------------------
def _mini(method: str = "traditional") -> s.Partnership:
    return s.Partnership(
        code="MINI", name="Mini LP",
        partners={
            "ATLAS": s.Partner(code="ATLAS", name="Atlas", interest_bps=6000),
            "BEACON": s.Partner(code="BEACON", name="Beacon", interest_bps=4000),
        },
        properties={
            "BLDG": s.ContributedProperty(
                code="BLDG", name="b", contributor="ATLAS",
                fmv_cents=to_cents(100_000), tax_basis_cents=to_cents(40_000),
                depreciable=True, book_life_years=5, tax_life_years=5,
            ),
        },
        property_years={},
        partnership_years={},
        years=[1, 2],
        method=method,
    )


@pytest.mark.parametrize("method", ["curative", "ceiling", "", "TRADITIONAL"])
def test_partnership_invalid_method_rejected(method) -> None:
    with pytest.raises(ValueError, match="method"):
        _mini(method=method)


@pytest.mark.parametrize("method", ["traditional", "remedial"])
def test_partnership_valid_method_accepted(method) -> None:
    assert _mini(method=method).method == method


def test_partnership_interests_must_total_full_scale() -> None:
    with pytest.raises(ValueError, match="sum to"):
        s.Partnership(
            code="X", name="X",
            partners={
                "A": s.Partner(code="A", name="a", interest_bps=6000),
                "B": s.Partner(code="B", name="b", interest_bps=5000),
            },
            properties={}, property_years={}, partnership_years={}, years=[1],
        )


def test_partnership_unknown_contributor_rejected() -> None:
    with pytest.raises(ValueError, match="unknown partner"):
        s.Partnership(
            code="X", name="X",
            partners={"A": s.Partner(code="A", name="a", interest_bps=10000)},
            properties={
                "P": s.ContributedProperty(
                    code="P", name="p", contributor="GHOST",
                    fmv_cents=100, tax_basis_cents=50,
                )
            },
            property_years={}, partnership_years={}, years=[1],
        )


def test_ordered_partners_and_properties_are_code_sorted() -> None:
    p = s.generate_partnership()
    assert [x.code for x in p.ordered_partners()] == ["ATLAS", "BEACON"]
    assert [x.code for x in p.ordered_properties()] == ["BEACON_CASH", "HARBOR_BLDG"]


def test_interest_weights_follow_partner_order() -> None:
    assert _mini().interest_weights() == [6000, 4000]


def test_property_year_default_is_unsold_zero_price() -> None:
    p = s.generate_partnership()
    py = p.property_year("HARBOR_BLDG", 999)
    assert py.sold is False
    assert py.sale_price_cents == 0


def test_partnership_year_default_is_zero_income_and_dist() -> None:
    p = s.generate_partnership()
    pyr = p.partnership_year(999)
    assert pyr.ordinary_income_cents == 0
    assert pyr.cash_distribution_cents == 0


# ---------------------------------------------------------------------------
# CapitalAccount copy & formation idempotency
# ---------------------------------------------------------------------------
def test_capital_account_copy_is_independent() -> None:
    a = s.CapitalAccount(book_cents=10, tax_cents=5)
    b = a.copy()
    b.book_cents = 99
    assert a.book_cents == 10
    assert b.book_cents == 99
    assert b.tax_cents == 5


def test_formation_capital_is_idempotent() -> None:
    eng = s.Section704cEngine(s.generate_partnership())
    first = eng.formation_capital()
    second = eng.formation_capital()
    assert first["ATLAS"].book_cents == second["ATLAS"].book_cents
    assert first["ATLAS"].tax_cents == second["ATLAS"].tax_cents


def test_run_after_formation_does_not_double_count_contribution() -> None:
    eng = s.Section704cEngine(s.generate_partnership())
    eng.formation_capital()
    results = eng.run()
    # Year 1 book_open ties to formation FMV, not twice it.
    atlas_y1 = next(p for p in results[0].partners if p.partner == "ATLAS")
    assert atlas_y1.book_open == to_cents(1_200_000)


# ---------------------------------------------------------------------------
# _other_weights renormalisation
# ---------------------------------------------------------------------------
def test_other_weights_renormalise_to_full_scale() -> None:
    partners = {
        "ATLAS": s.Partner(code="ATLAS", name="a", interest_bps=4000),
        "BPART": s.Partner(code="BPART", name="b", interest_bps=3000),
        "CPART": s.Partner(code="CPART", name="c", interest_bps=3000),
    }
    p = s.Partnership(
        code="X", name="X", partners=partners,
        properties={
            "P": s.ContributedProperty(
                code="P", name="p", contributor="ATLAS",
                fmv_cents=100, tax_basis_cents=50,
            )
        },
        property_years={}, partnership_years={}, years=[1],
    )
    weights = s._other_weights(p, "ATLAS")
    assert sum(weights) == s.BPS_SCALE
    assert weights == [5000, 5000]   # equal 30/30 renormalised to 50/50


def test_other_weights_single_other_gets_full_scale() -> None:
    p = s.generate_partnership()  # 50/50, two partners
    weights = s._other_weights(p, "ATLAS")
    assert weights == [s.BPS_SCALE]


# ---------------------------------------------------------------------------
# Built-in-LOSS sale path
# ---------------------------------------------------------------------------
def _bil_partnership() -> s.Partnership:
    return s.Partnership(
        code="BIL", name="BIL LP",
        partners={
            "ATLAS": s.Partner(code="ATLAS", name="a", interest_bps=5000),
            "BEACON": s.Partner(code="BEACON", name="b", interest_bps=5000),
        },
        properties={
            "BLDG": s.ContributedProperty(
                code="BLDG", name="b", contributor="ATLAS",
                fmv_cents=to_cents(400_000), tax_basis_cents=to_cents(700_000),
                depreciable=True, book_life_years=6, tax_life_years=6,
            ),
            "CASH": s.ContributedProperty(
                code="CASH", name="c", contributor="BEACON",
                fmv_cents=to_cents(700_000), tax_basis_cents=to_cents(700_000),
            ),
        },
        property_years={
            ("BLDG", 1): s.PropertyYear(
                property="BLDG", year=1, sold=True, sale_price_cents=to_cents(400_000)
            )
        },
        partnership_years={}, years=[1],
    )


def test_built_in_loss_layer_seeds_negative() -> None:
    res = s.Section704cEngine(_bil_partnership()).run()
    pr = next(x for y in res for x in y.properties if x.property == "BLDG")
    assert pr.layer_open == to_cents(-300_000)


def test_built_in_loss_sale_allocates_loss_to_contributor() -> None:
    res = s.Section704cEngine(_bil_partnership()).run()
    pr = next(x for y in res for x in y.properties if x.property == "BLDG")
    assert pr.tax_gain == to_cents(-300_000)
    assert pr.tax_gain_alloc["ATLAS"] == to_cents(-300_000)
    assert pr.tax_gain_alloc["BEACON"] == 0


def test_built_in_loss_layer_cleared_on_sale() -> None:
    res = s.Section704cEngine(_bil_partnership()).run()
    pr = next(x for y in res for x in y.properties if x.property == "BLDG")
    assert pr.layer_close == 0
    assert pr.layer_cured == to_cents(-300_000)


# ---------------------------------------------------------------------------
# Immediate sale at FMV taxes full BIG to contributor; book gain zero
# ---------------------------------------------------------------------------
def test_immediate_sale_at_fmv_book_gain_zero() -> None:
    p = s.Partnership(
        code="SALE", name="Sale LP",
        partners={
            "ATLAS": s.Partner(code="ATLAS", name="a", interest_bps=5000),
            "BEACON": s.Partner(code="BEACON", name="b", interest_bps=5000),
        },
        properties={
            "BLDG": s.ContributedProperty(
                code="BLDG", name="b", contributor="ATLAS",
                fmv_cents=to_cents(1_200_000), tax_basis_cents=to_cents(600_000),
                depreciable=True, book_life_years=6, tax_life_years=6,
            ),
            "CASH": s.ContributedProperty(
                code="CASH", name="c", contributor="BEACON",
                fmv_cents=to_cents(1_200_000), tax_basis_cents=to_cents(1_200_000),
            ),
        },
        property_years={
            ("BLDG", 1): s.PropertyYear(
                property="BLDG", year=1, sold=True, sale_price_cents=to_cents(1_200_000)
            )
        },
        partnership_years={}, years=[1],
    )
    pr = next(x for y in s.Section704cEngine(p).run() for x in y.properties)
    assert pr.book_gain == 0
    assert pr.tax_gain == to_cents(600_000)
    assert pr.tax_gain_alloc["ATLAS"] == to_cents(600_000)
    assert pr.tax_gain_alloc["BEACON"] == 0


# ---------------------------------------------------------------------------
# generate_partnership guard & method threading
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("n_years", [0, -1, -10])
def test_generate_partnership_rejects_nonpositive_years(n_years) -> None:
    with pytest.raises(ValueError, match="n_years"):
        s.generate_partnership(n_years=n_years)


@pytest.mark.parametrize("n", [1, 3, 6, 8])
def test_generate_partnership_year_count(n) -> None:
    p = s.generate_partnership(n_years=n)
    assert p.years == list(range(1, n + 1))


def test_generate_partnership_defaults_traditional() -> None:
    assert s.generate_partnership().method == "traditional"


def test_generate_partnership_threads_remedial() -> None:
    assert s.generate_partnership(method="remedial").method == "remedial"


# ---------------------------------------------------------------------------
# Layer monotonicity (depreciation only) — never crosses zero
# ---------------------------------------------------------------------------
def test_layer_decreases_monotonically_under_depreciation() -> None:
    # 5 depreciation years (no sale) so we observe the layer narrowing only.
    p = s.Partnership(
        code="DEP", name="Dep LP",
        partners={
            "ATLAS": s.Partner(code="ATLAS", name="a", interest_bps=5000),
            "BEACON": s.Partner(code="BEACON", name="b", interest_bps=5000),
        },
        properties={
            "BLDG": s.ContributedProperty(
                code="BLDG", name="b", contributor="ATLAS",
                fmv_cents=to_cents(1_200_000), tax_basis_cents=to_cents(300_000),
                depreciable=True, book_life_years=6, tax_life_years=6,
            ),
            "CASH": s.ContributedProperty(
                code="CASH", name="c", contributor="BEACON",
                fmv_cents=to_cents(1_200_000), tax_basis_cents=to_cents(1_200_000),
            ),
        },
        property_years={}, partnership_years={}, years=[1, 2, 3, 4, 5],
    )
    res = s.Section704cEngine(p).run()
    rows = [x for y in res for x in y.properties if x.property == "BLDG"]
    for r in rows:
        assert r.layer_close >= 0
        assert r.layer_close <= r.layer_open
    # Each ceiling year cures book(200k)-tax(50k)=150k of the 900k layer.
    assert rows[0].layer_open == to_cents(900_000)
    assert rows[0].layer_close == to_cents(750_000)


# ---------------------------------------------------------------------------
# Reports — rendered Markdown content
# ---------------------------------------------------------------------------
def test_build_reports_keys() -> None:
    artifacts = s.build_reports(s.generate_partnership())
    assert set(artifacts) == {
        "section704c_summary.md",
        "section704c_k1_ATLAS.md",
        "section704c_k1_BEACON.md",
    }


def test_summary_flags_binding_ceiling_under_traditional() -> None:
    summary = s.build_reports(s.generate_partnership())["section704c_summary.md"]
    assert "BINDING" in summary
    assert "FICTIONAL" in summary


def test_summary_balances_on_tax_basis() -> None:
    summary = s.build_reports(s.generate_partnership())["section704c_summary.md"]
    assert "balances" in summary
    assert "OUT OF BALANCE" not in summary


def test_k1_shows_contributor_built_in_gain() -> None:
    artifacts = s.build_reports(s.generate_partnership())
    assert "900,000.00" in artifacts["section704c_k1_ATLAS.md"]


def test_remedial_summary_has_no_binding_ceiling() -> None:
    # The static legend always mentions "BINDING"; the per-row flag ("BINDING
    # short ...") only appears where the ceiling actually binds. The remedial
    # method cures every ceiling year, so the row marker must be absent — while
    # the traditional run shows it for each of its 5 depreciation years.
    remedial = s.build_reports(s.generate_partnership(method="remedial"))[
        "section704c_summary.md"
    ]
    traditional = s.build_reports(s.generate_partnership())["section704c_summary.md"]
    assert remedial.count("BINDING short") == 0
    assert traditional.count("BINDING short") == 5


def test_run_demo_writes_summary_and_k1s(tmp_path) -> None:
    partnership, written = s.run_demo(tmp_path)
    names = [p.name for p in written]
    assert names[0] == "section704c_summary.md"   # summary written first
    assert "section704c_k1_ATLAS.md" in names
    assert "section704c_k1_BEACON.md" in names
    for p in written:
        assert p.exists()


def test_build_reports_deterministic() -> None:
    a = s.build_reports(s.generate_partnership(seed=42))
    b = s.build_reports(s.generate_partnership(seed=42))
    assert a == b
