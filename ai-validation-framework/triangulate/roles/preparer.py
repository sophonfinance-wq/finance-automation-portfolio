"""The Preparer role -- builds and normalises the workpaper."""

from __future__ import annotations

from typing import List

from triangulate.generate import build_sample
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
