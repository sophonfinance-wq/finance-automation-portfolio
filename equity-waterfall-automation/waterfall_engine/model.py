"""
Data model for the equity-waterfall & JV-promote control engine.
================================================================

The engine consumes **deal files**: one JSON file per real-estate joint-venture,
carrying the artifacts a distribution waterfall emits. Each source artifact is
modelled as a typed document -- a dict with a ``doc_type`` discriminator and
typed fields -- so the whole engine stays stdlib-only, deterministic and
byte-stable.

Scope: re-derivation, not negotiation
-------------------------------------
This engine is about **whether the money the operating agreement promises is the
money the schedule pays**. It does not opine on whether a deal's terms are wise;
it takes the executed agreement's mechanics as given -- the preferred-return
rate, the tier order, the hurdle, the promote split, the dilution penalty -- and
re-derives every distributed dollar from the contribution history, then compares
the recomputed figure to the one the workpaper states.

Why that is worth an engine
---------------------------
A JV waterfall is a chain of dependent computations, and a wrong number early
travels silently to the bottom line.

Three things go wrong, and none of them look wrong in a spreadsheet.

**The accrual drifts.** The preferred return compounds monthly on unreturned
capital; a single mis-set month, or simple interest where the agreement says
compound, moves every downstream tier and the promote with it.

**The split leaks.** A tier pays out of order, a pari-passu split is struck off
the wrong weights, or the promote tier is entered as though the hurdle were
already cleared -- and the developer's carry is larger than the contract earns.

**The summary asserts.** The realized-returns table reports an equity multiple, a
preferred return and a profit split that nobody recomputed from the waterfall
underneath it.

So the controls here are re-derivation controls. Every accrued balance, every
tier allocation, every promote dollar and every reported return is rebuilt from
the base facts through the shared kernel in :mod:`waterfall_engine.waterfall`,
and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (an accrual, allocation, split, promote,
  loan, dilution or reported-return figure that does not recompute; a tier out of
  order; a threshold breached; a leakage residual).
- ``FLAG`` -- a human-review signal (a financing that matures inside the warning
  window, an investor report due inside its lead time).
- ``PASS`` -- the rule ran and the control held.

A deal file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: Executed-agreement mechanics: rates, tier splits, hurdle, dilution penalty.
DOC_DEAL_TERMS = "deal_terms"
#: Every member of the venture, with role and committed capital.
DOC_MEMBER_REGISTER = "member_register"
#: Per-member capital-account roll-forward (contribution + preferred-return acct).
DOC_CAPITAL_LEDGER = "capital_ledger"
#: The distribution waterfall: proceeds allocated across tiers and members.
DOC_WATERFALL_SCHEDULE = "waterfall_schedule"
#: The capital-call default recompute (substitute contribution + dilution).
DOC_DILUTION_WORKSHEET = "dilution_worksheet"
#: Realized-returns summary (equity multiple, preferred return, profit split).
DOC_RETURNS_SUMMARY = "returns_summary"
#: Financing terms and the fund-of-projects syndicate draw (secondary covenants).
DOC_LOAN_COVENANT = "loan_covenant"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_DEAL_TERMS,
    DOC_MEMBER_REGISTER,
    DOC_CAPITAL_LEDGER,
    DOC_WATERFALL_SCHEDULE,
    DOC_DILUTION_WORKSHEET,
    DOC_RETURNS_SUMMARY,
    DOC_LOAN_COVENANT,
)

# --------------------------------------------------------------------------- #
# Venture vocabulary
# --------------------------------------------------------------------------- #
#: Member roles. A well-formed venture carries exactly one of each.
ROLE_INVESTOR = "investor"
ROLE_DEVELOPER = "developer"
ROLES: tuple[str, ...] = (ROLE_INVESTOR, ROLE_DEVELOPER)

#: Waterfall tiers, in the strict order the agreement's Section 3.3 prescribes:
#: preferred return, then return of capital, then the hurdle split, then the
#: promote split. Each schedule entry names the tier it belongs to.
TIER_PREF = "A_preferred_return"
TIER_CAPITAL = "B_return_of_capital"
TIER_HURDLE = "C_hurdle_split"
TIER_PROMOTE = "D_promote_split"
TIER_ORDER: tuple[str, ...] = (TIER_PREF, TIER_CAPITAL, TIER_HURDLE, TIER_PROMOTE)

#: Dilution recompute methods. Three partner-specific formula variants are
#: maintained; each is deterministic and re-derivable from the same inputs.
METHOD_RATIO = "ratio_method"
METHOD_NUMDENOM = "numerator_denominator_method"
METHOD_IJB = "i_plus_ii_minus_b_method"
DILUTION_METHODS: tuple[str, ...] = (METHOD_RATIO, METHOD_NUMDENOM, METHOD_IJB)

#: Months in a year; the preferred, hurdle and loan accruals compound monthly.
MONTHS_PER_YEAR = 12

#: 200% -- the statutory dilution penalty the agreement applies to a substitute
#: contribution when a member fails to fund a capital call.
DILUTION_PENALTY_BPS = 20000

#: 33.5% -- the fixed syndicate capital-call ratio (a draw of $167,500 on each
#: $500,000 committed).
SYNDICATE_CALL_BPS = 3350

#: Default warning windows, in months, for the secondary covenant flags when a
#: deal file does not carry its own.
DEFAULT_MATURITY_LEAD_PERIODS = 6
DEFAULT_REPORT_LEAD_PERIODS = 3


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a deal file or the whole run."""

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
        ``"pref_accrual_recomputes"``).
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
    """Everything a check needs about one deal file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the deal file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def sponsor(self) -> str:
        """Fictional sponsor whose joint-venture the file carries."""
        value = self.data.get("sponsor")
        return str(value) if isinstance(value, str) else "-"

    @property
    def project(self) -> str:
        """Fictional-future project label."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting-period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of_period(self) -> int | None:
        """Month index the accruals and covenant windows are measured to.

        Time here is an integer month index rather than a wall-clock date: every
        accrual compounds monthly from funding, and every covenant window is a
        span of months, so the review point is a month count. Returns ``None``
        when it is absent or malformed, and ``set_complete`` owns that finding.
        """
        value = self.data.get("as_of_period")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    @property
    def maturity_lead_periods(self) -> int:
        """Warning window, in months, for a maturing financing."""
        value = self.data.get("maturity_lead_periods")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_MATURITY_LEAD_PERIODS
        return value

    @property
    def report_lead_periods(self) -> int:
        """Warning window, in months, for a due investor report."""
        value = self.data.get("report_lead_periods")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_REPORT_LEAD_PERIODS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the deal file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A deal file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one deal file plus its rolled-up verdict."""

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
