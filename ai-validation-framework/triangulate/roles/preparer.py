"""The Preparer role -- builds and normalises the workpaper."""

from __future__ import annotations

from typing import List

from triangulate.formula import evaluate
from triangulate.generate import build_sample, make_adversarial_workpaper
from triangulate.model import Workpaper
from triangulate.roles.base import Preparer


class DemoPreparer(Preparer):
    """Builds a workpaper from the bundled synthetic sample.

    In a real engagement the Preparer would ingest a trial balance and produce
    the workbook; here it loads a deterministic, fictional sample so the whole
    pipeline runs with no external inputs. It is the *only* role handed a live,
    mutable :class:`~triangulate.model.Workpaper`.
    """

    name = "Preparer:DemoPreparer"

    def __init__(self, kind: str = "defective", seed: int = 20240101) -> None:
        self.kind = kind
        self.seed = seed

    def build(self) -> Workpaper:
        """Produce a fresh, normalised workpaper from the synthetic source."""
        return build_sample(self.kind, self.seed)

    def builder_memo(self, wp: Workpaper) -> List[str]:
        """Builder Memo: declared sources, assumptions and known risks."""
        memo: List[str] = [
            f"Engagement {wp.engagement} -- {wp.entity} ({wp.period}).",
            f"Built by {self.name} from synthetic current-year source data.",
            f"Cells prepared: {len(wp.cells)}.",
        ]
        assumptions = [
            c for c in wp.ordered_cells()
            if c.source.name == "AI_ASSUMPTION"
        ]
        if assumptions:
            memo.append(
                "Assumptions requiring verification (AI-generated, lowest "
                "authority): " + ", ".join(f"{c.ref} ({c.label})" for c in assumptions)
            )
        else:
            memo.append("No AI-generated assumptions in this build.")
        memo.append(
            "Risk posture: figures are synthetic; tie-outs to be confirmed by "
            "the automated audit before sign-off."
        )
        return memo


class AdversarialPreparer(Preparer):
    """Ships a clean workpaper with ONE injected hallucination.

    Used by ``--demo-adversarial`` to prove the load-bearing claim: deterministic
    verification beats asking an AI whether a workbook "looks right". The injected
    figure is plausible enough to slip past a human skim, but cannot survive the
    auditor re-deriving the formula.
    """

    name = "Preparer:AdversarialDemo"

    def __init__(self, seed: int = 20240101) -> None:
        self.seed = seed

    def build(self) -> Workpaper:
        return make_adversarial_workpaper(self.seed)

    def builder_memo(self, wp: Workpaper) -> List[str]:
        b5 = wp.get("B5")
        values = {ref: c.value for ref, c in wp.cells.items() if c.value is not None}
        derived = evaluate(b5.formula, values) if b5 and b5.formula else None
        return [
            f"Engagement {wp.engagement} -- {wp.entity} ({wp.period}).",
            "ADVERSARIAL DEMO: a clean workpaper with ONE injected hallucination.",
            f"An AI asserted B5 (Total Revenue) as {b5.value:,.2f} -- but =B2+B3+B4 "
            f"sums to {derived:,.2f}, a {abs(b5.value - derived):,.2f} overstatement "
            "backed only by an AI assumption (lowest authority).",
            "B5 feeds B7 (tax) and B8 (net), so the single bad figure propagates downstream.",
            "A human skim might accept a plausible-looking total. The deterministic audit "
            "cannot: the Reviewer and the independent Auditor each re-derive every formula,",
            "raise a CRITICAL tie-out break on each affected cell, and the automated policy gate returns",
            "FAIL -- the workpaper is blocked from sign-off. No model 'looks at it and says OK'.",
        ]
