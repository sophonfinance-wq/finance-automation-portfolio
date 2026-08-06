"""The cleanly built package must satisfy every control, rule by rule.

Parametrized over the registry rather than asserted as one blanket PASS, so a
regression names the control that broke instead of reporting that "something" in
a 24-rule registry is unhappy.
"""

from __future__ import annotations

import pytest

from workpaper_engine.engine import REGISTRY, SEVERITY, analyze_document
from workpaper_engine.model import DocumentReport, Status, Verdict

RULE_IDS = [rule_id for rule_id, _fn in REGISTRY]


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_clean_build_passes_rule(rule_id: str, clean_report: DocumentReport) -> None:
    """Each control produces only PASS findings on the cleanly built package."""
    fired = [
        f for f in clean_report.findings
        if f.rule == rule_id and f.status is not Status.PASS
    ]
    assert not fired, (
        f"{rule_id} fired on the clean baseline: "
        + "; ".join(f"{f.status.value} @ {f.location}: {f.message}" for f in fired)
    )


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_every_rule_reports_something_on_the_clean_build(
    rule_id: str, clean_report: DocumentReport
) -> None:
    """A control that stays silent has not demonstrated that it ran.

    Every rule emits at least one finding -- a PASS when the control holds -- so
    the report distinguishes "checked and fine" from "never looked".
    """
    assert any(f.rule == rule_id for f in clean_report.findings), (
        f"{rule_id} produced no finding at all on the clean build file"
    )


def test_clean_build_verdict_is_pass(clean_report: DocumentReport) -> None:
    """The whole build file rolls up to PASS."""
    assert clean_report.verdict is Verdict.PASS


def test_clean_build_has_no_flags(clean_report: DocumentReport) -> None:
    """Not even a review flag: the baseline is meant to be unambiguously clean."""
    flags = [f for f in clean_report.findings if f.status is Status.FLAG]
    assert not flags, [f"{f.rule}: {f.message}" for f in flags]


def test_registry_ships_twenty_four_controls() -> None:
    """The engine claims twenty-four controls over the built package.

    Pinned rather than floored: the count is a published figure, and a rule that
    quietly failed to register would otherwise show up as a corpus that
    mysteriously passes.
    """
    assert len(REGISTRY) == 24


def test_registry_rule_ids_are_unique() -> None:
    """A duplicate id would make findings ambiguous and the report unstable."""
    assert len(RULE_IDS) == len(set(RULE_IDS))


def test_every_rule_declares_a_severity(clean_report: DocumentReport) -> None:
    """Severity is declared by running the rule, so this doubles as a smoke test.

    ``SEVERITY`` is populated as each check executes. After a full clean run every
    registered rule must have registered its severity -- a rule that returned
    early before declaring one would be invisible to
    :func:`~workpaper_engine.engine.amount_invalid_finding` and would silently
    default to FAIL.
    """
    for rule_id in RULE_IDS:
        assert rule_id in SEVERITY, f"{rule_id} never declared a severity"
        assert SEVERITY[rule_id] in (Status.FAIL, Status.FLAG)


def test_registry_order_is_stable(corpus, clean_report: DocumentReport) -> None:
    """Analyzing the same build file twice yields findings in the same order."""
    path = next(p for p in sorted(corpus.glob("*.json")) if p.stem.startswith("clean"))
    again = analyze_document(path)
    assert [f.to_dict() for f in again.findings] == [
        f.to_dict() for f in clean_report.findings
    ]
