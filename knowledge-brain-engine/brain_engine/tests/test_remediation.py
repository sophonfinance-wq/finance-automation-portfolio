"""Tests for the review-to-remediation capability.

Covers: directive extraction with full provenance, the generated remediation
prompt (every directive in order, each with a byte-identical source quote +
timestamp), the cited change-log (1:1 with directives, PENDING status),
determinism, and refuse/empty when a review topic has no directives.
"""

from __future__ import annotations

from brain_engine import cli
from brain_engine.engine import STATUS_PENDING, BrainEngine
from brain_engine.generate import REVIEW_MEETING_TITLE, build_corpus
from brain_engine.model import ChangeDirective
from brain_engine.report import REFUSAL, render_change_log, render_remediation


def _engine():
    return BrainEngine(build_corpus())


def _review_directives(engine):
    return engine.directives_for(REVIEW_MEETING_TITLE)


# --- directives are extracted with full provenance ------------------------
def test_corpus_has_change_directives() -> None:
    corpus = build_corpus()
    assert corpus.directives
    assert all(isinstance(d, ChangeDirective) for d in corpus.directives)


def test_every_directive_has_full_provenance() -> None:
    corpus = build_corpus()
    for directive in corpus.directives:
        prov = directive.provenance
        assert prov.meeting_id
        assert prov.title
        assert prov.date
        assert prov.speaker
        assert prov.timestamp
        assert len(prov.timestamp.split(":")) == 3  # HH:MM:SS


def test_directive_request_text_is_byte_identical_to_source_utterance() -> None:
    """Each directive's request must exist verbatim in some transcript utterance."""
    corpus = build_corpus()
    for directive in corpus.directives:
        source = corpus.utterance_text(
            directive.provenance.meeting_id, directive.provenance.timestamp
        )
        assert directive.request_text == source


def test_review_meeting_emits_no_standing_cards() -> None:
    """A review meeting issues directives, not standing knowledge cards."""
    corpus = build_corpus()
    review_cards = [
        c for c in corpus.cards if c.provenance.title == REVIEW_MEETING_TITLE
    ]
    assert review_cards == []


# --- resolution: title + topic-tag, and refusal ---------------------------
def test_directives_for_resolves_by_full_review_title() -> None:
    engine = _engine()
    directives = _review_directives(engine)
    assert len(directives) == 4
    ids = [d.directive_id for d in directives]
    assert ids == [
        "DIR-SURPLUS-REVIEW-01",
        "DIR-SURPLUS-REVIEW-02",
        "DIR-SURPLUS-REVIEW-03",
        "DIR-SURPLUS-REVIEW-04",
    ]


def test_directives_for_resolves_by_short_title_substring() -> None:
    engine = _engine()
    ids = [d.directive_id for d in engine.directives_for("Surplus Workpaper Review")]
    assert ids == [
        "DIR-SURPLUS-REVIEW-01",
        "DIR-SURPLUS-REVIEW-02",
        "DIR-SURPLUS-REVIEW-03",
        "DIR-SURPLUS-REVIEW-04",
    ]


def test_directives_for_refuses_unknown_topic() -> None:
    engine = _engine()
    assert engine.directives_for("cafeteria menu rotation") == []


def test_directives_are_returned_in_spoken_order() -> None:
    engine = _engine()
    timestamps = [d.provenance.timestamp for d in _review_directives(engine)]
    assert timestamps == sorted(timestamps)


# --- the generated remediation prompt -------------------------------------
def test_remediation_prompt_contains_every_directive_in_order() -> None:
    engine = _engine()
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    prompt = rem.prompt
    positions = [prompt.index(d.request_text) for d in rem.directives]
    assert positions == sorted(positions)  # in order, all present
    assert len(positions) == len(rem.directives)


def test_remediation_prompt_carries_verbatim_quote_and_timestamp_per_directive() -> None:
    engine = _engine()
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    for directive in rem.directives:
        # The verbatim request appears as an explicit source quote...
        assert f'Source quote: "{directive.request_text}"' in rem.prompt
        # ...and the timestamp travels with it.
        assert directive.provenance.timestamp in rem.prompt


def test_remediation_prompt_is_numbered_one_per_directive() -> None:
    engine = _engine()
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    for entry in rem.fix_packet:
        assert f"{entry.number}. {entry.directive.request_text}" in rem.prompt


