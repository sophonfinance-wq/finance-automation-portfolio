"""
Certificate-of-insurance (COI) compliance control engine (READ-ONLY).
=====================================================================

Loads each compliance file (a ``.json`` file produced by
:mod:`coi_engine.generate`) and runs an ordered *registry* of independent
controls over it.

Scope
-----
This engine is about **whether the paper in the file satisfies the contract**,
not where an insurance cost lands. Premium allocation across projects is a
separate engine's job, and that engine explicitly declines to check a
certificate. This engine is that check.

The shape of the problem
------------------------
A developer requires every consultant, general contractor and subcontractor it
hires to carry insurance per contract, and it has to prove, party by party, that
each one's certificate of insurance is on file, unexpired, and meets the
required limits and endorsements for that party type.

Three failures hide inside that, and none of them look wrong in a folder of
one-page certificates: the certificate that lapsed while the file still shows one
(or the single uninsured day between two renewals); the certificate that is
current but short of the required limit or missing the endorsement the contract
demanded; and the monthly rollup that calls a party compliant on a determination
nobody recomputed from the certificates underneath it.

The registry is organised around that:

1. ``set_``   -- is the compliance file complete?
2. ``party_`` -- is the party register sound, and is each party's requirement known?
3. ``cert_``  -- is every certificate well-formed and attributable?
4. ``cov_``   -- is each required coverage present, adequate, and free of any gap?
5. ``end_``   -- are the endorsements the matrix requires actually on the certificate?
6. ``exp_``   -- is the coverage in force now, and what is due to renew?
7. ``rpt_``   -- does the rollup recompute from the certificates it summarises?

Design notes
------------
- **Strictly read-only.** Compliance files are parsed and never written back.
- **Deterministic.** Same inputs, same findings, in the same order.
- **Integer cents, no tolerance.** Every limit is compared with exact ``>=``.
- **One compliance predicate.** Controls and the generator share the kernel in
  :mod:`coi_engine.compliance`, so a determination cannot disagree with the data
  that produced it.
- **Absent evidence is not a passing control.** ``set_complete`` runs first.
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

from .compliance import (
    Coverage,
    Requirement,
    coverage_satisfies,
    within_renewal_window,
)
from .model import (
    COVERAGE_TYPES,
    COVERAGE_WORKERS_COMP,
    DOC_CERTIFICATE_REGISTER,
    DOC_COMPLIANCE_REPORT,
    DOC_COVERAGE_SUMMARY,
    DOC_PARTY_REGISTER,
    DOC_RENEWAL_WATCHLIST,
    DOC_REQUIREMENT_MATRIX,
    DOC_TYPES,
    PARTY_TYPES,
    Context,
    DocumentReport,
    Finding,
    Status,
    Verdict,
)
from .money import AmountInvalidError, fmt, require_cents

CheckFn = Callable[[Context], list[Finding]]

#: Ordered registry of ``(rule_id, check_fn)`` pairs.
REGISTRY: list[tuple[str, CheckFn]] = []

#: Declared severity of every rule.
SEVERITY: dict[str, Status] = {}


def amount_invalid_finding(rule_id: str, exc: AmountInvalidError) -> Finding:
    """Render an :class:`~coi_engine.money.AmountInvalidError` as a finding."""
    return Finding(
        rule_id,
        SEVERITY.get(rule_id, Status.FAIL),
        f"amount:{exc.field}",
        f"{exc} -- amounts are integer cents and are never coerced",
    )


@contextlib.contextmanager
def amount_guard(rule_id: str, out: list[Finding]) -> Iterator[None]:
    """Contain a malformed amount to the one row being read."""
    try:
        yield
    except AmountInvalidError as exc:
        out.append(amount_invalid_finding(rule_id, exc))


def check(rule_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register ``fn`` in :data:`REGISTRY` under ``rule_id``."""

    def wrapper(fn: CheckFn) -> CheckFn:
        @functools.wraps(fn)
        def guarded(ctx: Context) -> list[Finding]:
            try:
                return fn(ctx)
            except AmountInvalidError as exc:
                return [amount_invalid_finding(rule_id, exc)]

        REGISTRY.append((rule_id, guarded))
        return guarded

    return wrapper


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sev(rule_id: str, status: Status) -> Status:
    SEVERITY[rule_id] = status
    return status


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _rows(doc: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    rows = doc.get(key)
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) and value else None


def _int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# --------------------------------------------------------------------------- #
# Compliance-file helpers
# --------------------------------------------------------------------------- #
def _parties(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_PARTY_REGISTER), "parties")


def _party_id(row: dict[str, Any]) -> str:
    value = row.get("party_id")
    return value if isinstance(value, str) and value else "?"


