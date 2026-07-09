"""Render an autonomous-close :class:`~close_engine.loop.LoopJournal` as Markdown
or as a self-contained, theme-aware HTML page.

Both renderers are pure functions of the journal, so output is deterministic and
byte-stable across runs.
"""

from __future__ import annotations

from html import escape

from . import money
from .loop import AUTO_POSTED, HALTED, PARTIAL, LoopJournal

# Fault name -> (control, one-line root cause) for the injected-drift table.
_FAULT_INFO: dict[str, tuple[str, str]] = {
    "interco_one_sided": ("C2", "Intercompany note lost its far leg — the lender mirror was dropped"),
    "missing_recurring_entry": ("C3", "An expected recurring accrual is silently absent from the register"),
    "rounded_total_leg": ("C8", "A clearing leg booked as round(total) instead of the sum of rounded lines"),
    "shadow_tamper": ("C9", "One posted amount is off by a single cent from the sub-ledger"),
    "prior_period_mutation": ("C10", "A signed-off, locked prior period was quietly rewritten"),
}

_VERDICT_BLURB = {
    AUTO_POSTED: "Clean. The close was posted autonomously — no human, nothing held.",
    PARTIAL: "The current period was posted autonomously. Some scope could not be "
    "certified without authority the loop does not have, so it was quarantined and "
    "logged rather than acted on.",
    HALTED: "The loop could not certify a postable close and refused to post. "
    "Escalated for investigation rather than papering over the break.",
}


def _cat(category: str) -> str:
    return category.replace("_", " ")


# --------------------------------------------------------------------------- #
# Markdown.
# --------------------------------------------------------------------------- #
def render_markdown(journal: LoopJournal) -> str:
    out: list[str] = []
    mark = {AUTO_POSTED: "✅", PARTIAL: "⚑", HALTED: "⛔"}[journal.verdict]
    out.append("# Autonomous Close Loop — Human-Out-of-the-Loop Remediation [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional, seeded data. The loop drives a *drifted* posted close back to a "
        "certifiable state by resyncing each recurring-entry category to the seeded "
        "sub-ledger of record — then posts on its own authority, quarantining what it "
        "cannot certify."
    )
    out.append("")
    out.append(f"**Verdict: {mark} {journal.verdict}** — {_VERDICT_BLURB[journal.verdict]}")
    out.append("")
    out.append(f"- Period **{journal.period}** (seed {journal.seed})")
    out.append(
        f"- Injected drift: **{len(journal.faults)}** fault(s) · "
        f"initial findings: **{len(journal.initial_findings)}**"
    )
    out.append(
        f"- Remediation turns: **{len(journal.turns)}** / budget **{journal.budget}** · "
        f"categories resynced: **{', '.join(_cat(c) for c in journal.categories_resynced) or '—'}**"
    )
    out.append(
        f"- Adjustments booked: **{journal.total_adjustments}** · "
        f"gross movement **{money.fmt(journal.total_adjustment_cents)}**"
    )
    out.append(
        f"- Quarantined: **{len(journal.quarantined)}** · halted-on: **{len(journal.halted_on)}**"
    )
    out.append("")

    if journal.faults:
        out.append("## Injected drift (the contaminated close)")
        out.append("")
        out.append("| Fault | Control | Root cause |")
        out.append("|-------|---------|------------|")
        for name in journal.faults:
            control, why = _FAULT_INFO.get(name, ("—", name))
            out.append(f"| `{name}` | `{control}` | {why} |")
        out.append("")

    out.append("## The loop, turn by turn")
    out.append("")
    if not journal.turns:
        out.append("_No remediable drift — the close reconciled to source on the first pass._")
        out.append("")
    for t in journal.turns:
        cleared = ", ".join(t.controls_cleared) or "—"
        out.append(
            f"### Turn {t.index} — resync `{_cat(t.category)}`  "
            f"·  cleared {cleared}  ·  {t.criticals_before} → {t.criticals_after} critical"
        )
        out.append("")
        if t.adjustments:
            out.append("| Entity | Account | From Dr/Cr | To Dr/Cr | Δ Dr | Δ Cr |")
            out.append("|--------|---------|-----------:|---------:|-----:|-----:|")
            for a in t.adjustments:
                out.append(
                    f"| {a.entity} | {a.account} | "
                    f"{money.fmt(a.from_debit)}/{money.fmt(a.from_credit)} | "
                    f"{money.fmt(a.to_debit)}/{money.fmt(a.to_credit)} | "
                    f"{money.fmt(a.delta_debit)} | {money.fmt(a.delta_credit)} |"
                )
        else:
            out.append("_No line movement (the category re-derived to what was already posted)._")
        out.append("")

    if journal.quarantined or journal.halted_on:
        out.append("## Held, not acted on")
        out.append("")
        for b in journal.halted_on:
            out.append(f"- **HALT** `{b.control_id}` — {b.subject} (the loop refuses to post on this)")
        for b in journal.quarantined:
            out.append(f"- **QUARANTINE** `{b.control_id}` — {b.subject} (held + logged; not auto-overwritten)")
        out.append("")

    out.append("## Why it's defensible")
    out.append("")
    out.append(
        "Autonomous does not mean ungated. The loop never invents a number: every correction "
        "is the engine's own re-derivation from the seeded sub-ledger of record, and every "
        "movement is booked as an adjustment. The ten controls remain the acceptance test — "
        "the loop only posts once they are silent over the non-quarantined scope. What it "
        "cannot certify with authority it has (a broken opening carryforward) or should not "
        "overwrite (a signed-off locked period) is held and logged, not acted on. The verdict "
        "doubles as a CI exit code."
    )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# HTML.
