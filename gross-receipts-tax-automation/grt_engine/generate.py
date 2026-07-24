"""
Fictional gross-receipts & excise tax reconciliation corpus generator.
======================================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The filers, the entities, the taxing jurisdictions,
the classification rates, the GL accounts, the receipts and the filing dates are
fictional, and every period is set in a fictional future. No real entity, person,
jurisdiction, city, project or path appears anywhere. The generator is
deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the entities, the jurisdiction rate table, the GL revenue lines and the
worksheet skeletons (their standard-deduction, cadence and calendar facts) are
stated as base facts. Every monetary figure the engine later re-derives -- each
worksheet's gross, non-taxable back-out, taxable base, rate, pre-credit tax,
credit and tax due, the per-filing tax summary, and the portfolio totals -- is
recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`grt_engine.grt` kernel the engine recomputes with. So the relationships the
engine tests are the relationships that produced the data: a defect that changes
a base fact re-derives the rollup and keeps the break confined; a defect that
targets a stated rollup edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import _jur_map, _key, _ledger_for, _windows_for
from .grt import (
    effective_rate,
    expected_credit,
    net_tax,
    tax_before_credit,
    taxable_base,
)
from .model import (
    DOC_ENTITY_REGISTER,
    DOC_EXCISE_REPORT,
    DOC_FILING_REGISTER,
    DOC_JURISDICTION_REGISTER,
    DOC_LICENSE_REGISTER,
    DOC_REVENUE_LEDGER,
    DOC_TAX_SUMMARY,
    LICENSE_ACTIVE,
    Context,
)

#: Fictional filer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
)

PERIOD = "FY2029"
#: The review date every due-date and renewal test is measured to.
AS_OF = "2030-03-01"
#: Lead-time window, in days, for the due-soon and renewal flags.
LEAD_DAYS = 60

GL_ACCOUNT = "29-001-4514"


# --------------------------------------------------------------------------- #
# Base facts
# --------------------------------------------------------------------------- #
#: ``(entity_id, name, status, required_jurisdictions)``.
ENTITIES: tuple[tuple[Any, ...], ...] = (
    ("ENT-01", "Northmoor Development Group", "active", ("MARRAN-STATE", "KELDER-CITY")),
    ("ENT-02", "Halbrook Residential Partners", "active", ("MARRAN-STATE", "OSTREND-CITY")),
    ("ENT-03", "Stonecrest Communities", "active", ("MARRAN-STATE", "HALZA-GET")),
)

#: Each jurisdiction: code, name, cadence, classification, threshold (below which
#: a period owes no tax), small-business credit cap, rate windows (closed date
#: spans with an integer basis-point rate), and the periods expected this cycle.
#: Rates are integer basis points so every tax re-derives to the cent.
JURISDICTIONS: tuple[dict[str, Any], ...] = (
    {
        "jurisdiction_code": "MARRAN-STATE",
        "name": "State of Marran (state gross-receipts tax)",
        "cadence": "monthly",
        "classification": "service_other",
        "threshold_cents": 0,
        "sb_cap_cents": 500_000,
        "rate_windows": [
            {"effective_from": "2029-01-01", "effective_to": "2029-09-30", "rate_bps": 175},
            {"effective_from": "2029-10-01", "effective_to": "2031-12-31", "rate_bps": 210},
        ],
        "periods": ["2029-09", "2029-10"],
    },
    {
        "jurisdiction_code": "KELDER-CITY",
        "name": "City of Kelder (city excise)",
        "cadence": "quarterly",
        "classification": "service",
        "threshold_cents": 10_000_000,
        "sb_cap_cents": 0,
        "rate_windows": [
            {"effective_from": "2029-01-01", "effective_to": "2029-12-31", "rate_bps": 45},
            {"effective_from": "2030-01-01", "effective_to": "2031-12-31", "rate_bps": 66},
        ],
        "periods": ["2029-Q3"],
    },
    {
        "jurisdiction_code": "OSTREND-CITY",
        "name": "City of Ostrend (annual city excise)",
        "cadence": "annual",
        "classification": "service",
        "threshold_cents": 0,
        "sb_cap_cents": 0,
        "rate_windows": [
            {"effective_from": "2029-01-01", "effective_to": "2031-12-31", "rate_bps": 150},
        ],
        "periods": ["2029"],
    },
    {
        "jurisdiction_code": "HALZA-GET",
        "name": "Territory of Halza (general-excise tax)",
        "cadence": "annual",
        "classification": "get",
        "threshold_cents": 0,
        "sb_cap_cents": 0,
        "rate_windows": [
            {"effective_from": "2029-01-01", "effective_to": "2031-12-31", "rate_bps": 400},
        ],
        "periods": ["2029"],
    },
)

#: ``(filing_id, entity, jurisdiction, period, period_start, standard_deduction,
#:   filing_date, due_date, approval_date, worksheet_ref, ledger_grosses)``.
#: The classification is taken from the jurisdiction. Each MARRAN worksheet has
#: two GL lines so the monthly-lines-sum-to-the-worksheet tie has something to
#: check; the others carry one. Gross figures are in cents. Every worksheet is
#: filed on time and approved before filing.
FILING_SPECS: tuple[tuple[Any, ...], ...] = (
    ("FIL-01", "ENT-01", "MARRAN-STATE", "2029-09", "2029-09-01", 0, "2029-10-20", "2029-10-25", "2029-10-18", "WS-M0109-01", (40_000_000, 20_000_000)),
    ("FIL-02", "ENT-01", "MARRAN-STATE", "2029-10", "2029-10-01", 0, "2029-11-20", "2029-11-25", "2029-11-18", "WS-M1009-01", (40_000_000, 20_000_000)),
    ("FIL-03", "ENT-02", "MARRAN-STATE", "2029-09", "2029-09-01", 0, "2029-10-20", "2029-10-25", "2029-10-18", "WS-M0109-02", (40_000_000, 20_000_000)),
    ("FIL-04", "ENT-02", "MARRAN-STATE", "2029-10", "2029-10-01", 0, "2029-11-20", "2029-11-25", "2029-11-18", "WS-M1009-02", (40_000_000, 20_000_000)),
    ("FIL-05", "ENT-03", "MARRAN-STATE", "2029-09", "2029-09-01", 0, "2029-10-20", "2029-10-25", "2029-10-18", "WS-M0109-03", (40_000_000, 20_000_000)),
    ("FIL-06", "ENT-03", "MARRAN-STATE", "2029-10", "2029-10-01", 0, "2029-11-20", "2029-11-25", "2029-11-18", "WS-M1009-03", (40_000_000, 20_000_000)),
    ("FIL-07", "ENT-01", "KELDER-CITY", "2029-Q3", "2029-07-01", 200_000_000, "2029-10-28", "2029-10-31", "2029-10-26", "WS-K3-01", (300_000_000,)),
    ("FIL-08", "ENT-02", "OSTREND-CITY", "2029", "2029-01-01", 0, "2030-01-20", "2030-01-31", "2030-01-18", "WS-O-02", (20_000_000,)),
    ("FIL-09", "ENT-03", "HALZA-GET", "2029", "2029-01-01", 0, "2030-01-15", "2030-01-31", "2030-01-12", "WS-H-03", (20_000_000,)),
)


def _classification_of(code: str) -> str:
    for jur in JURISDICTIONS:
        if jur["jurisdiction_code"] == code:
            return str(jur["classification"])
    return "?"


def _build_ledger() -> list[dict[str, Any]]:
    """One GL revenue document's worth of lines, derived from the filing specs."""
    lines: list[dict[str, Any]] = []
    n = 0
    for fid, entity, code, period, _ps, _std, _fd, _dd, _ad, _ws, grosses in FILING_SPECS:
        classification = _classification_of(code)
        for gross in grosses:
            n += 1
            lines.append(
                {
                    "gl_line_id": f"GL-{n:02d}",
                    "entity_id": entity,
                    "jurisdiction_code": code,
                    "classification": classification,
                    "period": period,
                    "gl_account": GL_ACCOUNT,
                    "gross_receipts_cents": gross,
                    "nontaxable_cents": 0,
                }
            )
    return lines


