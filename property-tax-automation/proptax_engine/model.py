"""
Data model for the property tax control engine.
===============================================

The engine consumes **roll files**: one JSON file per tax year for a developer's
parcels, carrying the artifacts a property tax cycle emits. Each source artifact
is modelled as a typed document -- a dict with a ``doc_type`` discriminator and
typed fields -- so the whole engine stays stdlib-only, deterministic and
byte-stable.

Why property tax is worth an engine
-----------------------------------
A homebuilder's property tax problem is not the arithmetic on one bill. It is that
the unit of taxation and the unit of ownership drift apart, continuously, in a
direction nobody is watching.

A project starts as one parent parcel. It is platted, and becomes forty. The
county assessor picks the split up on its own schedule, which is not the
developer's. Then the units start closing -- one at a time, over eighteen months --
and each closing moves exactly one parcel off the developer's books while the tax
roll keeps billing the same account it always has. The bill still arrives. It
still looks right. It is simply, increasingly, for somebody else's houses.

Nothing in the payables cycle catches this. The invoice is genuine, the payee is
genuinely the county, the amount genuinely matches the notice. The only thing
wrong is *whose parcel it is*, and that fact lives in a closing file the person
approving the payment has never seen.

The second problem is the calendar. A developer operating across state lines is
subject to regimes that share no dates, no instalment count and no penalty
arithmetic. Applying one jurisdiction's habits to another's parcel is how a
delinquency is discovered after the penalty has already attached.

So the controls here are ownership and calendar controls. A parcel's tax follows
the parcel; the parcel follows a plat; the payment follows the ownership; and the
dates follow the jurisdiction's own regime, never a default.

Regimes are data, not code
--------------------------
Each jurisdiction carries a **regime profile**: when its fiscal year opens, how
many instalments it takes, when each falls due, and how penalty and interest
accrue once one is missed. Three shapes ship in the fictional corpus -- a
two-instalment spring/autumn regime on a calendar fiscal year, a two-instalment
regime on a mid-year fiscal year that raises a supplemental assessment on change
of ownership, and a single-instalment regime -- and nothing about them is
hard-coded into a control. A fourth would be a row, not a patch.

The clock is stated, never sampled
-----------------------------------
Every delinquency and ageing test is made against ``as_of``, a date carried *in
the roll file*. The engine never reads the system clock, so its verdict is a
property of the data rather than of the day it ran.

Severity model
--------------
- ``FAIL`` -- a hard control failure (tax paid on a parcel after it closed, a
  proration that does not sum to the annual charge, instalments that do not foot,
  a due date that is not the jurisdiction's).
- ``FLAG`` -- a human-review signal (an assessment jump worth protesting, a
  missing receipt, an exemption with no authority cited).
- ``PASS`` -- the rule ran and the control held.

A roll file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: Every parcel: its assessment, its annual charge, and who owns it now.
DOC_PARCEL_REGISTER = "parcel_register"
#: The projects parcels belong to, and how many lots each plat created.
DOC_PROJECT_REGISTER = "project_register"
#: Per-jurisdiction regime: fiscal year, instalments, due dates, penalty maths.
DOC_REGIME_TABLE = "regime_table"
#: Every instalment: what is due, when, what was paid and when.
DOC_INSTALMENT_SCHEDULE = "instalment_schedule"
#: Closings: which parcel left the books, when, and how the tax was prorated.
DOC_SALE_REGISTER = "sale_register"
#: The monthly accrual behind the liability.
DOC_ACCRUAL_LEDGER = "accrual_ledger"
#: The prior year's assessed values, for the protest-review comparison.
DOC_ASSESSMENT_HISTORY = "assessment_history"
#: The general-ledger positions the cycle has to tie to.
DOC_GL_POSITIONS = "gl_positions"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_REGIME_TABLE,
    DOC_PROJECT_REGISTER,
    DOC_PARCEL_REGISTER,
    DOC_ASSESSMENT_HISTORY,
    DOC_INSTALMENT_SCHEDULE,
    DOC_SALE_REGISTER,
    DOC_ACCRUAL_LEDGER,
    DOC_GL_POSITIONS,
)

# --------------------------------------------------------------------------- #
# Parcel vocabulary
# --------------------------------------------------------------------------- #
#: The developer still owns it, so the tax is the developer's.
PARCEL_HELD = "held"
#: It closed to a buyer; from close of escrow the tax is theirs.
PARCEL_SOLD = "sold"
#: The parent parcel of a plat, retired once its children are on the roll.
PARCEL_RETIRED = "retired"
PARCEL_STATUSES: tuple[str, ...] = (PARCEL_HELD, PARCEL_SOLD, PARCEL_RETIRED)

#: Project stages. Tax on a project still in development is capitalised into the
#: job; tax on a completed project is period expense.
STAGE_DEVELOPMENT = "development"
STAGE_COMPLETE = "complete"
PROJECT_STAGES: tuple[str, ...] = (STAGE_DEVELOPMENT, STAGE_COMPLETE)

#: Days in the tax year used for proration. A fixed 365-day convention is used
#: deliberately: settlement statements prorate on a stated convention, and a
#: convention the engine invents would disagree with the closing it is checking.
PRORATION_DAYS = 365

#: Interest on a delinquent instalment accrues per whole period of this many days
#: past the due date. Stated once, here, so every regime uses the same clock and
#: only the rate differs.
INTEREST_PERIOD_DAYS = 30

#: An assessed value moving more than this year over year is surfaced for a
#: protest review. It is a reporting threshold, not a rule of law.
ASSESSMENT_VARIANCE_BPS = 2500


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a roll file or the whole run."""

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
        ``"own_sold_parcel_not_paid"``).
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
    """Everything a check needs about one roll file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the roll file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional portfolio the roll file belongs to."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def tax_year(self) -> int | None:
        """The tax year every parcel in the file is assessed for."""
        value = self.data.get("tax_year")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def as_of(self) -> str:
        """The stated review date every delinquency test is made against."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the roll file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A roll file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one roll file plus its rolled-up verdict."""

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
