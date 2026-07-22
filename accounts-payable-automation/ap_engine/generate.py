"""
Seeded posting-document generator (FICTIONAL DATA ONLY).
========================================================

Builds the corpus the control engine runs against. Every file is one **posting
document set**: a JSON document carrying the five typed source artifacts an
accounts-payable cycle emits for one entity and period.

One set is **clean** and should PASS every rule. Each of the others plants
**exactly one** defect, so every rule in :data:`ap_engine.engine.REGISTRY` has a
matching positive fixture and a matching negative one. A test asserts
``{d.rule for d in DEFECTS} == {rule_id for rule_id, _ in REGISTRY}``, so a rule
cannot be added without a fixture that exercises it.

Determinism
-----------
Every synthetic figure comes from a single :class:`random.Random` seeded with
:data:`SEED` and threaded through as an explicit parameter. There is no
module-level ``random.*`` call anywhere, so the corpus is byte-stable run to run
and a later sub-ledger can take a named derived stream without shifting the
existing sequence.

A sibling ``.xlsx`` is written per document set when :mod:`openpyxl` is
importable. It is a convenience rendering only: ``.xlsx`` is not byte
reproducible (the writer stamps times), so it is gitignored and the determinism
tests compare ``.json`` alone.

Confidentiality
---------------
Every entity, vendor, job, identifier and figure is invented, drawn from the
platform's shared fictional register. No real vendor, entity, person, bank,
document number or path appears anywhere.
"""

from __future__ import annotations

import copy
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import (
    DOC_COMMITMENT_REGISTER,
    DOC_INFORMATION_REPORTING,
    DOC_INVOICE_POSTING,
    DOC_PAYMENT_SELECTION,
    DOC_WORKFLOW_MATRIX,
)
from .money import apply_rate

#: Fixed RNG seed -- guarantees a reproducible corpus.
SEED = 20260731

#: Part number of this engine on the platform.
PART_NO = "SFS-E10-APX"

#: Fictional-future period the whole corpus sits in.
PERIOD = "2026-07"
POSTING_DATE = "2026-07-31"
PAYMENT_DATE = "2026-07-31"
FUNDING_DATE = "2026-07-30"
INSURANCE_EXPIRY = "2026-12-31"
TAX_YEAR = 2026

#: Ledger code the payables control account posts to (fictional).
LEDGER_CODE = "AP-3000"

#: Fictional funding bank.
FUNDING_BANK = "Northgate Demo Bank"

#: Obviously-fictional entity names, shared with the rest of the platform.
ENTITIES: tuple[str, ...] = (
    "Demo Holdings LLC",
    "Maple Fund LP",
    "Birchwood Op Co",
    "Cedar Ridge Trust",
    "Harborview Partners LP",
)

#: Obviously-fictional vendors, in the same register.
VENDORS: tuple[tuple[str, str], ...] = (
    ("VEN-1001", "Ironwood Sandbox Supply Co"),
    ("VEN-1002", "Foxglove Mock Freight LLC"),
    ("VEN-1003", "Harborview Demo Services Inc"),
)

#: A small vendor that stays under the reporting threshold all year.
SMALL_VENDOR: tuple[str, str] = ("VEN-1004", "Birchwood Mock Rentals LLC")

#: Fictional lower-tier subcontractors whose waivers a progress billing needs.
LOWER_TIERS: tuple[str, ...] = ("VEN-2001", "VEN-2002")

#: Fictional role-holders. Never a real person's name.
APPROVERS: tuple[str, ...] = ("approver-a", "approver-b", "approver-c", "approver-d")
CLERKS: tuple[str, ...] = ("clerk-one", "clerk-two", "clerk-three")
REVIEWERS: tuple[str, ...] = ("reviewer-one", "reviewer-two", "reviewer-three")
REVIEW_GROUPS: tuple[str, ...] = ("review-group-one", "review-group-two")

