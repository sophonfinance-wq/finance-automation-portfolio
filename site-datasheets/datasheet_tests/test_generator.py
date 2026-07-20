"""Generator: determinism, committed-artifact freshness, CLI, well-formed doc."""
from __future__ import annotations

import subprocess
import sys

import pytest

import generate_datasheets as gen
from datasheet_tests.conftest import ROOT  # noqa: F401 (path bootstrap)


def test_render_is_deterministic_in_process():
    assert gen.render("triangulate") == gen.render("triangulate")


def test_two_runs_are_byte_identical(tmp_path):
    a = tmp_path / "a.html"
    b = tmp_path / "b.html"
    assert gen.main(["--slug", "triangulate", "--out", str(a)]) == 0
    assert gen.main(["--slug", "triangulate", "--out", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()


def test_document_is_well_formed():
    html = gen.render("triangulate")
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "SFS-E06-TRI" in html
    assert "Triangulate" in html


def test_committed_page_is_fresh():
    page = gen.OUT_DIR / "triangulate.html"
    assert page.read_bytes() == gen.render("triangulate").encode("utf-8"), (
        "docs/engines/triangulate.html is stale — regenerate it"
    )


def test_cli_exits_cleanly(tmp_path):
    target = tmp_path / "t.html"
    proc = subprocess.run(
        [sys.executable, "generate_datasheets.py",
         "--slug", "triangulate", "--out", str(target)],
        cwd=str(gen.ROOT), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert target.is_file()
