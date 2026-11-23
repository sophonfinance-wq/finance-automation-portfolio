"""What each control actually means, tested at its boundary.

The planted-defect suite proves every control *can* fire. This suite proves each
one fires at the right moment: one day, one cent or one status either side of the
line. A control that fires a cent early is as wrong as one that never fires, and
only a boundary test can tell the two apart.

The date cases carry the most weight here, because this engine is almost entirely
date arithmetic. A check dated on the as-of date is nought days old, not one. An
item sitting exactly on the stale-dating threshold has not crossed it; a day later
it has. The same holds at the dormancy period, where crossing the line moves money
from the entity to a state. Every one of those edges is one day wide, and every
one of them is tested from both sides.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from checkage_engine.aging import age_days, bucket_for, is_dormant, is_stale_dated
from checkage_engine.engine import (
    SEVERITY,
    check_age_bucket_recomputes,
    check_age_outstanding_set_recomputes,
    check_age_stale_dated_flagged,
    check_chk_cleared_pairing,
    check_chk_cleared_ties_issued,
    check_chk_date_not_future,
    check_chk_number_unique_per_account,
    check_esc_jurisdiction_assigned,
    check_esc_set_recomputes,
    check_rpt_bucket_totals_tie,
    check_rpt_outstanding_total_ties,
    check_void_nets_to_zero,
    check_void_not_outstanding,
)
from checkage_engine.generate import (
    AS_OF,
    DORMANCY_DAYS,
    PORTFOLIOS,
    STALE_DATED_DAYS,
    baseline,
    rederive,
)
from checkage_engine.model import (
    DOC_BANK_RECONCILIATION,
    DOC_CHECK_REGISTER,
    DOC_ESCHEATMENT_SCHEDULE,
    DOC_OUTSTANDING_SCHEDULE,
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


def _check(payload: dict, account_id: str, check_number: str) -> dict:
    return next(
        c for c in _doc(payload, DOC_CHECK_REGISTER)["checks"]
        if c["account_id"] == account_id and c["check_number"] == check_number
    )


def _item(payload: dict, account_id: str, check_number: str) -> dict:
    return next(
        r for r in _doc(payload, DOC_OUTSTANDING_SCHEDULE)["items"]
        if r["account_id"] == account_id and r["check_number"] == check_number
    )


def _escheat_items(payload: dict, account_id: str, check_number: str) -> list[dict]:
    return [
        r for r in _doc(payload, DOC_ESCHEATMENT_SCHEDULE)["items"]
        if r["account_id"] == account_id and r["check_number"] == check_number
    ]


def _fired(findings) -> list:
    return [f for f in findings if f.status is not Status.PASS]


def _as_of() -> date:
    return date.fromisoformat(AS_OF)


def _redate(payload: dict, account_id: str, check_number: str, age: int) -> None:
    """Re-date a check to sit exactly ``age`` days before the as-of date."""
    _check(payload, account_id, check_number)["check_date"] = (
        _as_of() - timedelta(days=age)
    ).isoformat()
    rederive(payload)


# --------------------------------------------------------------------------- #
# The kernel's own edges
# --------------------------------------------------------------------------- #
def test_a_check_issued_on_the_as_of_date_is_nought_days_old() -> None:
    """Age counts elapsed days, so the issue date itself is not a day of age."""
    assert age_days(_as_of(), _as_of()) == 0


@pytest.mark.parametrize(
    "age, expected",
    [
        (0, "0-30"), (30, "0-30"), (31, "31-60"), (60, "31-60"),
        (61, "61-90"), (90, "61-90"), (91, "91-180"), (180, "91-180"),
        (181, "181-365"), (365, "181-365"), (366, "366+"), (5000, "366+"),
    ],
)
def test_aging_bands_are_inclusive_of_their_upper_bound(age: int, expected: str) -> None:
    """Each band closes *on* its bound; the next day opens the band above."""
    assert bucket_for(age) == expected


@pytest.mark.parametrize(
    "age, expected", [(STALE_DATED_DAYS - 1, False), (STALE_DATED_DAYS, False), (STALE_DATED_DAYS + 1, True)]
)
def test_stale_dating_needs_the_threshold_passed_not_reached(age: int, expected: bool) -> None:
    assert is_stale_dated(age, STALE_DATED_DAYS) is expected


@pytest.mark.parametrize(
    "age, expected", [(DORMANCY_DAYS - 1, False), (DORMANCY_DAYS, False), (DORMANCY_DAYS + 1, True)]
)
def test_dormancy_needs_the_period_passed_not_reached(age: int, expected: bool) -> None:
    assert is_dormant(age, DORMANCY_DAYS) is expected


# --------------------------------------------------------------------------- #
# chk_date_not_future -- the as-of date itself is allowed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("offset, should_fail", [(0, False), (1, True)])
def test_a_check_dated_on_the_as_of_date_is_allowed(offset: int, should_fail: bool) -> None:
    """A check cut on the as-of date is nought days old; one day later cannot exist."""
    payload = _payload()
    _check(payload, "BNK-100", "CHK-4110")["check_date"] = (
        _as_of() + timedelta(days=offset)
    ).isoformat()
    assert bool(_fired(check_chk_date_not_future(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# chk_cleared_ties_issued -- the reconciliation is exact to the cent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_cleared_ties_issued_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    row = _check(payload, "BNK-100", "CHK-4101")
    row["cleared_amount_cents"] = row["check_amount_cents"] + delta
    assert bool(_fired(check_chk_cleared_ties_issued(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# chk_cleared_pairing -- both halves of a clearing, or neither
# --------------------------------------------------------------------------- #
def test_a_cleared_amount_without_a_cleared_date_is_ambiguous() -> None:
    payload = _payload()
    assert not _fired(check_chk_cleared_pairing(_ctx(payload)))
    _check(payload, "BNK-100", "CHK-4101")["cleared_date"] = None
    assert _fired(check_chk_cleared_pairing(_ctx(payload)))


def test_a_cleared_date_without_a_cleared_amount_is_ambiguous() -> None:
    """The shape that would keep an item on the outstanding schedule forever."""
    payload = _payload()
    _check(payload, "BNK-100", "CHK-4104")["cleared_date"] = "2029-09-20"
    assert _fired(check_chk_cleared_pairing(_ctx(payload)))


# --------------------------------------------------------------------------- #
# chk_number_unique_per_account -- scoped to the account, not the portfolio
# --------------------------------------------------------------------------- #
def test_the_same_number_in_two_accounts_is_not_a_duplicate() -> None:
    """Both baseline accounts open at CHK-4101; the register is still sound."""
    payload = _payload()
    numbers = [c["check_number"] for c in _doc(payload, DOC_CHECK_REGISTER)["checks"]]
    assert len(numbers) != len(set(numbers)), "the fixture must reuse numbers across accounts"
    assert not _fired(check_chk_number_unique_per_account(_ctx(payload)))


def test_the_same_number_twice_in_one_account_is_a_duplicate() -> None:
    payload = _payload()
    register = _doc(payload, DOC_CHECK_REGISTER)
    register["checks"].append(dict(_check(payload, "BNK-100", "CHK-4110")))
    assert _fired(check_chk_number_unique_per_account(_ctx(payload)))


# --------------------------------------------------------------------------- #
# void_ -- a withdrawn check is off the set and netted to zero
# --------------------------------------------------------------------------- #
def test_withdrawn_checks_are_not_outstanding() -> None:
    """Nothing cleared against the three withdrawn checks, and none is outstanding."""
    payload = _payload()
    keys = {
        (r["account_id"], r["check_number"])
        for r in _doc(payload, DOC_OUTSTANDING_SCHEDULE)["items"]
    }
    assert ("BNK-100", "CHK-4109") not in keys
    assert ("BNK-200", "CHK-4107") not in keys
    assert not _fired(check_void_not_outstanding(_ctx(payload)))


def test_a_withdrawn_check_put_back_on_the_schedule_fires() -> None:
    payload = _payload()
    _doc(payload, DOC_OUTSTANDING_SCHEDULE)["items"].append(
        {
            "account_id": "BNK-100",
            "check_number": "CHK-4109",
            "check_date": "2029-07-10",
            "amount_cents": 450_000,
            "age_days": 82,
            "aging_bucket": "61-90",
            "follow_up_required": False,
        }
    )
    assert _fired(check_void_not_outstanding(_ctx(payload)))


@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_a_void_nets_to_zero_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    entry = next(
        e for e in _doc(payload, "void_register")["entries"]
        if e["account_id"] == "BNK-100" and e["check_number"] == "CHK-4109"
    )
    entry["void_amount_cents"] += delta
    assert bool(_fired(check_void_nets_to_zero(_ctx(payload)))) is should_fail


# --------------------------------------------------------------------------- #
# age_ -- the set, the band and the follow-up marker
# --------------------------------------------------------------------------- #
def test_the_outstanding_set_recomputes_on_the_baseline() -> None:
    payload = _payload()
    assert not _fired(check_age_outstanding_set_recomputes(_ctx(payload)))
    _doc(payload, DOC_OUTSTANDING_SCHEDULE)["items"].pop()
    assert _fired(check_age_outstanding_set_recomputes(_ctx(payload)))


def test_a_zero_amount_check_with_a_cleared_date_is_not_outstanding() -> None:
    """Both halves of the outstanding test matter, not just the zero amount."""
    payload = _payload()
    _check(payload, "BNK-100", "CHK-4104")["cleared_date"] = "2029-09-22"
    rederive(payload)
    keys = {
        (r["account_id"], r["check_number"])
        for r in _doc(payload, DOC_OUTSTANDING_SCHEDULE)["items"]
    }
    assert ("BNK-100", "CHK-4104") not in keys


@pytest.mark.parametrize(
    "age, expected", [(30, "0-30"), (31, "31-60"), (180, "91-180"), (181, "181-365")]
)
def test_the_derived_band_moves_on_the_boundary_day(age: int, expected: str) -> None:
    payload = _payload()
    _redate(payload, "BNK-100", "CHK-4104", age)
    assert _item(payload, "BNK-100", "CHK-4104")["aging_bucket"] == expected
    assert not _fired(check_age_bucket_recomputes(_ctx(payload)))


def test_a_typed_band_that_contradicts_the_check_date_fires() -> None:
    payload = _payload()
    assert not _fired(check_age_bucket_recomputes(_ctx(payload)))
    _item(payload, "BNK-100", "CHK-4106")["aging_bucket"] = "61-90"
    assert _fired(check_age_bucket_recomputes(_ctx(payload)))


@pytest.mark.parametrize(
    "age, should_flag", [(STALE_DATED_DAYS, False), (STALE_DATED_DAYS + 1, True)]
)
def test_the_follow_up_marker_turns_on_one_day_past_the_threshold(
    age: int, should_flag: bool
) -> None:
    """With the marker held at False, the control objects only once the item is stale."""
    payload = _payload()
    _redate(payload, "BNK-100", "CHK-4104", age)
    _item(payload, "BNK-100", "CHK-4104")["follow_up_required"] = False
    fired = _fired(check_age_stale_dated_flagged(_ctx(payload)))
    assert bool(fired) is should_flag
    if fired:
        assert fired[0].status is Status.FLAG


def test_a_stale_item_marked_for_follow_up_raises_nothing() -> None:
    """The baseline carries genuinely stale items, correctly marked."""
    payload = _payload()
    assert _item(payload, "BNK-100", "CHK-4107")["follow_up_required"] is True
    assert not _fired(check_age_stale_dated_flagged(_ctx(payload)))


# --------------------------------------------------------------------------- #
# esc_ -- the dormancy line and the jurisdiction it reports to
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "age, should_escheat", [(DORMANCY_DAYS, False), (DORMANCY_DAYS + 1, True)]
)
def test_dormancy_moves_an_item_onto_the_escheatment_schedule(
    age: int, should_escheat: bool
) -> None:
    payload = _payload()
    _redate(payload, "BNK-200", "CHK-4102", age)
    listed = bool(_escheat_items(payload, "BNK-200", "CHK-4102"))
    assert listed is should_escheat
    assert not _fired(check_esc_set_recomputes(_ctx(payload)))


def test_dropping_a_dormant_item_from_the_schedule_fires() -> None:
    payload = _payload()
    assert not _fired(check_esc_set_recomputes(_ctx(payload)))
    _doc(payload, DOC_ESCHEATMENT_SCHEDULE)["items"].pop()
    assert _fired(check_esc_set_recomputes(_ctx(payload)))


def test_an_item_filed_to_the_wrong_jurisdiction_fires() -> None:
    payload = _payload()
    assert not _fired(check_esc_jurisdiction_assigned(_ctx(payload)))
    _doc(payload, DOC_ESCHEATMENT_SCHEDULE)["items"][0]["escheat_jurisdiction"] = (
        "State of Marran and City of Kelder"
    )
    assert _fired(check_esc_jurisdiction_assigned(_ctx(payload)))


def test_both_declared_jurisdictions_are_represented() -> None:
    """The baseline escheats out of both accounts, so neither mapping is untested."""
    payload = _payload()
    named = {
        r["escheat_jurisdiction"]
        for r in _doc(payload, DOC_ESCHEATMENT_SCHEDULE)["items"]
    }
    assert named == {"State of Marran", "City of Kelder"}


# --------------------------------------------------------------------------- #
# rpt_ -- the reconciliation ties the evidence, not the other way round
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delta, should_fail", [(-1, True), (0, False), (1, True)])
def test_the_outstanding_line_ties_at_the_cent(delta: int, should_fail: bool) -> None:
    payload = _payload()
    _doc(payload, DOC_BANK_RECONCILIATION)["outstanding_checks_cents"] += delta
    assert bool(_fired(check_rpt_outstanding_total_ties(_ctx(payload)))) is should_fail


def test_the_outstanding_count_ties_as_well_as_the_amount() -> None:
    payload = _payload()
    _doc(payload, DOC_BANK_RECONCILIATION)["outstanding_count"] += 1
    assert _fired(check_rpt_outstanding_total_ties(_ctx(payload)))


def test_the_outstanding_line_is_tied_to_the_register_not_the_schedule() -> None:
    """Deleting a schedule row leaves the reconciliation tied; the register rules."""
    payload = _payload()
    _doc(payload, DOC_OUTSTANDING_SCHEDULE)["items"].pop()
    assert not _fired(check_rpt_outstanding_total_ties(_ctx(payload)))


def test_bucket_subtotals_tie_the_rederived_bands() -> None:
    payload = _payload()
    assert not _fired(check_rpt_bucket_totals_tie(_ctx(payload)))
    _doc(payload, DOC_BANK_RECONCILIATION)["bucket_totals"][1]["amount_cents"] += 1
    fired = _fired(check_rpt_bucket_totals_tie(_ctx(payload)))
    assert fired
    assert fired[0].status is Status.FLAG


def test_every_aging_band_is_reported_even_when_empty() -> None:
    """A band that empties out shows as a zero, never as an absence."""
    payload = _payload()
    labels = [r["bucket"] for r in _doc(payload, DOC_BANK_RECONCILIATION)["bucket_totals"]]
    assert labels == ["0-30", "31-60", "61-90", "91-180", "181-365", "366+"]


# --------------------------------------------------------------------------- #
# Severity design table
# --------------------------------------------------------------------------- #
DESIGNED_SEVERITY = {
    "set_complete": Status.FAIL,
    "acct_unique_ids": Status.FAIL,
    "acct_jurisdiction_declared": Status.FAIL,
    "chk_required_fields": Status.FAIL,
    "chk_number_unique_per_account": Status.FAIL,
    "chk_account_exists": Status.FAIL,
    "chk_type_valid": Status.FAIL,
    "chk_date_not_future": Status.FAIL,
    "chk_cleared_pairing": Status.FAIL,
    "chk_cleared_ties_issued": Status.FAIL,
    "void_disposition_valid": Status.FAIL,
    "void_not_outstanding": Status.FAIL,
    "void_nets_to_zero": Status.FAIL,
    "age_outstanding_set_recomputes": Status.FAIL,
    "age_bucket_recomputes": Status.FAIL,
    "age_stale_dated_flagged": Status.FLAG,
    "esc_set_recomputes": Status.FAIL,
    "esc_jurisdiction_assigned": Status.FAIL,
    "rpt_outstanding_total_ties": Status.FAIL,
    "rpt_bucket_totals_tie": Status.FLAG,
}


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_observed_severity_matches_the_design_table(rule_id: str, reports) -> None:
    """``reports`` is requested so the whole registry has executed first."""
    assert SEVERITY[rule_id] is DESIGNED_SEVERITY[rule_id]


def test_design_table_covers_the_whole_registry(reports) -> None:
    assert set(SEVERITY) == set(DESIGNED_SEVERITY)


@pytest.mark.parametrize("rule_id", sorted(DESIGNED_SEVERITY))
def test_rule_id_prefix_matches_its_family(rule_id: str) -> None:
    assert rule_id.split("_")[0] in {"set", "acct", "chk", "void", "age", "esc", "rpt"}
