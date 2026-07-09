"""Render a :class:`~surplus_engine.loop.LoopJournal` as Markdown or as a
self-contained, theme-aware HTML page.

Both renderers are pure functions of the journal (and the structure, for entity
display names), so their output is deterministic and byte-stable across runs.
"""

from __future__ import annotations

from html import escape
from typing import List

from .loop import FAIL, FLAG, PASS, LoopJournal
from .model import Structure


def _money(x: float) -> str:
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def _signed(x: float) -> str:
    return f"+{x:,.2f}" if x >= 0 else f"({abs(x):,.2f})"


def _name(structure: Structure, code: str) -> str:
    ent = structure.entities.get(code)
    return ent.name if ent else code


_VERDICT_BLURB = {
    PASS: "Converged. Booked adjustments are immaterial — clean to sign off.",
    FLAG: "Converged, but material adjustments were booked. A human must review "
    "what changed before sign-off, even though every identity now ties.",
    FAIL: "Did not converge within the turn budget. Escalate to a human — the "
    "workpapers still fail at least one structural identity.",
}


# --------------------------------------------------------------------------- #
# Markdown.
# --------------------------------------------------------------------------- #
def render_markdown(journal: LoopJournal, structure: Structure) -> str:
    out: List[str] = []
    mark = {PASS: "✅", FLAG: "⚑", FAIL: "❌"}[journal.verdict]
    out.append("# Surplus Assurance Loop — Continuous Reconciliation [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional data. The loop drives a *drifted* workpaper set back to a "
        "clean structural tie-out by re-deriving each fiscal period from cited "
        "source facts — one locked period at a time — then hands a verdict to a human."
    )
    out.append("")
    out.append(f"**Verdict: {mark} {journal.verdict}** — {_VERDICT_BLURB[journal.verdict]}")
    out.append("")
    out.append(
        f"- Fiscal range **{journal.start_year}–{journal.end_year}** · "
        f"**{journal.checks_total}** structural identity checks per pass"
    )
    out.append(
        f"- Injected drift: **{len(journal.faults)}** fault(s) · "
        f"initial breaks: **{len(journal.initial_breaks)}**"
    )
    out.append(
        f"- Remediation turns: **{len(journal.turns)}** / budget **{journal.budget}** · "
        f"periods locked: **{', '.join(str(y) for y in journal.periods_locked) or '—'}**"
    )
    out.append(
        f"- Adjustments booked: **{journal.total_adjustments}** · "
        f"total magnitude **CAD {_money(journal.total_adjustment_cad)}** · "
        f"materiality **CAD {_money(journal.materiality_cad)}**"
    )
    out.append(f"- Converged: **{'yes' if journal.converged else 'no'}**")
    out.append("")

    if journal.faults:
        out.append("## Injected drift (the contaminated workpapers)")
        out.append("")
        out.append("| Fault | Entity | FY | Root cause | Control that must catch it |")
        out.append("|-------|--------|----|------------|----------------------------|")
        for f in journal.faults:
            out.append(
                f"| `{f.id}` | {_name(structure, f.entity)} | {f.year} | {f.title} | `{f.control}` |"
            )
        out.append("")

    out.append("## The loop, turn by turn")
    out.append("")
    if not journal.turns:
        out.append("_No drift detected — every identity reconciled on the first pass. Nothing to remediate._")
        out.append("")
    for t in journal.turns:
        out.append(
            f"### Turn {t.index} — lock FY{t.year_settled}  "
            f"·  {len(t.breaks_before)} break(s) in → {t.breaks_after_count} out "
            f"({t.cleared} cleared)"
        )
        out.append("")
        if t.adjustments:
            out.append("| Entity | FY | Field | From | To | Δ (FC) | Δ (CAD) |")
            out.append("|--------|----|-------|-----:|---:|-------:|--------:|")
            for a in t.adjustments:
                out.append(
                    f"| {_name(structure, a.entity)} | {a.year} | `{a.field}` | "
                    f"{_money(a.from_value)} | {_money(a.to_value)} | "
                    f"{_signed(a.delta)} | {_money(a.delta_cad)} |"
                )
        else:
            out.append("_No field corrections this turn (the period re-derived to what was already stored)._")
        out.append("")

    out.append("## How it works")
    out.append("")
    out.append(
        "Each turn the loop **observes** (runs the reconciliation harness), "
        "**detects** the earliest fiscal period that still fails an identity, "
        "**remediates** it by re-deriving the period from source facts via the engine "
        "(booking every field change as an adjustment), locks the period, and "
        "**re-verifies**. It repeats until all identities across every period and tier "
        "reconcile — or the turn budget is exhausted. The loop never invents a number: "
        "the final workpaper set is byte-identical to a clean engine run. A human gate "
        "returns PASS / FLAG / FAIL."
    )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# HTML.