def _licenses() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entity_id, _name, _status, required in ENTITIES:
        for code in required:
            out.append(
                {
                    "entity_id": entity_id,
                    "jurisdiction_code": code,
                    "status": LICENSE_ACTIVE,
                    "renewal_date": "2031-06-30",
                }
            )
    return out


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _entity(payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_ENTITY_REGISTER)
    assert register is not None
    for row in register["entities"]:
        if row.get("entity_id") == entity_id:
            return row
    raise KeyError(entity_id)


def _jur(payload: dict[str, Any], code: str) -> dict[str, Any]:
    register = _doc(payload, DOC_JURISDICTION_REGISTER)
    assert register is not None
    for row in register["jurisdictions"]:
        if row.get("jurisdiction_code") == code:
            return row
    raise KeyError(code)


def _ledger_line(payload: dict[str, Any], line_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_REVENUE_LEDGER)
    assert register is not None
    for row in register["lines"]:
        if row.get("gl_line_id") == line_id:
            return row
    raise KeyError(line_id)


def _filing(payload: dict[str, Any], filing_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_FILING_REGISTER)
    assert register is not None
    for row in register["filings"]:
        if row.get("filing_id") == filing_id:
            return row
    raise KeyError(filing_id)


def _summary_row(payload: dict[str, Any], filing_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_TAX_SUMMARY)
    assert summary is not None
    for row in summary["filings"]:
        if row.get("filing_id") == filing_id:
            return row
    raise KeyError(filing_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_EXCISE_REPORT)
    assert report is not None
    return report


