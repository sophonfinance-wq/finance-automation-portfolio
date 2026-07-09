"""Surplus Assurance Loop — a bounded, human-gated remediation loop.

The engine (:mod:`surplus_engine.engine`) computes an authoritative, internally
consistent surplus / ACB roll-forward from cited source facts. The reconciliation
harness (:mod:`surplus_engine.reconcile`) independently re-derives that roll-forward
and proves 200+ named structural identities. Together they are a perfect substrate
for a *control loop*.

In real month-end / year-end work the stored workpapers **drift** from what the
source facts support: a cell is fat-fingered, a roll-forward is stale, an
intercompany elevation is booked without support, an ACB balance is mis-keyed.
This module drives a drifted workpaper set back to full structural consistency
the way a reviewer actually does a roll-forward remediation — one period at a
time, earliest first, locking each period before moving on:

    observe → detect → remediate → re-verify → gate → repeat

Each **turn**:

1. **observe / detect** — run :func:`reconcile` over the current workpapers and
   find the *earliest fiscal period* that still fails any identity.
2. **remediate** — re-derive that period from the cited source facts via the
   engine, book the field-level corrections as journal *adjustments*, and lock
   the period (roll-forward continuity re-seats the next period's opening from
   the locked close).
3. **re-verify** — reconcile again; the loop repeats until every identity across
   every period and tier reconciles, or the **turn budget** is exhausted.

The loop never invents a number: every correction is the engine's own
re-derivation from source, and the final workpaper set is byte-identical to a
clean engine run. It ends at a **human gate** that returns a verdict:

* ``PASS``  — converged, and the booked adjustments are immaterial.
* ``FLAG``  — converged, but material adjustments were booked; a human must
  review *what changed* before sign-off even though it now ties.
* ``FAIL``  — did not converge within the turn budget; escalate to a human.

Everything operates on the *fictional* engine output; no real data.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .engine import EXEMPT_CAP, EntityYearResult, SurplusEngine
from .generate import DEFAULT_SEED, generate_structure
from .reconcile import ReconCheck, reconcile
from .report import attach_fx
from .model import Structure

# Verdicts (mirrors the platform's severity -> verdict gate; doubles as a CLI
# exit code: FAIL is the only non-zero verdict).
PASS = "PASS"
FLAG = "FLAG"
FAIL = "FAIL"

# CAD adjustment magnitude at or below which a converged run is a clean PASS.
# Above it, the run converges but is FLAGged for human review of what changed.
DEFAULT_MATERIALITY_CAD = 1_000.0

# Fields compared when a period is re-derived, so any drift is captured as an
# explicit journal adjustment (dotted paths resolve into the row or its balances).
_TRACKED_FIELDS: Tuple[str, ...] = (
    "opening.exempt_surplus",
    "opening.taxable_surplus",
    "opening.pre_acquisition_capital",
    "opening.acb",
    "closing.exempt_surplus",
    "closing.taxable_surplus",
    "closing.pre_acquisition_capital",
    "closing.acb",
    "current_exempt_addition",
    "current_taxable_addition",
    "elevated_exempt",
    "elevated_taxable",
    "capital_contribution",
    "return_of_capital",
    "distribution",
    "deemed_gain_on_negative_acb",
)

# A field diff smaller than this (functional currency) is rounding, not drift.
_FIELD_EPS = 0.005


# --------------------------------------------------------------------------- #
# Fault model — the drift injected into a stored workpaper set.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Mutation:
    """One field-level edit applied to a stored workpaper cell."""

    field: str          # dotted path, e.g. "closing.exempt_surplus"
    op: str             # "add" | "set"
    operand: float

    def apply(self, row: EntityYearResult) -> None:
        old = _get_field(row, self.field)
        new = self.operand if self.op == "set" else round(old + self.operand, 2)
        _set_field(row, self.field, new)


@dataclass(frozen=True)
class Fault:
    """A drift scenario with a root-cause story and the control that catches it."""

    id: str
    title: str          # human root cause
    entity: str
    year: int
    mutations: Tuple[Mutation, ...]
    control: str        # the structural identity/identities expected to fire


# The built-in contamination profile used by ``--demo``. Targets are chosen
# against the default seeded structure (2021-2024) so each fault genuinely
# breaks its named identity; ``tests/test_loop.py`` asserts that it does.
DEMO_FAULTS: Tuple[Fault, ...] = (
    Fault(
        id="F1-MISKEY-CLOSE",
        title="Fat-fingered closing cell: exempt surplus overstated on the 2021 workpaper",
        entity="CEDAR_MEZZ",
        year=2021,
        mutations=(Mutation("closing.exempt_surplus", "add", 50_000.00),),
        control="exempt_conservation + continuity_exempt",
    ),
    Fault(
        id="F2-UNSUPPORTED-ELEVATION",
        title="Intercompany elevation booked at the fund with no subsidiary distribution to support it",
        entity="MAPLE_FUND",
        year=2022,
        mutations=(
            Mutation("elevated_exempt", "add", 8_000.00),
            Mutation("closing.exempt_surplus", "add", 8_000.00),
        ),
        control="elevation_exempt",
    ),
    Fault(
        id="F3-ACB-MISKEY",
        title="Mis-keyed ACB balance on the 2023 mezzanine workpaper",
        entity="CEDAR_MEZZ",
        year=2023,
        mutations=(Mutation("closing.acb", "add", 15_000.00),),
        control="acb_conservation + continuity_acb",
    ),
)


# --------------------------------------------------------------------------- #
# Journal records.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Adjustment:
    """One field correction booked when a period is re-derived from source."""

    entity: str
    year: int
    currency: str
    field: str
    from_value: float
    to_value: float
    rate_to_cad: float

    @property
    def delta(self) -> float:
        return round(self.to_value - self.from_value, 2)

    @property
    def delta_cad(self) -> float:
        return round(abs(self.delta) * self.rate_to_cad, 2)


@dataclass(frozen=True)
class BreakSnapshot:
    """A lightweight, render-friendly copy of a reconciliation break."""

    name: str
    entity: str
    year: Optional[int]
    delta: float

    @classmethod
    def of(cls, c: ReconCheck) -> "BreakSnapshot":
        return cls(c.name, c.entity, c.year, c.delta)


@dataclass(frozen=True)
class Turn:
    """One remediation turn: settle and lock the earliest failing period."""

    index: int
    year_settled: int
    breaks_before: Tuple[BreakSnapshot, ...]
    adjustments: Tuple[Adjustment, ...]
    breaks_after_count: int

    @property
    def cleared(self) -> int:
        return len(self.breaks_before) - self.breaks_after_count


@dataclass(frozen=True)
class LoopJournal:
    """The full record of a loop run — deterministic and render-ready."""

    start_year: int
    end_year: int
    seed: int
    checks_total: int
    faults: Tuple[Fault, ...]
    initial_breaks: Tuple[BreakSnapshot, ...]
    turns: Tuple[Turn, ...]
    converged: bool
    budget: int
    materiality_cad: float
    verdict: str

    @property
    def total_adjustments(self) -> int:
        return sum(len(t.adjustments) for t in self.turns)

    @property
    def total_adjustment_cad(self) -> float:
        return round(
            sum(a.delta_cad for t in self.turns for a in t.adjustments), 2
        )

    @property
    def periods_locked(self) -> Tuple[int, ...]:
        return tuple(t.year_settled for t in self.turns)


# --------------------------------------------------------------------------- #
# Field access helpers.
# --------------------------------------------------------------------------- #
def _resolve(row: EntityYearResult, path: str):
    parts = path.split(".")
    if len(parts) == 1:
        return row, parts[0]
    obj = row
    for p in parts[:-1]:
        obj = getattr(obj, p)
    return obj, parts[-1]


def _get_field(row: EntityYearResult, path: str) -> float:
    obj, name = _resolve(row, path)
    return float(getattr(obj, name))


def _set_field(row: EntityYearResult, path: str, value: float) -> None:
    obj, name = _resolve(row, path)
    setattr(obj, name, round(float(value), 2))


# --------------------------------------------------------------------------- #
# Loop.
# --------------------------------------------------------------------------- #
def run_authoritative(
    structure: Structure, years: List[int], exempt_cap: float = EXEMPT_CAP
) -> List[EntityYearResult]:
    """Compute the authoritative, source-derived workpaper set (with FX attached)."""
    results = SurplusEngine(structure, exempt_cap_fraction=exempt_cap).run(years)
    attach_fx(results, structure)
    return results


def apply_faults(
    workpapers: List[EntityYearResult], faults: Tuple[Fault, ...]
) -> List[EntityYearResult]:
    """Return a drifted copy of ``workpapers`` with ``faults`` applied in place."""
    drifted = copy.deepcopy(workpapers)
    by_key = {(r.entity, r.year): r for r in drifted}
    for fault in faults:
        row = by_key.get((fault.entity, fault.year))
        if row is None:
            raise KeyError(f"fault {fault.id}: no workpaper for {fault.entity} FY{fault.year}")
        for mut in fault.mutations:
            mut.apply(row)
    return drifted


def _settle_year(
    wp_by_key: Dict[Tuple[str, int], EntityYearResult],
    auth_by_key: Dict[Tuple[str, int], EntityYearResult],
    year: int,
    entities: List[str],
    structure: Structure,
) -> List[Adjustment]:
    """Re-derive every entity's ``year`` row from source; book field corrections."""
    adjustments: List[Adjustment] = []
    for code in sorted(entities):
        key = (code, year)
        cur = wp_by_key.get(key)
        auth = auth_by_key.get(key)
        if cur is None or auth is None:
            continue
        rate = structure.fx.rate(year, structure.entities[code].currency)
        for path in _TRACKED_FIELDS:
            was = _get_field(cur, path)
            now = _get_field(auth, path)
            if abs(now - was) > _FIELD_EPS:
                adjustments.append(
                    Adjustment(code, year, structure.entities[code].currency,
                               path, round(was, 2), round(now, 2), rate)
                )
        # Lock the period: replace the drifted row with the authoritative one.
        wp_by_key[key] = copy.deepcopy(auth)
    # Order adjustments deterministically for stable reports.
    adjustments.sort(key=lambda a: (a.entity, a.field))
    return adjustments


