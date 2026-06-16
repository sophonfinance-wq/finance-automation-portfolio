"""Reporting layer: citation blocks, the brain index, and prep briefings.

Every renderer here is built so that a quote never appears without its source. The
core primitive is :func:`citation_block` — a verbatim quote followed by its
``[Title — Date — HH:MM:SS — Speaker]`` tag — and every other view composes it.

The refusal banner (:data:`REFUSAL`) is the visible face of the governance rule:
when retrieval returns nothing above the relevance floor, the brain says so rather
than inventing an answer.
"""

from __future__ import annotations

from typing import List

from .engine import BrainEngine, RetrievalHit
from .model import OPEN_ITEM

REFUSAL = "No sourced answer — the brain does not guess."

_KIND_LABEL = {
    "decision": "Decision",
    "rule": "Rule",
    "definition": "Definition",
    "open-item": "Open item",
}


def citation_block(hit: RetrievalHit) -> str:
    """Render a single hit as a verbatim quote + citation tag.

    This is the load-bearing primitive: the quote is the card's ``rule_text``
    (byte-identical to the source utterance) and the tag carries date, timestamp,
    and speaker so the citation is fully traceable.
    """
    card = hit.card
    prov = card.provenance
    lines = [
        f"> {card.rule_text}",
        "",
        f"{prov.citation_tag()}",
        f"_{_KIND_LABEL[card.kind]} · card `{card.card_id}` · relevance {hit.score:.3f}_",
    ]
    return "\n".join(lines)


def render_ask(query: str, hits: List[RetrievalHit]) -> str:
    """Render an ``ask`` answer: every hit cited, or the refusal banner."""
    out: List[str] = []
    out.append(f"# Ask — “{query}” [FICTIONAL]")
    out.append("")
    if not hits:
        out.append(f"> 🔒 {REFUSAL}")
        out.append("")
        out.append(
            "_No knowledge card cleared the relevance threshold. The brain refuses "
            "to answer without a cited source._"
        )
        out.append("")
        return "\n".join(out)
    out.append(f"_{len(hits)} sourced answer(s); each carries a citation._")
    out.append("")
    for i, hit in enumerate(hits, start=1):
        out.append(f"## {i}. {', '.join(hit.card.topic_tags)}")
        out.append("")
        out.append(citation_block(hit))
        out.append("")
    return "\n".join(out)


def render_citation(assertion: str, hit: RetrievalHit | None) -> str:
    """Render a ``--cite`` answer: one paste-ready footnote, or refusal."""
    out: List[str] = []
    out.append(f"# Workpaper Citation — “{assertion}” [FICTIONAL]")
    out.append("")
    if hit is None:
        out.append(f"> 🔒 {REFUSAL}")
        out.append("")
        out.append(
            "_No authoritative card (decision / rule / definition) cleared the "
            "threshold. Nothing is cited rather than citing a guess._"
        )
        out.append("")
        return "\n".join(out)
    out.append("_Ready-to-paste footnote for a workpaper or disclosure note:_")
    out.append("")
    out.append(citation_block(hit))
    out.append("")
    out.append(
        "_Provenance integrity: the quote above is byte-identical to the source "
        "transcript utterance; date, timestamp, and speaker travel with it._"
    )
    out.append("")
    return "\n".join(out)


def render_prep(topic: str, hits: List[RetrievalHit]) -> str:
    """Render a ``--prep`` briefing grouped into settled positions vs open items."""
    out: List[str] = []
    out.append(f"# Meeting Prep — “{topic}” [FICTIONAL]")
    out.append("")
    if not hits:
        out.append(f"> 🔒 {REFUSAL}")
        out.append("")
        out.append("_The brain holds no prior decisions or open items on this topic._")
        out.append("")
        return "\n".join(out)

    settled = [h for h in hits if h.card.kind != OPEN_ITEM]
    open_items = [h for h in hits if h.card.kind == OPEN_ITEM]

    out.append(
        "> 🔒 Prep briefing assembled from prior **fictional** meetings. Every prior "
        "position is cited so you can quote it word-for-word."
    )
    out.append("")
    out.append("## Settled prior positions")
    out.append("")
    if settled:
        for hit in settled:
            out.append(f"- **{_KIND_LABEL[hit.card.kind]}** ({', '.join(hit.card.topic_tags)}):")
            out.append("")
            out.append(citation_block(hit))
            out.append("")
    else:
        out.append("_None on record._")
        out.append("")

    out.append("## Open items to resolve")
    out.append("")
    if open_items:
        for hit in open_items:
            out.append(f"- ({', '.join(hit.card.topic_tags)}):")
            out.append("")
            out.append(citation_block(hit))
            out.append("")
    else:
        out.append("_None on record._")
        out.append("")
    return "\n".join(out)


def render_index(engine: BrainEngine) -> str:
    """Render the brain index: cards grouped by topic, with provenance."""
    summary = engine.index_summary()
    out: List[str] = []
    out.append("# Knowledge Brain — Index [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Sanitized public version of an internal NotebookLM-style finance brain. "
        "All meetings, people, dates, and quotes are invented; nothing reproduces a "
        "real meeting, person, or decision."
    )
    out.append("")
    out.append(
        f"**Meetings ingested:** {summary['meetings']} &nbsp;·&nbsp; "
        f"**Knowledge cards:** {summary['cards']}"
    )
    out.append("")

    kind_counts = summary["kind_counts"]  # type: ignore[assignment]
    out.append("## Cards by kind")
    out.append("")
    out.append("| Kind | Count |")
    out.append("|---|---:|")
    for kind in ("decision", "rule", "definition", "open-item"):
        out.append(f"| {_KIND_LABEL[kind]} | {kind_counts.get(kind, 0)} |")
    out.append("")

    out.append("## Cards by topic")
    out.append("")
    out.append("| Topic tag | Cards |")
    out.append("|---|---:|")
    for tag, count in summary["topic_counts"].items():  # type: ignore[union-attr]
        out.append(f"| `{tag}` | {count} |")
    out.append("")

    out.append("## Card catalogue (with provenance)")
    out.append("")
    out.append("| Card | Kind | Topics | Source (Title — Date — HH:MM:SS — Speaker) |")
    out.append("|---|---|---|---|")
    for card in sorted(engine.corpus.cards, key=lambda c: c.card_id):
        prov = card.provenance
        tag = f"{prov.title} — {prov.date} — {prov.timestamp} — {prov.speaker}"
        out.append(
            f"| `{card.card_id}` | {_KIND_LABEL[card.kind]} | "
            f"{', '.join(card.topic_tags)} | {tag} |"
        )
    out.append("")
    out.append(
        "_Every card cites a source utterance; no card exists without provenance. "
        "Retrieval is deterministic — the same query returns the same ranked order "
        "every run._"
    )
    out.append("")
    return "\n".join(out)
