"""Triangulate Review Loop — arithmetic self-heals; judgment escalates.

Triangulate's pipeline (:mod:`triangulate.orchestrator`) is one adversarial
pass: preparer builds, reviewer and specialist challenge, a deterministic
auditor re-derives every formula, and the gate returns PASS / FLAG / FAIL.
When it FAILs, a human rebuilds and resubmits. This loop automates exactly the
part of that rebuild a machine is *entitled* to do — and nothing more:

    observe → detect → remediate → re-review → gate → repeat

1. **observe / detect** — run the full pipeline. Tie-out findings
   (``AUDIT_TIE_OUT_FAIL`` / ``TIE_OUT_MISMATCH``) carry the auditor's
   re-derived ``expected`` value for a formula cell — pure arithmetic, no
   judgment.
2. **remediate** — take the lowest broken formula cell and re-derive its value
   from its own formula (:func:`triangulate.formula.evaluate`) **on a clone**.
   The pipeline's hash-enforced read-only guard is never touched: each turn
   produces a *new workpaper version* with a new digest; nothing is edited
   inside a read-only stage.
3. **re-review** — the full pipeline runs again over the new version: reviewer,
   specialist, auditor, gate. The loop's fix gets no shortcut — it faces the
   same three challengers as any preparer.

What the loop refuses to touch is the point of the framework: an
``AI_ASSUMPTION`` input, a hardcoded cell with no formula, a missing required
cell — there is nothing to re-derive those *from*. They stay in the fix packet
for a human. The loop clears arithmetic drift; it cannot manufacture authority.

Verdicts (exit code follows the framework's PASS→0, else 1):

* ``CLEAN``        — first pass was already PASS; nothing to do.
* ``AUTO-CLEARED`` — the loop's re-derivations converged the pipeline to PASS.
* ``ESCALATED``    — residual findings need a human (or the budget ran out).

All data is fictional.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .formula import evaluate
from .generate import make_adversarial_workpaper, make_clean_workpaper
from .model import Workpaper
from .orchestrator import TriangulateOrchestrator
from .reconcile import VerdictStatus
from .roles.base import Preparer

CLEAN = "CLEAN"
AUTO_CLEARED = "AUTO-CLEARED"
ESCALATED = "ESCALATED"

# The only findings the loop may act on: tie-out breaks on formula cells,
# where the correction is the cell's own formula re-evaluated.
REMEDIABLE_CODES = frozenset({"AUDIT_TIE_OUT_FAIL", "TIE_OUT_MISMATCH"})


class _VersionPreparer(Preparer):
    """Feeds a loop-remediated workpaper version back through the pipeline."""

    name = "Preparer:LoopVersion"

    def __init__(self, wp: Workpaper) -> None:
        self._wp = wp

    def build(self) -> Workpaper:
        return self._wp.clone()

    def builder_memo(self, wp: Workpaper) -> List[str]:
        return [
            "Loop-remediated version: broken formula cells re-derived from "
            "their own formulas; no judgment inputs altered.",
        ]


# --------------------------------------------------------------------------- #
# Journal records.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Correction:
    """One formula cell re-derived from its own formula."""

    cell_ref: str
    from_value: float
    to_value: float
    formula: str


@dataclass(frozen=True)
class Turn:
    index: int
    version_digest: str        # digest of the NEW workpaper version
    correction: Correction
    verdict_before: str
    verdict_after: str
    criticals_before: int
    criticals_after: int


@dataclass(frozen=True)
class LoopJournal:
    seed: int
    scenario: str
    initial_verdict: str
    initial_findings: Tuple[str, ...]      # "SEVERITY code cell" summaries
    turns: Tuple[Turn, ...]
    residual_findings: Tuple[str, ...]     # left for the human fix packet
    budget: int
    verdict: str
    final_pipeline_verdict: str

    @property
    def versions(self) -> int:
        return len(self.turns) + 1


# --------------------------------------------------------------------------- #
# Loop internals.
# --------------------------------------------------------------------------- #
def _run_pipeline(wp: Workpaper):
    """Full adversarial pass over ``wp`` (offline mock reviewer, no artifacts)."""
    orch = TriangulateOrchestrator(preparer=_VersionPreparer(wp))
    return orch.run()


def _finding_summary(f) -> str:
    return f"{f.severity.name} {f.code} {f.cell_ref}"


def _remediable(findings, wp: Workpaper):
    """Tie-out breaks on cells that actually carry a formula, lowest ref first."""
    out = []
    for f in findings:
        if f.code not in REMEDIABLE_CODES:
            continue
        cell = wp.cells.get(f.cell_ref)
        if cell is None or not cell.formula:
            continue
        out.append(f)
    out.sort(key=lambda f: f.cell_ref)
    return out


def review_loop(
    workpaper: Workpaper,
    *,
    seed: int = 20240101,
    scenario: str = "custom",
    budget: int = 6,
) -> LoopJournal:
    """Drive ``workpaper`` through review → remediate → re-review to a verdict."""
    result = _run_pipeline(workpaper)
    initial_verdict = result.verdict.status.value
    initial = tuple(_finding_summary(f) for f in result.verdict.findings)

    wp = workpaper
    turns: List[Turn] = []
    while result.verdict.status is not VerdictStatus.PASS and len(turns) < budget:
        fixable = _remediable(result.verdict.findings, wp)
        if not fixable:
            break  # everything left needs a human
        target = fixable[0]
        # Re-derive on a CLONE — a new version, never an in-place edit.
        new_wp = wp.clone()
        cell = new_wp.cells[target.cell_ref]
        values = {ref: c.value for ref, c in new_wp.cells.items() if c.value is not None}
        derived = round(evaluate(cell.formula, values), 2)
        correction = Correction(
            cell_ref=target.cell_ref,
            from_value=cell.value,
            to_value=derived,
            formula=cell.formula,
        )
        cell.value = derived

        before_v = result.verdict.status.value
        before_c = result.verdict.severity_counts.get("Critical", 0)
        result = _run_pipeline(new_wp)
        turns.append(Turn(
            index=len(turns) + 1,
            version_digest=new_wp.digest()[:12],
            correction=correction,
            verdict_before=before_v,
            verdict_after=result.verdict.status.value,
            criticals_before=before_c,
            criticals_after=result.verdict.severity_counts.get("Critical", 0),
        ))
        wp = new_wp

    residual = tuple(_finding_summary(f) for f in result.verdict.findings)
    final = result.verdict.status.value
    if final == VerdictStatus.PASS.value:
        verdict = AUTO_CLEARED if turns else CLEAN
    else:
        verdict = ESCALATED

    return LoopJournal(
        seed=seed,
        scenario=scenario,
        initial_verdict=initial_verdict,
        initial_findings=initial,
        turns=tuple(turns),
        residual_findings=residual,
        budget=budget,
        verdict=verdict,
        final_pipeline_verdict=final,
    )


def verdict_exit_code(journal: LoopJournal) -> int:
    """Framework convention: PASS-final exits 0, anything else 1."""
    return 0 if journal.final_pipeline_verdict == VerdictStatus.PASS.value else 1


# --------------------------------------------------------------------------- #
# Markdown report.
# --------------------------------------------------------------------------- #
_BLURB = {
    CLEAN: "First pass was already PASS — nothing to remediate.",
    AUTO_CLEARED: "Arithmetic drift re-derived from the workpaper's own formulas; "
    "the pipeline re-reviewed every version and reached PASS.",
    ESCALATED: "Residual findings need judgment or a cited source — the loop "
    "refuses to manufacture authority. Fix packet goes to a human.",
}


def render_markdown(journal: LoopJournal) -> str:
    mark = {CLEAN: "✅", AUTO_CLEARED: "✅", ESCALATED: "⚑"}[journal.verdict]
    out: List[str] = []
    out.append("# Triangulate Review Loop [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional data. The loop re-derives broken formula cells on a new "
        "workpaper version each turn and sends it back through the full "
        "adversarial pipeline — reviewer, specialist, deterministic auditor, gate."
    )
    out.append("")
    out.append(f"**Verdict: {mark} {journal.verdict}** — {_BLURB[journal.verdict]}")
    out.append("")
    out.append(
        f"- Scenario **{journal.scenario}** (seed {journal.seed}) · "
        f"initial pipeline verdict: **{journal.initial_verdict}** · "
        f"final: **{journal.final_pipeline_verdict}**"
    )
    out.append(
        f"- Turns: **{len(journal.turns)}** / budget **{journal.budget}** · "
        f"workpaper versions: **{journal.versions}** (each with its own digest — "
        f"the read-only guard is never touched)"
    )
    out.append("")

    if journal.initial_findings:
        out.append("## Findings on the first pass")
        out.append("")
        for f in journal.initial_findings:
            out.append(f"- `{f}`")
        out.append("")

    out.append("## The loop, turn by turn")
    out.append("")
    if not journal.turns:
        out.append("_No machine-remediable findings._")
        out.append("")
    for t in journal.turns:
        out.append(
            f"### Turn {t.index} — re-derive `{t.correction.cell_ref}` "
            f"(version `{t.version_digest}`) · {t.verdict_before} → {t.verdict_after}"
        )
        out.append("")
        c = t.correction
        out.append(
            f"- `{c.cell_ref}` = `{c.formula}` → **{c.to_value:,.2f}** "
            f"(was {c.from_value:,.2f}) · criticals {t.criticals_before} → {t.criticals_after}"
        )
        out.append("")

    if journal.residual_findings and journal.verdict == ESCALATED:
        out.append("## Fix packet — left for the human")
        out.append("")
        for f in journal.residual_findings:
            out.append(f"- `{f}`")
        out.append("")
        out.append(
            "_An AI assumption, a hardcoded cell, a missing input: nothing to "
            "re-derive those from. The loop clears arithmetic; it cannot "
            "manufacture authority._"
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

    from .generate import build_sample

    p = argparse.ArgumentParser(
        prog="triangulate.loop",
        description="Review loop: re-derive arithmetic drift, re-review every "
        "version through the full pipeline, escalate judgment (fictional data).",
    )
    p.add_argument("--seed", type=int, default=20240101)
    p.add_argument(
        "--sample", choices=("clean", "defective", "adversarial"),
        default="adversarial",
        help="workpaper scenario (default: adversarial — the injected $49k figure)",
    )
    p.add_argument("--budget", type=int, default=6)
    p.add_argument("--out", default=None, help="directory for the Markdown report")
    args = p.parse_args(argv)

    if args.sample == "adversarial":
        wp = make_adversarial_workpaper(seed=args.seed)
    elif args.sample == "clean":
        wp = make_clean_workpaper(seed=args.seed)
    else:
        wp = build_sample("defective", seed=args.seed)

    journal = review_loop(wp, seed=args.seed, scenario=args.sample, budget=args.budget)
    md = render_markdown(journal)
    try:
        print(md)
    except UnicodeEncodeError:  # pragma: no cover
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(md.encode(enc, errors="replace").decode(enc) + "\n")

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "review_loop_report.md").write_text(md, encoding="utf-8")
        print(f"\nWrote review_loop_report.md to {out_dir.resolve()}")

    return verdict_exit_code(journal)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
