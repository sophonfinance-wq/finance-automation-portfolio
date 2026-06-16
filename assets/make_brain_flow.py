"""Generate assets/flows/brain-flow.svg — the animated "moving parts" flow chart
for the Knowledge Brain engine.

Matches the visual language of the other flow SVGs in this folder: a tall,
mobile-first card stack with numbered steps, chips, animated connector traces,
moving diamond particles, and a staggered green-burst pulse on each card.

Run:  python make_brain_flow.py   ->  writes ./flows/brain-flow.svg
"""

from pathlib import Path

OUT = Path(__file__).parent / "flows" / "brain-flow.svg"
OUT.parent.mkdir(exist_ok=True)

ACCENT = "#4f46e5"        # indigo — the brain's distinct accent
TITLE = "Knowledge Brain"
SUBTITLE = "Carries the laws and the corrections — cite them, or auto-apply them hands-free."

# (step title, body line 1, body line 2, [chips])
STEPS = [
    ("Record the meeting",
     "Every engagement meeting is captured live as",
     "audio — nothing is lost to memory.",
     ["Audio", "Live"]),
    ("Transcribe with timestamps",
     "Speaker-tagged utterances, each stamped to the",
     "second (HH:MM:SS).",
     ["Speaker", "HH:MM:SS"]),
    ("Ingest: laws + corrections",
     "Authoritative rules AND reviewer change-requests",
     "become cards with full provenance.",
     ["Law", "Decision", "Directive"]),
    ("Index the brain",
     "A deterministic TF-IDF index over every card,",
     "organised by topic.",
     ["Topic", "TF-IDF"]),
    ("Query the brain",
     "Ask it, prep for a meeting, or cite a prior",
     "decision word-for-word.",
     ["Ask", "Prep", "Cite"]),
    ("Reviewer corrections → directives",
     "A review transcript becomes a cited, executable",
     "list of the exact changes requested.",
     ["Verbatim", "Cited"]),
    ("Auto-apply, hands-free",
     "The brain writes the prompt; you copy-paste it;",
     "the AI applies every change, traced to source.",
     ["Copy-paste", "Change-log"]),
]

CARD_H = 200
GAP = 44
TOP = 128
W = 640
LEFT = 16
CARD_W = 608
DUR = 10.8
N = len(STEPS)

card_tops = [TOP + i * (CARD_H + GAP) for i in range(N)]
height = card_tops[-1] + CARD_H + 28
rw = 1300
rh = round(height * rw / W)

defs = f'''  <defs>
    <filter id="green-explode" x="-35%" y="-55%" width="170%" height="210%">
      <feGaussianBlur stdDeviation="5.2" result="greenBlur"/>
      <feColorMatrix in="greenBlur" type="matrix" values="0 0 0 0 0 0 0 0 0 1 0 0 0 0 0.34 0 0 0 1 0" result="greenGlow"/>
      <feMerge><feMergeNode in="greenGlow"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <linearGradient id="diamond-blue" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0" stop-color="#4f46e5"/>
      <stop offset="0.42" stop-color="#eef2ff"/>
      <stop offset="0.68" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#818cf8"/>
    </linearGradient>
    <filter id="diamond-glow" x="-95%" y="-95%" width="290%" height="290%">
      <feGaussianBlur stdDeviation="4.8" result="blur"/>
      <feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.31 0 0 0 0 0.27 0 0 0 0 0.9 0 0 0 1 0" result="iBlur"/>
      <feMerge><feMergeNode in="iBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <marker id="arrow-i" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="{ACCENT}"/></marker>
    <style>
  .t {{ font-family: 'Segoe UI', Arial, sans-serif; }}
  .title {{ font-size: 36px; font-weight: 850; fill: #0f172a; }}
  .subtitle {{ font-size: 20px; fill: #334155; }}
  .step-title {{ font-size: 27px; font-weight: 820; fill: #0f172a; }}
  .body {{ font-size: 22px; fill: #334155; }}
  .chip {{ font-size: 15px; font-weight: 780; fill: #0f172a; }}
  .num {{ font-size: 20px; font-weight: 900; fill: #ffffff; }}
  @keyframes flowCardPulse {{
    0%, 100% {{ fill: #ffffff; fill-opacity: 1; stroke-width: 2; filter: none; transform: scale(1); }}
    4% {{ fill: #e0e7ff; fill-opacity: .92; stroke: {ACCENT}; stroke-width: 4; filter: url(#green-explode); transform: scale(1.004); }}
    8% {{ fill: #c7d2fe; fill-opacity: .62; stroke: #6366f1; stroke-width: 6; filter: url(#green-explode); transform: scale(1.012); }}
    12% {{ fill: #e0e7ff; fill-opacity: .82; stroke: {ACCENT}; stroke-width: 4; filter: url(#green-explode); transform: scale(1.004); }}
    18% {{ fill: #ffffff; fill-opacity: 1; stroke-width: 2; filter: none; transform: scale(1); }}
  }}
  @keyframes chipPulse {{
    0%, 100% {{ fill: #ffffff; fill-opacity: 1; filter: none; transform: scale(1); }}
    6% {{ fill: #e0e7ff; fill-opacity: .95; stroke: {ACCENT}; filter: url(#green-explode); transform: scale(1.03); }}
    14% {{ fill: #ffffff; fill-opacity: 1; filter: none; transform: scale(1); }}
  }}
  @keyframes traceFlow {{ to {{ stroke-dashoffset: -52; }} }}
  .flow-trace {{ stroke: {ACCENT}; stroke-width: 10; stroke-linecap: round; stroke-dasharray: 20 36; opacity: .9; animation: traceFlow 4.4s linear infinite; filter: url(#diamond-glow); }}
  .flow-diamond {{ filter: url(#diamond-glow); }}
  .flow-card {{ transform-box: fill-box; transform-origin: center; animation: flowCardPulse {DUR}s ease-in-out infinite; }}
  .chip-pill {{ transform-box: fill-box; transform-origin: center; animation: chipPulse {DUR}s ease-in-out infinite; }}
  @media (prefers-reduced-motion: reduce) {{
    .flow-card, .chip-pill, .flow-trace {{ animation: none; }}
    .flow-particle, .flow-trace {{ display: none; }}
  }}
    </style>
  </defs>'''

