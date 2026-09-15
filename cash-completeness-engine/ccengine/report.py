"""Reporting layer: reviewer-ready Markdown and CSV outputs.

The engine's promise is a single sentence -- "no dollar is unaccounted
for" -- and this module is where that promise is written down in a form a
reviewer can check. Four artifacts are produced from one report dict:

    exec_summary.md          leads with the only question that matters
    resolution_schedule.md   every exception, grouped by class, with the fix
    scope_reconciliation.md  every register account in exactly one bucket
    journal_entries.csv      drafted entries with their discipline status

Everything here is presentation: numbers arrive already classified
(``reconcile``) and already drafted (``journal``), and are independently
re-derived from raw inputs by ``verify`` *after* the report is built. To
keep that verification honest, :func:`build_report` serializes everything
to plain dicts and lists -- the report is a data artifact, not a bundle of
live objects.

All entities, banks, accounts, and figures in this package are fictional
(Juniper 42 Development LLC, First Legacy Bank, Union National Bank, and
friends); see the repository README.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only; runtime access is duck-typed
    from .models import (
        ExceptionItem,
        RegisterAccount,
        ScopeReconciliation,
        TBRow,
        Verdict,
    )

# --------------------------------------------------------------------------
# Exception-class vocabulary (shared with evidence.py)
# --------------------------------------------------------------------------

KIND_ORDER: List[str] = [
    "A_UNMAPPED_SUCCESSOR",
    "B_STALE_CLOSEOUT",
    "C_TIMING",
    "D_UNEXPLAINED",
]

KIND_LABELS: Dict[str, str] = {
    "A_UNMAPPED_SUCCESSOR": "Class A - Unmapped successor account",
    "B_STALE_CLOSEOUT": "Class B - Stale close-out balance",
    "C_TIMING": "Class C - Timing difference",
    "D_UNEXPLAINED": "Class D - Unexplained",
}

KIND_ACTIONS: Dict[str, str] = {
    "A_UNMAPPED_SUCCESSOR": (
        "Map the live successor account into the trial balance. This is a "
        "completeness gap in the TB, not a cash gap."
    ),
    "B_STALE_CLOSEOUT": (
        "Book the close-out entry. The stale TB figure is the traced "
        "pre-sweep balance; every sweep destination is named below."
    ),
    "C_TIMING": (
        "No entry. Post-cutoff activity explains the difference and clears "
        "next period; re-check at the next close."
    ),
    "D_UNEXPLAINED": (
        "Investigate before close. Never book an entry against an "
        "unexplained difference."
    ),
}

PHANTOM_LABEL = "Phantom / no-register TB rows"


# --------------------------------------------------------------------------
# Small shared helpers (evidence.py imports these)
# --------------------------------------------------------------------------

def field(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a dataclass attribute or a mapping key.

    The reporting layer is representation-tolerant: it accepts the model
    objects from ``models.py`` or their plain-dict serializations (e.g. a
    report round-tripped through JSON), so a report can be rebuilt or
    re-rendered from saved inputs.
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def money(x: Optional[float]) -> str:
    """Format a number with thousands separators and parens for negatives.

    ``None`` renders as ``n/a`` so a missing TB balance is visibly missing,
    never silently zero.
    """
    if x is None:
        return "n/a"
    x = float(x)
    if x < 0:
        return f"({abs(x):,.2f})"
    return f"{x:,.2f}"


def _cell(text: Any) -> str:
    """Make a value safe inside a Markdown table cell."""
    return str(text if text is not None else "").replace("|", "/").replace("\n", " ")


def _write(path: str, text: str) -> str:
    """Write ``text`` to ``path`` (UTF-8, LF), creating parent dirs."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def _dest_phrase(dests: Sequence[Dict[str, Any]]) -> str:
    """Render traced destinations as one readable phrase."""
    if not dests:
        return "-"
    parts = [
        f"{d.get('date', '')} {d.get('counterparty', '') or '(unnamed)'} "
        f"{money(d.get('amount'))}"
        for d in dests
    ]
    return "; ".join(parts)


# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------

