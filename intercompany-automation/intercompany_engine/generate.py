"""
Fictional intercompany period-file generator.
==============================================

Builds a byte-stable corpus for the engine to analyze. One file is clean; every
other carries exactly **one** planted defect, built to make a named control fire.

Everything here is invented. The entity group, its projects, the reporting period
and every amount are fictional and the period is set in a fictional future. No
real Intracorp entity, person, bank, project or path appears anywhere. The
generator is deterministic and takes no seed.

The baseline is derived, not typed
----------------------------------
Only the entity tree, the protocol thresholds, the opening balances and the period
transactions are stated. Every closing due-from balance is rolled forward from its
opening plus the advances and repayments that moved it; every due-to is the mirror
of the due-from it faces; and the ledger totals are summed from the lines. So the
reciprocity, the roll-forward and the footing the engine checks are the same
relationships that produced the data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import (
    DOC_DUE_FROM,
    DOC_DUE_TO,
    DOC_ENTITY_REGISTER,
    DOC_FUNDING_PROTOCOL,
    DOC_IC_LEDGER,
    DOC_LIQUIDITY,
    GROUP_CAPITAL,
    TXN_ADVANCE,
    TXN_EQUITY,
    TXN_REPAYMENT,
    TXN_TYPES,
)

#: Fictional consolidation-group labels, rotated for file identity only. The
#: entity tree below is the same fictional group in every file.
GROUPS: tuple[str, ...] = (
    "Rivermont US Group",
    "Calderwood Holdings",
    "Westmere Development Group",
    "Ashfield US Group",
)

CURRENT_PERIOD = "2028-Q2"
WINDOW_FROM = "2028-04-01"
WINDOW_TO = "2028-06-30"
TOP_PARENT = "HOLD"
GUARANTOR = "WCAP"


def d(dollars: float) -> int:
    """Dollars to integer cents."""
    return round(dollars * 100)


MIN_LIQUIDITY = d(10_000_000)
LARGE_ADVANCE_THRESHOLD = d(500_000)

#: ``(code, name, group, parent, region)`` -- the entity tree.
ENTITIES: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    ("HOLD", "Rivermont US Holdings LLC", "Holdings", None, None),
    ("SVCS", "Rivermont Services LLC", "Services", "HOLD", None),
    ("NWSV", "Rivermont NW Services LLC", "Services", "SVCS", "Seattle"),
    ("SWSV", "Rivermont SW Services LLC", "Services", "SVCS", "SoCal"),
    ("WCAP", "Rivermont Capital LLC", "Capital", "HOLD", None),
    ("NWCP", "Rivermont NW Capital LLC", "Capital", "WCAP", "Seattle"),
    ("SWCP", "Rivermont SW Capital LLC", "Capital", "WCAP", "SoCal"),
    ("PRED", "Rivermont Predevelopment LLC", "Predevelopment", "HOLD", None),
)

#: ``(code, target_low_dollars, target_high_dollars)`` -- protocol target bands.
TARGETS: tuple[tuple[str, int, int], ...] = (
    ("HOLD", 2_000_000, 5_000_000),
    ("SVCS", 200_000, 600_000),
    ("NWSV", 200_000, 600_000),
    ("SWSV", 200_000, 600_000),
    ("NWCP", 200_000, 600_000),
    ("SWCP", 200_000, 600_000),
    ("PRED", 400_000, 800_000),
)

#: ``(creditor, debtor, opening_dollars)`` -- opening due-from balances.
OPENINGS: tuple[tuple[str, str, int], ...] = (
    ("HOLD", "PRED", 400_000),
    ("HOLD", "NWSV", 80_000),
    ("HOLD", "SWSV", 70_000),
    ("HOLD", "SVCS", 150_000),
    ("WCAP", "NWCP", 180_000),
    ("WCAP", "SWCP", 160_000),
)

#: ``(creditor, debtor, dollars, date, purpose)`` -- advances flow creditor->debtor.
ADVANCES: tuple[tuple[str, str, int, str, str], ...] = (
    ("HOLD", "PRED", 120_000, "2028-04-15", "predevelopment funding advance"),
    ("HOLD", "NWSV", 60_000, "2028-05-05", "NW services overhead advance"),
    ("HOLD", "SWSV", 55_000, "2028-05-20", "SW services overhead advance"),
    ("HOLD", "SVCS", 90_000, "2028-04-22", "services shared-cost advance"),
    ("WCAP", "NWCP", 100_000, "2028-04-10", "NW capital funding advance"),
    ("WCAP", "SWCP", 110_000, "2028-05-12", "SW capital funding advance"),
)

#: ``(debtor, creditor, dollars, date, purpose)`` -- repayments flow debtor->creditor.
REPAYMENTS: tuple[tuple[str, str, int, str, str], ...] = (
    ("PRED", "HOLD", 70_000, "2028-06-10", "predevelopment land-lift repayment"),
    ("SVCS", "HOLD", 40_000, "2028-06-18", "services advance repayment"),
    ("NWCP", "WCAP", 60_000, "2028-06-05", "NW capital return of advance"),
    ("SWCP", "WCAP", 30_000, "2028-06-25", "SW capital return of advance"),
)

#: ``(capital_entity, project, region, dollars, date, purpose)`` -- project equity.
EQUITY: tuple[tuple[str, str, str, int, str, str], ...] = (
    ("NWCP", "Ballard Yard", "Seattle", 350_000, "2028-04-18", "project equity funding"),
    ("SWCP", "Tustin Row", "SoCal", 420_000, "2028-05-28", "project equity funding"),
)

#: ``(code, cash_dollars)`` -- period-end cash positions.
LIQUIDITY: tuple[tuple[str, int], ...] = (
    ("HOLD", 3_200_000),
    ("WCAP", 12_500_000),
    ("SVCS", 410_000),
    ("NWSV", 290_000),
    ("SWSV", 305_000),
    ("NWCP", 340_000),
    ("SWCP", 310_000),
    ("PRED", 560_000),
)


def _closing(creditor: str, debtor: str) -> int:
    """Roll a pair's opening forward by its advances less its repayments."""
    opening = next(o for c, dr, o in OPENINGS if c == creditor and dr == debtor)
    advanced = sum(a for c, dr, a, _dt, _p in ADVANCES if c == creditor and dr == debtor)
    repaid = sum(a for dr, c, a, _dt, _p in REPAYMENTS if dr == debtor and c == creditor)
    return d(opening) + d(advanced) - d(repaid)


