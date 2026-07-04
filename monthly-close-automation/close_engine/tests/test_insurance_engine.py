"""Insurance allocation engine tests.

Covers: largest-remainder exactness (entity shares sum EXACTLY to the policy
monthly total), the mid-year renewal step-up (the step-up month books the new
rate; a flat renewal does not change the premium in force), the prepaid
insurance tie (account 1450), and per-entity JE correctness. Parametrized
across seeds and periods. All data is fictional and seeded.
"""

from __future__ import annotations

from functools import lru_cache

import pytest

from close_engine import money
from close_engine.engine import CloseEngine
from close_engine.generate import (
    InsurancePolicy,
    generate_dataset,
    months_elapsed,
    period_index,
)

SEEDS = [1, 7, 11, 99, 555, 2026]
PERIODS = [f"2026-{m:02d}" for m in range(1, 13)]
GRID = [(p, s) for p in PERIODS for s in SEEDS]


@lru_cache(maxsize=None)
def _dataset(period: str, seed: int):
    return generate_dataset(period, seed=seed)


@lru_cache(maxsize=None)
def _result(period: str, seed: int):
    return CloseEngine(_dataset(period, seed)).run()


def _insurance_je(period: str, seed: int):
    return next(
        je
        for je in _result(period, seed).register
        if je.category == "insurance_allocation"
    )


def _applicable_annual(pol: InsurancePolicy, period: str) -> int:
    if period_index(period) >= period_index(pol.renewal_period):
        return pol.renewal_annual_premium_cents
    return pol.annual_premium_cents


def _monthly_total(pol: InsurancePolicy, period: str) -> int:
    offset = months_elapsed(pol.inception_period, period)
    if offset < 0:
        return 0
    return money.split_evenly(_applicable_annual(pol, period), 12)[offset % 12]


def _remaining_after(pol: InsurancePolicy, period: str) -> int:
    """Unamortized premium after the period's entry (mirrors the engine rule)."""
    offset = months_elapsed(pol.inception_period, period)
    if offset < 0:
        return 0
    annual = _applicable_annual(pol, period)
    parts = money.split_evenly(annual, 12)
    return annual - sum(parts[: offset % 12 + 1])


def _policy_credits(je, pol: InsurancePolicy) -> dict[str, int]:
    """Per-entity prepaid-insurance relief posted for one policy."""
    out: dict[str, int] = {}
    for ln in je.lines:
        if ln.account == "1450" and ln.memo == f"Relieve prepaid insurance {pol.policy_id}":
            out[ln.entity] = out.get(ln.entity, 0) + ln.credit
    return out


# --------------------------------------------------------------------------- #
# Generator invariants
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", SEEDS)
def test_the_generator_produces_one_step_up_and_one_flat_policy(seed) -> None:
    policies = _dataset("2026-03", seed).insurance_policies()
    assert len(policies) == 2
    step_up, flat = policies
    # A genuine step-up: the renewal premium is strictly higher.
    assert step_up.renewal_annual_premium_cents > step_up.annual_premium_cents
    # The flat policy renews at the same premium.
    assert flat.renewal_annual_premium_cents == flat.annual_premium_cents


@pytest.mark.parametrize("seed", SEEDS)
def test_every_policy_split_sums_to_one_hundred_percent(seed) -> None:
    for pol in _dataset("2026-03", seed).insurance_policies():
        assert sum(pol.split_bps.values()) == 10000
        assert all(bps > 0 for bps in pol.split_bps.values())


@pytest.mark.parametrize("seed", SEEDS)
def test_policies_renew_on_their_inception_anniversary(seed) -> None:
    for pol in _dataset("2026-03", seed).insurance_policies():
        assert months_elapsed(pol.inception_period, pol.renewal_period) == 12


@pytest.mark.parametrize("seed", SEEDS)
def test_policies_are_deterministic_for_a_seed(seed) -> None:
    a = generate_dataset("2026-03", seed=seed).insurance_policies()
    b = generate_dataset("2026-03", seed=seed).insurance_policies()
    assert a == b


def test_different_seeds_change_the_generated_premiums() -> None:
    fingerprints = {
        tuple(
            (p.annual_premium_cents, p.renewal_annual_premium_cents)
            for p in _dataset("2026-03", seed).insurance_policies()
        )
        for seed in SEEDS
    }
    assert len(fingerprints) > 1


def test_the_dataset_summary_counts_the_insurance_policies() -> None:
    assert "Insurance     : 2" in _dataset("2026-03", 2026).summary()


