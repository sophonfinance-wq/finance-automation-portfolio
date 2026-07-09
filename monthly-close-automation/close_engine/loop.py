"""Autonomous Close Loop — a human-out-of-the-loop remediation controller.

The Close Sentinel (:mod:`close_engine.sentinel`) is a *read-only* detector: ten
controls re-derive their expectations from the seeded sub-ledgers and report
findings, but nothing remediates — today a human works the exception list and
re-runs. This module closes that loop and takes the operator out of it, without
pretending the controls no longer matter.

The seeded sub-ledger is the **system of record**: the controls already re-derive
against it, so ``CloseEngine(dataset).run()`` is the authoritative close. Given a
*drifted* posted register (a dropped intercompany leg, a missing accrual, a
one-cent shadow tamper, a rounding drift), each turn the loop:

    observe → detect → remediate → re-verify → gate → repeat

1. **observe / detect** — run the sentinel; find the earliest recurring-entry
   *category* whose posted lines disagree with the authoritative re-derivation.
2. **remediate** — resync that category to the authoritative posting, booking the
   line-level movement as adjustments, and rebuild the trial balance.
3. **re-verify** — re-run the sentinel; the loop repeats until every
   auto-remediable control is silent, or a turn budget is exhausted.

"Autonomous" does not mean "no gate" — it means the gate is a deterministic,
logged policy rather than a person. Two classes of finding are things the loop
has **no authority** to act on unilaterally, so it does not:

* **Quarantine** (``C10`` locked-period mutation): a signed-off prior period was
  altered. The loop will not silently overwrite a locked artifact — it holds and
  logs it, and still posts the current period.
* **Halt** (``C1`` opening trial balance out of balance): the opening balances are
  an upstream carryforward the loop cannot invent. It refuses to post on a broken
  opening rather than fabricate one.

The loop never invents a number: every correction is the engine's own
re-derivation from the sub-ledger of record. It ends at a verdict that doubles as
a CI exit code:

* ``AUTO-POSTED``            — clean; posted autonomously, nothing held.
* ``AUTO-POSTED (PARTIAL)``  — posted autonomously; some scope quarantined + logged.
* ``HALTED``                 — could not certify a postable close; escalated.

All data is fictional and seeded.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from . import money
from .engine import CloseEngine, CloseResult
from .generate import Dataset, generate_dataset
from .model import JournalEntry, Ledger
from .sentinel import Severity, run_sentinel
from .sentinel.findings import Finding, SentinelReport

# Verdicts (also the CLI exit code: HALTED is the only failure).
AUTO_POSTED = "AUTO-POSTED"
PARTIAL = "AUTO-POSTED (PARTIAL)"
HALTED = "HALTED"

# Recurring-entry categories in the engine's own posting order.
CATEGORY_ORDER: tuple[str, ...] = (
    "prepaid_amortization",
    "depreciation",
    "deferred_rent_cam",
    "mgmt_fee_accrual",
    "note_interest",
    "gna_allocation",
    "insurance_allocation",
)

# Controls the loop can remediate by resyncing a category to the authoritative
# re-derivation (in-period recurring-entry drift). C7 escalates at WARN.
AUTO_REMEDIABLE = frozenset({"C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"})
# A tampered, signed-off prior period: held and logged, never auto-overwritten.
QUARANTINE_CONTROLS = frozenset({"C10"})
# A broken opening carryforward: the loop refuses to post rather than invent it.
HALT_CONTROLS = frozenset({"C1"})


# --------------------------------------------------------------------------- #
# Journal records.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Adjustment:
    """One (entity, account) movement booked when a category is resynced."""

    category: str
    entity: str
    account: str
    from_debit: int
    from_credit: int
    to_debit: int
    to_credit: int

    @property
    def delta_debit(self) -> int:
        return self.to_debit - self.from_debit

    @property
    def delta_credit(self) -> int:
        return self.to_credit - self.from_credit

    @property
    def magnitude_cents(self) -> int:
        """Gross movement (max of the debit/credit swing), in cents."""
        return max(abs(self.delta_debit), abs(self.delta_credit))


@dataclass(frozen=True)
class BreakSnapshot:
    """A render-friendly copy of a sentinel finding."""

    control_id: str
    severity: str
    entity: Optional[str]
    subject: str

    @classmethod
    def of(cls, f: Finding) -> "BreakSnapshot":
        return cls(f.control_id, f.severity.value, f.entity, f.subject)


@dataclass(frozen=True)
class Turn:
    """One remediation turn: resync the earliest drifted category to source."""

    index: int
    category: str
    controls_cleared: tuple[str, ...]
    adjustments: tuple[Adjustment, ...]
    criticals_before: int
    criticals_after: int

    @property
    def cleared(self) -> int:
        return self.criticals_before - self.criticals_after


@dataclass(frozen=True)
class LoopJournal:
    """The full record of an autonomous-close run — deterministic, render-ready."""

    period: str
    seed: int
    faults: tuple[str, ...]
    initial_findings: tuple[BreakSnapshot, ...]
    turns: tuple[Turn, ...]
    quarantined: tuple[BreakSnapshot, ...]
    halted_on: tuple[BreakSnapshot, ...]
    budget: int
    materiality_cents: int
    verdict: str

    @property
    def total_adjustments(self) -> int:
        return sum(len(t.adjustments) for t in self.turns)

    @property
    def total_adjustment_cents(self) -> int:
        return sum(a.magnitude_cents for t in self.turns for a in t.adjustments)

    @property
    def categories_resynced(self) -> tuple[str, ...]:
        return tuple(t.category for t in self.turns)

    @property
    def posted(self) -> bool:
        return self.verdict in (AUTO_POSTED, PARTIAL)


# --------------------------------------------------------------------------- #
# Ledger / register helpers.
# --------------------------------------------------------------------------- #
def _rebuild_ledger(dataset: Dataset, register: list[JournalEntry]) -> Ledger:
    """Recompute the post-close trial balance from opening + a register.

    Uses the unchecked opening-load path to accumulate balances so an
    intermediate, mid-remediation register never raises on the tie control;
    the sentinel's C1 gate is what independently re-verifies balance.
    """
    ledger = Ledger(dataset.coa)
    ledger.load_opening(dataset.opening_tb)
    ledger.load_opening(line for je in register for line in je.lines)
    return ledger


def _category_lines(register: list[JournalEntry], category: str):
    """Aggregate a category's posted lines to ``{(entity, account): (dr, cr)}``."""
    agg: dict[tuple[str, str], tuple[int, int]] = {}
    for je in register:
        if je.category != category:
            continue
        for line in je.lines:
            key = (line.entity, line.account)
            dr, cr = agg.get(key, (0, 0))
            agg[key] = (dr + line.debit, cr + line.credit)
    return agg


