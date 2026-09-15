"""Command-line entrypoint for the partnership-tax (§704(c)) engine.

Build the fictional partnership, roll it forward, and emit the per-partner
Schedule K-1 capital analyses and the Form 1065 summary as Markdown.

Examples
--------
    python -m partnership_engine
    python -m partnership_engine --years 6 --out out
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .generate import DEFAULT_SEED, DEFAULT_YEARS, generate_partnership
from .report import build_reports


def _safe_print(text: str) -> None:
    """Print ``text`` even on consoles whose encoding can't render every char.

    Windows consoles often default to cp1252, which cannot encode the emoji used
    in the confidentiality banners. Re-encode via the stream's encoding with a
    replacement fallback rather than crashing the CLI.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(text.encode(enc, errors="replace").decode(enc) + "\n")


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="partnership_engine",
        description=(
            "US partnership-tax (Form 1065) model with IRC §704(c) built-in "
            "gain/loss tracking — traditional method with the ceiling rule "
            "(fictional data)."
        ),
    )
    p.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help="number of fiscal years to roll forward after formation",
    )
    p.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="RNG seed (reproducibility)"
    )
    p.add_argument(
        "--out",
        type=str,
        default=None,
        help="directory to write K-1s + summary (default: print summary to stdout only)",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main. Returns a process exit code."""
    args = _parse_args(argv)
    if args.years < 1:
        print("error: --years must be >= 1", file=sys.stderr)
        return 2

    partnership = generate_partnership(n_years=args.years, seed=args.seed)
    artifacts = build_reports(partnership)
    summary = artifacts["partnership_1065_summary.md"]

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in artifacts.items():
            (out_dir / filename).write_text(content, encoding="utf-8")
        n_k1 = sum(1 for k in artifacts if k.startswith("k1_"))
        _safe_print(
            f"Wrote {n_k1} K-1 capital analyses + 1065 summary to {out_dir.resolve()}"
        )

    # Always echo the partnership summary so the CLI is useful bare.
    _safe_print("")
    _safe_print(summary)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
