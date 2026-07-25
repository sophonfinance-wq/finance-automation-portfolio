"""
Data model for the unit sales and commission tie-out control engine.
====================================================================

The engine consumes **sales files**: one JSON file per for-sale housing project's
sales-administration record, carrying the artifacts that record emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: the Matrix, not the ledger
---------------------------------
A residential for-sale project (condo or townhome) is administered out of one
workbook. The "Matrix" tab carries every unit in the building: its plan, its
plan square footage, its list price, the price it actually sold for, the
concession granted, the revenue per square foot, the closing costs and the total
selling commission. A "Sold/Close" tab logs, for every unit that went hard, the
offer date, the actual date sold, the closing date and whether the proof of
closing came back. A Commission Log splits each unit's total commission across
the named selling agents who earned it.

One template is instantiated across every project, and the same three failures
recur in each instantiation. Nothing here posts a journal entry, releases a
commission payment or files a closing statement; the question is narrower and
entirely arithmetic: does the Matrix still tie to the tabs that feed it?

Why that is worth an engine
---------------------------
The Matrix is a spreadsheet, and a spreadsheet drifts in ways that look right.

**A derived column stops deriving.** Revenue per square foot, net proceeds and
total commission are formulas until somebody types over one of them for a single
unit, and from then on the column is a mixture of computed and typed figures that
no longer agree with the prices beside them.

**The commission splits stop adding up.** The Commission Log pays named agents,
and the sum of the splits on a unit is meant to be the total commission on the
Matrix row. A split edited after the fact, or an agent added without reducing
another, leaves the log paying an amount the Matrix never authorised.

**The tabs stop reconciling.** A unit is marked Sold on the Matrix and never
reaches the Sold/Close tab, or a closing is logged with the sale date before the
offer date, or the rollup that goes upstairs counts a project the Matrix does not
support.

So the controls here are arithmetic and reconciliation controls. Every derived
figure on the Matrix is recomputed from the prices that produced it, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a derived figure that does not recompute, a
  commission split that does not sum to the total, a sold unit with no closing
  row, a date sequence that runs backwards, a rollup that does not tie).
- ``FLAG`` -- a human-review signal (a discount to list beyond the approved band,
  a closing whose proof of closing has not come back).
- ``PASS`` -- the rule ran and the control held.

A sales file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: The plan types released in the project, with their plan square footage.
DOC_PLAN_REGISTER = "plan_register"
#: The Matrix: one row per unit, priced and costed.
DOC_UNIT_MATRIX = "unit_matrix"
#: The selling-commission rate for each sale channel, in basis points.
DOC_COMMISSION_SCHEDULE = "commission_schedule"
#: The Sold/Close tab: offer, sale and closing dates plus the received-proof flag.
DOC_SOLD_CLOSE_LOG = "sold_close_log"
#: The selling agents a commission split can name.
DOC_AGENT_REGISTER = "agent_register"
#: The Commission Log: each unit's total commission split across named agents.
DOC_COMMISSION_LOG = "commission_log"
#: The project sales rollup that leaves the sales office.
DOC_SALES_ROLLUP = "sales_rollup"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PLAN_REGISTER,
    DOC_UNIT_MATRIX,
    DOC_COMMISSION_SCHEDULE,
    DOC_SOLD_CLOSE_LOG,
    DOC_AGENT_REGISTER,
    DOC_COMMISSION_LOG,
    DOC_SALES_ROLLUP,
)

# --------------------------------------------------------------------------- #
# Sales-administration vocabulary
# --------------------------------------------------------------------------- #
#: Unit statuses on the Matrix. Only ``sold`` obliges a Sold/Close row.
UNIT_AVAILABLE = "available"
UNIT_RESERVED = "reserved"
UNIT_SOLD = "sold"
UNIT_STATUSES: tuple[str, ...] = (UNIT_AVAILABLE, UNIT_RESERVED, UNIT_SOLD)

#: Sale channels. The commission schedule is keyed by channel, so adding a
#: channel is a schedule row -- never a control.
CHANNEL_IN_HOUSE = "in_house"
CHANNEL_CO_BROKE = "co_broke"
CHANNEL_REFERRAL = "referral"
SALE_CHANNELS: tuple[str, ...] = (
    CHANNEL_IN_HOUSE,
    CHANNEL_CO_BROKE,
    CHANNEL_REFERRAL,
)

#: Default discount-to-list band, in basis points, when a file does not carry its
#: own. A sold unit discounted beyond this is a FLAG, not a failure -- the price
#: was struck, and the question is whether it was struck inside sales authority.
DEFAULT_MAX_DISCOUNT_BPS = 500


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a sales file or the whole run."""

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
        ``"comm_splits_tie"``).
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
    """Everything a check needs about one sales file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the sales file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose sales record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def project(self) -> str:
        """Fictional for-sale housing project the Matrix covers."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def market(self) -> str:
        """Fictional market label carried for identification only."""
        value = self.data.get("market")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future sales period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every closing test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def max_discount_bps(self) -> int:
        """Approved discount-to-list band, in basis points.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_MAX_DISCOUNT_BPS` when it is absent or malformed.
        """
        value = self.data.get("max_discount_bps")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_MAX_DISCOUNT_BPS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the sales file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A sales file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one sales file plus its rolled-up verdict."""

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
