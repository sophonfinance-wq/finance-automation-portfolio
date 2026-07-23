"""Command-line entry point for the cash-completeness engine.

Bank-side-first reconciliation, end to end. A trial-balance-first tie-out
cannot see cash accounts that were never added to the TB, so this engine:

1. ingests the FULL bank register population plus the trial balance,
2. classifies every exception (A unmapped successor, B stale close-out,
   C timing, D unexplained -- nothing is silently dropped) and flags
   phantom TB rows with no register behind them,
3. drafts disciplined journal entries (no invented offsets),
4. writes the report package (exec summary, resolution schedule, scope
   reconciliation, JE CSV, evidence cards, machine-readable report.json),
5. INDEPENDENTLY re-derives the population from the raw inputs and
   cross-foots the written report before it ships
   (``ccengine.verify.independent_verify`` -- the ship gate).

All bundled sample data is fictional: a First Legacy Bank -> Union National
Bank migration across invented LLCs.

Subcommands
-----------
    demo      Run end-to-end on the bundled dataset (samples/ -> out/).
    run       Run on arbitrary inputs:
                  python run.py run --registers DIR --tb FILE --out DIR
    verify    Load a previously written report and cross-foot it against
              the raw inputs:
                  python run.py verify --registers DIR --tb FILE --report OUT_DIR
              Exits 1 on a NO_GO verdict.

``demo`` and ``run`` finish with the same independent verification pass and
exit 1 on NO_GO, so a broken report can never ship silently from CI.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, List, Optional

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:  # allow ``python run.py`` from any cwd
    sys.path.insert(0, str(_ROOT))

from ccengine import evidence, ingest, journal, report, verify  # noqa: E402
from ccengine.reconcile import (  # noqa: E402
    classify_exceptions,
    flag_placeholder_gls,
)
from ccengine.scope import build_scope_reconciliation  # noqa: E402

_REPORT_JSON = "report.json"
_WIDTH = 62

_KIND_LABELS = (
    ("A_UNMAPPED_SUCCESSOR", "A  Unmapped successor account"),
    ("B_STALE_CLOSEOUT", "B  Stale close-out balance"),
    ("C_TIMING", "C  Timing / deposit in transit"),
    ("D_UNEXPLAINED", "D  Unexplained"),
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` off a dataclass/object attribute or a dict key."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _money(x: Optional[float]) -> str:
    """Format a number with thousands separators; '--' for missing."""
    if x is None:
        return "--"
    if x < 0:
        return f"({abs(x):,.2f})"
    return f"{x:,.2f}"


def _jsonable(obj: Any) -> Any:
    """JSON fallback serializer for dataclasses and plain objects."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


def _check_inputs(registers_dir: Path, tb_path: Path) -> Optional[str]:
    """Return an error string when inputs are missing, else None."""
    if not registers_dir.is_dir():
        return f"error: registers directory not found: {registers_dir}"
    if not tb_path.is_file():
        return f"error: trial balance file not found: {tb_path}"
    return None


# --------------------------------------------------------------------------
# Console output
# --------------------------------------------------------------------------

