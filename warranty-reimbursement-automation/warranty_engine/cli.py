"""
Command-line interface for the warranty reimbursement engine.
===================================================

Usage
-----
::

    python -m warranty_engine <folder> [options]

Analyzes every ``.json`` claim file in ``<folder>`` (read-only) and prints the
exceptions. Optionally writes the full markdown and JSON reports.

Options
-------
``--json PATH``   Write the structured JSON report to ``PATH``.
``--md PATH``     Write the markdown report to ``PATH``.
``--generate``    (Re)generate the fictional sample corpus into ``<folder>``
                  before analyzing.
``--quiet``       Print only the overall verdict line.

Exit codes
----------
``0`` overall PASS - every control held.
``1`` overall REVIEW - FLAGs only, human review required.
``2`` overall FAIL - at least one hard control failure.
``3`` usage / IO error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import analyze_folder, overall_verdict
from .model import Status, Verdict
from .report import write_reports

_EXIT_BY_VERDICT = {Verdict.PASS: 0, Verdict.REVIEW: 1, Verdict.FAIL: 2}
_STATUS_TAG = {Status.PASS: "[PASS]", Status.FAIL: "[FAIL]", Status.FLAG: "[FLAG]"}


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    p = argparse.ArgumentParser(
        prog="python -m warranty_engine",
        description=(
            "Read-only control engine for warranty reimbursement claims. "
            "Analyzes seeded, fictional claim files."
        ),
    )
    p.add_argument("folder", help="folder containing .json claim files")
    p.add_argument("--json", metavar="PATH", help="write the JSON report to PATH")
    p.add_argument("--md", metavar="PATH", help="write the markdown report to PATH")
    p.add_argument(
        "--generate",
        action="store_true",
        help="regenerate the fictional sample corpus into <folder> first",
    )
    p.add_argument(
        "--quiet", action="store_true", help="print only the overall verdict"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the process exit code; never calls ``sys.exit``."""
    args = _build_parser().parse_args(argv)
    folder = Path(args.folder)

    if args.generate:
        from .generate import generate_corpus

        try:
            written = generate_corpus(folder)
        except OSError as exc:
            print(f"error: could not generate corpus into {folder}: {exc}", file=sys.stderr)
            return 3
        if not args.quiet:
            print(f"Generated {len(written)} fictional claim file(s) into {folder}")

    if not folder.is_dir():
        print(f"error: not a folder: {folder}", file=sys.stderr)
        return 3

    try:
        reports = analyze_folder(folder)
    except (OSError, ValueError) as exc:
        print(f"error: could not read claim files in {folder}: {exc}", file=sys.stderr)
        return 3

    if not reports:
        print(f"error: no .json claim files found in {folder}", file=sys.stderr)
        return 3

    overall = overall_verdict(reports)

    if not args.quiet:
        for report in reports:
            actionable = [f for f in report.findings if f.status is not Status.PASS]
            print(f"\n=== {report.document} === verdict: {report.verdict.value}")
            if not actionable:
                print("  all controls held")
            for finding in actionable:
                print(
                    f"  {_STATUS_TAG[finding.status]} {finding.rule} @ "
                    f"{finding.location}: {finding.message}"
                )

    written_paths = write_reports(reports, json_path=args.json, md_path=args.md)
    if not args.quiet:
        for path in written_paths:
            label = "JSON" if path.suffix == ".json" else "markdown"
            print(f"\nWrote {label} report -> {path}")

    print(f"\nOverall verdict: {overall.value}  ({len(reports)} claim file(s))")
    return _EXIT_BY_VERDICT[overall]


if __name__ == "__main__":
    raise SystemExit(main())
