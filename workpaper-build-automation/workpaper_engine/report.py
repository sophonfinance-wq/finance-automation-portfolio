"""
Report rendering for the tax workpaper build engine.
====================================================

Three renderings. Two of them describe the controls -- a structured JSON
document for machines and a markdown document for humans -- and the third
describes the **build**: a markdown build register listing every constructed
cell beside the derivation that produced it, which is the page a reviewer ticks
before signing.

All three are **byte-stable**: the same corpus produces the same bytes, with no
timestamps, absolute paths or hash-ordered iteration anywhere in the output.
That is what makes the committed report diffable -- a change in the diff means a
change in the controls or the build, not a change in when it was run.
"""

from __future__ import annotations

import json
from pathlib import Path

from .build import WorkpaperPackage
from .engine import REGISTRY, SEVERITY, overall_verdict
from .model import DocumentReport, Status, Verdict
from .money import fmt

#: Report title, used in the markdown heading.
TITLE = "Tax workpaper build & carry-down control report"


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
        "file_count": len(reports),
        "rule_count": len(REGISTRY),
        "rules": [
            {
                "rule": rule_id,
                "severity": SEVERITY.get(rule_id, Status.FAIL).value,
                "exceptions": fired.get(rule_id, 0),
            }
            for rule_id in _rule_index()
        ],
        "files": [r.to_dict() for r in reports],
    }


def build_markdown_report(reports: list[DocumentReport]) -> str:
    """Build the human-readable control report as a markdown string."""
    overall = overall_verdict(reports)
    tally = {v.value: 0 for v in Verdict}
    for report in reports:
        tally[report.verdict.value] += 1

    lines: list[str] = [
        f"# {TITLE}",
        "",
        f"**Overall verdict:** {overall.value}",
        "",
        f"- Build files analyzed: {len(reports)}",
        f"- Controls in registry: {len(REGISTRY)}",
        f"- PASS / REVIEW / FAIL: {tally['PASS']} / {tally['REVIEW']} / {tally['FAIL']}",
        "",
        "The engine builds the package; these controls prove what it built. All data is",
        "fictional. The controls never write to a source artifact, the builder never writes",
        "to its inputs, and every fiscal year is read from the file, never the system clock.",
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

    lines += ["", "## Build files", ""]
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


def build_register_markdown(package: WorkpaperPackage) -> str:
    """Render a built package's build register as a reviewable markdown page.

    One row per constructed cell, grouped by schedule and in construction order,
    each beside the derivation that produced it. This is the artifact that makes
    the build reviewable rather than merely repeatable: a reviewer reads the
    derivation, agrees with it, and the edit-scope control guarantees nothing
    outside this page moved.
    """
    entries = package.build_register
    manifest = package.manifest_doc()
    lines: list[str] = [
        f"# Build register - {package.document_id}",
        "",
        f"- Entity block: `{package.entity_block}`",
        f"- Fiscal year built: {package.fiscal_year} (rolled from "
        f"{package.prior_fiscal_year})",
        f"- Harvest date: {package.harvest_date}",
        f"- Constructed cells: {len(entries)}",
        "",
        "## Chain of custody",
        "",
        "| Digest | Value |",
        "|--------|-------|",
        f"| locked source | `{manifest['locked_source_digest']}` |",
        f"| pre-build image | `{manifest['prebuild_image_digest']}` |",
        f"| built package | `{manifest['built_package_digest']}` |",
        "",
    ]
    schedules: list[str] = []
    for entry in entries:
        if entry.schedule not in schedules:
            schedules.append(entry.schedule)
    for schedule in schedules:
        lines += [
            f"## {schedule}",
            "",
            "| Cell | Value | Derived from |",
            "|------|-------|--------------|",
        ]
        for entry in entries:
            if entry.schedule != schedule:
                continue
            value = (
                fmt(entry.value)
                if isinstance(entry.value, int) and not isinstance(entry.value, bool)
                else str(entry.value)
            )
            lines.append(f"| `{entry.cell_id}` | {value} | {entry.derivation} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_reports(
    reports: list[DocumentReport],
    *,
    json_path: str | Path | None = None,
    md_path: str | Path | None = None,
) -> list[Path]:
    """Write whichever control reports were requested; return the paths written."""
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
