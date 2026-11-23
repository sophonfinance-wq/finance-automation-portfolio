"""
Data model for the project labor charge control engine.
=======================================================

The engine consumes **charge-run files**: one JSON file per contractor entity for a
monthly cycle of charging employee labor cost to projects. Each source artifact is
modelled as a typed document -- a dict with a ``doc_type`` discriminator and typed
fields -- so the whole engine stays stdlib-only, deterministic and byte-stable.

Scope: authorization and arithmetic, not payroll
------------------------------------------------
This engine is about **whether a labor charge was authorized and computed
correctly**, not about how the employee was paid. Whether the burdened rate is the
right one, whether payroll withheld the right taxes -- those are payroll questions,
and they belong upstream. The question here is narrower and entirely procedural: a
project manager notifies the project accountant *in advance* that an employee will
be charged to a project, on a stated cost code, at a fixed monthly amount or a
percentage of the employee's fully-burdened cost -- and every month a charge lands
that must match what was authorized, foot into an invoice, and stay inside budget.

Why that is worth an engine
---------------------------
An employee's time is not free to a project just because the company already pays
their salary. The cost has to be *charged over* -- salary plus payroll taxes plus
benefits, the fully-burdened figure -- and it has to be charged only where a
project manager authorized it, only from the month the authorization takes effect,
and only up to the labor budget the project carries.

Four things go wrong, and none of them look wrong in a monthly invoice run.

**The charge outruns the authorization.** A fixed amount was authorized, and the
ledger charges a different one; or a percentage was authorized, and the resolved
monthly figure does not re-derive from the burdened cost to the cent. The invoice
still totals cleanly. The project is simply carrying the wrong number.

**The charge predates the authorization.** An employee is charged for a month
before the authorized start date -- the notice was given late, or the start slipped
and the charge did not. The month is real, the amount is right, and the charge
should not exist at all.

**The charge lands where nobody authorized it.** An employee is charged to a
project, or on a cost code, that the authorization never named. The money is real
and it is on the wrong job.

**The budget is silently overrun.** Cumulative labor charges cross the project's
labor budget parameter and nobody notices until the job is underwater, because each
individual monthly charge looked ordinary.

So the controls here are authorization controls. Every monthly charge is checked
against the authorization that permits it, every invoice is re-footed from the
charges beneath it, and the cumulative charge is measured against the budget.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a charge that does not match its
  authorization, a charge before the authorized start, a charge to an
  unauthorized project or cost code, an invoice that does not foot, a budget
  overrun, a ledger that does not tie the general ledger).
- ``FLAG`` -- a human-review signal (cumulative labor charges nearing the budget).
- ``PASS`` -- the rule ran and the control held.

A charge-run file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every chargeable employee, with a fully-burdened monthly cost.
DOC_EMPLOYEE_REGISTER = "employee_register"
#: The projects a labor charge can land on, with cost codes and a labor budget.
DOC_PROJECT_REGISTER = "project_register"
#: The advance authorizations: which employee, to which project, on what basis.
DOC_CHARGE_AUTHORIZATION = "charge_authorization"
#: The monthly charges themselves: one row per employee per project per period.
DOC_LABOR_CHARGE_LEDGER = "labor_charge_ledger"
#: The per-project per-period invoice totals the charges foot into.
DOC_MONTHLY_INVOICE = "monthly_invoice"
#: The general-ledger positions the charge run has to tie to.
DOC_GL_POSITIONS = "gl_positions"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_EMPLOYEE_REGISTER,
    DOC_PROJECT_REGISTER,
    DOC_CHARGE_AUTHORIZATION,
    DOC_LABOR_CHARGE_LEDGER,
    DOC_MONTHLY_INVOICE,
    DOC_GL_POSITIONS,
)

# --------------------------------------------------------------------------- #
# Charge vocabulary
# --------------------------------------------------------------------------- #
#: Authorization methods. A fixed monthly amount, or a percentage of the
#: employee's fully-burdened cost.
METHOD_FIXED = "fixed"
METHOD_PERCENT = "percent"
METHODS: tuple[str, ...] = (METHOD_FIXED, METHOD_PERCENT)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a charge-run file or the whole run."""

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
        ``"chg_amount_matches_auth"``).
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
    """Everything a check needs about one charge-run file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the charge-run file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def entity(self) -> str:
        """Fictional contractor entity the file belongs to."""
        value = self.data.get("entity")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_label(self) -> str:
        """Fictional-future charge-cycle label."""
        value = self.data.get("period_label")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date the charge run is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the charge-run file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A charge-run file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one charge-run file plus its rolled-up verdict."""

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
