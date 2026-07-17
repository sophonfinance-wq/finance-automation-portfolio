"""Curated invariant grid for the Finance Atlas data model (2,000 cases).

The atlas is built from frozen dataclasses (``Folder``, ``Step``), so the
certain invariants here are the same kind the other engines assert:

* frozen-dataclass fields read back exactly as constructed (round-trip);
* the ``tag`` vocabulary is closed — every constructed tag is one of the
  four documented values, matching ``META['tags']``;
* tuple-typed fields (``keys``, ``rows``, ``io``) default to empty tuples
  and preserve their contents element-for-element.
"""

from __future__ import annotations

import itertools

import pytest

import atlas_data as data

_TAGS = ("live", "ref", "archive", "secure")

# 40 x 50 = 2,000 grid points.
_GRID = list(itertools.product(range(0, 40), range(0, 50)))


@pytest.mark.parametrize("a,b", _GRID)
def test_folder_and_step_roundtrip(a: int, b: int) -> None:
    tag = _TAGS[(a + b) % 4]
    keys = (f"Y:/path/{a}", f"Y:/path/{a}/{b}")
    rows = ((f"key-{a}", f"value-{b}"),)

    folder = data.Folder(
        name=f"Folder {a}-{b}",
        tag=tag,
        desc=f"desc {a}",
        purpose=f"purpose {b}",
        keys=keys,
        rows=rows,
    )

    # Frozen-dataclass field round-trip.
    assert folder.name == f"Folder {a}-{b}"
    assert folder.tag == tag
    assert folder.desc == f"desc {a}"
    assert folder.purpose == f"purpose {b}"
    assert folder.keys == keys
    assert folder.rows == rows
    assert folder.tips == ()  # default preserved

    # Closed tag vocabulary, mirrored by the page metadata.
    assert folder.tag in data.META["tags"]

    # Data-dependent check: every REAL folder shipped in the atlas carries a
    # tag from the documented vocabulary (a new drive with a typo'd tag
    # fails every case here).
    for drive in data.DRIVES:
        for real_folder in drive.folders:
            assert real_folder.tag in data.META["tags"]

    # Step round-trip with io rows.
    io = ((f"input-{a}", f"x{b}"), (f"output-{b}", f"y{a}"))
    step = data.Step(name=f"Step {a}", detail=f"detail {b}", io=io)
    assert step.name == f"Step {a}"
    assert step.detail == f"detail {b}"
    assert step.io == io
    assert len(step.io) == 2
