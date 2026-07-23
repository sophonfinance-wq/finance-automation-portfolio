"""Evidence layer: one reviewable card per exception, plus a gallery.

A resolution schedule tells the reviewer *what* was classified; an evidence
card shows *why*, in the bank's own words. Each card carries:

    title bar      exception class, entity, GL account, headline figures
    body           the register's transaction table, verbatim, with the
                   traced sweep rows highlighted
    TIES footer    the one-line tie-out ("stale TB figure = traced
                   pre-sweep balance") or the honest OPEN flag when it
                   does not tie

Rendering is best-effort by design:

* **matplotlib available** -> PNG cards (``Agg`` backend, no display
  needed). All text is passed through :func:`_tex`, which escapes ``$`` --
  otherwise mathtext treats ``$1,000 ... $2,000`` as a formula and garbles
  the card.
* **matplotlib missing** -> self-contained HTML cards (inline CSS, no
  external assets), pixel-for-pixel the same information.
* **always** -> an ``INDEX.html`` gallery so a reviewer can open one file
  and see every exception with its tie-out status.

Only helpers are imported from :mod:`ccengine.report` (labels and
formatting); classification decisions arrive already made on the
``ExceptionItem`` objects and are never re-litigated here.

All entities, banks, accounts, and figures in this package are fictional
(Juniper 42 Development LLC, First Legacy Bank, Union National Bank, and
friends); see the repository README.
"""

from __future__ import annotations

import html
import os
import re
import textwrap
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:  # package layout
    from .report import KIND_LABELS, KIND_ORDER, field, money
except ImportError:  # pragma: no cover - standalone execution
    from report import KIND_LABELS, KIND_ORDER, field, money  # type: ignore

# --------------------------------------------------------------------------
# Optional matplotlib (guarded import; HTML fallback when absent)
# --------------------------------------------------------------------------

try:  # pragma: no cover - exercised implicitly by whichever env runs this
    import matplotlib

    matplotlib.use("Agg")  # must precede pyplot import; headless-safe
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    HAVE_MATPLOTLIB = True
except ImportError:  # pragma: no cover
    plt = None  # type: ignore[assignment]
    Rectangle = None  # type: ignore[assignment]
    HAVE_MATPLOTLIB = False

__all__ = ["render_evidence_cards", "HAVE_MATPLOTLIB"]

#: Closing-transfer descriptions the sweep tracer recognizes; rows matching
#: these are highlighted on the card.
_SWEEP_RE = re.compile(
    r"\b(transfer to|wire to|to close account|close account)\b", re.IGNORECASE
)

#: Title-bar color per exception class (PNG and HTML share these).
_KIND_COLORS: Dict[str, str] = {
    "A_UNMAPPED_SUCCESSOR": "#B45309",  # amber: TB completeness gap
    "B_STALE_CLOSEOUT": "#1D4ED8",      # blue: traced, book the entry
    "C_TIMING": "#047857",              # green: clears next period
    "D_UNEXPLAINED": "#B91C1C",         # red: blocks sign-off
}

_HIGHLIGHT = "#FEF3C7"   # background of highlighted sweep rows
_TIE_OK = "#047857"
_TIE_BAD = "#B91C1C"

_FOOTNOTE = "Fictional data - portfolio demonstration."


# --------------------------------------------------------------------------
# Card data assembly (representation-tolerant, same as report.py)
# --------------------------------------------------------------------------

def _tex(text: Any) -> str:
    """Escape a string for matplotlib text rendering.

    matplotlib parses ``$...$`` spans as mathtext, so a line containing two
    dollar amounts renders as garbled math. Escaping every ``$`` keeps the
    card verbatim.
    """
    return str(text if text is not None else "").replace("$", r"\$")


def _trunc(text: Any, width: int = 64) -> str:
    """Clip a long description so the table column stays readable."""
    s = str(text if text is not None else "")
    return s if len(s) <= width else s[: width - 3] + "..."


