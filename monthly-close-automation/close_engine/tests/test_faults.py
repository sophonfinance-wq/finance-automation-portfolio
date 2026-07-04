"""Fault injector tests: every injector forges its documented corruption.

Each test verifies the SHAPE of the corruption (a fresh deep copy, the
original untouched, the documented effect present, and a one-line
description), then the ``run_fault_demo`` round trip proves the expected
sentinel control actually fires on every fault and that a clean baseline
produces zero findings.
"""

from __future__ import annotations

from functools import lru_cache

import pytest

from close_engine import money
from close_engine.engine import CloseEngine
from close_engine.faults import (
    FAULTS,
    _prior_period,
    inject_accumulated_over_cost,
    inject_balance_as_driver,
    inject_duplicate_entry,
    inject_ended_asset_keeps_depreciating,
    inject_interco_one_sided,
    inject_missing_recurring_entry,
    inject_prior_period_mutation,
    inject_rounded_total_leg,
    inject_shadow_tamper,
    inject_stale_renewal_row,
    inject_unbalanced_opening,
    inject_uncorroborated_step,
    run_fault_demo,
)
from close_engine.generate import generate_dataset, months_elapsed, period_index
from close_engine.sentinel import Severity

SEEDS = [3, 42, 2026]
# One period before and one after the step-up policy's mid-year renewal.
PERIODS = ["2026-03", "2026-08"]
GRID = [(p, s) for p in PERIODS for s in SEEDS]

EXPECTED_FAULT_ORDER = [
    "unbalanced_opening",
    "ended_asset_keeps_depreciating",
    "accumulated_over_cost",
    "balance_as_driver",
    "stale_renewal_row",
    "missing_recurring_entry",
    "duplicate_entry",
    "interco_one_sided",
    "uncorroborated_step",
    "rounded_total_leg",
    "shadow_tamper",
    "prior_period_mutation",
]

EXPECTED_CONTROL_FOR = {
    "unbalanced_opening": "C1",
    "ended_asset_keeps_depreciating": "C4",
    "accumulated_over_cost": "C4",
    "balance_as_driver": "C5",
    "stale_renewal_row": "C6",
    "missing_recurring_entry": "C3",
    "duplicate_entry": "C3",
    "interco_one_sided": "C2",
    "uncorroborated_step": "C7",
    "rounded_total_leg": "C8",
    "shadow_tamper": "C9",
    "prior_period_mutation": "C10",
}

# C7 is a reviewer-escalation control: its qualifying catch is WARN or above.
# Every other expected control must block the close with a CRITICAL finding.
WARN_COUNTS_AS_CAUGHT = {"C7"}


@lru_cache(maxsize=None)
def _dataset(period: str, seed: int):
    return generate_dataset(period, seed=seed)


@lru_cache(maxsize=None)
def _result(period: str, seed: int):
    return CloseEngine(_dataset(period, seed)).run()


def _register_fingerprint(result):
    return [
        (je.je_id, je.category, [(l.entity, l.account, l.debit, l.credit) for l in je.lines])
        for je in result.register
    ]


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_the_fault_registry_lists_the_twelve_faults_in_order() -> None:
    assert len(FAULTS) == 12
    assert list(FAULTS) == EXPECTED_FAULT_ORDER


@pytest.mark.parametrize("fault_name", EXPECTED_FAULT_ORDER)
def test_every_fault_maps_to_the_control_that_must_catch_it(fault_name) -> None:
    injector, control_id = FAULTS[fault_name]
    assert callable(injector)
    assert control_id == EXPECTED_CONTROL_FOR[fault_name]
    assert injector.stage in {"dataset_pre", "dataset_post", "result", "prior_result"}


@pytest.mark.parametrize("fault_name", EXPECTED_FAULT_ORDER)
@pytest.mark.parametrize("period,seed", GRID)
def test_every_injector_returns_a_fresh_copy_and_a_one_line_description(
    fault_name, period, seed
) -> None:
    injector, _ = FAULTS[fault_name]
    if injector.stage in ("dataset_pre", "dataset_post"):
        source = _dataset(period, seed)
    else:
        source = _result(period, seed)
    corrupted, desc = injector(source)
    assert corrupted is not source
    assert isinstance(desc, str)
    assert desc.strip()
    assert "\n" not in desc


