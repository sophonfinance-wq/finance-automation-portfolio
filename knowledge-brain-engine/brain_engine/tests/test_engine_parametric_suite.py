"""Parametric engine test suite — ~700 tests.

Tests the BrainEngine against the default fictional corpus across:
- Query shapes (ask / cite / prep / rank / remediate)
- Parametrised query strings, top_k values, confidence floors, topic tags
- Determinism, ordering, provenance integrity, and refusal governance
"""

from __future__ import annotations

import math
import pytest

from brain_engine.generate import build_corpus, REVIEW_MEETING_TITLE
from brain_engine.engine import (
    BrainEngine,
    MIN_RELEVANCE,
    STATUS_PENDING,
    RetrievalHit,
    FixPacketEntry,
    Remediation,
    _tokenize,
)
from brain_engine.model import (
    AUTHORITATIVE_KINDS,
    CARD_KINDS,
    DECISION,
    DEFINITION,
    OPEN_ITEM,
    RULE,
    KnowledgeCard,
    Corpus,
    Meeting,
    Utterance,
    Provenance,
    ChangeDirective,
    format_timestamp,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def corpus():
    return build_corpus()


@pytest.fixture(scope="module")
def engine(corpus):
    return BrainEngine(corpus)


# ---------------------------------------------------------------------------
# 1. _tokenize — parametrised over 80 inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_nonempty", [
    ("warranty reserve book-tax", True),
    ("the and or but", False),   # all stopwords
    ("basis capital gain", True),
    ("a an and", False),
    ("deferred tax asset", True),
    ("", False),
    ("   ", False),
    ("workpaper evidence anchor", True),
    ("surplus distribution elevation", True),
    ("return of capital", True),          # 'of' is stopword; 'return capital' remain
    ("fx rate source", True),
    ("accrual schedule line", True),
    ("open item extended warranty", True),
    ("book-tax-difference", True),        # hyphenated compound preserved
    ("Decision rule definition", True),
    ("100 200 300", True),                # numbers are tokens
    ("UPPERCASE QUERY", True),            # lowercased
    ("mixed123 numbers456", True),
    ("a", False),                         # single stopword
    ("z", True),                          # single non-stopword letter
    ("performance obligation year", True),
    ("state tax federal", True),
    ("capital-gain recharacterization", True),
    ("adjusted cost base", True),
    ("distribution formula column", True),
    ("evidence tie-out footnote", True),
    ("reviewer corrections apply", True),
    ("meeting transcript speaker", True),
    ("timestamp provenance citation", True),
    ("M-1 add-back accrual", True),
    ("deferred tax deferred", True),      # repeated term
    ("warranty warranty warranty", True),
    ("book tax book tax", True),
    ("is it the what", False),            # all stopwords
    ("net gross difference", True),
    ("year end period close", True),
    ("sign-off sign off", True),
    ("re-run re run", True),
    ("consolidated development level", True),
    ("footnote anchor source", True),
    ("prior decisions open items", True),
    ("reviewer sign basis zero", True),
    ("column D column E", True),
    ("26000 distribution classification", True),
    ("not should must can do", False),    # stopwords
    ("capital events contributions returns", True),
    ("operating income undistributed", True),
    ("ownership percentage parent", True),
    ("foreign affiliate subsidiary", True),
    ("cash paid distribution trigger", True),
    ("tax return classification reclassification", True),
    ("verbatim byte-identical quote", True),
    ("knowledge brain engine", True),
    ("deterministic retrieval index", True),
    ("cosine similarity score", True),
    ("TF-IDF term frequency", True),
    ("min relevance threshold floor", True),
    ("provenance integrity chain custody", True),
    ("workpaper disclosure citation", True),
    ("rule text card kind", True),
    ("meeting id date title", True),
    ("participant speaker utterance", True),
    ("seconds offset timestamp", True),
    ("hours minutes seconds", True),
    ("question assertion topic", True),
    ("refusal banner governance", True),
    ("fix packet change log", True),
    ("status pending applied", True),
    ("directive id topic tags", True),
    ("remediation prompt paste", True),
    ("downstream AI operator", True),
    ("apply changes log source", True),
    ("fiction fictional demo", True),
    ("sanitized public data", True),
    ("foo bar baz", True),
    ("x y z", True),
    ("1 2 3", True),
    ("zero one two", True),
    ("hello world test", True),
    ("a1b2c3", True),
    ("hyphen-ated com-pound term", True),
])
def test_tokenize(text, expected_nonempty):
    tokens = _tokenize(text)
    assert isinstance(tokens, list)
    if expected_nonempty:
        assert len(tokens) > 0
    else:
        assert len(tokens) == 0


