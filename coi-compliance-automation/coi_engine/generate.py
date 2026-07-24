"""
Fictional certificate-of-insurance compliance corpus generator.
===============================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the insured parties, the carriers,
the policy numbers, the limits and the certificate dates are fictional, and the
compliance period is set in a fictional future. No real entity, person, carrier,
project or path appears anywhere. The generator is deterministic and takes no
seed.

The baseline is derived, not typed
----------------------------------
Only the parties, the requirement matrix and the certificates are stated as base
facts. Everything the engine later checks as a rollup -- each party's compliant
determination, the renewal watchlist, the portfolio compliant / non-compliant
counts -- is recomputed by :func:`rederive` from those base facts, through the
*same* :mod:`coi_engine.compliance` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the rollup and keeps the break
confined to one control; a defect that targets a stated rollup edits that figure
alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    _matrix,
    _parties,
    _party_id,
    recompute_party_compliant,
    recompute_watchlist,
)
from .model import (
    COVERAGE_AUTO,
    COVERAGE_CGL,
    COVERAGE_PROFESSIONAL,
    COVERAGE_UMBRELLA,
    COVERAGE_WORKERS_COMP,
    DEFAULT_RENEWAL_LEAD_DAYS,
    DOC_CERTIFICATE_REGISTER,
    DOC_COMPLIANCE_REPORT,
    DOC_COVERAGE_SUMMARY,
    DOC_PARTY_REGISTER,
    DOC_RENEWAL_WATCHLIST,
    DOC_REQUIREMENT_MATRIX,
    PARTY_CONSULTANT,
    PARTY_GENERAL_CONTRACTOR,
    PARTY_SUBCONTRACTOR,
    Context,
)

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
)

PERIOD = "FY2029"
#: The review date every expiry and renewal test is measured to.
AS_OF = "2029-10-01"
#: Lead-time window, in days, for the renewal watchlist.
RENEWAL_LEAD_DAYS = 30


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(party_id, name, party_type, required_coverages)``. Invented vendor names;
#: each party type carries the coverage set its contract demands.
PARTIES: tuple[tuple[Any, ...], ...] = (
    (
        "PTY-101",
        "Kettleridge Builders",
        PARTY_GENERAL_CONTRACTOR,
        (COVERAGE_CGL, COVERAGE_AUTO, COVERAGE_WORKERS_COMP, COVERAGE_UMBRELLA),
    ),
    (
        "PTY-102",
        "Pinehollow Mechanical",
        PARTY_SUBCONTRACTOR,
        (COVERAGE_CGL, COVERAGE_AUTO, COVERAGE_WORKERS_COMP),
    ),
    (
        "PTY-103",
        "Vellmont Design Studio",
        PARTY_CONSULTANT,
        (COVERAGE_CGL, COVERAGE_PROFESSIONAL, COVERAGE_WORKERS_COMP),
    ),
    (
        "PTY-104",
        "Grovewell Site Services",
        PARTY_SUBCONTRACTOR,
        (COVERAGE_CGL, COVERAGE_AUTO, COVERAGE_WORKERS_COMP),
    ),
)

#: ``(party_type, coverage_type, required_per_occurrence, required_aggregate,
#:   requires_additional_insured, requires_waiver_of_subrogation)``. Limits in
#: dollars. The certificates below are struck exactly at these limits so a
#: one-cent shortfall is the whole of a boundary defect.
MATRIX: tuple[tuple[Any, ...], ...] = (
    (PARTY_GENERAL_CONTRACTOR, COVERAGE_CGL, 2_000_000, 4_000_000, True, True),
    (PARTY_GENERAL_CONTRACTOR, COVERAGE_AUTO, 1_000_000, 1_000_000, True, True),
    (PARTY_GENERAL_CONTRACTOR, COVERAGE_WORKERS_COMP, 1_000_000, 1_000_000, False, True),
    (PARTY_GENERAL_CONTRACTOR, COVERAGE_UMBRELLA, 5_000_000, 5_000_000, True, True),
    (PARTY_SUBCONTRACTOR, COVERAGE_CGL, 1_000_000, 2_000_000, True, True),
    (PARTY_SUBCONTRACTOR, COVERAGE_AUTO, 1_000_000, 1_000_000, True, False),
    (PARTY_SUBCONTRACTOR, COVERAGE_WORKERS_COMP, 1_000_000, 1_000_000, False, True),
    (PARTY_CONSULTANT, COVERAGE_CGL, 1_000_000, 2_000_000, True, True),
    (PARTY_CONSULTANT, COVERAGE_PROFESSIONAL, 1_000_000, 2_000_000, False, False),
    (PARTY_CONSULTANT, COVERAGE_WORKERS_COMP, 1_000_000, 1_000_000, False, True),
)

#: ``(certificate_id, party_id, coverage_type, carrier, policy_no, inception,
#:   expiration, per_occurrence, aggregate, additional_insured,
#:   waiver_of_subrogation)``. Limits in dollars. PTY-101 general liability runs
#: as a renewal pair -- a prior term abutting the current one -- so the gap
#: control has a real handover to check; the prior term is fully lapsed by the
#: review date and the current one governs.
CERTIFICATES: tuple[tuple[Any, ...], ...] = (
    ("COI-1001", "PTY-101", COVERAGE_CGL, "Meridian Casualty", "PN-1001", "2029-06-01", "2030-06-01", 2_000_000, 4_000_000, True, True),
    ("COI-1002", "PTY-101", COVERAGE_CGL, "Meridian Casualty", "PN-1002", "2028-06-01", "2029-06-01", 2_000_000, 4_000_000, True, True),
    ("COI-1003", "PTY-101", COVERAGE_AUTO, "Continental Indemnity", "PN-1003", "2029-06-01", "2030-06-01", 1_000_000, 1_000_000, True, True),
    ("COI-1004", "PTY-101", COVERAGE_WORKERS_COMP, "Kingsford Mutual", "PN-1004", "2029-06-01", "2030-06-01", 1_000_000, 1_000_000, False, True),
    ("COI-1005", "PTY-101", COVERAGE_UMBRELLA, "Vantage Surety", "PN-1005", "2029-06-01", "2030-06-01", 5_000_000, 5_000_000, True, True),
    ("COI-1006", "PTY-102", COVERAGE_CGL, "Harborline Specialty", "PN-1006", "2029-06-01", "2030-06-01", 1_000_000, 2_000_000, True, True),
    ("COI-1007", "PTY-102", COVERAGE_AUTO, "Continental Indemnity", "PN-1007", "2029-06-01", "2030-06-01", 1_000_000, 1_000_000, True, False),
    ("COI-1008", "PTY-102", COVERAGE_WORKERS_COMP, "Kingsford Mutual", "PN-1008", "2029-06-01", "2030-06-01", 1_000_000, 1_000_000, False, True),
    ("COI-1009", "PTY-103", COVERAGE_CGL, "Harborline Specialty", "PN-1009", "2029-06-01", "2030-06-01", 1_000_000, 2_000_000, True, True),
    ("COI-1010", "PTY-103", COVERAGE_PROFESSIONAL, "Meridian Casualty", "PN-1010", "2029-06-01", "2030-06-01", 1_000_000, 2_000_000, False, False),
    ("COI-1011", "PTY-103", COVERAGE_WORKERS_COMP, "Kingsford Mutual", "PN-1011", "2029-06-01", "2030-06-01", 1_000_000, 1_000_000, False, True),
    ("COI-1012", "PTY-104", COVERAGE_CGL, "Harborline Specialty", "PN-1012", "2029-06-01", "2030-06-01", 1_000_000, 2_000_000, True, True),
    ("COI-1013", "PTY-104", COVERAGE_AUTO, "Continental Indemnity", "PN-1013", "2029-06-01", "2030-06-01", 1_000_000, 1_000_000, True, False),
    ("COI-1014", "PTY-104", COVERAGE_WORKERS_COMP, "Kingsford Mutual", "PN-1014", "2029-06-01", "2030-06-01", 1_000_000, 1_000_000, False, True),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _party(payload: dict[str, Any], party_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PARTY_REGISTER)
    assert register is not None
    for row in register["parties"]:
        if row.get("party_id") == party_id:
            return row
    raise KeyError(party_id)


def _cert(payload: dict[str, Any], certificate_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_CERTIFICATE_REGISTER)
    assert register is not None
    for row in register["certificates"]:
        if row.get("certificate_id") == certificate_id:
            return row
    raise KeyError(certificate_id)


def _matrix_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    register = _doc(payload, DOC_REQUIREMENT_MATRIX)
    assert register is not None
    return register["requirements"]


def _summary_row(payload: dict[str, Any], party_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_COVERAGE_SUMMARY)
    assert summary is not None
    for row in summary["parties"]:
        if row.get("party_id") == party_id:
            return row
    raise KeyError(party_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_COMPLIANCE_REPORT)
    assert report is not None
    return report


def _watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    watchlist = _doc(payload, DOC_RENEWAL_WATCHLIST)
    assert watchlist is not None
    return watchlist


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup figure from the payload's own base facts."""
    party_doc = _doc(payload, DOC_PARTY_REGISTER)
    matrix_doc = _doc(payload, DOC_REQUIREMENT_MATRIX)
    cert_doc = _doc(payload, DOC_CERTIFICATE_REGISTER)
    summary = _doc(payload, DOC_COVERAGE_SUMMARY)
    watchlist = _doc(payload, DOC_RENEWAL_WATCHLIST)
    report = _doc(payload, DOC_COMPLIANCE_REPORT)
    if not all((party_doc, matrix_doc, cert_doc, summary, watchlist, report)):
        return
    assert summary is not None and watchlist is not None and report is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    as_of = date.fromisoformat(payload["as_of"])
    lead = payload.get("renewal_lead_days", DEFAULT_RENEWAL_LEAD_DAYS)
    matrix = _matrix(ctx)

    # Coverage summary: one compliant determination per party, recomputed through
    # the shared kernel the engine recomputes with.
    summary["parties"] = [
        {
            "party_id": _party_id(party),
            "compliant": recompute_party_compliant(ctx, party, matrix, as_of),
        }
        for party in _parties(ctx)
    ]

    # Renewal watchlist: governing certificates due inside the lead-time window.
    watchlist["entries"] = recompute_watchlist(ctx, as_of, lead)

    # Compliance report: the portfolio counts, derived from the summary flags.
    compliant = sum(1 for row in summary["parties"] if row["compliant"])
    total = len(summary["parties"])
    report["compliant_count"] = compliant
    report["noncompliant_count"] = total - compliant


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean compliance file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "renewal_lead_days": RENEWAL_LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_PARTY_REGISTER,
                "document_id": "PARTIES-2029",
                "parties": [
                    {
                        "party_id": party_id,
                        "name": name,
                        "party_type": party_type,
                        "required_coverages": list(required),
                    }
                    for party_id, name, party_type, required in PARTIES
                ],
            },
            {
                "doc_type": DOC_REQUIREMENT_MATRIX,
                "document_id": "MATRIX-2029",
                "requirements": [
                    {
                        "party_type": party_type,
                        "coverage_type": coverage_type,
                        "required_per_occurrence_cents": d(per_occ),
                        "required_aggregate_cents": d(aggregate),
                        "requires_additional_insured": ai,
                        "requires_waiver_of_subrogation": wos,
                    }
                    for party_type, coverage_type, per_occ, aggregate, ai, wos in MATRIX
                ],
            },
            {
                "doc_type": DOC_CERTIFICATE_REGISTER,
                "document_id": "CERTS-2029",
                "certificates": [
                    {
                        "certificate_id": cert_id,
                        "party_id": party_id,
                        "coverage_type": coverage_type,
                        "carrier": carrier,
                        "policy_no": policy_no,
                        "inception_date": inception,
                        "expiration_date": expiration,
                        "per_occurrence_cents": d(per_occ),
                        "aggregate_cents": d(aggregate),
                        "additional_insured": ai,
                        "waiver_of_subrogation": wos,
                    }
                    for (
                        cert_id, party_id, coverage_type, carrier, policy_no, inception,
                        expiration, per_occ, aggregate, ai, wos,
                    ) in CERTIFICATES
                ],
            },
            {
                "doc_type": DOC_COVERAGE_SUMMARY,
                "document_id": "SUMMARY-2029",
                "parties": [],
            },
            {
                "doc_type": DOC_RENEWAL_WATCHLIST,
                "document_id": "WATCHLIST-2029",
                "entries": [],
            },
            {
                "doc_type": DOC_COMPLIANCE_REPORT,
                "document_id": "REPORT-2029",
                "compliant_count": 0,
                "noncompliant_count": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control
# --------------------------------------------------------------------------- #
def _missing_artifact(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_COMPLIANCE_REPORT
    ]


def _duplicate_party_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_PARTY_REGISTER)
    assert register is not None
    register["parties"].append(dict(_party(payload, "PTY-101")))