def _txn_dict(t: Any) -> Dict[str, Any]:
    """Serialize one Transaction (object or dict) to a plain dict."""
    return {
        "date": str(field(t, "date") or ""),
        "description": str(field(t, "description") or ""),
        "amount": float(field(t, "amount") or 0.0),
        "running_balance": float(field(t, "running_balance") or 0.0),
        "counterparty": str(field(t, "counterparty") or ""),
    }


def _sweep_rows(
    txns: Sequence[Dict[str, Any]], destinations: Sequence[Dict[str, Any]]
) -> Set[int]:
    """Indices of transactions that are (or match) traced sweep movements.

    A row is highlighted when its description matches a closing-transfer
    pattern, or when its date and absolute amount line up with a traced
    destination from ``reconcile.trace_sweeps``.
    """
    dest_keys = {
        (str(d.get("date") or ""), round(abs(float(d.get("amount") or 0.0)), 2))
        for d in destinations
    }
    rows: Set[int] = set()
    for i, t in enumerate(txns):
        if _SWEEP_RE.search(t["description"]):
            rows.add(i)
        elif (t["date"], round(abs(t["amount"]), 2)) in dest_keys:
            rows.add(i)
    return rows


def _tie_line(
    kind: str,
    register_balance: Optional[float],
    tb_balance: Optional[float],
    difference: float,
    destinations: Sequence[Dict[str, Any]],
) -> Tuple[str, bool]:
    """The card's footer sentence: does this exception tie out?

    Returns ``(text, ok)``. ``ok`` is ``True`` only when the card itself
    demonstrates the tie; Class D is always ``False`` -- an evidence card
    never dresses up an unexplained difference.
    """
    if kind == "B_STALE_CLOSEOUT":
        dest_total = round(
            sum(float(d.get("amount") or 0.0) for d in destinations), 2
        )
        if (
            destinations
            and tb_balance is not None
            and abs(dest_total - tb_balance) <= 0.005
        ):
            return (
                f"TIES: stale TB figure {money(tb_balance)} equals the traced "
                f"pre-sweep balance -- {len(destinations)} sweep "
                f"destination(s) totaling {money(dest_total)}, highlighted "
                "above.",
                True,
            )
        return (
            f"DOES NOT TIE: stale TB figure {money(tb_balance)} vs traced "
            f"sweep destinations {money(dest_total)}. Trace the remaining "
            "movement before booking anything.",
            False,
        )
    if kind == "A_UNMAPPED_SUCCESSOR":
        return (
            f"TIES: register balance {money(register_balance)} is live cash "
            "with no TB row. The full balance is a TB mapping gap, not "
            "missing money; map the account and it clears.",
            True,
        )
    if kind == "C_TIMING":
        return (
            f"TIES: register {money(register_balance)} vs TB "
            f"{money(tb_balance)}; the {money(difference)} difference is "
            "post-cutoff activity and clears next period.",
            True,
        )
    return (
        f"OPEN: register {money(register_balance)} vs TB {money(tb_balance)}; "
        f"difference {money(difference)} is unexplained. This blocks "
        "sign-off -- never book an entry against an unexplained difference.",
        False,
    )


