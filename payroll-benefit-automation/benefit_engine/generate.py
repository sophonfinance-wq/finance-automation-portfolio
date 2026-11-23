"""
Fictional payroll & benefit reconciliation corpus generator.
============================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The employers, the employees, the benefit
providers, the plan codes, the compensation and the contribution amounts are
fictional, and the pay period is set in a fictional future. No real entity,
person, provider, plan or path appears anywhere. The generator is deterministic
and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the employees, the plan catalog, the register deductions (employee-typed
deferrals and FSA elections) and the pay/remit dates are stated as base facts.
The employer match and the per-period HSA withholding are computed through the
*same* :mod:`benefit_engine.reconcile` kernel the engine recomputes with; and
every rollup the engine later checks -- the provider uploads, the entity
subtotals, the cash transfers, the journal entry, and the reconciliation report's
tie flags and exception watchlist -- is rebuilt by :func:`rederive` from those
base facts through the same helpers the controls use. So the relationships the
engine tests are the relationships that produced the data: a defect that changes
a base fact re-derives the rollups and keeps the break confined; a defect that
targets a stated rollup edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    _known_plan_codes_in_register,
    _plan_providers,
    recompute_exceptions,
    recompute_plan_tied,
    register_total,
    register_total_entity,
)
from .model import (
    DOC_DEDUCTION_REGISTER,
    DOC_EMPLOYEE_REGISTER,
    DOC_ENTITY_SUMMARY,
    DOC_JOURNAL_ENTRY,
    DOC_PLAN_CATALOG,
    DOC_PROVIDER_FILE,
    DOC_RECONCILIATION_REPORT,
    DOC_REMITTANCE_SCHEDULE,
    ENTITY_NW,
    ENTITY_SW,
    ENTITY_TX,
    PLAN_DEFERRAL,
    PLAN_FSA_DEPENDENT,
    PLAN_FSA_MEDICAL,
    PLAN_HSA,
    PLAN_MATCH,
    TIER_FAMILY,
    TIER_NONE,
    TIER_SELF_ONLY,
    Context,
)
from .reconcile import derive_match, hsa_limit, per_period_base, remaining_room

#: Fictional employer labels, rotated for file identity only.
EMPLOYERS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere Holdings",
)

PERIOD = "FY2031-P17"
#: The review date every date-gate is measured to.
AS_OF = "2031-09-30"
#: Plan-year-end the age-50 / age-55 catch-up gates are measured to.
PLAN_YEAR_END = "2031-12-31"
#: Pay periods remaining, the divisor in the per-period HSA withholding.
PERIODS_REMAINING = 7
#: DOL small-plan deposit safe harbor, in business days.
SAFE_HARBOR_BUSINESS_DAYS = 7
#: Watch band, in cents, below the 402(g) limit for the review FLAG.
DEFERRAL_WATCH_BAND_CENTS = 200_000

#: Fictional benefit providers.
REC = "Vantage Benefits"  # 401(k) recordkeeper
CUST = "Harborline Trust"  # 401(k) / match custodian
HSA_ADMIN = "Kelder Health Savings"  # HSA administrator
FSA_ADMIN = "Marran Flex Administrators"  # FSA administrator

#: Plan codes.
P_401K = "P-401K"
P_MATCH = "P-MATCH"
P_HSA = "P-HSA"
P_FSA_MED = "P-FSA-MED"
P_FSA_DEP = "P-FSA-DEP"

#: Journal-entry settlement accounts (not clearing accounts).
ACCT_NETPAY = "1900-NETPAY"
ACCT_CASH = "1000-CASH"

MATCH_RATE_BPS = 5000  # 50% match
COMP_CAP_CENTS = 1_346_150  # per-period 401(a)(17) compensation cap
ADDITIONS_LIMIT_CENTS = 7_000_000  # 415(c) annual additions ceiling

#: Plan catalog. Each row is a plan definition the engine reads limits from.
PLANS: tuple[dict[str, Any], ...] = (
    {
        "plan_code": P_401K,
        "plan_name": "401(k) pre-tax deferral",
        "plan_type": PLAN_DEFERRAL,
        "providers": [REC, CUST],
        "is_employee_money": True,
        "flat_limit_cents": 2_350_000,
        "catchup_limit_cents": 750_000,
        "catchup_age": 50,
        "gl_liability_account": "2110-DEFERRAL",
        "gl_description": "401(k) deferrals payable",
    },
    {
        "plan_code": P_MATCH,
        "plan_name": "Employer matching contribution",
        "plan_type": PLAN_MATCH,
        "providers": [CUST],
        "is_employee_money": False,
        "match_rate_bps": MATCH_RATE_BPS,
        "comp_cap_cents": COMP_CAP_CENTS,
        "additions_limit_cents": ADDITIONS_LIMIT_CENTS,
        "gl_liability_account": "2115-MATCH",
        "gl_description": "Employer match payable",
    },
    {
        "plan_code": P_HSA,
        "plan_name": "Health savings account",
        "plan_type": PLAN_HSA,
        "providers": [HSA_ADMIN],
        "is_employee_money": True,
        "self_only_limit_cents": 430_000,
        "family_limit_cents": 855_000,
        "catchup_limit_cents": 100_000,
        "catchup_age": 55,
        "gl_liability_account": "2130-HSA",
        "gl_description": "HSA contributions payable",
    },
    {
        "plan_code": P_FSA_MED,
        "plan_name": "Health FSA",
        "plan_type": PLAN_FSA_MEDICAL,
        "providers": [FSA_ADMIN],
        "is_employee_money": True,
        "flat_limit_cents": 330_000,
        "gl_liability_account": "2140-FSAMED",
        "gl_description": "FSA medical payable",
    },
    {
        "plan_code": P_FSA_DEP,
        "plan_name": "Dependent-care FSA",
        "plan_type": PLAN_FSA_DEPENDENT,
        "providers": [FSA_ADMIN],
        "is_employee_money": True,
        "flat_limit_cents": 500_000,
        "gl_liability_account": "2145-FSADEP",
        "gl_description": "FSA dependent-care payable",
    },
)

#: ``(employee_id, name, entity, dob, tier, eligible_comp, match_eligible,
#:   hsa_employer_annual, prior_ytd, deferral_this, fsa_this)``. Invented people.
#: ``prior_ytd`` and the this-period figures are struck so every employee sits
#: comfortably under each statutory ceiling; the defects breach them one at a time.
EMPLOYEES: tuple[dict[str, Any], ...] = (
    {
        "employee_id": "EMP-01",
        "name": "Rowan Ashby",
        "entity": ENTITY_NW,
        "dob": "1985-04-10",
        "hsa_coverage_tier": TIER_SELF_ONLY,
        "eligible_comp_cents": 800_000,
        "match_eligible": True,
        "hsa_employer_annual_cents": 50_000,
        "prior_ytd": {P_401K: 1_000_000, P_HSA: 100_000, P_FSA_MED: 100_000},
        "deferral_this": 90_000,
        "fsa_this": [(P_FSA_MED, 12_000)],
    },
    {
        "employee_id": "EMP-02",
        "name": "Devin Calloway",
        "entity": ENTITY_NW,
        "dob": "1972-08-22",
        "hsa_coverage_tier": TIER_FAMILY,
        "eligible_comp_cents": 1_200_000,
        "match_eligible": True,
        "hsa_employer_annual_cents": 75_000,
        "prior_ytd": {P_401K: 2_000_000, P_HSA: 300_000, P_FSA_DEP: 200_000},
        "deferral_this": 100_000,
        "fsa_this": [(P_FSA_DEP, 30_000)],
    },
    {
        "employee_id": "EMP-03",
        "name": "Marlowe Finch",
        "entity": ENTITY_SW,
        "dob": "1990-01-05",
        "hsa_coverage_tier": TIER_NONE,
        "eligible_comp_cents": 600_000,
        "match_eligible": True,
        "hsa_employer_annual_cents": 0,
        "prior_ytd": {P_401K: 500_000, P_FSA_MED: 80_000},
        "deferral_this": 60_000,
        "fsa_this": [(P_FSA_MED, 10_000)],
    },
    {
        "employee_id": "EMP-04",
        "name": "Sana Okoro",
        "entity": ENTITY_SW,
        "dob": "1968-11-30",
        "hsa_coverage_tier": TIER_SELF_ONLY,
        "eligible_comp_cents": 1_500_000,  # above the comp cap
        "match_eligible": True,
        "hsa_employer_annual_cents": 40_000,
        "prior_ytd": {P_401K: 900_000, P_HSA: 90_000},
        "deferral_this": 120_000,
        "fsa_this": [],
    },
    {
        "employee_id": "EMP-05",
        "name": "Teodor Vance",
        "entity": ENTITY_TX,
        "dob": "1995-06-18",
        "hsa_coverage_tier": TIER_FAMILY,
        "eligible_comp_cents": 900_000,
        "match_eligible": False,
        "hsa_employer_annual_cents": 24_000,
        "prior_ytd": {P_401K: 200_000, P_HSA: 130_000},
        "deferral_this": 70_000,
        "fsa_this": [],
    },
)

#: ``plan_code -> (pay_date, remit_date)``. Base facts; the cash transfer is
#: derived. Every employee-money plan remits inside the safe harbor.
REMIT_DATES: dict[str, tuple[str, str]] = {
    P_401K: ("2031-08-29", "2031-09-03"),
    P_MATCH: ("2031-08-29", "2031-09-03"),
    P_HSA: ("2031-08-29", "2031-09-03"),
    P_FSA_MED: ("2031-08-29", "2031-09-03"),
    P_FSA_DEP: ("2031-08-29", "2031-09-03"),
}


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _plan(plan_code: str) -> dict[str, Any]:
    for plan in PLANS:
        if plan["plan_code"] == plan_code:
            return plan
    raise KeyError(plan_code)


def _employee(payload: dict[str, Any], employee_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_EMPLOYEE_REGISTER)
    assert register is not None
    for row in register["employees"]:
        if row.get("employee_id") == employee_id:
            return row
    raise KeyError(employee_id)


def _deduction(payload: dict[str, Any], employee_id: str, plan_code: str) -> dict[str, Any]:
    register = _doc(payload, DOC_DEDUCTION_REGISTER)
    assert register is not None
    for row in register["deductions"]:
        if row.get("employee_id") == employee_id and row.get("plan_code") == plan_code:
            return row
    raise KeyError((employee_id, plan_code))


def _plan_row(payload: dict[str, Any], plan_code: str) -> dict[str, Any]:
    catalog = _doc(payload, DOC_PLAN_CATALOG)
    assert catalog is not None
    for row in catalog["plans"]:
        if row.get("plan_code") == plan_code:
            return row
    raise KeyError(plan_code)


def _upload(payload: dict[str, Any], provider: str, plan_code: str, employee_id: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_PROVIDER_FILE)
    assert doc is not None
    for row in doc["uploads"]:
        if (
            row.get("provider") == provider
            and row.get("plan_code") == plan_code
            and row.get("employee_id") == employee_id
        ):
            return row
    raise KeyError((provider, plan_code, employee_id))


def _subtotal(payload: dict[str, Any], entity: str, plan_code: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_ENTITY_SUMMARY)
    assert doc is not None
    for row in doc["subtotals"]:
        if row.get("entity") == entity and row.get("plan_code") == plan_code:
            return row
    raise KeyError((entity, plan_code))


def _consolidated_row(payload: dict[str, Any], plan_code: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_ENTITY_SUMMARY)
    assert doc is not None
    for row in doc["consolidated"]:
        if row.get("plan_code") == plan_code:
            return row
    raise KeyError(plan_code)


def _remittance(payload: dict[str, Any], plan_code: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_REMITTANCE_SCHEDULE)
    assert doc is not None
    for row in doc["remittances"]:
        if row.get("plan_code") == plan_code:
            return row
    raise KeyError(plan_code)


def _je_credit_line(payload: dict[str, Any], plan_code: str) -> dict[str, Any]:
    """The accrual (credit) line of one plan's liability account."""
    doc = _doc(payload, DOC_JOURNAL_ENTRY)
    assert doc is not None
    account = _plan(plan_code)["gl_liability_account"]
    for row in doc["lines"]:
        if row.get("gl_account") == account and row.get("plan_code") == plan_code and row.get("credit_cents", 0):
            return row
    raise KeyError(plan_code)


