"""
Data model for the baseline & version drift control engine.
===========================================================

The engine consumes **cycle files**: one JSON file per project reporting cycle,
carrying every copy of that project's budget that is in circulation, plus the
agreement that says which copy governs. Each artifact is modelled as a typed
document -- a dict with a ``doc_type`` discriminator and typed fields -- so the
whole engine stays stdlib-only, deterministic and byte-stable.

Scope: agreement between copies, not arithmetic inside one
----------------------------------------------------------
Whether a single budget workbook foots is a *within-document* question, and a
separate engine owns it. This engine starts where that one stops. Its subject is
the set: the contractual exhibit a joint venture was signed against, the
sponsor's working model, the billing instrument a draw is requested on, and the
summary memo circulated to a lender. Four copies of one budget, each of which
can be internally perfect while disagreeing with the other three.

Why that is worth an engine
---------------------------
Because every failure mode here survives every within-document check:

**A copy is internally consistent and materially wrong.** Sources equal uses,
hard plus soft equals total, the margin re-derives -- in all four copies. They
simply carry different totals. Nothing inside any one of them can detect it.

**A reclassification reads as a change.** Two lines move by offsetting amounts
and the total never budges. That is a re-carve of the same money, not a budget
change, and grading it as a change buries the real ones in noise.

**A category exists in one copy and not another.** A line renamed or split in
the working model has no counterpart in the exhibit, so a naive comparison comes
back clean on the lines it *can* pair and silently skips the one that moved.

**A copy is stale rather than wrong.** It was right when it was prepared. Its
prepared date is before the agreement it purports to be an exhibit to, or its
cost-through date is months behind the period being reported, and every figure
read off it is quoted with confidence.

**A derived schedule loses its inputs.** An instalment schedule amortised across
a construction period depends on milestone dates. Blank the milestones and the
schedule does not error -- it silently keeps the last amortisation it was given,
and the fee it drives stops matching the term it is supposed to span.

So the controls here are agreement controls: category sets reconciled before
values, every paired line compared with exact ``==``, offsetting pairs graded as
reclassification rather than change, every change traced to an approved
amendment, every version's dates tested against the period the file carries, and
every derived schedule's declared inputs proven present before its output is
trusted.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a line that disagrees across copies, a
  change with no approved amendment, a derived schedule missing an input, a
  version dated before the agreement it belongs to).
- ``FLAG`` -- a human-review signal (a confirmed difference below the file's
  materiality threshold, a recognised reclassification, a summary memo quoting a
  superseded version).
- ``PASS`` -- the rule ran and the control held.

A cycle file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
up to ``REVIEW``; everything clean is ``PASS``.

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
#: The executed agreement: which version governs, the phase splits, the caps.
DOC_AGREEMENT = "governing_agreement"
#: Every copy of the budget in circulation, each with its own provenance.
DOC_BUDGET_VERSION = "budget_version"
#: The approved-change register every non-zero movement must trace to.
DOC_AMENDMENT_LOG = "amendment_log"
#: The milestone schedule derived schedules read their dates from.
DOC_MILESTONE_SET = "milestone_set"
#: A schedule computed off the budget and the milestones (e.g. a fee amortisation).
DOC_DERIVED_SCHEDULE = "derived_schedule"
#: Member funding: commitments, contributions to date, and the caps that bound them.
DOC_FUNDING_REGISTER = "funding_register"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_AGREEMENT,
    DOC_BUDGET_VERSION,
    DOC_AMENDMENT_LOG,
    DOC_MILESTONE_SET,
    DOC_DERIVED_SCHEDULE,
    DOC_FUNDING_REGISTER,
)

# --------------------------------------------------------------------------- #
# Version vocabulary
# --------------------------------------------------------------------------- #
#: The contractual exhibit. Exactly one version carries this role, and it is the
#: version every variance is measured against.
ROLE_BASELINE = "contractual_baseline"
#: The sponsor's live working model. Moves between reporting cycles.
ROLE_WORKING = "working_model"
#: The form a draw or requisition is billed on. What the investor actually reads.
ROLE_BILLING = "billing_instrument"
#: A restatement circulated to a third party. Derivative, never authoritative.
ROLE_SUMMARY = "summary_memo"

#: Every version role, in canonical order.
VERSION_ROLES: tuple[str, ...] = (
    ROLE_BASELINE,
    ROLE_WORKING,
    ROLE_BILLING,
    ROLE_SUMMARY,
)

#: Project phases. The funding split is a function of the phase, so a split
#: compared without its phase is compared against the wrong ratio half the time.
PHASE_PRE = "pre_conversion"
PHASE_POST = "post_conversion"
PHASES: tuple[str, ...] = (PHASE_PRE, PHASE_POST)

#: Budget line disposition inside an amendment log.
CHANGE_APPROVED = "approved"
CHANGE_PENDING = "pending"
CHANGE_STATES: tuple[str, ...] = (CHANGE_APPROVED, CHANGE_PENDING)

#: Default materiality threshold, in cents, when the file carries none. A
#: difference at or above this is a FAIL; below it is a FLAG for review. The
#: threshold grades a difference that has already been found -- it never decides
#: whether one exists.
DEFAULT_MATERIALITY_CENTS = 100000

#: Default staleness band, in days. A working model whose cost-through date is
#: more than this far behind the period end is stale.
DEFAULT_STALE_DAYS = 45


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a cycle file or the whole run."""

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
        ``"lin_line_values_agree"``).
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
    """Everything a check needs about one cycle file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the cycle file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def project(self) -> str:
        """Fictional project whose budget copies the file carries."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting-period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date the cycle is measured at."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    def _iso(self, key: str) -> date | None:
        value = self.data.get(key)
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @property
    def period_start(self) -> date | None:
        """First day of the reporting period, or ``None`` if unreadable.

        Returns ``None`` when absent or malformed, so ``set_complete`` owns the
        finding and the date controls stand down rather than measuring versions
        against a period they had to invent.
        """
        return self._iso("period_start")

    @property
    def period_end(self) -> date | None:
        """Last day of the reporting period, or ``None`` if unreadable."""
        return self._iso("period_end")

    @property
    def materiality_cents(self) -> int:
        """Threshold, in cents, at which a confirmed difference becomes a FAIL."""
        value = self.data.get("materiality_cents")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_MATERIALITY_CENTS
        return value

    @property
    def stale_days(self) -> int:
        """Band, in days, beyond which a version's cost-through date is stale."""
        value = self.data.get("stale_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_STALE_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the cycle file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A cycle file carries exactly one of each singular artifact. Returning
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
    """All findings for one cycle file plus its rolled-up verdict."""

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