# --------------------------------------------------------------------------- #
_VERDICT_ACCENT = {PASS: "#2ea44f", FLAG: "#d29922", FAIL: "#d1242f"}


def _cycle_svg(active_stage: int = -1) -> str:
    """Inline SVG of the five-stage loop cycle."""
    stages = ["observe", "detect", "remediate", "re-verify", "gate"]
    n = len(stages)
    cx, cy, r = 300, 130, 96
    import math

    nodes = []
    for i, label in enumerate(stages):
        ang = -math.pi / 2 + i * (2 * math.pi / n)
        x = cx + r * math.cos(ang)
        y = cy + r * math.sin(ang)
        nodes.append((x, y, label))
    # Arrows between consecutive nodes (along the circle).
    arcs = []
    for i in range(n):
        x1, y1, _ = nodes[i]
        x2, y2, _ = nodes[(i + 1) % n]
        arcs.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'class="cyc-arc" marker-end="url(#ah)"/>'
        )
    dots = []
    for i, (x, y, label) in enumerate(nodes):
        cls = "cyc-node cyc-node--gate" if label == "gate" else "cyc-node"
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="30" class="{cls}"/>'
            f'<text x="{x:.1f}" y="{y+4:.1f}" class="cyc-lbl">{label}</text>'
        )
    return (
        f'<svg viewBox="0 0 600 260" role="img" aria-label="Five-stage loop: '
        f'observe, detect, remediate, re-verify, gate, repeating." class="cycle">'
        f'<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" '
        f'orient="auto"><path d="M0,0 L7,3 L0,6 Z" class="cyc-ah"/></marker></defs>'
        f'{"".join(arcs)}{"".join(dots)}'
        f'<text x="300" y="126" class="cyc-center">repeat</text>'
        f'<text x="300" y="146" class="cyc-center-sub">until it ties</text>'
        f'</svg>'
    )


