"""Each planted defect must be caught by the control it was planted for.

The corpus carries one defect per control. A defect file proves its control
fires; the clean file (``test_clean_baseline``) proves the controls are quiet
otherwise. Together those two facts are what makes a PASS meaningful.

A mutation may legitimately disturb a second control -- moving one line in one
copy changes that copy's total as well as that copy's line -- so these tests
assert the targeted control fired, not that it fired alone.
"""

from __future__ import annotations

import pytest

from baseline_engine.generate import DEFECTS
from baseline_engine.model import DocumentReport, Status, Verdict

from .conftest import defect_names


@pytest.mark.parametrize("name", defect_names())
def test_defect_is_caught_by_its_control(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    rule, _mutator = DEFECTS[name]
    report = by_defect[name]
    fired = report.rules_fired()
    assert rule in fired, (
        f"defect {name!r} did not trip {rule!r}; fired instead: {fired}"
    )


@pytest.mark.parametrize("name", defect_names())
def test_defect_file_is_not_clean(name: str, by_defect: dict[str, DocumentReport]) -> None:
    assert by_defect[name].verdict is not Verdict.PASS


@pytest.mark.parametrize("name", defect_names())
def test_defect_finding_carries_a_location_and_reason(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """An exception must say where it is and why it matters, not merely that it is."""
    rule, _mutator = DEFECTS[name]
    hits = [
        f
        for f in by_defect[name].findings
        if f.rule == rule and f.status is not Status.PASS
    ]
    assert hits, f"no non-PASS finding for {rule!r}"
    for f in hits:
        assert f.location and f.location != "-", f"{rule} finding has no location"
        assert len(f.message) > 40, f"{rule} message is too thin to act on"


def test_every_control_has_a_planted_defect() -> None:
    """No control ships without a corpus file proving it fires."""
    from baseline_engine.engine import REGISTRY

    covered = {rule for rule, _m in DEFECTS.values()}
    registered = {rule_id for rule_id, _fn in REGISTRY}
    assert registered <= covered, f"controls with no planted defect: {registered - covered}"


def test_flag_only_defects_roll_up_to_review(by_defect: dict[str, DocumentReport]) -> None:
    """A review signal must not masquerade as a hard failure.

    ``summary_superseded`` and ``offsetting_reclass`` are the two defects whose
    every consequence is a FLAG. If either ever rolls up to FAIL, a reviewer is
    being told a judgement call is a breach.
    """
    for name in ("summary_superseded", "offsetting_reclass"):
        report = by_defect[name]
        assert report.verdict is Verdict.REVIEW, (
            f"{name} rolled up to {report.verdict.value}; "
            f"findings: {[(f.rule, f.status.value) for f in report.findings if f.status is not Status.PASS]}"
        )
