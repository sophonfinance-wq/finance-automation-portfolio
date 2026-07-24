"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one unit either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The eligibility and re-derivation cases carry the most weight. A unit closing
exactly on the sunset date is still eligible and a day later is not; a credit met
to the cent must pass and a cent off must fail; a project that closed exactly what
it credited is clean and one unit short is a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from energy_engine.engine import (
    SEVERITY,
    check_alloc_share_rederived,
    check_cert_present_for_credited,
    check_elig_close_in_period,
    check_elig_within_sunset,
    check_fwd_remaining_to_close,
    check_fwd_total_identity,
    check_net_tax_effect,
    check_rate_gross_credit,
    check_rate_per_unit,
    check_recon_certification_gap,
    check_recon_closed_ge_credited,
    check_roll_project_units,
    check_rpt_units_times_rate,
)
from energy_engine.generate import PER_UNIT_DOLLARS, PORTFOLIOS, baseline
from energy_engine.model import (
    DOC_CLOSINGS_SCHEDULE,
    DOC_CREDIT_WORKSHEET,
    DOC_FINAL_REPORT,
    DOC_PARTNER_ALLOCATION,
    DOC_PERIOD_ROLLFORWARD,
    DOC_UNIT_REGISTER,
    Context,
    Status,
)

PER_UNIT_CENTS = PER_UNIT_DOLLARS * 100


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(PORTFOLIOS[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _unit(payload: dict, unit_id: str) -> dict:
    return next(
        u for u in _doc(payload, DOC_UNIT_REGISTER)["units"] if u["unit_id"] == unit_id
    )


def _wsproject(payload: dict, project_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_CREDIT_WORKSHEET)["projects"]
        if p["project_id"] == project_id
    )


def _rfproject(payload: dict, project_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_PERIOD_ROLLFORWARD)["projects"]
        if p["project_id"] == project_id
    )


