"""Independent verification: the check that ships (or blocks) the report.

This module is the crown jewel of the engine. Its one job is to answer, from
the RAW inputs and nothing else:

    "Does the report account for every dollar in the register population?"

``independent_verify`` re-derives the full register population directly from
the register CSVs and the trial balance, then cross-foots the preparer's
report against that re-derivation:

1. **Population completeness** -- every register account must appear in the
   report's scope reconciliation in EXACTLY one bucket. An omitted account is
   an automatic ``NO_GO`` naming the account; so is a double-counted one.
2. **Totals re-add** -- every bucket total in the report must re-foot, to the
   cent, against the independently derived register balances of that bucket's
   members.
3. **Exception coverage** -- the verifier re-computes its own classification
   signals (live account absent from the TB, closed account still carried on
   the TB, closed account absent from the TB that still holds cash at the
   bank, account whose register and TB balances differ) and confirms the
   report surfaced an exception for each one. A dollar difference that the
   report never mentions is exactly the overclaim this module exists to catch.

DELIBERATE DUPLICATION -- READ BEFORE "REFACTORING":
    This file re-implements CSV parsing, GL normalization, and the minimal
    matching logic instead of importing them from ``ingest.py``,
    ``normalize.py``, or ``reconcile.py``. That is intentional, not an
    oversight. An auditor who reuses the preparer's code inherits the
    preparer's bugs: if the shared normalizer silently drops an account, both
    the report AND the check built on the same normalizer agree the account
    never existed. Independent re-derivation is the entire point of this
    module. Do not "clean this up" by importing the shared helpers.

All data in this repository is fictional (see the top-level README).
"""

from __future__ import annotations

import csv
import os
import re
from typing import Dict, Iterable, List, Optional, Tuple

try:  # The shared contract type. Fall back so this file also runs standalone.
    from .models import Verdict
except ImportError:  # pragma: no cover - standalone / audit-from-a-USB-stick mode
    from dataclasses import dataclass, field

    @dataclass
    class Verdict:  # type: ignore[no-redef]
        """Local stand-in matching the shared contract in ``models.py``."""

        status: str = "NO_GO"
        findings: List[dict] = field(default_factory=list)


__all__ = ["independent_verify", "derive_population"]

# One half-cent: two amounts within this are "equal to the cent".
_CENT: float = 0.005

_CRITICAL = "critical"
_WARNING = "warning"
_INFO = "info"


# ---------------------------------------------------------------------------
# Independent primitives (duplicated on purpose -- see module docstring)
# ---------------------------------------------------------------------------


