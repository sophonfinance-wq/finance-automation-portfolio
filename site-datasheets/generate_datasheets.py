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


def _is_seeded(spec: dict) -> bool:
    # Honesty gate for the shared chrome: "seeded" may only be claimed when the
    # spec declares it (atlas and brain are deterministic but not seeded), and an
    # absent flag claims less, never more.
    det = spec.get("control_characteristics", {}).get("determinism", {})
    return bool(det.get("seeded"))


class Footnotes:
    """Collects (source) markers so zones 3 and 7 share one Substantiation list."""

    def __init__(self) -> None:
        self._items: list[str] = []

    def mark(self, source: str) -> str:
        self._items.append(source)
        n = len(self._items)
        return (
            f'<sup class="fn"><a id="fnref-{n}" href="#fn-{n}" '
            f'aria-label="See substantiation {n}">{n}</a></sup>'
        )

    def render(self) -> str:
        if not self._items:
            return ""
        rows = [
            (f'    <li id="fn-{i + 1}"><a class="fnid" href="#fnref-{i + 1}" '
             f'aria-label="Back to reference {i + 1}">{i + 1}</a>{_esc(s)}</li>')
            for i, s in enumerate(self._items)
        ]
        return ('<div class="subst"><span class="zone-k">Substantiation</span><ul>\n'
                + "\n".join(rows) + "\n</ul></div>")


# --- zone builders ---------------------------------------------------------

def masthead_html(spec: dict) -> str:
    part = "{} &middot; {} &middot; REV {} &middot; {}".format(
        _esc(spec["part_no"]), _esc(spec["family"].upper()),
        _esc(spec["rev"]), _esc(spec["status"]))
    legend = ("PRODUCTION = runnable end-to-end, CI-backed, full test suite passing. "
              + ("All data fictional and seeded." if _is_seeded(spec)
                 else "All data fictional."))
    thesis = _esc(spec.get("marketing_thesis", ""))
    thesis_html = (f'  <p class="thesis">{thesis}</p>\n') if thesis else ""
    return (
        '<section class="masthead">\n'
        '  <p class="kicker">ENGINE {:02d}</p>\n'
        '  <p class="partline">{}</p>\n'
        '  <p class="legend">{}</p>\n'
        '  <h1><strong>{}</strong></h1>\n'
        '  <p class="tag">{}</p>\n'
        '  <p class="intro">{}</p>\n'
        '{}'
        '  <p><a class="btn btn-p" href="{}" target="_blank" rel="noopener">Run it</a> '
        '<a class="btn btn-t" href="{}">Book a consultation</a></p>\n'
        '</section>'
    ).format(
        spec["num"], part, _esc(legend), _esc(spec["name"]),
        _esc(spec["tagline"]), _esc(spec["plain_summary"]), thesis_html,
        _esc(spec["links"]["codespaces"]), CTA_BOOK,
    )


def spec_strip_html(spec: dict, fn: Footnotes) -> str:
    cells = []
    for item in spec["spec_strip"]:
        plain = ('<div class="p">{}</div>'.format(_esc(item["plain"]))) if item.get("plain") else ""
        cells.append(
            '  <div class="cell"><div class="v">{}{}</div>'
            '<div class="l">{}</div>{}</div>'.format(_esc(item["value"]), fn.mark(item["source"]), _esc(item["label"]), plain))
    return ('<section><h2>Key specifications</h2>'
            '<span class="zone-k">at a glance</span>\n'
            '<div class="strip">\n' + "\n".join(cells) + "\n</div></section>")


def plain_terms_html(spec: dict, fn: Footnotes) -> str:
    scen = []
    for s in spec["scenarios"]:
        scen.append('  <p style="margin:10px 0"><b>{}{}.</b> {}</p>'.format(_esc(s["title"]), fn.mark(s["source"]),
                       _esc(s["narrative"])))
    return ('<section><h2>What it does for you</h2>'
            '<span class="zone-k">plain terms</span>\n'
            '  <p class="intro">{}</p>\n{}\n</section>'.format(_esc(spec["problem_statement"]), "\n".join(scen)))


