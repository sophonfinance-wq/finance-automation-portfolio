"""Knowledge Brain Engine — the sanitized, runnable public version of an internal
NotebookLM-style "finance brain".

In the real (confidential) workflow the operator records project and tax meetings,
transcribes them, and loads the transcripts into a queryable knowledge base. That
brain is used BEFORE engagements to (a) prep for upcoming meetings and (b) cite the
authoritative source — word-for-word, with date and timestamp — when writing
workpaper logic and accounting disclosure notes.

This package demonstrates that capability on a corpus of **fully fictional**
transcripts:

    record -> transcribe -> ingest -> query (prep / cite)

The pipeline is deterministic and stdlib-only (no embeddings, no LLM calls, no
network): a fictional transcript corpus is parsed into timestamped utterances,
authoritative utterances are extracted into knowledge cards carrying full
provenance (meeting, date, timestamp, speaker), and a reproducible keyword/tag
retrieval index ranks cards for a query.

Governance is the differentiator. EREDACTED answer must carry a citation; if no card
clears the relevance threshold the engine REFUSES rather than guessing. Cite mode
returns text that is byte-identical to the source utterance, and the date,
timestamp, and speaker always travel with the quote.

All meetings, participants, entities, dates, and quotes in this package are
invented for a portfolio demonstration. Nothing here reproduces any real meeting,
person, company, decision, or data.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
