# HANDOFF — Engine Datasheet Pages (Phase 1: Triangulate exemplar)

**For:** Claude Code (VS Code) picking this up fresh. Everything you need is in this file +
the committed spec. Owner: Sophonnarith Hang (Sophon), contact@sophonfinance.com.

> Historical handoff note: this file preserves the original implementation context.
> Current behavior and claims are governed by `site-datasheets/specs/triangulate.json`,
> the generator, and the executable tests; do not treat unchecked steps below as current
> repository status.

## Original handoff state and standing constraints

1. **Repo/branch at handoff:** `finance-automation-portfolio`, branch
   `feature/engine-datasheets` (based on `origin/main` @ `e5a374d`). **Local `main` is
   stale/diverged from the rewritten GitHub history — never merge it or base work on it.**
2. **Approved design spec (read it first):**
   `specs/2026-07-20-engine-datasheet-pages-design.md` — rev 2, already adversarially
   reviewed (4 lenses, 41 findings applied) and **approved by Sophon**. It defines the
   whole project: upgrade the nine `docs/engines/<slug>.html` brochure pages into
   chip-datasheet-grade pages; data-driven stdlib generator; 11-zone template; part
   numbers `SFS-E01-CLS … SFS-E09-CSH`.
3. **Original next step (historical):** write the implementation plan from the recon
   facts below, then execute Phase 1 task-by-task with tests. That planning step has
   already been performed; verify the current checkout rather than replaying it.
4. **Decisions already made — do not re-ask:** spec rev 2 approved in full; interactive
   in-browser visuals (CSS 3D + SVG, no three.js); Triangulate (Engine 06) exemplar
   first; full chip-datasheet register; test-count policy = `site_tooling` pytest marker
   excluded from headline counts, shown as a separate "site tooling" row.
5. **Approval gate:** Sophon reviews the built page locally before any merge to main.
6. **Push/PR gate:** never push, open a PR, or merge without the owner's explicit
   approval. After approval, use the repository's established authenticated workflow;
   if credentials are unavailable, stop after the verified local handoff.
7. **Environment:** the repo targets Python ≥3.12 and CI runs Python 3.12. Use
   `python -m ...` commands in portable instructions. Preview through a local static
   server rooted at `docs/`; live-domain access is not required for local verification.

## Suggested task breakdown (~16 bite-sized tasks)

1. Scaffold `site-datasheets/` + spec loader w/ validation + `triangulate.json`
2. Generator core: page shell (masthead/part line/status legend/thesis/CTAs/footer) + determinism tests
3–11. Zone tasks: spec strip + substantiation footnotes → plain-terms scenarios →
   die stack (static SVG default + CSS-3D swap + panel JS) → CAD schematic →
   instruction set → benchmarks → control characteristics → operating limits →
   see-it-run → integration zone
12. Honesty machinery: `counts.json` + claim lint; size budget (≤150 KB); link existence;
   deny-list; voice lint
13. BRAND-VOICE.md canonical roster update (9 names)
14. ci.yml wiring + drift step; test-count marker policy; docs/tests "site tooling" row
15. Homepage Triangulate card link + sitemap check
16. Full verification: root pytest, local preview, print/reduced-motion/mobile checks

## Historical recon facts (verified 2026-07-20)

These facts document the basis of the original plan. Re-run the relevant commands before
making a current public claim; the checked-in spec and tests remain authoritative.

### Collision traps (violating these breaks root pytest + the published test-count workflow)
- Test package MUST be `datasheet_tests/` (with `__init__.py`), NOT `tests/` —
  `tax-surplus-engine/tests` already owns the top-level `tests` package name.
- Generator module MUST be `generate_datasheets.py`, NOT `generate.py` —
  `finance-atlas/generate.py` owns `sys.modules['generate']` under root collection.
- `site-datasheets/pytest.ini`: `[pytest]` + `testpaths = datasheet_tests` +
  `python_files = test_*.py` + `markers = site_tooling: site tooling tests, excluded
  from headline engine counts`. Register the marker HERE (package-local), NOT in root
  pyproject — root has NO pytest config, and adding root addopts/testpaths would
  silently change CI behavior for the 6 packages that lack their own pytest.ini.
- Root pytest discovery will collect `site-datasheets` tests automatically (no
  testpaths restriction at root) — so the marker/deselect must land in the same PR as
  the tests.