def instruction_set_html(spec: dict) -> str:
    rows = []
    for op in spec["instruction_set"]:
        cmd = _esc(op["cmd"])
        rows.append(
            '  <tr><td class="mono"><div class="copyrow"><code>{}</code>'
            '<button class="copybtn" data-copy="{}" aria-label="Copy command: {}">copy</button></div></td>'
            '<td>{}</td><td class="mono">{}</td><td class="mono">{}</td><td>{}</td></tr>'.format(cmd, cmd, cmd, _esc(op["operation"]), _esc(op["output"]),
               _esc(op["exit_code"]), _esc(op["artifacts"])))
    return ('<section><h2>Instruction set</h2>'
            '<span class="zone-k">every public command</span>\n'
            '<table class="ds"><thead><tr><th>Command</th><th>Operation</th>'
            '<th>Output</th><th>Exit</th><th>Artifacts</th></tr></thead>\n'
            '<tbody>\n' + "\n".join(rows) + "\n</tbody></table></section>")


def benchmarks_html(spec: dict, fn: Footnotes) -> str:
    rows = []
    for b in spec["benchmarks"]:
        plain = ('<br><span style="color:#6f6f6f;font-size:12.5px">{}</span>'.format(_esc(b["plain"]))) if b.get("plain") else ""
        rows.append('  <tr><td>{}{}</td><td class="mono"><b>{}</b> {}</td></tr>'.format(_esc(b["label"]), fn.mark(b["source"]),
                       _esc(b["value"]), _esc(b["unit"]) + plain))
    return ('<section><h2>Benchmarks</h2>'
            '<span class="zone-k">measured demo results</span>\n'
            '<table class="ds"><thead><tr><th>Measure</th><th>Result</th></tr></thead>\n'
            '<tbody>\n' + "\n".join(rows) + "\n</tbody></table></section>")


def control_characteristics_html(spec: dict) -> str:
    cc = spec["control_characteristics"]
    det = cc["determinism"]
    det_bits = []
    if det.get("seeded"):
        det_bits.append("seeded fictional inputs")
    if det.get("read_only"):
        det_bits.append("read-only operation")
    if det.get("offline_default"):
        det_bits.append("offline default mode")
    det_text = ", ".join(det_bits) if det_bits else "see the engine source"
    guarantees = "".join(f'<li style="list-style:disc;margin-left:18px">{_esc(g)}</li>'
                          for g in cc["guarantees"])
    # Plain/engineering pair: the plain side takes the gate note when the engine has a
    # human-approval gate, otherwise an optional control summary; the demo-gate line is
    # only emitted for engines that actually have a gate policy.
    gate = cc.get("gate_policy")
    plain_text = _esc(gate["note"] if gate else cc.get("plain", ""))
    det = _esc(det_text)
    gate_line = f'<p><b>Demo gate.</b> {_esc(gate["demo_gate"])}</p>' if gate else ""
    pair = (
        '<div class="pair control-pair">'
        f'<div class="plain"><h3>Plain terms</h3><p>{plain_text}</p></div>'
        '<div class="engineering"><h3>Engineering</h3>'
        f'<p><b>Deterministic envelope.</b> {det}.</p>'
        f'{gate_line}</div></div>\n'
    )
    parts = [
        '<section><h2>Control characteristics</h2>'
        '<span class="zone-k">engineering</span>\n',
        pair,
    ]
    if cc.get("authority"):
        auth = "".join(
            '<tr><td class="mono">{}</td><td><b>{}</b></td><td>{}</td></tr>'.format(
                a["rank"], _esc(a["level"]), _esc(a["note"])
            )
            for a in cc["authority"]
        )
        parts.append(
            '<table class="ds"><thead><tr><th>Authority</th><th>Level</th><th>Note</th></tr></thead>'
            f'<tbody>{auth}</tbody></table>\n'
        )
    if cc.get("verdict_map"):
        vmap = "".join('<tr><td>{}</td><td class="mono"><b>{}</b></td><td>{}</td></tr>'.format(_esc(v["severity"]), _esc(v["verdict"]), _esc(v["action"]))
                       for v in cc["verdict_map"])
        parts.append(
            '<table class="ds" style="margin-top:14px"><thead><tr><th>Severity</th><th>Verdict</th><th>Action</th></tr></thead>'
            f'<tbody>{vmap}</tbody></table>\n'
        )
    parts.append(f'<ul style="margin-top:14px">{guarantees}</ul>\n')
    if cc.get("modes"):
        parts.append("".join('<p style="margin:8px 0"><b>{}.</b> {}</p>'.format(_esc(m["name"]), _esc(m["detail"])) for m in cc["modes"]))
    parts.append('</section>')
    return "".join(parts)