def _differing_categories(
    posted: CloseResult, authoritative: CloseResult
) -> list[str]:
    """Categories whose posted aggregation differs from the authoritative one."""
    out: list[str] = []
    for category in CATEGORY_ORDER:
        if _category_lines(posted.register, category) != _category_lines(
            authoritative.register, category
        ):
            out.append(category)
    return out


def _resync_category(
    dataset: Dataset,
    posted: CloseResult,
    authoritative: CloseResult,
    category: str,
) -> list[Adjustment]:
    """Replace a category's posted entries with the authoritative ones.

    Books the (entity, account) movement as adjustments, swaps the entries, and
    rebuilds the trial balance so the next observe sees a consistent close.
    """
    before = _category_lines(posted.register, category)
    after = _category_lines(authoritative.register, category)
    adjustments: list[Adjustment] = []
    for key in sorted(set(before) | set(after)):
        f_dr, f_cr = before.get(key, (0, 0))
        t_dr, t_cr = after.get(key, (0, 0))
        if (f_dr, f_cr) != (t_dr, t_cr):
            entity, account = key
            adjustments.append(
                Adjustment(category, entity, account, f_dr, f_cr, t_dr, t_cr)
            )

    kept = [je for je in posted.register if je.category != category]
    restored = [copy.deepcopy(je) for je in authoritative.register if je.category == category]
    new_register = kept + restored
    # Stable order: engine category order, then je_id.
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    new_register.sort(key=lambda je: (order.get(je.category, 99), je.je_id))
    posted.register = new_register
    posted.ledger = _rebuild_ledger(dataset, posted.register)
    return adjustments


