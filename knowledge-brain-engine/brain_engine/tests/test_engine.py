"""Tests for retrieval determinism, ranking, citation governance, and refusal."""

from __future__ import annotations

from brain_engine.engine import BrainEngine
from brain_engine.generate import build_corpus
from brain_engine.model import AUTHORITATIVE_KINDS, OPEN_ITEM


def _engine():
    return BrainEngine(build_corpus())


# --- retrieval determinism ------------------------------------------------
def test_retrieval_is_deterministic_same_ranked_order() -> None:
    q = "return of capital beyond basis"
    a = [h.card.card_id for h in _engine().ask(q, top_k=5)]
    b = [h.card.card_id for h in _engine().ask(q, top_k=5)]
    assert a == b


def test_retrieval_scores_are_deterministic() -> None:
    q = "warranty book-tax"
    a = [(h.card.card_id, round(h.score, 6)) for h in _engine().rank(q)]
    b = [(h.card.card_id, round(h.score, 6)) for h in _engine().rank(q)]
    assert a == b


# --- keyword/tag scoring ranks the obviously-best card first --------------
def test_warranty_query_ranks_warranty_card_first() -> None:
    engine = _engine()
    top = engine.ask("warranty reserve book-tax deferred tax")[0]
    assert top.card.card_id == "CARD-WARRANTY-01"


def test_surplus_distribution_query_ranks_surplus_decision_first() -> None:
    engine = _engine()
    top = engine.ask("when does foreign affiliate surplus elevate to the parent")[0]
    assert top.card.card_id == "CARD-SURPLUS-01"


def test_evidence_anchor_query_ranks_evidence_card_first() -> None:
    engine = _engine()
    top = engine.ask("every figure must foot to a cited anchor")[0]
    assert top.card.card_id in {"CARD-EVIDENCE-01", "CARD-EVIDENCE-03"}


# --- every returned answer carries a citation -----------------------------
def test_every_ask_hit_carries_provenance() -> None:
    engine = _engine()
    hits = engine.ask("basis and return of capital", top_k=5)
    assert hits
    for hit in hits:
        prov = hit.card.provenance
        assert prov.date and prov.speaker and prov.timestamp and prov.title


# --- REFUSE behaviour when nothing is relevant ----------------------------
def test_ask_refuses_on_irrelevant_query() -> None:
    engine = _engine()
    assert engine.ask("office parking lunch holiday party policy") == []


def test_cite_refuses_on_irrelevant_query() -> None:
    engine = _engine()
    assert engine.cite("the weather forecast for next week") is None


def test_prep_refuses_on_irrelevant_topic() -> None:
    engine = _engine()
    assert engine.prep("cafeteria menu rotation") == []


def test_relevance_floor_excludes_below_threshold() -> None:
    engine = _engine()
    for hit in engine.rank("warranty"):
        assert hit.score >= engine.min_relevance


# --- cite mode: authoritative only, byte-identical ------------------------
def test_cite_returns_authoritative_card() -> None:
    engine = _engine()
    hit = engine.cite("return of capital in excess of basis is a deemed gain")
    assert hit is not None
    assert hit.card.kind in AUTHORITATIVE_KINDS


def test_cite_never_returns_open_item() -> None:
    engine = _engine()
    # A topic whose strongest match family includes an open item.
    hit = engine.cite("state treatment of return of capital")
    assert hit is None or hit.card.kind != OPEN_ITEM


def test_cite_text_is_byte_identical_to_source_utterance() -> None:
    engine = _engine()
    hit = engine.cite("return of capital in excess of basis is a deemed gain")
    assert hit is not None
    source = engine.corpus.utterance_text(
        hit.card.provenance.meeting_id, hit.card.provenance.timestamp
    )
    assert hit.card.rule_text == source


# --- prep mode: right decisions in, irrelevant ones out -------------------
def test_prep_includes_warranty_decision_for_warranty_topic() -> None:
    engine = _engine()
    ids = {h.card.card_id for h in engine.prep("warranty reserve book-tax treatment")}
    assert "CARD-WARRANTY-01" in ids


def test_prep_excludes_unrelated_surplus_card_for_warranty_topic() -> None:
    engine = _engine()
    ids = {h.card.card_id for h in engine.prep("warranty reserve book-tax treatment")}
    assert "CARD-SURPLUS-01" not in ids
    assert "CARD-ROC-02" not in ids


def test_prep_surfaces_open_items_after_settled_positions() -> None:
    engine = _engine()
    hits = engine.prep("warranty reserve book-tax treatment")
    kinds = [h.card.kind for h in hits]
    if OPEN_ITEM in kinds:
        first_open = kinds.index(OPEN_ITEM)
        # No settled (non-open) card may appear after the first open item.
        assert all(k == OPEN_ITEM for k in kinds[first_open:])


# --- index summary counts -------------------------------------------------
def test_index_summary_counts_match_corpus() -> None:
    engine = _engine()
    summary = engine.index_summary()
    assert summary["meetings"] == len(engine.corpus.meetings)
    assert summary["cards"] == len(engine.corpus.cards)
    assert sum(summary["kind_counts"].values()) == len(engine.corpus.cards)


def test_index_summary_topic_counts_nonempty() -> None:
    engine = _engine()
    topic_counts = engine.index_summary()["topic_counts"]
    assert topic_counts
    assert all(count >= 1 for count in topic_counts.values())


def test_read_only_corpus_not_mutated_by_queries() -> None:
    engine = _engine()
    before = len(engine.corpus.cards)
    engine.ask("warranty")
    engine.cite("basis")
    engine.prep("surplus")
    assert len(engine.corpus.cards) == before
