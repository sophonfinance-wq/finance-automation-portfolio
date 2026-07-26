"""Every tile's spec strip stays tied to the figures it renders.

All forty-seven engine tiles are now raster. The artwork is generated carrying no
lettering at all, and the strip -- controls, tests, read-only, part number -- is
composited afterwards from counts.json and the roster. That split exists because a
figure baked into pixels cannot be parsed: four tiles shipped for weeks reading
392 / 279 / 299 / 310 tests against a truth of 10,392 / 10,279 / 10,299 / 10,310,
and the intercompany tile contradicted its own alt text, which already said 10,310.

Pixels still cannot be read, but the drift can be gated. `raster_footers.json`
records the figures composited onto each tile together with digests of the exact
files they were composited into, which closes the loop from both directions:

* a count moves in counts.json and the artwork is not re-rendered -> the figure
  assertion fails, naming the tile that now lies;
* a file is re-rendered and nobody re-reads the strip -> its digest assertion
  fails, so new pixels cannot inherit the old verification.

Four tiles pin a motion file as well as a poster. The poster is only frame 0, so
correcting it alone hid the defect rather than fixing it -- all four animations
went on rendering the short figure until they were pinned too.

This replaces the old vector guard, which parsed `<text>` out of the SVG tiles.
There are no SVG tiles left for it to check.
"""
from __future__ import annotations

import hashlib
import json
import re

import datasheet_spec as ds
import generate_datasheets as gen

from datasheet_tests.conftest import ROSTER, present_slugs

COUNTS = json.loads((gen.ROOT / "counts.json").read_text(encoding="utf-8"))
PINS = json.loads((gen.ROOT / "raster_footers.json").read_text(encoding="utf-8"))["tiles"]


def _asset(name: str):
    # OUT_DIR is docs/engines; the shared artwork sits one level up in docs/assets.
    return gen.REPO / "docs" / "assets" / name


def _files(entry):
    """(kind, filename) for every pinned file on a tile."""
    return [(k, entry[k]) for k in ("poster", "motion") if k in entry]


def test_every_pinned_tile_exists_and_is_rostered() -> None:
    """The manifest names real files and real engines, and nothing invented."""
    for slug, entry in sorted(PINS.items()):
        assert slug in ROSTER, f"{slug} is pinned but has no roster row"
        for kind, name in _files(entry):
            assert _asset(name).exists(), f"{slug}: pinned {kind} {name} is missing"
            assert entry["sha256"].get(kind), f"{slug}: no {kind} digest pinned"


def test_pinned_figures_still_match_counts_json() -> None:
    """The test figure burnt into each tile is the one counts.json pins.

    This is the assertion whose absence let four tiles run 10,000 short.
    """
    problems: list[str] = []
    for slug, entry in sorted(PINS.items()):
        want = COUNTS[slug]["tests"]
        if entry["tests"] != want:
            targets = " and ".join(f"docs/assets/{n}" for _, n in _files(entry))
            problems.append(
                f"{slug}: tile renders {entry['tests']:,} tests but counts.json says "
                f"{want:,} -- re-render {targets}, then re-pin"
            )
    assert not problems, "raster tile footers out of date:\n  " + "\n  ".join(problems)


def test_pinned_part_numbers_match_the_roster() -> None:
    """A renumbered engine cannot leave its old part number sitting in the artwork."""
    for slug, entry in sorted(PINS.items()):
        assert entry["part_no"] == ROSTER[slug]["part_no"], (
            f"{slug}: tile renders {entry['part_no']}, roster says {ROSTER[slug]['part_no']}"
        )


def test_pinned_bytes_are_the_bytes_that_were_read() -> None:
    """Re-rendered artwork cannot inherit the previous verification.

    Without this the figure check above would be worthless: the artwork could be
    replaced with anything and the manifest would keep vouching for it.
    """
    problems: list[str] = []
    for slug, entry in sorted(PINS.items()):
        for kind, name in _files(entry):
            pinned = entry["sha256"][kind]
            digest = hashlib.sha256(_asset(name).read_bytes()).hexdigest()
            if digest != pinned:
                problems.append(
                    f"{slug} {kind}: {name} changed since its strip was read "
                    f"(sha256 {digest[:12]}..., pinned {pinned[:12]}...) "
                    f"-- re-read the strip and update raster_footers.json"
                )
    assert not problems, "raster artwork changed without re-verification:\n  " + "\n  ".join(problems)


def test_alt_text_states_the_strip_the_tile_renders() -> None:
    """The alt text quotes the same figures the artwork does.

    A screen-reader user gets the alt and nothing else, so an alt that disagrees
    with the picture is simply wrong -- which is exactly how the intercompany tile
    was caught claiming 10,310 while rendering 310.
    """
    problems: list[str] = []
    for slug, entry in sorted(PINS.items()):
        alt = (ds.load_spec(slug).get("media") or {}).get("poster_alt") or ""
        if "footer" not in alt.lower():
            continue  # an alt that makes no strip claim cannot misstate it
        # Eight engines carry no Controls figure in their spec_strip, so their strip
        # renders three cells instead of four and their pin has no controls key. The
        # cell that does not exist cannot be misstated; the rest still must not be.
        cells = [f"{entry['tests']:,} tests", entry["part_no"]]
        if "controls" in entry:
            cells.insert(0, f"{entry['controls']} controls")
        elif re.search(r"\d[\d,]*\s+controls\b", alt, re.I):
            # The exemption must not become a way to dodge the assertion: a tile whose
            # strip omits the figure may not have an alt that claims one anyway. Match a
            # FIGURE rather than the bare word, because the alt legitimately describes
            # "a bank of inspection stations that each check one family of controls".
            problems.append(
                f"{slug}: strip renders no controls figure, but its alt text claims one")
        for cell in cells:
            if cell.lower() not in alt.lower():
                problems.append(f"{slug}: strip renders {cell!r}, alt does not say it")
    assert not problems, "alt text contradicts the artwork:\n  " + "\n  ".join(problems)


def test_every_engine_tile_is_pinned() -> None:
    """No engine tile quietly escapes the manifest.

    Tiles whose artwork carries no figures (the seven illustrative ones) are out of
    scope; every tile that does render a strip must be covered.
    """
    unpinned = [
        slug for slug in present_slugs()
        if (ds.load_spec(slug).get("media") or {}).get("poster", "").endswith(".webp")
        and "footer" in ((ds.load_spec(slug).get("media") or {}).get("poster_alt") or "").lower()
        and slug not in PINS
    ]
    assert not unpinned, f"these tiles claim a footer strip but are not pinned: {unpinned}"
