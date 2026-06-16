# Sample — Knowledge Cards from a Fictional Transcript (FICTIONAL)

> 🔒 Invented meeting, participants, and dialogue for demonstration. Illustrates the
> *record → transcribe → ingest → query* lineage only — not a real meeting, person, or
> decision. All quotes below are fabricated.

This is a short worked example of how one fictional meeting becomes citable knowledge
cards, and how a later query cites them word-for-word.

## Step 1 — The transcribed meeting (excerpt)

**Meeting:** Return of Capital and Basis Review · **Date:** 2025-02-03
**Participants:** Marco Reyes, Lena Frost, Avery Stone

| Timestamp | Speaker | Utterance (verbatim) |
|---|---|---|
| 00:01:35 | Lena Frost | Definition: a return of capital is a distribution treated first as a tax-free recovery of basis, reducing the investor's adjusted basis dollar for dollar. |
| 00:03:41 | Lena Frost | Decision: any return of capital in excess of the investor's remaining basis is recharacterized as a deemed capital gain in the year received. |
| 00:06:40 | Marco Reyes | Rule: basis can never go below zero, so the workpaper must clamp it and route the excess to the gain line. |
| 00:08:25 | Lena Frost | Open item: decide if the state follows the federal recharacterization or defers it. |

## Step 2 — The extracted knowledge cards

Each authoritative utterance is lifted into a card whose `rule_text` is **byte-identical**
to the transcript, carrying full provenance.

| Card | Kind | Topics | Provenance (Title — Date — HH:MM:SS — Speaker) |
|---|---|---|---|
| `CARD-ROC-01` | Definition | return-of-capital, basis, definition | Return of Capital and Basis Review — 2025-02-03 — 00:01:35 — Lena Frost |
| `CARD-ROC-02` | Decision | return-of-capital, basis, capital-gain | Return of Capital and Basis Review — 2025-02-03 — 00:03:41 — Lena Frost |
| `CARD-ROC-03` | Rule | basis, workpaper, capital-gain | Return of Capital and Basis Review — 2025-02-03 — 00:06:40 — Marco Reyes |
| `CARD-ROC-04` | Open item | return-of-capital, state-tax | Return of Capital and Basis Review — 2025-02-03 — 00:08:25 — Lena Frost |

## Step 3 — Citing a card in a workpaper

A workpaper assertion — *"return of capital in excess of basis is a deemed gain"* — retrieves
the single best **authoritative** card and returns a paste-ready footnote:

> Decision: any return of capital in excess of the investor's remaining basis is recharacterized as a deemed capital gain in the year received.

[Return of Capital and Basis Review — 2025-02-03 — 00:03:41 — Lena Frost]

## Step 4 — When the brain refuses

A query with no relevant card — *"office parking and lunch policy"* — returns no card and the
governance banner instead of a guess:

> 🔒 No sourced answer — the brain does not guess.

---
**Governance rule shown here:** every answer carries a citation; the cited quote is byte-identical
to the source utterance; the date, timestamp, and speaker always travel with it; and if nothing
clears the relevance floor, the brain **refuses** rather than fabricating. *(Open-items appear in
meeting-prep briefings but are never returned as workpaper authority.)*
