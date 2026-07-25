"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one day or one member either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The re-derivation cases carry the most weight. A margin struck to the cent must
pass and a cent off must fail; an apportionment factor is floored to a basis
point and bounded to ``[0, 1]``; a roster rebuilds from the prior year plus
additions less removals exactly; a registration-renewal window closes at exactly
``lead_days`` out.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from franchise_engine.engine import (
    SEVERITY,
    check_aff_registration_renewal,
    check_apt_factor_recomputes,
    check_apt_totals_tie_receipts,
    check_grp_excluded_reconciled,
    check_grp_roster_continuity,
    check_mgn_apportioned_recomputes,
    check_mgn_margin_recomputes,
    check_mgn_revenue_ties_tb,
    check_mgn_tax_recomputes,
    check_rpt_report_totals_tie,
    check_rpt_summary_recomputes,
)
from franchise_engine.franchise import (
    apportionment_factor_bps,
    combined_members,
    taxable_margin,
)
from franchise_engine.generate import AS_OF, LEAD_DAYS, PORTFOLIOS, baseline
from franchise_engine.model import (
    DOC_AFFILIATE_REGISTER,
    DOC_COMBINED_GROUP,
    DOC_FRANCHISE_REPORT,
    DOC_MARGIN_WORKSHEET,
    DOC_RECEIPTS_FACTOR,
    DOC_TAX_SUMMARY,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _worksheet(payload: dict) -> dict:
    return _doc(payload, DOC_MARGIN_WORKSHEET)


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# mgn_ -- the margin tax re-derives to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_taxable_margin_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _worksheet(payload)["taxable_margin_cents"] += delta
    assert bool(_fired(check_mgn_margin_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_apportioned_margin_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _worksheet(payload)["apportioned_margin_cents"] += delta
    assert bool(_fired(check_mgn_apportioned_recomputes(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tax_recomputes_to_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _worksheet(payload)["tax_cents"] += delta
    assert bool(_fired(check_mgn_tax_recomputes(_ctx(payload)))) is should_fail


def test_group_revenue_must_tie_the_trial_balance() -> None:
    payload = _payload()
    assert not _fired(check_mgn_revenue_ties_tb(_ctx(payload)))
    _worksheet(payload)["group_revenue_cents"] += 1
    assert _fired(check_mgn_revenue_ties_tb(_ctx(payload)))


# --------------------------------------------------------------------------- #
# apt_ -- the apportionment factor is in-state over everywhere, bounded 0..1
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "in_state, everywhere, expected",
    [
        (75_000_000_00, 200_000_000_00, 3750),   # 37.50%
        (200_000_000_00, 200_000_000_00, 10000),  # exactly 100%
        (300_000_000_00, 200_000_000_00, 10000),  # in-state above everywhere clamps to 100%
        (0, 200_000_000_00, 0),                   # no in-state receipts
        (5_000_000_00, 0, 0),                     # no everywhere base means no factor
        (1, 3, 3333),                             # floored to the basis point, not rounded
    ],
)
def test_apportionment_factor_is_floored_and_bounded(
    in_state: int, everywhere: int, expected: int
) -> None:
    assert apportionment_factor_bps(in_state, everywhere) == expected


def test_factor_control_fires_when_factor_is_wrong() -> None:
    payload = _payload()
    assert not _fired(check_apt_factor_recomputes(_ctx(payload)))
    _doc(payload, DOC_RECEIPTS_FACTOR)["factor_bps"] += 50
    assert _fired(check_apt_factor_recomputes(_ctx(payload)))


def test_totals_tie_control_fires_when_a_total_drifts() -> None:
    payload = _payload()
    assert not _fired(check_apt_totals_tie_receipts(_ctx(payload)))
    _doc(payload, DOC_RECEIPTS_FACTOR)["in_state_total_cents"] += 100
    assert _fired(check_apt_totals_tie_receipts(_ctx(payload)))


# --------------------------------------------------------------------------- #
# taxable_margin -- the elected deduction cannot drive the margin below zero
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "revenue, deduction, expected",
    [
        (200_000_000_00, 70_000_000_00, 130_000_000_00),
        (70_000_000_00, 70_000_000_00, 0),      # deduction exactly at revenue
        (50_000_000_00, 70_000_000_00, 0),      # deduction beyond revenue does not refund
    ],
)
def test_taxable_margin_clamps_at_zero(revenue: int, deduction: int, expected: int) -> None:
    assert taxable_margin(revenue, deduction) == expected


# --------------------------------------------------------------------------- #
# grp_ -- the roster rebuilds, and the exclusions reconcile
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "prior, additions, removals, expected",
    [
        (["A", "B", "C", "D"], ["E"], ["D"], ["A", "B", "C", "E"]),
        (["A", "B"], [], [], ["A", "B"]),
        (["A", "B"], ["B"], [], ["A", "B"]),        # a re-added member is not duplicated
        (["A", "B"], ["C"], ["C"], ["A", "B"]),     # a removal wins over an addition
    ],
)
def test_combined_members_rebuilds(prior, additions, removals, expected) -> None:
    assert combined_members(prior, additions, removals) == expected


def test_roster_continuity_fires_when_the_roster_does_not_rebuild() -> None:
    payload = _payload()
    assert not _fired(check_grp_roster_continuity(_ctx(payload)))
    _doc(payload, DOC_COMBINED_GROUP)["prior_year_members"].append("AFF-06")
    assert _fired(check_grp_roster_continuity(_ctx(payload)))


def test_excluded_must_be_reconciled_against_removals() -> None:
    payload = _payload()
    assert not _fired(check_grp_excluded_reconciled(_ctx(payload)))
    _doc(payload, DOC_COMBINED_GROUP)["excluded"] = []
    assert _fired(check_grp_excluded_reconciled(_ctx(payload)))


# --------------------------------------------------------------------------- #
# aff_registration_renewal -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_flag", [(LEAD_DAYS, True), (LEAD_DAYS + 1, False)])
def test_registration_renewal_window_edge(offset: int, should_flag: bool) -> None:
    """A registration renewing exactly ``lead_days`` out is inside the window; a
    day past it is not."""
    payload = _payload()
    register = _doc(payload, DOC_AFFILIATE_REGISTER)
    register["affiliates"][0]["registration_renewal_date"] = (
        _as_of() + timedelta(days=offset)
    ).isoformat()
    fired = _fired(check_aff_registration_renewal(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_registration_renewal_is_clean_far_out() -> None:
    """The baseline registrations renew well beyond the window and raise no flag."""
    assert not _fired(check_aff_registration_renewal(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the workpapers, not the other way round
# --------------------------------------------------------------------------- #
def test_summary_must_recompute() -> None:
    payload = _payload()
    assert not _fired(check_rpt_summary_recomputes(_ctx(payload)))
    _doc(payload, DOC_TAX_SUMMARY)["tax_cents"] += 1
    assert _fired(check_rpt_summary_recomputes(_ctx(payload)))


def test_report_total_must_tie_the_summary() -> None:
    payload = _payload()
    assert not _fired(check_rpt_report_totals_tie(_ctx(payload)))
    _doc(payload, DOC_FRANCHISE_REPORT)["total_tax_due_cents"] += 1
    assert _fired(check_rpt_report_totals_tie(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "aff_unique_ids": Status.FAIL,
    "aff_address_valid": Status.FAIL,
    "aff_status_valid": Status.FAIL,
    "aff_registration_renewal": Status.FLAG,
    "grp_roster_continuity": Status.FAIL,
    "grp_members_registered": Status.FAIL,
    "grp_excluded_reconciled": Status.FAIL,
    "tb_required_fields": Status.FAIL,
    "tb_line_unique": Status.FAIL,
    "tb_member_known": Status.FAIL,
    "apt_receipts_sound": Status.FAIL,
    "apt_totals_tie_receipts": Status.FAIL,
    "apt_factor_recomputes": Status.FAIL,
    "apt_worksheet_factor_recomputes": Status.FAIL,
    "mgn_revenue_ties_tb": Status.FAIL,
    "mgn_margin_recomputes": Status.FAIL,
    "mgn_apportioned_recomputes": Status.FAIL,
    "mgn_tax_recomputes": Status.FAIL,
    "rpt_summary_recomputes": Status.FAIL,
    "rpt_report_totals_tie": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "aff", "grp", "tb", "apt", "mgn", "rpt"}
