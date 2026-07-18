"""Independent shadow recomputation of every recurring-entry amount.

This module is the second, fully independent computation path behind control
C9: it re-derives every category's expected posting amounts straight from the
raw dataset with its own arithmetic. It deliberately imports NOTHING from
:mod:`close_engine.engine` -- it even re-implements the penny-splitting
helpers -- so an engine bug and a shadow bug can only agree by coincidence.
That is the two-independent-computations gate: the posted register and this
shadow must match to the cent before a close may stand.

The output is a map ``(entity, category, account) -> (debit_cents,
credit_cents)`` aggregating what the posted register should contain for the
dataset's close period.
"""

from __future__ import annotations

# The recurring-entry categories the shadow re-derives, in posting order.
CATEGORIES: tuple[str, ...] = (
    "prepaid_amortization",
    "depreciation",
    "deferred_rent_cam",
    "fixed_fee_accrual",
    "mgmt_fee_accrual",
    "note_interest",
    "gna_allocation",
    "insurance_allocation",
    "postage_allocation",
)

# (entity, category, account) -> (debit_cents, credit_cents)
AmountKey = tuple[str, str, str]
AmountMap = dict[AmountKey, tuple[int, int]]


# --------------------------------------------------------------------------- #
# Own arithmetic (no imports from the engine or the money module)
# --------------------------------------------------------------------------- #


def _abs_month(period: str) -> int:
    """Convert ``YYYY-MM`` to an absolute month count for span arithmetic."""
    year, month = period.split("-")
    return int(year) * 12 + int(month) - 1


def _span(start: str, end: str) -> int:
    """Whole months from ``start`` to ``end`` (0 in the start month)."""
    return _abs_month(end) - _abs_month(start)


def _straight_line_part(total: int, months: int, offset: int) -> int:
    """Month ``offset``'s slice of an even split; the final month plugs.

    Accounting policy: straight-line schedules carry the integer-division
    remainder in the last month so the parts always sum back to the whole.
    """
    base, leftover = divmod(total, months)
    return base + (leftover if offset == months - 1 else 0)


def _hamilton_shares(total: int, weights_bps: list[int]) -> list[int]:
    """Largest-remainder allocation over basis-point weights (sum 10000).

    Accounting policy: floor each share, then hand leftover cents to the
    largest fractional remainders, first-listed entity winning ties, so the
    shares always sum exactly to ``total``.
    """
    shares: list[int] = []
    fractions: list[tuple[int, int]] = []
    for position, weight in enumerate(weights_bps):
        part, fraction = divmod(total * weight, 10000)
        shares.append(part)
        fractions.append((fraction, position))
    short = total - sum(shares)
    fractions.sort(key=lambda pair: (-pair[0], pair[1]))
    for _, position in fractions[:short]:
        shares[position] += 1
    return shares


def _half_up_monthly_interest(principal_cents: int, annual_rate_bps: int) -> int:
    """One month of simple interest, rounded half-up to the cent.

    monthly = principal * rate_bps / (10000 bps * 12 months), half-up.
    """
    gross = principal_cents * annual_rate_bps
    quotient, leftover = divmod(gross, 120000)
    return quotient + (1 if leftover * 2 >= 120000 else 0)


# --------------------------------------------------------------------------- #
# Per-category shadows
# --------------------------------------------------------------------------- #


def _add(
    amounts: AmountMap,
    entity: str,
    category: str,
    account: str,
    debit: int = 0,
    credit: int = 0,
) -> None:
    """Accumulate a debit/credit expectation onto one aggregation key."""
    key = (entity, category, account)
    debits, credits = amounts.get(key, (0, 0))
    amounts[key] = (debits + debit, credits + credit)


def _shadow_prepaid_amortization(dataset, amounts: AmountMap) -> None:
    """Active prepaids: DR the expense account / CR prepaid expenses (1400)."""
    for pp in dataset.prepaids():
        offset = _span(pp.start_period, dataset.period)
        if not 0 <= offset < pp.term_months:
            continue
        monthly = _straight_line_part(pp.total_cents, pp.term_months, offset)
        _add(amounts, pp.entity, "prepaid_amortization", pp.expense_account,
             debit=monthly)
        _add(amounts, pp.entity, "prepaid_amortization", "1400", credit=monthly)


def _shadow_depreciation(dataset, amounts: AmountMap) -> None:
    """In-life assets: DR depreciation (6100) / CR accumulated (1510)."""
    for fa in dataset.fixed_assets():
        offset = _span(fa.in_service_period, dataset.period)
        if not 0 <= offset < fa.useful_life_months:
            continue
        monthly = _straight_line_part(fa.cost_cents, fa.useful_life_months, offset)
        _add(amounts, fa.entity, "depreciation", "6100", debit=monthly)
        _add(amounts, fa.entity, "depreciation", "1510", credit=monthly)


