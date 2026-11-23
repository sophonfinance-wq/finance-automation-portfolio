"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of
the line. A control that fires a cent early is as wrong as one that never fires,
and only a boundary test can tell the two apart.

The trigger, floor and fee cases carry the most weight. An Initial Commitment
approval dated *on* the breach date satisfies the trigger and one day later does
not; a contingency met to the cent passes and a cent under fails; bid coverage
at exactly 80% clears the gate and a cent short of it does not; the template
refreshed exactly on the review date is current.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from spending_engine.engine import (
    SEVERITY,
    check_bid_coverage_meets,
    check_cal_basis_matches_waiver,
    check_cal_template_current,
    check_cty_hard_floor,
    check_cty_soft_floor,
    check_fee_cm_rederives,
    check_fee_variance_rederives,
    check_gro_growth_default,
    check_seq_gate_summary_recomputes,
    check_trg_ic_before_pursuit_spend,
)
from spending_engine.generate import PORTFOLIOS, baseline
from spending_engine.model import (
    DOC_BID_SCHEDULE,
    DOC_COST_BUDGET,
    DOC_GATE_SUMMARY,
    DOC_PLAN_COMPARISON,
    DOC_PROJECT_PROFILE,
    GC_OWNER,
    Context,
    Status,
)
from spending_engine.money import apply_rate
from spending_engine.standards import (
    DEV_FEE_RATE_BPS,
    derive_fee_block,
    first_breach,
    latest_template_refresh,
    meets_floor,
    required_basis,
    trigger_satisfied,
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


def _approval(payload: dict, approval_id: str) -> dict:
    log = next(d for d in payload["documents"] if d["doc_type"] == "approval_log")
    return next(a for a in log["approvals"] if a["approval_id"] == approval_id)


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# trg_ -- the approval must precede the breach, not merely exist
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "ic_date, should_fail",
    [("2028-11-01", False), ("2028-10-15", False), ("2028-11-02", True)],
)
def test_ic_on_the_breach_date_satisfies_the_trigger(
    ic_date: str, should_fail: bool
) -> None:
    """The cumulative pursuit spend crosses its trigger on 2028-11-01. An IC
    approval dated that same day (or earlier) satisfies the gate; one dated the
    day after is capital committed before the approval."""
    payload = _payload()
    _approval(payload, "SR-01")["approval_date"] = ic_date
    assert bool(_fired(check_trg_ic_before_pursuit_spend(_ctx(payload)))) is should_fail


@pytest.mark.parametrize(
    "entries, threshold, expected",
    [
        ([(date(2030, 1, 1), 100)], 100, date(2030, 1, 1)),  # reached exactly
        ([(date(2030, 1, 1), 99)], 100, None),  # one cent under
        (
            [(date(2030, 1, 2), 60), (date(2030, 1, 1), 50)],
            100,
            date(2030, 1, 2),
        ),  # accumulated in date order, not file order
        ([], 100, None),
    ],
)
def test_first_breach_lands_on_the_crossing_entry(
    entries: list, threshold: int, expected: date | None
) -> None:
    assert first_breach(entries, threshold) == expected


def test_trigger_satisfied_boundary() -> None:
    breach = date(2030, 1, 15)
    assert trigger_satisfied(None, None)  # no breach, nothing to authorize
    assert trigger_satisfied(breach, date(2030, 1, 15))  # approved on the day
    assert not trigger_satisfied(breach, date(2030, 1, 16))  # a day late
    assert not trigger_satisfied(breach, None)  # never approved


