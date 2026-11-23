"""Reporting layer: per-entity workpapers and a consolidated summary.

Honours the source-of-truth lineage from the project narrative:

    Evidence (cited inputs) -> Surplus-Details (derived) -> Summary (+ FX)

Per-entity workpapers are emitted as Markdown. A consolidated multi-entity
summary rolls every entity/year into one table, converting each entity's
functional-currency closing pools into CAD via the fictional FX table.
"""

from __future__ import annotations

from typing import Dict, List

from .engine import EntityYearResult
from .model import EXEMPT, PREACQ, TAXABLE, Structure

_POOL_LABEL = {
    EXEMPT: "Exempt surplus",
    TAXABLE: "Taxable surplus",
    PREACQ: "Pre-acquisition capital",
}


def _money(x: float) -> str:
    """Format a number with thousands separators and parens for negatives."""
    if x < 0:
        return f"({abs(x):,.2f})"
    return f"{x:,.2f}"


def attach_fx(results: List[EntityYearResult], structure: Structure) -> None:
    """Fill ``fx_rate_to_cad`` on each result from the structure's FX table."""
    for r in results:
        r.fx_rate_to_cad = structure.fx.rate(r.year, r.currency)


def entity_workpaper(
    entity_code: str,
    results: List[EntityYearResult],
    structure: Structure,
) -> str:
    """Render a single entity's multi-year workpaper as Markdown."""
    ent = structure.entities[entity_code]
    rows = sorted(
        [r for r in results if r.entity == entity_code], key=lambda r: r.year
    )
    parent = structure.entities[ent.parent].name if ent.parent else "— (top holdco)"

    out: List[str] = []
    out.append(f"# Workpaper — {ent.name} ({ent.code}) [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Invented entity and amounts for demonstration. Implements the public "
        "Reg. 5907 surplus framework generically; not real methodology or figures."
    )
    out.append("")
    out.append(
        f"**Tier:** {ent.tier} &nbsp;·&nbsp; **Functional currency:** {ent.currency} "
        f"&nbsp;·&nbsp; **Owned by:** {parent} @ {ent.ownership_pct:.0%}"
    )
    out.append("")

    # --- Layer 1: Evidence -------------------------------------------------
    out.append("## Layer 1 — Evidence (cited inputs)")
    out.append("")
    out.append(
        "| FY | Standalone taxable income | Reg. 5907(2) adj | Exempt % | "
        "Distribution | Capital contribution | Return of capital |"
    )
    out.append("|----|--------------------------:|-----------------:|---------:|"
               "-------------:|---------------------:|------------------:|")
    for r in rows:
        out.append(
            f"| {r.year} | {_money(r.standalone_taxable_income)} | "
            f"{_money(r.reg_5907_2_adjustment)} | {r.exempt_portion:.0%} | "
            f"{_money(r.distribution)} | {_money(r.capital_contribution)} | "
            f"{_money(r.return_of_capital)} |"
        )
    out.append("")

    # --- Layer 2: Surplus-Details -----------------------------------------
    out.append("## Layer 2 — Surplus-Details (derived; rolls forward)")
    out.append("")
    out.append(
        "| FY | Standalone surplus | + Exempt | + Taxable | "
        "Elevated exempt | Elevated taxable | Distribution draws | Exempt cap |"
    )
    out.append("|----|-------------------:|---------:|----------:|"
               "----------------:|-----------------:|:-------------------|----------:|")
    for r in rows:
        draws = (
            ", ".join(f"{_POOL_LABEL[s.pool].split()[0]} {_money(s.amount)}" for s in r.waterfall)
            or "—"
        )
        cap = _money(r.exempt_cap_amount) + (" ⚑" if r.exempt_cap_binding else "")
        out.append(
            f"| {r.year} | {_money(r.standalone_surplus)} | "
            f"{_money(r.current_exempt_addition)} | {_money(r.current_taxable_addition)} | "
            f"{_money(r.elevated_exempt)} | {_money(r.elevated_taxable)} | {draws} | {cap} |"
        )
    out.append("")
    out.append("_⚑ = exempt-distribution cap was binding (limited the exempt draw)._")
    out.append("")

    # --- Layer 3: Summary (closing balances + FX) -------------------------
    out.append("## Layer 3 — Summary (closing pool balances + ACB, with FX→CAD)")
    out.append("")
    out.append(
        "| FY | Exempt surplus | Taxable surplus | Pre-acq capital | ACB | "
        f"FX→CAD | Total surplus (CAD) |"
    )
    out.append("|----|---------------:|----------------:|----------------:|----:|"
               "-------:|--------------------:|")
    for r in rows:
        total_surplus = (
            r.closing.exempt_surplus
            + r.closing.taxable_surplus
            + r.closing.pre_acquisition_capital
        )
        out.append(
            f"| {r.year} | {_money(r.closing.exempt_surplus)} | "
            f"{_money(r.closing.taxable_surplus)} | "
            f"{_money(r.closing.pre_acquisition_capital)} | {_money(r.closing.acb)} | "
            f"{r.fx_rate_to_cad:.4f} | {_money(total_surplus * r.fx_rate_to_cad)} |"
        )
    out.append("")
    out.append(
        "_Lineage: Evidence (cited) → Surplus-Details (derived, rolled forward) → "
        "Summary (+ FX). ACB moves only on capital events; surplus elevates only on "
        "actual distributions._"
    )
    dg_rows = [r for r in rows if r.deemed_gain_on_negative_acb > 0]
    if dg_rows:
        out.append("")
        out.append("**Deemed gains on negative ACB (ITA 40(3)-style):**")
        for r in dg_rows:
            out.append(
                f"- FY{r.year}: return of capital exceeded ACB by "
                f"{_money(r.deemed_gain_on_negative_acb)} → deemed capital gain to the "
                f"owner; ACB deemed nil."
            )
    out.append("")
    return "\n".join(out)


def consolidated_summary(
    results: List[EntityYearResult], structure: Structure
) -> str:
    """Render the consolidated multi-entity summary (all in CAD)."""
    out: List[str] = []
    out.append("# Consolidated Surplus & ACB Summary [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional multi-tier structure. Closing pool balances per entity/year, "
        "each converted to CAD via the fictional FX table."
    )
    out.append("")
    out.append(
        "| FY | Entity | Cur | Exempt (CAD) | Taxable (CAD) | Pre-acq (CAD) | "
        "ACB (CAD) | Total surplus (CAD) |"
    )
    out.append("|----|--------|-----|-------------:|--------------:|--------------:|"
               "----------:|--------------------:|")

    by_year: Dict[int, List[EntityYearResult]] = {}
    for r in results:
        by_year.setdefault(r.year, []).append(r)

    grand_total = 0.0
    for year in sorted(by_year):
        rows = sorted(by_year[year], key=lambda r: -structure.entities[r.entity].tier)
        for r in rows:
            fx = r.fx_rate_to_cad
            ex = r.closing.exempt_surplus * fx
            tx = r.closing.taxable_surplus * fx
            pa = r.closing.pre_acquisition_capital * fx
            acb = r.closing.acb * fx
            tot = ex + tx + pa
            grand_total += tot
            out.append(
                f"| {year} | {structure.entities[r.entity].name} | {r.currency} | "
                f"{_money(ex)} | {_money(tx)} | {_money(pa)} | {_money(acb)} | {_money(tot)} |"
            )
    out.append("")
    out.append(f"**Grand total surplus across all entity-years (CAD): {_money(grand_total)}**")
    out.append("")
    return "\n".join(out)
