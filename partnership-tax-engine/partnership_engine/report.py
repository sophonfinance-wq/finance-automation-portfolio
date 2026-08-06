"""Reporting layer: Schedule K-1-style capital analyses and a 1065 summary.

Three Markdown artifacts are produced:

* :func:`partner_k1` — a per-partner capital-account analysis on BOTH a §704(b)
  book basis and a tax basis (beginning + contributions + share of income/(loss)
  − distributions = ending), with the §704(c) effect called out.
* :func:`partnership_summary` — a partnership tax-basis balance sheet
  (assets = liabilities + tax capital), a book-vs-tax capital reconciliation, and
  the §704(c) layer roll-forward for each contributed property.

All figures originate from the integer-cent engine; formatting to dollars happens
only here, at the edge.
"""

from __future__ import annotations

from typing import Dict, List

from .engine import PartnershipEngine, PartnerYearResult, PropertyYearResult, YearResult
from .model import Partnership
from .money import fmt


def _signed(cents: int) -> str:
    """Format a signed cent amount, using parentheses for negatives."""
    return fmt(cents)


def _gather_partner_rows(
    results: List[YearResult], partner_code: str
) -> List[PartnerYearResult]:
    rows: List[PartnerYearResult] = []
    for yr in results:
        for pr in yr.partners:
            if pr.partner == partner_code:
                rows.append(pr)
    return rows


def _gather_property_rows(
    results: List[YearResult], prop_code: str
) -> List[PropertyYearResult]:
    rows: List[PropertyYearResult] = []
    for yr in results:
        for pr in yr.properties:
            if pr.property == prop_code:
                rows.append(pr)
    return rows


def partner_k1(
    partnership: Partnership,
    results: List[YearResult],
    formation: Dict[str, "object"],
    partner_code: str,
) -> str:
    """Render a single partner's Schedule K-1-style capital analysis (Markdown).

    Shows beginning, contributions, share of income/(loss), distributions and
    ending capital on BOTH a §704(b) book basis and a tax basis, plus the
    §704(c) built-in gain/(loss) the partner carries.
    """
    partner = partnership.partners[partner_code]
    rows = _gather_partner_rows(results, partner_code)
    form = formation[partner_code]
    pct = partner.interest_bps / 100.0

    # The §704(c) built-in gain this partner carries = sum of BIG/BIL on the
    # property they contributed.
    big = sum(
        p.built_in_gain_cents
        for p in partnership.properties.values()
        if p.contributor == partner_code
    )

    out: List[str] = []
    out.append(f"# Schedule K-1 Capital Analysis — {partner.name} [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Invented partner and amounts for demonstration. Implements the public "
        "US partnership-tax framework (Form 1065, IRC §704(b)/§704(c), traditional "
        "method) generically; not real methodology or figures."
    )
    out.append("")
    out.append(
        f"**Partnership:** {partnership.name} &nbsp;·&nbsp; "
        f"**Profit/loss interest:** {pct:.2f}% &nbsp;·&nbsp; "
        f"**§704(c) built-in gain/(loss) at formation:** {_signed(big)}"
    )
    out.append("")

    # --- §704(b) book basis ------------------------------------------------
    out.append("## Capital account on a §704(b) book basis")
    out.append("")
    out.append(
        "| FY | Beginning | + Contributions | + Income/(loss) | − Distributions | Ending |"
    )
    out.append("|----|----------:|----------------:|----------------:|----------------:|-------:|")
    out.append(
        f"| 0 (formation) | {fmt(0)} | {fmt(form.book_cents)} | {fmt(0)} | "
        f"{fmt(0)} | {fmt(form.book_cents)} |"
    )
    for r in rows:
        out.append(
            f"| {r.year} | {fmt(r.book_open)} | {fmt(r.contribution_book)} | "
            f"{_signed(r.income_book)} | {fmt(r.distribution)} | {fmt(r.book_close)} |"
        )
    out.append("")

    # --- tax basis ---------------------------------------------------------
    out.append("## Capital account on a tax basis")
    out.append("")
    out.append(
        "| FY | Beginning | + Contributions | + Income/(loss) | − Distributions | Ending |"
    )
    out.append("|----|----------:|----------------:|----------------:|----------------:|-------:|")
    out.append(
        f"| 0 (formation) | {fmt(0)} | {fmt(form.tax_cents)} | {fmt(0)} | "
        f"{fmt(0)} | {fmt(form.tax_cents)} |"
    )
    for r in rows:
        out.append(
            f"| {r.year} | {fmt(r.tax_open)} | {fmt(r.contribution_tax)} | "
            f"{_signed(r.income_tax)} | {fmt(r.distribution)} | {fmt(r.tax_close)} |"
        )
    out.append("")

    # --- book vs tax disparity --------------------------------------------
    out.append("## §704(c) effect — book vs. tax disparity over time")
    out.append("")
    out.append("| FY | Book capital | Tax capital | Book − Tax disparity |")
    out.append("|----|-------------:|------------:|---------------------:|")
    out.append(
        f"| 0 (formation) | {fmt(form.book_cents)} | {fmt(form.tax_cents)} | "
        f"{_signed(form.book_cents - form.tax_cents)} |"
    )
    for r in rows:
        out.append(
            f"| {r.year} | {fmt(r.book_close)} | {fmt(r.tax_close)} | "
            f"{_signed(r.book_close - r.tax_close)} |"
        )
    out.append("")
    out.append(
        "_The disparity opens at the §704(c) built-in gain/(loss) the partner "
        "contributed and narrows over time as the traditional method shifts tax "
        "items between partners. Where the **ceiling rule** binds (see the "
        "partnership summary), the disparity may **not** close fully even after "
        "the property is sold — that residual is the traditional-method distortion "
        "the model surfaces rather than cures._"
    )
    out.append("")
    return "\n".join(out)


