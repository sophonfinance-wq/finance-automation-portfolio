# 🤝 Partnership-Tax §704(c) Engine

> How I model **US partnership tax (Form 1065)** with **IRC §704(c) built-in gain/loss
> tracking** — the **traditional method** with the **ceiling rule** — as a traceable,
> testable calculation engine over **fully fictional** data.

> 🔒 This page describes my **approach and capabilities** and references only **public tax
> law** (IRC §704(b)/§704(c), Reg. §1.704-3, Form 1065 / Schedule K-1). It does not reproduce
> any employer's or client's specific methodology, entities, structures, or figures.

---

## The problem I solve

When a partner contributes **appreciated (or depreciated) property** instead of cash, the
partnership has to keep **two capital accounts** for every partner — a **§704(b) book** account
(credited at fair market value) and a **tax** account (credited at carryover tax basis). The
gap between them is the **built-in gain/(loss) (BIG/BIL)**. IRC **§704(c)** then dictates how
the partnership's *tax* items (depreciation, gain on sale) are allocated so that built-in gain
is ultimately borne by the partner who contributed it — not silently shifted to the others.

Doing this by hand across years, properties, and a moving **ceiling rule** is error-prone. This
engine does it deterministically and ties out to the penny.

## My approach

- **Two parallel capital accounts, integer-cent exact.** Every figure is stored as integer
  cents and allocated with a largest-remainder (Hamilton) method, so book and tax capital
  always sum exactly to partnership equity.
- **Traditional method, faithfully.** Book items are allocated by interest %; **tax**
  depreciation is allocated to the **non-contributing** partners first (up to their book share)
  to *cure* the disparity, with the contributing partner taking the remainder.
- **The ceiling rule is surfaced, not hidden.** When actual tax depreciation is *less* than the
  non-contributors' book share, they are capped at what actually exists — a real distortion. The
  engine flags it (`ceiling_binding` + a shortfall amount) and notes it in every report.
- **§704(c) layer roll-forward.** The remaining built-in gain/(loss) starts at `FMV − basis`,
  amortises toward zero as the book/tax depreciation difference cures it, never flips sign, and
  is caught up to the contributor on sale.
- **Schedule K-1-style output, both bases.** Per-partner capital analyses on book *and* tax
  bases, plus a tax-basis balance sheet that balances (assets = liabilities + tax capital).

## What this demonstrates

- **Partnership-tax depth:** book vs. tax capital, §704(b)/§704(c), the traditional method, the
  ceiling rule, and the on-sale catch-up — the things a partnership-tax preparer actually wrestles
  with.
- **Engineering discipline:** deterministic integer-cent math, a clean model/engine/report/CLI
  split, and a rigorous test suite that pins the load-bearing rules.
- **Honest scope:** I implement only the traditional method and **document the limitation
  explicitly** — where the ceiling rule bites, the distortion is shown rather than papered over.

## Tools

`Python (stdlib)` · `openpyxl` (available; not required here) · `pytest` · `Claude Code` ·
`ChatGPT` · `Codex`

## Sample (fictional)

- [§704(c) traditional-method allocation](./samples/sample-704c-allocation.md) — a short worked
  example showing the book → tax → §704(c) allocation lineage, including a ceiling-rule case, with
  fully invented numbers.

---

## ▶️ Run it

This repo ships a **genuinely working** reference implementation over **fully fictional data**:
*Harborview Partners LP*, a 50/50 partnership where **Atlas Capital LLC** contributes an
appreciated, already-partly-depreciated building (FMV 1,200,000; tax basis 300,000 → **900,000
built-in gain**) and **Beacon Equity LLC** contributes 1,200,000 of cash. The building's long
book life vs. short remaining tax life forces the **ceiling rule** to bind for five years; the
building is then sold, catching the residual built-in gain up to Atlas for tax.

**Requirements:** Python 3 (3.14 OK) and `pytest` for the test suite. No pandas/numpy/faker —
stdlib only, with fixed figures for determinism.

```bash
# from this folder:
python -m pip install --quiet pytest        # one-time, for the test suite

# build the partnership, roll it forward, and write the K-1s + 1065 summary:
python -m partnership_engine --out out
#   (equivalently: python run.py --out out)

# bare run — just print the 1065 summary to the console:
python -m partnership_engine

# run the test suite:
python -m pytest -q
```

