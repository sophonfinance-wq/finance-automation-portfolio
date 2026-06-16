"""Finding reconciliation and the final VERDICT / HumanGate.

The reconciler takes every finding raised across the pipeline (Reviewer,
Specialist, Audit), de-duplicates and ranks them using the severity taxonomy
and the source-of-truth authority hierarchy, and produces a structured
:class:`Verdict`. The :class:`HumanGate` then applies a policy to decide
PASS vs. FLAG vs. FAIL and records the final sign-off.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List

from triangulate.model import Finding, Severity


class VerdictStatus(enum.Enum):
    """Final pipeline outcome."""

    PASS = "PASS"
    FLAG = "FLAG"
    FAIL = "FAIL"


@dataclass
class Verdict:
    """The reconciled outcome of a pipeline run."""

    status: VerdictStatus
    findings: List[Finding]
    severity_counts: Dict[str, int]
    max_severity: Severity | None
    rationale: str
    signed_off_by: str = "HumanGate(automated-policy)"
    notes: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status is VerdictStatus.PASS

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status.value,
            "max_severity": self.max_severity.label if self.max_severity else None,
            "severity_counts": self.severity_counts,
            "rationale": self.rationale,
            "signed_off_by": self.signed_off_by,
            "findings": [f.to_dict() for f in self.findings],
            "notes": list(self.notes),
        }


def reconcile(findings: List[Finding]) -> List[Finding]:
    """De-duplicate and rank findings.

    De-duplication key is ``(code, cell_ref)``. When two findings collide, the
    one backed by the **higher authority source** wins; ties break on higher
    severity. The result is sorted most-severe-first, then by authority, then by
    cell reference for stable, deterministic output.
    """
    best: Dict[tuple, Finding] = {}
    for finding in findings:
        key = (finding.code, finding.cell_ref)
        incumbent = best.get(key)
        if incumbent is None:
            best[key] = finding
            continue
        # Higher authority wins; then higher severity.
        if (finding.authority, finding.severity) > (
            incumbent.authority,
            incumbent.severity,
        ):
            best[key] = finding

    ranked = sorted(
        best.values(),
        key=lambda f: (-int(f.severity), -int(f.authority), f.cell_ref),
    )
    return ranked


def severity_breakdown(findings: List[Finding]) -> Dict[str, int]:
    """Count findings by severity label, always including all four buckets."""
    counts = {sev.label: 0 for sev in (
        Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW
    )}
    for finding in findings:
        counts[finding.severity.label] += 1
    return counts


class HumanGate:
    """Final sign-off policy.

    Encodes the human gate as an explicit, auditable policy so the demo runs
    end-to-end without a person in the loop, while still modelling where the
    human decision sits:

    * any **Critical** finding  -> ``FAIL`` (cannot sign off)
    * any **High** finding      -> ``FLAG`` (return to Preparer)
    * only Medium/Low (or none) -> ``PASS`` with documented residual notes

    In production this policy would surface the reconciled packet to a senior
    reviewer who retains final responsibility; here the policy *is* the gate.
    """

    def __init__(self, signer: str = "HumanGate(automated-policy)") -> None:
        self.signer = signer

    def decide(self, ranked_findings: List[Finding]) -> Verdict:
        counts = severity_breakdown(ranked_findings)
        max_sev = max((f.severity for f in ranked_findings), default=None)

        if counts[Severity.CRITICAL.label] > 0:
            status = VerdictStatus.FAIL
            rationale = (
                f"{counts[Severity.CRITICAL.label]} Critical finding(s) present; "
                "deliverable cannot be signed off and is returned for rebuild."
            )
        elif counts[Severity.HIGH.label] > 0:
            status = VerdictStatus.FLAG
            rationale = (
                f"{counts[Severity.HIGH.label]} High finding(s) present; "
                "deliverable is flagged for Preparer remediation before sign-off."
            )
        else:
            status = VerdictStatus.PASS
            residual = counts[Severity.MEDIUM.label] + counts[Severity.LOW.label]
            rationale = (
                "No Critical or High findings. "
                + (
                    f"{residual} residual Medium/Low item(s) documented; "
                    "human accepts and signs off."
                    if residual
                    else "Clean run; human signs off."
                )
            )

        notes: List[str] = []
        if status is not VerdictStatus.PASS:
            notes.append(
                "Per authority hierarchy, AI-generated assumptions are lowest "
                "authority and must be replaced with a cited source before re-run."
            )

        return Verdict(
            status=status,
            findings=ranked_findings,
            severity_counts=counts,
            max_severity=max_sev,
            rationale=rationale,
            signed_off_by=self.signer,
            notes=notes,
        )
