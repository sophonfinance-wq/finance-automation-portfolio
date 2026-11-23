"""Every planted defect must trip the control it was built to trip.

This is the suite that proves the registry is awake. A control with no planted
defect is a control nobody has ever seen fire, and a defect that fires nothing is
a control asleep at exactly the moment it was needed.
"""

from __future__ import annotations

import pytest

from workpaper_engine.engine import REGISTRY
from workpaper_engine.generate import DEFECTS
from workpaper_engine.model import DocumentReport, Status, Verdict

from .conftest import defect_names


@pytest.mark.parametrize("name", defect_names())
def test_defect_fires_its_intended_rule(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """The control the defect was designed for produces a non-PASS finding."""
    intended, _mutation = DEFECTS[name]
    report = by_defect[name]
    assert intended in report.rules_fired(), (
        f"planted defect {name!r} did not trip {intended!r}; "
        f"rules that did fire: {report.rules_fired()}"
    )


@pytest.mark.parametrize("name", defect_names())
def test_defect_build_is_not_clean(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """A build file carrying a planted defect never rolls up to PASS."""
    assert by_defect[name].verdict is not Verdict.PASS


@pytest.mark.parametrize("name", defect_names())
def test_defect_declares_itself(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """Each defect file is labelled, so a reader can tell what it demonstrates."""
    assert by_defect[name].document.startswith(name)


@pytest.mark.parametrize("name", defect_names())
def test_every_finding_carries_a_message(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """An exception with no explanation teaches nothing.

    Messages are the product here: a preparer reading the report should learn
    *why* the control exists, not merely that it failed.
    """
    for finding in by_defect[name].findings:
        assert finding.message.strip(), f"{finding.rule} produced an empty message"
        assert len(finding.message) > 20, (
            f"{finding.rule} message is too terse to be useful: {finding.message!r}"
        )


@pytest.mark.parametrize("name", defect_names())
def test_findings_carry_locations(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """Non-PASS findings point somewhere specific."""
    for finding in by_defect[name].findings:
        if finding.status is Status.PASS:
            continue
        assert finding.location and finding.location != "", (
            f"{finding.rule} fired with no location"
        )


def test_every_registered_rule_has_a_planted_defect() -> None:
    """No control ships without a build file that demonstrates it firing."""
    covered = {intended for intended, _m in DEFECTS.values()}
    registered = {rule_id for rule_id, _fn in REGISTRY}
    uncovered = sorted(registered - covered)
    assert not uncovered, f"controls with no planted defect: {uncovered}"


def test_no_defect_targets_an_unregistered_rule() -> None:
    """The corpus cannot claim to demonstrate a control that does not exist."""
    registered = {rule_id for rule_id, _fn in REGISTRY}
    for name, (intended, _m) in sorted(DEFECTS.items()):
        assert intended in registered, (
            f"defect {name!r} targets {intended!r}, which is not in the registry"
        )


def test_each_defect_is_confined_to_its_own_control(
    by_defect: dict[str, DocumentReport]
) -> None:
    """One planted break fires one control, so independence is demonstrated.

    A corpus in which a single defect trips three controls cannot prove that any
    of the three is independently violable. This engine's controls overlap by
    subject -- the frozen layers, the edit scope and the surviving labels all
    look at the same schedule -- so the isolation property is what shows each of
    them measures something the others do not.
    """
    for name, report in sorted(by_defect.items()):
        if name == "clean":
            continue
        intended, _mutation = DEFECTS[name]
        assert report.rules_fired() == [intended], (
            f"{name} fired {report.rules_fired()}, not just {intended!r}"
        )


def test_a_disclosed_difference_rolls_up_to_review(
    by_defect: dict[str, DocumentReport]
) -> None:
    """A difference the package discloses is a review signal, not a failure.

    Without this the middle rung of the verdict ladder is untested: flipping the
    FLAG branch of :meth:`DocumentReport.verdict` to FAIL would leave the rest of
    the suite green. The disclosed and undisclosed variants of the same break are
    both shipped, so the pair also proves the disclosure is what makes the
    difference rather than the amount.
    """
    disclosed = by_defect["equity_vs_bs_disclosed"]
    undisclosed = by_defect["equity_vs_bs_undisclosed"]
    assert disclosed.verdict is Verdict.REVIEW
    assert undisclosed.verdict is Verdict.FAIL
    assert [f.status for f in disclosed.findings if f.status is not Status.PASS] == [
        Status.FLAG
    ]


def test_amount_invalid_is_reported_not_coerced(
    by_defect: dict[str, DocumentReport]
) -> None:
    """A non-integer amount surfaces as AMOUNT_INVALID rather than being rounded.

    Coercing the value would make the engine the author of the number it is meant
    to prove, so the contract is to report and move on.
    """
    report = by_defect["amount_not_integer"]
    messages = [f.message for f in report.findings if f.status is not Status.PASS]
    assert any("AMOUNT_INVALID" in m for m in messages), (
        f"no AMOUNT_INVALID finding; got {messages}"
    )
    assert any("never coerced" in m for m in messages)


def test_amount_invalid_is_contained_to_its_cell(
    by_defect: dict[str, DocumentReport]
) -> None:
    """One malformed amount does not stop the rest of the package being proved.

    A fractional cent on one equity row is read by the flow control and by
    nothing else, and every other control in the registry still has to run and
    report -- so twenty-three of the twenty-four still hold.
    """
    report = by_defect["amount_not_integer"]
    assert report.rules_fired() == ["capital_flow_equals_delta"]
    passing = {f.rule for f in report.findings if f.status is Status.PASS}
    assert len(passing) == len(REGISTRY) - 1