def _party_map(ctx: Context) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _parties(ctx):
        pid = _party_id(row)
        if pid != "?" and pid not in out:
            out[pid] = row
    return out


def _required_coverages(party: dict[str, Any]) -> list[str]:
    value = party.get("required_coverages")
    if not isinstance(value, list):
        return []
    return [c for c in value if isinstance(c, str)]


def _requirements(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_REQUIREMENT_MATRIX), "requirements")


def _matrix(ctx: Context) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _requirements(ctx):
        ptype = _text(row, "party_type")
        cov = _text(row, "coverage_type")
        if ptype and cov and (ptype, cov) not in out:
            out[(ptype, cov)] = row
    return out


def _certs(ctx: Context) -> list[dict[str, Any]]:
    return _rows(ctx.one(DOC_CERTIFICATE_REGISTER), "certificates")


def _cert_id(row: dict[str, Any]) -> str:
    value = row.get("certificate_id")
    return value if isinstance(value, str) and value else "?"


def _certs_for(ctx: Context, party_id: str, coverage_type: str) -> list[dict[str, Any]]:
    return [
        c
        for c in _certs(ctx)
        if _text(c, "party_id") == party_id and _text(c, "coverage_type") == coverage_type
    ]


def _governing_cert(
    ctx: Context, party_id: str, coverage_type: str
) -> dict[str, Any] | None:
    """The certificate whose term reaches furthest forward, or ``None``.

    Selection reads only the expiration date and the certificate id, never an
    amount, so choosing the governing certificate cannot itself raise on a
    malformed limit -- the limit is read later, by the control that needs it.
    """
    dated: list[tuple[date, str, dict[str, Any]]] = []
    for cert in _certs_for(ctx, party_id, coverage_type):
        expiration = _parse_date(cert.get("expiration_date"))
        if expiration is not None:
            dated.append((expiration, _cert_id(cert), cert))
    if not dated:
        return None
    dated.sort(key=lambda t: (t[0], t[1]))
    return dated[-1][2]


def _requirement_from_row(row: dict[str, Any]) -> Requirement:
    """Read a matrix row into a :class:`~coi_engine.compliance.Requirement`.

    Raises :class:`AmountInvalidError` if either limit is not integer cents.
    """
    return Requirement(
        per_occurrence_cents=require_cents(
            "requirement.required_per_occurrence_cents",
            row.get("required_per_occurrence_cents"),
        ),
        aggregate_cents=require_cents(
            "requirement.required_aggregate_cents", row.get("required_aggregate_cents")
        ),
        requires_additional_insured=bool(row.get("requires_additional_insured")),
        requires_waiver_of_subrogation=bool(row.get("requires_waiver_of_subrogation")),
    )


def _coverage_from_cert(cert: dict[str, Any], expiration: date) -> Coverage:
    """Read a certificate into a :class:`~coi_engine.compliance.Coverage`.

    Raises :class:`AmountInvalidError` if either limit is not integer cents.
    """
    return Coverage(
        per_occurrence_cents=require_cents(
            f"certificate[{_cert_id(cert)}].per_occurrence_cents",
            cert.get("per_occurrence_cents"),
        ),
        aggregate_cents=require_cents(
            f"certificate[{_cert_id(cert)}].aggregate_cents", cert.get("aggregate_cents")
        ),
        additional_insured=bool(cert.get("additional_insured")),
        waiver_of_subrogation=bool(cert.get("waiver_of_subrogation")),
        expiration=expiration,
    )


def recompute_party_compliant(
    ctx: Context,
    party: dict[str, Any],
    matrix: dict[tuple[str, str], dict[str, Any]],
    as_of: date,
) -> bool:
    """Recompute a party's compliant determination from the certificates.

    A party is compliant when every coverage its contract requires has a
    governing certificate that is unexpired at ``as_of`` and, where the matrix
    carries a row for it, meets the required limits and endorsements. Shared with
    the generator through :mod:`coi_engine.compliance`, so the determination the
    engine recomputes is the one that produced the data.

    Raises :class:`AmountInvalidError` if a limit it must read is not integer
    cents; the calling control contains that to the party being read.
    """
    ptype = _text(party, "party_type")
    pid = _party_id(party)
    for cov in _required_coverages(party):
        gov = _governing_cert(ctx, pid, cov)
        if gov is None:
            return False
        expiration = _parse_date(gov.get("expiration_date"))
        if expiration is None:
            return False
        coverage = _coverage_from_cert(gov, expiration)
        row = matrix.get((ptype or "", cov))
        requirement = _requirement_from_row(row) if row is not None else None
        if not coverage_satisfies(coverage, requirement, as_of):
            return False
    return True


