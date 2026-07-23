"""Targeted tests for the controls whose logic is worth pinning down directly.

The planted-defect corpus proves each control fires. These prove the *boundaries*
are where they should be -- that a due-from is reciprocal to the cent and not a
penny more, that the group's intercompany balances eliminate to zero, that a
closing rolls forward from the transactions with repayments reducing the reversed
pair, that the guarantor floor is inclusive, that target bands are inclusive at
both ends, and that funding must come from the protocol-correct entity and flow
down the ownership chain.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from intercompany_engine.engine import analyze_document
from intercompany_engine.generate import GROUPS, baseline, d
from intercompany_engine.model import (
    DOC_DUE_FROM,
    DOC_DUE_TO,
    DOC_ENTITY_REGISTER,
    DOC_IC_LEDGER,
    DOC_LIQUIDITY,
    TXN_ADVANCE,
    TXN_EQUITY,
    TXN_REPAYMENT,
)


def _write(tmp_path: Path, f: dict[str, Any], name: str = "case") -> Path:
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(f, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def _doc(f: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(x for x in f["documents"] if x["doc_type"] == doc_type)


def _txns(f: dict[str, Any]) -> list[dict[str, Any]]:
    return _doc(f, DOC_IC_LEDGER)["transactions"]


def _df(f: dict[str, Any], entity: str, cpty: str) -> dict[str, Any]:
    return next(r for r in _doc(f, DOC_DUE_FROM)["positions"]
               if r["entity"] == entity and r["counterparty"] == cpty)


def _dt(f: dict[str, Any], entity: str, cpty: str) -> dict[str, Any]:
    return next(r for r in _doc(f, DOC_DUE_TO)["positions"]
               if r["entity"] == entity and r["counterparty"] == cpty)


def _liq(f: dict[str, Any], code: str) -> dict[str, Any]:
    return next(r for r in _doc(f, DOC_LIQUIDITY)["positions"] if r["entity"] == code)


def _resync_totals(f: dict[str, Any]) -> None:
    from intercompany_engine.generate import _totals

    ledger = _doc(f, DOC_IC_LEDGER)
    ledger["totals"] = _totals(ledger["transactions"])


def _next_no(f: dict[str, Any]) -> int:
    return max(t["txn_no"] for t in _txns(f)) + 1


def _fired(path: Path, rule: str) -> bool:
    return rule in analyze_document(path).rules_fired()


@pytest.fixture()
def cf() -> dict[str, Any]:
    return copy.deepcopy(baseline(GROUPS[0]))


# --------------------------------------------------------------------------- #
# Reciprocity is the spine
# --------------------------------------------------------------------------- #
def test_baseline_pairs_are_reciprocal(cf: dict[str, Any], tmp_path: Path) -> None:
    """Every due-from equals the due-to that faces it on the clean baseline."""
    assert not _fired(_write(tmp_path, cf), "rec_amounts_reciprocal")


def test_one_cent_of_drift_breaks_reciprocity(cf: dict[str, Any], tmp_path: Path) -> None:
    """A single penny between the two sides is a break, not a rounding tolerance."""
    _dt(cf, "PRED", "HOLD")["closing_cents"] += 1
    path = _write(tmp_path, cf)
    assert _fired(path, "rec_amounts_reciprocal")
    # ...and only reciprocity: the pair is still two-sided and the balances still
    # roll forward, which is why the drift is invisible on either entity alone.
    assert not _fired(path, "rec_pairs_symmetric")
    assert not _fired(path, "led_rollforward_ties")


def test_group_intercompany_eliminates_to_zero(cf: dict[str, Any]) -> None:
    """The sum of due-froms equals the sum of due-tos: the group nets to zero.

    This is the whole point of the reconciliation. When every pair is reciprocal,
    the intercompany balances cancel on consolidation and leave no residual.
    """
    df_total = sum(r["closing_cents"] for r in _doc(cf, DOC_DUE_FROM)["positions"])
    dt_total = sum(r["closing_cents"] for r in _doc(cf, DOC_DUE_TO)["positions"])
    assert df_total == dt_total


def test_orphan_due_from_has_no_mirror(cf: dict[str, Any], tmp_path: Path) -> None:
    """A receivable the counterparty never booked is an orphan, not a balance."""
    _doc(cf, DOC_DUE_FROM)["positions"].append(
        {"entity": "SWCP", "counterparty": "NWCP", "opening_cents": 0,
         "closing_cents": d(10_000)})
    assert _fired(_write(tmp_path, cf), "rec_pairs_symmetric")


# --------------------------------------------------------------------------- #
# Balances roll forward from the ledger
# --------------------------------------------------------------------------- #
def test_baseline_rolls_forward(cf: dict[str, Any], tmp_path: Path) -> None:
    assert not _fired(_write(tmp_path, cf), "led_rollforward_ties")


def test_an_advance_moves_the_closing_balance(cf: dict[str, Any], tmp_path: Path) -> None:
    """Add an advance on a pair without restating its closing: it no longer ties."""
    _txns(cf).append({
        "txn_no": _next_no(cf), "txn_type": TXN_ADVANCE, "from_entity": "HOLD",
        "to_entity": "PRED", "amount_cents": d(10_000), "txn_date": "2028-05-01",
        "purpose": "extra advance",
    })
    _resync_totals(cf)
    assert _fired(_write(tmp_path, cf), "led_rollforward_ties")


def test_a_repayment_reduces_the_reversed_pair(cf: dict[str, Any], tmp_path: Path) -> None:
    """A repayment flows debtor->creditor and reduces the pair it faces.

    Keyed on the reversed pair: a repayment from PRED to HOLD reduces HOLD's
    due-from against PRED, so adding one without restating the closing overstates
    the balance and the roll-forward catches it.
    """
    _txns(cf).append({
        "txn_no": _next_no(cf), "txn_type": TXN_REPAYMENT, "from_entity": "PRED",
        "to_entity": "HOLD", "amount_cents": d(10_000), "txn_date": "2028-06-20",
        "purpose": "extra repayment",
    })
    _resync_totals(cf)
    assert _fired(_write(tmp_path, cf), "led_rollforward_ties")


def test_equity_does_not_roll_a_due_from(cf: dict[str, Any], tmp_path: Path) -> None:
    """Equity debits an investment account, not a due-from, so it never moves one."""
    _txns(cf).append({
        "txn_no": _next_no(cf), "txn_type": TXN_EQUITY, "from_entity": "NWCP",
        "project": "Alderpoint Terraces", "region": "Seattle", "amount_cents": d(75_000),
        "txn_date": "2028-05-03", "purpose": "project equity funding",
    })
    _resync_totals(cf)
    assert not _fired(_write(tmp_path, cf), "led_rollforward_ties")


# --------------------------------------------------------------------------- #
# The guarantor liquidity floor is inclusive
# --------------------------------------------------------------------------- #
def test_guarantor_exactly_at_the_floor_passes(cf: dict[str, Any], tmp_path: Path) -> None:
    """Holding exactly the covenant minimum is compliant."""
    _liq(cf, "WCAP")["cash_cents"] = d(10_000_000)
    assert not _fired(_write(tmp_path, cf), "liq_guarantor_minimum")


def test_guarantor_one_cent_below_the_floor_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    _liq(cf, "WCAP")["cash_cents"] = d(10_000_000) - 1
    assert _fired(_write(tmp_path, cf), "liq_guarantor_minimum")


# --------------------------------------------------------------------------- #
# Target bands are inclusive at both ends
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "cash,expected_flag",
    [(d(200_000), False), (d(600_000), False),
     (d(200_000) - 1, True), (d(600_000) + 1, True)],
)
def test_target_band_boundaries_are_inclusive(
    cf: dict[str, Any], tmp_path: Path, cash: int, expected_flag: bool
) -> None:
    """The band floor and ceiling are inside the band; a penny outside flags."""
    _liq(cf, "NWCP")["cash_cents"] = cash
    assert _fired(_write(tmp_path, cf), "liq_target_band") is expected_flag


def test_target_band_is_a_flag_not_a_failure(cf: dict[str, Any], tmp_path: Path) -> None:
    """A band breach wants review; it is a guideline, not a covenant."""
    _liq(cf, "NWCP")["cash_cents"] = d(10_000)
    report = analyze_document(_write(tmp_path, cf))
    statuses = {f.status.value for f in report.findings if f.rule == "liq_target_band"}
    assert "FLAG" in statuses
    assert "FAIL" not in statuses


# --------------------------------------------------------------------------- #
# Funding comes from the protocol-correct entity
# --------------------------------------------------------------------------- #
def test_equity_from_the_capital_group_passes(cf: dict[str, Any], tmp_path: Path) -> None:
    assert not _fired(_write(tmp_path, cf), "fund_equity_from_capital")


def test_equity_from_outside_capital_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    """Project equity routed around the capital arm breaks the guarantor structure."""
    next(t for t in _txns(cf) if t.get("project") == "Brightwater Commons")["from_entity"] = "SVCS"
    assert _fired(_write(tmp_path, cf), "fund_equity_from_capital")


def test_cross_region_equity_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    """The Southern California capital entity may not fund a Seattle project."""
    next(t for t in _txns(cf) if t.get("project") == "Brightwater Commons")["from_entity"] = "SWCP"
    assert _fired(_write(tmp_path, cf), "fund_region_matches")


def test_services_funded_from_capital_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    """A Services entity funded by Capital crosses the wall Holdings sits on."""
    _txns(cf).append({
        "txn_no": _next_no(cf), "txn_type": TXN_ADVANCE, "from_entity": "WCAP",
        "to_entity": "SWSV", "amount_cents": d(20_000), "txn_date": "2028-05-07",
        "purpose": "capital funding a services entity",
    })
    _resync_totals(cf)
    assert _fired(_write(tmp_path, cf), "fund_services_from_holdings")


def test_services_funded_from_holdings_passes(cf: dict[str, Any], tmp_path: Path) -> None:
    assert not _fired(_write(tmp_path, cf), "fund_services_from_holdings")


# --------------------------------------------------------------------------- #
# Advances flow down the ownership chain
# --------------------------------------------------------------------------- #
def test_advance_down_the_chain_is_clean(cf: dict[str, Any], tmp_path: Path) -> None:
    assert not _fired(_write(tmp_path, cf), "fund_advance_flows_down")


def test_advance_up_the_chain_is_flagged(cf: dict[str, Any], tmp_path: Path) -> None:
    """A child 'advancing' its parent is more often a distribution mislabelled."""
    _txns(cf).append({
        "txn_no": _next_no(cf), "txn_type": TXN_ADVANCE, "from_entity": "NWCP",
        "to_entity": "WCAP", "amount_cents": d(15_000), "txn_date": "2028-06-01",
        "purpose": "advance up the chain",
    })
    _resync_totals(cf)
    assert _fired(_write(tmp_path, cf), "fund_advance_flows_down")


def test_advance_across_the_tree_is_flagged(cf: dict[str, Any], tmp_path: Path) -> None:
    """Two siblings are not ancestor and descendant; the movement wants classifying."""
    _txns(cf).append({
        "txn_no": _next_no(cf), "txn_type": TXN_ADVANCE, "from_entity": "NWCP",
        "to_entity": "SWCP", "amount_cents": d(15_000), "txn_date": "2028-06-03",
        "purpose": "advance across the tree",
    })
    _resync_totals(cf)
    assert _fired(_write(tmp_path, cf), "fund_advance_flows_down")


# --------------------------------------------------------------------------- #
# The entity tree
# --------------------------------------------------------------------------- #
def test_self_balance_is_caught(cf: dict[str, Any], tmp_path: Path) -> None:
    """An entity owing itself is a mis-keyed counterparty, not a balance."""
    _doc(cf, DOC_DUE_FROM)["positions"].append(
        {"entity": "PRED", "counterparty": "PRED", "opening_cents": 0, "closing_cents": 0})
    assert _fired(_write(tmp_path, cf), "rec_no_self_balance")


def test_ownership_cycle_is_caught(cf: dict[str, Any], tmp_path: Path) -> None:
    """A parent loop leaves the group with no root."""
    reg = _doc(cf, DOC_ENTITY_REGISTER)
    reg["entities"].append({"code": "LP1", "name": "Loop One LLC", "group": "Capital",
                            "parent": "LP2", "region": None})
    reg["entities"].append({"code": "LP2", "name": "Loop Two LLC", "group": "Capital",
                            "parent": "LP1", "region": None})
    assert _fired(_write(tmp_path, cf), "ent_tree_acyclic")


def test_unregistered_entity_is_caught(cf: dict[str, Any], tmp_path: Path) -> None:
    """A position on a code the register never heard of cannot be reconciled."""
    _liq(cf, "SWSV")["entity"] = "GHOST"
    assert _fired(_write(tmp_path, cf), "set_entities_exist")


# --------------------------------------------------------------------------- #
# Missing evidence never reads as a passing control
# --------------------------------------------------------------------------- #
def test_dropping_the_due_to_schedule_is_caught(cf: dict[str, Any], tmp_path: Path) -> None:
    """With no due-to side, reciprocity cannot be shown and completeness fails."""
    cf["documents"] = [x for x in cf["documents"] if x["doc_type"] != DOC_DUE_TO]
    path = _write(tmp_path, cf)
    assert _fired(path, "set_complete")
    # ...and the reciprocity rule stays silent rather than crashing or passing.
    assert "rec_amounts_reciprocal" not in analyze_document(path).rules_fired()
