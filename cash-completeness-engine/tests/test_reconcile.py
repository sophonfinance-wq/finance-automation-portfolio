"""Classification: every register-vs-TB difference lands in exactly one class."""

from __future__ import annotations

from ccengine.models import (
    KIND_STALE_CLOSEOUT,
    KIND_TIMING,
    KIND_UNEXPLAINED,
    KIND_UNMAPPED_SUCCESSOR,
)
from ccengine.reconcile import (
    classify_exceptions,
    flag_placeholder_gls,
    match_population,
)
from tests.conftest import make_account, make_tb_row, make_txn


# ---------------------------------------------------------------------------
# Population matching
# ---------------------------------------------------------------------------


def test_match_population_partitions_everything_and_drops_nothing():
    registers = [
        make_account("615-001-1101", 100.0),
        make_account("424-002-1101", 50.0),
    ]
    tb_rows = [
        make_tb_row("615-001-00-1101", 100.0),  # filler spelling still matches
        make_tb_row("615-001-1101", 25.0),  # duplicate line on the same key
        make_tb_row("424-009-1101", 10.0),  # no register behind it
    ]
    match = match_population(registers, tb_rows)
    assert len(match.matched) == 1
    acct, rows = match.matched[0]
    assert acct.gl_norm == "615-001-1101"
    assert len(rows) == 2  # both TB rows carried, never collapsed
    assert [a.gl_norm for a in match.register_only] == ["424-002-1101"]
    assert [r.gl_norm for r in match.tb_only] == ["424-009-1101"]


# ---------------------------------------------------------------------------
# Class A: live register account the TB cannot see
# ---------------------------------------------------------------------------


def test_live_account_with_no_tb_row_is_class_a():
    acct = make_account(
        "424-002-1101", 84210.55, status="live",
        entity="Harbor 17 Investor LLC",
    )
    exceptions, phantoms = classify_exceptions([acct], [])
    assert phantoms == []
    assert len(exceptions) == 1
    exc = exceptions[0]
    assert exc.kind == KIND_UNMAPPED_SUCCESSOR
    assert exc.gl_norm == "424-002-1101"
    assert exc.register_balance == 84210.55
    assert exc.tb_balance is None


def test_closed_account_absent_from_tb_with_money_left_is_class_d():
    acct = make_account("424-005-1133", 750.00, status="closed")
    exceptions, _ = classify_exceptions([acct], [])
    assert [e.kind for e in exceptions] == [KIND_UNEXPLAINED]


def test_closed_swept_account_absent_from_tb_is_fully_resolved():
    acct = make_account("424-005-1133", 0.00, status="closed")
    exceptions, phantoms = classify_exceptions([acct], [])
    assert exceptions == []
    assert phantoms == []


# ---------------------------------------------------------------------------
# Ties
# ---------------------------------------------------------------------------


def test_register_tying_to_tb_produces_no_exception():
    acct = make_account("615-001-1101", 160000.00)
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("615-001-1101", 160000.00)]
    )
    assert exceptions == []


def test_duplicate_tb_rows_are_summed_before_comparison():
    acct = make_account("615-001-1101", 150.00)
    tb_rows = [
        make_tb_row("615-001-1101", 100.00),
        make_tb_row("615-001-1101", 50.00),
    ]
    exceptions, _ = classify_exceptions([acct], tb_rows)
    assert exceptions == []  # 100 + 50 ties to 150


# ---------------------------------------------------------------------------
# Class B: stale close-out, fully corroborated or not awarded at all
# ---------------------------------------------------------------------------


def _closed_swept_account(gl: str = "615-001-1133"):
    txns = [
        make_txn("2026-06-01", "Opening balance", 0.00, 52140.25),
        make_txn(
            "2026-06-28",
            "Transfer to Union National Bank - to close account",
            -52140.25,
            0.00,
            counterparty="Union National Bank",
        ),
    ]
    return make_account(gl, 0.00, status="closed", txns=txns)


def test_stale_closeout_awarded_when_fully_documented():
    acct = _closed_swept_account()
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("615-001-1133", 52140.25)]
    )
    assert len(exceptions) == 1
    exc = exceptions[0]
    assert exc.kind == KIND_STALE_CLOSEOUT
    assert exc.tb_balance == 52140.25
    assert exc.destinations == [
        {
            "date": "2026-06-28",
            "counterparty": "Union National Bank",
            "amount": 52140.25,
        }
    ]


