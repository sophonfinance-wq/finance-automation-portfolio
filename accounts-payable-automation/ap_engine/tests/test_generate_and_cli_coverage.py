"""Generator behaviour and every CLI branch, including all four exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ap_engine.cli import _build_parser, main
from ap_engine.generate import (
    DEFECTS,
    SEED,
    Defect,
    apply_defect,
    build_document_set,
    generate_corpus,
)
from ap_engine.model import DOC_COMMITMENT_REGISTER, DOC_TYPES


# --------------------------------------------------------------------------- #
# Generator
# --------------------------------------------------------------------------- #
def test_corpus_is_one_clean_set_plus_one_per_defect(tmp_path: Path) -> None:
    written = generate_corpus(tmp_path)
    assert len(written) == len(DEFECTS) + 1
    assert all(p.suffix == ".json" for p in written)
    stems = sorted(p.stem.split("__", 1)[0] for p in written)
    assert stems == sorted(["clean", *[d.key for d in DEFECTS]])


def test_every_generated_set_carries_all_document_types(tmp_path: Path) -> None:
    """Every set is complete except the one whose planted defect *is* incompleteness.

    That fixture is asserted incomplete rather than skipped, so it cannot quietly
    become complete and leave ``set_complete`` with nothing to catch.
    """
    for path in generate_corpus(tmp_path):
        data = json.loads(path.read_text(encoding="utf-8"))
        present = [d["doc_type"] for d in data["documents"]]
        if path.stem.startswith("set_incomplete__"):
            assert DOC_COMMITMENT_REGISTER not in present
            assert present != list(DOC_TYPES)
        else:
            assert present == list(DOC_TYPES)
        assert data["period"] == "2026-07"
        assert data["currency"] == "USD"


def test_generate_wipes_stale_artifacts_but_spares_lock_files(tmp_path: Path) -> None:
    stale_json = tmp_path / "old_schema.json"
    stale_xlsx = tmp_path / "old_schema.xlsx"
    lock = tmp_path / "~$locked.xlsx"
    other = tmp_path / "notes.txt"
    for path in (stale_json, stale_xlsx, lock, other):
        path.write_text("stale", encoding="utf-8")

    generate_corpus(tmp_path)

    assert not stale_json.exists()
    assert not stale_xlsx.exists()
    assert lock.exists(), "lock files must be left alone"
    assert other.exists(), "unrelated files must be left alone"


def test_generate_is_seed_sensitive(tmp_path: Path) -> None:
    """A different seed must produce a different corpus, or the seed is a lie."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate_corpus(a, seed=SEED)
    generate_corpus(b, seed=SEED + 1)
    texts_a = [p.read_text(encoding="utf-8") for p in sorted(a.glob("*.json"))]
    texts_b = [p.read_text(encoding="utf-8") for p in sorted(b.glob("*.json"))]
    assert len(texts_a) == len(texts_b)
    assert texts_a != texts_b


def test_generate_writes_a_workbook_alongside_each_set(tmp_path: Path) -> None:
    """The xlsx rendering is a convenience; it is written when openpyxl exists."""
    pytest.importorskip("openpyxl")
    written = generate_corpus(tmp_path)
    for path in written:
        assert path.with_suffix(".xlsx").exists()


def test_apply_defect_rejects_an_unregistered_key() -> None:
    import random

    packet = build_document_set("Demo Holdings LLC", 1, random.Random(SEED))
    with pytest.raises(ValueError, match="no applier registered"):
        apply_defect(packet, Defect("not_a_key", "not_a_rule", "unregistered defect"))


def test_generated_identifiers_use_the_fictional_conventions(tmp_path: Path) -> None:
    data = json.loads(
        sorted(generate_corpus(tmp_path))[0].read_text(encoding="utf-8")
    )
    assert data["document_set_id"].startswith("APDS-2026-")
    assert data["part_no"] == "SFS-E10-APX"
    selection = next(d for d in data["documents"] if d["doc_type"] == DOC_TYPES[1])
    for payment in selection["payments"]:
        assert payment["document_number"].startswith("INV-2026-")
        assert payment["purchase_order"].startswith("PO-2026-")
        assert payment["ledger_code"] == "AP-3000"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_parser_exposes_the_documented_options() -> None:
    args = _build_parser().parse_args(["folder", "--json", "j", "--md", "m", "--quiet"])
    assert args.folder == "folder"
    assert args.json == "j"
    assert args.md == "m"
    assert args.quiet is True
    assert args.generate is False


def test_cli_returns_two_when_the_corpus_contains_failures(corpus_dir, capsys) -> None:
    code = main([str(corpus_dir)])
    out = capsys.readouterr().out
    assert code == 2
    assert "Overall verdict: FAIL" in out
    assert "[FAIL]" in out
    assert "[FLAG]" in out


def test_cli_returns_zero_on_a_clean_only_folder(corpus_dir, tmp_path, capsys) -> None:
    clean = sorted(corpus_dir.glob("clean__*.json"))[0]
    target = tmp_path / "clean_only"
    target.mkdir()
    (target / clean.name).write_text(clean.read_text(encoding="utf-8"), encoding="utf-8")

    code = main([str(target)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Overall verdict: PASS" in out
    assert "all controls held" in out


def test_cli_returns_one_on_a_review_only_folder(corpus_dir, tmp_path, capsys) -> None:
    """A FLAG-only corpus is REVIEW, exit code 1."""
    source = sorted(corpus_dir.glob("header_date_drift__*.json"))[0]
    target = tmp_path / "review_only"
    target.mkdir()
    (target / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    code = main([str(target)])
    assert code == 1
    assert "Overall verdict: REVIEW" in capsys.readouterr().out


def test_cli_returns_three_for_a_missing_folder(tmp_path, capsys) -> None:
    code = main([str(tmp_path / "nope")])
    assert code == 3
    assert "not a folder" in capsys.readouterr().err


def test_cli_returns_three_for_an_empty_folder(tmp_path, capsys) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    code = main([str(empty)])
    assert code == 3
    assert "no .json document sets" in capsys.readouterr().err


def test_cli_returns_three_for_unreadable_json(tmp_path, capsys) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "bad.json").write_text("{ not json", encoding="utf-8")
    code = main([str(broken)])
    assert code == 3
    assert "could not read document sets" in capsys.readouterr().err


def test_cli_generate_then_analyze_and_write_artifacts(tmp_path, capsys) -> None:
    samples = tmp_path / "samples"
    json_path = tmp_path / "ap_report.json"
    md_path = tmp_path / "ap_report.md"

    code = main(
        [str(samples), "--generate", "--json", str(json_path), "--md", str(md_path)]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert f"Generated {len(DEFECTS) + 1} fictional document set(s)" in out
    assert "Wrote JSON report ->" in out
    assert "Wrote markdown report ->" in out
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["document_count"] == len(DEFECTS) + 1
    assert md_path.read_text(encoding="utf-8").startswith("# Accounts Payable Control Report")


def test_cli_quiet_prints_only_the_verdict(corpus_dir, capsys) -> None:
    code = main([str(corpus_dir), "--quiet"])
    out = capsys.readouterr().out.strip().split("\n")
    assert code == 2
    assert len(out) == 1
    assert out[0].startswith("Overall verdict: FAIL")


def test_module_entrypoint_is_importable() -> None:
    """``python -m ap_engine`` resolves to the same main()."""
    import ap_engine.__main__ as entry

    assert entry.main is main
