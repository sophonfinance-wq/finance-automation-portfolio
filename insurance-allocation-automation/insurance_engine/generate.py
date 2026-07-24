"""
Fictional insurance-programme corpus generator.
===============================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The programmes, the carriers, the projects, the
policy numbers, the premiums and every basis value are fictional, and the policy
year is set in a fictional future. No real entity, person, carrier, project or
path appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the projects, the policies, and the audits are stated as base facts. Every
figure the engine later checks as a tie-out -- each project's share of every
premium, the reallocation of each audit true-up, what lands on job cost, the
per-unit metric, the prepaid balance and the programme total -- is recomputed by
:func:`rederive` from those base facts, using the *same* largest-remainder
primitive the engine re-derives with. So the relationships the engine tests are
the relationships that produced the data: a defect that changes a base fact
re-derives everything downstream and keeps the break confined to one control; a
defect that targets a stated tie-out edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .allocation import basis_weights_bps
from .model import (
    BASIS_HARD_COST,
    BASIS_INSURED_VALUE,
    DOC_ALLOCATION_SCHEDULE,
    DOC_ALLOCATION_SUMMARY,
    DOC_AUDIT_REGISTER,
    DOC_GL_POSITIONS,
    DOC_JOB_COST_LEDGER,
    DOC_POLICY_REGISTER,
    DOC_PROJECT_REGISTER,
    LAYER_EXCESS,
    LAYER_PRIMARY,
    LINE_BUILDERS_RISK,
    LINE_EXCESS,
    LINE_GENERAL_LIABILITY,
    STAGE_COMPLETE,
    STAGE_DEVELOPMENT,
)
from .money import allocate_by_ratio

#: Fictional programme labels, rotated for file identity only.
PROGRAMMES: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

POLICY_YEAR = "PY2029"
#: The review date every prepaid amortisation and ageing test is measured to.
AS_OF = "2029-10-01"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(code, name, stage, hard_cost_cents, insured_value_cents, unit_count,
#:   construction_start, construction_end)``. Insured value tracks the hard-cost
#: budget in the baseline, so the tolerant builder's-risk control has nothing to
#: flag; a defect widens the gap on purpose.
PROJECTS: tuple[tuple[Any, ...], ...] = (
    ("PRJ-101", "Brightwater Commons", STAGE_DEVELOPMENT, d(4_800_000), d(4_800_000), 40, "2029-08-01", "2030-05-01"),
    ("PRJ-102", "Copperfield Yards",   STAGE_DEVELOPMENT, d(3_600_000), d(3_600_000), 30, "2029-08-15", "2030-06-01"),
    ("PRJ-103", "Alderpoint Terraces", STAGE_DEVELOPMENT, d(2_400_000), d(2_400_000), 24, "2029-09-01", "2030-04-15"),
    # Complete, and deliberately off the builder's risk schedule.
    ("PRJ-104", "Dunmore Flats",       STAGE_COMPLETE,     d(1_800_000), d(1_800_000), 18, "2028-03-01", "2029-05-01"),
)

_ALL_PROJECTS = ("PRJ-101", "PRJ-102", "PRJ-103", "PRJ-104")
_DEVELOPMENT_PROJECTS = ("PRJ-101", "PRJ-102", "PRJ-103")

#: ``(policy_no, line, layer, carrier, inception, expiration, premium_cents,
#:   allocation_basis, covered_projects, limit_cents, attaches_over,
#:   attachment_point_cents, value_tolerance_bps)``. The GL primary runs as a
#: renewal pair (a prior term abutting the current one) so the continuity control
#: has a real handover to check; the prior term is fully earned by the review
#: date and drops out of the prepaid.
POLICIES: tuple[tuple[Any, ...], ...] = (
    ("GL-2028", LINE_GENERAL_LIABILITY, LAYER_PRIMARY, "Meridian Casualty", "2028-07-01", "2029-07-01", d(210_000), BASIS_HARD_COST, _ALL_PROJECTS, d(5_000_000), None, 0, 0),
    ("GL-2029", LINE_GENERAL_LIABILITY, LAYER_PRIMARY, "Meridian Casualty", "2029-07-01", "2030-07-01", d(234_000), BASIS_HARD_COST, _ALL_PROJECTS, d(5_000_000), None, 0, 0),
    ("XS-2029", LINE_EXCESS,            LAYER_EXCESS,   "Continental Re",    "2029-07-01", "2030-07-01", d(96_000),  BASIS_HARD_COST, _ALL_PROJECTS, d(10_000_000), "GL-2029", d(5_000_000), 0),
    ("BR-2029", LINE_BUILDERS_RISK,     LAYER_PRIMARY,  "Harborline Specialty", "2029-07-01", "2030-07-01", d(72_000), BASIS_INSURED_VALUE, _DEVELOPMENT_PROJECTS, 0, None, 0, 1000),
)

#: ``(audit_no, policy_no, audit_type, amount_cents)``. The reallocation, its
#: deposit basis and the restated final exposure are all derived from the audited
#: policy's own allocation.
AUDITS: tuple[tuple[Any, ...], ...] = (
    ("AUD-2028", "GL-2028", "additional", d(18_000)),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _policy(payload: dict[str, Any], policy_no: str) -> dict[str, Any]:
    register = _doc(payload, DOC_POLICY_REGISTER)
    assert register is not None
    for row in register["policies"]:
        if row.get("policy_no") == policy_no:
            return row
    raise KeyError(policy_no)


def _project(payload: dict[str, Any], code: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PROJECT_REGISTER)
    assert register is not None
    for row in register["projects"]:
        if row.get("code") == code:
            return row
    raise KeyError(code)


def _alloc(payload: dict[str, Any], policy_no: str, code: str) -> dict[str, Any]:
    schedule = _doc(payload, DOC_ALLOCATION_SCHEDULE)
    assert schedule is not None
    for row in schedule["allocations"]:
        if row.get("policy_no") == policy_no and row.get("project_code") == code:
            return row
    raise KeyError((policy_no, code))


def _audit(payload: dict[str, Any], audit_no: str) -> dict[str, Any]:
    register = _doc(payload, DOC_AUDIT_REGISTER)
    assert register is not None
    for row in register["audits"]:
        if row.get("audit_no") == audit_no:
            return row
    raise KeyError(audit_no)


def _realloc(payload: dict[str, Any], audit_no: str, code: str) -> dict[str, Any]:
    for row in _audit(payload, audit_no)["reallocation"]:
        if row.get("project_code") == code:
            return row
    raise KeyError((audit_no, code))


def _posting(payload: dict[str, Any], code: str) -> dict[str, Any]:
    ledger = _doc(payload, DOC_JOB_COST_LEDGER)
    assert ledger is not None
    for row in ledger["postings"]:
        if row.get("project_code") == code:
            return row
    raise KeyError(code)


def _summary(payload: dict[str, Any], code: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_ALLOCATION_SUMMARY)
    assert summary is not None
    for row in summary["projects"]:
        if row.get("project_code") == code:
            return row
    raise KeyError(code)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def derive_shares(premium_cents: int, basis_values: list[int]) -> list[int]:
    """The allocation every control compares against.

    Values become integer basis-point weights, weights become integer cents, both
    by largest remainder -- defined once so the engine and generator cannot drift
    on the residual cent.
    """
    return allocate_by_ratio(premium_cents, basis_weights_bps(basis_values))


def prepaid_unearned(policies: list[dict[str, Any]], as_of: date) -> int:
    """Straight-line unearned premium across each policy term to ``as_of``.

    Replicates :func:`insurance_engine.engine.check_gl_prepaid_amortisation_ties`
    exactly, so the derived baseline ties the control to the cent.
    """
    derived = 0
    for policy in policies:
        inception = date.fromisoformat(policy["inception_date"])
        expiration = date.fromisoformat(policy["expiration_date"])
        if expiration <= inception:
            continue
        span = (expiration - inception).days
        remaining = (expiration - as_of).days
        if remaining <= 0:
            continue
        remaining = min(remaining, span)
        derived += policy["premium_cents"] * remaining // span
    return derived


def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    projects_doc = _doc(payload, DOC_PROJECT_REGISTER)
    policy_doc = _doc(payload, DOC_POLICY_REGISTER)
    schedule = _doc(payload, DOC_ALLOCATION_SCHEDULE)
    audit_doc = _doc(payload, DOC_AUDIT_REGISTER)
    ledger = _doc(payload, DOC_JOB_COST_LEDGER)
    summary = _doc(payload, DOC_ALLOCATION_SUMMARY)
    gl = _doc(payload, DOC_GL_POSITIONS)
    if not all((projects_doc, policy_doc, schedule, audit_doc, ledger, summary, gl)):
        return
    assert projects_doc and policy_doc and schedule and audit_doc and ledger and summary and gl

    as_of = date.fromisoformat(payload["as_of"])
    projects = {p["code"]: p for p in projects_doc["projects"]}
    policies = policy_doc["policies"]

    # Allocation schedule: one share per covered project, by the declared basis.
    schedule["allocations"] = []
    for policy in policies:
        covered = list(policy["covered_projects"])
        basis = policy["allocation_basis"]
        values = [projects[code][basis] for code in covered]
        shares = derive_shares(policy["premium_cents"], values)
        for code, share in zip(covered, shares):
            schedule["allocations"].append(
                {
                    "policy_no": policy["policy_no"],
                    "project_code": code,
                    "allocated_cents": share,
                }
            )

    # Audit true-up: reallocated on the same basis that split the deposit, to the
    # projects that bore it.
    for audit in audit_doc["audits"]:
        policy = next(p for p in policies if p["policy_no"] == audit["policy_no"])
        covered = list(policy["covered_projects"])
        basis = policy["allocation_basis"]
        bases = [projects[code][basis] for code in covered]
        credits = derive_shares(audit["amount_cents"], bases)
        audit["reallocation"] = [
            {
                "project_code": code,
                "credit_cents": credit,
                "deposit_basis_cents": basis_value,
                "final_basis_cents": basis_value,
            }
            for code, credit, basis_value in zip(covered, credits, bases)
        ]

    # Job cost: what each project actually carries is the sum of every share.
    landed: dict[str, int] = {}
    for row in schedule["allocations"]:
        landed[row["project_code"]] = landed.get(row["project_code"], 0) + row["allocated_cents"]
    ledger["postings"] = [
        {"project_code": code, "amount_cents": landed[code]} for code in sorted(landed)
    ]

    # Reporting summary: the per-unit metric, re-derived from cost and unit count.
    summary["projects"] = [
        {
            "project_code": code,
            "per_unit_cents": landed.get(code, 0) // projects[code]["unit_count"],
        }
        for code in sorted(landed)
        if projects[code]["unit_count"] > 0
    ]

    # General-ledger positions: the prepaid asset and the programme total.
    gl["prepaid_insurance_cents"] = prepaid_unearned(policies, as_of)
    gl["total_insurance_cost_cents"] = sum(p["premium_cents"] for p in policies)


def baseline(programme: str) -> dict[str, Any]:
    """Build a clean programme file for ``programme``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "programme": programme,
        "policy_year": POLICY_YEAR,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PROJ-2029",
                "projects": [
                    {
                        "code": code,
                        "name": name,
                        "stage": stage,
                        "hard_cost_cents": hard_cost,
                        "insured_value_cents": insured,
                        "unit_count": units,
                        "construction_start": start,
                        "construction_end": end,
                    }
                    for code, name, stage, hard_cost, insured, units, start, end in PROJECTS
                ],
            },
            {
                "doc_type": DOC_POLICY_REGISTER,
                "document_id": "POL-2029",
                "policies": [
                    {
                        "policy_no": policy_no,
                        "line": line,
                        "layer": layer,
                        "carrier": carrier,
                        "inception_date": inception,
                        "expiration_date": expiration,
                        "premium_cents": premium,
                        "allocation_basis": basis,
                        "covered_projects": list(covered),
                        "limit_cents": limit,
                        "attaches_over": attaches_over,
                        "attachment_point_cents": attachment,
                        "value_tolerance_bps": tolerance,
                    }
                    for (
                        policy_no, line, layer, carrier, inception, expiration, premium,
                        basis, covered, limit, attaches_over, attachment, tolerance,
                    ) in POLICIES
                ],
            },
            {
                "doc_type": DOC_ALLOCATION_SCHEDULE,
                "document_id": "ALLOC-2029",
                "allocations": [],
            },
            {
                "doc_type": DOC_AUDIT_REGISTER,
                "document_id": "AUDIT-2029",
                "audits": [
                    {
                        "audit_no": audit_no,
                        "policy_no": policy_no,
                        "audit_type": audit_type,
                        "amount_cents": amount,
                        "reallocation": [],
                    }
                    for audit_no, policy_no, audit_type, amount in AUDITS
                ],
            },
            {
                "doc_type": DOC_JOB_COST_LEDGER,
                "document_id": "JOBCOST-2029",
                "postings": [],
            },
            {
                "doc_type": DOC_ALLOCATION_SUMMARY,
                "document_id": "SUMMARY-2029",
                "projects": [],
            },
            {
                "doc_type": DOC_GL_POSITIONS,
                "document_id": "GL-2029",
                "prepaid_insurance_cents": 0,
                "total_insurance_cost_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_GL_POSITIONS
    ]