def _bad_party_type(payload: dict[str, Any]) -> None:
    _party(payload, "PTY-104")["party_type"] = "vendor"


def _undeclared_coverage(payload: dict[str, Any]) -> None:
    # The party's contract terms were never captured; its coverage set is empty.
    _party(payload, "PTY-103")["required_coverages"] = []


def _matrix_row_missing(payload: dict[str, Any]) -> None:
    # The subcontractor auto-liability requirement is gone; the subs still require
    # it, so their limit can no longer be tested.
    rows = _matrix_rows(payload)
    register = _doc(payload, DOC_REQUIREMENT_MATRIX)
    assert register is not None
    register["requirements"] = [
        r
        for r in rows
        if not (r["party_type"] == PARTY_SUBCONTRACTOR and r["coverage_type"] == COVERAGE_AUTO)
    ]


def _cert_missing_field(payload: dict[str, Any]) -> None:
    del _cert(payload, "COI-1003")["carrier"]


def _duplicate_policy_no(payload: dict[str, Any]) -> None:
    _cert(payload, "COI-1013")["policy_no"] = _cert(payload, "COI-1012")["policy_no"]


def _inverted_cert_term(payload: dict[str, Any]) -> None:
    # The term is entered back to front, while still ending after the review date
    # so only the term-direction control sees it.
    cert = _cert(payload, "COI-1010")
    cert["inception_date"] = "2031-06-01"
    cert["expiration_date"] = "2030-06-01"