# --------------------------------------------------------------------------- #
_VERDICT_ACCENT = {AUTO_POSTED: "#2ea44f", PARTIAL: "#d29922", HALTED: "#d1242f"}


def _cycle_svg() -> str:
    import math

    stages = ["observe", "detect", "remediate", "re-verify", "gate"]
    n = len(stages)
    cx, cy, r = 300, 130, 96
    nodes = []
    for i, label in enumerate(stages):
        ang = -math.pi / 2 + i * (2 * math.pi / n)
        nodes.append((cx + r * math.cos(ang), cy + r * math.sin(ang), label))
    arcs = "".join(
        f'<line x1="{nodes[i][0]:.1f}" y1="{nodes[i][1]:.1f}" '
        f'x2="{nodes[(i+1) % n][0]:.1f}" y2="{nodes[(i+1) % n][1]:.1f}" '
        f'class="cyc-arc" marker-end="url(#ah)"/>'
        for i in range(n)
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="30" '
        f'class="{"cyc-node cyc-node--gate" if label == "gate" else "cyc-node"}"/>'
        f'<text x="{x:.1f}" y="{y+4:.1f}" class="cyc-lbl">{label}</text>'
        for (x, y, label) in nodes
    )
    return (
        '<svg viewBox="0 0 600 260" role="img" aria-label="Five-stage autonomous '
        'loop: observe, detect, remediate, re-verify, gate, repeating." class="cycle">'
        '<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" '
        'orient="auto"><path d="M0,0 L7,3 L0,6 Z" class="cyc-ah"/></marker></defs>'
        f'{arcs}{dots}'
        '<text x="300" y="126" class="cyc-center">repeat</text>'
        '<text x="300" y="146" class="cyc-center-sub">until certifiable</text></svg>'
    )


