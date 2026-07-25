"""Every SVG tile footer must agree with counts.json and with its own alt text.

This guard exists because nothing used to check it. Twenty-four published tiles
carried a test figure exactly 10,000 short -- authored before each engine gained its
10,000-case invariant grid and never refreshed -- and eleven `poster_alt` strings
described a footer layout their image had never rendered. Both drifted silently
across many engine cycles because the datasheet suite validated the spec and the
page but never the artwork the spec points at.

Scope note: this can only cover vector tiles. The four raster `.webp` diagrams
(draw, upgrade, warranty, intercompany) carry the same figure in pixels and cannot
be parsed, so they need a line in the release checklist instead.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import generate_datasheets as gen

from datasheet_tests.conftest import ROSTER, present_slugs

COUNTS = json.loads((gen.ROOT / "counts.json").read_text(encoding="utf-8"))

#: The footer strip is the trailing run of <text> cells: controls, families, tests,
#: then a tagline/read-only cell and a wordmark/part-number cell.
_TEXT = re.compile(r"<text[^>]*>([^<]*)</text>")


def _footer_cells(svg: Path) -> list[str]:
    return [c.strip() for c in _TEXT.findall(svg.read_text(encoding="utf-8"))][-5:]


def _svg_poster(slug: str) -> Path | None:
    import datasheet_spec as ds

    poster = (ds.load_spec(slug).get("media") or {}).get("poster") or ""
    if not poster.endswith(".svg"):
        return None
    return (gen.OUT_DIR / poster).resolve()


def test_every_svg_tile_footer_cites_its_counts_json_figure() -> None:
    """The rendered test figure is the pinned one, to the comma.

    This is the assertion that was missing. A tile whose engine gained tests keeps
    rendering the old figure forever unless something compares the two.
    """
    problems: list[str] = []
    checked = 0
    for slug in present_slugs():
        svg = _svg_poster(slug)
        if svg is None:
            continue
        assert svg.exists(), f"{slug}: declared poster {svg} is missing"
        cells = _footer_cells(svg)
        cited = [c for c in cells if c.endswith("tests")]
        if not cited:
            problems.append(f"{slug}: no 'N tests' cell in the footer strip")
            continue
        want = f"{COUNTS[slug]['tests']:,} tests"
        checked += 1
        if want not in cited:
            problems.append(f"{slug}: footer renders {cited} but counts.json says {want}")
    assert not problems, "tile footers out of date:\n  " + "\n  ".join(problems)
    assert checked >= 30, f"only {checked} svg tiles checked; the sweep is not covering them"


def test_every_svg_tile_footer_is_described_by_its_alt_text() -> None:
    """The alt text describes the footer the image actually renders.

    A screen-reader user gets the alt and nothing else, so an alt that narrates a
    layout the artwork never had is simply wrong. Checks the three figure cells,
    which are the parts a reader would act on.
    """
    problems: list[str] = []
    import datasheet_spec as ds

    for slug in present_slugs():
        svg = _svg_poster(slug)
        if svg is None:
            continue
        alt = (ds.load_spec(slug).get("media") or {}).get("poster_alt") or ""
        if "footer" not in alt.lower():
            continue  # an alt that makes no footer claim cannot misdescribe it
        controls, families, tests = _footer_cells(svg)[:3]
        for cell in (controls, families, tests):
            if cell and cell not in alt:
                problems.append(f"{slug}: footer renders {cell!r}, alt does not say it")
    assert not problems, "alt text contradicts the artwork:\n  " + "\n  ".join(problems)


def test_roster_and_counts_agree_on_every_present_engine() -> None:
    """Cheap belt-and-braces: a slug with a spec has a roster row and a pinned count."""
    for slug in present_slugs():
        assert slug in ROSTER, f"{slug} has a spec but no roster row"
        assert COUNTS.get(slug, {}).get("tests"), f"{slug} has no counts.json figure"