def test_stale_closeout_not_awarded_when_tb_figure_does_not_tie():
    acct = _closed_swept_account()
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("615-001-1133", 60000.00)]  # not the pre-sweep figure
    )
    assert [e.kind for e in exceptions] == [KIND_UNEXPLAINED]


def test_stale_closeout_not_awarded_when_register_not_swept_to_zero():
    txns = [
        make_txn("2026-06-01", "Opening balance", 0.00, 52140.25),
        make_txn(
            "2026-06-28", "Transfer to Union National Bank", -52000.00, 140.25,
            counterparty="Union National Bank",
        ),
    ]
    acct = make_account("615-001-1133", 140.25, status="closed", txns=txns)
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("615-001-1133", 52140.25)]
    )
    assert [e.kind for e in exceptions] == [KIND_UNEXPLAINED]


def test_stale_closeout_not_awarded_without_traceable_sweep():
    txns = [
        make_txn("2026-06-01", "Opening balance", 0.00, 52140.25),
        make_txn("2026-06-28", "Withdrawal", -52140.25, 0.00),  # no sweep pattern
    ]
    acct = make_account("615-001-1133", 0.00, status="closed", txns=txns)
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("615-001-1133", 52140.25)]
    )
    assert [e.kind for e in exceptions] == [KIND_UNEXPLAINED]


# ---------------------------------------------------------------------------
# Class C: timing, from running balances or an explicit cutoff
# ---------------------------------------------------------------------------


def test_timing_difference_explained_by_running_balances_is_class_c():
    txns = [
        make_txn("2026-06-01", "Opening balance", 0.00, 40000.00),
        make_txn("2026-06-15", "Homeowner deposit", 10000.00, 50000.00),
        make_txn("2026-06-30", "Deposit in transit", 7500.00, 57500.00),
    ]
    acct = make_account("424-003-1101", 57500.00, txns=txns)
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("424-003-1101", 50000.00)]
    )
    assert [e.kind for e in exceptions] == [KIND_TIMING]


def test_timing_with_explicit_cutoff_uses_post_cutoff_transactions():
    txns = [
        make_txn("2026-06-20", "Deposit", 50000.00, 50000.00),
        make_txn("2026-07-02", "Deposit in transit", 7500.00, 57500.00),
    ]
    acct = make_account("424-003-1101", 57500.00, txns=txns)
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("424-003-1101", 50000.00)], cutoff="2026-06-30"
    )
    assert [e.kind for e in exceptions] == [KIND_TIMING]


def test_timing_note_without_cutoff_does_not_claim_post_cutoff():
    # Regression: with no cutoff configured, the explanation comes from the
    # register's own running balances -- the note must NOT assert the items
    # are "post-cutoff" (there is no cutoff to be after). See defect 2a.
    txns = [
        make_txn("2026-06-01", "Opening balance", 0.00, 40000.00),
        make_txn("2026-06-15", "Homeowner deposit", 10000.00, 50000.00),
        make_txn("2026-06-30", "Deposit in transit", 7500.00, 57500.00),
    ]
    acct = make_account("424-003-1101", 57500.00, txns=txns)
    (exc,) = classify_exceptions(
        [acct], [make_tb_row("424-003-1101", 50000.00)]
    )[0]
    assert exc.kind == KIND_TIMING
    assert "post-cutoff" not in exc.note
    assert "no cutoff configured" in exc.note
    assert "in-transit" in exc.note


def test_timing_note_with_cutoff_names_the_cutoff_date():
    # Regression: when a cutoff IS configured, the note references it, so the
    # "post-cutoff" evidence path is honestly described. See defect 2a.
    txns = [
        make_txn("2026-06-20", "Deposit", 50000.00, 50000.00),
        make_txn("2026-07-02", "Deposit in transit", 7500.00, 57500.00),
    ]
    acct = make_account("424-003-1101", 57500.00, txns=txns)
    (exc,) = classify_exceptions(
        [acct], [make_tb_row("424-003-1101", 50000.00)], cutoff="2026-06-30"
    )[0]
    assert exc.kind == KIND_TIMING
    assert "2026-06-30 cutoff" in exc.note


