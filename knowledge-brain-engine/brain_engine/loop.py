"""Knowledge-Base Integrity Loop — verbatim-or-refuse remediation.

The Knowledge Brain's whole trust model is *verbatim, timestamped citation*:
every :class:`~brain_engine.model.KnowledgeCard` and
:class:`~brain_engine.model.ChangeDirective` must carry its source utterance's
text byte-for-byte, with provenance pointing at a real (meeting, timestamp,
speaker). Today that guarantee is asserted at extraction time — nothing
re-verifies it once the KB is stored, where it can drift: a card's text edited
after the fact, a provenance stamped with the wrong speaker, an entry whose
citation points at a moment no one ever spoke.

This loop closes that gap:

    observe → detect → remediate → re-verify → gate → repeat

1. **observe / detect** — an integrity pass over every card and directive,
   comparing stored text and provenance against the transcript of record
   (:meth:`~brain_engine.model.Corpus.utterance_text`). Findings:

   * ``TAMPERED_TEXT`` — stored text no longer matches the source utterance.
   * ``TAMPERED_SPEAKER`` — provenance names the wrong speaker for that moment.
   * ``ORPHANED`` — the citation points at a (meeting, timestamp) where no
     utterance exists. **There is no source to re-derive from.**

2. **remediate** — for the earliest affected meeting, re-derive every tampered
   entry from the transcript (text and speaker restored verbatim), booking
   each change. Orphans are **held, never repaired**: inventing a source would
   betray the engine's one rule. They are quarantined for a human.
3. **re-verify** — run the integrity pass again; repeat until only orphans (or
   nothing) remain, or the turn budget is exhausted.

The verdict mirrors the brain's refusal discipline (CLI exit code 3 = refusal):

* ``CLEAN``      — nothing drifted (exit 0).
* ``REMEDIATED`` — every finding re-derived from the transcript (exit 0).
* ``ESCALATED``  — uncited entries remain quarantined for a human; the loop
  refuses to guess (exit 3).

All transcripts are fictional.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .generate import DEFAULT_SEED, build_corpus
from .model import Corpus, format_timestamp

CLEAN = "CLEAN"
REMEDIATED = "REMEDIATED"
ESCALATED = "ESCALATED"

TAMPERED_TEXT = "TAMPERED_TEXT"
TAMPERED_SPEAKER = "TAMPERED_SPEAKER"
ORPHANED = "ORPHANED"

# Findings the loop may repair by re-deriving from the transcript. ORPHANED is
# deliberately absent: no source, no guess.
REMEDIABLE = frozenset({TAMPERED_TEXT, TAMPERED_SPEAKER})


# --------------------------------------------------------------------------- #
# Findings.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Finding:
    """One integrity break: a stored entry that disagrees with the transcript."""

    kind: str              # TAMPERED_TEXT | TAMPERED_SPEAKER | ORPHANED
    entry_id: str          # card_id or directive_id
    entry_type: str        # "card" | "directive"
    meeting_id: str
    timestamp: str
    detail: str


@dataclass(frozen=True)
class Correction:
    """One field re-derived verbatim from the transcript."""

    entry_id: str
    field: str
    from_value: str
    to_value: str


@dataclass(frozen=True)
class Turn:
    index: int
    meeting_id: str
    corrections: Tuple[Correction, ...]
    findings_before: int
    findings_after: int


@dataclass(frozen=True)
class LoopJournal:
    seed: int
    faults: Tuple[str, ...]
    initial_findings: Tuple[Finding, ...]
    turns: Tuple[Turn, ...]
    quarantined: Tuple[Finding, ...]
    budget: int
    verdict: str

    @property
    def total_corrections(self) -> int:
        return sum(len(t.corrections) for t in self.turns)


# --------------------------------------------------------------------------- #
# Sensor: the KB integrity pass.
# --------------------------------------------------------------------------- #
def _speaker_at(corpus: Corpus, meeting_id: str, timestamp: str) -> Optional[str]:
    for meeting in corpus.meetings:
        if meeting.meeting_id != meeting_id:
            continue
        for utt in meeting.utterances:
            if format_timestamp(utt.t_seconds) == timestamp:
                return utt.speaker
    return None


def _verify_entry(corpus: Corpus, entry, entry_type: str, text_field: str) -> List[Finding]:
    prov = entry.provenance
    entry_id = getattr(entry, "card_id", None) or getattr(entry, "directive_id")
    try:
        source_text = corpus.utterance_text(prov.meeting_id, prov.timestamp)
    except KeyError:
        return [Finding(
            ORPHANED, entry_id, entry_type, prov.meeting_id, prov.timestamp,
            f"citation points at {prov.meeting_id} {prov.timestamp}, where no "
            f"utterance exists — no source to re-derive from",
        )]
    findings: List[Finding] = []
    stored = getattr(entry, text_field)
    if stored != source_text:
        findings.append(Finding(
            TAMPERED_TEXT, entry_id, entry_type, prov.meeting_id, prov.timestamp,
            f"stored text no longer matches the transcript verbatim",
        ))
    true_speaker = _speaker_at(corpus, prov.meeting_id, prov.timestamp)
    if true_speaker is not None and prov.speaker != true_speaker:
        findings.append(Finding(
            TAMPERED_SPEAKER, entry_id, entry_type, prov.meeting_id, prov.timestamp,
            f"provenance names {prov.speaker!r}; the transcript says "
            f"{true_speaker!r} spoke at {prov.timestamp}",
        ))
    return findings


def verify_corpus(corpus: Corpus) -> List[Finding]:
    """Integrity pass: every card and directive vs the transcript of record."""
    findings: List[Finding] = []
    for card in corpus.cards:
        findings.extend(_verify_entry(corpus, card, "card", "rule_text"))
    for directive in corpus.directives:
        findings.extend(_verify_entry(corpus, directive, "directive", "request_text"))
    findings.sort(key=lambda f: (f.meeting_id, f.timestamp, f.entry_id, f.kind))
    return findings


# --------------------------------------------------------------------------- #
# Authority: re-derive an entry verbatim from the transcript.
# --------------------------------------------------------------------------- #
def _rederive(corpus: Corpus, entry, text_field: str) -> Tuple[object, List[Correction]]:
    """Return (fixed entry, corrections) — text and speaker restored from source."""
    prov = entry.provenance
    entry_id = getattr(entry, "card_id", None) or getattr(entry, "directive_id")
    corrections: List[Correction] = []

    source_text = corpus.utterance_text(prov.meeting_id, prov.timestamp)
    stored = getattr(entry, text_field)
    new_entry = entry
    if stored != source_text:
        corrections.append(Correction(entry_id, text_field, stored, source_text))
        new_entry = dataclasses.replace(new_entry, **{text_field: source_text})

    true_speaker = _speaker_at(corpus, prov.meeting_id, prov.timestamp)
    if true_speaker is not None and prov.speaker != true_speaker:
        corrections.append(Correction(entry_id, "provenance.speaker", prov.speaker, true_speaker))
        new_entry = dataclasses.replace(
            new_entry, provenance=dataclasses.replace(prov, speaker=true_speaker)
        )
    return new_entry, corrections


def _remediate_meeting(corpus: Corpus, meeting_id: str) -> List[Correction]:
    """Re-derive every remediable entry cited to ``meeting_id``."""
    corrections: List[Correction] = []
    for i, card in enumerate(corpus.cards):
        if card.provenance.meeting_id == meeting_id:
            try:
                fixed, corr = _rederive(corpus, card, "rule_text")
            except KeyError:
                continue  # orphan — held for a human
            corpus.cards[i] = fixed
            corrections.extend(corr)
    for i, directive in enumerate(corpus.directives):
        if directive.provenance.meeting_id == meeting_id:
            try:
                fixed, corr = _rederive(corpus, directive, "request_text")
            except KeyError:
                continue
            corpus.directives[i] = fixed
            corrections.extend(corr)
    return corrections


# --------------------------------------------------------------------------- #
# Demo drift.
# --------------------------------------------------------------------------- #
def demo_setup(seed: int = DEFAULT_SEED):
    """Build a drifted corpus: two tampers, a wrong speaker, and an orphan."""
    corpus = build_corpus(seed)
    faults: List[str] = []

    cards = sorted(range(len(corpus.cards)), key=lambda i: corpus.cards[i].card_id)
    # F1 — a card's rule text quietly edited after storage.
    i = cards[0]
    card = corpus.cards[i]
    corpus.cards[i] = dataclasses.replace(
        card, rule_text=card.rule_text + " (net of immaterial items)"
    )
    faults.append(f"F1 {card.card_id}: rule text edited after storage")

    # F2 — a directive's request text reworded.
    d = corpus.directives[0]
    corpus.directives[0] = dataclasses.replace(
        d, request_text=d.request_text.replace("column", "row")
        if "column" in d.request_text else d.request_text + " ASAP"
    )
    faults.append(f"F2 {d.directive_id}: reviewer's correction reworded")

    # F3 — provenance stamped with the wrong speaker.
    i = cards[1]
    card = corpus.cards[i]
    corpus.cards[i] = dataclasses.replace(
        card, provenance=dataclasses.replace(card.provenance, speaker="A. Nobody")
    )
    faults.append(f"F3 {card.card_id}: provenance names the wrong speaker")

    # F4 — an orphaned citation: timestamp shifted to a moment no one spoke.
    i = cards[2]
    card = corpus.cards[i]
    corpus.cards[i] = dataclasses.replace(
        card, provenance=dataclasses.replace(card.provenance, timestamp="03:59:59")
    )
    faults.append(f"F4 {card.card_id}: citation orphaned (no utterance at 03:59:59)")

    return corpus, tuple(faults)


# --------------------------------------------------------------------------- #
# Loop.
# --------------------------------------------------------------------------- #
def integrity_loop(
    corpus: Corpus,
    *,
    seed: int = DEFAULT_SEED,
    budget: Optional[int] = None,
    faults: Tuple[str, ...] = (),
) -> LoopJournal:
    """Drive a drifted KB back to verbatim fidelity with its transcripts."""
    if budget is None:
        budget = len(corpus.meetings) + 2

    findings = verify_corpus(corpus)
    initial = tuple(findings)

    turns: List[Turn] = []
    while len(turns) < budget:
        remediable = [f for f in findings if f.kind in REMEDIABLE]
        if not remediable:
            break
        meeting_id = remediable[0].meeting_id
        corrections = _remediate_meeting(corpus, meeting_id)
        after = verify_corpus(corpus)
        turns.append(Turn(
            index=len(turns) + 1,
            meeting_id=meeting_id,
            corrections=tuple(corrections),
            findings_before=len(findings),
            findings_after=len(after),
        ))
        findings = after

    quarantined = tuple(f for f in findings if f.kind == ORPHANED)
    remediable_left = [f for f in findings if f.kind in REMEDIABLE]
    if remediable_left:
        verdict = ESCALATED  # budget exhausted with fixable drift left
    elif quarantined:
        verdict = ESCALATED
    elif turns:
        verdict = REMEDIATED
    else:
        verdict = CLEAN

    return LoopJournal(
        seed=seed,
        faults=faults,
        initial_findings=initial,
        turns=tuple(turns),
        quarantined=quarantined,
        budget=budget,
        verdict=verdict,
    )


def verdict_exit_code(verdict: str) -> int:
    """ESCALATED reuses the engine's refusal exit code (3)."""
    return 3 if verdict == ESCALATED else 0