> 💡 On Windows, if your console can't render the 🔒 / § / ⚑ characters, set
> `PYTHONIOENCODING=utf-8` (the CLI also degrades gracefully and will not crash on a legacy code
> page — the written `.md` files are always UTF-8).

### What it produces

- `out/k1_<PARTNER>.md` — per-partner Schedule K-1-style capital analysis on **both** a §704(b)
  book basis and a tax basis, with the §704(c) book−tax disparity tracked year by year.
- `out/partnership_1065_summary.md` — tax-basis balance sheet (assets = liabilities + tax
  capital), book-vs-tax capital reconciliation, and the §704(c) layer roll-forward per property.

### Example output (real, generated by the command above)

§704(c) built-in-gain layer roll-forward — note the binding **ceiling rule** ⚑ in years 1–5 and
the catch-up on sale in year 6:

| Property | FY | Book dep | Tax dep | Book gain | Tax gain | Layer (open → close) | Ceiling? |
|----------|----|---------:|--------:|----------:|---------:|:--------------------|:--------:|
| HARBOR_BLDG | 1 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 900,000.00 → 750,000.00 | ⚑ short 50,000.00 |
| HARBOR_BLDG | 2 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 750,000.00 → 600,000.00 | ⚑ short 50,000.00 |
| HARBOR_BLDG | 5 | 200,000.00 | 50,000.00 | 0.00 | 0.00 | 300,000.00 → 150,000.00 | ⚑ short 50,000.00 |
| HARBOR_BLDG | 6 | 0.00 | 0.00 | 500,000.00 | 650,000.00 | 150,000.00 → 0.00 | — |

On sale, the tax gain (650,000) splits **400,000 to Atlas / 250,000 to Beacon** — the remaining
150,000 layer goes entirely to Atlas (the contributor) plus its 50% of the residual.

Tax-basis balance sheet (ending) — it balances:

| Assets | Amount | | Liabilities & capital | Amount |
|--------|-------:|---|----------------------|-------:|
| Cash | 2,260,000.00 | | Liabilities | 0.00 |
| Property (adj. tax basis) | 0.00 | | Tax capital | 2,260,000.00 |
| **Total assets** | **2,260,000.00** | | **Total liab. & capital** | **2,260,000.00** |

> The Atlas K-1 shows the §704(c) discipline directly: the book−tax disparity opens at the
> **900,000** built-in gain and narrows each year. Because the ceiling rule bound, it does **not**
> fully close even after sale — a **250,000** residual distortion the model surfaces rather than
> cures.

### Test output (real)

```text
$ python -m pytest -q
....................................                                      [100%]
36 passed
```

The suite asserts the load-bearing rules: **BIG = FMV − tax basis** at formation; **book/tax
capital each sum to partnership equity**; **tax depreciation cures the non-contributor first**;
a constructed **ceiling-rule** case where the non-contributor is capped at the actual tax item;
the **§704(c) layer decreases and never goes negative**; **on sale the remaining built-in gain is
taxed to the contributor**; the **K-1 roll-forward identity** (begin + contrib + income − distrib
= end) on **both** book and tax bases; the **tax-basis balance sheet balances**; **determinism**
(same seed → identical output); and **ownership-% allocation** of book items.

### Layout

```text
partnership-tax-engine/
├── partnership_engine/
│   ├── __init__.py      # package + confidentiality posture
│   ├── money.py         # integer-cent money + Hamilton allocation
│   ├── model.py         # Partner / ContributedProperty / Partnership / capital accounts
│   ├── engine.py        # the engine: §704(c) traditional method, ceiling rule, roll-forward
│   ├── generate.py      # deterministic fictional partnership (Harborview LP)
│   ├── report.py        # K-1 capital analyses + 1065 summary (Markdown)
│   ├── cli.py           # argparse CLI
│   ├── __main__.py      # python -m partnership_engine
│   └── tests/           # pytest suite (36 tests)
├── run.py               # convenience entrypoint
├── pytest.ini
├── out/                 # generated K-1s + 1065 summary
└── samples/             # fictional worked example
```

> ⚠️ **Method limitation (by design):** only the §704(c) **traditional method** is implemented.
> The **remedial** and **curative** methods of Reg. §1.704-3 are **not** modelled; where the
> ceiling rule binds, the distortion is **surfaced**, not cured.

> 🔒 Everything above — the partnership, partners, figures, and paths — is **invented for this
> portfolio demo**. It implements only published US tax rules generically and reproduces no real
> entity, person, methodology, or data.
