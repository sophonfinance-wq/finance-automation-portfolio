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

from datasheet_tests.conftest import ROSTER, present_slugs

COUNTS = gen.ROOT / "counts.json"


def _int(text: str) -> int:
    return int(re.sub(r"[^0-9]", "", text))


def _collected_count(cwd: Path, *extra: str) -> int:
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # `-o addopts=` neutralizes each engine's own pyproject/ini addopts (several set
    # "-q", which combined with our -q becomes -qq and suppresses the "N tests collected"
    # summary in favor of per-file lines). Forcing empty addopts gives one stable format
    # across all nine engines.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", *extra],
        cwd=str(cwd), capture_output=True, text=True, timeout=180, env=env,
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


def test_spec_test_counts_match_counts_file():
    # Every engine's cited "Tests" figure (spec strip) must equal counts.json[slug].tests,
    # so no page can quote a number that isn't pinned.
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    for slug in present_slugs():
        assert data.get(slug, {}).get("tests"), f"counts.json missing {slug}.tests"
        expected = data[slug]["tests"]
        spec = ds.load_spec(slug)
        strip_counts = [_int(i["value"]) for i in spec["spec_strip"]
                        if i["label"].lower() == "tests"]
        assert expected in strip_counts, (slug, expected, strip_counts)


def test_engine_counts_match_live_collection():
    # The pinned count for each engine must equal what its own suite actually collects —
    # the "no invented numbers" guarantee, re-derived from source on every CI run.
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    for slug in present_slugs():
        engine_dir = ROSTER[slug]["engine_dir"]
        actual = _collected_count(gen.REPO / engine_dir)
        assert actual == data[slug]["tests"], (
            f"{slug} count drift: refresh counts.json only after reviewing the live collection",
            actual,
            data[slug]["tests"],
        )


def test_site_tooling_count_matches_live_collection():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    actual = _collected_count(gen.ROOT)
    assert actual == data["site_tooling"]["tests"], (
        "site-tooling count drift: refresh counts.json and docs/tests/index.html",
        actual,
        data["site_tooling"]["tests"],
    )
