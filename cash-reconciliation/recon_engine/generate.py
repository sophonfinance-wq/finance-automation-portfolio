"""Synthetic, seeded data generator for the reconciliation engine.

Produces three in-memory "workpapers" for a set of fictional entities:

1. **GL records** — the general-ledger cash and debt balances (the book/target).
2. **Bank statements** — ending balances per cash account (the cash source).
3. **Lender statements** — principal / interest / paydown per debt account
   (the debt source).

A handful of discrepancies are *intentionally injected* and seeded so the engine
(and the tests) can prove they are caught and classified correctly:

* ``deposit-in-transit`` — bank ending is higher than GL cash because a deposit
  hit the bank but was not yet booked (a CLEAN timing item, within threshold or
  flagged depending on size — here it is a flagged structural gap).
* ``timing`` — a lender interest accrual booked in GL but not yet on the lender
  statement, producing a small variance under materiality (a TIMING item).
* ``error`` — an outright keying error on a debt principal (a FLAG).

Everything is generated with the stdlib :mod:`random` module under a fixed seed
for full reproducibility. No third-party data libraries are used.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

DEFAULT_SEED: int = 20260331

# Discrepancy kinds we intentionally inject, for assertions in the test suite.
InjectedKind = Literal["deposit_in_transit", "timing", "error"]


@dataclass(frozen=True)
class GLRecord:
    """A single general-ledger balance row for one account of one entity."""

    entity: str
    account_type: Literal["cash", "debt"]
    account_number: str
    description: str
    gl_balance: float
    dormant: bool = False


@dataclass(frozen=True)
class BankStatement:
    """A bank statement ending balance for a single cash account."""

    account_number: str
    bank_name: str
    statement_date: str
    ending_balance: float


@dataclass(frozen=True)
class LenderStatement:
    """A lender statement for a single debt account.

    The reconciled lender total uses a 3-part formula:
    ``principal + current_interest_reserve + late_paydown``.
    """

    account_number: str
    lender_name: str
    statement_date: str
    principal: float
    current_interest_reserve: float
    late_paydown: float


@dataclass(frozen=True)
class InjectedDiscrepancy:
    """Metadata describing a discrepancy deliberately seeded into the data."""

    kind: InjectedKind
    account_number: str
    entity: str
    note: str


@dataclass
class SyntheticDataset:
    """Bundle of all generated workpapers plus the injected-discrepancy log."""

    period: str
    statement_date: str
    gl_records: list[GLRecord] = field(default_factory=list)
    bank_statements: list[BankStatement] = field(default_factory=list)
    lender_statements: list[LenderStatement] = field(default_factory=list)
    injected: list[InjectedDiscrepancy] = field(default_factory=list)


# Fictional entities. Obviously-fake names only.
_ENTITIES: tuple[str, ...] = (
    "Demo Holdings LLC",
    "Maple Fund LP",
    "Birchwood Op Co",
    "Cedar Ridge Partners LLC",
)

_BANKS: tuple[str, ...] = (
    "Northgate Demo Bank",
    "Riverstone Mock Bank",
    "Summit Sandbox Bank",
    "Lakeside Test Bank",
)

_LENDERS: tuple[str, ...] = (
    "Crestline Demo Capital",
    "Foxglove Mock Lending",
    "Ironwood Sandbox Finance",
    "Harbor Test Credit Co",
)


def _money(rng: random.Random, low: float, high: float) -> float:
    """Return a random dollar amount rounded to cents."""
    return round(rng.uniform(low, high), 2)


def generate_dataset(seed: int = DEFAULT_SEED) -> SyntheticDataset:
    """Generate the full seeded synthetic dataset.

    Args:
        seed: Random seed controlling all generated values. The same seed always
            yields byte-identical data, which keeps the tests deterministic.

    Returns:
        A :class:`SyntheticDataset` with GL, bank, and lender workpapers and a
        log of the discrepancies that were intentionally injected.
    """
    rng = random.Random(seed)
    statement_date = "2026-03-31"
    period = "March 2026"

    ds = SyntheticDataset(period=period, statement_date=statement_date)

    # Assign a stable account-number scheme per entity.
    for idx, entity in enumerate(_ENTITIES):
        cash_acct = f"CASH-{1000 + idx:04d}"
        debt_acct = f"DEBT-{2000 + idx:04d}"
        bank = _BANKS[idx % len(_BANKS)]
        lender = _LENDERS[idx % len(_LENDERS)]

        # ---- Base cash account (clean tie by default) --------------------
        cash_balance = _money(rng, 75_000, 950_000)
        ds.gl_records.append(
            GLRecord(
                entity=entity,
                account_type="cash",
                account_number=cash_acct,
                description=f"{entity} operating cash",
                gl_balance=cash_balance,
            )
        )
        bank_ending = cash_balance  # ties exactly unless a discrepancy is injected

        # ---- Base debt account (clean tie by default) --------------------
        principal = _money(rng, 250_000, 3_500_000)
        interest_reserve = _money(rng, 500, 12_000)
        late_paydown = 0.0
        # GL debt should equal the 3-part lender total when clean.
        gl_debt = round(principal + interest_reserve + late_paydown, 2)
        ds.gl_records.append(
            GLRecord(
                entity=entity,
                account_type="debt",
                account_number=debt_acct,
                description=f"{entity} term loan",
                gl_balance=gl_debt,
            )
        )

        ds.bank_statements.append(
            BankStatement(
                account_number=cash_acct,
                bank_name=bank,
                statement_date=statement_date,
                ending_balance=bank_ending,
            )
        )
        ds.lender_statements.append(
            LenderStatement(
                account_number=debt_acct,
                lender_name=lender,
                statement_date=statement_date,
                principal=principal,
                current_interest_reserve=interest_reserve,
                late_paydown=late_paydown,
            )
        )

    # ----------------------------------------------------------------------
    # Inject discrepancies into specific accounts (all seeded / deterministic).
    # ----------------------------------------------------------------------
    _inject_deposit_in_transit(ds)
    _inject_timing_difference(ds)
    _inject_outright_error(ds)
    _inject_late_paydown(ds)  # exercises the optional 3rd part of the debt formula
    _inject_dormant_account(ds)

    # Stable ordering for deterministic output.
    ds.gl_records.sort(key=lambda r: (r.entity, r.account_type, r.account_number))
    ds.bank_statements.sort(key=lambda r: r.account_number)
    ds.lender_statements.sort(key=lambda r: r.account_number)
    ds.injected.sort(key=lambda r: r.account_number)
    return ds


def _bank_by_acct(ds: SyntheticDataset, acct: str) -> BankStatement:
    for i, b in enumerate(ds.bank_statements):
        if b.account_number == acct:
            return b
    raise KeyError(acct)


def _replace_bank(ds: SyntheticDataset, new: BankStatement) -> None:
    ds.bank_statements = [
        new if b.account_number == new.account_number else b
        for b in ds.bank_statements
    ]


def _lender_by_acct(ds: SyntheticDataset, acct: str) -> LenderStatement:
    for ln in ds.lender_statements:
        if ln.account_number == acct:
            return ln
    raise KeyError(acct)


def _replace_lender(ds: SyntheticDataset, new: LenderStatement) -> None:
    ds.lender_statements = [
        new if ln.account_number == new.account_number else ln
        for ln in ds.lender_statements
    ]


def _gl_by_acct(ds: SyntheticDataset, acct: str) -> GLRecord:
    for r in ds.gl_records:
        if r.account_number == acct:
            return r
    raise KeyError(acct)


def _replace_gl(ds: SyntheticDataset, new: GLRecord) -> None:
    ds.gl_records = [
        new if r.account_number == new.account_number else r for r in ds.gl_records
    ]


def _inject_deposit_in_transit(ds: SyntheticDataset) -> None:
    """Bank ending exceeds GL cash: a deposit hit the bank, not yet booked.

    Targets entity index 1's cash account. The gap is well above materiality so
    it surfaces as a flagged (but explainable timing) structural item.
    """
    entity = _ENTITIES[1]
    acct = "CASH-1001"
    bank = _bank_by_acct(ds, acct)
    deposit = 1_875.40  # bank is higher than GL by this amount
    _replace_bank(
        ds,
        BankStatement(
            account_number=bank.account_number,
            bank_name=bank.bank_name,
            statement_date=bank.statement_date,
            ending_balance=round(bank.ending_balance + deposit, 2),
        ),
    )
    ds.injected.append(
        InjectedDiscrepancy(
            kind="deposit_in_transit",
            account_number=acct,
            entity=entity,
            note=(
                "Deposit in transit: bank ending exceeds GL cash by "
                f"${deposit:,.2f} (deposit cleared bank, not yet booked to GL)."
            ),
        )
    )


def _inject_timing_difference(ds: SyntheticDataset) -> None:
    """Small interest accrual booked in GL, not yet on the lender statement.

    Targets entity index 2's debt account. The variance is intentionally *under*
    the materiality threshold so it classifies as a TIMING (immaterial) item.
    """
    entity = _ENTITIES[2]
    acct = "DEBT-2002"
    gl = _gl_by_acct(ds, acct)
    accrual = 18.75  # under the $50 threshold -> timing/noise
    _replace_gl(
        ds,
        GLRecord(
            entity=gl.entity,
            account_type=gl.account_type,
            account_number=gl.account_number,
            description=gl.description,
            gl_balance=round(gl.gl_balance + accrual, 2),
            dormant=gl.dormant,
        ),
    )
    ds.injected.append(
        InjectedDiscrepancy(
            kind="timing",
            account_number=acct,
            entity=entity,
            note=(
                "Timing difference: GL accrued interest of "
                f"${accrual:,.2f} not yet reflected on the lender statement "
                "(immaterial, expected to clear)."
            ),
        )
    )


def _inject_outright_error(ds: SyntheticDataset) -> None:
    """A keying error on debt principal: GL is materially wrong.

    Targets entity index 3's debt account by overstating GL principal.
    """
    entity = _ENTITIES[3]
    acct = "DEBT-2003"
    gl = _gl_by_acct(ds, acct)
    error = 12_500.00  # far above materiality -> hard FLAG
    _replace_gl(
        ds,
        GLRecord(
            entity=gl.entity,
            account_type=gl.account_type,
            account_number=gl.account_number,
            description=gl.description,
            gl_balance=round(gl.gl_balance + error, 2),
            dormant=gl.dormant,
        ),
    )
    ds.injected.append(
        InjectedDiscrepancy(
            kind="error",
            account_number=acct,
            entity=entity,
            note=(
                "Outright error: GL debt overstated by "
                f"${error:,.2f} versus the lender 3-part total (keying error)."
            ),
        )
    )


def _inject_late_paydown(ds: SyntheticDataset) -> None:
    """Populate the optional late-paydown leg so the clean tie still holds.

    Targets entity index 0's debt account. We add a paydown on the lender side
    *and* mirror it in GL, so this remains a clean tie but exercises the 3-part
    formula's third term (proving the optional leg is wired through correctly).
    """
    acct = "DEBT-2000"
    ln = _lender_by_acct(ds, acct)
    paydown = 7_500.00
    new_ln = LenderStatement(
        account_number=ln.account_number,
        lender_name=ln.lender_name,
        statement_date=ln.statement_date,
        principal=ln.principal,
        current_interest_reserve=ln.current_interest_reserve,
        late_paydown=paydown,
    )
    _replace_lender(ds, new_ln)
    gl = _gl_by_acct(ds, acct)
    _replace_gl(
        ds,
        GLRecord(
            entity=gl.entity,
            account_type=gl.account_type,
            account_number=gl.account_number,
            description=gl.description,
            gl_balance=round(
                new_ln.principal
                + new_ln.current_interest_reserve
                + new_ln.late_paydown,
                2,
            ),
            dormant=gl.dormant,
        ),
    )


def _inject_dormant_account(ds: SyntheticDataset) -> None:
    """Add a dormant zero-activity cash account that must be skipped with a note."""
    entity = _ENTITIES[0]
    acct = "CASH-1900"
    ds.gl_records.append(
        GLRecord(
            entity=entity,
            account_type="cash",
            account_number=acct,
            description=f"{entity} dormant escrow (closed)",
            gl_balance=0.0,
            dormant=True,
        )
    )
    ds.bank_statements.append(
        BankStatement(
            account_number=acct,
            bank_name=_BANKS[0],
            statement_date=ds.statement_date,
            ending_balance=0.0,
        )
    )
