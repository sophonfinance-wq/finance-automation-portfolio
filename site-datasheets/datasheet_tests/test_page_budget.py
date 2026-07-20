"""Page engineering: size budget and that every local asset/link path exists."""
from __future__ import annotations

import generate_datasheets as gen
import datasheet_spec as ds

MAX_BYTES = 150 * 1024


def test_page_within_size_budget():
    size = len(gen.render("triangulate").encode("utf-8"))
    assert size <= MAX_BYTES, f"{size} bytes exceeds {MAX_BYTES}"


def test_media_assets_exist_on_disk():
    spec = ds.load_spec("triangulate")
    docs_engines = gen.OUT_DIR  # docs/engines
    for key in ("poster", "motion"):
        rel = spec["media"][key]  # e.g. ../assets/tile-triangulate.webp
        resolved = (docs_engines / rel).resolve()
        assert resolved.is_file(), f"missing media asset: {rel} -> {resolved}"


def test_internal_tests_link_route_exists():
    # links.tests points at /tests/ — the docs/tests/ directory must exist
    spec = ds.load_spec("triangulate")
    assert spec["links"]["tests"] == "/tests/"
    assert (gen.REPO / "docs" / "tests").is_dir()
