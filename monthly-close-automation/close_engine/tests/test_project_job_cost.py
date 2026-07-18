from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.project_job_cost import (
    JobExport,
    JobTransaction,
    ProjectJobCostSnapshot,
    ProjectJobCostValidator,
)


def transaction(
    transaction_id: str,
    job_id: str,
    *,
    cost_code: str = "COST-DESIGN",
    transaction_type: str = "INVOICE",
    transaction_date: str = "2026-06-15",
    accounting_date: str = "2026-06-15",
    amount_cents: object = 10_000,
) -> JobTransaction:
    return JobTransaction(
        transaction_id=transaction_id,
        job_id=job_id,
        cost_code=cost_code,
        transaction_type=transaction_type,
        transaction_date=transaction_date,
        accounting_date=accounting_date,
        amount_cents=amount_cents,
        description=f"Fictional detail {transaction_id}",
        source_reference=f"fictional://support/{transaction_id}",
    )


def snapshot(period: str = "2026-06") -> ProjectJobCostSnapshot:
    period_date = f"{period}-15"
    first = (
        transaction("TX-001", "JOB-ALPHA", transaction_date=period_date, accounting_date=period_date, amount_cents=10_000),
        transaction("TX-002", "JOB-ALPHA", cost_code="COST-PERMIT", transaction_date=period_date, accounting_date=period_date, amount_cents=2_500),
    )
    second = (transaction("TX-003", "JOB-BETA", transaction_date=period_date, accounting_date=period_date, amount_cents=8_000),)
    return ProjectJobCostSnapshot(
        period=period,
        jobs=(
            JobExport("JOB-ALPHA", period, first, 12_500),
            JobExport("JOB-BETA", period, second, 8_000),
        ),
    )


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def test_clean_export_is_validation_only_and_ready_for_human_review() -> None:
    result = ProjectJobCostValidator(snapshot()).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.job_count == 2
    assert result.transaction_count == 3
    assert result.cost_code_count == 2
    assert result.journal_entries == ()
    assert result.import_payloads == ()
    assert result.posting_actions == ()


@pytest.mark.parametrize("period", ["2026-6", "June 2026", "", "2026-13"])
def test_invalid_current_period_is_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        ProjectJobCostValidator(replace(snapshot(), period=period))


def test_missing_and_duplicate_job_exports_block() -> None:
    current = snapshot()
    missing = replace(current, jobs=())
    duplicate = replace(current, jobs=current.jobs + (current.jobs[0],))
    assert "JOB_EXPORT_MISSING" in codes(ProjectJobCostValidator(missing).validate())
    assert "DUPLICATE_JOB_EXPORT" in codes(ProjectJobCostValidator(duplicate).validate())


def test_job_period_and_transaction_job_mismatch_block() -> None:
    current = snapshot()
    changed_transaction = replace(current.jobs[0].transactions[0], job_id="JOB-WRONG")
    changed_job = replace(
        current.jobs[0],
        period="2026-05",
        transactions=(changed_transaction,) + current.jobs[0].transactions[1:],
    )
    result = ProjectJobCostValidator(replace(current, jobs=(changed_job, current.jobs[1]))).validate()
    assert "JOB_PERIOD_MISMATCH" in codes(result)
    assert "TRANSACTION_JOB_MISMATCH" in codes(result)


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("transaction_id", "UNSAFE_TRANSACTION_ID"),
        ("job_id", "UNSAFE_TRANSACTION_JOB"),
        ("cost_code", "UNSAFE_COST_CODE"),
        ("transaction_type", "UNSAFE_TRANSACTION_TYPE"),
        ("description", "UNSAFE_DESCRIPTION"),
        ("source_reference", "UNSAFE_SOURCE_REFERENCE"),
    ],
)
def test_blank_or_untrimmed_core_text_blocks(field: str, code: str) -> None:
    current = snapshot()
    changed = replace(current.jobs[0].transactions[0], **{field: " BAD"})
    job = replace(current.jobs[0], transactions=(changed,) + current.jobs[0].transactions[1:])
    assert code in codes(ProjectJobCostValidator(replace(current, jobs=(job, current.jobs[1]))).validate())


@pytest.mark.parametrize("unsafe", [None, 1.5, True, "100"])
def test_unsafe_transaction_amount_blocks(unsafe: object) -> None:
    current = snapshot()
    changed = replace(current.jobs[0].transactions[0], amount_cents=unsafe)
    job = replace(current.jobs[0], transactions=(changed,) + current.jobs[0].transactions[1:])
    assert "UNSAFE_TRANSACTION_AMOUNT" in codes(
        ProjectJobCostValidator(replace(current, jobs=(job, current.jobs[1]))).validate()
    )


