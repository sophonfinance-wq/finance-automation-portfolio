# Engine Datasheet Pages — Phase 1 (Triangulate Exemplar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, data-driven generator that renders the Triangulate engine page at `docs/engines/triangulate.html` as an eleven-zone chip-style datasheet, with a full pytest suite, CI wiring, and the homepage link updated — shipping the exemplar in-place at its existing URL.

**Architecture:** A stdlib-only Python generator (`site-datasheets/generate_datasheets.py`) reads one JSON spec per engine (`site-datasheets/specs/triangulate.json`) and renders it through a shared `string.Template` shell plus zone-helper functions that each return an HTML string — the exact pattern proven in `finance-atlas/generate.py`. Output is a pure function of spec + template (no timestamps, no environment reads), so two runs are byte-identical and the committed page must equal a fresh render. Interactivity is vanilla JS + CSS 3D + inline SVG; no bundler, no WebGL library, no new runtime dependencies.

**Tech Stack:** Python 3.12 stdlib (`json`, `html`, `string.Template`, `pathlib`, `hashlib`, `re`), pytest, vanilla JS/CSS/SVG. Google Fonts (IBM Plex Sans/Mono) already used site-wide. GitHub Pages serves `docs/`.

## Global Constraints

Every task's requirements implicitly include these (verbatim from the design spec, `specs/2026-07-20-engine-datasheet-pages-design.md`, and `docs/BRAND-VOICE.md`):

- **Determinism:** generator is a pure function of specs + template. No `datetime`, no timestamps, no environment reads, no `Math.random`-style nondeterminism. Two runs → byte-identical files. `json.dumps(..., ensure_ascii=True, sort_keys=False)` preserving insertion order; where a set/dir is iterated, sort explicitly.
- **Stdlib only for generation** (CI pins Python 3.12). No new runtime dependencies. No three.js, no bundler. Google Fonts stays.
- **Module naming (collision-proof under root pytest collection):** test package is `datasheet_tests/` (NOT a second top-level `tests`); generator module is `generate_datasheets.py` (NOT a second top-level `generate`).
- **Output path:** `docs/engines/<slug>.html`, committed. GitHub Pages serves `docs/`. URLs, nav, footer, and the img→video motion-swap pattern are **retained** — the upgrade is in-place.
- **Every number is true and demonstrable.** Every figure in the spec-strip, benchmarks, scenarios, and limits carries a non-empty `source` pointer (file/test/command). No invented dollar-savings figures; money/time framing is qualitative or an explicitly labeled fictional illustration.
- **Voice:** measured; no superlatives or exclamation-driven hype. No exclamation marks in body copy (permitted only inside `<pre>`/`<code>` CLI output). Banned phrases from BRAND-VOICE.md ("slide deck," "vibes," "marks its own homework," "press play," "wow moment," "command center," "game-changer") must not appear.
- **Orchestration framing, verbatim wherever "autonomous"/"agent-enabled" appears:** *"an optional orchestration layer for approved, agent-enabled environments; the platform runs fully without it."*
- **Knowledge Brain rule (applies to any page mentioning it):** never state or imply the engine applies/verifies changes; "hands-free" is banned. (Triangulate page must not claim it applies fixes autonomously without the human gate.)
- **Footer disclaimer on every page:** "All public examples use fictional, seeded data."
- **Performance budget:** ≤ 150 KB per generated page (HTML + inline SVG/CSS/JS, both hero representations included).
- **Part number for this engine:** `SFS-E06-TRI` · family "AI Validation" · slug `triangulate` · num `6`. Canonical H1: **Triangulate**.

---

## File Structure

```
site-datasheets/
├── pytest.ini                       # testpaths = datasheet_tests
├── conftest.py                      # sys.path bootstrap (repo-root import safety)
├── datasheet_spec.py                # spec loader + schema validation (pure, importable)
├── generate_datasheets.py          # the generator: render(slug) + main(); stdlib only
├── counts.json                      # per-engine test counts (refreshed via pytest --collect-only)
├── templates/
│   └── datasheet.html.tmpl          # the shared eleven-zone string.Template shell
├── partials/
│   ├── page.css                     # inline CSS (IBM Plex + Carbon tokens, datasheet zones)
│   └── page.js                      # inline JS (motion-swap + die-stack rotate + copy button)
├── specs/
│   └── triangulate.json             # THE data source of truth for the Triangulate page
├── capture/
│   └── record_screencast.py         # minimal CLI-run capture/encode helper (Task 10)
└── datasheet_tests/
    ├── __init__.py
    ├── conftest.py                  # fixtures: rendered html, DocIndex, loaded spec
    ├── voice_lint_terms.txt         # banned-phrase list seeded from BRAND-VOICE.md
    ├── test_schema.py               # spec validates; required fields; claim-lint (sources)
    ├── test_roster.py               # part no / slug / num; H1 asserts vs BRAND-VOICE roster
    ├── test_generator.py            # determinism; committed-artifact-fresh; --out; clean exit
    ├── test_die_stack.py            # zone 2: both representations; N focusable layers
    ├── test_schematic.py            # zone 5: blocks + edges rendered; source links
    ├── test_page_budget.py          # ≤150 KB; link/asset existence
    ├── test_voice_lint.py           # banned phrases; no "!" in body; orchestration framing
    └── test_deny_list.py            # confidentiality sweep (atlas pattern) over generated page

docs/engines/triangulate.html        # MODIFIED: regenerated datasheet (in place, same URL)
docs/BRAND-VOICE.md                  # MODIFIED: canonical roster updated to nine site names
docs/index.html                      # MODIFIED: Triangulate card link text → "View datasheet"
.github/workflows/ci.yml             # MODIFIED: add site-datasheets to dep + test loops; drift step
.github/workflows/*test-count*.yml   # MODIFIED: deselect datasheet-tooling marker from headline
```

Design decision (locked here): **zone 10 media uses the existing `assets/tile-triangulate.webp` + `assets/tile-triangulate-motion.mp4`** (already committed) so the page ships without a capture pipeline. The dedicated CLI screencast (Task 10) is a separately-scoped enhancement a later spec bump can point to; it does not block Phase 1.

---

## Task 1: Package scaffold + spec loader + schema validation

**Files:**
- Create: `site-datasheets/conftest.py`
- Create: `site-datasheets/pytest.ini`
- Create: `site-datasheets/datasheet_spec.py`
- Create: `site-datasheets/datasheet_tests/__init__.py`
- Create: `site-datasheets/datasheet_tests/conftest.py`
- Test: `site-datasheets/datasheet_tests/test_schema.py`

**Interfaces:**
- Produces:
  - `datasheet_spec.REQUIRED_FIELDS: tuple[str, ...]`
  - `datasheet_spec.SOURCED_ARRAYS: tuple[str, ...]` — arrays whose every row needs a non-empty `source` (`"spec_strip"`, `"benchmarks"`, `"scenarios"`, `"limits"`)
  - `datasheet_spec.load_spec(slug: str) -> dict` — reads `specs/<slug>.json`, returns parsed dict
  - `datasheet_spec.validate_spec(spec: dict) -> list[str]` — returns a list of human-readable problems; empty list means valid
  - `datasheet_spec.SPECS_DIR: Path`, `datasheet_spec.ROOT: Path`

- [ ] **Step 1: Create the pytest config**

Create `site-datasheets/pytest.ini`:

```ini
[pytest]
testpaths = datasheet_tests
python_files = test_*.py
markers =
    site_tooling: datasheet-generator tooling tests (deselected from the engine test-count headline)
```

- [ ] **Step 2: Create the root conftest for import safety**

Create `site-datasheets/conftest.py` (mirrors the atlas path bootstrap so `datasheet_spec` and `generate_datasheets` import cleanly under both root and per-dir pytest runs):

```python
"""Put the site-datasheets root on sys.path for both root and per-dir pytest."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 3: Write the failing schema test**

Create `site-datasheets/datasheet_tests/__init__.py` (empty file), then create `site-datasheets/datasheet_tests/conftest.py`:

This conftest bootstraps the import path AND auto-marks every test in this package `site_tooling`, so the repo-root `pytest --collect-only` in `test-count.yml` can deselect the whole package from the nine-engine headline (the root run recursively collects this package — root `pyproject.toml` has no `testpaths` restriction):

```python
"""Shared fixtures + package-wide marker for the datasheet test suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_collection_modifyitems(items):
    """Every datasheet test is site tooling, not an engine test."""
    for item in items:
        item.add_marker("site_tooling")
```

Then create `site-datasheets/datasheet_tests/test_schema.py`:

```python
"""Spec schema: required fields present; every sourced row carries a source."""
from __future__ import annotations

import datasheet_spec as ds


def _minimal_valid_spec() -> dict:
    return {
        "num": 6, "slug": "triangulate", "part_no": "SFS-E06-TRI",
        "mnemonic": "TRI", "family": "AI Validation", "name": "Triangulate",
        "tagline": "t", "plain_summary": "s", "rev": "2026-07-20",
        "status": "PRODUCTION",
        "layers": [{"id": "a", "label": "A", "plain": "p",
                    "engineering": "e", "source_link": "u"}],
        "blocks": [{"id": "b", "label": "B", "source_link": "u",
                    "col": 0, "row": 0}],
        "edges": [{"from": "b", "to": "b"}],
        "spec_strip": [{"label": "L", "value": "1", "source": "s"}],
        "problem_statement": "p",
        "scenarios": [{"title": "T", "narrative": "n", "source": "s"}],
        "instruction_set": [{"cmd": "c", "operation": "o", "output": "x",
                             "exit_code": "0", "artifacts": "a"}],
        "benchmarks": [{"label": "L", "value": "1", "unit": "u", "source": "s"}],
        "control_characteristics": {"authority": [], "verdict_map": [],
                                    "guarantees": [], "determinism": {},
                                    "gate_policy": {}, "modes": []},
        "limits": [{"statement": "x", "source": "s"}],
        "media": {"poster": "p.webp", "motion": "m.mp4", "crops": []},
        "links": {"readme": "r", "source": "s", "tests": "t", "codespaces": "c"},
        "meta": {"description": "d"},
    }


def test_minimal_spec_is_valid():
    assert ds.validate_spec(_minimal_valid_spec()) == []


def test_missing_required_field_is_reported():
    spec = _minimal_valid_spec()
    del spec["part_no"]
    problems = ds.validate_spec(spec)
    assert any("part_no" in p for p in problems)


def test_sourced_row_without_source_is_reported():
    spec = _minimal_valid_spec()
    spec["benchmarks"][0]["source"] = ""
    problems = ds.validate_spec(spec)
    assert any("benchmarks" in p and "source" in p for p in problems)
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'datasheet_spec'`.

- [ ] **Step 5: Write the spec loader + validator**

Create `site-datasheets/datasheet_spec.py`:

```python
"""Load and validate one engine datasheet spec (pure, stdlib only)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPECS_DIR = ROOT / "specs"

REQUIRED_FIELDS: tuple[str, ...] = (
    "num", "slug", "part_no", "mnemonic", "family", "name", "tagline",
    "plain_summary", "rev", "status", "layers", "blocks", "edges",
    "spec_strip", "problem_statement", "scenarios", "instruction_set",
    "benchmarks", "control_characteristics", "limits", "media", "links",
    "meta",
)

#: Arrays where every row must carry a non-empty "source" (claim-lint).
SOURCED_ARRAYS: tuple[str, ...] = (
    "spec_strip", "benchmarks", "scenarios", "limits",
)

_REV_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PART_RE = re.compile(r"^SFS-E\d{2}-[A-Z]{3}$")


