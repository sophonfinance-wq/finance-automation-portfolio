# Sophon Finance Systems — portfolio repo

Nine deterministic finance/tax engines + a self-healing loop layer, all on fictional data
(seeded where the engine declares it). One rule everywhere: **no material output rests on a single model's word.**

## Orient in 30 seconds
- Every engine is a self-contained package: `monthly-close-automation/close_engine`,
  `cash-reconciliation/recon_engine`, `tax-surplus-engine/surplus_engine`,
  `partnership-1065-automation/partnership_tax`, `audit-automation/validation_engine`,
  `ai-validation-framework/triangulate`, `knowledge-brain-engine/brain_engine`,
  `finance-atlas`, `cash-management/cash_engine`.
- Five engines carry a `loop.py` (observe → detect → remediate → re-verify → gate); each has
  its own gate policy and its verdict doubles as the exit code.
- Tests run **per package** (like CI): `cd <package-dir> && python -m pytest -q`.
  `SWEEP=1` unlocks the ~1.15M-case grids. Deps: `pip install -r requirements.txt` once.
- The marketing site is `docs/index.html` (GitHub Pages from `main` — merges go live).

## Use the skills — don't re-derive
`.claude/skills/` carries the distilled operating knowledge from prior sessions. Invoke
instead of rediscovering:
- Engines: `/close` `/recon` `/surplus` `/tax-1065` `/validate` `/triangulate` `/brain` `/atlas`
- The loop family + methodology: `/loops` `/build-loop`
- Brand + comms: `/brand-graphics` `/linkedin-post` `/site-update`
- Releasing work: `/ship`

## House rules
- Fictional data only (seeded where the engine declares it) — the atlas test suite lints a hashed confidentiality deny-list.
- Deterministic core: integer cents, seeded generators, byte-stable outputs. New code must not
  break byte-stability.
- Engines refuse rather than fudge; loops never invent a number; validation never writes.
- Human gate: autonomy is always framed as governed (escalate/quarantine what can't be proven).
