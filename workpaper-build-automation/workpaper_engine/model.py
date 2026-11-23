"""
Data model for the tax workpaper build engine.
==============================================

This engine **builds** a thing. Its product is a constructed tax workpaper
package for a new fiscal year -- trial balance, balance sheet, statement of
operations, members' equity, member capital accounts, earnings-and-profits
roll-forward, an evidence tab and a build register -- assembled from four
inputs and emitted as an artifact somebody signs. The controls in
:mod:`.engine` exist to prove what the builder produced; they are the second
half of the story, not the first.

The four inputs
---------------
**A locked current-year general-ledger source extract.** Accounts, titles and
balances, scoped to an entity block. "Locked" is the operative word: the build
records its digest, so a source re-exported or moved after the build
invalidates every harvested figure rather than quietly changing them.

**The prior-year workpaper package.** The structure being rolled: the frozen
history, the classification map, last year's equity total, last year's member
capital closings, last year's accumulated earnings and profits, and every
caption that has to advance.

**An allocation register.** The member split percentages, in integer basis
points, carried into the new year and used to allocate income and liability
shares.

**A known-exception register.** The account numbers a reviewer has already seen
and accepted -- a suspense-series placeholder, an account whose source title
drifted from the chart -- and the tie-out differences already disclosed.

What the build has to get right
-------------------------------
Rolling a workpaper is not copying it. Six things go wrong every year, and all
six produce a package that *looks* finished:

**A prior-year layer moves.** History is supposed to be a constant. A sort
applied to the equity schedule, a formula left live in a frozen row, a
re-derivation that reaches back a year -- any of these rewrites a number that
was signed off, and the schedule still foots.

**A caption is left at last year's date.** The figures roll and the label does
not, so a reader reconciles a current-year column against a prior-year heading
and finds it agrees with nothing.

**A current-year flow is typed rather than derived.** Contributions and
distributions are the *movement* in an equity account, not its balance. Taking
the balance where the delta belongs double-counts every prior year at once.

**A row's form is read off a formula.** Some rows carry a cumulative residual
and some carry a year delta; which one a row is depends on the account's
balances at both year-ends, not on whether the cell happens to contain a live
formula. Guessing from the formula is how a cumulative row gets rolled as if it
were a delta.

**The build edits more than it declared.** A rebuild that touches a cell
outside the build register has changed something nobody reviewed, and the only
way to know is to hold the pre-build image and diff against it.

**The evidence stops being evidence.** A support tab whose citation names the
wrong tab, or whose rows no longer tie to the source by account number, is a
tab that reconciles to nothing a reviewer can open.

Severity model
--------------
- ``FAIL`` -- a hard control failure: a constructed figure the inputs do not
  support, a frozen layer that moved, a digest that no longer matches.
- ``FLAG`` -- a human-review signal: a difference the package itself discloses,
  which the engine can confirm is disclosed but cannot confirm is *right*.
- ``PASS`` -- the control ran and held.

A file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll up
to ``REVIEW``; everything clean is ``PASS``.

All shipped data is fictional. The controls never write to a source artifact,
and the builder never writes to its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Document type vocabulary
# --------------------------------------------------------------------------- #
#: The locked current-year general-ledger extract the build harvests from.
DOC_LOCKED_SOURCE = "locked_source"
#: Last year's signed workpaper package: history, captions, classification map.
DOC_PRIOR_PACKAGE = "prior_package"
#: Member split percentages, in integer basis points, carried into the new year.
DOC_ALLOCATION_REGISTER = "allocation_register"
#: Account numbers and tie-out differences a reviewer has already accepted.
DOC_EXCEPTION_REGISTER = "exception_register"
#: The counterpart entity's stub for the investment held in this entity block.
DOC_COUNTERPART_STUB = "counterpart_stub"
#: The working file captured immediately before the build ran (backup custody).
DOC_PREBUILD_IMAGE = "prebuild_image"
#: The product: the constructed workpaper package.
DOC_BUILT_PACKAGE = "built_package"
#: Every constructed cell with the derivation that produced it.
DOC_BUILD_REGISTER = "build_register"
#: Content digests for chain of custody.
DOC_MANIFEST = "manifest"

#: Every document type the engine understands, in canonical order.
DOC_TYPES: tuple[str, ...] = (
    DOC_LOCKED_SOURCE,
    DOC_PRIOR_PACKAGE,
    DOC_ALLOCATION_REGISTER,
    DOC_EXCEPTION_REGISTER,
    DOC_COUNTERPART_STUB,
    DOC_PREBUILD_IMAGE,
    DOC_BUILT_PACKAGE,
    DOC_BUILD_REGISTER,
    DOC_MANIFEST,
)

# --------------------------------------------------------------------------- #
# Classification vocabulary
# --------------------------------------------------------------------------- #
#: Balance-sheet section: assets, liabilities and anything else presented at a
#: point in time other than the equity section.
SECTION_BALANCE_SHEET = "balance_sheet"
#: The equity section, whose total has to agree with the equity schedule.
SECTION_EQUITY = "equity"
#: The statement of operations.
SECTION_PROFIT_LOSS = "profit_loss"
SECTIONS: tuple[str, ...] = (
    SECTION_BALANCE_SHEET,
    SECTION_EQUITY,
    SECTION_PROFIT_LOSS,
)

#: Equity-account kinds. Contribution and distribution accounts produce the
#: current-year flow rows; the retained-earnings account never does -- its
#: movement is last year's result, not this year's capital activity.
EQUITY_CONTRIBUTION = "contribution"
EQUITY_DISTRIBUTION = "distribution"
EQUITY_RETAINED_EARNINGS = "retained_earnings"
EQUITY_KINDS: tuple[str, ...] = (
    EQUITY_CONTRIBUTION,
    EQUITY_DISTRIBUTION,
    EQUITY_RETAINED_EARNINGS,
)

#: Equity-schedule row roles.
ROLE_OPENING = "opening"
ROLE_CONTRIBUTION = "contribution"
ROLE_DISTRIBUTION = "distribution"
ROLE_INCOME = "income"
ROLE_CLOSING = "closing"
ROW_ROLES: tuple[str, ...] = (
    ROLE_OPENING,
    ROLE_CONTRIBUTION,
    ROLE_DISTRIBUTION,
    ROLE_INCOME,
    ROLE_CLOSING,
)

#: Row forms. A ``year_delta`` row carries the movement in an account that was
#: already funded at the prior year-end. A ``cumulative_residual`` row carries
#: the whole of an account that was flat at the prior year-end, so the balance
#: and the movement are the same figure. Which one a row is has to be decided
#: from the balances at both year-ends -- never from whether a cell holds a
#: live formula, because a formula survives a copy and a balance does not.
FORM_YEAR_DELTA = "year_delta"
FORM_CUMULATIVE_RESIDUAL = "cumulative_residual"
ROW_FORMS: tuple[str, ...] = (FORM_YEAR_DELTA, FORM_CUMULATIVE_RESIDUAL)

#: Exception kinds a reviewer can register against an account number.
EXC_PLACEHOLDER = "placeholder"
EXC_MISLABELED = "mislabeled"
EXCEPTION_KINDS: tuple[str, ...] = (EXC_PLACEHOLDER, EXC_MISLABELED)

#: Account prefix reserved for the chart's suspense / unmapped range. Anything
#: harvested out of this range is a placeholder by construction.
PLACEHOLDER_PREFIX = "9"

#: The allocation register's split pairs, by purpose.
SPLIT_ORDINARY_INCOME = "ordinary_income"
SPLIT_LIABILITY_SHARE = "liability_share"
SPLIT_PURPOSES: tuple[str, ...] = (SPLIT_ORDINARY_INCOME, SPLIT_LIABILITY_SHARE)

#: Caption ids that roll: every one of these names the reporting year and has to
#: advance by exactly one when the package is built.
CAPTION_IDS: tuple[str, ...] = (
    "package_title",
    "trial_balance_title",
    "balance_sheet_title",
    "profit_loss_title",
    "equity_title",
    "equity_closing",
    "member_block_current",
    "ep_block_current",
    "evidence_title",
)

#: Markers that must never survive into a rendered package.
FORMULA_ERROR_MARKERS: tuple[str, ...] = (
    "#REF!",
    "#VALUE!",
    "#DIV/0!",
    "#NAME?",
    "#NUM!",
    "#N/A",
)

#: Prefixes that betray an external link or a local filesystem path.
EXTERNAL_MARKERS: tuple[str, ...] = (
    "http://",
    "https://",
    "file://",
    "\\\\",
    "C:\\",
    "D:\\",
    "/Users/",
    "/home/",
    "/mnt/",
)


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a build file or the whole run."""

    PASS = "PASS"  # every control held
    REVIEW = "REVIEW"  # at least one FLAG, no FAILs
    FAIL = "FAIL"  # at least one FAIL