def load_spec(slug: str) -> dict:
    path = SPECS_DIR / f"{slug}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_spec(spec: dict) -> list[str]:
    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in spec:
            problems.append(f"missing required field: {field}")
    if "rev" in spec and not _REV_RE.match(str(spec["rev"])):
        problems.append(f"rev must be ISO date YYYY-MM-DD, got {spec['rev']!r}")
    if "part_no" in spec and not _PART_RE.match(str(spec["part_no"])):
        problems.append(f"part_no must match SFS-E##-XXX, got {spec['part_no']!r}")
    if spec.get("status") not in (None, "PRODUCTION"):
        problems.append(f"status must be PRODUCTION, got {spec.get('status')!r}")
    for array_name in SOURCED_ARRAYS:
        for i, row in enumerate(spec.get(array_name, [])):
            if not str(row.get("source", "")).strip():
                problems.append(f"{array_name}[{i}] has empty source")
    return problems
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_schema.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add site-datasheets/pytest.ini site-datasheets/conftest.py \
        site-datasheets/datasheet_spec.py site-datasheets/datasheet_tests/
git commit -m "feat(datasheets): spec loader + schema validation with claim-lint"
```

---

## Task 2: The Triangulate spec JSON (real data) + roster test

**Files:**
- Create: `site-datasheets/specs/triangulate.json`
- Test: `site-datasheets/datasheet_tests/test_roster.py`

**Interfaces:**
- Consumes: `datasheet_spec.load_spec`, `datasheet_spec.validate_spec` (Task 1).
- Produces: the file `specs/triangulate.json` whose top-level fields match the §4 roster (`num=6`, `slug="triangulate"`, `part_no="SFS-E06-TRI"`, `mnemonic="TRI"`, `family="AI Validation"`, `name="Triangulate"`).

- [ ] **Step 1: Write the failing roster test**

Create `site-datasheets/datasheet_tests/test_roster.py`:

```python
"""The Triangulate spec loads, validates, and matches the §4 roster identity."""
from __future__ import annotations

import datasheet_spec as ds


def test_triangulate_spec_is_valid():
    spec = ds.load_spec("triangulate")
    assert ds.validate_spec(spec) == []


def test_triangulate_roster_identity():
    spec = ds.load_spec("triangulate")
    assert spec["num"] == 6
    assert spec["slug"] == "triangulate"
    assert spec["part_no"] == "SFS-E06-TRI"
    assert spec["mnemonic"] == "TRI"
    assert spec["family"] == "AI Validation"
    assert spec["name"] == "Triangulate"