### House pattern to copy (finance-atlas — the spec mandates this pattern)
- `generate.py` structure: module-level `_CSS = Template(...)` (palette via
  `$placeholders`), `_JS` plain string (no template literals), `_SHELL = Template(...)`;
  `render()` = `_SHELL.substitute(...)` with every text field through
  `html.escape(str(...))`; data embedded as JSON via
  `json.dumps(..., ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")`.
- Output: `out_path.write_bytes(document.encode("utf-8"))` — NEVER `write_text` (kills
  byte-identical on Windows). No timestamps anywhere. Document ends `</html>\n`.
- `main(argv=None) -> int` with single `--out` arg (type=Path), `if __name__ ==
  "__main__": raise SystemExit(main())`; tests call `generate.main(["--out", ...])`
  in-process.
- `atlas_tests/conftest.py`: `PKG_DIR = Path(__file__).resolve().parents[1]`;
  `sys.path.insert(0, str(PKG_DIR))` then import the modules; exposes
  `ARTIFACT_PATH` constant; session fixtures `rendered`, `artifact_text`, and a
  `DocIndex(HTMLParser)` structural index (tag balance, ids, scripts, sections).
- Determinism tests (copy all three): `test_render_is_deterministic_in_process`
  (`render()==render()`), `test_two_generator_runs_are_byte_identical` (two `main()`
  runs into tmp_path, compare `read_bytes()`), `test_committed_artifact_is_fresh`
  (`ARTIFACT_PATH.read_bytes() == generate.render().encode("utf-8")`).
  NOTE: for datasheets the committed artifact is `docs/engines/triangulate.html`
  (= `PKG_DIR.parent / "docs" / "engines" / "triangulate.html"`) — resolve via
  `__file__`, never cwd (root pytest runs from root; CI runs from inside the package).
- Deny-list test (`atlas_tests/test_deny_list.py`): terms stored as
  `(sha256_hex_of_normalized_term, n_words)` tuples — plaintext never in repo;
  normalization = fold curly quotes → lowercase → tokenize `[0-9a-z]+(?:'[0-9a-z]+)*`
  → join single spaces; n-gram digests swept over TEXT_SUFFIXES {.py,.md,.html,.htm,
  .txt,.json,.ini,.cfg,.toml,.yml,.yaml,.css,.js,.svg}, skipping
  __pycache__/.pytest_cache/.git/node_modules; failures print digest[:12] only;
  canary phrases self-test the matcher. Copy the mechanics; reuse the same 85-digest
  DENYLIST from the atlas file.

### CI wiring (exact edit targets)
- `.github/workflows/ci.yml`: two byte-identical nine-directory bash lists at
  **line 44** (deps step) and **line 68** (test loop):
  `for dir in monthly-close-automation cash-reconciliation cash-management
  tax-surplus-engine partnership-1065-automation audit-automation
  ai-validation-framework knowledge-brain-engine finance-atlas; do`
  → append ` site-datasheets` before the `;` on BOTH lines.
  Test loop does `( cd "$dir" && python -m pytest -q )`, aggregates exit codes,
  `PYTHONIOENCODING: utf-8`, no caching.
- Add belt-and-braces drift step to ci.yml after the test loop:
  `py`/`python site-datasheets/generate_datasheets.py && git diff --exit-code docs/engines/`.
