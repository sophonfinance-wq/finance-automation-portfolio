# 🗺️ Finance Operations Atlas

> An **interactive, single-file system map** for a finance department —
> drives, workstreams, a find-it directory, and the recurring calendar,
> generated from a Python data model into one clickable HTML artifact.

> 🔒 This is a **demonstration artifact**. Every entity, person, path,
> platform, bank, and figure is fictional — it maps the finance group of an
> invented real-estate investment company (Demo Holdings Inc.). The tax
> content references **public law only** (CRA Form T1134 and the Reg. 5907
> series), consistent with this portfolio's
> [tax-surplus-engine](../tax-surplus-engine/).

---

## The problem it solves

Finance departments carry an enormous amount of *structural* knowledge —
which drive holds what, how each recurring process actually runs, what the
file-naming conventions mean, and what happens in which week of the month.
That knowledge usually lives in people's heads and a scattering of documents,
so onboarding is slow and handoffs are fragile.

This system demonstrates **documentation-as-artifact**: the department map is
data (`atlas_data.py`), and a deterministic generator renders it into a
single self-contained HTML page anyone can open — no server, no build chain,
no external resources. Update the data, re-run the generator, redistribute
one file.

## What the artifact contains

Five views, all driven from the same data model:

- **Overview** — the four core workstreams, the drive landscape, and the
  conventions worth knowing, as clickable cards.
- **Drive Map** — a three-pane browser (drive → folder → briefing) covering
  four fictional drives plus the systems group, with 14 folder briefings:
  purpose, key locations, what-to-know rows, and working notes.
- **Workstreams** — four process pipelines rendered as clickable steps, each
  step showing inputs, outputs, locations, and watch-fors:
  month-end cash reconciliation · foreign-affiliate surplus & ACB (T1134) ·
  monthly close & recurring entries · the compliance & audit cycle.
- **Find It** — a live-filtered lookup table (33 rows): *looking for… →
  location → notes*, categorized by function.
- **Calendar** — the recurring rhythm in monthly / quarterly / annual columns
  (16 events), keyed to a December 31 fiscal year-end.

## 60-second tour

1. Open [`out/finance-operations-atlas.html`](./out/finance-operations-atlas.html)
   in any browser.
2. On **Overview**, click *Month-End Cash Reconciliation* — the pipeline
   opens; click step 3 (*Tie each account to the bank*) to see the
   materiality and dormant-account rules.
3. Switch to **Drive Map**, pick the *Group Drive*, then *Entity Registry* —
   note the *Controlled* access tag and the briefing layout.
4. On **Find It**, type `t1134` — the table filters to the cross-border
   locations as you type.
5. Check **Calendar** for what January looks like (schedule rollforward +
   information-return season).

## ▶️ Regenerate it

Requirements: **Python 3.12+**, standard library only — no dependencies.

```bash
# from this folder (finance-atlas/)
py generate.py                          # writes out/finance-operations-atlas.html
py generate.py --out somewhere.html     # custom output path
```

The generator is **deterministic**: no timestamps, no randomness — running it
twice produces byte-identical output, so the committed artifact diffs cleanly
when (and only when) the data changes.

### How it works

- **`atlas_data.py`** — the data model: typed dataclasses and plain dicts for
  the drives (with folder briefings), the workstream pipelines, the find-it
  rows, the calendar, the palette, and the page metadata. All display text
  lives here.
- **`generate.py`** — the renderer: substitutes the palette into the
  stylesheet, escapes and embeds the static shell, serializes the data model
  to JSON inside the page, and appends a small dependency-free script that
  builds the interactive views client-side. One command, one file out.

## Accessibility

Baked in rather than bolted on:

- Every clickable element is a native `<button>` — keyboard reachable, with
  visible `:focus-visible` outlines.
- Text colors are chosen for WCAG AA contrast on their backgrounds (accent
  hues get darkened "ink" variants for text use).
- Landmarks and labels: `<nav aria-label>`, section labels, a labelled search
  input, a `role="status"` result counter for the live filter, and
  `aria-current` on the active view.
- Responsive: the header wraps, the three-pane browser collapses to one
  column, and long paths wrap (`overflow-wrap: anywhere`) instead of
  overflowing on small screens.
- `prefers-reduced-motion` disables the view-transition animation.

## Tools

`Python 3 (stdlib)` · `HTML/CSS/JS (no frameworks, no CDN)` · `Claude Code`

## Layout

```
finance-atlas/
├─ atlas_data.py     # the data model — drives, workstreams, find-it, calendar, palette, meta
├─ generate.py       # deterministic renderer: py generate.py [--out PATH]
├─ out/
│  └─ finance-operations-atlas.html   # the committed single-file artifact
└─ README.md
```

---

*Demonstration artifact — all entities, people, paths and figures are
fictional. Real department maps are internal documents and are never
published.*
