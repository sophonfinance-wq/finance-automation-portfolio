# §704(c) Built-In Gain Summary — Harborview Partners LP [FICTIONAL]

> Invented partnership and amounts for demonstration. Implements the public US partnership-tax framework (Form 1065, IRC §704(b)/§704(c), traditional method with the ceiling rule) generically; not real methodology or figures.

> **Method limitation (by design):** only the §704(c) *traditional method* is modelled. The *remedial* and *curative* methods of Reg. §1.704-3 are **not** implemented; where the ceiling rule binds, the resulting distortion is **surfaced**, not cured.

## Contributed property at formation

| Property | Contributor | §704(b) book (FMV) | Tax basis | Built-in gain/(loss) |
|----------|-------------|-------------------:|----------:|---------------------:|
| Beacon cash contribution | Beacon Equity LLC | 1,200,000.00 | 1,200,000.00 | 0.00 |
| Harborview mixed-use building | Atlas Capital LLC | 1,200,000.00 | 300,000.00 | 900,000.00 |

## §704(c) built-in gain/(loss) layer roll-forward

| Property | FY | Book dep | Tax dep | Book gain | Tax gain | Layer (open -> close) | Ceiling? |
|----------|----|---------:|--------:|----------:|---------:|:--------------------|:--------:|
| HARBOR_BLDG | 1 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 900,000.00 -> 750,000.00 | BINDING short 50,000.00 |
| HARBOR_BLDG | 2 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 750,000.00 -> 600,000.00 | BINDING short 50,000.00 |
| HARBOR_BLDG | 3 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 600,000.00 -> 450,000.00 | BINDING short 50,000.00 |
| HARBOR_BLDG | 4 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 450,000.00 -> 300,000.00 | BINDING short 50,000.00 |
| HARBOR_BLDG | 5 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 300,000.00 -> 150,000.00 | BINDING short 50,000.00 |
| HARBOR_BLDG | 6 | 0.00 | 0.00 | 500,000.00 | 650,000.00 | 150,000.00 -> 0.00 | - |

_**BINDING** = the ceiling rule was binding: actual tax depreciation was less than the non-contributing partners' share of book depreciation, so they were capped at the available tax item and the contributing partner received none. Under the traditional method this distortion is left in place; the residual built-in gain is caught up to the contributor on sale._

## Book vs. tax capital reconciliation (ending)

| Partner | §704(b) book capital | Tax capital | Book - Tax |
|---------|---------------------:|------------:|-----------:|
| Atlas Capital LLC | 1,130,000.00 | 880,000.00 | 250,000.00 |
| Beacon Equity LLC | 1,130,000.00 | 1,380,000.00 | (250,000.00) |
| **Total** | **2,260,000.00** | **2,260,000.00** | **0.00** |

## Tax-basis balance sheet (ending)

| Assets | Amount | | Liabilities & capital | Amount |
|--------|-------:|---|----------------------|-------:|
| Cash | 2,260,000.00 | | Liabilities | 0.00 |
| Property (adj. tax basis) | 0.00 | | Tax capital | 2,260,000.00 |
| **Total assets** | **2,260,000.00** | | **Total liab. & capital** | **2,260,000.00** |

_Tax-basis balance sheet balances: assets (2,260,000.00) = liabilities (0) + tax capital (2,260,000.00)._
