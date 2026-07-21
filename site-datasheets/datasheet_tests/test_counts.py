"""The published test-count on the page matches counts.json (no stale numbers)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import datasheet_spec as ds
import generate_datasheets as gen

COUNTS = gen.ROOT / "counts.json"


def _int(text: str) -> int:
    return int(re.sub(r"[^0-9]", "", text))


def _collected_count(cwd: Path, *extra: str) -> int:
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *extra],
        cwd=str(cwd), capture_output=True, text=True, timeout=120, env=env,
    )
    output = proc.stdout + "\n" + proc.stderr
    assert proc.returncode == 0, output[-4000:]
    match = re.search(r"(\d+)(?:/\d+)? tests? collected", output)
    assert match, output[-4000:]
    return int(match.group(1))


def test_counts_file_present_and_nonempty():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    assert data.get("triangulate", {}).get("tests"), "counts.json missing triangulate.tests"
    assert data.get("portfolio_curated", {}).get("tests"), (
        "counts.json missing portfolio_curated.tests"
    )
    assert data.get("site_tooling", {}).get("tests"), "counts.json missing site_tooling.tests"


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


def test_triangulate_count_matches_live_collection():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    actual = _collected_count(gen.REPO / "ai-validation-framework")
    assert actual == data["triangulate"]["tests"], (
        "Triangulate count drift: update evidence only after reviewing the live collection",
        actual,
        data["triangulate"]["tests"],
    )


def test_site_tooling_count_matches_live_collection():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    actual = _collected_count(gen.ROOT)
    assert actual == data["site_tooling"]["tests"], (
        "site-tooling count drift: refresh counts.json and docs/tests/index.html",
        actual,
        data["site_tooling"]["tests"],
    )
