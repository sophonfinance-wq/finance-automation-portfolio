# Engine Datasheet Pages — Design

**Date:** 2026-07-20 · **Rev:** 2 (post adversarial review, 4 lenses / 41 findings applied)
**Status:** Pending owner review · **Owner:** Sophonnarith Hang · **Prepared with:** Claude Code

## 1. Goal

Upgrade the nine per-engine pages at `sophonfinance.com/engines/<slug>.html` from ~12 KB
brochure pages (hero, one tile, three columns, two FAQs) into **datasheet-grade product
pages** — the depth and precision a semiconductor company gives a processor. Each page
explains the engine in **plain English and engineering terms side by side**, leaving no
ambiguity about what the engine does, how it is controlled, and how a client verifies it.

The chip-datasheet register completes the existing brand: the site already runs IBM Plex
Sans/Mono and Carbon blue `#0f62fe`, and BRAND-VOICE.md already demands measured,
spec-dense, evidence-led copy. A datasheet is a hype-free register.

**The marketing thesis — the one thing no chip company can offer:** a CPU buyer cannot
re-run the vendor's benchmark lab; every claim on a Sophon datasheet re-derives from the
public repository. The benchmark is a command, not a press release. Each page states
this once, plainly, in the masthead area.

## 2. Constraints

From **BRAND-VOICE.md** (non-negotiable):
- Every number on a page is true, current, and demonstrable from the repository.
  (Corollary applied here: no invented dollar-savings figures; time/money benefit
  framing is qualitative or an explicitly labeled fictional illustration.)
- Measured voice; no superlatives, exclamation-driven hype, or banned phrases.
- Orchestration framing, verbatim wherever autonomous/agent-enabled modes are described:
  *"an optional orchestration layer for approved, agent-enabled environments; the
  platform runs fully without it."*
- Knowledge Brain rule: never state or imply the engine itself applies or verifies
  changes ("hands-free" is banned); it **generates** an apply-ready, cited remediation
  prompt.
- Primary CTA is **run it**.

