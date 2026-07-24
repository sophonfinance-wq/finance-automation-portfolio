"""
Data model for the earnest-money deposit (EMD) trust control engine.
====================================================================

The engine consumes **deposit files**: one JSON file per residential
developer's pre-close earnest-money record for a for-sale project, carrying
the artifacts that record emits. Each source artifact is modelled as a typed
document -- a dict with a ``doc_type`` discriminator and typed fields -- so the
whole engine stays stdlib-only, deterministic and byte-stable.

Scope: the pre-close deposit trust, nothing after it
----------------------------------------------------
Before a for-sale unit closes, its buyer pays an earnest-money deposit (and
often a separate upgrade deposit) into escrow. The earnest money is not held
idle: it is swept to the construction loan as a principal paydown, while the
upgrade portion sits in a segregated deposit bank account until the unit
closes. This engine reconciles that pre-close world -- the internal deposit
ledger, the escrow agent's record, and the loan paydown register -- three
ways, per unit, to zero variance. The fully-closed unit's settlement-statement
tie-out belongs to the close-of-escrow engine, and the upgrade deposit's
selection/pricing story belongs to the buyer-upgrades engine; this engine
reads the upgrade column only as the segregation counterpart that must sum
with earnest money to the cash that moved.

Why that is worth an engine
---------------------------
Three failures hide in a deposit ledger, and none of them look wrong on any
single page.

**The agent's record and the books disagree.** The escrow agent shows a
deposit our ledger never booked (a completeness gap), or our ledger shows a
release the agent never recorded (an over-release). Each side is internally
consistent; only the per-unit tie-out sees the break.

**The sweep drifts.** An earnest-money deposit marked posted has no principal
paydown behind it, a deposit still marked need-to-post was already swept, or a
cancelled buyer's earlier paydown was never reversed -- so the loan balance
and the deposit ledger quietly stop describing the same money.

**The rollup drifts from the evidence.** The reconciliation summary carries a
variance column, exception flags, bucket totals and trust-bank balances that
nobody recomputed from the deposits underneath them.

So the controls here are tie-out controls. Every stated determination -- unit
variance, exception flag, bucket total, trust balance -- is recomputed from
the base facts through the same kernel that produced it, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a nonzero three-way variance, a missing
  or premature sweep, a forfeiture split that does not sum, a rollup figure
  that does not recompute).
- ``FLAG`` -- a human-review signal (a closed or cancelled unit still sitting
  on the agent's open-escrow statement, an exception flag that does not tie).
- ``PASS`` -- the rule ran and the control held.

A deposit file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
FAILs roll up to ``REVIEW``; everything clean is ``PASS``.

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
#: Every buyer deposit on the developer's books, with its EM/upgrade split.
DOC_DEPOSIT_LEDGER = "deposit_ledger"
#: The escrow/closing agent's record of earnest money held per open unit.
DOC_ESCROW_STATEMENT = "escrow_agent_statement"
#: Construction-loan principal paydowns (and reversals) driven by deposits.
DOC_PAYDOWN_REGISTER = "loan_paydown_register"
#: The forfeiture/refund split for every cancelled buyer.
DOC_CANCELLATION_REGISTER = "cancellation_register"
#: The segregated upgrade-deposit bank balance and forfeiture income to date.
DOC_TRUST_BALANCES = "trust_account_balances"
#: Per-unit list/sales price, concession and net sale price.
DOC_SALES_MATRIX = "sales_matrix"
#: The stated per-unit reconciliation: variances, flags, bucket totals.
DOC_RECON_SUMMARY = "reconciliation_summary"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_DEPOSIT_LEDGER,
    DOC_ESCROW_STATEMENT,
    DOC_PAYDOWN_REGISTER,
    DOC_CANCELLATION_REGISTER,
    DOC_TRUST_BALANCES,
    DOC_SALES_MATRIX,
    DOC_RECON_SUMMARY,
)

# --------------------------------------------------------------------------- #
# Deposit vocabulary
# --------------------------------------------------------------------------- #
#: Posting status buckets. Every deposit sits in exactly one: its sweep to the
#: construction loan is still to be posted, has been posted, or the unit has
#: closed and left the pre-close world. A cancelled deposit keeps the bucket it
#: held at cancellation, which is what says whether its paydown must reverse.
STATUS_NEED_TO_POST = "need_to_post"
STATUS_ALREADY_POSTED = "already_posted"
STATUS_UNIT_CLOSED = "unit_closed"
STATUS_BUCKETS: tuple[str, ...] = (
    STATUS_NEED_TO_POST,
    STATUS_ALREADY_POSTED,
    STATUS_UNIT_CLOSED,
)

#: Deposit lifecycle states. ``cancelled`` routes a deposit through the
#: forfeiture split gate instead of the pre-close reconciliation.
STATE_ACTIVE = "active"
STATE_CANCELLED = "cancelled"
STATES: tuple[str, ...] = (STATE_ACTIVE, STATE_CANCELLED)

#: Loan-register movement kinds. A ``paydown`` applies earnest money to
#: construction-loan principal; a ``reversal`` unwinds one after cancellation.
KIND_PAYDOWN = "paydown"
KIND_REVERSAL = "reversal"
PAYDOWN_KINDS: tuple[str, ...] = (KIND_PAYDOWN, KIND_REVERSAL)

#: The income account a retained termination fee must be booked to. A fee
#: booked anywhere else -- above all to a construction cost code -- hides
#: forfeiture income inside job cost.
FORFEITURE_ACCOUNT = "4910 Forfeited Deposits"

#: The revenue account a sales concession must be booked to. A concession is a
#: reduction of revenue, never a construction cost.
CONCESSION_REVENUE_ACCOUNT = "3900 Sales Revenue - Concessions"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a deposit file or the whole run."""

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
        ``"tie_agent_variance_zero"``).
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
    """Everything a check needs about one deposit file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the deposit file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose deposit record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def project(self) -> str:
        """Fictional for-sale project the deposits belong to."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated ledger cut-off date the reconciliation is drawn at."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the deposit file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A deposit file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one deposit file plus its rolled-up verdict."""

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
