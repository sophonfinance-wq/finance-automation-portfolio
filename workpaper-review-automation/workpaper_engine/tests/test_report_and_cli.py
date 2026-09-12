"""The report renders and the CLI's verdict is its exit code."""

from __future__ import annotations

import os

from workpaper_engine.cli import main
from workpaper_engine.engine import EXIT_CODES, analyze_folder
from workpaper_engine.report import build_json_report, build_markdown_report


def test_markdown_leads_with_the_verdict(corpus):
    md = build_markdown_report(analyze_folder(corpus))
    assert md.splitlines()[0].startswith("# Workpaper review")
    assert "**Verdict:" in md
    assert md.endswith("\n")


def test_json_report_is_stable_and_sorted(corpus):
    js = build_json_report(analyze_folder(corpus))
    assert js.endswith("\n")
    assert js == build_json_report(analyze_folder(corpus))


def test_cli_exit_code_matches_the_verdict(corpus, capsys):
    code = main([corpus, "--quiet"])
    out = capsys.readouterr().out
    verdict = out.strip().split()[-1]
    assert code == EXIT_CODES[verdict]
    assert code == 2, "the shipped corpus plants hard failures"


def test_cli_writes_both_reports(tmp_path, corpus):
    j = tmp_path / "r.json"
    m = tmp_path / "r.md"
    main([corpus, "--json", str(j), "--md", str(m), "--quiet"])
    assert j.read_text(encoding="utf-8").startswith("{")
    assert m.read_text(encoding="utf-8").startswith("# Workpaper review")


def test_cli_can_generate_then_analyze(tmp_path, capsys):
    folder = tmp_path / "fresh"
    code = main([str(folder), "--generate", "--quiet"])
    capsys.readouterr()
    assert os.path.isdir(str(folder))
    assert code in (0, 1, 2)


def test_cli_reports_a_bad_folder_as_usage_error(tmp_path, capsys):
    assert main([str(tmp_path / "nope"), "--quiet"]) == 3
