"""Typed findings for the Close Sentinel.

A control never mutates the close; it only reports findings. Severity is a
three-level scale: CRITICAL blocks the close, WARN needs a reviewer's eye,
and INFO is a corroborated note kept for the audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """How serious a control finding is."""

    CRITICAL = "critical"
    WARN = "warn"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    """One control finding.

    Attributes:
        control_id: The control that raised it (e.g. ``"C4"``).
        severity: CRITICAL blocks the close; WARN and INFO do not.
        entity: Entity code the finding concerns, or None if group-wide.
        subject: Short, stable statement of the defect.
        detail: Full explanation carrying the numbers that prove it.
    """

    control_id: str
    severity: Severity
    entity: str | None
    subject: str
    detail: str


@dataclass
class SentinelReport:
    """The aggregated outcome of one sentinel run.

    Findings are kept in control order (C1 first). The close is considered
    clean only when no control raised a CRITICAL finding.
    """

    findings: list[Finding] = field(default_factory=list)

    @property
    def criticals(self) -> list[Finding]:
        """All CRITICAL findings, in control order."""
        return [f for f in self.findings if f.severity is Severity.CRITICAL]

    @property
    def warnings(self) -> list[Finding]:
        """All WARN findings, in control order."""
        return [f for f in self.findings if f.severity is Severity.WARN]

    @property
    def infos(self) -> list[Finding]:
        """All INFO findings, in control order."""
        return [f for f in self.findings if f.severity is Severity.INFO]

    @property
    def clean(self) -> bool:
        """True iff no control raised a CRITICAL finding."""
        return not self.criticals

    @property
    def by_control(self) -> dict[str, list[Finding]]:
        """Findings grouped by control id, preserving control order."""
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.control_id, []).append(finding)
        return grouped

    def summary_line(self) -> str:
        """One plain-ASCII line summarizing the run for reports and the CLI."""
        if not self.findings:
            return "Sentinel: all controls passed (no findings)."
        verdict = "CLEAN" if self.clean else "NOT CLEAN"
        return (
            f"Sentinel: {verdict} - {len(self.criticals)} critical, "
            f"{len(self.warnings)} warning, {len(self.infos)} info."
        )
