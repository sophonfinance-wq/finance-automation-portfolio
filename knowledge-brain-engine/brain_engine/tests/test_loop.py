"""Tests for the Knowledge-Base Integrity Loop.

Prove the sensor (drift genuinely breaks the verbatim guarantee), the loop
(re-derives from the transcript, never invents, refuses orphans), the verdict
gate (CLEAN / REMEDIATED / ESCALATED with the engine's refusal exit code), and
determinism.
"""

from __future__ import annotations

import dataclasses

from brain_engine.generate import DEFAULT_SEED, build_corpus
from brain_engine.loop import (
    CLEAN,
    ESCALATED,
    ORPHANED,
    REMEDIATED,
    TAMPERED_SPEAKER,
    TAMPERED_TEXT,
    demo_setup,
    integrity_loop,
    render_markdown,
    verdict_exit_code,
    verify_corpus,
)


# --------------------------------------------------------------------------- #
# Sensor.
# --------------------------------------------------------------------------- #
def test_pristine_corpus_verifies_clean():
    assert verify_corpus(build_corpus(DEFAULT_SEED)) == []


def test_demo_drift_trips_the_sensor():
    corpus, faults = demo_setup()
    findings = verify_corpus(corpus)
    kinds = {f.kind for f in findings}
    assert kinds == {TAMPERED_TEXT, TAMPERED_SPEAKER, ORPHANED}
    assert len(findings) == 4
    assert len(faults) == 4


def test_orphan_detected_by_kind():
    corpus = build_corpus(DEFAULT_SEED)
    card = corpus.cards[0]
    corpus.cards[0] = dataclasses.replace(
        card, provenance=dataclasses.replace(card.provenance, timestamp="03:59:59")
    )
    findings = verify_corpus(corpus)
    assert [f.kind for f in findings] == [ORPHANED]


# --------------------------------------------------------------------------- #
# Loop behaviour.
# --------------------------------------------------------------------------- #
def test_loop_rederives_tampered_and_quarantines_orphans():
    corpus, faults = demo_setup()
    journal = integrity_loop(corpus, faults=faults)
    assert journal.verdict == ESCALATED
    assert len(journal.quarantined) == 1
    assert journal.quarantined[0].kind == ORPHANED
    # All remediable drift is gone; only the orphan remains.
    remaining = verify_corpus(corpus)
    assert [f.kind for f in remaining] == [ORPHANED]
    assert journal.total_corrections == 3


def test_loop_never_invents_text():
    """Every corrected entry is byte-identical to its source utterance."""
    corpus, faults = demo_setup()
    integrity_loop(corpus, faults=faults)
    for card in corpus.cards:
        try:
            source = corpus.utterance_text(card.provenance.meeting_id, card.provenance.timestamp)
        except KeyError:
            continue  # the quarantined orphan
        assert card.rule_text == source
    for d in corpus.directives:
        source = corpus.utterance_text(d.provenance.meeting_id, d.provenance.timestamp)
        assert d.request_text == source


def test_remediated_verdict_without_orphans():
    corpus = build_corpus(DEFAULT_SEED)
    card = corpus.cards[0]
    corpus.cards[0] = dataclasses.replace(card, rule_text=card.rule_text + " x")
    journal = integrity_loop(corpus)
    assert journal.verdict == REMEDIATED
    assert not journal.quarantined
    assert verify_corpus(corpus) == []


def test_clean_corpus_is_clean_verdict():
    journal = integrity_loop(build_corpus(DEFAULT_SEED))
    assert journal.verdict == CLEAN
    assert not journal.turns


def test_budget_exhaustion_escalates():
    corpus, faults = demo_setup()
    journal = integrity_loop(corpus, faults=faults, budget=1)
    # One meeting settled; the second still carries fixable drift.
    assert journal.verdict == ESCALATED
    assert len(journal.turns) == 1


def test_verdict_exit_codes():
    assert verdict_exit_code(CLEAN) == 0
    assert verdict_exit_code(REMEDIATED) == 0
    assert verdict_exit_code(ESCALATED) == 3


# --------------------------------------------------------------------------- #
# Determinism + rendering + CLI.
# --------------------------------------------------------------------------- #
def test_loop_is_deterministic():
    c1, f1 = demo_setup()
    c2, f2 = demo_setup()
    md1 = render_markdown(integrity_loop(c1, faults=f1))
    md2 = render_markdown(integrity_loop(c2, faults=f2))
    assert md1 == md2


def test_markdown_report_contents():
    corpus, faults = demo_setup()
    md = render_markdown(integrity_loop(corpus, faults=faults))
    assert "ESCALATED" in md
    assert "Held, not repaired" in md
    assert "No source, no guess" in md


def test_cli_smoke(tmp_path):
    from brain_engine.loop import main

    rc = main(["--demo", "--out", str(tmp_path)])
    assert rc == 3  # orphan quarantined -> refusal exit code
    assert (tmp_path / "integrity_loop_report.md").exists()
    assert main([]) == 0  # pristine corpus is clean
