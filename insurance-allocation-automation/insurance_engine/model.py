"""
Data model for the insurance cost allocation control engine.
============================================================

The engine consumes **programme files**: one JSON file per policy year for a
developer's insurance programme, carrying the artifacts that programme emits.
Each source artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: allocation, not compliance
---------------------------------
This engine is about **where the cost lands**. Whether a subcontractor's
certificate is on file, unexpired and carrying the required limits is a payment
question, and it belongs to the accounts-payable engine, which gates release on
exactly that. Nothing here re-checks a certificate. The question here is narrower
and entirely arithmetic: a master policy premium arrives as one number, and it has
to become a number on each project's job cost -- correctly, reproducibly, and
summing back to what was actually paid.

Why that is worth an engine
---------------------------
A developer does not buy insurance per project. It buys a programme: a general
liability tower, a builder's risk policy over whatever is under construction, an
excess layer above the primary. One premium, many projects, and an allocation
basis that is a *choice* -- hard cost, insured value, unit count, payroll -- made
once and then applied every year by whoever inherited the spreadsheet.

Three things go wrong, and none of them look wrong.

**The residual cent.** Any allocation of one amount across N projects leaves a
remainder. Dropped, the allocation no longer sums to the premium; assigned twice,
it sums to a penny more. Neither is visible in a column of six-figure numbers, and
both make the job-cost tie-out fail for a reason nobody can find.

**The basis drifts from the data.** A project joins mid-term, or the basis value
behind it was never filled in, and the weights quietly redistribute across
whatever remains -- so every *other* project's share moves too. The total still
ties. Every individual share is wrong.

**The audit true-up goes to the wrong year.** Carriers audit after the term and
issue additional or return premium months later. The projects that bore the
deposit premium are not necessarily the projects that are open when the credit
arrives -- some have closed. Crediting whoever is active today is the intuitive
booking, and it takes money from the wrong job.

So the controls here are allocation controls. Every share is re-derived from the
declared basis by the same largest-remainder method that should have produced it,
and compared to the cent.

Severity model
--------------
- ``FAIL`` -- a hard control failure (an allocation that does not sum to the
  premium, a share that does not re-derive, a credit routed to projects that never
  bore the deposit, a gap in the tower).
- ``FLAG`` -- a human-review signal (an insured value adrift of the budget, an
  audit with no restated basis, a per-unit metric that does not recompute).
- ``PASS`` -- the rule ran and the control held.

A programme file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every policy in the programme: line, tower position, term, premium, basis.
DOC_POLICY_REGISTER = "policy_register"
#: The projects a premium can land on, with every basis value they carry.
DOC_PROJECT_REGISTER = "project_register"
#: The allocation itself: one row per policy per project.
DOC_ALLOCATION_SCHEDULE = "allocation_schedule"
#: Carrier audits: additional or return premium, and how it was reallocated.
DOC_AUDIT_REGISTER = "audit_register"
#: What actually landed on each project's job cost.
DOC_JOB_COST_LEDGER = "job_cost_ledger"
#: The per-project reporting summary, including the per-unit metric.
DOC_ALLOCATION_SUMMARY = "allocation_summary"
#: The general-ledger positions the programme has to tie to.
DOC_GL_POSITIONS = "gl_positions"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PROJECT_REGISTER,
    DOC_POLICY_REGISTER,
    DOC_ALLOCATION_SCHEDULE,
    DOC_AUDIT_REGISTER,
    DOC_JOB_COST_LEDGER,
    DOC_ALLOCATION_SUMMARY,
    DOC_GL_POSITIONS,
)

# --------------------------------------------------------------------------- #
# Programme vocabulary
# --------------------------------------------------------------------------- #
#: Lines of cover. Successive terms of the same line must not leave a gap.
LINE_GENERAL_LIABILITY = "general_liability"
LINE_EXCESS = "excess_liability"
LINE_BUILDERS_RISK = "builders_risk"
LINES: tuple[str, ...] = (
    LINE_GENERAL_LIABILITY,
    LINE_EXCESS,
    LINE_BUILDERS_RISK,
)

#: Position in the tower. An excess layer attaches above a primary.
LAYER_PRIMARY = "primary"
LAYER_EXCESS = "excess"
LAYERS: tuple[str, ...] = (LAYER_PRIMARY, LAYER_EXCESS)

#: Allocation bases. Each is a field name on the project register, so adding a
#: basis is a column and a row -- never a change to a control.
BASIS_HARD_COST = "hard_cost_cents"
BASIS_INSURED_VALUE = "insured_value_cents"
BASIS_UNIT_COUNT = "unit_count"
BASES: tuple[str, ...] = (BASIS_HARD_COST, BASIS_INSURED_VALUE, BASIS_UNIT_COUNT)

#: Carrier audit outcomes.
AUDIT_ADDITIONAL = "additional"
AUDIT_RETURN = "return"
AUDIT_TYPES: tuple[str, ...] = (AUDIT_ADDITIONAL, AUDIT_RETURN)

#: Project stages. A completed project carries no builder's risk.
STAGE_DEVELOPMENT = "development"
STAGE_COMPLETE = "complete"
PROJECT_STAGES: tuple[str, ...] = (STAGE_DEVELOPMENT, STAGE_COMPLETE)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a programme file or the whole run."""

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
        ``"alloc_sums_to_premium"``).
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
    """Everything a check needs about one programme file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the programme file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def programme(self) -> str:
        """Fictional insurance programme the file belongs to."""
        value = self.data.get("programme")
        return str(value) if isinstance(value, str) else "-"

    @property
    def policy_year(self) -> str:
        """Fictional-future policy year label."""
        value = self.data.get("policy_year")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date the prepaid amortisation is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the programme file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A programme file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one programme file plus its rolled-up verdict."""

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