def _shadow_deferred_rent_cam(dataset, amounts: AmountMap) -> None:
    """Shared leases: straight-line rent + CAM split across the group.

    The holder funds the landlord (accrued cash rent + CAM), books the
    deferred-rent movement on the full lease, and receives due-from the other
    entities; each non-holder books its share against due-to.
    """
    category = "deferred_rent_cam"
    year = dataset.period.split("-")[0]
    codes = [e.code for e in dataset.entities()]
    for lease in dataset.leases():
        idx = _span(f"{year}-01", dataset.period)
        if not 0 <= idx < len(lease.cash_rent_schedule_cents):
            continue
        cash_rent = lease.cash_rent_schedule_cents[idx]
        total_rent = lease.straight_line_cents
        total_cam = lease.monthly_cam_cents
        weights = [lease.split_bps[code] for code in codes]
        rent_shares = _hamilton_shares(total_rent, weights)
        cam_shares = _hamilton_shares(total_cam, weights)
        for code, rent_share, cam_share in zip(codes, rent_shares, cam_shares):
            _add(amounts, code, category, "6000", debit=rent_share)
            _add(amounts, code, category, "6050", debit=cam_share)
            if code == lease.entity:
                due_from = (total_rent - rent_share) + (total_cam - cam_share)
                _add(amounts, code, category, "1800", debit=due_from)
                deferred_delta = total_rent - cash_rent
                if deferred_delta >= 0:
                    _add(amounts, code, category, "2200", credit=deferred_delta)
                else:
                    _add(amounts, code, category, "1600", debit=-deferred_delta)
                _add(amounts, code, category, "2100",
                     credit=cash_rent + total_cam)
            else:
                _add(amounts, code, category, "2800",
                     credit=rent_share + cam_share)


def _shadow_mgmt_fee_accrual(dataset, amounts: AmountMap) -> None:
    """Fee arrangements: DR expense; CR cash paid in-month and the net payable."""
    for mf in dataset.mgmt_fees():
        _add(amounts, mf.payer_entity, "mgmt_fee_accrual", "6200",
             debit=mf.monthly_fee_cents)
        if mf.in_month_payment_cents:
            _add(amounts, mf.payer_entity, "mgmt_fee_accrual", "1000",
                 credit=mf.in_month_payment_cents)
        net = mf.monthly_fee_cents - mf.in_month_payment_cents
        if net:
            _add(amounts, mf.payer_entity, "mgmt_fee_accrual", "2300",
                 credit=net)


def _shadow_fixed_fee_accrual(dataset, amounts: AmountMap) -> None:
    """Fixed fees: independently derive fee plus signed approved adjustment.

    Settlements are deliberately absent: they are upstream activity already
    reflected in the opening payable balance and must not be posted twice.
    """
    for fee in dataset.fixed_fees():
        accrual = fee.monthly_fee_cents + fee.approved_adjustment_cents
        if accrual > 0:
            _add(amounts, fee.entity, "fixed_fee_accrual", "6250",
                 debit=accrual)
            _add(amounts, fee.entity, "fixed_fee_accrual", "2350",
                 credit=accrual)
        elif accrual < 0:
            reversal = -accrual
            _add(amounts, fee.entity, "fixed_fee_accrual", "2350",
                 debit=reversal)
            _add(amounts, fee.entity, "fixed_fee_accrual", "6250",
                 credit=reversal)


def _shadow_note_interest(dataset, amounts: AmountMap) -> None:
    """Notes: borrower accrues expense/payable; lender mirrors via due-from."""
    for note in dataset.notes():
        monthly = _half_up_monthly_interest(note.principal_cents,
                                            note.annual_rate_bps)
        _add(amounts, note.borrower_entity, "note_interest", "6300",
             debit=monthly)
        _add(amounts, note.borrower_entity, "note_interest", "2400",
             credit=monthly)
        _add(amounts, note.lender_entity, "note_interest", "1800",
             debit=monthly)
        _add(amounts, note.lender_entity, "note_interest", "4900",
             credit=monthly)


def _shadow_gna_allocation(dataset, amounts: AmountMap) -> None:
    """G&A pool: each entity's allocated share, cleared through the pool."""
    gna = dataset.subs.gna
    if gna is None:
        return
    codes = [e.code for e in dataset.entities()]
    shares = _hamilton_shares(gna.monthly_pool_cents,
                              [gna.split_bps[code] for code in codes])
    for code, share in zip(codes, shares):
        _add(amounts, code, "gna_allocation", "6600", debit=share)
        if code == gna.pool_entity:
            _add(amounts, code, "gna_allocation", "6650",
                 credit=gna.monthly_pool_cents)
            others = gna.monthly_pool_cents - share
            if others:
                _add(amounts, code, "gna_allocation", "1800", debit=others)
        else:
            _add(amounts, code, "gna_allocation", "2800", credit=share)