#: Contract minimums every certificate is measured against (fictional cents).
CONTRACT_MINIMUMS: dict[str, int] = {
    "general_liability_cents": 100_000_000,
    "auto_liability_cents": 50_000_000,
    "umbrella_cents": 200_000_000,
}

#: Coverage actually carried on a clean certificate (fictional cents).
CARRIED_COVERAGE: dict[str, int] = {
    "general_liability_cents": 200_000_000,
    "auto_liability_cents": 100_000_000,
    "umbrella_cents": 500_000_000,
}

#: Reporting threshold in integer cents (600.00).
REPORTING_THRESHOLD_CENTS = 60_000

#: Retention and tax rates in integer basis points.
RETENTION_RATE_BPS = 1_000
TAX_RATE_BPS = 875

#: Ceiling an off-cycle payment must stay under, in integer cents.
OFF_CYCLE_LIMIT_CENTS = 2_000_000


@dataclass(frozen=True)
class Defect:
    """Describes a single planted defect (exactly one per registered rule)."""

    key: str  # short slug used in the filename
    rule: str  # rule id the defect must trip
    label: str  # human description


#: One defect per rule in the registry, in registry order, plus a clean baseline
#: generated alongside them.
DEFECTS: tuple[Defect, ...] = (
    Defect("set_incomplete", "set_complete", "document set is missing an artifact type"),
    Defect("proof_nonzero", "post_proof_zero", "posting proof figure is not zero"),
    Defect("gl_recap_out", "post_gl_balanced", "ledger recap debits do not equal credits"),
    Defect("totals_out", "post_totals_balanced", "posting total debit does not equal credit"),
    Defect("rejected_entries", "post_no_rejects", "rejected entry count is not zero"),
    Defect("nothing_posted", "post_actually_posted", "run recorded zero posted documents"),
    Defect("blocking_error", "post_no_error_marker", "blocking batch-contention error marker"),
    Defect("jobcost_drift", "post_jobcost_ties", "job-cost recap does not tie to payable cost"),
    Defect("header_date_drift", "post_header_date_agrees", "header date disagrees with file name"),
    Defect("missing_w9", "gate_w9_on_file", "first payment without a taxpayer certificate"),
    Defect("waiver_gap", "gate_lien_waiver", "lower-tier lien waiver not received"),
    Defect("insurance_expired", "gate_insurance_current", "certificate expired at payment date"),
    Defect("insurance_thin", "gate_insurance_limits", "coverage below the contract minimum"),
    Defect("funding_unconfirmed", "gate_funding_confirmed", "funding not confirmed before release"),
    Defect("duplicate_payment", "gate_no_duplicate", "duplicate vendor, document and amount"),
    Defect("retention_drift", "gate_retention_present", "retention line inconsistent with rate"),
    Defect("offcycle_unapproved", "gate_offcycle_approved", "off-cycle payment without approval"),
    Defect("job_unmapped", "route_every_job_mapped", "active job maps to no workflow"),
    Defect("workflow_no_approver", "route_workflow_has_approver", "workflow has no approver"),
    Defect("no_final_review", "route_final_review_present", "workflow names no final-review group"),
    Defect("duties_merged", "route_duties_segregated", "data entry and final review are one role"),
    Defect("direct_post_undeclared", "route_preapproved_declared", "direct post not enumerated"),
    Defect("threshold_skipped", "ir_threshold_coverage", "vendor over threshold not evaluated"),
    Defect("tin_missing", "ir_tin_present", "reportable vendor without an identifier"),
    Defect("tin_malformed", "ir_tin_structure", "identifier is structurally invalid"),
    Defect("split_vendor", "ir_no_split_vendor", "two vendor records share one identifier"),
    Defect("filed_count_off", "ir_filed_reconciles", "filed-form count does not reconcile"),
    Defect("sov_lump_sum", "cmt_sov_not_lump_sum", "subcontract schedule is a single lump line"),
    Defect("commitment_id_drift", "cmt_id_convention", "commitment identifier breaks convention"),
    Defect("orphan_change_order", "cmt_co_attaches_to_original", "change order has no original"),
)