def _missing_required_field(payload: dict[str, Any]) -> None:
    del _policy(payload, "GL-2029")["carrier"]


def _duplicate_policy(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_POLICY_REGISTER)
    assert register is not None
    register["policies"].append(dict(_policy(payload, "GL-2029")))


def _inverted_term(payload: dict[str, Any]) -> None:
    # The excess layer's term is entered back to front; the remaining-days figure
    # its prepaid would produce is negative.
    _policy(payload, "XS-2029")["expiration_date"] = "2029-06-01"


def _coverage_gap(payload: dict[str, Any]) -> None:
    # The renewal is bound two months after the prior term lapsed.
    _policy(payload, "GL-2029")["inception_date"] = "2029-09-01"


def _tower_gap(payload: dict[str, Any]) -> None:
    _policy(payload, "XS-2029")["attachment_point_cents"] = (
        _policy(payload, "GL-2029")["limit_cents"] + d(1_000_000)
    )


def _undeclared_basis(payload: dict[str, Any]) -> None:
    _policy(payload, "BR-2029")["allocation_basis"] = "square_feet"


def _unknown_project(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_ALLOCATION_SCHEDULE)
    assert schedule is not None
    schedule["allocations"].append(
        {"policy_no": "GL-2029", "project_code": "PRJ-777", "allocated_cents": 0}
    )


