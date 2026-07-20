"""Shared fixtures + package-wide marker for the datasheet test suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    """Every datasheet test is site tooling, not an engine test.

    NOTE: this hook receives the WHOLE session's items (pytest calls it once,
    with everything collected — not just this directory), so the marker must
    be scoped by path or a repo-root run would mark all engine tests too.
    """
    for item in items:
        try:
            item_path = Path(str(item.fspath)).resolve()
        except OSError:
            continue
        if item_path.is_relative_to(HERE):
            item.add_marker("site_tooling")


import pytest  # noqa: E402
import datasheet_spec as ds  # noqa: E402
import generate_datasheets as gen  # noqa: E402


@pytest.fixture(scope="session")
def spec() -> dict:
    return ds.load_spec("triangulate")


@pytest.fixture(scope="session")
def rendered() -> str:
    return gen.render("triangulate")