def _unknown_party_cert(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CERTIFICATE_REGISTER)
    assert register is not None
    register["certificates"].append(
        {
            "certificate_id": "COI-2001",
            "party_id": "PTY-999",
            "coverage_type": COVERAGE_CGL,
            "carrier": "Meridian Casualty",
            "policy_no": "PN-2001",
            "inception_date": "2029-06-01",
            "expiration_date": "2030-06-01",
            "per_occurrence_cents": d(1_000_000),
            "aggregate_cents": d(2_000_000),
            "additional_insured": True,
            "waiver_of_subrogation": True,
        }
    )


def _invalid_coverage_type(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CERTIFICATE_REGISTER)
    assert register is not None
    register["certificates"].append(
        {
            "certificate_id": "COI-2002",
            "party_id": "PTY-104",
            "coverage_type": "cyber_liability",
            "carrier": "Vantage Surety",
            "policy_no": "PN-2002",
            "inception_date": "2029-06-01",
            "expiration_date": "2030-06-01",
            "per_occurrence_cents": d(1_000_000),
            "aggregate_cents": d(1_000_000),
            "additional_insured": True,
            "waiver_of_subrogation": True,
        }
    )


def _missing_required_cert(payload: dict[str, Any]) -> None:
    # The general contractor's umbrella certificate is off the register entirely.
    register = _doc(payload, DOC_CERTIFICATE_REGISTER)
    assert register is not None
    register["certificates"] = [
        c for c in register["certificates"] if c.get("certificate_id") != "COI-1005"
    ]