def limits_html(spec: dict, fn: Footnotes) -> str:
    items = "".join(
        '<li>{}{}</li>'.format(_esc(limit["statement"]), fn.mark(limit["source"]))
        for limit in spec["limits"]
    )
    return ('<section><h2>Operating limits</h2>'
            '<span class="zone-k">what it refuses to do</span>\n'
            f'<ul class="limits">{items}</ul></section>')


def see_it_run_html(spec: dict) -> str:
    m = spec["media"]
    crops = "".join(
        '<figure><img src="{}" alt="{}" loading="lazy">'
        '<figcaption>{}</figcaption></figure>'.format(_esc(c["path"]), _esc(c["alt"]), _esc(c["label"]))
        for c in m.get("crops", [])
    )
    crops_html = (f'<div class="media-crops">{crops}</div>') if crops else ""
    # run_label is spec-driven and honest: only a spec whose media is a genuine CLI
    # capture may say "the real CLI" (Triangulate). A spec that omits the field falls
    # back to the modest claim, so reusing the synthesized brand animation can never
    # silently advertise a capture that doesn't exist.
    run_label = _esc(m.get("run_label", "brand animation"))
    return (
        f'<section><h2>See it run</h2><span class="zone-k">{run_label}</span>\n'
        '<figure class="figwrap"><img src="{}" data-video="{}" '
        'alt="{}" loading="lazy">'
        '<figcaption>{}</figcaption></figure>'
        '{}</section>'
    ).format(_esc(m["poster"]), _esc(m["motion"]), _esc(m["poster_alt"]),
             _esc(m["caption"]), crops_html)


def integration_html(spec: dict, fn: Footnotes) -> str:
    links = spec["links"]
    qs = "".join('<div class="runline">{}</div>'.format(_esc(q["command"]))
                 for q in spec.get("quickstart", []))
    return (
        '<section><h2>Integration</h2><span class="zone-k">how to run it</span>\n'
        '<p class="intro">Distribution: public repository, MIT license.</p>\n'
        '<div class="verify">\n{}'
        '  <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px">\n'
        '    <a class="btn btn-t" href="{}" target="_blank" rel="noopener">Source on GitHub</a>\n'
        '    <a class="btn btn-t" href="{}" target="_blank" rel="noopener">Engine README</a>\n'
        '    <a class="btn btn-t" href="{}">All tests, by engine</a>\n'
        '    <a class="btn btn-t" href="{}" target="_blank" rel="noopener">Run in Codespaces</a>\n'
        '  </div>\n</div>\n'
        '{}\n'
        '<div class="cta"><h2>Show us where the hours go.</h2>'
        '<p>One conversation: you describe the work that consumes your team\'s month; '
        'we tell you plainly what this engine can take over, what it can\'t, and what a '
        'scoped first phase would cost. Your people keep approval authority.</p>'
        '<a class="btn btn-w" href="{}">Book a free consultation</a></div>\n'
        '</section>'
    ).format(qs, _esc(links["source"]), _esc(links["readme"]), _esc(links["tests"]),
         _esc(links["codespaces"]), fn.render(), CTA_BOOK)


# --- visual zones (STUBS — replaced in Tasks 4 and 5) ----------------------

