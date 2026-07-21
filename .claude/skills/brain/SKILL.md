---
name: brain
description: "Run the Knowledge Brain (citation-governed retrieval over meeting transcripts: ask/cite/prep/remediate) or its verbatim-or-refuse integrity loop. Use for cited answers, review-to-remediation, or KB drift repair."
---
# Knowledge Brain Engine

Package `brain_engine` in `knowledge-brain-engine/`. Stdlib TF-IDF, no network. Exit codes: 0 sourced, 2 usage error, 3 refusal.

## Commands (run from `knowledge-brain-engine/`)
```bash
python -m brain_engine ask "how do we handle FX on ACB?"
python -m brain_engine --cite "distributions draw exempt surplus first"
python -m brain_engine remediate "Surplus Review"     # reviewer corrections -> apply-ready prompt
python -m brain_engine.loop --demo                    # INTEGRITY LOOP: re-derive tampered entries verbatim
python -m pytest -q                                   # 7,011 tests
```

## Loop verdicts (`brain_engine/loop.py`)
`CLEAN` (0) / `REMEDIATED` (0) / `ESCALATED` (3 — the engine's refusal code).
The signature rule: tampered text/speakers are re-derived BYTE-FOR-BYTE from `Corpus.utterance_text`; **orphaned citations (no utterance behind them) are quarantined, never repaired** — no source, no guess.
