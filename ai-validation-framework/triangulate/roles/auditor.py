"""The deterministic, read-only automated Audit step.

A script cannot hallucinate "yes." This auditor re-derives every formula cell
mechanically and confirms structural integrity. It is the machine backstop the
framework relies on between AI review and human sign-off.
"""

from __future__ import annotations

from typing import List

from triangulate.formula import FormulaError, evaluate
from triangulate.model import (
    AuthoritySource,
    Finding,
    ReadOnlyWorkpaperView,
    Severity,
)
from triangulate.roles.base import Auditor

# Required structural cells the audit expects in a well-formed workpaper.
_REQUIRED_REFS = ("B5", "B7", "B8")


class DeterministicAuditor(Auditor):
    """Mechanical, reproducible cell-by-cell audit.

    Checks performed:

    * **Tie-outs** -- every cell with a formula must equal its re-derived value.
    * **Structural completeness** -- required summary cells must be present.
    * **Self-reference / unresolvable formulas** -- caught and flagged.

    The auditor receives a :class:`~triangulate.model.ReadOnlyWorkpaperView`,
    so it physically cannot modify anything.
    """

    name = "Audit:DeterministicAuditor"

    def audit(self, view: ReadOnlyWorkpaperView) -> List[Finding]:
        findings: List[Finding] = []
        values = {
            c.ref: c.value
            for c in view.ordered_cells()
            if c.value is not None
        }

        # Structural completeness.
        present = {c.ref for c in view.ordered_cells()}
        for ref in _REQUIRED_REFS:
            if ref not in present:
                findings.append(Finding(
                    code="MISSING_REQUIRED_CELL",
                    cell_ref=ref,
                    severity=Severity.HIGH,
                    message=f"Required summary cell {ref} is missing from the workpaper.",
                    raised_by=self.name,
                    authority=AuthoritySource.WORKBOOK_FORMULA,
                ))

        # Tie-out re-derivation.
        for cell in view.ordered_cells():
            if not cell.formula:
                continue
            try:
                expected = round(evaluate(cell.formula, values), 2)
            except FormulaError as exc:
                findings.append(Finding(
                    code="AUDIT_FORMULA_ERROR",
                    cell_ref=cell.ref,
                    severity=Severity.HIGH,
                    message=f"Audit could not evaluate {cell.formula!r}: {exc}",
                    raised_by=self.name,
                    authority=AuthoritySource.WORKBOOK_FORMULA,
                ))
                continue
            actual = round(float(cell.value), 2) if cell.value is not None else None
            if actual is None or abs(expected - actual) > 0.01:
                findings.append(Finding(
                    code="AUDIT_TIE_OUT_FAIL",
                    cell_ref=cell.ref,
                    severity=Severity.CRITICAL,
                    message=(
                        f"Audit tie-out failed: {cell.ref} stated {actual} but "
                        f"{cell.formula} re-derives to {expected}."
                    ),
                    raised_by=self.name,
                    authority=AuthoritySource.WORKBOOK_FORMULA,
                    expected=expected,
                    actual=actual,
                ))

        return findings
