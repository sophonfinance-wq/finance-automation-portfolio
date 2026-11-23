#!/usr/bin/env python
"""Render the Finance Operations Atlas to a single self-contained HTML file.

Usage::

    py generate.py [--out PATH]

Reads everything from :mod:`atlas_data` and writes one HTML artifact with
embedded CSS and JavaScript — no external resources, no CDN links, no
timestamps. Output is deterministic: running the generator twice produces
byte-identical files.
"""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import asdict
from pathlib import Path
from string import Template
from typing import Any, Dict, List

import atlas_data as data

DEFAULT_OUT = Path(__file__).resolve().parent / "out" / "finance-operations-atlas.html"


# ---------------------------------------------------------------------------
# Payload — resolve palette keys to hex and flatten dataclasses to JSON-ready
# structures. Order is preserved everywhere (tuples/dicts keep insertion order).
# ---------------------------------------------------------------------------

def build_payload() -> Dict[str, Any]:
    """Assemble the JSON payload embedded in the page's <script> block."""
    pal = data.PALETTE

    drives: List[Dict[str, Any]] = []
    for drive in data.DRIVES:
        d = asdict(drive)
        d["color"] = pal[drive.color]
        drives.append(d)

    workstreams: List[Dict[str, Any]] = []
    for ws in data.WORKSTREAMS:
        w = asdict(ws)
        w["kicker_color"] = pal[ws.kicker_color]
        workstreams.append(w)

    notes: List[Dict[str, Any]] = []
    for note in data.META["notes"]:  # type: ignore[index]
        n = dict(note)
        n["kicker_color"] = pal[n["kicker_color"]]
        notes.append(n)

    return {
        "tags": data.META["tags"],
        "notes": notes,
        "drives": drives,
        "workstreams": workstreams,
        "findit": [list(row) for row in data.FINDIT],
        "calendar": {k: [list(r) for r in rows] for k, rows in data.CALENDAR.items()},
        "nores": data.META["find_nores"],
    }


def payload_json() -> str:
    """Serialize the payload for safe embedding inside a <script> element."""
    text = json.dumps(build_payload(), ensure_ascii=True, separators=(",", ":"))
    # Never allow a literal "</script>" (or any "</") inside the script block.
    return text.replace("</", "<\\/")


# ---------------------------------------------------------------------------
# CSS — palette tokens substituted via string.Template ($name placeholders).
# ---------------------------------------------------------------------------

