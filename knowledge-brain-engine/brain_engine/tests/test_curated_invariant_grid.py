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


# --- extended timestamp grid (+2,700 cases) --------------------------------
# Full minute coverage across 45 hour values (two-digit hours throughout).
_HOURS_X = range(0, 45)    # 45 values
_MINUTES_X = range(0, 60)  # 60 values


@pytest.mark.parametrize("h,m", list(itertools.product(_HOURS_X, _MINUTES_X)))
def test_timestamp_full_minute_coverage(h: int, m: int) -> None:
    s = (h * 11 + m * 7) % 60
    total = h * 3600 + m * 60 + s
    rendered = format_timestamp(total)
    # Exact HH:MM:SS identity and determinism.
    assert rendered == f"{h:02d}:{m:02d}:{s:02d}"
    assert format_timestamp(total) == rendered


# --- extended provenance grid (+1,800 cases) -------------------------------
_SPEAKERS = range(0, 30)   # 30 speaker indices
_SECONDS_X = range(0, 60)  # 60 second values


@pytest.mark.parametrize("i,s", list(itertools.product(_SPEAKERS, _SECONDS_X)))
def test_provenance_roundtrip_extended(i: int, s: int) -> None:
    ts = f"{i:02d}:{s:02d}:{s:02d}"
    prov = Provenance(
        meeting_id=f"MTG-X-{i}-{s}",
        title=f"Review {i}",
        date="2025-06-30",
        speaker=f"Speaker {s}",
        timestamp=ts,
    )
    # Frozen-dataclass field round-trip.
    assert prov.meeting_id == f"MTG-X-{i}-{s}"
    assert prov.title == f"Review {i}"
    assert prov.date == "2025-06-30"
    assert prov.speaker == f"Speaker {s}"
    assert prov.timestamp == ts
    # citation_tag is a deterministic pure function of the fields.
    tag = prov.citation_tag()
    assert tag == prov.citation_tag()
    assert tag == f"[{prov.title} — {prov.date} — {prov.timestamp} — {prov.speaker}]"