# --------------------------------------------------------------------------- #
# cty_ -- the floor is met at the floor, not a cent under
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_site_contingency_meets_floor_at_the_cent(delta: int, should_fail: bool) -> None:
    """The baseline site contingency sits exactly at the 10% construction-start
    floor, so one cent either side is the whole of the boundary."""
    payload = _payload()
    _doc(payload, DOC_COST_BUDGET)["site_contingency_cents"] += delta
    assert bool(_fired(check_cty_hard_floor(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_soft_contingency_meets_floor_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_COST_BUDGET)["soft_contingency_cents"] += delta
    assert bool(_fired(check_cty_soft_floor(_ctx(payload)))) is should_fail


def test_soft_floor_shortfall_passes_with_documented_justification() -> None:
    """The standards permit an under-floor soft contingency only with a
    documented justification; the flag flips a FAIL into a documented PASS."""
    payload = _payload()
    budget = _doc(payload, DOC_COST_BUDGET)
    budget["soft_contingency_cents"] -= 1
    assert _fired(check_cty_soft_floor(_ctx(payload)))
    budget["soft_floor_justification_documented"] = True
    assert not _fired(check_cty_soft_floor(_ctx(payload)))


@pytest.mark.parametrize(
    "part, base, floor_bps, expected",
    [
        (1000, 10000, 1000, True),  # exactly at the floor
        (999, 10000, 1000, False),  # one cent under
        (0, 0, 1000, True),  # no base carries no floor
    ],
)
def test_meets_floor_is_exact(part: int, base: int, floor_bps: int, expected: bool) -> None:
    assert meets_floor(part, base, floor_bps) is expected


# --------------------------------------------------------------------------- #
# fee_ -- the formula is met with exact equality
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_cm_fee_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_COST_BUDGET)["cm_fee_cents"] += delta
    assert bool(_fired(check_fee_cm_rederives(_ctx(payload)))) is should_fail


def test_derived_fee_block_is_internally_consistent() -> None:
    """The fixed-point Development Fee satisfies its own formula exactly, so the
    generator's stated figures always tie under the engine's ``==`` tests."""
    cm, dev, tpc = derive_fee_block(
        2_400_000_000, 210_000_000, 400_000_000, 20_000_000, 150_000_000
    )
    assert dev == apply_rate(tpc - 150_000_000, DEV_FEE_RATE_BPS)
    assert tpc == (
        2_400_000_000 + 210_000_000 + 400_000_000 + 20_000_000 + 150_000_000 + cm + dev
    )


def test_variance_must_rederive() -> None:
    payload = _payload()
    assert not _fired(check_fee_variance_rederives(_ctx(payload)))
    _doc(payload, DOC_PLAN_COMPARISON)["rows"][0]["variance_cents"] += 1
    assert _fired(check_fee_variance_rederives(_ctx(payload)))


# --------------------------------------------------------------------------- #
# bid_ -- coverage clears at exactly 80%
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "covered, should_fail",
    [(1_920_000_000, False), (1_919_999_999, True)],
)
def test_third_party_bid_coverage_edge(covered: int, should_fail: bool) -> None:
    """Hard cost is 24,000,000.00, so 80% coverage is exactly 19,200,000.00;
    covered amounts one cent either side sit on the boundary."""
    payload = _payload()
    schedule = _doc(payload, DOC_BID_SCHEDULE)
    schedule["lines"] = [
        {
            "line_id": "BID-01",
            "description": "Bid scope",
            "amount_cents": covered,
            "competitively_bid": True,
        },
        {
            "line_id": "BID-02",
            "description": "Unbid scope",
            "amount_cents": 2_400_000_000 - covered,
            "competitively_bid": False,
        },
    ]
    assert bool(_fired(check_bid_coverage_meets(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("unbid_lines, should_fail", [(1, False), (2, True)])
def test_owner_gc_line_item_coverage_edge(unbid_lines: int, should_fail: bool) -> None:
    """An owner-GC project counts line items: 5 of 6 bid is 83% and clears the
    80% threshold; 4 of 6 is 66% and does not."""
    payload = _payload()
    _doc(payload, DOC_PROJECT_PROFILE)["gc_model"] = GC_OWNER
    lines = _doc(payload, DOC_BID_SCHEDULE)["lines"]
    for row in lines[:unbid_lines]:
        row["competitively_bid"] = False
    assert bool(_fired(check_bid_coverage_meets(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# gro_ -- the default is an equality, the escape is a membership fact
# --------------------------------------------------------------------------- #
def test_growth_default_is_exact() -> None:
    payload = _payload()
    assert not _fired(check_gro_growth_default(_ctx(payload)))
    profile = _doc(payload, DOC_PROJECT_PROFILE)
    profile["cost_growth_bps"] = 301
    assert _fired(check_gro_growth_default(_ctx(payload)))
    profile["market_supported_growth"] = True
    assert not _fired(check_gro_growth_default(_ctx(payload)))


# --------------------------------------------------------------------------- #
# cal_ -- the basis switch and the template calendar
# --------------------------------------------------------------------------- #
def test_required_basis_switches_on_the_waiver() -> None:
    assert required_basis(False) == "template"
    assert required_basis(True) == "actual_plan"


def test_basis_must_match_the_waiver_status() -> None:
    payload = _payload()
    assert not _fired(check_cal_basis_matches_waiver(_ctx(payload)))
    _doc(payload, DOC_PLAN_COMPARISON)["basis"] = "template"
    assert _fired(check_cal_basis_matches_waiver(_ctx(payload)))


@pytest.mark.parametrize(
    "as_of, expected",
    [
        (date(2030, 3, 15), date(2030, 1, 1)),
        (date(2030, 1, 1), date(2030, 1, 1)),  # refreshed on the review date
        (date(2029, 12, 31), date(2029, 6, 1)),  # the day before the refresh
        (date(2030, 6, 1), date(2030, 6, 1)),
        (date(2030, 8, 20), date(2030, 6, 1)),
    ],
)
def test_latest_template_refresh(as_of: date, expected: date) -> None:
    assert latest_template_refresh(as_of) == expected


@pytest.mark.parametrize(
    "template_date, should_flag",
    [("2030-01-01", False), ("2029-06-01", True)],
)
def test_template_currency_when_the_regime_is_in_effect(
    template_date: str, should_flag: bool
) -> None:
    payload = _payload()
    _doc(payload, DOC_PROJECT_PROFILE)["feasibility_waived"] = False
    comparison = _doc(payload, DOC_PLAN_COMPARISON)
    comparison["basis"] = "template"
    comparison["template_effective_date"] = template_date
    fired = _fired(check_cal_template_current(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_template_currency_is_not_checked_outside_the_regime() -> None:
    """A wrong basis is owned by ``cal_basis_matches_waiver``; the calendar
    control must not double-report it."""
    payload = _payload()
    _doc(payload, DOC_PLAN_COMPARISON)["basis"] = "template"  # waiver still True
    assert not _fired(check_cal_template_current(_ctx(payload)))


# --------------------------------------------------------------------------- #
# seq_ -- the gate summary recomputes from the evidence, not the other way round
# --------------------------------------------------------------------------- #
def test_gate_summary_must_recompute() -> None:
    """A stated determination that contradicts the evidence fails; leaving it
    derived fails not."""
    payload = _payload()
    assert not _fired(check_seq_gate_summary_recomputes(_ctx(payload)))
    _doc(payload, DOC_GATE_SUMMARY)["phases"][1]["gate_cleared"] = False
    assert _fired(check_seq_gate_summary_recomputes(_ctx(payload)))


def test_gate_summary_missing_phase_row_fails() -> None:
    payload = _payload()
    summary = _doc(payload, DOC_GATE_SUMMARY)
    summary["phases"] = summary["phases"][1:]
    assert _fired(check_seq_gate_summary_recomputes(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "trg_ic_before_pursuit_spend": Status.FAIL,
    "trg_ic_before_nonrefundable_deposit": Status.FAIL,
    "trg_ic_before_refundable_deposits": Status.FAIL,
    "seq_phase_known": Status.FAIL,
    "seq_approvals_in_order": Status.FAIL,
    "seq_no_phase_skipped": Status.FAIL,
    "seq_current_phase_approved": Status.FAIL,
    "seq_gate_summary_recomputes": Status.FAIL,
    "del_items_known": Status.FAIL,
    "del_unique_rows": Status.FAIL,
    "del_prior_phase_complete": Status.FAIL,
    "del_current_phase_outstanding": Status.FLAG,
    "del_estimate_basis_matches": Status.FAIL,
    "cty_hard_floor": Status.FAIL,
    "cty_soft_floor": Status.FAIL,
    "cty_split_foots": Status.FAIL,
    "cty_escalation_reserved": Status.FAIL,
    "gro_growth_default": Status.FAIL,
    "fee_cm_rederives": Status.FAIL,
    "fee_dev_rederives": Status.FAIL,
    "fee_tpc_foots": Status.FAIL,
    "fee_variance_rederives": Status.FAIL,
    "cal_basis_matches_waiver": Status.FAIL,
    "cal_template_current": Status.FLAG,
    "evt_type_known": Status.FAIL,
    "evt_interim_request_filed": Status.FAIL,
    "bid_coverage_meets": Status.FAIL,
    "bid_gmp_bindable": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {
        "set", "trg", "seq", "del", "cty", "gro", "fee", "cal", "evt", "bid",
    }
