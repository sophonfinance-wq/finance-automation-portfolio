"""Additional coverage for the core data model: validation, provenance,
timestamps, and the Corpus grouping/lookup helpers.

Every test exercises real ``brain_engine.model`` code and asserts behaviour
derived from the model's actual contracts (frozen dataclasses, __post_init__
validation, byte-identical provenance lookups).
"""

from __future__ import annotations

import dataclasses

import pytest

from brain_engine.generate import build_corpus
from brain_engine.model import (
    AUTHORITATIVE_KINDS,
    CARD_KINDS,
    DECISION,
    DEFINITION,
    OPEN_ITEM,
    RULE,
    ChangeDirective,
    Corpus,
    KnowledgeCard,
    Meeting,
    Provenance,
    Utterance,
    format_timestamp,
)


def _corpus():
    return build_corpus()


# --- format_timestamp boundary / parametrized -----------------------------
@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0, "00:00:00"),
        (1, "00:00:01"),
        (59, "00:00:59"),
        (60, "00:01:00"),
        (61, "00:01:01"),
        (599, "00:09:59"),
        (600, "00:10:00"),
        (3599, "00:59:59"),
        (3600, "01:00:00"),
        (3661, "01:01:01"),
        (3725, "01:02:05"),
        (86399, "23:59:59"),
        (90061, "25:01:01"),
    ],
)
def test_format_timestamp_table(seconds, expected) -> None:
    assert format_timestamp(seconds) == expected


def test_format_timestamp_always_three_colon_groups() -> None:
    for s in (0, 7, 125, 4000, 100000):
        parts = format_timestamp(s).split(":")
        assert len(parts) == 3
        assert all(len(p) == 2 or p == parts[0] for p in parts[1:])


@pytest.mark.parametrize("bad", [-1, -60, -3600])
def test_format_timestamp_rejects_negative_values(bad) -> None:
    with pytest.raises(ValueError):
        format_timestamp(bad)


def test_format_timestamp_round_trip_against_utterance() -> None:
    # The HH:MM:SS rendering must invert back to the original whole seconds.
    for s in (0, 47, 182, 540, 3725):
        h, m, sec = (int(p) for p in format_timestamp(s).split(":"))
        assert h * 3600 + m * 60 + sec == s


# --- Utterance validation & immutability ----------------------------------
def test_utterance_rejects_negative_seconds() -> None:
    with pytest.raises(ValueError):
        Utterance("Demo", -5, "hi")


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n  \n"])
def test_utterance_rejects_blank_text(blank) -> None:
    with pytest.raises(ValueError):
        Utterance("Demo", 0, blank)


