"""
Data model for the debt term-sheet sizing & loan-terms control engine.
======================================================================

The engine consumes **sizing files**: one JSON file per fictional borrower's
term-sheet workbook, carrying the artifacts that workbook emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: sizing tie-out, not funding
----------------------------------
This engine is the sizing half of the debt story. Whether a draw is actually
advanced against a budget line is a *funding* question, and a separate engine
owns it -- this engine explicitly declines to move a dollar. This engine is the
tie-out that runs before anything closes: does the term sheet's own arithmetic
hold together? A borrower runs several projects through legal at once, and each
period a new dated workbook is produced from one template as the deals move
toward close. The workbook lays the deals out side by side -- max loan amount,
max loan-to-cost, the index + spread rate build-up over a floor, the LC and
overdraft facilities, the origination / commitment / unused / admin fees, the
term and its extension options, the recourse -- and the question here is narrow
and entirely arithmetic: do the numbers on the term sheet reconcile to the terms
the term sheet states?

Why that is worth an engine
---------------------------
A term sheet is a one-page summary re-keyed from a longer credit memo, and it
drifts in ways nobody re-foots.

Three things go wrong, and none of them look wrong.

**The loan is sized over the advance rate.** The stated max loan amount creeps a
cent or a million above max loan-to-cost times the cost basis, and the
over-advance rides in the workbook while the cap sits in a cell nobody
recomputed.

**A build-up figure is re-keyed, not re-derived.** The all-in rate is typed as
index plus spread when the floor actually governs, or a fee line is struck on
the wrong base -- commitment where it should be drawn, facility where it should
be undrawn -- so the fee is arithmetically the wrong number against the right
rate.

**The rollup drifts from the deals.** The portfolio total commitment, the total
fees, or the count of active deals is maintained beside the side-by-side rather
than footed from it, and it drifts the first time a deal moves and nobody re-adds
the column.

So the controls here are re-derivation controls. Every all-in rate, every fee
amount and every portfolio total is recomputed from the base terms and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (an over-advance, an all-in rate or fee that
  does not recompute, a maturity that does not reconcile to term plus extensions,
  an enumerated field off its allowed list, a rollup total that does not foot).
- ``FLAG`` -- a human-review signal (a term sheet expiring inside the
  lead-time window, an expiry watchlist that does not tie the deals).
- ``PASS`` -- the rule ran and the control held.

A sizing file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
roll up to ``REVIEW``; everything clean is ``PASS``.

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
#: The active deals being sized, with their base terms.
DOC_DEAL_REGISTER = "deal_register"
#: The index / spread / floor build-up inputs, one row per deal.
DOC_RATE_BUILDUP = "rate_buildup"
#: Every fee line, with its rate and the base it is struck on.
DOC_FEE_SCHEDULE = "fee_schedule"
#: The all-in rate determination, one row per deal.
DOC_RATE_SUMMARY = "rate_summary"
#: The computed amount for each fee line.
DOC_FEE_SUMMARY = "fee_summary"
#: Term sheets expiring inside the lead-time window.
DOC_EXPIRY_WATCHLIST = "expiry_watchlist"
#: The portfolio term-sheet rollup (counts and totals).
DOC_TERM_SHEET_ROLLUP = "term_sheet_rollup"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_DEAL_REGISTER,
    DOC_RATE_BUILDUP,
    DOC_FEE_SCHEDULE,
    DOC_RATE_SUMMARY,
    DOC_FEE_SUMMARY,
    DOC_EXPIRY_WATCHLIST,
    DOC_TERM_SHEET_ROLLUP,
)

# --------------------------------------------------------------------------- #
# Sizing vocabulary
# --------------------------------------------------------------------------- #
#: Loan types. Each is a distinct product with its own sizing rhythm. All
#: fictional labels; adding one is a value, never a control.
LOAN_CONSTRUCTION = "construction"
LOAN_PERMANENT = "permanent"
LOAN_BRIDGE = "bridge"
LOAN_MINI_PERM = "mini_perm"
LOAN_TYPES: tuple[str, ...] = (
    LOAN_CONSTRUCTION,
    LOAN_PERMANENT,
    LOAN_BRIDGE,
    LOAN_MINI_PERM,
)

#: Reference indices the rate build-up may be struck on. Every name here is
#: invented; no real published benchmark is referenced.
INDEX_TERM_REFERENCE = "term_reference_index"
INDEX_OVERNIGHT = "overnight_index"
INDEX_PRIME_REFERENCE = "prime_reference"
INDEX_FIXED_SWAP = "fixed_swap_index"
INDEX_NAMES: tuple[str, ...] = (
    INDEX_TERM_REFERENCE,
    INDEX_OVERNIGHT,
    INDEX_PRIME_REFERENCE,
    INDEX_FIXED_SWAP,
)

#: Recourse structures a deal may carry.
RECOURSE_FULL = "full_recourse"
RECOURSE_PARTIAL = "partial_recourse"
RECOURSE_NON = "non_recourse"
RECOURSE_TYPES: tuple[str, ...] = (
    RECOURSE_FULL,
    RECOURSE_PARTIAL,
    RECOURSE_NON,
)

#: Fee lines a deal can carry. The type is descriptive; the base drives the math.
FEE_ORIGINATION = "origination"
FEE_COMMITMENT = "commitment"
FEE_UNUSED = "unused"
FEE_ADMIN = "admin"
FEE_TYPES: tuple[str, ...] = (
    FEE_ORIGINATION,
    FEE_COMMITMENT,
    FEE_UNUSED,
    FEE_ADMIN,
)

#: The base a fee rate is applied to. ``undrawn`` is commitment less drawn.
BASE_COMMITMENT = "commitment"
BASE_DRAWN = "drawn"
BASE_UNDRAWN = "undrawn"
BASE_FACILITY = "facility"
BASE_TYPES: tuple[str, ...] = (
    BASE_COMMITMENT,
    BASE_DRAWN,
    BASE_UNDRAWN,
    BASE_FACILITY,
)

#: Default lead-time, in days, for the term-sheet expiry watchlist when a file
#: does not carry its own. A term sheet expiring inside this window is a FLAG,
#: not a failure -- there is still time to close.
DEFAULT_COMMITMENT_LEAD_DAYS = 45


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a sizing file or the whole run."""

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
        ``"size_ltc_not_exceeded"``).
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
    """Everything a check needs about one sizing file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the sizing file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional borrower whose term-sheet workbook the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future workbook period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated pricing date every expiry test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def commitment_lead_days(self) -> int:
        """Lead-time window, in days, for the term-sheet expiry watchlist.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_COMMITMENT_LEAD_DAYS` when it is absent or
        malformed.
        """
        value = self.data.get("commitment_lead_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_COMMITMENT_LEAD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the sizing file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A sizing file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one sizing file plus its rolled-up verdict."""

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
