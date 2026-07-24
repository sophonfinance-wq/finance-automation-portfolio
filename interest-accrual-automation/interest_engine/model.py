"""
Data model for the interest-accrual & loan-amortization control engine.
=======================================================================

The engine consumes **loan files**: one JSON file per debt-service record,
carrying the artifacts that record emits. Each source artifact is modelled as a
typed document -- a dict with a ``doc_type`` discriminator and typed fields -- so
the whole engine stays stdlib-only, deterministic and byte-stable.

Scope: does the schedule prove itself
-------------------------------------
This engine is about **whether the interest a note reports is the interest its
own terms produce**, not where a financing cost lands or how a draw is funded.
Those are separate engines. A lender carries notes receivable and interest
income; the reciprocal borrower carries notes payable and interest expense; and
every month somebody accrues interest, rolls the balance forward, and posts a
journal entry that is supposed to tie to both sides. The question here is
narrower and entirely arithmetic: rebuild each note's accrual from its stated
rate and day-count, roll the balance forward row by row, and prove the schedule,
the reciprocal GL and the journal all agree.

Why that is worth an engine
---------------------------
An amortization schedule is a column of numbers that looks self-evidently right,
and it goes wrong in ways nobody re-adds.

**The accrual drifts from the terms.** A period accrues at the wrong rate, on the
wrong balance, or over the wrong day count, and the booked interest is off by an
amount too small to notice against a six-figure balance -- until it compounds.

**The roll-forward breaks.** One period's ending balance is not the next period's
beginning; an advance is added but never accrues; a payment relieves more than was
owed; the payoff leaves a residual cent instead of settling to zero.

**A gate is missed.** Interest keeps accruing past maturity, the default rate
never steps after an event of default, a note prohibited from prepayment is paid
down early, or a subordinated note is paid before the senior it sits behind.

**The two sides stop reconciling.** The lender's receivable and the borrower's
payable drift apart, interest income no longer equals interest expense, or the
monthly journal no longer ties to the accrual it was meant to record.

So the controls here are re-derivation controls. Every accrual is recomputed from
the note's terms, every ending balance is rebuilt from its beginning, and every
rollup determination is recomputed from the schedule underneath it, then compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (an accrual that does not re-derive, a broken
  roll-forward, a missed maturity or rate gate, a prepayment or subordination
  violation, a reciprocity or journal break, a rollup that does not recompute).
- ``FLAG`` -- a human-review signal (a note maturing inside the lead-time window,
  a maturity watchlist that does not tie the evidence).
- ``PASS`` -- the rule ran and the control held.

A loan file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: Every note with its stated terms (rate, day-count, maturity, gates, GL map).
DOC_NOTE_REGISTER = "note_register"
#: The per-note interest roll-forward: period rows with begin/advance/accrue/pay/end.
DOC_ROLLFORWARD = "rollforward_schedule"
#: The monthly interest journal entry (paired DR/CR lines, self-proving to zero).
DOC_INTEREST_JOURNAL = "interest_journal"
#: GL account balances the reciprocal and completeness controls tie out against.
DOC_TRIAL_BALANCE = "trial_balance"
#: The per-note settled determination and accrued-interest total.
DOC_INTEREST_SUMMARY = "interest_summary"
#: Notes maturing inside the lead-time window.
DOC_MATURITY_WATCHLIST = "maturity_watchlist"
#: The portfolio debt-service rollup (settled / outstanding counts).
DOC_DEBT_SERVICE_REPORT = "debt_service_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_NOTE_REGISTER,
    DOC_ROLLFORWARD,
    DOC_INTEREST_JOURNAL,
    DOC_TRIAL_BALANCE,
    DOC_INTEREST_SUMMARY,
    DOC_MATURITY_WATCHLIST,
    DOC_DEBT_SERVICE_REPORT,
)

# --------------------------------------------------------------------------- #
# Debt-service vocabulary
# --------------------------------------------------------------------------- #
#: Day-count denominators a note may state. Actual/365 and 30/360 are the two the
#: engine re-derives against; an unknown denominator has no defined accrual.
DAY_COUNT_ACTUAL_365 = 365
DAY_COUNT_30_360 = 360
DAY_COUNT_DENOMINATORS: tuple[int, ...] = (
    DAY_COUNT_30_360,
    DAY_COUNT_ACTUAL_365,
)

#: GL account kinds carried on the trial balance, one set per note.
TB_KIND_NR = "notes_receivable"
TB_KIND_NP = "notes_payable"
TB_KIND_INCOME = "interest_income"
TB_KIND_EXPENSE = "interest_expense"
TB_KINDS: tuple[str, ...] = (
    TB_KIND_NR,
    TB_KIND_NP,
    TB_KIND_INCOME,
    TB_KIND_EXPENSE,
)

#: Default lead-time, in days, for the maturity watchlist when a file does not
#: carry its own. A note maturing inside this window is a FLAG, not a failure --
#: there is still time to refinance or extend.
DEFAULT_MATURITY_LEAD_DAYS = 60


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a loan file or the whole run."""

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
        ``"acc_interest_rederives"``).
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
    """Everything a check needs about one loan file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the loan file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional lender whose debt-service record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future accrual period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every maturity and gate test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def maturity_lead_days(self) -> int:
        """Lead-time window, in days, for the maturity watchlist.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_MATURITY_LEAD_DAYS` when it is absent or malformed.
        """
        value = self.data.get("maturity_lead_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_MATURITY_LEAD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the loan file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A loan file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one loan file plus its rolled-up verdict."""

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
