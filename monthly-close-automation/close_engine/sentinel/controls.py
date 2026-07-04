"""The ten Close Sentinel controls (C1-C10).

Each control is a pure function ``(dataset, result, ...) -> list[Finding]``
that inspects a finished close and reports what it finds; nothing here ever
mutates the close. Controls re-derive their expectations from the raw
sub-ledgers (never from the engine's intermediate math), so they stay
meaningful even when the engine itself is the thing that is wrong.

Controls are registered in :data:`ALL_CONTROLS` in id order; the runner in
:mod:`close_engine.sentinel.sentinel` executes them in that order.
"""

from __future__ import annotations

import hashlib
import json

from .. import money
from ..engine import CloseEngine, CloseResult
from ..generate import Dataset, generate_dataset, months_elapsed, period_index
from . import shadow
from .findings import Finding, Severity

# A calendar waiver excusing one expected (entity, category) for the period.
Waiver = tuple[str, str, str]  # (entity, category, reason)

# C7 step thresholds: a month-over-month step needs review only above BOTH the
# relative threshold (basis points of the prior amount) and the absolute floor.
STEP_REL_THRESHOLD_BPS = 2000  # 20.00% of the prior period's amount
STEP_ABS_THRESHOLD_CENTS = 100 * 100  # 100.00 in integer cents


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _memo_references(memo: str, ref_id: str) -> bool:
    """True iff ``memo`` cites ``ref_id`` as a whole token.

    Leg identification must be boundary-aware: the id must appear with a
    non-alphanumeric character (or the string edge) on both sides, so
    ``POL-1`` never cross-matches a ``POL-10`` memo the way a bare
    ``startswith``/substring test would.
    """
    start = 0
    while True:
        idx = memo.find(ref_id, start)
        if idx < 0:
            return False
        end = idx + len(ref_id)
        before_ok = idx == 0 or not memo[idx - 1].isalnum()
        after_ok = end == len(memo) or not memo[end].isalnum()
        if before_ok and after_ok:
            return True
        start = idx + 1


def _prior_period(period: str) -> str:
    """Return the ``YYYY-MM`` period immediately before ``period``."""
    idx = period_index(period) - 1
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _entries(result: CloseResult, category: str):
    """Yield the posted entries of one recurring category."""
    return (je for je in result.register if je.category == category)


# --------------------------------------------------------------------------- #
# C1 - re-balance
# --------------------------------------------------------------------------- #


