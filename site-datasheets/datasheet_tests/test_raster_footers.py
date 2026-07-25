"""The four raster tile footers stay tied to the figures they render.

`test_tile_footers.py` compares every *vector* tile's footer to counts.json, and
that guard caught twenty-four tiles rendering a figure 10,000 short. It could not
cover the four `.webp` diagrams -- draw, upgrade, warranty and intercompany -- whose
footers are pixels, and all four were carrying the same defect unnoticed: 392 /
279 / 299 / 310 where counts.json said 10,392 / 10,279 / 10,299 / 10,310. The
intercompany tile even contradicted its own alt text, which already said 10,310.

Pixels cannot be parsed, but the drift can still be gated. `raster_footers.json`
records the figures read off each corrected tile together with the bytes they were
read from, which closes the loop from both directions:

* a count moves in counts.json and the artwork is not re-rendered -> the figure
  assertion fails, naming the tile that now lies;
* the artwork is re-rendered and nobody re-reads the footer -> the digest
  assertion fails, so the new pixels cannot inherit the old verification.

Neither can be satisfied by editing one file alone, which is the point: the only
way through is to re-render the tile and re-read its footer.
"""
from __future__ import annotations

import hashlib
import json

import generate_datasheets as gen

from datasheet_tests.conftest import ROSTER

COUNTS = json.loads((gen.ROOT / "counts.json").read_text(encoding="utf-8"))
PINS = json.loads((gen.ROOT / "raster_footers.json").read_text(encoding="utf-8"))["tiles"]

#: The tiles whose footers are baked into pixels. Kept explicit rather than derived:
#: a new raster tile should have to be added here deliberately, not slip in unchecked.
RASTER_SLUGS = ("draw", "upgrade", "warranty", "intercompany")


def _asset(slug: str):
    # OUT_DIR is docs/engines; the shared artwork sits one level up in docs/assets.
    return gen.REPO / "docs" / "assets" / PINS[slug]["asset"]


def test_every_raster_tile_is_pinned() -> None:
    """No raster tile escapes the manifest, and the manifest invents none."""
    assert set(PINS) == set(RASTER_SLUGS), (
        "raster_footers.json and RASTER_SLUGS disagree", sorted(PINS), sorted(RASTER_SLUGS)
    )
    for slug in RASTER_SLUGS:
        assert _asset(slug).exists(), f"{slug}: pinned asset {_asset(slug)} is missing"


def test_pinned_raster_figures_still_match_counts_json() -> None:
    """The figure burnt into each tile is the one counts.json pins.

    This is the assertion the vector guard could not make. It fails the moment an
    engine's test count moves, which is exactly when the artwork goes stale.
    """
    problems: list[str] = []
    for slug in RASTER_SLUGS:
        want = COUNTS[slug]["tests"]
        got = PINS[slug]["tests"]
        if got != want:
            problems.append(
                f"{slug}: tile renders {got:,} tests but counts.json says {want:,} "
                f"-- re-render docs/assets/{PINS[slug]['asset']} and re-pin it"
            )
    assert not problems, "raster tile footers out of date:\n  " + "\n  ".join(problems)


def test_pinned_raster_part_numbers_match_the_roster() -> None:
    """The part number in the artwork matches the roster's, so renumbering is caught."""
    for slug in RASTER_SLUGS:
        assert PINS[slug]["part_no"] == ROSTER[slug]["part_no"], (
            f"{slug}: tile renders {PINS[slug]['part_no']}, "
            f"roster says {ROSTER[slug]['part_no']}"
        )


def test_pinned_raster_bytes_are_the_bytes_that_were_read() -> None:
    """A re-rendered tile cannot inherit the previous footer verification.

    Without this the figure check above would be worthless: someone could replace
    the artwork with anything and the manifest would keep vouching for it.
    """
    problems: list[str] = []
    for slug in RASTER_SLUGS:
        digest = hashlib.sha256(_asset(slug).read_bytes()).hexdigest()
        if digest != PINS[slug]["sha256"]:
            problems.append(
                f"{slug}: {PINS[slug]['asset']} has changed since its footer was read "
                f"(sha256 {digest[:12]}..., pinned {PINS[slug]['sha256'][:12]}...) "
                f"-- re-read the footer and update raster_footers.json"
            )
    assert not problems, "raster artwork changed without re-verification:\n  " + "\n  ".join(problems)
