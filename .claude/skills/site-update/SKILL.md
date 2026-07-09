---
name: site-update
description: "Update sophonfinance.com (docs/index.html on GitHub Pages) with new sections or graphics. Use for any marketing-site change."
---
# sophonfinance.com Updates

The site is a single file: `docs/index.html`, served by GitHub Pages from `main` — **changes go live only when merged to main**.

## Conventions
- Sections: `<section class="alt" id="...">` on wash background; `.sec-kicker` eyebrow, `h2`, `.lead`. Scroll-reveal via `.reveal` classes (IntersectionObserver adds `.in`).
- Palette vars in `:root`: `--navy #0f2a5c, --blue #2563eb, --sky #00a8ff, --slate, --wash`.
- **Trap**: `.flow-caption` is styled for DARK bands (light text). On light sections use inline dark styles instead.
- Assets must live under `docs/assets/` (Pages serves only /docs). Nav links are in the `.nav-links` block.
- The "Self-Healing Operations" section (`#loops`) embeds `docs/assets/self-healing-loop.svg`.

## Verify before pushing
Extract the section + `<style>` into a temp page, force-reveal (`.reveal{opacity:1!important;transform:none!important}`), render with headless chromium FROM the docs/ directory (so relative asset paths resolve), and Read the PNG. Check tag balance (sections/divs open == close).

## Guardrail
The site promises "0 Numbers Finalized Without Approval" and "Humans stay the gate". Frame autonomy as **governed autonomy** (self-heal routine drift, escalate judgment, client sets the gate) unless the user explicitly re-positions — and if they do, the trust bar + principles sections must be rewritten too so the page doesn't contradict itself.