def render_html_body(journal: LoopJournal, structure: Structure) -> str:
    """Return the page *body* content (self-contained styles, no <html>/<head>).

    Suitable for the Artifact renderer, which supplies the document skeleton.
    """
    accent = _VERDICT_ACCENT[journal.verdict]
    mark = {PASS: "✓", FLAG: "⚑", FAIL: "✕"}[journal.verdict]

    def stat(value: str, label: str) -> str:
        return (
            f'<div class="stat"><div class="stat-v">{escape(value)}</div>'
            f'<div class="stat-l">{escape(label)}</div></div>'
        )

    stats = "".join([
        stat(f"{journal.start_year}–{journal.end_year}", "fiscal range"),
        stat(str(journal.checks_total), "identity checks / pass"),
        stat(str(len(journal.initial_breaks)), "breaks at start"),
        stat(f"{len(journal.turns)}", "remediation turns"),
        stat(", ".join(str(y) for y in journal.periods_locked) or "—", "periods locked"),
        stat(f"CAD {_money(journal.total_adjustment_cad)}", "adjustments booked"),
    ])

    # Injected faults.
    faults_rows = "".join(
        f"<tr><td><code>{escape(f.id)}</code></td>"
        f"<td>{escape(_name(structure, f.entity))}</td><td>{f.year}</td>"
        f"<td>{escape(f.title)}</td><td><code>{escape(f.control)}</code></td></tr>"
        for f in journal.faults
    )
    faults_block = (
        f'<section><h2>Injected drift</h2>'
        f'<p class="muted">The stored workpapers arrive contaminated — the kind of drift a '
        f'reviewer meets in real month-end work. Each fault names the control that must catch it.</p>'
        f'<div class="tw"><table><thead><tr><th>Fault</th><th>Entity</th><th>FY</th>'
        f'<th>Root cause</th><th>Control</th></tr></thead><tbody>{faults_rows}</tbody></table></div>'
        f'</section>'
        if journal.faults else ""
    )

    # Turns timeline.
    turn_cards = []
    for t in journal.turns:
        if t.adjustments:
            adj = (
                '<div class="tw"><table class="adj"><thead><tr><th>Entity</th><th>FY</th>'
                '<th>Field</th><th class="num">From</th><th class="num">To</th>'
                '<th class="num">Δ FC</th><th class="num">Δ CAD</th></tr></thead><tbody>'
                + "".join(
                    f'<tr><td>{escape(_name(structure, a.entity))}</td><td>{a.year}</td>'
                    f'<td><code>{escape(a.field)}</code></td>'
                    f'<td class="num">{_money(a.from_value)}</td>'
                    f'<td class="num">{_money(a.to_value)}</td>'
                    f'<td class="num delta">{_signed(a.delta)}</td>'
                    f'<td class="num">{_money(a.delta_cad)}</td></tr>'
                    for a in t.adjustments
                )
                + "</tbody></table></div>"
            )
        else:
            adj = '<p class="muted">No field corrections — the period re-derived to what was already stored.</p>'
        bar = _breakbar(len(t.breaks_before), t.breaks_after_count, len(journal.initial_breaks))
        turn_cards.append(
            f'<div class="turn"><div class="turn-h">'
            f'<span class="turn-n">Turn {t.index}</span>'
            f'<span class="turn-lock">lock FY{t.year_settled}</span>'
            f'<span class="turn-delta">{len(t.breaks_before)} → {t.breaks_after_count} breaks '
            f'<em>({t.cleared} cleared)</em></span></div>'
            f'{bar}{adj}</div>'
        )
    if not journal.turns:
        turn_cards.append(
            '<div class="turn"><p class="muted">No drift detected — every identity reconciled '
            'on the first pass. Nothing to remediate.</p></div>'
        )
    turns_block = f'<section><h2>The loop, turn by turn</h2>{"".join(turn_cards)}</section>'

    return f"""<style>{_CSS}</style>
<main class="wrap" style="--accent:{accent}">
  <header class="hero">
    <div class="eyebrow">Sophon Finance Systems · Tax Surplus / ACB Engine</div>
    <h1>Surplus Assurance Loop</h1>
    <p class="lede">A bounded, human-gated control loop that drives a <strong>drifted</strong>
      workpaper set back to a clean structural tie-out — re-deriving each fiscal period from
      cited source facts, one locked period at a time — then hands a verdict to a person.</p>
    <div class="verdict" role="status">
      <span class="v-badge">{mark}</span>
      <div><div class="v-word">{journal.verdict}</div>
      <div class="v-blurb">{escape(_VERDICT_BLURB[journal.verdict])}</div></div>
    </div>
    <p class="fic">🔒 Fully fictional, seeded data. No real entity, figure, or methodology.</p>
  </header>

  <section class="cycle-wrap">
    {_cycle_svg()}
    <ol class="legend">
      <li><b>observe</b> — run the {journal.checks_total}-check reconciliation harness</li>
      <li><b>detect</b> — find the earliest fiscal period still failing an identity</li>
      <li><b>remediate</b> — re-derive that period from source; book the corrections</li>
      <li><b>re-verify</b> — reconcile again; lock the period</li>
      <li><b>gate</b> — PASS / FLAG / FAIL to a human</li>
    </ol>
  </section>

  <section class="stats">{stats}</section>

  {faults_block}
  {turns_block}

  <section class="how">
    <h2>Why it's defensible</h2>
    <p>The loop never invents a number. Every correction is the engine's own re-derivation from
    the cited source facts, and the final workpaper set is <strong>byte-identical to a clean engine
    run</strong>. The reconciliation harness — {journal.checks_total} named structural identities
    (conservation, roll-forward continuity, elevation, ACB, per-layer FX) — is both the loop's
    sensor and its acceptance test. Convergence is bounded by a turn budget; if it can't tie out,
    it escalates rather than papering over the break. The verdict doubles as a CI exit code.</p>
  </section>

  <footer class="foot">Generated deterministically from <code>surplus_engine.loop</code> ·
  fictional data · re-runnable and diffable.</footer>
</main>"""


def _breakbar(before: int, after: int, scale: int) -> str:
    scale = max(scale, before, 1)
    wb = round(100 * before / scale)
    wa = round(100 * after / scale)
    return (
        f'<div class="bars">'
        f'<div class="bar"><span class="bar-l">in</span>'
        f'<div class="track"><i style="width:{wb}%" class="fill fill-in"></i></div>'
        f'<span class="bar-n">{before}</span></div>'
        f'<div class="bar"><span class="bar-l">out</span>'
        f'<div class="track"><i style="width:{wa}%" class="fill fill-out"></i></div>'
        f'<span class="bar-n">{after}</span></div></div>'
    )


def render_html_document(journal: LoopJournal, structure: Structure) -> str:
    """Return a full standalone HTML document (for committing / opening directly)."""
    body = render_html_body(journal, structure)
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Surplus Assurance Loop — {journal.verdict}</title>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


