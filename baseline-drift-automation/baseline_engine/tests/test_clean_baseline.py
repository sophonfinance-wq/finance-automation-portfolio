"""The clean cycle file must satisfy every control.

This is the anchor of the suite. Each defect test proves a control *fires*; only
this file proves the controls are quiet when there is nothing to say. Without it
a control that fired unconditionally would look correct in every other test.
"""

from __future__ import annotations

from baseline_engine.engine import REGISTRY, SEVERITY
from baseline_engine.model import DocumentReport, Status, Verdict


def test_clean_file_passes_every_control(clean_report: DocumentReport) -> None:
    offenders = [
        f"{f.rule} @ {f.location}: {f.message}"
        for f in clean_report.findings
        if f.status is not Status.PASS
    ]
    assert not offenders, "clean file raised findings:\n  " + "\n  ".join(offenders)
    assert clean_report.verdict is Verdict.PASS


def test_clean_file_exercises_every_registered_control(
    clean_report: DocumentReport,
) -> None:
    """Every control ran and returned a finding, so none is silently unreachable."""
    fired = {f.rule for f in clean_report.findings}
    registered = {rule_id for rule_id, _fn in REGISTRY}
    assert fired == registered, f"controls that produced nothing: {registered - fired}"


def test_every_control_declares_a_severity() -> None:
    registered = {rule_id for rule_id, _fn in REGISTRY}
    assert registered <= set(SEVERITY), f"no severity declared: {registered - set(SEVERITY)}"
    assert all(s in (Status.FAIL, Status.FLAG) for s in SEVERITY.values())


def test_registry_ids_are_unique_and_ordered() -> None:
    ids = [rule_id for rule_id, _fn in REGISTRY]
    assert len(ids) == len(set(ids)), "duplicate rule id in REGISTRY"
    assert len(ids) >= 25


def test_registry_order_groups_controls_by_family() -> None:
    """Report order is the registry order, so the families must not interleave."""
    ids = [rule_id for rule_id, _fn in REGISTRY]
    prefixes = [i.split("_")[0] for i in ids if "_" in i]
    seen: list[str] = []
    for p in prefixes:
        if not seen or seen[-1] != p:
            assert p not in seen, f"family {p!r} appears in two separate blocks"
            seen.append(p)
