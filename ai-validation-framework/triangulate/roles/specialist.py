"""The Specialist role -- supporting transforms and a read-only second opinion."""

from __future__ import annotations

from typing import List

from triangulate.model import (
    AuthoritySource,
    Finding,
    ReadOnlyWorkpaperView,
    Severity,
    Workpaper,
)
from triangulate.roles.base import Specialist


class DemoSpecialist(Specialist):
    """A supporting specialist (OCR/normalisation stand-in + second opinion).

    Its *transform* capability normalises rounding so downstream tie-outs are
    not tripped by float noise -- a legitimate supporting transform invoked
    explicitly by the orchestrator. Its *review* capability is read-only: it
    contributes a second opinion as findings, mirroring the framework's
    "specialist supports, never owns the deliverable" rule.
    """

    name = "Specialist:DemoSpecialist"

    def second_opinion(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        """Read-only supporting review: flag rate cells outside a sane band."""
        findings: List[Finding] = []
        for cell in view.ordered_cells():
            # A "rate" cell is a small fractional value; flag implausible ones.
            if (
                cell.value is not None
                and isinstance(cell.value, (int, float))
                and 0 < cell.value < 1
                and "rate" in cell.label.lower()
            ):
                if not (0.10 <= cell.value <= 0.35):
                    findings.append(Finding(
                        code="RATE_OUT_OF_BAND",
                        cell_ref=cell.ref,
                        severity=Severity.MEDIUM,
                        message=(
                            f"Rate {cell.value} in '{cell.label}' is outside the "
                            f"expected 10%-35% band; confirm against source."
                        ),
                        raised_by=self.name,
                        authority=AuthoritySource.CURRENT_YEAR_SOURCE,
                    ))
        return findings

    def apply_transform(self, wp: Workpaper) -> List[str]:
        """Normalise numeric precision in place; return a change log."""
        change_log: List[str] = []
        for cell in wp.ordered_cells():
            if isinstance(cell.value, float):
                normalised = round(cell.value, 2)
                if normalised != cell.value:
                    change_log.append(
                        f"{cell.ref}: normalised value {cell.value} -> {normalised}"
                    )
                    cell.value = normalised
        if not change_log:
            change_log.append("No normalisation required; values already clean.")
        return change_log
