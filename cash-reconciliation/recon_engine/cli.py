"""Command-line interface for the reconciliation engine.

Run as a module::

    python -m recon_engine                 # generate, reconcile, write outputs
    python -m recon_engine --threshold 25  # override materiality threshold
    python -m recon_engine --seed 7        # regenerate with a different seed

Or via the repo-root convenience script::

    python run.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import MATERIALITY_THRESHOLD
from .engine import reconcile
from .generate import DEFAULT_SEED, generate_dataset
from .report import render_markdown, write_xlsx

# The Markdown log is committed at the package root; the .xlsx goes to ./output
# (gitignored).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MARKDOWN_PATH = _REPO_ROOT / "evidence-log.md"
_OUTPUT_DIR = _REPO_ROOT / "output"


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="recon_engine",
        description="Cash & debt reconciliation engine (fully synthetic data).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=MATERIALITY_THRESHOLD,
        help=f"Materiality threshold in dollars (default: {MATERIALITY_THRESHOLD}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for synthetic data (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--markdown-path",
        type=Path,
        default=_MARKDOWN_PATH,
        help="Path to write the committed Markdown evidence log.",
    )
    parser.add_argument(
        "--xlsx-path",
        type=Path,
        default=_OUTPUT_DIR / "evidence-log.xlsx",
        help="Path to write the .xlsx evidence log (gitignored ./output).",
    )
    parser.add_argument(
        "--no-xlsx",
        action="store_true",
        help="Skip writing the .xlsx workbook (Markdown only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code (0 on success).

    The exit code is intentionally ``0`` even when flags are present — flags are
    an expected reconciliation outcome, not a program failure.
    """
    args = build_parser().parse_args(argv)

    dataset = generate_dataset(seed=args.seed)
    result = reconcile(dataset, threshold=args.threshold)

    markdown = render_markdown(result, dataset)
    args.markdown_path.write_text(markdown, encoding="utf-8")

    counts = result.summary_counts()

    print("Cash & Debt Reconciliation Engine")
    print(f"  Period            : {result.period} ({result.statement_date})")
    print(f"  Seed              : {args.seed}")
    print(f"  Materiality       : ${args.threshold:,.2f}")
    print(f"  Accounts in scope : {counts['accounts_total']}")
    print(
        f"    cash={counts['cash_accounts']} debt={counts['debt_accounts']} "
        f"skipped={counts['skipped']}"
    )
    print(f"  Clean             : {counts['clean']}")
    print(f"  Timing/immaterial : {counts['timing']}")
    print(f"  Flagged           : {counts['flag']}")
    print(f"  Markdown log      : {args.markdown_path}")

    if not args.no_xlsx:
        xlsx_path = write_xlsx(result, dataset, args.xlsx_path)
        print(f"  XLSX log          : {xlsx_path}")

    if result.flagged:
        print("\nFlagged for review:")
        for ln in result.flagged:
            print(
                f"  {ln.flag_id}  {ln.account_number}  {ln.entity}  "
                f"variance={ln.variance:,.2f}"
            )

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
