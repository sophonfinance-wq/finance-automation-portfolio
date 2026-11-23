"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one cent, one sequence number or one status either
side of the line. A control that fires a cent early is as wrong as one that never
fires, and only a boundary test can tell the two apart.

The cap and the re-derivations carry the most weight. A line billed exactly to
its scheduled value is fully billed and a cent past it is overbilled; a stated
figure equal to its derivation passes and a cent off fails; a pending change
order moves nothing and the same order approved moves everything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sov_engine.billing import CO_APPROVED
from sov_engine.engine import (
    SEVERITY,
    check_cap_not_overbilled,
    check_cmt_revised_rederives,
    check_co_numbering_sequential,
    check_lien_amount_ties,
    check_line_completed_rederives,
    check_line_current_request_rederives,
    check_line_percent_rederives,
    check_ret_rate_known,
    check_ret_rederives,
    check_roll_previously_ties_prior,
    check_sov_foots_to_original,
    check_tax_payment_due_rederives,
)
from sov_engine.generate import (
    CID_CIND,
    CID_KETT,
    CID_MARO,
    PORTFOLIOS,
    baseline,
    rederive,
)
from sov_engine.model import (
    DOC_CHANGE_ORDER_LOG,
    DOC_COMMITMENT_REGISTER,
    DOC_LIEN_RELEASE_REGISTER,
    DOC_PAY_APP_REGISTER,
    DOC_SOV_SCHEDULE,
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


def _commitment(payload: dict, commitment_id: str) -> dict:
    return next(
        c for c in _doc(payload, DOC_COMMITMENT_REGISTER)["commitments"]
        if c["commitment_id"] == commitment_id
    )


def _sov_line(payload: dict, commitment_id: str, line_no: int) -> dict:
    return next(
        r for r in _doc(payload, DOC_SOV_SCHEDULE)["lines"]
        if r["commitment_id"] == commitment_id and r["line_no"] == line_no
    )


def _app(payload: dict, commitment_id: str, app_no: int) -> dict:
    return next(
        a for a in _doc(payload, DOC_PAY_APP_REGISTER)["pay_applications"]
        if a["commitment_id"] == commitment_id and a["app_no"] == app_no
    )


def _app_line(app: dict, line_no: int) -> dict:
    return next(line for line in app["lines"] if line["line_no"] == line_no)


def _release(payload: dict, commitment_id: str, app_no: int) -> dict:
    return next(
        r for r in _doc(payload, DOC_LIEN_RELEASE_REGISTER)["releases"]
        if r["commitment_id"] == commitment_id and r["app_no"] == app_no
    )


def _co(payload: dict, co_id: str) -> dict:
    return next(
        c for c in _doc(payload, DOC_CHANGE_ORDER_LOG)["change_orders"]
        if c["co_id"] == co_id
    )


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


# --------------------------------------------------------------------------- #
# cap_not_overbilled -- fully billed at the cent, overbilled a cent past it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, False), (0, False), (1, True)])
def test_cap_bites_one_cent_past_the_scheduled_value(
    delta: int, should_fail: bool
) -> None:
    """The chain is re-derived after the work moves, so only the cap can fire."""
    payload = _payload()
    scheduled = _sov_line(payload, CID_CIND, 1)["scheduled_value_cents"]
    _app_line(_app(payload, CID_CIND, 1), 1)["work_this_period_cents"] = scheduled + delta
    rederive(payload)
    assert bool(_fired(check_cap_not_overbilled(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# sov_foots_to_original -- the decomposition foots exactly, either direction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_sov_foots_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _sov_line(payload, CID_KETT, 3)["scheduled_value_cents"] += delta
    assert bool(_fired(check_sov_foots_to_original(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# line_completed_rederives -- D+E holds to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_completed_is_exactly_prev_plus_current(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _app_line(_app(payload, CID_KETT, 2), 1)["total_completed_cents"] += delta
    assert bool(_fired(check_line_completed_rederives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# line_current_request_rederives -- the request is a difference, not a fact
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_request_is_exactly_completed_minus_previous(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _app(payload, CID_MARO, 2)["totals"]["current_request_cents"] += delta
    assert bool(_fired(check_line_current_request_rederives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ret_rederives / tax_payment_due_rederives -- the money chain holds exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_retention_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _app(payload, CID_KETT, 1)["totals"]["retention_cents"] += delta
    fired = _fired(check_ret_rederives(_ctx(payload)))
    assert bool(fired) is should_fail


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_payment_due_rederives_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _app(payload, CID_KETT, 1)["totals"]["payment_due_incl_tax_cents"] += delta
    assert bool(_fired(check_tax_payment_due_rederives(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# ret_rate_known -- the menu is 5% or 10%, and off-menu is a FLAG, not a FAIL
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rate, should_flag", [(500, False), (1000, False), (750, True)])
def test_retention_menu(rate: int, should_flag: bool) -> None:
    payload = _payload()
    _commitment(payload, CID_CIND)["retention_rate_bps"] = rate
    fired = _fired(check_ret_rate_known(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# line_percent_rederives -- floored basis points, and a FLAG when they drift
# --------------------------------------------------------------------------- #
def test_percent_drift_is_a_flag_not_a_failure() -> None:
    payload = _payload()
    assert not _fired(check_line_percent_rederives(_ctx(payload)))
    _app_line(_app(payload, CID_KETT, 2), 2)["percent_complete_bps"] += 1
    fired = _fired(check_line_percent_rederives(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


# --------------------------------------------------------------------------- #
# roll_previously_ties_prior -- the chain ties to the cent, and opens at zero
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_roll_forward_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _app(payload, CID_KETT, 2)["totals"]["total_previously_billed_cents"] += delta
    assert bool(_fired(check_roll_previously_ties_prior(_ctx(payload)))) is should_fail


def test_first_app_opens_from_zero() -> None:
    payload = _payload()
    _app(payload, CID_MARO, 1)["totals"]["total_previously_billed_cents"] = 1
    assert _fired(check_roll_previously_ties_prior(_ctx(payload)))


# --------------------------------------------------------------------------- #
# cmt_revised_rederives -- only an approved change order moves the contract
# --------------------------------------------------------------------------- #
def test_pending_change_order_moves_nothing() -> None:
    """Re-pricing a pending order changes no committed cost; approving it does."""
    payload = _payload()
    _co(payload, "CO-2002")["amount_cents"] += 100_000
    assert not _fired(check_cmt_revised_rederives(_ctx(payload)))
    _co(payload, "CO-2002")["status"] = CO_APPROVED
    assert _fired(check_cmt_revised_rederives(_ctx(payload)))


# --------------------------------------------------------------------------- #
# co_numbering_sequential -- #-N with no gap and no repeat
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("number, should_fail", [(2, False), (3, True), (1, True)])
def test_change_orders_number_sequentially(number: int, should_fail: bool) -> None:
    """Renumbering the second order to #-3 leaves a gap; to #-1, a repeat."""
    payload = _payload()
    _co(payload, "CO-2002")["co_number"] = number
    assert bool(_fired(check_co_numbering_sequential(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# lien_amount_ties -- the release is signed for the certified cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_release_ties_the_certified_payment_at_the_cent(
    delta: int, should_fail: bool
) -> None:
    payload = _payload()
    _release(payload, CID_KETT, 2)["amount_cents"] += delta
    assert bool(_fired(check_lien_amount_ties(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "cmt_ids_unique": Status.FAIL,
    "cmt_required_fields": Status.FAIL,
    "cmt_rollup_ties_register": Status.FAIL,
    "cmt_revised_rederives": Status.FAIL,
    "co_commitment_exists": Status.FAIL,
    "co_numbering_sequential": Status.FAIL,
    "co_status_valid": Status.FAIL,
    "co_not_split_to_new_commitment": Status.FAIL,
    "co_commitment_id_format": Status.FAIL,
    "sov_lines_wellformed": Status.FAIL,
    "sov_foots_to_original": Status.FAIL,
    "line_ref_valid": Status.FAIL,
    "line_completed_rederives": Status.FAIL,
    "line_percent_rederives": Status.FLAG,
    "line_header_foots": Status.FAIL,
    "line_current_request_rederives": Status.FAIL,
    "cap_not_overbilled": Status.FAIL,
    "cap_balance_rederives": Status.FAIL,
    "ret_rate_known": Status.FLAG,
    "ret_rederives": Status.FAIL,
    "tax_rederives": Status.FAIL,
    "tax_payment_due_rederives": Status.FAIL,
    "roll_previously_ties_prior": Status.FAIL,
    "roll_apps_sequential": Status.FAIL,
    "port_totals_foot": Status.FAIL,
    "port_revised_identity": Status.FAIL,
    "lien_release_per_app": Status.FAIL,
    "lien_amount_ties": Status.FAIL,
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
        "set", "cmt", "co", "sov", "line", "cap", "ret", "tax", "roll", "port", "lien",
    }
