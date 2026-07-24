"""
Data model for the depreciation & prepaid amortization control engine.
======================================================================

The engine consumes **close files**: one JSON file per entity per close month,
carrying the artifacts a month-end fixed-asset and prepaid close emits. Each
source artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: the register, not the close cadence
------------------------------------------
This engine re-derives and ties out the fixed-asset and prepaid (non-insurance)
subledgers. It does **not** claim the JE-posting / close-checklist cadence, debt
or loan amortization, or the prepaid-insurance entity allocation -- each of those
is a neighbouring engine's job. The question here is narrower and entirely
arithmetical: does every figure on the depreciation register and the prepaid
schedule re-derive from cost, life, convention and the stated amortization
window, and do the register totals tie the GL control accounts and the recurring
journal entry?

Why that is worth an engine
---------------------------
A depreciation register is a spreadsheet of tiny derived numbers, and it drifts
in ways nobody watches.

Three things go wrong, and none of them look wrong.

**The derivation drifts.** A useful life is keyed off the class table, a monthly
charge is overtyped, an asset keeps depreciating past its end date or starts
before it is in service, and every downstream month inherits the error. The
register still foots; the arithmetic underneath it is simply not the stated
convention.

**The roll-forward breaks.** Accumulated depreciation is a running balance --
opening plus the month's charge less what a disposal removed equals closing --
and a balance maintained by hand drifts the first time a row is edited and
nobody re-adds the column. Prepaid balances break the same way.

**The totals stop tying.** The register says one number, the GL control account
says another, and the recurring JE posts a third. Each looks plausible alone;
the tie-out is the only thing that can say they are the same number.

So the controls here are re-derivation controls. Every monthly charge, every
accumulated balance, every net book value and every prepaid waterfall figure is
recomputed from the base facts through one shared kernel, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a stated figure that does not re-derive, a
  roll-forward that does not close, a register total that does not tie the GL or
  the recurring JE, a sub-threshold item capitalized).
- ``FLAG`` -- a human-review signal (an asset fully depreciated long past its end
  date and still on the register, a prepaid window about to end).
- ``PASS`` -- the rule ran and the control held.

A close file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every capitalized asset, with its stated derivation columns.
DOC_ASSET_REGISTER = "fixed_asset_register"
#: Useful life and method by asset class.
DOC_LIFE_TABLE = "useful_life_table"
#: The capitalization threshold, the excluded categories, and the expense log.
DOC_CAP_POLICY = "capitalization_policy"
#: Every prepaid item, with its stated amortization waterfall columns.
DOC_PREPAID_REGISTER = "prepaid_register"
#: Assets disposed of, with the write-off each disposal booked.
DOC_DISPOSAL_REGISTER = "disposal_register"
#: The accumulated-depreciation and prepaid-balance roll-forwards.
DOC_ROLLFORWARD = "rollforward_schedule"
#: The GL control-account balances the registers must tie to.
DOC_GL_BALANCES = "gl_control_balances"
#: The posted monthly recurring journal entry.
DOC_RECURRING_JE = "recurring_je"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ASSET_REGISTER,
    DOC_LIFE_TABLE,
    DOC_CAP_POLICY,
    DOC_PREPAID_REGISTER,
    DOC_DISPOSAL_REGISTER,
    DOC_ROLLFORWARD,
    DOC_GL_BALANCES,
    DOC_RECURRING_JE,
)

# --------------------------------------------------------------------------- #
# Register vocabulary
# --------------------------------------------------------------------------- #
#: The only depreciation method these books use. Method is carried per asset so
#: a tax-basis method could extend the model later -- as a parameter, never a
#: judgment call.
METHOD_STRAIGHT_LINE = "straight_line"

#: A class whose life is fixed by the class table.
LIFE_SOURCE_FIXED = "fixed"
#: A class (leasehold improvements) whose life is the asset's own lease term.
LIFE_SOURCE_LEASE_TERM = "lease_term"
LIFE_SOURCES: tuple[str, ...] = (LIFE_SOURCE_FIXED, LIFE_SOURCE_LEASE_TERM)

#: GL control accounts (fictional chart of accounts).
GL_COST = "1610"
GL_ACCUM = "1611"
GL_PREPAID = "1420"
#: Recurring-JE line ids the register totals must tie to.
JE_DEPRECIATION = "JE-DEP"
JE_AMORTIZATION = "JE-AMORT"

#: Default number of months an asset may sit fully depreciated on the register
#: before it is flagged for disposal review, when the file carries no figure.
DEFAULT_DISPOSAL_REVIEW_MONTHS = 12
#: Default look-ahead, in months, for the prepaid window-ending watch.
DEFAULT_PREPAID_WATCH_MONTHS = 1


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a close file or the whole run."""

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
        ``"nbv_accum_rederives"``).
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
    """Everything a check needs about one close file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the close file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def entity(self) -> str:
        """Fictional entity whose registers the file carries."""
        value = self.data.get("entity")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future fiscal period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def close_month(self) -> str:
        """The stated close month every derivation is measured to (``YYYY-MM``)."""
        value = self.data.get("close_month")
        return str(value) if isinstance(value, str) else "-"

    @property
    def disposal_review_months(self) -> int:
        """Months an asset may sit fully depreciated before the disposal watch.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_DISPOSAL_REVIEW_MONTHS` when absent or malformed.
        """
        value = self.data.get("disposal_review_months")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_DISPOSAL_REVIEW_MONTHS
        return value

    @property
    def prepaid_watch_months(self) -> int:
        """Look-ahead window, in months, for the prepaid window-ending watch."""
        value = self.data.get("prepaid_watch_months")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_PREPAID_WATCH_MONTHS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the close file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A close file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one close file plus its rolled-up verdict."""

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
