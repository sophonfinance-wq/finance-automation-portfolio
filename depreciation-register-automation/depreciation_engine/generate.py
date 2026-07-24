"""
Fictional depreciation & prepaid amortization close-file corpus generator.
==========================================================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The entities, the projects, the vendors, the asset
descriptions, the account numbers, every cost, life, window and balance are
fictional, and the close month is set in a fictional future. No real entity,
person, vendor, project or path appears anywhere. The generator is deterministic
and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the base facts are stated: each asset's cost, class, method, in-service
month and life, each prepaid item's additions and amortization window, the
policy threshold and the disposal facts. Every derived column the engine later
re-checks -- the monthly charge, months used, accumulated depreciation, the
close-month expense, NBV, the end-of-depreciation month, the prepaid waterfall
figures, the roll-forwards, the GL control balances and the recurring JE -- is
computed by the *same* :mod:`depreciation_engine.schedule` kernel the engine
recomputes with. So the relationships the engine tests are the relationships
that produced the data: a defect that changes a base fact re-derives the row and
the rollups and keeps the break confined to one control; a defect that targets a
stated derived figure edits that figure alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import (
    DOC_ASSET_REGISTER,
    DOC_CAP_POLICY,
    DOC_DISPOSAL_REGISTER,
    DOC_GL_BALANCES,
    DOC_LIFE_TABLE,
    DOC_PREPAID_REGISTER,
    DOC_RECURRING_JE,
    DOC_ROLLFORWARD,
    GL_ACCUM,
    GL_COST,
    GL_PREPAID,
    JE_AMORTIZATION,
    JE_DEPRECIATION,
    LIFE_SOURCE_FIXED,
    LIFE_SOURCE_LEASE_TERM,
    METHOD_STRAIGHT_LINE,
)
from .schedule import (
    accum_dep_cents,
    amort_expense_cents,
    depr_expense_cents,
    end_depr_month,
    monthly_amort_cents,
    monthly_dep_cents,
    month_str,
    months_used,
    nbv_cents,
    parse_month,
    prepaid_beginning_cents,
    prepaid_ending_cents,
    window_periods,
)

#: Fictional entity labels, rotated for file identity only.
ENTITIES: tuple[str, ...] = (
    "Northmoor Development Group",
    "Halbrook Residential",
    "Stonecrest Communities",
    "Ardenne Field Partners",
    "Westmere Homes",
)

PERIOD = "FY2030"
#: The close month every derivation and date gate is measured to.
CLOSE_MONTH = "2029-06"
#: Months an asset may sit fully depreciated before the disposal watch flags it.
DISPOSAL_REVIEW_MONTHS = 12
#: Look-ahead window, in months, for the prepaid window-ending watch.
PREPAID_WATCH_MONTHS = 1
#: Capitalization threshold: items below this are expensed, never capitalized.
THRESHOLD_CENTS = 50_000  # 500.00 (fictional currency)
#: Categories excluded from capitalization outright, whatever they cost.
EXCLUDED_CATEGORIES: tuple[str, ...] = ("annual_software",)


#: ``(asset_class, life_source, life_months)``. The class table the register
#: must key its lives off. Leasehold improvements have no fixed life -- they
#: depreciate over each asset's own stated lease term.
LIFE_TABLE: tuple[tuple[str, str, int | None], ...] = (
    ("computer_equipment", LIFE_SOURCE_FIXED, 36),
    ("software", LIFE_SOURCE_FIXED, 36),
    ("office_furniture", LIFE_SOURCE_FIXED, 84),
    ("automobile", LIFE_SOURCE_FIXED, 60),
    ("leasehold_improvements", LIFE_SOURCE_LEASE_TERM, None),
)

#: ``(asset_id, description, project, asset_class, cost_cents, in_service_month,
#:   useful_life_months, lease_term_months)``. Base facts only -- every derived
#: column is computed through the kernel. The mix covers each lifecycle stage:
#: mid-life assets, one asset recently fully depreciated (inside the
#: disposal-review band), and one staged asset not yet in service.
ASSETS: tuple[tuple[Any, ...], ...] = (
    ("FA-101", "Kestrelwood Systems rack server", "Brightwater Commons", "computer_equipment", 1_260_000, "2027-03", 36, None),
    ("FA-102", "Vellhurst Office Interiors suite fit-out furniture", "Brightwater Commons", "office_furniture", 1_403_072, "2023-09", 84, None),
    ("FA-103", "Site pool vehicle", "Dunmore Flats", "automobile", 3_840_000, "2028-11", 60, None),
    ("FA-104", "Copperline IT Supply site laptops (4)", "Copperfield Yards", "computer_equipment", 504_000, "2026-04", 36, None),
    ("FA-105", "Alderpoint Terraces office buildout", "Alderpoint Terraces", "leasehold_improvements", 5_760_000, "2027-07", 96, 96),
    ("FA-106", "Copperline IT Supply wide-format plotter (staged)", "Copperfield Yards", "computer_equipment", 210_000, "2029-08", 36, None),
)

#: ``(item_id, description, cost_cents, category, capitalized)``. The expense
#: log carried inside the capitalization policy: small purchases that were
#: (correctly) expensed, each sitting on the right side of the gate.
EXPENSE_ITEMS: tuple[tuple[Any, ...], ...] = (
    ("EX-201", "Break-room kettle and fittings", 18_000, "equipment", False),
    ("EX-202", "Alderleaf annual software subscription", 390_000, "annual_software", False),
    ("EX-203", "Vellhurst task chairs (4)", 46_000, "furniture", False),
)

#: ``(item_id, description, vendor, additions_cents, window_start, window_end,
#:   booked_from)``. Base facts only. PP-402 is set up one month after its
#: window opens, so the clean baseline itself carries a first-month catch-up
#: charge; PP-404 is paid ahead of a window that has not opened yet, so it sits
#: at full balance with zero expense.
PREPAIDS: tuple[tuple[Any, ...], ...] = (
    ("PP-401", "Harborline Title & Escrow annual policy fee", "Harborline Title & Escrow", 900_000, "2028-11", "2029-10", "2028-11"),
    ("PP-402", "Dealtrack pipeline software licence", "Kestrelwood Systems", 1_858_560, "2029-05", "2030-04", "2029-06"),
    ("PP-403", "Broker commission - Dunmore Flats", "Stonebriar Realty Advisors", 4_402_500, "2029-01", "2033-12", "2029-01"),
    ("PP-404", "State of Marran business licence", "State of Marran", 144_000, "2029-09", "2030-08", "2029-09"),
)

#: ``(asset_id, description, disposal_month, cost_cents, accum_at_disposal_cents)``.
#: The write-off is derived (cost less accumulated), never stated as a fact.
DISPOSALS: tuple[tuple[Any, ...], ...] = (
    ("FA-090", "Kestrelwood analytics platform buildout", "2029-04", 4_176_000, 3_248_000),
)


# --------------------------------------------------------------------------- #
# Payload accessors
# --------------------------------------------------------------------------- #
def _doc(payload: dict[str, Any], doc_type: str) -> dict[str, Any] | None:
    for doc in payload.get("documents", []):
        if isinstance(doc, dict) and doc.get("doc_type") == doc_type:
            return doc
    return None


def _asset(payload: dict[str, Any], asset_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_ASSET_REGISTER)
    assert register is not None
    for row in register["assets"]:
        if row.get("asset_id") == asset_id:
            return row
    raise KeyError(asset_id)


def _prepaid(payload: dict[str, Any], item_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_PREPAID_REGISTER)
    assert register is not None
    for row in register["items"]:
        if row.get("item_id") == item_id:
            return row
    raise KeyError(item_id)


def _expense_item(payload: dict[str, Any], item_id: str) -> dict[str, Any]:
    policy = _doc(payload, DOC_CAP_POLICY)
    assert policy is not None
    for row in policy["items"]:
        if row.get("item_id") == item_id:
            return row
    raise KeyError(item_id)


def _disposal(payload: dict[str, Any], asset_id: str) -> dict[str, Any]:
    register = _doc(payload, DOC_DISPOSAL_REGISTER)
    assert register is not None
    for row in register["disposals"]:
        if row.get("asset_id") == asset_id:
            return row
    raise KeyError(asset_id)


def _gl_row(payload: dict[str, Any], account: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_GL_BALANCES)
    assert doc is not None
    for row in doc["accounts"]:
        if row.get("account") == account:
            return row
    raise KeyError(account)


def _je_row(payload: dict[str, Any], line_id: str) -> dict[str, Any]:
    doc = _doc(payload, DOC_RECURRING_JE)
    assert doc is not None
    for row in doc["lines"]:
        if row.get("line_id") == line_id:
            return row
    raise KeyError(line_id)


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def rederive_asset_row(row: dict[str, Any], close_month: str = CLOSE_MONTH) -> None:
    """Recompute one asset's derived columns from its base facts, via the kernel.

    Used by the baseline builder and by defects that change a base fact (a life,
    a class, an in-service month) so the row stays self-consistent and the break
    stays confined to the control the defect targets.
    """
    close = parse_month(close_month)
    cost = row["cost_cents"]
    life = row["useful_life_months"]
    in_service = parse_month(row["in_service_month"])
    assert close is not None and in_service is not None
    row["monthly_dep_cents"] = monthly_dep_cents(cost, life)
    row["months_used"] = months_used(in_service, close, life)
    row["accum_dep_cents"] = accum_dep_cents(cost, life, in_service, close)
    row["depr_exp_cents"] = depr_expense_cents(cost, life, in_service, close)
    row["nbv_cents"] = nbv_cents(cost, row["accum_dep_cents"])
    row["end_depr_month"] = month_str(end_depr_month(in_service, life))


def rederive_prepaid_row(row: dict[str, Any], close_month: str = CLOSE_MONTH) -> None:
    """Recompute one prepaid item's waterfall columns from its base facts."""
    close = parse_month(close_month)
    start = parse_month(row["window_start"])
    end = parse_month(row["window_end"])
    booked = parse_month(row["booked_from"])
    assert close is not None and start is not None and end is not None and booked is not None
    additions = row["additions_cents"]
    row["monthly_amort_cents"] = monthly_amort_cents(additions, window_periods(start, end))
    row["beginning_balance_cents"] = prepaid_beginning_cents(additions, start, end, booked, close)
    row["amort_this_period_cents"] = amort_expense_cents(additions, start, end, booked, close)
    row["ending_balance_cents"] = prepaid_ending_cents(additions, start, end, booked, close)


