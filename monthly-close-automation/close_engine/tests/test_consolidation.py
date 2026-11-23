from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.consolidation import (
    APPROVED_DEPENDENCY_ROLES,
    REQUIRED_ROLES,
    ConsolidationSnapshot,
    ConsolidationValidator,
    ControlEvidence,
    DependencyEvidence,
    FormulaEvidence,
    ManualAdjustment,
    StatementRole,
)


def snapshot(period: str = "2026-06") -> ConsolidationSnapshot:
    roles = tuple(StatementRole(role, period) for role in sorted(REQUIRED_ROLES))
    dependencies = (
        DependencyEvidence("dep-tb", "trial_balance", period, "fictional://trial-balance"),
        DependencyEvidence("dep-ops", "operations_package", period, "fictional://operations"),
        DependencyEvidence("dep-prior", "prior_consolidation", "2026-05", "fictional://prior"),
    )
    formulas = (
        FormulaEvidence("bs-total", "balance_sheet", "SUM_DETAIL", 12_500_00),
        FormulaEvidence("cash-tie", "cash_flow", "ENDING_CASH_TIE", 0),
        FormulaEvidence(
            "tb-import",
            "balance_sheet",
            "EXTERNAL_SOURCE_VALUE",
            4_200_00,
            external_dependency_id="dep-tb",
        ),
    )
    controls = tuple(
        ControlEvidence(control_id, role, value, value)
        for control_id, role, value in (
            ("balance-sheet", "balance_sheet", 12_500_00),
            ("operations", "operations_statement", 2_400_00),
            ("equity", "equity_rollforward", 3_200_00),
            ("ending-cash", "cash_flow", 1_850_00),
            ("receivables", "accounts_receivable", 440_00),
            ("fee-income", "fee_income", 780_00),
            ("project-results", "project_gains_losses", -125_00),
            ("related-party", "related_party_matrix", 0),
            ("investment-bridge", "investment_change_bridge", 920_00),
            ("grossed-balance", "grossed_balance_sheet", 18_300_00),
        )
    )
    return ConsolidationSnapshot(
        period=period,
        roles=roles,
        formulas=formulas,
        dependencies=dependencies,
        controls=controls,
        entity_keys=("ENTITY-ALPHA", "ENTITY-BETA"),
        project_keys=("PROJECT-ORANGE", "PROJECT-VIOLET"),
        account_keys=("ASSET-CASH", "EQUITY-MEMBERS"),
    )


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def test_clean_package_is_validation_only_and_ready_for_human_review() -> None:
    result = ConsolidationValidator(snapshot()).validate()

    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.role_count == 13
    assert result.formula_count == 3
    assert result.external_formula_count == 1
    assert result.dependency_count == 3
    assert result.control_count == 10
    assert result.journal_entries == ()
    assert result.import_payloads == ()
    assert result.posting_actions == ()
    assert result.submissions == ()


def test_missing_role_blocks() -> None:
    current = snapshot()
    current = replace(current, roles=current.roles[:-1])
    result = ConsolidationValidator(current).validate()
    assert "MISSING_ROLE" in codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_duplicate_role_blocks() -> None:
    current = snapshot()
    current = replace(current, roles=current.roles + (current.roles[0],))
    assert "DUPLICATE_ROLE" in codes(ConsolidationValidator(current).validate())


def test_unknown_role_blocks() -> None:
    current = snapshot()
    current = replace(current, roles=current.roles + (StatementRole("mystery_role", "2026-06"),))
    assert "UNKNOWN_ROLE" in codes(ConsolidationValidator(current).validate())


def test_role_period_mismatch_blocks() -> None:
    current = snapshot()
    changed = replace(current.roles[0], period="2026-05")
    current = replace(current, roles=(changed,) + current.roles[1:])
    assert "ROLE_PERIOD_MISMATCH" in codes(ConsolidationValidator(current).validate())


@pytest.mark.parametrize("period", ["2026-6", "June 2026", "", "2026-13"])
def test_invalid_current_period_is_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        ConsolidationValidator(replace(snapshot(), period=period))