# --------------------------------------------------------------------------- #
# Loop.
# --------------------------------------------------------------------------- #
def _blocking(report: SentinelReport) -> list[Finding]:
    """Auto-remediable findings that still demand work (CRITICAL, or C7 WARN)."""
    out = [f for f in report.criticals if f.control_id in AUTO_REMEDIABLE]
    out += [
        f for f in report.warnings
        if f.control_id in AUTO_REMEDIABLE and f.severity is Severity.WARN
    ]
    return out


def _control_counts(findings: list[Finding]) -> dict[str, int]:
    """Count findings per control id."""
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.control_id] = counts.get(f.control_id, 0) + 1
    return counts


def autonomous_close_loop(
    dataset: Dataset,
    posted: CloseResult,
    *,
    locked: dict[str, str] | None = None,
    budget: int | None = None,
    materiality_cents: int = 100_00,
) -> LoopJournal:
    """Drive a drifted posted close back to a certifiable state, autonomously.

    Args:
        dataset: The seeded source of record the close is built from.
        posted: The (possibly drifted) posted close to remediate — mutated in place.
        locked: Optional ``{period: register_hash}`` of signed-off periods (C10).
        budget: Max remediation turns (default: one per recurring category + 2).
        materiality_cents: Threshold above which auto-adjustments are flagged as
            material in the report (informational; does not change the verdict).
    """
    authoritative = CloseEngine(dataset).run()
    if budget is None:
        budget = len(CATEGORY_ORDER) + 2

    initial = run_sentinel(dataset, posted, locked=locked)
    initial_findings = tuple(BreakSnapshot.of(f) for f in initial.findings)

    turns: list[Turn] = []
    report = initial
    while len(turns) < budget:
        blocking = _blocking(report)
        if not blocking:
            break
        diffs = _differing_categories(posted, authoritative)
        if not diffs:
            break  # blocking findings we cannot resolve by resyncing — halt below
        category = diffs[0]
        before_counts = _control_counts(blocking)
        criticals_before = len(report.criticals)
        adjustments = _resync_category(dataset, posted, authoritative, category)
        report = run_sentinel(dataset, posted, locked=locked)
        after_counts = _control_counts(_blocking(report))
        # A control "progressed" this turn when its finding count strictly fell.
        progressed = tuple(
            sorted(c for c, n in before_counts.items() if after_counts.get(c, 0) < n)
        )
        turns.append(
            Turn(
                index=len(turns) + 1,
                category=category,
                controls_cleared=progressed,
                adjustments=tuple(adjustments),
                criticals_before=criticals_before,
                criticals_after=len(report.criticals),
            )
        )

    final = report
    quarantined = tuple(
        BreakSnapshot.of(f) for f in final.findings if f.control_id in QUARANTINE_CONTROLS
    )
    halted_on = tuple(
        BreakSnapshot.of(f) for f in final.findings if f.control_id in HALT_CONTROLS
    )
    verdict = _verdict(final, len(turns) < budget)

    return LoopJournal(
        period=posted.period,
        seed=posted.seed,
        faults=(),  # filled by demo_setup when applicable
        initial_findings=initial_findings,
        turns=tuple(turns),
        quarantined=quarantined,
        halted_on=halted_on,
        budget=budget,
        materiality_cents=materiality_cents,
        verdict=verdict,
    )


def _verdict(final: SentinelReport, within_budget: bool) -> str:
    """Map the final sentinel state to a posting verdict."""
    remaining = _blocking(final)
    halt = [f for f in final.findings if f.control_id in HALT_CONTROLS]
    if halt or remaining or not within_budget:
        return HALTED
    if any(f.control_id in QUARANTINE_CONTROLS for f in final.findings):
        return PARTIAL
    return AUTO_POSTED


