# Sample — Surplus Pool Calculation (FICTIONAL)

> 🔒 Invented entity, ownership, and amounts for demonstration. Illustrates *structure and
> data lineage only* — not real methodology detail or real figures. All USD.

**Entity:** Demo Affiliate LLC (a fictional US operating affiliate) · **Owner:** Demo Fund (100%)

## Layer 1 — Evidence tab (cited, hardcoded inputs)
| Input | Value | Source (fictional) |
|-------|-------|--------------------|
| Standalone taxable income, FY2024 | 500,000 | Demo 1065, p.1 ln 22 |
| Reg. 5907(2) net adjustment | (50,000) | Demo book-tax workpaper |
| Opening exempt surplus | 1,000,000 | Prior-year signed workpaper |
| Distribution paid in FY2024 | (200,000) | Demo cash ledger |

## Layer 2 — Surplus-Details (formulas pull from Evidence)
| Line | Formula logic | FY2024 |
|------|---------------|--------|
| Taxable income (standalone) | ← Evidence | 500,000 |
| Reg. 5907(2) adjustment | ← Evidence | (50,000) |
| **Surplus after adjustment** | sum above | **450,000** |
| Allocable @ ownership % | × 100% | 450,000 |
| Opening exempt surplus | ← Evidence | 1,000,000 |
| Distribution (exempt first) | ← Evidence | (200,000) |
| **Closing exempt surplus** | opening + current − distribution | **1,250,000** |

## Layer 3 — Summary (formulas pull from Surplus-Details + FX tab)
| Output | Logic | USD | CAD @ 1.35 |
|--------|-------|-----|------------|
| Closing exempt surplus | ← Surplus-Details | 1,250,000 | 1,687,500 |

---
**Lineage rule shown here:** `Evidence (cited input) → Surplus-Details (formulas) → Summary
(formulas + FX)`. Income never hardcoded on Surplus-Details; FX never hardcoded on Summary;
every figure traces to a source. *(ACB column omitted — in the real engine it moves only on
capital events, never on operating income.)*
