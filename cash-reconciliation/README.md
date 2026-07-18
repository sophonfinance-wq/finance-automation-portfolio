# 🔁 Cash & Debt Reconciliation

<p align="center"><img src="../assets/systems/recon.gif" alt="Cash & Debt Reconciliation Engine — live demo" width="100%"></p>
<p align="center"><img src="../assets/flows/recon-flow.svg" alt="Cash and Debt Reconciliation flow chart" width="100%"></p>

> An **AI-assisted, materiality-based reconciliation system** with a structured,
> audit-ready evidence log — so cash and debt tie to the ledger the same way every month, with
> a clean trail.

> 🔒 This page describes the platform's **approach and capabilities** and ships a **runnable, fully
> synthetic** demo. It does not reproduce any employer's specific reconciliation procedures,
> banks, entities, or figures. All names and numbers below are invented.

---

## The problem it solves
Reconciling cash and debt means tying every bank and lender movement to the general ledger,
explaining the differences, and keeping audit-ready evidence — across many entities. Performed by
hand, the work is repetitive, slow, and the evidence trail is inconsistent.

## Approach
- **Scope discipline.** Reconcile what matters (cash, debt); explicitly exclude what is out of
  scope; skip dormant rows with a documented rule rather than chasing zeros.
- **Source-to-target mapping.** A mapping reference that resolves the recurring mismatch between
  ledger tab names and bank-file names, and targets values **by account number, not row
  number**, to eliminate off-by-one errors.
- **Materiality and flagging.** Differences within a set threshold are treated as noise (commented);
  anything over becomes a **numbered flag** escalated for review.
- **A structured evidence log.** A multi-sheet workbook (summary, cash, debt, flagged items,
  notes) where every value carries a standardized comment citing its source, the balance
  found, the variance, and a status.
- **Clean close-out reporting.** Color-coded status and a closing summary that separates
  *timing* items (expected, will clear) from *structural* items (cleanups that warrant attention).

## What this demonstrates
- Automates reconciliation of **many trial-balance tabs** on a repeatable cadence.
- Builds **materiality and escalation** into the process so reviewers see signal, not noise.
- Produces a **consistent, audit-ready evidence trail** every cycle.

📄 **Deep dive:** [Verification &amp; Completeness Patterns](verification-patterns.md) — the layered checks (account-number targeting, entity-mapping cross-checks, independent re-derivation, and a full-population completeness sweep) plus the finding taxonomy that separates timing noise from structural signal.

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

## 🔁 Reconciliation Assurance Loop (`loop.py`)

The engine answers *"what doesn't tie?"* — one pass. The **assurance loop** answers the next
question: *"the stored package has drifted from source — restore it, show every correction, and
apply a materiality gate before it ships."*

**observe → detect → remediate → re-verify → gate → repeat**

The seeded generator is the system of record. Each turn the loop reconciles the current package,
compares every account's outcome against the **baseline** (the reconciliation of the pristine
seeded dataset), takes the lowest-numbered deviating account, and resyncs every record it owns —
GL row, bank statement, lender statement, dormant marker — booking each field change as a
correction. It repeats until nothing deviates from source.

Two properties keep it honest:

- **Fidelity, not zeroing.** The scenario's *genuine* reconciling items (the deposit in transit,
  the keying error) are part of the baseline and survive the loop untouched — the loop restores
  agreement with source, it does not paper over real flags.
- **Materiality gate.** `PASS` (corrections immaterial, exit 0) · `FLAG` (converged but material —
  reviewer sees what moved, exit 0) · `FAIL` (did not converge, exit 1).

```bash
# inject the drift profile (fat-fingered GL, missing lender statement,
# active account mis-marked dormant) and watch the loop restore the package:
python -m recon_engine.loop --demo
```
```text
Verdict: ⚑ FLAG — converged, material corrections booked
Turn 1  resync CASH-1002   gl_balance 212,292.45 -> 207,462.20
Turn 2  resync DEBT-2000   lender statement restored
Turn 3  resync DEBT-2001   dormant True -> False   (back in scope)
```

## 🏦 Cash-manager controls (validation only)

Five read-only validators model the monthly cash-manager control set on seeded,
fictional data — integer cents, deterministic, never posting:

| Module | Control |
|---|---|
| `recon_engine.bank_rec` | Bank→GL bridge: bank ending + deposits in transit − outstanding checks ± approved error plugs must equal the adjusted book balance. |
| `recon_engine.outstanding_checks` | Outstanding/void/zero check register: aging vs a stale-date policy, void-amount rules, and an independently re-added outstanding total. |
| `recon_engine.wire_approval` | Wire dual-approval: no approved or scheduled wire without two distinct approvers, both different from the initiator (segregation of duties). |
| `recon_engine.bank_register` | Register continuity: every running balance re-derived row by row; closing foots; opening ties to prior close; optional bank tie-out. |
| `recon_engine.cash_concentration` | Concentration sweep: sub-account sweeps re-added to the concentration inflow; roll-forward re-derived. |

Each validator ends at READY FOR HUMAN REVIEW — mechanical cleanliness is a
precondition for review, never a sign-off. A curated invariant grid exercises
all five end-to-end (clean ties + one-cent tampers) across 5,000 parameter points.

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
