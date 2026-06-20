# 🧠 Knowledge Brain Engine

> The platform turns recorded finance/tax meetings into a **queryable, citation-governed knowledge
> base** — the sanitized public version of an internal **NotebookLM-style finance brain**.
> Used *before* engagements to prepare for meetings, and *during* workpaper and disclosure-note
> writing to cite the authoritative source **word-for-word, with date and timestamp**.

> 🔒 This page describes the platform's **approach and capabilities** over **fully fictional transcripts**.
> Every meeting, participant, date, and quote is invented. It reproduces **no real meeting,
> person, company, decision, or data** — only public accounting/tax concepts, generically.

---

## The problem it solves

Finance and tax knowledge lives in meetings: a partner settles how a warranty reserve flows
book-to-tax, a reviewer fixes the tie-out standard, a specialist rules on return of capital
beyond basis. Months later that decision has to be applied — but it survives only as a vague
memory or a buried note. When it lands in a workpaper or a disclosure footnote, it needs to be
**quotable and sourced**, not paraphrased from recall.

## Approach: record → transcribe → ingest → query

In the real (confidential) workflow, the platform **records** the meeting, **transcribes** it, and
**ingests** the transcript into a queryable brain. It is then **queried** three ways:

- **Prep** — before the next meeting, pull every prior decision, rule, and open item on the
  topic, each already cited.
- **Cite** — while writing workpaper logic or a disclosure note, retrieve the single authoritative
  prior statement as a **paste-ready footnote**, quoted verbatim with its date and timestamp.
- **Remediate** — after a **review meeting**, turn the reviewer's spoken corrections into a
  cited change set and an **apply-ready, ready-to-paste prompt** (plus a change-log mapping each
  directive → source → status) that a downstream AI or operator uses to apply every fix.

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

## Review → remediation

The brain holds **two** kinds of source-cited knowledge: the standing **laws** (decisions,
rules, definitions) *and* the per-review **change-requests** a reviewer dictates. In the real
(confidential) workflow, the platform records the review meeting where a reviewer asks for specific
corrections, then feeds that transcript through this engine to **generate** an apply-ready, cited
remediation prompt; a downstream AI or operator then runs that prompt to **apply** the requested
changes. **The transcript IS the instruction set** — and application and verification happen
downstream.

This engine generates exactly that:

1. A fictional review meeting's corrections are captured **verbatim** as `ChangeDirective`s, each
   with full provenance (meeting, date, **HH:MM:SS**, speaker).
2. `remediate "<review>"` retrieves those directives in spoken order and **auto-writes the
   prompt you paste into your AI** — every numbered change annotated with its exact source quote
   and timestamp, plus an instruction to log each applied change against its source.
3. A **cited change-log** maps each directive → source citation → status (starts **PENDING**), so
   every applied change traces back to the exact words it came from. Nothing is paraphrased; the
   quote in the prompt and the change-log is **byte-identical** to what was said.

If a review topic has no directives on record, the engine **refuses** rather than inventing
corrections — the same refuse-do-not-guess control that governs every other mode.

```bash
# turn a review meeting's spoken corrections into cited directives + a paste-ready fix prompt:
python -m brain_engine remediate "Surplus Workpaper Review — Reviewer Corrections"
```

**Real generated excerpt** (the directive list, then the prompt the operator copy-pastes):

```text
## Change-directives (in spoken order)

**1. — target: distribution formula column reference**
> Change the distribution formula to reference column E, not column D, across every year column.
[Surplus Workpaper Review — Reviewer Corrections — 2025-04-08 — 00:01:04 — Quinn Harlow]
directive `DIR-SURPLUS-REVIEW-01` · status PENDING
...

## Ready-to-paste remediation prompt
You are a downstream AI or operator applying reviewer corrections to a finance/tax workpaper.
Apply EACH numbered change below exactly as the reviewer stated it. ...

1. Change the distribution formula to reference column E, not column D, across every year column.
   Source quote: "Change the distribution formula to reference column E, not column D, across every year column."
   Source: [Surplus Workpaper Review — Reviewer Corrections — 2025-04-08 — 00:01:04 — Quinn Harlow]
...
After applying all changes, output a change log: for each numbered change, record the change you
made, the file/cell you touched, and the source citation above ... and set its status to APPLIED.
... If any change cannot be applied, leave it PENDING and explain why — never guess.
```

With `--out`, this also writes `out/remediation_prompt.md` (the copy-paste prompt) and
`out/change_log.md` (the cited fix-packet). Every name, number, and date here is **fictional**.

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

# remediate — a review's spoken corrections as cited directives + a paste-ready fix prompt:
python -m brain_engine remediate "Surplus Workpaper Review — Reviewer Corrections"

# write the Markdown deliverables (index / citation / prep / remediation prompt / change-log):
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
- `out/remediation_prompt.md` — a review's cited change-directives + the paste-ready fix prompt.
- `out/change_log.md` — the cited fix-packet (directive → source citation → status PENDING).

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
...........................................................................  [100%]
226 passed
```

The suite asserts the load-bearing governance: **every returned answer carries a citation**,
the **refuse-do-not-guess** behaviour when nothing clears the relevance floor, **HH:MM:SS
formatting** from second offsets, **cite-mode text byte-identical** to the source utterance,
**retrieval determinism** (same query → same ranked order and scores), **keyword/tag scoring**
ranking the obviously-best card first, **prep mode** including the right prior decisions and
excluding irrelevant ones, **index counts**, and that **no card exists without a source**. The
**review → remediation** tests add: change-directives extracted with full provenance, the
generated remediation prompt containing **every directive in order**, each directive in the
prompt *and* the change-log carrying its **verbatim** source quote + timestamp, the change-log
mapping **1:1** to the directives at status **PENDING**, prompt **determinism**, and
**refusal/empty** when a review topic has no directives on record.

### Layout
```text
knowledge-brain-engine/
├── brain_engine/
│   ├── __init__.py      # package + confidentiality posture
│   ├── model.py         # Meeting / Utterance / Provenance / KnowledgeCard / ChangeDirective / Corpus
│   ├── generate.py      # seeded fictional transcript corpus + card & directive extraction
│   ├── engine.py        # deterministic TF-IDF retrieval, cite/prep, remediation, refusal governance
│   ├── report.py        # citation blocks, brain index, prep briefing, remediation prompt + change-log
│   ├── cli.py           # argparse CLI (ask / --cite / --prep / remediate / default index)
│   ├── __main__.py      # python -m brain_engine
│   └── tests/           # pytest suite (226 tests, inside the package)
├── run.py               # convenience entrypoint
├── pytest.ini
├── out/                 # generated Markdown deliverables
└── samples/             # fictional worked example
```

> 🔒 Everything above — meetings, participants, dates, quotes — is **invented for this portfolio
> demo**. The engine implements only public accounting/tax concepts generically and reproduces no
> real meeting, person, company, methodology, or data.
