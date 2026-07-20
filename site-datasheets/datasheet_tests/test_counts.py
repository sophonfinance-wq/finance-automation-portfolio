"""The published test-count on the page matches counts.json (no stale numbers)."""
from __future__ import annotations

import json
import re

import generate_datasheets as gen
import datasheet_spec as ds

COUNTS = gen.ROOT / "counts.json"


def _int(text: str) -> int:
    return int(re.sub(r"[^0-9]", "", text))


def test_counts_file_present_and_nonempty():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    assert data.get("triangulate", {}).get("tests"), "counts.json missing triangulate.tests"


def test_spec_test_count_matches_counts_file():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    expected = data["triangulate"]["tests"]
    spec = ds.load_spec("triangulate")
    strip_counts = [_int(i["value"]) for i in spec["spec_strip"]
                    if i["label"].lower() == "tests"]
    bench_counts = [_int(b["value"]) for b in spec["benchmarks"]
                    if "test" in b["label"].lower()]
    assert expected in strip_counts, (expected, strip_counts)
    assert expected in bench_counts, (expected, bench_counts)