def _license(payload: dict[str, Any], entity_id: str, code: str) -> dict[str, Any]:
    register = _doc(payload, DOC_LICENSE_REGISTER)
    assert register is not None
    for row in register["licenses"]:
        if row.get("entity_id") == entity_id and row.get("jurisdiction_code") == code:
            return row
    raise KeyError((entity_id, code))


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def _rederive_filings(payload: dict[str, Any]) -> None:
    """Refill every worksheet's monetary fields from the ledger and rate table."""
    register = _doc(payload, DOC_FILING_REGISTER)
    if register is None:
        return
    ctx = Context(path=Path("<generated>"), data=payload)
    jmap = _jur_map(ctx)
    for filing in register["filings"]:
        key = _key(filing)
        lines = _ledger_for(ctx, key)
        gross = sum(int(line["gross_receipts_cents"]) for line in lines)
        nontaxable = sum(int(line["nontaxable_cents"]) for line in lines)
        filing["gross_receipts_cents"] = gross
        filing["nontaxable_cents"] = nontaxable
        standard = int(filing["standard_deduction_applied_cents"])
        base = taxable_base(gross, nontaxable, standard)
        filing["taxable_base_cents"] = base
        jur = jmap.get(filing.get("jurisdiction_code") or "")
        rate = effective_rate(_windows_for(jur), date.fromisoformat(filing["period_start"])) if jur else None
        filing["rate_bps"] = rate if rate is not None else 0
        tb = tax_before_credit(base, rate) if rate is not None else 0
        filing["tax_before_credit_cents"] = tb
        threshold = int(jur["threshold_cents"]) if jur else 0
        cap = int(jur["sb_cap_cents"]) if jur else 0
        credit = expected_credit(gross, tb, threshold, cap)
        filing["credit_cents"] = credit
        filing["tax_due_cents"] = net_tax(tb, credit)


def _rederive_rollup(payload: dict[str, Any]) -> None:
    """Rebuild the tax summary and the portfolio report from the worksheets."""
    filing_reg = _doc(payload, DOC_FILING_REGISTER)
    summary = _doc(payload, DOC_TAX_SUMMARY)
    report = _doc(payload, DOC_EXCISE_REPORT)
    if filing_reg is None or summary is None or report is None:
        return
    summary["filings"] = [
        {"filing_id": f["filing_id"], "tax_due_cents": int(f["tax_due_cents"])}
        for f in filing_reg["filings"]
    ]
    report["total_tax_due_cents"] = sum(int(r["tax_due_cents"]) for r in summary["filings"])
    report["filing_count"] = len(summary["filings"])


