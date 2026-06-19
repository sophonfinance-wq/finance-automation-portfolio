"""Per-layer (lot-level) FX translation for adjusted cost base.

The Summary layer (:func:`surplus_engine.report.consolidated_summary`) converts a
*closing* ACB balance to CAD at a single year's rate::

    acb_cad = closing.acb * fx_rate(final_year)

That is fine for a point-in-time pool snapshot, but the adjusted cost base of a
foreign affiliate is not a snapshot — it is built from capital events that occur
in different years. For Canadian tax purposes each event is translated at the
exchange rate prevailing when it occurred (ITA 261 functional-currency / foreign
exchange conventions). Translating the *net* closing balance at one rate silently
assumes every layer arose at that one rate.

This module re-derives ACB in CAD the layered way. Each capital contribution
(ACB up) and each *applied* return of capital (ACB down) is a **layer**,
translated at its own year's rate, then netted::

    acb_cad = Σ contribution_layer.fc * rate(layer.year)
            − Σ return_layer.fc       * rate(layer.year)

Two properties make this worth its own module:

1. **It reconciles in functional currency.** The engine never lets an applied
   return of capital exceed the running ACB — the excess becomes a deemed gain
   (see :mod:`surplus_engine.engine`). So the *signed functional-currency* layers
   always sum back to the engine's closing ACB to the cent. The FX layer model
   cannot drift from the engine; it only re-times the currency translation.
2. **The CAD figure can change magnitude — and sign.** When a large contribution
   and a large return of capital fall in years with materially different rates,
   the single-rate and per-layer CAD figures diverge. A positive
   functional-currency ACB can translate to a *negative* CAD ACB. Collapsing
   every layer to one rate hides that "blended-rate trap".

Everything here operates on the *fictional* engine output; no real data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .engine import EntityYearResult
from .model import Structure

CONTRIBUTION = "contribution"
RETURN_OF_CAPITAL = "return_of_capital"

# Functional-currency reconciliation tolerance (cents). The signed layers are
# expected to sum back to the engine's closing ACB within this.
FC_TOLERANCE = 0.01

_MONEY_DP = 2


def _r(x: float) -> float:
    """Round to money precision, normalising ``-0.0`` to ``0.0``."""
    v = round(x, _MONEY_DP)
    return 0.0 if v == 0 else v


def _money(x: float) -> str:
    """Thousands-separated, parentheses for negatives (matches the report layer)."""
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


@dataclass(frozen=True)
class AcbLayer:
    """One ACB-moving capital event, with the rate used to translate it.

    ``amount_fc`` is always a positive magnitude in the entity's functional
    currency; ``kind`` carries the direction.
    """

    entity: str
    year: int
    kind: str  # CONTRIBUTION | RETURN_OF_CAPITAL
    amount_fc: float
    currency: str
    rate_to_cad: float

    @property
    def signed_fc(self) -> float:
        """Functional-currency contribution to ACB (+ for contributions)."""
        return self.amount_fc if self.kind == CONTRIBUTION else -self.amount_fc

    @property
    def signed_cad(self) -> float:
        """CAD contribution to ACB, translated at this layer's own year rate."""
        return self.signed_fc * self.rate_to_cad


@dataclass
class AcbFxReconciliation:
    """Per-entity comparison of single-rate vs per-layer CAD ACB."""

    entity: str
    currency: str
    final_year: int

    closing_acb_fc: float        # engine's closing ACB (functional currency)
    layered_acb_fc: float        # Σ signed_fc — must equal closing_acb_fc
    fc_reconciles: bool          # |layered_acb_fc − closing_acb_fc| <= FC_TOLERANCE

    single_rate: float           # rate(final_year) — the current report.py approach
    single_rate_acb_cad: float   # closing_acb_fc * single_rate
    per_layer_acb_cad: float     # Σ signed_cad
    divergence_cad: float        # per_layer − single_rate
    sign_flip: bool              # the two CAD figures have opposite signs

    layers: List[AcbLayer] = field(default_factory=list)


def acb_layers(
    results: List[EntityYearResult], structure: Structure
) -> Dict[str, List[AcbLayer]]:
    """Extract ordered ACB layers per entity from engine results.

    A capital contribution is a positive layer. A return of capital is a negative
    layer, but only for the portion *applied* to ACB — the part beyond ACB became
    a deemed gain (``deemed_gain_on_negative_acb``) and never reduced basis, so it
    is not a layer.
    """
    layers: Dict[str, List[AcbLayer]] = {code: [] for code in structure.entities}
    for r in sorted(results, key=lambda x: (x.entity, x.year)):
        rate = structure.fx.rate(r.year, r.currency)
        if r.capital_contribution > 0:
            layers[r.entity].append(
                AcbLayer(r.entity, r.year, CONTRIBUTION, _r(r.capital_contribution), r.currency, rate)
            )
        applied_roc = _r(r.return_of_capital - r.deemed_gain_on_negative_acb)
        if applied_roc > 0:
            layers[r.entity].append(
                AcbLayer(r.entity, r.year, RETURN_OF_CAPITAL, applied_roc, r.currency, rate)
            )
    return layers


