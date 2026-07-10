"""Shared test fixtures and helpers.

Builds small, hand-controlled register/TB structures so each classification
behaviour can be asserted in isolation, plus one session-scoped demo dataset
that exercises every exception class end to end (tie, Class A/B/C/D, a
resolved closed account, and a phantom TB row).

All entities, banks, account numbers and figures are fictional.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import pytest

from ccengine.models import RegisterAccount, TBRow, Transaction
from ccengine.normalize import normalize_gl

# ---------------------------------------------------------------------------
# Canonical GL keys of the session demo dataset (fictional)
# ---------------------------------------------------------------------------

#: Live account that ties to the TB to the cent.
GL_TIED = "615-001-1101"
#: Live successor-bank account with no TB row (Class A).
GL_A = "424-002-1101"
#: Closed legacy account whose stale balance the TB still carries (Class B).
GL_B = "615-001-1133"
#: Live account whose difference is deposit-in-transit timing (Class C).
GL_C = "424-003-1101"
#: Live account with an unexplained difference (Class D).
GL_D = "424-004-1101"
#: Closed account, swept to zero AND absent from the TB (resolved; ties by
#: absence and must still appear in scope).
GL_RESOLVED = "424-005-1133"
#: Mis-keyed placeholder TB row with no register behind it (phantom).
GL_PHANTOM = "001-001-0000"

ALL_REGISTER_GLS = (GL_TIED, GL_A, GL_B, GL_C, GL_D, GL_RESOLVED)

ENTITY_TIED = "Juniper 42 Development LLC"
ENTITY_A = "Harbor 17 Investor LLC"
ENTITY_B = "Juniper 42 Development LLC"
ENTITY_C = "Bluffside 9 Townhomes LLC"
ENTITY_D = "Kestrel Capital Partners LLC"
ENTITY_RESOLVED = "Saltgrass 6 Services LLC"

BANK_LEGACY = "First Legacy Bank"
BANK_SUCCESSOR = "Union National Bank"
BANK_THIRD = "Coastal Mutual"

#: Headline figures of the demo dataset, used by assertions.
BALANCE_TIED = 160000.00
BALANCE_A = 84210.55
BALANCE_B_PRE_SWEEP = 52140.25
BALANCE_C_REGISTER = 57500.00
BALANCE_C_TB = 50000.00
BALANCE_D_REGISTER = 12500.00
BALANCE_D_TB = 11000.00
BALANCE_PHANTOM = 1250.00


# ---------------------------------------------------------------------------
# In-memory model builders (no file IO)
# ---------------------------------------------------------------------------


def make_txn(
    date: str,
    description: str,
    amount: float,
    running_balance: float,
    counterparty: Optional[str] = None,
) -> Transaction:
    return Transaction(
        date=date,
        description=description,
        amount=amount,
        running_balance=running_balance,
        counterparty=counterparty,
    )


def make_account(
    gl: str,
    balance: float,
    status: str = "live",
    entity: str = ENTITY_TIED,
    bank: str = BANK_SUCCESSOR,
    txns: Optional[Sequence[Transaction]] = None,
    source_file: Optional[str] = None,
    account_no: str = "000111222",
    as_of: str = "2026-06-30",
) -> RegisterAccount:
    return RegisterAccount(
        source_file=source_file or f"{gl}.csv",
        entity=entity,
        bank=bank,
        bank_account_no=account_no,
        gl_raw=gl,
        gl_norm=normalize_gl(gl),
        balance=balance,
        as_of=as_of,
        status=status,
        transactions=list(txns or []),
    )


def make_tb_row(
    gl: str,
    balance: float,
    sheet: str = "TB-JUN",
    title: str = "Cash - operating",
    source_file: str = "trial_balance.csv",
) -> TBRow:
    return TBRow(
        source_file=source_file,
        sheet=sheet,
        gl_raw=gl,
        gl_norm=normalize_gl(gl) if gl else "",
        title=title,
        balance=balance,
    )


# ---------------------------------------------------------------------------
# CSV writers (mirror the documented source-file formats)
# ---------------------------------------------------------------------------


def write_register_csv(
    path: str,
    entity: str,
    bank: str,
    account_no: str,
    gl: str,
    rows: Sequence[Tuple],
    status: Optional[str] = None,
    as_of: Optional[str] = None,
    balance: Optional[str] = None,
    extra_meta: Optional[Sequence[str]] = None,
) -> str:
    """Write one register CSV in the engine's documented format."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(f"# entity: {entity}\n")
        fh.write(f"# bank: {bank}\n")
        fh.write(f"# bank_account_no: {account_no}\n")
        fh.write(f"# gl_account: {gl}\n")
        if status is not None:
            fh.write(f"# status: {status}\n")
        if as_of is not None:
            fh.write(f"# as_of: {as_of}\n")
        if balance is not None:
            fh.write(f"# balance: {balance}\n")
        for line in extra_meta or []:
            fh.write(line + "\n")
        writer = csv.writer(fh)
        writer.writerow(
            ["date", "description", "amount", "running_balance", "counterparty"]
        )
        for row in rows:
            writer.writerow(row)
    return path


