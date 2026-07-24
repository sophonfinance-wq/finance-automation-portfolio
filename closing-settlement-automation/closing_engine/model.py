"""
Data model for the home-sale closing & settlement tie-out engine.
=================================================================

The engine consumes **closing files**: one JSON file per residential project's
close-of-escrow record, carrying the artifacts that record emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: tie-out, not underwriting
--------------------------------
This engine is about **whether the paper the closing produced agrees with
itself**, not whether the deal should have been done. What a home should have
sold for, whether the proforma was right, whether the loan should have been
made -- those are underwriting questions a different engine owns. This engine is
narrower and entirely evidentiary: when a home closes escrow, does the balanced
journal entry foot, does the settlement statement recompute, do the rate-derived
fees strike at their proforma rates, was revenue recognised in the close month,
and does each unit's loan release tie to the lender's loan statement?

Why that is worth an engine
---------------------------
A close-of-escrow package is a stack of spreadsheets assembled under deadline,
and it goes wrong in ways nobody watches.

**The entry does not foot.** A closing journal entry whose debits and credits do
not balance -- or whose Accounts Receivable plug was typed rather than derived --
posts a number that ties to nothing.

**The statement does not recompute.** The total settlement charges, the total
closing costs or the net to seller was keyed instead of summed, or a rate-derived
fee -- the LISTING sales fee, the warranty reserve -- was struck at the wrong rate.
The statement looks complete; the arithmetic underneath it is not.

**The rollup drifts from the units.** The closing report states a closed count or
a total net to seller, or a per-unit tie-out flag, that nobody recomputed from
the settlements and entries underneath it.

So the controls here are evidentiary controls. Every unit's tie-out flag is
recomputed from the settlement, the entry, the loan release and the schedules,
and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (an entry that does not foot, a settlement
  line that does not recompute, a fee off its derived rate, revenue in the wrong
  month, a loan release that does not tie, a flag or count that does not
  recompute).
- ``FLAG`` -- a human-review signal (an actual fee that varies from the proforma
  assumption, a concession above the assumed allowance).
- ``PASS`` -- the rule ran and the control held.

A closing file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every unit in the project, its status and its close-of-escrow base facts.
DOC_UNIT_REGISTER = "unit_register"
#: The proforma rate assumptions the actual fees are measured against.
DOC_PROFORMA_ASSUMPTIONS = "proforma_assumptions"
#: The per-unit settlement statement (charges, closing costs, net to seller).
DOC_SETTLEMENT_REGISTER = "settlement_register"
#: The per-unit balanced close-of-escrow journal entry.
DOC_CLOSING_JE_REGISTER = "closing_je_register"
#: The per-unit revenue-recognition schedule (recognised in the close month).
DOC_REVENUE_SCHEDULE = "revenue_schedule"
#: The per-unit loan release reconciled to the lender's loan statement.
DOC_LOAN_RELEASE_REGISTER = "loan_release_register"
#: The per-unit cost-of-sale / margin relief schedule.
DOC_COS_SCHEDULE = "cos_schedule"
#: The per-unit tie-out determination.
DOC_CLOSING_SUMMARY = "closing_summary"
#: The project close-of-escrow rollup.
DOC_CLOSING_REPORT = "closing_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_UNIT_REGISTER,
    DOC_PROFORMA_ASSUMPTIONS,
    DOC_SETTLEMENT_REGISTER,
    DOC_CLOSING_JE_REGISTER,
    DOC_REVENUE_SCHEDULE,
    DOC_LOAN_RELEASE_REGISTER,
    DOC_COS_SCHEDULE,
    DOC_CLOSING_SUMMARY,
    DOC_CLOSING_REPORT,
)

# --------------------------------------------------------------------------- #
# Closing vocabulary
# --------------------------------------------------------------------------- #
#: Unit sale status. Only a closed unit has reached close of escrow, so only a
#: closed unit requires a settlement, an entry, a revenue line and a loan
#: release; sold and unsold units carry none of those.
STATUS_UNSOLD = "unsold"
STATUS_SOLD = "sold"
STATUS_CLOSED = "closed"
UNIT_STATUSES: tuple[str, ...] = (STATUS_UNSOLD, STATUS_SOLD, STATUS_CLOSED)

#: The Accounts Receivable line is the balancing plug of the closing entry.
ACCOUNT_ACCOUNTS_RECEIVABLE = "Accounts Receivable"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a closing file or the whole run."""

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
        ``"ss_net_to_seller_recompute"``).
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
    """Everything a check needs about one closing file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the closing file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def project(self) -> str:
        """Fictional project whose close-of-escrow record the file carries."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future closing period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the closing file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A closing file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one closing file plus its rolled-up verdict."""

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
