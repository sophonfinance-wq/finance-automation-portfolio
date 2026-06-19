"""Additional coverage for the retrieval engine: tokenizer behaviour, the
relevance floor, ranking invariants, top_k boundaries, cite/prep governance,
directive resolution paths, and generation-spec integrity.

Every test exercises real ``brain_engine.engine`` / ``brain_engine.generate``
code and pins behaviour observed from the actual implementation.
"""

from __future__ import annotations

import pytest

from brain_engine.engine import (
    MIN_RELEVANCE,
    STATUS_PENDING,
    BrainEngine,
    RetrievalHit,
    _tokenize,
)
from brain_engine.generate import (
    DEFAULT_SEED,
    REVIEW_MEETING_TITLE,
    build_corpus,
)
from brain_engine.model import AUTHORITATIVE_KINDS, OPEN_ITEM


def _engine(min_relevance: float = MIN_RELEVANCE):
    return BrainEngine(build_corpus(), min_relevance=min_relevance)


# --- tokenizer -------------------------------------------------------------
@pytest.mark.parametrize(
    "text, expected",
    [
        ("warranty reserve", ["warranty", "reserve"]),
        ("THE AND OF", []),  # pure stopwords -> empty
        ("Book-Tax", ["book", "tax", "book-tax"]),  # hyphen compound preserved
        ("Hello, World!", ["hello", "world"]),  # punctuation stripped
        ("a1 b2", ["a1", "b2"]),  # alphanumerics kept
        ("", []),
        ("   ", []),
    ],
)
def test_tokenize_table(text, expected) -> None:
    assert _tokenize(text) == expected


def test_tokenize_lowercases() -> None:
    assert _tokenize("WARRANTY") == ["warranty"]


def test_tokenize_drops_stopwords_but_keeps_content() -> None:
    toks = _tokenize("the warranty is in the workpaper")
    assert "the" not in toks
    assert "is" not in toks
    assert "in" not in toks
    assert "warranty" in toks
    assert "workpaper" in toks


def test_tokenize_multi_hyphen_compound() -> None:
    toks = _tokenize("return-of-capital")
    assert "return-of-capital" in toks
    assert "return" in toks and "capital" in toks


# --- relevance floor governance -------------------------------------------
def test_rank_respects_relevance_floor() -> None:
    engine = _engine()
    for hit in engine.rank("warranty book-tax workpaper"):
        assert hit.score >= engine.min_relevance


def test_floor_of_one_refuses_everything() -> None:
    engine = _engine(min_relevance=1.0)
    assert engine.rank("warranty book-tax deferred tax") == []
    assert engine.ask("warranty book-tax deferred tax") == []
    assert engine.cite("warranty book-tax deferred tax") is None


def test_lower_floor_returns_at_least_as_many_hits() -> None:
    q = "surplus distribution elevation"
    high = len(_engine(min_relevance=0.20).rank(q))
    low = len(_engine(min_relevance=0.01).rank(q))
    assert low >= high


def test_empty_query_yields_no_hits() -> None:
    engine = _engine()
    assert engine.rank("") == []
    assert engine.ask("") == []
    assert engine.cite("") is None
    assert engine.prep("") == []


def test_pure_stopword_query_refuses() -> None:
    engine = _engine()
    assert engine.rank("the and of to with") == []


# --- ranking invariants ----------------------------------------------------
def test_rank_is_sorted_descending_by_score() -> None:
    hits = _engine().rank("surplus distribution")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_rank_ties_break_on_card_id_ascending() -> None:
    hits = _engine().rank("workpaper evidence basis")
    # For any equal-score adjacent pair, card_id must be ascending.
    for a, b in zip(hits, hits[1:]):
        if a.score == b.score:
            assert a.card.card_id < b.card.card_id


def test_rank_returns_retrieval_hit_objects() -> None:
    hits = _engine().rank("warranty")
    assert hits
    assert all(isinstance(h, RetrievalHit) for h in hits)
    assert all(0.0 < h.score <= 1.0 for h in hits)


def test_ask_is_prefix_of_rank() -> None:
    engine = _engine()
    q = "return of capital beyond basis"
    full = [h.card.card_id for h in engine.rank(q)]
    top3 = [h.card.card_id for h in engine.ask(q, top_k=3)]
    assert top3 == full[:3]


@pytest.mark.parametrize("top_k", [1, 2, 3, 5, 100])
def test_ask_respects_top_k_cap(top_k) -> None:
    engine = _engine()
    hits = engine.ask("warranty book-tax evidence basis surplus", top_k=top_k)
    assert len(hits) <= top_k


@pytest.mark.parametrize("bad", [0, -1, -10])
def test_ask_rejects_non_positive_top_k(bad) -> None:
    with pytest.raises(ValueError):
        _engine().ask("warranty", top_k=bad)


@pytest.mark.parametrize("bad", [0, -1, -10])
def test_prep_rejects_non_positive_top_k(bad) -> None:
    with pytest.raises(ValueError):
        _engine().prep("warranty", top_k=bad)


# --- cite governance: authoritative only ----------------------------------
def test_cite_returns_first_authoritative_in_rank_order() -> None:
    engine = _engine()
    q = "return of capital in excess of basis is a deemed gain"
    ranked = engine.rank(q)
    hit = engine.cite(q)
    expected = next((h for h in ranked if h.card.kind in AUTHORITATIVE_KINDS), None)
    assert hit is not None and expected is not None
    assert hit.card.card_id == expected.card.card_id