def render_html_body(journal: LoopJournal) -> str:
    """Return the page *body* content (self-contained styles, no <html>/<head>)."""
    accent = _VERDICT_ACCENT[journal.verdict]
    mark = {AUTO_POSTED: "✓", PARTIAL: "⚑", HALTED: "✕"}[journal.verdict]

    def stat(value: str, label: str) -> str:
        return (
            f'<div class="stat"><div class="stat-v">{escape(value)}</div>'
            f'<div class="stat-l">{escape(label)}</div></div>'
        )

    stats = "".join([
        stat(journal.period, "close period"),
        stat(str(len(journal.initial_findings)), "findings at start"),
        stat(str(len(journal.turns)), "remediation turns"),
        stat(", ".join(_cat(c) for c in journal.categories_resynced) or "—", "categories resynced"),
        stat(money.fmt(journal.total_adjustment_cents), "gross movement booked"),
        stat(f"{len(journal.quarantined) + len(journal.halted_on)}", "held, not acted on"),
    ])

    faults_rows = "".join(
        f"<tr><td><code>{escape(name)}</code></td>"
        f"<td><code>{escape(_FAULT_INFO.get(name, ('—', ''))[0])}</code></td>"
        f"<td>{escape(_FAULT_INFO.get(name, ('', name))[1])}</td></tr>"
        for name in journal.faults
    )
    faults_block = (
        '<section><h2>Injected drift</h2>'
        '<p class="muted">The posted close arrives contaminated. Each fault names the control '
        'that catches it — the same catalogue the Close Sentinel is proven against.</p>'
        f'<div class="tw"><table><thead><tr><th>Fault</th><th>Control</th><th>Root cause</th>'
        f'</tr></thead><tbody>{faults_rows}</tbody></table></div></section>'
        if journal.faults else ""
    )

    turn_cards = []
    for t in journal.turns:
        if t.adjustments:
            adj = (
                '<div class="tw"><table class="adj"><thead><tr><th>Entity</th><th>Account</th>'
                '<th class="num">From Dr/Cr</th><th class="num">To Dr/Cr</th>'
                '<th class="num">Δ Dr</th><th class="num">Δ Cr</th></tr></thead><tbody>'
                + "".join(
                    f'<tr><td>{escape(a.entity)}</td><td>{escape(a.account)}</td>'
                    f'<td class="num">{money.fmt(a.from_debit)}/{money.fmt(a.from_credit)}</td>'
                    f'<td class="num">{money.fmt(a.to_debit)}/{money.fmt(a.to_credit)}</td>'
                    f'<td class="num delta">{money.fmt(a.delta_debit)}</td>'
                    f'<td class="num delta">{money.fmt(a.delta_credit)}</td></tr>'
                    for a in t.adjustments
                )
                + "</tbody></table></div>"
            )
        else:
            adj = '<p class="muted">No line movement — the category re-derived to what was already posted.</p>'
        cleared = " ".join(f'<span class="pill">{escape(c)}</span>' for c in t.controls_cleared) or "—"
        bar = _breakbar(t.criticals_before, t.criticals_after, len(journal.initial_findings))
        turn_cards.append(
            f'<div class="turn"><div class="turn-h"><span class="turn-n">Turn {t.index}</span>'
            f'<span class="turn-cat">resync {escape(_cat(t.category))}</span>'
            f'<span class="turn-cleared">cleared {cleared}</span></div>{bar}{adj}</div>'
        )
    if not journal.turns:
        turn_cards.append(
            '<div class="turn"><p class="muted">No remediable drift — the close reconciled '
            'to source on the first pass.</p></div>'
        )
    turns_block = f'<section><h2>The loop, turn by turn</h2>{"".join(turn_cards)}</section>'

    held_items = "".join(
        f'<li><span class="tag tag-halt">HALT</span> <code>{escape(b.control_id)}</code> — '
        f'{escape(b.subject)} <span class="muted">· the loop refuses to post on this</span></li>'
        for b in journal.halted_on
    ) + "".join(
        f'<li><span class="tag tag-q">QUARANTINE</span> <code>{escape(b.control_id)}</code> — '
        f'{escape(b.subject)} <span class="muted">· held + logged, never auto-overwritten</span></li>'
        for b in journal.quarantined
    )
    held_block = (
        f'<section><h2>Held, not acted on</h2>'
        f'<p class="muted">The boundary of autonomy: what the loop has no authority to fabricate '
        f'or overwrite, it holds and logs instead of touching.</p><ul class="held">{held_items}</ul></section>'
        if held_items else ""
    )

    return f"""<style>{_CSS}</style>
<main class="wrap" style="--accent:{accent}">
  <header class="hero">
    <div class="eyebrow">Sophon Finance Systems · Month-End Close Engine</div>
    <h1>Autonomous Close Loop</h1>
    <p class="lede">A human-out-of-the-loop remediation controller: it drives a <strong>drifted</strong>
      posted close back to a certifiable state, resyncing each recurring-entry category to the seeded
      sub-ledger of record, then posts on its own authority — and <strong>quarantines what it cannot
      certify</strong>.</p>
    <div class="verdict" role="status">
      <span class="v-badge">{mark}</span>
      <div><div class="v-word">{escape(journal.verdict)}</div>
      <div class="v-blurb">{escape(_VERDICT_BLURB[journal.verdict])}</div></div>
    </div>
    <p class="fic">🔒 Fully fictional, seeded data. No real entity, figure, or methodology.</p>
  </header>

  <section class="cycle-wrap">
    {_cycle_svg()}
    <ol class="legend">
      <li><b>observe</b> — run the ten-control Close Sentinel</li>
      <li><b>detect</b> — find the earliest category that disagrees with source</li>
      <li><b>remediate</b> — resync it to the authoritative re-derivation; book the movement</li>
      <li><b>re-verify</b> — re-run the controls</li>
      <li><b>gate</b> — post autonomously, or quarantine / halt what it can't certify</li>
    </ol>
  </section>

  <section class="stats">{stats}</section>

  {faults_block}
  {turns_block}
  {held_block}

  <section class="how">
    <h2>Why it's defensible</h2>
    <p>Autonomous does not mean ungated — the gate is a deterministic, logged policy instead of a
    person. The loop never invents a number: every correction is the engine's own re-derivation from
    the seeded sub-ledger of record, booked as an adjustment. The ten controls remain the acceptance
    test; the loop only posts once they fall silent over the non-quarantined scope. A broken opening
    carryforward it will not fabricate; a signed-off locked period it will not overwrite — both are
    held and logged. The verdict doubles as a CI exit code.</p>
  </section>

  <footer class="foot">Generated deterministically from <code>close_engine.loop</code> ·
  fictional data · re-runnable and diffable.</footer>
</main>"""


