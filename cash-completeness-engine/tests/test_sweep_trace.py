"""Sweep tracing: closing transfers are parsed into named destinations."""

from __future__ import annotations

from ccengine.reconcile import pre_sweep_balance, trace_sweeps
from tests.conftest import make_account, make_txn


def test_transfer_to_pattern_captures_destination_and_amount():
    acct = make_account(
        "615-001-1133", 0.00, status="closed",
        txns=[
            make_txn("2026-06-01", "Opening balance", 0.00, 52140.25),
            make_txn(
                "2026-06-28", "Transfer to Union National Bank",
                -52140.25, 0.00,
            ),
        ],
    )
    dests = trace_sweeps(acct)
    assert dests == [
        {
            "date": "2026-06-28",
            "counterparty": "Union National Bank",
            "amount": 52140.25,  # positive dollars moved OUT
        }
    ]


def test_wire_to_pattern_is_recognised():
    acct = make_account(
        "424-002-1133", 0.00, status="closed",
        txns=[
            make_txn("2026-06-01", "Opening balance", 0.00, 900.00),
            make_txn("2026-06-15", "Wire to Coastal Mutual", -900.00, 0.00),
        ],
    )
    dests = trace_sweeps(acct)
    assert [d["counterparty"] for d in dests] == ["Coastal Mutual"]


def test_generic_close_phrases_fall_back_to_counterparty_column():
    acct = make_account(
        "424-003-1133", 0.00, status="closed",
        txns=[
            make_txn("2026-06-01", "Opening balance", 0.00, 1200.00),
            make_txn(
                "2026-05-20", "To close account", -700.00, 500.00,
                counterparty="Union National Bank",
            ),
            make_txn("2026-05-21", "Close account", -500.00, 0.00),
        ],
    )
    dests = trace_sweeps(acct)
    assert len(dests) == 2
    assert dests[0]["counterparty"] == "Union National Bank"
    assert dests[1]["counterparty"] == ""  # honest blank, never invented
    assert dests[0]["amount"] == 700.00
    assert dests[1]["amount"] == 500.00


def test_trailing_close_account_clause_is_stripped_from_destination():
    acct = make_account(
        "615-001-1133", 0.00, status="closed",
        txns=[
            make_txn(
                "2026-06-28",
                "Transfer to Union National Bank - to close account",
                -52140.25, 0.00,
            ),
        ],
    )
    assert trace_sweeps(acct)[0]["counterparty"] == "Union National Bank"


def test_inflows_and_ordinary_outflows_are_never_sweeps():
    acct = make_account(
        "424-004-1101", 500.00,
        txns=[
            # Description matches, but the money came IN: not a sweep.
            make_txn("2026-06-10", "Transfer to operating account", 250.00, 750.00),
            # Ordinary outflow, no close-out phrasing: not a sweep.
            make_txn("2026-06-11", "Vendor payment", -250.00, 500.00),
        ],
    )
    assert trace_sweeps(acct) == []
    assert pre_sweep_balance(acct) is None


def test_multiple_sweeps_all_traced_and_sum_to_total_swept():
    acct = make_account(
        "424-005-1133", 0.00, status="closed",
        txns=[
            make_txn("2026-06-01", "Opening balance", 0.00, 1000.00),
            make_txn("2026-06-20", "Transfer to Union National Bank", -600.00, 400.00),
            make_txn("2026-06-21", "Wire to Coastal Mutual", -400.00, 0.00),
        ],
    )
    dests = trace_sweeps(acct)
    assert [d["counterparty"] for d in dests] == [
        "Union National Bank", "Coastal Mutual",
    ]
    assert round(sum(d["amount"] for d in dests), 2) == 1000.00


def test_pre_sweep_balance_reconstructs_the_figure_the_tb_still_carries():
    acct = make_account(
        "424-005-1133", 0.00, status="closed",
        txns=[
            make_txn("2026-06-01", "Opening balance", 0.00, 1000.00),
            make_txn("2026-06-20", "Transfer to Union National Bank", -600.00, 400.00),
            make_txn("2026-06-21", "Wire to Coastal Mutual", -400.00, 0.00),
        ],
    )
    # Balance immediately before the FIRST sweep: 400 - (-600) = 1000.
    assert pre_sweep_balance(acct) == 1000.00