def _card_data(exc: Any, reg: Any) -> Dict[str, Any]:
    """Flatten one exception + its register account into a render-ready dict."""
    kind = str(field(exc, "kind") or "")
    reg_bal_raw = field(exc, "register_balance")
    tb_bal_raw = field(exc, "tb_balance")
    reg_bal = None if reg_bal_raw is None else float(reg_bal_raw)
    tb_bal = None if tb_bal_raw is None else float(tb_bal_raw)
    difference = round((reg_bal or 0.0) - (tb_bal or 0.0), 2)
    destinations = [
        {
            "date": str(field(d, "date") or ""),
            "counterparty": str(field(d, "counterparty") or ""),
            "amount": float(field(d, "amount") or 0.0),
        }
        for d in (field(exc, "destinations") or [])
    ]
    txns = [_txn_dict(t) for t in (field(reg, "transactions") or [])]
    tie_text, tie_ok = _tie_line(kind, reg_bal, tb_bal, difference, destinations)
    return {
        "kind": kind,
        "label": KIND_LABELS.get(kind, kind),
        "color": _KIND_COLORS.get(kind, "#374151"),
        "gl_norm": str(field(exc, "gl_norm") or ""),
        "entity": str(field(exc, "entity") or ""),
        "register_balance": reg_bal,
        "tb_balance": tb_bal,
        "difference": difference,
        "note": str(field(exc, "note") or ""),
        "destinations": destinations,
        "bank": str(field(reg, "bank") or ""),
        "bank_account_no": str(field(reg, "bank_account_no") or ""),
        "status": str(field(reg, "status") or ""),
        "as_of": str(field(reg, "as_of") or ""),
        "source_file": str(field(reg, "source_file") or ""),
        "transactions": txns,
        "sweep_rows": _sweep_rows(txns, destinations),
        "tie_text": tie_text,
        "tie_ok": tie_ok,
    }


def _subtitle(card: Dict[str, Any]) -> str:
    """Second title-bar line: entity, GL, and register provenance."""
    bits = [card["entity"], f"GL {card['gl_norm']}"]
    if card["bank"]:
        bits.append(f"{card['bank']} #{card['bank_account_no']}")
    if card["status"]:
        bits.append(f"status: {card['status']}")
    if card["as_of"]:
        bits.append(f"as of {card['as_of']}")
    return "  |  ".join(b for b in bits if b)


def _figures(card: Dict[str, Any]) -> str:
    """Right-hand title-bar figures."""
    return (
        f"Register {money(card['register_balance'])}   "
        f"TB {money(card['tb_balance'])}   "
        f"Diff {money(card['difference'])}"
    )


