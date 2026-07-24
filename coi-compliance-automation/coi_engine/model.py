"""
Data model for the certificate-of-insurance (COI) compliance control engine.
============================================================================

The engine consumes **compliance files**: one JSON file per residential
developer's insurance-compliance record, carrying the artifacts that record
emits. Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: compliance, not allocation
---------------------------------
This engine is the other half of the insurance story. Where the master premium
lands on each project's job cost is an *allocation* question, and a separate
engine owns it -- and that engine explicitly declines to check whether a
certificate is on file. This engine is that check. A developer requires every
consultant (architect/engineer), general contractor and subcontractor it hires
to carry insurance per contract, and it has to prove, party by party, that each
one's certificate of insurance is on file, unexpired, and meets the
contract-required coverage. Nothing here allocates a cost; the question here is
narrower and entirely evidentiary: does the paper in the file actually satisfy
what the contract demanded?

Why that is worth an engine
---------------------------
A COI is a one-page snapshot of coverage that was true on the day the broker
issued it, and it goes stale in ways nobody watches.

Three things go wrong, and none of them look wrong.

**The certificate lapses.** A policy expires and the renewal certificate never
arrives, so the party is uninsured on the developer's own job while its file
still shows a certificate -- just an expired one. Between two valid renewal
certificates the same gap can open for a single day, and an occurrence lands in
it with nothing to respond.

**The limits fall short of the contract.** The certificate is current, but the
per-occurrence or aggregate limit is below what the contract required for that
party type, or the additional-insured and waiver-of-subrogation endorsements the
contract demanded were never added. The paper looks complete; the protection is
not there.

**The compliance rollup drifts from the evidence.** The monthly report says a
party is compliant, or counts a portfolio as clean, on a determination nobody
recomputed from the certificates underneath it.

So the controls here are evidentiary controls. Every party's compliant flag is
recomputed from the certificates and the requirement matrix, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a required coverage with no certificate, a
  certificate that is expired or short of the required limit, a missing
  endorsement, a compliant flag or count that does not recompute).
- ``FLAG`` -- a human-review signal (a certificate due for renewal inside the
  lead-time window, a renewal watchlist that does not tie the evidence).
- ``PASS`` -- the rule ran and the control held.

A compliance file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every party the developer requires insurance from, with its required coverage.
DOC_PARTY_REGISTER = "party_register"
#: Required limits and endorsements, keyed by party type and coverage type.
DOC_REQUIREMENT_MATRIX = "requirement_matrix"
#: Every certificate of insurance on file.
DOC_CERTIFICATE_REGISTER = "certificate_register"
#: The per-party compliant determination.
DOC_COVERAGE_SUMMARY = "coverage_summary"
#: Certificates due for renewal inside the lead-time window.
DOC_RENEWAL_WATCHLIST = "renewal_watchlist"
#: The monthly portfolio compliance rollup.
DOC_COMPLIANCE_REPORT = "compliance_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PARTY_REGISTER,
    DOC_REQUIREMENT_MATRIX,
    DOC_CERTIFICATE_REGISTER,
    DOC_COVERAGE_SUMMARY,
    DOC_RENEWAL_WATCHLIST,
    DOC_COMPLIANCE_REPORT,
)

# --------------------------------------------------------------------------- #
# Compliance vocabulary
# --------------------------------------------------------------------------- #
#: Party types. Each requires a different set of coverages by contract.
PARTY_CONSULTANT = "consultant"
PARTY_GENERAL_CONTRACTOR = "general_contractor"
PARTY_SUBCONTRACTOR = "subcontractor"
PARTY_TYPES: tuple[str, ...] = (
    PARTY_CONSULTANT,
    PARTY_GENERAL_CONTRACTOR,
    PARTY_SUBCONTRACTOR,
)

#: Coverage lines a certificate can attest. Each requirement matrix row is keyed
#: by (party_type, coverage_type), so adding a line is a row -- never a control.
COVERAGE_CGL = "commercial_general_liability"
COVERAGE_AUTO = "automobile_liability"
COVERAGE_WORKERS_COMP = "workers_compensation"
COVERAGE_PROFESSIONAL = "professional_liability"
COVERAGE_UMBRELLA = "umbrella_excess"
COVERAGE_TYPES: tuple[str, ...] = (
    COVERAGE_CGL,
    COVERAGE_AUTO,
    COVERAGE_WORKERS_COMP,
    COVERAGE_PROFESSIONAL,
    COVERAGE_UMBRELLA,
)

#: Default lead-time, in days, for the renewal watchlist when a file does not
#: carry its own. A certificate expiring inside this window is a FLAG, not a
#: failure -- there is still time to renew.
DEFAULT_RENEWAL_LEAD_DAYS = 30


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a compliance file or the whole run."""

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
        ``"cov_required_present"``).
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
    """Everything a check needs about one compliance file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the compliance file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose compliance record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future compliance period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every expiry and renewal test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def renewal_lead_days(self) -> int:
        """Lead-time window, in days, for the renewal watchlist.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_RENEWAL_LEAD_DAYS` when it is absent or malformed.
        """
        value = self.data.get("renewal_lead_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_RENEWAL_LEAD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the compliance file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A compliance file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one compliance file plus its rolled-up verdict."""

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