# --------------------------------------------------------------------------- #
# Clean document construction
# --------------------------------------------------------------------------- #
def _tin(index: int) -> str:
    """Return a structurally valid, obviously-fictional identifier."""
    return f"00-{1_000_000 + index:07d}"


def _payment(
    seq: int,
    index: int,
    vendor: tuple[str, str],
    rng: random.Random,
    *,
    first_payment: bool,
    progress_billing: bool,
    off_cycle: bool,
) -> dict[str, Any]:
    """Build one clean payment line for the selection register."""
    vendor_id, vendor_name = vendor
    gross = rng.randrange(250_000, 900_000, 2_500)
    retention_bps = RETENTION_RATE_BPS if progress_billing else 0
    retention = apply_rate(gross, retention_bps)
    tax = apply_rate(gross - retention, TAX_RATE_BPS)
    amount = gross - retention + tax
    return {
        "payment_id": f"PAY-2026-{seq:02d}{index:02d}",
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "document_number": f"INV-2026-{seq:02d}{index:02d}",
        "purchase_order": f"PO-2026-{seq:02d}{index:02d}",
        "ledger_code": LEDGER_CODE,
        "gross_cents": gross,
        "retention_rate_bps": retention_bps,
        "retention_cents": retention,
        "tax_rate_bps": TAX_RATE_BPS,
        "tax_cents": tax,
        "amount_cents": amount,
        "first_payment": first_payment,
        "w9_on_file": True,
        "progress_billing": progress_billing,
        "lien_waiver": {
            "required": progress_billing,
            "vendor_received": progress_billing,
            "lower_tier_required": list(LOWER_TIERS) if progress_billing else [],
            "lower_tier_received": list(LOWER_TIERS) if progress_billing else [],
        },
        "insurance": {
            "certificate_on_file": True,
            "expires_on": INSURANCE_EXPIRY,
            **CARRIED_COVERAGE,
        },
        "contract_minimums": dict(CONTRACT_MINIMUMS),
        "off_cycle": off_cycle,
        "off_cycle_approval": (
            {"approver": APPROVERS[3], "approved_on": FUNDING_DATE} if off_cycle else None
        ),
        "off_cycle_limit_cents": OFF_CYCLE_LIMIT_CENTS,
    }


def _payment_selection(seq: int, rng: random.Random) -> dict[str, Any]:
    """Build a clean payment selection register."""
    payments = [
        _payment(
            seq, 1, VENDORS[0], rng,
            first_payment=True, progress_billing=True, off_cycle=False,
        ),
        _payment(
            seq, 2, VENDORS[1], rng,
            first_payment=False, progress_billing=False, off_cycle=False,
        ),
        _payment(
            seq, 3, VENDORS[2], rng,
            first_payment=False, progress_billing=False, off_cycle=True,
        ),
    ]
    funded = sum(p["amount_cents"] for p in payments)
    return {
        "doc_type": DOC_PAYMENT_SELECTION,
        "document_id": f"PAYSEL-2026-{seq:04d}",
        "payment_date": PAYMENT_DATE,
        "payment_method": "electronic payment provider",
        "funding": {
            "confirmed": True,
            "confirmed_on": FUNDING_DATE,
            "bank": FUNDING_BANK,
            "amount_cents": funded,
        },
        "payments": payments,
    }


