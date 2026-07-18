from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.group_operations import (
    CONTROL_TOLERANCES_CENTS,
    REQUIRED_DEPENDENCY_ROLES,
    REQUIRED_ROLES,
    ControlEvidence,
    DependencyEvidence,
    FormulaEvidence,
    GroupOperationsSnapshot,
    GroupOperationsValidator,
    ManualAdjustmentEvidence,
    PackageRole,
)


def snapshot(period: str = "2026-06") -> GroupOperationsSnapshot:
    dependencies = tuple(
        DependencyEvidence(
            f"dep-{role}",
            role,
            period,
            f"fictional://{role}",
        )
        for role in sorted(REQUIRED_DEPENDENCY_ROLES)
    )
    return GroupOperationsSnapshot(
        period=period,
        roles=tuple(PackageRole(role, period) for role in sorted(REQUIRED_ROLES)),
        formulas=(
            FormulaEvidence("summary-total", "executive_summary", "SUM_REGIONS", 8_000_00),
            FormulaEvidence("regional-crossfoot", "regional_summary_a", "SUM_MONTHS", 2_000_00),
            FormulaEvidence(
                "trial-balance-link",
                "executive_summary",
                "EXTERNAL_SOURCE_VALUE",
                3_000_00,
                external_dependency_id="dep-trial_balance_package",
            ),
        ),
        dependencies=dependencies,
        controls=tuple(
            ControlEvidence(control_id, 0)
            for control_id in sorted(CONTROL_TOLERANCES_CENTS)
        ),
        label_keys=("REPORTING-LINE-A", "REPORTING-LINE-B"),
    )


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def test_clean_package_is_validation_only_and_ready_for_human_review() -> None:
    result = GroupOperationsValidator(snapshot()).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.role_count == 16
    assert result.formula_count == 3
    assert result.external_formula_count == 1
    assert result.dependency_count == 3
    assert result.control_count == 10
    assert result.journal_entries == ()
    assert result.import_payloads == ()
    assert result.posting_actions == ()


def test_missing_duplicate_and_unknown_roles_block() -> None:
    current = snapshot()
    missing = replace(current, roles=current.roles[:-1])
    duplicate = replace(current, roles=current.roles + (current.roles[0],))
    unknown = replace(current, roles=current.roles + (PackageRole("mystery", current.period),))
    assert "MISSING_ROLE" in codes(GroupOperationsValidator(missing).validate())
    assert "DUPLICATE_ROLE" in codes(GroupOperationsValidator(duplicate).validate())
    assert "UNKNOWN_ROLE" in codes(GroupOperationsValidator(unknown).validate())


def test_role_period_mismatch_blocks() -> None:
    current = snapshot()
    changed = replace(current.roles[0], period="2026-05")
    current = replace(current, roles=(changed,) + current.roles[1:])
    assert "ROLE_PERIOD_MISMATCH" in codes(GroupOperationsValidator(current).validate())


@pytest.mark.parametrize("period", ["2026-6", "June 2026", "", "2026-13"])
def test_invalid_current_period_is_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        GroupOperationsValidator(replace(snapshot(), period=period))


def test_required_dependency_roles_are_exactly_one() -> None:
    current = snapshot()
    missing = replace(current, dependencies=current.dependencies[1:])
    duplicate = replace(current, dependencies=current.dependencies + (current.dependencies[0],))
    assert "REQUIRED_DEPENDENCY_COUNT" in codes(GroupOperationsValidator(missing).validate())
    observed = codes(GroupOperationsValidator(duplicate).validate())
    assert "REQUIRED_DEPENDENCY_COUNT" in observed
    assert "DUPLICATE_DEPENDENCY_ID" in observed


def test_optional_dependency_is_current_and_may_appear_once() -> None:
    current = snapshot()
    optional = DependencyEvidence("dep-plan", "business_plan", current.period, "fictional://plan")
    clean = replace(current, dependencies=current.dependencies + (optional,))
    assert "OPTIONAL_DEPENDENCY_COUNT" not in codes(GroupOperationsValidator(clean).validate())
    duplicate = replace(clean, dependencies=clean.dependencies + (replace(optional, dependency_id="dep-plan-2"),))
    assert "OPTIONAL_DEPENDENCY_COUNT" in codes(GroupOperationsValidator(duplicate).validate())


def test_dependency_role_period_and_reference_are_controlled() -> None:
    current = snapshot()
    item = current.dependencies[0]
    unknown = replace(current, dependencies=(replace(item, role="unapproved"),) + current.dependencies[1:])
    stale = replace(current, dependencies=(replace(item, period="2026-05"),) + current.dependencies[1:])
    broken = replace(current, dependencies=(replace(item, reference="#REF!"),) + current.dependencies[1:])
    assert "UNKNOWN_DEPENDENCY_ROLE" in codes(GroupOperationsValidator(unknown).validate())
    assert "DEPENDENCY_PERIOD_MISMATCH" in codes(GroupOperationsValidator(stale).validate())
    assert "UNSAFE_DEPENDENCY_REFERENCE" in codes(GroupOperationsValidator(broken).validate())


@pytest.mark.parametrize("unsafe", [None, 1.25, True, "100", "#VALUE!"])
def test_unsafe_formula_cache_blocks(unsafe: object) -> None:
    current = snapshot()
    changed = replace(current.formulas[0], cached_cents=unsafe)
    current = replace(current, formulas=(changed,) + current.formulas[1:])
    assert "FORMULA_CACHE_MISSING_OR_UNSAFE" in codes(GroupOperationsValidator(current).validate())