def recompute_watchlist(ctx: Context, as_of: date, lead_days: int) -> list[dict[str, Any]]:
    """The renewal watchlist re-derived from the certificate evidence.

    One entry per governing certificate of a required coverage whose term ends
    inside the lead-time window. Shared with the generator so the stated watchlist
    can be tied to it. Reads no amounts, so it never raises on a malformed limit.
    """
    entries: list[dict[str, Any]] = []
    for party in _parties(ctx):
        pid = _party_id(party)
        for cov in _required_coverages(party):
            if cov not in COVERAGE_TYPES:
                continue
            gov = _governing_cert(ctx, pid, cov)
            if gov is None:
                continue
            expiration = _parse_date(gov.get("expiration_date"))
            if expiration is None:
                continue
            if within_renewal_window(expiration, as_of, lead_days):
                entries.append(
                    {
                        "certificate_id": _cert_id(gov),
                        "party_id": pid,
                        "coverage_type": cov,
                        "expiration_date": gov.get("expiration_date"),
                        "days_remaining": (expiration - as_of).days,
                    }
                )
    entries.sort(
        key=lambda e: (e["certificate_id"], e["party_id"], e["coverage_type"])
    )
    return entries


def _normalize_entry(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("certificate_id"),
        entry.get("party_id"),
        entry.get("coverage_type"),
        entry.get("expiration_date"),
        entry.get("days_remaining"),
    )


# --------------------------------------------------------------------------- #
# set_ -- structural precondition
# --------------------------------------------------------------------------- #
@check("set_complete")
def check_set_complete(ctx: Context) -> list[Finding]:
    """Every artifact the compliance file depends on is present, exactly once.

    This runs first and deliberately owns the "missing artifact" finding. A
    control that silently passes because its input is absent is worse than no
    control: it reports assurance it never performed.
    """
    rule = "set_complete"
    _sev(rule, Status.FAIL)
    out: list[Finding] = []
    for doc_type in DOC_TYPES:
        found = ctx.docs(doc_type)
        if not found:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"{doc_type} is missing; the controls that read it cannot run and "
                    f"must not be reported as having passed",
                )
            )
        elif len(found) > 1:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    f"{doc_type}:-",
                    f"{len(found)} {doc_type} documents present; the compliance file "
                    f"carries exactly one of each",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(DOC_TYPES)} compliance artifacts are present",
            )
        )
    if _parse_date(ctx.as_of) is None:
        out.append(
            Finding(
                rule,
                Status.FAIL,
                "-",
                f"as_of {ctx.as_of!r} is not a readable date; every expiry and renewal "
                f"test is measured to it",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# party_ -- the party register and each party's requirement
# --------------------------------------------------------------------------- #
@check("party_unique_ids")
def check_party_unique_ids(ctx: Context) -> list[Finding]:
    """No party id appears twice.

    The party id joins the register to every certificate and to the coverage
    summary. A duplicate makes a certificate ambiguous about whom it insures.
    """
    rule = "party_unique_ids"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARTY_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _parties(ctx):
        seen[_party_id(row)] = seen.get(_party_id(row), 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"parties/{pid}"),
            f"party id {pid} appears {count} times; a certificate that names it cannot "
            f"be attributed to one party",
        )
        for pid, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {len(seen)} party ids are unique")
        )
    return out


@check("party_type_valid")
def check_party_type_valid(ctx: Context) -> list[Finding]:
    """Every party carries a known party type.

    The party type is the key into the requirement matrix; an unknown one has no
    row, so nothing downstream could say what that party was required to carry.
    """
    rule = "party_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARTY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _parties(ctx):
        ptype = _text(row, "party_type")
        if ptype not in PARTY_TYPES:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parties/{_party_id(row)}/party_type"),
                    f"party {_party_id(row)} is typed {ptype!r}, which is not one of "
                    f"{PARTY_TYPES}; its requirement cannot be looked up",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(_parties(ctx))} parties carry a known type"
            )
        )
    return out


@check("party_coverage_declared")
def check_party_coverage_declared(ctx: Context) -> list[Finding]:
    """Every party declares a non-empty, known contract-required coverage set.

    An empty set is not a compliant party; it is a party whose contract terms were
    never captured, so every coverage control below would have nothing to check
    and pass vacuously.
    """
    rule = "party_coverage_declared"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_PARTY_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    for row in _parties(ctx):
        pid = _party_id(row)
        declared = row.get("required_coverages")
        if not isinstance(declared, list) or not _required_coverages(row):
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parties/{pid}/required_coverages"),
                    f"party {pid} declares no contract-required coverage; its coverage "
                    f"controls would pass on an empty requirement",
                )
            )
            continue
        unknown = [c for c in _required_coverages(row) if c not in COVERAGE_TYPES]
        if unknown:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"parties/{pid}/required_coverages"),
                    f"party {pid} requires {unknown}, which is not among the known "
                    f"coverage lines {COVERAGE_TYPES}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_parties(ctx))} parties declare a known required-coverage set",
            )
        )
    return out


