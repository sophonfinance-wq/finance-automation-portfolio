"""Reconciliation Assurance Loop — materiality-gated drift remediation.

The reconciliation engine (:mod:`recon_engine.engine`) classifies every account
against its source statement; the seeded generator (:mod:`recon_engine.generate`)
is the deterministic system of record. Between runs, the *stored* books can
drift: a GL balance is fat-fingered, a source statement goes missing from the
package, an active account is mis-marked dormant. Each looks plausible on its
own — the reconciliation silently reports different flags than the source
supports.

This loop drives a drifted dataset back to the source of record:

    observe → detect → remediate → re-verify → gate → repeat

1. **observe / detect** — reconcile the current dataset and compare every
   account's outcome (presence, classification, variance, source) against the
   *baseline*: the reconciliation of the pristine seeded dataset. Any
   difference is a deviation. (The baseline is not "all clean" — the seeded
   scenario intentionally contains flags; the loop restores *fidelity to
   source*, it does not zero out genuine reconciling items.)
2. **remediate** — take the lowest-numbered deviating account and resync every
   record it owns (GL row, bank statement, lender statement, dormant marker)
   to the pristine dataset, booking each field change as an adjustment.
3. **re-verify** — reconcile again; repeat until no account deviates from the
   baseline, or the turn budget is exhausted.

The gate is **materiality-based** (a third policy flavor beside the surplus
loop's human gate and the close loop's autonomy policy):

* ``PASS`` — converged; total corrections at or below the materiality
  threshold. Clean to file.
* ``FLAG`` — converged, but the corrections were material; a reviewer sees
  *what moved* before the package ships.
* ``FAIL`` — did not converge within the turn budget; escalate.

The loop never invents a number: every correction is a restoration of the
seeded record, and the settled reconciliation is identical to a pristine run.
All data is fictional.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import MATERIALITY_THRESHOLD
from .engine import ReconResult, reconcile
from .generate import DEFAULT_SEED, SyntheticDataset, generate_dataset

PASS = "PASS"
FLAG = "FLAG"
FAIL = "FAIL"


# --------------------------------------------------------------------------- #
# Journal records.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Adjustment:
    """One field restoration booked when an account is resynced to source."""

    account_number: str
    record: str            # "gl" | "bank" | "lender"
    field: str
    from_value: object
    to_value: object

    @property
    def magnitude(self) -> float:
        """Monetary movement, when both sides are numeric (else 0)."""
        try:
            return abs(float(self.to_value) - float(self.from_value))
        except (TypeError, ValueError):
            return 0.0


@dataclass(frozen=True)
class Deviation:
    """One account whose outcome disagrees with the baseline reconciliation."""

    account_number: str
    expected: str          # baseline outcome, rendered compactly
    actual: str            # current outcome


@dataclass(frozen=True)
class Turn:
    """One remediation turn: resync one deviating account to source."""

    index: int
    account_number: str
    adjustments: Tuple[Adjustment, ...]
    deviations_before: int
    deviations_after: int


@dataclass(frozen=True)
class LoopJournal:
    """The full, deterministic record of a loop run."""

    seed: int
    threshold: float
    faults: Tuple[str, ...]
    initial_deviations: Tuple[Deviation, ...]
    turns: Tuple[Turn, ...]
    converged: bool
    budget: int
    materiality: float
    verdict: str

    @property
    def total_adjustments(self) -> int:
        return sum(len(t.adjustments) for t in self.turns)

    @property
    def total_correction(self) -> float:
        return round(sum(a.magnitude for t in self.turns for a in t.adjustments), 2)

    @property
    def accounts_resynced(self) -> Tuple[str, ...]:
        return tuple(t.account_number for t in self.turns)


# --------------------------------------------------------------------------- #
# Sensor: per-account outcome fingerprints vs the baseline.
# --------------------------------------------------------------------------- #
def _outcomes(result: ReconResult) -> Dict[str, str]:
    """``{account_number: compact outcome fingerprint}`` for every line."""
    out: Dict[str, str] = {}
    for ln in result.all_active_lines:
        out[ln.account_number] = (
            f"{ln.classification} var={ln.variance:+.2f} src={ln.source_label}"
        )
    for ln in result.skipped_lines:
        out[ln.account_number] = "skipped"
    return out


def deviations(
    current: ReconResult, baseline: ReconResult
) -> List[Deviation]:
    """Accounts whose current outcome differs from the baseline outcome."""
    cur, base = _outcomes(current), _outcomes(baseline)
    out: List[Deviation] = []
    for acct in sorted(set(cur) | set(base)):
        expected = base.get(acct, "absent")
        actual = cur.get(acct, "absent")
        if expected != actual:
            out.append(Deviation(acct, expected, actual))
    return out


# --------------------------------------------------------------------------- #
# Authority: resync one account's records to the pristine dataset.
# --------------------------------------------------------------------------- #
def _index(records, acct: str):
    for i, r in enumerate(records):
        if r.account_number == acct:
            return i
    return None


def _resync_records(kind: str, current: list, pristine: list, acct: str,
                    adjustments: List[Adjustment]) -> None:
    """Restore ``acct``'s record in ``current`` to match ``pristine``."""
    ci, pi = _index(current, acct), _index(pristine, acct)
    if pi is None:
        if ci is not None:  # record should not exist — remove it
            adjustments.append(Adjustment(acct, kind, "(record)", "present", "removed"))
            del current[ci]
        return
    truth = pristine[pi]
    if ci is None:  # record was dropped from the package — restore it
        adjustments.append(Adjustment(acct, kind, "(record)", "missing", "restored"))
        current.append(truth)
        return
    drifted = current[ci]
    for f in dataclasses.fields(truth):
        was, now = getattr(drifted, f.name), getattr(truth, f.name)
        if was != now:
            adjustments.append(Adjustment(acct, kind, f.name, was, now))
    current[ci] = truth


