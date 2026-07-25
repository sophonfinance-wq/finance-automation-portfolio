"""
Data model for the Section 263A interest-capitalization control engine.
=======================================================================

The engine consumes **capitalization files**: one JSON file per fiscal-year
UNICAP interest schedule, carrying the tabs that schedule emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: the avoided-cost capitalization, not the deduction
--------------------------------------------------------
A real-estate developer that builds designated property with borrowed money may
not deduct all of the interest it pays. Under the avoided-cost method of
IRC section 263A(f), the interest that production could have avoided -- the
period rate applied to the accumulated production expenditures tied up in the
project -- must be **capitalized** into the property's basis rather than
deducted in the year paid. The rest is deducted. This engine proves, project by
project and quarter by quarter, that the split was computed the way the method
requires and that every tab of the schedule ties to the one beneath it.

Nothing here posts an entry, files a return or moves a dollar. The question is
narrower and entirely evidentiary: does the interest each project capitalized
re-derive from the expenditures and the rate, and do the annual, comparison and
rollup figures tie the quarterly evidence that produced them?

Why that is worth an engine
---------------------------
An annual interest-capitalization schedule is a grid of quarters that is rebuilt
every fiscal year, and it goes wrong in ways nobody watches.

**A row stops footing.** A quarter column is edited and the annual total beside
it is not re-added, so the project's interest, capitalized and deducted columns
no longer cross-foot -- the schedule looks complete and the total is wrong.

**The split leaks.** The interest a project incurred no longer equals the
capitalized portion plus the deducted portion, so a slice of interest is neither
capitalized into basis nor deducted -- it has simply left the schedule.

**A project is missing.** A construction project carrying an interest balance on
the entity trial balance never makes it onto the schedule, so its interest is
deducted in full and none is capitalized, and nothing in the workbook notices.

**The capitalized figure is asserted, not derived.** The capitalized interest is
typed in rather than recomputed as accumulated production expenditures times the
period rate rolled by quarter, or the rate is applied at one level for one
project and another level for the next, or the year-over-year comparison does
not carry the prior year's capitalized balance forward.

So the controls here are re-derivation controls. Every capitalized figure is
recomputed from the expenditures and the rate through the same kernel that
produced it, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a row that does not foot, a split that
  leaks, a missing project, a capitalized figure that does not re-derive, a rate
  applied inconsistently, a comparison that does not tie forward).
- ``FLAG`` -- a human-review signal (a project placed in service that is still
  capitalizing interest, where the capitalization period should have ended).
- ``PASS`` -- the rule ran and the control held.

A capitalization file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
FAILs roll up to ``REVIEW``; everything clean is ``PASS``.

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
#: The entity trial balance: every construction project carrying an interest
#: balance. The completeness source the schedule is proved against.
DOC_TRIAL_BALANCE = "trial_balance"
#: Project Status tab: the roster of active development projects.
DOC_PROJECT_STATUS = "project_status"
#: Project Data tab: accumulated production expenditures and the period rate.
DOC_PROJECT_DATA = "project_data"
#: Project Interest Exp by Year tab: interest, capitalized and deducted by quarter.
DOC_INTEREST_BY_YEAR = "interest_by_year"
#: Comparison tab: the year-over-year capitalized rollforward.
DOC_COMPARISON = "comparison"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_TRIAL_BALANCE,
    DOC_PROJECT_STATUS,
    DOC_PROJECT_DATA,
    DOC_INTEREST_BY_YEAR,
    DOC_COMPARISON,
)

# --------------------------------------------------------------------------- #
# Capitalization vocabulary
# --------------------------------------------------------------------------- #
#: A project actively under production; its avoided-cost interest is capitalized.
STATUS_ACTIVE = "active"
#: A project placed in service; the capitalization period has ended.
STATUS_COMPLETE = "complete"
#: A project whose production is suspended for the period.
STATUS_ON_HOLD = "on_hold"
PROJECT_STATUSES: tuple[str, ...] = (
    STATUS_ACTIVE,
    STATUS_COMPLETE,
    STATUS_ON_HOLD,
)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a capitalization file or the whole run."""

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
        ``"cap_rederives"``).
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
    """Everything a check needs about one capitalization file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the capitalization file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def entity(self) -> str:
        """Fictional developer whose interest schedule the file carries."""
        value = self.data.get("entity")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future fiscal-year label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date the completion test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def quarter_ends(self) -> list[str]:
        """The calendar quarter-end grid the schedule is built across."""
        value = self.data.get("quarter_ends")
        if not isinstance(value, list):
            return []
        return [q for q in value if isinstance(q, str) and q]

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the capitalization file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A capitalization file carries exactly one of each tab. Returning ``None``
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
    """All findings for one capitalization file plus its rolled-up verdict."""

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
