"""
Report rendering: byte-stable markdown and JSON artifacts.
==========================================================

The same list of :class:`~ap_engine.model.DocumentReport` objects is rendered
two ways:

* :func:`build_markdown_report` -- a committed, human-readable exception report.
* :func:`build_json_report` -- the structured payload other tools consume.

Byte stability is the contract. Markdown is assembled as ``lines: list[str]``
joined with ``"\\n"``; JSON is dumped with ``indent=2`` and **no** ``sort_keys``,
so the literal dict order in this module is the published key order. Every dict
and set iteration is forced through ``sorted()`` with a tiebreaker.

The only value that legitimately changes between two runs over the same corpus
is ``generated_utc``; the determinism test pops it before comparing.

Output is plain ASCII, so a terminal with a legacy code page needs no encoding
fallback.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .engine import REGISTRY, RULE_FAMILIES, overall_verdict
from .model import DocumentReport, Status, Verdict

#: Part number of this engine on the platform.
PART_NO = "SFS-E10-APX"

#: Canonical display name.
ENGINE_NAME = "Accounts Payable"

_STATUS_TAG = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.FLAG: "FLAG"}
_VERDICT_TAG = {Verdict.PASS: "PASS", Verdict.REVIEW: "REVIEW", Verdict.FAIL: "FAIL"}

#: Human labels for the rule families, in registry order.
_FAMILY_LABEL: dict[str, str] = {
    "set": "Structural precondition",
    "post": "Posting integrity",
    "gate": "Payment release gate",
    "route": "Routing and segregation of duties",
    "ir": "Information reporting",
    "cmt": "Commitment hygiene",
}


def _family(rule: str) -> str:
    """Return the family prefix of ``rule`` (``"post"``, ``"gate"``, ...)."""
    return rule.split("_", 1)[0]


def total_counts(reports: list[DocumentReport]) -> dict[str, int]:
    """Return a ``{status: count}`` tally across every report."""
    out = {s.value: 0 for s in Status}
    for report in reports:
        for status, count in report.counts().items():
            out[status] += count
    return out


def family_counts(reports: list[DocumentReport]) -> dict[str, dict[str, int]]:
    """Return ``{family: {status: count}}`` across every report.

    Families appear in :data:`~ap_engine.engine.RULE_FAMILIES` order, which is
    registry order, so the rollup table is stable.
    """
    out: dict[str, dict[str, int]] = {
        family: {s.value: 0 for s in Status} for family in RULE_FAMILIES
    }
    for report in reports:
        for finding in report.findings:
            bucket = out.get(_family(finding.rule))
            if bucket is not None:
                bucket[finding.status.value] += 1
    return out


def build_json_report(reports: list[DocumentReport]) -> dict:
    """Assemble the structured JSON report for a run."""
    return {
        "tool": "ap_engine",
        "engine": ENGINE_NAME,
        "part_no": PART_NO,
        "version": __version__,
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall_verdict": overall_verdict(reports).value,
        "document_count": len(reports),
        "counts": total_counts(reports),
        "family_counts": family_counts(reports),
        "registry": [rule_id for rule_id, _ in REGISTRY],
        "reports": [r.to_dict() for r in reports],
    }


def build_markdown_report(reports: list[DocumentReport]) -> str:
    """Render a human-readable exception report for a run."""
    lines: list[str] = []
    add = lines.append
    overall = overall_verdict(reports)
    counts = total_counts(reports)

    add(f"# {ENGINE_NAME} Control Report ({PART_NO})")
    add("")
    add(
        "> Fully synthetic, seeded data. Invented entities, vendors, jobs and "
        "identifiers for demonstration. Not real data."
    )
    add("")
    add(f"**Overall verdict:** {_VERDICT_TAG[overall]}")
    add("")
    add(
        f"Document sets analyzed: {len(reports)} - "
        f"PASS {counts['PASS']} / FAIL {counts['FAIL']} / FLAG {counts['FLAG']} "
        f"across {len(REGISTRY)} registered controls."
    )
    add("")

    add("## Control families")
    add("")
    add("| Family | Controls | PASS | FAIL | FLAG |")
    add("| --- | --- | --: | --: | --: |")
    per_family = family_counts(reports)
    for family in RULE_FAMILIES:
        registered = sum(1 for rule_id, _ in REGISTRY if _family(rule_id) == family)
        bucket = per_family[family]
        add(
            f"| {_FAMILY_LABEL[family]} (`{family}_*`) | {registered} | "
            f"{bucket['PASS']} | {bucket['FAIL']} | {bucket['FLAG']} |"
        )
    add("")

    add("## Document sets")
    add("")
    add("| Document set | Verdict | PASS | FAIL | FLAG | Controls fired |")
    add("| --- | --- | --: | --: | --: | --- |")
    for report in reports:
        c = report.counts()
        fired = ", ".join(report.rules_fired()) or "-"
        add(
            f"| {report.document} | {_VERDICT_TAG[report.verdict]} | "
            f"{c['PASS']} | {c['FAIL']} | {c['FLAG']} | {fired} |"
        )
    add("")

    add("## Exceptions")
    add("")
    for report in reports:
        add(f"### {report.document} - {_VERDICT_TAG[report.verdict]}")
        add("")
        actionable = [f for f in report.findings if f.status is not Status.PASS]
        if not actionable:
            add("All controls held.")
            add("")
            continue
        add("| Status | Control | Location | Message |")
        add("| --- | --- | --- | --- |")
        for finding in actionable:
            message = finding.message.replace("|", "\\|")
            add(
                f"| {_STATUS_TAG[finding.status]} | {finding.rule} | "
                f"{finding.location} | {message} |"
            )
        add("")

    add("## Registered controls")
    add("")
    add("| Control | Family |")
    add("| --- | --- |")
    for rule_id, _fn in REGISTRY:
        add(f"| {rule_id} | {_FAMILY_LABEL[_family(rule_id)]} |")
    add("")
    return "\n".join(lines)


def write_reports(
    reports: list[DocumentReport],
    *,
    json_path: Path | str | None = None,
    md_path: Path | str | None = None,
) -> list[Path]:
    """Write the requested artifacts and return the paths written, in order."""
    written: list[Path] = []
    if json_path is not None:
        target = Path(json_path)
        target.write_text(
            json.dumps(build_json_report(reports), indent=2), encoding="utf-8"
        )
        written.append(target)
    if md_path is not None:
        target = Path(md_path)
        target.write_text(build_markdown_report(reports), encoding="utf-8")
        written.append(target)
    return written