def resync_account(
    dataset: SyntheticDataset, pristine: SyntheticDataset, acct: str
) -> List[Adjustment]:
    """Restore every record ``acct`` owns to the source of record."""
    adjustments: List[Adjustment] = []
    _resync_records("gl", dataset.gl_records, pristine.gl_records, acct, adjustments)
    _resync_records("bank", dataset.bank_statements, pristine.bank_statements, acct, adjustments)
    _resync_records("lender", dataset.lender_statements, pristine.lender_statements, acct, adjustments)
    return adjustments


# --------------------------------------------------------------------------- #
# Demo drift: three realistic faults on baseline-clean accounts.
# --------------------------------------------------------------------------- #
def demo_setup(seed: int = DEFAULT_SEED, threshold: float = MATERIALITY_THRESHOLD):
    """Build (pristine, drifted, fault descriptions) for the demo.

    Faults target accounts that reconcile *clean* in the baseline, so every
    deviation the loop reports is genuinely injected drift — not one of the
    scenario's intentional reconciling items.
    """
    pristine = generate_dataset(seed)
    baseline = reconcile(pristine, threshold=threshold)
    clean = [ln for ln in baseline.all_active_lines if ln.classification == "clean"]
    clean_cash = [ln for ln in clean if ln.account_type == "cash"]
    clean_debt = [ln for ln in clean if ln.account_type == "debt"]
    if len(clean_cash) < 1 or len(clean_debt) < 2:
        raise RuntimeError("seeded scenario lacks enough clean accounts for the demo")

    drifted = generate_dataset(seed)
    faults: List[str] = []

    # F1 — fat-fingered GL balance on a clean cash account (spurious flag).
    acct = clean_cash[0].account_number
    i = _index(drifted.gl_records, acct)
    rec = drifted.gl_records[i]
    drifted.gl_records[i] = dataclasses.replace(
        rec, gl_balance=round(rec.gl_balance + 4_830.25, 2)
    )
    faults.append(f"F1 {acct}: GL balance fat-fingered +4,830.25 (spurious flag)")

    # F2 — lender statement dropped from the package (no-source flag).
    acct = clean_debt[0].account_number
    i = _index(drifted.lender_statements, acct)
    del drifted.lender_statements[i]
    faults.append(f"F2 {acct}: lender statement missing from the package")

    # F3 — active account mis-marked dormant (coverage silently lost).
    acct = clean_debt[1].account_number
    i = _index(drifted.gl_records, acct)
    drifted.gl_records[i] = dataclasses.replace(drifted.gl_records[i], dormant=True)
    faults.append(f"F3 {acct}: active account mis-marked dormant (dropped from scope)")

    return pristine, drifted, tuple(faults)


# --------------------------------------------------------------------------- #
# Loop.
# --------------------------------------------------------------------------- #
def assurance_loop(
    dataset: SyntheticDataset,
    *,
    seed: int = DEFAULT_SEED,
    threshold: float = MATERIALITY_THRESHOLD,
    budget: Optional[int] = None,
    materiality: float = MATERIALITY_THRESHOLD,
    faults: Tuple[str, ...] = (),
) -> LoopJournal:
    """Drive ``dataset`` back to fidelity with the seeded source of record."""
    pristine = generate_dataset(seed)
    baseline = reconcile(pristine, threshold=threshold)
    if budget is None:
        budget = len(pristine.gl_records) + 2

    devs = deviations(reconcile(dataset, threshold=threshold), baseline)
    initial = tuple(devs)

    turns: List[Turn] = []
    while devs and len(turns) < budget:
        acct = devs[0].account_number
        adjustments = resync_account(dataset, pristine, acct)
        after = deviations(reconcile(dataset, threshold=threshold), baseline)
        turns.append(
            Turn(
                index=len(turns) + 1,
                account_number=acct,
                adjustments=tuple(adjustments),
                deviations_before=len(devs),
                deviations_after=len(after),
            )
        )
        devs = after

    converged = not devs
    total = round(sum(a.magnitude for t in turns for a in t.adjustments), 2)
    if not converged:
        verdict = FAIL
    elif total > materiality:
        verdict = FLAG
    else:
        verdict = PASS

    return LoopJournal(
        seed=seed,
        threshold=threshold,
        faults=faults,
        initial_deviations=initial,
        turns=tuple(turns),
        converged=converged,
        budget=budget,
        materiality=materiality,
        verdict=verdict,
    )


