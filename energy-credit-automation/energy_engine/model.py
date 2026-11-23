"""
Data model for the Energy-Efficient Home Credit (IRC §45L) control engine.
=========================================================================

The engine consumes **credit files**: one JSON file per project-portfolio's
§45L homebuilder-credit record for a fiscal year, carrying the artifacts that
record emits. Each source artifact is modelled as a typed document -- a dict with
a ``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: the claim recomputes, it is not read back
------------------------------------------------
The §45L credit is a *per-unit* credit. A homebuilder earns a fixed statutory
amount for each newly constructed dwelling unit it sells, but only for a unit
that clears two gates at once: the unit closed (close-of-escrow) inside the
fiscal-year window being filed, **and** the unit holds an energy certificate from
a certified RESNET/HERS rater. The gross credit is nothing more than the count of
qualifying units times the dated statutory per-unit amount, and every figure
above it -- the profit addback, the tax effect at the effective rate, the net
benefit, the partner split -- is arithmetic on that product.

That is exactly what makes it worth an engine: the arithmetic is simple and the
places it silently drifts are many.

Three things go wrong, and none of them look wrong.

**A unit is claimed that should not be.** It closed outside the fiscal-year
window, or it closed after the statutory sunset, or it was never certified by a
rater -- yet it was counted in the credit anyway. The computation still foots;
the units underneath it do not qualify.

**A unit is counted twice.** The same dwelling unit is claimed in two successive
period filings, so a credit already taken is taken again. Each filing looks
internally consistent; the overlap is only visible across them.

**The rollup drifts from the units.** The worksheet's gross credit, the report's
certified-unit tie-out, the roll-forward identity, the net-benefit derivation or
the partner allocation is stated on a number nobody recomputed from the unit
register underneath it.

So the controls here are re-derivation controls. Every credit figure is rebuilt
from the unit register and the dated statutory rate, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a claimed unit outside the period or past
  the sunset or without a certificate, a unit double-counted across filings, a
  credit / tie-out / roll-forward / net-benefit / allocation figure that does not
  recompute).
- ``FLAG`` -- a human-review signal (units still remaining to close in a future
  period, a certification gap where more units closed than were certified and
  claimed).
- ``PASS`` -- the rule ran and the control held.

A credit file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: Per-unit eligibility register: one row per closed dwelling unit.
DOC_UNIT_REGISTER = "unit_register"
#: Per-project credit computation worksheet (units x rate -> net benefit).
DOC_CREDIT_WORKSHEET = "credit_worksheet"
#: Units-by-period roll-forward reconciliation.
DOC_PERIOD_ROLLFORWARD = "period_rollforward"
#: Partner allocation schedule (net benefit split by ownership).
DOC_PARTNER_ALLOCATION = "partner_allocation"
#: Closings schedule: physically closed units + prior-period claims.
DOC_CLOSINGS_SCHEDULE = "closings_schedule"
#: Final certification report (the certified-unit / total-credit face figures).
DOC_FINAL_REPORT = "final_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_UNIT_REGISTER,
    DOC_CREDIT_WORKSHEET,
    DOC_PERIOD_ROLLFORWARD,
    DOC_PARTNER_ALLOCATION,
    DOC_CLOSINGS_SCHEDULE,
    DOC_FINAL_REPORT,
)

# --------------------------------------------------------------------------- #
# §45L vocabulary
# --------------------------------------------------------------------------- #
#: The statutory per-unit credit amount, in dollars (pre-IRA §45L: $2,000).
DEFAULT_PER_UNIT_DOLLARS = 2_000

#: The effective tax rate applied to the credit's profit addback, in basis
#: points, when a file does not carry its own (21.00%).
DEFAULT_EFFECTIVE_RATE_BPS = 2_100


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a credit file or the whole run."""

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
        ``"rate_gross_credit"``).
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
    """Everything a check needs about one credit file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the credit file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional builder / portfolio whose §45L record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def fiscal_year(self) -> str:
        """Fictional-future fiscal-year label the credit is filed for."""
        value = self.data.get("fiscal_year")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_start(self) -> str:
        """First day of the fiscal-year close-of-escrow window (inclusive)."""
        value = self.data.get("period_start")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_end(self) -> str:
        """Last day of the fiscal-year close-of-escrow window (inclusive)."""
        value = self.data.get("period_end")
        return str(value) if isinstance(value, str) else "-"

    @property
    def sunset_date(self) -> str:
        """Statutory sunset: a unit closing after it cannot be claimed."""
        value = self.data.get("sunset_date")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the credit file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A credit file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one credit file plus its rolled-up verdict."""

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