def _invoice_posting(seq: int, selection: dict[str, Any]) -> dict[str, Any]:
    """Build a clean invoice posting report tied to ``selection``."""
    payments = selection["payments"]
    booked = sum(p["amount_cents"] for p in payments)
    job_costed = [p for p in payments if p["progress_billing"]]
    ledger_only = len(payments) - len(job_costed)
    job_cost_total = sum(p["gross_cents"] for p in job_costed)
    stamp = POSTING_DATE.replace("-", "")
    return {
        "doc_type": DOC_INVOICE_POSTING,
        "document_id": f"POST-2026-{seq:04d}",
        "file_name": f"invoice_posting_report_{stamp}_{seq:04d}.json",
        "header_date": POSTING_DATE,
        "ledger_code": LEDGER_CODE,
        "posting_proof_cents": 0,
        "gl_recap": {"debit_cents": booked, "credit_cents": booked},
        "posting_totals": {"debit_cents": booked, "credit_cents": booked},
        "posted_counts": {
            "invoices": len(payments),
            "entries": len(payments) * 2,
            "job_cost_entries": len(job_costed),
        },
        "rejected": {"invoices": 0, "entries": 0, "job_cost_entries": 0},
        "notices": [
            f"job-cost entries not created for {ledger_only} ledger-only invoice(s)",
        ],
        "error_markers": [],
        "job_cost_recap_cents": job_cost_total,
        "payable_cost_total_cents": job_cost_total,
    }


def _workflow_matrix(seq: int) -> dict[str, Any]:
    """Build a clean routing matrix with one declared direct-post workflow."""
    workflows = [
        {
            "workflow_id": "WF-STD-01",
            "approvers": [APPROVERS[0], APPROVERS[1]],
            "final_review_group": REVIEW_GROUPS[0],
            "data_entry_role": CLERKS[0],
            "final_review_role": REVIEWERS[0],
            "direct_post": False,
        },
        {
            "workflow_id": "WF-STD-02",
            "approvers": [APPROVERS[2]],
            "final_review_group": REVIEW_GROUPS[1],
            "data_entry_role": CLERKS[1],
            "final_review_role": REVIEWERS[1],
            "direct_post": False,
        },
        {
            "workflow_id": "WF-DIRECT-01",
            "approvers": [APPROVERS[3]],
            "final_review_group": REVIEW_GROUPS[0],
            "data_entry_role": CLERKS[2],
            "final_review_role": REVIEWERS[2],
            "direct_post": True,
        },
    ]
    jobs = [
        {"job_id": "JOB-2026-0001", "active": True, "workflows": ["WF-STD-01"]},
        {"job_id": "JOB-2026-0002", "active": True, "workflows": ["WF-STD-02"]},
        {"job_id": "JOB-2026-0003", "active": True, "workflows": ["WF-DIRECT-01"]},
        # A closed job legitimately routes nowhere; the control only tests
        # active jobs, and this line proves it.
        {"job_id": "JOB-2025-0009", "active": False, "workflows": []},
    ]
    return {
        "doc_type": DOC_WORKFLOW_MATRIX,
        "document_id": f"ROUTE-2026-{seq:04d}",
        "as_of": POSTING_DATE,
        "jobs": jobs,
        "workflows": workflows,
        "preapproved_direct_post": ["WF-DIRECT-01"],
    }


def _information_reporting(seq: int, entity: str, rng: random.Random) -> dict[str, Any]:
    """Build a clean year-end information-reporting register."""
    vendors: list[dict[str, Any]] = []
    for index, (vendor_id, vendor_name) in enumerate(VENDORS, start=1):
        vendors.append(
            {
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "entity": entity,
                "ytd_paid_cents": rng.randrange(700_000, 3_000_000, 5_000),
                "reportable": True,
                "evaluated": True,
                "tin": _tin(seq * 10 + index),
                "form_filed": True,
            }
        )
    small_id, small_name = SMALL_VENDOR
    # Under the threshold, so the coverage rule must not require an evaluation.
    vendors.append(
        {
            "vendor_id": small_id,
            "vendor_name": small_name,
            "entity": entity,
            "ytd_paid_cents": rng.randrange(5_000, 55_000, 500),
            "reportable": False,
            "evaluated": False,
            "tin": _tin(seq * 10 + len(VENDORS) + 1),
            "form_filed": False,
        }
    )
    return {
        "doc_type": DOC_INFORMATION_REPORTING,
        "document_id": f"IR-2026-{seq:04d}",
        "tax_year": TAX_YEAR,
        "threshold_cents": REPORTING_THRESHOLD_CENTS,
        "vendors": vendors,
        "filed_counts": {entity: len(VENDORS)},
    }


