"""
Fictional warranty claim-file generator.
========================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect.

Everything here is invented. The projects, insurer, vendors, units and invoice
numbers are fictional and the periods are set in a fictional future. No real
policy, person, entity, bank or path appears anywhere. The generator is
deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only construction cost, the two policy rates, and the repair events are stated.
Premium, coverage limit, policy end date, every quarterly subtotal, the
cumulative total, coverage remaining, the cost ledger and the claim submission
are all computed from them -- so the derivation chain the engine checks is the
same chain that produced the data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .model import (
    DOC_CLAIMS_HISTORY,
    DOC_CLAIM_SUBMISSION,
    DOC_CLOSED_UNITS,
    DOC_COST_LEDGER,
    DOC_POLICY,
    WARRANTY_COST_CODES,
)
from .money import apply_rate

PROJECTS: tuple[str, ...] = (
    "Alderpoint Terraces",
    "Brightwater Commons",
    "Copperfield Yards",
    "Dunmore Flats",
)
INSURER = "Northmarch Sandbox Casualty SPC"
INSURED = "Alderpoint Terraces Holdings LLC"
APPROVER = "R. Castellanos"

CONSTRUCTION_COST = 6_957_699_00      # cents
PREMIUM_RATE_BPS = 150                # 1.50% of construction cost
COVERAGE_MULTIPLE_BPS = 13000         # 130.00% of premium
POLICY_START = date(2027, 6, 1)
POLICY_MONTHS = 18
CURRENT_PERIOD = "2028-Q2"

#: ``(unit, close_date)`` -- warranty coverage begins here.
UNITS: tuple[tuple[str, str], ...] = (
    ("U-04", "2027-06-14"),
    ("U-07", "2027-06-16"),
    ("U-11", "2027-05-27"),
    ("U-15", "2027-07-02"),
    ("U-18", "2027-08-19"),
)

#: ``(period, from, to)`` -- the quarterly reporting windows filed so far.
PERIODS: tuple[tuple[str, str, str], ...] = (
    ("2027-Q3", "2027-07-01", "2027-09-30"),
    ("2027-Q4", "2027-10-01", "2027-12-31"),
    ("2028-Q1", "2028-01-01", "2028-03-31"),
    ("2028-Q2", "2028-04-01", "2028-06-30"),
)

#: ``(period, claim_no, unit, vendor, invoice, date, description, dollars)``
REPAIRS: tuple[tuple[str, int, str, str, str, str, str, float], ...] = (
    ("2027-Q3", 1, "U-04", "Rosewater Plumbing", "RP-4412", "2027-07-19",
     "sink supply line leak, kitchen", 1_240),
    ("2027-Q3", 2, "U-11", "Halloway Electrical", "HE-2210", "2027-08-03",
     "failed GFCI circuit, garage", 860),
    ("2027-Q4", 1, "U-07", "Rosewater Plumbing", "RP-4630", "2027-11-08",
     "shower diverter replacement", 1_575),
    ("2028-Q1", 1, "U-15", "Bellhaven Glazing", "BG-0912", "2028-02-14",
     "sealed unit failure, living room", 2_310),
    ("2028-Q1", 2, "U-04", "Halloway Electrical", "HE-2455", "2028-03-02",
     "dimmer module replacement", 495),
    ("2028-Q2", 1, "U-18", "Rosewater Plumbing", "RP-5104", "2028-04-22",
     "hot water recirculation pump", 3_180),
    ("2028-Q2", 2, "U-11", "Cranbrook Millwork", "CM-1180", "2028-05-30",
     "cabinet door realignment", 640),
)


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


def _premium() -> int:
    return apply_rate(CONSTRUCTION_COST, PREMIUM_RATE_BPS)


def _coverage_limit() -> int:
    return apply_rate(_premium(), COVERAGE_MULTIPLE_BPS)


def _policy_end() -> date:
    y = POLICY_START.year + (POLICY_START.month - 1 + POLICY_MONTHS) // 12
    m = (POLICY_START.month - 1 + POLICY_MONTHS) % 12 + 1
    return date(y, m, POLICY_START.day)


def _period_subtotal(period: str) -> int:
    return sum(d(r[7]) for r in REPAIRS if r[0] == period)


def _cumulative() -> int:
    return sum(d(r[7]) for r in REPAIRS)


# --------------------------------------------------------------------------- #
# Artifact builders
# --------------------------------------------------------------------------- #
def _policy() -> dict[str, Any]:
    return {
        "doc_type": DOC_POLICY,
        "document_id": f"POL-{POLICY_START.year}-0001",
        "insurer": INSURER,
        "insured_entity": INSURED,
        "construction_cost_cents": CONSTRUCTION_COST,
        "premium_rate_bps": PREMIUM_RATE_BPS,
        "premium_cents": _premium(),
        "coverage_multiple_bps": COVERAGE_MULTIPLE_BPS,
        "coverage_limit_cents": _coverage_limit(),
        "policy_start": POLICY_START.isoformat(),
        "policy_end": _policy_end().isoformat(),
        "policy_months": POLICY_MONTHS,
    }


def _claim_submission() -> dict[str, Any]:
    cumulative = _cumulative()
    return {
        "doc_type": DOC_CLAIM_SUBMISSION,
        "document_id": f"CLM-{CURRENT_PERIOD}",
        "period": CURRENT_PERIOD,
        "claim_date": "2028-06-30",
        "reimbursement_requested_cents": _period_subtotal(CURRENT_PERIOD),
        "cumulative_reimbursement_cents": cumulative,
        "coverage_remaining_cents": _coverage_limit() - cumulative,
        "remit_to_entity": INSURED,
        "remit_bank_name": "Meridian Sandbox Bank, N.A.",
        "remit_account_reference": "ACCT-REF-0041",
        "remit_routing_reference": "RTG-REF-0007",
        "approved_by": APPROVER,
        "approval_date": "2028-07-05",
    }


def _claims_history() -> dict[str, Any]:
    periods = []
    for label, start, end in PERIODS:
        claims = [
            {
                "claim_no": no,
                "unit": unit,
                "vendor": vendor,
                "invoice_number": invoice,
                "claim_date": when,
                "description": desc,
                "amount_cents": d(amount),
            }
            for (p, no, unit, vendor, invoice, when, desc, amount) in REPAIRS
            if p == label
        ]
        periods.append({
            "period": label,
            "from_date": start,
            "to_date": end,
            "claims": claims,
            "subtotal_cents": sum(c["amount_cents"] for c in claims),
        })
    return {
        "doc_type": DOC_CLAIMS_HISTORY,
        "document_id": f"HIS-{CURRENT_PERIOD}",
        "periods": periods,
    }


def _cost_ledger() -> dict[str, Any]:
    txns = []
    for i, (_p, _no, unit, vendor, invoice, when, desc, amount) in enumerate(REPAIRS):
        repaired = date.fromisoformat(when)
        txns.append({
            "job": "2170-08",
            "cost_code": WARRANTY_COST_CODES[i % len(WARRANTY_COST_CODES)],
            "unit": unit,
            "transaction_type": "AP invoice",
            "transaction_date": when,
            # Posted a few days after the work, still inside the window.
            "accounting_date": (repaired + timedelta(days=4)).isoformat(),
            "description": desc,
            "vendor": vendor,
            "invoice_number": invoice,
            "amount_cents": d(amount),
        })
    return {
        "doc_type": DOC_COST_LEDGER,
        "document_id": f"LDG-{CURRENT_PERIOD}",
        "from_date": PERIODS[0][1],
        "to_date": PERIODS[-1][2],
        "transactions": txns,
    }


def _closed_units() -> dict[str, Any]:
    return {
        "doc_type": DOC_CLOSED_UNITS,
        "document_id": f"UNT-{CURRENT_PERIOD}",
        "units": [
            {"unit": unit, "buyer": f"Buyer {unit[-2:]}", "close_date": when}
            for unit, when in UNITS
        ],
    }


def baseline(project: str) -> dict[str, Any]:
    """A complete, internally consistent claim file that passes every control."""
    return {
        "file_id": f"{project.replace(' ', '_')}__{CURRENT_PERIOD}",
        "project": project,
        "period": CURRENT_PERIOD,
        "insurer": INSURER,
        "documents": [
            _policy(),
            _claim_submission(),
            _claims_history(),
            _cost_ledger(),
            _closed_units(),
        ],
    }


# --------------------------------------------------------------------------- #
# Defect mutations
# --------------------------------------------------------------------------- #
def _doc(f: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(x for x in f["documents"] if x["doc_type"] == doc_type)


def _period(f: dict[str, Any], label: str) -> dict[str, Any]:
    return next(p for p in _doc(f, DOC_CLAIMS_HISTORY)["periods"]
                if p["period"] == label)


def _resync(f: dict[str, Any]) -> None:
    """Recompute the submission from the history, so only one thing is wrong."""
    hist = _doc(f, DOC_CLAIMS_HISTORY)
    sub = _doc(f, DOC_CLAIM_SUBMISSION)
    pol = _doc(f, DOC_POLICY)
    cumulative = sum(p["subtotal_cents"] for p in hist["periods"])
    current = next((p for p in hist["periods"] if p["period"] == CURRENT_PERIOD), None)
    sub["cumulative_reimbursement_cents"] = cumulative
    sub["coverage_remaining_cents"] = pol["coverage_limit_cents"] - cumulative
    if current is not None:
        sub["reimbursement_requested_cents"] = current["subtotal_cents"]


def _drop_document(f: dict[str, Any]) -> None:
    f["documents"] = [x for x in f["documents"] if x["doc_type"] != DOC_CLOSED_UNITS]


def _bad_period_label(f: dict[str, Any]) -> None:
    f["period"] = "2028-06"


def _premium_off(f: dict[str, Any]) -> None:
    _doc(f, DOC_POLICY)["premium_cents"] += d(1_500)


def _coverage_off(f: dict[str, Any]) -> None:
    _doc(f, DOC_POLICY)["coverage_limit_cents"] += d(9_000)


def _policy_end_off(f: dict[str, Any]) -> None:
    _doc(f, DOC_POLICY)["policy_end"] = "2028-11-01"


def _over_limit(f: dict[str, Any]) -> None:
    # One very large repair pushes cumulative past the pool.
    p = _period(f, CURRENT_PERIOD)
    p["claims"].append({
        "claim_no": 9, "unit": "U-15", "vendor": "Bellhaven Glazing",
        "invoice_number": "BG-1440", "claim_date": "2028-06-11",
        "description": "curtain wall remediation", "amount_cents": d(140_000),
    })
    p["subtotal_cents"] = sum(c["amount_cents"] for c in p["claims"])
    _doc(f, DOC_COST_LEDGER)["transactions"].append({
        "job": "2170-08", "cost_code": WARRANTY_COST_CODES[0], "unit": "U-15",
        "transaction_type": "AP invoice", "transaction_date": "2028-06-11",
        "accounting_date": "2028-06-15", "description": "curtain wall remediation",
        "vendor": "Bellhaven Glazing", "invoice_number": "BG-1440",
        "amount_cents": d(140_000),
    })
    _resync(f)


def _remaining_off(f: dict[str, Any]) -> None:
    _doc(f, DOC_CLAIM_SUBMISSION)["coverage_remaining_cents"] -= d(750)


def _nearly_exhausted(f: dict[str, Any]) -> None:
    sub = _doc(f, DOC_CLAIM_SUBMISSION)
    limit = _doc(f, DOC_POLICY)["coverage_limit_cents"]
    sub["cumulative_reimbursement_cents"] = limit - d(4_000)
    sub["coverage_remaining_cents"] = d(4_000)


def _subtotal_off(f: dict[str, Any]) -> None:
    _period(f, "2028-Q1")["subtotal_cents"] += d(300)


def _cumulative_off(f: dict[str, Any]) -> None:
    _doc(f, DOC_CLAIM_SUBMISSION)["cumulative_reimbursement_cents"] += d(1_100)


def _request_off(f: dict[str, Any]) -> None:
    _doc(f, DOC_CLAIM_SUBMISSION)["reimbursement_requested_cents"] += d(220)


def _claim_outside_quarter(f: dict[str, Any]) -> None:
    _period(f, "2028-Q1")["claims"][0]["claim_date"] = "2028-04-09"


def _claim_outside_policy(f: dict[str, Any]) -> None:
    p = _period(f, CURRENT_PERIOD)
    p["from_date"] = "2028-04-01"
    p["to_date"] = "2029-06-30"
    p["claims"][0]["claim_date"] = "2029-02-11"
    _doc(f, DOC_COST_LEDGER)["transactions"][5]["transaction_date"] = "2029-02-11"


def _duplicate_invoice(f: dict[str, Any]) -> None:
    p = _period(f, CURRENT_PERIOD)
    dup = dict(_period(f, "2027-Q3")["claims"][0])
    dup["claim_no"] = 8
    dup["claim_date"] = "2028-05-14"
    p["claims"].append(dup)
    p["subtotal_cents"] = sum(c["amount_cents"] for c in p["claims"])
    _resync(f)


def _claim_without_cost(f: dict[str, Any]) -> None:
    _period(f, CURRENT_PERIOD)["claims"][0]["invoice_number"] = "RP-9999"


def _claim_amount_mismatch(f: dict[str, Any]) -> None:
    _doc(f, DOC_COST_LEDGER)["transactions"][6]["amount_cents"] -= d(90)


def _wrong_cost_code(f: dict[str, Any]) -> None:
    _doc(f, DOC_COST_LEDGER)["transactions"][2]["cost_code"] = "12-400"


def _accounting_outside_window(f: dict[str, Any]) -> None:
    _doc(f, DOC_COST_LEDGER)["transactions"][1]["accounting_date"] = "2029-01-10"


def _unit_not_closed(f: dict[str, Any]) -> None:
    units = _doc(f, DOC_CLOSED_UNITS)
    units["units"] = [u for u in units["units"] if u["unit"] != "U-18"]


def _claim_before_close(f: dict[str, Any]) -> None:
    _doc(f, DOC_CLOSED_UNITS)["units"][4]["close_date"] = "2028-05-01"


def _wrong_remittee(f: dict[str, Any]) -> None:
    _doc(f, DOC_CLAIM_SUBMISSION)["remit_to_entity"] = "Alderpoint Services LLC"


def _bank_details_missing(f: dict[str, Any]) -> None:
    _doc(f, DOC_CLAIM_SUBMISSION)["remit_routing_reference"] = ""


def _unapproved(f: dict[str, Any]) -> None:
    _doc(f, DOC_CLAIM_SUBMISSION)["approved_by"] = ""


def _amount_not_integer(f: dict[str, Any]) -> None:
    _period(f, "2027-Q3")["claims"][0]["amount_cents"] = 124000.5


#: ``name -> (rule the file is built to trip, mutation)``
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _drop_document),
    "bad_period_label": ("set_period_label", _bad_period_label),
    "premium_off": ("pol_premium_derived_from_cost", _premium_off),
    "coverage_off": ("pol_coverage_derived_from_premium", _coverage_off),
    "policy_end_off": ("pol_period_length", _policy_end_off),
    "over_limit": ("pol_cumulative_within_limit", _over_limit),
    "remaining_off": ("pol_remaining_is_limit_less_cumulative", _remaining_off),
    "nearly_exhausted": ("pol_coverage_not_nearly_exhausted", _nearly_exhausted),
    "subtotal_off": ("clm_period_subtotals_foot", _subtotal_off),
    "cumulative_off": ("clm_cumulative_is_sum_of_periods", _cumulative_off),
    "request_off": ("clm_request_matches_current_period", _request_off),
    "claim_outside_quarter": ("clm_claim_inside_its_period", _claim_outside_quarter),
    "claim_outside_policy": ("clm_claim_inside_policy_period", _claim_outside_policy),
    "duplicate_invoice": ("clm_no_duplicate_invoice", _duplicate_invoice),
    "claim_without_cost": ("cost_claim_traces_to_ledger", _claim_without_cost),
    "claim_amount_mismatch": ("cost_claim_traces_to_ledger", _claim_amount_mismatch),
    "wrong_cost_code": ("cost_uses_warranty_cost_code", _wrong_cost_code),
    "accounting_outside_window": ("cost_accounting_date_inside_period",
                                  _accounting_outside_window),
    "unit_not_closed": ("unit_claim_unit_has_closed", _unit_not_closed),
    "claim_before_close": ("unit_claim_after_close", _claim_before_close),
    "wrong_remittee": ("rem_insured_entity_matches", _wrong_remittee),
    "bank_details_missing": ("rem_bank_details_present", _bank_details_missing),
    "unapproved": ("rem_submission_approved", _unapproved),
    "amount_not_integer": ("clm_period_subtotals_foot", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PROJECTS[0])
    clean["file_id"] = f"clean__{PROJECTS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        project = PROJECTS[(i + 1) % len(PROJECTS)]
        f = baseline(project)
        f["file_id"] = f"{name}__{project.replace(' ', '_')}"
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
