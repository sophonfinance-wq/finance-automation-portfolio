"""Command-line interface for the close engine.

Run a full month-end close for a given period::

    python -m close_engine --period 2026-03 --out ./output

The CLI generates the seeded fictional dataset, runs the engine, writes the
committed outputs, and prints a concise tie-out summary. It exits non-zero if
the close is not clean (any refused entry or failed schedule tie) or, with
the sentinel on, if any control raises a CRITICAL finding -- the sentinel's
C1 gate independently verifies that the opening and post-close trial
balances balance. It can therefore gate an automated pipeline.

The Close Sentinel controls run by default after the close (``--no-sentinel``
turns them off); any CRITICAL finding also makes the exit code non-zero.
``--demo-guardrails`` injects every registered fault and prints a PASS/FAIL
table showing which control caught each one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, money
from .engine import CloseEngine, CloseResult
from .generate import generate_dataset
from .report import write_outputs
from .sentinel import ALL_CONTROLS, SentinelReport, Severity, run_sentinel


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
        "--sentinel",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the Close Sentinel controls after the close; CRITICAL "
             "findings make the exit code non-zero (default: on).",
    )
    parser.add_argument(
        "--demo-guardrails",
        action="store_true",
        help="Run the guardrail demo: a clean baseline plus every registered "
             "fault, printing which control caught each one.",
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


def _print_summary(
    result: CloseResult,
    out_dir: str,
    sentinel: SentinelReport | None = None,
) -> None:
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
    if sentinel is not None:
        print(f"  {sentinel.summary_line()}")
        for finding in sentinel.findings:
            scope = finding.entity or "group"
            print(f"    - [{finding.severity.value.upper()}] "
                  f"{finding.control_id} {scope}: {finding.subject}")
    out_path = Path(out_dir).resolve()
    print(f"  Outputs written to: {out_path}")
    print(f"  Close status: {'CLEAN' if result.clean else 'NOT CLEAN'}")


def _control_labels() -> dict[str, str]:
    """Map each control id (e.g. ``"C4"``) to its name (``"asset_life_guard"``).

    Derived from the control function names (``c4_asset_life_guard``) so the
    demo table always matches the registered controls.
    """
    labels: dict[str, str] = {}
    for control in ALL_CONTROLS:
        control_id, _, label = control.__name__.partition("_")
        labels[control_id.upper()] = label
    return labels


def _qualifying_hits(expected_id: str, hits: list) -> list:
    """Return the findings that count as a catch for the demo.

    A fault is caught only when its EXPECTED control fired at a blocking
    severity: the blocking controls must raise CRITICAL, while C7 (step
    change) is a reviewer-escalation control whose WARN counts as a catch.
    Findings from other controls never vouch for the expected one.
    """
    if expected_id == "C7":
        allowed = (Severity.CRITICAL, Severity.WARN)
    else:
        allowed = (Severity.CRITICAL,)
    return [f for f in hits if f.severity in allowed]


def _run_demo_guardrails(seed: int, period: str) -> int:
    """Run the guardrail demo and return a process exit code.

    A trustworthy control layer must both stay silent on a clean close and
    catch every known failure mode. The demo first runs the sentinel over an
    untouched close (which must produce ZERO findings), then injects every
    registered fault and checks that its mapped control fires with a
    qualifying severity (see :func:`_qualifying_hits`). Exit code 0 only if
    the baseline is silent AND every fault is caught.
    """
    from .faults import FAULTS, run_fault_demo

    labels = _control_labels()
    baseline_label = "baseline (no fault)"
    width = max(len(baseline_label), *(len(name) for name in FAULTS))

    print(f"Close Sentinel guardrail demo - period {period} (seed {seed})")

    dataset = generate_dataset(period, seed=seed)
    result = CloseEngine(dataset).run()
    baseline = run_sentinel(dataset, result)
    baseline_ok = not baseline.findings
    if baseline_ok:
        print(f"  {baseline_label:<{width}} -> PASS: zero findings on clean data")
    else:
        print(f"  {baseline_label:<{width}} -> FAIL: "
              f"{len(baseline.findings)} unexpected finding(s) on clean data")

    all_caught = True
    for fault_name, (_injector, expected_id) in FAULTS.items():
        demo_report, _desc = run_fault_demo(seed, period, fault_name)
        hits = _qualifying_hits(
            expected_id, demo_report.by_control.get(expected_id, [])
        )
        control_name = f"{expected_id} {labels.get(expected_id, 'unknown')}"
        if hits:
            severity = hits[0].severity.value.upper()
            print(f"  {fault_name:<{width}} -> PASS: caught by "
                  f"{control_name} ({severity}): {hits[0].subject}")
        else:
            all_caught = False
            print(f"  {fault_name:<{width}} -> FAIL: "
                  f"{control_name} did not fire")

    ok = baseline_ok and all_caught
    verdict = "ALL GUARDRAILS HELD" if ok else "GUARDRAIL GAP DETECTED"
    print(f"  Demo verdict: {verdict} "
          f"({len(FAULTS)} faults, baseline {'clean' if baseline_ok else 'dirty'})")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns a process exit code.

    Exit code 0 requires a clean close AND (when the sentinel is on) zero
    CRITICAL findings. With ``--demo-guardrails`` the exit code instead
    reflects the demo verdict (clean baseline + every fault caught).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    _validate_period(args.period)
    if args.demo_guardrails:
        return _run_demo_guardrails(args.seed, args.period)
    dataset = generate_dataset(args.period, seed=args.seed)
    result = CloseEngine(dataset).run()
    sentinel = run_sentinel(dataset, result) if args.sentinel else None
    write_outputs(result, args.out, sentinel=sentinel)
    _print_summary(result, args.out, sentinel)
    ok = result.clean and (sentinel is None or sentinel.clean)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
