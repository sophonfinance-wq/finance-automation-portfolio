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
