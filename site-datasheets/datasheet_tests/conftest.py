"""Shared fixtures + package-wide marker for the datasheet test suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_collection_modifyitems(items):
    """Every datasheet test is site tooling, not an engine test."""
    for item in items:
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
