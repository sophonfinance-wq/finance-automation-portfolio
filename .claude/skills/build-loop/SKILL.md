---
name: build-loop
description: "Add a self-healing loop to a new engine using the house methodology (sensor/authority/gate, fault demo, never-invents tests). Use when asked to build a loop for an engine that doesn't have one."
---
# How to Build a Loop (house methodology)

Reference implementations: `surplus_engine/loop.py` (human-gated), `close_engine/loop.py` (autonomous+quarantine), `recon_engine/loop.py` (materiality), `brain_engine/loop.py` (verbatim-or-refuse), `triangulate/loop.py` (arithmetic-vs-judgment).

## Recipe
1. **Scout the engine first**: find the SENSOR (an existing independent check that yields named breaks) and the AUTHORITY (a deterministic re-derivation from the seeded source of record). If no sensor exists (brain case), build one that compares stored state to source.
2. **Pick the gate policy from the domain's discipline** — never copy another engine's. Ask: what is this system entitled to decide on its own? What must it refuse to touch (quarantine/halt/escalate)?
3. **Loop core**: while breaks remain and turns < budget: pick the EARLIEST failing scope (period/category/account/meeting/cell), resync it to authority, book every field change as an Adjustment, re-run the sensor. Frozen dataclasses -> `dataclasses.replace`; mutable -> setattr.
4. **Demo faults**: 3-5 realistic drift injectors, each with a root-cause story, targeting scopes chosen dynamically from the baseline (don't hardcode IDs). Include at least one fault the loop must REFUSE to fix.
5. **Deterministic journal** (frozen dataclasses): faults, initial findings, turns (before/after counts, adjustments), quarantined/held items, verdict. `render_markdown(journal)` must be byte-stable.
6. **CLI**: `--demo`, `--budget`, `--out`; verdict doubles as exit code (match the engine's existing convention — e.g. brain refusal=3).
7. **Tests** (~10-12, mirror `tests/test_loop.py` files): drift trips the sensor; loop converges; NEVER-INVENTS (settled state equals clean authority run exactly); the refusal boundary holds; clean input = zero turns; budget exhaustion fails; exit codes; determinism (two runs render identical markdown); CLI smoke with tmp_path.
8. **README section**: what/why, the five-stage loop line, verdict table with exit codes, `--demo` command + real output excerpt.
9. Run the package suite AND the full portfolio (`python -m pytest` per package, like CI) before pushing.
