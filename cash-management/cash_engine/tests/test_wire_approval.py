"""Controls for the fictional validation-only wire dual-approval bridge."""

from dataclasses import replace

import pytest

from cash_engine.wire_approval import (
    WireRequest,
    WireApprovalValidator,
    demo_wires,
)

PERIOD = "2026-06"


def run(wires=None):
    return WireApprovalValidator(
        PERIOD, demo_wires() if wires is None else wires
    ).run()


def codes(result):
    return {finding.code for finding in result.findings}


def test_clean_set_passes_and_stays_validation_only():
    result = run()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.wire_count == 3
    assert result.approved_count == 1
    assert result.scheduled_count == 1
    assert result.pending_count == 1
    assert result.blocked_count == 0
    assert "manual release to the bank" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


def test_demo_wires_carry_three_distinct_names_each():
    for wire in demo_wires():
        names = [wire.initiator, wire.first_approver]
        if wire.second_approver:
            names.append(wire.second_approver)
        folded = [name.casefold() for name in names]
        assert len(folded) == len(set(folded))
        # The initiator is always distinct from the first approver.
        assert wire.initiator.casefold() != wire.first_approver.casefold()


@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_period_must_be_canonical(period):
    with pytest.raises(ValueError, match="period must be canonical YYYY-MM"):
        WireApprovalValidator(period, demo_wires())


@pytest.mark.parametrize("bad_id", ["", "   ", " WIRE-1 ", "\tWIRE-1"])
def test_wire_id_must_be_clean(bad_id):
    recs = demo_wires()
    changed = (replace(recs[0], wire_id=bad_id),) + recs[1:]
    assert "WIRE_ID_INVALID" in codes(run(changed))


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("entity", " Cedar Demo LLC", "ENTITY_INVALID"),
        ("entity", "", "ENTITY_INVALID"),
        ("beneficiary", "  ", "BENEFICIARY_INVALID"),
        ("initiator", "Dana Rivera ", "INITIATOR_INVALID"),
        ("first_approver", "", "FIRST_APPROVER_INVALID"),
        ("second_approver", " Grace Okafor", "SECOND_APPROVER_INVALID"),
        ("second_approver", "   ", "SECOND_APPROVER_INVALID"),
    ],
)
def test_semantic_identifiers_are_strict(field, value, expected):
    recs = demo_wires()
    changed = (replace(recs[0], **{field: value}),) + recs[1:]
    assert expected in codes(run(changed))


def test_second_approver_blank_is_allowed_for_pending():
    result = run()
    pending = demo_wires()[2]
    assert pending.second_approver == ""
    assert "SECOND_APPROVER_INVALID" not in codes(result)
    assert "MISSING_SECONDARY_APPROVAL" not in codes(result)


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_amounts_are_rejected_without_coercion(value):
    recs = demo_wires()
    changed = (replace(recs[0], amount_cents=value),) + recs[1:]
    assert "AMOUNT_INVALID" in codes(run(changed))


@pytest.mark.parametrize("value", [0, -1, -4_500_000])
def test_amount_must_be_strictly_positive(value):
    recs = demo_wires()
    changed = (replace(recs[0], amount_cents=value),) + recs[1:]
    result = run(changed)
    assert "AMOUNT_NOT_POSITIVE" in codes(result)
    assert "AMOUNT_INVALID" not in codes(result)


@pytest.mark.parametrize("status", ["", "released", "Approved", "pending", "posted"])
def test_status_must_be_recognized(status):
    recs = demo_wires()
    changed = (replace(recs[0], status=status),) + recs[1:]
    assert "STATUS_INVALID" in codes(run(changed))


@pytest.mark.parametrize(
    "value", ["2026-6-10", "06-10-2026", "2026-13-01", "2026-02-30", " 2026-06-10", "", "not-a-date"]
)
def test_request_date_must_be_valid_iso(value):
    recs = demo_wires()
    changed = (replace(recs[0], request_date=value),) + recs[1:]
    assert "REQUEST_DATE_INVALID" in codes(run(changed))


@pytest.mark.parametrize("value", ["2026-13-01", "2026-06-31", "2026/06/15", "soon"])
def test_scheduled_date_must_be_blank_or_valid_iso(value):
    recs = demo_wires()
    changed = recs[:1] + (replace(recs[1], scheduled_date=value),) + recs[2:]
    assert "SCHEDULED_DATE_INVALID" in codes(run(changed))


