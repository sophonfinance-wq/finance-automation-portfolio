"""
Fictional subcontract-commitment billing corpus generator.
==========================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the vendors, the
escrow agent, the jurisdiction (the "State of Marran" and its sales tax), the
contract amounts and the billing periods are fictional, and every period is set
in a fictional future. No real entity, person, vendor, project or path appears
anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the commitments, the change orders, the SOV lines and each pay app's
work-this-period figures are stated as base facts. Everything the engine later
re-derives -- previously billed, completed to date, percents, balances, header
totals, the request / retention / tax / payment-due chain, the committed-cost
roster and the conditional releases -- is recomputed by :func:`rederive` from
those base facts, through the *same* :mod:`sov_engine.billing` kernel the
engine recomputes with. So the relationships the engine tests are the
relationships that produced the data: a defect that changes a base fact
re-derives the chain and keeps the break confined to one control; a defect that
targets a stated derived figure edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import billing
from .engine import recompute_net_approved_changes
from .model import (
    DOC_CHANGE_ORDER_LOG,
    DOC_COMMITMENT_REGISTER,
    DOC_COMMITMENT_ROLLUP,
    DOC_LIEN_RELEASE_REGISTER,
    DOC_PAY_APP_REGISTER,
    DOC_SOV_SCHEDULE,
    ORIGIN_ORIGINAL,
    RELEASE_CONDITIONAL,
    Context,
)

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere",
)

#: The fictional project every commitment in the corpus bills against.
PROJECT = "Brightwater Commons"
PROJECT_CODE = "BWC"
PERIOD = "FY2030"
#: Fictional escrow agent named on every conditional release.
ESCROW_AGENT = "Harborline Title & Escrow"
#: Fictional jurisdiction whose sales tax the pay apps carry.
JURISDICTION = "State of Marran"
#: The Marran state sales-tax rate, in basis points (8.20%).
TAX_RATE_BPS = 820


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(vendor_code, vendor, original_dollars, retention_rate_bps)``. Invented
#: vendors; each holds exactly one commitment, numbered ``-1`` by the procedure.
COMMITMENTS: tuple[tuple[Any, ...], ...] = (
    ("KETT00", "Kettleridge Concrete", 485_000.00, 500),
    ("MARO00", "Marrowfield Steel", 312_400.00, 1000),
    ("CIND00", "Cindermill Electric", 126_750.00, 500),
)

CID_KETT = billing.make_commitment_id(PROJECT_CODE, "KETT00", 1)
CID_MARO = billing.make_commitment_id(PROJECT_CODE, "MARO00", 1)
CID_CIND = billing.make_commitment_id(PROJECT_CODE, "CIND00", 1)

#: ``(commitment_id, line_no, description, scheduled_dollars)``. Each
#: commitment's lines foot exactly to its original contract amount.
SOV_LINES: tuple[tuple[Any, ...], ...] = (
    (CID_KETT, 1, "Structural excavation & shoring", 150_000.00),
    (CID_KETT, 2, "Foundations & flatwork", 210_000.00),
    (CID_KETT, 3, "Site concrete & curbs", 125_000.00),
    (CID_MARO, 1, "Structural steel supply", 200_000.00),
    (CID_MARO, 2, "Steel erection", 112_400.00),
    (CID_CIND, 1, "Electrical rough-in", 86_750.00),
    (CID_CIND, 2, "Fixtures & trim", 40_000.00),
)

#: ``(co_id, commitment_id, co_number, description, classification, status,
#:   amount_dollars)``. The pending order deliberately moves nothing; the
#: soft-cost credit is applied to the original commitment, as the procedure
#: requires, never booked as a commitment of its own.
CHANGE_ORDERS: tuple[tuple[Any, ...], ...] = (
    ("CO-2001", CID_KETT, 1, "Rock excavation overrun", "hard_cost", billing.CO_APPROVED, 12_500.00),
    ("CO-2002", CID_KETT, 2, "Winter protection allowance", "hard_cost", billing.CO_PENDING, 8_000.00),
    ("CO-2003", CID_MARO, 1, "Steel connection redesign credit", "soft_cost", billing.CO_APPROVED, -4_200.00),
)

#: ``(commitment_id, app_no, period_end, {line_no: work_this_period_dollars})``.
#: These are the only billing base facts; everything else is derived.
PAY_APPS: tuple[tuple[Any, ...], ...] = (
    (CID_KETT, 1, "2030-01-31", {1: 60_000.00, 2: 40_000.00, 3: 0.00}),
    (CID_KETT, 2, "2030-02-28", {1: 45_000.00, 2: 55_000.00, 3: 20_000.00}),
    (CID_MARO, 1, "2030-01-31", {1: 80_000.00, 2: 0.00}),
    (CID_MARO, 2, "2030-02-28", {1: 50_000.00, 2: 30_000.00}),
    (CID_CIND, 1, "2030-02-28", {1: 25_000.00, 2: 0.00}),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _commitment(payload: dict[str, Any], commitment_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_COMMITMENT_REGISTER)
    assert register is not None
    for row in register["commitments"]:
        if row.get("commitment_id") == commitment_id:
            return row
    raise KeyError(commitment_id)


def _change_order(payload: dict[str, Any], co_id: str) -> dict[str, Any]:
    log = _doc(payload, DOC_CHANGE_ORDER_LOG)
    assert log is not None
    for row in log["change_orders"]:
        if row.get("co_id") == co_id:
            return row
    raise KeyError(co_id)


def _sov_line(payload: dict[str, Any], commitment_id: str, line_no: int) -> dict[str, Any]:
    schedule = _doc(payload, DOC_SOV_SCHEDULE)
    assert schedule is not None
    for row in schedule["lines"]:
        if row.get("commitment_id") == commitment_id and row.get("line_no") == line_no:
            return row
    raise KeyError((commitment_id, line_no))


def _app(payload: dict[str, Any], commitment_id: str, app_no: int) -> dict[str, Any]:
    register = _doc(payload, DOC_PAY_APP_REGISTER)
    assert register is not None
    for row in register["pay_applications"]:
        if row.get("commitment_id") == commitment_id and row.get("app_no") == app_no:
            return row
    raise KeyError((commitment_id, app_no))


def _app_line(app: dict[str, Any], line_no: int) -> dict[str, Any]:
    for line in app["lines"]:
        if line.get("line_no") == line_no:
            return line
    raise KeyError(line_no)


def _rollup(payload: dict[str, Any]) -> dict[str, Any]:
    rollup = _doc(payload, DOC_COMMITMENT_ROLLUP)
    assert rollup is not None
    return rollup


def _rollup_row(payload: dict[str, Any], commitment_id: str) -> dict[str, Any]:
    for row in _rollup(payload)["rows"]:
        if row.get("commitment_id") == commitment_id:
            return row
    raise KeyError(commitment_id)


def _release(payload: dict[str, Any], commitment_id: str, app_no: int) -> dict[str, Any]:
    register = _doc(payload, DOC_LIEN_RELEASE_REGISTER)
    assert register is not None
    for row in register["releases"]:
        if row.get("commitment_id") == commitment_id and row.get("app_no") == app_no:
            return row
    raise KeyError((commitment_id, app_no))


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    register = _doc(payload, DOC_COMMITMENT_REGISTER)
    schedule = _doc(payload, DOC_SOV_SCHEDULE)
    apps_doc = _doc(payload, DOC_PAY_APP_REGISTER)
    rollup = _doc(payload, DOC_COMMITMENT_ROLLUP)
    releases_doc = _doc(payload, DOC_LIEN_RELEASE_REGISTER)
    log = _doc(payload, DOC_CHANGE_ORDER_LOG)
    if not all((register, schedule, apps_doc, rollup, releases_doc, log)):
        return
    assert register is not None and schedule is not None and apps_doc is not None
    assert rollup is not None and releases_doc is not None

    ctx = Context(path=Path("<generated>"), data=payload)
    scheduled = {
        (row["commitment_id"], row["line_no"]): row["scheduled_value_cents"]
        for row in schedule["lines"]
    }
    terms = {
        row["commitment_id"]: (row["retention_rate_bps"], row["tax_rate_bps"])
        for row in register["commitments"]
    }

    # Pay applications: the whole per-line and header chain, re-derived from the
    # work-this-period base facts through the shared kernel.
    by_commitment: dict[str, list[dict[str, Any]]] = {}
    for app in apps_doc["pay_applications"]:
        by_commitment.setdefault(app["commitment_id"], []).append(app)
    for cid, apps in by_commitment.items():
        retention_rate, tax_rate = terms[cid]
        prior_completed: dict[int, int] = {}
        for app in sorted(apps, key=lambda a: a["app_no"]):
            completed_sum = 0
            prev_sum = 0
            for line in app["lines"]:
                line_no = line["line_no"]
                prev = prior_completed.get(line_no, 0)
                completed = billing.total_completed_cents(
                    prev, line["work_this_period_cents"]
                )
                line["previously_billed_cents"] = prev
                line["total_completed_cents"] = completed
                sv = scheduled.get((cid, line_no))
                if sv is not None:
                    line["percent_complete_bps"] = billing.percent_complete(completed, sv)
                    line["balance_to_finish_cents"] = billing.balance_to_finish_cents(
                        sv, completed
                    )
                prev_sum += prev
                completed_sum += completed
                prior_completed[line_no] = completed
            request = billing.current_request_cents(completed_sum, prev_sum)
            retention = billing.retention_cents(request, retention_rate)
            taxable = request
            tax = billing.sales_tax_cents(taxable, tax_rate)
            app["totals"] = {
                "total_completed_cents": completed_sum,
                "total_previously_billed_cents": prev_sum,
                "current_request_cents": request,
                "retention_cents": retention,
                "taxable_request_cents": taxable,
                "sales_tax_cents": tax,
                "payment_due_incl_tax_cents": billing.payment_due_cents(
                    request, retention, tax
                ),
            }

    # Committed-cost roster: one row per commitment, revised = original + net
    # approved change orders, and the three Total columns footed from the rows.
    rows: list[dict[str, Any]] = []
    for commitment in register["commitments"]:
        cid = commitment["commitment_id"]
        net = recompute_net_approved_changes(ctx, cid)
        rows.append(
            {
                "commitment_id": cid,
                "original_contract_cents": commitment["original_contract_cents"],
                "net_changes_cents": net,
                "revised_contract_cents": billing.revised_contract_cents(
                    commitment["original_contract_cents"], net
                ),
            }
        )
    rollup["rows"] = rows
    rollup["totals"] = {
        "original_total_cents": sum(r["original_contract_cents"] for r in rows),
        "changes_total_cents": sum(r["net_changes_cents"] for r in rows),
        "revised_total_cents": sum(r["revised_contract_cents"] for r in rows),
    }

    # Conditional releases: one per pay app, signed for the certified payment.
    releases_doc["releases"] = [
        {
            "release_id": f"REL-{app['commitment_id']}-{app['app_no']}",
            "commitment_id": app["commitment_id"],
            "app_no": app["app_no"],
            "release_type": RELEASE_CONDITIONAL,
            "escrow_agent": ESCROW_AGENT,
            "amount_cents": app["totals"]["payment_due_incl_tax_cents"],
        }
        for app in apps_doc["pay_applications"]
    ]


def baseline(portfolio: str) -> dict[str, Any]:
    """Build a clean billing file for ``portfolio``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "project": PROJECT,
        "jurisdiction": JURISDICTION,
        "period": PERIOD,
        "documents": [
            {
                "doc_type": DOC_COMMITMENT_REGISTER,
                "document_id": "COMMITS-2030",
                "commitments": [
                    {
                        "commitment_id": billing.make_commitment_id(
                            PROJECT_CODE, vendor_code, 1
                        ),
                        "vendor": vendor,
                        "project_code": PROJECT_CODE,
                        "vendor_code": vendor_code,
                        "origin": ORIGIN_ORIGINAL,
                        "original_contract_cents": d(original),
                        "retention_rate_bps": retention_rate,
                        "tax_rate_bps": TAX_RATE_BPS,
                    }
                    for vendor_code, vendor, original, retention_rate in COMMITMENTS
                ],
            },
            {
                "doc_type": DOC_CHANGE_ORDER_LOG,
                "document_id": "COLOG-2030",
                "change_orders": [
                    {
                        "co_id": co_id,
                        "commitment_id": cid,
                        "co_number": co_number,
                        "description": description,
                        "classification": classification,
                        "status": status,
                        "amount_cents": d(amount),
                    }
                    for (
                        co_id, cid, co_number, description, classification, status, amount,
                    ) in CHANGE_ORDERS
                ],
            },
            {
                "doc_type": DOC_SOV_SCHEDULE,
                "document_id": "SOV-2030",
                "lines": [
                    {
                        "commitment_id": cid,
                        "line_no": line_no,
                        "description": description,
                        "scheduled_value_cents": d(value),
                    }
                    for cid, line_no, description, value in SOV_LINES
                ],
            },
            {
                "doc_type": DOC_PAY_APP_REGISTER,
                "document_id": "PAYAPPS-2030",
                "pay_applications": [
                    {
                        "commitment_id": cid,
                        "app_no": app_no,
                        "period_end": period_end,
                        "lines": [
                            {
                                "line_no": line_no,
                                "work_this_period_cents": d(work),
                            }
                            for line_no, work in sorted(work_by_line.items())
                        ],
                        "totals": {},
                    }
                    for cid, app_no, period_end, work_by_line in PAY_APPS
                ],
            },
            {
                "doc_type": DOC_COMMITMENT_ROLLUP,
                "document_id": "ROLLUP-2030",
                "rows": [],
                "totals": {},
            },
            {
                "doc_type": DOC_LIEN_RELEASE_REGISTER,
                "document_id": "RELEASES-2030",
                "releases": [],
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
        doc
        for doc in payload["documents"]
        if doc.get("doc_type") != DOC_LIEN_RELEASE_REGISTER
    ]


def _duplicate_commitment_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_COMMITMENT_REGISTER)
    assert register is not None
    register["commitments"].append(dict(_commitment(payload, CID_KETT)))