# --------------------------------------------------------------------------- #
# C1 — one-sided opening line
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_one_sided_opening_line_unbalances_the_trial_balance(period, seed) -> None:
    ds = _dataset(period, seed)
    corrupted, desc = inject_unbalanced_opening(ds)
    assert len(corrupted.opening_tb) == len(ds.opening_tb) + 1
    extra = corrupted.opening_tb[-1]
    assert extra.debit == 12345 and extra.credit == 0
    assert sum(l.debit - l.credit for l in corrupted.opening_tb) == 12345
    # Original dataset untouched and still balanced.
    assert sum(l.debit - l.credit for l in ds.opening_tb) == 0
    assert "one-sided" in desc
    assert "123.45" in desc


# --------------------------------------------------------------------------- #
# C4 — ended asset keeps depreciating
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_fully_depreciated_asset_is_left_booking_depreciation(period, seed) -> None:
    ds = _dataset(period, seed)
    corrupted, desc = inject_ended_asset_keeps_depreciating(ds)
    fa = corrupted.subs.fixed_assets[0]
    # The asset is now past its useful life as of the close month...
    assert months_elapsed(fa.in_service_period, period) >= fa.useful_life_months
    # ...while the clean register (unchanged by this dataset fault) still
    # books its monthly depreciation.
    result = _result(period, seed)
    dep_je = next(je for je in result.register if je.category == "depreciation")
    assert any(fa.asset_id in ln.memo for ln in dep_je.lines if ln.debit)
    # Original dataset untouched.
    assert ds.subs.fixed_assets[0].useful_life_months > fa.useful_life_months
    assert fa.asset_id in desc


# --------------------------------------------------------------------------- #
# C4 — accumulated depreciation over cost
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_over_accrued_depreciation_exceeds_cost_by_exactly_one_dollar(
    period, seed
) -> None:
    ds = _dataset(period, seed)
    original = ds.subs.fixed_assets[0]
    parts = money.split_evenly(original.cost_cents, original.useful_life_months)
    elapsed = months_elapsed(original.in_service_period, period)
    booked = sum(parts[: max(0, min(elapsed + 1, original.useful_life_months))])

    corrupted, desc = inject_accumulated_over_cost(ds)
    fa = corrupted.subs.fixed_assets[0]
    assert fa.cost_cents == booked - 100
    assert booked - fa.cost_cents == 100  # the exact reversal candidate
    assert ds.subs.fixed_assets[0].cost_cents == original.cost_cents
    assert "1.00" in desc


# --------------------------------------------------------------------------- #
# C5 — cumulative balance used as allocation driver
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_the_allocation_driver_becomes_a_cumulative_balance(period, seed) -> None:
    ds = _dataset(period, seed)
    corrupted, desc = inject_balance_as_driver(ds)
    factor = max(2, int(period.split("-")[1]))
    assert (
        corrupted.subs.gna.monthly_pool_cents
        == ds.subs.gna.monthly_pool_cents * factor
    )
    # The split itself stays valid: the corruption is the driver, not the map.
    assert sum(corrupted.subs.gna.split_bps.values()) == 10000
    assert "cumulative" in desc


# --------------------------------------------------------------------------- #
# C6 — stale renewal row
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_repriced_premium_leaves_the_posted_shares_stranded(period, seed) -> None:
    ds = _dataset(period, seed)
    original = ds.subs.insurance[0]
    corrupted, desc = inject_stale_renewal_row(ds)
    pol = corrupted.subs.insurance[0]
    if period_index(period) >= period_index(pol.renewal_period):
        assert (
            pol.renewal_annual_premium_cents
            == original.renewal_annual_premium_cents * 12000 // 10000
        )
        assert pol.annual_premium_cents == original.annual_premium_cents
    else:
        assert pol.annual_premium_cents == original.annual_premium_cents * 12000 // 10000
        assert (
            pol.renewal_annual_premium_cents == original.renewal_annual_premium_cents
        )
    # The posted register (clean run) still totals the OLD monthly amount, so
    # the entity shares no longer crossfoot to the repriced policy total.
    assert ds.subs.insurance[0] == original
    assert pol.policy_id in desc


# --------------------------------------------------------------------------- #
# C3 — missing and duplicate recurring entries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_the_management_fee_accrual_goes_silently_missing(period, seed) -> None:
    result = _result(period, seed)
    corrupted, desc = inject_missing_recurring_entry(result)
    before = {je.category for je in result.register}
    after = {je.category for je in corrupted.register}
    assert before - after == {"mgmt_fee_accrual"}
    assert "mgmt_fee_accrual" in {je.category for je in result.register}
    assert "absent" in desc


