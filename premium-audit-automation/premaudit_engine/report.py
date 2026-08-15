"""Byte-stable emitters for the audit-response package (JSON + Markdown)."""
from __future__ import annotations

import json
from collections import Counter

from .model import AuditPackage
from .money import format_cents


def package_json(pkg: AuditPackage) -> str:
    payload = {
        "company": pkg.company,
        "window": {"start": pkg.window.start.isoformat(),
                   "end": pkg.window.end.isoformat()},
        "totals": {"window_cents": pkg.window_total_cents,
                   "full_cents": pkg.full_total_cents},
        "lines": [
            {
                "job": t.line.job,
                "cost_code": t.line.cost_code,
                "tran_type": t.line.tran_type.value,
                "acctg_date": t.line.acctg_date.isoformat(),
                "vendor_id": t.line.vendor_id,
                "vendor_name": t.line.vendor_name,
                "invoice": t.line.invoice,
                "amount_cents": t.line.amount_cents,
                "in_window": t.in_window,
                "triage": t.triage.value,
            }
            for t in pkg.lines
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def package_markdown(pkg: AuditPackage) -> str:
    tri = Counter(t.triage.value for t in pkg.lines)
    jobs = sorted({t.line.job for t in pkg.lines})
    out = [
        f"# Premium audit response - {pkg.company}",
        "",
        f"Window {pkg.window.start.isoformat()} .. {pkg.window.end.isoformat()} (inclusive)",
        "",
        f"| Jobs | Lines | Window total | Full total |",
        f"|---|---|---|---|",
        f"| {len(jobs)} | {len(pkg.lines)} | {format_cents(pkg.window_total_cents)} | "
        f"{format_cents(pkg.full_total_cents)} |",
        "",
        "## Triage",
        "",
    ]
    for name in sorted(tri):
        out.append(f"- {name}: {tri[name]}")
    out.append("")
    return "\n".join(out)
