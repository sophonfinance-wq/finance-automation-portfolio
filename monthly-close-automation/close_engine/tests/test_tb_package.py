from __future__ import annotations

from dataclasses import replace

import pytest

from close_engine.tb_package import (
    REQUIRED_CONTROL_IDS,
    REQUIRED_ROLES,
    AdjustmentEvidence,
    ControlEvidence,
    DependencyEvidence,
    FormulaEvidence,
    PackageRole,
    TBPackageSnapshot,
    TBPackageValidator,
)


def snapshot(period: str = "2026-06") -> TBPackageSnapshot:
    return TBPackageSnapshot(
        period=period,
        roles=tuple(PackageRole(role, period) for role in sorted(REQUIRED_ROLES)),
        formulas=(
            FormulaEvidence("summary-total", "consolidated_summary", "SUM_DETAIL", 5_000_00),
            FormulaEvidence("support-tie", "service_entities", "SUPPORT_TIE", 0),
            FormulaEvidence(
                "operations-link",
                "consolidated_summary",
                "EXTERNAL_OPERATIONS_VALUE",
                2_000_00,
                external_dependency_id="dep-operations",
            ),
        ),
        dependencies=(
            DependencyEvidence(
                "dep-operations",
                "operations_package",
                period,
                "fictional://operations-package",
            ),
        ),
        controls=tuple(ControlEvidence(control_id, 0, 0) for control_id in sorted(REQUIRED_CONTROL_IDS)),
        entity_keys=("ENTITY-ALPHA", "ENTITY-BETA"),
        account_keys=("ACCOUNT-FEES", "ACCOUNT-ADMIN"),
        row_keys=("ROW-PROJECT-ONE", "ROW-OFFICE-COSTS"),
    )


def codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def test_clean_package_is_validation_only_and_ready_for_human_review() -> None:
    result = TBPackageValidator(snapshot()).validate()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.role_count == 8
    assert result.formula_count == 3
    assert result.external_formula_count == 1
    assert result.dependency_count == 1
    assert result.control_count == 9
    assert result.journal_entries == ()
    assert result.import_payloads == ()
    assert result.posting_actions == ()


def test_missing_and_duplicate_roles_block() -> None:
    current = snapshot()
    missing = replace(current, roles=current.roles[:-1])
    duplicate = replace(current, roles=current.roles + (current.roles[0],))
    assert "MISSING_ROLE" in codes(TBPackageValidator(missing).validate())
    assert "DUPLICATE_ROLE" in codes(TBPackageValidator(duplicate).validate())


def test_unknown_role_and_role_period_mismatch_block() -> None:
    current = snapshot()
    unknown = replace(current, roles=current.roles + (PackageRole("mystery", current.period),))
    changed = replace(current.roles[0], period="2026-05")
    mismatch = replace(current, roles=(changed,) + current.roles[1:])
    assert "UNKNOWN_ROLE" in codes(TBPackageValidator(unknown).validate())
    assert "ROLE_PERIOD_MISMATCH" in codes(TBPackageValidator(mismatch).validate())


@pytest.mark.parametrize("period", ["2026-6", "June 2026", "", "2026-13"])
def test_invalid_current_period_is_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="canonical YYYY-MM"):
        TBPackageValidator(replace(snapshot(), period=period))


@pytest.mark.parametrize("unsafe", [None, 1.25, True, "100", "#REF!"])
def test_unsafe_formula_cache_blocks(unsafe: object) -> None:
    current = snapshot()
    changed = replace(current.formulas[0], cached_cents=unsafe)
    current = replace(current, formulas=(changed,) + current.formulas[1:])
    assert "FORMULA_CACHE_MISSING_OR_UNSAFE" in codes(TBPackageValidator(current).validate())


def test_formula_error_and_missing_external_dependency_block() -> None:
    current = snapshot()
    broken = replace(current.formulas[0], signature="SUM_DETAIL+#VALUE!")
    missing = replace(current.formulas[2], external_dependency_id="missing")
    current = replace(current, formulas=(broken, current.formulas[1], missing))
    observed = codes(TBPackageValidator(current).validate())
    assert "FORMULA_ERROR_TOKEN" in observed
    assert "FORMULA_DEPENDENCY_MISSING" in observed


