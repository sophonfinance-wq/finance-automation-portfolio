"""
Command-line interface for the workpaper review & handback engine.
==================================================================

Usage
-----
::

    python -m workpaper_engine <folder> [options]

Analyzes every ``.json`` package file in ``<folder>`` (read-only) and prints the
exceptions.

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
``1`` overall FLAG - human review required, no hard failure.
``2`` overall FAIL - at least one hard control failure.
``3`` usage / IO error.
"""

from __future__ import annotations

import argparse
import os
import sys

from .engine import EXIT_CODES, analyze_folder
from .generate import generate_corpus
from .report import build_json_report, build_markdown_report

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workpaper_engine",
        description="Read-only traceability controls for a tax workpaper handback.",
    )
    parser.add_argument("folder", help="folder of .json package files")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--md", dest="md_path", default=None)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.generate:
            generate_corpus(args.folder)
        if not os.path.isdir(args.folder):
            print("not a folder: %s" % args.folder, file=sys.stderr)
            return 3
        result = analyze_folder(args.folder)
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 3

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(build_json_report(result))
    if args.md_path:
        with open(args.md_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(build_markdown_report(result))

    if not args.quiet:
        for p in result["packages"]:
            for f in p["findings"]:
                print("%-6s %-24s %-28s %s"
                      % (f["severity"], f["control"], f["address"], f["message"]))
    print("verdict: %s" % result["verdict"])
    return EXIT_CODES[result["verdict"]]