def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    _rederive_filings(payload)
    _rederive_rollup(payload)


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean reconciliation file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "period": PERIOD,
        "as_of": AS_OF,
        "lead_days": LEAD_DAYS,
        "documents": [
            {
                "doc_type": DOC_ENTITY_REGISTER,
                "document_id": "ENTITIES-2029",
                "entities": [
                    {
                        "entity_id": entity_id,
                        "name": name,
                        "status": status,
                        "required_jurisdictions": list(required),
                    }
                    for entity_id, name, status, required in ENTITIES
                ],
            },
            {
                "doc_type": DOC_JURISDICTION_REGISTER,
                "document_id": "JUR-2029",
                "jurisdictions": [json.loads(json.dumps(j)) for j in JURISDICTIONS],
            },
            {
                "doc_type": DOC_REVENUE_LEDGER,
                "document_id": "GL-2029",
                "lines": _build_ledger(),
            },
            {
                "doc_type": DOC_FILING_REGISTER,
                "document_id": "FILINGS-2029",
                "filings": [
                    {
                        "filing_id": fid,
                        "entity_id": entity,
                        "jurisdiction_code": code,
                        "classification": _classification_of(code),
                        "period": period,
                        "period_start": period_start,
                        "standard_deduction_applied_cents": std,
                        "gross_receipts_cents": 0,
                        "nontaxable_cents": 0,
                        "taxable_base_cents": 0,
                        "rate_bps": 0,
                        "tax_before_credit_cents": 0,
                        "credit_cents": 0,
                        "tax_due_cents": 0,
                        "filed": True,
                        "filing_date": filing_date,
                        "due_date": due_date,
                        "approval_signed": True,
                        "approval_date": approval_date,
                        "worksheet_ref": worksheet_ref,
                    }
                    for (
                        fid, entity, code, period, period_start, std, filing_date,
                        due_date, approval_date, worksheet_ref, _grosses,
                    ) in FILING_SPECS
                ],
            },
            {
                "doc_type": DOC_TAX_SUMMARY,
                "document_id": "SUMMARY-2029",
                "filings": [],
            },
            {
                "doc_type": DOC_LICENSE_REGISTER,
                "document_id": "LICENSES-2029",
                "licenses": _licenses(),
            },
            {
                "doc_type": DOC_EXCISE_REPORT,
                "document_id": "REPORT-2029",
                "total_tax_due_cents": 0,
                "filing_count": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_EXCISE_REPORT
    ]


def _duplicate_entity_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_ENTITY_REGISTER)
    assert register is not None
    register["entities"].append(dict(_entity(payload, "ENT-01")))


def _undeclared_jurisdictions(payload: dict[str, Any]) -> None:
    # The entity's filing scope was never captured; its jurisdiction set is empty.
    _entity(payload, "ENT-03")["required_jurisdictions"] = []


def _bad_cadence(payload: dict[str, Any]) -> None:
    _jur(payload, "OSTREND-CITY")["cadence"] = "fortnightly"


def _inverted_rate_window(payload: dict[str, Any]) -> None:
    # The window is entered back to front while its rate stays plausible.
    window = _jur(payload, "HALZA-GET")["rate_windows"][0]
    window["effective_from"] = "2032-06-01"


def _ledger_missing_field(payload: dict[str, Any]) -> None:
    del _ledger_line(payload, "GL-01")["gross_receipts_cents"]


def _duplicate_ledger_line(payload: dict[str, Any]) -> None:
    # A second line reuses an existing id but carries no receipts, so the gross
    # tie still holds and only the uniqueness control sees it.
    twin = dict(_ledger_line(payload, "GL-01"))
    twin["gross_receipts_cents"] = 0
    twin["nontaxable_cents"] = 0
    _doc(payload, DOC_REVENUE_LEDGER)["lines"].append(twin)


