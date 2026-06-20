"""Command-line entrypoint for the Triangulate Orchestrator.

Run the pipeline over a bundled synthetic workpaper and print the verdict plus
the audit-trail artifacts.

Examples::

    python -m triangulate                     # defective sample (default)
    python -m triangulate --sample clean      # clean sample passes
    python -m triangulate --demo-adversarial  # inject one hallucination; watch it get caught
    python -m triangulate --no-specialist     # skip the specialist step
    python -m triangulate --output ./output   # where artifacts are written
    python -m triangulate --xlsx              # also emit a .xlsx workpaper
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from triangulate.generate import write_xlsx
from triangulate.orchestrator import PipelineResult, TriangulateOrchestrator
from triangulate.reconcile import VerdictStatus
from triangulate.roles.preparer import AdversarialPreparer, DemoPreparer

_RULE = "=" * 64


def _print_section(title: str, lines: List[str]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for line in lines:
        print(f"  {line}")


def _verdict_banner(status: VerdictStatus) -> str:
    icon = {
        VerdictStatus.PASS: "PASS  [signed off]",
        VerdictStatus.FLAG: "FLAG  [returned to Preparer]",
        VerdictStatus.FAIL: "FAIL  [cannot sign off]",
    }[status]
    return f"VERDICT: {icon}"


def render(result: PipelineResult) -> None:
    """Pretty-print a :class:`PipelineResult` to stdout."""
    wp = result.workpaper
    print(_RULE)
    print("TRIANGULATE ORCHESTRATOR -- AI VALIDATION PIPELINE")
    print(_RULE)
    print(f"Engagement : {wp.engagement}")
    print(f"Entity     : {wp.entity}  (all data fictional)")
    print(f"Period     : {wp.period}")

    verdict = result.verdict
    print(f"\n{_verdict_banner(verdict.status)}")
    print(f"  Rationale     : {verdict.rationale}")
    print(f"  Signed off by : {verdict.signed_off_by}")
    counts = verdict.severity_counts
    print(
        "  Severity      : "
        f"Critical={counts['Critical']} High={counts['High']} "
        f"Medium={counts['Medium']} Low={counts['Low']}"
    )

    _print_section("Builder Memo", result.builder_memo)

    _print_section(
        "Fix Packet (Critical/High -> back to Preparer)",
        [
            f"[{f.severity.label}] {f.cell_ref} {f.code}: {f.message}"
            for f in result.fix_packet
        ] or ["No Critical/High items."],
    )

    _print_section(
        "Reconciled Findings (ranked)",
        [
            f"[{f.severity.label}] {f.cell_ref} {f.code} "
            f"(authority: {f.authority.label}; by {f.raised_by})"
            for f in verdict.findings
        ] or ["No findings."],
    )

    _print_section("Change Log", result.change_log)
    _print_section("QA Summary", result.qa_summary)

    if result.artifact_paths:
        _print_section(
            "Artifacts written",
            [f"{name}: {path}" for name, path in result.artifact_paths.items()],
        )
    print(f"\n{_RULE}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="triangulate",
        description="Run the Triangulate AI validation pipeline over a sample workpaper.",
    )
    parser.add_argument(
        "--sample",
        choices=("clean", "defective"),
        default="defective",
        help="Which bundled synthetic workpaper to run (default: defective).",
    )
    parser.add_argument(
        "--demo-adversarial",
        action="store_true",
        help="Inject one hallucinated figure into a clean workpaper and watch the "
             "pipeline catch it (CRITICAL tie-out break -> FAIL). Overrides --sample.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20240101,
        help="Random seed for deterministic synthetic data (default: 20240101).",
    )
    parser.add_argument(
        "--no-specialist",
        action="store_true",
        help="Skip the optional Specialist step.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(os.getcwd(), "output"),
        help="Directory for audit-trail artifacts (default: ./output).",
    )
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="Do not write artifact files (print only).",
    )
    parser.add_argument(
        "--xlsx",
        action="store_true",
        help="Also write the workpaper as a .xlsx file in the output directory.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint. Returns a process exit code.

    Exit code 0 on PASS, 1 on FLAG/FAIL -- so the pipeline is usable in CI as a
    gate. (The bundled defective sample therefore exits 1 *by design*.)
    """
    args = build_parser().parse_args(argv)

    preparer = (
        AdversarialPreparer(seed=args.seed)
        if args.demo_adversarial
        else DemoPreparer(kind=args.sample, seed=args.seed)
    )
    orchestrator = TriangulateOrchestrator(
        preparer=preparer,
        use_specialist=not args.no_specialist,
    )
    result = orchestrator.run()

    if not args.no_artifacts:
        orchestrator.write_artifacts(result, args.output)
        if args.xlsx:
            xlsx_path = os.path.abspath(os.path.join(args.output, "workpaper.xlsx"))
            write_xlsx(result.workpaper, xlsx_path)
            result.artifact_paths["Workpaper (XLSX)"] = xlsx_path

    render(result)

    return 0 if result.verdict.status is VerdictStatus.PASS else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