def test_formula_error_and_missing_dependency_block() -> None:
    current = snapshot()
    broken = replace(current.formulas[0], signature="SUM_REGIONS+#REF!")
    missing = replace(current.formulas[2], external_dependency_id="missing")
    current = replace(current, formulas=(broken, current.formulas[1], missing))
    observed = codes(GroupOperationsValidator(current).validate())
    assert "FORMULA_ERROR_TOKEN" in observed
    assert "FORMULA_DEPENDENCY_MISSING" in observed


def test_embedded_formula_amount_is_visible_warning() -> None:
    current = snapshot()
    changed = replace(current.formulas[0], contains_embedded_amount=True)
    current = replace(current, formulas=(changed,) + current.formulas[1:])
    result = GroupOperationsValidator(current).validate()
    assert "EMBEDDED_AMOUNT_REQUIRES_REVIEW" in codes(result)
    assert result.embedded_amount_formula_count == 1
    assert result.mechanical_clean


@pytest.mark.parametrize("control_id", sorted(CONTROL_TOLERANCES_CENTS))
def test_each_control_accepts_its_disclosed_boundary(control_id: str) -> None:
    current = snapshot()
    changed = tuple(
        replace(item, difference_cents=CONTROL_TOLERANCES_CENTS[control_id])
        if item.control_id == control_id else item
        for item in current.controls
    )
    result = GroupOperationsValidator(replace(current, controls=changed)).validate()
    assert "CONTROL_OUT_OF_TOLERANCE" not in codes(result)


def test_control_outside_boundary_and_missing_control_block() -> None:
    current = snapshot()
    first = current.controls[0]
    changed = replace(first, difference_cents=CONTROL_TOLERANCES_CENTS[first.control_id] + 1)
    out = replace(current, controls=(changed,) + current.controls[1:])
    missing = replace(current, controls=current.controls[1:])
    assert "CONTROL_OUT_OF_TOLERANCE" in codes(GroupOperationsValidator(out).validate())
    assert "MISSING_REQUIRED_CONTROL" in codes(GroupOperationsValidator(missing).validate())


@pytest.mark.parametrize("unsafe", [None, 1.5, True, "0"])
def test_unsafe_control_amount_blocks(unsafe: object) -> None:
    current = snapshot()
    changed = replace(current.controls[0], difference_cents=unsafe)
    current = replace(current, controls=(changed,) + current.controls[1:])
    assert "UNSAFE_CONTROL_AMOUNT" in codes(GroupOperationsValidator(current).validate())


def test_manual_adjustment_requires_support_and_approval() -> None:
    current = replace(
        snapshot(),
        manual_adjustments=(ManualAdjustmentEvidence("adj-1", "company_summary", 25_00),),
    )
    result = GroupOperationsValidator(current).validate()
    assert "UNSUPPORTED_MANUAL_ADJUSTMENT" in codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_supported_manual_adjustment_remains_warning_and_creates_no_action() -> None:
    current = replace(
        snapshot(),
        manual_adjustments=(
            ManualAdjustmentEvidence(
                "adj-1",
                "company_summary",
                25_00,
                "fictional://support",
                "fictional://approval",
            ),
        ),
    )
    result = GroupOperationsValidator(current).validate()
    assert "MANUAL_ADJUSTMENT_REQUIRES_REVIEW" in codes(result)
    assert result.mechanical_clean
    assert result.journal_entries == ()
    assert result.posting_actions == ()


def test_duplicate_and_untrimmed_labels_block() -> None:
    current = snapshot()
    duplicate = replace(current, label_keys=current.label_keys + (current.label_keys[0],))
    untrimmed = replace(current, label_keys=(" BAD",))
    assert "DUPLICATE_LABEL_KEY" in codes(GroupOperationsValidator(duplicate).validate())
    assert "UNSAFE_LABEL_KEY" in codes(GroupOperationsValidator(untrimmed).validate())


def test_prior_must_be_immediately_preceding_month_including_year_boundary() -> None:
    assert "PRIOR_PERIOD_MISMATCH" in codes(
        GroupOperationsValidator(snapshot(), snapshot("2026-04")).validate()
    )
    assert "PRIOR_PERIOD_MISMATCH" not in codes(
        GroupOperationsValidator(snapshot("2027-01"), snapshot("2026-12")).validate()
    )


def test_current_prior_structural_changes_are_visible_warnings() -> None:
    current = snapshot()
    prior = replace(
        snapshot("2026-05"),
        formulas=(replace(current.formulas[0], signature="OLD_SUM"),) + current.formulas[1:-1],
        dependencies=current.dependencies + (
            DependencyEvidence("dep-plan", "business_plan", "2026-05", "fictional://plan"),
        ),
        label_keys=("REPORTING-LINE-A", "REPORTING-LINE-OLD"),
    )
    result = GroupOperationsValidator(current, prior).validate()
    observed = codes(result)
    assert "FORMULA_POPULATION_CHANGED" in observed
    assert "DEPENDENCY_POPULATION_CHANGED" in observed
    assert "LABEL_POPULATION_CHANGED" in observed
    assert result.formula_added_count == 1
    assert result.formula_changed_count == 1
    assert result.dependency_removed_count == 1
    assert result.label_added_count == 1
    assert result.label_removed_count == 1
    assert result.mechanical_clean
