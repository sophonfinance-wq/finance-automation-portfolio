"""
Data model for the non-resident withholding & 1042-S control engine.
====================================================================

The engine consumes **withholding files**: one JSON file per filer's Chapter 3/4
FDAP-withholding record for an annual Form 1042 cycle, carrying the artifacts that
record emits. Each source artifact is modelled as a typed document -- a dict with
a ``doc_type`` discriminator and typed fields -- so the whole engine stays
stdlib-only, deterministic and byte-stable.

Scope: the withholding is right, on file, remitted and reconciled
-----------------------------------------------------------------
A US withholding agent that pays cross-border interest, dividends, royalties or
rent to foreign recipients has to withhold Chapter 3 tax at the right rate, prove
each reduced rate is supported, deposit what it withheld, and reconcile the annual
Form 1042 to the 1042-S slips it files. This engine is that proof. It does not pay
anyone and it does not file anything; the question here is narrower and entirely
evidentiary: does the withholding the workpapers state actually recompute from the
payee's status and the treaty table, is every reduced rate supported by a valid
W-8, and do the 1042 totals tie to the slips and the deposits?

Why that is worth an engine
---------------------------
A withholding determination is a snapshot of a payee's status on the day a payment
went out, and it goes stale -- or was wrong to begin with -- in ways nobody
watches.

Four things go wrong, and none of them look wrong.

**The rate is reduced without support.** A payment is withheld at a treaty rate
while the W-8 that would support it is missing, expired, or claims a
limitation-on-benefits code that was never valid. The paper shows a low rate; the
support for it is not there.

**The classification is off.** A US payee is withheld on, or excluded when it
should not be; an accrued-but-unpaid coupon is treated as paid; a
non-participating FFI is given treaty relief it is barred from; a contingent
coupon is coded as exempt portfolio interest.

**The deposit drifts from the liability.** The tax withheld across the year does
not equal what was deposited, or the annual return is filed after its due date.

**The return does not tie to the slips.** The Form 1042 total gross or total tax
does not equal the sum of the 1042-S slips, or a reportable payee has no slip at
all.

So the controls here are evidentiary controls. Every payment's applicable rate is
recomputed from the payee's status and the treaty table and compared; every reduced
rate is gated on a valid W-8; and the 1042 totals are rebuilt from the slips and
the deposits.

Severity model
--------------
- ``FAIL`` -- a hard control failure (a rate that does not recompute, a reduced
  rate with no valid W-8, a US payee withheld, an accrued coupon withheld, a
  deposit or return total that does not tie).
- ``FLAG`` -- a human-review signal (a W-8 due for renewal inside the lead-time
  window, an expiry watchlist that does not tie the evidence).
- ``PASS`` -- the rule ran and the control held.

A withholding file with any FAIL rolls up to verdict ``FAIL``; FLAGs without FAILs
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
#: Every foreign recipient the filer paid, with its Chapter 3/4 status and W-8.
DOC_PAYEE_REGISTER = "payee_register"
#: Treaty / statutory rate lookup, keyed by (country, income_type).
DOC_TREATY_RATE_TABLE = "treaty_rate_table"
#: The fixed list of 1042-S income codes and what each one means.
DOC_INCOME_CODE_TABLE = "income_code_table"
#: Every FDAP payment made in the cycle, with its stated rate and tax withheld.
DOC_PAYMENT_REGISTER = "payment_register"
#: Every deposit remitted toward the year's withholding liability.
DOC_DEPOSIT_REGISTER = "deposit_register"
#: One 1042-S slip per reportable payee.
DOC_SLIP_REGISTER = "slip_register"
#: Payees whose W-8 is due for renewal inside the lead-time window.
DOC_W8_WATCHLIST = "w8_watchlist"
#: The annual Form 1042 reconciliation panel.
DOC_FORM_1042 = "form_1042"

#: Every document type the engine understands, in canonical report order.
DOC_TYPES: tuple[str, ...] = (
    DOC_PAYEE_REGISTER,
    DOC_TREATY_RATE_TABLE,
    DOC_INCOME_CODE_TABLE,
    DOC_PAYMENT_REGISTER,
    DOC_DEPOSIT_REGISTER,
    DOC_SLIP_REGISTER,
    DOC_W8_WATCHLIST,
    DOC_FORM_1042,
)

# --------------------------------------------------------------------------- #
# Withholding vocabulary
# --------------------------------------------------------------------------- #
#: Chapter 3 status code that marks a US person -- excluded from withholding.
CH3_US_PERSON = "US"
#: Known Chapter 3 recipient status codes (a fixed classification list).
#: ``15`` foreign individual, ``16`` foreign corporation, ``US`` US person.
CH3_STATUS_CODES: tuple[str, ...] = ("15", "16", CH3_US_PERSON)

#: Known Chapter 4 (FATCA) status codes. ``01`` participating FFI, ``09``
#: non-participating FFI, ``19`` passive NFFE, ``22`` active NFFE.
CH4_STATUS_CODES: tuple[str, ...] = ("01", "09", "19", "22")
#: The Chapter 4 statuses that force the statutory rate regardless of treaty.
NONPARTICIPATING_FFI_CODES: tuple[str, ...] = ("09",)

#: Known limitation-on-benefits (Article XXIX-A) codes.
LOB_CODES: tuple[str, ...] = ("01", "02", "03", "04", "05")

#: Payment status vocabulary. Only ``paid`` amounts are subject to withholding.
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_ACCRUED = "accrued"
PAYMENT_STATUSES: tuple[str, ...] = (PAYMENT_STATUS_PAID, PAYMENT_STATUS_ACCRUED)

#: Interest sub-character. Contingent interest is ineligible for the
#: portfolio-interest exemption, so it is tracked separately.
INTEREST_BASE = "base"
INTEREST_MAKE_WHOLE = "make_whole"
INTEREST_CONTINGENT = "contingent"
INTEREST_SUBCHARACTERS: tuple[str, ...] = (
    INTEREST_BASE,
    INTEREST_MAKE_WHOLE,
    INTEREST_CONTINGENT,
)

#: Income types the treaty table is keyed on.
INCOME_TYPES: tuple[str, ...] = ("interest", "dividend", "royalty", "rent")

#: The W-8 status string that reads valid.
W8_STATUS_VALID = "valid"

#: Default lead-time, in days, for the W-8 renewal watchlist when a file does not
#: carry its own. A W-8 expiring inside this window is a FLAG, not a failure --
#: there is still time to collect a fresh form.
DEFAULT_W8_RENEWAL_LEAD_DAYS = 60


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    """Status of a single finding."""

    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"


class Verdict(str, Enum):
    """Overall verdict for a withholding file or the whole run."""

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
        ``"wh_rate_recomputes"``).
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
    """Everything a check needs about one withholding file.

    The context is a thin, read-only view over the parsed JSON. It never copies or
    rewrites the payload, so a check is structurally incapable of mutating a
    source artifact.
    """

    path: Path
    data: dict[str, Any]

    @property
    def file_id(self) -> str:
        """Identifier of the withholding file (falls back to the file stem)."""
        value = self.data.get("file_id")
        return str(value) if isinstance(value, str) else self.path.stem

    @property
    def filer(self) -> str:
        """Fictional withholding agent whose 1042 record the file carries."""
        value = self.data.get("filer")
        return str(value) if isinstance(value, str) else "-"

    @property
    def period(self) -> str:
        """Fictional-future reporting period label."""
        value = self.data.get("period")
        return str(value) if isinstance(value, str) else "-"

    @property
    def as_of(self) -> str:
        """The stated review date every expiry and renewal test is measured to."""
        value = self.data.get("as_of")
        return str(value) if isinstance(value, str) else "-"

    @property
    def w8_renewal_lead_days(self) -> int:
        """Lead-time window, in days, for the W-8 renewal watchlist.

        Read from the file when present so the band comes from the data, falling
        back to :data:`DEFAULT_W8_RENEWAL_LEAD_DAYS` when it is absent or malformed.
        """
        value = self.data.get("w8_renewal_lead_days")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return DEFAULT_W8_RENEWAL_LEAD_DAYS
        return value

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Every document in the withholding file, in file order."""
        docs = self.data.get("documents")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]

    def docs(self, doc_type: str) -> list[dict[str, Any]]:
        """Return every document of ``doc_type``, in file order."""
        return [d for d in self.documents if d.get("doc_type") == doc_type]

    def one(self, doc_type: str) -> dict[str, Any] | None:
        """Return the single document of ``doc_type``, or ``None``.

        A withholding file carries exactly one of each artifact. Returning
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
    """All findings for one withholding file plus its rolled-up verdict."""

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
