"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a day early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

Contexts are built from the generator's clean baseline and mutated in memory, so
each case differs from a known-passing programme by exactly the fact under test.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from bond_engine.engine import (
    SEVERITY,
    check_coll_not_exceed_penal_sum,
    check_coll_refund_aging,
    check_expo_within_facility_limit,
    check_life_expiry_horizon,
    check_life_no_release_while_collateral_outstanding,
    check_life_release_after_obligation,
    check_life_renewal_continuity,
    check_prem_no_premium_after_release,
    check_prem_rate_within_schedule,
    check_stat_licence_minimum,
)
from bond_engine.generate import PROGRAMMES, baseline, rederive
from bond_engine.model import (
    COLL_POSTED,
    DOC_BOND_REGISTER,
    DOC_COLLATERAL_LEDGER,
    DOC_PREMIUM_LEDGER,
    DOC_SURETY_FACILITY,
    EXPIRY_HORIZON_DAYS,
    COLLATERAL_AGE_BANDS,
    Context,
    Status,
)

AS_OF = date(2029, 2, 15)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PROGRAMMES[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _bond(payload: dict, bond_no: str) -> dict:
    return next(
        b for b in _doc(payload, DOC_BOND_REGISTER)["bonds"] if b["bond_no"] == bond_no
    )


def _entry(payload: dict, doc_type: str, entry_no: str) -> dict:
    return next(e for e in _doc(payload, doc_type)["entries"] if e["entry_no"] == entry_no)


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _iso(d: date) -> str:
    return d.isoformat()


# --------------------------------------------------------------------------- #
# life_expiry_horizon -- the renewal window
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset_days, should_flag",
    [
        (EXPIRY_HORIZON_DAYS - 1, True),
        (EXPIRY_HORIZON_DAYS, True),  # inclusive at the edge
        (EXPIRY_HORIZON_DAYS + 1, False),
    ],
)
def test_expiry_horizon_is_inclusive_at_its_edge(
    offset_days: int, should_flag: bool
) -> None:
    payload = _payload()
    _bond(payload, "B-4445")["expiration_date"] = _iso(AS_OF + timedelta(days=offset_days))
    findings = check_life_expiry_horizon(_ctx(payload))
    assert bool(_fired(findings)) is should_flag


def test_expiry_horizon_ignores_bonds_that_are_not_active() -> None:
    """A released bond inside the window needs no renewal decision."""
    payload = _payload()
    bond = _bond(payload, "B-4445")
    bond["expiration_date"] = _iso(AS_OF + timedelta(days=10))
    bond["status"] = "released"
    bond["release_date"] = "2029-01-05"
    bond["release_reference"] = "REL-2029-0002"
    assert not _fired(check_life_expiry_horizon(_ctx(payload)))


# --------------------------------------------------------------------------- #
# life_renewal_continuity -- the unbonded window
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "gap_days, should_fail",
    [
        (0, False),  # new term starts the day the old one ended
        (1, False),  # starts the next day -- continuous
        (2, True),   # one clear day with no bond in force
    ],
)
def test_renewal_continuity_allows_only_a_seamless_handover(
    gap_days: int, should_fail: bool
) -> None:
    payload = _payload()
    prior_expiry = date.fromisoformat(_bond(payload, "B-4399")["expiration_date"])
    _bond(payload, "B-4401")["effective_date"] = _iso(prior_expiry + timedelta(days=gap_days))
    findings = check_life_renewal_continuity(_ctx(payload))
    assert bool(_fired(findings)) is should_fail


def test_renewal_pointing_at_a_missing_bond_fails() -> None:
    """Continuity cannot be proven against a predecessor that is not there."""
    payload = _payload()
    _bond(payload, "B-4401")["renewed_from"] = "B-0000"
    assert _fired(check_life_renewal_continuity(_ctx(payload)))


# --------------------------------------------------------------------------- #
# life_release_after_obligation -- standing down cover too early
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset_days, should_fail",
    [(-1, True), (0, False), (1, False)],
)
def test_release_on_the_obligation_end_date_is_allowed(
    offset_days: int, should_fail: bool
) -> None:
    """A maintenance bond may be released the day the warranty period ends."""
    payload = _payload()
    warranty_end = date(2028, 5, 20)  # PRJ-133 warranty end
    _bond(payload, "B-4431")["release_date"] = _iso(warranty_end + timedelta(days=offset_days))
    findings = check_life_release_after_obligation(_ctx(payload))
    assert bool(_fired(findings)) is should_fail


def test_licence_bond_has_no_project_obligation_to_release_against() -> None:
    """A licence bond secures a registration, so no project date constrains it."""
    payload = _payload()
    bond = _bond(payload, "B-4399")
    bond["status"] = "released"
    bond["release_date"] = "2028-09-02"
    bond["release_reference"] = "REL-2028-0100"
    assert not _fired(check_life_release_after_obligation(_ctx(payload)))