@pytest.mark.parametrize("unsafe", [None, 1.25, True, "100", "#REF!"])
def test_unsafe_formula_cache_blocks(unsafe: object) -> None:
    current = snapshot()
    changed = replace(current.formulas[0], cached_cents=unsafe)
    current = replace(current, formulas=(changed,) + current.formulas[1:])
    result = ConsolidationValidator(current).validate()
    assert "FORMULA_CACHE_MISSING_OR_UNSAFE" in codes(result)


def test_formula_error_token_blocks_even_with_numeric_cache() -> None:
    current = snapshot()
    changed = replace(current.formulas[0], signature="SUM_DETAIL+#VALUE!")
    current = replace(current, formulas=(changed,) + current.formulas[1:])
    assert "FORMULA_ERROR_TOKEN" in codes(ConsolidationValidator(current).validate())


def test_external_formula_requires_declared_dependency() -> None:
    current = snapshot()
    changed = replace(current.formulas[0], external_dependency_id="missing-dependency")
    current = replace(current, formulas=(changed,) + current.formulas[1:])
    assert "FORMULA_DEPENDENCY_MISSING" in codes(ConsolidationValidator(current).validate())


def test_unknown_dependency_role_blocks() -> None:
    current = snapshot()
    changed = replace(current.dependencies[0], role="unapproved_feed")
    current = replace(current, dependencies=(changed,) + current.dependencies[1:])
    assert "UNKNOWN_DEPENDENCY_ROLE" in codes(ConsolidationValidator(current).validate())


def test_all_approved_dependency_roles_are_explicit() -> None:
    assert APPROVED_DEPENDENCY_ROLES == {
        "trial_balance",
        "debt_schedule",
        "investment_schedule",
        "operations_package",
        "prior_consolidation",
    }


def test_current_dependency_period_mismatch_blocks() -> None:
    current = snapshot()
    changed = replace(current.dependencies[0], period="2026-05")
    current = replace(current, dependencies=(changed,) + current.dependencies[1:])
    assert "DEPENDENCY_PERIOD_MISMATCH" in codes(ConsolidationValidator(current).validate())


def test_prior_consolidation_must_be_immediately_preceding_month() -> None:
    current = snapshot()
    changed = replace(current.dependencies[-1], period="2026-04")
    current = replace(current, dependencies=current.dependencies[:-1] + (changed,))
    assert "DEPENDENCY_PERIOD_MISMATCH" in codes(ConsolidationValidator(current).validate())


def test_january_prior_dependency_crosses_year_boundary() -> None:
    current = snapshot("2027-01")
    dependencies = tuple(
        replace(item, period="2026-12" if item.role == "prior_consolidation" else "2027-01")
        for item in current.dependencies
    )
    current = replace(current, dependencies=dependencies)
    assert "DEPENDENCY_PERIOD_MISMATCH" not in codes(ConsolidationValidator(current).validate())


def test_broken_dependency_reference_blocks() -> None:
    current = snapshot()
    changed = replace(current.dependencies[0], reference="#REF!")
    current = replace(current, dependencies=(changed,) + current.dependencies[1:])
    assert "UNSAFE_DEPENDENCY_REFERENCE" in codes(ConsolidationValidator(current).validate())


@pytest.mark.parametrize("unsafe", [None, 1.5, True, "100"])
def test_unsafe_control_amount_blocks(unsafe: object) -> None:
    current = snapshot()
    changed = replace(current.controls[0], actual_cents=unsafe)
    current = replace(current, controls=(changed,) + current.controls[1:])
    assert "UNSAFE_CONTROL_AMOUNT" in codes(ConsolidationValidator(current).validate())