def _per_occurrence_short(payload: dict[str, Any]) -> None:
    _cert(payload, "COI-1001")["per_occurrence_cents"] -= d(100_000)


def _aggregate_short(payload: dict[str, Any]) -> None:
    _cert(payload, "COI-1001")["aggregate_cents"] -= d(100_000)


def _coverage_gap(payload: dict[str, Any]) -> None:
    # The current general-liability certificate incepts two months after the prior
    # one lapsed, leaving an uninsured band between the two.
    _cert(payload, "COI-1001")["inception_date"] = "2029-08-01"


def _missing_additional_insured(payload: dict[str, Any]) -> None:
    _cert(payload, "COI-1001")["additional_insured"] = False


def _missing_waiver(payload: dict[str, Any]) -> None:
    _cert(payload, "COI-1004")["waiver_of_subrogation"] = False


def _expired_certificate(payload: dict[str, Any]) -> None:
    # The certificate lapsed a month before the review date; the file still shows
    # it, just expired.
    _cert(payload, "COI-1006")["expiration_date"] = "2029-09-01"


def _renewal_due_soon(payload: dict[str, Any]) -> None:
    # The certificate is still in force but expires inside the lead-time window;
    # the rollup is re-derived so only the renewal FLAG remains.
    _cert(payload, "COI-1012")["expiration_date"] = "2029-10-20"
    rederive(payload)