def _exception_dict(e: Any) -> Dict[str, Any]:
    """Serialize one ExceptionItem to a plain dict."""
    reg = field(e, "register_balance")
    tb = field(e, "tb_balance")
    dests = [
        {
            "date": str(field(d, "date") or ""),
            "counterparty": str(field(d, "counterparty") or ""),
            "amount": round(float(field(d, "amount") or 0.0), 2),
        }
        for d in (field(e, "destinations") or [])
    ]
    return {
        "kind": str(field(e, "kind") or ""),
        "gl_norm": str(field(e, "gl_norm") or ""),
        "entity": str(field(e, "entity") or ""),
        "register_balance": None if reg is None else round(float(reg), 2),
        "tb_balance": None if tb is None else round(float(tb), 2),
        "difference": round(float(reg or 0.0) - float(tb or 0.0), 2),
        "destinations": dests,
        "note": str(field(e, "note") or ""),
    }


def _tb_row_dict(r: Any) -> Dict[str, Any]:
    """Serialize one TBRow to a plain dict."""
    return {
        "source_file": str(field(r, "source_file") or ""),
        "sheet": str(field(r, "sheet") or ""),
        "gl_raw": str(field(r, "gl_raw") or ""),
        "gl_norm": str(field(r, "gl_norm") or ""),
        "title": str(field(r, "title") or ""),
        "balance": round(float(field(r, "balance") or 0.0), 2),
    }


