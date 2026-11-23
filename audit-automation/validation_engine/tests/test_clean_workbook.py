"""The clean workbook must pass every rule with no FAIL and no FLAG."""

from __future__ import annotations

from validation_engine.engine import REGISTRY, Status, Verdict


def test_clean_workbook_passes(reports):
    """The clean baseline workbook yields verdict PASS."""
    clean = reports["clean"]
    bad = [f for f in clean.findings if f.status is not Status.PASS]
    assert not bad, f"clean workbook produced non-PASS findings: {[f.to_dict() for f in bad]}"
    assert clean.verdict is Verdict.PASS


def test_clean_workbook_exercises_every_rule(reports):
    """Every registry rule emits at least one finding on the clean workbook."""
    clean = reports["clean"]
    fired_rules = {f.rule for f in clean.findings}
    registry_rules = {rule_id for rule_id, _ in REGISTRY}
    assert registry_rules <= fired_rules


def test_only_target_rule_trips_on_each_defect(reports):
    """A defect workbook must not produce spurious FAILs from unrelated rules."""
    expected_fail_rule = {
        "hardcoded_total": "expected_formula",
        "unbalanced_tb": "debit_credit_balance",
        "json_mismatch": "json_tieout",
    }
    for key, rule in expected_fail_rule.items():
        fails = {f.rule for f in reports[key].findings if f.status is Status.FAIL}
        assert fails == {rule}, f"{key}: unexpected FAILs {fails}"
