"""Read-only validation for a recurring journal-entry register.

This module deliberately stops at validation.  It does not create
:class:`~close_engine.model.JournalEntry` objects, post to a
:class:`~close_engine.model.Ledger`, build an ERP import payload, or mutate the
input register.  The narrow boundary makes it suitable as a preflight gate for
a human-controlled recurring-entry process.

Amounts use the same integer-cent convention as the rest of ``close_engine``.
Strings, floats, booleans, formulas, and spreadsheet error tokens are rejected
instead of being coerced into accounting amounts.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


AmountInput = int | float | str | None

_PERIOD_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_PERIOD_TOKEN_RE = re.compile(
    r"(?<!\d)(\d{4}-(?:0[1-9]|1[0-2]))(?!\d)"
)
_SPREADSHEET_ERRORS = {
    "#CALC!",
    "#DIV/0!",
    "#N/A",
    "#NAME?",
    "#NULL!",
    "#NUM!",
    "#REF!",
    "#SPILL!",
    "#VALUE!",
}


@dataclass(frozen=True)
class RegisterRow:
    """One line from a recurring-entry register.

    ``entry_id`` groups lines into one proposed entry.  ``line_id`` must be
    unique within that entry.  Debit and credit values are raw on purpose so
    the validator can report unsafe spreadsheet values without first coercing
    them.
    """

    period: str
    entry_id: str
    line_id: str
    entity: str
    account: str
    debit_cents: AmountInput
    credit_cents: AmountInput
    memo: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "RegisterRow":
        """Build a row from a JSON-like mapping without amount coercion."""

        required = (
            "period",
            "entry_id",
            "line_id",
            "entity",
            "account",
            "debit_cents",
            "credit_cents",
            "memo",
        )
        missing = [name for name in required if name not in value]
        if missing:
            raise ValueError(
                "register row missing required fields: " + ", ".join(missing)
            )
        return cls(
            period=value["period"],  # type: ignore[arg-type]
            entry_id=value["entry_id"],  # type: ignore[arg-type]
            line_id=value["line_id"],  # type: ignore[arg-type]
            entity=value["entity"],  # type: ignore[arg-type]
            account=value["account"],  # type: ignore[arg-type]
            debit_cents=value["debit_cents"],  # type: ignore[arg-type]
            credit_cents=value["credit_cents"],  # type: ignore[arg-type]
            memo=value["memo"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class RegisterFinding:
    """A deterministic issue found in the register."""

    code: str
    detail: str
    row_number: int | None = None
    entry_id: str = ""
    line_id: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class RegisterGroupBalance:
    """Independent debit/credit crossfoot for one proposed entry."""

    entry_id: str
    debit_cents: int
    credit_cents: int
    verifiable: bool

    @property
    def balanced(self) -> bool:
        """Return true only when complete valid amounts crossfoot exactly."""

        return self.verifiable and self.debit_cents == self.credit_cents


@dataclass(frozen=True)
class RecurringRegisterResult:
    """Read-only recurring-register validation result."""

    target_period: str
    row_count: int
    group_balances: tuple[RegisterGroupBalance, ...]
    total_debits_cents: int
    total_credits_cents: int
    totals_verifiable: bool
    findings: tuple[RegisterFinding, ...] = field(default_factory=tuple)
    # These are intentionally permanent empty evidence fields.  A consumer can
    # assert the validator produced no posting or import work product.
    posting_actions: tuple[object, ...] = field(default_factory=tuple)
    import_payloads: tuple[object, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        """True when every validation gate passes."""

        return not self.findings

    @property
    def verdict(self) -> str:
        """Return the compact review verdict."""

        return "PASS" if self.clean else "NEEDS REVIEW"

    @property
    def posting_authorized(self) -> bool:
        """Always false: this component is a validator, not a posting engine."""

        return False


def _canonical_period(value: object) -> bool:
    return isinstance(value, str) and _PERIOD_RE.fullmatch(value) is not None


def _text_problem(label: str, value: object) -> str | None:
    if not isinstance(value, str):
        return f"{label} must be text"
    if not value.strip():
        return f"{label} must not be blank"
    if value != value.strip():
        return f"{label} must already be trimmed"
    return None


def _amount_problem(value: AmountInput) -> str | None:
    """Return why a raw cents value is unsafe, or ``None`` when valid."""

    if isinstance(value, bool):
        return "boolean is not an accounting amount"
    if isinstance(value, int):
        if value < 0:
            return "amount must be nonnegative; use the opposite column"
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return "nonfinite amount"
        return "floating-point amount is not allowed; provide integer cents"
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized.startswith("="):
            return "formula text is not a cached accounting amount"
        if normalized in _SPREADSHEET_ERRORS:
            return f"spreadsheet error token {normalized}"
        return "text amount is not allowed; provide integer cents"
    if value is None:
        return "amount is missing"
    return f"unsupported amount type {type(value).__name__}"


class RecurringRegisterValidator:
    """Validate a recurring-entry register without producing side effects."""

    def __init__(
        self, target_period: str, rows: Iterable[RegisterRow]
    ) -> None:
        if not _canonical_period(target_period):
            raise ValueError("target_period must be canonical YYYY-MM")
        self.target_period = target_period
        self.rows = tuple(rows)

    def run(self) -> RecurringRegisterResult:
        """Run row, duplicate, stale-period, and balance controls."""

        findings: list[RegisterFinding] = []
        if not self.rows:
            findings.append(
                RegisterFinding(
                    "REGISTER_EMPTY",
                    "the recurring-entry register contains no rows",
                )
            )

        seen_keys: dict[tuple[str, str], int] = {}
        group_totals: dict[str, list[int]] = {}
        group_verifiable: dict[str, bool] = {}

        for row_number, row in enumerate(self.rows, start=1):
            entry_label = (
                row.entry_id if isinstance(row.entry_id, str) else str(row.entry_id)
            )
            line_label = (
                row.line_id if isinstance(row.line_id, str) else str(row.line_id)
            )
            group_key = entry_label or f"<row:{row_number}>"
            group_totals.setdefault(group_key, [0, 0])
            group_verifiable.setdefault(group_key, True)

            def add(code: str, detail: str) -> None:
                findings.append(
                    RegisterFinding(
                        code,
                        detail,
                        row_number=row_number,
                        entry_id=entry_label,
                        line_id=line_label,
                    )
                )

            if not _canonical_period(row.period):
                add(
                    "ROW_PERIOD_INVALID",
                    "row period must be canonical YYYY-MM",
                )
            elif row.period != self.target_period:
                add(
                    "ROW_PERIOD_STALE",
                    f"row period {row.period} does not equal target "
                    f"{self.target_period}",
                )

            for label, value in (
                ("entry_id", row.entry_id),
                ("line_id", row.line_id),
                ("entity", row.entity),
                ("account", row.account),
                ("memo", row.memo),
            ):
                problem = _text_problem(label, value)
                if problem:
                    add("ROW_FIELD_INVALID", problem)

            if isinstance(row.entry_id, str) and isinstance(row.line_id, str):
                key = (row.entry_id, row.line_id)
                if key in seen_keys:
                    add(
                        "DUPLICATE_LINE_KEY",
                        "entry_id and line_id duplicate row "
                        f"{seen_keys[key]}",
                    )
                else:
                    seen_keys[key] = row_number

            if isinstance(row.memo, str):
                stale_tokens = sorted(
                    {
                        token
                        for token in _PERIOD_TOKEN_RE.findall(row.memo)
                        if token != self.target_period
                    }
                )
                if stale_tokens:
                    add(
                        "STALE_MEMO_PERIOD",
                        "memo names a non-target period: "
                        + ", ".join(stale_tokens),
                    )

            amount_valid = True
            for label, value in (
                ("debit_cents", row.debit_cents),
                ("credit_cents", row.credit_cents),
            ):
                problem = _amount_problem(value)
                if problem:
                    amount_valid = False
                    add("ROW_AMOUNT_INVALID", f"{label}: {problem}")

            if not amount_valid:
                group_verifiable[group_key] = False
                continue

            # Type guards above prove these are nonnegative integer cents.
            debit = row.debit_cents
            credit = row.credit_cents
            assert isinstance(debit, int) and not isinstance(debit, bool)
            assert isinstance(credit, int) and not isinstance(credit, bool)
            group_totals[group_key][0] += debit
            group_totals[group_key][1] += credit
            if debit and credit:
                add(
                    "ROW_TWO_SIDED",
                    "a register line cannot contain both a debit and a credit",
                )
            elif debit == 0 and credit == 0:
                add(
                    "ROW_ZERO_AMOUNT",
                    "a register line must contain a nonzero debit or credit",
                )

        balances: list[RegisterGroupBalance] = []
        for entry_id in sorted(group_totals):
            debit, credit = group_totals[entry_id]
            verifiable = group_verifiable[entry_id]
            balance = RegisterGroupBalance(
                entry_id, debit, credit, verifiable
            )
            balances.append(balance)
            if not verifiable:
                findings.append(
                    RegisterFinding(
                        "GROUP_BALANCE_UNVERIFIABLE",
                        "one or more rows contain invalid amounts",
                        entry_id=entry_id,
                    )
                )
            elif debit != credit:
                findings.append(
                    RegisterFinding(
                        "GROUP_OUT_OF_BALANCE",
                        f"debits {debit} cents do not equal credits "
                        f"{credit} cents",
                        entry_id=entry_id,
                    )
                )

        totals_verifiable = all(group_verifiable.values())
        total_debits = sum(balance.debit_cents for balance in balances)
        total_credits = sum(balance.credit_cents for balance in balances)
        if not totals_verifiable:
            findings.append(
                RegisterFinding(
                    "GLOBAL_BALANCE_UNVERIFIABLE",
                    "one or more groups contain invalid amounts",
                )
            )
        elif total_debits != total_credits:
            findings.append(
                RegisterFinding(
                    "GLOBAL_OUT_OF_BALANCE",
                    f"debits {total_debits} cents do not equal credits "
                    f"{total_credits} cents",
                )
            )

        return RecurringRegisterResult(
            target_period=self.target_period,
            row_count=len(self.rows),
            group_balances=tuple(balances),
            total_debits_cents=total_debits,
            total_credits_cents=total_credits,
            totals_verifiable=totals_verifiable,
            findings=tuple(findings),
        )


def demo_rows(period: str) -> tuple[RegisterRow, ...]:
    """Return a small, fully fictional clean register for the CLI demo."""

    return (
        RegisterRow(
            period,
            f"RJE-{period}-01",
            "01-D",
            "NORTH",
            "EXP-SERVICE",
            125_000,
            0,
            f"{period} recurring service accrual",
        ),
        RegisterRow(
            period,
            f"RJE-{period}-01",
            "01-C",
            "NORTH",
            "LIAB-SERVICE",
            0,
            125_000,
            f"{period} recurring service accrual",
        ),
        RegisterRow(
            period,
            f"RJE-{period}-02",
            "02-D",
            "SOUTH",
            "EXP-SUPPORT",
            80_000,
            0,
            f"{period} recurring support accrual",
        ),
        RegisterRow(
            period,
            f"RJE-{period}-02",
            "02-C",
            "SOUTH",
            "LIAB-SUPPORT",
            0,
            80_000,
            f"{period} recurring support accrual",
        ),
    )


def _load_json(path: Path) -> tuple[str, tuple[RegisterRow, ...]]:
    """Load a generic register document for validation only."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input JSON must be an object")
    period = value.get("target_period")
    rows = value.get("rows")
    if not isinstance(period, str):
        raise ValueError("input target_period must be text")
    if not isinstance(rows, list):
        raise ValueError("input rows must be a list")
    parsed: list[RegisterRow] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"input row {index} must be an object")
        parsed.append(RegisterRow.from_mapping(row))
    return period, tuple(parsed)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the read-only validator against a JSON file or fictional demo."""

    parser = argparse.ArgumentParser(
        prog="close_engine.recurring_register",
        description="Validate a recurring JE register without posting it.",
    )
    parser.add_argument("--period", default="2026-03", help="Demo period YYYY-MM.")
    parser.add_argument(
        "--input",
        type=Path,
        help="Optional JSON register; omitted uses seeded fictional rows.",
    )
    args = parser.parse_args(argv)
    try:
        if args.input:
            target_period, rows = _load_json(args.input)
        else:
            target_period = args.period
            rows = demo_rows(target_period)
        result = RecurringRegisterValidator(target_period, rows).run()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(f"Recurring-register preflight - {result.target_period}")
    print(f"  Rows             : {result.row_count}")
    print(f"  Entry groups     : {len(result.group_balances)}")
    print(
        f"  Debits / credits : {result.total_debits_cents} / "
        f"{result.total_credits_cents} cents"
    )
    print(f"  Findings         : {len(result.findings)}")
    print("  Posting actions  : 0 (validation only)")
    print("  Import payloads  : 0 (validation only)")
    for finding in result.findings:
        location = f" row {finding.row_number}" if finding.row_number else ""
        print(f"  - {finding.code}{location}: {finding.detail}")
    print(f"  Verdict          : {result.verdict}")
    return 0 if result.clean else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