@check("party_matrix_defined")
def check_party_matrix_defined(ctx: Context) -> list[Finding]:
    """Every coverage a party requires has a requirement-matrix row for its type.

    Without the row the engine knows the party must carry a line but not what
    limit or endorsement to hold it to, so the adequacy controls would silently
    skip it. Parties whose type is itself unknown are left to ``party_type_valid``.
    """
    rule = "party_matrix_defined"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_REQUIREMENT_MATRIX)
    if register is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        ptype = _text(party, "party_type")
        if ptype not in PARTY_TYPES:
            continue  # party_type_valid owns this
        for cov in _required_coverages(party):
            if cov not in COVERAGE_TYPES:
                continue  # party_coverage_declared owns this
            checked += 1
            if (ptype, cov) not in matrix:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"requirements/{ptype}/{cov}"),
                        f"the requirement matrix has no row for {ptype}/{cov}, which party "
                        f"{_party_id(party)} must carry; its limit cannot be tested",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} required coverages have a matrix row"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# cert_ -- the certificate register
# --------------------------------------------------------------------------- #
@check("cert_required_fields")
def check_cert_required_fields(ctx: Context) -> list[Finding]:
    """Every certificate carries the descriptive fields the controls read."""
    rule = "cert_required_fields"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CERTIFICATE_REGISTER)
    if register is None:
        return []
    required = (
        "certificate_id",
        "party_id",
        "carrier",
        "policy_no",
        "coverage_type",
        "inception_date",
        "expiration_date",
    )
    out: list[Finding] = []
    for row in _certs(ctx):
        missing = [f for f in required if not _text(row, f)]
        if missing:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"certificates/{_cert_id(row)}"),
                    f"certificate {_cert_id(row)} is missing {', '.join(missing)}",
                )
            )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_certs(ctx))} certificates carry their required fields",
            )
        )
    return out


@check("cert_policy_no_unique")
def check_cert_policy_no_unique(ctx: Context) -> list[Finding]:
    """No policy number appears on two certificates.

    A shared policy number means one policy was photocopied onto two lines or two
    parties, and the register can no longer prove they are distinct coverages.
    """
    rule = "cert_policy_no_unique"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CERTIFICATE_REGISTER)
    if register is None:
        return []
    seen: dict[str, int] = {}
    for row in _certs(ctx):
        policy = _text(row, "policy_no")
        if policy:
            seen[policy] = seen.get(policy, 0) + 1
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"certificates/policy_no/{policy}"),
            f"policy number {policy} appears on {count} certificates; they cannot both "
            f"be independent evidence of coverage",
        )
        for policy, count in seen.items()
        if count > 1
    ]
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {len(seen)} certificate policy numbers are unique"
            )
        )
    return out


@check("cert_term_runs_forward")
def check_cert_term_runs_forward(ctx: Context) -> list[Finding]:
    """A certificate's term runs forwards.

    An inverted term makes every date test on it meaningless: the days-remaining
    figure it produces is negative and the coverage it appears to prove never
    existed.
    """
    rule = "cert_term_runs_forward"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CERTIFICATE_REGISTER)
    if register is None:
        return []
    out: list[Finding] = []
    checked = 0
    for row in _certs(ctx):
        inception = _parse_date(row.get("inception_date"))
        expiration = _parse_date(row.get("expiration_date"))
        if inception is None or expiration is None:
            continue
        checked += 1
        if inception >= expiration:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(register, f"certificates/{_cert_id(row)}/inception_date"),
                    f"certificate {_cert_id(row)} incepts {inception.isoformat()} and "
                    f"expires {expiration.isoformat()}; the term does not run forwards",
                )
            )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} certificate terms run forwards")
        )
    return out


@check("cert_party_exists")
def check_cert_party_exists(ctx: Context) -> list[Finding]:
    """Every certificate names a party in the register."""
    rule = "cert_party_exists"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CERTIFICATE_REGISTER)
    if register is None:
        return []
    parties = _party_map(ctx)
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"certificates/{_cert_id(row)}/party_id"),
            f"certificate {_cert_id(row)} names party {_text(row, 'party_id')!r}, which "
            f"is not in the party register",
        )
        for row in _certs(ctx)
        if _text(row, "party_id") and _text(row, "party_id") not in parties
    ]
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", "every certificate names a party in the register")
        )
    return out