def _commitment_missing_field(payload: dict[str, Any]) -> None:
    del _commitment(payload, CID_MARO)["vendor"]


def _rollup_row_missing(payload: dict[str, Any]) -> None:
    # The electrical commitment fell off the committed-cost roster; the Total
    # columns still carry it, so the footing breaks alongside the tie.
    rollup = _rollup(payload)
    rollup["rows"] = [
        r for r in rollup["rows"] if r.get("commitment_id") != CID_CIND
    ]


def _net_changes_wrong(payload: dict[str, Any]) -> None:
    # The pending winter-protection order was counted as if approved.
    _rollup_row(payload, CID_KETT)["net_changes_cents"] += d(8_000)


def _co_unknown_commitment(payload: dict[str, Any]) -> None:
    log = _doc(payload, DOC_CHANGE_ORDER_LOG)
    assert log is not None
    log["change_orders"].append(
        {
            "co_id": "CO-2099",
            "commitment_id": "BWC-TALV00-1",
            "co_number": 1,
            "description": "Lobby millwork upgrade",
            "classification": "hard_cost",
            "status": billing.CO_APPROVED,
            "amount_cents": d(5_000),
        }
    )


def _co_number_gap(payload: dict[str, Any]) -> None:
    # The second order on the concrete commitment was logged as #-5.
    _change_order(payload, "CO-2002")["co_number"] = 5


