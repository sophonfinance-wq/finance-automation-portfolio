"""
Data model for the JV investor reporting package control engine.
================================================================

The engine consumes **package files**: one JSON file per monthly financial
reporting package a developer issues to the joint-venture equity partner of a
single project entity. Each source artifact is modelled as a typed document -- a
dict with a ``doc_type`` discriminator and typed fields -- so the whole engine
stays stdlib-only, deterministic and byte-stable.

Scope: the package, not the judgement behind it
-----------------------------------------------
A project entity's monthly investor package is a small stack of statements: a
trial balance, a balance sheet, a statement of operations, a statement of
members' capital, a development cost schedule, a job cost bridge and the notes.
Behind them sit the sources they are built from -- the project entity's general
ledger extract, the job cost detail by division, the executed equity draw
schedule, the parent entity's ledger carrying the reciprocal investment account,
and the package issued for the period before.

Nothing here decides anything. Whether a cost the ledger calls one thing and the
draw schedule calls another is really one or the other is a classification
judgement, and no engine can make it: the engine reports that two sources
disagree and stops. What an engine *can* settle is whether the package that
leaves the building is the package its own sources produce.

Why that is worth an engine
---------------------------
The process is monthly, per project, per investor, and the failure mode is a
wrong figure sent to an outside equity partner. Five failures found during a
manual build of one such package took three rounds of human review to surface,
and none of them looked wrong on the page.

**A difference gets dropped rather than disclosed.** The job cost report does not
tie to the ledger, so the gap is absorbed into a rounding line instead of being
itemized and told to the partner.

**A contribution agrees to nothing.** The capital statement's contribution column
is typed from a funding notice rather than footed from the executed draw
schedule, and the variance is never quantified.

**A caption outlives its schedule.** A cost-to-date schedule keeps a caption
saying the cost arose in the period, so a reader adds a month of spend that was
really three years of it.

**The cover contradicts the notes.** The basis of presentation asserts the
package is free of exceptions while the notes disclose one.

**A tie-out check row is left in the print area.** The reviewer's own arithmetic
ships to the investor as though it were a line of the statement.

So the controls here are re-derivation controls. Every figure the package states
is rebuilt from the source that is supposed to produce it and compared with exact
``==``, matched by account number and member id rather than by row position.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a trial balance that does not net, a
  balance that does not agree to its ledger account, a statement that does not
  foot or cross-foot, a rollforward that does not roll, a difference that is not
  disclosed, a caption that contradicts its schedule, a check row or preparer
  artifact left in the release, a package released over an open exception).
- ``FLAG`` -- a human-review signal (cash whose bank reconciliation has not
  arrived; the engine can report the absence and must not manufacture support).
- ``PASS`` -- the rule ran and the control held.

A package file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
# Sources -- what the package is built from. The engine reads these and never
# writes them.
#: The project entity's general ledger extract for the period.
DOC_ENTITY_LEDGER = "entity_ledger"
#: Job cost detail by division, as the cost system reports it.
DOC_JOB_COST_DETAIL = "job_cost_detail"
#: The executed equity draw schedule -- what each member actually funded.
DOC_DRAW_SCHEDULE = "draw_schedule"
#: The parent entity's ledger, carrying the reciprocal investment account.
DOC_PARENT_LEDGER = "parent_ledger"
#: The package issued for the period before this one.
DOC_PRIOR_PACKAGE = "prior_package"

# The package itself -- what gets issued to the equity partner.
#: Cover, contents and basis-of-presentation assertions.
DOC_PACKAGE_COVER = "package_cover"
#: The package trial balance.
DOC_TRIAL_BALANCE = "trial_balance"
#: Statement of financial position.
DOC_BALANCE_SHEET = "balance_sheet"
#: Statement of operations.
DOC_INCOME_STATEMENT = "income_statement"
#: Statement of members' capital, one column per member plus a Total column.
DOC_CAPITAL_STATEMENT = "capital_statement"
#: Development cost schedule, cost incurred to date by division.
DOC_DEVCOST_SCHEDULE = "devcost_schedule"
#: The job cost bridge: report total, reconciling items and their disclosure.
DOC_JOBCOST_REPORT = "jobcost_report"
#: Bank reconciliation support behind the cash balances.
DOC_CASH_SUPPORT = "cash_support"
#: Notes to the financial statements, each quoting a figure from a named cell.
DOC_FOOTNOTES = "footnotes"
#: The release record: tie-out check rows, released artifacts and the decision.
DOC_RELEASE_LOG = "release_log"

#: The five source artifacts, in canonical report order.
SOURCE_DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_LEDGER,
    DOC_JOB_COST_DETAIL,
    DOC_DRAW_SCHEDULE,
    DOC_PARENT_LEDGER,
    DOC_PRIOR_PACKAGE,
)

#: Everything the issued package is made of, in canonical report order.
PACKAGE_DOC_TYPES: tuple[str, ...] = (
    DOC_PACKAGE_COVER,
    DOC_TRIAL_BALANCE,
    DOC_BALANCE_SHEET,
    DOC_INCOME_STATEMENT,
    DOC_CAPITAL_STATEMENT,
    DOC_DEVCOST_SCHEDULE,
    DOC_JOBCOST_REPORT,
    DOC_CASH_SUPPORT,
    DOC_FOOTNOTES,
    DOC_RELEASE_LOG,
)

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = SOURCE_DOC_TYPES + PACKAGE_DOC_TYPES

#: The statements the cover's contents list may name, mapped to the keys that
#: have to carry something for the statement to count as issued rather than
#: merely present. A statement may instead declare ``presented_nil``, which
#: ``nil_is_genuine`` then audits against the ledger.
STATEMENT_CONTENT: dict[str, tuple[str, ...]] = {
    DOC_TRIAL_BALANCE: ("rows",),
    DOC_BALANCE_SHEET: ("rows",),
    DOC_INCOME_STATEMENT: ("revenue_rows", "expense_rows"),
    DOC_CAPITAL_STATEMENT: ("members", "contribution_detail"),
    DOC_DEVCOST_SCHEDULE: ("rows",),
    DOC_JOBCOST_REPORT: ("total_cents",),
    DOC_FOOTNOTES: ("notes",),
}

# --------------------------------------------------------------------------- #
# Ledger vocabulary
# --------------------------------------------------------------------------- #
#: Account classes. Revenue and expense are carried even when nil, because
#: whether they are nil is exactly what ``nil_is_genuine`` has to look at.
ACCT_ASSET = "asset"
ACCT_LIABILITY = "liability"
ACCT_EQUITY = "equity"
ACCT_REVENUE = "revenue"
ACCT_EXPENSE = "expense"
ACCOUNT_TYPES: tuple[str, ...] = (
    ACCT_ASSET,
    ACCT_LIABILITY,
    ACCT_EQUITY,
    ACCT_REVENUE,
    ACCT_EXPENSE,
)

#: Accounts that produce a result on the statement of operations.
RESULT_ACCOUNT_TYPES: tuple[str, ...] = (ACCT_REVENUE, ACCT_EXPENSE)

#: The role an account plays in the package, where its account class is not
#: enough to say. ``ROLE_NONE`` is carried explicitly so every ledger row has
#: the same shape.
ROLE_NONE = ""
ROLE_CASH = "cash"
ROLE_WIP = "wip"
ROLE_INTERCOMPANY = "intercompany"
ROLE_CAPITAL = "capital"
ACCOUNT_ROLES: tuple[str, ...] = (
    ROLE_NONE,
    ROLE_CASH,
    ROLE_WIP,
    ROLE_INTERCOMPANY,
    ROLE_CAPITAL,
)

# --------------------------------------------------------------------------- #
# Presentation vocabulary
# --------------------------------------------------------------------------- #
#: Balance sheet sections. A credit-balance intercompany account belongs in
#: ``SECTION_LIABILITIES`` however it is numbered in the chart of accounts.
SECTION_ASSETS = "assets"
SECTION_LIABILITIES = "liabilities"
SECTION_EQUITY = "equity"
SECTIONS: tuple[str, ...] = (SECTION_ASSETS, SECTION_LIABILITIES, SECTION_EQUITY)

#: What a schedule measures. The distinction is the whole of
#: ``caption_matches_type``: a cost-to-date schedule and a period-activity
#: schedule are read differently, and the caption is how a reader knows which.
SCHEDULE_COST_TO_DATE = "cost_to_date"
SCHEDULE_PERIOD_ACTIVITY = "period_activity"
SCHEDULE_TYPES: tuple[str, ...] = (SCHEDULE_COST_TO_DATE, SCHEDULE_PERIOD_ACTIVITY)

#: Caption vocabulary, stated once. Each schedule type requires one of its own
#: markers and forbids every marker of the other type, so a caption cannot be
#: silent about which of the two the schedule is.
CAPTION_REQUIRED: dict[str, tuple[str, ...]] = {
    SCHEDULE_COST_TO_DATE: ("to date",),
    SCHEDULE_PERIOD_ACTIVITY: ("for the period", "during the period"),
}
CAPTION_FORBIDDEN: dict[str, tuple[str, ...]] = {
    SCHEDULE_COST_TO_DATE: ("for the period", "during the period"),
    SCHEDULE_PERIOD_ACTIVITY: ("to date",),
}

# --------------------------------------------------------------------------- #
# Members' capital vocabulary
# --------------------------------------------------------------------------- #
#: The money rows of the capital statement, in presentation order. The
#: rollforward identity is stated over exactly these.
CAPITAL_BEGINNING = "beginning_cents"
CAPITAL_CONTRIBUTIONS = "contributions_cents"
CAPITAL_NET_INCOME = "net_income_cents"
CAPITAL_DISTRIBUTIONS = "distributions_cents"
CAPITAL_ENDING = "ending_cents"
CAPITAL_ROWS: tuple[str, ...] = (
    CAPITAL_BEGINNING,
    CAPITAL_CONTRIBUTIONS,
    CAPITAL_NET_INCOME,
    CAPITAL_DISTRIBUTIONS,
    CAPITAL_ENDING,
)

#: The sharing-ratio row, in integer basis points. It is not money, and it still
#: has to cross-foot: a Total column is a Total column on every row.
CAPITAL_RATIO_ROW = "ownership_bps"

#: Key of the Total column in the capital statement's column map.
TOTAL_COLUMN = "total"

# --------------------------------------------------------------------------- #
# Draw schedule vocabulary
# --------------------------------------------------------------------------- #
#: Only an executed draw is a contribution. A scheduled draw is a plan and a
#: cancelled one is a withdrawn plan; neither funded anything.
DRAW_EXECUTED = "executed"
DRAW_SCHEDULED = "scheduled"
DRAW_CANCELLED = "cancelled"
DRAW_STATUSES: tuple[str, ...] = (DRAW_EXECUTED, DRAW_SCHEDULED, DRAW_CANCELLED)

# --------------------------------------------------------------------------- #
# Release vocabulary
# --------------------------------------------------------------------------- #
#: The two states a package can be in. There is no third: a package with an open
#: exception is held, and a package that is not held has been issued.
RELEASE_HELD = "held"
RELEASE_RELEASED = "released"
RELEASE_DECISIONS: tuple[str, ...] = (RELEASE_HELD, RELEASE_RELEASED)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a package file or the whole run."""

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
        ``"tb_agrees_ledger"``).
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
    """Everything a check needs about one package file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.

    ``prior_findings`` is the one exception to "a check sees only the file": the
    release gate is a control *over the other controls*, so it needs the
    findings the registry has already produced. The runner appends to it as it
    goes, and no other check reads it.
    """

    path: Path
    data: dict[str, Any]
    prior_findings: list[Finding] = field(default_factory=list)

    @property
    def file_id(self) -> str:
        """Identifier of the package file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def project_entity(self) -> str:
        """Fictional project entity whose package the file carries."""
        value = self.data.get("project_entity")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_start(self) -> str:
        """First day of the period an executed draw must fall inside."""
        value = self.data.get("period_start")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period_end(self) -> str:
        """Last day of the period the package is issued as of."""
        value = self.data.get("period_end")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the package file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A package file carries exactly one of each artifact. Returning ``None``
        rather than raising lets ``package_complete`` own the "missing
        statement" finding, so every downstream rule reports absence the same
        way instead of inventing a failure of its own.
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
    """All findings for one package file plus its rolled-up verdict."""

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
