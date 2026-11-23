"""Command-line entry for the Cash Management engine.

``python -m cash_engine --demo`` runs all five validation-only controls on
seeded, fictional data and prints one verdict line per control. Every control
is read-only; nothing is posted, drafted, or written back to any source.
"""

from __future__ import annotations

import argparse

from .bank_rec import BankReconciliationValidator, demo_reconciliations
from .outstanding_checks import OutstandingCheckValidator, demo_checks
from .wire_approval import WireApprovalValidator, demo_wires
from .bank_register import BankRegisterValidator, demo_register
from .cash_concentration import CashConcentrationValidator, demo_concentration

PERIOD = "2026-06"


def _run_all() -> list[tuple[str, object]]:
    """Run every control on its clean demo input; return (name, result) pairs."""
    account, sweeps = demo_concentration()
    return [
        ("bank_rec           ", BankReconciliationValidator(PERIOD, demo_reconciliations()).run()),
        ("outstanding_checks ", OutstandingCheckValidator(PERIOD, "2026-06-30", 180, demo_checks()).run()),
        ("wire_approval      ", WireApprovalValidator(PERIOD, demo_wires()).run()),
        ("bank_register      ", BankRegisterValidator(demo_register()).run()),
        ("cash_concentration ", CashConcentrationValidator(account, sweeps).run()),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cash_engine", description="Cash Management controls (validation only).")
    parser.add_argument("--demo", action="store_true", help="run all five controls on seeded fictional data")
    args = parser.parse_args(argv)

    if not args.demo:
        parser.print_help()
        return 0

    print("Cash Management — validation-only controls (fictional data)\n")
    all_clean = True
    for name, result in _run_all():
        n = len(result.findings)
        verdict = result.verdict
        all_clean = all_clean and result.mechanical_clean
        assert not result.posting_authorized  # invariant: never posts
        print(f"  {name}  {verdict:22}  findings={n}")
    print(f"\n  Every control read-only; nothing posted. "
          f"{'All clean.' if all_clean else 'Review required.'}")
    return 0 if all_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