def _co_bad_status(payload: dict[str, Any]) -> None:
    _change_order(payload, "CO-2002")["status"] = "maybe"


def _co_booked_as_commitment(payload: dict[str, Any]) -> None:
    # The soft-cost redesign credit was booked as a brand-new commitment instead
    # of being applied to the original as #-N.
    register = _doc(payload, DOC_COMMITMENT_REGISTER)
    assert register is not None
    register["commitments"].append(
        {
            "commitment_id": billing.make_commitment_id(PROJECT_CODE, "MARO00", 2),
            "vendor": "Marrowfield Steel",
            "project_code": PROJECT_CODE,
            "vendor_code": "MARO00",
            "origin": "change_order",
            "original_contract_cents": d(4_200),
            "retention_rate_bps": 1000,
            "tax_rate_bps": TAX_RATE_BPS,
        }
    )


def _commitment_id_prefix_mismatch(payload: dict[str, Any]) -> None:
    # The register says the electrical commitment belongs to a different
    # project than its own id was minted from.
    _commitment(payload, CID_CIND)["project_code"] = "CPY"


def _sov_duplicate_line(payload: dict[str, Any]) -> None:
    schedule = _doc(payload, DOC_SOV_SCHEDULE)
    assert schedule is not None
    schedule["lines"].append(
        {
            "commitment_id": CID_KETT,
            "line_no": 2,
            "description": "Foundations & flatwork (duplicate)",
            "scheduled_value_cents": 0,
        }
    )