# --------------------------------------------------------------------------- #
# Markdown report.
# --------------------------------------------------------------------------- #
_BLURB = {
    CLEAN: "Every card and directive matches its transcript verbatim. Nothing to do.",
    REMEDIATED: "All drift re-derived verbatim from the transcript of record.",
    ESCALATED: "Uncited entries are quarantined for a human — the loop refuses "
    "to invent a source.",
}


def render_markdown(journal: LoopJournal) -> str:
    mark = {CLEAN: "✅", REMEDIATED: "✅", ESCALATED: "⚑"}[journal.verdict]
    out: List[str] = []
    out.append("# Knowledge-Base Integrity Loop [FICTIONAL]")
    out.append("")
    out.append(
        "> 🔒 Fictional transcripts. The loop re-verifies every stored card and "
        "directive against its source utterance — re-deriving drift verbatim, "
        "and refusing to repair what has no source."
    )
    out.append("")
    out.append(f"**Verdict: {mark} {journal.verdict}** — {_BLURB[journal.verdict]}")
    out.append("")
    out.append(
        f"- Injected drift: **{len(journal.faults)}** fault(s) · "
        f"initial findings: **{len(journal.initial_findings)}**"
    )
    out.append(
        f"- Turns: **{len(journal.turns)}** / budget **{journal.budget}** · "
        f"corrections: **{journal.total_corrections}** · "
        f"quarantined: **{len(journal.quarantined)}**"
    )
    out.append("")

    if journal.faults:
        out.append("## Injected drift")
        out.append("")
        for f in journal.faults:
            out.append(f"- {f}")
        out.append("")

    out.append("## The loop, turn by turn")
    out.append("")
    if not journal.turns:
        out.append("_No remediable drift._")
        out.append("")
    for t in journal.turns:
        out.append(
            f"### Turn {t.index} — re-derive `{t.meeting_id}` · "
            f"{t.findings_before} → {t.findings_after} findings"
        )
        out.append("")
        for c in t.corrections:
            out.append(f"- `{c.entry_id}` **{c.field}**: “{c.from_value}” → “{c.to_value}”")
        out.append("")

    if journal.quarantined:
        out.append("## Held, not repaired")
        out.append("")
        for f in journal.quarantined:
            out.append(f"- **{f.kind}** `{f.entry_id}` — {f.detail}")
        out.append("")
        out.append(
            "_No source, no guess: repairing an uncited entry would mean inventing "
            "a citation. These wait for a human._"
        )
        out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys
    from pathlib import Path

    p = argparse.ArgumentParser(
        prog="brain_engine.loop",
        description="Knowledge-base integrity loop: verbatim-or-refuse "
        "remediation against the transcript of record (fictional data).",
    )
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--demo", action="store_true", help="inject the drift profile")
    p.add_argument("--budget", type=int, default=None)
    p.add_argument("--out", default=None, help="directory for the Markdown report")
    args = p.parse_args(argv)

    if args.demo:
        corpus, faults = demo_setup(args.seed)
    else:
        corpus, faults = build_corpus(args.seed), ()

    journal = integrity_loop(corpus, seed=args.seed, budget=args.budget, faults=faults)
    md = render_markdown(journal)
    try:
        print(md)
    except UnicodeEncodeError:  # pragma: no cover
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(md.encode(enc, errors="replace").decode(enc) + "\n")

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "integrity_loop_report.md").write_text(md, encoding="utf-8")
        print(f"\nWrote integrity_loop_report.md to {out_dir.resolve()}")

    return verdict_exit_code(journal.verdict)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