_CSS = Template("""\
  :root{
    --ink:$ink; --ink-deep:$ink_deep; --ink-bright:$ink_bright;
    --steel:$steel; --teal:$teal; --teal-ink:$teal_ink;
    --amber:$amber; --amber-ink:$amber_ink; --slate:$slate;
    --paper:$paper; --card:$card; --line:$line; --silver:$silver;
    --text:$text; --muted:$muted; --grey:$grey; --pale:$pale;
    --radius:10px;
    --shadow:0 1px 3px rgba(21,43,64,.08),0 4px 14px rgba(21,43,64,.06);
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html{scroll-behavior:smooth}
  body{font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,Roboto,Arial,sans-serif;
    background:var(--paper);color:var(--text);font-size:15px;line-height:1.55}
  button{appearance:none;border:0;background:none;font:inherit;color:inherit;cursor:pointer}
  button:focus-visible,input:focus-visible{outline:2px solid var(--steel);outline-offset:2px}
  .visually-hidden{position:absolute;width:1px;height:1px;margin:-1px;padding:0;
    overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
  @media (prefers-reduced-motion:reduce){
    *{animation:none!important;transition:none!important}
    html{scroll-behavior:auto}
  }

  /* ---------- header ---------- */
  header{position:sticky;top:0;z-index:50;background:var(--ink);color:#fff;
    box-shadow:0 2px 10px rgba(14,30,46,.35)}
  .bar{max-width:1280px;margin:0 auto;display:flex;align-items:center;gap:24px;
    padding:10px 24px;min-height:62px;flex-wrap:wrap}
  .wordmark .wm-main{display:block;font-weight:700;font-size:17px;letter-spacing:.2em}
  .wordmark .wm-sub{display:block;font-weight:400;font-size:10px;letter-spacing:.18em;
    text-transform:uppercase;color:var(--pale);margin-top:2px}
  nav{display:flex;gap:4px;flex-wrap:wrap;margin-left:auto}
  nav button{color:#c3d2dd;font-size:13.5px;padding:9px 14px;border-radius:7px;transition:.15s}
  nav button:hover{background:rgba(255,255,255,.10);color:#fff}
  nav button.active{background:var(--steel);color:#fff;font-weight:600}
  nav button:focus-visible{outline:2px solid var(--pale);outline-offset:1px}
  @media (max-width:760px){.bar{gap:10px;padding:10px 16px}nav{margin-left:0}}

  main{max-width:1280px;margin:0 auto;padding:26px 24px 80px}
  section.view{display:none}
  section.view.active{display:block;animation:fade .25s ease}
  @keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}

  /* ---------- hero ---------- */
  .hero{position:relative;border-radius:14px;overflow:hidden;color:#fff;
    padding:44px 42px 40px;margin-bottom:26px;
    background:linear-gradient(120deg,var(--ink-deep) 0%,var(--ink) 48%,var(--ink-bright) 100%)}
  .hero::before{content:"";position:absolute;inset:0;opacity:.14;
    background-image:linear-gradient(rgba(207,227,238,.55) 1px,transparent 1px),
      linear-gradient(90deg,rgba(207,227,238,.55) 1px,transparent 1px);
    background-size:60px 60px}
  .hero>*{position:relative}
  .hero h2{font-size:29px;font-weight:600}
  .hero p{margin-top:8px;max-width:760px;color:#d9e4ec;font-size:15.5px}
  .chips{display:flex;gap:10px;margin-top:22px;flex-wrap:wrap}
  .chip{border:1px solid rgba(255,255,255,.42);border-radius:999px;padding:7px 16px;
    font-size:12px;letter-spacing:.12em;color:#e7f0f6}
  .chip b{color:#fff;font-weight:600}

  .hint{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px;margin:2px 2px 18px}
  .hint .dot{width:8px;height:8px;border-radius:50%;background:var(--teal);flex:none}

  /* ---------- cards & grids ---------- */
  .grid{display:grid;gap:16px}
  .grid.cols4{grid-template-columns:repeat(4,1fr)}
  .grid.cols3{grid-template-columns:repeat(3,1fr)}
  @media (max-width:1000px){.grid.cols4,.grid.cols3{grid-template-columns:repeat(2,1fr)}}
  @media (max-width:640px){.grid.cols4,.grid.cols3{grid-template-columns:1fr}}

  .card{display:block;width:100%;text-align:left;background:var(--card);
    border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);
    padding:18px 20px;transition:.16s;position:relative;color:var(--text)}
  .card:hover{transform:translateY(-2px);box-shadow:0 6px 22px rgba(21,43,64,.14);
    border-color:var(--steel)}
  .card .kicker{display:block;font-size:10.5px;letter-spacing:.18em;font-weight:700;
    text-transform:uppercase;margin-bottom:6px}
  .card .card-title{display:block;font-size:16.5px;color:var(--ink);font-weight:600;margin-bottom:6px}
  .card .card-sub{display:block;font-size:13.5px;color:var(--muted)}
  .card .cardrow{display:flex;gap:12px;align-items:center}
  .card .cardrow .card-title,.card .cardrow .card-sub{margin:0}
  .card .cardfoot{display:block;margin-top:10px;font-size:13.5px;color:var(--muted)}
  .card .go{position:absolute;top:16px;right:16px;color:var(--steel);font-weight:700;
    opacity:0;transition:.16s}
  .card:hover .go{opacity:1}
  @media (hover:none){.card .go{opacity:1}}

  h2.sect{font-size:19px;color:var(--ink);margin:30px 0 14px;font-weight:600}
  h2.sect span{color:var(--grey);font-weight:400;font-size:14px;margin-left:10px}

  /* ---------- drive map ---------- */
  .three-pane{display:grid;grid-template-columns:230px 330px 1fr;gap:16px;align-items:start}
  @media (max-width:1000px){.three-pane{grid-template-columns:1fr}}
  .rail{display:flex;flex-direction:column;gap:8px}
  .drive-btn{display:flex;align-items:center;gap:12px;background:var(--card);
    border:1px solid var(--line);border-radius:var(--radius);padding:13px 14px;
    transition:.15s;text-align:left;width:100%}
  .drive-btn:hover{border-color:var(--steel)}
  .drive-btn.active{border-color:var(--ink);background:var(--ink);color:#fff}
  .drive-letter{width:38px;height:38px;border-radius:9px;display:flex;align-items:center;
    justify-content:center;font-weight:800;font-size:15px;color:#fff;flex:none}
  .drive-letter.sys{font-size:11px;letter-spacing:.04em}
  .drive-text{min-width:0}
  .drive-btn .dl{display:block;font-weight:600;color:var(--ink);font-size:14px}
  .drive-btn .ds{display:block;font-size:11.5px;color:var(--muted)}
  .drive-btn.active .dl{color:#fff}
  .drive-btn.active .ds{color:var(--pale)}
  .folder-list{display:flex;flex-direction:column;gap:6px;max-height:70vh;overflow:auto;padding-right:4px}
  .folder{display:block;width:100%;text-align:left;background:var(--card);
    border:1px solid var(--line);border-left:4px solid var(--silver);border-radius:8px;
    padding:10px 13px;transition:.13s;font-size:13.5px}
  .folder:hover{border-left-color:var(--teal)}
  .folder.active{border-color:var(--steel);border-left-color:var(--steel);background:#eef4f8}
  .folder .fname{display:block;font-weight:600;color:var(--ink)}
  .folder .fdesc{display:block;color:var(--muted);font-size:12.5px;margin-top:2px}
  .ftag{float:right;font-size:10px;letter-spacing:.08em;padding:2px 8px;margin-left:8px;
    border-radius:999px;font-weight:700;text-transform:uppercase}
  .tag-live{background:#e2f1ef;color:var(--teal-ink)}
  .tag-ref{background:#e8eff5;color:var(--steel)}
  .tag-archive{background:#eeece8;color:#5c6470}
  .tag-secure{background:#f7ead9;color:var(--amber-ink)}

  .detail{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
    box-shadow:var(--shadow);padding:24px 26px;min-height:340px}
  .detail .crumb{font-size:11px;letter-spacing:.14em;text-transform:uppercase;
    color:var(--steel);font-weight:700;margin-bottom:8px}
  .detail h3{font-size:20px;color:var(--ink);margin-bottom:10px}
  .detail p.purpose{color:var(--text);margin-bottom:16px}
  .detail h4{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
    color:var(--grey);margin:16px 0 8px}
  .kv{display:flex;flex-direction:column;gap:6px}
  .kv .row{display:flex;gap:10px;font-size:13.5px}
  .kv .k{flex:0 0 210px;font-weight:600;color:var(--steel)}
  .kv .v{color:var(--text);min-width:0}
  @media (max-width:640px){.kv .row{flex-direction:column;gap:2px}.kv .k{flex:none}}
  .pathchip{display:inline-block;background:#efede9;border:1px solid var(--line);
    border-radius:6px;font-family:Consolas,Menlo,monospace;font-size:12px;color:var(--ink);
    padding:3px 8px;margin:2px 4px 2px 0;overflow-wrap:anywhere;word-break:break-word;max-width:100%}
  ul.tips{margin:4px 0 0 18px}
  ul.tips li{font-size:13.5px;color:var(--text);margin-bottom:5px}
  .empty{color:var(--grey);display:flex;align-items:center;justify-content:center;
    min-height:300px;font-size:14px}
  .legend{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:11.5px;
    color:var(--muted);margin:6px 0 16px}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;
    vertical-align:-1px}

  /* ---------- workstreams ---------- */
  .ws-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
  .ws-tab{border:1px solid var(--line);background:var(--card);border-radius:999px;
    padding:9px 18px;font-size:13.5px;font-weight:600;color:var(--steel);transition:.15s}
  .ws-tab:hover{border-color:var(--steel)}
  .ws-tab.active{background:var(--ink);border-color:var(--ink);color:#fff}
  .ws-meta{display:flex;gap:22px;flex-wrap:wrap;background:var(--card);
    border:1px solid var(--line);border-radius:var(--radius);padding:14px 20px;
    margin-bottom:18px;font-size:13.5px}
  .ws-meta .m b{display:block;color:var(--steel);font-weight:600;font-size:11px;
    letter-spacing:.12em;text-transform:uppercase;margin-bottom:2px}
  .pipeline{display:flex;align-items:stretch;overflow-x:auto;padding:6px 2px 14px}
  .step{position:relative;flex:1;min-width:150px;background:var(--card);
    border:1.5px solid var(--line);border-radius:10px;padding:14px 14px 12px;
    transition:.15s;margin-right:26px;text-align:left}
  .step:last-child{margin-right:0}
  .step::after{content:"";position:absolute;top:50%;right:-21px;width:16px;height:2px;
    background:var(--grey)}
  .step:last-child::after{display:none}
  .step .num{display:flex;width:24px;height:24px;border-radius:50%;background:var(--steel);
    color:#fff;font-size:12px;font-weight:700;align-items:center;justify-content:center;
    margin-bottom:8px}
  .step:hover{border-color:var(--steel);transform:translateY(-2px)}
  .step.active{border-color:var(--ink);background:#eef4f8}
  .step.active .num{background:var(--ink)}
  .step .sname{display:block;font-size:13px;font-weight:600;color:var(--ink);line-height:1.3}
  .stepdetail{background:var(--card);border:1px solid var(--line);
    border-left:5px solid var(--teal);border-radius:var(--radius);box-shadow:var(--shadow);
    padding:22px 24px;margin-top:4px}
  .stepdetail h3{color:var(--ink);font-size:17px;margin-bottom:8px}

  /* ---------- find it ---------- */
  .searchwrap{position:relative;margin-bottom:16px}
  .searchwrap input{width:100%;font:inherit;font-size:15px;padding:13px 18px 13px 46px;
    border:1.5px solid var(--line);border-radius:10px;background:var(--card);color:var(--text)}
  .searchwrap input:focus{outline:none;border-color:var(--steel);
    box-shadow:0 0 0 3px rgba(47,111,146,.18)}
  .searchwrap .icon{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:var(--grey)}
  .findtable{width:100%;border-collapse:collapse;background:var(--card);
    border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow)}
  .findtable th{background:var(--ink);color:#fff;text-align:left;font-size:11.5px;
    letter-spacing:.12em;text-transform:uppercase;padding:11px 16px;font-weight:600}
  .findtable td{padding:11px 16px;border-top:1px solid var(--line);font-size:13.5px;vertical-align:top}
  .findtable td:first-child{font-weight:600;color:var(--ink);width:26%}
  .findtable td:nth-child(2){width:44%}
  .findtable .cat{display:inline-block;font-size:10px;letter-spacing:.1em;
    text-transform:uppercase;font-weight:700;padding:2px 8px;border-radius:999px;
    background:#e8eff5;color:var(--steel)}
  .nores{padding:26px;text-align:center;color:var(--grey)}

  /* ---------- calendar ---------- */
  .cal-col h3{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:#fff;
    border-radius:8px 8px 0 0;padding:10px 16px;font-weight:700}
  .cal-col:nth-child(1) h3{background:var(--teal-ink)}
  .cal-col:nth-child(2) h3{background:var(--steel)}
  .cal-col:nth-child(3) h3{background:var(--ink)}
  .cal-body{background:var(--card);border:1px solid var(--line);border-top:0;
    border-radius:0 0 var(--radius) var(--radius);padding:8px}
  .event{border-left:4px solid var(--teal);background:#fbfaf8;border-radius:6px;
    padding:10px 12px;margin:8px 6px}
  .event .when{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
    font-weight:700;color:var(--steel)}
  .event .what{font-size:13.5px;font-weight:600;color:var(--ink);margin:1px 0 2px}
  .event .who{font-size:12px;color:var(--muted)}

  footer{border-top:1px solid var(--line);margin-top:50px;padding:18px 24px;
    display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;
    max-width:1280px;margin-left:auto;margin-right:auto;color:var(--muted);font-size:12px}
""")


