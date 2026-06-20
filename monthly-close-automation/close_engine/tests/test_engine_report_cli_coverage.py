"""Additional coverage for the engine, report writers, and CLI.

Covers: the engine's recurring-entry computations and intercompany routing,
the CloseResult/TieResult/Schedule dataclasses, per-entity self-balance of
every posted entry across multiple periods/seeds, the JSON/markdown writers
and their structural invariants, and the CLI exit-code contract and period
validation.
"""

from __future__ import annotations

import json

import pytest

from close_engine import cli, money, report
from close_engine.engine import (
    CloseEngine,
    CloseResult,
    Schedule,
    ScheduleRow,
    TieResult,
)
from close_engine.generate import Note, generate_dataset


def _run(period: str = "2026-03", seed: int = 2026) -> CloseResult:
    return CloseEngine(generate_dataset(period, seed=seed)).run()


# --------------------------------------------------------------------------- #
# TieResult / Schedule / ScheduleRow dataclasses
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "expected, actual, ties, variance",
    [
        (100, 100, True, 0),
        (100, 90, False, 10),
        (90, 100, False, -10),
        (0, 0, True, 0),
    ],
)
def test_tie_result_properties(expected, actual, ties, variance) -> None:
    t = TieResult("sched", "1400", expected, actual)
    assert t.ties is ties
    assert t.variance_cents == variance


def test_schedule_defaults() -> None:
    sched = Schedule("Prepaid", "prepaid_amortization")
    assert sched.rows == []
    assert sched.tie_account is None
    assert sched.tie_expected_cents is None


def test_schedule_row_holds_fields() -> None:
    row = ScheduleRow("PP-01", {"entity": "DH", "monthly": "1,000.00"})
    assert row.key == "PP-01"
    assert row.fields["entity"] == "DH"


# --------------------------------------------------------------------------- #
# CloseResult derived flags
# --------------------------------------------------------------------------- #


def test_close_result_clean_on_default_run() -> None:
    result = _run()
    assert result.all_balanced is True
    assert result.all_tie is True
    assert result.refused == []
    assert result.clean is True


def test_close_result_has_one_schedule_per_category() -> None:
    result = _run()
    categories = [s.category for s in result.schedules]
    assert categories == [
        "prepaid_amortization",
        "depreciation",
        "deferred_rent_cam",
        "mgmt_fee_accrual",
        "note_interest",
        "gna_allocation",
    ]


def test_close_result_register_categories() -> None:
    result = _run()
    cats = [je.category for je in result.register]
    assert cats == [
        "prepaid_amortization",
        "depreciation",
        "deferred_rent_cam",
        "mgmt_fee_accrual",
        "note_interest",
        "gna_allocation",
    ]


# --------------------------------------------------------------------------- #
# Every posted entry self-balances per entity across periods and seeds
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period", ["2026-01", "2026-03", "2026-06", "2026-12"])
def test_every_entry_self_balances_each_period(period) -> None:
    result = _run(period)
    assert result.register
    for je in result.register:
        assert je.is_balanced
        for entity, diff in je.balances_per_entity().items():
            assert diff == 0


@pytest.mark.parametrize("seed", [1, 2026, 99, 12345])
def test_trial_balance_in_balance_across_seeds(seed) -> None:
    result = _run(seed=seed)
    debits, credits = result.ledger.total_debits_credits()
    assert debits == credits


@pytest.mark.parametrize("period", ["2026-02", "2026-05", "2026-09"])
def test_close_is_clean_across_periods(period) -> None:
    assert _run(period).clean


# --------------------------------------------------------------------------- #
# Recurring-entry math via internal helpers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "principal, rate_bps, expected_cents",
    [
        (500000, 600, 250000),  # 500k @ 6% -> 2,500/mo
        (250000, 450, 93750),  # 250k @ 4.5% -> 937.50/mo
        (120000, 1200, 120000),  # 120k @ 12% -> 1,200/mo
        (100, 1, 0),  # tiny accrual rounds to 0
    ],
)
def test_monthly_interest_amounts(principal, rate_bps, expected_cents) -> None:
    eng = CloseEngine(generate_dataset("2026-03"))
    note = Note("N", "MF", "BW", money.to_cents(principal), rate_bps)
    assert eng._monthly_interest(note) == expected_cents


def test_note_interest_je_self_balances_per_entity() -> None:
    result = _run()
    ni = next(je for je in result.register if je.category == "note_interest")
    for entity, diff in ni.balances_per_entity().items():
        assert diff == 0


def test_prepaid_je_credits_only_prepaid_asset() -> None:
    result = _run()
    pp = next(je for je in result.register if je.category == "prepaid_amortization")
    credit_accts = {ln.account for ln in pp.lines if ln.credit}
    assert credit_accts == {"1400"}
    assert pp.total_debits == pp.total_credits > 0


def test_depreciation_je_credits_accumulated_depreciation() -> None:
    result = _run()
    dep = next(je for je in result.register if je.category == "depreciation")
    credit_accts = {ln.account for ln in dep.lines if ln.credit}
    debit_accts = {ln.account for ln in dep.lines if ln.debit}
    assert credit_accts == {"1510"}
    assert debit_accts == {"6100"}


def test_mgmt_fee_je_expense_equals_cash_plus_payable() -> None:
    result = _run()
    mf = next(je for je in result.register if je.category == "mgmt_fee_accrual")
    expense = sum(ln.debit for ln in mf.lines if ln.account == "6200")
    cash = sum(ln.credit for ln in mf.lines if ln.account == "1000")
    payable = sum(ln.credit for ln in mf.lines if ln.account == "2300")
    assert expense == cash + payable