def _breakbar(before: int, after: int, scale: int) -> str:
    scale = max(scale, before, 1)
    wb, wa = round(100 * before / scale), round(100 * after / scale)
    return (
        '<div class="bars">'
        f'<div class="bar"><span class="bar-l">in</span>'
        f'<div class="track"><i style="width:{wb}%" class="fill fill-in"></i></div>'
        f'<span class="bar-n">{before}</span></div>'
        f'<div class="bar"><span class="bar-l">out</span>'
        f'<div class="track"><i style="width:{wa}%" class="fill fill-out"></i></div>'
        f'<span class="bar-n">{after}</span></div></div>'
    )


def render_html_document(journal: LoopJournal) -> str:
    """Return a full standalone HTML document (for committing / opening directly)."""
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Autonomous Close Loop — {escape(journal.verdict)}</title>\n"
        "</head>\n<body>\n"
        f"{render_html_body(journal)}\n"
        "</body>\n</html>\n"
    )


_CSS = """
*{box-sizing:border-box}
:root{
  --bg:#f5f7fa; --panel:#ffffff; --ink:#161c26; --muted:#556074; --line:#e2e7ef;
  --accent:#2f6f9f; --good:#2ea44f; --bad:#c9382f;
  --code:#123a5c; --codebg:#eaf1f7; --shadow:0 1px 3px rgba(20,30,45,.08);
}
@media (prefers-color-scheme:dark){
  :root{--bg:#0d1117; --panel:#151b24; --ink:#e6ecf3; --muted:#93a0b3; --line:#26303d;
        --good:#3fb862; --bad:#e06b62; --code:#8fc7ee; --codebg:#122231; --shadow:0 1px 3px rgba(0,0,0,.4);}
}
:root[data-theme="light"]{--bg:#f5f7fa;--panel:#fff;--ink:#161c26;--muted:#556074;--line:#e2e7ef;--good:#2ea44f;--bad:#c9382f;--code:#123a5c;--codebg:#eaf1f7;--shadow:0 1px 3px rgba(20,30,45,.08)}
:root[data-theme="dark"]{--bg:#0d1117;--panel:#151b24;--ink:#e6ecf3;--muted:#93a0b3;--line:#26303d;--good:#3fb862;--bad:#e06b62;--code:#8fc7ee;--codebg:#122231;--shadow:0 1px 3px rgba(0,0,0,.4)}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px 60px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.85em;
  color:var(--code);background:var(--codebg);padding:1px 5px;border-radius:5px}
h1{font-size:2.05rem;margin:.1em 0 .3em;letter-spacing:-.022em;text-wrap:balance}
h2{font-size:1.15rem;margin:2.2em 0 .7em;padding-bottom:.35em;border-bottom:1px solid var(--line);text-wrap:balance}
.eyebrow{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
.lede{font-size:1.05rem;color:var(--muted);max-width:64ch}
.fic{font-size:.8rem;color:var(--muted);margin-top:1.2em}
.muted{color:var(--muted)}
.verdict{display:flex;gap:16px;align-items:center;margin:1.4em 0 .4em;padding:16px 18px;
  background:var(--panel);border:1px solid var(--line);border-left:5px solid var(--accent);
  border-radius:12px;box-shadow:var(--shadow)}
.v-badge{flex:0 0 auto;width:46px;height:46px;border-radius:50%;background:var(--accent);
  color:#fff;font-size:1.5rem;font-weight:800;display:grid;place-items:center}
.v-word{font-weight:800;font-size:1.1rem;color:var(--accent);letter-spacing:.02em}
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
.legend{margin:0;padding-left:1.1em;font-size:.9rem;color:var(--muted);max-width:340px}
.legend li{margin:.25em 0}.legend b{color:var(--ink)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:1.6em 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}
.stat-v{font-size:1.25rem;font-weight:800;letter-spacing:-.01em}
.stat-l{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:2px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.86rem;margin:.3em 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.delta{font-weight:700}
.turn{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0;box-shadow:var(--shadow)}
.turn-h{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}
.turn-n{font-weight:800}
.turn-cat{font-size:.75rem;font-weight:700;color:var(--accent);background:var(--codebg);padding:2px 9px;border-radius:20px}
.turn-cleared{font-size:.82rem;color:var(--muted);margin-left:auto;display:flex;gap:5px;align-items:center;flex-wrap:wrap}
.pill{font-size:.72rem;font-weight:700;color:var(--good);border:1px solid var(--good);border-radius:20px;padding:1px 7px}
.bars{display:flex;gap:18px;margin:.4em 0 .8em;flex-wrap:wrap}
.bar{display:flex;align-items:center;gap:8px;flex:1;min-width:180px}
.bar-l{font-size:.72rem;color:var(--muted);width:22px}
.bar-n{font-size:.8rem;font-weight:700;font-variant-numeric:tabular-nums;width:26px;text-align:right}
.track{flex:1;height:8px;background:var(--codebg);border-radius:6px;overflow:hidden}
.fill{display:block;height:100%;transition:width .2s ease}
.fill-in{background:var(--bad)}.fill-out{background:var(--good)}
@media(prefers-reduced-motion:reduce){.fill{transition:none}}
.held{list-style:none;padding:0;margin:.5em 0;display:flex;flex-direction:column;gap:8px}
.held li{padding:10px 12px;background:var(--panel);border:1px solid var(--line);border-radius:10px;font-size:.9rem}
.tag{font-size:.68rem;font-weight:800;letter-spacing:.05em;padding:1px 7px;border-radius:5px;color:#fff}
.tag-halt{background:var(--bad)}.tag-q{background:#d29922}
.how p{color:var(--muted);max-width:72ch}
.foot{margin-top:2.4em;padding-top:1em;border-top:1px solid var(--line);font-size:.78rem;color:var(--muted)}
@media(max-width:560px){h1{font-size:1.6rem}.turn-cleared{margin-left:0}}
"""