# --------------------------------------------------------------------------- #
# cov_ -- the required coverage, present and adequate
# --------------------------------------------------------------------------- #
@check("cov_coverage_type_valid")
def check_cov_coverage_type_valid(ctx: Context) -> list[Finding]:
    """Every certificate attests a known coverage line.

    An unknown line cannot be matched to a requirement, so a certificate carrying
    one satisfies nothing while looking like evidence of something.
    """
    rule = "cov_coverage_type_valid"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CERTIFICATE_REGISTER)
    if register is None:
        return []
    out = [
        Finding(
            rule,
            Status.FAIL,
            ctx.loc(register, f"certificates/{_cert_id(row)}/coverage_type"),
            f"certificate {_cert_id(row)} attests coverage {_text(row, 'coverage_type')!r}, "
            f"which is not a known coverage line",
        )
        for row in _certs(ctx)
        if _text(row, "coverage_type") and _text(row, "coverage_type") not in COVERAGE_TYPES
    ]
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {len(_certs(ctx))} certificates attest a known coverage line",
            )
        )
    return out


@check("cov_required_present")
def check_cov_required_present(ctx: Context) -> list[Finding]:
    """Every coverage a party is required to carry has a certificate on file.

    Presence, not currency: a required line with no certificate at all is the
    plainest failure, and expiry is a separate control's job.
    """
    rule = "cov_required_present"
    _sev(rule, Status.FAIL)
    party_reg = ctx.one(DOC_PARTY_REGISTER)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    if party_reg is None or cert_reg is None:
        return []
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        pid = _party_id(party)
        for cov in _required_coverages(party):
            if cov not in COVERAGE_TYPES:
                continue  # party_coverage_declared owns this
            checked += 1
            if not _certs_for(ctx, pid, cov):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(cert_reg, f"certificates/{pid}/{cov}"),
                        f"party {pid} is required to carry {cov} but has no certificate on "
                        f"file for it",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} required coverages have a certificate on file",
            )
        )
    return out


@check("cov_per_occurrence_meets")
def check_cov_per_occurrence_meets(ctx: Context) -> list[Finding]:
    """The governing certificate's per-occurrence limit meets the requirement.

    Compared with exact ``>=``: a limit a cent short of the contract requirement
    is a limit short of the contract requirement.
    """
    rule = "cov_per_occurrence_meets"
    _sev(rule, Status.FAIL)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    if cert_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        ptype = _text(party, "party_type")
        pid = _party_id(party)
        for cov in _required_coverages(party):
            row = matrix.get((ptype or "", cov))
            if row is None:
                continue  # party_matrix_defined owns this
            gov = _governing_cert(ctx, pid, cov)
            if gov is None:
                continue  # cov_required_present owns this
            with amount_guard(rule, out):
                per_occurrence = require_cents(
                    f"certificate[{_cert_id(gov)}].per_occurrence_cents",
                    gov.get("per_occurrence_cents"),
                )
                required = require_cents(
                    f"requirement[{ptype}/{cov}].required_per_occurrence_cents",
                    row.get("required_per_occurrence_cents"),
                )
                checked += 1
                if per_occurrence < required:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(cert_reg, f"certificates/{_cert_id(gov)}/per_occurrence_cents"),
                            f"party {pid} carries {fmt(per_occurrence)} per-occurrence on "
                            f"{cov}; the contract requires {fmt(required)} "
                            f"(short {fmt(required - per_occurrence)})",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} per-occurrence limits meet the requirement"
            )
        )
    return out


@check("cov_aggregate_meets")
def check_cov_aggregate_meets(ctx: Context) -> list[Finding]:
    """The governing certificate's aggregate limit meets the requirement.

    The aggregate is what is left after earlier claims in the period; a shortfall
    here is coverage that runs out before the job does, invisible until it does.
    """
    rule = "cov_aggregate_meets"
    _sev(rule, Status.FAIL)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    if cert_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        ptype = _text(party, "party_type")
        pid = _party_id(party)
        for cov in _required_coverages(party):
            row = matrix.get((ptype or "", cov))
            if row is None:
                continue  # party_matrix_defined owns this
            gov = _governing_cert(ctx, pid, cov)
            if gov is None:
                continue  # cov_required_present owns this
            with amount_guard(rule, out):
                aggregate = require_cents(
                    f"certificate[{_cert_id(gov)}].aggregate_cents", gov.get("aggregate_cents")
                )
                required = require_cents(
                    f"requirement[{ptype}/{cov}].required_aggregate_cents",
                    row.get("required_aggregate_cents"),
                )
                checked += 1
                if aggregate < required:
                    out.append(
                        Finding(
                            rule,
                            Status.FAIL,
                            ctx.loc(cert_reg, f"certificates/{_cert_id(gov)}/aggregate_cents"),
                            f"party {pid} carries {fmt(aggregate)} aggregate on {cov}; the "
                            f"contract requires {fmt(required)} "
                            f"(short {fmt(required - aggregate)})",
                        )
                    )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} aggregate limits meet the requirement"
            )
        )
    return out