def _report_plan(payload: dict[str, Any], plan_code: str) -> dict[str, Any]:
    report = _doc(payload, DOC_RECONCILIATION_REPORT)
    assert report is not None
    for row in report["plans"]:
        if row.get("plan_code") == plan_code:
            return row
    raise KeyError(plan_code)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_RECONCILIATION_REPORT)
    assert report is not None
    return report


# --------------------------------------------------------------------------- #
# Deductions -- match and HSA computed through the shared kernel
# --------------------------------------------------------------------------- #
def _base_deductions() -> list[dict[str, Any]]:
    """Build the register deductions, deriving match and HSA from the kernel."""
    rows: list[dict[str, Any]] = []
    for emp in EMPLOYEES:
        eid = emp["employee_id"]
        rows.append({"employee_id": eid, "plan_code": P_401K, "amount_cents": emp["deferral_this"]})
        if emp["match_eligible"]:
            match = derive_match(emp["eligible_comp_cents"], MATCH_RATE_BPS, COMP_CAP_CENTS)
            rows.append({"employee_id": eid, "plan_code": P_MATCH, "amount_cents": match})
        if emp["hsa_coverage_tier"] != TIER_NONE:
            hsa_plan = _plan(P_HSA)
            # age at plan-year-end drives the catch-up; kept simple and explicit.
            from datetime import date

            from .reconcile import age_on

            age = age_on(date.fromisoformat(emp["dob"]), date.fromisoformat(PLAN_YEAR_END))
            limit = hsa_limit(
                hsa_plan["self_only_limit_cents"],
                hsa_plan["family_limit_cents"],
                hsa_plan["catchup_limit_cents"],
                hsa_plan["catchup_age"],
                emp["hsa_coverage_tier"],
                age,
            )
            room = remaining_room(limit, emp["hsa_employer_annual_cents"], emp["prior_ytd"].get(P_HSA, 0))
            rows.append(
                {"employee_id": eid, "plan_code": P_HSA, "amount_cents": per_period_base(room, PERIODS_REMAINING)}
            )
        for plan_code, amount in emp["fsa_this"]:
            rows.append({"employee_id": eid, "plan_code": plan_code, "amount_cents": amount})
    rows.sort(key=lambda r: (r["employee_id"], r["plan_code"]))
    return rows


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every rollup from the payload's own base facts."""
    provider_doc = _doc(payload, DOC_PROVIDER_FILE)
    entity_doc = _doc(payload, DOC_ENTITY_SUMMARY)
    remit_doc = _doc(payload, DOC_REMITTANCE_SCHEDULE)
    je_doc = _doc(payload, DOC_JOURNAL_ENTRY)
    report = _doc(payload, DOC_RECONCILIATION_REPORT)
    if not all((provider_doc, entity_doc, remit_doc, je_doc, report)):
        return
    assert provider_doc is not None and entity_doc is not None and remit_doc is not None
    assert je_doc is not None and report is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    plan_codes = _known_plan_codes_in_register(ctx)
    entities = (ENTITY_NW, ENTITY_SW, ENTITY_TX)
    deductions = _doc(payload, DOC_DEDUCTION_REGISTER)["deductions"]  # type: ignore[index]

    # Provider file: mirror every deduction to each of its plan's providers.
    uploads: list[dict[str, Any]] = []
    for row in deductions:
        plan_code = row.get("plan_code")
        if plan_code not in plan_codes:
            continue
        for provider in _plan_providers(_plan(plan_code)):
            uploads.append(
                {
                    "provider": provider,
                    "plan_code": plan_code,
                    "employee_id": row["employee_id"],
                    "amount_cents": row["amount_cents"],
                }
            )
    uploads.sort(key=lambda u: (u["provider"], u["plan_code"], u["employee_id"]))
    provider_doc["uploads"] = uploads

    # Entity summary: per-(entity, plan) subtotals and the consolidated totals.
    subtotals: list[dict[str, Any]] = []
    for entity in entities:
        for plan_code in plan_codes:
            amount = register_total_entity(ctx, entity, plan_code)
            if amount:
                subtotals.append({"entity": entity, "plan_code": plan_code, "subtotal_cents": amount})
    subtotals.sort(key=lambda s: (s["entity"], s["plan_code"]))
    entity_doc["subtotals"] = subtotals
    entity_doc["consolidated"] = [
        {"plan_code": pc, "total_cents": register_total(ctx, pc)} for pc in plan_codes
    ]

    # Remittance schedule: keep the pay/remit dates, derive the cash transfer.
    remittances: list[dict[str, Any]] = []
    for plan_code in plan_codes:
        pay, remit = REMIT_DATES[plan_code]
        remittances.append(
            {
                "plan_code": plan_code,
                "pay_date": pay,
                "remit_date": remit,
                "cash_transfer_cents": register_total(ctx, plan_code),
            }
        )
    remit_doc["remittances"] = remittances

    # Journal entry: accrue and relieve each plan's payable, settle to cash.
    lines: list[dict[str, Any]] = []
    grand = 0
    for plan_code in plan_codes:
        total = register_total(ctx, plan_code)
        grand += total
        plan = _plan(plan_code)
        account = plan["gl_liability_account"]
        desc = plan["gl_description"]
        lines.append(
            {"gl_account": account, "gl_description": desc, "entity": "-", "plan_code": plan_code, "debit_cents": 0, "credit_cents": total}
        )
        lines.append(
            {"gl_account": account, "gl_description": desc, "entity": "-", "plan_code": plan_code, "debit_cents": total, "credit_cents": 0}
        )
    lines.append(
        {"gl_account": ACCT_NETPAY, "gl_description": "Net pay clearing", "entity": "-", "plan_code": "-", "debit_cents": grand, "credit_cents": 0}
    )
    lines.append(
        {"gl_account": ACCT_CASH, "gl_description": "Cash - benefit remittances", "entity": "-", "plan_code": "-", "debit_cents": 0, "credit_cents": grand}
    )
    je_doc["lines"] = lines

    # Reconciliation report: per-plan tie flags and the statutory exceptions.
    report["plans"] = [{"plan_code": pc, "tied": recompute_plan_tied(ctx, pc)} for pc in plan_codes]
    report["exceptions"] = recompute_exceptions(ctx)
    tied = sum(1 for row in report["plans"] if row["tied"])
    report["tied_count"] = tied
    report["broken_count"] = len(report["plans"]) - tied