def _to_float(raw: object) -> Optional[float]:
    """Parse a monetary cell tolerantly; return ``None`` if not numeric.

    Accepts ints/floats, thousands separators, a leading ``$``, and
    accountant-style parenthesized negatives like ``(1,234.56)``.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", "").replace("$", "")
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def _normalize_gl(raw: object) -> str:
    """Canonicalize a GL key to ``NNN-NNN-NNNN`` form (verifier's own copy).

    Mirrors the documented behavior of ``normalize.normalize_gl`` -- e.g.
    ``'615-001-00-1133'``, ``'615-001-1133'`` and ``6150011133`` all map to
    ``'615-001-1133'`` -- but is written from the spec, not copied from the
    shared module, so a bug there cannot hide an account from this check.
    """
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    text = str(raw).strip()
    if not text:
        return ""
    segments = [s for s in re.split(r"[^0-9]+", text) if s]
    # Drop short all-zero filler segments ('00' in 615-001-00-1133).
    segments = [s for s in segments if not (len(s) <= 2 and set(s) == {"0"})]
    digits = "".join(segments)
    if len(digits) == 12 and digits[6:8] == "00":
        digits = digits[:6] + digits[8:]
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return "-".join(segments) if segments else ""


def _is_placeholder_gl(gl_norm: str) -> bool:
    """Flag suspicious placeholder keys such as ``001-001-...`` (mis-keyed rows)."""
    digits = re.sub(r"\D", "", gl_norm)
    if not digits or set(digits) == {"0"}:
        return True
    return gl_norm.startswith("001-001")


def _field(obj: object, name: str, default: object = None) -> object:
    """Read ``name`` from either a dict or an object attribute (report-tolerant)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# Raw-input re-derivation
# ---------------------------------------------------------------------------


def _read_register_file(path: str) -> Tuple[Dict[str, object], List[str]]:
    """Parse one register CSV with the verifier's own parser.

    Returns ``(record, problems)`` where ``record`` carries entity, status,
    ``gl_norm`` and the independently derived closing balance (the last
    transaction's running balance), and ``problems`` lists internal-foot
    breaks (rows where prior running balance + amount != running balance).
    """
    meta: Dict[str, str] = {}
    txn_rows: List[List[str]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if not row or not any(cell.strip() for cell in row):
                continue
            first = row[0].strip()
            if first.startswith("#"):
                text = ",".join(row).lstrip("#").strip()
                sep = ":" if ":" in text else ("=" if "=" in text else None)
                if sep:
                    key, _, value = text.partition(sep)
                    meta[key.strip().lower().replace(" ", "_")] = value.strip()
                continue
            if first.lower() == "date":  # optional column-header row
                continue
            txn_rows.append(row)

    problems: List[str] = []
    balance = 0.0
    prev_rb: Optional[float] = None
    for row in txn_rows:
        amount = _to_float(row[2]) if len(row) > 2 else None
        rb = _to_float(row[3]) if len(row) > 3 else None
        if rb is None or amount is None:
            problems.append(f"{os.path.basename(path)}: non-numeric row {row!r}")
            continue
        if prev_rb is not None and abs(prev_rb + amount - rb) > _CENT:
            problems.append(
                f"{os.path.basename(path)}: running balance breaks at "
                f"{row[0]!r} ({prev_rb:,.2f} + {amount:,.2f} != {rb:,.2f})"
            )
        prev_rb = rb
        balance = rb

    record: Dict[str, object] = {
        "source_file": os.path.basename(path),
        "entity": meta.get("entity", ""),
        "gl_norm": _normalize_gl(meta.get("gl_account", "")),
        "status": (meta.get("status", "live") or "live").strip().lower(),
        "balance": round(balance, 2),
    }
    return record, problems


def derive_population(registers_dir: str) -> Tuple[Dict[str, Dict[str, object]], List[str]]:
    """Independently derive the register population from the raw CSV directory.

    Returns ``(population, problems)``: a map ``gl_norm -> record`` and a list
    of data-integrity problems found along the way (duplicate GL keys across
    files, registers whose running balances do not internally foot).
    """
    population: Dict[str, Dict[str, object]] = {}
    problems: List[str] = []
    names = sorted(n for n in os.listdir(registers_dir) if n.lower().endswith(".csv"))
    for name in names:
        record, file_problems = _read_register_file(os.path.join(registers_dir, name))
        problems.extend(file_problems)
        gl = str(record["gl_norm"])
        if not gl:
            problems.append(f"{name}: register file has no parseable gl_account")
            continue
        if gl in population:
            problems.append(
                f"duplicate GL {gl} across register files "
                f"{population[gl]['source_file']} and {name}"
            )
            continue
        population[gl] = record
    return population, problems


def _read_trial_balance(path: str) -> Dict[str, float]:
    """Parse the TB CSV (``sheet,gl_account,title,balance``) -> ``gl_norm -> balance``.

    Multiple rows on the same normalized GL are summed, exactly because a
    typo-duplicated line is one of the failure modes this engine teaches.
    """
    balances: Dict[str, float] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 4 or not any(cell.strip() for cell in row):
                continue
            balance = _to_float(row[3])
            if balance is None:  # header or junk row
                continue
            # Digit-free keys (a mis-keyed "BAL", say) pass through verbatim
            # so the row stays visible to the phantom check below instead of
            # vanishing from the verifier's view of the TB.
            gl = _normalize_gl(row[1]) or str(row[1]).strip()
            if not gl:
                continue
            balances[gl] = round(balances.get(gl, 0.0) + balance, 2)
    return balances


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def _finding(severity: str, finding: str, fix: str) -> dict:
    """Build one finding row for the verdict."""
    return {"severity": severity, "finding": finding, "fix": fix}


def _extract_scope(report_dict: dict) -> Tuple[Dict[str, List[str]], Dict[str, float]]:
    """Pull ``buckets`` and ``totals`` out of the report, shape-tolerantly.

    Accepts either ``report['scope_reconciliation']`` (dict or object with
    ``buckets``/``totals``) or those keys at the top level of the report.
    """
    scope = _field(report_dict, "scope_reconciliation", None)
    if scope is None:
        scope = report_dict
    raw_buckets = _field(scope, "buckets", {}) or {}
    raw_totals = _field(scope, "totals", {}) or {}
    buckets = {
        str(name): [_normalize_gl(g) for g in members]
        for name, members in dict(raw_buckets).items()
    }
    totals = {str(name): value for name, value in dict(raw_totals).items()}
    return buckets, totals


def independent_verify(registers_dir: str, tb_path: str, report_dict: dict) -> Verdict:
    """Re-derive the population from raw inputs and cross-foot the report.

    Gate semantics:

    * any ``critical`` finding  -> ``NO_GO`` (do not ship the report),
    * only ``warning`` findings -> ``GO_WITH_FIXES``,
    * nothing but ``info``      -> ``GO``.

    An omission from the scope reconciliation, a bucket total that does not
    re-add, or a register-vs-TB dollar difference the report never surfaced
    are all critical: each one means a dollar could be unaccounted for.
    """
    findings: List[dict] = []

    if not os.path.isdir(registers_dir):
        return Verdict(
            status="NO_GO",
            findings=[
                _finding(
                    _CRITICAL,
                    f"registers directory not found: {registers_dir}",
                    "Point the verifier at the same raw register directory the report used.",
                )
            ],
        )

    population, data_problems = derive_population(registers_dir)
    for problem in data_problems:
        findings.append(
            _finding(
                _WARNING,
                f"register data integrity: {problem}",
                "Fix the source register export before relying on the report.",
            )
        )
    if not population:
        findings.append(
            _finding(
                _CRITICAL,
                f"no register accounts could be derived from {registers_dir}",
                "Verify the register directory contains the entity CSV exports.",
            )
        )

    # --- Check 1: every account in the scope reconciliation exactly once ----
    buckets, totals = _extract_scope(report_dict)
    if not buckets:
        findings.append(
            _finding(
                _CRITICAL,
                "report contains no scope reconciliation buckets",
                "Rebuild the report with a scope reconciliation covering every register account.",
            )
        )

    membership: Dict[str, int] = {gl: 0 for gl in population}
    unknown: List[str] = []
    for name, members in buckets.items():
        for gl in members:
            if gl in membership:
                membership[gl] += 1
            else:
                unknown.append(f"{gl} (bucket '{name}')")

    omitted = sorted(gl for gl, n in membership.items() if n == 0)
    if omitted:
        named = ", ".join(
            f"{gl} [{population[gl]['entity']}]" for gl in omitted
        )
        findings.append(
            _finding(
                _CRITICAL,
                f"{len(omitted)} register account(s) missing from the report scope "
                f"reconciliation: {named}",
                "The report does not cover the full bank-side population; re-run the "
                "reconciliation with these accounts included.",
            )
        )
    doubled = sorted(gl for gl, n in membership.items() if n > 1)
    if doubled:
        findings.append(
            _finding(
                _CRITICAL,
                f"register account(s) counted in more than one scope bucket: "
                f"{', '.join(doubled)}",
                "Each account belongs in exactly one bucket; fix the classifier.",
            )
        )
    if unknown:
        findings.append(
            _finding(
                _CRITICAL,
                f"report scope claims account(s) that do not exist in the raw "
                f"registers: {', '.join(sorted(unknown))}",
                "Remove or re-source these entries; the report must not claim "
                "accounts the raw population does not contain.",
            )
        )

    # --- Check 2: every bucket total must re-add, to the cent ---------------
    for name, members in buckets.items():
        refooted = round(sum(float(population[gl]["balance"]) for gl in members if gl in population), 2)
        reported = _to_float(totals.get(name))
        if reported is None:
            if members:
                findings.append(
                    _finding(
                        _WARNING,
                        f"bucket '{name}' has members but no reported total",
                        "Report a total for every bucket so it can be cross-footed.",
                    )
                )
            continue
        if abs(reported - refooted) > _CENT:
            findings.append(
                _finding(
                    _CRITICAL,
                    f"bucket '{name}' total does not re-add: reported "
                    f"{reported:,.2f}, independently refooted {refooted:,.2f}",
                    "Recompute the bucket total from the underlying register balances.",
                )
            )

    # --- Check 3: re-derive classification signals and check coverage -------
    if not os.path.isfile(tb_path):
        findings.append(
            _finding(
                _CRITICAL,
                f"trial balance not found: {tb_path}",
                "Point the verifier at the same trial balance the report used.",
            )
        )
        tb: Dict[str, float] = {}
    else:
        tb = _read_trial_balance(tb_path)

    reported_exceptions = _field(report_dict, "exceptions", None)
    exception_gls: set = set()
    if reported_exceptions is not None:
        for item in reported_exceptions:
            exception_gls.add(_normalize_gl(_field(item, "gl_norm", "")))

    expected: List[Tuple[str, str]] = []  # (gl, why it demands an exception)
    for gl, record in sorted(population.items()):
        status = record["status"]
        reg_bal = float(record["balance"])  # independently derived
        tb_bal = tb.get(gl) if tb else None
        if status == "live" and tb and tb_bal is None:
            expected.append((gl, "live register account absent from the trial balance"))
        elif status != "live" and tb_bal is not None and abs(tb_bal) > _CENT:
            expected.append(
                (gl, f"closed account still carried on the TB at {tb_bal:,.2f}")
            )
        elif status != "live" and tb and tb_bal is None and abs(reg_bal) > _CENT:
            # Money at the bank in a closed account the ledger has never
            # seen: certifying this inside a "ties" bucket is the exact
            # overclaim class a scope-and-totals check alone cannot catch.
            expected.append(
                (
                    gl,
                    f"closed account absent from the TB still holds "
                    f"{reg_bal:,.2f} at the bank",
                )
            )
        elif tb_bal is not None and abs(tb_bal - reg_bal) > _CENT:
            expected.append(
                (
                    gl,
                    f"register {reg_bal:,.2f} vs TB {tb_bal:,.2f} "
                    f"(difference {tb_bal - reg_bal:,.2f})",
                )
            )

    if reported_exceptions is None:
        if expected:
            findings.append(
                _finding(
                    _WARNING,
                    "report includes no 'exceptions' list, so exception coverage "
                    f"could not be verified ({len(expected)} signal(s) re-derived "
                    "independently)",
                    "Include the exception list in the report dict.",
                )
            )
    else:
        for gl, why in expected:
            if gl not in exception_gls:
                entity = population[gl]["entity"]
                findings.append(
                    _finding(
                        _CRITICAL,
                        f"unexplained difference not surfaced by the report: "
                        f"{gl} [{entity}] -- {why}",
                        "Every dollar difference must appear as a classified "
                        "exception; nothing may be silently dropped.",
                    )
                )

    # TB rows with no register behind them (the typo-line lesson). The report
    # is expected to flag these under 'phantom_or_no_register'; the verifier
    # only complains when a no-register TB balance is not surfaced anywhere.
    phantom_flagged: set = set()
    for row in _field(report_dict, "phantom_or_no_register", None) or []:
        raw_key = _field(row, "gl_norm", None) or _field(row, "gl_raw", "")
        key = _normalize_gl(raw_key) or str(raw_key or "").strip()
        if key:
            phantom_flagged.add(key)

    for gl, tb_bal in sorted(tb.items()):
        if gl in population or abs(tb_bal) <= _CENT:
            continue
        mentioned = (
            gl in exception_gls
            or gl in phantom_flagged
            or any(gl in members for members in buckets.values())
        )
        if mentioned:
            continue
        suffix = (
            " (key looks like a placeholder / mis-keyed row)"
            if _is_placeholder_gl(gl)
            else ""
        )
        findings.append(
            _finding(
                _WARNING,
                f"TB row {gl}{suffix} ({tb_bal:,.2f}) has no supporting register "
                "and is not flagged anywhere in the report",
                "Flag it phantom_or_no_register and route it for review.",
            )
        )

    # --- Verdict -------------------------------------------------------------
    severities = {f["severity"] for f in findings}
    if _CRITICAL in severities:
        status = "NO_GO"
    elif _WARNING in severities:
        status = "GO_WITH_FIXES"
    else:
        status = "GO"
        findings.append(
            _finding(
                _INFO,
                f"independent re-derivation ties: {len(population)} register "
                "account(s) each appear exactly once in scope and every bucket "
                "total re-adds to the cent",
                "None required.",
            )
        )
    return Verdict(status=status, findings=findings)
