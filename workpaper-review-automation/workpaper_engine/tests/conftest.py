"""Shared fixtures: a seeded clean package and a corpus folder."""

from __future__ import annotations

import random

import pytest

from workpaper_engine.generate import SEED, build_clean_package, generate_corpus


@pytest.fixture()
def clean_doc() -> dict:
    return build_clean_package("WP-TEST", "Invented Holdings LLC", random.Random(SEED))


@pytest.fixture()
def corpus(tmp_path):
    folder = tmp_path / "corpus"
    generate_corpus(str(folder))
    return str(folder)
