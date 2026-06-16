"""Shared pytest fixtures: a generated fictional corpus in a temp folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from validation_engine.engine import WorkbookReport, validate_folder
from validation_engine.generate import generate_corpus


@pytest.fixture(scope="session")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the fictional corpus once into a session-scoped temp folder."""
    out = tmp_path_factory.mktemp("samples")
    generate_corpus(out)
    return out


@pytest.fixture(scope="session")
def reports(corpus_dir: Path) -> dict[str, WorkbookReport]:
    """Validate the corpus and index reports by the defect key in the filename."""
    out: dict[str, WorkbookReport] = {}
    for rep in validate_folder(corpus_dir):
        key = rep.workbook.split("__", 1)[0]  # e.g. "hardcoded_total"
        out[key] = rep
    return out