def _slug(text: str) -> str:
    """Filesystem-safe fragment for card filenames."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "card"


# --------------------------------------------------------------------------
# PNG rendering (matplotlib path)
# --------------------------------------------------------------------------

def _render_card_png(card: Dict[str, Any], path: str) -> str:
    """Render one card as a PNG via matplotlib (Agg backend)."""
    txns: List[Dict[str, Any]] = card["transactions"]
    n_rows = len(txns)

    header_in = 1.15
    row_in = 0.30
    table_in = row_in * (max(n_rows, 1) + 1) + 0.35
    footer_in = 1.15
    fig_w = 11.0
    fig_h = header_in + table_in + footer_in

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=150)
    fig.patch.set_facecolor("white")

    # --- title bar ---------------------------------------------------------
    ax_h = fig.add_axes([0.0, 1.0 - header_in / fig_h, 1.0, header_in / fig_h])
    ax_h.set_axis_off()
    ax_h.add_patch(
        Rectangle((0, 0), 1, 1, transform=ax_h.transAxes,
                  facecolor=card["color"], edgecolor="none")
    )
    ax_h.text(0.015, 0.66, _tex(card["label"]), transform=ax_h.transAxes,
              fontsize=13, fontweight="bold", color="white", va="center")
    ax_h.text(0.015, 0.26, _tex(_subtitle(card)), transform=ax_h.transAxes,
              fontsize=8.5, color="white", va="center")
    ax_h.text(0.985, 0.66, _tex(_figures(card)), transform=ax_h.transAxes,
              fontsize=9.5, fontweight="bold", color="white",
              va="center", ha="right")

    # --- transaction table (verbatim) ---------------------------------------
    ax_t = fig.add_axes(
        [0.02, footer_in / fig_h, 0.96, table_in / fig_h]
    )
    ax_t.set_axis_off()
    if txns:
        col_labels = ["Date", "Description", "Amount", "Balance", "Counterparty"]
        cell_text = [
            [
                _tex(t["date"]),
                _tex(_trunc(t["description"])),
                _tex(money(t["amount"])),
                _tex(money(t["running_balance"])),
                _tex(_trunc(t["counterparty"], 28)),
            ]
            for t in txns
        ]
        tbl = ax_t.table(
            cellText=cell_text,
            colLabels=col_labels,
            colWidths=[0.10, 0.42, 0.12, 0.13, 0.23],
            cellLoc="left",
            loc="upper left",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8.5)
        tbl.scale(1.0, 1.35)
        for (r, c), cell in tbl.get_celld().items():
            cell.set_edgecolor("#D1D5DB")
            if r == 0:
                cell.set_facecolor("#111827")
                cell.set_text_props(color="white", fontweight="bold")
            elif (r - 1) in card["sweep_rows"]:
                cell.set_facecolor(_HIGHLIGHT)
                if c == 1:  # description column carries the trace
                    cell.set_text_props(fontweight="bold")
    else:
        ax_t.text(
            0.5, 0.5,
            "No register transactions for this GL key.",
            transform=ax_t.transAxes, ha="center", va="center",
            fontsize=10, color="#6B7280", style="italic",
        )

    # --- TIES footer ---------------------------------------------------------
    ax_f = fig.add_axes([0.0, 0.0, 1.0, footer_in / fig_h])
    ax_f.set_axis_off()
    ax_f.add_patch(
        Rectangle((0.0, 0.96), 1.0, 0.04, transform=ax_f.transAxes,
                  facecolor="#E5E7EB", edgecolor="none")
    )
    tie_color = _TIE_OK if card["tie_ok"] else _TIE_BAD
    tie_wrapped = "\n".join(textwrap.wrap(card["tie_text"], width=125))
    ax_f.text(0.015, 0.78, _tex(tie_wrapped), transform=ax_f.transAxes,
              fontsize=9.5, fontweight="bold", color=tie_color, va="top")
    if card["note"]:
        note_wrapped = "\n".join(
            textwrap.wrap("Note: " + card["note"], width=145)
        )
        ax_f.text(0.015, 0.38, _tex(note_wrapped), transform=ax_f.transAxes,
                  fontsize=8, color="#374151", va="top")
    src = f"Source: {card['source_file']}" if card["source_file"] else ""
    ax_f.text(0.015, 0.06, _tex(f"{_FOOTNOTE}  {src}".strip()),
              transform=ax_f.transAxes, fontsize=7, color="#9CA3AF",
              va="bottom")

    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# HTML rendering (fallback path; self-contained, inline CSS)
# --------------------------------------------------------------------------

_CARD_CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0;
       background: #F3F4F6; color: #111827; }
.card { max-width: 960px; margin: 24px auto; background: white;
        border: 1px solid #D1D5DB; border-radius: 6px; overflow: hidden; }
.bar { color: white; padding: 14px 18px; display: flex;
       justify-content: space-between; align-items: baseline;
       flex-wrap: wrap; gap: 6px; }
.bar h1 { font-size: 17px; margin: 0; }
.bar .sub { font-size: 12px; opacity: 0.92; margin: 4px 0 0; width: 100%; }
.bar .figs { font-size: 13px; font-weight: bold; white-space: nowrap; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid #E5E7EB; padding: 5px 9px; text-align: left; }
th { background: #111827; color: white; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.sweep td { background: #FEF3C7; }
tr.sweep td.desc { font-weight: bold; }
.body { padding: 12px 18px 4px; }
.empty { color: #6B7280; font-style: italic; padding: 18px; }
footer { border-top: 3px solid #E5E7EB; padding: 12px 18px 14px; }
.tie { font-weight: bold; font-size: 14px; margin: 0 0 8px; }
.tie.ok { color: #047857; } .tie.bad { color: #B91C1C; }
.note { font-size: 12px; color: #374151; margin: 0 0 8px; }
.fine { font-size: 10px; color: #9CA3AF; margin: 0; }
"""


def _esc(text: Any) -> str:
    """HTML-escape a value."""
    return html.escape(str(text if text is not None else ""))


