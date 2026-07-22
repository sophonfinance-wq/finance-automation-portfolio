"""Targeted tests for the controls whose logic is worth pinning down directly.

The planted-defect corpus proves each control fires. These prove the *semantics*
are what they claim: that recognition really is gated on close of escrow and not
on payment or completion, that the sign conventions are enforced in both
directions, and that a missing ledger balance fails rather than passes.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from upgrade_engine.engine import analyze_document
from upgrade_engine.generate import baseline, d
from upgrade_engine.model import (
    ACCT_CONTRA_WIP,
    ACCT_REVENUE,
    ACCT_SALES_TAX,
    ACCT_UNEARNED,
    DOC_CLOSINGS_SCHEDULE,
    DOC_COST_TO_COMPLETE,
    DOC_LEDGER_BALANCES,
    DOC_PROFORMA,
    DOC_UPGRADE_REGISTER,
    Status,
)


def _write(tmp_path: Path, bk: dict[str, Any], name: str = "case") -> Path:
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(bk, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def _doc(bk: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(x for x in bk["documents"] if x["doc_type"] == doc_type)


def _unit(bk: dict[str, Any], doc_type: str, unit: str) -> dict[str, Any]:
    return next(u for u in _doc(bk, doc_type)["units"] if u["unit"] == unit)


def _acct(bk: dict[str, Any], name: str) -> dict[str, Any]:
    return next(a for a in _doc(bk, DOC_LEDGER_BALANCES)["accounts"]
                if a["account"] == name)


def _fired(path: Path, rule: str) -> bool:
    return rule in analyze_document(path).rules_fired()


@pytest.fixture()
def bk() -> dict[str, Any]:
    return copy.deepcopy(baseline("Alderpoint Terraces"))


# --------------------------------------------------------------------------- #
# Recognition is gated on close of escrow, not on anything else
# --------------------------------------------------------------------------- #
def test_paid_and_complete_is_still_not_recognised(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """An unclosed unit stays deferred no matter what else is true of it.

    This is the rule a hand-maintained schedule most often gets wrong, because
    every other signal says the money is earned. The engine is deliberately
    indifferent to all of them.
    """
    u = _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-03")
    u["buyer_paid_in_full"] = True
    u["work_complete"] = True
    u["invoice_settled"] = True
    # ...and still not closed.
    assert u["closed"] is False
    assert not _fired(_write(tmp_path, bk), "def_released_only_on_close")


def test_one_cent_recognised_early_fails(bk: dict[str, Any], tmp_path: Path) -> None:
    """There is no immaterial amount of premature recognition."""
    u = _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-03")
    u["revenue_recognised_cents"] = 1
    u["deferred_balance_cents"] -= 1
    assert _fired(_write(tmp_path, bk), "def_released_only_on_close")


def test_closed_unit_must_release_the_whole_balance(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """A partial release leaves a stranded liability nobody will ever clear."""
    u = _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-01")
    u["deferred_balance_cents"] = 1
    u["revenue_recognised_cents"] -= 1
    assert _fired(_write(tmp_path, bk), "def_released_only_on_close")


# --------------------------------------------------------------------------- #
# Sign conventions, enforced in both directions
# --------------------------------------------------------------------------- #
def test_contra_wip_must_offset_not_add(bk: dict[str, Any], tmp_path: Path) -> None:
    """Cost of sales and contra-WIP must net to zero, not double up.

    Flipping the contra credit to a debit makes the entry sum to twice the cost
    rather than to nothing -- an error that leaves both accounts individually
    plausible.
    """
    a = _acct(bk, ACCT_CONTRA_WIP)
    a["balance_cents"] = abs(a["balance_cents"])
    assert _fired(_write(tmp_path, bk), "cos_entry_balances")


def test_proforma_cost_sign_is_enforced(bk: dict[str, Any], tmp_path: Path) -> None:
    """The proforma job-cost line is negative; a positive one is caught.

    The tie negates one side deliberately. Comparing raw would fire on every
    correct book -- and hold on this one, which is the wrong way round.
    """
    pf = _doc(bk, DOC_PROFORMA)
    pf["upgrade_costs_to_date_cents"] = abs(pf["upgrade_costs_to_date_cents"])
    assert _fired(_write(tmp_path, bk), "tie_ctc_costs_to_proforma")


def test_correct_negative_cost_line_passes(bk: dict[str, Any], tmp_path: Path) -> None:
    pf = _doc(bk, DOC_PROFORMA)
    assert pf["upgrade_costs_to_date_cents"] < 0
    assert not _fired(_write(tmp_path, bk), "tie_ctc_costs_to_proforma")


# --------------------------------------------------------------------------- #
# Missing evidence never reads as a passing control
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "account,rule",
    [
        (ACCT_UNEARNED, "def_schedule_ties_ledger"),
        (ACCT_REVENUE, "def_revenue_ties_ledger"),
        (ACCT_SALES_TAX, "tax_not_recognised_as_revenue"),
        (ACCT_CONTRA_WIP, "cos_entry_balances"),
    ],
)
def test_absent_ledger_balance_fails(
    bk: dict[str, Any], tmp_path: Path, account: str, rule: str
) -> None:
    """A schedule with nothing to tie to has not tied."""
    ledger = _doc(bk, DOC_LEDGER_BALANCES)
    ledger["accounts"] = [a for a in ledger["accounts"] if a["account"] != account]
    assert _fired(_write(tmp_path, bk), rule)


def test_missing_tax_rate_fails_rather_than_skips(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """With no declared rate, no tax line can be shown to be right."""
    _doc(bk, DOC_UPGRADE_REGISTER)["sales_tax_rate_bps"] = None
    assert _fired(_write(tmp_path, bk), "tax_derived_from_rate")


# --------------------------------------------------------------------------- #
# Sales tax is a liability
# --------------------------------------------------------------------------- #
def test_tax_derivation_truncates_like_the_order(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """Tax is derived with the same truncating arithmetic the order uses.

    A price whose tax lands on a fractional cent must truncate, not round, or the
    engine and the source would disagree by a penny on ordinary orders.
    """
    reg = _doc(bk, DOC_UPGRADE_REGISTER)
    reg["sales_tax_rate_bps"] = 733           # deliberately awkward
    for order in reg["orders"]:
        order["sales_tax_cents"] = order["price_cents"] * 733 // 10000
    assert not _fired(_write(tmp_path, bk), "tax_derived_from_rate")


def test_tax_folded_into_revenue_is_caught(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """Moving tax into revenue still foots, and is still wrong."""
    tax = _acct(bk, ACCT_SALES_TAX)
    moved = tax["balance_cents"]
    tax["balance_cents"] = 0
    _acct(bk, ACCT_REVENUE)["balance_cents"] += moved
    path = _write(tmp_path, bk)
    assert _fired(path, "tax_not_recognised_as_revenue")


# --------------------------------------------------------------------------- #
# The budgeted/actual marker
# --------------------------------------------------------------------------- #
def test_actual_marker_on_an_open_unit_flags(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """The marker is wrong in both directions, not just the stale one."""
    _unit(bk, DOC_COST_TO_COMPLETE, "U-03")["revenue_basis"] = "actual"
    assert _fired(_write(tmp_path, bk), "flag_actual_on_closed_units")


def test_marker_mismatch_is_review_not_failure(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """A stale marker needs a human, but does not block: nothing is misstated."""
    _unit(bk, DOC_COST_TO_COMPLETE, "U-01")["revenue_basis"] = "budgeted"
    report = analyze_document(_write(tmp_path, bk))
    statuses = {
        f.status for f in report.findings if f.rule == "flag_actual_on_closed_units"
    }
    assert Status.FLAG in statuses
    assert Status.FAIL not in statuses


# --------------------------------------------------------------------------- #
# A unit with no upgrades is not an error
# --------------------------------------------------------------------------- #
def test_unit_with_no_upgrades_is_clean(bk: dict[str, Any], tmp_path: Path) -> None:
    """U-06 contracts nothing. Zero is a legitimate answer, not a missing one."""
    u = _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-06")
    assert u["revenue_recognised_cents"] == 0
    assert u["deferred_balance_cents"] == 0
    assert not _fired(_write(tmp_path, bk), "def_unit_total_is_deposit")


def test_orphaned_deferred_balance_is_caught(
    bk: dict[str, Any], tmp_path: Path
) -> None:
    """A deferred balance on a unit that contracted nothing has no source."""
    u = _unit(bk, DOC_CLOSINGS_SCHEDULE, "U-06")
    u["deferred_balance_cents"] = d(4_000)
    assert _fired(_write(tmp_path, bk), "def_unit_total_is_deposit")
