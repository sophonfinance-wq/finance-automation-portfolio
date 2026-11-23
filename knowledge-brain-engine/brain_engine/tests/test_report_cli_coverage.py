"""Additional coverage for the reporting layer and the CLI.

Pins the citation-block primitive, every render_* view (including refusal
banners), the change-log table escaping, and CLI exit codes / argument
validation. Everything exercises real ``brain_engine.report`` / ``brain_engine.cli``
code; file writes go only to pytest's ``tmp_path``.
"""

from __future__ import annotations

import pytest

from brain_engine import cli
from brain_engine.engine import BrainEngine
from brain_engine.generate import REVIEW_MEETING_TITLE, build_corpus
from brain_engine.report import (
    REFUSAL,
    citation_block,
    render_ask,
    render_change_log,
    render_citation,
    render_index,
    render_prep,
    render_remediation,
)


def _engine():
    return BrainEngine(build_corpus())


# --- citation_block primitive ---------------------------------------------
def test_citation_block_quotes_with_blockquote_marker() -> None:
    hit = _engine().ask("warranty reserve book-tax")[0]
    block = citation_block(hit)
    assert block.startswith(f"> {hit.card.rule_text}")
    assert hit.card.provenance.citation_tag() in block


def test_citation_block_reports_relevance_with_three_decimals() -> None:
    hit = _engine().ask("warranty reserve book-tax")[0]
    block = citation_block(hit)
    assert f"relevance {hit.score:.3f}" in block
    assert hit.card.card_id in block


@pytest.mark.parametrize(
    "kind, label",
    [
        ("decision", "Decision"),
        ("rule", "Rule"),
        ("definition", "Definition"),
        ("open-item", "Open item"),
    ],
)
def test_citation_block_kind_label(kind, label) -> None:
    engine = _engine()
    card = next(c for c in engine.corpus.cards if c.kind == kind)
    from brain_engine.engine import RetrievalHit

    block = citation_block(RetrievalHit(card=card, score=0.5))
    assert label in block


# --- render_ask ------------------------------------------------------------
def test_render_ask_lists_each_hit_numbered() -> None:
    engine = _engine()
    q = "return of capital beyond basis"
    hits = engine.ask(q)
    text = render_ask(q, hits)
    assert f"{len(hits)} sourced answer(s)" in text
    for i in range(1, len(hits) + 1):
        assert f"## {i}." in text


def test_render_ask_refusal_banner_and_no_citations() -> None:
    text = render_ask("parking policy", [])
    assert REFUSAL in text
    assert "refuses" in text.lower()
    assert "## 1." not in text


def test_render_ask_includes_fictional_marker() -> None:
    engine = _engine()
    q = "surplus distribution"
    assert "[FICTIONAL]" in render_ask(q, engine.ask(q))


# --- render_citation -------------------------------------------------------
def test_render_citation_footnote_has_byte_identical_quote() -> None:
    engine = _engine()
    a = "return of capital in excess of basis is a deemed gain"
    hit = engine.cite(a)
    text = render_citation(a, hit)
    assert hit is not None
    assert hit.card.rule_text in text
    assert "byte-identical" in text


def test_render_citation_refusal_when_none() -> None:
    text = render_citation("the weather forecast", None)
    assert REFUSAL in text
    assert "authoritative card" in text


# --- render_prep -----------------------------------------------------------
def test_render_prep_has_both_sections() -> None:
    engine = _engine()
    topic = "warranty reserve book-tax treatment"
    text = render_prep(topic, engine.prep(topic))
    assert "## Settled prior positions" in text
    assert "## Open items to resolve" in text


def test_render_prep_refusal_when_empty() -> None:
    text = render_prep("cafeteria menu", [])
    assert REFUSAL in text
    assert "no prior decisions" in text.lower()


def test_render_prep_settled_none_on_record_when_only_open_items() -> None:
    # Build hits comprising only an open-item card -> settled section says none.
    engine = _engine()
    from brain_engine.engine import RetrievalHit
    from brain_engine.model import OPEN_ITEM

    open_card = next(c for c in engine.corpus.cards if c.kind == OPEN_ITEM)
    text = render_prep("x", [RetrievalHit(card=open_card, score=0.5)])
    # The settled section should render the empty placeholder.
    settled_part = text.split("## Open items to resolve")[0]
    assert "_None on record._" in settled_part


# --- render_index ----------------------------------------------------------
def test_render_index_reports_counts_and_catalogue() -> None:
    engine = _engine()
    text = render_index(engine)
    summary = engine.index_summary()
    assert f"**Knowledge cards:** {summary['cards']}" in text
    assert "Card catalogue" in text
    # Every card id appears in the catalogue table.
    for card in engine.corpus.cards:
        assert card.card_id in text


