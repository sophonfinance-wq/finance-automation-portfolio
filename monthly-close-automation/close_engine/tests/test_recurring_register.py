"""Focused controls for the read-only recurring-register validator."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from close_engine.recurring_register import (
    RecurringRegisterValidator,
    RegisterRow,
    demo_rows,
    main,
)


PERIOD = "2026-03"


def _run(rows=None):
    return RecurringRegisterValidator(
        PERIOD, demo_rows(PERIOD) if rows is None else rows
    ).run()


def _codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def test_clean_fictional_register_passes_every_gate() -> None:
    result = _run()

    assert result.clean
    assert result.verdict == "PASS"
    assert result.row_count == 4
    assert len(result.group_balances) == 2
    assert all(group.balanced for group in result.group_balances)
    assert result.total_debits_cents == result.total_credits_cents == 205_000
    assert result.totals_verifiable


def test_validator_never_authorizes_or_builds_posting_work() -> None:
    result = _run()

    assert not result.posting_authorized
    assert result.posting_actions == ()
    assert result.import_payloads == ()


@pytest.mark.parametrize(
    "period", ["2026-3", "03-2026", "2026-00", "2026-13", " 2026-03", ""]
)
def test_target_period_must_be_exact_canonical_year_month(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        RecurringRegisterValidator(period, [])


def test_prior_period_row_is_explicitly_stale() -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], period="2026-02")

    result = _run(rows)

    assert "ROW_PERIOD_STALE" in _codes(result)
    assert not result.clean


@pytest.mark.parametrize("period", ["2026-3", "2026-00", "202603", "2026-03 "])
def test_noncanonical_row_period_is_rejected(period: str) -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], period=period)

    assert "ROW_PERIOD_INVALID" in _codes(_run(rows))


def test_duplicate_line_key_is_blocking_even_when_register_still_balances() -> None:
    rows = list(demo_rows(PERIOD))
    rows.extend((rows[0], rows[1]))

    result = _run(rows)

    assert result.total_debits_cents == result.total_credits_cents
    assert "DUPLICATE_LINE_KEY" in _codes(result)
    assert not result.clean


def test_stale_period_token_in_memo_is_detected() -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], memo="2026-02 recurring service accrual")

    result = _run(rows)

    finding = next(
        finding
        for finding in result.findings
        if finding.code == "STALE_MEMO_PERIOD"
    )
    assert "2026-02" in finding.detail


def test_current_period_token_in_memo_is_not_stale() -> None:
    assert "STALE_MEMO_PERIOD" not in _codes(_run())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_amounts_are_rejected_without_crashing(value: float) -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], debit_cents=value)

    result = _run(rows)

    amount_finding = next(
        finding
        for finding in result.findings
        if finding.code == "ROW_AMOUNT_INVALID"
    )
    assert "nonfinite" in amount_finding.detail
    assert "GROUP_BALANCE_UNVERIFIABLE" in _codes(result)
    assert "GLOBAL_BALANCE_UNVERIFIABLE" in _codes(result)


@pytest.mark.parametrize(
    "value,detail",
    [
        ("=SUM(A1:A2)", "formula text"),
        ("#REF!", "spreadsheet error token"),
        ("#VALUE!", "spreadsheet error token"),
        ("#DIV/0!", "spreadsheet error token"),
        ("125000", "text amount"),
    ],
)
def test_formula_error_and_numeric_text_amounts_are_never_coerced(
    value: str, detail: str
) -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], debit_cents=value)

    result = _run(rows)

    assert any(
        finding.code == "ROW_AMOUNT_INVALID" and detail in finding.detail
        for finding in result.findings
    )


@pytest.mark.parametrize(
    "value,detail",
    [
        (True, "boolean"),
        (-1, "nonnegative"),
        (1250.0, "floating-point"),
        (None, "missing"),
    ],
)
def test_unsafe_amount_types_and_signs_are_rejected(value, detail: str) -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], debit_cents=value)

    result = _run(rows)

    assert any(
        finding.code == "ROW_AMOUNT_INVALID" and detail in finding.detail
        for finding in result.findings
    )


def test_a_line_cannot_hold_both_a_debit_and_a_credit() -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], credit_cents=125_000)

    assert "ROW_TWO_SIDED" in _codes(_run(rows))


def test_zero_value_line_is_not_silently_treated_as_activity() -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], debit_cents=0)

    result = _run(rows)

    assert "ROW_ZERO_AMOUNT" in _codes(result)
    assert "GROUP_OUT_OF_BALANCE" in _codes(result)


def test_per_group_balance_cannot_hide_behind_global_netting() -> None:
    rows = list(demo_rows(PERIOD))
    # The first entry has a 100-cent excess debit; the second has an equal
    # excess credit.  Global debits still equal global credits.
    rows[0] = replace(rows[0], debit_cents=125_100)
    rows[3] = replace(rows[3], credit_cents=80_100)

    result = _run(rows)

    assert result.total_debits_cents == result.total_credits_cents
    out = [
        finding
        for finding in result.findings
        if finding.code == "GROUP_OUT_OF_BALANCE"
    ]
    assert {finding.entry_id for finding in out} == {
        f"RJE-{PERIOD}-01",
        f"RJE-{PERIOD}-02",
    }
    assert "GLOBAL_OUT_OF_BALANCE" not in _codes(result)


def test_global_out_of_balance_is_an_independent_gate() -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], debit_cents=125_001)

    result = _run(rows)

    assert "GROUP_OUT_OF_BALANCE" in _codes(result)
    assert "GLOBAL_OUT_OF_BALANCE" in _codes(result)


def test_invalid_amount_marks_totals_unverifiable_not_false_clean() -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], debit_cents="#N/A")

    result = _run(rows)

    assert not result.totals_verifiable
    assert "GROUP_BALANCE_UNVERIFIABLE" in _codes(result)
    assert "GLOBAL_BALANCE_UNVERIFIABLE" in _codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_empty_register_is_not_a_clean_noop() -> None:
    result = _run([])

    assert "REGISTER_EMPTY" in _codes(result)
    assert not result.clean


@pytest.mark.parametrize(
    "field,value",
    [
        ("entry_id", ""),
        ("line_id", "  "),
        ("entity", " NORTH"),
        ("account", "EXP-SERVICE "),
        ("memo", ""),
    ],
)
def test_required_text_fields_must_be_nonblank_and_trimmed(
    field: str, value: str
) -> None:
    rows = list(demo_rows(PERIOD))
    rows[0] = replace(rows[0], **{field: value})

    assert "ROW_FIELD_INVALID" in _codes(_run(rows))


def test_validator_does_not_mutate_input_rows() -> None:
    rows = list(demo_rows(PERIOD))
    before = tuple(rows)

    _run(rows)

    assert tuple(rows) == before


def test_demo_cli_reports_validation_only_pass(capsys) -> None:
    exit_code = main(["--period", PERIOD])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Posting actions  : 0 (validation only)" in output
    assert "Import payloads  : 0 (validation only)" in output
    assert "Verdict          : PASS" in output


def test_json_cli_reports_defect_and_leaves_source_unchanged(
    tmp_path, capsys
) -> None:
    rows = [row.__dict__ for row in demo_rows(PERIOD)]
    rows[0]["debit_cents"] = "#REF!"
    path = tmp_path / "register.json"
    path.write_text(
        json.dumps({"target_period": PERIOD, "rows": rows}),
        encoding="utf-8",
    )
    before = path.read_bytes()

    exit_code = main(["--input", str(path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "ROW_AMOUNT_INVALID" in output
    assert "Posting actions  : 0 (validation only)" in output
    assert path.read_bytes() == before


def test_json_mapping_requires_every_public_field() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        RegisterRow.from_mapping({"period": PERIOD})