def partnership_summary(
    partnership: Partnership,
    results: List[YearResult],
    formation: Dict[str, "object"],
) -> str:
    """Render the partnership 1065 summary (Markdown).

    Includes a tax-basis balance sheet (assets = liabilities + tax capital), a
    book-vs-tax capital reconciliation, and the §704(c) layer roll-forward per
    contributed property (with ceiling-rule notes).
    """
    partners = partnership.ordered_partners()
    final = results[-1]
    final_by_partner = {pr.partner: pr for pr in final.partners}

    out: List[str] = []
    out.append(f"# Form 1065 Summary — {partnership.name} [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Invented partnership and amounts for demonstration. Implements the "
        "public US partnership-tax framework (Form 1065, IRC §704(b)/§704(c), "
        "traditional method with the ceiling rule) generically; not real "
        "methodology or figures."
    )
    out.append("")
    out.append(
        "> **Method limitation (by design):** only the §704(c) *traditional method* "
        "is modelled. The *remedial* and *curative* methods of Reg. §1.704-3 are "
        "**not** implemented; where the ceiling rule binds, the resulting distortion "
        "is **surfaced**, not cured."
    )
    out.append("")

    # --- Contributed property at formation --------------------------------
    out.append("## Contributed property at formation")
    out.append("")
    out.append(
        "| Property | Contributor | §704(b) book (FMV) | Tax basis | "
        "Built-in gain/(loss) |"
    )
    out.append("|----------|-------------|-------------------:|----------:|---------------------:|")
    for prop in partnership.ordered_properties():
        contributor = partnership.partners[prop.contributor].name
        out.append(
            f"| {prop.name} | {contributor} | {fmt(prop.fmv_cents)} | "
            f"{fmt(prop.tax_basis_cents)} | {_signed(prop.built_in_gain_cents)} |"
        )
    out.append("")

    # --- §704(c) layer roll-forward per property --------------------------
    out.append("## §704(c) built-in gain/(loss) layer roll-forward")
    out.append("")
    out.append(
        "| Property | FY | Book dep | Tax dep | Book gain | Tax gain | "
        "Layer (open → close) | Ceiling? |"
    )
    out.append("|----------|----|---------:|--------:|----------:|---------:|:--------------------|:--------:|")
    for prop in partnership.ordered_properties():
        if not prop.depreciable:
            continue
        for r in _gather_property_rows(results, prop.code):
            ceiling = (
                f"⚑ short {fmt(r.ceiling_shortfall)}" if r.ceiling_binding else "—"
            )
            layer = f"{fmt(r.layer_open)} → {fmt(r.layer_close)}"
            out.append(
                f"| {prop.code} | {r.year} | {fmt(r.book_depreciation)} | "
                f"{fmt(r.tax_depreciation)} | {_signed(r.book_gain)} | "
                f"{_signed(r.tax_gain)} | {layer} | {ceiling} |"
            )
    out.append("")
    out.append(
        "_⚑ = the ceiling rule was binding: actual tax depreciation was less than "
        "the non-contributing partners' share of book depreciation, so they were "
        "capped at the available tax item and the contributing partner received "
        "none. Under the traditional method this distortion is left in place._"
    )
    out.append("")

    # --- Book vs. tax capital reconciliation ------------------------------
    out.append("## Book vs. tax capital reconciliation (ending)")
    out.append("")
    out.append("| Partner | §704(b) book capital | Tax capital | Book − Tax |")
    out.append("|---------|---------------------:|------------:|-----------:|")
    tot_book = tot_tax = 0
    for partner in partners:
        pr = final_by_partner[partner.code]
        tot_book += pr.book_close
        tot_tax += pr.tax_close
        out.append(
            f"| {partner.name} | {fmt(pr.book_close)} | {fmt(pr.tax_close)} | "
            f"{_signed(pr.book_close - pr.tax_close)} |"
        )
    out.append(
        f"| **Total** | **{fmt(tot_book)}** | **{fmt(tot_tax)}** | "
        f"**{_signed(tot_book - tot_tax)}** |"
    )
    out.append("")

    # --- Tax-basis balance sheet ------------------------------------------
    # Assets = cash + adjusted tax basis of remaining property. Liabilities are
    # zero in this fictional model, so assets must equal total tax capital. Cash
    # is the contributed cash plus operating income and sale proceeds, less
    # distributions paid out over the life of the partnership.
    cash = _final_cash(partnership, results)
    eng_state = _final_property_tax_basis(partnership, results)
    property_basis = sum(eng_state.values())
    total_assets = cash + property_basis

    out.append("## Tax-basis balance sheet (ending)")
    out.append("")
    out.append("| Assets | Amount | | Liabilities & capital | Amount |")
    out.append("|--------|-------:|---|----------------------|-------:|")
    out.append(
        f"| Cash | {fmt(cash)} | | Liabilities | {fmt(0)} |"
    )
    out.append(
        f"| Property (adj. tax basis) | {fmt(property_basis)} | | "
        f"Tax capital | {fmt(tot_tax)} |"
    )
    out.append(
        f"| **Total assets** | **{fmt(total_assets)}** | | "
        f"**Total liab. & capital** | **{fmt(tot_tax)}** |"
    )
    out.append("")
    balanced = "balances ✓" if total_assets == tot_tax else "OUT OF BALANCE ✗"
    out.append(
        f"_Tax-basis balance sheet {balanced}: assets ({fmt(total_assets)}) = "
        f"liabilities (0) + tax capital ({fmt(tot_tax)})._"
    )
    out.append("")
    return "\n".join(out)


