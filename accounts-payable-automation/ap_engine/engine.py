"""
Accounts payable control engine (READ-ONLY).
============================================

Loads each posting document set (a ``.json`` file produced by
:mod:`ap_engine.generate`) and runs an ordered *registry* of independent
controls over it. Every check returns zero or more :class:`~ap_engine.model.Finding`
objects; the per-set findings roll up into a
:class:`~ap_engine.model.DocumentReport` with an overall
:class:`~ap_engine.model.Verdict`.

The registry opens with ``set_*``, the structural precondition -- is the
document set complete enough to be worth reading? -- and then answers the four
questions a controller actually asks:

1. ``post_*``  -- did the post actually happen, and did it balance?
2. ``gate_*``  -- is this payment allowed to be released yet?
3. ``route_*`` -- is every job routed to a valid approver chain, duties split?
4. ``ir_*``    -- will year-end information reporting be complete and correct?

plus ``cmt_*`` for commitment hygiene, which is where the other three go wrong
one period later.

Design notes
------------
- **Strictly read-only.** Documents are parsed and never written back. The
  engine is incapable of *introducing* a defect -- it can only report.
- **Deterministic.** Same inputs, same findings, in the same order. Every glob,
  dict and set iteration is forced through ``sorted()`` with a tiebreaker.
- **Integer cents, no tolerance.** Amounts are compared with exact ``==``. A
  value that should be integer cents but is not produces an ``AMOUNT_INVALID``
  finding -- at the owning rule's declared severity, contained to the one row it
  was read on -- rather than being coerced.
- **Absent evidence is not a passing control.** ``set_complete`` runs first and
  fails a set that does not carry every artifact type the registry reads.
- **Extensible.** A check is a function ``(Context) -> list[Finding]``
  registered by the :func:`check` decorator. New rules drop into
  :data:`REGISTRY` without touching the runner.

Benign versus blocking
----------------------
An informational "job-cost entries not created" notice is normal for a
ledger-only invoice and is explicitly **not** a failure. Only a blocking error
marker -- batch contention, an aborted update -- fails ``post_no_error_marker``.
Conflating the two produces false positives on every clean ledger-only run.

The classification is driven by the **text**, and runs over ``error_markers``
and ``notices`` alike, so the same sentence cannot pass in one field and fail in
the other. The single asymmetry is conservative: an unrecognised line in
``error_markers`` stays blocking.
"""

from __future__ import annotations

