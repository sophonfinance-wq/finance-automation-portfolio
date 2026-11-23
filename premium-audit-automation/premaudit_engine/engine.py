"""Orchestration: parse -> verify -> window cut -> triage -> package."""
from __future__ import annotations

from .model import AuditPackage, AuditWindow, CoverageRecord, TriagePolicy, TriagedLine
from .parse import parse_report
from .triage import triage_line


def build_package(report_text: str, company: str, window: AuditWindow,
                  policy: TriagePolicy,
                  coverage: list[CoverageRecord]) -> AuditPackage:
    parsed = parse_report(report_text, company)
    pkg = AuditPackage(company=company, window=window)
    for line in parsed.lines:
        pkg.lines.append(TriagedLine(
            line=line,
            in_window=window.contains(line.acctg_date),
            triage=triage_line(line, policy, coverage, window),
        ))
    return pkg