def _unknown_entity_ledger(payload: dict[str, Any]) -> None:
    _ledger_line(payload, "GL-13")["entity_id"] = "ENT-999"


def _orphan_ledger_line(payload: dict[str, Any]) -> None:
    # A receipt for an entity/jurisdiction pair with no worksheet to carry it.
    _doc(payload, DOC_REVENUE_LEDGER)["lines"].append(
        {
            "gl_line_id": "GL-90",
            "entity_id": "ENT-01",
            "jurisdiction_code": "HALZA-GET",
            "classification": "get",
            "period": "2029",
            "gl_account": GL_ACCOUNT,
            "gross_receipts_cents": 0,
            "nontaxable_cents": 0,
        }
    )


def _unknown_entity_filing(payload: dict[str, Any]) -> None:
    # A zero-value worksheet naming an entity that is not in the register.
    _doc(payload, DOC_FILING_REGISTER)["filings"].append(
        {
            "filing_id": "FIL-90",
            "entity_id": "ENT-999",
            "jurisdiction_code": "OSTREND-CITY",
            "classification": "service",
            "period": "2029",
            "period_start": "2029-01-01",
            "standard_deduction_applied_cents": 0,
            "gross_receipts_cents": 0,
            "nontaxable_cents": 0,
            "taxable_base_cents": 0,
            "rate_bps": 150,
            "tax_before_credit_cents": 0,
            "credit_cents": 0,
            "tax_due_cents": 0,
            "filed": True,
            "filing_date": "2030-01-20",
            "due_date": "2030-01-31",
            "approval_signed": True,
            "approval_date": "2030-01-18",
            "worksheet_ref": "WS-90",
        }
    )


def _gross_tie_break(payload: dict[str, Any]) -> None:
    _filing(payload, "FIL-01")["gross_receipts_cents"] += 100


def _filing_missing_field(payload: dict[str, Any]) -> None:
    del _filing(payload, "FIL-04")["worksheet_ref"]


def _duplicate_filing(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_FILING_REGISTER)["filings"].append(dict(_filing(payload, "FIL-05")))


def _wrong_effective_rate(payload: dict[str, Any]) -> None:
    # The period is dated before any rate window opens, so no rate is in force
    # for it, while the stated rate still ties the stated tax.
    _filing(payload, "FIL-01")["period_start"] = "2028-06-01"


def _tax_before_wrong(payload: dict[str, Any]) -> None:
    # The pre-credit tax is a cent off; the tax due is moved with it so only the
    # pre-credit re-derivation sees the break.
    filing = _filing(payload, "FIL-01")
    filing["tax_before_credit_cents"] += 1
    filing["tax_due_cents"] += 1


def _tax_due_wrong(payload: dict[str, Any]) -> None:
    _filing(payload, "FIL-02")["tax_due_cents"] += 1


def _base_wrong(payload: dict[str, Any]) -> None:
    _filing(payload, "FIL-02")["taxable_base_cents"] += 1


def _nontaxable_tie_break(payload: dict[str, Any]) -> None:
    # A GL line's non-taxable portion no longer sums to the worksheet's back-out.
    _ledger_line(payload, "GL-05")["nontaxable_cents"] += 1


def _credit_wrong(payload: dict[str, Any]) -> None:
    # A credit is claimed where the jurisdiction's rules allow none; the tax due
    # is moved with it so only the credit re-derivation sees the break.
    filing = _filing(payload, "FIL-01")
    filing["credit_cents"] += 1
    filing["tax_due_cents"] -= 1


def _missing_filing(payload: dict[str, Any]) -> None:
    # An expected worksheet, and its receipts, are off the record entirely; the
    # rollup is re-derived so only the completeness control sees the hole.
    filing_reg = _doc(payload, DOC_FILING_REGISTER)
    ledger_reg = _doc(payload, DOC_REVENUE_LEDGER)
    assert filing_reg is not None and ledger_reg is not None
    filing_reg["filings"] = [f for f in filing_reg["filings"] if f["filing_id"] != "FIL-08"]
    ledger_reg["lines"] = [
        line
        for line in ledger_reg["lines"]
        if not (line["entity_id"] == "ENT-02" and line["jurisdiction_code"] == "OSTREND-CITY")
    ]
    _rederive_rollup(payload)