import contextlib
import functools
import json
import re
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from .model import (
    DOC_COMMITMENT_REGISTER,
    DOC_INFORMATION_REPORTING,
    DOC_INVOICE_POSTING,
    DOC_PAYMENT_SELECTION,
    DOC_TYPES,
    DOC_WORKFLOW_MATRIX,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, apply_rate, fmt, require_cents, total

# --------------------------------------------------------------------------- #
# Check registry
# --------------------------------------------------------------------------- #
CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs. Order is preserved so the
#: report is deterministic.
REGISTRY: list[tuple[str, CheckFn]] = []


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~ap_engine.money.AmountInvalidError` as a finding.

    The status is the rule's **declared** severity, read from :data:`SEVERITY`
    at call time. A malformed amount is evidence about the rule that read it, so
    it cannot be more severe than the control itself: a FLAG-only rule that
    hard-coded FAIL here would escalate a whole document set from REVIEW to FAIL
    on a schema defect. An unregistered rule falls back to FAIL.
    """
    return Finding(
        rule_id,
        SEVERITY.get(rule_id, Status.FAIL),
        f"amount:{exc.field}",
        f"{exc} -- amounts are integer cents and are never coerced",
    )


@contextlib.contextmanager
def amount_guard(rule_id: str, out: list[Finding]) -> Iterator[None]:
    """Contain a malformed amount to the **one row** being read.

    A check wraps each document, payment line or register row in this guard so a
    single bad amount costs that row and no more. Guarding the whole check body
    instead would abort the remaining iterations silently -- one malformed
    ``amount_cents`` would end duplicate detection for an entire register, and
    the report would show no exception for the lines never examined.
    """
    try:
        yield
    except AmountInvalidError as exc:
        out.append(amount_invalid_finding(rule_id, exc))


def check(rule_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register ``fn`` in :data:`REGISTRY` under ``rule_id``.

    The wrapper is the last-resort net for an
    :class:`~ap_engine.money.AmountInvalidError` raised outside any per-row
    :func:`amount_guard`, so a malformed amount anywhere in a document surfaces
    as an ``AMOUNT_INVALID`` exception on the owning rule -- at that rule's
    declared severity -- instead of crashing the run.
    """

    def wrapper(fn: CheckFn) -> CheckFn:
        @functools.wraps(fn)
        def guarded(ctx: Context) -> list[Finding]:
            try:
                return fn(ctx)
            except AmountInvalidError as exc:
                # SEVERITY is defined below this decorator, so the lookup has to
                # happen here, at call time, not when the rule is registered.
                return [amount_invalid_finding(rule_id, exc)]

        REGISTRY.append((rule_id, guarded))
        return guarded

    return wrapper


# --------------------------------------------------------------------------- #
# Rule configuration (kept here so checks stay declarative)
# --------------------------------------------------------------------------- #
#: The severity a rule uses when the control does *not* hold. Mirrors the
#: design tables; a test cross-checks it against observed behaviour.
SEVERITY: dict[str, Status] = {
    # Structural precondition
    "set_complete": Status.FAIL,
    # Posting integrity
    "post_proof_zero": Status.FAIL,
    "post_gl_balanced": Status.FAIL,
    "post_totals_balanced": Status.FAIL,
    "post_no_rejects": Status.FAIL,
    "post_actually_posted": Status.FAIL,
    "post_no_error_marker": Status.FAIL,
    "post_jobcost_ties": Status.FAIL,
    "post_header_date_agrees": Status.FLAG,
    # Payment release gate
    "gate_w9_on_file": Status.FAIL,
    "gate_lien_waiver": Status.FAIL,
    "gate_insurance_current": Status.FAIL,
    "gate_insurance_limits": Status.FLAG,
    "gate_funding_confirmed": Status.FAIL,
    "gate_no_duplicate": Status.FAIL,
    "gate_retention_present": Status.FLAG,
    "gate_offcycle_approved": Status.FLAG,
    # Routing and segregation of duties
    "route_every_job_mapped": Status.FAIL,
    "route_workflow_has_approver": Status.FAIL,
    "route_final_review_present": Status.FAIL,
    "route_duties_segregated": Status.FAIL,
    "route_preapproved_declared": Status.FLAG,
    # Information reporting
    "ir_threshold_coverage": Status.FAIL,
    "ir_tin_present": Status.FAIL,
    "ir_tin_structure": Status.FLAG,
    "ir_no_split_vendor": Status.FLAG,
    "ir_filed_reconciles": Status.FAIL,
    # Commitment hygiene
    "cmt_sov_not_lump_sum": Status.FAIL,
    "cmt_id_convention": Status.FLAG,
    "cmt_co_attaches_to_original": Status.FLAG,
}

#: Prefix of the structural precondition family. It is deliberately a family of
#: one: a single gate that proves the set is readable before any control family
#: is applied to it.
PRECONDITION_FAMILY = "set"

#: Rule-id prefixes, in registry order. Used by the report family rollup.
RULE_FAMILIES: tuple[str, ...] = (PRECONDITION_FAMILY, "post", "gate", "route", "ir", "cmt")

#: Phrases that mark a *blocking* posting error. A run carrying any of these
#: did not complete, whatever the operator filed.
BLOCKING_MARKERS: tuple[str, ...] = (
    "batch contention",
    "aborted update",
    "update aborted",
    "post aborted",
    "posting aborted",
    "run terminated",
)

#: Phrases that mark a *benign, informational* notice. Normal on a ledger-only
#: invoice; never a control failure.
BENIGN_NOTICE_MARKERS: tuple[str, ...] = (
    "job-cost entries not created",
    "job cost entries not created",
    "no job-cost entries",
    "ledger-only",
)

#: Counters that must be zero on a clean posting run.
REJECT_COUNTERS: tuple[str, ...] = ("invoices", "entries", "job_cost_entries")

#: Counters that prove documents actually reached the ledger. ``job_cost_entries``
#: is deliberately excluded: zero is legitimate for a ledger-only invoice.
POSTED_COUNTERS: tuple[str, ...] = ("invoices", "entries")

#: Coverage lines compared against the contract minimums, in report order.
COVERAGE_LINES: tuple[str, ...] = (
    "general_liability_cents",
    "auto_liability_cents",
    "umbrella_cents",
)

#: Structural shape of a fictional taxpayer identification number.
TIN_PATTERN = re.compile(r"^\d{2}-\d{7}$")

#: Eight consecutive digits in a file name, read as ``YYYYMMDD``.
FILE_DATE_PATTERN = re.compile(r"(?<!\d)(\d{8})(?!\d)")

#: Suffix a commitment identifier must end with: two digits after the
#: ``<job>-<vendor>-`` stem.
COMMITMENT_SUFFIX_PATTERN = re.compile(r"^\d{2}$")

#: Commitment types whose schedule of values must mirror the contract.
DETAILED_CONTRACT_TYPES: tuple[str, ...] = ("subcontract",)


# --------------------------------------------------------------------------- #
# Small typed readers
# --------------------------------------------------------------------------- #
def _cents(doc: dict[str, Any], field_path: str, value: object) -> int:
    """Read ``value`` as integer cents, tagging the error with its location."""
    return require_cents(f"{doc.get('document_id', '?')}/{field_path}", value)


def _count(doc: dict[str, Any], field_path: str, value: object) -> int:
    """Read ``value`` as a whole count, tagging the error with its location."""
    return require_cents(
        f"{doc.get('document_id', '?')}/{field_path}", value, unit="a whole count"
    )


def _bps(doc: dict[str, Any], field_path: str, value: object) -> int:
    """Read ``value`` as an integer basis-point rate."""
    return require_cents(
        f"{doc.get('document_id', '?')}/{field_path}",
        value,
        unit="an integer basis-point rate",
    )


def _dig(node: object, *keys: str) -> object:
    """Walk nested dicts, returning ``None`` at the first missing/odd level."""
    cur: object = node
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _rows(node: object, key: str) -> list[dict[str, Any]]:
    """Return ``node[key]`` as a list of dicts (empty when absent or odd)."""
    value = _dig(node, key)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _strs(node: object, key: str) -> list[str]:
    """Return ``node[key]`` as a list of strings (empty when absent or odd)."""
    value = _dig(node, key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _text(value: object) -> str:
    """Return ``value`` as a stripped string ("" for anything non-string)."""
    return value.strip() if isinstance(value, str) else ""


def _is_true(value: object) -> bool:
    """Strict boolean truth: only ``True`` counts, never ``1`` or ``"yes"``."""
    return value is True


def _iso_date(value: object) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` string, or return ``None``."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _label(row: dict[str, Any], *keys: str) -> str:
    """First present identifier among ``keys``, for readable locations."""
    for key in keys:
        text = _text(row.get(key))
        if text:
            return text
    return "?"


# --------------------------------------------------------------------------- #
# 0. Structural precondition -- is there a document set here at all?
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """The set must carry every artifact type the registry reads.

    Every other rule iterates the documents of one type and returns nothing when
    that type is absent. Absent evidence therefore looks exactly like a held
    control: an empty payload produces zero findings and a PASS verdict, and a
    set missing two artifacts silently drops half the registry while still
    reporting PASS. This rule is registered first so the report opens with proof
    that the controls below it had something to read.
    """
    loc = "document_set/documents"
    raw = ctx.data.get("documents")
    if not isinstance(raw, list):
        return [
            Finding(
                "set_complete",
                Status.FAIL,
                loc,
                f"the document set carries no documents list (found "
                f"{type(raw).__name__}); every control below would report nothing "
                f"and the set would be filed as though it passed",
            )
        ]
    present = {str(doc.get("doc_type")) for doc in ctx.documents}
    missing = [doc_type for doc_type in DOC_TYPES if doc_type not in present]
    if missing:
        return [
            Finding(
                "set_complete",
                Status.FAIL,
                loc,
                f"the document set is missing {len(missing)} of {len(DOC_TYPES)} "
                f"required artifact type(s): {', '.join(missing)}; the controls that "
                f"read them cannot run and their silence is not a passing control",
            )
        ]
    return [
        Finding(
            "set_complete",
            Status.PASS,
            loc,
            f"all {len(DOC_TYPES)} required artifact type(s) present across "
            f"{len(ctx.documents)} document(s); every control below has evidence to "
            f"read",
        )
    ]


# --------------------------------------------------------------------------- #
# 1. Posting integrity -- did the post actually happen, and did it balance?
# --------------------------------------------------------------------------- #
@check("post_proof_zero")
def check_post_proof_zero(ctx: Context) -> list[Finding]:
    """The posting proof figure must be exactly zero.

    The proof is the ERP's own out-of-balance residual. Any non-zero value means
    the run wrote a one-sided entry somewhere, so the ledger is wrong even if
    every other total on the report looks plausible.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        with amount_guard("post_proof_zero", out):
            proof = _cents(doc, "posting_proof_cents", doc.get("posting_proof_cents"))
            loc = ctx.loc(doc, "posting_proof_cents")
            if proof == 0:
                out.append(
                    Finding(
                        "post_proof_zero",
                        Status.PASS,
                        loc,
                        "posting proof is exactly zero; the run left no out-of-balance "
                        "residual",
                    )
                )
            else:
                out.append(
                    Finding(
                        "post_proof_zero",
                        Status.FAIL,
                        loc,
                        f"posting proof is {fmt(proof)}, not zero; the run wrote a "
                        f"one-sided entry and the ledger is out of balance",
                    )
                )
    return out


@check("post_gl_balanced")
def check_post_gl_balanced(ctx: Context) -> list[Finding]:
    """Ledger recap debits must equal credits, exactly.

    The recap is the posting report's own summary of what reached the ledger. If
    it does not balance, the sub-ledger and the ledger disagree from the moment
    the run finished.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        with amount_guard("post_gl_balanced", out):
            debit = _cents(doc, "gl_recap.debit_cents", _dig(doc, "gl_recap", "debit_cents"))
            credit = _cents(doc, "gl_recap.credit_cents", _dig(doc, "gl_recap", "credit_cents"))
            loc = ctx.loc(doc, "gl_recap")
            if debit == credit:
                out.append(
                    Finding(
                        "post_gl_balanced",
                        Status.PASS,
                        loc,
                        f"ledger recap balances (debit == credit == {fmt(debit)})",
                    )
                )
            else:
                out.append(
                    Finding(
                        "post_gl_balanced",
                        Status.FAIL,
                        loc,
                        f"ledger recap does not balance: debit {fmt(debit)} vs credit "
                        f"{fmt(credit)} (difference {fmt(debit - credit)})",
                    )
                )
    return out


@check("post_totals_balanced")
def check_post_totals_balanced(ctx: Context) -> list[Finding]:
    """The posting-total debit must equal the posting-total credit.

    The posting totals and the ledger recap are produced by different sections
    of the report; checking both catches a run that balanced in one and not the
    other, which is the signature of a partially applied batch.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        with amount_guard("post_totals_balanced", out):
            debit = _cents(
                doc, "posting_totals.debit_cents", _dig(doc, "posting_totals", "debit_cents")
            )
            credit = _cents(
                doc, "posting_totals.credit_cents", _dig(doc, "posting_totals", "credit_cents")
            )
            loc = ctx.loc(doc, "posting_totals")
            if debit == credit:
                out.append(
                    Finding(
                        "post_totals_balanced",
                        Status.PASS,
                        loc,
                        f"posting totals balance (debit == credit == {fmt(debit)})",
                    )
                )
            else:
                out.append(
                    Finding(
                        "post_totals_balanced",
                        Status.FAIL,
                        loc,
                        f"posting totals do not balance: debit {fmt(debit)} vs credit "
                        f"{fmt(credit)} (difference {fmt(debit - credit)}); the batch was "
                        f"only partially applied",
                    )
                )
    return out


@check("post_no_rejects")
def check_post_no_rejects(ctx: Context) -> list[Finding]:
    """Rejected counts must be zero for invoices, entries and job-cost entries.

    A rejected document is one the operator believes was filed. Nobody goes back
    for it unless a control names it.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        rejected = _dig(doc, "rejected")
        for counter in REJECT_COUNTERS:
            with amount_guard("post_no_rejects", out):
                raw = _dig(rejected, counter)
                count = _count(doc, f"rejected.{counter}", raw)
                loc = ctx.loc(doc, f"rejected.{counter}")
                if count == 0:
                    out.append(
                        Finding(
                            "post_no_rejects",
                            Status.PASS,
                            loc,
                            f"no rejected {counter.replace('_', ' ')}",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            "post_no_rejects",
                            Status.FAIL,
                            loc,
                            f"{count} rejected {counter.replace('_', ' ')}; the run reports "
                            f"success but those documents never reached the ledger",
                        )
                    )
    return out


@check("post_actually_posted")
def check_post_actually_posted(ctx: Context) -> list[Finding]:
    """A posting report must record more than zero posted documents.

    Batch contention can abort a post and still emit a well-formed, balanced
    report -- everything ties because nothing moved. Job-cost entries are
    excluded from this count on purpose: zero is legitimate for a ledger-only
    invoice.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        posted = _dig(doc, "posted_counts")
        for counter in POSTED_COUNTERS:
            with amount_guard("post_actually_posted", out):
                count = _count(doc, f"posted_counts.{counter}", _dig(posted, counter))
                loc = ctx.loc(doc, f"posted_counts.{counter}")
                if count > 0:
                    out.append(
                        Finding(
                            "post_actually_posted",
                            Status.PASS,
                            loc,
                            f"{count} {counter.replace('_', ' ')} reached the ledger",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            "post_actually_posted",
                            Status.FAIL,
                            loc,
                            f"zero {counter.replace('_', ' ')} posted; the report balances "
                            f"because nothing moved -- the run was filed as though it "
                            f"succeeded",
                        )
                    )
    return out


@check("post_no_error_marker")
def check_post_no_error_marker(ctx: Context) -> list[Finding]:
    """No blocking ERP error may appear on the posting report.

    Blocking means the run stopped: batch contention, an aborted update. A
    benign "job-cost entries not created" notice is normal for a ledger-only
    invoice and is reported as informational, never as a failure. Conflating the
    two is the single most expensive false positive in this family.

    The text decides, not the field it arrived in. The same classification runs
    over ``error_markers`` and ``notices``, so a benign line cannot fail a run by
    landing in the wrong list. The one asymmetry is deliberate and conservative:
    an *unrecognised* line in ``error_markers`` stays blocking, because the ERP
    filed it as an error and the engine will not talk it down.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        # error_markers first, so a run carrying both reports the marker first.
        sourced: list[tuple[str, str]] = [
            *(("error_markers", m) for m in _strs(doc, "error_markers")),
            *(("notices", n) for n in _strs(doc, "notices")),
        ]
        blocking: list[tuple[str, str]] = []
        benign: list[str] = []
        other: list[str] = []
        for source, text in sourced:
            low = text.lower()
            if any(phrase in low for phrase in BLOCKING_MARKERS):
                blocking.append((source, text))
            elif any(phrase in low for phrase in BENIGN_NOTICE_MARKERS):
                benign.append(text)
            elif source == "error_markers":
                blocking.append((source, text))
            else:
                other.append(text)
        if blocking:
            for source, text in blocking:
                out.append(
                    Finding(
                        "post_no_error_marker",
                        Status.FAIL,
                        ctx.loc(doc, source),
                        f"blocking posting error: {text!r}; the run did not complete and "
                        f"the invoices are not in the ledger",
                    )
                )
        else:
            out.append(
                Finding(
                    "post_no_error_marker",
                    Status.PASS,
                    ctx.loc(doc, "error_markers"),
                    f"no blocking posting error; {len(benign)} recognised benign notice(s) "
                    f"and {len(other)} other informational notice(s) carried without "
                    f"failing the run",
                )
            )
    return out


@check("post_jobcost_ties")
def check_post_jobcost_ties(ctx: Context) -> list[Finding]:
    """The job-cost recap total must equal the payable cost total, exactly.

    These two figures are produced by different sub-systems from the same
    invoices. When they diverge, job cost and the payable ledger tell the project
    team two different stories about the same period.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        with amount_guard("post_jobcost_ties", out):
            recap = _cents(doc, "job_cost_recap_cents", doc.get("job_cost_recap_cents"))
            payable = _cents(
                doc, "payable_cost_total_cents", doc.get("payable_cost_total_cents")
            )
            loc = ctx.loc(doc, "job_cost_recap_cents")
            if recap == payable:
                out.append(
                    Finding(
                        "post_jobcost_ties",
                        Status.PASS,
                        loc,
                        f"job-cost recap ties to the payable cost total ({fmt(recap)})",
                    )
                )
            else:
                out.append(
                    Finding(
                        "post_jobcost_ties",
                        Status.FAIL,
                        loc,
                        f"job-cost recap {fmt(recap)} does not tie to the payable cost "
                        f"total {fmt(payable)} (difference {fmt(recap - payable)})",
                    )
                )
    return out


@check("post_header_date_agrees")
def check_post_header_date_agrees(ctx: Context) -> list[Finding]:
    """The header date must agree with the date encoded in the file name.

    A drifting pair means the report was re-run, re-saved or re-filed under the
    wrong period -- the cheapest available signal that a posting artifact is
    filed against the wrong month.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INVOICE_POSTING):
        file_name = _text(doc.get("file_name"))
        loc = ctx.loc(doc, "header_date")
        header = _iso_date(doc.get("header_date"))
        match = FILE_DATE_PATTERN.search(file_name)
        if header is None:
            out.append(
                Finding(
                    "post_header_date_agrees",
                    Status.FLAG,
                    loc,
                    f"header date {doc.get('header_date')!r} is not an ISO date; the "
                    f"period the report belongs to cannot be established",
                )
            )
            continue
        if match is None:
            out.append(
                Finding(
                    "post_header_date_agrees",
                    Status.FLAG,
                    loc,
                    f"file name {file_name!r} carries no YYYYMMDD stamp to compare the "
                    f"header date against",
                )
            )
            continue
        stamp = match.group(1)
        encoded = _iso_date(f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}")
        if encoded == header:
            out.append(
                Finding(
                    "post_header_date_agrees",
                    Status.PASS,
                    loc,
                    f"header date agrees with the file name stamp ({header.isoformat()})",
                )
            )
        else:
            out.append(
                Finding(
                    "post_header_date_agrees",
                    Status.FLAG,
                    loc,
                    f"header date {header.isoformat()} disagrees with the file name stamp "
                    f"{stamp}; the report may be filed against the wrong period",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# 2. Payment release gate -- is this payment allowed to be released yet?
# --------------------------------------------------------------------------- #
def _payments(ctx: Context) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield ``(register, payment)`` pairs across every selection register."""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for doc in ctx.docs(DOC_PAYMENT_SELECTION):
        for payment in _rows(doc, "payments"):
            out.append((doc, payment))
    return out


def _payment_loc(ctx: Context, doc: dict[str, Any], payment: dict[str, Any], leaf: str) -> str:
    """Location string for a field on one payment line."""
    pay_id = _label(payment, "payment_id", "document_number")
    return ctx.loc(doc, f"payments[{pay_id}].{leaf}")


@check("gate_w9_on_file")
def check_gate_w9_on_file(ctx: Context) -> list[Finding]:
    """A taxpayer-identification certificate must exist before a first payment.

    Chasing the certificate after the money has left is how a vendor ends the
    year unreportable and the entity ends it with a penalty.
    """
    out: list[Finding] = []
    for doc, payment in _payments(ctx):
        if not _is_true(payment.get("first_payment")):
            continue
        loc = _payment_loc(ctx, doc, payment, "w9_on_file")
        vendor = _label(payment, "vendor_name", "vendor_id")
        if _is_true(payment.get("w9_on_file")):
            out.append(
                Finding(
                    "gate_w9_on_file",
                    Status.PASS,
                    loc,
                    f"taxpayer certificate on file for first payment to {vendor}",
                )
            )
        else:
            out.append(
                Finding(
                    "gate_w9_on_file",
                    Status.FAIL,
                    loc,
                    f"first payment to {vendor} has no taxpayer certificate on file; "
                    f"release is not permitted until it is received",
                )
            )
    return out


@check("gate_lien_waiver")
def check_gate_lien_waiver(ctx: Context) -> list[Finding]:
    """Waivers must be received from the subcontractor and its lower tiers.

    A lower-tier lien survives payment to the tier above it. Missing one tier is
    enough to leave the property encumbered after the money is gone.
    """
    out: list[Finding] = []
    for doc, payment in _payments(ctx):
        waiver = _dig(payment, "lien_waiver")
        loc = _payment_loc(ctx, doc, payment, "lien_waiver")
        vendor = _label(payment, "vendor_name", "vendor_id")
        if not isinstance(waiver, dict) or not _is_true(waiver.get("required")):
            out.append(
                Finding(
                    "gate_lien_waiver",
                    Status.PASS,
                    loc,
                    f"no lien waiver required for {vendor} on this payment",
                )
            )
            continue
        if not _is_true(waiver.get("vendor_received")):
            out.append(
                Finding(
                    "gate_lien_waiver",
                    Status.FAIL,
                    loc,
                    f"lien waiver from {vendor} not received; release is not permitted",
                )
            )
            continue
        required = sorted(set(_strs(waiver, "lower_tier_required")))
        received = set(_strs(waiver, "lower_tier_received"))
        missing = [tier for tier in required if tier not in received]
        if missing:
            out.append(
                Finding(
                    "gate_lien_waiver",
                    Status.FAIL,
                    loc,
                    f"lower-tier lien waiver(s) not received from {', '.join(missing)}; "
                    f"a lower-tier lien survives payment to {vendor}",
                )
            )
        else:
            out.append(
                Finding(
                    "gate_lien_waiver",
                    Status.PASS,
                    loc,
                    f"lien waivers received from {vendor} and {len(required)} lower tier(s)",
                )
            )
    return out


@check("gate_insurance_current")
def check_gate_insurance_current(ctx: Context) -> list[Finding]:
    """An insurance certificate must be present and unexpired at payment date.

    An expired certificate is indistinguishable from no certificate once a claim
    is filed against the period the work was performed in.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_PAYMENT_SELECTION):
        pay_date = _iso_date(doc.get("payment_date"))
        for payment in _rows(doc, "payments"):
            insurance = _dig(payment, "insurance")
            loc = _payment_loc(ctx, doc, payment, "insurance.expires_on")
            vendor = _label(payment, "vendor_name", "vendor_id")
            if not isinstance(insurance, dict) or not _is_true(
                insurance.get("certificate_on_file")
            ):
                out.append(
                    Finding(
                        "gate_insurance_current",
                        Status.FAIL,
                        loc,
                        f"no insurance certificate on file for {vendor}; release is not "
                        f"permitted",
                    )
                )
                continue
            expires = _iso_date(insurance.get("expires_on"))
            if expires is None or pay_date is None:
                out.append(
                    Finding(
                        "gate_insurance_current",
                        Status.FAIL,
                        loc,
                        f"insurance expiry {insurance.get('expires_on')!r} or payment date "
                        f"{doc.get('payment_date')!r} is not an ISO date; currency cannot "
                        f"be established for {vendor}",
                    )
                )
            elif expires >= pay_date:
                out.append(
                    Finding(
                        "gate_insurance_current",
                        Status.PASS,
                        loc,
                        f"insurance for {vendor} is current through {expires.isoformat()}",
                    )
                )
            else:
                out.append(
                    Finding(
                        "gate_insurance_current",
                        Status.FAIL,
                        loc,
                        f"insurance for {vendor} expired {expires.isoformat()}, before the "
                        f"payment date {pay_date.isoformat()}; release is not permitted",
                    )
                )
    return out


@check("gate_insurance_limits")
def check_gate_insurance_limits(ctx: Context) -> list[Finding]:
    """Coverage must meet the contract minimums, line by line.

    A current certificate with thin limits passes every date test and still
    leaves the entity self-insured above the shortfall.
    """
    out: list[Finding] = []
    for doc, payment in _payments(ctx):
        insurance = _dig(payment, "insurance")
        minimums = _dig(payment, "contract_minimums")
        if not isinstance(insurance, dict) or not isinstance(minimums, dict):
            continue
        vendor = _label(payment, "vendor_name", "vendor_id")
        for line in COVERAGE_LINES:
            if line not in minimums:
                continue
            with amount_guard("gate_insurance_limits", out):
                loc = _payment_loc(ctx, doc, payment, f"insurance.{line}")
                carried = _cents(doc, f"insurance.{line}", insurance.get(line))
                floor = _cents(doc, f"contract_minimums.{line}", minimums.get(line))
                label = line.removesuffix("_cents").replace("_", " ")
                if carried >= floor:
                    out.append(
                        Finding(
                            "gate_insurance_limits",
                            Status.PASS,
                            loc,
                            f"{vendor} {label} coverage {fmt(carried)} meets the contract "
                            f"minimum {fmt(floor)}",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            "gate_insurance_limits",
                            Status.FLAG,
                            loc,
                            f"{vendor} {label} coverage {fmt(carried)} is below the "
                            f"contract minimum {fmt(floor)} (short {fmt(floor - carried)})",
                        )
                    )
    return out


@check("gate_funding_confirmed")
def check_gate_funding_confirmed(ctx: Context) -> list[Finding]:
    """Funding confirmation must be recorded before the release.

    Releasing a run against unconfirmed funding is how a payment file is
    transmitted to an electronic payment provider ahead of the cash that clears
    it.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_PAYMENT_SELECTION):
        funding = _dig(doc, "funding")
        loc = ctx.loc(doc, "funding.confirmed")
        pay_date = _iso_date(doc.get("payment_date"))
        if not isinstance(funding, dict) or not _is_true(funding.get("confirmed")):
            out.append(
                Finding(
                    "gate_funding_confirmed",
                    Status.FAIL,
                    loc,
                    "funding is not confirmed for this selection; the run may not be "
                    "released",
                )
            )
            continue
        confirmed_on = _iso_date(funding.get("confirmed_on"))
        if confirmed_on is None or pay_date is None:
            out.append(
                Finding(
                    "gate_funding_confirmed",
                    Status.FAIL,
                    loc,
                    f"funding confirmation date {funding.get('confirmed_on')!r} or payment "
                    f"date {doc.get('payment_date')!r} is not an ISO date",
                )
            )
        elif confirmed_on <= pay_date:
            with amount_guard("gate_funding_confirmed", out):
                amount = _cents(doc, "funding.amount_cents", funding.get("amount_cents"))
                out.append(
                    Finding(
                        "gate_funding_confirmed",
                        Status.PASS,
                        loc,
                        f"funding of {fmt(amount)} confirmed {confirmed_on.isoformat()}, "
                        f"on or before the payment date",
                    )
                )
        else:
            out.append(
                Finding(
                    "gate_funding_confirmed",
                    Status.FAIL,
                    loc,
                    f"funding confirmed {confirmed_on.isoformat()}, after the payment date "
                    f"{pay_date.isoformat()}; the release preceded the cash",
                )
            )
    return out


@check("gate_no_duplicate")
def check_gate_no_duplicate(ctx: Context) -> list[Finding]:
    """No vendor + document number + amount may appear twice in a selection.

    The classic duplicate payment: the same invoice entered twice under two
    payment lines. It survives every approval because each line is individually
    correct.

    The key is built from the identifiers as recorded, never from a placeholder.
    Two lines that are merely *unidentified* are not evidence of a duplicate --
    collapsing them onto a shared sentinel would manufacture a hard FAIL out of
    missing data. Such a line is reported on its own, as a FLAG, and left out of
    the comparison.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_PAYMENT_SELECTION):
        seen: dict[tuple[str, str, int], str] = {}
        duplicates: list[tuple[str, str, str]] = []
        unidentifiable: list[tuple[str, str]] = []
        for payment in _rows(doc, "payments"):
            with amount_guard("gate_no_duplicate", out):
                vendor_id = _text(payment.get("vendor_id"))
                document_number = _text(payment.get("document_number"))
                amount = _cents(doc, "payments.amount_cents", payment.get("amount_cents"))
                pay_id = _label(payment, "payment_id")
                if not vendor_id or not document_number:
                    absent = ", ".join(
                        field
                        for field, value in (
                            ("vendor_id", vendor_id),
                            ("document_number", document_number),
                        )
                        if not value
                    )
                    unidentifiable.append((pay_id, absent))
                    continue
                key = (vendor_id, document_number, amount)
                if key in seen:
                    duplicates.append((seen[key], pay_id, f"{vendor_id} / {document_number}"))
                else:
                    seen[key] = pay_id
        loc = ctx.loc(doc, "payments")
        if duplicates:
            for first, second, label in duplicates:
                out.append(
                    Finding(
                        "gate_no_duplicate",
                        Status.FAIL,
                        loc,
                        f"duplicate selection: {label} appears on both {first} and "
                        f"{second} for the same amount; one of them is a second payment "
                        f"of the same obligation",
                    )
                )
        else:
            out.append(
                Finding(
                    "gate_no_duplicate",
                    Status.PASS,
                    loc,
                    f"no duplicate vendor + document + amount across {len(seen)} "
                    f"payment line(s)",
                )
            )
        for pay_id, absent in unidentifiable:
            out.append(
                Finding(
                    "gate_no_duplicate",
                    Status.FLAG,
                    loc,
                    f"payment line {pay_id} records no {absent}, so it cannot be compared "
                    f"against the other lines and was excluded from the duplicate test; "
                    f"identify the line and re-run before release",
                )
            )
    return out


