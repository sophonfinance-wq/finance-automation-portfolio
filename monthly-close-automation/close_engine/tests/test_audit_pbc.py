"""Controls for the fictional validation-only audit/PBC component."""

from dataclasses import replace

import pytest

from close_engine.audit_pbc import (
    AuditPbcValidator,
    ContinuityLine,
    DependencyEvidence,
    DisplayedCheck,
    LeadLine,
    PackageRole,
    REQUIRED_ROLES,
    demo_package,
)


CURRENT_PERIOD = "2026-06"
PRIOR_PERIOD = "2025-06"


def run(
    roles=None,
    current=None,
    prior=None,
    continuity=None,
    checks=None,
    dependencies=(),
):
    demo_roles, demo_current, demo_prior, demo_continuity, demo_checks = demo_package()
    return AuditPbcValidator(
        CURRENT_PERIOD,
        PRIOR_PERIOD,
        demo_roles if roles is None else roles,
        demo_current if current is None else current,
        demo_prior if prior is None else prior,
        demo_continuity if continuity is None else continuity,
        demo_checks if checks is None else checks,
        dependencies,
    ).run()


def codes(result):
    return {finding.code for finding in result.findings}


def test_clean_package_rederives_all_controls_and_never_posts():
    result = run()
    assert result.mechanical_clean
    assert result.verdict == "READY FOR HUMAN REVIEW"
    assert result.validation_only
    assert not result.posting_authorized
    assert result.current_line_count == result.prior_line_count == 2
    assert result.shared_line_count == 2
    assert result.added_line_count == result.removed_line_count == 0
    assert result.continuity_failure_count == 0
    assert result.displayed_check_failure_count == 0
    assert "controlled audit trial balance" in " | ".join(result.manual_gates)
    assert result.journal_entries == result.posting_actions == result.import_payloads == ()


@pytest.mark.parametrize("period", ["2026-6", "06-2026", "2026-00", "2026-13", " 2026-06", ""])
def test_current_period_must_be_canonical(period):
    roles, current, prior, continuity, checks = demo_package()
    with pytest.raises(ValueError, match="current_period must be canonical YYYY-MM"):
        AuditPbcValidator(period, PRIOR_PERIOD, roles, current, prior, continuity, checks)


@pytest.mark.parametrize("period", ["2025-6", "06-2025", "2025-00", "2025-13", ""])
def test_prior_period_must_be_canonical(period):
    roles, current, prior, continuity, checks = demo_package()
    with pytest.raises(ValueError, match="prior_period must be canonical YYYY-MM"):
        AuditPbcValidator(CURRENT_PERIOD, period, roles, current, prior, continuity, checks)


@pytest.mark.parametrize("period", ["2026-06", "2027-06"])
def test_prior_period_must_precede_current(period):
    roles, current, prior, continuity, checks = demo_package()
    with pytest.raises(ValueError, match="prior_period must precede"):
        AuditPbcValidator(CURRENT_PERIOD, period, roles, current, prior, continuity, checks)


def test_required_roles_must_be_complete_and_unique():
    roles, *_ = demo_package()
    result = run(roles=roles[:-1] + (roles[0],))
    assert {"REQUIRED_ROLE_MISSING", "ROLE_DUPLICATE"} <= codes(result)


def test_unknown_role_and_bad_label_are_rejected():
    roles, *_ = demo_package()
    changed = roles + (
        PackageRole("not_a_role", "Unsupported"),
        PackageRole(next(iter(REQUIRED_ROLES)), " bad label"),
    )
    result = run(roles=changed)
    assert {"ROLE_INVALID", "ROLE_LABEL_INVALID", "ROLE_DUPLICATE"} <= codes(result)


def test_current_final_equation_is_independently_readded():
    _, current, *_ = demo_package()
    changed = (replace(current[0], final_cents=1_250_001), current[1])
    assert "CURRENT_FINAL_EQUATION_OUT_OF_TIE" in codes(run(current=changed))