def _uncovered_project(payload: dict[str, Any]) -> None:
    # Builder's risk allocates to the completed project it does not schedule.
    schedule = _doc(payload, DOC_ALLOCATION_SCHEDULE)
    assert schedule is not None
    schedule["allocations"].append(
        {"policy_no": "BR-2029", "project_code": "PRJ-104", "allocated_cents": 0}
    )


def _missing_basis_value(payload: dict[str, Any]) -> None:
    # The basis value drops out; the stated shares (derived from it) are left in
    # place, so the total still ties while every share is now unsupported.
    _project(payload, "PRJ-104")["hard_cost_cents"] = 0


def _allocation_short(payload: dict[str, Any]) -> None:
    _alloc(payload, "GL-2029", "PRJ-101")["allocated_cents"] -= d(500)


def _share_misallocated(payload: dict[str, Any]) -> None:
    # The residual cent-plus lands on the wrong project; the policy still foots.
    _alloc(payload, "GL-2029", "PRJ-101")["allocated_cents"] -= d(300)
    _alloc(payload, "GL-2029", "PRJ-102")["allocated_cents"] += d(300)


def _negative_share(payload: dict[str, Any]) -> None:
    # A correction booked as a negative share nets to the right policy total.
    a104 = _alloc(payload, "GL-2029", "PRJ-104")
    a101 = _alloc(payload, "GL-2029", "PRJ-101")
    value = a104["allocated_cents"]
    a104["allocated_cents"] = -value
    a101["allocated_cents"] += 2 * value


