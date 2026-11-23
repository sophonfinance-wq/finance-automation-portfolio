"""
Data model for the outstanding-check aging and escheatment control engine.
==========================================================================

The engine consumes **aging files**: one JSON file per entity's disbursement
bank accounts, carrying the artifacts the outstanding-check process emits at each
"as of" date. Each source artifact is modelled as a typed document -- a dict with
a ``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: what is still out there, not what was paid
-------------------------------------------------
This engine is the back half of the disbursement story. Whether a payment was
authorised, coded and released is somebody else's control. This one starts after
the check has left the building and asks a narrower question: of everything
issued, what has never cleared, how old is it, and what has to happen to it now?

A check register is a list of promises the bank has not yet been asked to keep.
Each row records a check number, a check date, a check type (manual or system), a
payee, the amount issued, the amount cleared and the date it cleared. Alongside
it sit the companion sets -- voided checks, zero-dollar checks and stop-payment
checks -- which record the promises that were withdrawn rather than kept.

Why that is worth an engine
---------------------------
Nothing in an outstanding-check register looks wrong, and three things go wrong
in it anyway.

**The outstanding set is asserted, not reconciled.** The schedule of outstanding
checks is a filtered view -- cleared amount of zero and no cleared date -- and the
moment somebody maintains it beside the register rather than deriving it from the
register, it drifts. A check that cleared last month stays on the schedule; a
check issued this month never reaches it; the bank reconciliation's outstanding
line ties to the schedule and not to the evidence.

**A withdrawn check keeps living.** A voided, zero-dollar or stop-payment check
still occupies a row in the register. If the void never nets the amount to zero,
or the check is still counted as outstanding, the reconciliation carries an
obligation that was cancelled.

**The clock runs and nobody hears it.** A check that has not cleared in six months
is stale-dated and the bank may refuse it; a check that has not cleared through
the dormancy period is unclaimed property and belongs to the state, not the
entity. Both are pure date arithmetic against an as-of date, and both are missed
because the register looks exactly the same on the day before and the day after.

So the controls here are re-derivation controls. The outstanding set, every aging
bucket, the follow-up marker and the escheatment schedule are all rebuilt from the
check register and compared to what the file says.

Severity model
--------------
- ``FAIL`` -- a hard control failure (an outstanding set that does not recompute,
  a void that does not net to zero, a duplicate check number in one account, a
  check dated after the as-of date, an escheatment schedule that does not tie).
- ``FLAG`` -- a human-review signal (a stale-dating follow-up marker that does not
  agree with the age, an aging-bucket subtotal that does not tie).
- ``PASS`` -- the rule ran and the control held.

An aging file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs roll
up to ``REVIEW``; everything clean is ``PASS``.

All shipped data is fictional. The engine never writes to a source artifact, and
it never voids, re-issues, escheats or pays anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Document type vocabulary
# --------------------------------------------------------------------------- #
#: The disbursement bank accounts in scope, and the escheat jurisdiction of each.
DOC_ACCOUNT_REGISTER = "bank_account_register"
#: Every check issued in the period, cleared or not.
DOC_CHECK_REGISTER = "check_register"
#: Voided, zero-dollar and stop-payment checks.
DOC_VOID_REGISTER = "void_register"
#: The stated schedule of checks still outstanding at the as-of date.
DOC_OUTSTANDING_SCHEDULE = "outstanding_schedule"
#: The stated schedule of outstanding checks past the dormancy period.
DOC_ESCHEATMENT_SCHEDULE = "escheatment_schedule"
#: The bank reconciliation's outstanding-checks line and aging subtotals.
DOC_BANK_RECONCILIATION = "bank_reconciliation"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_ACCOUNT_REGISTER,
    DOC_CHECK_REGISTER,
    DOC_VOID_REGISTER,
    DOC_OUTSTANDING_SCHEDULE,
    DOC_ESCHEATMENT_SCHEDULE,
    DOC_BANK_RECONCILIATION,
)

# --------------------------------------------------------------------------- #
# Disbursement vocabulary
# --------------------------------------------------------------------------- #
#: Cut by the disbursement run from an approved payment batch.
CHECK_TYPE_SYSTEM = "system"
#: Written outside the run -- the type that goes stale most often.
CHECK_TYPE_MANUAL = "manual"
CHECK_TYPES: tuple[str, ...] = (CHECK_TYPE_MANUAL, CHECK_TYPE_SYSTEM)

#: The check was cancelled before or after issue and the amount reversed.
DISPOSITION_VOIDED = "voided"
#: The check was cut for no value and carries no obligation.
DISPOSITION_ZERO_DOLLAR = "zero_dollar"
#: The bank was instructed not to pay the item.
DISPOSITION_STOP_PAYMENT = "stop_payment"
DISPOSITIONS: tuple[str, ...] = (
    DISPOSITION_VOIDED,
    DISPOSITION_ZERO_DOLLAR,
    DISPOSITION_STOP_PAYMENT,
)

#: Default stale-dating threshold, in days, when a file does not carry its own.
#: A check older than this is past the period most banks will honour it in.
DEFAULT_STALE_DATED_DAYS = 180

#: Default dormancy period, in days, when a file does not carry its own. An
#: outstanding check older than this is unclaimed property and reports to the
#: escheat jurisdiction of the account it was drawn on.
DEFAULT_DORMANCY_DAYS = 1095

#: Aging bands as ``(label, inclusive_upper_bound_in_days)``. The final band is
#: open-ended and carries ``None``. Adding a band is a row here -- never a control.
AGING_BUCKETS: tuple[tuple[str, int | None], ...] = (
    ("0-30", 30),
    ("31-60", 60),
    ("61-90", 90),
    ("91-180", 180),
    ("181-365", 365),
    ("366+", None),
)

#: Bucket labels alone, in report order.
BUCKET_LABELS: tuple[str, ...] = tuple(label for label, _upper in AGING_BUCKETS)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for an aging file or the whole run."""

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
        ``"age_outstanding_set_recomputes"``).
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
    """Everything a check needs about one aging file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the aging file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def portfolio(self) -> str:
        """Fictional entity whose disbursement accounts the file carries."""
        value = self.data.get("portfolio")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated as-of date every age and threshold test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def stale_dated_days(self) -> int:
        """Stale-dating threshold, in days.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_STALE_DATED_DAYS` when it is absent or malformed.
        """
        value = self.data.get("stale_dated_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_STALE_DATED_DAYS
        return value

    @property
    def dormancy_days(self) -> int:
        """Dormancy period, in days, after which an item escheats.

        Read from the file when present, falling back to
        :data:`DEFAULT_DORMANCY_DAYS` when it is absent or malformed.
        """
        value = self.data.get("dormancy_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_DORMANCY_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the aging file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        An aging file carries exactly one of each artifact. Returning ``None``
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
    """All findings for one aging file plus its rolled-up verdict."""

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