# ---------------------------------------------------------------------------
# JavaScript — plain script, no template literals (the page data arrives as
# JSON in window.ATLAS). All dynamic text passes through esc().
# ---------------------------------------------------------------------------

_JS = """\
"use strict";
var ATLAS = window.ATLAS;

function esc(s){
  return String(s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function narrow(){ return window.matchMedia("(max-width: 1000px)").matches; }

/* ---------------- view switching ---------------- */
var VIEW_KEYS = ["overview","drives","workstreams","find","calendar"];
function showView(key){
  VIEW_KEYS.forEach(function(k){
    document.getElementById("view-"+k).classList.toggle("active", k===key);
  });
  document.querySelectorAll("#nav button").forEach(function(btn){
    var on = btn.dataset.view === key;
    btn.classList.toggle("active", on);
    if(on){ btn.setAttribute("aria-current","page"); }
    else { btn.removeAttribute("aria-current"); }
  });
  window.scrollTo({top:0});
}
document.querySelectorAll("#nav button").forEach(function(btn){
  btn.addEventListener("click", function(){ showView(btn.dataset.view); });
});

/* ---------------- shared fragments ---------------- */
function tagChip(tag, inline){
  var style = inline ? ' style="float:none"' : "";
  return '<span class="ftag tag-'+esc(tag)+'"'+style+'>'+esc(ATLAS.tags[tag]||tag)+'</span>';
}
function driveChip(d){
  var label = d.key==="SYS" ? "SYS" : d.key+":";
  var cls = d.key==="SYS" ? "drive-letter sys" : "drive-letter";
  return '<span class="'+cls+'" style="background:'+esc(d.color)+'" aria-hidden="true">'+esc(label)+'</span>';
}
function driveByKey(key){
  return ATLAS.drives.filter(function(d){ return d.key===key; })[0] || null;
}
function runAction(action){
  if(action.view==="drives" && action.drive){
    showView("drives");
    selectDrive(action.drive);
    if(action.folder){ selectFolder(action.drive, action.folder); }
  } else {
    showView(action.view);
  }
}

/* ---------------- overview ---------------- */
var ovWs = document.getElementById("ov-workstreams");
ATLAS.workstreams.forEach(function(w){
  var b = document.createElement("button");
  b.type = "button"; b.className = "card";
  b.innerHTML =
    '<span class="kicker" style="color:'+esc(w.kicker_color)+'">'+esc(w.kicker)+'</span>'+
    '<span class="card-title">'+esc(w.title)+'</span>'+
    '<span class="card-sub">'+esc(w.blurb)+'</span>'+
    '<span class="go" aria-hidden="true">&#8594;</span>';
  b.addEventListener("click", function(){ openWorkstream(w.key); });
  ovWs.appendChild(b);
});

var ovDrives = document.getElementById("ov-drives");
ATLAS.drives.forEach(function(d){
  var names = d.folders.slice(0,3).map(function(f){ return f.name; }).join(" \\u00b7 ");
  var more = d.folders.length>3 ? " \\u2026" : "";
  var b = document.createElement("button");
  b.type = "button"; b.className = "card";
  b.innerHTML =
    '<span class="cardrow">'+driveChip(d)+
      '<span><span class="card-title">'+esc(d.label)+'</span>'+
      '<span class="card-sub">'+esc(d.sub)+'</span></span></span>'+
    '<span class="cardfoot">'+d.folders.length+' mapped areas \\u2014 '+esc(names)+more+'</span>'+
    '<span class="go" aria-hidden="true">&#8594;</span>';
  b.addEventListener("click", function(){ showView("drives"); selectDrive(d.key); });
  ovDrives.appendChild(b);
});

var ovNotes = document.getElementById("ov-notes");
ATLAS.notes.forEach(function(n){
  var b = document.createElement("button");
  b.type = "button"; b.className = "card";
  b.innerHTML =
    '<span class="kicker" style="color:'+esc(n.kicker_color)+'">'+esc(n.kicker)+'</span>'+
    '<span class="card-title">'+esc(n.title)+'</span>'+
    '<span class="card-sub">'+esc(n.text)+'</span>';
  b.addEventListener("click", function(){ runAction(n.action); });
  ovNotes.appendChild(b);
});

/* ---------------- drive map ---------------- */
var rail = document.getElementById("drive-rail");
var flist = document.getElementById("folder-list");
var det = document.getElementById("drive-detail");
ATLAS.drives.forEach(function(d){
  var b = document.createElement("button");
  b.type = "button"; b.className = "drive-btn"; b.dataset.drive = d.key;
  b.innerHTML = driveChip(d)+
    '<span class="drive-text"><span class="dl">'+esc(d.label)+'</span>'+
    '<span class="ds">'+esc(d.sub)+'</span></span>';
  b.addEventListener("click", function(){ selectDrive(d.key); });
  rail.appendChild(b);
});
function selectDrive(key){
  var d = driveByKey(key); if(!d){ return; }
  document.querySelectorAll(".drive-btn").forEach(function(b){
    b.classList.toggle("active", b.dataset.drive===key);
  });
  flist.innerHTML = "";
  d.folders.forEach(function(f){
    var el = document.createElement("button");
    el.type = "button"; el.className = "folder"; el.dataset.folder = f.name;
    el.innerHTML = tagChip(f.tag,false)+
      '<span class="fname">'+esc(f.name)+'</span>'+
      '<span class="fdesc">'+esc(f.desc)+'</span>';
    el.addEventListener("click", function(){ selectFolder(key, f.name); });
    flist.appendChild(el);
  });
  selectFolder(key, d.folders[0].name);
}
function selectFolder(key, name){
  var d = driveByKey(key); if(!d){ return; }
  var f = d.folders.filter(function(x){ return x.name===name; })[0];
  if(!f){ return; }
  document.querySelectorAll(".folder").forEach(function(el){
    el.classList.toggle("active", el.dataset.folder===name);
  });
  var out =
    '<p class="crumb">'+esc(d.label)+' \\u00b7 '+tagChip(f.tag,true)+'</p>'+
    '<h3>'+esc(f.name)+'</h3>'+
    '<p class="purpose">'+esc(f.purpose)+'</p>';
  if(f.keys.length){
    out += '<h4>Key locations</h4><div>'+
      f.keys.map(function(k){ return '<span class="pathchip">'+esc(k)+'</span>'; }).join("")+
      '</div>';
  }
  if(f.rows.length){
    out += '<h4>What to know</h4><div class="kv">'+
      f.rows.map(function(r){
        return '<div class="row"><span class="k">'+esc(r[0])+'</span>'+
          '<span class="v">'+esc(r[1])+'</span></div>';
      }).join("")+'</div>';
  }
  if(f.tips.length){
    out += '<h4>Working notes</h4><ul class="tips">'+
      f.tips.map(function(t){ return '<li>'+esc(t)+'</li>'; }).join("")+'</ul>';
  }
  det.innerHTML = out;
  if(narrow()){ det.scrollIntoView({behavior:"smooth",block:"nearest"}); }
}

/* ---------------- workstreams ---------------- */
var curWs = null;
var wsTabs = document.getElementById("ws-tabs");
var wsMeta = document.getElementById("ws-meta");
var wsPipe = document.getElementById("ws-pipeline");
var wsDet = document.getElementById("ws-stepdetail");
ATLAS.workstreams.forEach(function(w){
  var b = document.createElement("button");
  b.type = "button"; b.className = "ws-tab"; b.dataset.ws = w.key;
  b.textContent = w.title;
  b.addEventListener("click", function(){ selectWs(w.key); });
  wsTabs.appendChild(b);
});
function wsByKey(key){
  return ATLAS.workstreams.filter(function(w){ return w.key===key; })[0] || null;
}
function selectWs(key){
  var w = wsByKey(key); if(!w){ return; }
  curWs = key;
  document.querySelectorAll(".ws-tab").forEach(function(b){
    b.classList.toggle("active", b.dataset.ws===key);
  });
  wsMeta.innerHTML = w.meta.map(function(m){
    return '<div class="m"><b>'+esc(m[0])+'</b>'+esc(m[1])+'</div>';
  }).join("");
  wsPipe.innerHTML = "";
  w.steps.forEach(function(s, i){
    var el = document.createElement("button");
    el.type = "button"; el.className = "step"; el.dataset.step = String(i);
    el.innerHTML = '<span class="num" aria-hidden="true">'+(i+1)+'</span>'+
      '<span class="sname">'+esc(s.name)+'</span>';
    el.addEventListener("click", function(){ selectStep(i); });
    wsPipe.appendChild(el);
  });
  selectStep(0);
}
function selectStep(i){
  var w = wsByKey(curWs); if(!w){ return; }
  var s = w.steps[i]; if(!s){ return; }
  document.querySelectorAll(".step").forEach(function(el){
    el.classList.toggle("active", el.dataset.step===String(i));
  });
  wsDet.innerHTML =
    '<h3>Step '+(i+1)+' \\u2014 '+esc(s.name)+'</h3>'+
    '<p style="margin-bottom:14px">'+esc(s.detail)+'</p>'+
    '<div class="kv">'+s.io.map(function(r){
      return '<div class="row"><span class="k">'+esc(r[0])+'</span>'+
        '<span class="v">'+esc(r[1])+'</span></div>';
    }).join("")+'</div>';
  if(narrow()){ wsDet.scrollIntoView({behavior:"smooth",block:"nearest"}); }
}
function openWorkstream(key){ showView("workstreams"); selectWs(key); }

/* ---------------- find it ---------------- */
var tbody = document.getElementById("findrows");
var nores = document.getElementById("nores");
var findcount = document.getElementById("findcount");
function renderFind(query){
  tbody.innerHTML = "";
  var q = (query||"").toLowerCase().trim();
  var shown = 0;
  ATLAS.findit.forEach(function(r){
    var hay = (r[0]+" "+r[1]+" "+r[2]+" "+r[3]).toLowerCase();
    if(q && hay.indexOf(q)===-1){ return; }
    shown++;
    var tr = document.createElement("tr");
    tr.innerHTML = '<td>'+esc(r[0])+'</td>'+
      '<td><span class="pathchip">'+esc(r[1])+'</span></td>'+
      '<td><span class="cat">'+esc(r[3])+'</span><br>'+esc(r[2])+'</td>';
    tbody.appendChild(tr);
  });
  nores.style.display = shown ? "none" : "block";
  findcount.textContent = shown+" of "+ATLAS.findit.length+" locations shown.";
}
document.getElementById("findbox").addEventListener("input", function(e){
  renderFind(e.target.value);
});

/* ---------------- calendar ---------------- */
[["cal-monthly","monthly"],["cal-quarterly","quarterly"],["cal-annual","annual"]]
  .forEach(function(pair){
    var el = document.getElementById(pair[0]);
    ATLAS.calendar[pair[1]].forEach(function(ev){
      var d = document.createElement("div");
      d.className = "event";
      d.innerHTML = '<div class="when">'+esc(ev[0])+'</div>'+
        '<div class="what">'+esc(ev[1])+'</div>'+
        '<div class="who">'+esc(ev[2])+'</div>';
      el.appendChild(d);
    });
  });

/* ---------------- init ---------------- */
selectDrive(ATLAS.drives[0].key);
selectWs(ATLAS.workstreams[0].key);
renderFind("");
"""