def assurance_loop(
    structure: Structure,
    years: List[int],
    faults: Tuple[Fault, ...] = (),
    budget: Optional[int] = None,
    exempt_cap: float = EXEMPT_CAP,
    materiality_cad: float = DEFAULT_MATERIALITY_CAD,
    seed: int = DEFAULT_SEED,
) -> LoopJournal:
    """Run the assurance loop and return a :class:`LoopJournal`.

    Parameters
    ----------
    structure, years:
        The fictional structure and the fiscal-year range to reconcile.
    faults:
        Drift to inject into the stored workpapers before the loop runs. Empty
        means "reconcile a clean set" (the loop should find nothing to do).
    budget:
        Maximum remediation turns. Defaults to ``len(years) + 2`` — generous
        enough to settle every period once and confirm convergence.
    materiality_cad:
        CAD adjustment magnitude separating a clean ``PASS`` from a ``FLAG``.
    """
    years = sorted(years)
    if budget is None:
        budget = len(years) + 2

    authoritative = run_authoritative(structure, years, exempt_cap)
    auth_by_key = {(r.entity, r.year): r for r in authoritative}

    workpapers = apply_faults(authoritative, faults)
    wp_by_key = {(r.entity, r.year): r for r in workpapers}
    entities = list(structure.entities.keys())

    def current_report():
        return reconcile(list(wp_by_key.values()), structure)

    initial = current_report()
    initial_breaks = tuple(BreakSnapshot.of(c) for c in initial.breaks)

    turns: List[Turn] = []
    converged = initial.ok
    report = initial
    while not report.ok and len(turns) < budget:
        breaks_before = tuple(BreakSnapshot.of(c) for c in report.breaks)
        earliest = min(c.year for c in report.breaks if c.year is not None)
        adjustments = _settle_year(wp_by_key, auth_by_key, earliest, entities, structure)
        report = current_report()
        turns.append(
            Turn(
                index=len(turns) + 1,
                year_settled=earliest,
                breaks_before=breaks_before,
                adjustments=tuple(adjustments),
                breaks_after_count=len(report.breaks),
            )
        )
    converged = report.ok

    total_cad = round(sum(a.delta_cad for t in turns for a in t.adjustments), 2)
    verdict = _verdict(converged, total_cad, materiality_cad)

    return LoopJournal(
        start_year=years[0],
        end_year=years[-1],
        seed=seed,
        checks_total=len(initial.checks),
        faults=tuple(faults),
        initial_breaks=initial_breaks,
        turns=tuple(turns),
        converged=converged,
        budget=budget,
        materiality_cad=materiality_cad,
        verdict=verdict,
    )


