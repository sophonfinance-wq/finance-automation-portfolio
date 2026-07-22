"""Targeted tests for the controls whose logic is worth pinning down directly.

The planted-defect corpus proves each control fires. These prove the *boundaries*
are where they should be -- that the pool is exact at its limit and fails one cent
past it, that period edges are inclusive, that coverage begins on the close date
rather than after it, and that a duplicate is caught across quarters and not only
within one.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from warranty_engine.engine import analyze_document
from warranty_engine.generate import CURRENT_PERIOD, baseline, d
from warranty_engine.model import (
    DOC_CLAIMS_HISTORY,
    DOC_CLAIM_SUBMISSION,
    DOC_CLOSED_UNITS,
    DOC_COST_LEDGER,
    DOC_POLICY,
    Status,
)


def _write(tmp_path: Path, f: dict[str, Any], name: str = "case") -> Path:
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(f, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


def _doc(f: dict[str, Any], doc_type: str) -> dict[str, Any]:
    return next(x for x in f["documents"] if x["doc_type"] == doc_type)


def _period(f: dict[str, Any], label: str) -> dict[str, Any]:
    return next(p for p in _doc(f, DOC_CLAIMS_HISTORY)["periods"]
                if p["period"] == label)


def _fired(path: Path, rule: str) -> bool:
    return rule in analyze_document(path).rules_fired()


@pytest.fixture()
def cf() -> dict[str, Any]:
    return copy.deepcopy(baseline("Alderpoint Terraces"))


# --------------------------------------------------------------------------- #
# The pool is exact at its boundary
# --------------------------------------------------------------------------- #
def test_cumulative_exactly_at_the_limit_passes(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """Spending the pool to the cent is allowed. It is exceeding it that is not."""
    limit = _doc(cf, DOC_POLICY)["coverage_limit_cents"]
    sub = _doc(cf, DOC_CLAIM_SUBMISSION)
    sub["cumulative_reimbursement_cents"] = limit
    sub["coverage_remaining_cents"] = 0
    assert not _fired(_write(tmp_path, cf), "pol_cumulative_within_limit")


def test_cumulative_one_cent_over_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    limit = _doc(cf, DOC_POLICY)["coverage_limit_cents"]
    sub = _doc(cf, DOC_CLAIM_SUBMISSION)
    sub["cumulative_reimbursement_cents"] = limit + 1
    sub["coverage_remaining_cents"] = -1
    assert _fired(_write(tmp_path, cf), "pol_cumulative_within_limit")


def test_exhausted_pool_is_flagged_not_failed(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """A pool spent exactly to zero is valid, but somebody needs to know."""
    limit = _doc(cf, DOC_POLICY)["coverage_limit_cents"]
    sub = _doc(cf, DOC_CLAIM_SUBMISSION)
    sub["cumulative_reimbursement_cents"] = limit
    sub["coverage_remaining_cents"] = 0
    report = analyze_document(_write(tmp_path, cf))
    statuses = {f.status for f in report.findings
                if f.rule == "pol_coverage_not_nearly_exhausted"}
    assert Status.FLAG in statuses
    assert Status.FAIL not in statuses


# --------------------------------------------------------------------------- #
# Period boundaries are inclusive
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "when,expected_fire",
    [("2028-04-01", False), ("2028-06-30", False),
     ("2028-03-31", True), ("2028-07-01", True)],
)
def test_reporting_period_boundaries_are_inclusive(
    cf: dict[str, Any], tmp_path: Path, when: str, expected_fire: bool
) -> None:
    """The first and last day of the quarter are inside it."""
    _period(cf, CURRENT_PERIOD)["claims"][0]["claim_date"] = when
    assert _fired(_write(tmp_path, cf), "clm_claim_inside_its_period") is expected_fire


def test_policy_boundary_is_inclusive(cf: dict[str, Any], tmp_path: Path) -> None:
    """A claim on the policy's final day is covered."""
    pol = _doc(cf, DOC_POLICY)
    period = _period(cf, CURRENT_PERIOD)
    period["to_date"] = "2028-12-31"
    period["claims"][0]["claim_date"] = pol["policy_end"]
    assert not _fired(_write(tmp_path, cf), "clm_claim_inside_policy_period")


