---
name: triangulate
description: "Run Triangulate (multi-agent AI validation: preparer/reviewer/specialist/deterministic auditor/human gate), the adversarial hallucination demo, or the review loop where arithmetic self-heals and judgment escalates."
---
# Triangulate — AI Validation Framework

Package `triangulate` in `ai-validation-framework/`. Offline mock reviewer by default; live Claude reviewer (`AnthropicReviewer`, stdlib urllib) needs `ANTHROPIC_API_KEY`.

## Commands (run from `ai-validation-framework/`)
```bash
python -m triangulate --demo-adversarial     # inject $49k fake revenue; 6 CRITICAL tie-out breaks; FAIL exit 1
python -m triangulate --sample defective     # AI-assumption + hardcoded-cell sample
python -m triangulate.loop --sample adversarial   # REVIEW LOOP: FAIL -> PASS in 1 turn (B5 re-derived), exit 0
python -m triangulate.loop --sample defective     # arithmetic fixed, judgment ESCALATED, exit 1
python -m pytest -q                          # 8,320 tests
```

## Loop boundary (`triangulate/loop.py`)
Remediates ONLY tie-out breaks on formula cells, re-derived from the cell's own formula ON A CLONE (new workpaper version per turn — never violates the hash-enforced read-only guard). AI assumptions / hardcoded cells / missing cells stay in the human fix packet. "The loop clears arithmetic; it cannot manufacture authority."