def write_tb_csv(path: str, rows: Sequence[Tuple]) -> str:
    """Write the trial-balance CSV (``sheet,gl_account,title,balance``)."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("# fictional trial balance - portfolio demonstration\n")
        writer = csv.writer(fh)
        writer.writerow(["sheet", "gl_account", "title", "balance"])
        for row in rows:
            writer.writerow(row)
    return path


# ---------------------------------------------------------------------------
# Session demo dataset: every class represented, internally footed registers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoDataset:
    """Paths of the generated demo dataset."""

    registers_dir: str
    tb_path: str


@pytest.fixture(scope="session")
def demo_dataset(tmp_path_factory: pytest.TempPathFactory) -> DemoDataset:
    """Write the full fictional demo dataset once per test session.

    Every register's running balances internally foot (prior balance +
    amount == balance), because the independent verifier checks that and a
    foot break would downgrade its verdict to GO_WITH_FIXES.
    """
    root = tmp_path_factory.mktemp("cc_demo")
    registers_dir = root / "registers"
    registers_dir.mkdir()

    # 1. Tied: live, register == TB to the cent.
    write_register_csv(
        str(registers_dir / "juniper42_successor_operating.csv"),
        entity=ENTITY_TIED,
        bank=BANK_SUCCESSOR,
        account_no="4400123001",
        gl="615-001-00-1101",  # filler spelling; normalizes to GL_TIED
        status="live",
        as_of="2026-06-30",
        rows=[
            ("2026-06-01", "Opening balance", "0.00", "150000.00", ""),
            ("2026-06-10", "Draw deposit", "25000.00", "175000.00", ""),
            ("2026-06-20", "Vendor payment", "-15000.00", "160000.00", ""),
        ],
    )

    # 2. Class A: live successor account the TB has never seen.
    write_register_csv(
        str(registers_dir / "harbor17_successor_new.csv"),
        entity=ENTITY_A,
        bank=BANK_SUCCESSOR,
        account_no="4400123002",
        gl=GL_A,
        status="live",
        as_of="2026-06-30",
        rows=[
            ("2026-06-05", "Incoming wire - account funding", "84210.55", "84210.55", ""),
        ],
    )

    # 3. Class B: closed legacy account, swept to zero, TB still carries the
    #    pre-sweep balance.
    write_register_csv(
        str(registers_dir / "juniper42_legacy_closed.csv"),
        entity=ENTITY_B,
        bank=BANK_LEGACY,
        account_no="000988771",
        gl="615-001-00-1133",  # filler spelling; normalizes to GL_B
        status="closed",
        as_of="2026-06-30",
        rows=[
            ("2026-06-01", "Opening balance", "0.00", "52140.25", ""),
            (
                "2026-06-28",
                "Transfer to Union National Bank - to close account",
                "-52140.25",
                "0.00",
                BANK_SUCCESSOR,
            ),
        ],
    )

    # 4. Class C: live account; the difference is one deposit in transit.
    write_register_csv(
        str(registers_dir / "bluffside9_successor_operating.csv"),
        entity=ENTITY_C,
        bank=BANK_SUCCESSOR,
        account_no="4400123003",
        gl=GL_C,
        status="live",
        as_of="2026-06-30",
        rows=[
            ("2026-06-01", "Opening balance", "0.00", "40000.00", ""),
            ("2026-06-15", "Homeowner deposit", "10000.00", "50000.00", ""),
            ("2026-06-30", "Deposit in transit", "7500.00", "57500.00", ""),
        ],
    )

    # 5. Class D: live account whose difference nothing in the register
    #    explains.
    write_register_csv(
        str(registers_dir / "kestrel_thirdbank_operating.csv"),
        entity=ENTITY_D,
        bank=BANK_THIRD,
        account_no="770055001",
        gl=GL_D,
        status="live",
        as_of="2026-06-30",
        rows=[
            ("2026-06-01", "Opening balance", "0.00", "10000.00", ""),
            ("2026-06-12", "Management fee received", "2500.00", "12500.00", ""),
        ],
    )

    # 6. Resolved: closed, swept to zero, and absent from the TB altogether.
    write_register_csv(
        str(registers_dir / "saltgrass_legacy_resolved.csv"),
        entity=ENTITY_RESOLVED,
        bank=BANK_LEGACY,
        account_no="000988772",
        gl=GL_RESOLVED,
        status="closed",
        as_of="2026-06-30",
        rows=[
            ("2026-05-01", "Opening balance", "0.00", "1200.00", ""),
            ("2026-05-20", "To close account", "-1200.00", "0.00", BANK_SUCCESSOR),
        ],
    )

    tb_path = str(root / "trial_balance.csv")
    write_tb_csv(
        tb_path,
        rows=[
            ("TB-JUN", GL_TIED, "Cash - operating (successor)", "160000.00"),
            ("TB-JUN", "615-001-00-1133", "Cash - legacy (closed)", "52140.25"),
            ("TB-JUN", GL_C, "Cash - operating", "50000.00"),
            ("TB-JUN", GL_D, "Cash - operating", "11000.00"),
            ("TB-JUN", GL_PHANTOM, "BAL", "1250.00"),
        ],
    )

    return DemoDataset(registers_dir=str(registers_dir), tb_path=tb_path)