def verdict_exit_code(verdict: str) -> int:
    """FAIL is the only process failure."""
    return 1 if verdict == FAIL else 0


# --------------------------------------------------------------------------- #
# Markdown report.
# --------------------------------------------------------------------------- #
_BLURB = {
    PASS: "Converged; corrections immaterial — clean to file.",
    FLAG: "Converged, but material corrections were booked — a reviewer sees "
    "what moved before the package ships.",
    FAIL: "Did not converge within the turn budget — escalate.",
}


def render_markdown(journal: LoopJournal) -> str:
    mark = {PASS: "✅", FLAG: "⚑", FAIL: "❌"}[journal.verdict]
    out: List[str] = []
    out.append("# Reconciliation Assurance Loop [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional data. The loop restores a *drifted* reconciliation "
        "package to fidelity with the seeded source of record, one account at "
        "a time, then applies a materiality gate."
    )
    out.append("")
    out.append(f"**Verdict: {mark} {journal.verdict}** — {_BLURB[journal.verdict]}")
    out.append("")
    out.append(
        f"- Injected drift: **{len(journal.faults)}** fault(s) · "
        f"initial deviations: **{len(journal.initial_deviations)}**"
    )
    out.append(
        f"- Turns: **{len(journal.turns)}** / budget **{journal.budget}** · "
        f"accounts resynced: **{', '.join(journal.accounts_resynced) or '—'}**"
    )
    out.append(
        f"- Corrections booked: **{journal.total_adjustments}** · gross movement "
        f"**{journal.total_correction:,.2f}** · materiality **{journal.materiality:,.2f}**"
    )
    out.append("")

    if journal.faults:
        out.append("## Injected drift")
        out.append("")
        for f in journal.faults:
            out.append(f"- {f}")
        out.append("")

    out.append("## The loop, turn by turn")
    out.append("")
    if not journal.turns:
        out.append("_No deviation from source — nothing to remediate._")
        out.append("")
    for t in journal.turns:
        out.append(
            f"### Turn {t.index} — resync `{t.account_number}` · "
            f"{t.deviations_before} → {t.deviations_after} deviations"
        )
        out.append("")
        if t.adjustments:
            out.append("| Record | Field | From | To |")
            out.append("|--------|-------|------|-----|")
            for a in t.adjustments:
                out.append(f"| {a.record} | `{a.field}` | {a.from_value} | {a.to_value} |")
        else:
            out.append("_No field movement._")
        out.append("")

    out.append(
        "_The loop never invents a number: every correction restores the seeded "
        "record, and the settled reconciliation is identical to a pristine run. "
        "Genuine reconciling items in the scenario are preserved, not zeroed._"
    )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys
    from pathlib import Path

    p = argparse.ArgumentParser(
        prog="recon_engine.loop",
        description="Reconciliation Assurance Loop: restore a drifted package "
        "to the source of record; materiality-gated verdict (fictional data).",
    )
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--threshold", type=float, default=MATERIALITY_THRESHOLD)
    p.add_argument("--demo", action="store_true", help="inject the drift profile")
    p.add_argument("--budget", type=int, default=None)
    p.add_argument("--out", default=None, help="directory for the Markdown report")
    args = p.parse_args(argv)

    if args.demo:
        _pristine, dataset, faults = demo_setup(args.seed, args.threshold)
    else:
        dataset, faults = generate_dataset(args.seed), ()

    journal = assurance_loop(
        dataset, seed=args.seed, threshold=args.threshold,
        budget=args.budget, faults=faults,
    )
    md = render_markdown(journal)
    try:
        print(md)
    except UnicodeEncodeError:  # pragma: no cover
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(md.encode(enc, errors="replace").decode(enc) + "\n")

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "assurance_loop_report.md").write_text(md, encoding="utf-8")
        print(f"\nWrote assurance_loop_report.md to {out_dir.resolve()}")

    return verdict_exit_code(journal.verdict)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
