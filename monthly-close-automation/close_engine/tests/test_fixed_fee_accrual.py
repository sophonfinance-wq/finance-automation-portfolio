"""Fixed-fee accrual rollforward, posting, tie-out, and control tests."""

from __future__ import annotations

import copy
from dataclasses import replace

from close_engine import money
from close_engine.engine import CloseEngine
from close_engine.generate import generate_dataset
from close_engine.sentinel.controls import c3_completeness_calendar, c9_shadow_recompute
from close_engine.sentinel.shadow import expected_for_category


PERIOD = "2026-03"


def _run(seed: int = 2026):
    dataset = generate_dataset(PERIOD, seed=seed)
    return dataset, CloseEngine(dataset).run()


def _entry(result):
    return next(
        je for je in result.register if je.category == "fixed_fee_accrual"
    )


def _schedule(result):
    return next(
        schedule
        for schedule in result.schedules
        if schedule.category == "fixed_fee_accrual"
    )


def test_fixed_fee_posts_fee_plus_signed_approved_adjustment() -> None:
    dataset, result = _run()
    entry = _entry(result)

    for fee in dataset.fixed_fees():
        expected = fee.monthly_fee_cents + fee.approved_adjustment_cents
        assert sum(
            line.debit
            for line in entry.lines
            if line.entity == fee.entity and line.account == "6250"
        ) == max(expected, 0)
        assert sum(
            line.credit
            for line in entry.lines
            if line.entity == fee.entity and line.account == "2350"
        ) == max(expected, 0)


def test_settlement_is_in_opening_payable_but_not_double_booked_in_entry() -> None:
    dataset, result = _run()
    entry = _entry(result)

    for fee in dataset.fixed_fees():
        opening = sum(
            line.debit - line.credit
            for line in dataset.opening_tb
            if line.entity == fee.entity and line.account == "2350"
        )
        assert opening == -(
            fee.beginning_liability_cents - fee.settlement_cents
        )
        posted_magnitude = sum(
            max(line.debit, line.credit)
            for line in entry.lines
            if line.entity == fee.entity
        )
        expected_accrual = fee.monthly_fee_cents + fee.approved_adjustment_cents
        assert posted_magnitude == 2 * abs(expected_accrual)
        assert fee.settlement_cents not in {
            max(line.debit, line.credit)
            for line in entry.lines
            if line.entity == fee.entity
        }


def test_liability_rollforward_schedule_ties_to_post_close_gl() -> None:
    dataset, result = _run()
    schedule = _schedule(result)
    rows = {row.key: row for row in schedule.rows}

    expected_ending = 0
    for fee in dataset.fixed_fees():
        accrual = fee.monthly_fee_cents + fee.approved_adjustment_cents
        ending = (
            fee.beginning_liability_cents
            - fee.settlement_cents
            + accrual
        )
        expected_ending += ending
        assert rows[fee.arrangement_id].fields["current_accrual"] == money.fmt(
            accrual
        )
        assert rows[fee.arrangement_id].fields["ending_liability"] == money.fmt(
            ending
        )

    tie = next(tie for tie in result.ties if tie.account == "2350")
    assert tie.expected_cents == expected_ending
    assert tie.actual_cents == expected_ending
    assert tie.ties


def test_sufficiently_negative_adjustment_reverses_expense_and_payable() -> None:
    dataset = generate_dataset(PERIOD, seed=99)
    original = dataset.fixed_fees()[0]
    dataset.subs.fixed_fee_accruals[0] = replace(
        original,
        monthly_fee_cents=money.to_cents(500),
        approved_adjustment_cents=-money.to_cents(1000),
    )
    result = CloseEngine(dataset).run()
    entry = _entry(result)
    reversal = money.to_cents(500)

    assert any(
        line.entity == original.entity
        and line.account == "2350"
        and line.debit == reversal
        for line in entry.lines
    )
    assert any(
        line.entity == original.entity
        and line.account == "6250"
        and line.credit == reversal
        for line in entry.lines
    )
    assert c9_shadow_recompute(dataset, result) == []
    assert result.clean


def test_shadow_recomputes_fixed_fee_without_using_engine_schedule() -> None:
    dataset, result = _run()
    expected = expected_for_category(dataset, "fixed_fee_accrual")
    actual: dict[tuple[str, str, str], tuple[int, int]] = {}
    for line in _entry(result).lines:
        key = (line.entity, "fixed_fee_accrual", line.account)
        debit, credit = actual.get(key, (0, 0))
        actual[key] = (debit + line.debit, credit + line.credit)
    assert actual == expected

    # A stale workpaper output is never an input to the next engine run.
    stale = _schedule(result)
    stale.rows[0].fields["current_accrual"] = "999,999.99"
    rerun = CloseEngine(dataset).run()
    assert _schedule(rerun).rows[0].fields["current_accrual"] != "999,999.99"
    assert _entry(rerun).lines == _entry(result).lines


def test_completeness_control_detects_a_missing_fixed_fee_entry() -> None:
    dataset, result = _run()
    corrupted = copy.deepcopy(result)
    corrupted.register = [
        je for je in corrupted.register if je.category != "fixed_fee_accrual"
    ]
    findings = c3_completeness_calendar(dataset, corrupted)
    missing = [
        finding
        for finding in findings
        if finding.subject == "expected recurring entry absent"
        and "fixed_fee_accrual" in finding.detail
    ]
    assert {finding.entity for finding in missing} == {
        fee.entity for fee in dataset.fixed_fees()
    }
