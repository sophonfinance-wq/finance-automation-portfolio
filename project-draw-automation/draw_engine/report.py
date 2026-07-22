"""
Report rendering for the project draw engine.
=============================================

Two renderings of the same findings: a structured JSON document for machines and
a markdown document for humans. Both are **byte-stable** -- the same corpus
produces the same bytes, with no timestamps, absolute paths or hash-ordered
iteration anywhere in the output. That is what makes the committed report
diffable: a change in the diff means a change in the controls, not a change in
when the report was run.
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine import REGISTRY, SEVERITY, overall_verdict
from .model import DocumentReport, Status, Verdict

#: Report title, used in the markdown heading.
TITLE = "Project draw control report"


def _rule_index() -> list[str]:
    """Rule ids in registry order."""
    return [rule_id for rule_id, _fn in REGISTRY]


def build_json_report(reports: list[DocumentReport]) -> dict:
    """Build the structured report as a JSON-serialisable dict."""
    overall = overall_verdict(reports)
    fired: dict[str, int] = {}
    for report in reports:
        for finding in report.findings:
            if finding.status is not Status.PASS:
                fired[finding.rule] = fired.get(finding.rule, 0) + 1
    return {
        "title": TITLE,
        "overall_verdict": overall.value,
        "package_count": len(reports),
        "rule_count": len(REGISTRY),
        "rules": [
            {"rule": rule_id, "severity": SEVERITY.get(rule_id, Status.FAIL).value,
             "exceptions": fired.get(rule_id, 0)}
            for rule_id in _rule_index()
        ],
        "packages": [r.to_dict() for r in reports],
    }


def build_markdown_report(reports: list[DocumentReport]) -> str:
    """Build the human-readable report as a markdown string."""
    overall = overall_verdict(reports)
    tally = {v.value: 0 for v in Verdict}
    for report in reports:
        tally[report.verdict.value] += 1

    lines: list[str] = [
        f"# {TITLE}",
        "",
        f"**Overall verdict:** {overall.value}",
        "",
        f"- Packages analyzed: {len(reports)}",
        f"- Controls in registry: {len(REGISTRY)}",
        f"- PASS / REVIEW / FAIL: {tally['PASS']} / {tally['REVIEW']} / {tally['FAIL']}",
        "",
        "All data is fictional. The engine is read-only and never writes to a source",
        "artifact.",
        "",
        "## Controls",
        "",
        "| # | Rule | Severity | Exceptions |",
        "|---|------|----------|------------|",
    ]
    fired: dict[str, int] = {}
    for report in reports:
        for finding in report.findings:
            if finding.status is not Status.PASS:
                fired[finding.rule] = fired.get(finding.rule, 0) + 1
    for i, rule_id in enumerate(_rule_index(), 1):
        sev = SEVERITY.get(rule_id, Status.FAIL).value
        lines.append(f"| {i} | `{rule_id}` | {sev} | {fired.get(rule_id, 0)} |")

    lines += ["", "## Packages", ""]
    for report in reports:
        counts = report.counts()
        lines += [
            f"### {report.document}",
            "",
            f"**Verdict:** {report.verdict.value} "
            f"(PASS {counts['PASS']}, FLAG {counts['FLAG']}, FAIL {counts['FAIL']})",
            "",
        ]
        actionable = [f for f in report.findings if f.status is not Status.PASS]
        if not actionable:
            lines += ["All controls held.", ""]
            continue
        for finding in actionable:
            lines.append(
                f"- **{finding.status.value}** `{finding.rule}` @ `{finding.location}`  "
            )
            lines.append(f"  {finding.message}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_reports(
    reports: list[DocumentReport],
    *,
    json_path: str | Path | None = None,
    md_path: str | Path | None = None,
) -> list[Path]:
    """Write whichever reports were requested; return the paths written."""
    written: list[Path] = []
    if json_path:
        p = Path(json_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(build_json_report(reports), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(p)
    if md_path:
        p = Path(md_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(build_markdown_report(reports), encoding="utf-8")
        written.append(p)
    return written
