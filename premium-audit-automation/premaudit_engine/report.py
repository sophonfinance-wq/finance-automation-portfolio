"""Byte-stable emitters for the audit-response package (JSON + Markdown).

The working package (``package_json`` / ``package_markdown``) retains the full
internal workpaper: every line, both period cuts, vendor ids, and triage. The
deliverable (``deliverable_json``) is a separate emitter for the carrier-facing
response - in-window lines only, on an allow-listed field set, with the period
basis date chosen as transaction date when known else accounting date. Keeping
the two emitters separate means a leak of an internal field into the
deliverable is a test failure, not a judgment call.
"""
from __future__ import annotations

import json
from collections import Counter

from .model import AuditPackage
from .money import format_cents

DELIVERABLE_FIELDS = (
    "job", "cost_code", "tran_type", "date", "vendor_name", "invoice",
    "amount_cents", "coverage_note",
)


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


def deliverable_json(pkg: AuditPackage) -> str:
    """Carrier-facing subset: in-window lines on the deliverable allow-list."""
    lines = []
    total = 0
    for t in pkg.lines:
        if not t.in_window:
            continue
        d = t.line.txn_date if t.line.txn_date is not None else t.line.acctg_date
        lines.append({
            "job": t.line.job,
            "cost_code": t.line.cost_code,
            "tran_type": t.line.tran_type.value,
            "date": d.isoformat(),
            "vendor_name": t.line.vendor_name,
            "invoice": t.line.invoice,
            "amount_cents": t.line.amount_cents,
            "coverage_note": t.triage.value,
        })
        total += t.line.amount_cents
    payload = {
        "period": {"start": pkg.window.start.isoformat(),
                   "end": pkg.window.end.isoformat()},
        "total_cents": total,
        "lines": lines,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def deliverable_leaks(pkg: AuditPackage) -> list[str]:
    """Sorted unique field names present on deliverable lines but not allow-listed."""
    payload = json.loads(deliverable_json(pkg))
    allow = frozenset(DELIVERABLE_FIELDS)
    found: set[str] = set()
    for line in payload.get("lines", []):
        found.update(k for k in line if k not in allow)
    return sorted(found)
