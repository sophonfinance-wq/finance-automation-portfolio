"""Generator: determinism, committed-artifact freshness, CLI, well-formed doc."""
from __future__ import annotations

import subprocess
import sys

import generate_datasheets as gen

from datasheet_tests.conftest import ROOT, present_slugs  # noqa: F401 (path bootstrap)


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
    assert 'id="fnref-1" href="#fn-1"' in html
    assert 'id="fn-1"' in html
    assert "automated-policy" in html
    assert "triangulate-cli-verdict.webp" in html
    assert "triangulate-cli-fix-packet.webp" in html


def test_committed_pages_are_fresh():
    # Every engine that has a spec must have a committed page byte-identical to a fresh
    # render — the drift guard that keeps generated HTML honest as new engines land.
    for slug in present_slugs():
        page = gen.OUT_DIR / f"{slug}.html"
        assert page.is_file(), f"docs/engines/{slug}.html missing — generate it"
        assert page.read_bytes() == gen.render(slug).encode("utf-8"), (
            f"docs/engines/{slug}.html is stale — regenerate it"
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
