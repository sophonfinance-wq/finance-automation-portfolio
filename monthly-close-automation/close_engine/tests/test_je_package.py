from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.je_package import (
    JournalEntry,
    JournalEntryPackage,
    JournalLine,
    JournalPackageValidator,
)


def line(account_id: str, description: str, *, debit: int = 0, credit: int = 0) -> JournalLine:
    return JournalLine(account_id=account_id, description=description, debit_cents=debit, credit_cents=credit)


def entry(
    entry_id: str,
    lines: list[JournalLine],
    *,
    period: str = "2026-06",
    one_sided: bool = False,
    carry: bool = False,
) -> JournalEntry:
    debit = sum(item.debit_cents for item in lines if isinstance(item.debit_cents, int) and not isinstance(item.debit_cents, bool))
    credit = sum(item.credit_cents for item in lines if isinstance(item.credit_cents, int) and not isinstance(item.credit_cents, bool))
    return JournalEntry(
        entry_id=entry_id,
        period=period,
        lines=tuple(lines),
        cached_debit_total_cents=debit,
        cached_credit_total_cents=credit,
        one_sided_allowed=one_sided,
        carryforward=carry,
    )


def current_package() -> JournalEntryPackage:
    entries = (
        entry("CONST-INT", [line("ACCT-A", "Interest debit", debit=500000), line("ACCT-B", "Interest credit", credit=500000)]),
        entry("DEV-FEES", [line("ACCT-C", "Dev fee debit", debit=1000000), line("ACCT-D", "Dev fee credit", credit=1000000)]),
        entry("INTERCO", [line("ACCT-E", "Intercompany charge", debit=250000)], one_sided=True),
        entry("YE-ACCRUAL", [line("ACCT-F", "Accrual debit", debit=700000), line("ACCT-G", "Accrual credit", credit=700000)], period="2020-06", carry=True),
    )
    return JournalEntryPackage(period="2026-06", entries=entries, source_fingerprint="a" * 64)


def prior_package() -> JournalEntryPackage:
    entries = (
        entry("CONST-INT", [line("ACCT-A", "Interest debit", debit=400000), line("ACCT-B", "Interest credit", credit=400000)], period="2026-05"),
        entry("DEV-FEES", [line("ACCT-C", "Dev fee debit", debit=900000), line("ACCT-D", "Dev fee credit", credit=900000)], period="2026-05"),
        entry("INTERCO", [line("ACCT-E", "Intercompany charge", debit=50000)], period="2026-05", one_sided=True),
        entry("YE-ACCRUAL", [line("ACCT-F", "Accrual debit", debit=700000), line("ACCT-G", "Accrual credit", credit=700000)], period="2020-06", carry=True),
    )
    return JournalEntryPackage(period="2026-05", entries=entries, source_fingerprint="b" * 64)


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def replace_entry(package: JournalEntryPackage, index: int, new_entry: JournalEntry) -> JournalEntryPackage:
    entries = package.entries[:index] + (new_entry,) + package.entries[index + 1:]
    return replace(package, entries=entries)


def test_clean_package_is_validation_only_and_ready() -> None:
    result = JournalPackageValidator(current_package()).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.entry_count == 4
    assert result.balanced_entry_count == 3
    assert result.out_of_balance_count == 0
    assert result.one_sided_count == 1
    assert result.carryforward_count == 1
    assert result.stale_period_count == 0
    assert "ONE_SIDED_ENTRY_REVIEW" in codes(result)
    assert result.journal_entries == ()
    assert result.import_payloads == ()
    assert result.posting_actions == ()


@pytest.mark.parametrize("period", ["2026-6", "June 2026", "", "2026-13"])
def test_invalid_period_is_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        JournalPackageValidator(replace(current_package(), period=period))


def test_missing_population_blocks() -> None:
    result = JournalPackageValidator(replace(current_package(), entries=())).validate()
    assert "PACKAGE_POPULATION_MISSING" in codes(result)


def test_unsafe_entry_id_blocks() -> None:
    bad = replace(current_package().entries[0], entry_id=" BAD")
    assert "UNSAFE_ENTRY_ID" in codes(JournalPackageValidator(replace_entry(current_package(), 0, bad)).validate())


@pytest.mark.parametrize(("field", "code"), [("account_id", "UNSAFE_ACCOUNT_ID"), ("description", "UNSAFE_LINE_DESCRIPTION")])
def test_blank_line_text_blocks(field: str, code: str) -> None:
    current = current_package()
    bad_line = replace(current.entries[0].lines[0], **{field: " BAD"})
    bad_entry = replace(current.entries[0], lines=(bad_line,) + current.entries[0].lines[1:])
    assert code in codes(JournalPackageValidator(replace_entry(current, 0, bad_entry)).validate())


def test_duplicate_entry_blocks() -> None:
    current = current_package()
    dup = replace(current.entries[1], entry_id="CONST-INT")
    assert "DUPLICATE_ENTRY" in codes(JournalPackageValidator(replace_entry(current, 1, dup)).validate())


