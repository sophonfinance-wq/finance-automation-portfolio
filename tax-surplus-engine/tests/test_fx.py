"""Per-layer FX translation: functional-currency tie-out, CAD divergence, sign flip."""

from __future__ import annotations

from surplus_engine.engine import SurplusEngine
from surplus_engine.fx import (
    CONTRIBUTION,
    RETURN_OF_CAPITAL,
    acb_fx_reconciliations,
    acb_layers,
)
from surplus_engine.model import FxTable
from tests.conftest import make_entity, make_facts, make_structure  # noqa: F401


def _run(structure, years):
    return SurplusEngine(structure).run(years)


def test_acb_layers_classify_events(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, capital_contribution=500_000),
        make_facts("SOLO", 2022, distribution=100_000, return_of_capital=100_000),
    ]
    struct = single_entity_factory(facts)
    results = _run(struct, [2021, 2022])
    layers = acb_layers(results, struct)["SOLO"]
    assert [(l.year, l.kind, l.amount_fc) for l in layers] == [
        (2021, CONTRIBUTION, 500_000.0),
        (2022, RETURN_OF_CAPITAL, 100_000.0),
    ]


def test_fc_layers_tie_back_to_closing_acb(single_entity_factory):
    # Contributions in two years, a partial return of capital in a third.
    facts = [
        make_facts("SOLO", 2021, capital_contribution=300_000),
        make_facts("SOLO", 2022, capital_contribution=100_000),
        make_facts("SOLO", 2023, distribution=120_000, return_of_capital=120_000),
    ]
    fx = FxTable(usd_cad={2021: 1.25, 2022: 1.30, 2023: 1.40})
    struct = single_entity_factory(facts, fx=fx)
    results = _run(struct, [2021, 2022, 2023])
    rec = acb_fx_reconciliations(results, struct)[0]
    # closing ACB = 300k + 100k - 120k = 280k
    assert rec.closing_acb_fc == 280_000
    assert rec.layered_acb_fc == 280_000
    assert rec.fc_reconciles


def test_cad_entity_has_no_fx_divergence(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, capital_contribution=500_000),
        make_facts("SOLO", 2022, distribution=200_000, return_of_capital=200_000),
    ]
    fx = FxTable(usd_cad={2021: 1.30, 2022: 1.45})
    struct = single_entity_factory(facts, currency="CAD", fx=fx)
    results = _run(struct, [2021, 2022])
    rec = acb_fx_reconciliations(results, struct)[0]
    assert rec.currency == "CAD"
    assert rec.single_rate == 1.0
    assert rec.per_layer_acb_cad == rec.single_rate_acb_cad == 300_000
    assert rec.divergence_cad == 0.0
    assert not rec.sign_flip


def test_per_layer_differs_from_single_rate(single_entity_factory):
    facts = [
        make_facts("SOLO", 2021, capital_contribution=1_000_000),
        make_facts("SOLO", 2023, distribution=400_000, return_of_capital=400_000),
    ]
    fx = FxTable(usd_cad={2021: 1.20, 2023: 1.45})
    struct = single_entity_factory(facts, fx=fx)
    results = _run(struct, [2021, 2023])
    rec = acb_fx_reconciliations(results, struct)[0]
    assert rec.closing_acb_fc == 600_000
    # single-rate: 600k * 1.45
    assert rec.single_rate_acb_cad == 870_000
    # per-layer: 1,000k*1.20 - 400k*1.45 = 1,200k - 580k
    assert rec.per_layer_acb_cad == 620_000
    assert rec.divergence_cad == -250_000
    assert not rec.sign_flip  # both still positive


def test_sign_flip_when_offsetting_layers_in_different_rate_years(single_entity_factory):
    # The headline case: a positive functional-currency ACB that translates to a
    # NEGATIVE CAD ACB once each layer is taken at its own year's rate.
    facts = [
        make_facts(
            "SOLO", 2018,
            capital_contribution=13_000_000,
            distribution=11_000_000,
            return_of_capital=11_000_000,
        ),
        make_facts("SOLO", 2023, distribution=1_990_000, return_of_capital=1_990_000),
    ]
    fx = FxTable(usd_cad={2018: 1.20, 2023: 1.45})
    struct = single_entity_factory(facts, fx=fx)
    results = _run(struct, [2018, 2023])
    rec = acb_fx_reconciliations(results, struct)[0]
    # closing ACB (USD) = 13M - 11M - 1.99M = 10,000 (positive)
    assert rec.closing_acb_fc == 10_000
    assert rec.fc_reconciles
    # single-rate CAD = 10,000 * 1.45 = 14,500 (positive)
    assert rec.single_rate_acb_cad == 14_500
    # per-layer CAD = 13M*1.20 - 11M*1.20 - 1.99M*1.45 = -485,500 (NEGATIVE)
    assert rec.per_layer_acb_cad == -485_500
    assert rec.sign_flip


def test_return_of_capital_beyond_basis_not_layered(single_entity_factory):
    # ROC beyond ACB becomes a deemed gain and never reduces basis, so only the
    # APPLIED portion is a layer.
    facts = [
        make_facts("SOLO", 2021, capital_contribution=100_000),
        make_facts("SOLO", 2022, distribution=500_000, return_of_capital=500_000),
    ]
    struct = single_entity_factory(facts)
    results = _run(struct, [2021, 2022])
    rec = acb_fx_reconciliations(results, struct)[0]
    assert rec.closing_acb_fc == 0.0
    assert rec.layered_acb_fc == 0.0  # +100k contribution - 100k applied ROC
    roc_layers = [l for l in acb_layers(results, struct)["SOLO"] if l.kind == RETURN_OF_CAPITAL]
    assert len(roc_layers) == 1
    assert roc_layers[0].amount_fc == 100_000.0  # only the applied portion
