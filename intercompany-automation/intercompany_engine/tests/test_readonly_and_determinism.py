"""The engine must be read-only, deterministic and byte-stable.

These three properties are what let the committed report be diffed and trusted.
If any of them fails the engine stops being a sensor and becomes a participant.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from intercompany_engine.engine import analyze_document, analyze_folder
from intercompany_engine.generate import generate_corpus
from intercompany_engine.report import build_json_report, build_markdown_report


def _digest(folder: Path) -> dict[str, str]:
    """SHA-256 of every file in the folder, keyed by name."""
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.glob("*.json"))
    }


def test_analysis_does_not_touch_the_source(corpus: Path) -> None:
    """Running the whole registry leaves every source byte identical."""
    before = _digest(corpus)
    analyze_folder(corpus)
    assert _digest(corpus) == before


def test_analysis_is_repeatable(corpus: Path) -> None:
    """Two runs over the same corpus produce identical findings."""
    first = [r.to_dict() for r in analyze_folder(corpus)]
    second = [r.to_dict() for r in analyze_folder(corpus)]
    assert first == second


def test_generator_is_deterministic(tmp_path: Path) -> None:
    """The generator takes no seed and writes byte-identical files every time."""
    a, b = tmp_path / "a", tmp_path / "b"
    generate_corpus(a)
    generate_corpus(b)
    assert _digest(a) == _digest(b)


def test_regenerating_in_place_is_a_no_op(tmp_path: Path) -> None:
    """Regenerating over an existing corpus changes nothing.

    This is what makes a diff meaningful: if regeneration churned bytes, every
    commit would show noise and a real change would hide in it.
    """
    folder = tmp_path / "corpus"
    generate_corpus(folder)
    before = _digest(folder)
    generate_corpus(folder)
    assert _digest(folder) == before


def test_folder_analysis_is_sorted(corpus: Path) -> None:
    """Files are analyzed in sorted order regardless of filesystem order."""
    names = [r.document for r in analyze_folder(corpus)]
    stems = [p.stem for p in sorted(corpus.glob("*.json"))]
    assert names == stems


def test_reports_are_byte_stable(corpus: Path) -> None:
    """The rendered reports do not carry timestamps, paths or unstable ordering."""
    reports = analyze_folder(corpus)
    md_a = build_markdown_report(reports)
    md_b = build_markdown_report(analyze_folder(corpus))
    assert md_a == md_b

    json_a = json.dumps(build_json_report(reports), sort_keys=True)
    json_b = json.dumps(build_json_report(analyze_folder(corpus)), sort_keys=True)
    assert json_a == json_b


def test_report_contains_no_absolute_paths(corpus: Path) -> None:
    """A report that embedded a build path would differ on every machine."""
    md = build_markdown_report(analyze_folder(corpus))
    assert str(corpus) not in md
    assert "C:\\" not in md
    assert "/home/" not in md


def test_bad_json_raises_value_error(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        analyze_document(p)


def test_non_object_json_raises_value_error(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        analyze_document(p)


def test_empty_package_does_not_crash(tmp_path: Path) -> None:
    """A period file with no documents fails loudly rather than passing vacuously."""
    p = tmp_path / "empty.json"
    p.write_text("{}", encoding="utf-8")
    report = analyze_document(p)
    assert "set_complete" in report.rules_fired()
