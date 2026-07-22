"""The Triangulate spec loads, validates, and matches the §4 roster identity."""
from __future__ import annotations

import html
import re

import datasheet_spec as ds
import generate_datasheets as gen

from datasheet_tests.conftest import ROSTER, present_slugs


def test_triangulate_spec_is_valid():
    spec = ds.load_spec("triangulate")
    assert ds.validate_spec(spec) == []


def test_every_present_spec_validates_and_matches_roster():
    # As each engine's spec lands, it must validate and its identity (num / part_no /
    # mnemonic / family / name) must match the one canonical §4 roster — so a wrong part
    # number or a stale engine name fails here, not on the live page.
    for slug in present_slugs():
        assert slug in ROSTER, f"{slug!r} is not in the canonical roster"
        spec = ds.load_spec(slug)
        assert ds.validate_spec(spec) == [], (slug, ds.validate_spec(spec))
        r = ROSTER[slug]
        for key in ("num", "part_no", "mnemonic", "family", "name"):
            assert spec[key] == r[key], (slug, key, spec.get(key), r[key])
        assert spec["slug"] == slug


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


BRAND_VOICE = gen.REPO / "docs" / "BRAND-VOICE.md"


def _published_h1_names() -> list[str]:
    names = []
    for page in sorted(gen.OUT_DIR.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        match = re.search(r"<h1><strong>(.*?)</strong></h1>", text)
        assert match, f"missing canonical H1 in {page}"
        names.append(html.unescape(match.group(1)))
    return names


def test_brand_voice_lists_all_ten_engine_names():
    text = BRAND_VOICE.read_text(encoding="utf-8")
    names = _published_h1_names()
    assert len(names) == 10
    assert len(set(names)) == 10
    for name in names:
        assert name in text, f"BRAND-VOICE.md missing canonical name: {name}"


def test_page_h1_is_in_brand_voice_roster():
    html = gen.render("triangulate")
    # H1 strong text is the canonical name
    assert "<h1><strong>Triangulate</strong></h1>" in html
    text = BRAND_VOICE.read_text(encoding="utf-8")
    assert "Triangulate" in text