def test_one_cent_control_difference_blocks() -> None:
    current = snapshot()
    changed = replace(current.controls[0], actual_cents=current.controls[0].expected_cents + 1)
    current = replace(current, controls=(changed,) + current.controls[1:])
    result = ConsolidationValidator(current).validate()
    assert "CONTROL_OUT_OF_TIE" in codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_missing_required_control_role_blocks() -> None:
    current = snapshot()
    current = replace(
        current,
        controls=tuple(
            item for item in current.controls if item.role != "investment_change_bridge"
        ),
    )
    assert "MISSING_REQUIRED_CONTROL" in codes(ConsolidationValidator(current).validate())


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("entity_keys", "DUPLICATE_ENTITY_KEY"),
        ("project_keys", "DUPLICATE_PROJECT_KEY"),
        ("account_keys", "DUPLICATE_ACCOUNT_KEY"),
    ],
)
def test_duplicate_population_keys_block(field: str, code: str) -> None:
    current = snapshot()
    first = getattr(current, field)[0]
    current = replace(current, **{field: getattr(current, field) + (first,)})
    assert code in codes(ConsolidationValidator(current).validate())


def test_unsupported_nonzero_manual_adjustment_blocks() -> None:
    current = replace(
        snapshot(),
        manual_adjustments=(ManualAdjustment("adj-1", "equity_rollforward", 25_00),),
    )
    assert "UNSUPPORTED_MANUAL_ADJUSTMENT" in codes(ConsolidationValidator(current).validate())


def test_supported_nonzero_adjustment_is_review_not_mechanical_error() -> None:
    current = replace(
        snapshot(),
        manual_adjustments=(
            ManualAdjustment(
                "adj-1",
                "equity_rollforward",
                25_00,
                support_reference="fictional://support-1",
                approval_reference="fictional://approval-1",
            ),
        ),
    )
    result = ConsolidationValidator(current).validate()
    assert "MANUAL_ADJUSTMENT_REQUIRES_REVIEW" in codes(result)
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.posting_actions == ()


def test_prior_comparator_must_be_immediately_preceding_month() -> None:
    result = ConsolidationValidator(snapshot(), snapshot("2026-04")).validate()
    assert "PRIOR_PERIOD_MISMATCH" in codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_formula_changes_are_counted_and_review_gated() -> None:
    current = snapshot()
    prior = snapshot("2026-05")
    changed = replace(current.formulas[0], signature="SUM_DETAIL_REVISED")
    added = FormulaEvidence("new-control", "debt_and_covenants", "NEW_CONTROL", 0)
    current = replace(current, formulas=(changed,) + current.formulas[1:] + (added,))
    prior = replace(prior, formulas=prior.formulas[:-1])
    result = ConsolidationValidator(current, prior).validate()
    assert "FORMULA_POPULATION_CHANGED" in codes(result)
    assert result.formula_added_count == 2
    assert result.formula_changed_count == 1
    assert result.mechanical_clean


def test_dependency_role_change_is_counted_and_review_gated() -> None:
    current = snapshot()
    prior = snapshot("2026-05")
    current = replace(
        current,
        dependencies=current.dependencies
        + (DependencyEvidence("dep-debt", "debt_schedule", "2026-06", "fictional://debt"),),
    )
    result = ConsolidationValidator(current, prior).validate()
    assert "DEPENDENCY_SET_CHANGED" in codes(result)
    assert result.dependency_role_added_count == 1
    assert result.mechanical_clean


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("entity_keys", "ENTITY_POPULATION_CHANGED"),
        ("project_keys", "PROJECT_POPULATION_CHANGED"),
        ("account_keys", "ACCOUNT_POPULATION_CHANGED"),
    ],
)
def test_population_changes_are_counted_and_review_gated(field: str, code: str) -> None:
    current = snapshot()
    prior = snapshot("2026-05")
    current = replace(current, **{field: getattr(current, field) + ("NEW-FICTIONAL-KEY",)})
    result = ConsolidationValidator(current, prior).validate()
    assert code in codes(result)
    assert getattr(result, field.removesuffix("_keys") + "_added_count") == 1
    assert result.mechanical_clean


def test_input_snapshots_are_not_mutated() -> None:
    current = snapshot()
    prior = snapshot("2026-05")
    before = (current, prior)
    result = ConsolidationValidator(current, prior).validate()
    assert (current, prior) == before
    assert result.journal_entries == ()
    assert result.import_payloads == ()
    assert result.posting_actions == ()
    assert result.submissions == ()