def _builders_value_adrift(payload: dict[str, Any]) -> None:
    project = _project(payload, "PRJ-102")
    project["insured_value_cents"] = project["hard_cost_cents"] + d(2_000_000)


def _br_term_short(payload: dict[str, Any]) -> None:
    _project(payload, "PRJ-101")["construction_end"] = "2030-08-01"


def _completed_still_scheduled(payload: dict[str, Any]) -> None:
    _project(payload, "PRJ-101")["stage"] = STAGE_COMPLETE


def _audit_true_up_short(payload: dict[str, Any]) -> None:
    _realloc(payload, "AUD-2028", "PRJ-101")["credit_cents"] -= d(100)


def _audit_wrong_bearers(payload: dict[str, Any]) -> None:
    _audit(payload, "AUD-2028")["reallocation"].append(
        {
            "project_code": "PRJ-777",
            "credit_cents": 0,
            "deposit_basis_cents": 0,
            "final_basis_cents": 0,
        }
    )


def _audit_wrong_basis(payload: dict[str, Any]) -> None:
    _realloc(payload, "AUD-2028", "PRJ-101")["credit_cents"] -= d(50)
    _realloc(payload, "AUD-2028", "PRJ-102")["credit_cents"] += d(50)


def _audit_no_final_basis(payload: dict[str, Any]) -> None:
    _realloc(payload, "AUD-2028", "PRJ-101")["final_basis_cents"] = None


