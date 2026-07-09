---
name: surplus
description: "Run the Tax Surplus / ACB engine (Reg. 5907, per-layer FX, 212-identity reconciliation harness) or its human-gated assurance loop. Use for cross-border tax demos, the FX sign-flip, --check gating, or drifted-workpaper remediation."
---
# Tax Surplus / ACB Engine

Package `surplus_engine` in `tax-surplus-engine/`. Seed 20240607. Canadian foreign-affiliate surplus pools, distribution waterfall, ACB on capital events only.

## Commands (run from `tax-surplus-engine/`)
```bash
python -m surplus_engine --start 2021 --end 2024 --out out --xlsx
python -m surplus_engine --start 2021 --end 2024 --check    # 212 identity checks; exit 1 on any break
python -m surplus_engine.loop --demo --out out              # HUMAN-GATED LOOP: settle drifted periods earliest-first
python -m pytest -q                                         # ~1,498 tests
```

## Showpieces
- **FX sign-flip**: `out/fx_layer_analysis.md` — USD ACB $0 but per-layer CAD ACB $(660.35); find the flag glyph.
- **Loop demo**: 3 turns lock FY2021-23, breaks 6->4->2->0, verdict FLAG (CAD 107,088.50 adjustments for human review).

## Loop verdicts (`surplus_engine/loop.py`)
`PASS` (0) / `FLAG` (0, material -> human reviews what changed) / `FAIL` (1). Sensor = `reconcile.py` (independent re-derivation); authority = `SurplusEngine.run` on seeded facts. Never invents: settled set is byte-identical to a clean run.
