"""
Data model for the contingency rollforward and adequacy control engine.
=======================================================================

The engine consumes **period files**: one JSON file per developer's periodic
project report, carrying the contingency status block that report restates every
reporting period. Each source artifact is modelled as a typed document -- a dict
with a ``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: the rollforward, not the forecast
----------------------------------------
Every periodic project report carries a contingency status block. For each active
project it rolls two buckets forward -- construction contingency and project
contingency -- from the prior period's balance, through the draws allocated
against them this period, to the balance remaining; then it states the projected
potential use still expected and calls each bucket adequate or inadequate. The
block is restated every period for every active project, and the portfolio rollup
adds the blocks up.

Nothing here forecasts. Whether the projected potential use is a *good* estimate
is a judgement, and no engine can make it. The question here is narrower and
entirely arithmetic: given the figures the report itself carries, does the block
roll forward, does it reconcile to the budget it came from, and is the adequacy
call the one those figures produce?

Why that is worth an engine
---------------------------
A contingency block is six numbers and a word, restated by hand, every period,
for every project. It goes wrong in ways that look like nothing.

**The rollforward stops rolling.** The current balance is typed rather than
derived, so it no longer equals the prior balance less what was allocated. The
column still adds down the page; it just stopped meaning the thing it is named
after.

**The draws and the total drift apart.** The allocated-this-period line is
maintained beside the draw detail rather than from it, so a draw is added to the
schedule and never reaches the total -- or reaches it twice -- and the bucket
reports more headroom than it has. Worse, a single draw can be written for more
than the balance it draws against, and nothing in a spreadsheet objects.

**The adequacy call outlives its own arithmetic.** A bucket is marked adequate in
one period and the word is carried forward while the projected potential use
climbs past the balance behind it. The report says adequate; the numbers on the
same row say otherwise.

So the controls here are arithmetic controls. Every derived figure in the block
is recomputed from the base facts and compared with exact ``==``, and the adequacy
word is rebuilt from the two amounts that define it.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a rollforward that does not roll, a total
  that does not tie its line items, a draw larger than the balance it draws
  against, a bucket that does not reconcile to the budget, an adequacy call or a
  rollup figure that does not recompute).
- ``FLAG`` -- a human-review signal (a bucket still adequate but with its headroom
  inside the watch band, an exposure watchlist that does not tie the blocks).
- ``PASS`` -- the rule ran and the control held.

A period file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
up to ``REVIEW``; everything clean is ``PASS``.

All shipped data is fictional. The engine never writes to a source artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Document type vocabulary
# --------------------------------------------------------------------------- #
#: Every project in the portfolio, with the status that decides whether it
#: carries a contingency block this period.
DOC_PROJECT_REGISTER = "project_register"
#: The contingency lines carried in each project budget, by bucket.
DOC_BUDGET_REGISTER = "budget_register"
#: Every draw allocated against contingency in the reporting period.
DOC_ALLOCATION_REGISTER = "allocation_register"
#: The contingency status block: one rollforward row per project and bucket.
DOC_CONTINGENCY_BLOCK = "contingency_block"
#: Buckets still adequate but with headroom inside the watch band.
DOC_EXPOSURE_WATCHLIST = "exposure_watchlist"
#: The portfolio rollup of the per-project blocks.
DOC_PORTFOLIO_ROLLUP = "portfolio_rollup"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PROJECT_REGISTER,
    DOC_BUDGET_REGISTER,
    DOC_ALLOCATION_REGISTER,
    DOC_CONTINGENCY_BLOCK,
    DOC_EXPOSURE_WATCHLIST,
    DOC_PORTFOLIO_ROLLUP,
)

# --------------------------------------------------------------------------- #
# Cost-control vocabulary
# --------------------------------------------------------------------------- #
#: Contingency buckets. Construction contingency absorbs field conditions and
#: trade scope; project contingency absorbs owner-side and soft-cost movement.
#: They roll forward separately and are never netted against one another.
BUCKET_CONSTRUCTION = "construction"
BUCKET_PROJECT = "project"
BUCKETS: tuple[str, ...] = (BUCKET_CONSTRUCTION, BUCKET_PROJECT)

#: Project statuses. Only an active project restates a contingency block.
PROJECT_ACTIVE = "active"
PROJECT_SUSPENDED = "suspended"
PROJECT_CLOSED = "closed"
PROJECT_STATUSES: tuple[str, ...] = (
    PROJECT_ACTIVE,
    PROJECT_SUSPENDED,
    PROJECT_CLOSED,
)

#: The adequacy assessment the block states for each bucket.
ADEQUACY_ADEQUATE = "adequate"
ADEQUACY_INADEQUATE = "inadequate"
ADEQUACY_VALUES: tuple[str, ...] = (ADEQUACY_ADEQUATE, ADEQUACY_INADEQUATE)

#: Default watch band, in basis points of the current balance, when a file does
#: not carry its own. A bucket whose projected potential use reaches this share
#: of what is left is still adequate -- and worth a human's attention.
DEFAULT_WATCH_THRESHOLD_BPS = 8000


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a period file or the whole run."""

    PASS = "PASS"  # every control held
    REVIEW = "REVIEW"  # at least one FLAG, no FAILs
    FAIL = "FAIL"  # at least one FAIL