def test_remediation_prompt_instructs_hands_free_and_log_against_source() -> None:
    engine = _engine()
    prompt = engine.remediate(REVIEW_MEETING_TITLE).prompt
    assert "hands-free" in prompt
    assert "change log" in prompt.lower()
    assert "APPLIED" in prompt
    assert "never guess" in prompt.lower()


# --- the change-log / fix-packet ------------------------------------------
def test_fix_packet_maps_one_to_one_with_directives() -> None:
    engine = _engine()
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert len(rem.fix_packet) == len(rem.directives)
    for entry, directive in zip(rem.fix_packet, rem.directives):
        assert entry.directive is directive
    numbers = [e.number for e in rem.fix_packet]
    assert numbers == list(range(1, len(rem.directives) + 1))


def test_fix_packet_entries_start_pending() -> None:
    engine = _engine()
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert all(entry.status == STATUS_PENDING for entry in rem.fix_packet)
    assert STATUS_PENDING == "PENDING"


def test_change_log_carries_verbatim_citation_per_directive() -> None:
    engine = _engine()
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    text = render_change_log(rem)
    for directive in rem.directives:
        prov = directive.provenance
        assert directive.request_text in text  # byte-identical quote
        assert prov.date in text
        assert prov.timestamp in text
        assert prov.speaker in text


# --- determinism ----------------------------------------------------------
def test_remediation_prompt_is_deterministic() -> None:
    a = BrainEngine(build_corpus()).remediate(REVIEW_MEETING_TITLE).prompt
    b = BrainEngine(build_corpus()).remediate(REVIEW_MEETING_TITLE).prompt
    assert a == b


def test_remediation_directive_order_is_deterministic() -> None:
    a = [d.directive_id for d in BrainEngine(build_corpus()).remediate(REVIEW_MEETING_TITLE).directives]
    b = [d.directive_id for d in BrainEngine(build_corpus()).remediate(REVIEW_MEETING_TITLE).directives]
    assert a == b


# --- refuse / empty on a topic with no directives -------------------------
def test_remediate_empty_on_unknown_topic() -> None:
    engine = _engine()
    rem = engine.remediate("office parking lunch policy")
    assert rem.is_empty
    assert rem.directives == ()
    assert rem.fix_packet == ()


def test_render_remediation_refuses_when_empty() -> None:
    engine = _engine()
    rem = engine.remediate("office parking lunch policy")
    assert REFUSAL in render_remediation(rem)


def test_render_change_log_refuses_when_empty() -> None:
    engine = _engine()
    rem = engine.remediate("office parking lunch policy")
    assert REFUSAL in render_change_log(rem)


def test_empty_remediation_prompt_does_not_invent_changes() -> None:
    engine = _engine()
    prompt = engine.remediate("cafeteria menu rotation").prompt
    assert "Do not invent" in prompt
    assert "Changes to apply:" not in prompt


# --- CLI wiring -----------------------------------------------------------
def test_cli_remediate_returns_zero_and_lists_directives(capsys) -> None:
    code = cli.main(["remediate", REVIEW_MEETING_TITLE])
    out = capsys.readouterr().out
    assert code == 0
    assert "DIR-SURPLUS-REVIEW-01" in out
    assert "Ready-to-paste remediation prompt" in out


def test_cli_remediate_refusal_exit_code(capsys) -> None:
    code = cli.main(["remediate", "cafeteria menu rotation"])
    out = capsys.readouterr().out
    assert code == 3
    assert REFUSAL in out


def test_cli_out_writes_remediation_and_change_log(tmp_path, capsys) -> None:
    code = cli.main(["--out", str(tmp_path)])
    capsys.readouterr()
    assert code == 0
    assert (tmp_path / "remediation_prompt.md").exists()
    assert (tmp_path / "change_log.md").exists()


def test_written_change_log_is_byte_identical_to_source(tmp_path, capsys) -> None:
    cli.main(["--out", str(tmp_path)])
    capsys.readouterr()
    engine = _engine()
    text = (tmp_path / "change_log.md").read_text(encoding="utf-8")
    for directive in _review_directives(engine):
        assert directive.request_text in text
