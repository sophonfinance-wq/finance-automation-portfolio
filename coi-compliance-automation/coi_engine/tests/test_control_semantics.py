"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The adequacy and expiry cases carry the most weight. A limit met to the cent must
pass and a cent short must fail; a certificate in force on the review date is not
the same as one expiring the day after; a renewal at the very edge of the lead
window is inside it and a day past the edge is not.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from coi_engine.engine import (
    SEVERITY,
    check_cov_aggregate_meets,
    check_cov_no_uninsured_gap,
    check_cov_per_occurrence_meets,
    check_end_additional_insured_present,
    check_exp_not_expired,
    check_exp_renewal_lead_time,
    check_exp_workers_comp_present,
    check_rpt_party_compliant_recomputes,
    check_rpt_report_count_ties,
    check_rpt_watchlist_ties,
)
from coi_engine.generate import AS_OF, PORTFOLIOS, RENEWAL_LEAD_DAYS, baseline
from coi_engine.model import (
    DOC_CERTIFICATE_REGISTER,
    DOC_COMPLIANCE_REPORT,
    DOC_COVERAGE_SUMMARY,
    DOC_RENEWAL_WATCHLIST,
    DOC_REQUIREMENT_MATRIX,
    PARTY_GENERAL_CONTRACTOR,
    COVERAGE_CGL,
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


def _cert(payload: dict, certificate_id: str) -> dict:
    return next(
        c for c in _doc(payload, DOC_CERTIFICATE_REGISTER)["certificates"]
        if c["certificate_id"] == certificate_id
    )


def _matrix_row(payload: dict, party_type: str, coverage_type: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_REQUIREMENT_MATRIX)["requirements"]
        if r["party_type"] == party_type and r["coverage_type"] == coverage_type
    )


def _summary_row(payload: dict, party_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_COVERAGE_SUMMARY)["parties"]
        if r["party_id"] == party_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


# --------------------------------------------------------------------------- #
# cov_per_occurrence_meets -- the limit is met at the requirement, not a cent under
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_per_occurrence_meets_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    required = _matrix_row(payload, PARTY_GENERAL_CONTRACTOR, COVERAGE_CGL)[
        "required_per_occurrence_cents"
    ]
    _cert(payload, "COI-1001")["per_occurrence_cents"] = required + delta
    assert bool(_fired(check_cov_per_occurrence_meets(_ctx(payload)))) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, False)])