def _print_summary(
    registers: list,
    tb_rows: list,
    exceptions: list,
    phantom_rows: list,
    drafts: list,
    scope_problems: List[str],
    registers_dir: Path,
    tb_path: Path,
    out_dir: Path,
    placeholder_accounts: Optional[list] = None,
) -> None:
    """Print the tight console summary table for a run."""
    kinds = Counter(str(_get(e, "kind", "?")) for e in exceptions)
    exception_accounts = {
        (str(_get(e, "entity", "")), str(_get(e, "gl_norm", "")))
        for e in exceptions
        if _get(e, "register_balance") is not None
    }
    clean = max(len(registers) - len(exception_accounts), 0)
    statuses = Counter(str(_get(d, "status", "?")) for d in drafts)

    print("=" * _WIDTH)
    print(" CASH COMPLETENESS RUN".ljust(_WIDTH - 18) + "[FICTIONAL DATA]")
    print("=" * _WIDTH)
    print(f" Registers dir : {registers_dir}")
    print(f" Trial balance : {tb_path}")
    print(f" Output dir    : {out_dir}")
    print("-" * _WIDTH)

    def row(label: str, value: Any) -> None:
        print(f" {label:<47}{str(value):>13}")

    row("Register accounts (bank-side population)", len(registers))
    row("Trial balance rows", len(tb_rows))
    row("Clean ties", clean)
    for kind, label in _KIND_LABELS:
        row(label, kinds.get(kind, 0))
    for kind in sorted(set(kinds) - {k for k, _ in _KIND_LABELS}):
        row(f"?  {kind}", kinds[kind])
    row("Phantom / no-register TB rows", len(phantom_rows))
    row("Placeholder / mis-keyed GL keys", len(placeholder_accounts or []))
    row(
        "Scope reconciliation foot",
        "CLEAN" if not scope_problems else f"{len(scope_problems)} PROBLEM(S)",
    )
    for problem in scope_problems:
        print(f"    ! {problem}")
    row(
        "JE drafts ready / needs_judgment / no_entry",
        f"{statuses.get('ready', 0)} / {statuses.get('needs_judgment', 0)}"
        f" / {statuses.get('no_entry', 0)}",
    )

    if exceptions:
        print("-" * _WIDTH)
        print(" Exceptions (register vs trial balance)")
        for e in exceptions:
            print(
                f"   {str(_get(e, 'kind', '?')):<22}{str(_get(e, 'gl_norm', '?')):<14}"
                f"{str(_get(e, 'entity', '?'))}"
            )
            print(
                f"     register {_money(_get(e, 'register_balance')):>14}"
                f"   TB {_money(_get(e, 'tb_balance')):>14}"
            )
    if placeholder_accounts:
        print("-" * _WIDTH)
        print(" Placeholder / mis-keyed GL keys (tie, but flagged for review)")
        for a in placeholder_accounts:
            print(
                f"   {str(_get(a, 'gl_norm', '?')):<16}"
                f"{_money(_get(a, 'balance')):>14}   "
                f"{str(_get(a, 'entity', '?'))}"
            )
    open_questions = [d for d in drafts if _get(d, "status") == "needs_judgment"]
    if open_questions:
        print("-" * _WIDTH)
        print(" Open JE questions (no offset is ever invented)")
        for d in open_questions:
            question = str(_get(d, "question", "") or "")
            if len(question) > 76:
                question = question[:73] + "..."
            print(f"   {str(_get(d, 'ref', '?')):<10}{question}")
    print("-" * _WIDTH)