def baseline(employer: str) -> dict[str, Any]:
    """Build a clean reconciliation file for ``employer``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "employer": employer,
        "period": PERIOD,
        "as_of": AS_OF,
        "plan_year_end": PLAN_YEAR_END,
        "periods_remaining": PERIODS_REMAINING,
        "safe_harbor_business_days": SAFE_HARBOR_BUSINESS_DAYS,
        "deferral_watch_band_cents": DEFERRAL_WATCH_BAND_CENTS,
        "documents": [
            {
                "doc_type": DOC_EMPLOYEE_REGISTER,
                "document_id": "EMPLOYEES-2031",
                "employees": [
                    {
                        "employee_id": emp["employee_id"],
                        "name": emp["name"],
                        "entity": emp["entity"],
                        "dob": emp["dob"],
                        "hsa_coverage_tier": emp["hsa_coverage_tier"],
                        "eligible_comp_cents": emp["eligible_comp_cents"],
                        "match_eligible": emp["match_eligible"],
                        "hsa_employer_annual_cents": emp["hsa_employer_annual_cents"],
                        "prior_ytd": dict(emp["prior_ytd"]),
                    }
                    for emp in EMPLOYEES
                ],
            },
            {
                "doc_type": DOC_PLAN_CATALOG,
                "document_id": "PLANS-2031",
                "plans": [dict(plan) for plan in PLANS],
            },
            {
                "doc_type": DOC_DEDUCTION_REGISTER,
                "document_id": "DEDUCTIONS-2031",
                "deductions": _base_deductions(),
            },
            {"doc_type": DOC_PROVIDER_FILE, "document_id": "UPLOADS-2031", "uploads": []},
            {"doc_type": DOC_REMITTANCE_SCHEDULE, "document_id": "REMIT-2031", "remittances": []},
            {"doc_type": DOC_ENTITY_SUMMARY, "document_id": "ENTITY-2031", "subtotals": [], "consolidated": []},
            {"doc_type": DOC_JOURNAL_ENTRY, "document_id": "JE-2031", "lines": []},
            {
                "doc_type": DOC_RECONCILIATION_REPORT,
                "document_id": "RECON-2031",
                "plans": [],
                "exceptions": [],
                "tied_count": 0,
                "broken_count": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects -- one per registered control (+ one malformed amount)
# --------------------------------------------------------------------------- #
def _missing_artifact(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_RECONCILIATION_REPORT
    ]


def _duplicate_employee_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_EMPLOYEE_REGISTER)
    assert register is not None
    register["employees"].append(dict(_employee(payload, "EMP-01")))


def _bad_entity(payload: dict[str, Any]) -> None:
    _employee(payload, "EMP-03")["entity"] = "ENT-ZZ"


def _bad_employee_field(payload: dict[str, Any]) -> None:
    _employee(payload, "EMP-04")["dob"] = "not-a-date"


def _duplicate_plan_code(payload: dict[str, Any]) -> None:
    catalog = _doc(payload, DOC_PLAN_CATALOG)
    assert catalog is not None
    catalog["plans"].append(dict(_plan_row(payload, P_HSA)))


def _bad_plan_type(payload: dict[str, Any]) -> None:
    _plan_row(payload, P_FSA_DEP)["plan_type"] = "cafeteria"


def _unknown_reference(payload: dict[str, Any]) -> None:
    # A deduction to a plan the catalog does not carry; owned solely by ded_refs.
    register = _doc(payload, DOC_DEDUCTION_REGISTER)
    assert register is not None
    register["deductions"].append({"employee_id": "EMP-01", "plan_code": "P-UNKNOWN", "amount_cents": 500})


def _duplicate_deduction_pair(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_DEDUCTION_REGISTER)
    assert register is not None
    register["deductions"].append(dict(_deduction(payload, "EMP-03", P_FSA_MED)))


def _provider_per_employee_mismatch(payload: dict[str, Any]) -> None:
    # Swap two employees' HSA uploads: each mis-keyed, but the plan total is
    # unchanged, so only the per-employee hand-off breaks.
    a = _upload(payload, HSA_ADMIN, P_HSA, "EMP-01")
    b = _upload(payload, HSA_ADMIN, P_HSA, "EMP-05")
    a["amount_cents"], b["amount_cents"] = b["amount_cents"], a["amount_cents"]


def _provider_total_off(payload: dict[str, Any]) -> None:
    # An extra upload answering to no deduction inflates the custodian total.
    doc = _doc(payload, DOC_PROVIDER_FILE)
    assert doc is not None
    doc["uploads"].append(
        {"provider": CUST, "plan_code": P_401K, "employee_id": "EMP-GHOST", "amount_cents": 1_000}
    )


def _je_liability_off(payload: dict[str, Any]) -> None:
    # The HSA accrual is tagged to a neighbouring plan, so the liability credit no
    # longer answers to the HSA register total (the account still nets to zero).
    _je_credit_line(payload, P_HSA)["plan_code"] = "P-HSA-X"


def _cash_transfer_off(payload: dict[str, Any]) -> None:
    _remittance(payload, P_FSA_DEP)["cash_transfer_cents"] -= 1_000


def _entity_subtotal_off(payload: dict[str, Any]) -> None:
    # Move value between two HSA subtotals: the sum still ties the consolidated
    # total, so only the per-entity recompute breaks.
    _subtotal(payload, ENTITY_NW, P_HSA)["subtotal_cents"] += 142
    _subtotal(payload, ENTITY_SW, P_HSA)["subtotal_cents"] -= 142


def _consolidated_off(payload: dict[str, Any]) -> None:
    _consolidated_row(payload, P_FSA_MED)["total_cents"] += 500


def _match_miscomputed(payload: dict[str, Any]) -> None:
    _deduction(payload, "EMP-01", P_MATCH)["amount_cents"] -= 10_000
    rederive(payload)


def _match_over_cap(payload: dict[str, Any]) -> None:
    # The high earner's match is computed on uncapped compensation.
    from .money import apply_rate

    uncapped = apply_rate(_employee(payload, "EMP-04")["eligible_comp_cents"], MATCH_RATE_BPS)
    _deduction(payload, "EMP-04", P_MATCH)["amount_cents"] = uncapped
    rederive(payload)


def _over_402g(payload: dict[str, Any]) -> None:
    _employee(payload, "EMP-03")["prior_ytd"][P_401K] = 2_400_000
    rederive(payload)


def _over_hsa(payload: dict[str, Any]) -> None:
    _employee(payload, "EMP-05")["prior_ytd"][P_HSA] = 800_000
    rederive(payload)


def _over_fsa(payload: dict[str, Any]) -> None:
    _employee(payload, "EMP-01")["prior_ytd"][P_FSA_MED] = 325_000
    rederive(payload)


def _over_415c(payload: dict[str, Any]) -> None:
    _employee(payload, "EMP-02")["prior_ytd"][P_401K] = 6_500_000
    rederive(payload)


def _deferral_watch(payload: dict[str, Any]) -> None:
    # Inside the watch band but under the limit: a review FLAG, not a breach.
    _employee(payload, "EMP-04")["prior_ytd"][P_401K] = 2_820_000
    rederive(payload)


def _hsa_per_period_off(payload: dict[str, Any]) -> None:
    # A cent above the level base, still within the true-up ceiling.
    _deduction(payload, "EMP-05", P_HSA)["amount_cents"] += 1
    rederive(payload)


def _hsa_over_max(payload: dict[str, Any]) -> None:
    _deduction(payload, "EMP-01", P_HSA)["amount_cents"] = 50_000
    rederive(payload)


def _late_deposit(payload: dict[str, Any]) -> None:
    _remittance(payload, P_401K)["remit_date"] = "2031-09-15"


def _remit_before_pay(payload: dict[str, Any]) -> None:
    _remittance(payload, P_HSA)["remit_date"] = "2031-08-25"


def _je_unbalanced(payload: dict[str, Any]) -> None:
    doc = _doc(payload, DOC_JOURNAL_ENTRY)
    assert doc is not None
    doc["lines"].append(
        {"gl_account": "9999-PLUG", "gl_description": "unbalanced plug", "entity": "-", "plan_code": "-", "debit_cents": 100, "credit_cents": 0}
    )


def _clearing_not_zero(payload: dict[str, Any]) -> None:
    # An extra relief debit to the HSA payable, offset to cash so the entry still
    # balances and the accrual credit still ties -- only the payable fails to zero.
    doc = _doc(payload, DOC_JOURNAL_ENTRY)
    assert doc is not None
    doc["lines"].append(
        {"gl_account": _plan(P_HSA)["gl_liability_account"], "gl_description": "HSA contributions payable", "entity": "-", "plan_code": P_HSA, "debit_cents": 100, "credit_cents": 0}
    )
    doc["lines"].append(
        {"gl_account": ACCT_CASH, "gl_description": "Cash - benefit remittances", "entity": "-", "plan_code": "-", "debit_cents": 0, "credit_cents": 100}
    )


def _tie_flag_wrong(payload: dict[str, Any]) -> None:
    # The stated determination contradicts the evidence; only the recompute sees it.
    _report_plan(payload, P_HSA)["tied"] = False


def _watchlist_overstated(payload: dict[str, Any]) -> None:
    _report(payload)["exceptions"].append(
        {"employee_id": "EMP-01", "plan_code": P_401K, "kind": "deferral_over"}
    )


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _deduction(payload, "EMP-01", P_401K)
    row["amount_cents"] = float(row["amount_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_employee_id": ("emp_unique_ids", _duplicate_employee_id),
    "bad_entity": ("emp_entity_valid", _bad_entity),
    "bad_employee_field": ("emp_fields_valid", _bad_employee_field),
    "duplicate_plan_code": ("pln_unique_codes", _duplicate_plan_code),
    "bad_plan_type": ("pln_type_valid", _bad_plan_type),
    "unknown_reference": ("ded_refs_valid", _unknown_reference),
    "duplicate_deduction_pair": ("ded_unique_pairs", _duplicate_deduction_pair),
    "provider_per_employee_mismatch": ("ded_matches_provider", _provider_per_employee_mismatch),
    "provider_total_off": ("tie_provider_total", _provider_total_off),
    "je_liability_off": ("tie_je_liability", _je_liability_off),
    "cash_transfer_off": ("tie_cash_transfer", _cash_transfer_off),
    "entity_subtotal_off": ("ent_subtotal_recomputes", _entity_subtotal_off),
    "consolidated_off": ("ent_consolidated_ties", _consolidated_off),
    "match_miscomputed": ("mat_recomputes", _match_miscomputed),
    "match_over_cap": ("mat_comp_cap", _match_over_cap),
    "over_402g": ("lim_402g_deferral", _over_402g),
    "over_hsa": ("lim_hsa_tier", _over_hsa),
    "over_fsa": ("lim_fsa_cap", _over_fsa),
    "over_415c": ("lim_415c_additions", _over_415c),
    "deferral_watch": ("lim_deferral_watch", _deferral_watch),
    "hsa_per_period_off": ("whh_per_period_recomputes", _hsa_per_period_off),
    "hsa_over_max": ("whh_not_over_max", _hsa_over_max),
    "late_deposit": ("dol_safe_harbor", _late_deposit),
    "remit_before_pay": ("dol_remit_after_pay", _remit_before_pay),
    "je_unbalanced": ("je_balances", _je_unbalanced),
    "clearing_not_zero": ("je_clearing_zeroes", _clearing_not_zero),
    "tie_flag_wrong": ("rpt_tie_status_recomputes", _tie_flag_wrong),
    "watchlist_overstated": ("rpt_exception_watchlist_ties", _watchlist_overstated),
    "amount_not_integer": ("tie_provider_total", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(EMPLOYERS[0])
    clean["file_id"] = f"clean__{EMPLOYERS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        employer = EMPLOYERS[(i + 1) % len(EMPLOYERS)]
        f = baseline(employer)
        f["file_id"] = f"{name}__{employer.replace(' ', '_')}"
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