def _sov_does_not_foot(payload: dict[str, Any]) -> None:
    _sov_line(payload, CID_KETT, 3)["scheduled_value_cents"] += d(10_000)


def _payapp_line_unknown(payload: dict[str, Any]) -> None:
    # The pay app bills a line the schedule of values never carried.
    _app(payload, CID_KETT, 1)["lines"].append(
        {
            "line_no": 9,
            "work_this_period_cents": 0,
            "previously_billed_cents": 0,
            "total_completed_cents": 0,
            "percent_complete_bps": 0,
            "balance_to_finish_cents": 0,
        }
    )


def _line_completed_wrong(payload: dict[str, Any]) -> None:
    # This period's work was re-typed after the completed column was footed.
    _app_line(_app(payload, CID_KETT, 2), 1)["work_this_period_cents"] -= d(100)


def _percent_overstated(payload: dict[str, Any]) -> None:
    _app_line(_app(payload, CID_KETT, 2), 2)["percent_complete_bps"] += 25


def _header_totals_wrong(payload: dict[str, Any]) -> None:
    _app(payload, CID_KETT, 1)["totals"]["total_completed_cents"] += d(100)


def _request_not_difference(payload: dict[str, Any]) -> None:
    _app(payload, CID_MARO, 2)["totals"]["current_request_cents"] += d(100)


