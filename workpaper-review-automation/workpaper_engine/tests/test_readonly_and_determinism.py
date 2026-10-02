"""The engine never writes, never reads the clock, and repeats byte for byte."""

from __future__ import annotations

import json
import os

from workpaper_engine.engine import analyze_document, analyze_folder
from workpaper_engine.generate import generate_corpus
from workpaper_engine.report import build_json_report, build_markdown_report


def _snapshot(folder):
    out = {}
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), "rb") as fh:
            out[name] = fh.read()
    return out


def test_analysis_does_not_touch_the_corpus(corpus):
    before = _snapshot(corpus)
    analyze_folder(corpus)
    assert _snapshot(corpus) == before


def test_analysis_does_not_mutate_its_input(clean_doc):
    before = json.dumps(clean_doc, sort_keys=True)
    analyze_document(clean_doc)
    assert json.dumps(clean_doc, sort_keys=True) == before


def test_repeated_analysis_is_identical(corpus):
    a = build_json_report(analyze_folder(corpus))
    b = build_json_report(analyze_folder(corpus))
    assert a == b
    assert build_markdown_report(analyze_folder(corpus)) == build_markdown_report(
        analyze_folder(corpus)
    )


def test_generation_is_seeded_and_byte_stable(tmp_path):
    one, two = tmp_path / "a", tmp_path / "b"
    assert generate_corpus(str(one)) == generate_corpus(str(two))
    assert _snapshot(str(one)) == _snapshot(str(two))


def test_no_wall_clock_in_the_engine_sources():
    """A control that reads the clock is not reproducible. Guard it structurally."""
    import workpaper_engine.engine as eng
    import workpaper_engine.model as mdl

    for mod in (eng, mdl):
        src = open(mod.__file__, "r", encoding="utf-8").read()
        assert "datetime.now" not in src
        assert "time.time" not in src
