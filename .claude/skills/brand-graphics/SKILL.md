---
name: brand-graphics
description: "Create diagrams, LinkedIn graphics, or system GIFs in the Sophon house style (light engineering/CAD look, navy palette, hand-built SVG - never AI image models for labeled diagrams). Use for any new marketing or docs visual."
---
# Sophon Brand Graphics

## Palette
Navy `#0f2a5c` (ink/headers) - blue `#2563eb` (accent) - sky `#00a8ff` - slate `#5b6b84` (muted) - light ground `#f6f8fb` with faint 30px grid `#eef2f8` - green `#2f6b4f`/`#15803d` (pass) - amber `#c8912f`/`#d29922` (review) - red `#c0392b` (break). Wordmark: Georgia serif "SOPHON" + letterspaced sans "FINANCE SYSTEMS - sophonfinance.com".

## Hard rules learned the hard way
- **Light background, dark text** for LinkedIn/professional audiences.
- **Never use AI image models for diagrams with small text** — they garble labels ("Manual scove and"). Hand-build as HTML/SVG; every character controlled. Higgsfield (`nano_banana_pro`) is OK only for texture/hero art, and output text must be proofread.
- **CPA-readable labels**: no control-theory jargon (no Sigma comparator symbols) — say "DOES IT TIE OUT?", "TIES / BREAKS / JUDGMENT", "FIX FROM SOURCE".
- Verify text fits its shape; add an auto-shrink pass or measure before shipping. Strip `<script>` from SVGs destined for GitHub (sanitized there).

## Render pipeline (this container)
```bash
/opt/pw-browsers/chromium-1194/chrome-linux/chrome --headless=new --no-sandbox --hide-scrollbars \
  --window-size=WxH --force-device-scale-factor=2 --default-background-color=FFFFFFFF \
  --screenshot=out.png file:///path/page.html
```
Read the PNG back and visually verify before delivering. Fonts: Liberation family at `/usr/share/fonts/truetype/liberation/` (Sans/Sans-Bold/Mono map to segoeui/seguisb/consola).

## System GIFs
`assets/make_system_gifs.py` — scripted terminal-frame renderer (PIL, 2x supersampled). Add a SYSTEMS entry (authentic code + real output only), then `python make_system_gifs.py <key>`. Has Linux font fallback + a `loop` icon.

## Existing assets
`assets/flows/*.svg` (numbered-card template), `assets/architecture.svg`, `assets/flows/self-healing-close-loop.svg` (CPA loop diagram), `docs/assets/self-healing-loop.svg` (site copy).