def _print_verdict(verdict: Any) -> str:
    """Print the verification verdict and its findings; returns the status."""
    status = str(_get(verdict, "status", "UNKNOWN"))
    findings = _get(verdict, "findings", None) or []
    print(f" Independent verification: {status}")
    for f in findings:
        print(f"   [{_get(f, 'severity', '')}] {_get(f, 'finding', '')}")
        fix = _get(f, "fix", "")
        if fix:
            print(f"         fix: {fix}")
    print("=" * _WIDTH)
    return status


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_run(
    registers_dir: Path,
    tb_path: Path,
    out_dir: Path,
    cutoff: Optional[str] = None,
) -> int:
    """Full pipeline: ingest -> classify -> JEs -> report -> evidence -> verify."""
    problem = _check_inputs(registers_dir, tb_path)
    if problem:
        print(problem, file=sys.stderr)
        return 2

    # 1. Ingest the full bank-side population plus the trial balance.
    registers = ingest.load_registers(str(registers_dir))
    tb_rows = ingest.load_trial_balance(str(tb_path))

    # 2. Classify every exception; phantom TB rows come back separately.
    exceptions, phantom_rows = classify_exceptions(registers, tb_rows, cutoff=cutoff)
    scope = build_scope_reconciliation(registers, exceptions)
    scope_problems = scope.foot(registers)

    # 2b. Flag register accounts booked against a mis-keyed placeholder GL.
    #     They tie and stay in their scope bucket; the flag travels alongside
    #     so the suspicious key still reaches a reviewer.
    placeholder_accounts = flag_placeholder_gls(registers)

    # 3. Journal-entry discipline: ready only when amount AND offset are
    #    fully documented; otherwise a precise question, never a guess.
    drafts = journal.draft_entries(exceptions, phantom_rows)

    # 4. Assemble the report artifact and persist the machine-readable copy
    #    FIRST -- verification runs against what actually ships.
    as_of = max((str(_get(r, "as_of", "") or "") for r in registers), default="")
    report_dict = report.build_report(
        registers, tb_rows, exceptions, scope, phantom_rows=phantom_rows,
        as_of=as_of, placeholder_gls=placeholder_accounts,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / _REPORT_JSON
    report_json.write_text(
        json.dumps(report_dict, indent=2, default=_jsonable), encoding="utf-8"
    )

    # 5. The ship gate: independently re-derive the population from the raw
    #    inputs and cross-foot the written report (no shared classifier).
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    verdict = verify.independent_verify(str(registers_dir), str(tb_path), payload)

    # 6. Human-readable outputs, stamped with the verdict.
    written = report.write_outputs(report_dict, drafts, str(out_dir), verdict=verdict)
    cards = evidence.render_evidence_cards(
        exceptions, registers, str(out_dir / "evidence")
    )

    _print_summary(
        registers, tb_rows, exceptions, phantom_rows, drafts,
        scope_problems, registers_dir, tb_path, out_dir,
        placeholder_accounts=placeholder_accounts,
    )
    print(
        f" Wrote {len(written) + 1} report files + {len(cards)} evidence files"
        f" to {out_dir.resolve()}"
    )
    print("-" * _WIDTH)
    status = _print_verdict(verdict)
    if status == "NO_GO" or scope_problems:
        return 1
    return 0


def cmd_verify(registers_dir: Path, tb_path: Path, report_dir: Path) -> int:
    """Load a written report and cross-foot it against the raw inputs."""
    problem = _check_inputs(registers_dir, tb_path)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    report_path = report_dir if report_dir.is_file() else report_dir / _REPORT_JSON
    if not report_path.is_file():
        print(
            f"error: {report_path} not found -- run 'python run.py run'"
            " (or 'demo') first",
            file=sys.stderr,
        )
        return 2

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    verdict = verify.independent_verify(str(registers_dir), str(tb_path), payload)

    print("=" * _WIDTH)
    print(f" Report under test : {report_path}")
    print(f" Registers dir     : {registers_dir}")
    print(f" Trial balance     : {tb_path}")
    print("-" * _WIDTH)
    status = _print_verdict(verdict)
    return 1 if status == "NO_GO" else 0


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------

def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cash-completeness-engine",
        description=(
            "Bank-side-first cash completeness reconciliation (fictional data). "
            "Starts from the register population, classifies every exception, "
            "and independently verifies the report before it ships."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run end-to-end on the bundled fictional dataset")
    demo.add_argument("--out", type=str, default=str(_ROOT / "out"), help="output directory")

    run = sub.add_parser("run", help="run on arbitrary inputs")
    run.add_argument("--registers", type=str, required=True, help="directory of register CSVs")
    run.add_argument("--tb", type=str, required=True, help="trial balance CSV")
    run.add_argument("--out", type=str, required=True, help="output directory")
    run.add_argument(
        "--cutoff", type=str, default=None,
        help=(
            "ISO cutoff date for timing classification. When omitted (the "
            "default), timing is derived from each register's own running "
            "balances rather than a fixed date."
        ),
    )

    ver = sub.add_parser("verify", help="independently cross-foot a written report")
    ver.add_argument("--registers", type=str, required=True, help="directory of register CSVs")
    ver.add_argument("--tb", type=str, required=True, help="trial balance CSV")
    ver.add_argument(
        "--report", type=str, required=True,
        help="output directory of a prior run (or a report.json path)",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main. Returns a process exit code (1 == NO_GO, 2 == bad inputs)."""
    args = _parse_args(argv)
    if args.command == "demo":
        return cmd_run(
            _ROOT / "samples" / "registers",
            _ROOT / "samples" / "trial_balance.csv",
            Path(args.out),
        )
    if args.command == "run":
        return cmd_run(
            Path(args.registers), Path(args.tb), Path(args.out), cutoff=args.cutoff
        )
    if args.command == "verify":
        return cmd_verify(Path(args.registers), Path(args.tb), Path(args.report))
    return 2  # pragma: no cover - argparse enforces the choices


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