def rederive(payload: dict[str, Any]) -> None:
    """Recompute the rollups -- roll-forwards, GL balances, recurring JE -- from
    the registers' stated columns.

    Deliberately reads the *stated* register columns rather than re-deriving
    them from base facts: the rollups summarise the register as it stands, so a
    defect planted in one stated column stays confined to the control that
    re-derives that column, while the tie-outs stay clean.
    """
    asset_doc = _doc(payload, DOC_ASSET_REGISTER)
    prepaid_doc = _doc(payload, DOC_PREPAID_REGISTER)
    roll = _doc(payload, DOC_ROLLFORWARD)
    gl = _doc(payload, DOC_GL_BALANCES)
    je = _doc(payload, DOC_RECURRING_JE)
    if not all((asset_doc, prepaid_doc, roll, gl, je)):
        return
    assert asset_doc is not None and prepaid_doc is not None
    assert roll is not None and gl is not None and je is not None

    cost_total = sum(a["cost_cents"] for a in asset_doc["assets"])
    accum_total = sum(a["accum_dep_cents"] for a in asset_doc["assets"])
    exp_total = sum(a["depr_exp_cents"] for a in asset_doc["assets"])
    begin_total = sum(p["beginning_balance_cents"] for p in prepaid_doc["items"])
    amort_total = sum(p["amort_this_period_cents"] for p in prepaid_doc["items"])
    ending_total = sum(p["ending_balance_cents"] for p in prepaid_doc["items"])

    # No disposal fell inside the close month itself, so nothing rolled off this
    # period; the opening balance is whatever closes back through the identity.
    roll["fixed_assets"] = {
        "opening_accum_cents": accum_total - exp_total,
        "depreciation_cents": exp_total,
        "disposal_accum_removed_cents": 0,
        "closing_accum_cents": accum_total,
    }
    roll["prepaid"] = {
        "opening_cents": begin_total,
        "additions_cents": ending_total + amort_total - begin_total,
        "amort_cents": amort_total,
        "closing_cents": ending_total,
    }

    _gl_row(payload, GL_COST)["balance_cents"] = cost_total
    _gl_row(payload, GL_ACCUM)["balance_cents"] = accum_total
    _gl_row(payload, GL_PREPAID)["balance_cents"] = ending_total

    _je_row(payload, JE_DEPRECIATION)["amount_cents"] = exp_total
    _je_row(payload, JE_AMORTIZATION)["amount_cents"] = amort_total


