"""
Data model for the gross-receipts & excise tax reconciliation engine.
=====================================================================

The engine consumes **reconciliation files**: one JSON file per filer's
gross-receipts / excise tax record, carrying the artifacts that record emits.
Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: the tax the paper claims versus the tax the receipts re-derive
--------------------------------------------------------------------
A developer that manages projects across several taxing jurisdictions owes a
gross-receipts or excise tax in each one -- a state Business & Occupation tax, a
city excise, a territorial general-excise tax. Each jurisdiction has its own
classification rate, its own filing cadence (monthly, quarterly, annual), its own
deductions, thresholds and due dates, and each rate can change mid-year. The
filer prepares one worksheet per entity per jurisdiction per period, and files
it.

This engine is about **whether the tax on the worksheet is the tax the receipts
produce**, not where an expense lands. It re-derives, from the general-ledger
revenue pull, each worksheet's taxable base, applies the classification rate that
was actually in effect for the period, subtracts the deductions and credits the
jurisdiction's own rules allow, and ties the recomputed tax to the number the
worksheet filed. Then it proves the filing calendar is complete: every active
entity in every jurisdiction has a filing for every period at its cadence, filed
by its due date, approved before it was filed.

Why that is worth an engine
---------------------------
The tax on a worksheet is a *derived* figure, and it goes wrong in ways that look
right on the page.

**The base does not tie the ledger.** A revenue line is omitted, a non-taxable
back-out is overstated, or the monthly lines do not sum to the total the rate is
struck against -- and the tax is computed on a base nobody reconciled to the GL.

**The rate is the wrong rate.** A classification rate changed mid-year and the
worksheet applied last quarter's rate to this quarter's receipts, or applied a
neighbouring jurisdiction's rate; the arithmetic is internally consistent and
still wrong.

**A deduction or credit is misapplied.** A standard deduction that was already
exhausted is taken again, a below-threshold no-tax rule is claimed above the
threshold, or a small-business credit is read off the wrong bracket.

**The calendar has a hole.** An entity-jurisdiction-period that should have a
filing has none, a return was filed after its due date, or filed before anyone
approved it -- and the exposure is invisible until an assessment arrives.

So the controls here are re-derivation controls. Every worksheet's tax is
recomputed from the receipts and the rate table, and compared; every expected
filing is enumerated from the calendar and proven present, timely and approved.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a base that does not tie the ledger, a
  wrong rate, a misapplied deduction or credit, a re-derived tax that does not
  match the worksheet, a missing or late filing, an unapproved filing, a
  rollup that does not recompute).
- ``FLAG`` -- a human-review signal (a filing due soon and not yet filed, a
  business licence due to renew inside the lead-time window).
- ``PASS`` -- the rule ran and the control held.

A reconciliation file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
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
#: Every filing entity, with the jurisdictions it is required to file in.
DOC_ENTITY_REGISTER = "entity_register"
#: Per-jurisdiction rate table: cadence, classification, rate windows, deduction
#: / threshold / small-business-credit rules, and the periods expected this cycle.
DOC_JURISDICTION_REGISTER = "jurisdiction_register"
#: The GL revenue pull: gross-receipts lines by entity, jurisdiction and period.
DOC_REVENUE_LEDGER = "revenue_ledger"
#: The filed worksheets: one per entity x jurisdiction x period.
DOC_FILING_REGISTER = "filing_register"
#: The per-filing recomputed tax determination.
DOC_TAX_SUMMARY = "tax_summary"
#: City / territorial business-licence status and renewal register.
DOC_LICENSE_REGISTER = "license_register"
#: The portfolio rollup: total tax due and filing count.
DOC_EXCISE_REPORT = "excise_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_REGISTER,
    DOC_JURISDICTION_REGISTER,
    DOC_REVENUE_LEDGER,
    DOC_FILING_REGISTER,
    DOC_TAX_SUMMARY,
    DOC_LICENSE_REGISTER,
    DOC_EXCISE_REPORT,
)

# --------------------------------------------------------------------------- #
# Reconciliation vocabulary
# --------------------------------------------------------------------------- #
#: Filing cadences. Each jurisdiction files at exactly one of these.
CADENCE_MONTHLY = "monthly"
CADENCE_QUARTERLY = "quarterly"
CADENCE_ANNUAL = "annual"
CADENCES: tuple[str, ...] = (
    CADENCE_MONTHLY,
    CADENCE_QUARTERLY,
    CADENCE_ANNUAL,
)

#: Licence statuses tracked by the secondary register.
LICENSE_ACTIVE = "active"
LICENSE_CANCELLED = "cancelled"
LICENSE_STATUSES: tuple[str, ...] = (LICENSE_ACTIVE, LICENSE_CANCELLED)

#: Default lead-time, in days, for the due-soon and licence-renewal windows when
#: a file does not carry its own. A filing due -- or a licence renewing -- inside
#: this window is a FLAG, not a failure: there is still time to act.
DEFAULT_LEAD_DAYS = 60


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a reconciliation file or the whole run."""

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
        ``"rate_tax_due_recomputes"``).
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
    """Everything a check needs about one reconciliation file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the reconciliation file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional filer whose tax record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reconciliation-cycle label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every due-date and renewal test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def lead_days(self) -> int:
        """Lead-time window, in days, for the due-soon and renewal flags.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_LEAD_DAYS` when it is absent or malformed.
        """
        value = self.data.get("lead_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_LEAD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the reconciliation file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A reconciliation file carries exactly one of each artifact. Returning
        ``None`` rather than raising lets ``set_complete`` own the "missing
        artifact" finding, so every downstream rule reports absence the same way.
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
    """All findings for one reconciliation file plus its rolled-up verdict."""

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
