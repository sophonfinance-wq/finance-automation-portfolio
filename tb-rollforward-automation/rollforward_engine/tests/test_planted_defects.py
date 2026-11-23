"""Every planted defect must trip the control it was built to trip.

This is the suite that proves the registry is awake. A control with no planted
defect is a control nobody has ever seen fire, and a defect that fires nothing is
a control asleep at exactly the moment it was needed.
"""

from __future__ import annotations

import pytest

from rollforward_engine.engine import REGISTRY
from rollforward_engine.generate import DEFECTS
from rollforward_engine.model import DocumentReport, Status, Verdict

from .conftest import defect_names


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
    """A workpaper file carrying a planted defect never rolls up to PASS."""
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
    """No control ships without a file that demonstrates it firing."""
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


def test_flag_only_defects_roll_up_to_review(
    by_defect: dict[str, DocumentReport]
) -> None:
    """A review signal is not a failure, and the verdict has to say so.

    Both FLAG-severity controls ship a defect that fires nothing else, so the
    REVIEW rung of the verdict ladder is exercised rather than merely declared.
    Without this the ladder's middle rung is untested: flipping the FLAG branch
    of :meth:`DocumentReport.verdict` to FAIL leaves the rest of the suite green.
    """
    for name in ("short_first_period", "dormant_column_present"):
        assert by_defect[name].verdict is Verdict.REVIEW, (
            f"{name} rolled up to {by_defect[name].verdict.value}, not REVIEW"
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


def test_amount_invalid_is_contained_to_its_cell(
    by_defect: dict[str, DocumentReport]
) -> None:
    """One malformed amount does not stop the rest of the file being read.

    A single bad cell is read by several rules -- the tie to the extract, the
    column footing, the link resolution -- and each must still report rather
    than aborting the whole file at the first bad value.
    """
    report = by_defect["amount_not_integer"]
    fired = report.rules_fired()
    assert "map_values_exact" in fired
    assert len(fired) > 1, (
        "a malformed amount silenced every rule after the first; the guard is "
        "meant to contain the failure to its own cell"
    )


def test_activity_column_defect_names_the_real_cause(
    by_defect: dict[str, DocumentReport]
) -> None:
    """The signature defect is diagnosed, not merely detected.

    A column populated from the monthly-activity column still self-balances, so
    a footing check cannot see it. The basis control has to recognise the
    *pattern* -- every differing row equals the activity figure -- and say so,
    because a hundred unexplained cell breaks send a reviewer to the wrong
    place.
    """
    report = by_defect["activity_column_used"]
    assert "src_balance_basis" in report.rules_fired()
    message = next(
        f.message for f in report.findings
        if f.rule == "src_balance_basis" and f.status is not Status.PASS
    )
    assert "activity" in message.lower()
    assert "self-balance" in message.lower() or "foots" in message.lower()


def test_activity_column_defect_still_self_balances(
    by_defect: dict[str, DocumentReport]
) -> None:
    """Proof the footing check genuinely cannot catch this defect.

    If ``col_self_balance`` fired here the basis control would be redundant.
    It does not fire -- which is exactly why the basis control exists.
    """
    report = by_defect["activity_column_used"]
    assert "col_self_balance" not in report.rules_fired(), (
        "the activity-column defect unbalanced a column, so this corpus no "
        "longer demonstrates the failure mode that survives a footing check"
    )


def test_backup_title_defect_names_the_category_column(
    by_defect: dict[str, DocumentReport]
) -> None:
    """The wrong-text-column defect explains itself in the finding.

    Reading text by position instead of by role is the same error as reading a
    value by position, and the message says so rather than reporting a bare
    string mismatch.
    """
    report = by_defect["backup_title_from_category"]
    messages = [
        f.message for f in report.findings
        if f.rule == "bak_titles_from_title_column" and f.status is not Status.PASS
    ]
    assert messages, "the backup-title control did not fire"
    assert any("CATEGORY" in m for m in messages)
