"""
Data model for the warranty reimbursement control engine.
=========================================================

The engine consumes **claim files**: one JSON file per project/reporting period
carrying the artifacts a homebuilder's warranty-reimbursement programme emits.
Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Why warranty claims are worth an engine
---------------------------------------
A builder buys a warranty policy at the start of a project, then spends the next
several years claiming against it a few thousand dollars at a time: a leaking
sink in unit 4, a failed fixture in unit 11. Each claim is trivially small. The
policy behind them is not, and it is finite.

Two things therefore have to hold simultaneously and nobody watching a single
claim can see either. First, the pool is bounded: cumulative reimbursement can
never exceed the coverage limit, and that limit is itself derived from the
premium, which is derived from construction cost -- three numbers that are typed
once at inception and then trusted forever. Second, every claim has to be *inside*
something: inside the policy period, inside its own quarterly reporting window,
and after the unit it relates to actually closed, because warranty coverage
begins at close of escrow and not before.

The failure mode is accumulation. Any one claim is obviously fine. It is the
running total, and the boundary conditions at the edges of each period, that
quietly go wrong.

Severity model
--------------
- ``FAIL`` -- a hard control failure (cumulative claims past the coverage limit,
  a claim outside the policy period, a claim with no cost behind it).
- ``FLAG`` -- a human-review signal (coverage nearly exhausted, a claim close to
  a period boundary, remittance details incomplete).
- ``PASS`` -- the rule ran and the control held.

A claim file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: Policy terms: construction cost, premium, coverage limit, and the policy period.
DOC_POLICY = "policy_declaration"
#: The reimbursement request being submitted this period.
DOC_CLAIM_SUBMISSION = "claim_submission"
#: Every reporting period to date, with the claim lines inside each.
DOC_CLAIMS_HISTORY = "claims_history"
#: Warranty cost transactions from the job-cost ledger, at the warranty cost codes.
DOC_COST_LEDGER = "warranty_cost_ledger"
#: Units that have closed, with their close-of-escrow dates.
DOC_CLOSED_UNITS = "closed_units"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_POLICY,
    DOC_CLAIM_SUBMISSION,
    DOC_CLAIMS_HISTORY,
    DOC_COST_LEDGER,
    DOC_CLOSED_UNITS,
)

#: Job-cost codes a warranty claim may draw from. A cost outside these is not a
#: warranty cost, whatever the description says.
WARRANTY_COST_CODES: tuple[str, ...] = ("86-103", "86-104")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a claim file or the whole run."""

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
        ``"pol_cumulative_within_limit"``).
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
    """Everything a check needs about one claim file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the claim file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def project(self) -> str:
        """Fictional project the claim file belongs to."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label (``YYYY-Qn``)."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the claim file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A claim file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one claim file plus its rolled-up verdict."""

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
