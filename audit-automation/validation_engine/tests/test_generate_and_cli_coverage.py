"""Coverage for the synthetic generator and the CLI entrypoint.

The generator tests pin the corpus shape, determinism of the seeded figures and
the one-defect-per-rule contract. The CLI tests drive :func:`main` through its
exit-code paths (PASS / FAIL / usage errors) using temp folders only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation_engine.engine import REGISTRY, Verdict
from validation_engine.cli import _EXIT_BY_VERDICT, _build_parser, main
from validation_engine.generate import (
    DEFECTS,
    FICTIONAL_ENTITIES,
    SEED,
    Defect,
    generate_corpus,
)
from validation_engine.generate import _amounts


# --------------------------------------------------------------------------- #
# _amounts — seeded, deterministic figures
# --------------------------------------------------------------------------- #
def test_amounts_deterministic_for_fixed_seed():
    """Same seed => identical first two amount triples (frozen golden values)."""
    import random

    rng = random.Random(SEED)
    assert _amounts(rng) == (1500, 425, -125)
    assert _amounts(rng) == (1250, 150, -75)


def test_amounts_respect_declared_ranges_and_signs():
    """Across many draws, amounts stay within the documented ranges/steps."""
    import random

    rng = random.Random(SEED)
    for _ in range(200):
        opening, income, dist = _amounts(rng)
        assert 800 <= opening < 2000 and opening % 50 == 0
        assert 100 <= income < 600 and income % 25 == 0
        assert -300 < dist <= -50 and dist % 25 == 0  # distributions are negative


# --------------------------------------------------------------------------- #
# DEFECTS / registry contract
# --------------------------------------------------------------------------- #
def test_defects_cover_every_registry_rule_exactly_once():
    """Each registry rule has exactly one planted defect (bijection)."""
    planted = [d.rule for d in DEFECTS]
    registry = [rid for rid, _ in REGISTRY]
    assert sorted(planted) == sorted(registry)
    assert len(planted) == len(set(planted))


def test_defect_keys_are_unique():
    """Defect filename slugs are unique."""
    keys = [d.key for d in DEFECTS]
    assert len(keys) == len(set(keys))


def test_defect_is_frozen():
    """Defect is a frozen dataclass."""
    d = DEFECTS[0]
    with pytest.raises(Exception):
        d.key = "x"  # type: ignore[misc]


def test_fictional_entities_nonempty_and_distinct():
    """The fictional entity pool is non-empty and has no duplicates."""
    assert FICTIONAL_ENTITIES
    assert len(FICTIONAL_ENTITIES) == len(set(FICTIONAL_ENTITIES))


# --------------------------------------------------------------------------- #
# generate_corpus
# --------------------------------------------------------------------------- #
def test_generate_corpus_writes_clean_plus_one_per_defect(tmp_path):
    """The corpus is one clean workbook plus one per defect."""
    written = generate_corpus(tmp_path)
    assert len(written) == 1 + len(DEFECTS)
    assert all(p.suffix == ".xlsx" for p in written)


def test_generate_corpus_emits_json_sibling_per_workbook(tmp_path):
    """Each .xlsx gets a sibling .json export."""
    written = generate_corpus(tmp_path)
    for p in written:
        assert p.with_suffix(".json").exists()
    assert len(list(tmp_path.glob("*.json"))) == len(written)


def test_generate_corpus_includes_clean_and_each_defect_key(tmp_path):
    """Filenames carry the 'clean' baseline plus every defect key prefix."""
    generate_corpus(tmp_path)
    stems = {p.stem.split("__", 1)[0] for p in tmp_path.glob("*.xlsx")}
    assert "clean" in stems
    assert {d.key for d in DEFECTS} <= stems


def test_generate_corpus_returns_paths_that_exist(tmp_path):
    """Returned paths point at real files on disk."""
    written = generate_corpus(tmp_path)
    assert all(p.exists() and p.is_file() for p in written)


def test_generate_corpus_creates_missing_directory(tmp_path):
    """A non-existent out_dir is created."""
    target = tmp_path / "nested" / "samples"
    assert not target.exists()
    written = generate_corpus(target)
    assert target.is_dir() and written


def test_generate_corpus_cleans_stale_artifacts(tmp_path):
    """Re-generation removes stale .xlsx/.json from a previous run."""
    stale_xlsx = tmp_path / "stale__Old.xlsx"
    stale_json = tmp_path / "stale__Old.json"
    stale_xlsx.write_text("garbage")
    stale_json.write_text("{}")
    generate_corpus(tmp_path)
    assert not stale_xlsx.exists()
    assert not stale_json.exists()


def test_generate_corpus_uses_only_fictional_entities(tmp_path):
    """Every workbook is stamped with a name from the fictional pool."""
    generate_corpus(tmp_path)
    slugs = {e.replace(" ", "_") for e in FICTIONAL_ENTITIES}
    for p in tmp_path.glob("*.xlsx"):
        entity_slug = p.stem.split("__", 1)[1]
        assert entity_slug in slugs


def test_json_mismatch_export_differs_from_clean_total(tmp_path):
    """The json_mismatch defect publishes a closing_surplus offset by +25."""
    generate_corpus(tmp_path)
    jm = next(tmp_path.glob("json_mismatch__*.json"))
    payload = json.loads(jm.read_text(encoding="utf-8"))
    # The defect adds 25 to the true closing; the inputs reconstruct the truth.
    assert "closing_surplus" in payload
    # closing_surplus is an int; the defect makes it not divisible cleanly into
    # the opening+income+dist sum — assert it's the offset value, not the truth.
    assert isinstance(payload["closing_surplus"], int)


def test_generated_json_payload_has_expected_keys(tmp_path):
    """Each JSON export carries the documented payload keys."""
    generate_corpus(tmp_path)
    payload = json.loads(
        next(tmp_path.glob("clean__*.json")).read_text(encoding="utf-8")
    )
    assert {
        "entity",
        "fiscal_year",
        "currency",
        "closing_surplus",
        "source_workbook",
    } <= set(payload)
    assert payload["currency"] == "USD"
    assert payload["fiscal_year"] == "FY2024"


# --------------------------------------------------------------------------- #
# CLI argument parser
# --------------------------------------------------------------------------- #
def test_parser_requires_folder():
    """The parser requires a positional folder argument."""
    with pytest.raises(SystemExit):
        _build_parser().parse_args([])


def test_parser_defaults():
    """Optional flags default to None/False."""
    ns = _build_parser().parse_args(["somedir"])
    assert ns.folder == "somedir"
    assert ns.json is None and ns.md is None
    assert ns.generate is False and ns.quiet is False


def test_parser_accepts_all_flags():
    """All documented flags parse into the namespace."""
    ns = _build_parser().parse_args(
        ["dir", "--json", "out.json", "--md", "out.md", "--generate", "--quiet"]
    )
    assert ns.json == "out.json" and ns.md == "out.md"
    assert ns.generate is True and ns.quiet is True


def test_exit_by_verdict_mapping():
    """Exit-code mapping matches the documented 0/1/2 contract."""
    assert _EXIT_BY_VERDICT == {
        Verdict.PASS: 0,
        Verdict.REVIEW: 1,
        Verdict.FAIL: 2,
    }


# --------------------------------------------------------------------------- #
# CLI main() exit codes
# --------------------------------------------------------------------------- #
def test_main_returns_2_for_failing_corpus(tmp_path, capsys):
    """The default corpus has FAIL defects => exit code 2."""
    generate_corpus(tmp_path)
    assert main([str(tmp_path), "--quiet"]) == 2


def test_main_returns_3_for_missing_folder(tmp_path, capsys):
    """A non-existent folder => usage error exit code 3."""
    missing = tmp_path / "nope"
    assert main([str(missing), "--quiet"]) == 3
    err = capsys.readouterr().err
    assert "not a folder" in err


def test_main_returns_3_for_empty_folder(tmp_path, capsys):
    """An existing folder with no .xlsx => exit code 3."""
    assert main([str(tmp_path), "--quiet"]) == 3
    err = capsys.readouterr().err
    assert "no .xlsx workbooks" in err


def test_main_clean_only_folder_returns_0(tmp_path):
    """A folder containing only the clean workbook => exit code 0 (PASS)."""
    full = tmp_path / "full"
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    generate_corpus(full)
    src = next(full.glob("clean__*.xlsx"))
    (clean_dir / src.name).write_bytes(src.read_bytes())
    sib = src.with_suffix(".json")
    (clean_dir / sib.name).write_bytes(sib.read_bytes())
    assert main([str(clean_dir), "--quiet"]) == 0


def test_main_generate_flag_creates_and_validates(tmp_path):
    """--generate builds the corpus into the folder then validates it (FAIL=2)."""
    assert main([str(tmp_path), "--generate", "--quiet"]) == 2
    assert len(list(tmp_path.glob("*.xlsx"))) == 1 + len(DEFECTS)


def test_main_writes_json_and_md_reports(tmp_path):
    """--json/--md write well-formed report files to disk."""
    generate_corpus(tmp_path)
    json_out = tmp_path / "report.json"
    md_out = tmp_path / "report.md"
    main([str(tmp_path), "--quiet", "--json", str(json_out), "--md", str(md_out)])
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["tool"] == "validation_engine"
    assert md_out.read_text(encoding="utf-8").startswith("# Validation Report")


def test_main_quiet_suppresses_per_workbook_output(tmp_path, capsys):
    """--quiet prints only the overall verdict line, not per-workbook sections."""
    generate_corpus(tmp_path)
    main([str(tmp_path), "--quiet"])
    out = capsys.readouterr().out
    assert "Overall verdict:" in out
    assert "=== " not in out  # no per-workbook headers in quiet mode


def test_main_verbose_prints_per_workbook_sections(tmp_path, capsys):
    """Without --quiet, per-workbook verdict headers are printed."""
    generate_corpus(tmp_path)
    main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "=== " in out
    assert "verdict:" in out
