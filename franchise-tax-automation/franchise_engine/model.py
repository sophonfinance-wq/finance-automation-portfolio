"""
Data model for the combined-group franchise (margin) tax control engine.
========================================================================

The engine consumes **combined-return files**: one JSON file per fiscal year's
combined-group franchise-tax filing, carrying the artifacts that filing emits.
Each source artifact is modelled as a typed document -- a dict with a
``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: the tax the return claims versus the tax the workpapers re-derive
--------------------------------------------------------------------------
A group of affiliated development companies that does business in the fictional
State of Marran files a single **combined** franchise-tax return each fiscal
year. The return is not one entity's; it is the whole group's, apportioned to
Marran by a single receipts factor. Preparing it means three things happen
together, and each is a place a number can go wrong.

**The combined group is redrawn.** The affiliate roster is rebuilt each year --
last year's members, plus the affiliates that joined, minus the ones that left --
and the affiliates *not* included this year have to be enumerated and reconciled,
not silently dropped. An affiliate that quietly falls off the roster is revenue
that leaves the combined base with nobody noticing.

**The margin is apportioned.** Consolidated group revenue, taken from the
consolidated tax trial-balance workpaper, is reduced by the group's elected
deduction to a taxable margin, and that margin is apportioned to Marran by the
single receipts factor -- in-state receipts over everywhere receipts. A factor
struck against the wrong denominator, or a base that does not tie the trial
balance, is a tax computed on numbers nobody reconciled.

**The tax is a derived figure.** The tax is the margin times the apportionment
factor times the rate, in that order. A margin that does not re-derive from
revenue less the deduction, an apportioned figure that does not re-derive from
the factor, a tax that does not re-derive from the rate -- each looks right on
the return and is wrong underneath it.

So the controls here are re-derivation and reconciliation controls. The roster is
rebuilt from the prior list and the year's changes and compared; group revenue is
tied to the trial balance; the apportionment factor is recomputed from the
receipts; and the whole tax is recomputed from the workpapers and tied to the
return.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a roster that does not rebuild, a member
  with no registration, group revenue that does not tie the trial balance, an
  apportionment factor that does not recompute or falls outside ``[0, 1]``, a
  margin / apportioned-margin / tax that does not re-derive, a rollup that does
  not recompute).
- ``FLAG`` -- a human-review signal (an affiliate registration due to renew
  inside the lead-time window).
- ``PASS`` -- the rule ran and the control held.

A combined-return file with any FAIL rolls up to verdict ``FAIL``; FLAGs without
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
#: The affiliate roster and address tab: every affiliate, its address and its
#: state registration.
DOC_AFFILIATE_REGISTER = "affiliate_register"
#: The combined-group continuity workpaper: prior-year members, additions,
#: removals, the current-year member list, and the affiliates excluded this year.
DOC_COMBINED_GROUP = "combined_group"
#: The consolidated tax trial-balance workpaper: revenue lines by affiliate.
DOC_TRIAL_BALANCE = "trial_balance"
#: The single-factor receipts apportionment workpaper: in-state and everywhere
#: receipts by affiliate, the totals, and the factor.
DOC_RECEIPTS_FACTOR = "receipts_factor"
#: The margin-tax computation: group revenue, elected deduction, taxable margin,
#: apportionment factor, apportioned margin, rate and tax.
DOC_MARGIN_WORKSHEET = "margin_worksheet"
#: The per-return recomputed tax determination.
DOC_TAX_SUMMARY = "tax_summary"
#: The combined-return rollup: total tax due and combined-member count.
DOC_FRANCHISE_REPORT = "franchise_report"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_AFFILIATE_REGISTER,
    DOC_COMBINED_GROUP,
    DOC_TRIAL_BALANCE,
    DOC_RECEIPTS_FACTOR,
    DOC_MARGIN_WORKSHEET,
    DOC_TAX_SUMMARY,
    DOC_FRANCHISE_REPORT,
)

# --------------------------------------------------------------------------- #
# Combined-return vocabulary
# --------------------------------------------------------------------------- #
#: Affiliate registration statuses tracked on the address tab.
AFFILIATE_ACTIVE = "active"
AFFILIATE_INACTIVE = "inactive"
AFFILIATE_STATUSES: tuple[str, ...] = (AFFILIATE_ACTIVE, AFFILIATE_INACTIVE)

#: The fictional filing state's home code, used on the address tab.
HOME_STATE_CODE = "MARRAN"

#: Default lead-time, in days, for the registration-renewal window when a file
#: does not carry its own. A registration renewing inside this window is a FLAG,
#: not a failure: there is still time to lodge the renewal.
DEFAULT_LEAD_DAYS = 60


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a combined-return file or the whole run."""

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
        ``"mgn_tax_recomputes"``).
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
    """Everything a check needs about one combined-return file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the combined-return file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional combined group whose return the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future fiscal-year label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every renewal test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def lead_days(self) -> int:
        """Lead-time window, in days, for the registration-renewal flag.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_LEAD_DAYS` when it is absent or malformed.
        """
        value = self.data.get("lead_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_LEAD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the combined-return file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A combined-return file carries exactly one of each artifact. Returning
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
    """All findings for one combined-return file plus its rolled-up verdict."""

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