def die_stack_html(spec: dict) -> str:
    layers = spec["layers"]
    n = len(layers)
    # Static isometric SVG: stacked slabs (top parallelogram + front face), top layer first.
    box_w, box_h, gap = 320, 46, 14
    total_h = n * (box_h + gap) + 60 + 40
    svg_layers = []
    faces = []
    for i, layer in enumerate(layers):
        y = 20 + i * (box_h + gap)
        top = f"{80},{y} {80 + box_w},{y} {box_w + 40},{y + 22} {40},{y + 22}"
        front = f"40,{y + 22} {box_w + 40},{y + 22} {box_w + 40},{y + 22 + box_h} 40,{y + 22 + box_h}"
        svg_layers.append(
            '  <g class="die-layer" data-layer="{}">'
            '<polygon points="{}" fill="#edf5ff" stroke="#0f62fe" stroke-width="1.4"/>'
            '<polygon points="{}" fill="#ffffff" stroke="#0f62fe" stroke-width="1.4"/>'
            '<text x="60" y="{}" font-family="IBM Plex Mono,monospace" font-size="13" '
            'fill="#161616">{}</text></g>'.format(
                _esc(layer["id"]), top, front,
                y + 22 + box_h // 2 + 4, _esc(layer["label"]),
            )
        )
        faces.append(
            '    <button class="die-face" data-layer="{}" '
            'data-plain="{}" data-eng="{}" data-src="{}" '
            'aria-label="{} layer — open detail" aria-controls="die-panel" '
            'aria-expanded="false">{}</button>'.format(_esc(layer["id"]), _esc(layer["plain"]), _esc(layer["engineering"]),
               _esc(layer["source_link"]), _esc(layer["label"]), _esc(layer["label"])))
    substrate = "seeded fictional data" if _is_seeded(spec) else "fictional data"
    svg = (
        '<svg class="die-svg" viewBox="0 0 {} {}" role="img" '
        'aria-label="Exploded functional block stack: {} over {}">\n{}\n'
        '  <text x="40" y="{}" font-family="IBM Plex Mono,monospace" font-size="11" '
        'fill="#6f6f6f">substrate: {}</text>\n</svg>'
    ).format(
        box_w + 90, total_h,
        _esc(", ".join(layer["label"] for layer in layers)), substrate,
        "\n".join(svg_layers), total_h - 10, substrate,
    )
    faces_html = "\n".join(faces)
    layers_intro = _esc(spec.get(
        "layers_intro",
        "Each layer is an independent stage of the engine. "
        "Select a layer for its plain-terms and engineering detail.",
    ))
    return (
        '<section><h2>Architecture</h2>'
        '<span class="zone-k die-instruction">functional block stack &middot; static overview</span>\n'
        f'<div class="die">\n{svg}\n'
        f'  <div class="die-3d" aria-hidden="false">\n{faces_html}\n  </div>\n'
        '  <div class="die-panel" id="die-panel" role="region" '
        'aria-label="Architecture layer details" aria-live="polite">'
        f'<h3>Select a layer</h3><p>{layers_intro}</p></div>\n'
        '</div></section>'
    )


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
        if x2 <= x1:
            # Feedback loop: leave from the source bottom and route below all blocks.
            sx, sy = cx(a) + cw // 2, cy(a) + ch
            tx, ty = cx(b) + cw // 2, cy(b) + ch
            loop_y = height - 48
            path = f"M{sx},{sy} C{sx},{loop_y} {sx},{loop_y} {sx - 24},{loop_y} L{tx + 24},{loop_y} C{tx},{loop_y} {tx},{loop_y} {tx},{ty}"
            lx, ly = (sx + tx) // 2, loop_y - 7
        else:
            mx = (x1 + x2) // 2
            path = f"M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}"
            lx, ly = mx, (y1 + y2) // 2 - 8
        label = (
            '<text x="{}" y="{}" font-family="IBM Plex Mono,monospace" '
            'font-size="10" fill="#6f6f6f" text-anchor="middle">{}</text>'.format(
                lx, ly, _esc(e["label"])
            )
            if e.get("label") else ""
        )
        edge_svg.append(
            f'  <g class="{cls}"><path d="{path}" fill="none" stroke="#0f62fe" '
            f'stroke-width="1.6" marker-end="url(#arrow)"/>{label}</g>')

    kind_fill = {"role": "#ffffff", "audit": "#edf5ff", "gate": "#edf5ff",
                 "human": "#e6f4ea"}
    block_svg = []
    for b in blocks:
        x, y = cx(b), cy(b)
        fill = kind_fill.get(b.get("kind", ""), "#ffffff")
        block_svg.append(
            '  <g class="schem-block" data-block="{}">'
            '<a href="{}" target="_blank" rel="noopener" '
            'aria-label="Open {} source on GitHub">'
            '<rect x="{}" y="{}" width="{}" height="{}" rx="4" fill="{}" '
            'stroke="#0f62fe" stroke-width="1.6"/>'
            '<text x="{}" y="{}" font-family="IBM Plex Sans,sans-serif" font-size="13" '
            'font-weight="600" fill="#161616" text-anchor="middle">{}</text></a></g>'.format(
                _esc(b["id"]), _esc(b["source_link"]), _esc(b["label"]),
                x, y, cw, ch, fill,
                x + cw // 2, y + ch // 2 + 4, _esc(b["label"]),
            )
        )

    title_block = (
        '  <g class="schem-title">'
        '<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="#c6c6c6" stroke-width="1"/>'
        '<text x="{}" y="{}" font-family="IBM Plex Mono,monospace" font-size="10" '
        'fill="#6f6f6f">{} &middot; FUNCTIONAL BLOCK DIAGRAM &middot; REV {}</text></g>'
    ).format(
        pad, height - 26, width - pad, height - 26, pad, height - 12,
        _esc(spec["part_no"]), _esc(spec["rev"]),
    )

    svg = (
        '<svg class="schem" viewBox="0 0 {} {}" role="group" '
        'aria-labelledby="schem-title">\n'
        '  <title id="schem-title">Functional block diagram of the {} engine</title>\n'
        '  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#0f62fe"/></marker></defs>\n'
        '{}\n{}\n{}\n</svg>'
    ).format(
        width, height, _esc(spec["name"]),
        "\n".join(edge_svg), "\n".join(block_svg), title_block,
    )

    plain_rows = "".join(
        '<li><b>{}.</b> {}</li>'.format(_esc(b["label"]), _esc(b["plain"]))
        for b in blocks if b.get("plain")
    )
    engineering_rows = "".join(
        '<li><b>{}.</b> {}</li>'.format(_esc(b["label"]), _esc(b["engineering"]))
        for b in blocks if b.get("engineering")
    )
    pair = (
        '<div class="pair schematic-pair">'
        f'<div class="plain"><h3>Plain terms</h3><ul>{plain_rows}</ul></div>'
        f'<div class="engineering"><h3>Engineering</h3><ul>{engineering_rows}</ul></div>'
        '</div>\n'
    )

    return ('<section><h2>Functional block diagram</h2>'
            '<span class="zone-k">engineering &middot; each block links to its source</span>\n'
            f'{svg}{pair}</section>')