def test_claim_one_day_past_policy_end_fails(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """A claim inside its quarter can still be outside the policy entirely.

    This is the case the quarterly foot cannot catch, because the quarter still
    sums correctly with an uncovered claim inside it.
    """
    from datetime import date, timedelta

    pol = _doc(cf, DOC_POLICY)
    past = (date.fromisoformat(pol["policy_end"]) + timedelta(days=1)).isoformat()
    period = _period(cf, CURRENT_PERIOD)
    period["to_date"] = "2029-12-31"
    period["claims"][0]["claim_date"] = past
    path = _write(tmp_path, cf)
    assert _fired(path, "clm_claim_inside_policy_period")
    # ...and the quarter still foots, which is exactly why the second rule exists.
    assert not _fired(path, "clm_period_subtotals_foot")


# --------------------------------------------------------------------------- #
# Coverage begins at close of escrow
# --------------------------------------------------------------------------- #
def test_claim_on_the_close_date_is_covered(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """Coverage begins on the close date, not the day after."""
    units = _doc(cf, DOC_CLOSED_UNITS)
    claim = _period(cf, CURRENT_PERIOD)["claims"][0]
    unit = next(u for u in units["units"] if u["unit"] == claim["unit"])
    unit["close_date"] = claim["claim_date"]
    assert not _fired(_write(tmp_path, cf), "unit_claim_after_close")


def test_claim_one_day_before_close_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    from datetime import date, timedelta

    units = _doc(cf, DOC_CLOSED_UNITS)
    claim = _period(cf, CURRENT_PERIOD)["claims"][0]
    unit = next(u for u in units["units"] if u["unit"] == claim["unit"])
    unit["close_date"] = (
        date.fromisoformat(claim["claim_date"]) + timedelta(days=1)).isoformat()
    assert _fired(_write(tmp_path, cf), "unit_claim_after_close")


# --------------------------------------------------------------------------- #
# Duplicates are caught across quarters
# --------------------------------------------------------------------------- #
def test_duplicate_is_caught_across_quarters(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """The same invoice re-claimed three periods later is invisible per-quarter.

    Each quarter still foots and each looks reasonable alone; only a check that
    spans the whole history finds it.
    """
    original = _period(cf, "2027-Q3")["claims"][0]
    later = _period(cf, CURRENT_PERIOD)
    dup = dict(original)
    dup["claim_no"] = 7
    dup["claim_date"] = "2028-05-02"
    later["claims"].append(dup)
    later["subtotal_cents"] = sum(c["amount_cents"] for c in later["claims"])
    path = _write(tmp_path, cf)
    assert _fired(path, "clm_no_duplicate_invoice")
    assert not _fired(path, "clm_period_subtotals_foot")


def test_same_amount_different_invoice_is_not_a_duplicate(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """Two repairs of equal value are common and are not each other.

    Matching on amount alone would make this a false positive on ordinary data.
    """
    later = _period(cf, CURRENT_PERIOD)
    original = _period(cf, "2027-Q3")["claims"][0]
    twin = dict(original)
    twin["claim_no"] = 7
    twin["invoice_number"] = "RP-7788"
    twin["claim_date"] = "2028-05-02"
    later["claims"].append(twin)
    later["subtotal_cents"] = sum(c["amount_cents"] for c in later["claims"])
    _doc(cf, DOC_COST_LEDGER)["transactions"].append({
        "job": "2170-08", "cost_code": "86-103", "unit": twin["unit"],
        "transaction_type": "AP invoice", "transaction_date": twin["claim_date"],
        "accounting_date": "2028-05-06", "description": twin["description"],
        "vendor": twin["vendor"], "invoice_number": "RP-7788",
        "amount_cents": twin["amount_cents"],
    })
    assert not _fired(_write(tmp_path, cf), "clm_no_duplicate_invoice")


# --------------------------------------------------------------------------- #
# Missing evidence never reads as a passing control
# --------------------------------------------------------------------------- #
def test_unreadable_policy_period_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    """With no policy period, no claim can be shown to fall inside it."""
    _doc(cf, DOC_POLICY)["policy_start"] = None
    assert _fired(_write(tmp_path, cf), "clm_claim_inside_policy_period")


def test_missing_premium_rate_fails(cf: dict[str, Any], tmp_path: Path) -> None:
    _doc(cf, DOC_POLICY)["premium_rate_bps"] = None
    assert _fired(_write(tmp_path, cf), "pol_premium_derived_from_cost")


def test_unit_missing_from_closed_list_fails(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """A claim for a unit nobody recorded closing is not covered."""
    units = _doc(cf, DOC_CLOSED_UNITS)
    units["units"] = []
    assert _fired(_write(tmp_path, cf), "unit_claim_unit_has_closed")


# --------------------------------------------------------------------------- #
# The derivation chain
# --------------------------------------------------------------------------- #
def test_construction_cost_error_cascades_through_the_chain(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """Premium descends from cost and coverage from premium.

    Moving the first number leaves both derived figures wrong, which is why all
    three are checked rather than trusted -- a single mistyped construction cost
    silently rescales the entire policy.
    """
    _doc(cf, DOC_POLICY)["construction_cost_cents"] += d(500_000)
    path = _write(tmp_path, cf)
    assert _fired(path, "pol_premium_derived_from_cost")


def test_a_claim_with_no_cost_behind_it_fails(
    cf: dict[str, Any], tmp_path: Path
) -> None:
    """A claim citing an invoice the ledger has never seen is money never spent."""
    _period(cf, CURRENT_PERIOD)["claims"][0]["invoice_number"] = "XX-0000"
    assert _fired(_write(tmp_path, cf), "cost_claim_traces_to_ledger")
