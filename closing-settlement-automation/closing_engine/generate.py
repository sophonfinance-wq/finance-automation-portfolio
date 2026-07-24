"""
Fictional home-sale closing corpus generator.
==============================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The developers, the projects, the units, the sale
prices, the fees, the loan balances and the closing dates are fictional, and the
closing period is set in a fictional future. No real entity, person, project,
lender or path appears anywhere. The generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the units, the proforma assumptions and the settlement charge components are
stated as base facts. Everything the engine later checks as a recomputation --
each settlement total, each closing entry, the revenue lines, the loan ending
balances, the cost-of-sale relief, each unit's tie-out flag and the report
counts -- is recomputed by :func:`rederive` from those base facts, through the
*same* :mod:`closing_engine.settlement` primitives the engine recomputes with. So
the relationships the engine tests are the relationships that produced the data:
a defect that changes a base fact re-derives the rollup and keeps the break
confined; a defect that targets a stated figure edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from .engine import (
    _closed_units,
    _cos_for,
    _loan_for,
    _revenue_for,
    _settlement_for,
    _unit_id,
    recompute_closed_count,
    recompute_net_to_seller_total,
    recompute_unit_tied,
)
from .model import (
    ACCOUNT_ACCOUNTS_RECEIVABLE,
    DOC_CLOSING_JE_REGISTER,
    DOC_CLOSING_REPORT,
    DOC_CLOSING_SUMMARY,
    DOC_COS_SCHEDULE,
    DOC_LOAN_RELEASE_REGISTER,
    DOC_PROFORMA_ASSUMPTIONS,
    DOC_REVENUE_SCHEDULE,
    DOC_SETTLEMENT_REGISTER,
    DOC_UNIT_REGISTER,
    STATUS_CLOSED,
    STATUS_SOLD,
    STATUS_UNSOLD,
    Context,
)
from .money import apply_rate
from .settlement import (
    CHARGE_FIELDS,
    coe_month,
    loan_ending_balance,
    margin_bps,
    prepaid_commission_relieved,
    revised_project_profit,
)

#: Fictional developer labels, rotated for file identity only.
DEVELOPERS: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
)

#: Fictional project the closing file covers.
PROJECT = "Brightwater Commons"
PERIOD = "FY2029-Q1"

#: Proforma rate assumptions, in basis points.
BROKER_COMMISSION_BPS = 360
TOTAL_CLOSING_COSTS_BPS = 200
CONCESSIONS_BPS = 50
LISTING_SALES_FEE_BPS = 50
WARRANTY_RESERVE_BPS = 100

#: Prepaid commission balance carried on each closed unit.
PREPAID_BALANCE = 2_000_000

#: ``(unit_id, name, status, coe_date, gross_sales_cents, deferred_upgrade_cents)``.
#: Four homes reach close of escrow; one is under contract and one is unsold, and
#: neither of those carries a closing package.
UNITS: tuple[tuple[Any, ...], ...] = (
    ("U-101", "Brightwater Commons Lot 12", STATUS_CLOSED, "2029-01-15", 80_000_000, 1_500_000),
    ("U-102", "Brightwater Commons Lot 14", STATUS_CLOSED, "2029-01-22", 65_000_000, 900_000),
    ("U-103", "Brightwater Commons Lot 16", STATUS_CLOSED, "2029-02-05", 72_500_000, 1_200_000),
    ("U-104", "Brightwater Commons Lot 18", STATUS_CLOSED, "2029-02-18", 90_000_000, 2_000_000),
    ("U-105", "Brightwater Commons Lot 20", STATUS_SOLD, None, 0, 0),
    ("U-106", "Brightwater Commons Lot 22", STATUS_UNSOLD, None, 0, 0),
)

#: Fixed (non rate-derived) settlement charge components, in cents.
SETTLEMENT_CLOSING_FEE = 150_000
TITLE_INSURANCE = 200_000
EXCISE_TAX = 1_250_000
BANK_PROCESSING_FEE = 25_000
HOLDBACK = 500_000
REAL_ESTATE_TAXES = 120_000

#: Loan release base facts (cents), shared across the closed units.
LOAN_BEGINNING = 50_000_000
LOAN_DRAWS = 2_000_000
LOAN_INTEREST_FEES = 300_000
LOAN_BANK_REMITTANCE = 1_000_000
LOAN_PAYDOWNS = 500_000
LOAN_RELEASE_PRICE = 900_000

#: Cost-of-sale base facts (cents).
COS_PROJECTED_PROFIT = 10_000_000
COS_CARRY_COSTS = 500_000
COS_PROJECTED_NET_REVENUE = 70_000_000


def _components(gross: int) -> dict[str, int]:
    """The ten settlement charge components for a unit's gross sale price."""
    return {
        "broker_commission_cents": apply_rate(gross, BROKER_COMMISSION_BPS),
        "settlement_closing_fee_cents": SETTLEMENT_CLOSING_FEE,
        "title_insurance_cents": TITLE_INSURANCE,
        "excise_tax_cents": EXCISE_TAX,
        "bank_processing_fee_cents": BANK_PROCESSING_FEE,
        "concessions_cents": apply_rate(gross, 40),  # 0.40%, inside the 0.50% allowance
        "listing_sales_fee_cents": apply_rate(gross, LISTING_SALES_FEE_BPS),
        "warranty_reserve_cents": apply_rate(gross, WARRANTY_RESERVE_BPS),
        "holdback_cents": HOLDBACK,
        "real_estate_taxes_cents": REAL_ESTATE_TAXES,
    }


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _unit_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_UNIT_REGISTER)
    assert register is not None
    for row in register["units"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _settlement_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_SETTLEMENT_REGISTER)
    assert register is not None
    for row in register["settlements"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _je_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_CLOSING_JE_REGISTER)
    assert register is not None
    for row in register["entries"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _revenue_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_REVENUE_SCHEDULE)
    assert register is not None
    for row in register["entries"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _loan_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_LOAN_RELEASE_REGISTER)
    assert register is not None
    for row in register["releases"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _cos_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_COS_SCHEDULE)
    assert register is not None
    for row in register["entries"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _summary_row(payload: dict[str, Any], unit_id: str) -> dict[str, Any]:
    summary = _doc(payload, DOC_CLOSING_SUMMARY)
    assert summary is not None
    for row in summary["units"]:
        if row.get("unit_id") == unit_id:
            return row
    raise KeyError(unit_id)


def _report(payload: dict[str, Any]) -> dict[str, Any]:
    report = _doc(payload, DOC_CLOSING_REPORT)
    assert report is not None
    return report


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def _build_je_lines(gross: int, deferred: int, broker: int, charges: int) -> list[dict[str, Any]]:
    """The five-line balanced closing entry, with the receivable as the plug."""
    receivable = (gross + deferred) - charges
    return [
        {"account": "Residential Sales", "description": "Revenue recognized at close of escrow", "debit_cents": 0, "credit_cents": gross},
        {"account": "Upgrade Revenue", "description": "Deferred upgrade revenue reversed at closing", "debit_cents": 0, "credit_cents": deferred},
        {"account": "Broker Commission", "description": "Selling commission", "debit_cents": broker, "credit_cents": 0},
        {"account": "Closing Costs", "description": "Settlement charges excluding commission", "debit_cents": charges - broker, "credit_cents": 0},
        {"account": ACCOUNT_ACCOUNTS_RECEIVABLE, "description": "Net proceeds receivable from escrow", "debit_cents": receivable, "credit_cents": 0},
    ]


def rederive(payload: dict[str, Any]) -> None:
    """Recompute every derived figure from the payload's own base facts."""
    if not all(
        _doc(payload, dt) is not None
        for dt in (
            DOC_UNIT_REGISTER,
            DOC_PROFORMA_ASSUMPTIONS,
            DOC_SETTLEMENT_REGISTER,
            DOC_CLOSING_JE_REGISTER,
            DOC_REVENUE_SCHEDULE,
            DOC_LOAN_RELEASE_REGISTER,
            DOC_COS_SCHEDULE,
            DOC_CLOSING_SUMMARY,
            DOC_CLOSING_REPORT,
        )
    ):
        return

    ctx = Context(path=Path("<generated>"), data=payload)

    for unit in _closed_units(ctx):
        uid = _unit_id(unit)
        gross = int(unit["gross_sales_cents"])
        deferred = int(unit["deferred_upgrade_cents"])
        prepaid_balance = int(unit["prepaid_balance_cents"])
        coe = date.fromisoformat(unit["coe_date"])

        settlement = _settlement_row(payload, uid)
        components = [int(settlement[f]) for f in CHARGE_FIELDS]
        charges = sum(components)
        broker = components[0]
        settlement["total_settlement_charges_cents"] = charges
        settlement["total_closing_costs_cents"] = charges - broker
        settlement["net_to_seller_cents"] = gross - charges

        entry = _je_row(payload, uid)
        entry["lines"] = _build_je_lines(gross, deferred, broker, charges)

        revenue = _revenue_row(payload, uid)
        revenue["recognized_month"] = coe_month(coe)
        revenue["residential_sales_cents"] = gross
        revenue["deferred_upgrade_reversed_cents"] = deferred

        loan = _loan_row(payload, uid)
        ending = loan_ending_balance(
            int(loan["beginning_balance_cents"]),
            int(loan["draws_cents"]),
            int(loan["interest_fees_cents"]),
            int(loan["bank_remittance_cents"]),
            int(loan["paydowns_cents"]),
        )
        loan["ending_balance_cents"] = ending
        loan["lender_statement_ending_cents"] = ending

        cos = _cos_row(payload, uid)
        revised = revised_project_profit(
            int(cos["projected_profit_cents"]), int(cos["carry_costs_cents"])
        )
        cos["revised_profit_cents"] = revised
        cos["margin_bps"] = margin_bps(revised, int(cos["projected_net_revenue_cents"]))
        cos["prepaid_relieved_cents"] = prepaid_commission_relieved(
            int(cos["commission_earned_cents"]), prepaid_balance
        )

    summary = _doc(payload, DOC_CLOSING_SUMMARY)
    assert summary is not None
    summary["units"] = [
        {"unit_id": _unit_id(unit), "tied": recompute_unit_tied(ctx, unit)}
        for unit in _closed_units(ctx)
    ]

    report = _report(payload)
    report["closed_count"] = recompute_closed_count(ctx)
    report["total_net_to_seller_cents"] = recompute_net_to_seller_total(ctx)


def baseline(developer: str) -> dict[str, Any]:
    """Build a clean closing file for ``developer``."""
    closed = [u for u in UNITS if u[2] == STATUS_CLOSED]
    payload: dict[str, Any] = {
        "file_id": "clean",
        "developer": developer,
        "project": PROJECT,
        "period": PERIOD,
        "documents": [
            {
                "doc_type": DOC_UNIT_REGISTER,
                "document_id": "UNITS-2029",
                "units": [
                    {
                        "unit_id": unit_id,
                        "name": name,
                        "status": status,
                        "coe_date": coe_date,
                        "gross_sales_cents": gross,
                        "deferred_upgrade_cents": deferred,
                        "prepaid_balance_cents": PREPAID_BALANCE if status == STATUS_CLOSED else 0,
                    }
                    for unit_id, name, status, coe_date, gross, deferred in UNITS
                ],
            },
            {
                "doc_type": DOC_PROFORMA_ASSUMPTIONS,
                "document_id": "PROFORMA-2029",
                "broker_commission_bps": BROKER_COMMISSION_BPS,
                "total_closing_costs_bps": TOTAL_CLOSING_COSTS_BPS,
                "concessions_bps": CONCESSIONS_BPS,
                "listing_sales_fee_bps": LISTING_SALES_FEE_BPS,
                "warranty_reserve_bps": WARRANTY_RESERVE_BPS,
            },
            {
                "doc_type": DOC_SETTLEMENT_REGISTER,
                "document_id": "SETTLEMENT-2029",
                "settlements": [
                    {
                        "unit_id": unit_id,
                        **_components(gross),
                        "total_settlement_charges_cents": 0,
                        "total_closing_costs_cents": 0,
                        "net_to_seller_cents": 0,
                    }
                    for unit_id, _n, _s, _c, gross, _d in closed
                ],
            },
            {
                "doc_type": DOC_CLOSING_JE_REGISTER,
                "document_id": "CLOSING-JE-2029",
                "entries": [
                    {"unit_id": unit_id, "entry_id": f"JE-{unit_id}", "lines": []}
                    for unit_id, _n, _s, _c, _g, _d in closed
                ],
            },
            {
                "doc_type": DOC_REVENUE_SCHEDULE,
                "document_id": "REVREC-2029",
                "entries": [
                    {
                        "unit_id": unit_id,
                        "recognized_month": "",
                        "residential_sales_cents": 0,
                        "deferred_upgrade_reversed_cents": 0,
                    }
                    for unit_id, _n, _s, _c, _g, _d in closed
                ],
            },
            {
                "doc_type": DOC_LOAN_RELEASE_REGISTER,
                "document_id": "LOAN-2029",
                "releases": [
                    {
                        "unit_id": unit_id,
                        "beginning_balance_cents": LOAN_BEGINNING,
                        "draws_cents": LOAN_DRAWS,
                        "interest_fees_cents": LOAN_INTEREST_FEES,
                        "bank_remittance_cents": LOAN_BANK_REMITTANCE,
                        "paydowns_cents": LOAN_PAYDOWNS,
                        "release_price_cents": LOAN_RELEASE_PRICE,
                        "ending_balance_cents": 0,
                        "lender_statement_ending_cents": 0,
                    }
                    for unit_id, _n, _s, _c, _g, _d in closed
                ],
            },
            {
                "doc_type": DOC_COS_SCHEDULE,
                "document_id": "COS-2029",
                "entries": [
                    {
                        "unit_id": unit_id,
                        "projected_profit_cents": COS_PROJECTED_PROFIT,
                        "carry_costs_cents": COS_CARRY_COSTS,
                        "projected_net_revenue_cents": COS_PROJECTED_NET_REVENUE,
                        "commission_earned_cents": apply_rate(gross, BROKER_COMMISSION_BPS),
                        "revised_profit_cents": 0,
                        "margin_bps": 0,
                        "prepaid_relieved_cents": 0,
                    }
                    for unit_id, _n, _s, _c, gross, _d in closed
                ],
            },
            {
                "doc_type": DOC_CLOSING_SUMMARY,
                "document_id": "SUMMARY-2029",
                "units": [],
            },
            {
                "doc_type": DOC_CLOSING_REPORT,
                "document_id": "REPORT-2029",
                "closed_count": 0,
                "total_net_to_seller_cents": 0,
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_CLOSING_REPORT
    ]


def _duplicate_unit_id(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_UNIT_REGISTER)
    assert register is not None
    register["units"].append(dict(_unit_row(payload, "U-101")))


def _bad_unit_status(payload: dict[str, Any]) -> None:
    # The under-contract unit carries an unknown status; it holds no closing
    # package, so only the status vocabulary control sees it.
    _unit_row(payload, "U-105")["status"] = "pending"


def _unit_missing_field(payload: dict[str, Any]) -> None:
    del _unit_row(payload, "U-103")["coe_date"]


def _artifacts_incomplete(payload: dict[str, Any]) -> None:
    # A closed unit's settlement statement is off the register entirely.
    register = _doc(payload, DOC_SETTLEMENT_REGISTER)
    assert register is not None
    register["settlements"] = [
        s for s in register["settlements"] if s.get("unit_id") != "U-102"
    ]


def _je_unknown_unit(payload: dict[str, Any]) -> None:
    register = _doc(payload, DOC_CLOSING_JE_REGISTER)
    assert register is not None
    register["entries"].append(
        {
            "unit_id": "U-999",
            "entry_id": "JE-U-999",
            "lines": [
                {"account": "Residential Sales", "description": "orphan", "debit_cents": 0, "credit_cents": 100},
                {"account": ACCOUNT_ACCOUNTS_RECEIVABLE, "description": "orphan", "debit_cents": 100, "credit_cents": 0},
            ],
        }
    )


def _je_does_not_foot(payload: dict[str, Any]) -> None:
    # A non-receivable debit line is overstated, so the entry no longer balances.
    entry = _je_row(payload, "U-101")
    for line in entry["lines"]:
        if line["account"] == "Closing Costs":
            line["debit_cents"] += 1_000_000


def _ar_plug_wrong(payload: dict[str, Any]) -> None:
    entry = _je_row(payload, "U-102")
    for line in entry["lines"]:
        if line["account"] == ACCOUNT_ACCOUNTS_RECEIVABLE:
            line["debit_cents"] += 1_000_000


def _total_charges_wrong(payload: dict[str, Any]) -> None:
    _settlement_row(payload, "U-101")["total_settlement_charges_cents"] += 1_000_000


def _total_closing_costs_wrong(payload: dict[str, Any]) -> None:
    _settlement_row(payload, "U-102")["total_closing_costs_cents"] += 1_000_000


def _net_to_seller_wrong(payload: dict[str, Any]) -> None:
    _settlement_row(payload, "U-103")["net_to_seller_cents"] += 1_000_000


def _listing_off_rate(payload: dict[str, Any]) -> None:
    _settlement_row(payload, "U-101")["listing_sales_fee_cents"] += 100_000
    rederive(payload)


def _warranty_off_rate(payload: dict[str, Any]) -> None:
    _settlement_row(payload, "U-102")["warranty_reserve_cents"] += 100_000
    rederive(payload)


def _broker_commission_varies(payload: dict[str, Any]) -> None:
    # The commission is booked above the proforma rate; the rollup is re-derived
    # so only the variance FLAG remains.
    _settlement_row(payload, "U-103")["broker_commission_cents"] += 250_000
    rederive(payload)


def _concessions_over_allowance(payload: dict[str, Any]) -> None:
    # Concessions are lifted above the assumed allowance (0.60% > 0.50%).
    unit = _unit_row(payload, "U-104")
    _settlement_row(payload, "U-104")["concessions_cents"] = apply_rate(
        int(unit["gross_sales_cents"]), 60
    )
    rederive(payload)


def _revenue_wrong_month(payload: dict[str, Any]) -> None:
    _revenue_row(payload, "U-103")["recognized_month"] = "2029-03"


def _deferred_upgrade_wrong(payload: dict[str, Any]) -> None:
    _revenue_row(payload, "U-104")["deferred_upgrade_reversed_cents"] += 50_000


def _loan_ending_wrong(payload: dict[str, Any]) -> None:
    # The stated ending balance and the lender figure move together, so only the
    # roll-forward control -- not the tie -- sees the break.
    loan = _loan_row(payload, "U-101")
    loan["ending_balance_cents"] += 1_000_000
    loan["lender_statement_ending_cents"] += 1_000_000


def _loan_does_not_tie(payload: dict[str, Any]) -> None:
    _loan_row(payload, "U-102")["lender_statement_ending_cents"] += 1_000_000


def _release_price_short(payload: dict[str, Any]) -> None:
    loan = _loan_row(payload, "U-103")
    loan["release_price_cents"] = int(loan["bank_remittance_cents"]) + 100_000


def _cos_margin_wrong(payload: dict[str, Any]) -> None:
    _cos_row(payload, "U-101")["revised_profit_cents"] += 1_000_000


def _prepaid_relief_over_cap(payload: dict[str, Any]) -> None:
    _cos_row(payload, "U-102")["prepaid_relieved_cents"] += 100_000


def _closed_count_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["closed_count"] -= 1


def _net_total_wrong(payload: dict[str, Any]) -> None:
    _report(payload)["total_net_to_seller_cents"] += 1_000_000


def _tied_flag_wrong(payload: dict[str, Any]) -> None:
    _summary_row(payload, "U-101")["tied"] = False


def _amount_not_integer(payload: dict[str, Any]) -> None:
    settlement = _settlement_row(payload, "U-101")
    settlement["broker_commission_cents"] = float(settlement["broker_commission_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "duplicate_unit_id": ("unit_unique_ids", _duplicate_unit_id),
    "bad_unit_status": ("unit_status_valid", _bad_unit_status),
    "unit_missing_field": ("unit_required_fields", _unit_missing_field),
    "artifacts_incomplete": ("unit_artifacts_complete", _artifacts_incomplete),
    "je_unknown_unit": ("je_unit_exists", _je_unknown_unit),
    "je_does_not_foot": ("je_balances", _je_does_not_foot),
    "ar_plug_wrong": ("je_ar_plug_recomputes", _ar_plug_wrong),
    "total_charges_wrong": ("ss_total_charges_recompute", _total_charges_wrong),
    "total_closing_costs_wrong": ("ss_total_closing_costs_recompute", _total_closing_costs_wrong),
    "net_to_seller_wrong": ("ss_net_to_seller_recompute", _net_to_seller_wrong),
    "listing_off_rate": ("fee_listing_sales_rederives", _listing_off_rate),
    "warranty_off_rate": ("fee_warranty_reserve_rederives", _warranty_off_rate),
    "broker_commission_varies": ("fee_broker_commission_variance", _broker_commission_varies),
    "concessions_over_allowance": ("fee_concessions_within_assumption", _concessions_over_allowance),
    "revenue_wrong_month": ("rev_recognized_in_coe_month", _revenue_wrong_month),
    "deferred_upgrade_wrong": ("rev_deferred_upgrade_reversed", _deferred_upgrade_wrong),
    "loan_ending_wrong": ("loan_ending_recomputes", _loan_ending_wrong),
    "loan_does_not_tie": ("loan_ties_lender_statement", _loan_does_not_tie),
    "release_price_short": ("loan_release_price_covered", _release_price_short),
    "cos_margin_wrong": ("cos_margin_recompute", _cos_margin_wrong),
    "prepaid_relief_over_cap": ("cos_prepaid_commission_relief_cap", _prepaid_relief_over_cap),
    "closed_count_wrong": ("rpt_closed_count_ties", _closed_count_wrong),
    "net_total_wrong": ("rpt_net_to_seller_total_ties", _net_total_wrong),
    "tied_flag_wrong": ("rpt_unit_tied_recomputes", _tied_flag_wrong),
    "amount_not_integer": ("ss_total_charges_recompute", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(DEVELOPERS[0])
    clean["file_id"] = f"clean__{DEVELOPERS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        developer = DEVELOPERS[(i + 1) % len(DEVELOPERS)]
        f = baseline(developer)
        f["file_id"] = f"{name}__{developer.replace(' ', '_')}"
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