def test_cite_skips_open_item_even_if_top_ranked() -> None:
    engine = _engine()
    hit = engine.cite("confirm the FX rate source for the elevation year")
    if hit is not None:
        assert hit.card.kind != OPEN_ITEM


# --- prep ordering: settled before open, top_k cap ------------------------
def test_prep_orders_open_items_last() -> None:
    hits = _engine().prep("surplus distribution acb")
    kinds = [h.card.kind for h in hits]
    if OPEN_ITEM in kinds:
        idx = kinds.index(OPEN_ITEM)
        assert all(k == OPEN_ITEM for k in kinds[idx:])


@pytest.mark.parametrize("top_k", [1, 2, 4, 6])
def test_prep_respects_top_k(top_k) -> None:
    hits = _engine().prep("warranty reserve book-tax evidence basis surplus", top_k=top_k)
    assert len(hits) <= top_k


def test_prep_can_include_open_item_unlike_cite() -> None:
    # Prep keeps open-items; cite never does. Pick a topic with an open item.
    engine = _engine()
    prep_kinds = {h.card.kind for h in engine.prep("warranty reserve book-tax")}
    assert prep_kinds  # non-empty
    # At least one settled position should be present.
    assert prep_kinds - {OPEN_ITEM}


# --- determinism across fresh engines -------------------------------------
def test_two_engines_rank_identically() -> None:
    q = "evidence tie-out anchor workpaper"
    a = [(h.card.card_id, round(h.score, 9)) for h in _engine().rank(q)]
    b = [(h.card.card_id, round(h.score, 9)) for h in _engine().rank(q)]
    assert a == b


def test_seed_argument_does_not_change_corpus() -> None:
    # build_corpus accepts a seed for API parity; corpus is hand-authored.
    a = [c.card_id for c in build_corpus(seed=1).cards]
    b = [c.card_id for c in build_corpus(seed=999).cards]
    assert a == b == [c.card_id for c in build_corpus(seed=DEFAULT_SEED).cards]


# --- directive resolution paths -------------------------------------------
def test_directives_for_title_match_full_set_in_order() -> None:
    engine = _engine()
    ids = [d.directive_id for d in engine.directives_for(REVIEW_MEETING_TITLE)]
    assert ids == [
        "DIR-SURPLUS-REVIEW-01",
        "DIR-SURPLUS-REVIEW-02",
        "DIR-SURPLUS-REVIEW-03",
        "DIR-SURPLUS-REVIEW-04",
    ]


def test_directives_for_is_case_insensitive() -> None:
    engine = _engine()
    lower = [d.directive_id for d in engine.directives_for("surplus workpaper review")]
    upper = [d.directive_id for d in engine.directives_for("SURPLUS WORKPAPER REVIEW")]
    assert lower == upper
    assert lower  # non-empty


def test_directives_for_tag_match_single_topic() -> None:
    engine = _engine()
    # 'footnote' is a tag only on directive 03; no title contains it.
    ids = [d.directive_id for d in engine.directives_for("footnote")]
    assert ids == ["DIR-SURPLUS-REVIEW-03"]


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_directives_for_blank_topic_returns_empty(blank) -> None:
    assert _engine().directives_for(blank) == []


def test_directives_for_unknown_topic_returns_empty() -> None:
    assert _engine().directives_for("cafeteria menu rotation") == []


def test_order_directives_is_total_and_stable() -> None:
    engine = _engine()
    directives = engine.directives_for(REVIEW_MEETING_TITLE)
    keyed = [
        (d.provenance.meeting_id, d.provenance.timestamp, d.directive_id)
        for d in directives
    ]
    assert keyed == sorted(keyed)


# --- remediate packet integrity -------------------------------------------
def test_remediate_fix_packet_numbers_are_one_based_sequential() -> None:
    rem = _engine().remediate(REVIEW_MEETING_TITLE)
    assert [e.number for e in rem.fix_packet] == list(range(1, len(rem.directives) + 1))


def test_remediate_fix_packet_all_pending() -> None:
    rem = _engine().remediate(REVIEW_MEETING_TITLE)
    assert all(e.status == STATUS_PENDING for e in rem.fix_packet)


def test_remediate_empty_topic_is_empty_packet() -> None:
    rem = _engine().remediate("")
    assert rem.is_empty
    assert rem.directives == ()
    assert rem.fix_packet == ()


def test_remediate_prompt_refusal_text_when_empty() -> None:
    prompt = _engine().remediate("unrelated parking policy").prompt
    assert "Do not invent" in prompt
    assert "Changes to apply:" not in prompt


# --- index_summary integrity ----------------------------------------------
def test_index_summary_kind_counts_sum_to_card_total() -> None:
    engine = _engine()
    summary = engine.index_summary()
    assert sum(summary["kind_counts"].values()) == summary["cards"]


def test_index_summary_topic_counts_sorted_keys() -> None:
    topic_counts = _engine().index_summary()["topic_counts"]
    keys = list(topic_counts.keys())
    assert keys == sorted(keys)


def test_index_summary_meeting_count_matches_corpus() -> None:
    engine = _engine()
    assert engine.index_summary()["meetings"] == len(engine.corpus.meetings)


# --- generation integrity --------------------------------------------------
def test_every_card_id_is_unique() -> None:
    ids = [c.card_id for c in build_corpus().cards]
    assert len(ids) == len(set(ids))


def test_every_directive_id_is_unique() -> None:
    ids = [d.directive_id for d in build_corpus().directives]
    assert len(ids) == len(set(ids))


def test_all_meetings_have_utterances() -> None:
    for m in build_corpus().meetings:
        assert m.utterances  # __post_init__ enforces, but assert the property
