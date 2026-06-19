"""Additional coverage for the synthetic data generator.

Pins down the period arithmetic helpers, the fixed entity group and chart, the
determinism guarantees of the seeded generator, the per-entity opening
trial-balance invariant, and the structural properties of every generated
sub-ledger (prepaids, fixed assets, leases, notes, mgmt fees, G&A).
"""

from __future__ import annotations

import pytest

from close_engine import money
from close_engine.generate import (
    CHART,
    ENTITIES,
    ENTITY_BY_CODE,
    Dataset,
    chart_of_accounts,
    generate_dataset,
    months_elapsed,
    period_index,
)
from close_engine.model import Account


# --------------------------------------------------------------------------- #
# period_index / months_elapsed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "period, expected",
    [
        ("0000-01", 0),
        ("0001-01", 12),
        ("2026-01", 2026 * 12),
        ("2026-12", 2026 * 12 + 11),
        ("2026-03", 2026 * 12 + 2),
    ],
)
def test_period_index_values(period, expected) -> None:
    assert period_index(period) == expected


def test_period_index_is_monotonic_within_year() -> None:
    idxs = [period_index(f"2026-{m:02d}") for m in range(1, 13)]
    assert idxs == sorted(idxs)
    # Consecutive months differ by exactly one.
    assert all(b - a == 1 for a, b in zip(idxs, idxs[1:]))


@pytest.mark.parametrize(
    "start, current, expected",
    [
        ("2026-01", "2026-01", 0),
        ("2026-01", "2026-03", 2),
        ("2025-12", "2026-01", 1),
        ("2026-03", "2026-01", -2),
        ("2025-01", "2026-01", 12),
        ("2024-06", "2026-06", 24),
    ],
)
def test_months_elapsed_values(start, current, expected) -> None:
    assert months_elapsed(start, current) == expected


def test_months_elapsed_is_antisymmetric() -> None:
    assert months_elapsed("2026-01", "2026-07") == -months_elapsed(
        "2026-07", "2026-01"
    )


def test_months_elapsed_crosses_year_boundary() -> None:
    assert months_elapsed("2025-11", "2026-02") == 3


# --------------------------------------------------------------------------- #
# Entity group / chart constants
# --------------------------------------------------------------------------- #


def test_entities_are_three_stable_codes() -> None:
    assert [e.code for e in ENTITIES] == ["DH", "MF", "BW"]


def test_entity_by_code_maps_every_entity() -> None:
    assert set(ENTITY_BY_CODE) == {"DH", "MF", "BW"}
    for code, ent in ENTITY_BY_CODE.items():
        assert ent.code == code


def test_chart_account_codes_unique() -> None:
    codes = [a.code for a in CHART]
    assert len(codes) == len(set(codes))


def test_chart_of_accounts_indexes_all_chart_entries() -> None:
    coa = chart_of_accounts()
    for acct in CHART:
        assert acct.code in coa
        assert coa.get(acct.code) is acct


def test_chart_entries_are_account_instances() -> None:
    assert all(isinstance(a, Account) for a in CHART)


# --------------------------------------------------------------------------- #
# generate_dataset — structure and determinism
# --------------------------------------------------------------------------- #


def test_generate_dataset_returns_dataset_with_fields() -> None:
    ds = generate_dataset("2026-03", seed=2026)
    assert isinstance(ds, Dataset)
    assert ds.period == "2026-03"
    assert ds.seed == 2026
    assert [e.code for e in ds.entities()] == ["DH", "MF", "BW"]


def test_generate_dataset_default_seed() -> None:
    ds = generate_dataset("2026-03")
    assert ds.seed == 2026


def test_generate_dataset_is_deterministic_per_seed() -> None:
    a = generate_dataset("2026-03", seed=7)
    b = generate_dataset("2026-03", seed=7)

    def fingerprint(ds: Dataset):
        return (
            [(l.entity, l.account, l.debit, l.credit) for l in ds.opening_tb],
            [(p.item_id, p.total_cents, p.start_period) for p in ds.prepaids()],
            [(f.asset_id, f.cost_cents, f.in_service_period) for f in ds.fixed_assets()],
        )

    assert fingerprint(a) == fingerprint(b)


