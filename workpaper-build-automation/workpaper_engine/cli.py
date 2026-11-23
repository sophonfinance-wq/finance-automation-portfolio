"""
Command-line interface for the tax workpaper build engine.
==========================================================

Usage
-----
::

    python -m workpaper_engine <folder> [options]

The engine builds workpaper packages and then proves what it built, and the CLI
does both. ``--build DIR`` runs the construction pipeline over each file's own
inputs -- the locked extract, the prior-year package, the allocation register
and the exception register -- and writes the **constructed package** plus its
**build register** into ``DIR``. With no ``--build``, every ``.json`` build file
in ``<folder>`` is analyzed (read-only) and the exceptions printed.

Options
-------
``--build DIR``   Rebuild each file's package from its inputs and write the
                  constructed package (``<file_id>.package.json``) and its build
                  register (``<file_id>.register.md``) into ``DIR``.
``--json PATH``   Write the structured JSON control report to ``PATH``.
``--md PATH``     Write the markdown control report to ``PATH``.
``--generate``    (Re)generate the fictional sample corpus into ``<folder>``
                  before building or analyzing.
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
import json
import sys
from pathlib import Path

from .build import build_package
from .engine import analyze_folder, overall_verdict
from .model import (
    DOC_ALLOCATION_REGISTER,
    DOC_COUNTERPART_STUB,
    DOC_EXCEPTION_REGISTER,
    DOC_LOCKED_SOURCE,
    DOC_PREBUILD_IMAGE,
    DOC_PRIOR_PACKAGE,
    Status,
    Verdict,
)
from .report import build_register_markdown, write_reports

_EXIT_BY_VERDICT = {Verdict.PASS: 0, Verdict.REVIEW: 1, Verdict.FAIL: 2}
_STATUS_TAG = {Status.PASS: "[PASS]", Status.FAIL: "[FAIL]", Status.FLAG: "[FLAG]"}


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    p = argparse.ArgumentParser(
        prog="python -m workpaper_engine",
        description=(
            "Builder and control engine for the annual tax workpaper package: it "
            "constructs a new fiscal year's trial balance, balance sheet, statement "
            "of operations, members' equity schedule, member capital accounts, "
            "earnings-and-profits roll-forward and evidence tab from a locked "
            "general-ledger extract, the prior-year package, an allocation register "
            "and a known-exception register -- freezing every prior-year layer, "
            "advancing every rolling caption by one year, deriving each current-year "
            "flow as the source-less-prior movement of its account, and emitting a "
            "build register naming every constructed cell. Twenty-four controls then "
            "prove the built package against the inputs it came from. Operates on "
            "seeded, fictional files."
        ),
    )
    p.add_argument("folder", help="folder containing .json build files")
    p.add_argument(
        "--build",
        metavar="DIR",
        help="rebuild each package from its inputs and write it, with its build "
             "register, into DIR",
    )
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


def _documents(payload: dict) -> dict[str, dict]:
    """Index a build file's documents by type, first occurrence winning."""
    out: dict[str, dict] = {}
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and isinstance(doc.get("doc_type"), str):
            out.setdefault(doc["doc_type"], doc)
    return out


def emit_builds(folder: Path, out_dir: Path) -> list[Path]:
    """Rebuild every package in ``folder`` and write the products into ``out_dir``.

    The package is constructed from the file's own inputs rather than copied out
    of it, so what lands in ``out_dir`` is the pipeline's output and not a
    re-serialisation of whatever the file happened to carry.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        docs = _documents(payload)
        source = docs.get(DOC_LOCKED_SOURCE)
        prior = docs.get(DOC_PRIOR_PACKAGE)
        if source is None or prior is None:
            continue
        package = build_package(
            source,
            prior,
            {
                "allocation": docs.get(DOC_ALLOCATION_REGISTER),
                "exception": docs.get(DOC_EXCEPTION_REGISTER),
                "counterpart_stub": docs.get(DOC_COUNTERPART_STUB),
                "prebuild_image": docs.get(DOC_PREBUILD_IMAGE),
            },
        )
        stem = str(payload.get("file_id", path.stem))
        package_path = out_dir / f"{stem}.package.json"
        package_path.write_text(
            json.dumps(package.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        register_path = out_dir / f"{stem}.register.md"
        register_path.write_text(build_register_markdown(package), encoding="utf-8")
        written += [package_path, register_path]
    return written


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
            print(f"Generated {len(written)} fictional build file(s) into {folder}")

    if not folder.is_dir():
        print(f"error: not a folder: {folder}", file=sys.stderr)
        return 3

    if args.build:
        try:
            products = emit_builds(folder, Path(args.build))
        except (OSError, ValueError, KeyError) as exc:
            print(f"error: could not build packages from {folder}: {exc}", file=sys.stderr)
            return 3
        if not products:
            print(f"error: no build inputs found in {folder}", file=sys.stderr)
            return 3
        if not args.quiet:
            packages = len([p for p in products if p.name.endswith(".package.json")])
            print(
                f"Built {packages} workpaper package(s) with build register(s) "
                f"into {Path(args.build)}"
            )

    try:
        reports = analyze_folder(folder)
    except (OSError, ValueError) as exc:
        print(f"error: could not read build files in {folder}: {exc}", file=sys.stderr)
        return 3

    if not reports:
        print(f"error: no .json build files found in {folder}", file=sys.stderr)
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

    print(f"\nOverall verdict: {overall.value}  ({len(reports)} build file(s))")
    return _EXIT_BY_VERDICT[overall]


if __name__ == "__main__":
    raise SystemExit(main())
