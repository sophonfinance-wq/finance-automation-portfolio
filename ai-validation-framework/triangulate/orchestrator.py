"""The Triangulate Orchestrator -- the centerpiece.

Wires the pluggable roles into the validation flow::

    Build (Preparer)
      -> Review (Reviewer: flag, never fix)
      -> optional Specialist (second opinion + supporting transform)
      -> automated read-only Audit
      -> reconcile findings (severity taxonomy + authority hierarchy)
      -> automated HumanGate policy -> VERDICT -> external human approval boundary
      -> write audit-trail artifacts (Builder Memo, Fix Packet, Change Log,
         QA Summary) to ./output

Separation of duties is enforced *mechanically*: before every read-only step
the orchestrator records the workpaper digest and asserts it is unchanged
afterwards. If a read-only role somehow mutated state, the run aborts with a
:class:`SeparationOfDutiesError`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

from triangulate.model import Finding, Workpaper
from triangulate.reconcile import (
    HumanGate,
    Verdict,
    reconcile,
)
from triangulate.roles.auditor import DeterministicAuditor
from triangulate.roles.base import Auditor, Preparer, Reviewer, Specialist
from triangulate.roles.preparer import DemoPreparer
from triangulate.roles.reviewer import AdversarialReviewer
from triangulate.roles.specialist import DemoSpecialist


class SeparationOfDutiesError(RuntimeError):
    """Raised if a read-only role mutated the workpaper (control breach)."""


@dataclass
class PipelineResult:
    """Everything produced by a single orchestrator run."""

    workpaper: Workpaper
    verdict: Verdict
    builder_memo: List[str]
    fix_packet: List[Finding]
    change_log: List[str]
    qa_summary: List[str]
    artifact_paths: dict = field(default_factory=dict)


class TriangulateOrchestrator:
    """Runs the 3-role validation pipeline plus audit and gate policy."""

    def __init__(
        self,
        preparer: Optional[Preparer] = None,
        reviewer: Optional[Reviewer] = None,
        specialist: Optional[Specialist] = None,
        auditor: Optional[Auditor] = None,
        human_gate: Optional[HumanGate] = None,
        use_specialist: bool = True,
    ) -> None:
        self.preparer = preparer or DemoPreparer()
        self.reviewer = reviewer or AdversarialReviewer()
        self.specialist = specialist or DemoSpecialist()
        self.auditor = auditor or DeterministicAuditor()
        self.human_gate = human_gate or HumanGate()
        self.use_specialist = use_specialist

    # -- control helper ------------------------------------------------------
    @staticmethod
    def _assert_unchanged(wp: Workpaper, digest_before: str, who: str) -> None:
        """Mechanical separation-of-duties check around read-only steps."""
        if wp.digest() != digest_before:
            raise SeparationOfDutiesError(
                f"{who} mutated the workpaper -- separation of duties violated."
            )

    # -- main flow -----------------------------------------------------------
    def run(self) -> PipelineResult:
        """Execute the full pipeline and return a :class:`PipelineResult`."""
        all_findings: List[Finding] = []
        change_log: List[str] = []
        qa_summary: List[str] = []

        # 1) BUILD ----------------------------------------------------------
        wp = self.preparer.build()
        builder_memo = self.preparer.builder_memo(wp)

        # 2) REVIEW (flag, never fix) --------------------------------------
        digest = wp.digest()
        review_findings = self.reviewer.review(wp.frozen_snapshot())
        self._assert_unchanged(wp, digest, self.reviewer.name)
        all_findings.extend(review_findings)
        qa_summary.append(
            f"Reviewer ({self.reviewer.name}) raised {len(review_findings)} "
            f"finding(s); workpaper digest unchanged (read-only confirmed)."
        )

        # 3) OPTIONAL SPECIALIST -------------------------------------------
        if self.use_specialist:
            # 3a) read-only second opinion
            digest = wp.digest()
            specialist_findings = self.specialist.second_opinion(wp.frozen_snapshot())
            self._assert_unchanged(wp, digest, f"{self.specialist.name}:second_opinion")
            all_findings.extend(specialist_findings)
            qa_summary.append(
                f"Specialist ({self.specialist.name}) second opinion raised "
                f"{len(specialist_findings)} finding(s); read-only confirmed."
            )
            # 3b) explicit supporting transform (allowed to mutate)
            change_log = self.specialist.apply_transform(wp)
            qa_summary.append(
                f"Specialist transform applied {len(change_log)} change(s) "
                "(explicitly authorised mutation)."
            )
        else:
            change_log = ["Specialist step skipped (use_specialist=False)."]

        # 4) AUTOMATED READ-ONLY AUDIT -------------------------------------
        digest = wp.digest()
        audit_findings = self.auditor.audit(wp.frozen_snapshot())
        self._assert_unchanged(wp, digest, self.auditor.name)
        all_findings.extend(audit_findings)
        qa_summary.append(
            f"Automated audit ({self.auditor.name}) raised "
            f"{len(audit_findings)} finding(s); read-only confirmed."
        )

        # 5) RECONCILE (severity taxonomy + authority hierarchy) -----------
        ranked = reconcile(all_findings)
        qa_summary.append(
            f"Reconciled {len(all_findings)} raw finding(s) into "
            f"{len(ranked)} ranked, de-duplicated finding(s)."
        )

        # 6) HUMAN GATE -> VERDICT -----------------------------------------
        verdict = self.human_gate.decide(ranked)
        qa_summary.append(
            f"HumanGate verdict: {verdict.status.value} -- {verdict.rationale}"
        )

        # The Fix Packet is the actionable subset (Critical/High) for the Preparer.
        fix_packet = [f for f in ranked if f.severity.name in {"CRITICAL", "HIGH"}]

        return PipelineResult(
            workpaper=wp,
            verdict=verdict,
            builder_memo=builder_memo,
            fix_packet=fix_packet,
            change_log=change_log,
            qa_summary=qa_summary,
        )

    # -- artifact emission ---------------------------------------------------
    def write_artifacts(self, result: PipelineResult, output_dir: str) -> dict:
        """Write the four audit-trail artifacts + verdict JSON to ``output_dir``.

        Returns a mapping of artifact name -> absolute path.
        """
        os.makedirs(output_dir, exist_ok=True)
        wp = result.workpaper
        header = (
            f"Engagement {wp.engagement} | {wp.entity} | {wp.period}\n"
            f"{'=' * 60}\n"
        )
        paths: dict = {}

        def _write(name: str, title: str, lines: List[str]) -> None:
            path = os.path.abspath(os.path.join(output_dir, name))
            body = header + f"{title}\n{'-' * 60}\n"
            body += "\n".join(f"- {line}" for line in lines) + "\n"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            paths[title] = path

        _write("builder_memo.txt", "Builder Memo", result.builder_memo)
        _write(
            "fix_packet.txt",
            "Fix Packet",
            [
                f"[{f.severity.label}] {f.cell_ref} {f.code}: {f.message} "
                f"(authority: {f.authority.label}; by {f.raised_by})"
                for f in result.fix_packet
            ] or ["No Critical/High items -- nothing to fix."],
        )
        _write("change_log.txt", "Change Log", result.change_log)
        _write("qa_summary.txt", "QA Summary", result.qa_summary)

        # Machine-readable verdict.
        verdict_path = os.path.abspath(os.path.join(output_dir, "verdict.json"))
        with open(verdict_path, "w", encoding="utf-8") as handle:
            json.dump(result.verdict.to_dict(), handle, indent=2, default=str)
        paths["Verdict (JSON)"] = verdict_path

        result.artifact_paths = paths
        return paths