def _jobcost_untied(payload: dict[str, Any]) -> None:
    _posting(payload, "PRJ-101")["amount_cents"] += d(250)


def _prepaid_untied(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_GL_POSITIONS)["prepaid_insurance_cents"] += d(500)


def _programme_total_untied(payload: dict[str, Any]) -> None:
    _doc(payload, DOC_GL_POSITIONS)["total_insurance_cost_cents"] += d(1_000)


def _per_unit_wrong(payload: dict[str, Any]) -> None:
    _summary(payload, "PRJ-101")["per_unit_cents"] += d(10)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _alloc(payload, "GL-2029", "PRJ-102")
    row["allocated_cents"] = float(row["allocated_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "missing_required_field": ("pol_required_fields", _missing_required_field),
    "duplicate_policy": ("pol_no_duplicate", _duplicate_policy),
    "inverted_term": ("pol_term_runs_forwards", _inverted_term),
    "coverage_gap": ("pol_no_coverage_gap", _coverage_gap),
    "tower_gap": ("pol_tower_has_no_gap", _tower_gap),
    "undeclared_basis": ("alloc_basis_declared", _undeclared_basis),
    "unknown_project": ("alloc_project_exists", _unknown_project),
    "uncovered_project": ("alloc_only_covered_projects", _uncovered_project),
    "missing_basis_value": ("alloc_basis_data_complete", _missing_basis_value),
    "allocation_short": ("alloc_sums_to_premium", _allocation_short),
    "share_misallocated": ("alloc_shares_recompute", _share_misallocated),
    "negative_share": ("alloc_no_negative", _negative_share),
    "builders_value_adrift": ("br_value_ties_budget", _builders_value_adrift),
    "br_term_short": ("br_term_covers_construction", _br_term_short),
    "completed_still_scheduled": ("br_completed_project_removed", _completed_still_scheduled),
    "audit_true_up_short": ("aud_true_up_sums", _audit_true_up_short),
    "audit_wrong_bearers": ("aud_credits_deposit_bearers", _audit_wrong_bearers),
    "audit_wrong_basis": ("aud_uses_deposit_basis", _audit_wrong_basis),
    "audit_no_final_basis": ("aud_basis_restated", _audit_no_final_basis),
    "jobcost_untied": ("gl_allocation_ties_job_cost", _jobcost_untied),
    "prepaid_untied": ("gl_prepaid_amortisation_ties", _prepaid_untied),
    "programme_total_untied": ("gl_total_ties_programme", _programme_total_untied),
    "per_unit_wrong": ("rpt_per_unit_recomputes", _per_unit_wrong),
    "amount_not_integer": ("alloc_sums_to_premium", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PROGRAMMES[0])
    clean["file_id"] = f"clean__{PROGRAMMES[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        programme = PROGRAMMES[(i + 1) % len(PROGRAMMES)]
        f = baseline(programme)
        f["file_id"] = f"{name}__{programme.replace(' ', '_')}"
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
