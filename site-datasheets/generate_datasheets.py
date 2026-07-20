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


class Footnotes:
    """Collects (source) markers so zones 3 and 7 share one Substantiation list."""

    def __init__(self) -> None:
        self._items: list[str] = []

    def mark(self, source: str) -> str:
        self._items.append(source)
        return '<sup class="fn">%d</sup>' % len(self._items)

    def render(self) -> str:
        if not self._items:
            return ""
        rows = [
            '    <li><span class="fnid">%d</span>%s</li>' % (i + 1, _esc(s))
            for i, s in enumerate(self._items)
        ]
        return ('<div class="subst"><span class="zone-k">Substantiation</span><ul>\n'
                + "\n".join(rows) + "\n</ul></div>")


# --- zone builders ---------------------------------------------------------

def masthead_html(spec: dict) -> str:
    part = "%s &middot; %s &middot; REV %s &middot; %s" % (
        _esc(spec["part_no"]), _esc(spec["family"].upper()),
        _esc(spec["rev"]), _esc(spec["status"]))
    legend = ("PRODUCTION = runnable end-to-end, CI-backed, full test suite passing. "
              "All data fictional and seeded.")
    thesis = _esc(spec.get("marketing_thesis", ""))
    thesis_html = ('  <p class="thesis">%s</p>\n' % thesis) if thesis else ""
    return (
        '<section class="masthead">\n'
        '  <p class="kicker">ENGINE %02d</p>\n'
        '  <p class="partline">%s</p>\n'
        '  <p class="legend">%s</p>\n'
        '  <h1><strong>%s</strong></h1>\n'
        '  <p class="tag">%s</p>\n'
        '  <p class="intro">%s</p>\n'
        '%s'
        '  <p><a class="btn btn-p" href="%s" target="_blank" rel="noopener">Run it</a> '
        '<a class="btn btn-t" href="%s">Book a consultation</a></p>\n'
        '</section>'
    ) % (spec["num"], part, _esc(legend), _esc(spec["name"]),
         _esc(spec["tagline"]), _esc(spec["plain_summary"]), thesis_html,
         _esc(spec["links"]["codespaces"]), CTA_BOOK)


def spec_strip_html(spec: dict, fn: Footnotes) -> str:
    cells = []
    for item in spec["spec_strip"]:
        plain = ('<div class="p">%s</div>' % _esc(item["plain"])) if item.get("plain") else ""
        cells.append(
            '  <div class="cell"><div class="v">%s%s</div>'
            '<div class="l">%s</div>%s</div>'
            % (_esc(item["value"]), fn.mark(item["source"]), _esc(item["label"]), plain))
    return ('<section><h2>Key specifications</h2>'
            '<span class="zone-k">at a glance</span>\n'
            '<div class="strip">\n' + "\n".join(cells) + "\n</div></section>")


def plain_terms_html(spec: dict) -> str:
    scen = []
    for s in spec["scenarios"]:
        scen.append('  <p style="margin:10px 0"><b>%s.</b> %s</p>'
                    % (_esc(s["title"]), _esc(s["narrative"])))
    return ('<section><h2>What it does for you</h2>'
            '<span class="zone-k">plain terms</span>\n'
            '  <p class="intro">%s</p>\n%s\n</section>'
            % (_esc(spec["problem_statement"]), "\n".join(scen)))


def instruction_set_html(spec: dict) -> str:
    rows = []
    for op in spec["instruction_set"]:
        cmd = _esc(op["cmd"])
        rows.append(
            '  <tr><td class="mono"><div class="copyrow"><code>%s</code>'
            '<button class="copybtn" data-copy="%s" aria-label="Copy command">copy</button></div></td>'
            '<td>%s</td><td class="mono">%s</td><td class="mono">%s</td><td>%s</td></tr>'
            % (cmd, cmd, _esc(op["operation"]), _esc(op["output"]),
               _esc(op["exit_code"]), _esc(op["artifacts"])))
    return ('<section><h2>Instruction set</h2>'
            '<span class="zone-k">every public command</span>\n'
            '<table class="ds"><thead><tr><th>Command</th><th>Operation</th>'
            '<th>Output</th><th>Exit</th><th>Artifacts</th></tr></thead>\n'
            '<tbody>\n' + "\n".join(rows) + "\n</tbody></table></section>")