def _clproject(payload: dict, project_id: str) -> dict:
    return next(
        p for p in _doc(payload, DOC_CLOSINGS_SCHEDULE)["projects"]
        if p["project_id"] == project_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# elig_close_in_period -- closed inside the window, boundaries inclusive
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "coe, should_fail",
    [
        ("2028-07-01", False),  # first day of the period
        ("2028-06-30", True),   # one day before the period opens
        ("2029-06-30", False),  # last day of the period
        ("2029-07-01", True),   # one day after the period closes
    ],
)
def test_close_in_period_boundaries(coe: str, should_fail: bool) -> None:
    payload = _payload()
    _unit(payload, "UNIT-A01")["coe_date"] = coe
    assert bool(_fired(check_elig_close_in_period(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# elig_within_sunset -- eligible on the sunset date, not the day after
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "coe, should_fail",
    [("2029-03-31", False), ("2029-04-01", True)],
)
def test_within_sunset_boundary(coe: str, should_fail: bool) -> None:
    """A unit closing exactly on the sunset date is still eligible; the day after
    it has missed the statute. Both dates stay inside the period window so only the
    sunset control sees them."""
    payload = _payload()
    _unit(payload, "UNIT-A01")["coe_date"] = coe
    assert bool(_fired(check_elig_within_sunset(_ctx(payload)))) is should_fail


def test_only_claimed_units_are_gated() -> None:
    """An unclaimed unit outside the period is not the eligibility control's business."""
    payload = _payload()
    unit = _unit(payload, "UNIT-A01")
    unit["claimed"] = False
    unit["coe_date"] = "2020-01-01"
    assert not _fired(check_elig_close_in_period(_ctx(payload)))
    assert not _fired(check_elig_within_sunset(_ctx(payload)))


# --------------------------------------------------------------------------- #
# cert_present_for_credited -- a claim needs a certificate
# --------------------------------------------------------------------------- #
def test_claimed_unit_must_be_certified() -> None:
    payload = _payload()
    assert not _fired(check_cert_present_for_credited(_ctx(payload)))
    _unit(payload, "UNIT-A01")["certified"] = False
    assert _fired(check_cert_present_for_credited(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rate_per_unit -- the credited amount is the statutory rate, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_per_unit_rate_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _unit(payload, "UNIT-A01")["credited_amount_cents"] = PER_UNIT_CENTS + delta
    assert bool(_fired(check_rate_per_unit(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rate_gross_credit -- gross is units x rate, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_gross_credit_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    proj = _wsproject(payload, "PRJ-ALDR")
    proj["gross_credit_cents"] = proj["gross_credit_cents"] + delta
    assert bool(_fired(check_rate_gross_credit(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# rpt_units_times_rate -- the report foots to itself
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_report_units_times_rate(delta: int, should_fail: bool) -> None:
    payload = _payload()
    report = _doc(payload, DOC_FINAL_REPORT)
    report["total_credits_cents"] = report["total_credits_cents"] + delta
    assert bool(_fired(check_rpt_units_times_rate(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# net_tax_effect -- minus the credit at the effective rate, to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_tax_effect_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    proj = _wsproject(payload, "PRJ-ALDR")
    proj["tax_effect_cents"] = proj["tax_effect_cents"] + delta
    assert bool(_fired(check_net_tax_effect(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# roll_project_units -- the worksheet count ties the register
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_project_units_tie_the_register(delta: int, should_fail: bool) -> None:
    payload = _payload()
    proj = _wsproject(payload, "PRJ-ALDR")
    proj["qualifying_units"] = proj["qualifying_units"] + delta
    assert bool(_fired(check_roll_project_units(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# alloc_share_rederived -- each share re-derives from ownership
# --------------------------------------------------------------------------- #
def test_partner_shares_must_rederive() -> None:
    payload = _payload()
    assert not _fired(check_alloc_share_rederived(_ctx(payload)))
    partners = _doc(payload, DOC_PARTNER_ALLOCATION)["partners"]
    partners[0]["allocated_cents"], partners[1]["allocated_cents"] = (
        partners[1]["allocated_cents"],
        partners[0]["allocated_cents"],
    )
    assert _fired(check_alloc_share_rederived(_ctx(payload)))


# --------------------------------------------------------------------------- #
# fwd_total_identity -- total = closed + remaining
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_rollforward_identity(delta: int, should_fail: bool) -> None:
    payload = _payload()
    proj = _rfproject(payload, "PRJ-ALDR")
    proj["total_units"] = proj["total_units"] + delta
    assert bool(_fired(check_fwd_total_identity(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# fwd_remaining_to_close -- a flag, not a failure
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("remaining, should_flag", [(0, False), (1, True)])
def test_remaining_to_close_flags(remaining: int, should_flag: bool) -> None:
    payload = _payload()
    proj = _rfproject(payload, "PRJ-ALDR")
    proj["remaining_units"] = remaining
    proj["total_units"] = sum(proj["closed_by_period"]) + remaining
    fired = _fired(check_fwd_remaining_to_close(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# recon_closed_ge_credited / recon_certification_gap -- the two directions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "closed, should_fail", [(4, False), (3, True)]
)
def test_closed_must_cover_credited(closed: int, should_fail: bool) -> None:
    """PRJ-ALDR credits 4 units; the closings schedule must show at least 4."""
    payload = _payload()
    _clproject(payload, "PRJ-ALDR")["closed_units"] = closed
    assert bool(_fired(check_recon_closed_ge_credited(_ctx(payload)))) is should_fail


@pytest.mark.parametrize(
    "closed, should_flag", [(4, False), (5, True)]
)
def test_certification_gap_flags(closed: int, should_flag: bool) -> None:
    """PRJ-ALDR credits 4 units; more than 4 closed is a certification-gap flag."""
    payload = _payload()
    _clproject(payload, "PRJ-ALDR")["closed_units"] = closed
    fired = _fired(check_recon_certification_gap(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "unit_unique_ids": Status.FAIL,
    "unit_required_fields": Status.FAIL,
    "unit_project_known": Status.FAIL,
    "elig_close_in_period": Status.FAIL,
    "elig_within_sunset": Status.FAIL,
    "cert_present_for_credited": Status.FAIL,
    "cert_rater_id": Status.FAIL,
    "dup_no_double_count": Status.FAIL,
    "rate_per_unit": Status.FAIL,
    "rate_gross_credit": Status.FAIL,
    "rpt_units_times_rate": Status.FAIL,
    "roll_project_units": Status.FAIL,
    "roll_grand_total": Status.FAIL,
    "roll_region_subtotal": Status.FAIL,
    "fwd_total_identity": Status.FAIL,
    "fwd_period_bounds": Status.FAIL,
    "fwd_remaining_to_close": Status.FLAG,
    "net_addback": Status.FAIL,
    "net_tax_effect": Status.FAIL,
    "net_benefit": Status.FAIL,
    "alloc_shares_sum": Status.FAIL,
    "alloc_share_rederived": Status.FAIL,
    "recon_final_report_ties": Status.FAIL,
    "recon_closed_ge_credited": Status.FAIL,
    "recon_certification_gap": Status.FLAG,
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
        "set", "unit", "elig", "cert", "dup", "rate", "rpt", "roll", "fwd",
        "net", "alloc", "recon",
    }