@check("gate_retention_present")
def check_gate_retention_present(ctx: Context) -> list[Finding]:
    """Progress billings must carry retention and tax lines consistent with their rates.

    Retention released a period early never comes back. The engine re-derives
    both lines from the gross and the stated rates and compares with exact
    equality.
    """
    out: list[Finding] = []
    for doc, payment in _payments(ctx):
        if not _is_true(payment.get("progress_billing")):
            continue
        with amount_guard("gate_retention_present", out):
            loc = _payment_loc(ctx, doc, payment, "retention_cents")
            vendor = _label(payment, "vendor_name", "vendor_id")
            gross = _cents(doc, "payments.gross_cents", payment.get("gross_cents"))
            retention_bps = _bps(
                doc, "payments.retention_rate_bps", payment.get("retention_rate_bps")
            )
            tax_bps = _bps(doc, "payments.tax_rate_bps", payment.get("tax_rate_bps"))
            if payment.get("retention_cents") is None or payment.get("tax_cents") is None:
                out.append(
                    Finding(
                        "gate_retention_present",
                        Status.FLAG,
                        loc,
                        f"progress billing for {vendor} is missing its retention or tax "
                        f"line; the billing cannot be proved against the contract",
                    )
                )
                continue
            retention = _cents(doc, "payments.retention_cents", payment.get("retention_cents"))
            tax = _cents(doc, "payments.tax_cents", payment.get("tax_cents"))
            expected_retention = apply_rate(gross, retention_bps)
            expected_tax = apply_rate(gross - retention, tax_bps)
            issues: list[str] = []
            if retention != expected_retention:
                issues.append(
                    f"retention {fmt(retention)} does not equal {retention_bps} bps of "
                    f"gross {fmt(gross)} ({fmt(expected_retention)})"
                )
            if tax != expected_tax:
                issues.append(
                    f"tax {fmt(tax)} does not equal {tax_bps} bps of the net "
                    f"({fmt(expected_tax)})"
                )
            if issues:
                for issue in issues:
                    out.append(
                        Finding(
                            "gate_retention_present",
                            Status.FLAG,
                            loc,
                            f"progress billing for {vendor}: {issue}",
                        )
                    )
            else:
                out.append(
                    Finding(
                        "gate_retention_present",
                        Status.PASS,
                        loc,
                        f"progress billing for {vendor} carries retention {fmt(retention)} "
                        f"and tax {fmt(tax)}, both consistent with the stated rates",
                    )
                )
    return out