@pytest.mark.parametrize("period,seed", GRID)
def test_the_gna_allocation_posts_twice_in_one_period(period, seed) -> None:
    result = _result(period, seed)
    corrupted, desc = inject_duplicate_entry(result)
    cats = [je.category for je in corrupted.register]
    assert cats.count("gna_allocation") == 2
    assert len(corrupted.register) == len(result.register) + 1
    assert [je.category for je in result.register].count("gna_allocation") == 1
    assert "duplicate" in desc


# --------------------------------------------------------------------------- #
# C2 — one-sided intercompany
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_the_lender_mirror_disappears_but_every_leg_still_balances(
    period, seed
) -> None:
    result = _result(period, seed)
    corrupted, desc = inject_interco_one_sided(result)
    je = next(j for j in corrupted.register if j.category == "note_interest")
    # The far leg is gone...
    assert not any(
        ln.account in ("1800", "4900") and ln.memo.startswith("NOTE-01")
        for ln in je.lines
    )
    # ...the near leg still posts...
    assert any(
        ln.account == "6300" and ln.memo.startswith("NOTE-01") for ln in je.lines
    )
    assert any(
        ln.account == "2400" and ln.memo.startswith("NOTE-01") for ln in je.lines
    )
    # ...and the entry stays balanced in aggregate AND per entity, so only the
    # intercompany-mirror control (not the balance control) can see the hole.
    assert je.is_balanced
    assert all(diff == 0 for diff in je.balances_per_entity().values())
    # Original result untouched.
    clean_je = next(j for j in result.register if j.category == "note_interest")
    assert any(
        ln.account == "1800" and ln.memo.startswith("NOTE-01") for ln in clean_je.lines
    )
    assert "one-sided" in desc


# --------------------------------------------------------------------------- #
# C7 — uncorroborated step
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_one_entity_accrual_steps_up_with_no_event_behind_it(period, seed) -> None:
    result = _result(period, seed)
    corrupted, desc = inject_uncorroborated_step(result)
    clean_je = next(
        j for j in result.register if j.category == "mgmt_fee_accrual"
    )
    bad_je = next(
        j for j in corrupted.register if j.category == "mgmt_fee_accrual"
    )
    target = clean_je.lines[0].entity
    for clean_ln, bad_ln in zip(clean_je.lines, bad_je.lines):
        if clean_ln.entity == target:
            assert bad_ln.debit == clean_ln.debit * 3 // 2
            assert bad_ln.credit == clean_ln.credit * 3 // 2
        else:
            assert (bad_ln.debit, bad_ln.credit) == (
                clean_ln.debit, clean_ln.credit
            )
    # The tampered entry still balances in aggregate AND per entity, so only
    # the step-change review (and the shadow recompute) can see it.
    assert bad_je.is_balanced
    assert all(d == 0 for d in bad_je.balances_per_entity().values())
    assert target in desc
    assert "1.5x" in desc


@pytest.mark.parametrize("period,seed", GRID)
def test_the_uncorroborated_step_warns_c7_and_is_blocked_by_c9(period, seed) -> None:
    report, _ = run_fault_demo(seed, period, "uncorroborated_step")
    c7 = [f for f in report.findings if f.control_id == "C7"]
    assert c7
    assert all(f.severity is Severity.WARN for f in c7)
    assert all(f.subject == "unexplained step change" for f in c7)
    # The same tamper also fails the independent shadow recompute, which is
    # what actually blocks the close (C7 escalates to the reviewer).
    assert any(f.control_id == "C9" for f in report.criticals)
    assert not report.clean


# --------------------------------------------------------------------------- #
# C8 — clearing leg = round(total)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_the_clearing_leg_drifts_one_cent_from_the_rounded_detail(period, seed) -> None:
    result = _result(period, seed)
    pool = _dataset(period, seed).gna().monthly_pool_cents
    corrupted, desc = inject_rounded_total_leg(result)
    je = next(j for j in corrupted.register if j.category == "gna_allocation")
    clearing = sum(ln.credit for ln in je.lines if ln.account == "6650")
    detail = sum(ln.debit for ln in je.lines if ln.account == "6600")
    assert clearing == pool + 1
    assert detail == pool  # the rounded detail lines are untouched
    assert clearing - detail == 1
    assert je.is_balanced
    assert all(diff == 0 for diff in je.balances_per_entity().values())
    assert "one cent" in desc


