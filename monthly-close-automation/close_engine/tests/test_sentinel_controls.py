"""Per-control sentinel tests: clean closes raise nothing; corruption fires.

Every control C1-C10 gets (a) clean-run tests proving zero findings across a
seed/period grid and (b) targeted corruptions proving the control fires with
the documented severity and subject. All data is fictional and seeded.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from functools import lru_cache

import pytest

from close_engine import money
from close_engine.engine import CloseEngine
from close_engine.faults import (
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
)
from close_engine.generate import generate_dataset, months_elapsed
from close_engine.sentinel import (
    ALL_CONTROLS,
    Finding,
    SentinelReport,
    Severity,
    lock_register,
    run_sentinel,
)
from close_engine.sentinel.controls import (
    STEP_ABS_THRESHOLD_CENTS,
    STEP_REL_THRESHOLD_BPS,
    c1_re_balance,
    c2_interco_mirror,
    c3_completeness_calendar,
    c4_asset_life_guard,
    c5_driver_provenance,
    c6_crossfoot,
    c7_step_change,
    c8_rounding_policy,
    c9_shadow_recompute,
    c10_period_lock,
    _memo_references,
    _prior_period,
)

SEEDS = [3, 42, 2026]
# One period before and one after the step-up policy's mid-year renewal.
PERIODS = ["2026-03", "2026-08"]
GRID = [(p, s) for p in PERIODS for s in SEEDS]

CONTROLS = [
    ("C1", c1_re_balance),
    ("C2", c2_interco_mirror),
    ("C3", c3_completeness_calendar),
    ("C4", c4_asset_life_guard),
    ("C5", c5_driver_provenance),
    ("C6", c6_crossfoot),
    ("C7", c7_step_change),
    ("C8", c8_rounding_policy),
    ("C9", c9_shadow_recompute),
    ("C10", c10_period_lock),
]


@lru_cache(maxsize=None)
def _dataset(period: str, seed: int):
    return generate_dataset(period, seed=seed)


@lru_cache(maxsize=None)
def _result(period: str, seed: int):
    return CloseEngine(_dataset(period, seed)).run()


def _bump_line(je, index: int, *, debit: int = 0, credit: int = 0) -> None:
    """Replace one frozen line of a journal entry with adjusted amounts."""
    line = je.lines[index]
    je.lines[index] = replace(
        line, debit=line.debit + debit, credit=line.credit + credit
    )


# --------------------------------------------------------------------------- #
# Registry shape and clean baseline
# --------------------------------------------------------------------------- #


def test_all_controls_registers_the_ten_controls_in_id_order() -> None:
    names = [fn.__name__ for fn in ALL_CONTROLS]
    assert names == [
        "c1_re_balance",
        "c2_interco_mirror",
        "c3_completeness_calendar",
        "c4_asset_life_guard",
        "c5_driver_provenance",
        "c6_crossfoot",
        "c7_step_change",
        "c8_rounding_policy",
        "c9_shadow_recompute",
        "c10_period_lock",
    ]


@pytest.mark.parametrize("control_id,control", CONTROLS)
@pytest.mark.parametrize("period,seed", GRID)
def test_a_clean_close_raises_no_findings_from_any_control(
    control_id, control, period, seed
) -> None:
    assert control(_dataset(period, seed), _result(period, seed)) == []


@pytest.mark.parametrize("period,seed", GRID)
def test_a_clean_close_passes_the_full_sentinel(period, seed) -> None:
    report = run_sentinel(_dataset(period, seed), _result(period, seed))
    assert report.clean
    assert report.findings == []
    assert report.summary_line() == "Sentinel: all controls passed (no findings)."


# --------------------------------------------------------------------------- #
# C1 - re-balance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_an_entry_that_fails_independent_resummation_is_critical(
    period, seed
) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = res.register[0]
    debit_idx = next(i for i, ln in enumerate(je.lines) if ln.debit)
    _bump_line(je, debit_idx, debit=500)
    findings = c1_re_balance(_dataset(period, seed), res)
    assert any(
        f.severity is Severity.CRITICAL
        and f.subject == "journal entry out of balance"
        and je.je_id in f.detail
        for f in findings
    )


@pytest.mark.parametrize("period,seed", GRID)
def test_a_cross_entity_entry_must_balance_within_each_leg(period, seed) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = next(j for j in res.register if j.category == "note_interest")
    # +1 debit in the borrower, +1 credit in the lender: the entry still
    # balances in aggregate but both entity legs are now off by a cent.
    debit_idx = next(i for i, ln in enumerate(je.lines) if ln.account == "6300")
    credit_idx = next(i for i, ln in enumerate(je.lines) if ln.account == "4900")
    _bump_line(je, debit_idx, debit=1)
    _bump_line(je, credit_idx, credit=1)
    findings = c1_re_balance(_dataset(period, seed), res)
    legs = [f for f in findings if f.subject == "entity leg out of balance"]
    assert len(legs) == 2
    assert all(f.severity is Severity.CRITICAL for f in legs)
    assert len({f.entity for f in legs}) == 2


@pytest.mark.parametrize("period,seed", GRID)
def test_an_unbalanced_opening_trial_balance_is_critical(period, seed) -> None:
    corrupted_ds, _ = inject_unbalanced_opening(_dataset(period, seed))
    result = CloseEngine(corrupted_ds).run()
    findings = c1_re_balance(corrupted_ds, result)
    subjects = [f.subject for f in findings]
    # The one-sided opening line breaks both independent verifications: the
    # opening trial balance no longer nets to zero, and the post-close
    # ledger trial balance inherits the imbalance.
    assert "opening trial balance out of balance" in subjects
    assert "post-close trial balance out of balance" in subjects
    assert all(f.severity is Severity.CRITICAL for f in findings)
    assert any("123.45" in f.detail for f in findings)


@pytest.mark.parametrize("period,seed", GRID)
def test_a_post_close_ledger_imbalance_is_critical_on_its_own(period, seed) -> None:
    # Corrupt only the LEDGER (the dataset's opening lines stay balanced), as
    # if a balance were edited after posting: only the post-close gate fires.
    ds = _dataset(period, seed)
    res = copy.deepcopy(_result(period, seed))
    entity = ds.entities()[0].code
    res.ledger._bal[(entity, "1000")] += 777
    findings = c1_re_balance(ds, res)
    assert [f.subject for f in findings] == [
        "post-close trial balance out of balance"
    ]
    assert findings[0].severity is Severity.CRITICAL
    assert "7.77" in findings[0].detail


# --------------------------------------------------------------------------- #
# Memo reference matching (shared by C2/C4/C6/C8 leg identification)
# --------------------------------------------------------------------------- #


def test_memo_reference_matching_is_boundary_aware() -> None:
    # POL-1 must never cross-match a POL-10 memo (and vice versa).
    assert _memo_references("POL-1 2026-03 insurance amortization", "POL-1")
    assert not _memo_references("POL-10 2026-03 insurance amortization", "POL-1")
    assert not _memo_references("Relieve prepaid insurance POL-10", "POL-1")
    assert _memo_references("Relieve prepaid insurance POL-1", "POL-1")
    assert _memo_references("POL-10", "POL-10")
    assert not _memo_references("POL-1", "POL-10")
    # The id must also start on a boundary, not inside another token.
    assert not _memo_references("XPOL-1 amortization", "POL-1")
    # Punctuation and string edges both count as boundaries.
    assert _memo_references("share of POL-1, repriced", "POL-1")
    assert _memo_references("POL-1", "POL-1")


@pytest.mark.parametrize("seed", SEEDS)
def test_policy_ids_that_prefix_each_other_do_not_cross_match(seed) -> None:
    # Rename the policies so one id is a strict prefix of the other; a clean
    # close over that dataset must stay clean (bare substring matching would
    # double-count POL-1's legs with POL-10's).
    ds = copy.deepcopy(_dataset("2026-08", seed))
    ds.subs.insurance[0] = replace(ds.subs.insurance[0], policy_id="POL-1")
    ds.subs.insurance[1] = replace(ds.subs.insurance[1], policy_id="POL-10")
    result = CloseEngine(ds).run()
    assert result.clean
    assert c6_crossfoot(ds, result) == []
    assert c8_rounding_policy(ds, result) == []


# --------------------------------------------------------------------------- #
# C2 - intercompany mirror
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_one_sided_note_accrual_names_the_missing_lender_mirror(
    period, seed
) -> None:
    corrupted, _ = inject_interco_one_sided(_result(period, seed))
    findings = c2_interco_mirror(_dataset(period, seed), corrupted)
    one_sided = [f for f in findings if f.subject == "one-sided intercompany entry"]
    assert len(one_sided) == 1
    assert one_sided[0].severity is Severity.CRITICAL
    assert "lender mirror" in one_sided[0].detail
    assert "NOTE-01" in one_sided[0].detail


@pytest.mark.parametrize("period,seed", GRID)
def test_intercompany_legs_off_by_a_cent_do_not_mirror(period, seed) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = next(j for j in res.register if j.category == "note_interest")
    # Bump the lender's side (both lines, so its leg still self-balances).
    recv_idx = next(
        i for i, ln in enumerate(je.lines)
        if ln.account == "1800" and ln.memo.startswith("NOTE-01")
    )
    income_idx = next(
        i for i, ln in enumerate(je.lines)
        if ln.account == "4900" and ln.memo.startswith("NOTE-01")
    )
    _bump_line(je, recv_idx, debit=1)
    _bump_line(je, income_idx, credit=1)
    findings = c2_interco_mirror(_dataset(period, seed), res)
    mirrors = [f for f in findings if f.subject == "intercompany legs do not mirror"]
    assert len(mirrors) == 1
    assert mirrors[0].severity is Severity.CRITICAL
    assert "0.01" in mirrors[0].detail


@pytest.mark.parametrize("period,seed", GRID)
def test_an_allocation_without_its_payable_side_is_one_sided(period, seed) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = next(j for j in res.register if j.category == "gna_allocation")
    je.lines = [ln for ln in je.lines if ln.account != "2800"]
    findings = c2_interco_mirror(_dataset(period, seed), res)
    assert any(
        f.subject == "one-sided intercompany entry"
        and "due to affiliates" in f.detail
        for f in findings
    )


# --------------------------------------------------------------------------- #
# C3 - completeness calendar
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_silently_dropped_accrual_breaks_the_calendar(period, seed) -> None:
    corrupted, _ = inject_missing_recurring_entry(_result(period, seed))
    findings = c3_completeness_calendar(_dataset(period, seed), corrupted)
    absent = [f for f in findings if f.subject == "expected recurring entry absent"]
    payers = {mf.payer_entity for mf in _dataset(period, seed).mgmt_fees()}
    assert {f.entity for f in absent} == payers
    assert all(f.severity is Severity.CRITICAL for f in absent)
    assert all("mgmt_fee_accrual" in f.detail for f in absent)


@pytest.mark.parametrize("period,seed", GRID)
def test_a_double_posted_allocation_breaks_the_calendar(period, seed) -> None:
    corrupted, _ = inject_duplicate_entry(_result(period, seed))
    findings = c3_completeness_calendar(_dataset(period, seed), corrupted)
    duplicates = [f for f in findings if f.subject == "duplicate recurring entry"]
    assert duplicates
    assert all(f.severity is Severity.CRITICAL for f in duplicates)
    assert all("gna_allocation" in f.detail for f in duplicates)


def test_a_waived_entry_downgrades_the_miss_to_an_info_note() -> None:
    ds = _dataset("2026-08", 2026)
    corrupted, _ = inject_missing_recurring_entry(_result("2026-08", 2026))
    waivers = [
        (mf.payer_entity, "mgmt_fee_accrual", "fee holiday agreed for the quarter")
        for mf in ds.mgmt_fees()
    ]
    findings = c3_completeness_calendar(ds, corrupted, calendar=waivers)
    assert all(f.severity is not Severity.CRITICAL for f in findings)
    infos = [f for f in findings if f.subject == "calendar waiver on file"]
    assert len(infos) == len(waivers)
    assert all("fee holiday" in f.detail for f in infos)


def test_calendar_waivers_flow_through_run_sentinel() -> None:
    ds = _dataset("2026-08", 2026)
    corrupted, _ = inject_missing_recurring_entry(_result("2026-08", 2026))
    waivers = [
        (mf.payer_entity, "mgmt_fee_accrual", "documented one-month suspension")
        for mf in ds.mgmt_fees()
    ]
    report = run_sentinel(ds, corrupted, calendar_waivers=waivers)
    assert not any(
        f.control_id == "C3" and f.severity is Severity.CRITICAL
        for f in report.findings
    )
    assert any(f.subject == "calendar waiver on file" for f in report.findings)


# --------------------------------------------------------------------------- #
# C4 - asset life guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_an_expired_asset_still_booking_depreciation_is_critical(
    period, seed
) -> None:
    corrupted_ds, _ = inject_ended_asset_keeps_depreciating(_dataset(period, seed))
    findings = c4_asset_life_guard(corrupted_ds, _result(period, seed))
    hits = [
        f for f in findings
        if f.subject == "fully depreciated asset still depreciating"
    ]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    asset = corrupted_ds.subs.fixed_assets[0]
    assert hits[0].entity == asset.entity
    assert asset.asset_id in hits[0].detail
    assert "overstatement" in hits[0].detail


@pytest.mark.parametrize("period,seed", GRID)
def test_over_accrued_depreciation_reports_the_exact_excess(period, seed) -> None:
    corrupted_ds, _ = inject_accumulated_over_cost(_dataset(period, seed))
    findings = c4_asset_life_guard(corrupted_ds, _result(period, seed))
    hits = [
        f for f in findings if f.subject == "accumulated depreciation exceeds cost"
    ]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    # The fault writes cost down to exactly 1.00 below the recorded accum.
    assert "1.00 is the reversal candidate" in hits[0].detail


@pytest.mark.parametrize("period,seed", GRID)
def test_a_doctored_workpaper_cannot_hide_the_over_accrual(period, seed) -> None:
    # The adversarial probe: write the cost down AND doctor the schedule's
    # accum figure to match, so a control that trusts the workpaper stays
    # silent. C4 re-derives the accumulation from the sub-ledger and the
    # posted register, so the doctored schedule cannot vouch for itself.
    corrupted_ds, _ = inject_accumulated_over_cost(_dataset(period, seed))
    res = copy.deepcopy(_result(period, seed))
    fa = corrupted_ds.subs.fixed_assets[0]
    sched = next(s for s in res.schedules if s.category == "depreciation")
    for row in sched.rows:
        if row.key == fa.asset_id:
            row.fields["accum_dep"] = money.fmt(fa.cost_cents)
            row.fields["cost"] = money.fmt(fa.cost_cents)
    findings = c4_asset_life_guard(corrupted_ds, res)
    hits = [
        f for f in findings if f.subject == "accumulated depreciation exceeds cost"
    ]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    assert "1.00 is the reversal candidate" in hits[0].detail


# --------------------------------------------------------------------------- #
# C5 - driver provenance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_cumulative_balance_driver_is_named_as_such(period, seed) -> None:
    corrupted_ds, _ = inject_balance_as_driver(_dataset(period, seed))
    result = CloseEngine(corrupted_ds).run()
    findings = c5_driver_provenance(corrupted_ds, result)
    assert [f.subject for f in findings] == [
        "cumulative balance used as allocation driver"
    ]
    assert findings[0].severity is Severity.CRITICAL
    assert "year-to-date" in findings[0].detail


@pytest.mark.parametrize("period,seed", GRID)
def test_any_other_driver_mismatch_reports_both_numbers(period, seed) -> None:
    ds = copy.deepcopy(_dataset(period, seed))
    gna = ds.subs.gna
    ds.subs.gna = replace(
        gna, monthly_pool_cents=gna.monthly_pool_cents + 12345
    )
    result = CloseEngine(ds).run()
    findings = c5_driver_provenance(ds, result)
    assert [f.subject for f in findings] == [
        "allocation driver does not match period activity"
    ]
    assert money.fmt(gna.monthly_pool_cents) in findings[0].detail
    assert money.fmt(gna.monthly_pool_cents + 12345) in findings[0].detail


# --------------------------------------------------------------------------- #
# C6 - crossfoot
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_repriced_premium_with_stale_shares_fails_the_crossfoot(
    period, seed
) -> None:
    corrupted_ds, _ = inject_stale_renewal_row(_dataset(period, seed))
    findings = c6_crossfoot(corrupted_ds, _result(period, seed))
    hits = [
        f for f in findings
        if f.subject == "entity shares do not crossfoot to the policy monthly total"
    ]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    assert "stranded" in hits[0].detail
    assert corrupted_ds.subs.insurance[0].policy_id in hits[0].detail


def test_a_split_map_that_misses_full_coverage_is_a_critical_finding() -> None:
    ds = copy.deepcopy(_dataset("2026-08", 2026))
    pol = ds.subs.insurance[0]
    short_split = dict(pol.split_bps)
    first_entity = next(iter(short_split))
    short_split[first_entity] -= 10
    ds.subs.insurance[0] = replace(pol, split_bps=short_split)
    findings = c6_crossfoot(ds, _result("2026-08", 2026))
    hits = [
        f for f in findings
        if f.subject == "allocation split map fails dataset integrity"
    ]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    assert "9990 bps" in hits[0].detail
    assert "-10 bps" in hits[0].detail


def test_a_split_map_naming_an_outside_entity_is_a_critical_finding() -> None:
    ds = copy.deepcopy(_dataset("2026-08", 2026))
    pol = ds.subs.insurance[0]
    split = dict(pol.split_bps)
    first_entity = next(iter(split))
    split["ZZ"] = split.pop(first_entity)  # sum stays 10000; ZZ is outside
    ds.subs.insurance[0] = replace(pol, split_bps=split)
    findings = c6_crossfoot(ds, _result("2026-08", 2026))
    hits = [
        f for f in findings
        if f.subject == "allocation split map fails dataset integrity"
    ]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    assert "ZZ" in hits[0].detail
    assert "outside the group" in hits[0].detail


@pytest.mark.parametrize("corruption", ["bad_sum", "unknown_entity"])
@pytest.mark.parametrize("period,seed", GRID)
def test_an_invalid_split_map_is_refused_and_blocked_end_to_end(
    corruption, period, seed
) -> None:
    # End to end: the engine must refuse (never crash on) an invalid split
    # map, the close must not be clean, and C6 must block it.
    ds = copy.deepcopy(_dataset(period, seed))
    pol = ds.subs.insurance[0]
    split = dict(pol.split_bps)
    first_entity = next(iter(split))
    if corruption == "bad_sum":
        split[first_entity] += 100  # 10100 bps
    else:
        split["ZZ"] = split.pop(first_entity)  # unknown entity, sum intact
    ds.subs.insurance[0] = replace(pol, split_bps=split)
    result = CloseEngine(ds).run()  # must not raise
    assert not result.clean
    assert [err.je.category for err in result.refused] == [
        "insurance_allocation"
    ]
    assert "split_bps" in result.refused[0].detail
    assert not any(
        je.category == "insurance_allocation" for je in result.register
    )
    report = run_sentinel(ds, result)
    assert not report.clean
    integrity = [
        f for f in report.findings
        if f.control_id == "C6"
        and f.subject == "allocation split map fails dataset integrity"
    ]
    assert len(integrity) == 1
    assert integrity[0].severity is Severity.CRITICAL
    assert pol.policy_id in integrity[0].detail


# --------------------------------------------------------------------------- #
# C7 - step change
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_an_uncorroborated_step_change_warns_the_reviewer(period, seed) -> None:
    res = copy.deepcopy(_result(period, seed))
    je = next(j for j in res.register if j.category == "mgmt_fee_accrual")
    for i, line in enumerate(je.lines):
        je.lines[i] = replace(line, debit=line.debit * 3, credit=line.credit * 3)
    findings = c7_step_change(_dataset(period, seed), res)
    warns = [f for f in findings if f.subject == "unexplained step change"]
    payers = {mf.payer_entity for mf in _dataset(period, seed).mgmt_fees()}
    assert {f.entity for f in warns} == payers
    assert all(f.severity is Severity.WARN for f in warns)
    assert all("no corroborating sub-ledger event" in f.detail for f in warns)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_renewal_step_up_is_corroborated_as_an_info_note(seed) -> None:
    # Reprice the renewal to double, then close AT the renewal month: the big
    # step is real, but the sub-ledger renewal event explains it.
    ds = copy.deepcopy(_dataset("2026-07", seed))
    pol = ds.subs.insurance[0]
    assert pol.renewal_period == "2026-07"
    ds.subs.insurance[0] = replace(
        pol, renewal_annual_premium_cents=pol.annual_premium_cents * 2
    )
    result = CloseEngine(ds).run()
    findings = c7_step_change(ds, result)
    infos = [f for f in findings if f.severity is Severity.INFO]
    assert infos
    assert all(
        f.subject == "step change corroborated by sub-ledger event" for f in infos
    )
    assert all("step-up explained by POL-01 renewal" in f.detail for f in infos)
    assert not any(f.severity is Severity.WARN for f in findings)


def test_step_thresholds_are_named_module_constants() -> None:
    assert STEP_REL_THRESHOLD_BPS == 2000  # 20.00%
    assert STEP_ABS_THRESHOLD_CENTS == 100 * 100  # 100.00


@pytest.mark.parametrize("period,seed", GRID)
def test_an_uncorroborated_step_down_warns_too(period, seed) -> None:
    # Decreases are steps as well: halve one category with no sub-ledger
    # event behind it and the reviewer must still be warned.
    res = copy.deepcopy(_result(period, seed))
    je = next(j for j in res.register if j.category == "mgmt_fee_accrual")
    for i, line in enumerate(je.lines):
        je.lines[i] = replace(
            line, debit=line.debit // 2, credit=line.credit // 2
        )
    findings = c7_step_change(_dataset(period, seed), res)
    warns = [f for f in findings if f.subject == "unexplained step change"]
    payers = {mf.payer_entity for mf in _dataset(period, seed).mgmt_fees()}
    assert {f.entity for f in warns} == payers
    assert all(f.severity is Severity.WARN for f in warns)


@pytest.mark.parametrize("seed", SEEDS)
def test_an_event_at_one_entity_does_not_corroborate_another_entitys_step(
    seed,
) -> None:
    # The dataset places one asset in service in the close month at ONE
    # entity; a doctored depreciation step at a DIFFERENT entity must not
    # borrow that event as corroboration.
    period = "2026-03"
    ds = _dataset(period, seed)
    new_asset = next(
        fa for fa in ds.fixed_assets() if fa.in_service_period == period
    )
    other = next(
        e.code for e in ds.entities() if e.code != new_asset.entity
    )
    res = copy.deepcopy(_result(period, seed))
    je = next(j for j in res.register if j.category == "depreciation")
    je.lines = [
        replace(ln, debit=ln.debit * 3, credit=ln.credit * 3)
        if ln.entity == other
        else ln
        for ln in je.lines
    ]
    findings = c7_step_change(ds, res)
    steps = [f for f in findings if f.entity == other]
    assert steps
    assert all(f.subject == "unexplained step change" for f in steps)
    assert all(f.severity is Severity.WARN for f in steps)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_prepaid_expiring_this_period_corroborates_the_step_down(seed) -> None:
    # End the first prepaid's term exactly at the close month: its last
    # amortization was the prior period, so this period steps down. The
    # sub-ledger expiry is the corroborating event (INFO, not WARN).
    period = "2026-03"
    ds = copy.deepcopy(_dataset(period, seed))
    pp = ds.subs.prepaids[0]
    elapsed = months_elapsed(pp.start_period, period)
    ds.subs.prepaids[0] = replace(pp, term_months=elapsed)
    result = CloseEngine(ds).run()
    findings = c7_step_change(ds, result)
    entity_findings = [f for f in findings if f.entity == pp.entity]
    assert entity_findings
    assert all(
        f.subject == "step change corroborated by sub-ledger event"
        for f in entity_findings
    )
    assert all(f.severity is Severity.INFO for f in entity_findings)
    assert any(
        f"step-down explained by prepaid {pp.item_id} expired" in f.detail
        for f in entity_findings
    )


# --------------------------------------------------------------------------- #
# C8 - rounding policy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_rounded_total_clearing_leg_drifts_from_the_detail(period, seed) -> None:
    corrupted, _ = inject_rounded_total_leg(_result(period, seed))
    findings = c8_rounding_policy(_dataset(period, seed), corrupted)
    hits = [
        f for f in findings
        if f.subject == "rounding drift between detail and clearing leg"
    ]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    assert "round(total)" in hits[0].detail


def test_an_insurance_relief_off_by_a_cent_drifts_from_its_expense_lines() -> None:
    res = copy.deepcopy(_result("2026-08", 2026))
    je = next(j for j in res.register if j.category == "insurance_allocation")
    relief_idx = next(
        i for i, ln in enumerate(je.lines)
        if ln.account == "1450" and "POL-01" in ln.memo
    )
    _bump_line(je, relief_idx, credit=1)
    findings = c8_rounding_policy(_dataset("2026-08", 2026), res)
    hits = [f for f in findings if "POL-01" in f.detail]
    assert len(hits) == 1
    assert hits[0].severity is Severity.CRITICAL
    assert "0.01 drift" in hits[0].detail


# --------------------------------------------------------------------------- #
# C9 - shadow recompute
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_a_balanced_single_cent_tamper_only_the_shadow_can_see(
    period, seed
) -> None:
    corrupted, _ = inject_shadow_tamper(_result(period, seed))
    findings = c9_shadow_recompute(_dataset(period, seed), corrupted)
    assert len(findings) == 2  # the tampered debit key and credit key
    assert all(f.severity is Severity.CRITICAL for f in findings)
    assert all(f.subject == "shadow recomputation disagrees" for f in findings)


# --------------------------------------------------------------------------- #
# C10 - period lock
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_lock_register_is_deterministic_across_recomputes(period, seed) -> None:
    first = lock_register(_result(period, seed))
    recomputed = CloseEngine(generate_dataset(period, seed=seed)).run()
    assert lock_register(recomputed) == first
    assert len(first) == 64  # sha256 hex digest


@pytest.mark.parametrize("period,seed", GRID)
def test_an_honest_lock_verifies_against_the_recompute(period, seed) -> None:
    prior = _prior_period(period)
    locked = {prior: lock_register(_result(prior, seed))}
    findings = c10_period_lock(
        _dataset(period, seed), _result(period, seed), locked=locked
    )
    assert findings == []


@pytest.mark.parametrize("period,seed", GRID)
def test_a_mutated_locked_period_is_critical(period, seed) -> None:
    prior = _prior_period(period)
    mutated, _ = inject_prior_period_mutation(_result(prior, seed))
    locked = {prior: lock_register(mutated)}
    findings = c10_period_lock(
        _dataset(period, seed), _result(period, seed), locked=locked
    )
    assert [f.subject for f in findings] == ["closed period mutated"]
    assert findings[0].severity is Severity.CRITICAL
    assert prior in findings[0].detail


def test_no_lock_map_means_no_period_lock_findings() -> None:
    assert c10_period_lock(
        _dataset("2026-08", 2026), _result("2026-08", 2026), locked=None
    ) == []


def test_locked_hashes_flow_through_run_sentinel() -> None:
    prior = _prior_period("2026-08")
    mutated, _ = inject_prior_period_mutation(_result(prior, 2026))
    report = run_sentinel(
        _dataset("2026-08", 2026),
        _result("2026-08", 2026),
        locked={prior: lock_register(mutated)},
    )
    assert not report.clean
    assert [f.control_id for f in report.criticals] == ["C10"]


# --------------------------------------------------------------------------- #
# SentinelReport behaviour
# --------------------------------------------------------------------------- #


def _sample_report() -> SentinelReport:
    return SentinelReport(
        [
            Finding("C4", Severity.CRITICAL, "DH", "subject a", "detail a"),
            Finding("C7", Severity.WARN, "MF", "subject b", "detail b"),
            Finding("C3", Severity.INFO, None, "subject c", "detail c"),
            Finding("C4", Severity.CRITICAL, "BW", "subject d", "detail d"),
        ]
    )


def test_report_partitions_findings_by_severity() -> None:
    report = _sample_report()
    assert [f.subject for f in report.criticals] == ["subject a", "subject d"]
    assert [f.subject for f in report.warnings] == ["subject b"]
    assert [f.subject for f in report.infos] == ["subject c"]


def test_report_is_clean_only_without_criticals() -> None:
    assert not _sample_report().clean
    assert SentinelReport([]).clean
    assert SentinelReport(
        [Finding("C7", Severity.WARN, None, "s", "d")]
    ).clean


def test_report_groups_findings_by_control() -> None:
    grouped = _sample_report().by_control
    assert list(grouped) == ["C4", "C7", "C3"]
    assert len(grouped["C4"]) == 2


def test_report_summary_line_counts_each_severity() -> None:
    line = _sample_report().summary_line()
    assert line == "Sentinel: NOT CLEAN - 2 critical, 1 warning, 1 info."
    warn_only = SentinelReport([Finding("C7", Severity.WARN, None, "s", "d")])
    assert warn_only.summary_line() == (
        "Sentinel: CLEAN - 0 critical, 1 warning, 0 info."
    )


def test_run_sentinel_aggregates_findings_in_control_order() -> None:
    corrupted, _ = inject_duplicate_entry(_result("2026-08", 2026))
    report = run_sentinel(_dataset("2026-08", 2026), corrupted)
    ids = [int(f.control_id[1:]) for f in report.findings]
    assert ids == sorted(ids)
    assert not report.clean