@check("cov_no_uninsured_gap")
def check_cov_no_uninsured_gap(ctx: Context) -> list[Finding]:
    """Successive certificates of one coverage leave no uninsured day.

    Both certificates look valid on their own; the gap exists only *between* a
    lapse and the renewal that follows it, and an occurrence lands in it with
    nothing to respond.
    """
    rule = "cov_no_uninsured_gap"
    _sev(rule, Status.FAIL)
    register = ctx.one(DOC_CERTIFICATE_REGISTER)
    if register is None:
        return []
    groups: dict[tuple[str, str], list[tuple[date, date, dict[str, Any]]]] = {}
    for cert in _certs(ctx):
        pid = _text(cert, "party_id")
        cov = _text(cert, "coverage_type")
        inception = _parse_date(cert.get("inception_date"))
        expiration = _parse_date(cert.get("expiration_date"))
        if pid and cov and inception and expiration:
            groups.setdefault((pid, cov), []).append((inception, expiration, cert))
    out: list[Finding] = []
    checked = 0
    for (pid, cov), rows in sorted(groups.items()):
        ordered = sorted(rows, key=lambda t: (t[0], t[1], _cert_id(t[2])))
        for (_p_inc, prior_end, prior), (next_start, _n_exp, following) in zip(
            ordered, ordered[1:]
        ):
            checked += 1
            if next_start > prior_end:
                gap = (next_start - prior_end).days
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(register, f"certificates/{_cert_id(following)}/inception_date"),
                        f"party {pid} {cov} expires {prior_end.isoformat()} on "
                        f"{_cert_id(prior)} and does not resume until "
                        f"{next_start.isoformat()} on {_cert_id(following)}, leaving "
                        f"{gap} uninsured day(s)",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} renewal handovers leave no uninsured day"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# end_ -- required endorsements
# --------------------------------------------------------------------------- #
@check("end_additional_insured_present")
def check_end_additional_insured_present(ctx: Context) -> list[Finding]:
    """Where the matrix requires it, the governing certificate names the developer
    an additional insured.

    Without the endorsement the developer is not a beneficiary of the party's
    policy at all; the certificate proves the party is covered and the developer
    is not.
    """
    rule = "end_additional_insured_present"
    _sev(rule, Status.FAIL)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    if cert_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        ptype = _text(party, "party_type")
        pid = _party_id(party)
        for cov in _required_coverages(party):
            row = matrix.get((ptype or "", cov))
            if row is None or not bool(row.get("requires_additional_insured")):
                continue
            gov = _governing_cert(ctx, pid, cov)
            if gov is None:
                continue  # cov_required_present owns this
            checked += 1
            if not bool(gov.get("additional_insured")):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(cert_reg, f"certificates/{_cert_id(gov)}/additional_insured"),
                        f"party {pid} {cov} certificate {_cert_id(gov)} does not carry the "
                        f"additional-insured endorsement the contract requires",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} required additional-insured endorsements are present",
            )
        )
    return out


@check("end_waiver_of_subrogation_present")
def check_end_waiver_of_subrogation_present(ctx: Context) -> list[Finding]:
    """Where the matrix requires it, the governing certificate carries a waiver of
    subrogation.

    Without the waiver the party's carrier can pay a loss and then recover it from
    the developer, unwinding the risk transfer the contract was written to make.
    """
    rule = "end_waiver_of_subrogation_present"
    _sev(rule, Status.FAIL)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    if cert_reg is None:
        return []
    matrix = _matrix(ctx)
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        ptype = _text(party, "party_type")
        pid = _party_id(party)
        for cov in _required_coverages(party):
            row = matrix.get((ptype or "", cov))
            if row is None or not bool(row.get("requires_waiver_of_subrogation")):
                continue
            gov = _governing_cert(ctx, pid, cov)
            if gov is None:
                continue  # cov_required_present owns this
            checked += 1
            if not bool(gov.get("waiver_of_subrogation")):
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(cert_reg, f"certificates/{_cert_id(gov)}/waiver_of_subrogation"),
                        f"party {pid} {cov} certificate {_cert_id(gov)} does not carry the "
                        f"waiver-of-subrogation endorsement the contract requires",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} required waiver-of-subrogation endorsements are present",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# exp_ -- currency and renewal
