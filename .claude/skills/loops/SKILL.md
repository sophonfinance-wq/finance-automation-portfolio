---
name: loops
description: "Run or demo the full self-healing loop family (five engines, five gate policies), or explain the loop architecture. Use when asked about the loops as a family, gate policies, or a full loop demo sweep."
---
# The Self-Healing Loop Family

Five loops, one architecture: **observe -> detect -> remediate -> re-verify -> gate -> repeat**.
Sensor = the engine's own control harness. Authority = deterministic re-derivation from the seeded source of record. The loop never invents a number.

| Engine | Command (from its folder) | Gate policy | Exit |
|---|---|---|---|
| Close | `python -m close_engine.loop --demo` | autonomous + quarantine (`AUTO-POSTED/PARTIAL/HALTED`) | HALTED=1 |
| Tax surplus | `python -m surplus_engine.loop --demo` | human-gated (`PASS/FLAG/FAIL`) | FAIL=1 |
| Recon | `python -m recon_engine.loop --demo` | materiality (`PASS/FLAG/FAIL`) | FAIL=1 |
| Knowledge brain | `python -m brain_engine.loop --demo` | verbatim-or-refuse (`CLEAN/REMEDIATED/ESCALATED`) | ESCALATED=3 |
| Triangulate | `python -m triangulate.loop --sample adversarial` | arithmetic vs judgment (`CLEAN/AUTO-CLEARED/ESCALATED`) | non-PASS=1 |

Full sweep: run all five demos and report each verdict line. Docs: ARCHITECTURE.md section 5a; each engine README has a loop section; assets/flows/self-healing-close-loop.svg is the CPA-readable diagram.