def _commitment(
    job_id: str,
    vendor: tuple[str, str],
    contract_type: str,
    descriptions: tuple[str, ...],
    rng: random.Random,
) -> dict[str, Any]:
    """Build one clean commitment with a schedule of values that foots."""
    vendor_id, vendor_name = vendor
    sov = [
        {
            "line": index,
            "description": description,
            "amount_cents": rng.randrange(150_000, 1_200_000, 5_000),
        }
        for index, description in enumerate(descriptions, start=1)
    ]
    return {
        "commitment_id": f"{job_id}-{vendor_id}-01",
        "job_id": job_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "contract_type": contract_type,
        "amount_cents": sum(line["amount_cents"] for line in sov),
        "schedule_of_values": sov,
        "change_orders": [],
    }


def _commitment_register(seq: int, rng: random.Random) -> dict[str, Any]:
    """Build a clean commitment register with one attached change order."""
    first = _commitment(
        "JOB-2026-0001",
        VENDORS[0],
        "subcontract",
        ("Mobilization", "Rough-in", "Final finish"),
        rng,
    )
    first["change_orders"] = [
        {
            "change_order_id": f"{first['commitment_id']}-CO-01",
            "original_commitment_id": first["commitment_id"],
            "description": "Added scope per owner directive",
            "amount_cents": rng.randrange(20_000, 120_000, 5_000),
        }
    ]
    second = _commitment(
        "JOB-2026-0002",
        VENDORS[1],
        "subcontract",
        ("Haul-off", "Site restoration"),
        rng,
    )
    # A purchase order legitimately carries a single line; the lump-sum control
    # applies to subcontracts only, and this line proves it.
    third = _commitment(
        "JOB-2026-0003",
        VENDORS[2],
        "purchase_order",
        ("Materials release",),
        rng,
    )
    return {
        "doc_type": DOC_COMMITMENT_REGISTER,
        "document_id": f"CMT-2026-{seq:04d}",
        "as_of": POSTING_DATE,
        "commitments": [first, second, third],
    }


def build_document_set(entity: str, seq: int, rng: random.Random) -> dict[str, Any]:
    """Build one clean posting document set for ``entity``.

    Parameters
    ----------
    entity:
        Fictional entity name stamped on the set.
    seq:
        Sequence number, used for the fictional document identifiers.
    rng:
        Seeded RNG. Every figure in the set is drawn from it, in a fixed order.
    """
    selection = _payment_selection(seq, rng)
    return {
        "document_set_id": f"APDS-2026-{seq:04d}",
        "part_no": PART_NO,
        "entity": entity,
        "period": PERIOD,
        "currency": "USD",
        "documents": [
            _invoice_posting(seq, selection),
            selection,
            _workflow_matrix(seq),
            _information_reporting(seq, entity, rng),
            _commitment_register(seq, rng),
        ],
    }


# --------------------------------------------------------------------------- #
# Defect appliers -- each mutates exactly one field, tripping exactly one rule
# --------------------------------------------------------------------------- #
def _doc(packet: dict[str, Any], doc_type: str) -> dict[str, Any]:
    """Return the single document of ``doc_type`` inside ``packet``."""
    for doc in packet["documents"]:
        if doc["doc_type"] == doc_type:
            return doc
    raise KeyError(f"document set carries no {doc_type}")


def _defect_set_incomplete(packet: dict[str, Any]) -> None:
    """Drop an artifact type so the controls that read it cannot run.

    The commitment register is removed rather than corrupted: the point of the
    fixture is that *absent* evidence must not read as a held control. Without
    ``set_complete`` this packet would report PASS on the three ``cmt_*`` rules
    it silently stopped exercising.
    """
    packet["documents"] = [
        doc
        for doc in packet["documents"]
        if doc.get("doc_type") != DOC_COMMITMENT_REGISTER
    ]


