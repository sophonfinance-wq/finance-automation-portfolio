"""Reconciliation harness: independently re-derive the roll-forward and prove
the structural identities the engine must satisfy.

This mirrors how a reviewer rebuilds a workpaper from its own inputs and proves
it ties out, instead of trusting the stored numbers. Each check is a *named
identity* with an expected value, an actual value, and a signed delta — so a
break points straight at the entity, year, and quantity that disagrees (the same
discipline as a cell-level tie-out on a real workpaper).

The harness re-implements each statutory step from the exposed intermediate
quantities on :class:`~surplus_engine.engine.EntityYearResult` and compares the
result to the engine's stored closing balances. Because it is an *independent*
recomputation, it catches any regression that makes the engine's internal
bookkeeping disagree with its own published intermediates.

Identities checked
------------------
* **Roll-forward continuity** — each entity's closing balances in year *N* equal
  its opening balances in year *N+1* (all four pools incl. ACB).
* **Exempt / taxable conservation** — closing pool = opening + current addition
  + elevation − amount drawn in the waterfall (taxable floored at zero pre-draw).
* **Pre-acquisition conservation** — closing = opening + capital contribution −
  amount drawn from the pre-acquisition pool.
* **ACB conservation** — closing ACB = max(0, opening + contribution − return of
  capital); and the deemed gain equals the return of capital beyond basis.
* **Waterfall integrity** — total drawn ≤ distribution, and the exempt draw
  never exceeds the exempt-distribution cap.
* **Non-negativity** — no closing pool or ACB is negative.
* **Elevation conservation** — surplus elevated into a parent equals the sum over
  its children of (exempt/taxable drawn × ownership %).
* **ACB FX reconciliation** — signed functional-currency ACB layers sum back to
  the engine's closing ACB (ties :mod:`surplus_engine.fx` to the engine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .engine import EntityYearResult
from .fx import acb_fx_reconciliations
from .model import EXEMPT, PREACQ, TAXABLE, Structure

# Default tie-out tolerance (cents). Rounding across the engine's ``_r`` steps can
# leave sub-cent residue; anything larger is a genuine break.
DEFAULT_TOLERANCE = 0.02


def _money(x: float) -> str:
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


@dataclass(frozen=True)
class ReconCheck:
    """One named identity tie-out."""

    name: str
    entity: str
    year: Optional[int]
    expected: float
    actual: float
    passed: bool

    @property
    def delta(self) -> float:
        return round(self.actual - self.expected, 4)


@dataclass
class ReconReport:
    """The full set of checks plus convenience roll-ups."""

    checks: List[ReconCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def breaks(self) -> List[ReconCheck]:
        return [c for c in self.checks if not c.passed]

    def counts_by_name(self) -> Dict[str, Tuple[int, int]]:
        """``{identity_name: (passed, total)}`` for a compact summary."""
        agg: Dict[str, Tuple[int, int]] = {}
        for c in self.checks:
            p, t = agg.get(c.name, (0, 0))
            agg[c.name] = (p + (1 if c.passed else 0), t + 1)
        return agg


def _drawn(result: EntityYearResult) -> Dict[str, float]:
    """Pool → amount drawn in this year's distribution waterfall."""
    d: Dict[str, float] = {EXEMPT: 0.0, TAXABLE: 0.0, PREACQ: 0.0}
    for step in result.waterfall:
        d[step.pool] = d.get(step.pool, 0.0) + step.amount
    return d


