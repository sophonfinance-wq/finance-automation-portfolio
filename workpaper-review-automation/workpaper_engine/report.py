"""
Report rendering for the workpaper review & handback engine.
============================================================

Two renderers over the same result object: a markdown report a person reads and
a JSON report a pipeline consumes. Both are pure functions of the analysis
result -- byte-stable for a given input, no clock, no environment.

The markdown leads with the verdict and the counts, because the first question a
reviewer asks is "can this go out", not "what are the details".
"""

from __future__ import annotations

import json
from typing import Any

from .money import format_cents

__all__ = ["build_markdown_report", "build_json_report"]

_SEVERITY_ORDER = {"FAIL": 0, "FLAG": 1}


def _fmt_detail(detail: dict[str, Any]) -> str:
    bits = []
    for k in sorted(detail):
        v = detail[k]
        if k.endswith("_cents") and isinstance(v, int):
            bits.append("%s %s" % (k[: -len("_cents")], format_cents(v)))
        else:
            bits.append("%s %s" % (k, v))
    return "; ".join(bits)


def build_markdown_report(result: dict[str, Any]) -> str:
    """Render a folder- or package-level result as markdown."""
    packages = result.get("packages", [result])
    lines: list[str] = []
    lines.append("# Workpaper review — handback report")
    lines.append("")
    lines.append("**Verdict: %s**" % result.get("verdict", "PASS"))
    lines.append("")
    lines.append("| Package | Entity | Verdict | Findings |")
    lines.append("|---|---|---|---:|")
    for p in packages:
        lines.append(
            "| %s | %s | %s | %d |"
            % (p["package_id"], p["entity"], p["verdict"], p["counts"]["findings"])
        )
    lines.append("")
    for p in packages:
        if not p["findings"]:
            continue
        lines.append("## %s — %s" % (p["package_id"], p["entity"]))
        lines.append("")
        lines.append("| Severity | Control | Address | Finding |")
        lines.append("|---|---|---|---|")
        for f in sorted(
            p["findings"],
            key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 9), f["control"], f["address"]),
        ):
            lines.append(
                "| %s | %s | `%s` | %s |"
                % (f["severity"], f["control"], f["address"], f["message"])
            )
        lines.append("")
        for f in sorted(p["findings"], key=lambda f: (f["control"], f["address"])):
            if f["detail"]:
                lines.append("- `%s` %s — %s" % (f["address"], f["control"], _fmt_detail(f["detail"])))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_json_report(result: dict[str, Any]) -> str:
    """Render the result as stable JSON."""
    return json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