@check("gate_offcycle_approved")
def check_gate_offcycle_approved(ctx: Context) -> list[Finding]:
    """An off-cycle payment must carry the required approval and stay within limit.

    Off-cycle is where the standard controls are bypassed by design, so the
    compensating approval is the only control left.
    """
    out: list[Finding] = []
    for doc, payment in _payments(ctx):
        if not _is_true(payment.get("off_cycle")):
            continue
        with amount_guard("gate_offcycle_approved", out):
            loc = _payment_loc(ctx, doc, payment, "off_cycle_approval")
            vendor = _label(payment, "vendor_name", "vendor_id")
            approval = _dig(payment, "off_cycle_approval")
            amount = _cents(doc, "payments.amount_cents", payment.get("amount_cents"))
            limit = _cents(
                doc, "payments.off_cycle_limit_cents", payment.get("off_cycle_limit_cents")
            )
            is_recorded = isinstance(approval, dict)
            approver = _text(_dig(approval, "approver")) if is_recorded else ""
            approved_on = _iso_date(_dig(approval, "approved_on")) if is_recorded else None
            if not approver or approved_on is None:
                out.append(
                    Finding(
                        "gate_offcycle_approved",
                        Status.FLAG,
                        loc,
                        f"off-cycle payment of {fmt(amount)} to {vendor} carries no "
                        f"recorded approver and approval date; the compensating control "
                        f"is absent",
                    )
                )
            elif amount > limit:
                out.append(
                    Finding(
                        "gate_offcycle_approved",
                        Status.FLAG,
                        loc,
                        f"off-cycle payment of {fmt(amount)} to {vendor} exceeds the "
                        f"off-cycle limit {fmt(limit)} approved by {approver}",
                    )
                )
            else:
                out.append(
                    Finding(
                        "gate_offcycle_approved",
                        Status.PASS,
                        loc,
                        f"off-cycle payment of {fmt(amount)} to {vendor} approved by "
                        f"{approver} on {approved_on.isoformat()}, within the limit "
                        f"{fmt(limit)}",
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# 3. Routing and segregation of duties
# --------------------------------------------------------------------------- #
@check("route_every_job_mapped")
def check_route_every_job_mapped(ctx: Context) -> list[Finding]:
    """Every active job must map to exactly one existing workflow.

    A job with no workflow routes its invoices nowhere -- they sit in the
    capture system unrouted, and the period closes without them. A job with two
    workflows routes them twice.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_WORKFLOW_MATRIX):
        known = sorted(
            {_label(w, "workflow_id") for w in _rows(doc, "workflows")}
        )
        for job in _rows(doc, "jobs"):
            if not _is_true(job.get("active")):
                continue
            job_id = _label(job, "job_id")
            loc = ctx.loc(doc, f"jobs[{job_id}].workflows")
            mapped = _strs(job, "workflows")
            if len(mapped) != 1:
                out.append(
                    Finding(
                        "route_every_job_mapped",
                        Status.FAIL,
                        loc,
                        f"active job {job_id} maps to {len(mapped)} workflow(s); exactly "
                        f"one is required or its invoices route nowhere",
                    )
                )
            elif mapped[0] not in known:
                out.append(
                    Finding(
                        "route_every_job_mapped",
                        Status.FAIL,
                        loc,
                        f"active job {job_id} maps to unknown workflow {mapped[0]!r}",
                    )
                )
            else:
                out.append(
                    Finding(
                        "route_every_job_mapped",
                        Status.PASS,
                        loc,
                        f"active job {job_id} maps to workflow {mapped[0]}",
                    )
                )
    return out


@check("route_workflow_has_approver")
def check_route_workflow_has_approver(ctx: Context) -> list[Finding]:
    """Every workflow must name at least one approver.

    An empty approver list is a workflow that approves nothing and blocks
    everything, or -- worse, depending on the capture system -- approves
    everything by default.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_WORKFLOW_MATRIX):
        for workflow in _rows(doc, "workflows"):
            workflow_id = _label(workflow, "workflow_id")
            loc = ctx.loc(doc, f"workflows[{workflow_id}].approvers")
            approvers = [a for a in _strs(workflow, "approvers") if a.strip()]
            if approvers:
                out.append(
                    Finding(
                        "route_workflow_has_approver",
                        Status.PASS,
                        loc,
                        f"workflow {workflow_id} names {len(approvers)} approver(s)",
                    )
                )
            else:
                out.append(
                    Finding(
                        "route_workflow_has_approver",
                        Status.FAIL,
                        loc,
                        f"workflow {workflow_id} names no approver; every invoice routed "
                        f"to it has no reviewer",
                    )
                )
    return out


@check("route_final_review_present")
def check_route_final_review_present(ctx: Context) -> list[Finding]:
    """Every workflow must name a final-review group.

    Approval by a project reviewer is not the same control as final review by
    accounting. A workflow that ends at the project has no accounting sign-off.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_WORKFLOW_MATRIX):
        for workflow in _rows(doc, "workflows"):
            workflow_id = _label(workflow, "workflow_id")
            loc = ctx.loc(doc, f"workflows[{workflow_id}].final_review_group")
            group = _text(workflow.get("final_review_group"))
            if group:
                out.append(
                    Finding(
                        "route_final_review_present",
                        Status.PASS,
                        loc,
                        f"workflow {workflow_id} ends at final-review group {group}",
                    )
                )
            else:
                out.append(
                    Finding(
                        "route_final_review_present",
                        Status.FAIL,
                        loc,
                        f"workflow {workflow_id} names no final-review group; invoices "
                        f"routed to it reach payment without an accounting sign-off",
                    )
                )
    return out


@check("route_duties_segregated")
def check_route_duties_segregated(ctx: Context) -> list[Finding]:
    """Data-entry and final-review roles must not be the same person.

    One role-holder on both ends of the workflow can create and approve the same
    payable without a second pair of eyes anywhere in the chain.

    Segregation has to be *shown*, not inferred from silence. A workflow that
    records neither role is not segregated -- it is undocumented, and the two
    ends could well be the same person -- so it is flagged for review rather
    than passed.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_WORKFLOW_MATRIX):
        for workflow in _rows(doc, "workflows"):
            workflow_id = _label(workflow, "workflow_id")
            loc = ctx.loc(doc, f"workflows[{workflow_id}].final_review_role")
            entry = _text(workflow.get("data_entry_role"))
            review = _text(workflow.get("final_review_role"))
            if not entry or not review:
                out.append(
                    Finding(
                        "route_duties_segregated",
                        Status.FLAG,
                        loc,
                        f"workflow {workflow_id} records data entry ({entry or '-'}) and "
                        f"final review ({review or '-'}); an absent role is not evidence "
                        f"that the duties are held by different people",
                    )
                )
            elif entry == review:
                out.append(
                    Finding(
                        "route_duties_segregated",
                        Status.FAIL,
                        loc,
                        f"workflow {workflow_id} has {entry} on both data entry and final "
                        f"review; the same role-holder can create and approve a payable",
                    )
                )
            else:
                out.append(
                    Finding(
                        "route_duties_segregated",
                        Status.PASS,
                        loc,
                        f"workflow {workflow_id} separates data entry ({entry}) "
                        f"from final review ({review})",
                    )
                )
    return out


