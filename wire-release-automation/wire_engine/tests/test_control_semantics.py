"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The authority-limit, funding and duplicate-window cases carry the most weight. An
amount met to the cent must pass and a cent over must fail; a wire dated at the
edge of the duplicate window is inside it and a day past the edge is not; an
authorization dated on the initiation date is in order and a day before is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wire_engine.engine import (
    SEVERITY,
    check_aba_check_digit_valid,
    check_dup_not_already_posted,
    check_fund_sufficient_balance,
    check_ben_off_template_review,
    check_rpt_release_flag_recomputes,
    check_rpt_report_count_ties,
    check_sig_within_authority_limit,
    check_sod_auth_not_before_init,
)
from wire_engine.generate import ENTITIES, baseline
from wire_engine.model import (
    DOC_ACCOUNT_REGISTER,
    DOC_RELEASE_REPORT,
    DOC_RELEASE_SUMMARY,
    DOC_WIRE_REGISTER,
    STAGE_SCHEDULED,
    Context,
    Status,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _payload() -> dict:
    return baseline(ENTITIES[0])


def _ctx(payload: dict) -> Context:
    return Context(path=Path("in-memory.json"), data=payload)


def _doc(payload: dict, doc_type: str) -> dict:
    return next(d for d in payload["documents"] if d["doc_type"] == doc_type)


def _wire(payload: dict, wire_id: str) -> dict:
    return next(
        w for w in _doc(payload, DOC_WIRE_REGISTER)["wires"]
        if w["wire_id"] == wire_id
    )


def _account(payload: dict, account_id: str) -> dict:
    return next(
        a for a in _doc(payload, DOC_ACCOUNT_REGISTER)["accounts"]
        if a["account_id"] == account_id
    )


def _summary_row(payload: dict, wire_id: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_RELEASE_SUMMARY)["wires"]
        if r["wire_id"] == wire_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# sig_within_authority_limit -- met at the limit, not a cent over
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_authority_limit_at_the_cent(delta: int, should_fail: bool) -> None:
    """W-1005 is authorized by SGN-02, whose limit on ACCT-100 is 3,000,000.00."""
    payload = _payload()
    _wire(payload, "W-1005")["amount_cents"] = 3_000_000_00 + delta
    assert bool(_fired(check_sig_within_authority_limit(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# fund_sufficient_balance -- met at the balance, not a cent over
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_funding_balance_at_the_cent(delta: int, should_fail: bool) -> None:
    """ACCT-100 carries 5,000,000.00 available; W-1005 draws on it."""
    payload = _payload()
    _wire(payload, "W-1005")["amount_cents"] = 5_000_000_00 + delta
    assert bool(_fired(check_fund_sufficient_balance(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# sod_auth_not_before_init -- authorized on the initiation date, not before
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "authorized, should_fail",
    [("2030-03-08", True), ("2030-03-09", False), ("2030-03-10", False)],
)
def test_authorization_not_before_initiation(authorized: str, should_fail: bool) -> None:
    """W-1004 is initiated 2030-03-09; authorizing it a day earlier is out of order."""
    payload = _payload()
    _wire(payload, "W-1004")["authorized_date"] = authorized
    assert bool(_fired(check_sod_auth_not_before_init(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# aba_check_digit_valid -- the mod-10 checksum, one digit either side
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "aba, should_fail",
    [("975000054", False), ("975000055", True), ("111111111", True)],
)
def test_aba_check_digit_boundary(aba: str, should_fail: bool) -> None:
    """W-1005 carries 975000054, which passes; a flipped last digit does not."""
    payload = _payload()
    _wire(payload, "W-1005")["receiving_aba"] = aba
    assert bool(_fired(check_aba_check_digit_valid(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# dup_not_already_posted -- the window closes at exactly window_days out
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value_date, should_fail",
    [("2030-03-08", True), ("2030-03-09", False)],
)
def test_duplicate_window_edge(value_date: str, should_fail: bool) -> None:
    """P-9001 posted 2030-03-03 for 1,200,000.00 to 4471180022. A scheduled wire of
    the same beneficiary and amount inside the 5-day window is a duplicate; one
    outside it is not."""
    payload = _payload()
    dupe = _wire(payload, "W-1002")
    dupe["beneficiary_account"] = "4471180022"
    dupe["amount_cents"] = 1_200_000_00
    dupe["value_date"] = value_date
    assert bool(_fired(check_dup_not_already_posted(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ben_off_template_review -- an off-template beneficiary is a FLAG
# --------------------------------------------------------------------------- #
def test_off_template_beneficiary_flags_for_review() -> None:
    payload = _payload()
    assert not _fired(check_ben_off_template_review(_ctx(payload)))
    wire = _wire(payload, "W-1005")
    wire["on_template"] = False
    wire["callback_completed"] = True
    fired = _fired(check_ben_off_template_review(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# rpt_ -- the rollup recomputes from the evidence, not the other way round
# --------------------------------------------------------------------------- #
def test_release_flag_must_recompute() -> None:
    """A stated flag that contradicts the evidence fails; leaving it does not."""
    payload = _payload()
    assert not _fired(check_rpt_release_flag_recomputes(_ctx(payload)))
    _summary_row(payload, "W-1005")["releasable"] = False
    assert _fired(check_rpt_release_flag_recomputes(_ctx(payload)))


def test_report_count_must_tie_the_summary() -> None:
    payload = _payload()
    assert not _fired(check_rpt_report_count_ties(_ctx(payload)))
    _doc(payload, DOC_RELEASE_REPORT)["releasable_count"] += 1
    assert _fired(check_rpt_report_count_ties(_ctx(payload)))


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "sod_two_distinct_signers": Status.FAIL,
    "sod_dual_auth_complete": Status.FAIL,
    "sod_auth_not_before_init": Status.FAIL,
    "sig_initiator_authorized": Status.FAIL,
    "sig_authorizer_authorized": Status.FAIL,
    "sig_within_authority_limit": Status.FAIL,
    "ben_template_exists": Status.FAIL,
    "ben_triplet_matches_template": Status.FAIL,
    "ben_new_account_callback": Status.FAIL,
    "ben_off_template_review": Status.FLAG,
    "aba_classification_fields": Status.FAIL,
    "aba_check_digit_valid": Status.FAIL,
    "aba_resolves_to_bank_name": Status.FAIL,
    "fund_account_exists": Status.FAIL,
    "fund_sufficient_balance": Status.FAIL,
    "dup_wire_ids_unique": Status.FAIL,
    "dup_not_already_posted": Status.FAIL,
    "flow_stage_valid": Status.FAIL,
    "flow_posted_has_approval": Status.FAIL,
    "flow_posted_ref_ties": Status.FAIL,
    "rpt_release_flag_recomputes": Status.FAIL,
    "rpt_report_count_ties": Status.FAIL,
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
        "set", "sod", "sig", "ben", "aba", "fund", "dup", "flow", "rpt"
    }
