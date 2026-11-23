"""Report structure, the build register page, and the CLI's exit-code contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workpaper_engine.build import WorkpaperPackage
from workpaper_engine.cli import emit_builds, main
from workpaper_engine.engine import REGISTRY, analyze_folder
from workpaper_engine.model import DocumentReport, Status, Verdict
from workpaper_engine.report import (
    build_json_report,
    build_markdown_report,
    build_register_markdown,
    write_reports,
)


# --------------------------------------------------------------------------- #
# JSON report
# --------------------------------------------------------------------------- #
def test_json_report_shape(reports: list[DocumentReport]) -> None:
    doc = build_json_report(reports)
    assert doc["overall_verdict"] in {v.value for v in Verdict}
    assert doc["file_count"] == len(reports)
    assert doc["rule_count"] == len(REGISTRY)
    assert len(doc["rules"]) == len(REGISTRY)
    assert len(doc["files"]) == len(reports)


def test_json_report_lists_rules_in_registry_order(
    reports: list[DocumentReport],
) -> None:
    """Report order follows the registry so a diff is readable."""
    doc = build_json_report(reports)
    assert [r["rule"] for r in doc["rules"]] == [r for r, _f in REGISTRY]


def test_json_report_is_serialisable(reports: list[DocumentReport]) -> None:
    json.dumps(build_json_report(reports))


def test_json_report_severities_are_valid(reports: list[DocumentReport]) -> None:
    for rule in build_json_report(reports)["rules"]:
        assert rule["severity"] in {Status.FAIL.value, Status.FLAG.value}


def test_json_exception_counts_match_findings(reports: list[DocumentReport]) -> None:
    """The per-rule tally is derived from the findings, not maintained separately."""
    doc = build_json_report(reports)
    counted: dict[str, int] = {}
    for report in reports:
        for finding in report.findings:
            if finding.status is not Status.PASS:
                counted[finding.rule] = counted.get(finding.rule, 0) + 1
    for rule in doc["rules"]:
        assert rule["exceptions"] == counted.get(rule["rule"], 0)


# --------------------------------------------------------------------------- #
# Markdown control report
# --------------------------------------------------------------------------- #
def test_markdown_report_has_structure(reports: list[DocumentReport]) -> None:
    md = build_markdown_report(reports)
    assert md.startswith("# ")
    assert "**Overall verdict:**" in md
    assert "## Controls" in md
    assert "## Build files" in md
    assert md.endswith("\n")


def test_markdown_lists_every_rule(reports: list[DocumentReport]) -> None:
    md = build_markdown_report(reports)
    for rule_id, _fn in REGISTRY:
        assert f"`{rule_id}`" in md


def test_markdown_lists_every_build_file(reports: list[DocumentReport]) -> None:
    md = build_markdown_report(reports)
    for report in reports:
        assert report.document in md


def test_markdown_states_the_data_is_fictional(reports: list[DocumentReport]) -> None:
    """The claim is load-bearing and belongs in the artifact, not only the README."""
    assert "fictional" in build_markdown_report(reports).lower()


def test_markdown_states_the_year_comes_from_the_file(
    reports: list[DocumentReport],
) -> None:
    """A roll tested against the system clock would report differently next July.

    The report says the fiscal year comes from the file, and that claim is the
    reason the committed output is diffable at all, so it is asserted rather than
    trusted.
    """
    assert "never the system clock" in build_markdown_report(reports)


def test_write_reports_creates_both(
    reports: list[DocumentReport], tmp_path: Path
) -> None:
    written = write_reports(
        reports, json_path=tmp_path / "r.json", md_path=tmp_path / "r.md"
    )
    assert len(written) == 2
    assert all(p.exists() for p in written)
    json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))


def test_write_reports_creates_parent_directories(
    reports: list[DocumentReport], tmp_path: Path
) -> None:
    target = tmp_path / "nested" / "deeper" / "r.json"
    write_reports(reports, json_path=target)
    assert target.exists()


def test_write_reports_writes_nothing_when_asked_for_nothing(
    reports: list[DocumentReport],
) -> None:
    assert write_reports(reports) == []


# --------------------------------------------------------------------------- #
# The build register page
# --------------------------------------------------------------------------- #
def test_register_page_names_every_constructed_cell(built: WorkpaperPackage) -> None:
    """The reviewable page lists each cell the build claims to have constructed."""
    md = build_register_markdown(built)
    for entry in built.build_register:
        assert f"`{entry.cell_id}`" in md


def test_register_page_carries_the_chain_of_custody(built: WorkpaperPackage) -> None:
    """The three digests are on the page a reviewer signs, not only in the file."""
    md = build_register_markdown(built)
    manifest = built.manifest_doc()
    assert manifest["locked_source_digest"] in md
    assert manifest["prebuild_image_digest"] in md
    assert manifest["built_package_digest"] in md


def test_register_page_states_both_years(built: WorkpaperPackage) -> None:
    md = build_register_markdown(built)
    assert str(built.fiscal_year) in md
    assert str(built.prior_fiscal_year) in md


def test_register_page_groups_by_schedule(built: WorkpaperPackage) -> None:
    md = build_register_markdown(built)
    for schedule in ("captions", "trial_balance", "equity", "member_capital", "evidence"):
        assert f"## {schedule}" in md


def test_register_page_is_byte_stable(built: WorkpaperPackage) -> None:
    assert build_register_markdown(built) == build_register_markdown(built)


# --------------------------------------------------------------------------- #
# DocumentReport roll-up
# --------------------------------------------------------------------------- #
def test_counts_cover_every_status(reports: list[DocumentReport]) -> None:
    for report in reports:
        counts = report.counts()
        assert set(counts) == {s.value for s in Status}
        assert sum(counts.values()) == len(report.findings)


def test_rules_fired_excludes_passes_and_deduplicates(
    reports: list[DocumentReport],
) -> None:
    for report in reports:
        fired = report.rules_fired()
        assert len(fired) == len(set(fired))
        passing_only = {
            f.rule for f in report.findings if f.status is Status.PASS
        } - {f.rule for f in report.findings if f.status is not Status.PASS}
        assert not (set(fired) & passing_only)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_generate_then_analyze(tmp_path: Path) -> None:
    """Generating into an empty folder and analyzing it returns a real verdict."""
    code = main([str(tmp_path), "--generate", "--quiet"])
    assert code in (0, 1, 2)
    assert list(tmp_path.glob("*.json"))


def test_cli_emits_a_built_package_and_its_register(tmp_path: Path) -> None:
    """The headline: the CLI constructs packages and writes them out.

    This is the engine's product, so the CLI is asserted to produce it rather
    than merely to report on it -- one package file and one register page per
    build file, and the package has to carry the schedules a workpaper is made of.
    """
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    main([str(corpus), "--generate", "--build", str(out), "--quiet"])
    packages = sorted(out.glob("*.package.json"))
    registers = sorted(out.glob("*.register.md"))
    assert packages and len(packages) == len(registers)
    payload = json.loads(packages[0].read_text(encoding="utf-8"))
    assert set(payload) == {"built_package", "build_register", "manifest"}
    for schedule in (
        "trial_balance", "balance_sheet", "profit_loss", "equity",
        "member_capital", "earnings_and_profits", "evidence", "captions",
    ):
        assert schedule in payload["built_package"], schedule
    assert payload["build_register"]["entries"]
    assert payload["manifest"]["built_package_digest"]


def test_emit_builds_constructs_rather_than_copies(tmp_path: Path) -> None:
    """The emitted package comes from the pipeline, not from the file it read.

    A defect file's stored package carries the planted break; rebuilding it from
    the same inputs must produce the clean construction instead, which is what
    proves the emitter ran the builder.
    """
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    main([str(corpus), "--generate", "--quiet"])
    emit_builds(corpus, out)
    defect = next(out.glob("equity_total_typed_over*.package.json"))
    clean = next(out.glob("clean*.package.json"))
    rebuilt = json.loads(defect.read_text(encoding="utf-8"))["built_package"]
    reference = json.loads(clean.read_text(encoding="utf-8"))["built_package"]
    assert rebuilt["equity"]["total_cents"] == reference["equity"]["total_cents"]


def test_cli_exit_code_matches_verdict(corpus: Path) -> None:
    """The exit code is the verdict, which is what a CI gate keys on."""
    expected = {Verdict.PASS: 0, Verdict.REVIEW: 1, Verdict.FAIL: 2}
    reports = analyze_folder(corpus)
    verdict = (
        Verdict.FAIL if any(r.verdict is Verdict.FAIL for r in reports)
        else Verdict.REVIEW if any(r.verdict is Verdict.REVIEW for r in reports)
        else Verdict.PASS
    )
    assert main([str(corpus), "--quiet"]) == expected[verdict]


def test_cli_missing_folder_is_usage_error(tmp_path: Path) -> None:
    assert main([str(tmp_path / "nope"), "--quiet"]) == 3


def test_cli_empty_folder_is_usage_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty), "--quiet"]) == 3


def test_cli_build_on_an_empty_folder_is_a_usage_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty), "--build", str(tmp_path / "out"), "--quiet"]) == 3


def test_cli_writes_requested_reports(corpus: Path, tmp_path: Path) -> None:
    main([
        str(corpus), "--quiet",
        "--json", str(tmp_path / "out.json"),
        "--md", str(tmp_path / "out.md"),
    ])
    assert (tmp_path / "out.json").exists()
    assert (tmp_path / "out.md").exists()


def test_cli_verbose_prints_findings(corpus: Path, capsys: pytest.CaptureFixture) -> None:
    main([str(corpus)])
    out = capsys.readouterr().out
    assert "verdict:" in out
    assert "Overall verdict:" in out


def test_cli_verbose_announces_the_build(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    corpus = tmp_path / "corpus"
    main([str(corpus), "--generate", "--build", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert "workpaper package(s) with build register(s)" in out