def test_generate_dataset_different_seed_changes_opening() -> None:
    a = generate_dataset("2026-03", seed=1)
    b = generate_dataset("2026-03", seed=2)
    a_tb = [(l.entity, l.account, l.debit, l.credit) for l in a.opening_tb]
    b_tb = [(l.entity, l.account, l.debit, l.credit) for l in b.opening_tb]
    assert a_tb != b_tb


@pytest.mark.parametrize("seed", [1, 2026, 99, 12345])
def test_opening_trial_balance_balances_per_entity(seed) -> None:
    ds = generate_dataset("2026-03", seed=seed)
    by_entity: dict[str, int] = {}
    for line in ds.opening_tb:
        by_entity[line.entity] = (
            by_entity.get(line.entity, 0) + line.debit - line.credit
        )
    # Each entity's opening trial balance self-balances (debits == credits).
    for entity, diff in by_entity.items():
        assert diff == 0, f"entity {entity} opening out of balance by {diff}"


@pytest.mark.parametrize("seed", [1, 2026, 99])
def test_opening_trial_balance_aggregate_balances(seed) -> None:
    ds = generate_dataset("2026-03", seed=seed)
    debits = sum(l.debit for l in ds.opening_tb)
    credits = sum(l.credit for l in ds.opening_tb)
    assert debits == credits


# --------------------------------------------------------------------------- #
# Sub-ledger structure
# --------------------------------------------------------------------------- #


def test_prepaids_have_positive_totals_and_known_accounts() -> None:
    ds = generate_dataset("2026-03")
    coa = ds.coa
    prepaids = ds.prepaids()
    assert len(prepaids) == 4
    for pp in prepaids:
        assert pp.total_cents > 0
        assert pp.term_months >= 1
        assert pp.expense_account in coa
        assert pp.entity in ENTITY_BY_CODE


def test_fixed_assets_include_one_new_in_service_this_period() -> None:
    period = "2026-03"
    ds = generate_dataset(period)
    assets = ds.fixed_assets()
    assert len(assets) == 5
    # The last asset goes in service exactly in the close period.
    assert assets[-1].in_service_period == period
    assert months_elapsed(assets[-1].in_service_period, period) == 0


def test_lease_split_sums_to_full_allocation() -> None:
    ds = generate_dataset("2026-03")
    leases = ds.leases()
    assert len(leases) == 1
    lease = leases[0]
    assert sum(lease.split_bps.values()) == 10000
    assert lease.entity == "DH"
    assert set(lease.split_bps) == {"DH", "MF", "BW"}


def test_lease_straight_line_is_average_of_cash_schedule() -> None:
    ds = generate_dataset("2026-03")
    lease = ds.leases()[0]
    expected = money.to_cents(
        sum(c / 100 for c in lease.cash_rent_schedule_cents)
        / len(lease.cash_rent_schedule_cents)
    )
    assert lease.straight_line_cents == expected


def test_notes_are_intercompany_with_positive_principal() -> None:
    ds = generate_dataset("2026-03")
    notes = ds.notes()
    assert len(notes) == 2
    for note in notes:
        assert note.lender_entity != note.borrower_entity
        assert note.principal_cents > 0
        assert note.annual_rate_bps > 0


def test_mgmt_fees_payment_does_not_exceed_fee() -> None:
    ds = generate_dataset("2026-03")
    fees = ds.mgmt_fees()
    assert len(fees) == 2
    for mf in fees:
        assert 0 <= mf.in_month_payment_cents <= mf.monthly_fee_cents


def test_gna_split_sums_to_full_allocation() -> None:
    ds = generate_dataset("2026-03")
    gna = ds.gna()
    assert sum(gna.split_bps.values()) == 10000
    assert gna.pool_entity == "DH"
    assert gna.monthly_pool_cents > 0


def test_dataset_summary_mentions_period_and_seed() -> None:
    ds = generate_dataset("2026-03", seed=2026)
    summary = ds.summary()
    assert "2026-03" in summary
    assert "seed 2026" in summary
    assert "Entities" in summary


def test_opening_prepaid_balance_seeded_for_tie() -> None:
    # The opening TB must include account 1400 (prepaid asset) so the prepaid
    # schedule can tie to the GL.
    ds = generate_dataset("2026-03")
    accts = {l.account for l in ds.opening_tb}
    assert "1400" in accts