@dataclass(frozen=True)
class Finding:
    """A single observation produced by a control.

    Attributes
    ----------
    rule:
        Stable identifier of the control that produced the finding (e.g.
        ``"frozen_layers_byte_equal"``).
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
    """Everything a control needs about one build file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a control is structurally incapable of mutating
    the artifact it is proving.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the build file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional group whose workpaper build the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def entity_block(self) -> str:
        """The entity block the build was scoped to."""
        value = self.data.get("entity_block")
        return str(value) if isinstance(value, str) else "-"

    @property
    def fiscal_year(self) -> int | None:
        """The fiscal year being built, read from the file (never the clock)."""
        value = self.data.get("fiscal_year")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @property
    def prior_fiscal_year(self) -> int | None:
        """The fiscal year being rolled from, read from the file."""
        value = self.data.get("prior_fiscal_year")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the build file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A build file carries exactly one of each artifact. Returning ``None``
        rather than raising lets each control report absence in its own voice --
        "the control cannot be evidenced" -- instead of a PASS on evidence that
        is not there.
        """
        found = self.docs(doc_type)
        return found[0] if found else None

    def loc(self, doc: dict[str, Any] | None, field_path: str) -> str:
        """Build a stable ``location`` string for a field inside ``doc``."""
        if not isinstance(doc, dict):
            return f"?:-/{field_path}"
        doc_type = doc.get("doc_type", "?")
        doc_id = doc.get("document_id", "?")
        return f"{doc_type}:{doc_id}/{field_path}"


@dataclass
class DocumentReport:
    """All findings for one build file plus its rolled-up verdict."""

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
