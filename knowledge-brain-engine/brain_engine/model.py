"""Core data model for the Knowledge Brain engine.

These dataclasses describe the *fictional* transcript corpus and the knowledge
cards extracted from it. Keeping them as plain, typed, frozen dataclasses makes
ingestion deterministic and easy to test.

The chain of custody is the whole point:

    Meeting (id, date, title, participants)
        -> Utterance (speaker, t_seconds, text)   [the source of truth]
        -> KnowledgeCard (verbatim rule_text + Provenance)

Provenance — meeting, title, date, speaker, and HH:MM:SS timestamp — always
travels with the quote. A card's ``rule_text`` is byte-identical to the source
utterance's ``text``; the engine asserts this so a citation can never drift from
what was actually said.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# The kinds of authoritative statement a card can capture. ``open-item`` is a
# parked question rather than a settled rule — prep mode surfaces it, cite mode
# never treats it as authority.
DECISION = "decision"
RULE = "rule"
DEFINITION = "definition"
OPEN_ITEM = "open-item"

CARD_KINDS: Tuple[str, ...] = (DECISION, RULE, DEFINITION, OPEN_ITEM)

# Kinds that constitute authority a workpaper / disclosure note may cite.
AUTHORITATIVE_KINDS: Tuple[str, ...] = (DECISION, RULE, DEFINITION)


def format_timestamp(t_seconds: int) -> str:
    """Render an integer second offset as ``HH:MM:SS``.

    >>> format_timestamp(0)
    '00:00:00'
    >>> format_timestamp(3725)
    '01:02:05'
    """
    if t_seconds < 0:
        raise ValueError(f"t_seconds must be >= 0, got {t_seconds}")
    hours, rem = divmod(int(t_seconds), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@dataclass(frozen=True)
class Utterance:
    """A single timestamped line of a transcript.

    Attributes
    ----------
    speaker:
        Display name of the speaker — always an obviously fake name.
    t_seconds:
        Offset from the start of the meeting, in whole seconds.
    text:
        The verbatim spoken text. This is the source of truth a card quotes.
    """

    speaker: str
    t_seconds: int
    text: str

    def __post_init__(self) -> None:
        if self.t_seconds < 0:
            raise ValueError("t_seconds must be >= 0")
        if not self.text.strip():
            raise ValueError("utterance text must be non-empty")

    @property
    def timestamp(self) -> str:
        """The ``HH:MM:SS`` rendering of :attr:`t_seconds`."""
        return format_timestamp(self.t_seconds)


@dataclass(frozen=True)
class Meeting:
    """A fictional recorded-and-transcribed meeting.

    Attributes
    ----------
    meeting_id:
        Short stable identifier (e.g. ``"MTG-2025-WARRANTY"``).
    date:
        Meeting date as ``YYYY-MM-DD``.
    title:
        Display title — always an obviously fake topic.
    participants:
        Names present in the room.
    utterances:
        The transcript, in spoken order.
    """

    meeting_id: str
    date: str
    title: str
    participants: Tuple[str, ...]
    utterances: Tuple[Utterance, ...]

    def __post_init__(self) -> None:
        parts = self.date.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"date must be YYYY-MM-DD, got {self.date!r}")
        if not self.utterances:
            raise ValueError(f"meeting {self.meeting_id} has no utterances")


@dataclass(frozen=True)
class Provenance:
    """Where a knowledge card came from. Travels with every quote.

    The fields are exactly what an auditor needs to re-open the source: which
    meeting, on what date, at what timestamp, said by whom.
    """

    meeting_id: str
    title: str
    date: str
    speaker: str
    timestamp: str  # HH:MM:SS

    def citation_tag(self) -> str:
        """A compact, paste-ready citation tag for inline use."""
        return f"[{self.title} — {self.date} — {self.timestamp} — {self.speaker}]"


@dataclass(frozen=True)
class KnowledgeCard:
    """An authoritative rule / decision / definition / open-item from a transcript.

    Attributes
    ----------
    card_id:
        Stable identifier (e.g. ``"CARD-WARRANTY-01"``).
    topic_tags:
        Normalised topic tags used by retrieval (e.g. ``("warranty", "book-tax")``).
    rule_text:
        The VERBATIM quote — byte-identical to the source utterance text.
    kind:
        One of :data:`CARD_KINDS`.
    provenance:
        Full source attribution (see :class:`Provenance`).
    """

    card_id: str
    topic_tags: Tuple[str, ...]
    rule_text: str
    kind: str
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.kind not in CARD_KINDS:
            raise ValueError(f"kind must be one of {CARD_KINDS}, got {self.kind!r}")
        if not self.rule_text.strip():
            raise ValueError("card rule_text must be non-empty")
        if not self.topic_tags:
            raise ValueError(f"card {self.card_id} must carry at least one topic tag")

    @property
    def is_authoritative(self) -> bool:
        """True if this card may back a workpaper / disclosure citation."""
        return self.kind in AUTHORITATIVE_KINDS


@dataclass
class Corpus:
    """The full fictional corpus: meetings plus the cards extracted from them."""

    meetings: List[Meeting] = field(default_factory=list)
    cards: List[KnowledgeCard] = field(default_factory=list)

    def utterance_text(self, meeting_id: str, timestamp: str) -> str:
        """Return the source utterance text for a (meeting, timestamp) pair.

        Used by tests and cite mode to prove a card's quote is byte-identical to
        the transcript it came from.
        """
        for meeting in self.meetings:
            if meeting.meeting_id != meeting_id:
                continue
            for utt in meeting.utterances:
                if utt.timestamp == timestamp:
                    return utt.text
        raise KeyError(f"no utterance at {meeting_id} {timestamp}")

    def cards_by_topic(self) -> Dict[str, List[KnowledgeCard]]:
        """Group cards by topic tag (a card with N tags appears under N keys)."""
        grouped: Dict[str, List[KnowledgeCard]] = {}
        for card in self.cards:
            for tag in card.topic_tags:
                grouped.setdefault(tag, []).append(card)
        return grouped
