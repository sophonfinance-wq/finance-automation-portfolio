"""
Data model for the intercompany reciprocity control engine.
===========================================================

The engine consumes **period files**: one JSON file per reporting period for a
group of affiliated entities, carrying the artifacts a homebuilder's consolidation
process emits. Each source artifact is modelled as a typed document -- a dict with
a ``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Why intercompany balances are worth an engine
----------------------------------------------
A development group is not one company; it is a tree of them. A top holding parent
owns a services arm (the employer entities that carry payroll) and a capital arm
(the entities that guarantee construction loans and fund projects), plus a
predevelopment entity that carries land while it is entitled. Cash moves between
them constantly -- advances down the chain, repayments back up, equity into
projects -- and every one of those movements leaves two entries on two different
sets of books kept by two different people.

The failure mode is that the two sides drift. Entity A books a receivable from B;
B books a smaller payable to A, or none at all. Each entity's own books foot
perfectly. Nothing is out of balance *within* a company. The break only exists
*between* them, and it only surfaces at consolidation, when the intercompany
balances are supposed to eliminate to zero and instead leave a residual nobody
can source. By then the period is closed.

So the controls here are reciprocity controls: a due-from on one entity must equal
the due-to that faces it, a closing balance must roll forward from its opening
plus the transactions that moved it, and cash must flow along the ownership chain
and from the protocol-correct source -- not merely balance on each entity alone.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a non-reciprocal pair, a balance that does
  not roll forward, funding from the wrong entity, a guarantor below its covenant
  floor).
- ``FLAG`` -- a human-review signal (an advance running against the ownership
  chain, a cash target out of band, a single advance large enough to want a
  second signature).
- ``PASS`` -- the rule ran and the control held.

A period file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
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
#: The entity tree: every affiliate, its group, its parent, its region.
DOC_ENTITY_REGISTER = "entity_register"
#: The cash-flow protocol: liquidity floor, target bands, funding-routing rules.
DOC_FUNDING_PROTOCOL = "funding_protocol"
#: Every intercompany transaction this period: advances, repayments, equity.
DOC_IC_LEDGER = "intercompany_ledger"
#: Each creditor's receivable from each affiliate, opening and closing.
DOC_DUE_FROM = "due_from_schedule"
#: Each debtor's payable to each affiliate, closing.
DOC_DUE_TO = "due_to_schedule"
#: Each entity's period-end cash, for the liquidity thresholds.
DOC_LIQUIDITY = "liquidity_positions"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_REGISTER,
    DOC_FUNDING_PROTOCOL,
    DOC_IC_LEDGER,
    DOC_DUE_FROM,
    DOC_DUE_TO,
    DOC_LIQUIDITY,
)

#: Entity-group labels the protocol reasons about.
GROUP_HOLDINGS = "Holdings"
GROUP_SERVICES = "Services"
GROUP_CAPITAL = "Capital"
GROUP_PREDEV = "Predevelopment"

#: Groups whose funding must originate from the top parent, never the Capital arm.
HOLDINGS_FUNDED_GROUPS: tuple[str, ...] = (GROUP_SERVICES, GROUP_PREDEV)

#: Intercompany transaction types.
TXN_ADVANCE = "advance"
TXN_REPAYMENT = "repayment"
TXN_EQUITY = "equity"
TXN_TYPES: tuple[str, ...] = (TXN_ADVANCE, TXN_REPAYMENT, TXN_EQUITY)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a period file or the whole run."""

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
        ``"rec_amounts_reciprocal"``).
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
    """Everything a check needs about one period file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a source
    artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the period file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def group(self) -> str:
        """Fictional consolidation group the period file belongs to."""
        value = self.data.get("group")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label (``YYYY-Qn``)."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the period file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A period file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one period file plus its rolled-up verdict."""

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
