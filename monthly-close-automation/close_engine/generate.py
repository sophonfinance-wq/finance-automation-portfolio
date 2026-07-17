"""Synthetic data generator for the close engine.

Produces a fully fictional, seeded dataset for one entity group:

* a chart of accounts,
* three operating entities,
* an opening trial balance that balances per entity, and
* source sub-ledgers: prepaids, fixed assets, leases (deferred rent + CAM),
  fixed-fee accruals, related-party notes, management-fee arrangements, the
  G&A allocation map, and shared insurance policies (one with a mid-year
  renewal step-up), plus signed postage meter detail and approved
  project/job/cost routes.

Everything is generated with ``random.seed(seed)`` so two runs with the same
seed produce byte-identical inputs. No real names, figures, or paths appear.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import money
from .model import Account, AccountType, ChartOfAccounts, JournalLine

# --------------------------------------------------------------------------- #
# Fictional entity group
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Entity:
    """A fictional operating entity in the group."""

    code: str
    name: str


# Obviously-fake entities in a single group.
ENTITIES: list[Entity] = [
    Entity("DH", "Demo Holdings LLC"),
    Entity("MF", "Maple Fund LP"),
    Entity("BW", "Birchwood Op Co"),
]
ENTITY_BY_CODE: dict[str, Entity] = {e.code: e for e in ENTITIES}


# --------------------------------------------------------------------------- #
# Chart of accounts (aligned with the repo's existing fictional samples)
# --------------------------------------------------------------------------- #

CHART: list[Account] = [
    Account("1000", "Cash", AccountType.ASSET),
    Account("1200", "Accounts receivable", AccountType.ASSET),
    Account("1400", "Prepaid expenses", AccountType.ASSET),
    Account("1450", "Prepaid insurance", AccountType.ASSET),
    Account("1460", "Unallocated postage", AccountType.ASSET),
    Account("1500", "Fixed assets - gross", AccountType.ASSET),
    Account("1510", "Accumulated depreciation", AccountType.ASSET),
    Account("1600", "Deferred rent asset", AccountType.ASSET),
    Account("1700", "Note receivable - related party", AccountType.ASSET),
    Account("1800", "Due from affiliates", AccountType.ASSET),
    Account("2000", "Accounts payable", AccountType.LIABILITY),
    Account("2100", "Accrued liabilities", AccountType.LIABILITY),
    Account("2200", "Deferred rent liability", AccountType.LIABILITY),
    Account("2300", "Management fee payable", AccountType.LIABILITY),
    Account("2350", "Fixed fee payable", AccountType.LIABILITY),
    Account("2400", "Accrued interest payable", AccountType.LIABILITY),
    Account("2500", "Note payable - related party", AccountType.LIABILITY),
    Account("2800", "Due to affiliates", AccountType.LIABILITY),
    Account("3000", "Members' equity", AccountType.EQUITY),
    Account("4000", "Revenue", AccountType.REVENUE),
    Account("4900", "Intercompany interest income", AccountType.REVENUE),
    Account("5000", "Cost of services", AccountType.EXPENSE),
    Account("6000", "Rent expense", AccountType.EXPENSE),
    Account("6050", "CAM expense", AccountType.EXPENSE),
    Account("6100", "Depreciation expense", AccountType.EXPENSE),
    Account("6200", "Management fee expense", AccountType.EXPENSE),
    Account("6250", "Fixed fee expense", AccountType.EXPENSE),
    Account("6300", "Interest expense", AccountType.EXPENSE),
    Account("6400", "Insurance expense", AccountType.EXPENSE),
    Account("6500", "Software expense", AccountType.EXPENSE),
    Account("6600", "G&A - allocated", AccountType.EXPENSE),
    Account("6650", "G&A - shared services", AccountType.EXPENSE),
    Account("6700", "Postage and delivery", AccountType.EXPENSE),
]


def chart_of_accounts() -> ChartOfAccounts:
    """Return the chart of accounts as an indexed object."""
    return ChartOfAccounts(CHART)


# --------------------------------------------------------------------------- #
# Sub-ledger record types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Prepaid:
    """A prepaid item amortized straight-line over its service period."""

    item_id: str
    entity: str
    vendor: str
    description: str
    expense_account: str
    total_cents: int
    start_period: str  # YYYY-MM
    term_months: int


@dataclass(frozen=True)
class FixedAsset:
    """A depreciable fixed asset (straight-line, monthly, no salvage)."""

    asset_id: str
    entity: str
    description: str
    cost_cents: int
    in_service_period: str  # YYYY-MM
    useful_life_months: int


@dataclass(frozen=True)
class Lease:
    """A lease driving deferred-rent straight-lining plus monthly CAM.

    The lease is held by ``entity`` but its economic cost is shared across the
    group by a fixed cross-entity split (basis points summing to 10000). The
    non-holder shares are routed through intercompany due-to / due-from.
    """

    lease_id: str
    entity: str  # entity that holds the lease / pays the landlord
    description: str
    cash_rent_schedule_cents: tuple[int, ...]  # escalating contractual rent
    straight_line_cents: int  # level monthly rent expense
    monthly_cam_cents: int
    split_bps: dict[str, int]  # entity -> basis points (sum 10000)


@dataclass(frozen=True)
class Note:
    """A related-party note accruing simple monthly interest."""

    note_id: str
    lender_entity: str
    borrower_entity: str
    principal_cents: int
    annual_rate_bps: int  # e.g. 600 == 6.00%


@dataclass(frozen=True)
class MgmtFee:
    """A monthly management-fee arrangement with possible in-month payments."""

    arrangement_id: str
    payer_entity: str
    monthly_fee_cents: int
    in_month_payment_cents: int  # cash already paid this period (netted)


@dataclass(frozen=True)
class FixedFeeAccrual:
    """A recurring fixed-fee accrual with an explicit liability rollforward.

    ``settlement_cents`` is current-period cash activity already reflected in
    the opening GL presented to the recurring-entry engine. The engine must
    therefore book only the recurring fee plus the signed, approved
    adjustment -- never the settlement a second time.
    """

    arrangement_id: str
    entity: str
    beginning_liability_cents: int
    settlement_cents: int
    monthly_fee_cents: int
    approved_adjustment_cents: int = 0


@dataclass(frozen=True)
class GnaAllocation:
    """The G&A shared-services cost pool and its fixed allocation ratios."""

    pool_entity: str  # entity that incurs the shared-services cost
    monthly_pool_cents: int
    split_bps: dict[str, int]  # entity -> basis points (sum 10000)


@dataclass(frozen=True)
class InsurancePolicy:
    """A shared insurance policy amortized monthly across the group.

    The annual premium is prepaid and expensed one twelfth per month, split
    across entities by ``split_bps`` (basis points summing to 10000). The
    policy renews on its inception anniversary: from ``renewal_period`` on,
    ``renewal_annual_premium_cents`` is the premium in force (a renewal at a
    higher premium is a genuine step-up the close must book that month).
    """

    policy_id: str
    carrier: str
    description: str
    annual_premium_cents: int
    split_bps: dict[str, int]  # entity -> basis points (sum 10000)
    inception_period: str  # YYYY-MM
    renewal_period: str  # YYYY-MM (the inception anniversary)
    renewal_annual_premium_cents: int


@dataclass(frozen=True)
class PostageMeterLine:
    """One signed meter-detail row awaiting an approved project route.

    Positive amounts are charges and negative amounts are refunds. A zero
    line remains visible in the source schedule but deliberately creates no
    journal line.
    """

    line_id: str
    project_code: str
    description: str
    amount_cents: int


@dataclass(frozen=True)
class PostageRoute:
    """Approved exact-match route from project to entity, job, and cost."""

    project_code: str
    recipient_entity: str
    job_code: str
    cost_code: str


@dataclass(frozen=True)
class PostageBatch:
    """A period meter batch and its independently maintained route table.

    Every meter row must match exactly one route. The engine refuses the
    entire batch if a project is unmapped, maps more than once, names an
    entity outside the group, or repeats a meter line id.
    """

    batch_id: str
    period: str
    holder_entity: str
    meter_lines: tuple[PostageMeterLine, ...]
    routes: tuple[PostageRoute, ...]


@dataclass
class SubLedgers:
    """Container for all generated sub-ledger data."""

    prepaids: list[Prepaid] = field(default_factory=list)
    fixed_assets: list[FixedAsset] = field(default_factory=list)
    leases: list[Lease] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    mgmt_fees: list[MgmtFee] = field(default_factory=list)
    gna: GnaAllocation | None = None
    insurance: list[InsurancePolicy] = field(default_factory=list)
    fixed_fee_accruals: list[FixedFeeAccrual] = field(default_factory=list)
    postage_batches: list[PostageBatch] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Period helpers
# --------------------------------------------------------------------------- #


def period_index(period: str) -> int:
    """Convert ``YYYY-MM`` to an absolute month index for arithmetic."""
    year, month = period.split("-")
    return int(year) * 12 + (int(month) - 1)


def months_elapsed(start_period: str, current_period: str) -> int:
    """Return how many months ``current_period`` is after ``start_period``.

    Returns 0 in the start month, 1 the next month, etc. Negative if current
    precedes start.
    """
    return period_index(current_period) - period_index(start_period)


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


def _opening_trial_balance(rng: random.Random) -> list[JournalLine]:
    """Build an opening trial balance that balances within each entity.

    For each entity we seed cash, equity, and a little revenue/expense activity,
    then plug equity so each entity's debits equal its credits exactly.
    """
    lines: list[JournalLine] = []
    for ent in ENTITIES:
        cash = money.to_cents(rng.randint(400, 900) * 1000)
        ar = money.to_cents(rng.randint(50, 200) * 1000)
        fa_gross = money.to_cents(rng.randint(200, 500) * 1000)
        accum_dep = money.to_cents(rng.randint(20, 80) * 1000)
        ap = money.to_cents(rng.randint(30, 120) * 1000)

        debits = [
            JournalLine(ent.code, "1000", cash, 0, "Opening cash"),
            JournalLine(ent.code, "1200", ar, 0, "Opening A/R"),
            JournalLine(ent.code, "1500", fa_gross, 0, "Opening fixed assets"),
        ]
        credits = [
            JournalLine(ent.code, "1510", 0, accum_dep, "Opening accum. dep."),
            JournalLine(ent.code, "2000", 0, ap, "Opening A/P"),
        ]
        # Plug members' equity so the entity balances.
        total_debits = cash + ar + fa_gross
        total_credits = accum_dep + ap
        equity = total_debits - total_credits
        credits.append(
            JournalLine(ent.code, "3000", 0, equity, "Opening equity (plug)")
        )
        lines.extend(debits)
        lines.extend(credits)
    return lines


def _prepaids(rng: random.Random, period: str) -> list[Prepaid]:
    """Generate a handful of prepaids straddling the close period."""
    idx = period_index(period)
    items = [
        ("Demo Insure Co.", "Annual insurance", "6400", 12),
        ("Demo SaaS Inc.", "Software license", "6500", 12),
        ("Birch Services", "Maintenance contract", "5000", 6),
        ("Maple Media", "Advertising retainer", "6650", 9),
    ]
    out: list[Prepaid] = []
    for i, (vendor, desc, acct, term) in enumerate(items):
        ent = ENTITIES[i % len(ENTITIES)].code
        # Start somewhere in the trailing months so it is mid-amortization.
        start_offset = rng.randint(1, term - 1)
        start_idx = idx - start_offset
        start_period = f"{start_idx // 12:04d}-{start_idx % 12 + 1:02d}"
        monthly = rng.choice([500, 750, 1000, 1200])
        total = monthly * term
        out.append(
            Prepaid(
                item_id=f"PP-{i + 1:02d}",
                entity=ent,
                vendor=vendor,
                description=desc,
                expense_account=acct,
                total_cents=money.to_cents(total),
                start_period=start_period,
                term_months=term,
            )
        )
    return out


def _opening_prepaid_balances(
    prepaids: list[Prepaid], period: str
) -> list[JournalLine]:
    """Seed opening prepaid asset balances so the schedule ties to the GL.

    For each prepaid, the opening balance is the unamortized total as of the
    start of the close month (total less every monthly part booked in months
    strictly before the close month). A per-entity equity plug offsets the
    debit so each entity's opening trial balance still balances.

    Args:
        prepaids: The generated prepaid sub-ledger.
        period: Close period ``YYYY-MM``.

    Returns:
        Opening journal lines (debit 1400, credit 3000) per entity.
    """
    by_entity: dict[str, int] = {}
    for pp in prepaids:
        parts = money.split_evenly(pp.total_cents, pp.term_months)
        elapsed = months_elapsed(pp.start_period, period)
        booked_before = max(0, min(elapsed, pp.term_months))
        opening_balance = pp.total_cents - sum(parts[:booked_before])
        by_entity[pp.entity] = by_entity.get(pp.entity, 0) + opening_balance
    lines: list[JournalLine] = []
    for entity, bal in by_entity.items():
        if bal == 0:
            continue
        lines.append(JournalLine(entity, "1400", bal, 0, "Opening prepaid balance"))
        lines.append(
            JournalLine(entity, "3000", 0, bal, "Opening equity (prepaid plug)")
        )
    return lines


def _fixed_assets(rng: random.Random, period: str) -> list[FixedAsset]:
    """Generate fixed assets, including one newly in service this period."""
    idx = period_index(period)
    descs = [
        "Office build-out",
        "Server hardware",
        "Vehicles",
        "Furniture & fixtures",
        "Lab equipment",
    ]
    out: list[FixedAsset] = []
    for i, desc in enumerate(descs):
        ent = ENTITIES[i % len(ENTITIES)].code
        life = rng.choice([36, 48, 60])
        cost = rng.choice([36000, 48000, 60000, 90000, 120000])
        # Most assets are mid-life; the last one goes in service this period.
        if i == len(descs) - 1:
            in_service_idx = idx
        else:
            in_service_idx = idx - rng.randint(2, life - 2)
        in_service = f"{in_service_idx // 12:04d}-{in_service_idx % 12 + 1:02d}"
        out.append(
            FixedAsset(
                asset_id=f"FA-{i + 1:02d}",
                entity=ent,
                description=desc,
                cost_cents=money.to_cents(cost),
                in_service_period=in_service,
                useful_life_months=life,
            )
        )
    return out


def _leases() -> list[Lease]:
    """Generate one shared lease with a fixed cross-entity split.

    The lease is held by Demo Holdings but its cost is shared 50/30/20 across
    the group. Cash rent escalates; straight-line rent is the level average,
    creating a deferred-rent asset/liability. CAM is a flat monthly add-on.
    """
    # Escalating 12-month cash rent (deterministic, fictional).
    cash_schedule = tuple(
        money.to_cents(v)
        for v in (
            10000, 10000, 10000, 10250, 10250, 10250,
            10500, 10500, 10500, 10750, 10750, 10750,
        )
    )
    straight_line = money.to_cents(sum(c / 100 for c in cash_schedule) / 12)
    return [
        Lease(
            lease_id="LSE-01",
            entity="DH",
            description="Headquarters lease (shared)",
            cash_rent_schedule_cents=cash_schedule,
            straight_line_cents=straight_line,
            monthly_cam_cents=money.to_cents(1500),
            split_bps={"DH": 5000, "MF": 3000, "BW": 2000},
        )
    ]


def _notes() -> list[Note]:
    """Generate related-party notes accruing simple monthly interest."""
    return [
        Note(
            note_id="NOTE-01",
            lender_entity="MF",
            borrower_entity="BW",
            principal_cents=money.to_cents(500000),
            annual_rate_bps=600,  # 6.00%
        ),
        Note(
            note_id="NOTE-02",
            lender_entity="DH",
            borrower_entity="MF",
            principal_cents=money.to_cents(250000),
            annual_rate_bps=450,  # 4.50%
        ),
    ]


def _mgmt_fees() -> list[MgmtFee]:
    """Generate management-fee arrangements with an in-month payment to net."""
    return [
        MgmtFee(
            arrangement_id="MGT-01",
            payer_entity="BW",
            monthly_fee_cents=money.to_cents(8000),
            in_month_payment_cents=money.to_cents(3000),  # partial cash paid
        ),
        MgmtFee(
            arrangement_id="MGT-02",
            payer_entity="MF",
            monthly_fee_cents=money.to_cents(6000),
            in_month_payment_cents=money.to_cents(0),
        ),
    ]


def _fixed_fee_accruals() -> list[FixedFeeAccrual]:
    """Generate fixed-fee arrangements with fictional rollforward inputs.

    The settlements are already present in the pre-accrual GL balance. One
    arrangement also carries a positive approved adjustment and the other a
    negative one so both signed-adjustment paths are exercised every run.
    """
    return [
        FixedFeeAccrual(
            arrangement_id="FFA-01",
            entity="DH",
            beginning_liability_cents=money.to_cents(48000),
            settlement_cents=money.to_cents(10000),
            monthly_fee_cents=money.to_cents(7500),
            approved_adjustment_cents=money.to_cents(250),
        ),
        FixedFeeAccrual(
            arrangement_id="FFA-02",
            entity="MF",
            beginning_liability_cents=money.to_cents(18000),
            settlement_cents=money.to_cents(6000),
            monthly_fee_cents=money.to_cents(5000),
            approved_adjustment_cents=-money.to_cents(500),
        ),
    ]


def _opening_fixed_fee_balances(
    arrangements: list[FixedFeeAccrual],
) -> list[JournalLine]:
    """Seed the post-settlement, pre-accrual liability for each entity.

    Current settlements belong to the upstream cash ledger. The recurring
    close therefore receives an opening balance of ``beginning - settlement``
    and posts only the current fee and approved adjustment. A matching equity
    plug preserves a balanced fictional opening trial balance.
    """
    by_entity: dict[str, int] = {}
    for arrangement in arrangements:
        pre_accrual = (
            arrangement.beginning_liability_cents
            - arrangement.settlement_cents
        )
        by_entity[arrangement.entity] = (
            by_entity.get(arrangement.entity, 0) + pre_accrual
        )

    lines: list[JournalLine] = []
    for entity, balance in by_entity.items():
        if balance > 0:
            lines.append(
                JournalLine(
                    entity, "2350", 0, balance, "Opening fixed-fee payable"
                )
            )
            lines.append(
                JournalLine(
                    entity,
                    "3000",
                    balance,
                    0,
                    "Opening equity (fixed-fee plug)",
                )
            )
        elif balance < 0:
            lines.append(
                JournalLine(
                    entity,
                    "2350",
                    -balance,
                    0,
                    "Opening fixed-fee debit balance",
                )
            )
            lines.append(
                JournalLine(
                    entity,
                    "3000",
                    0,
                    -balance,
                    "Opening equity (fixed-fee plug)",
                )
            )
    return lines


def _gna() -> GnaAllocation:
    """Generate the G&A shared-services pool and its 100% allocation ratio."""
    return GnaAllocation(
        pool_entity="DH",
        monthly_pool_cents=money.to_cents(15000),
        split_bps={"DH": 4000, "MF": 3500, "BW": 2500},  # sums to 10000
    )


def _insurance(seed: int, entities: list[Entity]) -> list[InsurancePolicy]:
    """Generate two shared insurance policies (one step-up, one flat renewal).

    The package policy is shared by every entity and renews mid-calendar-year
    at a genuinely HIGHER premium; the umbrella policy covers two entities and
    renews flat. Both renew on their inception anniversary. Amounts and splits
    are drawn from a dedicated seeded stream so this generator never disturbs
    the random sequences consumed by the other sub-ledger generators.
    """
    rng = random.Random(f"insurance-{seed}")
    codes = [e.code for e in entities]
    # Package policy: shared by all entities, renews 8.00%-15.00% higher.
    annual_1 = money.to_cents(rng.choice([18600, 21000, 24600, 27000]))
    step_up_bps = rng.randint(800, 1500)
    renewal_1 = annual_1 * (10000 + step_up_bps) // 10000
    first = rng.randrange(3500, 5001, 100)
    second = rng.randrange(2000, 3501, 100)
    split_1 = {codes[0]: first, codes[1]: second, codes[2]: 10000 - first - second}
    # Umbrella policy: two entities, renews at the same premium (flat).
    annual_2 = money.to_cents(rng.choice([9000, 10800, 12600]))
    lead = rng.randrange(5500, 7001, 100)
    split_2 = {codes[1]: lead, codes[2]: 10000 - lead}
    return [
        InsurancePolicy(
            policy_id="POL-01",
            carrier="Demo Mutual Insurance Co.",
            description="Package policy (property & liability, shared)",
            annual_premium_cents=annual_1,
            split_bps=split_1,
            inception_period="2025-07",
            renewal_period="2026-07",
            renewal_annual_premium_cents=renewal_1,
        ),
        InsurancePolicy(
            policy_id="POL-02",
            carrier="Birch Casualty Ltd.",
            description="Umbrella policy (flat renewal)",
            annual_premium_cents=annual_2,
            split_bps=split_2,
            inception_period="2025-10",
            renewal_period="2026-10",
            renewal_annual_premium_cents=annual_2,
        ),
    ]


def _postage(seed: int, period: str) -> list[PostageBatch]:
    """Generate one fictional meter batch with charges, a refund, and a zero.

    A dedicated seeded stream keeps the postage population deterministic
    without changing any pre-existing generator sequence. The route table is
    deliberately separate from meter detail so the engine must prove exact
    one-to-one routing before it can draft a journal entry.
    """
    rng = random.Random(f"postage-{seed}")
    orchard = money.to_cents(rng.randint(850, 1250))
    cedar = money.to_cents(rng.randint(600, 950))
    harbor = money.to_cents(rng.randint(400, 750))
    refund = -money.to_cents(rng.randint(25, 75))
    return [
        PostageBatch(
            batch_id=f"PST-{period}",
            period=period,
            holder_entity="DH",
            meter_lines=(
                PostageMeterLine(
                    "MTR-001", "PRJ-ORCHARD", "Document delivery", orchard
                ),
                PostageMeterLine(
                    "MTR-002", "PRJ-CEDAR", "Recorded-mail batch", cedar
                ),
                PostageMeterLine(
                    "MTR-003", "PRJ-HARBOR", "Courier dispatch", harbor
                ),
                PostageMeterLine(
                    "MTR-004", "PRJ-CEDAR", "Carrier credit", refund
                ),
                PostageMeterLine(
                    "MTR-005", "PRJ-ORCHARD", "Voided label", 0
                ),
            ),
            routes=(
                PostageRoute(
                    "PRJ-ORCHARD", "DH", "JOB-ORCHARD-01", "COST-MAIL-01"
                ),
                PostageRoute(
                    "PRJ-CEDAR", "MF", "JOB-CEDAR-02", "COST-MAIL-02"
                ),
                PostageRoute(
                    "PRJ-HARBOR", "BW", "JOB-HARBOR-03", "COST-MAIL-03"
                ),
            ),
        )
    ]


def _opening_postage_balances(
    batches: list[PostageBatch], period: str
) -> list[JournalLine]:
    """Seed meter activity into unallocated postage before routing.

    The fictional upstream meter import has already placed the signed batch
    total in account 1460. The recurring engine therefore clears that exact
    balance to project/job expense and intercompany, with an equity plug here
    solely to keep the generated opening trial balance balanced.
    """
    by_holder: dict[str, int] = {}
    for batch in batches:
        if batch.period != period:
            continue
        total = sum(line.amount_cents for line in batch.meter_lines)
        by_holder[batch.holder_entity] = (
            by_holder.get(batch.holder_entity, 0) + total
        )
    lines: list[JournalLine] = []
    for holder, total in sorted(by_holder.items()):
        if total > 0:
            lines.append(
                JournalLine(holder, "1460", total, 0, "Opening meter activity")
            )
            lines.append(
                JournalLine(holder, "3000", 0, total, "Opening postage plug")
            )
        elif total < 0:
            refund = -total
            lines.append(
                JournalLine(holder, "1460", 0, refund, "Opening meter refund")
            )
            lines.append(
                JournalLine(holder, "3000", refund, 0, "Opening postage plug")
            )
    return lines


def _opening_insurance_balances(
    policies: list[InsurancePolicy], period: str
) -> list[JournalLine]:
    """Seed opening prepaid-insurance balances so the schedule ties to the GL.

    Each policy year is a 12-month prepaid of the premium in force (the
    renewal premium from the renewal period onward). The opening balance is
    the unamortized portion of the current policy year as of the START of the
    close month, allocated per entity by the policy split (largest-remainder,
    in group entity order). A per-entity equity plug offsets the debit so
    each entity's opening trial balance still balances.

    Args:
        policies: The generated insurance sub-ledger.
        period: Close period ``YYYY-MM``.

    Returns:
        Opening journal lines (debit 1450, credit 3000) per entity.
    """
    by_entity: dict[str, int] = {}
    for pol in policies:
        offset = months_elapsed(pol.inception_period, period)
        if offset < 0:
            continue
        if period_index(period) >= period_index(pol.renewal_period):
            annual = pol.renewal_annual_premium_cents
        else:
            annual = pol.annual_premium_cents
        parts = money.split_evenly(annual, 12)
        opening = annual - sum(parts[: offset % 12])
        weights = [pol.split_bps.get(e.code, 0) for e in ENTITIES]
        shares = money.allocate_by_ratio(opening, weights)
        for ent, share in zip(ENTITIES, shares):
            by_entity[ent.code] = by_entity.get(ent.code, 0) + share
    lines: list[JournalLine] = []
    for entity, bal in by_entity.items():
        if bal == 0:
            continue
        lines.append(
            JournalLine(entity, "1450", bal, 0, "Opening prepaid insurance")
        )
        lines.append(
            JournalLine(entity, "3000", 0, bal, "Opening equity (insurance plug)")
        )
    return lines


def generate_dataset(period: str, seed: int = 2026) -> "Dataset":
    """Generate a complete, seeded, fictional dataset for ``period``.

    Args:
        period: Close period as ``YYYY-MM``.
        seed: Seed for the ``random`` stream (default 2026).

    Returns:
        A :class:`Dataset` with chart, entities, opening TB, and sub-ledgers.
    """
    rng = random.Random(seed)
    opening = _opening_trial_balance(rng)
    subs = SubLedgers(
        prepaids=_prepaids(rng, period),
        fixed_assets=_fixed_assets(rng, period),
        leases=_leases(),
        notes=_notes(),
        mgmt_fees=_mgmt_fees(),
        fixed_fee_accruals=_fixed_fee_accruals(),
        gna=_gna(),
        insurance=_insurance(seed, ENTITIES),
        postage_batches=_postage(seed, period),
    )
    # Seed the opening prepaid asset balance (account 1400) so the prepaid
    # schedule ties to the GL after this period's amortization. The opening
    # balance is the unamortized prepaid as of the START of the close month
    # (i.e. before this period's entry). Offset with an equity plug per entity
    # so each entity's opening trial balance still balances.
    opening.extend(_opening_prepaid_balances(subs.prepaids, period))
    # Same treatment for prepaid insurance (account 1450): seed the current
    # policy year's unamortized premium so the insurance schedule ties.
    opening.extend(_opening_insurance_balances(subs.insurance, period))
    # Fixed-fee settlements are upstream cash activity, so the recurring
    # engine starts with the post-settlement, pre-accrual payable balance.
    opening.extend(_opening_fixed_fee_balances(subs.fixed_fee_accruals))
    # Meter detail is upstream activity in unallocated postage (1460). The
    # recurring engine must clear it exactly to approved project/job routes.
    opening.extend(_opening_postage_balances(subs.postage_batches, period))
    return Dataset(
        period=period,
        seed=seed,
        coa=chart_of_accounts(),
        entities=list(ENTITIES),
        opening_tb=opening,
        subs=subs,
    )


class Dataset:
    """A complete generated input dataset for one close period."""

    def __init__(
        self,
        period: str,
        seed: int,
        coa: ChartOfAccounts,
        entities: list[Entity],
        opening_tb: list[JournalLine],
        subs: SubLedgers,
    ) -> None:
        self.period = period
        self.seed = seed
        self.coa = coa
        self._entities = entities
        self.opening_tb = opening_tb
        self.subs = subs

    def entities(self) -> list[Entity]:
        """Return the group's entities (stable order)."""
        return self._entities

    def prepaids(self) -> list[Prepaid]:
        """Return the prepaid sub-ledger."""
        return self.subs.prepaids

    def fixed_assets(self) -> list[FixedAsset]:
        """Return the fixed-asset sub-ledger."""
        return self.subs.fixed_assets

    def leases(self) -> list[Lease]:
        """Return the lease sub-ledger."""
        return self.subs.leases

    def notes(self) -> list[Note]:
        """Return the related-party note sub-ledger."""
        return self.subs.notes

    def mgmt_fees(self) -> list[MgmtFee]:
        """Return the management-fee arrangements."""
        return self.subs.mgmt_fees

    def fixed_fees(self) -> list[FixedFeeAccrual]:
        """Return the recurring fixed-fee accrual arrangements."""
        return self.subs.fixed_fee_accruals

    def gna(self) -> GnaAllocation:
        """Return the G&A allocation map (must be present)."""
        assert self.subs.gna is not None
        return self.subs.gna

    def insurance_policies(self) -> list[InsurancePolicy]:
        """Return the shared insurance policy sub-ledger."""
        return self.subs.insurance

    def postage_batches(self) -> list[PostageBatch]:
        """Return meter batches and their approved route tables."""
        return self.subs.postage_batches

    def summary(self) -> str:
        """Return a short human-readable summary of the generated inputs."""
        lines = [
            f"Synthetic close dataset — period {self.period} (seed {self.seed})",
            f"  Entities      : {', '.join(e.code for e in self._entities)}",
            f"  Chart accounts: {sum(1 for _ in self.coa)}",
            f"  Opening TB rows: {len(self.opening_tb)}",
            f"  Prepaids      : {len(self.subs.prepaids)}",
            f"  Fixed assets  : {len(self.subs.fixed_assets)}",
            f"  Leases        : {len(self.subs.leases)}",
            f"  Notes         : {len(self.subs.notes)}",
            f"  Mgmt fees     : {len(self.subs.mgmt_fees)}",
            f"  Fixed fees    : {len(self.subs.fixed_fee_accruals)}",
            f"  Insurance     : {len(self.subs.insurance)}",
            f"  Postage batches: {len(self.subs.postage_batches)}",
            f"  G&A pool      : {money.fmt(self.subs.gna.monthly_pool_cents)}"
            if self.subs.gna
            else "  G&A pool      : (none)",
        ]
        return "\n".join(lines)


def _main(argv: list[str] | None = None) -> int:
    """Standalone generator entrypoint: print a dataset summary.

    Usage::

        python -m close_engine.generate --period 2026-03 --seed 2026
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="close_engine.generate",
        description="Generate and summarize the seeded fictional close dataset.",
    )
    parser.add_argument("--period", default="2026-03", help="Period YYYY-MM.")
    parser.add_argument("--seed", type=int, default=2026, help="Random seed.")
    args = parser.parse_args(argv)
    ds = generate_dataset(args.period, seed=args.seed)
    print(ds.summary())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
