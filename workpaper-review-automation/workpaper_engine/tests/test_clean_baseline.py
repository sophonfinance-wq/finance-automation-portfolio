"""The clean package passes every control."""

from __future__ import annotations

from workpaper_engine.engine import PASS, REGISTRY, analyze_document
from workpaper_engine.model import parse_package


def test_clean_package_passes(clean_doc):
    result = analyze_document(clean_doc)
    assert result["verdict"] == PASS, result["findings"]
    assert result["findings"] == []


def test_every_control_returns_nothing_on_a_clean_package(clean_doc):
    pkg = parse_package(clean_doc)
    for name, control in REGISTRY.items():
        assert control(pkg) == [], "%s fired on the clean package" % name


def test_registry_is_complete_and_sorted_stable():
    assert set(REGISTRY) == {
        "UNSOURCED_INPUT",
        "CITATION_MISMATCH",
        "DATE_MISREAD",
        "ORPHANED_DEPENDANT",
        "QUESTION_COUNT_MISMATCH",
        "ATTACHMENT_DRIFT",
        "RESIDUAL_PLUGGED",
        "PRESENTATION_DRIFT",
        "EVIDENCE_OVERCLAIM",
    }
