---
name: recon
description: "Run the Cash & Debt Reconciliation engine or its materiality-gated assurance loop. Use when asked to reconcile, demo GL-to-bank/lender matching, or restore a drifted reconciliation package to source."
---
# Cash & Debt Reconciliation Engine

Package `recon_engine` in `cash-reconciliation/`. Seed 20260331, materiality $50, always exit 0 for the base CLI (flags are an expected outcome, not a failure).

## Commands (run from `cash-reconciliation/`)
```bash
python -m recon_engine                          # reconcile; writes evidence-log.md + xlsx
python -m recon_engine --threshold 25 --no-xlsx
python -m recon_engine.loop --demo              # ASSURANCE LOOP: restore drifted package to source
python -m pytest -q                             # 7,511 tests
```

## Loop verdicts (`recon_engine/loop.py`)
`PASS` (0) / `FLAG` (0, material corrections booked for review) / `FAIL` (1, unconverged).
Key property: **fidelity, not zeroing** — the scenario's genuine reconciling items (deposit-in-transit, keying error) are part of the baseline and survive the loop. Baseline = `reconcile(generate_dataset(seed))`, not "all clean".

## Key files
- `recon_engine/engine.py` — classify clean/timing/flag by account number; lender 3-part total
- `recon_engine/generate.py` — frozen dataclasses; use `dataclasses.replace` to inject drift
- `recon_engine/loop.py` — per-account resync (GL row, statements, dormant marker)