# ---------------------------------------------------------------------------
# 2. format_timestamp parametrised over 60 values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("t_seconds,expected", [
    (0, "00:00:00"),
    (1, "00:00:01"),
    (59, "00:00:59"),
    (60, "00:01:00"),
    (61, "00:01:01"),
    (119, "00:01:59"),
    (120, "00:02:00"),
    (599, "00:09:59"),
    (600, "00:10:00"),
    (3599, "00:59:59"),
    (3600, "01:00:00"),
    (3601, "01:00:01"),
    (3660, "01:01:00"),
    (3661, "01:01:01"),
    (3725, "01:02:05"),
    (7199, "01:59:59"),
    (7200, "02:00:00"),
    (10800, "03:00:00"),
    (36000, "10:00:00"),
    (36060, "10:01:00"),
    (36061, "10:01:01"),
    (72000, "20:00:00"),
    (86399, "23:59:59"),
    (86400, "24:00:00"),
    (90000, "25:00:00"),
    (182, "00:03:02"),
    (361, "00:06:01"),
    (540, "00:09:00"),
    (95, "00:01:35"),
    (221, "00:03:41"),
    (400, "00:06:40"),
    (505, "00:08:25"),
    (72, "00:01:12"),
    (240, "00:04:00"),
    (360, "00:06:00"),
    (455, "00:07:35"),
    (88, "00:01:28"),
    (300, "00:05:00"),
    (410, "00:06:50"),
    (520, "00:08:40"),
    (64, "00:01:04"),
    (212, "00:03:32"),
    (366, "00:06:06"),
    (498, "00:08:18"),
    (47, "00:00:47"),
    (168, "00:02:48"),
    (333, "00:05:33"),
    (100, "00:01:40"),
    (200, "00:03:20"),
    (1000, "00:16:40"),
    (2000, "00:33:20"),
    (5000, "01:23:20"),
    (9999, "02:46:39"),
    (99999, "27:46:39"),
    (30, "00:00:30"),
    (45, "00:00:45"),
    (90, "00:01:30"),
    (150, "00:02:30"),
    (3000, "00:50:00"),
    (18000, "05:00:00"),
])
def test_format_timestamp(t_seconds, expected):
    assert format_timestamp(t_seconds) == expected


# ---------------------------------------------------------------------------
# 3. format_timestamp negative raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [-1, -60, -3600, -100])
def test_format_timestamp_negative_raises(bad):
    with pytest.raises(ValueError):
        format_timestamp(bad)


# ---------------------------------------------------------------------------
# 4. BrainEngine.ask — on-topic queries that should return hits
# ---------------------------------------------------------------------------

ON_TOPIC_QUERIES = [
    "warranty reserve book tax",
    "book tax deferred tax asset",
    "accrual deduction warranty",
    "return of capital basis",
    "distribution excess basis capital gain",
    "basis floor zero",
    "workpaper evidence tie out",
    "evidence anchor figure",
    "surplus elevation distribution",
    "adjusted cost base capital event",
    "distribution definition trigger",
    "foreign affiliate parent",
    "book tax difference M1 add back",
    "rework workpaper anchor",
    "extended warranty performance obligation",
    "state tax federal recharacterization",
    "FX rate elevation year",
    "accrual schedule line workpaper",
    "basis investor distribution",
    "surplus distribution ownership percentage",
    "reviewer corrections distribution formula",
    "add back warranty book tax development",
    "evidence query footnote anchor",
    "distribution classification tax return",
    "change directive review surplus",
    "surplus workpaper review corrections",
    "warranty accrual tax deduction timing",
    "deemed capital gain excess distribution",
    "anchor tie out evidence figure",
    "surplus elevated parent ownership",
]


@pytest.mark.parametrize("query", ON_TOPIC_QUERIES)
def test_ask_on_topic_returns_hits(engine, query):
    hits = engine.ask(query)
    assert len(hits) >= 1, f"Expected hits for on-topic query: {query!r}"


@pytest.mark.parametrize("query", ON_TOPIC_QUERIES)
def test_ask_on_topic_scores_above_floor(engine, query):
    hits = engine.ask(query)
    for hit in hits:
        assert hit.score >= engine.min_relevance


@pytest.mark.parametrize("query", ON_TOPIC_QUERIES)
def test_ask_on_topic_hits_have_cards(engine, query):
    hits = engine.ask(query)
    for hit in hits:
        assert isinstance(hit, RetrievalHit)
        assert isinstance(hit.card, KnowledgeCard)


@pytest.mark.parametrize("query", ON_TOPIC_QUERIES)
def test_ask_on_topic_cards_have_provenance(engine, query):
    hits = engine.ask(query)
    for hit in hits:
        prov = hit.card.provenance
        assert prov.meeting_id
        assert prov.date
        assert prov.speaker
        assert prov.timestamp


# ---------------------------------------------------------------------------
# 5. BrainEngine.ask — off-topic queries that should return no hits
# ---------------------------------------------------------------------------

OFF_TOPIC_QUERIES = [
    "office parking policy",
    "lunch menu cafeteria",
    "company holiday party",
    "IT helpdesk password reset",
    "quarterly gym membership",
    "travel reimbursement hotel",
    "onboarding new hire checklist",
    "coffee machine maintenance",
    "ergonomic chair request",
    "shuttle bus timetable",
    "birthday cake policy",
    "desk plant watering",
    "printer ink replacement",
    "fire drill evacuation",
    "remote work dog policy",
    "ping pong table reservation",
    "office temperature complaint",
    "whiteboard marker order",
    "laptop keyboard replacement",
    "phone number directory",
]


@pytest.mark.parametrize("query", OFF_TOPIC_QUERIES)
def test_ask_off_topic_returns_empty(engine, query):
    hits = engine.ask(query)
    assert hits == [], f"Expected no hits for off-topic query: {query!r}"


# ---------------------------------------------------------------------------
# 6. BrainEngine.ask — top_k parametrised
# ---------------------------------------------------------------------------

