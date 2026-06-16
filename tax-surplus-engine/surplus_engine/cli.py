"""Command-line entrypoint for the tax-surplus engine.

Run the full fictional structure across a range of fiscal years, emitting
per-entity Markdown workpapers, a consolidated summary, and (optionally) an
Excel workbook.

Examples
--------
    python -m surplus_engine --start 2021 --end 2024
    python -m surplus_engine --start 2020 --end 2025 --out out --xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .engine import EXEMPT_CAP, SurplusEngine
from .generate import DEFAULT_SEED, generate_structure
from .report import attach_fx, consolidated_summary, entity_workpaper


def _safe_print(text: str) -> None:
    """Print ``text`` even on consoles whose encoding can't render every char.

    Windows consoles often default to cp1252, which cannot encode emoji used in
    the confidentiality banners. Re-encode via the stream's encoding with a
    replacement fallback rather than crashing the CLI.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        enc = (sys.stdout.encoding or "utf-8")
        sys.stdout.write(text.encode(enc, errors="replace").decode(enc) + "\n")


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="surplus_engine",
        description="Canadian foreign-affiliate surplus-pool / ACB model (fictional data).",
    )
    p.add_argument("--start", type=int, default=2021, help="first fiscal year (inclusive)")
    p.add_argument("--end", type=int, default=2024, help="last fiscal year (inclusive)")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed (reproducibility)")
    p.add_argument(
        "--exempt-cap",
        type=float,
        default=EXEMPT_CAP,
        help="exempt-distribution cap fraction (0..1)",
    )
    p.add_argument(
        "--out",
        type=str,
        default=None,
        help="directory to write workpapers/summary (default: print summary to stdout only)",
    )
    p.add_argument("--xlsx", action="store_true", help="also write an Excel workbook")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main. Returns a process exit code."""
    args = _parse_args(argv)
    if args.end < args.start:
        print("error: --end must be >= --start", file=sys.stderr)
        return 2
    if not 0.0 <= args.exempt_cap <= 1.0:
        print("error: --exempt-cap must be in [0,1]", file=sys.stderr)
        return 2

    years = list(range(args.start, args.end + 1))
    structure = generate_structure(args.start, args.end, seed=args.seed)
    engine = SurplusEngine(structure, exempt_cap_fraction=args.exempt_cap)
    results = engine.run(years)
    attach_fx(results, structure)

    summary = consolidated_summary(results, structure)

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        # Per-entity workpapers.
        for code in structure.entities:
            wp = entity_workpaper(code, results, structure)
            (out_dir / f"workpaper_{code}.md").write_text(wp, encoding="utf-8")
        # Consolidated summary.
        (out_dir / "consolidated_summary.md").write_text(summary, encoding="utf-8")
        # Optional workbook.
        if args.xlsx:
            from .workbook import build_workbook

            wb = build_workbook(results, structure)
            wb.save(out_dir / "surplus_model.xlsx")

        _safe_print(f"Wrote {len(structure.entities)} workpapers + summary to {out_dir.resolve()}")
        if args.xlsx:
            _safe_print(f"Wrote workbook: {(out_dir / 'surplus_model.xlsx').resolve()}")

    # Always echo the consolidated summary to stdout so the CLI is useful bare.
    _safe_print("")
    _safe_print(summary)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
