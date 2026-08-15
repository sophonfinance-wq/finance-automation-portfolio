"""CLI: generate a fictional print report, build the package, emit artifacts."""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

from .engine import build_package
from .generate import generate_report
from .model import AuditWindow, ParseRefusal, TriagePolicy
from .report import package_json, package_markdown


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="premaudit",
                                 description="Premium-audit response engine (fictional data)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--window-start", default="2025-10-15")
    ap.add_argument("--window-end", default="2026-06-01")
    ap.add_argument("--out", default="out")
    args = ap.parse_args(argv)

    gen = generate_report(args.seed, jobs=args.jobs)
    window = AuditWindow(dt.date.fromisoformat(args.window_start),
                         dt.date.fromisoformat(args.window_end))
    try:
        pkg = build_package(gen.text, gen.company, window, TriagePolicy(),
                            gen.coverage)
    except ParseRefusal as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"package_seed{args.seed}.json").write_text(package_json(pkg), encoding="utf-8")
    (out / f"package_seed{args.seed}.md").write_text(package_markdown(pkg), encoding="utf-8")
    print(f"package built: {len(pkg.lines)} lines, window "
          f"{pkg.window_total_cents} cents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