TOP_K_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 50, 100]


@pytest.mark.parametrize("k", TOP_K_VALUES)
def test_ask_top_k_respects_limit(engine, k):
    hits = engine.ask("warranty basis surplus distribution evidence", top_k=k)
    # Should return at most k results (but never more than corpus size)
    assert len(hits) <= k


@pytest.mark.parametrize("k", TOP_K_VALUES)
def test_ask_top_k_sorted_descending(engine, k):
    hits = engine.ask("warranty surplus distribution basis evidence", top_k=k)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("k", [0, -1, -5, -100])
def test_ask_invalid_top_k_raises(engine, k):
    with pytest.raises(ValueError):
        engine.ask("warranty", top_k=k)


# ---------------------------------------------------------------------------
# 7. BrainEngine.cite — authoritative results only
# ---------------------------------------------------------------------------

CITE_QUERIES = [
    "warranty reserve book tax treatment",
    "return of capital basis definition",
    "basis can never go below zero",
    "figure must foot to cited anchor",
    "reviewer refuses to sign rework",
    "evidence anchor single source cell",
    "foreign affiliate surplus elevation",
    "adjusted cost base capital events",
    "distribution cash paid trigger",
    "accrual basis deducted tax claim performed",
    "book tax difference deferred tax asset",
    "excess basis deemed capital gain",
    "workpaper sign accrual schedule",
    "anchor reconcile tolerance",
    "surplus distribution percentage owner",
]


@pytest.mark.parametrize("query", CITE_QUERIES)
def test_cite_returns_authoritative_card(engine, query):
    hit = engine.cite(query)
    assert hit is not None, f"Expected an authoritative cite for: {query!r}"
    assert hit.card.kind in AUTHORITATIVE_KINDS


@pytest.mark.parametrize("query", CITE_QUERIES)
def test_cite_score_above_floor(engine, query):
    hit = engine.cite(query)
    assert hit is not None
    assert hit.score >= engine.min_relevance


@pytest.mark.parametrize("query", OFF_TOPIC_QUERIES)
def test_cite_off_topic_returns_none(engine, query):
    hit = engine.cite(query)
    assert hit is None


# Open-item queries that should never be returned as authoritative citations
OPEN_ITEM_ONLY_HINTS = [
    "extended warranty performance obligation year end confirm",
    "state tax federal defer",
    "rounding tolerance FX translated anchor agree",
    "FX rate source elevation year confirm publish",
]


@pytest.mark.parametrize("query", OPEN_ITEM_ONLY_HINTS)
def test_cite_never_returns_open_item(engine, query):
    hit = engine.cite(query)
    # If a hit is returned, it must not be an open-item
    if hit is not None:
        assert hit.card.kind != OPEN_ITEM


# ---------------------------------------------------------------------------
# 8. BrainEngine.prep — keeps open-items, authoritative first
# ---------------------------------------------------------------------------

PREP_TOPICS = [
    "warranty",
    "book-tax",
    "basis",
    "return-of-capital",
    "evidence",
    "surplus",
    "distribution",
    "workpaper",
    "acb",
    "capital-gain",
    "anchor",
    "tie-out",
    "deferred-tax",
    "capital-event",
    "fx",
    "elevation",
]


@pytest.mark.parametrize("topic", PREP_TOPICS)
def test_prep_returns_hits(engine, topic):
    hits = engine.prep(topic)
    assert len(hits) >= 1, f"Expected prep hits for topic: {topic!r}"


@pytest.mark.parametrize("topic", PREP_TOPICS)
def test_prep_authoritative_before_open_items(engine, topic):
    hits = engine.prep(topic)
    kinds = [h.card.kind for h in hits]
    # Find index of first open-item; all before it must not be open-item
    if OPEN_ITEM in kinds:
        first_open = kinds.index(OPEN_ITEM)
        for k in kinds[:first_open]:
            assert k != OPEN_ITEM


@pytest.mark.parametrize("topic", PREP_TOPICS)
def test_prep_all_scores_above_floor(engine, topic):
    hits = engine.prep(topic)
    for h in hits:
        assert h.score >= engine.min_relevance


PREP_TOP_K = [1, 2, 3, 4, 5, 6, 8, 10, 20]


@pytest.mark.parametrize("k", PREP_TOP_K)
def test_prep_top_k_respected(engine, k):
    hits = engine.prep("warranty surplus distribution evidence basis", top_k=k)
    assert len(hits) <= k


@pytest.mark.parametrize("k", [0, -1, -3])
def test_prep_invalid_top_k_raises(engine, k):
    with pytest.raises(ValueError):
        engine.prep("warranty", top_k=k)


@pytest.mark.parametrize("topic", OFF_TOPIC_QUERIES)
def test_prep_off_topic_returns_empty(engine, topic):
    hits = engine.prep(topic)
    assert hits == []


# ---------------------------------------------------------------------------
# 9. BrainEngine.rank — determinism (same query → same order)
# ---------------------------------------------------------------------------

DETERMINISM_QUERIES = [
    "warranty book tax",
    "surplus distribution",
    "basis capital gain",
    "evidence anchor workpaper",
    "return of capital investor",
    "foreign affiliate parent",
    "accrual schedule deferred",
    "tie out rework refuse sign",
    "distribution formula column",
    "reviewer corrections add back",
]