# ---------------------------------------------------------------------------
# HTML shell
# ---------------------------------------------------------------------------

_SHELL = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="$description">
<title>$title</title>
<style>
$css
</style>
</head>
<body>

<header>
  <div class="bar">
    <div class="wordmark">
      <span class="wm-main">$wordmark_main</span>
      <span class="wm-sub">$wordmark_sub</span>
    </div>
    <h1 class="visually-hidden">$h1</h1>
    <nav id="nav" aria-label="Atlas views">
      <button type="button" data-view="overview" class="active" aria-current="page">Overview</button>
      <button type="button" data-view="drives">Drive Map</button>
      <button type="button" data-view="workstreams">Workstreams</button>
      <button type="button" data-view="find">Find It</button>
      <button type="button" data-view="calendar">Calendar</button>
    </nav>
  </div>
</header>

<main>

<!-- ================= OVERVIEW ================= -->
<section class="view active" id="view-overview" aria-label="Overview">
  <div class="hero">
    <h2>$hero_heading</h2>
    <p>$hero_text</p>
    <div class="chips">
$chips
    </div>
  </div>

  <p class="hint"><span class="dot" aria-hidden="true"></span> $hint</p>

  <h2 class="sect">Core workstreams</h2>
  <div class="grid cols4" id="ov-workstreams"></div>

  <h2 class="sect">The drives <span>click to explore</span></h2>
  <div class="grid cols4" id="ov-drives"></div>

  <h2 class="sect">Good to know</h2>
  <div class="grid cols3" id="ov-notes"></div>
