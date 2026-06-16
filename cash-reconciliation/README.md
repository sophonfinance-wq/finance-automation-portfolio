# 🔁 Cash & Debt Reconciliation

<p align="center"><img src="../assets/systems/recon.gif" alt="Cash & Debt Reconciliation Engine — live demo" width="100%"></p>
<p align="center"><img src="../assets/flows/recon-flow.svg" alt="Cash and Debt Reconciliation flow chart" width="100%"></p>

> How I build an **AI-assisted, materiality-based reconciliation system** with a structured,
> audit-ready evidence log — so cash and debt tie to the ledger the same way every month, with
> a clean trail.

> 🔒 This page describes my **approach and capabilities** and ships a **runnable, fully
> synthetic** demo. It does not reproduce any employer's specific reconciliation procedures,
> banks, entities, or figures. All names and numbers below are invented.

---

## The problem I solve
Reconciling cash and debt means tying every bank and lender movement to the general ledger,
explaining the differences, and keeping audit-ready evidence — across many entities. Done by
hand it's repetitive, slow, and the evidence trail comes out inconsistent.

## My approach
- **Scope discipline.** Reconcile what matters (cash, debt); explicitly exclude what's out of
  scope; skip dormant rows with a documented rule rather than chasing zeros.
- **Source-to-target mapping.** A cheat sheet that resolves the perennial mismatch between
  ledger tab names and bank-file names, and targets values **by account number, not row
  number**, to defeat off-by-one errors.
- **Materiality + flagging.** Differences within a set threshold are noise (commented);
  anything over becomes a **numbered flag** escalated for review.
- **A structured evidence log.** A multi-sheet workbook (summary, cash, debt, flagged items,
  notes) where every value carries a standardized comment citing its source, the balance
  found, the variance, and a status.
- **Clean close-out reporting.** Color-coded status and a wrap summary that separates
  *timing* items (expected, will clear) from *structural* items (cleanups worth attention).

## What this demonstrates
- I can automate reconciliation of **many trial-balance tabs** on a repeatable cadence.
- I build **materiality and escalation** into the process so reviewers see signal, not noise.
- I produce a **consistent, audit-ready evidence trail** every cycle.

---

## ▶️ Run it

Requirements: **Python 3.12+**, `openpyxl` (already standard here), and `pytest` for the tests.
No pandas / numpy / faker — only the standard library plus `openpyxl`.

```bash
# from this folder (cash-reconciliation/)

# 1) Run the engine: generates synthetic data, reconciles, writes both logs
python -m recon_engine
#    └─ equivalently: python run.py

# 2) Run the tests
python -m pip install --quiet pytest      # one-time
python -m pytest -q
```

**Useful flags**

```bash
python -m recon_engine --threshold 25     # tighten materiality to $25
python -m recon_engine --seed 7           # regenerate with a different seed
python -m recon_engine --no-xlsx          # Markdown only, skip the workbook
```

**Outputs**
- `evidence-log.md` — the committed 5-section Markdown evidence log (see below).
- `output/evidence-log.xlsx` — a color-coded 5-sheet workbook (gitignored).

### How it works
- **`recon_engine/generate.py`** — seeded synthetic generator for 4 fictional entities. It
  builds GL cash & debt balances, bank statements, and lender statements, then **injects four
  known discrepancies**: a deposit-in-transit, a sub-threshold timing difference, an outright
  keying error, plus a populated *late-paydown* leg (to exercise the optional 3rd term) and a
  dormant zero-activity account.
- **`recon_engine/engine.py`** — reconciles **by account number**. Cash rec = GL vs. bank
  ending. Debt rec = GL vs. the lender **3-part total** =
  `principal + current interest/reserve + late paydown`. It computes the variance, applies the
  materiality threshold, and classifies each line **clean / timing / FLAG**, skipping dormant
  rows with a note.
- **`recon_engine/report.py`** — renders the 5-section evidence log to Markdown and to `.xlsx`.
- **`recon_engine/cli.py`** — the CLI entry point.

### Real example output

Running `python -m recon_engine` produces:

```
Cash & Debt Reconciliation Engine
  Period            : March 2026 (2026-03-31)
  Seed              : 20260331
  Materiality       : $50.00
  Accounts in scope : 9
    cash=4 debt=4 skipped=1
  Clean             : 5
  Timing/immaterial : 1
  Flagged           : 2
  Markdown log      : ...\cash-reconciliation\evidence-log.md
  XLSX log          : ...\cash-reconciliation\output\evidence-log.xlsx

Flagged for review:
  FLAG-001  CASH-1001  Maple Fund LP  variance=-1,875.40
  FLAG-002  DEBT-2003  Cedar Ridge Partners LLC  variance=12,500.00
```

The generated debt section shows the 3-part formula tying out, the sub-$50 timing item, and
the flagged keying error (fictional figures):

| Entity | Account | GL loan | Principal | Interest/Reserve | Late paydown | Lender total | Variance | Result |
|--------|---------|--------:|----------:|-----------------:|-------------:|-------------:|---------:|--------|
| Birchwood Op Co | DEBT-2002 | 3,386,059.19 | 3,380,732.17 | 5,308.27 | 0.00 | 3,386,040.44 | 18.75 | 🟡 Timing |
| Cedar Ridge Partners LLC | DEBT-2003 | 2,432,184.77 | 2,414,349.91 | 5,334.86 | 0.00 | 2,419,684.77 | 12,500.00 | 🔴 FLAG-002 |
| Demo Holdings LLC | DEBT-2000 | 2,846,629.29 | 2,829,837.76 | 9,291.53 | 7,500.00 | 2,846,629.29 | 0.00 | ✅ Clean |
| Maple Fund LP | DEBT-2001 | 2,936,205.07 | 2,926,267.92 | 9,937.15 | 0.00 | 2,936,205.07 | 0.00 | ✅ Clean |

The full committed log lives in [`evidence-log.md`](./evidence-log.md).

---

## Tools
`Excel / openpyxl` · `Python 3` · `Bank registers / lender statements` · `Claude Code / Cowork`

## Layout
```
cash-reconciliation/
├─ recon_engine/
│  ├─ __init__.py        # version + default materiality threshold
│  ├─ generate.py        # seeded synthetic GL / bank / lender data + injected discrepancies
│  ├─ engine.py          # variance, materiality, classification, 3-part debt formula
│  ├─ report.py          # 5-section Markdown + xlsx renderers
│  ├─ cli.py             # CLI entry point
│  ├─ __main__.py        # enables `python -m recon_engine`
│  └─ tests/             # pytest: variance, thresholds, 3-part formula, injected items
├─ run.py                # `python run.py` convenience entry point
├─ evidence-log.md       # committed 5-section evidence log (regenerated by a run)
├─ output/               # .xlsx workbook (gitignored)
├─ samples/              # hand-written fictional sample log (narrative)
└─ pyproject.toml
```

## Sample (fictional)
- [Reconciliation evidence log](./samples/sample-evidence-log.md) — a hand-written 5-section
  log with a flagged material variance, using invented banks and balances.
- [Generated evidence log](./evidence-log.md) — the live output of the engine above.

*Real evidence logs — which embed live bank screenshots — are never published.*
