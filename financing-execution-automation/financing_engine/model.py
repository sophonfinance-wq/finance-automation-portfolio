"""
Data model for the Financing Execution & Schedule-Variance engine (READ-ONLY).
==============================================================================

The engine consumes **financing reports**: one JSON file per monthly
capital-markets "Upcoming Financings" report, carrying the artifacts that report
emits. Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: execution and schedule, not the money that moves
-------------------------------------------------------
This engine is about **whether the monthly financing report is internally and
cross-period sound**, not whether a wire cleared or a note accrued. It re-derives
each milestone's schedule variance, ties this month's ``Prior`` column back to
last month's ``Current`` column, enforces a frozen ``Original`` baseline, checks
that every financing type carries its standard milestone playbook, and gates on
overdue milestones and a period-end report date. Nothing here books an entry; the
question is narrower and entirely evidentiary: does the report the deal team
circulated actually reconcile to itself and to the month before it?

Why that is worth an engine
---------------------------
An "Upcoming Financings" report is a snapshot of a pipeline that moves every
month, and it drifts in ways nobody watches.

**The variance stops reconciling.** The ``Variance`` column is meant to be
``Current - Prior`` in days, but a hand-edited ``Current`` date leaves the
variance behind, so the report says a milestone slipped by a number that no
longer matches its own dates.

**The month-over-month chain breaks.** This month's ``Prior`` column is supposed
to be last month's ``Current`` column, and the ``Original`` baseline is supposed
to be frozen forever. When either is quietly overwritten, the report looks
current while its history no longer ties.

**The rollup drifts from the schedule.** The summary counts an active pipeline,
an overdue list or a financing total on figures nobody recomputed from the
workstreams underneath them, and the Gantt places a bar in a month that is not the
month the deal is set to close.

So the controls here are re-derivation controls. Every variance, every overdue
flag, every Gantt month and every rollup count is recomputed from the base
schedule facts through the shared kernel in :mod:`financing_engine.schedule`, and
compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a variance that does not re-derive, a broken
  roll-forward, a mutated baseline, a missing playbook milestone, an out-of-order
  milestone, a wrong report date, a rollup count or Gantt month that does not
  recompute).
- ``FLAG`` -- a human-review signal (a milestone whose stated overdue flag does
  not match the date gate).
- ``PASS`` -- the rule ran and the control held.

A financing report with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every financing workstream in the report, with region, type, status, target.
DOC_WORKSTREAM_REGISTER = "workstream_register"
#: This month's milestone rows: Original | Prior | Current | Variance per row.
DOC_MILESTONE_SCHEDULE = "milestone_schedule"
#: Last month's Original and Current per milestone, for the roll-forward tie-out.
DOC_PRIOR_SCHEDULE = "prior_schedule"
#: The canonical ordered milestone set for each financing type.
DOC_PLAYBOOK_CATALOG = "playbook_catalog"
#: The master portfolio every active financing must appear against.
DOC_MASTER_TRACKER = "master_tracker"
#: The summary Gantt: one bar per workstream, placed by target-closing month.
DOC_GANTT_SUMMARY = "gantt_summary"
#: The monthly rollup: active count, overdue count and financing total.
DOC_FINANCING_REPORT = "financing_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_WORKSTREAM_REGISTER,
    DOC_MILESTONE_SCHEDULE,
    DOC_PRIOR_SCHEDULE,
    DOC_PLAYBOOK_CATALOG,
    DOC_MASTER_TRACKER,
    DOC_GANTT_SUMMARY,
    DOC_FINANCING_REPORT,
)

# --------------------------------------------------------------------------- #
# Financing vocabulary
# --------------------------------------------------------------------------- #
#: Financing types. Each carries a different standard milestone playbook.
FINANCING_DEBT = "debt"
FINANCING_EQUITY = "equity"
FINANCING_EXTENSION = "extension"
FINANCING_TYPES: tuple[str, ...] = (
    FINANCING_DEBT,
    FINANCING_EQUITY,
    FINANCING_EXTENSION,
)

#: Workstream status. Overdue gating and portfolio completeness key on ACTIVE.
STATUS_ACTIVE = "ACTIVE"
STATUS_CLOSED = "CLOSED"
STATUSES: tuple[str, ...] = (STATUS_ACTIVE, STATUS_CLOSED)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a financing report or the whole run."""

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
        ``"var_recomputes"``).
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
    """Everything a check needs about one financing report.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the financing report (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def entity(self) -> str:
        """Fictional developer whose financing report the file carries."""
        value = self.data.get("entity")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future report period label, formatted ``YYYY-MM``."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def report_date(self) -> str:
        """The stated report date every overdue and period-end test is measured to."""
        value = self.data.get("report_date")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the financing report, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A financing report carries exactly one of each artifact. Returning
        ``None`` rather than raising lets ``set_complete`` own the "missing
        artifact" finding, so every downstream rule reports absence the same way.
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
    """All findings for one financing report plus its rolled-up verdict."""

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