def _render_card_html(card: Dict[str, Any], path: str) -> str:
    """Render one card as a self-contained HTML file (no external assets)."""
    rows: List[str] = []
    for i, t in enumerate(card["transactions"]):
        cls = ' class="sweep"' if i in card["sweep_rows"] else ""
        rows.append(
            f"<tr{cls}><td>{_esc(t['date'])}</td>"
            f"<td class=\"desc\">{_esc(t['description'])}</td>"
            f"<td class=\"num\">{_esc(money(t['amount']))}</td>"
            f"<td class=\"num\">{_esc(money(t['running_balance']))}</td>"
            f"<td>{_esc(t['counterparty'])}</td></tr>"
        )
    if rows:
        table = (
            "<table><thead><tr><th>Date</th><th>Description</th>"
            "<th>Amount</th><th>Balance</th><th>Counterparty</th></tr>"
            "</thead><tbody>" + "".join(rows) + "</tbody></table>"
        )
    else:
        table = '<p class="empty">No register transactions for this GL key.</p>'

    tie_cls = "ok" if card["tie_ok"] else "bad"
    note = (
        f'<p class="note">Note: {_esc(card["note"])}</p>' if card["note"] else ""
    )
    src = f"Source: {card['source_file']}" if card["source_file"] else ""
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{_esc(card['label'])} - {_esc(card['gl_norm'])}</title>
<style>{_CARD_CSS}</style></head><body>
<div class="card">
<header class="bar" style="background:{card['color']}">
<h1>{_esc(card['label'])}</h1>
<span class="figs">{_esc(_figures(card))}</span>
<p class="sub">{_esc(_subtitle(card))}</p>
</header>
<div class="body">{table}</div>
<footer>
<p class="tie {tie_cls}">{_esc(card['tie_text'])}</p>
{note}
<p class="fine">{_esc((_FOOTNOTE + '  ' + src).strip())}</p>
</footer>
</div></body></html>
"""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    return path


# --------------------------------------------------------------------------
# INDEX.html gallery (always written)
# --------------------------------------------------------------------------

_INDEX_CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0;
       background: #F3F4F6; color: #111827; }
.wrap { max-width: 1200px; margin: 0 auto; padding: 24px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: #6B7280; font-size: 13px; margin: 0 0 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill,
        minmax(340px, 1fr)); gap: 18px; }
.tile { background: white; border: 1px solid #D1D5DB; border-radius: 6px;
        overflow: hidden; display: flex; flex-direction: column; }
.tile .bar { color: white; padding: 9px 12px; font-size: 13px;
             font-weight: bold; }
.tile img { width: 100%; height: auto; display: block;
            border-bottom: 1px solid #E5E7EB; }
.tile .info { padding: 10px 12px; font-size: 12.5px; flex: 1; }
.tile .info p { margin: 0 0 6px; }
.tie { font-weight: bold; } .tie.ok { color: #047857; }
.tie.bad { color: #B91C1C; }
.tile a.open { display: block; padding: 8px 12px; background: #111827;
               color: white; text-decoration: none; font-size: 12.5px;
               text-align: center; }
.fine { color: #9CA3AF; font-size: 11px; margin-top: 20px; }
.empty { color: #6B7280; font-style: italic; }
"""