# --------------------------------------------------------------------------- #
# Artifact builders
# --------------------------------------------------------------------------- #
def _entity_register() -> dict[str, Any]:
    return {
        "doc_type": DOC_ENTITY_REGISTER,
        "document_id": "REG-2028",
        "top_parent": TOP_PARENT,
        "entities": [
            {"code": code, "name": name, "group": group, "parent": parent,
             "region": region}
            for code, name, group, parent, region in ENTITIES
        ],
    }


def _funding_protocol() -> dict[str, Any]:
    return {
        "doc_type": DOC_FUNDING_PROTOCOL,
        "document_id": "PROT-2018",
        "guarantor_code": GUARANTOR,
        "min_liquidity_cents": MIN_LIQUIDITY,
        "equity_funding_group": GROUP_CAPITAL,
        "large_advance_threshold_cents": LARGE_ADVANCE_THRESHOLD,
        "targets": [
            {"code": code, "target_low_cents": d(low), "target_high_cents": d(high)}
            for code, low, high in TARGETS
        ],
    }


def _ic_ledger() -> dict[str, Any]:
    txns: list[dict[str, Any]] = []
    n = 0
    for creditor, debtor, amount, when, purpose in ADVANCES:
        n += 1
        txns.append({
            "txn_no": n, "txn_type": TXN_ADVANCE, "from_entity": creditor,
            "to_entity": debtor, "amount_cents": d(amount), "txn_date": when,
            "purpose": purpose,
        })
    for debtor, creditor, amount, when, purpose in REPAYMENTS:
        n += 1
        txns.append({
            "txn_no": n, "txn_type": TXN_REPAYMENT, "from_entity": debtor,
            "to_entity": creditor, "amount_cents": d(amount), "txn_date": when,
            "purpose": purpose,
        })
    for entity, project, region, amount, when, purpose in EQUITY:
        n += 1
        txns.append({
            "txn_no": n, "txn_type": TXN_EQUITY, "from_entity": entity,
            "project": project, "region": region, "amount_cents": d(amount),
            "txn_date": when, "purpose": purpose,
        })
    return {
        "doc_type": DOC_IC_LEDGER,
        "document_id": f"LDG-{CURRENT_PERIOD}",
        "from_date": WINDOW_FROM,
        "to_date": WINDOW_TO,
        "transactions": txns,
        "totals": _totals(txns),
        "approved_by": "M. Tennant",
        "approval_date": "2028-07-06",
    }