@check("route_preapproved_declared")
def check_route_preapproved_declared(ctx: Context) -> list[Finding]:
    """Direct-post workflows must be explicitly enumerated.

    A direct-post workflow skips routing entirely. That can be legitimate, but
    only when it is declared: an undeclared one is an approval bypass nobody
    signed off on.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_WORKFLOW_MATRIX):
        declared = sorted(set(_strs(doc, "preapproved_direct_post")))
        workflows = _rows(doc, "workflows")
        known = sorted({_label(w, "workflow_id") for w in workflows})
        loc = ctx.loc(doc, "preapproved_direct_post")
        issues: list[str] = []
        for workflow in workflows:
            workflow_id = _label(workflow, "workflow_id")
            if _is_true(workflow.get("direct_post")) and workflow_id not in declared:
                issues.append(
                    f"workflow {workflow_id} posts directly but is not enumerated as "
                    f"pre-approved"
                )
        for workflow_id in declared:
            if workflow_id not in known:
                issues.append(
                    f"pre-approved direct-post entry {workflow_id} matches no workflow in "
                    f"the matrix"
                )
        if issues:
            for issue in issues:
                out.append(Finding("route_preapproved_declared", Status.FLAG, loc, issue))
        else:
            out.append(
                Finding(
                    "route_preapproved_declared",
                    Status.PASS,
                    loc,
                    f"{len(declared)} direct-post workflow(s) enumerated and all reconcile "
                    f"to the matrix",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# 4. Information reporting
# --------------------------------------------------------------------------- #
@check("ir_threshold_coverage")
def check_ir_threshold_coverage(ctx: Context) -> list[Finding]:
    """Every vendor over the reporting threshold must be evaluated.

    Reporting completeness is decided a year before it is tested. A vendor that
    crossed the threshold and was never evaluated is discovered in January, when
    nothing can be done about it.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INFORMATION_REPORTING):
        threshold: int | None = None
        with amount_guard("ir_threshold_coverage", out):
            threshold = _cents(doc, "threshold_cents", doc.get("threshold_cents"))
        if threshold is None:
            # Without a threshold there is nothing to measure the register
            # against; the exception above already names the reason.
            continue
        for vendor in _rows(doc, "vendors"):
            with amount_guard("ir_threshold_coverage", out):
                vendor_id = _label(vendor, "vendor_id")
                paid = _cents(
                    doc, f"vendors[{vendor_id}].ytd_paid_cents", vendor.get("ytd_paid_cents")
                )
                if paid < threshold:
                    continue
                loc = ctx.loc(doc, f"vendors[{vendor_id}].evaluated")
                if _is_true(vendor.get("evaluated")):
                    out.append(
                        Finding(
                            "ir_threshold_coverage",
                            Status.PASS,
                            loc,
                            f"{vendor_id} paid {fmt(paid)} year to date and was evaluated "
                            f"against the {fmt(threshold)} threshold",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            "ir_threshold_coverage",
                            Status.FAIL,
                            loc,
                            f"{vendor_id} paid {fmt(paid)} year to date, over the "
                            f"{fmt(threshold)} threshold, but was never evaluated for "
                            f"reporting",
                        )
                    )
    return out


