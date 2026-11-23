"""Shared fixtures: one generated fictional corpus in a session temp folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from ap_engine.engine import analyze_folder
from ap_engine.generate import generate_corpus
from ap_engine.model import DocumentReport


@pytest.fixture(scope="session")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the fictional corpus once into a session-scoped temp folder."""
    out = tmp_path_factory.mktemp("samples")
    generate_corpus(out)
    return out


@pytest.fixture(scope="session")
def reports(corpus_dir: Path) -> dict[str, DocumentReport]:
    """Analyze the corpus and index reports by the defect key in the filename."""
    out: dict[str, DocumentReport] = {}
    for report in analyze_folder(corpus_dir):
        key = report.document.split("__", 1)[0]  # e.g. "waiver_gap"
        out[key] = report
    return out


@pytest.fixture(scope="session")
def clean_report(reports: dict[str, DocumentReport]) -> DocumentReport:
    """The report for the single clean baseline document set."""
    return reports["clean"]


# --- Optional exhaustive property/invariant sweep --------------------------
# `test_bulk_invariant_grid.py` generates a very large parametrized sweep
# (hundreds of thousands of cases). It is excluded from the default suite for
# speed and runs on demand:  SWEEP=1 pytest
def pytest_ignore_collect(collection_path, config):
    import os
    if os.environ.get("SWEEP") != "1" and collection_path.name == "test_bulk_invariant_grid.py":
        return True
