"""Output writers for the close engine.

Produces the committed release artifacts in an output directory:

* ``je_register.md`` / ``je_register.json`` — the journal-entry register,
* ``schedules.json`` — every backing schedule and structured route field,
* ``trial_balance.md`` / ``trial_balance.json`` — the updated trial balance, and
* ``close_report.md`` — a close report with a checklist and tie-out summary.

An optional ``.xlsx`` workbook is written when openpyxl is available; it is
gitignored (kept out of version control) while the markdown/JSON are committed.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import money
from .engine import CloseResult
from .generate import ENTITY_BY_CODE
from .sentinel.findings import SentinelReport


def _account_name(result: CloseResult, code: str) -> str:
    """Return the account label for a code, or the bare code if unknown."""
    try:
        return result.ledger.coa.get(code).label
    except KeyError:
        return code


def _entity_name(code: str) -> str:
    """Return the fictional entity display name for a code."""
    ent = ENTITY_BY_CODE.get(code)
    return ent.name if ent else code


# --------------------------------------------------------------------------- #
# JE register
# --------------------------------------------------------------------------- #


def je_register_markdown(result: CloseResult) -> str:
    """Render the JE register as markdown."""
    lines: list[str] = []
    lines.append(f"# Journal Entry Register — {result.period}")
    lines.append("")
    lines.append(
        f"_Seed {result.seed}. {len(result.register)} entries posted; "
        f"{len(result.refused)} refused (out of tie)._"
    )
    lines.append("")
    for je in result.register:
        status = "ties" if je.is_balanced else "OUT OF TIE"
        lines.append(f"## {je.je_id} — {je.description}")
        lines.append("")
        lines.append(f"- Category: `{je.category}`")
        lines.append(f"- Control: debits {money.fmt(je.total_debits)} == "
                     f"credits {money.fmt(je.total_credits)} ({status})")
        lines.append("")
        lines.append(
            "| Entity | Account | Source | Project | Job | Cost | Memo | Debit | Credit |"
        )
        lines.append(
            "|--------|---------|--------|---------|-----|------|------|------:|-------:|"
        )
        for ln in je.lines:
            source = (
                f"{ln.source_batch}/{ln.source_line}"
                if ln.source_batch or ln.source_line
                else ""
            )
            lines.append(
                f"| {ln.entity} | {_account_name(result, ln.account)} | {source} "
                f"| {ln.project_code} | {ln.job_code} | {ln.cost_code} | {ln.memo} "
                f"| {money.fmt(ln.debit) if ln.debit else ''} "
                f"| {money.fmt(ln.credit) if ln.credit else ''} |"
            )
        lines.append(
            f"| | | | | | | **Totals** | **{money.fmt(je.total_debits)}** "
            f"| **{money.fmt(je.total_credits)}** |"
        )
        lines.append("")
    if result.refused:
        lines.append("## Refused entries (out of tie)")
        lines.append("")
        for err in result.refused:
            lines.append(f"- `{err.je.je_id}`: {err.detail}")
        lines.append("")
    return "\n".join(lines)


def je_register_json(result: CloseResult) -> dict:
    """Render the JE register as a JSON-serializable dict (amounts in cents)."""
    return {
        "period": result.period,
        "seed": result.seed,
        "entries": [
            {
                "je_id": je.je_id,
                "category": je.category,
                "description": je.description,
                "is_balanced": je.is_balanced,
                "total_debits_cents": je.total_debits,
                "total_credits_cents": je.total_credits,
                "lines": [
                    {
                        "entity": ln.entity,
                        "account": ln.account,
                        "debit_cents": ln.debit,
                        "credit_cents": ln.credit,
                        "memo": ln.memo,
                        "source_batch": ln.source_batch,
                        "source_line": ln.source_line,
                        "project_code": ln.project_code,
                        "job_code": ln.job_code,
                        "cost_code": ln.cost_code,
                    }
                    for ln in je.lines
                ],
            }
            for je in result.register
        ],
        "refused": [
            {"je_id": err.je.je_id, "detail": err.detail} for err in result.refused
        ],
    }


def schedules_json(result: CloseResult) -> dict:
    """Render every backing schedule with structured route provenance."""
    return {
        "period": result.period,
        "seed": result.seed,
        "schedules": [
            {
                "name": schedule.name,
                "category": schedule.category,
                "tie_account": schedule.tie_account,
                "tie_expected_cents": schedule.tie_expected_cents,
                "tie_expected_by_entity_cents": (
                    schedule.tie_expected_by_entity_cents
                ),
                "rows": [
                    {"key": row.key, **row.fields}
                    for row in schedule.rows
                ],
            }
            for schedule in result.schedules
        ],
    }


# --------------------------------------------------------------------------- #
# Trial balance
# --------------------------------------------------------------------------- #


def trial_balance_markdown(result: CloseResult) -> str:
    """Render the updated trial balance as markdown."""
    rows = result.ledger.trial_balance()
    debits, credits = result.ledger.total_debits_credits()
    lines: list[str] = []
    lines.append(f"# Updated Trial Balance — {result.period}")
    lines.append("")
    status = "in balance" if debits == credits else "OUT OF BALANCE"
    lines.append(
        f"_Total debits {money.fmt(debits)} vs credits {money.fmt(credits)} "
        f"({status})._"
    )
    lines.append("")
    lines.append("| Entity | Account | Debit | Credit |")
    lines.append("|--------|---------|------:|-------:|")
    for entity, account, dr, cr in rows:
        lines.append(
            f"| {entity} | {_account_name(result, account)} "
            f"| {money.fmt(dr) if dr else ''} "
            f"| {money.fmt(cr) if cr else ''} |"
        )
    lines.append(
        f"| | **Totals** | **{money.fmt(debits)}** | **{money.fmt(credits)}** |"
    )
    lines.append("")
    return "\n".join(lines)


def trial_balance_json(result: CloseResult) -> dict:
    """Render the trial balance as a JSON-serializable dict (amounts in cents)."""
    rows = result.ledger.trial_balance()
    debits, credits = result.ledger.total_debits_credits()
    return {
        "period": result.period,
        "total_debits_cents": debits,
        "total_credits_cents": credits,
        "in_balance": debits == credits,
        "rows": [
            {
                "entity": entity,
                "account": account,
                "debit_cents": dr,
                "credit_cents": cr,
            }
            for entity, account, dr, cr in rows
        ],
    }


# --------------------------------------------------------------------------- #
# Close report
# --------------------------------------------------------------------------- #


def close_report_markdown(
    result: CloseResult,
    sentinel: SentinelReport | None = None,
) -> str:
    """Render the close report (checklist + tie-out summary) as markdown.

    When a sentinel report is provided, a "Control findings" section lists
    every finding (or states that all controls passed).
    """
    lines: list[str] = []
    lines.append(f"# Month-End Close Report — {result.period}")
    lines.append("")
    lines.append("> FICTIONAL demonstration data. Generated deterministically "
                 f"(seed {result.seed}).")
    lines.append("")

    # Entity group.
    lines.append("## Entity group")
    lines.append("")
    for code, ent in ENTITY_BY_CODE.items():
        lines.append(f"- `{code}` — {ent.name}")
    lines.append("")

    # Checklist.
    lines.append("## Recurring-entry checklist")
    lines.append("")
    lines.append("| # | Recurring entry | Entry | Debits | Credits | Balanced |")
    lines.append("|---|-----------------|-------|-------:|--------:|:--------:|")
    for i, je in enumerate(result.register, start=1):
        mark = "[x]" if je.is_balanced else "[ ]"
        lines.append(
            f"| {i} | {je.description} | `{je.je_id}` "
            f"| {money.fmt(je.total_debits)} | {money.fmt(je.total_credits)} "
            f"| {mark} |"
        )
    lines.append("")

    # Tie-out summary.
    lines.append("## Tie-out summary")
    lines.append("")
    if result.ties:
        lines.append("| Schedule | GL account | Schedule | GL balance | Tie |")
        lines.append("|----------|-----------|---------:|-----------:|:---:|")
        for t in result.ties:
            mark = "[x]" if t.ties else "[ ]"
            lines.append(
                f"| {t.schedule} | {_account_name(result, t.account)} "
                f"| {money.fmt(t.expected_cents)} "
                f"| {money.fmt(t.actual_cents)} | {mark} |"
            )
    else:
        lines.append("_No schedules declared a GL tie-out account._")
    lines.append("")

    # Controls summary.
    debits, credits = result.ledger.total_debits_credits()
    lines.append("## Controls")
    lines.append("")
    lines.append(f"- [{'x' if result.all_balanced else ' '}] "
                 "Every posted entry balances (debits == credits).")
    lines.append(f"- [{'x' if debits == credits else ' '}] "
                 f"Trial balance is in balance "
                 f"({money.fmt(debits)} == {money.fmt(credits)}).")
    lines.append(f"- [{'x' if result.all_tie else ' '}] "
                 "Every schedule ties to the GL.")
    lines.append(f"- [{'x' if not result.refused else ' '}] "
                 f"No entries refused for being out of tie "
                 f"({len(result.refused)} refused).")
    lines.append("")
    if result.refused:
        lines.append("### Refused entries (out of tie)")
        lines.append("")
        for err in result.refused:
            lines.append(f"- `{err.je.je_id}`: {err.detail}")
        lines.append("")

    # Control findings (Close Sentinel).
    if sentinel is not None:
        lines.append("## Control findings")
        lines.append("")
        lines.append(f"_{sentinel.summary_line()}_")
        lines.append("")
        if not sentinel.findings:
            lines.append("All controls passed.")
        else:
            lines.append("| Control | Severity | Entity | Subject | Detail |")
            lines.append("|---------|----------|--------|---------|--------|")
            for finding in sentinel.findings:
                lines.append(
                    f"| {finding.control_id} | {finding.severity.value.upper()} "
                    f"| {finding.entity or 'group'} | {finding.subject} "
                    f"| {finding.detail} |"
                )
        lines.append("")

    close_clean = result.clean and (sentinel is None or sentinel.clean)
    verdict = "CLEAN — ready for review." if close_clean else \
        "NOT CLEAN — resolve flagged items before review."
    lines.append(f"**Close status: {verdict}**")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Sentinel report
# --------------------------------------------------------------------------- #


def sentinel_json(report: SentinelReport) -> dict:
    """Render a sentinel report as a JSON-serializable dict.

    Carries the clean verdict, per-severity counts, and every finding with
    its control id so a pipeline can gate on ``clean`` without re-parsing.
    """
    return {
        "clean": report.clean,
        "summary": report.summary_line(),
        "critical_count": len(report.criticals),
        "warning_count": len(report.warnings),
        "info_count": len(report.infos),
        "findings": [
            {
                "control_id": finding.control_id,
                "severity": finding.severity.value,
                "entity": finding.entity,
                "subject": finding.subject,
                "detail": finding.detail,
            }
            for finding in report.findings
        ],
    }


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #


def write_outputs(
    result: CloseResult,
    out_dir: str | Path,
    sentinel: SentinelReport | None = None,
) -> list[Path]:
    """Write all committed outputs (and optional xlsx) to ``out_dir``.

    Args:
        result: The close result to render.
        out_dir: Destination directory (created if missing).
        sentinel: Optional sentinel report; when given, its findings render
            into the close report and ``sentinel.json`` is also written.

    Returns:
        The list of files written.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def _write(name: str, text: str) -> None:
        path = out / name
        path.write_text(text, encoding="utf-8")
        written.append(path)

    def _write_json(name: str, data: dict) -> None:
        path = out / name
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        written.append(path)

    _write("je_register.md", je_register_markdown(result))
    _write_json("je_register.json", je_register_json(result))
    _write_json("schedules.json", schedules_json(result))
    _write("trial_balance.md", trial_balance_markdown(result))
    _write_json("trial_balance.json", trial_balance_json(result))
    _write("close_report.md", close_report_markdown(result, sentinel=sentinel))
    if sentinel is not None:
        _write_json("sentinel.json", sentinel_json(sentinel))

    xlsx_path = _write_xlsx(result, out)
    if xlsx_path is not None:
        written.append(xlsx_path)

    return written


