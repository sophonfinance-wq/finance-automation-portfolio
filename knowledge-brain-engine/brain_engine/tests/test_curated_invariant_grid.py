"""Curated invariant grid for the Knowledge Brain engine (1,000 cases).

A bounded, CI-gating slice of the SWEEP-gated ``test_bulk_invariant_grid.py``.
Every assertion is a certain invariant of the real code:

* ``format_timestamp(h*3600 + m*60 + s)`` renders exactly ``HH:MM:SS`` and is
  deterministic;
* ``Provenance`` frozen-dataclass fields round-trip, and ``citation_tag`` is a
  deterministic pure function of those fields.
"""

import itertools

import pytest

from brain_engine.model import Provenance, format_timestamp

# 20 hours x 50 minutes = 1,000.
_HOURS = range(0, 20)
_MINUTES = range(0, 50)
_GRID = list(itertools.product(_HOURS, _MINUTES))


@pytest.mark.parametrize("h,m", _GRID)
def test_timestamp_and_provenance(h: int, m: int) -> None:
    s = (h * 7 + m) % 60
    total = h * 3600 + m * 60 + s

    # Exact rendering identity + determinism (h < 20 -> two-digit hours).
    rendered = format_timestamp(total)
    assert rendered == f"{h:02d}:{m:02d}:{s:02d}"
    assert format_timestamp(total) == rendered

    # Frozen-dataclass field round-trip.
    prov = Provenance(
        meeting_id=f"MTG-{h}-{m}",
        title=f"Title {h}/{m}",
        date="2025-01-01",
        speaker=f"Speaker {s}",
        timestamp=rendered,
    )
    assert prov.meeting_id == f"MTG-{h}-{m}"
    assert prov.title == f"Title {h}/{m}"
    assert prov.date == "2025-01-01"
    assert prov.speaker == f"Speaker {s}"
    assert prov.timestamp == rendered

    # citation_tag is a deterministic pure function of the fields.
    tag = prov.citation_tag()
    assert tag == prov.citation_tag()
    assert tag == f"[{prov.title} — {prov.date} — {prov.timestamp} — {prov.speaker}]"
