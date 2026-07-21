---
name: close
description: "Run the Month-End Close engine: full close, ten-control sentinel, fault-injection guardrails demo, or the autonomous close loop. Use when asked to run/demo the close, prove the close controls, or self-heal a drifted close."
---
# Month-End Close Engine

Package `close_engine` in `monthly-close-automation/`. All data fictional, seeded (default seed 2026). Integer-cent math.

## Commands (run from `monthly-close-automation/`)
```bash
python -m close_engine --period 2026-03 --out ./output   # full close; exit != 0 if not clean
python -m close_engine --demo-guardrails                 # inject 12 faults, prove all 10 controls (C1-C10) catch them
python -m close_engine.loop --demo --out output          # AUTONOMOUS LOOP: resync drift from sub-ledger, quarantine C10 tamper
python -m pytest -q                                      # 15,687 tests
```

## Loop verdicts (`close_engine/loop.py`)
`AUTO-POSTED` (0) / `AUTO-POSTED (PARTIAL)` (0, something quarantined) / `HALTED` (1).
Boundary of autonomy: C10 locked-period tamper -> QUARANTINE (held, never overwritten); C1 broken opening TB -> HALT (never fabricated).

## Key files
- `close_engine/engine.py` — 7 recurring-entry classes, refuses out-of-tie posts
- `close_engine/sentinel/` — controls C1-C10, shadow recompute, findings
- `close_engine/faults.py` — 12 seeded fault injectors (the drift vocabulary)
- `close_engine/loop.py` + `loop_report.py` — autonomous loop + Markdown/HTML reports

Windows consoles: set `PYTHONIOENCODING=utf-8` if emoji banners crash.
