"""Shared fixtures for the tax workpaper build engine test suite.

The corpus is generated once per session into a temporary directory rather than
read from the committed ``samples/`` folder, so the tests prove the *builder*,
the *generator* and the *controls* agree. A test that read the committed corpus
would keep passing after a build change that no longer produces it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from workpaper_engine.build import (
    WorkpaperPackage,
    build_package,
    capture_prebuild_image,
)
from workpaper_engine.engine import analyze_document, analyze_folder
from workpaper_engine.generate import (
    PREBUILD_CAPTURED_AT,
    allocation_register,
    counterpart_stub,
    exception_register,
    generate_corpus,
    locked_source,
    prior_package,
)
from workpaper_engine.model import DocumentReport


@pytest.fixture(scope="session")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A freshly generated corpus in a temporary directory."""
    folder = tmp_path_factory.mktemp("workpaper_corpus")
    generate_corpus(folder)
    return folder


@pytest.fixture(scope="session")
def reports(corpus: Path) -> list[DocumentReport]:
    """Every build file in the corpus, analyzed once."""
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
    """The one build file with no planted defect."""
    return by_defect["clean"]


@pytest.fixture
def inputs() -> dict[str, Any]:
    """A fresh set of build inputs: the extract, the prior package, the registers."""
    prior = prior_package()
    image = capture_prebuild_image(
        prior, captured_at=PREBUILD_CAPTURED_AT, document_id="PRE-TEST"
    )
    return {
        "sources": locked_source(),
        "prior_year": prior,
        "registers": {
            "allocation": allocation_register(),
            "exception": exception_register(),
            "counterpart_stub": counterpart_stub(),
            "prebuild_image": image,
        },
    }


@pytest.fixture
def built(inputs: dict[str, Any]) -> WorkpaperPackage:
    """A package constructed from a fresh set of inputs."""
    return build_package(inputs["sources"], inputs["prior_year"], inputs["registers"])


def defect_names() -> list[str]:
    """Planted-defect names, sorted, for parametrization."""
    from workpaper_engine.generate import DEFECTS

    return sorted(DEFECTS)