def _totals(txns: list[dict[str, Any]]) -> dict[str, int]:
    """Sum transaction amounts by type (integer amounts only)."""
    out = {f"{t}_cents": 0 for t in TXN_TYPES}
    for txn in txns:
        key = f"{txn.get('txn_type')}_cents"
        amt = txn.get("amount_cents")
        if key in out and isinstance(amt, int) and not isinstance(amt, bool):
            out[key] += amt
    return out


def _due_from_schedule() -> dict[str, Any]:
    return {
        "doc_type": DOC_DUE_FROM,
        "document_id": f"DF-{CURRENT_PERIOD}",
        "positions": [
            {"entity": creditor, "counterparty": debtor,
             "opening_cents": d(opening), "closing_cents": _closing(creditor, debtor)}
            for creditor, debtor, opening in OPENINGS
        ],
    }


def _due_to_schedule() -> dict[str, Any]:
    return {
        "doc_type": DOC_DUE_TO,
        "document_id": f"DT-{CURRENT_PERIOD}",
        "positions": [
            {"entity": debtor, "counterparty": creditor,
             "closing_cents": _closing(creditor, debtor)}
            for creditor, debtor, _opening in OPENINGS
        ],
    }


def _liquidity_positions() -> dict[str, Any]:
    return {
        "doc_type": DOC_LIQUIDITY,
        "document_id": f"LIQ-{CURRENT_PERIOD}",
        "positions": [
            {"entity": code, "cash_cents": d(cash)} for code, cash in LIQUIDITY
        ],
    }


def baseline(group: str) -> dict[str, Any]:
    """A complete, internally consistent period file that passes every control."""
    return {
        "file_id": f"{group.replace(' ', '_')}__{CURRENT_PERIOD}",
        "group": group,
        "period": CURRENT_PERIOD,
        "documents": [
            _entity_register(),
            _funding_protocol(),
            _ic_ledger(),
            _due_from_schedule(),
            _due_to_schedule(),
            _liquidity_positions(),
        ],
    }