def _late_filing(payload: dict[str, Any]) -> None:
    _filing(payload, "FIL-09")["filing_date"] = "2030-02-15"


def _due_soon_unfiled(payload: dict[str, Any]) -> None:
    # The worksheet is not yet filed and its due date is inside the lead window.
    filing = _filing(payload, "FIL-09")
    filing["filed"] = False
    filing["due_date"] = "2030-03-20"


def _unapproved_filing(payload: dict[str, Any]) -> None:
    _filing(payload, "FIL-06")["approval_signed"] = False


def _license_cancelled(payload: dict[str, Any]) -> None:
    _license(payload, "ENT-01", "MARRAN-STATE")["status"] = "cancelled"


def _license_renewal_due(payload: dict[str, Any]) -> None:
    # The licence is still active but its renewal falls inside the lead window.
    _license(payload, "ENT-02", "OSTREND-CITY")["renewal_date"] = "2030-04-01"


def _summary_recompute_break(payload: dict[str, Any]) -> None:
    # The stated determination contradicts the receipts; the total is moved with
    # it so only the recompute control sees the break.
    _summary_row(payload, "FIL-07")["tax_due_cents"] += 1
    _report(payload)["total_tax_due_cents"] += 1


def _report_total_break(payload: dict[str, Any]) -> None:
    _report(payload)["total_tax_due_cents"] += 1


def _amount_not_integer(payload: dict[str, Any]) -> None:
    filing = _filing(payload, "FIL-01")
    filing["taxable_base_cents"] = float(filing["taxable_base_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_entity_id": ("ent_unique_ids", _duplicate_entity_id),
    "undeclared_jurisdictions": ("ent_jurisdictions_declared", _undeclared_jurisdictions),
    "bad_cadence": ("jur_cadence_valid", _bad_cadence),
    "inverted_rate_window": ("jur_rate_windows_sound", _inverted_rate_window),
    "ledger_missing_field": ("rev_required_fields", _ledger_missing_field),
    "duplicate_ledger_line": ("rev_line_unique", _duplicate_ledger_line),
    "unknown_entity_ledger": ("rev_entity_known", _unknown_entity_ledger),
    "orphan_ledger_line": ("rev_ledger_mapped", _orphan_ledger_line),
    "gross_tie_break": ("rev_gross_ties_ledger", _gross_tie_break),
    "filing_missing_field": ("fil_required_fields", _filing_missing_field),
    "duplicate_filing": ("fil_unique", _duplicate_filing),
    "unknown_entity_filing": ("fil_refs_exist", _unknown_entity_filing),
    "wrong_effective_rate": ("eff_rate_matches_period", _wrong_effective_rate),
    "tax_before_wrong": ("rate_tax_before_credit_recomputes", _tax_before_wrong),
    "tax_due_wrong": ("rate_tax_due_recomputes", _tax_due_wrong),
    "base_wrong": ("ded_base_recomputes", _base_wrong),
    "nontaxable_tie_break": ("ded_nontaxable_ties_ledger", _nontaxable_tie_break),
    "credit_wrong": ("ded_credit_recomputes", _credit_wrong),
    "missing_filing": ("cal_completeness", _missing_filing),
    "late_filing": ("cal_due_date_gate", _late_filing),
    "due_soon_unfiled": ("cal_due_soon", _due_soon_unfiled),
    "unapproved_filing": ("cal_approval_before_filing", _unapproved_filing),
    "license_cancelled": ("lic_status_active", _license_cancelled),
    "license_renewal_due": ("lic_renewal_current", _license_renewal_due),
    "summary_recompute_break": ("rpt_summary_recomputes", _summary_recompute_break),
    "report_total_break": ("rpt_report_totals_tie", _report_total_break),
    "amount_not_integer": ("rate_tax_before_credit_recomputes", _amount_not_integer),
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
