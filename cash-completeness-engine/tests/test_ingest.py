"""Ingestion: register and trial-balance loaders build the shared contracts."""

from __future__ import annotations

import os

import pytest

from ccengine.ingest import (
    load_registers,
    load_trial_balance,
    load_xlsx_registers,
    load_xlsx_trial_balance,
)
from tests.conftest import write_register_csv, write_tb_csv

try:
    import openpyxl  # noqa: F401

    HAVE_OPENPYXL = True
except ImportError:
    HAVE_OPENPYXL = False


# ---------------------------------------------------------------------------
# Registers
# ---------------------------------------------------------------------------


def test_register_file_loads_metadata_and_transactions(tmp_path):
    write_register_csv(
        str(tmp_path / "juniper42.csv"),
        entity="Juniper 42 Development LLC",
        bank="First Legacy Bank",
        account_no="000111222",
        gl="615-001-00-1133",
        status="closed",
        as_of="2026-06-30",
        rows=[
            ("2026-06-01", "Opening balance", "0.00", "52140.25", ""),
            (
                "2026-06-28",
                "Transfer to Union National Bank, closing",
                "-52140.25",
                "0.00",
                "Union National Bank",
            ),
        ],
    )
    accounts = load_registers(str(tmp_path))
    assert len(accounts) == 1
    acct = accounts[0]
    assert acct.source_file == "juniper42.csv"
    assert acct.entity == "Juniper 42 Development LLC"
    assert acct.bank == "First Legacy Bank"
    assert acct.bank_account_no == "000111222"
    assert acct.gl_raw == "615-001-00-1133"
    assert acct.gl_norm == "615-001-1133"  # normalized at ingest
    assert acct.status == "closed"
    assert acct.as_of == "2026-06-30"
    assert acct.balance == 0.00
    assert len(acct.transactions) == 2
    # Quoted comma survives inside the description.
    assert acct.transactions[1].description == (
        "Transfer to Union National Bank, closing"
    )
    assert acct.transactions[1].counterparty == "Union National Bank"
    # Blank counterparty becomes None, never "".
    assert acct.transactions[0].counterparty is None


def test_register_defaults_balance_and_as_of_from_last_transaction(tmp_path):
    write_register_csv(
        str(tmp_path / "harbor17.csv"),
        entity="Harbor 17 Investor LLC",
        bank="Union National Bank",
        account_no="4400123002",
        gl="424-002-1101",
        rows=[
            ("2026-06-05", "Incoming wire", "84210.55", "84210.55", ""),
        ],
    )
    acct = load_registers(str(tmp_path))[0]
    assert acct.status == "live"  # default when metadata omits it
    assert acct.balance == 84210.55
    assert acct.as_of == "2026-06-05"


def test_register_metadata_balance_and_aliases_override(tmp_path):
    path = tmp_path / "aliased.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("# entity: Wrenfield 28 Development LLC\n")
        fh.write("# bank name = Coastal Mutual\n")  # alias + '=' separator
        fh.write("# account_no: 770055009\n")  # alias for bank_account_no
        fh.write("# gl: 424-006-1101\n")  # alias for gl_account
        fh.write("# balance: $1,234.56\n")
        fh.write("# as_of: 2026-06-30\n")
        fh.write("# prepared_by: not a recognised key, ignored\n")
        fh.write("\n")
        fh.write("2026-06-02,Deposit,1000.00,1000.00,\n")
    acct = load_registers(str(tmp_path))[0]
    assert acct.bank == "Coastal Mutual"
    assert acct.bank_account_no == "770055009"
    assert acct.gl_norm == "424-006-1101"
    assert acct.balance == 1234.56  # metadata wins over last running balance
    assert acct.as_of == "2026-06-30"


def test_registers_load_in_sorted_file_order_and_skip_non_csv(tmp_path):
    for name, gl in [("b_second.csv", "424-002-1101"), ("a_first.csv", "615-001-1101")]:
        write_register_csv(
            str(tmp_path / name),
            entity="Demo Holdings LLC",
            bank="Union National Bank",
            account_no="4400123000",
            gl=gl,
            rows=[("2026-06-01", "Opening balance", "0.00", "10.00", "")],
        )
    (tmp_path / "notes.txt").write_text("not a register", encoding="utf-8")
    accounts = load_registers(str(tmp_path))
    assert [a.source_file for a in accounts] == ["a_first.csv", "b_second.csv"]


def test_register_missing_metadata_fails_loudly(tmp_path):
    path = tmp_path / "broken.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("# entity: Demo Holdings LLC\n")
        fh.write("# bank: Union National Bank\n")
        # bank_account_no and gl_account deliberately missing
        fh.write("2026-06-01,Deposit,10.00,10.00,\n")
    with pytest.raises(ValueError, match="gl_account"):
        load_registers(str(tmp_path))


def test_register_invalid_status_fails_loudly(tmp_path):
    write_register_csv(
        str(tmp_path / "badstatus.csv"),
        entity="Demo Holdings LLC",
        bank="Union National Bank",
        account_no="4400123000",
        gl="615-001-1101",
        status="dormant",
        rows=[("2026-06-01", "Deposit", "10.00", "10.00", "")],
    )
    with pytest.raises(ValueError, match="status"):
        load_registers(str(tmp_path))