- `.github/workflows/test-count.yml`: counts at REPO ROOT, writes ONLY to
  `$GITHUB_STEP_SUMMARY`. Curated total at **line 38**
  (`python -m pytest --collect-only -q | tail -1`); by-engine table at **line 56**
  (engine = first path segment via `sed -E 's#/.*##'` — a `site-datasheets` row appears
  automatically); sweep at **line 70** (`SWEEP: "1"`). Insert `-m "not site_tooling"`
  into line 38 (and 70) per the approved policy; keep the echoed reader-facing commands
  at **lines 48 and 77** in sync or the summary shows a command that doesn't reproduce
  the number. Decide in-plan whether the line-56 table keeps the site-datasheets row
  (recommended: yes, it's honest) — if so deselect only the totals.

### Hard-coded test-count locations (do NOT let published numbers go stale)
With the `site_tooling` deselect, headline counts stay 2,392 / 67,664 and none of these
need touching — verify that in the final task. Locations for reference: README lines 8
(badge `2,392`), 9 (`systems-9`), 36, 138–140, 146–148 (per-system:
triangulate **8,320**); `docs/tests/index.html` (hand-written, 67,664 in 11 places:
lines 6,7,10,11,155,159,183,189,203,260,276; per-engine rows 212–256; add the
"site tooling" row in the same 3-cell `<tr>` shape as the finance-atlas row at
252–256); `docs/index.html` SITE-FACTS comment block lines 10–24 + lines
7,15,30,827,829,1332,1336,1345,1354,1615,1623,1631,1639; `docs/CASE-STUDY.md` 22,
90–100; `docs/CODEX-REVIEW-PROMPT.md` 9–10; `docs/BRAND-VOICE.md` 33–34;
`worker/src/index.js` 59, 82.

### Triangulate facts for `triangulate.json` (all verified live, seed 20240101)
- **Tests: 8,320 collected** (`python -m pytest --collect-only -q` in
  ai-validation-framework; full run 8,320 passed in ~8s). The engine README was stale
  during the original recon and has since been synchronized to 8,320.
- Portable quickstart: `git clone https://github.com/sophonfinance-wq/finance-automation-portfolio.git && cd finance-automation-portfolio/ai-validation-framework && python -m triangulate`.
- Entry points: `python -m triangulate` (cli.py), `python run.py` (equivalent),
  `python -m triangulate.loop`. Package `__version__ = "1.0.0"`.
- Pipeline flags: `--sample {clean,defective}` (default defective);
  `--demo-adversarial` (overrides --sample; 'adversarial' is NOT a --sample value on
  the pipeline CLI); `--seed` (default 20240101); `--no-specialist`; `--output DIR`
  (default ./output); `--no-artifacts`; `--xlsx` (only flag needing openpyxl, lazy
  import).
- Exit codes: **0 = PASS, 1 = FLAG or FAIL** — nothing else. Loop: 0 only if final PASS.
- Pipeline artifacts (5): `builder_memo.txt`, `fix_packet.txt`, `change_log.txt`,
  `qa_summary.txt`, `verdict.json` (+ `workpaper.xlsx` with --xlsx). Loop writes only
  `review_loop_report.md` and only with `--out`.
- Loop flags: `--seed`, `--sample {clean,defective,adversarial}` (default adversarial),
  `--budget` (default 6), `--out`. Loop verdicts: CLEAN / AUTO-CLEARED / ESCALATED.
  Remediable codes: `{AUDIT_TIE_OUT_FAIL, TIE_OUT_MISMATCH}` and only cells carrying a
  formula — fix = the cell's own formula re-evaluated on a clone (new digest).
- Roles + source links: Preparer `triangulate/roles/preparer.py` (only role that may
  mutate); Reviewer `roles/reviewer.py` (flags, never mutates); Specialist
  `roles/specialist.py` (read-only second opinions; transform only when explicitly
  invoked); Auditor `roles/auditor.py` (deterministic — "a script cannot hallucinate
  'yes'"); **`class HumanGate` in `triangulate/reconcile.py` is an automated severity
  policy, not a person and not a recorded approval**. A real person remains the final
  approver for escalations and sign-off.
- Implemented authority hierarchy (`model.py:58-77`, higher is more authoritative):
  AI_ASSUMPTION=1 < WORKBOOK_FORMULA=2 < CURRENT_YEAR_SOURCE=3 < MEETING_DECISION=4 <
  MANAGEMENT_INSTRUCTION=5 < SIGNED_PRIOR_YEAR=6. The public datasheet must render
  these six evidence-authority levels in the reverse display order, highest to lowest.
- Severity LOW=1..CRITICAL=4; the automated HumanGate policy maps any Critical → FAIL,
  any High → FLAG, and Medium/Low only or no findings → PASS. PASS means eligible for
  human sign-off with residual notes documented; it is not a human signature. Tie-out
  tolerance 0.01. Fix packet = Critical/High subset. Dedup key
  (code, cell_ref); higher authority wins; sort (-severity, -authority, cell_ref).
- Hash guard: `Workpaper.digest()` = sha256 of sort-keys JSON; orchestrator asserts
  digest unchanged around Reviewer/Specialist/Auditor steps, raises
  `SeparationOfDutiesError` on mutation; read-only roles get a
  `ReadOnlyWorkpaperView` whose `__setattr__` raises. Auditor structural check:
  required refs B5/B7/B8 → MISSING_REQUIRED_CELL (High).
- Modes: default = MockLLMReviewer (offline, key-free, deterministic). Live =
  `AnthropicReviewer` (stdlib urllib, model string `claude-opus-4-8`,
  `ANTHROPIC_API_KEY` supplies the key only) — live mode is selected **in code**
  (`AdversarialReviewer(AnthropicReviewer())`), no env var/flag switches it; default
  pipeline never calls the network. Don't overstate this on the page.
- Adversarial demo numbers: injection = +$49,000 on B5 (stated 593,000.0 vs re-derived
  544,000.0); verdict FAIL, Critical=6 High=0 Medium=1 Low=0 (criticals =
  TIE_OUT_MISMATCH + AUDIT_TIE_OUT_FAIL on each of B5, B7, B8 — both roles catch each
  cell independently; Medium = UNSUPPORTED_AI_ASSUMPTION on B5). Loop: 1 turn,
  re-derive B5 → 544,000.00, criticals 6→0, AUTO-CLEARED, 2 workpaper versions, exit 0.
- Defective sample: FAIL, Critical=2 High=1 Medium=2 Low=1 (B5 543,000 vs 544,000 —
  $1,000 break; High = B7 HARDCODED_NO_FORMULA; Medium = UNSUPPORTED_AI_ASSUMPTION on
  B6+B7; Low = PROCESS_LANGUAGE_LEAK). Loop: 2 turns (B5, then B8 → 441,184.00), final
  FLAG → ESCALATED, exit 1.
- Deps: default demo = pure stdlib. Repo-wide requirements.txt = openpyxl==3.1.5 +
  pytest==9.1.0 only.
- Dollar figures above are seed-20240101-specific; the $49k offset and severity
  patterns are seed-independent — say "at the default seed" wherever absolute dollars
  appear.

### Site integration points
- Triangulate tile: `docs/index.html:1011-1017`; the ONLY link is the h3 anchor
  `<a href="engines/triangulate.html">Triangulate</a>` (no "Learn more" text exists
  anywhere). For "View datasheet", add a small link element to the tile — don't rewrite
  the tile. Homepage SITE-FACTS comment (lines 10–24) governs any number shown on index.
- `/#book` is a JS modal (`#bookov`, opens on `location.hash==='#book'`; FormSubmit
  email form; Google appointment URLs dormant). Engine pages link `/#book` — keep as-is.
- All 9 engine pages: exactly 148 lines, byte-identical chrome — header.nav (lines
  71–78), .cta (122–127), footer (130), img[data-video]→video IntersectionObserver
  script (132–146). Minimal head: charset/viewport/title/description/Google-Fonts only
  (no favicon/og/canonical). The new template keeps the chrome verbatim; adding the
  index favicon (index.html:39 data-URI) + og tags is an approved improvement.
- `docs/sitemap.xml` already lists all nine engine pages — no change for phase 1.
- Media naming: `tile-<slug>.webp` + `tile-<slug>-motion.mp4` for 6 engines;
  close/recon/tax use legacy `engine-close.*`, `engine-recon.*`, `engine-1065.*`
  (normalize in phase 2, not now).
- **No screencast capture pipeline exists** — `assets/make_system_gifs.py` synthesizes
  PIL GUI-style GIFs, doesn't record CLIs; the committed mp4/webp were external
  renders. Phase 1 writes a minimal capture script (run `--demo-adversarial`, render
  stdout frames via PIL → poster webp + crop webps; mp4 via ffmpeg only if on PATH,
  else the page keeps `tile-triangulate-motion.mp4` as its motion asset).

### BRAND-VOICE.md edit (exact target)
Lines 44–45 (inside "## Terminology and mechanics"):
`- Use the canonical system names consistently: Month-End Close, Cash & Debt Reconciliation,`
`  Tax Surplus / ACB, Partnership Tax · Form 1065, Validation Engine, Triangulate, Knowledge Brain.`
→ Expand this to the nine site H1 names per spec §4 roster; engine 03 is
"Partnership Tax · Form 1065".

## Non-negotiables (from the spec — read §2, §5, §8 before coding)
- Every number on the page carries a `source` and renders a substantiation footnote.
- Generator = pure function; `rev` + `status` come from the spec JSON, never the clock.
- ≤150 KB per page incl. both hero representations; static SVG is the default state,
  JS swaps in the CSS-3D stack; print + reduced-motion force the SVG.
- Verbatim orchestration framing sentence wherever autonomous modes are mentioned.
- Measured voice; no invented savings; fictional-data footer retained.
