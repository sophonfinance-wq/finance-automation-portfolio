"""
Data model for the subcontract SOV & change-order control engine.
=================================================================

The engine consumes **billing files**: one JSON file per project's subcontract
commitment billing record, carrying the artifacts that record emits. Each source
artifact is modelled as a typed document -- a dict with a ``doc_type``
discriminator and typed fields -- so the whole engine stays stdlib-only,
deterministic and byte-stable.

Scope: the commitment billing chain, not the draw and not the waiver
--------------------------------------------------------------------
A developer buys construction through subcontract *commitments*: a contract with
a schedule of values (SOV) breaking the price into lines, change orders that
amend it, and a monthly pay application that bills against it line by line. The
question this engine answers is entirely arithmetical: does every figure on that
chain re-derive from the figures beneath it? Which pay app lands in which lender
draw is a funding question owned by a separate engine, and the statutory form of
each lien waiver is a document-compliance question owned by another; this engine
checks only that the conditional release *amount* ties the certified payment and
that each pay app carries exactly one.

Why that is worth an engine
---------------------------
A pay application is a page of derived columns, and every one of them is typed
by hand somewhere. Three failures hide inside that, and none of them look wrong
on the page.

**The contract drifts from its paper.** The revised commitment stops equalling
original plus net approved change orders -- a pending CO counted early, a
soft-cost CO booked as a brand-new commitment instead of a ``#-N`` amendment --
and the committed-cost roster no longer states what was actually signed.

**The billing chain breaks a line at a time.** A line's completed-to-date stops
equalling previously-billed plus this period, a line quietly bills past its
scheduled value, or this month's "previously billed" no longer equals last
month's "total billed" -- and the overbilling compounds under a column that
still foots.

**The money math is asserted, not derived.** Retention stops being the contract
rate on the billing, the sales tax stops being the rate on the taxable request,
the payment due stops being request minus retention plus tax -- and the
conditional lien release is signed for an amount nobody recomputed.

So the controls here are re-derivation controls. Every derived figure on the
chain is recomputed from the base facts and compared, exactly.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a figure that does not re-derive, a line
  billed past its scheduled value, a roll-forward break, a CO gate violation,
  a release amount that does not tie).
- ``FLAG`` -- a human-review signal (a stated percent-complete that does not
  re-derive, a retention rate off the standard 5% / 10% menu).
- ``PASS`` -- the rule ran and the control held.

A billing file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every subcontract commitment on the project, with its contract terms.
DOC_COMMITMENT_REGISTER = "commitment_register"
#: Every change order raised against a commitment, with status and amount.
DOC_CHANGE_ORDER_LOG = "change_order_log"
#: The schedule of values: each commitment's price broken into lines.
DOC_SOV_SCHEDULE = "sov_schedule"
#: Every pay application billed against a commitment, line by line.
DOC_PAY_APP_REGISTER = "pay_application_register"
#: The committed-cost roster: per-commitment revised amounts and Total columns.
DOC_COMMITMENT_ROLLUP = "commitment_rollup"
#: Every conditional lien release exchanged for a pay application.
DOC_LIEN_RELEASE_REGISTER = "lien_release_register"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_COMMITMENT_REGISTER,
    DOC_CHANGE_ORDER_LOG,
    DOC_SOV_SCHEDULE,
    DOC_PAY_APP_REGISTER,
    DOC_COMMITMENT_ROLLUP,
    DOC_LIEN_RELEASE_REGISTER,
)

# --------------------------------------------------------------------------- #
# Commitment vocabulary
# --------------------------------------------------------------------------- #
#: The only origin a commitment may carry. A change order -- soft-cost or
#: otherwise -- is applied to the original commitment as an amendment, never
#: booked as a commitment of its own.
ORIGIN_ORIGINAL = "original"
COMMITMENT_ORIGINS: tuple[str, ...] = (ORIGIN_ORIGINAL,)

#: The standard all-lines retention menu, in basis points: 5% or 10%.
STANDARD_RETENTION_RATES_BPS: tuple[int, ...] = (500, 1000)

#: The one release type this engine ties out: the conditional release exchanged
#: for the current payment, certified at the payment-due-including-tax figure.
RELEASE_CONDITIONAL = "conditional"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a billing file or the whole run."""

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
        ``"cap_not_overbilled"``).
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
    """Everything a check needs about one billing file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the billing file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose billing record the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def project(self) -> str:
        """Fictional project the commitments belong to."""
        value = self.data.get("project")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future billing period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the billing file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A billing file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one billing file plus its rolled-up verdict."""

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
