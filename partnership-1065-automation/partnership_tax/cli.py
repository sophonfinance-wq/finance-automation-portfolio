"""Command-line interface for the partnership 1065 automation demo."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import build_tax_package
from .generate import DEFAULT_SEED, generate_source_package
from .money import fmt
from .report import write_outputs

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _REPO_ROOT / "output"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="partnership_tax",
        description="Fictional AI-assisted Form 1065 preparation automation demo.",
    )
    parser.add_argument("--year", type=int, default=2025, help="Tax year.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Synthetic source seed.")
    parser.add_argument("--out", type=Path, default=_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--no-xlsx", action="store_true", help="Skip optional support workbook.")
    parser.add_argument(
        "--section704c",
        action="store_true",
        help=(
            "Run the IRC §704(c) built-in-gain demo (traditional method + ceiling "
            "rule) instead of the standard 1065 package; writes section704c_*.md."
        ),
    )
    return parser


def _run_section704c(out_dir: Path) -> int:
    """Run the §704(c) built-in-gain demo and write its Markdown artifacts."""
    from . import section704c

    partnership, written = section704c.run_demo(out_dir)
    print("Partnership §704(c) Built-In Gain (traditional method + ceiling rule)")
    print(f"  Partnership       : {partnership.name}")
    print(f"  Partners          : {len(partnership.partners)}")
    print(f"  Contributed props : {len(partnership.properties)}")
    biggest = max(
        partnership.properties.values(), key=lambda p: p.built_in_gain_cents
    )
    print(
        f"  Built-in gain     : ${fmt(biggest.built_in_gain_cents)} "
        f"({biggest.name})"
    )
    print(f"  Outputs           : {out_dir}")
    for path in written:
        print(f"    - {path.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.section704c:
        return _run_section704c(args.out)

    source = generate_source_package(year=args.year, seed=args.seed)
    package = build_tax_package(source)
    written = write_outputs(package, args.out, write_xlsx=not args.no_xlsx)

    print("Partnership 1065 Automation")
    print(f"  Tax year          : {source.year}")
    print(f"  Partnership       : {source.partnership_name}")
    print(f"  Partners          : {len(source.partners)}")
    print(f"  Ordinary income   : ${fmt(package.ordinary_income_cents)}")
    print(f"  Review checks     : {sum(c.status == 'OK' for c in package.checks)}/{len(package.checks)} OK")
    print(f"  Package status    : {'READY' if package.ready else 'REVIEW'}")
    print(f"  Outputs           : {args.out}")
    for path in written:
        print(f"    - {path.name}")
    return 0 if package.ready else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