def test_prior_final_equation_is_independently_readded():
    _, _, prior, *_ = demo_package()
    changed = (replace(prior[0], final_cents=1_100_001), prior[1])
    assert "PRIOR_FINAL_EQUATION_OUT_OF_TIE" in codes(run(prior=changed))


def test_current_and_prior_change_equations_are_readded():
    _, current, prior, *_ = demo_package()
    current_changed = (replace(current[0], change_cents=149_999), current[1])
    prior_changed = (replace(prior[0], change_cents=99_999), prior[1])
    result = run(current=current_changed, prior=prior_changed)
    assert {
        "CURRENT_CHANGE_EQUATION_OUT_OF_TIE",
        "PRIOR_CHANGE_EQUATION_OUT_OF_TIE",
    } <= codes(result)


def test_current_prior_must_equal_prior_final():
    _, current, *_ = demo_package()
    changed = (replace(current[0], prior_cents=1_099_999, change_cents=150_001), current[1])
    result = run(current=changed)
    assert "PRIOR_FINAL_CURRENT_PRIOR_OUT_OF_TIE" in codes(result)
    assert result.continuity_failure_count == 1


def test_population_change_is_review_gated_and_counted():
    _, current, *_ = demo_package()
    changed = (replace(current[0], account="AST-101"), current[1])
    result = run(current=changed)
    assert "ACCOUNT_POPULATION_CHANGED" in codes(result)
    assert result.added_line_count == result.removed_line_count == 1
    assert any(f.severity == "REVIEW" for f in result.findings if f.code == "ACCOUNT_POPULATION_CHANGED")


@pytest.mark.parametrize("which", ["current", "prior"])
def test_duplicate_schedule_account_keys_are_blocked_case_insensitively(which):
    _, current, prior, *_ = demo_package()
    source = list(current if which == "current" else prior)
    source[1] = replace(
        source[1],
        schedule=source[0].schedule.lower(),
        account=source[0].account.lower(),
    )
    result = run(current=source) if which == "current" else run(prior=source)
    assert f"{which.upper()}_LINE_DUPLICATE" in codes(result)


@pytest.mark.parametrize("value", [1.5, True, "100", None, float("nan"), float("inf")])
def test_unsafe_leadsheet_amounts_are_rejected_without_coercion(value):
    _, current, *_ = demo_package()
    changed = (replace(current[0], adjustment_cents=value), current[1])
    assert "CURRENT_AMOUNT_INVALID" in codes(run(current=changed))


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schedule", " Cash Leadsheet", "CURRENT_SCHEDULE_INVALID"),
        ("account", "cash", "CURRENT_ACCOUNT_INVALID"),
        ("description", "", "CURRENT_DESCRIPTION_INVALID"),
    ],
)
def test_leadsheet_identifiers_are_strict(field, value, expected):
    _, current, *_ = demo_package()
    changed = (replace(current[0], **{field: value}), current[1])
    assert expected in codes(run(current=changed))


def test_nonzero_adjustment_is_review_gated_and_never_drafted():
    _, current, *_ = demo_package()
    changed = (
        replace(
            current[0],
            adjustment_cents=12_500,
            final_cents=1_262_500,
            change_cents=162_500,
        ),
        current[1],
    )
    result = run(current=changed)
    assert "CURRENT_ADJUSTMENT_REVIEW_REQUIRED" in codes(result)
    assert result.journal_entries == ()


def test_continuity_opening_plus_movements_must_equal_ending():
    line = ContinuityLine("Debt Continuity", "Demo Facility", 500_000, (100_000, -75_000), 525_001)
    result = run(continuity=(line,))
    assert "CONTINUITY_OUT_OF_TIE" in codes(result)
    assert result.continuity_failure_count == 1


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (ContinuityLine(" Debt", "Demo", 0, (), 0), "CONTINUITY_IDENTIFIER_INVALID"),
        (ContinuityLine("Debt", "Demo", True, (), 0), "CONTINUITY_AMOUNT_INVALID"),
        (ContinuityLine("Debt", "Demo", 0, [1], 1), "CONTINUITY_MOVEMENTS_INVALID"),
        (ContinuityLine("Debt", "Demo", 0, (1.0,), 1), "CONTINUITY_MOVEMENTS_INVALID"),
    ],
)
def test_continuity_structure_is_fail_closed(line, expected):
    assert expected in codes(run(continuity=(line,)))


