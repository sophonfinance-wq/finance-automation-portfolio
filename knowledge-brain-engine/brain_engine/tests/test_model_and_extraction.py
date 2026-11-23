"""Tests for the model, timestamp formatting, and card extraction provenance."""

from __future__ import annotations

import pytest

from brain_engine.generate import build_corpus
from brain_engine.model import (
    AUTHORITATIVE_KINDS,
    CARD_KINDS,
    OPEN_ITEM,
    KnowledgeCard,
    Provenance,
    Utterance,
    format_timestamp,
)


def _corpus():
    return build_corpus()


# --- HH:MM:SS formatting from seconds ------------------------------------
def test_format_timestamp_zero() -> None:
    assert format_timestamp(0) == "00:00:00"


def test_format_timestamp_minutes_and_seconds() -> None:
    assert format_timestamp(182) == "00:03:02"


def test_format_timestamp_hours() -> None:
    assert format_timestamp(3725) == "01:02:05"


def test_format_timestamp_rejects_negative() -> None:
    with pytest.raises(ValueError):
        format_timestamp(-1)


def test_utterance_timestamp_property_matches_formatter() -> None:
    utt = Utterance("Demo Speaker", 540, "Some line.")
    assert utt.timestamp == "00:09:00"
    assert utt.timestamp == format_timestamp(540)


# --- extraction yields cards with full provenance -------------------------
def test_every_card_has_full_provenance() -> None:
    corpus = _corpus()
    assert corpus.cards
    for card in corpus.cards:
        prov = card.provenance
        assert prov.meeting_id
        assert prov.title
        assert prov.date
        assert prov.speaker
        assert prov.timestamp  # HH:MM:SS
        assert len(prov.timestamp.split(":")) == 3


def test_no_card_emitted_without_a_source_utterance() -> None:
    """Every card's quote must exist verbatim in some transcript utterance."""
    corpus = _corpus()
    for card in corpus.cards:
        source_text = corpus.utterance_text(card.provenance.meeting_id, card.provenance.timestamp)
        assert card.rule_text == source_text


def test_card_kinds_are_valid() -> None:
    corpus = _corpus()
    for card in corpus.cards:
        assert card.kind in CARD_KINDS


def test_card_requires_a_topic_tag() -> None:
    prov = Provenance("MTG-X", "Demo", "2025-01-01", "Demo Speaker", "00:00:01")
    with pytest.raises(ValueError):
        KnowledgeCard("CARD-X", (), "Some rule.", "rule", prov)


def test_card_rejects_unknown_kind() -> None:
    prov = Provenance("MTG-X", "Demo", "2025-01-01", "Demo Speaker", "00:00:01")
    with pytest.raises(ValueError):
        KnowledgeCard("CARD-X", ("topic",), "Some rule.", "not-a-kind", prov)


def test_open_item_is_not_authoritative() -> None:
    corpus = _corpus()
    open_items = [c for c in corpus.cards if c.kind == OPEN_ITEM]
    assert open_items
    for card in open_items:
        assert card.is_authoritative is False


def test_authoritative_kinds_are_authoritative() -> None:
    corpus = _corpus()
    auth = [c for c in corpus.cards if c.kind in AUTHORITATIVE_KINDS]
    assert auth
    for card in auth:
        assert card.is_authoritative is True


def test_provenance_citation_tag_shape() -> None:
    tag = Provenance("MTG-X", "Demo Meeting", "2025-02-03", "Lena Frost", "00:03:41").citation_tag()
    assert tag == "[Demo Meeting — 2025-02-03 — 00:03:41 — Lena Frost]"


def test_corpus_has_at_least_four_meetings() -> None:
    corpus = _corpus()
    assert len(corpus.meetings) >= 4


def test_meeting_rejects_bad_date() -> None:
    from brain_engine.model import Meeting

    with pytest.raises(ValueError):
        Meeting("MTG-X", "not-a-date", "Demo", ("A",), (Utterance("A", 0, "hi"),))