def test_gna_allocation_relieves_full_pool() -> None:
    result = _run()
    gna_je = next(je for je in result.register if je.category == "gna_allocation")
    allocated = sum(ln.debit for ln in gna_je.lines if ln.account == "6600")
    relieved = sum(ln.credit for ln in gna_je.lines if ln.account == "6650")
    assert allocated == relieved == generate_dataset("2026-03").gna().monthly_pool_cents


def test_lease_je_routes_through_intercompany() -> None:
    result = _run()
    lease = next(je for je in result.register if je.category == "deferred_rent_cam")
    accts = {ln.account for ln in lease.lines}
    # Holder uses due-from (1800); non-holders use due-to (2800).
    assert "1800" in accts
    assert "2800" in accts
    # Each entity leg still balances independently.
    for diff in lease.balances_per_entity().values():
        assert diff == 0


# --------------------------------------------------------------------------- #
# Engine refusal of an injected out-of-tie entry
# --------------------------------------------------------------------------- #


def test_engine_post_skips_empty_entry() -> None:
    from close_engine.model import JournalEntry

    eng = CloseEngine(generate_dataset("2026-03"))
    empty = JournalEntry("JE-EMPTY", "2026-03", "test", "no lines", [])
    eng._post(empty)
    assert empty not in eng.register
    assert eng.refused == []


def test_engine_post_skips_none() -> None:
    eng = CloseEngine(generate_dataset("2026-03"))
    eng._post(None)
    assert eng.register == []
    assert eng.refused == []


# --------------------------------------------------------------------------- #
# Tie-out
# --------------------------------------------------------------------------- #


def test_prepaid_tie_matches_remaining_balance() -> None:
    result = _run()
    prepaid_tie = next(t for t in result.ties if t.account == "1400")
    assert prepaid_tie.ties
    assert prepaid_tie.variance_cents == 0
    # GL actual equals abs of the group-wide 1400 balance.
    assert prepaid_tie.actual_cents == abs(result.ledger.account_balance("1400"))


def test_remaining_prepaid_non_increasing_over_period() -> None:
    march = next(t for t in _run("2026-03").ties if t.account == "1400")
    april = next(t for t in _run("2026-04").ties if t.account == "1400")
    assert april.expected_cents <= march.expected_cents


# --------------------------------------------------------------------------- #
# Report writers
# --------------------------------------------------------------------------- #


def test_je_register_json_structure(tmp_path) -> None:
    result = _run()
    data = report.je_register_json(result)
    assert data["period"] == "2026-03"
    assert data["seed"] == 2026
    assert len(data["entries"]) == len(result.register)
    assert data["refused"] == []
    for entry in data["entries"]:
        assert entry["total_debits_cents"] == entry["total_credits_cents"]
        assert entry["is_balanced"] is True
        # Each line's debit/credit cents are non-negative integers.
        for ln in entry["lines"]:
            assert ln["debit_cents"] >= 0
            assert ln["credit_cents"] >= 0


def test_trial_balance_json_balances() -> None:
    result = _run()
    data = report.trial_balance_json(result)
    assert data["in_balance"] is True
    assert data["total_debits_cents"] == data["total_credits_cents"]
    # Every row carries exactly one non-zero column.
    for row in data["rows"]:
        assert (row["debit_cents"] == 0) != (row["credit_cents"] == 0)


def test_je_register_markdown_lists_every_entry() -> None:
    result = _run()
    md = report.je_register_markdown(result)
    for je in result.register:
        assert je.je_id in md
    assert "Journal Entry Register" in md


def test_trial_balance_markdown_reports_in_balance() -> None:
    result = _run()
    md = report.trial_balance_markdown(result)
    assert "in balance" in md
    assert "OUT OF BALANCE" not in md


def test_close_report_markdown_clean_and_entities() -> None:
    result = _run()
    md = report.close_report_markdown(result)
    assert "Close status: CLEAN" in md
    assert "Demo Holdings LLC" in md
    assert "Maple Fund LP" in md
    assert "Birchwood Op Co" in md


def test_write_outputs_creates_all_committed_files(tmp_path) -> None:
    result = _run()
    written = report.write_outputs(result, tmp_path)
    names = {p.name for p in written}
    assert {
        "je_register.md",
        "je_register.json",
        "trial_balance.md",
        "trial_balance.json",
        "close_report.md",
    } <= names
    for name in (
        "je_register.json",
        "trial_balance.json",
    ):
        # JSON outputs parse cleanly.
        json.loads((tmp_path / name).read_text(encoding="utf-8"))


def test_write_outputs_creates_missing_directory(tmp_path) -> None:
    target = tmp_path / "nested" / "out"
    result = _run()
    report.write_outputs(result, target)
    assert (target / "close_report.md").exists()


def test_account_name_falls_back_to_code_for_unknown() -> None:
    result = _run()
    assert report._account_name(result, "1000") == "1000 · Cash"
    assert report._account_name(result, "ZZZZ") == "ZZZZ"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_clean_close_returns_zero(tmp_path) -> None:
    code = cli.main(
        ["--period", "2026-03", "--out", str(tmp_path), "--seed", "2026"]
    )
    assert code == 0


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "26-03", "2026/03", "bad"])
def test_cli_rejects_malformed_periods(period, tmp_path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--period", period, "--out", str(tmp_path)])


@pytest.mark.parametrize("period", ["2026-01", "2026-06", "2026-12"])
def test_cli_accepts_valid_periods(period, tmp_path) -> None:
    code = cli.main(["--period", period, "--out", str(tmp_path)])
    assert code == 0


def test_cli_run_close_writes_and_returns_result(tmp_path) -> None:
    result = cli.run_close("2026-03", str(tmp_path), 2026)
    assert isinstance(result, CloseResult)
    assert result.clean
    assert (tmp_path / "je_register.json").exists()


def test_cli_version_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