def test_accounting_date_outside_month_blocks() -> None:
    current = snapshot()
    changed = replace(current.jobs[0].transactions[0], accounting_date="2026-05-31")
    job = replace(current.jobs[0], transactions=(changed,) + current.jobs[0].transactions[1:])
    assert "ACCOUNTING_DATE_OUT_OF_RANGE" in codes(
        ProjectJobCostValidator(replace(current, jobs=(job, current.jobs[1]))).validate()
    )


@pytest.mark.parametrize("value", ["2026-6-1", "", "2026-02-30"])
def test_invalid_transaction_date_blocks(value: str) -> None:
    current = snapshot()
    changed = replace(current.jobs[0].transactions[0], transaction_date=value)
    job = replace(current.jobs[0], transactions=(changed,) + current.jobs[0].transactions[1:])
    assert "TRANSACTION_DATE_INVALID" in codes(
        ProjectJobCostValidator(replace(current, jobs=(job, current.jobs[1]))).validate()
    )


def test_post_period_transaction_date_is_visible_warning() -> None:
    current = snapshot()
    changed = replace(current.jobs[0].transactions[0], transaction_date="2026-07-02")
    job = replace(current.jobs[0], transactions=(changed,) + current.jobs[0].transactions[1:])
    result = ProjectJobCostValidator(replace(current, jobs=(job, current.jobs[1]))).validate()
    assert "POST_PERIOD_TRANSACTION_DATE_REVIEW" in codes(result)
    assert result.post_period_transaction_count == 1
    assert result.mechanical_clean


def test_negative_transaction_is_visible_warning() -> None:
    current = snapshot()
    changed = replace(current.jobs[0].transactions[0], amount_cents=-10_000)
    job = replace(current.jobs[0], transactions=(changed,) + current.jobs[0].transactions[1:], cached_total_cents=-7_500)
    result = ProjectJobCostValidator(replace(current, jobs=(job, current.jobs[1]))).validate()
    assert "NEGATIVE_TRANSACTION_REVIEW" in codes(result)
    assert result.negative_transaction_count == 1
    assert result.mechanical_clean


def test_cached_job_total_difference_and_unsafe_type_block() -> None:
    current = snapshot()
    different = replace(current.jobs[0], cached_total_cents=12_501)
    unsafe = replace(current.jobs[0], cached_total_cents=12.5)
    assert "JOB_TOTAL_OUT_OF_TIE" in codes(
        ProjectJobCostValidator(replace(current, jobs=(different, current.jobs[1]))).validate()
    )
    assert "UNSAFE_CACHED_JOB_TOTAL" in codes(
        ProjectJobCostValidator(replace(current, jobs=(unsafe, current.jobs[1]))).validate()
    )


def test_duplicate_transaction_id_and_exact_key_block() -> None:
    current = snapshot()
    duplicate_id = replace(current.jobs[0].transactions[1], transaction_id="TX-001")
    job = replace(current.jobs[0], transactions=(current.jobs[0].transactions[0], duplicate_id))
    assert "DUPLICATE_TRANSACTION_ID" in codes(
        ProjectJobCostValidator(replace(current, jobs=(job, current.jobs[1]))).validate()
    )
    exact = current.jobs[0].transactions[0]
    duplicate_job = replace(current.jobs[0], transactions=(exact, exact), cached_total_cents=20_000)
    result = ProjectJobCostValidator(replace(current, jobs=(duplicate_job, current.jobs[1]))).validate()
    assert "EXACT_DUPLICATE_TRANSACTION" in codes(result)
    assert result.duplicate_transaction_count == 1


def test_prior_must_be_immediately_preceding_month_including_year_boundary() -> None:
    assert "PRIOR_PERIOD_MISMATCH" in codes(
        ProjectJobCostValidator(snapshot(), snapshot("2026-04")).validate()
    )
    assert "PRIOR_PERIOD_MISMATCH" not in codes(
        ProjectJobCostValidator(snapshot("2027-01"), snapshot("2026-12")).validate()
    )


def test_current_prior_population_changes_are_visible_warnings() -> None:
    current = snapshot()
    prior = ProjectJobCostSnapshot(
        period="2026-05",
        jobs=(
            JobExport(
                "JOB-ALPHA",
                "2026-05",
                (
                    transaction(
                        "OLD-001",
                        "JOB-ALPHA",
                        cost_code="COST-OLD",
                        transaction_type="ADJUSTMENT",
                        transaction_date="2026-05-15",
                        accounting_date="2026-05-15",
                    ),
                ),
                10_000,
            ),
        ),
    )
    result = ProjectJobCostValidator(current, prior).validate()
    observed = codes(result)
    assert "JOB_POPULATION_CHANGED" in observed
    assert "COST_CODE_POPULATION_CHANGED" in observed
    assert "TRANSACTION_TYPE_POPULATION_CHANGED" in observed
    assert result.job_added_count == 1
    assert result.cost_code_added_count == 2
    assert result.cost_code_removed_count == 1
    assert result.transaction_type_added_count == 1
    assert result.transaction_type_removed_count == 1
    assert result.mechanical_clean
