# Partnership 1065 Automation

<p align="center"><img src="../assets/systems/partnership-tax.gif" alt="Partnership 1065 Automation live demo" width="100%"></p>
<p align="center"><img src="../assets/flows/partnership-tax-flow.svg" alt="Partnership 1065 Automation flow chart" width="100%"></p>

An AI-driven partnership tax engine that prepares Form 1065 support on fully fictional, seeded data.
The workflow starts with source workpapers and a prior-return line map, builds a book-to-tax bridge,
allocates Schedule K items to partners, and produces a review-ready Form 1065 support package with
deterministic tie-out checks before anything is marked ready.

The public demo is sanitized. It does not include any real taxpayer, partner, EIN, client amount,
file path, or engagement workpaper.

## What It Automates

| Stage | What the system does |
|---|---|
| Source intake | Reads the fictional trial balance, P&L, balance sheet, member capital, syndication cost support, and return line targets |
| Workpaper build | Reconstructs book income, book-tax adjustments, taxable ordinary income, Schedule L, M-1, and M-2 support |
| 1065 mapping | Maps the prepared workpapers to Form 1065, Schedule K, Schedule L, Schedule M-1, Schedule M-2, and K-1 preview lines |
| Partner allocation | Allocates ordinary income and capital activity with exact penny control |
| Review package | Produces Markdown, JSON, optional Excel support, and deterministic checks before marking the package ready |

## Run It

```bash
python -m partnership_tax
python run.py --no-xlsx
python -m pytest -q
```

The module ships with 1,605 curated tests (`python -m pytest -q`).

## Outputs

| Output | Purpose |
|---|---|
| `output/tax_workpapers.md` | Review-ready 1065 workpaper bridge and source index |
| `output/review_checks.md` | Tie-out checks for return lines, K-1 allocations, Schedule L, M-1, and M-2 |
| `output/form_1065_preview.json` | Machine-readable 1065/K-1 preview for downstream packaging |
| `output/1065_supporting_package.xlsx` | Optional Excel support workbook generated locally and ignored by Git |

## IRC §704(c) Built-In Gain Module

The engine also includes a self-contained **IRC §704(c)** built-in-gain (BIG) capability layered on
top of the same integer-cent money helpers, so it ties out to the penny. It tracks two parallel
capital accounts for every partner — **§704(b) book** (credited at fair market value) and **tax**
(credited at carryover tax basis) — and allocates the partnership's tax items under the **traditional
method**:

- **Built-in gain** is `FMV − tax basis` at formation; the per-partner book-minus-tax disparity opens
  at exactly that amount.
- **Traditional method.** Book depreciation is shared by interest %; tax depreciation goes **first to
  the non-contributing partner** to cure the disparity, with any excess to the contributor.
- **Ceiling rule, surfaced not hidden.** When actual tax depreciation is less than the
  non-contributor's book share, they are capped at the available tax item, the contributor gets none,
  and the year is **flagged `BINDING`** with the uncured shortfall — the traditional-method distortion
  is shown, not silently cured.
- **On sale**, the remaining §704(c) layer is caught up to the contributing partner; the layer never
  flips sign and is cleared to zero.
- Outputs a per-partner Schedule **K-1 capital analysis on both book and tax bases** and a summary with
  the layer roll-forward and a tax-basis balance sheet that balances.

Run the §704(c) demo (the default `python -m partnership_tax` behaviour is unchanged):

```bash
python -m partnership_tax --section704c
```

Worked example — **Harborview Partners LP** (fictional): Atlas Capital LLC contributes appreciated
property (FMV $1,200,000 / tax basis $300,000 → **$900,000 built-in gain**); Beacon Equity LLC
contributes $1,200,000 cash. Book depreciation ($200,000/yr) far exceeds tax depreciation
($50,000/yr), so the ceiling rule binds every year until the building is sold:

| Property | FY | Book dep | Tax dep | Layer (open → close) | Ceiling? |
|----------|----|---------:|--------:|:---------------------|:---------|
| HARBOR_BLDG | 1 | 200,000.00 | 50,000.00 | 900,000.00 → 750,000.00 | BINDING short 50,000.00 |
| HARBOR_BLDG | 5 | 200,000.00 | 50,000.00 | 300,000.00 → 150,000.00 | BINDING short 50,000.00 |
| HARBOR_BLDG | 6 (sale) | 0.00 | 0.00 | 150,000.00 → 0.00 | — |

On sale the residual $150,000 built-in gain is caught up to Atlas, and the tax-basis balance sheet
ties: assets $2,260,000 = liabilities $0 + tax capital $2,260,000.

| Output | Purpose |
|---|---|
| `output/section704c_summary.md` | Book-vs-tax capital reconciliation + §704(c) layer roll-forward with the ceiling rule flagged |
| `output/section704c_k1_<PARTNER>.md` | Per-partner Schedule K-1 capital analysis on both §704(b) book and tax bases |

## How It Operates

The operator provides a source bundle. The system then:

1. builds the tax workpapers,
2. maps the numbers to the return,
3. checks the package, and
4. drafts the supporting summary for reviewer or executive follow-up.

In approved, agent-enabled environments, an optional orchestration layer can coordinate the whole
sequence — source bundle, workpaper build, review checks, and status reporting — as an unattended
workflow. The platform runs fully without it: in a conservative environment, the same package runs
through Python and CI with no orchestration layer.

## Controls

- fictional seeded data only
- exact-cent allocation logic
- source IDs on every mapped return line
- Schedule K to Form 1065 tie-out
- K-1 allocations sum to Schedule K
- Schedule L balance check
- Schedule M-1 and M-2 reconciliation checks
- human review remains the final sign-off