def reconcile(
    results: List[EntityYearResult],
    structure: Structure,
    tol: float = DEFAULT_TOLERANCE,
) -> ReconReport:
    """Run every identity check and return a :class:`ReconReport`."""
    checks: List[ReconCheck] = []

    def check(name: str, entity: str, year: Optional[int], expected: float, actual: float) -> None:
        checks.append(
            ReconCheck(name, entity, year, round(expected, 2), round(actual, 2),
                       abs(actual - expected) <= tol)
        )

    by_key: Dict[Tuple[str, int], EntityYearResult] = {
        (r.entity, r.year): r for r in results
    }

    # --- per (entity, year) conservation identities ----------------------
    for r in results:
        drawn = _drawn(r)

        # Exempt: opening + current + elevation − drawn.
        exp_exempt = (
            r.opening.exempt_surplus
            + r.current_exempt_addition
            + r.elevated_exempt
            - drawn[EXEMPT]
        )
        check("exempt_conservation", r.entity, r.year, exp_exempt, r.closing.exempt_surplus)

        # Taxable: pool is floored at zero *before* the waterfall draw.
        taxable_pre_draw = max(
            0.0,
            r.opening.taxable_surplus + r.current_taxable_addition + r.elevated_taxable,
        )
        exp_taxable = taxable_pre_draw - drawn[TAXABLE]
        check("taxable_conservation", r.entity, r.year, exp_taxable, r.closing.taxable_surplus)

        # Pre-acquisition capital: opening + contribution − drawn.
        exp_preacq = r.opening.pre_acquisition_capital + r.capital_contribution - drawn[PREACQ]
        check("preacq_conservation", r.entity, r.year, exp_preacq, r.closing.pre_acquisition_capital)

        # ACB: max(0, opening + contribution − return of capital).
        acb_before_roc = r.opening.acb + r.capital_contribution
        exp_acb = max(0.0, acb_before_roc - r.return_of_capital)
        check("acb_conservation", r.entity, r.year, exp_acb, r.closing.acb)

        # Deemed gain = return of capital beyond available basis.
        exp_gain = max(0.0, r.return_of_capital - acb_before_roc)
        check("deemed_gain", r.entity, r.year, exp_gain, r.deemed_gain_on_negative_acb)

        # Waterfall integrity: total drawn ≤ distribution; exempt draw ≤ cap.
        total_drawn = drawn[EXEMPT] + drawn[TAXABLE] + drawn[PREACQ]
        check("waterfall_le_distribution", r.entity, r.year,
              0.0, max(0.0, total_drawn - r.distribution - tol))
        check("exempt_within_cap", r.entity, r.year,
              0.0, max(0.0, drawn[EXEMPT] - r.exempt_cap_amount - tol))

        # Non-negativity of every closing balance.
        worst_negative = min(
            r.closing.exempt_surplus,
            r.closing.taxable_surplus,
            r.closing.pre_acquisition_capital,
            r.closing.acb,
        )
        check("non_negative_balances", r.entity, r.year, 0.0, max(0.0, -worst_negative))

    # --- roll-forward continuity (closing[N] == opening[N+1]) ------------
    years = sorted(structure.years or sorted({r.year for r in results}))
    for code in structure.entities:
        for y0, y1 in zip(years, years[1:]):
            a = by_key.get((code, y0))
            b = by_key.get((code, y1))
            if a is None or b is None:
                continue
            for pool_name, get in (
                ("exempt", lambda p: p.exempt_surplus),
                ("taxable", lambda p: p.taxable_surplus),
                ("preacq", lambda p: p.pre_acquisition_capital),
                ("acb", lambda p: p.acb),
            ):
                check(f"continuity_{pool_name}", code, y1, get(a.closing), get(b.opening))

    # --- elevation conservation (parent receives Σ children drawn × pct) --
    for year in years:
        for parent in structure.entities.values():
            pr = by_key.get((parent.code, year))
            if pr is None:
                continue
            exp_ex = 0.0
            exp_tx = 0.0
            for child in structure.children_of(parent.code):
                cr = by_key.get((child.code, year))
                if cr is None or child.ownership_pct <= 0:
                    continue
                drawn = _drawn(cr)
                exp_ex += drawn[EXEMPT] * child.ownership_pct
                exp_tx += drawn[TAXABLE] * child.ownership_pct
            check("elevation_exempt", parent.code, year, exp_ex, pr.elevated_exempt)
            check("elevation_taxable", parent.code, year, exp_tx, pr.elevated_taxable)

    # --- ACB FX reconciliation (signed FC layers == closing ACB) ---------
    for rec in acb_fx_reconciliations(results, structure):
        check("acb_fx_layers_tie", rec.entity, rec.final_year,
              rec.closing_acb_fc, rec.layered_acb_fc)

    return ReconReport(checks=checks)


def render_reconciliation(report: ReconReport, structure: Optional[Structure] = None) -> str:
    """Render the reconciliation report as Markdown."""
    out: List[str] = []
    out.append("# Reconciliation Report — Structural Identity Tie-Out [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional data. Independent re-derivation of the engine roll-forward; "
        "every statutory identity is recomputed from published intermediates and "
        "tied back to the engine's stored balances."
    )
    out.append("")
    status = "✅ ALL CHECKS PASS" if report.ok else f"❌ {len(report.breaks)} BREAK(S)"
    out.append(f"**Result: {status}**  ·  {len(report.checks)} checks total")
    out.append("")
    out.append("| Identity | Passed / Total |")
    out.append("|----------|:--------------:|")
    for name, (passed, total) in sorted(report.counts_by_name().items()):
        mark = "✓" if passed == total else "✗"
        out.append(f"| `{name}` | {mark} {passed} / {total} |")
    out.append("")

    if report.breaks:
        out.append("## Breaks")
        out.append("")
        out.append("| Identity | Entity | FY | Expected | Actual | Delta |")
        out.append("|----------|--------|----|---------:|-------:|------:|")
        for c in report.breaks:
            fy = "—" if c.year is None else str(c.year)
            out.append(
                f"| `{c.name}` | {c.entity} | {fy} | {_money(c.expected)} | "
                f"{_money(c.actual)} | {_money(c.delta)} |"
            )
        out.append("")
    else:
        out.append(
            "_No breaks. Closing balances, ACB, the distribution waterfall, "
            "elevation, and the per-layer FX tie-out all reconcile within tolerance._"
        )
        out.append("")
    return "\n".join(out)