def _verdict(converged: bool, total_adjustment_cad: float, materiality_cad: float) -> str:
    if not converged:
        return FAIL
    if total_adjustment_cad > materiality_cad:
        return FLAG
    return PASS


def verdict_exit_code(verdict: str) -> int:
    """Map a verdict to a process exit code (FAIL is the only failure)."""
    return 1 if verdict == FAIL else 0


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[List[str]]):
    import argparse

    p = argparse.ArgumentParser(
        prog="surplus_engine.loop",
        description="Surplus Assurance Loop: drive drifted workpapers back to a "
        "clean structural tie-out, one locked period at a time (fictional data).",
    )
    p.add_argument("--start", type=int, default=2021, help="first fiscal year (inclusive)")
    p.add_argument("--end", type=int, default=2024, help="last fiscal year (inclusive)")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed (reproducibility)")
    p.add_argument("--exempt-cap", type=float, default=EXEMPT_CAP, help="exempt-distribution cap (0..1)")
    p.add_argument("--demo", action="store_true", help="inject the built-in workpaper-drift profile")
    p.add_argument("--budget", type=int, default=None, help="max remediation turns (default: years+2)")
    p.add_argument("--materiality", type=float, default=DEFAULT_MATERIALITY_CAD,
                   help="CAD adjustment threshold separating PASS from FLAG")
    p.add_argument("--out", type=str, default=None, help="directory for Markdown + HTML reports")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main. Returns a process exit code (FAIL -> 1, else 0)."""
    import sys
    from pathlib import Path

    from .loop_report import render_html_document, render_markdown

    args = _parse_args(argv)
    if args.end < args.start:
        print("error: --end must be >= --start", file=sys.stderr)
        return 2

    structure = generate_structure(args.start, args.end, seed=args.seed)
    years = list(range(args.start, args.end + 1))
    faults = DEMO_FAULTS if args.demo else ()

    journal = assurance_loop(
        structure, years, faults=faults, budget=args.budget,
        exempt_cap=args.exempt_cap, materiality_cad=args.materiality, seed=args.seed,
    )

    md = render_markdown(journal, structure)
    try:
        print(md)
    except UnicodeEncodeError:  # pragma: no cover - console encoding fallback
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(md.encode(enc, errors="replace").decode(enc) + "\n")

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "assurance_loop_report.md").write_text(md, encoding="utf-8")
        (out_dir / "assurance_loop.html").write_text(
            render_html_document(journal, structure), encoding="utf-8"
        )
        print(f"\nWrote assurance_loop_report.md and assurance_loop.html to {out_dir.resolve()}")

    return verdict_exit_code(journal.verdict)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