def test_aggregate_meets_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    required = _matrix_row(payload, PARTY_GENERAL_CONTRACTOR, COVERAGE_CGL)[
        "required_aggregate_cents"
    ]
    _cert(payload, "COI-1001")["aggregate_cents"] = required + delta
    assert bool(_fired(check_cov_aggregate_meets(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# cov_no_uninsured_gap -- the renewal must not leave an uninsured day
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "inception, should_fail",
    [("2029-06-01", False), ("2029-05-31", False), ("2029-06-02", True)],
)
def test_renewal_leaves_no_uninsured_day(inception: str, should_fail: bool) -> None:
    """The prior GL certificate expires 2029-06-01; a renewal incepting a day later
    leaves a gap. Binding it early is an overlap, which the control tolerates."""
    payload = _payload()
    _cert(payload, "COI-1001")["inception_date"] = inception
    assert bool(_fired(check_cov_no_uninsured_gap(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exp_not_expired -- expired on the review date, not the day after
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(0, True), (1, False)])
def test_expired_on_the_review_date(offset: int, should_fail: bool) -> None:
    """A certificate expiring exactly on ``as_of`` has lapsed; one day later is in
    force."""
    payload = _payload()
    expiration = (_as_of() + timedelta(days=offset)).isoformat()
    _cert(payload, "COI-1006")["expiration_date"] = expiration
    assert bool(_fired(check_exp_not_expired(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# exp_renewal_lead_time -- the window closes at exactly lead_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_flag", [(RENEWAL_LEAD_DAYS, True), (RENEWAL_LEAD_DAYS + 1, False)])
def test_renewal_window_edge(offset: int, should_flag: bool) -> None:
    """A term ending exactly ``lead_days`` out is inside the window; a day past it
    is not."""
    payload = _payload()
    expiration = (_as_of() + timedelta(days=offset)).isoformat()
    _cert(payload, "COI-1006")["expiration_date"] = expiration
    fired = _fired(check_exp_renewal_lead_time(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_renewal_window_is_clean_far_out() -> None:
    """The baseline certificates expire well beyond the window and raise no flag."""
    assert not _fired(check_exp_renewal_lead_time(_ctx(_payload())))


# --------------------------------------------------------------------------- #
# end_additional_insured_present -- the endorsement is present where required
# --------------------------------------------------------------------------- #
def test_additional_insured_must_be_present_where_required() -> None:
    payload = _payload()
    assert not _fired(check_end_additional_insured_present(_ctx(payload)))
    _cert(payload, "COI-1001")["additional_insured"] = False
    assert _fired(check_end_additional_insured_present(_ctx(payload)))


# --------------------------------------------------------------------------- #
# exp_workers_comp_present -- the statutory floor for every party
# --------------------------------------------------------------------------- #
def test_workers_comp_is_required_of_every_party() -> None:
    payload = _payload()
    assert not _fired(check_exp_workers_comp_present(_ctx(payload)))
    register = _doc(payload, DOC_CERTIFICATE_REGISTER)
    register["certificates"] = [
        c for c in register["certificates"] if c["certificate_id"] != "COI-1004"
    ]
    assert _fired(check_exp_workers_comp_present(_ctx(payload)))


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence, not the other way round
# --------------------------------------------------------------------------- #
def test_compliant_flag_must_recompute() -> None:
    """A stated flag that contradicts the certificates fails; leaving it fails not."""
    payload = _payload()
    assert not _fired(check_rpt_party_compliant_recomputes(_ctx(payload)))
    _summary_row(payload, "PTY-101")["compliant"] = False
    assert _fired(check_rpt_party_compliant_recomputes(_ctx(payload)))


def test_report_count_must_tie_the_summary() -> None:
    payload = _payload()
    assert not _fired(check_rpt_report_count_ties(_ctx(payload)))
    _doc(payload, DOC_COMPLIANCE_REPORT)["compliant_count"] += 1
    assert _fired(check_rpt_report_count_ties(_ctx(payload)))


def test_watchlist_must_tie_the_evidence() -> None:
    payload = _payload()
    assert not _fired(check_rpt_watchlist_ties(_ctx(payload)))
    _doc(payload, DOC_RENEWAL_WATCHLIST)["entries"].append(
        {
            "certificate_id": "COI-1001",
            "party_id": "PTY-101",
            "coverage_type": COVERAGE_CGL,
            "expiration_date": "2030-06-01",
            "days_remaining": 243,
        }
    )
    fired = _fired(check_rpt_watchlist_ties(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "party_unique_ids": Status.FAIL,
    "party_type_valid": Status.FAIL,
    "party_coverage_declared": Status.FAIL,
    "party_matrix_defined": Status.FAIL,
    "cert_required_fields": Status.FAIL,
    "cert_policy_no_unique": Status.FAIL,
    "cert_term_runs_forward": Status.FAIL,
    "cert_party_exists": Status.FAIL,
    "cov_coverage_type_valid": Status.FAIL,
    "cov_required_present": Status.FAIL,
    "cov_per_occurrence_meets": Status.FAIL,
    "cov_aggregate_meets": Status.FAIL,
    "cov_no_uninsured_gap": Status.FAIL,
    "end_additional_insured_present": Status.FAIL,
    "end_waiver_of_subrogation_present": Status.FAIL,
    "exp_not_expired": Status.FAIL,
    "exp_renewal_lead_time": Status.FLAG,
    "exp_workers_comp_present": Status.FAIL,
    "rpt_party_compliant_recomputes": Status.FAIL,
    "rpt_report_count_ties": Status.FAIL,
    "rpt_watchlist_ties": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "party", "cert", "cov", "end", "exp", "rpt"}