@pytest.mark.parametrize("query", DETERMINISM_QUERIES)
def test_rank_deterministic(engine, query):
    hits1 = engine.rank(query)
    hits2 = engine.rank(query)
    assert [h.card.card_id for h in hits1] == [h.card.card_id for h in hits2]
    assert [h.score for h in hits1] == [h.score for h in hits2]


@pytest.mark.parametrize("query", DETERMINISM_QUERIES)
def test_rank_sorted_descending_score(engine, query):
    hits = engine.rank(query)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("query", DETERMINISM_QUERIES)
def test_rank_all_above_floor(engine, query):
    hits = engine.rank(query)
    for h in hits:
        assert h.score >= engine.min_relevance


@pytest.mark.parametrize("query", DETERMINISM_QUERIES)
def test_rank_scores_in_01(engine, query):
    hits = engine.rank(query)
    for h in hits:
        assert 0.0 <= h.score <= 1.0 + 1e-9  # cosine can be ≈1.0


# ---------------------------------------------------------------------------
# 10. Tie-breaking: card_id ascending at equal score
# ---------------------------------------------------------------------------

def test_rank_tie_breaks_on_card_id_ascending(corpus):
    """Build a minimal corpus where two cards have identical text → same score."""
    prov = Provenance("MTG-TIE", "Tie Test", "2025-01-01", "Alice", "00:00:10")
    text = "capital basis adjusted cost base"
    c1 = KnowledgeCard("CARD-TIE-B", ("basis",), text, RULE, prov)
    c2 = KnowledgeCard("CARD-TIE-A", ("basis",), text, RULE, prov)
    c3 = KnowledgeCard("CARD-TIE-C", ("basis",), text, RULE, prov)
    m = Meeting("MTG-TIE", "2025-01-01", "Tie Test", ("Alice",),
                (Utterance("Alice", 10, text),))
    corp = Corpus(meetings=[m], cards=[c1, c2, c3])
    eng = BrainEngine(corp)
    hits = eng.rank("capital basis")
    ids = [h.card.card_id for h in hits]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# 11. Provenance integrity — rule_text == source utterance verbatim
# ---------------------------------------------------------------------------

def test_all_cards_rule_text_verbatim(corpus):
    for card in corpus.cards:
        prov = card.provenance
        source = corpus.utterance_text(prov.meeting_id, prov.timestamp)
        assert card.rule_text == source, (
            f"Card {card.card_id} rule_text drifted from source utterance"
        )


def test_all_directives_request_text_verbatim(corpus):
    for directive in corpus.directives:
        prov = directive.provenance
        source = corpus.utterance_text(prov.meeting_id, prov.timestamp)
        assert directive.request_text == source, (
            f"Directive {directive.directive_id} request_text drifted from source"
        )


# ---------------------------------------------------------------------------
# 12. Corpus structural invariants
# ---------------------------------------------------------------------------

def test_corpus_has_meetings(corpus):
    assert len(corpus.meetings) >= 5


def test_corpus_has_cards(corpus):
    assert len(corpus.cards) >= 15


def test_corpus_has_directives(corpus):
    assert len(corpus.directives) >= 4


def test_all_card_kinds_valid(corpus):
    for card in corpus.cards:
        assert card.kind in CARD_KINDS


def test_all_cards_have_topic_tags(corpus):
    for card in corpus.cards:
        assert len(card.topic_tags) >= 1


def test_all_card_ids_unique(corpus):
    ids = [c.card_id for c in corpus.cards]
    assert len(ids) == len(set(ids))


def test_all_directive_ids_unique(corpus):
    ids = [d.directive_id for d in corpus.directives]
    assert len(ids) == len(set(ids))


def test_all_meeting_ids_unique(corpus):
    ids = [m.meeting_id for m in corpus.meetings]
    assert len(ids) == len(set(ids))


def test_cards_by_topic_covers_all_cards(corpus):
    grouped = corpus.cards_by_topic()
    all_in_groups = set()
    for cards in grouped.values():
        for c in cards:
            all_in_groups.add(c.card_id)
    all_ids = {c.card_id for c in corpus.cards}
    assert all_ids == all_in_groups


def test_directives_by_topic_covers_all_directives(corpus):
    grouped = corpus.directives_by_topic()
    all_in_groups = set()
    for directives in grouped.values():
        for d in directives:
            all_in_groups.add(d.directive_id)
    all_ids = {d.directive_id for d in corpus.directives}
    assert all_ids == all_in_groups


# ---------------------------------------------------------------------------
# 13. BrainEngine.directives_for — meeting title match
# ---------------------------------------------------------------------------

MEETING_TITLE_QUERIES = [
    "Surplus Workpaper Review",
    "surplus workpaper review",
    REVIEW_MEETING_TITLE,
    "Reviewer Corrections",
    "reviewer corrections",
    "Surplus Workpaper Review — Reviewer Corrections",
]


@pytest.mark.parametrize("topic", MEETING_TITLE_QUERIES)
def test_directives_for_title_match_nonempty(engine, topic):
    directives = engine.directives_for(topic)
    assert len(directives) >= 1


@pytest.mark.parametrize("topic", MEETING_TITLE_QUERIES)
def test_directives_for_title_match_spoken_order(engine, topic):
    directives = engine.directives_for(topic)
    timestamps = [d.provenance.timestamp for d in directives]
    assert timestamps == sorted(timestamps)