def acb_fx_reconciliations(
    results: List[EntityYearResult], structure: Structure
) -> List[AcbFxReconciliation]:
    """Build a per-entity single-rate vs per-layer CAD ACB reconciliation."""
    layers_by_entity = acb_layers(results, structure)
    final_result: Dict[str, EntityYearResult] = {}
    for r in results:
        cur = final_result.get(r.entity)
        if cur is None or r.year > cur.year:
            final_result[r.entity] = r

    out: List[AcbFxReconciliation] = []
    for code in structure.entities:
        r = final_result.get(code)
        if r is None:
            continue
        layers = layers_by_entity[code]
        closing_acb_fc = _r(r.closing.acb)
        layered_acb_fc = _r(sum(l.signed_fc for l in layers))
        single_rate = structure.fx.rate(r.year, r.currency)
        single_rate_cad = _r(closing_acb_fc * single_rate)
        per_layer_cad = _r(sum(l.signed_cad for l in layers))
        divergence = _r(per_layer_cad - single_rate_cad)
        sign_flip = (
            (per_layer_cad < 0) != (single_rate_cad < 0)
            and max(abs(per_layer_cad), abs(single_rate_cad)) > 0.005
        )
        out.append(
            AcbFxReconciliation(
                entity=code,
                currency=r.currency,
                final_year=r.year,
                closing_acb_fc=closing_acb_fc,
                layered_acb_fc=layered_acb_fc,
                fc_reconciles=abs(layered_acb_fc - closing_acb_fc) <= FC_TOLERANCE,
                single_rate=single_rate,
                single_rate_acb_cad=single_rate_cad,
                per_layer_acb_cad=per_layer_cad,
                divergence_cad=divergence,
                sign_flip=sign_flip,
                layers=layers,
            )
        )
    return out


def render_fx_analysis(
    results: List[EntityYearResult], structure: Structure
) -> str:
    """Render the per-layer FX analysis as Markdown."""
    recs = acb_fx_reconciliations(results, structure)
    out: List[str] = []
    out.append("# ACB FX — Single-Rate vs Per-Layer [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional entities and amounts. Illustrates the public ITA 261 / Reg. "
        "5907 principle that each ACB layer is translated at its own year's rate; "
        "not real data or methodology."
    )
    out.append("")
    out.append(
        "ACB is built from capital events in different years. Translating the net "
        "closing balance at one rate (the Summary-layer convention) assumes every "
        "layer arose at that rate. Translating each layer at its own year's rate is "
        "the correct treatment — and can change the CAD figure's magnitude or sign."
    )
    out.append("")
    out.append(
        "| Entity | Cur | Closing ACB (FC) | Single-rate ACB (CAD) | Per-layer ACB (CAD) | "
        "Divergence (CAD) | Sign flip | FC ties |"
    )
    out.append(
        "|--------|-----|----------------:|----------------------:|--------------------:|"
        "-----------------:|:---------:|:-------:|"
    )
    for rec in recs:
        out.append(
            f"| {structure.entities[rec.entity].name} | {rec.currency} | "
            f"{_money(rec.closing_acb_fc)} | {_money(rec.single_rate_acb_cad)} | "
            f"{_money(rec.per_layer_acb_cad)} | {_money(rec.divergence_cad)} | "
            f"{'⚑ yes' if rec.sign_flip else '—'} | {'✓' if rec.fc_reconciles else '✗'} |"
        )
    out.append("")
    out.append(
        "_FC ties = signed functional-currency layers sum back to the engine's "
        "closing ACB (the per-layer model cannot drift from the engine). "
        "⚑ = per-layer and single-rate CAD figures have opposite signs._"
    )
    out.append("")

    # Layer detail for entities that actually have capital events.
    detailed = [r for r in recs if r.layers]
    if detailed:
        out.append("## Layer detail")
        out.append("")
        for rec in detailed:
            out.append(f"### {structure.entities[rec.entity].name} ({rec.currency})")
            out.append("")
            out.append("| FY | Event | Amount (FC) | Rate | Signed (CAD) |")
            out.append("|----|-------|------------:|-----:|-------------:|")
            for l in rec.layers:
                label = "Contribution" if l.kind == CONTRIBUTION else "Return of capital"
                out.append(
                    f"| {l.year} | {label} | {_money(l.amount_fc)} | "
                    f"{l.rate_to_cad:.4f} | {_money(l.signed_cad)} |"
                )
            out.append(
                f"| | **Per-layer ACB (CAD)** | | | **{_money(rec.per_layer_acb_cad)}** |"
            )
            out.append(
                f"| | _Single-rate ACB (CAD)_ | | {rec.single_rate:.4f} | "
                f"_{_money(rec.single_rate_acb_cad)}_ |"
            )
            out.append("")
    return "\n".join(out)
