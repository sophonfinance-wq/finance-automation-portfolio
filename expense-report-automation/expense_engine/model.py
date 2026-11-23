"""
Data model for the employee-expense & company card (P-Card) control engine.
==========================================================================

The engine consumes **cycle files**: one JSON file per statement cycle for a
company's purchasing-card programme, carrying the artifacts that cycle emits.
Each source artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: does the report reconcile, and is every charge supported and coded?
--------------------------------------------------------------------------
A company does not reimburse a card statement on trust. It issues a card to a
cardholder, the bank issues a statement, and the cardholder owes a matching
expense report: one report line per statement charge, each with a receipt on
file, a business purpose, a valid general-ledger code and a real project, filed
inside the submission window, under the per-charge limit, approved by somebody
other than the cardholder.

Three things go wrong, and none of them look wrong in a page of small numbers.

**The charge that never gets reported.** A statement line with no matching
report line is a company expense nobody coded and nobody has a receipt for. It
does not fail a total -- the total is simply lower than the bank's -- so it
surfaces only when the report is reconciled line by line against the statement.

**The residual cent between the report and the bank.** A report can foot to a
tidy round number and still be a penny off the statement it is meant to mirror.
Reconciliation is exact here: every statement line ties its report line to the
cent, and the report total ties the statement total to the cent.

**The charge that should never have been on the card.** A charge over the
per-charge limit, in a disallowed merchant category, coded to a project that
does not exist, or approved by the person who incurred it -- each is a control
break that a footed, receipted report will still carry straight through.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a charge with no report line, a report that
  does not reconcile to the statement, a missing receipt, a charge over the
  limit, an approver who is the cardholder, a duplicate charge).
- ``FLAG`` -- a human-review signal (a charge in a disallowed category, a report
  filed after the submission window).
- ``PASS`` -- the rule ran and the control held.

A cycle file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: Every cardholder on the programme: id, card last four, home entity.
DOC_CARDHOLDER_REGISTER = "cardholder_register"
#: The programme policy: window, per-charge limit, disallowed categories, GL set.
DOC_POLICY = "policy"
#: The projects a charge can be coded to, with their budgets.
DOC_PROJECT_REGISTER = "project_register"
#: The bank statements for the cycle, one per cardholder, each a list of charges.
DOC_STATEMENT_REGISTER = "statement_register"
#: The expense reports for the cycle, one per cardholder, each a list of lines.
DOC_EXPENSE_REPORT_REGISTER = "expense_report_register"
#: The general-ledger positions the programme has to tie to.
DOC_GL_POSITIONS = "gl_positions"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_CARDHOLDER_REGISTER,
    DOC_POLICY,
    DOC_PROJECT_REGISTER,
    DOC_STATEMENT_REGISTER,
    DOC_EXPENSE_REPORT_REGISTER,
    DOC_GL_POSITIONS,
)

# --------------------------------------------------------------------------- #
# Programme vocabulary
# --------------------------------------------------------------------------- #
#: The home entities a cardholder can belong to. Each is a fictional org.
ENTITIES: tuple[str, ...] = (
    "Northmoor Construction LLC",
    "Halbrook Builders",
    "Stonecrest Holdings",
    "Ardenne Field Partners",
)

#: Merchant categories the programme recognises. Membership is documentary; the
#: disallowed subset is a policy field, read at runtime rather than hard-coded.
CATEGORIES: tuple[str, ...] = (
    "airfare",
    "lodging",
    "meals",
    "supplies",
    "software",
    "fuel",
    "cash_advance",
    "gambling",
    "alcohol",
    "gift_card",
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
    """Overall verdict for a cycle file or the whole run."""

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
        ``"rec_every_charge_reported"``).
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
    """Everything a check needs about one cycle file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the cycle file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def programme(self) -> str:
        """Fictional company the P-Card programme belongs to."""
        value = self.data.get("programme")
        return str(value) if isinstance(value, str) else "-"

    @property
    def cycle(self) -> str:
        """Fictional-future statement cycle label."""
        value = self.data.get("cycle")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date the cycle is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the cycle file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A cycle file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one cycle file plus its rolled-up verdict."""

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
