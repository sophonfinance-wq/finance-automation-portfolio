"""
Data model for the G&A expense allocation control engine.
=========================================================

The engine consumes **allocation files**: one JSON file per management/holding
group's recurring G&A allocation workbook, carrying the artifacts that workbook
emits. Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: where the overhead lands, not whether it should have been spent
----------------------------------------------------------------------
A management or holding entity carries the group's shared cost: corporate G&A,
shared overhead, the postage meter. None of it belongs to the holding entity.
Every month it is pushed out to the operating entities and projects that
consumed it, on a driver -- headcount-equivalents, unit counts, whatever the
allocation policy names -- and a journal entry is generated to move it.

The workbook that does this is the classic recurring one: one tab per month, a
driver tab and a lookup tab behind them, a stamped accounting date per period,
and a formula column that turns a driver share into a dollar figure. It is
copied forward every month. That is exactly why it drifts.

Why that is worth an engine
---------------------------
Four things go wrong, and none of them look wrong on the face of the tab.

**The percentages stop summing to one hundred.** A recipient is added, a project
closes, a share is typed over -- and the column now sums to 99.97% or 100.02%.
The allocation still runs. It simply pushes out slightly less, or slightly more,
than the pool it was dividing, and the holding entity quietly retains or
over-relieves the difference every month for the rest of the year.

**The allocated amounts stop tying the pool.** The shares are right and the
amounts beside them are stale, or were rounded independently rather than by a
largest-remainder split, so the column sums to a cent or two off the cost pool it
was supposed to exhaust.

**The journal entry drifts from the schedule.** The workbook is one artifact and
the entry posted from it is another. A debit is retyped, a credit is left on the
prior month's figure, an entity is charged and relieved inside the same entry --
and the entry still balances, so nothing downstream objects.

**A month goes missing, or is stamped to the wrong date.** The tab was never
rolled, or was rolled and dated to the month it was copied from, so a period is
absent from the year or posts into the wrong accounting period.

So the controls here are re-derivation controls. Every share is rebuilt from the
driver counts, every allocated amount is rebuilt from the share and the pool, and
the entry is rebuilt from both -- then compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (shares that do not sum to 10000 bps,
  allocated amounts that do not tie the pool or do not re-derive, an entry that
  does not balance or does not tie the schedule, a missing month, a postage
  allocation that does not reconcile to the meter).
- ``FLAG`` -- a human-review signal (a cost pool that steps month over month by
  more than the file's own variance band).
- ``PASS`` -- the rule ran and the control held.

An allocation file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
FAILs roll up to ``REVIEW``; everything clean is ``PASS``.

All shipped data is fictional. The engine never writes to a source artifact, and
it never posts, files or pays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Document type vocabulary
# --------------------------------------------------------------------------- #
#: The month tabs: one period per row, each with its stamped accounting date.
DOC_PERIOD_CALENDAR = "period_calendar"
#: The lookup tab: every operating entity and project that receives allocation.
DOC_RECIPIENT_REGISTER = "recipient_register"
#: The driver tab: one driver count per (period, recipient).
DOC_DRIVER_TABLE = "driver_table"
#: The source cost pool per period, by component.
DOC_COST_POOL_LEDGER = "cost_pool_ledger"
#: The allocation itself: a share in basis points and an amount per recipient.
DOC_ALLOCATION_SCHEDULE = "allocation_schedule"
#: The journal entry generated from the schedule, one per period.
DOC_ALLOCATION_JOURNAL = "allocation_journal"
#: The postage meter readings and the per-code split of the metered spend.
DOC_POSTAGE_LOG = "postage_log"
#: The year-to-date rollup reported off the workbook.
DOC_ALLOCATION_REPORT = "allocation_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PERIOD_CALENDAR,
    DOC_RECIPIENT_REGISTER,
    DOC_DRIVER_TABLE,
    DOC_COST_POOL_LEDGER,
    DOC_ALLOCATION_SCHEDULE,
    DOC_ALLOCATION_JOURNAL,
    DOC_POSTAGE_LOG,
    DOC_ALLOCATION_REPORT,
)

# --------------------------------------------------------------------------- #
# Allocation vocabulary
# --------------------------------------------------------------------------- #
#: A legal operating entity inside the consolidation.
RECIPIENT_OPERATING_ENTITY = "operating_entity"
#: A project cost centre inside one of those entities.
RECIPIENT_PROJECT = "project"
#: Every kind of recipient the allocation recognises.
RECIPIENT_KINDS: tuple[str, ...] = (
    RECIPIENT_OPERATING_ENTITY,
    RECIPIENT_PROJECT,
)

#: Postage classes carried on the meter, with the fixed basis-point weight the
#: allocation policy splits the metered spend by. The weights sum to 10000, so a
#: metered period is exhausted exactly.
POSTAGE_FIRST_CLASS = "first_class"
POSTAGE_CERTIFIED = "certified"
POSTAGE_PARCEL = "parcel"
POSTAGE_CODE_WEIGHTS: tuple[tuple[str, int], ...] = (
    (POSTAGE_FIRST_CLASS, 6000),
    (POSTAGE_CERTIFIED, 2500),
    (POSTAGE_PARCEL, 1500),
)
#: Every postage code the engine understands.
POSTAGE_CODES: tuple[str, ...] = tuple(code for code, _w in POSTAGE_CODE_WEIGHTS)

#: Default month-over-month band, in basis points, above which a cost pool step
#: is flagged for review when a file does not carry its own. A pool that moves
#: more than this has changed in substance, not in rounding.
DEFAULT_VARIANCE_FLAG_BPS = 500


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for an allocation file or the whole run."""

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
        ``"alc_amounts_rederive"``).
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
    """Everything a check needs about one allocation file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the allocation file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional group whose allocation workbook the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def fiscal_year(self) -> str:
        """Fictional-future fiscal year label."""
        value = self.data.get("fiscal_year")
        return str(value) if isinstance(value, str) else "-"

    @property
    def first_period(self) -> str:
        """The month the workbook opens on, as ``YYYY-MM``.

        Stated separately from the calendar so a calendar that lost its opening
        tab is distinguishable from one that never had it.
        """
        value = self.data.get("first_period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def holding_entity_id(self) -> str:
        """The management/holding entity whose G&A is being pushed out."""
        value = self.data.get("holding_entity_id")
        return str(value) if isinstance(value, str) else "-"

    @property
    def holding_credit_account(self) -> str:
        """The account the holding entity's relief is credited to."""
        value = self.data.get("holding_credit_account")
        return str(value) if isinstance(value, str) else "-"

    @property
    def variance_flag_bps(self) -> int:
        """Month-over-month band, in basis points, above which a pool is flagged.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_VARIANCE_FLAG_BPS` when it is absent or malformed.
        """
        value = self.data.get("variance_flag_bps")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_VARIANCE_FLAG_BPS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the allocation file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        An allocation file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one allocation file plus its rolled-up verdict."""

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