@dataclass(frozen=True)
class Finding:
    """A single observation produced by a check.

    Attributes
    ----------
    rule:
        Stable identifier of the rule that produced the finding (e.g.
        ``"ctg_current_rolls_forward"``).
    status:
        :class:`Status` of this finding.
    location:
        Where the finding applies -- ``"<doc_type>:<document_id>/<field path>"``
        for document fields, or ``"-"`` when not field-specific.
    message:
        Human-readable explanation. Messages carry the control rationale, so an
        exception teaches the reason rather than only the verdict.
    """

    rule: str
    status: Status
    location: str
    message: str

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of the finding."""
        return {
            "rule": self.rule,
            "status": self.status.value,
            "location": self.location,
            "message": self.message,
        }


@dataclass
class Context:
    """Everything a check needs about one period file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the period file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose project report the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_start(self) -> str:
        """First day of the reporting period a draw must fall inside."""
        value = self.data.get("period_start")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_end(self) -> str:
        """Last day of the reporting period the block is restated to."""
        value = self.data.get("period_end")
        return str(value) if isinstance(value, str) else "-"

    @property
    def watch_threshold_bps(self) -> int:
        """Watch band, in basis points of the current balance.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_WATCH_THRESHOLD_BPS` when it is absent or malformed.
        """
        value = self.data.get("watch_threshold_bps")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_WATCH_THRESHOLD_BPS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the period file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A period file carries exactly one of each artifact. Returning ``None``
        rather than raising lets ``set_complete`` own the "missing artifact"
        finding, so every downstream rule reports absence the same way.
        """
        found = self.docs(doc_type)
        return found[0] if found else None

    def loc(self, doc: dict[str, Any], field_path: str) -> str:
        """Build a stable ``location`` string for a field inside ``doc``."""
        doc_type = doc.get("doc_type", "?")
        doc_id = doc.get("document_id", "?")
        return f"{doc_type}:{doc_id}/{field_path}"


@dataclass
class DocumentReport:
    """All findings for one period file plus its rolled-up verdict."""

    document: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        """Roll findings up into a single :class:`Verdict`."""
        if any(f.status is Status.FAIL for f in self.findings):
            return Verdict.FAIL
        if any(f.status is Status.FLAG for f in self.findings):
            return Verdict.REVIEW
        return Verdict.PASS

    def counts(self) -> dict[str, int]:
        """Return a ``{status: count}`` tally across findings."""
        out = {s.value: 0 for s in Status}
        for f in self.findings:
            out[f.status.value] += 1
        return out

    def rules_fired(self) -> list[str]:
        """Rule ids that produced a non-PASS finding, in first-seen order."""
        out: list[str] = []
        for f in self.findings:
            if f.status is not Status.PASS and f.rule not in out:
                out.append(f.rule)
        return out

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of the report."""
        return {
            "document": self.document,
            "verdict": self.verdict.value,
            "counts": self.counts(),
            "findings": [f.to_dict() for f in self.findings],
        }