def _line_overbilled(payload: dict[str, Any]) -> None:
    # The rough-in line bills past its scheduled value; the chain is re-derived
    # so every other figure stays consistent and only the cap is broken.
    _app_line(_app(payload, CID_CIND, 1), 1)["work_this_period_cents"] = d(90_000)
    rederive(payload)


def _balance_misstated(payload: dict[str, Any]) -> None:
    _app_line(_app(payload, CID_MARO, 1), 1)["balance_to_finish_cents"] -= d(100)


def _retention_rate_nonstandard(payload: dict[str, Any]) -> None:
    # A 7.5% rate off the 5% / 10% menu; the chain is re-derived at that rate so
    # the arithmetic still ties and only the menu flag remains.
    _commitment(payload, CID_CIND)["retention_rate_bps"] = 750
    rederive(payload)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    totals = _app(payload, CID_KETT, 2)["totals"]
    totals["retention_cents"] = float(totals["retention_cents"]) + 0.5


def _sales_tax_wrong(payload: dict[str, Any]) -> None:
    _app(payload, CID_MARO, 1)["totals"]["sales_tax_cents"] += 10


def _payment_due_wrong(payload: dict[str, Any]) -> None:
    _app(payload, CID_KETT, 1)["totals"]["payment_due_incl_tax_cents"] += d(100)