# --------------------------------------------------------------------------- #
@check("exp_not_expired")
def check_exp_not_expired(ctx: Context) -> list[Finding]:
    """The governing certificate for each required coverage is in force at as_of.

    A certificate expired on or before the review date is not coverage; the file
    still shows a certificate, just a lapsed one.
    """
    rule = "exp_not_expired"
    _sev(rule, Status.FAIL)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if cert_reg is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        pid = _party_id(party)
        for cov in _required_coverages(party):
            if cov not in COVERAGE_TYPES:
                continue  # party_coverage_declared owns this
            gov = _governing_cert(ctx, pid, cov)
            if gov is None:
                continue  # cov_required_present owns this
            expiration = _parse_date(gov.get("expiration_date"))
            if expiration is None:
                continue  # cert_required_fields owns this
            checked += 1
            if expiration <= as_of:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(cert_reg, f"certificates/{_cert_id(gov)}/expiration_date"),
                        f"party {pid} {cov} certificate {_cert_id(gov)} expired "
                        f"{expiration.isoformat()}, on or before the review date "
                        f"{as_of.isoformat()}; the party is uninsured on this line",
                    )
                )
    if not out:
        out.append(
            Finding(rule, Status.PASS, "-", f"all {checked} governing certificates are unexpired")
        )
    return out


@check("exp_renewal_lead_time")
def check_exp_renewal_lead_time(ctx: Context) -> list[Finding]:
    """A governing certificate expiring inside the lead-time window is flagged.

    Deliberately a FLAG, not a failure: the coverage is still in force, but the
    renewal certificate needs to be chased before it lapses. The window comes from
    the file's own ``renewal_lead_days``.
    """
    rule = "exp_renewal_lead_time"
    _sev(rule, Status.FLAG)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if cert_reg is None or as_of is None:
        return []
    lead = ctx.renewal_lead_days
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        pid = _party_id(party)
        for cov in _required_coverages(party):
            if cov not in COVERAGE_TYPES:
                continue
            gov = _governing_cert(ctx, pid, cov)
            if gov is None:
                continue
            expiration = _parse_date(gov.get("expiration_date"))
            if expiration is None:
                continue
            checked += 1
            if within_renewal_window(expiration, as_of, lead):
                remaining = (expiration - as_of).days
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(cert_reg, f"certificates/{_cert_id(gov)}/expiration_date"),
                        f"party {pid} {cov} certificate {_cert_id(gov)} expires "
                        f"{expiration.isoformat()}, in {remaining} day(s); inside the "
                        f"{lead}-day renewal window and due to be chased",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule,
                Status.PASS,
                "-",
                f"all {checked} governing certificates are outside the renewal window",
            )
        )
    return out


@check("exp_workers_comp_present")
def check_exp_workers_comp_present(ctx: Context) -> list[Finding]:
    """Every party carries an unexpired workers' compensation certificate.

    Workers' compensation is a statutory floor for anyone with employees on the
    site, independent of what a party's own requirement list happens to say, so it
    is checked for every party in the register.
    """
    rule = "exp_workers_comp_present"
    _sev(rule, Status.FAIL)
    party_reg = ctx.one(DOC_PARTY_REGISTER)
    cert_reg = ctx.one(DOC_CERTIFICATE_REGISTER)
    as_of = _parse_date(ctx.as_of)
    if party_reg is None or cert_reg is None or as_of is None:
        return []
    out: list[Finding] = []
    checked = 0
    for party in _parties(ctx):
        pid = _party_id(party)
        checked += 1
        gov = _governing_cert(ctx, pid, COVERAGE_WORKERS_COMP)
        if gov is None:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(cert_reg, f"certificates/{pid}/{COVERAGE_WORKERS_COMP}"),
                    f"party {pid} has no workers' compensation certificate on file; it is "
                    f"a statutory floor for anyone with employees on site",
                )
            )
            continue
        expiration = _parse_date(gov.get("expiration_date"))
        if expiration is None or expiration <= as_of:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(cert_reg, f"certificates/{_cert_id(gov)}/expiration_date"),
                    f"party {pid} workers' compensation certificate {_cert_id(gov)} is not "
                    f"in force at {as_of.isoformat()}; the statutory floor is unmet",
                )
            )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", f"all {checked} parties carry unexpired workers' comp"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence
# --------------------------------------------------------------------------- #
@check("rpt_party_compliant_recomputes")
def check_rpt_party_compliant_recomputes(ctx: Context) -> list[Finding]:
    """Each party's stated compliant flag recomputes from its certificates.

    This is the control the engine exists for. The coverage summary is a
    determination, and a determination that is not recomputed from the evidence
    is an assertion. The engine rebuilds every flag from the requirement matrix
    and the governing certificates, and compares.
    """
    rule = "rpt_party_compliant_recomputes"
    _sev(rule, Status.FAIL)
    summary = ctx.one(DOC_COVERAGE_SUMMARY)
    as_of = _parse_date(ctx.as_of)
    if summary is None or as_of is None:
        return []
    parties = _party_map(ctx)
    matrix = _matrix(ctx)
    out: list[Finding] = []
    for row in _rows(summary, "parties"):
        pid = _text(row, "party_id")
        party = parties.get(pid or "")
        if party is None:
            continue
        stated = row.get("compliant")
        with amount_guard(rule, out):
            recomputed = recompute_party_compliant(ctx, party, matrix, as_of)
            if recomputed != stated:
                out.append(
                    Finding(
                        rule,
                        Status.FAIL,
                        ctx.loc(summary, f"parties/{pid}/compliant"),
                        f"party {pid} is summarised compliant={stated}; recomputing from "
                        f"its certificates gives compliant={recomputed}",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "every party compliant flag recomputes from its certificates"
            )
        )
    return out


