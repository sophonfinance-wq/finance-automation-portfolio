"""
Data model for the project draw control engine.
===============================================

The engine consumes **draw packages**: one JSON file per project/period carrying
the fixed-format artifacts a construction loan draw cycle emits. Each source
artifact is modelled as a typed *draw document* -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Why a draw is worth an engine
-----------------------------
A draw request is the moment a developer asks a lender for money, and it is
almost entirely arithmetic. The package has to prove three things at once: that
cumulative draws equal cumulative costs, that the form the lender receives
agrees with the working papers behind it, and that the money being requested was
actually incurred inside the period being billed. Each of those is a tie-out
with a right answer, which is exactly what a deterministic control can assert.

The failure modes are not exotic. A retention release moved in one schedule but
not the other, a contingency line drawn faster than the work it is meant to
cover, a cost posted two days after cutoff and billed anyway -- each is invisible
in a spreadsheet and obvious to a rule.

Severity model
--------------
- ``FAIL`` -- a hard control failure (the reconciliation does not tie, the form
  contradicts its own working papers, contingency drawn past percent complete).
- ``FLAG`` -- a human-review signal (a cycle date missed, an unexplained but
  immaterial variance, a follow-up not logged).
- ``PASS`` -- the rule ran and the control held.

A package with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll up
to ``REVIEW``; everything clean is ``PASS``.

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
#: The job-cost-to-draw reconciliation: the project accountant's working paper.
DOC_JC_RECONCILIATION = "job_cost_to_draw_reconciliation"
#: The draw request form the lender or equity partner actually receives.
DOC_DRAW_REQUEST = "draw_request_form"
#: Current-period cost transactions, by hard/soft cost category.
DOC_COST_DETAIL = "cost_transaction_detail"
#: Equity and debt fundings to date, with the ledger balances they must tie to.
DOC_FUNDING_LEDGER = "funding_ledger"
#: Signatures, invoice backup and schedule-of-values coverage for the package.
DOC_SUPPORT_INDEX = "supporting_documentation_index"
#: The dated milestones of one draw cycle: cutoff, approval, prep, submittal.
DOC_CYCLE_CALENDAR = "draw_cycle_calendar"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_JC_RECONCILIATION,
    DOC_DRAW_REQUEST,
    DOC_COST_DETAIL,
    DOC_FUNDING_LEDGER,
    DOC_SUPPORT_INDEX,
    DOC_CYCLE_CALENDAR,
)

#: Cost classes a draw is split by. Contingency is governed per class, because a
#: hard-cost contingency may only be drawn against hard-cost progress.
COST_CLASSES: tuple[str, ...] = ("hard", "soft")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a draw package or the whole run."""

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
        ``"recon_draws_tie_costs"``).
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
    """Everything a check needs about one draw package.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def package_id(self) -> str:
        """Identifier of the draw package (falls back to the file stem)."""
        value = self.data.get("package_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def project(self) -> str:
        """Fictional project the draw belongs to."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future accounting period label (``YYYY-MM``)."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def draw_number(self) -> int | None:
        """Sequence number of this draw within the project, if declared."""
        value = self.data.get("draw_number")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every draw document in the package, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A draw package carries exactly one of each artifact. Returning ``None``
        rather than raising lets ``set_complete`` own the "missing artifact"
        finding, so every downstream rule reports absence the same way instead of
        each inventing its own message.
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
    """All findings for one draw package plus its rolled-up verdict."""

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