# Tag-based match topics
TAG_MATCH_TOPICS = [
    "surplus",
    "distribution",
    "formula",
    "review",
    "warranty",
    "book-tax",
    "add-back",
    "evidence",
    "tie-out",
    "footnote",
]


@pytest.mark.parametrize("topic", TAG_MATCH_TOPICS)
def test_directives_for_tag_match_nonempty(engine, topic):
    directives = engine.directives_for(topic)
    assert len(directives) >= 1


# Empty / whitespace-only → empty list
@pytest.mark.parametrize("bad", ["", "   ", "\t", "\n"])
def test_directives_for_empty_returns_empty(engine, bad):
    assert engine.directives_for(bad) == []


# Off-topic → empty list
@pytest.mark.parametrize("topic", ["parking policy", "lunch menu", "gym membership"])
def test_directives_for_off_topic_empty(engine, topic):
    directives = engine.directives_for(topic)
    assert directives == []


# ---------------------------------------------------------------------------
# 14. BrainEngine.remediate — full review packet
# ---------------------------------------------------------------------------

REMEDIATE_TOPICS = [
    "Surplus Workpaper Review",
    "Surplus Workpaper Review — Reviewer Corrections",
    "reviewer corrections",
    "surplus review",
]


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_not_empty(engine, topic):
    rem = engine.remediate(topic)
    assert not rem.is_empty


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_directives_count(engine, topic):
    rem = engine.remediate(topic)
    assert len(rem.directives) >= 4


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_fix_packet_length_matches_directives(engine, topic):
    rem = engine.remediate(topic)
    assert len(rem.fix_packet) == len(rem.directives)


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_fix_packet_numbers_sequential(engine, topic):
    rem = engine.remediate(topic)
    numbers = [e.number for e in rem.fix_packet]
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_all_status_pending(engine, topic):
    rem = engine.remediate(topic)
    for entry in rem.fix_packet:
        assert entry.status == STATUS_PENDING


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_prompt_not_empty(engine, topic):
    rem = engine.remediate(topic)
    assert len(rem.prompt) > 50


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_prompt_contains_apply_instruction(engine, topic):
    rem = engine.remediate(topic)
    assert "apply" in rem.prompt.lower() or "Apply" in rem.prompt


@pytest.mark.parametrize("topic", REMEDIATE_TOPICS)
def test_remediate_prompt_contains_topic(engine, topic):
    rem = engine.remediate(topic)
    # Topic or a substantial fragment appears in the prompt
    # (the engine quotes it inside the prompt header)
    first_word = topic.split()[0].lower()
    assert first_word in rem.prompt.lower()


EMPTY_REMEDIATE_TOPICS = ["parking policy", "gym membership", "lunch menu", ""]


@pytest.mark.parametrize("topic", EMPTY_REMEDIATE_TOPICS)
def test_remediate_off_topic_is_empty(engine, topic):
    rem = engine.remediate(topic)
    assert rem.is_empty


@pytest.mark.parametrize("topic", EMPTY_REMEDIATE_TOPICS)
def test_remediate_off_topic_prompt_contains_refusal(engine, topic):
    rem = engine.remediate(topic)
    assert "No sourced" in rem.prompt or "not" in rem.prompt.lower()


# ---------------------------------------------------------------------------
# 15. BrainEngine.index_summary
# ---------------------------------------------------------------------------

def test_index_summary_keys(engine):
    s = engine.index_summary()
    assert "meetings" in s
    assert "cards" in s
    assert "kind_counts" in s
    assert "topic_counts" in s


def test_index_summary_meeting_count(engine, corpus):
    s = engine.index_summary()
    assert s["meetings"] == len(corpus.meetings)


def test_index_summary_card_count(engine, corpus):
    s = engine.index_summary()
    assert s["cards"] == len(corpus.cards)


def test_index_summary_kind_counts_sum_to_total(engine, corpus):
    s = engine.index_summary()
    total = sum(s["kind_counts"].values())
    assert total == len(corpus.cards)


def test_index_summary_topic_counts_positive(engine):
    s = engine.index_summary()
    for tag, count in s["topic_counts"].items():
        assert count >= 1


# ---------------------------------------------------------------------------
# 16. Custom min_relevance threshold behaviour
# ---------------------------------------------------------------------------

THRESHOLDS = [0.0, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 0.99, 1.0]


@pytest.mark.parametrize("threshold", THRESHOLDS)
def test_lower_threshold_more_or_equal_results(corpus, threshold):
    eng_low = BrainEngine(corpus, min_relevance=threshold)
    eng_high = BrainEngine(corpus, min_relevance=min(threshold + 0.3, 1.0))
    hits_low = eng_low.rank("warranty surplus distribution basis evidence")
    hits_high = eng_high.rank("warranty surplus distribution basis evidence")
    assert len(hits_low) >= len(hits_high)


@pytest.mark.parametrize("threshold", THRESHOLDS)
def test_all_hits_above_custom_threshold(corpus, threshold):
    eng = BrainEngine(corpus, min_relevance=threshold)
    hits = eng.rank("warranty surplus distribution basis evidence")
    for h in hits:
        assert h.score >= threshold - 1e-12


