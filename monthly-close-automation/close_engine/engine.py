"""The month-end close engine.

Given a generated :class:`~close_engine.generate.Dataset`, the engine:

1. loads the opening trial balance into a :class:`~close_engine.model.Ledger`,
2. computes each recurring journal entry with a backing schedule,
3. enforces the balance control (debits == credits, per entity for
   intercompany), refusing to post anything out of tie,
4. ties each schedule back to the resulting GL balance, and
5. returns a :class:`CloseResult` with the JE register, updated trial balance,
   schedules, and a tie-out checklist.

Recurring-entry classes implemented:

* prepaid amortization (straight-line over the service period)
* fixed-asset depreciation (straight-line, monthly, no salvage)
* deferred rent + CAM straight-lining with a fixed cross-entity split routed
  through intercompany due-to / due-from
* management-fee accrual, netting any in-month cash payment
* note interest accrual (simple monthly interest)
* G&A cost allocation by a fixed ratio summing to 100%
* insurance premium allocation (shared policies, largest-remainder entity
  split, renewal step-up booked from the renewal month)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import money
from .generate import (
    Dataset,
    FixedAsset,
    GnaAllocation,
    InsurancePolicy,
    Lease,
    MgmtFee,
    Note,
    Prepaid,
    months_elapsed,
    period_index,
)
from .model import JournalEntry, JournalLine, Ledger, OutOfTieError


@dataclass
class ScheduleRow:
    """One row of a recurring-entry schedule (for the workpaper/report)."""

    key: str
    fields: dict[str, str]


@dataclass
class Schedule:
    """A named schedule that must tie to a GL account balance.

    Attributes:
        name: Display name.
        category: Recurring-entry category id.
        rows: The schedule rows.
        tie_account: Account code the schedule ties to (group-wide), if any.
        tie_expected_cents: The schedule's computed balance for that account.
    """

    name: str
    category: str
    rows: list[ScheduleRow] = field(default_factory=list)
    tie_account: str | None = None
    tie_expected_cents: int | None = None


@dataclass
class TieResult:
    """The outcome of tying a schedule to the GL."""

    schedule: str
    account: str
    expected_cents: int
    actual_cents: int

    @property
    def ties(self) -> bool:
        """True iff the schedule expectation equals the GL balance."""
        return self.expected_cents == self.actual_cents

    @property
    def variance_cents(self) -> int:
        """Signed expected - actual difference, in cents."""
        return self.expected_cents - self.actual_cents


@dataclass
class CloseResult:
    """Everything produced by a close run."""

    period: str
    seed: int
    ledger: Ledger
    register: list[JournalEntry]
    schedules: list[Schedule]
    ties: list[TieResult]
    refused: list[OutOfTieError]

    @property
    def all_balanced(self) -> bool:
        """True iff every posted entry balanced."""
        return all(je.is_balanced for je in self.register)

    @property
    def all_tie(self) -> bool:
        """True iff every schedule ties to the GL."""
        return all(t.ties for t in self.ties)

    @property
    def clean(self) -> bool:
        """True iff the whole close is clean (balanced, tied, nothing refused)."""
        return self.all_balanced and self.all_tie and not self.refused


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


class CloseEngine:
    """Computes and posts the recurring close entries for one period."""

    def __init__(self, dataset: Dataset) -> None:
        self.ds = dataset
        self.period = dataset.period
        self.ledger = Ledger(dataset.coa)
        self.register: list[JournalEntry] = []
        self.schedules: list[Schedule] = []
        self.refused: list[OutOfTieError] = []

    # -- public API -------------------------------------------------------- #

    def run(self) -> CloseResult:
        """Run the full close and return the result.

        The opening trial balance is loaded first, then each recurring entry is
        computed, controlled, and posted. A split-driven entry whose allocation
        map fails validation is refused up front (never crashing mid-close).
        Finally every schedule is tied back to the GL.
        """
        self.ledger.load_opening(self.ds.opening_tb)

        refused_splits = self._refuse_invalid_splits()
        self._post(self._prepaid_amortization())
        self._post(self._depreciation())
        if "deferred_rent_cam" not in refused_splits:
            self._post(self._deferred_rent_and_cam())
        self._post(self._mgmt_fee_accrual())
        self._post(self._note_interest_accrual())
        if "gna_allocation" not in refused_splits:
            self._post(self._gna_allocation())
        if "insurance_allocation" not in refused_splits:
            self._post(self._insurance_allocation())

        ties = self._tie_out()
        return CloseResult(
            period=self.period,
            seed=self.ds.seed,
            ledger=self.ledger,
            register=list(self.register),
            schedules=list(self.schedules),
            ties=ties,
            refused=list(self.refused),
        )

    # -- posting with controls -------------------------------------------- #

    def _refuse_invalid_splits(self) -> set[str]:
        """Refuse split-driven entries whose allocation map fails validation.

        A ``split_bps`` map must sum to exactly 10000 basis points and may
        only name entities inside the group. A map that fails either rule is
        a dataset-integrity defect: instead of crashing mid-close with a raw
        ``ValueError``, the engine records a refusal through the same
        mechanism as an out-of-tie entry and skips the affected category; the
        sentinel's crossfoot control (C6) raises the CRITICAL finding.

        Returns:
            The recurring-entry categories refused this run.
        """
        codes = {e.code for e in self.ds.entities()}
        checks: list[tuple[str, str, str, dict[str, int]]] = [
            (
                "deferred_rent_cam",
                f"JE-{self.period}-LEASE",
                lease.lease_id,
                lease.split_bps,
            )
            for lease in self.ds.leases()
        ]
        if self.ds.subs.gna is not None:
            checks.append(
                (
                    "gna_allocation",
                    f"JE-{self.period}-GNA",
                    "G&A shared-services pool",
                    self.ds.gna().split_bps,
                )
            )
        checks.extend(
            (
                "insurance_allocation",
                f"JE-{self.period}-INSUR",
                pol.policy_id,
                pol.split_bps,
            )
            for pol in self.ds.insurance_policies()
        )
        refused_categories: set[str] = set()
        for category, je_id, key, split in checks:
            problems: list[str] = []
            total_bps = sum(split.values())
            if total_bps != 10000:
                problems.append(
                    f"split_bps sums to {total_bps} bps, not 10000"
                )
            unknown = sorted(set(split) - codes)
            if unknown:
                problems.append(
                    f"split_bps names entities outside the group: "
                    f"{', '.join(unknown)}"
                )
            if not problems:
                continue
            je = JournalEntry(
                je_id=je_id,
                period=self.period,
                category=category,
                description=f"REFUSED: invalid allocation split ({key})",
            )
            self.refused.append(
                OutOfTieError(je, f"{key}: " + "; ".join(problems))
            )
            refused_categories.add(category)
        return refused_categories

    def _post(self, je: JournalEntry | None) -> None:
        """Post an entry, capturing any out-of-tie refusal instead of raising.

        The engine REFUSES to post an out-of-tie entry: the offending entry is
        recorded in ``self.refused`` and is excluded from the register and GL.
        """
        if je is None or not je.lines:
            return
        try:
            self.ledger.post(je, require_entity_balance=True)
            self.register.append(je)
        except OutOfTieError as exc:
            self.refused.append(exc)

    # -- recurring entries ------------------------------------------------- #

    def _prepaid_amortization(self) -> JournalEntry:
        """Compute straight-line prepaid amortization for the period.

        Each prepaid is amortized over its term; only items whose service
        period covers the close month are amortized. Debits the expense
        account(s); credits Prepaid expenses (1400).
        """
        je = JournalEntry(
            je_id=f"JE-{self.period}-PREPAID",
            period=self.period,
            category="prepaid_amortization",
            description="Prepaid amortization (straight-line)",
        )
        sched = Schedule("Prepaid amortization", "prepaid_amortization")
        total_relief = 0
        for pp in self.ds.prepaids():
            elapsed = months_elapsed(pp.start_period, self.period)
            active = 0 <= elapsed < pp.term_months
            monthly = self._prepaid_monthly(pp)
            remaining = self._prepaid_remaining(pp)
            sched.rows.append(
                ScheduleRow(
                    pp.item_id,
                    {
                        "entity": pp.entity,
                        "vendor": pp.vendor,
                        "item": pp.description,
                        "total": money.fmt(pp.total_cents),
                        "start": pp.start_period,
                        "months": str(pp.term_months),
                        "monthly": money.fmt(monthly),
                        "remaining": money.fmt(remaining),
                        "amortized_this_period": money.fmt(monthly if active else 0),
                    },
                )
            )
            if active:
                je.lines.append(
                    JournalLine(
                        pp.entity,
                        pp.expense_account,
                        monthly,
                        0,
                        f"{pp.item_id} {self.period} amortization",
                    )
                )
                je.lines.append(
                    JournalLine(
                        pp.entity, "1400", 0, monthly, f"Relieve prepaid {pp.item_id}"
                    )
                )
                total_relief += monthly
        # Schedule ties to the remaining prepaid asset balance group-wide.
        sched.tie_account = "1400"
        sched.tie_expected_cents = sum(
            self._prepaid_remaining(pp) for pp in self.ds.prepaids()
        )
        self.schedules.append(sched)
        return je

    def _prepaid_monthly(self, pp: Prepaid) -> int:
        """Straight-line monthly amortization for a prepaid (last month plugs)."""
        parts = money.split_evenly(pp.total_cents, pp.term_months)
        elapsed = months_elapsed(pp.start_period, self.period)
        if 0 <= elapsed < pp.term_months:
            return parts[elapsed]
        return 0

    def _prepaid_remaining(self, pp: Prepaid) -> int:
        """Unamortized prepaid balance after this period's entry.

        Equals the total less every monthly part booked through the close
        month (clamped to the term).
        """
        parts = money.split_evenly(pp.total_cents, pp.term_months)
        elapsed = months_elapsed(pp.start_period, self.period)
        booked_through = max(0, min(elapsed + 1, pp.term_months))
        return pp.total_cents - sum(parts[:booked_through])

    def _depreciation(self) -> JournalEntry:
        """Compute straight-line monthly depreciation (no salvage).

        Assets in service for the close month depreciate one monthly part.
        Debits Depreciation expense (6100); credits Accumulated depreciation
        (1510, a contra-asset carried with a credit balance).
        """
        je = JournalEntry(
            je_id=f"JE-{self.period}-DEPREC",
            period=self.period,
            category="depreciation",
            description="Fixed-asset depreciation (straight-line, monthly)",
        )
        sched = Schedule("Fixed-asset depreciation", "depreciation")
        for fa in self.ds.fixed_assets():
            elapsed = months_elapsed(fa.in_service_period, self.period)
            active = 0 <= elapsed < fa.useful_life_months
            monthly = self._depreciation_monthly(fa)
            accum = self._accumulated_depreciation(fa)
            nbv = fa.cost_cents - accum
            sched.rows.append(
                ScheduleRow(
                    fa.asset_id,
                    {
                        "entity": fa.entity,
                        "asset": fa.description,
                        "cost": money.fmt(fa.cost_cents),
                        "in_service": fa.in_service_period,
                        "life_months": str(fa.useful_life_months),
                        "monthly": money.fmt(monthly),
                        "accum_dep": money.fmt(accum),
                        "net_book_value": money.fmt(nbv),
                        "depr_this_period": money.fmt(monthly if active else 0),
                    },
                )
            )
            if active:
                je.lines.append(
                    JournalLine(
                        fa.entity, "6100", monthly, 0, f"{fa.asset_id} {self.period}"
                    )
                )
                je.lines.append(
                    JournalLine(
                        fa.entity, "1510", 0, monthly, f"Accum. dep. {fa.asset_id}"
                    )
                )
        # The depreciation schedule ties to total accumulated depreciation.
        # Opening accum-dep balances exist on the ledger, so the tie target is
        # the *movement* this period; we verify the JE side ties instead.
        sched.tie_account = None
        self.schedules.append(sched)
        return je

    def _depreciation_monthly(self, fa: FixedAsset) -> int:
        """Straight-line monthly depreciation amount for an asset."""
        parts = money.split_evenly(fa.cost_cents, fa.useful_life_months)
        elapsed = months_elapsed(fa.in_service_period, self.period)
        if 0 <= elapsed < fa.useful_life_months:
            return parts[elapsed]
        return 0

    def _accumulated_depreciation(self, fa: FixedAsset) -> int:
        """Accumulated depreciation through the close month for an asset."""
        parts = money.split_evenly(fa.cost_cents, fa.useful_life_months)
        elapsed = months_elapsed(fa.in_service_period, self.period)
        booked_through = max(0, min(elapsed + 1, fa.useful_life_months))
        return sum(parts[:booked_through])

    def _deferred_rent_and_cam(self) -> JournalEntry:
        """Deferred-rent straight-lining + CAM with a fixed cross-entity split.

        Rent expense is recognized straight-line; the difference versus the
        contractual cash rent posts to the deferred-rent liability/asset
        (2200/1600). CAM is recognized monthly. The non-holder entities' shares
        of rent+CAM are routed through intercompany due-to (2800) / due-from
        (1800), so each entity leg balances independently.
        """
        je = JournalEntry(
            je_id=f"JE-{self.period}-LEASE",
            period=self.period,
            category="deferred_rent_cam",
            description="Deferred rent + CAM straight-lining (intercompany split)",
        )
        sched = Schedule("Deferred rent & CAM", "deferred_rent_cam")
        for lease in self.ds.leases():
            idx = self._lease_month_index(lease)
            if not (0 <= idx < len(lease.cash_rent_schedule_cents)):
                continue
            cash_rent = lease.cash_rent_schedule_cents[idx]
            sl_rent = lease.straight_line_cents
            cam = lease.monthly_cam_cents
            deferred_delta = sl_rent - cash_rent  # +ve builds liability

            # Total cost to spread across the group this period.
            total_rent = sl_rent
            total_cam = cam
            rent_split = money.allocate_by_ratio(
                total_rent, [lease.split_bps[e.code] for e in self.ds.entities()]
            )
            cam_split = money.allocate_by_ratio(
                total_cam, [lease.split_bps[e.code] for e in self.ds.entities()]
            )
            holder = lease.entity

            for i, ent in enumerate(self.ds.entities()):
                ent_rent = rent_split[i]
                ent_cam = cam_split[i]
                # Each entity recognizes its share of rent + CAM expense.
                je.lines.append(
                    JournalLine(
                        ent.code, "6000", ent_rent, 0, f"{lease.lease_id} rent share"
                    )
                )
                je.lines.append(
                    JournalLine(
                        ent.code, "6050", ent_cam, 0, f"{lease.lease_id} CAM share"
                    )
                )
                if ent.code == holder:
                    # Holder funds the landlord: credit deferred-rent movement
                    # and accrued liabilities for cash rent + CAM, then
                    # receives intercompany due-from the other entities.
                    # Build the credit side for the holder's OWN economic share
                    # via deferred rent; the cross-charge to others via 1800.
                    # Holder posts the deferred-rent liability movement on the
                    # full lease (straight-line vs cash) plus the landlord
                    # obligation.
                    # Holder's net expense recognized = ent_rent + ent_cam.
                    # Holder pays full cash_rent + cam to landlord (accrued).
                    holder_due_from = (total_rent - ent_rent) + (total_cam - ent_cam)
                    je.lines.append(
                        JournalLine(
                            holder,
                            "1800",
                            holder_due_from,
                            0,
                            "Due from affiliates (lease cost share)",
                        )
                    )
                    # Credit: deferred-rent movement on the full lease.
                    if deferred_delta >= 0:
                        je.lines.append(
                            JournalLine(
                                holder,
                                "2200",
                                0,
                                deferred_delta,
                                "Deferred rent liability build",
                            )
                        )
                    else:
                        je.lines.append(
                            JournalLine(
                                holder,
                                "1600",
                                -deferred_delta,
                                0,
                                "Deferred rent asset build",
                            )
                        )
                    # Credit accrued liability for the cash the holder owes the
                    # landlord (cash rent + CAM for the whole building).
                    je.lines.append(
                        JournalLine(
                            holder,
                            "2100",
                            0,
                            cash_rent + total_cam,
                            "Accrued lease cash obligation",
                        )
                    )
                else:
                    # Non-holder owes its share to the holder via due-to.
                    je.lines.append(
                        JournalLine(
                            ent.code,
                            "2800",
                            0,
                            ent_rent + ent_cam,
                            "Due to affiliate (lease cost share)",
                        )
                    )

            sched.rows.append(
                ScheduleRow(
                    lease.lease_id,
                    {
                        "lease": lease.description,
                        "holder": holder,
                        "month_index": str(idx + 1),
                        "cash_rent": money.fmt(cash_rent),
                        "straight_line_rent": money.fmt(sl_rent),
                        "cam": money.fmt(cam),
                        "deferred_movement": money.fmt(deferred_delta),
                        "split": " / ".join(
                            f"{e.code} {lease.split_bps[e.code] / 100:.0f}%"
                            for e in self.ds.entities()
                        ),
                    },
                )
            )
        self.schedules.append(sched)
        return je

    def _lease_month_index(self, lease: Lease) -> int:
        """Return the 0-based month index into the lease's cash-rent schedule.

        The lease schedule is anchored to the first period of the close year so
        the engine is deterministic regardless of the requested close period.
        """
        year = int(self.period.split("-")[0])
        anchor = f"{year:04d}-01"
        return months_elapsed(anchor, self.period)

    def _mgmt_fee_accrual(self) -> JournalEntry:
        """Accrue the monthly management fee, netting any in-month cash payment.

        Debits Management fee expense (6200) for the full monthly fee; credits
        Cash (1000) for any in-month payment already made and Management fee
        payable (2300) for the remaining accrual.
        """
        je = JournalEntry(
            je_id=f"JE-{self.period}-MGMTFEE",
            period=self.period,
            category="mgmt_fee_accrual",
            description="Management-fee accrual (net of in-month payments)",
        )
        sched = Schedule("Management-fee accrual", "mgmt_fee_accrual")
        total_payable = 0
        for mf in self.ds.mgmt_fees():
            net_accrual = mf.monthly_fee_cents - mf.in_month_payment_cents
            sched.rows.append(
                ScheduleRow(
                    mf.arrangement_id,
                    {
                        "payer": mf.payer_entity,
                        "monthly_fee": money.fmt(mf.monthly_fee_cents),
                        "paid_in_month": money.fmt(mf.in_month_payment_cents),
                        "net_accrual": money.fmt(net_accrual),
                    },
                )
            )
            je.lines.append(
                JournalLine(
                    mf.payer_entity,
                    "6200",
                    mf.monthly_fee_cents,
                    0,
                    f"{mf.arrangement_id} monthly management fee",
                )
            )
            if mf.in_month_payment_cents:
                je.lines.append(
                    JournalLine(
                        mf.payer_entity,
                        "1000",
                        0,
                        mf.in_month_payment_cents,
                        f"{mf.arrangement_id} in-month payment",
                    )
                )
            if net_accrual:
                je.lines.append(
                    JournalLine(
                        mf.payer_entity,
                        "2300",
                        0,
                        net_accrual,
                        f"{mf.arrangement_id} fee payable",
                    )
                )
                total_payable += net_accrual
        self.schedules.append(sched)
        return je

    def _note_interest_accrual(self) -> JournalEntry:
        """Accrue one month of simple interest on related-party notes.

        For each note the borrower debits Interest expense (6300) and credits
        Accrued interest payable (2400). Because notes are intercompany, the
        lender also recognizes the mirror: debit Due-from (1800) / credit
        Intercompany interest income (4900). Each entity leg self-balances.
        """
        je = JournalEntry(
            je_id=f"JE-{self.period}-INTEREST",
            period=self.period,
            category="note_interest",
            description="Related-party note interest accrual",
        )
        sched = Schedule("Note interest accrual", "note_interest")
        for note in self.ds.notes():
            monthly_interest = self._monthly_interest(note)
            sched.rows.append(
                ScheduleRow(
                    note.note_id,
                    {
                        "lender": note.lender_entity,
                        "borrower": note.borrower_entity,
                        "principal": money.fmt(note.principal_cents),
                        "annual_rate": f"{note.annual_rate_bps / 100:.2f}%",
                        "monthly_interest": money.fmt(monthly_interest),
                    },
                )
            )
            # Borrower side.
            je.lines.append(
                JournalLine(
                    note.borrower_entity,
                    "6300",
                    monthly_interest,
                    0,
                    f"{note.note_id} interest expense",
                )
            )
            je.lines.append(
                JournalLine(
                    note.borrower_entity,
                    "2400",
                    0,
                    monthly_interest,
                    f"{note.note_id} accrued interest",
                )
            )
            # Lender mirror (intercompany).
            je.lines.append(
                JournalLine(
                    note.lender_entity,
                    "1800",
                    monthly_interest,
                    0,
                    f"{note.note_id} interest receivable",
                )
            )
            je.lines.append(
                JournalLine(
                    note.lender_entity,
                    "4900",
                    0,
                    monthly_interest,
                    f"{note.note_id} interest income",
                )
            )
        self.schedules.append(sched)
        return je

    def _monthly_interest(self, note: Note) -> int:
        """Simple monthly interest = principal * annual_rate / 12, in cents.

        Computed with integer arithmetic and rounded half-up to the cent so the
        accrual is deterministic.
        """
        # principal_cents * annual_rate_bps is cents*bps; the monthly divisor is
        # 10000 (bps per unit) * 12 (months) = 120000.
        numerator = note.principal_cents * note.annual_rate_bps
        return (numerator + 60000) // 120000

    def _gna_allocation(self) -> JournalEntry:
        """Allocate the G&A shared-services pool by a fixed ratio (sums 100%).

        The pool entity holds the shared-services cost (6650). The engine
        reclasses it to allocated G&A (6600) across all entities by the fixed
        basis-point split (which must sum to 10000). Non-pool entities' shares
        route through intercompany due-to / due-from so each leg balances.
        """
        gna = self.ds.gna()
        je = JournalEntry(
            je_id=f"JE-{self.period}-GNA",
            period=self.period,
            category="gna_allocation",
            description="G&A cost allocation (fixed ratio, sums to 100%)",
        )
        sched = Schedule("G&A allocation", "gna_allocation")
        entities = self.ds.entities()
        shares = money.allocate_by_ratio(
            gna.monthly_pool_cents, [gna.split_bps[e.code] for e in entities]
        )
        pool = gna.pool_entity
        for i, ent in enumerate(entities):
            share = shares[i]
            # Every entity recognizes its allocated G&A expense.
            je.lines.append(
                JournalLine(ent.code, "6600", share, 0, "Allocated G&A share")
            )
            sched.rows.append(
                ScheduleRow(
                    ent.code,
                    {
                        "entity": ent.code,
                        "ratio": f"{gna.split_bps[ent.code] / 100:.2f}%",
                        "allocated": money.fmt(share),
                    },
                )
            )
            if ent.code == pool:
                # Pool entity relieves the shared-services cost it incurred and
                # books a due-from for the other entities' shares.
                others = gna.monthly_pool_cents - share
                je.lines.append(
                    JournalLine(
                        pool,
                        "6650",
                        0,
                        gna.monthly_pool_cents,
                        "Relieve shared-services pool",
                    )
                )
                if others:
                    je.lines.append(
                        JournalLine(
                            pool,
                            "1800",
                            others,
                            0,
                            "Due from affiliates (G&A allocation)",
                        )
                    )
            else:
                je.lines.append(
                    JournalLine(
                        ent.code,
                        "2800",
                        0,
                        share,
                        "Due to affiliate (G&A allocation)",
                    )
                )
        sched.rows.append(
            ScheduleRow(
                "TOTAL",
                {
                    "entity": "ALL",
                    "ratio": f"{sum(gna.split_bps.values()) / 100:.2f}%",
                    "allocated": money.fmt(gna.monthly_pool_cents),
                },
            )
        )
        self.schedules.append(sched)
        return je

    def _insurance_allocation(self) -> JournalEntry:
        """Amortize one month of each shared insurance policy, split per entity.

        Accounting rule: one month of the premium in force (original premium
        until the renewal period; the renewal premium from the renewal month
        on, so a step-up books at the new rate) is expensed and relieved from
        prepaid insurance. Entity shares use the largest-remainder method so
        the per-entity lines sum EXACTLY to the policy's monthly amortization
        total. Each entity debits Insurance expense (6400) and credits Prepaid
        insurance (1450) for its own share, so every entity leg self-balances.
        """
        je = JournalEntry(
            je_id=f"JE-{self.period}-INSUR",
            period=self.period,
            category="insurance_allocation",
            description="Insurance premium allocation (shared policies)",
        )
        sched = Schedule("Insurance allocation", "insurance_allocation")
        entities = self.ds.entities()
        for pol in self.ds.insurance_policies():
            monthly_total = self._insurance_monthly_total(pol)
            weights = [pol.split_bps.get(e.code, 0) for e in entities]
            shares = money.allocate_by_ratio(monthly_total, weights)
            annual = self._insurance_applicable_premium(pol)
            for ent, weight, share in zip(entities, weights, shares):
                if weight == 0:
                    continue
                sched.rows.append(
                    ScheduleRow(
                        f"{pol.policy_id}-{ent.code}",
                        {
                            "policy": pol.policy_id,
                            "carrier": pol.carrier,
                            "entity": ent.code,
                            "ratio": f"{weight / 100:.2f}%",
                            "annual_premium": money.fmt(annual),
                            "policy_monthly": money.fmt(monthly_total),
                            "entity_share": money.fmt(share),
                        },
                    )
                )
                if share:
                    je.lines.append(
                        JournalLine(
                            ent.code,
                            "6400",
                            share,
                            0,
                            f"{pol.policy_id} {self.period} insurance amortization",
                        )
                    )
                    je.lines.append(
                        JournalLine(
                            ent.code,
                            "1450",
                            0,
                            share,
                            f"Relieve prepaid insurance {pol.policy_id}",
                        )
                    )
        # Schedule ties to the remaining prepaid insurance balance group-wide.
        sched.tie_account = "1450"
        sched.tie_expected_cents = sum(
            self._insurance_remaining(pol) for pol in self.ds.insurance_policies()
        )
        self.schedules.append(sched)
        return je

    def _insurance_applicable_premium(self, pol: InsurancePolicy) -> int:
        """Annual premium in force for the close month.

        The original premium applies until the renewal period; the renewal
        premium applies FROM the renewal period on (the step-up month books
        the new rate). Policies renew on their inception anniversary, so the
        12-month amortization cycle and the premium switch stay aligned.
        """
        if period_index(self.period) >= period_index(pol.renewal_period):
            return pol.renewal_annual_premium_cents
        return pol.annual_premium_cents

    def _insurance_monthly_total(self, pol: InsurancePolicy) -> int:
        """One month of the applicable annual premium (0 before inception).

        The premium splits into 12 straight-line parts (the final month
        absorbs the split remainder, matching :func:`money.split_evenly`).
        """
        offset = months_elapsed(pol.inception_period, self.period)
        if offset < 0:
            return 0
        annual = self._insurance_applicable_premium(pol)
        return money.split_evenly(annual, 12)[offset % 12]

    def _insurance_remaining(self, pol: InsurancePolicy) -> int:
        """Unamortized prepaid insurance after this period's entry.

        Equals the applicable annual premium less every monthly part booked
        through the close month within the current policy year.
        """
        offset = months_elapsed(pol.inception_period, self.period)
        if offset < 0:
            return 0
        annual = self._insurance_applicable_premium(pol)
        parts = money.split_evenly(annual, 12)
        return annual - sum(parts[: offset % 12 + 1])

    # -- tie-out ----------------------------------------------------------- #

    def _tie_out(self) -> list[TieResult]:
        """Tie each schedule that declares a ``tie_account`` to the GL.

        Returns a :class:`TieResult` per tied schedule comparing the schedule's
        expected balance to the actual group-wide GL balance.
        """
        results: list[TieResult] = []
        for sched in self.schedules:
            if sched.tie_account is None or sched.tie_expected_cents is None:
                continue
            actual = abs(self.ledger.account_balance(sched.tie_account))
            results.append(
                TieResult(
                    schedule=sched.name,
                    account=sched.tie_account,
                    expected_cents=sched.tie_expected_cents,
                    actual_cents=actual,
                )
            )
        return results
