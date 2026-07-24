"""
Fictional surety bond programme generator.
==========================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developer, its surety, the states, the cities,
the projects, the bond numbers and every amount are fictional, and the review
period is set in a fictional future. No real entity, person, surety, municipality,
project or path appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the facility, the rate card, the statutory minimums, the projects, the bonds
and the two ledgers are stated. Every figure that the engine later checks as a
*tie-out* is computed here from those inputs by :func:`rederive`:

* each bond's annual premium, from the rate card applied to its penal sum;
* each bond's outstanding collateral, from the postings and refunds against it;
* restricted cash, from the collateral ledger as a whole;
* prepaid premium, straight-line across each term to the review date;
* the exposure summary, from the penal sums of the bonds still active.

So the relationships the engine tests are the same relationships that produced the
data. A defect that changes a *base* fact calls :func:`rederive` afterwards, which
keeps the break confined to the one control it was built for; a defect that
targets a tie-out edits the stated figure alone and leaves the base untouched.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .model import (
    BOND_COMPLETION,
    BOND_LICENCE,
    BOND_MAINTENANCE,
    BOND_PERFORMANCE,
    BOND_PERMIT,
    COLL_POSTED,
    COLL_REFUNDED,
    DOC_BOND_REGISTER,
    DOC_COLLATERAL_LEDGER,
    DOC_GL_POSITIONS,
    DOC_PREMIUM_LEDGER,
    DOC_PROJECT_REGISTER,
    DOC_RATE_SCHEDULE,
    DOC_STATUTORY_TABLE,
    DOC_SURETY_FACILITY,
    OBLIGEE_MUNICIPAL,
    OBLIGEE_STATE,
    PREM_INITIAL,
    PREM_RENEWAL,
    PREM_RETURN,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_RELEASED,
)
from .money import apply_rate

#: Fictional programme labels, rotated for file identity only. The bond
#: programme below is the same fictional developer in every file.
PROGRAMMES: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

CURRENT_PERIOD = "2029-Q1"
AS_OF = "2029-02-15"

#: Fictional obligees.
OBL_CASCADIA = "Cascadia Department of Labour & Industries"
OBL_ARDENNE = "Ardenne Contractors Board"
OBL_BRIGHTWATER = "City of Brightwater"
OBL_HALLOWAY = "City of Halloway"

#: Fictional jurisdictions.
J_CASCADIA = "Cascadia"
J_ARDENNE = "Ardenne"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(code, name, jurisdiction, acceptance_date, warranty_end_date)``.
#: ``ENT-CORP`` is the operating entity the statutory licence bonds attach to; it
#: has no acceptance because it is a registration, not a job.
PROJECTS: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    ("ENT-CORP", "Northmoor Construction Co", J_CASCADIA, None, None),
    ("PRJ-114", "Ashgrove Terraces", J_CASCADIA, "2028-06-15", "2029-06-15"),
    ("PRJ-127", "Ferncliff Row", J_CASCADIA, "2028-09-01", "2029-09-01"),
    ("PRJ-133", "Wexford Commons", J_ARDENNE, "2027-05-20", "2028-05-20"),
    ("PRJ-140", "Marlowe Heights", J_CASCADIA, None, None),
)

#: ``bond_type -> (rate_bps, minimum_premium_cents, tolerance_bps)``. The
#: tolerance is the surety's, not the engine's: rates move with credit and term,
#: so the rate control is a reasonableness band and says so.
RATE_CARD: tuple[tuple[str, int, int, int], ...] = (
    (BOND_LICENCE, 250, d(250), 1000),
    (BOND_PERFORMANCE, 180, d(500), 1500),
    (BOND_MAINTENANCE, 120, d(350), 1500),
    (BOND_COMPLETION, 200, d(500), 1500),
    (BOND_PERMIT, 300, d(400), 1500),
)

#: ``(jurisdiction, bond_type, minimum_penal_sum_cents)`` -- set by statute.
STATUTORY: tuple[tuple[str, str, int], ...] = (
    (J_CASCADIA, BOND_LICENCE, d(12_000)),
    (J_ARDENNE, BOND_LICENCE, d(15_000)),
)

FACILITY_LIMIT = d(2_500_000)
COLLATERAL_CUSTODIAN = "Meridian Surety - collateral account"

#: The bond register. Premium and outstanding collateral are deliberately absent:
#: :func:`rederive` computes them, so the register cannot disagree with the rate
#: card or the ledger unless a defect makes it.
#:
#: ``(bond_no, project, type, jurisdiction, obligee, obligee_kind, penal_cents,
#:   effective, expiration, status, permit_no, release_date, release_reference,
#:   renewed_from, collateral_location)``
BONDS: tuple[tuple[Any, ...], ...] = (
    (
        "B-4399", "ENT-CORP", BOND_LICENCE, J_CASCADIA, OBL_CASCADIA, OBLIGEE_STATE,
        d(12_000), "2027-09-01", "2028-09-01", STATUS_EXPIRED,
        None, None, None, None, None,
    ),
    (
        "B-4401", "ENT-CORP", BOND_LICENCE, J_CASCADIA, OBL_CASCADIA, OBLIGEE_STATE,
        d(12_000), "2028-09-01", "2029-09-01", STATUS_ACTIVE,
        None, None, None, "B-4399", None,
    ),
    (
        "B-4402", "ENT-CORP", BOND_LICENCE, J_ARDENNE, OBL_ARDENNE, OBLIGEE_STATE,
        d(15_000), "2028-07-01", "2029-07-01", STATUS_ACTIVE,
        None, None, None, None, None,
    ),
    (
        "B-4415", "PRJ-114", BOND_PERFORMANCE, J_CASCADIA, OBL_BRIGHTWATER, OBLIGEE_MUNICIPAL,
        d(685_000), "2027-04-01", "2028-10-01", STATUS_RELEASED,
        "PUB27-118", "2028-08-01", "REL-2028-0031", None, COLLATERAL_CUSTODIAN,
    ),
    (
        "B-4416", "PRJ-114", BOND_MAINTENANCE, J_CASCADIA, OBL_BRIGHTWATER, OBLIGEE_MUNICIPAL,
        d(68_500), "2028-06-15", "2029-06-15", STATUS_ACTIVE,
        "PUB27-118", None, None, None, None,
    ),
    (
        "B-4422", "PRJ-127", BOND_PERFORMANCE, J_CASCADIA, OBL_BRIGHTWATER, OBLIGEE_MUNICIPAL,
        d(420_000), "2027-09-01", "2029-09-01", STATUS_ACTIVE,
        "PUB27-204", None, None, None, COLLATERAL_CUSTODIAN,
    ),
    (
        "B-4430", "PRJ-133", BOND_COMPLETION, J_ARDENNE, OBL_HALLOWAY, OBLIGEE_MUNICIPAL,
        d(250_000), "2026-05-01", "2028-05-01", STATUS_RELEASED,
        "PLT26-77", "2027-06-01", "REL-2027-0014", None, COLLATERAL_CUSTODIAN,
    ),
    (
        "B-4431", "PRJ-133", BOND_MAINTENANCE, J_ARDENNE, OBL_HALLOWAY, OBLIGEE_MUNICIPAL,
        d(25_000), "2027-05-20", "2028-05-20", STATUS_RELEASED,
        "PLT26-77", "2028-06-01", "REL-2028-0009", None, None,
    ),
    (
        "B-4440", "PRJ-140", BOND_PERMIT, J_CASCADIA, OBL_BRIGHTWATER, OBLIGEE_MUNICIPAL,
        d(150_000), "2028-02-01", "2029-08-01", STATUS_ACTIVE,
        "ROW28-051", None, None, None, COLLATERAL_CUSTODIAN,
    ),
    (
        "B-4445", "PRJ-140", BOND_PERFORMANCE, J_CASCADIA, OBL_BRIGHTWATER, OBLIGEE_MUNICIPAL,
        d(950_000), "2028-05-01", "2030-05-01", STATUS_ACTIVE,
        "PUB28-090", None, None, None, None,
    ),
)

#: ``(entry_no, bond_no, date, entry_type, amount_cents, reference)``.
COLLATERAL: tuple[tuple[str, str, str, str, int, str], ...] = (
    ("C-0011", "B-4415", "2027-04-05", COLL_POSTED, d(34_250), "WIRE-27-0405"),
    ("C-0012", "B-4430", "2026-05-10", COLL_POSTED, d(12_500), "WIRE-26-0510"),
    ("C-0018", "B-4422", "2027-09-10", COLL_POSTED, d(21_000), "WIRE-27-0910"),
    ("C-0021", "B-4430", "2027-08-20", COLL_REFUNDED, d(12_500), "REF-27-0820"),
    ("C-0025", "B-4440", "2028-02-10", COLL_POSTED, d(7_500), "WIRE-28-0210"),
    ("C-0030", "B-4415", "2028-09-15", COLL_REFUNDED, d(34_250), "REF-28-0915"),
)

#: ``(entry_no, bond_no, entry_type, period_from, period_to, amount_cents,
#:   rider_reference)``. Amounts are stated here because a premium *invoice* is a
#: third-party fact; what :func:`rederive` computes is the register's annual
#: premium and the prepaid balance, which are the developer's own figures.
PREMIUMS: tuple[tuple[str, str, str, str, str, int, str | None], ...] = (
    ("P-0101", "B-4399", PREM_INITIAL, "2027-09-01", "2028-09-01", d(300), None),
    ("P-0102", "B-4415", PREM_INITIAL, "2027-04-01", "2028-04-01", d(12_330), None),
    ("P-0103", "B-4430", PREM_INITIAL, "2026-05-01", "2027-05-01", d(5_000), None),
    ("P-0104", "B-4422", PREM_INITIAL, "2027-09-01", "2028-09-01", d(7_560), None),
    ("P-0105", "B-4431", PREM_INITIAL, "2027-05-20", "2028-05-20", d(350), None),
    ("P-0106", "B-4430", PREM_RENEWAL, "2027-05-01", "2028-05-01", d(5_000), None),
    ("P-0107", "B-4440", PREM_INITIAL, "2028-02-01", "2029-02-01", d(4_500), None),
    ("P-0108", "B-4415", PREM_RETURN, "2028-04-01", "2028-10-01", d(1_500), "RID-2028-0031"),
    ("P-0109", "B-4445", PREM_INITIAL, "2028-05-01", "2029-05-01", d(17_100), None),
    ("P-0110", "B-4416", PREM_INITIAL, "2028-06-15", "2029-06-15", d(822), None),
    ("P-0111", "B-4402", PREM_INITIAL, "2028-07-01", "2029-07-01", d(375), None),
    ("P-0112", "B-4401", PREM_RENEWAL, "2028-09-01", "2029-09-01", d(300), None),
    ("P-0113", "B-4422", PREM_RENEWAL, "2028-09-01", "2029-09-01", d(7_560), None),
    ("P-0114", "B-4440", PREM_RENEWAL, "2029-02-01", "2030-02-01", d(4_500), None),
)


# --------------------------------------------------------------------------- #
# Payload construction
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _bond(payload: dict[str, Any], bond_no: str) -> dict[str, Any]:
    register = _doc(payload, DOC_BOND_REGISTER)
    assert register is not None
    for row in register["bonds"]:
        if row.get("bond_no") == bond_no:
            return row
    raise KeyError(bond_no)


def _entry(payload: dict[str, Any], doc_type: str, entry_no: str) -> dict[str, Any]:
    doc = _doc(payload, doc_type)
    assert doc is not None
    for row in doc["entries"]:
        if row.get("entry_no") == entry_no:
            return row
    raise KeyError(entry_no)


def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts.

    Called after any defect that changes a base fact, so the planted break stays
    confined to the control it was built for instead of cascading into every
    tie-out downstream.
    """
    register = _doc(payload, DOC_BOND_REGISTER)
    collateral = _doc(payload, DOC_COLLATERAL_LEDGER)
    premium = _doc(payload, DOC_PREMIUM_LEDGER)
    gl = _doc(payload, DOC_GL_POSITIONS)
    schedule = _doc(payload, DOC_RATE_SCHEDULE)
    if not all((register, collateral, premium, gl, schedule)):
        return
    assert register and collateral and premium and gl and schedule

    rates = {r["bond_type"]: r for r in schedule["rates"]}

    # Annual premium: the rate card applied to the penal sum, floored at the
    # surety's minimum premium.
    for row in register["bonds"]:
        card = rates.get(row.get("bond_type"))
        if card is None or not isinstance(row.get("penal_sum_cents"), int):
            continue
        row["annual_premium_cents"] = max(
            apply_rate(row["penal_sum_cents"], card["rate_bps"]),
            card["minimum_premium_cents"],
        )

    # Outstanding collateral: postings less refunds, per bond and in total.
    net: dict[str, int] = {}
    for entry in collateral["entries"]:
        bond_no = entry.get("bond_no")
        amount = entry.get("amount_cents")
        if not isinstance(bond_no, str) or not isinstance(amount, int):
            continue
        sign = 1 if entry.get("entry_type") == COLL_POSTED else -1
        net[bond_no] = net.get(bond_no, 0) + sign * amount
    for row in register["bonds"]:
        row["collateral_outstanding_cents"] = net.get(row.get("bond_no"), 0)
    gl["restricted_cash_collateral_cents"] = sum(net.values())

    # Prepaid premium: straight-line across each term to the review date, by the
    # same truncating arithmetic the engine uses to re-derive it.
    as_of = date.fromisoformat(payload["as_of"])
    prepaid = 0
    for entry in premium["entries"]:
        if entry.get("entry_type") == PREM_RETURN:
            continue
        starts = date.fromisoformat(entry["period_from"])
        ends = date.fromisoformat(entry["period_to"])
        if ends <= starts:
            continue
        span = (ends - starts).days
        remaining = (ends - as_of).days
        if remaining <= 0:
            continue
        remaining = min(remaining, span)
        prepaid += entry["amount_cents"] * remaining // span
    gl["prepaid_bond_premium_cents"] = prepaid

    # Exposure summary: the penal sums of the bonds still active, by obligee.
    exposure: dict[str, int] = {}
    for row in register["bonds"]:
        if row.get("status") != STATUS_ACTIVE:
            continue
        obligee = row.get("obligee")
        penal = row.get("penal_sum_cents")
        if isinstance(obligee, str) and isinstance(penal, int):
            exposure[obligee] = exposure.get(obligee, 0) + penal
    register["exposure_by_obligee"] = [
        {"obligee": obligee, "penal_sum_cents": exposure[obligee]}
        for obligee in sorted(exposure)
    ]


