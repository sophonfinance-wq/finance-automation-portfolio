"""
Data model for the entity good-standing control engine.
========================================================

The engine consumes **standing files**: one JSON file per fictional entity
family's registration-compliance record, carrying the artifacts that record
emits. Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: registration, not tax computation
-----------------------------------------
This engine is about **whether each legal entity is in good standing in every
state it is formed or foreign-qualified in**, not about computing an income-tax
liability. A closely-held real-estate group forms one entity per project and
qualifies it into each state it operates in, and it has to prove, entity by
entity and state by state, that the annual/biennial report is filed on time, the
statutory franchise tax is paid in the exact amount by its due date, the
registered agent of record is the one under contract, and the Secretary-of-State
status is ACTIVE -- and that a wound-down entity has been cancelled in every
state it ever touched.

Why that is worth an engine
---------------------------
A good-standing record is a snapshot that was true the day the state produced it,
and it goes stale in ways nobody watches.

**The filing lapses.** The annual report or franchise-tax payment slips past its
statutory due date, so the entity drifts toward administrative suspension while
the internal register still shows it Active -- just late.

**The obligation is short or misdated.** The franchise tax is paid, but a dollar
under the flat statutory amount, or the stated due date does not match the one
the statute re-derives, or the registered agent named on the state's record is
not the agent actually under contract. The paper looks complete; the standing is
not there.

**The rollup drifts from the evidence.** The compliance report calls an entity in
good standing, or counts a family as clean, on a determination nobody recomputed
from the state records underneath it.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a required jurisdiction with no record, a
  report filed late, a franchise tax short of the statutory amount or paid late,
  a suspended status, a mismatched agent, an incomplete dissolution, a
  good-standing flag or count that does not recompute).
- ``FLAG`` -- a human-review signal (a filing due inside the lead-time window, a
  renewal watchlist that does not tie the evidence).
- ``PASS`` -- the rule ran and the control held.

A standing file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every legal entity in the family, with its formation and qualified states.
DOC_ENTITY_REGISTER = "entity_register"
#: Statutory obligations (report cadence, flat fees, due dates), keyed by state
#: and entity type.
DOC_JURISDICTION_MATRIX = "jurisdiction_matrix"
#: Every per-(entity, state) good-standing / filing record on file.
DOC_STANDING_RECORD_REGISTER = "standing_record_register"
#: The per-entity good-standing determination.
DOC_STANDING_SUMMARY = "standing_summary"
#: Filings due for renewal inside the lead-time window.
DOC_RENEWAL_WATCHLIST = "renewal_watchlist"
#: The family-level good-standing rollup.
DOC_COMPLIANCE_REPORT = "compliance_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_REGISTER,
    DOC_JURISDICTION_MATRIX,
    DOC_STANDING_RECORD_REGISTER,
    DOC_STANDING_SUMMARY,
    DOC_RENEWAL_WATCHLIST,
    DOC_COMPLIANCE_REPORT,
)

# --------------------------------------------------------------------------- #
# Registration vocabulary
# --------------------------------------------------------------------------- #
#: Entity types. Each keys a different row of the jurisdiction matrix per state.
ENTITY_LLC = "llc"
ENTITY_CORPORATION = "corporation"
ENTITY_LP = "lp"
ENTITY_TYPES: tuple[str, ...] = (
    ENTITY_LLC,
    ENTITY_CORPORATION,
    ENTITY_LP,
)

#: Internal register status. ``active`` entities carry live filing obligations;
#: ``dissolved`` entities must instead be fully cancelled in every state.
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_DISSOLVED = "dissolved"
ENTITY_STATUSES: tuple[str, ...] = (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_DISSOLVED,
)

#: Secretary-of-State reported status on a standing record.
SOS_ACTIVE = "ACTIVE"
SOS_SUSPENDED = "SUSPENDED"
SOS_DISSOLVED = "DISSOLVED"

#: Business-license status on a standing record.
LICENSE_CURRENT = "current"
LICENSE_LAPSED = "lapsed"

#: The fictional jurisdictions this corpus is registered in. Each carries its own
#: fixed statutory report/franchise due dates and flat fees, so a due date is a
#: pure re-derivation from the statute rather than a lookup nobody can check.
STATE_MARRAN = "Marran"
STATE_KELDER = "Kelder"
STATE_TOLVANE = "Tolvane"
STATE_VERRADO = "Verrado"
KNOWN_STATES: tuple[str, ...] = (
    STATE_MARRAN,
    STATE_KELDER,
    STATE_TOLVANE,
    STATE_VERRADO,
)

#: Default lead-time, in days, for the renewal watchlist when a file does not
#: carry its own. A filing due inside this window is a FLAG, not a failure --
#: there is still time to file.
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
    """Overall verdict for a standing file or the whole run."""

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
        ``"tax_amount_meets"``).
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
    """Everything a check needs about one standing file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the standing file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional entity family whose standing record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future compliance period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_year(self) -> int | None:
        """The filing year every statutory due date is re-derived against."""
        value = self.data.get("period_year")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @property
    def as_of(self) -> str:
        """The stated review date every currency and renewal test is measured to."""
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
        """Every document in the standing file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A standing file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one standing file plus its rolled-up verdict."""

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