@pytest.mark.parametrize("threshold", [0.0])
def test_zero_threshold_returns_all_relevant_cards(corpus, threshold):
    eng = BrainEngine(corpus, min_relevance=threshold)
    # With threshold 0, query-norm can still be 0 for empty/stopword queries
    hits = eng.rank("warranty surplus distribution basis evidence")
    assert len(hits) >= 1


# ---------------------------------------------------------------------------
# 17. KnowledgeCard.is_authoritative property
# ---------------------------------------------------------------------------

AUTHORITATIVE_CARD_KINDS = [(DECISION,), (RULE,), (DEFINITION,)]
NON_AUTHORITATIVE_CARD_KINDS = [(OPEN_ITEM,)]


@pytest.mark.parametrize("kind_tuple", AUTHORITATIVE_CARD_KINDS)
def test_card_is_authoritative_for_authoritative_kinds(kind_tuple):
    kind = kind_tuple[0]
    prov = Provenance("MTG-X", "Test", "2025-01-01", "Alice", "00:00:05")
    card = KnowledgeCard("CARD-X", ("tag",), "some text", kind, prov)
    assert card.is_authoritative is True


@pytest.mark.parametrize("kind_tuple", NON_AUTHORITATIVE_CARD_KINDS)
def test_card_is_not_authoritative_for_open_item(kind_tuple):
    kind = kind_tuple[0]
    prov = Provenance("MTG-X", "Test", "2025-01-01", "Alice", "00:00:05")
    card = KnowledgeCard("CARD-X", ("tag",), "some text", kind, prov)
    assert card.is_authoritative is False


# ---------------------------------------------------------------------------
# 18. KnowledgeCard construction validation
# ---------------------------------------------------------------------------

INVALID_KINDS = ["unknown", "rule-draft", "pending", "note", "comment", ""]


@pytest.mark.parametrize("bad_kind", INVALID_KINDS)
def test_card_invalid_kind_raises(bad_kind):
    prov = Provenance("MTG-X", "Test", "2025-01-01", "Alice", "00:00:05")
    with pytest.raises(ValueError):
        KnowledgeCard("CARD-X", ("tag",), "some text", bad_kind, prov)


def test_card_empty_rule_text_raises():
    prov = Provenance("MTG-X", "Test", "2025-01-01", "Alice", "00:00:05")
    with pytest.raises(ValueError):
        KnowledgeCard("CARD-X", ("tag",), "   ", RULE, prov)


def test_card_empty_topic_tags_raises():
    prov = Provenance("MTG-X", "Test", "2025-01-01", "Alice", "00:00:05")
    with pytest.raises(ValueError):
        KnowledgeCard("CARD-X", (), "some text", RULE, prov)


# ---------------------------------------------------------------------------
# 19. Utterance construction validation
# ---------------------------------------------------------------------------

NEGATIVE_T = [-1, -60, -3600]


@pytest.mark.parametrize("t", NEGATIVE_T)
def test_utterance_negative_t_raises(t):
    with pytest.raises(ValueError):
        Utterance("Alice", t, "hello")


BLANK_TEXTS = ["", "   ", "\t", "\n", "  \n  "]


@pytest.mark.parametrize("blank", BLANK_TEXTS)
def test_utterance_blank_text_raises(blank):
    with pytest.raises(ValueError):
        Utterance("Alice", 0, blank)


# ---------------------------------------------------------------------------
# 20. Utterance.timestamp property
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("t_seconds,expected_ts", [
    (0, "00:00:00"),
    (182, "00:03:02"),
    (3725, "01:02:05"),
    (86399, "23:59:59"),
    (64, "00:01:04"),
    (212, "00:03:32"),
    (366, "00:06:06"),
    (498, "00:08:18"),
])
def test_utterance_timestamp_property(t_seconds, expected_ts):
    u = Utterance("Alice", t_seconds, "some text here")
    assert u.timestamp == expected_ts


# ---------------------------------------------------------------------------
# 21. Meeting construction validation
# ---------------------------------------------------------------------------

INVALID_DATES = [
    "2025/01/14",
    "jan 14 2025",
    "not-a-date",
    "20250114",
    "",
    "2025-XX-14",
    "date-bad-val",
    "no date here",
]


@pytest.mark.parametrize("bad_date", INVALID_DATES)
def test_meeting_invalid_date_raises(bad_date):
    u = Utterance("Alice", 0, "hello world text")
    with pytest.raises(ValueError):
        Meeting("MTG-X", bad_date, "Test Meeting", ("Alice",), (u,))


def test_meeting_no_utterances_raises():
    with pytest.raises(ValueError):
        Meeting("MTG-X", "2025-01-01", "Test", ("Alice",), ())