def c1_re_balance(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """Both trial balances and every posted entry must re-balance from raw lines.

    Accounting rule: debits equal credits -- in the opening trial balance
    group-wide, in every posted entry (in aggregate and within each entity
    leg), and in the post-close ledger trial balance. The control re-sums
    every line itself instead of calling the entries' or the ledger's own
    helpers, so a corrupted helper cannot vouch for itself.
    """
    findings: list[Finding] = []

    # The opening trial balance must net to zero group-wide before anything
    # posts on top of it.
    opening_net = sum(
        line.debit - line.credit for line in dataset.opening_tb
    )
    if opening_net != 0:
        findings.append(
            Finding(
                "C1",
                Severity.CRITICAL,
                None,
                "opening trial balance out of balance",
                f"the opening trial balance nets to {money.fmt(opening_net)} "
                f"group-wide instead of zero; the close starts out of "
                f"balance before any entry posts",
            )
        )

    for je in result.register:
        debits = 0
        credits = 0
        per_entity: dict[str, int] = {}
        for line in je.lines:
            debits += line.debit
            credits += line.credit
            net = per_entity.get(line.entity, 0)
            per_entity[line.entity] = net + line.debit - line.credit
        if debits != credits:
            findings.append(
                Finding(
                    "C1",
                    Severity.CRITICAL,
                    None,
                    "journal entry out of balance",
                    f"{je.je_id}: independent re-summation gives debits "
                    f"{money.fmt(debits)} vs credits {money.fmt(credits)} "
                    f"(off by {money.fmt(debits - credits)})",
                )
            )
            continue
        for entity in sorted(per_entity):
            net = per_entity[entity]
            if net != 0:
                findings.append(
                    Finding(
                        "C1",
                        Severity.CRITICAL,
                        entity,
                        "entity leg out of balance",
                        f"{je.je_id}: entity {entity} nets {money.fmt(net)}; "
                        f"every intercompany leg must self-balance",
                    )
                )

    # The post-close ledger trial balance must balance, re-summed from its
    # raw rows.
    tb_debits = 0
    tb_credits = 0
    for _entity, _account, debit, credit in result.ledger.trial_balance():
        tb_debits += debit
        tb_credits += credit
    if tb_debits != tb_credits:
        findings.append(
            Finding(
                "C1",
                Severity.CRITICAL,
                None,
                "post-close trial balance out of balance",
                f"the post-close trial balance re-sums to debits "
                f"{money.fmt(tb_debits)} vs credits {money.fmt(tb_credits)} "
                f"(off by {money.fmt(tb_debits - tb_credits)})",
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# C2 - intercompany mirror
# --------------------------------------------------------------------------- #


def c2_interco_mirror(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """Intercompany legs must exist on both sides and mirror to the cent.

    Accounting rule: a charge into one entity is a receivable in the other;
    a one-sided intercompany posting silently misstates both entities. The
    control pairs each note's borrower accrual with the lender's receivable,
    and each allocation's due-from with the counterparties' due-to.
    """
    findings: list[Finding] = []

    # Related-party notes: borrower payable vs lender receivable, per note.
    note_jes = list(_entries(result, "note_interest"))
    if note_jes:
        for note in dataset.notes():
            borrower_leg = sum(
                line.credit
                for je in note_jes
                for line in je.lines
                if line.account == "2400"
                and _memo_references(line.memo, note.note_id)
            )
            lender_leg = sum(
                line.debit
                for je in note_jes
                for line in je.lines
                if line.account == "1800"
                and _memo_references(line.memo, note.note_id)
            )
            if borrower_leg == 0 and lender_leg == 0:
                continue  # not booked at all; absence belongs to the calendar
            if lender_leg == 0:
                findings.append(
                    Finding(
                        "C2",
                        Severity.CRITICAL,
                        note.lender_entity,
                        "one-sided intercompany entry",
                        f"{note.note_id}: borrower accrues "
                        f"{money.fmt(borrower_leg)} but the lender mirror "
                        f"(due-from / interest income) is absent",
                    )
                )
            elif borrower_leg == 0:
                findings.append(
                    Finding(
                        "C2",
                        Severity.CRITICAL,
                        note.borrower_entity,
                        "one-sided intercompany entry",
                        f"{note.note_id}: lender books "
                        f"{money.fmt(lender_leg)} receivable but the borrower "
                        f"leg (interest expense / accrued interest) is absent",
                    )
                )
            elif borrower_leg != lender_leg:
                findings.append(
                    Finding(
                        "C2",
                        Severity.CRITICAL,
                        None,
                        "intercompany legs do not mirror",
                        f"{note.note_id}: borrower leg "
                        f"{money.fmt(borrower_leg)} vs lender leg "
                        f"{money.fmt(lender_leg)} "
                        f"(off by {money.fmt(lender_leg - borrower_leg)})",
                    )
                )

    # Cross-entity allocations: clearing due-from vs counterparties' due-to.
    for category, label in (
        ("gna_allocation", "G&A allocation"),
        ("deferred_rent_cam", "lease cost share"),
    ):
        for je in _entries(result, category):
            due_from = sum(
                line.debit for line in je.lines if line.account == "1800"
            )
            due_to = sum(
                line.credit for line in je.lines if line.account == "2800"
            )
            if due_from == 0 and due_to == 0:
                continue
            if due_from == 0:
                findings.append(
                    Finding(
                        "C2",
                        Severity.CRITICAL,
                        None,
                        "one-sided intercompany entry",
                        f"{je.je_id}: affiliates owe {money.fmt(due_to)} "
                        f"({label}) but the receivable side "
                        f"(due from affiliates) is absent",
                    )
                )
            elif due_to == 0:
                findings.append(
                    Finding(
                        "C2",
                        Severity.CRITICAL,
                        None,
                        "one-sided intercompany entry",
                        f"{je.je_id}: due-from of {money.fmt(due_from)} "
                        f"({label}) but the payable side "
                        f"(due to affiliates) is absent",
                    )
                )
            elif due_from != due_to:
                findings.append(
                    Finding(
                        "C2",
                        Severity.CRITICAL,
                        None,
                        "intercompany legs do not mirror",
                        f"{je.je_id}: due-from {money.fmt(due_from)} vs "
                        f"due-to {money.fmt(due_to)} ({label}, off by "
                        f"{money.fmt(due_from - due_to)})",
                    )
                )
    return findings


# --------------------------------------------------------------------------- #
# C3 - completeness calendar
# --------------------------------------------------------------------------- #


def c3_completeness_calendar(
    dataset: Dataset,
    result: CloseResult,
    *,
    calendar: list[Waiver] | None = None,
) -> list[Finding]:
    """Every entry the sub-ledgers imply must post exactly once this period.

    Accounting rule: the close calendar is derived from the sub-ledgers, not
    from memory. Active prepaids imply amortization; in-life assets imply
    depreciation; shared leases imply deferred rent; notes imply interest on
    both sides; fee arrangements imply an accrual; the G&A pool and in-force
    policies imply allocations. A missing expected entry or a double posting
    is CRITICAL; an explicit waiver records the miss as INFO instead.
    """
    period = dataset.period
    expected: dict[tuple[str, str], str] = {}

    def expect(entity: str, category: str, why: str) -> None:
        expected.setdefault((entity, category), why)

    for pp in dataset.prepaids():
        offset = months_elapsed(pp.start_period, period)
        if 0 <= offset < pp.term_months:
            expect(pp.entity, "prepaid_amortization", f"active prepaid {pp.item_id}")
    for fa in dataset.fixed_assets():
        offset = months_elapsed(fa.in_service_period, period)
        if 0 <= offset < fa.useful_life_months:
            expect(fa.entity, "depreciation", f"in-life asset {fa.asset_id}")
    year = period.split("-")[0]
    for lease in dataset.leases():
        idx = months_elapsed(f"{year}-01", period)
        if 0 <= idx < len(lease.cash_rent_schedule_cents):
            for entity, bps in lease.split_bps.items():
                if bps > 0:
                    expect(entity, "deferred_rent_cam", f"shared lease {lease.lease_id}")
    for note in dataset.notes():
        expect(note.borrower_entity, "note_interest", f"{note.note_id} (borrower)")
        expect(note.lender_entity, "note_interest", f"{note.note_id} (lender)")
    for mf in dataset.mgmt_fees():
        expect(mf.payer_entity, "mgmt_fee_accrual", f"arrangement {mf.arrangement_id}")
    if dataset.subs.gna is not None:
        for entity, bps in dataset.gna().split_bps.items():
            if bps > 0:
                expect(entity, "gna_allocation", "G&A shared-services pool")
    for pol in dataset.insurance_policies():
        if months_elapsed(pol.inception_period, period) >= 0:
            for entity, bps in pol.split_bps.items():
                if bps > 0:
                    expect(entity, "insurance_allocation", f"in-force policy {pol.policy_id}")

    findings: list[Finding] = []
    waived: set[tuple[str, str]] = set()
    for entity, category, reason in calendar or []:
        waived.add((entity, category))
        findings.append(
            Finding(
                "C3",
                Severity.INFO,
                entity,
                "calendar waiver on file",
                f"({entity}, {category}) waived for {period}: {reason}",
            )
        )

    posted: dict[tuple[str, str], int] = {}
    for je in result.register:
        for entity in sorted(je.entities()):
            key = (entity, je.category)
            posted[key] = posted.get(key, 0) + 1

    for key in sorted(expected):
        if key in waived or posted.get(key, 0) > 0:
            continue
        entity, category = key
        findings.append(
            Finding(
                "C3",
                Severity.CRITICAL,
                entity,
                "expected recurring entry absent",
                f"({entity}, {category}) implied by {expected[key]} has no "
                f"posting in {period}",
            )
        )
    for key in sorted(posted):
        if posted[key] > 1:
            entity, category = key
            findings.append(
                Finding(
                    "C3",
                    Severity.CRITICAL,
                    entity,
                    "duplicate recurring entry",
                    f"({entity}, {category}) posted {posted[key]} times "
                    f"in {period}; one period, one posting",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# C4 - asset life guard
# --------------------------------------------------------------------------- #


def c4_asset_life_guard(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """Depreciation must stop at end of life and never exceed cost.

    Accounting rule: an asset past its useful life contributes zero
    depreciation, and accumulated depreciation can never exceed cost. The
    control recomputes months remaining from the sub-ledger and re-derives
    the accumulated balance from the posted register and the sub-ledger's
    in-service date -- never from the workpaper schedule, so a doctored
    schedule cannot vouch for the balance.
    """
    findings: list[Finding] = []
    dep_jes = list(_entries(result, "depreciation"))

    def booked_this_period(asset_id: str) -> int:
        return sum(
            line.debit
            for je in dep_jes
            for line in je.lines
            if line.account == "6100" and _memo_references(line.memo, asset_id)
        )

    # An expired asset must not book a monthly charge.
    for fa in dataset.fixed_assets():
        elapsed = months_elapsed(fa.in_service_period, dataset.period)
        months_remaining = fa.useful_life_months - elapsed
        if elapsed < 0 or months_remaining > 0:
            continue
        booked = booked_this_period(fa.asset_id)
        if booked:
            findings.append(
                Finding(
                    "C4",
                    Severity.CRITICAL,
                    fa.entity,
                    "fully depreciated asset still depreciating",
                    f"{fa.asset_id} ended its {fa.useful_life_months}-month "
                    f"life before {dataset.period} yet books "
                    f"{money.fmt(booked)} this period (monthly overstatement "
                    f"{money.fmt(booked)})",
                )
            )

    # Accumulated depreciation, independently re-derived, must never exceed
    # the asset's cost per the sub-ledger. Straight-line parts are equal in
    # every month before the final plug month, so the accumulation through
    # the period is the register's posted monthly charge times the months in
    # service; the posted register -- not the workpaper schedule -- is the
    # evidence.
    for fa in dataset.fixed_assets():
        elapsed = months_elapsed(fa.in_service_period, dataset.period)
        if elapsed < 0 or elapsed >= fa.useful_life_months - 1:
            # Expired assets belong to the branch above; the final (plug)
            # month breaks the equal-parts inference.
            continue
        monthly = booked_this_period(fa.asset_id)
        if monthly == 0:
            continue  # absence of the charge belongs to the calendar (C3)
        accumulated = monthly * (elapsed + 1)
        if accumulated > fa.cost_cents:
            excess = accumulated - fa.cost_cents
            findings.append(
                Finding(
                    "C4",
                    Severity.CRITICAL,
                    fa.entity,
                    "accumulated depreciation exceeds cost",
                    f"{fa.asset_id}: accumulated depreciation re-derived "
                    f"from the sub-ledger and the posted register is "
                    f"{money.fmt(accumulated)} ({elapsed + 1} months at "
                    f"{money.fmt(monthly)}) vs cost "
                    f"{money.fmt(fa.cost_cents)}; the excess "
                    f"{money.fmt(excess)} is the reversal candidate",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# C5 - driver provenance
# --------------------------------------------------------------------------- #


def c5_driver_provenance(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """The G&A driver must be the pool's period activity, re-pulled from source.

    Accounting rule: a period allocation is driven by that period's activity,
    never by a cumulative balance. Provenance means re-deriving the driver
    from the system of record instead of trusting the workpaper figure; in
    this demonstration the seeded generator IS the system of record, so the
    control re-pulls the pool's period activity from it and compares the
    driver actually used in the posted register.
    """
    gna_jes = list(_entries(result, "gna_allocation"))
    if not gna_jes or dataset.subs.gna is None:
        return []  # absence of the allocation belongs to the calendar (C3)
    driver = sum(
        line.credit
        for je in gna_jes
        for line in je.lines
        if line.account == "6650"
    )
    source = generate_dataset(result.period, seed=result.seed)
    activity = source.gna().monthly_pool_cents
    if driver == activity:
        return []
    month_no = int(result.period.split("-")[1])
    if month_no >= 2 and driver == activity * month_no:
        subject = "cumulative balance used as allocation driver"
        detail = (
            f"G&A driver {money.fmt(driver)} equals the pool's "
            f"{month_no}-month year-to-date balance, not the current-period "
            f"activity {money.fmt(activity)}"
        )
    else:
        subject = "allocation driver does not match period activity"
        detail = (
            f"G&A driver {money.fmt(driver)} vs current-period activity "
            f"{money.fmt(activity)} re-derived from the source sub-ledger"
        )
    return [
        Finding("C5", Severity.CRITICAL, source.gna().pool_entity, subject, detail)
    ]


# --------------------------------------------------------------------------- #
# C6 - crossfoot
# --------------------------------------------------------------------------- #


def c6_crossfoot(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """Entity insurance shares must crossfoot; split maps must be valid.

    Accounting rule: when a policy reprices, every entity share reallocates
    so the detail still sums to the policy's monthly amortization -- a
    repriced premium with stranded old shares understates the close. Every
    allocation split map (leases, the G&A pool, insurance policies) must
    also pass dataset integrity: exactly 10000 basis points, naming only
    entities inside the group.
    """
    findings: list[Finding] = []
    ins_jes = list(_entries(result, "insurance_allocation"))
    for pol in dataset.insurance_policies():
        offset = months_elapsed(pol.inception_period, dataset.period)
        if offset < 0:
            expected_total = 0
        else:
            if period_index(dataset.period) >= period_index(pol.renewal_period):
                annual = pol.renewal_annual_premium_cents
            else:
                annual = pol.annual_premium_cents
            expected_total = money.split_evenly(annual, 12)[offset % 12]
        allocated = sum(
            line.debit
            for je in ins_jes
            for line in je.lines
            if line.account == "6400"
            and _memo_references(line.memo, pol.policy_id)
        )
        if allocated != expected_total:
            stranded = expected_total - allocated
            findings.append(
                Finding(
                    "C6",
                    Severity.CRITICAL,
                    None,
                    "entity shares do not crossfoot to the policy monthly total",
                    f"{pol.policy_id}: entity shares sum to "
                    f"{money.fmt(allocated)} but the policy's monthly "
                    f"amortization in force is {money.fmt(expected_total)}; "
                    f"{money.fmt(stranded)} is stranded (unallocated "
                    f"remainder)",
                )
            )

    # Dataset integrity: every split map must sum to exactly 10000 bps and
    # may only name entities inside the group. The engine refuses to post on
    # such a map; the control independently blocks the close.
    codes = {e.code for e in dataset.entities()}
    split_maps: list[tuple[str, dict[str, int]]] = [
        (lease.lease_id, lease.split_bps) for lease in dataset.leases()
    ]
    if dataset.subs.gna is not None:
        split_maps.append(
            ("G&A shared-services pool", dataset.subs.gna.split_bps)
        )
    split_maps.extend(
        (pol.policy_id, pol.split_bps) for pol in dataset.insurance_policies()
    )
    for key, split in split_maps:
        problems: list[str] = []
        total_bps = sum(split.values())
        if total_bps != 10000:
            problems.append(
                f"split_bps sums to {total_bps} bps "
                f"({total_bps - 10000:+d} bps vs the required 10000)"
            )
        unknown = sorted(set(split) - codes)
        if unknown:
            problems.append(
                f"split_bps names entities outside the group: "
                f"{', '.join(unknown)}"
            )
        if problems:
            findings.append(
                Finding(
                    "C6",
                    Severity.CRITICAL,
                    None,
                    "allocation split map fails dataset integrity",
                    f"{key}: " + "; ".join(problems),
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# C7 - step change
# --------------------------------------------------------------------------- #


def _corroborating_event(
    dataset: Dataset, entity: str, category: str
) -> str | None:
    """Return a sub-ledger event of ``entity`` explaining a step in ``category``.

    Corroboration is scoped to the entity whose amount stepped: an event in
    one entity's sub-ledger cannot vouch for a movement in another entity.
    Both directions have events -- inceptions, renewals, and in-service dates
    explain step-ups; item expiry and end-of-life explain step-downs.
    """
    period = dataset.period
    if category == "insurance_allocation":
        for pol in dataset.insurance_policies():
            if pol.split_bps.get(entity, 0) <= 0:
                continue
            if pol.renewal_period == period:
                return f"{pol.policy_id} renewal repricing effective {period}"
            if pol.inception_period == period:
                return f"{pol.policy_id} incepted {period}"
    elif category == "depreciation":
        for fa in dataset.fixed_assets():
            if fa.entity != entity:
                continue
            if fa.in_service_period == period:
                return f"{fa.asset_id} placed in service {period}"
            if months_elapsed(fa.in_service_period, period) == fa.useful_life_months:
                return f"{fa.asset_id} reached end of life before {period}"
    elif category == "prepaid_amortization":
        for pp in dataset.prepaids():
            if pp.entity != entity:
                continue
            if pp.start_period == period:
                return f"new prepaid {pp.item_id} starting {period}"
            if months_elapsed(pp.start_period, period) == pp.term_months:
                return f"prepaid {pp.item_id} expired before {period}"
    return None


def c7_step_change(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """A big month-over-month step needs a sub-ledger event behind it.

    Accounting rule: recurring entries move smoothly; a step -- up or down,
    measured as the absolute delta -- above BOTH
    :data:`STEP_REL_THRESHOLD_BPS` and :data:`STEP_ABS_THRESHOLD_CENTS`
    against the prior period's independently recomputed amount must be
    corroborated by a sub-ledger event of the SAME entity (a renewal
    repricing, a new asset in service, a new prepaid, an item expiring or
    reaching end of life). Corroborated steps are noted as INFO; steps with
    no event behind them are WARN for the reviewer.
    """
    prior = _prior_period(result.period)
    prior_expected = shadow.expected_amounts(
        generate_dataset(prior, seed=result.seed)
    )
    prior_by_pair: dict[tuple[str, str], int] = {}
    for (entity, category, _account), (debit, _credit) in prior_expected.items():
        pair = (entity, category)
        prior_by_pair[pair] = prior_by_pair.get(pair, 0) + debit
    current_by_pair: dict[tuple[str, str], int] = {}
    for je in result.register:
        for line in je.lines:
            pair = (line.entity, je.category)
            current_by_pair[pair] = current_by_pair.get(pair, 0) + line.debit

    findings: list[Finding] = []
    for pair in sorted(set(prior_by_pair) & set(current_by_pair)):
        prior_amount = prior_by_pair[pair]
        current_amount = current_by_pair[pair]
        if prior_amount <= 0:
            continue
        step = current_amount - prior_amount
        # A step (in either direction) needs review only above BOTH the
        # relative and the absolute threshold.
        if (
            abs(step) * 10000 <= prior_amount * STEP_REL_THRESHOLD_BPS
            or abs(step) <= STEP_ABS_THRESHOLD_CENTS
        ):
            continue
        entity, category = pair
        percent = abs(step) * 100 / prior_amount
        movement = (
            f"({entity}, {category}) moved {money.fmt(prior_amount)} -> "
            f"{money.fmt(current_amount)} ({percent:.1f}% step)"
        )
        direction = "step-up" if step > 0 else "step-down"
        event = _corroborating_event(dataset, entity, category)
        if event:
            findings.append(
                Finding(
                    "C7",
                    Severity.INFO,
                    entity,
                    "step change corroborated by sub-ledger event",
                    f"{movement}; {direction} explained by {event}",
                )
            )
        else:
            findings.append(
                Finding(
                    "C7",
                    Severity.WARN,
                    entity,
                    "unexplained step change",
                    f"{movement}; no corroborating sub-ledger event in "
                    f"{result.period}",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# C8 - rounding policy
# --------------------------------------------------------------------------- #


def c8_rounding_policy(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """Clearing legs must equal the sum of the rounded detail lines.

    Accounting rule: in a multi-line allocation the clearing (summary) leg is
    the SUM of the rounded per-line amounts -- never an independently rounded
    total. One cent of drift between detail and clearing silently strands a
    penny in the group.
    """
    findings: list[Finding] = []

    # G&A: the pool-relief clearing leg vs the allocated detail lines.
    for je in _entries(result, "gna_allocation"):
        detail_sum = sum(
            line.debit for line in je.lines if line.account == "6600"
        )
        clearing = sum(
            line.credit for line in je.lines if line.account == "6650"
        )
        if clearing != detail_sum:
            drift = clearing - detail_sum
            findings.append(
                Finding(
                    "C8",
                    Severity.CRITICAL,
                    None,
                    "rounding drift between detail and clearing leg",
                    f"{je.je_id}: clearing leg {money.fmt(clearing)} vs sum "
                    f"of rounded detail lines {money.fmt(detail_sum)} "
                    f"({money.fmt(drift)} drift; the clearing leg must be "
                    f"the sum of the rounded lines, never round(total))",
                )
            )

    # Insurance: each policy's prepaid relief vs its rounded expense lines.
    ins_jes = list(_entries(result, "insurance_allocation"))
    for pol in dataset.insurance_policies():
        expense = sum(
            line.debit
            for je in ins_jes
            for line in je.lines
            if line.account == "6400"
            and _memo_references(line.memo, pol.policy_id)
        )
        relief = sum(
            line.credit
            for je in ins_jes
            for line in je.lines
            if line.account == "1450"
            and _memo_references(line.memo, pol.policy_id)
        )
        if expense == 0 and relief == 0:
            continue
        if expense != relief:
            drift = relief - expense
            findings.append(
                Finding(
                    "C8",
                    Severity.CRITICAL,
                    None,
                    "rounding drift between detail and clearing leg",
                    f"{pol.policy_id}: prepaid relief {money.fmt(relief)} vs "
                    f"sum of rounded expense lines {money.fmt(expense)} "
                    f"({money.fmt(drift)} drift)",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# C9 - shadow recompute
# --------------------------------------------------------------------------- #


def c9_shadow_recompute(dataset: Dataset, result: CloseResult) -> list[Finding]:
    """Two independent computations must agree to the cent before post.

    Accounting rule: the posted register must match a fully independent
    recomputation of every recurring amount from the raw sub-ledgers (see
    :mod:`close_engine.sentinel.shadow`). Any cent of disagreement -- on
    either side -- is CRITICAL.
    """
    expected = shadow.expected_amounts(dataset)
    actual: dict[tuple[str, str, str], tuple[int, int]] = {}
    for je in result.register:
        for line in je.lines:
            key = (line.entity, je.category, line.account)
            debits, credits = actual.get(key, (0, 0))
            actual[key] = (debits + line.debit, credits + line.credit)

    findings: list[Finding] = []
    for key in sorted(set(expected) | set(actual)):
        expected_dc = expected.get(key, (0, 0))
        actual_dc = actual.get(key, (0, 0))
        if expected_dc == actual_dc:
            continue
        entity, category, account = key
        findings.append(
            Finding(
                "C9",
                Severity.CRITICAL,
                entity,
                "shadow recomputation disagrees",
                f"({entity}, {category}, {account}): posted debit/credit "
                f"{money.fmt(actual_dc[0])}/{money.fmt(actual_dc[1])} vs "
                f"shadow {money.fmt(expected_dc[0])}/"
                f"{money.fmt(expected_dc[1])}",
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# C10 - period lock
# --------------------------------------------------------------------------- #


def lock_register(result: CloseResult) -> str:
    """Hash a close's register for the period lock (sha256, canonical JSON).

    Accounting rule: once a period is signed off, its register is immutable;
    the lock is a content hash a later run can verify against a
    deterministic recompute.
    """
    payload = {
        "period": result.period,
        "seed": result.seed,
        "register": [
            {
                "je_id": je.je_id,
                "period": je.period,
                "category": je.category,
                "description": je.description,
                "lines": [
                    {
                        "entity": line.entity,
                        "account": line.account,
                        "debit": line.debit,
                        "credit": line.credit,
                        "memo": line.memo,
                    }
                    for line in je.lines
                ],
            }
            for je in result.register
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def c10_period_lock(
    dataset: Dataset,
    result: CloseResult,
    *,
    locked: dict[str, str] | None = None,
) -> list[Finding]:
    """A locked period's register hash must match a deterministic recompute.

    Accounting rule: a closed period cannot be quietly rewritten. For every
    ``{period: hash}`` on file, the control re-closes that period from the
    seeded source data and compares register hashes; any difference means the
    signed-off artifact was altered after the fact.
    """
    if not locked:
        return []
    findings: list[Finding] = []
    for period in sorted(locked):
        recomputed = CloseEngine(
            generate_dataset(period, seed=result.seed)
        ).run()
        recomputed_hash = lock_register(recomputed)
        if recomputed_hash != locked[period]:
            findings.append(
                Finding(
                    "C10",
                    Severity.CRITICAL,
                    None,
                    "closed period mutated",
                    f"locked register hash for {period} is "
                    f"{locked[period][:12]}.. but a deterministic recompute "
                    f"gives {recomputed_hash[:12]}..; the closed period was "
                    f"altered after sign-off",
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Registry (id order; the runner executes in this order)
# --------------------------------------------------------------------------- #

ALL_CONTROLS = [
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
]