@check("ir_tin_present")
def check_ir_tin_present(ctx: Context) -> list[Finding]:
    """Each reportable vendor must have a taxpayer identification number.

    A reportable vendor with no identifier cannot be filed at all; the form is
    rejected on receipt.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INFORMATION_REPORTING):
        for vendor in _rows(doc, "vendors"):
            if not _is_true(vendor.get("reportable")):
                continue
            vendor_id = _label(vendor, "vendor_id")
            loc = ctx.loc(doc, f"vendors[{vendor_id}].tin")
            tin = _text(vendor.get("tin"))
            if tin:
                out.append(
                    Finding(
                        "ir_tin_present",
                        Status.PASS,
                        loc,
                        f"reportable vendor {vendor_id} carries a taxpayer identification "
                        f"number",
                    )
                )
            else:
                out.append(
                    Finding(
                        "ir_tin_present",
                        Status.FAIL,
                        loc,
                        f"reportable vendor {vendor_id} has no taxpayer identification "
                        f"number; the year-end form cannot be filed",
                    )
                )
    return out


@check("ir_tin_structure")
def check_ir_tin_structure(ctx: Context) -> list[Finding]:
    """A recorded identifier must be structurally valid.

    Only vendors that actually carry an identifier are examined, so a missing
    identifier is reported once, by ``ir_tin_present``, rather than twice.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INFORMATION_REPORTING):
        for vendor in _rows(doc, "vendors"):
            tin = _text(vendor.get("tin"))
            if not tin:
                continue
            vendor_id = _label(vendor, "vendor_id")
            loc = ctx.loc(doc, f"vendors[{vendor_id}].tin")
            if TIN_PATTERN.match(tin):
                out.append(
                    Finding(
                        "ir_tin_structure",
                        Status.PASS,
                        loc,
                        f"{vendor_id} identifier is structurally valid",
                    )
                )
            else:
                out.append(
                    Finding(
                        "ir_tin_structure",
                        Status.FLAG,
                        loc,
                        f"{vendor_id} identifier {tin!r} does not match the expected "
                        f"structure; the filing will be rejected on validation",
                    )
                )
    return out


