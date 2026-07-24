"""
Data model for the filing-obligation calendar control engine.
=============================================================

The engine consumes **calendar files**: one JSON file per fiscal-year filing
record, carrying the artifacts that record emits. Each source artifact is
modelled as a typed document -- a dict with a ``doc_type`` discriminator and
typed fields -- so the whole engine stays stdlib-only, deterministic and
byte-stable.

Scope: the calendar, not the return
------------------------------------
This engine does not prepare a tax return, compute a tax, or move a payment. It
answers a narrower, entirely evidentiary question: for every entity, in every
jurisdiction, was each return or payment obligation *filed or validly extended
before its statutory due date*, was each fixed-amount payment made in the exact
amount the statute prints on the voucher, and does the status register tie to the
filed evidence with no missing or orphaned obligations?

Why that is worth an engine
---------------------------
A filing calendar is a matrix of dates that was correct the day someone typed it,
and it goes wrong in ways nobody watches until a notice arrives.

**The due date drifts.** An original or extended due date is typed a day off, or
an extension offset is applied to the wrong form, and the whole register keys its
follow-up off a deadline that is not the statutory one.

**The deadline passes.** An obligation is neither filed nor extended, its due date
slides past the review date, and it sits in the register looking like every other
open row -- until it is a late-filing penalty.

**The evidence and the register part company.** A row is marked filed with a
receipt number but no voucher was ever archived, or a voucher sits in the archive
with no row that claims it, and the count of "done" no longer means what it says.

**The fixed amount is not fixed.** The annual LLC tax is a statutory constant; a
voucher cut for a cent more or less than that constant is wrong on its face.

So the controls here recompute. Every due date is re-derived from the form and the
year-end against the statutory table and compared to the register; every
obligation's status is rebuilt from its dates; every fixed payment is checked
against the exact statutory amount; every filed row is tied to a piece of
evidence, and every piece of evidence back to a row.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a due date that does not re-derive, an
  overdue or late obligation, a fixed amount that is not the statutory constant,
  a filed row with no evidence or evidence with no row, a roster gap, a status or
  count that does not recompute, a final entity carrying a live obligation, an
  out-of-order workflow schedule).
- ``FLAG`` -- a human-review signal (an unfiled obligation falling due inside the
  lead-time window, an internal workflow actual that slipped past its goal, a
  due-soon watchlist that does not tie the register).
- ``PASS`` -- the rule ran and the control held.

A calendar file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every entity subject to a filing obligation, with its EIN and active flag.
DOC_ENTITY_ROSTER = "entity_roster"
#: The statutory Due Dates lookup: form x year-end -> original/extended offsets.
DOC_DUE_DATES_TABLE = "due_dates_table"
#: The obligation register (the Tax-Return-Status matrix), one row per obligation.
DOC_OBLIGATION_REGISTER = "obligation_register"
#: Filed vouchers and extension acceptances, keyed to the obligation they prove.
DOC_EVIDENCE_INDEX = "evidence_index"
#: Entities marked FINAL in the prior fiscal year (the cross-year baseline).
DOC_PRIOR_YEAR_REGISTER = "prior_year_register"
#: The per-obligation status roll-up and portfolio counts.
DOC_STATUS_SUMMARY = "status_summary"
#: Unfiled obligations falling due inside the lead-time window.
DOC_DUE_WATCHLIST = "due_watchlist"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_ROSTER,
    DOC_DUE_DATES_TABLE,
    DOC_OBLIGATION_REGISTER,
    DOC_EVIDENCE_INDEX,
    DOC_PRIOR_YEAR_REGISTER,
    DOC_STATUS_SUMMARY,
    DOC_DUE_WATCHLIST,
)

# --------------------------------------------------------------------------- #
# Filing vocabulary
# --------------------------------------------------------------------------- #
#: Evidence kinds. A filed return or a made payment proves an obligation was met;
#: an extension acceptance proves an obligation was validly deferred.
EVIDENCE_RETURN = "return"
EVIDENCE_PAYMENT = "payment"
EVIDENCE_EXTENSION = "extension"
EVIDENCE_KINDS: tuple[str, ...] = (
    EVIDENCE_RETURN,
    EVIDENCE_PAYMENT,
    EVIDENCE_EXTENSION,
)

#: Evidence kinds that prove an obligation was satisfied (as opposed to deferred).
FILING_EVIDENCE_KINDS: tuple[str, ...] = (EVIDENCE_RETURN, EVIDENCE_PAYMENT)

#: Default lead-time, in days, for the due-date watchlist when a file does not
#: carry its own. An unfiled obligation falling due inside this window is a FLAG,
#: not a failure -- there is still time to file.
DEFAULT_DUE_LEAD_DAYS = 30


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a calendar file or the whole run."""

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
        ``"ext_applicable_overdue"``).
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
    """Everything a check needs about one calendar file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the calendar file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional filing group whose calendar the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future fiscal-year label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every due-date and overdue test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def due_lead_days(self) -> int:
        """Lead-time window, in days, for the due-date watchlist.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_DUE_LEAD_DAYS` when it is absent or malformed.
        """
        value = self.data.get("due_lead_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_DUE_LEAD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the calendar file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A calendar file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one calendar file plus its rolled-up verdict."""

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
