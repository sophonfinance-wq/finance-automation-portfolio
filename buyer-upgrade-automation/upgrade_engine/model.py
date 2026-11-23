"""
Data model for the buyer upgrade control engine.
================================================

The engine consumes **upgrade books**: one JSON file per project/period carrying
the artifacts a homebuilder's buyer-upgrade programme emits. Each source artifact
is modelled as a typed document -- a dict with a ``doc_type`` discriminator and
typed fields -- so the whole engine stays stdlib-only, deterministic and
byte-stable.

Why buyer upgrades are worth an engine
--------------------------------------
A buyer pays for an upgrade months before the home closes. That money is not
revenue when it arrives -- it is a liability, and it stays one until the unit
actually closes. Between those two dates the same figure has to appear
consistently in four places: the closings schedule, the general ledger, the
cost-to-complete report and the proforma. Each is maintained by a different
person on a different cadence, and each is a spreadsheet.

The failure mode is almost never a wrong number. It is the *same* number failing
to move everywhere at once: a unit closes and the deferred balance is released in
the schedule but not the ledger; an upgrade is repriced and the proforma keeps
the old figure; a change order is executed and the committed cost never lands.
Every one of those is a tie-out with a right answer.

Severity model
--------------
- ``FAIL`` -- a hard control failure (revenue recognised before the unit closed,
  a schedule that does not tie to the ledger, cost of sales that does not balance
  its contra credit).
- ``FLAG`` -- a human-review signal (a stale budgeted/actual flag, an upgrade
  approaching its committed cost, a missing change order reference).
- ``PASS`` -- the rule ran and the control held.

A book with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll up to
``REVIEW``; everything clean is ``PASS``.

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
#: The closings schedule: units, buyers, close dates and the revenue recognition tab.
DOC_CLOSINGS_SCHEDULE = "closings_schedule"
#: The upgrade order register: what each buyer selected, at what price, and when.
DOC_UPGRADE_REGISTER = "upgrade_order_register"
#: The cost-to-complete report's upgrade tab: revenue, committed cost, cost to date.
DOC_COST_TO_COMPLETE = "cost_to_complete_upgrades"
#: The proforma's upgrade lines: income and the job-cost line that offsets it.
DOC_PROFORMA = "proforma_upgrade_lines"
#: General ledger balances for the accounts the programme touches.
DOC_LEDGER_BALANCES = "ledger_balances"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_CLOSINGS_SCHEDULE,
    DOC_UPGRADE_REGISTER,
    DOC_COST_TO_COMPLETE,
    DOC_PROFORMA,
    DOC_LEDGER_BALANCES,
)

#: The unearned-revenue account an upgrade deposit lands in before the unit closes.
ACCT_UNEARNED = "unearned_revenue_upgrades"
#: Where upgrade revenue goes once the unit closes.
ACCT_REVENUE = "revenue_upgrades"
#: Cost of sales for upgrades.
ACCT_COST_OF_SALES = "cost_of_sales_upgrades"
#: The contra work-in-progress account the cost of sales is credited against.
ACCT_CONTRA_WIP = "contra_wip_upgrades"
#: Sales tax collected on an upgrade is a liability, never revenue.
ACCT_SALES_TAX = "sales_tax_payable"

ACCOUNTS: tuple[str, ...] = (
    ACCT_UNEARNED,
    ACCT_REVENUE,
    ACCT_COST_OF_SALES,
    ACCT_CONTRA_WIP,
    ACCT_SALES_TAX,
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
    """Overall verdict for an upgrade book or the whole run."""

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
        ``"def_released_only_on_close"``).
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
    """Everything a check needs about one upgrade book.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def book_id(self) -> str:
        """Identifier of the upgrade book (falls back to the file stem)."""
        value = self.data.get("book_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def project(self) -> str:
        """Fictional project the book belongs to."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future accounting period label (``YYYY-MM``)."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the book, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A book carries exactly one of each artifact. Returning ``None`` rather
        than raising lets ``set_complete`` own the "missing artifact" finding, so
        every downstream rule reports absence the same way instead of each
        inventing its own message.
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
    """All findings for one upgrade book plus its rolled-up verdict."""

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