def _defect_proof_nonzero(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_INVOICE_POSTING)["posting_proof_cents"] = 2_500


def _defect_gl_recap_out(packet: dict[str, Any]) -> None:
    recap = _doc(packet, DOC_INVOICE_POSTING)["gl_recap"]
    recap["credit_cents"] = recap["credit_cents"] + 5_000


def _defect_totals_out(packet: dict[str, Any]) -> None:
    totals = _doc(packet, DOC_INVOICE_POSTING)["posting_totals"]
    totals["credit_cents"] = totals["credit_cents"] - 7_500


def _defect_rejected_entries(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_INVOICE_POSTING)["rejected"]["entries"] = 2


def _defect_nothing_posted(packet: dict[str, Any]) -> None:
    doc = _doc(packet, DOC_INVOICE_POSTING)
    doc["posted_counts"] = {"invoices": 0, "entries": 0, "job_cost_entries": 0}


def _defect_blocking_error(packet: dict[str, Any]) -> None:
    doc = _doc(packet, DOC_INVOICE_POSTING)
    doc["error_markers"] = ["batch contention on the posting queue - update aborted"]


def _defect_jobcost_drift(packet: dict[str, Any]) -> None:
    doc = _doc(packet, DOC_INVOICE_POSTING)
    doc["job_cost_recap_cents"] = doc["job_cost_recap_cents"] + 1_500


def _defect_header_date_drift(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_INVOICE_POSTING)["header_date"] = "2026-06-30"


def _defect_missing_w9(packet: dict[str, Any]) -> None:
    for payment in _doc(packet, DOC_PAYMENT_SELECTION)["payments"]:
        if payment["first_payment"]:
            payment["w9_on_file"] = False
            return


def _defect_waiver_gap(packet: dict[str, Any]) -> None:
    for payment in _doc(packet, DOC_PAYMENT_SELECTION)["payments"]:
        waiver = payment["lien_waiver"]
        if waiver["required"]:
            waiver["lower_tier_received"] = waiver["lower_tier_received"][:-1]
            return


def _defect_insurance_expired(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_PAYMENT_SELECTION)["payments"][0]["insurance"]["expires_on"] = "2026-06-30"


def _defect_insurance_thin(packet: dict[str, Any]) -> None:
    payment = _doc(packet, DOC_PAYMENT_SELECTION)["payments"][1]
    minimum = payment["contract_minimums"]["general_liability_cents"]
    payment["insurance"]["general_liability_cents"] = minimum // 2


def _defect_funding_unconfirmed(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_PAYMENT_SELECTION)["funding"]["confirmed"] = False


def _defect_duplicate_payment(packet: dict[str, Any]) -> None:
    doc = _doc(packet, DOC_PAYMENT_SELECTION)
    twin = copy.deepcopy(doc["payments"][0])
    twin["payment_id"] = f"{twin['payment_id']}-B"
    doc["payments"].append(twin)


def _defect_retention_drift(packet: dict[str, Any]) -> None:
    for payment in _doc(packet, DOC_PAYMENT_SELECTION)["payments"]:
        if payment["progress_billing"]:
            payment["retention_cents"] = payment["retention_cents"] + 1_500
            return


def _defect_offcycle_unapproved(packet: dict[str, Any]) -> None:
    for payment in _doc(packet, DOC_PAYMENT_SELECTION)["payments"]:
        if payment["off_cycle"]:
            payment["off_cycle_approval"] = None
            return


def _defect_job_unmapped(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_WORKFLOW_MATRIX)["jobs"][0]["workflows"] = []


def _defect_workflow_no_approver(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_WORKFLOW_MATRIX)["workflows"][0]["approvers"] = []


def _defect_no_final_review(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_WORKFLOW_MATRIX)["workflows"][1]["final_review_group"] = ""


def _defect_duties_merged(packet: dict[str, Any]) -> None:
    workflow = _doc(packet, DOC_WORKFLOW_MATRIX)["workflows"][1]
    workflow["final_review_role"] = workflow["data_entry_role"]