def baseline(entity: str) -> dict[str, Any]:
    """Build a clean close file for ``entity``."""
    assets: list[dict[str, Any]] = []
    for asset_id, description, project, cls, cost, in_service, life, lease in ASSETS:
        row: dict[str, Any] = {
            "asset_id": asset_id,
            "description": description,
            "project": project,
            "asset_class": cls,
            "method": METHOD_STRAIGHT_LINE,
            "cost_cents": cost,
            "in_service_month": in_service,
            "useful_life_months": life,
        }
        if lease is not None:
            row["lease_term_months"] = lease
        rederive_asset_row(row)
        assets.append(row)

    prepaids: list[dict[str, Any]] = []
    for item_id, description, vendor, additions, start, end, booked in PREPAIDS:
        row = {
            "item_id": item_id,
            "description": description,
            "vendor": vendor,
            "additions_cents": additions,
            "window_start": start,
            "window_end": end,
            "booked_from": booked,
        }
        rederive_prepaid_row(row)
        prepaids.append(row)

    disposals: list[dict[str, Any]] = []
    for asset_id, description, month, cost, accum in DISPOSALS:
        disposals.append(
            {
                "asset_id": asset_id,
                "description": description,
                "disposal_month": month,
                "cost_cents": cost,
                "accum_at_disposal_cents": accum,
                "writeoff_cents": cost - accum,
            }
        )

    payload: dict[str, Any] = {
        "file_id": "clean",
        "entity": entity,
        "period": PERIOD,
        "close_month": CLOSE_MONTH,
        "disposal_review_months": DISPOSAL_REVIEW_MONTHS,
        "prepaid_watch_months": PREPAID_WATCH_MONTHS,
        "documents": [
            {
                "doc_type": DOC_ASSET_REGISTER,
                "document_id": "FAR-2029-06",
                "assets": assets,
            },
            {
                "doc_type": DOC_LIFE_TABLE,
                "document_id": "LIVES-2029",
                "classes": [
                    {
                        "asset_class": cls,
                        "method": METHOD_STRAIGHT_LINE,
                        "life_source": source,
                        "life_months": life,
                    }
                    for cls, source, life in LIFE_TABLE
                ],
            },
            {
                "doc_type": DOC_CAP_POLICY,
                "document_id": "CAP-2029",
                "threshold_cents": THRESHOLD_CENTS,
                "excluded_categories": list(EXCLUDED_CATEGORIES),
                "items": [
                    {
                        "item_id": item_id,
                        "description": description,
                        "cost_cents": cost,
                        "category": category,
                        "capitalized": capitalized,
                    }
                    for item_id, description, cost, category, capitalized in EXPENSE_ITEMS
                ],
            },
            {
                "doc_type": DOC_PREPAID_REGISTER,
                "document_id": "PPD-2029-06",
                "items": prepaids,
            },
            {
                "doc_type": DOC_DISPOSAL_REGISTER,
                "document_id": "DISP-2029",
                "disposals": disposals,
            },
            {
                "doc_type": DOC_ROLLFORWARD,
                "document_id": "ROLL-2029-06",
                "fixed_assets": {},
                "prepaid": {},
            },
            {
                "doc_type": DOC_GL_BALANCES,
                "document_id": "GL-2029-06",
                "accounts": [
                    {"account": GL_COST, "name": "Fixed assets - cost", "balance_cents": 0},
                    {"account": GL_ACCUM, "name": "Accumulated depreciation", "balance_cents": 0},
                    {"account": GL_PREPAID, "name": "Prepaid expenses", "balance_cents": 0},
                ],
            },
            {
                "doc_type": DOC_RECURRING_JE,
                "document_id": "RJE-2029-06",
                "lines": [
                    {
                        "line_id": JE_DEPRECIATION,
                        "description": "Monthly depreciation per fixed-asset register",
                        "debit_account": "6410",
                        "credit_account": GL_ACCUM,
                        "amount_cents": 0,
                    },
                    {
                        "line_id": JE_AMORTIZATION,
                        "description": "Monthly prepaid amortization per schedule",
                        "debit_account": "6420",
                        "credit_account": GL_PREPAID,
                        "amount_cents": 0,
                    },
                ],
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
        doc for doc in payload["documents"] if doc.get("doc_type") != DOC_RECURRING_JE
    ]


def _subthreshold_capitalized(payload: dict[str, Any]) -> None:
    # A 460.00 chair order marked capitalized: the wrong side of the 500.00 gate.
    _expense_item(payload, "EX-203")["capitalized"] = True


def _subthreshold_asset_on_register(payload: dict[str, Any]) -> None:
    # A 420.00 desk-lamp set capitalized onto the register; the row itself is
    # kernel-consistent so only the threshold control sees it.
    register = _doc(payload, DOC_ASSET_REGISTER)
    assert register is not None
    row: dict[str, Any] = {
        "asset_id": "FA-107",
        "description": "Vellhurst desk lamp set",
        "project": "Brightwater Commons",
        "asset_class": "office_furniture",
        "method": METHOD_STRAIGHT_LINE,
        "cost_cents": 42_000,
        "in_service_month": "2029-02",
        "useful_life_months": 84,
    }
    rederive_asset_row(row)
    register["assets"].append(row)
    rederive(payload)


def _unknown_asset_class(payload: dict[str, Any]) -> None:
    _asset(payload, "FA-103")["asset_class"] = "artwork"


def _life_off_class_table(payload: dict[str, Any]) -> None:
    # The server is keyed to a 48-month life against the table's 36; the row is
    # re-derived from the wrong life so only the class-mapping control sees it.
    row = _asset(payload, "FA-101")
    row["useful_life_months"] = 48
    rederive_asset_row(row)
    rederive(payload)


def _non_straight_line_method(payload: dict[str, Any]) -> None:
    _asset(payload, "FA-102")["method"] = "declining_balance"


def _monthly_dep_overstated(payload: dict[str, Any]) -> None:
    _asset(payload, "FA-101")["monthly_dep_cents"] += 100


def _expense_overstated(payload: dict[str, Any]) -> None:
    # The month's charge is overtyped; the rollups are re-derived so the JE and
    # roll-forward still tie the register and only the re-derivation control fires.
    _asset(payload, "FA-103")["depr_exp_cents"] += 500
    rederive(payload)


def _end_depr_date_wrong(payload: dict[str, Any]) -> None:
    _asset(payload, "FA-105")["end_depr_month"] = "2035-07"


def _fully_depreciated_still_carrying(payload: dict[str, Any]) -> None:
    # The laptops finished their schedule in 2029-03 yet still carry NBV; the
    # cost-less-accum identity is preserved so only the end-date gate fires.
    row = _asset(payload, "FA-104")
    row["accum_dep_cents"] = row["cost_cents"] - 90_000
    row["nbv_cents"] = 90_000
    rederive(payload)


def _depreciation_before_service(payload: dict[str, Any]) -> None:
    # The staged plotter is not in service until 2029-08 yet carries accumulated
    # depreciation; the identity is preserved so only the service gate fires.
    row = _asset(payload, "FA-106")
    row["accum_dep_cents"] = 14_000
    row["nbv_cents"] = row["cost_cents"] - 14_000
    rederive(payload)


def _months_used_overstated(payload: dict[str, Any]) -> None:
    _asset(payload, "FA-101")["months_used"] += 1


def _accum_dep_misstated(payload: dict[str, Any]) -> None:
    # One month's charge missing from the accumulated balance; NBV moves with it
    # so the identity holds and only the accumulated re-derivation fires.
    row = _asset(payload, "FA-102")
    row["accum_dep_cents"] -= 16_703
    row["nbv_cents"] += 16_703
    rederive(payload)


def _nbv_identity_broken(payload: dict[str, Any]) -> None:
    _asset(payload, "FA-103")["nbv_cents"] += 1


def _accum_rollforward_broken(payload: dict[str, Any]) -> None:
    roll = _doc(payload, DOC_ROLLFORWARD)
    assert roll is not None
    roll["fixed_assets"]["opening_accum_cents"] += 1_000


def _rollforward_untied_to_register(payload: dict[str, Any]) -> None:
    # Opening and closing move together, so the roll-forward still closes on
    # itself -- it has simply drifted off the register it summarises.
    roll = _doc(payload, DOC_ROLLFORWARD)
    assert roll is not None
    roll["fixed_assets"]["opening_accum_cents"] += 1_000
    roll["fixed_assets"]["closing_accum_cents"] += 1_000


def _prepaid_rollforward_broken(payload: dict[str, Any]) -> None:
    roll = _doc(payload, DOC_ROLLFORWARD)
    assert roll is not None
    roll["prepaid"]["opening_cents"] += 500


def _prepaid_window_inverted(payload: dict[str, Any]) -> None:
    _prepaid(payload, "PP-401")["window_end"] = "2028-10"


def _prepaid_monthly_amort_wrong(payload: dict[str, Any]) -> None:
    _prepaid(payload, "PP-401")["monthly_amort_cents"] += 10


def _prepaid_expense_wrong(payload: dict[str, Any]) -> None:
    _prepaid(payload, "PP-403")["amort_this_period_cents"] += 1_000
    rederive(payload)


def _prepaid_ending_balance_wrong(payload: dict[str, Any]) -> None:
    _prepaid(payload, "PP-403")["ending_balance_cents"] += 777
    rederive(payload)


def _prepaid_window_ending(payload: dict[str, Any]) -> None:
    # The escrow policy's window is moved to end at the close month; the row is
    # re-derived so the schedule is arithmetically clean and only the
    # window-ending watch flags it.
    row = _prepaid(payload, "PP-401")
    row["window_start"] = "2028-07"
    row["window_end"] = "2029-06"
    row["booked_from"] = "2028-07"
    rederive_prepaid_row(row)
    rederive(payload)


def _disposed_asset_still_depreciating(payload: dict[str, Any]) -> None:
    # The disposed analytics buildout reappears on the fixed-asset register,
    # kernel-consistent, so only the disposal roll-off control sees it.
    register = _doc(payload, DOC_ASSET_REGISTER)
    assert register is not None
    row: dict[str, Any] = {
        "asset_id": "FA-090",
        "description": "Kestrelwood analytics platform buildout",
        "project": "Copperfield Yards",
        "asset_class": "computer_equipment",
        "method": METHOD_STRAIGHT_LINE,
        "cost_cents": 4_176_000,
        "in_service_month": "2026-05",
        "useful_life_months": 36,
    }
    rederive_asset_row(row)
    register["assets"].append(row)
    rederive(payload)


def _disposal_writeoff_wrong(payload: dict[str, Any]) -> None:
    _disposal(payload, "FA-090")["writeoff_cents"] += 100


def _stale_fully_depreciated_asset(payload: dict[str, Any]) -> None:
    # The laptops' schedule is moved back so it completed 18 months before the
    # close -- past the 12-month disposal-review band; the row is re-derived so
    # it is arithmetically clean and only the watch flags it.
    row = _asset(payload, "FA-104")
    row["in_service_month"] = "2025-01"
    rederive_asset_row(row)
    rederive(payload)


def _gl_cost_untied(payload: dict[str, Any]) -> None:
    _gl_row(payload, GL_COST)["balance_cents"] += 5_000


def _gl_accum_untied(payload: dict[str, Any]) -> None:
    _gl_row(payload, GL_ACCUM)["balance_cents"] += 5_000


def _gl_prepaid_untied(payload: dict[str, Any]) -> None:
    _gl_row(payload, GL_PREPAID)["balance_cents"] += 5_000


def _je_depreciation_untied(payload: dict[str, Any]) -> None:
    _je_row(payload, JE_DEPRECIATION)["amount_cents"] += 100


def _je_amortization_untied(payload: dict[str, Any]) -> None:
    _je_row(payload, JE_AMORTIZATION)["amount_cents"] += 100


def _amount_not_integer(payload: dict[str, Any]) -> None:
    row = _asset(payload, "FA-102")
    row["accum_dep_cents"] = float(row["accum_dep_cents"]) + 0.5


#: ``name -> (rule the file is built to trip, mutation)``.
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _missing_artifact),
    "subthreshold_capitalized": ("cap_threshold_gate", _subthreshold_capitalized),
    "subthreshold_asset_on_register": ("cap_register_meets_threshold", _subthreshold_asset_on_register),
    "unknown_asset_class": ("life_class_known", _unknown_asset_class),
    "life_off_class_table": ("life_matches_class", _life_off_class_table),
    "non_straight_line_method": ("life_method_straight_line", _non_straight_line_method),
    "monthly_dep_overstated": ("sl_monthly_dep_rederives", _monthly_dep_overstated),
    "expense_overstated": ("sl_expense_rederives", _expense_overstated),
    "end_depr_date_wrong": ("date_end_depr_rederives", _end_depr_date_wrong),
    "fully_depreciated_still_carrying": ("date_fully_depreciated_zero", _fully_depreciated_still_carrying),
    "depreciation_before_service": ("date_not_in_service_yet", _depreciation_before_service),
    "months_used_overstated": ("nbv_months_used_cap", _months_used_overstated),
    "accum_dep_misstated": ("nbv_accum_rederives", _accum_dep_misstated),
    "nbv_identity_broken": ("nbv_floor", _nbv_identity_broken),
    "accum_rollforward_broken": ("roll_accum_identity", _accum_rollforward_broken),
    "rollforward_untied_to_register": ("roll_closing_ties_register", _rollforward_untied_to_register),
    "prepaid_rollforward_broken": ("roll_prepaid_rollforward", _prepaid_rollforward_broken),
    "prepaid_window_inverted": ("pre_window_valid", _prepaid_window_inverted),
    "prepaid_monthly_amort_wrong": ("pre_monthly_amort_rederives", _prepaid_monthly_amort_wrong),
    "prepaid_expense_wrong": ("pre_expense_rederives", _prepaid_expense_wrong),
    "prepaid_ending_balance_wrong": ("pre_ending_balance_rederives", _prepaid_ending_balance_wrong),
    "prepaid_window_ending": ("pre_window_ending_watch", _prepaid_window_ending),
    "disposed_asset_still_depreciating": ("disp_not_on_register", _disposed_asset_still_depreciating),
    "disposal_writeoff_wrong": ("disp_gain_loss_rederives", _disposal_writeoff_wrong),
    "stale_fully_depreciated_asset": ("disp_fully_depreciated_watch", _stale_fully_depreciated_asset),
    "gl_cost_untied": ("gl_cost_ties", _gl_cost_untied),
    "gl_accum_untied": ("gl_accum_ties", _gl_accum_untied),
    "gl_prepaid_untied": ("gl_prepaid_ties", _gl_prepaid_untied),
    "je_depreciation_untied": ("je_depreciation_ties", _je_depreciation_untied),
    "je_amortization_untied": ("je_prepaid_amort_ties", _je_amortization_untied),
    "amount_not_integer": ("nbv_accum_rederives", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(ENTITIES[0])
    clean["file_id"] = f"clean__{ENTITIES[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        entity = ENTITIES[(i + 1) % len(ENTITIES)]
        f = baseline(entity)
        f["file_id"] = f"{name}__{entity.replace(' ', '_')}"
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
