"""
Data model for the project-proforma integrity (QPR) control engine.
===================================================================

The engine consumes **proforma files**: one JSON file per development region's
quarterly reporting cycle, carrying the artifacts that cycle emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: integrity, not valuation
-------------------------------
This engine does not decide whether a project is a good investment, nor does it
underwrite a rent or a cap rate. It asks a narrower, entirely arithmetic
question: does the workbook still tie to itself? A quarterly proforma carries a
built-in registry of tie-out checks -- a source-and-use error line, an unlevered
cost error line, a four-way profit/waterfall reconciliation, a set of margin and
per-NSF derivations, a current-versus-prior variance column -- and a reporting
calendar that says which deliverables are due when. When the numbers are typed
across tabs and rolled forward quarter over quarter, those ties break silently.
This engine recomputes each one from the base ledger and reports the breaks.

Why that is worth an engine
---------------------------
Every figure on the summary tabs is a *determination*: a number that was correct
when a formula last recalculated, and that becomes an assertion the moment a cell
is overtyped or a tab is copied forward without its precedents.

Three families of drift hide inside a clean-looking workbook, and none of them
look wrong in a grid of formatted numbers.

**The balances stop balancing.** Total sources drift from total uses; hard plus
soft stops equalling total project cost; the dev-cost budget no longer matches
the proforma's unlevered cost. The error-check tab still shows a zero because the
zero itself was typed.

**The profit chain stops tying.** Net profit no longer equals revenue minus cost;
the waterfall's distributed profit stops matching the budgeted profit; the
sponsor and investor splits stop summing to the whole. The distribution looks
funded; the arithmetic underneath it does not close.

**The report drifts from the evidence.** A margin is quoted off a stale cost, a
variance column is typed rather than subtracted, a project's QPR never makes the
cycle or lands after its region's due date, and the cycle count is maintained
beside the filings rather than derived from them.

So the controls here are re-derivation controls. Every stated figure is
recomputed from the base ledger through the same kernel that produced it, and
compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a tie-out that does not close, a figure that
  does not recompute, a missing or late filing, an inadequate interest reserve).
- ``FLAG`` -- a human-review signal (a period-over-period profit swing beyond the
  materiality band -- real, re-derived, and worth a reviewer's eyes, but not a
  hard stop).
- ``PASS`` -- the rule ran and the control held.

A proforma file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every active development project in the cycle, with its region.
DOC_PROJECT_REGISTER = "project_register"
#: Per-project base ledger -- the raw sources, uses, costs, revenue and dates the
#: derived figures are recomputed from.
DOC_PROFORMA_LEDGER = "proforma_ledger"
#: Per-project stated tie-out figures (the summary tabs the engine recomputes).
DOC_TIEOUT_SUMMARY = "tieout_summary"
#: Per-region reporting due dates (the date-gate lookup).
DOC_REPORTING_CALENDAR = "reporting_calendar"
#: Filed deliverables -- per-project QPRs and the regional reports.
DOC_FILING_REGISTER = "filing_register"
#: The cycle roll-up count.
DOC_CYCLE_REPORT = "cycle_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PROJECT_REGISTER,
    DOC_PROFORMA_LEDGER,
    DOC_TIEOUT_SUMMARY,
    DOC_REPORTING_CALENDAR,
    DOC_FILING_REGISTER,
    DOC_CYCLE_REPORT,
)

# --------------------------------------------------------------------------- #
# Proforma vocabulary
# --------------------------------------------------------------------------- #
#: Variance metrics carried on the summary, each a stated current-minus-prior
#: delta the engine re-subtracts. Keyed by the ledger prior-value field.
VARIANCE_METRICS: tuple[str, ...] = (
    "net_profit_cents",
    "total_project_cost_cents",
)

#: Regional deliverables every region with active projects must file each cycle.
DELIVERABLE_MARKET_UPDATE = "market_update"
DELIVERABLE_APARTMENT_REPORT = "apartment_report"
DELIVERABLE_ACQ_SUMMARY = "acq_summary"
REGIONAL_DELIVERABLES: tuple[str, ...] = (
    DELIVERABLE_MARKET_UPDATE,
    DELIVERABLE_APARTMENT_REPORT,
    DELIVERABLE_ACQ_SUMMARY,
)

#: Default materiality band, in cents, for the period-over-period profit-swing
#: flag when a file does not carry its own. A net-profit variance whose absolute
#: value exceeds this is a FLAG, not a failure -- the swing is real and correctly
#: derived, it just wants a reviewer.
DEFAULT_MATERIALITY_CENTS = 100_000_000  # $1,000,000.00


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a proforma file or the whole run."""

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
        ``"prof_net_profit_derivation"``).
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
    """Everything a check needs about one proforma file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the proforma file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose quarterly reporting cycle the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting-cycle label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every due-date gate is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def materiality_cents(self) -> int:
        """Materiality band, in cents, for the profit-swing flag.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_MATERIALITY_CENTS` when it is absent or malformed.
        """
        value = self.data.get("materiality_cents")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_MATERIALITY_CENTS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the proforma file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A proforma file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one proforma file plus its rolled-up verdict."""

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