# --- assembly --------------------------------------------------------------

def render(slug: str) -> str:
    spec = ds.load_spec(slug)
    problems = ds.validate_spec(spec)
    if problems:
        raise ValueError("invalid spec {!r}: {}".format(slug, "; ".join(problems)))
    fn = Footnotes()
    css = (PARTIALS / "page.css").read_text(encoding="utf-8")
    js = (PARTIALS / "page.js").read_text(encoding="utf-8")
    shell = Template((TEMPLATES / "datasheet.html.tmpl").read_text(encoding="utf-8"))
    # Order matters: sourced zones feed `fn`; integration renders fn.render() last.
    ms = masthead_html(spec)
    dk = die_stack_html(spec)
    ss = spec_strip_html(spec, fn)
    pt = plain_terms_html(spec, fn)
    sc = schematic_html(spec)
    ins = instruction_set_html(spec)
    bm = benchmarks_html(spec, fn)
    ctrl = control_characteristics_html(spec)
    lim = limits_html(spec, fn)
    sir = see_it_run_html(spec)
    integ = integration_html(spec, fn)
    return shell.substitute(
        title=_esc("{} — Sophon Finance Systems".format(spec["name"])),
        description=_esc(spec["meta"]["description"]),
        css=css, js=js,
        cta_book=CTA_BOOK,
        link_source=_esc(spec["links"]["source"]),
        data_note=("All public examples use fictional, seeded data."
                   if _is_seeded(spec)
                   else "All public examples use fictional data."),
        masthead=ms, die_stack=dk, spec_strip=ss, plain_terms=pt, schematic=sc,
        instruction_set=ins, benchmarks=bm, control_characteristics=ctrl,
        limits=lim, see_it_run=sir, integration=integ,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate an engine datasheet page.")
    parser.add_argument("--slug", default="triangulate")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    out = args.out or (OUT_DIR / (f"{args.slug}.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    document = render(args.slug)
    out.write_bytes(document.encode("utf-8"))
    print(f"datasheet: {args.slug} ({len(document.encode('utf-8'))} bytes) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
