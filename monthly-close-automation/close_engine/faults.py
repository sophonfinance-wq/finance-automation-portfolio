"""Seeded fault injectors for the Close Sentinel guardrail demo.

Each injector forges one specific, realistic close failure on a deep copy of
its input (the original is never mutated) and returns the corrupted copy plus
a one-line description of the damage. Every fault maps to exactly one sentinel
control that must catch it (see :data:`FAULTS`). Other controls may also fire
on the same corruption (a scaled accrual fails the shadow recompute too); the
guardrail demo counts a fault as caught when its EXPECTED control fired -- at
CRITICAL for the blocking controls, and at WARN or above for the
reviewer-escalation control C7.

Faults come in four stages, marked by the ``stage`` attribute on each
injector, because some failures live in the source data and others in the
posted output:

* ``"dataset_pre"``  — corrupt the dataset BEFORE the engine runs (the engine
  then faithfully books bad inputs);
* ``"dataset_post"`` — corrupt the dataset AFTER a clean run (the sub-ledger
  changed but the posted close was never trued up);
* ``"result"``       — corrupt the posted :class:`~close_engine.engine.CloseResult`
  after a clean run (tampering, duplicates, dropped legs);
* ``"prior_result"`` — corrupt a LOCKED prior-period result (a closed period
  quietly rewritten after sign-off).

All data is fictional and seeded; nothing here touches wall-clock time.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Callable

from . import money
from .engine import CloseEngine, CloseResult
from .generate import Dataset, generate_dataset, months_elapsed, period_index
from .model import JournalLine


def _stage(name: str) -> Callable:
    """Mark an injector with the stage at which it corrupts the close."""

    def mark(fn: Callable) -> Callable:
        fn.stage = name
        return fn

    return mark


def _prior_period(period: str) -> str:
    """Return the ``YYYY-MM`` period immediately before ``period``."""
    idx = period_index(period) - 1
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


# --------------------------------------------------------------------------- #
# Injectors (each maps to the control that must catch it)
# --------------------------------------------------------------------------- #


@_stage("dataset_pre")
def inject_unbalanced_opening(dataset: Dataset) -> tuple[Dataset, str]:
    """C1: the opening trial balance arrives with a one-sided line.

    Accounting truth: a trial balance nets to zero before anything posts on
    top of it. The fault appends a one-sided opening debit with no offsetting
    credit (a conversion line loaded without its other half), so the whole
    close starts -- and therefore ends -- out of balance.
    """
    ds = copy.deepcopy(dataset)
    entity = ds.entities()[0].code
    ds.opening_tb.append(
        JournalLine(entity, "1000", 12345, 0, "One-sided conversion line")
    )
    desc = (
        f"one-sided 123.45 opening debit loaded for {entity} with no "
        f"offsetting credit; the opening trial balance no longer nets to zero"
    )
    return ds, desc


@_stage("dataset_post")
def inject_ended_asset_keeps_depreciating(dataset: Dataset) -> tuple[Dataset, str]:
    """C4: a fully depreciated asset keeps contributing depreciation.

    Accounting truth: depreciation stops when the useful life ends. The fault
    shortens an asset's life so it is fully depreciated BEFORE the close
    month, while the posted register (from the clean run) still books its
    monthly charge — the classic recurring entry nobody turned off.
    """
    ds = copy.deepcopy(dataset)
    fa = ds.subs.fixed_assets[0]
    new_life = max(1, months_elapsed(fa.in_service_period, ds.period))
    ds.subs.fixed_assets[0] = replace(fa, useful_life_months=new_life)
    desc = (
        f"{fa.asset_id} useful life shortened to {new_life} months so it is "
        f"fully depreciated before {ds.period}, yet the posted register still "
        f"books its monthly depreciation"
    )
    return ds, desc


@_stage("dataset_post")
def inject_accumulated_over_cost(dataset: Dataset) -> tuple[Dataset, str]:
    """C4: accumulated depreciation exceeds the asset's cost (over-accrual).

    Accounting truth: accumulated depreciation can never exceed cost. The
    fault writes an asset's cost down below the depreciation already booked
    in the clean close (as after a partial disposal nobody trued up), leaving
    the recorded accumulated balance 1.00 above the new cost — the exact
    excess is the reversal candidate the control must quantify.
    """
    ds = copy.deepcopy(dataset)
    fa = ds.subs.fixed_assets[0]
    parts = money.split_evenly(fa.cost_cents, fa.useful_life_months)
    elapsed = months_elapsed(fa.in_service_period, ds.period)
    booked = sum(parts[: max(0, min(elapsed + 1, fa.useful_life_months))])
    new_cost = booked - 100
    ds.subs.fixed_assets[0] = replace(fa, cost_cents=new_cost)
    desc = (
        f"{fa.asset_id} cost written down to {money.fmt(new_cost)}, "
        f"1.00 below the {money.fmt(booked)} of depreciation already "
        f"accumulated in the posted close"
    )
    return ds, desc


@_stage("dataset_pre")
def inject_balance_as_driver(dataset: Dataset) -> tuple[Dataset, str]:
    """C5: the G&A allocation driver is a cumulative balance, not activity.

    Accounting truth: a period allocation must be driven by the period's
    activity. The fault replaces the monthly pool with its cumulative
    year-to-date balance through the close month, so the engine allocates a
    running total as if it were one month of cost.
    """
    ds = copy.deepcopy(dataset)
    gna = ds.subs.gna
    assert gna is not None
    factor = max(2, int(ds.period.split("-")[1]))
    ds.subs.gna = replace(gna, monthly_pool_cents=gna.monthly_pool_cents * factor)
    desc = (
        f"G&A driver replaced with the pool's cumulative {factor}-month "
        f"balance {money.fmt(gna.monthly_pool_cents * factor)} instead of the "
        f"current-period activity {money.fmt(gna.monthly_pool_cents)}"
    )
    return ds, desc


@_stage("dataset_post")
def inject_stale_renewal_row(dataset: Dataset) -> tuple[Dataset, str]:
    """C6: the premium was repriced but the entity share rows were not.

    Accounting truth: when a policy reprices, every entity share must be
    reallocated so the detail still crossfoots to the policy monthly total.
    The fault picks a policy IN FORCE for the close month and raises its
    premium by 20% AFTER the run, leaving the posted entity shares stranded
    at the old rate. In a period before any policy has incepted there is no
    premium in force to reprice, so the fault substitutes a same-class
    crossfoot corruption: the split map itself is broken (dataset
    integrity), which the same control must block.
    """
    ds = copy.deepcopy(dataset)
    in_force = next(
        (
            i
            for i, pol in enumerate(ds.subs.insurance)
            if months_elapsed(pol.inception_period, ds.period) >= 0
        ),
        None,
    )
    if in_force is None:
        pol = ds.subs.insurance[0]
        bad_split = dict(pol.split_bps)
        first = next(iter(bad_split))
        bad_split[first] += 100
        ds.subs.insurance[0] = replace(pol, split_bps=bad_split)
        desc = (
            f"no policy in force in {ds.period} to reprice, so the "
            f"{pol.policy_id} split map is corrupted to "
            f"{sum(bad_split.values())} bps instead (same-class crossfoot "
            f"integrity fault)"
        )
        return ds, desc
    pol = ds.subs.insurance[in_force]
    if period_index(ds.period) >= period_index(pol.renewal_period):
        bumped = replace(
            pol,
            renewal_annual_premium_cents=(
                pol.renewal_annual_premium_cents * 12000 // 10000
            ),
        )
    else:
        bumped = replace(
            pol,
            annual_premium_cents=pol.annual_premium_cents * 12000 // 10000,
        )
    ds.subs.insurance[in_force] = bumped
    desc = (
        f"{pol.policy_id} premium in force repriced 20% higher after the "
        f"close ran; the posted entity shares still crossfoot only to the "
        f"old monthly total"
    )
    return ds, desc


@_stage("result")
def inject_missing_recurring_entry(result: CloseResult) -> tuple[CloseResult, str]:
    """C3: an expected recurring accrual is silently absent.

    Accounting truth: every recurring entry the sub-ledgers imply must post
    every month. The fault drops the management-fee accrual from the register
    — the close looks balanced, but the calendar has a hole.
    """
    res = copy.deepcopy(result)
    res.register = [je for je in res.register if je.category != "mgmt_fee_accrual"]
    desc = (
        "management-fee accrual silently dropped from the register "
        "(expected recurring entry absent for the period)"
    )
    return res, desc


@_stage("result")
def inject_duplicate_entry(result: CloseResult) -> tuple[CloseResult, str]:
    """C3: the same recurring entry posts twice in one period.

    Accounting truth: one period, one posting per (entity, category). The
    fault appends a second copy of the G&A allocation entry, double-charging
    every entity's allocated share.
    """
    res = copy.deepcopy(result)
    gna_je = next(je for je in res.register if je.category == "gna_allocation")
    res.register.append(copy.deepcopy(gna_je))
    desc = (
        "G&A allocation posted twice for the same period "
        "(duplicate (entity, category) in the register)"
    )
    return res, desc


@_stage("result")
def inject_interco_one_sided(result: CloseResult) -> tuple[CloseResult, str]:
    """C2: an intercompany entry lost its far leg.

    Accounting truth: every intercompany charge must mirror to the cent in
    the counterparty. The fault drops the lender's mirror (due-from /
    interest income) for one note; the borrower's accrual posts one-sided.
    Both remaining legs still self-balance, so only the mirror control —
    not the balance control — can see the hole.
    """
    res = copy.deepcopy(result)
    je = next(j for j in res.register if j.category == "note_interest")
    je.lines = [
        ln
        for ln in je.lines
        if not (ln.account in ("1800", "4900") and ln.memo.startswith("NOTE-01"))
    ]
    desc = (
        "lender mirror (due-from / interest income) dropped for NOTE-01; "
        "the borrower's interest accrual posts one-sided"
    )
    return res, desc


@_stage("result")
def inject_uncorroborated_step(result: CloseResult) -> tuple[CloseResult, str]:
    """C7: one entity's recurring accrual steps 50% with no event behind it.

    Accounting truth: a big month-over-month step needs a sub-ledger event
    behind it. The fault scales ONE entity's management-fee accrual lines by
    1.5x (the entry and the entity leg still balance), leaving a 50% step
    that no arrangement change corroborates. The step-change control
    escalates it to the reviewer as WARN; the shadow recompute independently
    blocks the amount difference.
    """
    res = copy.deepcopy(result)
    je = next(j for j in res.register if j.category == "mgmt_fee_accrual")
    target = je.lines[0].entity
    je.lines = [
        replace(ln, debit=ln.debit * 3 // 2, credit=ln.credit * 3 // 2)
        if ln.entity == target
        else ln
        for ln in je.lines
    ]
    desc = (
        f"{target} management-fee accrual scaled 1.5x in the posted register "
        f"(a 50% step with no corroborating sub-ledger event)"
    )
    return res, desc


@_stage("result")
def inject_rounded_total_leg(result: CloseResult) -> tuple[CloseResult, str]:
    """C8: the clearing leg was computed as round(total), not sum-of-lines.

    Accounting truth: a clearing leg must equal the SUM of the rounded detail
    lines, never an independently rounded total. The fault shifts the G&A
    pool-relief credit (and its offsetting due-from) up one cent, creating
    the one-cent drift between detail and clearing leg while the entry — and
    every entity leg — still balances.
    """
    res = copy.deepcopy(result)
    je = next(j for j in res.register if j.category == "gna_allocation")
    new_lines = []
    for ln in je.lines:
        if ln.account == "6650" and ln.credit:
            new_lines.append(replace(ln, credit=ln.credit + 1))
        elif ln.account == "1800" and ln.memo == "Due from affiliates (G&A allocation)":
            new_lines.append(replace(ln, debit=ln.debit + 1))
        else:
            new_lines.append(ln)
    je.lines = new_lines
    desc = (
        "G&A clearing leg recomputed as round(total): one cent of drift vs "
        "the sum of the rounded detail lines (the entry still balances)"
    )
    return res, desc


@_stage("result")
def inject_shadow_tamper(result: CloseResult) -> tuple[CloseResult, str]:
    """C9: one posted amount is off by a single cent from the source data.

    Accounting truth: two independent computations of the same entry must
    agree to the cent. The fault perturbs one prepaid amortization amount by
    one cent on BOTH sides (so the entry still balances) — only an
    independent shadow recomputation from the raw sub-ledger can see it.
    """
    res = copy.deepcopy(result)
    je = next(j for j in res.register if j.category == "prepaid_amortization")
    debit_idx = next(i for i, ln in enumerate(je.lines) if ln.debit)
    credit_idx = next(i for i, ln in enumerate(je.lines) if ln.credit)
    je.lines[debit_idx] = replace(
        je.lines[debit_idx], debit=je.lines[debit_idx].debit + 1
    )
    je.lines[credit_idx] = replace(
        je.lines[credit_idx], credit=je.lines[credit_idx].credit + 1
    )
    desc = (
        "one prepaid amortization amount perturbed by a single cent on both "
        "sides (the entry still balances; only a shadow recompute disagrees)"
    )
    return res, desc


@_stage("prior_result")
def inject_prior_period_mutation(result: CloseResult) -> tuple[CloseResult, str]:
    """C10: a closed, locked prior period is quietly rewritten.

    Accounting truth: once a period is locked, its register is immutable.
    The fault alters one journal line of the prior-period register by a cent
    on both sides (so nothing looks unbalanced); the register hash no longer
    matches a deterministic recompute of the locked period.
    """
    res = copy.deepcopy(result)
    je = res.register[0]
    debit_idx = next(i for i, ln in enumerate(je.lines) if ln.debit)
    credit_idx = next(i for i, ln in enumerate(je.lines) if ln.credit)
    je.lines[debit_idx] = replace(
        je.lines[debit_idx], debit=je.lines[debit_idx].debit + 1
    )
    je.lines[credit_idx] = replace(
        je.lines[credit_idx], credit=je.lines[credit_idx].credit + 1
    )
    desc = (
        f"a journal line in the locked {res.period} register quietly altered "
        f"by one cent after sign-off (the entry still balances)"
    )
    return res, desc


# --------------------------------------------------------------------------- #
# Registry: fault name -> (injector, expected control id), insertion-ordered
# --------------------------------------------------------------------------- #

FAULTS: dict[str, tuple[Callable, str]] = {
    "unbalanced_opening": (inject_unbalanced_opening, "C1"),
    "ended_asset_keeps_depreciating": (inject_ended_asset_keeps_depreciating, "C4"),
    "accumulated_over_cost": (inject_accumulated_over_cost, "C4"),
    "balance_as_driver": (inject_balance_as_driver, "C5"),
    "stale_renewal_row": (inject_stale_renewal_row, "C6"),
    "missing_recurring_entry": (inject_missing_recurring_entry, "C3"),
    "duplicate_entry": (inject_duplicate_entry, "C3"),
    "interco_one_sided": (inject_interco_one_sided, "C2"),
    "uncorroborated_step": (inject_uncorroborated_step, "C7"),
    "rounded_total_leg": (inject_rounded_total_leg, "C8"),
    "shadow_tamper": (inject_shadow_tamper, "C9"),
    "prior_period_mutation": (inject_prior_period_mutation, "C10"),
}


def run_fault_demo(seed: int, period: str, fault_name: str):
    """Inject one named fault, run the close, and return the sentinel verdict.

    Generates the seeded dataset, applies the injector at its declared stage,
    runs the sentinel over the (possibly corrupted) dataset/result pair, and
    returns ``(SentinelReport, description)``. For ``prior_result`` faults the
    prior period is closed cleanly, its MUTATED register is hashed into the
    ``locked`` map (modelling a stored artifact edited after sign-off), and
    the period-lock control compares it against a deterministic recompute.

    The sentinel package is imported lazily inside this function so the fault
    library stays importable before ``close_engine.sentinel`` lands.

    Args:
        seed: Random seed for the synthetic dataset.
        period: Close period ``YYYY-MM``.
        fault_name: A key of :data:`FAULTS`.

    Returns:
        A ``(SentinelReport, description)`` tuple.

    Raises:
        KeyError: If ``fault_name`` is not a registered fault.
    """
    if fault_name not in FAULTS:
        raise KeyError(
            f"unknown fault {fault_name!r}; expected one of {list(FAULTS)}"
        )
    from .sentinel import lock_register, run_sentinel

    injector, _expected_control = FAULTS[fault_name]
    dataset = generate_dataset(period, seed=seed)
    locked: dict[str, str] | None = None
    if injector.stage == "dataset_pre":
        dataset, desc = injector(dataset)
        result = CloseEngine(dataset).run()
    elif injector.stage == "dataset_post":
        result = CloseEngine(dataset).run()
        dataset, desc = injector(dataset)
    elif injector.stage == "result":
        result = CloseEngine(dataset).run()
        result, desc = injector(result)
    else:  # "prior_result"
        prior = _prior_period(period)
        prior_result = CloseEngine(generate_dataset(prior, seed=seed)).run()
        mutated, desc = injector(prior_result)
        locked = {prior: lock_register(mutated)}
        result = CloseEngine(dataset).run()
    report = run_sentinel(dataset, result, locked=locked)
    return report, desc
