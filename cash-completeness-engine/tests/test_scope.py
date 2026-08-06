"""Scope reconciliation: the completeness claim must foot or fail loudly."""

from __future__ import annotations

from ccengine.models import ExceptionItem, ScopeReconciliation
from ccengine.reconcile import classify_exceptions
from ccengine.scope import (
    BUCKET_A,
    BUCKET_B,
    BUCKET_C,
    BUCKET_D,
    BUCKET_MATCHED,
    BUCKET_ORDER,
    build_scope_reconciliation,
    foot_scope,
)
from tests.conftest import make_account, make_tb_row


def _population():
    return [
        make_account("615-001-1101", 160000.00),
        make_account("424-002-1101", 84210.55, entity="Harbor 17 Investor LLC"),
        make_account("424-004-1101", 12500.00, entity="Kestrel Capital Partners LLC"),
    ]


def _exceptions():
    return [
        ExceptionItem(
            kind="A_UNMAPPED_SUCCESSOR",
            gl_norm="424-002-1101",
            entity="Harbor 17 Investor LLC",
            register_balance=84210.55,
        ),
        ExceptionItem(
            kind="D_UNEXPLAINED",
            gl_norm="424-004-1101",
            entity="Kestrel Capital Partners LLC",
            register_balance=12500.00,
            tb_balance=11000.00,
        ),
    ]


# ---------------------------------------------------------------------------
# Building the scope statement
# ---------------------------------------------------------------------------


def test_every_account_lands_in_exactly_one_bucket_and_all_buckets_exist():
    scope = build_scope_reconciliation(_population(), _exceptions())
    assert set(scope.buckets) == set(BUCKET_ORDER)  # empties included
    assert scope.buckets[BUCKET_MATCHED] == ["615-001-1101"]
    assert scope.buckets[BUCKET_A] == ["424-002-1101"]
    assert scope.buckets[BUCKET_B] == []
    assert scope.buckets[BUCKET_C] == []
    assert scope.buckets[BUCKET_D] == ["424-004-1101"]
    assert scope.totals[BUCKET_MATCHED] == 160000.00
    assert scope.totals[BUCKET_A] == 84210.55
    assert scope.totals[BUCKET_D] == 12500.00


def test_scope_built_from_classifier_output_foots_clean():
    registers = _population()
    tb_rows = [
        make_tb_row("615-001-1101", 160000.00),
        make_tb_row("424-004-1101", 11000.00),
    ]
    exceptions, _ = classify_exceptions(registers, tb_rows)
    scope = build_scope_reconciliation(registers, exceptions)
    assert scope.foot(registers) == []
    assert foot_scope(scope, registers) == []


# ---------------------------------------------------------------------------
# Footing failures: the exact account is always named
# ---------------------------------------------------------------------------


def test_foot_fails_naming_the_omitted_account():
    registers = _population()
    scope = build_scope_reconciliation(registers, _exceptions())
    scope.buckets[BUCKET_A].remove("424-002-1101")  # simulate the overclaim
    problems = scope.foot(registers)
    assert problems, "an omitted account must not foot clean"
    assert any(
        "424-002-1101" in p and "missing from every scope bucket" in p
        for p in problems
    )


def test_foot_fails_naming_a_double_counted_account():
    registers = _population()
    scope = build_scope_reconciliation(registers, _exceptions())
    scope.buckets[BUCKET_MATCHED].append("424-002-1101")  # now in two buckets
    problems = scope.foot(registers)
    assert any("424-002-1101" in p and "2 buckets" in p for p in problems)


def test_foot_fails_naming_an_account_that_does_not_exist():
    registers = _population()
    scope = build_scope_reconciliation(registers, _exceptions())
    scope.buckets[BUCKET_MATCHED].append("999-999-9999")
    scope.totals[BUCKET_MATCHED] = 160000.00  # total untouched
    problems = scope.foot(registers)
    assert any(
        "999-999-9999" in p and "not in the register population" in p
        for p in problems
    )


def test_foot_fails_when_a_total_does_not_re_add():
    registers = _population()
    scope = build_scope_reconciliation(registers, _exceptions())
    scope.totals[BUCKET_MATCHED] = 159000.00  # off by 1,000
    problems = scope.foot(registers)
    assert any(BUCKET_MATCHED in p and "re-add" in p for p in problems)


def test_foot_fails_on_bucket_and_totals_key_mismatch():
    scope = ScopeReconciliation(
        buckets={"only_bucket": ["615-001-1101"]},
        totals={"other_total": 160000.00},
    )
    problems = scope.foot([make_account("615-001-1101", 160000.00)])
    assert any("only_bucket" in p and "totals" in p for p in problems)
    assert any("other_total" in p for p in problems)


def test_foot_reports_duplicate_gl_norms_in_the_population():
    registers = [
        make_account("615-001-1101", 100.00, source_file="one.csv"),
        make_account("615-001-1101", 50.00, source_file="two.csv"),
    ]
    scope = build_scope_reconciliation(registers, [])
    problems = scope.foot(registers)
    assert any("duplicate gl_norm 615-001-1101" in p for p in problems)


def test_cent_tolerance_does_not_flag_rounding_dust():
    registers = [make_account("615-001-1101", 100.004)]
    scope = ScopeReconciliation(
        buckets={BUCKET_MATCHED: ["615-001-1101"]},
        totals={BUCKET_MATCHED: 100.00},
    )
    assert scope.foot(registers) == []