def baseline(programme: str) -> dict[str, Any]:
    """Build a clean programme file for ``programme``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "programme": programme,
        "period": CURRENT_PERIOD,
        "as_of": AS_OF,
        "documents": [
            {
                "doc_type": DOC_SURETY_FACILITY,
                "document_id": "FAC-2029",
                "surety": "Meridian Surety Company",
                "indemnity_agreement": "IND-2026-0004",
                "aggregate_limit_cents": FACILITY_LIMIT,
                "indemnitors": ["Northmoor Development Group", "Northmoor Construction Co"],
            },
            {
                "doc_type": DOC_STATUTORY_TABLE,
                "document_id": "STAT-2029",
                "minimums": [
                    {
                        "jurisdiction": juris,
                        "bond_type": btype,
                        "minimum_penal_sum_cents": minimum,
                    }
                    for juris, btype, minimum in STATUTORY
                ],
            },
            {
                "doc_type": DOC_RATE_SCHEDULE,
                "document_id": "RATE-2029",
                "rates": [
                    {
                        "bond_type": btype,
                        "rate_bps": rate,
                        "minimum_premium_cents": minimum,
                        "tolerance_bps": tolerance,
                    }
                    for btype, rate, minimum, tolerance in RATE_CARD
                ],
            },
            {
                "doc_type": DOC_PROJECT_REGISTER,
                "document_id": "PROJ-2029",
                "projects": [
                    {
                        "code": code,
                        "name": name,
                        "jurisdiction": juris,
                        "acceptance_date": accepted,
                        "warranty_end_date": warranty,
                    }
                    for code, name, juris, accepted, warranty in PROJECTS
                ],
            },
            {
                "doc_type": DOC_BOND_REGISTER,
                "document_id": "BOND-2029Q1",
                "bonds": [
                    {
                        "bond_no": bond_no,
                        "project_code": project,
                        "bond_type": btype,
                        "jurisdiction": juris,
                        "obligee": obligee,
                        "obligee_kind": kind,
                        "penal_sum_cents": penal,
                        "effective_date": effective,
                        "expiration_date": expiration,
                        "status": status,
                        "permit_no": permit,
                        "release_date": release_date,
                        "release_reference": release_ref,
                        "renewed_from": renewed_from,
                        "collateral_location": location,
                        "collateral_refund_status": None,
                    }
                    for (
                        bond_no, project, btype, juris, obligee, kind, penal,
                        effective, expiration, status, permit, release_date,
                        release_ref, renewed_from, location,
                    ) in BONDS
                ],
                "exposure_by_obligee": [],
            },
            {
                "doc_type": DOC_COLLATERAL_LEDGER,
                "document_id": "COLL-2029Q1",
                "entries": [
                    {
                        "entry_no": entry_no,
                        "bond_no": bond_no,
                        "entry_date": when,
                        "entry_type": etype,
                        "amount_cents": amount,
                        "reference": reference,
                    }
                    for entry_no, bond_no, when, etype, amount, reference in COLLATERAL
                ],
            },
            {
                "doc_type": DOC_PREMIUM_LEDGER,
                "document_id": "PREM-2029Q1",
                "entries": [
                    {
                        "entry_no": entry_no,
                        "bond_no": bond_no,
                        "entry_type": etype,
                        "period_from": period_from,
                        "period_to": period_to,
                        "amount_cents": amount,
                        "rider_reference": rider,
                    }
                    for entry_no, bond_no, etype, period_from, period_to, amount, rider
                    in PREMIUMS
                ],
            },
            {
                "doc_type": DOC_GL_POSITIONS,
                "document_id": "GL-2029Q1",
                "restricted_cash_collateral_cents": 0,
                "prepaid_bond_premium_cents": 0,
            },
        ],
    }
    rederive(payload)
    return payload


# --------------------------------------------------------------------------- #
# Planted defects
# --------------------------------------------------------------------------- #
def _drop_document(payload: dict[str, Any]) -> None:
    payload["documents"] = [
        d for d in payload["documents"] if d.get("doc_type") != DOC_RATE_SCHEDULE
    ]


def _duplicate_bond_number(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_BOND_REGISTER)
    assert register is not None
    clone = dict(_bond(payload, "B-4440"))
    register["bonds"].append(clone)
    rederive(payload)


def _missing_required_field(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4422")["obligee"] = None
    rederive(payload)


def _bad_status(payload: dict[str, Any]) -> None:
    # "closed" is not in the vocabulary, so every lifecycle control would quietly
    # skip this bond -- which is the point of the control.
    _bond(payload, "B-4430")["status"] = "closed"
    rederive(payload)


def _inverted_term(payload: dict[str, Any]) -> None:
    # Planted on a released bond on purpose: swapping the dates on an *active*
    # bond would also expire it, and the file is meant to isolate one control.
    bond = _bond(payload, "B-4415")
    bond["effective_date"], bond["expiration_date"] = (
        bond["expiration_date"],
        bond["effective_date"],
    )


def _unmapped_project(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4416")["project_code"] = "PRJ-999"


def _licence_below_minimum(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4402")["penal_sum_cents"] = d(10_000)
    rederive(payload)


def _wrong_obligee_kind(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4401")["obligee_kind"] = OBLIGEE_MUNICIPAL


def _missing_permit_no(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4422")["permit_no"] = None


def _expired_but_active(payload: dict[str, Any]) -> None:
    # Still carried active, but the term ran out before the review date.
    _bond(payload, "B-4416")["expiration_date"] = "2028-12-31"


def _expiring_soon(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4445")["expiration_date"] = "2029-03-20"


def _renewal_gap(payload: dict[str, Any]) -> None:
    # The renewal starts six weeks after the bond it replaces expired.
    _bond(payload, "B-4401")["effective_date"] = "2028-10-15"


def _released_without_evidence(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4431")["release_reference"] = None


def _early_release(payload: dict[str, Any]) -> None:
    # Released a month before the warranty period it secures had ended.
    _bond(payload, "B-4431")["release_date"] = "2028-04-20"


def _maintenance_before_acceptance(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4416")["effective_date"] = "2028-03-01"


def _released_with_collateral(payload: dict[str, Any]) -> None:
    """The headline: the obligee discharged the bond, the cash never came back."""
    ledger = _doc(payload, DOC_COLLATERAL_LEDGER)
    assert ledger is not None
    ledger["entries"] = [e for e in ledger["entries"] if e["entry_no"] != "C-0030"]
    rederive(payload)


def _stale_collateral(payload: dict[str, Any]) -> None:
    """Same money, but a refund is on record as in flight -- so it ages instead."""
    ledger = _doc(payload, DOC_COLLATERAL_LEDGER)
    assert ledger is not None
    ledger["entries"] = [e for e in ledger["entries"] if e["entry_no"] != "C-0030"]
    _bond(payload, "B-4415")["collateral_refund_status"] = "requested 2028-08-10, chasing"
    rederive(payload)


def _collateral_over_penal_sum(payload: dict[str, Any]) -> None:
    _entry(payload, DOC_COLLATERAL_LEDGER, "C-0025")["amount_cents"] = d(155_000)
    rederive(payload)


def _collateral_ledger_break(payload: dict[str, Any]) -> None:
    # A tie-out defect: the stated summary alone, base facts untouched.
    _bond(payload, "B-4422")["collateral_outstanding_cents"] = d(19_500)


def _over_refund(payload: dict[str, Any]) -> None:
    _entry(payload, DOC_COLLATERAL_LEDGER, "C-0021")["amount_cents"] = d(15_000)
    rederive(payload)


def _missing_collateral_location(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4422")["collateral_location"] = None


def _restricted_cash_break(payload: dict[str, Any]) -> None:
    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["restricted_cash_collateral_cents"] += d(7_500)


def _premium_off_rate(payload: dict[str, Any]) -> None:
    _bond(payload, "B-4445")["annual_premium_cents"] = d(31_000)


def _premium_after_release(payload: dict[str, Any]) -> None:
    premium = _doc(payload, DOC_PREMIUM_LEDGER)
    assert premium is not None
    premium["entries"].append(
        {
            "entry_no": "P-0120",
            "bond_no": "B-4431",
            "entry_type": PREM_RENEWAL,
            "period_from": "2028-11-01",
            "period_to": "2029-11-01",
            "amount_cents": d(350),
            "rider_reference": None,
        }
    )
    # The prepaid balance is re-derived so only the release control breaks.
    rederive(payload)


def _prepaid_break(payload: dict[str, Any]) -> None:
    gl = _doc(payload, DOC_GL_POSITIONS)
    assert gl is not None
    gl["prepaid_bond_premium_cents"] += d(2_400)


def _return_without_rider(payload: dict[str, Any]) -> None:
    _entry(payload, DOC_PREMIUM_LEDGER, "P-0108")["rider_reference"] = None


def _bad_entry_type(payload: dict[str, Any]) -> None:
    _entry(payload, DOC_PREMIUM_LEDGER, "P-0104")["entry_type"] = "adjustment"


def _over_facility_limit(payload: dict[str, Any]) -> None:
    facility = _doc(payload, DOC_SURETY_FACILITY)
    assert facility is not None
    facility["aggregate_limit_cents"] = d(1_000_000)


def _obligee_summary_break(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_BOND_REGISTER)
    assert register is not None
    for row in register["exposure_by_obligee"]:
        if row["obligee"] == OBL_BRIGHTWATER:
            row["penal_sum_cents"] -= d(68_500)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    _entry(payload, DOC_COLLATERAL_LEDGER, "C-0018")["amount_cents"] = 21000.0


#: ``name -> (rule the file is built to trip, mutation)``
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _drop_document),
    "duplicate_bond_number": ("reg_bond_number_unique", _duplicate_bond_number),
    "missing_required_field": ("reg_required_fields", _missing_required_field),
    "bad_status": ("reg_status_domain", _bad_status),
    "inverted_term": ("reg_effective_before_expiration", _inverted_term),
    "unmapped_project": ("reg_project_mapped", _unmapped_project),
    "licence_below_minimum": ("stat_licence_minimum", _licence_below_minimum),
    "wrong_obligee_kind": ("stat_obligee_kind_matches_type", _wrong_obligee_kind),
    "missing_permit_no": ("stat_permit_reference_present", _missing_permit_no),
    "expired_but_active": ("life_active_not_expired", _expired_but_active),
    "expiring_soon": ("life_expiry_horizon", _expiring_soon),
    "renewal_gap": ("life_renewal_continuity", _renewal_gap),
    "released_without_evidence": ("life_released_has_evidence", _released_without_evidence),
    "early_release": ("life_release_after_obligation", _early_release),
    "maintenance_before_acceptance": (
        "life_maintenance_follows_acceptance",
        _maintenance_before_acceptance,
    ),
    "released_with_collateral": (
        "life_no_release_while_collateral_outstanding",
        _released_with_collateral,
    ),
    "collateral_over_penal_sum": ("coll_not_exceed_penal_sum", _collateral_over_penal_sum),
    "collateral_ledger_break": ("coll_ledger_ties_register", _collateral_ledger_break),
    "over_refund": ("coll_refund_not_exceed_posted", _over_refund),
    "stale_collateral": ("coll_refund_aging", _stale_collateral),
    "missing_collateral_location": ("coll_location_recorded", _missing_collateral_location),
    "restricted_cash_break": ("coll_ties_restricted_cash_gl", _restricted_cash_break),
    "premium_off_rate": ("prem_rate_within_schedule", _premium_off_rate),
    "premium_after_release": ("prem_no_premium_after_release", _premium_after_release),
    "prepaid_break": ("prem_prepaid_amortisation_ties", _prepaid_break),
    "return_without_rider": ("prem_return_has_rider", _return_without_rider),
    "bad_entry_type": ("prem_entry_type_domain", _bad_entry_type),
    "over_facility_limit": ("expo_within_facility_limit", _over_facility_limit),
    "obligee_summary_break": ("expo_by_obligee_ties_total", _obligee_summary_break),
    "amount_not_integer": ("coll_ledger_ties_register", _amount_not_integer),
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
