# 🧠 Knowledge Brain Engine

> How I turn recorded finance/tax meetings into a **queryable, citation-governed knowledge
> base** — the sanitized public version of an internal **NotebookLM-style finance brain**.
> Used *before* engagements to prep for meetings, and *during* workpaper and disclosure-note
> writing to cite the authoritative source **word-for-word, with date and timestamp**.

> 🔒 This page describes my **approach and capabilities** over **fully fictional transcripts**.
> Every meeting, participant, date, and quote is invented. It reproduces **no real meeting,
> person, company, decision, or data** — only public accounting/tax concepts, generically.

---

## The problem I solve

Finance and tax knowledge lives in meetings: a partner settles how a warranty reserve flows
book-to-tax, a reviewer fixes the tie-out standard, a specialist rules on return of capital
beyond basis. Months later that decision has to be applied — but it survives only as a vague
memory or a buried note. When it lands in a workpaper or a disclosure footnote, it needs to be
**quotable and sourced**, not paraphrased from recall.

## My approach: record → transcribe → ingest → query

In the real (confidential) workflow I **record** the meeting, **transcribe** it, and **ingest**
the transcript into a queryable brain. Then I **query** it two ways:

- **Prep** — before the next meeting, pull every prior decision, rule, and open item on the
  topic, each already cited.
- **Cite** — while writing workpaper logic or a disclosure note, get the single authoritative
  prior statement back as a **paste-ready footnote**, quoted verbatim with its date and timestamp.

This engine is the **public, runnable** version of that brain, over invented transcripts.

## What this demonstrates

- **Knowledge management** — meetings become structured, searchable institutional memory
  instead of evaporating.
- **Retrieval with citation governance** — every answer carries a source; the engine **refuses
  to guess** when nothing is relevant.
- **Audit-ready provenance** — date, timestamp, and speaker travel with every quote, so a
  disclosure note or workpaper line can be traced straight back to who said it and when.
- **Meeting prep** — settled positions and open items for a topic, assembled and cited in one
  briefing.

## Tools

`Python (stdlib only)` · `deterministic TF-IDF (no embeddings, no LLM, no network)` ·
`NotebookLM` · `Claude Code` · `generic transcription (record → transcribe)` · `Markdown evidence`

## Sample (fictional)

- [Knowledge cards worked example](./samples/sample-knowledge-cards.md) — one fictional meeting
  → extracted cards → a verbatim citation → the refusal banner.

---

## ▶️ Run it

This engine ships a **genuinely working** brain over a corpus of **fully fictional** finance/tax
meetings. It parses transcripts into timestamped utterances, extracts authoritative utterances
into knowledge cards (each carrying full provenance), builds a **deterministic** keyword/tag
TF-IDF index, and answers three query shapes — always with a citation, or an explicit refusal.

The seeded corpus contains four invented meetings whose decisions map onto real public concepts:

```text
Warranty Reserve Book-Tax Working Session   (warranty reserve book-tax attribution)
Return of Capital and Basis Review          (return of capital beyond basis is a deemed gain)
Workpaper Evidence and Tie-Out Standards    (evidence must foot to a cited anchor)
Foreign Affiliate Surplus Elevation Review  (surplus elevates only on an actual distribution)
```

**Requirements:** Python 3 (3.14 OK). No third-party packages — stdlib only. `pytest` for tests.

```bash
# from this folder:
python -m pip install --quiet pytest        # one-time, for the test suite

# bare run — print the brain index (meetings ingested, card counts by topic):
python -m brain_engine

# ask a question — top matching card(s), each with a citation block:
python -m brain_engine ask "how is return of capital beyond basis treated?"

# cite — one paste-ready workpaper/disclosure footnote, quoted verbatim:
python -m brain_engine --cite "return of capital in excess of basis is a deemed gain"

# prep — a meeting-prep briefing of prior decisions/rules/open-items for a topic:
python -m brain_engine --prep "warranty reserve book-tax treatment"

# write the Markdown deliverables (index / citation example / prep example):
python -m brain_engine --out out
#   (equivalently: python run.py --out out)

# run the test suite:
python -m pytest -q
```

