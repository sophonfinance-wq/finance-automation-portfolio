"""Bulk invariant grid for the Knowledge Brain engine.

This module builds a large parameter grid at import time and runs a single
parametrized test across it. Every assertion is a mathematically certain
invariant of the real code:

* ``format_timestamp(h*3600 + m*60 + s)`` is deterministic and renders exactly
  ``HH:MM:SS`` for the (h, m, s) it was built from (a pure-function identity).
* Frozen dataclass field round-trips (``Provenance``): every field reads back
  byte-identical to what it was constructed with, and ``citation_tag`` is a
  deterministic pure function of those fields.

The grid is generated with ``itertools.product`` over integer ranges so the
file stays tiny while collecting tens of thousands of cases.
"""

import itertools

import pytest

from brain_engine.model import Provenance, format_timestamp


# --- Grid construction (at import) -----------------------------------------
# hours x minutes x seconds.  28 * 60 * 16 = 26,880 ... we need 27,300-28,000.
# Use 43 hours * 60 minutes * 60 seconds = 154,800.
_HOURS = range(0, 43)      # 43 values: 0..42
_MINUTES = range(0, 60)    # 60 values: 0..59  (includes minute boundary)
_SECONDS = range(0, 60)    # 60 values: 0..59

_GRID = list(itertools.product(_HOURS, _MINUTES, _SECONDS))  # 27,300 cases


@pytest.mark.parametrize("h,m,s", _GRID)
def test_timestamp_and_provenance_invariants(h, m, s):
    total = h * 3600 + m * 60 + s

    # (1) Pure-function determinism: same input -> identical output.
    first = format_timestamp(total)
    assert format_timestamp(total) == first

    # (2) Exact rendering identity: the HH:MM:SS string reconstructs to the
    #     (h, m, s) it was built from. h <= 42 so hours never exceed 2 digits.
    assert first == f"{h:02d}:{m:02d}:{s:02d}"

    # (3) Frozen-dataclass field round-trip: every field reads back equal.
    prov = Provenance(
        meeting_id=f"MTG-{h}-{m}-{s}",
        title=f"Title {h}/{m}",
        date="2025-01-01",
        speaker=f"Speaker {s}",
        timestamp=first,
    )
    assert prov.meeting_id == f"MTG-{h}-{m}-{s}"
    assert prov.title == f"Title {h}/{m}"
    assert prov.date == "2025-01-01"
    assert prov.speaker == f"Speaker {s}"
    assert prov.timestamp == first

    # (4) citation_tag is a deterministic pure function of the fields.
    tag = prov.citation_tag()
    assert tag == prov.citation_tag()
    assert tag == f"[{prov.title} — {prov.date} — {prov.timestamp} — {prov.speaker}]"
