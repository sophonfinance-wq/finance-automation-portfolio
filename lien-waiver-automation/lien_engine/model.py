"""
Data model for the mechanics-lien waiver tracking control engine.
=================================================================

The engine consumes **portfolio files**: one JSON file per developer's waiver
book for a construction period, carrying the artifacts that the subcontractor
payment cycle emits. Each source artifact is modelled as a typed document -- a
dict with a ``doc_type`` discriminator and typed fields -- so the whole engine
stays stdlib-only, deterministic and byte-stable.

Scope: waiver coverage, not payment release
--------------------------------------------
This engine is about **whether a lien waiver stands behind every dollar already
paid**. Whether an invoice is approved, three-way matched and inside its budget
is a payment question, and it belongs to the accounts-payable gate. Nothing here
re-authorises a payment. The question here is narrower and entirely about
coverage: a progress payment has gone out to a subcontractor, and there must be a
lien waiver -- of the right kind, through the right date, for the right amount --
standing behind it, all the way down the tier chain, so that no lien survives to
attach to the developer's title.

Why that is worth an engine
---------------------------
A developer pays a general contractor, who pays subcontractors, who pay their own
lower-tier subs and material suppliers. Every one of those parties can file a
mechanics lien against the project. A lien waiver is the release that gives it
up, and the waiver has to march in lockstep with the money:

**The conditional that never became unconditional.** A subcontractor signs a
*conditional* waiver when it is paid -- conditional on the payment actually
clearing. Once the cheque clears, it owes an *unconditional* waiver. The cheque
clears; the unconditional waiver is never chased; the file looks complete because
*a* waiver is on record. The lien right is still live.

**The coverage that stops short of the money.** A waiver runs through a date. If a
payment covers work through the end of February but the waiver only releases
through the end of January, the last month of paid work is unwaived, and nobody
notices because there is a waiver in the folder.

**The tier nobody waived.** The subcontractor waived. Its own rebar supplier,
paid out of that same progress payment, did not. A downstream lien survives the
upstream release, and it attaches to the same title.

So the controls here are coverage controls. Every cleared payment is matched to
an unconditional waiver that runs at least as far as the money did; every
lower-tier party required to release is checked against the date its parent was
paid through; and the unwaived exposure per project is re-derived rather than
trusted.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a cleared payment with no unconditional
  waiver, a waiver whose amount does not tie the payment, a lower-tier party that
  never released, an exposure figure that does not re-derive).
- ``FLAG`` -- a human-review signal (a conditional waiver aging past the point it
  should have been upgraded, a reported count that does not reconcile).
- ``PASS`` -- the rule ran and the control held.

A portfolio file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every subcontract in the tier chain: sub id, tier, parent, project.
DOC_CONTRACT_REGISTER = "contract_register"
#: Each progress payment: sub, project, period, paid-through date, amount, clear.
DOC_PAYMENT_REGISTER = "payment_register"
#: Each lien waiver: id, sub, type, through-date, amount, the payment it backs.
DOC_WAIVER_REGISTER = "waiver_register"
#: The lower-tier parties every tier-1 sub must obtain a release from.
DOC_LOWER_TIER_REGISTER = "lower_tier_register"
#: Unwaived exposure per project (the tie-out figure).
DOC_EXPOSURE_SUMMARY = "exposure_summary"
#: The waiver-log roll-up whose counts must reconcile.
DOC_WAIVER_LOG = "waiver_log"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_CONTRACT_REGISTER,
    DOC_PAYMENT_REGISTER,
    DOC_WAIVER_REGISTER,
    DOC_LOWER_TIER_REGISTER,
    DOC_EXPOSURE_SUMMARY,
    DOC_WAIVER_LOG,
)

# --------------------------------------------------------------------------- #
# Waiver vocabulary
# --------------------------------------------------------------------------- #
#: Signed when the sub is paid, conditional on the payment clearing.
WAIVER_CONDITIONAL = "conditional"
#: Owed once the payment has cleared; the release that actually stands.
WAIVER_UNCONDITIONAL = "unconditional"
WAIVER_TYPES: tuple[str, ...] = (WAIVER_CONDITIONAL, WAIVER_UNCONDITIONAL)

#: The lowest valid tier. A tier is a whole number >= 1.
TIER_MIN = 1

#: Projects the portfolio may reference. A project outside this set is a typo, and
#: a typo silently drops the party that carried it out of every coverage test.
PROJECTS: tuple[str, ...] = (
    "Brightwater Commons",
    "Copperfield Yards",
    "Alderpoint Terraces",
    "Dunmore Flats",
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
    """Overall verdict for a portfolio file or the whole run."""

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
        ``"cov_cleared_unconditional"``).
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
    """Everything a check needs about one portfolio file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the portfolio file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose waiver book the file belongs to."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future construction period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every coverage and ageing test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the portfolio file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A portfolio file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one portfolio file plus its rolled-up verdict."""

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