def benchmarks_html(spec: dict, fn: Footnotes) -> str:
    rows = []
    for b in spec["benchmarks"]:
        plain = ('<br><span style="color:#6f6f6f;font-size:12.5px">%s</span>'
                 % _esc(b["plain"])) if b.get("plain") else ""
        rows.append('  <tr><td>%s%s</td><td class="mono"><b>%s</b> %s</td></tr>'
                    % (_esc(b["label"]), fn.mark(b["source"]),
                       _esc(b["value"]), _esc(b["unit"]) + plain))
    return ('<section><h2>Benchmarks</h2>'
            '<span class="zone-k">measured demo results</span>\n'
            '<table class="ds"><thead><tr><th>Measure</th><th>Result</th></tr></thead>\n'
            '<tbody>\n' + "\n".join(rows) + "\n</tbody></table></section>")


def control_characteristics_html(spec: dict) -> str:
    cc = spec["control_characteristics"]
    auth = "".join('<tr><td class="mono">%d</td><td><b>%s</b></td><td>%s</td></tr>'
                   % (a["rank"], _esc(a["level"]), _esc(a["note"])) for a in cc["authority"])
    vmap = "".join('<tr><td>%s</td><td class="mono"><b>%s</b></td><td>%s</td></tr>'
                   % (_esc(v["severity"]), _esc(v["verdict"]), _esc(v["action"]))
                   for v in cc["verdict_map"])
    guarantees = "".join('<li style="list-style:disc;margin-left:18px">%s</li>' % _esc(g)
                         for g in cc["guarantees"])
    modes = "".join('<p style="margin:8px 0"><b>%s.</b> %s</p>'
                    % (_esc(m["name"]), _esc(m["detail"])) for m in cc["modes"])
    return (
        '<section><h2>Control characteristics</h2>'
        '<span class="zone-k">engineering</span>\n'
        '<table class="ds"><thead><tr><th>Authority</th><th>Level</th><th>Note</th></tr></thead>'
        '<tbody>%s</tbody></table>\n'
        '<table class="ds" style="margin-top:14px"><thead><tr><th>Severity</th><th>Verdict</th><th>Action</th></tr></thead>'
        '<tbody>%s</tbody></table>\n'
        '<ul style="margin-top:14px">%s</ul>\n%s</section>'
    ) % (auth, vmap, guarantees, modes)


def limits_html(spec: dict, fn: Footnotes) -> str:
    items = "".join('<li>%s%s</li>' % (_esc(l["statement"]), fn.mark(l["source"]))
                    for l in spec["limits"])
    return ('<section><h2>Operating limits</h2>'
            '<span class="zone-k">what it refuses to do</span>\n'
            '<ul class="limits">%s</ul></section>' % items)


def see_it_run_html(spec: dict) -> str:
    m = spec["media"]
    return (
        '<section><h2>See it run</h2><span class="zone-k">the real CLI</span>\n'
        '<figure class="figwrap"><img src="%s" data-video="%s" '
        'alt="Screencast of the Triangulate CLI running on fictional seeded data" '
        'loading="lazy"></figure></section>'
    ) % (_esc(m["poster"]), _esc(m["motion"]))