@pytest.mark.parametrize("period,seed", GRID)
def test_the_opening_trial_balance_seeds_prepaid_insurance(period, seed) -> None:
    ds = _dataset(period, seed)
    accts = {ln.account for ln in ds.opening_tb}
    assert "1450" in accts
    # The opening 1450 balance equals the unamortized premium BEFORE this
    # period's entry: remaining after the entry plus this month's amortization.
    opening = sum(ln.debit - ln.credit for ln in ds.opening_tb if ln.account == "1450")
    expected = sum(
        _remaining_after(pol, period) + _monthly_total(pol, period)
        for pol in ds.insurance_policies()
    )
    assert opening == expected


# --------------------------------------------------------------------------- #
# Largest-remainder allocation exactness
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_entity_shares_sum_exactly_to_the_policy_monthly_total(period, seed) -> None:
    ds = _dataset(period, seed)
    je = _insurance_je(period, seed)
    for pol in ds.insurance_policies():
        posted = sum(_policy_credits(je, pol).values())
        assert posted == _monthly_total(pol, period), (
            f"{pol.policy_id}: entity lines must sum EXACTLY to the policy "
            f"monthly total (no penny lost or created)"
        )


@pytest.mark.parametrize("period,seed", GRID)
def test_entity_shares_follow_the_largest_remainder_method(period, seed) -> None:
    ds = _dataset(period, seed)
    je = _insurance_je(period, seed)
    entities = ds.entities()
    for pol in ds.insurance_policies():
        weights = [pol.split_bps.get(e.code, 0) for e in entities]
        expected = money.allocate_by_ratio(_monthly_total(pol, period), weights)
        posted = _policy_credits(je, pol)
        for ent, share in zip(entities, expected):
            assert posted.get(ent.code, 0) == share


@pytest.mark.parametrize("period,seed", GRID)
def test_expense_debits_mirror_prepaid_relief_per_entity(period, seed) -> None:
    je = _insurance_je(period, seed)
    debit_accts = {ln.account for ln in je.lines if ln.debit}
    credit_accts = {ln.account for ln in je.lines if ln.credit}
    assert debit_accts == {"6400"}
    assert credit_accts == {"1450"}
    # DR insurance expense / CR prepaid insurance within each entity.
    for entity, diff in je.balances_per_entity().items():
        assert diff == 0, f"entity {entity} insurance leg off by {diff}"


@pytest.mark.parametrize("period,seed", GRID)
def test_entities_outside_a_policy_split_get_no_lines(period, seed) -> None:
    ds = _dataset(period, seed)
    je = _insurance_je(period, seed)
    for pol in ds.insurance_policies():
        outside = {e.code for e in ds.entities()} - set(pol.split_bps)
        for ln in je.lines:
            if pol.policy_id in ln.memo:
                assert ln.entity not in outside


@pytest.mark.parametrize("period,seed", GRID)
def test_the_insurance_schedule_has_a_row_per_policy_per_split_entity(
    period, seed
) -> None:
    ds = _dataset(period, seed)
    sched = next(
        s
        for s in _result(period, seed).schedules
        if s.category == "insurance_allocation"
    )
    assert len(sched.rows) == sum(
        len(pol.split_bps) for pol in ds.insurance_policies()
    )
    keys = {row.key for row in sched.rows}
    for pol in ds.insurance_policies():
        for code in pol.split_bps:
            assert f"{pol.policy_id}-{code}" in keys


# --------------------------------------------------------------------------- #
# Renewal step-up
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", SEEDS)
def test_the_step_up_month_books_the_renewal_rate(seed) -> None:
    pol = _dataset("2026-07", seed).insurance_policies()[0]
    renewal_month = _insurance_je("2026-07", seed)
    posted = sum(_policy_credits(renewal_month, pol).values())
    assert posted == money.split_evenly(pol.renewal_annual_premium_cents, 12)[0]
    # The step-up is genuine: the renewal month books strictly more than the
    # last month at the old rate.
    prior_month = _insurance_je("2026-06", seed)
    assert posted > sum(_policy_credits(prior_month, pol).values())


@pytest.mark.parametrize("seed", SEEDS)
def test_before_the_renewal_the_original_premium_amortizes(seed) -> None:
    pol = _dataset("2026-06", seed).insurance_policies()[0]
    je = _insurance_je("2026-06", seed)
    posted = sum(_policy_credits(je, pol).values())
    # 2026-06 is month 12 of the original policy year (inception 2025-07).
    assert posted == money.split_evenly(pol.annual_premium_cents, 12)[11]