def test_approved_wire_missing_second_approver_is_blocked():
    recs = demo_wires()
    changed = (replace(recs[0], second_approver=""),) + recs[1:]
    result = run(changed)
    assert "MISSING_SECONDARY_APPROVAL" in codes(result)
    assert result.verdict == "NEEDS REVIEW"
    assert result.journal_entries == ()


def test_scheduled_wire_missing_second_approver_is_blocked():
    recs = demo_wires()
    changed = recs[:1] + (replace(recs[1], second_approver=""),) + recs[2:]
    assert "MISSING_SECONDARY_APPROVAL" in codes(run(changed))


@pytest.mark.parametrize("field", ["first_approver", "second_approver"])
def test_self_approval_when_an_approver_is_the_initiator(field):
    recs = demo_wires()
    changed = (replace(recs[0], **{field: recs[0].initiator}),) + recs[1:]
    assert "SELF_APPROVAL" in codes(run(changed))


def test_self_approval_is_case_insensitive():
    recs = demo_wires()
    changed = (replace(recs[0], first_approver=recs[0].initiator.upper()),) + recs[1:]
    assert "SELF_APPROVAL" in codes(run(changed))


def test_duplicate_approver_when_both_approvers_match():
    recs = demo_wires()
    changed = (replace(recs[0], second_approver=recs[0].first_approver),) + recs[1:]
    result = run(changed)
    assert "DUPLICATE_APPROVER" in codes(result)
    assert "SELF_APPROVAL" not in codes(result)


def test_duplicate_approver_is_case_insensitive():
    recs = demo_wires()
    changed = (replace(recs[0], second_approver=recs[0].first_approver.upper()),) + recs[1:]
    assert "DUPLICATE_APPROVER" in codes(run(changed))


def test_scheduled_date_before_request_is_blocked():
    recs = demo_wires()
    changed = recs[:1] + (replace(recs[1], scheduled_date="2026-06-11"),) + recs[2:]
    assert "SCHEDULED_DATE_BEFORE_REQUEST" in codes(run(changed))


def test_scheduled_wire_without_scheduled_date_is_blocked():
    recs = demo_wires()
    changed = recs[:1] + (replace(recs[1], scheduled_date=""),) + recs[2:]
    result = run(changed)
    assert "SCHEDULED_DATE_MISSING" in codes(result)
    assert "SCHEDULED_DATE_BEFORE_REQUEST" not in codes(result)


def test_scheduled_date_equal_to_request_is_allowed():
    recs = demo_wires()
    changed = recs[:1] + (replace(recs[1], scheduled_date=recs[1].request_date),) + recs[2:]
    result = run(changed)
    assert "SCHEDULED_DATE_BEFORE_REQUEST" not in codes(result)
    assert result.mechanical_clean


def test_pending_wire_must_not_be_scheduled():
    recs = demo_wires()
    changed = recs[:2] + (replace(recs[2], scheduled_date="2026-06-20"),)
    assert "PENDING_WIRE_SCHEDULED" in codes(run(changed))


def test_duplicate_wire_id_is_blocked_case_insensitively():
    recs = demo_wires()
    changed = (recs[0], replace(recs[1], wire_id=recs[0].wire_id.lower()), recs[2])
    result = run(changed)
    assert "WIRE_ID_DUPLICATE" in codes(result)


def test_blocked_count_tracks_wires_with_a_breach():
    recs = demo_wires()
    changed = (replace(recs[0], second_approver=recs[0].first_approver),) + recs[1:]
    result = run(changed)
    assert result.blocked_count == 1
    assert result.approved_count == 1
    assert result.scheduled_count == 1
    assert result.pending_count == 1


def test_status_counts_ignore_unrecognized_status():
    recs = demo_wires()
    changed = (replace(recs[0], status="posted"),) + recs[1:]
    result = run(changed)
    assert result.approved_count == 0
    assert result.scheduled_count == 1
    assert result.pending_count == 1


def test_empty_set_is_not_a_clean_noop():
    result = run(())
    assert "WIRE_SET_EMPTY" in codes(result)
    assert result.verdict == "NEEDS REVIEW"
    assert result.wire_count == 0


def test_validator_does_not_mutate_input_sequence():
    wires = list(demo_wires())
    before = tuple(wires)
    run(wires)
    assert tuple(wires) == before
