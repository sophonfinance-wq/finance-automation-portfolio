"""
Data model for the payroll & benefit contribution reconciliation engine.
========================================================================

The engine consumes **reconciliation files**: one JSON file per employer's
single pay-period benefit reconciliation, carrying the artifacts that period
emits. Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

The shape of the problem
------------------------
Every pay period a payroll run fans one register out to several benefit
providers, to cash, and to the general ledger. A 401(k) deferral withheld on the
register has to reach both the recordkeeper and the custodian; an HSA deduction
has to reach the HSA administrator; an FSA election has to reach the FSA
administrator; the employer match has to be recomputed from the plan formula;
and every dollar has to land in the ledger as a balanced entry whose benefit
payable clears to zero once the money is remitted.

Four failures hide inside that, and none of them look wrong in a stack of
provider upload files:

**The hand-off drifts.** A per-employee deduction on the register is not the
amount that reached the provider, or a plan total ties to the recordkeeper but
not the custodian, or the cash transfer is a dollar off the liability it settles.

**The employer match is wrong.** The booked match does not recompute from the
plan formula applied to eligible compensation, or it was computed on
compensation above the 401(a)(17) cap.

**A statutory limit is breached.** An employee is over the 402(g) deferral limit
(before or after the age-50 catch-up), over the HSA tier limit (self-only vs
family, plus the age-55 catch-up), over an FSA cap, or over the 415(c) annual
additions ceiling -- and the per-period withholding no longer recomputes from the
remaining room over the remaining periods.

**The deposit is late.** Participant money reached the provider outside the DOL
small-plan seven-business-day safe harbor, or the reconciliation rollup calls a
plan tied on a determination nobody recomputed from the evidence underneath it.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a hand-off that does not tie, a match that
  does not recompute, a limit breach, a late deposit, an unbalanced entry, a
  clearing account that does not zero, a stated tie flag that does not recompute).
- ``FLAG`` -- a human-review signal (a deferral inside the watch band approaching
  its limit, an exception watchlist that does not tie the evidence).
- ``PASS`` -- the rule ran and the control held.

A reconciliation file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
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
#: Every employee paid this period, with entity, tier, comp and prior-YTD room.
DOC_EMPLOYEE_REGISTER = "employee_register"
#: Every benefit plan: type, providers, statutory limits and match formula.
DOC_PLAN_CATALOG = "plan_catalog"
#: The payroll register detail: one row per (employee, plan) deduction.
DOC_DEDUCTION_REGISTER = "deduction_register"
#: What actually reached each provider: one row per (provider, plan, employee).
DOC_PROVIDER_FILE = "provider_file"
#: Per-plan pay/remit dates and the settling cash transfer.
DOC_REMITTANCE_SCHEDULE = "remittance_schedule"
#: Per-(entity, plan) subtotals and the consolidated per-plan total.
DOC_ENTITY_SUMMARY = "entity_summary"
#: The balanced pay-period journal entry.
DOC_JOURNAL_ENTRY = "journal_entry"
#: The per-plan tie determination and the statutory exception watchlist.
DOC_RECONCILIATION_REPORT = "reconciliation_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_EMPLOYEE_REGISTER,
    DOC_PLAN_CATALOG,
    DOC_DEDUCTION_REGISTER,
    DOC_PROVIDER_FILE,
    DOC_REMITTANCE_SCHEDULE,
    DOC_ENTITY_SUMMARY,
    DOC_JOURNAL_ENTRY,
    DOC_RECONCILIATION_REPORT,
)

# --------------------------------------------------------------------------- #
# Payroll vocabulary
# --------------------------------------------------------------------------- #
#: Employing entities. Payroll is partitioned by these; a completeness check
#: requires each entity that paid this period to carry its own subtotal.
ENTITY_NW = "ENT-NW"
ENTITY_SW = "ENT-SW"
ENTITY_TX = "ENT-TX"
ENTITIES: tuple[str, ...] = (ENTITY_NW, ENTITY_SW, ENTITY_TX)

#: HSA coverage tiers. The tier selects which annual HSA limit applies.
TIER_SELF_ONLY = "self_only"
TIER_FAMILY = "family"
TIER_NONE = "none"
HSA_TIERS: tuple[str, ...] = (TIER_SELF_ONLY, TIER_FAMILY, TIER_NONE)

#: Plan types. The type selects which controls apply and which limit is tested.
PLAN_DEFERRAL = "deferral_pretax"  # employee money, 402(g), safe-harbor timed
PLAN_MATCH = "employer_match"  # employer money, 415(c), comp-capped
PLAN_HSA = "hsa"  # employee money, tier limit, safe-harbor timed
PLAN_FSA_MEDICAL = "fsa_medical"  # employee money, FSA cap, safe-harbor timed
PLAN_FSA_DEPENDENT = "fsa_dependent_care"  # employee money, FSA cap
PLAN_TYPES: tuple[str, ...] = (
    PLAN_DEFERRAL,
    PLAN_MATCH,
    PLAN_HSA,
    PLAN_FSA_MEDICAL,
    PLAN_FSA_DEPENDENT,
)

#: Default DOL small-plan safe harbor, in business days, used when a file does
#: not carry its own. Participant money must reach the provider within it.
DEFAULT_SAFE_HARBOR_BUSINESS_DAYS = 7

#: Default watch band, in cents, below a deferral limit. A year-to-date deferral
#: inside this band of its limit is a FLAG to watch, not yet a breach.
DEFAULT_DEFERRAL_WATCH_BAND_CENTS = 200_000


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a reconciliation file or the whole run."""

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
        ``"ded_matches_provider"``).
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
    """Everything a check needs about one reconciliation file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the reconciliation file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def employer(self) -> str:
        """Fictional employer whose pay-period reconciliation the file carries."""
        value = self.data.get("employer")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future pay-period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every date-gate is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def plan_year_end(self) -> str:
        """Plan-year-end date the age-50 / age-55 catch-up gates are measured to."""
        value = self.data.get("plan_year_end")
        return str(value) if isinstance(value, str) else "-"

    @property
    def periods_remaining(self) -> int:
        """Pay periods remaining, the divisor in the per-period withholding."""
        value = self.data.get("periods_remaining")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return 1
        return value

    @property
    def safe_harbor_business_days(self) -> int:
        """DOL small-plan deposit safe harbor, in business days.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_SAFE_HARBOR_BUSINESS_DAYS` when absent or malformed.
        """
        value = self.data.get("safe_harbor_business_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_SAFE_HARBOR_BUSINESS_DAYS
        return value

    @property
    def deferral_watch_band_cents(self) -> int:
        """Watch band, in cents, below a deferral limit for the review FLAG."""
        value = self.data.get("deferral_watch_band_cents")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_DEFERRAL_WATCH_BAND_CENTS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the reconciliation file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A reconciliation file carries exactly one of each artifact. Returning
        ``None`` rather than raising lets ``set_complete`` own the "missing
        artifact" finding, so every downstream rule reports absence the same way.
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
    """All findings for one reconciliation file plus its rolled-up verdict."""

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