</section>

<!-- ================= DRIVE MAP ================= -->
<section class="view" id="view-drives" aria-label="Drive map">
  <h2 class="sect" style="margin-top:4px">Drive Map <span>drive &#8594; folder &#8594; briefing</span></h2>
  <div class="legend">
$legend
  </div>
  <div class="three-pane">
    <div class="rail" id="drive-rail"></div>
    <div class="folder-list" id="folder-list"></div>
    <div class="detail" id="drive-detail"><div class="empty">Choose a folder to open its briefing.</div></div>
  </div>
</section>

<!-- ================= WORKSTREAMS ================= -->
<section class="view" id="view-workstreams" aria-label="Workstreams">
  <h2 class="sect" style="margin-top:4px">Workstreams <span>open any step for its inputs, outputs and filing locations</span></h2>
  <div class="ws-tabs" id="ws-tabs"></div>
  <div class="ws-meta" id="ws-meta"></div>
  <div class="pipeline" id="ws-pipeline"></div>
  <div class="stepdetail" id="ws-stepdetail"></div>
</section>

<!-- ================= FIND IT ================= -->
<section class="view" id="view-find" aria-label="Find it">
  <h2 class="sect" style="margin-top:4px">Find It <span>search the location directory</span></h2>
  <div class="searchwrap">
    <span class="icon" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" style="display:block"><circle cx="11" cy="11" r="7"></circle><line x1="16.5" y1="16.5" x2="21" y2="21"></line></svg></span>
    <label class="visually-hidden" for="findbox">Filter the location table</label>
    <input id="findbox" type="text" placeholder="$find_placeholder" autocomplete="off">
  </div>
  <div id="findcount" class="visually-hidden" role="status"></div>
  <div style="overflow-x:auto"><table class="findtable">
    <thead><tr><th scope="col">Looking for&#8230;</th><th scope="col">Location</th><th scope="col">Notes</th></tr></thead>
    <tbody id="findrows"></tbody>
  </table></div>
  <div class="nores" id="nores" style="display:none">$find_nores</div>