def test_duplicate_continuity_keys_are_blocked_case_insensitively():
    first = ContinuityLine("Debt", "Facility", 0, (), 0)
    second = ContinuityLine("debt", "facility", 0, (), 0)
    assert "CONTINUITY_LINE_DUPLICATE" in codes(run(continuity=(first, second)))


def test_nonzero_displayed_check_blocks_release():
    result = run(checks=(DisplayedCheck("Cash Flow Proof", "Final Proof", 1),))
    assert "DISPLAYED_CHECK_FAILED" in codes(result)
    assert result.displayed_check_failure_count == 1
    assert result.verdict == "NEEDS REVIEW"


@pytest.mark.parametrize("value", [1.5, True, "0", None])
def test_displayed_check_amount_must_be_integer_cents(value):
    result = run(checks=(DisplayedCheck("Cash Flow Proof", "Final Proof", value),))
    assert "DISPLAYED_CHECK_AMOUNT_INVALID" in codes(result)


def test_displayed_check_keys_are_clean_and_unique():
    checks = (
        DisplayedCheck("Cash Flow Proof", "Proof", 0),
        DisplayedCheck("cash flow proof", "proof", 0),
        DisplayedCheck(" Cash Flow Proof", "Other", 0),
    )
    result = run(checks=checks)
    assert {"DISPLAYED_CHECK_DUPLICATE", "DISPLAYED_CHECK_IDENTIFIER_INVALID"} <= codes(result)


@pytest.mark.parametrize(
    ("reference", "cached", "authoritative", "expected", "severity"),
    [
        ("'[Source.xlsx]TB'!A1", 0, True, "DEPENDENCY_EXTERNAL_OR_BROKEN", "ERROR"),
        ("'TB'!#REF!", 0, True, "DEPENDENCY_EXTERNAL_OR_BROKEN", "ERROR"),
        ("https://example.invalid/source", 0, True, "DEPENDENCY_EXTERNAL_OR_BROKEN", "ERROR"),
        ("'TB'!A1", "#VALUE!", True, "DEPENDENCY_CACHED_ERROR", "ERROR"),
        ("'Old'!#REF!", "#REF!", False, "STALE_DEPENDENCY_EXTERNAL_OR_BROKEN", "REVIEW"),
    ],
)
def test_dependency_failures_are_named_and_scope_sensitive(reference, cached, authoritative, expected, severity):
    dependency = DependencyEvidence("PBC Schedule", "Source Tie", reference, cached, authoritative)
    result = run(dependencies=(dependency,))
    finding = next(item for item in result.findings if item.code == expected)
    assert finding.severity == severity


def test_dependency_identifiers_scope_and_reference_fail_closed():
    dependencies = (
        DependencyEvidence(" PBC", "Tie", "'TB'!A1"),
        DependencyEvidence("PBC", "Tie", "'TB'!A1", authoritative="yes"),
        DependencyEvidence("PBC", "Tie", " 'TB'!A1"),
    )
    result = run(dependencies=dependencies)
    assert {
        "DEPENDENCY_IDENTIFIER_INVALID",
        "DEPENDENCY_SCOPE_INVALID",
        "DEPENDENCY_REFERENCE_INVALID",
    } <= codes(result)


def test_empty_current_and_prior_are_not_clean_noops():
    result = run(current=(), prior=())
    assert {"CURRENT_LEADSHEET_EMPTY", "PRIOR_LEADSHEET_EMPTY"} <= codes(result)


def test_validator_does_not_mutate_input_sequences():
    roles, current, prior, continuity, checks = demo_package()
    inputs = tuple(map(list, (roles, current, prior, continuity, checks)))
    before = tuple(tuple(items) for items in inputs)
    AuditPbcValidator(CURRENT_PERIOD, PRIOR_PERIOD, *inputs).run()
    assert tuple(tuple(items) for items in inputs) == before