> 💡 On Windows, if your console can't render the 🔒 banner, set `PYTHONIOENCODING=utf-8`
> (the CLI also degrades gracefully and will not crash on a legacy code page).

### What it produces
- `out/brain_index.md` — every card grouped by topic and by kind, with full provenance.
- `out/citation_example.md` — a sample workpaper citation block (verbatim quote + source).
- `out/meeting_prep_example.md` — a sample prep briefing (settled positions + open items).

### Example output (real, generated by the commands above)

**`--cite "return of capital in excess of basis is a deemed gain"`** returns a paste-ready
footnote — the quote is byte-identical to the transcript:

```text
> Decision: any return of capital in excess of the investor's remaining basis is
  recharacterized as a deemed capital gain in the year received.

[Return of Capital and Basis Review — 2025-02-03 — 00:03:41 — Lena Frost]
```

**`--prep "warranty reserve book-tax treatment"`** assembles the prior positions, each cited,
and parks the open items separately:

```text
## Settled prior positions

> Decision: the warranty reserve is booked on an accrual basis but deducted for tax only when
  the claim is economically performed, so the book-tax difference is a deferred tax asset.
[Warranty Reserve Book-Tax Working Session — 2025-01-14 — 00:03:02 — Priya Vale]   (relevance 0.693)

> Rule: every warranty book-tax adjustment must reference the originating accrual schedule by
  line, or the workpaper is not signed.
[Warranty Reserve Book-Tax Working Session — 2025-01-14 — 00:06:01 — Priya Vale]   (relevance 0.387)

## Open items to resolve

> Open item: confirm whether the extended-warranty piece is a separate performance obligation
  before year end.
[Warranty Reserve Book-Tax Working Session — 2025-01-14 — 00:09:00 — Dana Brook]   (relevance 0.238)
```

**The governance differentiator — refusal.** Ask something the brain has no source for and it
will not guess:

```text
$ python -m brain_engine ask "what is the office parking and lunch policy"
> 🔒 No sourced answer — the brain does not guess.
```

### Test output (real)

```text
$ python -m pytest -q
..................................................                       [100%]
50 passed
```

The suite asserts the load-bearing governance: **every returned answer carries a citation**,
the **refuse-do-not-guess** behaviour when nothing clears the relevance floor, **HH:MM:SS
formatting** from second offsets, **cite-mode text byte-identical** to the source utterance,
**retrieval determinism** (same query → same ranked order and scores), **keyword/tag scoring**
ranking the obviously-best card first, **prep mode** including the right prior decisions and
excluding irrelevant ones, **index counts**, and that **no card exists without a source**.

### Layout
```text
knowledge-brain-engine/
├── brain_engine/
│   ├── __init__.py      # package + confidentiality posture
│   ├── model.py         # Meeting / Utterance / Provenance / KnowledgeCard / Corpus
│   ├── generate.py      # seeded fictional transcript corpus + card extraction
│   ├── engine.py        # deterministic TF-IDF retrieval, cite/prep, refusal governance
│   ├── report.py        # citation blocks, brain index, prep briefing, refusal banner
│   ├── cli.py           # argparse CLI (ask / --cite / --prep / default index)
│   ├── __main__.py      # python -m brain_engine
│   └── tests/           # pytest suite (50 tests, inside the package)
├── run.py               # convenience entrypoint
├── pytest.ini
├── out/                 # generated Markdown deliverables
└── samples/             # fictional worked example
```

> 🔒 Everything above — meetings, participants, dates, quotes — is **invented for this portfolio
> demo**. The engine implements only public accounting/tax concepts generically and reproduces no
> real meeting, person, company, methodology, or data.
