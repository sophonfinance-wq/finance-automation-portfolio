"""Command-line interface for the close engine.

Run a full month-end close for a given period::

    python -m close_engine --period 2026-03 --out ./output

The CLI generates the seeded fictional dataset, runs the engine, writes the
committed outputs, and prints a concise tie-out summary. It exits non-zero if
the close is not clean (any out-of-tie entry, failed schedule tie, or
unbalanced trial balance), so it can gate an automated pipeline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, money
from .engine import CloseEngine, CloseResult
from .generate import generate_dataset
from .report import write_outputs


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="close_engine",
        description="Run a deterministic, tie-checked month-end close.",
    )
    parser.add_argument(
        "--period",
        default="2026-03",
        help="Close period as YYYY-MM (default: 2026-03).",
    )
    parser.add_argument(
        "--out",
        default="./output",
        help="Output directory for the JE register, TB, and report.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Random seed for the synthetic data (default: 2026).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _validate_period(period: str) -> None:
    """Validate the YYYY-MM period format.

    Raises:
        SystemExit: With a clear message if the format is invalid.
    """
    parts = period.split("-")
    ok = (
        len(parts) == 2
        and len(parts[0]) == 4
        and parts[0].isdigit()
        and parts[1].isdigit()
        and 1 <= int(parts[1]) <= 12
    )
    if not ok:
        raise SystemExit(f"error: --period must be YYYY-MM, got {period!r}")


def run_close(period: str, out_dir: str, seed: int) -> CloseResult:
    """Generate data, run the engine, and write outputs for ``period``."""
    dataset = generate_dataset(period, seed=seed)
    result = CloseEngine(dataset).run()
    write_outputs(result, out_dir)
    return result


def _print_summary(result: CloseResult, out_dir: str) -> None:
    """Print a human-readable close summary to stdout."""
    print(f"Month-end close — period {result.period} (seed {result.seed})")
    print(f"  Posted entries : {len(result.register)}")
    print(f"  Refused (tie)  : {len(result.refused)}")
    debits, credits = result.ledger.total_debits_credits()
    tb_ok = "OK" if debits == credits else "FAIL"
    print(f"  Trial balance  : Dr {money.fmt(debits)} / Cr {money.fmt(credits)} "
          f"[{tb_ok}]")
    print("  Tie-outs:")
    if result.ties:
        for t in result.ties:
            mark = "OK" if t.ties else "FAIL"
            print(f"    - {t.schedule:<28} acct {t.account}: "
                  f"sched {money.fmt(t.expected_cents)} vs "
                  f"GL {money.fmt(t.actual_cents)} [{mark}]")
    else:
        print("    (none declared)")
    if result.refused:
        print("  Refused entries:")
        for err in result.refused:
            print(f"    - {err.je.je_id}: {err.detail}")
    out_path = Path(out_dir).resolve()
    print(f"  Outputs written to: {out_path}")
    print(f"  Close status: {'CLEAN' if result.clean else 'NOT CLEAN'}")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns a process exit code (0 == clean close)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    _validate_period(args.period)
    result = run_close(args.period, args.out, args.seed)
    _print_summary(result, args.out)
    return 0 if result.clean else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