</section>

<!-- ================= CALENDAR ================= -->
<section class="view" id="view-calendar" aria-label="Calendar">
  <h2 class="sect" style="margin-top:4px">The Finance Calendar <span>the recurring rhythm at a glance</span></h2>
  <div class="grid cols3">
    <div class="cal-col"><h3>Monthly</h3><div class="cal-body" id="cal-monthly"></div></div>
    <div class="cal-col"><h3>Quarterly</h3><div class="cal-body" id="cal-quarterly"></div></div>
    <div class="cal-col"><h3>Annual</h3><div class="cal-body" id="cal-annual"></div></div>
  </div>
</section>

</main>

<footer>
  <span>$footer_left</span>
  <span>$footer_right</span>
</footer>

<script>
window.ATLAS = $data_json;
</script>
<script>
$js
</script>
</body>
</html>
""")


def _chips_html() -> str:
    rows = []
    for bold, rest in data.META["chips"]:  # type: ignore[index]
        rows.append(
            '      <span class="chip"><b>%s</b> %s</span>'
            % (html.escape(bold), html.escape(rest))
        )
    return "\n".join(rows)


def _legend_html() -> str:
    rows = []
    for color_key, label in data.META["legend"]:  # type: ignore[index]
        rows.append(
            '    <span><i style="background:%s"></i>%s</span>'
            % (html.escape(data.PALETTE[color_key]), html.escape(label))
        )
    return "\n".join(rows)


def render() -> str:
    """Render the complete HTML document as a string."""
    meta = data.META
    return _SHELL.substitute(
        title=html.escape(str(meta["title"])),
        description=html.escape(str(meta["description"])),
        wordmark_main=html.escape(str(meta["wordmark_main"])),
        wordmark_sub=html.escape(str(meta["wordmark_sub"])),
        h1=html.escape(str(meta["h1"])),
        hero_heading=html.escape(str(meta["hero_heading"])),
        hero_text=html.escape(str(meta["hero_text"])),
        hint=html.escape(str(meta["hint"])),
        find_placeholder=html.escape(str(meta["find_placeholder"])),
        find_nores=html.escape(str(meta["find_nores"])),
        footer_left=html.escape(str(meta["footer_left"])),
        footer_right=html.escape(str(meta["footer_right"])),
        chips=_chips_html(),
        legend=_legend_html(),
        css=_CSS.substitute(data.PALETTE),
        data_json=payload_json(),
        js=_JS,
    )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Finance Operations Atlas HTML artifact."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="output path (default: out/finance-operations-atlas.html)",
    )
    args = parser.parse_args(argv)

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document = render()
    out_path.write_bytes(document.encode("utf-8"))

    print("Finance Operations Atlas")
    print("  Drives      : %d (+%d folder briefings)" % (
        len(data.DRIVES), sum(len(d.folders) for d in data.DRIVES)))
    print("  Workstreams : %d (%d steps)" % (
        len(data.WORKSTREAMS), sum(len(w.steps) for w in data.WORKSTREAMS)))
    print("  Find It     : %d rows" % len(data.FINDIT))
    print("  Calendar    : %d events" % sum(len(v) for v in data.CALENDAR.values()))
    print("  Output      : %s (%d bytes)" % (out_path, len(document.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
