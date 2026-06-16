"""CLI and report writer tests."""

from __future__ import annotations

import json

from partnership_tax import cli
from partnership_tax.engine import build_tax_package
from partnership_tax.generate import generate_source_package
from partnership_tax.report import form_preview_json, review_checks_markdown, tax_workpapers_markdown, write_outputs


def test_cli_writes_markdown_and_json(tmp_path) -> None:
    code = cli.main(["--out", str(tmp_path), "--no-xlsx"])
    assert code == 0
    assert (tmp_path / "tax_workpapers.md").exists()
    assert (tmp_path / "review_checks.md").exists()
    assert (tmp_path / "form_1065_preview.json").exists()


def test_preview_json_is_ready_and_has_lines() -> None:
    package = build_tax_package(generate_source_package())
    data = form_preview_json(package)
    assert data["status"] == "READY"
    assert len(data["form_lines"]) >= 10
    assert len(data["k1_allocations"]) == 3


def test_markdown_reports_include_fictional_notice() -> None:
    package = build_tax_package(generate_source_package())
    text = tax_workpapers_markdown(package)
    checks = review_checks_markdown(package)
    assert "FICTIONAL" in text
    assert "**Overall status:** READY" in checks


def test_write_outputs_can_create_support_workbook(tmp_path) -> None:
    package = build_tax_package(generate_source_package())
    written = write_outputs(package, tmp_path, write_xlsx=True)
    names = {path.name for path in written}
    assert "1065_supporting_package.xlsx" in names


def test_json_round_trips(tmp_path) -> None:
    package = build_tax_package(generate_source_package())
    write_outputs(package, tmp_path, write_xlsx=False)
    data = json.loads((tmp_path / "form_1065_preview.json").read_text(encoding="utf-8"))
    assert data["partnership_name"] == "Demo 721 Development LP"
    assert data["checks"][0]["status"] == "OK"