def _final_property_tax_basis(
    partnership: Partnership, results: List[YearResult]
) -> Dict[str, int]:
    """Reconstruct ending adjusted tax basis per depreciable property.

    Starts from the carryover tax basis and subtracts each year's tax
    depreciation; a sold property ends at zero basis.
    """
    basis: Dict[str, int] = {}
    sold: Dict[str, bool] = {}
    for prop in partnership.properties.values():
        if prop.depreciable:
            basis[prop.code] = prop.tax_basis_cents
            sold[prop.code] = False
    for yr in results:
        for pr in yr.properties:
            if pr.property not in basis:
                continue
            if pr.sold:
                basis[pr.property] = 0
                sold[pr.property] = True
            elif not sold[pr.property]:
                basis[pr.property] -= pr.tax_depreciation
    return basis


def _final_cash(partnership: Partnership, results: List[YearResult]) -> int:
    """Reconstruct the partnership's ending cash on a tax basis.

    Cash = contributed cash + cumulative ordinary operating income + sale
    proceeds − cumulative cash distributions. Depreciation is a non-cash
    deduction and does not affect cash (it reduces tax capital and property
    basis in lockstep, keeping the balance sheet in balance).
    """
    cash = sum(
        p.tax_basis_cents
        for p in partnership.properties.values()
        if not p.depreciable
    )
    for yr in results:
        py = partnership.partnership_year(yr.year)
        cash += py.ordinary_income_cents
        cash -= py.cash_distribution_cents
        for pr in yr.properties:
            if pr.sold:
                # Sale converts property into cash: the gross proceeds land in
                # cash, while the property's tax basis leaves the asset side.
                cash += _sale_proceeds(partnership, pr)
    return cash


def _sale_proceeds(partnership: Partnership, pr: PropertyYearResult) -> int:
    """Gross sale proceeds for a sold property (from the configured facts)."""
    fact = partnership.property_year(pr.property, pr.year)
    return fact.sale_price_cents


def build_reports(partnership: Partnership) -> Dict[str, str]:
    """Run the engine and render every Markdown artifact, keyed by filename."""
    eng = PartnershipEngine(partnership)
    formation = eng.formation_capital()
    results = eng.run()
    artifacts: Dict[str, str] = {}
    for code in partnership.partners:
        artifacts[f"k1_{code}.md"] = partner_k1(
            partnership, results, formation, code
        )
    artifacts["partnership_1065_summary.md"] = partnership_summary(
        partnership, results, formation
    )
    return artifacts