From the **existing site conventions** (docs/engines/*.html, retained):
- Footer disclaimer "All public examples use fictional, seeded data." on every page.
- "Verify it yourself" block and consultation secondary CTA.
- Sticky nav, brand mark, img→video motion-swap pattern.

**Canonical names authority:** the nine H1s as rendered on the live engine pages (§4
roster). BRAND-VOICE.md's canonical list currently names only seven engines and calls
engine 03 "Partnership 1065 Automation"; **phase 1 updates BRAND-VOICE.md's roster to
the nine site names** (explicitly in scope, see §11), and the §8 roster test asserts
page H1s against BRAND-VOICE.md so there is one authority thereafter.

## 3. Architecture — data-driven generator (approved: option A)

One reviewable spec file per engine; a deterministic generator renders all pages from a
single template. House pattern: `finance-atlas/generate.py` (documentation-as-artifact,
stdlib-only, no timestamps, byte-identical output pinned by tests).

```
site-datasheets/
├── specs/                     # one JSON spec per engine — the single source of truth
│   ├── triangulate.json       #   (exemplar; other eight follow in phase 2)
│   └── …
├── generate_datasheets.py     # stdlib only: json, html, string.Template, pathlib
├── templates/
│   └── datasheet.html.tmpl    # the shared eleven-zone template
├── partials/                  # build-time includes (SVG/CSS/JS fragments)
└── datasheet_tests/           # pytest package, uniquely named — see §8
```

- **Module naming (collision-proof, verified against root pytest collection):** the test
  package is `datasheet_tests/` (mirroring `atlas_tests/`; a second top-level `tests`
  package would collide with `tax-surplus-engine/tests`), and the generator module is
  `generate_datasheets.py` (a second top-level `generate` would collide with
  `finance-atlas/generate.py` in `sys.modules` under single-process root collection).
- **Partials are build-time includes.** The generator inlines them into each page; the
  only emitted artifacts are the per-page HTML files, matching the site's existing
  inline-CSS pattern. A template or partial change therefore requires regenerating all
  pages — the CI drift check enforces this.
- **Output:** `docs/engines/<slug>.html`, committed (GitHub Pages serves `docs/`).
  Byte-identical across runs — the generator is a pure function of specs + template
  (no dates, no environment reads). CI regeneration must produce a clean diff.
- **No new runtime dependencies.** Python 3.12 stdlib for generation (CI pins 3.12);
  vanilla JS + CSS 3D + inline SVG in the pages. No three.js, no bundler. Google Fonts
  stays (already used site-wide).
- **URLs, nav, footer, and the motion-swap pattern are retained** — the upgrade is
  in-place.

## 4. Part-number scheme

Format: **`SFS-E<NN>-<MNEMONIC>`** — Sophon Finance Systems, Engine NN (site numbering,
already public in each page's "ENGINE NN" kicker), three-letter mnemonic.

- **REV** = the `rev` field in the engine's spec JSON (ISO date `YYYY-MM-DD`), bumped
  deliberately when the spec's content changes — never derived from the generation run
  (that would break determinism; the atlas pattern embeds no dates for exactly this
  reason).
- **Status** = the `status` field; all nine ship as **PRODUCTION**, and every masthead
  carries a one-line legend so the term implies nothing untrue:
  *"PRODUCTION = runnable end-to-end, CI-backed, full test suite passing. All data
  fictional and seeded."*
- **Relation to the existing `reports/` series:** `SFS-ENG-00N` on the PDF reports is a
  document-numbering series whose digits differ from site order; it is unrelated to
  part numbers. Part numbers follow site numbering only. (Renaming the report series is
  out of scope; noted to avoid confusion.)

| # | Part no. | Engine (H1) | Slug | Family label |
|---|---|---|---|---|
| 01 | SFS-E01-CLS | Month-End Close | close | Close Automation |
| 02 | SFS-E02-RCN | Cash & Debt Reconciliation | recon | Reconciliation |
| 03 | SFS-E03-PTX | Partnership Tax · Form 1065 | tax | Partnership Tax |
| 04 | SFS-E04-VAL | Validation Engine | validation | Read-Only Validation |
| 05 | SFS-E05-SRP | Tax Surplus / ACB | surplus | Cross-Border Tax |
| 06 | SFS-E06-TRI | Triangulate | triangulate | AI Validation |
| 07 | SFS-E07-KBN | Knowledge Brain | brain | Cited Knowledge |
| 08 | SFS-E08-ATL | Finance Operations Atlas | atlas | Documentation-as-Artifact |
| 09 | SFS-E09-CSH | Cash Management | cash | Cash Controls |

No trademark symbols. The part number is presentation, not a rename: canonical H1s
remain the page titles.

## 5. Page anatomy — the eleven zones

Every engine page renders the same eleven zones in order. **PLAIN TERMS / ENGINEERING
pairing is structural in zones 2, 5, and 8** (the technical-narrative zones); zones 3,
6, 7, and 9 are self-explanatory tabular data and take an optional per-row `plain` gloss
rendered where present. Nothing hides behind toggles — a datasheet presents; it does not
conceal (also keeps pages printable and accessible).

**Footnote discipline (chip-marketing pattern, done honestly):** every figure in zones
3 and 7 renders a superscript marker resolving to a **Substantiation** list at the foot
of the page (part of zone 11): the file, test, or command the figure derives from —
generated from the `source` fields in the spec JSON.

1. **Masthead** — part line (`SFS-E06-TRI · AI VALIDATION · REV 2026-07-20 ·
   PRODUCTION`) + status legend (§4), canonical H1, tagline, one-paragraph plain-English
   purpose, the marketing-thesis line (§1), primary CTA **Run it** (links to
   `links.codespaces`) + secondary consultation CTA (site-constant `/#book`). CTAs are
   template-level, drawing hrefs from `links{}` — no CTA field in the spec JSON.
2. **Interactive die stack (hero)** — an exploded isometric stack of the engine's
   functional blocks (Triangulate: Human Gate / Deterministic Auditor / Reviewer /
   Specialist / Preparer over a substrate labeled "seeded fictional data").
   **Progressive enhancement, single source:** the generator renders BOTH a static
   isometric SVG (the default state, built from the same `layers[]` data — fallback and
   interactive stack can never disagree) and the CSS-3D stack markup; JS adds a root
   class that swaps in the 3D version; `@media print` and `prefers-reduced-motion`
   force the SVG regardless of JS. Pointer-drag rotates within stated bounds
   (rotateX 55°–70°, rotateZ ±35°) with a drag threshold so tap ≠ drag. Layers are
   focusable buttons in DOM order: click/Enter/Space opens the info panel (that layer's
   PLAIN TERMS + ENGINEERING copy + source link), Esc closes it. Hover alone never
   gates content.
3. **Key specifications strip** — chip-style stat band: hand-written tests,
   grid-expanded tests, verdict states, exit codes, roles/controls count, determinism
   guarantee. Every figure carries `source` (→ Substantiation footnote).
4. **What it does for you (PLAIN TERMS)** — `problem_statement` (the problem in
   working-day terms) plus 2–3 `scenarios[]` on fictional data, each carrying `source`
   pointing at the engine README demo it is taken from — never invented (e.g., "An AI
   asserts a Total Revenue $49,000 over what the streams sum to; two independent roles
   catch it and sign-off is blocked.").
5. **Functional block diagram (ENGINEERING)** — a CAD-drawing-sheet SVG schematic
   (title block, border rules — continuous with the homepage close-engine drawing-sheet
   idiom, ~4.5 KB scale: blocks and gates, not netlists): blocks, data paths, gates;
   signal-trace animation via CSS `stroke-dashoffset`; each block links to its GitHub
   source file. Layout positions come from explicit grid coordinates in the spec JSON
   (`col`/`row` per block) — no auto-layout in the generator.
6. **Instruction set** — every public command/flag as an opcode row rendered from
   `instruction_set[]`: the `cmd` is the opcode column (`--demo-adversarial`),
   operation, expected output, exit code, artifacts written. Copy-to-clipboard per row.
7. **Benchmarks** — measured demo results only: findings raised by class, cascade
   depth, loop turns-to-heal, test counts, suite runtime order. Inline-SVG datasheet
   figures. Time/money framing appears only as a labeled fictional illustration or a
   qualitative statement. Every figure carries `source` (→ Substantiation footnote).
8. **Control characteristics (ENGINEERING)** — the "electrical characteristics" analog,
   rendered from `control_characteristics{}` sub-keys (§7): authority hierarchy table,
   severity→verdict mapping, read-only/hash guarantees, determinism (integer-cent,
   seeded, byte-stable), gate policy (human-gated vs autonomous-with-quarantine), and
   operating modes (offline mock / live Anthropic Claude reviewer). Wherever
   autonomous/agent-enabled modes appear, the template emits the verbatim orchestration
   framing sentence (§2).
9. **Operating limits** — the errata analog, from `limits[]`: what the engine refuses
   to do, stated as capability discipline (e.g., "the loop clears arithmetic; it cannot
   manufacture authority — AI-assumption inputs and unsupported hardcodes escalate to a
   human"). Chip companies bury errata; these pages lead with limits as proof of
   control.
10. **See it run** — screencast of the real CLI run as a webp poster + silent looping
    mp4 pair (the site's existing asset convention — `tile-*` names for six engines;
    close/recon/tax use legacy `engine-*` names, normalized in phase 2), plus close-up
    crops of the verdict block and fix packet from `media.crops[]`. **No capture
    pipeline exists in the repo today** (the tile assets were committed as rendered
    binaries; `assets/make_system_gifs.py` synthesizes GUI-style GIFs, it does not
    record CLIs); phase 1 creates a minimal capture/encode script for Triangulate's
    `--demo-adversarial` run and checks it in beside the generator.
11. **Integration** — heading is "Integration" (not "Ordering" — nothing here is a
    purchasable SKU); first line reads "Distribution: public repository, MIT license."
    Contains: clone/Codespaces quickstart (template boilerplate parameterized by slug
    and `links{}`, plus optional per-engine `quickstart[]` rows), CI-gate usage (exit
    codes from `instruction_set[]`), the retained "Verify it yourself" block, the
    **Substantiation** footnote list, the consultation CTA band, and the site footer
    with the fictional-data disclaimer.

## 6. Interactivity & page engineering

- **Die stack:** pure CSS 3D (`transform-style: preserve-3d`); vanilla JS for pointer
  rotation, panel focus management, and copy-to-clipboard — target ~4 KB unminified,
  within the page budget. No WebGL library.
- **Schematic:** inline SVG; animation CSS-only; interaction = plain anchors.
- **Accessibility (all interactive elements, both hero and schematic):** keyboard
  operable, visible `:focus-visible` states, aria-labels, reduced-motion respected.
- **Performance budget: ≤ 150 KB HTML+inline SVG/CSS/JS per page** — including both
  hero representations (static SVG + 3D markup) and all fallbacks; media lazy-loaded
  below the fold. Verified realistic: the whole nine-engine homepage is 177 KB; existing
  drawing-sheet schematics run ~4.5 KB; a full datasheet page estimates 65–115 KB.
  Enforced by a §8 test, not by vigilance.
- **Print stylesheet:** datasheets get printed — single column, static SVGs, nav/CTA
  suppressed.

## 7. Spec JSON schema (per engine)

Top-level required fields unless marked optional:

- `num`, `slug`, `part_no`, `mnemonic` (part-number letters, e.g. `TRI`), `family`,
  `name`, `tagline`, `plain_summary`, `rev` (ISO date, deliberately bumped),
  `status` (`PRODUCTION`)
- `layers[]`: `{id, label, plain, engineering, source_link}` — die stack (both
  representations render from this one array)
- `blocks[]`: `{id, label, kind?, plain?, engineering?, source_link, col, row}` and
  `edges[]`: `{from, to, label?, gate?}` — schematic
- `spec_strip[]`: `{label, value, source, plain?}`
- `problem_statement` and `scenarios[]`: `{title, narrative, source}`
- `instruction_set[]`: `{cmd, operation, output, exit_code, artifacts, plain?}`
- `benchmarks[]`: `{label, value, unit, source, plain?}`
- `control_characteristics{}`: `{authority[], verdict_map[], guarantees[],
  determinism{}, gate_policy{}, modes[]}`
- `limits[]`: `{statement, source}`
- `media{}`: `{poster, motion, crops[]: {src, alt, caption}}`
- `quickstart[]` (optional): `{label, command}` — per-engine extras beyond the
  template boilerplate
- `links{}`: `{readme, source, tests, codespaces}`
- `meta{}`: `{description, og fields}`

Every `source` field is a non-empty pointer to the file, test, or command the value
derives from; the generator renders them as Substantiation footnotes. The honesty
mechanism is in the schema — and the §8 lint enforces it for `spec_strip`,
`benchmarks`, `scenarios`, and `limits` alike.

## 8. Tests (`datasheet_tests/`, pytest)

- **Schema validation** — every spec JSON validates; required fields present and
  well-formed (`rev` ISO-dated); slugs, numbers, part numbers match the §4 roster; page
  H1s assert against **BRAND-VOICE.md's canonical roster** (updated in phase 1 — one
  authority).
- **Determinism** — generate twice in-process, byte-identical; committed
  `docs/engines/*.html` match a fresh regeneration (the atlas
  `test_committed_artifact_is_fresh` pattern; paths resolved relative to `__file__`,
  not cwd, so both root pytest and per-directory CI runs pass).
- **Claim lint** — every `spec_strip`/`benchmarks`/`scenarios`/`limits` entry has a
  non-empty `source`. Test-count figures are cross-checked against
  `site-datasheets/counts.json`, refreshed in phase 1 via `pytest --collect-only -q`
  per engine directory; a missing or stale counts file is a **hard fail**, not a skip.
- **Size budget** — each generated page ≤ 150 KB.
- **Link/asset existence** — every internal link and media path (including
  `media.crops[]`) resolves to a file in the repo or a known site route.
- **Confidentiality deny-list** — the Atlas linter pattern over generated pages.
- **Voice lint** — generated pages checked against a checked-in term list
  (`datasheet_tests/voice_lint_terms.txt`, seeded from BRAND-VOICE.md's banned-phrase
  prose); no exclamation marks in body copy (permitted inside `<pre>`/`<code>` CLI
  output samples); pages containing "autonomous" or "agent-enabled" must contain the
  verbatim orchestration framing sentence; the Knowledge Brain page must not contain
  "hands-free"/"applies the changes" phrasings.

**CI wiring (explicit phase-1 deliverable):** append `site-datasheets` to both
hard-coded directory lists in `.github/workflows/ci.yml` (deps step and test loop), and
add a belt-and-braces drift step: run the generator, then `git diff --exit-code
docs/engines/`.

**Test-count policy:** the published headline counts (README badge, docs/tests/ page)
remain **engine** tests. Datasheet-tooling tests carry a pytest marker and are
deselected from the test-count workflow's headline pass, appearing as a separately
labeled "site tooling" line on docs/tests/ — the nine-engine framing stays true and no
published number goes stale. Implemented in the same phase-1 PR as the tests.

## 9. Rollout

- **Phase 1 — exemplar (this effort):**
  1. Generator + template + `triangulate.json` + die stack + schematic;
  2. the full §8 test suite + CI wiring + `counts.json` + test-count-policy marker;
  3. BRAND-VOICE.md canonical roster updated to the nine site names;
  4. minimal screencast capture/encode script + refreshed Triangulate capture;
  5. ships `docs/engines/triangulate.html` in-place at its existing URL; homepage
     Triangulate card link text becomes "View datasheet".
  Approval gate: owner reviews the built page locally before merge.
- **Phase 2 — replicate:** eight spec JSONs; per-engine die-stack layers and
  schematics; screencasts engine-by-engine; normalize the three legacy `engine-*`
  media asset names to the `tile-*` convention. Template fixes from phase-1 feedback
  propagate by regeneration.
- **Phase 3 — family integration:** homepage cards gain part numbers + spec-strip
  teasers; a **family comparison matrix** ("which engine for which job" — the lineup
  table, the Core i3/i5/i7 pattern); sitemap/OG metadata pass; cross-links between
  related datasheets (Triangulate ↔ Validation Engine). Scope enumerated here is the
  committed phase-3 scope (see §11).

## 10. Deployment & logistics

- Work happens on branch `feature/engine-datasheets` off `origin/main` in the local
  clone at `C:\Users\SHang\Documents\New project\finance-automation-portfolio`.
  (Local `main` had diverged from the rewritten GitHub history; it is left untouched.)
- The site is served by GitHub Pages from `docs/` (CNAME present). Pages source
  settings (main branch, `/docs` folder) are repo-settings-side — **confirm before
  merge**; merge to `main` then publishes automatically.
- Push requires GitHub auth on this machine: `gh auth login` device-code flow, approved
  in the owner's signed-in Chrome session, with the owner's go-ahead at that moment.
- Observed local condition (2026-07): the workstation's network resets direct HTTPS to
  sophonfinance.com; GitHub and raw.githubusercontent are unaffected. Preview via a
  local static server over `docs/`.

## 11. Scope boundaries

**In scope beyond the generator and its tests (explicit exceptions):**
- BRAND-VOICE.md canonical-roster update (§2, §9.1).
- `.github/workflows/ci.yml` directory-list addition + drift step; test-count workflow
  marker/deselect change (§8).
- The screencast capture/encode script and the refreshed Triangulate capture (§5.10);
  it may be minimally adjusted per engine in phase 2.
- Homepage changes enumerated in §9 only (phase 1: Triangulate card link text;
  phase 3: part numbers, spec-strip teasers, family matrix, sitemap/OG).

**Out of scope:**
- Cinematic/voiceover marketing videos (storyboard hand-off to a vendor if wanted).
- Any change to engine code or engine test suites.
- Renaming engines, changing URLs, or renaming the `reports/` SFS-ENG document series.
- Homepage redesign beyond the §9 enumeration.