def test_out_of_balance_entry_blocks() -> None:
    unbalanced = entry("CONST-INT", [line("ACCT-A", "d", debit=500000), line("ACCT-B", "c", credit=400000)])
    result = JournalPackageValidator(replace_entry(current_package(), 0, unbalanced)).validate()
    assert "ENTRY_OUT_OF_BALANCE" in codes(result)
    assert "ENTRY_DEBIT_TOTAL_OUT_OF_TIE" not in codes(result)
    assert not result.mechanical_clean
    assert result.out_of_balance_count == 1


def test_one_sided_intercompany_is_review_warning_not_error() -> None:
    result = JournalPackageValidator(current_package()).validate()
    assert "ONE_SIDED_ENTRY_REVIEW" in codes(result)
    assert "ENTRY_OUT_OF_BALANCE" not in codes(result)
    assert result.mechanical_clean


def test_line_cannot_be_both_debit_and_credit() -> None:
    both = entry("CONST-INT", [line("ACCT-A", "both", debit=1, credit=1), line("ACCT-B", "c", credit=1)])
    assert "LINE_BOTH_DEBIT_AND_CREDIT" in codes(JournalPackageValidator(replace_entry(current_package(), 0, both)).validate())


@pytest.mark.parametrize("unsafe", [None, 1.5, True, -1, "100"])
def test_line_amounts_must_be_nonnegative_integer_cents(unsafe: object) -> None:
    current = current_package()
    bad_line = replace(current.entries[0].lines[0], debit_cents=unsafe)
    bad_entry = replace(current.entries[0], lines=(bad_line,) + current.entries[0].lines[1:])
    assert "UNSAFE_LINE_AMOUNT" in codes(JournalPackageValidator(replace_entry(current, 0, bad_entry)).validate())


def test_cached_entry_totals_must_readd() -> None:
    current = current_package()
    debit_wrong = replace(current.entries[0], cached_debit_total_cents=1)
    assert "ENTRY_DEBIT_TOTAL_OUT_OF_TIE" in codes(JournalPackageValidator(replace_entry(current, 0, debit_wrong)).validate())
    credit_wrong = replace(current.entries[0], cached_credit_total_cents=1)
    assert "ENTRY_CREDIT_TOTAL_OUT_OF_TIE" in codes(JournalPackageValidator(replace_entry(current, 0, credit_wrong)).validate())


def test_stale_non_carryforward_entry_period_blocks() -> None:
    stale = replace(current_package().entries[0], period="2026-05")
    result = JournalPackageValidator(replace_entry(current_package(), 0, stale)).validate()
    assert "STALE_ENTRY_PERIOD" in codes(result)
    assert result.stale_period_count == 1


def test_carryforward_entry_may_retain_older_period() -> None:
    result = JournalPackageValidator(current_package()).validate()
    assert "STALE_ENTRY_PERIOD" not in codes(result)
    assert result.stale_period_count == 0
    assert result.carryforward_count == 1


@pytest.mark.parametrize("fingerprint", ["", "A" * 64, "a" * 63, "private-path"])
def test_source_fingerprint_must_be_lowercase_sha256(fingerprint: str) -> None:
    result = JournalPackageValidator(replace(current_package(), source_fingerprint=fingerprint)).validate()
    assert "UNSAFE_SOURCE_FINGERPRINT" in codes(result)


def test_prior_must_be_immediately_preceding_month() -> None:
    prior = replace(prior_package(), period="2026-04")
    assert "PRIOR_PERIOD_MISMATCH" in codes(JournalPackageValidator(current_package(), prior).validate())


def test_clean_current_prior_pair_is_mechanically_clean() -> None:
    result = JournalPackageValidator(current_package(), prior_package()).validate()
    assert result.mechanical_clean
    assert result.entry_added_count == 0
    assert result.entry_removed_count == 0
    assert result.carryforward_change_count == 0
    assert result.total_debits_cents == 500000 + 1000000 + 250000 + 700000
    assert result.total_credits_cents == 500000 + 1000000 + 0 + 700000


def test_carryforward_change_blocks() -> None:
    prior = prior_package()
    changed = entry("YE-ACCRUAL", [line("ACCT-F", "Accrual debit", debit=600000), line("ACCT-G", "Accrual credit", credit=600000)], period="2020-06", carry=True)
    prior = replace_entry(prior, 3, changed)
    result = JournalPackageValidator(current_package(), prior).validate()
    assert "CARRYFORWARD_ENTRY_CHANGED" in codes(result)
    assert result.carryforward_change_count == 1
    assert not result.mechanical_clean


def test_entry_population_change_is_visible_warning() -> None:
    prior = prior_package()
    prior = replace(prior, entries=prior.entries[:3])  # drop the carryforward entry
    result = JournalPackageValidator(current_package(), prior).validate()
    assert "ENTRY_POPULATION_CHANGED" in codes(result)
    assert result.entry_added_count == 1
    assert result.entry_removed_count == 0
    assert result.mechanical_clean


def test_identical_sequential_fingerprints_are_visible_warning() -> None:
    prior = replace(prior_package(), source_fingerprint="a" * 64)
    result = JournalPackageValidator(current_package(), prior).validate()
    assert "IDENTICAL_PERIOD_FINGERPRINTS" in codes(result)
    assert result.mechanical_clean
