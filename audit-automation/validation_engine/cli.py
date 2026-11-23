"""
Command-line interface for the validation engine.
=================================================

Usage
-----
::

    python -m validation_engine <folder> [options]

Validates every ``.xlsx`` workbook in ``<folder>`` (read-only) and prints a
summary. Optionally writes the full markdown and JSON reports to disk.

Options
-------
``--json PATH``   Write the structured JSON report to ``PATH``.
``--md PATH``     Write the markdown report to ``PATH``.
``--generate``    (Re)generate the fictional sample corpus into ``<folder>``
                  before validating.
``--quiet``       Print only the overall verdict line.

Exit codes
----------
``0`` overall PASS · ``1`` overall REVIEW (FLAGs only) · ``2`` overall FAIL ·
``3`` usage / IO error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import (
    Status,
    Verdict,
    build_json_report,
    build_markdown_report,
    overall_verdict,
    validate_folder,
)

_EXIT_BY_VERDICT = {Verdict.PASS: 0, Verdict.REVIEW: 1, Verdict.FAIL: 2}
_STATUS_TAG = {Status.PASS: "[PASS]", Status.FAIL: "[FAIL]", Status.FLAG: "[FLAG]"}


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    p = argparse.ArgumentParser(
        prog="python -m validation_engine",
        description="Read-only rules-based validation engine for .xlsx workbooks.",
    )
    p.add_argument("folder", help="folder containing .xlsx workbooks to validate")
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
    """CLI entrypoint. Returns the process exit code."""
    args = _build_parser().parse_args(argv)
    folder = Path(args.folder)

    if args.generate:
        from .generate import generate_corpus

        written = generate_corpus(folder)
        if not args.quiet:
            print(f"Generated {len(written)} fictional workbook(s) into {folder}")

    if not folder.is_dir():
        print(f"error: not a folder: {folder}", file=sys.stderr)
        return 3

    reports = validate_folder(folder)
    if not reports:
        print(f"error: no .xlsx workbooks found in {folder}", file=sys.stderr)
        return 3

    overall = overall_verdict(reports)

    if not args.quiet:
        for r in reports:
            actionable = [f for f in r.findings if f.status is not Status.PASS]
            print(f"\n=== {r.workbook} === verdict: {r.verdict.value}")
            if not actionable:
                print("  all checks passed")
            for f in actionable:
                print(f"  {_STATUS_TAG[f.status]} {f.rule} @ {f.location}: {f.message}")

    if args.json:
        import json

        Path(args.json).write_text(
            json.dumps(build_json_report(reports), indent=2), encoding="utf-8"
        )
        if not args.quiet:
            print(f"\nWrote JSON report -> {args.json}")

    if args.md:
        Path(args.md).write_text(build_markdown_report(reports), encoding="utf-8")
        if not args.quiet:
            print(f"Wrote markdown report -> {args.md}")

    print(f"\nOverall verdict: {overall.value}  ({len(reports)} workbook(s))")
    return _EXIT_BY_VERDICT[overall]


if __name__ == "__main__":
    raise SystemExit(main())
