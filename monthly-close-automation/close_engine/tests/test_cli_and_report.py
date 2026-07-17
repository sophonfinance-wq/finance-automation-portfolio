"""Tests for the CLI entrypoint and the output writers."""

from __future__ import annotations

import json
from pathlib import Path

from close_engine import cli, report
from close_engine.engine import CloseEngine
from close_engine.generate import generate_dataset


def test_cli_clean_close_returns_zero_and_tracked_outputs_are_fresh(tmp_path) -> None:
    code = cli.main(["--period", "2026-03", "--out", str(tmp_path), "--seed", "2026"])
    assert code == 0
    tracked_output = Path(__file__).resolve().parents[2] / "output"
    # Every deterministic committed output must match a clean regeneration.
    for name in (
        "je_register.md",
        "je_register.json",
        "schedules.json",
        "trial_balance.md",
        "trial_balance.json",
        "close_report.md",
        "sentinel.json",
    ):
        assert (tmp_path / name).exists(), f"missing {name}"
        assert (tmp_path / name).read_text("utf-8") == (
            tracked_output / name
        ).read_text("utf-8"), f"stale tracked output: {name}"


def test_cli_rejects_bad_period(tmp_path) -> None:
    import pytest

    with pytest.raises(SystemExit):
        cli.main(["--period", "2026-13", "--out", str(tmp_path)])


def test_register_json_round_trips_and_balances(tmp_path) -> None:
    result = CloseEngine(generate_dataset("2026-03")).run()
    report.write_outputs(result, tmp_path)
    data = json.loads((tmp_path / "je_register.json").read_text(encoding="utf-8"))
    assert data["period"] == "2026-03"
    for entry in data["entries"]:
        assert entry["total_debits_cents"] == entry["total_credits_cents"]
        assert entry["is_balanced"] is True


def test_trial_balance_json_in_balance(tmp_path) -> None:
    result = CloseEngine(generate_dataset("2026-03")).run()
    report.write_outputs(result, tmp_path)
    data = json.loads((tmp_path / "trial_balance.json").read_text(encoding="utf-8"))
    assert data["in_balance"] is True
    assert data["total_debits_cents"] == data["total_credits_cents"]


def test_close_report_reports_clean(tmp_path) -> None:
    result = CloseEngine(generate_dataset("2026-03")).run()
    report.write_outputs(result, tmp_path)
    text = (tmp_path / "close_report.md").read_text(encoding="utf-8")
    assert "Close status: CLEAN" in text
    # All fictional entities are present.
    assert "Demo Holdings LLC" in text
    assert "Maple Fund LP" in text
    assert "Birchwood Op Co" in text


def test_xlsx_written_when_openpyxl_available(tmp_path) -> None:
    result = CloseEngine(generate_dataset("2026-03")).run()
    written = report.write_outputs(result, tmp_path)
    # openpyxl is a declared dependency, so the workbook should be present.
    assert any(p.name == "close_workbook.xlsx" for p in written)