def test_triangulate_has_all_five_die_layers():
    # README roster: Preparer, Specialist, Reviewer, Deterministic Auditor, Human Gate
    spec = ds.load_spec("triangulate")
    labels = {layer["label"] for layer in spec["layers"]}
    for expected in ("Preparer", "Specialist", "Reviewer",
                     "Deterministic Auditor", "Human Gate"):
        assert expected in labels, expected
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_roster.py -v`
Expected: FAIL — `FileNotFoundError: specs/triangulate.json`.

- [ ] **Step 3: Write the Triangulate spec JSON**

Create `site-datasheets/specs/triangulate.json`. All values below are drawn from `ai-validation-framework/README.md` (the engine's own documentation) — no invented figures. `source` fields point at the README, a test file, or a runnable command:

```json
{
  "num": 6,
  "slug": "triangulate",
  "part_no": "SFS-E06-TRI",
  "mnemonic": "TRI",
  "family": "AI Validation",
  "name": "Triangulate",
  "tagline": "Separation of duties for AI work — no consensus, no sign-off",
  "plain_summary": "Triangulate runs independent reviewer roles plus a deterministic auditor over the same AI-assisted workpaper. When they disagree, the line stops and the work goes to a person. It is separation of duties applied to AI: an explicit authority hierarchy, not a multi-model majority vote.",
  "rev": "2026-07-20",
  "status": "PRODUCTION",
  "marketing_thesis": "A processor buyer cannot re-run the vendor's benchmark lab. Every figure on this page re-derives from the public repository — the benchmark is a command, not a press release.",

  "layers": [
    {"id": "gate", "label": "Human Gate",
     "plain": "A person makes the final call. The framework never overrides itself.",
     "engineering": "Deterministic gate maps severity to a verdict; sign-off authority is held by a human, not any model.",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/reconcile.py"},
    {"id": "auditor", "label": "Deterministic Auditor",
     "plain": "Re-does the arithmetic itself, so no model is asked whether a number 'looks right.'",
     "engineering": "Mechanically re-derives every formula on a hashed clone; a tie-out mismatch is a Critical finding regardless of model opinion.",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/auditor.py"},
    {"id": "reviewer", "label": "Reviewer",
     "plain": "Challenges the draft and flags issues — read-only, it cannot change the file.",
     "engineering": "Read-only reviewer role; the orchestrator hashes the workpaper before and after so a reviewer cannot mutate what it inspects.",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/reviewer.py"},
    {"id": "specialist", "label": "Specialist",
     "plain": "A narrow second opinion or source analysis where the work needs one.",
     "engineering": "Specialist role supplies scoped second opinions; ranks below source data and signed work in the authority model.",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/specialist.py"},
    {"id": "preparer", "label": "Preparer",
     "plain": "Builds the first draft of the workpaper.",
     "engineering": "Preparer role produces the draft that the other roles then challenge; no self-review.",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/preparer.py"}
  ],

  "blocks": [
    {"id": "preparer", "label": "Preparer", "kind": "role", "col": 0, "row": 1,
     "plain": "drafts the workpaper",
     "engineering": "DemoPreparer builds draft; offline deterministic in the public demo",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/preparer.py"},
    {"id": "reviewer", "label": "Reviewer", "kind": "role", "col": 1, "row": 0,
     "engineering": "read-only challenge; hash-guarded",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/reviewer.py"},
    {"id": "specialist", "label": "Specialist", "kind": "role", "col": 1, "row": 1,
     "engineering": "scoped second opinion",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/specialist.py"},
    {"id": "auditor", "label": "Deterministic Auditor", "kind": "audit", "col": 1, "row": 2,
     "engineering": "re-derives every formula mechanically",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/roles/auditor.py"},
    {"id": "reconcile", "label": "Reconcile + Gate", "kind": "gate", "col": 2, "row": 1,
     "engineering": "severity → verdict; findings reconciled",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/reconcile.py"},
    {"id": "human", "label": "Human Gate", "kind": "human", "col": 3, "row": 1,
     "plain": "a person signs off — or doesn't",
     "engineering": "final authority; framework never overrides itself",
     "source_link": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/triangulate/reconcile.py"}
  ],
  "edges": [
    {"from": "preparer", "to": "reviewer", "label": "draft"},
    {"from": "preparer", "to": "specialist", "label": "draft"},
    {"from": "preparer", "to": "auditor", "label": "draft"},
    {"from": "reviewer", "to": "reconcile", "label": "findings"},
    {"from": "specialist", "to": "reconcile", "label": "findings"},
    {"from": "auditor", "to": "reconcile", "label": "tie-outs"},
    {"from": "reconcile", "to": "human", "label": "verdict", "gate": true},
    {"from": "reconcile", "to": "preparer", "label": "fix packet (loop)"}
  ],

  "spec_strip": [
    {"label": "Tests", "value": "8,320", "source": "py -3 -m pytest --collect-only -q (ai-validation-framework/); verified 2026-07-20 — the README's \"1,311\" is stale", "plain": "the checks that pin this engine's behavior"},
    {"label": "Roles", "value": "5", "source": "ai-validation-framework/README.md — Preparer, Reviewer, Specialist, Deterministic audit, Human gatekeeper", "plain": "independent duties over one workpaper"},
    {"label": "Verdict states", "value": "PASS / FLAG / FAIL", "source": "ai-validation-framework/README.md — verdicts and exit behavior"},
    {"label": "Gate exit codes", "value": "0 = PASS · non-zero = FLAG/FAIL", "source": "ai-validation-framework/README.md — \"exits 0 on PASS and non-zero on FLAG/FAIL\"", "plain": "so it can act as a CI gate"},
    {"label": "Default mode", "value": "offline, no API key", "source": "ai-validation-framework/README.md — \"default demo needs no API key and no network access\""},
    {"label": "Determinism", "value": "seeded + read-only", "source": "ai-validation-framework/README.md — \"All sample data is fictional and seeded\"; read-only reviewer"}
  ],

  "problem_statement": "No high-stakes workpaper should rely on one AI system reporting \"looks good.\" Models agree too easily, invent support, miss the same issue twice, and explain a number without tying it to source. Triangulate assumes those failures will happen and builds the workflow around them.",
  "scenarios": [
    {"title": "An injected hallucination is caught by the arithmetic, not an opinion",
     "narrative": "In the adversarial demo, an AI asserts a Total Revenue $49,000 over what the revenue streams actually sum to, backed only by an 'AI assumption' — the lowest authority. Because that cell feeds tax and net, the single bad figure cascades. The Reviewer and the deterministic Auditor both flag it independently; the verdict is FAIL and the process exits non-zero.",
     "source": "python -m triangulate --demo-adversarial (ai-validation-framework/README.md)"},
    {"title": "The gate discriminates — a clean workpaper passes",
     "narrative": "The clean sample runs the identical flow and returns PASS, proving the gate discriminates instead of always failing.",
     "source": "python -m triangulate --sample clean (ai-validation-framework/README.md)"},
    {"title": "Arithmetic self-heals; judgment escalates",
     "narrative": "The review loop re-derives the lowest broken formula cell from its own formula on a clone, then re-runs the full pipeline. The injected $49k error clears in one turn (FAIL → PASS). An AI-assumption input and a hardcoded cell have nothing to re-derive from, so they stay in the fix packet for a human (FAIL → FLAG).",
     "source": "python -m triangulate.loop --sample adversarial / --sample defective (ai-validation-framework/README.md)"}
  ],

  "instruction_set": [
    {"cmd": "python -m triangulate", "operation": "run the defective sample", "output": "VERDICT: FAIL [cannot sign off]", "exit_code": "non-zero", "artifacts": "builder memo, fix packet, change log, QA summary, verdict.json"},
    {"cmd": "python -m triangulate --sample clean", "operation": "run the clean sample", "output": "VERDICT: PASS", "exit_code": "0", "artifacts": "output/ artifacts + verdict.json"},
    {"cmd": "python -m triangulate --demo-adversarial", "operation": "inject one hallucinated figure and catch it", "output": "VERDICT: FAIL · Critical=6", "exit_code": "non-zero", "artifacts": "fix packet showing cascade"},
    {"cmd": "python -m triangulate.loop --sample adversarial", "operation": "self-heal the injected error", "output": "FAIL → PASS", "exit_code": "0", "artifacts": "re-derivation change log"},
    {"cmd": "python -m triangulate --xlsx", "operation": "also emit a small .xlsx workpaper", "output": "VERDICT + workpaper.xlsx", "exit_code": "non-zero", "artifacts": "output/*.xlsx"},
    {"cmd": "python -m pytest -q", "operation": "run the engine's test suite", "output": "test session summary", "exit_code": "0", "artifacts": "none"}
  ],

  "benchmarks": [
    {"label": "Adversarial cascade depth", "value": "6", "unit": "Critical findings from 1 injected cell", "source": "ai-validation-framework/README.md — \"Critical=6\" in --demo-adversarial", "plain": "one bad number, six downstream failures caught"},
    {"label": "Self-heal turns (adversarial)", "value": "1", "unit": "loop turn to PASS", "source": "ai-validation-framework/README.md — \"Turn 1 re-derive B5 … PASS\""},
    {"label": "Independent detectors", "value": "2", "unit": "roles flag the same cell", "source": "ai-validation-framework/README.md — \"flagged independently by two roles\""},
    {"label": "Engine tests", "value": "8,320", "unit": "tests", "source": "py -3 -m pytest --collect-only -q (ai-validation-framework/); verified 2026-07-20 — the README's \"1,311\" is stale"}
  ],

  "control_characteristics": {
    "authority": [
      {"rank": 1, "level": "Source data", "note": "signed/source evidence outranks everything"},
      {"rank": 2, "level": "Signed work", "note": "prior signed work product"},
      {"rank": 3, "level": "AI assumption", "note": "lowest authority; cannot outrank source"}
    ],
    "verdict_map": [
      {"severity": "Critical present", "verdict": "FAIL", "action": "returned for rebuild; exits non-zero"},
      {"severity": "High/unresolved judgment", "verdict": "FLAG", "action": "fix packet escalated to a human"},
      {"severity": "None", "verdict": "PASS", "action": "eligible for human sign-off; exit 0"}
    ],
    "guarantees": [
      "Read-only reviewer: the orchestrator hashes the workpaper before and after review steps, so a reviewer cannot mutate what it inspects.",
      "Deterministic audit: every formula is mechanically re-derived; arithmetic decides, not model opinion.",
      "Seeded, fictional data throughout the public demo."
    ],
    "determinism": {"seeded": true, "read_only": true, "offline_default": true},
    "gate_policy": {"human_gated": true, "note": "A stopped line goes to a person — the framework never overrides itself."},
    "modes": [
      {"name": "Enterprise-safe mode (default)", "detail": "deterministic mock reviewer, no API key, no network call, runnable in conservative corporate IT."},
      {"name": "Agent-accelerated mode", "detail": "where approved, a live Anthropic Claude reviewer adapter can replace the mock reviewer; an optional orchestration layer for approved, agent-enabled environments; the platform runs fully without it."}
    ]
  },

  "limits": [
    {"statement": "The loop clears arithmetic; it cannot manufacture authority. An AI-assumption input or a hardcoded cell with no formula has nothing to re-derive from — those stay in the fix packet for a human.", "source": "ai-validation-framework/README.md — review-loop section"},
    {"statement": "The framework does not apply changes on its own or override its own verdict; final sign-off authority is held by a person.", "source": "ai-validation-framework/README.md — human gate"},
    {"statement": "The public demo runs offline with a deterministic mock reviewer; live-model results depend on the pinned model approved for that client environment.", "source": "ai-validation-framework/README.md — two operating modes"}
  ],

  "media": {
    "poster": "../assets/tile-triangulate.webp",
    "motion": "../assets/tile-triangulate-motion.mp4",
    "crops": []
  },

  "quickstart": [
    {"label": "Clone + run the defective sample", "command": "git clone https://github.com/sophonfinance-wq/finance-automation-portfolio.git && cd ai-validation-framework && python -m triangulate"},
    {"label": "Run the clean sample (PASS)", "command": "python -m triangulate --sample clean"}
  ],

  "links": {
    "readme": "https://github.com/sophonfinance-wq/finance-automation-portfolio/blob/main/ai-validation-framework/README.md",
    "source": "https://github.com/sophonfinance-wq/finance-automation-portfolio/tree/main/ai-validation-framework",
    "tests": "/tests/",
    "codespaces": "https://codespaces.new/sophonfinance-wq/finance-automation-portfolio"
  },

  "meta": {
    "description": "Triangulate (SFS-E06-TRI) datasheet — separation of duties for AI-assisted financial workpapers: independent reviewer roles plus a deterministic auditor, a human-gated verdict, and every figure re-derivable from the public repository."
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_roster.py datasheet_tests/test_schema.py -v`
Expected: PASS (all). If `validate_spec` reports a problem, fix the JSON (do not weaken the validator).

- [ ] **Step 5: Commit**

```bash
git add site-datasheets/specs/triangulate.json site-datasheets/datasheet_tests/test_roster.py
git commit -m "feat(datasheets): Triangulate spec JSON (README-sourced) + roster test"
```

---

## Task 3: Generator core + template + text/tabular zones

Renders zones 1, 3, 4, 6, 7, 8, 9, 11 (masthead, spec strip, plain-terms, instruction set, benchmarks, control characteristics, limits, integration) into the shell template. Zones 2 (die stack) and 5 (schematic) render via placeholder tokens filled by Tasks 4–5; here they get empty container markup so the page is valid and deterministic.

**Files:**
- Create: `site-datasheets/templates/datasheet.html.tmpl`
- Create: `site-datasheets/partials/page.css`
- Create: `site-datasheets/partials/page.js`
- Create: `site-datasheets/generate_datasheets.py`
- Test: `site-datasheets/datasheet_tests/test_generator.py`
- Modify: `site-datasheets/datasheet_tests/conftest.py` (add fixtures)

**Interfaces:**
- Consumes: `datasheet_spec.load_spec`, `datasheet_spec.validate_spec`.
- Produces:
  - `generate_datasheets.render(slug: str) -> str` — full HTML document as a string
  - `generate_datasheets.main(argv: list[str] | None = None) -> int` — CLI: `--slug` (default `triangulate`), `--out` (default `docs/engines/<slug>.html`)
  - `generate_datasheets.OUT_DIR: Path` (= repo `docs/engines`)
  - `generate_datasheets.die_stack_html(spec: dict) -> str` and `generate_datasheets.schematic_html(spec: dict) -> str` — defined as stubs here returning an empty labeled container; **replaced** in Tasks 4–5.

- [ ] **Step 1: Add fixtures to the test conftest**

Append to `site-datasheets/datasheet_tests/conftest.py`:

```python
import pytest  # noqa: E402
import datasheet_spec as ds  # noqa: E402
import generate_datasheets as gen  # noqa: E402


@pytest.fixture(scope="session")
def spec() -> dict:
    return ds.load_spec("triangulate")


@pytest.fixture(scope="session")
def rendered() -> str:
    return gen.render("triangulate")
```

- [ ] **Step 2: Write the failing generator test**

Create `site-datasheets/datasheet_tests/test_generator.py`:

```python
"""Generator: determinism, committed-artifact freshness, CLI, well-formed doc."""
from __future__ import annotations

import subprocess
import sys

import generate_datasheets as gen
from datasheet_tests.conftest import ROOT  # noqa: F401 (path bootstrap)


def test_render_is_deterministic_in_process():
    assert gen.render("triangulate") == gen.render("triangulate")


def test_two_runs_are_byte_identical(tmp_path):
    a = tmp_path / "a.html"
    b = tmp_path / "b.html"
    assert gen.main(["--slug", "triangulate", "--out", str(a)]) == 0
    assert gen.main(["--slug", "triangulate", "--out", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()


def test_document_is_well_formed():
    html = gen.render("triangulate")
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "SFS-E06-TRI" in html
    assert "Triangulate" in html


def test_committed_page_is_fresh():
    from pathlib import Path
    page = gen.OUT_DIR / "triangulate.html"
    assert page.read_bytes() == gen.render("triangulate").encode("utf-8"), (
        "docs/engines/triangulate.html is stale — regenerate it"
    )


def test_cli_exits_cleanly(tmp_path):
    target = tmp_path / "t.html"
    proc = subprocess.run(
        [sys.executable, "generate_datasheets.py",
         "--slug", "triangulate", "--out", str(target)],
        cwd=str(gen.ROOT), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert target.is_file()
```

Note: `test_committed_page_is_fresh` will fail until Task 11 regenerates the committed page. That is expected and intended — it is the drift guard. Mark it `@pytest.mark.xfail(reason="committed page written in Task 11", strict=False)` while building, and **remove the xfail in Task 11** once the page is generated. Add this import at the top: `import pytest` and decorate that one test.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_generator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'generate_datasheets'`.

- [ ] **Step 4: Create the inline CSS partial**

Create `site-datasheets/partials/page.css` — reuse the existing engine-page tokens (IBM Plex + Carbon blue `#0f62fe`) verbatim from `docs/engines/triangulate.html`, then add datasheet-zone styles. Full file:

```css
:root{--bg:#ffffff;--bg-alt:#f4f4f4;--border:#e0e0e0;--border-strong:#c6c6c6;--text:#161616;--text-2:#525252;--text-3:#6f6f6f;--blue:#0f62fe;--blue-hover:#0043ce;--blue-tint:#edf5ff;--green:#198038;--amber:#8e6a00;--red:#da1e28;
  --sans:'IBM Plex Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;--mono:'IBM Plex Mono',ui-monospace,Consolas,Menlo,monospace;}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--sans);color:var(--text);background:var(--bg);line-height:1.6}
.wrap{width:100%;max-width:1040px;margin:0 auto;padding:0 22px}
a{color:var(--blue)}
header.nav{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);border-bottom:1px solid var(--border);padding:14px 0}
.nav-in{display:flex;align-items:center;gap:16px}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--text)}
.brand-mark{width:24px;height:24px}
.brand-word{font-weight:600;font-size:14px;letter-spacing:.2px;white-space:nowrap}
.brand-word span{font-weight:300}
.nav-in .backlink{margin-left:auto;color:var(--blue);text-decoration:none;font-size:14px}
.btn{display:inline-flex;align-items:center;gap:10px;text-decoration:none;font-size:15px;padding:13px 18px;min-height:46px;border:1px solid transparent}
.btn-p{background:var(--blue);color:#fff}.btn-p:hover{background:var(--blue-hover)}
.btn-t{background:transparent;color:var(--blue);border-color:var(--blue)}.btn-t:hover{background:var(--blue);color:#fff}
.kicker{font-family:var(--mono);font-size:12px;font-weight:500;letter-spacing:.6px;color:var(--blue)}
.partline{font-family:var(--mono);font-size:12.5px;color:var(--text-2);letter-spacing:.3px;margin-top:4px}
.legend{font-size:12px;color:var(--text-3);margin-top:6px}
.thesis{border-left:3px solid var(--blue);background:var(--blue-tint);padding:12px 16px;margin:18px 0;font-size:14.5px;color:var(--text-2)}
.masthead{padding:46px 0 8px}
h1{font-size:clamp(30px,5vw,46px);font-weight:300;letter-spacing:-.3px;line-height:1.15;margin:8px 0 6px}
h1 strong{font-weight:600}
.tag{font-size:16px;color:var(--text-2);max-width:44em}
.intro{font-size:16.5px;color:var(--text-2);max-width:48em;margin:16px 0 8px}
section{padding:30px 0 6px;border-top:1px solid var(--border);margin-top:26px}
section:first-of-type{border-top:0;margin-top:0}
h2{font-size:clamp(20px,2.6vw,26px);font-weight:600;letter-spacing:-.2px;margin-bottom:6px}
.zone-k{font-family:var(--mono);font-size:11px;font-weight:500;letter-spacing:.8px;text-transform:uppercase;color:var(--text-3);display:block;margin-bottom:12px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--border)}
.pair>div{padding:18px 20px}.pair>div+div{border-left:1px solid var(--border)}
.pair h4{font-family:var(--mono);font-size:11px;letter-spacing:.8px;text-transform:uppercase;color:var(--text-3);margin-bottom:8px}
.pair .plain h4{color:var(--blue)}
.strip{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--border)}
.strip .cell{padding:16px 18px;border-top:1px solid var(--border);border-left:1px solid var(--border)}
.strip .cell:nth-child(-n+3){border-top:0}
.strip .cell:nth-child(3n+1){border-left:0}
.strip .v{font-size:22px;font-weight:600;letter-spacing:-.3px}
.strip .l{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--text-3);margin-top:4px}
.strip .p{font-size:12.5px;color:var(--text-2);margin-top:6px}
sup.fn{font-family:var(--mono);font-size:10px;color:var(--blue);margin-left:2px}
table.ds{width:100%;border-collapse:collapse;font-size:14px}
table.ds th,table.ds td{text-align:left;padding:9px 12px;border:1px solid var(--border);vertical-align:top}
table.ds th{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--text-3);background:var(--bg-alt);font-weight:500}
table.ds td.mono,table.ds code{font-family:var(--mono);font-size:12.5px}
.copyrow{display:flex;align-items:center;gap:8px}
.copybtn{font-family:var(--mono);font-size:11px;border:1px solid var(--border);background:#fff;padding:2px 8px;cursor:pointer;color:var(--text-2)}
.copybtn:hover{border-color:var(--blue);color:var(--blue)}
.limits li{list-style:none;border:1px solid var(--border);border-left:3px solid var(--amber);padding:12px 16px;margin:10px 0;font-size:14.5px;color:var(--text-2)}
.figwrap{margin:22px 0 8px}.figwrap img,.figwrap video{display:block;width:100%;height:auto;border:1px solid var(--border)}
.subst{font-size:12.5px;color:var(--text-3);margin-top:8px}
.subst li{list-style:none;margin:5px 0;padding-left:20px;text-indent:-20px}
.subst .fnid{font-family:var(--mono);color:var(--blue);margin-right:6px}
.verify{background:var(--bg-alt);border:1px solid var(--border);padding:24px;margin-top:8px}
.verify .runline{font-family:var(--mono);font-size:13px;background:#161616;color:#9ef0a0;padding:12px 16px;margin:12px 0;overflow-x:auto;white-space:pre}
.cta{margin:40px 0 56px;background:var(--blue);color:#fff;padding:32px 28px}
.cta h2{color:#fff;border:0}.cta p{color:#d0e2ff;font-size:15px;max-width:44em;margin:6px 0 16px}
.btn-w{background:#fff;color:var(--blue)}.btn-wo{background:transparent;color:#fff;border-color:#fff}
footer{border-top:1px solid var(--border);padding:18px 0 26px;font-size:13px;color:var(--text-3)}
footer a{color:var(--blue);text-decoration:none}
/* die stack (filled in Task 4) */
.die{position:relative;margin:8px 0}
.die-svg{width:100%;height:auto;display:block}
.die-3d{display:none}
.die-panel{border:1px solid var(--border);border-left:3px solid var(--blue);padding:14px 18px;margin-top:12px;font-size:14px;color:var(--text-2);min-height:64px}
.die-panel h4{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--blue);margin-bottom:6px}
/* schematic (filled in Task 5) */
.schem{width:100%;height:auto;display:block;border:1px solid var(--border)}
@media (max-width:760px){.pair{grid-template-columns:1fr}.pair>div+div{border-left:0;border-top:1px solid var(--border)}.strip{grid-template-columns:1fr}.strip .cell{border-left:0!important;border-top:1px solid var(--border)!important}.strip .cell:first-child{border-top:0!important}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media print{header.nav,.cta,.copybtn{display:none}.die-3d{display:none!important}.die-svg{display:block!important}section{break-inside:avoid}}
```

- [ ] **Step 5: Create the inline JS partial**

Create `site-datasheets/partials/page.js` — motion-swap (copied from the existing page) + copy-to-clipboard; die-stack rotation JS is appended in Task 4:

```javascript
// motion upgrade: poster image swaps to its silent looping video when visible
document.querySelectorAll('img[data-video]').forEach(function(img){
  var io=new IntersectionObserver(function(es){es.forEach(function(e){
    if(!e.isIntersecting)return;io.unobserve(img);
    var v=document.createElement('video');
    v.muted=true;v.defaultMuted=true;v.loop=true;v.autoplay=true;v.playsInline=true;
    v.setAttribute('muted','');v.setAttribute('playsinline','');v.setAttribute('autoplay','');v.setAttribute('loop','');v.setAttribute('preload','auto');
    v.poster=img.currentSrc||img.src;v.src=img.getAttribute('data-video');
    v.setAttribute('role','img');v.setAttribute('aria-label',img.alt);
    v.style.width='100%';v.style.height='auto';v.style.display='block';v.style.border='1px solid #e0e0e0';
    img.replaceWith(v);var p=v.play();if(p&&p.catch)p.catch(function(){});
  });},{rootMargin:'120px'});
  io.observe(img);
});
// copy-to-clipboard for instruction rows
document.querySelectorAll('.copybtn').forEach(function(b){
  b.addEventListener('click',function(){
    var t=b.getAttribute('data-copy')||'';
    if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){
      var old=b.textContent;b.textContent='copied';setTimeout(function(){b.textContent=old;},1200);
    }).catch(function(){});}
  });
});
```

- [ ] **Step 6: Create the shell template**

Create `site-datasheets/templates/datasheet.html.tmpl` (a `string.Template` with `$name` slots; note literal `$` in any CSS/JS is not present because CSS/JS are injected via `$css`/`$js` slots, not written inline here):

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<meta name="description" content="$description">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
$css
</style>
</head>
<body>
<header class="nav"><div class="wrap nav-in">
  <a class="brand" href="/" aria-label="Sophon Finance Systems — home">
    <svg class="brand-mark" viewBox="0 0 48 48" aria-hidden="true"><path d="M10 30 L19 21 L27 26 L38 14" fill="none" stroke="#0f62fe" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="38" cy="14" r="3" fill="#0f62fe"/><rect x="10" y="35" width="28" height="3" fill="#161616"/></svg>
    <span class="brand-word">Sophon <span>Finance Systems</span></span>
  </a>
  <a class="backlink" href="/#engines">&larr; All engines</a>
  <a class="btn btn-p" href="$cta_book" style="padding:10px 14px;min-height:40px;font-size:14px">Book a consultation</a>
</div></header>
<main class="wrap">
$masthead
$die_stack
$spec_strip
$plain_terms
$schematic
$instruction_set
$benchmarks
$control_characteristics
$limits
$see_it_run
$integration
</main>
<footer><div class="wrap">&copy; 2026 Sophon Finance Systems &nbsp;&middot;&nbsp; <a href="/">sophonfinance.com</a> &nbsp;&middot;&nbsp; <a href="$link_source" target="_blank" rel="noopener">GitHub</a> &nbsp;&middot;&nbsp; All public examples use fictional, seeded data.</div></footer>
<script>
$js
</script>
</body>
</html>
```

- [ ] **Step 7: Write the generator**

Create `site-datasheets/generate_datasheets.py`. This is the core; each zone is a helper returning an HTML string, mirroring the atlas `_chips_html()` pattern. `die_stack_html` and `schematic_html` are stubs here (replaced in Tasks 4–5). Footnote numbering is centralized so zones 3 and 7 share one Substantiation list.

```python
#!/usr/bin/env python
"""Render one engine datasheet page from its JSON spec. Stdlib only, deterministic."""
from __future__ import annotations

import argparse
import html
from pathlib import Path
from string import Template

import datasheet_spec as ds

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT_DIR = REPO / "docs" / "engines"
TEMPLATES = ROOT / "templates"
PARTIALS = ROOT / "partials"

CTA_BOOK = "/#book"


def _esc(value) -> str:
    return html.escape(str(value))


class Footnotes:
    """Collects (source) markers so zones 3 and 7 share one Substantiation list."""

    def __init__(self) -> None:
        self._items: list[str] = []

    def mark(self, source: str) -> str:
        self._items.append(source)
        return '<sup class="fn">%d</sup>' % len(self._items)

    def render(self) -> str:
        if not self._items:
            return ""
        rows = [
            '    <li><span class="fnid">%d</span>%s</li>' % (i + 1, _esc(s))
            for i, s in enumerate(self._items)
        ]
        return ('<div class="subst"><span class="zone-k">Substantiation</span><ul>\n'
                + "\n".join(rows) + "\n</ul></div>")


# --- zone builders ---------------------------------------------------------

def masthead_html(spec: dict) -> str:
    part = "%s &middot; %s &middot; REV %s &middot; %s" % (
        _esc(spec["part_no"]), _esc(spec["family"].upper()),
        _esc(spec["rev"]), _esc(spec["status"]))
    legend = ("PRODUCTION = runnable end-to-end, CI-backed, full test suite passing. "
              "All data fictional and seeded.")
    thesis = _esc(spec.get("marketing_thesis", ""))
    thesis_html = ('  <p class="thesis">%s</p>\n' % thesis) if thesis else ""
    return (
        '<section class="masthead">\n'
        '  <p class="kicker">ENGINE %02d</p>\n'
        '  <p class="partline">%s</p>\n'
        '  <p class="legend">%s</p>\n'
        '  <h1><strong>%s</strong></h1>\n'
        '  <p class="tag">%s</p>\n'
        '  <p class="intro">%s</p>\n'
        '%s'
        '  <p><a class="btn btn-p" href="%s" target="_blank" rel="noopener">Run it</a> '
        '<a class="btn btn-t" href="%s">Book a consultation</a></p>\n'
        '</section>'
    ) % (spec["num"], part, _esc(legend), _esc(spec["name"]),
         _esc(spec["tagline"]), _esc(spec["plain_summary"]), thesis_html,
         _esc(spec["links"]["codespaces"]), CTA_BOOK)


def spec_strip_html(spec: dict, fn: Footnotes) -> str:
    cells = []
    for item in spec["spec_strip"]:
        plain = ('<div class="p">%s</div>' % _esc(item["plain"])) if item.get("plain") else ""
        cells.append(
            '  <div class="cell"><div class="v">%s%s</div>'
            '<div class="l">%s</div>%s</div>'
            % (_esc(item["value"]), fn.mark(item["source"]), _esc(item["label"]), plain))
    return ('<section><h2>Key specifications</h2>'
            '<span class="zone-k">at a glance</span>\n'
            '<div class="strip">\n' + "\n".join(cells) + "\n</div></section>")


def plain_terms_html(spec: dict) -> str:
    scen = []
    for s in spec["scenarios"]:
        scen.append('  <p style="margin:10px 0"><b>%s.</b> %s</p>'
                    % (_esc(s["title"]), _esc(s["narrative"])))
    return ('<section><h2>What it does for you</h2>'
            '<span class="zone-k">plain terms</span>\n'
            '  <p class="intro">%s</p>\n%s\n</section>'
            % (_esc(spec["problem_statement"]), "\n".join(scen)))


def instruction_set_html(spec: dict) -> str:
    rows = []
    for op in spec["instruction_set"]:
        cmd = _esc(op["cmd"])
        rows.append(
            '  <tr><td class="mono"><div class="copyrow"><code>%s</code>'
            '<button class="copybtn" data-copy="%s" aria-label="Copy command">copy</button></div></td>'
            '<td>%s</td><td class="mono">%s</td><td class="mono">%s</td><td>%s</td></tr>'
            % (cmd, cmd, _esc(op["operation"]), _esc(op["output"]),
               _esc(op["exit_code"]), _esc(op["artifacts"])))
    return ('<section><h2>Instruction set</h2>'
            '<span class="zone-k">every public command</span>\n'
            '<table class="ds"><thead><tr><th>Command</th><th>Operation</th>'
            '<th>Output</th><th>Exit</th><th>Artifacts</th></tr></thead>\n'
            '<tbody>\n' + "\n".join(rows) + "\n</tbody></table></section>")


def benchmarks_html(spec: dict, fn: Footnotes) -> str:
    rows = []
    for b in spec["benchmarks"]:
        plain = ('<br><span style="color:#6f6f6f;font-size:12.5px">%s</span>'
                 % _esc(b["plain"])) if b.get("plain") else ""
        rows.append('  <tr><td>%s%s</td><td class="mono"><b>%s</b> %s</td></tr>'
                    % (_esc(b["label"]), fn.mark(b["source"]),
                       _esc(b["value"]), _esc(b["unit"]) + plain))
    return ('<section><h2>Benchmarks</h2>'
            '<span class="zone-k">measured demo results</span>\n'
            '<table class="ds"><thead><tr><th>Measure</th><th>Result</th></tr></thead>\n'
            '<tbody>\n' + "\n".join(rows) + "\n</tbody></table></section>")


def control_characteristics_html(spec: dict) -> str:
    cc = spec["control_characteristics"]
    auth = "".join('<tr><td class="mono">%d</td><td><b>%s</b></td><td>%s</td></tr>'
                   % (a["rank"], _esc(a["level"]), _esc(a["note"])) for a in cc["authority"])
    vmap = "".join('<tr><td>%s</td><td class="mono"><b>%s</b></td><td>%s</td></tr>'
                   % (_esc(v["severity"]), _esc(v["verdict"]), _esc(v["action"]))
                   for v in cc["verdict_map"])
    guarantees = "".join('<li style="list-style:disc;margin-left:18px">%s</li>' % _esc(g)
                         for g in cc["guarantees"])
    modes = "".join('<p style="margin:8px 0"><b>%s.</b> %s</p>'
                    % (_esc(m["name"]), _esc(m["detail"])) for m in cc["modes"])
    return (
        '<section><h2>Control characteristics</h2>'
        '<span class="zone-k">engineering</span>\n'
        '<table class="ds"><thead><tr><th>Authority</th><th>Level</th><th>Note</th></tr></thead>'
        '<tbody>%s</tbody></table>\n'
        '<table class="ds" style="margin-top:14px"><thead><tr><th>Severity</th><th>Verdict</th><th>Action</th></tr></thead>'
        '<tbody>%s</tbody></table>\n'
        '<ul style="margin-top:14px">%s</ul>\n%s</section>'
    ) % (auth, vmap, guarantees, modes)


def limits_html(spec: dict, fn: Footnotes) -> str:
    items = "".join('<li>%s%s</li>' % (_esc(l["statement"]), fn.mark(l["source"]))
                    for l in spec["limits"])
    return ('<section><h2>Operating limits</h2>'
            '<span class="zone-k">what it refuses to do</span>\n'
            '<ul class="limits">%s</ul></section>' % items)


def see_it_run_html(spec: dict) -> str:
    m = spec["media"]
    return (
        '<section><h2>See it run</h2><span class="zone-k">the real CLI</span>\n'
        '<figure class="figwrap"><img src="%s" data-video="%s" '
        'alt="Screencast of the Triangulate CLI running on fictional seeded data" '
        'loading="lazy"></figure></section>'
    ) % (_esc(m["poster"]), _esc(m["motion"]))


def integration_html(spec: dict, fn: Footnotes) -> str:
    links = spec["links"]
    qs = "".join('<div class="runline">%s</div>' % _esc(q["command"])
                 for q in spec.get("quickstart", []))
    return (
        '<section><h2>Integration</h2><span class="zone-k">how to run it</span>\n'
        '<p class="intro">Distribution: public repository, MIT license.</p>\n'
        '<div class="verify">\n%s'
        '  <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px">\n'
        '    <a class="btn btn-t" href="%s" target="_blank" rel="noopener">Source on GitHub</a>\n'
        '    <a class="btn btn-t" href="%s" target="_blank" rel="noopener">Engine README</a>\n'
        '    <a class="btn btn-t" href="%s">All tests, by engine</a>\n'
        '    <a class="btn btn-t" href="%s" target="_blank" rel="noopener">Run in Codespaces</a>\n'
        '  </div>\n</div>\n'
        '%s\n'
        '<div class="cta"><h2>Show us where the hours go.</h2>'
        '<p>One conversation: you describe the work that consumes your team\'s month; '
        'we tell you plainly what this engine can take over, what it can\'t, and what a '
        'scoped first phase would cost. Your people keep approval authority.</p>'
        '<a class="btn btn-w" href="%s">Book a free consultation</a></div>\n'
        '</section>'
    ) % (qs, _esc(links["source"]), _esc(links["readme"]), _esc(links["tests"]),
         _esc(links["codespaces"]), fn.render(), CTA_BOOK)


# --- visual zones (STUBS — replaced in Tasks 4 and 5) ----------------------

def die_stack_html(spec: dict) -> str:
    return ('<section><h2>Architecture</h2>'
            '<span class="zone-k">functional block stack</span>\n'
            '<div class="die"><!-- die stack: Task 4 --></div></section>')


def schematic_html(spec: dict) -> str:
    return ('<section><h2>Functional block diagram</h2>'
            '<span class="zone-k">engineering</span>\n'
            '<div><!-- schematic: Task 5 --></div></section>')


# --- assembly --------------------------------------------------------------

def render(slug: str) -> str:
    spec = ds.load_spec(slug)
    problems = ds.validate_spec(spec)
    if problems:
        raise ValueError("invalid spec %r: %s" % (slug, "; ".join(problems)))
    fn = Footnotes()
    css = (PARTIALS / "page.css").read_text(encoding="utf-8")
    js = (PARTIALS / "page.js").read_text(encoding="utf-8")
    shell = Template((TEMPLATES / "datasheet.html.tmpl").read_text(encoding="utf-8"))
    # Order matters: spec_strip (zone 3) then benchmarks (zone 7) then limits (zone 9)
    # all feed `fn`; integration renders fn.render() last.
    ms = masthead_html(spec)
    dk = die_stack_html(spec)
    ss = spec_strip_html(spec, fn)
    pt = plain_terms_html(spec)
    sc = schematic_html(spec)
    ins = instruction_set_html(spec)
    bm = benchmarks_html(spec, fn)
    ctrl = control_characteristics_html(spec)
    lim = limits_html(spec, fn)
    sir = see_it_run_html(spec)
    integ = integration_html(spec, fn)
    return shell.substitute(
        title="%s — Sophon Finance Systems" % spec["name"],
        description=spec["meta"]["description"],
        css=css, js=js,
        cta_book=CTA_BOOK,
        link_source=spec["links"]["source"],
        masthead=ms, die_stack=dk, spec_strip=ss, plain_terms=pt, schematic=sc,
        instruction_set=ins, benchmarks=bm, control_characteristics=ctrl,
        limits=lim, see_it_run=sir, integration=integ,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate an engine datasheet page.")
    parser.add_argument("--slug", default="triangulate")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    out = args.out or (OUT_DIR / ("%s.html" % args.slug))
    out.parent.mkdir(parents=True, exist_ok=True)
    document = render(args.slug)
    out.write_bytes(document.encode("utf-8"))
    print("datasheet: %s (%d bytes) -> %s" % (args.slug, len(document.encode("utf-8")), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: Run the generator once and the tests**

Run: `cd site-datasheets && py -3 generate_datasheets.py --slug triangulate --out /tmp/t.html && py -3 -m pytest datasheet_tests/test_generator.py -v`
Expected: all pass EXCEPT `test_committed_page_is_fresh` (xfail, until Task 11). Fix any `KeyError`/`substitute` mismatch until green.

- [ ] **Step 9: Commit**

```bash
git add site-datasheets/generate_datasheets.py site-datasheets/templates \
        site-datasheets/partials site-datasheets/datasheet_tests/test_generator.py \
        site-datasheets/datasheet_tests/conftest.py
git commit -m "feat(datasheets): generator core + template + text/tabular zones"
```

---

## Task 4: Interactive die stack (zone 2)

Replaces `die_stack_html` with a builder that emits BOTH a static isometric SVG (default, fallback) and CSS-3D markup from the same `layers[]` array, plus focusable layer buttons and an info panel. Appends rotation JS to `page.js`.

**Files:**
- Modify: `site-datasheets/generate_datasheets.py` (replace `die_stack_html`)
- Modify: `site-datasheets/partials/page.js` (append rotation + panel JS)
- Modify: `site-datasheets/partials/page.css` (add `.die-3d` 3D rules)
- Test: `site-datasheets/datasheet_tests/test_die_stack.py`

**Interfaces:**
- Consumes: `spec["layers"]` (list of `{id,label,plain,engineering,source_link}`).
- Produces: `die_stack_html(spec)` emitting one `<section>` containing `svg.die-svg` (static, `layers` count `<g class="die-layer">`), a `div.die-3d` with one focusable `button.die-face` per layer (DOM order = `layers[]` order), and a `div.die-panel` info region.

- [ ] **Step 1: Write the failing die-stack test**

Create `site-datasheets/datasheet_tests/test_die_stack.py`:

```python
"""Zone 2: die stack renders both representations and one focusable button per layer."""
from __future__ import annotations

import re

import generate_datasheets as gen
import datasheet_spec as ds


def test_static_svg_has_one_layer_group_per_layer():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    assert 'class="die-svg"' in html
    groups = html.count('class="die-layer"')
    assert groups == len(spec["layers"]), (groups, len(spec["layers"]))


def test_each_layer_has_a_focusable_button_in_dom_order():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    buttons = re.findall(r'<button class="die-face"[^>]*data-layer="([^"]+)"', html)
    assert buttons == [layer["id"] for layer in spec["layers"]]


def test_both_representations_present():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    assert 'class="die-svg"' in html   # static fallback
    assert 'class="die-3d"' in html    # interactive
    assert 'class="die-panel"' in html # info panel


def test_layer_copy_carries_source_links():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    for layer in spec["layers"]:
        assert layer["source_link"] in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_die_stack.py -v`
Expected: FAIL — stub emits no `die-svg`/`die-face`.

- [ ] **Step 3: Replace `die_stack_html` in the generator**

In `site-datasheets/generate_datasheets.py`, replace the stub `die_stack_html` with:

```python
def die_stack_html(spec: dict) -> str:
    layers = spec["layers"]
    n = len(layers)
    # Static isometric SVG: stacked parallelograms, top layer first.
    box_w, box_h, skew, gap = 320, 46, 60, 14
    total_h = n * (box_h + gap) + skew + 40
    svg_layers = []
    faces = []
    for i, layer in enumerate(layers):
        y = 20 + i * (box_h + gap)
        pts = "%d,%d %d,%d %d,%d %d,%d" % (
            skew, y + skew, skew + box_w, y + skew,
            skew + box_w + 0, y, 0 + skew + 0, y)  # simple iso top face
        # Draw an isometric slab: top parallelogram + front + side.
        top = "%d,%d %d,%d %d,%d %d,%d" % (
            80, y, 80 + box_w, y, box_w + 40, y + 22, 40, y + 22)
        front = "40,%d %d,%d %d,%d 40,%d" % (
            y + 22, box_w + 40, y + 22, box_w + 40, y + 22 + box_h, y + 22 + box_h)
        svg_layers.append(
            '  <g class="die-layer" data-layer="%s">'
            '<polygon points="%s" fill="#edf5ff" stroke="#0f62fe" stroke-width="1.4"/>'
            '<polygon points="%s" fill="#ffffff" stroke="#0f62fe" stroke-width="1.4"/>'
            '<text x="60" y="%d" font-family="IBM Plex Mono,monospace" font-size="13" '
            'fill="#161616">%s</text></g>'
            % (_esc(layer["id"]), top, front, y + 22 + box_h // 2 + 4, _esc(layer["label"])))
        faces.append(
            '    <button class="die-face" data-layer="%s" '
            'data-plain="%s" data-eng="%s" data-src="%s" '
            'aria-label="%s layer — open detail">%s</button>'
            % (_esc(layer["id"]), _esc(layer["plain"]), _esc(layer["engineering"]),
               _esc(layer["source_link"]), _esc(layer["label"]), _esc(layer["label"])))
    svg = ('<svg class="die-svg" viewBox="0 0 %d %d" role="img" '
           'aria-label="Exploded functional block stack: %s over seeded fictional data">\n%s\n'
           '  <text x="40" y="%d" font-family="IBM Plex Mono,monospace" font-size="11" '
           'fill="#6f6f6f">substrate: seeded fictional data</text>\n</svg>'
           % (box_w + 90, total_h,
              _esc(", ".join(l["label"] for l in layers)),
              "\n".join(svg_layers), total_h - 10))
    faces_html = "\n".join(faces)
    return (
        '<section><h2>Architecture</h2>'
        '<span class="zone-k">functional block stack &middot; click a layer</span>\n'
        '<div class="die">\n%s\n'
        '  <div class="die-3d" aria-hidden="false">\n%s\n  </div>\n'
        '  <div class="die-panel" id="die-panel" role="region" aria-live="polite">'
        '<h4>Select a layer</h4><p>Each layer is an independent duty. '
        'Click any block for its plain-terms and engineering description.</p></div>\n'
        '</div></section>'
    ) % (svg, faces_html)
```

- [ ] **Step 4: Append die-stack 3D CSS**

Append to `site-datasheets/partials/page.css`:

```css
.die-3d{perspective:1200px;margin:10px 0}
.die-face{display:block;width:min(360px,80%);margin:0 auto;padding:12px 16px;border:1px solid var(--blue);background:var(--blue-tint);font-family:var(--mono);font-size:13px;color:var(--text);text-align:left;cursor:pointer;transition:transform .15s,box-shadow .15s}
.die-face+ .die-face{margin-top:8px}
.die-face:hover,.die-face:focus-visible{transform:translateX(6px);box-shadow:-4px 0 0 var(--blue);outline:none}
.die-face[aria-pressed="true"]{background:var(--blue);color:#fff}
.js-3d .die-svg{display:none}
.js-3d .die-3d{display:block}
```

- [ ] **Step 5: Append rotation + panel JS**

Append to `site-datasheets/partials/page.js`:

```javascript
// die stack: enable interactive representation only when JS is available
(function(){
  var die=document.querySelector('.die');
  if(!die)return;
  var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  if(reduce)return; // keep the static SVG for reduced-motion users
  document.documentElement.classList.add('js-3d');
  var panel=document.getElementById('die-panel');
  die.querySelectorAll('.die-face').forEach(function(btn){
    btn.setAttribute('aria-pressed','false');
    function open(){
      die.querySelectorAll('.die-face').forEach(function(b){b.setAttribute('aria-pressed','false');});
      btn.setAttribute('aria-pressed','true');
      var src=btn.getAttribute('data-src');
      panel.innerHTML='<h4>'+btn.textContent+'</h4>'+
        '<p><b>Plain terms.</b> '+btn.getAttribute('data-plain')+'</p>'+
        '<p><b>Engineering.</b> '+btn.getAttribute('data-eng')+'</p>'+
        '<p><a href="'+src+'" target="_blank" rel="noopener">Source on GitHub</a></p>';
    }
    btn.addEventListener('click',open);
    btn.addEventListener('keydown',function(e){
      if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}
      if(e.key==='Escape'){btn.setAttribute('aria-pressed','false');}
    });
  });
})();
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_die_stack.py datasheet_tests/test_generator.py -v`
Expected: die-stack tests PASS; generator determinism still PASS (committed-fresh still xfail).

- [ ] **Step 7: Commit**

```bash
git add site-datasheets/generate_datasheets.py site-datasheets/partials \
        site-datasheets/datasheet_tests/test_die_stack.py
git commit -m "feat(datasheets): interactive die stack (static SVG + CSS-3D, a11y)"
```

---

## Task 5: CAD-style functional block schematic (zone 5)

Replaces `schematic_html` with a builder that lays out `blocks[]` on the `col`/`row` grid, draws `edges[]` as connectors with labels, marks gate edges, links each block to its source, and animates signal traces via CSS `stroke-dashoffset`.

**Files:**
- Modify: `site-datasheets/generate_datasheets.py` (replace `schematic_html`)
- Modify: `site-datasheets/partials/page.css` (add trace animation)
- Test: `site-datasheets/datasheet_tests/test_schematic.py`

**Interfaces:**
- Consumes: `spec["blocks"]` (`{id,label,kind?,plain?,engineering?,source_link,col,row}`) and `spec["edges"]` (`{from,to,label?,gate?}`).
- Produces: `schematic_html(spec)` emitting an `svg.schem` with one `<g class="schem-block" data-block="ID">` per block and one `<g class="schem-edge">` per edge; gate edges carry `class="schem-edge gate"`.

- [ ] **Step 1: Write the failing schematic test**

Create `site-datasheets/datasheet_tests/test_schematic.py`:

```python
"""Zone 5: schematic renders one node per block and one connector per edge."""
from __future__ import annotations

import generate_datasheets as gen
import datasheet_spec as ds


def test_one_node_per_block():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    for block in spec["blocks"]:
        assert 'data-block="%s"' % block["id"] in html


def test_one_edge_group_per_edge():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    assert html.count("schem-edge") >= len(spec["edges"])


def test_gate_edge_is_marked():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    if any(e.get("gate") for e in spec["edges"]):
        assert "schem-edge gate" in html


def test_blocks_link_to_source():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    for block in spec["blocks"]:
        assert block["source_link"] in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_schematic.py -v`
Expected: FAIL — stub emits no `data-block`.

- [ ] **Step 3: Replace `schematic_html` in the generator**

In `site-datasheets/generate_datasheets.py`, replace the stub `schematic_html` with:

```python
def schematic_html(spec: dict) -> str:
    blocks = spec["blocks"]
    edges = spec["edges"]
    by_id = {b["id"]: b for b in blocks}
    cols = max(b["col"] for b in blocks) + 1
    rows = max(b["row"] for b in blocks) + 1
    cw, ch, pad = 170, 74, 30
    gx, gy = cw + 70, ch + 40
    width = pad * 2 + (cols - 1) * gx + cw
    height = pad * 2 + (rows - 1) * gy + ch + 40  # title-block room

    def cx(b): return pad + b["col"] * gx
    def cy(b): return pad + b["row"] * gy

    edge_svg = []
    for e in edges:
        a, b = by_id[e["from"]], by_id[e["to"]]
        x1, y1 = cx(a) + cw, cy(a) + ch // 2
        x2, y2 = cx(b), cy(b) + ch // 2
        cls = "schem-edge gate" if e.get("gate") else "schem-edge"
        mx = (x1 + x2) // 2
        path = "M%d,%d C%d,%d %d,%d %d,%d" % (x1, y1, mx, y1, mx, y2, x2, y2)
        label = ('<text x="%d" y="%d" font-family="IBM Plex Mono,monospace" '
                 'font-size="10" fill="#6f6f6f" text-anchor="middle">%s</text>'
                 % (mx, min(y1, y2) - 6, _esc(e["label"]))) if e.get("label") else ""
        edge_svg.append(
            '  <g class="%s"><path d="%s" fill="none" stroke="#0f62fe" '
            'stroke-width="1.6" marker-end="url(#arrow)"/>%s</g>' % (cls, path, label))

    kind_fill = {"role": "#ffffff", "audit": "#edf5ff", "gate": "#edf5ff",
                 "human": "#e6f4ea"}
    block_svg = []
    for b in blocks:
        x, y = cx(b), cy(b)
        fill = kind_fill.get(b.get("kind", ""), "#ffffff")
        block_svg.append(
            '  <g class="schem-block" data-block="%s">'
            '<a href="%s" target="_blank" rel="noopener">'
            '<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="%s" '
            'stroke="#0f62fe" stroke-width="1.6"/>'
            '<text x="%d" y="%d" font-family="IBM Plex Sans,sans-serif" font-size="13" '
            'font-weight="600" fill="#161616" text-anchor="middle">%s</text></a></g>'
            % (_esc(b["id"]), _esc(b["source_link"]), x, y, cw, ch, fill,
               x + cw // 2, y + ch // 2 + 4, _esc(b["label"])))

    title_block = (
        '  <g class="schem-title">'
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#c6c6c6" stroke-width="1"/>'
        '<text x="%d" y="%d" font-family="IBM Plex Mono,monospace" font-size="10" '
        'fill="#6f6f6f">%s &middot; FUNCTIONAL BLOCK DIAGRAM &middot; REV %s</text></g>'
        % (pad, height - 26, width - pad, height - 26, pad, height - 12,
           _esc(spec["part_no"]), _esc(spec["rev"])))

    svg = (
        '<svg class="schem" viewBox="0 0 %d %d" role="img" '
        'aria-label="Functional block diagram of the %s engine">\n'
        '  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#0f62fe"/></marker></defs>\n'
        '%s\n%s\n%s\n</svg>'
    ) % (width, height, _esc(spec["name"]),
         "\n".join(edge_svg), "\n".join(block_svg), title_block)

    return ('<section><h2>Functional block diagram</h2>'
            '<span class="zone-k">engineering &middot; each block links to its source</span>\n'
            '%s</section>' % svg)
```

- [ ] **Step 4: Add trace animation CSS**

Append to `site-datasheets/partials/page.css`:

```css
.schem-edge path{stroke-dasharray:6 6;animation:flow 1.6s linear infinite}
.schem-edge.gate path{stroke-dasharray:none;stroke-width:2.2}
@keyframes flow{to{stroke-dashoffset:-12}}
@media (prefers-reduced-motion:reduce){.schem-edge path{animation:none;stroke-dasharray:none}}
.schem-block rect{transition:fill .15s}
.schem-block:hover rect{fill:var(--blue-tint)}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_schematic.py datasheet_tests/test_generator.py -v`
Expected: schematic tests PASS; determinism PASS (committed-fresh still xfail).

- [ ] **Step 6: Commit**

```bash
git add site-datasheets/generate_datasheets.py site-datasheets/partials/page.css \
        site-datasheets/datasheet_tests/test_schematic.py
git commit -m "feat(datasheets): CAD-style functional block schematic (zone 5)"
```

---

## Task 6: Roster authority (BRAND-VOICE roster) + H1-vs-roster test

Updates `docs/BRAND-VOICE.md` so its canonical roster names all nine site engines, then asserts the generated page's H1 against that single authority.

**Files:**
- Modify: `docs/BRAND-VOICE.md` (canonical names line)
- Modify: `site-datasheets/datasheet_tests/test_roster.py` (add H1-vs-roster test)

**Interfaces:**
- Consumes: `gen.render("triangulate")`, `docs/BRAND-VOICE.md`.
- Produces: an assertion tying page H1 → BRAND-VOICE roster.

- [ ] **Step 1: Write the failing H1-vs-roster test**

Append to `site-datasheets/datasheet_tests/test_roster.py`:

```python
from pathlib import Path

import generate_datasheets as gen

BRAND_VOICE = gen.REPO / "docs" / "BRAND-VOICE.md"

NINE_NAMES = (
    "Month-End Close", "Cash & Debt Reconciliation", "Partnership 1065 Automation",
    "Validation Engine", "Tax Surplus / ACB", "Triangulate", "Knowledge Brain",
    "Finance Operations Atlas", "Cash Management",
)


def test_brand_voice_lists_all_nine_engine_names():
    text = BRAND_VOICE.read_text(encoding="utf-8")
    for name in NINE_NAMES:
        assert name in text, f"BRAND-VOICE.md missing canonical name: {name}"


def test_page_h1_is_in_brand_voice_roster():
    html = gen.render("triangulate")
    # H1 strong text is the canonical name
    assert "<h1><strong>Triangulate</strong></h1>" in html
    text = BRAND_VOICE.read_text(encoding="utf-8")
    assert "Triangulate" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_roster.py -v`
Expected: FAIL — BRAND-VOICE.md currently names only seven engines (missing "Finance Operations Atlas", "Cash Management", "Validation Engine" as canonical list members, and uses "Partnership 1065 Automation").

- [ ] **Step 3: Update the canonical roster in BRAND-VOICE.md**

In `docs/BRAND-VOICE.md`, replace the "Use the canonical system names consistently:" line (currently seven names) with all nine site names:

```markdown
- Use the canonical system names consistently: Month-End Close, Cash & Debt Reconciliation,
  Partnership 1065 Automation, Validation Engine, Tax Surplus / ACB, Triangulate,
  Knowledge Brain, Finance Operations Atlas, Cash Management.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_roster.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/BRAND-VOICE.md site-datasheets/datasheet_tests/test_roster.py
git commit -m "docs(brand-voice): canonical roster to nine site engines + H1 authority test"
```

---

## Task 7: Page-engineering guards — size budget + link/asset existence

**Files:**
- Test: `site-datasheets/datasheet_tests/test_page_budget.py`

**Interfaces:**
- Consumes: `gen.render`, `gen.REPO`, `spec["media"]`, `spec["links"]`.

- [ ] **Step 1: Write the failing budget/asset test**

Create `site-datasheets/datasheet_tests/test_page_budget.py`:

```python
"""Page engineering: size budget and that every local asset/link path exists."""
from __future__ import annotations

import re
from pathlib import Path

import generate_datasheets as gen
import datasheet_spec as ds

MAX_BYTES = 150 * 1024


def test_page_within_size_budget():
    size = len(gen.render("triangulate").encode("utf-8"))
    assert size <= MAX_BYTES, f"{size} bytes exceeds {MAX_BYTES}"


def test_media_assets_exist_on_disk():
    spec = ds.load_spec("triangulate")
    docs_engines = gen.OUT_DIR  # docs/engines
    for key in ("poster", "motion"):
        rel = spec["media"][key]  # e.g. ../assets/tile-triangulate.webp
        resolved = (docs_engines / rel).resolve()
        assert resolved.is_file(), f"missing media asset: {rel} -> {resolved}"


def test_internal_tests_link_route_exists():
    # links.tests points at /tests/ — the docs/tests/ directory must exist
    spec = ds.load_spec("triangulate")
    assert spec["links"]["tests"] == "/tests/"
    assert (gen.REPO / "docs" / "tests").is_dir()
```

- [ ] **Step 2: Run the test to verify it fails or passes**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_page_budget.py -v`
Expected: PASS if assets resolve and page is under budget. If `docs/tests` does not exist as a directory, adjust the assertion to check for `docs/tests.html` or the actual route the live site uses (verify with `ls docs/ | grep -i test`); keep the test asserting the real route.

- [ ] **Step 3: Commit**

```bash
git add site-datasheets/datasheet_tests/test_page_budget.py
git commit -m "test(datasheets): page size budget + asset/link existence guards"
```

---

## Task 8: Voice lint + confidentiality deny-list over the generated page

**Files:**
- Create: `site-datasheets/datasheet_tests/voice_lint_terms.txt`
- Test: `site-datasheets/datasheet_tests/test_voice_lint.py`
- Test: `site-datasheets/datasheet_tests/test_deny_list.py`

**Interfaces:**
- Consumes: `gen.render("triangulate")`, `finance-atlas/atlas_tests/test_deny_list.py` (reuse the digest machinery by import).

- [ ] **Step 1: Create the banned-phrase list**

Create `site-datasheets/datasheet_tests/voice_lint_terms.txt` (seeded from BRAND-VOICE.md "What we do not say"; one term per line, lowercase):

```
slide deck
vibes
marks its own homework
press play
wow moment
command center
game-changer
game changer
hands-free
```

- [ ] **Step 2: Write the failing voice-lint test**

Create `site-datasheets/datasheet_tests/test_voice_lint.py`:

```python
"""Voice lint: banned phrases absent; no '!' in body copy; orchestration framing."""
from __future__ import annotations

import re
from pathlib import Path

import generate_datasheets as gen

TERMS_FILE = Path(__file__).resolve().parent / "voice_lint_terms.txt"
ORCH = ("an optional orchestration layer for approved, agent-enabled environments; "
        "the platform runs fully without it")


def _terms():
    return [t.strip().lower() for t in TERMS_FILE.read_text(encoding="utf-8").splitlines()
            if t.strip()]


def test_no_banned_phrases():
    body = gen.render("triangulate").lower()
    for term in _terms():
        assert term not in body, f"banned phrase present: {term!r}"


def test_no_exclamation_in_body_copy():
    html = gen.render("triangulate")
    # strip <pre>/<code> CLI samples where "!" would be legitimate
    stripped = re.sub(r"<code>.*?</code>", "", html, flags=re.S)
    stripped = re.sub(r"<pre>.*?</pre>", "", stripped, flags=re.S)
    assert "!" not in stripped


def test_orchestration_framing_is_verbatim_when_agent_mode_present():
    html = gen.render("triangulate")
    if "agent-enabled" in html or "agent-accelerated" in html.lower():
        assert ORCH in html, "agent mode described without the verbatim orchestration sentence"


def test_no_hands_free_claim():
    assert "hands-free" not in gen.render("triangulate").lower()
```

- [ ] **Step 3: Run the test; fix copy if needed**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_voice_lint.py -v`
Expected: PASS. If `test_orchestration_framing...` fails, the Triangulate spec's agent-mode `detail` already contains the verbatim sentence (Task 2) — confirm it is rendered intact (no HTML-escaping of the semicolon breaks the substring; `html.escape` leaves `;` and words intact, so the check holds).

- [ ] **Step 4: Write the deny-list test (reuse atlas machinery)**

Create `site-datasheets/datasheet_tests/test_deny_list.py`:

```python
"""Confidentiality sweep over the generated datasheet page (atlas digest machinery)."""
from __future__ import annotations

import sys
from pathlib import Path

import generate_datasheets as gen

# Reuse the atlas deny-list digests + n-gram matcher without duplicating them.
ATLAS_TESTS = gen.REPO / "finance-atlas" / "atlas_tests"
if str(ATLAS_TESTS) not in sys.path:
    sys.path.insert(0, str(ATLAS_TESTS))
if str(gen.REPO / "finance-atlas") not in sys.path:
    sys.path.insert(0, str(gen.REPO / "finance-atlas"))

import test_deny_list as atlas_deny  # noqa: E402


def test_generated_page_is_clean_of_denied_terms():
    page = gen.render("triangulate")
    grams = atlas_deny.ngram_digests(page)
    for digest, nwords in atlas_deny.DENYLIST:
        assert digest not in grams.get(nwords, set()), (
            f"denied term (digest {digest[:12]}...) found on the generated page"
        )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_deny_list.py -v`
Expected: PASS. If the atlas module import fails under the collision-proof naming, fall back to copying `ngram_digests` + `DENYLIST` reference via `importlib.util.spec_from_file_location` (load `test_deny_list.py` by path) — keep the digests as the single source, do not re-hash new plaintext.

- [ ] **Step 6: Commit**

```bash
git add site-datasheets/datasheet_tests/voice_lint_terms.txt \
        site-datasheets/datasheet_tests/test_voice_lint.py \
        site-datasheets/datasheet_tests/test_deny_list.py
git commit -m "test(datasheets): voice lint + confidentiality deny-list over generated page"
```

---

## Task 9: Test-count reconciliation — counts.json + claim cross-check

The spec-strip and benchmarks cite "8,320 tests" for the engine (verified 2026-07-20 via `pytest --collect-only`; the engine's own README says "1,311," which is stale — do not use it). This task pins the number to a refreshable `counts.json` so it cannot silently go stale again, and marks datasheet-tooling tests so they are excluded from the engine test-count headline.

**Files:**
- Create: `site-datasheets/counts.json`
- Test: `site-datasheets/datasheet_tests/test_counts.py`
- Modify: `site-datasheets/datasheet_tests/test_generator.py` (add `site_tooling` marker to tooling tests) — optional; primarily handled by CI deselect in Task 10.

**Interfaces:**
- Consumes: `spec["spec_strip"]`, `spec["benchmarks"]`.
- Produces: `site-datasheets/counts.json` mapping `slug -> {"tests": int}`.

- [ ] **Step 1: Capture the real engine test count**

Run: `cd ai-validation-framework && py -3 -m pytest --collect-only -q | tail -1` (bare `python` on this machine is the WindowsApps stub — use `py -3`).
Expected/confirmed 2026-07-20: `8320 tests collected`. The engine's own `README.md:8` says "1,311 tests," which is stale — the spec JSON and `counts.json` already use the verified 8,320 (fixed in Task 2). If a future re-run of this step gets a different number, treat that as current truth and update `counts.json` AND the spec's `spec_strip`/`benchmarks` values together — never let them diverge.

- [ ] **Step 2: Create counts.json**

Create `site-datasheets/counts.json` (use the number from Step 1):

```json
{
  "triangulate": { "tests": 8320 }
}
```

- [ ] **Step 3: Write the failing counts cross-check test**

Create `site-datasheets/datasheet_tests/test_counts.py`:

```python
"""The published test-count on the page matches counts.json (no stale numbers)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import generate_datasheets as gen
import datasheet_spec as ds

COUNTS = gen.ROOT / "counts.json"


def _int(text: str) -> int:
    return int(re.sub(r"[^0-9]", "", text))


def test_counts_file_present_and_nonempty():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    assert data.get("triangulate", {}).get("tests"), "counts.json missing triangulate.tests"


def test_spec_test_count_matches_counts_file():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    expected = data["triangulate"]["tests"]
    spec = ds.load_spec("triangulate")
    strip_counts = [_int(i["value"]) for i in spec["spec_strip"]
                    if i["label"].lower() == "tests"]
    bench_counts = [_int(b["value"]) for b in spec["benchmarks"]
                    if "test" in b["label"].lower()]
    assert expected in strip_counts, (expected, strip_counts)
    assert expected in bench_counts, (expected, bench_counts)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd site-datasheets && py -3 -m pytest datasheet_tests/test_counts.py -v`
Expected: PASS (a stale/missing counts file is a hard fail by construction).

- [ ] **Step 5: Commit**

```bash
git add site-datasheets/counts.json site-datasheets/datasheet_tests/test_counts.py
git commit -m "test(datasheets): pin published test-count to counts.json (no stale numbers)"
```

---

## Task 10: CI wiring + screencast capture script

Adds `site-datasheets` to CI, a regeneration drift guard, deselects tooling tests from the engine test-count headline, and adds the minimal screencast capture/encode script (the page already ships with existing tile assets, so this script is an enhancement — not a page dependency).

**Files:**
- Modify: `.github/workflows/ci.yml` (two hard-coded dir lists + drift step)
- Modify: the test-count workflow under `.github/workflows/` (deselect `site_tooling` marker)
- Create: `site-datasheets/capture/record_screencast.py`

**Interfaces:**
- Produces: a CI job that runs `datasheet_tests` and fails on generator drift; a standalone capture helper.

- [ ] **Step 1: Add site-datasheets to both CI directory lists**

In `.github/workflows/ci.yml`, append `site-datasheets` to BOTH `for dir in ...` lists (the "Install any per-package dependencies" loop and the "Run test suite across all packages" loop):

```yaml
          for dir in monthly-close-automation cash-reconciliation cash-management tax-surplus-engine partnership-1065-automation audit-automation ai-validation-framework knowledge-brain-engine finance-atlas site-datasheets; do
```

(Apply the identical edit in both loops.)

- [ ] **Step 2: Add a regeneration drift guard step**

In `.github/workflows/ci.yml`, add a step after the test loop (before the final aggregate-report step):

```yaml
      - name: Datasheet generator drift check
        shell: bash
        run: |
          # The committed page must equal a fresh render.
          python site-datasheets/generate_datasheets.py --slug triangulate
          git diff --exit-code docs/engines/triangulate.html
```

- [ ] **Step 3: Deselect tooling tests from the test-count headline**

The workflow is `.github/workflows/test-count.yml`. It runs `pytest --collect-only -q` at the **repo root** with no path filter — and the root `pyproject.toml` has no `[tool.pytest.ini_options]`/`testpaths`, so root collection recursively picks up `site-datasheets/datasheet_tests/` too. The `datasheet_tests/conftest.py` hook from Task 1 already marks every item in that package `site_tooling` at collection time (registration isn't required for `-m` to filter — it works on unregistered markers too, it just emits a cosmetic `PytestUnknownMarkWarning`). Add `-m "not site_tooling"` to both `pytest --collect-only` invocations in `test-count.yml` (the curated-suite step, line 38, and the opt-in sweep step, line 70):

```yaml
          curated=$(python -m pytest --collect-only -q -m "not site_tooling" | tail -1)
```

and

```yaml
          sweep=$(python -m pytest --collect-only -q -m "not site_tooling" | tail -1)
```

Also add a **separate** "site tooling" line to the run summary so the datasheet-tooling test count is visible without polluting the nine-engine headline — insert this right after the "By engine" table block (still inside the `{ ... } >> "$GITHUB_STEP_SUMMARY"` group in the curated-suite step):

```yaml
            echo ""
            echo "### Site tooling (excluded from the engine headline above)"
            echo ""
            echo '```'
            echo "\$ pytest --collect-only -q -m site_tooling | tail -1"
            python -m pytest --collect-only -q -m "site_tooling" | tail -1
            echo '```'
```

- [ ] **Step 4: Do NOT register the marker at root — leave root pyproject.toml untouched**

The marker is already registered package-locally in `site-datasheets/pytest.ini` (Task 1, `markers = site_tooling: ...`), which is sufficient for the `site-datasheets` package's own `cd site-datasheets && pytest` runs. **Do not add a `[tool.pytest.ini_options]` section to the root `pyproject.toml`** — six of the nine engine packages have no `pytest.ini` of their own, so their `( cd "$dir" && python -m pytest -q )` CI runs currently resolve to *no* ini file at all (pytest only treats a `pyproject.toml` as a valid ini file once it has a `[tool.pytest.ini_options]` table — root's currently doesn't). Adding that table at root would newly give every one of those six packages a discovered rootdir/config where none existed, which risks silently changing their collection/rootdir behavior in CI. That risk isn't worth silencing a cosmetic `PytestUnknownMarkWarning` on unregistered-marker use during root-level `-m "not site_tooling"` filtering — the filter works correctly on an unregistered marker; only the warning is cosmetic. Leave root `pyproject.toml` exactly as it is.

- [ ] **Step 5: Create the screencast capture script**

Create `site-datasheets/capture/record_screencast.py` — a minimal, dependency-light helper that runs the Triangulate CLI and captures its terminal output to a text/cast artifact for later encoding. It does NOT auto-encode video (that needs `ffmpeg`/`asciinema` which may be absent); it documents the encode command:

```python
#!/usr/bin/env python
"""Capture the Triangulate CLI run for the datasheet 'See it run' zone.

Runs `python -m triangulate --demo-adversarial` in the engine directory and
writes the terminal transcript to capture/out/triangulate-demo.txt. Encoding
that transcript into a webp poster + mp4 loop is a manual/vendor step (the page
ships with the existing assets/tile-triangulate.* pair until a capture is made).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "ai-validation-framework"
OUT = Path(__file__).resolve().parent / "out"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "triangulate", "--demo-adversarial"],
        cwd=str(ENGINE), capture_output=True, text=True, timeout=180,
    )
    transcript = OUT / "triangulate-demo.txt"
    transcript.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    print("captured %d bytes -> %s (exit %d)"
          % (transcript.stat().st_size, transcript, proc.returncode))
    print("To encode a poster+loop, hand the transcript to the video/CAD vendor,")
    print("or render with asciinema + agg if available:")
    print("  asciinema rec --command 'python -m triangulate --demo-adversarial' demo.cast")
    print("  agg demo.cast triangulate-demo.gif   # then encode gif -> mp4/webp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Validate the edited YAML locally, then confirm the marker filter actually works**

Run:
```bash
py -3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/workflows/test-count.yml')); print('workflows OK')"
```
(If PyYAML is unavailable, visually verify indentation matches the surrounding steps.)
Expected: `workflows OK`.

Then, from the repo root, confirm the marker filter changes the root headline count and that the excluded tests are exactly the datasheet package (root `pyproject.toml` is untouched, so expect a `PytestUnknownMarkWarning` — that's the accepted cosmetic cost from Step 4, not a failure):
```bash
py -3 -m pytest --collect-only -q | tail -1
py -3 -m pytest --collect-only -q -m "not site_tooling" | tail -1
py -3 -m pytest --collect-only -q -m "site_tooling" | tail -1
```
Expected: the third command's count equals (first count − second count), and its collected node IDs are all under `site-datasheets/datasheet_tests/`.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/test-count.yml \
        site-datasheets/capture/record_screencast.py
git commit -m "ci(datasheets): wire site-datasheets + drift guard; exclude tooling tests from headline; capture script"
```

---

## Task 11: Ship — regenerate the page in place + homepage link + full-suite green

**Files:**
- Modify: `docs/engines/triangulate.html` (regenerated)
- Modify: `docs/index.html` (Triangulate card link text → "View datasheet")
- Modify: `site-datasheets/datasheet_tests/test_generator.py` (remove the xfail on `test_committed_page_is_fresh`)

**Interfaces:**
- Consumes: everything above.
- Produces: the shipped exemplar page and a green full suite.

- [ ] **Step 1: Regenerate the committed page**

Run: `cd site-datasheets && py -3 generate_datasheets.py --slug triangulate`
Expected: writes `docs/engines/triangulate.html`; prints byte count (should be well under 150 KB).

- [ ] **Step 2: Remove the xfail guard**

In `site-datasheets/datasheet_tests/test_generator.py`, remove the `@pytest.mark.xfail(...)` decorator from `test_committed_page_is_fresh` so it now enforces freshness for real.

- [ ] **Step 3: Update the homepage Triangulate card link**

In `docs/index.html`, find the Triangulate card's link to `engines/triangulate.html` (located earlier: `grep -n "engines/triangulate" docs/index.html`) and change its visible link text to "View datasheet" (keep the href). Show the exact before/after in the commit; do not alter other cards (those are phase 2/3).

- [ ] **Step 4: Preview locally (network-safe)**

Run: `cd docs && py -3 -m http.server 8080` then open `http://localhost:8080/engines/triangulate.html` in a browser. Verify: die stack layers are clickable and the panel updates; schematic blocks link out; spec-strip footnotes resolve to the Substantiation list; motion swap plays; page prints as a single column with the static SVG. (The workstation's corporate network resets the live domain — preview locally, never via sophonfinance.com.)

- [ ] **Step 5: Run the FULL datasheet suite**

Run: `cd site-datasheets && py -3 -m pytest -q`
Expected: all pass, including `test_committed_page_is_fresh` (now un-xfailed) and determinism.

- [ ] **Step 6: Run the atlas suite to confirm no cross-package collision**

Run: `cd finance-atlas && py -3 -m pytest -q`
Expected: unchanged, all pass (confirms `datasheet_tests`/`generate_datasheets` naming did not collide).

- [ ] **Step 7: Commit**

```bash
git add docs/engines/triangulate.html docs/index.html \
        site-datasheets/datasheet_tests/test_generator.py
git commit -m "feat(datasheets): ship Triangulate exemplar datasheet in place + homepage link"
```

- [ ] **Step 8: Push and open a PR (with owner's go-ahead on auth)**

Confirm with the owner before triggering the GitHub device-code flow (`gh auth login`, approved in their signed-in Chrome). Then:

```bash
git push -u origin feature/engine-datasheets
gh pr create --base main --head feature/engine-datasheets \
  --title "Engine datasheets — Phase 1: Triangulate exemplar" \
  --body "Data-driven eleven-zone datasheet for Triangulate (SFS-E06-TRI), generated from site-datasheets/specs/triangulate.json. Full pytest suite + CI drift guard. Ships in place at /engines/triangulate.html. Phases 2–3 (other 8 engines, family matrix) follow."
```

Note: GitHub Pages source (main branch, `/docs`) is repo-settings-side — confirm before merge; merge publishes automatically.

---

## Self-Review

**Spec coverage (design §-by-§):**
- §3 architecture (data-driven generator, collision-proof naming, byte-identical, stdlib) → Tasks 1, 3; determinism tests Task 3.
- §4 part-number scheme (SFS-E06-TRI, REV from spec, PRODUCTION legend) → Task 2 (data) + Task 3 (masthead render).
- §5 eleven zones → masthead/strip/plain/instruction/benchmarks/control/limits/see-it-run/integration (Task 3), die stack (Task 4), schematic (Task 5); footnote/Substantiation discipline (Task 3 `Footnotes`).
- §6 interactivity & budget (CSS-3D, inline SVG, a11y, ≤150 KB, print) → Tasks 4, 5, 7; print CSS Task 3.
- §7 spec JSON schema → Task 1 validator + Task 2 data.
- §8 tests (schema, determinism, claim-lint, size, link/asset, deny-list, voice-lint, roster-vs-BRAND-VOICE) → Tasks 1, 3, 6, 7, 8, 9; CI wiring + counts + marker → Tasks 9, 10.
- §9 rollout phase-1 items (generator+template+spec+die+schematic; test suite+CI+counts+marker; BRAND-VOICE roster; capture script; ship in place + card link) → Tasks 1–11.
- §10 deployment (branch, local preview, device-code auth, network quirk) → Task 11 steps 4, 8.
- §11 scope (BRAND-VOICE update, CI edits, capture script, homepage card link only) → Tasks 6, 10, 11; nothing beyond §9 homepage scope touched.

**Placeholder scan:** No "TBD"/"implement later." Two intentional, bounded deferrals are explicit: `docs/tests` route (Task 7 Step 2 verifies the real route before asserting) and the test-count workflow's exact flag placement (Task 10 Step 3 records the edit after inspecting the workflow) — both require reading a file whose exact contents weren't captured in this plan; each names the command to run and the invariant to preserve.

**Type/name consistency:** `render(slug)`, `main(argv)`, `OUT_DIR`, `ROOT`, `REPO`, `die_stack_html(spec)`, `schematic_html(spec)`, `Footnotes.mark/render`, `load_spec`, `validate_spec`, `REQUIRED_FIELDS`, `SOURCED_ARRAYS` are used identically across Tasks 1–11. Test package `datasheet_tests/`, generator `generate_datasheets.py` — consistent throughout and collision-checked in Task 11 Step 6.
