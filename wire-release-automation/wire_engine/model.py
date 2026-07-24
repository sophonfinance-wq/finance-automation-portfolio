"""
Data model for the wire & transfer release-control engine.
==========================================================

The engine consumes **release-control files**: one JSON file per operating
entity's outbound-payment record, carrying the artifacts that record emits. Each
source artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: releasing a payment, not booking it
------------------------------------------
This engine is the control layer that sits in front of the wire room. Where a
transfer finally lands in the general ledger is a *booking* question owned by a
separate engine -- and that engine assumes the money was allowed to leave. This
engine is that gate. Before any outbound wire, ACH or book transfer is released,
someone has to prove -- packet by packet -- that two different people signed it,
that the beneficiary is the one the entity meant to pay, that the receiving bank
is real and named correctly, that the funding account can cover it, that it is
not a second copy of a payment already sent, and that it moved through the
three-stage workflow in order. Nothing here books a cash entry; the question
here is narrower and entirely preventive: is this payment *safe to release*?

Why that is worth an engine
---------------------------
A wire is irreversible the moment it posts, and the ways one goes wrong all look
ordinary in a folder of one-page wire forms.

Three things go wrong, and none of them look wrong.

**The same person moves the money end to end.** One name initiates and authorizes
the same packet, or the second signature and its date were never filled in before
the packet left the pending tray -- and the segregation of duties the wire room
exists to enforce was never actually enforced.

**The money goes to the wrong account.** The beneficiary triplet on the form does
not match the approved template, or a first-time or changed bank detail was
released with no callback to verify it, or the routing number fails its own
check-digit or names a bank it does not resolve to. The form looks complete; the
money lands somewhere it should not.

**The release log drifts from the evidence.** The daily released-wire log calls a
packet releasable, or counts a batch as clear, on a determination nobody
recomputed from the signatures, limits and templates underneath it.

So the controls here are preventive controls. Every packet's releasable
determination is recomputed from the signers, the beneficiary templates and the
funding accounts, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (one signer on both roles, an incomplete
  secondary authorization, a beneficiary off template or a changed detail without
  callback, a routing checksum or bank-name mismatch, a funding shortfall, a
  duplicate payment, a skipped workflow stage, or a release flag or count that
  does not recompute).
- ``FLAG`` -- a human-review signal (an off-template beneficiary that did clear
  callback but is new and warrants a second look before release).
- ``PASS`` -- the rule ran and the control held.

A release-control file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
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
#: Every funding (From) account, with its available balance for the release date.
DOC_ACCOUNT_REGISTER = "account_register"
#: Every authorized signer, keyed by account, with a dollar authority limit.
DOC_SIGNER_REGISTER = "signer_register"
#: Routing-number to receiving-bank-name directory (the bank-name source of truth).
DOC_BANK_DIRECTORY = "bank_directory"
#: Approved-beneficiary whitelist: one template per approved (ABA, account, name).
DOC_BENEFICIARY_REGISTER = "beneficiary_register"
#: Every outbound wire / book-transfer packet awaiting or past release.
DOC_WIRE_REGISTER = "wire_register"
#: The posted-wire log: payments already executed.
DOC_POSTED_LOG = "posted_log"
#: The per-packet releasable determination.
DOC_RELEASE_SUMMARY = "release_summary"
#: The daily release rollup (releasable / blocked counts).
DOC_RELEASE_REPORT = "release_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ACCOUNT_REGISTER,
    DOC_SIGNER_REGISTER,
    DOC_BANK_DIRECTORY,
    DOC_BENEFICIARY_REGISTER,
    DOC_WIRE_REGISTER,
    DOC_POSTED_LOG,
    DOC_RELEASE_SUMMARY,
    DOC_RELEASE_REPORT,
)

# --------------------------------------------------------------------------- #
# Release vocabulary
# --------------------------------------------------------------------------- #
#: Request types. External wires carry routing detail; internal book transfers do
#: not, and the two are held to different controls.
REQUEST_WIRE = "wire"
REQUEST_BOOK_TRANSFER = "book_transfer"
REQUEST_TYPES: tuple[str, ...] = (REQUEST_WIRE, REQUEST_BOOK_TRANSFER)

#: Workflow stages, in the order a packet must traverse them.
STAGE_PENDING = "pending_secondary_approval"
STAGE_SCHEDULED = "approved_scheduled"
STAGE_POSTED = "posted"
STAGES: tuple[str, ...] = (STAGE_PENDING, STAGE_SCHEDULED, STAGE_POSTED)

#: Default window, in days, for the duplicate-payment check when a file does not
#: carry its own. A pending/scheduled packet whose (beneficiary, amount) matches a
#: posted payment within this many days of it is a suspected duplicate.
DEFAULT_DUPLICATE_WINDOW_DAYS = 5


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a release-control file or the whole run."""

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
        ``"sod_two_distinct_signers"``).
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
    """Everything a check needs about one release-control file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the release-control file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def entity(self) -> str:
        """Fictional operating entity whose release record the file carries."""
        value = self.data.get("entity")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future release period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated release/review date the daily log is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def duplicate_window_days(self) -> int:
        """Window, in days, for the duplicate-payment check.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_DUPLICATE_WINDOW_DAYS` when it is absent or
        malformed.
        """
        value = self.data.get("duplicate_window_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_DUPLICATE_WINDOW_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the release-control file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A release-control file carries exactly one of each artifact. Returning
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
    """All findings for one release-control file plus its rolled-up verdict."""

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
