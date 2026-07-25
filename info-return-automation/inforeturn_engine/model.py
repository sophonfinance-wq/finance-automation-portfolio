"""
Data model for the information-return issuance control engine.
==============================================================

The engine consumes **reporting files**: one JSON file per group's annual
information-return cycle, carrying the artifacts that cycle emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: issuance, not payment
----------------------------
This engine is the reporting half of the vendor story. Whether an invoice was
approved and paid is a *disbursement* question, and a separate engine owns it --
and that engine explicitly declines to ask whether the payment it released was
reportable. This engine is that question. Once a year the group has to reassemble,
entity by entity, every payee it paid something reportable to -- interest to
lenders and affiliates, non-employee compensation to vendors, card and
third-party settlement -- apply the box threshold, issue a form, and reconcile
each box back to the ledger it came from. Nothing here files or transmits
anything; the question is narrower and entirely evidentiary: does the set of
forms about to go out match the payments the ledger actually recorded?

Why that is worth an engine
---------------------------
The population is rebuilt from scratch every year, across many project entities,
and it is rebuilt from a ledger that was never organised around who has to
receive a form.

Three things go wrong, and none of them look wrong.

**A payee is missed.** A vendor paid across two entities clears the threshold in
one of them and no form is cut, or a payee with no taxpayer number on file is
paid and no backup withholding is taken. Nothing in the ledger objects: the
payment posted, the invoice closed, and the omission is only visible if somebody
re-runs the threshold over the whole year.

**A box does not tie the ledger.** The form is issued, but the box amount is a
figure re-keyed from a summary rather than footed from the entity's own payment
lines -- so the payee is told one number and the ledger holds another.

**The transmittal drifts from the forms.** The form count or the reported total
on the transmittal is maintained beside the register rather than footed from it,
and the annual rollup inherits the drift.

So the controls here are reconciliation controls. Every form is re-derived from
the ledger, the threshold and the payee's taxpayer number, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a required form not issued, a form issued
  where none is due, a box that does not tie the ledger, a duplicate form,
  withholding that does not recompute, a transmittal that does not foot).
- ``FLAG`` -- a human-review signal (a payee sitting just under a box threshold,
  a near-threshold watchlist that does not tie the evidence).
- ``PASS`` -- the rule ran and the control held.

A reporting file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
roll up to ``REVIEW``; everything clean is ``PASS``.

All shipped data is fictional. The engine never writes to a source artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Document type vocabulary
# --------------------------------------------------------------------------- #
#: The payer entities that issue returns in their own name.
DOC_ENTITY_REGISTER = "entity_register"
#: Every payee in this year's population, with its taxpayer number if on file.
DOC_PAYEE_REGISTER = "payee_register"
#: The reportable boxes, their thresholds and whether withholding attaches.
DOC_BOX_CATALOG = "box_catalog"
#: Every reportable payment line the ledger recorded, by entity and box.
DOC_LEDGER_EXTRACT = "ledger_extract"
#: Every information return the cycle is about to issue.
DOC_FORM_REGISTER = "form_register"
#: The per-entity transmittal that accompanies its forms.
DOC_TRANSMITTAL_REGISTER = "transmittal_register"
#: Payees sitting just under a box threshold, held for review.
DOC_THRESHOLD_WATCHLIST = "threshold_watchlist"
#: The annual issuance rollup across every entity.
DOC_ISSUANCE_REPORT = "issuance_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_REGISTER,
    DOC_PAYEE_REGISTER,
    DOC_BOX_CATALOG,
    DOC_LEDGER_EXTRACT,
    DOC_FORM_REGISTER,
    DOC_TRANSMITTAL_REGISTER,
    DOC_THRESHOLD_WATCHLIST,
    DOC_ISSUANCE_REPORT,
)

# --------------------------------------------------------------------------- #
# Information-reporting vocabulary
# --------------------------------------------------------------------------- #
#: Return series. Every designation here is invented for this engine.
FORM_INTEREST = "interest_return"
FORM_NONEMPLOYEE = "nonemployee_compensation_return"
FORM_CARD_SETTLEMENT = "card_settlement_return"
FORM_TYPES: tuple[str, ...] = (
    FORM_INTEREST,
    FORM_NONEMPLOYEE,
    FORM_CARD_SETTLEMENT,
)

#: Payee classes. The class does not drive the threshold -- the box does -- but a
#: payee whose class is unknown was never characterised, and an uncharacterised
#: payee is one nobody decided the reporting treatment for.
PAYEE_LENDER = "lender"
PAYEE_AFFILIATE = "affiliate"
PAYEE_VENDOR = "vendor"
PAYEE_SETTLEMENT_ENTITY = "settlement_entity"
PAYEE_TYPES: tuple[str, ...] = (
    PAYEE_LENDER,
    PAYEE_AFFILIATE,
    PAYEE_VENDOR,
    PAYEE_SETTLEMENT_ENTITY,
)

#: Statutory backup-withholding rate, in basis points, for the fictional regime
#: modelled here, used when a reporting file does not carry its own.
DEFAULT_BACKUP_WITHHOLDING_BPS = 2500

#: Default band, in cents, below a box threshold inside which a payee is held for
#: review rather than ignored. A payee sitting this close to a threshold tips over
#: it the moment a late invoice posts to the year.
DEFAULT_NEAR_THRESHOLD_CENTS = 5000


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a reporting file or the whole run."""

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
        ``"frm_box_ties_ledger"``).
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
    """Everything a check needs about one reporting file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the reporting file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional group whose annual issuance cycle the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated issuance review date the cycle is measured at."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def reporting_year(self) -> int | None:
        """Calendar year the return population is assembled for.

        Returns ``None`` when the field is absent or malformed, so
        ``set_complete`` owns the finding and the date controls stand down rather
        than measuring payments against a year they had to invent.
        """
        value = self.data.get("reporting_year")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if value < 1 or value > 9999:
            return None
        return value

    @property
    def year_start(self) -> date | None:
        """First day of the reporting year, or ``None`` if the year is unreadable."""
        year = self.reporting_year
        return date(year, 1, 1) if year is not None else None

    @property
    def year_end(self) -> date | None:
        """Last day of the reporting year, or ``None`` if the year is unreadable."""
        year = self.reporting_year
        return date(year, 12, 31) if year is not None else None

    @property
    def backup_withholding_bps(self) -> int:
        """Statutory backup-withholding rate, in basis points.

        Read from the file when present so the rate comes from the data, falling
        back to :data:`DEFAULT_BACKUP_WITHHOLDING_BPS` when it is absent or
        malformed.
        """
        value = self.data.get("backup_withholding_bps")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_BACKUP_WITHHOLDING_BPS
        return value

    @property
    def near_threshold_cents(self) -> int:
        """Review band, in cents, below a box threshold."""
        value = self.data.get("near_threshold_cents")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_NEAR_THRESHOLD_CENTS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the reporting file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A reporting file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one reporting file plus its rolled-up verdict."""

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
