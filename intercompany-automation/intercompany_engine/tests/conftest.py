"""Shared fixtures for the intercompany engine test suite.

The corpus is generated once per session into a temporary directory rather than
read from the committed ``samples/`` folder, so the tests prove the *generator*
and the *engine* agree. A test that read the committed corpus would keep passing
after a generator change that no longer produces it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from intercompany_engine.engine import analyze_document, analyze_folder
from intercompany_engine.generate import DEFECTS, generate_corpus
from intercompany_engine.model import DocumentReport


@pytest.fixture(scope="session")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A freshly generated corpus in a temporary directory."""
    folder = tmp_path_factory.mktemp("intercompany_corpus")
    generate_corpus(folder)
    return folder


@pytest.fixture(scope="session")
def reports(corpus: Path) -> list[DocumentReport]:
    """Every period file in the corpus, analyzed once."""
    return analyze_folder(corpus)


@pytest.fixture(scope="session")
def by_defect(corpus: Path) -> dict[str, DocumentReport]:
    """Map planted-defect name -> its analyzed report."""
    out: dict[str, DocumentReport] = {}
    for path in sorted(corpus.glob("*.json")):
        out[path.stem.split("__")[0]] = analyze_document(path)
    return out


@pytest.fixture(scope="session")
def clean_report(by_defect: dict[str, DocumentReport]) -> DocumentReport:
    """The one period file with no planted defect."""
    return by_defect["clean"]


def defect_names() -> list[str]:
    """Planted-defect names, sorted, for parametrization."""
    return sorted(DEFECTS)
