"""JE discipline: book only what the evidence documents; never invent offsets."""

from __future__ import annotations

import pytest

from ccengine.journal import (
    STATUS_NEEDS_JUDGMENT,
    STATUS_NO_ENTRY,
    STATUS_READY,
    draft_entries,
)
from ccengine.models import ExceptionItem, TBRow


def _stale_exception(tb=52140.25, register=0.0, destinations=None):
    return ExceptionItem(
        kind="B_STALE_CLOSEOUT",
        gl_norm="615-001-1133",
        entity="Juniper 42 Development LLC",
        register_balance=register,
        tb_balance=tb,
        destinations=(
            destinations
            if destinations is not None
            else [
                {
                    "date": "2026-06-28",
                    "counterparty": "Union National Bank",
                    "amount": 52140.25,
                }
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Ready drafts: fully documented, balanced to the cent
# ---------------------------------------------------------------------------


def test_fully_documented_stale_closeout_is_ready_and_balances():
    (draft,) = draft_entries([_stale_exception()])
    assert draft.ref == "JE-001"
    assert draft.status == STATUS_READY
    assert draft.question == ""
    assert len(draft.lines) == 2  # one traced destination + the stale GL
    assert draft.total_debits == draft.total_credits == 52140.25
    # The credit clears the stale GL; the debit follows the traced sweep.
    assert any("615-001-1133" in l["account"] and l["credit"] for l in draft.lines)
    assert any(
        "Union National Bank" in l["account"] and l["debit"] for l in draft.lines
    )


def test_multi_destination_draft_balances_to_the_cent():
    destinations = [
        {"date": "2026-06-20", "counterparty": "Union National Bank", "amount": 33.34},
        {"date": "2026-06-21", "counterparty": "Coastal Mutual", "amount": 33.33},
        {"date": "2026-06-22", "counterparty": "Union National Bank", "amount": 33.33},
    ]
    (draft,) = draft_entries(
        [_stale_exception(tb=100.00, destinations=destinations)]
    )
    assert draft.status == STATUS_READY
    assert len(draft.lines) == 4
    assert abs(draft.total_debits - draft.total_credits) <= 0.005
    assert draft.total_credits == 100.00


def test_negative_stale_balance_flips_direction_and_still_balances():
    destinations = [
        {"date": "2026-06-28", "counterparty": "Union National Bank", "amount": 500.00}
    ]
    (draft,) = draft_entries(
        [_stale_exception(tb=-500.00, destinations=destinations)]
    )
    assert draft.status == STATUS_READY
    assert draft.total_debits == draft.total_credits == 500.00
    assert any("615-001-1133" in l["account"] and l["debit"] for l in draft.lines)


# ---------------------------------------------------------------------------
# Never invent an offset
# ---------------------------------------------------------------------------


def test_untraced_closeout_asks_instead_of_guessing():
    (draft,) = draft_entries([_stale_exception(destinations=[])])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []  # no guessed lines, ever
    assert "no sweep destinations" in draft.question


def test_partial_trace_names_the_exact_shortfall_and_books_nothing():
    destinations = [
        {"date": "2026-06-28", "counterparty": "Union National Bank", "amount": 90.00}
    ]
    (draft,) = draft_entries(
        [_stale_exception(tb=100.00, destinations=destinations)]
    )
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []
    assert "10.00" in draft.question  # the undocumented remainder, named


def test_closeout_with_money_still_at_the_bank_is_not_ready():
    (draft,) = draft_entries([_stale_exception(register=140.25)])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []


def test_closeout_with_missing_register_balance_is_not_ready():
    # Regression (defect 2b): a Class B draft whose register_balance is None
    # (e.g. a dict-serialized exception that omits it) must NOT be booked as
    # 'ready'. A missing balance is UNKNOWN, not confirmed-swept-to-zero, so
    # it must ask a question instead of coercing the balance to 0.0.
    exc = {
        "kind": "B_STALE_CLOSEOUT",
        "gl_norm": "615-001-1133",
        "entity": "Juniper 42 Development LLC",
        "register_balance": None,  # unknown, not zero
        "tb_balance": 52140.25,
        "destinations": [
            {
                "date": "2026-06-28",
                "counterparty": "Union National Bank",
                "amount": 52140.25,
            }
        ],
    }
    (draft,) = draft_entries([exc])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []  # never guessed lines
    assert "register balance is missing" in draft.question


def test_closeout_with_register_balance_key_absent_is_not_ready():
    # Same defect, via a dict that omits the register_balance key entirely.
    exc = {
        "kind": "B_STALE_CLOSEOUT",
        "gl_norm": "615-001-1133",
        "entity": "Juniper 42 Development LLC",
        "tb_balance": 52140.25,
        "destinations": [
            {
                "date": "2026-06-28",
                "counterparty": "Union National Bank",
                "amount": 52140.25,
            }
        ],
    }
    (draft,) = draft_entries([exc])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []


def test_missing_tb_figure_is_not_ready():
    (draft,) = draft_entries([_stale_exception(tb=None)])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []
    assert "TB balance is missing" in draft.question


def test_unparseable_destination_amount_is_not_ready():
    destinations = [{"date": "2026-06-28", "counterparty": "X", "amount": "n/a"}]
    (draft,) = draft_entries(
        [_stale_exception(tb=100.00, destinations=destinations)]
    )
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []


def test_unmapped_successor_carries_the_precise_question():
    exc = ExceptionItem(
        kind="A_UNMAPPED_SUCCESSOR",
        gl_norm="424-002-1101",
        entity="Harbor 17 Investor LLC",
        register_balance=84210.55,
    )
    (draft,) = draft_entries([exc])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []
    assert "424-002-1101" in draft.question
    assert "84,210.55" in draft.question


def test_unexplained_difference_is_never_plugged():
    exc = ExceptionItem(
        kind="D_UNEXPLAINED",
        gl_norm="424-004-1101",
        entity="Kestrel Capital Partners LLC",
        register_balance=12500.00,
        tb_balance=11000.00,
    )
    (draft,) = draft_entries([exc])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert draft.lines == []
    assert "1,500.00" in draft.question  # the unexplained difference, named


# ---------------------------------------------------------------------------
# no_entry decisions
# ---------------------------------------------------------------------------


def test_timing_difference_gets_no_entry():
    exc = ExceptionItem(
        kind="C_TIMING",
        gl_norm="424-003-1101",
        entity="Bluffside 9 Townhomes LLC",
        register_balance=57500.00,
        tb_balance=50000.00,
    )
    (draft,) = draft_entries([exc])
    assert draft.status == STATUS_NO_ENTRY
    assert draft.lines == []


def test_phantom_tb_row_gets_no_entry_retire_the_line():
    row = TBRow(
        source_file="trial_balance.csv",
        sheet="TB-JUN",
        gl_raw="001-001-0000",
        gl_norm="001-001-0000",
        title="BAL",
        balance=1250.00,
    )
    (draft,) = draft_entries([], phantom_rows=[row])
    assert draft.status == STATUS_NO_ENTRY
    assert draft.lines == []
    assert "Retire the line" in draft.question
    assert "001-001-0000" in draft.question


# ---------------------------------------------------------------------------
# Structural guarantees
# ---------------------------------------------------------------------------


def test_refs_are_sequential_and_phantoms_come_last():
    exceptions = [
        _stale_exception(),
        ExceptionItem(
            kind="C_TIMING", gl_norm="424-003-1101",
            entity="Bluffside 9 Townhomes LLC",
            register_balance=57500.00, tb_balance=50000.00,
        ),
    ]
    row = TBRow(
        source_file="trial_balance.csv", sheet="TB-JUN",
        gl_raw="001-001-0000", gl_norm="001-001-0000",
        title="BAL", balance=1250.00,
    )
    drafts = draft_entries(exceptions, phantom_rows=[row])
    assert [d.ref for d in drafts] == ["JE-001", "JE-002", "JE-003"]
    assert drafts[-1].status == STATUS_NO_ENTRY
    assert "Retire the line" in drafts[-1].question


def test_dict_serialized_exceptions_are_accepted():
    exc = {
        "kind": "B_STALE_CLOSEOUT",
        "gl_norm": "615-001-1133",
        "entity": "Juniper 42 Development LLC",
        "register_balance": 0.0,
        "tb_balance": 52140.25,
        "destinations": [
            {
                "date": "2026-06-28",
                "counterparty": "Union National Bank",
                "amount": 52140.25,
            }
        ],
    }
    (draft,) = draft_entries([exc])
    assert draft.status == STATUS_READY
    assert draft.total_debits == draft.total_credits == 52140.25


def test_unknown_kind_is_surfaced_never_dropped():
    exc = {"kind": "X_MYSTERY", "gl_norm": "424-009-1101", "entity": ""}
    (draft,) = draft_entries([exc])
    assert draft.status == STATUS_NEEDS_JUDGMENT
    assert "X_MYSTERY" in draft.question


def test_every_line_bearing_draft_balances_to_the_cent():
    drafts = draft_entries(
        [
            _stale_exception(),
            _stale_exception(
                tb=100.00,
                destinations=[
                    {"date": "2026-06-20", "counterparty": "A", "amount": 66.67},
                    {"date": "2026-06-21", "counterparty": "B", "amount": 33.33},
                ],
            ),
        ]
    )
    for draft in drafts:
        if draft.lines:
            assert abs(draft.total_debits - draft.total_credits) <= 0.005


def test_invalid_status_is_rejected_at_construction():
    from ccengine.journal import JEDraft

    with pytest.raises(ValueError):
        JEDraft(ref="JE-999", entity="Demo Holdings LLC", status="maybe")
