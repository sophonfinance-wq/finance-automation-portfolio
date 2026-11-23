"""
Data model for the equity-method pickup & eliminations control engine.
======================================================================

The engine consumes **consolidation files**: one JSON file per reporting
group's equity-method workpaper set, carrying the artifacts that workpaper
emits. Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: re-derivation and tie-out, not valuation
-----------------------------------------------
A parent that holds an interest in a subsidiary or joint venture books that
interest once as an investment, and then every period three things must remain
true at the same time: the parent's *equity pickup* must equal its ownership
share of the sub's net income; the investment carrying value must roll forward
as begin + contributions + pickup - distributions = end; and on consolidation
every Investment account must be eliminated against the sub's Equity-Parent
account so each entity block nets to zero. This engine re-derives all three and
ties them to the trial balance. It deliberately does **not** opine on
impairment or fair value -- those are judgment calls owned by a valuation
workpaper, not a control engine. Everything here is a hard equality, a
membership test, a date gate or a re-derivation.

Why that is worth an engine
---------------------------
Three failures hide inside an equity-method workpaper, and none of them look
wrong on their own page.

**The pickup drifts from the ownership math.** Somebody keys the pickup, or
carries last quarter's percentage, and the parent books a share of income that
its ownership percentage does not produce.

**The elimination goes stale.** The investment balance moves during the period
but the elimination entry does not, so the consolidated balance sheet quietly
carries a residual that is neither an asset nor equity -- or a holding gains an
investment account that never gets paired to the sub's equity at all.

**The rollup drifts from the evidence.** The trial balance carries a "should
be" column nobody re-derives, member allocations stop summing to the income
they allocate, and a preferred-return accrual keeps compounding a day-count
error forward.

So the controls here are re-derivation controls. Every stated figure is
recomputed from the base facts underneath it, and compared exactly.

Severity model
--------------
- ``FAIL`` -- a hard control failure (an identity that does not foot, a pickup
  that does not recompute, an elimination that does not extinguish the
  carrying value, a figure that is not integer cents).
- ``FLAG`` -- a human-review signal (a stated trial-balance adjustment that is
  internally consistent but has not been posted).
- ``PASS`` -- the rule ran and the control held.

A consolidation file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
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
#: Every entity in the reporting group, with its role and company code.
DOC_ENTITY_REGISTER = "entity_register"
#: Every parent-sub holding: ownership, method, and the linked GL accounts.
DOC_HOLDING_REGISTER = "holding_register"
#: Each subsidiary's period result: net income and distributions declared.
DOC_SUB_RESULTS = "sub_results"
#: The per-holding investment roll-forward (begin + contributions + pickup -
#: distributions = end).
DOC_INVESTMENT_ROLLFORWARD = "investment_rollforward"
#: The consolidation elimination schedule, one block per equity holding.
DOC_ELIMINATION_SCHEDULE = "elimination_schedule"
#: The preferred-return day-count accrual schedule per member.
DOC_PREFERRED_RETURN = "preferred_return_schedule"
#: The member allocation of each fully-held sub's net income.
DOC_ALLOCATION_SUMMARY = "allocation_summary"
#: The trial balance the roll-forward and pickup figures must tie to.
DOC_TRIAL_BALANCE = "trial_balance"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ENTITY_REGISTER,
    DOC_HOLDING_REGISTER,
    DOC_SUB_RESULTS,
    DOC_INVESTMENT_ROLLFORWARD,
    DOC_ELIMINATION_SCHEDULE,
    DOC_PREFERRED_RETURN,
    DOC_ALLOCATION_SUMMARY,
    DOC_TRIAL_BALANCE,
)

# --------------------------------------------------------------------------- #
# Consolidation vocabulary
# --------------------------------------------------------------------------- #
#: Entity roles. A holding runs from a parent to a subsidiary, never sideways.
ROLE_PARENT = "parent"
ROLE_SUBSIDIARY = "subsidiary"
ROLES: tuple[str, ...] = (ROLE_PARENT, ROLE_SUBSIDIARY)

#: Accounting methods a holding can carry. Cost-vs-equity is configured per
#: holding because real books are not uniform: some interests sit at cost with
#: no pickup at all, and the roll-forward rules differ accordingly.
METHOD_EQUITY = "equity"
METHOD_COST = "cost"
METHODS: tuple[str, ...] = (METHOD_EQUITY, METHOD_COST)

#: Default day-count basis for the preferred-return accrual when a schedule
#: does not carry its own. Actual/365, no compounding.
DEFAULT_DAY_BASIS = 365


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a consolidation file or the whole run."""

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
        ``"epu_pickup_rederives"``).
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
    """Everything a check needs about one consolidation file.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the consolidation file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def group(self) -> str:
        """Fictional reporting group whose workpaper set the file carries."""
        value = self.data.get("group")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future fiscal period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the consolidation file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A consolidation file carries exactly one of each artifact. Returning
        ``None`` rather than raising lets ``set_complete`` own the "missing
        artifact" finding, so every downstream rule reports absence the same
        way.
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
    """All findings for one consolidation file plus its rolled-up verdict."""

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