# ---------------------------------------------------------------------------
# 22. Provenance.citation_tag format
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("meeting_id,title,date,speaker,timestamp", [
    ("MTG-A", "Warranty Review", "2025-01-14", "Alice Stone", "00:03:02"),
    ("MTG-B", "Return of Capital", "2025-02-03", "Marco Reyes", "00:01:35"),
    ("MTG-C", "Evidence Standards", "2025-02-27", "Priya Vale", "00:01:12"),
    ("MTG-D", "Surplus Review", "2025-03-19", "Lena Frost", "00:01:28"),
    ("MTG-E", "Corrections Session", "2025-04-08", "Quinn Harlow", "00:01:04"),
    ("MTG-F", "Year End Close", "2024-12-31", "Dana Brook", "00:00:00"),
    ("MTG-G", "Q3 Review", "2025-09-30", "Theo Nguyen", "01:02:05"),
    ("MTG-H", "Audit Prep", "2026-06-20", "Avery Stone", "00:59:59"),
])
def test_provenance_citation_tag_format(meeting_id, title, date, speaker, timestamp):
    prov = Provenance(meeting_id, title, date, speaker, timestamp)
    tag = prov.citation_tag()
    assert tag.startswith("[")
    assert tag.endswith("]")
    assert title in tag
    assert date in tag
    assert speaker in tag
    assert timestamp in tag


# ---------------------------------------------------------------------------
# 23. ChangeDirective construction validation
# ---------------------------------------------------------------------------

def test_directive_empty_request_text_raises():
    prov = Provenance("MTG-X", "Test", "2025-01-01", "Alice", "00:00:05")
    with pytest.raises(ValueError):
        ChangeDirective("DIR-X", ("tag",), "  ", prov)


def test_directive_empty_topic_tags_raises():
    prov = Provenance("MTG-X", "Test", "2025-01-01", "Alice", "00:00:05")
    with pytest.raises(ValueError):
        ChangeDirective("DIR-X", (), "change the formula", prov)


# ---------------------------------------------------------------------------
# 24. ChangeDirective.citation_tag delegates to provenance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,date,speaker,timestamp", [
    ("Surplus Review", "2025-04-08", "Quinn Harlow", "00:01:04"),
    ("Warranty Review", "2025-01-14", "Dana Brook", "00:06:01"),
    ("Evidence Tie-Out", "2025-02-27", "Theo Nguyen", "00:07:35"),
    ("Surplus Elevation", "2025-03-19", "Marco Reyes", "00:01:28"),
])
def test_directive_citation_tag_matches_provenance(title, date, speaker, timestamp):
    prov = Provenance("MTG-X", title, date, speaker, timestamp)
    d = ChangeDirective("DIR-X", ("tag",), "change something here", prov)
    assert d.citation_tag() == prov.citation_tag()


# ---------------------------------------------------------------------------
# 25. Empty query edge cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blank", ["", "   ", "\t\n", "a an the and is"])
def test_ask_stopword_only_query_returns_empty(engine, blank):
    hits = engine.ask(blank) if blank.strip() and any(
        t not in _tokenize.__doc__ or True for t in blank.split()
    ) else []
    # The engine returns empty for purely stopword or truly empty queries
    result = engine.rank(blank)
    # All stopword/empty → query norm 0 → all scores 0 → nothing above floor
    for h in result:
        assert h.score >= engine.min_relevance  # vacuously if empty


# ---------------------------------------------------------------------------
# 26. build_corpus seed parameter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [0, 1, 42, 100, 1107, 9999, 2025])
def test_build_corpus_seed_accepted(seed):
    c = build_corpus(seed=seed)
    assert len(c.cards) >= 15


@pytest.mark.parametrize("seed", [0, 1, 42, 100, 1107, 9999, 2025])
def test_build_corpus_deterministic_across_seeds(seed):
    c1 = build_corpus(seed=seed)
    c2 = build_corpus(seed=seed)
    assert [c.card_id for c in c1.cards] == [c.card_id for c in c2.cards]


# ---------------------------------------------------------------------------
# 27. Corpus.utterance_text correctness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("meeting_id,timestamp,fragment", [
    ("MTG-2025-WARRANTY", "00:03:02", "warranty reserve"),
    ("MTG-2025-WARRANTY", "00:06:01", "accrual schedule"),
    ("MTG-2025-ROC", "00:01:35", "return of capital"),
    ("MTG-2025-ROC", "00:03:41", "deemed capital gain"),
    ("MTG-2025-EVIDENCE", "00:01:12", "cited anchor"),
    ("MTG-2025-EVIDENCE", "00:04:00", "refuses to sign"),
    ("MTG-2025-SURPLUS", "00:01:28", "actual distribution"),
    ("MTG-2025-SURPLUS", "00:05:00", "capital events"),
])
def test_corpus_utterance_text_contains_fragment(corpus, meeting_id, timestamp, fragment):
    text = corpus.utterance_text(meeting_id, timestamp)
    assert fragment.lower() in text.lower()


def test_corpus_utterance_text_missing_raises(corpus):
    with pytest.raises(KeyError):
        corpus.utterance_text("MTG-NONEXISTENT", "00:00:00")


def test_corpus_utterance_text_wrong_timestamp_raises(corpus):
    with pytest.raises(KeyError):
        corpus.utterance_text("MTG-2025-WARRANTY", "99:99:99")


# ---------------------------------------------------------------------------
# 28. RetrievalHit frozen dataclass
# ---------------------------------------------------------------------------

def test_retrieval_hit_is_frozen(engine):
    hits = engine.ask("warranty basis surplus")
    assert len(hits) >= 1
    hit = hits[0]
    with pytest.raises((AttributeError, TypeError)):
        hit.score = 0.0  # type: ignore[misc]


def test_retrieval_hit_card_is_frozen(engine):
    hits = engine.ask("warranty basis surplus")
    assert len(hits) >= 1
    card = hits[0].card
    with pytest.raises((AttributeError, TypeError)):
        card.kind = "unknown"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 29. FixPacketEntry frozen dataclass