# --------------------------------------------------------------------------- #
# life_no_release_while_collateral_outstanding -- the headline control
# --------------------------------------------------------------------------- #
def test_released_bond_with_outstanding_collateral_and_no_status_fails() -> None:
    payload = _payload()
    ledger = _doc(payload, DOC_COLLATERAL_LEDGER)
    ledger["entries"] = [e for e in ledger["entries"] if e["entry_no"] != "C-0030"]
    rederive(payload)
    assert _fired(check_life_no_release_while_collateral_outstanding(_ctx(payload)))


def test_a_refund_recorded_in_flight_satisfies_the_control() -> None:
    """The control asks for a chase, not for the cash to already be back."""
    payload = _payload()
    ledger = _doc(payload, DOC_COLLATERAL_LEDGER)
    ledger["entries"] = [e for e in ledger["entries"] if e["entry_no"] != "C-0030"]
    _bond(payload, "B-4415")["collateral_refund_status"] = "requested 2028-08-10"
    rederive(payload)
    assert not _fired(check_life_no_release_while_collateral_outstanding(_ctx(payload)))


def test_active_bond_with_collateral_is_not_a_finding() -> None:
    """Collateral on a live bond is doing its job."""
    payload = _payload()
    assert not _fired(check_life_no_release_while_collateral_outstanding(_ctx(payload)))


# --------------------------------------------------------------------------- #
# coll_refund_aging -- escalation by age band
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "age_days, should_flag",
    [
        (COLLATERAL_AGE_BANDS[0] - 1, False),
        (COLLATERAL_AGE_BANDS[0], True),
        (COLLATERAL_AGE_BANDS[-1] + 5, True),
    ],
)
def test_refund_aging_starts_at_the_first_band(age_days: int, should_flag: bool) -> None:
    payload = _payload()
    ledger = _doc(payload, DOC_COLLATERAL_LEDGER)
    ledger["entries"] = [e for e in ledger["entries"] if e["entry_no"] != "C-0030"]
    _bond(payload, "B-4415")["release_date"] = _iso(AS_OF - timedelta(days=age_days))
    rederive(payload)
    assert bool(_fired(check_coll_refund_aging(_ctx(payload)))) is should_flag


def test_refund_aging_reports_the_widest_band_reached() -> None:
    """A year-old balance is reported against the oldest band, not the first."""
    payload = _payload()
    ledger = _doc(payload, DOC_COLLATERAL_LEDGER)
    ledger["entries"] = [e for e in ledger["entries"] if e["entry_no"] != "C-0030"]
    _bond(payload, "B-4415")["release_date"] = _iso(
        AS_OF - timedelta(days=COLLATERAL_AGE_BANDS[-1] + 10)
    )
    rederive(payload)
    fired = _fired(check_coll_refund_aging(_ctx(payload)))
    assert fired and f">{COLLATERAL_AGE_BANDS[-1]}-day band" in fired[0].message