parts = []
parts.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" '
    f'width="{rw}" height="{rh}" role="img" aria-label="{TITLE}" '
    f'text-rendering="geometricPrecision" shape-rendering="geometricPrecision">'
)
parts.append(defs)
parts.append(f'<rect width="{W}" height="{height}" fill="#f8fafc"/>')
parts.append(f'<rect x="0" y="0" width="8" height="{height}" fill="{ACCENT}"/>')
parts.append(f'<text x="32" y="56" class="t title">{TITLE}</text>')
parts.append(f'<text x="32" y="88" class="t subtitle" text-anchor="start">{SUBTITLE}</text>')

for i, (title, b1, b2, chips) in enumerate(STEPS):
    cy = card_tops[i]
    delay = round(i * (DUR / N), 3)
    cls = f"flow-card flow-card-{i+1}"
    parts.append(
        f'<rect class="{cls}" style="animation-delay:{delay}s" x="{LEFT}" y="{cy}" '
        f'width="{CARD_W}" height="{CARD_H}" rx="10" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>'
    )
    parts.append(f'<circle cx="54" cy="{cy+43}" r="20" fill="{ACCENT}"/>')
    parts.append(f'<text x="54" y="{cy+51}" class="t num" text-anchor="middle">{i+1}</text>')
    parts.append(f'<text x="82" y="{cy+50}" class="t step-title" text-anchor="start">{title}</text>')
    parts.append(f'<text x="82" y="{cy+92}" class="t body" text-anchor="start">{b1}</text>')
    parts.append(f'<text x="82" y="{cy+120}" class="t body" text-anchor="start">{b2}</text>')
    cx = 92
    for c in chips:
        cw = 30 + len(c) * 11
        parts.append(
            f'<rect class="chip-pill" style="animation-delay:{delay}s" x="{cx}" y="{cy+148}" '
            f'width="{cw}" height="28" rx="6" fill="#ffffff" stroke="{ACCENT}" stroke-width="2"/>'
        )
        parts.append(f'<text x="{cx+cw/2:.0f}" y="{cy+167}" class="t chip" text-anchor="middle">{c}</text>')
        cx += cw + 10

# connectors between cards
for i in range(N - 1):
    y1 = card_tops[i] + CARD_H
    y2 = card_tops[i + 1]
    begin = round(i * (DUR / N), 3)
    parts.append(
        f'<line class="flow-trace" style="animation-delay:{round(i*1.1,3)}s" x1="320" y1="{y1}" x2="320" y2="{y2}"/>'
    )
    parts.append(
        f'<line x1="320" y1="{y1}" x2="320" y2="{y2}" stroke="{ACCENT}" stroke-width="4" '
        f'stroke-linecap="round" marker-end="url(#arrow-i)"/>'
    )
    parts.append('<g class="flow-particle" opacity="0">')
    parts.append('  <polygon class="flow-diamond" points="0,-9 9,0 0,9 -9,0" fill="url(#diamond-blue)" stroke="#ffffff" stroke-width="1.8"/>')
    parts.append('  <circle r="2.2" fill="#ffffff"/>')
    parts.append(
        f'  <animateMotion dur="{DUR}s" begin="{begin}s" repeatCount="indefinite" path="M320,{y1} L320,{y2}"/>'
        f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;0.03;0.08;0.16;0.22;1" '
        f'dur="{DUR}s" begin="{begin}s" repeatCount="indefinite"/>'
    )
    parts.append('</g>')

parts.append('</svg>')

OUT.write_text("\n".join(parts), encoding="utf-8")
print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB, {N} steps, viewBox 0 0 {W} {height})")