def _summarize(exc_dicts: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per-class counts and totals for the exception population."""
    out: Dict[str, Dict[str, Any]] = {}
    for kind in KIND_ORDER:
        items = [e for e in exc_dicts if e["kind"] == kind]
        if not items:
            continue
        out[kind] = {
            "count": len(items),
            "register_total": round(
                sum(e["register_balance"] or 0.0 for e in items), 2
            ),
            "tb_total": round(sum(e["tb_balance"] or 0.0 for e in items), 2),
            "destinations_total": round(
                sum(d["amount"] for e in items for d in e["destinations"]), 2
            ),
        }
    return out


def _placeholder_dict(a: Any) -> Dict[str, Any]:
    """Serialize one placeholder-GL register account to a plain dict."""
    return {
        "entity": str(field(a, "entity") or ""),
        "bank": str(field(a, "bank") or ""),
        "gl_raw": str(field(a, "gl_raw") or ""),
        "gl_norm": str(field(a, "gl_norm") or ""),
        "balance": round(float(field(a, "balance") or 0.0), 2),
        "source_file": str(field(a, "source_file") or ""),
    }


def build_report(
    registers: Iterable[Any],
    tb_rows: Iterable[Any],
    exceptions: Iterable[Any],
    scope: Any,
    phantom_rows: Optional[Iterable[Any]] = None,
    as_of: str = "",
    placeholder_gls: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Assemble the engine's single report artifact as a plain dict.

    Args:
        registers: full bank-side population (``RegisterAccount`` objects).
        tb_rows: trial-balance cash rows (``TBRow`` objects).
        exceptions: classified ``ExceptionItem`` objects from ``reconcile``.
        scope: ``ScopeReconciliation`` (buckets / totals / ``foot()``).
        phantom_rows: TB rows flagged ``phantom_or_no_register`` -- lines
            with no register match ever (the mis-keyed-line lesson).
        as_of: reporting date; defaults to the latest register ``as_of``.
        placeholder_gls: register accounts whose GL key looks mis-keyed
            (from :func:`ccengine.reconcile.flag_placeholder_gls`). These
            still tie and stay in their scope bucket; the list travels
            alongside so the suspicious key reaches a reviewer.

    Returns:
        JSON-serializable dict. ``verify.independent_verify`` re-derives
        the population from raw inputs and cross-foots this dict, so it
        must carry the full scope reconciliation, not a summary of one.
    """
    registers = list(registers)
    tb_rows = list(tb_rows)
    exceptions = list(exceptions)
    phantoms = list(phantom_rows or [])
    placeholders = list(placeholder_gls or [])

    reg_total = sum(float(field(a, "balance") or 0.0) for a in registers)
    tb_total = sum(float(field(r, "balance") or 0.0) for r in tb_rows)
    if not as_of:
        as_of = max((str(field(a, "as_of") or "") for a in registers), default="")

    buckets = field(scope, "buckets") or {}
    totals = field(scope, "totals") or {}
    problems: List[str] = []
    foot = getattr(scope, "foot", None)
    if callable(foot):
        problems = [str(p) for p in foot(registers)]

    exc_dicts = [_exception_dict(e) for e in exceptions]
    return {
        "engine": "cash-completeness-engine",
        "as_of": as_of,
        "population": {
            "register_accounts": len(registers),
            "entities": sorted({str(field(a, "entity") or "") for a in registers}),
            "register_total": round(reg_total, 2),
            "register_gl_norms": sorted(
                str(field(a, "gl_norm") or "") for a in registers
            ),
            "tb_rows": len(tb_rows),
            "tb_cash_total": round(tb_total, 2),
        },
        "scope_reconciliation": {
            "buckets": {
                str(name): [str(g) for g in members]
                for name, members in dict(buckets).items()
            },
            "totals": {
                str(name): round(float(v), 2) for name, v in dict(totals).items()
            },
            "problems": problems,
        },
        "exceptions": exc_dicts,
        "phantom_or_no_register": [_tb_row_dict(r) for r in phantoms],
        "placeholder_gls": [_placeholder_dict(a) for a in placeholders],
        "exception_summary": _summarize(exc_dicts),
    }


# --------------------------------------------------------------------------
# scope_reconciliation.md
# --------------------------------------------------------------------------

def write_scope_reconciliation(report: Dict[str, Any], path: str) -> str:
    """Write the scope reconciliation: every register account, one bucket."""
    pop = report["population"]
    scope = report["scope_reconciliation"]
    buckets: Dict[str, List[str]] = scope["buckets"]
    totals: Dict[str, float] = scope["totals"]
    problems: List[str] = scope["problems"]

    out: List[str] = []
    out.append("# Scope Reconciliation - Cash Completeness [FICTIONAL DATA]")
    out.append("")
    out.append(
        f"**As of:** {report['as_of']} &nbsp;|&nbsp; "
        f"**Register population:** {pop['register_accounts']} accounts, "
        f"{money(pop['register_total'])} &nbsp;|&nbsp; "
        f"**TB cash rows:** {pop['tb_rows']}, {money(pop['tb_cash_total'])}"
    )
    out.append("")
    out.append(
        "> Population is built from the bank side (registers), not the trial "
        "balance. A TB-first reconciliation cannot see accounts the TB is "
        "missing; this schedule proves every register account landed in "
        "exactly one bucket."
    )
    out.append("")

    out.append("## Buckets")
    out.append("")
    out.append("| Bucket | Accounts | Total |")
    out.append("|--------|---------:|------:|")
    bucket_accounts = 0
    bucket_total = 0.0
    for name in sorted(buckets):
        members = buckets[name]
        total = float(totals.get(name, 0.0))
        bucket_accounts += len(members)
        bucket_total += total
        out.append(f"| {_cell(name)} | {len(members)} | {money(total)} |")
    out.append(
        f"| **All buckets** | **{bucket_accounts}** | **{money(bucket_total)}** |"
    )
    out.append("")

    out.append("## Bucket membership")
    out.append("")
    for name in sorted(buckets):
        members = buckets[name]
        out.append(f"### {name} ({len(members)} accounts)")
        out.append("")
        for gl in members:
            out.append(f"- `{gl}`")
        if not members:
            out.append("- (none)")
        out.append("")

    out.append("## Foot check")
    out.append("")
    checks_ok = True
    if bucket_accounts != pop["register_accounts"]:
        checks_ok = False
        out.append(
            f"- FAIL: buckets hold {bucket_accounts} accounts but the register "
            f"population has {pop['register_accounts']}."
        )
    if abs(bucket_total - float(pop["register_total"])) >= 0.005:
        checks_ok = False
        out.append(
            f"- FAIL: bucket totals foot to {money(bucket_total)} but the "
            f"register population totals {money(pop['register_total'])}."
        )
    for p in problems:
        checks_ok = False
        out.append(f"- FAIL: {_cell(p)}")
    if checks_ok:
        out.append(
            "- PASS: every register account appears in exactly one bucket and "
            "the bucket totals re-add to the register population."
        )
    out.append("")

    placeholders: List[Dict[str, Any]] = report.get("placeholder_gls", []) or []
    out.append(f"## Placeholder / mis-keyed GL keys ({len(placeholders)})")
    out.append("")
    if placeholders:
        out.append(
            "> These register accounts tie to the trial balance and stay in "
            "their scope bucket above, but their GL key matches a mis-keyed "
            "placeholder pattern (e.g. `001-001-...`). A key like this can "
            "foot perfectly and still be wrong; give each one a human look "
            "before sign-off."
        )
        out.append("")
        out.append("| Entity | Bank | GL (raw) | GL (normalized) | Register balance |")
        out.append("|--------|------|----------|-----------------|-----------------:|")
        for a in placeholders:
            out.append(
                f"| {_cell(a.get('entity'))} | {_cell(a.get('bank'))} | "
                f"`{_cell(a.get('gl_raw'))}` | `{_cell(a.get('gl_norm'))}` | "
                f"{money(a.get('balance'))} |"
            )
    else:
        out.append(
            "None. Every register account carries a well-formed GL key."
        )
    out.append("")
    return _write(path, "\n".join(out))


# --------------------------------------------------------------------------
# resolution_schedule.md
# --------------------------------------------------------------------------

def write_resolution_schedule(report: Dict[str, Any], path: str) -> str:
    """Write the resolution schedule: every exception, grouped, with a fix."""
    exc_dicts: List[Dict[str, Any]] = report["exceptions"]
    phantoms: List[Dict[str, Any]] = report["phantom_or_no_register"]

    out: List[str] = []
    out.append("# Resolution Schedule - Cash Completeness [FICTIONAL DATA]")
    out.append("")
    out.append(
        f"**As of:** {report['as_of']} &nbsp;|&nbsp; "
        f"**Exceptions:** {len(exc_dicts)} &nbsp;|&nbsp; "
        f"**Phantom TB rows:** {len(phantoms)}"
    )
    out.append("")
    out.append(
        "Every item below is classified; nothing is netted away or silently "
        "dropped. Class D items block sign-off until explained."
    )
    out.append("")

    for kind in KIND_ORDER:
        items = [e for e in exc_dicts if e["kind"] == kind]
        if not items:
            continue
        out.append(f"## {KIND_LABELS[kind]} ({len(items)})")
        out.append("")
        out.append(f"**Action:** {KIND_ACTIONS[kind]}")
        out.append("")
        out.append(
            "| Entity | GL account | Register balance | TB balance | "
            "Difference | Traced destinations | Note |"
        )
        out.append(
            "|--------|------------|-----------------:|-----------:|"
            "-----------:|---------------------|------|"
        )
        for e in items:
            out.append(
                f"| {_cell(e['entity'])} | `{e['gl_norm']}` | "
                f"{money(e['register_balance'])} | {money(e['tb_balance'])} | "
                f"{money(e['difference'])} | {_cell(_dest_phrase(e['destinations']))} | "
                f"{_cell(e['note'])} |"
            )
        reg_sum = sum(e["register_balance"] or 0.0 for e in items)
        tb_sum = sum(e["tb_balance"] or 0.0 for e in items)
        diff_sum = sum(e["difference"] for e in items)
        out.append(
            f"| **Total** | | **{money(reg_sum)}** | **{money(tb_sum)}** | "
            f"**{money(diff_sum)}** | | |"
        )
        out.append("")

    out.append(f"## {PHANTOM_LABEL} ({len(phantoms)})")
    out.append("")
    if phantoms:
        out.append(
            "**Action:** Retire or remap each line. No register account has "
            "ever matched these GL keys -- typically a mis-keyed BAL row or a "
            "placeholder that survived a mapping change."
        )
        out.append("")
        out.append("| Sheet | GL (raw) | GL (normalized) | Title | TB balance |")
        out.append("|-------|----------|-----------------|-------|-----------:|")
        for r in phantoms:
            out.append(
                f"| {_cell(r['sheet'])} | `{_cell(r['gl_raw'])}` | "
                f"`{r['gl_norm']}` | {_cell(r['title'])} | {money(r['balance'])} |"
            )
        ph_total = sum(r["balance"] for r in phantoms)
        out.append(f"| **Total** | | | | **{money(ph_total)}** |")
    else:
        out.append("None. Every TB cash row matched a register account.")
    out.append("")
    return _write(path, "\n".join(out))


# --------------------------------------------------------------------------
# exec_summary.md
# --------------------------------------------------------------------------

def _lead_answer(report: Dict[str, Any]) -> List[str]:
    """Answer the headline question honestly from the report contents."""
    unexplained = [
        e for e in report["exceptions"] if e["kind"] == "D_UNEXPLAINED"
    ]
    problems = report["scope_reconciliation"]["problems"]
    lines: List[str] = ["**Is any dollar unaccounted for?**"]
    if not unexplained and not problems:
        lines.append("")
        lines.append(
            "**No.** Every register account is in scope exactly once, every "
            "exception is classified, and every traced dollar lands somewhere "
            "named. Details and per-item evidence follow."
        )
    else:
        lines.append("")
        parts = []
        if unexplained:
            open_total = sum(e["difference"] for e in unexplained)
            parts.append(
                f"{len(unexplained)} item(s) with a net difference of "
                f"{money(open_total)} remain unexplained (Class D)"
            )
        if problems:
            parts.append(
                f"the scope reconciliation does not foot "
                f"({len(problems)} problem(s))"
            )
        lines.append(
            "**Not yet.** " + " and ".join(parts) + ". These block sign-off; "
            "see the resolution schedule."
        )
    return lines


def write_exec_summary(
    report: Dict[str, Any],
    path: str,
    drafts: Optional[Iterable[Any]] = None,
    verdict: Any = None,
) -> str:
    """Write the executive summary, leading with the headline question.

    Args:
        report: dict from :func:`build_report`.
        path: destination for ``exec_summary.md``.
        drafts: optional JE drafts from ``journal.draft_entries`` -- adds a
            journal-entry discipline section.
        verdict: optional ``Verdict`` from ``verify.independent_verify`` --
            adds the independent verification result.
    """
    pop = report["population"]
    summary = report["exception_summary"]
    phantoms = report["phantom_or_no_register"]

    out: List[str] = []
    out.append("# Executive Summary - Cash Completeness Review [FICTIONAL DATA]")
    out.append("")
    out.extend(_lead_answer(report))
    out.append("")
    out.append(
        f"**As of:** {report['as_of']} &nbsp;|&nbsp; "
        f"**Register population:** {pop['register_accounts']} accounts across "
        f"{len(pop['entities'])} entities, {money(pop['register_total'])} "
        f"&nbsp;|&nbsp; **TB cash total:** {money(pop['tb_cash_total'])} "
        f"&nbsp;|&nbsp; **Difference:** "
        f"{money(pop['register_total'] - pop['tb_cash_total'])}"
    )
    out.append("")
    out.append(
        "> Method note: the population is built from the bank side (every "
        "register), not from the trial balance. A TB-first reconciliation "
        "cannot see accounts the TB is missing."
    )
    out.append("")

    out.append("## Exceptions at a glance")
    out.append("")
    if summary or phantoms:
        out.append("| Class | Count | Register balance | TB balance | Action |")
        out.append("|-------|------:|-----------------:|-----------:|--------|")
        for kind in KIND_ORDER:
            if kind not in summary:
                continue
            s = summary[kind]
            out.append(
                f"| {KIND_LABELS[kind]} | {s['count']} | "
                f"{money(s['register_total'])} | {money(s['tb_total'])} | "
                f"{_cell(KIND_ACTIONS[kind])} |"
            )
        if phantoms:
            ph_total = sum(r["balance"] for r in phantoms)
            out.append(
                f"| {PHANTOM_LABEL} | {len(phantoms)} | n/a | {money(ph_total)} | "
                f"Retire or remap the line; no register account has ever "
                f"matched it. |"
            )
    else:
        out.append("No exceptions. The register population ties to the TB.")
    out.append("")

    out.append("## Scope reconciliation")
    out.append("")
    problems = report["scope_reconciliation"]["problems"]
    n_buckets = len(report["scope_reconciliation"]["buckets"])
    if problems:
        out.append(
            f"FAIL - {pop['register_accounts']} register accounts across "
            f"{n_buckets} buckets; {len(problems)} problem(s):"
        )
        out.append("")
        for p in problems:
            out.append(f"- {_cell(p)}")
    else:
        out.append(
            f"PASS - every one of the {pop['register_accounts']} register "
            f"accounts appears in exactly one of {n_buckets} buckets and the "
            f"totals re-add. See `scope_reconciliation.md`."
        )
    out.append("")

    placeholders = report.get("placeholder_gls", []) or []
    if placeholders:
        keys = ", ".join(f"`{_cell(a.get('gl_norm'))}`" for a in placeholders)
        out.append(
            f"**Placeholder GL keys flagged for review ({len(placeholders)}):** "
            f"{keys}. These accounts tie and stay in scope, but their GL key "
            f"matches a mis-keyed placeholder pattern; confirm the key before "
            f"sign-off. See `scope_reconciliation.md`."
        )
        out.append("")

    if drafts is not None:
        drafts = list(drafts)
        out.append("## Journal-entry discipline")
        out.append("")
        by_status: Dict[str, int] = {}
        questions: List[str] = []
        for d in drafts:
            status = str(field(d, "status") or "")
            by_status[status] = by_status.get(status, 0) + 1
            q = field(d, "question")
            if status == "needs_judgment" and q:
                questions.append(f"`{field(d, 'ref')}`: {q}")
        counts = ", ".join(
            f"{by_status.get(s, 0)} {s}"
            for s in ("ready", "needs_judgment", "no_entry")
        )
        out.append(
            f"{len(drafts)} draft(s): {counts}. An entry is `ready` only when "
            f"both the amount and the offset are fully documented; offsets "
            f"are never invented. See `journal_entries.csv`."
        )
        if questions:
            out.append("")
            out.append("Open questions for the reviewer:")
            out.append("")
            for q in questions:
                out.append(f"- {_cell(q)}")
        out.append("")

    if verdict is not None:
        out.append("## Independent verification")
        out.append("")
        status = str(field(verdict, "status") or "")
        out.append(
            f"**{status}** -- the verifier re-derived the population from raw "
            f"inputs with its own logic and cross-footed this report."
        )
        findings = field(verdict, "findings") or []
        if findings:
            out.append("")
            out.append("| Severity | Finding | Fix |")
            out.append("|----------|---------|-----|")
            for f in findings:
                out.append(
                    f"| {_cell(field(f, 'severity'))} | "
                    f"{_cell(field(f, 'finding'))} | {_cell(field(f, 'fix'))} |"
                )
        out.append("")

    return _write(path, "\n".join(out))


# --------------------------------------------------------------------------
# journal_entries.csv
# --------------------------------------------------------------------------

def _amt(v: Any) -> str:
    """Format a debit/credit cell: blank when absent or zero."""
    if v is None or v == "":
        return ""
    v = float(v)
    if abs(v) < 0.005:
        return ""
    return f"{v:.2f}"


def write_journal_entries_csv(drafts: Iterable[Any], path: str) -> str:
    """Write JE drafts to CSV, one row per line (or per line-less draft).

    Faithful transcription only: statuses and open questions come from
    ``journal.draft_entries`` and are not editorialized here.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    headers = [
        "ref", "entity", "status", "line", "account", "debit", "credit",
        "question",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for d in drafts:
            ref = field(d, "ref")
            entity = field(d, "entity")
            status = field(d, "status")
            question = field(d, "question") or ""
            lines = list(field(d, "lines") or [])
            if not lines:
                writer.writerow([ref, entity, status, "", "", "", "", question])
                continue
            for i, line in enumerate(lines, 1):
                writer.writerow([
                    ref,
                    entity,
                    status,
                    i,
                    field(line, "account"),
                    _amt(field(line, "debit")),
                    _amt(field(line, "credit")),
                    question if i == 1 else "",
                ])
    return path


# --------------------------------------------------------------------------
# Convenience: write the full output set
# --------------------------------------------------------------------------

def write_outputs(
    report: Dict[str, Any],
    drafts: Iterable[Any],
    out_dir: str,
    verdict: Any = None,
) -> List[str]:
    """Write all four report artifacts into ``out_dir``; return their paths."""
    drafts = list(drafts)
    return [
        write_exec_summary(
            report, os.path.join(out_dir, "exec_summary.md"),
            drafts=drafts, verdict=verdict,
        ),
        write_resolution_schedule(
            report, os.path.join(out_dir, "resolution_schedule.md")
        ),
        write_scope_reconciliation(
            report, os.path.join(out_dir, "scope_reconciliation.md")
        ),
        write_journal_entries_csv(
            drafts, os.path.join(out_dir, "journal_entries.csv")
        ),
    ]