# --------------------------------------------------------------------------- #
# coll_not_exceed_penal_sum -- one cent over the exposure
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_collateral_may_equal_but_not_exceed_the_penal_sum(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    penal = _bond(payload, "B-4440")["penal_sum_cents"]
    _entry(payload, DOC_COLLATERAL_LEDGER, "C-0025")["amount_cents"] = penal + delta
    rederive(payload)
    assert bool(_fired(check_coll_not_exceed_penal_sum(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# expo_within_facility_limit -- capacity at the edge
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_exposure_may_reach_but_not_pass_the_facility_limit(
    delta: int, should_fail: bool
) -> None:
    """``delta`` moves the *limit* around the fixed active exposure."""
    payload = _payload()
    exposure = sum(
        b["penal_sum_cents"]
        for b in _doc(payload, DOC_BOND_REGISTER)["bonds"]
        if b["status"] == "active"
    )
    _doc(payload, DOC_SURETY_FACILITY)["aggregate_limit_cents"] = exposure + delta
    assert bool(_fired(check_expo_within_facility_limit(_ctx(payload)))) is should_fail


def test_released_bonds_do_not_consume_capacity() -> None:
    """Capacity is the point of releasing cleanly, so the control must reflect it."""
    payload = _payload()
    active = sum(
        b["penal_sum_cents"]
        for b in _doc(payload, DOC_BOND_REGISTER)["bonds"]
        if b["status"] == "active"
    )
    every = sum(b["penal_sum_cents"] for b in _doc(payload, DOC_BOND_REGISTER)["bonds"])
    assert active < every
    _doc(payload, DOC_SURETY_FACILITY)["aggregate_limit_cents"] = active
    assert not _fired(check_expo_within_facility_limit(_ctx(payload)))


# --------------------------------------------------------------------------- #
# stat_licence_minimum -- the statute is a floor, not a target
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_licence_bond_may_equal_or_exceed_the_statutory_minimum(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _bond(payload, "B-4402")["penal_sum_cents"] = 1_500_000 + delta
    assert bool(_fired(check_stat_licence_minimum(_ctx(payload)))) is should_fail


def test_non_statutory_bond_types_are_not_constrained() -> None:
    """Only bond types the statutory table names are tested against a minimum."""
    payload = _payload()
    _bond(payload, "B-4440")["penal_sum_cents"] = 100
    rederive(payload)
    assert not _fired(check_stat_licence_minimum(_ctx(payload)))


# --------------------------------------------------------------------------- #
# prem_no_premium_after_release -- the period that starts too late
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset_days, should_fail", [(-1, False), (0, False), (1, True)])
def test_premium_period_may_start_on_the_release_date(
    offset_days: int, should_fail: bool
) -> None:
    payload = _payload()
    release = date.fromisoformat(_bond(payload, "B-4431")["release_date"])
    entry = _entry(payload, DOC_PREMIUM_LEDGER, "P-0105")
    entry["period_from"] = _iso(release + timedelta(days=offset_days))
    assert bool(_fired(check_prem_no_premium_after_release(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# prem_rate_within_schedule -- the one deliberately tolerant control
# --------------------------------------------------------------------------- #
def test_premium_exactly_at_the_tolerance_edge_is_allowed() -> None:
    payload = _payload()
    bond = _bond(payload, "B-4445")
    expected = bond["annual_premium_cents"]
    tolerance = expected * 1500 // 10000
    bond["annual_premium_cents"] = expected + tolerance
    assert not _fired(check_prem_rate_within_schedule(_ctx(payload)))


def test_premium_one_cent_past_the_tolerance_flags() -> None:
    payload = _payload()
    bond = _bond(payload, "B-4445")
    expected = bond["annual_premium_cents"]
    tolerance = expected * 1500 // 10000
    bond["annual_premium_cents"] = expected + tolerance + 1
    assert _fired(check_prem_rate_within_schedule(_ctx(payload)))


def test_minimum_premium_floors_the_rate_card() -> None:
    """A small bond is rated at the surety's minimum, not at rate times penal sum.

    ``B-4431`` is the case in the baseline: 120 bps of its penal sum comes to less
    than the minimum premium, so the floor is what the control expects.
    """
    payload = _payload()
    bond = _bond(payload, "B-4431")
    assert bond["annual_premium_cents"] == 35_000
    assert not _fired(check_prem_rate_within_schedule(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "reg_bond_number_unique": Status.FAIL,
    "reg_required_fields": Status.FAIL,
    "reg_status_domain": Status.FAIL,
    "reg_effective_before_expiration": Status.FAIL,
    "reg_project_mapped": Status.FAIL,
    "stat_licence_minimum": Status.FAIL,
    "stat_obligee_kind_matches_type": Status.FLAG,
    "stat_permit_reference_present": Status.FLAG,
    "life_active_not_expired": Status.FAIL,
    "life_expiry_horizon": Status.FLAG,
    "life_renewal_continuity": Status.FAIL,
    "life_released_has_evidence": Status.FAIL,
    "life_release_after_obligation": Status.FAIL,
    "life_maintenance_follows_acceptance": Status.FLAG,
    "life_no_release_while_collateral_outstanding": Status.FAIL,
    "coll_not_exceed_penal_sum": Status.FAIL,
    "coll_ledger_ties_register": Status.FAIL,
    "coll_refund_not_exceed_posted": Status.FAIL,
    "coll_refund_aging": Status.FLAG,
    "coll_location_recorded": Status.FLAG,
    "coll_ties_restricted_cash_gl": Status.FAIL,
    "prem_rate_within_schedule": Status.FLAG,
    "prem_no_premium_after_release": Status.FAIL,
    "prem_prepaid_amortisation_ties": Status.FAIL,
    "prem_return_has_rider": Status.FLAG,
    "prem_entry_type_domain": Status.FAIL,
    "expo_within_facility_limit": Status.FAIL,
    "expo_by_obligee_ties_total": Status.FAIL,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """The severity a rule declares at runtime is the one it was designed with.

    ``reports`` is requested so the whole registry has executed and populated
    ``SEVERITY`` before the comparison.
    """
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    """A new control cannot ship without a declared, reviewed severity."""
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    """Prefixes are how the report groups controls; a stray one hides a rule."""
    assert rule_id.split("_")[0] in {
        "set", "reg", "stat", "life", "coll", "prem", "expo"
    }