_CSS = """
*{box-sizing:border-box}
:root{
  --bg:#f6f8f5; --panel:#ffffff; --ink:#18201a; --muted:#586a5b; --line:#e2e8df;
  --accent:#2ea44f; --good:#2ea44f; --bad:#c9382f;
  --code:#0b3d2e; --codebg:#eef4ee; --shadow:0 1px 3px rgba(20,40,20,.07);
}
@media (prefers-color-scheme:dark){
  :root{--bg:#0e130f; --panel:#161d17; --ink:#e8efe6; --muted:#94a494; --line:#273028;
        --good:#3fb862; --bad:#e06b62; --code:#8fe3b8; --codebg:#12241a; --shadow:0 1px 3px rgba(0,0,0,.4);}
}
:root[data-theme="light"]{--bg:#f6f8f5;--panel:#fff;--ink:#18201a;--muted:#586a5b;--line:#e2e8df;--good:#2ea44f;--bad:#c9382f;--code:#0b3d2e;--codebg:#eef4ee;--shadow:0 1px 3px rgba(20,40,20,.07)}
:root[data-theme="dark"]{--bg:#0e130f;--panel:#161d17;--ink:#e8efe6;--muted:#94a494;--line:#273028;--good:#3fb862;--bad:#e06b62;--code:#8fe3b8;--codebg:#12241a;--shadow:0 1px 3px rgba(0,0,0,.4)}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px 60px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.85em;
  color:var(--code);background:var(--codebg);padding:1px 5px;border-radius:5px}
h1{font-size:2.05rem;margin:.1em 0 .3em;letter-spacing:-.022em;text-wrap:balance}
h2{font-size:1.15rem;margin:2.2em 0 .7em;padding-bottom:.35em;border-bottom:1px solid var(--line);text-wrap:balance}
.eyebrow{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
.lede{font-size:1.05rem;color:var(--muted);max-width:62ch}
.fic{font-size:.8rem;color:var(--muted);margin-top:1.2em}
.muted{color:var(--muted)}
.verdict{display:flex;gap:16px;align-items:center;margin:1.4em 0 .4em;padding:16px 18px;
  background:var(--panel);border:1px solid var(--line);border-left:5px solid var(--accent);
  border-radius:12px;box-shadow:var(--shadow)}
.v-badge{flex:0 0 auto;width:46px;height:46px;border-radius:50%;background:var(--accent);
  color:#fff;font-size:1.5rem;font-weight:800;display:grid;place-items:center}
.v-word{font-weight:800;font-size:1.15rem;color:var(--accent);letter-spacing:.02em}
.v-blurb{font-size:.9rem;color:var(--muted)}
.cycle-wrap{display:flex;gap:20px;flex-wrap:wrap;align-items:center;justify-content:center;
  margin:2em 0;padding:18px;background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}
.cycle{width:min(100%,420px);height:auto}
.cyc-arc{stroke:var(--accent);stroke-width:2;opacity:.55}
.cyc-ah{fill:var(--accent)}
.cyc-node{fill:var(--panel);stroke:var(--accent);stroke-width:2}
.cyc-node--gate{fill:var(--accent)}
.cyc-lbl{fill:var(--ink);font-size:11px;font-weight:600;text-anchor:middle}
.cyc-node--gate + .cyc-lbl{fill:#fff}
.cyc-center{fill:var(--ink);font-size:15px;font-weight:800;text-anchor:middle}
.cyc-center-sub{fill:var(--muted);font-size:10px;text-anchor:middle}
.legend{margin:0;padding-left:1.1em;font-size:.9rem;color:var(--muted);max-width:320px}
.legend li{margin:.25em 0}
.legend b{color:var(--ink)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:1.6em 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}
.stat-v{font-size:1.3rem;font-weight:800;letter-spacing:-.01em}
.stat-l{font-size:.74rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:2px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.88rem;margin:.3em 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.delta{font-weight:700}
.turn{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;margin:12px 0;box-shadow:var(--shadow)}
.turn-h{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}
.turn-n{font-weight:800}
.turn-lock{font-size:.75rem;font-weight:700;color:var(--accent);background:var(--codebg);
  padding:2px 9px;border-radius:20px}
.turn-delta{font-size:.85rem;color:var(--muted);margin-left:auto}
.turn-delta em{color:var(--accent);font-style:normal;font-weight:700}
.bars{display:flex;gap:18px;margin:.4em 0 .8em;flex-wrap:wrap}
.bar{display:flex;align-items:center;gap:8px;flex:1;min-width:180px}
.bar-l{font-size:.72rem;color:var(--muted);width:22px}
.bar-n{font-size:.8rem;font-weight:700;font-variant-numeric:tabular-nums;width:26px;text-align:right}
.track{flex:1;height:8px;background:var(--codebg);border-radius:6px;overflow:hidden}
.fill{display:block;height:100%;transition:width .2s ease}
.fill-in{background:var(--bad)}
.fill-out{background:var(--good)}
@media(prefers-reduced-motion:reduce){.fill{transition:none}}
.how p{color:var(--muted);max-width:70ch}
.foot{margin-top:2.4em;padding-top:1em;border-top:1px solid var(--line);font-size:.78rem;color:var(--muted)}
@media(max-width:560px){h1{font-size:1.6rem}.turn-delta{margin-left:0}}
"""