def test_dependency_role_period_reference_and_count_are_controlled() -> None:
    current = snapshot()
    item = current.dependencies[0]
    unknown = replace(current, dependencies=(replace(item, role="unapproved"),))
    stale = replace(current, dependencies=(replace(item, period="2026-05"),))
    broken = replace(current, dependencies=(replace(item, reference="#REF!"),))
    missing = replace(current, dependencies=())
    assert "UNKNOWN_DEPENDENCY_ROLE" in codes(TBPackageValidator(unknown).validate())
    assert "DEPENDENCY_PERIOD_MISMATCH" in codes(TBPackageValidator(stale).validate())
    assert "UNSAFE_DEPENDENCY_REFERENCE" in codes(TBPackageValidator(broken).validate())
    assert "OPERATIONS_DEPENDENCY_COUNT" in codes(TBPackageValidator(missing).validate())


@pytest.mark.parametrize("unsafe", [None, 1.5, True, "0"])
def test_unsafe_control_amount_blocks(unsafe: object) -> None:
    current = snapshot()
    changed = replace(current.controls[0], actual_cents=unsafe)
    current = replace(current, controls=(changed,) + current.controls[1:])
    assert "UNSAFE_CONTROL_AMOUNT" in codes(TBPackageValidator(current).validate())


def test_control_difference_and_missing_control_block() -> None:
    current = snapshot()
    changed = replace(current.controls[0], actual_cents=1)
    out = replace(current, controls=(changed,) + current.controls[1:])
    missing = replace(current, controls=current.controls[1:])
    assert "CONTROL_OUT_OF_TIE" in codes(TBPackageValidator(out).validate())
    assert "MISSING_REQUIRED_CONTROL" in codes(TBPackageValidator(missing).validate())


def test_manual_adjustment_requires_support_and_approval() -> None:
    current = replace(
        snapshot(),
        adjustments=(AdjustmentEvidence("adj-1", "capital_entities", 25_00, False),),
    )
    result = TBPackageValidator(current).validate()
    assert "UNSUPPORTED_MANUAL_ADJUSTMENT" in codes(result)
    assert result.verdict == "NEEDS REVIEW"


def test_supported_adjustment_remains_warning_and_creates_no_action() -> None:
    current = replace(
        snapshot(),
        adjustments=(
            AdjustmentEvidence(
                "adj-1",
                "capital_entities",
                25_00,
                False,
                "fictional://support",
                "fictional://approval",
            ),
        ),
    )
    result = TBPackageValidator(current).validate()
    assert "ADJUSTMENT_REQUIRES_HUMAN_REVIEW" in codes(result)
    assert result.mechanical_clean
    assert result.journal_entries == ()
    assert result.posting_actions == ()


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("entity_keys", "DUPLICATE_ENTITY_KEY"),
        ("account_keys", "DUPLICATE_ACCOUNT_KEY"),
        ("row_keys", "DUPLICATE_ROW_KEY"),
    ],
)
def test_duplicate_population_keys_block(field: str, code: str) -> None:
    current = snapshot()
    current = replace(current, **{field: getattr(current, field) + (getattr(current, field)[0],)})
    assert code in codes(TBPackageValidator(current).validate())


def test_prior_must_be_immediately_preceding_month_including_year_boundary() -> None:
    assert "PRIOR_PERIOD_MISMATCH" in codes(
        TBPackageValidator(snapshot(), snapshot("2026-04")).validate()
    )
    january = snapshot("2027-01")
    december = snapshot("2026-12")
    assert "PRIOR_PERIOD_MISMATCH" not in codes(TBPackageValidator(january, december).validate())


def test_current_prior_structural_changes_are_visible_warnings() -> None:
    current = snapshot()
    prior = replace(
        snapshot("2026-05"),
        formulas=(replace(current.formulas[0], signature="OLD_SUM"),) + current.formulas[1:-1],
        entity_keys=("ENTITY-ALPHA", "ENTITY-OLD"),
        account_keys=("ACCOUNT-FEES",),
        row_keys=("ROW-PROJECT-ONE",),
    )
    result = TBPackageValidator(current, prior).validate()
    observed = codes(result)
    assert "FORMULA_POPULATION_CHANGED" in observed
    assert "ENTITY_POPULATION_CHANGED" in observed
    assert "ACCOUNT_POPULATION_CHANGED" in observed
    assert "ROW_POPULATION_CHANGED" in observed
    assert result.formula_added_count == 1
    assert result.formula_changed_count == 1
    assert result.entity_added_count == 1
    assert result.entity_removed_count == 1
    assert result.account_added_count == 1
    assert result.row_added_count == 1
    assert result.mechanical_clean