@check("rpt_report_count_ties")
def check_rpt_report_count_ties(ctx: Context) -> list[Finding]:
    """The monthly report's compliant / non-compliant counts tie the summary.

    The number that reaches a risk committee is a count, and a count maintained
    beside the summary rather than derived from it drifts the first time a flag
    moves and nobody re-adds the column.
    """
    rule = "rpt_report_count_ties"
    _sev(rule, Status.FAIL)
    report = ctx.one(DOC_COMPLIANCE_REPORT)
    summary = ctx.one(DOC_COVERAGE_SUMMARY)
    if report is None or summary is None:
        return []
    compliant = 0
    noncompliant = 0
    for row in _rows(summary, "parties"):
        value = row.get("compliant")
        if value is True:
            compliant += 1
        elif value is False:
            noncompliant += 1
    out: list[Finding] = []
    with amount_guard(rule, out):
        stated_compliant = require_cents(
            "compliance_report.compliant_count",
            report.get("compliant_count"),
            unit="a whole count",
        )
        stated_noncompliant = require_cents(
            "compliance_report.noncompliant_count",
            report.get("noncompliant_count"),
            unit="a whole count",
        )
        if stated_compliant != compliant or stated_noncompliant != noncompliant:
            out.append(
                Finding(
                    rule,
                    Status.FAIL,
                    ctx.loc(report, "compliant_count"),
                    f"the report states {stated_compliant} compliant / "
                    f"{stated_noncompliant} non-compliant; the coverage summary recomputes "
                    f"{compliant} / {noncompliant}",
                )
            )
        else:
            out.append(
                Finding(
                    rule,
                    Status.PASS,
                    "-",
                    f"the report counts of {compliant} / {noncompliant} tie the summary",
                )
            )
    return out


@check("rpt_watchlist_ties")
def check_rpt_watchlist_ties(ctx: Context) -> list[Finding]:
    """The renewal watchlist ties the certificate evidence.

    A FLAG rather than a failure: the watchlist is an operational to-do, and a
    watchlist that lists a certificate not actually due -- or omits one that is --
    sends the renewal chase to the wrong place. It is rebuilt from the governing
    certificates and compared.
    """
    rule = "rpt_watchlist_ties"
    _sev(rule, Status.FLAG)
    watchlist = ctx.one(DOC_RENEWAL_WATCHLIST)
    as_of = _parse_date(ctx.as_of)
    if watchlist is None or as_of is None:
        return []
    recomputed = [_normalize_entry(e) for e in recompute_watchlist(ctx, as_of, ctx.renewal_lead_days)]
    stated = [_normalize_entry(e) for e in _rows(watchlist, "entries")]
    out: list[Finding] = []
    want = sorted(recomputed)
    have = sorted(stated)
    if want != have:
        for entry in have:
            if entry not in want:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"the watchlist lists certificate {entry[0]} as due for renewal, but "
                        f"it is not inside the lead-time window as of {as_of.isoformat()}",
                    )
                )
        for entry in want:
            if entry not in have:
                out.append(
                    Finding(
                        rule,
                        Status.FLAG,
                        ctx.loc(watchlist, f"entries/{entry[0]}"),
                        f"certificate {entry[0]} is due for renewal within the lead-time "
                        f"window but is not on the watchlist",
                    )
                )
    if not out:
        out.append(
            Finding(
                rule, Status.PASS, "-", "the renewal watchlist ties the certificate evidence"
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def analyze_document(path: Path) -> DocumentReport:
    """Run every registered control over one compliance file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: not valid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top level must be a JSON object")

    ctx = Context(path=path, data=raw)
    report = DocumentReport(document=ctx.file_id)
    for _rule_id, fn in REGISTRY:
        report.findings.extend(fn(ctx))
    return report


def analyze_folder(folder: Path) -> list[DocumentReport]:
    """Analyze every ``.json`` compliance file in ``folder``, in sorted order."""
    return [analyze_document(p) for p in sorted(folder.glob("*.json"))]


def overall_verdict(reports: list[DocumentReport]) -> Verdict:
    """Roll a list of compliance-file reports up into one verdict."""
    if any(r.verdict is Verdict.FAIL for r in reports):
        return Verdict.FAIL
    if any(r.verdict is Verdict.REVIEW for r in reports):
        return Verdict.REVIEW
    return Verdict.PASS
