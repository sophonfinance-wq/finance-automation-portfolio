"""The Triangulate spec loads, validates, and matches the §4 roster identity."""
from __future__ import annotations

import datasheet_spec as ds


def test_triangulate_spec_is_valid():
    spec = ds.load_spec("triangulate")
    assert ds.validate_spec(spec) == []


def test_triangulate_roster_identity():
    spec = ds.load_spec("triangulate")
    assert spec["num"] == 6
    assert spec["slug"] == "triangulate"
    assert spec["part_no"] == "SFS-E06-TRI"
    assert spec["mnemonic"] == "TRI"
    assert spec["family"] == "AI Validation"
    assert spec["name"] == "Triangulate"


def test_triangulate_has_all_five_die_layers():
    # README roster: Preparer, Specialist, Reviewer, Deterministic Auditor, Human Gate
    spec = ds.load_spec("triangulate")
    labels = {layer["label"] for layer in spec["layers"]}
    for expected in ("Preparer", "Specialist", "Reviewer",
                     "Deterministic Auditor", "Human Gate"):
        assert expected in labels, expected


import generate_datasheets as gen  # noqa: E402

BRAND_VOICE = gen.REPO / "docs" / "BRAND-VOICE.md"

NINE_NAMES = (
    "Month-End Close", "Cash & Debt Reconciliation", "Partnership 1065 Automation",
    "Validation Engine", "Tax Surplus / ACB", "Triangulate", "Knowledge Brain",
    "Finance Operations Atlas", "Cash Management",
)


def test_brand_voice_lists_all_nine_engine_names():
    text = BRAND_VOICE.read_text(encoding="utf-8")
    for name in NINE_NAMES:
        assert name in text, f"BRAND-VOICE.md missing canonical name: {name}"


def test_page_h1_is_in_brand_voice_roster():
    html = gen.render("triangulate")
    # H1 strong text is the canonical name
    assert "<h1><strong>Triangulate</strong></h1>" in html
    text = BRAND_VOICE.read_text(encoding="utf-8")
    assert "Triangulate" in text
