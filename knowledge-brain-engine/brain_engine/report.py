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

from .engine import BrainEngine, Remediation, RetrievalHit
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


def render_remediation(rem: Remediation) -> str:
    """Render the review-to-remediation view for the CLI: the cited directive
    list followed by the ready-to-paste remediation prompt (or a refusal)."""
    out: List[str] = []
    out.append(f"# Review → Remediation — “{rem.topic}” [FICTIONAL]")
    out.append("")
    if rem.is_empty:
        out.append(f"> 🔒 {REFUSAL}")
        out.append("")
        out.append(
            "_No change-directive on record for this review. The brain refuses to "
            "manufacture corrections._"
        )
        out.append("")
        return "\n".join(out)

    out.append(
        "> 🔒 Reviewer corrections from a prior **fictional** review meeting, captured "
        "verbatim. The transcript IS the instruction set — paste the prompt below into "
        "your AI and the changes get applied hands-free, each traceable to the exact words."
    )
    out.append("")
    out.append(f"_{len(rem.directives)} change-directive(s); each carries a citation._")
    out.append("")

    out.append("## Change-directives (in spoken order)")
    out.append("")
    for entry in rem.fix_packet:
        d = entry.directive
        prov = d.provenance
        target = f" — _target: {d.target}_" if d.target else ""
        out.append(f"**{entry.number}.{target}**")
        out.append("")
        out.append(f"> {d.request_text}")
        out.append("")
        out.append(f"{prov.citation_tag()}")
        out.append(f"_directive `{d.directive_id}` · status {entry.status}_")
        out.append("")

    out.append("## Ready-to-paste remediation prompt")
    out.append("")
    out.append("_Copy everything in the block below into your AI; it applies each change "
               "hands-free and logs every applied change against its source._")
    out.append("")
    out.append("```text")
    out.append(rem.prompt)
    out.append("```")
    out.append("")
    return "\n".join(out)


def render_change_log(rem: Remediation) -> str:
    """Render the cited change-log / fix-packet: directive -> source -> status.

    The change-log maps 1:1 to the review's directives and quotes each request
    byte-identically so a reviewer can confirm nothing drifted from what was said.
    """
    out: List[str] = []
    out.append(f"# Change Log — “{rem.topic}” [FICTIONAL]")
    out.append("")
    if rem.is_empty:
        out.append(f"> 🔒 {REFUSAL}")
        out.append("")
        out.append("_No change-directive on record for this review; nothing to log._")
        out.append("")
        return "\n".join(out)

    out.append(
        "> 🔒 Fix-packet for a **fictional** review. Each row maps a reviewer change-request "
        "to its verbatim source citation and a status. Every entry starts **PENDING**; the AI "
        "(or operator) flips it to **APPLIED** once the edit is made and logged against its source."
    )
    out.append("")
    out.append("| # | Change requested (verbatim) | Target | Source (Title — Date — HH:MM:SS — Speaker) | Directive | Status |")
    out.append("|---:|---|---|---|---|---|")
    for entry in rem.fix_packet:
        d = entry.directive
        prov = d.provenance
        quote = d.request_text.replace("|", "\\|")
        target = d.target.replace("|", "\\|") if d.target else "—"
        src = f"{prov.title} — {prov.date} — {prov.timestamp} — {prov.speaker}"
        out.append(
            f"| {entry.number} | {quote} | {target} | {src} | `{d.directive_id}` | {entry.status} |"
        )
    out.append("")
    out.append(
        "_Every change traces to the exact words and timestamp it came from; the quote above is "
        "byte-identical to the source transcript utterance. Status starts PENDING by design._"
    )
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