def _missing_wc_cert(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CERTIFICATE_REGISTER)
    assert register is not None
    register["certificates"] = [
        c for c in register["certificates"] if c.get("certificate_id") != "COI-1008"
    ]


def _compliant_flag_wrong(payload: dict[str, Any]) -> None:
    # The stated determination contradicts the certificates; the count is moved
    # with it so only the recompute control sees the break.
    _summary_row(payload, "PTY-101")["compliant"] = False
    report = _report(payload)
    report["compliant_count"] = 3
    report["noncompliant_count"] = 1


def _report_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["compliant_count"] += 1


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _watchlist(payload)["entries"].append(
        {
            "certificate_id": "COI-1001",
            "party_id": "PTY-101",
            "coverage_type": COVERAGE_CGL,
            "expiration_date": "2030-06-01",
            "days_remaining": 243,
        }
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    cert = _cert(payload, "COI-1001")
    cert["per_occurrence_cents"] = float(cert["per_occurrence_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_party_id": ("party_unique_ids", _duplicate_party_id),
    "bad_party_type": ("party_type_valid", _bad_party_type),
    "undeclared_coverage": ("party_coverage_declared", _undeclared_coverage),
    "matrix_row_missing": ("party_matrix_defined", _matrix_row_missing),
    "cert_missing_field": ("cert_required_fields", _cert_missing_field),
    "duplicate_policy_no": ("cert_policy_no_unique", _duplicate_policy_no),
    "inverted_cert_term": ("cert_term_runs_forward", _inverted_cert_term),
    "unknown_party_cert": ("cert_party_exists", _unknown_party_cert),
    "invalid_coverage_type": ("cov_coverage_type_valid", _invalid_coverage_type),
    "missing_required_cert": ("cov_required_present", _missing_required_cert),
    "per_occurrence_short": ("cov_per_occurrence_meets", _per_occurrence_short),
    "aggregate_short": ("cov_aggregate_meets", _aggregate_short),
    "coverage_gap": ("cov_no_uninsured_gap", _coverage_gap),
    "missing_additional_insured": ("end_additional_insured_present", _missing_additional_insured),
    "missing_waiver": ("end_waiver_of_subrogation_present", _missing_waiver),
    "expired_certificate": ("exp_not_expired", _expired_certificate),
    "renewal_due_soon": ("exp_renewal_lead_time", _renewal_due_soon),
    "missing_wc_cert": ("exp_workers_comp_present", _missing_wc_cert),
    "compliant_flag_wrong": ("rpt_party_compliant_recomputes", _compliant_flag_wrong),
    "report_count_wrong": ("rpt_report_count_ties", _report_count_wrong),
    "watchlist_overstated": ("rpt_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("cov_per_occurrence_meets", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PORTFOLIOS[0])
    clean["file_id"] = f"clean__{PORTFOLIOS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        portfolio = PORTFOLIOS[(i + 1) % len(PORTFOLIOS)]
        f = baseline(portfolio)
        f["file_id"] = f"{name}__{portfolio.replace(' ', '_')}"
        f["planted_defect"] = name
        mutate(f)
        files.append(f)

    for f in files:
        path = folder / f"{f['file_id']}.json"
        path.write_text(
            json.dumps(f, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