def test_utterance_is_frozen() -> None:
    utt = Utterance("Demo", 10, "hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        utt.t_seconds = 20  # type: ignore[misc]


def test_utterance_timestamp_property_consistent() -> None:
    utt = Utterance("Demo", 3661, "line")
    assert utt.timestamp == "01:01:01"


# --- Meeting validation ----------------------------------------------------
@pytest.mark.parametrize(
    "bad_date",
    ["2025/01/01", "2025-1", "not-a-date", "2025-01", "abcd-ef-gh", "20250101"],
)
def test_meeting_rejects_malformed_dates(bad_date) -> None:
    with pytest.raises(ValueError):
        Meeting("MTG-X", bad_date, "Demo", ("A",), (Utterance("A", 0, "hi"),))


def test_meeting_rejects_empty_utterances() -> None:
    with pytest.raises(ValueError):
        Meeting("MTG-X", "2025-01-01", "Demo", ("A",), ())


def test_meeting_accepts_well_formed_date() -> None:
    m = Meeting("MTG-X", "2025-12-31", "Demo", ("A",), (Utterance("A", 0, "hi"),))
    assert m.date == "2025-12-31"


# --- Provenance citation tag ----------------------------------------------
def test_provenance_citation_tag_orders_fields() -> None:
    tag = Provenance("MTG-Z", "Title", "2025-05-05", "Pat Doe", "00:10:20").citation_tag()
    assert tag == "[Title — 2025-05-05 — 00:10:20 — Pat Doe]"


def test_provenance_is_frozen() -> None:
    prov = Provenance("MTG-Z", "Title", "2025-05-05", "Pat Doe", "00:10:20")
    with pytest.raises(dataclasses.FrozenInstanceError):
        prov.speaker = "Other"  # type: ignore[misc]


# --- KnowledgeCard validation & is_authoritative --------------------------
@pytest.mark.parametrize("kind", list(CARD_KINDS))
def test_card_accepts_every_valid_kind(kind) -> None:
    prov = Provenance("MTG-X", "Demo", "2025-01-01", "Speaker", "00:00:01")
    card = KnowledgeCard("CARD-X", ("topic",), "Some text.", kind, prov)
    assert card.kind == kind


@pytest.mark.parametrize(
    "kind, expected",
    [
        (DECISION, True),
        (RULE, True),
        (DEFINITION, True),
        (OPEN_ITEM, False),
    ],
)
def test_card_is_authoritative_matches_kind(kind, expected) -> None:
    prov = Provenance("MTG-X", "Demo", "2025-01-01", "Speaker", "00:00:01")
    card = KnowledgeCard("CARD-X", ("topic",), "Some text.", kind, prov)
    assert card.is_authoritative is expected


@pytest.mark.parametrize("blank", ["", "   "])
def test_card_rejects_blank_rule_text(blank) -> None:
    prov = Provenance("MTG-X", "Demo", "2025-01-01", "Speaker", "00:00:01")
    with pytest.raises(ValueError):
        KnowledgeCard("CARD-X", ("topic",), blank, RULE, prov)


def test_authoritative_kinds_excludes_open_item() -> None:
    assert OPEN_ITEM not in AUTHORITATIVE_KINDS
    assert set(AUTHORITATIVE_KINDS) == {DECISION, RULE, DEFINITION}


# --- ChangeDirective validation -------------------------------------------
def test_directive_rejects_blank_request_text() -> None:
    prov = Provenance("MTG-X", "Demo", "2025-01-01", "Speaker", "00:00:01")
    with pytest.raises(ValueError):
        ChangeDirective("DIR-X", ("topic",), "   ", prov)


def test_directive_requires_topic_tag() -> None:
    prov = Provenance("MTG-X", "Demo", "2025-01-01", "Speaker", "00:00:01")
    with pytest.raises(ValueError):
        ChangeDirective("DIR-X", (), "change something", prov)


def test_directive_citation_tag_matches_provenance() -> None:
    prov = Provenance("MTG-X", "Review", "2025-04-08", "Quinn", "00:01:04")
    d = ChangeDirective("DIR-X", ("review",), "change it", prov, target="thing")
    assert d.citation_tag() == prov.citation_tag()


def test_directive_default_target_is_empty() -> None:
    prov = Provenance("MTG-X", "Review", "2025-04-08", "Quinn", "00:01:04")
    d = ChangeDirective("DIR-X", ("review",), "change it", prov)
    assert d.target == ""


# --- Corpus helpers --------------------------------------------------------
def test_corpus_defaults_are_empty_and_independent() -> None:
    a = Corpus()
    b = Corpus()
    a.cards.append("sentinel")  # type: ignore[arg-type]
    assert a.cards != b.cards  # default_factory gives each its own list


def test_corpus_utterance_text_returns_exact_source() -> None:
    corpus = _corpus()
    text = corpus.utterance_text("MTG-2025-WARRANTY", "00:03:02")
    assert "warranty reserve" in text
    # And it equals the card lifted from that timestamp.
    card = next(c for c in corpus.cards if c.card_id == "CARD-WARRANTY-01")
    assert card.rule_text == text


def test_corpus_utterance_text_raises_on_unknown_meeting() -> None:
    with pytest.raises(KeyError):
        _corpus().utterance_text("MTG-DOES-NOT-EXIST", "00:00:01")


def test_corpus_utterance_text_raises_on_unknown_timestamp() -> None:
    with pytest.raises(KeyError):
        _corpus().utterance_text("MTG-2025-WARRANTY", "99:99:99")


def test_cards_by_topic_card_appears_under_each_tag() -> None:
    corpus = _corpus()
    grouped = corpus.cards_by_topic()
    card = next(c for c in corpus.cards if c.card_id == "CARD-WARRANTY-01")
    for tag in card.topic_tags:
        assert card in grouped[tag]


def test_cards_by_topic_total_listings_equals_sum_of_tags() -> None:
    corpus = _corpus()
    grouped = corpus.cards_by_topic()
    total_listings = sum(len(v) for v in grouped.values())
    assert total_listings == sum(len(c.topic_tags) for c in corpus.cards)


def test_directives_by_topic_groups_review_tag() -> None:
    corpus = _corpus()
    grouped = corpus.directives_by_topic()
    review_ids = sorted(d.directive_id for d in grouped["review"])
    assert review_ids == [
        "DIR-SURPLUS-REVIEW-01",
        "DIR-SURPLUS-REVIEW-02",
        "DIR-SURPLUS-REVIEW-03",
        "DIR-SURPLUS-REVIEW-04",
    ]


def test_directives_by_topic_total_listings_equals_sum_of_tags() -> None:
    corpus = _corpus()
    grouped = corpus.directives_by_topic()
    total = sum(len(v) for v in grouped.values())
    assert total == sum(len(d.topic_tags) for d in corpus.directives)
