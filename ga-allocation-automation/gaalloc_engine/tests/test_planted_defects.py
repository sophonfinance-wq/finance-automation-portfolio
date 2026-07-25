"""Every planted defect must trip the control it was built to trip.

This is the suite that proves the registry is awake. A control with no planted
defect is a control nobody has ever seen fire, and a defect that fires nothing is
a control asleep at exactly the moment it was needed.
"""

from __future__ import annotations

import pytest

from gaalloc_engine.engine import REGISTRY
from gaalloc_engine.generate import DEFECTS
from gaalloc_engine.model import DocumentReport, Status, Verdict

from .conftest import defect_names

#: Controls a defect is additionally allowed to trip, beyond the one it targets.
#: A malformed amount is read by every control that reads that field, and
#: reporting it in each of them is the contract -- see
#: ``test_amount_invalid_is_contained_to_its_row``, which asserts the companion
#: property: that one bad value does not abort the rest of the file. Every other
#: defect is held to exactly one control.
ALSO_EXPECTED: dict[str, set[str]] = {
    "amount_not_integer": {"alc_amounts_rederive"},
}


@pytest.mark.parametrize("name", defect_names())
def test_defect_fires_its_intended_rule(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """The rule the defect was designed for produces a non-PASS finding."""
    intended, _mutation = DEFECTS[name]
    report = by_defect[name]
    assert intended in report.rules_fired(), (
        f"planted defect {name!r} did not trip {intended!r}; "
        f"rules that did fire: {report.rules_fired()}"
    )


@pytest.mark.parametrize("name", defect_names())
def test_defect_package_is_not_clean(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """An allocation file carrying a planted defect never rolls up to PASS."""
    assert by_defect[name].verdict is not Verdict.PASS


@pytest.mark.parametrize("name", defect_names())
def test_defect_is_contained_to_its_own_control(
    name: str, by_defect: dict[str, DocumentReport]
) -> None:
    """One planted break trips one control, not a cascade down the registry.

    Containment is what makes the corpus a teaching artifact rather than a pile
    of noise: each file demonstrates exactly one failure mode. It is also the
    property that keeps the guard comments honest -- a control that reports a gap
    another control already owns would show up here.
    """
    intended, _mutation = DEFECTS[name]
    allowed = {intended} | ALSO_EXPECTED.get(name, set())
    fired = set(by_defect[name].rules_fired())
    assert fired == allowed, (
        f"planted defect {name!r} was designed to trip {sorted(allowed)}; "
        f"it tripped {sorted(fired)}"
    )


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

    Messages are the product here: a controller reading the report should learn
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
    """No control ships without a package that demonstrates it firing."""
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


def test_amount_invalid_is_reported_not_coerced(
    by_defect: dict[str, DocumentReport]
) -> None:
    """A non-integer amount surfaces as AMOUNT_INVALID rather than being rounded.

    Coercing the value would make the engine the author of the number it is meant
    to audit, so the contract is to report and move on.
    """
    report = by_defect["amount_not_integer"]
    messages = [f.message for f in report.findings if f.status is not Status.PASS]
    assert any("AMOUNT_INVALID" in m for m in messages), (
        f"no AMOUNT_INVALID finding; got {messages}"
    )
    assert any("never coerced" in m for m in messages)


def test_amount_invalid_is_contained_to_its_row(
    by_defect: dict[str, DocumentReport]
) -> None:
    """One malformed amount does not stop the rest of the file being read.

    A single bad allocated amount is read by more than one rule -- the pool
    tie-out and the per-recipient re-derivation -- and both must still report
    rather than aborting at the first bad value.
    """
    report = by_defect["amount_not_integer"]
    fired = report.rules_fired()
    assert "alc_amounts_tie_pool" in fired
    assert "alc_amounts_rederive" in fired


def test_the_flag_defect_is_the_only_review_verdict(
    by_defect: dict[str, DocumentReport]
) -> None:
    """The FLAG-severity control produces REVIEW, not FAIL.

    A review signal that rolled up to a hard failure would stop a close over a
    figure that is arithmetically correct, which is the opposite of what the
    severity is for.
    """
    assert by_defect["pool_step_change"].verdict is Verdict.REVIEW
