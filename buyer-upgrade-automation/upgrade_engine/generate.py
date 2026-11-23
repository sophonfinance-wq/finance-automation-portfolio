"""
Fictional buyer-upgrade book generator.
=======================================

Builds a byte-stable corpus for the engine to analyze. One book is clean; every
other carries exactly **one** planted defect, so a test can assert that a given
rule fires on its own book.

Everything here is invented. The projects, buyers, vendors and unit numbers are
fictional, the periods are set in a fictional future, and no real person,
document, entity or path appears anywhere. The generator is deterministic and
takes no seed: given the same source it writes byte-identical files.

The baseline is derived, not typed
----------------------------------
Only the units and their upgrade orders are stated. Everything downstream --
contracted totals per unit, the recognised/deferred split, sales tax, the
cost-to-complete rows and totals, the proforma lines, and all five ledger
balances -- is computed from them. A book that has to satisfy twenty interlocking
tie-outs cannot be maintained by hand without rotting the first time a rule is
added.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import (
    ACCT_CONTRA_WIP,
    ACCT_COST_OF_SALES,
    ACCT_REVENUE,
    ACCT_SALES_TAX,
    ACCT_UNEARNED,
    DOC_CLOSINGS_SCHEDULE,
    DOC_COST_TO_COMPLETE,
    DOC_LEDGER_BALANCES,
    DOC_PROFORMA,
    DOC_UPGRADE_REGISTER,
)
from .money import apply_rate

PROJECTS: tuple[str, ...] = (
    "Alderpoint Terraces",
    "Brightwater Commons",
    "Copperfield Yards",
    "Dunmore Flats",
)
PERIOD = "2027-04"
SALES_TAX_RATE_BPS = 950  # 9.50%, fictional
COST_RATIO_BPS = 6000     # upgrade cost runs about 60% of upgrade price


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


#: ``(unit, closed, close_date)``
UNITS: tuple[tuple[str, bool, str | None], ...] = (
    ("U-01", True, "2027-04-08"),
    ("U-02", True, "2027-04-15"),
    ("U-03", False, None),
    ("U-04", False, None),
    ("U-05", True, "2027-04-22"),
    ("U-06", False, None),
)

#: ``(order_id, unit, price_dollars, selection)``
ORDERS: tuple[tuple[str, str, float, str], ...] = (
    ("O-1001", "U-01", 28_000, "Kitchen package, quartz surfaces"),
    ("O-1002", "U-02", 16_500, "Flooring upgrade throughout"),
    ("O-1003", "U-02", 9_200, "Bathroom fixture package"),
    ("O-1004", "U-03", 22_000, "Kitchen package, appliance tier 2"),
    ("O-1005", "U-04", 12_750, "Built-in cabinetry, study"),
    ("O-1006", "U-05", 34_400, "Whole-home package, tier 3"),
)


def _contracted() -> dict[str, int]:
    """Upgrade value contracted per unit, in cents."""
    out: dict[str, int] = {u: 0 for u, _c, _dt in UNITS}
    for _oid, unit, price, _sel in ORDERS:
        out[unit] = out.get(unit, 0) + d(price)
    return out


def _closed_units() -> set[str]:
    return {u for u, closed, _dt in UNITS if closed}


# --------------------------------------------------------------------------- #
# Artifact builders
# --------------------------------------------------------------------------- #
def _closings_schedule() -> dict[str, Any]:
    contracted, closed = _contracted(), _closed_units()
    units = []
    for unit, is_closed, close_date in UNITS:
        total = contracted[unit]
        units.append({
            "unit": unit,
            "buyer": f"Buyer {unit[-2:]}",
            "closed": is_closed,
            "close_date": close_date,
            "revenue_recognised_cents": total if is_closed else 0,
            "deferred_balance_cents": 0 if is_closed else total,
        })
    return {
        "doc_type": DOC_CLOSINGS_SCHEDULE,
        "document_id": f"CLS-{PERIOD}",
        "period": PERIOD,
        "units": units,
        "closed_count": len(closed),
    }


def _upgrade_register() -> dict[str, Any]:
    orders = []
    for oid, unit, price, selection in ORDERS:
        price_c = d(price)
        orders.append({
            "order_id": oid,
            "unit": unit,
            "selection": selection,
            "price_cents": price_c,
            "sales_tax_cents": apply_rate(price_c, SALES_TAX_RATE_BPS),
            "ordered_date": "2027-01-18",
        })
    return {
        "doc_type": DOC_UPGRADE_REGISTER,
        "document_id": f"UPR-{PERIOD}",
        "period": PERIOD,
        "sales_tax_rate_bps": SALES_TAX_RATE_BPS,
        "orders": orders,
    }


def _cost_to_complete() -> dict[str, Any]:
    contracted, closed = _contracted(), _closed_units()
    units = []
    for unit, is_closed, _dt in UNITS:
        revenue = contracted[unit]
        committed = apply_rate(revenue, COST_RATIO_BPS)
        # A closed unit has incurred its whole committed cost and relieved it to
        # cost of sales; an open one is part-way through and has relieved nothing.
        costs_to_date = committed if is_closed else apply_rate(committed, 4500)
        units.append({
            "unit": unit,
            "net_upgrade_revenue_cents": revenue,
            "budgeted_cost_cents": committed,
            "committed_cost_cents": committed,
            "costs_to_date_cents": costs_to_date,
            "cost_of_sales_cents": committed if is_closed else 0,
            "change_order_ref": None,
            "revenue_basis": "actual" if is_closed else "budgeted",
        })
    keys = ("net_upgrade_revenue_cents", "costs_to_date_cents", "committed_cost_cents")
    return {
        "doc_type": DOC_COST_TO_COMPLETE,
        "document_id": f"CTC-{PERIOD}",
        "period": PERIOD,
        "cost_code": "19-100",
        "units": units,
        "totals": {k: sum(u[k] for u in units) for k in keys},
        "closed_count": len(closed),
    }


def _proforma() -> dict[str, Any]:
    ctc = _cost_to_complete()
    income = ctc["totals"]["net_upgrade_revenue_cents"]
    # The proforma posts cost to a job-cost line as a negative, so income and
    # cost sum directly on the variance tab.
    costs = -ctc["totals"]["costs_to_date_cents"]
    return {
        "doc_type": DOC_PROFORMA,
        "document_id": f"PFA-{PERIOD}",
        "period": PERIOD,
        "upgrade_income_cents": income,
        "upgrade_costs_to_date_cents": costs,
        "variance_tab_net_cents": income + costs,
    }


def _ledger_balances() -> dict[str, Any]:
    schedule = _closings_schedule()
    register = _upgrade_register()
    ctc = _cost_to_complete()
    deferred = sum(u["deferred_balance_cents"] for u in schedule["units"])
    revenue = sum(u["revenue_recognised_cents"] for u in schedule["units"])
    cos = sum(u["cost_of_sales_cents"] for u in ctc["units"])
    tax = sum(o["sales_tax_cents"] for o in register["orders"])
    return {
        "doc_type": DOC_LEDGER_BALANCES,
        "document_id": f"LGR-{PERIOD}",
        "period": PERIOD,
        "accounts": [
            {"account": ACCT_UNEARNED, "balance_cents": deferred},
            {"account": ACCT_REVENUE, "balance_cents": revenue},
            {"account": ACCT_COST_OF_SALES, "balance_cents": cos},
            # Contra-WIP is a credit, so it offsets cost of sales to zero.
            {"account": ACCT_CONTRA_WIP, "balance_cents": -cos},
            {"account": ACCT_SALES_TAX, "balance_cents": tax},
        ],
    }


def baseline(project: str) -> dict[str, Any]:
    """A complete, internally consistent upgrade book that passes every control."""
    return {
        "book_id": f"{project.replace(' ', '_')}__{PERIOD}",
        "project": project,
        "period": PERIOD,
        "documents": [
            _closings_schedule(),
            _upgrade_register(),
            _cost_to_complete(),
            _proforma(),
            _ledger_balances(),
        ],
    }


# --------------------------------------------------------------------------- #
# Defect mutations -- exactly one surgical change each
# --------------------------------------------------------------------------- #
def _doc(bk: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(x for x in bk["documents"] if x["doc_type"] == doc_type)


def _unit(bk: dict[str, Any], doc_type: str, unit: str) -> dict[str, Any]:
    return next(u for u in _doc(bk, doc_type)["units"] if u["unit"] == unit)


def _acct(bk: dict[str, Any], name: str) -> dict[str, Any]:
    return next(a for a in _doc(bk, DOC_LEDGER_BALANCES)["accounts"]
                if a["account"] == name)


def _drop_document(bk: dict[str, Any]) -> None:
    bk["documents"] = [x for x in bk["documents"] if x["doc_type"] != DOC_PROFORMA]


def _period_drift(bk: dict[str, Any]) -> None:
    _doc(bk, DOC_COST_TO_COMPLETE)["period"] = "2027-03"


def _orphan_unit(bk: dict[str, Any]) -> None:
    _doc(bk, DOC_UPGRADE_REGISTER)["orders"][3]["unit"] = "U-99"


def _duplicate_order(bk: dict[str, Any]) -> None:
    reg = _doc(bk, DOC_UPGRADE_REGISTER)
    reg["orders"].append(dict(reg["orders"][0]))


def _closed_no_date(bk: dict[str, Any]) -> None:
    _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-02")["close_date"] = None


def _early_recognition(bk: dict[str, Any]) -> None:
    u = _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-03")
    u["revenue_recognised_cents"] = u["deferred_balance_cents"]
    u["deferred_balance_cents"] = 0


def _unit_total_off(bk: dict[str, Any]) -> None:
    _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-04")["deferred_balance_cents"] += d(500)


def _deferred_vs_ledger(bk: dict[str, Any]) -> None:
    _acct(bk, ACCT_UNEARNED)["balance_cents"] += d(1_250)


def _revenue_vs_ledger(bk: dict[str, Any]) -> None:
    _acct(bk, ACCT_REVENUE)["balance_cents"] -= d(900)


def _entry_unbalanced(bk: dict[str, Any]) -> None:
    _acct(bk, ACCT_CONTRA_WIP)["balance_cents"] += d(2_000)


def _cost_before_close(bk: dict[str, Any]) -> None:
    u = _unit(bk, DOC_COST_TO_COMPLETE, "U-03")
    u["cost_of_sales_cents"] = u["costs_to_date_cents"]


def _cost_overrun(bk: dict[str, Any]) -> None:
    u = _unit(bk, DOC_COST_TO_COMPLETE, "U-04")
    u["costs_to_date_cents"] = u["committed_cost_cents"] + d(1_800)
    ctc = _doc(bk, DOC_COST_TO_COMPLETE)
    ctc["totals"]["costs_to_date_cents"] = sum(
        x["costs_to_date_cents"] for x in ctc["units"])
    pf = _doc(bk, DOC_PROFORMA)
    pf["upgrade_costs_to_date_cents"] = -ctc["totals"]["costs_to_date_cents"]
    pf["variance_tab_net_cents"] = (
        pf["upgrade_income_cents"] + pf["upgrade_costs_to_date_cents"])


def _no_change_order(bk: dict[str, Any]) -> None:
    u = _unit(bk, DOC_COST_TO_COMPLETE, "U-05")
    u["committed_cost_cents"] = u["budgeted_cost_cents"] + d(2_400)
    ctc = _doc(bk, DOC_COST_TO_COMPLETE)
    ctc["totals"]["committed_cost_cents"] = sum(
        x["committed_cost_cents"] for x in ctc["units"])


def _tax_wrong(bk: dict[str, Any]) -> None:
    _doc(bk, DOC_UPGRADE_REGISTER)["orders"][2]["sales_tax_cents"] += d(40)


def _tax_in_revenue(bk: dict[str, Any]) -> None:
    _acct(bk, ACCT_SALES_TAX)["balance_cents"] -= d(300)


def _ctc_vs_proforma_rev(bk: dict[str, Any]) -> None:
    pf = _doc(bk, DOC_PROFORMA)
    pf["upgrade_income_cents"] += d(1_500)
    pf["variance_tab_net_cents"] = (
        pf["upgrade_income_cents"] + pf["upgrade_costs_to_date_cents"])


def _ctc_vs_proforma_cost(bk: dict[str, Any]) -> None:
    pf = _doc(bk, DOC_PROFORMA)
    pf["upgrade_costs_to_date_cents"] += d(700)
    pf["variance_tab_net_cents"] = (
        pf["upgrade_income_cents"] + pf["upgrade_costs_to_date_cents"])


def _proforma_vs_variance(bk: dict[str, Any]) -> None:
    _doc(bk, DOC_PROFORMA)["variance_tab_net_cents"] += d(325)


def _ctc_no_foot(bk: dict[str, Any]) -> None:
    _doc(bk, DOC_COST_TO_COMPLETE)["totals"]["committed_cost_cents"] += d(650)


def _stale_basis(bk: dict[str, Any]) -> None:
    _unit(bk, DOC_COST_TO_COMPLETE, "U-01")["revenue_basis"] = "budgeted"


def _amount_not_integer(bk: dict[str, Any]) -> None:
    _doc(bk, DOC_UPGRADE_REGISTER)["orders"][0]["price_cents"] = 2800000.5


#: ``name -> (rule the book is built to trip, mutation)``
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _drop_document),
    "period_drift": ("set_period_aligned", _period_drift),
    "orphan_unit": ("unit_upgrade_maps_to_a_unit", _orphan_unit),
    "duplicate_order": ("unit_no_duplicate_orders", _duplicate_order),
    "closed_no_date": ("unit_closed_has_close_date", _closed_no_date),
    "early_recognition": ("def_released_only_on_close", _early_recognition),
    "unit_total_off": ("def_unit_total_is_deposit", _unit_total_off),
    "deferred_vs_ledger": ("def_schedule_ties_ledger", _deferred_vs_ledger),
    "revenue_vs_ledger": ("def_revenue_ties_ledger", _revenue_vs_ledger),
    "entry_unbalanced": ("cos_entry_balances", _entry_unbalanced),
    "cost_before_close": ("cos_only_closed_units_costed", _cost_before_close),
    "cost_overrun": ("cos_costs_within_committed", _cost_overrun),
    "no_change_order": ("cos_change_order_referenced", _no_change_order),
    "tax_wrong": ("tax_derived_from_rate", _tax_wrong),
    "tax_in_revenue": ("tax_not_recognised_as_revenue", _tax_in_revenue),
    "ctc_vs_proforma_rev": ("tie_ctc_revenue_to_proforma", _ctc_vs_proforma_rev),
    "ctc_vs_proforma_cost": ("tie_ctc_costs_to_proforma", _ctc_vs_proforma_cost),
    "proforma_vs_variance": ("tie_proforma_to_variance", _proforma_vs_variance),
    "ctc_no_foot": ("tie_ctc_units_foot", _ctc_no_foot),
    "stale_basis": ("flag_actual_on_closed_units", _stale_basis),
    "amount_not_integer": ("tax_derived_from_rate", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    books: list[dict[str, Any]] = []
    clean = baseline(PROJECTS[0])
    clean["book_id"] = f"clean__{PROJECTS[0].replace(' ', '_')}"
    books.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        project = PROJECTS[(i + 1) % len(PROJECTS)]
        bk = baseline(project)
        bk["book_id"] = f"{name}__{project.replace(' ', '_')}"
        bk["planted_defect"] = name
        mutate(bk)
        books.append(bk)

    for bk in books:
        path = folder / f"{bk['book_id']}.json"
        path.write_text(
            json.dumps(bk, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return sorted(written)