def test_render_index_kind_table_counts_match_summary() -> None:
    engine = _engine()
    text = render_index(engine)
    summary = engine.index_summary()
    for kind, label in [
        ("decision", "Decision"),
        ("rule", "Rule"),
        ("definition", "Definition"),
        ("open-item", "Open item"),
    ]:
        count = summary["kind_counts"].get(kind, 0)
        assert f"| {label} | {count} |" in text


# --- render_remediation / render_change_log -------------------------------
def test_render_remediation_lists_directives_and_prompt_block() -> None:
    rem = _engine().remediate(REVIEW_MEETING_TITLE)
    text = render_remediation(rem)
    assert "Change-directives (in spoken order)" in text
    assert "Ready-to-paste remediation prompt" in text
    assert "```text" in text
    for d in rem.directives:
        assert d.request_text in text


def test_render_remediation_refusal_when_empty() -> None:
    rem = _engine().remediate("parking policy")
    text = render_remediation(rem)
    assert REFUSAL in text
    assert "manufacture corrections" in text


def test_render_change_log_table_header_and_rows() -> None:
    rem = _engine().remediate(REVIEW_MEETING_TITLE)
    text = render_change_log(rem)
    assert "| # | Change requested (verbatim) |" in text
    for entry in rem.fix_packet:
        assert f"`{entry.directive.directive_id}`" in text
        assert entry.status in text


def test_render_change_log_refusal_when_empty() -> None:
    text = render_change_log(_engine().remediate("parking policy"))
    assert REFUSAL in text


def test_render_change_log_escapes_pipe_in_quote() -> None:
    # Construct a directive whose request text contains a pipe; the table must
    # escape it so the Markdown columns are not broken.
    from brain_engine.engine import FixPacketEntry, Remediation
    from brain_engine.model import ChangeDirective, Provenance

    prov = Provenance("MTG-X", "Review", "2025-04-08", "Quinn", "00:01:04")
    d = ChangeDirective("DIR-PIPE", ("review",), "use A | B not C", prov, target="x|y")
    rem = Remediation(
        topic="Review",
        directives=(d,),
        prompt="",
        fix_packet=(FixPacketEntry(number=1, directive=d),),
    )
    text = render_change_log(rem)
    assert "use A \\| B not C" in text
    assert "x\\|y" in text


# --- CLI exit codes & validation ------------------------------------------
def test_cli_min_relevance_out_of_range_returns_two(capsys) -> None:
    code = cli.main(["--min-relevance", "1.5", "ask", "warranty"])
    assert code == 2
    assert "min-relevance" in capsys.readouterr().err


def test_cli_remediate_without_topic_returns_two(capsys) -> None:
    code = cli.main(["remediate", ""])
    assert code == 2
    assert "remediate requires" in capsys.readouterr().err


def test_cli_ask_empty_question_returns_two(capsys) -> None:
    code = cli.main(["ask", ""])
    assert code == 2
    assert "ask requires" in capsys.readouterr().err


def test_cli_bare_question_positional_is_treated_as_ask(capsys) -> None:
    code = cli.main(["return of capital beyond basis"])
    out = capsys.readouterr().out
    assert code == 0
    assert "CARD-ROC" in out


def test_cli_prep_refusal_exit_code(capsys) -> None:
    code = cli.main(["--prep", "cafeteria menu rotation"])
    out = capsys.readouterr().out
    assert code == 3
    assert REFUSAL in out


@pytest.mark.parametrize(
    "argv, expected_code",
    [
        (["ask", "warranty reserve book-tax"], 0),
        (["ask", "office parking and lunch policy"], 3),
        (["--cite", "return of capital in excess of basis is a deemed gain"], 0),
        (["--cite", "the weather forecast next week"], 3),
        (["--prep", "warranty reserve book-tax treatment"], 0),
        (["remediate", REVIEW_MEETING_TITLE], 0),
        (["remediate", "cafeteria menu rotation"], 3),
        ([], 0),
    ],
)
def test_cli_exit_codes_table(argv, expected_code, capsys) -> None:
    code = cli.main(argv)
    capsys.readouterr()
    assert code == expected_code


def test_cli_out_writes_all_five_deliverables(tmp_path, capsys) -> None:
    code = cli.main(["--out", str(tmp_path)])
    capsys.readouterr()
    assert code == 0
    for name in (
        "brain_index.md",
        "citation_example.md",
        "meeting_prep_example.md",
        "remediation_prompt.md",
        "change_log.md",
    ):
        assert (tmp_path / name).exists()