def _write_xlsx(result: CloseResult, out: Path) -> Path | None:
    """Write an xlsx workbook of the trial balance and register, if possible.

    Returns the path written, or None if openpyxl is unavailable.
    """
    try:
        from openpyxl import Workbook
    except ImportError:  # pragma: no cover - openpyxl is a declared dependency
        return None

    wb = Workbook()
    tb_ws = wb.active
    tb_ws.title = "Trial Balance"
    tb_ws.append(["Entity", "Account", "Debit", "Credit"])
    for entity, account, dr, cr in result.ledger.trial_balance():
        tb_ws.append(
            [entity, _account_name(result, account), dr / 100.0, cr / 100.0]
        )

    je_ws = wb.create_sheet("JE Register")
    je_ws.append(
        [
            "JE ID",
            "Entity",
            "Account",
            "Source Batch",
            "Source Line",
            "Project",
            "Job",
            "Cost",
            "Memo",
            "Debit",
            "Credit",
        ]
    )
    for je in result.register:
        for ln in je.lines:
            je_ws.append(
                [
                    je.je_id,
                    ln.entity,
                    _account_name(result, ln.account),
                    ln.source_batch,
                    ln.source_line,
                    ln.project_code,
                    ln.job_code,
                    ln.cost_code,
                    ln.memo,
                    ln.debit / 100.0,
                    ln.credit / 100.0,
                ]
            )

    path = out / "close_workbook.xlsx"
    wb.save(path)
    return path