def verdict_exit_code(verdict: str) -> int:
    """Map a verdict to a process exit code (HALTED is the only failure)."""
    return 1 if verdict == HALTED else 0


# --------------------------------------------------------------------------- #
# Demo: a drifted close plus a tampered locked prior.
# --------------------------------------------------------------------------- #
# Result-stage faults on distinct categories (so they compose cleanly), each
# mapped to the control that catches it, plus a locked-period tamper (C10).
DEMO_RESULT_FAULTS: tuple[str, ...] = (
    "interco_one_sided",       # C2  -> note_interest
    "missing_recurring_entry", # C3  -> mgmt_fee_accrual
    "rounded_total_leg",       # C8  -> gna_allocation
    "shadow_tamper",           # C9  -> prepaid_amortization
)
DEMO_LOCKED_FAULT = "prior_period_mutation"  # C10 -> quarantined


def _prior_period(period: str) -> str:
    from .generate import period_index

    idx = period_index(period) - 1
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def demo_setup(period: str, seed: int):
    """Build a drifted posted close + a tampered locked prior for the demo.

    Returns ``(dataset, posted, locked, fault_names)`` where ``dataset`` is the
    clean source of record, ``posted`` is a deep-copied clean close with the
    result-stage faults applied, and ``locked`` carries a mutated prior-period
    hash the period-lock control (C10) will catch.
    """
    from .faults import FAULTS
    from .sentinel import lock_register

    dataset = generate_dataset(period, seed=seed)
    posted = CloseEngine(dataset).run()
    for name in DEMO_RESULT_FAULTS:
        injector, _control = FAULTS[name]
        posted, _desc = injector(posted)

    prior = _prior_period(period)
    prior_clean = CloseEngine(generate_dataset(prior, seed=seed)).run()
    mutate, _control = FAULTS[DEMO_LOCKED_FAULT]
    mutated, _desc = mutate(prior_clean)
    locked = {prior: lock_register(mutated)}

    fault_names = DEMO_RESULT_FAULTS + (DEMO_LOCKED_FAULT,)
    return dataset, posted, locked, fault_names


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[list[str]]):
    import argparse

    p = argparse.ArgumentParser(
        prog="close_engine.loop",
        description="Autonomous Close Loop: drive a drifted close back to a "
        "certifiable, auto-posted state — quarantining what it cannot certify "
        "(fictional data).",
    )
    p.add_argument("--period", default="2026-03", help="close period YYYY-MM")
    p.add_argument("--seed", type=int, default=2026, help="synthetic-data seed")
    p.add_argument("--demo", action="store_true",
                   help="inject the built-in drift profile + a tampered locked prior")
    p.add_argument("--budget", type=int, default=None, help="max remediation turns")
    p.add_argument("--out", default=None, help="directory for Markdown + HTML reports")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. Returns a process exit code (HALTED -> 1, else 0)."""
    import sys
    from dataclasses import replace
    from pathlib import Path

    from .loop_report import render_html_document, render_markdown

    args = _parse_args(argv)
    if args.demo:
        dataset, posted, locked, fault_names = demo_setup(args.period, args.seed)
    else:
        dataset = generate_dataset(args.period, seed=args.seed)
        posted = CloseEngine(dataset).run()
        locked, fault_names = None, ()

    journal = autonomous_close_loop(dataset, posted, locked=locked, budget=args.budget)
    journal = replace(journal, faults=fault_names)

    md = render_markdown(journal)
    try:
        print(md)
    except UnicodeEncodeError:  # pragma: no cover - console encoding fallback
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(md.encode(enc, errors="replace").decode(enc) + "\n")

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "autonomous_close_loop.md").write_text(md, encoding="utf-8")
        (out_dir / "autonomous_close_loop.html").write_text(
            render_html_document(journal), encoding="utf-8"
        )
        print(f"\nWrote autonomous_close_loop.md and autonomous_close_loop.html to {out_dir.resolve()}")

    return verdict_exit_code(journal.verdict)


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
