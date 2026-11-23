"""War-story regressions: generic accounting truths the sentinel must enforce.

Each test tells one classic close failure with fictional entities and seeded
fictional numbers, proven end to end: forge the failure, run the close and
the sentinel, and confirm the right control blocks it. These are the
regressions a controller learns the hard way; here they are executable.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from functools import lru_cache

import pytest

from close_engine.engine import CloseEngine
from close_engine.faults import run_fault_demo
from close_engine.generate import generate_dataset
from close_engine.sentinel import Severity, run_sentinel
from close_engine.sentinel.controls import c2_interco_mirror

# Modest grid: the stories must hold before and after the mid-year renewal
# and across seeds.
GRID = [(p, s) for p in ("2026-03", "2026-08") for s in (3, 2026)]


@lru_cache(maxsize=None)
def _dataset(period: str, seed: int):
    return generate_dataset(period, seed=seed)


@lru_cache(maxsize=None)
def _result(period: str, seed: int):
    return CloseEngine(_dataset(period, seed)).run()


def _findings_for(report, control_id: str):
    return [f for f in report.findings if f.control_id == control_id]


@pytest.mark.parametrize("period,seed", GRID)
def test_a_fully_depreciated_asset_stops_depreciating(period, seed) -> None:
    report, desc = run_fault_demo(seed, period, "ended_asset_keeps_depreciating")
    assert not report.clean
    hits = _findings_for(report, "C4")
    assert any(
        f.subject == "fully depreciated asset still depreciating" for f in hits
    )
    assert "fully depreciated" in desc or "depreciat" in desc


@pytest.mark.parametrize("period,seed", GRID)
def test_over_accrued_depreciation_is_quantified(period, seed) -> None:
    report, _ = run_fault_demo(seed, period, "accumulated_over_cost")
    hits = [
        f
        for f in _findings_for(report, "C4")
        if f.subject == "accumulated depreciation exceeds cost"
    ]
    assert len(hits) == 1
    # The fault strands exactly 1.00 of over-accrual; the finding names it.
    assert "1.00 is the reversal candidate" in hits[0].detail


@pytest.mark.parametrize("period,seed", GRID)
def test_an_allocation_driver_is_period_activity_not_cumulative_balance(
    period, seed
) -> None:
    report, _ = run_fault_demo(seed, period, "balance_as_driver")
    hits = _findings_for(report, "C5")
    assert [f.subject for f in hits] == [
        "cumulative balance used as allocation driver"
    ]
    assert hits[0].severity is Severity.CRITICAL


@pytest.mark.parametrize("period,seed", GRID)
def test_a_renewed_premium_reallocates_or_the_close_blocks(period, seed) -> None:
    report, _ = run_fault_demo(seed, period, "stale_renewal_row")
    assert not report.clean
    hits = _findings_for(report, "C6")
    assert any("stranded" in f.detail for f in hits)


@pytest.mark.parametrize("period,seed", GRID)
def test_the_calendar_catches_a_silently_missing_accrual(period, seed) -> None:
    report, _ = run_fault_demo(seed, period, "missing_recurring_entry")
    hits = _findings_for(report, "C3")
    assert any(f.subject == "expected recurring entry absent" for f in hits)
    assert all(f.severity is Severity.CRITICAL for f in hits)


@pytest.mark.parametrize("period,seed", GRID)
def test_intercompany_legs_must_mirror_to_the_cent(period, seed) -> None:
    # Both legs exist, one is a single cent off: still balanced everywhere,
    # but the mirror control refuses the cent.
    res = copy.deepcopy(_result(period, seed))
    je = next(j for j in res.register if j.category == "note_interest")
    for account, field in (("1800", "debit"), ("4900", "credit")):
        idx = next(
            i
            for i, ln in enumerate(je.lines)
            if ln.account == account and ln.memo.startswith("NOTE-02")
        )
        line = je.lines[idx]
        je.lines[idx] = replace(line, **{field: getattr(line, field) + 1})
    findings = c2_interco_mirror(_dataset(period, seed), res)
    assert any(
        f.subject == "intercompany legs do not mirror" and "NOTE-02" in f.detail
        for f in findings
    )


@pytest.mark.parametrize("period,seed", GRID)
def test_one_sided_intercompany_blocks_the_close(period, seed) -> None:
    report, _ = run_fault_demo(seed, period, "interco_one_sided")
    assert not report.clean
    hits = _findings_for(report, "C2")
    assert any(
        f.subject == "one-sided intercompany entry" and "absent" in f.detail
        for f in hits
    )


@pytest.mark.parametrize("period,seed", GRID)
def test_clearing_legs_sum_rounded_lines_not_rounded_totals(period, seed) -> None:
    report, _ = run_fault_demo(seed, period, "rounded_total_leg")
    hits = _findings_for(report, "C8")
    assert any(
        f.subject == "rounding drift between detail and clearing leg"
        for f in hits
    )
    assert not report.clean


@pytest.mark.parametrize("period,seed", GRID)
def test_a_closed_period_cannot_be_quietly_rewritten(period, seed) -> None:
    report, desc = run_fault_demo(seed, period, "prior_period_mutation")
    hits = _findings_for(report, "C10")
    assert [f.subject for f in hits] == ["closed period mutated"]
    assert "sign-off" in hits[0].detail
    # Only the period lock sees it: the current period itself closed clean.
    assert {f.control_id for f in report.criticals} == {"C10"}
    assert desc


@pytest.mark.parametrize("period,seed", GRID)
def test_two_independent_computations_must_agree_before_post(period, seed) -> None:
    # Clean data: the register and the shadow agree, the close stands.
    clean_report = run_sentinel(_dataset(period, seed), _result(period, seed))
    assert clean_report.clean and not clean_report.findings
    # One cent of tampering hidden inside a balanced entry: only the second,
    # independent computation path can see it.
    report, _ = run_fault_demo(seed, period, "shadow_tamper")
    hits = _findings_for(report, "C9")
    assert hits
    assert all(f.subject == "shadow recomputation disagrees" for f in hits)
    assert {f.control_id for f in report.criticals} == {"C9"}
