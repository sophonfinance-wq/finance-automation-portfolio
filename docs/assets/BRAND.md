# Sophon Finance Systems — brand lockup

The permanent logo. One object, two lines. Do not set the descriptor as a
separate page element — that is what it used to be, and it read as two pieces of
furniture instead of one mark.

One sanctioned exception: the why-film endcard. It is a full-frame brand card
rather than a nav logo, and it already carries the positioning line ("Automate
the work. Keep the judgment.") in the slot the descriptor would occupy. It uses
the mark and wordmark only.

```
  ╱‾  Sophon Finance Systems
 ▁▁   FINANCE & ACCOUNTING AUTOMATION
```

## Rules

- **The descriptor's left edge sits on the S of Sophon** — not on the mark. Both
  text lines share one left margin; the mark hangs outside it.
- The two lines are one link/one element. `assets/logo.svg` is the standalone
  asset; in HTML the lockup is `.brand > .brand-mark + .brand-text`.
- Never letter-space the wordmark to fill space.

## Measured geometry

Widths measured in-browser with the real IBM Plex webfonts, off-layout so flex
could not squeeze the result. The descriptor is tuned to sit a hair *inside* the
wordmark — a mono line set to the exact same measure as a proportional one reads
optically wider, and dead-flush looks like an accident.

| viewport | wordmark | descriptor | descriptor width | delta |
|---|---|---|---|---|
| default | 18px | 9.5px / 0.9px tracking | 204.5px vs 206.2px | −1.6 |
| ≤400px | 16px | 8.5px / 0.8px tracking | 182.8px vs 183.8px | −0.9 |

Mark: 30×30. Gap mark→text: 10px. Gap wordmark→descriptor: 2px.

## Colours

| token | hex | use |
|---|---|---|
| ink | `#161616` | wordmark, mark baseline |
| blue | `#0f62fe` | descriptor, chart line, peak dot |

`#0f62fe` on `#f4f4f4` is 4.55:1 — it clears AA for text, with no margin to
spare. Do not lighten it.

## Type

- Wordmark — IBM Plex Sans. "Sophon" 600, "Finance Systems" 300, 0.2px tracking.
- Descriptor — IBM Plex Mono 500, uppercase.

## Where it lives

- `assets/logo.svg` — standalone asset
- `index.html`, `thanks.html`, `engines/*.html` — 12 pages, inline in the nav
- `../site-films/why/compose.py` — the film's endcard draws the mark and wordmark
  with PIL rather than CSS. Colour and weight changes need mirroring there; the
  descriptor line deliberately does not appear on it (see the exception above)