@pytest.mark.parametrize("seed", SEEDS)
def test_a_flat_renewal_does_not_change_the_premium_in_force(seed) -> None:
    flat = _dataset("2026-03", seed).insurance_policies()[1]
    engine = CloseEngine(generate_dataset("2026-09", seed=seed))
    before = engine._insurance_applicable_premium(flat)
    engine.period = "2026-10"  # the flat policy's renewal month
    after = engine._insurance_applicable_premium(flat)
    assert before == after == flat.annual_premium_cents


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_the_renewal_policy_year_amortizes_the_full_renewal_premium(seed) -> None:
    pol = _dataset("2026-07", seed).insurance_policies()[0]
    year = [f"2026-{m:02d}" for m in range(7, 13)] + [
        f"2027-{m:02d}" for m in range(1, 7)
    ]
    total = sum(
        sum(_policy_credits(_insurance_je(p, seed), pol).values()) for p in year
    )
    assert total == pol.renewal_annual_premium_cents


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_the_original_policy_year_amortizes_the_full_original_premium(seed) -> None:
    pol = _dataset("2026-01", seed).insurance_policies()[0]
    year = [f"2025-{m:02d}" for m in range(7, 13)] + [
        f"2026-{m:02d}" for m in range(1, 7)
    ]
    total = sum(
        sum(_policy_credits(_insurance_je(p, seed), pol).values()) for p in year
    )
    assert total == pol.annual_premium_cents


# --------------------------------------------------------------------------- #
# Tie to prepaid insurance (account 1450)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_the_insurance_schedule_ties_to_prepaid_insurance(period, seed) -> None:
    result = _result(period, seed)
    tie = next(t for t in result.ties if t.account == "1450")
    assert tie.ties
    assert tie.variance_cents == 0
    assert tie.actual_cents == abs(result.ledger.account_balance("1450"))


@pytest.mark.parametrize("period,seed", GRID)
def test_the_close_stays_clean_with_insurance(period, seed) -> None:
    result = _result(period, seed)
    assert result.clean
    assert result.refused == []


@pytest.mark.parametrize("seed", SEEDS)
def test_remaining_prepaid_insurance_declines_within_a_policy_year(seed) -> None:
    # 2026-01 .. 2026-06 sit inside both policies' original years, so the
    # unamortized balance must fall (or hold) every month.
    expected = [
        next(t for t in _result(f"2026-{m:02d}", seed).ties if t.account == "1450")
        .expected_cents
        for m in range(1, 7)
    ]
    assert expected == sorted(expected, reverse=True)
    assert expected[0] > expected[-1]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_renewal_month_reseeds_a_full_years_premium(seed) -> None:
    policies = _dataset("2026-07", seed).insurance_policies()
    step_up = policies[0]
    june = next(t for t in _result("2026-06", seed).ties if t.account == "1450")
    july = next(t for t in _result("2026-07", seed).ties if t.account == "1450")
    # June is month 12 of the step-up policy's original year: it is fully
    # amortized. July restarts at the renewal premium less one month.
    assert _remaining_after(step_up, "2026-06") == 0
    for period, tie in (("2026-06", june), ("2026-07", july)):
        assert tie.expected_cents == sum(
            _remaining_after(pol, period) for pol in policies
        )
    assert july.expected_cents > june.expected_cents


# --------------------------------------------------------------------------- #
# Per-entity JE correctness and determinism
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("period,seed", GRID)
def test_the_insurance_entry_posts_balanced_and_is_never_refused(period, seed) -> None:
    result = _result(period, seed)
    je = _insurance_je(period, seed)
    assert je.is_balanced
    assert je.total_debits > 0
    assert not any(err.je.category == "insurance_allocation" for err in result.refused)


@pytest.mark.parametrize("seed", SEEDS)
def test_same_seed_same_insurance_entry(seed) -> None:
    def lines(run):
        je = next(
            j for j in run.register if j.category == "insurance_allocation"
        )
        return [(ln.entity, ln.account, ln.debit, ln.credit, ln.memo) for ln in je.lines]

    a = CloseEngine(generate_dataset("2026-05", seed=seed)).run()
    b = CloseEngine(generate_dataset("2026-05", seed=seed)).run()
    assert lines(a) == lines(b)