def _previously_billed_break(payload: dict[str, Any]) -> None:
    _app(payload, CID_KETT, 2)["totals"]["total_previously_billed_cents"] -= d(500)


def _app_number_gap(payload: dict[str, Any]) -> None:
    # The steel commitment's second app was numbered 4; the sequence skips.
    _app(payload, CID_MARO, 2)["app_no"] = 4


def _rollup_totals_wrong(payload: dict[str, Any]) -> None:
    _rollup(payload)["totals"]["original_total_cents"] += d(100)


def _revised_identity_broken(payload: dict[str, Any]) -> None:
    _rollup(payload)["totals"]["revised_total_cents"] += d(100)


def _release_missing(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_LIEN_RELEASE_REGISTER)
    assert register is not None
    register["releases"] = [
        r
        for r in register["releases"]
        if not (r.get("commitment_id") == CID_CIND and r.get("app_no") == 1)
    ]


def _release_amount_mismatch(payload: dict[str, Any]) -> None:
    _release(payload, CID_KETT, 2)["amount_cents"] -= d(100)


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_commitment_id": ("cmt_ids_unique", _duplicate_commitment_id),
    "commitment_missing_field": ("cmt_required_fields", _commitment_missing_field),
    "rollup_row_missing": ("cmt_rollup_ties_register", _rollup_row_missing),
    "net_changes_wrong": ("cmt_revised_rederives", _net_changes_wrong),
    "co_unknown_commitment": ("co_commitment_exists", _co_unknown_commitment),
    "co_number_gap": ("co_numbering_sequential", _co_number_gap),
    "co_bad_status": ("co_status_valid", _co_bad_status),
    "co_booked_as_commitment": ("co_not_split_to_new_commitment", _co_booked_as_commitment),
    "commitment_id_prefix_mismatch": ("co_commitment_id_format", _commitment_id_prefix_mismatch),
    "sov_duplicate_line": ("sov_lines_wellformed", _sov_duplicate_line),
    "sov_does_not_foot": ("sov_foots_to_original", _sov_does_not_foot),
    "payapp_line_unknown": ("line_ref_valid", _payapp_line_unknown),
    "line_completed_wrong": ("line_completed_rederives", _line_completed_wrong),
    "percent_overstated": ("line_percent_rederives", _percent_overstated),
    "header_totals_wrong": ("line_header_foots", _header_totals_wrong),
    "request_not_difference": ("line_current_request_rederives", _request_not_difference),
    "line_overbilled": ("cap_not_overbilled", _line_overbilled),
    "balance_misstated": ("cap_balance_rederives", _balance_misstated),
    "retention_rate_nonstandard": ("ret_rate_known", _retention_rate_nonstandard),
    "amount_not_integer": ("ret_rederives", _amount_not_integer),
    "sales_tax_wrong": ("tax_rederives", _sales_tax_wrong),
    "payment_due_wrong": ("tax_payment_due_rederives", _payment_due_wrong),
    "previously_billed_break": ("roll_previously_ties_prior", _previously_billed_break),
    "app_number_gap": ("roll_apps_sequential", _app_number_gap),
    "rollup_totals_wrong": ("port_totals_foot", _rollup_totals_wrong),
    "revised_identity_broken": ("port_revised_identity", _revised_identity_broken),
    "release_missing": ("lien_release_per_app", _release_missing),
    "release_amount_mismatch": ("lien_amount_ties", _release_amount_mismatch),
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
