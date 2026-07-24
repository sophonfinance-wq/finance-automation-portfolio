"""
Data model for the surety bond & collateral control engine.
===========================================================

The engine consumes **programme files**: one JSON file per review period for a
developer's surety bond programme, carrying the artifacts that programme emits.
Each source artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Why a bond programme is worth an engine
---------------------------------------
A residential developer cannot pull a permit, record a plat or turn a street over
to a city without posting surety. So the bonds pile up: a statutory licence bond
per operating entity, a performance bond per set of subdivision improvements, a
maintenance bond that runs for the warranty period after the city accepts the
work, a street-use bond for the right of way. Each has its own obligee, its own
term, its own premium, and -- this is the part that costs real money -- some of
them are collateralised with the developer's own cash.

The failure mode is quiet and expensive. A bond does its job, the city accepts the
work, the obligation ends, and the bond is marked released in the log. Nobody
sends a letter to the surety. The collateral stays where it is. There is no
invoice to chase and no aged payable to sort it, because the money is not owed to
anyone -- it is *already paid*, sitting in a surety's account, indistinguishable
from cash on the balance sheet until somebody reconciles the register to the
restricted-cash ledger and finds that a released bond still has a balance.

The second failure mode is the opposite: a bond everyone forgot is still live.
Premium keeps renewing on an obligation that ended two years ago, and the penal
sum keeps consuming the aggregate limit of the indemnity agreement -- so the next
project's bond gets declined for capacity the programme does not actually use.

So the controls here are lifecycle controls. A bond has a beginning, a term, an
obligation it secures, and an end; the collateral, the premium and the exposure
each have to follow that lifecycle, and each is checked against it rather than
against itself.

The clock is stated, never sampled
-----------------------------------
Every date comparison is made against ``as_of``, a date carried *in the programme
file*. The engine never reads the system clock. A control that asked
``date.today()`` would give a different answer tomorrow, and an engine whose
verdict depends on when it ran cannot be diffed, cached or reproduced.

Severity model
--------------
- ``FAIL`` -- a hard control failure (collateral outstanding on a released bond, a
  coverage gap between renewal terms, a penal sum over the facility limit, a
  register that does not tie to the collateral ledger).
- ``FLAG`` -- a human-review signal (a premium off the rate schedule, a bond
  approaching expiry, a reduction without a rider reference).
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
#: Every bond in the programme: penal sum, term, obligee, status, collateral.
DOC_BOND_REGISTER = "bond_register"
#: The projects bonds are posted for, and when their improvements were accepted.
DOC_PROJECT_REGISTER = "project_register"
#: The indemnity agreement: the surety, the aggregate limit, the indemnitors.
DOC_SURETY_FACILITY = "surety_facility"
#: Every collateral movement: cash posted to the surety, cash refunded back.
DOC_COLLATERAL_LEDGER = "collateral_ledger"
#: Every premium charge: initial, renewal, and return premium on a reduction.
DOC_PREMIUM_LEDGER = "premium_ledger"
#: The surety's rate card, by bond type, in basis points of the penal sum.
DOC_RATE_SCHEDULE = "rate_schedule"
#: Statutory minimums by jurisdiction and bond type, and the obligee each takes.
DOC_STATUTORY_TABLE = "statutory_table"
#: The general-ledger positions the programme has to tie to.
DOC_GL_POSITIONS = "gl_positions"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_SURETY_FACILITY,
    DOC_STATUTORY_TABLE,
    DOC_RATE_SCHEDULE,
    DOC_PROJECT_REGISTER,
    DOC_BOND_REGISTER,
    DOC_COLLATERAL_LEDGER,
    DOC_PREMIUM_LEDGER,
    DOC_GL_POSITIONS,
)

# --------------------------------------------------------------------------- #
# Bond vocabulary
# --------------------------------------------------------------------------- #
#: A statutory licence bond, held by a state agency against the contractor's
#: registration. Its penal sum is set by statute, not by the job.
BOND_LICENCE = "licence"
#: Secures completion of subdivision or site improvements for the municipality.
BOND_PERFORMANCE = "performance"
#: Runs for the warranty period *after* the municipality accepts the work.
BOND_MAINTENANCE = "maintenance"
#: Secures completion of a plat's improvements as a condition of recording.
BOND_COMPLETION = "completion"
#: Secures restoration of the public right of way under a use permit.
BOND_PERMIT = "permit"

BOND_TYPES: tuple[str, ...] = (
    BOND_LICENCE,
    BOND_PERFORMANCE,
    BOND_MAINTENANCE,
    BOND_COMPLETION,
    BOND_PERMIT,
)

#: Bond types issued against a permit or plat, which must carry its number. A
#: licence bond is deliberately absent: it secures a registration, not a permit.
PERMIT_LINKED_TYPES: tuple[str, ...] = (
    BOND_PERFORMANCE,
    BOND_MAINTENANCE,
    BOND_COMPLETION,
    BOND_PERMIT,
)

#: The kind of body that holds a bond. A licence bond is held by a state agency;
#: everything else in this programme is held by the permitting municipality.
OBLIGEE_STATE = "state_agency"
OBLIGEE_MUNICIPAL = "municipality"
OBLIGEE_KINDS: tuple[str, ...] = (OBLIGEE_STATE, OBLIGEE_MUNICIPAL)

#: Bond lifecycle states.
STATUS_PENDING = "pending"  # applied for, not yet issued
STATUS_ACTIVE = "active"  # issued and in force
STATUS_RELEASED = "released"  # obligee has discharged the obligation
STATUS_EXPIRED = "expired"  # term ran out without a release
BOND_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_ACTIVE,
    STATUS_RELEASED,
    STATUS_EXPIRED,
)

#: Collateral ledger entry types.
COLL_POSTED = "posted"
COLL_REFUNDED = "refunded"
COLLATERAL_ENTRY_TYPES: tuple[str, ...] = (COLL_POSTED, COLL_REFUNDED)

#: Premium ledger entry types.
PREM_INITIAL = "initial"
PREM_RENEWAL = "renewal"
PREM_RETURN = "return"  # credit on a reduction in penal sum
PREMIUM_ENTRY_TYPES: tuple[str, ...] = (PREM_INITIAL, PREM_RENEWAL, PREM_RETURN)

#: Age bands, in days, for collateral still outstanding after a bond is released.
#: The bands are reported so a stale refund escalates on its age rather than
#: sitting at one undifferentiated severity forever.
COLLATERAL_AGE_BANDS: tuple[int, ...] = (30, 90, 180, 365)

#: A bond inside this many days of expiring is surfaced for renewal or release.
EXPIRY_HORIZON_DAYS = 60


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
        ``"coll_released_bond_refunded"``).
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
        """Fictional bond programme the file belongs to."""
        value = self.data.get("programme")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future review period label (``YYYY-Qn``)."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every age and expiry test is made against.

        Carried in the file, never sampled from the system clock, so the verdict
        is a property of the data rather than of the day the engine ran.
        """
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