@check("ir_no_split_vendor")
def check_ir_no_split_vendor(ctx: Context) -> list[Finding]:
    """No two vendor records may share one identifier.

    Two records behind one identifier split a vendor's year-to-date across both,
    so each half can sit under the threshold while the vendor as a whole is well
    over it. That is the split-payment failure mode.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INFORMATION_REPORTING):
        by_tin: dict[str, list[str]] = {}
        for vendor in _rows(doc, "vendors"):
            tin = _text(vendor.get("tin"))
            if not tin:
                continue
            by_tin.setdefault(tin, []).append(_label(vendor, "vendor_id"))
        loc = ctx.loc(doc, "vendors")
        shared = sorted((tin, ids) for tin, ids in by_tin.items() if len(ids) > 1)
        if shared:
            for tin, ids in shared:
                out.append(
                    Finding(
                        "ir_no_split_vendor",
                        Status.FLAG,
                        loc,
                        f"vendor records {', '.join(sorted(ids))} share identifier {tin}; "
                        f"year-to-date payments are split across them and each half may "
                        f"sit under the reporting threshold",
                    )
                )
        else:
            out.append(
                Finding(
                    "ir_no_split_vendor",
                    Status.PASS,
                    loc,
                    f"{len(by_tin)} identifier(s) are unique across the vendor register",
                )
            )
    return out


@check("ir_filed_reconciles")
def check_ir_filed_reconciles(ctx: Context) -> list[Finding]:
    """Filed-form count per entity must reconcile to the expected list.

    The expected list is derived from the register itself, so the control is a
    tie-out rather than a restatement of the same number.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_INFORMATION_REPORTING):
        expected: dict[str, int] = {}
        unfiled: list[str] = []
        for vendor in _rows(doc, "vendors"):
            if not _is_true(vendor.get("reportable")):
                continue
            entity = _label(vendor, "entity")
            if _is_true(vendor.get("form_filed")):
                expected[entity] = expected.get(entity, 0) + 1
            else:
                unfiled.append(_label(vendor, "vendor_id"))
        reported = _dig(doc, "filed_counts")
        reported_map = reported if isinstance(reported, dict) else {}
        entities = sorted(set(expected) | {str(k) for k in reported_map})
        for entity in entities:
            with amount_guard("ir_filed_reconciles", out):
                loc = ctx.loc(doc, f"filed_counts[{entity}]")
                want = expected.get(entity, 0)
                got = _count(doc, f"filed_counts.{entity}", reported_map.get(entity, 0))
                if got == want:
                    out.append(
                        Finding(
                            "ir_filed_reconciles",
                            Status.PASS,
                            loc,
                            f"{entity} filed {got} form(s), reconciling to the expected "
                            f"list",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            "ir_filed_reconciles",
                            Status.FAIL,
                            loc,
                            f"{entity} reports {got} filed form(s) but the register expects "
                            f"{want}; the difference is {want - got} unaccounted vendor(s)",
                        )
                    )
        if unfiled:
            out.append(
                Finding(
                    "ir_filed_reconciles",
                    Status.FAIL,
                    ctx.loc(doc, "vendors"),
                    f"reportable vendor(s) {', '.join(sorted(unfiled))} have no filed form",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# 5. Commitment hygiene
# --------------------------------------------------------------------------- #
@check("cmt_sov_not_lump_sum")
def check_cmt_sov_not_lump_sum(ctx: Context) -> list[Finding]:
    """A subcontract schedule of values must mirror the contract, not one lump line.

    A single lump line makes every progress billing unverifiable: there is
    nothing to bill against, so percent-complete becomes an assertion. The
    schedule must also foot to the commitment amount, exactly.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_COMMITMENT_REGISTER):
        for commitment in _rows(doc, "commitments"):
            with amount_guard("cmt_sov_not_lump_sum", out):
                commitment_id = _label(commitment, "commitment_id")
                loc = ctx.loc(doc, f"commitments[{commitment_id}].schedule_of_values")
                sov = _rows(commitment, "schedule_of_values")
                amount = _cents(
                    doc,
                    f"commitments[{commitment_id}].amount_cents",
                    commitment.get("amount_cents"),
                )
                sov_total = total(
                    _cents(
                        doc,
                        f"commitments[{commitment_id}].schedule_of_values.amount_cents",
                        line.get("amount_cents"),
                    )
                    for line in sov
                )
                contract_type = _text(commitment.get("contract_type"))
                if contract_type in DETAILED_CONTRACT_TYPES and len(sov) < 2:
                    out.append(
                        Finding(
                            "cmt_sov_not_lump_sum",
                            Status.FAIL,
                            loc,
                            f"{contract_type} {commitment_id} carries {len(sov)} schedule-"
                            f"of-values line(s); a lump-sum schedule leaves progress "
                            f"billings with nothing to bill against",
                        )
                    )
                elif sov_total != amount:
                    out.append(
                        Finding(
                            "cmt_sov_not_lump_sum",
                            Status.FAIL,
                            loc,
                            f"{commitment_id} schedule of values foots to {fmt(sov_total)} "
                            f"but the commitment is {fmt(amount)} (difference "
                            f"{fmt(sov_total - amount)})",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            "cmt_sov_not_lump_sum",
                            Status.PASS,
                            loc,
                            f"{commitment_id} carries {len(sov)} schedule-of-values line(s) "
                            f"footing to {fmt(amount)}",
                        )
                    )
    return out


@check("cmt_id_convention")
def check_cmt_id_convention(ctx: Context) -> list[Finding]:
    """Commitment identifiers must follow the project/vendor convention.

    The convention is what lets a commitment, its change orders and its billings
    be found together a year later. Off-convention identifiers are the ones that
    go missing at close-out.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_COMMITMENT_REGISTER):
        for commitment in _rows(doc, "commitments"):
            commitment_id = _label(commitment, "commitment_id")
            job_id = _label(commitment, "job_id")
            vendor_id = _label(commitment, "vendor_id")
            loc = ctx.loc(doc, f"commitments[{commitment_id}].commitment_id")
            stem = f"{job_id}-{vendor_id}-"
            suffix = commitment_id[len(stem):] if commitment_id.startswith(stem) else ""
            if suffix and COMMITMENT_SUFFIX_PATTERN.match(suffix):
                out.append(
                    Finding(
                        "cmt_id_convention",
                        Status.PASS,
                        loc,
                        f"{commitment_id} follows the <job>-<vendor>-<nn> convention",
                    )
                )
            else:
                out.append(
                    Finding(
                        "cmt_id_convention",
                        Status.FLAG,
                        loc,
                        f"{commitment_id} does not follow the <job>-<vendor>-<nn> "
                        f"convention (expected the stem {stem!r}); it will not be found "
                        f"with its job at close-out",
                    )
                )
    return out


@check("cmt_co_attaches_to_original")
def check_cmt_co_attaches_to_original(ctx: Context) -> list[Finding]:
    """Change orders must attach to the original commitment.

    A detached change order inflates nothing and reduces nothing: the commitment
    reports its original value while the obligation has moved.
    """
    out: list[Finding] = []
    for doc in ctx.docs(DOC_COMMITMENT_REGISTER):
        commitments = _rows(doc, "commitments")
        known = sorted({_label(c, "commitment_id") for c in commitments})
        for commitment in commitments:
            commitment_id = _label(commitment, "commitment_id")
            for change_order in _rows(commitment, "change_orders"):
                change_id = _label(change_order, "change_order_id")
                loc = ctx.loc(
                    doc, f"commitments[{commitment_id}].change_orders[{change_id}]"
                )
                original = _text(change_order.get("original_commitment_id"))
                if original == commitment_id:
                    out.append(
                        Finding(
                            "cmt_co_attaches_to_original",
                            Status.PASS,
                            loc,
                            f"change order {change_id} attaches to {commitment_id}",
                        )
                    )
                elif original in known:
                    out.append(
                        Finding(
                            "cmt_co_attaches_to_original",
                            Status.FLAG,
                            loc,
                            f"change order {change_id} is filed under {commitment_id} but "
                            f"attaches to {original}",
                        )
                    )
                else:
                    out.append(
                        Finding(
                            "cmt_co_attaches_to_original",
                            Status.FLAG,
                            loc,
                            f"change order {change_id} attaches to {original!r}, which is "
                            f"not a commitment in this register; the obligation is not "
                            f"reflected on any commitment",
                        )
                    )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def load_context(path: Path | str) -> Context:
    """Parse one posting document set into a :class:`Context` (read-only).

    Raises:
        ValueError: If the payload is not a JSON object. Substituting an empty
            mapping would hand every check an empty context, and the run would
            report PASS over a file it never understood. The error travels the
            same path as malformed JSON and exits 3.
    """
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"{path.name}: a posting document set must be a JSON object, got "
            f"{type(data).__name__}"
        )
    return Context(path=path, data=data)


def analyze_document(path: Path | str) -> DocumentReport:
    """Run the full :data:`REGISTRY` over a single document set (read-only).

    Parameters
    ----------
    path:
        Path to a ``.json`` posting document set.

    Returns
    -------
    DocumentReport
        All findings, in registry order, plus a rolled-up :class:`Verdict`.
    """
    path = Path(path)
    ctx = load_context(path)
    report = DocumentReport(document=path.name)
    for _rule_id, fn in REGISTRY:
        report.findings.extend(fn(ctx))
    return report


def analyze_folder(folder: Path | str) -> list[DocumentReport]:
    """Analyze every ``.json`` document set in ``folder`` (non-recursive)."""
    folder = Path(folder)
    reports: list[DocumentReport] = []
    for path in sorted(folder.glob("*.json"), key=lambda p: p.name):
        if path.name.startswith("~$"):  # skip lock files
            continue
        reports.append(analyze_document(path))
    return reports


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of document reports into one overall verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