def _defect_direct_post_undeclared(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_WORKFLOW_MATRIX)["preapproved_direct_post"] = []


def _defect_threshold_skipped(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_INFORMATION_REPORTING)["vendors"][0]["evaluated"] = False


def _defect_tin_missing(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_INFORMATION_REPORTING)["vendors"][1]["tin"] = ""


def _defect_tin_malformed(packet: dict[str, Any]) -> None:
    _doc(packet, DOC_INFORMATION_REPORTING)["vendors"][2]["tin"] = "000000001"


def _defect_split_vendor(packet: dict[str, Any]) -> None:
    doc = _doc(packet, DOC_INFORMATION_REPORTING)
    original = doc["vendors"][0]
    doc["vendors"].append(
        {
            "vendor_id": "VEN-1091",
            "vendor_name": f"{original['vendor_name']} - remit-to two",
            "entity": original["entity"],
            "ytd_paid_cents": 42_500,
            "reportable": False,
            "evaluated": True,
            "tin": original["tin"],
            "form_filed": False,
        }
    )


def _defect_filed_count_off(packet: dict[str, Any]) -> None:
    doc = _doc(packet, DOC_INFORMATION_REPORTING)
    entity = packet["entity"]
    doc["filed_counts"][entity] = doc["filed_counts"][entity] - 1


def _defect_sov_lump_sum(packet: dict[str, Any]) -> None:
    commitment = _doc(packet, DOC_COMMITMENT_REGISTER)["commitments"][0]
    commitment["schedule_of_values"] = [
        {
            "line": 1,
            "description": "Contract lump sum",
            "amount_cents": commitment["amount_cents"],
        }
    ]


def _defect_commitment_id_drift(packet: dict[str, Any]) -> None:
    # The second commitment carries no change orders, so re-labelling it cannot
    # detach one and trip a second rule.
    _doc(packet, DOC_COMMITMENT_REGISTER)["commitments"][1]["commitment_id"] = "CMT-0002"


def _defect_orphan_change_order(packet: dict[str, Any]) -> None:
    commitment = _doc(packet, DOC_COMMITMENT_REGISTER)["commitments"][0]
    commitment["change_orders"][0]["original_commitment_id"] = "JOB-2026-0099-VEN-1099-01"


#: Defect key -> the mutation that plants it. Every key in :data:`DEFECTS` has
#: an entry, and a test asserts the two stay in step.
DEFECT_APPLIERS: dict[str, Callable[[dict[str, Any]], None]] = {
    "set_incomplete": _defect_set_incomplete,
    "proof_nonzero": _defect_proof_nonzero,
    "gl_recap_out": _defect_gl_recap_out,
    "totals_out": _defect_totals_out,
    "rejected_entries": _defect_rejected_entries,
    "nothing_posted": _defect_nothing_posted,
    "blocking_error": _defect_blocking_error,
    "jobcost_drift": _defect_jobcost_drift,
    "header_date_drift": _defect_header_date_drift,
    "missing_w9": _defect_missing_w9,
    "waiver_gap": _defect_waiver_gap,
    "insurance_expired": _defect_insurance_expired,
    "insurance_thin": _defect_insurance_thin,
    "funding_unconfirmed": _defect_funding_unconfirmed,
    "duplicate_payment": _defect_duplicate_payment,
    "retention_drift": _defect_retention_drift,
    "offcycle_unapproved": _defect_offcycle_unapproved,
    "job_unmapped": _defect_job_unmapped,
    "workflow_no_approver": _defect_workflow_no_approver,
    "no_final_review": _defect_no_final_review,
    "duties_merged": _defect_duties_merged,
    "direct_post_undeclared": _defect_direct_post_undeclared,
    "threshold_skipped": _defect_threshold_skipped,
    "tin_missing": _defect_tin_missing,
    "tin_malformed": _defect_tin_malformed,
    "split_vendor": _defect_split_vendor,
    "filed_count_off": _defect_filed_count_off,
    "sov_lump_sum": _defect_sov_lump_sum,
    "commitment_id_drift": _defect_commitment_id_drift,
    "orphan_change_order": _defect_orphan_change_order,
}


