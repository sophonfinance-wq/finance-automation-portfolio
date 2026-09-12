"""What each control means, at its edges."""

from __future__ import annotations

import pytest

from workpaper_engine.engine import (
    FAIL,
    FLAG,
    PASS,
    control_citation_mismatch,
    control_date_misread,
    control_question_count,
    control_unsourced_input,
    verdict_for,
    Finding,
)
from workpaper_engine.model import ModelError, parse_package


def test_prior_year_typed_content_is_not_a_finding(clean_doc):
    """Only current-year inputs must be sourced; inherited content is exempt."""
    pkg = parse_package(clean_doc)
    typed_prior = [c for c in pkg.cells if c.origin == "typed" and not c.is_current_year]
    assert typed_prior, "fixture should carry inherited typed content"
    assert control_unsourced_input(pkg) == []


def test_question_count_reads_the_block_not_the_note(clean_doc):
    clean_doc["questions"].append({"cell": "C17", "kind": "confirm", "summary": "another"})
    pkg = parse_package(clean_doc)
    hits = control_question_count(pkg)
    assert len(hits) == 1
    assert hits[0].detail["block_confirmations"] == 3
    assert hits[0].detail["stated_confirmations"] == 2


def test_sourced_origin_requires_a_source_ref(clean_doc):
    clean_doc["cells"][0].pop("source_ref")
    with pytest.raises(ModelError):
        parse_package(clean_doc)


def test_date_band_boundaries_are_inclusive(clean_doc):
    for whole, expect_flag in ((44_999, False), (45_000, True), (47_500, True), (47_501, False)):
        doc = dict(clean_doc)
        doc["cells"] = [dict(c) for c in clean_doc["cells"]]
        doc["cells"][0]["value_cents"] = whole * 100
        doc["cells"][0]["display_kind"] = "amount"
        pkg = parse_package(doc)
        fired = [f for f in control_date_misread(pkg) if f.address == pkg.cells[0].address]
        assert bool(fired) is expect_flag, whole


def test_a_value_with_cents_is_never_a_date_candidate(clean_doc):
    doc = dict(clean_doc)
    doc["cells"] = [dict(c) for c in clean_doc["cells"]]
    doc["cells"][0]["value_cents"] = 46_166_37
    doc["cells"][0]["display_kind"] = "amount"
    pkg = parse_package(doc)
    assert [f for f in control_date_misread(pkg) if f.address == pkg.cells[0].address] == []


def test_verdict_is_the_worst_severity_present():
    assert verdict_for([]) == PASS
    flag = Finding("X", FLAG, "a", "m", {})
    fail = Finding("Y", FAIL, "b", "m", {})
    assert verdict_for([flag]) == FLAG
    assert verdict_for([flag, fail]) == FAIL
    assert verdict_for([fail, flag]) == FAIL