# --------------------------------------------------------------------------- #
# Mutation helpers
# --------------------------------------------------------------------------- #
def _doc(f: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(x for x in f["documents"] if x["doc_type"] == doc_type)


def _txns(f: dict[str, Any]) -> list[dict[str, Any]]:
    return _doc(f, DOC_IC_LEDGER)["transactions"]


def _next_txn_no(f: dict[str, Any]) -> int:
    return max((t["txn_no"] for t in _txns(f)), default=0) + 1


def _resync_totals(f: dict[str, Any]) -> None:
    """Recompute the ledger totals from its lines, so only one thing is wrong."""
    ledger = _doc(f, DOC_IC_LEDGER)
    ledger["totals"] = _totals(ledger["transactions"])


def _liq_row(f: dict[str, Any], code: str) -> dict[str, Any]:
    return next(r for r in _doc(f, DOC_LIQUIDITY)["positions"] if r["entity"] == code)


def _df_row(f: dict[str, Any], entity: str, counterparty: str) -> dict[str, Any]:
    return next(r for r in _doc(f, DOC_DUE_FROM)["positions"]
                if r["entity"] == entity and r["counterparty"] == counterparty)


def _dt_row(f: dict[str, Any], entity: str, counterparty: str) -> dict[str, Any]:
    return next(r for r in _doc(f, DOC_DUE_TO)["positions"]
                if r["entity"] == entity and r["counterparty"] == counterparty)


def _equity_txn(f: dict[str, Any], project: str) -> dict[str, Any]:
    return next(t for t in _txns(f) if t.get("project") == project)


# --------------------------------------------------------------------------- #
# Defect mutations
# --------------------------------------------------------------------------- #
def _drop_document(f: dict[str, Any]) -> None:
    f["documents"] = [x for x in f["documents"] if x["doc_type"] != DOC_LIQUIDITY]


def _bad_period_label(f: dict[str, Any]) -> None:
    f["period"] = "2028-06"


def _unknown_entity(f: dict[str, Any]) -> None:
    # A liquidity position on a code the register has never heard of.
    _liq_row(f, "NWSV")["entity"] = "ZZZZ"


def _duplicate_entity_code(f: dict[str, Any]) -> None:
    reg = _doc(f, DOC_ENTITY_REGISTER)
    reg["entities"].append({
        "code": "NWCP", "name": "Rivermont NW Capital LLC (branch)",
        "group": "Capital", "parent": "WCAP", "region": "Seattle",
    })


def _dangling_parent(f: dict[str, Any]) -> None:
    reg = _doc(f, DOC_ENTITY_REGISTER)
    next(e for e in reg["entities"] if e["code"] == "WCAP")["parent"] = "NOPE"


def _parent_cycle(f: dict[str, Any]) -> None:
    # Two entities that own each other -- a disconnected cycle with no root.
    reg = _doc(f, DOC_ENTITY_REGISTER)
    reg["entities"].append({"code": "AAAA", "name": "Loop Alpha LLC",
                            "group": "Capital", "parent": "BBBB", "region": None})
    reg["entities"].append({"code": "BBBB", "name": "Loop Beta LLC",
                            "group": "Capital", "parent": "AAAA", "region": None})


def _orphan_due_to(f: dict[str, Any]) -> None:
    _doc(f, DOC_DUE_TO)["positions"].append(
        {"entity": "NWCP", "counterparty": "PRED", "closing_cents": d(50_000)})


def _reciprocity_off(f: dict[str, Any]) -> None:
    _dt_row(f, "PRED", "HOLD")["closing_cents"] += d(500)


def _self_balance(f: dict[str, Any]) -> None:
    # A zero-value self-pair on both sides: reciprocal and footing, but self-keyed.
    _doc(f, DOC_DUE_FROM)["positions"].append(
        {"entity": "SWCP", "counterparty": "SWCP", "opening_cents": 0, "closing_cents": 0})
    _doc(f, DOC_DUE_TO)["positions"].append(
        {"entity": "SWCP", "counterparty": "SWCP", "closing_cents": 0})


def _same_party(f: dict[str, Any]) -> None:
    _txns(f).append({
        "txn_no": _next_txn_no(f), "txn_type": TXN_REPAYMENT, "from_entity": "HOLD",
        "to_entity": "HOLD", "amount_cents": d(1), "txn_date": "2028-05-15",
        "purpose": "mis-keyed self repayment",
    })
    _resync_totals(f)


def _negative_amount(f: dict[str, Any]) -> None:
    # A reversed advance mis-signed; from HOLD to its own subsidiary WCAP so no
    # funding-routing or direction rule is disturbed.
    _txns(f).append({
        "txn_no": _next_txn_no(f), "txn_type": TXN_ADVANCE, "from_entity": "HOLD",
        "to_entity": "WCAP", "amount_cents": -d(1), "txn_date": "2028-05-16",
        "purpose": "reversed advance mis-signed",
    })
    _resync_totals(f)


def _totals_off(f: dict[str, Any]) -> None:
    _doc(f, DOC_IC_LEDGER)["totals"]["advance_cents"] += d(1_000)


def _rollforward_off(f: dict[str, Any]) -> None:
    # Move the closing balance on both sides, so reciprocity still holds but the
    # balance no longer rolls forward from the transactions.
    _df_row(f, "WCAP", "NWCP")["closing_cents"] += d(1_000)
    _dt_row(f, "NWCP", "WCAP")["closing_cents"] += d(1_000)


def _txn_outside_window(f: dict[str, Any]) -> None:
    next(t for t in _txns(f) if t.get("txn_no") == 1)["txn_date"] = "2028-08-15"


def _equity_from_services(f: dict[str, Any]) -> None:
    # Funded from a Services entity in the right region, so only the group is wrong.
    _equity_txn(f, "Ballard Yard")["from_entity"] = "NWSV"


def _region_mismatch(f: dict[str, Any]) -> None:
    # Funded from the wrong region's capital entity; the group is still Capital.
    _equity_txn(f, "Ballard Yard")["from_entity"] = "SWCP"


def _services_from_capital(f: dict[str, Any]) -> None:
    _txns(f).append({
        "txn_no": _next_txn_no(f), "txn_type": TXN_ADVANCE, "from_entity": "WCAP",
        "to_entity": "NWSV", "amount_cents": d(40_000), "txn_date": "2028-05-09",
        "purpose": "capital funding a services entity",
    })
    _resync_totals(f)


def _advance_upstream(f: dict[str, Any]) -> None:
    _txns(f).append({
        "txn_no": _next_txn_no(f), "txn_type": TXN_ADVANCE, "from_entity": "NWCP",
        "to_entity": "WCAP", "amount_cents": d(30_000), "txn_date": "2028-06-02",
        "purpose": "advance running up the chain",
    })
    _resync_totals(f)


def _guarantor_short(f: dict[str, Any]) -> None:
    _liq_row(f, GUARANTOR)["cash_cents"] = d(8_000_000)


def _negative_cash(f: dict[str, Any]) -> None:
    _liq_row(f, "NWSV")["cash_cents"] = -d(5_000)


def _target_breach(f: dict[str, Any]) -> None:
    _liq_row(f, "NWCP")["cash_cents"] = d(50_000)


def _unapproved(f: dict[str, Any]) -> None:
    _doc(f, DOC_IC_LEDGER)["approved_by"] = ""


def _large_advance(f: dict[str, Any]) -> None:
    _txns(f).append({
        "txn_no": _next_txn_no(f), "txn_type": TXN_ADVANCE, "from_entity": "HOLD",
        "to_entity": "WCAP", "amount_cents": d(600_000), "txn_date": "2028-04-30",
        "purpose": "large intercompany advance",
    })
    _resync_totals(f)


def _amount_not_integer(f: dict[str, Any]) -> None:
    next(t for t in _txns(f) if t.get("txn_no") == 5)["amount_cents"] = 10000000.5


#: ``name -> (rule the file is built to trip, mutation)``
DEFECTS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "missing_artifact": ("set_complete", _drop_document),
    "bad_period_label": ("set_period_label", _bad_period_label),
    "unknown_entity": ("set_entities_exist", _unknown_entity),
    "duplicate_entity_code": ("ent_codes_unique", _duplicate_entity_code),
    "dangling_parent": ("ent_parent_defined", _dangling_parent),
    "parent_cycle": ("ent_tree_acyclic", _parent_cycle),
    "orphan_due_to": ("rec_pairs_symmetric", _orphan_due_to),
    "reciprocity_off": ("rec_amounts_reciprocal", _reciprocity_off),
    "self_balance": ("rec_no_self_balance", _self_balance),
    "same_party": ("led_parties_distinct", _same_party),
    "negative_amount": ("led_amounts_positive", _negative_amount),
    "totals_off": ("led_totals_foot", _totals_off),
    "rollforward_off": ("led_rollforward_ties", _rollforward_off),
    "txn_outside_window": ("led_dates_inside_window", _txn_outside_window),
    "equity_from_services": ("fund_equity_from_capital", _equity_from_services),
    "region_mismatch": ("fund_region_matches", _region_mismatch),
    "services_from_capital": ("fund_services_from_holdings", _services_from_capital),
    "advance_upstream": ("fund_advance_flows_down", _advance_upstream),
    "guarantor_short": ("liq_guarantor_minimum", _guarantor_short),
    "negative_cash": ("liq_no_negative_cash", _negative_cash),
    "target_breach": ("liq_target_band", _target_breach),
    "unapproved": ("appr_ledger_approved", _unapproved),
    "large_advance": ("appr_large_advance_flagged", _large_advance),
    "amount_not_integer": ("led_totals_foot", _amount_not_integer),
}


# --------------------------------------------------------------------------- #
# Corpus writer
# --------------------------------------------------------------------------- #
def generate_corpus(folder: Path) -> list[Path]:
    """Write the fictional corpus into ``folder`` and return the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files: list[dict[str, Any]] = []
    clean = baseline(GROUPS[0])
    clean["file_id"] = f"clean__{GROUPS[0].replace(' ', '_')}"
    files.append(clean)

    for i, name in enumerate(sorted(DEFECTS)):
        _rule, mutate = DEFECTS[name]
        group = GROUPS[(i + 1) % len(GROUPS)]
        f = baseline(group)
        f["file_id"] = f"{name}__{group.replace(' ', '_')}"
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
