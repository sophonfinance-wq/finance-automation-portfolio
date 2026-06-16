"""The Knowledge Brain engine: deterministic retrieval with citation governance.

This is the "ingest -> query" stage. It builds a small, reproducible TF-IDF index
over the knowledge cards (stdlib ``math`` only — NO embeddings, NO external model,
NO network) and answers three query shapes:

* :meth:`BrainEngine.ask`     — top matching card(s) for a question,
* :meth:`BrainEngine.cite`    — the single best *authoritative* card,
* :meth:`BrainEngine.prep`    — the prior decisions / rules / open-items on a topic.

Governance is enforced here, not in the report layer:

* **Every answer carries a citation.** Each returned hit is a card with full
  provenance; the caller cannot get an answer without a source.
* **Refuse, do not guess.** If no card clears :data:`MIN_RELEVANCE`, ``ask`` and
  ``cite`` return *no* hits and the report layer prints the refusal banner. The
  brain never fabricates an answer.
* **Deterministic.** Fixed corpus -> identical scores and identical ranked order
  every run. Ties break on ``card_id`` so ordering is total and stable.
* **Provenance integrity.** Cite mode returns ``rule_text`` byte-identical to the
  source utterance; date, timestamp, and speaker always travel with the quote.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .model import AUTHORITATIVE_KINDS, OPEN_ITEM, Corpus, KnowledgeCard

# A card must clear this cosine-similarity score to be returned. Below it, the
# engine refuses rather than guessing. Tuned so off-topic questions (e.g.
# "office parking policy") score zero and are refused, while on-topic questions
# clear comfortably.
MIN_RELEVANCE = 0.05

# A small, deterministic stopword set so common words don't dominate scoring.
_STOPWORDS = frozenset(
    """
    a an and are as at be but by for from how if in into is it its of on or
    that the their to was were what when where which who why will with do does
    we you they this these those there here over only not no can must should
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords.

    Hyphenated topic tags like ``book-tax`` are also indexed whole (with the
    hyphen) so a query for ``book-tax`` matches the tag directly.
    """
    lowered = text.lower()
    tokens = [t for t in _TOKEN_RE.findall(lowered) if t not in _STOPWORDS]
    # Preserve hyphenated compounds present verbatim in the text.
    for compound in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+", lowered):
        if compound not in _STOPWORDS:
            tokens.append(compound)
    return tokens


@dataclass(frozen=True)
class RetrievalHit:
    """One scored card returned by retrieval, with its relevance score."""

    card: KnowledgeCard
    score: float


class BrainEngine:
    """A read-only, deterministic retrieval index over a :class:`Corpus`.

    The corpus is never mutated. The index is built once at construction.
    """

    def __init__(self, corpus: Corpus, min_relevance: float = MIN_RELEVANCE) -> None:
        self.corpus = corpus
        self.min_relevance = min_relevance
        self._doc_tokens: Dict[str, List[str]] = {}
        self._idf: Dict[str, float] = {}
        self._doc_vectors: Dict[str, Dict[str, float]] = {}
        self._doc_norms: Dict[str, float] = {}
        self._build_index()

    # ----------------------------------------------------------------- index
    def _card_document(self, card: KnowledgeCard) -> List[str]:
        """The token bag for a card: its tags (weighted) plus its rule text.

        Tags are repeated so an exact tag match ranks the obviously-best card
        first, which is the behaviour a reviewer expects from a topic query.
        """
        tokens: List[str] = []
        for tag in card.topic_tags:
            tokens.extend([tag] * 3)  # tag weight
            tokens.extend(_tokenize(tag))
        tokens.extend(_tokenize(card.rule_text))
        return tokens

    def _build_index(self) -> None:
        cards = self.corpus.cards
        n_docs = len(cards)
        df: Dict[str, int] = {}
        for card in cards:
            tokens = self._card_document(card)
            self._doc_tokens[card.card_id] = tokens
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1

        # Smoothed IDF so a term present in every doc still contributes a little.
        for term, freq in df.items():
            self._idf[term] = math.log((1 + n_docs) / (1 + freq)) + 1.0

        for card in cards:
            tokens = self._doc_tokens[card.card_id]
            tf: Dict[str, int] = {}
            for term in tokens:
                tf[term] = tf.get(term, 0) + 1
            vec = {term: count * self._idf.get(term, 0.0) for term, count in tf.items()}
            self._doc_vectors[card.card_id] = vec
            self._doc_norms[card.card_id] = math.sqrt(sum(v * v for v in vec.values()))

    def _query_vector(self, query: str) -> Tuple[Dict[str, float], float]:
        tf: Dict[str, int] = {}
        for term in _tokenize(query):
            tf[term] = tf.get(term, 0) + 1
        vec = {term: count * self._idf.get(term, 0.0) for term, count in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return vec, norm

    def _score(self, query_vec: Dict[str, float], query_norm: float, card_id: str) -> float:
        if query_norm == 0.0:
            return 0.0
        doc_vec = self._doc_vectors[card_id]
        doc_norm = self._doc_norms[card_id]
        if doc_norm == 0.0:
            return 0.0
        # Iterate the smaller vector for the dot product.
        if len(query_vec) <= len(doc_vec):
            dot = sum(weight * doc_vec.get(term, 0.0) for term, weight in query_vec.items())
        else:
            dot = sum(weight * query_vec.get(term, 0.0) for term, weight in doc_vec.items())
        return dot / (query_norm * doc_norm)

    # ----------------------------------------------------------------- query
    def rank(self, query: str) -> List[RetrievalHit]:
        """Score *every* card for ``query`` and return them best-first.

        Ranking is total and deterministic: sort by descending score, then by
        ``card_id`` ascending to break ties. Cards below the relevance floor are
        excluded — this is where the refuse-do-not-guess governance lives.
        """
        query_vec, query_norm = self._query_vector(query)
        scored: List[RetrievalHit] = []
        for card in self.corpus.cards:
            score = self._score(query_vec, query_norm, card.card_id)
            if score >= self.min_relevance:
                scored.append(RetrievalHit(card=card, score=score))
        scored.sort(key=lambda h: (-h.score, h.card.card_id))
        return scored

    def ask(self, query: str, top_k: int = 3) -> List[RetrievalHit]:
        """Return the top ``top_k`` relevant cards (possibly empty -> refusal)."""
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        return self.rank(query)[:top_k]

    def cite(self, assertion: str) -> RetrievalHit | None:
        """Return the single best *authoritative* card for a workpaper assertion.

        Open-items are never authority, so they are filtered out here even if they
        score well. Returns ``None`` when nothing authoritative clears the floor —
        the engine refuses to supply an unsourced citation.
        """
        for hit in self.rank(assertion):
            if hit.card.kind in AUTHORITATIVE_KINDS:
                return hit
        return None

    def prep(self, topic: str, top_k: int = 6) -> List[RetrievalHit]:
        """Return prior decisions / rules / definitions / open-items for a topic.

        Prep deliberately *keeps* open-items (a briefing should surface parked
        questions) and orders authoritative cards ahead of open-items at equal
        relevance so the settled positions read first.
        """
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        hits = self.rank(topic)[: top_k * 2]
        hits.sort(
            key=lambda h: (
                1 if h.card.kind == OPEN_ITEM else 0,  # open-items last
                -h.score,
                h.card.card_id,
            )
        )
        return hits[:top_k]

    # --------------------------------------------------------------- summary
    def index_summary(self) -> Dict[str, object]:
        """Counts for the bare-CLI brain index view."""
        kind_counts: Dict[str, int] = {}
        for card in self.corpus.cards:
            kind_counts[card.kind] = kind_counts.get(card.kind, 0) + 1
        topic_counts: Dict[str, int] = {}
        for tag, cards in self.corpus.cards_by_topic().items():
            topic_counts[tag] = len(cards)
        return {
            "meetings": len(self.corpus.meetings),
            "cards": len(self.corpus.cards),
            "kind_counts": kind_counts,
            "topic_counts": dict(sorted(topic_counts.items())),
        }
