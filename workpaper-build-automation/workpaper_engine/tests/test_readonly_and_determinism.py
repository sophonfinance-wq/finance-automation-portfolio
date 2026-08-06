"""The builder must be pure and the controls read-only, deterministic and stable.

These properties are what let the committed corpus and report be diffed and
trusted. If the build is not a pure function of its inputs, two people rolling
the same year get two packages; if a control writes, the engine stops being a
sensor and becomes a participant.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from workpaper_engine.build import build_package, digest_payload
from workpaper_engine.engine import analyze_document, analyze_folder
from workpaper_engine.generate import generate_corpus
from workpaper_engine.report import build_json_report, build_markdown_report


def _digest(folder: Path) -> dict[str, str]:
    """SHA-256 of every file in the folder, keyed by name."""
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.glob("*.json"))
    }


def test_build_is_a_pure_function_of_its_inputs(inputs: dict[str, Any]) -> None:
    """The same inputs produce the same package, byte for byte."""
    first = build_package(inputs["sources"], inputs["prior_year"], inputs["registers"])
    second = build_package(inputs["sources"], inputs["prior_year"], inputs["registers"])
    assert digest_payload(first.to_dict()) == digest_payload(second.to_dict())


def test_build_does_not_mutate_its_inputs(inputs: dict[str, Any]) -> None:
    """The extract, the prior package and the registers come back untouched.

    A build that edited the prior-year package would corrupt the very thing the
    next roll freezes, and nothing downstream would ever notice: the frozen
    layers would agree with the file they were copied from because the file was
    changed to agree with them.
    """
    before = copy.deepcopy(inputs)
    build_package(inputs["sources"], inputs["prior_year"], inputs["registers"])
    assert inputs == before


def test_built_package_does_not_alias_the_prior_package(inputs: dict[str, Any]) -> None:
    """Frozen layers are copies, not references into the prior package."""
    package = build_package(
        inputs["sources"], inputs["prior_year"], inputs["registers"]
    )
    package.equity["rows"][0]["amount_cents"] = 1
    assert inputs["prior_year"]["equity"]["rows"][0]["amount_cents"] != 1


def test_analysis_does_not_touch_the_source(corpus: Path) -> None:
    """Running the whole registry leaves every build file byte identical."""
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


def test_analysis_does_not_mutate_the_parsed_payload(corpus: Path) -> None:
    """The context is a view, not a copy, so a control that wrote would show here.

    Read-only over the file on disk is not enough on its own: a control that
    edited the parsed payload in memory would leave the bytes alone and still
    corrupt every control that ran after it.
    """
    path = next(p for p in sorted(corpus.glob("*.json")) if p.stem.startswith("clean"))
    raw_before = json.loads(path.read_text(encoding="utf-8"))
    first = [f.to_dict() for f in analyze_document(path).findings]
    second = [f.to_dict() for f in analyze_document(path).findings]
    assert first == second
    assert json.loads(path.read_text(encoding="utf-8")) == raw_before


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


def test_empty_file_produces_no_pass_at_all(tmp_path: Path) -> None:
    """A file with no artifacts fails loudly rather than passing vacuously.

    This is the property that makes the whole registry trustworthy: a control
    whose evidence is absent reports FAIL, because a PASS on an artifact that is
    not there is worse than no report at all. Every one of the twenty-four has to
    say so.
    """
    p = tmp_path / "empty.json"
    p.write_text("{}", encoding="utf-8")
    report = analyze_document(p)
    from workpaper_engine.engine import REGISTRY
    from workpaper_engine.model import Status, Verdict

    assert report.verdict is Verdict.FAIL
    assert not [f for f in report.findings if f.status is Status.PASS]
    assert {f.rule for f in report.findings} == {r for r, _fn in REGISTRY}
