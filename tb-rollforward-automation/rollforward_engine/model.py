"""
Data model for the trial-balance roll-forward control engine.
=============================================================

The engine consumes **workpaper files**: one JSON file per group's annual
roll-forward cycle, carrying the artifacts that cycle emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: the workpaper, not the filing
------------------------------------
This engine is the workpaper half of the annual state-filing story. Whether an
entity's return was filed by its statutory date is a *calendar* question, and a
separate engine owns it. This engine is the workpaper that filing is prepared
from: one column per entity, rolled forward from last year's structure and
repopulated from the year-end trial-balance extract.

Why that is worth an engine
---------------------------
The structure is rebuilt every year -- entities dissolve, rename and form -- and
the population is re-keyed from an extract that was organised around books, not
filings. Five things go wrong, and none of them look wrong:

**A column is populated from the wrong source column.** Some books in the
extract carry a monthly-activity column beside the balance column. Activity
foots to zero exactly the way balances do, so a column populated from it
self-balances, passes a footing check, and carries movement instead of balances.

**A balance rides an equivalent code and disappears.** Two charts of accounts
share one workpaper row (``"2001/1601"``); retained earnings lives on one chart
as one code and on the other as another. Drop the equivalence and the balance
silently lands nowhere -- while every column still foots.

**The eliminations range excludes this year's columns.** Ranges written over
last year's structure keep working after new columns are inserted beyond their
end. Nothing errors; the new columns simply are not eliminated.

**The backup tab quotes the wrong text column.** The extract carries a category
column beside the title column. A backup built from category reads plausibly --
"Cash", "Equity" -- and reconciles to nothing a reviewer can look up.

**The two rendered twins drift.** The workpaper ships in two formats; a repair
applied to one and not the other leaves reviewers reading different numbers.

So the controls here are re-derivation controls: every cell from the declared
balance column, every dual-code row through the equivalence map, every column to
zero, every range over every column, every title from the title column, and both
twins against each other.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a cell off the extract, a column that does
  not foot, a scope drift against the entity register, a dangling backup link).
- ``FLAG`` -- a human-review signal (a dormant column that is genuinely empty, a
  first-year entity registered late enough to imply a short first period).
- ``PASS`` -- the rule ran and the control held.

A workpaper file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: The confirmed filing population: every entity, its status and its book.
DOC_ENTITY_REGISTER = "entity_register"
#: Last year's column structure, renames, and last year's populated values.
DOC_PRIOR_STRUCTURE = "prior_structure"
#: The year-end trial-balance extract, book by book, with declared columns.
DOC_SOURCE_EXTRACT = "source_extract"
#: Chart-of-accounts equivalences shared by dual-chart workpaper rows.
DOC_CHART_MAP = "chart_map"
#: The rolled-forward, populated workpaper: columns, rows, eliminations, combined.
DOC_WORKPAPER = "workpaper"
#: The flat backup tab embedded beside the workpaper, one row per account.
DOC_BACKUP_TAB = "backup_tab"
#: The second rendered format of the same workpaper (the "twin").
DOC_TWIN_EXPORT = "twin_export"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_REGISTER,
    DOC_PRIOR_STRUCTURE,
    DOC_SOURCE_EXTRACT,
    DOC_CHART_MAP,
    DOC_WORKPAPER,
    DOC_BACKUP_TAB,
    DOC_TWIN_EXPORT,
)

# --------------------------------------------------------------------------- #
# Roll-forward vocabulary
# --------------------------------------------------------------------------- #
#: Entity statuses. The status drives the roll-forward treatment: a continuing
#: entity keeps its column, a final-year entity loses it, a first-year entity
#: gains one, and an excluded entity (owned outside the group) never had one.
STATUS_CONTINUING = "continuing"
STATUS_FIRST_YEAR = "first_year"
STATUS_FINAL_YEAR = "final_year"
STATUS_EXCLUDED = "excluded"
ENTITY_STATUSES: tuple[str, ...] = (
    STATUS_CONTINUING,
    STATUS_FIRST_YEAR,
    STATUS_FINAL_YEAR,
    STATUS_EXCLUDED,
)

#: Source-extract column roles. Every book table declares its columns; the
#: balance column is located by role, never by position -- that is the control.
COL_BALANCE = "current_balance"
COL_ACTIVITY = "monthly_activity"
COL_TITLE = "account_title"
COL_CATEGORY = "category"

#: Row positions inside a book table. Only ``code`` rows are trial-balance rows;
#: ``memo`` rows are side-schedule annotations and must never be populated.
POS_CODE = "code"
POS_MEMO = "memo"

#: Default fixed annual filing fee, in cents, when the file carries none.
#: Suppressed in an entity's final year -- charging it there is the defect.
DEFAULT_FIXED_FEE_CENTS = 80000

#: Default first-period review band, in days. A first-year entity registered
#: more than this far into the fiscal year implies a short first period the
#: preparer must be told about.
DEFAULT_SHORT_PERIOD_DAYS = 90


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a workpaper file or the whole run."""

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
        ``"map_values_exact"``).
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
    """Everything a check needs about one workpaper file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the workpaper file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional group whose annual roll-forward cycle the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future fiscal-period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated workpaper review date the cycle is measured at."""
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
    def fiscal_start(self) -> date | None:
        """First day of the fiscal year, or ``None`` if unreadable.

        Returns ``None`` when absent or malformed, so ``set_complete`` owns the
        finding and the date controls stand down rather than measuring
        registrations against a year they had to invent.
        """
        return self._iso("fiscal_year_start")

    @property
    def fiscal_end(self) -> date | None:
        """Last day of the fiscal year, or ``None`` if unreadable."""
        return self._iso("fiscal_year_end")

    @property
    def fixed_fee_cents(self) -> int:
        """Fixed annual filing fee, in cents.

        Read from the file when present so the figure comes from the data,
        falling back to :data:`DEFAULT_FIXED_FEE_CENTS` when absent or malformed.
        """
        value = self.data.get("fixed_fee_cents")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_FIXED_FEE_CENTS
        return value

    @property
    def short_period_days(self) -> int:
        """Review band, in days, after fiscal start for a short first period."""
        value = self.data.get("short_period_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_SHORT_PERIOD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the workpaper file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A workpaper file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one workpaper file plus its rolled-up verdict."""

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
