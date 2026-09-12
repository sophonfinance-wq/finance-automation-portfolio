"""Each planted defect is caught, by the control that owns it."""

from __future__ import annotations

import json
import os
import random

import pytest

from workpaper_engine.engine import FAIL, FLAG, analyze_document
from workpaper_engine.generate import DEFECTS, SEED, _apply_defect, build_clean_package

EXPECTED = {
    "typed_current_year_input": "UNSOURCED_INPUT",
    "citation_off_by_a_dollar": "CITATION_MISMATCH",
    "citation_unresolvable": "CITATION_MISMATCH",
    "amount_reclassified_as_date": "DATE_MISREAD",
    "orphaned_dependant": "ORPHANED_DEPENDANT",
    "cover_note_count_mismatch": "QUESTION_COUNT_MISMATCH",
    "attachment_hash_drift": "ATTACHMENT_DRIFT",
    "residual_plugged": "RESIDUAL_PLUGGED",
    "presentation_stray_underline": "PRESENTATION_DRIFT",
    "evidence_overclaim": "EVIDENCE_OVERCLAIM",
}


@pytest.fixture()
def clean():
    return build_clean_package("WP-TEST", "Invented Holdings LLC", random.Random(SEED))


@pytest.mark.parametrize("defect", DEFECTS)
def test_defect_is_caught_by_its_control(defect, clean):
    doc = _apply_defect(clean, defect)
    result = analyze_document(doc)
    controls = {f["control"] for f in result["findings"]}
    assert EXPECTED[defect] in controls, (defect, result["findings"])
    assert result["verdict"] in (FAIL, FLAG)


def test_every_defect_class_has_an_expectation():
    assert set(DEFECTS) == set(EXPECTED)


def test_a_dollar_of_citation_drift_is_still_a_failure(clean):
    """The defect that survives longest is the one closest to correct."""
    doc = _apply_defect(clean, "citation_off_by_a_dollar")
    result = analyze_document(doc)
    hit = [f for f in result["findings"] if f["control"] == "CITATION_MISMATCH"]
    assert hit, result["findings"]
    assert hit[0]["severity"] == "FAIL"
    assert hit[0]["detail"]["difference_cents"] == -100
    assert hit[0]["detail"]["rounding_sized"] is True


def test_an_amount_in_the_date_band_is_protected_not_converted(clean):
    """A genuine amount inside the date-serial range is flagged, never silently converted."""
    clean["cells"][0]["value_cents"] = 46_166_00
    clean["citations"][0]["quoted_cents"] = 46_166_00
    clean["cells"][6]["value_cents"] = sum(c["value_cents"] for c in clean["cells"][:6])
    clean["citations"][1]["quoted_cents"] = clean["cells"][6]["value_cents"]
    result = analyze_document(clean)
    hits = [f for f in result["findings"] if f["control"] == "DATE_MISREAD"]
    assert hits and hits[0]["severity"] == FLAG
    assert hits[0]["detail"]["protected"] is True
