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
        "blocks": [{"id": "b", "label": "B", "source_link": "u",
                    "col": 0, "row": 0}],
        "edges": [{"from": "b", "to": "b"}],
        "spec_strip": [{"label": "L", "value": "1", "source": "s"}],
        "problem_statement": "p",
        "scenarios": [{"title": "T", "narrative": "n", "source": "s"}],
        "instruction_set": [{"cmd": "c", "operation": "o", "output": "x",
                             "exit_code": "0", "artifacts": "a"}],
        "benchmarks": [{"label": "L", "value": "1", "unit": "u", "source": "s"}],
        "control_characteristics": {"authority": [], "verdict_map": [],
                                    "guarantees": [], "determinism": {},
                                    "gate_policy": {}, "modes": []},
        "limits": [{"statement": "x", "source": "s"}],
        "media": {"poster": "p.webp", "motion": "m.mp4", "crops": []},
        "links": {"readme": "r", "source": "s", "tests": "t", "codespaces": "c"},
        "meta": {"description": "d"},
    }


def test_minimal_spec_is_valid():
    assert ds.validate_spec(_minimal_valid_spec()) == []


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