def _write_index(
    entries: List[Dict[str, Any]], out_dir: str, mode: str, as_of: str
) -> str:
    """Write the INDEX.html gallery over all rendered cards."""
    tiles: List[str] = []
    for e in entries:
        card = e["card"]
        fname = e["filename"]
        tie_cls = "ok" if card["tie_ok"] else "bad"
        tie_word = "TIES" if card["tie_ok"] else (
            "DOES NOT TIE" if card["kind"] == "B_STALE_CLOSEOUT" else "OPEN"
        )
        thumb = (
            f'<a href="{_esc(fname)}"><img src="{_esc(fname)}" '
            f'alt="Evidence card {_esc(card["gl_norm"])}"></a>'
            if fname.lower().endswith(".png")
            else ""
        )
        tiles.append(
            f'<div class="tile">'
            f'<div class="bar" style="background:{card["color"]}">'
            f'{_esc(card["label"])}</div>'
            f"{thumb}"
            f'<div class="info">'
            f"<p><b>{_esc(card['entity'])}</b> - GL {_esc(card['gl_norm'])}</p>"
            f"<p>Register {_esc(money(card['register_balance']))} | "
            f"TB {_esc(money(card['tb_balance']))} | "
            f"Diff {_esc(money(card['difference']))}</p>"
            f'<p class="tie {tie_cls}">{_esc(tie_word)}</p>'
            f"</div>"
            f'<a class="open" href="{_esc(fname)}">Open evidence card</a>'
            f"</div>"
        )
    body = (
        '<div class="grid">' + "".join(tiles) + "</div>"
        if tiles
        else '<p class="empty">No exceptions - no evidence cards to show.</p>'
    )
    as_of_bit = f"As of {_esc(as_of)}. " if as_of else ""
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Evidence Cards - Cash Completeness [FICTIONAL DATA]</title>
<style>{_INDEX_CSS}</style></head><body><div class="wrap">
<h1>Evidence Cards - Cash Completeness Review</h1>
<p class="meta">{as_of_bit}{len(entries)} card(s), rendered as {_esc(mode)}.
Each card shows the register's own transactions with traced sweep rows
highlighted, and closes with a one-line tie-out.</p>
{body}
<p class="fine">{_esc(_FOOTNOTE)}</p>
</div></body></html>
"""
    path = os.path.join(out_dir, "INDEX.html")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    return path


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def render_evidence_cards(
    exceptions: Iterable[Any],
    registers: Iterable[Any],
    out_dir: str,
    force_html: bool = False,
) -> List[str]:
    """Render one evidence card per exception plus an ``INDEX.html`` gallery.

    Args:
        exceptions: classified ``ExceptionItem`` objects (or their plain-dict
            serializations) from ``reconcile``.
        registers: the full ``RegisterAccount`` population; each card pulls
            its verbatim transaction table from the account whose ``gl_norm``
            matches the exception.
        out_dir: destination directory (created if missing).
        force_html: skip matplotlib even when it is importable -- used by
            tests to exercise the fallback path deterministically.

    Returns:
        Paths of every file written; ``INDEX.html`` is always last and is
        always written, even for an empty exception list.
    """
    os.makedirs(out_dir, exist_ok=True)

    reg_by_gl: Dict[str, Any] = {}
    latest_as_of = ""
    for reg in registers:
        gl = str(field(reg, "gl_norm") or "")
        if gl and gl not in reg_by_gl:
            reg_by_gl[gl] = reg
        latest_as_of = max(latest_as_of, str(field(reg, "as_of") or ""))

    kind_rank = {kind: i for i, kind in enumerate(KIND_ORDER)}
    ordered = sorted(
        exceptions,
        key=lambda e: (
            kind_rank.get(str(field(e, "kind") or ""), len(kind_rank)),
            str(field(e, "gl_norm") or ""),
        ),
    )

    use_png = HAVE_MATPLOTLIB and not force_html
    paths: List[str] = []
    entries: List[Dict[str, Any]] = []
    for i, exc in enumerate(ordered, 1):
        gl = str(field(exc, "gl_norm") or "")
        card = _card_data(exc, reg_by_gl.get(gl))
        stem = f"{i:02d}_{_slug(card['kind'])}_{_slug(gl)}"
        if use_png:
            try:
                fname = stem + ".png"
                paths.append(
                    _render_card_png(card, os.path.join(out_dir, fname))
                )
            except Exception:  # matplotlib present but broken: degrade, don't die
                fname = stem + ".html"
                paths.append(
                    _render_card_html(card, os.path.join(out_dir, fname))
                )
        else:
            fname = stem + ".html"
            paths.append(_render_card_html(card, os.path.join(out_dir, fname)))
        entries.append({"card": card, "filename": fname})

    mode = "matplotlib PNG" if use_png else "self-contained HTML (matplotlib not available)"
    paths.append(_write_index(entries, out_dir, mode, latest_as_of))
    return paths