def test_timing_where_tb_equals_opening_balance_is_class_c():
    txns = [make_txn("2026-06-30", "Deposit in transit", 500.00, 10500.00)]
    acct = make_account("424-003-1101", 10500.00, txns=txns)
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("424-003-1101", 10000.00)]
    )
    assert [e.kind for e in exceptions] == [KIND_TIMING]


def test_post_cutoff_activity_that_does_not_sum_is_never_forced_into_timing():
    txns = [
        make_txn("2026-06-20", "Deposit", 50000.00, 50000.00),
        make_txn("2026-07-02", "Deposit in transit", 7500.00, 57500.00),
    ]
    acct = make_account("424-003-1101", 57500.00, txns=txns)
    exceptions, _ = classify_exceptions(
        # TB of 51000: the 7500 post-cutoff item does not explain a 6500 gap.
        [acct], [make_tb_row("424-003-1101", 51000.00)], cutoff="2026-06-30"
    )
    assert [e.kind for e in exceptions] == [KIND_UNEXPLAINED]


# ---------------------------------------------------------------------------
# Class D and phantom rows: nothing is silently dropped
# ---------------------------------------------------------------------------


def test_unexplained_live_difference_is_class_d():
    txns = [
        make_txn("2026-06-01", "Opening balance", 0.00, 10000.00),
        make_txn("2026-06-12", "Management fee received", 2500.00, 12500.00),
    ]
    acct = make_account(
        "424-004-1101", 12500.00, txns=txns,
        entity="Kestrel Capital Partners LLC",
    )
    exceptions, _ = classify_exceptions(
        [acct], [make_tb_row("424-004-1101", 11000.00)]
    )
    assert len(exceptions) == 1
    exc = exceptions[0]
    assert exc.kind == KIND_UNEXPLAINED
    assert exc.register_balance == 12500.00
    assert exc.tb_balance == 11000.00


def test_tb_rows_with_no_register_match_are_returned_as_phantoms():
    acct = make_account("615-001-1101", 100.00)
    tb_rows = [
        make_tb_row("615-001-1101", 100.00),
        make_tb_row("001-001-0000", 1250.00, title="BAL"),
    ]
    exceptions, phantoms = classify_exceptions([acct], tb_rows)
    assert exceptions == []
    assert [r.gl_norm for r in phantoms] == ["001-001-0000"]


def test_exceptions_are_sorted_by_class_then_entity_then_gl():
    registers = [
        make_account("424-004-1101", 12500.00, entity="Kestrel Capital Partners LLC"),
        make_account("424-002-1101", 50.00, entity="Harbor 17 Investor LLC"),
        _closed_swept_account("615-001-1133"),
    ]
    tb_rows = [
        make_tb_row("615-001-1133", 52140.25),
        make_tb_row("424-004-1101", 11000.00),
    ]
    exceptions, _ = classify_exceptions(registers, tb_rows)
    assert [e.kind for e in exceptions] == [
        KIND_UNMAPPED_SUCCESSOR,
        KIND_STALE_CLOSEOUT,
        KIND_UNEXPLAINED,
    ]


# ---------------------------------------------------------------------------
# Placeholder / mis-keyed GL review flag (defect 2c)
# ---------------------------------------------------------------------------


def test_flag_placeholder_gls_surfaces_a_tying_placeholder_account():
    # A register account can tie to the TB perfectly and still be booked
    # against a mis-keyed 001-001-... placeholder key. It stays a clean tie
    # (no A/B/C/D exception) but must be flagged so the key gets a human look.
    placeholder = make_account(
        "001-001-00-1015", 12406.90, entity="Demo Holdings LLC",
    )
    real = make_account("615-001-1101", 160000.00)
    tb_rows = [
        make_tb_row("001-001-1015", 12406.90),  # ties to the cent
        make_tb_row("615-001-1101", 160000.00),
    ]

    exceptions, _ = classify_exceptions([placeholder, real], tb_rows)
    assert exceptions == []  # both tie; placeholder is not an A/B/C/D exception

    flagged = flag_placeholder_gls([placeholder, real])
    assert [a.gl_norm for a in flagged] == ["001-001-1015"]


def test_flag_placeholder_gls_empty_when_every_key_is_well_formed():
    registers = [
        make_account("615-001-1101", 100.00),
        make_account("424-002-1101", 50.00, entity="Harbor 17 Investor LLC"),
    ]
    assert flag_placeholder_gls(registers) == []