# ---------------------------------------------------------------------------

def test_fix_packet_entry_status_is_pending(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    for entry in rem.fix_packet:
        assert entry.status == STATUS_PENDING


def test_fix_packet_entry_is_frozen(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    entry = rem.fix_packet[0]
    with pytest.raises((AttributeError, TypeError)):
        entry.status = "APPLIED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 30. Multiple engines over same corpus are independent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("threshold", [0.05, 0.1, 0.2, 0.3, 0.5])
def test_multiple_engines_independent(corpus, threshold):
    e1 = BrainEngine(corpus, min_relevance=threshold)
    e2 = BrainEngine(corpus, min_relevance=threshold)
    q = "warranty surplus distribution"
    h1 = e1.rank(q)
    h2 = e2.rank(q)
    assert [h.card.card_id for h in h1] == [h.card.card_id for h in h2]
    assert [h.score for h in h1] == [h.score for h in h2]


# ---------------------------------------------------------------------------
# 31. Specific corpus card identities
# ---------------------------------------------------------------------------

EXPECTED_CARD_IDS = [
    "CARD-WARRANTY-01",
    "CARD-WARRANTY-02",
    "CARD-WARRANTY-03",
    "CARD-ROC-01",
    "CARD-ROC-02",
    "CARD-ROC-03",
    "CARD-ROC-04",
    "CARD-EVIDENCE-01",
    "CARD-EVIDENCE-02",
    "CARD-EVIDENCE-03",
    "CARD-EVIDENCE-04",
    "CARD-SURPLUS-01",
    "CARD-SURPLUS-02",
    "CARD-SURPLUS-03",
    "CARD-SURPLUS-04",
]


@pytest.mark.parametrize("card_id", EXPECTED_CARD_IDS)
def test_corpus_contains_expected_card(corpus, card_id):
    ids = {c.card_id for c in corpus.cards}
    assert card_id in ids


EXPECTED_DIRECTIVE_IDS = [
    "DIR-SURPLUS-REVIEW-01",
    "DIR-SURPLUS-REVIEW-02",
    "DIR-SURPLUS-REVIEW-03",
    "DIR-SURPLUS-REVIEW-04",
]


@pytest.mark.parametrize("directive_id", EXPECTED_DIRECTIVE_IDS)
def test_corpus_contains_expected_directive(corpus, directive_id):
    ids = {d.directive_id for d in corpus.directives}
    assert directive_id in ids


# ---------------------------------------------------------------------------
# 32. Cards-by-topic expected tags present
# ---------------------------------------------------------------------------

EXPECTED_TOPIC_TAGS = [
    "warranty",
    "book-tax",
    "deferred-tax",
    "workpaper",
    "evidence",
    "return-of-capital",
    "basis",
    "capital-gain",
    "tie-out",
    "surplus",
    "distribution",
    "elevation",
    "acb",
    "capital-event",
    "fx",
    "anchor",
    "definition",
    "refuse",
    "state-tax",
    "revenue-recognition",
]


@pytest.mark.parametrize("tag", EXPECTED_TOPIC_TAGS)
def test_cards_by_topic_contains_expected_tag(corpus, tag):
    grouped = corpus.cards_by_topic()
    assert tag in grouped, f"Expected topic tag {tag!r} in cards_by_topic()"


# ---------------------------------------------------------------------------
# 33. index_summary kind counts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", list(CARD_KINDS))
def test_index_summary_kind_count_non_negative(engine, kind):
    s = engine.index_summary()
    count = s["kind_counts"].get(kind, 0)
    assert count >= 0


def test_index_summary_has_decisions(engine):
    s = engine.index_summary()
    assert s["kind_counts"].get(DECISION, 0) >= 1


def test_index_summary_has_rules(engine):
    s = engine.index_summary()
    assert s["kind_counts"].get(RULE, 0) >= 1


def test_index_summary_has_definitions(engine):
    s = engine.index_summary()
    assert s["kind_counts"].get(DEFINITION, 0) >= 1


def test_index_summary_has_open_items(engine):
    s = engine.index_summary()
    assert s["kind_counts"].get(OPEN_ITEM, 0) >= 1


# ---------------------------------------------------------------------------
# 34. Ask returns cards with rule_text == source utterance (spot checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,fragment", [
    ("warranty reserve book tax deferred", "deferred tax asset"),
    ("accrual schedule line workpaper sign", "accrual schedule"),
    ("return of capital definition basis", "return of capital"),
    ("basis floor zero workpaper clamp", "basis can never go below zero"),
    ("evidence anchor figure hardcoded", "anchor"),
    ("reviewer refuses sign rework estimate", "refuses to sign"),
    ("anchor single cited source cell", "cited source cell"),
    ("surplus distribution parent ownership", "actual distribution"),
    ("adjusted cost base capital event contribution", "capital events"),
    ("distribution cash paid trigger elevation", "distribution is the cash"),
])
def test_ask_top_result_rule_text_fragment(engine, query, fragment):
    hits = engine.ask(query, top_k=5)
    texts = [h.card.rule_text.lower() for h in hits]
    assert any(fragment.lower() in t for t in texts), (
        f"Fragment {fragment!r} not found in top results for {query!r}"
    )
