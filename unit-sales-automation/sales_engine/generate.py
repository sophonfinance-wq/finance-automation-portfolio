"""
Fictional unit sales and commission corpus generator.
=====================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the plans, the unit
numbers, the selling agents, the prices and the closing dates are fictional, and
the sales period is set in a fictional future. No real entity, person, project,
address or path appears anywhere. The generator is deterministic and takes no
seed.

The Matrix is derived, not typed
--------------------------------
Only the plans, the commission schedule, the unit base prices, the Sold/Close
dates and the agent split weights are stated as base facts. Everything the engine
later checks as a derived column -- revenue per square foot, net proceeds, total
commission, each agent's split in cents, and the three rollup totals -- is
recomputed by :func:`rederive` from those base facts, through the *same*
:mod:`sales_engine.tieout` kernel the engine recomputes with. So the
relationships the engine tests are the relationships that produced the data: a
defect that changes a base fact re-derives the Matrix and keeps the break confined
to one control; a defect that targets a derived figure edits that cell alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engine import (
    _split_rows,
    _unit_id,
    _units,
    recompute_commission_total,
    recompute_revenue_totals,
    recompute_sold_count,
    recompute_unit_derived,
)
from .model import (
    CHANNEL_CO_BROKE,
    CHANNEL_IN_HOUSE,
    CHANNEL_REFERRAL,
    DOC_AGENT_REGISTER,
    DOC_COMMISSION_LOG,
    DOC_COMMISSION_SCHEDULE,
    DOC_PLAN_REGISTER,
    DOC_SALES_ROLLUP,
    DOC_SOLD_CLOSE_LOG,
    DOC_UNIT_MATRIX,
    UNIT_AVAILABLE,
    UNIT_RESERVED,
    UNIT_SOLD,
    Context,
)
from .tieout import split_commission

#: Fictional developer labels, rotated for file identity only.
PORTFOLIOS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential Partners",
    "Stonecrest Communities",
    "Ardenne Field Group",
)

#: Fictional for-sale projects. One workbook template, many projects.
PROJECTS: tuple[str, ...] = (
    "Brightwater Commons",
    "Copperfield Yards",
)

#: Fictional market label, carried for identification only.
MARKET = "City of Kelder, State of Marran"

PERIOD = "FY2031"
#: The review date every closing test is measured to.
AS_OF = "2031-04-01"
#: Approved discount-to-list band, in basis points.
MAX_DISCOUNT_BPS = 500


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(plan_code, plan_name, plan_sqft)``. Invented plan names; the square footage
#: is the denominator every revenue-per-square-foot figure divides by.
PLANS: tuple[tuple[Any, ...], ...] = (
    ("PL-A1", "Alder", 1200),
    ("PL-B2", "Birchway", 1500),
    ("PL-C3", "Cedargate", 1800),
    ("PL-D4", "Dovecote", 2400),
)

#: ``(sale_channel, commission_rate_bps)``. The rate the total commission on the
#: Matrix is struck at, keyed by how the unit was sold.
COMMISSION_SCHEDULE: tuple[tuple[Any, ...], ...] = (
    (CHANNEL_IN_HOUSE, 250),
    (CHANNEL_CO_BROKE, 500),
    (CHANNEL_REFERRAL, 300),
)

#: ``(agent_id, agent_name)``. Invented selling agents.
AGENTS: tuple[tuple[str, str], ...] = (
    ("AG-01", "Renna Ashgrove"),
    ("AG-02", "Delmar Quenby"),
    ("AG-03", "Sable Ferngate"),
    ("AG-04", "Torin Wexhollow"),
)

#: ``(unit_id, building, plan_code, sale_channel, status, list_price, sales_price,
#:   concession, closing_costs)``. Prices in dollars. Each sold price divides
#: evenly into its plan area, so the revenue-per-square-foot column is exact to
#: the cent and a one-cent edit is the whole of a boundary defect.
UNITS: tuple[tuple[Any, ...], ...] = (
    ("UNIT-101", "Building A", "PL-A1", CHANNEL_IN_HOUSE, UNIT_SOLD, 610_000, 600_000, 6_000, 9_000),
    ("UNIT-102", "Building A", "PL-A1", CHANNEL_CO_BROKE, UNIT_SOLD, 615_000, 612_000, 0, 9_180),
    ("UNIT-103", "Building A", "PL-B2", CHANNEL_IN_HOUSE, UNIT_SOLD, 750_000, 735_000, 7_350, 11_025),
    ("UNIT-104", "Building B", "PL-B2", CHANNEL_REFERRAL, UNIT_SOLD, 760_000, 757_500, 5_000, 11_362),
    ("UNIT-105", "Building B", "PL-C3", CHANNEL_CO_BROKE, UNIT_SOLD, 900_000, 891_000, 9_000, 13_365),
    ("UNIT-106", "Building B", "PL-C3", CHANNEL_IN_HOUSE, UNIT_RESERVED, 905_000, 0, 0, 0),
    ("UNIT-107", "Building C", "PL-D4", CHANNEL_CO_BROKE, UNIT_AVAILABLE, 1_180_000, 0, 0, 0),
    ("UNIT-108", "Building C", "PL-D4", CHANNEL_IN_HOUSE, UNIT_SOLD, 1_200_000, 1_188_000, 12_000, 17_820),
)

#: ``(unit_id, offer_date, actual_date_sold, closing_date, proof_received)``. One
#: row per unit the Matrix marks Sold; every closing lands on or before the review
#: date, so every proof of closing is already due.
CLOSINGS: tuple[tuple[Any, ...], ...] = (
    ("UNIT-101", "2030-11-05", "2030-11-12", "2031-01-15", True),
    ("UNIT-102", "2030-11-18", "2030-11-25", "2031-01-28", True),
    ("UNIT-103", "2030-12-02", "2030-12-09", "2031-02-11", True),
    ("UNIT-104", "2030-12-15", "2030-12-20", "2031-02-24", True),
    ("UNIT-105", "2031-01-08", "2031-01-14", "2031-03-10", True),
    ("UNIT-108", "2031-01-22", "2031-01-29", "2031-03-24", True),
)

#: ``(unit_id, agent_id, split_bps)``. The weights each unit's total commission is
#: divided by; they sum to 10000 basis points on every unit, and the cents are
#: allocated from them by the shared kernel so the residual cent lands on a named
#: agent rather than disappearing.
COMMISSION_SPLITS: tuple[tuple[Any, ...], ...] = (
    ("UNIT-101", "AG-01", 6000),
    ("UNIT-101", "AG-02", 4000),
    ("UNIT-102", "AG-01", 5000),
    ("UNIT-102", "AG-03", 5000),
    ("UNIT-103", "AG-02", 10000),
    ("UNIT-104", "AG-03", 7000),
    ("UNIT-104", "AG-04", 3000),
    ("UNIT-105", "AG-01", 3333),
    ("UNIT-105", "AG-02", 3333),
    ("UNIT-105", "AG-04", 3334),
    ("UNIT-108", "AG-04", 10000),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _plan(payload: dict[str, Any], plan_code: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PLAN_REGISTER)
    assert register is not None
    for row in register["plans"]:
        if row.get("plan_code") == plan_code:
            return row
    raise KeyError(plan_code)


def _unit(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    matrix = _doc(payload, DOC_UNIT_MATRIX)
    assert matrix is not None
    for row in matrix["units"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _rate(payload: dict[str, Any], sale_channel: str) -> dict[str, Any]:
    schedule = _doc(payload, DOC_COMMISSION_SCHEDULE)
    assert schedule is not None
    for row in schedule["rates"]:
        if row.get("sale_channel") == sale_channel:
            return row
    raise KeyError(sale_channel)


def _closing(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    log = _doc(payload, DOC_SOLD_CLOSE_LOG)
    assert log is not None
    for row in log["closings"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _split(payload: dict[str, Any], unit_id: str, agent_id: str) -> dict[str, Any]:
    log = _doc(payload, DOC_COMMISSION_LOG)
    assert log is not None
    for row in log["splits"]:
        if row.get("unit_id") == unit_id and row.get("agent_id") == agent_id:
            return row
    raise KeyError((unit_id, agent_id))


def _rollup(payload: dict[str, Any]) -> dict[str, Any]:
    rollup = _doc(payload, DOC_SALES_ROLLUP)
    assert rollup is not None
    return rollup


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    plan_doc = _doc(payload, DOC_PLAN_REGISTER)
    matrix = _doc(payload, DOC_UNIT_MATRIX)
    schedule = _doc(payload, DOC_COMMISSION_SCHEDULE)
    close_log = _doc(payload, DOC_SOLD_CLOSE_LOG)
    agent_doc = _doc(payload, DOC_AGENT_REGISTER)
    comm_log = _doc(payload, DOC_COMMISSION_LOG)
    rollup = _doc(payload, DOC_SALES_ROLLUP)
    if not all((plan_doc, matrix, schedule, close_log, agent_doc, comm_log, rollup)):
        return
    assert matrix is not None and comm_log is not None and rollup is not None

    ctx = Context(path=Path("<generated>"), data=payload)

    # The Matrix: the three formula columns, recomputed through the shared kernel
    # the engine recomputes with.
    for unit in _units(ctx):
        derived = recompute_unit_derived(ctx, unit)
        for key, value in derived.items():
            if value is not None:
                unit[key] = value

    # The Commission Log: each unit's total split by its stated basis-point
    # weights, allocated so the splits sum to the total exactly.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _split_rows(ctx):
        unit_id = row.get("unit_id")
        if isinstance(unit_id, str):
            grouped.setdefault(unit_id, []).append(row)
    totals = {
        _unit_id(unit): unit.get("total_commission_cents") for unit in _units(ctx)
    }
    for unit_id, rows in grouped.items():
        total = totals.get(unit_id)
        if not isinstance(total, int):
            continue
        weights = [row["split_bps"] for row in rows]
        for row, cents in zip(rows, split_commission(total, weights), strict=True):
            row["split_cents"] = cents

    # The rollup: the three totals, derived from the Matrix they summarise.
    rollup["sold_unit_count"] = recompute_sold_count(ctx)
    revenue = recompute_revenue_totals(ctx)
    rollup["total_sales_price_cents"] = revenue["total_sales_price_cents"]
    rollup["total_net_proceeds_cents"] = revenue["total_net_proceeds_cents"]
    rollup["total_commission_cents"] = recompute_commission_total(ctx)


def baseline(portfolio: str, project: str) -> dict[str, Any]:
    """Build a clean sales file for ``portfolio`` / ``project``."""
    payload: dict[str, Any] = {
        "file_id": "clean",
        "portfolio": portfolio,
        "project": project,
        "market": MARKET,
        "period": PERIOD,
        "as_of": AS_OF,
        "max_discount_bps": MAX_DISCOUNT_BPS,
        "documents": [
            {
                "doc_type": DOC_PLAN_REGISTER,
                "document_id": "PLANS-2031",
                "plans": [
                    {
                        "plan_code": plan_code,
                        "plan_name": plan_name,
                        "plan_sqft": plan_sqft,
                    }
                    for plan_code, plan_name, plan_sqft in PLANS
                ],
            },
            {
                "doc_type": DOC_UNIT_MATRIX,
                "document_id": "MATRIX-2031",
                "units": [
                    {
                        "unit_id": unit_id,
                        "building": building,
                        "plan_code": plan_code,
                        "sale_channel": sale_channel,
                        "status": status,
                        "list_price_cents": d(list_price),
                        "sales_price_cents": d(sales_price),
                        "concession_cents": d(concession),
                        "closing_costs_cents": d(closing_costs),
                        "rev_per_sqft_cents": 0,
                        "total_commission_cents": 0,
                        "net_proceeds_cents": 0,
                    }
                    for (
                        unit_id, building, plan_code, sale_channel, status,
                        list_price, sales_price, concession, closing_costs,
                    ) in UNITS
                ],
            },
            {
                "doc_type": DOC_COMMISSION_SCHEDULE,
                "document_id": "COMMSCHED-2031",
                "rates": [
                    {"sale_channel": channel, "commission_rate_bps": rate_bps}
                    for channel, rate_bps in COMMISSION_SCHEDULE
                ],
            },
            {
                "doc_type": DOC_SOLD_CLOSE_LOG,
                "document_id": "SOLDCLOSE-2031",
                "closings": [
                    {
                        "unit_id": unit_id,
                        "offer_date": offer_date,
                        "actual_date_sold": actual_date_sold,
                        "closing_date": closing_date,
                        "proof_received": proof_received,
                    }
                    for (
                        unit_id, offer_date, actual_date_sold, closing_date,
                        proof_received,
                    ) in CLOSINGS
                ],
            },
            {
                "doc_type": DOC_AGENT_REGISTER,
                "document_id": "AGENTS-2031",
                "agents": [
                    {"agent_id": agent_id, "agent_name": agent_name}
                    for agent_id, agent_name in AGENTS
                ],
            },
            {
                "doc_type": DOC_COMMISSION_LOG,
                "document_id": "COMMLOG-2031",
                "splits": [
                    {
                        "unit_id": unit_id,
                        "agent_id": agent_id,
                        "split_bps": split_bps,
                        "split_cents": 0,
                    }
                    for unit_id, agent_id, split_bps in COMMISSION_SPLITS
                ],
            },
            {
                "doc_type": DOC_SALES_ROLLUP,
                "document_id": "ROLLUP-2031",
                "sold_unit_count": 0,
                "total_sales_price_cents": 0,
                "total_net_proceeds_cents": 0,
                "total_commission_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_SALES_ROLLUP
    ]


def _duplicate_plan_code(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_PLAN_REGISTER)
    assert register is not None
    register["plans"].append(dict(_plan(payload, "PL-A1")))


def _plan_sqft_zero(payload: dict[str, Any]) -> None:
    # The plan area is blanked to zero after the Matrix was struck, so the column
    # that divided by it still carries the figures it produced.
    _plan(payload, "PL-D4")["plan_sqft"] = 0


def _unit_missing_field(payload: dict[str, Any]) -> None:
    del _unit(payload, "UNIT-103")["building"]


def _duplicate_unit_id(payload: dict[str, Any]) -> None:
    # An unsold unit is copied, so nothing it carries moves a total.
    matrix = _doc(payload, DOC_UNIT_MATRIX)
    assert matrix is not None
    matrix["units"].append(dict(_unit(payload, "UNIT-107")))


def _unknown_plan_code(payload: dict[str, Any]) -> None:
    _unit(payload, "UNIT-107")["plan_code"] = "PL-Z9"


def _bad_unit_status(payload: dict[str, Any]) -> None:
    _unit(payload, "UNIT-106")["status"] = "pending"


def _rev_per_sqft_wrong(payload: dict[str, Any]) -> None:
    # One cell of the formula column typed over.
    _unit(payload, "UNIT-101")["rev_per_sqft_cents"] += d(1)


def _concession_exceeds_price(payload: dict[str, Any]) -> None:
    # The concession is entered above the price it discounts; the derived columns
    # are re-derived so only the concession control sees the break.
    unit = _unit(payload, "UNIT-103")
    unit["concession_cents"] = unit["sales_price_cents"] + 1
    rederive(payload)


def _net_proceeds_wrong(payload: dict[str, Any]) -> None:
    # The net-proceeds cell is typed over and the rollup is moved with it, so only
    # the re-derivation control sees the break.
    _unit(payload, "UNIT-105")["net_proceeds_cents"] -= d(500)
    _rollup(payload)["total_net_proceeds_cents"] -= d(500)


def _discount_over_band(payload: dict[str, Any]) -> None:
    # The list price is restated upward after the sale, widening the discount past
    # the approved band. No derived column reads the list price.
    _unit(payload, "UNIT-102")["list_price_cents"] = d(700_000)


def _channel_rate_missing(payload: dict[str, Any]) -> None:
    # The referral rate is dropped from the schedule; UNIT-104 was sold through it,
    # so its commission can no longer be re-derived.
    schedule = _doc(payload, DOC_COMMISSION_SCHEDULE)
    assert schedule is not None
    schedule["rates"] = [
        r for r in schedule["rates"] if r["sale_channel"] != CHANNEL_REFERRAL
    ]


def _commission_rate_wrong(payload: dict[str, Any]) -> None:
    # The schedule rate is edited after the Matrix was struck, so the commission
    # column no longer re-derives while every split still ties to it.
    _rate(payload, CHANNEL_CO_BROKE)["commission_rate_bps"] = 550


def _agent_split_short(payload: dict[str, Any]) -> None:
    _split(payload, "UNIT-105", "AG-02")["split_cents"] -= d(100)


def _unknown_agent(payload: dict[str, Any]) -> None:
    _split(payload, "UNIT-104", "AG-04")["agent_id"] = "AG-99"


def _close_row_missing(payload: dict[str, Any]) -> None:
    log = _doc(payload, DOC_SOLD_CLOSE_LOG)
    assert log is not None
    log["closings"] = [r for r in log["closings"] if r["unit_id"] != "UNIT-104"]


def _dates_out_of_order(payload: dict[str, Any]) -> None:
    # The sale is logged before the offer that produced it.
    _closing(payload, "UNIT-103")["actual_date_sold"] = "2030-11-20"


def _proof_not_received(payload: dict[str, Any]) -> None:
    _closing(payload, "UNIT-105")["proof_received"] = False


def _sold_count_wrong(payload: dict[str, Any]) -> None:
    _rollup(payload)["sold_unit_count"] += 1


def _revenue_total_wrong(payload: dict[str, Any]) -> None:
    _rollup(payload)["total_sales_price_cents"] -= d(1_000)


def _commission_total_overstated(payload: dict[str, Any]) -> None:
    _rollup(payload)["total_commission_cents"] += d(5_000)


def _amount_not_integer(payload: dict[str, Any]) -> None:
    unit = _unit(payload, "UNIT-101")
    unit["net_proceeds_cents"] = float(unit["net_proceeds_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_plan_code": ("plan_unique_codes", _duplicate_plan_code),
    "plan_sqft_zero": ("plan_sqft_positive", _plan_sqft_zero),
    "unit_missing_field": ("unit_required_fields", _unit_missing_field),
    "duplicate_unit_id": ("unit_unique_ids", _duplicate_unit_id),
    "unknown_plan_code": ("unit_plan_defined", _unknown_plan_code),
    "bad_unit_status": ("unit_status_valid", _bad_unit_status),
    "rev_per_sqft_wrong": ("price_rev_per_sqft_recomputes", _rev_per_sqft_wrong),
    "concession_exceeds_price": ("price_concession_within_price", _concession_exceeds_price),
    "net_proceeds_wrong": ("price_net_proceeds_recomputes", _net_proceeds_wrong),
    "discount_over_band": ("price_discount_to_list", _discount_over_band),
    "channel_rate_missing": ("comm_rate_defined", _channel_rate_missing),
    "commission_rate_wrong": ("comm_total_recomputes", _commission_rate_wrong),
    "agent_split_short": ("comm_splits_tie", _agent_split_short),
    "unknown_agent": ("comm_agent_known", _unknown_agent),
    "close_row_missing": ("close_sold_reconciles", _close_row_missing),
    "dates_out_of_order": ("close_date_order", _dates_out_of_order),
    "proof_not_received": ("close_proof_received", _proof_not_received),
    "sold_count_wrong": ("rpt_sold_count_ties", _sold_count_wrong),
    "revenue_total_wrong": ("rpt_revenue_ties", _revenue_total_wrong),
    "commission_total_overstated": ("rpt_commission_ties", _commission_total_overstated),
    "amount_not_integer": ("price_net_proceeds_recomputes", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(PORTFOLIOS[0], PROJECTS[0])
    clean["file_id"] = f"clean__{PORTFOLIOS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        portfolio = PORTFOLIOS[(i + 1) % len(PORTFOLIOS)]
        project = PROJECTS[(i + 1) % len(PROJECTS)]
        f = baseline(portfolio, project)
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