def test_register_short_row_and_bad_amount_fail_loudly(tmp_path):
    write_register_csv(
        str(tmp_path / "short.csv"),
        entity="Demo Holdings LLC",
        bank="Union National Bank",
        account_no="4400123000",
        gl="615-001-1101",
        rows=[("2026-06-01", "Deposit", "10.00")],  # no running_balance
    )
    with pytest.raises(ValueError):
        load_registers(str(tmp_path))

    for name in os.listdir(tmp_path):
        os.remove(tmp_path / name)
    write_register_csv(
        str(tmp_path / "badamount.csv"),
        entity="Demo Holdings LLC",
        bank="Union National Bank",
        account_no="4400123000",
        gl="615-001-1101",
        rows=[("2026-06-01", "Deposit", "ten dollars", "10.00", "")],
    )
    with pytest.raises(ValueError, match="amount"):
        load_registers(str(tmp_path))


def test_register_amount_parsing_handles_accounting_styles(tmp_path):
    write_register_csv(
        str(tmp_path / "styles.csv"),
        entity="Demo Holdings LLC",
        bank="Union National Bank",
        account_no="4400123000",
        gl="615-001-1101",
        rows=[
            ("2026-06-01", "Deposit", "$1,234.56", "1234.56", ""),
            ("2026-06-02", "Payment", "(234.56)", "1000.00", ""),
        ],
    )
    acct = load_registers(str(tmp_path))[0]
    assert acct.transactions[0].amount == 1234.56
    assert acct.transactions[1].amount == -234.56
    assert acct.balance == 1000.00


def test_missing_register_directory_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_registers(str(tmp_path / "nope"))


# ---------------------------------------------------------------------------
# Trial balance
# ---------------------------------------------------------------------------


def test_trial_balance_loads_rows_and_keeps_typo_lines(tmp_path):
    tb_path = write_tb_csv(
        str(tmp_path / "trial_balance.csv"),
        rows=[
            ("TB-JUN", "615-001-00-1133", "Cash - legacy", "52,140.25"),
            ("TB-JUN", "BAL", "mis-keyed balance row", "(1,250.00)"),
            ("TB-JUN", "", "blank GL cell", "0.00"),
        ],
    )
    rows = load_trial_balance(tb_path)
    assert len(rows) == 3
    assert rows[0].source_file == "trial_balance.csv"
    assert rows[0].sheet == "TB-JUN"
    assert rows[0].gl_raw == "615-001-00-1133"
    assert rows[0].gl_norm == "615-001-1133"
    assert rows[0].balance == 52140.25
    # The typo line survives ingestion verbatim -- never laundered out.
    assert rows[1].gl_raw == "BAL"
    assert rows[1].gl_norm == "BAL"
    assert rows[1].balance == -1250.00
    assert rows[2].gl_norm == ""


def test_trial_balance_missing_file_and_short_row(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_trial_balance(str(tmp_path / "missing.csv"))

    path = tmp_path / "short.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("sheet,gl_account,title,balance\n")
        fh.write("TB-JUN,615-001-1101,Cash\n")  # missing balance column
    with pytest.raises(ValueError):
        load_trial_balance(str(path))


# ---------------------------------------------------------------------------
# Optional xlsx loaders (guarded dependency)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    HAVE_OPENPYXL, reason="openpyxl installed; RuntimeError path unreachable"
)
def test_xlsx_loaders_raise_clear_error_without_openpyxl(tmp_path):
    with pytest.raises(RuntimeError, match="openpyxl"):
        load_xlsx_registers(str(tmp_path))
    with pytest.raises(RuntimeError, match="openpyxl"):
        load_xlsx_trial_balance(str(tmp_path / "tb.xlsx"))


@pytest.mark.skipif(not HAVE_OPENPYXL, reason="openpyxl not installed")
def test_xlsx_register_loader_mirrors_csv_layout(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["entity", "Juniper 42 Development LLC"])
    ws.append(["bank", "Union National Bank"])
    ws.append(["bank_account_no", "4400123001"])
    ws.append(["gl_account", "615-001-00-1101"])
    ws.append(["status", "live"])
    ws.append(["date", "description", "amount", "running_balance", "counterparty"])
    ws.append(["2026-06-01", "Opening balance", 0.0, 150000.0, ""])
    ws.append(["2026-06-10", "Draw deposit", 25000.0, 175000.0, ""])
    wb.save(str(tmp_path / "juniper42.xlsx"))

    accounts = load_xlsx_registers(str(tmp_path))
    assert len(accounts) == 1
    acct = accounts[0]
    assert acct.gl_norm == "615-001-1101"
    assert acct.balance == 175000.00
    assert len(acct.transactions) == 2


@pytest.mark.skipif(not HAVE_OPENPYXL, reason="openpyxl not installed")
def test_xlsx_trial_balance_three_column_layout_uses_sheet_title(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TB-JUN"
    ws.append(["gl_account", "title", "balance"])
    ws.append(["615-001-1101", "Cash - operating", 160000.0])
    path = str(tmp_path / "tb.xlsx")
    wb.save(path)

    rows = load_xlsx_trial_balance(path)
    assert len(rows) == 1
    assert rows[0].sheet == "TB-JUN"
    assert rows[0].gl_norm == "615-001-1101"
    assert rows[0].balance == 160000.00