def integration_html(spec: dict, fn: Footnotes) -> str:
    links = spec["links"]
    qs = "".join('<div class="runline">%s</div>' % _esc(q["command"])
                 for q in spec.get("quickstart", []))
    return (
        '<section><h2>Integration</h2><span class="zone-k">how to run it</span>\n'
        '<p class="intro">Distribution: public repository, MIT license.</p>\n'
        '<div class="verify">\n%s'
        '  <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px">\n'
        '    <a class="btn btn-t" href="%s" target="_blank" rel="noopener">Source on GitHub</a>\n'
        '    <a class="btn btn-t" href="%s" target="_blank" rel="noopener">Engine README</a>\n'
        '    <a class="btn btn-t" href="%s">All tests, by engine</a>\n'
        '    <a class="btn btn-t" href="%s" target="_blank" rel="noopener">Run in Codespaces</a>\n'
        '  </div>\n</div>\n'
        '%s\n'
        '<div class="cta"><h2>Show us where the hours go.</h2>'
        '<p>One conversation: you describe the work that consumes your team\'s month; '
        'we tell you plainly what this engine can take over, what it can\'t, and what a '
        'scoped first phase would cost. Your people keep approval authority.</p>'
        '<a class="btn btn-w" href="%s">Book a free consultation</a></div>\n'
        '</section>'
    ) % (qs, _esc(links["source"]), _esc(links["readme"]), _esc(links["tests"]),
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
        top = "%d,%d %d,%d %d,%d %d,%d" % (
            80, y, 80 + box_w, y, box_w + 40, y + 22, 40, y + 22)
        front = "40,%d %d,%d %d,%d 40,%d" % (
            y + 22, box_w + 40, y + 22, box_w + 40, y + 22 + box_h, y + 22 + box_h)
        svg_layers.append(
            '  <g class="die-layer" data-layer="%s">'
            '<polygon points="%s" fill="#edf5ff" stroke="#0f62fe" stroke-width="1.4"/>'
            '<polygon points="%s" fill="#ffffff" stroke="#0f62fe" stroke-width="1.4"/>'
            '<text x="60" y="%d" font-family="IBM Plex Mono,monospace" font-size="13" '
            'fill="#161616">%s</text></g>'
            % (_esc(layer["id"]), top, front, y + 22 + box_h // 2 + 4, _esc(layer["label"])))
        faces.append(
            '    <button class="die-face" data-layer="%s" '
            'data-plain="%s" data-eng="%s" data-src="%s" '
            'aria-label="%s layer — open detail">%s</button>'
            % (_esc(layer["id"]), _esc(layer["plain"]), _esc(layer["engineering"]),
               _esc(layer["source_link"]), _esc(layer["label"]), _esc(layer["label"])))
    svg = ('<svg class="die-svg" viewBox="0 0 %d %d" role="img" '
           'aria-label="Exploded functional block stack: %s over seeded fictional data">\n%s\n'
           '  <text x="40" y="%d" font-family="IBM Plex Mono,monospace" font-size="11" '
           'fill="#6f6f6f">substrate: seeded fictional data</text>\n</svg>'
           % (box_w + 90, total_h,
              _esc(", ".join(l["label"] for l in layers)),
              "\n".join(svg_layers), total_h - 10))
    faces_html = "\n".join(faces)
    return (
        '<section><h2>Architecture</h2>'
        '<span class="zone-k">functional block stack &middot; click a layer</span>\n'
        '<div class="die">\n%s\n'
        '  <div class="die-3d" aria-hidden="false">\n%s\n  </div>\n'
        '  <div class="die-panel" id="die-panel" role="region" aria-live="polite">'
        '<h4>Select a layer</h4><p>Each layer is an independent duty. '
        'Click any block for its plain-terms and engineering description.</p></div>\n'
        '</div></section>'
    ) % (svg, faces_html)


def schematic_html(spec: dict) -> str:
    return ('<section><h2>Functional block diagram</h2>'
            '<span class="zone-k">engineering</span>\n'
            '<div><!-- schematic: Task 5 --></div></section>')


# --- assembly --------------------------------------------------------------

def render(slug: str) -> str:
    spec = ds.load_spec(slug)
    problems = ds.validate_spec(spec)
    if problems:
        raise ValueError("invalid spec %r: %s" % (slug, "; ".join(problems)))
    fn = Footnotes()
    css = (PARTIALS / "page.css").read_text(encoding="utf-8")
    js = (PARTIALS / "page.js").read_text(encoding="utf-8")
    shell = Template((TEMPLATES / "datasheet.html.tmpl").read_text(encoding="utf-8"))
    # Order matters: spec_strip (zone 3) then benchmarks (zone 7) then limits (zone 9)
    # all feed `fn`; integration renders fn.render() last.
    ms = masthead_html(spec)
    dk = die_stack_html(spec)
    ss = spec_strip_html(spec, fn)
    pt = plain_terms_html(spec)
    sc = schematic_html(spec)
    ins = instruction_set_html(spec)
    bm = benchmarks_html(spec, fn)
    ctrl = control_characteristics_html(spec)
    lim = limits_html(spec, fn)
    sir = see_it_run_html(spec)
    integ = integration_html(spec, fn)
    return shell.substitute(
        title="%s — Sophon Finance Systems" % spec["name"],
        description=spec["meta"]["description"],
        css=css, js=js,
        cta_book=CTA_BOOK,
        link_source=spec["links"]["source"],
        masthead=ms, die_stack=dk, spec_strip=ss, plain_terms=pt, schematic=sc,
        instruction_set=ins, benchmarks=bm, control_characteristics=ctrl,
        limits=lim, see_it_run=sir, integration=integ,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate an engine datasheet page.")
    parser.add_argument("--slug", default="triangulate")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    out = args.out or (OUT_DIR / ("%s.html" % args.slug))
    out.parent.mkdir(parents=True, exist_ok=True)
    document = render(args.slug)
    out.write_bytes(document.encode("utf-8"))
    print("datasheet: %s (%d bytes) -> %s" % (args.slug, len(document.encode("utf-8")), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
