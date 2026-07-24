"""
Data model for the capital spending request gate control engine.
================================================================

The engine consumes **request packages**: one JSON file per development
project's capital Spending Request record, carrying the artifacts that record
emits. Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: standards compliance, not investment merit
-------------------------------------------------
Before a development project may commit capital it must pass through an ordered
sequence of Investment Committee (IC) phase gates, and every Spending Request it
submits must conform to a written set of underwriting standards: hard dollar
triggers that demand an approval *before* the first dollar is spent, contingency
floors, a standard growth assumption, prescribed fee formulas, a phase-indexed
estimate basis and deliverable checklist, and a comparison basis that switches
once feasibility is waived. Whether the *investment itself* is worth making is
genuine business judgment and is deliberately out of scope. This engine checks
only the deterministic standards layer: triggers, floors, sequence, membership,
re-derivations and calendar gates -- every deviation flagged as an exception.

Why that is worth an engine
---------------------------
Three things go wrong, and none of them look wrong in a bound request package.

**Capital moves before the gate.** Pursuit costs accumulate past the trigger, or
a deposit goes non-refundable, before the Initial Commitment Request was ever
approved -- and by the time the package is assembled the approval that *is* in it
post-dates the spend it was supposed to authorize.

**The standards drift quietly.** A contingency sits a hair under the floor, a
fee is stated a little off its formula, the growth assumption departs from the
standard with no market support documented, the comparison still points at the
template after feasibility was waived. Each figure looks plausible; none of them
was re-derived.

**The gate summary is asserted, not recomputed.** The package says every phase
gate cleared, on a determination nobody rebuilt from the approvals and the
deliverable checklist underneath it.

So the controls here are evidentiary controls. Every stated determination is
recomputed from the package's own base facts, and compared.

Severity model
--------------
- ``FAIL`` -- a hard control failure (spend before the trigger approval, a phase
  out of sequence, a contingency under the floor, a fee that does not re-derive,
  a gate summary that does not recompute).
- ``FLAG`` -- a human-review signal (a current-phase deliverable still
  outstanding, a comparison template past its refresh date).
- ``PASS`` -- the rule ran and the control held.

A request package with any FAIL rolls up to verdict ``FAIL``; FLAGs without
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
#: The project's identity: region, GC model, current phase, growth assumptions.
DOC_PROJECT_PROFILE = "project_profile"
#: Every IC approval on record -- phase Spending Requests and interim requests.
DOC_APPROVAL_LOG = "approval_log"
#: Every pre-approval-sensitive spend: pursuit costs and deposits, dated.
DOC_SPEND_LEDGER = "spend_ledger"
#: The underwriting cost budget: costs, contingencies, fees, estimate basis.
DOC_COST_BUDGET = "cost_budget"
#: The phase-indexed development-plan deliverable checklist.
DOC_DELIVERABLE_CHECKLIST = "deliverable_checklist"
#: The construction-start bid schedule and GMP status.
DOC_BID_SCHEDULE = "bid_schedule"
#: The side-by-side comparison to the Business Plan (template or actual).
DOC_PLAN_COMPARISON = "plan_comparison"
#: The per-phase gate-cleared determination.
DOC_GATE_SUMMARY = "gate_summary"
#: Events that force an out-of-cycle (interim) Spending Request.
DOC_EVENT_LOG = "event_log"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PROJECT_PROFILE,
    DOC_APPROVAL_LOG,
    DOC_SPEND_LEDGER,
    DOC_COST_BUDGET,
    DOC_DELIVERABLE_CHECKLIST,
    DOC_BID_SCHEDULE,
    DOC_PLAN_COMPARISON,
    DOC_GATE_SUMMARY,
    DOC_EVENT_LOG,
)

# --------------------------------------------------------------------------- #
# Phase-gate vocabulary
# --------------------------------------------------------------------------- #
#: The five ordered IC phase gates. A project enters a phase only after the IC
#: approves that phase's Spending Request and the prior phases' deliverables are
#: complete, so the order of this tuple *is* the control.
PHASE_INITIAL_COMMITMENT = "initial_commitment"
PHASE_FEASIBILITY = "feasibility"
PHASE_ENACTMENT_ZONING = "enactment_zoning"
PHASE_APPROVALS = "approvals"
PHASE_CONSTRUCTION = "presales_construction"
PHASES: tuple[str, ...] = (
    PHASE_INITIAL_COMMITMENT,
    PHASE_FEASIBILITY,
    PHASE_ENACTMENT_ZONING,
    PHASE_APPROVALS,
    PHASE_CONSTRUCTION,
)

#: Request types an approval-log row can carry.
REQUEST_PHASE = "phase"
REQUEST_INTERIM = "interim"
REQUEST_TYPES: tuple[str, ...] = (REQUEST_PHASE, REQUEST_INTERIM)

#: Fictional regions with their own underwriting floors. Marran carries the
#: 10%-hard / 5%-soft floors (splitting to 10% site + 5% vertical at
#: construction start); Vanterre carries 3% / 3% plus a separate escalation
#: contingency requirement.
REGION_MARRAN = "marran"
REGION_VANTERRE = "vanterre"
REGIONS: tuple[str, ...] = (REGION_MARRAN, REGION_VANTERRE)

#: General-contractor delivery models. Each has its own construction-start
#: bid-coverage test.
GC_THIRD_PARTY = "third_party_gc"
GC_OWNER = "owner_gc"
GC_MODELS: tuple[str, ...] = (GC_THIRD_PARTY, GC_OWNER)

#: Spend categories whose first dollar (or cumulative total) is gated on an
#: approved Initial Commitment Request.
SPEND_PURSUIT = "pursuit_cost"
SPEND_REFUNDABLE = "refundable_deposit"
SPEND_NONREFUNDABLE = "nonrefundable_deposit"
SPEND_CATEGORIES: tuple[str, ...] = (
    SPEND_PURSUIT,
    SPEND_REFUNDABLE,
    SPEND_NONREFUNDABLE,
)

#: The development-plan deliverables each phase must complete before the next
#: phase may be entered. A fixed membership matrix, never a judgment call.
DELIVERABLES_BY_PHASE: dict[str, tuple[str, ...]] = {
    PHASE_INITIAL_COMMITMENT: ("site_control_agreement", "title_report"),
    PHASE_FEASIBILITY: ("boundary_survey", "environmental_phase_1"),
    PHASE_ENACTMENT_ZONING: ("zoning_confirmation", "environmental_phase_2"),
    PHASE_APPROVALS: ("design_development_drawings", "entitlement_approvals"),
    PHASE_CONSTRUCTION: ("construction_drawings", "building_permits"),
}

#: Every deliverable the checklist can carry, in phase order.
DELIVERABLE_TYPES: tuple[str, ...] = tuple(
    d for phase in PHASES for d in DELIVERABLES_BY_PHASE[phase]
)

#: Statuses a checklist row can carry.
DELIVERABLE_STATUSES: tuple[str, ...] = ("complete", "outstanding")

#: The cost-estimate basis each phase's Spending Request must be built on. The
#: basis progresses top-down to a bindable GMP; a fixed lookup, not judgment.
ESTIMATE_BASIS_BY_PHASE: dict[str, str] = {
    PHASE_INITIAL_COMMITMENT: "top_down",
    PHASE_FEASIBILITY: "gc_comparable",
    PHASE_ENACTMENT_ZONING: "divisional",
    PHASE_APPROVALS: "major_division_third_party",
    PHASE_CONSTRUCTION: "bindable_gmp",
}

#: Events that force an out-of-cycle (interim) Spending Request.
EVENT_TYPES: tuple[str, ...] = (
    "financing_closing",
    "additional_commitment",
    "condo_construction_start",
    "material_change",
    "project_at_risk",
)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a request package or the whole run."""

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
        ``"trg_ic_before_pursuit_spend"``).
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
    """Everything a check needs about one request package.

    The context is a thin, read-only view over the parsed JSON. It never copies
    or rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the request package (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional developer whose request package the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future underwriting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every calendar test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the request package, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A request package carries exactly one of each artifact. Returning
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
    """All findings for one request package plus its rolled-up verdict."""

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