# --------------------------------------------------------------------------- #
# C9 — single-cent tamper
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_single_cent_tamper_hides_inside_a_balanced_entry(period, seed) -> None:
    result = _result(period, seed)
    corrupted, desc = inject_shadow_tamper(result)
    clean_je = next(
        j for j in result.register if j.category == "prepaid_amortization"
    )
    bad_je = next(
        j for j in corrupted.register if j.category == "prepaid_amortization"
    )
    diffs = [
        (a, b)
        for a, b in zip(clean_je.lines, bad_je.lines)
        if (a.debit, a.credit) != (b.debit, b.credit)
    ]
    assert len(diffs) == 2
    for clean_ln, bad_ln in diffs:
        assert (bad_ln.debit - clean_ln.debit) + (bad_ln.credit - clean_ln.credit) == 1
    assert bad_je.is_balanced
    assert "cent" in desc


# --------------------------------------------------------------------------- #
# C10 — prior-period mutation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_locked_period_register_is_quietly_rewritten(period, seed) -> None:
    prior = _prior_period(period)
    prior_result = _result(prior, seed)
    corrupted, desc = inject_prior_period_mutation(prior_result)
    assert _register_fingerprint(corrupted) != _register_fingerprint(prior_result)
    # The mutation is quiet: same entries, same counts, still balanced.
    assert len(corrupted.register) == len(prior_result.register)
    assert corrupted.register[0].is_balanced
    assert prior in desc
    assert "alter" in desc


def test_the_prior_period_helper_rolls_across_a_year_end() -> None:
    assert _prior_period("2026-01") == "2025-12"
    assert _prior_period("2026-08") == "2026-07"


# --------------------------------------------------------------------------- #
# run_fault_demo — round trip through the sentinel
# --------------------------------------------------------------------------- #


def test_run_fault_demo_rejects_an_unknown_fault() -> None:
    with pytest.raises(KeyError):
        run_fault_demo(2026, "2026-03", "not_a_registered_fault")


@pytest.mark.parametrize("fault_name", EXPECTED_FAULT_ORDER)
@pytest.mark.parametrize("period,seed", GRID)
def test_run_fault_demo_round_trip_expected_control_fires(
    fault_name, period, seed
) -> None:
    report, desc = run_fault_demo(seed, period, fault_name)
    expected = FAULTS[fault_name][1]
    assert any(f.control_id == expected for f in report.findings), (
        f"{fault_name} must be caught by {expected}"
    )
    assert not report.clean, f"{fault_name} left the close clean"
    assert desc


@pytest.mark.parametrize("fault_name", EXPECTED_FAULT_ORDER)
def test_run_fault_demo_never_blames_the_wrong_severity(fault_name) -> None:
    report, _ = run_fault_demo(2026, "2026-08", fault_name)
    expected = FAULTS[fault_name][1]
    fired = [f for f in report.findings if f.control_id == expected]
    assert fired
    # A fault is caught when its expected control fires at a qualifying
    # severity: CRITICAL for the blocking controls, WARN or above for the
    # reviewer-escalation control C7. Either way the close ends not clean
    # (for C7's fault the shadow recompute raises the blocking CRITICAL).
    if expected in WARN_COUNTS_AS_CAUGHT:
        assert any(f.severity.value in ("critical", "warn") for f in fired)
    else:
        assert any(f.severity.value == "critical" for f in fired)
    assert not report.clean


def test_stale_renewal_substitutes_a_same_class_fault_before_inception() -> None:
    # 2025-06 precedes both policies' inception: nothing is in force to
    # reprice, so the injector swaps in a split-map integrity corruption of
    # the same crossfoot class instead of silently doing nothing.
    ds = _dataset("2025-06", 2026)
    corrupted, desc = inject_stale_renewal_row(ds)
    pol = corrupted.subs.insurance[0]
    assert sum(pol.split_bps.values()) == 10100
    # Original dataset untouched.
    assert sum(ds.subs.insurance[0].split_bps.values()) == 10000
    assert "no policy in force" in desc
    report, _ = run_fault_demo(2026, "2025-06", "stale_renewal_row")
    assert not report.clean
    assert any(
        f.control_id == "C6"
        and f.severity is Severity.CRITICAL
        and f.subject == "allocation split map fails dataset integrity"
        for f in report.findings
    )


def test_run_fault_demo_clean_baseline_has_zero_findings() -> None:
    from close_engine.sentinel import run_sentinel

    ds = generate_dataset("2026-08", seed=2026)
    report = run_sentinel(ds, CloseEngine(ds).run())
    assert report.clean
    assert not report.findings