def _shadow_insurance_allocation(dataset, amounts: AmountMap) -> None:
    """In-force policies: one twelfth of the premium in force, split per entity.

    The renewal premium takes over FROM the renewal period (the step-up month
    books the new rate); entity shares use the largest-remainder method so
    they sum exactly to the policy's monthly amortization.
    """
    codes = [e.code for e in dataset.entities()]
    for pol in dataset.insurance_policies():
        offset = _span(pol.inception_period, dataset.period)
        if offset < 0:
            continue
        if _abs_month(dataset.period) >= _abs_month(pol.renewal_period):
            annual = pol.renewal_annual_premium_cents
        else:
            annual = pol.annual_premium_cents
        monthly_total = _straight_line_part(annual, 12, offset % 12)
        weights = [pol.split_bps.get(code, 0) for code in codes]
        shares = _hamilton_shares(monthly_total, weights)
        for code, share in zip(codes, shares):
            if share == 0:
                continue
            _add(amounts, code, "insurance_allocation", "6400", debit=share)
            _add(amounts, code, "insurance_allocation", "1450", credit=share)


def _shadow_postage_allocation(dataset, amounts: AmountMap) -> None:
    """Meter rows: independently exact-match routes and clear account 1460.

    The shadow intentionally rebuilds route counts and posting legs without
    calling any engine helper. An invalid batch is omitted because the engine
    must refuse it in full; C6 independently reports the mapping defect.
    """
    category = "postage_allocation"
    codes = {entity.code for entity in dataset.entities()}
    current_batches = [
        batch
        for batch in dataset.postage_batches()
        if batch.period == dataset.period
    ]
    batch_ids = [batch.batch_id for batch in current_batches]

    def canonical(value: str) -> bool:
        return bool(value.strip()) and value == value.strip()

    for batch in current_batches:
        route_counts: dict[str, int] = {}
        route_by_project = {}
        invalid = (
            batch.holder_entity not in codes
            or not canonical(batch.batch_id)
            or batch_ids.count(batch.batch_id) != 1
        )
        line_ids = [line.line_id for line in batch.meter_lines]
        if len(line_ids) != len(set(line_ids)):
            invalid = True
        if any(
            not canonical(line.line_id) or not canonical(line.project_code)
            for line in batch.meter_lines
        ):
            invalid = True
        for route in batch.routes:
            route_counts[route.project_code] = (
                route_counts.get(route.project_code, 0) + 1
            )
            route_by_project[route.project_code] = route
            if (
                route.recipient_entity not in codes
                or not canonical(route.project_code)
                or not canonical(route.job_code)
                or not canonical(route.cost_code)
            ):
                invalid = True
        if any(count != 1 for count in route_counts.values()):
            invalid = True
        if any(
            route_counts.get(line.project_code, 0) != 1
            for line in batch.meter_lines
        ):
            invalid = True
        if invalid:
            continue
        for line in batch.meter_lines:
            amount = line.amount_cents
            if amount == 0:
                continue
            recipient = route_by_project[line.project_code].recipient_entity
            holder = batch.holder_entity
            if amount > 0:
                _add(amounts, recipient, category, "6700", debit=amount)
                if recipient == holder:
                    _add(amounts, holder, category, "1460", credit=amount)
                else:
                    _add(amounts, recipient, category, "2800", credit=amount)
                    _add(amounts, holder, category, "1800", debit=amount)
                    _add(amounts, holder, category, "1460", credit=amount)
            else:
                refund = -amount
                _add(amounts, recipient, category, "6700", credit=refund)
                if recipient == holder:
                    _add(amounts, holder, category, "1460", debit=refund)
                else:
                    _add(amounts, recipient, category, "2800", debit=refund)
                    _add(amounts, holder, category, "1800", credit=refund)
                    _add(amounts, holder, category, "1460", debit=refund)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def expected_amounts(dataset) -> AmountMap:
    """Re-derive every category's expected posting amounts from the dataset.

    Args:
        dataset: A :class:`~close_engine.generate.Dataset` (typed loosely so
            this module stays import-free of the rest of the package).

    Returns:
        ``{(entity, category, account): (debit_cents, credit_cents)}`` for
        every amount the posted register should contain this period.
    """
    amounts: AmountMap = {}
    _shadow_prepaid_amortization(dataset, amounts)
    _shadow_depreciation(dataset, amounts)
    _shadow_deferred_rent_cam(dataset, amounts)
    _shadow_fixed_fee_accrual(dataset, amounts)
    _shadow_mgmt_fee_accrual(dataset, amounts)
    _shadow_note_interest(dataset, amounts)
    _shadow_gna_allocation(dataset, amounts)
    _shadow_insurance_allocation(dataset, amounts)
    _shadow_postage_allocation(dataset, amounts)
    return amounts


def expected_for_category(dataset, category: str) -> AmountMap:
    """Return the shadow expectations for a single category.

    Raises:
        KeyError: If ``category`` is not a recurring-entry category.
    """
    if category not in CATEGORIES:
        raise KeyError(f"unknown recurring-entry category: {category!r}")
    return {
        key: value
        for key, value in expected_amounts(dataset).items()
        if key[1] == category
    }
