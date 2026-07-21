"""Spec schema: required fields present; every sourced row carries a source."""
from __future__ import annotations

import datasheet_spec as ds


def _minimal_valid_spec() -> dict:
    return {
        "num": 6, "slug": "triangulate", "part_no": "SFS-E06-TRI",
        "mnemonic": "TRI", "family": "AI Validation", "name": "Triangulate",
        "tagline": "t", "plain_summary": "s", "rev": "2026-07-20",
        "status": "PRODUCTION",
        "layers": [{"id": "a", "label": "A", "plain": "p",
                    "engineering": "e", "source_link": "u"}],
        "blocks": [{"id": "b", "label": "B", "plain": "p",
                    "engineering": "e", "source_link": "u",
                    "col": 0, "row": 0}],
        "edges": [{"from": "b", "to": "b"}],
        "spec_strip": [{"label": "L", "value": "1", "source": "s"}],
        "problem_statement": "p",
        "scenarios": [{"title": "T", "narrative": "n", "source": "s"}],
        "instruction_set": [{"cmd": "c", "operation": "o", "output": "x",
                             "exit_code": "0", "artifacts": "a"}],
        "benchmarks": [{"label": "L", "value": "1", "unit": "u", "source": "s"}],
        "control_characteristics": {
            "authority": [{"rank": 1, "level": "L", "note": "n"}],
            "verdict_map": [{"severity": "None", "verdict": "PASS",
                             "action": "review"}],
            "guarantees": ["g"],
            "determinism": {"seeded": True, "read_only": True,
                            "offline_default": True},
            "gate_policy": {"human_approval_required": True,
                            "demo_gate": "automated-policy", "note": "n"},
            "modes": [{"name": "offline", "detail": "d"}],
        },
        "limits": [{"statement": "x", "source": "s"}],
        "media": {"poster": "p.webp", "motion": "m.mp4", "crops": []},
        "links": {"readme": "r", "source": "s", "tests": "t", "codespaces": "c"},
        "meta": {"description": "d"},
    }


def test_minimal_spec_is_valid():
    assert ds.validate_spec(_minimal_valid_spec()) == []


def test_checked_in_spec_is_valid():
    assert ds.validate_spec(ds.load_spec("triangulate")) == []


def test_missing_required_field_is_reported():
    spec = _minimal_valid_spec()
    del spec["part_no"]
    problems = ds.validate_spec(spec)
    assert any("part_no" in p for p in problems)


def test_sourced_row_without_source_is_reported():
    spec = _minimal_valid_spec()
    spec["benchmarks"][0]["source"] = ""
    problems = ds.validate_spec(spec)
    assert any("benchmarks" in p and "source" in p for p in problems)


def test_invalid_calendar_date_is_reported():
    spec = _minimal_valid_spec()
    spec["rev"] = "2026-02-30"
    assert any("calendar date" in p for p in ds.validate_spec(spec))


def test_unknown_schematic_endpoint_is_reported():
    spec = _minimal_valid_spec()
    spec["edges"][0]["to"] = "missing"
    assert any("unknown block" in p for p in ds.validate_spec(spec))


def test_negative_block_coordinate_is_reported():
    spec = _minimal_valid_spec()
    spec["blocks"][0]["col"] = -1
    assert any("non-negative" in p for p in ds.validate_spec(spec))


def test_crop_requires_path_label_and_alt():
    spec = _minimal_valid_spec()
    spec["media"]["crops"] = [{"path": "crop.webp", "label": "Verdict"}]
    assert any("media.crops[0] missing alt" in p for p in ds.validate_spec(spec))

    spec = _minimal_valid_spec()
    spec["control_characteristics"]["gate_policy"] = {}
    problems = ds.validate_spec(spec)
    assert any("human_approval_required" in p for p in problems)
    assert any("demo_gate" in p for p in problems)

    spec = _minimal_valid_spec()
    spec["control_characteristics"]["authority"][0]["rank"] = 2
    assert any("ranks must be sequential" in p for p in ds.validate_spec(spec))
