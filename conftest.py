"""Repository-wide pytest metadata that does not alter test discovery."""
from __future__ import annotations


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "site_tooling: datasheet-generator tooling excluded from engine headline counts",
    )