def apply_defect(packet: dict[str, Any], defect: Defect) -> None:
    """Plant ``defect`` into ``packet`` in place.

    Raises:
        ValueError: If the defect has no registered applier.
    """
    applier = DEFECT_APPLIERS.get(defect.key)
    if applier is None:
        raise ValueError(f"no applier registered for defect key {defect.key!r}")
    applier(packet)


# --------------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------------- #
def _slug(entity: str) -> str:
    """Filename-safe slug for a fictional entity name."""
    return entity.replace(" ", "_")


def _flatten(prefix: str, value: object, rows: list[tuple[str, str]]) -> None:
    """Flatten nested JSON into ``(path, text)`` rows for the xlsx rendering."""
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten(f"{prefix}.{key}" if prefix else str(key), value[key], rows)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten(f"{prefix}[{index}]", item, rows)
    else:
        rows.append((prefix, "" if value is None else str(value)))


def _write_xlsx(packet: dict[str, Any], path: Path) -> Path | None:
    """Write a convenience workbook rendering of ``packet``, if possible.

    Returns the path written, or ``None`` when :mod:`openpyxl` is unavailable.
    The workbook is never byte-compared: the writer stamps times, so ``.xlsx``
    is not reproducible and is gitignored.
    """
    try:
        from openpyxl import Workbook
    except ImportError:  # pragma: no cover - openpyxl is a declared dependency
        return None

    wb = Workbook()
    index_ws = wb.active
    index_ws.title = "Document Set"
    index_ws.append(["Field", "Value"])
    for key in sorted(packet):
        if key == "documents":
            continue
        index_ws.append([key, str(packet[key])])
    index_ws.append(["documents", str(len(packet["documents"]))])

    for doc in packet["documents"]:
        title = str(doc["doc_type"])[:31]
        ws = wb.create_sheet(title)
        ws.append(["Path", "Value"])
        rows: list[tuple[str, str]] = []
        _flatten("", doc, rows)
        for row in rows:
            ws.append(list(row))
    wb.save(path)
    return path


def generate_corpus(out_dir: Path | str, *, seed: int = SEED) -> list[Path]:
    """Generate the full corpus into ``out_dir`` (created if needed).

    Writes one clean document set plus one set per planted defect. Stale
    ``.json`` and ``.xlsx`` artifacts from an earlier run are removed first so an
    older schema cannot contaminate the corpus; lock files starting ``~$`` are
    left alone.

    Returns the list of written ``.json`` paths, in write order.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    for stale in sorted(
        (*out.glob("*.json"), *out.glob("*.xlsx")), key=lambda p: p.name
    ):
        if not stale.name.startswith("~$"):
            stale.unlink()

    rng = random.Random(seed)

    plans: list[tuple[str, Defect | None]] = [(ENTITIES[0], None)]
    for index, defect in enumerate(DEFECTS, start=1):
        plans.append((ENTITIES[index % len(ENTITIES)], defect))

    written: list[Path] = []
    for seq, (entity, defect) in enumerate(plans, start=1):
        key = defect.key if defect else "clean"
        packet = build_document_set(entity, seq, rng)
        if defect is not None:
            apply_defect(packet, defect)
        stem = f"{key}__{_slug(entity)}"
        json_path = out / f"{stem}.json"
        json_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        _write_xlsx(packet, out / f"{stem}.xlsx")
        written.append(json_path)
    return written


if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent
    target = here / "samples"
    paths = generate_corpus(target)
    print(f"Wrote {len(paths)} fictional posting document set(s) to {target}:")
    for path in paths:
        print("  -", path.name)
    print("\nNow run:  python -m ap_engine ./samples")
